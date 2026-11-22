# Running Java Applications with the java Command

## 1. Role of the Java Launcher

The java command is the program that launches a Java application. It creates or uses a JVM, loads the required classes/modules, sets runtime options, and then invokes the application's entry point method.

Three tasks should be distinguished:

- **Compile:** converts .java source files into .class bytecode, typically using javac or a build tool.
- **Package:** bundles classes, resources, and metadata into a JAR/WAR/distribution, typically using jar, Maven, or Gradle.
- **Run:** launches a class, module, source file, or executable JAR using java.

The java command does not automatically build an entire Maven/Gradle project. For a compiled application, the launcher needs to know the main class and the locations of classes/dependencies. In source-file mode, the launcher can compile and run a simple source file in a single command.

A typical workflow:

~~~text
Source code
    |
    v
javac / Maven / Gradle
    |
    v
.class files or executable JAR
    |
    v
java launcher
    |
    v
JVM runs main()
~~~

## 2. Checking Which Java Launcher Is Being Used

Before running the application, check the version and path:

~~~bash
java --version
javac --version
where java
~~~

where java is for Windows Command Prompt/PowerShell. On Linux/macOS:

~~~bash
java --version
javac --version
command -v java
command -v javac
~~~

java --version shows the actual runtime version invoked via PATH. If multiple JDKs are installed on the machine, the terminal, IDE, Maven, and Gradle may be using different versions.

On Windows PowerShell:

~~~powershell
Get-Command java, javac | Select-Object Name, Source
$env:JAVA_HOME
$env:PATH -split ';'
~~~

On Linux/macOS:

~~~bash
command -v java
echo "$JAVA_HOME"
echo "$PATH"
~~~

JAVA_HOME typically points to the root directory of the JDK; PATH should contain the bin directory of that JDK. If java --version returns an unexpected version, fix the PATH order or select the right JDK before diagnosing application errors.

## 3. Four Main Launch Modes

The Java launcher has multiple invocation forms. Four common forms:

| Mode | Syntax | When to use |
|---|---|---|
| Source-file mode | java Hello.java | Quickly running a single source file. |
| Main class | java -cp classes com.example.Main | Compiled classes requiring a classpath. |
| Executable JAR | java -jar app.jar | JAR with a Main-Class manifest attribute. |
| Module | java --module-path mods -m module/name | Applications using the Java Platform Module System. |

JVM options are typically placed before the class name, -jar, -m, or source file. Arguments for the application are placed after the entry point.

## 4. Running a Source File Directly

Since Java 11, the launcher supports source-file mode:

~~~java
// Hello.java
public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Run:

~~~bash
java Hello.java
java Hello.java "Ada Lovelace"
~~~

Output of the second command:

~~~text
Hello, Ada Lovelace!
~~~

You can specify the source level:

~~~bash
java --source 17 Hello.java "Java 17"
~~~

In source-file mode, the Java launcher compiles the source and then runs the program. This approach is suitable for demos, small scripts, and lessons. Projects with multiple classes, dependencies, resources, or modules should use a build tool or compile explicitly into classes/JARs.

The source file name must match the path being executed. If the path contains spaces, enclose it in quotes:

~~~powershell
java "C:\Projects\Java Demo\Hello.java" "Ada Lovelace"
~~~

## 5. Compiling First and Then Running the Main Class

For a typical project, compile the source into class files first.

Example structure:

~~~text
project/
├── src/
│   └── com/example/App.java
└── build/
    └── classes/
~~~

File src/com/example/App.java:

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "local");
        System.out.println("Application started");
        System.out.println("mode=" + mode);
        System.out.println("argument.count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("argument[" + i + "]=" + args[i]);
        }
    }
}
~~~

Compile with the JDK 17 API:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/com/example/App.java
~~~

Run the main class:

~~~bash
java -cp build/classes com.example.App local "two words"
~~~

Exact stdout:

~~~text
Application started
mode=local
argument.count=2
argument[0]=local
argument[1]=two words
~~~

-cp is shorthand for --class-path. The value build/classes is the root directory of the package tree; do not pass the path to the App.class file directly.

The fully qualified class name is com.example.App, consisting of the package and class name, without .java or .class.

## 6. Understanding the Classpath

The classpath tells the JVM where to find classes and resources. It can contain:

- Directories containing compiled classes.
- Dependency JARs.
- Multiple directories and JARs combined.
- Wildcards for JARs in a directory.

Windows example:

~~~powershell
java -cp "build\classes;lib\helper.jar;lib\logging.jar" com.example.App
~~~

You can use a wildcard:

~~~powershell
java -cp "build\classes;lib\*" com.example.App
~~~

Linux/macOS uses : to separate entries:

~~~bash
java -cp "build/classes:lib/helper.jar:lib/logging.jar" com.example.App
java -cp "build/classes:lib/*" com.example.App
~~~

The classpath separator is ; on Windows and : on Linux/macOS. When writing cross-OS scripts, construct the classpath using an appropriate API/tool rather than assuming one separator works everywhere.

The Java launcher's lib/* wildcard includes JARs directly inside the lib directory on the classpath; it does not search recursively into subdirectories. Enclose the classpath in quotes to prevent the shell from unintentionally expanding wildcards or splitting on spaces.

If -cp is not passed, the launcher may use the default classpath or the CLASSPATH environment variable. In scripts and CI, pass the classpath explicitly so results do not depend on machine configuration.

## 7. Running an Executable JAR

An executable JAR declares its entry point in META-INF/MANIFEST.MF using the Main-Class attribute.

Create a JAR from compiled classes:

~~~bash
jar --create \
  --file build/app.jar \
  --main-class com.example.App \
  -C build/classes .
~~~

Run:

~~~bash
java -jar build/app.jar
~~~

Java reads Main-Class from the manifest and invokes that class's main method.

Inspect the JAR contents:

~~~bash
jar --list --file build/app.jar
~~~

Read the manifest:

~~~bash
jar --extract --file build/app.jar META-INF/MANIFEST.MF
~~~

A minimal manifest looks like:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.App
~~~

The class name must be exact, include the full package, and is case-sensitive. If a JAR does not have Main-Class, it can still be a valid library JAR; it just cannot be run standalone with java -jar.

## 8. Passing Arguments to the Application

Arguments for the application follow the main class name, -jar, module entry point, or source file.

Example:

~~~bash
java -cp build/classes com.example.App import "quarter 1.csv" --verbose
~~~

In main(String[] args):

- args[0] is import.
- args[1] is quarter 1.csv.
- args[2] is --verbose.

Quotes tell the shell to pass a string containing spaces as a single argument.

Windows PowerShell:

~~~powershell
java -jar .\build\app.jar "quarter 1.csv" --verbose
~~~

Linux/macOS:

~~~bash
java -jar ./build/app.jar "quarter 1.csv" --verbose
~~~

The Java launcher does not interpret the meaning of application arguments. The program itself must parse args, check the count, validate input, and display usage when the user passes invalid arguments.

## 9. Order of JVM Options and Application Arguments

A common mistake is placing a JVM option after -jar or after the main class name. In that case, the option may be passed as an application argument instead.

Correct:

~~~bash
java -Dapp.mode=ci -Xms32m -Xmx128m -jar build/app.jar first "two words"
~~~

Structure:

~~~text
java [JVM options] -jar app.jar [application arguments]
~~~

Similarly when running a main class:

~~~bash
java -Dapp.mode=ci -Xmx256m -cp build/classes com.example.App first
~~~

-D, -Xms, and -Xmx appear before the entry point. Values after com.example.App are passed into args.

In Windows PowerShell, quote system property options containing dots to prevent PowerShell 5.1 from splitting tokens when invoking a native executable:

~~~powershell
java '-Dapp.mode=ci' '-Xms32m' '-Xmx128m' -jar .\build\app.jar first "two words"
~~~

This quoted form also works in Bash. If a command works in Command Prompt but fails in PowerShell, check how the shell passes arguments before changing Java code.

## 10. Passing System Properties with -D

A system property is a key/value configuration readable inside the JVM:

~~~bash
java -Dapp.mode=production -Dapp.region=ap-southeast-1 \
  -cp build/classes com.example.App
~~~

In code:

~~~java
String mode = System.getProperty("app.mode", "local");
String region = System.getProperty("app.region", "default");
~~~

-Dname=value must appear before the entry point. This is a JVM system property, not an application argument and not an environment variable.

Use system properties for simple configuration such as mode, endpoint, or feature flags. For complex configuration, use a config file or configuration framework and validate values at application startup.

Avoid putting passwords, API tokens, or private keys on the command line whenever possible. The command line can appear in process listings, diagnostic logs, or shell history.

## 11. Configuring JVM Memory

Two common options:

- -Xms: initial heap size.
- -Xmx: maximum heap size.

Example:

~~~bash
java -Xms256m -Xmx1g -jar build/app.jar
~~~

-Xmx1g sets the maximum heap limit to approximately 1 GiB. It does not mean the JVM will immediately consume 1 GiB or all of the machine's memory.

Choose heap size based on workload, container memory limit, and remaining resources for metaspace, thread stacks, direct buffers, native libraries, and the operating system. Setting -Xmx too high can cause the process to be killed by the OS/container; setting it too low can cause OutOfMemoryError.

Some -X and -XX options depend on the JVM version or implementation. Check the documentation for the JDK in use:

~~~bash
java -X
java -XX:+PrintFlagsFinal -version
~~~

Do not copy JVM flags wholesale from another machine without measuring and testing.

## 12. Enabling Java Assertions

Java assertions help check invariants during development or testing.

Example:

~~~java
public class CheckArgs {
    public static void main(String[] args) {
        assert args.length > 0 : "Expected at least one argument";
        System.out.println(args[0]);
    }
}
~~~

Assertions are disabled by default. Run with -ea:

~~~bash
java -ea -cp build/classes CheckArgs hello
~~~

Without -ea, the assert statement may not be executed. Do not use assertions to validate user input or replace mandatory error handling; use regular checks and exceptions for conditions that must always be verified.

## 13. Working Directory and File Paths

The working directory is the directory the process sees when opening relative paths. It is not necessarily the directory containing the JAR or class files.

Check in Java:

~~~java
System.out.println(System.getProperty("user.dir"));
~~~

Example run:

~~~bash
java -jar /opt/apps/app.jar
~~~

If the working directory is /home/user, a relative path such as config/app.properties will be resolved relative to /home/user, not /opt/apps.

How to handle this:

- Set an explicit working directory in scripts/services/CI.
- Use absolute paths when files reside at fixed locations.
- For resources packaged inside a JAR, read them via the classpath resource API instead of assuming a physical file exists.
- Do not concatenate paths with hardcoded slashes; use Path.resolve.
- Do not rely on the current directory of an IDE or developer terminal.

Config and runtime data paths should be specified via options, environment variables, or explicit deployment configuration.

## 14. Environment Variables Affecting Execution

Common variables:

| Variable | Effect |
|---|---|
| JAVA_HOME | Points to the JDK/JRE installation directory that other tools can use. |
| PATH | Determines which java executable the shell finds. |
| CLASSPATH | Default classpath when no explicit classpath is passed. |
| JDK_JAVA_OPTIONS | Appends launcher options to Java launcher invocations. |
| JAVA_TOOL_OPTIONS | Appends JVM options when the JVM is initialized. |

JDK_JAVA_OPTIONS can cause a command to behave differently from what is directly visible on the command line. JAVA_TOOL_OPTIONS can also add agents or VM options. If an application starts with unexpected options, check these variables.

On PowerShell:

~~~powershell
Get-ChildItem Env:JAVA_HOME, Env:CLASSPATH, Env:JDK_JAVA_OPTIONS, Env:JAVA_TOOL_OPTIONS
~~~

On Linux/macOS:

~~~bash
env | grep -E '^(JAVA_HOME|CLASSPATH|JDK_JAVA_OPTIONS|JAVA_TOOL_OPTIONS)='
~~~

Do not set a global classpath if different projects have different dependencies. Do not print the entire environment to logs, as it may expose secrets.

## 15. Running Modular Applications

Applications using the Java Platform Module System can be launched via the module path.

Example structure:

~~~text
src/
├── module-info.java
└── com/example/ModuleApp.java
~~~

module-info.java:

~~~java
module com.example.app {
}
~~~

ModuleApp.java:

~~~java
package com.example;

public final class ModuleApp {
    public static void main(String[] args) {
        System.out.println("Module application started");
        System.out.println("argument.count=" + args.length);
    }
}
~~~

Compile the module:

~~~bash
javac --release 17 \
  -d mods/com.example.app \
  src/module-info.java \
  src/com/example/ModuleApp.java
~~~

Run from the exploded module directory:

~~~bash
java --module-path mods \
  --module com.example.app/com.example.ModuleApp "two words"
~~~

You can package the module into a JAR:

~~~bash
jar --create \
  --file build/module-app.jar \
  -C mods/com.example.app .
~~~

Run the modular JAR:

~~~bash
java --module-path build/module-app.jar \
  --module com.example.app/com.example.ModuleApp "two words"
~~~

--module-path specifies where to find modules; --module or -m selects the module and main class. When debugging module errors, inspect the module name and dependencies with:

~~~bash
jar --describe-module --file build/module-app.jar
java --list-modules
~~~

## 16. Choosing the Right Java Runtime for Bytecode

The runtime must support the class file version and APIs used by the application.

Example compiling for Java 17 compatibility:

~~~bash
javac --release 17 -d build/classes src/com/example/App.java
~~~

It can then run on Java 17 or newer runtimes, provided dependencies and application features are compatible.

Check the runtime:

~~~bash
java --version
~~~

Check the class file version:

~~~bash
javap -verbose -classpath build/classes com.example.App
~~~

If you encounter UnsupportedClassVersionError, the runtime in use is older than the bytecode. The fix is to select a sufficiently new runtime or rebuild with an appropriate --release and ensure dependencies are also compatible.

The build JDK and runtime JDK can differ. Test on the minimum runtime version that the product commits to supporting.

## 17. Reading stdin, stdout, stderr, and Exit Codes

Console applications typically communicate through three streams:

- stdin: input data.
- stdout: standard output.
- stderr: errors and diagnostic messages.

Redirect output:

~~~bash
java -jar app.jar > app.log 2> app-error.log
~~~

Merge stderr into stdout:

~~~bash
java -jar app.jar > app.log 2>&1
~~~

Pass a file as stdin:

~~~bash
java -jar app.jar < input.txt
~~~

The exit code is read immediately after the process finishes. On PowerShell:

~~~powershell
java -jar .\app.jar
$LASTEXITCODE
~~~

On Bash:

~~~bash
java -jar ./app.jar
echo $?
~~~

By convention, 0 indicates success and non-zero values indicate failure. Programs should return consistent exit codes via System.exit(code) when needed to report status to scripts/CI; do not call System.exit in shared libraries.

## 18. Running a JAR with External Dependencies

A JAR may contain a main class while still requiring external libraries. If dependencies are in the lib directory, you can run the main class via the classpath.

Windows:

~~~powershell
java -cp "app.jar;lib/*" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

Note: when using java -jar app.jar, the classpath passed via -cp or -classpath is not used to add dependencies. -jar takes the entry point from the manifest.

There are two options:

1. Run the main class directly with -cp, listing the main JAR and dependencies.
2. Keep java -jar and declare relative dependencies in the manifest Class-Path.

Example manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/helper.jar lib/logging.jar
~~~

Paths in the manifest Class-Path are URLs relative to the JAR containing the manifest and use forward slashes /, even on Windows. The manifest only references dependencies; it does not bundle the libraries themselves.

## 19. Running Applications Built with Maven or Gradle

With Maven, build the artifact first:

~~~bash
mvn -B clean package
~~~

If the JAR has Main-Class and dependencies are properly distributed, run:

~~~bash
java -jar target/app-1.0.0.jar
~~~

With Gradle:

~~~bash
./gradlew clean jar
java -jar build/libs/app-1.0.0.jar
~~~

On Windows using the wrapper:

~~~powershell
.\gradlew.bat clean jar
java -jar .\build\libs\app-1.0.0.jar
~~~

If the project uses the Gradle Application Plugin, you can declare:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.Main'
}
~~~

Then run the run task:

~~~bash
./gradlew run
~~~

The run task uses the runtime classpath managed by Gradle. The java -jar command runs the packaged artifact and requires an appropriate manifest/dependencies. The two approaches can have different classpaths; test both if the application only fails after packaging.

## 20. Running on Windows, Linux, and macOS

| Platform | Running executable JAR | Notes |
|---|---|---|
| Windows CMD | java -jar app.jar | Classpath separator is ;. |
| Windows PowerShell | java -jar .\app.jar | Quote JVM options like '-Dapp.mode=ci' when needed. |
| Linux | java -jar ./app.jar | Classpath separator is :. |
| macOS | java -jar ./app.jar | Verify the right JDK is selected via PATH or java_home. |

A pure Java JAR can run across multiple OSes if the runtime and dependencies are compatible. Applications with JNI/native libraries, OS-specific file paths, or OS service integrations may require different artifacts/runtimes.

Do not assume double-clicking a JAR will work. File associations and desktop launchers depend on the operating system; running from a terminal makes errors and exit codes clearer.

## 21. Diagnosing Errors When Running Applications

| Error | Common cause | Resolution |
|---|---|---|
| java is not recognized | Java is not installed or PATH is wrong. | Check java --version, JAVA_HOME, PATH. |
| Could not find or load main class | Wrong class name or classpath. | Check package, -cp, and .class file location. |
| no main manifest attribute | JAR is missing Main-Class. | Check manifest; verify whether the JAR is executable. |
| Unable to access jarfile | Wrong path or read permissions. | Check working directory, absolute path, and file permissions. |
| NoClassDefFoundError | Missing runtime dependency. | Add dependency to classpath/manifest/module path. |
| UnsupportedClassVersionError | Runtime is older than bytecode. | Select a newer JDK or build with an appropriate --release. |
| FindException: Module not found | Missing module or wrong module path. | Check --module-path, module name, and descriptor. |
| OutOfMemoryError | Insufficient heap or native memory. | Measure memory usage, check for leaks, and adjust JVM options. |
| Application reads wrong config file | Working directory is not as expected. | Print user.dir, pass an absolute path or explicit config path. |
| Unexpected options appear | Environment adds JVM options. | Check JDK_JAVA_OPTIONS and JAVA_TOOL_OPTIONS. |
| PowerShell passes -D incorrectly | Native argument parsing/quoting. | Quote the entire token, e.g., '-Dapp.mode=ci'. |
| Console window closes quickly | Application exits or errors are not shown. | Run from a terminal and inspect stdout/stderr. |

When there is a stack trace, start from the first meaningful exception and read the deepest Caused by cause. Do not change heap, classpath, or JDK by guessing; first determine what the launcher is running and what arguments it receives.

## 22. Security When Launching Applications

- Only run JARs from trusted sources.
- Verify checksums or signatures when provided by the publisher.
- Do not pass secrets on the command line if a safer configuration channel exists.
- Do not log all environment variables or system properties that might contain credentials.
- Restrict the process's user privileges and file access permissions.
- Use a JDK with security updates.
- Do not open remote debugging ports in public environments without access control.
- Inspect native dependencies because they run with the privileges of the Java process.

JVM options affecting security, TLS, module access, or native access should be managed as deployment configuration, with review and testing.

## 23. Lab: Running the Same Application via Source, Class, JAR, and Module

This lab uses a Java 17 program to test the launch modes. The com.example.App program prints a system property and application arguments:

~~~java
package com.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "local");
        System.out.println("Application started");
        System.out.println("mode=" + mode);
        System.out.println("argument.count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("argument[" + i + "]=" + args[i]);
        }
    }
}
~~~

Compile the class:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/App.java
~~~

Run the class:

~~~bash
java -cp build/classes com.example.App local "two words"
~~~

Create and run the JAR:

~~~bash
jar --create --file build/app.jar --main-class com.example.App -C build/classes .
java -Dapp.mode=ci -Xms32m -Xmx128m -jar build/app.jar first "two words"
~~~

With Windows PowerShell, quote the JVM options:

~~~powershell
java '-Dapp.mode=ci' '-Xms32m' '-Xmx128m' -jar .\build\app.jar first "two words"
~~~

Output of the JAR run:

~~~text
Application started
mode=ci
argument.count=2
argument[0]=first
argument[1]=two words
~~~

Command without passing application arguments:

~~~bash
java -jar build/app.jar
~~~

Output:

~~~text
Application started
mode=local
argument.count=0
~~~

## 24. Verified Lab Results

The commands were run on Windows 11 with Azul Zulu JDK 24.0.2 and Amazon Corretto 17.0.15 runtime:

| Run mode | Result |
|---|---|
| Source-file mode java Hello.java | PASS |
| Compile javac --release 17 | PASS |
| Main class with explicit classpath | PASS |
| Executable JAR with java -jar | PASS |
| -Dapp.mode, -Xms, -Xmx | PASS |
| Application arguments with spaces | PASS |
| Java 17 running JAR compiled for target 17 | PASS |
| Modular JAR via --module-path and --module | PASS |

Source-file mode prints exact Hello, source file!.

The JAR ran on Java 17 with output:

~~~text
Application started
mode=local
argument.count=2
argument[0]=first
argument[1]=two words
~~~

The modular JAR printed:

~~~text
Module application started
argument.count=1
~~~

These results confirm the launch modes in the lab on Windows and the stated JDKs. They do not replace separate testing for Linux/macOS or real-world application dependencies/native libraries.

## 25. Checklist Before Putting Run Commands into Scripts or CI

1. Verify the right java executable and runtime version.
2. Determine the launch mode: source file, main class, JAR, or module.
3. Ensure the classpath/module path contains all runtime dependencies.
4. Place JVM options before the entry point.
5. Place application arguments after the entry point.
6. Quote paths and arguments containing spaces.
7. Set the working directory.
8. Pass config paths and environment explicitly.
9. Choose a heap size appropriate for container/machine limits.
10. Capture stdout, stderr, and exit codes.
11. Test on the minimum supported Java runtime.
12. Verify checksums/signatures if running external artifacts.

A production run script should check the exit code according to the shell, log appropriately, and avoid printing secrets.

## 26. References

- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [JAR File Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html)
- [Java Platform Module System](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html)
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)

To run Java applications reliably, specify the right entry point, runtime version, classpath or module path, JVM options, application arguments, and working directory. When commands are placed into scripts or CI, make these inputs explicit so results do not depend on implicit developer machine configuration.