# Agent Classes Are Loaded by the System Class Loader and Belong to an Unnamed Module

> **Context:** Java Advance → Instrumentation → **Class loaders and helpers**. According to the `java.lang.instrument` package specification, classes in an agent JAR are loaded by the **system class loader**, and belong to the **unnamed module of the system loader**. These are two distinct properties: the *defining class loader* determines class identity and class visibility; *module membership* participates in readability, exports, and opens rules. This article uses Java 17+, with an agent running alongside both a classpath application and a named-module application, while also pointing out the consequences for designing helpers.

## 1. Exact Statement from the Specification

In the Java instrumentation mechanism:

1. The JVM uses the agent JAR declared via `-javaagent:...` to locate the class specified by the `Premain-Class` manifest attribute, loads the agent class, and then invokes `premain` **before** the application's `main`.
2. If the JVM supports starting an agent in a running process, the manifest uses `Agent-Class` and the JVM invokes `agentmain`. Regardless of which entry point is invoked, the loading section in `java.lang.instrument` specifies that classes from the agent JAR belong to the **system loader and the unnamed module of this loader**.
3. The system class loader **usually** also defines the application's main class, but the application may run with a classpath, a **named module**, or custom loaders. Do not infer the module of the main class solely from the fact that the main class is defined by the system loader.
4. A class loader is not equated with a single module: one loader can define classes in an unnamed module **and** in named modules. Each `Class<?>` is associated with a specific `Module`, and in the JVM, class identity is based on **binary name + defining loader**.

Comparison:

| Example class | Defining loader | Module |
|---|---|---|
| `demo.agent.ProbeAgent` loaded via `-javaagent` | **system** | **unnamed module of system** |
| `demo.agent.AgentHelper` in the same agent JAR, used as a normal class | **system** | **unnamed module of system** |
| `demo.app.LoaderDemo` run from classpath | **system** in a standard launcher | **unnamed module of system** |
| `demo.named.NamedMain` run from `-m demo.named/...` | **system** in the test example | **named module `demo.named`** |
| `java.lang.String` | **bootstrap**, Java API represents the loader as `null` | **named module `java.base`** |
| `java.lang.instrument.Instrumentation` | defined by the JDK runtime | **named module `java.instrument`** |

In particular, `ProbeAgent` importing `Instrumentation` does **not** make `ProbeAgent` a member of the `java.instrument` module. Imports/type references do not determine the module containing the caller class.

## 2. Distinguishing Class Loader, Module, and Package

**Class loader** answers: which object defined the class? In Java there are:

- **Bootstrap class loader:** creates foundational classes; `String.class.getClassLoader() == null` is a valid representation, not an error.
- **Platform class loader:** participates in loading certain platform modules in modern JDKs.
- **System/application class loader:** the default loader for classpath applications and Java instrumentation agents. Can be obtained via `ClassLoader.getSystemClassLoader()`.
- **Custom loaders:** such as `URLClassLoader`, plugin loaders, and application-server loaders. Classes defined by them are not automatically visible in reverse from the system loader.

**Module** answers: which module unit does the class belong to, and what are its read/export/open relationships?

~~~java
ClassLoader loader = SomeType.class.getClassLoader();
Module module = SomeType.class.getModule();
System.out.println(loader == ClassLoader.getSystemClassLoader());
System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

This is a **code snippet inside an existing class `SomeType`**, not a standalone program. `module.isNamed() == false` means the class is in an unnamed module; `module.getName() == null`. A class in `package demo.agent` still has a **named package**, even though its module is **unnamed**. “Unnamed package” is a different matter, applying only when Java source does not declare a `package`.

Each class loader has **its own unnamed module**. Two classes in two loaders that both have `module.isNamed() == false` do not necessarily belong to the **same `Module` object**. Use `moduleA == moduleB` to check for the same module; use `classA.getClassLoader() == classB.getClassLoader()` to check the defining loader.

### Readability, exports, and opens

- An unnamed module reads **the modules that have been resolved/are observable** in the module graph. However, it **does not automatically make packages of other named modules exported/opened**.
- **Readability:** can module A read module B? Use `moduleA.canRead(moduleB)` to partially diagnose the issue.
- **Exports:** does the package allow using public types/members from another module? Having only a read edge may not be enough.
- **Opens:** is the package open for deep reflection? Simply reading a module or importing a class is not enough to call `setAccessible(true)` on a private member of an unopened package.

Therefore, an agent in an unnamed module can use the public API of `java.instrument`, but does not automatically have deep reflection access to all internal packages of `java.base` or application modules. When genuinely needed, design explicit access using `--add-modules` (resolve required modules), `--add-exports` (public API packages), `--add-opens` (deep reflection), or `Instrumentation.redefineModule(...)` within permitted conditions and scope. Do not treat `--add-opens` as a general measure to “fix all class loader errors”.

### Illustrative Diagram

~~~text
Bootstrap loader (Java API represents as null)
  ├── java.lang.String          -> named module java.base
  │
  └── Platform loader
       │
       └── System loader
            ├── ProbeAgent     -> unnamed module of system
            ├── AgentHelper    -> unnamed module of system
            ├── LoaderDemo     -> unnamed module of system (classpath)
            └── NamedMain      -> named module demo.named
~~~

This is a diagram of a **typical JDK launcher case**, not a guarantee that every class in every JDK has the same loader. The key point is that **the same system loader can still contain classes in different modules**.

## 3. How Does the JVM Load the Agent and Find Helpers?

With the command:

~~~bash
java -javaagent:out/probe-agent.jar=demo -cp out/app demo.app.LoaderDemo
~~~

The JVM executes the following logical sequence:

~~~text
JVM receives option -javaagent:path.jar[=options]
   └─ reads META-INF/MANIFEST.MF
      └─ Premain-Class: demo.agent.ProbeAgent
         └─ adds agent JAR to the system loader's class lookup mechanism
            └─ loads ProbeAgent in the unnamed module of system
               └─ invokes static premain("demo", Instrumentation)
                  └─ agent can call AgentHelper from the same agent JAR
                     └─ JVM proceeds to invoke LoaderDemo.main()
~~~

The agent JAR **does not need** to be listed again in `-cp` for the JVM to invoke `premain`. In typical experiments, the classpath app can also use the system loader to **find** the agent class once the agent JAR has been added to the system lookup. However, this must not be turned into an API dependency of business code: when the agent is not enabled, that class will not exist; and a **named module** application still has module readability constraints when linking directly to an unnamed module.

Note: **the ability to find a class** is not equivalent to **the ability to access types/methods by module rules**, and even less does it guarantee that the same module/classloader sees all classes of plugin loaders.

### Entry Point and Manifest

The manifest of a startup agent requires:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ProbeAgent

~~~

The name `demo.agent.ProbeAgent` is a Java binary name, not a file path `demo/agent/ProbeAgent.class`. The method selected first is:

~~~java
public static void premain(String agentArgs,
                           java.lang.instrument.Instrumentation inst)
~~~

There is a single-parameter overload `premain(String)` as a fallback per the package specification. On the dynamic agent path, the entry point is `agentmain` and the manifest requires `Agent-Class`; an agent JAR can declare both `Premain-Class` and `Agent-Class`. The Attach API is not needed in this experiment.

## 4. Java 17+ Practice — Agent Class, Helper, and Classpath App

Try two runs **without** and **with** `-javaagent`. The agent and app are compiled separately so that the app has no compile-time dependency on the agent.

### 4.1 Project Structure

~~~text
agent-loader-lab/
├── manifest.mf
├── src/
│   └── demo/
│       ├── agent/
│       │   ├── ProbeAgent.java
│       │   └── AgentHelper.java
│       └── app/
│           └── LoaderDemo.java
└── out/                        # generated on build
    ├── agent/
    ├── app/
    └── probe-agent.jar
~~~

Requires JDK 17+, with `java`, `javac`, and `jar` commands. Run all commands from the **root directory `agent-loader-lab/`**.

### 4.2 File `src/demo/agent/ProbeAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class ProbeAgent {
    private ProbeAgent() {}

    public static void premain(String options, Instrumentation instrumentation) {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("[AGENT] loaderSystem="
                + (ProbeAgent.class.getClassLoader() == system));
        System.out.println("[AGENT] moduleNamed="
                + ProbeAgent.class.getModule().isNamed());
        System.out.println("[AGENT] readsJavaInstrument="
                + ProbeAgent.class.getModule().canRead(
                        Instrumentation.class.getModule()));
        System.out.println("[AGENT] helperSameModule="
                + (ProbeAgent.class.getModule() == AgentHelper.class.getModule()));

        AgentHelper.report();
    }
}
~~~

Here we compare **loader identity** using `==` instead of printing the loader's implementation name (for example, the name `AppClassLoader` should not be hard-coded). `getModule().isNamed()` returns `false` for the agent. The `instrumentation` parameter is received via the API but not yet used to transform bytecode; this class only observes the loader/module.

### 4.3 File `src/demo/agent/AgentHelper.java`

~~~java
package demo.agent;

final class AgentHelper {
    private AgentHelper() {}

    static void report() {
        System.out.println("[HELPER] loaderSystem="
                + (AgentHelper.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));
    }
}
~~~

The helper is a package-private class in the **same agent JAR**. It is not loaded by the bootstrap loader just because the file name contains the word “Agent”; the JVM uses the class loader visible to `ProbeAgent`. There is no need to declare `Premain-Class` for the helper.

### 4.4 File `src/demo/app/LoaderDemo.java`

~~~java
package demo.app;

public final class LoaderDemo {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("[APP] loaderSystem="
                + (LoaderDemo.class.getClassLoader() == system));
        System.out.println("[APP] moduleNamed="
                + LoaderDemo.class.getModule().isNamed());

        try {
            Class<?> agent = Class.forName(
                    "demo.agent.ProbeAgent", false, system);
            System.out.println("[APP] agentVisible="
                    + (agent.getClassLoader() == system));
        } catch (ClassNotFoundException e) {
            System.out.println("[APP] agentVisible=false");
        }

        System.out.println("[APP] stringLoaderBootstrap="
                + (String.class.getClassLoader() == null));
        System.out.println("[APP] stringModule="
                + String.class.getModule().getName());
    }
}
~~~

The app does not import `ProbeAgent`. `Class.forName("...", false, system)` checks whether the system can find the class by name **without attempting to run the static initializer** just for diagnostics. Do not conclude that a named-module caller always has a read edge to the agent simply because `Class.forName` succeeds.

### 4.5 Manifest and Build

Create `manifest.mf` with a trailing blank line:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ProbeAgent

~~~

**macOS/Linux (Bash):**

~~~bash
mkdir -p out/agent out/app
javac --release 17 -d out/agent src/demo/agent/ProbeAgent.java src/demo/agent/AgentHelper.java
javac --release 17 -d out/app src/demo/app/LoaderDemo.java
jar --create --file out/probe-agent.jar --manifest manifest.mf -C out/agent .
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent, out/app | Out-Null
javac --release 17 -d out/agent src/demo/agent/ProbeAgent.java src/demo/agent/AgentHelper.java
javac --release 17 -d out/app src/demo/app/LoaderDemo.java
jar --create --file out/probe-agent.jar --manifest manifest.mf -C out/agent .
~~~

Inspect the JAR contents:

~~~bash
jar --list --file out/probe-agent.jar
~~~

The JAR must contain `META-INF/MANIFEST.MF`, `demo/agent/ProbeAgent.class`, and `demo/agent/AgentHelper.class`. The application is compiled independently into `out/app`; there is no need to include `out/agent` in `-cp` when running.

### 4.6 Running Without the Agent

~~~bash
java -cp out/app demo.app.LoaderDemo
~~~

**Verified stdout when running Java 17 bytecode on OpenJDK 24:**

~~~text
[APP] loaderSystem=true
[APP] moduleNamed=false
[APP] agentVisible=false
[APP] stringLoaderBootstrap=true
[APP] stringModule=java.base
~~~

The application class is on the classpath, so it belongs to the unnamed module of the system loader. The agent JAR is neither on the classpath nor activated, so `Class.forName` throws `ClassNotFoundException` and the app prints `agentVisible=false`.

### 4.7 Running With the Startup Agent

**macOS/Linux:**

~~~bash
java -javaagent:out/probe-agent.jar=demo -cp out/app demo.app.LoaderDemo
~~~

**Windows PowerShell:**

~~~powershell
java "-javaagent:out/probe-agent.jar=demo" -cp out/app demo.app.LoaderDemo
~~~

**Verified stdout:**

~~~text
[AGENT] loaderSystem=true
[AGENT] moduleNamed=false
[AGENT] readsJavaInstrument=true
[AGENT] helperSameModule=true
[HELPER] loaderSystem=true
[APP] loaderSystem=true
[APP] moduleNamed=false
[APP] agentVisible=true
[APP] stringLoaderBootstrap=true
[APP] stringModule=java.base
~~~

Four observations:

1. The agent runs before the app thanks to `premain`.
2. The agent class and helper are defined by the system loader and share the same **unnamed module**.
3. The agent module reads `java.instrument`, but it is not the `java.instrument` module.
4. The classpath app can find the agent's class using the system loader, even though `-cp` only lists `out/app`. Runtime visibility is **not** a reason to let business code arbitrarily depend on the agent.

The reference point `String.class.getClassLoader() == null` and module `java.base` also emphasize that the bootstrap loader is not synonymous with an unnamed module.

## 5. Java 17+ Practice — A Named Module Can Still Use the System Loader

Extend the project with a new module app:

~~~text
agent-loader-lab/
└── named-src/
    └── demo.named/
        ├── module-info.java
        └── demo/
            └── named/
                └── NamedMain.java
~~~

`named-src/demo.named/module-info.java`:

~~~java
module demo.named { }
~~~

`named-src/demo.named/demo/named/NamedMain.java`:

~~~java
package demo.named;

public final class NamedMain {
    public static void main(String[] args) {
        System.out.println("[NAMED] loaderSystem="
                + (NamedMain.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader()));
        System.out.println("[NAMED] moduleName="
                + NamedMain.class.getModule().getName());
    }
}
~~~

Compile on Bash or PowerShell:

~~~bash
javac --release 17 --module-source-path named-src -d out/mods -m demo.named
~~~

**macOS/Linux:**

~~~bash
java -javaagent:out/probe-agent.jar=module --module-path out/mods -m demo.named/demo.named.NamedMain
~~~

**Windows PowerShell:**

~~~powershell
java "-javaagent:out/probe-agent.jar=module" --module-path out/mods -m demo.named/demo.named.NamedMain
~~~

**Verified stdout:**

~~~text
[AGENT] loaderSystem=true
[AGENT] moduleNamed=false
[AGENT] readsJavaInstrument=true
[AGENT] helperSameModule=true
[HELPER] loaderSystem=true
[NAMED] loaderSystem=true
[NAMED] moduleName=demo.named
~~~

This is a very clear counterexample: `ProbeAgent` and `NamedMain` **share the same system loader**, but belong to **different modules**. The agent is in an unnamed module; the app is in the named module `demo.named`.

If a named-module app wants to **link directly** to the agent's API, it cannot write `requires <unnamed>` in `module-info.java` because that module has no name. Instead, design an appropriately named **shared API module** or an explicit integration mechanism. Having loaded the agent with the system loader does not automatically create a module dependency for all application sources.

Placing a regular JAR on the **module path** is also different from passing it to the **`-javaagent`** option. A library placed on the module path can become an **automatic named module**, whereas an **agent class** launched via Java instrumentation still follows the contract of being loaded into the **system-loader unnamed module**.

## 6. Who Can Use a Helper Placed in the System Loader?

A startup agent typically contains:

- **Agent implementation:** `premain`, transformer, configuration, telemetry.
- **System helper:** recorder, formatter, exporter called from the agent or from target classes that the system loader can resolve.
- **Bootstrap helper:** a minimal bridge called by code injected into bootstrap-defined classes such as `java.base`.

Do not mix these three role layers.

### An Agent in the System Loader Cannot See All Other Class Loaders

A transformer has a callback of the form:

~~~java
byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] bytes);
~~~

This is a **reference signature**, not standalone Java code. The `loader` parameter indicates the **defining loader of the target class**, which may be `null` for bootstrap, the system loader, or a custom/plugin loader. It is **not required to be the same** as `ProbeAgent.class.getClassLoader()`.

Example:

~~~text
ProbeAgent in system loader
   |
   ├── transform(app class A)         loader = system
   ├── transform(plugin class B)      loader = plugin loader
   └── transform(java.base class C)   loader = null (bootstrap)
~~~

The system loader normally does not look up classes defined by a child plugin loader in reverse. `Class.forName("plugin.Type")` inside the agent can fail even when `plugin.Type` already exists. Inside the callback, one should also avoid using `Class.forName(className)` to load **the very class currently being transformed**: recursive class loading can cause `LinkageError`, circular waits, or deadlocks.

### A Bootstrap-Defined Target Does Not Automatically See a System-Only Helper

If a transformer alters the bytecode of a bootstrap class so that it calls:

~~~text
java.base target class (bootstrap)
   └── call to demo.agent.AgentHelper (only in system loader)
       └── bootstrap loader does not look downward into system loader
           └── NoClassDefFoundError / linkage failure
~~~

This is a **classloader visibility** issue; it is not automatically resolved just because the agent belongs to an unnamed module or runs before `main`. Placing a helper in the system loader is sufficient for some targets, but **not sufficient** for all bootstrap classes.

### Bootstrap Helpers Must Be Arranged Separately

Java Instrumentation provides:

- Manifest `Boot-Class-Path` with search paths appended to the bootstrap loader.
- `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` for the agent to add a JAR to the bootstrap loader's search.

Snippet **illustrating inside an agent that already has the `inst` variable**, not a standalone file:

~~~java
import java.util.jar.JarFile;

inst.appendToBootstrapClassLoaderSearch(
        new JarFile("/absolute/path/bootstrap-helper.jar"));
~~~

Important rules:

1. Only put the minimal helper genuinely defined for bootstrap into that JAR, in a **uniquely named package**, without colliding with application class names.
2. The bootstrap helper may only link to classes that the **bootstrap loader can define**. Do not make it directly depend on the agent implementation that exists only in the system loader.
3. The bootstrap helper is in the **unnamed module of the bootstrap loader**, not the unnamed module of the system loader. These two unnamed modules are **not the same object**.
4. Appending a JAR does not automatically redefine already-loaded classes. If the JVM has already failed resolution for a symbolic reference, adding the class file later **does not guarantee** that a subsequent resolution will succeed according to the JVMS.
5. Use bootstrap injection in a controlled manner; do not put the entire agent JAR or unnecessary dependencies into the bootstrap search. Doing so easily causes class/resource conflicts and hard-to-diagnose `IllegalAccessError` failures.

### `appendToSystemClassLoaderSearch` Is a Different API

~~~java
inst.appendToSystemClassLoaderSearch(
        new JarFile("/absolute/path/system-helper.jar"));
~~~

This API adds a JAR to the **system loader search**, not the bootstrap loader. According to the Javadoc, it **does not modify the `java.class.path` property**. A custom system loader must support the `appendToClassPathForInstrumentation(String)` method so the JVM can append the agent JAR/helper JAR; otherwise, `appendToSystemClassLoaderSearch` may throw `UnsupportedOperationException` or agent startup may fail.

When running with a custom system loader (for example configured with `-Djava.system.class.loader=...`), do not hard-code the implementation class name `AppClassLoader`; use an identity check and verify the exact behavior of `appendToClassPathForInstrumentation`.

## 7. JPMS: An Agent Unnamed Module Does Not Mean Every Package Is Open

There are three independent questions:

1. **Where is the agent loaded?** The system class loader / its unnamed module.
2. **Can the instrumented code resolve the helper?** Depends on the target's defining loader and where the helper is placed.
3. **Can the agent access/reflect into classes in other named modules?** Depends on module readability, package exports/opens, and Java access controls.

The Java instrumentation package specification has a notable provision: the JVM **arranges for the module of a transformed class to read the unnamed module of the bootstrap loader and the unnamed module of the loader containing the main agent class**. This read edge allows instrumented classes to reference helpers in the relevant unnamed modules. However:

- Readability does **not** make the bootstrap loader look down into the system loader; the helper must still reside where the target loader can resolve it.
- Readability does **not** automatically open private packages of a named module for the agent to use deep reflection.
- A named-module application must not be assumed to already have a read edge to the agent simply because an agent JAR is present. Distinguish classes actually processed by the transformer from other app classes.
- An agent in an unnamed module can read resolved modules, which does **not** mean every module present in the runtime image has been included in the boot layer. If an optional JDK module is needed, `--add-modules` may be required.

If reflective access is genuinely needed, use an explicitly designed approach (`opens` configuration, `--add-opens`, or `Instrumentation.redefineModule`), avoiding opening too broadly without a requirement.

## 8. Diagnosing Classloader and Module Errors

| Symptom | Common Cause | How to Check |
|---|---|---|
| JVM stops before `main` because agent is not found | Wrong JAR/manifest/`Premain-Class` | Use `jar --list --file ...`, verify binary name and `public static premain` |
| Agent runs but cannot find plugin class | Plugin is defined by a custom loader; system loader does not look downward | Log `type.getClassLoader()`/loader in the transformer |
| Bootstrap class throws `NoClassDefFoundError` after instrumentation | Bytecode calls a helper that resides only in the system loader | Place a minimal bootstrap helper, check module/visibility |
| Helper is loaded but reports `IllegalAccessError` | Wrong Java/module/package access or class identity | Check modifiers, loader, module exports/opens |
| Reflection throws `InaccessibleObjectException` | Named module does not open the package to the agent | Check `--add-opens` or `redefineModule` with appropriate scope |
| App module is in system loader yet `isNamed() == true` | App is run as a named module | This is valid behavior; check `getModule().getName()` |
| `Class.forName(...)` fails even though JAR was appended | Wrong loader, class already failed resolution, wrong name, or JAR not in the right search | Verify name, launcher, load order, and append API |
| `ClassCastException` between types with the same name | Different defining loaders create different class identities | Print binary name, defining loader, and module |
| Agent does not see a JDK module | Module is not resolved into the current graph | Check `--add-modules`, runtime image, and boot layer |
| Custom system loader causes agent/startup failure | Loader does not support instrumentation appending | Check `java.system.class.loader` and `appendToClassPathForInstrumentation` |
| Helper JAR is appended but classpath property is unchanged | Append API does not modify `java.class.path` | Check actual class lookup, not just the property text |

**Misconceptions to avoid:** “System loader is always equivalent to unnamed module” (false), “Agent is in the system loader so bootstrap classes can automatically call helpers” (false), “Unnamed module allows reflection on all packages” (false), and “being able to instrument a class in a custom loader means the agent can `Class.forName` any class from that loader” (false).

## 9. Self-Check Questions

1. **Which loader/module is an agent JAR loaded via `-javaagent` placed in?** The system class loader, **the unnamed module of that loader**.
2. **Do application classes defined by the system loader necessarily belong to an unnamed module?** No. A named app module can be defined by the same loader.
3. **What does `ProbeAgent.class.getModule().getName()` usually return?** `null` because it is an unnamed module; `module.isNamed() == false`.
4. **What does `Instrumentation.class.getModule().getName()` return?** `java.instrument`; not the agent's module name.
5. **What is `getClassLoader()` for a bootstrap-defined class?** `null` in the Java API; that does not mean its module is unnamed.
6. **Does the agent and app sharing the same unnamed module mean the app must import the agent?** No. Ideally, the business app has no direct dependency on the agent.
7. **Is a helper from the same agent JAR automatically loaded by the bootstrap loader?** No. A normal helper resides in the system loader; a bootstrap helper requires a separate search mechanism.
8. **Can the target's named module read the agent's unnamed module after being transformed?** Instrumentation has a mechanism to add a read edge for the module of transformed classes; classloader visibility and exports/opens must still be considered.
9. **Is `canRead == true` alone enough for deep reflection into a private field of a named module?** No. Package opens and access rules must also be satisfied.
10. **Does the system loader automatically look down into child plugin loaders?** Not under normal parent delegation.
11. **Why can't two classes with the same name in two different loaders be cast to each other?** They are two distinct class identities.
12. **When appending a JAR to the system search, is `java.class.path` always modified?** No; `appendToSystemClassLoaderSearch` does not modify that property.

## 10. Checklist for Production Agents

- [ ] Manifest has the correct `Premain-Class` / `Agent-Class` and supported entry points.
- [ ] Verify loader with `== ClassLoader.getSystemClassLoader()`, and module with `getModule().isNamed()`.
- [ ] Distinguish named vs. unnamed **modules**, without relying on `ClassLoader` or package names.
- [ ] Place agent implementation/system helpers and bootstrap helpers in the appropriate loaders.
- [ ] Keep bootstrap helpers minimal, without linking back to system-only code.
- [ ] Do not accidentally depend on the agent JAR from business code.
- [ ] In transformers, distinguish the target's defining loader from the agent's loader.
- [ ] Inspect readability, exports, opens, and classloader lookup separately when `IllegalAccessError`/`NoClassDefFoundError` occurs.
- [ ] Check custom system loaders and `appendToClassPathForInstrumentation` when the runtime uses special configurations.
- [ ] Do not treat the `java.class.path` property as the entire runtime search path.
- [ ] Test with classpath apps, named modules, and bootstrap targets if the agent supports them.
- [ ] Use dedicated packages and manage class name collisions/dependencies.

## Official References

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): loading agent classes, system loader/unnamed module, class visibility, bootstrap helpers, and module reads for transformed classes.
- [Java SE 21 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, `redefineModule`.
- [Java SE 21 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): system/parent/bootstrap loaders, custom loaders.
- [JLS 21 — §7.7.5 Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.5): module readability, exports/opens, and unnamed modules.
- [Dev.java — Unnamed Module](https://dev.java/learn/organizing/modules/unnamed-module/): relationship between the classpath and unnamed modules.
- [Dev.java — `--add-exports` and `--add-opens`](https://dev.java/learn/organizing/modules/add-exports-opens/): distinguishing public API visibility and deep reflection.
