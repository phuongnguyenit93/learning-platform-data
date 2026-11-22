# Relationship Between Source Code, Compiler, Bytecode, and the JVM

## 1. The Big Picture

When writing Java, you create **source code** (usually `.java` files) for humans to read and edit. The **`javac`** tool in the JDK compiles source code into **bytecode** in `.class` files. When running, the **`java`** program starts the JVM, the JVM loads the needed classes, verifies and links them, and then executes the bytecode via interpretation or JIT compilation depending on the JVM and the execution profile.

The goal of this lesson is to answer four questions accurately:

1. What do `.java` and `.class` contain, and how do they differ?
2. How does `javac` work at **compile time**, and how do `java` and the JVM work at **run time**?
3. Why does Java bytecode generally work across multiple operating systems, and what are the limits of that?
4. How can you compile, run, inspect bytecode, and diagnose errors at each stage yourself?

~~~mermaid
flowchart LR
    SRC["HelloPipeline.java<br/>Java source code"] -->|"javac"| CLS["HelloPipeline.class<br/>Bytecode"]
    CLS -->|"java: starts JVM"| JVM["JVM<br/>Loads, verifies, links,<br/>initializes, and executes class"]
    JVM -->|"Interpretation or JIT<br/>when appropriate"| NATIVE["Machine instructions running on<br/>CPU and operating system"]
~~~

The diagram illustrates the common flow when **compiling ahead of time and then running**. It does not mean every bytecode instruction is compiled by JIT, nor does it mean the JVM always loads all classes of the application right at startup.

## 2. Distinguishing the Four Components

| Component | Role | Timing and Result |
|---|---|---|
| **Java source code** | Represents classes, methods, and statements in Java syntax | Learner creates `HelloPipeline.java` |
| **Compiler `javac`** | Checks syntax, names, types, and many static constraints; generates bytecode | `javac HelloPipeline.java` produces `HelloPipeline.class` if successful |
| **Bytecode / `.class` file** | Contains compiled class representation: metadata, constant pool, methods, and bytecode instructions | Input for the JVM; **not** direct native machine code for Windows/Linux |
| **JVM** | Execution environment for Java bytecode; manages class loading, memory, exceptions, and runtime | An appropriate JVM executes the `main` call along with the classes used |

The **JDK** (Java Development Kit) provides the development tools—notably `javac`, `java`, `javap`—along with the Java runtime. The **JVM** is the virtual machine that executes bytecode, not another name for the compiler. In modern Java distributions, people usually install the **JDK** to both compile and run; older documentation may refer to the separate runtime portion as the **JRE**.

Further distinction: the `java` program is the **launcher** (the command that starts the runtime); the JVM is the execution environment initialized by the launcher. Saying “run with Java” in short usually refers to this entire process, but when diagnosing errors, you should know which step failed.

## 3. A Runnable Java Example

Create the file **`HelloPipeline.java`** (matching the exact capitalization of the public class) with this content:

~~~java
public class HelloPipeline {
    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];

        System.out.println("Xin chao, " + name);
        System.out.println("2 * 3 = " + twice(3));
    }
}
~~~

Assume **JDK 17 or newer** is installed. Open a terminal in the directory containing the file. Check:

~~~bash
java -version
javac -version
~~~

Compile and run (this example targets Java 17 bytecode):

~~~bash
javac --release 17 -encoding UTF-8 HelloPipeline.java
java -cp . HelloPipeline
~~~

Expected output:

~~~text
Xin chao, Java
2 * 3 = 6
~~~

Try passing a command-line argument:

~~~bash
java -cp . HelloPipeline Linh
~~~

Output:

~~~text
Xin chao, Linh
2 * 3 = 6
~~~

Exact explanation:

- `javac` reads the source file contents, checks the code, and creates `HelloPipeline.class` in the current directory. If compilation reports an error, you need to fix the source and recompile.
- `java -cp . HelloPipeline` tells the launcher to look for the **class named `HelloPipeline` on the classpath** (`.` is the current directory), and then the JVM executes the `public static void main(String[] args)` method of that class.
- When running a compiled class, the argument to `java` is the **class name**, not the `.class` file name. Correct: `java HelloPipeline`; wrong in this mode: `java HelloPipeline.class`.
- `args` holds the arguments **after** the class name. The no-argument case is already guarded by `args.length == 0`, because accessing `args[0]` directly on an empty array would cause `ArrayIndexOutOfBoundsException`.

**Note on `-encoding UTF-8`:** this flag instructs `javac` to read the source code as UTF-8; it **does not automatically change the terminal encoding**. If strings with Vietnamese diacritics print incorrectly on some consoles, check the console and runtime environment encoding separately.

## 4. How Does `javac` Check Code and Generate Bytecode?

Consider this snippet in the example:

~~~java
private static int twice(int value) {
    return value * 2;
}
~~~

Conceptually, the compiler must verify that:

1. The syntax of the class, method, and statement declarations is valid.
2. The variable `value` is declared, has type `int`, and the multiplication `value * 2` is valid.
3. The return value matches the declared return type `int`.
4. The call `twice(3)` from `main` can be resolved to the corresponding method.

If you write `return "sai kiểu";`, `javac` will reject it because the method is declared to return `int` while the expression returns `String`. This error occurs **before the program is ever run**.

After checking succeeds, the compiler creates the `.class` file. A class file can contain information such as the class name and superclass, fields/methods, type descriptors, the constant pool, and the bytecode of methods. The exact level of detail depends on the compiler, Java version, and compiler options.

**Do not equate “compiles successfully” with “correct program”.** `javac` does not automatically prove every business rule, does not test every branch, and usually does not detect errors such as division by zero on a runtime execution path, missing files, or a `NullPointerException` triggered by real data.

## 5. Inspecting Bytecode Yourself Instead of Just Imagining It

The JDK includes the **`javap`** tool to inspect the structure of a `.class` file. After compiling successfully, run:

~~~bash
javap -c -p HelloPipeline
~~~

Things you can observe:

- The `twice(int)`, `main(java.lang.String[])`, and default constructor methods.
- Instructions performing arithmetic operations and method calls, such as `iload`, `imul`, and `ireturn` in `twice`.
- Operations accessing `System.out` and calling `println` in `main`.
- For string concatenation on modern JDKs, the compiler may use `invokedynamic` rather than a predictable sequence of `StringBuilder` concatenation calls.

To view metadata and the class file version:

~~~bash
javap -verbose HelloPipeline
~~~

If compiled with `--release 17`, the class file section typically displays **`major version: 61`**. This is the Java 17 class file format, not an operating system version and not a source code version number.

`javap` is a **disassembler/inspector** tool: it presents bytecode and metadata in human-readable form without running the application. You do not need to memorize every opcode; simply recognize that **bytecode is an intermediate representation**, distinct from both source code and CPU machine code.

### Verifying with an Intentional Change

Change `return value * 2;` to `return value * 3;`, **save the file, and then just run `java HelloPipeline` again without recompiling**. The result still comes from the old `.class`: `2 * 3 = 6`. Only after running `javac --release 17 -encoding UTF-8 HelloPipeline.java` again does the result become `2 * 3 = 9`. **Note:** the label string `2 * 3 = ` in `println` stays the same, while the internal calculation changed to multiplying by 3. As a result, the label no longer accurately describes the actual operation; this is a small example of **output presenting a misleading meaning even though the code is valid**. Change the label if you want the displayed information to be accurate.

This is a very clear experiment for distinguishing **current source** from the **bytecode the JVM is executing**. After this exercise, restore `twice` to multiply by 2 so the remaining examples stay consistent.

## 6. What Does the JVM Do After the `java` Command?

In the mode that runs a compiled class, the process goes roughly as follows:

1. **Runtime startup:** the `java` launcher processes options, classpath/module path, and requests the main class.
2. **Class loading:** the JVM uses class loaders to find, read, and define the needed classes. Many classes are loaded only when used.
3. **Linking:** the JVM checks the validity of the class file (*verification*), prepares the necessary structures/static storage (*preparation*), and resolves symbolic references (*resolution*). Some steps may be performed lazily when needed according to JVM rules.
4. **Initialization:** before using a class under initialization-triggering conditions, the JVM executes that class's static field initializers/static blocks according to language rules.
5. **Execution:** the JVM invokes `main`, executes the program's bytecode, creates objects, calls methods, handles exceptions, and manages memory at runtime.

Common JVM implementations can **interpret** bytecode initially and use a **JIT compiler** to optimize/compile frequently executed segments into native machine code. That often improves speed, but does not guarantee that every method is JIT-compiled. Different JVMs may choose different execution strategies while still supporting the same Java model.

**Garbage collection (GC)** is a runtime service related to object memory management. It is not the job of `javac`, nor does it turn bytecode into native code; GC and JIT are two different mechanisms.

## 7. Why Is Java Said to Be “Write Once, Run Anywhere”?

The same valid `.class` file can run on different operating systems **if** there is a JVM compatible with the class file version and the APIs the program uses.

| Component | Does it depend on the OS/architecture? |
|---|---|
| `HelloPipeline.java` | Source code can usually be shared; build environments may still differ |
| `HelloPipeline.class` | Bytecode is standardized and generally portable across platforms |
| JVM/JDK installation | Built specifically per OS and CPU (Windows x64, Linux ARM, …) |
| Native libraries via JNI, system tools, file paths | Can be platform-dependent and require separate handling |

Therefore, **portable bytecode** does not mean “runs on every machine with nothing installed”. The target machine needs a suitable runtime; an application may also depend on libraries, file permissions, configuration, native components, or a specific Java version.

For example, a class file built with a newer JDK may use a **higher class file version** than an older JVM supports. In that case, `UnsupportedClassVersionError` occurs when the JVM tries to load the class, even though your Java code has no syntax errors.

## 8. JDK Versions, `--release`, and Compatibility

When developing on a newer JDK while needing to run on Java 17, compile with:

~~~bash
javac --release 17 -encoding UTF-8 HelloPipeline.java
~~~

`--release 17` instructs `javac` to use the language rules, class file target, and standard public API set corresponding to Java 17. It is usually more reliable than changing only the class-file target while accidentally calling a newer Java API.

Condition: **the compiler must support the chosen release**. An older JDK cannot compile for a newer language/release it does not know about.

Do not confuse three things:

- **The JDK used to build**: check with `javac -version`.
- **The class file compatibility level**: affected by `--release`; inspect with `javap -verbose`.
- **The JVM actually running the application**: check with `java -version`.

In an environment with multiple JDKs installed, `java` and `javac` can point to **two different versions** via `PATH`/tool configuration. Diagnosing versions must check **both commands**, not rely on the project folder name.

## 9. Directories, Packages, Classpath, and Class Names

The first example uses the **default package** so beginners can run it easily. In projects, you usually declare a package name. Suppose you have:

~~~text
src/
└── demo/
    └── Welcome.java
~~~

File `src/demo/Welcome.java`:

~~~java
package demo;

public class Welcome {
    public static void main(String[] args) {
        System.out.println("Welcome from demo");
    }
}
~~~

Compile into an output directory (create the `out` directory beforehand using OS file/terminal tools):

~~~bash
javac --release 17 -d out src/demo/Welcome.java
java -cp out demo.Welcome
~~~

Output:

~~~text
Welcome from demo
~~~

When there is a `demo` package, the launcher requires the **fully qualified name** `demo.Welcome`; the classpath `out` must point to the **root directory containing `demo/`**, not the `out/demo` directory. `javac -d out` places the class under the appropriate package directory structure.

Some common mistakes:

- Typing `java Welcome` even though the class belongs to package `demo`.
- Setting `-cp out/demo` instead of `-cp out`.
- Running the command from a directory different from what you think, causing `.` or `out` to point to the wrong place.
- Passing the path to `.java` or `.class` instead of the class name when running in class mode.

The classpath can also contain directories and `.jar` dependencies. For this lesson, you only need to understand: **compile time needs to find referenced types; run time needs to find the classes the application actually uses**. The compile and runtime paths are not necessarily identical, so a missing dependency may only surface at runtime.

## 10. Classifying Errors by Stage

| Symptom | Common Stage | First Thing to Check |
|---|---|---|
| `';' expected`, `cannot find symbol`, `incompatible types` | Compile time | Check source file, syntax, names/types, and libraries on the compile classpath |
| `class HelloPipeline is public, should be declared in a file named HelloPipeline.java` | Compile time | Match the public class name and file name, including case |
| `javac: command not found` or “not recognized” | Before compilation | Check JDK installation, `PATH`, and the terminal being used |
| `Could not find or load main class` | Launcher/class loading | Check classpath, package, compiled file location, and class name |
| `Main method not found` | Program startup | Check that the class has a suitable entry point method, e.g., `public static void main(String[] args)` |
| `UnsupportedClassVersionError` | Class loading | Compare the class file target with `java -version` |
| `NoClassDefFoundError` when invoking functionality | Runtime/linking/loading | Check that the dependent class is present and compatible at runtime |
| `NullPointerException`, division by zero, file errors | During execution | Read the stack trace, input data, and actual call path |

**Important distinction:** `cannot find symbol` from `javac` is a code/reference error at **compile** time. `Could not find or load main class` is an error during **launch/run**: a class may have already been compiled, yet the launcher cannot find it on the requested classpath.

If an error only appears at runtime, “recompiling identically” will not necessarily fix it. Read the exception name, message, stack trace location, and verify the runtime environment.

## 11. An Interesting Exception: Running a `.java` File Directly

Since Java 11, with source-file launching, a simple single-file program can be run with:

~~~bash
java HelloPipeline.java
~~~

In **this mode**, the launcher invokes compilation of the source for that run and then executes it; you do not need to call `javac` beforehand, and you do not necessarily get `.class` files saved to disk like with the traditional `javac` command.

Therefore, distinguish between:

- `javac HelloPipeline.java` then `java HelloPipeline`: **compile first, run the class**.
- `java HelloPipeline.java`: **run from source file** via source-file mode (when the environment/version supports it).

This **does not negate the role of bytecode/JVM**. In lessons about the build chain and inspecting class files, use the `javac` + `java` pair and `javap` first so you clearly see each component.

## 12. Edge Cases to Know Early

**1. Editing source without rebuilding.** In class-running mode, the JVM reads existing bytecode and does not compare `.java` modification dates to recompile for you. This easily causes the confusion “why is the program still printing the old output?”.

**2. Compilation succeeds, but a library is missing at runtime.** A class may use types from a library at compile time, yet at runtime the `.jar` containing the needed class is missing. Depending on when the JVM needs that class, the error might only appear when execution reaches the related feature.

**3. Classpath points to the right file's folder but the wrong root.** For `demo.Welcome`, passing `out/demo` to `-cp` is the wrong root location; you must pass `out`.

**4. Multiple classes in one source file.** One Java file can declare additional non-public top-level classes or nested classes; `javac` can generate **multiple `.class` files** from a single `.java` file. Do not assume there is always a one-to-one relationship between source files and class files.

**5. A static initializer fails.** A class can pass compilation yet fail when the JVM initializes the class—for example, static initialization throws an exception. This error is completely different from a syntax error in `javac`.

**6. Console encoding other than UTF-8.** Reading UTF-8 source accurately does not guarantee the console displays Unicode characters properly. This is the difference between bytecode, source encoding, and output encoding.

**7. Running on an older JDK.** A JVM that does not support the built class file version may refuse to load the file. Adjust the target/release appropriately or upgrade the runtime; do not edit bytecode contents by hand.

**8. Missing permissions or insufficient resources.** Valid bytecode can still fail when file access is denied, configuration is missing, a network port is already in use, or memory is limited. Compile-time checks do not replace runtime error handling.

## 13. Practice Exercises with Verification Answers

### Exercise A — Identify Each Command's Output

Given three commands:

~~~bash
javac --release 17 HelloPipeline.java
javap -c HelloPipeline
java -cp . HelloPipeline
~~~

Match:

1. Produces bytecode from source.
2. Displays bytecode information/instructions.
3. Loads and executes the program on the JVM.

**Answer:** 1 is `javac`, 2 is `javap`, 3 is `java`. The `javap` command does not execute the `main` method.

### Exercise B — Predict the Error

You have `src/demo/Welcome.java` declaring `package demo;`, compiled with `-d out`. You run:

~~~bash
java -cp out Welcome
~~~

What might happen? **Answer:** the launcher cannot find a class named `Welcome` in the default package. The correct command is `java -cp out demo.Welcome`.

### Exercise C — Identify the Stage

You edit the source file to:

~~~java
int number = "sai";
~~~

You receive an error message immediately when running `javac`. Does the error happen in the JVM or the compiler? **Answer:** the `javac` compiler detects the type incompatibility `String` → `int`; `main` is not executed because compilation failed.

### Exercise D — Class File Version

You compile with `--release 17` and inspect with `javap -verbose`. You find `major version: 61`. Explain why a Java runtime older than what supports this class file might fail to run it, even though the `.class` file contains no Windows/Linux paths.

**Answer:** bytecode portability across platforms is one thing, while **whether a runtime version understands the class file format** is another. The JVM must support the corresponding class file version.

### Exercise E — Prove That the Class File Is the Execution Input

After compiling `HelloPipeline`, change a message line in the source and then only run `java HelloPipeline`. Record the result. Recompile and record the new result.

**Expected answer:** the first run continues using the behavior from the old `.class`; after recompiling, `.class` updates so the output reflects the new source. Do not confuse this with `java HelloPipeline.java`, because that is source-file mode.

## 14. Takeaways and Completion Criteria

- [ ] Explain **`.java` → `javac` → `.class` → `java`/JVM** in your own words.
- [ ] Successfully compile and run `HelloPipeline.java` on a JDK that supports Java 17.
- [ ] Use `javap -c` to view bytecode without confusing it with native machine code.
- [ ] Know the differences between compile-time errors, class loading/launcher errors, and runtime exceptions.
- [ ] Understand that the classpath is where the JVM searches for classes, while the package determines the fully qualified class name.
- [ ] Know that `--release` and `java -version` answer two different compatibility questions.
- [ ] Do not claim that all bytecode must be JIT-compiled; do not claim a Java application runs without a compatible runtime.

**Conclusion:** In a standard build workflow, Java code is not executed directly by the CPU from `.java` files. `javac` turns source code into standardized bytecode; the `java` launcher and the JVM load, verify, link, initialize, and execute the needed classes. Thanks to the bytecode/JVM layer, an application can be moved across platforms more easily, but it still must satisfy the right runtime version, libraries, and environmental requirements.
