# What is JDK Tooling?

## 1. Concept

**JDK Tooling** is the collection of tools included with the **Java Development Kit (JDK)** that supports the entire lifecycle of developing and operating Java applications: checking the environment, compiling source code, running programs, packaging, generating documentation, analyzing dependencies, creating custom runtimes, managing certificates, and diagnosing running applications.

JDK Tooling is not a single program. It consists of many specialized commands and utilities, typically run from a Terminal or Command Prompt and invoked behind the scenes by IDEs and build systems.

For example, when you run `javac`, you use the Java compiler. When you run `jar`, you package compiled classes into a JAR file. When you run `jcmd` or `jstack`, you inspect the state of a running Java process.

The goal of tooling is to give developers explicit control over technical steps rather than relying solely on the Run button in an IDE.

## 2. JDK, JVM, and Related Tools

To understand JDK Tooling, you need to distinguish three concepts:

- **JVM (Java Virtual Machine):** the execution environment for Java bytecode. The JVM loads classes, verifies bytecode, manages memory, performs garbage collection, and can compile frequently executed code into machine code using a JIT compiler.
- **JDK (Java Development Kit):** the Java development kit. The JDK provides the runtime to execute applications, the standard library, the compiler, and various utilities for development, packaging, inspection, and diagnostics.
- **JDK tools:** programs such as `java`, `javac`, `jar`, `javadoc`, `jshell`, `jdeps`, `jlink`, `jpackage`, `keytool`, and `jcmd`.

Basic workflow when developing a Java program:

```text
.java source code
      |
      | javac
      v
.class bytecode
      |
      | jar (optional)
      v
.jar file
      |
      | java
      v
JVM executes the program
```

A `.class` file contains bytecode, not machine code specific to a single CPU. The JVM on each platform is responsible for executing bytecode and interacting with the operating system. Therefore, the same JAR can run on multiple operating systems as long as those platforms have a compatible runtime and the application does not depend on OS-specific components.

In modern Java versions, the JDK already includes the environment needed to run applications. The concept of installing a separate JRE was common in older versions; from Java 9 onward, the module system and custom runtime images make runtime distribution more flexible. When learning and developing applications, you normally install an appropriate JDK instead of looking for a separate JRE package.

## 3. Important Tool Categories

Exact names and usage details may vary slightly depending on the JDK version, vendor, and operating system. The tools below are commonly encountered in modern JDKs and are especially useful when working with Java 17 or later.

| Tool | Function | When to use |
|---|---|---|
| `java` | Launches a Java application, main class, JAR, or module | Running a program |
| `javac` | Compiles `.java` source code into `.class` bytecode | Compiling an application |
| `jar` | Creates, inspects, and updates JAR files | Packaging an application or library |
| `javadoc` | Generates HTML documentation from source code and JavaDoc comments | Generating API documentation |
| `jshell` | REPL environment for testing Java expressions and statements | Learning, trying APIs, or quickly testing ideas |
| `javap` | Disassembles class information and bytecode | Inspecting method signatures, modifiers, and bytecode |
| `jdeps` | Analyzes dependencies between classes, JARs, and modules | Checking dependencies, preparing to migrate to modules |
| `jdeprscan` | Detects usage of APIs marked as deprecated | Auditing code before upgrading |
| `jlink` | Creates a custom runtime image from modules | Distributing a smaller runtime |
| `jpackage` | Packages an application into a platform-specific installer | Distributing desktop or standalone applications |
| `keytool` | Manages keystores, keys, and digital certificates | Working with TLS, certificates, and keys |
| `jarsigner` | Signs and verifies JAR signatures | Verifying the origin and integrity of a JAR package |
| `jcmd` | Sends diagnostic commands to a JVM process | Inspecting threads, runtime, heap, and Java Flight Recorder |
| `jstack` | Captures thread dumps | Investigating deadlocks or hung threads |
| `jmap` | Displays heap information and generates heap dumps | Investigating memory issues |
| `jstat` | Displays JVM, garbage collection, and class loading statistics | Monitoring runtime activity |
| `jfr` | Reads and analyzes Java Flight Recorder recordings | Investigating performance |
| `jmod`, `jimage` | Works with JMOD files and runtime images | Advanced tasks involving modules and runtime images |
| `serialver` | Displays the `serialVersionUID` of a Serializable class | Checking serialization compatibility |

Not every distribution or minimal runtime environment includes all of these commands. A runtime image created with `jlink` may contain only the modules required to run the application, so it does not necessarily include the compiler or diagnostic tools.

### 3.1. Compilation and Execution Tools

- `javac`: translates Java source code into bytecode. You can specify the output directory, classpath, module path, and target API version.
- `java`: launches a program from a class, JAR, or module. This command also accepts JVM configuration options such as heap memory, garbage collector, and system properties.
- `jshell`: lets you enter Java statements interactively without creating a full project.
- `javap`: lets you inspect the structure of compiled classes, useful when learning about bytecode or checking the API provided by a library.

### 3.2. Packaging and Documentation Tools

- `jar`: bundles `.class` files, resources, and metadata into a JAR archive.
- `javadoc`: generates API documentation from comments written with JavaDoc syntax such as `/** ... */`.
- `jpackage`: creates distribution packages or installers for the target operating system. Supported installer formats depend on the platform and corresponding system tools.

### 3.3. Module and Dependency Tools

- `jdeps`: shows which packages and modules an application or library depends on. This is a useful step when removing unnecessary dependencies or preparing to use JPMS.
- `jlink`: assembles the required modules into a custom runtime image. An application can be distributed with this runtime without requiring users to install a full JDK.
- `jmod` and `jimage`: support module and runtime image formats at a lower level.

### 3.4. Security Tools

- `keytool`: creates and manages keystores, key pairs, and certificates. Keystores are commonly used when configuring HTTPS/TLS or signing applications.
- `jarsigner`: signs JAR files with an appropriate key and verifies the signature of signed packages.

Treat keystores and their passwords as sensitive information. Never commit private keys or passwords to repositories, build logs, or public documentation.

### 3.5. Runtime Diagnostic Tools

- `jcmd`: communicates with a JVM process to retrieve information or trigger a diagnostic action.
- `jstack`: captures stack traces of threads at a point in time.
- `jmap`: helps inspect the heap and generate heap dumps.
- `jstat`: displays runtime metrics periodically.
- `jfr`: reads Java Flight Recorder recordings; starting and stopping recordings is typically controlled via `jcmd`.

These tools are useful when an application is slow, consumes high CPU, shows signs of a memory leak, stops responding, or is suspected of having a deadlock.

## 4. Checking and Configuring the JDK Environment

Before using tooling, verify which JDKs are installed on your machine and whether your Terminal is invoking the intended version.

Run these commands:

```bash
java --version
javac --version
jshell --version
```

`java --version` shows the runtime launcher version. `javac --version` confirms the compiler is available and shows the compiler version. Both should be checked together because a machine may have multiple JDKs installed and `PATH` might point to different versions.

You can check which executable paths the operating system resolves:

- Windows PowerShell: `Get-Command java` and `Get-Command javac`.
- Windows Command Prompt: `where java` and `where javac`.
- Linux/macOS: `which java` and `which javac`.

### 4.1. JAVA_HOME and PATH

`JAVA_HOME` typically points to the root directory of the JDK, for example:

```text
C:\Program Files\Java\jdk-17
```

`PATH` needs to include the `bin` directory inside the JDK:

- Windows: `%JAVA_HOME%\bin`
- Linux/macOS: `$JAVA_HOME/bin`

Do not set `JAVA_HOME` to point directly to the `bin` directory. Many build tools, IDEs, and scripts rely on `JAVA_HOME` to locate the JDK.

If your machine has multiple JDKs, check `JAVA_HOME`, `PATH`, and the output of `java --version`/`javac --version`. Updating only one variable while ignoring the others can cause your terminal, IDE, and build system to use different JDKs.

## 5. Practical Example: Compiling and Running a Program

The following example uses Java 17 or later. Create the file `src/com/example/Hello.java` with the following content:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, JDK Tooling!");
    }
}
```

Create the output directory `out`, then compile:

```bash
mkdir out
javac --release 17 -d out src/com/example/Hello.java
```

Meaning of the options:

- `--release 17`: compiles against the language features, bytecode, and public APIs of Java 17. This option is suitable when using a newer JDK while ensuring compatibility with Java 17.
- `-d out`: writes `.class` files into the `out` directory. Because the class declares `package com.example`, the compiler automatically creates the corresponding directory structure inside `out`.

Run the program:

```bash
java -cp out com.example.Hello
```

Output:

```text
Hello, JDK Tooling!
```

In the command above:

- `-cp out` adds the `out` directory to the classpath so the JVM can find the compiled class.
- `com.example.Hello` is the fully qualified class name, consisting of the package and class name.
- The `main` method is the entry point of the program under the traditional launch mechanism.

If the `out` directory already exists, you do not need to create it again. These commands can be run in a Terminal at the project root directory; path syntax may vary depending on the shell and operating system.

## 6. Practical Example: Packaging into a JAR

After compiling successfully, use `jar` to create a JAR with a declared main class:

```bash
jar --create --file app.jar --main-class com.example.Hello -C out .
```

Meaning:

- `--create`: creates a new JAR.
- `--file app.jar`: specifies the output file name.
- `--main-class com.example.Hello`: writes the main class into the JAR manifest.
- `-C out .`: changes to the `out` directory and includes its contents in the JAR.

List the contents of the JAR:

```bash
jar --list --file app.jar
```

Run the JAR:

```bash
java -jar app.jar
```

The program output remains:

```text
Hello, JDK Tooling!
```

This illustrates how `javac`, `jar`, and `java` work together: compiling source code, packaging bytecode, and launching the packaged application.

## 7. Other Useful Tooling Operations

### 7.1. Quick Experiments with JShell

Open JShell:

```bash
jshell
```

Enter an expression:

```java
int total = 12 + 8;
System.out.println(total);
```

JShell executes the statements immediately in an interactive session. Exit with:

```text
/exit
```

JShell is suitable for trying out an API, testing an expression, or demonstrating a language feature. For applications that need to manage multiple classes, dependencies, and project structure, use a standard Java project.

### 7.2. Inspecting Bytecode with javap

After compiling the example above:

```bash
javap -classpath out -c com.example.Hello
```

`-classpath out` tells `javap` where to find the class. `-c` requests the disassembled bytecode for the methods. This is a way to observe how Java source code is translated into bytecode instructions executed by the JVM.

### 7.3. Generating Documentation with javadoc

From the project root directory:

```bash
javadoc -d docs src/com/example/Hello.java
```

HTML documentation is generated in the `docs` directory. To make documentation useful for library users, write JavaDoc comments for classes, constructors, and public API methods. `javadoc` can emit warnings when comments are missing or documentation details are incomplete.

### 7.4. Analyzing Dependencies with jdeps

```bash
jdeps --summary app.jar
```

This command summarizes the module dependencies of the JAR. The output can help identify which modules are needed when building a runtime image with `jlink`.

### 7.5. Creating a Runtime Image with jlink

Example of creating a minimal runtime containing only the `java.base` module:

```bash
jlink --add-modules java.base --output runtime-image
```

`jlink` assembles the required modules into a custom runtime image. An application can be distributed with this runtime without requiring users to install a full JDK.

This runtime image contains a runtime capable of executing applications that only use APIs from `java.base`. If the application uses other modules, you must add the corresponding modules, for example using the module list obtained from dependency analysis and application configuration.

This runtime image is not a full JDK: it is built to run the application, not to provide the full set of compilers and development tools.

### 7.6. Diagnosing Java Processes with jcmd

List JVM processes detectable by the tool:

```bash
jcmd -l
```

View the JVM version of a process:

```bash
jcmd <pid> VM.version
```

Capture a thread dump:

```bash
jcmd <pid> Thread.print
```

Here `<pid>` is the process ID of the Java application. You can also use `jstack <pid>` for the same purpose of capturing a thread dump.

### 7.7. Monitoring Garbage Collection with jstat

```bash
jstat -gc <pid> 1000 5
```

This command requests GC statistics for the process at a sampling interval of 1,000 milliseconds, up to 5 times. The columns report information about heap regions and garbage collection activity; the exact meaning of each column should be checked against the documentation for the JDK version in use.

### 7.8. Recording with Java Flight Recorder

You can instruct the JVM to start a JFR recording for 60 seconds:

```bash
jcmd <pid> JFR.start duration=60s filename=app.jfr
```

After the recording is created, view the summary:

```bash
jfr summary app.jfr
```

JFR collects runtime events for performance and application behavior analysis. When investigating slowness, combine JFR data with logs, metrics, and real load information.

### 7.9. Inspecting a Keystore with keytool

Example of listing the contents of a PKCS12 keystore:

```bash
keytool -list -keystore my-keystore.p12 -storetype PKCS12
```

The command may prompt for the keystore password. Never record real passwords in scripts or shared terminal histories.

## 8. JDK Tooling and Maven, Gradle, IDEs

JDK Tooling is the technical foundation that many other development tools build upon:

- **Maven** and **Gradle** are build and dependency management tools. They orchestrate steps such as compiling, running tests, packaging, and producing artifacts; they typically invoke the compiler and runtime from a configured JDK.
- **IDEs** such as IntelliJ IDEA, Eclipse, or VS Code provide interfaces for writing code, debugging, refactoring, and managing projects. An IDE may invoke `javac`, `java`, and other JDK tools behind the scenes.
- **Frameworks and libraries** such as Spring or JUnit provide functionality for applications and testing. They are not JDK commands and are typically managed as project dependencies.

Therefore, installing a JDK does not mean Maven or Gradle is installed. Conversely, a project using Maven or Gradle still requires an appropriate JDK to compile and run Java tasks.

## 9. Common Errors

| Symptom | Common cause | Resolution |
|---|---|---|
| `javac` is not recognized | JDK is not installed or `PATH` does not include the JDK's `bin` directory | Check the JDK installation, `JAVA_HOME`, `PATH`, and `Get-Command`/`where`/`which` |
| `java` and `javac` have different versions | `PATH` points to multiple Java installations or the terminal uses a different JDK than the IDE | Check the paths and JDK configuration of each tool |
| `UnsupportedClassVersionError` | The running runtime is older than the bytecode version produced by the compiler | Use a compatible runtime or compile with the appropriate `--release` |
| `Could not find or load main class` | Incorrect classpath, incorrect package/class name, or running from the wrong directory | Check `-cp`, directory structure, and the fully qualified class name |
| Unable to run `java -jar` | The JAR is missing a manifest or does not declare a valid `Main-Class` | Rebuild the JAR with `--main-class` or configure the manifest |
| `NoSuchMethodError` at runtime | The library version at runtime differs from the version at compile time, or dependencies conflict | Inspect the dependency tree and actual runtime classpath |
| `jcmd` cannot see or attach to a process | Different OS user, attach restrictions, container isolation, or runtime configuration | Check permissions, process environment, and platform limits |

A few notes when troubleshooting:

1. If `java` runs but `javac` does not exist, check whether only a minimal runtime is installed or whether `PATH` points to a different runtime.
2. If multiple JDKs are installed, check the version in your terminal, IDE, and Maven/Gradle. Do not assume all of them use the same JDK.
3. On Windows, the classpath separator for multiple entries is typically a semicolon (`;`); on Linux/macOS it is typically a colon (`:`).
4. When using packages, the class name passed to run must include the package. For example, `com.example.Hello`, not just `Hello`.
5. Tools that generate heap dumps or collect diagnostic data can impact performance and produce large files. Heap dumps may contain sensitive data from application memory, so protect those files and collect them only when appropriate.

## 10. Choosing the Right Tool for the Job

| Need | Tool to start with |
|---|---|
| Check whether Java is installed properly | `java --version`, `javac --version` |
| Compile source code | `javac` |
| Run a program | `java` |
| Try a small Java snippet | `jshell` |
| Inspect bytecode or class structure | `javap` |
| Package an application | `jar` |
| Generate API documentation | `javadoc` |
| Check module dependencies | `jdeps` |
| Create a custom runtime | `jlink` |
| Create an application installer | `jpackage` |
| Manage certificates and keys | `keytool`, `jarsigner` |
| Inspect threads of a running application | `jcmd`, `jstack` |
| Investigate memory | `jcmd`, `jmap`, `jstat` |
| Analyze performance via runtime events | `jcmd`, `jfr` |

## 11. Summary

JDK Tooling is the toolkit that helps developers work directly with source code, bytecode, the runtime, and Java application distribution. The most important commands to get familiar with first are:

- `java` to run programs.
- `javac` to compile.
- `jar` to package.
- `jshell` for quick experimentation.
- `javadoc` to generate documentation.
- `javap` and `jdeps` to inspect structure and dependencies.
- `jcmd`, `jstack`, `jstat`, and `jfr` for runtime diagnostics.

Once you understand the role of each tool, you can read the commands that IDEs or build systems execute, compile and package a small application yourself, and know where to start when troubleshooting an issue in a Java process.
