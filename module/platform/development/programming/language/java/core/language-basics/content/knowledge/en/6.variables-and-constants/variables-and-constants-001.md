# Variable Declaration, Initialization, and Assignment in Java

## 1. Three Distinct Operations

A **variable** is a named, typed storage location. In Java 17+, a variable's type is checked at compile time. Learning how to use variables starts with three operations:

~~~java
int quantity;       // (1) Declaration: the name quantity has type int
quantity = 3;       // (2) Assigning the first value to the variable
quantity = 4;       // (3) Reassignment: replacing the currently stored value
~~~

You can also **declare and initialize in the same statement**:

~~~java
int quantity = 3;
~~~

| Operation | Example | What happens |
|---|---|---|
| Declaration | `int count;` | Introduces the variable `count` with type `int` |
| Initialization | `int count = 3;` | Creates the variable and immediately gives it an initial value |
| Assignment after declaration | `count = 3;` | Puts a value into an already declared variable |
| Reassignment | `count = 4;` | Replaces the old value with a new value |
| Reading a variable | `System.out.println(count);` | Uses the value currently held by the variable |

**Key point:** the `=` sign here is the **assignment operator**, not the mathematical "equals" sign. `count = 4` tells Java to store a new value; whereas `count == 4` is a **comparison** expression that returns a `boolean`.

## 2. Declaration Syntax and Type Rules

A typical local variable declaration has the form:

~~~java
Type variableName;
Type otherName = expression;
~~~

Examples:

~~~java
int age = 20;
long population = 8_000_000_000L;
double temperature = 26.5;
boolean active = true;
char grade = 'A';
String city = "Ha Noi";
~~~

Here `int`, `long`, `double`, `boolean`, `char` are primitive types; `String` is a reference type. The expression on the right-hand side must have a type **assignable** to the variable according to Java's type conversion rules.

A single declaration can also declare multiple variables of the same type:

~~~java
int width = 3, height = 4;
int area = width * height;
~~~

Although valid, in business code you should separate declarations if multiple variables have different meanings or complex initializers. You cannot use a single declaration to mix arbitrary types like `int a = 1, b = "hai";`.

### Variable Names and Scope

~~~java
int subtotal = 100;
if (subtotal > 0) {
    int discount = 10;
    System.out.println(subtotal - discount); // 90
}
// System.out.println(discount); // Error: discount is out of scope
~~~

A local variable is typically scoped to the block containing its declaration, starting from the point of declaration according to Java's rules. **Declare once** and reassign when needed; do not redeclare a local variable with the same name where it is prohibited:

~~~java
int count = 1;
count = 2;       // Valid: reassignment
// int count = 3; // Error: duplicate declaration in the same block
~~~


## 3. Conditions for a Valid Read

For a **local variable**, simply declaring it is not enough to read it: Java requires that it has been definitely assigned before that read (*definite assignment*).

~~~java
int score;
// System.out.println(score); // Error: might not have been initialized
score = 80;
System.out.println(score); // 80
~~~

**Parameters** receive values from the call; **fields and array elements** have default values based on their type. These mechanisms differ, so do not assume `int score;` inside a method automatically gets `0`. Analyzing `if` paths, loops, and `final` belongs to the in-depth lesson on *definite assignment*.

## 4. Assigning Values and Evaluating the Right-Hand Side

In a simple assignment:

~~~java
int unitPrice = 120;
int quantity = 3;
int subtotal = unitPrice * quantity;
~~~

Java evaluates the expression `unitPrice * quantity` and assigns the result `360` to `subtotal`.

If afterward:

~~~java
quantity = 4;
System.out.println(subtotal); // 360
subtotal = unitPrice * quantity;
System.out.println(subtotal); // 480
~~~

Then `subtotal` **does not update automatically** when `quantity` changes. A Java variable holds the value computed at the time of assignment; it is not a spreadsheet formula cell.

Assignment is also an **expression with a result**, so chained assignment can be used:

~~~java
int first, second;
first = second = 9; // Equivalent to first = (second = 9)
System.out.println(first + ", " + second); // 9, 9
~~~

Assignment is right-to-left associative. However, do not overuse nested assignments that make code hard to follow; separate statements are usually easier to test.

### `=` vs `==`

~~~java
int points = 10;
points = 20;                      // Reassignment
boolean matches = points == 20;  // Comparison, true
~~~

Inside a boolean condition, accidentally writing an assignment can **still compile and cause a bug**:

~~~java
boolean approved = false;
if (approved = true) { // Valid, but mutates approved!
    System.out.println("APPROVED");
}
~~~

If the goal is to check the value, write `if (approved)`. For integers, `if (points = 20)` does not compile because the assignment expression has type `int`, not `boolean`.


## 5. Limits to Know Before Assigning

A valid assignment must be **compatible with the declared type**; for example, `int amount = 10; long total = amount;` is valid, while `int amount = "10";` is a type error. With `var`, the compiler infers a **static** type from the initializer; with `final`, reassigning the variable is restricted. Details on type ranges, narrowing conversions, `final`, and object mutability have dedicated lessons in this chapter.

Here, always ask: which variable is being assigned, which expression must be evaluated first, and does the assigned value need to be recomputed when inputs change?

## 6. Java 17 Example: Tracing Each Assignment

Save the file `AssignmentWalkthrough.java`:

~~~java
public final class AssignmentWalkthrough {
    public static void main(String[] args) {
        int quantity;                 // Declaration
        quantity = 3;                 // First assignment
        int unitPrice = 120;          // Declaration and initialization
        int total = unitPrice * quantity;
        System.out.println("start=" + total);

        quantity = 4;                 // Reassigning an input
        System.out.println("stored=" + total);
        total = unitPrice * quantity; // Deliberate recomputation
        System.out.println("recomputed=" + total);

        int left, right;
        left = right = 9;             // Chained assignment right to left
        System.out.println("chain=" + left + "," + right);
        boolean same = total == 480;  // Comparison, not assignment
        System.out.println("same=" + same);

        int earlier = quantity;       // Copies the int value
        quantity = 5;
        System.out.println("copy=" + earlier + ", now=" + quantity);
    }
}
~~~

Using JDK 17 or later in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 AssignmentWalkthrough.java
java -cp . AssignmentWalkthrough
~~~

Output:

~~~text
start=360
stored=360
recomputed=480
chain=9,9
same=true
copy=4, now=5
~~~

`stored=360` does not automatically turn into `480` after `quantity` changes, because the variable `total` already received the result of the previous computation. `recomputed=480` only appears after a **new assignment**. `chain=9,9` is the result of `left = (right = 9)`; `same=true` comes from the `==` comparison. Finally, `earlier` remains `4` because assigning from an `int` variable copies the value, without creating an auto-updating link.

## 7. Common Confusions

| Code pattern | Issue | Correct perspective |
|---|---|---|
| `int n; System.out.println(n);` in a method | Unassigned local variable | Definitely assign before reading |
| `int n = 1; int n = 2;` in the same block | Duplicate declaration | Write `n = 2;` if you want to reassign |
| `int a, b = 5;` | Only `b` is initialized | Each name has its own initializer |
| `if (approved = true)` | Changes `approved` while checking | Write `if (approved)` if only checking |
| Changing `quantity` and expecting `total` to change | Assignment does not create a live formula | Recompute and reassign `total` when needed |

When debugging, mark the **read points** and **write points** of each variable. Inspect each RHS in execution order; do not read an assignment line as a mathematical equation.

## 8. Practice with Explanations

**Exercise 1.** Write two separate versions: `int score; score = 90;` and `int score = 90;`. What do both print?  
*Answer:* Both print `90`; they differ in when declaration/initialization occurs.

**Exercise 2.** Predict:

~~~java
int price = 25;
int count = 2;
int total = price * count;
count = 3;
System.out.println(total + "," + (price * count));
~~~

*Answer:* `50,75`; `total` keeps the assigned result, while the new expression uses `count = 3`.

**Exercise 3.** How does `int first, second; first = second = 7;` differ from `first == second`?  
*Answer:* The first assigns both variables; the second expression compares their values and returns a `boolean`.

**Exercise 4.** Given `int a = 2; int b = a; a = 9;`, does `b` change automatically?  
*Answer:* No, `b` stays `2` because it holds a copy of the value at the time of assignment.

### Self-Check

- [ ] Distinguish declaration, initialization, first assignment, reassignment, and reading a variable.
- [ ] Correctly predict RHS evaluation order and the effect of assignment.
- [ ] Know that `=` assigns a value while `==` compares.
- [ ] Do not confuse Java variables with self-updating formulas.
- [ ] Know basic boundaries regarding types, scope, and assigning before reading.
- [ ] Run `AssignmentWalkthrough.java` and explain each line of output.

**Conclusion:** Assignment changes the **value held in a variable at a point in time**. To change a computed result, the program must perform another assignment. Learning this first will help you deeply understand types, scope, `final`, and default values in the upcoming lessons.
