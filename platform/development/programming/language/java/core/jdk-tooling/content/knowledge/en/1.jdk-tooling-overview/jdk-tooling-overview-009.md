# Development Tools in the JDK

The JDK (Java Development Kit) provides a suite of tools for writing, compiling, running, packaging, analyzing, and diagnosing Java applications. Understanding these tools helps you handle each stage of the application lifecycle, diagnose errors at the source-code or bytecode level, and collect data when a running program encounters issues.

This lesson uses JDK 21 as its reference baseline. Most commands also apply to other modern JDK releases, though specific options may vary by version and operating system.

## 1. What Does the JDK Include?

The JDK includes the Java runtime environment along with development tools. Some commonly used components are:

- **`javac`**: compiles `.java` source code into `.class` bytecode.
- **`java`**: launches an application or runs a Java source file directly.
- **`jshell`**: a REPL for interactively testing Java expressions and code snippets.
- **`jar`**: creates, lists, and extracts JAR archive files.
- **`javadoc`**: generates API documentation from source code and Javadoc comments.
- **`javap`**: inspects class structure and bytecode.
- **`jdeps`, `jdeprscan`**: analyzes dependencies and APIs marked as deprecated.
- **`jlink`, `jpackage`**: creates custom runtimes and application packages for distribution.
- **`jcmd`, `jstack`, `jmap`, `jstat`, `jconsole`, `jfr`**: observes and diagnoses a running JVM.
- **`keytool`, `jarsigner`**: manages keystores/certificates and signs or verifies JARs.

It is important to distinguish three concepts:

| Component | Role |
|---|---|
| JDK | Development toolkit containing the compiler and bundled utilities |
| JVM | Virtual machine that executes Java bytecode |
| Java runtime | Environment required to run an application; a custom runtime can be created with `jlink` |

If you only have a runtime without a JDK, you can run applications, but you typically will not have `javac`, `javadoc`, `jshell`, and other development tools.

## 2. Checking Which JDK Is Being Used

Open Terminal, Command Prompt, or PowerShell:

~~~bash
java --version
javac --version
jshell --version
~~~

`java --version` shows the launcher/runtime version. `javac --version` shows the compiler version. The two commands can return different versions if multiple JDKs are installed and `PATH` points to different directories.

Find the executable being resolved by the operating system:

~~~powershell
# Windows PowerShell
Get-Command java
Get-Command javac
~~~

~~~bash
# macOS / Linux
command -v java
command -v javac
~~~

Check environment variables:

~~~powershell
# Windows PowerShell
$env:JAVA_HOME
$env:Path -split ';'
~~~

~~~bash
# macOS / Linux
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
~~~

Typically, `JAVA_HOME` points to the JDK root directory, and the JDK's `bin` directory is added to `PATH`. You should not set `JAVA_HOME` to point directly to `bin`.

## 3. Compiling and Running a Program

### 3.1. Compiling Source Code

Create a file named `Hello.java`:

~~~java
/**
 * Small program to demonstrate JDK tools.
 */
public class Hello {
    /**
     * Entry point of the program.
     */
    public static void main(String[] args) {
        System.out.println("Hello from JDK tools");
    }
}
~~~

Create an output directory and compile:

~~~bash
# macOS / Linux
mkdir -p out
javac --release 21 -Xlint:all -d out Hello.java
~~~

~~~powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 21 -Xlint:all -d out Hello.java
~~~

Important options:

- `--release 21`: compiles against the language, bytecode, and public API of Java 21. This option is useful when you need to control the minimum Java version your application supports.
- `-Xlint:all`: enables additional warnings to detect potential issues.
- `-d out`: places generated `.class` files into the `out` directory.
- `-classpath` or `-cp`: specifies where the compiler looks for dependent classes and libraries.
- `--module-path`: specifies the path containing modules when working with the Java Platform Module System.

If a project needs Java 17 compatibility, you can use `--release 17` when compiling with a JDK that supports that release. Avoid using only `-source` and `-target` when you also need to restrict the platform API; `--release` handles all three aspects.

### 3.2. Running Bytecode

After compiling successfully:

~~~bash
java -cp out Hello
~~~

The `java` launcher finds the `Hello` class on the classpath, loads the class, and invokes its `main` method.

Common ways to launch an application:

| Launch Command | Meaning |
|---|---|
| `java -cp out Hello` | Runs the class with fully qualified name `Hello` from the classpath |
| `java -cp "out:lib/*" Hello` | Runs on macOS/Linux with multiple directories or JARs on the classpath |
| `java -cp "out;lib/*" Hello` | Equivalent syntax on Windows, using `;` as the separator |
| `java -jar app.jar` | Runs a JAR that declares `Main-Class` in its manifest |
| `java --module-path mods -m app/com.example.Main` | Runs the main class belonging to a module on the module path |

With `java -jar`, the launcher reads the main class from the JAR's manifest; classpath settings passed via `-cp` on the same command line are ignored in this launch mode. If the application requires external libraries, configure the manifest's `Class-Path` attribute or use an appropriate launch approach.

### 3.3. Running a Source File Directly

Since JDK 11, you can run a simple program without invoking `javac` separately:

~~~bash
java Hello.java
~~~

This is the launcher's source-file mode. It is convenient for small scripts, illustrative examples, and quick experiments. For multi-class applications, projects with dependencies, or builds that need to be repeatable, use the compiler and a clear project structure.

## 4. Quick Code Experiments with JShell

`jshell` is a REPL (Read-Eval-Print Loop) environment. You enter an expression or statement, and JShell evaluates it and displays the result immediately.

Start JShell:

~~~bash
jshell
~~~

Example in a JShell session:

~~~java
int x = 12;
int y = 8;
x + y
String message = "JDK";
message.toLowerCase()
/vars
/methods
/exit
~~~

Commonly used control commands:

- `/help`: view help.
- `/vars`: list declared variables.
- `/methods`: list declared methods.
- `/imports`: view current imports.
- `/save file.jsh`: save the session contents.
- `/open file.jsh`: load commands from a file.
- `/reset`: reset the session state.
- `/exit`: exit JShell.

JShell is well suited for testing APIs, trying short algorithms, or exploring the behavior of an expression. It does not replace class structure, automated tests, or a real application's build process.

## 5. Packaging and Generating Documentation

### 5.1. Creating and Managing JARs

After compiling `Hello.java` into `out`, create a JAR with a main class:

~~~bash
jar --create --file hello.jar --main-class Hello -C out .
~~~

Run the JAR:

~~~bash
java -jar hello.jar
~~~

List its contents:

~~~bash
jar --list --file hello.jar
~~~

Extract into the current directory:

~~~bash
jar --extract --file hello.jar
~~~

JAR is a ZIP-based archive format that can contain bytecode, resources, and metadata in `META-INF`. The manifest file can declare the main class, classpath, and other packaging attributes. A JAR does not automatically bundle all of an application's dependent libraries.

### 5.2. Generating API Documentation

`javadoc` reads Javadoc comments in source code and generates HTML API documentation:

~~~bash
javadoc -d docs Hello.java
~~~

Example comment:

~~~java
/**
 * Represents a temperature converter.
 *
 * @since 1.0
 */
public class TemperatureConverter {

    /**
     * Converts degrees Celsius to degrees Fahrenheit.
     *
     * @param celsius temperature in degrees Celsius
     * @return corresponding temperature in degrees Fahrenheit
     */
    public static double toFahrenheit(double celsius) {
        return celsius * 9.0 / 5.0 + 32.0;
    }
}
~~~

Document the API contract: purpose, parameters, return value, exceptions that may be thrown, and usage conditions. Comments must accurately match the actual behavior of the code; generated documentation does not replace API testing and verification.

## 6. Inspecting Bytecode and Dependencies

### 6.1. Inspecting Class Structure and Bytecode

`javap` is the JDK disassembler tool. It lets you inspect member signatures, modifiers, the constant pool, and bytecode.

~~~bash
javap -classpath out Hello
javap -classpath out -c Hello
javap -classpath out -c -p Hello
~~~

- `-c`: displays the bytecode of methods.
- `-p`: displays private members as well.
- `-verbose`: displays additional details such as the constant pool and metadata.

Use `javap` when you need to understand how the compiler translated source code into bytecode, check class signatures, or investigate class-file-related errors.

### 6.2. Analyzing Dependencies

`jdeps` analyzes dependencies at the package or module level:

~~~bash
jdeps --summary hello.jar
jdeps --recursive hello.jar
jdeps --jdk-internals hello.jar
~~~

`--recursive` expands the analysis across discovered dependencies. `--jdk-internals` helps detect whether an application depends on internal JDK APIs; these APIs may change or be encapsulated in other Java versions.

If the application uses external libraries, provide an appropriate classpath for more complete results, for example `--class-path "lib/*"`.

### 6.3. Finding Deprecated APIs

`jdeprscan` scans classes or JARs for Java APIs marked as deprecated:

~~~bash
jdeprscan --release 21 hello.jar
~~~

The output helps you plan replacements for older APIs before upgrading Java. Deprecated does not necessarily mean an API has been removed; read the documentation for the API and target version to decide how to replace it.

### 6.4. Exploring Modules

Useful commands:

~~~bash
java --list-modules
java --describe-module java.base
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
jmod list "$JAVA_HOME/jmods/java.base.jmod"
~~~

- `java --list-modules`: lists modules present in the runtime currently in use.
- `java --describe-module`: displays module details.
- `jmod describe`: reads the module descriptor in a JMOD file.
- `jmod list`: lists the contents of a JMOD file.

The classpath and module path serve two different class/module resolution mechanisms. Traditional applications can run on the classpath; modular applications typically declare `module-info.java` and run on the module path.

## 7. Creating Custom Runtimes and Installers

### 7.1. Creating a Minimal Runtime

`jlink` assembles the required modules to create a custom runtime image. This is useful when distributing modular applications and wanting to strip out unneeded runtime components.

Example on macOS/Linux:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging --output runtime-mini
~~~

Example on Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME/jmods" --add-modules java.base,java.logging --output runtime-mini
~~~

The resulting runtime contains the selected modules and their required dependencies. The module list must match the application's needs. If the application uses JDBC, XML, logging, or other modules, include those modules accordingly. You can use `jdeps` to help identify dependencies, but you still need to check components loaded dynamically via reflection, service loaders, or configuration.

### 7.2. Packaging an Application

`jpackage` creates an application package or application image for the target platform. For example:

~~~bash
jpackage --type app-image --name Demo --input dist --main-jar demo.jar --main-class com.example.Main
~~~

The `dist` directory must contain the specified JAR and required input files. Package types such as `msi`, `exe`, `dmg`, `pkg`, or `deb` depend on the operating system and require the platform's packaging tools. Build and test the package on the target OS, verifying resource paths, execution permissions, runtime configuration, and how application updates work.

`jlink` creates a runtime; `jpackage` creates an application distribution bundle. The two tools can be combined: create a custom runtime first, then use that runtime when packaging if your distribution workflow calls for it.

## 8. Monitoring and Diagnosing a Running JVM

Diagnostic tools typically require the PID of the Java process. You can list local JVMs with:

~~~bash
jcmd -l
~~~

In container environments, remote servers, or environments with restricted permissions, the process list may not show everything.

### 8.1. jcmd — Unified Diagnostic Interface

`jcmd` sends diagnostic commands to a running JVM:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
~~~

View commands supported by the JVM:

~~~bash
jcmd <pid> help
jcmd <pid> help GC.heap_info
~~~

`jcmd` is often a good starting point because it provides many observation and diagnostic operations. Available commands depend on the JVM version and process state.

### 8.2. Thread Dumps

~~~bash
jstack -l <pid>
~~~

A thread dump records stack traces and thread states at a point in time. Use it to investigate:

- Threads that are `BLOCKED` or waiting on locks.
- Deadlocks.
- Thread pools failing to process work.
- Hung or persistently slow requests.

A thread dump is a point-in-time snapshot. When investigating an incident, take several snapshots spaced apart and compare thread states, stack traces, and recurrence.

### 8.3. Heap and GC Statistics

View an object histogram:

~~~bash
jmap -histo:live <pid>
~~~

Generate a heap dump for deep analysis:

~~~bash
jmap -dump:live,format=b,file=heap.hprof <pid>
~~~

`heap.hprof` can be opened with a compatible heap analyzer such as VisualVM or Eclipse Memory Analyzer. Heap dumps can be very large and contain sensitive in-memory data; control where they are stored, access permissions, and retention time.

Monitor GC statistics periodically:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

The command above samples every 1,000 milliseconds, up to 10 times. The columns report memory region utilization and GC metrics depending on the collector/JVM. Consult the documentation for your exact JDK version before interpreting a column as the root cause of an issue.

### 8.4. Monitoring with jconsole

~~~bash
jconsole
~~~

`jconsole` provides a graphical interface to view heap usage, threads, classes, MBeans, and various JVM metrics. You can select a local Java process or connect via remote JMX if the application is configured for it.

Remote JMX requires authentication and connection security configuration. Do not expose a JVM management port to a public network without proper access control and encryption.

### 8.5. Recording and Reading Java Flight Recorder

Java Flight Recorder (JFR) collects runtime events with typically low overhead when configured appropriately. You can start a recording using `jcmd`:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
~~~

Once the file is created, view a summary:

~~~bash
jfr summary profile.jfr
~~~

Print events as text:

~~~bash
jfr print profile.jfr
~~~

You can open `.jfr` files with JDK Mission Control to filter events and inspect CPU time, allocations, GC, lock contention, and related data. Choose a recording configuration suited to your investigation; recording too many events or recording for too long can produce large files.

### 8.6. jhsdb — Serviceability Agent

`jhsdb` supports deep inspection of a live process or core dump, for example:

~~~bash
jhsdb jstack --pid <pid>
~~~

This is an advanced tool that may require elevated OS privileges and carries a risk of affecting the inspected process. Use it only when standard tools are insufficient and you understand the runtime environment.

## 9. Managing Keys, Certificates, and Signatures

### 9.1. keytool

`keytool` manages keystores, key pairs, and digital certificates. For example, generating an RSA key pair in a PKCS12 keystore:

~~~bash
keytool -genkeypair -alias app -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore app.p12
~~~

The command prompts for passwords and certificate details. List keystore contents:

~~~bash
keytool -list -keystore app.p12 -storetype PKCS12
~~~

A keystore holds key material or certificates; protect passwords, private keys, and backups according to your project's security policy.

### 9.2. jarsigner

`jarsigner` signs a JAR using a key in a keystore:

~~~bash
jarsigner -keystore app.p12 -storetype PKCS12 app.jar app
~~~

Verify a signature:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Signatures verify the integrity and signing origin of JAR contents along a trust chain. Signing a JAR does not encrypt its contents; anyone with the file can still read unencrypted classes and resources. Never commit private keys or keystore passwords into source code, logs, or Git repositories.

## 10. Other Specialized Utilities

- **`serialver`**: displays the `serialVersionUID` of a `Serializable` class. For example: `serialver -classpath out com.example.Model`.
- **`jmod`**: creates, describes, and lists JMOD module files; commonly seen in module/runtime workflows.
- **`jdeprscan`**: helps audit deprecated APIs before upgrading Java versions.
- **`jfr`**: reads and summarizes Java Flight Recorder recordings.
- **`jpackage`**: creates platform-specific application images or installers.

Not every command appears in every distribution or runtime environment. If an executable cannot be found, check whether you are using a JDK or a trimmed runtime, and verify `JAVA_HOME`, `PATH`, and the tool list of that specific JDK build.

## 11. Practical Workflow from Source Code to Diagnostics

For a small Java program, you can follow this sequence:

1. **Verify the toolchain:** run `java --version` and `javac --version`; ensure the compiler and runtime match the intended version.
2. **Compile:** run `javac --release 21 -Xlint:all -d out Hello.java`.
3. **Run:** run `java -cp out Hello` to verify program behavior.
4. **Package:** run `jar --create --file hello.jar --main-class Hello -C out .`, then run `java -jar hello.jar`.
5. **Generate documentation:** run `javadoc -d docs Hello.java` to inspect API comments.
6. **Inspect bytecode and dependencies:** run `javap -c -p -classpath out Hello` and `jdeps --summary hello.jar`.
7. **Observe a live application:** get the PID with `jcmd -l`; when needed, use `jcmd`, `jstack`, `jstat`, or JFR to gather evidence.

Each tool answers a different kind of question. For instance, `javap` shows what the bytecode looks like; `jdeps` shows what classes/modules depend on; `jstack` shows what threads are doing at the moment of capture; JFR helps analyze a timeline of events over time.

## 12. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| `javac` is not recognized | JDK is not installed or `PATH` is missing the `bin` directory | Run `Get-Command javac` or `command -v javac`; check `JAVA_HOME` |
| `java` and `javac` have different versions | Multiple JDKs are installed and the two executables point to different locations | Check the actual resolved paths of both commands |
| `Could not find or load main class` | Incorrect class name, package, or classpath | Verify the fully qualified class name and `.class` location; update `-cp` |
| `UnsupportedClassVersionError` | Runtime is older than the compiled bytecode version | Run with a compatible runtime or recompile with the appropriate `--release` |
| `no main manifest attribute` | JAR is missing `Main-Class` | Create a proper manifest or pass `jar --main-class` when packaging |
| Missing dependent classes at runtime | Library is absent from classpath/module path or manifest | Check classpath, module path, and manifest configuration |
| `jcmd` cannot attach to the process | Different user, container restrictions, JVM attach disabled, or OS policy | Check permissions, PID, runtime environment, and attach configuration |
| Module not found when using `jlink` | Missing module on module path or incomplete module list | Check input JMODs/JARs and dependencies; use `jdeps` to help analyze |

A few working practices to keep in mind:

- Always verify versions with both `java --version` and `javac --version`.
- Use `--release` to control the target API when compiling.
- Distinguish classpath from module path; do not mix the two mechanisms without understanding how the launcher resolves classes.
- Read the help output of the specific executable before using unfamiliar options: `java --help`, `javac --help`, `jcmd <pid> help`, or `jfr help`.
- Heap dumps, thread dumps, and JFR recordings may contain operational details or sensitive data. Store and share them as protected internal data.
- Attach and process inspection commands may be restricted by user permissions, containers, security policies, or the operating system.

## 13. Choosing the Right Tool

| Need | Tool to Start With |
|---|---|
| Compile `.java` | `javac` |
| Run a class or JAR | `java` |
| Quickly test APIs | `jshell` |
| Create or inspect JAR contents | `jar` |
| Generate API documentation | `javadoc` |
| Inspect bytecode | `javap` |
| Find dependencies and JDK internals | `jdeps` |
| Audit deprecated APIs | `jdeprscan` |
| Create a minimal runtime | `jlink` |
| Create a distribution package | `jpackage` |
| Inspect a running JVM | `jcmd` |
| Check threads/deadlocks | `jstack` or `jcmd Thread.print` |
| Analyze heap | `jmap` and a heap dump analyzer |
| Sample GC metrics | `jstat` |
| Monitor JVM with a GUI | `jconsole` |
| Record runtime events | `jcmd` and `jfr` |
| Manage certificates and sign JARs | `keytool`, `jarsigner` |

JDK tools add observability and control across multiple layers: source code, bytecode, modules, distribution packages, and the JVM process. Start with the smallest tool that can answer your current question, consult the help for your active JDK version, and escalate to deeper analysis tools once you have the evidence you need.
