# Path of a Java Program: Source Code → javac → .class → JVM → Machine Code

When writing a Java program, the CPU **does not directly execute the `.java` file**. In the standard workflow, the `javac` compiler transforms source code into **Java bytecode** inside a `.class` file; at launch, the JVM loads and verifies the classes, then executes the bytecode using an interpreter and/or JIT compilation into **machine instructions for the current CPU**. This is why the same `.class` file can run on different operating systems and processors, provided there is a compatible JVM and appropriate dependencies.

```text
Hello.java (Java source code)
       │ javac: parsing + type checking + bytecode generation
       ▼
Hello.class (JVM bytecode, not yet x86/ARM machine code)
       │ java: starts JVM and locates the main class
       ▼
JVM: Class Loading → Verification/Linking → Initialization when needed
       │
       ├── Interpreter: reads and executes each bytecode instruction
       └── JIT: compiles selected code into machine code, possibly with optimizations
                    │
                    ▼
       Machine code + JVM libraries/runtime
                    │
                    ▼
           Operating system / CPU executes
```

The diagram is a **mental model**; it does not mean every class is loaded immediately at startup, every bytecode is always interpreted before JIT, or every method is compiled by JIT. The specific strategy depends on the JVM version and implementation.

## 1. Distinguishing Source Code, Bytecode, and Machine Code

| Layer | Representation | Who processes it? | Meaning |
| --- | --- | --- | --- |
| Source code | `.java`, human-readable Java syntax | `javac` or another compilation tool | Defines classes, methods, and program rules |
| Bytecode | `.class` in the JVM Class File format | JVM (class loader, verifier, interpreter/JIT) | Abstract instruction set, largely independent of CPU architecture |
| Machine code | Native instructions suitable for x86-64, AArch64, ... | CPU, with support from the OS/runtime | Instructions actually executed by the processor |

- `.class` **is not** the final machine translation for an OS/CPU. A class file contains the constant pool, class/method/field metadata, and `Code` bytecode sections for methods that have code; `abstract` or `native` methods do not have a bytecode section like regular Java methods.
- The JVM is built specifically for the target platform, and the JVM itself is a native program. Even when running bytecode with the interpreter, the CPU is still executing **the interpreter's machine code** to interpret the bytecode instructions.
- The “write once, run anywhere” capability depends on **the class file version, available APIs/runtime, external libraries, and platform-dependent behavior**. Code that uses native libraries or assumes OS-specific paths/features may still not be portable.

### JDK, JVM, and the `java` Command

The **JDK** (Java Development Kit) provides development tools such as `javac`, `java`, `javap`, packaging tools, and a Java runtime. The **JVM** is the virtual machine that executes class files; the runtime also includes the Java standard libraries. `javac` and `java` are **two tools with different roles**: `javac` produces bytecode, while the `java` launcher sets up the runtime/JVM and executes the program.

```bash
javac --version
java --version
```

Both commands should come from the same intended JDK environment. If `PATH` is configured to point to two different versions, compatibility errors may occur even if the source code compiled successfully.

## 2. Runnable Example: Going from `.java` to `.class`

Create the file **`Hello.java`** (the file name must match `public class Hello`):

```java
public class Hello {
    public static void main(String[] args) {
        int left = 20;
        int right = 22;
        int sum = left + right;
        System.out.println("Result: " + sum);
    }
}
```

In a terminal with JDK 17 or later, from the directory containing `Hello.java`:

```bash
mkdir out
javac -encoding UTF-8 -d out Hello.java
java -cp out Hello
```

Expected output:

```text
Result: 42
```

Step-by-step explanation:

1. `mkdir out` creates the directory for compilation outputs; depending on the OS/shell command, an equivalent way to create a directory can be used.
2. `javac -encoding UTF-8 -d out Hello.java` reads the source code, parses syntax, checks language/type rules, and generates **`out/Hello.class`**. Depending on the source code, additional class files for other classes may be generated; this example only needs `Hello.class`.
3. `java -cp out Hello` puts `out` on the classpath, looks up the class name **`Hello`**, starts the runtime, and invokes `public static void main(String[] args)`. The argument `Hello` is the **class name**, not `Hello.class` or a path to the `.java` file.
4. The JVM and standard libraries execute `main`; `System.out.println` writes the result line to standard output. Printing to the screen ultimately goes through runtime/OS facilities.

If `package com.example;` is declared, the file is typically placed to match the package, the output resides at `out/com/example/Hello.class`, and the run command is `java -cp out com.example.Hello`. This is the **fully qualified class name**; the classpath directory is the **root of the package tree**, not the innermost directory containing `Hello.class`.

### Inspecting Real Bytecode with `javap`

```bash
javap -classpath out -c Hello
```

The `javap` tool disassembles class file information and displays bytecode. In the `main` method, this example typically has operations equivalent to: pushing integers onto the operand stack, storing/loading local variables, using **`iadd`** to add, getting `System.out`, and calling `println`. Java 17 may represent string concatenation via **`invokedynamic`**. Offset numbers, constant-pool indices, and how each expression is compiled are **compiler output details**: inspect the actual output from `javap` rather than memorizing a hypothetical listing.

`javap -c` shows **bytecode**, and does not prove what shape the JIT machine instructions will take; the JIT is free to optimize or eliminate intermediate operations as long as required semantics are preserved.

## 3. What Does `javac` Do at Compile Time?

Simply put, the compiler performs the following sequence of tasks:

1. **Reading and parsing:** turns character streams/tokens into a program structure and checks for valid syntax.
2. **Name resolution and semantic/type checking:** resolves classes, variables, overloads, access permissions, return types, assignments, and language rules. If invalid, `javac` reports an error and does not produce a valid class file for the erroneous part.
3. **Transforming high-level constructs:** many Java features such as `for-each` loops, generics (type erasure), lambdas, or string concatenation are lowered into appropriate bytecode and metadata. Some features may use `invokedynamic` instead of simulating everything with simple instruction sequences.
4. **Generating class files:** emits the constant pool, descriptors, bytecode, and attributes needed for runtime. The file format has a **major version** so the JVM knows whether the class file is compatible.

For example, `javac` catches type errors such as assigning a `String` to an `int`, but it cannot predict every runtime error: division by zero, out-of-bounds array access, network failures, or a missing class at runtime may only surface later.

**Note:** `javac` checks and **JVM bytecode verification** are two separate steps. `javac` validates the source program, whereas the JVM checks bytecode structural validity/safety when loading/linking a class, including class files not generated by `javac`.

## 4. When Running `java -cp out Hello`, What Does the JVM Do?

### 4.1. Startup and Class Loading

The `java` launcher determines the launch mode (main class, JAR, module, or source-file mode), JVM configuration, classpath/module path, and arguments. The JVM initializes the essential runtime and uses the class loader system to locate class definitions when needed.

- The **bootstrap class loader** is responsible for core platform classes.
- The **platform class loader** and **application/system class loader** serve other platform class groups and application classes, depending on configuration/modules.
- Class loading delegation generally favors permitted definitions in parent loaders; custom class loaders may exist for plugins, containers, or frameworks.

Loading brings a **class definition** from a class file or another source into the runtime. Merely placing a `.class` file on disk does not mean the JVM has loaded it. Loading/lazy linking may happen while the program is already running.

### 4.2. Linking: Verification, Preparation, Resolution

According to the JVM class lifecycle model:

- **Verification:** checks that the class file/bytecode conforms to required structural and type constraints; failures may result in `VerifyError`.
- **Preparation:** allocates and assigns **default values** to the class's static fields (for example `0` for `int`, `null` for references). This is not yet when all static initialization statements in Java code are executed.
- **Resolution:** turns symbolic references in the constant pool into concrete runtime references when needed; resolution may be performed lazily and does not have to process everything before `main`.

Loading, linking, and initialization are distinct concepts; do not lump them all together as “the JVM reads the class and runs it right away”.

### 4.3. Initialization and Invoking `main`

When a class is actively used under conditions specified by JVM rules, the JVM performs **class initialization**: static field initializers and `static { ... }` blocks run in their respective order in the class, via the bytecode-level class initialization method (`<clinit>`, when present). Only after the required initialization conditions are met does the runtime execute the relevant program code.

In the `Hello` example, the entry point is `main(String[] args)`. The JVM sets up the execution thread and stack frames to run the method; it may then call methods in the standard library and application code.

## 5. From Bytecode to Machine Instructions: Interpreter and JIT

Bytecode consists of instructions such as `iload`, `istore`, `iadd`, `invokevirtual`, and `return`. They operate on the JVM's **stack-based model** (operand stack, local variables, frame), rather than directly being register instructions of a specific CPU.

**Interpreter:** the runtime can read a method's bytecode instructions one by one and perform the corresponding behavior. This allows execution to start quickly without needing dedicated native compilation for that method, at the cost of some instruction-interpretation overhead.

**JIT (Just-In-Time compiler):** when the runtime observes code segments that would benefit from optimization, the JIT can translate bytecode into **machine code for the current CPU**, store it in code memory, and reuse it for subsequent executions. HotSpot commonly uses **tiered compilation** combining execution profiling with compilers such as C1/C2; this is a detail of one popular JVM, **not a universal guarantee across all JVMs**.

Example of how the mechanism can unfold:

```text
main() calls calculate() many times
        │
        ├── Initially: interpreter and/or fast-code tier
        ├── JVM observes call counts, frequent branches, actual object types
        ├── JIT generates optimized machine code for calculate()
        └── Subsequent calls can execute the compiled machine code
```

The JIT can **inline** calls, optimize loops, eliminate redundant checks when proven safe, and leverage profiling. If an optimization assumption no longer holds, the runtime can **deoptimize** to return to an appropriate execution state. One must not assume that “first call of a method = interpreter, second call = JIT”; thresholds and strategies depend on the JVM, options, and program characteristics.

The CPU ultimately executes native code of the JVM/interpreter, JIT-generated code (if any), runtime code, and native libraries. **Machine code is not written out as an `.exe` file just from running `java Hello`**; the JIT normally compiles at runtime in process memory. AOT/native-image mechanisms are a separate path, outside the basic `javac → .class → JVM` flow.

### Bytecode Is Portable, Performance Still Depends on the Environment

The same bytecode can be run by different JVMs on x86-64 or ARM64; the runtime chooses an execution mechanism compatible with the CPU. However, performance depends on the JIT, memory/GC, workload profile, OS environment, and resources. Concluding that “Java is always slow because it is interpreted” is incorrect for runtimes with JIT; concluding that “Java is always as fast as native” cannot be generalized either.

## 6. Runtime Data Areas Appearing During Execution

Although this lesson focuses on the compilation path, it is useful to distinguish several areas used by the runtime:

| Concept | Role while the program is running |
| --- | --- |
| **Heap** | Holds allocated objects/arrays; the garbage collector manages reclaiming memory as appropriate |
| **Per-thread JVM stack** | Holds stack frames for Java method calls; a frame contains local variables, operand stack, and linking information |
| **Method area / class metadata** | Stores runtime structures related to classes, methods, and the constant pool; HotSpot commonly uses **Metaspace** for much of class metadata |
| **Per-thread PC register** | Tracks the JVM instruction position associated with the current execution thread |
| **Native method stack / native memory** | Supports native code and the runtime; details depend on the JVM and platform |
| **Code cache (in HotSpot)** | Holds JIT-compiled machine code and some runtime-generated code |

`javac` creates **class files** on disk; the JVM then creates various structures **in memory** to load classes and run. Do not confuse **`Hello.class` on disk**, **class metadata in the runtime**, and **an object `new Hello()` on the heap** as the same thing.

## 7. Java Version Determines Class File Compatibility

The JVM must support the **class-file major version** of the loaded bytecode. Common examples:

| Compilation target | Class-file major version |
| --- | ---: |
| Java 17 | 61 |
| Java 21 | 65 |

Running a class file generated for target Java 21 on a runtime that only supports Java 17 will throw `UnsupportedClassVersionError`. On JDK 21, you can compile for Java 17 using:

```bash
javac --release 17 -encoding UTF-8 -d out Hello.java
```

`--release 17` selects the language semantics, class file format, and platform APIs corresponding to the target release (within what the tool supports). It **does not guarantee** that external libraries or native dependencies will work merely by changing `--release`. Conversely, bytecode targeting 17 can usually run on newer JVMs if there are no incompatibilities from libraries or configuration.

You can check the major version using:

```bash
javap -classpath out -verbose Hello
```

Look for the `major version` line in the output. There is no need to open the binary file in a text editor.

## 8. Launch Modes and Where Bytecode Lives

- **Classes on the classpath:** `java -cp out Hello` loads `Hello` via the classpath; with packages, use the fully qualified class name.
- **JAR:** `jar --create --file app.jar --main-class Hello -C out .` packages the classes; `java -jar app.jar` runs the entry point from the manifest. A JAR is an archive containing bytecode/resources; the JAR itself is not machine code.
- **Module:** modular Java applications use the module path and `java --module-path ... -m module.name/com.example.Main` following the module structure; this changes how modules are organized/resolved, not the fundamental bytecode → JVM nature.
- **Source-file mode (JDK 11+):** `java Hello.java` can compile and run a source file in one command. It still uses the compiler/runtime underneath; do not mistake this for the CPU directly executing `.java` syntax.

For the `Hello.java` example, the separate `javac` then `java` workflow remains most useful for observing the **intermediate class file**.

## 9. How to Identify Which Layer an Error Occurs In

| Symptom | Stage to check | What to inspect |
| --- | --- | --- |
| `javac` reports `';' expected`, `cannot find symbol`, `incompatible types` | Source compilation | Syntax, imports, types, and compiler dependencies |
| `Could not find or load main class Hello` | Launch / class loading | Class name, package, location of `Hello.class`, `-cp out` |
| `UnsupportedClassVersionError` | Class loading on the JVM | Compare `java --version`, `javap -verbose`, `--release` setting |
| `NoClassDefFoundError` | Runtime linking/loading or class usage | Runtime dependencies, classpath/module path, earlier initialization error; read the accompanying cause |
| `VerifyError` | Bytecode verification | Invalid class file, bytecode tool/instrumentation, or version conflict |
| `ExceptionInInitializerError` | Class initialization | Static initializer or static field initialization threw an exception |
| `NullPointerException`, `ArithmeticException` | Execution | Runtime logic and values; successful compilation does not eliminate these errors |

Do not attribute every “cannot run” error to the JVM. For example, `cannot find symbol` from `javac` is a **compile-time** error; a missing class when `java` loads dependencies is a **runtime** issue. When an error occurs, preserve the full **stack trace** and check the exact stage.

## 10. Self-Verifying the Path of a Program

You can perform this sequence of steps in order:

1. Run `javac --version` and `java --version` to see which compiler/runtime is being used.
2. Create `Hello.java`, run `javac -encoding UTF-8 -d out Hello.java`, then verify that `out/Hello.class` exists.
3. Run `javap -classpath out -c Hello` to observe the bytecode instructions, including adding `20 + 22`.
4. Run `java -cp out Hello` and verify that only the line `Result: 42` is printed from the example program.
5. Try changing `int right = 22;` to `int right = "22";`: the error appears at **`javac`**, and the modified program fails to compile.
6. Restore the file, recompile, and try running with a wrong class name or wrong classpath: this time the error appears at the **`java` class lookup/loading step**.

### Self-Check Questions

- Does `javac` directly generate x86-64 machine instructions? **No**; normally it generates bytecode in `.class`.
- If the JVM uses an interpreter, does the CPU execute bytecode directly as native code? **No**; the CPU executes the interpreter's machine code.
- Why can the same `.class` run on different CPUs? **Each platform's JVM** understands the same bytecode format and produces/executes appropriate behavior.
- Must the JIT compile every method? **No**; it depends on the JVM and program behavior.
- Does successful Java compilation mean all errors have been eliminated? **No**; class loading, initialization, and runtime logic can still fail.

When looking at the entire path, accurately distinguish **`javac` turning source code into bytecode**, **the JVM verifying/loading/initializing classes**, and **the runtime interpreting or JIT-compiling bytecode so the CPU can execute native instructions**. These intermediate layers simultaneously explain portability, runtime optimization mechanisms, and the origin of each category of errors.