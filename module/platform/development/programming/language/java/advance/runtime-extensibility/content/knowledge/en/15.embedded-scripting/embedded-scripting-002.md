# Discovering ScriptEngineFactory via ScriptEngineManager and the Right Class Loader

## 1. Why Embedded Scripting Systems Need the Right Class Loader

The Java Scripting API (JSR 223, package `javax.script`) lets a host discover and use script engines supplied as plugins. The host typically uses `ScriptEngineManager` to enumerate `ScriptEngineFactory` instances, then create a `ScriptEngine` and evaluate scripts. The key point is that **the engine implementation must be visible from the class loader the manager uses to discover providers**.

In a plugin system with dedicated loaders, an engine JAR may exist on disk yet still not appear if the manager was created with a different loader. This is not necessarily a bug in the engine: the discovered factory list depends on the runtime class path, module graph/layer, SPI metadata, and loader.

**Version note:** Java 17+ provides the `javax.script` API in the `java.scripting` module, but does not guarantee any default language engine. Nashorn, which used to ship in older JDKs, was removed from the JDK starting in Java 15. For example, calling `getEngineByName("JavaScript")` on plain JDK 17 typically returns `null`, unless a compatible JSR 223 engine has been installed.

## 2. Key Objects

| API | Purpose |
|---|---|
| `ScriptEngineManager` | Discovers, registers, and looks up engine factories; maintains global bindings used for engines created through the manager |
| `ScriptEngineFactory` | Describes the language/engine and creates instances via `getScriptEngine()` |
| `ScriptEngine` | Evaluates scripts, manages bindings/context per the engine contract |
| `ScriptEngineManager.getEngineFactories()` | Returns the list of discovered and registered factories |
| `getEngineByName(name)` | Looks up an engine by a name/alias advertised by a factory |
| `getEngineByExtension(extension)` | Looks up an engine by a file extension advertised by a factory |
| `getEngineByMimeType(mimeType)` | Looks up an engine by a MIME type advertised by a factory |
| `registerEngineName/Extension/MimeType` | Manually registers a mapping from an identifier to a factory |

Factories expose metadata for the host to inspect before creating an engine: `getEngineName()`, `getEngineVersion()`, `getLanguageName()`, `getLanguageVersion()`, `getNames()`, `getExtensions()`, `getMimeTypes()`, and `getParameter(...)`. This metadata is useful for selecting an engine by capability or policy. Keep in mind that even looking up factories may load classes and instantiate factory instances; discovery is **not completely free of cost/side effects**.

## 3. Default Manager vs. Manager with Explicit Loader

```java
ScriptEngineManager defaultManager = new ScriptEngineManager();
ScriptEngineManager pluginManager = new ScriptEngineManager(pluginLoader);
```

This is an **illustrative code snippet** requiring `import javax.script.ScriptEngineManager` and a `pluginLoader` variable of type `ClassLoader`.

The no-arg constructor typically uses the thread context class loader (TCCL) to discover providers. If a server application changes the TCCL per request/thread, using the default constructor can yield different results across contexts.

The constructor accepting a `ClassLoader` lets the host **explicitly specify the loader used for discovery**. In the module path/layer model, service discovery also involves the module graph and resolved modules; passing a loader does not automatically turn JARs outside the module graph into providers.

Do not mutate the global TCCL and assume every engine will be found. When TCCL is needed for a legacy library, save the old value, set the temporary loader, and restore it in `finally`; however, if an API accepts a loader directly, using the explicit constructor is easier to control.

## 4. Requirements for an Engine JAR to Be Discovered

With the class path or a custom `URLClassLoader`, an engine provider typically implements `javax.script.ScriptEngineFactory` and includes an SPI file in the JAR:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

The file contents are the fully qualified name of the factory implementation, for example:

```text
demo.engine.EchoEngineFactory
```

The service descriptor only lists provider classes; it does not declare language aliases itself. Aliases like `echo` are provided by `ScriptEngineFactory.getNames()`. The factory must be public and validly instantiable according to the environment's `ServiceLoader` mechanism.

If the engine is an explicit named module, the module descriptor typically declares:

```java
module demo.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with demo.engine.EchoEngineFactory;
}
```

This is an **illustrative module descriptor**; the implementation source must exist. Named modules use `provides` and appropriate resolution/layers; having only a `META-INF/services` descriptor is not sufficient for an explicit named module to be discovered under module service binding rules.

## 5. Complete Hands-On Example: A Minimal JSR 223 Engine

This example creates an `echo` engine that returns the evaluated script verbatim. The engine is for verifying discovery, **not a JavaScript engine**; it does not execute arbitrary languages and should not be used as a production interpreter.

Source layout:

```text
script-demo/
├── host/
│   └── Host.java
└── engine/
    ├── demo/engine/EchoEngine.java
    ├── demo/engine/EchoEngineFactory.java
    └── META-INF/services/javax.script.ScriptEngineFactory
```

### 5.1. Engine Implementation

`engine/demo/engine/EchoEngine.java`:

```java
package demo.engine;

import java.io.IOException;
import java.io.Reader;
import java.util.Objects;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class EchoEngine extends AbstractScriptEngine {
    private final ScriptEngineFactory factory;

    public EchoEngine(ScriptEngineFactory factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    @Override
    public Object eval(String script, ScriptContext context) {
        return script;
    }

    @Override
    public Object eval(Reader reader, ScriptContext context) throws ScriptException {
        try {
            StringBuilder output = new StringBuilder();
            char[] buffer = new char[1024];
            int n;
            while ((n = reader.read(buffer)) != -1) {
                output.append(buffer, 0, n);
            }
            return output.toString();
        } catch (IOException ex) {
            throw new ScriptException(ex);
        }
    }

    @Override
    public Bindings createBindings() {
        return new SimpleBindings();
    }

    @Override
    public ScriptEngineFactory getFactory() {
        return factory;
    }
}
```

Note: `AbstractScriptEngine` supplies the remaining `eval` overloads that use `ScriptContext`/`Bindings`. To keep the example minimal, this engine does not interpret variables or statements, so `eval("hello")` simply returns the string `hello`.

### 5.2. Factory and Metadata

`engine/demo/engine/EchoEngineFactory.java`:

```java
package demo.engine;

import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;

public final class EchoEngineFactory implements ScriptEngineFactory {
    @Override public String getEngineName() { return "Echo Engine"; }
    @Override public String getEngineVersion() { return "1.0"; }
    @Override public List<String> getExtensions() { return List.of("echo"); }
    @Override public List<String> getMimeTypes() { return List.of("text/x-echo"); }
    @Override public List<String> getNames() { return List.of("echo", "EchoEngine"); }
    @Override public String getLanguageName() { return "Echo"; }
    @Override public String getLanguageVersion() { return "1.0"; }

    @Override
    public Object getParameter(String key) {
        return switch (key) {
            case ScriptEngine.NAME -> "echo";
            case ScriptEngine.ENGINE -> getEngineName();
            case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
            case ScriptEngine.LANGUAGE -> getLanguageName();
            case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
            case "THREADING" -> null;
            default -> null;
        };
    }

    @Override
    public String getMethodCallSyntax(String obj, String method, String... args) {
        return obj + "." + method + "(" + String.join(", ", args) + ")";
    }

    @Override
    public String getOutputStatement(String toDisplay) {
        return toDisplay;
    }

    @Override
    public String getProgram(String... statements) {
        return String.join("\n", statements);
    }

    @Override
    public ScriptEngine getScriptEngine() {
        return new EchoEngine(this);
    }
}
```

The factory includes the required metadata fields of `ScriptEngineFactory`. The value `THREADING = null` makes no guarantee that the engine is safe for concurrent multi-threaded access. You must not infer from it that the host may share one `ScriptEngine` across multiple threads.

### 5.3. SPI Descriptor

Create the text file `engine/META-INF/services/javax.script.ScriptEngineFactory` with exactly one line:

```text
demo.engine.EchoEngineFactory
```

Ensure this file sits at the resource root of the JAR, not under the `demo.engine` package. A trailing newline at the end of the file is recommended for clean packaging and reading.

### 5.4. Host Creating a Dedicated Loader and Looking Up the Factory

`host/Host.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public final class Host {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("build/echo-engine.jar").toUri().toURL();
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar}, ClassLoader.getPlatformClassLoader())) {
            ScriptEngineManager manager = new ScriptEngineManager(pluginLoader);
            ScriptEngineFactory chosen = manager.getEngineFactories().stream()
                    .filter(factory -> factory.getNames().contains("echo"))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException("Missing echo engine"));

            System.out.println("factory: " + chosen.getEngineName());
            System.out.println("language: " + chosen.getLanguageName());
            System.out.println("aliases: " + chosen.getNames());

            ScriptEngine engine = manager.getEngineByName("echo");
            if (engine == null) {
                throw new IllegalStateException("Factory exists but engine not found");
            }
            System.out.println("result: " + engine.eval("hello plugin"));
        }
    }
}
```

In this example, `ClassLoader.getPlatformClassLoader()` is the parent of the plugin loader. `javax.script` belongs to the platform module `java.scripting`, so the loader can still see the SPI interface. Do not place `echo-engine.jar` on the host's class path; let the JAR be defined by `pluginLoader` to observe the difference clearly.

**Note on `URLClassLoader.close()`:** Closing the loader releases resources managed by the loader (such as JAR handles). It does not force loaded classes to unload, nor does it automatically stop threads or close engine resources. In a real system, close engine resources according to the API/provider contract before closing the loader.

### 5.5. Compile, Package, and Run

Run the following commands from the `script-demo/` directory using a POSIX shell with JDK 17+:

```bash
mkdir -p build/engine-classes build/host-classes
javac -encoding UTF-8 -d build/engine-classes \
  engine/demo/engine/EchoEngine.java \
  engine/demo/engine/EchoEngineFactory.java
jar --create --file build/echo-engine.jar \
  -C build/engine-classes . \
  -C engine META-INF/services
javac -encoding UTF-8 -d build/host-classes host/Host.java
java -cp build/host-classes Host
```

Expected output when run on JDK 17 with the demo engine JAR:

```text
factory: Echo Engine
language: Echo
aliases: [echo, EchoEngine]
result: hello plugin
```

This is a self-contained runnable example on JDK 17+ and requires no third-party JavaScript engine. No `--module-path` is needed because both the host and demo engine use the class path/custom loader mechanism. The `jar` command packages both classes and the SPI descriptor into the same artifact.

## 6. Diagnosing When the Manager Does Not See a Factory

First inspect the artifact:

```bash
jar --list --file build/echo-engine.jar
```

It should contain `demo/engine/EchoEngineFactory.class`, `demo/engine/EchoEngine.class`, and `META-INF/services/javax.script.ScriptEngineFactory`. Verify the exact descriptor filename and the binary name inside it; `ServiceLoader` will not automatically find the provider class if the descriptor is missing.

If it is still not visible, diagnose with:

```java
System.out.println("TCCL: " + Thread.currentThread().getContextClassLoader());
System.out.println("plugin loader: " + pluginLoader);
System.out.println("factory count: " + manager.getEngineFactories().size());
```

This is an illustrative snippet to place inside `Host.main` after creating the manager. Confirm that `new ScriptEngineManager(pluginLoader)` actually uses a loader with access to the JAR; the default constructor may use a different TCCL.

Common cases you may encounter:

| Symptom | Common Cause | Resolution |
|---|---|---|
| `getEngineFactories()` is empty | No JSR 223 provider discovered | Check JAR, SPI descriptor, and class loader |
| `getEngineByName("JavaScript") == null` | JDK 17 has no built-in JavaScript engine | Install a compatible JSR 223 engine or choose another language |
| Factory is visible but `getScriptEngine()` fails | Missing engine dependency, constructor error, or misconfiguration | Inspect the exception and runtime dependencies |
| `ServiceConfigurationError` | Invalid/unloadable provider class | Check descriptor, visibility, constructor, and class loader |
| `ClassCastException` or provider not assignable | SPI/API loaded twice through different loaders | Share `javax.script` and common contracts via parent |
| Engine JAR is present but missing from old manager | Manager snapshotted factories at initialization or module not resolved | Create a new manager after setting up the loader/module graph |

Do not alter the entire application class path just to fix one plugin. Identify which loader owns that engine and use the corresponding manager.

## 7. Selecting a Factory by Metadata Before Creating an Engine

When a system has multiple engines sharing an alias, `getEngineByName` is not always sufficient to enforce business policy. The host can iterate `getEngineFactories()` and filter by language name, version, alias, MIME type, or allowlist.

Illustrative snippet:

```java
ScriptEngineFactory factory = manager.getEngineFactories().stream()
    .filter(f -> f.getLanguageName().equalsIgnoreCase("Echo"))
    .filter(f -> f.getNames().contains("echo"))
    .findFirst()
    .orElseThrow();
ScriptEngine engine = factory.getScriptEngine();
```

This snippet only runs in a context that has `manager` and the corresponding imports. It allows selection by metadata before calling `getScriptEngine()`, avoiding instantiating unnecessary engines. However, factory discovery may still initialize factory classes, so factory constructors should be lightweight and avoid network I/O, thread allocation, or script execution.

For a deterministic policy, add tie-breakers and version checks; do not treat the order in which `ServiceLoader` discovers factories as business priority. Metadata advertised by plugins must be checked for validity and trustworthiness if plugins come from third parties.

## 8. Relationship Between Class Loaders, JPMS, and ModuleLayer

In a JPMS application, `ScriptEngineFactory` belongs to the `java.scripting` module. Named engine modules use `provides javax.script.ScriptEngineFactory with ...` and are resolved in an appropriate module graph. `ScriptEngineManager` can work with providers visible through the service/module mechanism, but passing a loader to the manager is not a call to resolve new modules in a layer that does not yet exist.

If the host creates a separate plugin `ModuleLayer` after startup, discovery must be designed explicitly. `ServiceLoader.load(layer, ScriptEngineFactory.class)` is the API that discovers providers in a layer; the host can use the returned factories and call `getScriptEngine()` directly, rather than assuming the manager will automatically scan all child layers.

**Non-standalone** illustrative example requiring `pluginLayer` to already exist and `java.scripting` to be a shared module:

```java
var factories = java.util.ServiceLoader.load(
        pluginLayer, javax.script.ScriptEngineFactory.class);
for (var factory : factories) {
    System.out.println(factory.getEngineName());
}
```

Do not assume that closing a module layer unloads classes; Java has no `ModuleLayer.close()`. Lifecycle management of loaders, engines, and plugin resources must be designed explicitly. Using custom class loaders alongside JPMS requires attention to split packages, module readability, `exports`/`opens`, and type identity.

## 9. Safety When Running Embedded Scripts

A script engine is code running inside the Java process. `ScriptEngine.eval(...)` can execute whatever the engine permits, including accessing Java objects, I/O, or other powerful capabilities depending on the language/engine. Placing an engine in a separate JAR or separate class loader **does not create a security sandbox**.

For untrusted scripts, the host should control accepted languages and engines, limit execution time, memory, and I/O using appropriate process/OS mechanisms; restrict Java objects exposed in bindings, and define how to stop the engine on timeout. Do not assume `ScriptEngine` is thread-safe: check the `THREADING` specification, provider documentation, and run tests before sharing an instance across multiple requests.

**Conclusion:** `ScriptEngineManager` discovers `ScriptEngineFactory` implementations via SPI within the visible class loader/module graph scope. For plugin systems, specify the loader explicitly when creating the manager, verify descriptor/module registration, select factories by metadata, and instantiate only the chosen engine. For dynamically created module layers, use `ServiceLoader.load(layer, ScriptEngineFactory.class)` to control discovery scope.
