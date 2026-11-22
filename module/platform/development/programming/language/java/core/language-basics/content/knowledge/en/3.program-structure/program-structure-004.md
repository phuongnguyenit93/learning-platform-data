# Braces, Semicolons, and Blocks in Java

> **Java core — language-basics / Program Structure**  
> **Practice requirement:** JDK 17 or later; examples use syntax valid in Java 17.  
> **Objective:** Accurately distinguish `{ }` (curly braces), `;` (semicolon), and a *block*; know where `;` must be placed or omitted; understand variable scope and execution flow when using `if`, `for`, `while`, and `do...while`. Compile, run, and predict the output of a minimal Java program on your own.

## 1. Three Foundational Concepts

In Java, **syntax** determines whether a snippet forms valid statements; **block structure** determines which group of statements belongs to a branch or a loop.

| Symbol/concept | Primary role | Example | What it does not mean |
| --- | --- | --- | --- |
| `{` and `}` | Marks the boundaries of a class body, method body, or statement block; also has other uses such as array initializers | `if (ok) { run(); }` | Not every `{ }` pair is a block statement |
| `;` | Terminates many kinds of statements/declarations or acts as a separator in a `for` header | `int age = 20;` | Does not mean every line of Java must end with `;` |
| **Block** | A statement containing **zero or more** statements/local declarations enclosed in `{ }` | `{ int x = 1; print(x); }` | Line breaks or indentation do not automatically create a block |

Remember two independent rules:

- The `;` character usually **terminates a statement**, whereas `{ }` establishes a structural boundary for a group of statements.
- In Java, **indentation helps readability**, but curly braces and grammar — not the number of spaces — determine what an `if` branch or a loop contains.

~~~mermaid
flowchart TD
    A["Statements in main"] --> B["for (...) { ... }"]
    B --> C["if (condition) { ... }"]
    C --> D["total += number;"]
    B --> E["After for loop"]
    E --> F["System.out.println(...);"]
~~~

## 2. A Minimal Java 17+ Program with All Three Elements

Create the file **BlockSyntaxDemo.java**; the filename matches `public class BlockSyntaxDemo`:

~~~java
public final class BlockSyntaxDemo {

    private static int sumEvenUpTo(int limit) {
        int total = 0;

        for (int number = 1; number <= limit; number++) {
            if (number % 2 == 0) {
                total += number;
            }
        }

        return total;
    }

    public static void main(String[] args) {
        int limit = 6;
        int result = sumEvenUpTo(limit);

        System.out.println("Tong so chan tu 1 den " + limit + ": " + result);

        if (result > 0) {
            System.out.println("Da tim thay so chan");
        } else {
            System.out.println("Khong co so chan");
        }
    }
}
~~~

**Run in the terminal inside the directory containing the file:**

~~~bash
java -version
javac -version
javac -encoding UTF-8 BlockSyntaxDemo.java
java BlockSyntaxDemo
~~~

The first two commands verify the tools, not the program output. If compilation succeeds, `javac` normally prints nothing and creates `BlockSyntaxDemo.class`. The final command prints **exactly two lines**:

~~~text
Tong so chan tu 1 den 6: 12
Da tim thay so chan
~~~

Because the even numbers from 1 to 6 are 2, 4, and 6, the sum is 12.

### Inspecting each kind of punctuation in the example

| Snippet | Why is it written that way? |
| --- | --- |
| `public final class BlockSyntaxDemo { ... }` | Braces enclose the **class body**; no `;` is required after the closing `}` of a class declaration |
| `private static int sumEvenUpTo(int limit) { ... }` | Braces enclose the **method body** |
| `int total = 0;` | A local variable declaration statement ending with `;` |
| `for (...; ...; ...) { ... }` | Two `;` separators in the header split the three parts of a traditional `for` loop |
| `if (number % 2 == 0) { ... }` | Block belonging to the `if` branch; do not place `;` between `)` and `{` |
| `total += number;` | An expression statement modifying a variable, ending with `;` |
| `return total;` | A return statement, ending with `;` |
| `System.out.println(...);` | A method call used as a statement, ending with `;` |

**Note on names:** Use `java BlockSyntaxDemo` to launch the compiled class, not `java BlockSyntaxDemo.class`. Because the source file has no `package` declaration, the class name to run in this example is simply `BlockSyntaxDemo`.

## 3. How `{ }` Creates a Block

A block statement has the form:

~~~java
{
    // Can contain 0, 1, or many statements.
    int first = 2;
    int second = 3;
    System.out.println(first + second);
}
~~~

The block above is **valid when placed inside a method body or any position allowing a block statement**, but this standalone snippet is **not a complete Java file** that you can pass directly to `java`.

Inside a method, you can nest multiple blocks:

~~~java
int outer = 10;
{
    int inner = 5;
    System.out.println(outer + inner); // 15
}
System.out.println(outer);             // 10
// System.out.println(inner);          // Invalid: inner is out of scope.
~~~

**Scope:** the local variable `inner` is only usable within the block where it is declared, from its declaration point onward. The variable `outer` is declared outside, so the nested inner block can reference it. When the block ends, a local variable existing only in that block is no longer accessible.

This is also how it differs from a class **field**:

~~~java
class Counter {
    private int total;  // Field of each Counter object.

    void addOne() {
        int delta = 1;  // Local variable of the method.
        total += delta;
    }
}
~~~

`total` is an object field; `delta` is a local variable scoped only to the method. Do not use the end of a block to infer that an object holding fields has definitely been garbage-collected; those are two different concepts.

### Declaration boundaries and name shadowing

In overlapping local scopes, Java does not allow redeclaring a **local variable with the same name** as shown below:

~~~java
void example() {
    int value = 1;
    {
        // int value = 2; // Compile error: duplicate local variable name still in scope.
        System.out.println(value);
    }
}
~~~

Conversely, a field and a local variable can share the same name; in that case, syntax like `this.value` clarifies the object's field. This rule should only be introduced to prevent inferring that "just adding `{ }` lets you reuse any name."

## 4. When Is `;` Needed?

Many statements end with a semicolon, though **not all of them**. The table below summarizes common forms in Java 17:

| Form | Example | Has `;`? |
| --- | --- | --- |
| Local variable declaration | `int count = 0;` | Yes |
| Assignment and method call | `count++;`, `System.out.println(count);` | Yes |
| Return | `return count;` or `return;` in a `void` method | Yes |
| Exiting/skipping a loop | `break;`, `continue;` | Yes |
| `package` and `import` declarations | `package demo;`, `import java.util.List;` | Yes |
| `if` with a block | `if (ready) { work(); }` | **Do not** place `;` after the `if (...)` header |
| Traditional `for` | `for (int i = 0; i < 3; i++) { ... }` | Has **two** `;` inside the header |
| `while` with a block | `while (ready) { work(); }` | No `;` between `)` and `{` |
| `do...while` | `do { work(); } while (ready);` | Has `;` at the end |
| Method declaration with body | `void work() { ... }` | No `;` required after `}` |
| Class declaration with body | `class Example { ... }` | No `;` needed after `}` |

**More precisely:** `;` is a syntactic token, not simply "end of a line of code." Java allows multiple statements on a single line or one statement spanning multiple lines:

~~~java
int a = 1; int b = 2;
System.out.println(
        a + b
); // The statement ends here, not at the end of the first line.
~~~

The following two forms are not equivalent:

~~~java
int amount = 10;  // Complete statement.
int amount = 10   // If this is a standalone statement: missing ;, compile error.
~~~

The second line is only a **snippet illustrating invalid syntax**, not code to place together with the first line in a runnable program.


## 5. Syntax Trap: `;` Becomes the Body of `if`

A standalone `;` is an **empty statement**. When placed immediately after `if (condition)`, it becomes the entire body of the branch, while the block after it runs independently:

~~~java
boolean ready = false;
if (ready); // Empty if body.
{
    System.out.println("Khoi nay chay doc lap");
}
~~~

Even though `ready` is `false`, the snippet above (when placed inside a method) still prints `Khoi nay chay doc lap`. To print only when the condition is true, remove the `;` after the condition and write `if (ready) { ... }`.

This is a brief example of how the `;` token affects block structure. The lesson **Expression Statements and Empty Statements** explains in greater depth when `;` is a standalone statement and how it behaves in loops. With nested `if` branches lacking braces, `else` syntactically binds to the nearest `if` that can accept it, regardless of indentation.

## 6. Blocks in `for`, `while`, and `do...while`

### 6.1. Traditional `for` has two `;` separators

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Output:

~~~text
0
1
2
~~~

The three parts of the header are:

1. `int i = 0` — initialization, runs once before the loop.
2. `i < 3` — condition checked before each iteration.
3. `i++` — update after each execution of the loop body.

The two `;` separators in between are **mandatory for this construct**, even when some parts are omitted. For example, `for (;;) { break; }` is valid: the header has two separators while all three parts are empty, and the loop stops via `break;`.

### 6.2. Enhanced `for` does not use two `;`

~~~java
int[] values = {2, 4, 6};
for (int value : values) {
    System.out.println(value);
}
~~~

The colon `:` is enhanced-for syntax; do not confuse it with `for (init; condition; update)`. The array `values` is initialized with braces, but `{2, 4, 6}` here is an **array initializer**, not a block statement.

### 6.3. `while` has no `;` after the condition

~~~java
int remaining = 2;
while (remaining > 0) {
    System.out.println(remaining);
    remaining--;
}
~~~

The output is `2` then `1`. Semicolons appear at the **two statements inside** the block, not between `while (...)` and the block. Writing `while (remaining > 0);` where `remaining` does not change in the header can create a non-terminating empty loop.

### 6.4. `do...while` requires a trailing `;`

~~~java
int remaining = 2;
do {
    System.out.println(remaining);
    remaining--;
} while (remaining > 0);
~~~

The closing line `} while (...);` has a **mandatory** semicolon. The difference from `while` is that the `do` body executes at least once before checking the condition.

## 7. Blocks Determine Both Variable Scope and Code Validity

### Variables exist only inside the branch where they are declared

The snippet below illustrates a scope error:

~~~java
if (args.length > 0) {
    String first = args[0];
    System.out.println(first);
}
// System.out.println(first); // Error: first is only declared inside the if block.
~~~

It uses the `args` variable available **inside `main(String[] args)`**. Normalizing whitespace or adding `;` **does not** fix an out-of-scope variable name error.

### Difference between "declared" and "assigned a value"

A local variable must be **definitely assigned** before its value is read:

~~~java
int result;
if (args.length > 0) {
    result = args.length;
} else {
    result = 0;
}
System.out.println(result);  // Valid: every branch assigns result.
~~~

If you remove the `else` branch, the compiler can report `variable result might not have been initialized`. Java **does not** automatically initialize local variables to 0 just because the type is `int`; default value rules for fields differ from definite assignment rules for local variables.

This is a good example showing that `{ }` are not merely "for making code look nice": they represent the test branches, scopes, and control paths that the compiler analyzes.

## 8. Not Every `{ }` Is a Block Statement

Curly braces also appear in other Java 17 constructs:

### 8.1. Array initializer

~~~java
int[] scores = {8, 9, 10};
System.out.println(scores.length); // 3
~~~

`{8, 9, 10}` is an **array initializer**. The trailing `;` terminates the **variable declaration**, not a required semicolon after every `}`.

### 8.2. Lambda with a block body

~~~java
Runnable task = () -> {
    System.out.println("Lam viec");
};
task.run();
~~~

The `println` call inside ends with `;`; the `;` after `}` terminates the **statement assigning the lambda to `task`**. Do not conclude that "every `{ }` block needs a trailing `;`."

### 8.3. `switch` expression in Java 17

~~~java
int day = 2;
String label = switch (day) {
    case 1 -> "Mon";
    case 2 -> "Tue";
    default -> "Other";
};
System.out.println(label);
~~~

Output: `Tue`. Here the `;` after `}` terminates the **declaration of variable `label`** using a `switch` expression. When a `case` branch has multiple statements, it can use a block and `yield` to produce a value for the switch expression:

~~~java
int n = 4;
String category = switch (n) {
    case 4 -> {
        System.out.println("Dang xet so 4");
        yield "Chan";
    }
    default -> "Khac";
};
~~~

This is supported syntax in Java 17; `yield "Chan";` produces a value for the switch expression, which is not the same as `return` exiting the method.

**In short:** identify whether `{ }` closes a **statement block, declaration body, or initializer** before deciding whether to place a `;`.

## 9. Syntax Errors: Read the Error in Context Instead of Guessing

| Message/symptom | Likely cause | Appropriate fix |
| --- | --- | --- |
| `';' expected` | Missing `;` after a variable declaration or expression statement | Identify where the statement should end |
| `reached end of file while parsing` | Missing `}` or an unclosed syntactic construct | Match pairs of `{ }` and `( )` |
| `'else' without 'if'` | A statement or `;` altered the branch structure | Check `;` after `if` and check blocks |
| `variable ... is already defined` | Redeclaring a local variable with the same name in overlapping scope | Rename or adjust scope as intended |
| `cannot find symbol` for a variable from an earlier block | Variable is outside the visible scope | Declare in an appropriate scope, pass as parameter, or return result |
| `variable ... might not have been initialized` | There is a path to the read site without definite assignment | Ensure assignment before use on all required paths |
| `while` loop never stops | Accidentally wrote `while (condition);` with an empty body | Remove the misplaced `;` and check update conditions |
| `if` always "prints" even when condition is false | There is a `;` after `if (...)`, making the following block independent | Write `if (condition) { ... }` properly |

**Important point:** compiler messages can point to a line **after** the misplaced `{`, `}`, or `;`, because the parser only detects the contradiction at the next token. When you see an error, inspect a few preceding lines as well.

## 10. Formatting Habits That Prevent Bugs

- Each `{`/`}` pair should be indented consistently; align closing braces with the block level.
- Prefer using `{ }` for `if`/`else`/`for`/`while` bodies even when Java grammar permits a single statement without braces. This lowers the risk when adding statements later.
- Do not put `;` right after the condition of `if (...)`, `for (...)`, or `while (...)` when you intend to run a block.
- For `do { ... } while (...);`, do not forget the trailing `;`.
- Do not just count braces in **plain text**: `{`, `}`, and `;` inside **strings** or **comments** do not become control syntax.

Example:

~~~java
String text = "{ ; }"; // Characters inside a string do not create a block.
System.out.println(text); // Prints literally: { ; }
~~~

Do not try to fix errors by deleting every semicolon after a closing brace `}`, because variable declarations with arrays, lambdas, or switch expressions **need** that semicolon to terminate the statement.

## 11. Self-Practice Exercises

**Exercise 1 — Predict the main program output.** With `limit = 6`, on which iterations does `total += number;` actually run? Try changing `limit` to 5 and predict the sum; then recompile to verify.

**Exercise 2 — Spot the misplaced punctuation.** Inside a `main` method, how many lines does the snippet below print and why?

~~~java
boolean pass = false;
if (pass);
{
    System.out.println("PASS");
}
~~~

*Guidance:* One line `PASS`. `if (pass)` governs an empty statement; the separate block still runs.

**Exercise 3 — Scope.** Does the following snippet compile? If not, fix it so the value can be printed:

~~~java
{
    int count = 3;
}
System.out.println(count);
~~~

*Guidance:* No. `count` is declared in a block that has already ended; `count` can be declared in the outer scope if it needs to be used afterward.

**Exercise 4 — Fill in separators.** Write a `for` loop that prints 1, 2, 3. Point out the two `;` separators in the header and the `;` terminating the `println` call inside.

**Exercise 5 — Compare two `while` forms.** Write a `while` loop and a `do...while` loop with an initial condition of `false`, and observe how many times the loop body executes and where semicolons appear.

**Exercise 6 — Identify kinds of `{ }`.** In `int[] a = {1, 2};`, `if (ok) { work(); }`, and `Runnable r = () -> { work(); };`, what kind is each pair of curly braces? Which construct does each outermost `;` terminate?

## 12. Lesson Self-Check

You understand the topic if you can accurately explain:

1. Where a **block** starts and ends, and why indentation does not determine structure.
2. Which `;` terminates a statement and which separates the three parts of `for`.
3. Why `if (condition); { ... }` is dangerous even though it is usually not a compile error.
4. Why `do...while` needs a trailing `;` while `while (...) { ... }` does not.
5. When a local variable is out of scope, and why it can also fail *definite assignment*.
6. Why `int[] values = {2, 4};` or `String s = switch (...) { ... };` needs a trailing semicolon even right after `}`.

**Key takeaway:** In Java, **`{ }` are structural boundaries**, whereas **`;` is a syntactic token** used to terminate or separate depending on the statement form. Look at the **kind of construct being written**, not just where lines break.
