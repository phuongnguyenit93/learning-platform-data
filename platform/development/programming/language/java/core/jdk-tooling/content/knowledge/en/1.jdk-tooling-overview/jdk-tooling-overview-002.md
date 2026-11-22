# Problems JDK Tooling Solves

JDK Tooling solves the problem of turning Java source code into a program that can be compiled, run, inspected, packaged, distributed, and operated. As a project grows, these tools also help developers understand dependency structure, generate documentation, investigate bugs, and prepare an appropriate runtime environment.

A `.java` file is just text describing a program. A computer does not execute Java text directly. The workflow requires a toolset to convert source code into bytecode, a runtime environment to execute that bytecode, and utilities to support tasks across the software lifecycle.

## 1. Distinguishing JDK, JVM, and JDK Tools

- **JVM (Java Virtual Machine)** is the virtual machine that executes Java bytecode. The JVM is responsible for loading classes, verifying bytecode, linking classes, managing memory, and executing the program.
- **JDK (Java Development Kit)** is the toolkit for Java development. The JDK includes the `javac` compiler, the `java` launcher, the `jar` archive tool, the `javadoc` documentation tool, and various analysis and diagnostic utilities.
- **JDK tools** are the command-line programs included with the JDK. Each tool handles a specific part of the development and operations workflow.

The JDK does not replace the JVM: the JVM is the execution component, while the JDK provides the environment and tools to build, inspect, package, and diagnose Java programs. Since Java 9, the JDK has been organized around the module system and can create custom runtime images; therefore, runtime installation and distribution should not be thought of simply as always having a separate JRE package as in older Java versions.

## 2. First Problem: Turning Source Code into Bytecode

**Problem:** Developers write human-readable Java code, but the JVM needs bytecode in `.class` files. Without a compilation step, syntax errors, type mismatches, or invalid references might only be discovered late, or the program might fail to run.

**Primary tool: `javac`**

`javac` reads `.java` source code, checks syntax and data types, and then generates bytecode in `.class` files. The compiler catches many errors before the program is launched, making the development feedback loop faster and clearer.

For example, create the file `src/HelloJdkTooling.java`:

```java
public class HelloJdkTooling {
    public static void main(String[] args) {
        System.out.println("Hello from JDK tooling!");
    }
}
```

Create the output directory and compile:

```bash
mkdir out
javac -d out src/HelloJdkTooling.java
```

After successful compilation, the `HelloJdkTooling` class is written to `out/HelloJdkTooling.class`. Run the program with:

```bash
java -cp out HelloJdkTooling
```

Output:

```text
Hello from JDK tooling!
```

Some commonly used `javac` options:

| Option | Meaning |
|---|---|
| `-d <dir>` | Specifies the directory to place generated `.class` files. |
| `-cp` or `-classpath` | Specifies the classpath so the compiler can find required classes and libraries. |
| `--release <version>` | Compiles against the target Java version, including the supported API set for that version. |
| `-encoding UTF-8` | Specifies the source file encoding when explicit control over text reading is needed. |
| `-parameters` | Preserves parameter names in bytecode metadata so reflection APIs can retrieve them. |

For example, if an application needs to be compatible with Java 17, you can use `javac --release 17` when compiling with a JDK that supports this option. This helps avoid accidentally depending on APIs newer than the target version. It does not automatically check every environment difference or external library; dependencies must also have compatible versions.

**Value:** `javac` produces output that the JVM understands and catches many errors early, before deployment.

## 3. Second Problem: Launching the Right Class and Dependencies

**Problem:** Having bytecode is not enough to run an application. The JVM needs to know which class contains the `main` entry point, where dependent classes are located, and what arguments or configuration the application requires. When the classpath/module path is missing or misconfigured, the program may encounter errors such as `ClassNotFoundException`, `NoClassDefFoundError`, or fail to find the main class.

**Primary tool: `java`**

The `java` command launches the JVM, loads the main class, and invokes the `public static void main(String[] args)` method if the application uses the traditional entry point style.

Common invocation forms:

```bash
# Run a class from the directory containing bytecode
java -cp out HelloJdkTooling

# Pass arguments to the program
java -cp out HelloJdkTooling input.txt --verbose

# Pass a system property to the application
java -Dapp.env=dev -cp out HelloJdkTooling
```

The classpath is a list of locations to search for classes and resources. The separator between entries depends on the operating system: Windows typically uses a semicolon (`;`), while Linux and macOS typically use a colon (`:`). Therefore, application launch scripts should account for the operating system or use a build/run mechanism that manages the classpath rather than assuming a single separator.

For an application packaged as a JAR with a main class declared in its manifest, you can run:

```bash
java -jar app.jar
```

When using `-jar`, the JVM reads the main class from the JAR manifest. You should not expect classpath entries passed separately with `-cp` to add dependencies in this mode; dependencies must be properly declared in the manifest or provided through another packaging/launch approach.

**Value:** the launcher standardizes how applications are started and provides options to configure the JVM, classpath, module path, system properties, and program arguments.

## 4. Third Problem: Bundling Classes into a Storable and Distributable Unit

**Problem:** An application typically consists of many `.class` files, resources, and metadata. Distributing individual files separately easily leads to missing files, incorrect directory structures, or difficulty identifying the startup class.

**Primary tool: `jar`**

`jar` creates and manipulates Java Archives (JAR), a ZIP-based archive format. A JAR can contain bytecode, resources, and a manifest. The manifest can declare the main class to support running with `java -jar`.

Using the example from the previous section, create a JAR:

```bash
jar --create --file app.jar --main-class HelloJdkTooling -C out .
```

Run the JAR:

```bash
java -jar app.jar
```

Output:

```text
Hello from JDK tooling!
```

Some useful commands:

```bash
# List archive contents
jar --list --file app.jar

# Extract the archive into the current directory
jar --extract --file app.jar

# View jar help and options
jar --help
```

JARs help package an application's classes and resources into a single file that is easy to store, transport, and deploy. However, a standard JAR **does not automatically include all external libraries**. If the application depends on other JARs, you must provide them on the classpath/module path, declare how to locate dependencies in the manifest, or use a build/packaging process that creates an appropriate artifact. Do not confuse a standard JAR with a fat JAR/uber JAR produced by build plugins.

**Value:** `jar` reduces the complexity of managing many output files and creates a well-structured Java artifact.

## 5. Fourth Problem: Generating Searchable API Documentation

**Problem:** When multiple people use a library or module, reading source code alone is not enough. Users need to know what classes and methods do, what parameters mean, what return values look like, and what exceptions may occur.

**Primary tool: `javadoc`**

`javadoc` reads Java declarations along with Javadoc-formatted comments to generate HTML documentation. Tags such as `@param`, `@return`, and `@throws` help describe the API contract.

For example, create the file `src/Calculator.java`:

```java
public class Calculator {
    /**
     * Calculates the sum of two integers.
     *
     * @param a the first addend
     * @param b the second addend
     * @return the sum of a and b
     */
    public static int add(int a, int b) {
        return a + b;
    }
}
```

You can generate documentation for the source file with:

```bash
javadoc -d docs src/Calculator.java
```

The `docs` directory will contain the generated HTML pages. Documentation quality depends on the comments and API structure provided by the development team; `javadoc` cannot fully infer business intent from method names alone.

**Value:** `javadoc` turns information embedded in source code into consistent, publishable, and searchable API documentation.

## 6. Fifth Problem: Quick Experimentation Without Creating a Full Project

**Problem:** Sometimes a developer just wants to test an expression, check API usage, or verify a small code snippet. Creating a project, source files, compiling, and running for every small experiment slows down exploration.

**Primary tool: `jshell`**

`jshell` is an interactive REPL (Read-Eval-Print Loop) environment that lets you enter Java expressions and statements and see results immediately.

```text
$ jshell
|  Welcome to JShell -- Version 17
jshell> int total = 10 + 20;
total ==> 30

jshell> System.out.println(total);
30

jshell> /exit
```

`jshell` is well suited for learning the language, trying APIs, checking calculations, and exploring the behavior of a small snippet. It does not replace project structure, automated testing, dependency management, or the build pipeline of a real application.

**Value:** reduces the time between a question and an experimental result, especially when learning and exploring APIs.

## 7. Sixth Problem: Understanding Bytecode and Analyzing Dependencies

**Problem:** When an application behaves unexpectedly, developers may need to know what the actual bytecode contains or which library depends on which package/module. Looking at source code alone is sometimes not enough, especially when working with compiled libraries or legacy applications.

**Primary tools: `javap` and `jdeps`**

- `javap` is a disassembler for Java class files. It can display class declarations, method signatures, modifiers, and bytecode.
- `jdeps` analyzes dependencies at the class/package/module level, helping identify dependencies and prepare for migrating to modules or removing unnecessary dependencies.

Examples:

```bash
# Display signatures and members of a compiled class
javap -classpath out HelloJdkTooling

# Display method bytecode
javap -c -classpath out HelloJdkTooling

# Analyze dependencies of a JAR
jdeps --summary app.jar
```

These tools support investigation and static analysis. `jdeps` output does not replace runtime testing: some dependencies loaded dynamically via reflection, service loaders, or configuration may not be fully inferred from bytecode alone.

**Value:** makes compiled structure and dependency relationships visible, supporting debugging, upgrades, and modularization.

## 8. Seventh Problem: Creating Compact Runtimes and Application Installers

**Problem:** A Java application may only use a small subset of the Java platform's modules. When deploying, shipping a runtime larger than needed can increase distribution size. End users may also not have Java installed or know how to install and configure a runtime.

**Primary tools: `jlink` and `jpackage`**

- `jlink` links the required modules to create a custom runtime image. It works with modules and requires dependent modules to be properly resolved.
- `jpackage` packages an application into a platform-appropriate distribution format, such as an installer for Windows, macOS, or Linux. Packaging formats and requirements depend on the operating system; you typically need to build on the target platform and may need system packaging tools.

A custom runtime image can be created with `jlink` once the application's root modules are known, for example:

```bash
jlink --add-modules java.base --output runtime
```

The command above creates a runtime containing only the `java.base` module, suitable for demonstrating how `jlink` works; a real application must include all modules it uses. You can use `jdeps` and testing to help determine the required set of modules.

**Value:** `jlink` helps control the runtime components being distributed; `jpackage` helps deliver the application to users in a more familiar installer format.

## 9. Eighth Problem: Diagnosing a Running Application

**Problem:** An application may compile successfully yet run into issues in operation: hangs, slow responses, high CPU usage, excessive memory consumption, or many blocked threads. Looking at application logs alone may not be enough to find the root cause.

**Some diagnostic tools in the JDK:**

| Tool | Primary Purpose |
|---|---|
| `jcmd` | Sends diagnostic commands to a running JVM; can list commands supported by the JVM and request diagnostic data generation. |
| `jstack` | Captures a thread dump to inspect thread states and stack traces at the time of capture. |
| `jmap` | Helps retrieve heap information and generate heap dumps in appropriate situations. |
| `jstat` | Displays statistics about JVM activity, garbage collection, and memory regions. |
| `jfr` | Works with Java Flight Recorder recordings to collect and analyze events for performance investigation. |
| `jconsole` | A graphical tool for observing metrics and managing JMX connections. |

For example, list Java processes accessible to `jcmd` and view supported commands:

```bash
jcmd
jcmd <pid> help
```

Capture a thread dump with:

```bash
jcmd <pid> Thread.print
```

Where `<pid>` is the process ID of the Java application to inspect. Process access permissions, OS user, JVM configuration, and runtime environment can affect whether a diagnostic command can be executed.

Thread dumps help identify blocked threads, deadlocks, or resource contention. Heap dumps are useful when investigating suspected memory leaks, but they can be very large and contain sensitive application data. JFR can record events for CPU, allocations, GC, threads, and many other JVM activities; you should choose a recording duration and configuration suited to the investigation goal.

**Value:** diagnostic tools provide JVM-level evidence for investigating performance and stability issues in real environments.

## 10. Ninth Problem: Managing Keys, Certificates, and JAR Signing

**Problem:** An application may need to store keys and certificates, set up a truststore for TLS connections, or sign artifacts so recipients can verify integrity and publisher origin.

**Primary tools: `keytool` and `jarsigner`**

- `keytool` manages keystores and certificates: generating key pairs, creating certificate signing requests, importing certificates, and viewing certificate details.
- `jarsigner` signs JARs and verifies JAR signatures.

Example of listing a keystore's contents:

```bash
keytool -list -keystore my-keystore.p12
```

Example of verifying a JAR's signature:

```bash
jarsigner -verify -verbose -certs app-signed.jar
```

Digital signing helps detect modifications to signed content and supports verifying certificate identity along a trust chain. Signing a JAR **does not encrypt** the archive contents and does not by itself guarantee that an application is secure. You must protect private keys, verify certificate sources, and manage certificate expiration and revocation according to your organization's policies. Avoid placing keystore passwords directly in shell history or shared scripts.

**Value:** supports managing trust information and protecting artifact integrity in the distribution pipeline.

## 11. Combining the Tools into a Development Workflow

JDK tools solve different parts of the same lifecycle:

1. **Write source code:** create `.java` files and resources.
2. **Compile:** use `javac` to check source code and generate bytecode.
3. **Test run:** use `java` to launch the application with the required classpath/module path and configuration.
4. **Quick experimentation:** use `jshell` to explore small expressions or APIs.
5. **Inspect output:** use `javap` to inspect compiled classes and `jdeps` to analyze dependencies.
6. **Generate documentation:** use `javadoc` to produce API documentation.
7. **Package:** use `jar` to create an archive containing classes and resources.
8. **Prepare distribution:** consider `jlink` to create a runtime image and `jpackage` to create an installer.
9. **Protect artifacts:** use `keytool` and `jarsigner` when the workflow requires certificate management and digital signing.
10. **Operate and investigate:** use `jcmd`, `jstack`, `jmap`, `jstat`, `jfr`, or `jconsole` when diagnostic data is needed.

Not every project needs every tool. A Java learning program might only need `javac` and `java`; a public library often also cares about `javadoc`; a desktop application distributed to end users might need `jpackage`; a running service might need JFR or thread dumps to investigate incidents.

## 12. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| Having `java` means you can definitely compile Java. | `java` is the launcher; you need `javac` to compile. Check both commands and the versions being invoked. |
| `javac` succeeding means the application will definitely run properly. | Compilation only verifies certain conditions at compile time. Configuration, dependency, data, and logic errors can still appear at runtime. |
| A JAR always contains all dependencies. | A standard JAR contains only what was packaged into it. External libraries must be provided or packaged through a separate process. |
| `-cp` and `--module-path` are the same. | The classpath serves the traditional class-loading mechanism; the module path serves the Java module system. Choose based on how your application and libraries are organized. |
| `jlink` creates a complete installer. | `jlink` creates a custom runtime image. `jpackage` is the tool that packages an application into a platform-appropriate distribution format. |
| Signing a JAR means encrypting the JAR. | Digital signatures help verify integrity and certificates; the JAR contents can still be read. |
| Diagnostic tools can always access every process. | OS permissions, the process owner, JVM configuration, and the environment can restrict operations. |

When a command is not recognized or invokes the wrong version, check the tool paths and versions:

```bash
java --version
javac --version
jar --version
```

On Windows you can use `where java` and `where javac`; on Linux/macOS you can use `which java` and `which javac` to see the executable found via `PATH`. If `java` and `javac` come from two different installations, build and runtime results may be inconsistent. Setting `JAVA_HOME` and `PATH` clearly helps reduce this class of issues.

## 13. When Should You Use Which Tool?

| Need | Tool to Consider |
|---|---|
| Compile source code and check compile errors | `javac` |
| Run a Java class or application | `java` |
| Package classes and resources into an archive | `jar` |
| Generate HTML API documentation | `javadoc` |
| Quickly test syntax or APIs | `jshell` |
| Inspect class signatures and bytecode | `javap` |
| Analyze dependencies and modules | `jdeps` |
| Create a minimal modular runtime image | `jlink` |
| Create an installer for end users | `jpackage` |
| Manage keystores and certificates | `keytool` |
| Sign or verify JAR signatures | `jarsigner` |
| Investigate threads, heap, and JVM performance | `jcmd`, `jstack`, `jmap`, `jstat`, `jfr`, `jconsole` |

JDK tools provide the foundation for working directly with Java without depending on a specific IDE. IDEs, Maven, and Gradle can invoke or integrate many of these tools to automate larger workflows; they add project, dependency, and build management, while JDK commands remain useful for understanding exactly what is happening underneath.

Once you understand the problem each tool solves, you can choose the right tool for each stage: compiling when you need bytecode, launching when you need to run the application, packaging when you need to distribute, and diagnosing when you need to find the root cause of an issue in the JVM.
