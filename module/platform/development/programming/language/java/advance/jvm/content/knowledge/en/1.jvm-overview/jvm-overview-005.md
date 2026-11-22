# Distinguishing the JVMS Specification, the OpenJDK Project, and the HotSpot Implementation

## Goal and Overall Picture

When saying "the JVM runs a Java program", it is necessary to distinguish **three layers with different roles**:

1. **JVMS (Java Virtual Machine Specification)** is the **specification**: it describes the abstract virtual machine, class file format, bytecode instruction set, data areas, and execution rules that a compliant JVM must follow.
2. **OpenJDK** is an **open-source project/codebase** that develops a JDK: it includes the Java compiler (`javac`), tools (`java`, `javap`, `jcmd`...), Java libraries, and a commonly bundled JVM implementation, HotSpot.
3. **HotSpot** is **a specific JVM implementation**, prominent in OpenJDK-based JDK builds. It implements the behaviors required by the JVMS, while choosing its own execution and optimization mechanisms, such as interpretation, JIT, garbage collectors, and memory management.

Visualized as a flow:

~~~text
JVM semantics specification:
  Java Virtual Machine Specification (JVMS)
             |
             | Sets the compatibility contract
             v
JDK implementation source project:
  OpenJDK: javac + java launcher + libraries + HotSpot + tools...
             |
             | Packaged into a vendor's JDK build
             v
Application:
  HelloJvm.java --(javac)--> HelloJvm.class --(HotSpot JVM)--> Result

Note: another JVM implementation can also comply with JVMS.
~~~

**Important distinction:** JVMS is not an installable program; OpenJDK is not the name of a bytecode execution algorithm; HotSpot is not the official name of the JVM specification.

## 1. JVMS: The Virtual Machine Contract

### What does JVMS specify?

JVMS describes an **abstract virtual machine**, without mandating a single software or hardware structure. The core rule groups include:

- **`.class` format:** magic number `0xCAFEBABE`, class file version, constant pool, class, method, field, attribute information, and instruction code. The JVM must recognize and interpret class files matching the versions it supports.
- **Type system and bytecode set:** primitive types, reference types, operations such as `iload`, `iadd`, `invokevirtual`, `new`, `return`; operand stack/local variables state and instruction effects.
- **Loading, linking, and initializing classes:** rules for loading, verification, preparation, resolution, initialization, and related errors. The timing of resolution can be flexible within the framework of the specification.
- **Run-time data areas:** concepts such as **heap**, **method area**, **run-time constant pool**, **JVM stack**, **PC register**, and **native method stack**. Some areas are shared across threads; some belong to each thread.
- **Method execution, exceptions, and synchronization:** how frames are formed/terminated, calling and returning from methods, throwing and handling exceptions, semantics of `monitorenter`/`monitorexit`.
- **Compatibility constraints:** what observable behavior a valid JVM must guarantee; what can lead to verification or linking errors.

For example: JVMS describes that `iadd` takes two `int` values from the operand stack, adds them according to Java integer rules, and pushes the result. JVMS **does not require** JVM developers to write the handler in C++, in assembly, or to generate one machine instruction corresponding to each `iadd`.

### What does JVMS not specify?

Many operational details are the implementer's choice:

- Whether the JVM uses **interpretation**, **JIT**, or a combination of techniques; the level of machine code optimization and how the JIT compiler is structured.
- Whether the garbage collector is G1, ZGC, or another algorithm; pause policies, number of GC threads, and specific memory region layouts.
- How objects are laid out in RAM, how long an object header is, whether pointers are compressed, or which physical memory area the method area is mapped to.
- Implementation flags such as `-XX:+PrintCompilation`, `-XX:MaxRAMPercentage=...`, proprietary log file structures, and most diagnostic interfaces.
- JDK installer package formats, vendor, update schedule, and supported OS/CPU.

Saying **"JVMS requires a heap"** is true; saying **"JVMS requires the heap to be divided into G1-like regions"** is false. JVMS requires an automatic memory reclamation mechanism for objects, but does not mandate a GC algorithm. Similarly, **method area** is a concept specified by JVMS, while **Metaspace** is a familiar implementation detail of HotSpot, not a memory area mandated by name in JVMS.

### How does JVMS differ from JLS and Java SE API?

| Document/Concept | Answers the question | Example |
| --- | --- | --- |
| **JLS – Java Language Specification** | What syntax, types, and semantics does a valid Java source program have? | `class`, overloading, generics, how expressions are evaluated in Java |
| **JVMS – Java Virtual Machine Specification** | How are class files and bytecode represented, verified, and executed? | `constant_pool`, `iload`, `invokevirtual`, stack frame |
| **Java SE API specification** | What APIs/behaviors do the standard libraries promise to provide? | `java.lang.String`, `java.util.List`, `System.out.println` |
| **JDK implementation** | Who writes the compiler, libraries, and VM to fulfill those contracts? | OpenJDK source code and builds based on it |

`System.out.println` is a **Java library** call with an API specification; the `getstatic`/`invokevirtual` bytecodes have semantics according to JVMS; actually writing characters to the console also depends on the standard library and the I/O environment. One should not attribute all Java SE behavior solely to JVMS.

## 2. OpenJDK: The Project Building the Java Toolkit

### What is OpenJDK?

**OpenJDK** is the open-source development ecosystem for Java SE platform implementations and related components. The JDK project brings together many components to form the **JDK (Java Development Kit)**, for example:

- **`javac`**: compiles `.java` source code into bytecode/class files.
- **`java`**: launcher that starts the program, sets up the execution environment, and uses the VM included in the build.
- **HotSpot VM**: the virtual machine implementation in most common OpenJDK builds.
- **Class libraries/modules**: for example `java.base`, `java.logging`, `java.net.http`.
- **Development/diagnostic tools**: `javap`, `jar`, `javadoc`, `jcmd`, `jstack`, `jfr` (depending on build and version).

The project is not synonymous with **a single installation on a machine**. Many vendors create builds from OpenJDK source code, which may differ in patches, support schedules, compatibility certifications, licenses/distribution terms, configurations, and supported platforms. Therefore, **OpenJDK** can refer to the source project, or be used in the name of a JDK build; one must look at the context.

A build "based on OpenJDK" does not automatically prove that all of its configurations, extensions, or performance are identical to all other builds. Nor should one infer that "Oracle JDK" and "OpenJDK" are two different language/virtual machine specifications: they are distributions/products in the Java ecosystem and have specific history and terms by version.

### When using OpenJDK, which components do the work?

For a normal Java application:

1. `javac` parses the source code according to Java language rules and generates class files compliant with JVMS.
2. The `java` tool launches the runtime and VM packaged in the JDK being used.
3. The VM loads/verifies/links/initializes the appropriate classes and executes bytecode; the Java libraries provide the behavior of the APIs called by the program.
4. At runtime, the VM may interpret and optimize code; it may call native code, use operating system services, and manage resources.

One can program in **Kotlin, Scala**, or other languages that produce class files for the JVM; at the execution step, the main boundary is **JVMS**, even though the original source compiler is not `javac`.

### Where is the OpenJDK source code located?

Main JDK development repository: [github.com/openjdk/jdk](https://github.com/openjdk/jdk). Useful directories to look up:

- `src/hotspot/`: the HotSpot VM part, including runtime, class file handling, JIT, GC, and CPU/OS support.
- `src/java.base/`: many foundational classes and supporting native libraries.
- `src/jdk.compiler/`: components of the Java compiler.
- `src/jdk.jcmd/`: tools for diagnostics.

This is the implementation source code structure, **not** a structure mandated by JVMS. Directories/mechanisms may change across branches and versions.

## 3. HotSpot: How Does the JVM Actually Work?

**HotSpot** is the name of a JVM implementation developed within OpenJDK. In a build using HotSpot, the VM guarantees the behavior required by JVMS and additionally provides optimization, resource management, and diagnostic mechanisms.

### Main Components

**Class loading and execution preparation.** HotSpot participates in loading class files, checking bytecode validity, linking, and initializing according to JVMS rules. Classes can come from files, modules, JARs, custom loaders, or dynamic sources; one should not understand the JVM as only running pre-saved `.class` files on disk.

**Execution engine.** HotSpot has an **interpreter** to execute bytecode and **JIT compilers** to compile suitable code regions into machine code. In many server configurations, HotSpot uses **tiered compilation** (typically consisting of C1/C2) to balance startup time, profile collection, and steady-state performance. Compiler/optimization tier details may vary by version/configuration; JVMS does not require a JIT.

**Memory management and garbage collection.** HotSpot allocates objects, tracks references needed for GC, and provides collectors such as **G1** and **ZGC** on supported versions/platforms. Structures such as **Metaspace**, code cache, TLAB, card table, or regions are all details of an implementation; they should not be considered mandatory names in JVMS.

**Threads, synchronization, and OS interaction.** HotSpot implements thread mechanisms, monitors, JNI, runtime coordination, OS communication, and coordination points needed for VM tasks such as GC. Thread mapping styles and locking algorithms can evolve while still preserving the prescribed JVM/Java semantics.

**Observation and configuration.** HotSpot has tools, flags, GC/JIT logs, and diagnostic mechanisms; `-X`/`-XX` flags are implementation-specific operational interfaces, which may change, be restricted, or not appear on other JVMs.

### Example: The Same Addition, Multiple Execution Paths

Suppose the bytecode has `iload_1`, `iload_2`, `iadd`, and `ireturn`:

- JVMS defines the abstract steps and resulting value of the `int` addition.
- HotSpot may run it using the interpreter initially.
- If the method is suitable for optimization, HotSpot may compile it to machine code and run that code in subsequent invocations; the translation does not necessarily correspond one bytecode to one CPU instruction.
- Regardless of which path is chosen, the program must observe the semantics required by the specification (except for behaviors allowed to be flexible by the specification).

HotSpot can perform **deoptimization** (falling back to general execution when an optimization assumption is no longer true). This is an internal strategy to optimize performance while preserving semantics, not a new bytecode instruction mandated by JVMS.

## 4. Comparison Table of the Three Concepts

| Criterion | JVMS | OpenJDK | HotSpot |
| --- | --- | --- | --- |
| Nature | Standard specification document of the virtual machine | Project/codebase building the JDK | A specific JVM implementation |
| Main question | "What must the VM do and guarantee?" | "Where are the source code/tools/libraries to build the JDK?" | "How does a specific VM execute and optimize?" |
| Can it be run directly? | No | The "project" does not run; **a JDK build** contains runnable programs/tools | Yes, when packaged in a runtime |
| Scope | Class file, bytecode, VM rules | Compiler, libraries, launcher, VM, tools, project processes | Runtime VM, JIT, GC, memory, threads, diagnostics |
| Example | Heap and operand stack are mandatory concepts | `javac`, `java.base`, `openjdk/jdk` repository | C1/C2, G1/ZGC, Metaspace, `-XX` flags |
| What can replace it? | Another specification version depending on release; compatibility must be considered | Another Java SE project/distribution | Another compatible JVM, e.g., Eclipse OpenJ9 |
| How to look up | Definition chapters in the JVMS of the right version | Project documentation, source code, release notes | HotSpot documentation, flags/help, `src/hotspot` source, logs |

Relationship to remember: **HotSpot is an implementation component used in OpenJDK; OpenJDK provides the source and tools of a JDK; JVMS sets the contract for the JVM.** The three names belong to three different kinds of things, not three products running in parallel and not three sequential "compilation" steps.

## 5. Practice: From Java Source to a Running JVM

Example using Java 17+; create the file `HelloJvm.java` (file name matches `public class`):

~~~java
public class HelloJvm {
    public static void main(String[] args) {
        int total = 3 + 4;
        System.out.println("Tong = " + total);
        System.out.println("VM = " + System.getProperty("java.vm.name"));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac HelloJvm.java
javap -c HelloJvm
java HelloJvm
java -version
~~~

The program output **definitely** has the first line:

~~~text
Tong = 7
~~~

The second line starts with `VM = `, but **the value depends on the JDK/VM build**. For example, on many HotSpot Server VM builds, that line contains a name like `OpenJDK 64-Bit Server VM`; do not copy this name as a universal result for all machines. The `java -version` command shows the version/runtime/VM information declared by the build; the format and vendor name may also differ.

The `javap -c HelloJvm` command lets you view the bytecode of the class file. With the string printing and API calls, you can see instructions like `getstatic` (reading `System.out`), `invokevirtual` (calling `println`), `ldc` or `invokedynamic` (depending on how the compiler generates string concatenation), along with return instructions. **Do not** treat constant pool indices or the entire disassembly as fixed across all compiler versions; the JVM only has to follow the class file structure/semantics it accepts.

### Relating Each Action to Each Layer

| Visible step | Related layer | Why? |
| --- | --- | --- |
| `javac HelloJvm.java` creates `HelloJvm.class` | OpenJDK/JDK tool + JLS/JVMS | The compiler is an actual program; the output bytecode must follow the class-file contract |
| `javap -c` prints bytecode instructions | JDK tool + JVMS | Instructions have meaning according to the JVMS document |
| `java HelloJvm` runs the program | Launcher in JDK + HotSpot or packaged VM | The specific JVM executes the class, libraries provide `System.out` |
| `java.vm.name` | Runtime in use | Observes the VM name declared by the implementer, not a way to verify full compatibility |
| G1, JIT, GC logs, `-XX` | Mainly HotSpot | Execution strategy/configuration, not standard bytecode |

### One More Comparison on HotSpot

In an environment using a supported HotSpot, you can try:

~~~bash
java -Xint HelloJvm
~~~

The `-Xint` flag asks HotSpot to run in interpreted mode, often useful for comparing behavior/diagnostics. The functional result is still the calculation `3 + 4 = 7` and printing the VM name; speed should not be inferred from such a small program. `-Xint` is a runtime-specific option, **not a command or requirement in JVMS**; other VMs may not support it.

If a diagnostic option is rejected, first check the build, version, and VM (`java -version`, official vendor documentation). Do not infer that the JVM violated JVMS just because it does not recognize a HotSpot `-XX` flag.

## 6. Standard vs. Implementation Choice: How to Classify Situations

**Situation A — malformed class file:** When encountering a class file with an invalid structure or unsupported version, check **JVMS – Class File Format/Verification** and the specific error message. Before concluding a VM bug, compare the JDK version and the bytecode being run.

**Situation B — application gets `OutOfMemoryError`:** JVMS has rules related to data areas and `OutOfMemoryError`, but to analyze memory usage, heap dumps, Metaspace, and how GC behaves on the actual machine, check the **specific HotSpot/runtime**, configuration, and logs. Do not equate heap size with total process memory.

**Situation C — switching collector from G1 to ZGC:** This is a choice **of HotSpot/the runtime build**. The Java program does not have to change bytecode because JVMS does not lock the application to a specific collector. However, performance/pauses may change significantly.

**Situation D — changing JDK vendor:** Compare releases, security patches, CPU/OS platforms, supported APIs, licenses, commercial support, and the **bundled VM**. Do not infer that sharing the word "OpenJDK" guarantees all JIT/GC options are identical.

**Situation E — another JVM running Java bytecode:** A compliant JVM may choose memory management and code generation methods different from HotSpot. **The ability to execute class files according to the contract** is the core of JVMS compatibility; HotSpot characteristics do not automatically become the specification.

## 7. Common Misconceptions

1. **"OpenJDK is HotSpot."** Not accurate: HotSpot is one VM component in the JDK codebase; OpenJDK also has a compiler, libraries, launcher, and many tools.
2. **"JVMS mandates using JIT or G1."** False: JVMS specifies virtual machine behavior, leaving implementers to choose optimization mechanisms and memory management algorithms.
3. **"Metaspace = method area by the official name of the specification."** False: method area is a JVMS concept; HotSpot has metadata storage details such as Metaspace.
4. **"Every OpenJDK build has the exact same `java -version` lines."** False: build, vendor, version, OS/CPU, and VM may differ.
5. **"Every HotSpot feature works on other JVMs."** False: HotSpot's `-XX` flags, logs, tools, and optimizations are usually not portable APIs/ABIs.
6. **"If you have bytecode, any VM must be able to run it regardless of version."** False: class files have versions/features, and the runtime needs to support the corresponding parts; `UnsupportedClassVersionError` usually reflects a Java runtime older than the class file.
7. **"JVM is Java."** False: the Java language, the Java SE library platform, and the JVM virtual machine are closely related but have different specifications/scopes.

## 8. Self-Check

**Question 1.** A document defines the `invokevirtual` bytecode, frames, and the constant pool. What concept are you reading about?  
**Answer:** JVMS, because these are rules about the virtual machine and class file format.

**Question 2.** You want to modify the GC algorithm or find the C++ source code running inside the VM of a common OpenJDK build. Where should you start?  
**Answer:** The HotSpot component, usually from `src/hotspot`; check the exact JDK branch being used.

**Question 3.** You want to view the code of `javac` and the `java.base` library. Does JVMS provide that code?  
**Answer:** No. Read the OpenJDK/JDK source project; JVMS is a document specifying VM behavior.

**Question 4.** A JVM processes bytecode correctly but does not support `-XX:+PrintCompilation`. Is there enough evidence to claim a JVMS violation?  
**Answer:** No. `-XX` is an implementation option; check the relevant standard requirements before assessing compatibility.

**Question 5.** When migrating from HotSpot to another JVM, what should be reviewed first?  
**Answer:** Options, tools, logs, and performance/GC assumptions that depend on HotSpot. Application behavior based on valid Java SE/JVMS has higher portability but still needs testing by platform and version.

## 9. Further Reading

- [Java Language and Virtual Machine Specifications](https://docs.oracle.com/javase/specs/) — choose the right Java SE version when looking up JVMS/JLS.
- [JVMS – The Structure of the Java Virtual Machine](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html) — abstract virtual machine, run-time data areas, guide to distinguishing contract from implementation.
- [JVMS – The Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html) — class file structure and format rules; look up the version corresponding to your runtime.
- [OpenJDK](https://openjdk.org/) and [OpenJDK JDK Project](https://openjdk.org/projects/jdk/) — JDK project and development guides.
- [OpenJDK JDK source](https://github.com/openjdk/jdk) — view source code for `src/hotspot`, `src/jdk.compiler`, `src/java.base`.

**Keep in mind when reading further about the JVM:** ask the question "**is this a contract in JVMS, source code from the OpenJDK project, or an implementation decision of HotSpot?**". Classifying it correctly right from the start will help you look up the right documentation and avoid confusing a feature of one VM with a mandatory requirement for all JVMs.