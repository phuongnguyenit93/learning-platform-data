# Limits of Syntax Portability, Type Conversion, and Engine Termination Mechanisms

Java provides the **JSR-223 / Scripting for the Java Platform** API in the `java.scripting` module, primarily through `javax.script.ScriptEngineManager`, `ScriptEngine`, `Bindings`, `ScriptContext`, and `ScriptEngineFactory`. The API enables a Java application to **work with multiple script engines through a common Java interface**; however, it **does not standardize the scripting language, its type system, the ability to stop a running script, or the engine's isolation level**.

Three design questions must be answered *separately*:

1. **Is script syntax portable to another engine?** There is no guarantee that the same script string will be understood and executed identically by all engines.
2. **How are Java and script values converted?** `eval` accepts and returns `Object`; Java has no universal conversion rule across all languages and engines.
3. **When a script exceeds its time limit, who stops it?** The `ScriptEngine` API has no standard `stop()`, `interrupt()`, or `close()` operation. Timeouts, thread interruption, and engine termination must be separated per the implementation's contract.

**Core principle:** you can standardize *the Java invocation wrapper*, yet true portability requires **application-designed contracts for syntax, data, lifecycle, and execution limits**, tested against each engine.

## 1. Which Layer Does JSR-223 Standardize?

Core components:

| API | Standardized Role | Not Guaranteed |
| --- | --- | --- |
| `ScriptEngineManager` | Discovers/registers engine factories; finds engines by name, extension, MIME type | That the environment always has an engine for JavaScript/Groovy or any particular language |
| `ScriptEngine` | `eval(String/Reader, ...)`, `put/get`, `createBindings`, get/set context | Shared syntax, shared type mapping, sandbox, timeout, stop |
| `ScriptEngineFactory` | Engine name, version, language, aliases, extensions, MIME, `THREADING` metadata | Uniform engine/version behavior across vendors |
| `Bindings` | A `String → Object` map for attributes visible to scripts | How variable names, host objects, null, or types are interpreted inside scripts |
| `ScriptContext` | `ENGINE_SCOPE`, `GLOBAL_SCOPE`, and input/output/error readers/writers | Complete isolation of engine or request state |
| `Invocable` | Calls script functions/methods when the engine supports this interface | Universal support across engines; identical function naming, argument conversion, or proxies |
| `Compilable` | Precompiles scripts via `compile` when supported by the engine | Portable caching/bytecode/compiled artifacts across engines or versions |
| `ScriptException` | API error type thrown when evaluation fails | Uniform representation of all native/timeout/cancellation errors |

`ScriptEngineManager` relies on Java's service provider mechanism to discover `ScriptEngineFactory` implementations on the runtime classpath/module path. You can use `registerEngineName` to register a factory **within that manager instance**, though this does not register a new language globally across the entire JVM.

**Important for Java 17:** the `java.scripting` module still exists, but **the JDK does not bundle the Nashorn JavaScript engine by default**. Nashorn was removed from the JDK in Java 15 (JEP 372). Therefore:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    throw new IllegalStateException(
        "No JavaScript engine configured; add and verify a compatible provider");
}
```

This is a **snippet** requiring `import javax.script.*;`. It only proceeds when the system actually has a JSR-223 JavaScript provider installed. Do not write Java 17 exercises assuming `engine.eval("1 + 2")` works while skipping the `null` check. When using a named application module, declare `requires java.scripting;` and configure the provider/module path per the chosen engine's documentation.

## 2. Syntax Portability: Same `eval` Does Not Mean Same Language

`ScriptEngine.eval(String script)` takes a **content string**, yet that content is parsed according to the **grammar and semantics of the language executed by that engine**.

Examples of differences to consider:

- How variables, blocks, functions, and imports/modules are declared: `let`/`const` in JavaScript is not shared syntax with Groovy or Python.
- Truthiness, string concatenation operators, equality comparison, evaluation order, exception syntax.
- Arithmetic: integer vs. floating-point division; overflow; precision; BigInt, decimals, and numeric APIs.
- Variable scoping, closures, global objects, async/promises/coroutines; host interop mechanisms.
- Built-ins such as `Date`, `JSON`, `Math`, `print`, I/O, or package imports may differ.
- Even within the "JavaScript" language, different engines and versions may support different ECMAScript levels, host access rules, or extensions.

The example below **only illustrates JavaScript syntax**, not a "portable script":

```javascript
const price = 19.5;
const quantity = 2;
price * quantity;
```

For another engine, you must supply source code written in its language. JSR-223 does not translate `const`, operators, built-ins, or control flow across engines.

### Inspecting Metadata Before Execution

An adapter can check:

```java
ScriptEngineFactory f = engine.getFactory();
String engineName = f.getEngineName();
String engineVersion = f.getEngineVersion();
String language = f.getLanguageName();
String languageVersion = f.getLanguageVersion();
Object threading = f.getParameter("THREADING");
```

This is a **snippet**; `engine` must already have been created successfully. `getNames()`, `getExtensions()`, and `getMimeTypes()` can list aliases/identifiers advertised by the provider. **Aliases are not portable identifiers of a standardized language**. "JavaScript" can resolve to different engines depending on dependencies and class loaders; always pin the supported implementation and version in product configuration.

A pragmatic selection strategy:

1. Specify the **language + engine/version** supported by the application (e.g., a concrete subset).
2. Select the provider from controlled dependencies using a verified engine name.
3. Inspect metadata and run a startup smoke test confirming required features.
4. If the required engine is absent, **fail fast**—never silently fall back to another language.
5. If replacing an engine, run migration and regression tests for every script rather than assuming "just swap the engine name."

### Invocable and Compilable Are Optional

`Invocable` and `Compilable` are not mandatory capabilities of every `ScriptEngine`:

```java
if (engine instanceof Compilable compilable) {
    CompiledScript program = compilable.compile(scriptText);
    // Use program within the lifetime/version of that same engine.
} else {
    engine.eval(scriptText);
}

if (engine instanceof Invocable invocable) {
    // Only when the script has declared a compatible function.
    Object answer = invocable.invokeFunction("transform", input);
}
```

This is a **snippet** with `engine`, `scriptText`, and `input` supplied; it requires `import javax.script.*;`. Even when `Invocable` is supported, function naming, method binding, exceptions, and conversions still depend on the language/engine. Nor is `CompiledScript` a portable artifact format across engines.

## 3. Data Areas: Bindings, ScriptContext, and State That Can Leak Between Requests

`Bindings` is a string-keyed map, and `ScriptContext` manages at least two scopes: `ENGINE_SCOPE` and `GLOBAL_SCOPE`. An engine may maintain **internal contexts, global variables, runtime caches, or host object references**, depending on the implementation. Thus "passing a separate `Bindings` to every `eval`" does not automatically prove all internal engine state is isolated.

Java caller supplying arguments:

```java
Bindings b = engine.createBindings();
b.put("customerId", "C-100");
b.put("quantity", 3);
Object raw = engine.eval(scriptText, b);
```

This is a **snippet**; the syntax the script uses to read `customerId` depends on the specific engine. The Java side should construct **a dedicated `Bindings` per evaluation**, without mutating that map concurrently while the engine reads it; a `List`, `Map`, or Java service placed inside `Bindings` can still carry shared mutable state.

### State Ownership Rules

- Separate **input values** from **engine global state**; never call `engine.put("user", ...)` on a singleton engine serving multiple concurrent users without a threading and isolation contract.
- Create engines/contexts at the proper scope (evaluation, worker, session, or app), defining when to reset, dispose, and whether reuse is permitted.
- If each request requires strict independence, a fresh `ScriptContext` is not necessarily enough; you may need a fresh engine or a separate process.
- A factory may advertise `getParameter("THREADING")` metadata. Meaning of the standard values in JDK 17:

| `THREADING` | Concurrency Contract Advertised by the Engine |
| --- | --- |
| `null` | Engine is not thread-safe; do not invoke concurrently on the same instance |
| `"MULTITHREADED"` | Engine synchronizes itself to allow concurrent execution, but effects across scripts may be visible to each other |
| `"THREAD-ISOLATED"` | Satisfies MULTITHREADED and keeps symbol values independent across threads |
| `"STATELESS"` | Satisfies THREAD-ISOLATED and script execution does not alter the `ENGINE_SCOPE` `Bindings` map |

Threading metadata **is not a sandbox/security guarantee**; passed-in host objects still have their own concurrency contracts. `getParameter("THREADING") == null` should be treated under the assumption of **no concurrent sharing**. To run in parallel, pool independent engines **only if permitted by the vendor**, or spawn separate workers/processes per policy.

## 4. Type Conversion: There Is No "Portable Object" Across All Engines

On the Java side, `ScriptEngine.eval` returns `Object`. On the script side, the type system may differ from Java's. Engines apply their own strategies to represent and convert values:

| Value at the Boundary | Common Risk | Principle |
| --- | --- | --- |
| Integers `int`, `long` | Engine converts to double, BigInteger, another wrapper, or proxy | Validate actual `Number`; never blindly cast `(Integer) raw` |
| Floating-point `double` | Binary floating-point error; NaN, ±Infinity | Explicit precision/range contract; never use directly for money |
| `BigDecimal` | Engine may keep a host object, convert to float, or not support it | Encode decimal as a string/typed record and parse by rule |
| `boolean` | Truthiness and Boolean coercion rules differ | Require an exact `Boolean` return; do not treat `0`/`""`/null as implicit false |
| `String` | Charset, Unicode normalization, escaping, and interpolation | Explicit string/encoding/normalization contract |
| `null`, missing, "undefined" | Missing key differs from key with null value; engines have distinct sentinels | Check `Bindings.containsKey`; model nullability explicitly |
| Arrays/lists | May be a Java `List`, script array, proxy, or wrapper | Do not cast blindly; convert to a validated DTO/`List` |
| Objects/maps | Script object may not be a `java.util.Map` | Use an adapter converting keys/values and validating schema |
| Date/time | Languages/engines differ in precision, timezone, and format | Use ISO-8601 or epoch with explicit unit and timezone |
| Java host objects | May expose host methods, reflection, and privileges | Expose only approved facades; never rely on conversion as security |
| Function/promise/async handle | May be a live runtime/engine-bound object | Do not return directly across a stable boundary; resolve into standard data |

Example of explicit type checking:

```java
Object raw = engine.eval(scriptText, bindings);
if (!(raw instanceof Number n)) {
    throw new IllegalArgumentException("Script must return a number");
}
double value = n.doubleValue();
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Non-finite result");
}
```

This is a **snippet**. It fits when the application API **accepts floating-point numbers with double precision**. It is **unsuitable** when results are monetary amounts or large integer IDs requiring exact precision; `doubleValue()` can lose precision from `BigDecimal`/`BigInteger`.

### Example on Integer Precision

Java `long` can represent 9,007,199,254,740,993 ($2^{53} + 1$). Under IEEE-754 double numeric semantics such as JavaScript `Number`, not every integer above $2^{53} - 1$ is represented exactly. A JSR-223 provider may convert `Long` in its own way; **never assume scripts always receive all 64-bit IDs accurately**. For IDs, use decimal strings or an explicitly supported and tested BigInt type.

### Decimals for Money and Exact Precision

Instead of passing a `double` and hoping the engine preserves it:

```java
Bindings b = engine.createBindings();
b.put("amountText", "0.10");       // decimal per contract
b.put("currency", "VND");
Object raw = engine.eval(scriptText, b);

// Suppose the contract requires the script to return a decimal as a String:
if (!(raw instanceof String decimalText)) {
    throw new IllegalStateException("Expected decimal string result");
}
java.math.BigDecimal amount = new java.math.BigDecimal(decimalText);
```

This is a **snippet of an application protocol** and does not guarantee every engine treats `amountText` as a decimal number automatically. The script adapter must parse/format according to the engine's language, specifying scale, rounding, and invalid-input rules. Use `BigDecimal(String)` rather than `BigDecimal(double)` when exact input decimal representation is required.

### Recommending a Testable Output Contract

Rather than letting business logic depend on provider implementation classes, define output as:

- A schema-defined DTO/record on the Java side with basic fields like `String`, `boolean`, `List`, decimal strings, and ISO-8601 timestamps;
- Or JSON text with an explicit JSON schema/contract version; script engines serialize to JSON text within their runtime, and Java parses with its chosen library.

Types coming from scripts must pass through a **recognizing and validating adapter**. Never cast `(Map<String,Object>) engine.eval(...)` unless the vendor explicitly guarantees the return value is a Java `Map`. Especially avoid leaking proxy objects tied to a disposed engine.

## 5. When to Distinguish null, Missing, and Exception?

A script interface can distinguish:

- **Missing input**: no `"limit"` key in Bindings; check via `containsKey` before `get`.
- **Explicit null**: key exists with value `null`; represents "no value" if the schema permits.
- **Undefined / nil / None**: concepts in some scripting languages; engine conversion may return `null`, a sentinel object, or throw an error.
- **Evaluation failure**: syntax error, runtime error, host interop error; `ScriptException` is the common reporting channel, though implementations may have other wrappers/native exceptions.
- **Timeout/cancellation**: actively managed by the application, **not a mandatory variant of null or ScriptException**.

Never use `raw == null` to conclude "the script did not find the variable" or "the engine timed out." Use a dedicated response envelope or app-level status, such as `SUCCESS(value)`, `SCRIPT_ERROR`, `TIMEOUT`, `CANCELLED`, `ENGINE_UNAVAILABLE`. For security, keep host stack traces and secrets out of caller-facing messages.

## 6. Stopping Mechanisms: ScriptEngine Has No Standard Stop API

`ScriptEngine` defines `eval`, `put/get`, `getContext`, `setBindings`, `createBindings`, and `getFactory`. **There is no standard method**:

```text
engine.stop()
engine.interrupt()
engine.terminate()
engine.close()    // not part of the javax.script.ScriptEngine interface
```

These are **fictitious names illustrating nonexistent APIs**; never call them in real Java code. Some vendors offer proprietary APIs to cancel/close contexts, set instruction limits, or enforce timeouts; read the contract for that specific vendor and version.

Distinguish clearly:

| Action | What Is Actually Guaranteed | What Is Not Guaranteed |
| --- | --- | --- |
| `Future.get(timeout, unit)` | Caller thread waits until deadline and receives `TimeoutException` | That the script worker stops on its own |
| `Future.cancel(true)` | If cancellation succeeds, marks the future cancelled and requests interrupting the running thread if applicable | That the engine/script respects interruption |
| `Thread.interrupt()` | Sets the interrupt flag, which may cause interruptible blocking methods to throw `InterruptedException` | That an interpreter/native call/CPU loop will exit |
| `ExecutorService.shutdownNow()` | Attempts to interrupt running tasks and returns unstarted tasks | Guaranteed termination of all running tasks |
| **Engine-specific** cancel/close API | Behavior per vendor documentation | Portability across engines |
| Isolation via **separate process/container** | Host can terminate the process and reclaim resources at the OS boundary | That partial script work rolls back external side effects automatically |

**Never use `Thread.stop()` to forcefully kill a script.** It is unsafe, can leave locks and objects in corrupted states, and does not undo external side effects. Inside a shared JVM, there is no universal "safely kill script thread" operation across all engines.

### A Timeout Pattern That Only Limits Caller Wait Time

```java
Future<Object> future = executor.submit(
    () -> engine.eval(scriptText, requestBindings));
try {
    return future.get(250, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true);  // requests interrupt, does NOT guarantee the script stops
    throw new IllegalStateException("Script exceeded deadline", timeout);
}
```

This is a **snippet inside a method returning `Object`**, requiring configured `ExecutorService executor`, `ScriptEngine engine`, `String scriptText`, and `Bindings requestBindings`. Import `java.util.concurrent.*` and handle `InterruptedException`/`ExecutionException` in the enclosing method. If the worker is uncooperative, the `Future` may be marked cancelled while the task keeps running. Never return that engine or thread to a pool for reuse as if it were clean.

### Soft Stop vs. Hard Stop

**Soft stop (cooperative cancellation):** the script engine or script code periodically checks `interrupt` or a cancellation token; when exit is requested, it throws or returns a termination status. Works well for custom DSLs or engines with documented cancellation hooks. Must be empirically tested against CPU loops, blocking I/O, host callbacks, and each engine version.

**Hard stop (isolation boundary):** for untrusted scripts or strict deadlines, run the engine in a **separate process** with CPU/RAM/time quotas and restricted access rights. On expiration, the host terminates the process per policy; this avoids depending on whether a Java thread exits voluntarily. You must still design idempotency/transactions for filesystem, database, and network calls if scripts can produce side effects.

Key decision: **request timeout ≠ engine stopped**. The system must observe actual task completion, manage hung workers, bound concurrent workers, and clean up across the lifecycle.

## 7. Standalone Java 17 Example: Self-Registered Engine, Type Validation, Cooperative Cancellation

To run on **plain JDK 17**, do not assume a JavaScript engine exists. We write a tiny **DemoDSL** (not JavaScript, not a full interpreter) using `javax.script` directly:

- `DemoFactory` publishes language/engine metadata and registers alias `demo-dsl` in a `ScriptEngineManager`.
- `DemoEngine extends AbstractScriptEngine` understands exactly two commands: `add` and `wait`; `add` reads two `BigDecimal` values from Bindings and returns `BigDecimal` so the caller validates the type.
- `wait` exists solely to demonstrate **cooperative interruption**: it calls `Thread.sleep` and throws `ScriptException` when interrupted. This is **not the default behavior of every engine**.
- `THREADING=null` declares the demo engine is not thread-safe. The program executes `add` on `main` before the `wait` task begins; it never runs two `eval` calls concurrently.

### 7.1. ScriptBoundaryDemo.java

```java
import java.io.IOException;
import java.io.Reader;
import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class ScriptBoundaryDemo {
    static final class DemoFactory implements ScriptEngineFactory {
        public String getEngineName() { return "Controlled Demo DSL"; }
        public String getEngineVersion() { return "1"; }
        public List<String> getExtensions() { return List.of("demo"); }
        public List<String> getMimeTypes() { return List.of("text/x-demo"); }
        public List<String> getNames() { return List.of("demo-dsl"); }
        public String getLanguageName() { return "DemoDSL"; }
        public String getLanguageVersion() { return "1"; }

        public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> getNames().get(0);
                case "THREADING" -> null;
                default -> null;
            };
        }

        public String getMethodCallSyntax(String obj, String method, String... args) {
            throw new UnsupportedOperationException("No method calls in DemoDSL");
        }
        public String getOutputStatement(String text) {
            throw new UnsupportedOperationException("No print statements in DemoDSL");
        }
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        public ScriptEngine getScriptEngine() { return new DemoEngine(this); }
    }

    static final class DemoEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        DemoEngine(ScriptEngineFactory factory) { this.factory = factory; }

        @Override
        public Object eval(String script, ScriptContext context) throws ScriptException {
            if ("add".equals(script)) {
                Object a = context.getAttribute("a");
                Object b = context.getAttribute("b");
                if (!(a instanceof BigDecimal left)
                        || !(b instanceof BigDecimal right)) {
                    throw new ScriptException("a and b must be BigDecimal");
                }
                return left.add(right);
            }
            if ("wait".equals(script)) {
                Object value = context.getAttribute("started");
                if (!(value instanceof CountDownLatch started)) {
                    throw new ScriptException("missing started latch");
                }
                started.countDown();
                try {
                    while (true) {
                        Thread.sleep(1000);
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new ScriptException("interrupted by host");
                }
            }
            throw new ScriptException("Unsupported DemoDSL command: " + script);
        }

        @Override
        public Object eval(Reader reader, ScriptContext context) throws ScriptException {
            StringBuilder text = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    text.append(buffer, 0, n);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(text.toString().trim(), context);
        }

        @Override
        public Bindings createBindings() { return new SimpleBindings(); }

        @Override
        public ScriptEngineFactory getFactory() { return factory; }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        manager.registerEngineName("demo-dsl", new DemoFactory());
        ScriptEngine engine = manager.getEngineByName("demo-dsl");
        if (engine == null) throw new IllegalStateException("Engine missing");

        Bindings input = engine.createBindings();
        input.put("a", new BigDecimal("0.1"));
        input.put("b", new BigDecimal("0.2"));
        Object result = engine.eval("add", input);
        if (!(result instanceof BigDecimal sum)) {
            throw new IllegalStateException("Unexpected result type");
        }
        System.out.println("engine=" + engine.getFactory().getEngineName());
        System.out.println("sum=" + sum.toPlainString());
        System.out.println("type=" + result.getClass().getSimpleName());
        System.out.println("threading=" + engine.getFactory().getParameter("THREADING"));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        Bindings waitInput = engine.createBindings();
        waitInput.put("started", started);
        try {
            Future<?> running = executor.submit(() -> engine.eval("wait", waitInput));
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Demo did not start");
            }
            System.out.println("cancelRequested=" + running.cancel(true));
        } finally {
            executor.shutdownNow();
        }
        System.out.println("workerStopped=" + executor.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

### 7.2. Compile and Output

From the directory containing `ScriptBoundaryDemo.java`, using JDK 17+:

```bash
javac --release 17 ScriptBoundaryDemo.java
java ScriptBoundaryDemo
```

**Stdout verified with `javac --release 17` and `java`:**

```text
engine=Controlled Demo DSL
sum=0.3
type=BigDecimal
threading=null
cancelRequested=true
workerStopped=true
```

### 7.3. What the Program Proves — and Does Not Prove

**Proven in the demo engine:**

1. `ScriptEngineManager.registerEngineName("demo-dsl", ...)` supplies a factory for the registered alias **within this manager**; we did not need to install a JavaScript engine.
2. `engine.createBindings()` and `engine.eval("add", input)` use the standard JSR-223 API.
3. The `add` command of **DemoDSL**, not a JavaScript expression, returns a `BigDecimal`; Java checks `instanceof` before using it.
4. `getFactory().getParameter("THREADING")` returns `null` per the metadata published by the demo itself: **do not share this engine for concurrent evals**.
5. `CountDownLatch` ensures the `wait` task has started before `cancel(true)`. `DemoEngine` actively responds to interruption in `Thread.sleep`; the worker genuinely exits afterward, so `awaitTermination` returns `true`.

**Must not be generalized:**

- Not every engine understands `add` or `wait`, returns `BigDecimal` output, or supports interruption.
- `cancelRequested=true` **alone** is not proof the script stopped; `workerStopped=true` is what confirms the **demo worker** terminated.
- The demo executes a single task and does not prove an engine is thread-safe or scales under multiple concurrent requests.
- `DemoDSL` handles only two test commands and is not a production language. Unused metadata methods in the example do not establish full grammar/semantics like a commercial engine.
- Never use this example itself as a sandbox for untrusted sources; it runs in the same JVM as the host.

## 8. Adapter Architecture When Supporting Multiple Script Engines

Recommended layered separation:

```text
Business API
  Input DTO / schema / deadline / tenantId
          |
          v
Script Execution Adapter
  - select pinned engine/version
  - validate types and permissions
  - create Bindings/context
  - translate request into engine-specific syntax
  - apply deadline/stop policy
          |
          v
ScriptEngine / provider runtime
  language-specific syntax & host interop
          |
          v
Adapter checks result + errors
  - normalize data
  - standardize status
  - release/retire resources
          |
          v
Business response DTO
```

Do not let business code scatter `eval("...")` calls and direct result casts everywhere. Instead, define a Java interface:

```java
public interface ScriptRunner {
    ScriptResult execute(ScriptRequest request);
}
```

This is a **contract snippet**; `ScriptRequest` and `ScriptResult` are application-defined DTOs/records, not built-in JDK types. One adapter per engine/version is responsible for compiling templates/script sources, validating inputs/outputs, enforcing runtime policies, and categorizing errors.

Example boundary error classification:

| Application Code | Condition | Handling |
| --- | --- | --- |
| `ENGINE_UNAVAILABLE` | Desired engine absent or wrong version | Fail fast at startup; never silently switch to another engine |
| `SYNTAX_ERROR` | Parser/compile/eval reports syntax error | Record script source and sanitized line/column |
| `INPUT_TYPE_ERROR` | Bindings missing a field or wrong type per schema | Return validation error before eval |
| `OUTPUT_TYPE_ERROR` | `eval` returns null/sentinel/proxy/unexpected type | Never cast blindly; reject or normalize per contract |
| `EXECUTION_ERROR` | Script/runtime/host callback failed | Wrap error with cause; protect secrets |
| `TIMEOUT` | Caller deadline expired | Issue cancel if supported; isolate/manage worker that may still be running |
| `CANCELLED` | Host policy actively stopped execution | Distinguish cancel request, cancel acknowledged, and actual termination |
| `RESOURCE_LIMIT` | Memory/CPU/IO quota exceeded in isolated environment | Terminate worker/process per policy |

These statuses are a **suggested application contract**, not enum constants defined by JSR-223.

### Lifetime Layering

- **Factory/metadata**: can be retained at registry scope after validation.
- **Engine instance**: lifetime per vendor docs; never assume a thread-safe singleton by default.
- **Bindings/ScriptContext**: ideally request-scoped for sensitive inputs; never allow host objects or user state to linger indefinitely.
- **CompiledScript**: bound to the engine/compiler version and class loader; cache with version/tenant-aware keys where appropriate.
- **Execution task**: explicit deadline; upon cancellation, verify termination and avoid reusing a worker still running an old script.
- **Plugin/class loader/engine context**: reclaim once no active executions remain; standard APIs do not automatically close all vendor-specific resources.

## 9. Minimum Tests Required When Replacing an Engine

To claim an application "supports multiple engines," test the **behavioral contract**, not just whether `getEngineByName` succeeds.

| Test Group | Critical Cases |
| --- | --- |
| Discovery | Missing engine, changed alias, missing dependency, differing class loader/TCCL |
| Syntax | Variables, functions, imports, literals, exceptions, async, unsupported syntax/version |
| Numeric types | Negative numbers, zero, very large integers, decimal `0.1 + 0.2`, NaN/Infinity, overflow/rounding |
| Nullability | Missing key, explicit null, undefined/nil/None, and engine sentinels |
| Strings | Unicode, escaping, control characters, normalization, empty string |
| Collections | Nested lists/maps, key order, mutable aliasing, proxies surviving after eval |
| Host interop | Java object exposure, method overloads, class access, callback exceptions |
| Context | Engine/global scope, engine reuse, multithreading, cross-request leakage |
| Stop | Timeout during sleep, tight CPU loop, blocking I/O, host callbacks, completion/cancel races |
| Cleanup | Lingering threads, executor queues, memory retention, external side effects, context/loader disposal |
| Portability | Same input DTO → same normalized output/error across supported engines |

**A timeout test that merely calls `future.get(timeout)` and observes `TimeoutException` is insufficient.** You must verify the worker actually stops consuming CPU and holding resources afterward, especially with infinite-loop scripts or native/host plugin callbacks.

## 10. Mistakes That Frequently Cause Production Incidents

### Mistake 1 — Assuming Java 17 Bundles JavaScript

`new ScriptEngineManager().getEngineByName("javascript")` can be `null` if the runtime lacks a provider. **Solution:** declare dependencies and class loader/module visibility explicitly; pin engine + language version; fail fast.

### Mistake 2 — Swapping Engines While Keeping the Same Script String

JSR-223 standardizes the `eval` method, not grammar. **Solution:** maintain per-language/version script adapters, test semantics, and establish a migration plan.

### Mistake 3 — Casting Directly After eval

`Integer result = (Integer) engine.eval("...")` can fail if the provider returns `Double`, `Long`, `BigDecimal`, or another wrapper. **Solution:** validate `Object` and normalize via DTOs. Never convert all numbers to `double` when exact IDs or monetary values are required.

### Mistake 4 — Conflating null, Missing, and Undefined

A `null` return value does not tell you whether the script ran cleanly or failed to find data. **Solution:** validate input schemas, use `containsKey` on Bindings, and use response envelopes with explicit status/nullability.

### Mistake 5 — Using a Singleton Engine for All Requests

If `THREADING=null`, concurrent `eval` violates the engine's supported model. Even `MULTITHREADED` may allow scripts to see shared state. **Solution:** scope engines/contexts properly and share only according to a documented contract.

### Mistake 6 — Treating cancel(true) as a Kill Switch

`Future.cancel(true)` only sends an interrupt signal; scripts can keep running if the engine does not cooperate. **Solution:** distinguish "request deadline exceeded," "cancellation requested," and "execution terminated"; use process isolation when hard limits are needed.

### Mistake 7 — Treating JSR-223 as a Sandbox

`ScriptEngine` imposes no boundaries on filesystem, network, class loading, or host object access. **Solution:** restrict APIs/host bindings using least privilege and run untrusted scripts outside privileged processes; enforce CPU/RAM/IO limits.

### Mistake 8 — Ignoring Lifecycle, Cleanup, and Side Effects

Vendor-specific engines can hold threads, contexts, caches, class loaders, or native resources. **Solution:** follow vendor close/cancel APIs when provided, close owned streams/readers, never reuse hung workers, and design transactions/idempotency for script side effects.

## 11. Pre-Deployment Design Checklist

- [ ] Specify an approved **engine implementation + version + language level**; do not rely on vague aliases.
- [ ] Verify the engine actually exists on the Java runtime; Java 17 does not include Nashorn by default.
- [ ] Use `eval` strictly as an invocation abstraction, never treating script syntax/libraries as portable.
- [ ] Check `Invocable`/`Compilable` before use; never assume every engine supports them.
- [ ] Define input/output schemas: nullability, numbers, BigDecimal, dates, collections, exceptions.
- [ ] Never cast `Object` results without validation; preserve exactness for IDs and financial values.
- [ ] Create per-request Bindings, check `THREADING` and isolation, and prevent engine state leaks.
- [ ] Establish clear deadline and cancellation policies; remember `get(timeout)` only bounds caller wait time.
- [ ] If uncooperative scripts must be stopped reliably, run them in an isolated process/container with quotas.
- [ ] Call vendor close/cleanup APIs per lifecycle; do not assume `ScriptEngine` has a standard `close`.
- [ ] Separate host/API privileges from script data; never run untrusted source in a privileged JVM.
- [ ] Test syntax/interop/timeout/cleanup against the **exact engine and version to be deployed**.

### Java 17 Primary Documentation

- [`ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [`ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [`ScriptEngineFactory` and `THREADING` metadata](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html)
- [`Bindings` and `ScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html)
- [JEP 372: Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372)
- [`Future.cancel` / `Future.get(timeout)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

**Remember:** `javax.script` lets Java call engines through a common API, but **script syntax, host-object conversion, and stop/cancel semantics belong to each individual engine**. To build a portable and safe system, pin versions, validate data into an explicit protocol, and choose termination policies matching code trust—never rely on a bare `eval` call or `Future.cancel(true)` as a substitute for those guarantees.