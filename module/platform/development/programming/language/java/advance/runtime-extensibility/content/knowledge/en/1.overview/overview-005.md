# Comparing Configuration, Java Plugins, Dynamic Compilation, Scripting, and JShell

In a Java application, "runtime extensibility" can mean very different things: changing a parameter, picking a pre-written handler, adding a new library, receiving Java source code to compile, executing a scripting language, or quickly testing a few lines in JShell. These five approaches solve different needs and have different deployment, testing, and security boundaries.

## 1. The Big Picture: What Actually Changes?

| Approach | Input That Changes Behavior | Typical Java Mechanism | Adds New Logic Without Recompiling the Main App? | Best Suited For |
|---|---|---|---|---|
| **Configuration** | Values, flags, parameters, strategy names | Properties/YAML, environment variables, system properties, app-read config | **No**, if only choosing among existing branches | Changing timeouts, limits, feature flags, selecting existing implementations |
| **Java Plugin** | JAR containing compiled classes and extension contract | Interface/SPI, §ServiceLoader§, class loaders, JPMS | **Yes**: adds built implementations, provided API compatibility holds | Integrating adapters, formats, providers, independent features |
| **Dynamic Java Compilation** | §.java§ source code received while the app is running | §javax.tools.JavaCompiler§, §java.compiler§, class loaders | **Yes**: creates classes from new Java source | Code generation, educational tools, specialized rules needing Java |
| **Scripting** | Script content of an engine-supported language | §javax.script§ / JSR 223 or engine-specific API | **Yes**, within the scope of the installed language/engine | Frequently changing rules, automation, DSLs, glue code |
| **JShell** | Interactively entered Java snippets | §jshell§ tool, §jdk.jshell§ module/API | **Yes** within an evaluation session; not a production plugin by default | Exploring APIs, diagnostics, teaching, prototyping |

**Three types of flexibility should be distinguished:**

- **Changing control data:** configuration selects behavior that has already been coded and released.
- **Adding executable code:** plugins, dynamic compilation, or scripting introduce additional runtime logic into the system; the differences lie in code origin, packaging, and when errors are checked.
- **Interactive experimentation:** JShell lets humans evaluate Java immediately within a working session; it does not by itself provide lifecycle, deployment, or contracts for production plugins.

None of these options automatically guarantees "hot reload". Detecting changes, creating new objects, transitioning states, closing resources, and recovering from errors must be designed explicitly.

## 2. Configuration: Changing Decisions, Not Creating New Algorithms

Configuration is the least complex option when the application already knows the possible handlers. Configuration values can be read at startup, per request, on a refresh schedule, or pushed through an update mechanism. **A configuration file changing does not mean the running program automatically reloads it.**

Java 17 example: selecting a string normalization approach via a system property; both handlers are already compiled.

File §ConfigDemo.java§:

```java
import java.util.Locale;

public class ConfigDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String input);
    }

    public static void main(String[] args) {
        String mode = System.getProperty("format.mode", "identity");

        Formatter formatter = switch (mode) {
            case "identity" -> text -> text;
            case "upper" -> text -> text.toUpperCase(Locale.ROOT);
            default -> throw new IllegalArgumentException(
                    "Unsupported format.mode: " + mode);
        };

        System.out.println(formatter.format("java"));
    }
}
```

Compile and run:

```bash
javac ConfigDemo.java
java ConfigDemo
java -Dformat.mode=upper ConfigDemo
```

The two runs print respectively:

```text
java
JAVA
```

Here §-Dformat.mode=upper§ only selects the §upper§ branch. Adding a language translation algorithm, connecting to a new system, or handling an unknown format still requires deployed code (directly or through another extensibility mechanism).

**Good design:** have clear schemas/defaults; reject invalid values; record configuration versions; refresh atomically if reloading is allowed; avoid using configuration values as arbitrary class names or commands without validation. Configuration is control data, not an arbitrary code execution zone.

## 3. Java Plugins: Adding Compiled Implementations Through a Stable Contract

A plugin implements an **extension point** published by the host application: interfaces, input/output data, error rules, API versioning, and lifecycle. §ServiceLoader§ is Java's built-in SPI mechanism for discovering providers. Libraries such as PF4J or custom plugin frameworks can add lifecycle, version, and isolation management, yet the contract with the application remains the core concern.

### Runnable Example: Loading a Plugin from a JAR via §ServiceLoader§

Create the files with this structure:

```text
src/
  demo/
    api/TextPlugin.java
    app/Main.java
    plugins/UppercasePlugin.java
resources/
  META-INF/
    services/demo.api.TextPlugin
```

§src/demo/api/TextPlugin.java§:

```java
package demo.api;

public interface TextPlugin {
    String name();
    String apply(String input);
}
```

§src/demo/plugins/UppercasePlugin.java§:

```java
package demo.plugins;

import demo.api.TextPlugin;
import java.util.Locale;

public final class UppercasePlugin implements TextPlugin {
    @Override
    public String name() {
        return "uppercase";
    }

    @Override
    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

§src/demo/app/Main.java§:

```java
package demo.app;

import demo.api.TextPlugin;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        boolean found = false;
        for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
            found = true;
            System.out.println(
                    plugin.name() + " = " + plugin.apply("java plugin"));
        }
        if (!found) {
            System.out.println("No plugin found");
        }
    }
}
```

The content of **§resources/META-INF/services/demo.api.TextPlugin§** is literally the provider class name:

```text
demo.plugins.UppercasePlugin
```

From the directory containing §src§ and §resources§, using JDK 17+:

```bash
javac -d app-out src/demo/api/TextPlugin.java src/demo/app/Main.java
javac -cp app-out -d plugin-out src/demo/plugins/UppercasePlugin.java
jar --create --file plugin.jar -C plugin-out . -C resources META-INF/services
```

Run on Windows (classpath uses a semicolon):

```powershell
java -cp "app-out;plugin.jar" demo.app.Main
```

On Linux/macOS (classpath uses a colon):

```bash
java -cp "app-out:plugin.jar" demo.app.Main
```

Both runs print:

```text
uppercase = JAVA PLUGIN
```

**Key point:** the §Main§ application only knows §TextPlugin§; the JAR carries the implementation and the descriptor under §META-INF/services§. The provider must be accessible from the class loader used by §ServiceLoader§. For projects using the Java Platform Module System, you can declare §uses§ and §provides ... with ...§ in §module-info.java§ instead of the classpath service file; module resolution and §exports§/§opens§ grants must be handled separately.

**Practical limits:**

- §ServiceLoader.load(TextPlugin.class)§ discovers providers currently available through the chosen class loader; it **does not automatically watch a JAR folder**, continuously load new JARs, or replace already-loaded classes.
- Loading JARs after the application has started typically requires a custom class loader design and calling §ServiceLoader.load(TextPlugin.class, pluginLoader)§. Updating an implementation requires creating a new loader/instance and routing users to the new version; classes with the same name defined by two different class loaders are still **two distinct types**.
- Keep shared APIs on the parent class loader side, and manage version/compatibility, dependency conflicts, initialization/shutdown, threads, connections, and static references; a loader cannot be garbage-collected while live references remain.
- Third-party plugins are **Java code with full process privileges**, unless isolated outside the JVM. Verify provenance and artifact signatures/hashes, and consider running untrusted plugins in separate processes.

## 4. Dynamic Compilation: Receiving Java Source, Generating Bytecode, and Loading New Classes

Dynamic compilation fits when new logic is expressed as **Java source code**, is more than just parameters, and does not yet exist as classes/JARs. High-level pipeline:

```text
Java source -> JavaCompiler -> .class (bytecode)
            -> class loader -> link with API/contract -> execute
```

§javax.tools.JavaCompiler§ belongs to the §java.compiler§ module, allowing the compiler to be invoked from a Java program. §ToolProvider.getSystemJavaCompiler()§ can return §null§ if the runtime image lacks a compiler; an appropriate JDK environment is required. Successful compilation does not guarantee the class is safe, API-compatible, or free of runtime errors.

### Runnable Java 17 Example: Compiling a Class While the Program Is Running

File §CompileDemo.java§:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class CompileDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("No Java compiler in this runtime");
        }

        Path dir = Files.createTempDirectory("java-dynamic-");
        Path file = dir.resolve("HelloDynamic.java");

        String source = """
                public class HelloDynamic {
                    public static String greet() {
                        return "Compiled at runtime";
                    }
                }
                """;
        Files.writeString(file, source);

        int status = compiler.run(
                null, null, null, "-d", dir.toString(), file.toString());
        if (status != 0) {
            throw new IllegalStateException("Compilation failed: " + status);
        }

        URL[] urls = {dir.toUri().toURL()};
        try (URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader())) {
            Class<?> generated = Class.forName(
                    "HelloDynamic", true, loader);
            Object result = generated.getMethod("greet").invoke(null);
            System.out.println(result);
        }
    }
}
```

Run with JDK 17+:

```bash
javac CompileDemo.java
java CompileDemo
```

Stdout on successful compilation:

```text
Compiled at runtime
```

The example creates source and class files in a temporary directory, then calls the public method via reflection. Real implementations typically need §JavaFileManager§, error diagnostics via §DiagnosticCollector§, a well-defined classpath/module path, shared APIs, versioned caching, and cleanup of temporary artifacts. Compilation can be done entirely in memory using a custom file manager, though JavaCompiler does not perform the class-loading/execution step itself.

**Do not equate "compiles cleanly" with "safe to run":** user-submitted code can read files, make network calls, spawn threads, or invoke native code with process privileges. Class loaders, syntax checks, per-method timeouts, or §SecurityManager§ are not reliable barriers for untrusted code. If arbitrary Java truly must run, use a process/container with OS-level restrictions on permissions, CPU, memory, time, and network; design stop paths and resource reclamation.

## 5. Scripting: Interpreting/Running Scripts Through an Engine

Scripting is suitable when authors need to edit rules or formulas frequently without building a JAR for every change. Java provides the standard §javax.script§ (JSR 223) API: look up an engine, pass variables via §Bindings§, call §eval§, and receive the result. **Having the API does not mean an engine is built in for every language.**

Specifically, **the Nashorn JavaScript engine was removed from the JDK as of JDK 15**. A standard JDK 17 does not include an engine named §JavaScript§ for §ScriptEngineManager§ to find. To run JavaScript, Groovy, or other languages, you must add a compatible engine and its required dependencies, or use the engine's native API.

File §ScriptDemo.java§:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class ScriptDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngine engine =
                new ScriptEngineManager().getEngineByName("JavaScript");

        if (engine == null) {
            System.out.println("No JavaScript engine installed");
            return;
        }

        engine.put("amount", 40);
        Object result = engine.eval("amount + 2");
        System.out.println(result);
    }
}
```

Compile/run:

```bash
javac ScriptDemo.java
java ScriptDemo
```

On JDK 17 **without an additional engine installed**, stdout:

```text
No JavaScript engine installed
```

If a compatible JavaScript engine is added, the §eval§ branch executes; return types and number formatting depend on the engine, so do not assume uniform stdout across all engines. For production scripts, clearly specify allowed APIs, input/output types, engine version, error policies, timeouts, auditing, and script update procedures. If only a narrow rule language is needed, a DSL/expression evaluator with restricted syntax and operators is often easier to control for end users.

**Operational warning:** depending on the engine and configuration, scripts allowed to call Java/IO or host APIs can be as powerful as plugin code. Restricting variables passed into §Bindings§ alone is not a sufficient sandbox. Do not run untrusted scripts inside a business process holding sensitive privileges without proper isolation.

## 6. JShell: Java REPL for Experimentation, Not a Default Script Engine

§jshell§ is the **Read–Eval–Print Loop** tool introduced in Java 9: enter expressions, variable declarations, methods, or classes and receive feedback without creating a Java project beforehand. Unlike a JavaScript script engine, JShell evaluates **Java snippets**. It is useful for learning APIs, testing hypotheses, and quick debugging.

Example in a terminal with JDK 17+:

```text
$ jshell
jshell> int base = 40;
jshell> System.out.println(base + 2);
42
jshell> /exit
```

The line §42§ is stdout from §System.out.println§; JShell's prompts/feedback may vary by configuration and version. JShell also provides commands like §/help§, §/vars§, §/methods§, §/open§, and §/save§. When embedding into an application is needed, the §jdk.jshell§ module provides the §jdk.jshell.JShell§ API to evaluate snippets and observe results/events.

How it differs from dynamic Java compilation with §JavaCompiler§: JShell supports an interactive loop and snippet state across multiple inputs, with its own rules for declaring/modifying/replacing snippets. It does not replace a build system, version repository, plugin contract, dependency resolution, or safe update mechanism. Using JShell to "let customers enter Java and run it" still raises the same code-trust issues as dynamic compilation and execution.

## 7. Which One Should You Choose Based on Need?

| Scenario | Preferred Choice | Reason and Conditions |
|---|---|---|
| Changing endpoints, timeouts, log levels, toggling an existing feature | **Configuration** | Changes data; may need restart/reload depending on app design |
| Picking one of several pre-coded algorithms per tenant | **Configuration + Strategy** | No plugin needed if the algorithm set is closed and rarely changes |
| Third party supplies a data-export adapter as a JAR | **Java Plugin** | Publish interface/SPI, API versioning, packaging and testing workflow |
| Loading new providers in a live request-serving system | **Plugin + custom loader/lifecycle** | §ServiceLoader§ alone does not solve hot reload, version switching, or leaks |
| Tool generating Java classes from a schema at runtime | **Dynamic Compilation** | Has Java source; must handle compiler errors and class loading |
| Operators tweaking short business rules multiple times a day | **Scripting or controlled DSL** | Needs a small language, updates/versioning/auditing; full Java not necessarily needed |
| Engineer wants to try an API and inspect results of a few lines | **JShell** | Suited for interactive sessions and learning |
| Letting untrusted users run code on a server | **Establish security boundaries before picking a mechanism** | None of the five approaches provides a reliable sandbox on its own |

A short decision tree:

```text
Need to add unpackaged algorithms?
├─ No -> Configuration; can choose a compiled Strategy
└─ Yes
   ├─ Already have a JAR following an extension API -> Java Plugin
   ├─ Have Java source needing compilation -> JavaCompiler + class loader
   ├─ Have a script for an engine/DSL -> Scripting
   └─ Only interactive Java experimentation -> JShell
```

This decision tree categorizes by input nature; trust level and isolation requirements may force a different choice even for the same input type.

## 8. Combining Them in an Extensible Architecture

In large products, these approaches can **complement one another**:

1. The application publishes §TextPlugin§ (a stable API); some implementations are built in, while others come from external JARs.
2. §ServiceLoader§ or a plugin registry discovers providers and manages versions and readiness states.
3. Configuration §transform.provider=uppercase§ selects an available provider. Changing configuration only changes the selection; adding a new provider still requires a JAR and loading workflow.
4. When business needs genuinely demand flexible rules, a dedicated provider can invoke a managed DSL/script engine. That does not turn every plugin into a script.
5. JShell is for engineers testing APIs or investigating issues in controlled environments, not on the end-user request path.
6. If Java source is accepted, dynamic compilation is a separate pipeline; test and isolate artifacts before letting compiled output participate in the live system.

Example deployment flow:

```text
Configuration selects provider
        |
        v
Plugin registry --(shared SPI/API)--> Built Java plugin
        |                               |
        |                               +--> business processing
        +--> provider running DSL (if engine exists)
        |
        +--> provider generated from Java source (if separate compile pipeline exists)

JShell: exploratory/diagnostics tool outside the main processing flow
```

To "swap behavior without restarting", you also need version-management mechanics: build the new version alongside the old one, run health checks, route new requests to the new version, let old requests finish, close resources, and support rollback. Do not directly mutate loaded classes or expect replacing a JAR on disk to immediately replace running bytecode.

## 9. Important Trade-Off Axes

### Complexity and Performance

- **Configuration:** cheapest to deploy and test; changes typically affect only branch/value selection, though reload mechanisms must be synchronized and handle malformed configs.
- **Plugins:** class-loading/initialization cost depends on provider count and dependencies; once loaded, regular interface calls perform comparably to other Java code. Compatibility and lifecycle must be maintained.
- **Dynamic compilation:** incurs CPU/memory cost for compilation, compiler errors, and file/class-loader management. Do not recompile the same source on every request; cache by hash/version and publish tested artifacts.
- **Scripting:** depends on the engine, eval/compile/cache mode, and JVM interaction. Can incur parsing/interpretation overhead; one cannot conclude every script is slower than Java without benchmarking actual workloads.
- **JShell:** optimized for interactive user feedback, not intended as a high-throughput transactional execution path; maintaining snippet state also requires resource control.

### Security, Testing, and Governance

| Area to Check | Configuration | Plugin | Dynamic Compilation | Scripting | JShell |
|---|---|---|---|---|---|
| Input validation | Schema, types, bounds | Manifest, API, provenance | Source/policy/diagnostics | Script/policy/engine | User/session/snippet |
| Version compatibility | Config schema | API/ABI, dependencies, JPMS | Compiler options, classpath | Engine + host API | JDK/module version |
| Rollback | Previous config | Previous JAR/registry | Previous artifact/class loader | Previous script version | Reinitialize session |
| Untrusted code isolation | Usually introduces no new code | Needs process isolation | Needs process isolation | Needs process isolation if scripts are powerful | Needs process isolation |
| Error observability | Validation/reload logs | Provider id, init, timeout | Diagnostics + runtime trace | Script id, engine, stack trace | Snippet status/events |

**Design rule:** log the *exact executing version* (config revision, plugin id/version, source/class hash, script id/version); bound resources; apply appropriate circuit breakers/timeouts; do not let plugin suppliers hold secrets or internal dependencies outside the contract; separate loading errors, compilation errors, and execution errors.

## 10. Common Misconceptions

1. **"Changing YAML adds new logic."** False: YAML only holds data; new logic must be built/loaded or processed by an executable engine.
2. **"`ServiceLoader` is hot swap."** False: SPI discovers providers; it does not update JARs, swap implementations of live objects, or reclaim class loaders.
3. **"Class loaders are a sandbox."** False: they isolate namespaces and support class loading; they do not inherently block file, network, thread, or native access by loaded code.
4. **"`JavaCompiler` runs code immediately."** False: the compiler produces classes/diagnostics; execution requires loading the class and invoking a method under a contract.
5. **"Java 17 includes JavaScript out of the box via `javax.script`."** False for standard JDK 17: the API exists, but Nashorn is gone; a corresponding engine must be installed.
6. **"JShell and JavaScript are the same thing."** False: JShell evaluates **Java** snippets, whereas JavaScript is a different language requiring its own runtime/engine.
7. **"Running scripts or snippets is harmless compared to plugins."** False: risk depends on actual privileges and host access; extensions can cause errors, leak data, or exhaust resources.
8. **"Adding plugins means no deployment is needed."** Not necessarily: if the app only scans the classpath at startup, you must deploy the JAR and restart; live plugin loading is a feature you must actively build.
9. **"The most flexible option is always best."** No: every mechanism adds error surface, version governance, and security burden. Choose the simplest mechanism that still supports the needed axis of change.

**Takeaway:** configuration **selects** existing behavior; plugins **plug in** pre-built Java bytecode via an API; dynamic compilation **produces** bytecode from Java source; scripting **evaluates** programs with an engine; JShell **experiments** with Java interactively. Identify the changing input and trust boundaries before choosing the tool.