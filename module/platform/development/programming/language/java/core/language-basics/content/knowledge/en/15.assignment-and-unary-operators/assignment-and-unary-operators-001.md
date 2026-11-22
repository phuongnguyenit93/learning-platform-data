# Assignment `=` and the Value of an Assignment Expression — Java 17+

## 1. Objective and Concept

In Java, the `=` operator is used to **assign a value to a variable** (*assignment*). More importantly: **an assignment itself is also an expression that has a type and a value** if it is evaluated successfully.

~~~java
int count = 1;
int result = (count = 5) + 2;

System.out.println(count);  // 5
System.out.println(result); // 7
~~~

Execution flow:

1. `count = 5` changes the value of the variable `count` to `5`.
2. The assignment expression `(count = 5)` has **type `int`** and **value `5`**.
3. `5 + 2` equals `7`, which is assigned to `result`.

From here, we need to clearly separate the **two effects** of an assignment:

- **Updating the storage location** (*side effect*): changing the value of the variable on the left-hand side.
- **Producing an expression value**: the expression `a = b` itself yields a value that can be used inside an enclosing expression.

This is the **static type** semantics of Java 17+, not dynamic typing or a special syntax made only for examples.

## 2. How Is `=` Different from `==`?

| Operator | Purpose | Example | Result |
|---|---|---|---|
| `=` | **Assign** a value to a variable | `x = 10` | Updates `x`; the assignment expression has value 10 |
| `==` | **Equality comparison** | `x == 10` | Expression of type `boolean` |
| `!=` | **Inequality comparison** | `x != 10` | Expression of type `boolean` |

Example:

~~~java
int x = 10;

System.out.println(x == 10); // true
System.out.println(x != 10); // false

x = 20;
System.out.println(x);       // 20
~~~

**Common pitfall:**

~~~java
boolean allowed = false;

if (allowed = true) { // Valid, but it is an ASSIGNMENT, not a comparison
    System.out.println("entered");
}
~~~

The `if` line above sets `allowed = true`; the assignment expression returns `true`, so the branch is executed. This is a **logic bug that easily slips past the compiler** because both the type and syntax are valid.

If the intent is to check, write `if (allowed)` or `if (allowed == true)` (the first form is usually cleaner). If you want to check for `false`, use `if (!allowed)`.

## 3. Components of a Simple Assignment

Basic syntax:

~~~java
variable = expression
~~~

- **The left-hand side** must denote an **assignable variable**, such as a local variable, a field, or an array component.
- **The right-hand side** is evaluated to obtain a value compatible with the type of the variable on the left.
- When it completes normally, the variable on the left receives the assigned value.

Example:

~~~java
int local = 0;
local = 12; // Local variable

int[] data = {1, 2};
data[1] = 9; // Array element

Box box = new Box();
box.value = 4; // Object field (class Box is defined in the standalone example below)
~~~

Not every expression that has a value can stand on the left of `=`:

~~~java
// 5 = local;                // INVALID: a literal is not a variable
// (local + 1) = 10;         // INVALID: the result of addition is not a variable
// Math.abs(local) = 10;     // INVALID: the result of a method call is not a variable
~~~

**`=` is not like the symmetric mathematical equals sign.** `x = y` and `y = x` are **two different operations**: the location updated is the variable on the left-hand side.

## 4. Value and Type of an Assignment Expression

The type of `x = expression` is tied to **the type of the variable on the left-hand side** according to language rules (including *capture conversion* details in generic cases). The expression value is **the value of the variable after assignment**, not an arbitrarily inferred new type.

~~~java
int n = 0;
long wider = (n = 7); // n=7; the int value 7 is widened to long

System.out.println(n);     // 7
System.out.println(wider); // 7
~~~

Here `(n = 7)` has type `int`. The outer assignment `long wider = ...` then widens from `int` to `long`.

With smaller numeric types:

~~~java
byte small = 0;
int combined = (small = 42) + 1;

System.out.println(small);    // 42
System.out.println(combined); // 43
~~~

`small = 42` has type `byte` and value 42; when adding 1, Java applies *binary numeric promotion*, so `(small = 42) + 1` has type `int` and value 43.

**Do not assume that every assignment returns a new reference variable or a copy of an object.** The expression yields a **value** (for references, the reference value) and updates the assigned location; those are two distinct aspects.

## 5. Type Conversion on Assignment: Valid and Invalid

Java checks the static type of the right-hand side using **assignment conversion**. Some common cases:

| Code pattern | Outcome | Explanation |
|---|---|---|
| `long a = 7;` | Valid | `int` to `long` (widening) |
| `double d = 7;` | Valid | `int` to `double` |
| `byte b = 42;` | Valid | Constant `int` literal within `byte` range is allowed to narrow on assignment |
| `byte b = 128;` | Compile error | Constant 128 is outside the `byte` range |
| `int n = 3.5;` | Compile error | `double` does not automatically narrow to `int` |
| `int n = (int) 3.5;` | Valid | Explicit cast, value 3 |
| `Integer boxed = 7;` | Valid | Autoboxing `int` to `Integer` |
| `Long boxed = 7;` | Compile error | Does not automatically chain `int → long → Long` in this assignment |
| `Long boxed = 7L;` | Valid | Boxing `long` to `Long` |

An important feature: **constant expression narrowing** in assignment:

~~~java
byte small = 100;  // int constant 100 is within the byte range
int variable = 100;
// byte other = variable; // Compile error: int variable is not a constant allowed to narrow
byte other = (byte) variable; // Syntactically valid; range must be checked manually
~~~

If a cast is used outside the valid range, data may be lost or overflow. An assignment that compiles **does not guarantee** that the data satisfies business requirements.

## 6. Chained Assignment: A Consequence of Assignment Expression Values

Because `(b = 9)` both updates `b` and produces the value `9`, Java allows using it as the right-hand side of another assignment:

~~~java
int a, b, c;
a = b = c = 9; // a, b, and c are all equal to 9
~~~

The `=` operator **associates from right to left**: `a = (b = (c = 9))`. This describes how the expression is **grouped**, not that all operands in Java are evaluated from right to left. Each assignment still goes through its own type check; for example, `long wide; int narrow; wide = narrow = 8;` is valid, whereas assigning a `long` result back to `int` is not automatically valid.

To fully understand when chained assignment should be avoided—especially with array indices, method calls, and multiple reference variables—see the lesson **“Chained Assignment and Why It Should Be Limited in Java”**. In this lesson, the key takeaway is that **the value of one assignment can serve as the input to another assignment**.

## 7. Where Can an Assignment Expression Be Used?

An assignment can serve as a **statement expression** or as part of a larger expression:

~~~java
int x = 1;

x = 5;                 // Assignment statement
int y = (x = 6) + 2;   // Assignment used as a subexpression
boolean changed = (x = 7) > 5; // Result of x=7 is compared

System.out.println(x);       // 7
System.out.println(y);       // 8
System.out.println(changed); // true
~~~

Also, with a boolean variable:

~~~java
boolean ready = false;
boolean copied = (ready = true);

System.out.println(ready);  // true
System.out.println(copied); // true
~~~

However, **being allowed does not mean it should be overused**. Business code is usually much clearer when separated:

~~~java
x = 7;
boolean changed = x > 5;
~~~

This is especially important if the right-hand side contains a method with side effects or a computation that may throw an exception.

## 8. Assignment Expressions and the Conditional Expression

Example with the conditional expression:

~~~java
int count = 0;
boolean valid = true;

int selected = valid ? (count = 10) : (count = -1);

System.out.println(selected); // 10
System.out.println(count);    // 10
~~~

When `valid` is true, only the `count = 10` branch is evaluated; the other branch does not execute. The value of the selected assignment becomes the result of the conditional expression.

**Important point:** assigning state inside `?:` can be hard to inspect; the conventional form is easier to read:

~~~java
if (valid) {
    count = 10;
} else {
    count = -1;
}
int selected = count;
~~~

Which approach is right depends on the scale of the logic, but you should avoid placing important side effects inside deeply nested expressions.

## 9. Evaluation Order When Using an Assigned Value in a Calculation

~~~java
int n = 1;
int result = (n = 4) + n;
System.out.println(result); // 8
System.out.println(n);      // 4
~~~

The left operand `(n = 4)` is evaluated before the right operand `n`. It updates `n` and supplies `4`; the subsequent read also sees `4`. Both “providing a value” and “changing state” happen in a single expression, so be cautious when placing assignments inside arithmetic or conditions.

Situations with multiple `++`/`--` operations on the same variable require a different tracing approach and are analyzed in the final lesson of this chapter. Here, the safe pattern when no side effect is needed inside the expression is to separate them clearly:

~~~java
n = 4;
int simplerResult = n + n; // 8
~~~

## 10. Fields and Array Elements Also Use Assignments with Values

Field example:

~~~java
static final class Box {
    int value;
}

Box box = new Box();
int assignedField = (box.value = 12);

System.out.println(box.value);     // 12
System.out.println(assignedField); // 12
~~~

Array example:

~~~java
int[] scores = {3, 7};
int assignedElement = (scores[1] = 20);

System.out.println(scores[1]);      // 20
System.out.println(assignedElement); // 20
~~~

In both cases, the assignment expression updates **an actual variable**: a field or an array component. The expression value reflects the value after assignment.

### Array Indices Can Have Their Own Side Effects

~~~java
int[] values = {10, 20};
int index = 0;
int result = (values[index++] = 99) + index;

System.out.println(values[0]); // 99
System.out.println(index);     // 1
System.out.println(result);    // 100
~~~

`index++` provides index 0 and then increments `index` to 1. The element assignment yields 99; the right-hand side `+ index` uses 1. The example is valid, but **harder to read and easier to mismodify** than separating index selection, array update, and summation.

## 11. Assigning a Reference Does Not Copy the Object

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder alias = first;

alias.append("B");
System.out.println(first); // AB
~~~

`alias = first` copies the **reference value**, so both variables point to the **same object**; the assignment does not create a copy of the `StringBuilder`.

When assigning a new reference to a variable:

~~~java
StringBuilder original = first;
first = new StringBuilder("C");

System.out.println(original); // AB
System.out.println(first);    // C
~~~

`first` points to the new object; `original` still points to the old object. Do not confuse **reassigning a reference variable** with **mutating an object's contents**.

If an independent object is desired, you must use an appropriate copy mechanism provided by the class, such as `new StringBuilder(first.toString())` in this context.

## 12. Boundary Between `=` and Compound Assignments

A simple assignment `x = value` converts the right-hand side according to *assignment conversion* rules. A compound assignment such as `x += value` also performs the operation and can **implicitly narrow** the result to the left-hand side's type; for a complex left-hand side, it evaluates the left-hand side **only once**. This is a semantic difference, not just shorthand syntax:

~~~java
byte b = 120;
b += 10;             // Valid; 130 narrows to byte as -126.
// b = b + 10;       // Compile error: ordinary addition produces int.

String label = "value=";
label += 7;          // String concatenation: "value=7".
~~~

This lesson uses those examples only to **draw the boundary with the `=` operator**. In real calculations, check numeric ranges and side effects; do not blindly replace `op=` with `x = x op y` when the left-hand side is an expression with side effects.

## 13. Assignment and `final` Constraints

`final` restricts **reassigning a variable**, not necessarily making the referenced object immutable:

~~~java
final int once;
once = 10; // Valid: local final variable is definitely assigned exactly once.
// once = 11; // Compile error: reassignment.

final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Valid: mutating object state.
// builder = new StringBuilder("C"); // Error: reassigning a final reference.
~~~

The value of an `=` assignment does not bypass definite assignment and `final` rules. When you only need to update an ordinary variable, prefer a standalone, easy-to-inspect statement rather than nesting it inside a large expression.

## 14. Exceptions and Errors on the Right-Hand Side

An assignment completes normally only when all required steps succeed. Example where the right-hand side throws an exception:

~~~java
int value = 3;
int divisor = 0;

try {
    value = 10 / divisor;
} catch (ArithmeticException ex) {
    System.out.println("division failed");
}
System.out.println(value); // 3
~~~

For this simple local variable, the division `10 / divisor` fails **before the new value is assigned**, so `value` remains 3.

However, do not generalize that every failed assignment expression has **no side effects**: evaluating the left-hand side or right-hand side may already have called a method, incremented an index, mutated an object, or performed I/O before the exception occurred.

**Recommendation:** validate inputs and minimize multiple side effects within a single assignment expression, especially in transactional logic.

## 15. Common Mistakes and How to Fix Them

| Mistake / Misconception | Why Is It Wrong? | Correct Approach |
|---|---|---|
| `x = 5` is a comparison | `=` assigns, it does not compare | `x == 5` |
| `if (ready = true)` to check `ready` | Actually assigns true so the condition is always true | `if (ready)` |
| `5 = x` | A literal is not an assignable variable | `x = 5` |
| `a + 1 = 3` | The result of addition cannot be assigned to | Assign to an appropriate variable |
| `int x = 3.5;` | `double` does not auto-convert to `int` | Cast with range checks or use `double` |
| `Long boxed = 7;` | Does not auto-convert `int → long → Long` | `Long boxed = 7L;` |
| `byte b = 128;` | Constant does not fit in `byte` range | Choose a sufficiently large type; do not mask with a cast |
| Thinking `a = b = 9` groups from the left | Assignment is right-associative | `a = (b = 9)` |
| `i = i++` to increment `i` | The outer assignment overwrites the postfix increment | `i++;` |
| Thinking an assignment expression has no value | It has the value after assignment | `(x = 5) + 2` can be used, but weigh readability |
| `byte b; b = b + 1;` | `int` result does not auto-narrow | Choose `int` or cast with checks |
| Thinking `b += 1` is always identical to `b = b + 1` | Compound assignment has specific type conversion and single LHS evaluation | Understand the rules before changing code |
| Assigning a reference and assuming the object was cloned | Copies the reference, does not copy the object | Perform an explicit copy when needed |
| Reassigning a `final` variable | Violates definite assignment rules | Design for single initialization |
| Assuming `catch` always rolls back an assignment | Side effects before the error may already have happened | Separate steps/validation/transactions appropriately |

## 16. Complete Java 17 Program — Observing Assignments Alone

Save as `AssignmentExpressionDemo.java`. This example gathers cases of **simple assignments returning values** and distinguishes them from comparisons; programs for `op=`, chained assignment, and `++` are implemented in separate lessons.

~~~java
public final class AssignmentExpressionDemo {
    static final class Box {
        int value;
    }

    public static void main(String[] args) {
        int count = 1;
        int result = (count = 5) + 2;
        System.out.println("assignment=" + result + ",count=" + count);

        boolean ready = false;
        boolean expression = (ready = true);
        System.out.println("boolean=" + expression + ",ready=" + ready);

        int number = 0;
        long widened = (number = 7);
        System.out.println("widened=" + widened + ",number=" + number);

        Box box = new Box();
        int assignedField = (box.value = 12);
        System.out.println("field=" + assignedField + ",stored=" + box.value);

        int[] scores = {3, 7};
        int assignedElement = (scores[1] = 20);
        System.out.println("element=" + assignedElement + ",stored=" + scores[1]);

        StringBuilder first = new StringBuilder("A");
        StringBuilder alias = first;
        alias.append("B");
        System.out.println("alias=" + first);

        int unchanged = 3;
        int zero = 0;
        try {
            unchanged = 10 / zero;
        } catch (ArithmeticException ex) {
            System.out.println("rhs failed");
        }
        System.out.println("unchanged=" + unchanged);
    }
}
~~~

Compile and run with **JDK 17+** in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 AssignmentExpressionDemo.java
java AssignmentExpressionDemo
~~~

**Expected stdout:**

~~~text
assignment=7,count=5
boolean=true,ready=true
widened=7,number=7
field=12,stored=12
element=20,stored=20
alias=AB
rhs failed
unchanged=3
~~~

`(count = 5)` returns `5`; assigning a `boolean` returns `true`; the `int` value from `(number = 7)` can be widened to `long`. Field/array assignments update the exact storage location, while reference assignment only copies the reference. Finally, division by 0 causes the right-hand side to fail before `unchanged` receives a new value.

## 17. Exercises with Answers

### Exercise A — Value of an Assignment Expression

~~~java
int x = 2;
int y = (x = 6) * 3;
System.out.println(x);
System.out.println(y);
~~~

**Answer:**

~~~text
6
18
~~~

### Exercise B — Chained Assignment

~~~java
int a, b, c;
a = b = c = 4;
System.out.println(a + b + c);
~~~

**Answer:** `12`. All three variables receive 4 and are then summed as integers.

### Exercise C — Logic Bug with `=` and `==`

~~~java
boolean enabled = false;
if (enabled = true) {
    System.out.println("enabled");
}
~~~

**Answer:** prints `enabled`; the code **assigned true**, rather than comparing. If you only want to check the initial value, write `if (enabled)`.

### Exercise D — Difference Between `=` and `+=`

~~~java
byte a = 120;
a += 10;
System.out.println(a);
~~~

**Answer:** `-126`. Compound assignment automatically converts back to `byte`; `a = a + 10` is not automatically valid because ordinary addition returns `int`.

### Exercise E — Assignment Expression in an Array

~~~java
int[] data = {5, 8};
int result = (data[0] = 12) + data[1];
System.out.println(result);
System.out.println(data[0]);
~~~

**Answer:**

~~~text
20
12
~~~

### Exercise F — Local `final`

~~~java
final int value;
value = 3;
// value = 4;
~~~

**Answer:** assigning `3` is valid initialization; uncommenting `value = 4` causes a compile error due to reassigning a local `final` variable.

### Exercise G — Exception Handling

~~~java
int x = 10;
int zero = 0;
try {
    x = 1 / zero;
} catch (ArithmeticException ex) {
    System.out.println(x);
}
~~~

**Answer:** `10`. The right-hand side fails before the simple assignment updates `x`.

## 18. Checklist and Conclusion

- [ ] Understand that `=` is **assignment** and `==` is **equality comparison**.
- [ ] Know that the left-hand side must be an assignable variable (local, field, array component).
- [ ] Know that an assignment is an expression with a type and the post-assignment value.
- [ ] Understand that `int y = (x = 5) + 2;` both modifies `x` and produces the value 7.
- [ ] Understand that assignment checks *assignment conversion* against the target type.
- [ ] Know that the chain `a = b = c = 9` is grouped from right to left.
- [ ] Do not mistakenly use `if (condition = true)` instead of a boolean check.
- [ ] Recognize side effects when nesting assignments inside other expressions.
- [ ] Know that field/array assignments also produce values; watch out for changing indices.
- [ ] Know that reference assignment does not automatically copy the object.
- [ ] Distinguish simple `=` from compound assignments like `+=`.
- [ ] Understand that `final` prevents reassigning an already initialized variable.
- [ ] Know that an exception thrown on the right-hand side can prevent an assignment from completing.
- [ ] Run `AssignmentExpressionDemo.java` with `javac` and `java` on JDK 17+; verify the full stdout matches.

**Conclusion:** `a = b` in Java 17+ both **updates the variable `a`** and **produces an expression value** with a type checked at compile time. The ability to use an assignment inside a larger expression explains chained assignment, assignments in conditions, and arithmetic expressions — but it also introduces the risk of hard-to-read side effects. Prefer separate assignment statements with clear variable names, and only leverage the value of an assignment expression when it genuinely makes the code simpler.