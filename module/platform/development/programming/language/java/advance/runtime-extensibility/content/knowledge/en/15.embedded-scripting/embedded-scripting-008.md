# Controlling Input, Output, and Errors via ScriptContext

When embedding a scripting language in a Java application, the host usually does not want every script reading directly from the keyboard, printing to the shared terminal, or dumping every error into the JVM log. Each script run may come from a different request, needing its own input, writing output to a separate memory buffer or file, and returning errors in a controlled format.

**The Java Scripting API (JSR 223), in the java.scripting module**, provides **javax.script.ScriptContext** to describe the execution context. For a ScriptEngine supporting this interface, the host can supply three character-based I/O channels:

- **Reader** from context.getReader(): data the script can read as input.
- **Writer** from context.getWriter(): normal output sent by the engine/script.
- **Writer** from context.getErrorWriter(): error or warning output explicitly sent by the engine/script.

ScriptContext also holds scoped **Bindings** so scripts can exchange variables with the host. However, **ScriptContext does not redirect System.in/System.out/System.err for the entire JVM**, does not automatically convert exceptions into error text, and is not a security sandbox. The engine itself must actually use the supplied channels.

This article covers the mechanism, how to manage each channel, scopes, errors, resources, and a Java 17+ example **independent of external JavaScript engines**.

## 1. Host → Script Engine → ScriptContext Model

A single execution can be visualized as follows:

~~~text
Java Host
  |
  | prepares input, output, error, bindings
  v
SimpleScriptContext
  ├── Reader            ← data read by script (input)
  ├── Writer            → normal output
  ├── ErrorWriter       → warnings/errors written by script/engine
  ├── ENGINE_SCOPE      → prioritized variables for this run
  └── GLOBAL_SCOPE      → shared/fallback variables depending on config
  |
  | engine.eval(scriptSource, context)
  v
ScriptEngine
  ├── may read context.getReader()
  ├── may write context.getWriter()/getErrorWriter()
  ├── may access context.getAttribute(...) / getBindings(...)
  ├── returns Object when eval finishes
  └── may throw ScriptException
~~~

**ScriptEngine** executes the syntax of a language or DSL. **ScriptContext** holds the variables and I/O channels used during that execution. **ScriptEngineManager** is the mechanism for discovering registered engines, not the engine or context itself.

Java 17+ provides the **javax.script** API, but **does not guarantee an available JavaScript engine**. Nashorn was removed from the JDK starting in JDK 15; to actually evaluate JavaScript, an application must install a compatible engine separately. Therefore, the example in this article uses a MiniEngine implementing three simple commands to demonstrate **the Java API mechanism**; it does not pretend to be a JavaScript interpreter.

### Three I/O Channels Serve Three Distinct Roles

| Method | Java Type | Role | Host-Supplied Examples |
| --- | --- | --- | --- |
| context.setReader(reader) | java.io.Reader | Input readable by script/engine | StringReader, BufferedReader from a file |
| context.setWriter(writer) | java.io.Writer | Normal script output | StringWriter, file writer |
| context.setErrorWriter(writer) | java.io.Writer | Warning/error channel written by script/engine | Separate StringWriter or log writer |

These APIs operate on **characters**, not byte-based InputStream/OutputStream. If input comes from a network socket or binary file, the host must decode bytes with an explicit charset (typically UTF-8) to construct a Reader. If output must be saved to a file or HTTP response, the corresponding Writer handles encoding characters to bytes.

**Distinguish two ways of supplying a Reader:**

- engine.eval(new StringReader("...script source..."), context) passes **script source code** for the engine to read and execute.
- context.setReader(new StringReader("...input data...")) passes **input data the script can consume while running**.

These two Readers serve completely different purposes. The example below uses both to demonstrate the difference.

## 2. Controlling Input with setReader/getReader

The host can swap the input source per eval invocation:

~~~java
ScriptContext context = new SimpleScriptContext();
context.setReader(new StringReader("An\n"));

Object result = engine.eval("greet", context);
~~~

This is an **illustrative snippet placed inside a method** after obtaining a suitable engine object and importing javax.script.* and java.io.StringReader; it is not a standalone runnable program. The engine must have logic to **read context.getReader()** for the data "An" to actually be consumed.

An engine may support script statements like readLine or input; function names are defined by each language/engine—JSR 223 does not inject an input command into every language automatically.

Practical considerations:

1. **Finite input:** StringReader reads until the end and returns EOF. If a script needs input a second time, provide a new reader or design a purposefully reusable input stream.
2. **Do not share a reader across independent requests:** one read can consume another request's data or exhaust input for the next run.
3. **Size and time limits:** externally supplied input can be huge, unbounded, or block on reads. Enforce limits before passing a Reader to the engine.
4. **Charset:** prefer Files.newBufferedReader(path, StandardCharsets.UTF_8) when reading files to avoid depending on the OS default charset.
5. **Ownership:** the host must know who closes the Reader. Calling context.setReader does not mean ScriptContext will close the Reader automatically after eval.

Never mutate JVM-wide System.setIn(...) just to handle a single script, as it affects other threads running in the same process.

## 3. Controlling Normal Output with setWriter/getWriter

To capture output in memory instead of letting it go to the console:

~~~java
StringWriter captured = new StringWriter();
context.setWriter(captured);
Object result = engine.eval("greet", context);
String text = captured.toString();
~~~

This is also an **illustrative snippet** with an existing context/engine and import java.io.StringWriter. When the engine/script calls context.getWriter().write(...), that text is stored in the StringWriter. With a BufferedWriter or network writer, the host/engine may need flush() so data reaches the receiver before completion.

**The Object returned by eval is not the same as Writer output.** A script can both print multiple lines and return a value. For example, a script function returns a username while also printing a greeting; the host should keep both results separate.

Configuring this Writer **does not automatically capture**:

- Java code inside the engine calling System.out.println(...) directly without going through context.
- A native library, logger, subprocess, or other API writing outside the Writer channel.
- Language-specific console APIs that the engine implementation does not route to ScriptContext.

Therefore, before promising that all script output is captured, **verify against the actual engine**. If plugins/scripts use Java interop or external libraries, establish appropriate logging policies and isolation outside ScriptContext.

## 4. Controlling the Error Channel with setErrorWriter/getErrorWriter

The host should use a separate Writer for errors:

~~~java
StringWriter normal = new StringWriter();
StringWriter errors = new StringWriter();
context.setWriter(normal);
context.setErrorWriter(errors);
~~~

When the engine intentionally writes warnings via context.getErrorWriter().write(...), the content goes into errors without mixing with normal.

However, there are **two distinct forms of error**:

1. **Error/warning text written to errorWriter:** for example, an interpreter emitting a warning. This is data sent by the engine and can happen even when eval succeeds.
2. **ScriptException thrown by engine.eval:** for example, syntax or runtime errors reported via a Java exception. Throwing ScriptException **does not guarantee** anything is written to context.getErrorWriter(). The host must catch the exception and record the error per policy.

ScriptException exposes diagnostic fields such as **getMessage()**, **getFileName()**, **getLineNumber()**, and **getColumnNumber()** (if supplied by the engine). Not every engine populates file/line/column completely; handle missing values gracefully.

Example of how the host can handle it:

~~~java
try {
    engine.eval(scriptSource, context);
} catch (ScriptException ex) {
    // Host policy: write a filtered message to the error channel.
    context.getErrorWriter().write("Script failed\n");
    context.getErrorWriter().flush();
}
~~~

This is an **illustrative snippet** inside a method that handles IOException and declares engine, scriptSource, and context. In production, log the technical root cause server-side while returning a controlled message that avoids leaking host paths, secrets, or internal stack traces. Catching every Throwable and ignoring it is never safe error handling.

## 5. How Engine Scope and Global Scope Affect Script Data

ScriptContext has two standard scopes:

~~~text
ScriptContext.ENGINE_SCOPE = 100
ScriptContext.GLOBAL_SCOPE = 200
~~~

Each scope holds a **Bindings**, essentially a name → Object map. Calling context.getAttribute("name") searches scopes in ascending numeric order: **ENGINE_SCOPE first, GLOBAL_SCOPE second**. If the same variable name exists in both places, the ENGINE_SCOPE value takes precedence.

Example:

~~~java
SimpleScriptContext context = new SimpleScriptContext();
context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);
context.setAttribute("prefix", "GLOBAL: ", ScriptContext.GLOBAL_SCOPE);
context.setAttribute("prefix", "ENGINE: ", ScriptContext.ENGINE_SCOPE);

System.out.println(context.getAttribute("prefix")); // ENGINE:
context.removeAttribute("prefix", ScriptContext.ENGINE_SCOPE);
System.out.println(context.getAttribute("prefix")); // GLOBAL:
~~~

The snippet above is a self-contained illustration **placed inside a method with `import javax.script.*`**. You can query explicitly with context.getAttribute("prefix", ScriptContext.GLOBAL_SCOPE) to bypass the precedence rule.

**Frequently overlooked detail:** SimpleScriptContext comes with a Bindings for ENGINE_SCOPE by default, while **GLOBAL_SCOPE defaults to null**. If you want to set global variables, call setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE) first. On SimpleScriptContext, calling setAttribute on GLOBAL_SCOPE when no global bindings exists is a no-op; do not assume the variable was stored.

Other methods:

| API | Result / Purpose |
| --- | --- |
| getBindings(scope) | Gets the Map-like Bindings for the specified scope |
| setBindings(bindings, scope) | Replaces the entire variable map of that scope |
| setAttribute(name, value, scope) | Writes a variable into a specific scope |
| getAttribute(name) | Looks up a variable following scope order |
| getAttribute(name, scope) | Reads a variable from that exact scope only |
| getAttributesScope(name) | Returns the first scope containing the name; -1 if absent |
| removeAttribute(name, scope) | Removes a variable from a specific scope |
| getScopes() | Lists valid scopes in ascending order |

For an independent script request, the host can create a **new SimpleScriptContext** to keep ENGINE_SCOPE, Reader, Writer, and ErrorWriter isolated. If GLOBAL_SCOPE holds shared data, assess cross-request visibility and the risk of inadvertent information disclosure. Shared Bindings is not an access-control mechanism.

## 6. Runnable Java 17 Example: Input, Output, Errors, and Scope Together

JDK 17 has no reliable default JavaScript engine, so this example builds a minimal **MiniEngine** implementing ScriptEngine by extending AbstractScriptEngine. It understands only three commands—**greet**, **warn**, and **fail**—and is not a JavaScript parser or polyglot runtime. Its purpose is verifying the exact Java **ScriptContext** API.

MiniEngine:

- greet reads one line from context.getReader(), looks up prefix in Bindings, writes one line to context.getWriter(), and returns the String read.
- warn writes one line to context.getErrorWriter() and returns null.
- fail throws ScriptException with line number 3; it **does not automatically write** the error message to errorWriter.
- eval(Reader, context) reads **command source** from the Reader passed directly, without mixing it with input data in context.

### 6.1. Complete Source Code

Create a single file **ScriptContextDemo.java**:

~~~java
import java.io.BufferedReader;
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
import javax.script.ScriptException;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class ScriptContextDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new MiniEngine();
        SimpleScriptContext context = new SimpleScriptContext();
        context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);

        StringWriter output = new StringWriter();
        StringWriter errors = new StringWriter();
        context.setWriter(output);
        context.setErrorWriter(errors);

        context.setAttribute("prefix", "GLOBAL: ", ScriptContext.GLOBAL_SCOPE);
        context.setAttribute("prefix", "ENGINE: ", ScriptContext.ENGINE_SCOPE);
        context.setReader(new StringReader("An\n"));
        Object first = engine.eval("greet", context);

        context.removeAttribute("prefix", ScriptContext.ENGINE_SCOPE);
        context.setReader(new StringReader("Binh\n"));
        Object second = engine.eval(new StringReader("greet\n"), context);

        engine.eval("warn", context);
        try {
            engine.eval("fail", context);
        } catch (ScriptException ex) {
            System.out.println("caughtLine=" + ex.getLineNumber());
        }

        System.out.println("return1=" + first);
        System.out.println("return2=" + second);
        System.out.println("prefixScope=" +
                context.getAttributesScope("prefix"));
        System.out.println("capturedOut=" +
                output.toString().replace("\n", "|"));
        System.out.println("capturedErr=" +
                errors.toString().replace("\n", "|"));
    }

    private static final class MiniEngine extends AbstractScriptEngine {
        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            String command = script.strip();
            try {
                if (command.equals("greet")) {
                    String name = new BufferedReader(context.getReader())
                            .readLine();
                    if (name == null) {
                        throw new ScriptException("No input");
                    }
                    String prefix = String.valueOf(
                            context.getAttribute("prefix"));
                    context.getWriter().write(prefix + name + "\n");
                    context.getWriter().flush();
                    return name;
                }
                if (command.equals("warn")) {
                    context.getErrorWriter().write("WARN: demo\n");
                    context.getErrorWriter().flush();
                    return null;
                }
                if (command.equals("fail")) {
                    throw new ScriptException("Demo failure", "mini", 3);
                }
                throw new ScriptException("Unknown command: " + command);
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
        }

        @Override
        public Object eval(Reader script, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buffer = new char[256];
                int n;
                while ((n = script.read(buffer)) != -1) {
                    source.append(buffer, 0, n);
                }
                return eval(source.toString(), context);
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
            return new MiniFactory();
        }
    }

    private static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniEngine"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("mini"); }
        @Override public List<String> getMimeTypes() { return List.of(); }
        @Override public List<String> getNames() { return List.of("mini"); }
        @Override public String getLanguageName() { return "MiniCommands"; }
        @Override public String getLanguageVersion() { return "1.0"; }
        @Override public Object getParameter(String key) { return null; }
        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) { return ""; }
        @Override public String getOutputStatement(String toDisplay) {
            return "";
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniEngine();
        }
    }
}
~~~

MiniFactory is only the minimal factory interface implementation needed for the example. Methods returning empty strings or null language parameters are **not a factory template for a production engine**. The program instantiates new MiniEngine() directly; it **does not register** MiniEngine with ScriptEngineManager. In a real project, an engine's factory must accurately advertise the names, syntax, and features actually supported by that runtime.

### 6.2. Compile and Run

In the directory containing **ScriptContextDemo.java**, run with JDK 17 or newer:

~~~powershell
javac --release 17 -encoding UTF-8 ScriptContextDemo.java
java ScriptContextDemo
~~~

On Linux/macOS the two commands are identical; a JDK must be installed for javac. The filename must match the public class ScriptContextDemo.

**Exact stdout:**

~~~text
caughtLine=3
return1=An
return2=Binh
prefixScope=200
capturedOut=ENGINE: An|GLOBAL: Binh|
capturedErr=WARN: demo|
~~~

The example above was **actually compiled with javac --release 17 and executed**. In stdout, the | symbol is inserted by main's formatting code to **replace newlines** in the captured output, not written by MiniEngine itself.

### 6.3. Line-by-Line Explanation

- **caughtLine=3:** the fail command throws ScriptException with line number 3, which the host catches. This exception **does not go into errorWriter automatically**.
- **return1=An:** this is the **Object** value returned by engine.eval("greet", context), not the output line.
- **return2=Binh:** on the second call, script source is supplied via eval(new StringReader("greet\n"), context), while user input data is read separately through context.getReader().
- **prefixScope=200:** after removing prefix from ENGINE_SCOPE, getAttributesScope returns GLOBAL_SCOPE. Before removal, the matching variable in ENGINE_SCOPE (100) took precedence.
- **capturedOut=ENGINE: An|GLOBAL: Binh|:** both greetings go into **StringWriter output**, first using the engine variable, then falling back to the global variable.
- **capturedErr=WARN: demo|:** the warn command writes to **StringWriter errors**. The fail command does not add anything to errorWriter.

The example runs two consecutive calls on the same SimpleScriptContext to make scope changes easy to observe. In a multi-user service, **do not reuse a context containing one user's input/output/error for another user**. Rather than simulating concurrent requests with a shared context, create a dedicated context per request.

## 7. Using ScriptContext with a Real Engine

If your application has a JSR 223–compatible ScriptEngine installed, basic API usage looks like this example:

~~~java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("language-name");

if (engine == null) {
    throw new IllegalStateException("Script engine not installed");
}

SimpleScriptContext ctx = new SimpleScriptContext();
ctx.setReader(new StringReader("input for script\n"));
ctx.setWriter(new StringWriter());
ctx.setErrorWriter(new StringWriter());

Object value = engine.eval(scriptSource, ctx);
~~~

This is an **illustrative integration snippet, not standalone runnable**: it requires importing javax.script.*, java.io.*, a scriptSource variable, and replacing language-name with the name of a real deployed engine. Input-reading functions inside scripts **depend on the language**. Never assume getEngineByName("JavaScript") always returns a non-null engine on Java 17+.

Compared to calling engine.eval(scriptSource) alone, the **eval(scriptSource, ctx)** overload forces the engine to use the **host-supplied context** rather than relying on the engine's default context. This is useful when one engine instance orchestrates sequential eval calls with different readers/writers and scopes, though you must still check the engine's thread-safety documentation.

### Explicit ScriptContext vs. engine.getContext()

There are two common configuration patterns:

1. **engine.setContext(ctx); engine.eval(script);** replaces the default context attached to the engine object.
2. **engine.eval(script, ctx);** passes an explicit context for a single eval call.

Approach (2) is usually easier to manage in multi-request hosts because it avoids mutating the engine's internal default context state. However, **it does not make an engine instance safe for concurrent calls**; the engine may still hold internal state outside ScriptContext.

Calling engine.put("key", value) and engine.get("key") typically operates on **ENGINE_SCOPE of the engine's default context**. They do not necessarily affect a **separate SimpleScriptContext** passed to eval(script, ctx). Therefore, to control per-request variables, operate directly on ctx.setAttribute or ctx.getBindings.

## 8. Routing Input/Output/Errors to Files Instead of StringWriter

For controlled tasks with dedicated directories, the host can open Reader/Writer streams via Files:

~~~java
try (Reader input = Files.newBufferedReader(
             inputPath, StandardCharsets.UTF_8);
     Writer output = Files.newBufferedWriter(
             outputPath, StandardCharsets.UTF_8);
     Writer errors = Files.newBufferedWriter(
             errorPath, StandardCharsets.UTF_8)) {

    SimpleScriptContext ctx = new SimpleScriptContext();
    ctx.setReader(input);
    ctx.setWriter(output);
    ctx.setErrorWriter(errors);

    engine.eval(scriptSource, ctx);
    output.flush();
    errors.flush();
}
~~~

This is an **illustrative snippet placed inside a method handling IOException and ScriptException**, with variables inputPath, outputPath, errorPath, engine, scriptSource and imports java.nio.file.Files, java.nio.charset.StandardCharsets, java.io.Reader/Writer, and javax.script.SimpleScriptContext. It is not a standalone compilable file. Default file writers may create/truncate target files depending on OpenOption; check overwrite policies before running on real data.

**try-with-resources** is where the host takes responsibility for closing streams it opened. ScriptContext itself does not promise to close resources after eval. If a Writer is shared across requests or managed elsewhere, the closing policy must differ; never close a Writer prematurely while the engine is still using it.

If eval throws ScriptException, try-with-resources still closes the streams, though the host should catch the exception outside or inside to record the failure state. To guarantee flushing and saving errors to a file before closing, structure catch/finally ordering carefully. When writing over a network, writers can also block, fill buffers, or hit I/O errors; apply appropriate timeouts and output limits.

## 9. ErrorWriter, Exceptions, and Logging Must Be Properly Separated

In a real system, distinguish at least four kinds of information:

| Channel | Examples | How to Collect |
| --- | --- | --- |
| Script output | Data the user wants produced | context.getWriter() if supported by engine |
| Script diagnostic text | Interpreter warnings, non-throwing errors | context.getErrorWriter() if supported by engine |
| Java exceptions | ScriptException and root cause | Caught and handled directly by host |
| Host/framework/JVM logs | Loggers, System.err, process messages | Dedicated logging/observability system |

Do not call context.setErrorWriter and assume you captured all of System.err. Do not treat non-empty errorWriter content as proof that compilation/execution failed; a script can emit a warning and still return a valid result. Conversely, an empty errorWriter does not prove eval succeeded, because an exception may have been thrown directly.

When returning errors to a client, build a structured response shape:

~~~text
ExecutionResult
  status: SUCCESS | SCRIPT_ERROR | ENGINE_ERROR | TIMEOUT
  returnValue: validated/converted value
  outputText: characters received by normal Writer
  diagnosticText: characters received by ErrorWriter
  errorMessage: safe message from exception if any
  line: error location if provided by engine
~~~

The block above is only a **data schema**, not a runnable Java class. Separate raw engine diagnostics from user-facing messages; sanitize data before rendering in a UI, especially if output contains HTML or private information.

In runtimes with their own console APIs, if you need to capture console.log, print, or stack traces, consult the **exact ScriptEngine's documentation** to see whether they route to the context Writer. ScriptContext does not force every language output mechanism to use its three channels.

## 10. One Context per Request: Avoiding Data Leaks and Race Conditions

For a service executing scripts for multiple users, a sensible architecture is:

~~~text
Request A → ScriptContext A → Reader A / Writer A / ErrorWriter A / Bindings A
Request B → ScriptContext B → Reader B / Writer B / ErrorWriter B / Bindings B
                                  |
                       ScriptEngine/engine pool
                       per concurrency policy
~~~

Principles to decide explicitly:

- **Create a separate context per task** so inputs/outputs of different requests never mix.
- **Never share mutable Bindings containing private data** across users; GLOBAL_SCOPE is not a security boundary.
- **Never swap JVM-wide System.out/System.err/System.in** to redirect one script; doing so interferes with other threads and the host itself.
- **Never let a Writer grow unbounded** if a script can print huge amounts of data; enforce character limits or bounded streams.
- **Never share a ScriptEngine across threads by default.** Check the engine's contract and threading info if available, typically via ScriptEngineFactory.getParameter("THREADING"). Advertised values/limits must be interpreted using that exact implementation's documentation.
- **Never treat ScriptContext as a sandbox.** A script engine may let scripts call Java classes or act outside the context depending on language and configuration.
- **Timeouts/infinite loops** are not ScriptContext's responsibility; when running untrusted scripts, use OS processes/containers and enforce CPU, RAM, I/O, and network limits.

Note on running multiple scripts "concurrently": giving each request its own context **does not automatically make the engine thread-safe**. Some engines keep global variables or internal runtime state; create a new engine per request, synchronize, or manage an engine pool according to the engine's documentation.

## 11. Common Issues and How to Diagnose Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| setWriter called yet console still prints to System.out | Engine/library writes directly to System.out or a logger | Check engine implementation and exact output paths |
| ErrorWriter is empty even though eval threw an error | Exceptions do not automatically become error text | Catch ScriptException and build structured diagnostics |
| Input is always EOF | Reader was already exhausted in a prior eval | Supply a fresh Reader per task/read pass |
| Eval cannot see the prefix variable just set | Set on default context instead of the context passed to eval | Verify exact context instance and scope |
| Global variable does not exist | Forgot to call setBindings for GLOBAL_SCOPE on SimpleScriptContext | Initialize Global Bindings before calling setAttribute |
| ENGINE_SCOPE overrides GLOBAL_SCOPE | Lookup checks lower scope number first | Use getAttribute(name, scope) or remove the engine variable |
| Two Readers caused data to be "misread" | Confused script source Reader with context input Reader | Separate the two streams by role |
| getEngineByName returns null | Language engine not installed/registered | Check JDK runtime, engine JAR, and ScriptEngineFactory |
| Writer closed too early | Host closed it before engine wrote or flushed | Manage ownership, wait/cancel task before closing |
| Output/errors mixed between users | Shared context, writer, or mutable bindings | Create per-task instances, track request IDs |
| Script never terminates | Blocking input, infinite loop, pending I/O | Enforce timeouts and process/resource limits |
| ScriptException file/line unexpected | Engine lacks metadata or sets its own filename | Check getFileName/getLineNumber and engine contract |

A frequent bug pattern:

~~~java
engine.put("user", "An");
engine.eval(scriptSource, mySeparateContext);
~~~

Those two statements **illustrate a potential bug**, because engine.put modifies the engine's default ENGINE_SCOPE, not necessarily the ENGINE_SCOPE of mySeparateContext. To ensure `user` is visible during this eval call, write:

~~~java
mySeparateContext.setAttribute(
        "user", "An", ScriptContext.ENGINE_SCOPE);
engine.eval(scriptSource, mySeparateContext);
~~~

These snippets assume existing engine, scriptSource, and mySeparateContext variables; they are not standalone Java classes.

## 12. QA Checklist for a Script Host

Before integrating ScriptContext into runtime extensibility:

1. **Identify the engine:** language, version, JSR 223 support, and ScriptEngineFactory installation/registration mechanism.
2. **Prepare per-request context:** create separate ENGINE_SCOPE; use GLOBAL_SCOPE only for intentionally shared data.
3. **Control input:** call setReader with a Reader of known origin, charset, size limit, and EOF policy.
4. **Separate output and errors:** call setWriter/setErrorWriter targeting two inspectable destinations; flush/close according to ownership.
5. **Pass context explicitly:** prefer engine.eval(script, ctx) when isolating runs from the default context.
6. **Check return values:** keep the Object returned by eval separate from characters printed by the script.
7. **Catch ScriptException:** extract file/line metadata if available; do not rely solely on ErrorWriter.
8. **Test failure modes:** scripts printing nothing, printing huge output, empty Reader, failing Writer, and errors containing Unicode or sensitive data.
9. **Test real engine streams:** confirm the language's input/output/error primitives actually honor ScriptContext.
10. **Isolate execution if needed:** ScriptContext only controls JSR 223 I/O APIs used by the engine; it does not replace process boundaries or security policies.

### Self-Check Questions

**Once setWriter is called, are all System.out.println calls inside a plugin guaranteed to be captured?** No. Writing directly to System.out uses a different mechanism; output is captured only if the engine/plugin actively uses the context Writer or the host establishes controlled redirection separately.

**If eval throws ScriptException, does ErrorWriter always contain error text?** No. They are two independent mechanisms; the host must catch the exception.

**Why does getAttribute("prefix") return the ENGINE_SCOPE value even when GLOBAL_SCOPE has the same name?** Because scope 100 precedes 200 in lookup order.

**What does ScriptEngine.eval(Reader, context) read?** The Reader passed directly to eval holds **script source**; context.getReader holds **input consumed by the script** if supported by the engine.

**Does calling eval(script, context) guarantee multithreaded safety?** No. Per-call context is only one part of the design; engine thread safety and shared resources must be verified separately.

**Does ScriptContext prevent scripts from accessing files or the network?** No. It is only an I/O and Bindings context object in JSR 223, not a sandboxing mechanism.

### Standard References

- Oracle Java SE 17 **javax.script.ScriptContext**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html
- Oracle Java SE 17 **javax.script.SimpleScriptContext**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html
- Oracle Java SE 17 **javax.script.ScriptEngine**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- Oracle Java SE 17 **javax.script.AbstractScriptEngine**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html
- Oracle Java SE 17 **javax.script.ScriptException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html
- OpenJDK **JEP 372: Remove the Nashorn JavaScript Engine**: https://openjdk.org/jeps/372

**Conclusion:** ScriptContext lets a host pass **Reader**, **Writer**, **ErrorWriter**, and **Bindings** for each script execution without altering JVM-wide system streams. For embedded scripting to work reliably, separate script source from input data, output text from return values, diagnostic writers from ScriptException, and API context objects from true execution isolation mechanisms.
