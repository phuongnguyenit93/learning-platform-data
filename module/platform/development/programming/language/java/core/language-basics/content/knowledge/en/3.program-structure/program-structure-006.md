# Expression Statements and Empty Statements in Java

> **Java core — language-basics / Program Structure**  
> **Environment:** JDK 17 or later, no external libraries required.  
> **Learning outcomes:** Recognize expression statements and empty statements, distinguish valid vs. invalid standalone expressions, accurately read the effect of `;`, predict behavior when an empty statement appears in `if` or a loop, and run a complete Java example yourself.

## 1. Expressions, Statements, and Semicolons

An **expression** is a construct evaluated to produce a value or a `void` result, sometimes with side effects. For example, `2 + 3` produces the value `5`; `number++` both produces a value and modifies `number`; `System.out.println("Hi")` has the effect of printing a line.

A **statement** is a unit of action or control permitted by Java at a specific position. An **expression statement** has the form of an allowed **statement expression**, terminated by `;`.

~~~java
int number = 1;             // Local variable declaration: not an expression statement.
number = number + 2;        // Expression statement: assignment.
number++;                   // Expression statement: post-increment.
System.out.println(number); // Expression statement: method invocation.
~~~

The printed result is `4`. Key point: **not every expression is allowed to be written as a statement simply by adding `;`**.

| Concept | Example | Note |
| --- | --- | --- |
| Value-producing expression | `number + 2` | Evaluates to a value, but is not a kind allowed to stand alone as a statement |
| Expression statement | `number += 2;` | Syntactically valid because it belongs to the assignment category |
| Local variable declaration | `int number = 1;` | Declaration statement, not an expression statement |
| Empty statement | `;` | Complete statement with no action inside |
| Empty block | `{}` | A block containing zero statements; **syntactically different** from `;` |

## 2. Valid Expression Statements

Java 17 defines the following categories of statement expressions:

| Category | Example in an appropriate context | Effect |
| --- | --- | --- |
| Assignment | `x = 10;`, `x += 2;` | Assigns/modifies the state of a variable, field, or element |
| Pre-increment, pre-decrement | `++x;`, `--x;` | Modifies the value; expression produces the updated value |
| Post-increment, post-decrement | `x++;`, `x--;` | Modifies the value; expression produces the value before update |
| Method invocation | `System.out.println(x);`, `Math.abs(-5);` | Calls the method, optionally ignoring any return value |
| Object creation with `new` | `new StringBuilder("abc");` | Creates an object, optionally without keeping a reference |

Points to note:

- `Math.abs(-5);` is a valid statement, but it **does not print 5**. The result is computed and discarded. To see it, use `System.out.println(Math.abs(-5));`.
- `new StringBuilder("abc");` is valid, though when you do not keep or use the object, the statement usually serves no clear purpose.
- `x++;` and `++x;` both increment `x` by one when standing alone; their expression values differ **when used inside a larger expression**.
- A method call does not always produce side effects, whereas an assignment or increment/decrement normally alters state. Do not define an expression statement simply as "a command with side effects."

**Clear boundary:** `new int[3];` is an **array creation expression**, not part of the *class instance creation expression* category allowed to stand alone as an expression statement. You must assign the array to a variable or use it in an appropriate expression context.

## 3. Complete Sample Program on Java 17+

Save the code under the name **StatementKindsDemo.java**:

~~~java
public final class StatementKindsDemo {
    private static int calls = 0;

    private static void mark() {
        calls++;  // Post-increment expression statement.
    }

    public static void main(String[] args) {
        int number = 1;               // Variable declaration.
        number = number + 2;          // Assignment.
        number++;                     // Post-increment.
        mark();                       // Method call.
        new StringBuilder("unused");  // Create object, discard reference.
        ;                             // Empty statement.

        int checks = 0;
        while (++checks < 3) {
            // This is an empty block, not a standalone ;.
        }

        System.out.println("number = " + number);
        System.out.println("calls = " + calls);
        System.out.println("checks = " + checks);

        boolean enabled = false;
        if (enabled)
            ;  // Only the empty statement belongs to the if branch.

        {  // This block is independent of if, because if has already ended.
            System.out.println("Khoi doc lap van chay");
        }
    }
}
~~~

Open a terminal in the directory containing `StatementKindsDemo.java` and run:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StatementKindsDemo.java
java StatementKindsDemo
~~~

The two `-version` commands check the environment; the output of the program itself after `java StatementKindsDemo` is:

~~~text
number = 4
calls = 1
checks = 3
Khoi doc lap van chay
~~~

**Why those numbers?** `number` changes from 1 to 3 via assignment, then to 4 via `number++`. `mark()` increments `calls` once. With the condition `++checks < 3`, the values compared in order are 1, 2, 3; the first two are true, the third is false, and `checks` ends up equal to **3**. The standalone `new StringBuilder(...)` and `;` statements print nothing.

`enabled` is `false`, so the empty statement acting as the `if` body does not run. However, the following `{ ... }` block **is not inside `if`**, so the program still prints the last line.

~~~mermaid
flowchart TD
    A["main starts"] --> B["Assign / increment / call mark / create object"]
    B --> C["Empty statement: ;"]
    C --> D["while: check ++checks < 3"]
    D --> E["Print number, calls, checks"]
    E --> F{"enabled?"}
    F -->|"true"| G["Execute empty ;"]
    F -->|"false"| H["Skip empty ;"]
    G --> I["Independent block: print final line"]
    H --> I
~~~

## 4. Which Expressions Cannot Stand Alone?

The following lines are **commented out because they are intentionally invalid**. Do not uncomment them and expect compilation to succeed:

~~~java
int x = 5;

// x + 1;               // Error: plain addition is not a statement expression.
// x > 0;               // Error: plain comparison.
// "Hello";             // Error: standalone literal.
// (x == 0) ? 1 : 2;    // Error: standalone conditional expression.
// new int[3];          // Error: standalone array creation.
~~~

With the compiler, invalid forms are typically reported as `not a statement` or a related syntax error. The issue is not a missing `;`; these lines **already have `;` yet still do not belong to the forms Java allows**.

To fix them, **use the value** in a meaningful operation:

~~~java
int x = 5;
int next = x + 1;
boolean positive = x > 0;

System.out.println(next);
System.out.println(positive);
System.out.println(x == 0 ? "Bang 0" : "Khac 0");
~~~

Output:

~~~text
6
true
Khac 0
~~~

`int next = x + 1;` is a **local variable declaration with an initializer expression**; `System.out.println(...)` is a **method invocation expression statement**. The conditional expression `?:` is placed **inside an argument** of a valid call rather than written as a standalone statement.

## 5. Empty Statement: When the Entire Statement Is Just `;`

Syntactically, an **empty statement** consists solely of a semicolon:

~~~java
;
~~~

It does not modify values, call methods, or print anything on its own. Yet it is still **a valid statement** anywhere Java accepts a statement.

~~~java
int total = 0;
;        // First empty statement.
;        // Second empty statement.
total++; // Expression statement: increments total.
System.out.println(total); // 1.
~~~

**Three constructs often confused with each other:**

| Syntax | Nature |
| --- | --- |
| `;` | An empty statement |
| `{}` | An empty block, containing 0 statements |
| `int total = 0;` | A local variable declaration statement terminated by `;` |

A `;` that terminates a declaration **does not simultaneously create an extra empty statement**. Similarly, `;` characters separating parts inside a `for` header have their own syntactic role.

## 6. Empty Statement vs. Empty Block: Same Behavior, Different Syntax

Both `;` and `{}` can express **no work to do**, but they are **two different kinds of statements**. For an `if` branch, Java can accept an empty statement as the body:

~~~java
boolean allowed = false;
if (allowed)
    ;
else
    System.out.println("Bi tu choi");
~~~

In code **inside a method**, the output is `Bi tu choi`. The `;` is the entire `if` branch body, and `else` still belongs to that same `if`. Writing an empty block can express the intent more clearly:

~~~java
if (allowed) {
    // Nothing to do yet when allowed.
} else {
    System.out.println("Bi tu choi");
}
~~~

The two snippets behave the same for the value of `allowed` shown above, but the block helps readers see branch boundaries and makes it easier to add statements later. An **accidental** `;` between `if (allowed)` and a block containing `println` makes that block independent so it runs regardless of the condition; that is a logic bug that can still compile cleanly.

In real code, you should normally revise missing intent into a clear condition and meaningful block rather than keeping confusing empty branches. The next section examines empty statements inside **loops**, where they also affect how many times the condition is evaluated.


## 7. Empty Statements Inside Loops

### `while` with an empty statement

~~~java
int attempts = 0;
while (++attempts < 3)
    ;
System.out.println(attempts); // 3
~~~

The condition increments `attempts` itself. It is checked with 1, 2, and 3 in turn, stopping at 3. In this example, the `while` body is just `;`.

By contrast, uncommenting the following form risks an infinite loop:

~~~java
// int attempts = 0;
// while (attempts < 3);
// The condition does not modify attempts, and the loop body does not update it either.
~~~

Do not use an empty **busy-wait** loop to wait for an event in real programs: besides the risk of never terminating, it can burn CPU and cause issues with communication across threads.

### `for`: two separators in the header are not empty statements

~~~java
int seen = 0;
for (int i = 0; i < 3; i++)
    ;
seen++;
System.out.println(seen); // 1
~~~

In `for (int i = 0; i < 3; i++)`, the two `;` characters split the three **initialization / condition / update** parts. Only the `;` **after `)`** is the empty statement serving as the loop body. `seen++` sits **after** the loop, so it executes only once.

To increment `seen` on every iteration:

~~~java
int seen = 0;
for (int i = 0; i < 3; i++) {
    seen++;
}
System.out.println(seen); // 3
~~~

`for (;;) ;` is syntactically valid: two `;` characters in the header, and the final one is an empty body. However, **there is no termination condition or `break`**, making it an infinite loop; **do not run it to test**.

### `do...while`: the trailing semicolon is required

~~~java
int count = 0;
do {
    count++;
} while (count < 2);
System.out.println(count); // 2
~~~

The `;` after `while (count < 2)` is a **mandatory part of `do-while` syntax**, not an extra empty statement. The form `do ; while (false);` is also valid: the first `;` is the empty body, and the second terminates the `do-while` statement.

## 8. When Expression Statements Appear in `for`

In the update section of `for`, Java allows a **comma-separated list of statement expressions**:

~~~java
int sum = 0;
for (int i = 1; i <= 3; i++, sum += i) {
    // Empty block.
}
System.out.println(sum); // 9
~~~

**Why 9 instead of 6?** After each iteration, Java evaluates `i++` **before** `sum += i`, so `sum` adds 2, 3, and 4 in turn. The total is 9. Reversing the order to `sum += i, i++` gives 6.

Note: the comma here is part of the expression-list syntax in `for`; Java **does not** have a general-purpose "comma expression" operator usable freely as in some other languages.

With `for (int i = 0; i < 3; i++);`, the trailing `;` (outside the parentheses) can cause the loop to run with no body unintentionally.

## 9. A Method's Return Value Can Be Ignored

An expression statement does not have to print a message or update a variable. For example:

~~~java
String label = "java";
label.toUpperCase();
System.out.println(label);
~~~

Output:

~~~text
java
~~~

`String` is immutable. The `toUpperCase()` method returns a new string; calling it without using the result leaves `label` holding `"java"`. If you want to save it:

~~~java
label = label.toUpperCase();
System.out.println(label); // JAVA
~~~

This explains why **Java permits** a method invocation statement even when **ignoring the return value** is sometimes a logic bug. Conversely, calling `System.out.println(...)` is useful specifically because of its side effect of printing to stdout.

## 10. Errors and What to Check

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `not a statement` | Standalone expression not in the statement expression category | Use the result in an assignment, declaration, or call |
| `';' expected` | Missing terminator on a statement/declaration that requires `;` | Check the syntactic form being written |
| `if` prints content even when condition is false | `;` placed after `if (...)`; following block is independent | Remove the wrong `;` and use `if (...) { ... }` |
| `while` or `for` never finishes | Empty body and condition never progresses toward false | Add an appropriate update or termination condition |
| Loop runs three times but variable increments only once | Increment sits **after** the loop, not in the body | Move the increment into the loop's block |
| Calling `toUpperCase()` leaves the string unchanged | Return value was discarded | Reassign or use the returned value |
| Object created but never used | `new SomeClass();` has its result ignored | Consider saving the reference or removing the statement |

There are logic bugs the **compiler does not necessarily warn about**: in particular, `if (condition);` can be completely valid. IDEs and linters can help detect them, but they do not replace reading the code to determine **which statements are actually inside a branch or loop**.

### Three diagnostic questions for `;`

1. Is this `;` **terminating** an expression/declaration statement?
2. Is this `;` **separating** parts inside `for (...)` or terminating `do...while` syntax?
3. Is this `;` **forming an empty statement on its own**, potentially breaking the structure of an `if` or loop?

## 11. Practice Exercises

**Exercise 1 — Classify.** Assume `int x = 1;` is already declared. Classify `x += 3;`, `x > 0;`, `x++;`, `;`, `new Object();`, `"hello";`, and `System.out.println(x);` as an expression statement, an empty statement, or invalid.

*Guided answer:* `x > 0;` and `"hello";` are invalid. `;` is an empty statement. The remaining cases are expression statements.

**Exercise 2 — Predict output.** When `boolean ready = false; if (ready); { System.out.println("OK"); }` runs inside a method, does it print `OK`? Why?

*Answer:* Yes; `if` only governs the empty statement, so the next block is independent.

**Exercise 3 — Condition update.** With `int n = 0; while (++n < 5) ;`, what is `n` after the loop? How does changing `++n` to `n++` change the comparison behavior?

*Guidance:* With `++n`, the final `n` is 5. With `n++`, the comparison uses the pre-increment value, and the final `n` is 6.

**Exercise 4 — Fix an invalid statement.** Turn `int x = 4; x * 2;` into one version that prints `8` and one version that stores the result in a variable `doubleX`.

**Exercise 5 — Test runnable source.** In `StatementKindsDemo`, replace `if (enabled) ;` and the independent block with `if (enabled) { ... }`. Run with `enabled` set to false and true in turn, comparing the number of output lines.

**Exercise 6 — Side-effect order.** Replace `i++, sum += i` in the `for` header with `sum += i, i++`, and explain why the sum changes from 9 to 6.

## 12. Self-Assessment

You have mastered this lesson if you no longer confuse:

- **`x++;`** — valid expression statement;
- **`x + 1;`** — not a valid statement;
- **`;`** — empty statement;
- **`{ }`** — empty block, **not identical** to an empty statement;
- **`if (condition); { ... }`** — block after `if` runs independently;
- **`for (a; b; c)`** — two `;` split the three header parts, not two empty statements.

**Conclusion:** Java only allows certain kinds of expressions to stand alone as statements. A `;` can **terminate** a statement, **separate** header parts, or **be an empty statement itself**. Determine its role from the **surrounding grammar**, not from line breaks.
