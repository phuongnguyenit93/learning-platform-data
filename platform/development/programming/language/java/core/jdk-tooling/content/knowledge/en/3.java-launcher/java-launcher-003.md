# Running a JAR with the Java Launcher

A JAR (Java Archive) is a ZIP-format archive file that typically contains `.class` bytecode, resources, and application metadata. The Java launcher can run a JAR as a program if the JAR declares a startup class in its manifest. This is a common way to package and deploy Java applications: users only need a single command invoking Java along with the JAR filename and any required arguments.

Three distinct steps should be separated:

- **Creating a JAR**: using the JDK's **jar** tool to package classes and resources.
- **Declaring the entry point**: setting the **Main-Class** attribute in the manifest.
- **Running a JAR**: using **java -jar** to instruct the JVM to launch the main class.

A library JAR can be valid even without a `Main-Class`. Such a JAR serves as a dependency for other applications, but it cannot be executed directly with the `java -jar` command.

## 1. Requirements to Run a JAR

To run a JAR as an executable JAR, you need:

1. A JVM compatible with the application's bytecode version.
2. A valid JAR file with a proper archive structure.
3. A main class with a valid entry point method: `public static void main(String[] args)`.
4. A **Main-Class** attribute in the manifest pointing to the main class.
5. Required dependencies accessible to the JVM at runtime.

Minimal manifest example:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main

~~~

The class name in `Main-Class` is the fully qualified class name, including the package and class name; do not append the `.class` extension and do not write a directory path. If the class is in the `com.example` package, the value must be `com.example.Main`.

The manifest is located at **META-INF/MANIFEST.MF** inside the JAR. The filename and path must match the exact case according to the format convention.

## 2. Creating an Executable JAR with the JDK

The following example uses JDK 17 or later. Initial directory structure:

~~~text
jar-demo/
  src/
    com/
      example/
        Main.java
~~~

Contents of **src/com/example/Main.java**:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");

        if (args.length > 0) {
            System.out.println("First argument: " + args[0]);
        }
    }
}
~~~

The program prints a fixed line and also prints the first argument if provided. This is a standalone Java program that can be compiled and run directly before packaging.

### Step 1: Check the JDK

~~~bash
java --version
javac --version
jar --version
~~~

These three commands check the Java launcher, the compiler, and the packaging tool. If you need to release the application for Java 17, compile with JDK 17 or use the `--release 17` option of `javac` on a newer JDK that supports that target.

### Step 2: Compile the Class

Run from the `jar-demo` root directory:

~~~bash
mkdir -p out
javac --release 17 -d out src/com/example/Main.java
~~~

On PowerShell, you can create the output directory with:

~~~powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out src/com/example/Main.java
~~~

Explanation:

- **--release 17**: compiles against the Java 17 API and bytecode level.
- **-d out**: places `.class` files into the `out` directory and automatically creates the package directory structure.
- Because the source file belongs to the `com.example` package, the class is generated at `out/com/example/Main.class`.

After this step, the main structure is:

~~~text
jar-demo/
  out/
    com/
      example/
        Main.class
  src/
    com/
      example/
        Main.java
~~~

### Step 3: Create the JAR and Declare the Main Class

~~~bash
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Meaning of the options:

- **--create**: creates a new archive.
- **--file app.jar**: specifies the output filename.
- **--main-class com.example.Main**: writes the `Main-Class` attribute to the manifest.
- **-C out .**: changes the working directory of the `jar` command to `out` and adds all contents of that directory to the archive. The dot means include everything inside `out`.

The `jar` command is a packaging tool, not an application runner. The `java` command is what starts the JVM and executes bytecode.

### Step 4: Inspect the JAR Contents

~~~bash
jar --list --file app.jar
~~~

The output will have a structure similar to:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
~~~

The display order may vary. What you need to verify is that the main class file is in the correct package and the manifest is located at `META-INF/MANIFEST.MF`.

You can read the manifest by extracting just that file:

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

After running this command, the file is extracted into the current directory. The manifest contents should include `Main-Class: com.example.Main`. If you only want a quick check, you can use any ZIP-compatible archive viewer without extracting the entire JAR.

### Step 5: Run the JAR

~~~bash
java -jar app.jar
~~~

Stdout:

~~~text
Hello from JAR
~~~

Passing arguments to the program:

~~~bash
java -jar app.jar demo
~~~

Stdout:

~~~text
Hello from JAR
First argument: demo
~~~

Arguments appearing after the JAR name are passed into the `String[] args` array of the `main` method. In this example, `args[0]` receives the value `demo`.

## 3. Syntax and Argument Order of java -jar

General syntax:

~~~bash
java [JVM options] -jar jar-file [application arguments]
~~~

Each part has a distinct role:

- **java**: launches the JVM.
- **JVM options**: options for configuring memory, system properties, logging, modules, and runtime features.
- **-jar**: instructs the launcher to run the application from the specified JAR.
- **jar-file**: path to the JAR file.
- **application arguments**: arguments received by the program via `String[] args`.

Example:

~~~bash
java -Xms256m -Xmx1g -Dapp.env=production -jar app.jar --port 8080
~~~

In this command:

- **-Xms256m**: sets the initial heap size to 256 MB.
- **-Xmx1g**: sets the maximum heap size to 1 GB.
- **-Dapp.env=production**: defines a system property named `app.env` with value `production`.
- **--port 8080**: is an application argument, not a JVM option.

Order matters. JVM options must be placed before **-jar**. Anything after the JAR filename is passed to the application. The following example does not set the maximum heap size to 1 GB:

~~~bash
java -jar app.jar -Xmx1g
~~~

In this command, the string `-Xmx1g` is treated as an application argument. To read a system property in Java, use:

~~~java
String environment = System.getProperty("app.env", "local");
~~~

To read application arguments, use `args` in `main`. System properties and application arguments are two separate configuration mechanisms.

## 4. Using JAR Paths and the Working Directory

You can pass either relative or absolute paths:

~~~bash
java -jar build/app.jar
java -jar /opt/myapp/app.jar
~~~

On Windows:

~~~powershell
java -jar "C:\Apps\My App\app.jar"
~~~

Enclose the path in double quotes when it contains spaces so the shell treats the entire path as a single argument. For relative paths, the location is resolved from the **current working directory of the process**, not necessarily from the directory containing the JAR.

For example, a program opening a config file with the relative path `config/app.properties` will look for the file relative to the current working directory. When running an application from a service manager, container, or IDE, the working directory may differ from when running in a terminal. If the application needs to access resources packaged inside the JAR, read them as classpath resources instead of assuming they are physical files next to the JAR.

You can check the working directory in Java using:

~~~java
System.out.println(System.getProperty("user.dir"));
~~~

## 5. Manifest and Manually Declaring Main-Class

The `--main-class` option of `jar` makes creating an executable JAR quick. When you need finer control over metadata, you can create a custom manifest.

Create a **MANIFEST.MF** file in the project directory:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main

~~~

The trailing blank line at the end of the manifest is required to terminate the declaration section. Then create the JAR:

~~~bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
~~~

Verify again with:

~~~bash
jar --list --file app.jar
~~~

Do not declare `Main-Class` twice with conflicting values. If using a custom manifest, ensure `Main-Class` matches the packaged class.

The manifest supports various standard and extended attributes. Each attribute has the form `name: value`. Lines in a manifest have a byte-length limit; long values must be wrapped according to manifest rules, with continuation lines starting with a single space. Using the `jar` tool to write the manifest is generally safer than concatenating strings manually.

## 6. Running a JAR with External Dependencies

A JAR only contains the classes and resources packaged into that archive. If the application depends on external libraries, the JVM must be able to locate those libraries at runtime.

Suppose the deployment structure is:

~~~text
app/
  app.jar
  lib/
    library-a.jar
    library-b.jar
~~~

There are three common ways to provide dependencies.

### Approach 1: Using the Manifest Class-Path

Add the `Class-Path` attribute to the manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/library-a.jar lib/library-b.jar

~~~

Create the JAR as usual and run:

~~~bash
java -jar app.jar
~~~

The `Class-Path` value is a space-separated list of URLs. Relative paths are resolved against the location of the JAR containing the manifest. Thus, with the structure above, the `lib` directory sits next to `app.jar`. If a path contains special characters or spaces, it must be encoded using valid URL syntax.

This approach works well when both the main JAR and its dependencies can be deployed in a stable directory layout.

### Approach 2: Using the Classpath on the Command Line

You can run the main class with an explicit classpath:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

On Windows, the classpath entry separator is a semicolon:

~~~powershell
java -cp "app.jar;lib/*" com.example.Main
~~~

In this example:

- **-cp** or **-classpath** specifies where the JVM searches for classes and resources.
- **app.jar** contains the main class.
- **lib/*** instructs the launcher to include all JARs directly inside the `lib` directory on the classpath.
- **com.example.Main** is the class whose `main` method is invoked.

Note: when using **-jar**, command-line classpath settings such as `-cp` are ignored. Therefore, do not run **java -cp "lib/*" -jar app.jar** expecting libraries in `lib` to be added to the classpath. Use the manifest `Class-Path` or run the main class via `-cp` as shown above.

### Approach 3: Packaging Dependencies into a Fat JAR

Some build tools or plugins produce a fat JAR / uber JAR containing both the application classes and its dependencies. You can then run it with:

~~~bash
java -jar app-all.jar
~~~

This approach is convenient for single-file deployment, but you need a packaging tool that understands metadata, duplicate resource names, and service loaders. You should not manually extract all dependencies and re-zip them while ignoring metadata files such as `META-INF/services`, JAR signatures, or framework configurations.

A standard JAR produced by Maven or Gradle may contain only the project's own classes. Having a `.jar` extension does not mean the JAR includes dependencies or is guaranteed to run with `-jar`.

## 7. Running a JAR Built by Maven or Gradle

In real-world projects, build tools typically manage dependencies, compilation, testing, and packaging.

### Maven

Common command:

~~~bash
mvn clean package
~~~

The output JAR is usually located in the `target` directory. However, the default JAR may be a plain library without a `Main-Class`. You need to configure the Maven JAR Plugin to add the `Main-Class` attribute if you want to use `java -jar`.

If the application requires external dependencies, configuring `Main-Class` alone is not enough. You need a strategy to distribute dependencies, such as manifest `Class-Path` alongside a `lib` directory, or an appropriate fat JAR packaging plugin for the project.

### Gradle

With Gradle:

~~~bash
./gradlew build
~~~

On Windows:

~~~powershell
.\gradlew.bat build
~~~

The default `jar` task creates an archive from the source set outputs; it does not automatically bundle all runtime dependencies into a single file. For deployable applications, you can use the Application Plugin to generate launch scripts and a distribution directory containing runtime dependencies, or use a fat JAR plugin as needed.

After building, inspect the archive contents and manifest instead of guessing the filename or assuming the output JAR is executable. Use **jar --list --file path/to/app.jar** and check `META-INF/MANIFEST.MF`.

## 8. Running a Modular Application

For modular applications with a `module-info.class` file, you can launch the module using the module path instead of `-jar`:

~~~bash
java --module-path app.jar --module com.example.app/com.example.Main
~~~

Here, `com.example.app` is the module name declared in `module-info.java` and `com.example.Main` is the main class. Both the module name and main class must match the compiled module structure.

This is how you run an application using the Java module system. For traditional classpath-based executable JARs, the standard command remains:

~~~bash
java -jar app.jar
~~~

Do not mix classpath and module path rules: the classpath is used to locate classes via the traditional class loader mechanism, whereas the module path is used to locate and resolve modules.

## 9. Checking Java Version and Compatibility

An application compiled with a newer JDK may not run on an older JVM. For example, classes compiled for Java 21 cannot run on Java 17.

Check the JVM being invoked:

~~~bash
java --version
~~~

Check the executable location:

~~~bash
where java
~~~

On Linux/macOS:

~~~bash
which java
~~~

A machine may have multiple JDKs installed, and `PATH` may point to a different version than `JAVA_HOME`. Therefore, when running from a service or script, verify the exact executable that the process actually uses.

To produce Java 17-compatible bytecode on a supporting JDK:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

The `--release` option restricts both the bytecode level and the platform APIs allowed. Setting source/target versions alone may not prevent accidentally calling APIs that only exist in a JDK newer than the target runtime.

## 10. Useful Runtime Options

Example running with memory and configuration options:

~~~bash
java -Xms512m -Xmx2g -Dapp.env=production -Duser.timezone=UTC -jar app.jar
~~~

Common option groups:

- **-Xms**: initial heap size.
- **-Xmx**: maximum heap size.
- **-Dname=value**: sets a system property.
- **-ea**: enables assertions in the application.
- **-verbose:class**: prints class loading information, useful for basic classpath troubleshooting.

Do not set `-Xmx` to an arbitrary number. Consider the machine or container's RAM limits, native memory, thread stacks, and JVM overhead. Maximum heap is not the total RAM the process will consume.

To see how the launcher parses options or view help:

~~~bash
java --help
java -X
~~~

Advanced options and flag names may change across JDK versions and JVM implementations. Check the documentation for your specific version before applying configurations to production.

## 11. Running in a Server Environment and Logging

You can redirect stdout and stderr to a file via the shell:

~~~bash
java -jar app.jar > app.log 2>&1
~~~

This command writes stdout to `app.log` and redirects stderr to the same file. On Linux/macOS, you can run a background process from the shell, but production environments should use a service manager or container orchestration to handle restarts, stop signals, log rotation, health checks, and resource limits.

Key items to determine when deploying:

- The Java executable and JDK/JRE version used by the environment.
- The working directory, configuration paths, log directory, and file permissions.
- Required environment variables and system properties.
- Heap limits appropriate for the allocated RAM.
- Dependencies packaged or deployed in the expected locations.
- How stdout, stderr, exit codes, and process status are monitored.
- Application shutdown policy and shutdown hook handling.

Do not rely on an open terminal to keep a production application running. Let the service management system handle the process lifecycle.

## 12. Common Errors When Running a JAR

| Message or Symptom | Common Cause | How to Check and Fix |
|---|---|---|
| no main manifest attribute | Manifest is missing `Main-Class` | Inspect `META-INF/MANIFEST.MF` and rebuild the JAR with `--main-class` |
| Unable to access jarfile | Wrong path, filename, read permissions, or file does not exist | Check current directory, path, quotes, and permissions |
| Invalid or corrupt jarfile | Corrupted archive or file is not a valid JAR | Check the output file and test with `jar --list --file` |
| Could not find or load main class | Wrong class name, package, or classpath | Check `Main-Class`, archive structure, and fully qualified class name |
| ClassNotFoundException | Application requested loading a class that the class loader cannot find | Check dependencies and classpath |
| NoClassDefFoundError | Required class is missing at runtime or class initialization failed | Check dependencies, library versions, and earlier causes in the stack trace |
| UnsupportedClassVersionError | Bytecode is newer than the running JVM supports | Use a newer JVM or compile with an appropriate `--release` |
| NoSuchMethodError / NoSuchFieldError | Runtime library version is incompatible with the compile-time version | Check dependency tree and classpath order |
| Exception in thread "main" | Application launched but threw an exception | Read the stack trace and fix the bug in application logic or configuration |

Some concrete examples:

**Missing Main-Class**

~~~text
no main manifest attribute, in app.jar
~~~

Usually caused by the JAR being packaged only as a library. Recreate it with the `--main-class` option or provide a manifest with the correct `Main-Class`.

**Missing dependency**

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: org/example/Library
~~~

Check whether the dependency is included in the fat JAR, listed in the manifest `Class-Path`, or added to the classpath when running the main class.

**JVM too old**

~~~text
java.lang.UnsupportedClassVersionError
~~~

Check `java --version` and the target bytecode version. If upgrading the JVM is not possible, recompile with a compatible `--release` and avoid calling APIs newer than the runtime version.

When diagnosing, distinguish between errors where the launcher cannot find or start the class and exceptions thrown after the `main` method has begun executing.

## 13. Pre-Delivery Checklist for a JAR

- Verify the JAR file was created successfully and its contents can be listed.
- Verify `Main-Class` points to the right class containing `public static void main(String[] args)`.
- Check runtime dependencies and required resources.
- Confirm the minimum JVM version and test with the exact Java executable of the target environment.
- Test running `java -jar` in a clean or production-like environment.
- Verify JVM options, system properties, and application arguments.
- Check relative paths, working directory, and read/write permissions.
- Check stdout, stderr, exit codes, and process shutdown behavior.
- Verify the JAR contents do not accidentally include secrets, private config files, or unreleased data.
- Document the deployment command and artifact version for reproducibility and rollback.

## 14. Key Takeaways

- **jar** is used to create, update, list, and extract archives; **java** is used to run the application.
- An executable JAR requires the **Main-Class** attribute in its manifest.
- The standard syntax is **java [JVM options] -jar app.jar [application arguments]**.
- JVM options go before `-jar`; application arguments go after the JAR filename.
- A JAR with dependencies must provide them via manifest `Class-Path`, an explicit classpath, or a fat JAR.
- When using `-jar`, command-line classpath options such as `-cp` are ignored.
- A JAR only runs on a JVM compatible with the bytecode and APIs used by the application.
- Always inspect the manifest, archive contents, dependencies, and runtime environment when troubleshooting errors.
