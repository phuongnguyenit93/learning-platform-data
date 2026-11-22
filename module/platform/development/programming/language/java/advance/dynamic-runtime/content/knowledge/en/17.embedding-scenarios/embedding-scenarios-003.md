# 17.3 `eval` from `String` or `Reader` and handling `ScriptException`

In Java, JSR 223 (Scripting API) provides the `javax.script.ScriptEngine` interface to run source code **of a scripting language supported by the engine**. Two common ways to pass source are `engine.eval(String)` and `engine.eval(Reader)`: the first receives text already in Java memory; the second receives a character source through `java.io.Reader`, such as `StringReader` or `Files.newBufferedReader(path, UTF_8)`. Both return a result of Java type `Object`, and both can throw **`ScriptException`**, a checked exception of the Scripting API.

This lesson focuses on **how to use the `eval` overloads properly, manage input sources, and handle script errors**. It also explains why on Java 17+ there is no default JavaScript engine: **Nashorn was removed from the JDK starting in Java 15 (JEP 372)**. The `ScriptEngine`, `ScriptEngineManager`, and `ScriptException` classes still reside in the standard `java.scripting` module, but executing a specific language depends on **an engine provider actually being present**.

What you will learn from this lesson:

- Distinguish the six `eval` overloads by `String`/`Reader` and `Bindings`/`ScriptContext`.
- Understand that the script source is **the engine's language** (JavaScript, Groovy, DSL...), not Java source automatically compiled by `eval`.
- Handle engine lookup returning `null`, especially when migrating from JDK 8 to JDK 17+.
- Use `StringReader` or a reader for UTF-8 files, and close the reader at the right boundary.
- Manage state via `ENGINE_SCOPE`, `GLOBAL_SCOPE`, and per-call `Bindings`.
- Catch `ScriptException`; safely read `getMessage()`, `getFileName()`, `getLineNumber()`, `getColumnNumber()`, and `getCause()`.
- Distinguish script syntax/evaluation errors from file reading errors (`IOException`), configuration errors, and Java unchecked errors.
- Practice with **a minimal ScriptEngine that runs on Java 17+** without installing extra libraries, an engine discovery demo, and a `ScriptException` metadata demo.
- Avoid mistakes regarding trust boundaries, isolation, thread safety, and assuming the `eval` result always has a fixed type.

## 1. The big picture of `javax.script`

A typical usage flow:

```text
                   Java application
                         |
                         v
                  ScriptEngineManager
                         |
             find provider by name
                         |
           +-------------+-------------+
           |                           |
       engine found                engine == null
           |                           |
           v                           v
    ScriptEngine instance        report missing provider
           |
           +-- eval(String source)
           |
           +-- eval(Reader source)
           |
           +-- eval(..., Bindings)
           |
           +-- eval(..., ScriptContext)
           |
           +-- result: Object (may be null)
           |
           +-- failure: ScriptException (or other runtime errors)
```

Representative classes:

| API | Role |
| --- | --- |
| `ScriptEngineManager` | Discovers `ScriptEngineFactory` providers via the service mechanism, finds engines by name/language/extension/MIME |
| `ScriptEngine` | Script execution contract, manipulating bindings, context, and returning results |
| `ScriptEngineFactory` | Engine/language metadata and factory to create `ScriptEngine` |
| `ScriptContext` | Holds `Bindings` by scope and readers/writers used by the engine |
| `Bindings` | Map of Java names/values provided to the script in a scope |
| `SimpleBindings` | Simple `Bindings` implementation |
| `SimpleScriptContext` | `ScriptContext` implementation with scopes and I/O streams |
| `AbstractScriptEngine` | Base class helping engine authors implement multiple `eval` overloads |
| `ScriptException` | Common checked exception to report errors occurring when executing/interpreting a script |

When a program runs on the **classpath**, Java 17's `java.scripting` module is used when needed. If your application is compiled as a **named module**, you need to declare the dependency:

```java
module my.application {
    requires java.scripting;
}
```

This is an **illustrative `module-info.java` snippet**, not a standalone program.

### 1.1. Important on Java 17+: no default JavaScript engine

JDK 8 used to include the Nashorn JavaScript engine. Nashorn was deprecated in Java 11 and **removed from JDK 15**. Therefore, on a plain JDK 17, the snippet:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("JavaScript");
```

can return `null`. If `engine.eval(...)` is called immediately afterward, the error will be **`NullPointerException`**, with no script having been run at all. Java still has the Scripting API, but **does not guarantee providing an engine for a language named "JavaScript"**.

Only when you have added a compatible provider (via dependencies/module path/classpath and appropriate service registration) can `getEngineByName(...)` find it. Engine name, language version, and evaluation behavior depend on the actual provider.

**Separate the two steps:** finding/initializing the engine is **discovery/configuration**; `eval` is **execution**. Do not lump `engine == null` errors into `ScriptException`.

## 2. The six `eval` overloads and usage contexts

The `ScriptEngine` interface has the main overloads:

| Overload | Source input | Context/bindings used for evaluation |
| --- | --- | --- |
| `eval(String script)` | Java string containing script source | Engine's **default `ScriptContext`** |
| `eval(Reader reader)` | Character source providing the script | Default `ScriptContext` |
| `eval(String script, Bindings bindings)` | Script string | Uses `bindings` as **`ENGINE_SCOPE`** for the call |
| `eval(Reader reader, Bindings bindings)` | Script reader | Uses `bindings` as `ENGINE_SCOPE` for the call |
| `eval(String script, ScriptContext context)` | Script string | Uses the explicitly passed `ScriptContext` |
| `eval(Reader reader, ScriptContext context)` | Script reader | Uses the explicitly passed `ScriptContext` |

A usage pattern from the application side:

```java
// Illustrative snippet: engine is a ScriptEngine that has already been found.
Object a = engine.eval("add 2 3");

try (Reader source = new StringReader("add 4 5")) {
    Object b = engine.eval(source);
}

Bindings oneCall = engine.createBindings();
oneCall.put("x", 10);
Object c = engine.eval("get x", oneCall);
```

**Note:** `"add 2 3"` and `"get x"` are the syntax of the **MiniCalc toy engine in the full example below**, not JavaScript or standard JSR 223 syntax. When using a real JavaScript provider, you must write valid script according to that language/provider, for example the expression `1 + 2`, subject to the semantics of the corresponding engine.

### 2.1. `eval(String)` does not mean running Java source

`String script = "System.out.println(1)";` is a Java string. `eval(script)` will send **that string's content** to the interpreter/compiler of the chosen scripting engine. If the engine understands a DSL with an `add` command, Java source may be reported as a syntax error. If the engine is JavaScript, the syntax and type system are defined by that JavaScript engine, not by the `javac` compiler.

JSR 223 is **a Java interface to scripting languages**, not a dynamic `javac`; nor is it an API for Java to natively understand every scripting language.

### 2.2. `eval(Reader)` does not mean "read line by line then call eval(String)"

`Reader` provides a character stream. **How the engine parses/evaluates source** depends on the implementation: one provider may read everything then parse; another provider may execute incrementally; one engine may support multiple statements, while another only supports a single expression.

In the MiniCalc demo, we **deliberately** define the semantics: read line by line, process `add`/`get` commands, then return **the result of the last non-blank line**. This is a contract set by the toy engine itself, not a requirement for every `ScriptEngine`.

Do not infer that `Reader` always saves more memory than `String` on every engine: even if the Java caller does not hold the entire source in a String itself, the engine may still read it into memory when parsing. To evaluate streaming/memory behavior, consult the actual provider's documentation.

## 3. When to choose `String`, when to choose `Reader`?

### Choose `eval(String)` when

- The script is small or already resides in a Java variable or config read as a string.
- You need to generate script content from a controlled template, after validating input.
- You want to quickly test an expression or a short DSL snippet.
- You prefer controlling the source and possibly logging an identifier/hash instead of logging the entire code.

Illustrative example:

```java
String source = "add 8 13";
Object result = engine.eval(source);
```

Note: this is a script in the **MiniCalc** language of this lesson, not JavaScript.

### Choose `eval(Reader)` when

- The script resides in a file, stream, or existing `StringReader`.
- You want to read from a file with an **explicitly specified** charset.
- You want to pass source as a `Reader` per the caller's API, without forcing the caller to call `Files.readString` first.
- You can manage the resource at the boundary using `try-with-resources`.

Example:

```java
Path path = Path.of("rules.calc");
try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    Object result = engine.eval(reader);
    System.out.println(result);
}
```

This is an **illustrative snippet** requiring imports `java.nio.file.*`, `java.nio.charset.StandardCharsets`, `java.io.Reader` and handling `IOException`, `ScriptException`; it only runs when the file and a suitable engine exist.

**Important rule about Reader:** a `Reader` object provided by the caller should be proactively closed by the caller code using `try-with-resources`. Do not assume every engine will close the `Reader` for you, and do not reuse a `Reader` that has already been consumed if it does not support reset. The MiniCalc example in this lesson intentionally **does not** close the caller-provided `Reader`.

### 3.1. Charset belongs to the Reader creation layer

A `Reader` is already a stream of **characters**, not bytes. When you create a `Reader` from a file, you must choose the charset at the bytes → chars conversion step:

```java
Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

The `engine.eval(reader)` call **does not take a charset**. If a UTF-8 file is read with the wrong charset, some characters may turn into corrupted text, causing the engine to report very hard-to-find syntax/identifier issues.

In code using real files, you should specify UTF-8 (or an agreed-upon charset), avoiding `new FileReader(path)` without specifying an encoding if portability matters.

### 3.2. The filename in `ScriptException` is not automatically taken from Reader

A `Reader` has no general contract containing a filename. `Files.newBufferedReader(path)` provides characters; the engine does not necessarily know the application's `path` variable. If the engine supports filename metadata, you can set:

```java
engine.put(ScriptEngine.FILENAME, "rules.calc");
```

The constant `ScriptEngine.FILENAME` is the name of a standard property, but **using the property to populate `ScriptException` depends on the implementation**. Do not assume every engine will automatically report the exact filename from `FILENAME`, because JSR 223 does not require every parser to provide exact line/column numbers. MiniCalc below deliberately reads `FILENAME` and attaches it to the exception for illustration.

## 4. Return value: `Object` can be `null`

All `eval` overloads return `Object`. The actual result depends on **the language and the engine**:

- A numeric result may be mapped by the engine to `Integer`, `Long`, `Double`, `BigDecimal`, or another wrapper/class.
- A script may return `String`, `Boolean`, list/map, an engine-specific object, or a Java proxy.
- A script with no clear final value may return `null`.
- A lookup of a non-existent variable may also return `null`, depending on the DSL/provider (or throw `ScriptException` if the language defines an undefined variable error).

Do not cast blindly:

```java
// Illustrative snippet used when the engine returns a Number:
Object result = engine.eval("add 2 5");
if (result instanceof Number number) {
    int value = number.intValue();
    System.out.println(value);
} else {
    throw new IllegalStateException("Script did not return a number");
}
```

When the result is `null`, `(String) null` does not throw an exception, but calling an instance method on it can cause a `NullPointerException`. You need to distinguish **a script validly returning null** from **a missing engine (null reference)**.

### 4.1. Do not accumulate unintended state

The same `ScriptEngine` can retain bindings or state across calls. If you call:

```java
engine.put("base", 10);
Object first = engine.eval("get base");
Object second = engine.eval("get base");
```

the same default `ENGINE_SCOPE` will be available for both calls in **MiniCalc**. With a real provider, a script might create variables, mutate global objects, or retain engine-specific state. Do not assume `eval(String)` is always a pure function.

## 5. `Bindings`, `ScriptContext`, and scopes

`Bindings` is a key/value map. With `ScriptContext`, there are two standard scopes:

1. `ScriptContext.ENGINE_SCOPE` — bindings specific to the engine/context being used for execution. `engine.put(key,value)` typically updates the `ENGINE_SCOPE` of the default context.
2. `ScriptContext.GLOBAL_SCOPE` — a shared set of bindings if configured, for example from `ScriptEngineManager`. During resolution by context, `ENGINE_SCOPE` typically takes precedence over `GLOBAL_SCOPE`.

Choose the overload to avoid unintended state changes:

```java
// Illustrative code with MiniCalc:
engine.put("base", 10);
System.out.println(engine.eval("get base"));  // 10

Bindings once = engine.createBindings();
once.put("base", 77);
System.out.println(engine.eval("get base", once)); // 77
System.out.println(engine.eval("get base"));       // 10
```

The value `base=77` is only used as `ENGINE_SCOPE` for **the `eval` call with the `Bindings` parameter** in implementations following the `AbstractScriptEngine` contract. It does not automatically replace the engine's default `ENGINE_SCOPE`.

**Limitation:** per-call `Bindings` helps control variables partially, but it is **not** a process sandbox, and does not guarantee every implementation is completely free of side effects/internal state. A script can manipulate provided Java objects, call permitted APIs, or affect other places if the provider/permissions allow.

### 5.1. `ScriptContext` when more information is needed

Sometimes you need to pass `ENGINE_SCOPE`, `GLOBAL_SCOPE`, filename metadata, an error writer, or a standard writer for a specific request:

```java
SimpleScriptContext ctx = new SimpleScriptContext();
Bindings bindings = new SimpleBindings();
bindings.put("base", 99);
ctx.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
ctx.setAttribute(ScriptEngine.FILENAME, "request-42.calc",
        ScriptContext.ENGINE_SCOPE);
Object result = engine.eval("get base", ctx);
```

This is an **illustrative snippet** with imports from `javax.script`; MiniCalc understands `get base`, while another provider needs valid script in its own language.

If you use `engine.eval(script,ctx)`, that custom context applies **to that call**. Do not confuse this with `engine.setContext(ctx)`, which replaces the engine's default context and can affect subsequent calls.

### 5.2. Scope does not replace permission checks

Having a variable named `role` in `Bindings` does not guarantee the script only has that role's permissions. If you provide an untrusted script with a Java object that has file/network/database capabilities, the script can use those capabilities depending on the engine. You must design a separate trust boundary.

## 6. What is `ScriptException`?

`javax.script.ScriptException` is a checked exception used by the Scripting API when an error occurs while interpreting/evaluating a script. It extends `Exception`, so code calling `eval` must either:

- `try/catch (ScriptException e)`, or
- declare `throws ScriptException` (or an appropriate supertype) and propagate it to the caller.

Available diagnostic information:

| Method | Meaning | When information is unavailable |
| --- | --- | --- |
| `getMessage()` | Error description, may already include filename/line/column | Returns exception text, engine-dependent |
| `getFileName()` | Name of the script source related to the error | May return `null` |
| `getLineNumber()` | Line where the error occurred | `-1` if unknown |
| `getColumnNumber()` | Column where the error occurred | `-1` if unknown |
| `getCause()` | Underlying cause exception if any | May return `null` |

Safe handling example:

```java
try {
    Object result = engine.eval(source);
    useResult(result);
} catch (ScriptException e) {
    String file = e.getFileName() != null
            ? e.getFileName() : "<unknown-source>";
    String line = e.getLineNumber() >= 0
            ? Integer.toString(e.getLineNumber()) : "?";
    String column = e.getColumnNumber() >= 0
            ? Integer.toString(e.getColumnNumber()) : "?";

    System.err.println(file + ":" + line + ":" + column);
    System.err.println(e.getMessage());

    Throwable cause = e.getCause();
    if (cause != null) {
        System.err.println("Cause: " + cause.getClass().getName());
    }
}
```

This is an **illustrative snippet**, requiring `engine`, `source`, a `useResult` method, and corresponding imports; it is not a standalone program.

### 6.1. Do not automatically treat every error as `ScriptException`

`ScriptException` is the API's standard exception for script errors and checked exceptions that the engine implementation needs to wrap. However, other errors can still occur:

- `engine == null` followed by calling `eval` → `NullPointerException` because **no provider was found**.
- `Files.newBufferedReader(...)` can throw `IOException` **before** calling `eval` due to a missing file or insufficient read permissions.
- Java code using a result with the wrong type → `ClassCastException` **in the caller**, not a script parse error.
- The engine or Java objects called by the script can throw unchecked exceptions/errors depending on the provider and trust boundary.
- `ScriptException` can wrap an `IOException` caused by a failing `Reader` **while the engine is reading** the source, or wrap another checked parser/interpreter exception.

If you want to classify errors for users/APIs, separate **file I/O**, **engine discovery**, **script execution**, and **post-processing** instead of catching a generic `Exception` and returning `"syntax error"`.

### 6.2. `getMessage()` may already include location

The constructor `new ScriptException(message,filename,line,column)` can generate text containing both the filename and coordinates. If you log `getMessage()` and also concatenate the location verbatim, the log may duplicate information. This is not critical, but you should know it when designing structured error responses.

For structured diagnostics, prefer the individual getters and pass the cause chain to the logger. Do not parse `getMessage()` to extract line/column when getters are already available.

## 7. Standalone runnable Java 17+ program: a teaching ScriptEngine

To have an example that is **reproducible without installing a JavaScript provider**, we create a tiny engine based on `AbstractScriptEngine`. It understands exactly **two commands of a custom-defined DSL**:

- `add A B`: reads two integers, adds them, and returns an `Integer`.
- `get key`: reads a variable from `ScriptContext` and returns the object or `null`.

The engine reads line by line; the result of an `eval` call is the result of **the last non-blank line**. If a token is not a number, it creates a `ScriptException` with filename/line/column and attaches `NumberFormatException` as the cause. If the `Reader` source throws `IOException` while reading, the engine wraps it in `ScriptException`.

**Scope warning:** `MiniCalc` **is not JavaScript**, is not a standard provider bundled with the JDK, and the example creates the engine **directly via `new MiniCalcEngine()`**. `MiniCalcFactory` here helps the class fully demonstrate `getFactory()`; it **does not self-register** into `ScriptEngineManager` via a service descriptor. Do not use this toy language as a production parser or security sandbox.

### 7.1. File `ScriptEvalDemo.java`

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public class ScriptEvalDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new MiniCalcEngine();
        engine.put(ScriptEngine.FILENAME, "rules.calc");
        engine.put("base", 10);

        System.out.println("String: " + engine.eval("add 2 5"));
        System.out.println("Reader: " + engine.eval(
                new StringReader("add 1 2\nadd 6 4\n")));
        System.out.println("binding: " + engine.eval("get base"));
        System.out.println("missing: " + engine.eval("get missing"));

        Bindings oneCall = new SimpleBindings(Map.of("base", 77));
        System.out.println("one-call binding: " + engine.eval("get base", oneCall));
        System.out.println("default binding: " + engine.eval("get base"));

        try {
            engine.eval(new StringReader("add 1 2\nadd 4 nope\n"));
        } catch (ScriptException e) {
            System.out.println("script failure: "
                    + e.getFileName() + ":" + e.getLineNumber()
                    + ":" + e.getColumnNumber());
            System.out.println("script cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        Path temporary = Files.createTempFile("minicalc-", ".calc");
        try {
            Files.writeString(temporary, "add 10 20\n", StandardCharsets.UTF_8);
            try (Reader fileReader =
                    Files.newBufferedReader(temporary, StandardCharsets.UTF_8)) {
                System.out.println("UTF-8 file: " + engine.eval(fileReader));
            }
        } finally {
            Files.deleteIfExists(temporary);
        }

        Reader broken = new Reader() {
            @Override
            public int read(char[] buffer, int offset, int length)
                    throws IOException {
                throw new IOException("read failed");
            }
            @Override
            public void close() {}
        };

        try (broken) {
            engine.eval(broken);
        } catch (ScriptException e) {
            System.out.println("Reader I/O cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        System.out.println("factory: " + engine.getFactory().getEngineName());
    }

    // A deliberately tiny teaching language: "add a b" or "get key".
    // This is NOT JavaScript and is NOT registered as a JSR-223 provider.
    static final class MiniCalcEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory = new MiniCalcFactory();

        @Override
        public Object eval(String source, ScriptContext context)
                throws ScriptException {
            Objects.requireNonNull(source, "source");
            return eval(new StringReader(source), context);
        }

        @Override
        public Object eval(Reader input, ScriptContext context)
                throws ScriptException {
            Objects.requireNonNull(input, "input");
            Objects.requireNonNull(context, "context");
            BufferedReader reader = new BufferedReader(input);
            Object result = null;
            int number = 0;

            try {
                String line;
                while ((line = reader.readLine()) != null) {
                    number++;
                    if (!line.isBlank()) {
                        result = execute(line, number, context);
                    }
                }
            } catch (IOException error) {
                throw new ScriptException(error);
            }
            return result;
        }

        private Object execute(String line, int number, ScriptContext context)
                throws ScriptException {
            String[] words = line.trim().split("\\s+");
            if (words.length == 2 && words[0].equals("get")) {
                return context.getAttribute(words[1]);
            }
            if (words.length == 3 && words[0].equals("add")) {
                try {
                    return Integer.parseInt(words[1])
                            + Integer.parseInt(words[2]);
                } catch (NumberFormatException error) {
                    int column = line.indexOf(words[2]) + 1;
                    ScriptException wrapped = failure(
                            "not an integer: " + words[2], context, number, column);
                    wrapped.initCause(error);
                    throw wrapped;
                }
            }
            throw failure("unknown command or wrong arity", context, number, 1);
        }

        private ScriptException failure(String message, ScriptContext context,
                int line, int column) {
            Object name = context.getAttribute(ScriptEngine.FILENAME);
            String filename = name == null ? "<eval>" : name.toString();
            return new ScriptException(message, filename, line, column);
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

    static final class MiniCalcFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniCalc"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("calc"); }
        @Override public List<String> getMimeTypes() {
            return List.of("text/x-minicalc");
        }
        @Override public List<String> getNames() { return List.of("minicalc"); }
        @Override public String getLanguageName() { return "MiniCalc"; }
        @Override public String getLanguageVersion() { return "1.0"; }
        @Override public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.NAME -> "minicalc";
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                default -> null;
            };
        }
        @Override public String getMethodCallSyntax(
                String object, String method, String... args) {
            return null; // Not supported by this two-command language.
        }
        @Override public String getOutputStatement(String value) {
            return null; // No print statement in MiniCalc.
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniCalcEngine();
        }
    }
}
```

### 7.2. Compile and run commands

Create a file with the exact name `ScriptEvalDemo.java`, then run:

```bash
javac --release 17 ScriptEvalDemo.java
java ScriptEvalDemo
```

The program does not depend on Nashorn, GraalJS, Groovy, or any external library; it only uses **JDK 17+**.

**Stdout verified by actual compilation and execution:**

```text
String: 7
Reader: 10
binding: 10
missing: null
one-call binding: 77
default binding: 10
script failure: rules.calc:2:7
script cause: NumberFormatException
UTF-8 file: 30
Reader I/O cause: IOException
factory: MiniCalc
```

### 7.3. Why is the `String` result 7 and the `Reader` result 10?

- `engine.eval("add 2 5")` calls the String overload, and then `MiniCalcEngine.eval(String, ScriptContext)` converts the string into a `StringReader`.
- `MiniCalcEngine.eval(Reader, ScriptContext)` reads lines using `BufferedReader.readLine()` and interprets the DSL.
- `"add 2 5"` returns `Integer 7`.
- The Reader contains two lines: `"add 1 2"` returns 3 first, `"add 6 4"` returns 10 afterward; the engine deliberately keeps **the last line's result**, so the entire `eval(Reader)` returns 10.

**Do not generalize** the last-line result behavior to JavaScript or every JSR 223 provider. These are semantics explicitly written in `MiniCalcEngine`.

### 7.4. Engine-level and one-call `Bindings`

`engine.put("base",10)` writes a value to the default `ENGINE_SCOPE`. `eval("get base")` uses the default context and returns 10. `SimpleBindings(Map.of("base",77))` is passed to `eval("get base",oneCall)`, so that call returns 77. The next call using the default context reads 10 again.

`eval("get missing")` calls `ScriptContext.getAttribute("missing")`, and the implementation in the demo returns `null` because the key is absent. That **does not** prove every scripting language allows accessing an undefined identifier without error.

### 7.5. Location and cause of `ScriptException`

The call:

```java
engine.eval(new StringReader("add 1 2\nadd 4 nope\n"));
```

has an error on **line 2**. In `"add 4 nope"`, the token `nope` starts at **column 7** (1-based). The toy parser intentionally constructs:

```java
new ScriptException("not an integer: nope", "rules.calc", 2, 7);
```

and then calls `initCause(numberFormatException)`. Because `engine.put(ScriptEngine.FILENAME,"rules.calc")` already set the metadata in the context, the output shows `rules.calc:2:7`; the cause is `NumberFormatException`.

**Limitation of the demo parser:** computing the column via `line.indexOf(words[2])+1` is only sufficient for the short commands in the example; a production parser must track exact token offsets, including when tokens repeat, when there is complex whitespace, or with Unicode code points. The demo aims to explain the JSR 223 exception API, not to build a complete lexer/parser.

### 7.6. Why is an I/O failure wrapped into `ScriptException`?

`Reader broken` intentionally throws `IOException("read failed")` when the engine calls `BufferedReader.readLine()`. `MiniCalcEngine` catches `IOException` and throws `new ScriptException(error)`. Therefore, the caller of `engine.eval(broken)` catches `ScriptException`, and `getCause()` is `IOException`.

This differs from `Files.newBufferedReader(...)` throwing `IOException` when **opening the file** on the application side. The two errors may be caught at different places:

```text
Files.newBufferedReader(path)
    |
    +-- IOException when opening file  --> catch IOException in caller
    |
    +-- Reader opened
            |
            v
       engine.eval(reader)
            |
            +-- checked read/parse failures per implementation
            |      --> may be wrapped in ScriptException
            |
            +-- script result Object
```

If a real engine handles `IOException` differently, use the provider documentation and cause chain to classify it. JSR 223 expects engines to wrap checked exceptions from the interpreter into `ScriptException`, but application code still needs to handle errors outside the `eval` phase separately.

### 7.7. Who closes the Reader?

`MiniCalcEngine.eval(Reader,ScriptContext)` creates a `BufferedReader` wrapping the input `Reader` but **does not** call `close()`, because ownership of the source belongs to the caller. For file sources, the caller uses:

```java
try (Reader fileReader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    engine.eval(fileReader);
}
```

The `Reader` is closed even if `eval` throws `ScriptException`. A `StringReader` may not involve external resources, but using `try-with-resources` still clarifies management when swapping in a `FileReader`/stream reader.

Do not close the `Reader` before calling `eval`, and do not reuse a `Reader` that has reached EOF expecting the engine to re-read the source automatically. To run again, **create a new Reader** or use a saved `String` source.

## 8. Standalone example 2 — safely discovering a JavaScript provider

This is a real program using only the JDK. It does not require a JavaScript engine to **compile or start**. If no provider is present, it reports the missing provider and exits cleanly instead of throwing `NullPointerException`.

Create the file **`ScriptEngineDiscoveryDemo.java`**:

```java
import java.io.Reader;
import java.io.StringReader;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class ScriptEngineDiscoveryDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");

        if (engine == null) {
            System.out.println("JavaScript engine: not installed");
            System.out.println("Install and register a compatible JSR-223 provider.");
            return;
        }

        System.out.println("engine name: "
                + engine.getFactory().getEngineName());
        try {
            Object fromString = engine.eval("1 + 2");
            System.out.println("String result: " + fromString);
            try (Reader source = new StringReader("2 + 3")) {
                Object fromReader = engine.eval(source);
                System.out.println("Reader result: " + fromReader);
            }
        } catch (ScriptException error) {
            System.err.println("Script error: " + error.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac --release 17 ScriptEngineDiscoveryDemo.java
java ScriptEngineDiscoveryDemo
```

**Observed output in a test JDK environment without a JavaScript provider installed:**

```text
JavaScript engine: not installed
Install and register a compatible JSR-223 provider.
```

If the environment **has a compatible provider**, the program enters the other branch: printing the engine name, running `1 + 2` from a `String`, then `2 + 3` from a `StringReader`. **The exact result/numeric type and engine name depend on the provider**, so do not assume a fixed stdout across all engines. The program also catches `ScriptException` from execution, instead of assuming the expression is always valid on any engine named JavaScript.

### 8.1. Why can `getEngineByName` return `null`?

`ScriptEngineManager` uses `ScriptEngineFactory` implementations discovered via the service-provider mechanism. When no factory advertises the requested name or the provider is not loaded properly, `getEngineByName(...)` returns `null`. That differs from an engine being present while the script has a syntax error.

To debug discovery, you can print the list of factories:

```java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName()
            + ": " + factory.getNames());
}
```

This is an illustrative snippet with imports `ScriptEngineManager` and `ScriptEngineFactory`; the list **depends on the environment and dependencies**. Do not assume JDK 17 is guaranteed to have a specific single factory or provider name.

### 8.2. Installing another engine and compatibility requirements

JSR 223 does not define a standard JavaScript interpreter bundled with every JDK. If an application truly needs JavaScript on Java 17+, choose a provider with clear documentation on:

- Compatibility with the JDK version and module system.
- The actual language and ECMAScript version supported.
- How to place dependencies on the classpath/module path and service registration.
- Host-access policy, sandboxing/isolation, and script permissions.
- `ScriptException`: how location, cause, error writers, and engine-specific types are reported.
- Concurrency policy and whether an engine instance can be used across multiple threads.

Do not simply replace `"JavaScript"` with `"nashorn"` and expect JDK 17 to restore the removed engine. If you choose a library providing Nashorn or another engine, it is an **external dependency outside the JDK** that requires separate testing and security management.

## 9. Standalone example 3 — default metadata of `ScriptException`

Because `ScriptException` may not have a filename/line/column, you must write code that does not assume location always exists.

Create the file **`ScriptExceptionMetadataDemo.java`**:

```java
import javax.script.ScriptException;

public class ScriptExceptionMetadataDemo {
    public static void main(String[] args) {
        ScriptException basic = new ScriptException("bad syntax");
        System.out.println("unknown file: " + basic.getFileName());
        System.out.println("unknown line: " + basic.getLineNumber());
        System.out.println("unknown column: " + basic.getColumnNumber());

        ScriptException positioned =
                new ScriptException("unexpected symbol", "rules.dsl", 4, 12);
        System.out.println("location: " + positioned.getFileName()
                + ":" + positioned.getLineNumber()
                + ":" + positioned.getColumnNumber());

        ScriptException wrapped =
                new ScriptException(new IllegalArgumentException("bad token"));
        System.out.println("wrapped cause: "
                + wrapped.getCause().getClass().getSimpleName());
        System.out.println("wrapped line: " + wrapped.getLineNumber());
    }
}
```

Compile and run:

```bash
javac --release 17 ScriptExceptionMetadataDemo.java
java ScriptExceptionMetadataDemo
```

**Verified stdout:**

```text
unknown file: null
unknown line: -1
unknown column: -1
location: rules.dsl:4:12
wrapped cause: IllegalArgumentException
wrapped line: -1
```

Analysis:

- The constructor `new ScriptException("bad syntax")` has no location metadata, so `getFileName() == null`, `getLineNumber() == -1`, and `getColumnNumber() == -1`.
- The constructor with `message,filename,line,column` stores the provided location.
- The constructor with `Exception` sets that exception as the cause, but **does not automatically infer** line/column from the cause if the cause does not provide them per the contract.
- Do not write `e.getCause().getMessage()` without a null check in general `ScriptException` handling code, because a constructor taking only a message may have no cause.

## 10. Complete error-handling workflow by boundary

An application that reads a script file, obtains an engine, and evaluates has **at least three places** where it can fail:

```text
1. Engine discovery
   getEngineByName(...)
       |
       +-- null: missing provider / incorrect engine name

2. File open/read source
   Files.newBufferedReader(path, charset)
       |
       +-- IOException: path does not exist, permission, I/O...
       |
       +-- Reader obtained
              |
              v
3. Evaluation
   engine.eval(reader)
       |
       +-- ScriptException: syntax/runtime/checked interpreter errors
       |
       +-- Object result: parse and check type in Java caller
```

An **application logic skeleton** might look like this:

```java
// Java pseudocode that can be integrated after declaring imports/engineName/path:
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName(engineName);
if (engine == null) {
    throw new IllegalStateException(
            "Missing JSR-223 engine provider: " + engineName);
}

engine.put(ScriptEngine.FILENAME, path.toString());

try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    Object raw = engine.eval(reader);
    // Validate result according to the script contract.
} catch (ScriptException e) {
    // Log engine name, safe script ID, optional filename/line/column.
    // Preserve e as the cause when propagating.
    throw new IllegalStateException("Script evaluation failed", e);
} catch (IOException e) {
    throw new IllegalStateException("Script file I/O failed", e);
}
```

Not a standalone program: requires `engineName`, `path`, imports, error policies, and appropriate result-handling choices.

In code with production logging, avoid logging the entire script and input variables if they contain secrets. You can log a **script ID, version, hash**, and location metadata, along with a request correlation ID.

### 10.1. Choosing useful error messages

A good message for users/developers might include:

```text
Rule evaluation failed
  engine: <provider name>
  source: rule-42.dsl
  location: 7:13   (if available)
  category: script-evaluation
  cause: <script/parser cause, if available>
```

Do not fabricate a line/column if the engine returns `-1`; display "unknown". Do not extrapolate a filename from the `Reader` content if the caller does not have a path. When the engine returns an error without metadata, keep the message and stack/cause, and do not try to guess.

### 10.2. Java file I/O errors differ from script runtime errors

Suppose `Path.of("missing.dsl")` does not exist. `Files.newBufferedReader` can throw `NoSuchFileException` (a subtype of `IOException`) before the engine receives the `Reader`.

Conversely, a `Reader` that is already open but fails midway can cause the engine to throw `ScriptException` wrapping `IOException`. When catching `ScriptException`, inspect the cause chain to classify reader I/O failures. Do not treat every `ScriptException` as a syntax error.

### 10.3. Script execution causing side effects and then throwing ScriptException

A script may have already modified state before an error occurs:

```text
step 1: insert into database
step 2: call an HTTP endpoint
step 3: syntax/runtime failure -> ScriptException
```

JSR 223 **does not** provide default transaction rollback. If a script runs in a system with side effects, provide transaction boundaries, idempotency, sandboxing, or isolation according to business requirements, rather than relying on catching `ScriptException` to "undo" previous steps.

## 11. Reading filename and line numbers properly

For a long script, errors need to be correlated back to the source:

```java
catch (ScriptException e) {
    String filename = e.getFileName() != null
            ? e.getFileName() : "<inline-script>";
    int line = e.getLineNumber();
    int column = e.getColumnNumber();

    String location = filename
            + ":" + (line >= 0 ? line : "?")
            + ":" + (column >= 0 ? column : "?");
    System.err.println(location);
}
```

This **illustrative snippet** must be inside a `try` block with a statement that can throw `ScriptException`.

Different engines may count line/column differently when handling:

- Line breaks `\n` or `\r\n`.
- A source `String` already containing newlines, or a `Reader` reading an actual file.
- Non-BMP Unicode characters, tabs, and code points.
- Scripts concatenated from multiple segments or preprocessed before parsing.

**Do not** slice/concatenate scripts and expect reported error locations to always match the original file. If there is transpilation/template expansion, you need source mapping provided by the framework. `ScriptException`'s line/column is information provided by the engine, which may correspond to the **transformed source**, not necessarily the user's original document.

### 11.1. FILENAME is metadata, not file-reading permission

`engine.put(ScriptEngine.FILENAME,"rules.calc")` only sets an attribute. It does not make the engine automatically read the file `rules.calc` when calling `eval("add 2 5")`. The source is still the `String` passed directly.

Similarly, `engine.eval(reader)` will read from **the passed Reader**, not automatically switch to another file just because `FILENAME` has a value.

## 12. State, engine reuse, and concurrency

An engine can be called multiple times, but you must understand the provider's state and thread-safety model.

### 12.1. Default context can retain data across eval calls

`engine.put("x", value)` updates the engine's bindings. A script can read or modify these bindings depending on the language. If you use the same instance for multiple untrusted requests, data leakage easily occurs when request B sees variables set by request A.

To avoid state leakage:

- Use a separate `Bindings`/`ScriptContext` for each evaluation when engine semantics support it properly.
- Check the provider documentation regarding global objects, shared caches, and scope leakage.
- Avoid providing Java objects that have access to data outside the request's scope.
- When true isolation is needed, use separate engine/language contexts or **process isolation** according to your threat model, rather than just creating a new `SimpleBindings`.

### 12.2. Do not assume ScriptEngine is thread-safe

JSR 223 providers have varying levels of threading support. `ScriptEngineFactory.getParameter("THREADING")` in some providers can indicate the concurrency model per JSR 223 conventions, but you should not treat every engine as thread-safe or singleton-safe.

Without an explicit guarantee:

- Do not share **a single ScriptEngine instance** to run multiple scripts concurrently across multiple threads without control.
- Consider instance-per-request, a pool with ownership rules, or synchronization/serialization when appropriate.
- Do not let multiple threads mutate the default `Bindings`/`ScriptContext` simultaneously and rely on stable results.
- Separate source caching/precompilation from evaluation state if the provider supports `Compilable`.

### 12.3. `Compilable` is not present in every engine

Some engines also implement `javax.script.Compilable`:

```java
// Illustrative snippet; not every engine is Compilable.
if (engine instanceof javax.script.Compilable compilable) {
    javax.script.CompiledScript compiled = compilable.compile(scriptSource);
    Object result = compiled.eval();
}
```

This is an *optional* optimization for scripts evaluated repeatedly. It does not change the basic `eval(String/Reader)` API; and a compiled script itself also has its own state/concurrency semantics, so read the provider documentation.

## 13. Do not treat `eval` as a security sandbox

This is a critical point when "embedding scripts" into an application:

- `eval` can execute code with whatever permissions **the engine and host integration** allow. If a script can access Java objects with I/O, network, or process permissions, script code can cause severe side effects.
- `Bindings` is a way to pass names/values into a script, **not** an access-control layer.
- `ScriptException` helps report errors; it **does not** limit time, memory, loop counts, or permissions.
- Cutting off execution time via `Thread.interrupt()` is not a guaranteed way to stop every engine/provider, especially if the interpreter/native code does not cooperate.
- Untrusted script sources require **process isolation/containers, resource limits, OS permissions, and host-access policies** suited to the threat model; not just `try/catch`.

Even a completely valid script can run an infinite loop or consume excessive memory. This is **not** a syntax error `ScriptException` in the usual sense. If the task is to run user-supplied scripts, design timeout/cancellation/process-kill mechanisms at a trusted boundary.

### 13.1. Do not insert user input directly into an uncontrolled template

When a script contains untrusted input, avoid string concatenation like:

```java
// Risky example: do not insert user data directly into script source.
String script = "calculate('" + userInput + "')";
```

A string containing quotes or scripting language syntax can alter program structure or inject code. Prefer passing data via `Bindings` or argument-passing APIs supported by the provider, with validation and host access restrictions. Binding alone does not eliminate all risks, but separating code/source from data is a good foundation.

## 14. Common mistakes when using `eval(String/Reader)`

### 14.1. Not checking whether the engine exists

Wrong:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("JavaScript");
engine.eval("1 + 2"); // Can throw NullPointerException
```

Right: check `engine != null` and provide a clear missing-provider message.

### 14.2. Assuming Java 17 always has Nashorn installed

Wrong. JEP 372 removed Nashorn starting in JDK 15. `java.scripting` still exists; `ScriptEngineManager` still works, but specific engines depend on dependencies.

### 14.3. Thinking `eval(Reader)` will automatically close the Reader

Do not rely on that. The caller creating the `Reader` must manage the resource, usually with `try-with-resources`; the MiniCalc demo itself **does not** close the input `Reader`. When the reader comes from a file, forgetting to close it can leak file descriptors.

### 14.4. Thinking Reader always contains the filename

Wrong. `Reader` is a character source; filename is separate metadata. Set `ScriptEngine.FILENAME` if the provider conventionally supports it, while also keeping the script ID/path on the application side for error reporting.

### 14.5. Confusing `IOException` when opening a file with `ScriptException`

`Files.newBufferedReader` throws `IOException` on the Java caller side. An engine reading a `Reader` may wrap `IOException` into `ScriptException` while evaluation is running. Distinguish the boundary when catching/logging.

### 14.6. Thinking `ScriptException` always has a location

Wrong. `getFileName()` can be null; line/column can be `-1`. Use a sensible fallback instead of printing `-1` as if it were an actual script line.

### 14.7. Thinking `getCause()` is guaranteed to be non-null

Wrong. `new ScriptException("bad syntax")` may have no cause. Check for null before dereferencing.

### 14.8. Casting `(Integer) engine.eval(...)` regardless of provider

Wrong. `eval` returns `Object`; the engine may return `Double`, `BigDecimal`, another object, or null. Check the type or use conversion APIs described by the provider.

### 14.9. Confusing `eval(String,Bindings)` with `engine.setBindings`

The overload with `Bindings` supplies scope for **the single call**, not as a default replacement for the engine's default context. `setBindings` or `setContext` has longer-lasting effects and needs control when sharing an engine.

### 14.10. Sharing one ScriptEngine across multiple threads without checking

There is no universal thread-safety guarantee across all providers. Check the factory/provider docs and consider one context/engine instance per request as needed.

### 14.11. Thinking ScriptException automatically rolls back side effects

Wrong. A script may have already modified a database, Java objects, files, or external APIs before the error occurred. The exception does not provide automatic transactions.

### 14.12. Using `eval` as a sandbox for untrusted scripts

Dangerous. There is no default memory/time/host-access isolation in the `ScriptEngine` interface; an appropriate boundary must be designed.

### 14.13. Thinking `Reader` is always faster than String

There is no guarantee. A provider may read the entire `Reader` into a `String`/AST; performance and memory depend on implementation and workload.

### 14.14. Confusing script errors with external Java checked/unchecked exceptions

An `IllegalArgumentException` when the application builds an invalid parameter, a `ClassCastException` after `eval` succeeds, or an `IOException` opening a file are not inherently a script's `ScriptException`.

## 15. Quick troubleshooting table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `getEngineByName("JavaScript") == null` | No registered provider, wrong alias, missing classpath/module path | Check `getEngineFactories()`, dependencies, and provider docs |
| `NullPointerException` at `engine.eval` | Engine reference is null | Validate discovery before `eval` |
| `ScriptException` with line/column | Engine parser/interpreter detected an error | Log location, script ID, message, and cause |
| `ScriptException` with line=-1, column=-1 | Engine does not know/provide location | Do not guess location; preserve message/cause |
| `ScriptException` wrapping `IOException` | Reading `Reader` failed during `eval` | Inspect underlying stream/source and cause |
| `NoSuchFileException` before `eval` | Wrong path/file does not exist | Handle file-open error separately |
| Script runs but result is `null` | Script has no return value or missing identifier depending on language | Verify language contract, do not cast |
| `ClassCastException` after `eval` | Caller assumed the wrong Java result type | Check `Object`/`instanceof` or provider conversions |
| Next `eval` sees previous call's values | Default `Bindings` or engine global state retained | Create per-call `Bindings`/context and check isolation semantics |
| Script charset/Unicode error | `Reader` created from file with wrong encoding | Use `StandardCharsets.UTF_8` or actual source charset |
| Concurrent scripts give erratic results | Sharing non-thread-safe engine/context | Isolate instances, synchronize, or use documented threading model |
| Script hangs indefinitely | No timeout/sandbox in JSR 223 API | Set resource limits/process isolation; do not just catch `ScriptException` |
| Log duplicates filename/line | `getMessage()` already contains metadata, concatenated again | Use separate structured fields; avoid duplication |

## 16. Pre-production checklist

**Step 1 — Lock down the provider.** Choose the language, version, and implementation. Verify `getEngineByName(...)` returns non-null on the actual JDK/runtime image, container, and build artifact. Avoid relying on a provider only present on one developer's machine.

**Step 2 — Lock down the source boundary.** Is the source a `String`, `Reader`, UTF-8 file, database, or request body? Are there clear size limits and encoding? Is the `Reader` closed properly when evaluation finishes?

**Step 3 — Lock down the execution contract.** What type should the script return? Which bindings may it read/write? Which side effects are allowed? Which errors are user-facing vs internal?

**Step 4 — Lock down ScriptContext.** Do variables belong in `ENGINE_SCOPE` or `GLOBAL_SCOPE`? Is a per-request context needed? Is filename metadata or writer/output capture needed?

**Step 5 — Lock down error mapping.** If the engine provider is missing, report a config error. If script parse/eval fails, report `ScriptException` with location if available. If opening the `Reader` fails, report an I/O error. If the result type is wrong, report a contract validation error.

**Step 6 — Lock down concurrency/security.** Is `ScriptEngine` thread-safe? Are there untrusted scripts? Are there timeout/memory/CPU limits and a way to cancel execution when needed?

**Step 7 — Test across environments.** Run on real JDK 17, actual classpath/module path, and packaged providers. Verify service discovery works inside packaged JARs or runtime images.

### 16.1. What should a minimal test suite include?

- `eval(String)` runs valid scripts and returns the expected result.
- `eval(Reader)` runs the same script with a `Reader`, including newlines, Unicode, and file encoding.
- Invalid scripts throw `ScriptException`; verify location/cause when supported by the provider.
- A `Reader` failing midway is reported and resources are cleaned up properly.
- Missing provider is reported **before calling `eval`**.
- Per-call bindings do not leak data to the default context in the corresponding scenario.
- Scripts returning null or wrong result types are handled explicitly.
- Multiple concurrent requests do not indiscriminately share context.
- Oversized script inputs or hanging scripts are bounded per the threat model.

## 17. Self-check questions

**Question 1.** What is the fundamental difference between `eval(String)` and `eval(Reader)`?

**Answer:** One overload takes script source already in memory as a `String`, while the other takes a character source via a `Reader`. Language semantics and script results are determined by the engine; `Reader` does not automatically convey filename or charset.

**Question 2.** On JDK 17 without an added provider, is `getEngineByName("JavaScript")` guaranteed to return an engine?

**Answer:** No. Nashorn was removed starting in JDK 15; `getEngineByName` can return `null`. You must validate and install an engine provider when the application actually needs it.

**Question 3.** Does `ScriptEngine.eval` execute Java source directly or the engine's script source?

**Answer:** Script source in the language implemented by the engine. The Scripting API is not a dynamic `javac` to compile arbitrary Java code.

**Question 4.** Does `engine.eval("get base",oneCallBindings)` permanently replace the default engine bindings?

**Answer:** No, per the overload contract: `Bindings` is used as `ENGINE_SCOPE` for that execution. However, a provider may have other shared side effects, so per-call `Bindings` is not absolute isolation.

**Question 5.** If a source `Reader` is created with `Files.newBufferedReader(path,UTF_8)`, does the engine automatically get the filename from `path`?

**Answer:** No, per the `Reader` contract. Set `ScriptEngine.FILENAME` if the provider supports it, and keep the path/script ID in the application for error reporting.

**Question 6.** Who closes a file `Reader` after `eval(reader)`?

**Answer:** The caller should use `try-with-resources`; do not rely on the engine closing it automatically. With `StringReader` there is no external file resource, so closing is less critical, but the pattern remains consistent.

**Question 7.** What does `ScriptException.getLineNumber()` return when the engine cannot determine the line?

**Answer:** `-1`. Similarly, column is `-1`, and filename may be `null`.

**Question 8.** Is `getCause()` always non-null?

**Answer:** No. A `ScriptException` constructed from just a message may have no cause; always null-check before reading it.

**Question 9.** A non-existent file causes `NoSuchFileException` before calling `eval`. Is this a script syntax error?

**Answer:** No. This is an `IOException` at the file-opening layer; the script engine has not started evaluating yet.

**Question 10.** A `Reader` throws `IOException` while being read, and the engine wraps it in `ScriptException`. How should you diagnose it?

**Answer:** Catch `ScriptException`, inspect `getCause()`, and check the source-reading error. Do not conclude every `ScriptException` is caused by bad syntax.

**Question 11.** Why can `Object result = engine.eval(...)` be `null`?

**Answer:** The result is defined by the language/provider; a script may produce no return value or access a missing variable according to those semantics. Check before casting/using.

**Question 12.** Can a single `ScriptEngine` be used across 100 threads at the same time?

**Answer:** Only if the provider and application design allow it. There is no universal thread-safety guarantee across all providers; read the threading contract and isolate contexts or engines if needed.

**Question 13.** Can `Bindings` be used as a sandbox to prevent scripts from accessing files/network?

**Answer:** No. `Bindings` is not a security sandbox; host-access policies and isolation depend on the provider/environment, and for untrusted scripts you should consider process isolation/resource limits.

**Question 14.** Why doesn't `ScriptException` roll back changes made by the script before the error?

**Answer:** JSR 223 only defines an evaluation error-reporting mechanism; it does not provide a transaction manager or undo side effects by default.

**Question 15.** Does an engine return `Integer` when running `1+2` on every JavaScript provider?

**Answer:** There is no such guarantee. `eval` returns `Object`, and mapping numbers from the script language to Java objects depends on the provider.

**Question 16.** Why does MiniCalc use `AbstractScriptEngine` and `getFactory()` yet not appear from `getEngineByName("minicalc")` by default?

**Answer:** Because the demo instantiates the engine directly and does not register the provider via the service mechanism or `ScriptEngineManager.registerEngineName`. Having a factory object does not mean the manager automatically discovers it.

## 18. Applied exercises

### Exercise A — compare String and StringReader

Using `MiniCalcEngine` from `ScriptEvalDemo`, evaluate `"add 11 12"` with `eval(String)` and `eval(new StringReader(...))`.

**Expected result:** both calls return `Integer 23`. You should explain that only **the source input** differs, while the parser/semantics in MiniCalc were written to handle both identically.

### Exercise B — read a file and close the Reader

Create a UTF-8 file containing:

```text
add 2 3
add 7 8
```

Open it with `Files.newBufferedReader(path,UTF_8)`, use `try-with-resources`, and call `engine.eval(reader)`.

**Expected with MiniCalc:** returns `15` because it picks the last line's result. In another engine, you must follow that engine's semantics.

### Exercise C — syntax error at line 3

Send MiniCalc source:

```text
add 1 1
add 2 2
add 3 bad
```

Set `ScriptEngine.FILENAME` to `"lesson.calc"`. Catch `ScriptException`, and print filename/line/column and cause.

**Expected result with MiniCalc:** location `lesson.calc:3:7`, cause `NumberFormatException`. Remember the difference between line/column provided by the toy parser and data reported by another provider.

### Exercise D — check engine discovery

Run `ScriptEngineDiscoveryDemo` on JDK 17 without a provider installed, then add a compatible JSR 223 provider according to its documentation and run again.

**Expected result:** previously the program took the "not installed" branch; once the provider is found, it evaluates both `String` and `Reader`. Compare `getEngineFactories()`, engine name, and Java result types to understand differences across runtime environments.

### Exercise E — separate ENGINE_SCOPE and GLOBAL_SCOPE

Create a `SimpleScriptContext`, with an `ENGINE_SCOPE` containing `base=3` and a `GLOBAL_SCOPE` containing `base=99`. Use MiniCalc `"get base"` to observe `ENGINE_SCOPE` taking precedence. Remove `base` from `ENGINE_SCOPE` and try again.

**Expected result:** when both scopes have the key, MiniCalc reads 3; after removing the key from `ENGINE_SCOPE`, it falls back to `GLOBAL_SCOPE` and reads 99 per `ScriptContext.getAttribute`.

## 19. Official documentation

- **Java SE 17 — `ScriptEngine`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html — six `eval` overloads, bindings, context, reserved keys like `FILENAME`.
- **Java SE 17 — `ScriptEngineManager`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html — service provider discovery, `getEngineByName`, manager global bindings.
- **Java SE 17 — `ScriptException`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html — constructors, filename/line/column, cause.
- **Java SE 17 — `ScriptContext`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html — `ENGINE_SCOPE`, `GLOBAL_SCOPE`, Readers/Writers.
- **Java SE 17 — `AbstractScriptEngine`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html — how `eval` overloads are implemented on top of abstract methods.
- **Java SE 17 — `ScriptEngineFactory`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html — metadata and provider factory.
- **Java SE 17 — `Bindings` and `SimpleBindings`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html ; https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleBindings.html .
- **Java SE 17 — `Files.newBufferedReader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html — Reader with charset and checked I/O.
- **JEP 372 — Remove the Nashorn JavaScript Engine:** https://openjdk.org/jeps/372 — why Nashorn is no longer bundled with JDK 15+.
- **Module `java.scripting`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/module-summary.html — foundational API of JSR 223.

**Conclusion:** `eval(String)` and `eval(Reader)` only differ in **how the script source is supplied**, while language semantics, result types, and error granularity are decided by the provider. With Java 17+, verify **the engine provider exists** before calling. When handling `ScriptException`, preserve filename/line/column if present, preserve the cause, and clearly separate I/O errors from script errors. Finally, manage `Reader`, `Bindings`, `ScriptContext`, and trust boundaries with clear rules so embedded scripting does not become a source of state, resource, or security bugs.