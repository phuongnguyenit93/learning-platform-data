# Creating a Minimal premain Agent and Observing Execution Before main

**Topic:** Java Advance → instrumentation → **Agent practice**.

`premain` is the entry point of a **Java startup agent**: when running `java -javaagent:agent.jar ...`, the JVM reads `Premain-Class` in the agent JAR's manifest, loads the agent class, and invokes the `premain` method **before invoking the application program's `main(String[])` method**. This is the simplest way to verify that an agent starts early, receives initialization options, and obtains the `Instrumentation` object provided by the JVM.

Lab objectives:

1. Write the **smallest observable Java agent**: a class with `public static void premain(String, Instrumentation)`.
2. Create a valid **manifest** containing `Premain-Class`, packaged with `jar` without Maven/Gradle.
3. Run the **same application** without the agent and with the agent, comparing **exact stdout**.
4. Prove the **agent `premain` → application `main`** order using both logs and a state set by the agent before `main` reads it.
5. Test **two `-javaagent` options on the same command line** and distinguish `agentArgs` from `main(String[] args)`.
6. Extend just enough with a `ClassFileTransformer` that only observes a class loaded after `main` starts, to understand that **`premain` before `main` does not mean every class is defined after `premain`**.
7. Know how to diagnose manifest errors, JAR paths, entry point signatures, arguments, and class initialization timing.

**Prerequisites:** JDK 17+ with `javac`, `jar`, and `java`, Bash Terminal or Windows PowerShell. The example requires no native attach, no external library downloads, no network access, no class file modification, and can be verified directly from stdout.

> **Distinction to make from the start:** `premain` is called after the JVM has performed the necessary initialization steps, and **before application `main`**. It is **not the very first Java code of the entire JVM**: JVM/agent infrastructure may have already loaded and initialized JDK or agent support classes beforehand. Do not assume the list of loaded classes at `premain` is empty.

## 1. Startup Flow Diagram

```text
Shell/launcher
    |
    | java -javaagent:startup-agent.jar=phase=boot
    |      -cp app-classes demo.DemoApp red blue
    v
JVM initializes required foundational components
    |
    +-- Reads startup-agent.jar!/META-INF/MANIFEST.MF
    |      Premain-Class: demo.StartupAgent
    |
    +-- Loads demo.StartupAgent
    |      (agent static initialization, if any)
    |
    +-- Invokes demo.StartupAgent.premain(agentArgs, instrumentation)
    |      agentArgs = "phase=boot"
    |      Instrumentation provided by the JVM
    |      agent can register transformers / prepare telemetry
    |
    +-- premain returns normally
    |
    +-- Invokes demo.DemoApp.main(String[] args)
           args = ["red", "blue"]
```

**Why does "returns normally" matter?** The JVM must complete the startup agent before transferring control to application `main`. If `premain` throws an unhandled exception or lacks a valid entry point, the JVM **may abort startup**; that is a startup agent failure, not a failure caused by application `main` running.

This mechanism is specified in the `java.lang.instrument` package. The JVM invokes one of two overloads:

```java
// API signature fragment, not a standalone program.
public static void premain(
        String agentArgs,
        java.lang.instrument.Instrumentation inst);

public static void premain(String agentArgs);
```

The JVM **prefers the signature with `Instrumentation`**; if it is absent, it falls back to the signature taking only `String`. The main example uses the first signature to demonstrate that the agent receives a real instrumentation object from the JVM. The name `premain` must be written in **exact lowercase**, not `preMain`, `Premain`, or `main`.

### 1.1. Roles in the Program

| Component | Role | Requirement |
| --- | --- | --- |
| `-javaagent:startup-agent.jar` | JVM startup option | Placed **before** the application main class name or before `-jar` |
| `startup-agent.jar` | Artifact containing the agent | Contains the manifest and `demo/StartupAgent.class` |
| `Premain-Class` | Manifest main attribute | Value is a **fully qualified binary class name** with dots |
| `premain` | Java agent startup entry point | `public static void`, one of the two valid signatures |
| `agentArgs` | Agent options | A single string passed verbatim by the JVM; the agent parses it itself |
| `Instrumentation` | API provided by the JVM | Not instantiated via `new Instrumentation()` |
| `-cp app-classes` | Where to find application classes | Not the path to the agent JAR |
| `demo.DemoApp` | Application main class | Has `public static void main(String[])` |
| `red blue` | Application arguments | Passed to `main`, not to `premain` |

## 2. Custom Project Structure

Create a learning directory, for example `premain-lab`, with the following files:

```text
premain-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── StartupAgent.java
│       ├── DemoApp.java
│       ├── WatchingAgent.java
│       ├── LoadApp.java
│       └── LazyTarget.java
├── watching-agent.mf
├── agent-classes/         # generated when compiling
├── app-classes/           # generated when compiling
├── startup-agent.jar      # generated by jar
└── watching-agent.jar     # generated by jar
```

**The two files `WatchingAgent.java` and `watching-agent.mf` are only for the extension exercise later.** For the minimal `premain` experiment, initially only `StartupAgent.java`, `DemoApp.java`, and `agent.mf` are needed.

Having two separate output directories helps show the boundary:

- `agent-classes` holds the classes packaged into the agent JAR.
- `app-classes` holds the application class. `DemoApp` has no compile-time dependency on `StartupAgent`.

We **do not modify the application source when toggling the agent**: both runs use the exact same `DemoApp.class` and only change the launcher flag.

## 3. Minimal Agent Code

### 3.1. `src/demo/StartupAgent.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    private StartupAgent() {}

    public static void premain(
            String agentArgs, Instrumentation inst) {

        System.out.println("AGENT_PREMAIN=" + agentArgs);
        System.out.println(
                "INSTRUMENTATION_PRESENT=" + (inst != null));

        // State demonstrating a check for main.
        System.setProperty("demo.premain.ready", "true");
    }
}
```

This is **a complete Java agent for testing startup**, even though it does not perform bytecode transformation yet:

- The JVM reads the manifest and locates class `demo.StartupAgent`.
- The JVM invokes `premain` with the argument string supplied by the `-javaagent` option.
- `inst != null` prints `true` on an API-compliant JVM; the `Instrumentation` object is not created by application code.
- The agent sets the system property `demo.premain.ready=true` to create an **observable marker**. Since application `main` reads the property afterward, we verify ordering without relying on timestamps or thread scheduling.
- The agent **does not call `Instrumentation.addTransformer`**, does not manipulate bytes, does not attach, and does not create threads.
- No `throws Exception` is needed; if an uncaught error occurs in `premain`, the JVM may abort startup.

**Correctness note:** `System.setProperty` here is an **intentional side effect for the lab**. A production observability agent should not arbitrarily modify application properties/shared state. The before/after log pair illustrates ordering; the property flag is not an authentication or anti-tampering mechanism, because a user can also set `-Ddemo.premain.ready=true` without running the agent.

### 3.2. `src/demo/DemoApp.java`

```java
package demo;

import java.util.Arrays;

public final class DemoApp {
    private DemoApp() {}

    public static void main(String[] args) {
        System.out.println("APP_MAIN");
        System.out.println("READY_AT_MAIN="
                + Boolean.getBoolean("demo.premain.ready"));
        System.out.println("APP_ARGS=" + Arrays.toString(args));
    }
}
```

The main program does not import `java.lang.instrument` and does not call `StartupAgent.premain` directly. It only:

1. Prints `APP_MAIN`.
2. Reads the flag via `Boolean.getBoolean(propertyName)`: returns `true` when the system property equals the string `"true"` case-insensitively.
3. Prints the arguments passed by the JVM to `main`.

**Common mistake:** `Boolean.getBoolean("demo.premain.ready")` **does not** parse that string as a boolean literal; it **looks up the system property named** `demo.premain.ready` and then parses the property value. That is exactly what we need for this lab.

### 3.3. `agent.mf` — Minimal Manifest

```text
Manifest-Version: 1.0
Premain-Class: demo.StartupAgent
```

Save the file as UTF-8 or ASCII text (this content is all ASCII) and **end with a trailing newline**, following the manifest convention. The attribute name must be `Premain-Class` and the value must be `demo.StartupAgent`, **not** `demo/StartupAgent` or `StartupAgent.java`.

For this minimal agent, the following are not needed:

- `Agent-Class`: used when loading a Java agent after startup via the attach mechanism, not required for `-javaagent`.
- `Can-Redefine-Classes`: for class redefinition capability.
- `Can-Retransform-Classes`: for class retransformation capability.
- `Boot-Class-Path`: not needed because the agent does not instrument bootstrap types.
- `Main-Class` in the agent JAR: we do not run `java -jar startup-agent.jar`; we load it via `-javaagent` and run the application separately with `-cp`.

`jar --manifest` will add the standard metadata required when creating the JAR. Do not put everything on a single line or omit the trailing newline at the end of the manifest file.

## 4. Compiling and Packaging with JDK 17+

### 4.1. Linux/macOS Bash Commands

From inside the `premain-lab` directory:

```bash
mkdir -p agent-classes app-classes

javac --release 17 -d agent-classes src/demo/StartupAgent.java
javac --release 17 -d app-classes src/demo/DemoApp.java

jar --create --file startup-agent.jar \
    --manifest agent.mf -C agent-classes .

jar --list --file startup-agent.jar
```

Meaning:

- `javac --release 17` produces Java 17-compatible class files and restricts APIs to release 17.
- `-d agent-classes` / `-d app-classes` preserves the `demo/` package structure.
- `jar --create --file ... --manifest agent.mf` creates the startup agent JAR with the specified manifest.
- `-C agent-classes .` tells `jar` to include the **contents** of the output directory in the JAR (without including the `agent-classes` directory name in the class entry path).
- `jar --list` lets you inspect the artifact. Output may include timestamps/additional entries depending on the tool, so do not hardcode the entire output; at a minimum it must contain `META-INF/MANIFEST.MF` and `demo/StartupAgent.class`.

### 4.2. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path agent-classes,app-classes | Out-Null

javac --release 17 -d agent-classes src/demo/StartupAgent.java
javac --release 17 -d app-classes src/demo/DemoApp.java

jar --create --file startup-agent.jar --manifest agent.mf -C agent-classes .
jar --list --file startup-agent.jar
```

The Java source files and manifest **remain identical**. In PowerShell, write the `jar` command on a single line so you do not accidentally use Bash's `\` line-continuation syntax. Common relative directory separators on Windows/JDK can use `/` in JDK command file paths; if a specific shell environment requires it, use the equivalent Windows path.

### 4.3. Checking the Artifact Before Running

```bash
jar --list --file startup-agent.jar
```

Expected key entries in the listing:

```text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/StartupAgent.class
```

Ordering and metadata entries beyond this list may vary. If you see `agent-classes/demo/StartupAgent.class` instead of `demo/StartupAgent.class`, the packaging is wrong: the JVM will not find class `demo.StartupAgent` from the root of the JAR.

If the manifest is missing `Premain-Class`, starting with `-javaagent` will fail even if the JAR contains valid class bytecode. **Check both the manifest contents and the class entry**, not just that the filename ends with `.jar`.

## 5. Run 1: Baseline Without a Java Agent

```bash
java -cp app-classes demo.DemoApp
```

**Exact stdout** when running in a clean JVM with no extraneous flags/properties setting `demo.premain.ready`:

```text
APP_MAIN
READY_AT_MAIN=false
APP_ARGS=[]
```

Why?

- The JVM locates `demo.DemoApp` in `app-classes`.
- There is no startup `-javaagent`, so `StartupAgent.premain` is not invoked.
- The system property has not been set, so `Boolean.getBoolean("demo.premain.ready")` is `false`.
- No application arguments were passed, so `Arrays.toString(args)` is `[]`.

The same application can run normally **without the agent**. This is an important check: if the app source directly called `StartupAgent.premain`, it would be a regular program using a helper rather than proving the JVM startup-agent mechanism.

## 6. Run 2: Enabling `-javaagent`

```bash
java -javaagent:startup-agent.jar=phase=boot \
    -cp app-classes demo.DemoApp red blue
```

Single-line Windows PowerShell:

```powershell
java -javaagent:startup-agent.jar=phase=boot -cp app-classes demo.DemoApp red blue
```

**Exact stdout** from the lab's Java code:

```text
AGENT_PREMAIN=phase=boot
INSTRUMENTATION_PRESENT=true
APP_MAIN
READY_AT_MAIN=true
APP_ARGS=[red, blue]
```

What this proves:

1. `AGENT_PREMAIN` appears **before** `APP_MAIN`, matching the JVM startup agent contract.
2. `Instrumentation` is available at `premain`, so `INSTRUMENTATION_PRESENT=true`.
3. The agent sets the property before `premain` finishes; `main` reads `READY_AT_MAIN=true`.
4. The string `phase=boot` is **agentArgs**; `red blue` are **application arguments**.
5. There is no bytecode processing in this example, yet the agent is still valid and runs before `main`.

**What cannot be concluded from this stdout:** how many classes the JVM has loaded at that point, which classes have been verified/initialized, the exact number of nanoseconds before `main`, or whether agent code has modified any class file. This exercise proves **entry point ordering** and **the presence of Instrumentation**, not automatic instrumentation of every class.

### 6.1. Why Not Use Timestamps for Comparison?

If you also log `System.nanoTime()`, timestamps change on every run and have no absolute epoch across processes. For the "premain before main" question, **two logs in the same process** on the same output stream and a property marker set by the agent are simpler and easier to test. When you need to measure real startup overhead, use a multi-fork benchmark with consistent JDK/VM flags and report statistical measurements rather than drawing conclusions from a single startup interval.

### 6.2. Distinguishing `-D`, `-javaagent`, and App Args

Example:

```text
-javaagent:startup-agent.jar=phase=boot
    ^ VM option, passes phase=boot to premain

-Ddemo.premain.ready=true
    ^ independent VM option: sets a system property

demo.DemoApp red blue
             ^ arguments to main(String[] args)
```

Setting `-Ddemo.premain.ready=true` can make the baseline print `READY_AT_MAIN=true` **without** `AGENT_PREMAIN`; therefore, when proving the mechanism, always check both the **premain log** and the launcher command. The property is only a learning marker, not a security key or a measure of instrumentation activity.

## 7. Running Two Java Startup Agents Simultaneously

Oracle JDK 17 allows the `-javaagent` option to appear multiple times, even for **the same JAR**. The `premain` methods are invoked in the order they appear on the command line.

```bash
java -javaagent:startup-agent.jar=first \
    -javaagent:startup-agent.jar=second \
    -cp app-classes demo.DemoApp
```

Stdout:

```text
AGENT_PREMAIN=first
INSTRUMENTATION_PRESENT=true
AGENT_PREMAIN=second
INSTRUMENTATION_PRESENT=true
APP_MAIN
READY_AT_MAIN=true
APP_ARGS=[]
```

Here the same `StartupAgent` code is invoked **twice** by the JVM during startup, not application `main` invoked twice. The argument strings for the two `premain` calls are `first` and `second`, respectively; the application still has only one `APP_MAIN`.

What to understand for production:

- Invoking an agent twice can create **two sets of transformers** if each `premain` registers one, leading to duplicate logs or repeated instrumentation.
- `premain` order alone does not prove final transformation order when class loading, transformer chaining, or complex interactions are involved; read the `ClassFileTransformer` contract and inspect bytes when needed.
- An agent should have an initialization guard/idempotency if it supports multiple invocations and wants to avoid duplicate hooks.
- Do not assume startup agents from different vendors will not conflict on classloaders, module accessibility, logging, or native dependencies.
- If one `premain` throws an uncaught exception, the JVM may abort before reaching `main` or subsequent startup steps.

## 8. Extension: Registering a Transformer in `premain`

In the minimal step, `premain` only logs and sets a property. We can add a **class-load-observation-only** experiment: the agent registers a `ClassFileTransformer` inside `premain`, and the application intentionally loads a class named `demo.LazyTarget` after `main` prints its start marker.

This answers the question: **if `premain` truly runs before `main`, when is the transformer registered, and does it see a class loaded afterward?**

To avoid complicating the stdout of the first lab, use a **second agent** named `WatchingAgent`. It only reads the class name and **returns `null`**, without modifying bytes.

### 8.1. `src/demo/WatchingAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class WatchingAgent {
    private WatchingAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("WATCHER_PREMAIN");

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if ("demo/LazyTarget".equals(className)) {
                    System.out.println("WATCHED_LOAD=demo/LazyTarget");
                }

                // Do not modify the classfileBuffer array.
                return null;
            }
        });
    }
}
```

Points to verify:

- `inst.addTransformer(...)` registers a callback for subsequent class definitions. The JVM may invoke the callback when a class is loaded, redefined, or retransformed depending on registration type; this lab only examines **load-time**.
- `className` uses the internal name with `/`: `demo/LazyTarget`, **not** `demo.LazyTarget`.
- `return null` is the contract for **not transforming the class file**, not "returning an empty class file".
- Never mutate `classfileBuffer` in place. If transformation is needed, return a new, valid `byte[]`.
- `classBeingRedefined` is typically `null` on initial load; do not assume it is always non-null.
- The callback may be invoked many times for other classes; filtering by class name **before logging** avoids a log storm.
- In JDK 9+, the interface also has a six-parameter overload with `Module`; the five-parameter override in this example remains supported via the forwarding default overload.

**Note:** when code runs inside a transformer, operations such as logging or reflection can trigger additional class loading and reentrancy. This exercise logs only one specific class; a real tool must design initialization/reentrancy guards and exclude agent/helper classes.

### 8.2. `src/demo/LazyTarget.java`

```java
package demo;

public final class LazyTarget {
    static {
        System.out.println("LAZY_TARGET_INITIALIZED");
    }

    private LazyTarget() {}
}
```

The `static` block is the **class initializer**, which is not synonymous with when the class file bytes are read. The JVM can **load** a class before it needs to initialize it.

### 8.3. `src/demo/LoadApp.java`

```java
package demo;

public final class LoadApp {
    private LoadApp() {}

    public static void main(String[] args) throws Exception {
        System.out.println("LOAD_APP_MAIN");

        ClassLoader loader = LoadApp.class.getClassLoader();
        Class.forName("demo.LazyTarget", false, loader);
        System.out.println("AFTER_LOAD_NOT_INIT");

        Class.forName("demo.LazyTarget", true, loader);
        System.out.println("AFTER_INITIALIZE");
    }
}
```

`Class.forName(name, false, loader)` can cause the JVM to load/link the target class **without running the class initializer during that call**. `Class.forName(name, true, loader)` requests initialization if the class has not been initialized yet. With a sample class that only has a logging `static` block, it is easy to distinguish **loading** from **initialization**.

### 8.4. `watching-agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.WatchingAgent
```

Remember the trailing newline. The difference between the two agent JARs is the `Premain-Class` value. `WatchingAgent` also does not need `Can-Retransform-Classes` because it only wants to observe a class loaded after the transformer has been registered.

### 8.5. Compiling and Packaging the Extension

At the `premain-lab` root after creating the extension files:

```bash
javac --release 17 -d agent-classes src/demo/WatchingAgent.java

javac --release 17 -d app-classes \
    src/demo/LoadApp.java src/demo/LazyTarget.java

jar --create --file watching-agent.jar \
    --manifest watching-agent.mf -C agent-classes .
```

The `jar` command also packages `StartupAgent.class` if it is already in `agent-classes`, but the manifest of `watching-agent.jar` specifies `demo.WatchingAgent`, so the JVM starts the right class. There is no conflict because only one `Premain-Class` belongs to the manifest.

On Windows PowerShell, write each command on a single line, omitting Bash's `\` line-continuation character:

```powershell
javac --release 17 -d agent-classes src/demo/WatchingAgent.java
javac --release 17 -d app-classes src/demo/LoadApp.java src/demo/LazyTarget.java
jar --create --file watching-agent.jar --manifest watching-agent.mf -C agent-classes .
```

### 8.6. Running and Comparing Output

Without the agent:

```bash
java -cp app-classes demo.LoadApp
```

Stdout:

```text
LOAD_APP_MAIN
AFTER_LOAD_NOT_INIT
LAZY_TARGET_INITIALIZED
AFTER_INITIALIZE
```

With the watcher:

```bash
java -javaagent:watching-agent.jar \
    -cp app-classes demo.LoadApp
```

Stdout in a **clean process**, assuming `demo.LazyTarget` has not been loaded earlier by another component:

```text
WATCHER_PREMAIN
LOAD_APP_MAIN
WATCHED_LOAD=demo/LazyTarget
AFTER_LOAD_NOT_INIT
LAZY_TARGET_INITIALIZED
AFTER_INITIALIZE
```

Line-by-line explanation:

1. `WATCHER_PREMAIN` prints before `LOAD_APP_MAIN`: the agent entry point precedes app `main`.
2. When `LoadApp.main` calls `Class.forName(..., false, loader)`, the registered transformer sees the bytes of `demo/LazyTarget` and prints `WATCHED_LOAD`.
3. `AFTER_LOAD_NOT_INIT` appears without `LAZY_TARGET_INITIALIZED`: the class has been loaded but not yet initialized.
4. `Class.forName(..., true, loader)` runs the `static` block before returning, so `LAZY_TARGET_INITIALIZED` prints before `AFTER_INITIALIZE`.
5. No new bytecode is output: the transformer returns `null`. The experiment proves observation of load timing, **not that the class was instrumented**.

If another agent or bootstrap code eagerly loads `LazyTarget` before the watcher is registered, the `WATCHED_LOAD` line may not appear even though the class is used later. This is not evidence of a JVM bug; control **class loading order** and test in a fresh process.

## 9. "Before main" Does Not Mean "Before Every Class"

This is an important theoretical point for agents:

```text
Before premain is called:
  The JVM already has bootstrap/runtime support classes;
  The JVM must locate/load the agent class;
  Agent class dependencies may load or initialize.

After premain returns:
  The JVM transfers control to application main;
  The application continues loading classes as needed.

Some class definitions can occur
before/during/after premain.
```

**Do not assume:** `getAllLoadedClasses().length == 0` in `premain`. In practice, a running Java JVM already has many foundational classes loaded beforehand.

If you want to inspect the list of loaded classes in `premain`:

```java
// Fragment, add to StartupAgent.premain.
Class<?>[] snapshot = inst.getAllLoadedClasses();
System.out.println("LOADED_CLASSES=" + snapshot.length);
```

The `LOADED_CLASSES` count is **empirical runtime data**, depending on JDK/JVM vendor, other agents, and runtime timing; you cannot write a fixed stdout number that applies to every machine. The snapshot does not auto-update and is not a list of every `.class` file on the classpath. If you need to track subsequent class loads, register a transformer/hook according to capabilities.

### 9.1. Loading and Initializing Are Two Different Milestones

| Milestone | Meaning | Signal in the example |
| --- | --- | --- |
| Transformer receives class-file bytes | The JVM is defining/transforming the class on that path | `WATCHED_LOAD=demo/LazyTarget` |
| Class loaded/linked by the JVM | A `Class<?>` exists for the type, depending on phase | `Class.forName(...,false,...)` returns |
| Class is initialized | `<clinit>` runs when required, per JLS/JVMS | `LAZY_TARGET_INITIALIZED` |
| Application `main` | Application entry point is invoked | `LOAD_APP_MAIN` |
| `premain` | Startup agent entry point | `WATCHER_PREMAIN` |

**Do not equate "the JVM has loaded the class" with "the constructor has run"**. The constructor `<init>` runs when instantiating an object; static initialization `<clinit>` is for class initialization. In the example, no `LazyTarget` instance is created, yet the `static` block still runs when `Class.forName(..., true, ...)` executes.

## 10. Distinguishing `premain`, `main`, and `agentmain`

| Entry point | When it runs | Artifact/trigger |
| --- | --- | --- |
| `premain(String, Instrumentation)` | Startup agent **before app main** | `-javaagent:agent.jar` with `Premain-Class` |
| `premain(String)` | Startup, fallback overload | Used if no overload taking `Instrumentation` exists |
| `main(String[])` | Application entry point | `java -cp ... MainClass` or `java -jar app.jar` |
| `agentmain(String, Instrumentation)` | Java agent loaded **after startup** if VM supports it | Attach API or equivalent mechanism with `Agent-Class` |
| `agentmain(String)` | Dynamic agent fallback overload | Used when no overload taking `Instrumentation` exists |
| `Agent_OnLoad` (native C) | Startup **native JVMTI agent** | `-agentlib`/`-agentpath`, not `-javaagent` |

Do not replace `Premain-Class` with `Agent-Class`, run with `-javaagent`, and expect the JVM to invoke `agentmain`. Conversely, the dynamic attach path normally does not invoke `premain`.

### 10.1. Java 21+ and Dynamic Agent Loading

JEP 451 (JDK 21) introduces warnings and prepares to restrict **dynamic agent loading** into a running JVM. **This lab uses `-javaagent` at startup**, so it requires no self-attach permission, no PID lookup, and is not an example of dynamic attach. When deploying to newer JDKs, check the specific JVM/runtime policy; do not assume all versions share the same default attach flags.

### 10.2. Can One JAR Contain Both the App and the Agent?

You can package an executable JAR with application/agent classes, but you must clearly distinguish the manifest attributes and how it is launched. When using **`-javaagent:agent.jar -jar app.jar`**, the JVM reads `Premain-Class` from **agent.jar**, and `Main-Class` to run the application from **app.jar**. The two JARs can be separate artifacts.

Java also has the `Launcher-Agent-Class` mechanism in executable JARs on supporting implementations, which has its own entry point/lifecycle (`agentmain` per the package spec) and is **not synonymous** with `Premain-Class` of `-javaagent`. To learn the difference in the simplest way, this lab uses two clear classpaths and separate agent JARs.

## 11. Common Mistakes When Running from the Terminal

### 11.1. Placing `-javaagent` in the Wrong Position

Correct:

```bash
java -javaagent:startup-agent.jar=demo \
    -cp app-classes demo.DemoApp
```

Wrong for the intended goal:

```bash
java -cp app-classes demo.DemoApp \
    -javaagent:startup-agent.jar=demo
```

In the second command, the string `-javaagent:startup-agent.jar=demo` appears **after the main class**, so it is passed as an **application argument**, no longer a JVM option. `DemoApp` may print it in `APP_ARGS`, but `premain` will **not be invoked by the JVM** from that flag. Do not assume "seeing `-javaagent` on the command line" means the agent ran.

Similarly:

```bash
java -jar app.jar -javaagent:startup-agent.jar
```

Arguments after `app.jar` go to the application; for the JVM to load the startup agent, place `-javaagent` **before `-jar`**:

```bash
java -javaagent:startup-agent.jar -jar app.jar
```

### 11.2. Confusing `-cp` and `-javaagent`

`-cp app-classes` tells the JVM where to find the **application main class**; it does not automatically locate the agent JAR. `-javaagent:startup-agent.jar` tells the JVM to locate the agent JAR and its manifest; it does not replace the application classpath. To run `DemoApp`, you still must specify `-cp app-classes` or an equivalent launcher option.

### 11.3. Confusing `Premain-Class` with a Java Filename

In the manifest:

```text
Premain-Class: demo.StartupAgent
```

Do not use:

```text
Premain-Class: StartupAgent.java
```

and do not use:

```text
Premain-Class: demo/StartupAgent
```

The manifest requires the class name `demo.StartupAgent`, whereas the class file resides at JAR entry `demo/StartupAgent.class`. Confusing the **binary class name** with the **JAR entry path** is a very common source of errors.

### 11.4. Missing Trailing Newline in the Manifest

A manifest has its own line-based format consisting of `Name: Value` attributes. A file that is not properly terminated may cause the last attribute not to be recognized as expected. Always ensure `agent.mf`/`watching-agent.mf` has a trailing newline and inspect the manifest packaged into the JAR. Do not rely solely on the filename `agent.mf` to conclude that `Premain-Class` was embedded.

### 11.5. Incorrect `premain` Signature

Example errors:

```java
// Invalid: not a signature accepted by java.lang.instrument.
private static void premain(String args) { }
public void premain(String args) { }
public static int premain(String args) { return 0; }
```

These are **error-illustration fragments**, not a standalone Java file. The entry point must be `public static void` with valid parameters. The package name of the class in the manifest must also match the compiled bytecode.

### 11.6. Unhandled Exceptions in `premain`

If `premain` throws an uncaught exception, the JVM may abort before running the application. In production, startup initialization should have a clear error policy: fail startup when the agent is mandatory, or fail-open when telemetry is optional and safe to skip. However, **never** swallow an error and report "agent active" if the transformer failed to register; you need a health indicator and effectiveness checks.

## 12. Quick Test Matrix, Beyond Checking a Single Log

| Test | Command / change | Expected |
| --- | --- | --- |
| A: No agent | `java -cp app-classes demo.DemoApp` | Only `APP_MAIN`, `READY_AT_MAIN=false` |
| B: One agent | `-javaagent:startup-agent.jar=phase=boot` | `AGENT_PREMAIN` appears before `APP_MAIN`, flag true |
| C: Two agents | Repeat two `-javaagent` flags: `first`/`second` | Two `premain` calls in order, `main` once |
| D: Options/args | `=phase=boot` and trailing `red blue` | `agentArgs` differs from `main args` |
| E: Agent flag after class | Misplaced option | `premain` does not run, `main` receives text as arg |
| F: Transformer load | `-javaagent:watching-agent.jar` + `LoadApp` | `WATCHER_PREMAIN` then load hook on `Class.forName` |
| G: Load without init | `Class.forName(...,false,...)` | `WATCHED_LOAD` before `LAZY_TARGET_INITIALIZED` |
| H: Watcher disabled | No `-javaagent` | App still loads and initializes target, no watcher logs |
| I: Missing manifest | Remove/change `Premain-Class` in a new test JAR | Startup agent fails; app `main` must not be treated as success |
| J: Wrong JAR path | Point to a nonexistent file | Java launcher reports an error, no valid `main` run |

For tests A–H, use a fresh JVM process each time. For negative tests I/J, **do not test on production systems** and do not hardcode stderr text that may vary across JDKs/vendors. Evaluate exit status and the meaningful presence/absence of logs.

### 12.1. Testing Twice with the Same JAR Without Prior Static State

Two separate `java` commands are two separate JVM processes: static fields and system properties do not persist into a new run. If you run two tests inside the same JVM (e.g., a JUnit test creating multiple classloaders), do not treat that as "restarting the JVM"; `premain` is not re-invoked by the JVM just because you call another method.

## 13. From Minimal Agent to Real Instrumentation

Once `premain` works, measuring or transforming code requires registering a transformer or using other methods on `Instrumentation`:

| API | Purpose |
| --- | --- |
| `inst.addTransformer(transformer)` | Observe/transform class files via callback for matching definitions |
| `inst.addTransformer(transformer, true)` | Register a retransformation-capable transformer if VM/manifest permits |
| `inst.getAllLoadedClasses()` | A snapshot of currently loaded runtime classes |
| `inst.getInitiatedClasses(loader)` | Classes that `loader` can find by name as an initiating loader |
| `inst.isRetransformClassesSupported()` | Check whether the JVM supports retransformation per agent capability |
| `inst.isModifiableClass(clazz)` | Whether a specific class can be modified |
| `inst.retransformClasses(clazz)` | Request retransformation when conditions permit |
| `inst.redefineClasses(...)` | Request redefinition with valid class definitions |
| `inst.removeTransformer(transformer)` | Unregister a transformer; does not undo already transformed bytes |

**No API in a Java app creates `Instrumentation` on its own**. The JVM supplies the handle to `premain` or `agentmain` per the contract. Having the handle does not mean every class is modifiable; some classes/VMs do not support retransformation or schema changes.

Example fragment getting the runtime class count:

```java
// Fragment inside premain, not a standalone program.
int count = inst.getAllLoadedClasses().length;
System.out.println("CURRENT_LOADED_CLASSES=" + count);
```

The count depends on runtime state; **do not hardcode the output**. And if an agent registers a transformer after a target class has already been loaded, the transformer **does not retroactively** receive that class's initial load. Processing already-loaded classes may require `retransformClasses`/`redefineClasses` subject to capability and modifiability, rather than assuming `addTransformer` transforms all previously loaded classes.

### 13.1. Why Does `transform` Return `null` in the Extension?

`ClassFileTransformer` contract: the JVM passes `byte[] classfileBuffer` as input, and the transformation **must not modify this array directly**. If no changes are made, return `null`. If transforming, return a **new `byte[]`** containing a valid class file. `WatchingAgent` only observes `demo/LazyTarget`, so it returns `null`, allowing the application program to continue completely unchanged.

In production, a transformer may call a bytecode library such as ASM/Byte Buddy or the Class-File API on JDK 24+, but that is the next step. A **minimal agent** is completely valid without any bytecode library dependency.

## 14. Observing Ordering When a Program Has Class Initializers

Java has multiple distinct moments in time:

- **Agent class initialization**: The JVM initializes `StartupAgent` before calling its `premain` method (per active-use rules). If there is a `static { ... }` block in the agent class, its log may appear **before `AGENT_PREMAIN`**.
- **Application class loading**: The JVM may load a class while locating/verifying/linking it, without necessarily initializing it yet.
- **Application class initialization**: `<clinit>` runs when Java initialization conditions are met; `Class.forName(name,true,loader)` explicitly requests this.
- **Application `main`**: The `main` method is called by the JVM after the startup agent completes. Do not assume no application classes have been loaded before that point.

The extension uses `LazyTarget` to show the **load hook firing before the class initializer**, without altering behavior. In a plugin/reflective framework, a class may be loaded by multiple classloaders: a class name string alone **is not enough** to uniquely identify a runtime type; when instrumenting real targets, consider defining loader identity.

### 14.1. Ordering Logs vs. Wall-Clock Time

The two lines `AGENT_PREMAIN`/`APP_MAIN` prove ordering within the same process, but do not tell you exact startup latency. If you want to measure "how many ms does the agent add to JVM startup", design a dedicated benchmark:

1. Run multiple baseline and agent JVM processes with the same app/JDK.
2. Measure **launcher-to-ready** time externally or an equivalent readiness criterion, not just the duration of `premain`.
3. Report median, p95/p99, and variance; avoid drawing conclusions from a single cold run.
4. Control for class loading, JIT, disk page cache, container CPU, and GC.
5. Distinguish startup overhead, steady-state throughput/latency, and exporter cost.
6. Do not let an agent log heavily inside class-load callbacks and assume logging is "free".

## 15. Java Version and Environment Notes

- `-javaagent`/`java.lang.instrument` has long been supported on compliant Java SE/JDK implementations; this lab chooses **Java 17+** for consistent APIs and launcher commands.
- `--enable-preview` is not needed for `premain` or `Instrumentation` in Java 17.
- With `javac --release 17`, the lab's class files have major version 61; newer compatible JDKs can run them, but you must check dependencies and module/loader policies on the target JVM.
- `java.instrument` is the standard JDK module containing `Instrumentation`; the example runs on the classpath/unnamed module and requires no complex module configuration.
- Not every embedded/minimal JVM runtime image supports the agent startup option; when building a custom runtime image via `jlink`, verify that the appropriate module/capability is included.
- Some launchers pick up extra arguments from `JDK_JAVA_OPTIONS` or `JAVA_TOOL_OPTIONS`; if the baseline shows unexpected agent logs, check the environment/JDK tooling rather than looking only at the command line you just typed.
- `-javaagent` is for Java JARs. `-agentlib`/`-agentpath` are for native agent shared libraries with `Agent_OnLoad`, not alternative syntax for JAR files.
- If an agent dependency requires a newer Java version than the runtime, `UnsupportedClassVersionError` may occur before application `main`. Compile/bundle targeting the **minimum host JDK**, not just the development machine's JDK.

## 16. Startup Agent Security and Reliability

An agent runs inside the same JVM process and has very strong privileges: it can read runtime state, alter class definitions, open module boundaries when permitted, and affect application logic. Because `premain` runs **before app main**, an initialization error can prevent the entire application from starting.

In real deployments:

- Only load trusted agent JARs; verify provenance, checksums/signatures, licenses, and dependencies.
- Do not allow untrusted users to override the `-javaagent` path before startup.
- Keep `premain` short; avoid synchronous network calls without timeouts, deadlocks, or excessive allocations during JVM initialization.
- Decouple telemetry export from the startup/business critical path, using bounded queues and proper failure isolation.
- Do not pass secrets/passwords in `agentArgs` if the command line may be visible to process inspection tools; prefer proper secret management.
- Do not arbitrarily instrument JDK/bootstrap/logger/agent helper classes, avoiding reentrant loading/`StackOverflowError` and class loader visibility failures.
- Explicitly define a fail-open or fail-fast policy: compliance-critical agents differ from optional tracing agents.
- When agent startup reports success but no events are collected, verify that the **transformer is registered** and the **target class is observed**; a `premain` log only proves the entry point ran.
- Maintain a rollback/disable path for `-javaagent` in the launcher/container image in case a new agent introduces a regression.

## 17. Troubleshooting and Diagnostics Table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No `AGENT_PREMAIN`, app still runs | `-javaagent` not passed or passed after main class | Check launcher option placement |
| `Failed to find Premain-Class manifest attribute` | Manifest lacks `Premain-Class` | Inspect manifest inside JAR, rebuild |
| Agent `ClassNotFoundException` | Wrong package/name or class entry at wrong path | `jar --list`, `Premain-Class` |
| Agent class exists but startup fails | Wrong `premain` signature or method not `public static void` | Verify exact overload |
| JVM aborts before `APP_MAIN` | Uncaught exception in `premain`/agent init | Check stack trace, fail policy |
| `NoClassDefFoundError` | Agent missing dependency or wrong classloader visibility | Package dependency properly, check modules |
| `UnsupportedClassVersionError` | Agent JAR compiled for too high a JDK | Build with proper `--release` and test target JDK |
| `READY_AT_MAIN=false` despite agent | Agent did not set property properly or property was overwritten | Check code and JVM flags |
| `APP_ARGS` contains `-javaagent:...` | JVM option placed after application main class name | Move option before main class |
| Only `APP_MAIN` seen when watcher runs | Wrong watcher JAR/manifest or class already loaded earlier | Check class loading and `Premain-Class` |
| `WATCHED_LOAD` missing | Wrong internal name; target loaded before transformer; output filter | Check `demo/LazyTarget` and `Class.forName` timing |
| `LAZY_TARGET_INITIALIZED` appears before `AFTER_LOAD_NOT_INIT` | Other code eagerly initialized target | Run in clean JVM, check `Class.forName` initialize flag |
| Transformer causes `VerifyError` | Bytecode edit broke frames/stack | Return `null` in observer; use bytecode verifier when transforming |
| Slow program startup | Heavy synchronous agent init / network / scanning | Profile startup, limit work in `premain` |
| Agent logs printed twice | Two `-javaagent` flags or duplicate transformer registration | Check launcher/config and idempotency |
| Incorrect agent options | Confusing `agentArgs` with `main` args | Log string received in `premain` and `main` array |
| App runs with no transformer events | Agent only prints `premain` without `addTransformer` | Register transformer, test target class |
| JVM does not support option/capability | Different runtime image/module/VM policy | Check JDK vendor/runtime configuration |

**Do not assume JVM stderr output is a fixed string**: exact error wording and exit codes can vary across JDKs/vendors. For successful runs, the stdout lines of the Java code in sections 5–8 are the values explained from the source and clean-run conditions.

## 18. Testing and Self-Assessment Checklist

- [ ] Created both sources `StartupAgent.java` and `DemoApp.java` in package `demo`.
- [ ] `StartupAgent` has `public static void premain(String, Instrumentation)`.
- [ ] Manifest `agent.mf` has `Premain-Class: demo.StartupAgent` and a trailing newline.
- [ ] `jar --list` confirms `META-INF/MANIFEST.MF` and `demo/StartupAgent.class`.
- [ ] Baseline without agent prints `APP_MAIN`, `READY_AT_MAIN=false`, and `APP_ARGS=[]`.
- [ ] Agent run prints `AGENT_PREMAIN` and `INSTRUMENTATION_PRESENT=true` before `APP_MAIN`.
- [ ] Main run with agent reads `READY_AT_MAIN=true` and correct arguments.
- [ ] Agent `phase=boot` is not mixed into `APP_ARGS=[red, blue]`.
- [ ] Two `-javaagent` flags actually invoke `premain` twice in order.
- [ ] App runs normally when the agent is removed and has no direct dependency on the agent class.
- [ ] Watcher extension only logs `demo/LazyTarget` and does not modify `classfileBuffer`.
- [ ] `Class.forName(..., false, ...)` does not run the static initializer, while `true` triggers initialization.
- [ ] Class name in the transformer uses internal form `demo/LazyTarget`.
- [ ] Do not confuse `premain` with `agentmain`, `Main-Class`, or native `Agent_OnLoad`.
- [ ] Do not assume `premain` runs before all JVM class loading.
- [ ] Do not fabricate loaded class counts, startup timings, or stderr lines.
- [ ] Handle agent startup failures: fail-fast if mandatory, controlled fail-open if optional.
- [ ] Verify JVM/module policy, JDK baseline, and agent provenance before production.
- [ ] When performing real instrumentation, include transformer verification and behavior tests beyond `premain` logs.

## 19. Self-Check Questions

1. **Which class contains `premain`?**  
   The class specified by the `Premain-Class` manifest attribute, e.g., `demo.StartupAgent`.

2. **Is a `main` method needed in the agent JAR?**  
   No. `-javaagent` uses `Premain-Class` and `premain`; the application has its own `main`.

3. **Does the JVM invoke `premain` before or after application `main`?**  
   Before. `premain` must complete normally for startup to proceed to `main`.

4. **Is `premain` the very first Java code the JVM ever runs?**  
   No. JVM/platform/agent classes may load/initialize before that point.

5. **Which signature does the JVM try first?**  
   `premain(String, Instrumentation)`. If absent, it looks for `premain(String)`.

6. **Do you need to instantiate `Instrumentation` with `new`?**  
   No. The JVM supplies the instance to the agent entry point.

7. **What do `AGENT_PREMAIN=phase=boot` and `APP_ARGS=[red, blue]` prove?**  
   The option string after `=` in `-javaagent` is distinct from the arguments placed after the application main class.

8. **If you run `java -cp app-classes demo.DemoApp -javaagent:startup-agent.jar`, does the JVM load the agent?**  
   Not with that syntax; the string after the main class is an application argument.

9. **Can two `-javaagent` options point to the same JAR?**  
   Yes, per the Java agent package specification. `premain` is invoked in flag order.

10. **If `Premain-Class` is missing while `StartupAgent.class` is still present, does the JVM find it automatically?**  
    No. The manifest identifies the startup agent class.

11. **Why does `Class.forName(..., false, loader)` in the watcher lab load the class without printing `LAZY_TARGET_INITIALIZED`?**  
    Because the `false` parameter does not request running the target's class initializer.

12. **Does `WatchingAgent` modify bytecode?**  
    No; the transformer only logs the target class and returns `null`.

13. **Does calling `addTransformer` after the target has loaded automatically transform the target?**  
    No. An appropriate retransform/redefine path is needed if the class is already loaded and the VM/capabilities permit it.

14. **Does `getAllLoadedClasses()` in `premain` return a fixed count across all JVMs?**  
    No; the class count depends on runtime state and timing, and is not a fixed output of this exercise.

15. **If an agent's `premain` throws an uncaught exception, is application `main` guaranteed to run?**  
    No. A startup agent failure can cause the JVM to abort.

16. **Is `Can-Retransform-Classes` required for an agent that only logs?**  
    No. The lab does not perform retransformation.

17. **Are `Agent-Class` and `Premain-Class` synonymous?**  
    No. They specify two different ways of loading a Java agent: dynamic vs. startup.

18. **If the watcher logs `WATCHED_LOAD`, does that prove the class has been initialized?**  
    No; the class-loading hook and class initializer are two different milestones.

19. **To measure startup overhead, is a single timestamp log enough?**  
    No. Multiple JVM forks, launcher-to-ready time, consistent configuration, and variance analysis are needed.

20. **When is a "premain before main" experiment considered successful?**  
    When the baseline has no agent logs, the agent run prints `premain` before `main`, the flag is read by `main` as expected, and the corresponding command/JAR/manifest are all verified.

## 20. Official References

1. **Oracle JDK 17 — `java.lang.instrument` package** (startup JAR, `Premain-Class`, `premain` overloads, ordering of multiple agents, and startup errors): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
2. **Oracle JDK 17 — `Instrumentation`** (received from `premain`, registering transformers, getting loaded classes, capability checks): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
3. **Oracle JDK 17 — `ClassFileTransformer`** (five-/six-argument callbacks, input bytes, `return null` when unchanged): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. **Oracle JDK 17 — `java` launcher** (`-javaagent`, `-cp`, `-jar`, and application argument ordering): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
5. **Oracle JDK 17 — `jar` tool** (`--create`, `--manifest`, `--list`, and `-C`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
6. **Oracle JDK 17 — `Class.forName(String,boolean,ClassLoader)`** (load vs. initialize): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
7. **Oracle JDK 17 — JAR File Specification, manifest attributes:** https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
8. **OpenJDK JEP 451 — dynamic agent loading warnings** (distinct from `-javaagent` startup): https://openjdk.org/jeps/451
9. **Java Virtual Machine Specification `5.5` — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html

**Conclusion:** To prove that a Java agent runs before the program, you do not need ASM or bytecode transformation: a **JAR with a `Premain-Class` manifest, a `public static void premain(String, Instrumentation)` method, the `java -javaagent:...` command, and an independent app `main`** are enough. Compare the baseline with the agent run, verify log ordering and the property marker in `main`. Then register a class-load-observing transformer to see that **`premain` before `main`** is a specific point in time, not a claim that the JVM has never loaded any class before the agent.
