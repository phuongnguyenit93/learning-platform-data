# Executing Code from String or Reader Using ScriptEngine.eval in Java

## 1. What Problem Does ScriptEngine.eval Solve?

Java provides **JSR 223 (Scripting API for Java)** in the **javax.script** package and **java.scripting** module. This API lets a Java application embed a scripting language executed by a **ScriptEngine**. The host can generate scripts dynamically, read scripts from a file, or receive a character stream and invoke **eval** to execute them according to the rules of the *installed engine*.

For example, an application can:
- Invoke a small processing rule supplied as text instead of writing a new Java class for every change.
- Read a stored, version-controlled script from a file **Reader**.
- Pass data into the script environment via **Bindings** or **ScriptContext**.
- Retrieve a return value, or catch **ScriptException** to report script-language errors.

**Important:** ScriptEngine is an **abstract interface**, not a universal interpreter for arbitrary syntax. Java 17 includes the **javax.script** API, but **does not ship a built-in Nashorn JavaScript engine** (Nashorn was removed from the JDK in Java 15). To run JavaScript, Groovy, or another real language via JSR 223, you must install a compatible **ScriptEngine provider** and verify the name advertised by the engine. Never assume **getEngineByName("JavaScript")** always returns a non-null engine.

Also do not confuse **eval("Java code")** with **compiling Java source code**. JSR 223 only runs the syntax of the language understood by a specific ScriptEngine; to compile .java into .class, use JavaCompiler/build pipelines or another appropriate tool.

## 2. Two Input Forms for eval: String and Reader

The two foundational overloads of **ScriptEngine**:

~~~java
Object eval(String script) throws ScriptException;
Object eval(Reader reader) throws ScriptException;
~~~

Both execute script content in the engine's **default ScriptContext**. Other overloads allow passing a separate environment:

~~~java
Object eval(String script, Bindings bindings) throws ScriptException;
Object eval(Reader reader, Bindings bindings) throws ScriptException;
Object eval(String script, ScriptContext context) throws ScriptException;
Object eval(Reader reader, ScriptContext context) throws ScriptException;
~~~

The declarations above are **illustrative API signatures**, not a standalone Java program.

| Aspect | **eval(String)** | **eval(Reader)** |
| --- | --- | --- |
| Input data | A string containing the full script | A character source supplied by a Reader |
| When suitable | Short scripts, templates already rendered to strings, verified script snippets | Script files, character stream sources, libraries producing a Reader |
| Who decides encoding? | Whoever created the String must have decoded it properly beforehand | The code creating the Reader, such as Files.newBufferedReader(..., UTF_8) |
| Resource management | No separate Reader to close | The caller should close the Reader it opened, typically with try-with-resources |
| Return value | **Object**, possibly null depending on language/statement | **Object**, following the same engine result rules |
| Errors | **ScriptException**, plus possible related Java errors | **ScriptException**; Reader read errors are handled/reported per engine implementation |
| Performance/memory | The entire script is already in a String | No guarantee the engine parses in streaming mode or avoids buffering the whole input |

**A Reader is not automatically faster or more memory-efficient.** It is simply a character-reading interface. An engine can easily read the entire Reader into a String before parsing, just like the demo engine in this article. Script size behavior must be measured with the actual provider and workload.

Given the same content, same state, and same provider, both overloads serve the same execution goal. Yet specific behavior—return value, error location, side effects, caching—belongs to the language/engine rather than being determined by String vs. Reader.

## 3. Finding a ScriptEngine Before Calling eval

Common usage pattern:

~~~java
// Illustrative snippet: requires a corresponding ScriptEngineFactory at runtime.
javax.script.ScriptEngineManager manager =
        new javax.script.ScriptEngineManager();

javax.script.ScriptEngine engine =
        manager.getEngineByName("language-name");

if (engine == null) {
    throw new IllegalStateException("Scripting engine is not installed");
}

Object result = engine.eval("valid-language-syntax");
~~~

**"language-name"** must be one of the names registered by the provider; **"valid-language-syntax"** must be replaced with real script syntax for that language. The snippet above is not standalone if no engine is installed.

ScriptEngineManager typically locates **ScriptEngineFactory** implementations via the service provider mechanism. For classpath JARs, the provider JAR may contain the resource **META-INF/services/javax.script.ScriptEngineFactory**; for explicit named modules, the provider is declared with **provides javax.script.ScriptEngineFactory with ...**. Discovery details and JAR/module visibility depend on the class loader/module layer and application configuration. If no provider exists, **getEngineByName() returns null**, leaving no engine to call eval on.

You can inspect which engines are currently discovered:

~~~java
// Illustrative snippet inside a method that already has a manager variable.
for (javax.script.ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + ": " + factory.getNames());
}
~~~

**Do not hard-code names like "js", "javascript", or "groovy" without checking the actual names** advertised by the provider version. In an application with multiple loaders, a factory present inside a JAR is not guaranteed to be found by the manager; you may need to pass the appropriate class loader to ScriptEngineManager.

**Do not confuse the java.scripting module with an engine's module**: java.scripting supplies the API; the engine is implemented by a provider. Seeing the javax.script package in an IDE does not prove a JavaScript engine is installed.

## 4. Execution Flow from Input to Result

~~~text
String or Reader
        |
        v
Validate source / select language / select engine
        |
        v
ScriptEngine.eval(source, Bindings or ScriptContext)
        |
        v
Engine parses and executes its own syntax
        |
        +--- returns Object (or null if defined by engine)
        |
        +--- throws ScriptException when engine reports script error
        |
        +--- may cause side effects per script/provider capabilities
~~~

A host should not call eval merely because a script "parses"; it must verify that the result has the expected type, is non-null if the contract forbids null, and control any permitted side effects. Do not infer that a **print** statement inside a script is also the return value of **eval**. An engine may write to the Writer in ScriptContext while returning **null** or a different object.

There are three layers of responsibility:
1. **Java caller**: validates inputs, limits size, manages the Reader, selects the provider, supplies Bindings/Context, catches errors, and maps results to the application contract.
2. **Script engine**: defines the language, parsing/evaluation, binding semantics, imports/interoperability, result types, and diagnostics.
3. **Runtime environment**: class loaders, modules, file/network permissions, dependency versions, CPU/memory resources, and lifecycle.

Thus the eval API looks simple, but integrating it into a real extensible system requires designing all three parts.

## 5. Complete Java 17 Example Without External Libraries

So that this article runs on **standard JDK 17**, the example supplies its own **small ScriptEngine named Mini** along with a **ScriptEngineFactory**. It is not JavaScript or Groovy; it understands only two commands:
- **greet**: reads the **name** variable from ScriptContext and returns a greeting string.
- **add <a> <b>**: takes two integers and returns their sum.

This example is valuable because it demonstrates the exact **ScriptEngine.eval(String)**, **eval(Reader)**, **Bindings**, and **ScriptException** contracts. In real applications, you will normally install an existing language provider rather than writing your own ScriptEngine.

### 5.1. Create One Java File

Create **src/demo/EvalDemo.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class EvalDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        manager.registerEngineName("mini", new MiniFactory());
        ScriptEngine engine = manager.getEngineByName("mini");

        engine.put("name", "Lan");
        System.out.println("String: " + engine.eval("greet"));

        try (Reader source = new StringReader("add 2 3")) {
            System.out.println("Reader: " + engine.eval(source));
        }

        Bindings temporary = engine.createBindings();
        temporary.put("name", "Mai");
        System.out.println("Bindings: " + engine.eval("greet", temporary));
        System.out.println("Original: " + engine.eval("greet"));

        try {
            engine.eval("invalid");
        } catch (ScriptException ex) {
            System.out.println("Error: " + ex.getClass().getSimpleName());
        }
    }

    private static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        private MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            String command = script.strip();
            if (command.equals("greet")) {
                Object name = context.getAttribute("name");
                if (name == null) {
                    throw new ScriptException("Missing name binding");
                }
                return "Hello, " + name + "!";
            }

            String[] parts = command.split("\\s+");
            if (parts.length == 3 && parts[0].equals("add")) {
                try {
                    int left = Integer.parseInt(parts[1]);
                    int right = Integer.parseInt(parts[2]);
                    return Math.addExact(left, right);
                } catch (NumberFormatException | ArithmeticException ex) {
                    throw new ScriptException("Invalid integer expression");
                }
            }
            throw new ScriptException("Unsupported mini command");
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    source.append(buffer, 0, count);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(source.toString(), context);
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

    private static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniEngine"; }
        @Override public String getEngineVersion() { return "1"; }
        @Override public List<String> getExtensions() { return List.of("mini"); }
        @Override public List<String> getMimeTypes() {
            return List.of("text/x-mini");
        }
        @Override public List<String> getNames() { return List.of("mini"); }
        @Override public String getLanguageName() { return "Mini"; }
        @Override public String getLanguageVersion() { return "1"; }
        @Override public Object getParameter(String key) {
            if (ScriptEngine.NAME.equals(key)) return "mini";
            if (ScriptEngine.ENGINE.equals(key)) return getEngineName();
            if (ScriptEngine.ENGINE_VERSION.equals(key)) return getEngineVersion();
            if (ScriptEngine.LANGUAGE.equals(key)) return getLanguageName();
            if (ScriptEngine.LANGUAGE_VERSION.equals(key))
                return getLanguageVersion();
            return null;
        }
        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) {
            return null; // Mini language has no method call syntax.
        }
        @Override public String getOutputStatement(String toDisplay) {
            return null; // Mini language has no print statement.
        }
        @Override public String getProgram(String... statements) {
            return statements.length == 1 ? statements[0] : null;
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniEngine(this);
        }
    }
}
~~~

Key points to note:

1. **manager.registerEngineName("mini", new MiniFactory())** registers the factory **directly on this manager**, so the program does not depend on an external engine. This is **not** automatic discovery via META-INF/services; in practice either registration style can be used depending on design.
2. **manager.getEngineByName("mini")** finds the newly registered factory and returns a ScriptEngine. In this example the engine variable is non-null because the right factory was explicitly registered.
3. **engine.put("name", "Lan")** sets the **name** variable in **ENGINE_SCOPE** of the default ScriptContext.
4. **engine.eval("greet")** takes its source from a String. MiniEngine reads the **name** variable and returns "Hello, Lan!".
5. **engine.eval(source)** with **StringReader("add 2 3")** enters the Reader overload. MiniEngine reads the characters and delegates to the String processing logic.
6. **engine.eval("greet", temporary)** uses a different Bindings containing **name = "Mai"**. This overload does not permanently replace the original bindings; the next call returns the greeting for "Lan".
7. **engine.eval("invalid")** throws **ScriptException** because the Mini language does not define that command; the application catches and prints the exception type.
8. **MiniFactory** implements the basic metadata of **ScriptEngineFactory**, including engine name, language, extension, and how to create MiniEngine. A toy language that does not support method call/print syntax returns null from the corresponding syntax-generation methods; this is not a JavaScript feature.

MiniEngine implements **eval(String, ScriptContext)** and **eval(Reader, ScriptContext)** via **AbstractScriptEngine**. AbstractScriptEngine supports the overloads corresponding to the default context or caller-supplied Bindings, reducing boilerplate compared to implementing the entire ScriptEngine interface directly. **createBindings()** returns SimpleBindings, and **getFactory()** returns the right metadata factory object.

### 5.2. Compile and Run

From the directory containing **src/**, create the **out** directory:

~~~bash
mkdir -p out
~~~

On Windows PowerShell, use **New-Item -ItemType Directory -Force out** if out does not yet exist. Then:

~~~bash
javac --release 17 -d out src/demo/EvalDemo.java
java -cp out demo.EvalDemo
~~~

**Exact standard output**:

~~~text
String: Hello, Lan!
Reader: 5
Bindings: Hello, Mai!
Original: Hello, Lan!
Error: ScriptException
~~~

The output shows that both overloads genuinely run through the engine; eval(String) returns a String, eval(Reader) returns an Integer (which becomes "5" when concatenated with a string), temporary Bindings allow changing a variable for a single execution, and invalid scripts are reported via ScriptException.

**Note on runnability:** the code uses standard Java APIs and does not depend on whether the JDK has Nashorn or GraalJS installed. The compiler must support **--release 17**, and the **java.scripting** module must be included in the runtime image if using a custom jlink build.

## 6. Example Using Reader from an External File

Instead of StringReader, applications commonly read from a file with a clearly specified encoding:

~~~java
// Illustrative snippet: engine is a valid obtained ScriptEngine,
// path is a Path pointing to a script file from a trusted source.
try (java.io.Reader reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    Object result = engine.eval(reader);
    System.out.println(result);
}
~~~

This is an **illustrative code snippet**, not a standalone program because it requires **engine** and **path** variables. The file's content must use syntax accepted by the chosen engine. With MiniEngine from section 5, a file containing **add 2 3** is valid; with a JavaScript provider, JavaScript syntax must be used instead.

Distinguish two error groups:
- **IOException** can occur when opening the file, and in some setups when reading/closing the Reader on the caller side.
- **ScriptException** can occur when the engine parses/evaluates or when the engine chooses to wrap a Reader error.

Do not assume **eval(Reader)** will automatically close the Reader; by resource-management convention, **whoever opens it closes it**, using try-with-resources even if eval throws an error.

**Reader differs from InputStream**: a Reader supplies already decoded characters, while an InputStream supplies bytes. When the source is an InputStream, use an InputStreamReader with an explicit Charset or equivalent APIs. Avoid relying on an implicit default charset if scripts must run consistently across operating systems.

## 7. Choosing Bindings and ScriptContext to Exchange Data

### 7.1. ENGINE_SCOPE and GLOBAL_SCOPE

A **ScriptContext** has standard scopes:

| Scope | Meaning | Usage |
| --- | --- | --- |
| **ScriptContext.ENGINE_SCOPE** | Variables bound to the specific engine/context; prioritized on lookup | Inputs and state for the current eval |
| **ScriptContext.GLOBAL_SCOPE** | Shared variables that may be exposed across contexts | Shared configuration when explicitly designed |

When calling **engine.put(key, value)**, JSR 223 places the value into ENGINE_SCOPE of the default context. When calling **engine.get(key)**, the API looks up the value in engine scope per the engine's conventions. If you want to supply inputs only for one eval call, typically create a separate **Bindings**:

~~~java
// Illustrative snippet; engine is already created and script matches provider syntax.
javax.script.Bindings input = engine.createBindings();
input.put("name", "Mai");
Object result = engine.eval("greet", input);
~~~

In the Mini example, the snippet above runs because the Mini language understands the **greet** command. With other languages, variable names may map to global variables/objects differently. **Bindings is a name → Object map**, not a guarantee that every engine follows the same Java/script type-conversion rules.

When using **eval(script, bindings)**, AbstractScriptEngine creates a temporary context using that bindings at ENGINE_SCOPE and may share GLOBAL_SCOPE from the default context. Thus **separating ENGINE_SCOPE does not automatically isolate all external state**: objects passed into Bindings can still be mutable, and the engine itself may retain internal state.

### 7.2. Using ScriptContext When Finer Control Is Needed

**ScriptContext** allows configuring the input Reader, output Writer, error Writer, and attributes:

~~~java
// Illustrative snippet: a valid engine has already been created.
javax.script.SimpleScriptContext context =
        new javax.script.SimpleScriptContext();
context.setBindings(engine.createBindings(),
        javax.script.ScriptContext.ENGINE_SCOPE);
context.setAttribute("name", "An",
        javax.script.ScriptContext.ENGINE_SCOPE);
context.setWriter(new java.io.StringWriter());

Object result = engine.eval("greet", context);
~~~

This snippet shows how to pass a custom context. MiniEngine in section 5 reads **name** from the context, so the result is **"Hello, An!"** when using that engine. However, the writer is only useful if the provider/syntax actually writes output—do not assume every engine automatically prints eval's return value to the writer.

Some engines use standard attributes like **ScriptEngine.FILENAME** to show the filename in diagnostics. You can set this attribute before eval, though file/line/column support and error formatting are **engine-specific**. If a file is loaded via a Reader, the engine does not automatically know the file path unless the caller/protocol provides that information.

### 7.3. Do Not Turn Bindings into a System-Privilege Container

Passing a richly privileged Java object into Bindings, such as a **DataSource**, filesystem handler, or HTTP client, can grant the script corresponding capabilities if the engine supports Java method invocation. Do not pass whole application objects or secrets when the script only needs a computed value.

For untrusted scripts, changing scopes or placing variables via Bindings **is not enough to sandbox**. Interop mechanisms, class lookups, and process privileges can still expand the attack surface.

## 8. Return Values and Exceptions

### 8.1. Object result Is Not Guaranteed to Be a String

Both **eval(String)** and **eval(Reader)** return **Object**. The Mini example returns a string from **greet** and an integer from **add**. JavaScript or other engines may return a Number, Boolean, String, script-language object, Java wrapper, or null, depending on syntax and engine.

Do not cast blindly:

~~~java
// Illustrative snippet of unsafe behavior if result is not a String.
String text = (String) engine.eval("add 2 3");
~~~

With MiniEngine, the line above will throw **ClassCastException** because result is an Integer. A safer approach is checking the type or enforcing an explicit data contract:

~~~java
// Illustrative snippet; use after obtaining an engine and defining the contract.
Object value = engine.eval("add 2 3");
if (!(value instanceof Number number)) {
    throw new IllegalStateException("Expected numeric result");
}
int sum = number.intValue();
~~~

When the engine returns null, distinguish **null as a valid result** from **missing result/contract violation**. Do not silently treat null as 0 or an empty string.

### 8.2. ScriptException and Other Error Types

**ScriptException** is the primary checked exception for script processing errors. It may contain a message, **fileName**, **lineNumber**, **columnNumber**, and cause depending on what information the provider can supply; many engines lack full location info, so do not assume every field is non-null or positive.

Error handling example:

~~~java
// Illustrative snippet; engine has already been configured.
try {
    Object result = engine.eval("invalid");
    System.out.println(result);
} catch (javax.script.ScriptException ex) {
    System.err.println("Script failed: " + ex.getMessage());
}
~~~

This is not a standalone Java class; in the MiniEngine example in section 5, "invalid" is an unsupported command and therefore always throws ScriptException. When reporting errors to users, translate them into messages that do not leak sensitive details, while recording **script version**, **engine name/version**, and **correlation ID** for investigation.

Other errors:
- **NullPointerException/IllegalArgumentException** when the caller passes invalid arguments or violates preconditions.
- **IOException** when the caller opens/closes the Reader, or I/O errors wrapped by the provider.
- **RuntimeException/Error** from the host/engine or Java objects invoked by the script. Do not treat every Throwable as a syntax error.
- **No engine**: manager returns null from getEngineByName; eval cannot even be called yet.

Classify **ENGINE_NOT_FOUND**, **INPUT_ERROR**, **SCRIPT_ERROR**, **RESULT_CONTRACT_ERROR**, and **EXECUTION_FAILURE** in logs/metrics instead of catching every error and returning the string "error".

## 9. String or Reader: Choosing in Real-World Systems

**Choose String** when the script is already in string form—for example, rendered from a controlled template, stored in a database and read as a String, or a short reviewed expression. The code is simple and makes it easy to compute a hash or record the source version before eval.

**Choose Reader** when the source is a file, a character stream, or an external API that already gives you a Reader. There is no need to read a file into a String only to wrap it in a StringReader for the sake of using Reader; for file sources, use **Files.newBufferedReader** and control charset/closing.

| Scenario | Suitable Input | Reason |
| --- | --- | --- |
| A few lines of rules generated from configuration | String | Full script is already available and easy to version |
| A UTF-8 script in a configuration directory | Reader | Read directly via file Reader, close properly per lifecycle |
| Content already in a String | String | Avoids unnecessary Reader wrapper |
| External library supplies a Reader | Reader | Uses the library's contract directly |
| Very large script | Do not decide by input type alone | Engine may buffer the whole source; benchmark and apply quotas |
| Running the same script many times | Check **Compilable** if provider supports it | Can reduce parse overhead; not every engine supports it |
| No suitable language provider | Neither overload helps | Must install an engine or choose another solution |

**Do not use StringReader to bypass validation:** passing a script through a Reader does not change the permissions or danger level of the evaluated code.

## 10. Optimizing Re-evaluation: Compilable and Invocable

Two extension interfaces **not implemented by every ScriptEngine**:

- **Compilable**: lets the engine compile a script once into a **CompiledScript**, then eval it multiple times. Measure parse/compile cost while also tracking script version and state/context.
- **Invocable**: can call functions/methods defined by an already evaluated script instead of re-evaluating the entire source each time.

Pattern for checking compilation support:

~~~java
// Illustrative snippet: engine and sourceScript are available; syntax depends on engine.
if (engine instanceof javax.script.Compilable compilable) {
    javax.script.CompiledScript compiled =
            compilable.compile(sourceScript);
    Object result = compiled.eval();
}
~~~

Do not cast if the provider does not support the interface. Compiling a script does not mean JavaCompiler; **Compilable** is the script engine's internal parse/compile capability, distinct from generating Java bytecode from .java files.

**Versioning/caching:** if the script source changes, do not reuse the compiled object from an old version without an explicit policy. Cache keys should consider source hash, engine/version, options/context, and dependencies whenever they alter semantics. Determine whether compiled scripts and the engine permit concurrent use across multiple threads.

## 11. Thread Safety, Lifecycle, and State Constraints

A ScriptEngine can retain state in:
- **Default ScriptContext** and ENGINE_SCOPE Bindings.
- Shared global bindings.
- Variables/functions created by scripts.
- Caches, module/script imports, and objects retained by the engine.

**Never assume a ScriptEngine is thread-safe by default.** A ScriptEngineFactory may advertise the **"THREADING"** parameter via getParameter to describe concurrent execution support under JSR 223 conventions. If the parameter is null or unknown, treat the engine as **unsafe for parallel eval**, or consult the provider's documentation; whether to create one instance per request/worker, use a controlled pool, or synchronize must be designed around the actual engine.

Separating **Bindings** per eval helps reduce variable leakage between tenants, but does not guarantee isolation when the provider has shared internals or shared object references. In multi-tenant environments, be especially careful with globalScope, Java interop, and references retained after evaluation.

Do not neglect lifecycle: Readers opened by the caller must be closed; engines/providers may manage their own resources; loaders holding JAR dependencies may need closing and dereferencing when unloading plugins. Do not assume that once eval returns, every resource or thread created by the script disappears automatically.

## 12. Security: eval Is Code Execution, Not Harmless String Processing

**Any script capable of running can have side effects** according to the permissions granted by the engine. In particular, if the engine allows interacting with Java objects/classes, scripts can invoke methods that perform I/O, send network requests, or access internal data exposed by the host.

Several principles:
1. **Only run trusted sources or sources that passed an appropriate vetting process.** Do not pass raw web-form input to eval if the engine's language has general-purpose execution capabilities.
2. **Do not interpolate user data directly into script source arbitrarily.** Pass data via Bindings/parameters if the language supports it, while still validating inputs. Do not treat Bindings as a sandboxing measure.
3. **Limit input size, execution time, CPU/memory, I/O, evaluation count**, and control lifecycle. Timeouts via Future.cancel are not guaranteed to stop arbitrary code running inside the same JVM.
4. **Do not expose high-privilege Java objects** to scripts unnecessarily; restrict class access using engine-supported mechanisms, without mistaking interop configuration for full process isolation.
5. **For untrusted scripts**, consider a restricted-capability DSL or running inside a genuinely isolated process/container with OS permissions and quotas.
6. **Log source version/hash and engine version**, while filtering diagnostics to avoid writing secrets or sensitive full scripts to logs.

Java 17 does not provide an automatic secure sandbox via javax.script alone. **SecurityManager** was marked deprecated for removal in Java 17 and should not be treated as a default strategy for executing untrusted code.

## 13. Common Errors and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| manager.getEngineByName("JavaScript") returns null | JDK 17 no longer bundles Nashorn by default; no JS engine installed | Install a compatible provider, check factories/names and loader |
| eval("class X {}") does not run Java as expected | The engine parses the scripting language syntax, not javac | Use JavaCompiler if you want to compile Java source |
| Script works with String but fails with Reader | Reader already consumed/closed, wrong charset, different content | Check Reader ownership, encoding, source content, version |
| eval(Reader) does not save RAM | Provider buffers the entire source | Benchmark and limit size; do not assume streaming |
| Variables leak between runs | Shared ENGINE_SCOPE/global objects, engine state | Use separate Bindings/context, control engine lifecycle |
| Casting result throws ClassCastException | eval returned a different type than expected | Check instanceof and normalize results per contract |
| ScriptException lacks line/column | Provider does not report location or did not receive file metadata | Check engine diagnostics; add filename context if supported |
| Engine fails across class loaders | Provider JAR missing/incompatible | Check the loader used by ScriptEngineManager, dependencies, and module graph |
| Multiple requests share an engine and produce erratic results | Engine does not support concurrency | Check THREADING docs, isolate instances, or synchronize |
| Untrusted script input creates risk | eval can execute code/Java interop | Design isolation, API allowlists, and runtime limits |

**Practical warning:** ScriptEngine.eval is not designed to replace an input-validation parser. If the requirement is merely validating a number, matching a regex, or mapping simple JSON, plain Java code or a constrained DSL is usually easier to audit and safer than a general-purpose script engine.

## 14. Checklist for Runtime-Extensible Systems

- Identified the **scripting language** and corresponding provider, without relying on an engine removed from the JDK.
- Verified **ScriptEngineManager** finds the factory with the right name and class loader/module.
- Chose **String** when the text is already in memory or **Reader** when character input comes from a file/stream, with explicit encoding/ownership.
- Understood that eval returns **Object**, possibly null; normalized and validated results.
- Used **Bindings/ScriptContext** to pass data instead of interpolating unvalidated input directly into source.
- Categorized **ScriptException**, IOException when opening a Reader, and runtime/type-contract errors.
- Verified thread safety/state and **Compilable/Invocable** support before optimizing/caching.
- Clearly decided which trust boundary scripts execute inside; if untrusted, did not rely on eval/Bindings as a sandbox.
- Put in place resource limits, source version/hash tracking, filtered logs/diagnostics, and rollback mechanisms.
- Tested both **eval(String)** and **eval(Reader)** with equivalent content against the exact provider used in production.

**Conclusion:** **eval(String)** and **eval(Reader)** are two ways to feed *code of a scripting language* into the same JSR 223 interface. String is convenient when source is already text; Reader is convenient when source is a character stream. The difference in input form does not change the requirement for a **ScriptEngine provider**, Bindings control, error handling, and protecting the execution boundary.

## Official Java 17 Documentation

- ScriptEngine: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- AbstractScriptEngine: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html
- ScriptEngineManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html
- ScriptContext: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html
- ScriptException: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html
- JEP 372 (Remove the Nashorn JavaScript Engine): https://openjdk.org/jeps/372
