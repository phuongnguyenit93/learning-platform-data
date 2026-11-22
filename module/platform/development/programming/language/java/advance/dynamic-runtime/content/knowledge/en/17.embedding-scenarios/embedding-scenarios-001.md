# 17.1. The Role of `javax.script` and the Relationship Between the API and the Script Engine

In Java, **`javax.script` is the programming interface for embedding scripting languages into a Java application**, not a JavaScript, Python, or Groovy interpreter itself. This API belongs to the **standard module `java.scripting`** and is known as the **Scripting API / JSR 223**. It standardizes how an application *finds an engine, submits a script, passes variables, receives results, and handles errors* without tightly coupling all calling code to each language's proprietary API.

To **execute** a specific script, the application also needs a compatible **script engine implementation**: an engine that understands the language's syntax/semantics and actually runs the code. `ScriptEngineManager` can discover or accept engine registrations via `ScriptEngineFactory`, but it **does not interpret every language on its own**.

A practical point when learning with **Java 17+**: the Nashorn JavaScript engine was **removed from the JDK starting in Java 15 (JEP 372)**. Therefore, even though `import javax.script.*` compiles normally, `new ScriptEngineManager().getEngineByName("JavaScript")` **can return `null`** if the application does not provide an external engine. You cannot call `eval` on a nonexistent engine.

After this lesson, you can accurately distinguish the API, manager, factory, and engine; know the two ways to register/discover an engine; understand `Bindings` and `ScriptContext`; run a **Java 17 example that works without adding external libraries**; and recognize why an environment may lack a JavaScript engine and how to add an appropriate provider.

## 1. The Big Picture: The API Is the Contract, the Engine Is the Implementation

```text
                      Java Application
                           |
                           | calls language-neutral API
                           v
                      javax.script
       +-------------------+------------------+
       | ScriptEngineManager                   |
       | - discovers/registers ScriptEngineFactory |
       | - provides Global Bindings to engine  |
       +-------------------+------------------+
                           |
                           | selects factory by name/extension/MIME
                           v
       +--------------------------------------+
       | ScriptEngineFactory                   |
       | - metadata: language, version, names  |
       | - creates ScriptEngine instance       |
       +-------------------+------------------+
                           |
                           v
       +--------------------------------------+
       | ScriptEngine implementation           |
       | - parses/interprets/compiles script   |
       | - executes, returns Object/ScriptException |
       | - uses Bindings and ScriptContext     |
       +-------------------+------------------+
                           |
                           v
                Actual Language Semantics
          (MiniDSL, JavaScript, Groovy, ...)
```

Separate **responsibilities**, rather than only memorizing class names:

| Component | Who provides it? | What does it do? | What does it not guarantee on its own? |
| --- | --- | --- | --- |
| `javax.script` | JDK, module `java.scripting` | Common interfaces/base classes for script engines | Does not bundle a parser/runtime for every language |
| `ScriptEngineManager` | Standard JDK API | Discovery, factory lookup, engine creation, managing global bindings | Does not compile or run scripts in place of an engine |
| `ScriptEngineFactory` | **Engine provider** | Reports language name, MIME/extensions, version, and creates the engine | Does not necessarily execute scripts itself |
| `ScriptEngine` | **Engine provider** | `eval` source, variables, context, errors | Does not necessarily support compile/invoke, isolation, or thread safety |
| `Bindings` | Standard API, caller/engine | Maps variable names → Java objects | Does not force every language to map variables identically |
| `ScriptContext` | Standard API, caller/engine | Manages scopes and reader/writer/errorWriter | Not a security sandbox |
| `ScriptException` | Standard API, thrown by engine during script processing | Propagates script errors across the Java boundary | Does not mean all runtime errors are converted into the same type |

**Analogy:** `java.sql` defines the JDBC API, but communicating with a specific DB typically requires a JDBC driver. `javax.script` defines script-embedding capabilities, but running a specific language requires a compatible engine. The analogy does not mean the two APIs use the same discovery mechanism or transaction model.

### 1.1. Where Does `javax.script` Live?

In JDK 17, types such as `ScriptEngine`, `ScriptEngineManager`, `ScriptEngineFactory`, `Bindings`, `ScriptContext`, and `ScriptException` reside in the **`javax.script` package**, belonging to the **`java.scripting` module**.

The package name starting with `javax` is a **standard Java SE name**; it does not mean it is a third-party engine that must be downloaded. Nor is it `jakarta.script`. For applications running on the traditional classpath, the standard module is usually resolved for use. For a **named module**, declare the dependency explicitly:

```java
module my.scripting.app {
    requires java.scripting;
}
```

This `module-info.java` snippet is illustrative: the application module name is chosen by the project. Adding `requires java.scripting` allows **calling the API**, but still **does not create a JavaScript engine provider**.

### 1.2. `eval` Is a Contract, Not a Unified Syntax

The Java statement:

```java
Object value = engine.eval(scriptSource);
```

has a common structure regardless of the engine. However, the meaning of `scriptSource` depends on **the language supported by the engine**. For a JavaScript engine, an expression can use JavaScript syntax; for a Groovy engine, it is Groovy syntax; for MiniDSL in the example below, it is the `upper:name` command. There is no guarantee that `eval("1 + 2")` is always valid or produces the same type/result across every `ScriptEngine`.

Communicating via `Object` also does not specify whether a returned script value is an `Integer`, `Double`, `BigDecimal`, an engine-specific object, or `null`. Identify the contract of the **actual engine** and convert the result with checks.

## 2. `ScriptEngineManager`: Discovering Engines or Registering Factories

Common initialization:

```java
import javax.script.ScriptEngineManager;

ScriptEngineManager manager = new ScriptEngineManager();
```

The default constructor relies on the **thread context class loader** to locate `ScriptEngineFactory` implementations via the service provider mechanism. It can find engines provided by the JDK/vendor, application, libraries, or modules depending on the classpath/module path and loader visibility.

Key methods:

| API | Meaning |
| --- | --- |
| `getEngineFactories()` | Lists **factories found via discovery** |
| `getEngineByName("...")` | Looks up by engine name/alias, then uses the factory to create a `ScriptEngine` |
| `getEngineByExtension("...")` | Looks up by filename extension, e.g., `"mini"` |
| `getEngineByMimeType("...")` | Looks up by MIME type, e.g., `"text/x-mini"` |
| `registerEngineName(name, factory)` | Registers a name → factory mapping on a specific manager |
| `registerEngineExtension(ext, factory)` | Registers an extension → factory mapping |
| `registerEngineMimeType(mime, factory)` | Registers a MIME → factory mapping |
| `put(key, value)` / `get(key)` | Manages the variable map in the manager's **global scope** |
| `getBindings()` / `setBindings(bindings)` | Reads or replaces the global scope map |

Note: **`getEngineFactories()` is the list of discovered factories**; it does not necessarily list factories that you only **registered with `registerEngineName`** after creating the manager. Registration is a **lookup mapping table** and does not turn a factory into a provider JAR automatically discovered by `ServiceLoader`.

### 2.1. Returning `null` When No Engine Is Found

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine js = manager.getEngineByName("JavaScript");

if (js == null) {
    System.out.println("No JavaScript ScriptEngine provider available.");
} else {
    System.out.println("Found: " + js.getFactory().getEngineName());
}
```

This is an **environment-dependent snippet** with no fixed stdout: finding an engine depends on dependencies/providers/class loaders. `getEngineByName` **does not automatically download a library from the Internet**, has no automatic fallback to another language, and `null` means no matching factory was found or an engine could not be created under the current mechanism. Do not immediately call `js.eval(...)` before checking `js != null`.

If no provider is present, `manager.getEngineFactories()` may be an empty list. This is a completely valid state of the API and does not prove that the `java.scripting` module is missing.

### 2.2. Java 17: Nashorn Is No Longer Bundled

Directly relevant history:

- **Java 6:** Scripting API (JSR 223) is available in Java SE.
- **Java 8:** Oracle/OpenJDK integrates the Nashorn JavaScript engine, typically allowing `"JavaScript"`/`"nashorn"` to be found in the corresponding environments.
- **Java 11:** Nashorn is marked *deprecated for removal*.
- **Java 15:** JEP 372 **removes the Nashorn JavaScript engine and `jjs`**, but **does not remove `javax.script`/`java.scripting`**.
- **Java 17+:** `javax.script` remains a standard API; to run JavaScript, you must add a compatible engine that is properly installed and registered/discovered. Not every external JavaScript engine is guaranteed to use the `"JavaScript"` alias.

Thus, the statement “Java 17 no longer has `javax.script`” is **false**; the accurate statement is “Java 17 no longer includes Nashorn by default in the standard JDK”. An application using a third-party library can still look up a `ScriptEngine` for JavaScript, Groovy, or another language.

**Note:** The `jrunscript` CLI and old examples running Nashorn do not prove a JavaScript engine is provided in the current runtime. Tools invoking the Scripting API also need a provider.

## 3. How Are Engines Discovered? `ScriptEngineFactory` and SPI

The factory acts as the **bridge** between a language name/discovery mechanism and the actual engine object. It provides metadata:

- `getEngineName()`, `getEngineVersion()` — implementation name and version.
- `getLanguageName()`, `getLanguageVersion()` — the language the engine handles.
- `getNames()` — aliases the manager can use for lookup.
- `getExtensions()` / `getMimeTypes()` — other mappings for scripts.
- `getScriptEngine()` — creates an engine instance.
- `getParameter(key)`, `getMethodCallSyntax`, `getOutputStatement`, `getProgram` — metadata/syntax depending on engine capabilities.

A class that **only** implements `ScriptEngine` without a suitable factory/provider **does not automatically appear** in `new ScriptEngineManager().getEngineFactories()`. There are two common paths:

**Path A — programmatic registration:** You already have a `ScriptEngineFactory` and explicitly call `manager.registerEngineName(...)`. This is how the standalone example in Section 6 works; no provider JAR is needed.

**Path B — service provider discovery:** Package the factory in a JAR/module and declare it for `ServiceLoader`. A new manager can automatically discover the factory if the provider is on the classpath/module path and class loader/module resolution is appropriate.

### 3.1. Classpath: The `META-INF/services` File

In a classpath JAR, the service descriptor filename is:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

The file contents are the **binary name of the class** implementing `ScriptEngineFactory`, one provider per line, for example:

```text
com.example.scripting.MyLanguageEngineFactory
```

The provider class must satisfy `ServiceLoader` rules, including instantiability according to the appropriate provider class mechanism, visibility, and valid dependencies. **Adding only the filename** without the factory bytecode and runtime implementation will not enable the manager to create an engine.

### 3.2. Named Module: `provides ... with ...`

In Java modules, a provider can declare:

```java
module my.mini.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.scripting.MyLanguageEngineFactory;
}
```

This is a **`module-info.java` template**, not a runnable project, because you must create the actual provider class and configure module resolution. An application with its own module needs `requires java.scripting` to use the API; the provider must be placed on the module path/resolved appropriately so the service mechanism can see it. Do not misspell the provider name and expect `ServiceLoader` to find the class automatically.

### 3.3. Factors That Cause Discovery to Fail

When the JAR is present but `getEngineByName` still returns null, check:

1. Does `META-INF/services/javax.script.ScriptEngineFactory` exist in the right JAR? Is its content the exact **binary class name**?
2. Can `ScriptEngineFactory` be seen and instantiated by the class loader? Are any runtime dependencies missing?
3. Does the factory return the right alias from `getNames()`? `"tiny"` is different from `"javascript"`; do not guess the alias from the JAR filename.
4. Was `ScriptEngineManager()` created **before** the classpath/class loader was changed? Manager discovery runs when constructing the manager; adding a provider later does not automatically update all existing managers.
5. If using the module path, is the provider module resolved and is `provides` declared properly?
6. Does `getEngineByName` find the factory, yet `getScriptEngine()` returns `null`/fails? That is a **factory/implementation** bug, not merely an alias issue.

`ScriptEngineManager(ClassLoader loader)` lets you choose the loader used for discovery; this can be useful in plugin frameworks, but it must respect lifecycle/class-loader isolation. Do not add JVM flags/module opens blindly just because an engine name was not found.

## 4. `ScriptEngine` and the Lifecycle of an `eval` Call

Once you have an engine:

```java
ScriptEngine engine = manager.getEngineByName("tiny");
if (engine == null) {
    throw new IllegalStateException("Missing engine: tiny");
}
Object result = engine.eval("upper:name");
```

Here `tiny` is the **custom MiniDSL** in Section 6, not a standard language provided by the JDK. In a real engine, `eval` accepts a `String` or `Reader` source; the implementation may parse, interpret, compile, or delegate to another language runtime. The return type is declared as `Object`. `eval` is typically used to execute a script snippet on the calling thread, though semantics and resource behavior are determined by the engine.

A `ScriptEngine` implementation must support the basic methods: `eval(String)`, `eval(Reader)` and the overloads taking `Bindings`/`ScriptContext`, `put/get`, `createBindings`, and `getFactory`. The `AbstractScriptEngine` class provides default implementations for several overloads so engine authors can focus on the two entrypoints `eval(String, ScriptContext)` and `eval(Reader, ScriptContext)`.

### 4.1. `AbstractScriptEngine` Is a Skeleton, Not an Interpreter

`AbstractScriptEngine` understands no syntax. It implements several `eval` overloads, manages the default `ScriptContext`, and handles `put/get`; the **subclass** defines how to parse/execute the source.

That is why a minimal engine can be built with:

```java
class MyEngine extends AbstractScriptEngine {
    // Must implement eval(String, ScriptContext),
    // eval(Reader, ScriptContext), createBindings(), getFactory().
}
```

This illustrative snippet is **not sufficient to compile**, because a real subclass must implement the abstract methods and typically needs constructors/imports. The complete example in Section 6 provides a full implementation.

### 4.2. `Compilable` and `Invocable` Are Optional Capabilities

Some engines also implement:

- `Compilable`: `compile(script)` returns a `CompiledScript`, suitable when a script is compiled once and run repeatedly; **not** every engine has this feature.
- `Invocable`: invokes functions/methods defined in the script environment via `invokeFunction`/`invokeMethod` or creates an interface proxy if supported by the engine; also **not required**.

Client code must check:

```java
if (engine instanceof Compilable c) {
    CompiledScript compiled = c.compile("some-engine-specific-source");
    Object output = compiled.eval();
} else {
    // Engine does not support the Compilable contract.
}
```

The snippet above illustrates **interface checking**; the source string must be replaced with real language code and may throw `ScriptException`. Never cast `(Compilable) engine` blindly. In the `MiniEngine` example, both `Compilable` and `Invocable` are **false**.

## 5. `Bindings` and `ScriptContext`: Passing Data Across the Java–Script Boundary

`Bindings` extends `Map<String, Object>`: keys are typically variable names; values are Java objects. `SimpleBindings` is the common implementation. `ScriptContext` manages multiple bindings scopes along with an input `Reader`, output `Writer`, and error `Writer`.

Two standard scopes:

| Scope | Constant | Purpose |
| --- | --- | --- |
| **Engine scope** | `ScriptContext.ENGINE_SCOPE` | State/variables attached to the engine or an eval call given separate bindings |
| **Global scope** | `ScriptContext.GLOBAL_SCOPE` | State shared from `ScriptEngineManager` to engines created by that manager |

Example with `ScriptEngineManager`:

```java
manager.put("city", "Hanoi");  // global scope of the manager
ScriptEngine engine = manager.getEngineByName("tiny");
engine.put("name", "Lan");     // ENGINE_SCOPE of the engine
```

When a factory creates an engine through a manager, the manager attaches its **global Bindings** to the new engine's `GLOBAL_SCOPE`. For an engine using the standard scope lookup policy, `context.getAttribute("name")` searches `ENGINE_SCOPE` before `GLOBAL_SCOPE`. In MiniDSL in Section 6, `get:city` reads Global if Engine does not have a matching key; `upper:name` reads Engine.

**Distinguishing `engine.get` from `context.getAttribute`:** In `AbstractScriptEngine`, `engine.get("name")` reads `ENGINE_SCOPE` directly, whereas `context.getAttribute("city")` can search across scopes. Thus, a global variable may be accessible from a script while `engine.get("city")` does not necessarily return that global variable.

### 5.1. `eval(String, Bindings)` Creates a Temporary Scope for the Evaluation

```java
Bindings local = engine.createBindings();
local.put("name", "Mai");

Object result = engine.eval("upper:name", local);
```

With `AbstractScriptEngine`, the overload accepting `Bindings` creates a `ScriptContext` using `local` as the **`ENGINE_SCOPE` for that evaluation**, while keeping the remaining scopes/reader/writer from the default context according to the API rules. It is **not** a permanent `engine.setBindings(local, ENGINE_SCOPE)`. After the evaluation, `engine.eval("upper:name")` can continue reading `name="Lan"` from the original engine context.

This is a good tool for limiting data pollution between scripts, but it is not enough to claim sandboxing; scripts can still access provided objects or APIs permitted by the engine.

### 5.2. `ScriptContext` for Clearer I/O and State

`ScriptContext` provides these APIs:

```java
ScriptContext context = engine.getContext();
Bindings globals = engine.getBindings(ScriptContext.GLOBAL_SCOPE);
Bindings locals = engine.getBindings(ScriptContext.ENGINE_SCOPE);

context.setWriter(new java.io.StringWriter());
context.setErrorWriter(new java.io.StringWriter());
```

This is an illustrative snippet; `engine` must be initialized beforehand. An engine may respect `context.getWriter()` to send script output to this writer, but **print semantics and I/O types depend on the implementation**. Setting a `StringWriter` does not prevent a script from using other APIs to write to files/network if the engine allows it. If `GLOBAL_SCOPE` is null in an engine not created by a manager, you must configure the context appropriately.

### 5.3. Do Not Treat `Bindings` as Object Serialization

Java objects placed into `Bindings` can be referenced by scripts according to the engine's Java–language interoperability capabilities; not every engine understands every object type. When receiving output, check `instanceof`/type adapters and handle `null`. Different engines may also differ in numeric coercion, variable assignment, global functions, and exception types. The common API does not standardize entire languages.

## 6. Complete Java 17 Program Requiring No External Engine

To distinguish the **framework API** from the **engine implementation**, this example builds a toy engine named **MiniDSL**. It is intentionally **not JavaScript** and understands only three command forms:

- `get:key`: reads a variable from `ScriptContext`.
- `upper:key`: reads a `String` variable and returns its uppercase version.
- `set:key=value`: writes a variable into `ENGINE_SCOPE`.
- Multiple commands can be written across multiple lines; returns the result of the last non-empty command.

The engine part only serves to represent a minimal language. `ScriptEngineManager` still manages factory selection and global bindings through the **standard API**. The code lives in a single file, **`ScriptApiRelationshipDemo.java`**, using the Java 17 API without downloading a JavaScript engine:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import java.util.Locale;
import javax.script.*;

public class ScriptApiRelationshipDemo {
    public static void main(String[] args) throws ScriptException {
        System.out.println("api.module=" + ScriptEngine.class.getModule().getName());
        ScriptEngineManager manager = new ScriptEngineManager();
        manager.put("city", "Hanoi");
        MiniFactory factory = new MiniFactory();
        manager.registerEngineName("tiny", factory);
        manager.registerEngineExtension("mini", factory);
        manager.registerEngineMimeType("text/x-mini", factory);

        ScriptEngine engine = manager.getEngineByName("tiny");
        System.out.println("engine.found=" + (engine != null));
        System.out.println("engine.factory=" + engine.getFactory().getEngineName());
        System.out.println("engine.language=" + engine.getFactory().getLanguageName());
        System.out.println("extension.found="
                + (manager.getEngineByExtension("mini") != null));
        System.out.println("mime.found="
                + (manager.getEngineByMimeType("text/x-mini") != null));

        engine.put("name", "Lan");
        System.out.println("eval.upper=" + engine.eval("upper:name"));
        System.out.println("global.city=" + engine.eval("get:city"));
        System.out.println("engine.scope="
                + engine.getBindings(ScriptContext.ENGINE_SCOPE).get("name"));

        Bindings local = engine.createBindings();
        local.put("name", "Mai");
        System.out.println("local.upper=" + engine.eval("upper:name", local));
        System.out.println("original.upper=" + engine.eval("upper:name"));

        System.out.println("eval.set=" + engine.eval("set:greeting=Hello"));
        System.out.println("engine.get=" + engine.get("greeting"));
        System.out.println("reader="
                + engine.eval(new StringReader("get:greeting")));
        System.out.println("multi=" + engine.eval(
                factory.getProgram("set:other=hi", "upper:other")));
        try {
            engine.eval("unknown-command");
        } catch (ScriptException e) {
            System.out.println("script.error=" + e.getClass().getSimpleName());
        }
        System.out.println("compilable=" + (engine instanceof Compilable));
        System.out.println("invocable=" + (engine instanceof Invocable));
    }

    public static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "EducationalMini"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("mini"); }
        @Override public List<String> getMimeTypes() {
            return List.of("text/x-mini");
        }
        @Override public List<String> getNames() { return List.of("tiny"); }
        @Override public String getLanguageName() { return "MiniDSL"; }
        @Override public String getLanguageVersion() { return "1"; }
        @Override public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.NAME -> "tiny";
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                default -> null;
            };
        }
        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) {
            return null; // MiniDSL does not support Java-object call syntax.
        }
        @Override public String getOutputStatement(String value) {
            return null; // MiniDSL does not support print statements.
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniEngine(this);
        }
    }

    public static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        public MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override public Object eval(String source, ScriptContext context)
                throws ScriptException {
            Object result = null;
            for (String line : source.split("\\R")) {
                if (!line.isBlank()) {
                    result = executeOne(line.trim(), context);
                }
            }
            return result;
        }

        private Object executeOne(String command, ScriptContext context)
                throws ScriptException {
            if (command.startsWith("get:")) {
                return context.getAttribute(command.substring(4).trim());
            }
            if (command.startsWith("upper:")) {
                Object value = context.getAttribute(command.substring(6).trim());
                if (!(value instanceof String text)) {
                    throw new ScriptException("Expected String variable");
                }
                return text.toUpperCase(Locale.ROOT);
            }
            if (command.startsWith("set:")) {
                String assignment = command.substring(4);
                int index = assignment.indexOf('=');
                if (index <= 0) {
                    throw new ScriptException("Expected set:name=value");
                }
                String name = assignment.substring(0, index).trim();
                String value = assignment.substring(index + 1);
                context.setAttribute(name, value, ScriptContext.ENGINE_SCOPE);
                return value;
            }
            throw new ScriptException("Unknown MiniDSL command");
        }

        @Override public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] chunk = new char[1024];
            try {
                int n;
                while ((n = reader.read(chunk)) != -1) {
                    source.append(chunk, 0, n);
                }
            } catch (IOException e) {
                throw new ScriptException(e);
            }
            return eval(source.toString(), context);
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

Compile and run in the directory containing the file:

```bash
javac --release 17 ScriptApiRelationshipDemo.java
java ScriptApiRelationshipDemo
```

**Exact** `stdout` from the tested program:

```text
api.module=java.scripting
engine.found=true
engine.factory=EducationalMini
engine.language=MiniDSL
extension.found=true
mime.found=true
eval.upper=LAN
global.city=Hanoi
engine.scope=Lan
local.upper=MAI
original.upper=LAN
eval.set=Hello
engine.get=Hello
reader=Hello
multi=HI
script.error=ScriptException
compilable=false
invocable=false
```

The program compiled successfully with `javac --release 17` and ran on OpenJDK 24 with the 18 lines of output above. It does not depend on whether the JDK has Nashorn or any external script engine: `MiniFactory` and `MiniEngine` are created in source and registered manually.

### 6.1. Reading the Output by Layer of Responsibility

**`api.module=java.scripting`:** the `ScriptEngine` interface genuinely belongs to the `java.scripting` module, regardless of whether any language implementation has been installed.

**`engine.found=true`, `engine.factory=EducationalMini`:** the manager finds the factory registered by the program and then calls `getScriptEngine()`. If you omit `registerEngineName("tiny", factory)` and also do not package an SPI provider, `getEngineByName("tiny")` is not guaranteed to be found.

**`extension.found=true`, `mime.found=true`:** the extension and MIME aliases are registered on **this same manager instance**. They do not prove the OS has installed a file association or an HTTP server automatically recognizes `.mini`; these are solely lookup mappings in the scripting API.

**`eval.upper=LAN`:** the engine understands the MiniDSL command `upper:name`; the manager does not parse the syntax itself. `MiniEngine.executeOne` is where the language handling happens.

**`global.city=Hanoi`:** `manager.put("city", ...)` places the variable in global scope, and the manager attaches global bindings to the new engine; `context.getAttribute` inside the engine finds it.

**`engine.scope=Lan`:** `engine.put("name", "Lan")` puts `name` into `ENGINE_SCOPE`, verified with `getBindings(ENGINE_SCOPE)`.

**`local.upper=MAI` and `original.upper=LAN`:** `eval(String, Bindings)` uses the local map for a single evaluation; the `name=Lan` state in the default engine context remains intact.

**`eval.set=Hello` / `engine.get=Hello`:** the custom implementation handles `set:greeting=Hello` via `context.setAttribute(..., ENGINE_SCOPE)`. The application then reads the variable via `engine.get("greeting")`.

**`reader=Hello`:** the overload taking a `Reader` converts the content into source and applies the same MiniDSL semantics. `reader` is a source channel, not a mandatory file system interface.

**`multi=HI`:** the factory joins two commands into a multi-line script; `MiniEngine` reads line by line and returns the result of the last command. This is a property of this specific MiniDSL, not a universal meaning of `getProgram` across all engines.

**`script.error=ScriptException`:** an invalid command is detected by **MiniEngine**, which throws `ScriptException`. The API defines the exception type; the engine decides when syntax is invalid and what message to provide.

**`compilable=false` / `invocable=false`:** basic `eval` capability **does not automatically imply** the extension interfaces. MiniDSL does not provide compile or invokeFunction.

### 6.2. Intentional Limitations of MiniDSL

MiniDSL is not a real JavaScript/Groovy interpreter; it has no complex AST, class isolation, sandbox, expression grammar, debug line numbers, module loader, or optimizations. `getMethodCallSyntax` and `getOutputStatement` of the toy factory return `null` because MiniDSL does not support those two syntax forms. That is an explicitly stated limitation in an educational example; do not treat it as a template for a full-featured production engine.

In practice, an engine provider must define its own full parser/evaluator, conversions between Java and script values, error reporting, resource management, concurrency, and security policy. `javax.script` only provides the **interface and integration infrastructure**, not solutions to those problems on the engine's behalf.

## 7. Putting the Factory from Section 6 into the `ServiceLoader` Mechanism

The main example intentionally uses manual registration so it **does not depend on SPI packaging**. When deploying a provider JAR, the engine factory can appear automatically after discovery if packaged properly.

### 7.1. Creating the Service-Provider File

With the source declared as:

```java
public static final class MiniFactory implements ScriptEngineFactory
```

nested inside `ScriptApiRelationshipDemo`, the **binary name** of the provider nested class is:

```text
ScriptApiRelationshipDemo$MiniFactory
```

Therefore, the service descriptor file must have the **exact** path:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

and a single-line content:

```text
ScriptApiRelationshipDemo$MiniFactory
```

Note: `$` is a **literal character in the binary class name of a nested class**, not a shell variable to be expanded. If creating the file via shell, quote it appropriately (e.g., single quotes in Bash). In real applications, providers are usually top-level classes in a package, so the file contains `com.company.MyScriptEngineFactory`.

### 7.2. Packaging Class Files and the Service Descriptor Properly

A provider JAR has the conceptual structure:

```text
mini-engine.jar
 ├─ ScriptApiRelationshipDemo.class
 ├─ ScriptApiRelationshipDemo$MiniFactory.class
 ├─ ScriptApiRelationshipDemo$MiniEngine.class
 └─ META-INF/
     └─ services/
         └─ javax.script.ScriptEngineFactory
```

Ensure that the dependent classes and the service file are actually inside the JAR. You can inspect it with:

```bash
jar --list --file mini-engine.jar
```

With `mini-engine.jar` present on the application's classpath **before creating the manager**, the manager can use `ServiceLoader` to find the factory. Another client can call:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class DiscoverMini {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new ScriptEngineManager().getEngineByName("tiny");
        if (engine == null) {
            throw new IllegalStateException("MiniDSL provider not found");
        }
        engine.put("name", "An");
        System.out.println(engine.getFactory().getEngineName());
        System.out.println(engine.eval("upper:name"));
    }
}
```

This is a **standalone client**, but it **requires the aforementioned provider JAR** at runtime. If the provider is packaged and visible to the class loader properly, the expected output is:

```text
EducationalMini
AN
```

You can also use a custom top-level factory and declare `META-INF/services` properly instead of the example's nested class. `ServiceLoader` does not require the client to call `registerEngineName` once the provider is discovered and `getNames()` contains `"tiny"`.

### 7.3. Why Can `getEngineFactories()` and `registerEngineName` Differ for the Same Engine?

`registerEngineName` creates a direct mapping; it tells the manager **which factory to choose when looking up a specific name**. `getEngineFactories()` reports the list of factories the manager discovered via the service-provider mechanism. A manually registered factory does not necessarily appear in the discovery list. Therefore, do not use `manager.getEngineFactories().isEmpty()` to conclude that `manager.getEngineByName("tiny")` must be null **after calling registerEngineName**. Check actual lookups and distinguish the factory-provisioning paths.

## 8. Common Errors When Using `javax.script`

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `import javax.script.*` compiles, but `getEngineByName("JavaScript") == null` | API is present, engine provider is missing or alias is not registered | Check JDK/version, factories, provider dependencies, and `getNames()` |
| `NullPointerException` on `engine.eval(...)` | `engine` is null due to failed lookup | Check `engine == null` before eval; report a clear “missing provider” error |
| `getEngineFactories()` is empty | Manager discovered no factories via ServiceLoader | Check classpath/module path, META-INF/services, class loader, named modules |
| Provider JAR is present but name lookup fails | Alias does not match `getNames()`, or JAR is not visible to the class loader | Use a name the factory supports; inspect service file and class loader |
| Name lookup succeeds but `eval` throws `ScriptException` | Invalid script syntax/semantics or engine-reported error | Inspect `ScriptException` message/line/column/cause and source language |
| `ClassCastException` on `eval` result | Application assumes wrong return type | Check `instanceof`, schema, and engine-specific conversion |
| `ClassNotFoundException`, `NoClassDefFoundError`, `ServiceConfigurationError` during discovery | Missing dependent JAR, wrong provider class name, or init failure | Check runtime dependencies, service descriptor packaging, logs |
| `engine instanceof Compilable` is false | Implementation does not support compilation | Use `eval` or choose another engine with the needed feature |
| `engine instanceof Invocable` is false | No `invokeFunction` capability via JSR 223 | Do not cast blindly; check provider capabilities |
| Global variable does not appear in script | Custom engine does not use `ScriptContext` properly or manager has not attached global scope | Check `manager.put` before engine creation, `getContext`, scope lookup |
| Variable `name` is overwritten after an `eval` | Shared default `ENGINE_SCOPE` or engine does not isolate state | Use separate `eval(script, Bindings)`, separate context, or separate engine depending on provider |
| Same script runs on engine A but fails on B | Different language/version/dialect/host interop | Document engine name+version and language name+version; test compatibility |

### 8.1. Diagnosing the Actual Engine Before `eval`

A recommended pattern in applications:

```java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println("Engine=" + factory.getEngineName()
            + ", language=" + factory.getLanguageName()
            + ", names=" + factory.getNames());
}

ScriptEngine engine = manager.getEngineByName("your-supported-alias");
if (engine == null) {
    throw new IllegalStateException("No matching engine provider found");
}
```

This is an **environment-dependent snippet** with no standard stdout, and `"your-supported-alias"` must be replaced with an alias published by a real provider. It does not download an engine from the network. When debugging deployments, also log the classpath/module path, TCCL, and provider version if needed, but avoid logging scripts containing secrets.

## 9. Security, Performance, and Thread Safety Belong to the Engine

### 9.1. `javax.script` Is Not a Sandbox

`Bindings` can expose Java objects to scripts. Depending on the engine, a script may call object methods, read/write resources, or perform dangerous operations. `javax.script` **does not** define an isolation mechanism to block file system, network, CPU/memory abuse, or reflection. Calling `eval` on a string from an **untrusted** user with a powerful runtime can create serious security risks.

System-level safeguards may include: accepting only controlled scripts, using a restricted DSL instead of a general-purpose language, validation, least-privilege execution permissions, process isolation, resource limits, and timeouts genuinely enforced by the host. Do not treat `ScriptContext.setWriter` or omitting a key from `Bindings` as a reliable protection if the engine still permits access to other APIs.

### 9.2. The API Does Not Guarantee Every `ScriptEngine` Is Thread-Safe

A `ScriptEngine` often holds state/`Bindings`; using the same instance across multiple threads can cause race conditions depending on the implementation. `ScriptEngineFactory.getParameter("THREADING")` can provide information about the engine's threading model per JSR 223 conventions, though specific behavior still needs to be verified against provider documentation. Common values may include `"MULTITHREADED"`, `"THREAD-ISOLATED"`, `"STATELESS"`, or `null`, each carrying its own conditions.

Do not assume:

```java
// Example that is NOT safe to use by default with every engine:
static ScriptEngine shared = new ScriptEngineManager()
        .getEngineByName("some-language");
// Multiple requests freely call shared.eval(...) concurrently.
```

This is **cautionary pseudocode**, not a recommended configuration: depending on the provider, you may need to create an engine per request, use locks, pool with a clear contract, or use another isolation mechanism. `ENGINE_SCOPE` and `GLOBAL_SCOPE` can also hold shared mutable objects, so simply “having multiple engine instances” does not necessarily eliminate all shared state.

### 9.3. Initialization Cost, Compilation, and Caching

Finding a factory with `ScriptEngineManager` and creating an engine has an initialization cost that depends on the provider. Each `eval` may parse/compile or interpret. If `Compilable` is supported, `CompiledScript` may allow reusing the compiled part within the engine's contract; however, not every `CompiledScript` is thread-safe or state-independent.

Performance optimizations must be **measured with realistic workloads** and must preserve the semantics of `Bindings`, global scope, instance lifetime, and security. Do not cache a global `ScriptEngine` unless the provider guarantees concurrent use.

## 10. Application Scenarios and Choosing a Solution

**Scenario A — processing a small formula/DSL in an internal system:** If the syntax is very limited, writing a dedicated parser may be safer; there is no need to add a general-purpose JavaScript engine. MiniDSL in this lesson illustrates layering, **not** a production parser.

**Scenario B — embedding an existing language:** Choose a JSR 223 engine that supports your Java version, security requirements, and needed features; add valid dependencies and verify the factory alias. If a language library only has its own embedding API without a `ScriptEngineFactory` adapter, `ScriptEngineManager` will not automatically know how to run it.

**Scenario C — multi-tenant plugin scripts:** Design class loader/module management, engine lifecycle, separate `Bindings`, script trust levels, and isolation. Do not assume `GLOBAL_SCOPE` is suitable for storing sensitive data across all requests.

**Scenario D — migrating from JDK 8/11 to Java 17:** Do not only check compile-time compatibility of `javax.script`. Check runtime discovery and how to handle Nashorn's removal; switching engines requires evaluating **differences in syntax, semantics, data types, interop, and security**, not just changing an alias.

**Scenario E — writing your own engine for a small language:** Provide a `ScriptEngine` implementation, standard factory metadata, registration or an SPI provider; use `AbstractScriptEngine` when appropriate and test scopes, I/O, exceptions, and threading.

## 11. Self-Check Exercises

**A.** Why does `import javax.script.ScriptEngine` compile on Java 17 while `getEngineByName("JavaScript")` returns `null`?

**B.** You have a class implementing `ScriptEngine`, but you neither register a factory nor provide `META-INF/services`. Will `new ScriptEngineManager()` definitely find it?

**C.** In the MiniDSL example, why can `manager.put("city","Hanoi")` be read by `eval("get:city")`, while `engine.put("name","Lan")` is in a different scope?

**D.** After creating `Bindings local` and calling `engine.eval("upper:name", local)`, is the variable in the default `ENGINE_SCOPE` necessarily replaced by the name in `local`?

**E.** When `engine.eval(...)` returns an `Object`, can you cast directly to `(Integer)` without any check? If a script is invalid, what standard exception type is typically used?

**F.** If `engine` already supports `eval`, does it definitely implement `Compilable` and `Invocable`?

**G.** `getEngineFactories()` is empty, yet the application just called `manager.registerEngineName("tiny", factory)`. Can you conclude from this that `getEngineByName("tiny")` is definitely null?

**H.** Why can a `ScriptEngine` be unsafe to share across threads, and why is `javax.script` not a sandbox?

**I.** In a modular app using `javax.script`, is adding `requires java.scripting` enough to run Groovy/JavaScript? What else is needed?

**Answers:**

- **A:** The API in `java.scripting` still exists; Nashorn was removed from the JDK starting in Java 15. Without a suitable provider, the manager returns null.
- **B:** No. The manager looks up **`ScriptEngineFactory`** via SPI or registered mappings; it does not scan all objects implementing `ScriptEngine`.
- **C:** `manager.put` writes to the shared `GLOBAL_SCOPE`, while `engine.put` writes to the instance's `ENGINE_SCOPE`; `ScriptContext` allows the engine to read variables by scope.
- **D:** No. With `AbstractScriptEngine`, the `eval(String, Bindings)` overload uses the passed bindings for that evaluation and does not modify the engine's default bindings by default.
- **E:** No. The runtime type is determined by the engine; checking and conversion are required. Script errors are typically represented by `ScriptException`.
- **F:** No. Those two interfaces are optional extensions and must be checked with `instanceof`.
- **G:** No. `registerEngineName` enables direct lookup even though the factory does not necessarily appear in the discovery list.
- **H:** The engine's state/Bindings may be mutable and the provider may not guarantee thread safety; the API does not restrict capabilities, file/network/CPU usage of script code.
- **I:** Not enough. `requires` only grants access to call the standard API; a language-appropriate engine implementation/provider must be added, visible on the classpath/module path, and matched by alias.

## 12. Official Documentation

- [Oracle Java SE 17 — module `java.scripting`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/module-summary.html): module defining the Scripting API and using the `ScriptEngineFactory` service.
- [Oracle Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): constructors, discovery, registrations, null when no engine is found, and manager `GLOBAL_SCOPE`.
- [Oracle Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval` API, bindings, context, and overloads.
- [Oracle Java SE 17 — `ScriptEngineFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): engine metadata, alias/extension/MIME, creation.
- [Oracle Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): base implementations, default ScriptContext, and `eval(..., Bindings)`.
- [Oracle Java SE 17 — `ScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html): `ENGINE_SCOPE`/`GLOBAL_SCOPE`, I/O, and scoped attributes.
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): confirms removal in Java 15, without removing the `javax.script` API.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): service-provider discovery mechanism for classpath and modules.

**Summary:** `javax.script` is an **integration contract** that lets Java code share common operations for discovering and invoking scripts. `ScriptEngineFactory` brings the real implementation into the system, while `ScriptEngine` is responsible for the language and execution. `ScriptEngineManager` can only find factories that have been properly registered or discovered; **having the API does not mean having a JavaScript engine**, especially from Java 15 onward when Nashorn was removed from the JDK. Always verify the provider, choose bindings/context carefully, and evaluate security/thread-safety properties before embedding scripts into an application.
