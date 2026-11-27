# Java SE, OpenJDK, JDK, and JVM: Roles and Relationships

When you start learning Java 17, you will frequently encounter four names: **Java SE**, **OpenJDK**, **JDK**, and **JVM**. They are closely related, yet they are not the same kind of concept: one is a **standard**, one is an **open-source implementation of that standard**, one is a **software kit installed on your machine**, and one is the **component that executes programs**.

Understanding this distinction properly helps you answer practical questions: What do I need to install to write Java 17 programs? Why are there multiple JDK vendors? Do I need `javac` when deploying to a server? Why can `.class` files run across multiple operating systems while still requiring a corresponding JVM?

## 1. The Big Picture: Four Concepts, Four Roles

| Concept | Nature | Primary Role |
| --- | --- | --- |
| **Java SE 17** (*Java Platform, Standard Edition*) | Specification/standard of the Java platform version 17 | Defines the Java language, JVM behavior, and standard APIs that a compliant implementation must provide. |
| **OpenJDK 17** (*Open Java Development Kit*) | Open-source project and codebase implementing Java SE | Provides most of the source code used to build a JDK, including the compiler, standard libraries, and the HotSpot JVM. |
| **JDK 17** (*Java Development Kit*) | Software kit used to develop and run Java 17 applications | Provides `javac`, `java`, other tools, and the runtime environment needed. |
| **JVM** (*Java Virtual Machine*) | Virtual machine that executes Java bytecode | Loads, verifies, and executes `.class` code; manages runtime mechanisms such as memory and garbage collection. |

A quick way to remember:

- **Java SE answers:** “What behavior and APIs must a standard-compliant Java 17 platform provide?”
- **OpenJDK answers:** “What source code implements that platform?”
- **JDK answers:** “What toolkit do I install to write, compile, package, and run Java?”
- **JVM answers:** “What component actually executes Java bytecode?”

## 2. Java SE 17: A Platform Defined by Standards

**Java SE** is the standard edition of the Java platform, encompassing the language rules and components required to write, compile, and run general-purpose Java programs. “Java SE 17” refers to **version 17 of the platform/specification**, not a standalone application that you download and launch.

Three key groups of specifications are:

1. **Java Language Specification (JLS):** specifies the syntax and semantics of the language—for example, how to declare classes, data types, expressions, inheritance, and exceptions.
2. **Java Virtual Machine Specification (JVMS):** specifies the class file (`.class`) format, bytecode instruction set, and JVM execution model. It defines the behavior that must be adhered to, without requiring every JVM to share the same internal architecture.
3. **Java SE API:** specifies the standard libraries available for applications to use, such as `java.lang`, `java.util`, `java.time`, `java.nio.file`, `java.net.http`, and `java.util.concurrent`.

For example, when you write:

```java
import java.time.LocalDate;
import java.util.List;

public class StandardApiExample {
    public static void main(String[] args) {
        List<String> languages = List.of("Java", "Kotlin");
        System.out.println(languages);
        System.out.println(LocalDate.now());
    }
}
```

`List` and `LocalDate` belong to the Java SE standard API, so you do not need to install any third-party library to use them on a full JDK 17. By contrast, frameworks like Spring or application libraries are separate dependencies; they do not automatically become part of Java SE.

**Key distinction:** a specification defines a *behavioral contract*; a specific JDK provides the *executable code and APIs* that fulfill that contract. Therefore, “programming against Java SE 17” and “installing a JDK 17 distribution” are related but distinct activities.

## 3. OpenJDK 17: The Open-Source Project Implementing Java SE

**OpenJDK** is the open-source project that develops an implementation of the Java SE platform. This project includes many components that developers use every day:

- **`javac`:** the compiler that translates Java source code into bytecode.
- **Standard libraries and modules:** implementations of APIs such as `java.base`, `java.sql`, and `java.net.http`.
- **HotSpot:** a widely used JVM implementation with interpretation, JIT compilation, memory management, and garbage collection mechanisms.
- **Other tools:** `jar`, `javadoc`, `jdeps`, `jlink`, `jshell`, and more.

You should distinguish between the **OpenJDK project/source code** and a **JDK distribution built from OpenJDK source code**. Distributions such as Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK, or Oracle JDK may all be largely based on OpenJDK while differing in packaging, update schedules, support policies, licenses, and sometimes additional components.

Therefore:

- **OpenJDK is not synonymous with just the JVM:** the project's source code also includes the compiler, standard libraries, and development tools.
- **OpenJDK is not the name of every JDK installer:** you can install a JDK packaged by a vendor from OpenJDK.
- **Using a JDK from a different vendor does not necessarily change the Java language:** what matters is the Java SE version, compatibility, operating system/machine architecture, and update policy.

Within the scope of learning Java 17, a **Java SE 17–compatible JDK 17 distribution** is the standard choice for development, whether you use an IDE or the command line.

## 4. JDK 17: The Actual Toolkit Installed on Your Machine

**JDK** is the Java Development Kit. When you install JDK 17, you get both the tools to build programs and the components to run Java programs.

| Component in the JDK | Purpose |
| --- | --- |
| `javac` | Compiles `.java` source code into `.class` files. |
| `java` | Launcher: starts application execution, creating/starting the JVM with the appropriate configuration. |
| `jar` | Creates, inspects, and manipulates JAR archive files. |
| `javadoc` | Generates API documentation from comments and source code. |
| `javap` | Inspects metadata/bytecode inside compiled class files. |
| `jshell` | Interactively tries out Java expressions and code snippets quickly. |
| `jdeps` | Analyzes dependencies of classes/JARs/modules. |
| `jlink` | Builds a custom runtime image from the required modules. |
| **JDK Runtime** | Includes the JVM, standard libraries, and components needed to execute applications. |

In modern Java, the runtime environment has a **modular** structure (introduced in Java 9); for instance, `java.base` is the foundational module always present in a Java SE runtime. You can run an application using the runtime bundled with the JDK, or package a tailored **runtime image** with `jlink` for deployment.

### How should you think about the JRE?

**JRE** (*Java Runtime Environment*) is the traditional name for the Java **runtime** environment, in contrast to the JDK which adds **development** tools. In older guides, the JRE was commonly introduced as a separate installer.

For Java 17, the useful and still-applicable mental model is: **an application needs a runtime containing a JVM and the required modules/libraries; a developer compiling code needs a JDK**. That runtime may come bundled with the JDK or be provided/packaged separately. You should not assume you must hunt down a standalone “JRE 17” installer just because older documentation used to instruct you to do so.

### JDK on developer machines vs. runtime machines

- **Developer machine / CI build:** requires a JDK to run `javac` and build tools.
- **Machine running a compiled application:** does not necessarily need `javac`; it needs a compatible runtime with all the modules/dependencies the application uses. Installing a full JDK can also run the program, though it is not the only option.
- **IDEs such as IntelliJ IDEA or VS Code:** an IDE is a tool for editing, navigation, and debugging; it needs to point to a JDK suitable for the project in order to compile and run Java 17.

## 5. JVM: The Bytecode Execution Engine

**JVM** provides the execution environment for compiled Java class files. The basic pipeline when launching an application includes:

1. **Class loading:** class loaders locate and load the required classes from the classpath/module path and the runtime.
2. **Linking and verification:** the JVM verifies the validity of the bytecode and prepares class structures according to JVM rules.
3. **Class initialization and execution:** runs the necessary initialization code and invokes `main` or the appropriate entry point.
4. **Runtime optimization:** a JVM such as HotSpot can interpret bytecode and JIT (*Just-In-Time*) compile frequently executed code paths into native machine code.
5. **Runtime management:** allocates and manages memory, performs garbage collection, coordinates thread synchronization, and handles exceptions according to Java semantics.

**The JVM is not the `javac` command itself.** `javac` runs beforehand to produce bytecode; the JVM processes bytecode while the program runs. The `java` command is the *launcher* used to start execution; it is not the name of the entire JVM.

### How does bytecode make applications portable?

A `.class` file contains **JVM bytecode**, not native machine code specific to Windows, Linux, or macOS. As long as a suitable Java runtime exists on each operating system/architecture, the corresponding JVM will execute that bytecode.

```text
Java 17 source code (.java)
          |
          | javac (compiler in JDK 17)
          v
JVM bytecode (.class, class file version 61)
          |
          | java (launcher)
          v
Compatible JVM + runtime libraries
          |
          | interpretation / JIT / OS services
          v
Program executes on the target machine
```

Portability is **conditional**: the runtime must support the class file version and APIs that the program uses; native libraries, file paths, operating system configuration, or external dependencies can still require environment-specific adjustments.

For bytecode compiled for **Java 17**, the class file version (*major version*) is **61**. Older JVMs, such as Java 11, cannot directly load version 61 class files; a common symptom is `UnsupportedClassVersionError`.

## 6. How Java SE, OpenJDK, JDK, and JVM Fit Together

Look at two dimensions at once: **what defines/provides the platform** and **which components a program passes through when running**.

```text
Java SE 17
(language, JVM, and API specifications)
      |
      | implemented by
      v
OpenJDK 17
(source code for javac, libraries, HotSpot, tools, ...)
      |
      | built, packaged, and updated by vendors
      v
JDK 17 Distribution
      |                              |
      +-- Development tools           +-- Runtime environment
          javac, jar, javadoc, ...       java launcher
                                       JVM (typically HotSpot)
                                       Java SE libraries/modules
```

This diagram illustrates one common distribution path from OpenJDK source code; the Java SE concept does not depend on any single vendor. Inside a JDK, the **JVM is the runtime component**, while the JDK is the **broader product** that also includes development tools.

A Java 17 program uses the entire chain: it is written according to Java SE 17 rules; compiled using `javac` from a JDK 17; started via `java` launching the JVM in a compatible runtime; and calls standard libraries provided by the runtime during execution.

## 7. Hands-On: From Source Code to the JVM on Java 17

Suppose you have installed a JDK 17 distribution and configured your terminal to use that JDK.

### Step 1: Verify the environment

Run:

```bash
java -version
javac -version
```

The first command shows the Java runtime found by your terminal; the second shows the compiler version. In this lesson, both should point to **Java 17**. Actual output may include the vendor name, a `17.0.x` update version, or the JVM name.

If `java` works but `javac` is not recognized, your terminal may be pointing to a runtime without a compiler, or the `PATH` environment variable may not include the `bin` directory of the desired JDK. `JAVA_HOME` (when required by tools) typically points to the **JDK root directory**, not to the `java` executable and not to the `bin` directory.

### Step 2: Write a small program

Create the file **`HelloJava17.java`**:

```java
public class HelloJava17 {
    public static void main(String[] args) {
        System.out.println("Java version: " + Runtime.version().feature());
        System.out.println("Hello Java 17!");
    }
}
```

`Runtime.version().feature()` is a built-in Java SE API; when run on a Java 17 runtime, the printed value is `17`.

### Step 3: Compile and run

In the directory containing the source file:

```bash
javac HelloJava17.java
java HelloJava17
```

Illustrative output:

```text
Java version: 17
Hello Java 17!
```

These are two distinct steps:

1. `javac HelloJava17.java` uses the **JDK compiler** to generate `HelloJava17.class`.
2. `java HelloJava17` uses the **launcher** to start the JVM, locate the `HelloJava17` class, and execute the `main` method.

Note that the run command takes the **class name** `HelloJava17`, without the `.class` extension.

You can inspect the class file metadata using a JDK tool:

```bash
javap -verbose HelloJava17.class
```

The output will include `major version: 61` if the file was compiled to run on Java 17.

### Step 4: Distinguish single-file source-code execution

Java 17 also supports running a program in *source-file mode*:

```bash
java HelloJava17.java
```

In this mode, the launcher handles compiling the source code for execution in a single invocation; you do not have to run `javac` yourself beforehand. This is a convenience for trying out small programs, and **it does not mean the JVM directly understands and executes raw Java syntax**: the source code still has to be compiled into an executable form.

### Step 5: When targeting Java 17 explicitly

If you are using a newer JDK to build for a Java 17 environment, use:

```bash
javac --release 17 HelloJava17.java
```

The `--release 17` option tells the compiler to target the language level, class file format, and standard APIs of Java 17. **`--release` is not a substitute for checking third-party dependencies or testing on the target runtime.** With a JDK 17 compiler when no other option is specified, the default target is already Java 17.

## 8. Choosing the Right Component in Practical Scenarios

| Scenario | Component to Focus On | Explanation |
| --- | --- | --- |
| Starting to learn Java 17 on a laptop | **A JDK 17 distribution** | Includes `javac` for compiling and a runtime to run examples. |
| Reading `java.util` docs or `switch` syntax | **Java SE 17** | The specification and API docs tell you what is supported in version 17. |
| Comparing Eclipse Temurin and Amazon Corretto 17 | **OpenJDK-based distributions** | Review update policies, security, support, licensing, and supported platforms. |
| Application runs slowly or needs garbage collector tuning | **Specific JVM and runtime** | The JVM executes the program and provides optimization/GC mechanisms; options may vary by implementation. |
| Building a project in CI | **JDK and compiler version** | Use the right toolchain version rather than only looking at the Java version on a local machine. |
| Running a packaged Java application | **Compatible runtime** | Needs a JVM and the modules/libraries used by the app; a compiler is not required on the target machine. |
| Packaging a compact runtime for a modular app | **`jlink` in the JDK** | Builds a custom runtime image containing only the selected modules. |

## 9. Common Misconceptions

**“Java SE 17 is itself a JDK you download.”** Conceptually incorrect. Java SE is the platform/specification; JDK 17 is the software implementation you install to use that platform.

**“OpenJDK is just a JVM.”** Incorrect. OpenJDK also includes the compiler, Java SE libraries, development tools, and the HotSpot JVM implementation.

**“JDK and JVM are interchangeable terms.”** Incorrect. The JVM is the engine that executes bytecode; the JDK includes the JVM/runtime along with tools such as `javac`.

**“I installed `java`, so I definitely have `javac`.”** Not necessarily. You should check both commands and their installation paths separately, especially when multiple Java installations exist on the machine.

**“A Java application runs everywhere without checking versions.”** Incorrect. Java 17 bytecode requires a JVM new enough to understand the corresponding class file version; library dependencies, modules, configuration, and OS specifics also matter.

**“To run Java 17, you must find a separate JRE installer.”** Incorrect. The runtime included with JDK 17 can run programs; for certain deployment scenarios you can also package a custom runtime image.

**“Spring Boot, Jakarta EE, and Java SE are at the same layer.”** Incorrect. Java SE is the foundational standard platform; frameworks and other application platforms have their own scope, APIs, and ecosystems, typically running on top of a compatible Java JDK/runtime.

## 10. Check Your Understanding

1. **If you only want to compile a `Hello.java` file, which tool does that?** → `javac` in the JDK.
2. **If you only have a `Hello.class` file, which component executes the bytecode?** → The JVM started via the `java` launcher in a compatible runtime.
3. **If you want to know whether `List.of(...)` is part of the Java 17 API, where should you check?** → The Java SE 17 specification and API documentation.
4. **If one machine uses Temurin 17 and another uses Corretto 17, can they both run the same Java SE 17 program?** → Usually yes, provided the program and its dependencies are compatible with both environments.
5. **If you compile for Java 17 and try to run it on Java 11, where can the error come from?** → A Java 11 JVM does not support class file version 61 produced by Java 17.

Whenever you encounter a Java issue, determine whether it lies in **Java SE rules/APIs**, **OpenJDK source code or a distribution**, **JDK tooling**, or **JVM runtime behavior**. Identifying the right layer helps you pick the right documentation, configuration, and troubleshooting tools.

## Official References

- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html)
- [Java Virtual Machine Specification, Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/index.html)
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/index.html)
- [OpenJDK — JDK 17 Project](https://openjdk.org/projects/jdk/17/)
- [JDK 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html)
