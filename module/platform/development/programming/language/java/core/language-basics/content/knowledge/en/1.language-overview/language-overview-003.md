# Distinguishing Java, Java SE, the JDK, and the Runtime Environment

> **Topic:** Java core — language-basics / Overview  
> **Goal:** Know precisely *which language* you are writing in, *which platform* you rely on, *which toolkit* you use to build, and *what is needed* to run the application. After this lesson, you can use `javac` and `java` to compile and run a simple program yourself, identify the environment being used, and explain common version mismatch errors.

## 1. Why Are These Four Names Easily Confused?

A beginner often says: “I have installed Java, so I can write and run any Java program.” That statement is not specific enough: does the machine have the **compiler tool**? Does it have a **Java Virtual Machine**? Which **platform version** was the program built for? Which installation does the `java` command in the terminal actually point to?

A useful way to distinguish them:

| Name | What is it? | What is it used for? | Identifying question |
| --- | --- | --- | --- |
| **Java (the language)** | A programming language with syntax, data types, classes, methods, and semantic rules | Writing `.java` source code | “What language is this code written in?” |
| **Java SE** (*Java Platform, Standard Edition*) | The standard platform: the relevant specifications and core Java APIs | Defining standard capabilities that typical Java programs rely on, e.g., `java.lang`, `java.util`, `java.io` | “Which standard Java platform/API does the application rely on?” |
| **JDK** (*Java Development Kit*) | The development toolkit along with the capability to run Java | Compiling, running, packaging, and inspecting programs; includes `javac`, `java`, `jar`… | “Which tools do I use to write, compile, and build the application?” |
| **JVM** (*Java Virtual Machine*) | The virtual machine that executes Java bytecode | Loading, verifying, and executing `.class` code, managing many runtime aspects | “What actually executes the bytecode?” |
| **JRE / runtime environment** | The capability to run applications: the virtual machine and required runtime libraries/components | Executing built programs without necessarily needing a compiler | “What components does the target machine need in order to run?” |

**Do not treat these as five competing products.** These names only refer to *different layers* of the same ecosystem. A typical JDK includes the components needed to develop **and** run; a minimal runtime may not contain the `javac` tool.

### Putting Each Concept in Its Right Place

In a standard workflow, `.java` source code is written in the **Java language**; `javac` from the **JDK** produces `.class` bytecode; the `java` command starts the **JVM** to run the class along with the needed runtime libraries. **Java SE** defines the standard platform and APIs that a compatible implementation provides.

This lesson focuses on **choosing and verifying the right environment**. Class loading mechanisms, bytecode, and compilation steps are practiced in depth in the lesson on source code → compiler → bytecode → JVM.

## 2. Java: Language Name vs. Platform Name

At the language level, Java specifies things such as type declarations, expressions, classes, interfaces, conditional statements, exception handling, and how methods are called. For example:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Java!");
    }
}
~~~

This is **source code written in the Java language**. The file is named `Hello.java` because it contains the public class `Hello`.

However, `System.out.println` is not just language syntax: `System` and `PrintStream` are classes provided by the platform. To run the program, you need an environment that has those corresponding standard components.

In everyday conversation, the term **“Java”** sometimes refers to the language, the platform, and the tools all at once. When configuring environments or explaining errors, refer specifically to **JDK**, **JVM**, **Java SE**, or **Java source** to avoid confusion.

## 3. Java SE: The Standard Platform, Not an Installer Command Name

**Java SE** stands for *Java Platform, Standard Edition*, focusing on the platform capabilities commonly used by general Java applications:

- The language and compatibility rules corresponding to a given Java version.
- The virtual machine and specifications related to Java execution.
- Standard libraries/APIs, such as the packages `java.lang` (core types), `java.util` (collections), `java.time` (date and time), `java.nio.file` (files/paths), and `java.net` (networking).
- Specific features depending on the **Java SE version**.

Java SE is **not** a `java-se.exe` file or a program you run with a `java-se` command. A JDK distribution is created to implement the corresponding Java platform, providing the compiler and development tools.

**Specifications, implementations, and distributions are different:**

| Concept | Meaning |
| --- | --- |
| Java SE specification | Defines the standard behaviors and APIs to be satisfied |
| Implementation | Software code that fulfills the platform/VM requirements |
| JDK distribution | An actual installer package from a vendor, containing tools and runtime |

For example, **OpenJDK** is an open-source Java implementation project; organizations can release JDK builds based on OpenJDK. For a beginner, the most important things are choosing a **JDK with a suitable version** and checking the tool paths—not looking for a separate program named “Java SE”.

**Scope:** Java SE is the core platform. An enterprise web application may also use Jakarta EE, Spring, or other libraries; those libraries/frameworks **do not automatically become standard Java SE APIs**. This lesson does not go into those platforms.

## 4. JDK, JVM, JRE: Who Compiles and Who Runs?

### 4.1. JDK — The Development Toolkit

A typical JDK includes:

| Tool | Common Role |
| --- | --- |
| `javac` | Compiles `.java` source code into `.class` bytecode |
| `java` | Launches a Java program and the appropriate execution environment |
| `jar` | Creates, views, or manipulates JAR files |
| `javadoc` | Generates documentation from JavaDoc comments |
| `jshell` | Evaluates Java expressions/commands interactively (modern JDKs) |
| `jlink` | Builds a custom runtime image from required modules (JDK 9+) |

When learning and building core Java applications, **installing a JDK** is the easiest choice because it includes both the compiler and the runtime. An IDE such as IntelliJ IDEA or VS Code is an editor/development environment **distinct from the JDK**; an IDE may download or select a JDK automatically, but the IDE itself is not synonymous with the JDK.

### 4.2. JVM — The Execution Component in the Runtime

**The JVM executes bytecode** and manages aspects such as class loading, memory, and exceptions; modern JVMs may combine interpretation and JIT compilation. It is not the `javac` compiler. The `java` command starts a runtime containing a JVM along with the needed libraries. A JVM build must match the operating system, CPU, and class file version, while bytecode can generally be shared across many compatible JVMs.

Installing a common JDK usually already includes the runtime and JVM to run examples; learners do not need to download a separate JVM just because they see JDK/JVM concepts in diagrams.

### 4.3. JRE — Understanding It in Version Context

**JRE** (*Java Runtime Environment*) is a familiar term for the set of components to **run** an application: the VM and required runtime libraries/files, without requiring full development tools like `javac`.

- In many older Java releases (especially Java 8), learners often encountered a **separate JRE package** or a `jre` folder inside the JDK.
- Starting from the modern modular Java generation (Java 9+), packaging changed. **Do not assume** every JDK has a separate `jre` directory or a standalone JRE installer.
- Some vendors still distribute runtime-only builds; applications can also bundle a runtime image created with `jlink`. Therefore, saying flatly “modern Java no longer has a JRE” is **inaccurate**.

Distinguish by *capability*: a machine that has **`java` to run** does not necessarily have **`javac` to compile**. A machine with a properly installed JDK normally has both.

## 5. Hands-On: Checking, Compiling, and Running a Program

The examples use **JDK 17 or later** to keep commands consistent. You can use a newer JDK, but choose the version required by your project/course.

### Step 1 — Check the Tools on Your Machine

Open a terminal and run:

~~~bash
java -version
javac -version
~~~

The first command shows the Java runtime/launcher currently found; the second shows the Java compiler currently found. Actual output depends on the JDK/distribution you installed. **The two commands do not necessarily point to the same installation**, because `PATH` may contain multiple JDKs/JREs; therefore, check whenever you see mismatched versions.

You can also run:

~~~bash
java --version
javac --version
~~~

The `--version` syntax applies to modern JDKs. For older Java environments, the `-version` form is more common.

**If `java` exists but `javac` does not:** you may be using a runtime-only installation, or `PATH` may be pointing to a directory without the compiler. Do not immediately conclude that “Java is broken”.

### Step 2 — Write a Source File That Inspects the Runtime

Create the file **JavaEnvironmentDemo.java** (matching the exact capitalization of the public class name) and copy the following code:

~~~java
public class JavaEnvironmentDemo {
    public static void main(String[] args) {
        String who = args.length == 0 ? "Java" : args[0];

        System.out.println("Xin chào, " + who + "!");
        System.out.println("Java version : "
                + System.getProperty("java.version"));
        System.out.println("Java vendor  : "
                + System.getProperty("java.vendor"));
        System.out.println("VM name      : "
                + System.getProperty("java.vm.name"));
        System.out.println("Runtime home : "
                + System.getProperty("java.home"));
        System.out.println("Số tham số   : " + args.length);
    }
}
~~~

Points to understand:

- `main(String[] args)` is the program's entry point in traditional class execution mode.
- `System.getProperty("java.version")` describes the **environment currently running the program**, not which compiler built the `.class` file.
- `java.vm.name` shows the current VM name; `java.vendor` shows the vendor reported by the runtime.
- `java.home` is the **runtime path currently in use**; it is not necessarily equal to the `JAVA_HOME` environment variable.
- `args` holds the arguments after the class name when invoking the `java` command.

### Step 3 — Compile and Then Run

In the directory containing the source file:

~~~bash
mkdir out
javac -encoding UTF-8 -d out JavaEnvironmentDemo.java
java -cp out JavaEnvironmentDemo VietNam
~~~

First, `mkdir out` creates the destination directory `out` (only needed if the directory does not exist yet). Because the source code contains Vietnamese characters, `-encoding UTF-8` helps `javac` read the UTF-8 file properly, even on machines whose default encoding is not UTF-8; this option **does not** automatically change the terminal encoding. `javac -d out` writes the `.class` file into the existing destination directory; when there is a `package`, `javac` can create the corresponding subdirectories. `java -cp out JavaEnvironmentDemo` finds the class there and runs the `main` method.

Illustrative output—the version and path parts **will differ between machines**:

~~~text
Xin chào, VietNam!
Java version : <running version>
Java vendor  : <runtime vendor>
VM name      : <Java VM name>
Runtime home : <runtime path>
Số tham số   : 1
~~~

The strings in angle brackets in the output example are only **placeholders**, not literal text Java prints.

Run again without passing any arguments:

~~~bash
java -cp out JavaEnvironmentDemo
~~~

This time the program prints `Xin chào, Java!` and `Số tham số   : 0`. Same `.class` file, different output due to **runtime arguments**.

### Step 4 — Two Different Ways to Launch

On JDK 11+, you can also run `java JavaEnvironmentDemo.java VietNam` using *source-file mode*. The launcher compiles the source for that run; no separate `javac` command is needed. With `java -cp out JavaEnvironmentDemo VietNam`, the launcher finds the **compiled class** in `out`. Both still use the Java runtime; they differ in the **input given to the launcher** and the bytecode preparation step.

### Step 5 — When You Need to Package a JAR

After compiling into the `out` directory, you can create a runnable JAR:

~~~bash
jar --create --file demo.jar --main-class JavaEnvironmentDemo -C out .
java -jar demo.jar VietNam
~~~

The `jar` command is part of the JDK toolkit. The `--main-class` option writes entry point information into the manifest; if a JAR does not specify a valid main class, `java -jar` will not know where to start. This is a simple application JAR **without external libraries**; for a project with dependencies, you must package or provide them appropriately.

## 6. What Does the Machine Running the Application Need?

**A program that only uses Java SE APIs** needs a runtime compatible with the bytecode and APIs the program requires. This **does not require** the end user's machine to have a compiler or an IDE.

| Situation | What is needed? | Not required |
| --- | --- | --- |
| Writing and compiling Java source | Appropriate JDK, editor/IDE if desired | Spring, Maven for small examples |
| Running compiled `.class` files | Compatible Java runtime; proper classpath and entry point | `javac` on the target machine |
| Running an application JAR | Compatible runtime; JAR with valid manifest and all dependencies | IDE or source code |
| Running with a runtime bundled with the app | Runtime image containing needed modules/APIs, launch configuration | Full JDK on the user's machine |

A practical deployment pattern is **developer/CI machines use a JDK to build**, while production machines use a compatible runtime or bundled runtime image. Applications with external libraries, native libraries, environment variables, config files, databases, or networks must also satisfy those dependencies: the phrase “write once, run anywhere” **does not** eliminate every operating system and infrastructure difference.

## 7. JDK Versions and Runtime Compatibility

When inspecting a machine or CI configuration, separate the **JDK doing the compiling**, the **compatibility level built for**, and the **runtime actually executing**. The `javac -version` and `java -version` commands can report two different versions if `PATH` points to two installations.

| Situation | What to check |
| --- | --- |
| Building on a newer JDK to run on Java 17 | When the compiler supports it, use `javac --release 17 -encoding UTF-8 -d out JavaEnvironmentDemo.java` to target Java 17 syntax, class files, and standard APIs |
| Running a class on a JVM older than the compilation target | May encounter `UnsupportedClassVersionError`; check the runtime version and class file level rather than renaming files |
| Compiler and launcher come from two different JDK installations | Verify the actual locations of `java`, `javac`, and build configuration instead of looking only at `JAVA_HOME` |
| External libraries or native components are present | `--release` does not prove all dependencies and environmental conditions work on the target runtime; test the actual distribution |

The chosen version must match the requirements of the project, libraries, CI, and deployment environment. To check the **actual executing environment**, run `java -version` directly on the target machine or inspect the `java.version` and `java.home` properties in the sample program; do not infer it from the build machine.

## 8. JAVA_HOME, PATH, and Classpath: Three Different Roles

| Name | Meaning | Common Mistake |
| --- | --- | --- |
| `JAVA_HOME` | Environment variable often used by build tools to locate the JDK directory | Pointing to a different JDK than the one the terminal is using |
| `PATH` | List of directories the OS searches for commands like `java`, `javac`… | `java` and `javac` come from two different installations |
| **Classpath** (`-cp`/`--class-path`) | Where Java looks for application classes and certain resources | Compilation succeeds, but the runtime cannot find the main class or a dependency |

Some commands to inspect tool locations:

**Windows PowerShell:**

~~~powershell
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

**macOS / Linux (common terminal shells):**

~~~bash
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

You can have multiple JDKs installed on one machine. These inspection commands only help diagnose; **they do not fix the environment automatically**. Do not rush to change system-wide `PATH` when another project still needs an older version.

An example distinguishing classpath and file paths: after `javac -d out` produces `out/JavaEnvironmentDemo.class`, you run:

~~~bash
java -cp out JavaEnvironmentDemo
~~~

Do not run with `JavaEnvironmentDemo.class` in the class name position. `java` expects a **class name** (or a package-qualified class name), not the `.class` extension.

If the source has `package demo;` and the class is compiled to `out/demo/Main.class`, then the entry point is **`demo.Main`** and the command is typically `java -cp out demo.Main`. This is the class lookup mechanism, not a different tool from the JVM.

## 9. When Errors Occur: Diagnose the Environment Methodically

First, run `java -version` and `javac -version`, then find the actual locations of both commands with `where.exe` (Windows) or `command -v` (macOS/Linux). Compare the results against `JAVA_HOME` and the JDK chosen by your IDE/build tool. Once the compiler and runtime are confirmed, then inspect `-cp`, the class name, and dependencies.

| Symptom | Helpful Diagnostic Questions |
| --- | --- |
| `java` exists, but `javac` does not | Does the machine only have a runtime, or is `PATH` pointing to the wrong JDK `bin` directory? |
| Terminal uses Java A, but IDE builds with Java B | Which JDK is the IDE/Gradle selecting? Does `JAVA_HOME` take precedence differently from `PATH`? |
| Build succeeds, running throws `UnsupportedClassVersionError` | Which runtime version does the class file require, and which `java -version` is the target machine using? |
| `Could not find or load main class` | Does `-cp` point to the root directory containing the package, and are you using the fully qualified class name instead of `.class`? |
| Running a JAR fails with a missing class at runtime | Was the dependency actually packaged or placed on the classpath/module path? |

An error can happen at the launch or class-loading stage rather than because Java SE/JDK was “installed wrong”. Use the specific message to address the right component and preserve the setup for other projects on the machine.

## 10. Misconceptions to Avoid

- **JDK is not JVM.** The JDK is the development toolkit that includes a runtime; the JVM is the component that executes bytecode.
- **Java SE is not the name of one vendor's installer.** It is the standard platform/API; a specific JDK provides an implementation.
- **Having the `java` command does not guarantee having `javac`.** Check both running and compiling capabilities according to the machine's role.
- **“Modern Java has completely removed the JRE” is too broad a claim.** There are multiple runtime packaging forms, including runtime-only distributions and custom images via `jlink`; do not assume there must be a standalone `jre` folder.
- **The IDE and `JAVA_HOME` do not automatically dictate every terminal's outcome.** Check the actual `java`/`javac` path being invoked, the project's JDK, and the target runtime.

## 11. Self-Practice Exercises with Guided Solutions

**Exercise 1 — Use the right name:** A machine only needs to run a prebuilt `demo.jar`. Must that machine install a full JDK? Why?

*Guidance:* Not required. It needs a compatible runtime, the necessary libraries and dependencies, and a valid entry point. Only the build machine needs the compiler/JDK.

**Exercise 2 — Explain two commands:** Compare `javac -encoding UTF-8 -d out JavaEnvironmentDemo.java` with `java -cp out JavaEnvironmentDemo`.

*Guidance:* The first command produces `.class` bytecode; the second starts the runtime to locate and execute the compiled class. Do not include the `.class` extension in the entry point name.

**Exercise 3 — Analyze an environment:** `java -version` reports version A, while `javac -version` reports version B. Can you conclude the machine lacks a JDK?

*Guidance:* Not yet. Both might be installed while `PATH` prioritizes two different locations. Check the actual paths of both commands and the build/runtime targets.

**Exercise 4 — Reason about an error:** You compile with a newer compiler, copy the `.class` file to a machine running an older Java, and get `UnsupportedClassVersionError`. Should you rename the `.class` file to fix it?

*Guidance:* No. This is a bytecode format/version issue. Choose a compatible runtime or compile for a lower release that your code and libraries actually support.

**Exercise 5 — Experiment:** Run the `JavaEnvironmentDemo` example in two ways: (a) `javac` then `java -cp`, and (b) `java JavaEnvironmentDemo.java`. Record what is the same in the output content and what differs in how the launcher prepares the code to run.

### Self-Check Before Moving On

You have mastered this lesson if you can explain in your own words: **Java is the language; Java SE is the standard platform; the JDK lets you build and also run programs; the JVM executes bytecode; the runtime/JRE is the set of components needed to run**. When opening a terminal, you know how to check `java`/`javac`, run an example, recognize the classpath, and explain why build and runtime versions must be compatible.
