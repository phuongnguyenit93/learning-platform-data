# JDK and JVM

In the Java ecosystem, the **JDK** and **JVM** are two components with distinct roles that work closely together. The JDK provides tools to develop, compile, package, and run Java applications. The JVM is the virtual machine that executes bytecode in class files. Understanding the boundary between these two components helps you choose the right tool, interpret environment errors, and understand how a Java program goes from source code to execution.

## 1. The Big Picture

When writing a Java program, you typically work with three concepts:

- **JDK (Java Development Kit):** the toolkit for developers. The JDK includes the compiler, launcher, platform libraries, and various utilities for developing, debugging, packaging, or analyzing applications.
- **JVM (Java Virtual Machine):** the virtual machine that executes Java bytecode. The JVM loads classes, verifies bytecode, manages memory, and executes code.
- **JRE (Java Runtime Environment):** the term for the environment required to run Java applications, commonly described as the JVM plus supporting runtime libraries and components. This is a useful concept for understanding the architecture, even though standalone JRE distribution has changed in modern Java versions.

A quick way to remember: **the JDK is for development; the JVM executes bytecode; the JRE describes the application runtime environment.** When you install a full JDK, you typically already have both the compilation tools and the environment to run programs.

## 2. What is the JDK?

The JDK is the toolkit and foundational set of components for building Java applications. A JDK distribution typically includes:

1. **Java compiler — javac:** translates `.java` source code into bytecode in `.class` files.
2. **Java launcher — java:** launches a class, JAR, or module; the launcher initializes an appropriate JVM to execute the program.
3. **Java platform APIs:** standard libraries such as collections, I/O, networking, concurrency, date/time, and many other APIs.
4. **Packaging and documentation tools:** for example, `jar` for working with JARs and `javadoc` for generating API documentation.
5. **Development and diagnostic tools:** for example, `jshell`, `jdb`, `jcmd`, `jstack`, `jmap`, and `jfr` in supported distributions.

The JDK is a toolkit, not just a compiler. You can use the same JDK installation to compile source code, run applications, create JARs, generate documentation, and investigate certain runtime issues.

### Common Tools

| Tool | Purpose |
|---|---|
| `javac` | Compiles Java source code into bytecode |
| `java` | Runs a Java class, JAR, or module |
| `jar` | Creates, views, and updates JAR files |
| `javadoc` | Generates documentation from Javadoc comments |
| `jshell` | Interactively evaluates Java expressions and code snippets |
| `jdb` | Debugs Java programs |
| `jcmd` | Sends diagnostic commands to a JVM process |
| `jstack` | Captures thread dumps to inspect thread states |
| `jmap` | Collects heap-related information |
| `jfr` | Works with Java Flight Recorder recordings |

The exact list of tools may vary across JDK vendors and versions. When you need to use a utility, check the `bin` directory of your installed JDK and the documentation for that specific version.

## 3. What is the JVM?

The JVM is an abstract computing machine specified to execute bytecode in the class file format. The JVM specification defines how class files are loaded, verified, and executed, as well as the runtime data areas that a program can use.

The JVM is not synonymous with the Java language. Several other languages can compile to Java bytecode and run on the JVM, provided that the bytecode and required libraries are compatible with that environment.

It is important to distinguish between **the JVM specification** and **a JVM implementation**:

- The specification describes the behavior that a compliant JVM must provide.
- An implementation is the actual software running on an operating system and hardware.
- HotSpot is a widely used JVM implementation. Other implementations also exist, each with its own optimization and operational choices.

The specification does not require every JVM to use the same garbage collection algorithm, the same memory layout, or the same JIT strategy. Therefore, details observed in one specific implementation are not always universal rules for every JVM.

## 4. How Does the JVM Execute a Program?

A typical Java program goes through the following sequence of steps:

1. **Writing source code:** the developer creates `.java` files.
2. **Compilation:** `javac` checks the source code and generates bytecode in `.class` files.
3. **Launching:** the `java` command locates the class or JAR to run and initializes the JVM.
4. **Class loading:** class loaders locate and load the required class definitions.
5. **Verification and linking:** the JVM verifies the validity of the class file, prepares class data, and resolves references as needed.
6. **Class initialization:** static initializers and static blocks are executed according to class initialization rules.
7. **Execution:** the execution engine interprets bytecode and may compile frequently executed code into machine code.
8. **Runtime management:** the JVM allocates memory, coordinates threads, and reclaims unreferenced objects according to the garbage collection policy.

Bytecode is not machine code specific to a single CPU. A compliant JVM on each platform is responsible for executing bytecode on that platform. This is the foundation of Java's portability, though an application can still depend on the operating system or architecture if it uses native libraries, system paths, or platform-specific behavior.

## 5. Main Components of the JVM

### 5.1. Class loader

The class loader is responsible for locating and loading classes into the JVM. Common built-in class loaders in modern Java include:

- **Bootstrap Class Loader:** loads core platform classes.
- **Platform Class Loader:** loads platform classes belonging to the appropriate modules.
- **Application Class Loader:** loads application classes from the classpath or module path as configured.

The delegation mechanism typically causes a class loader to ask its parent loader before attempting to locate a class itself. This mechanism helps prevent applications from accidentally replacing core platform classes. Applications can define custom class loaders for needs such as plugins or dynamic class loading; the exact behavior depends on the loader's design.

### 5.2. Linking and initialization

After a class is loaded, the JVM performs steps related to linking:

- **Verification:** checks the structure of the class file and bytecode safety constraints.
- **Preparation:** creates the necessary structures for the class and allocates storage for static variables with their default values.
- **Resolution:** transforms symbolic references into direct references that can be used directly. This can happen eagerly or lazily depending on the case.

Initialization executes the static initializers and corresponding static assignments. Class initialization occurs according to JVM rules, typically triggered by the first active use of the class. Therefore, the time a class is loaded and the time it is initialized do not necessarily coincide.

### 5.3. Runtime data areas

The JVM defines runtime data areas with different sharing scopes:

| Data Area | Scope | Role |
|---|---|---|
| Heap | Shared across threads | Stores objects and arrays allocated at runtime; managed by the garbage collector for reclamation |
| Java Virtual Machine Stack | Each thread has its own stack | Stores stack frames for method invocations |
| PC Register | Each thread has its own PC | Tracks the bytecode instruction currently being executed in the thread |
| Native Method Stack | Associated with a thread | Supports execution of native methods |
| Method Area | Shared across threads | Stores class structures, metadata, method code, and the runtime constant pool per the JVM model |

On each method invocation, the JVM creates a **stack frame** for that call. The frame holds information such as local variables, the operand stack, and data for dynamic linking or method completion. When the method finishes, its corresponding frame is popped from the stack.

The heap is where objects are typically allocated. Multiple threads can access the same object on the heap concurrently, so programs must use appropriate synchronization mechanisms when there is concurrent access and mutation of shared state.

**Method Area** is a concept in the JVM specification. The internal implementation depends on the JVM. For example, HotSpot has used **Metaspace** to store class metadata in native memory since Java 8; Metaspace is not a required memory area name in the JVM specification.

### 5.4. Execution engine

The execution engine is responsible for executing bytecode. Two key mechanisms are:

- **Interpreter:** reads and executes bytecode instruction by instruction. This mechanism allows the program to start running without compiling all code into machine code upfront.
- **JIT compiler (Just-In-Time compiler):** monitors frequently executed code paths and compiles them into machine code to improve performance. The JVM can apply optimizations based on runtime behavior and deoptimize when optimization assumptions no longer hold.

Because of the JIT compiler, a program's execution time can differ between startup and steady-state execution. A reliable performance measurement needs to account for warm-up, input data, and the execution environment.

### 5.5. Garbage collector

The garbage collector (GC) automatically reclaims memory occupied by objects that are no longer reachable by the program through valid reference paths. This reduces the need for manual memory deallocation, though it does not mean an application is immune to memory issues.

Key points to keep in mind:

- Objects that are still referenced can remain alive even if the application no longer needs them from a business logic perspective.
- Holding references longer than necessary can increase memory usage and lead to logical memory leaks.
- GC may pause some application threads depending on the collector and situation.
- Calling `System.gc()` is only a request for the JVM to consider running GC; there is no guarantee that GC will run immediately.

Collector names, heap partitioning, and configuration flags are implementation- and version-dependent details. When analyzing performance, consult the documentation for the JDK you are running and measure with appropriate tools rather than assuming every JVM behaves the same way.

### 5.6. Native interface

The JVM can interact with native code through mechanisms such as the Java Native Interface (JNI). This is how Java applications call libraries written in native languages or integrate with operating system components. Native code is useful in certain scenarios, but it can reduce portability and introduce additional risks around memory management, ABI compatibility, or process crashes.

## 6. Example: Compiling and Running a Java Program

Create a file named **Main.java** with the following content:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JDK");
    }
}
~~~

Open a terminal in the directory containing the file and check the tool versions:

~~~text
java --version
javac --version
~~~

Compile the source code:

~~~text
javac Main.java
~~~

If compilation succeeds, the current directory will now contain **Main.class** with the compiled bytecode. Run the class using the Java launcher:

~~~text
java Main
~~~

Stdout output:

~~~text
Hello from JDK
~~~

Here:

- `javac Main.java` is the compilation step provided by the JDK.
- `Main.class` contains bytecode, not CPU-specific machine code.
- `java Main` invokes the Java launcher, which initializes the JVM and instructs it to execute the `Main` class.
- The class name passed at runtime does not include the `.class` extension.

### Compiling into a separate directory

For small projects, it is good practice to separate source code from compiled bytecode output. Create an `out` directory if it does not already exist, then run:

~~~text
javac -d out Main.java
java -cp out Main
~~~

The `-d out` option specifies where to place the generated class files. The `-cp out` (or `-classpath out`) option tells the JVM where to find classes at runtime. For programs with packages, the output directory structure must mirror the package hierarchy; run the class using its fully qualified name, such as `com.example.Main`.

### Compiling for a target Java version

If you are using a newer JDK but want to generate bytecode and restrict APIs to Java 17, you can use:

~~~text
javac --release 17 -d out Main.java
~~~

The `--release` option instructs the compiler to compile against the specified platform version, including language level, class file format, and the corresponding public API set. It is more useful than simply setting a bytecode target flag, because the compiled code is also checked against the target version's APIs.

### Running a single source file directly

Since Java 11, the Java launcher supports source-file mode:

~~~text
java Main.java
~~~

This command lets you run a simple single source file without manually invoking `javac` first. For project build workflows, explicit compilation with `javac` or a build tool still provides better control over output and the classpath.

## 7. Distinguishing JDK, JRE, and JVM

| Concept | Question Answered | Components / Role |
|---|---|---|
| JDK | What is needed to develop Java applications? | Compiler, launcher, runtime, platform libraries, and development tools |
| JRE | What is needed to run Java applications? | Conceptual runtime environment consisting of the JVM, libraries, and supporting components |
| JVM | What executes bytecode? | Virtual machine that loads, verifies, and executes class files; manages runtime |

In the historical model commonly used for explanation, the JRE includes the JVM and runtime libraries, while the JDK includes the runtime environment plus development tools. This model remains useful for understanding roles, but it should not be used to assume how every vendor packages software today.

Since Java 9, the platform has been organized into modules. Many vendors no longer distribute standalone JRE installers in the traditional style for every release. A full JDK remains the convenient choice for development machines. When only a minimal runtime is needed for deployment, you can consider a custom runtime image created with the `jlink` tool, if your workflow and application support it.

## 8. Installing and Verifying the JDK Environment

After installing the JDK, verify both the compiler and the launcher:

~~~text
java --version
javac --version
~~~

Both commands should point to the installation appropriate for your project. If `java` runs but `javac` is not recognized, the machine may only have a runtime installed or the PATH variable may not point to the JDK's `bin` directory.

Common environment concepts:

- **JAVA_HOME:** typically points to the root directory of the JDK, such as `C:\Program Files\Java\jdk-17` on Windows or the corresponding JDK path on macOS/Linux. Do not set `JAVA_HOME` to point directly to the `bin` directory.
- **PATH:** should include the JDK's `bin` directory so you can invoke `java`, `javac`, and related tools from the terminal.
- **PATH and JAVA_HOME may be out of sync:** the terminal might find a different Java installation than the one your IDE or build tool is using.

On Windows, use `where.exe java` and `where.exe javac` to see which executables are found. On macOS/Linux, you can use `which -a java` and `which -a javac`. After changing environment variables, open a new terminal to verify again.

## 9. Common Errors and How to Fix Them

### `javac` is not recognized

**Common cause:** the JDK is not installed, or PATH does not include the JDK's `bin` directory.

**How to fix:** check the JDK installation directory, set JAVA_HOME to the root JDK directory, and add `%JAVA_HOME%\bin` on Windows or `$JAVA_HOME/bin` on macOS/Linux to PATH. Open a new terminal and run `javac --version`.

### `java` and `javac` have different versions

**Common cause:** PATH contains multiple Java installations, or the IDE/build tool uses a separate JDK.

**How to fix:** check the actual paths of both commands, then align the JDK used across your terminal, IDE, and build tools. Do not rely on the version output of only one command.

### `Could not find or load main class`

**Common cause:** the classpath does not include the directory or JAR containing the target class; the fully qualified class name does not match the package; or the run command uses the wrong class name.

**How to fix:** verify the output directory, package, and classpath. If compiled into `out`, try `java -cp out Main` for a class without a package, or use the fully qualified name such as `java -cp out com.example.Main`.

### `UnsupportedClassVersionError`

**Common cause:** the class file was compiled by a newer Java version than the JVM running it.

**How to fix:** upgrade the runtime version to be compatible, or recompile with `javac --release` targeting a Java version supported by the deployment environment.

### Works on development machine but fails on deployment machine

**Possible causes:** different JDK/JVM versions, missing modules or dependencies, different classpath, different OS/architecture, or missing native libraries.

**How to fix:** explicitly specify the target Java version, manage dependencies and build configuration consistently, and verify the actual runtime in the deployment environment. For applications using native code, also check native libraries and OS architecture.

## 10. Key Takeaways When Working with Java

- When you need to **compile** `.java` source code, use `javac` from the JDK.
- When you need to **launch** a class or JAR, use `java`; the launcher initializes the JVM.
- When you need to understand **how bytecode is executed and managed**, study the JVM, class loaders, runtime data areas, execution engine, and GC.
- When encountering version errors, check both the compiler and the runtime. The JDK version used to build and the JVM version used to run must be compatible with the class files and APIs the application requires.
- When deploying, clearly determine whether the application needs a full JDK or only an appropriate runtime.

The JDK provides the development toolkit and runtime environment; the JVM executes bytecode according to the Java platform specification. Understanding these two roles helps you grasp the full flow from source code to a running program, as well as isolate issues during compilation or application operation.