# The Role of Reflection, Proxies, and Method Handles at the Integration Boundary

In Java, the system core may have to work with plugins, adapters, vendor libraries, or components loaded after the application was compiled. The **integration boundary** is where the application's stable contract meets components that can vary at runtime. Reflection, dynamic proxies, and method handles frequently appear here, yet each answers a different question:

- **Reflection:** at runtime, which classes, methods, and annotations exist; what is a valid extension point?
- **Dynamic proxy:** when a call passes through an interface, how should it be intercepted, controlled, or forwarded?
- **MethodHandle:** once the call target is known, how do we bind and execute a call with a well-defined signature?

They **can work together**, but Java integration does not require using all three. This guide moves from architectural placement to APIs, a runnable Java 17 program, common failure points, and how to choose when building adapters.

## 1. Big Picture of the Integration Boundary

Suppose the system wants to expose a stable `GreetingGateway.greet(String)` method, while a vendor only provides `VendorPlugin.say(String)`. Callers should not depend directly on the vendor's class name, method name, or plugin-loading mechanics. We can arrange:

```text
Business code
    |
    v
Stable application interface/port (GreetingGateway)
    |
    v
Proxy: audit, policy, metrics, tracing (if needed)
    |
    v
Adapter / integration registry
    |-- Reflection: discover metadata, verify extension point
    |-- MethodHandle: bind and execute selected target
    |
    v
Plugin / external library
```

This is a responsibility diagram, not a mandatory sequence for every project. If a plugin already implements a shared interface directly, standard Java calls or `ServiceLoader` may be sufficient.

| Mechanism | Core Value | Typical Place in Integration | Limitations |
| --- | --- | --- | --- |
| `java.lang.reflect` | Runtime structure discovery, annotation/signature checks, dynamic invocation | Discovery and validation when registering plugins | Does not create a stable business contract by itself; type errors may surface late |
| `java.lang.reflect.Proxy` | Intercepts calls to interfaces via `InvocationHandler` | Wrapper/adapter for access control, logging, metrics | JDK dynamic proxy only implements interfaces; cannot proxy arbitrary classes |
| `java.lang.invoke.MethodHandle` | Holds a typed callable reference and adapts signatures when needed | Bound target invocation, typically cached | Does not discover API semantics or bypass access permissions automatically |
| Interface/`ServiceLoader` | Static contract and SPI-based discovery | First choice when both sides share an API | Requires agreement on interfaces and class loaders |

## 2. Reflection: From Metadata to Extension Point

Reflection uses `Class<?>`, `Method`, `Constructor`, `Field`, and annotations to inspect what capabilities an object or class offers at runtime.

At the plugin boundary, a sound workflow includes:

1. Obtain the provider object or load the class from an authorized source and class loader.
2. Use reflection to find the method/constructor or annotation designated as the extension point.
3. Verify **name, public visibility, parameter types, return type, version, and match count**.
4. Create an adapter or validated invoker; only then publish it to the core.

API distinctions that commonly cause bugs:

- `getMethod("say", String.class)` finds only **public** methods, including inherited public methods.
- `getDeclaredMethod("say", String.class)` finds a method declared **on that exact class**, which may be private and is not automatically callable.
- `getMethods()` returns accessible public methods under Java rules; filter annotations via `isAnnotationPresent(...)`.
- `Method.invoke(receiver, args...)` executes the call and returns `Object`. Instance methods require an appropriate receiver; primitives are boxed/unboxed. Static methods need no receiver instance.

**Exception handling:** if the plugin's method itself throws an exception, `Method.invoke` typically wraps the target exception in `InvocationTargetException`. To preserve the true root cause, inspect `getCause()`. `IllegalAccessException` indicates an access problem; `NoSuchMethodException` indicates the lookup could not find the requested signature. Avoid lumping all errors into a generic "reflection failed" message, as operations will struggle to distinguish configuration errors from business errors.

**When to use it:** discovery and signature validation typically run **once during provider registration/initialization**, after which the `Method` is cached or an adapter is created. Scanning `getMethods()` and annotations on every request makes the boundary harder to reason about and increases overhead.

**Avoid:** taking arbitrary class/method names from user input and invoking them via reflection. Use allowlists, extension-point rules, permission checks, and argument validation; reflection within the same JVM does not sandbox untrusted code.

## 3. Dynamic Proxy: Controlling Calls Going Through an Interface

`Proxy.newProxyInstance(classLoader, interfaces, invocationHandler)` creates a runtime instance implementing one or more interfaces. When a caller invokes a method through this instance, the handler receives:

- `proxy`: the proxy object itself;
- `method`: the `Method` metadata for the call;
- `args`: arguments, which can be `null` if there are no parameters.

The handler can check permissions, start tracing, increment metrics, measure latency, forward to the implementation, and map errors. The core still sees only the interface.

```text
caller.greet("An")
    -> proxy / InvocationHandler
       -> policy check
       -> forward to adapter/plugin
       -> log audit or metrics, complete
    -> caller
```

Limitations to plan for ahead of time:

1. **Interface-only:** JDK `Proxy` does not automatically subclass an arbitrary class. If a provider lacks an interface, write an adapter or use an appropriate bytecode generation tool when truly necessary.
2. **Call path:** only calls going through the *proxy instance* are intercepted. If the target calls an internal method on itself using `this`, that call bypasses the proxy.
3. **`Object` methods:** `equals`, `hashCode`, and `toString` can also reach the handler. Choose a consistent policy; do not accidentally call back into the proxy and cause infinite recursion.
4. **Default methods:** if the interface has default methods, the handler must decide whether to invoke the default implementation or handle them specially. Java 17 supports `InvocationHandler.invokeDefault(...)` when calling the default implementation.
5. **Checked exceptions:** a checked exception thrown by the handler that is not declared by the interface may be wrapped in `UndeclaredThrowableException`. Error contracts must be designed intentionally.
6. **Class loader:** the loader used to create the proxy must see the exact interface used by the caller; two same-named interfaces defined by two different loaders are still two distinct types.

A proxy does not discover which plugin is valid on its own. It is a place to apply **policy around an interface**; the real method can be invoked directly, via reflection, or via a method handle inside the handler/adapter.

## 4. MethodHandle: Dynamic Yet Typed Invocation

`MethodHandle` from the `java.lang.invoke` package is a reference to a callable operation. Every handle has a `MethodType` specifying parameter types and return type; handles are obtained via `MethodHandles.Lookup`, such as:

- `findVirtual`: instance methods;
- `findStatic`: static methods;
- `findConstructor`: constructors;
- `unreflect(Method)`: converts a `Method` found via reflection into a handle.

Conceptual example with `public VendorPlugin.say(String)`:

```java
MethodType signature = MethodType.methodType(String.class, String.class);
MethodHandle unbound = MethodHandles.publicLookup()
    .findVirtual(VendorPlugin.class, "say", signature);

// Bind the receiver so subsequent calls only need a String argument.
MethodHandle bound = unbound.bindTo(plugin);
String result = (String) bound.invokeExact("An");
```

This snippet illustrates usage with the variables/classes in the full example below.

A handle created from `findVirtual` for `String say(String)` has an invocation type that includes the receiver, equivalent to `(VendorPlugin, String) -> String`. After `bindTo(plugin)`, it becomes `(String) -> String`. Key concepts:

- `invokeExact` requires the **static signature at the call site** to match `handle.type()` exactly, including the return type. Thus the `(String)` cast in the example establishes the call-site type; mismatches can throw `WrongMethodTypeException`.
- `invoke` allows certain type adaptations according to method handle rules; `asType(...)` explicitly creates a handle with an adapted signature. Not every cast/conversion is valid.
- `invokeWithArguments(...)` is convenient for flexible calls via an `Object` list, trading off static type constraints and adding conversion overhead.
- `invokeExact` and `invoke` declare `throws Throwable`; exceptions from the target method propagate directly through this call path without wrapping in `InvocationTargetException` like `Method.invoke`.
- `MethodHandle` does not automatically "remember" to cache itself with the right lifecycle. Re-linking the target on every request can negate the potential benefits of a normalized call path.

Handle accessibility depends on `Lookup` and Java/JPMS rules. `publicLookup()` only accesses eligible public members; `privateLookupIn` also requires appropriate permissions, not an unrestricted way to bypass all encapsulation.

## 5. Standalone Runnable Java 17 Example: Combining All Three

Context: the core provides `GreetingGateway.greet(String)`, whereas the vendor plugin exposes a `say(String)` method annotated with `@EntryPoint`. Reflection locates the right method, a method handle binds the target, and a dynamic proxy adds auditing before the call. All classes are placed in one file for direct testing; in practice, they can live in separate modules.

Create `BoundaryDemo.java`:

```java
import java.lang.annotation.*;
import java.lang.invoke.*;
import java.lang.reflect.*;
import java.util.*;

public final class BoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface EntryPoint {}

    public interface GreetingGateway {
        String greet(String name);
    }

    public static final class VendorPlugin {
        @EntryPoint
        public String say(String name) {
            return "Hello, " + name + "!";
        }
    }

    public static void main(String[] args) throws Throwable {
        VendorPlugin plugin = new VendorPlugin();

        // Reflection: locate the extension point and verify its signature.
        Method selected = Arrays.stream(VendorPlugin.class.getMethods())
            .filter(m -> m.isAnnotationPresent(EntryPoint.class))
            .filter(m -> m.getName().equals("say"))
            .filter(m -> m.getReturnType() == String.class)
            .filter(m -> Arrays.equals(
                m.getParameterTypes(), new Class<?>[] {String.class}))
            .findFirst()
            .orElseThrow();

        // A direct call via reflection for comparison.
        String viaReflection = (String) selected.invoke(plugin, "An");

        // Convert the located Method into a handle and bind the receiver.
        MethodHandle bound = MethodHandles.publicLookup()
            .unreflect(selected)
            .bindTo(plugin);

        // Proxy exposes a stable interface to the application side.
        GreetingGateway gateway = (GreetingGateway) Proxy.newProxyInstance(
            GreetingGateway.class.getClassLoader(),
            new Class<?>[] {GreetingGateway.class},
            (proxy, method, arguments) -> {
                if (method.getDeclaringClass() == Object.class) {
                    return switch (method.getName()) {
                        case "toString" -> "GreetingGatewayProxy";
                        case "hashCode" -> System.identityHashCode(proxy);
                        case "equals" -> proxy == arguments[0];
                        default -> throw new UnsupportedOperationException(
                            method.getName());
                    };
                }
                if (!method.getName().equals("greet")) {
                    throw new UnsupportedOperationException(method.getName());
                }

                System.out.println("audit: " + method.getName());
                // Bound handle has type (String) -> String.
                return (String) bound.invokeExact((String) arguments[0]);
            }
        );

        System.out.println("reflection: " + viaReflection);
        System.out.println("proxy: " + gateway.greet("Binh"));
        System.out.println("toString: " + gateway);
    }
}
```

Compile with JDK 17+ and run:

```bash
javac --release 17 BoundaryDemo.java
java BoundaryDemo
```

Exact stdout:

```text
reflection: Hello, An!
audit: greet
proxy: Hello, Binh!
toString: GreetingGatewayProxy
```

**Explanation of program execution:**

1. `@Retention(RUNTIME)` preserves the annotation at runtime. `getMethods()` returns public methods; the `filter` steps ensure the right annotation, name, and signature are chosen. The example has a single match; a production registry must report clear errors when zero or multiple valid entry points exist, avoiding order-dependent `findFirst()`.
2. `selected.invoke(plugin, "An")` demonstrates reflection: knowing the `Method` at runtime, invoking it with a receiver and argument, then casting to `String`. Because the method throws no exception, the example produces no `InvocationTargetException`.
3. `unreflect(selected).bindTo(plugin)` turns the selected metadata into a handle with signature `(String) -> String` and binds the provider instance. Handle creation happens once before gateway calls.
4. `Proxy.newProxyInstance(...)` supplies an object implementing `GreetingGateway`. When `gateway.greet("Binh")` is called, the handler receives `method=greet`, prints the audit log, and forwards `arguments[0]` to the handle. The `(String)` casts on both argument and return for `invokeExact` are intentional.
5. `toString` is handled explicitly in the handler; `hashCode` and `equals` use identity for consistency with the demo wrapper. `main throws Throwable` keeps the example concise, whereas production code must standardize exception contracts and proper cleanup.

The example shows how they can work together, **not a recommendation to always use all three**. If a plugin already implements `GreetingGateway`, core code can invoke the interface directly or use a decorator/proxy when auditing is needed, without reflection or method handles.

## 6. Applying to Real-World Integration Patterns

### A. Plugins with a Shared SPI Contract

Create an API module containing the interface, have providers implement it, and register via `ServiceLoader` or an explicit registry. The adapter may only need to forward directly. This approach is easy to compile, test, refactor, and version-control. Add a dynamic proxy only when policies need to wrap the interface.

### B. Plugins Discovered via Annotations or Protocol

When classes/methods only appear at runtime, the registry validates annotations, parameter types, return types, and capabilities using reflection. After validation, the registry creates an adapter matching the shared interface. The adapter can use a cached `Method.invoke` or a bound `MethodHandle`; an outer proxy applies tracing, metrics, and policies across all providers.

A prerequisite is a **clearly documented runtime contract**, including annotations, signatures, versions, error types, and handling multiple candidates. Having the same method name does not guarantee the same semantics.

### C. Repeatedly Calling the Same Dynamic Target

Once the target is selected, cache the `Method` or method handle. You can use `asType`, `filterArguments`, and `guardWithTest` to build call adapters when needed, but keep them inside the integration layer and test thoroughly. Do not scatter `invokeExact` across business code. Pick the simplest path that satisfies the contract; dynamic optimization should be driven by measurements.

## 7. Access Permissions, JPMS, and Class Loaders

**Reflection does not erase access rules.** `getDeclaredMethod` can inspect metadata of private members, but that does not grant permission to invoke them. `setAccessible(true)` is not guaranteed to succeed, especially with Java 17 and JPMS strong encapsulation.

In named modules:

- `exports` exposes public API according to module rules;
- `opens` allows deep reflection for the opened package;
- `MethodHandles.Lookup` carries permissions matching where it was created; `privateLookupIn` must still satisfy access/module rules;
- `--add-opens` flags can aid migrating legacy systems, but should not become the default integration design.

**Class identity includes the class loader.** Two copies of `com.example.GreetingGateway` loaded by two different loaders are not the same type. For proxies and casts to work, core and plugin must both see the shared API from the appropriate loader/layer. When reloading plugins, caching `Class`/`Method`/`MethodHandle` or instances in overly long-lived locations can retain the old class loader and cause memory leaks.

**Trust boundary:** validate input/output, allowlist providers, verify capabilities/versions, log appropriate audits, and never let untrusted content arbitrarily specify classes/methods. Code running inside the same JVM is not sandboxed simply because it goes through a proxy or reflection. For untrusted plugins, consider process isolation and controlled protocols.

## 8. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `NoSuchMethodException` | Wrong name or parameter types during lookup | Validate contract/version at registration |
| `IllegalAccessException` / `InaccessibleObjectException` | Member/package lacks access or package is not `opens` | Fix API/module declarations with minimal scope |
| `InvocationTargetException` | Provider method invoked via reflection threw an exception | Read `getCause()` and preserve root-cause details |
| `WrongMethodTypeException` | Mismatched handle signature or `invokeExact` call site | Check `handle.type()`, receiver, inputs, and return type |
| `UndeclaredThrowableException` | Handler threw a checked exception not declared on the interface | Define an error contract and map exceptions intentionally |
| `ClassCastException` receiving proxy/provider | Interface loaded from a different loader or wrong return type | Unify the API class loader and validate types |
| Proxy audit missing | Caller invokes target directly or target self-invokes | Ensure callers use the proxy instance |
| Lookup succeeds but behavior is wrong | Provider changed version or semantics despite matching signature | Write contract tests on behavior, not just metadata |

Separate **integration setup errors** (missing entry point, wrong module, wrong loader, version mismatch) from **execution errors** (bad provider data, timeout, business logic). Setup errors should typically fail fast or disable the provider at registration; runtime errors should be expressed through the contract with operational context.

## 9. Performance and Maintainability

There is no universal rule that "MethodHandle is always faster than reflection" or "dynamic proxies are always slow". Cost depends on call-site shape, target stability, JIT, boxing, conversions, work done inside handlers, and workload. Many integrations spend most of their time in I/O, serialization, or networking rather than the invoke instruction itself.

Pragmatic principles:

- **Separate discovery from invocation:** scan annotations and select methods only during initialization/registration, never per request.
- **Cache with the right lifecycle:** cache metadata/handles after validation; evict them when replacing/reloading providers to avoid retaining old class loaders.
- **Keep types consistent:** with `invokeExact`, pass and receive exact `MethodType` types; use `asType` only when a valid conversion is genuinely needed.
- **Keep handlers minimal:** handle `Object` methods, default methods, and exceptions intentionally; avoid logging sensitive data or unexpected side effects.
- **Measure before optimizing:** if invocation is genuinely hot, use proper benchmarks such as JMH alongside end-to-end latency measurements. Benchmarks do not replace functional, access, and module tests.
- **Test edge cases:** mismatched signatures, multiple entry points, checked/unchecked exceptions, plugin reloads, JPMS, proxy callers, and version changes.

## 10. Quick Selection Rules

| Need | Recommended Tool |
| --- | --- |
| Both sides share an interface upfront | Direct Java call via the interface |
| Provider has standard SPI registration | `ServiceLoader` with the interface |
| Classes/methods/annotations unknown until runtime | Reflection for discovery and validation |
| Need auditing, metrics, or policy around an interface | Dynamic proxy or handwritten decorator |
| Dynamic target selected and invoked repeatedly | Cached `MethodHandle` or `Method`, depending on case |
| Need to run untrusted plugin code | Process/protocol boundary; do not treat reflection/proxy/handle as a sandbox |

Before finalizing an adapter, check: is the shared interface stable; does metadata validation verify full signatures and versions; do modules/loaders allow access; does the proxy handle call paths and errors accurately; does the method handle match receiver, parameters, and return type; are caches cleared on reload; are integration errors easy to diagnose?

**Core point:** reflection *discovers and checks* dynamic components; dynamic proxies *govern calls through an interface contract*; method handles *bind and execute* a resolved target. Placing them inside a registry/adapter at the integration boundary keeps the core's API clean even when external plugins or libraries change.