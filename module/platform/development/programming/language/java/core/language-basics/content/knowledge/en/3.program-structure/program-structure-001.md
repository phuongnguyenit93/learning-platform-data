# Source Files, Classes, and Methods in a Minimal Java Program

> **Java core — language-basics / Program Structure**  
> **Practice target:** JDK 17 or later, using traditional Java 17-compatible program syntax.  
> **After this lesson, you can:** create a properly named `.java` file, distinguish a source file from a class and a method, write `main`, compile it yourself with `javac`, run it with `java`, read the output, and recognize common structural errors.

## 1. What Does a Minimal Java Program Contain?

Before learning complex parts, look at a single file named **HelloWorld.java**:

~~~java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, Java 17!");
    }
}
~~~

This is a **complete** program using Java 17 syntax. It has three easily recognizable layers (plus statements inside the method):

| Component | In the example | Role |
| --- | --- | --- |
| **Source file** | `HelloWorld.java` | Text containing Java source code for the compiler to read |
| **Class** | `public class HelloWorld` | Named group declaring data and behavior; this is the class containing the program |
| **Method** | `main(String[] args)` | Named group of statements; in the example, the entry point for execution |
| **Statement** | `System.out.println(...);` | Instruction to perform an action, here printing a line |

Java does not run a "text file" like a note. In the standard workflow, the **compiler compiles** `.java` into `.class` bytecode; the **Java launcher/JVM** loads the class with the entry point and executes the statements inside the `main` method.

~~~mermaid
flowchart LR
    S["HelloWorld.java: source code"] --> C["javac: compile"]
    C --> B["HelloWorld.class: bytecode"]
    B --> J["java: launch class"]
    J --> M["main(): execute statements"]
    M --> O["Console: Hello, Java 17!"]
~~~

**One file does not mean one class in every case.** A `.java` file can declare multiple top-level classes with access and filename restrictions; this introductory example intentionally has only **one `public` class** so learners can focus on the basic structure.

## 2. Creating, Compiling, and Running a File with JDK 17+

### Step 1 — Create the source file

Use a text editor or IDE to create **HelloWorld.java**, paste the exact code from section 1, and save it as UTF-8. Note:

- The name `HelloWorld.java` matches the exact case of `public class HelloWorld`.
- The file is not `HelloWorld.java.txt` (some operating systems hide file extensions).
- Do not include Markdown markers such as `~~~java` in the **file content**: only copy the code between the two code fences.

### Step 2 — Verify the tools

In the terminal, navigate to the directory containing the file and check:

~~~bash
java -version
javac -version
~~~

You need a **JDK** to have the `javac` compiler. JDK versions compatible with Java 17 or newer can be used to practice this lesson; if neither command is found, check your JDK installation and path configuration before proceeding.

### Step 3 — Compile

In the directory containing `HelloWorld.java`:

~~~bash
javac -encoding UTF-8 HelloWorld.java
~~~

If the code is valid, the command normally **prints no success message** and creates `HelloWorld.class` next to the source code (for an example without `package` and without specifying `-d`).

### Step 4 — Run the class

~~~bash
java HelloWorld
~~~

Exact output:

~~~text
Hello, Java 17!
~~~

After `java` comes the **class name** `HelloWorld`, **not** `HelloWorld.class`. The `.class` filename only lets you observe the compiler output; the launcher syntax for running a class uses the class name.

### Alternative: running the source file directly

Since **JDK 11**, the Java launcher supports source-file mode:

~~~bash
java HelloWorld.java
~~~

With this example, the output is still:

~~~text
Hello, Java 17!
~~~

The launcher performs the necessary compilation step and then runs the program; you do not need to invoke `javac` separately. Do not infer that the JVM directly executes source code line by line. The two commands `java HelloWorld` and `java HelloWorld.java` have **different processing modes**: one launches an already compiled class, while the other takes a source file path.

## 3. Reading the Syntax Line by Line

Let's break the example code into layers of meaning:

~~~java
public class HelloWorld {                 // Class declaration
    public static void main(String[] args) {  // Method declaration
        System.out.println("Hello, Java 17!"); // Statement
    }                                       // End of method body
}                                           // End of class body
~~~

### `public class HelloWorld`

- `class`: declares a class.
- `HelloWorld`: class name, case-sensitive.
- `public`: public class; in this top-level public class example, the source filename must be `HelloWorld.java`.
- `{ ... }`: class body. Inside the body you can declare **fields**, **constructors**, **methods**, and other members; this example only needs one method.

### `public static void main(String[] args)`

In the standard entry-point syntax of **Java 17**:

| Component | Meaning in the `main` method |
| --- | --- |
| `public` | The launcher can access the public entry point |
| `static` | Invokes the method through the class; no need to create a `HelloWorld` object first |
| `void` | The method does not return a value |
| `main` | Entry-point method name recognized by the Java launcher |
| `String[] args` | Array of string arguments passed from the command line |
| `{ ... }` | Statements executed when `main` is called |

The variable name `args` can be changed to another name; what matters is a **matching signature/visibility** for how the Java 17 launcher looks up the entry point. The form `String... args` is also equivalent to an array parameter in a Java method declaration, though beginners should start with `String[] args`.

**`main` is not a "special command you can place anywhere."** It is a Java method that must reside inside a class according to the traditional program structure of Java 17. Newer JDKs may support other simplified program forms; do not confuse those features with the Java 17 practice rules of this lesson.

### `System.out.println("...");`

- `System`: standard Java API class.
- `out`: standard output stream for printing results.
- `println(...)`: the method being called; in this example it prints a string and a newline.
- Semicolon `;`: terminates the statement.
- Java strings use double quotes `"..."`; single quotes are normally for a single `char` character.

In Java, **case matters**: `System` is not `system`; `println` is not `printLn`; `HelloWorld` is not `Helloworld`.

## 4. What Is a Class, and What Is a Method?

A **class** describes a kind of object or groups related capabilities. A **method** is a named behavior that can accept parameters, perform work, and return a result. Not every method has to print to the screen.

Illustrative example:

~~~java
class Calculator {
    static int add(int left, int right) {
        return left + right;
    }
}
~~~

- `Calculator` is the class.
- `add` is the method.
- `int left` and `int right` are two input **parameters**.
- `return left + right;` returns a value of type `int`.
- `static` allows calling `Calculator.add(2, 3)` without creating an object.

This snippet is a **component illustration**, not a self-launching program because it does not declare a `main` entry point. To compile and run a complete program, look at the next example.

### Distinguishing closely related terms

| Term | Example | Key point |
| --- | --- | --- |
| Method declaration | `static int add(int a, int b) { ... }` | Defines the name, parameters, return type, and body |
| Method call | `add(2, 3)` | Requests execution of the method with concrete arguments |
| Parameter | `a`, `b` in the declaration | Local variable receiving data when the method is called |
| Argument | `2`, `3` at the call site | Value passed into the method |
| Return type | `int` or `void` | Whether a value of that type is returned |
| `static` method | `Calculator.add(2, 3)` | Associated with the class, no object required |
| Instance method | `lamp.turnOn()` | Called through a specific object |

Do not confuse `return` with `System.out.println`: `return` sends a value **back to the caller**, whereas `println` produces **console output**. You can compute and return a result without printing anything.

## 5. Runnable Example: One Class Containing Multiple Methods

Create the file **MethodDemo.java**:

~~~java
public class MethodDemo {

    private static String makeGreeting(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, guest!";
        }
        return "Hello, " + name.strip() + "!";
    }

    private static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static void main(String[] args) {
        String guest = args.length == 0 ? "friend" : args[0];

        String greeting = makeGreeting(guest);
        int total = add(7, 5);

        System.out.println(greeting);
        System.out.println("7 + 5 = " + total);
        System.out.println("Argument count: " + args.length);
    }
}
~~~

Compile and run with no arguments:

~~~bash
javac -encoding UTF-8 MethodDemo.java
java MethodDemo
~~~

Output:

~~~text
Hello, friend!
7 + 5 = 12
Argument count: 0
~~~

Run with an argument containing a space (in Bash or PowerShell):

~~~bash
java MethodDemo "Lan Anh"
~~~

Output:

~~~text
Hello, Lan Anh!
7 + 5 = 12
Argument count: 1
~~~

**Execution flow:**

1. The launcher calls `main`.
2. `main` checks whether there are command-line arguments. If not, it uses the default string `"friend"`.
3. `main` calls `makeGreeting(guest)`. This method checks the name and **returns a string**, rather than printing.
4. `main` calls `add(7, 5)`. The method computes and **returns 12**.
5. Only `main` calls `println` to print three lines to the console.

`private` on the two helper methods means only code inside `MethodDemo` itself can call them directly. Both are `static` so `main` (which is also `static`) can call them without creating a `MethodDemo` instance.

### What happens with special arguments?

| Command | Notable result | Why |
| --- | --- | --- |
| `java MethodDemo` | `Hello, friend!` | `args.length == 0` |
| `java MethodDemo "Lan Anh"` | `Hello, Lan Anh!` | One argument with a space thanks to quotes |
| `java MethodDemo ""` | `Hello, guest!` | `args[0]` is an empty string; `isBlank()` is true |
| `java MethodDemo An Binh` | Greets `An`; argument count is 2 | The shell splits it into two arguments; the example only uses `args[0]` |

This lesson only treats the **first** argument as the name; that is the contract of this example, not because Java automatically discards all other arguments. Always check `args.length` before accessing `args[0]` to avoid `ArrayIndexOutOfBoundsException`.

### Why use `Math.addExact`?

In the example, `7 + 5` does not overflow. However, ordinary `int` addition can overflow the numeric range silently without warning. `Math.addExact(left, right)` throws `ArithmeticException` on overflow. Choosing this method illustrates that **method behavior** is not just a calculation: it can also have an error contract. In real programs, edge cases should be tested when data comes from users.

## 6. `static` Methods and Instance Methods

In `MethodDemo`, all methods are `static`. A class can also create objects carrying their own state and have **non-static** methods. Create **LampDemo.java**:

~~~java
public class LampDemo {
    private boolean on;

    public void turnOn() {
        on = true;
    }

    public String status() {
        return on ? "ON" : "OFF";
    }

    public static void main(String[] args) {
        LampDemo lamp = new LampDemo();

        System.out.println(lamp.status());
        lamp.turnOn();
        System.out.println(lamp.status());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LampDemo.java
java LampDemo
~~~

Output:

~~~text
OFF
ON
~~~

- `LampDemo lamp = new LampDemo();` creates an **object**.
- `lamp.status()` and `lamp.turnOn()` are **instance** method calls through the `lamp` object.
- `on` is an object **field**, with a default value of `false` for type `boolean` when the object is created.
- `main` is `static` so the launcher can start it; inside `main`, we actively create an object to call the non-static methods.
- `turnOn()` has return type `void`: it changes the state of `lamp` and does not return a value.

**Common mistake:**

~~~java
// Inside a static method of LampDemo, the following statement is invalid:
turnOn(); // No object is specified to call the instance method.
~~~

In the example's `main`, you must have an appropriate object and then call `lamp.turnOn()`. This is the fundamental difference between **class behavior** and **behavior on an object**, not a reason to make every method `static`.

## 7. How Many Classes Can a Source File Contain?

A source file can have multiple **top-level classes**, but normally it may have **at most one top-level public class**. If there is a top-level public class, the filename must match that class's name.

Example saved in **MainWithHelper.java**:

~~~java
public class MainWithHelper {
    public static void main(String[] args) {
        Helper.sayHello();
    }
}

class Helper {
    static void sayHello() {
        System.out.println("Helper ran!");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MainWithHelper.java
java MainWithHelper
~~~

Output:

~~~text
Helper ran!
~~~

The compiler normally produces **`MainWithHelper.class`** and **`Helper.class`**. Both classes reside in **one source file** because `Helper` is not a top-level public class. However, as a project grows, it is usually better to separate classes with distinct responsibilities into appropriate files so they are easier to find, test, and maintain; this is a **helpful organizational convention**, not a rule that "every Java file may only contain one class."

If you create two **top-level public classes** with different names in the same `MainWithHelper.java`, the compiler will report an error about the public class filename requirement. Do not confuse this with **nested classes**, which are a different syntactic case.

## 8. With a `package`, the Class Name Used to Run Changes

The earlier examples omit `package` to keep the first steps brief. In a real project, classes are typically placed in a named package, such as `demo`.

Minimal project tree:

~~~text
project/
└── src/
    └── demo/
        └── PackageHello.java
~~~

Contents of `src/demo/PackageHello.java`:

~~~java
package demo;

public class PackageHello {
    public static void main(String[] args) {
        System.out.println("Hello from package demo!");
    }
}
~~~

From the `project` directory, compile and run:

**Bash (macOS/Linux):**

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/demo/PackageHello.java
java -cp out demo.PackageHello
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac -encoding UTF-8 -d out src/demo/PackageHello.java
java -cp out demo.PackageHello
~~~

Output:

~~~text
Hello from package demo!
~~~

The compiler creates `out/demo/PackageHello.class`. When running, you pass the **fully qualified class name** `demo.PackageHello` and the **classpath root** `out`. Do not run `java PackageHello` here because the class actually belongs to package `demo`.

**This is a supplementary example to explain file/class structure, not a guide to configuring multi-module projects.** You do not need Maven or Gradle to understand a minimal program; those build tools are useful when a project has more files and dependencies.

## 9. Common Errors When Writing Your First Program

| Symptom/error | Possible cause | How to check |
| --- | --- | --- |
| `class HelloWorld is public, should be declared in a file named HelloWorld.java` | Filename does not match the top-level public class | Name it `HelloWorld.java` |
| `cannot find symbol` for `System`, `String`, or a method name | Wrong capitalization or identifier spelling | Double-check `System`, `String`, `println`, and method names |
| `';' expected` | Missing semicolon after a statement that requires `;` | Check lines calling `println` or assigning variables |
| `reached end of file while parsing` | Missing `}` or incomplete syntax | Match opening/closing braces for classes and methods |
| `non-static method ... cannot be referenced from a static context` | Calling an instance method in `main` without an object | Create an object and call `object.method()` |
| `Main method not found in class ...` | No matching Java 17 entry point | Check `public static void main(String[] args)` |
| `Could not find or load main class` | Wrong class/package name or classpath | Check `.class` file, fully qualified name, and `-cp` |
| `ArrayIndexOutOfBoundsException` on `args[0]` | Reading the first element when no arguments were passed | Check `args.length` |
| `java HelloWorld.class` fails | Passing filename instead of class name | Use `java HelloWorld` when running bytecode |

**Compiling and running are two distinct phases.** If `javac` reports a syntax error, the program has not produced valid new bytecode yet. If `javac` succeeds but `java` reports it cannot find the main class, check the **class name and classpath**, not necessarily the printing logic.

### Three quick checks

1. **Filename:** a top-level `public class Example` must be in `Example.java`.
2. **Entry-point signature:** in standard Java 17 structure, use `public static void main(String[] args)`.
3. **Run command:** without a package, `java Example`; with `package demo;` and classpath `out`, `java -cp out demo.Example`.

## 10. Practice Exercises

**Exercise 1 — Change printed output:** In `HelloWorld.java`, change the string to `"I am learning Java!"`, then recompile and run again. Observe why editing only the `.java` file and running the old `.class` file **does not** show the new content unless you recompile.

**Exercise 2 — Write a method returning a result:** In `MethodDemo`, add `private static int square(int number)` returning the square. Call it from `main` with `4`, expecting `16` to be printed. Think about `int` overflow with very large inputs.

**Exercise 3 — Understand arguments:** Run `java MethodDemo "Ngoc Lan"` and `java MethodDemo Ngoc Lan`. Compare `args.length` and the greeting string to see how quotes in the **shell** affect how arguments are passed.

**Exercise 4 — Instance methods:** Add a `turnOff()` method to `LampDemo`, call in order: `turnOn()`, `turnOff()`, and print the status after each step. The output should reflect state changes on the **same object**.

**Exercise 5 — Find the structural error:** The snippet below does not produce a standard runnable program in Java 17. Point out the reason and fix it:

~~~java
public class Sample {
    public void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

*Hint:* In the structure being taught, `main` must be `static` so the launcher can call it without creating an object; change it to `public static void main(String[] args)`.

## 11. Self-Check

You have mastered the lesson if you can answer:

1. How does `HelloWorld.java` differ from `HelloWorld.class`?
2. Why does a file containing `public class HelloWorld` need the name `HelloWorld.java`?
3. Is `main` a class or a method? Why does `main` in Java 17 normally have `static`?
4. How do `return` and `System.out.println` differ?
5. In what two ways are `static` methods and instance methods called?
6. Why is `java -cp out demo.PackageHello` different from `java PackageHello`?
7. With no-argument input, why should you check `args.length` before `args[0]`?

**Key takeaway:** The **source file** is where code is written; the **class** organizes program components; the **method** defines behavior; **`main`** is the traditional entry point of a Java 17 program. From a single `.java` file and a few `javac`/`java` commands, you can already create, run, and explain basic Java program structure.
