# Compiling, Creating Objects, and Running the First Java Program

An object-based Java program typically goes through the following sequence of steps: **write a class definition → compile the source code → run the class with a `main` method → use `new` to create an object → call a method on the object → observe the result**. This lesson walks through each step using Java 17+, from a `.java` file to a working console program.

After this lesson, you should be able to do the following on your own:

- Check the JDK and use the `javac` and `java` commands correctly.
- Create a Java file containing one `public class` and one helper class; understand the relationship between file name, class name, and compilation outputs.
- Declare a class with fields, a constructor, and methods, then create multiple objects using `new`.
- Distinguish between a class, an object, a reference variable, and the `static main` method.
- Explain the execution order of program lines and predict stdout.
- Distinguish compile-time errors from runtime errors, and know how to handle common errors related to file names, constructors, classpath, and member access.

## 1. Preparing the Environment: JDK and Terminal

The **JDK (Java Development Kit)** provides the tools to compile and run Java programs. To build and run the examples yourself, install JDK **17 or higher**; the examples in this lesson use syntax compatible with Java 17. An IDE can assist with compilation, but understanding terminal commands helps determine whether an error comes from the source code or the environment configuration.

Open PowerShell, Terminal, or Command Prompt, and run:

~~~bash
java -version
javac -version
~~~

Meaning:

- `java -version` shows the Java runtime version currently used by the `java` command.
- `javac -version` shows the version of the `javac` compiler.
- If `java` works but `javac` is missing, you usually need to check your JDK installation and `PATH` configuration.
- If the two commands point to different versions, check the directory order in `PATH` and your IDE's Java configuration; do not assume the IDE uses the same JDK as the terminal.

The version outputs depend on the machine, so there is no single fixed stdout for these two commands.

### Source Code, Bytecode, and the JVM

Common workflow:

~~~text
FirstObjectApp.java    (Java source code)
        |
        | javac -encoding UTF-8 FirstObjectApp.java
        v
FirstObjectApp.class   (bytecode of the main class)
Student.class          (bytecode of the helper class)
        |
        | java -cp . FirstObjectApp
        v
JVM loads classes, finds main, executes code, and prints the result
~~~

`javac` checks syntax, data types, and many language rules before generating `.class` files. `java` starts the runtime, loads the required classes, and executes the program. The two steps serve different purposes: **successful compilation does not guarantee that the program will run without throwing an exception**.

In this first lesson, we keep all files in the **same directory**, without declaring a `package` or using a build tool. This helps you recognize how classes and objects work before learning multi-directory project structures.

## 2. Writing the First Program in a Single File

Create any practice directory you like, such as `java-first-object`. Inside that directory, create a file with the **exact name `FirstObjectApp.java`** and enter the entire following content:

~~~java
public class FirstObjectApp {
    public static void main(String[] args) {
        Student lan = new Student("Lan", 8);
        Student minh = new Student("Minh", 6);

        System.out.println(lan.describe());

        lan.study(2);

        System.out.println(lan.describe());
        System.out.println(minh.describe());
        System.out.println("Same object: " + (lan == minh));
    }
}

class Student {
    private final String name;
    private int completedLessons;

    Student(String name, int completedLessons) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Invalid name");
        }
        if (completedLessons < 0) {
            throw new IllegalArgumentException("Lesson count cannot be negative");
        }
        this.name = name;
        this.completedLessons = completedLessons;
    }

    void study(int additionalLessons) {
        if (additionalLessons <= 0) {
            throw new IllegalArgumentException("Additional lessons must be positive");
        }
        completedLessons = Math.addExact(completedLessons, additionalLessons);
    }

    String describe() {
        return name + ": " + completedLessons + " lessons";
    }
}
~~~

Having two classes in one source file is valid: `FirstObjectApp` is a **public top-level class**, while `Student` is a **package-private top-level class** because no access modifier is written. Java requires the file name to match the name of the public top-level class: `FirstObjectApp.java`. The `Student` class does not need to be in `Student.java` in this single-file example, although in real projects placing each main class in its own file usually makes management easier.

**There is no need to put `public` before `class Student`:** a single source file cannot declare two public top-level classes with different names; if you want both classes to be public, you must place them into their corresponding source files.

### Compiling

Open the terminal in the directory containing `FirstObjectApp.java`:

~~~bash
javac -encoding UTF-8 FirstObjectApp.java
~~~

When the code is valid, `javac` typically finishes **without printing anything to stdout**. Inspecting the directory reveals the compiled files:

~~~text
FirstObjectApp.java
FirstObjectApp.class
Student.class
~~~

The `.class` file names and locations above apply to this example **without a package**, using the `javac` command shown. The `.class` files are compilation outputs; you still need to keep the `.java` source file to edit the program.

`-encoding UTF-8` tells the compiler to read the source code explicitly as UTF-8, which is useful when lessons and display strings contain Vietnamese text. If you are using a terminal on Windows, you should save the file in UTF-8 rather than a legacy system encoding.

### Running

After compiling, run:

~~~bash
java -cp . FirstObjectApp
~~~

Exact output:

~~~text
Lan: 8 lessons
Lan: 10 lessons
Minh: 6 lessons
Same object: false
~~~

The `java` command takes the **fully qualified class name**, not the `.class` or `.java` file name, in the standard bytecode execution mode shown here. The `-cp .` option specifies the **class path** as the current directory, where Java looks for `FirstObjectApp.class` and `Student.class`. The dot here means “the current directory”, not a sentence-ending period.

If you run the command from a different directory, the `.` class path shifts to that other directory as well and the classes may not be found. When you are first learning, compile and run directly in the directory containing the source code, or pass an accurate class path.

## 3. Reading the Program in JVM Execution Order

The entry point of the console program in this example is:

~~~java
public static void main(String[] args) {
    // Statements are executed from here
}
~~~

This is part of the `FirstObjectApp` class. Meaning of each component:

| Component | Role |
| --- | --- |
| `public` | Allows the launcher to access the entry-point method |
| `static` | The method belongs to the class; the launcher does not have to instantiate `FirstObjectApp` itself |
| `void` | `main` does not return a value to Java code calling it |
| `main` | The conventional entry-point method name in Java |
| `String[] args` | String array containing command-line arguments; unused in this example |

Do not confuse **`main` being static** with every class or every object being static. The `main` method is just the entry point where the program begins; inside it, `new` is still used to create other objects.

In sequence:

1. The JVM runs `main` of `FirstObjectApp`.
2. `new Student("Lan", 8)` creates a new `Student` object and runs the constructor with the name Lan and completed lessons equal to 8. A reference to this object is assigned to the variable `lan`.
3. `new Student("Minh", 6)` creates a **second object**, assigned to the reference variable `minh`. The two objects have their own separate fields.
4. `lan.describe()` returns the string `Lan: 8 lessons`; `System.out.println` prints this string.
5. `lan.study(2)` updates Lan's completed lesson count from 8 to 10.
6. The second call to `lan.describe()` reflects the new state. `minh.describe()` still prints `Minh: 6 lessons` because Minh's object has not been updated.
7. `lan == minh` compares the **reference identity** of the two variables: they point to two different objects, so the expression evaluates to `false`.

### Class, Object, Reference: Three Things to Keep Separate

Reading the line:

~~~java
Student lan = new Student("Lan", 8);
~~~

Specifically:

- `Student` on the left is the **reference type** defined by the `Student` class.
- `lan` is a **reference variable** belonging to the `main` method.
- `new` requests the creation of a new object.
- `Student("Lan", 8)` calls the matching constructor to initialize the object.
- The result of the `new` expression is a reference to the created object; the `=` operator assigns that reference to `lan`.

Illustration:

~~~text
main()
    lan  --------> Student object #1
                    name = "Lan"
                    completedLessons = 10

    minh --------> Student object #2
                    name = "Minh"
                    completedLessons = 6
~~~

The arrows represent **reference relationships**, not specific JVM memory addresses. Objects are created and exist according to program semantics; from this example alone, one cannot assert that the JVM always places objects at fixed addresses or allocates them in any specific physical memory region.

**A variable is not the object itself.** Multiple variables can point to the same object; conversely, each `new Student(...)` in the example creates a separate instance.

## 4. What Parts Make Up the `Student` Definition?

Inside the class:

~~~java
class Student {
    private final String name;
    private int completedLessons;

    Student(String name, int completedLessons) {
        // Initialize state
    }

    void study(int additionalLessons) {
        // Update behavior
    }

    String describe() {
        // State-reading behavior
    }
}
~~~

The snippet above is an **illustrative skeleton**, not a standalone runnable file. The complete example in section 2 contains all the required method bodies.

### Fields Store the State of Each Instance

`name` and `completedLessons` are **instance fields**. Each created `Student` has its own field values. `private` restricts direct access from outside the class. As a result, external code cannot arbitrarily assign `completedLessons = -1` and must go through controlled behavior instead.

`final` in `private final String name` restricts reassigning this field after it has been initialized. Do not infer that every field or the entire object automatically becomes immutable just because one field is `final`. In this example, `completedLessons` can still change through `study`.

### Constructors Establish a Valid Initial State

Snippet:

~~~java
Student(String name, int completedLessons) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Invalid name");
    }
    if (completedLessons < 0) {
        throw new IllegalArgumentException("Lesson count cannot be negative");
    }
    this.name = name;
    this.completedLessons = completedLessons;
}
~~~

A constructor has the **same name as the class** and **declares no return type**, not even `void`. When `new Student("Lan", 8)` is executed, the name and lesson-count parameters are used to set the object's fields.

`this.name` is the `name` field of the object being constructed; `name` on the right-hand side is the constructor parameter. Using `this` disambiguates the two identical names. The same applies to `completedLessons`.

The constructor also checks: the name must be non-null and not contain only whitespace; the completed lesson count must be non-negative. If the data is invalid, the constructor throws an `IllegalArgumentException`. This helps the object finish creation in a valid state.

Once a class declares a constructor with parameters, Java **does not automatically add** a no-argument default constructor. Therefore, `new Student()` will cause a compilation error in this version of the class.

### Instance Methods Provide Behavior

`study` and `describe` are **instance methods** and must be called on an appropriate object reference, such as `lan.study(2)`:

~~~java
void study(int additionalLessons) {
    if (additionalLessons <= 0) {
        throw new IllegalArgumentException("Additional lessons must be positive");
    }
    completedLessons = Math.addExact(completedLessons, additionalLessons);
}
~~~

`study` requires the additional lesson count to be greater than 0 and safely computes the sum using `Math.addExact`. If the `int` addition overflows, `Math.addExact` throws an `ArithmeticException`; the field is not assigned an overflowed result. For this first lesson, the main goal is to see that a method can validate parameters and update an object's state.

~~~java
String describe() {
    return name + ": " + completedLessons + " lessons";
}
~~~

`describe` **returns** a `String` rather than printing to the terminal itself. When `main` calls `System.out.println(lan.describe())`, `describe` builds the string, and then `println` is responsible for printing it. Separating “producing data” from “printing data” makes the class easier to reuse and test.

## 5. Distinguishing Static Methods and Instance Methods

`main` is a `static` method, whereas `study` and `describe` are instance methods.

| Situation | Common Syntax | Meaning |
| --- | --- | --- |
| Calling a static method | `FirstObjectApp.main(new String[0])` | Calls a method belonging to the class; typically invoked automatically by the Java launcher in this lesson |
| Creating an instance | `new Student("Lan", 8)` | Creates a Student object |
| Calling an instance method | `lan.study(2)` | Executes the behavior of the Student referenced by `lan` |
| Reading an instance method's result | `lan.describe()` | Retrieves the string describing the state of the same object |

Writing `Student.study(2)` is **incorrect** because `study` is not static; the compiler cannot know which instance you want to update. Nor can you access `completedLessons` directly from static `main` without a valid reference and access rights.

You do not have to turn every method into a static method just to call it inside `main`; create an appropriate instance and use it through a reference variable.

## 6. Reference Variables Can Share One Object: Verifying with a Second Program

After learning how to create two independent objects, the next step is to observe **two variables pointing to the same object**. Create a separate file named **`ReferenceDemo.java`**:

~~~java
public class ReferenceDemo {
    public static void main(String[] args) {
        Counter first = new Counter(1);
        Counter alias = first;
        Counter second = new Counter(1);

        alias.increment();

        System.out.println("first: " + first.value());
        System.out.println("second: " + second.value());
        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == second: " + (first == second));
    }
}

class Counter {
    private int count;

    Counter(int count) {
        this.count = count;
    }

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ReferenceDemo.java
java -cp . ReferenceDemo
~~~

Exact stdout:

~~~text
first: 2
second: 1
first == alias: true
first == second: false
~~~

Analysis:

- `first` references the first Counter, which initially has `count = 1`.
- `alias = first` copies the **reference value**; it does not create a new Counter.
- `second = new Counter(1)` creates a second Counter with the same initial value, but it is a different object.
- `alias.increment()` increments the first Counter to 2. Reading via `first.value()` returns 2 because `first` and `alias` point to the same object.
- `first == alias` is true, and `first == second` is false. For two reference-type variables, `==` checks whether they point to the same object, **not** the contents of their fields.

Do not confuse this comparison with `String.equals` or a custom `equals` method defined by a class to compare values. This lesson is examining **how objects are created and referenced**, so `==` is appropriate for demonstrating identity.

## 7. Two Ways to Organize Source Code When Starting Out

### Approach A: One File with Multiple Top-Level Classes

The `FirstObjectApp.java` example contains `public class FirstObjectApp` and `class Student`. This is the easiest approach to run while learning because you only need to compile one file. The compiler generates a `.class` file for each class needed in that file.

Only the `FirstObjectApp` class has the example's `main` method; the fact that the compiler creates `Student.class` does **not** make `Student` a standalone console program. If you try to run `java -cp . Student`, the launcher will not find a suitable `main` method and will report an error.

### Approach B: Splitting into Two Source Files

As the program grows, you can split it into:

~~~text
java-first-object/
    FirstObjectApp.java
    Student.java
~~~

`FirstObjectApp.java` will contain only `public class FirstObjectApp` with `main`; `Student.java` will contain only the `class Student` definition. Both classes can remain in the same default package as in the original example. The content and logic remain the same as in section 2, only moving the class definition into its own file.

Explicitly compile both files:

~~~bash
javac -encoding UTF-8 Student.java FirstObjectApp.java
java -cp . FirstObjectApp
~~~

**Note:** This is **a guide to splitting the existing code**, not two independent source snippets listed again. Do not keep a `class Student` in both `FirstObjectApp.java` and `Student.java` in the same package at the same time, as doing so can cause a duplicate class definition error.

In a real project, classes also usually live in a named package; the section below introduces a brief transition step so you do not get confused when running from the terminal.

## 8. When Starting to Use Packages: Fully Qualified Class Names and Classpath

`package` groups classes into a namespace. If a source file declares `package edu.demo;`, the JVM needs the fully qualified class name `edu.demo.Main` when launching it. This is a modest advanced example, just enough for you to recognize the difference from the default package.

Create the directory `src/edu/demo/`, then create the file **`src/edu/demo/Main.java`**:

~~~java
package edu.demo;

public class Main {
    public static void main(String[] args) {
        Message message = new Message("Java");
        System.out.println(message.text());
    }
}

class Message {
    private final String subject;

    Message(String subject) {
        this.subject = subject;
    }

    String text() {
        return "Hello, " + subject + "!";
    }
}
~~~

From the **root directory of the example**, create an output directory and run:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/edu/demo/Main.java
java -cp out edu.demo.Main
~~~

Stdout:

~~~text
Hello, Java!
~~~

`javac -d out` places the bytecode files into the package directory structure under `out`, such as `out/edu/demo/Main.class` and `out/edu/demo/Message.class`. The command `java -cp out edu.demo.Main` has two important parts:

- `-cp out`: the classpath root is the `out` directory, **not** the `out/edu/demo` directory itself.
- `edu.demo.Main`: the fully qualified class name consisting of the package and class; do not write a file path or the `.class` extension.

If you already have an `out` directory, you do not need to create it again. These commands are independent of the `FirstObjectApp` example; you can try them in a separate directory to avoid mixing the two structures.

At this introductory stage, you do not need to memorize the entire module path and advanced packaging mechanisms. Just understand that the **package determines the class's fully qualified name** and the **classpath determines where the runtime looks for class files**.

## 9. Do Not Confuse Pre-Compilation with Source-File Execution Mode

Since Java 11, the `java` tool supports running a program directly from a source file in appropriate situations, for example:

~~~bash
java FirstObjectApp.java
~~~

This approach is commonly called **source-file mode**: the launcher processes the source code to run the program without requiring you to type a separate `javac` command first. However, because this lesson's goal is to clarify both stages, you should practice:

~~~bash
javac -encoding UTF-8 FirstObjectApp.java
java -cp . FirstObjectApp
~~~

Do not treat `java FirstObjectApp.java` and `java -cp . FirstObjectApp` as the same syntax; they use two different launch modes. For projects with multiple packages, dependencies, or a build tool, how you run the program will also depend on the project configuration.

## 10. Common Errors When Creating and Running the First Class

| Error / Symptom | Common Cause | How to Resolve |
| --- | --- | --- |
| `javac` is not recognized | The JDK is not installed properly, or `PATH` does not point to the JDK's `bin` directory | Check `javac -version`, install the JDK, and configure PATH |
| `class FirstObjectApp is public, should be declared in a file named FirstObjectApp.java` | The file name differs from the public top-level class name | Name the file `FirstObjectApp.java`, matching exact uppercase/lowercase letters |
| `';' expected`, `'}' expected` | Missing `;` or closing brace | Check the compilation error location and nearby lines |
| `cannot find symbol` | Misspelled field/method/class name, wrong scope, or class not found during compilation | Check names, declarations, imports/packages, and the files being compiled |
| `constructor Student ... cannot be applied to given types` | Calling the constructor with mismatched argument count or types | Use `new Student("Lan", 8)` matching the signature |
| `Student()` does not compile | The class only declares a constructor with parameters | Pass all required arguments or define an appropriate additional constructor |
| `non-static method ... cannot be referenced from a static context` | Calling an instance method via the class name from a static context | Create an object and call `object.method()` |
| `... has private access in Student` | Reading or writing a private field from another class | Use a valid public API; do not modify the modifier just to silence the error |
| `Could not find or load main class FirstObjectApp` | Running from the wrong directory, wrong classpath, or wrong class name | Check `.class` files and run `java -cp . FirstObjectApp` in the right directory |
| `Main method not found ...` | The executed class does not have a valid `main` entry point | Run the class that has `main` rather than a helper class like `Student` |
| `NullPointerException` | Calling a method through a `null` reference | Check whether the object has been created and validate values before using them |
| Program runs but output does not change after an update | Calling a method on a different object, forgetting to call the method, or reading the wrong variable | Trace each `new` call, reference assignment, and method call |
| Wrong value printed due to `==` with `String` | Comparing two references instead of string contents | When comparing string contents, use `equals` |
| Modified `.java` and ran again, still getting old output | `.java` has not been recompiled; running old `.class` files | Recompile before running |

### How to Categorize Errors for Quick Troubleshooting

**Compile-time errors** occur when `javac` cannot produce valid bytecode, for example due to a missing brace, disallowed member access, or an invalid constructor call. Fix the source code according to the compiler message and run `javac` again.

**Runtime errors** happen after the program has compiled, for example an `IllegalArgumentException` when calling `study(-1)`, a `NullPointerException`, or an incorrect classpath configuration. Read the exception name, message, and stack trace. If a method validates input and intentionally throws an exception, that can be state-protecting behavior rather than a compiler error.

**Logic errors** occur when the program compiles and runs normally but computes the wrong value. For example, accidentally using `minh.study(2)` instead of `lan.study(2)`. The compiler cannot know your business intent, so you need to predict and verify the results yourself.

## 11. Practice Exercises After Running the Examples

### Exercise A — Predict State Yourself

Keeping the `FirstObjectApp` program unchanged, replace the call:

~~~java
lan.study(2);
~~~

with:

~~~java
lan.study(5);
minh.study(1);
~~~

Before running it, predict the three Student description lines: the first print is still `Lan: 8 lessons`, the second print is `Lan: 13 lessons`, and Minh's line is `Minh: 7 lessons`. The expression `lan == minh` remains `false` because updating fields does not turn two objects into one.

### Exercise B — Test the Constructor Rules

Replace `new Student("Lan", 8)` with `new Student("Lan", -1)`. Predict what happens: the compiler still **accepts the syntax and data types**, but at runtime the constructor throws an `IllegalArgumentException` with the message `Lesson count cannot be negative`. Execution does not reach the `println` statements after the failed object creation unless appropriate exception-handling code is present.

### Exercise C — Create an Alias and Compare Identity

Add the following to `main` after creating `lan`:

~~~java
Student alias = lan;
System.out.println("Alias: " + (alias == lan));
alias.study(1);
~~~

This is **an addition to the existing program**, not a standalone file. The alias check output is `Alias: true`. Calling `alias.study(1)` mutates the very object that `lan` points to. Predict the subsequent `lan.describe()` outputs again.

### Exercise D — Split Classes into Separate Files

Move `Student` into `Student.java` as shown in section 7; remove the `Student` definition from `FirstObjectApp.java`. Compile both files and run again. If stdout stays identical, you have demonstrated that source file organization can change while program behavior remains unchanged.

### Exercise E — Create Your Own Program

Design a `Lamp` class with a `private boolean on` field, a constructor that initializes it in the off state, `turnOn()` and `turnOff()` methods, and a `status()` method returning `"ON"` or `"OFF"`. Write `LampApp` with a `main` method that creates **two separate lamps**, turns one on, and prints the status of both.

Self-check requirements:

1. Both newly created lamps are in the `OFF` state.
2. Calling `first.turnOn()` switches only the `first` lamp to `ON`.
3. Calling `first.turnOff()` returns it to `OFF`.
4. If `Lamp alias = first`, operations performed through `alias` affect `first`.
5. Compile and run from the terminal, and explain which file name contains `main`.

## 12. Completion Checklist

You have met the lesson requirements when you can answer and perform all of the following on your own:

- [ ] I can run `java -version` and `javac -version` and identify the JDK in use.
- [ ] I can create `FirstObjectApp.java` myself, compile it, and launch it from the right directory.
- [ ] I understand why `javac` creates two `.class` files even though the example has only one source file.
- [ ] I understand why the run command must point to `FirstObjectApp` containing `main`.
- [ ] I can read a class structure consisting of instance fields, a constructor, and instance methods.
- [ ] I can point out which expression creates an object (`new Student(...)`) and which variables hold references (`lan`, `minh`).
- [ ] I can explain why `lan` and `minh` have separate state.
- [ ] I can explain why `alias = first` does not create an additional object.
- [ ] I can distinguish `static main` from the instance method `study`.
- [ ] I know how to use `this.field` when a parameter has the same name as a field.
- [ ] I know how compile-time errors, runtime errors, and logic errors differ.
- [ ] I can modify source code, recompile it, and verify stdout against my predicted results.

Once these steps feel familiar, continue exploring class declarations, constructor overloading, field initialization, access levels, `this`, instance/static, state/behavior/identity, and how objects interact. All of those concepts become easier to understand once you have **created objects yourself, called methods, and observed state changes in an actual running program**.
