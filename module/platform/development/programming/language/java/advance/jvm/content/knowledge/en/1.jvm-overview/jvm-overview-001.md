# What is the JVM and why does Java need an intermediate execution machine?

## 1. The problem Java needs to solve

A computer ultimately executes **machine instructions** tailored to the CPU architecture and operating system. A program written in Java, however, is represented as source code (`.java`), a form that humans can read and compile. If source code were compiled into machine instructions specific to each system, developers would have to build and distribute different executables for multiple environments.

Java chooses a model with an **intermediate execution layer**:

```text
Java source code (.java)
          |
          | javac (JDK compiler)
          v
Java bytecode (.class, can be packaged in .jar)
          |
          | Compatible JVM: class loading → verification → execution
          v
Machine instructions running on CPU and OS services
```

A program is compiled once into **bytecode**, which is an instruction set for the *Java virtual machine* rather than directly for a specific CPU. Each platform needs a suitable JVM implementation; that JVM implementation handles executing bytecode on its platform. This is the basis of the idea **“write once, run anywhere”**.

The key point: the JVM helps decouple **compiled program code** from **the execution details of each system**. This portability is conditional: the target environment must provide a JVM compatible with the bytecode version and the libraries that the application requires.

## 2. What is the JVM actually?

The **JVM (Java Virtual Machine)** is an abstract computing model specified to load, verify, and execute Java class files (`.class`). A **JVM implementation** is the software that realizes that model, working alongside the real operating system and hardware. For example, **HotSpot** is a popular JVM implementation in OpenJDK distributions; not every JVM uses the same JIT compiler or the same memory management algorithms.

Three layers should be distinguished:

| Component | Role | Example |
| --- | --- | --- |
| **Java language** | Rules for writing source code: types, syntax, classes, expressions… | `class`, `interface`, `try` |
| **Bytecode / class format** | Compiled code form for the JVM and format carrying type, method, constant information… | `Hello.class` |
| **JVM** | Execution environment for compiled classes according to the JVM specification | HotSpot, OpenJ9 |

The JVM is **not** the `javac` source compiler, **not** the operating system itself, and **not** the entire Java ecosystem. It is a central runtime component. Also because bytecode is the execution interface, some other languages such as Kotlin or Scala can compile into code that runs on the JVM.

A more concrete description: when running `java TenLop`, the Java launcher sets up the environment and initializes an appropriate JVM, the JVM loads the necessary classes, and then executes the program entry point (usually the `main` method). A typical Java process has one running JVM, but one should not think that “each Java object is a virtual machine” or that every system only has a single JVM.

## 3. Why is an intermediate execution machine needed?

### 3.1. Portability across platforms

A valid `.class` file contains bytecode instructions, not x86-64 or ARM64 instruction sets directly for a specific CPU. A JVM on Windows, Linux, or macOS can understand the same format when version and library requirements are met. Developers usually do not have to recompile Java code for each operating system just because CPUs differ.

**However, “run anywhere” is not an absolute promise.** A program can still depend on file paths, permissions, environment variables, native libraries via JNI, graphical user interfaces, time/locale configurations, or APIs available only on one operating system. A class compiled for a newer Java version may not run on an older JVM.

### 3.2. A unified execution contract

The JVM specification defines the class file format, bytecode instruction set, runtime data areas, class loading and linking mechanisms, and many execution rules. As a result, the compiler and the runtime have a clear contract: the compiler produces valid bytecode, and the JVM implements the meaning of the bytecode.

The intermediate layer also enables bytecode analysis tools, testing, performance profiling, error monitoring, and other JVM languages to work on a common platform.

### 3.3. Runtime optimization

A modern JVM can start executing bytecode using an **interpreter** and then use a **JIT compiler** (*Just-In-Time*) to translate frequently executed code into machine code suited to the current CPU. The runtime can collect information while the program is running to make optimization decisions, such as inlining method calls under appropriate conditions.

Depending on the JVM and configuration, execution strategies may vary; **not all bytecode is required to be JIT-compiled**. Optimization decisions can be changed or reverted when runtime assumptions no longer hold (*deoptimization*).

### 3.4. Common runtime management

The JVM provides foundational mechanisms so applications can operate more consistently:

- **Class loading and linking:** finding, verifying, preparing, and using class definitions when needed.
- **Memory management:** allocating objects and coordinating *garbage collection* in common JVMs.
- **Method, exception, and thread execution:** maintaining execution context, call stacks, exception handling, and coordinating with the operating system.
- **Bytecode verification:** helping prevent many kinds of malformed class code or type constraint violations from being executed.

These mechanisms do not mean that the JVM automatically prevents all bugs, native resource leaks, or security vulnerabilities in an application.

## 4. How does the JVM participate in the program lifecycle?

The process can be divided into two different times.

**Compile time** (before running):

1. The programmer writes `.java` files.
2. The `javac` compiler parses the source code, checks types according to the Java language, and generates `.class` files.
3. Classes can be packaged in a JAR for distribution. A JAR is essentially an archive file; **it is not the JVM**.

**Runtime**:

1. The `java` launcher sets up the classpath/modulepath and starts the runtime.
2. The **class loader** loads the required classes. Not all classes in an application are necessarily loaded immediately at startup.
3. The JVM **links** classes: verifies bytecode (`verification`), prepares data structures (`preparation`), and resolves symbolic references (`resolution`, which can be deferred within specification limits).
4. The JVM **initializes** classes when the corresponding conditions occur, including executing the necessary static initializers.
5. The runtime executes bytecode using the appropriate mechanism of the JVM implementation (interpretation, JIT compilation, or a combination), calling OS services when needed.
6. During execution, the runtime manages objects, call stacks, exceptions, and coordinates with the operating system. When the program ends, process resources are released according to OS mechanisms.

Simplified model:

```text
                    +---------------------------------------+
.class  ----------> | Running JVM                           |
                    |  Class loading and bytecode checking  |
                    |  Runtime data areas                   |
                    |  Interpreter / JIT (JVM-dependent)    |
                    |  Garbage collector (JVM-dependent)    |
                    +-------------------+-------------------+
                                        |
                                        v
                          Operating System + Real CPU
```

The diagram above is a conceptual model. It does not mean the class loader, JIT, and garbage collector always run in a fixed sequential order; many activities are performed on demand or concurrently.

## 5. Java 17+ example: same program, JVM executes bytecode

Create the file **`BytecodeDemo.java`**:

```java
public class BytecodeDemo {
    public static int sum(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(sum(2, 3));
    }
}
```

In a terminal with JDK 17 or later, navigate to the directory containing the file and run:

```bash
javac BytecodeDemo.java
java BytecodeDemo
```

**Standard output of `java BytecodeDemo`:**

```text
5
```

The `javac` command creates **`BytecodeDemo.class`**. The `java` command launches the program on the JVM; there is no need to recompile from `.java` on every run if the class is still suitable.

Use the JDK's `javap` tool to inspect the bytecode:

```bash
javap -c BytecodeDemo
```

In the `sum(int, int)` method section, there will be output equivalent to the following (other parts of the `javap` output omitted):

```text
public static int sum(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

Meaning:

- `iload_0` and `iload_1`: push the two `int` arguments onto the operand stack.
- `iadd`: add the two `int` integers on the stack.
- `ireturn`: return the `int` result to the calling method.

These are **JVM bytecode instructions**, not assembly instructions specific to an x86 or ARM CPU. Other bytecode instructions in `main` invoke `sum` and print the result. A compatible JVM assigns a consistent meaning to these opcodes, even though how they are translated into machine instructions may differ by environment.

**Inspecting the runtime version yourself:**

```bash
java -version
javac -version
```

The output depends on the installed JDK/JVM, so there is no single fixed version string applicable to every machine. If a machine only has a runtime environment without compiler tools, a properly compiled class file can be run without `javac` in the target environment.

### Do not confuse the three forms of execution

| Command | Primary input | What happens |
| --- | --- | --- |
| `javac BytecodeDemo.java` | Java source code | Compiles to `BytecodeDemo.class` bytecode; does not run `main` |
| `java BytecodeDemo` | Class available on classpath | Launches the JVM and executes the program |
| `javap -c BytecodeDemo` | Compiled class | Analyzes/displays bytecode; does not execute `main` |

Some Java versions also support running a source file directly with `java File.java`. This is a convenience feature of the launcher; essentially there is still a compilation step and appropriate bytecode execution mechanism, which does not negate the role of the JVM.

## 6. What happens in JVM memory?

The JVM specification describes the main **runtime data areas**; physical allocation and optimizations belong to each implementation.

| Data area | Basic meaning |
| --- | --- |
| **Heap** | Stores objects and arrays; typically shared among threads of the same JVM, and is the target managed by the garbage collector |
| **Java Virtual Machine Stack** | Each thread has a stack consisting of *frames* for each Java method call, containing local variables, an operand stack, and related execution data |
| **PC register** | Each thread has a program counter associated with the JVM instruction currently being executed (for native methods, the state is specified differently) |
| **Method area** | Logical shared area for class structures such as method data and runtime information; implementation depends on the JVM |
| **Native method stack** | Supports native method calls if the JVM implementation uses this stack mechanism |

In HotSpot, **Metaspace** is an important implementation mechanism for class metadata, but the entire *method area* concept in the specification should not be equated with every detail of Metaspace.

For example, when `main` calls `sum(2, 3)`:

1. The JVM creates/contextualizes the frame corresponding to the `sum` call on the thread's stack.
2. The two parameters `a` and `b` are manipulated via the frame's local variables and operand stack.
3. The `iadd` instruction computes the result; `ireturn` ends the call and returns the value to the caller.
4. If a method creates an object with `new`, the object typically resides on the heap; the runtime may optimize allocation under specific conditions.

**Garbage collection** helps reclaim heap memory for objects that are no longer reachable according to the corresponding mechanism; it **does not replace** `close()` for files, network connections, locks, or resources that need to be closed deterministically. Therefore, applications still need `try-with-resources` when using appropriate resource types.

## 7. JVM, runtime environment, and JDK at an overview level

When saying “Java needs to be installed to run the program”, one must determine **whether development tools or only the runtime are needed**. A brief distinction:

| Component | Role in the `BytecodeDemo` example |
| --- | --- |
| **JVM** | Loads, verifies, and executes `BytecodeDemo.class` |
| **Runtime environment / JRE** | The JVM together with the libraries/modules needed to run; does not necessarily include a compiler |
| **JDK** | Provides the runtime along with `javac`, `java`, `javap`, `jar`, and development tools |

In modern Java, applications can be deployed with a full JDK or a trimmed **runtime image** using `jlink`; many vendors do not provide a separate JRE installer like in the Java 8 era. This difference affects installer and tool selection, **without changing the definition of the JVM**. The next article focuses on systematizing the terms **Java language, Java SE, JVM, JDK, and runtime environment**.

## 8. Compatibility and important limitations

**Version compatibility:** class files have a format version. For example, compiling with a newer JDK using default settings may produce classes that do not run on an older Java version, leading to errors such as `UnsupportedClassVersionError`. When Java 17 must be supported and using a JDK that supports this target, you can compile with:

```bash
javac --release 17 BytecodeDemo.java
```

Depending on the source code and libraries used, the `--release 17` option sets the language level, class format, and standard API surface according to Java 17. It **does not** automatically guarantee that all third-party dependencies or native libraries will run on the target environment; actual testing is still required.

**Platform independence does not guarantee identical environment behavior:** the operating system, file system, timezone, locale, permissions, machine resources, and native libraries can cause application results to differ.

**Performance involves trade-offs:** the JVM provides dynamic optimization capabilities and rich runtime mechanisms, but typically requires startup time, “warm-up” time, and memory for the runtime itself. The interpreter and JIT can work together to balance startup speed with long-term performance. One cannot conclude that “Java is always slow” or “JIT is always faster than every compilation approach” without specific workloads and measurements.

**Do not conflate with all ways of running Java programs:** some tools can produce a *native executable* via ahead-of-time compilation. That is a different deployment model compared to running class files on a standard JVM; this does not change the definition of “what the JVM is”.

**Do not misunderstand protection mechanisms:** the bytecode verifier checks many structural and type rules of class files, but cannot guarantee that an application has no logic flaws, improper data access permissions, or dependencies on insecure libraries.

## 9. Common misconceptions

1. **“The JVM reads `.java` code directly.”** In the standard flow, `javac` creates `.class` first; the JVM executes bytecode. Single-step source execution mode may hide the compilation step.
2. **“Bytecode is CPU machine code.”** Bytecode defines instructions for the JVM; the runtime must interpret or translate them using the appropriate mechanism of its implementation.
3. **“A class can run on any JVM.”** The right class file version, APIs, libraries, and environment conditions are required.
4. **“The JVM is just the JIT.”** JIT is an execution/optimization technique; the JVM also handles class loading, verification, runtime management, memory, exceptions…
5. **“With GC, resource leaks are impossible.”** GC does not release all resources outside the heap at the time the application needs; references held for too long can also cause unwanted memory consumption.
6. **“JDK and JVM are the same thing.”** The JDK includes development tools and the runtime; the JVM is the execution component.
7. **“The JVM guarantees uniform performance and behavior on every machine.”** The specification creates a semantic contract, while performance and certain environmental factors depend on the implementation/platform.

## 10. Self-check questions

**Question 1.** Why can the same `BytecodeDemo.class` run on multiple different CPUs?

Because the class contains bytecode according to the JVM specification; each platform has a compatible JVM responsible for executing it on that platform's CPU. Bytecode version and application dependencies must also be satisfied.

**Question 2.** Do `javac` and the JIT compiler do the same job?

No. `javac` translates Java source code into bytecode before runtime; the JIT of some JVMs translates part of the bytecode into machine code while the program is executing, based on runtime strategies.

**Question 3.** If there is already a garbage collector, can `try-with-resources` be omitted when reading files?

No. The garbage collector manages object memory, whereas files and operating system resources need to be closed promptly using mechanisms such as `try-with-resources`.

**Question 4.** Is the JVM the entirety of “Java”?

No. Java consists of the language, libraries, development tools, class file standard, and runtime. The JVM is the bytecode execution layer at the center of that model.

## Conclusion

The JVM is an **intermediate execution machine** sitting between Java bytecode and the real platform. The compiler produces class files according to a shared contract; a compatible JVM loads, verifies, executes, and manages runtime operations on each system. This separation forms the foundation for Java's portability, while enabling runtime optimization and providing a consistent execution environment. When designing or deploying applications, always also consider **version compatibility, libraries, environment, and actual performance measurement**.

### Further reading

- [The Java Virtual Machine Specification (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html) — class file model, instruction set, runtime data areas, and class loading/linking/initialization lifecycle.
- [Java `javac` documentation (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — Java compiler tool, including the `--release` option.
- [Java `javap` documentation (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html) — inspecting information and bytecode in class files.
