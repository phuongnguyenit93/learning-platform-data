# Standalone Agent JAR, Executable JAR, and Application Class Path or Module Path

A Java agent does not have to be part of the application JAR file. When deploying **Java Instrumentation**, you typically have a **standalone agent JAR** loaded by the JVM via `-javaagent`, while the application runs in one of three ways: **executable JAR** (`java -jar`), **class path** (`java -cp`), or **module path** (`java --module-path ... --module ...`). These three application launch modes have different class/dependency lookup mechanisms, yet all of them can use the same standalone agent JAR.

The topic of this lesson is **Packaging and Deployment**: distinguishing JAR types, manifest purposes, where the JVM looks for agent and application code, differences in the Java Platform Module System (JPMS), how to package accompanying libraries, how to run in practice, and how to diagnose common errors. The complete example below is compiled with **`javac --release 17`**, runs on **JDK 24**, and has been verified in **all three modes**.

> **First Principle:** `-javaagent:agent.jar` specifies the JAR containing the **agent startup entrypoint**; `-jar app.jar` specifies the JAR containing the **application main entrypoint**. They are two different options of the same `java` command. An agent JAR does not automatically become an executable application JAR just by having `Premain-Class`; an application does not automatically become an agent just by having `Main-Class`.

## 1. Four Concepts to Distinguish Before Packaging

| Concept | What Does It Contain? | Launch/Resolution Mechanism |
| --- | --- | --- |
| **Standalone agent JAR** | Agent class with `premain`, `ClassFileTransformer`, and required helpers | `-javaagent:path/to/agent.jar[=options]`; `Premain-Class` manifest attribute |
| **Executable application JAR** | Application with a `public static void main(String[])` and `Main-Class` manifest attribute | `java -jar app.jar` |
| **Class path** | List of directories/JARs for the application class loader to find classes and resources | `-cp`/`--class-path`; code runs in an *unnamed module* if on the class path |
| **Module path** | List of module artifacts/directories for JPMS to resolve the module graph | `--module-path`/`-p` with `--module`/`-m`; explicit modules via `module-info.class` |

A JAR file is an **archive format**; whether it acts as an agent, executable app, explicit module, or library depends on **its metadata and how the launcher uses it**, not just the `.jar` extension.

Standard architecture example:

~~~text
distribution/
├── packaging-agent.jar          -> loaded by the JVM via -javaagent
├── app.jar                      -> launched by the JVM via -jar, -cp, or -m
└── lib/
    └── greeting-lib.jar         -> application library
~~~

Startup flow diagram:

~~~text
java launcher
  |
  +-- -javaagent:packaging-agent.jar=lesson
  |         |
  |         +-- read Premain-Class
  |         +-- invoke premain("lesson", Instrumentation)
  |         +-- register ClassFileTransformer
  |
  +-- choose one application launch mode:
            |
            +-- -jar app.jar
            +-- -cp ... demo.app.Main
            +-- --module-path ... --module demo.app/demo.app.Main
                         |
                         v
                   invoke application main
                         |
                         v
                  load classes/dependencies
                  transformer receives callbacks
~~~

For a startup agent, the JVM invokes `premain` **before** the application `main`. Therefore, a load-time transformer registered early enough can observe application classes defined after the registration point.

## 2. Standalone Agent JAR: What Is Premain-Class?

An agent JAR loaded at startup must have a manifest entry:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PackagingAgent
~~~

The manifest file requires a **blank line terminating the main section**. The value of `Premain-Class` is the dot-separated **binary name** of the agent class located in the JAR. The agent class provides one of two overloads:

~~~java
public static void premain(String agentArgs,
                           java.lang.instrument.Instrumentation instrumentation)
~~~

or:

~~~java
public static void premain(String agentArgs)
~~~

The JVM prefers the overload that accepts `Instrumentation` when present. If the agent needs to register a `ClassFileTransformer`, the overload with `Instrumentation` is the most convenient.

When launching:

~~~bash
java -javaagent:packaging-agent.jar=lesson -jar app.jar
~~~

The JVM passes the string `"lesson"` to `agentArgs`. The option string after the `=` sign is a **string parsed by the agent itself**; Java Instrumentation does not enforce any JSON, CSV, or key-value format.

### An Agent JAR Does Not Need Main-Class

A JAR having:

~~~text
Premain-Class: demo.agent.PackagingAgent
~~~

but **no** `Main-Class` is completely normal: operators **do not run**:

~~~bash
java -jar packaging-agent.jar
~~~

to start instrumenting an application. That command will not run the agent via the `Premain-Class` mechanism; executable `-jar` requires a valid application `Main-Class`.

Conversely, `app.jar` having only `Main-Class` works with `java -jar app.jar` but is **not sufficient to start as an agent** via `-javaagent:app.jar` if it lacks an appropriate `Premain-Class`.

### An Agent May Need Its Own Dependencies

If `PackagingAgent` uses a bytecode library such as ASM or Byte Buddy, those library classes must **be found in the agent's loader context**. Having a library on the application's module path or inside a nested JAR **does not automatically** allow the agent to resolve it.

Common deployment approaches:

- Create an **agent JAR with properly packaged dependencies** (*shaded/uber JAR*) and check resource/service metadata.
- Or distribute the agent JAR alongside dependency JARs with a compatible manifest `Class-Path`, if the launcher/system loader can resolve them as designed.
- Keep runtime helpers called from injected bytecode **separate** and arrange accessibility according to the target's class loader/module.

In the hands-on example, the agent uses only JDK APIs and has no third-party dependencies so learners can verify packaging without needing Maven/Gradle.

## 3. Executable JAR: Main-Class and Class-Path

An executable JAR declares the application entrypoint:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/greeting-lib.jar
~~~

The two attributes serve different roles:

- `Main-Class: demo.app.Main` tells the JVM which `main(String[])` method to invoke when running `-jar`.
- `Class-Path: lib/greeting-lib.jar` is the **manifest class path**, declaring a **relative path from the location of app.jar** to the library JAR that needs to be added for class lookup.

For example:

~~~text
dist/
├── app.jar
└── lib/
    └── greeting-lib.jar
~~~

If `app.jar` is in `dist/`, `Class-Path: lib/greeting-lib.jar` points to `dist/lib/greeting-lib.jar`. It is **not** a path relative to the current working directory in all cases. Moving only `app.jar` without preserving the dependency directory structure can cause the application to fail to find `Greeting`.

**Note:** the manifest `Class-Path` is a space-separated list of **relative URLs**, not the same `:`/`;` syntax as the `-cp` option. For example:

~~~text
Class-Path: lib/greeting-lib.jar lib/metrics.jar config/
~~~

This is an **illustrative manifest example with sample paths**, not the actual structure of the demo. Directories must be declared with appropriate relative URLs; for production libraries, check resource packaging and path rules for deployment environments.

### When Using -jar, -cp Does Not Control the Application Classpath

According to the Java launcher documentation, if you run:

~~~bash
java -cp "other.jar" -jar app.jar
~~~

then **the classpath provided by `-cp` is not the source for finding user classes of the application launched by `-jar`**. The launcher uses the app JAR and its manifest class-path entries. Therefore, do not rely on `-cp extra.jar -jar app.jar` to load additional dependencies for an executable JAR.

The proper ways in the example are to put dependencies in the **manifest `Class-Path`**, use a purpose-built packaging launcher, or avoid `-jar` and run with `-cp ... MainClass`.

This distinction does not disable `-javaagent`: it is a **separate JVM option**. You can completely run:

~~~bash
java -javaagent:packaging-agent.jar=lesson -jar app.jar
~~~

and the agent still receives `premain` before the application, as verified.

## 4. Class Path: Launching the Application by Main Class

Instead of relying on the `Main-Class` manifest of the app JAR, operators can place both the application and library JARs on the class path:

~~~text
Windows:
    java -javaagent:packaging-agent.jar=lesson -cp "app.jar;lib/greeting-lib.jar" demo.app.Main

Linux/macOS:
    java -javaagent:packaging-agent.jar=lesson -cp "app.jar:lib/greeting-lib.jar" demo.app.Main
~~~

These are **two illustrative commands to run while inside dist/**. On Windows, the class path separator is a **semicolon `;`**; on Linux/macOS, it is a **colon `:`**. Using a hardcoded classpath string with the wrong separator can lead to `ClassNotFoundException` or `NoClassDefFoundError`.

Differences from `-jar`:

1. You explicitly specify the main class name `demo.app.Main` after the JVM options.
2. `-cp` determines where the launcher looks for classes and resources for the classpath.
3. No `Main-Class` manifest attribute is needed to launch by main class.
4. Multiple JARs/directories can be explicitly placed on the classpath.
5. Classes loaded from the class path belong to the **unnamed module** of the corresponding loader in JPMS.

With the same demo, the app and library JARs contain `module-info.class`, yet **when placed on the class path they are still treated as non-modular JARs**; the JVM does not use the `requires`/`exports` of that descriptor to create a named module for classes on the class path. This is an important property of the JAR File Specification.

### Class Path Wildcards and Class Lookup Order

A common launcher example:

~~~bash
java -cp "app.jar:lib/*" demo.app.Main
~~~

With the Java launcher, `lib/*` expands to the `.jar`/`.JAR` files directly inside the directory, but **the order of JARs expanded by the wildcard is not guaranteed**. Do not rely on wildcards if the application has multiple versions of the same class where load order is part of the logic.

Moreover, a class path wildcard does not turn a directory into a "fat JAR"; resource/class files in non-standard layouts still require proper packaging.

## 5. Module Path: Running the Application as a Named Module

JPMS was introduced in Java 9. For a modular application JAR, `module-info.java` is compiled into `module-info.class` at the root of the JAR. Example application module:

~~~java
module demo.app {
    requires demo.greeting;
}
~~~

And library module:

~~~java
module demo.greeting {
    exports demo.greeting;
}
~~~

The descriptor content describes **relationships between modules**:

- `requires demo.greeting`: the application module reads this library module.
- `exports demo.greeting`: public types in the library package are accessible at the Java API level to other modules that read it.
- `module-info.class` defines the explicit module name, not just the binary names of classes.

When running:

~~~text
Windows:
    java -javaagent:packaging-agent.jar=lesson --module-path "app.jar;lib/greeting-lib.jar" --module demo.app/demo.app.Main

Linux/macOS:
    java -javaagent:packaging-agent.jar=lesson --module-path "app.jar:lib/greeting-lib.jar" --module demo.app/demo.app.Main
~~~

The launcher resolves module `demo.app` and dependency `demo.greeting` via the **module path**. The `/demo.app.Main` part after the module name is the main class to execute; it can be omitted if the module artifact already provides a main class in its metadata and the launcher can determine it.

Points to distinguish clearly:

| Where the JAR Is Placed | How the JVM Treats the JAR |
| --- | --- |
| `-cp app.jar` | Classpath entry, **unnamed module**, even if the JAR has `module-info.class` |
| `--module-path app.jar --module demo.app` | Explicit named module `demo.app` if the descriptor is valid |
| `--module-path some-legacy.jar` | Can be an **automatic module** if the JAR has no descriptor; module name follows `Automatic-Module-Name` or derivation rules |
| `-jar app.jar` | Runs as an executable JAR, the app is loaded via this classpath mechanism; a descriptor does not automatically make it a named module |

**Do not expect the manifest `Class-Path` to automatically satisfy `requires demo.greeting` in a named module graph.** With `--module`, the `demo.greeting` module must be among the modules the resolver can observe/resolve (e.g., via `--module-path`). Manifest `Class-Path` is a mechanism for class-path JARs, not module descriptors.

### Where Does the Agent JAR Sit in a Modular Application?

Even when the application runs with `--module-path`, the standalone agent is still loaded by the JVM via **`-javaagent:packaging-agent.jar`**; there is no need to move the agent JAR onto the module path just because the app is modular.

According to the Java Instrumentation package spec, agent classes of a startup agent JAR are loaded by the system class loader into the **unnamed module of the system loader**. In the demo, the transformer receives the `Module module` parameter of the **target class**, so it observes:

- `demo.app.Main` belongs to named module `demo.app` when running in modular mode.
- `demo.greeting.Greeting` belongs to named module `demo.greeting` when running in modular mode.

**Do not equate the agent's module with the module of the class being transformed.** A transformer living in the system loader's unnamed module can still be invoked by the JVM to observe classes of a named module. However, if newly injected bytecode calls an agent helper, you must also address **class loader visibility and module access** for that call.

## 6. Hands-On Practice: One Agent and Application Running in All Three Modes

The example uses **three artifacts**:

1. `packaging-agent.jar` — standalone Java agent containing `Premain-Class`.
2. `app.jar` — executable application JAR with `Main-Class`, `Class-Path`, and `module-info.class`.
3. `lib/greeting-lib.jar` — modular library JAR with module `demo.greeting`.

The agent only **observes** callbacks for the target classes and prints the corresponding module name; it always returns `null`, so it **does not modify bytecode**. The application program prints `mainModule`, the flag state set by the agent before `main` runs, and the result of calling the library method `Greeting.text()`.

As a result, if one launch mode is missing a dependency, you will get an error; if the module graph is correct, the program produces the same business output but **different module names**.

### 6.1. Source and Distribution Structure

Create the directories:

~~~text
packaging-demo/
├── agent-src/
│   └── demo/agent/PackagingAgent.java
├── greeting-src/
│   ├── module-info.java
│   └── demo/greeting/Greeting.java
├── app-src/
│   ├── module-info.java
│   └── demo/app/Main.java
├── agent.mf
└── app.mf
~~~

After building:

~~~text
packaging-demo/
├── agent-bin/
├── greeting-bin/
├── app-bin/
└── dist/
    ├── packaging-agent.jar
    ├── app.jar
    └── lib/
        └── greeting-lib.jar
~~~

All sources in the demo use Java features available in JDK 17. There are no third-party libraries and `--enable-preview` is not required.

### 6.2. File agent-src/demo/agent/PackagingAgent.java

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class PackagingAgent {
    public static void premain(String options, Instrumentation inst) {
        System.setProperty("demo.agent.active", "true");
        System.out.println("agentPremain=" + options);

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> old,
                    ProtectionDomain domain,
                    byte[] bytes) {

                if ("demo/app/Main".equals(className)
                        || "demo/greeting/Greeting".equals(className)) {

                    String moduleName = module != null && module.isNamed()
                            ? module.getName() : "unnamed";
                    System.out.println("agentSaw=" + className
                            + " module=" + moduleName);
                }

                return null;
            }
        });
    }
}
~~~

**How to read the code:**

- `premain(String, Instrumentation)` is invoked by the JVM before `Main.main()`. It prints the exact option from `-javaagent:...=lesson`.
- `System.setProperty("demo.agent.active", "true")` acts as a test marker that the agent actually started; in production, avoid creating unnecessary JVM-wide side effects.
- `inst.addTransformer(...)` registers a transformer for **load-time instrumentation**; using the single-parameter overload makes it **non-retransformation-capable** by default.
- `className` is a **JVM internal name** with `/` separators; filter for `"demo/app/Main"` and `"demo/greeting/Greeting"` before processing.
- `module.isNamed()` distinguishes a named module from an unnamed module of the target class. The name `"unnamed"` is just a **display label chosen by the demo**, not a value returned directly by `module.getName()`.
- `return null` means the transformer **does not provide replacement bytes**; the JVM continues defining the class normally.

**Safety note:** the demo prints `System.out.println` directly inside the callback for illustration. In a production agent, synchronous logging on the class-loading path can increase latency and cause lock contention. Replace it with fast filters, counters, or bounded telemetry; do not reload the target itself via `loader.loadClass(className)` inside the callback.

### 6.3. File greeting-src/module-info.java

~~~java
module demo.greeting {
    exports demo.greeting;
}
~~~

The descriptor declares an explicit module named `demo.greeting`, exporting the `demo.greeting` package so the application module can call the library's public methods.

### 6.4. File greeting-src/demo/greeting/Greeting.java

~~~java
package demo.greeting;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "hello-from-library";
    }
}
~~~

This class uses only Java SE. When the application calls `Greeting.text()` for the first time, the agent's transformer gets the chance to observe the name `demo/greeting/Greeting` and the module containing this class.

### 6.5. File app-src/module-info.java

~~~java
module demo.app {
    requires demo.greeting;
}
~~~

In **module mode**, `requires demo.greeting` forces the resolver to find the library module. When this JAR is on the **class path**, the descriptor does not create a named module for the app; thus the same JAR can be tested in both classpath and modulepath modes.

### 6.6. File app-src/demo/app/Main.java

~~~java
package demo.app;

import demo.greeting.Greeting;

public final class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();

        System.out.println("mainModule="
                + (module.isNamed() ? module.getName() : "unnamed"));
        System.out.println("agentActive="
                + System.getProperty("demo.agent.active", "false"));
        System.out.println("greeting=" + Greeting.text());
    }
}
~~~

The application code **does not import or call any agent class**. It only reads a system property used as a test marker. This design allows swapping the agent JAR or disabling the agent without changing how `Main` and `Greeting` are compiled.

If run without `-javaagent`, the property defaults to `false`; if the agent is enabled, it becomes `true`. In the demo, the agent sets the property before `main` runs, so the test output confirms the startup order of the two entrypoints.

### 6.7. File agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PackagingAgent
~~~

Keep a **blank line after the `Premain-Class` line**. No `Main-Class` is needed in the agent JAR. Only if an implementation actually needs to retransform/redefine already-loaded classes should you add manifest capabilities such as `Can-Retransform-Classes: true` or `Can-Redefine-Classes: true` along with `Instrumentation.is...Supported()` checks; the current demo performs load-time observation only.

### 6.8. File app.mf

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/greeting-lib.jar
~~~

**Keep a blank line at the end of the main section.** This manifest file is used to build the executable `app.jar`; `Class-Path` points to the library in `dist/lib/` relative to the location of `dist/app.jar`.

Note: `module-info.class` will still be packaged inside `app.jar` alongside the manifest. In `--module` mode, the module descriptor determines dependency relationships; in `-jar` mode, the manifest `Main-Class`/`Class-Path` determines the entrypoint and library class path.

### 6.9. Compiling Each Artifact with JDK 17+

The commands below run from the root directory `packaging-demo/`. First, create the output directories:

~~~bash
mkdir -p agent-bin greeting-bin app-bin dist/lib
~~~

**Step A — Agent JAR:**

~~~bash
javac --release 17 -d agent-bin agent-src/demo/agent/PackagingAgent.java
jar --create --file dist/packaging-agent.jar \
    --manifest agent.mf -C agent-bin .
~~~

Use `-C agent-bin .` to package all compiled classes, including the anonymous class of `ClassFileTransformer` (e.g., `PackagingAgent$1.class`). If you only package `PackagingAgent.class` and forget the nested implementation class, the agent may encounter class loading errors when running `premain`.

**Step B — Modular Library JAR:**

~~~bash
javac --release 17 -d greeting-bin \
    greeting-src/module-info.java \
    greeting-src/demo/greeting/Greeting.java

jar --create --file dist/lib/greeting-lib.jar \
    -C greeting-bin .
~~~

The library contains `module-info.class`, so it is an explicit modular JAR when placed on the module path.

**Step C — Modular/Executable Application JAR:**

~~~bash
javac --release 17 \
    --module-path dist/lib/greeting-lib.jar \
    -d app-bin \
    app-src/module-info.java \
    app-src/demo/app/Main.java

jar --create --file dist/app.jar \
    --manifest app.mf -C app-bin .
~~~

`javac --module-path` at compile time helps the compiler resolve `demo.greeting` from the library module and check `requires`. This is a **compiler option**; running the application afterward with `-jar` or `-cp` still determines the runtime loading mode independently.

The Bash snippet uses `\` for line continuation. For **Windows PowerShell 5.1**, use the following single-line commands to avoid shell parsing errors:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, greeting-bin, app-bin, dist/lib | Out-Null
javac --release 17 -d agent-bin agent-src/demo/agent/PackagingAgent.java
jar --create --file dist/packaging-agent.jar --manifest agent.mf -C agent-bin .
javac --release 17 -d greeting-bin greeting-src/module-info.java greeting-src/demo/greeting/Greeting.java
jar --create --file dist/lib/greeting-lib.jar -C greeting-bin .
javac --release 17 --module-path dist/lib/greeting-lib.jar -d app-bin app-src/module-info.java app-src/demo/app/Main.java
jar --create --file dist/app.jar --manifest app.mf -C app-bin .
~~~

In CI, **fail the pipeline if `javac` or `jar` returns a non-zero exit code**; do not proceed to the run step with a stale artifact already on disk.

### 6.10. Running Mode 1 — Executable JAR

Change into the `dist/` directory after building. The command is the same on Windows/Linux/macOS because there is no path-list separator:

~~~bash
java -javaagent:packaging-agent.jar=lesson -jar app.jar
~~~

**Exact stdout verified on JDK 24:**

~~~text
agentPremain=lesson
agentSaw=demo/app/Main module=unnamed
mainModule=unnamed
agentActive=true
agentSaw=demo/greeting/Greeting module=unnamed
greeting=hello-from-library
~~~

From the output:

- `agentPremain=lesson` appears **before** the app output.
- `Main` is loaded with `module=unnamed` even though `app.jar` contains `module-info.class`.
- `Greeting` is found via `Class-Path: lib/greeting-lib.jar` from the executable JAR's manifest.
- `greeting=hello-from-library` confirms the dependency is present and called successfully.

### 6.11. Running Mode 2 — Class Path with Main Class

**Windows PowerShell:**

~~~powershell
java -javaagent:packaging-agent.jar=lesson -cp "app.jar;lib/greeting-lib.jar" demo.app.Main
~~~

**Linux/macOS Bash:**

~~~bash
java -javaagent:packaging-agent.jar=lesson -cp 'app.jar:lib/greeting-lib.jar' demo.app.Main
~~~

**Exact stdout verified on JDK 24:**

~~~text
agentPremain=lesson
agentSaw=demo/app/Main module=unnamed
mainModule=unnamed
agentActive=true
agentSaw=demo/greeting/Greeting module=unnamed
greeting=hello-from-library
~~~

The output matches `-jar` mode in module identity because both use classpath-mode loading for the app and library. However, **the entrypoint selection mechanism differs**: `-cp ... demo.app.Main` specifies the class on the command line without needing to read `Main-Class` to decide which class to invoke.

In this example, `app.jar` has a manifest `Class-Path`, yet the `-cp` command also explicitly lists the library for clarity and control. In a real distribution, avoid putting multiple versions of duplicate classes on the classpath because class lookup order can create hard-to-diagnose errors.

### 6.12. Running Mode 3 — Module Path with Named Modules

**Windows PowerShell:**

~~~powershell
java -javaagent:packaging-agent.jar=lesson --module-path "app.jar;lib/greeting-lib.jar" --module demo.app/demo.app.Main
~~~

**Linux/macOS Bash:**

~~~bash
java -javaagent:packaging-agent.jar=lesson --module-path 'app.jar:lib/greeting-lib.jar' --module demo.app/demo.app.Main
~~~

**Exact stdout verified on JDK 24:**

~~~text
agentPremain=lesson
agentSaw=demo/app/Main module=demo.app
mainModule=demo.app
agentActive=true
agentSaw=demo/greeting/Greeting module=demo.greeting
greeting=hello-from-library
~~~

Compared to modes 1 and 2, the difference is **not the business output**, but the **runtime module identity**:

- `Main.class.getModule().getName()` is `"demo.app"`.
- `Greeting.class.getModule().getName()` (observed by the agent via `Module module`) is `"demo.greeting"`.
- The runtime module graph actually resolves `requires demo.greeting` from `module-info.class`.

**This is the programmatically observable distinction between class path and module path**, rather than just reading JPMS theory.

## 7. Direct Comparison of the Three Launch Modes

| Feature | `-javaagent ... -jar app.jar` | `-javaagent ... -cp ... Main` | `-javaagent ... --module-path ... --module ...` |
| --- | --- | --- | --- |
| JVM starts agent separately | Yes | Yes | Yes |
| Agent entrypoint | `Premain-Class` / `premain` | Same as left | Same as left |
| App entrypoint | Manifest `Main-Class` | Main class name on CLI | Module name / main class |
| App module identity in demo | `unnamed` | `unnamed` | `demo.app` |
| Library module identity in demo | `unnamed` | `unnamed` | `demo.greeting` |
| Primary dependency source | Manifest `Class-Path` | `-cp`/launcher classpath | `module-info` and module resolver |
| Can reuse the same agent.jar | Yes | Yes | Yes |
| Need to put agent.jar on module path | No | No | No |
| May need module access for injected helpers | Depends on target | Depends on target | Especially important with named modules |

In terms of distribution, **the exact same set of JARs can run in multiple modes**, as in the demo, if compiled and declared with appropriate modules/manifests. However, not every existing application can switch launch modes arbitrarily. If you use framework launchers, nested JAR layouts, automatic modules, dynamic plugins, or module-specific service binding, you must test the actual runtime mode.

## 8. Which Loader/Module Do Agent Classes Live In?

A key question when deploying instrumentation is **whether agent code can see application classes, and whether application classes can see agent helpers?**

According to the `java.lang.instrument` package specification, classes from a **standalone agent JAR** loaded via Java instrumentation are loaded by the **system class loader** into the **unnamed module of the system loader**.

That **does not mean**:

1. Every application class is also defined by the system loader. Plugin loaders or custom class loaders can define targets independently.
2. The agent automatically reads every private/internal package of every named module.
3. Any injected bytecode calling a helper in the agent JAR is guaranteed to resolve and access the helper.
4. The agent needs to be on the application's module path.
5. The agent can bypass class loader constraints or Java Module System access rules.

A modular application can have a target belonging to `demo.app`, while the agent `demo.agent.PackagingAgent` still lives in the unnamed module. The `transform(Module module, ...)` method receives the **Module of the target class**. This is the information to preserve in order to filter named/unnamed modules accurately.

### Example of Using Module in a Transformer

~~~java
if (module != null && module.isNamed()) {
    String targetModule = module.getName();
    if (!"demo.app".equals(targetModule)) {
        return null;
    }
}
~~~

This is an **illustrative code snippet** inside a callback; it is not a standalone program. Do not blindly dereference `module` if it could be null. Also avoid filtering classes solely by binary name when multiple class loaders can define the same name in different contexts.

### When Instrumented Bytecode Calls an Agent Helper

Suppose a transform injects into `demo.app.Main` a call:

~~~text
invokestatic demo/agent/TelemetryHelper.record()V
~~~

This is an illustrative **JVM bytecode mnemonic**, not standalone Java source. When the target method runs, the JVM must resolve `TelemetryHelper` and perform access checks appropriate to the caller's runtime class loader/module.

If the target is defined by the bootstrap loader while the helper only exists in the system loader, the bootstrap class **cannot automatically find that helper**. If the target belongs to a named module, readability/exports/opens and the relevant instrumentation mechanisms must also be considered. Therefore:

- When a shared helper is needed for bootstrap targets, consider placing a **very small, isolated** JAR via `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`, with appropriate dependency limits.
- When using a helper in an application/custom loader, ensure that loader has a resolution path and avoid duplicate classes.
- For complex module access, consider the `Instrumentation.redefineModule(...)` API or launcher options such as `--add-reads`, `--add-exports`, `--add-opens` **only when genuinely needed and tested**.
- Do not use opening modules as a fix for invalid class files or missing dependencies.
- Do not let a helper depend back on a target currently being loaded and inadvertently trigger reentrant class loading.

**The demo does not inject helper calls into target methods**, so it requires no additional read edges or opened packages. That isolates the problem of **application packaging and resolution** from the problem of **runtime helper injection**.

## 9. Manifest Attributes Related to Java Agents

Attributes that are easily confused:

| Manifest Attribute | Where Used | What the JVM Invokes |
| --- | --- | --- |
| `Main-Class` | Executable application JAR | `public static void main(String[])` when running `-jar` |
| `Premain-Class` | Agent JAR loaded via `-javaagent` at startup | `premain(String, Instrumentation)` or single-argument overload |
| `Agent-Class` | Agent JAR attached to a **running JVM** (if supported by the environment) | `agentmain(...)` |
| `Launcher-Agent-Class` | Agent **packaged together with an executable application JAR** (special mechanism) | `agentmain(...)` **before application main** |
| `Can-Retransform-Classes` | Agent capabilities | Allows agent to request retransformation if supported by the JVM |
| `Can-Redefine-Classes` | Agent capabilities | Allows agent to request redefinition if supported by the JVM |
| `Boot-Class-Path` | Agent JAR, bootstrap helper search | Adds helper search paths per manifest rules |
| `Class-Path` | JAR manifest class path | Locates dependencies as relative URLs |

### Is Launcher-Agent-Class the Same as -javaagent?

**Not entirely.** In Java SE 21, when an executable JAR has `Launcher-Agent-Class`, the launcher can load the agent class **from the executable JAR itself** and invoke **`agentmain` before app main**. By contrast, for a **standalone** agent JAR specified with `-javaagent`, the JVM invokes **`premain`** based on `Premain-Class`.

Therefore, do not copy a class that only has a `premain` method and assume it will run automatically when you add `Launcher-Agent-Class`. Co-packaging requires the appropriate JAR structure/entrypoint and must be tested separately.

**This hands-on lesson uses the standalone model**, not `Launcher-Agent-Class`. This is a convenient deployment approach when administrators want to enable, disable, or swap agent versions without rebuilding the application JAR.

### Runtime Attach Is Not the Same as a Startup Agent

If a tool attaches an agent to an **already running** JVM, the JAR must have `Agent-Class`, an `agentmain` method, and satisfy the implementation's attach rules/mechanisms. You cannot assume a JAR with only `Premain-Class` will automatically invoke `agentmain` on attach. Policies allowing dynamic agent loading may vary by JDK/JVM, so you must check the target runtime.

For load-time tracing that needs to intercept classes very early, **launching with `-javaagent`** usually provides a clearer observation scope than attaching late and having to retransform already-loaded classes.

## 10. Where Should Agent and Application Third-Party Libraries Be Placed?

Do not mix the two dependency trees just because they reside on the same machine.

| Dependency | Who Uses It? | Packaging Approach |
| --- | --- | --- |
| `java.lang.instrument` / JDK APIs | Agent startup | Built into the JDK/platform modules; do not copy JDK classes into the JAR |
| Agent's ASM/Byte Buddy | Agent transformer/helper | Agent distribution/shaded JAR or agent library visible to the agent's loader |
| `demo.greeting.Greeting` | Application `demo.app.Main` | `lib/greeting-lib.jar` via manifest `Class-Path` or module path |
| Helper called by target bytecode at runtime | Instrumented target | Depends on **target's** loader/module; may need a bootstrap bridge |
| Build tool plugins (Maven/Gradle) | Build machine | Should not be packaged into runtime JARs |
| ServiceLoader descriptors/resources | Libraries needing runtime discovery | Must be preserved in the JAR under `META-INF/services/...` or proper module descriptors |

If you build a **fat/uber JAR** with Maven Shade or Gradle Shadow, consider:

- Package/class collisions between the agent and the application.
- Shading/relocation helps avoid conflicts between multiple library versions, but does not automatically solve all module access issues.
- `META-INF/services` files must be merged properly if dependent libraries use `ServiceLoader`.
- Old JAR signatures may become invalid after contents are modified and must be handled safely and re-signed if required.
- `module-info.class` files from multiple dependencies cannot simply be concatenated into a valid module descriptor without an explicit JPMS design.
- The agent entrypoint class and nested transformer classes must actually be present in the built artifact.
- Package relocation must stay consistent with reflection code, resource names, and manifest references if they are affected.

### Framework Nested JARs Are Not Standard java -jar Classpath

Some frameworks like Spring Boot support executable "fat JARs" with **nested JARs** and a custom launcher. That is a **framework-implemented** mechanism, not the default Java launcher automatically treating any nested JAR inside any ZIP/JAR as classpath entries.

If you want the agent to use a library located inside a framework application JAR, do not assume the agent's system class loader will automatically traverse nested JARs managed by the application's custom launcher. Distribute and test the agent's dependencies **separately**, and consider how helpers are accessed by target loaders/modules.

## 11. Inspecting Artifacts Before Running

After creating the three JARs, use the JDK tools:

~~~bash
jar --list --file dist/packaging-agent.jar
jar --list --file dist/app.jar
jar --list --file dist/lib/greeting-lib.jar
jar --describe-module --file dist/app.jar
jar --describe-module --file dist/lib/greeting-lib.jar
~~~

These commands only **list/inspect artifacts**; they do not run instrumentation. Check the core points:

- `packaging-agent.jar` must contain `demo/agent/PackagingAgent.class` and the compiler-generated nested transformer class.
- The agent's manifest must have `Premain-Class: demo.agent.PackagingAgent`.
- `app.jar` must contain `demo/app/Main.class`, `module-info.class`, and the `Main-Class` manifest attribute.
- `greeting-lib.jar` must contain `demo/greeting/Greeting.class` and the `module-info.class` of `demo.greeting`.
- The module descriptor of `demo.app` must `requires demo.greeting`, and the library descriptor must `exports demo.greeting`.
- The distribution must keep the library at `dist/lib/greeting-lib.jar` if using executable mode with the demo's manifest path.

**Distinguish artifact inspection from actual runtime testing:** a file existing or `jar --list` showing a class does not prove the runtime module graph resolves properly or that the transformer was invoked. You must run each command in Sections 6.10–6.12 and check stdout/exit codes.

## 12. Diagnosing Common Packaging and Runtime Errors

| Symptom | Common Cause | Check / Fix |
| --- | --- | --- |
| `no main manifest attribute` on `java -jar app.jar` | Missing `Main-Class` | Check app manifest and main method |
| `Failed to find Premain-Class manifest attribute` | Wrongly passed app JAR to `-javaagent` or missing agent manifest | Check manifest inside the agent JAR |
| `ClassNotFoundException: demo.app.Main` | Wrong class package/path or wrong classpath | `jar --list` and command line |
| `NoClassDefFoundError: demo/greeting/Greeting` | Missing dependency when running `-jar`/`-cp` | Correct manifest `Class-Path` or `-cp` |
| `Module demo.greeting not found, required by demo.app` | Library module not on module path or wrong module name | `--module-path`, `jar --describe-module` |
| `FindException` due to duplicate modules | Duplicate modules or inconsistent module names | Remove duplicate JAR, check module names |
| `IllegalAccessError` / `InaccessibleObjectException` | Module readability, exports/opens, or reflection | Check JPMS access; do not open indiscriminately |
| `agentPremain=...` does not appear | Missing `-javaagent` or different startup mechanism used | Print JVM command line and manifest |
| App `main` does not run due to agent error | `premain` throws uncaught error or missing agent dependency | Fix agent startup failure first |
| `app.jar` runs with `-jar` but ignores `-cp extra.jar` | `-jar` ignores CLI classpath for app | Put dependency in manifest or change launch mode |
| Agent found with `-cp` but helper missing when target is bootstrap-loaded | Helper only visible to system loader | Provide bootstrap helper if needed |
| App runs as unnamed instead of named | Used `-jar`/`-cp` instead of `--module` | Run in proper module mode |
| `ClassCastException` between two classes with the same name | Different class loaders create two runtime identities | Check defining loader/module and duplicate JARs |
| `UnsupportedClassVersionError` | Build JDK/release higher than runtime | Use `javac --release <target>` |
| Class transformed but `ClassFormatError`/`VerifyError` | Transformer returned invalid bytes | Verify output and test on target JDK |
| Static helper throws error during class loading | Agent helper initialization I/O or circular dependency | Pre-initialize dependencies and keep callbacks minimal |

**Do not** use "copy all application libraries into agent.jar" as a knee-jerk reaction to `ClassNotFoundException`. Duplicate classes and class loaders can make the error worse; first determine **which class needs to be loaded by which loader** and belongs to which module.

### A Minimal Test to Isolate Failures

1. Run `java -jar app.jar` **without the agent** (if the app manifest `Class-Path` is sufficient).
2. Run `java -javaagent:packaging-agent.jar=lesson -jar app.jar`.
3. Run `java -javaagent:packaging-agent.jar=lesson -cp ... demo.app.Main`.
4. Run `java -javaagent:packaging-agent.jar=lesson --module-path ... --module demo.app/demo.app.Main`.

If step 1 fails, fix the application packaging first. If step 1 succeeds but step 2 fails, investigate agent startup/transformer dependencies. If only step 4 fails, inspect the module graph and JPMS access. This layered isolation is faster than randomly editing manifests repeatedly.

## 13. Production Deployment and Side Risks

### 13.1. Agent Privileges

A Java agent can deeply alter code executed by the JVM. Only deploy agents from trusted sources, and verify versions, hashes/signatures, and JAR distribution permissions. Never take a JAR from an unverified source and enable `-javaagent` on a production application.

### 13.2. Keeping Startup Paths Reproducible

Record in full:

- JDK runtime version and vendor/JVM implementation.
- Hashes/build versions of the agent JAR, app JAR, and library JARs.
- Exact `java` command and JVM options.
- Classpath/modulepath along with entry order when there are multiple JARs.
- Agent options and instrumentation policies; do not log secrets to stdout.
- Target class loader/module names if custom loaders are present.

On Windows, record the `;` separator; on Linux/macOS, record `:`. For container images, make sure to COPY the entire `dist/lib/` structure if the manifest `Class-Path` uses that path. If using a Java executable in the image, verify it includes the `java.instrument` module; minimal runtime images created by `jlink` may lack modules required by an agent.

### 13.3. Java Version Compatibility

Both the agent and application in the demo are compiled with `--release 17`. This restricts the compiler's API/class-file output version to Java 17, helping avoid errors when running on JDK 17+. However, if the agent uses a bytecode library, that library version **must understand the class-file version of the classes it instruments**, which may be newer than the target release the agent itself was compiled for.

Do not equate `javac --release 17` with every Java agent working on every JVM and every bytecode version: you must test the exact JDK vendor, version, and class files the application actually loads.

### 13.4. Multiple Agents and Transformer Order

A single process can have multiple options:

~~~bash
java -javaagent:metrics-agent.jar -javaagent:security-agent.jar -jar app.jar
~~~

`premain` methods are invoked in the **order of `-javaagent` options on the command line**. However, transformer execution order does not depend solely on `premain` order: per `ClassFileTransformer`, the JVM applies Java/native **retransformation-incapable/capable** groups in a specified order, and registration order within each group.

Therefore, if two agents modify the same class, you must test the **final byte pipeline** and ordering compatibility. Do not conclude "agent A starts first so all of A's transforms always run before all of B's transforms" if they belong to different capability groups.

## 14. Tests to Include in CI

A reliable packaging test suite should include:

1. **Manifest test:** read `agent.jar` and `app.jar`, confirming `Premain-Class`/`Main-Class` have valid binary names.
2. **Jar content test:** all required nested/anonymous helper classes are packaged.
3. **Dependency test:** executable `-jar` finds `lib/greeting-lib.jar` via the relative path.
4. **Classpath test:** running with `-cp` using the right OS separator confirms app `main` executes.
5. **Modulepath test:** `jar --describe-module` shows correct `requires`/`exports` and `java --module-path ... --module ...` succeeds.
6. **Agent startup test:** `agentPremain` appears before `mainModule`.
7. **Transformer callback test:** the agent sees the expected internal names and receives the target's module.
8. **Isolation test:** running the app **without the agent** still satisfies the business contract, unless product requirements mandate the agent.
9. **Negative test — missing lib:** relocate the library in the test environment to confirm the error is clearly detected and not masked by an old classpath.
10. **Negative test — wrong manifest:** missing `Premain-Class`/`Main-Class` must fail the test, not be treated as a successful no-op.
11. **Custom loader test:** if production has plugins or nested loaders, verify helper visibility under the actual loader.
12. **JPMS access test:** for named modules, test closed/opened packages and injected helper paths if the agent modifies bytecode.
13. **Version matrix:** run on target JDKs, especially when using bytecode transformation libraries.
14. **Artifact integrity:** verify JAR hashes/signatures, dependency SBOM, and deployment layout.
15. **Performance sanity:** the agent does not increase startup/class-loading latency beyond budget when many modules/classes are enabled.

**A build that merely "created the JAR successfully" is not enough.** CI must prove that entrypoints are invoked and runtime dependencies are actually resolved in the intended deployment mode.

## 15. Exercises and Self-Check Questions

**Question 1.** Why is `Premain-Class` not equivalent to `Main-Class` even though both reside in `META-INF/MANIFEST.MF`?

**Question 2.** Does the command `java -cp extra.jar -jar app.jar` guarantee that the application can find classes in `extra.jar`?

**Question 3.** The app manifest has `Class-Path: lib/greeting-lib.jar`. You move `app.jar` to another directory without moving the corresponding `lib` folder. What is the risk?

**Question 4.** `app.jar` contains `module-info.class`. When running `java -jar app.jar`, is `Main.class.getModule().isNamed()` guaranteed to be `true`?

**Question 5.** Two JARs `app.jar` and `greeting-lib.jar` have modules `demo.app` and `demo.greeting`. What information must a modular launch command specify at a minimum?

**Question 6.** For an agent JAR using `-javaagent`, which method does the JVM invoke? How does it differ if the agent JAR uses post-startup attach?

**Question 7.** When an application runs via the module path, must a separate agent JAR be moved onto the module path?

**Question 8.** In the demo, `agentSaw=demo/app/Main module=demo.app`, but is the agent class a member of module `demo.app`?

**Question 9.** Inject `invokestatic demo/agent/TelemetryHelper.record()V` into a method of a bootstrap class. The helper only resides on the system loader. Does generating valid bytecode guarantee the call will work?

**Question 10.** Why shouldn't you assume a JAR containing other JARs inside it will automatically work with the standard Java launcher classpath?

**Question 11.** When building the agent JAR, you package only `PackagingAgent.class` and forget the anonymous transformer class. What can happen at startup?

**Question 12.** If a manifest has `Launcher-Agent-Class`, does the launcher invoke `premain` or `agentmain`, and how does it differ from `-javaagent`?

**Question 13.** With `-cp` on Windows, what is the entry separator? What about on Linux/macOS?

**Question 14.** Each JAR has `module-info.class`, but you place all of them on the class path. Does JPMS enforce the descriptor's `requires` relationships as explicit modules?

**Question 15.** The agent callback always returns `null` as in the demo. Does that mean the agent has modified the bytecode of the target classes?

### Answers

1. `Premain-Class` selects the **agent entrypoint** when using `-javaagent`; `Main-Class` selects the **application entrypoint** when using `-jar`.
2. **No.** With `-jar`, the launcher ignores the classpath specified by `-cp` for user classes; you need manifest `Class-Path` or a different launch mode.
3. The relative library path from `app.jar` breaks, typically causing `NoClassDefFoundError`/class resolution failure.
4. **No.** In the demo, `-jar` places the app into an `unnamed module` even though the JAR has a module descriptor.
5. You need `--module-path` containing the resolvable modules and `--module demo.app/demo.app.Main` or a properly declared main class; the module graph must satisfy `requires demo.greeting`.
6. A startup agent invokes `premain` via `Premain-Class`; an attach agent invokes `agentmain` via `Agent-Class` if supported by the environment.
7. **No.** The agent JAR is still picked up by the JVM via `-javaagent`.
8. **No.** The agent lives in the system loader's unnamed module; the `Module` logged is the **target class's module**.
9. **No.** Bootstrap loader/module access may fail to resolve a helper on the system loader; appropriate visibility must be arranged.
10. The standard Java launcher does not automatically unpack nested JARs as a classpath. Nested JARs require a custom launcher/loader.
11. The agent may miss the class required for the `ClassFileTransformer` implementation and fail before application `main` runs.
12. `Launcher-Agent-Class` invokes **`agentmain` before main** for a co-packaged agent; `-javaagent` invokes `premain` from a standalone agent JAR.
13. Windows: `;`. Linux/macOS: `:`.
14. **No.** A modular JAR on the class path is treated as a non-modular JAR.
15. **No.** It only observes callbacks; `null` means no replacement bytecode is provided at this step.

## 16. Pre-Release Checklist

- [ ] Agent JAR has a valid `Premain-Class` and contains all runtime classes/dependencies of the agent.
- [ ] Application JAR has `Main-Class` if launched as an executable `-jar`.
- [ ] If using manifest `Class-Path`, relative paths from `app.jar` to dependencies remain accurate after deployment.
- [ ] If using `-cp`, the OS-appropriate path separator is chosen; do not mix it up with manifest path syntax.
- [ ] If using JPMS, module descriptors have appropriate `requires/exports` and artifacts are placed on the module path.
- [ ] Do not place the agent JAR on the module path by default just because the app runs modularly.
- [ ] Helpers called by instrumented bytecode have valid loader/module visibility.
- [ ] Do not reload the class currently being transformed from inside the callback.
- [ ] Build with `--release` matching the minimum runtime and test bytecode compatibility with the actual JDK.
- [ ] CI runs the app in the **exact production mode** and verifies agent startup, `main`, library calls, and exit code.
- [ ] Do not confuse `Agent-Class`/`Launcher-Agent-Class` with `Premain-Class`.
- [ ] Release JARs have integrity/version metadata and are tested with the exact directory layout.

## 17. Summary

A **standalone agent JAR** is where the JVM looks for `Premain-Class` and invokes `premain` when it sees `-javaagent`. An **executable application JAR** is where the launcher looks for `Main-Class` and manifest library paths when using `-jar`. The **class path** is the class/resource lookup mechanism for unnamed-module applications. The **module path** creates explicit named modules when combined with `module-info.class` and `--module`.

In the tested example, the same three JARs run successfully with `-jar`, `-cp`, and `--module-path --module`. Business behavior remains identical, while the target module information observed by the agent changes accurately according to the runtime mode. This provides a practical basis for deploying a standalone agent without disrupting application entrypoints, dependency search paths, or JPMS configuration.

## 18. Official References

- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agents, `Premain-Class`/`Agent-Class`/`Launcher-Agent-Class`, system class loader, manifest capabilities, and module visibility.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): syntax for `-javaagent`, `-jar`, `-cp`, `--module-path`, `--module`, and classpath separators.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest, `Main-Class`, `Class-Path` relative URLs, modular/automatic JARs, and `module-info.class`.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks, module/loader/className, meaning of `return null`, and passing bytes between transformers.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registering transformers, bootstrap/system loader search, `redefineModule`, and checking capabilities.
- [Java SE 21 — jar tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): creating JARs with manifests, `--list`, `--describe-module`, and inspecting artifacts.
