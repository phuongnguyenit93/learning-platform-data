# 17.5 Checking `Compilable` Capability, Reusing `CompiledScript`

When embedding a scripting language into a Java application using **JSR-223** (`javax.script`), a program often has to run the **same script code** with **multiple data sets**. If it calls `ScriptEngine.eval(source, ...)` every time, the script engine may have to re-parse/recompile the source code. Some engines provide the capability to **precompile and reuse** in the form of the **`Compilable`** interface along with the **`CompiledScript`** object.

However, `Compilable` is an **optional capability of each engine**, not a contract that every `ScriptEngine` must implement. The program needs to:

1. **Find an engine that is actually installed**, without assuming a language is built into the JDK.
2. **Check `engine instanceof Compilable`** before casting.
3. If supported, **compile once** for a stable script, keeping `CompiledScript` to run multiple times.
4. On each run, pass the **appropriate `Bindings` or `ScriptContext`** to swap data, without recompiling just because input values change.
5. If the engine does not support it, **fall back to `ScriptEngine.eval`** using the source code.
6. Manage the **engine lifecycle, state, thread safety, errors, and trust boundaries** of the executed script.

This article uses **Java 17+**. A key detail to remember: Java SE 17 still has the **`java.scripting`** module, but **does not guarantee a bundled JavaScript engine**. Nashorn was removed from the JDK starting in Java 15; to run JavaScript, you need a JSR-223-compatible provider on the classpath/module path and proper discovery configuration. The standalone runnable example in this article will use a **self-written minimal arithmetic engine** to verify the API without needing to download external libraries.

## 1. Distinguishing Four Common Objects

| Object | Role | What not to confuse it with |
| --- | --- | --- |
| `ScriptEngineManager` | Discovers registered `ScriptEngineFactory` instances via the service-provider mechanism | Not the engine itself; does not create a JavaScript interpreter on its own if a provider is missing |
| `ScriptEngine` | Executes scripts, holds the default `ScriptContext`, and allows passing data in via `Bindings` | **Not necessarily** capable of precompilation |
| `Compilable` | Optional interface with `compile(String)` and `compile(Reader)` | Being compilable does not mean the engine can be freely shared across threads |
| `CompiledScript` | Object holding the result of a compilation, which can invoke `eval()`, `eval(Bindings)`, `eval(ScriptContext)` | **Tied to the engine that created it**; not portable bytecode across different engines/JVMs |

Model:

~~~text
ScriptEngineManager
      │ find provider by name / extension / mime type
      ▼
ScriptEngine instance
      │
      ├── instanceof Compilable == false
      │        │
      │        └── engine.eval(source, bindings)  [fallback]
      │
      └── instanceof Compilable == true
               │
               ▼
          compile(source)  [runs once for the cached script]
               │
               ▼
          CompiledScript
               │
        ┌──────┼─────────────┐
        ▼      ▼             ▼
      eval(A) eval(B)       eval(C)
        │      │             │
        ▼      ▼             ▼
     data A  data B        data C
~~~

Here, the word "compile" follows the **scripting engine** definition: the engine may produce opcodes, ASTs, intermediate code, or classes; it is not required to use `javac` or generate `.class` files. Actual performance optimization depends on the implementation.

## 2. Finding an Engine and Checking `Compilable` Properly

`ScriptEngineManager` finds JSR-223-compatible providers using `ServiceLoader`. Without a matching provider, `getEngineByName` may return **`null`**.

~~~java
import javax.script.*;

ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");

if (engine == null) {
    throw new IllegalStateException(
        "JavaScript JSR-223 provider not found; check dependencies");
}
if (engine instanceof Compilable compiler) {
    CompiledScript prepared = compiler.compile("1 + 2");
    Object result = prepared.eval();
} else {
    Object result = engine.eval("1 + 2");
}
~~~

**This is an illustrative snippet** placed inside a method scope with the appropriate imports, **not a standalone program with deterministic stdout**: the engine name, syntax, and result depend on the actual provider.

How to inspect the environment before selecting an engine:

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + " / " +
            factory.getLanguageName() + " / " + factory.getNames());
}
~~~

This is also an illustrative snippet. The list may be empty on a default JDK 17 installation; **do not** treat that as a bug in `ScriptEngineManager`. You need to add the provider for the desired language, with the right version, class loader, and module/service configuration according to the provider's documentation.

**Why should you check with `instanceof` instead of casting directly?**

~~~java
CompiledScript compiled = ((Compilable) engine).compile(source);
~~~

The snippet above **can throw `ClassCastException`** if the engine does not implement `Compilable`. `ScriptEngine` and `Compilable` are two separate contracts; `Invocable` is also an independent capability and cannot be inferred from the presence of `Compilable`.

### 2.1. Do Not Recompile Repeatedly on Every Request

A suboptimal approach when the script code does not change:

~~~java
Object process(ScriptEngine engine, String source, Bindings vars)
        throws ScriptException {
    if (engine instanceof Compilable c) {
        return c.compile(source).eval(vars); // still COMPILES every time
    }
    return engine.eval(source, vars);
}
~~~

This is an illustrative method. Even though `Compilable` is present, the `compile` call still sits in the per-turn execution path — losing the benefit of reuse.

Instead, **prepare before serving requests**, store the `CompiledScript` object, and call `eval` with separate `Bindings`. Section 5 provides a `Prepared` pattern that works for both engines that support compilation and engines that do not.

## 3. `compile` Differs from `eval` in Timing

Same source:

~~~text
"price * quantity + fee"
~~~

Suppose:

~~~text
Order A: price=10, quantity=3, fee=2 -> 32
Order B: price= 4, quantity=5, fee=1 -> 21
~~~

Execution path diagram **without reuse**:

~~~text
Order A
   │
   ▼
engine.eval(source, bindingsA)
   │ parse/compile according to the provider's implementation (possibly)
   ▼
32

Order B
   │
   ▼
engine.eval(source, bindingsB)
   │ parse/compile according to the provider's implementation (possibly)
   ▼
21
~~~

Execution path diagram **with reuse**:

~~~text
Prepare once:
    compiled = ((Compilable) engine).compile(source)
                         │
                 keep compiled
                         │
             ┌───────────┴──────────┐
             ▼                      ▼
       compiled.eval(A)        compiled.eval(B)
             │                      │
             ▼                      ▼
            32                     21
~~~

According to the Javadoc, `CompiledScript` can be re-executed **without reparsing** the source code; the implementation may hold a Java class, class file, opcode, or other structure. One should not claim that every engine always achieves a significant speedup: very short scripts, heavy execution steps, binding/call overhead, or the engine's internal caching mechanism can make the difference small.

**Compiling does not mean executing business logic.** An engine may resolve imports/modules, check syntax, or prepare resources during compilation; specific side effects and execution timing depend on the language/provider contract. Avoid writing applications that rely on the assumption that "compilation can never produce side effects" across all engines.

## 4. Three Ways to Execute `CompiledScript`: Which Context Is Used?

This is the most important knowledge for avoiding data leaks between runs.

| API | `ENGINE_SCOPE` and environment | When to use |
| --- | --- | --- |
| `compiled.eval()` | Uses the **default `ScriptContext`** of the associated engine | Test scripts or when the default environment is actively managed |
| `compiled.eval(bindings)` | Uses the **passed `Bindings` as `ENGINE_SCOPE`** for this run. Reader, Writer, and `GLOBAL_SCOPE` from the engine's default context are used | Same script, multiple different input variable sets |
| `compiled.eval(scriptContext)` | Uses an **explicit `ScriptContext`**: scope, reader/writer, error writer | Need to customize I/O, global scope, policy, or per-request context |

### 4.1. `Bindings` Is Not a Copy of the Compiled Program

~~~java
Bindings first = engine.createBindings();
first.put("price", 10);
first.put("quantity", 3);
first.put("fee", 2);

Object firstResult = compiled.eval(first);
~~~

This is an illustrative snippet, assuming `engine` and `compiled` already exist. `Bindings` is a map from `String` keys to Java values, **not source code** and not a second `CompiledScript`. When passing a different `Bindings` set, the same compiled program receives new data.

`CompiledScript.eval(Bindings)` **does not need to and does not automatically replace the engine's default `ENGINE_SCOPE`** with the passed map. Therefore, if the script can mutate variables, changes in the passed `Bindings` may be visible according to the engine's contract, and this map should not be assumed to be immutable or deep-copied by default.

### 4.2. `eval()` Uses the Engine's Default State

~~~java
engine.put("price", 10);
engine.put("quantity", 3);
engine.put("fee", 2);
Object result = compiled.eval();
~~~

This is an illustrative example. `ScriptEngine.put` places variables into the default `ENGINE_SCOPE`, because `compiled.eval()` uses the engine's default context. If a web application has multiple requests concurrently modifying `engine.put("userId", ...)`, runs may see interleaved state; **do not share unsynchronized default bindings across requests**.

### 4.3. `ScriptContext` Allows Managing Scope and I/O

~~~java
SimpleScriptContext ctx = new SimpleScriptContext();
Bindings attrs = engine.createBindings();
attrs.put("price", 10);
attrs.put("quantity", 3);
attrs.put("fee", 2);
ctx.setBindings(attrs, ScriptContext.ENGINE_SCOPE);
ctx.setWriter(new java.io.StringWriter());
Object result = compiled.eval(ctx);
~~~

This is an illustrative snippet, with `engine`/`compiled` already present. Use `ScriptContext` when you need a separate Writer/Reader per run, or need explicit control over `GLOBAL_SCOPE`.

According to `ScriptContext.getAttribute(name)` rules, scopes are looked up in priority order. If a name exists in both `ENGINE_SCOPE` and `GLOBAL_SCOPE`, the engine scope value takes precedence. When using `eval(Bindings)`, the `GLOBAL_SCOPE` of the default context **may still participate in lookup**; if you need to isolate all data, create a context and explicitly restrict the scopes as well as the Java objects that can be accessed.

### 4.4. `eval(null)` Is Not Equivalent to Passing an Empty Map

In the `CompiledScript.eval(Bindings)` overload, passing `null` according to the Javadoc has the same effect as `eval(getEngine().getContext())` — meaning it **uses the default context**. An empty `new SimpleBindings()`, on the other hand, creates an **empty `ENGINE_SCOPE`** (which may still inherit `GLOBAL_SCOPE`), so the result can differ.

Do not try to use `null` to "clear variables from the previous run." When you need to reset state, create a new `Bindings` or a new context with a clear policy.

## 5. Designing Fallback Capability: Prepare Once, Execute Many Times

A safer approach is to build a prepared object that retains the `ScriptEngine`, source, and `CompiledScript` if available:

~~~java
record Prepared(ScriptEngine engine, String source, CompiledScript compiled) {
    Object eval(Bindings variables) throws ScriptException {
        return compiled != null
                ? compiled.eval(variables)
                : engine.eval(source, variables);
    }
}

static Prepared prepare(ScriptEngine engine, String source)
        throws ScriptException {
    CompiledScript compiled = engine instanceof Compilable compiler
            ? compiler.compile(source)
            : null;
    return new Prepared(engine, source, compiled);
}
~~~

**These are illustrative method/record snippets**, not a standalone Java file. The complete example in section 6 contains the corresponding code and is verified.

Note that:

- `prepare` calls `compile` at most once **per `Prepared`**.
- `Prepared` retains **the same engine** that performed the compilation; do not fetch a new engine from the manager for each `eval` and use the old compiled object.
- If the engine does not support `Compilable`, `compiled` is `null` and each run uses `engine.eval(source, variables)`; this is a **functionally correct fallback**, not a compiled execution.
- A `CompiledScript` **is not automatically independent of engine state**. The Javadoc states that it is associated with the engine that created it; state mutations during execution may show up in another run.
- `Prepared` in the example **does not add synchronization itself**; multi-threaded usage must follow the engine/provider's contract.

If the language has global variables or side effects, simply passing separate `Bindings` does not necessarily isolate the interpreter's internal state completely; see section 8.

## 6. Standalone Java 17 Program, No JavaScript Provider Required

To provide a demonstration whose **stdout can be run and verified on a standard JDK 17**, we build a **teaching engine** that only understands a very narrow arithmetic syntax:

~~~text
identifier * identifier + identifier
~~~

For example `price * quantity + fee`. During `compile`, the engine parses the source and stores the three **variable names** in an `Expression` structure; during `eval`, it reads the **actual numeric values** from the context. This allows counting **parse once, execute many times**. A second engine uses the same syntax but **does not implement `Compilable`**, demonstrating the fallback branch.

**Demo scope:** `TinyEngine` is not a JavaScript engine, full parser, sandbox, or production provider; `TinyFactory` is minimal metadata for demo purposes only, **not registered with `ScriptEngineManager`**. The demo does not download external libraries or accept arbitrary code from the Internet.

Create the file **`CompilableReuseDemo.java`** with the full content:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.script.*;

public final class CompilableReuseDemo {
    private static final String SOURCE = "price * quantity + fee";
    private static final Pattern EXPRESSION = Pattern.compile(
            "\\s*([A-Za-z][A-Za-z0-9_]*)\\s*\\*\\s*" +
            "([A-Za-z][A-Za-z0-9_]*)\\s*\\+\\s*" +
            "([A-Za-z][A-Za-z0-9_]*)\\s*");

    private record Expression(String left, String right, String extra) {
        double execute(ScriptContext context) throws ScriptException {
            return number(context, left) * number(context, right)
                    + number(context, extra);
        }
    }

    private static Expression parse(String source) throws ScriptException {
        Matcher match = EXPRESSION.matcher(source);
        if (!match.matches()) {
            throw new ScriptException("Only 'a * b + c' is supported");
        }
        return new Expression(match.group(1), match.group(2), match.group(3));
    }

    private static double number(ScriptContext context, String name)
            throws ScriptException {
        Object value = context.getAttribute(name);
        if (!(value instanceof Number numeric)) {
            throw new ScriptException("Missing numeric variable: " + name);
        }
        return numeric.doubleValue();
    }

    private static String read(Reader reader) throws ScriptException {
        try {
            StringBuilder text = new StringBuilder();
            char[] buffer = new char[1024];
            for (int n; (n = reader.read(buffer)) != -1;) {
                text.append(buffer, 0, n);
            }
            return text.toString();
        } catch (IOException e) {
            throw new ScriptException(e);
        }
    }

    static class TinyEngine extends AbstractScriptEngine {
        int parses;
        int evaluations;

        Expression parseOnce(String source) throws ScriptException {
            Expression expression = parse(source);
            parses++;
            return expression;
        }

        Object execute(Expression expression, ScriptContext context)
                throws ScriptException {
            evaluations++;
            return expression.execute(context);
        }

        @Override
        public Object eval(String source, ScriptContext context)
                throws ScriptException {
            return execute(parseOnce(source), context);
        }

        @Override
        public Object eval(Reader source, ScriptContext context)
                throws ScriptException {
            return eval(read(source), context);
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return new TinyFactory();
        }
    }

    static final class CompilingTinyEngine extends TinyEngine implements Compilable {
        int compilations;

        @Override
        public CompiledScript compile(String source) throws ScriptException {
            Expression expression = parseOnce(source);
            compilations++;
            return new CompiledScript() {
                @Override
                public Object eval(ScriptContext context) throws ScriptException {
                    return execute(expression, context);
                }

                @Override
                public ScriptEngine getEngine() {
                    return CompilingTinyEngine.this;
                }
            };
        }

        @Override
        public CompiledScript compile(Reader source) throws ScriptException {
            return compile(read(source));
        }
    }

    static final class TinyFactory implements ScriptEngineFactory {
        public String getEngineName() { return "Tiny arithmetic demonstration"; }
        public String getEngineVersion() { return "1"; }
        public List<String> getExtensions() { return List.of("tiny"); }
        public List<String> getMimeTypes() { return List.of("text/x-tiny"); }
        public List<String> getNames() { return List.of("tiny"); }
        public String getLanguageName() { return "TinyArithmetic"; }
        public String getLanguageVersion() { return "1"; }
        public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> getNames().get(0);
                default -> null;
            };
        }
        public String getMethodCallSyntax(String obj, String name, String... args) {
            return null;
        }
        public String getOutputStatement(String text) { return null; }
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        public ScriptEngine getScriptEngine() { return new CompilingTinyEngine(); }
    }

    private record Prepared(ScriptEngine engine, String source,
                            CompiledScript compiled) {
        Object eval(Bindings bindings) throws ScriptException {
            return compiled != null
                    ? compiled.eval(bindings)
                    : engine.eval(source, bindings);
        }
        Object eval(ScriptContext context) throws ScriptException {
            return compiled != null
                    ? compiled.eval(context)
                    : engine.eval(source, context);
        }
    }

    private static Prepared prepare(ScriptEngine engine, String source)
            throws ScriptException {
        CompiledScript compiled = engine instanceof Compilable compiler
                ? compiler.compile(source) : null;
        return new Prepared(engine, source, compiled);
    }

    private static Bindings variables(ScriptEngine engine,
                                      double price, double quantity, double fee) {
        Bindings values = engine.createBindings();
        values.put("price", price);
        values.put("quantity", quantity);
        values.put("fee", fee);
        return values;
    }

    public static void main(String[] args) throws Exception {
        CompilingTinyEngine fast = new CompilingTinyEngine();
        Prepared cached = prepare(fast, SOURCE);
        System.out.println("compilable: " + (fast instanceof Compilable));
        System.out.println("compiled: " + (cached.compiled() != null));
        System.out.println("same engine: " + (cached.compiled().getEngine() == fast));

        Bindings orderA = variables(fast, 10, 3, 2);
        Bindings orderB = variables(fast, 4, 5, 1);
        System.out.println("compiled A: " + cached.eval(orderA));
        System.out.println("compiled B: " + cached.eval(orderB));

        fast.put("price", 2.0);
        fast.put("quantity", 3.0);
        fast.put("fee", 1.0);
        System.out.println("default context: " + cached.compiled().eval());

        SimpleScriptContext context = new SimpleScriptContext();
        context.setBindings(variables(fast, 7, 2, 1),
                ScriptContext.ENGINE_SCOPE);
        System.out.println("explicit context: " + cached.eval(context));
        System.out.println("compile calls: " + fast.compilations);
        System.out.println("parse calls: " + fast.parses);
        System.out.println("execute calls: " + fast.evaluations);

        Bindings incomplete = fast.createBindings();
        incomplete.put("price", 10);
        incomplete.put("quantity", 2);
        try {
            cached.eval(incomplete);
        } catch (ScriptException expected) {
            System.out.println("missing binding: " + expected.getMessage());
        }

        CompiledScript fromReader = ((Compilable) fast).compile(
                new StringReader(SOURCE));
        System.out.println("reader compiled: " + (fromReader.getEngine() == fast));

        TinyEngine plain = new TinyEngine();
        Prepared fallback = prepare(plain, SOURCE);
        System.out.println("fallback compilable: " + (plain instanceof Compilable));
        System.out.println("fallback A: " + fallback.eval(orderA));
        System.out.println("fallback B: " + fallback.eval(orderB));
        System.out.println("fallback parse calls: " + plain.parses);

        try {
            ((Compilable) fast).compile("price + quantity");
        } catch (ScriptException expected) {
            System.out.println("bad source: " + expected.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 CompilableReuseDemo.java
java CompilableReuseDemo
~~~

**Exact stdout** with the teaching engine example:

~~~text
compilable: true
compiled: true
same engine: true
compiled A: 32.0
compiled B: 21.0
default context: 7.0
explicit context: 15.0
compile calls: 1
parse calls: 1
execute calls: 4
missing binding: Missing numeric variable: fee
reader compiled: true
fallback compilable: false
fallback A: 32.0
fallback B: 21.0
fallback parse calls: 2
bad source: Only 'a * b + c' is supported
~~~

### 6.1. Exact Output Analysis

- `compilable: true`: the `CompilingTinyEngine` engine **implements `Compilable`**, so `prepare` calls `compile`.
- `compiled: true` and `same engine: true`: `CompiledScript` is created and retains **that same engine** via `getEngine()`.
- `compiled A: 32.0` and `compiled B: 21.0`: a single `CompiledScript` runs with two sets of `Bindings`, the same expression but different values.
- `default context: 7.0`: `fast.put` modifies the default engine scope; `compiled.eval()` uses it to compute `2 × 3 + 1`.
- `explicit context: 15.0`: `compiled.eval(context)` reads `7 × 2 + 1` from `ENGINE_SCOPE` in the caller-supplied context.
- `compile calls: 1`, `parse calls: 1`, and `execute calls: 4`: four successful turns execute a plan parsed **once**.
- `missing binding: ...fee`: the source code compiled validly, but one eval turn is missing a required variable, so `ScriptException` occurs **at runtime**, not at compile time.
- `reader compiled: true`: the `compile(Reader)` overload also returns a `CompiledScript` bound to the right engine.
- `fallback compilable: false`: `TinyEngine` does not implement `Compilable`. Both `fallback.eval(...)` turns call `engine.eval(source,bindings)`; `fallback parse calls: 2` illustrates having to parse on every turn according to the **demo implementation**, without claiming every real-world provider must reparse repeatedly.
- `bad source: ...`: invalid syntax is rejected with `ScriptException` right at `compile`.

### 6.2. Why Is This an Honest Demo, Yet Not a Real-World Engine?

The parser only accepts **three identifiers and two operators `*`/`+`**, with no numeric literals, function calls, escapes, imports, sandbox, or ECMAScript standard. `TinyFactory` only provides minimal metadata and does not register a service provider file, so `ScriptEngineManager.getEngineByName("tiny")` will not find it automatically. `Factory.getProgram` is also not intended to support multi-statement grammar.

The value `32.0` is a `Double` from `Number.doubleValue()`, not an ECMAScript result or exact monetary rule. In monetary systems, use `BigDecimal` or controlled numeric types with appropriate rounding rules; the demo uses `double` to focus on the `compile/eval` lifecycle.

What can be applied directly to real engines is **how to check capabilities, the `Prepared` structure, the `eval` overloads, and how to pass `Bindings`**. The API behavior of each specific scripting language/provider still requires reading its own documentation.

## 7. Integrating into an Application: Preparing, Caching, and Reusing Properly

A common usage cycle in a pricing or templating service:

~~~text
STARTUP / FIRST USE
  ├── create ScriptEngineManager
  ├── select compatible ScriptEngine provider
  ├── check Compilable
  ├── compile script X if supported
  └── store Prepared { engine, source, compiled? }

EACH REQUEST
  ├── create request's Bindings/ScriptContext
  ├── put validated data into the appropriate scope
  ├── prepared.eval(bindings/context)
  ├── validate result type, handle errors
  └── do not recompile X just because input changed

WHEN CONFIGURATION / SOURCE / PROVIDER CHANGES
  ├── invalidate the appropriate cache entry
  ├── recompile with the appropriate engine/config
  └── release old references when safe
~~~

### 7.1. Choosing the Right Cache Key

Caching solely by file name `"price.js"` is not enough. A reasonable cache can consider:

- **Exact source content** or source hash (including managed version).
- **Engine instance** or at least provider identity/version/configuration, because `CompiledScript` is **tied to the engine that compiled it**.
- Language/version/syntax, class loader/module context, and options affecting compilation.
- Tenant/execution permission boundaries, if the provider can use different metadata or state during compilation.

If the script changes, invalidation must ensure new requests do not continue running the old plan. The cache should not retain every `CompiledScript` indefinitely: this object may hold references to the engine, class loader, bytecode, closures, and large structures, causing resource retention or preventing loaders from being garbage-collected. Use size/lifecycle bounds appropriate to the system conditions.

### 7.2. When Should You *Not* Cache?

- Script code rarely repeats or each request generates completely new source.
- Compilation has high preparation overhead relative to just a few uses.
- The engine or configuration set changes frequently.
- The script contains session-dependent state; the compiled object cannot be shared by policy.
- Strong isolation is required and the provider only allows running each script in a separate engine/sandbox.

**Evaluate performance with real benchmarks**, including compile time, eval time, data variance, allocation, JIT warmup, thread contention, and memory retention. Do not assume "compile then eval" is always faster than `eval(source)` across all providers.

## 8. Thread Safety: Can `CompiledScript` Be Shared Across Threads?

**Do not infer thread safety from `instanceof Compilable`.** The `Compilable` interface only states that the engine can compile. It does not stipulate that engine state, `CompiledScript`, the underlying interpreter, and your `Bindings` are thread-safe.

Standard metadata you can inspect:

~~~java
Object threading = engine.getFactory().getParameter("THREADING");
System.out.println(threading);
~~~

This is an illustrative snippet; output depends on the provider. According to the Java 17 Javadoc:

| `THREADING` value | Declared contract meaning |
| --- | --- |
| `null` | Engine is **not guaranteed safe** for concurrent execution; per the contract it is described as not thread-safe |
| `"MULTITHREADED"` | Engine executes scripts concurrently safely internally, but state may affect one another across threads |
| `"THREAD-ISOLATED"` | Like MULTITHREADED, while also maintaining symbol values isolated per thread |
| `"STATELESS"` | Like THREAD-ISOLATED, with the added constraint that script execution does not alter the ENGINE_SCOPE `Bindings` mapping |

These values are **metadata declared by the engine provider**, not an automatic locking mechanism enforced by `ScriptEngineManager`. Even when an engine reports MULTITHREADED, Java code placed in `Bindings` or external side effects must still be protected by you.

Some practical options:

1. **One engine/compiled plan on a dedicated thread**, dispatching requests into a queue if the provider is not thread-safe.
2. **Engine-per-thread** or an engine pool with clear ownership; each engine needs its **own compiled plan** (do not take a plan from engine A and pass it to engine B).
3. **Synchronize around all shared uses of a single engine/compiled object** if the provider itself permits that usage and throughput is acceptable.
4. **Separate context/bindings per request** to avoid overwriting values; simultaneously audit state outside bindings and mutable objects passed into the engine.

In the section 6 program, the two counters `parses`/`evaluations` are intentionally unsynchronized plain fields. It is a **single-threaded** demo, not an example authorizing safe multi-threaded engine usage.

## 9. Do Errors Occur at Compile Time or Eval Time?

| Error location | Common symptoms | Action |
| --- | --- | --- |
| **Discovery** | `getEngineByName(...) == null` | Check JSR-223 provider dependency, engine/factory name, class loader, and module/service discovery |
| **Capability check** | Casting to `Compilable` throws `ClassCastException` | Use `instanceof Compilable`; fall back to `engine.eval` |
| **Compile** | `ScriptException` due to syntax/source parsing error | Report script location (line/column if provider supplies it), fix source, do not cache failed plan |
| **Compile input** | `compile(null)` may throw `NullPointerException` per API | Validate source/Reader before compiling |
| **Eval** | `ScriptException` due to missing variable, runtime error, import, or language exception | Distinguish request data errors from script errors; track root cause and context |
| **Eval** | `compiled.eval((ScriptContext) null)` causes `NullPointerException` | Supply a valid context or call `eval()` to use the default |
| **Result conversion** | Java code casts result to the wrong type | Inspect the `Object` returned from eval, convert according to the language contract; do not cast blindly |
| **Concurrent usage** | Race condition, interleaved state, wrong results | Check `THREADING` and the engine's synchronization/pooling policy |
| **Cache invalidation** | Script was modified but still runs old behavior | Cache by source/engine/config, invalidate according to script lifecycle |

**Do not try to turn every error into `ScriptException`.** Some errors come from the Java caller (bad cast, `NullPointerException` from passing a null argument, class loading errors, `Error`) and are not script syntax errors. Log appropriately and avoid letting messages contain sensitive information from `Bindings`.

### 9.1. Why Not Share the Same `Bindings` Everywhere?

Suppose request A sets `userId="A"` and B sets `userId="B"` in the **same** `engine.getBindings(ENGINE_SCOPE)`. Without synchronization, if the engine uses that variable, request A may see `B`. Precompilation does not eliminate this phenomenon.

A simpler approach is to create a **new map for each request**:

~~~java
Bindings variables = engine.createBindings();
variables.put("userId", requestUserId);
Object output = compiled.eval(variables);
~~~

This is an illustrative snippet, with `requestUserId`, `engine`, and `compiled` available. It helps avoid **directly overwriting a shared map**, but is not enough to declare the engine thread-safe or isolate all global objects. Restrict the data exposed to the script according to your security policy.

## 10. Safety When Running External Scripts

`CompiledScript` is a **reuse optimization**, not a sandbox. A script engine may allow calling Java classes, reflection, I/O, network, or accessing objects placed into `Bindings`. Do not use `compile` as a check of what a script is permitted to do.

For scripts coming from users, untrusted sources, or multi-tenant environments:

- Choose a language/provider that supports isolation and explicit permission configuration; carefully review Java-host interop capabilities.
- Enforce time and resource limits at a boundary that can genuinely enforce them. `Future.cancel(true)` or `Thread.interrupt()` is **not** a guaranteed measure to stop every interpreter/script.
- For high risk, run in an **isolated process/container** with appropriate permissions, CPU/memory, network, and filesystem restrictions.
- Do not pass `DataSource`, credentials, class loaders, or privileged objects directly into `Bindings`.
- Treat a tenant's compiled cache as an asset that must be properly partitioned; do not let another tenant's scripts see unauthorized global state or cached objects.
- Log source ID/hash and concise errors, avoiding logging raw scripts or sensitive data unnecessarily.

These issues **are not solved by `Compilable` alone**.

## 11. Implementation Checklist in a Java 17 Application

1. **Verify the engine actually exists at runtime**: `ScriptEngineManager.getEngineFactories()` and `getEngineByName` return a valid instance; do not assume a JavaScript engine ships with JDK 17.
2. **Choose provider/version** and verify language/syntax. `compile` from one engine does not accept syntax from another engine.
3. **Check `engine instanceof Compilable`**; if unsupported, still have the `engine.eval(source, ...)` branch.
4. **Compile once for stable source**, do not place `compile` inside every request. Watch out for preparation cost.
5. **Keep `CompiledScript` with the same engine** that created it; check `getEngine()` when diagnosing issues.
6. **Pass a fresh `Bindings` or `ScriptContext` with explicit scope** for each run. If using `eval()`, manage the default context actively.
7. **Ensure the right concurrency policy**: check `getFactory().getParameter("THREADING")` and provider documentation; do not arbitrarily share compiled objects across threads.
8. **Handle `ScriptException` separately at compile/eval**; validate the type and meaning of the `Object` result.
9. **Cache by version/source/engine/config**, with invalidation and memory limits. Do not treat `CompiledScript` as portable data.
10. **Protect the script boundary**: quotas, isolation, host access, bindings data, and auditing according to trust level.

## 12. Self-Check Exercises

**1.** `engine instanceof Compilable` is `false`. What must you do to run the script?  
**Answer:** Use `engine.eval(source, bindings/context)`, without casting and without assuming a `CompiledScript` exists.

**2.** You call `((Compilable)engine).compile(source).eval(bindings)` on every HTTP request. Have you reused the compiled program?  
**Answer:** Not yet. It still compiles on every request; you need to move `compile` to a preparation step and retain the `CompiledScript`.

**3.** A `CompiledScript` runs with `Bindings A` and `Bindings B`. Do you need to recompile if only `price`/`quantity`/`fee` change?  
**Answer:** No, if the **source/script** and engine context do not change; pass the data via `eval(Bindings)`.

**4.** Where does `compiled.eval()` get variables from? How does `compiled.eval(bindings)` differ?  
**Answer:** `eval()` uses the engine's default `ScriptContext`; `eval(bindings)` uses the passed map as `ENGINE_SCOPE`, with default globals/I/O per the Javadoc.

**5.** `compiled.getEngine() == engineA`. Can you call `engineB.eval(...)` to execute that same compiled plan on engine B?  
**Answer:** There is no universal API to transfer a `CompiledScript` to another engine. `CompiledScript` is tied to engine A; if you want B to use a compiled plan, compile separately on B.

**6.** The factory returns `THREADING = null`. Can you safely call a shared `compiled.eval(...)` from 10 threads just because each thread has its own `Bindings`?  
**Answer:** No. Separate `Bindings` do not make the engine thread-safe. You need to serialize access or use separate engines per the provider contract.

**7.** `new ScriptEngineManager().getEngineByName("JavaScript")` returns `null` on Java 17. Is that abnormal?  
**Answer:** Not necessarily. Nashorn was removed in JDK 15; you need to install/configure an appropriate JSR-223 JavaScript provider.

**8.** A script compiles successfully, but when eval runs, `fee` is missing—what error occurs?  
**Answer:** It may be a `ScriptException` at eval time due to a missing variable or runtime semantic violation; it is not evidence that `compile` failed syntax checking. The demo verified this scenario.

**9.** You want to cache `CompiledScript` by file name only and share it application-wide. What conditions are missing?  
**Answer:** You must account for source version/content, engine identity and configuration, tenant permissions, thread safety, cache lifecycle, and invalidation.

**10.** A script contains system-access commands but compiles successfully. Does that prove it is safe to execute?  
**Answer:** No. `Compilable` is not a sandbox; permissions and isolation must be configured independently.

## Official Java 17 Documentation

- [`javax.script` package overview — Script execution, Bindings, Compilation, Discovery](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/package-summary.html)
- [`Compilable` — optional interface, `compile(String)` and `compile(Reader)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Compilable.html)
- [`CompiledScript` — `eval()`, `eval(Bindings)`, `eval(ScriptContext)`, `getEngine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/CompiledScript.html)
- [`ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [`ScriptEngineManager` and service discovery](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [`ScriptEngineFactory` — `THREADING` metadata](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html)
- [`ScriptContext` and `SimpleScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html)
- [Oracle JDK 17 Migration Guide — Nashorn removed in JDK 15](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html)