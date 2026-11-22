# Distinguishing the Java Language, Java SE, JVM, JDK, and Runtime Environment

## Objectives

After this lesson, you can clearly distinguish the five concepts commonly referred to collectively as “Java”, explain the path from source code to bytecode and a running process, identify the toolset needed for development/deployment, and diagnose errors caused by incompatible versions or environments.

## 1. Map of the Five Concepts

| Component | What is it? | Primary role | Examples |
| --- | --- | --- | --- |
| **Java language** | Programming language with syntax, type system, and semantics specified in the Java Language Specification (JLS) | Defines how to *write* and understand source code | `class`, `interface`, `record`, `if`, lambda |
| **Java SE (Java Platform, Standard Edition)** | Standard Java platform with language specifications, JVM, and standard API libraries per version | Defines the contract of the *standard platform/API* | `java.lang`, `java.util`, `java.time`, `java.io` |
| **JVM (Java Virtual Machine)** | Virtual machine specified to load, verify, and execute code in class file format | *Executes* bytecode | HotSpot VM, Eclipse OpenJ9 |
| **JDK (Java Development Kit)** | Development toolset and components required to run Java | *Compiles, runs, packages, and analyzes* | `javac`, `java`, `jar`, `javap`, `jlink` |
| **Runtime environment** | Actual Java runtime combined with libraries, operating system, machine architecture, and deployment configuration | Determines whether the application can *run in practice* | JVM + Java SE modules + dependencies + OS/CPU + configuration |

**Relationship:** developers **write in the Java language**, can **call Java SE APIs**, use the **JDK** to compile into class files, and then a **JVM** belonging to the **runtime environment** executes the bytecode. These five terms cannot be used interchangeably.

## 2. Java Language: Rules of Source Code

The Java language defines rules for declaring classes/interfaces, data types, names, expressions, statements, exceptions, generics, lambdas, and many other constructs. The **Java Language Specification (JLS)** describes the syntax and semantics for each version.

For example, `int x = 2;` conforms to the language rules; assigning `String text = 123;` is a type error in the normal case. New syntax may require a new language version: `record` has been an official feature since Java 16, so it cannot be used when compiling with the Java 11 language level.

**A language is not synonymous with libraries or a virtual machine.** Java code can call libraries outside Java SE such as Spring; conversely, the JVM can run bytecode compiled from Kotlin or Scala. Despite having “Java” in the name, Spring is not language syntax and does not belong to the standard Java SE API set.

## 3. Java SE: Standard Platform and APIs

**Java SE** is the name of the standard Java platform. This platform includes the language specifications, JVM, and standard libraries/APIs corresponding to a release version. When emphasizing the “Java SE API”, we are referring to the standardized public API set, for example:

- `java.lang`: `Object`, `String`, `System`, `Thread` (package imported implicitly).
- `java.util`: `List`, `Map`, `Optional`, and utilities.
- `java.time`: modern date/time types.
- `java.io`, `java.nio.file`: input/output and file system.
- `java.net`, `java.net.http`: networking and HTTP client.

Since Java 9, platform components have been organized through the **module system**; every module implicitly reads the core `java.base` module. Some APIs exist in newer Java SE versions but not in older ones, so it is necessary to check the target platform version.

**Java SE is not a single executable or a single installer.** The JDK provides the tools and a platform implementation. Java SE is also not synonymous with the entire ecosystem: **Jakarta EE**, **Spring**, many JDBC drivers, and third-party libraries must be provided separately; JavaFX is no longer bundled as part of the standard JDK since Java 11.

## 4. JVM: Execution Layer, Not the Language or Toolset

The **JVM**, according to the *Java Virtual Machine Specification (JVMS)*, is an abstract machine with a contract for the `.class` format, bytecode, loading/linking/initialization, and execution. **HotSpot** and **OpenJ9** are implementations of that virtual machine. They can choose different interpreters, JITs, and GCs while having to preserve the specified semantics.

When running `java HelloJvm`, the runtime/JDK launcher starts the JVM; the VM loads and executes the class file, while calls to `List.of` and `System.out.println` use the Java SE library. Therefore, **the JVM is not `javac`, not all of Java SE, and not a virtual machine that emulates an operating system**. The steps and memory areas inside the JVM are analyzed in the lesson on execution architecture, rather than repeating loading and JIT details here.

## 5. JDK: Development Toolset

The **Java Development Kit** consists of tools that help write, compile, test, package, run, and analyze Java applications; it also provides the runtime components.

| JDK Tool | Used to |
| --- | --- |
| `javac` | Compile `.java` source into `.class` class files |
| `java` | Start the JVM and run a class, JAR, or module |
| `jar` | Create/view/update JAR files |
| `javadoc` | Generate API documentation |
| `javap` | Inspect class file information; `javap -c` shows bytecode instructions |
| `jshell` | Quickly try Java expressions/snippets in a REPL |
| `jdeps` | Analyze dependencies of classes/JARs |
| `jlink` | Create a custom runtime image from modules |

For example, **`javac` is not the JVM**: `javac` normally parses source code, performs type checking, and generates bytecode; the JVM reads the class file and executes that bytecode, possibly optimizing/JIT-compiling it at runtime. Nor should Java SE be called the JDK: Java SE describes the platform, whereas the JDK is a toolset tied to a specific implementation.

The JDK has release levels such as **17**, **21**, and many distributions from vendors. It is necessary to distinguish **Java/JDK version**, **vendor/build**, and **JVM implementation**; they affect the provided APIs, class file level, patches, configuration, and sometimes runtime characteristics.

## 6. “Runtime Environment”, JRE, and Runtime Images

In traditional terminology, the **JRE (Java Runtime Environment)** is a package containing the JVM and the libraries/resources needed to run Java, without the full set of development tools like `javac`. In the Java 8 era, JRE and JDK installers were often distributed separately.

Since Java 9, the module system and runtime images have changed distribution; many modern Java vendors do not release a separate installer named “JRE” in the Java 8 style. In practice, Java 17+ is usually run using:
- **A full JDK**, containing both tools and runtime.
- **A runtime image** packaged by the vendor, which may not include a compiler.
- **A runtime image created by `jlink`**, containing only the selected modules and required module dependencies.

The runtime environment is broader than the Java runtime: it includes the **OS/CPU**, native libraries, JAR dependencies, classpath/module path, system permissions, environment variables, configuration files, memory/resources, and external connections. For example, a properly working JVM still cannot supply a missing framework JAR on its own; a native library for Linux/x86-64 will not run on Windows/ARM64 on its own either.

**Distinguish clearly:**
- **JVM** is the component that executes bytecode.
- **JRE/runtime image** is the set of components packaged for running a program.
- **JDK** includes development tools and the ability to run.
- **Actual runtime environment** also includes all the deployment conditions listed above.
- A single machine can have one JDK while running multiple different **JVM processes**.

## 7. Mapping the Five Concepts to a Concrete Program

```text
Java source (syntax/semantics) + Java SE API (List, String, System)
          |
          | javac: tool in the JDK
          v
       HelloJvm.class
          |
          | java launcher → JVM
          v
Java SE libraries + dependencies + OS/CPU + configuration
          |
          v
      Running program
```

Save the file **`HelloJvm.java`**:

```java
import java.util.List;

public class HelloJvm {
    public static void main(String[] args) {
        List<String> concepts = List.of(
                "Java language",
                "Java SE",
                "JVM");
        System.out.println("Three layers: " + String.join(" | ", concepts));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 HelloJvm.java
java HelloJvm
```

**Exact stdout**:

```text
Three layers: Java language | Java SE | JVM
```

In the example, the class declaration, generics, and method calls belong to the **Java language**; `List`, `String.join`, and `System.out` belong to the **Java SE API**; `javac` and `java` are in the **JDK**; the **JVM** executes the class file; the **runtime environment** includes libraries, dependencies, and the OS. `--release 17` selects the target language, class-file version, and Java SE API, and **does not automatically verify** dependencies or native libraries on the target machine.

To trace **the exact compilation steps and opcodes**, use `javap -c` with the next lesson on the path `.java → .class → machine code`. Classifying the five concepts here does not require memorizing class loading algorithms or JIT details.

## 8. Checking Versions and Compatibility

~~~bash
java -version
javac -version
~~~

The first command shows the actual runtime/launcher being invoked; the second command shows the actual compiler being invoked. **The two commands may pick two different installations** because of `PATH`, `JAVA_HOME`, IDE settings, Maven/Gradle toolchains, or containers; `JAVA_HOME` is a convention used by many tools, while the executable actually being run determines the real JVM.

When verifying an application, ask four independent questions:

1. **Language:** does the compiler understand the syntax and the requested `--release`/`--source` level?
2. **Bytecode:** does the runtime JVM support the generated class file? For example, Java 17 corresponds to class file major version **61**, and Java 21 corresponds to major version **65**. A Java 17 JVM does not understand class file major version 65.
3. **APIs and libraries:** does the runtime have the corresponding Java SE APIs, modules, and third-party JARs?
4. **Platform:** are the OS, CPU, native binaries, configuration, permissions, and resources compatible?

**Case A — `UnsupportedClassVersionError`:** usually the class file was built for a newer JVM version than the running runtime. Check the versions, recompile with an appropriate target, or upgrade the JVM.

**Case B — `java` is present, but `javac` is not:** you may be using a runtime image or a path pointing to a runtime. Running compatible class files may work, but a compiler/JDK is needed for normal compilation.

**Case C — `ClassNotFoundException`/`NoClassDefFoundError`:** usually you need to check JARs/modules/classpath, class initialization errors, and the cause chain in the stack trace. This is not automatically a Java syntax error.

**Case D — works on a personal machine but fails on the server:** compare versions, modules trimmed with `jlink`, native libraries, OS/CPU, and deployment configuration. **“Write once, run anywhere”** expresses the portability goal; it does not mean every dependency outside the bytecode is automatically compatible.

## 9. Common False Claims

| Misconception | Accurate statement |
| --- | --- |
| “Java = JVM.” | Java is a language, and the JVM is a virtual machine; the JVM can run bytecode from multiple languages. |
| “Java SE is the JDK.” | Java SE is a platform/specification; the JDK is a toolset and an implementation of the required components. |
| “`javac` directly generates machine code.” | `javac` normally generates JVM bytecode; the VM executes it and may JIT-compile it to machine code. |
| “The JVM is a virtual machine containing its own operating system.” | The JVM executes bytecode and relies on the underlying OS. |
| “Installing a Java runtime automatically gives you a compiler.” | A runtime image may not contain `javac`. |
| “Without a separate JRE package, you cannot run Java.” | An appropriate JDK or runtime image can already run the application. |
| “A new JDK can always run on an old JVM.” | Bytecode must target the right JVM level; APIs and dependencies must also be compatible. |
| “A JAR is a virtual machine.” | A JAR is a packaging format for class files and resources. |

## 10. Self-Check and Answers

**Question 1.** In `List.of("A", "B")`, which concepts do the method call syntax and the `List.of` API belong to?

**Answer:** the syntax belongs to the **Java language**; `List.of` is a **Java SE API** (added in Java 9).

**Question 2.** The `java` command is available, but `javac` is not. Can a Java program be run?

**Answer:** **Yes, possibly**, if the runtime and all dependencies are compatible. However, you cannot assume the machine has a compiler; a JDK is needed if you want to use `javac` to compile source code in the standard way.

**Question 3.** JDK 21 compiles with `javac --release 17`; is the program guaranteed to run on JVM 17?

**Answer:** the option targets Java 17's language, bytecode, and Java SE API, so it helps ensure compatibility at those layers, but it is **not a sufficient guarantee**: you must still check libraries outside Java SE, dependencies, native code, and the actual environment.

**Question 4.** Kotlin generates bytecode to run on the JVM. Does that make Kotlin the Java language?

**Answer:** **No.** Kotlin is its own language; it can use the JVM as its bytecode execution environment.

**Question 5.** What are the distinct roles of Java SE and the JVM when using `java.util.List`?

**Answer:** **Java SE** specifies the `java.util.List` API; the platform implementation provides the corresponding library; the **JVM** executes the bytecode that calls that API.

## 11. Quick Mental Model

- **Language** → writing code using Java syntax/semantics.
- **Java SE** → platform contract and standard APIs.
- **JDK** → compiling, packaging, running, analyzing.
- **JVM** → loading and executing class files/bytecode.
- **Runtime environment** → JVM, libraries, OS, configuration, and all conditions for the program to actually run.

When encountering an error, identify which layer it is in: **source/syntax → compiler/tool → class file/JVM → API/dependency → configuration/host machine**. Distinguishing the layers properly helps choose the right troubleshooting step.
