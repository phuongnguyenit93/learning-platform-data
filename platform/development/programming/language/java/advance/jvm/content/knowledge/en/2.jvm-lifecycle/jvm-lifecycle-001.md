# From the `java` Command to the JVM Process and Program Entry Point

## 1. The Big Picture

When opening a terminal and typing `java demo.LifecycleApp`, we do not "call the `main` method directly" like calling a normal method from source code. This command starts **an operating system executable**, sets up a **process** containing the **JVM** environment, and then the JVM finds, loads, links, initializes the entry class, and invokes `main`.

Typical lifecycle of a Java application run via the command line:

```text
User / script / IDE
          |
          | type or run command java [JVM options] MainClass [app args]
          v
Shell locates the java executable via PATH (or absolute path)
          |
          v
Operating system creates a process (with PID, address space, etc.)
          |
          v
Java launcher parses options and configures the runtime
          |
          v
Start JVM inside the process
          |
          v
Identify entry class / JAR / module / source file
          |
          v
Load → link → initialize the main class
          |
          v
Invoke public static void main(String[] args)
          |
          v
Application runs: method calls, objects, threads, I/O, etc.
          |
          v
JVM termination condition / exit request
          |
          v
Shutdown hooks (when normal shutdown mechanism is executed)
          |
          v
JVM terminates, process returns exit code to the operating system
```

This is a **conceptual flow**, not a list of every internal native function. The order, component names, and specific JVM creation mechanisms may vary by operating system, JVM vendor, and how the runtime is embedded. In the case of **launching an application with the standard `java` command**, the model above explains most observed behaviors.

This lesson focuses on the boundary **shell command → operating system process → Java launcher → JVM → entry class → `main` method → process termination**.

## 2. Distinguishing Four Easily Confused Entities

| Entity | What is it? | What to remember |
| --- | --- | --- |
| **Shell** | Command interpreter program, such as PowerShell, CMD, Bash | Parses command syntax and asks the operating system to run a program |
| **`java` launcher** | Executable program shipped with the Java distribution | Reads options, determines the launch mode, and starts the JVM |
| **Process** | Execution unit managed by the operating system, with its own PID and resources | Contains native code of the launcher, the JVM, and the running application code |
| **JVM** | Virtual machine that executes bytecode and provides runtime mechanisms | Loads classes, executes Java code, manages many runtime activities |
| **`main`** | Standard entry method of a class-launch Java application | It is the **application logic** entry point, not the start point of the entire OS process |

For example, two terminal windows both running `java -cp out demo.LifecycleApp` will **normally create two independent Java processes**, with different PIDs and memory spaces. `static` fields are not automatically shared across two processes; "same class name" does not mean "same JVM".

One JVM can run **multiple threads** within a single process. Threads share many resources of the process, whereas separate Java processes do not share a heap in the normal way. Do not equate PID with thread ID or assume each thread creates a new JVM.

## 3. What Happens Right After Entering the `java` Command?

### 3.1. The Shell Finds the Right `java` Program

In a terminal, the name `java` is usually resolved according to the shell and operating system's program lookup mechanism, typically involving the `PATH` environment variable. Specifying the absolute path to `java` of a particular JDK avoids much confusion when multiple JDKs are installed.

Diagnostic commands:

```powershell
java -version
javac -version
where.exe java
Get-Command java
```

For Bash or similar shells:

```bash
java -version
javac -version
command -v java
```

`java -version` only prints runtime information and exits; it **does not require** an application class with `main`. `javac` is the source code compiler tool. The two commands can point to different installations if the `PATH` configuration is inconsistent.

Once the launcher is found, the shell asks the operating system to run it. On common systems, the operating system assigns the process a PID identifier, an address space, and the necessary resources. How the shell waits for the command to finish, runs it in the background, or redirects input/output depends on the shell; the JVM does not solely determine all of that behavior.

### 3.2. The Launcher Understands Two Different Kinds of Arguments

Basic class-launch syntax:

```text
java [launcher/JVM options] <main class name> [application arguments...]
```

Example:

```bash
java -Xmx256m -Dapp.mode=demo -cp out demo.LifecycleApp alpha "two words"
```

Here:

- `java`: launches the Java application.
- `-Xmx256m`: option setting the JVM's maximum heap size (an example of a JVM option, not a parameter of `main`).
- `-Dapp.mode=demo`: Java system property, readable via `System.getProperty("app.mode")`.
- `-cp out`: uses the `out` directory as the standard class search path.
- `demo.LifecycleApp`: the **fully qualified** (*fully qualified class name*) name of the entry class, not the `.java` or `.class` file name.
- `alpha` and `"two words"`: passed by the shell as two application arguments; the launcher forwards them into the `String[] args` array of `main`.

**Argument position matters.**

```bash
java -Xmx256m -cp out demo.LifecycleApp alpha
```

In the command above, `-Xmx256m` is processed by the launcher/JVM. Conversely:

```bash
java -cp out demo.LifecycleApp -Xmx256m
```

In the latter command, the string `"-Xmx256m"` appears **after the main class name**, so it is an **application argument**, not a heap setting request. JVM options must be placed in the options section before the program name according to the corresponding syntax.

Quote syntax and splitting strings into tokens happen on the shell side; Java receives the strings already passed to the launcher and does not re-split quoted content the way the shell does.

### 3.3. The Launcher Initializes the JVM and Finds the Program to Run

The launcher prepares the runtime configuration and starts the appropriate JVM. The JVM uses class loaders and runtime mechanisms to locate class definitions, link classes, and execute code. The JVM specification describes the meaning of the steps; one should not infer that every JVM implementation always has an identical internal step-by-step order.

In the case of running a regular class:

```text
java -cp out demo.LifecycleApp
                    |
                    v
Classpath = out
                    |
                    v
Locate out/demo/LifecycleApp.class
                    |
                    v
Load, link, initialize demo.LifecycleApp
                    |
                    v
Invoke demo.LifecycleApp.main(String[])
```

The file path shown above is how to visualize a compiled class directory. On Windows, the directory separator may be displayed as `\`; the class loader can also load classes from a JAR or other class sources depending on configuration.

## 4. The JVM Prepares the Main Class Before Calling `main`

According to Java's model, starting a class-launch application leads to the following key steps.

### Step 1: Loading — Loading the Class

The JVM needs the entry class definition in valid class file/bytecode form. The class loader locates and creates the runtime representation of the class. If the class is not on the appropriate classpath/module path or the fully qualified name is wrong, the application can fail **before entering `main`**.

For example, with `package demo;` and class name `LifecycleApp`, the launcher must look up `demo.LifecycleApp`. Typing `java -cp out LifecycleApp` will not be equivalent.

### Step 2: Linking — Linking the Class

Linking includes activities such as:

1. **Verification:** verifies the validity of class file structures and certain type/bytecode constraints.
2. **Preparation:** prepares storage for `static` fields and their default values according to the specification, before the application's static initialization code is executed.
3. **Resolution:** resolves symbolic references such as class/method/field information into runtime entities when needed; some resolution may be deferred.

Do not conclude that **all dependent classes** will be loaded, resolved, and initialized immediately before `main`. Some work occurs when the program begins using them.

### Step 3: Initialization — Initializing the Main Class

Before `main` is invoked, the class declaring that method must be successfully initialized. This involves initializing required superclasses, running `static` field initializers, and executing `static { ... }` blocks according to the language rules.

Example:

```java
public class InitBeforeMain {
    static {
        System.out.println("static initializer");
    }

    public static void main(String[] args) {
        System.out.println("main method");
    }
}
```

Compile and run:

```bash
javac InitBeforeMain.java
java InitBeforeMain
```

**Exact stdout on a normal run:**

```text
static initializer
main method
```

This proves: **`main` is not the first Java statement that can be executed in a program**. The main class's static initializer can run first. If initialization fails, `main` may never be called.

### Step 4: Invoke main — Calling the Entry Method

With the standard Java 17-compatible class-launch model, the entry method has the signature:

```java
public static void main(String[] args)
```

Or the equivalent varargs syntax for the parameter type:

```java
public static void main(String... args)
```

Meaning:

- `public`: the method can be called from outside the class according to the standard entry-point contract.
- `static`: the launcher does not need to instantiate an object of the application class to call the method.
- `void`: the method does not return a direct result value of type `int` as an exit code.
- `String[] args`: contains the program arguments that the launcher passes after the class/JAR/module/source file name, excluding already-processed JVM options.

The variable name `args` is **not mandatory**; you can write `String[] parameters`. The `main` method can also call other methods or initialize a framework, after which the application actually begins processing requests.

## 5. Complete Java 17+ Experiment: Observing Lifecycle, Arguments, and PID

Create the following directory structure:

```text
jvm-launch-demo/
└── src/
    └── demo/
        └── LifecycleApp.java
```

Contents of **`src/demo/LifecycleApp.java`**:

```java
package demo;

import java.util.Arrays;

public final class LifecycleApp {
    static {
        System.out.println("1. class initialized");
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("2. main entered");
        System.out.println("3. arguments: " + Arrays.toString(args));

        if (Arrays.asList(args).contains("--inspect")) {
            System.out.println("PID: " + ProcessHandle.current().pid());
            Thread.sleep(20_000);
        }

        System.out.println("4. main returning");
    }
}
```

Open a terminal in the **`jvm-launch-demo`** directory and run:

```bash
javac -d out src/demo/LifecycleApp.java
java -cp out demo.LifecycleApp alpha "two words"
```

**Exact stdout of the run above:**

```text
1. class initialized
2. main entered
3. arguments: [alpha, two words]
4. main returning
```

Point-by-point explanation:

1. `javac -d out ...` compiles the source code and generates `out/demo/LifecycleApp.class`. `-d out` specifies the root directory of the package structure in the output.
2. `java -cp out demo.LifecycleApp ...` starts a **new Java process**; `-cp out` indicates where to find classes.
3. Before `main` is called, the JVM initializes the class, so the line `1. class initialized` appears first.
4. The launcher passes two arguments into the `args` array. Because quotes were placed around `"two words"`, it is a single argument containing a space.
5. After the line `4. main returning`, the `main` method finishes normally. If no non-daemon threads remain to keep the JVM alive, the shutdown process begins.

Change the arguments:

```bash
java -cp out demo.LifecycleApp
```

Then line `3` is:

```text
3. arguments: []
```

**Observing the PID and a live process:** run:

```bash
java -cp out demo.LifecycleApp --inspect
```

This time the program will print an extra line of the form `PID: <number changing per run>` and then sleep for about 20 seconds. **There is no fixed PID value** to put into expected stdout, because the operating system allocates a PID on each run.

While the process is still alive, you can observe it with Task Manager/Process Explorer on Windows or the corresponding process management tools on Linux/macOS. When a JDK is available, try the command:

```bash
jps -l
```

The `jps` tool can display running JVM processes; in some environments/containers or with restricted permissions, it cannot list every process. Look for the process before the sleep interval ends. You can use `jcmd <PID> VM.command_line` when `jcmd` is available and has sufficient permissions; replace `<PID>` with the actual printed value. Do not type the literal `<`/`>` characters in the shell command.

**Observing process relationships:** run the application twice, each with `--inspect`, from two terminals. Normally they print two different PIDs. Each time the `LifecycleApp` class is initialized in its own JVM, so the `static` block runs in each process. There is no shared set of `static` variables automatically connecting the two runs.

## 6. Four Ways to Specify the Entry Point for the Java Launcher

The four modes differ in **how they locate the entry point and dependencies**, without changing bytecode execution principles, JVM termination conditions, or the meaning of `main`.

| Mode | Example command | Initial class selection mechanism |
| --- | --- | --- |
| **Class** | `java -cp out demo.LifecycleApp alpha` | Binary class name located on the classpath |
| **JAR** | `java -jar lifecycle-app.jar alpha` | `Main-Class` in the JAR manifest |
| **Named module** | `java --module-path mods -m com.example.app/com.example.app.Main alpha` | Resolves module and main class, requires a real module |
| **Source-file** | `java src/demo/LifecycleApp.java alpha` | Java 11+ launcher compiles the source file and runs the resulting class |

With the `LifecycleApp.java` code compiled in section 5, you can try JAR mode directly:

~~~bash
jar --create --file lifecycle-app.jar --main-class demo.LifecycleApp -C out .
java -jar lifecycle-app.jar alpha "two words"
~~~

The business output lines of `LifecycleApp` are the same as when running in class mode with the same `args`. With `-jar`, do not assume `-cp` provides dependencies in the same way as class mode; check the manifest and packaging. Module mode requires a `module-info.java` descriptor, `--module-path`, and an appropriate module artifact; the example in the table is not a complete module project. Source-file mode still compiles the class in memory; it is **not** the JVM directly reading Java source syntax.

When a classpath has multiple entries, Windows uses the `;` separator and Linux/macOS use `:`. The dedicated lesson on the four launch modes analyzes these mechanisms in depth; in this overview, the key point is that the launcher can select the entry point differently **before** handing control over to the same `main` logic.

## 7. `main` Returning Does Not Necessarily Mean the JVM Process Has Ended

Many people see `main` as the "entry point" and assume that **as soon as `main` returns, the JVM shuts down immediately**. This is false when **non-daemon threads** are still running.

Key shutdown conditions according to the Java API:

- The JVM initiates shutdown when **no live non-daemon threads remain** (subject to runtime conditions), even if `main` has already returned earlier.
- Calling `System.exit(status)` requests the runtime to initiate the shutdown sequence with a status code.
- Certain external events, such as an appropriate interrupt signal, can cause the runtime to initiate shutdown; forced process termination methods do not guarantee the same behavior.

Example **`BackgroundWorker.java`**:

```java
public class BackgroundWorker {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(1_000);
                System.out.println("worker finished");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "background-worker");

        worker.start(); // non-daemon by default when created from the standard main thread
        System.out.println("main is finishing");
    }
}
```

Run:

```bash
javac BackgroundWorker.java
java BackgroundWorker
```

In a typical run, two lines are printed:

```text
main is finishing
worker finished
```

The line from the worker thread usually appears after about one second; the actual timing is determined by the operating system and scheduler. The important point is that the process **waits for the non-daemon thread** to finish. In theory, the timing of thread scheduling can vary; do not use unsynchronized log order as absolute proof for every execution schedule.

If `worker.setDaemon(true)` is called **before** `worker.start()`, that thread no longer keeps the JVM alive by itself. Once all non-daemon threads have terminated, daemon threads may be stopped during JVM termination, even if they have not printed anything yet. Do not use daemon threads for tasks that must be guaranteed to complete and save results.

**What about frameworks?** A Spring Boot program may start a server, thread pools, and components that sustain the application lifecycle. The `main` method typically calls `SpringApplication.run(...)`; whether the process stays alive depends on the threads and mechanisms of the application/framework, not on "`main` looping infinitely".

## 8. When Does the Process Exit? Return, Exit, and Forced Termination

| Termination path | Condition | Cleanup / outcome |
| --- | --- | --- |
| **Natural** | `main` and remaining non-daemon threads finish | JVM initiates shutdown, runs registered hooks |
| **`System.exit(status)`** | Application requests whole-JVM shutdown | Runs hooks in sequence; does not automatically wait for all workers or unwind all `finally` blocks |
| **`Runtime.halt(status)`** | Forces immediate VM termination | Skips or interrupts hooks; risk of data loss |
| **Uncaught Java exception** | The thread carrying the error dies first | Does not automatically mean the entire JVM crashes; other non-daemon threads can keep running |
| **OS kill / native fatal crash** | Process is stopped outside the normal Java path | Hooks, logs, or cleanup are not guaranteed |

By convention, `0` is a successful exit status, and nonzero usually indicates an error, though the exit code alone does not explain the cause of termination. The traditional Java 17 `void` return type of `main` does not itself return an exit status; `System.exit(2)` can be called when a status code is needed, though critical resources should be closed **before** that call.

Register a hook while the JVM is running using `Runtime.getRuntime().addShutdownHook(new Thread(...))`. Hooks run concurrently without a fixed order; a hook that waits indefinitely can cause shutdown to hang. On `SIGKILL`, `Runtime.halt`, or power loss, do not expect hooks to run. Use resource scopes, transactions, and recovery instead of treating a hook as the sole place protecting data.

Thus **returning from main**, **a thread terminating**, **an orderly JVM shutdown**, and **a process being forcibly terminated** are four distinct events. Dedicated lessons in this chapter dive deeper into daemon/executor lifecycles, shutdown hooks, and errors/exit-status.

## 9. Common Errors Before and After `main`

| Symptom | Common timing / cause | What to check |
| --- | --- | --- |
| `java` is not recognized | Shell has not found the launcher | Check JDK, `PATH`, absolute path |
| `Could not find or load main class` | Wrong fully qualified class name or wrong classpath | Check `package`, `-cp`, and `.class` location |
| `Main method not found` | No entry point matching the launcher version's contract | Check the `public static void main(String[] args)` signature |
| `UnsupportedClassVersionError` | Class file compiled for a newer version than the running JVM | Check `java -version` and compile settings such as `--release` |
| `NoClassDefFoundError` | Dependent class unavailable when needed at runtime | Check classpath/module path and runtime dependencies |
| `ExceptionInInitializerError` | Unhandled error during static initialization | Read the root cause from the stack trace and `static` code |
| `No main manifest attribute` | JAR does not specify a main class | Check manifest, JAR creation command, or use class mode |
| Program printed "main done" but is still running | Non-daemon thread, server, executor, hook, etc. still active | Inspect thread dump/logs, manage thread and resource lifecycles |
| JVM exits too early, worker not finished | Task running on a daemon thread or forcibly terminated | Synchronize tasks, shut down executors cleanly, check exit code |

An error occurring **before `main`** usually belongs to class lookup, linking, class initialization, configuration, or entry-point validation. An error **after `main`** may stem from business logic, threads, background tasks, I/O, or shutdown. Classifying the timing accurately helps find the root cause faster.

## 10. Practical Inspection Techniques

**Checking which Java ran:** use `java -version` and the shell's command path lookup (PowerShell `Get-Command java` or Bash `command -v java`). Do not assume `JAVA_HOME` always determines the exact launcher when `PATH` contains multiple JDKs.

**Verifying classes and JARs:** with the compiled example, check the `out/demo/LifecycleApp.class` directory. You can use `jar --list --file lifecycle-app.jar` to inspect entries in the JAR and `jar --describe-module --file ...` when investigating an appropriate modular artifact. Check the manifest if `java -jar` cannot find the main class.

**Observing the current process:** `ProcessHandle.current().pid()` in Java 17+ returns the PID of the current process. Together with `jps`/`jcmd` (when the environment permits), this helps distinguish a Java process that has not exited from another newly started run.

**Diagnosing a JVM that does not exit:** inspect live threads and daemon/non-daemon status using a thread dump or debugger; look for unclosed thread pools/executors, active server listeners, or hanging shutdown hooks. Do not fix it by mechanically calling `System.exit(0)`, as that can bypass the completion of ongoing work.

**Viewing the command the JVM received:** with a supporting JDK and appropriate permissions, `jcmd <PID> VM.command_line` is useful for comparing JVM options against startup arguments; `jcmd <PID> Thread.print` can help inspect threads. These are implementation/JDK-specific diagnostic tools, so support may vary.

**When targeting a Java version:** if you need to run on a Java 17 runtime, you can use a compiler JDK that supports the `--release 17` option:

```bash
javac --release 17 -d out src/demo/LifecycleApp.java
```

This option sets the target language level, class file version, and Java SE API surface within what the compiler supports; you still need to verify third-party libraries, the OS environment, and runtime configuration separately.

## 11. Self-Check

**Question 1.** In the command `java -Xmx256m -cp out demo.LifecycleApp hello`, what are the arguments to `main`?

**Answer:** `args` consists of a single string `"hello"`. The `-Xmx256m` and `-cp out` options belong to the launcher/runtime.

**Question 2.** Why can a program print content from a `static` block before the first statement in `main`?

**Answer:** The JVM initializes the main class, executing the necessary static initializers before calling `main`.

**Question 3.** Two terminals run the same class; do they share a single `static int counter` variable?

**Answer:** Normally no. Two `java` launches create two processes/JVMs with independent memory spaces.

**Question 4.** `main` has returned, yet the process still appears in Task Manager. Is the JVM definitely hung?

**Answer:** No. A non-daemon thread, server, executor, or shutdown hook may still be active. You must inspect threads and the application lifecycle before concluding.

**Question 5.** Why is `java -jar app.jar` different from `java -cp app.jar demo.Main`?

**Answer:** `-jar` takes the entry class from `Main-Class` in the manifest; class mode uses the main class name on the command line and the classpath. Classpath rules when using `-jar` also differ from class mode.

**Question 6.** If `.class` files are already compiled, must the target machine necessarily have `javac`?

**Answer:** No. It needs a compatible runtime/JVM environment to run the classes and required dependencies; `javac` is only needed for the compilation step.

## 12. Summary as a Chain of Responsibility

```text
Shell              : selects and invokes the java executable
Operating System   : creates/manages the process, PID, resources
Java launcher      : interprets options, selects class/JAR/module/source
JVM                : prepares runtime, loads/links/initializes classes, executes bytecode
main(String[])     : application logic entry point; receives application args
Application threads: determine whether work continues running after main
Shutdown           : termination conditions, hooks, process exit code
```

Grasping this boundary helps explain **why a class is not found, why a `static` block runs before `main`, why `main` returns yet the JVM stays alive, why the PID changes on every run, and why `java -jar` differs from `java -cp`**. This is the foundation for deeper study of class loading, memory areas, thread lifecycles, JIT, and JVM diagnostics.

### Official References

- [The `java` Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): class/JAR/module/source launch modes and argument syntax.
- [Java Language Specification `12: Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): loading, linking, initializing classes, and `main` invocation.
- [`java.lang.Runtime` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html): shutdown sequence, hooks, exit, and halt.
- [`java.lang.Thread` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): threads and their relationship to JVM shutdown conditions.