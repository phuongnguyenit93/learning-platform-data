# Explicit Engine Registration or Building ScriptEngineFactory and AbstractScriptEngine (JSR-223)

## 1. Problem: The Host Needs to Run a Scripting Language Through a Unified Contract

In Java, the **JSR-223 Scripting API** (`javax.script` package, standard `java.scripting` module) defines interfaces for a **host** application to communicate with a **script engine**. The host can request script evaluation, pass data into the engine, receive results, capture output, or inspect language metadata without coupling host code directly to individual implementations.

There are two ways to bring an engine into the system:

1. **Explicit registration:** if the host already holds a `ScriptEngineFactory`, call `ScriptEngineManager.registerEngineName`, `registerEngineExtension`, or `registerEngineMimeType` to map a name/file extension/MIME type to the factory. This is very useful in plugin runtimes or when you want strict control over which engine is activated.
2. **Building a custom engine:** implement `ScriptEngineFactory` along with an engine extending `AbstractScriptEngine`, then register the factory explicitly or package it as a service provider for automatic discovery by the manager.

These two options are **complementary**, not mutually exclusive: an engine you build can still be registered explicitly; conversely, a third-party library's engine can also be registered explicitly using the factory provided by that library.

A note on modern JDKs: Java SE provides the **Scripting API**, but **does not guarantee bundling a JavaScript engine or an engine for any specific language**. Nashorn is no longer packaged in the JDK starting with JDK 15; having `getEngineByName("JavaScript")` return `null` in many modern environments is normal. To use a specific language, you must supply a compatible implementation on the classpath/module path or build an engine yourself.

### 1.1. Role of Each Component

| Component | Responsibility | Owner |
| --- | --- | --- |
| `ScriptEngineManager` | Discovers engine factories, manages name/extension/MIME mappings, issues engines | Host/application |
| `ScriptEngineFactory` | Declares engine name, version, language, aliases, file formats; creates engines | Engine provider |
| `ScriptEngine` | Evaluates scripts, manages contexts and bindings | Language implementation |
| `AbstractScriptEngine` | Base class implementing convenience operations of `ScriptEngine` | JDK, subclassed by engine |
| `ScriptContext` | Execution context: scopes, writer, reader, error writer | Host or engine |
| `Bindings` | Name → Java object mapping for script variables/values | Per scope/context |
| `ScriptException` | Error reading/evaluating scripts, optionally with line/column | Thrown by engine, handled by host |

Basic flow:

```text
Host
  |
  | new ScriptEngineManager()
  | registerEngineName("math", myFactory) [optional]
  v
ScriptEngineManager
  |
  | getEngineByName("math")
  v
ScriptEngineFactory ---- getScriptEngine() ----> ScriptEngine
                                                |
                                    eval(script, ScriptContext)
                                                |
                                  Bindings / Reader / Writer
                                                |
                                  Java result or ScriptException
```

## 2. Explicit Engine Registration with ScriptEngineManager

### 2.1. Three Registration Methods

Suppose the application already has a `factory` variable of type `ScriptEngineFactory`:

```java
ScriptEngineManager manager = new ScriptEngineManager();

manager.registerEngineName("math", factory);
manager.registerEngineExtension("mcalc", factory);
manager.registerEngineMimeType("text/x-minicalc", factory);

ScriptEngine byName = manager.getEngineByName("math");
ScriptEngine byExtension = manager.getEngineByExtension("mcalc");
ScriptEngine byMime = manager.getEngineByMimeType("text/x-minicalc");
```

This is an **integration illustration snippet**, not a standalone program: `factory` is supplied externally. Section 5 presents a self-contained runnable program including the factory, engine, and manager.

Key points to understand accurately:

- `registerEngineName(String name, ScriptEngineFactory factory)` registers an alias identifying the engine.
- `registerEngineExtension(String extension, ScriptEngineFactory factory)` registers the extension name **without a leading dot**, e.g., `mcalc` instead of `.mcalc`.
- `registerEngineMimeType(String mimeType, ScriptEngineFactory factory)` registers a content type, e.g., `text/x-minicalc`.
- The three lookup tables are **separate**: registering by name does not automatically register extensions or MIME types for a factory that was not discovered via SPI. If the host wants to support all three lookup paths, register each required key explicitly.
- Registration applies only to **that manager instance**, not a global registry across all `ScriptEngineManager` instances in the same JVM.
- `getEngineByName`, `getEngineByExtension`, and `getEngineByMimeType` return `null` if no matching engine is found or created; the host must check for `null` before calling `eval`.
- The manager uses the factory to obtain a `ScriptEngine` (typically the factory creates a new instance per request). Never assume multiple engines from the same factory share `Bindings`, interpreter state, or thread safety.
- An explicitly registered engine must still have its classes, dependencies, and access permissions available in the host's class loader; **registering** does not automatically download missing code, load nonexistent JARs, or resolve missing modules.

### 2.2. When Should You Use Explicit Registration?

This approach fits when the host:

- Maintains an allowlisted set of engines and actively instantiates/receives factories.
- Loads plugins via separate class loaders or module layers, then receives factories through a shared API.
- Wants custom aliases per tenant or language version, independent of service discovery order.
- Wants to disable an engine without modifying all artifacts in the JVM.
- Wants to verify compatibility, permissions, configuration, quotas, or versions **before** allowing `eval`.

For instance, you can apply `registerEngineName("rules-v2", factoryV2)` instead of overwriting the `rules` alias used by existing applications. When aliases collide, a new registration on the same manager can replace that alias's explicit mapping; manage and document override policies to prevent untrusted plugins from hijacking shared names.

### 2.3. Explicit Registration vs. SPI Discovery

`ScriptEngineManager` includes a service provider discovery mechanism for `ScriptEngineFactory`. On the classpath, a JAR typically contains the descriptor:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

Its contents list the compiled factory class name, for example:

```text
com.example.minicalc.MiniFactory
```

The declared factory must actually exist, implement `ScriptEngineFactory`, and be instantiable by the service loader as specified. Once discovered, the manager uses `getNames()`, `getExtensions()`, and `getMimeTypes()` metadata to look up matching engines. Merely having a class name in a descriptor **does not** guarantee that all dependencies, constructors, or engine implementations are valid.

With a **named module**, instead of a classpath descriptor, the provider module can publish the service using `provides` in `module-info.java`:

```java
module com.example.minicalc {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.minicalc.MiniFactory;
}
```

This is a **module packaging descriptor**, not a complete runnable file paired with the section 5 demo. The demo uses the default class `MiniScriptDemo` to minimize file count; to build a named module as shown above, move the classes into package `com.example.minicalc`, add the proper module descriptor, and ensure the module is resolved/visible through the application's discovery path.

Do not confuse these concepts:

- **`registerEngineName(...)`** accepts an existing factory object and requires no `META-INF/services`.
- **Service discovery** loads factories from service descriptors/module metadata and appropriate class loaders.
- **`getEngineFactories()`** is useful for inspecting discovered factories; do not rely on this list as the sole confirmation that an explicitly registered alias is active. Call the actual `getEngineByName` or relevant lookup method you intend to verify.
- When the manager uses the default constructor, the thread context class loader can affect SPI discovery. There is an overload `new ScriptEngineManager(classLoader)` to choose the discovery loader explicitly; this does not replace verifying class identity of `ScriptEngineFactory` from the shared API.

## 3. Designing ScriptEngineFactory

`ScriptEngineFactory` provides **metadata and the engine factory method**. An implementation cannot just implement `getScriptEngine()` and ignore the other methods: they are part of the interface and tell the host and tooling what the engine supports.

| API | Meaning in This Lesson | Example Value |
| --- | --- | --- |
| `getEngineName()` | Product/runtime name of the engine | `MiniCalculator` |
| `getEngineVersion()` | Engine implementation version | `1.0` |
| `getLanguageName()` | Language/script syntax name | `MiniCalc` |
| `getLanguageVersion()` | Syntax/language version | `1.0` |
| `getNames()` | Names/aliases for discovery | `minicalc`, `mc` |
| `getExtensions()` | Common file extensions | `mcalc` |
| `getMimeTypes()` | Advertised MIME types | `text/x-minicalc` |
| `getParameter(String)` | Metadata for `ScriptEngine.*` keys, `THREADING` | Corresponding value or `null` |
| `getMethodCallSyntax(...)` | How method calls are represented in the language | Unsupported in demo; throws unsupported |
| `getOutputStatement(...)` | Output statement in the engine's syntax | `print ...` |
| `getProgram(String...)` | Joins statements into a program | Joined with newlines |
| `getScriptEngine()` | Creates a `ScriptEngine` capable of eval | `new MiniEngine(this)` |

A real engine should keep its metadata consistent with its parser. For example, if `getProgram` returns multiple statements separated by newlines, `eval` must handle multi-statement scripts; if `getOutputStatement` returns `print ...`, the interpreter must recognize the `print` command.

### 3.1. Engine Name and Language Name Are Not Synonymous

A single language can have **multiple engine implementations**. `getLanguageName()` describes the language scripts are written in, whereas `getEngineName()` describes the implementation. Likewise, the language version (syntax/feature set) does not necessarily change on the same release cadence as the engine (bug fixes, optimizations, packaging).

If plugins register short aliases like `javascript` or `rules`, the host should pick implementations using explicit version/compatibility metadata; knowing the name alone is not enough to determine which interpreter will run.

### 3.2. The THREADING Key

`ScriptEngineFactory.getParameter("THREADING")` indicates the engine's concurrency guarantee per API conventions. In the demo, it returns **`null`**: the engine **does not guarantee** safety when multiple threads evaluate concurrently on the same instance. For custom engines with shared state, establish an explicit policy: create an independent engine/context per request, synchronize access, or design an interpreter with no shared mutable state.

Do not set `"MULTITHREADED"`, `"THREAD-ISOLATED"`, or `"STATELESS"` just to make metadata look nice if the runtime does not genuinely satisfy that contract. Distinguish interpreter thread safety from shared `Bindings` being mutated concurrently by multiple threads.

### 3.3. Syntax-Generation Methods Must Not Overstate Capabilities

The MiniCalc demo only has `add`, `set`, and `print` commands. It has **no method call syntax**, so `getMethodCallSyntax` throws `UnsupportedOperationException` rather than generating a Java-looking string that cannot execute. `getOutputStatement` only supports simple single-line output, while `getProgram` joins statements with newlines. For a real language, these methods must escape strings properly and emit code **that the actual parser accepts**.

## 4. Designing AbstractScriptEngine

`AbstractScriptEngine` is a base class that reduces boilerplate for `ScriptEngine`, but **contains no built-in interpreter**. When extending it, you must at minimum implement:

- `Object eval(String script, ScriptContext context) throws ScriptException`.
- `Object eval(Reader reader, ScriptContext context) throws ScriptException`.
- `Bindings createBindings()`.
- `ScriptEngineFactory getFactory()`.

Convenience overloads such as `engine.eval("...")`, `engine.put("x", value)`, or `engine.get("x")` operate through `AbstractScriptEngine`'s context/bindings machinery. When overriding the two `eval` methods taking `ScriptContext`, always use the passed `context` rather than ignoring it and operating on a secret global map.

### 4.1. Bindings and Scopes

`Bindings` is a variable-name → Java-value map. `ScriptContext` has standard scopes:

- **`ENGINE_SCOPE`**: state of the context/engine used during the current call. `engine.put(...)` typically stores entries in this scope's bindings.
- **`GLOBAL_SCOPE`**: shared values optionally provided by the host or manager. `ScriptContext.getAttribute(name)` searches scopes in order; a value in `ENGINE_SCOPE` shadows a same-named value in `GLOBAL_SCOPE`.

In the demo, `engine.put("seed", 7L)` places a variable into engine scope. The command `add $seed 5` reads the variable via `context.getAttribute("seed")`. The command `set total 20` writes via `context.setAttribute("total", 20L, ScriptContext.ENGINE_SCOPE)`, which `engine.get("total")` can then read back.

Remember: an engine can receive a **different ScriptContext** on each evaluation. Engine code should not read `this.getContext()` instead of the `context` parameter passed to the overload when the caller deliberately supplies a private context.

### 4.2. Reader and Writer

A script can be supplied via a `String` or a `Reader`. Implementing `eval(Reader, ScriptContext)` should read the full text, handle `IOException`, and throw `ScriptException` per the contract. The demo chooses to read the entire `Reader` into a `StringBuilder` and delegate to the String parser; this is simple, though you should enforce an input size limit when accepting external scripts.

To emit output, the interpreter uses `context.getWriter()` rather than printing directly to `System.out`. That lets the host supply a `StringWriter` in tests, write to files/logs, or route output to another UI. `context.getErrorWriter()` and `context.getReader()` can also be used by the language when an error stream or stdin is needed, though this simple parser does not need them.

### 4.3. Turning Parse Errors into ScriptException

In JSR-223, syntax or evaluation errors should be expressed as `ScriptException`, preserving cause and location information when possible. A real parser can use `ScriptException` constructors that specify filename, line, and column. The demo illustrates prepending line numbers to the message, without pretending to be a full parser or multi-file script loader.

Distinguish script evaluation errors from errors occurring when the host supplies a class loader, creates a factory, configures a context, or manages lifecycle. Do not blindly catch every `Throwable` and wrap it into `ScriptException`; doing so can swallow critical JVM errors outside the interpreter's scope.

## 5. Runnable Java 17+ Example: Building MiniCalc and Registering Three Ways

A **complete single-file Java example** using the standard Scripting API bundled in JDK 17. The MiniCalc language is intentionally tiny so registration, factory, bindings, and context behavior can be verified clearly:

- `add <a> <b>`: adds two integers or `$name` variables, returning `long`.
- `set <name> <value>`: stores a number in `ENGINE_SCOPE` and returns the stored value.
- `print <text>`: writes text and a newline to `ScriptContext.getWriter()`, returning `null`.
- Blank lines and lines starting with `#` are skipped.
- Multi-line scripts can be evaluated; `eval` returns the result of the last executed command.
- Invalid commands or arithmetic errors are reported via `ScriptException`.

**Save the file as `MiniScriptDemo.java`** in your working directory:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public class MiniScriptDemo {
    public static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniCalculator"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("mcalc"); }
        @Override public List<String> getMimeTypes() { return List.of("text/x-minicalc"); }
        @Override public List<String> getNames() { return List.of("minicalc", "mc"); }
        @Override public String getLanguageName() { return "MiniCalc"; }
        @Override public String getLanguageVersion() { return "1.0"; }

        @Override
        public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.NAME -> getNames().get(0);
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case "THREADING" -> null;
                default -> null;
            };
        }

        @Override
        public String getMethodCallSyntax(String obj, String method, String... args) {
            throw new UnsupportedOperationException("MiniCalc has no method calls");
        }

        @Override
        public String getOutputStatement(String toDisplay) {
            if (toDisplay.contains("\n")) {
                throw new IllegalArgumentException("One line only");
            }
            return "print " + toDisplay;
        }

        @Override
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }

        @Override
        public ScriptEngine getScriptEngine() {
            return new MiniEngine(this);
        }
    }

    public static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        public MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override
        public Object eval(String script, ScriptContext context) throws ScriptException {
            if (script == null || context == null) {
                throw new NullPointerException("script and context must be non-null");
            }
            Object result = null;
            String[] lines = script.split("\\R", -1);
            for (int i = 0; i < lines.length; i++) {
                String line = lines[i].trim();
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }
                try {
                    String[] words = line.split("\\s+");
                    switch (words[0]) {
                        case "add":
                            require(words.length == 3, "add needs two operands");
                            result = Math.addExact(number(words[1], context),
                                                   number(words[2], context));
                            break;
                        case "set":
                            require(words.length == 3, "set needs name and value");
                            require(words[1].matches("[A-Za-z][A-Za-z0-9_]*"),
                                    "invalid variable name");
                            long value = number(words[2], context);
                            context.setAttribute(words[1], value, ScriptContext.ENGINE_SCOPE);
                            result = value;
                            break;
                        case "print":
                            require(line.length() > 6, "print needs text");
                            context.getWriter().write(line.substring(6) + "\n");
                            context.getWriter().flush();
                            result = null;
                            break;
                        default:
                            throw new IllegalArgumentException("unknown command: " + words[0]);
                    }
                } catch (IllegalArgumentException | ArithmeticException | IOException problem) {
                    throw new ScriptException(
                            "line " + (i + 1) + ": " + problem.getMessage());
                }
            }
            return result;
        }

        private static void require(boolean condition, String message) {
            if (!condition) {
                throw new IllegalArgumentException(message);
            }
        }

        private static long number(String token, ScriptContext context) {
            if (token.startsWith("$")) {
                Object found = context.getAttribute(token.substring(1));
                if (!(found instanceof Number n)) {
                    throw new IllegalArgumentException("not a number: " + token);
                }
                return n.longValue();
            }
            return Long.parseLong(token);
        }

        @Override
        public Object eval(Reader reader, ScriptContext context) throws ScriptException {
            try {
                StringBuilder script = new StringBuilder();
                char[] block = new char[2048];
                int n;
                while ((n = reader.read(block)) != -1) {
                    script.append(block, 0, n);
                }
                return eval(script.toString(), context);
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }

        @Override public Bindings createBindings() { return new SimpleBindings(); }
        @Override public ScriptEngineFactory getFactory() { return factory; }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        MiniFactory factory = new MiniFactory();

        manager.registerEngineName("math", factory);
        manager.registerEngineExtension("mcalc", factory);
        manager.registerEngineMimeType("text/x-minicalc", factory);

        ScriptEngine engine = manager.getEngineByName("math");
        engine.put("seed", 7L);
        System.out.println("factory: " + engine.getFactory().getEngineName());
        System.out.println("sum: " + engine.eval("add $seed 5"));
        System.out.println("last: " + engine.eval("set total 20\nadd $total 2"));
        System.out.println("binding: " + engine.get("total"));

        System.out.println("extension: " +
                manager.getEngineByExtension("mcalc").eval("add 1 2"));
        System.out.println("mime: " +
                manager.getEngineByMimeType("text/x-minicalc").eval("add 10 20"));

        StringWriter writer = new StringWriter();
        engine.getContext().setWriter(writer);
        Object last = engine.eval(
                new StringReader("print Hello from Reader\nadd 3 4"));
        System.out.println("reader: " + last);
        System.out.println("writer: " + writer.toString().strip());

        try {
            engine.eval("unknown");
        } catch (ScriptException expected) {
            System.out.println("invalid: " + expected.getMessage());
        }
    }
}
```

### 5.1. Compile and Run

Use JDK 17 or newer, with no external libraries:

```bash
javac --release 17 MiniScriptDemo.java
java MiniScriptDemo
```

**Exact stdout**, verified with `javac --release 17` and `java`:

```text
factory: MiniCalculator
sum: 12
last: 22
binding: 20
extension: 3
mime: 30
reader: 7
writer: Hello from Reader
invalid: line 1: unknown command: unknown
```

### 5.2. Why Does Each Line Produce This Result?

1. `factory: MiniCalculator`: the manager looks up alias `math`, calls `MiniFactory.getScriptEngine()`, and the engine returns the matching factory via `getFactory()`.
2. `sum: 12`: `engine.put("seed", 7L)` stores a value in bindings; the parser resolves `$seed` to `7` and adds `5`.
3. `last: 22`: the multi-line script stores `total = 20`, then computes `add $total 2`; the final result is `22`.
4. `binding: 20`: `engine.get("total")` returns the value `set` stored in `ENGINE_SCOPE`.
5. `extension: 3` and `mime: 30`: the manager finds the factory under the two separately registered keys. Each `getEngineBy...` returns an appropriate engine and runs addition independently.
6. `reader: 7`: the `eval(Reader, context)` overload reads the `StringReader` into a script, executes `print`, and then `add`. The final value is `7`.
7. `writer: Hello from Reader`: output from `print` is written to the host-supplied `StringWriter`, not printed directly to the terminal by the interpreter.
8. `invalid: ...`: an instruction outside the valid syntax becomes a `ScriptException` with line number and cause.

The output does not depend on a pre-installed JavaScript engine. The program explicitly creates `MiniFactory`, registers the three tables, and requires no `META-INF/services`. Moreover, this is an **illustrative expression language**, not a JavaScript/Python interpreter or a complete production DSL.

### 5.3. Implementation Details Worth Inspecting Closely

- `MiniFactory` is a **static nested public class** of `MiniScriptDemo`, making it easy to package in a single runnable test file. When publishing a standalone SPI, factories and engines are normally placed in dedicated packages.
- `getScriptEngine()` returns a **new engine**, so the factory does not hold a shared singleton engine that accidentally leaks mutable state.
- `AbstractScriptEngine` is used to centralize logic in the two overloads `eval(String, ScriptContext)` and `eval(Reader, ScriptContext)`. The convenience overloads route through them.
- `createBindings()` creates a fresh `SimpleBindings`, which can be swapped for a controlled implementation if needed as long as it adheres to the `Bindings` contract.
- `getFactory()` returns the exact `factory` passed to the constructor, keeping the metadata visible to the host consistent.
- `Math.addExact` performs overflow-checked `long` addition. Overflow raises `ArithmeticException`, which is wrapped into `ScriptException` with line information.
- `Number.longValue()` in the demo simplifies conversion and may truncate fractional parts of a `Double`. A real DSL should define explicit numeric type, overflow, and rounding policies instead of coercing blindly.
- `split("\\s+")` accepts whitespace-delimited tokens for `add/set`; `print` takes the substring after the prefix without full quoting/escaping support.
- `getOutputStatement` only checks newline `\n` at an illustrative level. If an engine accepts untrusted user data, use a proper grammar, escaping, and input limits rather than concatenating raw strings into code.

## 6. Building Maintainable Engines and Factories in Real Projects

### 6.1. Separating Layers by Responsibility

A sustainable extensible architecture separates:

```text
host scripting module
  ScriptEngineManager
    - select engine per policy
    - verify metadata/compatibility
    - provision ScriptContext/Bindings
    - logging, quota, audit

provider module/JAR
  ScriptEngineFactory
    - metadata, extension/name/mime
    - instantiate ScriptEngine

  ScriptEngine extends AbstractScriptEngine
    - eval(String, ScriptContext)
    - eval(Reader, ScriptContext)
    - createBindings()
    - getFactory()

  Parser / Interpreter / Runtime
    - parse AST or bytecode depending on language
    - execute with the provided context
    - return result or positioned error
```

`AbstractScriptEngine` only helps implement the Java contract; it does not replace a parser, compiler, evaluator, or dependency isolation. A complex language may require an AST, execution memory management, service libraries, scheduling, module/class loaders, and Java ↔ script type-conversion adapters.

### 6.2. When Should You Build Your Own ScriptEngine?

Writing a custom `ScriptEngineFactory`/`AbstractScriptEngine` is worthwhile when:

- You are building a DSL with a narrow instruction set, syntax, and compatibility controlled by your organization.
- You want to expose an existing internal runtime under the JSR-223 interface for unified host consumption.
- You need a wrapper/adapter around an existing interpreter that does not natively support JSR-223.
- You need compatibility with frameworks that accept only `ScriptEngine`/`ScriptEngineFactory`.

**You do not necessarily need to write a new interpreter** if you only need to run a mainstream language. In that case, evaluate a reputable engine compatible with your JDK, license, version, and security model, and use that engine's factory. Writing a semantically sound parser, handling types, exceptions, performance, and security is far larger than writing the JSR-223 adapter code.

### 6.3. Registering When Plugins Are Dynamically Loaded

When a host loads plugins from JARs or separate `ModuleLayer`s, a sensible flow is:

1. Inspect metadata and verify the plugin source is authorized.
2. Load/instantiate `ScriptEngineFactory` via the designed mechanism.
3. Verify factory properties—especially name, language, version, API compatibility, and threading policy.
4. Decide which aliases/extensions/MIME types are permitted to be published in the host's manager.
5. Register the factory using the appropriate `registerEngineName`/`Extension`/`MimeType` calls.
6. On execution requests, obtain the appropriate engine/context and supply bindings scoped to the caller's permissions.
7. Clear references and recreate the manager/registry—or apply a proper replacement mechanism—when a plugin expires or is upgraded.

**Do not treat ScriptEngineManager as a full-featured unregister/hot-reload registry.** The explicit registration API does not provide symmetric unregister operations for every mapping. In multi-version runtimes or systems with per-tenant policies, it is often better for the host to maintain its own registry table and recreate managers/routes when engines change.

If a plugin has its own class loader, the manager retaining `factory` can retain the plugin's loader, instances, and classes, preventing unloading. Manage lifecycles, caches, threads, and references explicitly; do not merely delete an entry from a UI and assume the plugin was reclaimed.

## 7. ScriptContext, State, and Concurrency

### 7.1. Isolating State per Invocation

If scripts arrive from multiple requests or tenants, avoid sharing a mutable `ENGINE_SCOPE` without isolation. The host can use:

- A fresh engine and fresh bindings per request.
- A single engine (if the implementation guarantees thread safety) with **separate context/bindings** per execution.
- An engine pool with an explicit lifecycle, permission boundaries, and request limits.
- A worker runtime outside the Java process for strong security boundaries.

Choose the strategy according to the **actual thread-safety contract**, not merely API names. The demo returns `"THREADING" -> null` because it makes no claim of supporting concurrent evaluation on a single engine instance.

### 7.2. GLOBAL_SCOPE Is Not an Arbitrary Cache

`ScriptEngineManager` can manage shared bindings across engines it creates. `GLOBAL_SCOPE` is suitable for shared configuration values **when policy permits**, but must never hold secrets, admin privileges, or mutable objects that could leak into another tenant's script. A binding containing a Java object can expose more methods and privileges than expected.

If helpers must be shared, expose a narrow interface rather than passing an administrative service object for the entire system. Once a script holds a reference to a Java object, access constraints depend on the engine and the language's interop mechanism—JSR-223 does not sandbox them automatically.

### 7.3. Eval Does Not Guarantee Timeouts or Rollback

`ScriptEngine.eval` can run indefinitely, block threads, or mutate state through exposed objects. There is no universal guarantee that the JSR-223 API provides default timeouts, binding rollback, checkpoints, or safe cancellation across all engines. Timeouts based on `Thread.interrupt()` help only if the interpreter cooperatively checks interrupts and subtasks can also stop.

For untrusted inputs, consider separate processes, CPU/memory quotas, I/O/network restrictions, stripping unnecessary privileges, testing hangs/infinite loops, and process-kill policies. A separate `ClassLoader` and separate `ScriptContext` are only code/state organization boundaries, **not a security sandbox**.

## 8. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| `getEngineByName("JavaScript") == null` | JDK includes the API but no JavaScript engine is supplied | Check engine dependencies and SPI/module setup |
| `getEngineByName("math") == null` | Not registered in that manager, wrong alias, or factory failed | Check `registerEngineName` and the exact manager instance |
| `getEngineByExtension("mcalc") == null` | Only name was registered, extension was not | Call `registerEngineExtension` or configure SPI metadata |
| `getEngineByMimeType(...) == null` | MIME casing mismatch or missing mapping | Verify the exact key and factory |
| Manager has factory but `eval` fails | Parser, context, or engine could not process script | Inspect `ScriptException` and diagnostics |
| `ServiceConfigurationError` during discovery | Provider class/factory misconfigured or cannot be instantiated | Check descriptor, constructor, module, and dependencies |
| `ClassCastException` between host and engine | `javax.script` or shared API loaded with distinct identities | Inspect class loaders / shared runtime API |
| Script reads variables, but other requests see them too | Scope/bindings inadvertently shared | Use separate context/engine per policy |
| `ScriptException` lacks useful location info | Engine throws generic message without line/column/cause | Include clear line/column and cause chain in parser errors |
| Script produces output, yet host captures nothing | Interpreter writes to `System.out` instead of `context.getWriter()` | Route output through `context.getWriter()` in the engine |
| Engine supports `Reader` but loses data | Single read without looping to EOF; `IOException` mishandled | Test `eval(Reader, ScriptContext)` with long inputs |
| Cannot unload plugin | Manager/engine/cache retains factory and loader | Trace lifecycle and all live references |
| Script runs too long or accesses sensitive resources | JSR-223 has no built-in sandbox | Isolate execution and enforce permissions/quotas |

### 8.1. What Should Diagnostics Log?

When an engine fails to work, log:

- The alias/extension/MIME type looked up by the host.
- `getEngineName`/`getEngineVersion`/`getLanguageName`/`getLanguageVersion` metadata when the factory is available.
- Class name and defining loader of the factory/engine.
- Whether the engine was found via explicit registration or service discovery.
- Requested script language/version, request ID, duration, and timeout.
- Error type, line/location from `ScriptException` if present, and full cause chain.

Do not automatically log full scripts, bindings, or object graphs in production: scripts may contain customer data, tokens, and sensitive information.

## 9. Testing Checklist Before Providing a Script Engine to a Host

1. **Factory meets full contract:** every `ScriptEngineFactory` method returns consistent values; `getScriptEngine().getFactory()` returns the right factory.
2. **Name lookup:** register the name and verify `getEngineByName` returns a non-null instance.
3. **Extension/MIME lookup:** register separately and test each key; aliases must not collide with unintended mappings.
4. **No discovery dependency:** explicit registration mode runs even without a service descriptor.
5. **SPI deployment if used:** verify `META-INF/services` or `provides` in a named module, class loaders, constructors, and dependencies.
6. **String/Reader:** `eval(String, context)` and `eval(Reader, context)` produce identical results for the same script.
7. **Bindings/scopes:** `put/get`, `ENGINE_SCOPE`, `GLOBAL_SCOPE`, lookup order, and private contexts behave per contract.
8. **Output:** `context.getWriter()` receives output; errors are not swallowed.
9. **Parser errors:** invalid commands, bad operands, overflow, and `Reader` I/O errors produce appropriate `ScriptException`s.
10. **Threading:** concurrent `eval` policy and engine lifecycle are tested; `THREADING` never over-promises capabilities.
11. **Compatibility:** JDK version, `java.scripting`, language version, and engine version match the deployment environment.
12. **Security:** input size, CPU/quotas, access via exposed Java objects, annotations/modules/class loaders, and sensitive logging.
13. **Lifecycle:** registries/managers do not retain old plugin code indefinitely after updating or removing an engine.

**Conclusion:** `ScriptEngineManager` is where the host selects engines; `ScriptEngineFactory` describes and instantiates engines; and `AbstractScriptEngine` streamlines writing an implementation while still requiring a real parser and evaluation logic. When the host already has a factory, **explicit registration** by name/extension/MIME is simple, deliberate, and requires no service descriptor. When supplying a new DSL or runtime, implement the full factory + engine, honor `ScriptContext`/`Bindings`/`ScriptException`, and choose either explicit registration or SPI to match your packaging and plugin-management model.