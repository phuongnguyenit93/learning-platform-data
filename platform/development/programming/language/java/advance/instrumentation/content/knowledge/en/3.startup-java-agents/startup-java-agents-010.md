# Practice: A Marker Agent for Observing JVM Startup Order

## Objectives and Experiment Boundaries

In Java Instrumentation, a **startup agent** is a JAR with a `premain` entry point, loaded by the JVM via the `-javaagent` option. This is the simplest way to observe **when an agent starts and finishes** relative to the application's `main` method. This experiment creates an agent that only prints marker lines; it **does not register a `ClassFileTransformer`, does not modify bytecode, and does not attach to a running JVM**.

After this lesson, you will be able to:

- Correctly write the `premain(String, Instrumentation)` method and package the agent with the `Premain-Class` attribute.
- Compile and run the same application **with** and **without** a startup agent using JDK 17+.
- Distinguish between when the agent class is initialized, `premain` runs, the application class is initialized, `main` is invoked, and a class is initialized upon first use.
- Independently verify the order of **two `-javaagent` declarations**, even when pointing to the same JAR.
- Accurately explain what the markers prove and what they **do not** measure.

> Conclusion to verify experimentally: when using `-javaagent`, the JVM invokes each agent's `premain` in the **order it appears on the command line**, after the JVM has initialized enough to run Java code and **before** invoking the application's `main`. This is **not** a marker for the start of the entire JVM, nor proof that no classes/JVM subsystems were loaded before the agent.

## 1. How Does a Startup Agent Enter the JVM?

A typical invocation:

~~~text
java -javaagent:path/to/agent.jar=phase=boot -cp path/to/app example.app.StartupOrderDemo
     |_____________________________|              |____________________________|
               JVM option                                  Java program
~~~

- `-javaagent:<jarpath>[=<options>]` is a **JVM** option: `jarpath` points to the JAR containing the agent; the string after `=` (if present) is passed verbatim to the `agentArgs` parameter of `premain`.
- The main manifest inside the JAR must contain `Premain-Class: <fully.qualified.class.name>`. The JVM loads the agent class and invokes **`public static void premain(String, Instrumentation)`**, or the one-argument form `premain(String)` if no matching two-argument form exists.
- `premain` must **return normally** for startup to continue. If the JVM cannot load the agent, cannot find a matching entry point, or `premain` throws an unhandled exception, the application may not reach `main`.
- `Instrumentation` provides APIs for working with classes; this experiment only checks whether this object is received and prints markers, without using class transformation features.

Distinguish this from `agentmain`: that is the entry point for an agent started in an already-running JVM (via the attach mechanism when supported). Using `-javaagent` on the command line invokes **`premain`**, not `agentmain`.

### Markers to Observe

~~~text
JVM starts up and prepares the runtime
    │
    ├─ load/initialize StartupMarkerAgent
    │      └─ [AGENT] class initialized
    ├─ invoke premain(agentArgs, instrumentation)
    │      ├─ [AGENT] premain begin
    │      ├─ [AGENT] options=...
    │      ├─ [AGENT] instrumentation available=true
    │      └─ [AGENT] premain end
    │
    ├─ initialize StartupOrderDemo before executing main
    │      └─ [APP] class initialized
    └─ invoke StartupOrderDemo.main(...)
           ├─ [APP] main begin
           ├─ initialize Work on new Work()
           ├─ [WORK] constructor
           └─ [APP] main end
~~~

This diagram illustrates **the markers produced by this example**, not a complete map of all class loading/class initialization activity inside the JVM. In particular, a `ClassLoader` may **load** a class before it is **initialized** (running `<clinit>`). Printing from a static initializer alone does not determine when a class was loaded.

## 2. Setting Up a Small Framework-Free Project

Requirements: **JDK 17 or newer** with `java`, `javac`, and `jar` available in `PATH`. Verify:

~~~bash
java -version
javac -version
jar --version
~~~

Create the following directory structure (filenames, packages, and paths must match):

~~~text
startup-agent-lab/
├── manifest.mf
├── src/
│   ├── agent/
│   │   └── example/
│   │       └── agent/
│   │           └── StartupMarkerAgent.java
│   └── app/
│       └── example/
│           └── app/
│               └── StartupOrderDemo.java
└── build/                        # created during compilation
    ├── agent/
    ├── app/
    └── startup-marker-agent.jar
~~~

Run all remaining commands from the `startup-agent-lab/` root directory.

### File 1 — The Marker-Only Agent

`src/agent/example/agent/StartupMarkerAgent.java`:

~~~java
package example.agent;

import java.lang.instrument.Instrumentation;

public final class StartupMarkerAgent {
    static {
        System.out.println("[AGENT] class initialized");
    }

    private StartupMarkerAgent() {
        // No instance needed: the JVM invokes premain statically.
    }

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("[AGENT] premain begin");
        System.out.println("[AGENT] options=" + agentArgs);
        System.out.println("[AGENT] instrumentation available=" + (instrumentation != null));
        System.out.println("[AGENT] premain end");
    }
}
~~~

**Explanation of each marker:**

1. `[AGENT] class initialized` is printed when `StartupMarkerAgent` is **initialized** before the static `premain` method is invoked. The static initializer is part of the class lifecycle; it is not `premain` itself.
2. `premain begin` shows that the JVM has transferred control to the agent's startup callback.
3. `options=...` confirms that the JVM passes the argument after `=` in `-javaagent` as a single **String**. The JVM does not automatically parse it into a key/value map.
4. `instrumentation available=true` confirms that the two-argument signature received an `Instrumentation` instance on a valid startup; it does **not** mean any classes have been instrumented.
5. `premain end` shows that the agent has finished printing markers; the method then returns and the JVM proceeds to `main`.

The agent does not call `instrumentation.addTransformer(...)`, `retransformClasses(...)`, `redefineClasses(...)`, or spawn threads. As a result, the printed line order has minimal noise.

### File 2 — The Reference Application

`src/app/example/app/StartupOrderDemo.java`:

~~~java
package example.app;

public final class StartupOrderDemo {
    static {
        System.out.println("[APP] class initialized");
    }

    public static void main(String[] args) {
        System.out.println("[APP] main begin");
        new Work();
        System.out.println("[APP] main end");
    }

    private static final class Work {
        static {
            System.out.println("[WORK] class initialized");
        }

        Work() {
            System.out.println("[WORK] constructor");
        }
    }
}
~~~

The markers sit in **three distinct phases**: the static initializer of the class containing `main`; the body of `main` itself; and the static initializer and constructor of `Work`. `new Work()` is the first place the application actively uses `Work`, which triggers initialization of the `Work` class before running its constructor. Each `java` command invocation here is a **new JVM process**, so the static initializers run again on subsequent runs.

### File 3 — The Startup Agent Manifest

`manifest.mf` (create a UTF-8 text file ending with a blank line):

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.StartupMarkerAgent

~~~

`Premain-Class` must be the **binary name** of the agent class, including its package, not the `.java` or `.class` filename. This is what the JVM reads from the agent JAR to locate the method to invoke. Do not mistake `Main-Class` for `Premain-Class`. This experiment does not require `Can-Redefine-Classes`, `Can-Retransform-Classes`, or other instrumentation capabilities.

## 3. Compiling and Packaging the JAR

On macOS/Linux (Bash or POSIX shell), from the project root directory:

~~~bash
mkdir -p build/agent build/app

javac --release 17 -d build/agent \
  src/agent/example/agent/StartupMarkerAgent.java

javac --release 17 -d build/app \
  src/app/example/app/StartupOrderDemo.java

jar --create --file build/startup-marker-agent.jar \
  --manifest manifest.mf -C build/agent .
~~~

On Windows PowerShell, run the equivalent commands:

~~~powershell
New-Item -ItemType Directory -Force -Path build/agent, build/app | Out-Null

javac --release 17 -d build/agent src/agent/example/agent/StartupMarkerAgent.java
javac --release 17 -d build/app src/app/example/app/StartupOrderDemo.java

jar --create --file build/startup-marker-agent.jar --manifest manifest.mf -C build/agent .
~~~

`--release 17` targets Java 17 source/API/class-file compatibility; running these commands on JDK 21 also works. The `-d` option places compiled bytecode into the destination directory by package. With `jar ... -C build/agent .`, the JAR must contain `example/agent/StartupMarkerAgent.class` and `META-INF/MANIFEST.MF`. Verify the contents:

~~~bash
jar --list --file build/startup-marker-agent.jar
~~~

If `jar` reports missing files or classes, check your **current working directory**, the `src/...` paths, and that the compiler produced `build/agent/example/agent/StartupMarkerAgent.class`. You do not need to include the app class in the agent JAR: the app is supplied separately via `-cp build/app`.

## 4. Running Without an Agent: Establishing a Baseline

Run:

~~~bash
java -cp build/app example.app.StartupOrderDemo
~~~

**Exact expected stdout**:

~~~text
[APP] class initialized
[APP] main begin
[WORK] class initialized
[WORK] constructor
[APP] main end
~~~

Comparison: the application runs normally; there are no `[AGENT]` lines because no agent JAR was **passed via `-javaagent`**. The JVM initializes `StartupOrderDemo` before executing `main`, and then `Work` is initialized on its first active use in this code.

## 5. Running With a Single Startup Agent

On macOS/Linux:

~~~bash
java -javaagent:build/startup-marker-agent.jar=phase=boot \
  -cp build/app example.app.StartupOrderDemo
~~~

On Windows PowerShell:

~~~powershell
java "-javaagent:build/startup-marker-agent.jar=phase=boot" -cp build/app example.app.StartupOrderDemo
~~~

**Exact expected stdout**:

~~~text
[AGENT] class initialized
[AGENT] premain begin
[AGENT] options=phase=boot
[AGENT] instrumentation available=true
[AGENT] premain end
[APP] class initialized
[APP] main begin
[WORK] class initialized
[WORK] constructor
[APP] main end
~~~

From this output, we can draw three observations **within the scope of this test program**:

1. The JVM initializes the agent class and then invokes its `premain` callback. The string `phase=boot` is input data to the agent; it does **not** cause Java to perform any action named "boot".
2. The agent finishes `premain` **before** `[APP] main begin` is printed. This is guaranteed by the `java.lang.instrument` API: a startup agent's `premain` runs before the application's `main`.
3. `[APP] class initialized` appears before `main begin`, yet **after** the agent markers in this **specific example** because the agent does not actively load or initialize the application class. In larger systems, agent code may load other classes during `premain`; do not infer a general rule that "all application `<clinit>` blocks run after premain" from a single log.

Using a single process, a single thread, and sequential `System.out.println` calls to the same `System.out` keeps the test easy to read. Logs from the JVM, native runtime, other libraries, or `System.err` may interleave and are not markers emitted by this program.

## 6. Testing Two Startup Agents to Verify Command-Line Order

The specification allows repeating the `-javaagent` option and **allows using the same agent JAR multiple times**. You do not need to write a second agent: run the same JAR you just built with two different option strings.

macOS/Linux:

~~~bash
java -javaagent:build/startup-marker-agent.jar=first \
  -javaagent:build/startup-marker-agent.jar=second \
  -cp build/app example.app.StartupOrderDemo
~~~

Windows PowerShell:

~~~powershell
java "-javaagent:build/startup-marker-agent.jar=first" "-javaagent:build/startup-marker-agent.jar=second" -cp build/app example.app.StartupOrderDemo
~~~

**Expected stdout**:

~~~text
[AGENT] class initialized
[AGENT] premain begin
[AGENT] options=first
[AGENT] instrumentation available=true
[AGENT] premain end
[AGENT] premain begin
[AGENT] options=second
[AGENT] instrumentation available=true
[AGENT] premain end
[APP] class initialized
[APP] main begin
[WORK] class initialized
[WORK] constructor
[APP] main end
~~~

The two `premain` invocations occur in **the order `first` then `second`**. `[AGENT] class initialized` appears only **once** in this experiment: the same agent class is loaded by the system class loader in the same process, and Java initializes a given class identity only once. There are no two `StartupMarkerAgent` instances; `premain` is a static method and is invoked twice by the JVM for the two agent declarations.

To verify this is not due to alphabetical sorting, **reverse the order** of the two options:

~~~bash
java -javaagent:build/startup-marker-agent.jar=second \
  -javaagent:build/startup-marker-agent.jar=first \
  -cp build/app example.app.StartupOrderDemo
~~~

In PowerShell, you can use the same single-line command and swap `first`/`second` inside the two double-quoted arguments. The agent output will then start with `options=second` followed by `options=first`; all application markers still appear after the `premain` calls.

**What is guaranteed:** the `premain` invocation order follows the startup agent declarations, and each `premain` must return before the launcher proceeds to the application. **What is not guaranteed:** the order of all class loading, background threads, JIT compilation, or logs emitted by other tools. If a `premain` spawns an asynchronous thread or another agent transforms classes, markers produced by those threads/callbacks may interleave.

## 7. Reading the Results Accurately at the JVM Level

### `-javaagent` Does Not Imply Bytecode Transformation

Receiving `Instrumentation` only means the JVM provides the API so the agent *can* perform instrumentation. This example **does not** register a transformer, rename classes, modify methods, or inject probes into application code. The `[WORK] constructor` line comes from **existing application code**, not from code inserted by the agent.

If your goal is simply to observe startup timing, logging directly inside `premain` is sufficient. Do not complicate the experiment with `ClassFileTransformer` or the attach API before understanding this baseline.

### Loading, Initialization, and Execution Are Distinct Phases

- **Loading:** the JVM/class loader locates and defines the class. A static initializer cannot prove the exact moment a class began loading.
- **Initialization:** executes class initialization (corresponding to `<clinit>` when static initialization work is present). `[AGENT] class initialized`, `[APP] class initialized`, and `[WORK] class initialized` are markers in this phase.
- **Execution:** executes the `premain` callback, `main`, or the `Work()` constructor. A constructor is not a class initializer.

In applications with multiple modules, custom class loaders, async loggers, or multiple threads, real logs will not necessarily show every marker like this demo program. Avoid concluding that an agent runs *before the JVM exists*, or that the JVM has not loaded any classes before `premain`.

### Markers vs. Absolute Time

The labels above confirm **relative ordering**, not startup time measured from when the OS created the process. If you need to measure latency, capture timestamps within the same JVM and compute the difference; `System.nanoTime()` is only useful for computing **duration** between readings, not wall-clock timestamps or JVM start time. The current experiment intentionally keeps logs short, easy to compare, and predictable in output.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `Failed to find Premain-Class manifest attribute` | Agent JAR is missing or has an incorrect `Premain-Class` | Check `manifest.mf`, rebuild the JAR with `--manifest manifest.mf`; the class name must include the exact package |
| `ClassNotFoundException`/`NoClassDefFoundError` for the agent | Packaged with wrong directory/package structure or missing dependency | Run `jar --list --file ...` to verify `example/agent/StartupMarkerAgent.class` is present |
| Agent loads but reports an invalid `premain` method | Wrong method name, not `public static`, or wrong signature | Use the exact signature `public static void premain(String, Instrumentation)` |
| JVM exits before `[APP] main begin` | Corrupted agent JAR or `premain` threw an unhandled exception | Read stderr, rerun the no-agent baseline, and fix the agent first |
| `options=null` | Ran `-javaagent:path.jar` **without** `=...` | Pass `=phase=boot` when you want to verify an explicit option string; `null` when no options are passed is valid |
| No `[AGENT]` markers appear, yet the app still runs | Forgot `-javaagent` or placed it in the wrong position | Place the option **before** the main class name or before `-jar <app>` |
| `Could not find or load main class ...` | `-cp` points to the wrong compiled output directory | Use `-cp build/app example.app.StartupOrderDemo` |
| Markers print out of order when integrating into a real app | Logs from multiple threads, async loggers, or stderr interleaving with stdout | Repeat with a single-threaded test; separate app/agent markers from framework logs |

**Note on argument placement:** in a `java` command, all JVM options must be placed before the name of the class containing `main`. For example, `java -cp build/app example.app.StartupOrderDemo -javaagent:...` **does not enable the agent**: anything after the main class name becomes an argument to `main(String[] args)`.

**Note on the manifest:** the space after the colon and the trailing newline in the manifest are significant according to the JAR manifest format. When editing `manifest.mf`, recompile/repackage the JAR; editing the external file alone does not update the manifest inside the `.jar`.

## 9. Comprehension Check Exercises

1. **Omit `-javaagent`:** how many `[AGENT]` lines appear? **0**. The baseline run produces the 5 APP/WORK marker lines.
2. **Pass `=trace` instead of `=phase=boot`:** which line changes? Only the `[AGENT] options=...` line; sample behavior does not change because the code only prints that string.
3. **Repeat the same JAR twice:** how many times does `premain` run? **2** times, matching the two declarations; the static initializer of the same agent class identity runs only **once** in that JVM.
4. **Swap the `-javaagent` order:** in what order do `first`/`second` appear? In the order written on the command line, not alphabetically.
5. **Add another `new Work()` call in `main`:** does `[WORK] class initialized` print twice? **No**, not within the same JVM; the `Work()` constructor prints **twice** because two instances are created.
6. **Can you conclude from the output that the agent modified bytecode?** **No.** The Instrumentation API is available, but the agent does not register a transformer and does not modify code.
7. **Can you conclude that the agent runs before all internal JVM activity?** **No.** The JVM has already initialized part of the runtime and may load classes before `premain`; the guarantee here is that it runs before the application's `main`.

## 10. Self-Verification Checklist

- [ ] Using JDK 17+, with `java`/`javac`/`jar` available.
- [ ] Agent class has the exact name, package, and signature `public static void premain(String, Instrumentation)`.
- [ ] `manifest.mf` declares `Premain-Class: example.agent.StartupMarkerAgent`.
- [ ] JAR contains `example/agent/StartupMarkerAgent.class`.
- [ ] Baseline output contains only `[APP]` and `[WORK]` markers.
- [ ] With one `-javaagent`: all `[AGENT] premain ...` markers appear before `[APP] main begin`.
- [ ] With two `-javaagent` options: `first`/`second` options are printed in exact command-line order.
- [ ] When reading logs, you can distinguish class initialization, `premain` invocation, `main` invocation, and instance construction.

## Authoritative References

- [Java SE 17 — Package java.lang.instrument, Starting an Agent from the Command-Line Interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class` manifest attribute, `premain` signatures, options, startup failures, and multiple-agent ordering.
- [Java SE 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent API specification; the example also works on modern JDKs.
- [Java SE 17 — JAR Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): how to create a JAR and include a manifest.
- [Java SE 17 — Java Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): placement of `-javaagent`/`-cp` options relative to the main class.
- [JLS 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-12.html#jls-12.4): class initialization rules, used to explain the `class initialized` markers.
