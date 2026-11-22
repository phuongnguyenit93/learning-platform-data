# Core Terminology of JDK Tooling

JDK Tooling is the set of tools bundled with the Java Development Kit (JDK) that supports the entire lifecycle of a Java program: writing source code, compiling, running, packaging, inspecting dependencies, creating runtime environments, and diagnosing applications. Understanding the terminology accurately helps distinguish which tool processes source code, which tool launches the JVM, and which component is responsible at runtime.

## 1. Concept Map

A typical Java workflow can be visualized as follows:

1. **Source code** (.java) is written in the Java language.
2. **The compiler** javac checks the source code and generates **bytecode** in .class files.
3. **The launcher** java locates the class or module to run, initializes the JVM, and transfers control to the program.
4. **The JVM** loads, links, and executes bytecode. Depending on the JVM, code may be interpreted or dynamically compiled into machine code.
5. Other JDK tools support packaging, documentation, API inspection, dependency analysis, digital signing, runtime image creation, and process diagnostics.

Not every application requires all of these steps. For example, jshell can run expressions and code snippets interactively; java can also run a single simple source file directly without the user invoking javac first.

## 2. JDK, JRE, and JVM

### JVM — Java Virtual Machine

**JVM** is the virtual machine that executes Java bytecode. The JVM specifies the execution environment and behaviors such as class loading, linking, memory management, thread handling, bytecode verification, and exception mechanisms.

- The JVM is neither the Java language nor the javac compiler.
- A specific JVM is an implementation of the JVM specification. HotSpot is a widely used JVM implementation in OpenJDK distributions.
- The JVM can interpret bytecode or use a **JIT (Just-In-Time compiler)** to compile frequently executed code paths into machine code while the application is running.
- The JVM is responsible for executing bytecode; it does not automatically provide the full suite of development tools such as javac, javadoc, or jlink.

### JRE — Java Runtime Environment

**JRE** is the concept referring to the environment required to run Java applications: the JVM together with its associated libraries and runtime components.

Starting from Java 9, the standalone JRE distribution model is no longer the common default distribution approach it once was. Many vendors distribute the full JDK; applications can use custom runtime images created with jlink. Therefore, when reading older documentation, JRE should be understood as the runtime environment concept, rather than assuming a machine must have a separate directory or installer named JRE.

### JDK — Java Development Kit

**JDK** is the toolkit for Java development. It includes the runtime for running programs as well as development tools, such as:

- **javac**: compiles Java source code.
- **java**: launches Java applications.
- **jar**: creates and manipulates JAR files.
- **javadoc**: generates API documentation.
- **javap**: inspects class information and bytecode.
- **jshell**: an interactive Java execution environment.
- **jlink**, **jpackage**: create runtime images and application installation packages.
- Diagnostic tools such as **jcmd**, **jstack**, **jmap**, and **jfr**.

A general relationship to keep in mind is: **the JDK serves development; the JRE describes the runtime environment; the JVM executes bytecode**. These are three related concepts, not synonyms.

## 3. JDK Versions, Vendors, and Configuration

### Java version and JDK version

Java versions are typically referred to by platform version, such as Java 17, Java 21, or Java 25. The JDK is the concrete implementation used to develop and run applications on that version.

When checking the environment, two commonly used commands are:

~~~bash
java --version
javac --version
~~~

java --version displays the version of the launcher/JDK found via the command environment. javac --version displays the version of the compiler being invoked. The two commands can return different results if a machine has multiple JDKs and PATH points to different directories.

### Feature release, LTS, and update releases

- **Feature release** is a Java release whose major version increments according to the release cadence, for example 17, 21, 25.
- **LTS (Long-Term Support)** is a long-term support designation applied by a vendor or release policy to certain versions. LTS is not a compilation mechanism or a type of bytecode.
- **Update/patch release** is an update within the same version line, typically containing bug fixes, security updates, and stability improvements.
- **Preview feature** is a preview capability that must be explicitly enabled at both compile time and runtime using --enable-preview according to the rules of the corresponding version. Preview features should not be assumed to carry the same compatibility guarantees as finalized features.

### JDK distribution and vendor

**JDK distribution** is a JDK package built and released by a vendor. Distributions may differ in update schedules, licensing, supported platforms, bundled tools, and support policies. Many distributions are based on the OpenJDK source code.

When choosing a JDK, you should identify at least:

- The project's target Java version.
- The operating system and CPU architecture.
- The vendor and update policy to use.
- The organization's licensing and support requirements.

Distributions that conform to the same Java specification generally aim for high compatibility, but you should not assume that every installation package has identical support policies, additional components, and update schedules.

### JAVA_HOME and PATH

- **JAVA_HOME** typically points to the root directory of the JDK configured for use by a project or build tool. For example, if the JDK is installed at C:\Java\jdk-21, then JAVA_HOME can be set to that value.
- **PATH** is the list of directories the operating system searches when a user invokes a command such as java or javac.
- Adding the JDK's bin directory to PATH allows tools to be invoked from any directory. On Windows, the path typically looks like %JAVA_HOME%\bin; on Linux/macOS, it typically looks like $JAVA_HOME/bin.
- JAVA_HOME and PATH serve different roles. Setting JAVA_HOME does not by itself guarantee that the java command being executed comes from that JDK; the order of directories in PATH still determines which executable is found first.

To check the actual command found by the operating system, you can use where java on Windows or which java on Linux/macOS, and then compare it against JAVA_HOME.

## 4. Source Code, Bytecode, and Output Forms

### Source file

**Source file** is a source code file, usually with the .java extension. The file name typically must match the name of the top-level public class in the file. Source code is compiled by javac or processed by a corresponding Java-supporting tool.

### Bytecode and class file

**Bytecode** is the intermediate instruction set that the JVM understands and executes. After compilation, javac typically produces a **class file** with the .class extension.

A class file contains bytecode along with metadata such as the class name, method information, fields, constants, and the class file format version. A class file is not machine code specific to a single CPU. The JVM can execute it on platforms that have a compatible JVM.

### Class loader

**Class loader** is the component that loads class definitions into the JVM. Classes are typically loaded on demand rather than loading every class of an application at startup. Class loaders participate in loading, linking, and initializing classes.

A class's fully qualified name usually consists of the package name and class name, for example com.example.tools.Main. In environments with multiple class loaders, a class's identity is also tied to the class loader that defined it; two classes with the same name defined by two different class loaders can be treated by the JVM as two distinct types.

### Package

**Package** is the mechanism for grouping classes and creating namespaces in Java. For example, com.example.tools is a package name. The source directory structure usually mirrors the package name, though a package and a directory on disk are two distinct concepts.

### Artifact

**Artifact** is a product generated or distributed after a build step. In a Java project, an artifact may be a directory containing class files, a JAR file, a JMOD file, a runtime image, or an installation package. This term frequently appears in build and CI/CD documentation.

## 5. Classpath, Module Path, and the Java Platform Module System

### Classpath

**Classpath** is the list of locations where the compiler or JVM searches for classes and resources under the class path mechanism. A classpath entry can be a directory, a JAR file, or certain supported archive formats.

Example:

~~~bash
java -cp out com.example.Main
~~~

Here out is the directory containing class files; com.example.Main is the fully qualified class name to launch. Depending on the operating system, the separator between multiple classpath entries differs: `;` on Windows and `:` on Linux/macOS.

You can write -cp or --class-path in commands that support this option. Classpath is commonly used for applications following the traditional classpath model.

### Module and module path

**Module** is the unit of packaging and dependency declaration in the Java Platform Module System (JPMS), introduced in Java 9. A module can declare its name, the packages it exports, and the modules it depends on.

The module-info.java file is the module descriptor in source form. After compilation, module information is stored in the corresponding compiled module descriptor.

**Module path** is where the compiler or JVM searches for modules. It can be specified using --module-path or -p in commands that support it. The module path serves the module system; it is not merely an alternative spelling of classpath.

### Named, automatic, and unnamed modules

- **Named module** has an explicitly declared module name, typically via module-info.java.
- **Automatic module** is a module derived when a JAR without a module descriptor is placed on the module path; the module name may be inferred from metadata or the file name according to platform rules.
- **Unnamed module** is the module to which classes on the classpath belong. Each class loader can have a corresponding unnamed module.

When configuring an application, you need to understand whether a library resides on the classpath or the module path. Simply changing path flags does not automatically resolve all differences in package access, dependencies, or packaging.

## 6. Common JDK Tools

| Tool | Primary Role | Associated Terms |
|---|---|---|
| javac | Compiles .java source code into class files | Compiler, bytecode, classpath, module path |
| java | Launches a class, JAR, module, or source-file execution mode | Launcher, JVM, runtime |
| jshell | Evaluates Java expressions and code snippets interactively | REPL, snippet |
| jar | Creates, lists, and manipulates JAR files | Archive, manifest |
| javadoc | Generates API documentation from comments and source declarations | API documentation |
| javap | Displays class information, signatures, and bytecode | Class file inspection |
| jdeps | Analyzes dependencies at the package, class, or module level | Dependency analysis |
| jmod | Creates and inspects JMOD files | JDK module archive |
| jlink | Assembles required modules into a custom runtime image | Runtime image |
| jpackage | Packages an application into a platform-specific installer | Application packaging |
| keytool | Manages keystores and certificates | Keystore, certificate |
| jarsigner | Signs and verifies signatures on JAR files | Digital signature |
| jcmd | Sends diagnostic commands to a running JVM | Diagnostic command |
| jstack | Captures thread dumps | Thread, stack trace |
| jmap | Retrieves heap information or heap dumps depending on supported options | Heap, memory analysis |
| jstat | Monitors selected JVM statistics | GC, runtime statistics |
| jinfo | Views or inspects JVM configuration as supported by the version | VM flags, system properties |
| jps | Lists Java processes observable by the tool | Process discovery |
| jfr | Works with Java Flight Recorder recordings | Event recording, profiling |
| jhsdb | Serviceability Agent tool for inspecting processes/core dumps in appropriate scenarios | JVM diagnostics |

Not every tool is installed in every runtime image. Development and diagnostic tools are typically included in a full JDK; a minimal runtime image created with jlink may contain only the selected runtime modules. Some diagnostic operations also depend on process permissions, JVM configuration, the operating system, and the capabilities of the JDK in use.

### Tool-Related Terminology

- **Compiler:** converts source code into another output form. In the standard Java workflow, javac converts .java into .class.
- **Launcher:** parses the launch command, identifies the class/JAR/module or source to run, and starts the execution environment. java is the JDK launcher.
- **REPL:** short for Read-Eval-Print Loop, an environment that reads a snippet of code, evaluates it, prints the result, and continues accepting input. jshell is the REPL for Java.
- **Manifest:** metadata located in the META-INF directory of a JAR. The Main-Class attribute can specify the entry-point class for a JAR launched with java -jar.
- **Thread dump:** a snapshot of thread states at a point in time, typically including stack traces and thread statuses. It is useful when investigating deadlocks or hung applications.
- **Heap dump:** data describing the heap at a point in time, typically used to analyze objects and memory usage. It can be a large file and may contain sensitive application data.
- **JFR (Java Flight Recorder):** an event-recording mechanism with relatively low overhead in many scenarios, supporting JVM and application behavior analysis.
- **Runtime image:** an executable runtime structure containing the required modules and components. A runtime image created by jlink can be smaller than a full JDK.
- **JAR (Java ARchive):** a ZIP-based archive format used to bundle class files, resources, and metadata. A JAR is not the Java language itself and is not necessarily a standalone executable.

## 7. Key Command-Line Options

### --release, -source, and -target

When compiling, distinguish between three concepts:

- **--release N** instructs the compiler to compile for target Java platform version N, including the language level, class file version, and the set of Java SE APIs permitted for that release.
- **-source N** selects the accepted source syntax/language level.
- **-target N** selects the generated class file version.

For projects targeting a specific Java version, --release is usually the clearer choice because it coordinates these key constraints. Setting only -source and -target does not by itself guarantee that the code does not call APIs available only in a newer JDK.

For example, compiling source code against Java 17 APIs and bytecode using a newer JDK:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

The command assumes the source file exists at the specified path. The -d out option specifies the output directory for class files; package subdirectories will be created under out as needed.

### -cp / --class-path and --module-path

- **-cp** or **--class-path** configures where to search for classes under the classpath mechanism.
- **--module-path** configures where to search for modules.
- **--add-modules** can request adding extra modules to the application's module graph in appropriate scenarios.

You should not mechanically replace classpath with module path. Library organization and application access rules determine which path is appropriate.

### -D, -X, and -XX

- **-Dname=value** sets a system property for the JVM. The application reads the value using System.getProperty("name").
- **-X...** is typically used for advanced JVM options, such as configuring heap size.
- **-XX:...** is typically used for specialized configuration flags of a specific JVM.

-X and -XX options may vary across JVM implementations or versions. Check the documentation for the JDK being run rather than assuming all flags are supported identically.

### Preview features

When using a preview feature of a given Java version, preview mode must be enabled at both compile time and runtime. Example for JDK 21:

~~~bash
javac --release 21 --enable-preview -d out src/com/example/Main.java
java --enable-preview -cp out com.example.Main
~~~

This example is only appropriate when the source code actually uses a Java 21 preview feature and is running on a JDK that supports it. You should not enable --enable-preview as a default option for every project.

## 8. Minimal Tooling Lifecycle Example

Suppose there is a Main class in the com.example package:

~~~java
// File: src/com/example/Main.java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, JDK tooling!");
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Run the generated class file:

~~~bash
java -cp out com.example.Main
~~~

Output:

~~~text
Hello, JDK tooling!
~~~

You can inspect the class signatures and bytecode with:

~~~bash
javap -classpath out -c com.example.Main
~~~

In this example:

- src is the source directory.
- out is the compiler output directory.
- Main.java is the source file.
- Main.class is the class file containing bytecode.
- javac is the compiler.
- java is the launcher that starts the JVM.
- -cp out adds the out directory to the classpath.
- javap is used to inspect the class file.

These commands assume they are run from the project root directory and the JDK is configured in the command environment. If the system has multiple JDKs, check java --version, javac --version, and the actual paths of both commands.

## 9. Build Tools, IDEs, and JDK Tooling

**JDK Tooling** refers to the tools provided with the JDK. **Build tools** such as Maven or Gradle are separate software used to orchestrate build steps such as downloading dependencies, compiling, running tests, packaging, and managing tasks. Build tools typically invoke the compiler or launcher of a configured JDK.

**IDEs** such as IntelliJ IDEA, Eclipse, or VS Code provide an environment for writing code, navigating, debugging, and integrating builds. An IDE may use a separate JDK configured for the project, while the terminal invokes a different JDK via PATH.

Therefore, when encountering issues like "it runs in the IDE but not in the terminal," compare the JDKs used by the IDE, build tool, and terminal, along with the target version and classpath/module path of each environment.

**Toolchain** is the set of versions and tools selected to execute a build or run process. A Java toolchain typically includes a specific JDK, build tool, compiler configuration, dependency libraries, and target platform. Pinning toolchain versions helps make build results more consistent between developer machines and CI.

## 10. Common Misconceptions

1. **Equating JDK, JRE, and JVM.** The JDK is the development kit; the JRE describes the runtime environment; the JVM is the virtual machine that executes bytecode.
2. **Assuming javac runs the program.** javac compiles; java launches the program on the JVM.
3. **Assuming bytecode is machine code.** Bytecode is an intermediate format for the JVM; the JVM can interpret it or JIT-compile it into machine code.
4. **Assuming a JAR is always a standalone executable application.** A JAR is just an archive. To run with java -jar, a JAR needs an appropriate entry-point configuration, typically the Main-Class attribute in the manifest, and may still require dependency libraries.
5. **Assuming JAVA_HOME determines the java command.** PATH determines which executable is found when a command is invoked; both configurations must be checked separately.
6. **Treating classpath and module path as interchangeable.** Classpath and module path follow different lookup and access rules.
7. **Assuming -source and -target guarantee API compatibility.** These two options do not fully restrict platform APIs the way --release does.
8. **Assuming all JDK distributions have identical support.** You must check the vendor, platform, license, update schedule, and support policy.
9. **Assuming a runtime image contains all the tools of a full JDK.** A minimal runtime image only contains the modules included when it was created.
10. **Assuming the IDE and terminal always use the same JDK.** Each environment can have its own JDK configuration and environment variables.

## 11. Checklist When Reading or Running JDK Commands

- Identify which JDK is being used with java --version and javac --version.
- Check JAVA_HOME and the actual executable path found via PATH.
- Identify which directory source code is compiled into as class files.
- Determine whether the application uses classpath or module path.
- Identify the target Java version; prefer --release when you need to constrain APIs to a specific release.
- Distinguish between options for the compiler (javac), launcher (java), and JVM.
- When diagnosing issues, choose the right tool: jstack for thread dumps, jmap for heap, jcmd for general diagnostic commands, jfr for event recordings.
- Document the JDK version and toolchain in build instructions so others can reproduce the environment.

## 12. Key Takeaways

| Term | Brief Meaning |
|---|---|
| JDK | Java development toolkit |
| JRE | Environment required to run Java applications |
| JVM | Virtual machine that loads and executes bytecode |
| javac | Java compiler |
| java | Java application launcher |
| Bytecode | Intermediate code in a class file, meant for the JVM |
| Classpath | Path for locating classes and resources under the classpath mechanism |
| Module path | Path for locating modules under JPMS |
| JAR | Archive containing class files, resources, and metadata |
| JAVA_HOME | Variable typically pointing to the JDK root directory |
| PATH | List of directories used to locate executables |
| --release | Selects the target Java platform version when compiling |
| Runtime image | Runtime environment built from the required runtime modules |
| Toolchain | Set of tools and versions used in a build workflow |

When reading a JDK command, identify three things: **which tool is running, what the inputs/outputs are, and which configuration determines the Java environment in use**. These three questions help pinpoint most issues during compilation, execution, and diagnostics of Java applications.