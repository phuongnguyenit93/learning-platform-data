# Declarations vs. Executable Statements in Java

In a Java file, some lines **introduce structure or names** to the compiler, and some lines **perform actions when the program runs**. Distinguishing these two roles helps explain why a method you wrote prints nothing yet, or why a variable declaration with `=` causes an effect when the program executes.

Example:

~~~java
int score;                  // Local variable declaration.
score = 8;                  // Assign a value when the statement is executed.
System.out.println(score); // Execute a method call: prints 8.
~~~

The three lines above must be placed **inside a method, constructor, or appropriate block**. Declaring `score` defines a name and type; the assignment sets the value; `println` outputs the data.

A key point from the start: **"declaration" and "statement" are not always mutually exclusive syntactic categories**. `int score = 8;` is both a *local variable declaration statement* in Java grammar and contains the initializer expression `8`, which is evaluated when execution reaches this line.

## 1. Looking at a Java File: Which Parts Declare, Which Parts Run?

Look at this condensed program:

~~~java
public class Example {
    static int limit = 10;           // Field declaration with initializer.

    static void greet() {            // Method declaration.
        System.out.println("Hello"); // Statement inside the body.
    }

    public static void main(String[] args) {
        int count = 2;               // Local variable declaration with initializer.
        if (count > 0) {             // Branching statement.
            greet();                 // Method invocation statement.
        }
    }
}
~~~

When running `Example`, the compiler already knows about class `Example` and method `greet`. However, the body of `greet` runs only because `main` **calls** `greet()`.

| Construct | Primary role | Automatically prints/runs its body just from being declared? |
| --- | --- | --- |
| `class Example { ... }` | Type/class declaration | No; class initialization code is a separate matter |
| `static void greet() { ... }` | Declares a method and a callable body | No; requires a call or appropriate mechanism to trigger it |
| `int count;` inside a method | Local variable declaration | No initializer expression to evaluate at that line |
| `int count = calculate();` | Local variable declaration **with initializer** | Yes; `calculate()` is called when execution reaches the line |
| `count = 5;` | Assignment expression statement | Yes; assigns the value when reached |
| `System.out.println(count);` | Method invocation statement | Yes; calls the method when reached |
| `if`, `for`, `while` | Control-flow statements | Yes; evaluates the condition and decides which code runs |
| `import java.util.List;` | Imports a type name into the source file | Does not load data or call `List` on its own |

In Java 17, you cannot arbitrarily place standalone statements such as `System.out.println(...)` directly at class-body level. Ordinary statements belong inside a method body, constructor, or valid **initializer block**.

## 2. Complete Program: Observing Execution Order

Create the file **`DeclarationDemo.java`** with this exact name:

~~~java
public class DeclarationDemo {
    // Static field declaration, with initializer expression.
    static int classValue = trace("1. static field", 10);

    static {
        System.out.println("2. static initializer");
    }

    // Instance field declaration, initialized when creating an object.
    int objectValue = trace("5. instance field", 20);

    {
        System.out.println("6. instance initializer");
    }

    DeclarationDemo() {
        System.out.println("7. constructor");
    }

    // Simply declaring a method does not make it run automatically.
    static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    void greet() {
        System.out.println("8. greet method");
    }

    static void neverCalled() {
        System.out.println("KHONG DUOC IN");
    }

    public static void main(String[] args) {
        System.out.println("3. main begins");

        int count; // Local variable declared without a value yet.
        count = 2; // Assignment executes here.
        System.out.println("4. count=" + count);

        DeclarationDemo demo = new DeclarationDemo();
        demo.greet();
    }
}
~~~

**Run commands on Windows PowerShell or Linux/Bash** (terminal in the directory containing the file):

~~~bash
javac -encoding UTF-8 DeclarationDemo.java
java DeclarationDemo
~~~

Expected output:

~~~text
1. static field
2. static initializer
3. main begins
4. count=2
5. instance field
6. instance initializer
7. constructor
8. greet method
~~~

There is no `KHONG DUOC IN` line because the `neverCalled` method **is declared but never called**.

### Analyzing the print order

1. Before calling `main`, the JVM initializes class `DeclarationDemo`. The static field initializer for `classValue` calls `trace` and prints line 1.
2. The `static { ... }` block runs next, printing line 2. Static initializers are processed in **textual order** within the class.
3. The launcher calls `main`; line 3 is printed.
4. The declaration `int count;` **does not assign a value yet**. The line `count = 2;` assigns 2, and then line 4 is printed.
5. The expression `new DeclarationDemo()` creates a new object. The instance field initializer calls `trace` and prints line 5.
6. The instance initializer block prints line 6, and then the constructor body prints line 7.
7. The call `demo.greet()` executes the `greet` method and prints line 8.

**Scope limitation of the example:** the order above applies to a class directly extending `Object` like `DeclarationDemo`. With subclasses, superclass initialization steps also occur; do not overgeneralize the order above as a complete description of every class hierarchy.

You can run the source directly with JDK 17+:

~~~bash
java DeclarationDemo.java
~~~

The output is the same. In source-file execution mode, the launcher compiles in memory; if you run `javac` first, `DeclarationDemo.class` is written to disk. Both ways of running are suitable for testing this lesson.

## 3. Variable Declarations With or Without an Initializer Expression

Compare:

~~~java
int a;              // Local variable declaration, no value to read yet.
a = 5;              // Assign a value.
int b = a * 2;      // Declaration + evaluation of initializer expression.
System.out.println(b); // Prints 10.
~~~

A helpful way to read this:

- `int a;`: "From here on, the name `a` of type `int` exists within the appropriate scope."
- `a = 5;`: "Set the value of `a` to 5."
- `int b = a * 2;`: "Create the name `b` of type `int`, **compute `a * 2` when execution reaches this line**, and assign the result."
- `println`: "Call a method that outputs data."

The statement `int b = a * 2;` is not "pre-run" by the compiler to compute a fixed result in all situations. If `a` changes before reaching this line, the initialization result of `b` changes accordingly.

### Declaring a variable does not mean it is ready to be read

The snippet below **does not compile**:

~~~java
public class UnassignedLocal {
    public static void main(String[] args) {
        int amount;
        // System.out.println(amount); // Uncommenting this causes an error.
        amount = 10;
        System.out.println(amount);
    }
}
~~~

Java enforces **definite assignment**: a local variable must be definitely assigned before it is read. Having a variable declaration **does not automatically assign 0 by default** to a local variable. By contrast, an explicitly uninitialized `int` field receives the default value 0 when the object/class is initialized according to Java rules.

### Expressions in declarations can have side effects

~~~java
static int nextValue() {
    System.out.println("Tinh gia tri");
    return 7;
}

// Place the following statements inside a method:
int first = nextValue();  // Prints "Tinh gia tri" when execution reaches here.
int second = 9;           // Assigns a value, prints nothing on its own.
~~~

The call `nextValue()` is an **expression** inside the variable declaration; when execution reaches the initialization line, the expression is evaluated, including its side effects. Therefore, do not conclude that "a line starting with `int` is just a declaration so it executes nothing."

## 4. A Declared Method Is Not Automatically Called

Example:

~~~java
public class MethodDeclaration {
    static void sayHello() {
        System.out.println("Xin chao");
    }

    public static void main(String[] args) {
        System.out.println("Bat dau");
        // sayHello();
        System.out.println("Ket thuc");
    }
}
~~~

Run:

~~~bash
javac MethodDeclaration.java
java MethodDeclaration
~~~

Output:

~~~text
Bat dau
Ket thuc
~~~

If you uncomment `sayHello();`, the `Xin chao` line appears **between** the two lines above. In Java, a **method name + signature + body** defines what it will do *when called*, not to call itself during compilation.

This is also why you can write many helper methods in a class even when only some helpers are used in a specific run.

## 5. Where Declarations Are Allowed vs. Where Execution Happens

| Location in a Java file/class | What can it contain? | Note |
| --- | --- | --- |
| Source-file level | `package`, `import`, and top-level type declarations | Do not place arbitrary `System.out.println(...)` directly here |
| Class body | Fields, constructors, methods, nested types, initializer blocks | Do not place standalone assignment statements or method calls outside blocks |
| Method body | Local variable declaration statements, expression statements, `if`, `for`, `return`, etc. | Executes according to control flow |
| Constructor | Statements and valid local declarations | Runs when creating an object, during initialization sequence |
| `static { ... }` block | Class initialization statements | Runs when the class is initialized, not per object creation |
| `{ ... }` block in class body | Instance initialization statements | Runs when creating each instance in the appropriate sequence |

**Typical placement error:**

~~~java
public class WrongPlacement {
    // System.out.println("Hello"); // Invalid if // is removed:
    // a method call statement cannot stand alone directly in a class body.

    public static void main(String[] args) {
        System.out.println("Hello"); // Valid: inside a method.
    }
}
~~~

Do not confuse the `{}` of a class declaration with a method block. Not every statement valid inside `main` is allowed to be moved directly to class level.

## 6. An Expression Is Not Necessarily a Valid Statement

In Java, forms such as assignments, increments/decrements, method calls, and object creation can appear as an **expression statement**:

~~~java
int n = 2;
n = n + 1;
n++;
System.out.println(n); // 4
new StringBuilder("text");
~~~

The line `new StringBuilder("text");` creates an object and discards the reference; it is syntactically valid even though it has little practical use. Conversely, not every expression that computes a value can stand alone as a statement:

~~~java
// n + 1; // Invalid: not a valid statement expression.
~~~

As a beginner, a helpful question to ask is: "What does this line **declare**, what does it **compute/assign**, what does it **call**, or how does it **control flow**?" That is far more accurate than just looking for `;` and concluding all lines behave the same.

## 7. Common Mistakes and How to Distinguish Them

| Code/situation | Result | Explanation |
| --- | --- | --- |
| `int n; System.out.println(n);` inside a method | Compile error | Local variable has not been definitely assigned |
| Declaring `void work()` without calling it | Nothing printed from the method body | Method is only defined, not executed |
| `int n = read();` | Calls `read()` when reaching the line | The initializer is an executed expression |
| Placing `System.out.println("Hi");` directly in the class body | Compile error | Not a valid member declaration or initializer block |
| `static int x = trace(...);` | Can produce output during class initialization | Field initializer is evaluated in the initialization sequence |
| `int n = 2;` inside an unchosen `if` branch | That initializer does not run | Execution flow did not enter the branch |
| `n + 1;` standing alone | Compile error | Not a valid expression statement |

**The question "when does it run?" depends on location and control flow.** A method body does not run just by existing in source code; a field initializer can run during object/class initialization; a local initializer only runs when execution reaches it.

## 8. Self-Check Exercises

**Exercise 1 — Predict the output.** What does the following print?

~~~java
public class OrderDemo {
    static void later() {
        System.out.println("B");
    }

    public static void main(String[] args) {
        System.out.println("A");
        later();
        System.out.println("C");
    }
}
~~~

*Answer:* `A`, `B`, `C` on three lines. The body of `later` runs at the call site between the two print statements.

**Exercise 2 — Spot the error.** Given:

~~~java
public class ScopeDemo {
    public static void main(String[] args) {
        int score;
        // System.out.println(score);
    }
}
~~~

Why does removing `//` before `println` cause `javac` to report an error? Fix it by assigning `score = 10;` before the call. After fixing, predict the printed value.

*Answer:* The local variable is not definitely assigned; after assigning, it prints `10`.

**Exercise 3 — One line that both declares and executes.**

~~~java
int value = Integer.parseInt("21");
~~~

Which part is the declaration? Which part executes when this line runs? What happens if you change the string to `"hai muoi mot"`?

*Answer:* `int value` declares the name/type. `Integer.parseInt(...)` is called at runtime; an invalid string throws `NumberFormatException`.

**Exercise 4 — Which blocks run?** In `DeclarationDemo`, try removing the `demo.greet();` call. Does print line 8 still appear? Do instance initialization lines 5–7 still appear?

*Answer:* Line 8 no longer appears; lines 5–7 still print because `new DeclarationDemo()` is still executed.

**Exercise 5 — Practice classification.** In the following example, identify: type declaration, method declaration, variable declaration with initializer, assignment, and conditional statement.

~~~java
class Sample {
    static boolean enough(int n) {
        int limit = 5;
        n = n + 1;
        if (n >= limit) {
            return true;
        }
        return false;
    }
}
~~~

*Hint:* `class Sample` is a type declaration; `enough` is a method declaration; `int limit = 5;` both declares a local variable and initializes it; `n = n + 1;` is an assignment; `if` selects a branch.

## Checklist

- [ ] Distinguish class, field, and method declarations from runtime actions.
- [ ] Understand that a local variable declaration **is a form of statement** in Java, and its initializer is evaluated when flow reaches the line.
- [ ] Never read a local variable before it is definitely assigned.
- [ ] Predict the order of static initialization, instance initialization, constructor, `main`, and helper calls through a concrete example.
- [ ] Know that a declared but uncalled method will not print output on its own.
- [ ] Do not place standalone method invocations directly in a class body.
- [ ] Know that not every expression can stand alone as a statement.
- [ ] Run `javac DeclarationDemo.java` and `java DeclarationDemo`, matching all eight output lines.

**Key takeaway:** In Java, **declarations** help the program define names, types, and structure; **execution** evaluates expressions and statements along the runtime flow. A declaration can contain an initializer with runtime effects, so the two concepts are related rather than **completely opposite**. Ask: "What does this line declare, and which part is actually evaluated when the program reaches it?"
