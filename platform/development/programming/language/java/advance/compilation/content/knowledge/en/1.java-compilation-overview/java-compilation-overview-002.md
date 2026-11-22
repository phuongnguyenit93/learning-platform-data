# From Java Source Code to .class Files and Running Programs

A `.java` file is source code for humans to write and read. The Java compiler (`javac`) converts valid source code into `.class` files containing **Java bytecode** and class structure information. When running a program, the `java` command launches the JVM, loads the required classes, verifies and links them, initializes classes, and then executes bytecode (via interpretation, JIT compilation, or a combination depending on the JVM). The two phases—**compile time** and **runtime**—are therefore different: a successful compilation does not guarantee that all dependencies, configurations, or runtime conditions are correct.

This lesson traces the path from source code and class files to an executing program; distinguishes the responsibilities of `javac`, the `java` tool, and the JVM; and provides verification commands for Java 17 and later.

## 1. Overview Diagram

```text
Hello.java source code
        |
        v
  javac (compilation)
  - syntax parsing
  - name resolution and type checking
  - bytecode and metadata generation
        |
        v
    Hello.class                 (not native machine code)
        |
        v
  java -cp out Hello
        |
        v
       JVM
  - class loading
  - bytecode verification, linking
  - class initialization on demand
  - finding and invoking main
  - execution; may optimize via JIT
        |
        v
  Program results, errors, or effects
```

This is a **high-level model**, not a guarantee that every phase runs sequentially for every class. The JVM can load or resolve references on demand; execution details and JIT timing depend on the JVM. In a typical run command, initialization of the class containing the `main` method happens before `main` is invoked.

Concepts to distinguish:

| Component | Role | Output/Location |
| --- | --- | --- |
| `.java` source code | Describes classes, interfaces, records, expressions, statements, etc. in the Java language | Text file, input to `javac` |
| `javac` | Analyzes, validates, and generates bytecode | One or more `.class` files; or compilation error messages |
| `.class` file | Binary Java Class File format containing bytecode, constant pool, and metadata | Input that can be read by the JVM/ClassLoader |
| `java` | Tool that launches the Java runtime environment and the requested class/module/source | JVM process and application |
| JVM | Defines the execution model, loads/links/initializes classes, and runs bytecode | Runtime behavior; may produce errors or exceptions |

`javac` usually does **not** directly produce a native executable file like `.exe`. Bytecode is relatively independent of the operating system and CPU; a JVM suited to the environment is the component that provides execution. This does not mean every application automatically runs everywhere: Java version, libraries, JNI, files, permissions, and system configuration still have an effect.

## 2. Minimal Practice: Hello.java → Hello.class → stdout

Create a file named `Hello.java` with the content:

```java
public class Hello {
    public static void main(String[] args) {
        String target = "Java";
        System.out.println("Xin chào, " + target + "!");
    }
}
```

In the directory containing `Hello.java`, run with JDK 17+:

```bash
javac -encoding UTF-8 -d out Hello.java
java -cp out Hello
```

The stdout output of the `java` command:

```text
Xin chào, Java!
```

Observations:

1. `javac` checks the source code; if valid, it creates `out/Hello.class`. Depending on the operating system, the path separator may be `/` or `\`.
2. `-encoding UTF-8` specifies how `javac` reads source characters, making Vietnamese examples less dependent on default encoding settings.
3. `-d out` selects the root directory for placing class files. For a class without a `package` declaration, the output goes directly in `out`. You should create a separate output directory to avoid mixing source code and compiled artifacts.
4. `java -cp out Hello` puts the `out` directory on the **classpath** and requests running the class named `Hello`. The command uses the **class name**, not `Hello.class` or the path `out/Hello.class`.
5. In this program, the JVM locates the entry method `public static void main(String[] args)`, and then the `println` statement prints one line to stdout.

If the JDK is missing, the system may not find `javac`. A JRE/runtime can run applications but does not necessarily provide a compiler. `java -version` shows the runtime in use; `javac -version` shows the compiler version. If multiple JDKs are installed, the two commands can point to different versions due to `PATH`/environment configuration.

### File Name and Type Declarations

In the example, `Hello` is a `public` top-level class, so the source file must be `Hello.java` (case-sensitive according to Java naming rules). A single source file can declare multiple non-`public` top-level types and can produce multiple `.class` files; nested, local, or anonymous classes can also generate additional class files. **Do not equate "one source file = one class file".**

## 3. Inside javac's Compilation Process

At a learning level, the steps can be described as follows:

| Stage | What Does the Compiler Do? | Example Error or Output |
| --- | --- | --- |
| Reading source and lexical/syntactic analysis | Recognizes tokens, declaration structures, expressions, and statements; builds syntax representation | Missing `;`, missing `}`, invalid `if` syntax |
| Name and symbol resolution | Determines which declarations `String`, `System`, the `target` variable, and invoked methods belong to | `cannot find symbol` when referencing a non-existent/invisible name |
| Type checking and language constraints | Checks assignment types, calls, access permissions, methods, generics, checked exceptions, etc. | Cannot assign `String` to `int` |
| Lowering/representation transformation | Converts some source constructs into bytecode-suitable forms, possibly generating supporting code | Some generic constructs undergo type erasure; lambda expressions are represented via bytecode/runtime mechanisms |
| Class file generation | Writes the class file format, method bytecode, constant pool, and attributes | `Hello.class` and related class files |

This is not a complete list of internal passes of every `javac` version. In practice, the compiler may perform different passes and optimizations/transformations.

The following example **intentionally fails to compile**:

```java
public class Broken {
    public static void main(String[] args) {
        int count = "5";
    }
}
```

Save as `Broken.java` and run `javac Broken.java`: the compiler reports a type error because `String` cannot be converted to `int`. Do not treat the reported line and column numbers as invariant across versions. When a compilation error occurs, do not assume a valid new `Broken.class` has been created.

Similarly, `javac` does not run the `main` method just to inspect the result. It checks conditions that can be verified from the source code and available dependencies. For example, division by a variable equal to 0, file operations, or network connections may fail only at execution time.

### Method Calls and Type Information

For a call such as `System.out.println(...)`, the source code uses names and declarations; bytecode typically stores **symbolic references** to classes, fields, and methods in the constant pool. The JVM resolves these references into runtime entities according to linking rules, potentially on demand. Therefore, a `.class` file contains more information than a simple sequence of instructions.

`javac` also does not guarantee "optimizing away" every computation. The JVM can perform runtime optimizations based on observed information, while the compiler can fold constants, lower language constructs, and emit appropriate instructions.

## 4. What Do Class Files and Bytecode Look Like?

`.class` is a **binary file**, not a text file, so it cannot be read directly in an editor like `.java`. According to the class file format, it has a magic identifier, version, constant pool, class declaration, fields, methods, and attributes. Methods that normally have bytecode store their body in the `Code` attribute; not every method has a bytecode body (for example, `abstract` or `native` methods).

You can inspect it using the tool included with the JDK:

```bash
javap -classpath out Hello
javap -classpath out -c Hello
javap -classpath out -v Hello
```

- `javap Hello` (with an appropriate classpath) displays member declarations at the bytecode level.
- `-c` displays instructions such as loading values, invoking methods, and returning; the exact content depends on the source code, compiler version, and Java constructs.
- `-v` displays detailed information such as version, constant pool, flags, and attributes; the output is long, so use it only when analysis is needed.

**Do not infer the original source code directly from bytecode.** Local variable names, comments, and part of the source structure may not be preserved; the same behavior can compile to different bytecode. `javap` is a class file reading tool, not an application runner.

### Class File Version

A class file carries a `major/minor` version pair indicating the format level the runtime must support. For a typical Java 17 class file, the `major version` is **61**. A JVM that only supports a lower class file version may throw `UnsupportedClassVersionError` when trying to load a newer version. This is a classic example of "compiled successfully on machine A, but fails to run on machine B".

To proactively target Java 17 when using a newer JDK, use:

```bash
javac --release 17 -encoding UTF-8 -d out Hello.java
```

`--release 17` targets the language level, bytecode, and Java SE API appropriate for that release. It does not bundle external libraries automatically; an application still needs its own runtime libraries and a compatible environment. With a toolchain that only has JDK 17, `--release 17` is also valid.

## 5. From Classpath to Packages and Fully Qualified Class Names

A class placed in a package must be referenced by its **fully qualified name**. Suppose the file `src/com/example/app/Main.java` contains:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Ứng dụng đang chạy");
    }
}
```

From the project directory, run:

```bash
javac -encoding UTF-8 -d out src/com/example/app/Main.java
java -cp out com.example.app.Main
```

Stdout:

```text
Ứng dụng đang chạy
```

`javac -d out` places classes according to their package into `out/com/example/app/Main.class`. Meanwhile, `-cp out` points to the **root of the package tree**, not to the `out/com/example/app` directory itself. When using `java`, write `com.example.app.Main` instead of just `Main` or `Main.class`.

**Classpath** is a list of locations for class loaders to help locate classes and resources (for example, directories, JARs). For an application that uses external libraries, both compilation and execution may need an appropriate classpath. In the following symbolic example, replace `lib/example.jar` with an actual JAR and replace the source file and launch class to match the project:

```bash
javac -cp lib/example.jar -d out src/com/example/app/Main.java
java -cp "out:lib/example.jar" com.example.app.Main
```

The separator between multiple classpath entries is **`:` on Linux/macOS and `;` on Windows**. Thus, the `java` line illustrated above applies to Linux/macOS; on Windows use `"out;lib/example.jar"`. On both operating systems, quotation marks are helpful when paths contain spaces.

**Module path** (`--module-path`) in JPMS differs from classpath; modular applications use module names, `module-info.java` descriptors, and have their own package read/export rules. Do not arbitrarily replace classpath with module path if the program has not been designed as a module. From this basic example, grasp the exact meaning of `-d`, `-cp`, and class names first.

## 6. What Does the JVM Do When the Program Starts Running?

For a traditional classpath program, the command `java -cp out Hello` starts a JVM and requests running the `Hello` class. The JVM performs the following activities according to the specification and program needs:

1. **Loading:** the class loader locates the class definition and builds a runtime `Class` representation. Not all classes in the classpath directory are loaded right at the start.
2. **Linking:** includes verification (checking class file validity/safety bounds), preparation (preparing `static` fields with default values and required runtime structures), and resolution (resolving symbolic references). Resolution may be performed lazily depending on the reference and the JVM; do not imagine there is always a pass resolving everything before `main`.
3. **Initialization:** executes static field initializers and static initializer blocks in the specified order when a class needs to be initialized; this step differs from preparation. Other classes may be initialized later.
4. **Execution:** starts the thread calling `main` and the methods the application needs. The JVM executes bytecode via an interpreter, JIT, or another specification-compliant execution mechanism. HotSpot typically has a JIT compilation mechanism for frequently executed code, but there is no guarantee that every method is JIT-compiled.

A small example of class initialization, creating `Lifecycle.java`:

```java
public class Lifecycle {
    static {
        System.out.println("Khởi tạo lớp");
    }

    public static void main(String[] args) {
        System.out.println("Chạy main");
    }
}
```

Run:

```bash
javac -encoding UTF-8 Lifecycle.java
java Lifecycle
```

Stdout:

```text
Khởi tạo lớp
Chạy main
```

The `javac` command does not print those two lines because it only compiles. The `static` block is executed when the JVM initializes the `Lifecycle` class; only then does `main` print the remaining line. Static initialization in complex applications can cause separate errors, such as `ExceptionInInitializerError`.

### Bytecode Is Not Equivalent to CPU Instructions

Instructions such as `aload`, `invokevirtual`, and `return` belong to the **JVM instruction set**. They are not x86/ARM CPU instructions. The JVM may interpret instructions or compile some segments into machine code within the process. Thus, the "Java → bytecode → JVM" flow explains portability, while actual performance depends on runtime optimization, libraries, the operating system, and workload.

The rules for class files, the verifier, class loading, linking, and initialization are defined by the Java Virtual Machine Specification. This lesson distinguishes **specified behavior** from **common implementation approaches** (such as HotSpot JIT).

## 7. Successful Compilation Can Still Fail at Runtime

Distinguishing errors by phase helps find the root cause faster:

| Symptom | Phase | Common Cause | How to Handle |
| --- | --- | --- | --- |
| `error: cannot find symbol` | Compilation | Wrong name, import, scope, or missing compile classpath | Check declarations/imports and dependencies |
| `incompatible types` | Compilation | Type incompatible with assignment/call | Fix the data type or conversion |
| `Could not find or load main class` | Startup | Wrong fully qualified name or classpath not pointing to package root | Check `-cp`, package, file location |
| `NoClassDefFoundError` | When loading or using a class | A referenced class lacks a suitable definition at runtime, or prior initialization failed | Check JARs, classpath/runtime, and root cause |
| `ClassNotFoundException` | At runtime when loading a class via API | A class name requested via an API such as `Class.forName` cannot be found | Check name, class loader, classpath/module path |
| `UnsupportedClassVersionError` | When loading a class | The class file is newer than the runtime supports | Upgrade the runtime or compile with an appropriate `--release` |
| `NoSuchMethodError` | Runtime linking | The runtime class no longer has the method matching the signature referenced by bytecode | Synchronize library versions and rebuild |
| `NullPointerException`, `ArithmeticException` | Execution | Unsuitable runtime conditions/data | Check logic, inputs, stack trace |

Actual messages may include more details and vary by version. For instance, an application **can** compile against a newer library version, yet at runtime use an old JAR that no longer has the corresponding method; the JVM only detects the incompatibility when the relevant reference is resolved. Do not conclude "`javac` passed, so runtime is definitely fine".

**Old class files are a common trap.** If you just edited erroneous code, `javac` fails, yet class files from the previous compilation remain in the `out` directory, the `java` command may run old code. When debugging, check `javac`'s exit code and class file timestamps; use a clean build directory managed by the build tool when verification is needed. Avoid arbitrarily deleting data that does not belong to build output.

## 8. Three Ways of Running That Are Easily Confused

**Way A — compile then run the class** (the focus of this lesson):

```bash
javac -d out Hello.java
java -cp out Hello
```

This leaves class files in `out`, which can be inspected with `javap`.

**Way B — run a single source file directly with Java 11+**:

```bash
java Hello.java
```

The `java` tool supports source-file mode: it processes/compiles source code and runs the program in the same command, typically without creating `Hello.class` in the current directory like `javac`. This is a convenience for simple files and **does not prove that Java skips the compilation step**. This command differs from `java Hello`, which looks up a compiled class on the classpath.

**Way C — run a JAR with Main-Class**:

```bash
java -jar app.jar
```

This requires a suitable JAR with an entry point (for example, a `Main-Class` manifest attribute). A JAR is a container that can hold multiple classes/resources; `-jar` is not merely another way of writing `-cp`. Simply naming a file `app.jar` does not make it runnable by itself. This command illustrates how to launch and does not assume an existing `app.jar` is ready to run.

In large projects, Maven/Gradle typically configure `javac`, classpath, resources, tests, packaging, and run commands automatically. They **orchestrate the steps** without eliminating the source code → class file → JVM model.

## 9. Self-Verification in Your Environment

Follow each step to verify what gets created and what gets run:

1. Type `java -version` and `javac -version`; ensure you are using a suitable JDK (JDK 17+ preferred).
2. Compile `Hello.java` using `javac -encoding UTF-8 -d out Hello.java`. If the command reports an error, fix the error before running.
3. Verify that the file `out/Hello.class` actually exists. Use `javap -classpath out -c Hello` to view bytecode.
4. Run `java -cp out Hello` and compare stdout verbatim with the example. If the class is not found, verify the package and classpath root.
5. Try adding the type error `int count = "5";` to the source code to observe a **compile-time** error. Revert the error and recompile.
6. Try the `Lifecycle` example to witness the static initializer running before `main`. Note that the example's output comes from running `java`, not `javac`.
7. If you have multiple JDKs, try explaining why a class file compiled with `--release 17` targets a Java 17 runtime, whereas compiling with a newer release may not run on Java 17.

### Self-Check Questions

- Why is `java -cp out com.example.app.Main` different from `java -cp out Main`?
- Why can a single `.java` file generate multiple `.class` files?
- Why can `javac` not report every `NullPointerException` that could occur at runtime?
- How do class `preparation` and `initialization` differ?
- When do you suspect `UnsupportedClassVersionError`, and when do you suspect a wrong classpath?
- Does `java Hello.java` actually eliminate compilation?

Core answers: `-cp` points to the search root and the class name must match the package; nested/auxiliary types can become separate class files; many errors depend on data/runtime; preparation prepares default values for static fields while initialization runs initializers; class version differs from classpath; source-file mode still compiles before execution.

## 10. Takeaways

In Java, **`javac` turns source code into class files containing bytecode**, while **`java` starts the runtime environment and the JVM executes the program**. A class file is not machine code and does not guarantee sufficient dependencies or a compatible runtime. To diagnose accurately, observe **source code → compilation result → class file location/classpath → runtime behavior** separately, using `javac`, `java`, and `javap` to verify each step.

Authoritative references: *The Java Language Specification* (language and compile-time rules), *The Java Virtual Machine Specification* (class files, loading, linking, initialization, execution), and the `javac`/`java`/`javap` tool documentation of the JDK in use.