# Managing `ScriptEngine` State, Private `Bindings`, and Factory `THREADING` Metadata

In Java, the Java Scripting API (JSR 223, `java.scripting` module, `javax.script` package) lets an application execute scripting code through a common `ScriptEngine` interface. When integrating scripting into an application with multiple sessions, users, or threads, the challenge goes beyond calling `engine.eval(...)`: you must also **determine where state lives**, **which executions are allowed to see another execution's variables**, and **what concurrency guarantees the script engine provider makes**.

Three mechanisms must be understood:

1. **`ScriptEngine` and `ScriptContext`:** an engine object has a default context, scoped bindings, and potentially its own internal state managed by the implementation.
2. **`Bindings`:** a variable-name → value mapping. You can create a separate binding map per session/request and pass it to `eval(script, bindings)` or `eval(script, context)` instead of sharing the default `ENGINE_SCOPE`.
3. **`ScriptEngineFactory.getParameter("THREADING")`:** the **provider's** declaration regarding concurrent script execution and state isolation level. It is not a switch that magically makes Java thread-safe.

This lesson distinguishes the scopes, explains the exact four `THREADING` values, presents safe design patterns, and provides a runnable Java 17 program **without needing a third-party script engine**.

## 1. State Layers Often Confused with Each Other

An engine may appear in a system following this model:

```text
ScriptEngineManager
  |-- Registry of ScriptEngineFactory instances
  |-- Manager's GLOBAL_SCOPE Bindings
  |
  +-- creates ScriptEngine #1
  |      |-- Default ScriptContext
  |      |      |-- ENGINE_SCOPE Bindings
  |      |      +-- GLOBAL_SCOPE Bindings (may be shared from manager)
  |      |
  |      +-- internal engine/provider state (if any)
  |
  +-- creates ScriptEngine #2
         |-- Different default ScriptContext
         |      |-- Different ENGINE_SCOPE Bindings
         |      +-- GLOBAL_SCOPE may be the same manager object
         |
         +-- separate or shared internal state depending on implementation
```

**State visible in `Bindings` is not always the entirety of the scripting runtime's state.** An implementation may maintain an execution environment, compiled caches, objects/prototypes, callbacks, native resources, or data stored in private variables outside `Bindings`. Swapping a `Bindings` map can isolate variable names mapped through scopes, but **does not automatically guarantee resetting the entire runtime**.

Therefore, clearly identify your requirement:

- Need **each invocation to have its own variable set**? Use separate `Bindings` or `ScriptContext`.
- Need **each user/tenant to have an independent runtime**? Typically create separate engines and avoid sharing the global context, while verifying the actual implementation.
- Need **multiple threads to use the same engine**? Check `THREADING` and state/concurrency boundaries; never infer safety from sample code running once.
- Need **to execute untrusted code**? `ScriptEngine` is not a sandbox; consider process/permission/resource isolation as appropriate.

## 2. The Two `ScriptContext` Scopes: `ENGINE_SCOPE` and `GLOBAL_SCOPE`

`ScriptContext` defines the scopes in which an engine looks up attributes and where I/O streams are routed. With `SimpleScriptContext`, the two standard scopes are:

| Scope | Constant | Meaning |
|---|---|---|
| Engine | `ScriptContext.ENGINE_SCOPE` | Variables attached to the engine's execution context or to a specific run supplied with a distinct `Bindings` |
| Global | `ScriptContext.GLOBAL_SCOPE` | Default/wider-scope variables, commonly shared across engines created by the same `ScriptEngineManager` |

When looking up attributes in the default scope order, **`ENGINE_SCOPE` is searched before `GLOBAL_SCOPE`**. If both contain the key `"region"`, the value in `ENGINE_SCOPE` shadows the global value within that context.

Common APIs:

```java
engine.put("user", "Alice");
Object value = engine.get("user");

Bindings local = engine.getBindings(ScriptContext.ENGINE_SCOPE);
Bindings global = engine.getBindings(ScriptContext.GLOBAL_SCOPE);
```

These are **illustrative expressions**, assuming an `engine` variable exists. `engine.put/get` operates on the **default context's ENGINE_SCOPE**. Do not confuse `engine.get("key")` with `engine.getContext().getAttribute("key")`: the latter searches across scopes following `ScriptContext` rules.

If the same engine processes two users via:

```java
// Illustrates sharing ENGINE_SCOPE, not a user isolation policy.
engine.put("user", "Alice");
engine.eval("someScript");
engine.put("user", "Bob");
engine.eval("someScript");
```

then `ENGINE_SCOPE` state is mutated sequentially. On a subsequent execution, the name `"user"` may hold another user's value. In asynchronous environments, race conditions can also occur. Using separate `Bindings` resolves a major part of the shared variable-name issue.

### Is `GLOBAL_SCOPE` Really Private to Each Engine?

Not always. When using `ScriptEngineManager`, the manager maintains a global `Bindings` set and **attaches this object as `GLOBAL_SCOPE` to the engines it creates**. Thus, even when each engine has its own `ENGINE_SCOPE`, they can still see keys in the manager's global bindings.

Conceptual example:

```java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("region", "APAC"); // Belongs to the manager's GLOBAL_SCOPE.
```

If two engines are created by the manager and receive the same `GLOBAL_SCOPE`, modifying a global value can affect both. This is why per-user or per-tenant secrets must not be placed into shared global bindings. Being named "global" does not make data immutable or thread-safe.

## 3. How Does `eval(script)` Differ from `eval(script, bindings)`?

This is the fundamental distinction for preventing state leakage.

**Calling without private bindings**:

```java
Object result = engine.eval(script);
```

The engine uses its **default context**. Variables assigned by the script into `ENGINE_SCOPE` may persist for subsequent calls (depending on language and implementation). Retaining variables across two `eval` calls is often used intentionally for a single session, but is unsuitable when multiple tenants share an instance by default.

**Calling with private bindings**:

```java
Bindings alice = engine.createBindings();
Bindings bob = engine.createBindings();

Object one = engine.eval(script, alice);
Object two = engine.eval(script, bob);
```

`eval(String, Bindings)` uses `alice` or `bob` as the **ENGINE_SCOPE for that execution**. By the Java Scripting API contract, it **does not permanently replace the engine's default ENGINE_SCOPE**. With `AbstractScriptEngine`, the evaluation builds a temporary `SimpleScriptContext` whose `ENGINE_SCOPE` is the passed bindings while other parts—including `GLOBAL_SCOPE`—are taken from the default context.

Things to keep in mind:

- Variable changes written by the script to `alice` do not automatically appear in `bob`.
- `alice` itself can still retain modifications for **future runs of the same Alice session**, if you intentionally reuse that object.
- Swapping `Bindings` per call **does not prove the same engine can run concurrently** across multiple threads.
- If a mutable Java object is placed into both `alice` and `bob`, the two binding maps are distinct, yet **the inner object remains the exact same reference**.
- The script can still see `GLOBAL_SCOPE` and internal engine state. If strong isolation is needed, swapping `Bindings` alone is insufficient.

### `setBindings(...)` vs. `eval(..., bindings)`

```java
engine.setBindings(alice, ScriptContext.ENGINE_SCOPE);
```

This **replaces the engine's default ENGINE_SCOPE**. Subsequent `engine.eval(script)` calls will use `alice` until you change it again. It is **not equivalent** to passing `alice` for a single eval.

Avoid repeatedly calling `setBindings(...)` on an engine shared across concurrent requests: one request could swap the default context while another request is executing, corrupting data. Prefer `eval(script, requestBindings)` or `eval(script, requestContext)` on an engine that is not used concurrently in violation of the factory's contract.

## 4. `ScriptEngineFactory.getParameter("THREADING")`: Reading and Understanding It Correctly

`ScriptEngineFactory` describes the engine type, language name, version, and capabilities. Java defines **a reserved string key `"THREADING"`**, read via:

```java
Object threading = factory.getParameter("THREADING");
```

Do not write `ScriptEngine.THREADING`: `THREADING` here is **a string key passed to the factory**, not a standard constant of that name on the `ScriptEngine` interface.

According to the Java SE 17 API, the defined values are:

| `THREADING` | Documented Guarantee | Design Consequence |
|---|---|---|
| `null` | Engine implementation is **not thread-safe**; scripts must not execute concurrently on the same engine from multiple threads | Do not share one engine for parallel `eval`; use a dedicated engine per thread/request or enforce proper ownership/synchronization |
| `"MULTITHREADED"` | Engine can execute scripts concurrently; state mutations from one thread **may be visible** to another thread | Concurrency is advertised, but **variable isolation is not automatic** |
| `"THREAD-ISOLATED"` | Satisfies `MULTITHREADED` and maintains independent values for script symbols across different threads | Per-thread symbol isolation is promised by the implementation, yet shared objects, global bindings, and side effects still require management |
| `"STATELESS"` | Satisfies `THREAD-ISOLATED`; script execution **does not alter `ENGINE_SCOPE` `Bindings` mappings** before/after eval | This is a stronger guarantee about `ENGINE_SCOPE` mappings; **it does not mean code cannot mutate files, network, or mutable Java objects** |

Pay attention to points frequently misinterpreted:

1. `"MULTITHREADED"` **does not mean `"STATELESS"`**.
2. `"THREAD-ISOLATED"` refers to per-thread symbol values; it is not a license to share arbitrary `Map`, `List`, database connections, or mutable Java objects across threads.
3. `"STATELESS"` specifically states that `ENGINE_SCOPE` `Bindings` key/value mappings remain unchanged before and after the script; **it does not guarantee all side effects disappear**.
4. `null` means there is no thread-safety guarantee for the engine. You **must not** assume passing two separate `Bindings` automatically makes an engine thread-safe.
5. The factory only **advertises** the implementation's characteristics. In real deployments, read the provider docs, test against the exact version in use, and control concurrency at the application layer.

Most applications should **start by assuming engines are not shared for concurrent execution** unless proven otherwise. For multi-tenant workloads requiring strong isolation, even a per-tenant engine is not a sandbox; add appropriate security boundaries.

## 5. Engine Discovery and JDK 17 Constraints

`ScriptEngineManager` can locate factories via the service provider mechanism and create engines by name:

```java
ScriptEngineManager manager = new ScriptEngineManager();

for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName()
            + " threading=" + factory.getParameter("THREADING"));
}

ScriptEngine engine = manager.getEngineByName("some-engine-name");
if (engine == null) {
    throw new IllegalStateException("Script engine is not installed");
}
```

This snippet applies when the application already has a compatible provider installed. `getEngineFactories()` **may return an empty list**; never assume a JavaScript engine is always present just because the JDK includes `javax.script`. Nashorn was removed from the JDK starting in Java 15, so Java 17 does not bundle Nashorn like older versions did.

You can install a JSR 223-compatible third-party engine and register it via the service provider mechanism specified by the vendor. You can also **register a factory programmatically in Java** via:

```java
manager.registerEngineName("toy", factory);
```

In this illustrative snippet, `factory` is an already-constructed `ScriptEngineFactory`. Registering a name on the manager **does not turn the factory into a JS library**; the manager simply knows where to obtain an engine for the name `toy`.

So that the example in this lesson **runs reliably on a standard JDK 17**, the next section implements a *tiny script engine* supporting three commands: `set`, `get`, and `print`. It serves solely to observe scopes and APIs; **it is not JavaScript, not a production engine, and does not demonstrate safe multi-threaded execution**.

## 6. Complete Java 17 Program Without External Libraries

Create the file `ScriptingStateDemo.java`. The example builds `ToyFactory` and `ToyEngine` using standard `javax.script` interfaces/classes to illustrate:

- `ScriptEngineManager` and registering a factory by name.
- The default `ENGINE_SCOPE` when calling `eval(script)` or `engine.put(...)`.
- Two separate binding maps for two sessions via `eval(script, bindings)`.
- `GLOBAL_SCOPE` from the manager and value shadowing in `ENGINE_SCOPE`.
- A practical warning about `THREADING=null`.
- The difference between `setBindings(...)` and passing bindings for a single eval.

The code below **is a complete program**:

```java
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class ScriptingStateDemo {
    private static final class ToyFactory implements ScriptEngineFactory {
        @Override
        public String getEngineName() {
            return "Toy Scripting Engine";
        }

        @Override
        public String getEngineVersion() {
            return "1.0";
        }

        @Override
        public List<String> getExtensions() {
            return List.of("toy");
        }

        @Override
        public List<String> getMimeTypes() {
            return List.of("text/x-toy");
        }

        @Override
        public List<String> getNames() {
            return List.of("toy");
        }

        @Override
        public String getLanguageName() {
            return "ToyScript";
        }

        @Override
        public String getLanguageVersion() {
            return "1.0";
        }

        @Override
        public Object getParameter(String key) {
            return switch (key) {
                case "THREADING" -> null;
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> "toy";
                default -> null;
            };
        }

        @Override
        public String getMethodCallSyntax(
                String object, String method, String... args) {
            throw new UnsupportedOperationException(
                    "ToyScript does not support method calls");
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
            return new ToyEngine(this);
        }
    }

    private static final class ToyEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        ToyEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override
        public Object eval(String source, ScriptContext context)
                throws ScriptException {
            Object last = null;

            for (String raw : source.split("\\R")) {
                String command = raw.trim();
                if (command.isEmpty()) {
                    continue;
                }

                String[] parts = command.split(" ", 3);
                switch (parts[0]) {
                    case "set" -> {
                        if (parts.length != 3) {
                            throw new ScriptException("Usage: set name value");
                        }
                        context.setAttribute(
                                parts[1], parts[2], ScriptContext.ENGINE_SCOPE);
                        last = parts[2];
                    }
                    case "get" -> {
                        if (parts.length != 2) {
                            throw new ScriptException("Usage: get name");
                        }
                        last = context.getAttribute(parts[1]);
                    }
                    case "print" -> {
                        if (parts.length < 2) {
                            throw new ScriptException("Usage: print text");
                        }
                        try {
                            context.getWriter().write(
                                    command.substring("print ".length()));
                            context.getWriter().flush();
                        } catch (IOException ex) {
                            throw new ScriptException(ex);
                        }
                        last = null;
                    }
                    default -> throw new ScriptException(
                            "Unknown command: " + parts[0]);
                }
            }
            return last;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder text = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    text.append(buffer, 0, count);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(text.toString(), context);
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

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngineFactory factory = new ToyFactory();
        manager.registerEngineName("toy", factory);
        manager.put("region", "APAC");

        ScriptEngine engine = manager.getEngineByName("toy");
        if (engine == null) {
            throw new IllegalStateException("Toy engine not available");
        }

        System.out.println(
                "THREADING: " + engine.getFactory().getParameter("THREADING"));

        engine.eval("set user Root");
        System.out.println("Default user: " + engine.get("user"));

        Bindings alice = engine.createBindings();
        Bindings bob = engine.createBindings();
        engine.eval("set user Alice", alice);
        engine.eval("set user Bob", bob);

        System.out.println("A user: " + engine.eval("get user", alice));
        System.out.println("B user: " + engine.eval("get user", bob));
        System.out.println("Default after private eval: "
                + engine.eval("get user"));

        alice.put("region", "EU");
        System.out.println("A region: " + engine.eval("get region", alice));
        System.out.println("B region: " + engine.eval("get region", bob));

        ScriptEngine another = manager.getEngineByName("toy");
        System.out.println("Another default user: "
                + another.eval("get user"));
        System.out.println("Shared manager GLOBAL_SCOPE: "
                + (engine.getBindings(ScriptContext.GLOBAL_SCOPE)
                == another.getBindings(ScriptContext.GLOBAL_SCOPE)));

        engine.setBindings(alice, ScriptContext.ENGINE_SCOPE);
        System.out.println("Switched default user: "
                + engine.eval("get user"));
    }
}
```

### Compile and Run

Install **JDK 17 or newer** and navigate to the directory containing `ScriptingStateDemo.java`. The following two commands work in PowerShell, Bash, or a standard terminal:

```bash
javac --release 17 -encoding UTF-8 ScriptingStateDemo.java
java ScriptingStateDemo
```

`--release 17` instructs the compiler to emit Java 17-compatible bytecode. The program uses the standard `java.scripting` module in Java SE; in this classpath run mode, you do not need to create `module-info.java` or install an additional JavaScript implementation.

Expected stdout:

```text
THREADING: null
Default user: Root
A user: Alice
B user: Bob
Default after private eval: Root
A region: EU
B region: APAC
Another default user: null
Shared manager GLOBAL_SCOPE: true
Switched default user: Alice
```

This is **the output of `ToyEngine` written in the program**, not a universal default behavior across all JSR 223 engines. `ToyFactory` returns `null` for `"THREADING"` because it **does not claim it can run `eval` in parallel** on the same instance.

## 7. Analyzing Results and State After Each Step

### 7.1. An Engine Has Default State

The statement:

```java
engine.eval("set user Root");
```

sets `"user" = "Root"` in the default `ScriptContext`'s `ENGINE_SCOPE`. Therefore `engine.get("user")` returns `"Root"`.

If you simply use default `engine.eval(...)` calls for different users, they can share existing variables. This is a common form of *state leakage* when an engine is cached as a singleton.

### 7.2. Separate `Bindings` for Alice and Bob

```java
Bindings alice = engine.createBindings();
Bindings bob = engine.createBindings();

engine.eval("set user Alice", alice);
engine.eval("set user Bob", bob);
```

Each `Bindings` has its own map. The two corresponding `get user` commands return `Alice` and `Bob`. In the example, the `set` call mutates the passed request map, while the default `ENGINE_SCOPE` **remains `"Root"`**. Hence the program prints:

```text
Default after private eval: Root
```

If you want each session to preserve variables across multiple script executions, you can reuse `alice` for Alice's session; when the session ends, release the map and all no-longer-needed objects. **Do not share a single `Bindings` across two users** just because you called `createBindings()` twice elsewhere.

### 7.3. GLOBAL_SCOPE and Lookup Order

The manager called `manager.put("region", "APAC")`. Because the engines were created via the manager, their `GLOBAL_SCOPE` references the manager's global bindings.

- Since `bob` does not yet have `"region"`, `context.getAttribute("region")` falls back to `GLOBAL_SCOPE` and receives `"APAC"`.
- Since `alice.put("region", "EU")` sets `"region"` in Alice's `ENGINE_SCOPE`, it shadows the global value and returns `"EU"`.

Result:

```text
A region: EU
B region: APAC
```

Do not treat `alice.put("region","EU")` as changing the region for the whole application. It only updates Alice's map. Conversely, `manager.put("region",...)` changes shared data in the manager and can alter results across multiple engines.

### 7.4. New Engine and Changing Default Bindings

`another` is created from the same manager but is a **new instance** of `ToyEngine`; it has not set key `"user"` in its `ENGINE_SCOPE`, so `get user` returns `null`. Nevertheless, it still sees the same global map from the manager; the reference comparison in the example prints `true`.

Afterward:

```java
engine.setBindings(alice, ScriptContext.ENGINE_SCOPE);
```

installs Alice's map as the first engine's default `ENGINE_SCOPE`. Consequently, `engine.eval("get user")` (without passing bindings) returns `Alice`.

In the program, steps run sequentially with no concurrent requests. **Correct output does not prove `ToyEngine` is thread-safe**; the factory metadata remains `null`.

## 8. Separate `ScriptContext` When Per-Call Input/Output Isolation Is Needed

`eval(script, bindings)` is convenient when only `ENGINE_SCOPE` differs; it still uses the `Reader`/`Writer` and scopes outside `ENGINE_SCOPE` from the default context per `AbstractScriptEngine`'s contract. When each execution needs a **different writer, error writer, or global map**, create a dedicated `ScriptContext`.

Standalone illustrative example of configuring a context:

```java
import java.io.StringWriter;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

static Object runWithContext(ScriptEngine engine, String script)
        throws javax.script.ScriptException {
    SimpleScriptContext context = new SimpleScriptContext();
    Bindings local = engine.createBindings();
    local.put("requestId", "request-001");
    context.setBindings(local, ScriptContext.ENGINE_SCOPE);

    Bindings safeGlobals = new SimpleBindings();
    safeGlobals.put("locale", "en");
    context.setBindings(safeGlobals, ScriptContext.GLOBAL_SCOPE);

    StringWriter output = new StringWriter();
    context.setWriter(output);

    Object result = engine.eval(script, context);
    return result;
}
```

This is an **illustrative method snippet** to place inside a class; it is not a standalone program and is not called from `main` in section 6. If you want to read script output, return both `result` and `output.toString()` via a dedicated result type. With a real engine, also configure `setErrorWriter(...)` and `setReader(...)` if scripts use those channels.

**Note:** `eval(script, context)` can isolate scopes and I/O per invocation, yet with `THREADING=null` you still **must not run multiple concurrent calls on the same engine**. Nor do `SimpleBindings` and `SimpleScriptContext` make the Java objects inside them immutable or thread-safe.

## 9. Designing Engine Lifecycle in a Server Application

You can choose among three organizational patterns:

| Strategy | Advantages | What Must Be Controlled |
|---|---|---|
| Fresh engine per request | Limits state sharing across requests; compatible with non-thread-safe providers since instances are not shared | Initialization cost, internal resources; `GLOBAL_SCOPE` may still be shared if using one manager |
| Dedicated engine per session/tenant | Supports scripts that retain state across turns; reduces per-request startup overhead | Only one thread uses each engine at a time if `THREADING` forbids concurrency; quotas, timeouts, cleanup, tenant controls |
| Engine pool with exclusive checkout | Reuses engines without parallel execution on the same instance | Reset all state per provider specification; never return a dirty engine to the pool; prevent leftover user data |

Risky pool example: merely calling `setBindings(new SimpleBindings(), ENGINE_SCOPE)` **does not prove the engine is clean**, because the implementation may hold additional state inside the engine, globals, or retained script objects. Without a reliable reset API, a fresh engine is usually safer for isolation.

An approach that intentionally grants **exclusive ownership per request**:

```text
Incoming request
    |
    v
Create/acquire an engine with exclusive ownership
    |
    v
Create private Bindings (or private Context)
    |
    v
eval(...) and handle result / ScriptException
    |
    v
Clean state, return to pool if reset is guaranteed
or discard the engine and create a fresh one next time
```

With a provider declaring `THREADING="MULTITHREADED"`, you **can** design a shared engine with concurrent `eval` per the provider's guarantee, yet you must still protect shared mutable maps/objects and define user-separation logic. *Engine-execution thread safety* does not mean *data tenant safety*.

## 10. Check `THREADING` Before Choosing a Policy

In a program using a real factory, you can inspect metadata:

```java
ScriptEngineFactory factory = engine.getFactory();
Object value = factory.getParameter("THREADING");

if (value == null) {
    // Conservative policy: do not use the same engine for parallel eval.
} else if ("MULTITHREADED".equals(value)) {
    // Provider advertises concurrent eval support; state may be shared.
} else if ("THREAD-ISOLATED".equals(value)) {
    // Additional guarantee of per-thread isolated symbols.
} else if ("STATELESS".equals(value)) {
    // Additional guarantee that ENGINE_SCOPE mappings are unchanged by eval.
} else {
    // Non-standard parameter value: check provider docs or fail closed.
}
```

This is an **illustrative logic snippet**, not a standalone program; `engine` must come from an installed factory.

There is no need to cast `Object` to `String` before comparing: `"MULTITHREADED".equals(value)` is both null-safe and semantically clear. If you log non-standard values, log them without exposing sensitive internal engine attributes.

### Things Metadata Does Not Tell You Automatically

- How many engines are created and who owns them.
- Whether the provider stores state in auxiliary objects outside bindings.
- Whether a Java object received by a script is thread-safe or referenced by another tenant.
- Which sensitive APIs a script can access when the engine uses its own Java class loader.
- How long a script runs, whether it times out, or whether it blocks indefinitely.

You must supplement it with provider documentation, integration tests, and real operational boundaries.

## 11. Do Not Confuse Concurrency Safety with Security Isolation

A `ScriptEngine` described as `"STATELESS"` does not mean you can run untrusted scripts inside the server JVM without restricting permissions. Even a `Bindings` whose mappings are never altered can still contain mutable `List`, `Map`, `Connection`, `File`, or callback objects; a script can invoke methods that mutate **the object's own state**, files, network, or external systems.

Practical principles:

1. **Never place secrets or User A's data in global bindings visible to all users.**
2. **Never share uncontrolled mutable objects across private bindings.** Separate maps are not a deep copy.
3. **Classify script sources and dependencies:** only run in-JVM if scripts are sufficiently trusted. For untrusted scripts, use proper process isolation.
4. **Enforce resource limits:** CPU, wall-clock time, heap, input size, context/engine counts. The Java Scripting API does not impose timeouts or quotas automatically.
5. **Manage context I/O:** writers can contain sensitive data and must be configured and reclaimed per session rather than using a global writer.
6. **Do not automatically retry scripts with side effects:** if a script already wrote external data and failed late, re-running may duplicate writes.
7. **Observability:** log engine name, version, threading metadata, sanitized request ID, and execution duration; do not log full scripts or all bindings if they contain sensitive data.

## 12. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | How to Verify and Fix |
|---|---|---|
| Request B reads variables from Request A | Shared default `ENGINE_SCOPE` or reusing a binding map across wrong sessions | Pass per-request `Bindings`/`ScriptContext` and bound lifetimes |
| After `engine.eval(script, b)`, `engine.get("x")` does not see value in `b` | `eval(..., b)` only uses `b` as `ENGINE_SCOPE` for that eval, **does not replace default** | Read `b.get("x")` or `eval("get x", b)` |
| Two engines still see shared variables | `GLOBAL_SCOPE` comes from the same manager, or a mutable object is shared | Separate managers/contexts/global maps along tenant boundaries |
| Private `Bindings` used, yet multi-threaded shared engine still fails | `THREADING=null` or implementation has internal state | Do not run parallel `eval` on the engine; use separate instances or exclusive ownership |
| Assuming `"MULTITHREADED"` means no state leakage | This value allows thread effects to be visible to one another | Add data-isolation policies; consider separate engines/contexts |
| Assuming `"STATELESS"` forbids all side effects | The guarantee applies only to `ENGINE_SCOPE` mappings | Restrict objects and resources accessible to scripts |
| `getEngineByName("JavaScript")` returns `null` on Java 17 | No provider installed or visible to the class loader | Inspect `getEngineFactories()` and install a compatible engine |
| Script runs, but `ScriptException` on other code | Differences in provider language syntax/runtime and engine policies | Log controlled diagnostics; check source and libraries |
| `setBindings` overwrites default variables | Directly replaces default scope rather than a temporary override | Use `eval(script, bindings)` or `eval(script, context)` |
| Pooled engine leaks old user's data to a new user | Internal and global state were not completely reset | Discard instance or execute a provider-verified reset procedure |
| `Bindings` entries look isolated, yet script mutates inner object | Distinct maps hold a shared object reference | Pass immutable data, controlled DTOs, or appropriate copies |

## 13. Design Checklist for Integrating Scripting

Before using JSR 223 in a multi-session application:

- **Discovery:** do you know which engines are installed, their actual names and versions via `ScriptEngineFactory`?
- **THREADING:** have you read `factory.getParameter("THREADING")` and selected a matching concurrency policy?
- **Ownership:** does an engine belong to a request, session, pool, or singleton? Who is allowed to call `eval` and when?
- **Scopes:** which map is `ENGINE_SCOPE`? Is there a `GLOBAL_SCOPE` from the manager visible to multiple requests?
- **Isolation:** does each user/tenant have separate Bindings or context, and could objects inside maps be unintentionally shared?
- **Lifecycle:** is there a policy to clear state, clean caches/writers/callbacks, and avoid retaining instances used by another user?
- **Failure:** are syntax/runtime errors caught as `ScriptException` and routed properly without leaking data?
- **Security:** are scripts trusted? Is process isolation required instead of merely creating multiple ScriptEngines?
- **Testing:** have you tested Alice → Bob → Alice sequentially, multiple engines from the same manager, global shadowing, and concurrency per the provider's guarantee?

## 14. Reinforcement Exercises

1. **Session persistence:** use the same `Bindings alice` to run `set user Alice` and then `get user` across multiple turns; create a new `Bindings bob` and verify Bob does not see `"Alice"`.
2. **Explore shadowing:** put `"region" = "APAC"` in the manager, then put `"region" = "EU"` in `alice`. Remove key `"region"` from `alice` and explain why the next read falls back to global.
3. **Test a private context:** add a `SimpleScriptContext` with a `StringWriter` and an independent global map. Have ToyScript run `print Hello`, verify the writer contains exactly `"Hello"`, and verify other contexts are unchanged.
4. **Test replacing default:** after `engine.setBindings(alice, ENGINE_SCOPE)`, run `engine.eval("get user")`; explain why Alice is now visible even without passing bindings.
5. **Analyze factory metadata:** suppose three providers report `null`, `"MULTITHREADED"`, and `"STATELESS"` respectively. Draft an appropriate concurrency and state-isolation plan for each; point out what still needs protection even when a provider reports `"STATELESS"`.
6. **Risk of separate maps but shared object:** put the same `ArrayList` into two different bindings maps. Explain why mutating the list from one side still affects the other side.
7. **Real engine integration:** when a project has a JSR 223 engine installed, list `ScriptEngineManager.getEngineFactories()`, print `getEngineName()`, `getEngineVersion()`, and `getParameter("THREADING")`. Only run scripts when a compatible provider is actually present.

## 15. Core Summary

**`ScriptEngine` manages the execution environment; `Bindings` manages name–value mappings within each scope; `ScriptContext` defines scopes and I/O for an execution; `ScriptEngineFactory` advertises provider capabilities.**

With `eval(script, bindings)`, you can isolate `ENGINE_SCOPE` per call without altering default bindings. However, **variable isolation is not thread safety**, and **thread safety does not automatically provide user isolation**. Always inspect `"THREADING"`, explicitly define engine ownership, and manage `GLOBAL_SCOPE` and internal state to prevent data leaks.

### Standard Documentation

- [Java SE 17 — ScriptEngineFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): semantics of the `THREADING` key.
- [Java SE 17 — ScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, `put/get`, `setBindings`.
- [Java SE 17 — AbstractScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): how temporary contexts are constructed for `eval(script, bindings)`.
- [Java SE 17 — ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): discovery, factories, and global bindings.