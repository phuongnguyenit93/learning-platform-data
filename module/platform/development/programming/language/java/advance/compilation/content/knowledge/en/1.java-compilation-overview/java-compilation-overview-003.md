# Roles of JDK, javac, JVM, and JIT

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **JDK** (the development kit), **`javac`** (the source code compiler), **JVM** (the virtual machine that executes bytecode), and **JIT** (the optimizing compiler at runtime).
- Trace a program from a `.java` file, through `.class`, to execution and, when applicable, machine code generation.
- Independently compile, run, inspect bytecode, and observe JVM hot compilation using tools in the JDK.
- Explain why "successful compilation" differs from "running successfully", and why JIT is not a mandatory step for every method.

## 1. The Big Picture

A typical Java workflow looks like:

```text
Developer
    |
    | writes PipelineDemo.java (source code)
    v
JDK: javac ── checks syntax, types, and semantics ──> PipelineDemo.class
                                                       (JVM bytecode)
                                                              |
                                                              | java -cp out PipelineDemo
                                                              v
                                            JVM loads, links, initializes classes
                                                              |
                                                              v
                                                     Executes bytecode
                                               (interpretation and/or JIT)
                                                              |
                                        +---------------------+---------------------+
                                        |                                           |
                                   Interprets                                 JIT compiles
                                    bytecode                                    hot code
                                        |                                           |
                                        +---------------------+---------------------+
                                                              |
                                                              v
                                                  CPU executes machine code
```

The diagram above illustrates that **the JDK is used for development and provides launch tools**, while **the JVM performs the work of running the program**. `javac` typically runs before application startup; JIT, if implemented and enabled by the JVM, operates while the program is running. A method may be interpreted first and then JIT-compiled; there are also methods that never become "hot" enough to be selected by the JIT.

| Component | Core Role | Typical Input / Output | When It Participates |
| --- | --- | --- | --- |
| **JDK** (Java Development Kit) | Distribution of Java development tools, including compiler, launcher, diagnostic tools, and runtime | `javac`, `java`, `jar`, `javap`, `jshell`, etc. | During development, packaging, inspection, and also when using the bundled runtime to run |
| **`javac`** | Compiles Java source code into bytecode with checks according to the Java language | `.java` → `.class` | Usually before running; can also be invoked indirectly by a build tool/IDE |
| **JVM** (Java Virtual Machine) | Loads, verifies, and executes class files according to the JVM model; manages runtime services | Class files/bytecode → execution behavior | Throughout the lifetime of the Java process |
| **JIT** (Just-In-Time compiler) | Compiles selected portions of bytecode into machine code to optimize runtime performance | Bytecode + runtime information → machine code of the current CPU architecture | While the JVM is running, depending on version/configuration/actual workload |

**Do not equate concepts with products.** The JVM is a specification/execution model; HotSpot is a popular JVM implementation in OpenJDK. Details such as C1, C2, threshold counters, or `-XX` flags are specific to certain HotSpot builds, not guarantees of every JVM.

## 2. JDK: Environment and Toolkit

The JDK provides what is needed to **build** Java programs. Common tools:

- `javac`: compiles Java files into class files.
- `java`: launcher that starts an application and creates a JVM for execution.
- `jar`: creates/reads JAR packages, which are an archive format storing multiple resources and class files.
- `javap`: inspects class information, member signatures, and bytecode instructions.
- `javadoc`: generates API documentation from source code and doc comments.
- `jshell`: interactive environment for quickly testing Java expressions/snippets.
- `jcmd`, `jstack`, `jmap`, `jfr`: tools supporting observation or diagnostics on JDKs that provide them.

Modern JDK releases typically include a **runtime to run applications**, including a JVM. Historically there was a separate "JRE" distribution; since Java 9 and the module system, runtime packaging changed, so you should not assume every machine has a separate JRE installation. Custom runtimes can be created with `jlink` when appropriate.

Check the environment:

```bash
java -version
javac -version
```

The two commands above may use two different installations if `PATH` is configured inconsistently. Check the actual paths of `java`/`javac` and `JAVA_HOME` (if the project uses this variable) to see which JDK the build tool/IDE is using. `JAVA_HOME` is a configuration convention of many tools, **not** a requirement of the Java language specification.

Note the differences:

- Having `java` without `javac`: the environment may provide only a runtime, or `PATH` points to the wrong JDK.
- Installing a new JDK does not automatically make all projects use the new version: IDEs, Gradle, Maven, and terminals can select their own toolchains.
- The name "JDK 21" refers to the tool distribution; "Java 21" can also refer to the language level, standard library, or runtime version. You need to identify which part is being discussed.

## 3. `javac`: Turning Source into Class Files

The following complete Java 17+ example uses simple math so that the result is verifiable.

Create the file **`PipelineDemo.java`**:

```java
public class PipelineDemo {
    static int square(int value) {
        return value * value;
    }

    public static void main(String[] args) {
        int total = 0;
        for (int i = 1; i <= 5; i++) {
            total += square(i);
        }
        System.out.println("Tong binh phuong = " + total);
    }
}
```

From the directory containing the file, run:

```bash
javac -d out PipelineDemo.java
java -cp out PipelineDemo
```

Exact standard output:

```text
Tong binh phuong = 55
```

Explanation:

1. `javac -d out PipelineDemo.java` parses the source code, checks it, and generates `out/PipelineDemo.class`. Depending on the operating system, the path separator character may differ.
2. `java -cp out PipelineDemo` tells the launcher to add `out` to the classpath and look for the class with binary name `PipelineDemo` containing the entry point `public static void main(String[] args)`.
3. The loop sums `1² + 2² + 3² + 4² + 5² = 55`. This is the logical result of the program, regardless of whether the method is JIT-compiled or interpreted.
4. After running, the class file is still bytecode. `java` launches the JVM to process it; the preceding `javac` step **does not directly produce** a native executable file for the CPU.

What does `javac` do conceptually?

- **Lexical and syntactic analysis:** recognizes tokens, statements, expressions, declarations, and program structure.
- **Name resolution and type/semantic checking:** checks, for example, whether variables/methods exist, types are compatible, calls are valid, access rules, checked exceptions, etc.
- **Annotation processing when appropriately configured:** annotation processors can generate additional source or resources. Regular annotations do not mean `javac` automatically generates arbitrary runtime behavior.
- **Class file generation:** creates the constant pool, class/method/field information, and bytecode instructions, along with required metadata.

Bytecode is an instruction set for the JVM, such as loading a value, invoking a method, adding two numbers, or returning. It is **not** x86-64/ARM64 machine code. This is one reason Java can distribute shared classes/JARs across multiple operating systems/CPUs, provided the target has a compatible JVM and dependencies.

### 3.1 Inspecting `javac` Output

```bash
javap -c -p -classpath out PipelineDemo
javap -verbose -classpath out PipelineDemo
```

`javap -c` displays the bytecode instructions of methods that have code. You can see instructions such as `iload`, `imul`, `iadd`, `invokestatic`, `invokevirtual`; actual instructions and offsets depend on how the compiler generates the class file. `javap -verbose` also displays metadata, the constant pool, and the class file format version. This is a **class file reading/disassembly** tool, not a JIT compiler.

For example, a class file using Java 17 level has `major version: 61`; Java 21 has `major version: 65`. That is the **class file format** version, not the version number of the CPU or JIT.

### 3.2 Language Version and Running on Different Runtimes

With JDK 21, you can generate class files using the API, language rules, and bytecode level compatible with Java 17:

```bash
javac --release 17 -d out PipelineDemo.java
java -cp out PipelineDemo
```

The `--release 17` flag, when using a supporting `javac`, restricts the language level, Java platform APIs, and class-file target to version 17. It has stronger semantics than just setting `-source` and `-target` without restricting standard APIs. Third-party libraries and deployment environments still need to be checked separately.

Compiling with JDK 21 **by default** does not guarantee it can run on JVM 17: the default class file target according to the JDK may be newer. When the target JVM encounters a higher major version than it supports, `UnsupportedClassVersionError` can occur.

### 3.3 Compilation Differs from Execution

`javac` can detect syntax errors, type errors, and missing symbols identifiable at compile time. It **cannot guarantee** that the program will never divide by 0, have no `NullPointerException`, have no network/file configuration errors, or achieve good performance. For example:

```java
public class RuntimeFailure {
    public static void main(String[] args) {
        int denominator = Integer.parseInt(args[0]);
        System.out.println(10 / denominator);
    }
}
```

```bash
javac -d out RuntimeFailure.java
java -cp out RuntimeFailure 0
```

Compilation is valid, yet when run with argument `0`, integer division causes `ArithmeticException: / by zero`. The full error message/stack trace may differ by JVM version. If run with no arguments, the program may throw `ArrayIndexOutOfBoundsException` before evaluating the division.

## 4. JVM: From Class Files to Runtime Behavior

The JVM executes bytecode semantics according to the specification. For a typical Java process, responsibilities can be divided as follows.

### 4.1 Loading, Linking, and Initializing Classes

- **Loading:** the class loader locates and defines a class from the classpath, module path, or other valid source. The class loader also determines part of a class's identity: the same binary name defined by different class loaders is not automatically the same class.
- **Linking:** includes **verification** (checking bytecode validity/safety according to JVM rules), **preparation** (preparing `static` fields with default values), and **resolution** (resolving symbolic references; parts are permitted to be deferred).
- **Initialization:** executes `static` variable initializers and `static` blocks according to JVM rules at the time the class is initialized. **Loading** a class does not mean all `static` initialization code has already run.

This is a conceptual model; implementations may perform certain operations in different orders/times as long as they adhere to specified semantics. The JVM does not necessarily load all classes of an application immediately at process startup.

### 4.2 Memory Model and Runtime Services

Several important runtime data areas:

| Component | Purpose |
| --- | --- |
| **Heap** | Stores objects and arrays allocated under the JVM model; where the garbage collector typically manages memory lifecycle. |
| **Per-thread JVM stack** | Stores frames for method invocations, including local variables and the operand stack at the virtual-machine level. |
| **Per-thread PC register** | Tracks the JVM instruction position of the currently executing method (with different limits/details for native methods). |
| **Method area** | Logical area containing per-class structures; HotSpot typically uses Metaspace to manage most class metadata. |
| **Native method stack / native memory** | Serves native code and off-heap structures; details depend on implementation. |

JVM services typically include bytecode execution, thread management, object allocation, exception handling, synchronization, and garbage collection support. **The JVM, the Java standard library, and the operating system are not the same thing**: the JVM provides the execution model; Java libraries provide APIs such as `String`, `Files`, and `Socket`; the operating system provides actual system resources.

Garbage collection typically runs automatically according to runtime algorithms, yet **does not guarantee** when an object is collected or when off-heap resources like files/sockets are closed. Use `try-with-resources` for resources that require controlled closing.

### 4.3 Interpreter: Running Bytecode Without JIT Yet

The JVM can execute bytecode via an interpreter. When an application first starts, much of the code lacks sufficient usage data for the JIT to decide how to optimize. Interpretation has the advantage of faster startup for some code and avoids having to natively compile parts that are rarely called.

JVMs can use multiple different execution techniques: interpreter, JIT, and even AOT models in some products/runtimes. Therefore, one should not say **every bytecode must go through the interpreter before running** or "every JVM has a JIT".

## 5. JIT: Compiling and Optimizing at Runtime

The JIT takes bytecode along with information observed while the program is running (profile), then generates **native machine code** for selected segments. That machine code is executed directly on the CPU of the machine running the JVM. JIT is part of the runtime execution mechanism; you normally **do not have to call JIT from Java code**.

A simple model:

```text
Bytecode starts executing
       |
       v
JVM records usage / runtime behavior (when supported)
       |
       +--> Rarely used: continue along the current execution path
       |
       +--> Selected for compilation: JIT optimizes and generates machine code
                                             |
                                             v
                                 Run the generated native code
                                             |
                         Optimization assumption no longer holds?
                                             |
                                             v
                                Deoptimization / re-execute
                             along a path matching the semantics
```

Factors worth understanding:

- **Hot code:** methods or loops called/iterated frequently enough for the JVM to see a compilation benefit. There is no single, fixed threshold across all versions and configurations.
- **Profiling:** the JVM can collect actual object types, branch frequencies, call targets, etc., to optimize based on observed behavior.
- **Inlining:** inserts the logic of a called method into the call site when beneficial, reducing call overhead and opening further optimization opportunities.
- **Other optimizations:** eliminating redundant computations, dead-code elimination, escape analysis/scalar replacement under suitable conditions; do not assume every optimization always happens.
- **Deoptimization:** if an assumption used for optimized code no longer holds, the JVM can fall back to another execution form, preserving Java semantics.
- **Warm-up:** benchmark results of initial runs may differ after profiling/JIT stabilizes. JIT also consumes CPU and memory for the compilation process, so it is not free.

### 5.1 Tiered Compilation in HotSpot

In common HotSpot configurations, **tiered compilation** combines the interpreter with compilation levels to balance startup speed, profiling cost, and long-term performance. Two compilers often mentioned are **C1** (client compiler) and **C2** (server compiler). C1 can generate code quickly and gather profiling; C2 puts more effort into optimization at appropriate levels.

This is a description of the HotSpot implementation, **not mandatory JVM specification terminology**. Modes, compilation tiers, compilers, and algorithms can change across JDK releases, configuration flags, hardware, and JVM vendors.

### 5.2 Observing JIT, Without Guessing from a Single Run

Create the file **`JitDemo.java`**:

```java
public class JitDemo {
    static long work(int count) {
        long sum = 0;
        for (int i = 0; i < count; i++) {
            sum += i % 7;
        }
        return sum;
    }

    public static void main(String[] args) {
        long result = 0;
        for (int round = 0; round < 10_000; round++) {
            result += work(1_000);
        }
        System.out.println("Result = " + result);
    }
}
```

```bash
javac -d out JitDemo.java
java -cp out JitDemo
```

Standard output during normal execution:

```text
Result = 29970000
```

Each call to `work(1000)` sums to `2997`; calling it 10,000 times yields `29,970,000`. Runtime optimization algorithms are not allowed to alter the observable result according to the example's semantics.

On **HotSpot** supporting the corresponding options, try:

```bash
java -Xint -cp out JitDemo
java -XX:+PrintCompilation -cp out JitDemo
```

- `-Xint` requests running in interpreter-only mode on HotSpot. This is a way to compare execution paths, **not a standard benchmark** of Java performance.
- `-XX:+PrintCompilation` requests printing information about methods compiled by the runtime. You may see the name `JitDemo::work`, yet that **is not guaranteed** across every run/configuration; the log also contains internal JDK/JVM activity, and order and timing are not fixed.
- When `PrintCompilation` is enabled, stdout includes many diagnostic lines in addition to `Result = 29970000`; do not use the entire log as fixed output for testing.
- `-XX` flags are implementation-specific and may not exist or may change on other JVMs. Check the help/documentation of the runtime version you are using.

To measure actual throughput/latency, use a representative workload and controlled measurement methodology (for example, the **JMH** harness), accounting for warm-up, fork count, GC, CPU, environmental variance, and avoiding letting the optimizer eliminate unobserved work. **Do not deduce "JIT is N times faster" from just two single runs.**

## 6. Relationship Between Compile-Time, Load-Time, and Run-Time

Three points in time explain many practical issues:

| Phase | Typical Tools/Mechanisms | Typical Issues |
| --- | --- | --- |
| **Compile-time** | `javac`, annotation processors, compiler classpath dependencies | Syntax errors; type errors; missing compile-time dependencies; APIs unavailable under the selected `--release` |
| **Load/link/initialize-time** | JVM class loaders, verifier, linker, class initializers | Missing class at runtime; unsupported class version; verification errors; `static` initialization failure |
| **Run-time** | JVM interpreter/JIT, GC, libraries, OS | Invalid input data; exceptions; timeouts; I/O errors; memory pressure; varying performance |

**Compile-time and runtime classpaths can differ.** Compiling successfully when a library is found does not mean the JVM will also find it at runtime. For applications with packages, the directory layout and main class name must match the binary name of the class. For example, `com.example.Main` must be invoked by its fully qualified name if the class is declared in package `com.example`.

**Error types must be read according to cause.** `ClassNotFoundException` is a checked exception that can arise from certain dynamic class-loading APIs; `NoClassDefFoundError` typically occurs when the JVM needs a class definition that was present at compile time but cannot be found/initialized properly at runtime. They are not completely interchangeable.

**Runtime compatibility is not just the major version.** The runtime needs sufficient class/library/native dependencies, OS permissions, configuration, module access, and supporting environment. A `.class` compatible in version can still fail at runtime due to other conditions.

## 7. Common Situations

### "Why do I still get `java: command not found` or `javac is not recognized` even though a JDK is installed?"

The JDK may already be installed, yet the path to the `bin` directory is not in the current shell's `PATH`; the shell/IDE may also not have refreshed its environment. Check the actual versions and paths of `java`, `javac`, and `JAVA_HOME` and configure them consistently. This error is an environment configuration issue and says nothing about the correctness of the source code.

### "`javac` finished running, yet `java PipelineDemo` reports class not found?"

In the example `-d out` was used, so the class file is in `out`. Runtime requires `java -cp out PipelineDemo`. Do not pass the file name `PipelineDemo.class` to the launcher in class-name execution mode. The package name, classpath/module path, and main class name must also be exact.

### "Do I have to recompile with `javac` every time I run?"

No. If suitable classes/JARs already exist, the JVM can run those artifacts. However, the JIT usually has to regenerate machine code for a **new JVM process**; native code generated by JIT does not automatically replace `.class` files on disk. The JVM/JDK has other sharing/startup-improvement techniques, yet these should not be conflated with turning source code into a permanent native file.

### "Does JIT run before `main`?"

JIT is a runtime activity. The JVM and libraries can execute, initialize, or compile some code before the application's `main` body starts; therefore, the statement "JIT only runs after the first line of `main`" is oversimplified. However, the `javac` file-compilation step in the workflow above is still an independent step before starting the Java process.

### "With `java Hello.java`, is `javac` no longer necessary?"

Since Java 11, the launcher has **source-file mode**, for example `java PipelineDemo.java` with appropriate source. The launcher can compile source in memory and then run it in the JVM. That does not turn the JVM into a direct line-by-line reader of Java source statements, nor does it turn JIT into a Java source compiler. This mode is convenient for small programs; for projects with multiple files, packages, dependencies, and reproducible builds, a multi-step build pipeline is still usually clearer.

### "Is Java always slower than native because it has to interpret?"

No general conclusion can be drawn. JIT can optimize according to runtime data; performance also depends on algorithms, allocation, GC, I/O, warm-up, configuration, and hardware. Some Java workloads perform very well, while others are constrained by startup, memory, or the execution model. To draw a conclusion, measure the actual workload.

### "Once JIT turns bytecode into native code, does it ignore Java rules?"

No. Optimizations must preserve observable behavior according to Java semantics, including exception-handling rules, synchronization, and the memory model. JIT may reorder/change computations when valid, yet must not arbitrarily change results or cause the program to violate semantic constraints.

## 8. Self-Practice Checklist

1. Run `java -version` and `javac -version`; identify the actual version and JDK used by the terminal.
2. Create `PipelineDemo.java`, compile with `javac -d out ...`, run with `java -cp out PipelineDemo`, and verify the line `Tong binh phuong = 55`.
3. Use `javap -c -p -classpath out PipelineDemo`, identify the instruction calling `square` and the multiplication; distinguish it from Java source and machine code.
4. If you have JDK 21, recompile with `--release 17` and check the class file's major version; explain why an older runtime may reject a newer class file.
5. Run `JitDemo` normally and then try `-Xint` and `-XX:+PrintCompilation` on HotSpot; observe the difference between **execution path/diagnostic logs** and **result value**.

## 9. Self-Check Knowledge

**Question 1.** Does `javac` generate x86-64 machine code for the CPU to run directly from a `.class` file?

**Answer:** No. `javac` normally generates bytecode in the class file format; the JVM/runtime remains responsible for execution, which may use an interpreter or JIT.

**Question 2.** Why can source code that compiled still encounter `NoClassDefFoundError` at runtime?

**Answer:** Runtime dependencies/classpath or class loading/initialization conditions may differ from compile-time; a valid class file does not guarantee sufficient dependencies at launch.

**Question 3.** Why might a method in a very short program not be JIT-compiled?

**Answer:** The JVM may find that the compilation cost does not outweigh the benefit or lacks sufficient information/profile; many runtimes can execute the method with an interpreter.

**Question 4.** When do you use `javap` and when do you use `-XX:+PrintCompilation`?

**Answer:** `javap` analyzes static class files/bytecode. `PrintCompilation` is a HotSpot diagnostic flag indicating runtime native compilation activity, with logs varying by run and configuration.

**Question 5.** What is wrong with the statement "JDK = javac = JVM = JIT"?

**Answer:** JDK is the toolkit/distribution; `javac` is the compiler turning source into bytecode; JVM is the bytecode execution model/environment; JIT is a runtime optimization mechanism that may reside within a specific JVM.

## Conclusion

Remember the right chain of responsibilities: **JDK provides the tools → `javac` produces bytecode → JVM loads and executes → JIT can optimize selected parts into machine code at runtime**. The decisive distinction is that **compiling source into bytecode occurs at compile-time**, whereas **JIT compiling bytecode into machine code occurs at runtime**. Understanding this boundary helps you configure the JDK, read build/runtime errors, and evaluate Java performance accurately.