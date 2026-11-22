# 17.2. Discovering Engines via `ScriptEngineManager` and Handling Not-Found Results

## 1. The Core Problem: Having the JSR-223 API Does Not Mean Having a Script Engine

In Java, **JSR-223 / Scripting for the Java Platform** provides a standard API for embedding scripting languages into an application. The API resides in the **`java.scripting`** module, package **`javax.script`**. You can import `ScriptEngineManager`, `ScriptEngine`, `ScriptEngineFactory`, and `ScriptException` on JDK 17 **without adding any libraries**. However, the JDK library provides **API discovery**, not a guarantee of a built-in implementation for JavaScript, Python, Groovy, or any other language.

The real-world problem:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("javascript");
engine.eval("1 + 2");
```

This is a **counter-example snippet**, not a standalone program. In an environment without a JavaScript `ScriptEngineFactory`, `getEngineByName("javascript")` returns **`null`**; calling `engine.eval(...)` next causes the application to throw a **`NullPointerException`** before running any script. This error does not mean the JavaScript syntax is wrong, but rather that the **engine discovery step failed**.

Since JDK 15, the **Nashorn JavaScript engine and the `jjs` tool have been removed** (JEP 372). Java 17 still has **`javax.script`** and **`ScriptEngineManager`**, but a clean JDK 17 usually **does not have a JavaScript engine pre-installed**. If a project adds a compatible provider (for example, an external JSR-223 implementation), that machine can still return an engine for a JavaScript name published by the provider. Therefore:

> **Do not equate "API present" with "engine present"; always check the factory and lookup results in the actual deployment environment.**

This lesson presents the correct discovery workflow, how to handle `null` safely, class loader and Service Provider Interface (SPI) diagnostic strategies, and then builds a **completely self-contained test engine** to demonstrate lookup by name/extension/MIME on Java 17+.

## 2. Object Model in JSR-223

Let's separate the four roles:

| Component | Role | Usage example |
| --- | --- | --- |
| **`ScriptEngineManager`** | Discovers and creates `ScriptEngine` via `ScriptEngineFactory`; holds global bindings shared among engines created by the manager | `new ScriptEngineManager()` |
| **`ScriptEngineFactory`** | Provides metadata about the implementation, language name, aliases, extensions, MIME types; creates engine instances | `factory.getScriptEngine()` |
| **`ScriptEngine`** | The actual engine that executes `eval`, holds `ScriptContext`/bindings, and may support additional interfaces depending on the provider | `engine.eval(script)` |
| **`ScriptException`** | Reports script execution/compilation errors according to the JSR-223 API | `catch (ScriptException ex)` |

Typical flow:

```text
Application
    |
    | new ScriptEngineManager()
    v
ScriptEngineManager
    |
    | ServiceLoader<ScriptEngineFactory>
    | (visible provider classes/resources/modules)
    v
Factories discovered
    |
    | getEngineByName("mini")
    | getEngineByExtension("mini")
    | getEngineByMimeType("text/x-mini")
    v
Matched ScriptEngineFactory?
    |
    +---- NO ----> null ----> diagnostics / fail-fast / graceful fallback
    |
    +---- YES ---> factory.getScriptEngine()
                           |
                           v
                     ScriptEngine
                           |
                     eval(script)
                           |
                   Object result or ScriptException
```

**`ScriptEngineManager` does not parse or execute code of any language itself.** It uses the **`ServiceLoader`** mechanism to discover implementations of `ScriptEngineFactory`; each factory is responsible for providing the engine.

`getEngineByName`, `getEngineByExtension`, and `getEngineByMimeType` all **return a `ScriptEngine` or `null`** when no suitable implementation is found. The methods do not require the JVM to have a built-in engine for the corresponding language.

## 3. Three Lookups to Understand Correctly

### 3.1. By Name or Alias — `getEngineByName`

```java
ScriptEngine engine = manager.getEngineByName("javascript");
```

This is **illustrative code** with `manager` already initialized. The API matches against names registered via `registerEngineName` or published by `ScriptEngineFactory.getNames()` of the discovered providers.

- `ScriptEngineFactory.getNames()` often returns multiple aliases; for example, a provider may publish `"js"` and `"javascript"`. **That is provider-decided information**; there is no universal alias guaranteed to exist on every machine.
- `getEngineName()` is the **engine implementation name**, not necessarily a valid lookup alias.
- `getLanguageName()` is the **language name**, not a default key for `getEngineByName` unless the factory also includes that name in `getNames()`.
- Do not infer alias names from examples on the Internet without listing the actual factory metadata.
- Passing a `null` name causes a `NullPointerException` per Java SE 17; it is **not** equivalent to "not found".

In terms of order, the manager checks **manual registrations** for that name first, then checks factories discovered via SPI. Thus `registerEngineName("alias", someFactory)` can override the association used for that alias lookup in the current manager.

### 3.2. By Extension — `getEngineByExtension`

```java
ScriptEngine engine = manager.getEngineByExtension("mini");
```

Assumes `manager` already exists. `"mini"` is the **extension token** declared by the factory in `getExtensions()`, not a full path, filename, or glob.

If the factory publishes `getExtensions() == List.of("mini")`, look up using `"mini"`; do not assume the API will strip the `.` from `".mini"` or extract the extension from `"report.mini"` for you. If the application receives a file path, **extract the extension and validate the value** before looking it up.

### 3.3. By MIME Type — `getEngineByMimeType`

```java
ScriptEngine engine = manager.getEngineByMimeType("text/x-mini");
```

The factory must publish the corresponding MIME type in `getMimeTypes()`, or the application must have registered the association using `registerEngineMimeType`.

MIME types **are not automatically inferred** from file extensions. Conversely, having the extension `"mini"` does not prove that `"application/x-mini"` or `"text/x-mini"` is a valid alias if the provider does not publish it.

### Comparison Table

| API | Factory metadata to check | Input value | Not found |
| --- | --- | --- | --- |
| `getEngineByName(name)` | `getNames()` | Alias/short name, e.g., `"mini"` | `null` |
| `getEngineByExtension(ext)` | `getExtensions()` | Extension token, e.g., `"mini"` | `null` |
| `getEngineByMimeType(mime)` | `getMimeTypes()` | MIME type, e.g., `"text/x-mini"` | `null` |
| `getEngineFactories()` | Discovered providers | No key | Empty list if no factory is found |

Do not call `engine.getFactory()` when `engine == null`; branch first.

## 4. `getEngineFactories()` Is the First Diagnostic Tool

```java
ScriptEngineManager manager = new ScriptEngineManager();

for (ScriptEngineFactory f : manager.getEngineFactories()) {
    System.out.println(f.getEngineName());
    System.out.println(f.getEngineVersion());
    System.out.println(f.getLanguageName());
    System.out.println(f.getNames());
    System.out.println(f.getExtensions());
    System.out.println(f.getMimeTypes());
}
```

This is an illustrative Java snippet; you need to import `javax.script.ScriptEngineFactory` and `javax.script.ScriptEngineManager`.

Useful metadata:

| `ScriptEngineFactory` API | Question answered |
| --- | --- |
| `getEngineName()` | Which implementation is being used? |
| `getEngineVersion()` | Version of the engine implementation itself? |
| `getLanguageName()` | What language does the engine support? |
| `getLanguageVersion()` | What language version does the engine support? |
| `getNames()` | Which aliases can be passed to `getEngineByName`? |
| `getExtensions()` | Which file extensions can be looked up? |
| `getMimeTypes()` | Which MIME types can be looked up? |
| `getScriptEngine()` | How does the factory create an actual engine instance? |
| `getParameter(key)` | Additional metadata or capabilities, e.g., `"THREADING"` when supported by the provider? |

An **empty list** proves that **the current manager discovered no factories**, not that Java 17 does not support JSR-223. The cause may be that no provider is installed, the provider is not visible in the class loader/layer, the service file is missing or incorrect, or the deployment configuration is wrong.

A **non-empty list where lookup still returns `null`** usually means the alias/extension/MIME does not match any factory; you need to look at `getNames()` instead of trying arbitrary names.

`getEngineFactories()` provides the factories that the manager discovered through its constructor mechanism; it is **not a live registry of every alias registered manually later**. See section 12 for more details.

## 5. Rules for Handling `null` Results Before Calling `eval`

In real-world systems there are two valid policies, depending on the role of scripting:

### 5.1. Engine Is an Optional Feature — Degrade Gracefully

If the script only serves an optional feature, you can report it as unsupported instead of crashing the entire application:

```java
ScriptEngine engine = manager.getEngineByName(requiredName);
if (engine == null) {
    System.err.println("Scripting engine unavailable: " + requiredName);
    return;
}
// Only call eval after verifying engine != null.
```

This is a **snippet inside a `void`-returning method** with `manager` and `requiredName` already declared; it is not a standalone file.

What matters: a "fallback" must have **valid business semantics**. If the engine is used to run **authorization rules**, treating the condition as `true` by default when the engine is missing can compromise security. In that case, you should **fail closed** according to system policy.

### 5.2. Engine Is a Required Dependency — Fail Fast with a Clear Message

```java
ScriptEngine engine = manager.getEngineByName(requiredName);
if (engine == null) {
    throw new IllegalStateException(
            "No JSR-223 ScriptEngine for: " + requiredName);
}
```

This is an illustrative snippet for configuration/startup code. If the engine is missing, the application fails early **with a defined reason** instead of hitting a `NullPointerException` in a later `eval` call.

What should be included in the error message or telemetry: requested name, visible aliases/engine names, classloader/deployment mode, and expected configuration dependency. **Do not** log sensitive script source, tokens, or credentials.

### 5.3. `Optional<ScriptEngine>` Does Not Fix a Missing Provider by Itself

Wrapping `manager.getEngineByName(...)` in `Optional.ofNullable(...)` can make the caller API more expressive, but you still need a clear policy when `Optional.empty()` occurs: display a disabled status, fail fast, or use a designed fallback. `Optional` does not install an engine and does not change ServiceLoader.

### 5.4. Why Not Catch `NullPointerException` Around `eval`?

The wrong way:

```java
try {
    manager.getEngineByName("javascript").eval(script);
} catch (NullPointerException e) {
    // Assume that the engine does not exist?
}
```

This is a **counter-example**: a `NullPointerException` can also come from the provider itself, bindings, or the script evaluation path; catching too broadly hides the root cause of the error. Check **`engine == null` first**, then handle `ScriptException` and runtime exceptions in context.

## 6. Standalone Java 17+ Example: Listing Engines and Diagnosing Missing Engines

Save the file **`EngineProbe.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public final class EngineProbe {
    public static void main(String[] args) {
        String requested = args.length == 0 ? "javascript" : args[0];
        ScriptEngineManager manager = new ScriptEngineManager();

        List<ScriptEngineFactory> factories =
                new ArrayList<>(manager.getEngineFactories());
        factories.sort(Comparator.comparing(
                ScriptEngineFactory::getEngineName));
        System.out.println("factories=" + factories.size());

        for (ScriptEngineFactory f : factories) {
            System.out.println("engine=" + f.getEngineName()
                    + ";language=" + f.getLanguageName()
                    + ";names=" + f.getNames()
                    + ";extensions=" + f.getExtensions()
                    + ";mime=" + f.getMimeTypes());
        }

        ScriptEngine engine = manager.getEngineByName(requested);
        if (engine == null) {
            System.out.println("NOT_FOUND: " + requested);
            System.out.println(
                    "hint=Install a compatible JSR-223 provider and check classloader visibility");
            return;
        }
        System.out.println("FOUND: " + engine.getFactory().getEngineName());
    }
}
```

Compile/run:

```bash
javac --release 17 EngineProbe.java
java EngineProbe
java EngineProbe __missing_language_for_demo__
```

In an experiment on **JDK 17 without any external script-engine provider installed**, the two runs produced:

```text
factories=0
NOT_FOUND: javascript
hint=Install a compatible JSR-223 provider and check classloader visibility
```

and:

```text
factories=0
NOT_FOUND: __missing_language_for_demo__
hint=Install a compatible JSR-223 provider and check classloader visibility
```

**This is the output of a clean test environment, not a guaranteed output for every JDK 17.** If the classpath/module path has providers, `factories` may be greater than 0, `engine=...` lines will appear, and `"javascript"` may be supported depending on the implementation.

QA points of the example:

- The code **does not call `eval` when the engine is absent**.
- Prints the list of factories sorted by engine name by copying into an `ArrayList`; does not depend on ServiceLoader order.
- Has an explicit handling branch for `NOT_FOUND`.
- Does not assume Nashorn is the default engine.
- In the success branch, retrieves the implementation name from the **actual factory** that created the engine.

**A not-found branch is not a compilation error.** The JDK still compiles/imports the `javax.script` package normally because `java.scripting` is in the JDK; the issue occurs at **runtime service discovery**.

## 7. Why Does Java 17 Often Fail to Find `"javascript"`?

Nashorn used to be shipped with some JDK releases and exposed JavaScript through JSR-223. But the history changed:

| Stage | Impact |
| --- | --- |
| Java 6 onwards | The `javax.script` scripting API exists |
| JDK 11 | Nashorn is marked deprecated for removal |
| **JDK 15** | **Nashorn JavaScript engine/API and `jjs` tool are removed from the JDK** |
| **JDK 17** | The `java.scripting` API still exists; a JavaScript engine requires a suitable provider from the external environment |
| Later JDKs/environments | The engine list depends on providers and classloader/module configuration, and cannot be inferred from the JDK version alone |

JDK 17 **does not automatically replace Nashorn with another JavaScript engine** just because you call `"javascript"`. You must actively choose a suitable implementation, declare the dependency, ensure the provider is compatible with Java/JVM/JSR-223, and check the registered aliases.

Learners should not be instructed to `import jdk.nashorn.api.scripting.NashornScriptEngineFactory` in standard Java 17 applications: the old bundled Nashorn API has been removed. When choosing an alternative engine, evaluate version, script compatibility, host interop, sandbox/security, and threading; **do not assume every Nashorn API is compatible with every new engine**.

**Characteristic symptom:** `ScriptEngineManager` initializes successfully, `getEngineFactories()` returns an empty list, and `getEngineByName("javascript")` returns `null`. This is a valid and common scenario on JDK 17 without a provider.

## 8. SPI: Conditions for the Manager to Discover an Engine

`ScriptEngineManager` uses the service-provider mechanism corresponding to **`java.util.ServiceLoader<javax.script.ScriptEngineFactory>`**.

### 8.1. Deployment on the Classpath

A provider running via the classpath needs:

1. A **public** class implementing `ScriptEngineFactory`, with an instantiation path usable by ServiceLoader.
2. That class along with its dependencies actually present on the **runtime classpath**.
3. The exact resource file:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

4. The resource file content listing the **fully qualified class name** of the factory, one provider per line, for example:

```text
demo.scripting.MiniEngineFactory
```

5. The resource and class must be **visible** to the class loader that the manager uses for discovery.

The service resource is packaged in the JAR/directory on the classpath, **not** `META-INF/services/javax.script.ScriptEngine`, because the discovery mechanism looks for **`ScriptEngineFactory`**.

The service file content uses UTF-8; since the example name contains only ASCII, an ASCII file is also valid UTF-8. Do not add JSON/XML or shortened package names.

### 8.2. Deployment Using Named Modules (JPMS)

A provider as a named module can declare:

```java
module demo.mini.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with demo.scripting.MiniEngineFactory;
}
```

This is an **illustrative `module-info.java` snippet**; it is not one of the files used for the classpath demo in sections 9–11. The module must be built/resolved in a layer visible to the service loading mechanism. If the provider is on the module path but the module has not been properly resolved/bound, merely placing that JAR in a directory is not enough for `ScriptEngineManager` to see it.

`java.scripting` declares **`uses javax.script.ScriptEngineFactory`** so ServiceLoader can obtain providers. For a provider that is a named module, `provides ... with ...` is the standard declaration mechanism; do not use a classpath service file as the sole approach for all deployment forms.

### 8.3. An Engine Implementation Is a Dependency Outside the API

Adding the `java.scripting` dependency in an application's Java module **is only for using the API**; it does not automatically add a `ScriptEngineFactory`. Similarly, adding an arbitrary JAR to the project without proper provider registration in that JAR will not make the engine discoverable automatically.

If you use a scripting implementation via a direct constructor instead of SPI, the code may work, but **`new ScriptEngineManager().getEngineByName(...)` will not necessarily know about it**. You need to register the factory or package SPI properly.

## 9. Creating a Small Engine to Verify Both Success and Failure Branches

We will create a **test engine named `Mini Demo Engine`** that only understands two text commands:

```text
upper:hello   -> HELLO
echo:hello    -> hello
```

The goal is **not to build a production scripting language**, but to clearly verify:

- Discovery of `ScriptEngineFactory` via `META-INF/services`.
- Lookup by short name, extension, and MIME.
- The missing-name branch.
- `registerEngineName` adding an intentional alias.
- The difference between the application class loader and the platform class loader.

Directory structure:

```text
project/
├── src/
│   ├── EngineDiscoveryDemo.java
│   └── demo/
│       └── scripting/
│           └── MiniEngineFactory.java
└── classes/
    └── META-INF/
        └── services/
            └── javax.script.ScriptEngineFactory
```

`classes/` is the **output directory** containing `.class` files and the SPI resource; do not modify `java.scripting` in the JDK.

### 9.1. File `src/demo/scripting/MiniEngineFactory.java`

```java
package demo.scripting;

import java.io.IOException;
import java.io.Reader;
import java.util.List;
import java.util.Locale;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class MiniEngineFactory implements ScriptEngineFactory {
    @Override public String getEngineName() { return "Mini Demo Engine"; }
    @Override public String getEngineVersion() { return "1.0"; }

    @Override public List<String> getExtensions() {
        return List.of("mini");
    }

    @Override public List<String> getMimeTypes() {
        return List.of("text/x-mini");
    }

    @Override public List<String> getNames() {
        return List.of("mini", "mini-demo");
    }

    @Override public String getLanguageName() {
        return "MiniDemo";
    }

    @Override public String getLanguageVersion() {
        return "1.0";
    }

    @Override public Object getParameter(String key) {
        if (ScriptEngine.ENGINE.equals(key)) return getEngineName();
        if (ScriptEngine.ENGINE_VERSION.equals(key)) return getEngineVersion();
        if (ScriptEngine.LANGUAGE.equals(key)) return getLanguageName();
        if (ScriptEngine.LANGUAGE_VERSION.equals(key)) return getLanguageVersion();
        if (ScriptEngine.NAME.equals(key)) return "mini";
        return null;
    }

    // Just a demo toy language; does not support calling Java methods using script syntax.
    @Override public String getMethodCallSyntax(
            String obj, String method, String... args) {
        return null;
    }

    @Override public String getOutputStatement(String text) {
        return "echo:" + text;
    }

    @Override public String getProgram(String... statements) {
        return String.join("\n", statements);
    }

    @Override public ScriptEngine getScriptEngine() {
        return new MiniEngine(this);
    }

    private static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override public Object eval(String script, ScriptContext context)
                throws ScriptException {
            if (script == null) throw new NullPointerException("script");

            if (script.startsWith("upper:")) {
                return script.substring(6).toUpperCase(Locale.ROOT);
            }
            if (script.startsWith("echo:")) {
                return script.substring(5);
            }
            throw new ScriptException("Unsupported mini command");
        }

        @Override public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder text = new StringBuilder();
                char[] buffer = new char[1024];
                int n;

                while ((n = reader.read(buffer)) != -1) {
                    text.append(buffer, 0, n);
                }
                return eval(text.toString(), context);
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
        }

        @Override public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override public ScriptEngineFactory getFactory() {
            return factory;
        }
    }
}
```

This is a **standalone, compilable Java file**, but it requires packaging the SPI resource and the client file below to test the manager.

Why must the factory implement so many methods? Because `ScriptEngineFactory` is an interface describing metadata and how to create an engine; `ScriptEngineManager` cannot infer `getNames()` or `getMimeTypes()` from the class name alone.

`AbstractScriptEngine` reduces boilerplate code for `ScriptEngine`, but still requires implementing `eval(String,ScriptContext)`, `eval(Reader,ScriptContext)`, `createBindings`, and `getFactory`. The toy engine uses `Locale.ROOT` so uppercasing is more consistent across host machine locale differences.

**Intentional limitations of the demo:** `getMethodCallSyntax` returns `null` because Java method-call syntax is not supported, `getProgram` joins statements, but the evaluator only understands **one `upper:` or `echo:` command per eval**. Do not use this demo provider as a scripting runtime for a real application; in particular, it does not support sandboxing, a multi-statement parser, or execution control.

### 9.2. Service Provider File — Not Java Source

Create the file:

```text
classes/META-INF/services/javax.script.ScriptEngineFactory
```

Content is **exactly one line**:

```text
demo.scripting.MiniEngineFactory
```

The file must exist at **runtime**, under the same classpath root `classes/` that contains `demo/scripting/MiniEngineFactory.class`. It must not be placed in `src/META-INF` and forgotten to be copied to output; `javac` compiles Java source **without automatically copying arbitrary resources**.

### 9.3. File `src/EngineDiscoveryDemo.java`

```java
import java.util.Comparator;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import demo.scripting.MiniEngineFactory;

public final class EngineDiscoveryDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();

        boolean factoryVisible = manager.getEngineFactories().stream()
                .map(ScriptEngineFactory::getEngineName)
                .anyMatch("Mini Demo Engine"::equals);
        System.out.println("providerVisible=" + factoryVisible);

        ScriptEngine byName = manager.getEngineByName("mini");
        System.out.println("byName=" + (byName != null));
        System.out.println("byExtension=" +
                (manager.getEngineByExtension("mini") != null));
        System.out.println("byMime=" +
                (manager.getEngineByMimeType("text/x-mini") != null));
        System.out.println("unknown=" +
                (manager.getEngineByName("__definitely_missing_engine__") == null));

        if (byName == null) {
            throw new IllegalStateException("Mini provider not visible");
        }

        System.out.println("result=" + byName.eval("upper:hello"));
        System.out.println("language=" + byName.getFactory().getLanguageName());

        manager.registerEngineName("mini-alias", new MiniEngineFactory());
        System.out.println("alias=" +
                (manager.getEngineByName("mini-alias") != null));

        ScriptEngineManager platformOnly =
                new ScriptEngineManager(ClassLoader.getPlatformClassLoader());
        System.out.println("platformCanSeeMini=" +
                (platformOnly.getEngineByName("mini") != null));

        System.out.println("javascriptAvailable=" +
                (manager.getEngineByName("javascript") != null));
    }
}
```

In this example `import java.util.Comparator;` is unused, so **that import can be removed without changing behavior**. It does not cause a `javac` error because Java allows unused imports. The important parts are the `javax.script` imports and `demo.scripting.MiniEngineFactory`.

### 9.4. Compiling and Running

On Bash (Linux/macOS or a compatible shell), from the `project/` directory:

```bash
mkdir -p classes/META-INF/services
printf 'demo.scripting.MiniEngineFactory\n' > classes/META-INF/services/javax.script.ScriptEngineFactory

javac --release 17 -d classes \
    src/demo/scripting/MiniEngineFactory.java \
    src/EngineDiscoveryDemo.java

java -cp classes EngineDiscoveryDemo
```

On **Windows PowerShell**, create the exact service file and run the same example:

```powershell
New-Item -ItemType Directory -Force -Path "classes/META-INF/services"

Set-Content -Encoding Ascii `
    -Path "classes/META-INF/services/javax.script.ScriptEngineFactory" `
    -Value "demo.scripting.MiniEngineFactory"

javac --release 17 -d classes `
    src/demo/scripting/MiniEngineFactory.java `
    src/EngineDiscoveryDemo.java

java -cp classes EngineDiscoveryDemo
```

Because the provider class name is an ASCII string, choosing `-Encoding Ascii` creates a file with UTF-8-compatible bytes, avoiding a BOM generated by some PowerShell versions when using the UTF-8 option.

**The command must be run with classpath root `classes`**. If you invoke `java EngineDiscoveryDemo` from the project directory without `-cp classes`, the JVM may fail to find the main class or the provider resource. `-cp classes` makes both `.class` files and `META-INF/services` visible to the classloader.

## 10. Stdout from the Verified SPI Demo on Java 17

With the demo provider on the classpath and the JDK running without any other JavaScript provider, the output is:

```text
providerVisible=true
byName=true
byExtension=true
byMime=true
unknown=true
result=HELLO
language=MiniDemo
alias=true
platformCanSeeMini=false
javascriptAvailable=false
```

**The first lines verify the exact demo configuration.** The last line `javascriptAvailable=false` is the **result of the test environment**; if your classpath/JDK has another JavaScript provider, the last line may be `true`. The goal of the demo is to prove that having `mini` does not automatically create a `javascript` engine.

### Step-by-Step Analysis

1. **`providerVisible=true`**: The manager found `MiniEngineFactory` via `ServiceLoader`, so the factory appears in `getEngineFactories()`.
2. **`byName=true`**: `"mini"` exists in `MiniEngineFactory.getNames()`.
3. **`byExtension=true`**: `"mini"` exists in `getExtensions()`.
4. **`byMime=true`**: `"text/x-mini"` exists in `getMimeTypes()`.
5. **`unknown=true`**: A name not published by the factory receives `null` and the application handles it without running a script.
6. **`result=HELLO`**: `MiniEngine.eval("upper:hello")` runs the **demo language**, not JavaScript.
7. **`language=MiniDemo`**: The language name is metadata from `getLanguageName`; it does not have to match the `"mini"` alias.
8. **`alias=true`**: An association manually registered via `registerEngineName("mini-alias", ...)` makes this alias work in the current manager.
9. **`platformCanSeeMini=false`**: `ScriptEngineManager(ClassLoader.getPlatformClassLoader())` uses a loader that **cannot see** the application's classpath provider, so it cannot find `"mini"`. That shows discovery depends on the loader.
10. **`javascriptAvailable=false`**: The demo provider does not provide JavaScript; the test JDK has no other JavaScript engine. **Do not extrapolate this into a claim that every Java 17 returns false**.

Note: `getEngineByName`, `getEngineByExtension`, and `getEngineByMimeType` **may create different engine instances** when called three times. All three comparisons being `true` **does not prove they return the same object**. A factory is free to create a new engine instance on each lookup.

## 11. Class Loader: A Common Cause When the JAR Is Present but Still Returns `null`

`ScriptEngineManager` has two important constructors:

```java
new ScriptEngineManager();
new ScriptEngineManager(loader);
```

- **The no-argument constructor** behaves equivalently to `new ScriptEngineManager(Thread.currentThread().getContextClassLoader())`. This is the **thread context class loader (TCCL)** at the time the manager is created.
- **The constructor taking `ClassLoader`** uses the specified loader to find implementations of `ScriptEngineFactory` via the service-provider mechanism.
- **Passing `loader == null`** per the Java SE 17 API searches only for factories **bundled with the platform**; it does not mean automatically using the app classpath loader.

Illustrative code snippet:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();

ScriptEngineManager byContext = new ScriptEngineManager();
ScriptEngineManager explicit = new ScriptEngineManager(context);
ScriptEngineManager byPlatform =
        new ScriptEngineManager(ClassLoader.getPlatformClassLoader());
```

The three managers do not necessarily see the same factories if loader visibility differs. In an application server/plugin framework, threads may have different TCCLs; creating a manager on a bootstrap thread and using it on a plugin thread may yield different results than creating the manager directly inside the plugin.

### Safe Classloader Diagnostics

When a lookup fails, determine:

```java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
ClassLoader owner = YourApplication.class.getClassLoader();
```

This is **illustrative code**; replace `YourApplication` with a real class. `tccl` may differ from `owner`; `owner` is not always the loader you need to use (depending on the module/plugin architecture).

In Java 17, the demo verified that the app classpath manager sees the `mini` provider, while the platform loader manager does not. This helps explain the case "the JAR is in dependencies, yet `getEngineByName` is still null":

- The factory resource was not packaged into the runtime JAR.
- The provider JAR is not on the runtime classpath/module path of the actual classloader.
- The provider class or its dependencies failed to load.
- The context class loader differs from the loader containing the provider.
- The provider is in a named module, but the module has not been resolved/service-bound in the appropriate layer.
- The factory was found, but **the alias being looked up is not in `getNames()`**.

### TCCL and Thread Management

Do not change the global TCCL just to fix a null lookup without understanding classloader boundaries. If you must set the TCCL around an initialization operation, restore it in `finally`:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(providerLoader);
    ScriptEngineManager manager = new ScriptEngineManager();
    // Use manager within the designed scope.
} finally {
    thread.setContextClassLoader(old);
}
```

This is **illustrative code**; `providerLoader` must be a valid available loader. If the code has legacy `SecurityManager`/permission constraints or an environment restricting thread context access, changing the loader may not be permitted. In thread pools, forgetting to restore the TCCL can leak state across requests and retain plugin classloaders longer than intended.

Prefer `new ScriptEngineManager(providerLoader)` when you want to explicitly specify the loader without mutating ambient thread state.

## 12. What Are `registerEngineName`, `registerEngineExtension`, and `registerEngineMimeType` Used For?

Besides SPI discovery, a manager allows registering associations **on a manager instance**:

```java
manager.registerEngineName("alias", existingFactory);
manager.registerEngineExtension("mylang", existingFactory);
manager.registerEngineMimeType("text/x-mylang", existingFactory);
```

This is an **illustrative snippet** with `manager` and `existingFactory` already existing.

Points to remember:

- These APIs **register a mapping from a key to a factory**; they do not load/download/install an engine library.
- They are a suitable choice if you have a valid `ScriptEngineFactory` and want to add an application-controlled alias or replace an association.
- The manager **prioritizes registered associations** for the corresponding key before searching factories from service discovery.
- Registration is scoped to the **manager instance**; it does not modify a JVM-wide registry, nor does it modify `META-INF/services` or module descriptors.
- A manually registered factory does not necessarily become part of the **list of SPI-discovered factories** returned by `getEngineFactories()`; do not use that list as an inventory of all manual aliases.
- `registerEngineName` should not be used as a way to "label as javascript" an engine that **does not understand JavaScript**: changing an alias does not change the provider's language or semantics.

If `getEngineByName("javascript")` is null, do not think `registerEngineName("javascript", null)` can fix the error: a null factory argument is invalid and throws `NullPointerException`. You must **have an actual implementation**.

### Factory List Differs from Registration Table

The two lookup sources have different roles:

```text
ServiceLoader factory inventory: getEngineFactories()
        |
        +--> metadata getNames(), getExtensions(), getMimeTypes()

Explicit per-manager associations:
        |
        +--> registerEngineName/Extension/MimeType(...)
```

Lookup methods try explicit mappings first, then search discovered factories. Therefore, when debugging an **alias** registered by the application itself, `getEngineFactories()` may not reflect that alias as a standalone entry.

## 13. Global Bindings, Engine Scope, and Why Not to Share Arbitrarily

`ScriptEngineManager` also holds **`GLOBAL_SCOPE` Bindings**. When the manager creates a `ScriptEngine`, it places these global bindings into the engine's script context. API example:

```java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("environment", "development");

ScriptEngine engine = manager.getEngineByName("mini");
if (engine != null) {
    // Engine has GLOBAL_SCOPE bindings provided by manager.
}
```

This is an **illustrative snippet in a program**; it does not imply that the toy engine `MiniEngine` will automatically use the `"environment"` variable when evaluating commands.

Distinction:

- **`ENGINE_SCOPE`**: bindings at the script engine/context level, typically prioritized when looking up an attribute.
- **`GLOBAL_SCOPE`**: bindings provided by the manager and visible to engine instances created by that manager.

**Sharing a manager is not a sandbox.** If you put credentials, privileged Java objects, or tenant A's data into global bindings, and then use the same manager to run tenant B's scripts, you must consider data and execution-privilege risks.

Especially with engines that have host interop, a script may call Java APIs or interact with objects passed through bindings depending on provider capabilities. `ScriptEngineManager` only helps find an engine; **it does not restrict filesystem, network, or script execution permissions on its own**.

When allowing scripts from untrusted sources, evaluate host access policies, process/container isolation, resource limits, timeouts, auditing, and engine-specific sandboxing. Do not treat using `javax.script` as a default security boundary.

## 14. Having an Engine Does Not Guarantee Every Script Can Run

`getEngineByName("javascript") != null` only proves that a corresponding implementation is visible and can create an engine. It does **not** guarantee:

- Language/version compatibility with your existing code.
- That Nashorn-specific APIs still exist.
- That `eval` always returns a `String`; the return type is `Object` and may be `null`.
- That `Invocable` or `Compilable` is always supported; those are optional interfaces depending on the implementation.
- That the engine is safe to use concurrently from multiple threads.
- That scripts from untrusted users can run safely.
- That the engine handles charset/encoding or resource resolution the same way as another implementation.

With a real engine:

```java
ScriptEngine engine = manager.getEngineByName(configuredName);
if (engine == null) {
    throw new IllegalStateException("Engine unavailable: " + configuredName);
}
try {
    Object result = engine.eval(scriptSource);
    // Verify result type according to the application contract.
} catch (ScriptException ex) {
    // Handle error reported by the engine when parsing/executing script.
    throw new IllegalStateException("Script execution failed", ex);
}
```

This is an **illustrative snippet** with `manager`, `configuredName`, and `scriptSource` already existing. Avoid logging `scriptSource` or sensitive arguments directly if the script contains confidential data.

Separate three layers of errors:

| Stage | Symptom | Common causes |
| --- | --- | --- |
| **Initialization/discovery** | No factory, `getEngineByName` returns `null` | Unmatched provider/alias/loader/module |
| **Engine creation / configuration** | Provider fails to initialize, missing dependency, runtime exception | Engine implementation/deployment |
| **Script execution** | `ScriptException` or engine-reported error | Syntax/runtime semantics of the language |

If no engine is available, **do not call `eval` to test**: there is no object to execute; discovery must be resolved first.

## 15. Ordering Issues and Uncertainty of Discovery Results

In an environment containing multiple providers:

- `getEngineFactories()` should not be treated as a list with a fixed order by vendor name.
- Factories may publish overlapping aliases; for example, multiple engines may all accept `"javascript"`.
- A `ScriptEngineManager` may pick a factory via its discovery/association mechanism, but **do not rely on an arbitrary order to select a critical implementation**.
- If the application requires a specific engine, configure **implementation name + version policy** and verify `engine.getFactory().getEngineName()/getEngineVersion()` after lookup.
- When the application owns a trusted factory, you can instantiate directly from the factory or register an explicit association instead of hoping the "first" engine is the right one.
- Creating a new manager may yield a different list if the runtime class loader/module layer has changed; a manager does not automatically become a continuous watcher for every JAR loaded later.

Keep expected values in configuration and run integration tests in the same deployment environment. Do not rely solely on unit tests running on a developer machine when production uses a different container image or class loader.

## 16. JAR, Classpath, Module Path: What to Check When "Installed but Still Not Visible"?

If you have a JSR-223 provider from an external library, the diagnostic order should be:

1. **Confirm the dependency is present at runtime**, not only in compile-time/test scope.
2. For a JAR on the **classpath**, verify that the path `META-INF/services/javax.script.ScriptEngineFactory` actually exists in the output JAR.
3. Open the service file and check the exact fully qualified provider class name; the package/class must be on the same classloader or parent visibility path.
4. The factory must implement `javax.script.ScriptEngineFactory`, and the class/dependencies must be compatible with the running JDK.
5. For a **named module**, check that `module-info.class` has `provides javax.script.ScriptEngineFactory with ...` and the module is resolved in the runtime layer.
6. Create `ScriptEngineManager` with the appropriate loader; check the thread context loader if using the default constructor.
7. **Print `getEngineFactories()`** and the metadata of each factory to distinguish "provider not visible" from "wrong alias".
8. If the right factory is visible but `getEngineByName` returns `null`, compare aliases; try extension/MIME **only when the provider publishes them**.
9. If the application uses a shaded/fat JAR, check that the packaging process **did not drop/overwrite multiple service files** from different dependencies.
10. If engine instance creation fails, check dependency conflicts, class loading errors, service configuration, and logs; do not assume everything is a script syntax error.
11. When deploying containers, compare the **JDK image** and classpath/runtime module path between dev and production.
12. If there are multiple classloaders, confirm the provider resides in the exact loader/layer that the manager actually uses.

A few common inspection commands:

```bash
jar tf engine-provider.jar
java --describe-module java.scripting
```

The `jar tf` command shows the contents of the JAR so you can locate the service file/class; `java --describe-module java.scripting` helps confirm the module has `exports javax.script` and `uses javax.script.ScriptEngineFactory`.

In a Linux environment you can filter:

```bash
jar tf engine-provider.jar | grep 'META-INF/services/javax.script.ScriptEngineFactory'
```

And in PowerShell:

```powershell
jar tf engine-provider.jar | Select-String 'META-INF/services/javax.script.ScriptEngineFactory'
```

These commands **do not install the provider**; they help verify packaging paths. If the JAR is not on the runtime classpath/module path, merely seeing the service file inside the JAR is not enough.

## 17. Designing a Reliable Startup Workflow

An application that uses scripting as a dependency can implement this workflow:

```text
Application startup
    |
    v
Load configuration (required engine alias, version policy)
    |
    v
Create ScriptEngineManager with intended ClassLoader
    |
    v
Log/inspect safe metadata from getEngineFactories()
    |
    v
Lookup required engine by exact alias/extension/MIME
    |
    +--- null ---> Disable feature or fail startup with actionable message
    |
    +--- found --> Inspect factory identity and supported capabilities
                       |
                       v
                 Run a controlled smoke test
                       |
                       v
                 Ready to accept scripts
```

**Do not run user scripts as a smoke test.** Use a small, side-effect-free expression standardized for the specific language/provider. If the engine does not support `eval` for the smoke test you imagined, re-check the implementation contract instead of treating it as a broken engine.

For systems requiring the engine for security policies or critical financial calculations, prefer **fail fast** and do not automatically fall back to another engine with different semantics. For optional features, you can explicitly record a `DISABLED` status and provide instructions for installing a provider.

### Designing Useful Error Messages

Example message for operators:

```text
Required JSR-223 engine 'javascript' was not found.
Check runtime dependencies, META-INF/services or module provides,
ScriptEngineManager class loader, and factory aliases.
```

Much better than:

```text
java.lang.NullPointerException: Cannot invoke ScriptEngine.eval(...)
```

The message should be detailed enough to fix configuration, without needing to print all environment variables, script source, or secrets.

## 18. Testing: Without a Provider and With a Provider

Cases to test in the integration pipeline:

| Test | Setup | Expectation |
| --- | --- | --- |
| No provider | Clean JDK 17/test runtime | `getEngineFactories()` may be empty, `getEngineByName` is `null` |
| Unknown alias | Regardless of whether demo provider is present | `getEngineByName("__definitely_missing_engine__")` is `null` |
| Provider visible | Class present + valid META-INF/services | Factory appears in `getEngineFactories()` |
| Name lookup | Provider publishes `"mini"` | Engine is non-`null` |
| Extension lookup | `getExtensions()` contains `"mini"` | Engine is non-`null` |
| MIME lookup | `getMimeTypes()` contains `"text/x-mini"` | Engine is non-`null` |
| Custom alias | `registerEngineName("mini-alias", factory)` | Alias works on that manager |
| Loader isolation | Provider only in app loader | Platform-only manager does not see demo provider |
| Script smoke test | Demo engine `eval("upper:hello")` | Returns `"HELLO"` |
| Unsupported syntax | Demo engine `eval("not-supported")` | Throws `ScriptException` |
| Engine missing | Engine is null | Does not call eval, clear message or fail fast |

Test both **names present in `getNames()`** and *similar-looking* names that are not supported. Do not assume case is normalized automatically; check the exact aliases and variants registered by the provider.

### Testing Manager Independence

Two `ScriptEngineManager` instances do not share a JVM-wide manual associations table. If test A registers an alias with `registerEngineName`, do not expect test B creating a new manager to automatically see that alias unless the factory is published via SPI or test B registers it again.

### Packaging Tests

Run the real jar/fat-jar, not only unit tests inside an IDE. When packaging, Java classes and service descriptors must be copied/merged accurately. A provider that works when running `java -cp classes ...` but disappears after packaging is a sign of a packaging or classloader issue.

## 19. Security Risks: Discovery Is Not a Sandbox

`ScriptEngineManager` only resolves **who is capable of running scripts**. It does not guarantee:

- That the engine does not perform file/network I/O.
- That the engine cannot see sensitive Java objects from bindings.
- That scripts do not access resources outside policy.
- That engine execution has a time limit/CPU quota.
- That an `eval` called from another thread is safe.
- That the provider class is trustworthy or has no side effects in its constructor.

A scripting engine should be treated as **a code-execution component** that may have powerful host access. Only use approved providers and declare dependencies explicitly. For untrusted code, consider process/container isolation, the engine's permission model, worker-process timeouts, input validation, and safe logging.

An unexpected provider appearing on the classpath can change alias lookup results. Therefore, critical applications should verify the factory's identity/version and control the runtime dependency graph.

Never try to make the system "run by any means" by invoking an unknown-origin factory or switching scripts to another engine without verifying semantics and security policy.

## 20. Common Errors and How to Fix Them

| Error | Why it happens | How to handle |
| --- | --- | --- |
| `NullPointerException` at `engine.eval(...)` | Engine can be `null` after lookup | Check null first, fail fast/degrade per contract |
| `getEngineFactories()` is empty on JDK 17 | No JSR-223 provider visible | Install/run a suitable provider or disable the feature |
| JavaScript lookup is null | Nashorn is no longer bundled; no replacement provider or wrong alias | Check `getNames()`, dependencies, loader |
| `.getEngineByName("JavaScript")` differs from actual alias | Provider does not publish that name | Use an exact name in `getNames()` |
| `getEngineByExtension("file.mini")` is null | API expects an extension token | Extract and pass `"mini"` |
| Using a MIME type not published by the factory | No mapping exists | Check `getMimeTypes()` |
| Works in IDE, running JAR cannot find engine | Service file/dep missing in artifact | Check packaging/merging of service resources |
| Module JAR on module path but not discovered | Provider module not properly resolved/bound | Check `provides`, module layer, and service binding |
| App loader sees provider, platform loader does not | Classloader visibility differs | Create manager with the intended loader |
| `new Factory()` works directly but manager doesn't see it | SPI/registration not declared | Add `META-INF/services`/`provides` or register the factory |
| After `registerEngineName`, another part of app still gets null | Registration belongs only to the manager instance | Register in the right place or provide system-wide SPI |
| `eval` throws `ScriptException` | Provider exists, script has an error | Check script syntax/runtime and exception |
| Concurrent use of `engine` fails | Provider does not guarantee thread safety | Check `THREADING` metadata, how engines/contexts are created |
| Thinking `getEngineName()` is a short alias | Implementation metadata differs from `getNames()` | Use `getNames()` for lookup |
| Factory list shows engine A, but alias picks engine B | Multiple providers/registrations share an alias | Pin provider/config, inspect the factory of the created engine |
| Java 17 compiles `javax.script` so JS must be present | API still exists, implementation may be absent | Test runtime in the actual deployment |

## 21. Self-Check Exercises (with Answers)

1. **What does `new ScriptEngineManager()` use to find engines?** The service provider mechanism for `ScriptEngineFactory`, using the TCCL of the initializing thread.
2. **What does `getEngineByName` return when no matching factory is found?** `null`.
3. **Why can calling `.eval()` immediately throw an NPE?** Because the returned engine reference is `null`.
4. **Does an empty `getEngineFactories()` mean the `java.scripting` module does not exist?** No. The API can exist without any implementation.
5. **From which JDK version was Nashorn removed from the JDK?** JDK 15.
6. **Does Java 17 still have `javax.script.ScriptEngineManager`?** Yes, in the `java.scripting` module.
7. **What are the three main lookup methods?** Name/alias, extension, MIME type.
8. **Does `getEngineByName` rely on `getEngineName()` or `getNames()`?** It relies on registered aliases or `getNames()`.
9. **Does a factory publishing `"mini"` and `"mini-demo"` guarantee `"MiniDemo"` is an alias?** No, unless the factory also includes `"MiniDemo"` in `getNames()`.
10. **What is the SPI resource path for the classpath?** `META-INF/services/javax.script.ScriptEngineFactory`.
11. **What does the SPI resource contain?** Fully qualified binary class names of factories, one name per line.
12. **In a named module, what is the proper way to declare a provider?** `provides javax.script.ScriptEngineFactory with ...` in `module-info.java`, with the module resolved and the service visible.
13. **Is `new ScriptEngineManager(null)` the same as the no-argument constructor?** No. `null` only searches factories bundled with the platform; the no-argument constructor uses the TCCL.
14. **Can changing the TCCL change discovery results?** Yes, because loader visibility differs; use the constructor taking an explicit loader when appropriate.
15. **Does `registerEngineName` install a new language engine?** No; it only maps a key to an existing factory.
16. **Does a manually registered factory necessarily appear in `getEngineFactories()`?** No; that list reflects SPI-discovered factories.
17. **Do `getEngineByName("mini")` and `getEngineByExtension("mini")` return the same object?** Not guaranteed; the factory may create a new one each time.
18. **If an application is missing an engine needed for permission checks, should it automatically skip the check?** No; it must fail closed/fail fast according to policy.
19. **Is `ScriptException` the same as engine-not-found?** No. `ScriptException` is an error when a script is processed by an engine; a missing engine is a discovery error.
20. **Does having a `ScriptEngine` mean scripts are safe with all Java APIs?** No. JSR-223 is not a sandbox.
21. **Why is `java -cp classes EngineDiscoveryDemo` important?** The loader must see both the factory classes and the service resource in `classes`.
22. **What does the demo output `providerVisible=true` but `platformCanSeeMini=false` teach?** Discovery depends on the class loader, not just the presence of the Java API.
23. **When multiple engines share an alias, what needs to be checked?** Identity/version of the actually selected factory, selection policy, and classloader/registration.
24. **Is it necessary to override a JDK module to add a language engine?** No; external JSR-223 providers are discovered via SPI on the appropriate classpath/module path.
25. **When no provider is present in production, what should a helpful error message contain?** Requested name, visible aliases/providers, dependency/module/classloader hints; no leaked secrets.

## 22. Official Java SE 17 Documentation and Nashorn History

- [Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): constructors, ServiceLoader, `getEngineFactories`, the three lookup methods, null returns, and registrations.
- [Java SE 17 — `ScriptEngineFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): aliases, extensions, MIME types, versions, and factory metadata.
- [Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, context, bindings, and result contract.
- [Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): superclass supporting toy engine implementation and `eval` overloads.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): SPI deployment via `META-INF/services`, named module `provides`, and visibility.
- [Java SE 17 — `javax.script` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/package-summary.html): API and related interfaces.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): Nashorn removed from JDK 15; does not mean removing the JSR-223 API.
- [Oracle JDK 17 Migration Guide — Removed Tools and Components](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html): confirms Nashorn/JJS removal and migration impact.

**Conclusion:** `ScriptEngineManager` is a **factory discovery mechanism**, not a script engine. Inspect `getEngineFactories()` and metadata, look up by **alias/extension/MIME published by an actual provider**, and **handle `null` before `eval`**. On Java 17, failing to find `"javascript"` is a valid scenario because Nashorn has left the JDK; the solution is to deploy a **suitable JSR-223 provider with the right class loader/module**, or intentionally handle the feature as unavailable — do not mask the error with an NPE catch or assume an engine must be built in.