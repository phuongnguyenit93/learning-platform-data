# Discovering ScriptEngine Name, File Extension, MIME Type, and Version in Java

## 1. The Problem When Embedding Scripting Languages

A Java application can enable execution of a scripting language through **JSR-223 (Scripting for the Java Platform)**, whose API lives in the `java.scripting` module and the `javax.script` package. Rather than hard-coding a single engine, the host often needs to know **which scripting engines are present** and **what kinds of scripts each engine recognizes**.

Information commonly used during discovery:

- **Engine implementation name**: `ScriptEngineFactory.getEngineName()`, e.g., a product/implementation name.
- **Short names or aliases used to look up the engine**: `getNames()`, corresponding to `ScriptEngineManager.getEngineByName(...)`.
- **Script file extensions**: `getExtensions()`, corresponding to `getEngineByExtension(...)`.
- **MIME types of script content**: `getMimeTypes()`, corresponding to `getEngineByMimeType(...)`.
- **Engine implementation version**: `getEngineVersion()`, distinct from the **language version** returned by `getLanguageVersion()`.

This is **runtime capability discovery**, not reading JAR filenames or querying the JDK version. A runtime may contain no engines at all, or multiple implementations supporting the same language with different versions, aliases, or MIME types.

### Two Objects with Different Roles

```text
Scripting engine JAR
  └─ META-INF/services/javax.script.ScriptEngineFactory
                     │
                     ▼
         ScriptEngineManager
         discovers factories
                     │
       getEngineFactories()             ┌──────────────────────────────┐
                     │                  │ ScriptEngineFactory           │
                     ├─────────────────►│ getEngineName()/Version()    │
                     │                  │ getNames()/Extensions()      │
                     │                  │ getMimeTypes()               │
                     │                  │ getLanguageName()/Version()  │
                     │                  └──────────────────────────────┘
                     │
       getEngineByName / Extension / MimeType
                     │
                     ▼
          factory.getScriptEngine()
                     │
                     ▼
             ScriptEngine
             eval / bindings / context
```

**`ScriptEngineFactory`** describes the engine and knows how to instantiate it; **`ScriptEngine`** is the object that executes scripts. **`ScriptEngineManager`** uses Java's service provider mechanism to discover `ScriptEngineFactory` implementations and provides lookup methods by name/extension/MIME. Reading metadata only through the factory is usually the sensible step before actually creating an engine and evaluating scripts.

## 2. Standard `ScriptEngineFactory` API

| Data to Discover | Method | Return Type | What Is It Used For? |
| --- | --- | --- | --- |
| Implementation name | `getEngineName()` | `String` | Display the installed engine |
| Implementation version | `getEngineVersion()` | `String` | Diagnose compatibility / display version |
| Short names/aliases | `getNames()` | `List<String>` | Look up via `getEngineByName(name)` |
| Extensions | `getExtensions()` | `List<String>` | Look up via `getEngineByExtension(ext)` |
| MIME types | `getMimeTypes()` | `List<String>` | Look up via `getEngineByMimeType(mime)` |
| Language name | `getLanguageName()` | `String` | Know which language the engine runs |
| Language version | `getLanguageVersion()` | `String` | Check the language level supported by the engine |
| Other parameters | `getParameter(key)` | `Object` | Retrieve standard or engine-specific metadata |
| Create engine | `getScriptEngine()` | `ScriptEngine` | Create/obtain an instance capable of running scripts |

**Engine name** does not have to match **language name**. For instance, two different implementations can handle the same language while differing in version, features, and compatibility. `getEngineVersion()` is the **engine** version, not `Runtime.version()`, not the Java version, and not automatically equal to `getLanguageVersion()`.

**Illustrative** code example once you already have a `ScriptEngineFactory factory`:

```java
System.out.println(factory.getEngineName());
System.out.println(factory.getEngineVersion());
System.out.println(factory.getNames());
System.out.println(factory.getExtensions());
System.out.println(factory.getMimeTypes());
System.out.println(factory.getLanguageName());
System.out.println(factory.getLanguageVersion());
```

### 2.1. Short Names Differ from the Full Name

`getEngineName()` returns the **full name of the implementation**, whereas `getNames()` returns the list of **short names used for lookup**. For example, a hypothetical engine:

```text
Engine name: Caps Demo Engine
Names: [caps, caps-demo]
```

Here, the advertised lookup names are `"caps"` or `"caps-demo"`. Do not assume `getEngineByName(factory.getEngineName())` is always supported just because the full name appears in metadata; use the aliases from `getNames()` or register explicit aliases.

The alias list may contain multiple names, such as the language name, product name, or compatibility aliases. Each provider defines its own list; the host should not assume names like `javascript`, `python`, or `js` are guaranteed to exist on every machine.

### 2.2. How Are File Extensions Declared?

`getExtensions()` provides the list of script-identifying extensions supported by the engine. A factory might return:

```text
[caps, capstxt]
```

The lookup API uses the **extension**, for example:

```java
ScriptEngine engine = manager.getEngineByExtension("caps");
```

This is an illustrative snippet requiring a `manager` variable. Typically, the lookup string is `"caps"` **without a leading dot**. If given a filename like `example.caps`, the host must extract the extension first; do not pass the entire filename and expect the manager to parse it.

Example with `Path filename` as a host-controlled path:

```java
String file = filename.getFileName().toString();
int dot = file.lastIndexOf('.');
String ext = (dot > 0 && dot < file.length() - 1)
        ? file.substring(dot + 1)
        : "";
ScriptEngine engine = ext.isEmpty()
        ? null
        : manager.getEngineByExtension(ext);
```

This is **illustrative code**, omitting imports and handling of dotfiles, compound extensions like `tar.gz`, casing, or special naming conventions. For production requirements, establish a concrete normalization policy (such as which aliases are allowed and whether to lower-case using `Locale.ROOT`). Do not assume `getEngineByExtension` always normalizes input names automatically.

An extension is **only a routing hint**. A file carrying the `.caps` extension does not prove its contents are valid, safe, or actually in that language.

### 2.3. MIME Types Identify Content Formats

`getMimeTypes()` returns the media types advertised by the factory, for example:

```text
[text/x-caps]
```

The host can look up via:

```java
ScriptEngine engine = manager.getEngineByMimeType("text/x-caps");
```

Do not blindly append parameters like `"; charset=UTF-8"` to the lookup and expect the API to strip parameters. If receiving an HTTP `Content-Type` with parameters, the host should parse the media type properly, look up the normalized type/subtype, and still enforce content policies.

**A MIME type is not a byte-inspection language detection mechanism**, nor is it a digital signature of the engine. The API relies on metadata registered by the factory/host. Multiple engines can advertise the same MIME type; therefore, apply a deterministic selection policy when high compatibility or security is required.

### 2.4. Engine Version and Language Version: Do Not Use Interchangeably

A factory may advertise:

```text
Engine: Caps Demo Engine
Engine version: 1.2.3
Language: CapsLang
Language version: 1.0
```

- `getEngineVersion()`: version of the specific implementation, used for logging, compatibility matrices, and troubleshooting.
- `getLanguageVersion()`: version of the language supported by the engine, used for choosing syntax/features.
- `getLanguageName()`: name of the language, **not necessarily identical to the engine name**.

Version is a provider-defined `String`, with no guarantee that it follows SemVer. If policy requires version comparisons, do not rely solely on lexicographical string ordering (`"10"` vs. `"2"`); use specific parsing/version comparison rules suited to that engine's ecosystem.

### 2.5. `getParameter` and Concurrency Support

`ScriptEngineFactory.getParameter(String key)` supports several standard keys:

| Key | Meaningful Value |
| --- | --- |
| `ScriptEngine.ENGINE` | Engine name, corresponding to `getEngineName()` |
| `ScriptEngine.ENGINE_VERSION` | Engine version |
| `ScriptEngine.NAME` | One of the short names from `getNames()` |
| `ScriptEngine.LANGUAGE` | Language name |
| `ScriptEngine.LANGUAGE_VERSION` | Language version |
| `"THREADING"` | Information about thread safety advertised by the engine |

Example:

```java
Object engineVersion = factory.getParameter(ScriptEngine.ENGINE_VERSION);
Object threading = factory.getParameter("THREADING");
```

`getParameter("THREADING")` may return `null` (the engine does not support running scripts concurrently safely), `"MULTITHREADED"`, `"THREAD-ISOLATED"`, or `"STATELESS"`, representing increasing guarantees under JSR-223. A host should not share a `ScriptEngine` across multiple requests/threads by default without verifying its threading policy, how `Bindings` are managed, and the provider's actual behavior. Metadata is self-declared; testing and usage limits are necessary when integrating external engines.

## 3. Discovery with `ScriptEngineManager`

### 3.1. Listing All Available Factories

Illustrative code for a Java 17+ application:

```java
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

ScriptEngineManager manager = new ScriptEngineManager();
List<ScriptEngineFactory> factories =
        new ArrayList<>(manager.getEngineFactories());

factories.sort(
    Comparator.comparing(ScriptEngineFactory::getEngineName)
              .thenComparing(ScriptEngineFactory::getEngineVersion));

for (ScriptEngineFactory f : factories) {
    System.out.println("Engine: " + f.getEngineName());
    System.out.println("Version: " + f.getEngineVersion());
    System.out.println("Aliases: " + f.getNames());
    System.out.println("Extensions: " + f.getExtensions());
    System.out.println("MIME: " + f.getMimeTypes());
    System.out.println("Language: " + f.getLanguageName()
            + " " + f.getLanguageVersion());
}
```

**This is an illustrative snippet placed inside a valid method or block**, not a standalone `.java` file; the full example is in section 6. The code intentionally copies the list before sorting, because the list returned by the manager should not be assumed to be mutable.

`manager.getEngineFactories()` may return an **empty** list. That does not mean the JDK is broken: JSR-223 is an **API**, while concrete engines come from an implementation/provider.

**Note for Java 17:** The Nashorn JavaScript engine was removed from the JDK starting in **JDK 15**. Therefore, a Java 17 program must not assume that `new ScriptEngineManager().getEngineByName("JavaScript")` is always non-`null`. If JavaScript or another language is needed, a corresponding supporting engine/provider must be installed.

### 3.2. Three Ways to Obtain an Engine Based on Metadata

```java
ScriptEngine byName = manager.getEngineByName("caps");
ScriptEngine byExt = manager.getEngineByExtension("caps");
ScriptEngine byMime = manager.getEngineByMimeType("text/x-caps");
```

All of them return a `ScriptEngine` **or `null` if no matching engine is found**. `Optional` is not used directly in these API signatures; if you want an explicit idiom:

```java
ScriptEngine engine = java.util.Optional.ofNullable(
        manager.getEngineByName("caps"))
    .orElseThrow(() -> new IllegalStateException(
        "No engine installed with alias caps"));
```

**This is a snippet**, without `manager` and full imports. Missing-engine error messages should state the alias, script type, and required configuration guidance, rather than throwing a `NullPointerException` when calling `eval` on `null`.

The difference between **discovering factories** and **instantiating an engine** is crucial:

- `getEngineFactories()` lists the `ScriptEngineFactory` instances discovered by the manager. The goal is reading metadata; it does not actively call `ScriptEngineFactory.getScriptEngine()`.
- `getEngineByName`/`getEngineByExtension`/`getEngineByMimeType` find a factory by metadata or registration, then request **creating a `ScriptEngine`**. That step can be costly or fail due to implementation/dependency issues.
- `engine.getFactory()` returns the factory of an existing engine to inspect metadata; there is no need to create a new engine if you only want to list metadata.

### 3.3. How Are Factories Discovered?

`ScriptEngineManager` uses the **Java SPI/`ServiceLoader`** mechanism to locate classes implementing `javax.script.ScriptEngineFactory` from what the runtime can observe. When using a **classpath JAR**, the provider typically registers via the file:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

The contents are one or more *fully qualified names* of factory implementations, one per line, for example:

```text
example.engine.CapsEngineFactory
```

The file must sit **inside the JAR/provider artifact** at the exact path. `ScriptEngineFactory` requires a valid implementation class instantiable under service provider rules. Do not name the service file `javax.script.ScriptEngine`: the manager searches for the **factory**, not the engine.

`new ScriptEngineManager()` is equivalent to constructing a manager using the current **thread context class loader (TCCL)**. `new ScriptEngineManager(loader)` allows the host to specify the loader for discovery. Thus, if an engine JAR is only present in a dedicated plugin class loader that the TCCL cannot see, the default manager may not find the factory. The host can pass the right loader or manage discovery/registration for its own layer.

**In a JPMS module system:** an engine provides `ScriptEngineFactory` via `provides javax.script.ScriptEngineFactory with ...` and follows module visibility and module layer rules. Do not assume a newly created child `ModuleLayer` automatically appears inside an already initialized `ScriptEngineManager`. If the host actively creates layers and needs to register their factories, it can discover them via `ServiceLoader.load(layer, ScriptEngineFactory.class)` and register names, extensions, and MIME types into a host-owned manager according to policy. Control class loader/API identity and JAR/engine lifecycle when using dynamic plugin layers.

### 3.4. Explicit Registration When Priority Policy Is Needed

`ScriptEngineManager` provides the methods:

```java
manager.registerEngineName("my-dsl", factory);
manager.registerEngineExtension("mydsl", factory);
manager.registerEngineMimeType("text/x-my-dsl", factory);
```

This is an illustrative snippet with a `factory` already chosen by the host. Registrations on the manager take precedence during lookup for the corresponding key, which is useful if multiple providers advertise the same alias/extension/MIME type. They are **mappings specific to that manager instance**, do not rewrite SPI descriptors, and do not configure the system globally.

Important to note: `getEngineFactories()` returns factories obtained from the **discovery mechanism**. A factory added only via `registerEngineName/Extension/MimeType` does not necessarily appear in that list; lookup and enumeration are not guaranteed to return the same set after explicit registration.

## 4. Choosing an Engine When Multiple Providers Share Metadata

Suppose two factories both advertise the alias `"script"` and extension `"sc"`. `getEngineByName("script")` can locate an engine, but **does not provide enough information** to prove that engine has the exact version or features the host requires. Do not rely on the ordering of `getEngineFactories()` or `findFirst()` when deterministic selection is needed.

A robust workflow:

1. **Enumerate and record metadata** of each factory, along with artifact/loader provenance if managed by the host.
2. **Filter by language, engine name, version/capabilities**, and project requirements; do not use a vague alias as the sole criterion.
3. **Check for name collisions and conflicts** across aliases, MIME types, and extensions. Select or reject according to an intentional policy.
4. **Verify dependencies, trustworthiness, and compatibility** before calling the factory to create an engine.
5. **Create the engine from the selected factory** via `selectedFactory.getScriptEngine()` or register explicit mappings on the manager.
6. **Validate input scripts, resources, and execution limits**; metadata does not prove script code is safe.

Illustrative snippet for explicit selection by name and version:

```java
ScriptEngineFactory chosen = manager.getEngineFactories().stream()
    .filter(f -> f.getEngineName().equals("Caps Demo Engine"))
    .filter(f -> f.getEngineVersion().equals("1.2.3"))
    .findFirst()
    .orElseThrow(() -> new IllegalStateException(
        "Required engine/version not found"));

ScriptEngine engine = chosen.getScriptEngine();
```

This is **illustrative code**, not a standalone program. Exact string equality for version works here because a **specific exact version** is required; if you need a version range, use a dedicated version comparator rather than lexicographical comparison.

### Lookup Semantics Matrix

| Available Input | API Choice | Note |
| --- | --- | --- |
| Alias agreed in configuration | `getEngineByName(alias)` | Use a name from `getNames()`/registration |
| File `job.caps` | `getEngineByExtension("caps")` | Extract and normalize the extension first; do not pass `job.caps` verbatim |
| MIME `text/x-caps` | `getEngineByMimeType("text/x-caps")` | Do not confuse MIME with content inspection |
| Need to log engine/version inventory | `getEngineFactories()` | Reads metadata, does not force engine instantiation |
| Need a specific implementation/version | Filter `ScriptEngineFactory` then `getScriptEngine()` | Selection policy is decided by the host |
| Need to override alias conflicts | `registerEngineName/Extension/MimeType` | Manager-local mapping |

## 5. Runnable Java 17+ Example Independent of Built-In JDK Engines

To observe the exact metadata fields in a reproducible environment, we write a **minimal demonstration engine** for a mock language `CapsLang`. It only understands `upper <text>` (returning uppercase) and `print <text>` (writing to `ScriptContext.getWriter()`). The goal is learning **JSR-223 discovery/metadata**, not building a full programming language.

There are three Java files and one SPI descriptor. The host does not import the engine implementation; it only uses `javax.script`. The engine is packaged into a separate JAR and appears when that JAR is added to the runtime classpath.

### 5.1. Directory Structure

```text
demo/
├── src/
│   ├── host/
│   │   └── EngineProbe.java
│   └── example/
│       └── engine/
│           ├── CapsEngineFactory.java
│           └── CapsEngine.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── javax.script.ScriptEngineFactory
└── build/                    # created when compiling
```

### 5.2. Factory Advertising Name, Extension, MIME, and Version

**`src/example/engine/CapsEngineFactory.java`**

```java
package example.engine;

import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;

public final class CapsEngineFactory implements ScriptEngineFactory {
    @Override
    public String getEngineName() {
        return "Caps Demo Engine";
    }

    @Override
    public String getEngineVersion() {
        return "1.2.3";
    }

    @Override
    public List<String> getExtensions() {
        return List.of("caps");
    }

    @Override
    public List<String> getMimeTypes() {
        return List.of("text/x-caps");
    }

    @Override
    public List<String> getNames() {
        return List.of("caps", "caps-demo");
    }

    @Override
    public String getLanguageName() {
        return "CapsLang";
    }

    @Override
    public String getLanguageVersion() {
        return "1.0";
    }

    @Override
    public Object getParameter(String key) {
        return switch (key) {
            case ScriptEngine.ENGINE -> getEngineName();
            case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
            case ScriptEngine.NAME -> getNames().get(0);
            case ScriptEngine.LANGUAGE -> getLanguageName();
            case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
            case "THREADING" -> null; // Does not declare thread safety.
            default -> null;
        };
    }

    @Override
    public String getMethodCallSyntax(
            String obj, String method, String... args) {
        throw new UnsupportedOperationException(
            "CapsLang does not support Java method calls");
    }

    @Override
    public String getOutputStatement(String toDisplay) {
        return "print " + toDisplay;
    }

    @Override
    public String getProgram(String... statements) {
        return String.join("\n", statements);
    }

    @Override
    public ScriptEngine getScriptEngine() {
        return new CapsEngine(this);
    }
}
```

The primary fields are `getEngineName()`, `getNames()`, `getExtensions()`, `getMimeTypes()`, and `getEngineVersion()`. Under the JSR-223 API, the factory must also implement the remaining methods, including `getLanguageName()`, `getLanguageVersion()`, `getParameter()`, and `getScriptEngine()`.

`List.of(...)` returns an immutable list, fitting the metadata contract. `getParameter("THREADING") == null` indicates this engine **makes no thread-safety guarantee**. `getMethodCallSyntax` rejects a capability that this simple DSL does not support; that is an **explicit limitation of the mock engine**, not a complete Java method call syntax.

### 5.3. Demo Engine with Minimal `eval`

**`src/example/engine/CapsEngine.java`**

```java
package example.engine;

import java.io.IOException;
import java.io.Reader;
import java.io.StringWriter;
import java.util.Locale;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

final class CapsEngine extends AbstractScriptEngine {
    private final CapsEngineFactory factory;

    CapsEngine(CapsEngineFactory factory) {
        this.factory = factory;
    }

    @Override
    public Object eval(String script, ScriptContext context)
            throws ScriptException {
        Object result = null;

        for (String line : script.split("\\R")) {
            if (line.isBlank()) {
                continue;
            }
            if (line.startsWith("upper ")) {
                result = line.substring(6).toUpperCase(Locale.ROOT);
            } else if (line.startsWith("print ")) {
                try {
                    context.getWriter().write(line.substring(6));
                    context.getWriter().write(System.lineSeparator());
                    context.getWriter().flush();
                } catch (IOException error) {
                    throw new ScriptException(error);
                }
                result = null;
            } else {
                throw new ScriptException(
                    "Unsupported statement: " + line);
            }
        }
        return result;
    }

    @Override
    public Object eval(Reader reader, ScriptContext context)
            throws ScriptException {
        try {
            StringWriter buffer = new StringWriter();
            reader.transferTo(buffer);
            return eval(buffer.toString(), context);
        } catch (IOException error) {
            throw new ScriptException(error);
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

`AbstractScriptEngine` already implements several `eval` overloads and standard `ScriptContext`/`Bindings` management. The example only needs to implement the required abstract methods. `Reader.transferTo` and switch expressions are supported by JDK 17.

This program does **not** perform complex parsing, does not execute JavaScript, and does not provide a sandbox. It is just enough to prove that the factory produces a working `ScriptEngine` once discovered.

### 5.4. Host Application: Listing and Looking Up by Three Metadata Keys

**`src/host/EngineProbe.java`**

```java
package host;

import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class EngineProbe {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();

        // Discovery: no need to run a script yet to read metadata.
        List<ScriptEngineFactory> factories =
            manager.getEngineFactories();

        ScriptEngineFactory factory = factories.stream()
            .filter(f -> f.getNames().contains("caps"))
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "Caps engine factory not discovered"));

        System.out.println("Engine: " + factory.getEngineName());
        System.out.println("Engine version: " + factory.getEngineVersion());
        System.out.println("Names: " + factory.getNames());
        System.out.println("Extensions: " + factory.getExtensions());
        System.out.println("MIME: " + factory.getMimeTypes());
        System.out.println("Language: " + factory.getLanguageName());
        System.out.println("Language version: "
                + factory.getLanguageVersion());
        System.out.println("THREADING: "
                + factory.getParameter("THREADING"));

        ScriptEngine byName = manager.getEngineByName("caps");
        ScriptEngine byExt = manager.getEngineByExtension("caps");
        ScriptEngine byMime =
            manager.getEngineByMimeType("text/x-caps");

        System.out.println("By name: " + (byName != null));
        System.out.println("By extension: " + (byExt != null));
        System.out.println("By MIME: " + (byMime != null));

        if (byName == null) {
            throw new IllegalStateException(
                "Provider found but engine not created");
        }
        System.out.println("Eval: " + byName.eval("upper Java Script"));
    }
}
```

This code imports no classes from the `example.engine` package. It uses the host's standard API; the factory is found via SPI and lookups rely on the metadata advertised by the factory.

Because `getEngineFactories()` may contain other factories when the runtime adds extra JARs, `EngineProbe` filters by the short name `caps` rather than assuming the factory count is always 1. In the demo environment using the classpath commands below, providing just the engine JAR is enough to run.

### 5.5. SPI Descriptor for the Factory

**`resources/META-INF/services/javax.script.ScriptEngineFactory`**

```text
example.engine.CapsEngineFactory
```

The filename must match **`javax.script.ScriptEngineFactory`**, not `javax.script.ScriptEngine`. Its contents must be the fully qualified class name of a public factory with a no-arg constructor instantiable by `ServiceLoader`. In this example `CapsEngineFactory` declares no constructor, so Java generates a default public no-arg constructor for the public class.

### 5.6. Compiling and Running with Windows PowerShell

From the `demo` directory, ensure JDK 17+ `java`, `javac`, and `jar` are in `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/engine | Out-Null

# Host compiles independently, depending only on javax.script.
javac -encoding UTF-8 -d build/host src/host/EngineProbe.java

# Provider is compiled separately, relying on JDK APIs.
javac -encoding UTF-8 -d build/engine src/example/engine/CapsEngineFactory.java src/example/engine/CapsEngine.java

# Package the SPI descriptor into the provider JAR.
New-Item -ItemType Directory -Force build/engine/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/javax.script.ScriptEngineFactory build/engine/META-INF/services/javax.script.ScriptEngineFactory

jar --create --file build/caps-engine.jar -C build/engine .

# On Windows, ; separates classpath entries.
java -cp 'build/host;build/caps-engine.jar' host.EngineProbe
```

**Exact stdout of the demo with JDK 17+ and the classpath just created:**

```text
Engine: Caps Demo Engine
Engine version: 1.2.3
Names: [caps, caps-demo]
Extensions: [caps]
MIME: [text/x-caps]
Language: CapsLang
Language version: 1.0
THREADING: null
By name: true
By extension: true
By MIME: true
Eval: JAVA SCRIPT
```

The lines from `Engine:` through `THREADING:` are the data advertised by the factory. The three `true` results show that the manager mapped the alias, extension, and MIME type properly to a `ScriptEngine`. The `Eval: JAVA SCRIPT` line is the result of executing the minimal DSL, not a JavaScript engine.

**If you remove the engine JAR from the classpath** and run `java -cp build/host host.EngineProbe` in an environment with only standard JDK 17 and no other engine installed, the program throws `IllegalStateException` with the message `Caps engine factory not discovered`. That is intentional host behavior when no provider is found; JSR-223 does not install an engine for you automatically.

On Linux/macOS, use `mkdir -p` instead of `New-Item`, `cp` instead of `Copy-Item`, and `:` to separate classpath entries, for example:

```bash
java -cp 'build/host:build/caps-engine.jar' host.EngineProbe
```

Run the command above after compiling and packaging the JAR equivalently on your operating system.

### 5.7. Trying the `getParameter` API and Another Alias

In `EngineProbe`, you can try adding the following lines (**illustrative** snippet placed after obtaining `factory`):

```java
System.out.println(factory.getParameter(ScriptEngine.ENGINE));
System.out.println(factory.getParameter(ScriptEngine.ENGINE_VERSION));
System.out.println(factory.getParameter(ScriptEngine.LANGUAGE_VERSION));

ScriptEngine sameFamily = manager.getEngineByName("caps-demo");
System.out.println(sameFamily != null);
```

The results are `Caps Demo Engine`, `1.2.3`, `1.0`, and `true`, respectively. These are **new lookups/newly created engine objects** matching the metadata; `sameFamily` is not necessarily the same instance as `byName`. Do not assume `getEngineByName` returns a singleton or that a new engine always shares state with a previous engine.

## 6. Bringing the Example into a Plugin System and Module Runtime

### 6.1. Classpath Discovery Is Not a Dependency Resolver

The demo works because the provider JAR includes an SPI descriptor. The host still needs to:

- Supply the JAR and valid dependencies in the runtime classpath/module environment.
- Keep `javax.script`/provider API versions compatible.
- Specify the right class loader if plugins are loaded dynamically.
- Control engine lifecycle, script context, bindings, runtime duration, resources, and access permissions.

`ScriptEngineManager` discovers factories; it **does not download missing dependencies from Maven**, does not start every module/plugin along a dependency graph, and does not restrict script permissions.

### 6.2. JPMS and `ModuleLayer`

If the provider is implemented as a named module, the descriptor can look like (**illustrative snippet** only):

```java
module caps.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with example.engine.CapsEngineFactory;
}
```

When the host creates a child `ModuleLayer` at runtime, it must explicitly define which layer factories are discovered from. One approach is:

```java
ServiceLoader<ScriptEngineFactory> factories =
        ServiceLoader.load(layer, ScriptEngineFactory.class);

for (ScriptEngineFactory f : factories) {
    for (String name : f.getNames()) {
        manager.registerEngineName(name, f);
    }
    for (String ext : f.getExtensions()) {
        manager.registerEngineExtension(ext, f);
    }
    for (String mime : f.getMimeTypes()) {
        manager.registerEngineMimeType(mime, f);
    }
}
```

This is **non-standalone illustrative code**: the host must already have a validly defined `layer`, a host-managed `manager`, and the corresponding imports. Rules are needed to handle metadata collisions and versions; do not blindly register every factory if untrusted engines may be present. Creating/refreshing a layer does not automatically update an older manager.

### 6.3. Engine Metadata Differs from Verifying Actual Capabilities

A factory advertising `getExtensions()=[caps]` does not prove the engine handles all `.caps` files, supports every syntax version, or complies with sandbox policies. The host should test a benchmark suite of scripts, handle `ScriptException`, check timeouts/memory, and measure actual results.

In particular, **an engine running scripts can execute code with the process's privileges**. MIME/name/version metadata **does not grant security**. Do not accept untrusted user attachments or scripts and pass them to `engine.eval(...)` with full host access without strict isolation (typically a separate process with restricted OS permissions, resource limits, and network controls).

### 6.4. Version Configuration and Compatibility

When the host has specific requirements, record the full “engine implementation + engine version + language version + source artifact” in logs/diagnostics. Build a compatibility matrix based on actual features rather than just the language name. When upgrading the JDK, engine providers can be added or removed independently of the `java.scripting` API.

With Java 17, the absence of Nashorn from the JDK is a classic example: `javax.script` still exists, yet `getEngineFactories()` can be empty if no engine is installed. The presence of the `javax.script` package **does not mean** a JavaScript engine is distributed with the JDK.

## 7. Common Misconceptions and How to Fix Them

| Symptom | Likely Cause | How to Check/Fix |
| --- | --- | --- |
| `getEngineFactories()` is empty | Runtime has no `ScriptEngineFactory` provider, missing JAR, or wrong loader | Check runtime classpath/module path, SPI descriptor, and TCCL |
| `getEngineByName("JavaScript")` returns `null` on Java 17 | JDK no longer bundles Nashorn | Install a compatible JS engine; do not rely on JDK defaults |
| Engine has a full name but `getEngineByName(fullName)` returns `null` | Lookup uses `getNames()` aliases, not necessarily the full engine name | Print `getNames()` and look up using an advertised name |
| `getEngineByExtension(".caps")` returns `null` | Factory declares `caps` without a dot | Extract the extension from the filename and pass `caps` |
| `getEngineByMimeType("text/x-caps; charset=UTF-8")` returns `null` | Lookup matches registered MIME types, without promising parameter parsing | Parse/normalize the media type first |
| `ScriptEngineFactory` appears but lookup fails to create engine | `getScriptEngine()` fails or dependency is missing | Diagnose engine creation and root cause |
| `getEngineVersion()` does not equal language version | The two APIs describe two distinct version schemes | Log both engine version and language version |
| Environment A sees the engine, B does not | Different class loader/module layer/classpath | Pass an explicit loader to `ScriptEngineManager`, check SPI |
| Multiple engines share an alias and the wrong one is picked | No implementation/version selection policy | Filter factories, register explicit mappings, check conflicts |
| Replaced JAR but manager still uses old engine | Old factory/loader/engine instance still alive | Manage new class loaders and instances, refresh manager per lifecycle |
| Shared one engine across threads and state got corrupted | Ignored `THREADING` metadata and `Bindings` rules | Check engine docs, isolate instances/contexts, synchronize if needed |
| Picked engine from uploaded file extension and evaluated immediately | Mistook filename/MIME for a safety guarantee | Validate content, origin, permissions, and time/resource limits |

### Three Mental Traps to Avoid

**1. Name, extension, and MIME are not the same thing.** They are three distinct *lookup keys* advertised by the factory. One engine can support multiple aliases, multiple extensions, and multiple MIME types.

**2. “Engine found” is different from “engine created/executed successfully”.** Listing `ScriptEngineFactory` instances is discovery; creating a `ScriptEngine` and executing `eval` are steps that can raise their own errors or side effects.

**3. Engine version is not the JDK version.** The `java.scripting` API follows the Java platform version, while a JSR-223 implementation has its own lifecycle and versioning.

## 8. Checklist Before Using Embedded Engines in Production

- [ ] Enumerate available `ScriptEngineFactory` instances and record engine name/version, names, extensions, MIME types, and language name/version.
- [ ] Separate lookups by alias, extension, or MIME according to the data source; normalize inputs per application policy.
- [ ] Do not assume Java 17 includes a JavaScript/Nashorn engine out of the box.
- [ ] Ensure the provider JAR is packaged properly with `META-INF/services/javax.script.ScriptEngineFactory` or a JPMS descriptor.
- [ ] Determine the correct class loader/module layer for dynamic provider discovery.
- [ ] When aliases/MIME types/extensions collide, choose implementation/version explicitly; do not rely on factory order.
- [ ] Distinguish `null` (not found) from factory instantiation errors and runtime `ScriptException` errors.
- [ ] Verify actual versions and capabilities rather than trusting metadata alone.
- [ ] Do not evaluate untrusted scripts inside an unisolated process; restrict permissions, resources, network, and execution time.
- [ ] Use `Bindings`/`ScriptContext` appropriately, paying attention to shared state and `THREADING` metadata.
- [ ] Define a lifecycle policy when updating engine/provider JARs: reload discovery, swap instances, and clean up properly.

**Conclusion:** `ScriptEngineManager` helps the host **discover and select** engines; `ScriptEngineFactory` supplies **names/aliases, extensions, MIME types, engine version, and language version**; `ScriptEngine` is used to **execute scripts** after selection. Rely on metadata for discovery, but rely on compatibility testing and security policies to decide which engine runs.

**Official Documentation:**

- [`ScriptEngineFactory` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html).
- [`ScriptEngineManager` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html).
- [`AbstractScriptEngine` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html).
- [Oracle JDK 17 Migration Guide — Nashorn removed in JDK 15](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html).
