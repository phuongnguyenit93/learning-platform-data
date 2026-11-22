# Launcher-Agent-Class in an Executable JAR and the Role of `agentmain`

## 1. Goal and Context

The Java Instrumentation API (`java.lang.instrument`) allows a **Java agent** to observe, transform bytecode when classes are loaded, or work with certain already-loaded classes through the `Instrumentation` capabilities supported by the JVM. How an agent is **launched** determines the entry method name (`premain` or `agentmain`), when that method runs, and how the JAR is packaged.

In an **executable JAR** run with `java -jar application.jar`, the manifest can declare:

```text
Main-Class: com.example.Main
Launcher-Agent-Class: com.example.StartupAgent
```

`Main-Class` tells the Java launcher the entry point of the **application**. `Launcher-Agent-Class` specifies **the agent class packaged inside the executable JAR itself**; the JVM will invoke the **`agentmain` method of the agent class before calling the application's `main`**.

Thing to remember: even though this agent runs **right at startup**, its entry point is **`agentmain`**, not `premain`. The name `agentmain` is also used for agents attached to a running JVM, but these are **two different launch paths**.

This feature has been specified since Java 9; the hands-on example below uses Java 17+.

## 2. How the JVM Reads `Launcher-Agent-Class`

When using the standard executable JAR mechanism, the flow can be visualized as follows:

```text
java -jar application.jar [application arguments]
         |
         v
Java launcher reads META-INF/MANIFEST.MF
         |
         +-- Main-Class: application main class name
         |
         +-- Launcher-Agent-Class: agent class name bundled with the JAR
                   |
                   v
             JVM loads the agent class
                   |
                   v
             agentmain("", Instrumentation)
                   |
             sets up required transformer / state / hook
                   |
             agentmain returns
                   |
                   v
             Main.main(String[] args)
```

This is a logical flow diagram, not a claim that every system class is only loaded by the JVM after `agentmain`. Some JVM and library classes may already have been loaded during startup. The important guarantee is that **`agentmain` is called before calling the application's `main` method**.

Basic requirements:

1. Run an **executable JAR via the `java -jar` mechanism**; the JAR contains a main manifest with a valid `Main-Class`.
2. In the same **main section** of `META-INF/MANIFEST.MF`, `Launcher-Agent-Class` points to the **fully qualified binary name** of the agent class, for example `com.example.StartupAgent`; do not include the `.class` extension, and do not write a path like `com/example/StartupAgent.class`.
3. The agent class and any dependencies needed at startup must be findable by the appropriate class loader. For a standard JAR example, place the class at the corresponding path inside the JAR.
4. The agent class provides a valid `public static void agentmain(...)` method.
5. `agentmain` initializes the necessary components and then **returns** so the JVM can continue running the application.

If the manifest does not have `Launcher-Agent-Class`, the JVM will not automatically launch this kind of agent. If the manifest only has `Launcher-Agent-Class` and lacks `Main-Class`, the JAR does not qualify to launch as a standard executable JAR.

## 3. Contract of `agentmain` in Launcher Mode

The JVM looks for this signature first:

```java
public static void agentmain(String agentArgs,
                             java.lang.instrument.Instrumentation inst)
```

If the agent class **does not define the two-parameter signature**, the JVM tries the fallback method:

```java
public static void agentmain(String agentArgs)
```

If both overloads exist, the JVM prefers the **two-parameter** version. The method must be `public static` and return `void`; do not substitute `main`, `premain`, an instance method, or the wrong parameter name/type order.

### Value of `agentArgs`

**For `Launcher-Agent-Class`, `agentArgs` is always the empty string `""`.** This is a rule of the launcher mechanism, not a value taken from the arguments following the JAR name.

Example:

```bash
java -jar application.jar user-1 debug
```

- The application's `main(String[] args)` receives two elements: `"user-1"` and `"debug"`.
- The launcher agent's `agentmain(String agentArgs, ...)` receives `""`, **not** `"user-1 debug"`.
- There is no official syntax like `Launcher-Agent-Class=trace` to pass options via `-jar` arguments. If you need to configure an embedded agent, you can use system properties, environment variables, or custom configuration defined by the application/agent; make sure to define the reading mechanism and initialization order clearly.

### Role of `Instrumentation`

The `Instrumentation` object is an API provided by the JVM, commonly used to:

- Register or unregister a `ClassFileTransformer` with `addTransformer`/`removeTransformer`, to process classes loaded after the transformer becomes active.
- Check capabilities with `isRetransformClassesSupported()`, `isRedefineClassesSupported()`; if supported and conditions are met, call `retransformClasses`/`redefineClasses`.
- Inspect loaded class information (`getAllLoadedClasses`), check whether a class is modifiable (`isModifiableClass`), and support module/class-loader search via the corresponding APIs.

Not every VM supports every capability. Manifest capabilities such as `Can-Retransform-Classes: true` and `Can-Redefine-Classes: true` may be required, but they **do not guarantee** that the feature is actually supported by the VM; always check the API before using it.

With the **one-parameter** signature (`agentmain(String)`), the agent does not directly receive the `Instrumentation` object; that approach is suitable when only performing other initialization steps without needing instrumentation APIs.

### Initialization Errors Can Halt the Application Completely

If the agent class cannot be loaded, lacks a valid `agentmain` method, or `agentmain` throws an uncaught exception/error, **the JVM aborts before calling `main`**. Therefore, code in `agentmain` should perform essential initialization, handle errors intentionally, and avoid depending on state that is only set up in `main`.

## 4. Runnable Example on Java 17+: Embedded Agent Running Before `main`

This example uses only Java SE, without Maven/Gradle or external libraries. Create **three files** in the same directory:

```text
demo/
├── LauncherAgent.java
├── DemoApp.java
└── manifest.mf
```

The classes are in the default package to focus on the manifest; real-world projects should use explicit packages.

### File 1: `LauncherAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class LauncherAgent {
    private LauncherAgent() {
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        System.out.println("[agent] argsEmpty=" + agentArgs.isEmpty());
        System.out.println("[agent] hasInstrumentation=" + (inst != null));

        // Prove that agent initialization ran before DemoApp.main.
        System.setProperty("demo.launcher.agent", "ready");
    }
}
```

Explanation:

- The `agentmain` method has the exact signature `public static void ... (String, Instrumentation)`.
- `agentArgs.isEmpty()` will be `true` under the `Launcher-Agent-Class` mechanism.
- `inst` is the object provided by the JVM; the example does not modify bytecode yet, only verifies its presence.
- The system property is a way to **demonstrate execution order**. Do not treat this as a mandatory state-passing protocol for agents.

### File 2: `DemoApp.java`

```java
public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) {
        String agentState =
                System.getProperty("demo.launcher.agent", "missing");
        System.out.println("[main] agentState=" + agentState);
        System.out.println("[main] args=" + String.join(",", args));
    }
}
```

The application reads the property set by the agent and then prints the arguments passed by the user after `-jar`.

### File 3: `manifest.mf`

```text
Manifest-Version: 1.0
Main-Class: DemoApp
Launcher-Agent-Class: LauncherAgent

```

The manifest attributes are in the **main section** of the JAR; the example uses class names without a package. If a class has a package, the value must be the fully qualified name such as `example.agent.LauncherAgent`.

**Manifest formatting note:** each attribute is on one line `Name: value`, with a space after the colon; the file should end with a **trailing blank line**. Do not add `.class` syntax or quotes to the `Launcher-Agent-Class` value. The `jar --manifest` command will place the contents into `META-INF/MANIFEST.MF`.

### Compile, Package, and Run

Open a terminal in the directory containing the three files. Use JDK 17 or later with `--release 17` support:

```bash
javac --release 17 LauncherAgent.java DemoApp.java
jar --create --file launcher-demo.jar --manifest manifest.mf LauncherAgent.class DemoApp.class
java -jar launcher-demo.jar alpha beta
```

**Exact stdout** from `java -jar launcher-demo.jar alpha beta` when running the example on a JVM that supports the launcher agent mechanism:

```text
[agent] argsEmpty=true
[agent] hasInstrumentation=true
[main] agentState=ready
[main] args=alpha,beta
```

The two `[agent]` lines appear **before** the two `[main]` lines. The user passed `alpha beta` to the application, but the agent's `agentArgs` remains empty. `javac` and `jar` normally print nothing to stdout when they succeed.

To inspect the entries in the JAR:

```bash
jar --list --file launcher-demo.jar
```

You should see the corresponding entries `META-INF/MANIFEST.MF`, `LauncherAgent.class`, and `DemoApp.class` (in addition to any `META-INF/` entries).

### Control Experiment: Launching as a Regular Class

Run in **a new Java process**:

```bash
java -cp launcher-demo.jar DemoApp alpha beta
```

Stdout:

```text
[main] agentState=missing
[main] args=alpha,beta
```

Here the Java launcher uses `-cp` and specifies `DemoApp` directly, rather than using the `-jar` executable JAR mechanism. Therefore, merely having `Launcher-Agent-Class` metadata in the JAR **does not automatically activate the agent**. A new JVM also does not inherit Java system properties that were set in a previously run JVM.

## 5. From Simple Initialization to Real Instrumentation

In the previous example, `agentmain` only set a property. In real systems, `agentmain` is typically where configuration is created/accessed, transformers are registered, and only then is the application allowed to proceed. For example, this **illustrative snippet placed inside the `agentmain(String, Instrumentation)` method**, not a standalone Java program:

```java
inst.addTransformer((loader, className, classBeingRedefined,
                     protectionDomain, classfileBuffer) -> {
    if ("com/example/BusinessService".equals(className)) {
        System.out.println("[agent] loading " + className);
    }

    return null; // Observe only, do not replace bytecode.
});
```

Meaning:

- `ClassFileTransformer` receives the class name in internal form with `/` separators, for example `com/example/BusinessService`; the `className` parameter can be `null` in certain situations, so compare using a constant as shown above.
- `return null` means the transformer **does not modify** the bytecode. To actually transform it, you must return a valid byte array that preserves JVM constraints; this usually requires a library like ASM or Byte Buddy.
- The transformer receives events for classes defined **after registration**. Do not assume that all previously loaded classes will pass through the transformer.
- For already-loaded classes, `retransformClasses`/`redefineClasses` have different conditions and constraints; you must check VM support, permissions, and class modifiability before calling them.

Component diagram:

```text
LauncherAgent.agentmain("", inst)
            |
            +--> prepare configuration/observation
            |
            +--> inst.addTransformer(transformer)
                            |
                            v
                  JVM defines new class
                            |
                            v
                  transformer receives bytes
                            |
                  +---------+---------+
                  |                   |
             returns null       returns new byte[]
             keeps bytecode     uses modified bytecode
```

**Do not** perform overly heavy synchronous work in `agentmain`. If startup requires a transformer to be in place before the application runs, perform the essential registration and return. Background work needs explicit lifecycle, thread, error, and resource management; minimal observation/transformation should be preferred to reduce the risk of impacting startup.

## 6. Comparing the Three Java Agent Launch Mechanisms

| Mechanism | Activation | Manifest used to specify agent | Method invoked | Timing |
| --- | --- | --- | --- | --- |
| Agent bundled with executable JAR | `java -jar app.jar` | `Launcher-Agent-Class` in executable JAR | **`agentmain`** | Before `Main-Class.main` |
| Separate agent JAR on command line | `java -javaagent:agent.jar[=options] ...` | `Premain-Class` in agent JAR | **`premain`** | Before application `main` |
| Agent loaded after JVM is running | VM-supported attach/loadAgent mechanism | `Agent-Class` in agent JAR | **`agentmain`** | When agent is dynamically loaded, usually after `main` |

### Why Does the Same Name `agentmain` Have Different Error Behavior?

**Launcher agent:** `agentmain` is called **during the JVM's executable JAR startup phase**. If it fails to initialize, the JVM **aborts** and never reaches the application's `main`.

**Dynamically attached agent:** `agentmain` is also called, but the JVM is **already running**. According to the `java.lang.instrument` contract, initialization errors/uncaught exceptions from an attached agent **do not abort the application JVM via the same launcher mechanism** (they may be logged); loading the agent is also subject to each JVM's attach policy and support.

**Command-line agent:** `-javaagent` requires the `Premain-Class` manifest attribute, calls `premain`, and also halts JVM startup if a required agent cannot run. Having only `Launcher-Agent-Class` **cannot replace** `Premain-Class` when using `-javaagent`.

**Relationship between attributes:**

- `Main-Class`: application entry point. Not synonymous with an agent.
- `Launcher-Agent-Class`: agent embedded in the JAR that the launcher is running, calling `agentmain` before `main`.
- `Premain-Class`: agent supplied via `-javaagent`, calling `premain`.
- `Agent-Class`: agent JAR loaded into an already-started JVM, calling `agentmain`.
- `Can-Redefine-Classes`, `Can-Retransform-Classes`, and `Can-Set-Native-Method-Prefix`: request additional capabilities; they **do not** launch an agent by themselves.

If a single JAR declares multiple entry points and the application uses multiple launch paths, **the agent may be initialized multiple times**. Avoid assuming init only runs once in all situations: idempotency or explicit state control is needed.

## 7. When Should You Use `Launcher-Agent-Class`?

Suitable when:

1. You **control the executable JAR** and want to distribute the application and agent together in a single artifact.
2. You want the agent to set up tracing/metric hooks/instrumentation before `main` without deployers having to add the `-javaagent` flag.
3. You do not need to pass agent options via the `-javaagent:...=...` syntax; you can use another configuration mechanism.
4. You accept that **an embedded agent failure can block the application from starting**.

Not every file with a `.jar` extension is an executable JAR. If users actually run a class with `java -cp ... SomeMain`, the launcher will not automatically invoke `Launcher-Agent-Class`. If you want to attach a standalone agent to multiple applications without modifying their artifacts, `-javaagent` is usually more appropriate.

### Be Careful with JARs Having Nested Dependencies / Custom Launchers

A **standard** JAR places `com/example/StartupAgent.class` at the corresponding path in the archive. However, some packaging tools, such as **Spring Boot executable JARs**, place application classes in `BOOT-INF/classes/` and libraries in `BOOT-INF/lib/`; `Main-Class` may be `org.springframework.boot.loader.launch.JarLauncher`, while the application class is in `Start-Class`.

When a launcher agent runs **before** `main`, you must not assume that classes only present in `BOOT-INF/classes/` or nested JARs inside will be found by the **system class loader**. Spring Boot's nested JAR loading mechanism is set up by Spring Boot's launcher at a different time. To use an embedded agent in this type of packaging, you must **verify the actual class paths, class loaders, and dependencies**; you may need to arrange for the agent classes to be visible to the JVM from the very beginning or distribute a standalone agent JAR using `-javaagent`.

Inspect the class names, paths, and manifest of the **packaged artifact**, rather than only looking at `build.gradle` or source code.

## 8. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| `no main manifest attribute` on `java -jar` | JAR lacks a valid `Main-Class` | Check the main manifest; package the executable JAR properly |
| `main` runs but agent is not seen | Missing `Launcher-Agent-Class`, or running with `java -cp` | Check the manifest of the exact artifact and the actual launch command |
| JVM stops before `main` due to failure to load agent | `Launcher-Agent-Class` value has wrong name, or class/dependency is not where the loader can see it | Use the fully qualified binary name; check class path and JAR layout |
| JVM stops due to missing matching method | `agentmain` is instance/private, wrong parameters, or wrong return type | Define `public static void agentmain(String, Instrumentation)` or the one-parameter version |
| JVM stops because of an error inside the agent | Uncaught exception/error escaping `agentmain` | Log and handle initialization errors per policy, avoid depending on `main` |
| Using `-javaagent:launcher-demo.jar` does not run | Only `Launcher-Agent-Class` is declared, missing `Premain-Class` | Provide an agent JAR/manifest with `Premain-Class` and a `premain` method if using `-javaagent` |
| Transformer does not affect a class | Class was already loaded before registration; class name mismatch; transform returns `null` | Verify when the class is defined, the `com/example/Foo` name format, and that the transformer is registered |
| `retransformClasses` is rejected | VM/agent lacks capability or class is not modifiable | Check `isRetransformClassesSupported()`, `isModifiableClass()`, and manifest capabilities |
| Running a Spring Boot nested JAR cannot find the agent | Agent class is in an area not yet visible to the JVM startup loader | Inspect artifact contents and loader/manifest, try packaging the agent in a visible location or use `-javaagent` |

In addition, an agent can add startup overhead, affect performance, or alter application behavior. Only run agents and executable JARs from trusted sources; an agent itself has the ability to deeply intervene in bytecode and class loading.

## 9. Checklist Before Releasing an Executable JAR with an Embedded Agent

1. **Manifest:** has `Manifest-Version`, `Main-Class`, and `Launcher-Agent-Class` accurately set in the **main section**; class names use binary name syntax without `.class`.
2. **Packaging:** the agent class and its load-time dependencies are actually visible to the system class loader; test the exact JAR file after build/shading/repackaging.
3. **Entry point:** the agent has `public static void agentmain(String, Instrumentation)`; keep in mind the launcher always passes `agentArgs = ""` and the method must return.
4. **Configuration:** choose a clear system property/environment/config mechanism if the agent needs parameters; do not mistakenly read `main(args)` as `agentArgs`.
5. **Instrumentation capabilities:** register transformers at the right time, and check `isRetransformClassesSupported()` or `isRedefineClassesSupported()` before operations requiring additional capabilities.
6. **Real-world testing:** run `java -jar packaged-app.jar` on the target deployment JVM, confirm the agent launches before `main`, and verify behavior on agent failure as well as overhead.
7. **Other launch paths:** check `java -cp`, operational scripts, container entrypoints, and framework launchers; flags or manifest entries only take effect under **the right launch mechanism**.

## 10. Self-Check

**Scenario A:** The manifest has `Main-Class: DemoApp` and `Launcher-Agent-Class: LauncherAgent`. Which method does `java -jar demo.jar one two` call first? What is `agentArgs`?

**Answer:** The JVM calls `LauncherAgent.agentmain("", inst)` before `DemoApp.main(new String[]{"one", "two"})`, per the launcher contract. The agent receives an empty string; the application receives the two arguments.

**Scenario B:** Running `java -javaagent:demo.jar -jar demo.jar` with a JAR that only has `Launcher-Agent-Class` and does not have `Premain-Class`. Can the launcher entry point be used instead of premain?

**Answer:** No. `-javaagent` requires `Premain-Class` for the agent JAR; `Launcher-Agent-Class` only applies to the executable JAR mechanism and does not satisfy that requirement.

**Scenario C:** An agent running via `Launcher-Agent-Class` logs in `agentmain` and then throws an uncaught `IllegalStateException`. Does the application enter `main`?

**Answer:** No. Under the launcher agent contract, the JVM aborts when `agentmain` fails to initialize successfully.

**Scenario D:** If you simply replace `java -jar demo.jar` with `java -cp demo.jar DemoApp`, does the embedded agent still run automatically?

**Answer:** No. The `java -cp` syntax does not trigger `Launcher-Agent-Class` from the manifest like the `-jar` mechanism does.

## 11. Official References

- [Oracle Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): the three startup mechanisms, `agentmain`/`premain` signatures and errors, manifest capabilities.
- [Oracle Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): `Main-Class` and `Launcher-Agent-Class` manifest attributes.
- [Oracle — `jar` command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): `--create`, `--manifest`, `--file` syntax.
- [Spring Boot — Launching Executable JARs](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html): launcher/nested JAR structure to distinguish from standard JARs.

**Key takeaway:** `Launcher-Agent-Class` resides in an **executable JAR**, uses **`agentmain` before `main`**, passes **empty `agentArgs`**, and can cause the JVM to halt startup if the agent fails; `-javaagent` uses **`Premain-Class + premain`**, whereas dynamic attach uses **`Agent-Class + agentmain`**.
