# Initializing configuration, helpers, and transformers before the application runs

## 1. Goals of a startup Java agent

A **startup Java agent** is Java code that runs inside the JVM via the `-javaagent` option. Its entry point is `premain`, which is invoked by the JVM **before calling the application's `main`**. This window is critical: the agent has the opportunity to read configuration, prepare supporting components, and register a `ClassFileTransformer` before the business classes to be observed begin loading.

After this lesson, you should understand and be able to practice:

- Designing the sequence **read/validate configuration → initialize helpers → create and register transformer → return control to the application**.
- Distinguishing **helpers serving the agent** from **helpers that instrumented bytecode will call inside the application**; knowing why class loader/module visibility affects how helpers are packaged.
- Understanding when the `transform` callback runs, the scope that `premain` guarantees, and which classes may already have been loaded by the JVM beforehand.
- Creating and running an actual agent JAR on **JDK 17+**, proving that the transformer is registered before the business class is defined.
- Recognizing errors related to configuration, class loading loops, invisible helpers, registration order, bytecode quality, and startup impact.

The scope here is **an agent loaded at startup using `-javaagent`**. An agent loaded later via the Attach API goes through `agentmain` and must handle already-loaded classes separately; that is not the main initialization flow of this lesson.

## 2. Actual lifecycle: what does “before the application runs” mean?

With the example command:

~~~bash
java -javaagent:startup-agent.jar=target=demo.Work,verbose=true -cp app-classes demo.App
~~~

The JVM reads the agent JAR path and the options portion after the `=` sign, loads the class specified in the `Premain-Class` entry of the manifest, and then calls `premain`. Diagram:

~~~text
User launches JVM
    │
    ├── -javaagent:startup-agent.jar=target=demo.Work,verbose=true
    │
    ▼
JVM initializes runtime, loads agent JAR and required classes
    │
    ▼
StartupAgent.premain(agentArgs, Instrumentation)
    │
    ├── (1) parse and validate configuration
    ├── (2) prepare helpers, state, minimal services
    ├── (3) create ClassFileTransformer with finalized configuration
    ├── (4) instrumentation.addTransformer(transformer)
    └── (5) return from premain
    │
    ▼
JVM calls demo.App.main(...)
    │
    ├── application requests loading a new class
    └── transformer receives class bytes before the class is defined
         ├── does not match filter → return null
         └── matches → observe or return valid new byte[]
~~~

**Important guarantee:** `premain` is called before the application's `main` is called; when there are multiple `-javaagent` options, the `premain` methods are called in the order of the agents on the command line.

**Important limitation:** this **does not mean** every Java/JDK class is unloaded at the time `premain` runs. The JVM must initialize the runtime and load several classes so that the agent itself can operate. The agent can also accidentally load the target class too early while configuring or preparing helpers. Registering a transformer later does not turn back time to catch class definition events that have already occurred.

### 2.1. Three responsibilities, three types of data

| Component | Input received | Result after initialization | Principle |
|---|---|---|---|
| **Config** | `agentArgs` string, system properties, or environment variables per a clear contract | Validated configuration values, preferably immutable | Fail early on invalid options; do not share half-initialized state |
| **Helper** | Validated config, minimal dependencies | Logger/buffer/registry/runtime bridge ready | Know whether the helper will be called from the agent or from application bytecode |
| **Transformer** | Immutable config + ready helper state | Object registered with `Instrumentation` | Do not assume the callback runs only once or on a single thread |

A controllable way to separate responsibilities:

~~~text
premain
  |
  +-- AgentConfig.parse(...)           // create immutable configuration
  +-- AgentHelper.initialize(config)   // create supporting components first
  +-- new StartupTransformer(config)   // hold necessary state
  +-- inst.addTransformer(transformer) // callbacks can occur from here
  +-- return                            // application main comes after
~~~

If you register the transformer **before** configuration/helpers are ready, the callback may observe uninitialized state. If initialization actively loads the target class before registration, that class may bypass the transformer. Therefore, the order must be designed around **actual dependencies**, not just for neat method arrangement.

## 3. Agent configuration: specifying exactly what to target

`premain` typically has the signature:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

The agent JAR's manifest declares `Premain-Class`. The JVM passes **the entire options portion** after `-javaagent:<jarpath>=` as **a single `String`**, without automatically interpreting it into a key/value map. The agent must design the grammar and parse it.

Custom-defined example:

~~~text
-javaagent:startup-agent.jar=target=demo.Work,verbose=true
                               └──────────── agentArgs ──────────┘
~~~

With the illustrative syntax `key=value,key=value`, you should clarify:

- **Valid key names:** for example `target` and `verbose`; unknown keys must be detected.
- **Valid values:** `target` is a Java binary name like `demo.Work`, while `verbose` only accepts `true` or `false`.
- **Defaults:** if no options are passed, which default target is chosen; whether observation/logging is enabled or not.
- **Precedence:** if `agentArgs`, `-D...`, and environment variables are all present, which source wins? Do not silently mix configurations.
- **Errors:** does an invalid configuration cause the JVM to abort startup, or does the agent choose an ignore mode according to policy? This choice must be intentional.
- **Secrets:** do not print tokens, passwords, or URLs containing credentials to stdout; if sensitive configuration is needed, prefer an appropriate secret management mechanism.

**Parsing/validation should be completed before calling `addTransformer`**. Use a record or an immutable object so that callbacks see a consistent set of values. Do not store config field by field in `static` variables and update them while already receiving callbacks.

## 4. Helpers: two meanings to keep separate

### 4.1. Helpers running inside the agent

These are classes the agent calls directly to record events, buffer metrics, filter packages, collect traces, or assist in generating bytecode. For example, `AgentHelper.classSeen(...)` is **called by the transformer inside the callback**. If this helper is only used by the agent, it can be packaged alongside the agent entry point, without requiring the application to import the helper.

When designing helpers:

1. Limit operations in `premain` to genuinely necessary dependencies; avoid initializing a Spring context, calling application APIs, or opening unnecessary synchronous network connections.
2. Initialize state/queues/filters before registering callbacks; ensure visibility across threads using `final`, `volatile`, or appropriate synchronization.
3. When callbacks can occur concurrently, the helper must be thread-safe; logging every event to the console is a demo technique, not a high-throughput solution.
4. Do not let helper initialization inadvertently call `Class.forName` on the target class, because the class could be defined before the transformer is registered.
5. Place the agent's package outside the application namespace being instrumented and exclude the agent's package from the filter itself.

### 4.2. Helpers called from instrumented bytecode

Another scenario: the transformer **inserts calls** such as `TraceBridge.onEnter(...)` into the `demo.Work.run()` method. When this bytecode is executed by the JVM, the `demo.Work` class must **be able to find `TraceBridge` through its own class loading and module access mechanisms**.

Points to remember:

- The agent JAR is typically added to the **system class loader search** for startup agents; that does not guarantee every **child-first/custom class loader** of the application can see the helper.
- For classes loaded across multiple loaders, it may be necessary to package the helper into a **separate, very small** JAR and add it to the bootstrap search using `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` or the agent JAR's `Boot-Class-Path` mechanism when appropriate.
- A helper placed on the bootstrap classpath should only depend on types that the bootstrap class loader can define. Do not arbitrarily attach the entire agent/framework or libraries with many dependencies to bootstrap; class name collisions and linkage errors are very hard to debug.
- The Java module system also has requirements regarding **readability, exports/opens**. Being able to load a class does not automatically mean having permission to access every member; only adjust modules using valid mechanisms when truly necessary.
- Adding a JAR to the search **does not** retroactively fix classes that have already been loaded and does not guarantee resolving classes that previously failed to load.

**Distinguish by asking:** will the helper be called inside the `transform` method or called by **an application method after bytecode modification**? Only the second case requires fully resolving visibility from the target class's loader/module to the helper.

## 5. Transformer: register early, filter narrowly, return bytes per contract

`ClassFileTransformer` is an interface in `java.lang.instrument`. On Java 9+, there is an overload that also receives `Module`:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

When the JVM prepares to define a class, it passes to the callback the internal name (for example `demo/Work`), class loader, module, protection domain, and **the initial class-file bytes for this transformation pass**. On initial load, `classBeingRedefined` is usually `null`.

Foundational rules:

- `className` can be `null`; write filters to be `null`-tolerant.
- Filter using **the internal name with `/`**, do not use `demo.Work` directly when comparing against `className`.
- `return null` means **do not modify the class bytes in this callback**; do not return a copy just to indicate “processed”.
- If actually modifying, create a valid **new byte array**. **Do not mutate `classfileBuffer` directly** as passed in by the JVM.
- Registering with `inst.addTransformer(transformer)` is sufficient for subsequent class definitions; `addTransformer(transformer, true)` should only be used if retransformation is needed and the JVM supports that capability.
- The callback is a sensitive place: avoid reloading target classes, recursive transformation, slow I/O, complex locks, and unbounded processing.
- When there are multiple transformers, the result of an earlier transformer can become the input of a later one. Within a corresponding group, registration order matters; native transformers and retransform-capable transformers also have their own ordering rules.

For **classes already loaded before the transformer is registered**, registration does not automatically re-run the callback. Only consider `retransformClasses`/`redefineClasses` when needed, with the proper capability and within JVM limits; that is a separate task from startup load-time instrumentation.

### “Registering a transformer” vs. “modifying bytecode”

In the runnable example below, the transformer only observes `demo.Work` and returns `null`. We intentionally use this approach to demonstrate **initialization order** without needing a bytecode manipulation library. The agent operates successfully, yet the program's behavior is not altered.

To insert actual timing/logging into a method body on **JDK 17**, you need a compatible bytecode processing tool such as ASM or Byte Buddy and must verify the classfile verifier, stack map frames, exception paths, and helper visibility. **The standard Class-File API `java.lang.classfile` is available starting in JDK 24**, so code using that API cannot run on a JDK 17 runtime. The `premain`/`Instrumentation`/`addTransformer` mechanism remains the same; the valid bytecode generation part changes depending on the chosen tool.

## 6. Hands-on Java 17+: configuration → helper → transformer → application

This exercise uses **only the JDK**, requiring no Gradle, Maven, or external libraries. The target `demo.Work` is only invoked via reflection **after `main` starts**, making it clear when the loader defines the class.

### 6.1. File structure

~~~text
startup-agent-demo/
├── MANIFEST.MF
├── src-agent/
│   └── example/agent/
│       ├── AgentConfig.java
│       ├── AgentHelper.java
│       ├── StartupTransformer.java
│       └── StartupAgent.java
└── src-app/
    └── demo/
        ├── App.java
        └── Work.java
~~~

**File `src-agent/example/agent/AgentConfig.java`** — immutable record, parses two options. Class name format validation in the example uses simple ASCII Java naming rules:

~~~java
package example.agent;

import java.util.HashSet;
import java.util.Set;

record AgentConfig(String targetInternalName, boolean verbose) {

    static AgentConfig parse(String raw) {
        String target = "demo.Work";
        boolean verbose = false;
        Set<String> seen = new HashSet<>();

        if (raw != null && !raw.isBlank()) {
            for (String option : raw.split(",", -1)) {
                int equal = option.indexOf('=');
                if (equal <= 0 || equal == option.length() - 1) {
                    throw new IllegalArgumentException("Bad option: " + option);
                }

                String name = option.substring(0, equal).trim();
                String value = option.substring(equal + 1).trim();

                if (!seen.add(name)) {
                    throw new IllegalArgumentException("Duplicate option: " + name);
                }

                switch (name) {
                    case "target" -> {
                        if (!value.matches(
                                "[A-Za-z_$][A-Za-z0-9_$]*(\\.[A-Za-z_$][A-Za-z0-9_$]*)*")) {
                            throw new IllegalArgumentException("Bad target: " + value);
                        }
                        target = value;
                    }
                    case "verbose" -> {
                        if (!"true".equals(value) && !"false".equals(value)) {
                            throw new IllegalArgumentException("Bad verbose: " + value);
                        }
                        verbose = Boolean.parseBoolean(value);
                    }
                    default -> throw new IllegalArgumentException(
                            "Unknown option: " + name);
                }
            }
        }

        return new AgentConfig(target.replace('.', '/'), verbose);
    }
}
~~~

The record holds the final config state. `targetInternalName` uses `/` because the name received by the transformer is in internal name format, such as `demo/Work`. The example does not handle every valid Unicode character in Java names; the demo scope focuses on standard ASCII class names.

**File `src-agent/example/agent/AgentHelper.java`** — helper serving only the agent. The volatile `ready` variable ensures the thread invoking the callback sees the previously assigned values:

~~~java
package example.agent;

final class AgentHelper {
    private static volatile boolean ready;
    private static boolean verbose;

    private AgentHelper() {}

    static synchronized void initialize(AgentConfig config) {
        if (ready) {
            throw new IllegalStateException("Helper already initialized");
        }
        verbose = config.verbose();
        ready = true;
        System.out.println("[agent] helper ready");
    }

    static void classSeen(String internalName) {
        if (!ready) {
            throw new IllegalStateException("Helper not ready");
        }
        if (verbose) {
            System.out.println(
                    "[agent] observed " + internalName.replace('/', '.'));
        }
    }
}
~~~

This is a helper **called by the transformer**, not a helper injected into the bytecode of `demo.Work`. The `println` statement is only used for teaching how to observe the order; in practice, avoid synchronous logging on every class load event.

**File `src-agent/example/agent/StartupTransformer.java`** — exact single-class filter:

~~~java
package example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

final class StartupTransformer implements ClassFileTransformer {
    private final AgentConfig config;

    StartupTransformer(AgentConfig config) {
        this.config = config;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!config.targetInternalName().equals(className)) {
            return null;
        }

        AgentHelper.classSeen(className);
        return null; // Observe the class; keep bytecode unchanged.
    }
}
~~~

Because `config.targetInternalName()` is non-`null`, comparing in this direction is safe if `className` is `null`. The `config` object is an immutable record and the transformer's field is `final`, suitable for concurrent reads by callbacks.

**File `src-agent/example/agent/StartupAgent.java`** — entry point executing the exact sequence:

~~~java
package example.agent;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    private StartupAgent() {}

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[agent] premain begin");

        AgentConfig config = AgentConfig.parse(agentArgs);
        AgentHelper.initialize(config);

        StartupTransformer transformer = new StartupTransformer(config);
        inst.addTransformer(transformer); // Default canRetransform = false.

        System.out.println("[agent] transformer registered for "
                + config.targetInternalName().replace('/', '.'));
    }
}
~~~

This is where the dependencies meet:

1. No agent-specific callbacks occur before `addTransformer`.
2. `AgentConfig.parse` creates a valid snapshot or reports an error.
3. `AgentHelper.initialize` prepares state and prints a confirmation line.
4. `new StartupTransformer(config)` receives the finalized state.
5. `inst.addTransformer(transformer)` registers the callback before `premain` returns, after which the application's `main` is called.

**File `src-app/demo/Work.java`** — target business class:

~~~java
package demo;

public final class Work implements Runnable {
    @Override
    public void run() {
        System.out.println("[app] Work.run");
    }
}
~~~

**File `src-app/demo/App.java`** — loads the class after `main` has printed the first line:

~~~java
package demo;

public final class App {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] main");
        Runnable work = (Runnable) Class.forName("demo.Work")
                .getDeclaredConstructor()
                .newInstance();
        work.run();
    }
}
~~~

Using `Class.forName("demo.Work")` here provides clear control over the point where loading `Work` is requested. The application has no direct compile-time reference to the `Work` type in `App`; the example is run without another agent or tool proactively preloading this class.

**File `MANIFEST.MF`** — must have `Premain-Class` in the main section. There must be a trailing newline after the declaration line to terminate the manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.StartupAgent

~~~

`Agent-Class` is not needed because the example does not use dynamic attach. Declaring `Can-Retransform-Classes` is not needed because it only observes classes on initial load. An agent JAR can declare other attributes for appropriate purposes, but unused capabilities should not be enabled just because they are available.

### 6.2. Compiling and packaging

Run the commands from the `startup-agent-demo/` directory. Prepare two output directories.

**Bash:**

~~~bash
mkdir -p out/agent out/app
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
~~~

The following `javac`/`jar`/`java` commands work on Bash or PowerShell, assuming JDK 17+ is in `PATH`:

~~~bash
javac --release 17 -d out/agent src-agent/example/agent/AgentConfig.java src-agent/example/agent/AgentHelper.java src-agent/example/agent/StartupTransformer.java src-agent/example/agent/StartupAgent.java
javac --release 17 -d out/app src-app/demo/App.java src-app/demo/Work.java
jar cfm out/startup-agent.jar MANIFEST.MF -C out/agent .
~~~

Verify with `jar tf out/startup-agent.jar`: it should contain `example/agent/StartupAgent.class` and the corresponding helper/config/transformer classes. Inspect the packaged manifest with `jar xf` in a separate inspection directory if needed; `Premain-Class: example.agent.StartupAgent` must appear in `META-INF/MANIFEST.MF`.

Do not package all application classes into the agent JAR in this example. The agent JAR contains the classes serving the agent; the application resides in `out/app` and the JVM is pointed to it via `-cp out/app`.

### 6.3. Running without an agent

~~~bash
java -cp out/app demo.App
~~~

Result:

~~~text
[app] main
[app] Work.run
~~~

The application runs normally on its own. There are no `[agent]` lines because no JVM option loaded an agent.

### 6.4. Running with the startup agent

~~~bash
java -javaagent:out/startup-agent.jar=target=demo.Work,verbose=true -cp out/app demo.App
~~~

Expected result of this exact example:

~~~text
[agent] premain begin
[agent] helper ready
[agent] transformer registered for demo.Work
[app] main
[agent] observed demo.Work
[app] Work.run
~~~

Line-by-line explanation:

- The JVM calls `premain`, so the first lines come from the agent.
- The helper finishes initializing before the transformer is registered.
- The agent registers successfully, then `premain` returns; only then does `App.main` print `[app] main`.
- When `Class.forName` requests defining `demo.Work`, the transformer matches the name `demo/Work` and the helper prints `[agent] observed demo.Work`.
- `transform` returns `null`, so `Work.run` still runs exactly as the original and prints `[app] Work.run`.

**Note on output:** the log lines are only expected in the order above for this simple example, with no other agent actively loading `demo.Work`, and a runtime supporting `-javaagent` per the specification. In a real application, do not infer that every JVM class load will occur in the same order.

Try turning off verbose:

~~~bash
java -javaagent:out/startup-agent.jar=target=demo.Work,verbose=false -cp out/app demo.App
~~~

Result:

~~~text
[agent] premain begin
[agent] helper ready
[agent] transformer registered for demo.Work
[app] main
[app] Work.run
~~~

The transformer **is still registered** and is still called for `demo.Work`; only the observation logging was turned off in the helper. Do not treat “no log seen” as proof that the transformer did not run.

Try passing `verbose=maybe`:

~~~bash
java -javaagent:out/startup-agent.jar=target=demo.Work,verbose=maybe -cp out/app demo.App
~~~

`AgentConfig.parse` throws `IllegalArgumentException` before any transformer exists. This is the demo's **intentional fail-fast policy**: the JVM will abort when `premain` throws an unhandled exception; the exact JVM error message may vary across versions, with no normal application stdout.

## 7. Why not reverse the initialization order?

### Mistake A: registering the transformer before the helper is ready

~~~text
premain
  ├── addTransformer(transformer)
  ├── initialize helper
  └── return
~~~

A callback can occur when the helper is not yet ready, especially if class definition activity happens immediately after registration. If the callback needs configuration or a registry that does not exist yet, it may record wrong data, throw `NullPointerException`, or drop events. Recommended sequence:

~~~text
parse config → initialize essential dependencies → create transformer → addTransformer
~~~

If there is an extremely heavy helper part that must not block startup, separate **the minimal state for safe callbacks** from **services that can initialize asynchronously**. The transformer needs a clear policy when the service is not yet ready (drop events, bounded buffering, or apply a safe mode), rather than assuming the background thread will start in time.

### Mistake B: loading the class you want to instrument inside `premain` itself

For example, an agent instruments `demo.Work` yet calls:

~~~java
// Counterexample: do not use when you need to catch the first definition of demo.Work.
Class.forName("demo.Work");
instrumentation.addTransformer(transformer);
~~~

If `Class.forName` finds and defines `demo.Work` before `addTransformer` is called, the transformer arrives too late for **the first load** of that class. Avoid initializing the application or scanning/reflecting every class before registration. If you need to process already-loaded classes, that is a separate retransformation problem.

### Mistake C: the helper in bytecode is not within the loader's scope

~~~text
Agent system loader       ───> agent internals + AgentHelper
Custom app loader         ───> demo.Work
                                  |
                                  └── new bytecode calls AgentHelper ?
~~~

Even if the transformer builds the class bytes successfully, when the method runs, the JVM still has to resolve the helper reference from `demo.Work`'s context. The loader may not see the helper; typical errors are `NoClassDefFoundError`, `ClassNotFoundException` on dependency loading paths, or `IllegalAccessError` when encountering access restrictions.

The solution lies in class loading architecture: avoid referencing helpers when unnecessary, or arrange a **minimal, stable helper API** that target loaders/modules can access. With bootstrap append, use a separate helper JAR and check the impact of colliding package/class names. In the runnable example above, `Work` **does not call the helper**, so this visibility issue did not arise.

### Mistake D: using the transformer to initialize the entire application

The transformer must process class bytes concisely. Do not start a framework context, read an entire database, initialize a complex HTTP client, or synchronously wait for the application to be “ready” from inside the callback. The callback may run at a time when the application ecosystem **does not yet have a valid operational state** and on the very thread defining the class; blocking/reentrant operations cause deadlocks or class loading cycles.

## 8. Expanding from “observing” to actual bytecode transformation

The previous example only used `return null`. With the goal of instrumenting `Work.run`, a pipeline with proper separation of responsibilities typically looks like:

~~~text
StartupAgent.premain
   ├── parse config: class/method filter, mode, sampling
   ├── prepare helper called from bytecode (if needed)
   ├── prepare ASM/Byte Buddy/Class-File API engine appropriate for JDK
   └── addTransformer
          └── when JVM defines a class:
                1. filter by className + loader + module
                2. if no match: return null
                3. parse classfileBuffer
                4. insert code into selected methods
                5. recompute frames/max stack as needed
                6. return new byte[], valid for the JVM verifier
                7. JVM defines the class from the transformer chain's result
~~~

**Division of responsibilities in design:**

| Concern | Where to place it | Why |
|---|---|---|
| Deciding which class/method is selected | Config + transformer filter | Easy to adjust and limits scope |
| Re-encoding methods and generating a new classfile | Bytecode processor | The transformer is only the integration point with the JVM |
| Pushing events quickly to a queue/buffer | Agent helper / helper in target (if bytecode calls directly) | Avoids network/console I/O on the hot path |
| Registering the class definition callback | `Instrumentation.addTransformer` in `premain` | Captures class definitions after the registration point |
| Observing already-loaded classes | Separate retransform/redefine capability and operations | `addTransformer` is not retroactive |

Any real transformation must keep bytecode valid for the classfile version, including the exception table and stack map frames. Classes with synthetic/bridge methods, special method bodies, custom class loaders, and module boundaries must be tested before going to production. Class names can collide across loaders; using a plain name string alone is sometimes insufficient to identify **the exact type** to modify.

## 9. Reliable operational rules

### 9.1. Define an error policy for each stage

| Stage | Example error | Reasonable action |
|---|---|---|
| Parse config | Unknown key, wrong data type | Fail-fast before registration (mandatory agent); or disable agent per operational policy |
| Prepare helper | Cannot create buffer/logging backend | Do not let callbacks use half-initialized state; decide fail-open/fail-fast transparently |
| Register transformer | JVM lacks capability if retransform is requested | Check `isRetransformClassesSupported()` if truly needed; for basic load-time use the default overload |
| Transform class | Malformed bytes or tool encounters unfamiliar classfile | Report and skip the class if safe; do not attempt to apply corrupted bytes |
| Runtime helper call | Helper not visible, wrong module permissions | Test loader/module before running on a real application |

Per the specification, an uncaught exception in `ClassFileTransformer.transform` is usually handled by the JVM equivalently to the callback returning `null`, and other transformers may still be called. This **does not mean** a transformer error is harmless: a partial transformation can cause incorrect behavior, and valid class bytes with wrong logic can still pass the verifier. Choose the failure mode based on how essential the instrumentation is, log with rate limits, and preserve evidence for diagnostics.

### 9.2. Avoid unpredictable impacts on startup

- Read and validate configuration once; do not call external systems just to decide a simple flag.
- Do not instrument the agent's own package, bytecode engine, logging runtime, or core JDK without a clear reason and thorough testing.
- Do not initialize application singletons, beans, transactions, connection pools, or business services directly inside `premain`.
- Class load callbacks can run concurrently; use immutable state, thread-safe APIs, and avoid unsynchronized mutable global state.
- Measure **startup time with the agent** and **without the agent**. Scanning every class or printing logs in every callback can slow startup significantly.
- Use thresholds/bounded queues when collecting events; do not let target classes depend on the availability of an external collector.
- The same JVM can receive multiple startup agents; design hook idempotency and handle transformer conflicts if any.
- Ensure the agent and bytecode engine are compatible with the actual JDK version (classfile major version, module behavior, instrumentation capabilities); `--release 17` only constrains **the compiled code**, it does not prove all external libraries are also compatible.

### 9.3. When is it necessary to add `Boot-Class-Path` or `appendToBootstrapClassLoaderSearch`?

**Not needed** in the demo because `AgentHelper` is only called from the agent itself. It may be needed when bytecode is added to a class defined by the bootstrap/custom loader and **the bytecode will call the helper**.

Before choosing that approach, determine at least:

1. Which loader defines the target class, and where can that loader see the helper?
2. Does the helper depend on any class not visible to the bootstrap loader?
3. Will adding the JAR to the bootstrap search cause package or class name collisions?
4. Does the target class's Java module have permission to read/access the helper API?
5. If instrumentation is disabled or fails, can the application continue running?

The `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` API takes a `JarFile` containing **only the appropriate supporting classes**, and must be called before the target class needs to resolve the helper. Do not copy the entire agent JAR onto bootstrap out of habit.

## 10. Checklist for self-testing

| Check | Expected result |
|---|---|
| Agent JAR has `META-INF/MANIFEST.MF` declaring `Premain-Class` accurately | JVM finds `StartupAgent.premain` |
| Run without `-javaagent` | Only application output |
| Run with `-javaagent` | `premain` and helper logs appear before `[app] main` |
| `target=demo.Work,verbose=true` | Exactly one observation log for `demo.Work` in the demo scenario |
| `verbose=false` | No observation log, application still works |
| `verbose=maybe` | Invalid config is detected before the transformer is registered |
| Try `target=demo.Other` (class not loaded in demo) | No `observed demo.Work` log |
| No bytecode rewrite | `[app] Work.run` output remains identical to original app |
| Review target production packages and loaders | Does not self-instrument agent/helper and does not depend on invisible helpers |
| Measure startup overhead and fail-open/fail-fast capability | Policy matches application requirements |

**Distinguishing evidence:** the `[agent] transformer registered` log proves the registration call completed; the `[agent] observed demo.Work` log proves the callback **ran for the target class**; whereas to prove **bytecode was actually modified**, you must use a transformer that returns new bytes and test behavior or inspect the corresponding classfile. Do not use one signal to assert another.

## 11. Review questions and answers

**Question 1.** Why must config be parsed before `addTransformer`?

> Because callbacks can run after the transformer is registered, from multiple threads. A validated immutable config record ensures callbacks see a consistent state; invalid config is caught immediately rather than letting events pass through half-configured state.

**Question 2.** If `premain` runs before `main`, does that guarantee the transformer receives all classes in the JVM?

> No. The JVM has already initialized and loaded some classes for the runtime/agent before `premain`; the agent itself can also load additional classes before registration. The transformer only monitors class definitions occurring after registration and appropriate redefine/retransform operations.

**Question 3.** Does a helper called by the transformer need to be placed on the bootstrap classpath?

> Not by default. If the helper is only called by agent code, the agent can package it alongside its other classes. The need to add it to bootstrap typically arises when **bytecode injected into classes of another loader** must call the helper.

**Question 4.** Why is the demo transformer still useful even though it always `return null`?

> It proves the correct entry point, parsing, helper initialization order, registration, and class-definition callback, while keeping class bytes unchanged. Actual bytecode instrumentation can be swapped in after the startup flow has been verified.

**Question 5.** A `demo.Work` class was loaded by the agent itself before `addTransformer`. Can this mistake be fixed simply by calling `addTransformer` again?

> No. Additional registration does not replay a class definition event that has already finished. If an already-loaded class must be changed, retransform/redefine capabilities and allowed structural limits must be considered; it is still best to avoid loading the target too early.

**Question 6.** Why shouldn't you log every class load or make synchronous HTTP calls from `transform`?

> The callback can lie on the application's class loading path, running very frequently and concurrently. I/O/locks or new dependencies can increase startup latency, cause recursion, contention, or deadlock; use narrow filters and helpers with bounded buffering.

## 12. Official documentation

- Java SE 17, `java.lang.instrument`: manifest, `premain`, `-javaagent`, and startup agent ordering: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- `Instrumentation`, `addTransformer`, and bootstrap/system class loader search: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- `ClassFileTransformer`, callbacks, ordering, valid bytecode, and `return null`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `java.lang.Module` and module access: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JEP 484 (Standard Class-File API starting in JDK 24; use when runtime is appropriate): https://openjdk.org/jeps/484
