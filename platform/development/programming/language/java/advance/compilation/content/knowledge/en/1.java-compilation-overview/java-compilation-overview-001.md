# What Is Java Compilation and What Problem Does It Solve?

A Java program starts as source code that a programmer can read and edit, such as the file `HelloCompilation.java`. A computer needs a structured representation to execute that program. **Java compilation** is the process of transforming Java source code into class files (`.class`) containing **bytecode**, while also detecting many syntax and data type errors before the program runs.

The most important distinction to make from the start is that **`javac` compiles source code; `java` starts the program execution environment**. A successful compilation does not mean the program has already run, produced correct results, or cannot encounter errors at runtime.

## 1. The Big Picture: From Source File to Running Program

~~~text
Developer writes source code
        |
        v
HelloCompilation.java
        |
        | javac (compiler in the JDK)
        | - analyzes syntax, names, types, and language rules
        v
HelloCompilation.class  (bytecode + class metadata)
        |
        | java HelloCompilation
        v
JVM: class loading -> verification -> linking/initialization when needed
        |
        | bytecode interpretation and/or JIT compilation to machine code
        v
Program runs on the operating system and hardware
~~~

The diagram above is a model for orientation, not a claim that every stage happens exactly once or always in the same fixed order. The JVM can load classes on demand, and the JIT can compile only code segments that are executed frequently. Therefore, **compiling source code with `javac`** and **JIT compilation inside the JVM** are two different tasks.

Components to identify:

| Component | Role | Example |
| --- | --- | --- |
| `.java` | Source code written by the developer | `HelloCompilation.java` |
| `javac` | The JDK's Java compiler | `javac HelloCompilation.java` |
| `.class` | Bytecode file of a compiled class or type | `HelloCompilation.class` |
| `java` | Command to launch a Java application | `java HelloCompilation` |
| JVM | Virtual machine that executes bytecode and manages class loading, memory, and runtime mechanisms | The JVM included in the Java runtime |
| JDK | Development kit containing tools such as `javac`, `java`, `javap`, and the runtime | JDK 17, JDK 21 |

A single `.java` file can produce multiple `.class` files if it declares multiple types or has nested classes; these two extensions do not always correspond one-to-one.

## 2. Why Does Java Need Compilation?

**First, to translate from a human-written language into a format the JVM understands.** The statement `int total = price * quantity;` is Java source code. `javac` converts it into bytecode and information about classes, fields, methods, types, constants, and so on so that the JVM can load and execute it according to the Java specification.

**Second, to detect errors early.** The compiler checks program structure, declared names, type compatibility, access permissions, and many other constraints. If you assign a string to an `int` variable without a valid conversion, compilation fails; you do not need to run up to that statement to discover the error. This helps reduce the cost of fixing errors, but **does not prove that business logic is correct**.

**Third, to decouple source code from a specific hardware environment.** `javac` typically produces bytecode in the JVM class file format, rather than generating x86 or ARM machine code directly for each operating system. One set of bytecode can run on multiple systems that have a compatible JVM of the appropriate version and sufficient dependent libraries. This is the foundation of Java's portability, but it does not mean every program will behave identically on every machine: the operating system, file paths, native libraries, default charset, configuration, or external dependencies can still differ.

**Fourth, to produce output for packaging and distribution.** `.class` files are commonly placed into a `.jar` or application deployment structure. Runners can use the compiled output without receiving the entire source code. JAR packaging is a different step from compilation; a JAR containing classes also needs an appropriate entry point and dependencies to run.

**Fifth, to allow the runtime to optimize itself according to real execution conditions.** Bytecode preserves an intermediate form suitable for the JVM to execute using techniques such as interpretation and JIT compilation. This optimization capability does not make every Java program faster by default; the outcome still depends on algorithms, data, the JVM, startup, and machine resources.

### What Does Compilation Solve, and What Does It Not Solve?

| Issue | Does `javac` help? | Limitations |
| --- | --- | --- |
| Incorrect syntax, incompatible types, unresolved names | Yes, typically reports errors at compile time | Diagnostics depend on context and tool version |
| Converting Java code to bytecode | Yes | Output still requires a compatible runtime |
| Detecting syntactically valid operations that violate intent | Not guaranteed | Requires tests, reviews, and business verification |
| Detecting all errors such as division by zero with real data | No | Some errors only occur at runtime |
| Guaranteeing no missing configuration, libraries, or environment errors | No | Requires packaging and runtime verification |
| Compiling bytecode to machine code at runtime | Not the primary responsibility of `javac` | The JVM can do this via JIT |

## 3. First Example: How Does Compiling Differ from Running?

Install JDK 17 or later and check both tools:

~~~sh
javac -version
java -version
~~~

The displayed version depends on the installed JDK. Create a file named **`HelloCompilation.java`** with the following complete content (the file name matches the `public` class name):

~~~java
public class HelloCompilation {
    public static void main(String[] args) {
        int price = 120;
        int quantity = 3;
        int total = price * quantity;

        System.out.println("Tổng: " + total);
    }
}
~~~

Open a terminal in the directory containing the file and run in sequence:

~~~sh
javac -encoding UTF-8 HelloCompilation.java
java HelloCompilation
~~~

The output of the `java` command is:

~~~text
Tổng: 360
~~~

Observe three distinct milestones:

1. **Before `javac`:** You have the source code `HelloCompilation.java`; there is no new class file from this example yet.
2. **After `javac` succeeds:** You have `HelloCompilation.class`. The compiler normally does not execute the `main` method and does not print the line `Tổng: 360`.
3. **After `java HelloCompilation`:** The JVM loads the class, invokes `public static void main(String[] args)`, and the program prints the result to the console.

Here `java` takes **the name of the class containing `main`**, not the path `HelloCompilation.class`. When running from the current directory, the default classpath usually includes the current directory; to be explicit and avoid configuration dependence, you can use:

~~~sh
java -cp . HelloCompilation
~~~

In this command, `-cp .` specifies the current directory as the classpath. If there is a compilation error, **do not continue running an old `.class` file** and mistake it for the result of the newly edited source code: the class file generated from a previous successful compilation may still remain.

### Try Changing One Line

Change `quantity = 3` to `quantity = 4` in the source code. If you only re-run `java HelloCompilation` without recompiling, the output can still be `360` because the JVM is reading the old `.class`. Only after running `javac -encoding UTF-8 HelloCompilation.java` again will the output be `Tổng: 480`. This is direct proof that saving a source file and compiling are two separate actions.

## 4. What Does the Compiler Check?

An easy-to-understand view of what `javac` does:

1. **Reading and parsing:** From characters, keywords, brackets, operators, comments, and so on, it builds the syntactic structure of the program. Missing a `}` or writing a syntactically invalid statement can stop here.
2. **Name and context resolution:** Associates variable, method, class, package, and import names with their corresponding declarations; checks visibility scope and access rights.
3. **Type checking and language rules:** Evaluates whether expressions, assignments, method calls, checked exception handling, and many other rules are valid.
4. **Bytecode and metadata generation:** Generates JVM instructions, the constant pool, signatures, class information, attributes, and so on, then writes them to the class file.

These are responsibility groups for learning, not a commitment to describe every internal pass of every `javac` version accurately.

Example of a type error, saved separately as **`BrokenType.java`**:

~~~java
public class BrokenType {
    public static void main(String[] args) {
        int count = "3";
        System.out.println(count);
    }
}
~~~

Run:

~~~sh
javac BrokenType.java
~~~

`javac` reports an error because the string literal `"3"` has type `String` and cannot be assigned directly to `int`. The exact phrasing and position in error messages can change across JDK versions, so you should not test by matching error message text character for character.

If the intent is to convert a string of digits into an integer, you can use `Integer.parseInt("3")`. This call **is valid at compile time**, but can cause a `NumberFormatException` at runtime if the input string is not a valid integer. That is a classic example of the boundary between static checking and runtime conditions.

### Compile-Time Errors, Runtime Errors, and Logic Errors

| Issue Type | Example | When Is It Seen? | How to Handle |
| --- | --- | --- | --- |
| Syntax/type | Missing `;`; assigning `String` to `int` | `javac` reports an error | Fix code to match valid syntax and types |
| Runtime | Integer division by 0; missing data file | When the corresponding execution path is executed | Handle inputs, exceptions, and environment state |
| Logic | Multiplying by the wrong unit price, using the wrong discount formula | The program may still compile and run | Test against business requirements |

A standalone runtime error example, saved as **`RuntimeFailure.java`**:

~~~java
public class RuntimeFailure {
    public static void main(String[] args) {
        int divisor = 0;
        int result = 10 / divisor;
        System.out.println(result);
    }
}
~~~

~~~sh
javac RuntimeFailure.java
java RuntimeFailure
~~~

Compilation succeeds; at runtime, integer division by 0 causes an `ArithmeticException`. The exact stack trace and line numbers depend on the file and JDK, so they are not fixed here. This distinction is very important: **`javac` does not execute every branch of a program to prove that all runtime conditions are safe**.

## 5. What Is Bytecode and Why Is It Not Machine Code?

Bytecode in a `.class` file is an instruction set and data structure defined for the JVM. It contains virtual-machine-level operations, such as loading values, performing arithmetic, calling methods, and returning results. A computer's CPU does not inherently execute a `.class` file directly like a native program. The JVM must read, verify, and execute it in an appropriate way.

You can inspect the output from the first example with:

~~~sh
javap -c HelloCompilation
~~~

`javap` is the JDK's class file disassembler tool; depending on the options, it displays method signatures or bytecode instructions. A source line such as `int total = price * quantity;` can correspond to multiple instructions. There is no need to memorize opcodes in this introductory lesson; recognize that **a source program is re-represented in another form**.

A `.class` file also contains a class file format version. For example, Java 17's format has major version 61; Java 21 has major version 65. An older JVM can reject a newer class file with `UnsupportedClassVersionError`. This is a bytecode compatibility issue, distinct from failing to find a class on the classpath.

### `javac` and JIT Are Not the Same Step

- **`javac`:** Runs before application startup in the usual workflow; compiles from `.java` to `.class` bytecode.
- **Interpretation in the JVM:** Executes the semantics of bytecode at runtime.
- **JIT (just-in-time compilation):** A runtime mechanism that can compile suitable bytecode segments into optimized machine code based on runtime observations; depending on the JVM and configuration, the implementation may differ.

The fact that a JVM has a JIT does not mean every method is guaranteed to be JIT-compiled, or that JIT happened right after `javac`. The word "compilation" appears in both places, but **the input, output, and timing** are different.

## 6. Multiple Classes and Packages

When a project has packages, the class name used at runtime is the **fully qualified name including the package**, while the classpath points to the **root of the package structure**. For example, create the file tree:

~~~text
project/
└── src/
    └── demo/
        ├── Calculator.java
        └── App.java
~~~

Content of **`src/demo/Calculator.java`**:

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int twice(int value) {
        return value * 2;
    }
}
~~~

Content of **`src/demo/App.java`**:

~~~java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println("Kết quả: " + Calculator.twice(7));
    }
}
~~~

From the `project` directory, create the output directory `out` if it does not exist yet, then compile both files:

~~~sh
mkdir out
javac -encoding UTF-8 -d out src/demo/Calculator.java src/demo/App.java
java -cp out demo.App
~~~

The `mkdir out` command only needs to be run once when `out` does not exist yet. On Windows PowerShell and common shells there are equivalent commands; if the directory already exists, skip the creation step. Output:

~~~text
Kết quả: 14
~~~

The compiled output has the main structure:

~~~text
out/
└── demo/
    ├── Calculator.class
    └── App.class
~~~

Here:

- `package demo;` specifies the package name. By convention, source files are placed in the corresponding path for ease of management.
- `-d out` specifies the root output directory; `javac` creates the subdirectories matching the package inside it.
- `-cp out` tells the JVM where to find classes. It does not point only to `out/demo` because the fully qualified name `demo.App` already includes the package.
- `java -cp out demo.App` runs `main` of the `demo.App` class, not `App` as a class in the default package.
- Compilation needs to find the classes, types, and libraries that the source code depends on. Both the **compile-time classpath** and the **runtime classpath** are important; missing dependencies at either time causes different errors.

Real projects typically do not require typing every `.java` file manually: tools like Maven/Gradle determine source sets, dependencies, and invoke the compiler according to the build configuration. Even so, understanding the `javac` command directly helps clearly distinguish whether an issue belongs to source code, compilation, packaging, or runtime.

## 7. Practical Workflow When Compiling

A typical workflow loop is:

~~~text
Write/edit .java
      |
      v
Run build / javac ---- compilation error? ----> fix source code and recompile
      |
      | success
      v
.class / libraries / artifacts
      |
      v
Run application and test ---- runtime / logic error? ----> fix + compile + retry
      |
      v
Package, distribute, and operate
~~~

Some technical points that often cause confusion:

**Source and runtime versions.** On a JDK that supports this option, `javac --release 17 HelloCompilation.java` requests compilation targeting the language level, bytecode, and standard API of Java 17. For example, when using JDK 21, this option is useful for emitting code targeting Java 17 if the program and its dependencies are compatible. Using `-source 17 -target 17` alone does not guarantee that the entire Java API is restricted to the target version. Check the JDK running the program with `java -version`.

**Classpath.** A valid class file may still fail to run if `java` is looking in the wrong place or missing dependency JARs. When seeing `ClassNotFoundException` or `NoClassDefFoundError`, check the fully qualified class name, root directory, JARs, and dependency graph; these two errors can have different causes.

**File name and `public` class.** A top-level class `public class Example` must reside in `Example.java` (under Java's file-naming rules). Renaming the file arbitrarily can cause a compilation error. Uppercase and lowercase letters in the class name must be kept consistent.

**Operation order.** Save the source code, run `javac`, then run `java`. When a build fails, read the first meaningful compilation error before running old output. Clean old build artifacts when you need to verify that a new build was actually produced.

**Encoding.** For content containing Vietnamese, `-encoding UTF-8` helps `javac` read the source file correctly when the file is saved as UTF-8. The terminal encoding when *displaying* stdout is a separate issue; if the console displays garbled text, check the terminal and runtime encoding instead of immediately concluding that `javac` generated incorrect bytecode.

**Compiling a single class vs. compiling an entire project.** The compiler can find and compile additional dependent source code based on sourcepath/classpath and configuration; you should not rely accidentally on default source-finding behavior to build a large project. For multi-module projects, use a build configuration that clearly defines sources and dependencies.

**Running a source file directly.** Since Java 11, a command like `java HelloCompilation.java` has a single-file source-code program execution mode: the launcher handles compilation in memory and then runs it, usually without leaving `HelloCompilation.class` on disk with this invocation. This convenient feature **does not eliminate the transition from source code to executable form**, nor does it turn `java File.java` into a replacement for all multi-file project builds.

## 8. Misconceptions to Avoid

| Claim | More Accurate Explanation |
| --- | --- |
| "Java compilation produces machine code that runs directly on the CPU." | `javac` normally produces bytecode for the JVM, not a native executable for the CPU. |
| "Successful compilation means the program is correct." | It only confirms that the code meets the static checks performed by the compiler in that configuration. |
| "`javac` and `java` are the same command." | `javac` compiles; `java` launches the program. Source-file execution mode is a special case of the launcher. |
| "One Java file is guaranteed to produce exactly one class file." | One source file can produce multiple `.class` files. |
| "Any `.class` can run as long as there is a JVM." | Bytecode version, libraries, configuration, and environment must be compatible. |
| "JIT happens when running `javac`." | JIT is a technique inside the JVM when the program runs. |
| "`import` automatically downloads libraries." | `import` allows using declared names according to Java rules; the dependency must actually be present in the compile/runtime configuration. |

## 9. Practice and Self-Check

**Exercise 1 — Distinguish the two points in time.** Re-run the `HelloCompilation` example, edit `quantity`, and run `java HelloCompilation` *before* running `javac` again. Explain why you might see the old result. Then recompile and confirm the change.

**Exercise 2 — Fix a compilation error.** With `BrokenType.java`, replace `int count = "3";` with `int count = Integer.parseInt("3");`. After compiling and running successfully, try `Integer.parseInt("three")`: what changes between the compilation error and the runtime error? You do not need to force the program to catch the exception in this exercise; the goal is to identify the detection stage.

**Exercise 3 — Identify the classpath.** With the `demo` package project, predict the result when running `java App` instead of `java -cp out demo.App` from the `project` directory. Why does the JVM not find the requested class with that name/path?

**Exercise 4 — Explain bytecode.** After using `javap -c HelloCompilation`, state one sentence about `.java`, one sentence about `.class`, and one sentence about the role of the JVM. There is no need to memorize JVM instructions.

To evaluate yourself, you should be able to answer five questions:

1. **What input and output does Java compilation take and produce?** `.java` source code → bytecode together with metadata in `.class` (in normal `javac` usage).
2. **Why can type errors appear before running?** Because the compiler checks type constraints on the source code without needing to execute the `main` method.
3. **When do you see `System.out.println`?** When the JVM executes that statement, not when `javac` generates the class file.
4. **Why can a `.class` file still fail at runtime?** Because runtime requirements also apply: a compatible JVM, finding classes/dependencies, valid configuration, and a safe execution path.
5. **Where does JIT sit?** Inside the JVM's execution process (if the JVM uses this mechanism), distinct from the `javac` step before running.

**Connection to the next part of the course:** Once you have grasped `.java → javac → .class → JVM`, you can study in order: syntax and type checking, classfile/bytecode structure, classpath and module path, class loading/linking, JIT, and build tools. Each part answers a separate question; this lesson provides a map so you do not confuse them as a single step.