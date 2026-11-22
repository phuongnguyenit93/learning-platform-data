# 1.6. Trade-offs in type safety, encapsulation, performance, and maintainability

## Learning Objectives

This lesson helps you evaluate when to use Java's dynamic mechanisms, which checks they shift from compile time to runtime, how they affect encapsulation, performance, and maintainability, as well as how to mitigate risks during deployment.

In the `Java Advance - dynamic-runtime` module, "dynamic" can mean reading metadata via reflection, looking up methods by name, using `MethodHandle`, creating proxies, loading classes, or generating/transforming bytecode at runtime. These mechanisms serve DI/IoC, ORM, serializers, plugins, AOP, frameworks, and diagnostic tools. They are useful, but should not be chosen just to save a few lines of code.

## 1. Dynamicity does not mean abandoning the type system

Consider three ways of binding a call:

1. **Standard polymorphism:** a variable of type `PricingRule` calls `apply(int)`, while the JVM selects the actual implementation at runtime. The compiler still checks that the interface declares the method and that the arguments have the right types.
2. **Dynamic access via metadata:** `Class.getMethod(...)`, `Method.invoke(...)`, `MethodHandles.Lookup`, or a proxy handler can determine members/call paths at runtime. A method name written in a string can be wrong even though the entire source code still compiles.
3. **Dynamic code loading/linking:** `ClassLoader`, bytecode generation/instrumentation, or the `invokedynamic` bytecode mechanism supports creating/connecting behavior at runtime. The JVM still enforces class loading, bytecode verification, linking, and access control rules.

`invokedynamic` is a call site linking instruction at the bytecode level, not another name for reflection. `MethodHandle` represents an invocation with a defined `MethodType`; it can be used standalone and also participates in several dynamic linking mechanisms.

The point to evaluate is **who checks the contract and when**. Java still checks types at runtime; increasing the level of dynamicity usually causes errors to appear later, be harder to trace, and depend more heavily on tests/configuration.

## 2. Quick comparison of mechanisms

| Option | Benefits | Price to pay |
| --- | --- | --- |
| Direct call, interface, generics, polymorphism | Clear contract, compiler/IDE catches many errors, easy to refactor | Types/contracts must be designed upfront |
| `ServiceLoader<T>` + SPI interface | Discovers implementations at runtime while callers still communicate through type `T` | Provider/config/version may fail at load time |
| Reflection (`Method`, `Field`, `Constructor`) | Discovers/calls based on metadata, annotations, or configuration | Risks of string names, access, type casting, and runtime exceptions |
| `MethodHandle` / `MethodType` | Explicit invocation type, composable/adaptable; potential for JIT optimization depending on the case | Lookup/call site can still mismatch; more complex code |
| JDK `Proxy` | Intercepts/delegates calls by interface, suitable for logging/transactions | Handler operates dynamically; harder to debug, adds a call layer; interfaces only |
| Class loading/bytecode generation/instrumentation | Extends runtime capabilities, increases framework customizability | Complexity in verification, compatibility, memory, debugging, and lifecycle |

**Pragmatic rule:** keep business APIs statically typed; place discovery, reflection, or adaptation at a **small, verified, and testable boundary**.

## 3. Trade-off 1 — Type safety

### 3.1. Shifting errors from the compiler to runtime

With `rule.apply(100)`, the compiler checks the method on `PricingRule`, the number of arguments, and the return type. If the signature of `apply(int)` changes, call sites through the interface are re-checked at compile time.

With `clazz.getMethod("apply", int.class)`, the string `"apply"` is not bound by the compiler to a specific symbol. Renaming the method while forgetting this string causes `NoSuchMethodException` to appear only when that lookup branch is executed.

Reflection often has late check points:

- `getMethod` searches for **public** methods, including inherited public methods; `getDeclaredMethod` searches for methods declared on the class itself, including non-public ones, but does not automatically bypass access checks.
- `Method.invoke(receiver, args...)` accepts arguments as objects and returns `Object`. The caller must account for argument count/types, boxing/unboxing, null, and casting the result.
- Wrong receiver/arguments can throw `IllegalArgumentException`; insufficient access rights to invoke can throw `IllegalAccessException`; invalid result casting can throw `ClassCastException`; exceptions thrown by the target method are wrapped in `InvocationTargetException`.
- With generics, **type erasure** can prevent runtime metadata/types from fully verifying assumptions such as every element in `List<String>` being a `String`.

`MethodHandle` improves signature description via `MethodType`, but does not turn dynamic lookup into a compile-time check. `invokeExact` requires the types at the call site to match the handle's type exactly and can throw `WrongMethodTypeException` on mismatch; `invoke` allows certain valid conversions but still requires contract verification.

JDK dynamic proxy preserves the interface type on the caller side, but `InvocationHandler` still receives `Method` and `Object[]`. The handler can return the wrong type, forward exceptions improperly, or lose context; checked exceptions not declared on the interface can lead to `UndeclaredThrowableException`.

### 3.2. How to control type risks

1. Expose interfaces/SPIs at the business boundary; confine reflective code inside adapters, factories, or infrastructure layers.
2. Resolve **name, parameters, return type, modifiers, and access rights** once, then validate them before using in the main flow.
3. Use `Class<T>` and `Class.cast(...)` at the point of converting dynamic objects back to domain types, raising clear configuration errors instead of scattering casts.
4. Validate plugins/providers/configurations at startup when appropriate; detect missing classes/methods early.
5. Test missing symbols, overload/signature changes, incompatible providers, exceptions thrown by targets, and mistyped inputs.

**Conclusion on type safety:** dynamicity does not break the JVM verifier; it shifts the responsibility of proving certain assumptions from the compiler to validation code, tests, and runtime monitoring.

## 4. Trade-off 2 — Encapsulation

Reflection helps libraries map fields, read annotations, or instantiate objects. However, if external code relies on a `private field` or private constructor, an internal refactor can break the integration even though the public API has not changed.

For example: a serializer that directly reads the `customerId` field instead of a public contract may fail if the field is renamed, removed, or changed to another representation. Frameworks have valid reasons to do this, but applications need to treat deep access as **an intentional architectural dependency**.

### 4.1. Access control and JPMS on Java 17+

`setAccessible(true)` does not guarantee opening all non-public members. When accessing a package belonging to a named module that is not appropriately opened, requesting to suppress access checks can throw `InaccessibleObjectException`. `MethodHandles.Lookup` also respects access rights; `privateLookupIn` only works when access conditions are met and the module allows it.

Distinguish between:

- `exports p`: makes public types/public members in package `p` available for access according to module rules.
- `opens p to some.module`: allows deep reflection into package `p` for the specified module; does not automatically turn internals into a compile-time public API.
- `--add-opens`: an option to open packages at runtime, useful for migration/compatibility, but makes deployment dependent on JVM configuration.

Example **illustrating module configuration, not a standalone Java program**:

```java
module billing.core {
    exports com.example.billing.api;
    opens com.example.billing.model to com.example.serializer;
}
```

Here the API package is exported, while the model package is opened only to the specific serializer. Module/package names must exist in a real project. Avoid `open module` or broad `--add-opens ...=ALL-UNNAMED` as a default fix when a framework cannot access a private member.

### 4.2. Keeping boundaries clear

- Prefer public APIs, constructors/factories, interfaces, or service provider contracts before accessing private members.
- If deep reflection is unavoidable, open only the exact package/module and document the reason; include that case in JDK/framework upgrade tests.
- Do not let dynamic handlers/invocations bypass business domain invariants, validation, or authorization.
- Classloaders and JPMS **are not security sandboxes** for running untrusted plugin code; plugin sources must be controlled and isolated appropriately.

The deeper you open internals for framework automation, the less ability you have to change internal representations without affecting external consumers.

## 5. Trade-off 3 — Performance

There is no universal ordering of "interface fastest, handle second, reflection slowest" that holds in all circumstances. Costs consist of multiple components:

1. **Discovery/lookup:** loading classes, finding methods, scanning annotations, checking signatures, creating handles/proxies. Should be separated from hot paths whenever possible.
2. **Invocation:** reflection may involve argument conversion/boxing, proxy handlers add a forwarding step, and handles depend on call site type and usage.
3. **JIT and warm-up:** HotSpot can optimize steady calls over time. `MethodHandle` has the potential to be well-optimized in certain patterns, but **is not faster than `Method.invoke` by default** across all workloads and JDKs.
4. **Allocation/memory:** creating many dynamic proxies/classes or keeping metadata/handles in caches can increase allocation, class metadata, and GC overhead. Caches holding `Class`/`ClassLoader` references too long can prevent class unloading, especially in systems with hot reload.

For example, a few reflective lookups at startup are usually insignificant compared to database or network queries. Conversely, a dynamic call inside a loop processing millions of elements or on a low p99 latency path is worth profiling.

**Measure properly:** use JMH with warm-up, forks, and proper result consumption for microbenchmarks; use profilers/metrics and production-like data to verify hot paths, throughput, allocation, GC, and p95/p99. Do not use a single un-warmed `System.nanoTime()` loop to declare which mechanism is always faster.

It is usually best to resolve/cache metadata at initialization, use typed dispatch on hot paths, and avoid creating new proxies/classes per request. However, cache policies must align with the classloader/plugin lifecycle, and measurements should be taken before and after changes.

## 6. Runnable Java 17+ example: same business logic, three ways to invoke

Create the file **`DynamicRuntimeTradeoffs.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class DynamicRuntimeTradeoffs {
    interface PricingRule {
        int apply(int amount);
    }

    public static final class FlatDiscount implements PricingRule {
        public int apply(int amount) {
            return amount - 10;
        }
    }

    public static void main(String[] args) throws Throwable {
        FlatDiscount concrete = new FlatDiscount();
        PricingRule typed = concrete;

        int typedPrice = typed.apply(100);

        Method method = FlatDiscount.class.getMethod("apply", int.class);
        int reflectivePrice = (Integer) method.invoke(concrete, 100);

        MethodHandle handle = MethodHandles.lookup().findVirtual(
                FlatDiscount.class, "apply", MethodType.methodType(int.class, int.class));
        int handlePrice = (int) handle.invokeExact(concrete, 100);

        System.out.println("typed=" + typedPrice);
        System.out.println("reflection=" + reflectivePrice);
        System.out.println("handle=" + handlePrice);

        try {
            FlatDiscount.class.getMethod("aply", int.class);
        } catch (NoSuchMethodException expected) {
            System.out.println("missing=" + expected.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac --release 17 DynamicRuntimeTradeoffs.java
java DynamicRuntimeTradeoffs
```

Stdout output:

```text
typed=90
reflection=90
handle=90
missing=NoSuchMethodException
```

**Explanation of each branch:**

- `typed.apply(100)` is an interface call: Java checks the `PricingRule.apply(int)` contract at compile time and selects the implementation at runtime.
- `getMethod("apply", int.class)` looks up by string and `invoke(...)` returns `Object`, which here is actually an `Integer` that gets cast/unboxed. Misspelling the name `"aply"` is only detected when the lookup is called.
- `findVirtual(...)` creates a handle with signature `(FlatDiscount, int) -> int`. The expression `handle.invokeExact(concrete, 100)` takes variable `concrete` of static type `FlatDiscount` and returns `int`, so it matches exactly. A call site type mismatch can cause `WrongMethodTypeException`.
- All three paths produce `90`. **This example illustrates contracts and error timing, not a benchmark.**
- `main throws Throwable` keeps the demo concise; production code should distinguish lookup, access, invocation errors, and business exceptions to log/convert appropriately.

Try renaming `apply` to `calculate`: the compiler/IDE catches invalid statically typed call sites; string names in reflection/lookup require separate tests or configuration checks.

## 7. Trade-off 4 — Maintainability

Dynamic runtime helps frameworks and plugins evolve without hard-coding every implementation. However, it carries long-term costs:

- **Hard to trace dependencies:** call graphs, Find Usages, rename refactoring, and static analysis can miss class/method names inside strings, annotations, YAML, JSON, or dynamically generated code.
- **Hard to control versions:** changing fields, constructors, overloads, access modifiers, module opens, or dependency versions can cause runtime failures even when the compiler reports no issues in the calling module.
- **Complex debugging:** stack traces pass through `InvocationHandler`, proxies, reflection, or dynamically generated bytecode; missing log context makes bugs hard to reproduce.
- **Testing requires multiple layers:** unit tests for typed contracts, integration tests for discovery, mapping, module path, provider loading, and exception propagation.
- **Operational complexity:** managing startup scanning, metadata caches, classloader lifecycles, JVM flags, and compatibility during JDK upgrades.

A maintainable design is to group dynamic logic into an adapter/registry layer; document configuration names and how errors are raised; validate at startup; and keep interfaces/DTOs/domain invariants on the other side. When there are multiple providers, define contract versioning and compatibility tests across versions.

## 8. Application scenarios and reasonable decisions

| Need | Initial priority | Risks to check |
| --- | --- | --- |
| Business logic with an implementation set known at compile time | Interface, generics, strategy, factory | Clear contract, unit tests |
| Plugins discovered at runtime | SPI interface + `ServiceLoader` or typed registry | Missing provider, version, classloading, and startup validation |
| ORM/serializer/DI needing to read annotations/fields | Reflection inside an infrastructure adapter | Access/modules, schema, and type casting |
| Logging, transactions, interception via interface | Decorator/interceptor/JDK proxy | Exception propagation, interception scope, and overhead |
| Dynamic call resolved once and invoked frequently | Consider caching `MethodHandle` after measuring | Exact signature, access, JIT, and cache lifecycle |
| Profilers, agents, code-generating frameworks | Bytecode generation/instrumentation when truly needed | JVM compatibility, verification, memory, debugging, and version upgrades |

**Plugin architecture example:** instead of having each request read a class name from config and then do `Class.forName` + `getMethod("apply",...)`, define `PricingRule`, discover providers at startup, verify compatible implementations, and store them in a typed registry. Requests only call `PricingRule.apply(...)`. The boundary remains dynamic when registering plugins, while the core stays type-safe, readable, and measurable.

## 9. Evaluation checklist before using a dynamic mechanism

1. **Real need:** do you have to discover structure after the program starts, or do you only need an interface/strategy/decorator?
2. **Types:** which parts does the compiler check? Who is responsible for checking names, signatures, return types, nulls, casts, and exceptions?
3. **Encapsulation:** can a public contract be used? If deep reflection is required, are `opens` narrow and explicit about the target module?
4. **Fail fast:** are missing classes/methods, invalid providers/configs, signature mismatches, and access errors detected at startup or on the first request?
5. **Performance:** have the right hot paths and workloads been profiled? Are lookups reused, and do caches retain classloaders?
6. **Maintainability:** do dynamic dependencies have documentation, log context, integration tests, and a JDK/framework upgrade process?
7. **Operations:** are there metrics for lookup/invoke failures, allocation, startup time, p95/p99, and required module opens configurations?
8. **Security:** are plugin code/class names from external sources controlled? Does the dynamic adapter preserve authorization and invariants?

## 10. Common misconceptions

- **"Reflection removes type safety."** False: the JVM still has types and access checks; more checks are simply moved to runtime.
- **"`setAccessible(true)` opens every private member."** False: JPMS can block it with strong encapsulation.
- **"`MethodHandle` is always faster than reflection."** False: call site, JIT, warm-up, lookup cost, and actual measurement must be considered.
- **"JDK Proxy can proxy any concrete class."** False: JDK `Proxy` creates proxies that implement interfaces; proxying concrete classes requires other mechanisms with their own limitations.
- **"Cache as much as possible."** False: caches holding `Class`/`ClassLoader` can retain old plugins and increase memory usage.
- **"A successful build means dynamic integration is correct."** False: strings/configs/providers/module paths must be integration-tested and verified at runtime.

## Conclusion

Java's dynamic capabilities trade runtime flexibility and extensibility for **more runtime checks, deeper dependency on internals, measurable overhead, and higher maintenance requirements**. A sustainable design usually keeps statically typed contracts in business logic, confines dynamic parts to clear boundaries, fails fast on errors, and relies on benchmarks/profiling rather than assumptions about performance.
