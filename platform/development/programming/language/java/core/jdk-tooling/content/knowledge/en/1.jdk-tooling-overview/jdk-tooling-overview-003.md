# JDK and JRE

JDK and JRE are both related to using the Java platform, but they serve two different purposes:

- **JDK (Java Development Kit)** provides tools to write, compile, test, and package Java programs. Java developers need the JDK.
- **JRE (Java Runtime Environment)** is the environment required to run compiled Java programs.
- **JVM (Java Virtual Machine)** is the virtual machine that executes Java bytecode. The JVM is a core component of the Java runtime environment.

A quick way to remember: **The JDK is for development; the JRE is for running; the JVM executes bytecode.**

## 1. How are Java programs compiled and run?

A typical Java program goes through the following steps:

1. The developer writes source code in a `.java` file.
2. The `javac` compiler converts the source code into bytecode and saves it in a `.class` file.
3. The JVM loads, verifies, and executes the bytecode. Depending on the JVM, the code may be interpreted or Just-In-Time (JIT) compiled into native machine code to improve performance.
4. At runtime, the program uses classes and APIs from the standard Java library, along with the necessary runtime components.

Bytecode is designed to run across multiple operating systems and hardware architectures. However, each platform requires an appropriate JVM installation. Therefore, the same `.class` file can run on Windows, macOS, or Linux if a compatible Java environment is installed.

## 2. What is the JVM?

**JVM (Java Virtual Machine)** is the virtual machine that defines how Java bytecode is loaded and executed. The JVM creates an abstraction layer between the Java program and the operating system.

Some key responsibilities of the JVM:

- **Class Loading:** finding and loading required classes when the program runs.
- **Bytecode Verification:** checking the structure and validity of bytecode before execution.
- **Execution:** interpreting bytecode or using a JIT (Just-In-Time Compiler) to compile hot code paths into machine code.
- **Memory Management:** organizing runtime memory areas and working with the Garbage Collector to reclaim objects that are no longer in use.
- **Providing the Execution Environment:** supporting threads, exceptions, synchronization, and other runtime mechanisms.

The JVM is a specification; vendors can build different JVM implementations. An implementation must match the operating system and architecture it runs on.

## 3. What is the JRE?

**JRE (Java Runtime Environment)** is the environment for running a Java application. Under the traditional model, the JRE includes:

- The JVM to execute bytecode.
- The standard Java libraries that the application needs at runtime.
- Other supporting runtime files and components.

The JRE is aimed at users who need to **run** Java applications. A user who only runs a packaged application generally does not need development tools such as the `javac` compiler.

The JRE is not a different version of Java from the JDK. It is the term for the runtime environment and the components needed to run an application. How the JRE is packaged depends on the Java version and the distribution vendor.

## 4. What is the JDK?

**JDK (Java Development Kit)** is the toolkit for Java software development. The JDK provides a runtime environment along with tools for creating and testing programs.

Common tools include:

| Tool | Purpose |
| --- | --- |
| `java` | Launches Java applications |
| `javac` | Compiles `.java` source code into `.class` bytecode |
| `jar` | Creates and manipulates JAR files |
| `javadoc` | Generates API documentation from source code and comments |
| `jshell` | Interactively evaluates Java expressions and statements |
| `jdb` | Debugs Java programs |
| `jlink` | Creates a custom runtime image from required modules |

Specific tool names and sets may vary by version or vendor. The JDK is the right choice when writing code, compiling, testing, debugging, or packaging Java applications.

## 5. How do the JDK, JRE, and JVM relate to each other?

You can think of their relationship by function:

- The JVM executes bytecode.
- The JRE provides the JVM, libraries, and components needed to run applications.
- The JDK provides development tools, and also includes a runtime to run and test applications.

The following table helps distinguish the three concepts:

| Criterion | JVM | JRE | JDK |
| --- | --- | --- | --- |
| Purpose | Executes bytecode | Runs Java applications | Develops and runs applications |
| Main components | Execution virtual machine | JVM and runtime libraries | Runtime plus development tools |
| Includes `javac` compiler | No | Typically no | Yes |
| Target audience | Runtime platform component | End users/hosts running applications | Developers and build environments |
| Role | Execution | Provides runtime environment | Provides development toolkit |

**Note:** This table describes roles and the conceptual component model. Modern Java distributions may organize or package components differently; you should not rely solely on directory names to conclude whether a component is present.

## 6. Why did JRE packaging change across Java versions?

In older Java versions, especially Java 8, users commonly saw two separate installers: the JDK for development and the JRE for running applications. In many Java 8 distributions, the JDK installation directory also contained a subdirectory named `jre`.

Starting with Java 9, Java moved to a module system. The runtime can be organized as a runtime image containing only the required modules. As a result, the installation layout no longer necessarily includes a `jre` directory inside the JDK.

Additionally, Oracle no longer ships a separate JRE installer in the traditional way alongside Oracle JDK 11 and later. However, some other Java vendors may still provide runtime-only or separate JRE packages.

Therefore:

- Not seeing a `jre` folder inside a modern JDK directory does not mean the JDK lacks the ability to run Java.
- Download package names and directory layouts depend on the vendor.
- When deploying an application, check the documentation of your distribution and the application's runtime requirements.

## 7. When should you install the JDK, and when do you need a runtime?

**Install the JDK when:**

- You are learning or developing Java.
- You need to run `javac`, `jar`, `javadoc`, `jshell`, or other development tools.
- You run Maven, Gradle, or a build pipeline that requires a JDK.
- You need to compile and test applications on a personal machine or build server.

**Only a runtime is needed when:**

- The machine's only job is to run a compiled Java application.
- The application vendor only requires a compatible runtime.
- You are deploying a minimal runtime image that has already been built and tested for the application.

Installing the JDK on a machine that only runs applications can still work, but it usually brings along more tools than necessary. For deployment environments, a development team can use `jlink` to create a runtime image containing only the required modules. This approach should be tested with the actual application and libraries.

## 8. Checking if Java is installed

Open Terminal, Command Prompt, or PowerShell and run:

```bash
java -version
javac -version
```

- `java -version` displays the version of the Java launcher/runtime found via `PATH`.
- `javac -version` displays the compiler version. This tool is normally included in the JDK.

On Windows, you can identify which executables are selected using:

```powershell
where.exe java
where.exe javac
```

On macOS or Linux:

```bash
command -v java
command -v javac
```

If `java` runs but `javac` is not found, the machine may be pointing to a runtime-only package, or `PATH` may not point to the JDK's `bin` directory.

### JAVA_HOME and PATH

- `JAVA_HOME` typically points to the root directory of the JDK, for example `C:\Program Files\Java\jdk-17` on Windows or `/opt/jdk-17` on Linux.
- `PATH` must include the JDK's `bin` directory if you want to invoke `java`, `javac`, and other tools from any directory.
- Do not point `JAVA_HOME` directly to the `bin` directory; point it to the JDK root directory.

Example configuration in PowerShell for the current session:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

Example on Linux/macOS (replace the path with where the JDK is actually installed):

```bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
javac -version
```

Setting `JAVA_HOME` is not strictly required for the `java` command itself to work, but many build tools and development environments use this variable to locate the JDK.

## 9. Example: compiling and running a Java program

Create a file named `Hello.java` with the following content:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Java!");
    }
}
```

Open a terminal in the directory containing the file and run:

```bash
javac Hello.java
java Hello
```

Output:

```text
Xin chào Java!
```

Explanation:

1. `javac Hello.java` uses the JDK compiler to generate the `Hello.class` file.
2. `java Hello` launches the `Hello` class; the JVM loads and executes the bytecode in that class.
3. When running the `java` command, specify only the class name `Hello`, without the `.class` extension.

This example shows why a development environment needs the JDK: you need `javac` to compile. Once you have the bytecode, the machine running the application needs a compatible runtime to execute it.

## 10. Compatibility between compilation and runtime versions

An application compiled with a newer JDK may use bytecode or APIs that an older runtime does not support. When run on an overly old runtime, the program may throw `UnsupportedClassVersionError`.

With JDK 9 and later, the `--release` option lets you compile for a target Java version while restricting the standard Java APIs to those available in that version.

Example compiling a program for Java 17:

```bash
javac --release 17 -d out Hello.java
java -cp out Hello
```

Where:

- `--release 17` sets the target platform version to Java 17.
- `-d out` sets the output directory for `.class` files.
- `-cp out` adds the `out` directory to the classpath when running.

The runtime used to run the application must support the target bytecode version and the APIs used by the program. For real-world projects, you should align the JDK version across development, build, and deployment environments.

## 11. Common errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `javac` is not recognized | JDK is not installed or `PATH` does not point to the JDK | Install the JDK and verify the `bin` directory in `PATH` |
| `java` is not recognized | No suitable runtime is installed or `PATH` is incorrect | Install a suitable JDK/runtime and update `PATH` |
| `UnsupportedClassVersionError` | Runtime is older than the application's bytecode version | Upgrade the runtime or recompile with an appropriate target version |
| Build tool cannot find Java | `JAVA_HOME` is incorrect or points to a different version | Set `JAVA_HOME` to the root directory of the required JDK |
| `java` and `javac` report two different versions | Multiple Java installations exist and `PATH` order is unexpected | Use `where.exe` or `command -v` to inspect the actual paths |

Do not try to fix errors by randomly copying DLL files, libraries, or runtime directories between Java installations. Install or reconfigure a complete, compatible Java distribution instead.

## 12. Key takeaways

- **JVM** is the virtual machine that executes Java bytecode.
- **JRE** is the environment that provides the JVM and runtime components to run applications.
- **JDK** is the development toolkit containing the compiler and tools needed to build Java applications.
- When learning and developing Java, install the JDK.
- When deploying, choose a runtime compatible with the Java version and the application's actual requirements.
- JRE packaging varies by version and vendor; do not use the presence of a `jre` folder as the sole criterion for identifying a Java environment.