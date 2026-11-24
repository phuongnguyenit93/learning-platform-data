# Mapping Script Functions to a Java Interface and Handling Unsupported Results

In a runtime-extensible Java application, the host typically knows the **Java contract** in advance (such as text formatting, pricing calculation, or rule validation), while plugin authors want to write the implementation in a **scripting language**. If the host invokes function names as strings everywhere, application code becomes prone to typos, mismatched arguments, and brittle changes. The Java Scripting API (JSR 223, `java.scripting` module) provides the optional **javax.script.Invocable** interface, allowing certain script engines to **map script functions onto a Java interface**.

The primary methods are:

~~~java
<T> T Invocable.getInterface(Class<T> clasz)
<T> T Invocable.getInterface(Object thiz, Class<T> clasz)
~~~

Both can return **null** when a suitable implementation cannot be created. That must be handled as an **unsupported/unavailable mapping result**, not automatically treated as a syntax error, not equated with the entire script engine being broken, and never followed by calling a method on a null reference.

This lesson clarifies this contract, the difference between the two overloads, the capability check path, invocation errors, a standalone Java 17 example without external libraries, and how to integrate it safely into a real plugin host.

## 1. Problem: From Dynamic Script Functions to a Typed Java Contract

Suppose the host defines a Java interface:

~~~java
public interface Greeter {
    String greet(String name);
}
~~~

A script using JavaScript syntax may define a top-level function with the same name:

~~~javascript
function greet(name) {
    return "Hello, " + name;
}
~~~

The host wants to write Java code like this:

~~~java
Greeter greeter = /* obtain adapter provided by the engine */;
System.out.println(greeter.greet("Lan"));
~~~

Instead of using this everywhere:

~~~java
Object value = invocable.invokeFunction("greet", "Lan");
~~~

**The advantage** of an interface adapter is that the host communicates through a published Java contract; method signatures are checked in host code and callers do not have to manage string function names at every call site. However, the fact that a Java interface compiles **does not guarantee the script executes properly**: function names inside the engine, argument counts, value conversion capabilities, script errors, and engine lifecycle must still be checked at runtime.

High-level flow:

~~~text
Host has interface Greeter
            |
            v
Look up ScriptEngine by name/language
            |
         null? ----------------------> Engine unavailable
            |
            v
Check engine instanceof Invocable
            |
         false? ---------------------> Engine does not support Invocable
            |
            v
Evaluate/load script to define functions
            |
      ScriptException? --------------> Script failed to establish state
            |
            v
Invocable.getInterface(Greeter.class)
            |
         null? ----------------------> Cannot map Greeter
            |
            v
Call Greeter.greet(...)
            |
      error on call? ------------------> Execution/conversion error, not null mapping
            |
            v
Receive result per Java contract
~~~

**Only invoke the adapter after confirming it is non-null.** Do not lump all branches into a single `catch (Exception)` and conclude "engine does not support the interface", because many failures happen at other stages.

## 2. Completely Different Kinds of null and Unsupported Results

| Operation | Result / Mechanism | Accurate Meaning |
| --- | --- | --- |
| ScriptEngineManager.getEngineByName("JavaScript") | May be **null** | No engine registered under that name was found in the active environment and class loader |
| engine instanceof Invocable | May be **false** | The engine exists, but does not provide invocation/mapping capabilities via Invocable |
| invocable.getInterface(Greeter.class) | May be **null** | An interface adapter could not be created from the engine's current top-level functions |
| invocable.getInterface(scriptObject, Greeter.class) | May be **null** | An adapter could not be created from the methods of the selected script object |
| engine.eval(script) | May return a **null** value | The script was evaluated; this null may simply be the **expression's value**, not an indication that interface mapping is unsupported |
| greeter.greet("Lan") | May return **null** | The function may be valid and simply returned null; handle per business contract |
| invocable.invokeFunction("unknown") | May throw **NoSuchMethodException** | No function matching the name/arguments was found during direct invocation |
| engine.eval(script) or invokeFunction(...) | May throw **ScriptException** | An error occurred evaluating/running the script; do not convert into a default "unsupported" result |

Each category calls for an appropriate response: **missing engine**, **missing capability**, **interface mapping unavailable**, **script error**, **method invocation error**, **business method returning null**. This is the foundation for designing accurate status reporting and telemetry.

In Java 17, the **java.scripting** module still provides the javax.script interfaces. However, **the Nashorn JavaScript engine was removed from the JDK starting in Java 15**. Therefore:

~~~java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
~~~

may return null on JDK 17 if no external JavaScript engine is installed. Do not assume "Java 17 has a built-in JavaScript engine," and do not proceed to call engine.eval when it is null. If you want to support JavaScript, you must supply a suitable implementation (such as a ScriptEngine adapter for a modern JavaScript library) and verify its actual version and capabilities.

## 3. getInterface(Class<T>): Mapping Top-Level Functions

Contract of **Invocable.getInterface(Class<T> clasz)**:

- The `clasz` argument is a **Class object representing a Java interface**.
- The engine looks up **script functions already evaluated/compiled in the interpreter** that match the interface's methods.
- If an adapter can be created, the result has Java type **T**; the host invokes T's methods just like a normal Java implementation.
- If the requested interface cannot be created, the API permits returning **null**.
- If the argument is **null** or **not an interface**, the method is contracted to throw **IllegalArgumentException**.

Practical usage example, assuming a valid engine object supporting Invocable:

~~~java
// Snippet placed inside a method that has ScriptEngine engine and Greeter.
engine.eval("function greet(name) { return 'Hello, ' + name; }");

Invocable invocable = (Invocable) engine;
Greeter greeter = invocable.getInterface(Greeter.class);

if (greeter == null) {
    System.out.println("Greeter mapping unsupported");
} else {
    System.out.println(greeter.greet("Lan"));
}
~~~

**This is an integration snippet, not a standalone Java program.** The cast is only valid after checking `engine instanceof Invocable`; the full program below performs that check. JavaScript support and Java/String conversion rules are determined by the engine implementation.

### When Does It Return null?

Scenarios to investigate:

1. The script **has not been evaluated/executed yet**, so the engine does not yet have the `greet` function.
2. The function in the script has a different name, or was declared inside an object or another scope instead of top-level.
3. The interface declares additional methods for which the script has no matching functions.
4. The engine does not support creating interfaces with the requested method types/signatures, or the implementation restricts this feature.
5. The engine/script state has changed, or the adapter was requested from an engine/context that does not contain the expected functions.

**Do not rely on a single rule of thumb** such as "if the function count does not match, it is definitely null." The API defines a null return for when the interface is unavailable, while details of matching, overloading, conversion, and proxy creation may depend on the engine. For any specific implementation, test the required contract.

### How Should the Java Interface Be Designed?

Use clear method names, simple signatures, a minimal number of methods, data types that can cross the Java/script boundary, and host-side result validation. Do not assume Java annotations, overloads, generic type parameters, or default methods automatically translate into equivalent logic in scripts. For those cases, verify support in the specific engine.

A **functional interface** with a single abstract method is often the easiest starting point to verify, but the API **does not restrict** getInterface to functional interfaces: a multi-method interface can still be supported if the script engine provides a suitable mapping.

## 4. getInterface(Object thiz, Class<T>): Mapping Methods on a Script Object

Some script engines allow scripts to create objects containing methods. In that case, the method:

~~~java
<T> T getInterface(Object thiz, Class<T> clasz)
~~~

requires **thiz** to be a **script object meaningful to the engine**, not an arbitrary random Java Object. The Java API describes mapping methods on a script object; the implementation may invoke them equivalently to **invokeMethod(thiz, methodName, args)**.

Example in JavaScript syntax, usable only when the engine supports creating and returning an object from an expression:

~~~java
// Snippet, assuming engine instanceof Invocable and Greeter is declared.
Object scriptObject = engine.eval(
        "({ greet: function(name) { return 'Hi, ' + name; } })");

Greeter greeter = invocable.getInterface(
        scriptObject, Greeter.class);

if (greeter == null) {
    System.out.println("Object mapping unsupported");
} else {
    System.out.println(greeter.greet("Lan"));
}
~~~

If the engine fully supports this object model, the expected output is **Hi, Lan**. This is an **implementation-dependent example**; do not claim every JSR 223 engine understands JavaScript syntax or supports object-to-interface mapping.

**Which overload should you use?**

| Need | Preferred Overload |
| --- | --- |
| Script defines functions at top-level in the evaluated engine | getInterface(Greeter.class) |
| Script creates an instance/object with methods | getInterface(scriptObject, Greeter.class) |
| Need to call one specific function, not necessarily via an interface | invokeFunction("name", args...) |
| Need to call one specific method on a script object | invokeMethod(scriptObject, "name", args...) |

The **IllegalArgumentException** contract of the two-parameter overload applies when **clasz is null/not an interface**, or **thiz is null/does not represent a valid script object**. Do not pass null to represent "top-level functions": use the single-parameter overload instead.

If the engine creates an object per eval call, do not accidentally use an object from another engine or context. Script objects are typically tied to the lifecycle, state, and runtime of the engine that created them; caching them across reload cycles can break the adapter or retain memory references longer than intended.

## 5. Practical Integration Pattern: Checking Capabilities in Order

A host can write a reusable helper method for a Java interface to be implemented by a script:

~~~java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptException;
import java.util.Optional;

public final class ScriptAdapters {
    private ScriptAdapters() {
    }

    public static <T> Optional<T> mapTopLevel(
            ScriptEngine engine, String source, Class<T> api)
            throws ScriptException {

        if (engine == null) {
            return Optional.empty();
        }
        if (!(engine instanceof Invocable invocable)) {
            return Optional.empty();
        }
        engine.eval(source);
        return Optional.ofNullable(invocable.getInterface(api));
    }
}
~~~

**This is a standalone-compilable Java class**, though it has no main method and must be called from the host with a valid engine, source, and API interface. The pattern only demonstrates how to check and map; it does not distinguish the three unavailability causes in its return type—in production, use a richer result type. **Optional.empty() is not a script compile error**; ScriptException is kept separate. And if `api` is the wrong kind of class, IllegalArgumentException must still be handled as a caller bug rather than converted into unsupported.

If the missing mapping is an **optional feature**, the host can decline to register that plugin capability with status UNSUPPORTED. If the interface is a **mandatory** contract, the host can report a plugin configuration error and fail activation. This decision belongs to application policy, not to getInterface itself.

### Never Cast Before Checking

~~~java
// WRONG: engine may be null or not implement Invocable.
Invocable invocable = (Invocable) engine;
Greeter greeter = invocable.getInterface(Greeter.class);
greeter.greet("Lan");
~~~

The wrong snippet can suffer NullPointerException, ClassCastException, or invoke on a null adapter. The safe sequence is: **non-null engine → instanceof Invocable → eval script → non-null getInterface → invoke**.

### Distinguishing Errors of getInterface vs. Adapter Calls

- **getInterface returns null:** no matching adapter exists. The host has not executed any business method.
- **getInterface receives invalid arguments:** IllegalArgumentException is an API caller error.
- **Calling a method on the adapter:** executes script code and may fail at invocation time, even when the adapter was created successfully.
- **Return value cannot be converted to the Java type** or a script runtime event occurs: the engine may wrap/throw exceptions per its own rules; do not assume every error surfaces directly as a checked ScriptException on a Java interface that does not declare throws.

Therefore, the plugin execution boundary should log the **stage**, **engine/provider**, **interface name**, and **script version**, without exposing raw source or sensitive inputs in public error messages.

## 6. Standalone Java 17 Example: Testing null Mapping and a Real Engine If Present

On JDK 17 without a default JavaScript engine, an example relying solely on `new ScriptEngineManager().getEngineByName("JavaScript")` cannot reliably run the mapping section. To **run on plain JDK 17**, the program below has two branches:

- **contract**: a test double implementing only **Invocable**, not a real ScriptEngine, simulating missing functions, newly published functions, interfaces with missing methods, and calling a non-existent function name. This branch always produces deterministic output, ideal for testing host null handling.
- **engine**: looks up an actual ScriptEngine named JavaScript in the runtime, checks capabilities, evaluates a function, and attempts to obtain a Java interface. This branch depends on an installed/declared engine and does not assume JDK 17 bundles one.

The test double verifies **Java code decisions**; it **does not run JavaScript** and does not prove the behavior of a third-party engine. The real engine part is a separate integration test step.

### ScriptBridgeDemo.java

~~~java
import java.lang.reflect.Proxy;
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class ScriptBridgeDemo {
    public interface Greeter {
        String greet(String name);
    }

    public interface Missing {
        String absent(String name);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("usage: contract|engine");
            return;
        }
        if ("contract".equals(args[0])) {
            contract();
        } else if ("engine".equals(args[0])) {
            realEngine();
        } else {
            System.out.println("usage: contract|engine");
        }
    }

    private static void contract() throws Exception {
        ToyInvocable invocable = new ToyInvocable();

        // No function in the test double yet.
        System.out.println(
                "before=" + state(invocable.getInterface(Greeter.class)));

        // Simulate that the script has defined the greet function.
        invocable.defineGreet();
        Greeter greeter = invocable.getInterface(Greeter.class);

        System.out.println("after=" + (
                greeter == null ? "unsupported" : greeter.greet("Lan")));

        // This interface requires function absent, which the test double lacks.
        System.out.println(
                "missing=" + state(invocable.getInterface(Missing.class)));

        try {
            invocable.invokeFunction("absent", "Lan");
        } catch (NoSuchMethodException e) {
            System.out.println("direct=NoSuchMethodException");
        }
    }

    private static String state(Object value) {
        return value == null ? "unsupported" : "supported";
    }

    private static void realEngine() {
        ScriptEngine engine =
                new ScriptEngineManager().getEngineByName("JavaScript");

        if (engine == null) {
            System.out.println("engine=unavailable");
            return;
        }
        if (!(engine instanceof Invocable invocable)) {
            System.out.println("engine=not-invocable");
            return;
        }

        try {
            engine.eval(
                    "function greet(name) { return 'Hello, ' + name; }");

            Greeter greeter =
                    invocable.getInterface(Greeter.class);

            if (greeter == null) {
                System.out.println("interface=unsupported");
                return;
            }

            System.out.println("value=" + greeter.greet("Lan"));
        } catch (ScriptException e) {
            System.out.println("script=failed");
        } catch (RuntimeException e) {
            System.out.println("invocation=failed");
        }
    }

    // Test double for Invocable, NOT a JavaScript engine.
    private static final class ToyInvocable implements Invocable {
        private boolean ready;

        void defineGreet() {
            ready = true;
        }

        @Override
        public <T> T getInterface(Class<T> type) {
            if (type == null || !type.isInterface()) {
                throw new IllegalArgumentException(
                        "Expected an interface");
            }
            if (!ready || type != Greeter.class) {
                return null;
            }

            Object instance = Proxy.newProxyInstance(
                    type.getClassLoader(),
                    new Class<?>[] { type },
                    (proxy, method, args) -> {
                        if (method.getDeclaringClass() == Object.class) {
                            return switch (method.getName()) {
                                case "toString" -> "ToyGreeter";
                                case "hashCode" ->
                                        System.identityHashCode(proxy);
                                case "equals" -> proxy == args[0];
                                default ->
                                        throw new UnsupportedOperationException();
                            };
                        }

                        return invokeFunction(
                                method.getName(),
                                args == null ? new Object[0] : args);
                    });

            return type.cast(instance);
        }

        @Override
        public <T> T getInterface(Object thiz, Class<T> type) {
            if (thiz == null || type == null || !type.isInterface()) {
                throw new IllegalArgumentException(
                        "Invalid script object or interface");
            }

            // Test double does not support script-object mapping.
            return null;
        }

        @Override
        public Object invokeFunction(String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            if (name == null) {
                throw new NullPointerException("name");
            }
            if (!ready || !"greet".equals(name)) {
                throw new NoSuchMethodException(name);
            }
            return "Hello, " + args[0];
        }

        @Override
        public Object invokeMethod(
                Object thiz, String name, Object... args)
                throws ScriptException, NoSuchMethodException {

            if (thiz == null) {
                throw new IllegalArgumentException("thiz");
            }
            if (name == null) {
                throw new NullPointerException("name");
            }
            throw new NoSuchMethodException(name);
        }
    }
}
~~~

### Compile and Run

From the directory containing the file above, using JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 ScriptBridgeDemo.java
java ScriptBridgeDemo contract
~~~

**Exact stdout of contract mode:**

~~~text
before=unsupported
after=Hello, Lan
missing=unsupported
direct=NoSuchMethodException
~~~

Explanation:

1. Before `defineGreet`, `getInterface(Greeter.class)` returns null.
2. After `defineGreet`, the test double uses a Java dynamic proxy to return a `Greeter` implementation; the `greet` call is forwarded to `invokeFunction` inside the test double.
3. Interface `Missing` requires method `absent`, which is not simulated; `getInterface(Missing.class)` returns null.
4. When calling `invokeFunction("absent", "Lan")` directly, the test double throws `NoSuchMethodException` instead of returning null. This differs from `getInterface`'s contract.

Continue:

~~~bash
java ScriptBridgeDemo engine
~~~

**On a standard JDK 17 without an additional JavaScript ScriptEngine installed**, expected stdout:

~~~text
engine=unavailable
~~~

If the system has a JavaScript engine installed, output **depends on capabilities**: it may be `engine=not-invocable`, `interface=unsupported`, `script=failed`, `invocation=failed`, or (if the engine accepts the script and mapping):

~~~text
value=Hello, Lan
~~~

Do not combine the outputs above into the result of a single run. Do not modify the JDK or secretly add dependencies just to force the engine branch to succeed; in real projects, engine dependencies must be managed and tested at the same version across development, CI, and production.

### Why Does the Example Use a Dynamic Proxy?

ToyInvocable is a **mock** simulating the Invocable contract, not a script compiler. It controls supported/null states and allows tests to run without depending on an engine installed on the machine. Using `Proxy` in the test double shows how a Java adapter can forward interface calls to dynamic functions; **this is not a promise that real engines use `java.lang.reflect.Proxy` internally**.

The `realEngine` section is real integration code that checks engine availability, Invocable support, and a non-null adapter. It compiles on JDK 17 because the entire `javax.script` API resides in `java.scripting`, even when the runtime has no JavaScript engine.

## 7. Handling Unsupported Results in Host/Plugin Design

A large host should define a typed result instead of an ambiguous null. For example:

~~~java
enum ScriptBindingStatus {
    ENGINE_UNAVAILABLE,
    ENGINE_NOT_INVOCABLE,
    SCRIPT_EVALUATION_FAILED,
    INTERFACE_UNSUPPORTED,
    READY,
    INVOCATION_FAILED
}
~~~

This is an illustrative enum for integrating into an application service; it is not a standalone runnable program. It separates the READY state (adapter created) from errors during future method calls.

Example policy table:

| Status | Plugin Handling |
| --- | --- |
| ENGINE_UNAVAILABLE | If the script feature is optional: disable the plugin and report the missing engine clearly; if mandatory: fail startup/activation |
| ENGINE_NOT_INVOCABLE | Do not use getInterface; reject interface-based plugins or pick another supported adapter per configuration |
| SCRIPT_EVALUATION_FAILED | Actual failure while loading the script; provide controlled diagnostics without turning it into "unsupported" |
| INTERFACE_UNSUPPORTED | Do not activate the adapter, keep the host safe, report missing method/interface names if the engine allows identifying them |
| READY | Store the adapter together with the live engine/context; use via the validated contract |
| INVOCATION_FAILED | Record the per-call failure, apply appropriate timeout/circuit breaker/rollback; do not automatically assume the earlier adapter registration was wrong |

**Do not hardcode one behavior for every plugin:** For an optional interface like HealthCheck, a missing interface might only disable that health-check feature. For a mandatory interface like PaymentRule, a missing interface must reject the entire plugin. The business decision is driven by host metadata/contracts, not inferred from null alone.

### Distinguishing Contract null from Data null

Suppose the Greeter adapter is created successfully, yet a script function returns null according to business logic. Then:

~~~java
Greeter greeter = invocable.getInterface(Greeter.class);

if (greeter == null) {
    // No matching adapter: greet was not executed.
} else {
    String result = greeter.greet("Lan");
    if (result == null) {
        // Adapter exists, but the business method returned null.
    }
}
~~~

This is a diagnostic snippet inside a method that already has `invocable` and `Greeter`; it is not a standalone program. The two null checks represent **two different semantic layers**. Do not collapse both cases into a single null result when the API needs to distinguish them.

### Optional and Exception Pitfalls

`Optional.ofNullable(invocable.getInterface(...))` is useful when the host only cares whether an adapter exists. However, if the application needs root-cause diagnostics, return a dedicated result carrying status, diagnostics, and an optional adapter payload. `Optional` cannot convey whether the engine was missing or the script failed.

Nor should you catch every `RuntimeException` and classify it as `INTERFACE_UNSUPPORTED`. For example, a return-type conversion failure or a runtime exception thrown by executing script code is **INVOCATION_FAILED**, while an `IllegalArgumentException` from passing a non-interface `Class` is a **host programming bug**.

## 8. Method Names, Parameters, and Return Types

Mapping onto a typed API **does not turn a dynamic scripting language into a Java compiler for scripts**. Several differences must be verified during integration:

- **Names**: the interface method and script function/property name must be recognized by the engine as matching. Case mismatches can prevent mapping.
- **Parameter counts**: the Java method declares a signature; the engine may apply its own rules for missing/extra arguments or variadic arguments. Do not extrapolate from a different language.
- **Overloads**: Java allows multiple methods with the same name and different parameter types, whereas many scripting languages treat a function name as a single key. Avoid complex overloads unless the engine proves a clear matching policy.
- **Parameter types**: `Integer`, `String`, `List`, `Map`, host objects, or `null` may be converted to script values per implementation rules. Use simple DTOs and versioned contracts rather than passing uncontrolled internal objects.
- **Return types**: a script value may fail to convert to the declared Java type. A proxy/adapter can still fail at invocation time even when `getInterface` returned non-null.
- **Primitives**: a Java method returning `int`/`boolean` cannot safely unbox `null`; test type/numeric bounds and engine error handling.
- **Checked exceptions**: Java interface methods do not declare `ScriptException` by default. Engines may wrap script errors into unchecked exceptions when crossing the adapter; verify the actual contract instead of trying to catch `ScriptException` where the compiler forbids it.
- **Default, static, and Object methods**: do not assume a script adapter supports every interface feature identically to a hand-written Java class. Test at least the methods actually used at runtime.

The main benefit of the interface is a **static contract for the host**, while proper script execution must be ensured through integration tests against the specific engine.

## 9. The java.scripting Module, Class Loaders, and Engine Lifecycle

If the host is an **explicit JPMS module** using `javax.script` directly, the minimal module descriptor typically includes:

~~~java
module demo.host.scripting {
    requires java.scripting;
}
~~~

This is an example descriptor; other `requires` clauses depend on the actual host code. `requires java.scripting` grants access to the `javax.script` API, **it does not install a script engine by itself**. A real engine must be present in the application/module path/classpath and registered via the appropriate mechanism so `ScriptEngineManager` can discover it.

### Environment-Dependent Engine Discovery

`ScriptEngineManager` uses service discovery for `ScriptEngineFactory`, which interacts with the **thread context class loader** in the corresponding constructors. A plugin JAR containing an engine that is not visible from the loader/module layer used by the manager can still cause `getEngineByName` to return null. In dynamic plugin systems, identify the loader/layer of both the **factory** and the **engine**, rather than merely checking that the JAR is in the plugins directory.

If a script engine resides in a separate `ModuleLayer`, the host must design discovery/instantiation across the appropriate module boundary; the default manager may not scan all custom module layers. Therefore, log the requested engine name, loader identity, and provider source when diagnosing issues, rather than immediately assuming the engine name is wrong.

### Lifecycle and Thread Safety

1. Create engines at the appropriate scope (plugin instance, tenant, session, or request); do not lump the entire system into a single shared `ScriptEngine`.
2. Evaluate scripts before obtaining adapters; keep the adapter together with **the necessary engine and script object/context** for its entire lifetime.
3. When updating scripts, clarify whether reload mutates state inside an existing engine or creates a new engine/context; old adapters may remain bound to old state.
4. **Do not assume a ScriptEngine is safe for concurrent calls across multiple threads.** Check `ScriptEngineFactory.getParameter("THREADING")` and engine documentation; this parameter is only metadata and must be verified with tests and the specific implementation's contract.
5. Enforce limits on engine count, execution duration, data volume, and state size; clean up resources per engine API/lifecycle (if the implementation has its own `close` or context API).
6. When stopping a plugin, stop accepting new invocations and drain running tasks per policy; do not hold registry locks while waiting on scripts that might call back into the host.

**Do not retain mapped adapters as permanent Java objects** if the engine/module layer they depend on has been closed or unloaded. Doing so can break subsequent calls or pin class loaders/plugin classes from garbage collection.

## 10. Security When a Script Becomes an Interface Implementation

Mapping to an interface narrows the **host's communication surface**, but **does not automatically make the script safe**. Scripts can execute code during `engine.eval` and when interface methods are invoked via the adapter. Depending on the engine, they may access Java APIs, reflection, files, network, CPU/RAM, and host callbacks.

Measures to consider:

- Only run trusted scripts inside the same JVM if the environment and engine permissions allow it. For untrusted scripts, consider a **separate process/container**, OS policies, resource limits, and controlled RPC channels; an in-JVM adapter is not a sandbox.
- Do not arbitrarily expose full host objects, database handles, registries, or secrets to script bindings. Provide only minimal services and contracts.
- Enforce timeouts, invocation limits, parameter/return payload sizes, active plugin limits, and logging levels. **Invocable.getInterface has no universal timeout API**; timeouts usually must be enforced at the worker or engine-specific layer.
- Isolate state between tenants and plugins; avoid accidentally reusing bindings or adapters from another tenant's engine.
- Verify script provenance, versions, and update policies; having the same interface name does not guarantee compatible behavior in a new script.
- When a script fails, log diagnostic details without leaking sensitive source code or input data to unauthorized viewers.

Never choose "return null on error" to hide an exception from an executed script: doing so makes security or operational failures look like a normal missing capability.

## 11. Step-by-Step Error Diagnostics

When the host cannot create a Greeter adapter, trace from **discovery → capability → eval → mapping → invoke**.

| Symptom | Likely First Check | Verification Step |
| --- | --- | --- |
| engine == null | Missing ScriptEngineFactory/engine dependency or manager cannot see provider | List getEngineFactories; check engine name, class loader, and module layer |
| Engine present but not instanceof Invocable | Engine implementation lacks the optional capability | Check docs/runtime type; choose another adapter or report unsupported |
| getInterface returns null | Missing matching function/method, wrong scope, or engine does not support this mapping | Verify evaluated script, interface methods, names/scopes, engine docs |
| getInterface(thiz, interface) throws IllegalArgumentException | thiz is null/not a valid script object or clasz is not an interface | Verify object returned from the corresponding engine and valid interface Class |
| Error during eval | Invalid script source or missing context/dependency | Preserve ScriptException/diagnostics; do not turn into null mapping |
| getInterface non-null but calling method fails | Runtime exception in script, conversion mismatch, lost engine state | Log invocation and engine-specific cause; test arguments/return types |
| invokeFunction throws NoSuchMethodException | Direct-called function name or signature does not exist/is incompatible | Check function name, args, evaluated scope |
| Works in dev, missing engine in production | Runtime packaging/module/class loader differs from development | Check artifacts and engine providers in production |
| Intermittent errors when multiple requests share an adapter | Non-thread-safe engine/context, state race, or reload lifecycle | Check THREADING contract and test concurrent usage |

Example engine-list diagnostic (snippet for a Java `main` or helper method):

~~~java
ScriptEngineManager manager = new ScriptEngineManager();

for (var factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName()
            + " -> " + factory.getNames());
}
~~~

If the list contains no JavaScript engine, `getEngineByName("JavaScript")` can be null on Java 17. Do not use a specific stdout of the snippet above as a test assertion; the list depends on whichever providers are installed in the runtime.

### Common Mistakes

1. **Forgetting to check engine for null** and calling `eval` directly on null.
2. **Casting ScriptEngine to Invocable without checking**, causing `ClassCastException` on engines without support.
3. **getInterface returns null yet calling a method anyway**, causing `NullPointerException`.
4. **Confusing a null return value from a script function with a null mapping**, causing the host to report the wrong reason.
5. **Confusing invokeFunction/NoSuchMethodException with getInterface/null**, even though they are two distinct APIs with different return contracts.
6. **Calling getInterface(thiz, type) with null thiz or the wrong kind of Java object**, causing `IllegalArgumentException` per contract.
7. **Requesting the adapter before eval**, or from an engine lacking the corresponding function state.
8. **Confusing top-level functions with script-object methods**, picking the wrong overload.
9. **Expecting Nashorn to be bundled in Java 17**, even though it was removed from the JDK.
10. **Assuming every javax.script engine supports mapping**, when Invocable is optional.
11. **Believing having an adapter means every call will succeed**, ignoring conversion and lifecycle issues.
12. **Sharing a ScriptEngine/adapter across threads or tenants without verifying** thread safety and state isolation.

## 12. Test Matrix for a Runtime-Extensibility Host

Include both **policy unit tests** (using an Invocable test double) and **real engine integration tests** (matching production engine and version).

1. **No engine:** manager returns null; host records `ENGINE_UNAVAILABLE` without eval/cast.
2. **Engine does not implement Invocable:** host records `ENGINE_NOT_INVOCABLE` without forced cast.
3. **Invocable but script lacks the function:** `getInterface` returns null; host records `INTERFACE_UNSUPPORTED` per the engine contract under test.
4. **Function evaluated and valid mapping:** non-null adapter, method call returns properly typed data.
5. **Interface adds a method not yet supported by the script:** host detects mapping failure or applies the corresponding engine policy.
6. **Object-based mapping:** test `getInterface(scriptObject, Interface.class)` and invalid `thiz` cases.
7. **Invalid API interface:** pass non-interface/null `Class`, verify explicit input error.
8. **Eval error:** invalid source, verify `ScriptException` and ensure it is not logged as unsupported.
9. **Invocation error:** script function throws an error, return type mismatch, lost engine state; host records `INVOCATION_FAILED`.
10. **A valid method returns null:** verify this is a business null, distinct from a null adapter.
11. **Concurrency and reload:** verify engine scope, script updates, cleanup, and not retaining adapters of stopped plugins.
12. **Java 17 packaging:** test both plain JDK without a JS engine and the environment with the configured engine.

**Do not force integration tests to pass on plain JDK 17 by assuming a JavaScript engine exists.** Testing the engine-unavailable branch is a valid outcome. Real capability tests must include the specific dependency and configure the engine in CI identically to production.

## 13. Checklist for Designing a Script-to-Java-Interface Adapter

- A public **Java interface** with minimal, version-stable method names and types.
- An **engine provider** installed and discoverable by the right class loader; handle when the manager returns null.
- Engine **actually implements Invocable**; check before invoking.
- Script **already evaluated** in the right engine/context before creating the adapter.
- Choose **getInterface(Class<T>)** for top-level functions or **getInterface(thiz, Class<T>)** for script-object methods.
- The `thiz` object is a valid **script object** supplied by the engine; `clasz` is a non-null **interface Class**.
- Check **getInterface result is non-null**; do not blindly infer it from a successful `eval`.
- Distinguish **ENGINE_UNAVAILABLE, NOT_INVOCABLE, INTERFACE_UNSUPPORTED, SCRIPT_EVALUATION_FAILED, INVOCATION_FAILED**.
- Test Java/script conversion for **arguments, null values, primitives, return types, and exceptions**.
- Define **engine/context/adapter lifecycle rules**, avoiding uncontrolled cross-tenant/cross-thread state.
- Determine **script trust level**, permissions granted to plugins, and isolation mechanisms if needed.
- Test both **missing JavaScript engine on JDK 17** and the actual engine installed in the distribution.

**Conclusion:** A Java interface is the **contract boundary** for the host, whereas script mapping is an **optional capability** of an engine. Always follow the order: **find engine → check Invocable → eval script → request getInterface → check non-null → invoke methods and handle runtime errors**. Separating **missing engine**, **unsupported mapping**, **script error**, and **method returning null** is essential for a runtime-extensibility system to behave predictably and remain operable.

## References

- [Java SE 17 — javax.script.Invocable](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Invocable.html): the two `getInterface` overloads, `null` return values, `IllegalArgumentException`, `invokeFunction`, and `invokeMethod`.
- [Java SE 17 — ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): discovering engines by name, service discovery, and factories.
- [Java SE 17 — ScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval` and context contracts.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): why Nashorn is not bundled by default since JDK 15.