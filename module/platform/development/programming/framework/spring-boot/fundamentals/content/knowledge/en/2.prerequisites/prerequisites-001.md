# JDK, JVM, Bytecode, and the Java Process When Running an Application

When you run a Spring Boot application with `java -jar app.jar`, the operating system starts a **Java process**. Inside that process, the **JVM** loads compiled classes, executes the application code, and manages memory and threads. Before that, the **JDK** provides the tools needed to compile Java source code into **bytecode** and package the application.

Understanding the boundaries between these concepts helps answer practical questions: Why does code run on a developer machine but fail when deployed? Why can an application still use the wrong Java version even when a JDK is installed? Why does increasing `-Xmx` not equal limiting the total RAM of the process? Why do two Spring Boot applications running on the same machine have separate PIDs, ports, and memory?

## 1. Distinguishing JDK, JVM, Bytecode, and the Java Process

| Concept | Role | Example When Working with Spring Boot |
|---|---|---|
| **JDK** (*Java Development Kit*) | Java development toolkit, including the compiler, diagnostic tools, and the environment needed to run Java. | Uses `javac`, `jar`, `jcmd`, and runs Gradle/Maven to build the application. |
| **JVM** (*Java Virtual Machine*) | Virtual machine that executes compiled Java code: loads classes, verifies bytecode, executes, performs JIT compilation, and manages memory. | The JVM executes `main()` and all Spring Boot code. |
| **Bytecode** | Intermediate instruction set stored in `.class` files, relatively independent of the operating system and CPU. | Application classes reside inside the JAR as `.class` files. |
| **Java launcher** (`java`) | Program that starts the JVM and identifies the application entry point. | The command `java -jar app.jar` starts the execution process. |
| **Java process** | A process managed by the operating system, with its own PID, memory address space, threads, and resources. | A running Spring Boot instance typically corresponds to one Java process. |
| **JAR** (*Java Archive*) | Archive file packaging classes, resources, and metadata; not a JVM or a process. | A Spring Boot executable JAR contains application classes, dependencies, and the launcher. |

In modern Java releases, developers typically install the **JDK** for both building and running. The concept of **JRE** (*Java Runtime Environment*) describes the Java execution environment, though you should not assume every modern Java distribution provides a standalone JRE package as before. A minimal runtime can be built with `jlink` for certain types of applications.

One way to remember them by responsibility:

- **The JDK helps create the program**: source code, compilation, packaging, inspection, and diagnostics.
- **Bytecode is the compiled output**: stored in `.class` files, not executed on its own as a process.
- **The JVM executes the program**: turns bytecode into operations on the actual machine.
- **The operating system manages the process**: assigns a PID, schedules threads, manages resources, and allows terminating the application.

## 2. From `.java` Source Code to `.class` Bytecode

Suppose you have a file `HelloJava.java`:

```java
public class HelloJava {
    public static void main(String[] args) {
        String name = "Spring Boot";
        System.out.println("Hello, " + name);
    }
}
```

Run the following commands in the directory containing the file; the example assumes an installed JDK configured on your path:

```bash
javac -d out HelloJava.java
java -cp out HelloJava
javap -classpath out -c HelloJava
```

The steps proceed as follows:

1. `javac` checks syntax, data types, and compile-time checkable references, then generates `out/HelloJava.class`.
2. `java -cp out HelloJava` initializes the JVM with `out` on the *classpath*, locates the `HelloJava` class, and invokes `main(String[] args)`.
3. `javap -c` displays the bytecode instructions in `.class` so you can inspect the compiled output. Depending on the JDK version and expressions, the exact bytecode may vary.

For example, instructions such as `getstatic`, `ldc`, `invokevirtual`, and `return` represent fetching a static field, loading a constant, invoking a method, and returning from a method. They are **not native x86/ARM machine code directly**. The JVM interprets or compiles them into machine code suitable for the runtime environment.

Overall flow:

```text
HelloJava.java
     │  javac (tool in the JDK)
     ▼
HelloJava.class  ── bytecode + class metadata
     │  java launcher starts the JVM
     ▼
Class loading → verification/linking → initialization when needed
     │
     ▼
Interpreter / JIT → executes on CPU
     │
     ▼
Java process: PID, memory, threads, OS resources
```

Key point: **compiling successfully does not guarantee running successfully**. A library may be missing at runtime, a configuration or network port may be wrong, the JVM version may be incompatible, or the application may throw an exception during startup.

## 3. How Does the JVM Load and Execute a Program?

A high-level model of the JVM includes the following components.

### Class Loading, Linking, and Initialization

The **class loader** locates and loads class information from the classpath, module path, or a custom loading mechanism. During **linking**, the JVM verifies bytecode structure, prepares static fields, and resolves references as appropriate. **Initialization** executes the class's static initialization logic when the class is initialized according to Java's rules.

Classes are typically loaded on demand; the JVM does not have to read every `.class` file across all JARs immediately when the process starts. As a result, a missing-class error sometimes only appears when the corresponding code path is executed.

For a Spring Boot executable JAR, the **Spring Boot loader** helps locate application classes and dependencies packaged inside the JAR. This mechanism explains why a Spring Boot JAR can run with `java -jar` even though it stores libraries in a layout different from a standard classpath JAR.

### Interpreter and JIT Compiler

The JVM can execute bytecode via an **interpreter** and use the **JIT** (*Just-In-Time*) compiler to translate eligible code paths into machine code while the application is running. The JVM can optimize based on observed runtime behavior and adjust optimizations when assumptions no longer hold.

Therefore, the saying "Java compiles twice" is a simplification: first `javac` produces bytecode before execution; at runtime, the JVM **may** compile part of the code into machine code. Not every bytecode instruction is guaranteed to be JIT-compiled.

### Garbage Collector (GC)

Regular Java objects are allocated on the **heap** managed by the JVM. The GC finds and reclaims memory from objects that are no longer reachable according to the collector in use. The GC does not automatically close every connection, file handle, or resource outside the JVM; those resources still require proper lifecycle management, such as `try-with-resources`.

## 4. Memory of a Java Process

When an application reports an out-of-memory error, you need to distinguish the **heap** from the total memory used by the process.

| Memory Region / Source | What Is It Used For? | Notes |
|---|---|---|
| **Heap** | Holds most dynamically allocated Java objects. | `-Xms` and `-Xmx` affect heap size. |
| **Thread Java stack** | Holds method call frames, local variables, and per-thread execution data. | Each thread has its own stack; it is not where objects referenced by local variables live. |
| **Metaspace** | Holds various kinds of metadata about classes loaded by the JVM. | Resides outside the Java heap in modern HotSpot. |
| **Code cache** | Holds JIT-compiled machine code and related data. | Has its own limits and management mechanism. |
| **Native/direct memory and runtime resources** | Used by the JVM, native libraries, direct buffers, GC/JIT, and OS operations. | Can cause total process RAM to exceed `-Xmx`. |

Example:

```bash
java -Xms256m -Xmx512m -jar app.jar
```

Here, `-Xms256m` sets the initial heap size and `-Xmx512m` sets the maximum heap size. **Do not infer that the process uses at most 512 MB of RAM**: stacks, metaspace, direct buffers, and other components still consume off-heap memory. How the operating system reports RAM as RSS, working set, or virtual memory also carries different meanings.

Additional terms to distinguish:

- **Stack overflow** (`StackOverflowError`): usually involves a thread's stack being exhausted, such as from overly deep recursion.
- **Java heap space** (`OutOfMemoryError`): the JVM cannot allocate an object on the heap under current limits/conditions.
- **Native memory pressure**: the process or container can run out of RAM even when the Java heap has not reached `-Xmx`.

You cannot pinpoint the exact cause from a single RAM number alone; you must check the error message, JVM/container limits, and corresponding metrics.

## 5. Java Processes, Threads, and Application Lifecycle

A **process** is the unit of resource isolation at the operating system level. Each time an application is launched with a `java ...` command, it normally creates a new OS process containing one JVM. A **thread** is an execution path inside that process; multiple threads share the JVM heap but each has its own stack.

A running Spring Boot web application may have request-handling threads, JVM background threads, scheduler threads, threads for asynchronous tasks, and connection pool threads. **An HTTP request does not mean creating a new Java process.** Threads and how requests are handled depend on the specific web stack and configuration.

Example of running two instances on the same machine:

```bash
java -jar app.jar --server.port=8081
java -jar app.jar --server.port=8082
```

Running both commands concurrently creates **two processes**, with separate PIDs and heaps. They do not directly share objects in the heap. If two instances attempt to bind to the same port and listening address, one instance will usually fail because the port is already in use.

Typical lifecycle of a Spring Boot web application:

1. The OS creates a process and the Java launcher initializes the JVM.
2. The JVM loads the executable JAR's entry point; the Spring Boot launcher transfers control to the application class.
3. `main()` invokes `SpringApplication.run(...)`.
4. Spring initializes the `ApplicationContext`, configures beans, and, for a web application, starts the appropriate web server.
5. Threads continue serving requests and background tasks. `main()` returning **does not necessarily** cause the web process to stop immediately.
6. Upon receiving a stop signal or an appropriate shutdown request, the application/JVM executes configured shutdown logic, releases resources, and the process exits.

The **PID** helps distinguish instances. The **exit code** is the result the process returns to the operating system upon exiting: `0` typically indicates normal termination; a non-zero value typically indicates an error, though the exact meaning is determined by the program or launch mechanism.

## 6. JDK Version at Build Time vs. JVM Version at Runtime

Check the current toolchain:

```bash
java -version
javac -version
```

`java -version` shows the **runtime used by the current `java` command**; `javac -version` shows the compiler. The two commands can point to two different installations if `PATH`, `JAVA_HOME`, or IDE/build tool settings are inconsistent.

In particular, `JAVA_HOME` points to a JDK location used by many tools, whereas the `java` command is resolved by the shell via `PATH`. Do not look only at `JAVA_HOME` and conclude that `java -jar` definitely uses that JDK.

Every class file has a **class file version**. Common examples:

| Java Target | Class File Major Version |
|---|---:|
| Java 17 | 61 |
| Java 21 | 65 |

A class compiled for Java 21 normally does not run on a Java 17 JVM and can throw `UnsupportedClassVersionError`. When building on a newer JDK while supporting an older Java release, you can use:

```bash
javac --release 17 -d out HelloJava.java
```

The `--release 17` option instructs the compiler to generate code compatible with Java 17's API and language features; it does not make dependencies compiled for a newer Java version compatible. With Spring Boot, you must also check the minimum version required by **your Spring Boot version and libraries**. Gradle Java toolchains or Maven compiler configuration can also select a Java version different from your shell or IDE.

## 7. How Specifically Does Java Launch Spring Boot?

A typical Spring Boot entry point:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This code merely declares and calls the application's starting point. The JVM **does not natively understand the `@SpringBootApplication` annotation** to build beans: that is the work of the Spring libraries during `ApplicationContext` initialization.

For a project using the Spring Boot plugin and Gradle wrapper, a common execution path is:

```bash
./gradlew bootJar
java -jar build/libs/<built-jar-filename>.jar
```

On Windows PowerShell, the corresponding wrapper command is usually `./gradlew.bat bootJar`. The actual JAR filename depends on the build configuration. A typical Spring Boot executable JAR has the following structure:

```text
app.jar
├── META-INF/MANIFEST.MF     # Metadata, including entrypoint for launcher
├── BOOT-INF/classes/        # Application .class files and resources
├── BOOT-INF/lib/            # Dependency JARs
└── org/springframework/boot/loader/...  # Launcher classes
```

Depending on the version and packaging type, details may differ. You can inspect it with `jar tf app.jar` and `unzip -p app.jar META-INF/MANIFEST.MF` (if `unzip` is available). The executable JAR's manifest helps the Java launcher locate the entry point; the Spring Boot loader then loads the application along with the nested libraries. Therefore, **`java -jar` on a Spring Boot executable JAR is not the same as running a `.class` file directly with `java -cp`**.

Common ways to run share the fact that they all execute Java on a JVM, but differ in how classpath, arguments, and auxiliary processes are configured:

| Way to Run | Practical Meaning |
|---|---|
| **Run `main()` in an IDE** | The IDE builds the classpath, selects a JDK/runtime, and starts the application for development and debugging. |
| **`./gradlew bootRun`** | Gradle uses the project configuration to run the application; Gradle itself also involves a related Java process/daemon. |
| **`java -jar app.jar`** | Runs the built executable JAR package; suitable when deploying an artifact. |

Do not conclude that a JVM is broken just because an application runs with `bootRun` but fails with the JAR. First compare the artifact, Java runtime, configuration arguments, environment variables, working directory, and the dependencies actually packaged.

## 8. How Do JVM Options Differ from Spring Boot Arguments?

The position of arguments in the command matters:

```bash
java -Xms256m -Xmx512m -Dspring.profiles.active=dev -jar app.jar --server.port=8081
```

| Component | Who Primarily Processes It? | Meaning |
|---|---|---|
| `-Xms256m` | JVM | Initial heap size. |
| `-Xmx512m` | JVM | Maximum heap limit. |
| `-Dspring.profiles.active=dev` | Java launcher/JVM sets the system property; Spring reads the property | Activates the `dev` profile. |
| `-jar app.jar` | Java launcher | Specifies the executable JAR to run. |
| `--server.port=8081` | Spring Boot application | Configures the HTTP port, if a web server is present and the property applies. |

**JVM options** like `-Xmx` and Java system properties like `-D...` must be placed where the Java launcher processes them, typically **before** `-jar`. Application arguments of the form `--...` are usually placed **after** the JAR path to be passed to the application. Spring Boot can also receive configuration from files, environment variables, and other property sources; the final value depends on Spring's property source precedence.

For example, `java -jar app.jar -Xmx512m` does not set a 512 MB heap limit; `-Xmx512m` is passed into the application arguments section instead, where the application may ignore it or handle it differently.

## 9. Observing a Running Process

Tools included in the JDK are useful when you need to identify the JVM version, entry point, or current state of a Java process:

```bash
jps -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
```

Replace `<PID>` with the actual process ID without typing the angle brackets. `jps` and `jcmd` must be available in the machine's JDK; the ability to attach also depends on the OS, user permissions, JVM build, and how the process is configured. The name shown in `jps` may be the launcher or main class, not necessarily the project name.

Operating system commands also help locate the PID:

```bash
# Linux/macOS
ps -ef | grep java

# Windows PowerShell
Get-Process java
```

When diagnosing, correlate evidence by the same **PID**: command line, actual Java version, network port, logs, thread state, and heap info. Avoid combining logs from two instances into an error for a single process.

## 10. Common Errors and Boundaries to Check

| Symptom | Problem Layer to Check First | Verification Approach |
|---|---|---|
| `javac` not found | Missing JDK or `PATH` configuration. | Check `javac -version`, JDK installation location. |
| `java` uses the wrong version | Runtime/launcher in `PATH` or IDE, Gradle, or service configuration differs. | Check `java -version` in the **exact launch environment**. |
| `UnsupportedClassVersionError` | Bytecode was compiled for a newer JVM than the runtime. | Compare the Java target, build JDK, and runtime JVM. |
| `ClassNotFoundException` or `NoClassDefFoundError` | Class loading or dependency/runtime classpath; may also relate to a class initialization failure. | Inspect the full stack trace, which class is missing, and how the JAR is packaged. |
| `no main manifest attribute` | The JAR does not declare a main entry point as required by `java -jar`. | Check the manifest and whether the build task produces an executable JAR. |
| Port already in use / `BindException` | Port conflict or bind address conflict at the OS level. | Identify the PID listening on the port and check `server.port`. |
| `OutOfMemoryError: Java heap space` | Cannot allocate more on the heap; may be caused by workload, heap size, or retaining references too long. | Review heap/GC metrics, logs, and memory usage patterns before adjusting `-Xmx`. |
| Process terminated abruptly by OS/container | Resource limits or runtime environment behavior; may occur without a Java exception. | Check exit status, container/OS logs, memory limits, and signals. |

An `Exception` from Spring during bean initialization can prevent the application from starting even when the JDK, bytecode, and JVM are completely valid. Read the deepest cause in the stack trace instead of attributing every startup failure to a "Java error".

## 11. Hands-on Observation Exercises

**Exercise 1 — Seeing bytecode.** Create `HelloJava.java` from section 2, run `javac -d out HelloJava.java`, and compare the source file contents with the output of `javap -classpath out -c HelloJava`. Identify the bytecode instructions corresponding to the console print statement and the `main` method.

**Exercise 2 — Distinguishing build time and runtime.** Run `java -version` and `javac -version`. If two different JDKs are installed, determine where your shell points each command before compiling further. Try `javac --release 17` on a JDK that supports this option; inspect the class file with `javap -verbose` and locate `major version`.

**Exercise 3 — Observing two Spring Boot instances.** With an existing web executable JAR, start two instances with `--server.port=8081` and `--server.port=8082` in two terminals. Use `jps -l` or OS tools to find **two PIDs**, inspect their command lines, and try using the same port to observe the bind error. After practicing, stop both processes using your environment's normal termination mechanism.

**Exercise 4 — Distinguishing heap and process memory.** Run an application with `-Xmx512m`, use `jcmd <PID> GC.heap_info`, and inspect the process's memory figures in your OS tool. Explain why the measurements do not have to be equal.

## 12. Principles to Keep in Mind When Learning Spring Boot

1. **Spring Boot is still a Java application.** It needs a compatible runtime to execute `.class` files; the Spring framework provides the application initialization layer, dependency injection, and web/server integration.
2. **Build time and runtime are two separate moments.** Check the JDK/toolchain at compile time alongside the actual Java runtime when running.
3. **A JAR is an artifact, the JVM is a runtime, and a process is an OS entity.** Do not use the three terms interchangeably.
4. **One process has many threads and many memory regions.** Increasing the heap does not automatically solve every resource or performance error.
5. **Use the PID to tie evidence to the right instance.** Configuration, logs, ports, heap, and errors all need to be correlated within the same runtime environment.

Once you grasp the path `source → bytecode → JVM → process → Spring ApplicationContext`, you can explain Spring Boot startup and deployment issues based on the component truly responsible, rather than making random configuration changes.
