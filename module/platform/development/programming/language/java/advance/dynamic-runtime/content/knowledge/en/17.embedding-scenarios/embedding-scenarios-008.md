# 17.8 Controlling Exposed Java Objects and Limiting Engine Sharing Across Threads

In a Java application that embeds scripts via `javax.script` (JSR-223), the hard part is not only writing `engine.eval(source)` but also **controlling the permissions that a script receives when touching Java objects** and **preventing the engine/state of one request from affecting another request**. Simply providing a high-privilege repository, HTTP client, or service to the script can open up many actions beyond business requirements. If an engine is shared across multiple threads or tenants, variables and object references can also be shared unintentionally.

Two main decisions:

1. **Host access/capability:** what objects are put into `Bindings`, which methods can be called, which data/identity is allowed to be seen, and whether reflection/class loading, file/network/process/thread APIs, and resource abuse are blocked?
2. **Concurrency/state:** `ScriptEngineFactory.getParameter("THREADING")` indicates whether the engine can execute concurrently; whereas whether `ScriptContext`/`Bindings`/Java objects are shared is an independent condition.

**Safe default to start with:** a separate engine and context per request, providing only a minimal **capability facade**, removing manager-global secrets, checking provider-specific host policy; for truly untrusted scripts, consider **process isolation and quotas**. `Bindings` is not a security sandbox; `synchronized` only limits races, it does not clear state or restrict permissions.

## 1. Risk model and trust boundaries

| Scenario | Risk | Control |
| --- | --- | --- |
| Script is given `DataSource`/`EntityManager` | Can access data out of scope | Do not provide infrastructure objects; provide a facade that only returns authorized data |
| Providing `HttpServletRequest`, session, or security context | Leaks tokens/headers/tenant identity | Create a small DTO containing only allowed fields; host authenticates identity itself |
| Enabling broad Java class lookup | Reflection/`Runtime`/`ProcessBuilder`/file/network | Provider's host class lookup/host member access policy; OS permissions |
| Multiple requests use `engine.put("token", ...)` | Data persists across subsequent evals, cross-tenant leak | Dedicated request bindings/context, dedicated engine lifecycle |
| `THREADING=null` yet concurrent eval on same engine | Race/interpreter state corruption | One engine per worker/request or exclusive lock |
| Engine reports `MULTITHREADED` | Can still share global script state | Control scopes, globals, and mutable Java objects |
| `Future.cancel(true)` when script runs forever | Interrupt may not terminate runtime | Reliable provider cancellation; OS process isolation |
| Engine pool returns unreset instance to new tenant | Closures, caches, imported modules, or callbacks retain old permissions | Comprehensive provider-specific reset; otherwise, discard engine |

**Script classification:** trusted (reviewed/same privileges as application), semi-trusted (tenant admin or external config that may be faulty), untrusted (arbitrary input). Each group needs corresponding policies and isolation levels. A script called “trusted” still needs race and resource-limit testing. An untrusted script does **not** automatically become safe just because we only pass in a small `Map`.

## 2. Differences between ScriptEngineManager, ScriptEngine, ScriptContext, and Bindings

~~~text
ScriptEngineManager
   |
   +-- discovers ScriptEngineFactory (ServiceLoader)
   +-- manager GLOBAL_SCOPE Bindings
   |
   +-- getEngineByName(...) -> ScriptEngine instance
                                   |
                         default ScriptContext
                          ENGINE_SCOPE + GLOBAL_SCOPE
                                   |
                  eval(script, requestContext) --- dedicated ScriptContext
                                              |
                                    ENGINE_SCOPE Bindings
                                    GLOBAL_SCOPE Bindings (optional)
                                              |
                                      host Java objects
~~~

| Component | Contract | Common misconception |
| --- | --- | --- |
| `ScriptEngineManager` | Discovers factories, creates engines, has **global Bindings** | Is not itself an engine pool or isolation layer |
| `ScriptEngineFactory` | Engine metadata, creates `ScriptEngine` | `"THREADING"` describes engine-level concurrency |
| `ScriptEngine` | Interpreter with default context and internal state | Not necessarily thread-safe; state may persist across evals |
| `ScriptContext` | Scoped attributes, Reader/Writer/ErrorWriter for the run | Dedicated context does not guarantee dedicated interpreter internals |
| `Bindings` | Map `String` → `Object` | Holds references to Java objects, does not deep copy |
| `CompiledScript` / `Invocable` | Optional features to compile/invoke code | May hold references to engine and state, not cross-thread safe by default |
| Host facade | Object exposed via engine interop | Few methods do not automatically prevent reflection/class loading paths if provider allows |

In Java 17, the `java.scripting` module has the JSR-223 API, **but does not necessarily have a JavaScript engine**. Nashorn was removed from the JDK since **Java 15**; therefore `new ScriptEngineManager().getEngineByName("JavaScript")` may be `null` if no engine provider has been added.

## 3. Distinguishing ENGINE_SCOPE and GLOBAL_SCOPE

`ScriptContext.ENGINE_SCOPE` has code `100` and is searched **before** `ScriptContext.GLOBAL_SCOPE` which has code `200`. A newly created `SimpleScriptContext` has default ENGINE_SCOPE bindings and default GLOBAL_SCOPE `null`.

~~~java
ScriptContext ctx = new SimpleScriptContext();

Bindings local = new SimpleBindings();
local.put("tenant", "A");
ctx.setBindings(local, ScriptContext.ENGINE_SCOPE);

Bindings global = new SimpleBindings();
global.put("tenant", "fallback");
global.put("shared", "common");
ctx.setBindings(global, ScriptContext.GLOBAL_SCOPE);

System.out.println(ctx.getAttribute("tenant")); // A
System.out.println(ctx.getAttribute("shared")); // common
~~~

This is an **illustrative in-method snippet** with `import javax.script.*;`, not a standalone runnable Java file. Values are looked up in scope order. However, the concept of “the script sees the variable name `tenant`” also depends on how the provider exposes attributes to its language.

Three similar APIs:

- `engine.put("api", object)` modifies the ENGINE_SCOPE bindings of the **default context on the engine**. This data may persist across multiple `eval(script)` calls.
- `engine.eval(script, bindings)` uses `bindings` as ENGINE_SCOPE for **that evaluation** per JSR-223; it does not prove the interpreter clears state from the previous script.
- `engine.eval(script, ctx)` uses a caller-provided `ScriptContext`, including scopes and I/O. It may still use the **same engine internals** if the caller keeps the engine long-lived.

**Do not use `ScriptEngineManager.put` to store tokens/tenant IDs:** manager-global bindings are attached to engines created by the manager and can be exposed to all of their scripts.

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("sharedConfig", "non-secret"); // Public, truly shared only.
~~~

This snippet only illustrates a safe value to share. Replacing `"non-secret"` with credentials or a tenant's identity is a flawed design.

### A separate Context is not enough to “clear”

An engine can maintain global variables, compiled procedures, module caches, closures, or objects held by a previous eval. If the provider does not guarantee context-level isolation, swapping `SimpleBindings` does not guarantee request B cannot access remaining state from A. If strong guarantees are needed, instantiate a new engine per request or use a dedicated provider-specific Context.

## 4. A host object is a capability, not just a “value”

The following example is **illustrative code of what not to do** for untrusted scripts:

~~~java
bindings.put("db", dataSource);
bindings.put("request", servletRequest);
bindings.put("runtime", Runtime.getRuntime());
bindings.put("loader", classLoader);
bindings.put("service", applicationService);
~~~

The variables `bindings`/`dataSource`/`servletRequest`/... are assumed to exist to illustrate the risk, not as a standalone program. With a provider that has broad Java interoperability, scripts can call methods on those objects and gain capabilities beyond requirements.

Replace with a facade:

~~~java
public final class GreetingView {
    private final String prefix;
    public GreetingView(String prefix) { this.prefix = prefix; }
    public String hello(String name) { return prefix + name; }
}
~~~

The facade above only allows string concatenation, without directly granting DB, network, or filesystem access. However, **a small facade is not a sandbox**: if the provider enables overly broad reflection/class lookup, an object can open a path to `Object.getClass()` or other Java classes. A **host member access policy** and testing with the real engine are required. For simple values, a `String`/`int`/immutable DTO is sometimes better than passing any service object into the script.

### Object checklist before binding

1. **Which methods** does the script actually need to call? Reduce the API surface to the minimum.
2. Does the method already check **authorization/tenant boundary** on the Java side, or does it let the script specify the tenant ID itself?
3. Does the object hold a `ClassLoader`, file path, HTTP client, DB transaction, credentials, capture callbacks, or a logger that allows writing sensitive data?
4. Is a mutable object shared across other threads? `final` on a field does not make the inner object thread-safe.
5. If passing a `Map`/`List`, is allowed data copied and size/depth limited?
6. Does the engine interop allow calling `getClass`, reflection, `Java.type`, constructors, or loading host classes?
7. Is there a mechanism to block scripts from calling file/network/process/thread/native APIs?
8. Are script results going into SQL/HTML/URL/command further validated/escaped properly for the sink?

A `getBalance()` method on a facade can **still be dangerous** if it reads the balance of any arbitrary account without checking permissions. “Read-only” only means not writing data, it does **not** mean data cannot be leaked.

## 5. JSR-223 does not define a universal sandbox: a provider policy is required

JSR-223 manages evaluation/bindings/contexts, but **does not standardize** a host-access policy applicable to all interpreters. Each provider (GraalJS, standalone Nashorn, Groovy, or other engines) has its own rules. Do not rely on removing the variable name `"Runtime"` from Bindings to assert that a script cannot find the Java class through another path.

Example of **GraalJS Polyglot Context** (not part of pure JDK 17; the illustrative snippet requires the `org.graalvm.polyglot` dependency):

~~~java
// Provider-specific, requires GraalJS and corresponding dependencies.
try (org.graalvm.polyglot.Context ctx =
        org.graalvm.polyglot.Context.newBuilder("js")
            .allowHostAccess(org.graalvm.polyglot.HostAccess.EXPLICIT)
            .allowHostClassLookup(name -> false)
            .build()) {
    ctx.getBindings("js").putMember("api", exportedFacade);
    ctx.eval("js", "/* approved source */");
}
~~~

`HostAccess.EXPLICIT` only exposes members matching the policy such as `@HostAccess.Export`; `allowHostClassLookup(name -> false)` restricts the ability to look up host classes through that API. However, **this is not a complete sandbox**: there are also IO/native/threads/network/resource limits policies and features compatible with the provider version. For untrusted scripts, consider process isolation. Do not enable `HostAccess.ALL`, `allowHostClassLookup(name -> true)`, or equivalents just to make an example run quickly.

GraalJS has a JSR-223 engine wrapper in appropriate configurations. Some host-access options can be set via `Bindings` **before the engine context initializes**; calling `eval` or interacting with bindings may initialize the context early, so configuration order matters. GraalVM currently recommends using Polyglot `Context` directly for finer-grained control.

### Security Manager is not a platform choice

`System.setSecurityManager`/Java Security Manager has been deprecated for removal since Java 17 (JEP 411) and continues to be restricted on later JDKs. Do not design a new script sandbox relying on “enabling SecurityManager” to rescue an engine with broad host interop.

## 6. Checking `THREADING` with ScriptEngineFactory

The reserved parameter `"THREADING"` is meaningful in **`ScriptEngineFactory.getParameter(String)`**. Do not write `ScriptEngine.THREADING` because JSR-223 does not define that constant.

~~~java
ScriptEngineFactory factory = engine.getFactory();
Object threading = factory.getParameter("THREADING");
System.out.println("THREADING = " + threading);
~~~

The snippet requires an already-created `engine` variable and `import javax.script.*`. According to the Java SE 17 Javadoc:

| Value from factory | Contract | Decision |
| --- | --- | --- |
| `null` | Engine is **not thread-safe**, cannot execute scripts concurrently using the same instance | Do not call `eval` concurrently on that engine |
| `"MULTITHREADED"` | Internal implementation is thread-safe, concurrent scripts can run; **effects of one thread may be visible in another thread** | Concurrency at the interpreter level is possible, but globals/objects still need management |
| `"THREAD-ISOLATED"` | Satisfies `MULTITHREADED` and each thread has **independent symbol values** in the script | Still must manage shared Java references and resources |
| `"STATELESS"` | Satisfies `THREAD-ISOLATED` and script execution does not change **mappings of ENGINE_SCOPE Bindings** | Does not guarantee object values are immutable or that the script has no side effects |
| Unrecognized value | Provider-specific/unexpected metadata | Do not assume safe concurrency; check vendor docs |

**`STATELESS` does not mean “no side effects”.** For example, if Bindings contains a reference to an `AtomicInteger`, the script calling `incrementAndGet` changes the object's state even though the key/value mapping of Bindings remains unchanged. Similarly, a script can call an HTTP client or write files when the provider allows it; THREADING metadata does not block those actions.

### MULTITHREADED does not mean tenant isolation

~~~text
Thread A: context/sharedBindings["tenant"] = "A"; eval()
Thread B: context/sharedBindings["tenant"] = "B"; eval()
~~~

If the same mutable Bindings is used across two threads, A can read `"B"` during execution even though the interpreter reports `MULTITHREADED`. `THREAD-ISOLATED` adds isolation for symbol values per thread, but still does not make every shared Java object reference safe.

### Metadata is one part, tests are the rest

Read `getParameter("THREADING")` from the **factory of the exact engine being used**. Do not infer from the language name `"JavaScript"`: there are many different providers/versions. If the contract reports `null`, choose engine-per-request or exclusive borrow/lock. If it reports concurrent support, still test with representative workloads and host objects.

## 7. Engine usage patterns with multiple requests/threads

| Pattern | Pros | Conditions/limitations |
| --- | --- | --- |
| **New engine per request** | Easiest to reason about for state ownership | Startup can be expensive; manager-global and provider shared resources still need control |
| **Dedicated engine per worker thread** | Reuse reduces creation cost | Thread pools reuse threads across tenants; state outlives the request |
| **Exclusive engine pool** | Reduces number of engine creations | Exclusive checkout, provider-specific reset/discard, do not return a still-running engine to the pool |
| **One shared engine + synchronized lock** | Prevents concurrent eval if all callers respect the lock | Does not clear previous globals/closures, does not guarantee tenant isolation |
| **Shared engine supporting MULTITHREADED** | Can increase throughput | Shared state, mutable Java objects, readers/writers need control |
| **Isolated worker process/container** | More suitable boundary for untrusted scripts and hard deadlines | Higher IPC, OS quotas, process lifecycle, and overhead |

### 7.1. Engine per request

~~~java
ScriptEngine engine = approvedFactory.getScriptEngine();
Bindings vars = engine.createBindings();
vars.put("api", restrictedFacade);

ScriptContext context = new SimpleScriptContext();
context.setBindings(vars, ScriptContext.ENGINE_SCOPE);
Object result = engine.eval(approvedScriptSource, context);
~~~

The snippet above illustrates **inside a method that handles `ScriptException`**. There is no `GLOBAL_SCOPE` containing tokens. However, creating a new engine **does not guarantee** only allowed APIs remain: host-access must still be configured separately, and the provider may use caches/process-wide state.

### 7.2. Shared engine with lock

~~~java
Object result;
synchronized (engine) {
    result = engine.eval(source, context);
}
~~~

If all callers use the **same lock** for **all operations affecting engine state**, this is a way to prevent concurrent `eval`. But it **does not** prevent request B from seeing old data from request A when the interpreter retains state. With reentrant callbacks or long-running scripts, the lock can cause long queues or deadlocks. Do not call the “synchronized pattern” a sandbox.

### 7.3. Controlled pool

~~~text
borrow engine #3 (exclusive)
  -> bind request A -> eval -> cleanup/discard -> release

borrow engine #3 (exclusive)
  -> bind request B -> eval -> cleanup/discard -> release
~~~

Do not return an engine to the pool when a script times out but is **still running**. For providers that do not support full state reset (closures/module cache/global variables), simply clearing `Bindings` is **not enough** to reuse an engine across a tenant boundary. Prefer discarding.

## 8. Complete Java 17+ example without installing a JavaScript engine

The following example builds a **minimal JSR-223 mock engine** using `AbstractScriptEngine`. It only understands three commands: `"greet"`, `"tenant"`, and `"shared"`. This is **not JavaScript, not a sandbox**, and is not used to prove a general-purpose engine is safe; it only verifies the **ScriptEngine, ScriptContext, Bindings, ScriptEngineFactory, THREADING** contracts and ownership when running in parallel. Because no external provider is needed, it runs on **pure JDK 17+**.

Save the file **`ScriptBoundaryDemo.java`**:

~~~java
import javax.script.*;
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import java.util.TreeSet;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ScriptBoundaryDemo {
    public static final class GreetingView {
        private final String prefix;
        public GreetingView(String prefix) { this.prefix = prefix; }
        public String hello(String name) { return prefix + name; }
    }

    // A tiny, intentionally limited ScriptEngine for deterministic JSR-223 tests.
    // It is not JavaScript and it is NOT a security sandbox for other engines.
    public static final class DemoEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;
        DemoEngine(ScriptEngineFactory factory) { this.factory = factory; }

        @Override
        public Object eval(String script, ScriptContext ctx) throws ScriptException {
            return switch (script) {
                case "greet" -> {
                    Object api = ctx.getAttribute("api", ScriptContext.ENGINE_SCOPE);
                    Object name = ctx.getAttribute("user", ScriptContext.ENGINE_SCOPE);
                    if (!(api instanceof GreetingView view) || !(name instanceof String user)) {
                        throw new ScriptException("Required binding missing");
                    }
                    yield view.hello(user);
                }
                case "tenant" -> ctx.getAttribute("tenant");
                case "shared" -> ctx.getAttribute("shared");
                default -> throw new ScriptException("Unsupported demo command");
            };
        }

        @Override
        public Object eval(Reader reader, ScriptContext ctx) throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] buf = new char[256];
            try {
                int n;
                while ((n = reader.read(buf)) >= 0) source.append(buf, 0, n);
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(source.toString(), ctx);
        }

        @Override public Bindings createBindings() { return new SimpleBindings(); }
        @Override public ScriptEngineFactory getFactory() { return factory; }
    }

    public static final class DemoFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "DemoEngine"; }
        @Override public String getEngineVersion() { return "1"; }
        @Override public List<String> getExtensions() { return List.of("demo"); }
        @Override public List<String> getMimeTypes() { return List.of("text/x-demo"); }
        @Override public List<String> getNames() { return List.of("demo"); }
        @Override public String getLanguageName() { return "FixedDemoCommands"; }
        @Override public String getLanguageVersion() { return "1"; }
        @Override public Object getParameter(String key) {
            if ("THREADING".equals(key)) return null;
            if (ScriptEngine.ENGINE.equals(key)) return getEngineName();
            if (ScriptEngine.ENGINE_VERSION.equals(key)) return getEngineVersion();
            if (ScriptEngine.LANGUAGE.equals(key)) return getLanguageName();
            if (ScriptEngine.LANGUAGE_VERSION.equals(key)) return getLanguageVersion();
            if (ScriptEngine.NAME.equals(key)) return "demo";
            return null;
        }
        @Override public String getMethodCallSyntax(String obj, String method, String... args) {
            return obj + "." + method;
        }
        @Override public String getOutputStatement(String s) { return s; }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() { return new DemoEngine(this); }
    }

    private static ScriptContext newRequest(ScriptEngine engine, String tenant, String user) {
        Bindings vars = engine.createBindings();
        vars.put("api", new GreetingView(tenant + ":"));
        vars.put("tenant", tenant);
        vars.put("user", user);

        SimpleScriptContext ctx = new SimpleScriptContext();
        ctx.setBindings(vars, ScriptContext.ENGINE_SCOPE);
        // GLOBAL_SCOPE is left null. No large host objects are injected.
        return ctx;
    }

    private static String runIsolated(DemoFactory factory, String tenant, String user)
            throws ScriptException {
        ScriptEngine engine = factory.getScriptEngine();
        ScriptContext request = newRequest(engine, tenant, user);
        return (String) engine.eval("greet", request);
    }

    public static void main(String[] args) throws Exception {
        DemoFactory factory = new DemoFactory();
        System.out.println("THREADING = " + factory.getParameter("THREADING"));

        ScriptEngine engine = factory.getScriptEngine();
        ScriptContext a = newRequest(engine, "alpha", "An");
        ScriptContext b = newRequest(engine, "beta", "Binh");

        // Sequential only: THREADING=null does not permit parallel engine.eval.
        System.out.println("request A = " + engine.eval("greet", a));
        System.out.println("request B = " + engine.eval("greet", b));
        System.out.println("A binding keys = " +
                new TreeSet<>(a.getBindings(ScriptContext.ENGINE_SCOPE).keySet()));
        System.out.println("separate bindings = " +
                (a.getBindings(ScriptContext.ENGINE_SCOPE)
                        != b.getBindings(ScriptContext.ENGINE_SCOPE)));
        a.setAttribute("local", "A-only", ScriptContext.ENGINE_SCOPE);
        System.out.println("B local absent = " +
                (b.getAttribute("local") == null));

        Bindings global = new SimpleBindings();
        global.put("shared", "visible-to-A");
        global.put("tenant", "wrong-tenant");
        a.setBindings(global, ScriptContext.GLOBAL_SCOPE);
        System.out.println("engine scope takes precedence = " + engine.eval("tenant", a));
        System.out.println("A global visible = " + engine.eval("shared", a));
        System.out.println("B global absent = " +
                (b.getBindings(ScriptContext.GLOBAL_SCOPE) == null));

        try {
            engine.eval("dangerous-command", a);
        } catch (ScriptException expected) {
            System.out.println("unsupported demo command = " +
                    expected.getClass().getSimpleName());
        }

        // Parallel requests: each task obtains its OWN engine, context and facade.
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> fa = pool.submit(() -> runIsolated(factory, "alpha", "Lan"));
            Future<String> fb = pool.submit(() -> runIsolated(factory, "beta", "Minh"));
            System.out.println("parallel request A = " + fa.get());
            System.out.println("parallel request B = " + fb.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run from the directory containing the file, using **JDK 17 or higher**:

~~~bash
javac --release 17 ScriptBoundaryDemo.java
java ScriptBoundaryDemo
~~~

**Verified `stdout` when compiled with `--release 17`, running on JDK 24:**

~~~text
THREADING = null
request A = alpha:An
request B = beta:Binh
A binding keys = [api, tenant, user]
separate bindings = true
B local absent = true
engine scope takes precedence = alpha
A global visible = visible-to-A
B global absent = true
unsupported demo command = ScriptException
parallel request A = alpha:Lan
parallel request B = beta:Minh
~~~

The code **actually compiled with `javac --release 17` and ran on JDK 24**, producing the 12 lines of output above. Compiling with `--release 17` verifies source/API compatibility with Java 17, which **does not mean** it was run on a JVM 17. The demo factory is not registered with `ScriptEngineManager` and the demo interpreter does not support JavaScript syntax, so no additional engine is needed.

### 8.1. Observing scopes and state

`newRequest` creates a new `Bindings` for each request, binding only `api`, `tenant`, and `user`. The `A binding keys` output shows exactly three keys; then A adds `local=A-only`, and B does not have that key. When A has `tenant=alpha` in ENGINE_SCOPE and `tenant=wrong-tenant` in GLOBAL_SCOPE, `getAttribute` returns `alpha` because of scope precedence.

The demo intentionally attaches the global map **only to context A**; B keeps GLOBAL_SCOPE null. If we replaced it with a **shared global map** via the manager, the reference could be exposed to multiple engines, which is why tenant-specific values should not be placed in manager globals.

### 8.2. Why do parallel calls not violate THREADING=null?

The two calls on the `engine` instance using contexts A/B are executed **sequentially**. In the `ExecutorService` section, each task calls `runIsolated`, which creates a **separate** `DemoEngine`, context, and facade. No two threads concurrently call the same engine instance. The program's `DemoFactory` is immutable and was tested with this pattern of creating instances; **do not infer** that every external ScriptEngineFactory is thread-safe when creating engines concurrently.

### 8.3. Why is DemoEngine not a security proof?

`DemoEngine.eval` only understands the commands `greet`, `tenant`, and `shared`; it rejects other input with `ScriptException`. However, this engine has **no** JavaScript parser, reflection, or Java interoperability. It demonstrates how to use the JSR-223 API and separate ownership; to verify that a real engine does not let scripts touch files/DB/processes, you must run **adversarial tests on that exact provider** with the corresponding policy.

## 9. Finding a real provider in Java 17

When the application has an appropriate script engine provider installed, this pattern can be used:

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory f : manager.getEngineFactories()) {
    System.out.println(f.getEngineName() + ": " + f.getParameter("THREADING"));
}
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    throw new IllegalStateException("No approved JavaScript ScriptEngine installed");
}
Bindings bindings = engine.createBindings();
bindings.put("user", "An");
ScriptContext ctx = new SimpleScriptContext();
ctx.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
Object value = engine.eval("user", ctx);
~~~

The snippet above is only an **in-method snippet**, requiring `javax.script.*` and handling `ScriptException`. The alias name `"JavaScript"` is not guaranteed to always exist or point to a fixed provider; to be safe, check the factory name/version and policy before execution. The expression `"user"` is a JavaScript-side syntax example, not standard syntax across all scripting languages.

`ScriptEngineManager.getEngineByName` returns `null` if there is no matching engine. Built-in Nashorn was removed in JDK 15 (JEP 372), so many Java 8 tutorials do not run as-is on JDK 17. If using GraalJS on a modern JDK, choose the dependency/module and how to configure host access according to the documentation of the deployed version; avoid guessing versions/configuration flags.

### CompiledScript and Invocable

If the engine supports `Compilable`, `CompiledScript` may hold a reference to the engine and state. If it supports `Invocable`, script functions/closures may capture Java objects. **Do not** assume CompiledScript or guest function objects can be passed between threads/tenants. Read the provider's thread/context ownership contract and test it; do not let compiled code retain secrets from a previous request.

## 10. THREADING metadata does not guarantee Java objects are thread-safe

A `STATELESS` engine can still be bound with a mutable object:

~~~java
Bindings shared = new SimpleBindings();
shared.put("counter", new java.util.concurrent.atomic.AtomicInteger());
~~~

Suppose the provider allows the script to call `counter.incrementAndGet()`: the internal state of `AtomicInteger` changes, even though `shared` keeps the same `counter` key and the same value reference. With a regular `ArrayList`/`HashMap`, concurrent mutations can even cause races. Therefore, three separate layers must be examined:

| Layer | Contract |
| --- | --- |
| Engine execution | `THREADING` metadata and provider implementation |
| Request namespace | `Bindings`/`ScriptContext`/default context/manager globals |
| Java object behavior | Authorization, thread-safety, mutability, capabilities, side effects |

Even an immutable DTO that contains a reference to a high-privilege service can open a path to dangerous actions. And a read-only facade can leak data if it does not check the tenant.

## 11. Timeouts and resource limits are not part of standard JSR-223

`javax.script.ScriptEngine.eval` **does not provide standard timeout/CPU quota/memory quota APIs**. Do not assume the snippet:

~~~java
// Pseudo-code for warning purposes only:
Future<?> f = executor.submit(() -> runScript());
f.cancel(true);
~~~

will kill an infinitely running script. `cancel(true)` only requests an interrupt; it does not force the interpreter to stop if it does not cooperate. This is **pseudo-code**, assuming `executor` and `runScript` already exist; it is not a standalone file.

Production measures:

1. Limit source and input size, recursion depth, and CPU budget if supported by the provider.
2. Use supported provider cancellation/close APIs; test with actual infinite loops.
3. Backpressure: bounded queue, max parallel engines, memory/CPU metrics, request deadlines.
4. Do not return a still-running engine to the pool after a timeout.
5. For untrusted scripts, place the engine in a **worker process/container** with restricted OS permissions, dedicated resources, and lifecycle. Close/terminate the process on deadline expiration, and apply IPC validation.
6. Close contexts/resources per the provider; standard `ScriptEngine` is not `AutoCloseable`.
7. Restrict file/network/process/native access at the engine-specific policy and OS levels, not relying on `Thread.interrupt`.

### Why can a pool amplify failures?

A fixed engine pool of 10 instances will stall if 10 scripts block forever. Setting a timeout on the caller without actually stopping the running scripts is even worse: the system may **reuse** the just-cancelled instance for the next request while the old thread is still manipulating the engine. Pool correctness requires exclusive ownership and lifecycle handling on abort, not just a timeout at the HTTP layer.

## 12. Validating output and exceptions before returning to the host

`ScriptEngine.eval` returns `Object`. The host needs to verify type, size, and business constraints:

~~~java
Object raw = engine.eval(source, context);
if (!(raw instanceof String result) || result.length() > 256) {
    throw new IllegalArgumentException("Invalid script result");
}
// result still needs to be escaped/validated according to HTML, SQL, URL, or file path sink.
~~~

This is an in-method snippet with corresponding variables and `ScriptException` handling. Data returned by a script **does not automatically become trusted**. Do not use it directly as an SQL fragment, command, HTML, or path while bypassing checks.

If the output is a provider-specific guest object, do not pass the reference across another thread when the runtime does not allow it. Convert it into an immutable Java DTO/primitive while still in a valid context, with serialization depth/size limits. For `null`, decide according to the API contract and do not default to treating it as “success”.

After a `ScriptException`, the interpreter may have already updated globals/caches or called Java methods causing side effects. Do not assume “if an exception occurs, state rolls back”. If using an engine pool across tenants, consider discarding the failed instance.

## 13. Practical isolation testing

| Test | Expectation |
| --- | --- |
| No JavaScript engine on JDK 17 | `getEngineByName` returning null is handled, no NPE |
| `THREADING=null` and 20 concurrent requests | Same instance is not used concurrently |
| `THREADING=MULTITHREADED` | Tenant data is not shared even though engine can execute concurrently |
| Bindings A/B | No leakage of tokens, user objects, or global vars between requests |
| Manager GLOBAL_SCOPE | Contains no secrets or per-request identity |
| Host class interop | Cannot reach `Runtime`, `ProcessBuilder`, filesystem, reflection, class loader |
| Facade | Enforces authorization, input/output constraints, and side effects itself |
| Engine pool after ScriptException | No remaining state/closures/module cache from previous tenant |
| Infinite loop script | Execution resource deadline is enforced by provider/process |
| Mutable Java object | No race or passing reference to wrong owner thread |
| CompiledScript/Invocable | Engine-specific state is not transferred across tenants/threads without contract |
| Output | Type, length, nested data, and sink validation |
| Provider shutdown | No leaked threads, class loaders, scripts, or contexts |

**Testing on the real engine** is mandatory for host-access security. The minimal demo in section 8 only demonstrates general API usage; testing malicious scripts on it has no meaning for GraalJS/Groovy/other engines.

## 14. Common misconceptions

**“If Bindings are separate, can we share an engine concurrently?”** No. `ScriptEngine` concurrency is described by the factory's `THREADING`; separate bindings are only one part of state.

**“Does `MULTITHREADED` mean each script has its own globals?”** No. The contract states state effects may be visible from other threads. `THREAD-ISOLATED` is stronger regarding symbols, but Java object references can still be shared.

**“Does `STATELESS` mean a script cannot write files?”** No. It only imposes conditions on engine-scope bindings mappings; host I/O depends on the provider/OS.

**“Does `engine.put("service", obj)` only let the script read data, not call methods?”** Cannot be inferred generally. With host interop enabled, an object reference can allow the script to call methods, look up classes, and access other capabilities.

**“Can we use synchronized(engine) and trust that tenants are isolated?”** No. A lock does not clear globals/closures/caches.

**“Does JSR-223 have guaranteed timeouts via cancel(true)?”** No. Interrupt is not a mechanism to forcibly terminate script execution.

**“Does Java 17 come with Nashorn built-in?”** No. Nashorn was removed in JDK 15; install a compatible provider if JavaScript is needed.

**“Is a thread-local engine in a worker pool safe per tenant?”** No. Worker threads are reused; script state can persist from a previous tenant.

**“Is a facade with few methods definitely a sandbox?”** No. A small method surface is good, but a permissive host interop policy can still allow reflection/class loading or callbacks.

## 15. Practical adoption workflow

1. Choose an engine **and a fixed version**, check factory metadata, `THREADING`, and host interop.
2. Classify scripts: trusted, semi-trusted, untrusted; define boundaries and quotas.
3. Design a **capabilities allowlist**: which objects/methods are exposed, what data can be read, and what side effects are allowed.
4. Configure host class lookup, member access, and file/network/process/thread/native restrictions per the provider. Do not enable “allow all” just to pass a demo.
5. Create separate `Bindings` and `ScriptContext` per request, do not use manager-global secrets. Ensure the context also has independent Reader/Writer if needed.
6. Choose engine-per-request as the baseline when state is hard to reset. With pools/threads, maintain exclusive ownership when metadata does not allow concurrent calls.
7. Keep request identity/tenant authorization at the Java host boundary; do not let scripts specify permissions themselves.
8. Validate results, exceptions, and output sinks; do not treat `Object` from a script as trusted.
9. Monitor concurrency, memory, timeouts, queue saturation, and cleanup. Untrusted scripts need reliable resource/process isolation.
10. Run adversarial tests and cross-tenant tests after every provider upgrade.

## 16. Self-check questions

**1.** Factory `getParameter("THREADING")` returns null. Can `eval` be called concurrently on one engine?  
**Answer:** No, per the contract. Use separate engine instances or exclusive locking.

**2.** The engine reports `"MULTITHREADED"`. Can a shared `SimpleBindings` containing `tenant` be used and modified on two threads?  
**Answer:** Should not. The interpreter allows concurrency, but data/state can be shared; use separate contexts and bindings.

**3.** Does `"THREAD-ISOLATED"` guarantee a shared bound Java `ArrayList` is safe when mutated?  
**Answer:** No. Per-thread symbol values and thread safety of a Java object are two independent things.

**4.** Does `"STATELESS"` prevent a script from mutating an object that bindings point to?  
**Answer:** No. Immutable mappings do not mean immutable object values.

**5.** Does `engine.eval(source, context)` automatically forbid reflection or networking?  
**Answer:** No. `ScriptContext` is scopes/I/O; host interop must be configured at the provider/OS level.

**6.** Why can `new ScriptEngineManager().getEngineByName("JavaScript")` return null in JDK 17?  
**Answer:** The JDK is not required to ship a JS provider; Nashorn was removed in Java 15.

**7.** Is `ScriptEngineManager.put("token", value)` good for per-request tokens?  
**Answer:** No. Manager-global bindings can be shared across other engines.

**8.** Does `Future.cancel(true)` guarantee stopping an infinite-loop script?  
**Answer:** No. It sends an interrupt; the runtime may not cooperate. Provider cancellation or killing an isolated worker process is needed.

**9.** Do the two parallel tasks in `ScriptBoundaryDemo` when `THREADING=null` violate the contract?  
**Answer:** No, because each task creates **a separate engine instance** and separate context; the shared engine in the earlier section was only used sequentially.

**10.** The `DemoEngine` demo rejected an unknown command; does that prove a GraalJS sandbox is safe?  
**Answer:** No. This is a toy interpreter that does not support JavaScript/interop; security must be tested with the real engine and specific configuration.

**11.** Can `ThreadLocal<ScriptEngine>` be used to always isolate requests from different tenants?  
**Answer:** No. Thread pools reuse worker threads, so engine state can persist across request boundaries.

**12.** When a provider allows Java object interop, can a read-only facade cause data leakage?  
**Answer:** Yes. A read-only method can still return unauthorized information; tenant authorization, data filtering, and a host-access policy are required.

## References

- [Java SE 17 — ScriptEngine: eval, Bindings, state](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [Java SE 17 — ScriptEngineFactory: THREADING contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html)
- [Java SE 17 — ScriptEngineManager: discovery, manager GLOBAL_SCOPE](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [Java SE 17 — ScriptContext and SimpleScriptContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html)
- [Java SE 17 — AbstractScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html)
- [Java SE 17 — java.scripting, JSR-223 interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/package-summary.html)
- [Oracle — Nashorn removal in Java 15](https://docs.oracle.com/en/java/javase/21/migrate/removed-tools-and-components.html)
- [GraalVM — JavaScript embedding, interop, multithreading](https://www.graalvm.org/javascript/docs/)
- [GraalVM — ScriptEngine wrapper and host access options](https://www.graalvm.org/javascript/docs/#scriptengine-implementation)
