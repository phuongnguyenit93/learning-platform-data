# Comparing Reflection with Interfaces, Strategy, ServiceLoader, and Code Generation in Java

## 1. One Problem, Several Different Approaches

Suppose a Java application needs to choose how to transform strings, process payments, or build serializers based on configuration. There are multiple levels of flexibility:

- **Interfaces and ordinary polymorphism:** contract is known at compile time, invoked directly through the interface.
- **Strategy pattern:** encapsulates multiple algorithms sharing a contract and selects one algorithm according to runtime context.
- **`ServiceLoader`:** discovers implementations of a **service interface/abstract class** declared via Java's provider mechanism, without listing every implementation in client code.
- **Reflection:** queries types and members at runtime, optionally loading classes by name and instantiating/invoking implementations when structure is known late.
- **Code generation:** creates Java source, bytecode, or typed accessors from schemas/annotations/metadata, often to reduce repetitive runtime work.

These are not five mutually exclusive options. For example, `ServiceLoader` returns interface implementations; the application can store them in a Strategy map. A framework might use Reflection at startup and then generate code or cache dispatchers for repeated handling.

**Selection principle:** prefer explicit contracts verifiable at compile time; add dynamic discovery/introspection when real requirements demand it or benefits outweigh costs. Reflection helps handle structures not known in advance, yet you should not pass method names as strings when a call can be safely expressed via an interface.

## 2. Interfaces: Stable Contracts and Direct Polymorphism

An interface specifies the behavior callers use. For example:

```java
public interface Transform {
    String apply(String input);
}
```

Implementation:

```java
public class UpperCaseTransform implements Transform {
    @Override
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Client:

```java
Transform transform = new UpperCaseTransform();
System.out.println(transform.apply("Hi")); // HI
```

The three snippets above are **parts of a multi-file example** presented in full in Section 7; each `public` top-level type resides in a file of the same name.

Benefits:

1. The compiler checks method names, parameter types, and return types.
2. IDE refactoring/renaming easily finds call sites and reports compile errors when contracts change.
3. Callers only need to know `Transform`, without looking up `Method`, calling `setAccessible`, or manually casting `Object` results.
4. Normal method calls can be optimized by the JIT based on runtime characteristics; there is no per-call Reflection metadata overhead.
5. Implementations can be injected via constructor injection, factories, or a DI container.

Limitation of a **plain interface**: someone still has to decide which implementation to instantiate. If plugins must appear without client code knowing their names at build time, you must add a discovery mechanism such as `ServiceLoader` or an appropriate DI/registry mechanism.

There is no reason to use Reflection merely to call `transform.apply(text)` if the object already implements `Transform` and that contract meets the need.

## 3. Strategy Pattern: Selecting Algorithms at Runtime Without Calling Reflection

**Strategy** is a design pattern: turn transformation behaviors into objects sharing an interface, then choose which object to use at runtime. The interface is the contract; Strategy describes **how algorithms are organized and swapped**.

Registry example:

```java
java.util.Map<String, Transform> strategies = java.util.Map.of(
        "upper", new UpperCaseTransform(),
        "lower", new LowerCaseTransform());

Transform selected = strategies.get("lower");
if (selected == null) {
    throw new IllegalArgumentException("Unsupported transform");
}
System.out.println(selected.apply("Hi")); // hi
```

This illustrative snippet assumes `Transform`, `UpperCaseTransform`, and `LowerCaseTransform` are already defined. The standalone runnable example below provides all files.

Advantages:

- Can switch algorithms at runtime based on requests, config, or feature flags while keeping calls through the interface.
- Each strategy can be tested independently, dependencies can be constructor-injected, and ownership and lifecycle are easy to describe.
- Strategy-name checks, fallback policies, and accessibility can be centralized at one selection point.
- Dispatch logic needs neither `Class.forName` nor `getMethod`.

Limitations:

- A static `Map.of(...)` registry knows selectable classes upfront at build time. To add plugin JARs without editing the list, you need a dynamic strategy provision/registration mechanism.
- String registry keys still risk typos at runtime; applications can use enums/validated keys or validate configuration at startup.
- Strategies may hold mutable state; reusing the same instance across multiple threads requires appropriate thread-safety design.

**Strategy does not automatically discover implementations.** You can combine Strategy + `ServiceLoader` to gather providers from the classpath/module path and then select by a stable ID.

## 4. ServiceLoader: Finding Registered Implementations via SPI

`java.util.ServiceLoader<S>` is the JDK's **Service Provider Interface (SPI)** mechanism. The application defines a service contract `S`; one or more providers advertise that they supply implementations of `S`. Clients iterate and consume providers through the service type instead of needing to know implementation names in advance.

```java
java.util.ServiceLoader<Transform> loader =
        java.util.ServiceLoader.load(Transform.class);

for (Transform provider : loader) {
    System.out.println(provider.apply("Hi"));
}
```

This is an illustrative fragment. **Provider order should not be treated as a business contract**; the full example will sort results for deterministic stdout.

### 4.1. Classpath: Registering in META-INF/services

For applications running on the **classpath** (not named modules), if the service interface is `Transform` in the unnamed package, the resource path must be:

```text
META-INF/services/Transform
```

Contents:

```text
UpperCaseTransform
LowerCaseTransform
```

Each provider name must be the **binary class name** of the implementation. In a real project, if the interface is `com.example.spi.Transform`, the file name must be:

```text
META-INF/services/com.example.spi.Transform
```

and each line inside lists a fully qualified name, such as `com.example.impl.UpperCaseTransform`. Registering providers in an arbitrarily named config file will not make `ServiceLoader` recognize them.

For providers deployed on the **classpath**, the simplest form is a public concrete class implementing the service type with a public no-arg constructor. The provider must be visible to the class loader responsible for reading the configuration. Package/classpath mistakes, missing public constructors, wrong names, or providers not matching the service type can cause `ServiceConfigurationError` during iteration.

### 4.2. Module Path: uses and provides

With the Java Platform Module System (JPMS), example syntax (excerpts from **module descriptors**, not pasted directly into the classpath program in Section 7):

```java
// In the client module, e.g.: module client.app
uses com.example.spi.Transform;
```

```java
// In the provider module, e.g.: module provider.impl
provides com.example.spi.Transform
    with com.example.impl.UpperCaseTransform;
```

The application typically adds `requires` to read the module containing the service interface. The two directives `uses` and `provides ... with ...` participate in module service/provider binding; JPMS examples also require module declarations and valid package structure, so the fragments above are **not a standalone project**.

ServiceLoader supports named-module providers under its own contract, including the ability to use a `public static provider()` method on the provider class when matching rules are satisfied; do not equate all named-module rules with the no-arg constructor requirement of classpath providers.

### 4.3. Discovery, Lazy Loading, and Lifecycle

- `ServiceLoader.load(Transform.class)` uses the thread context class loader in this common overload; `load(service, classLoader)` lets you specify a class loader.
- Provider discovery/instantiation is usually **lazy**; some configuration errors surface only when iterating or streaming/getting instances, not necessarily at the `load(...)` call itself.
- ServiceLoader caches discovered providers; `reload()` clears the loader's cache to allow re-lookup. Do not assume new JARs are automatically discovered if the class loader cannot see them.
- `ServiceLoader` is **not thread-safe**; when multiple threads share an instance, the application must synchronize or structure loaders/registries properly.
- Do not rely on "the first provider" to infer priority when the system has no explicit ordering rule; if needed, read separate metadata/priority and sort.
- `ServiceConfigurationError` is an `Error`, not an `Exception`. Therefore `catch (Exception)` is not adequate handling for broken provider configs.

**Boundary:** ServiceLoader finds implementations **registered for a service contract**, rather than scanning every class on the classpath and picking by arbitrary method/annotation names. When you need to inspect fields/methods lacking a shared interface, Reflection may still be needed.

## 5. Reflection: When Enough Structure Is Not Available at Compile Time

Reflection (`java.lang.Class`, `java.lang.reflect.Method`, `Field`, `Constructor`, ...) allows reading metadata and operating on classes/members at runtime.

Example where configuration holds an implementation name:

```java
String configuredClassName = "UpperCaseTransform";
Class<? extends Transform> implementation =
        Class.forName(configuredClassName).asSubclass(Transform.class);
Transform transform = implementation.getDeclaredConstructor().newInstance();
System.out.println(transform.apply("Hi")); // HI
```

This illustrative snippet sits inside a method with `throws ReflectiveOperationException` or appropriate catch handling. The code uses `asSubclass(Transform.class)` to verify the loaded class can actually be used as `Transform`. After instantiation, the caller invokes through the normal interface.

### Strengths

1. No need to know **all** concrete classes upfront at compile time.
2. Useful for reading annotations, resolving constructors/methods/fields, building serializers/mappers, diagnostic tooling, or DI frameworks.
3. Can pick a plugin-appropriate class loader, analyze structure at runtime, and build adapters for types without a shared interface.
4. Can pair with metadata caches such as `ClassValue<T>` to avoid repeated computation.

### Costs and Limitations

- Class/method names passed as Strings are usually verified only at runtime; API renames easily break configurations at runtime.
- `getMethod`/`getDeclaredMethod` require exact names and parameter types; wrong overloads/visibility throw checked lookup exceptions.
- `Method.invoke` and `Constructor.newInstance` carry argument checks, access checks, and exception wrapping (`InvocationTargetException` for errors thrown by target code).
- Metadata analysis and indirect calls have overhead; how much compared to direct calls depends on JDK, JIT, call counts, and caching. **Do not assign a fixed slowdown factor** to every scenario.
- JPMS restrictions on visibility/`opens` still apply; `setAccessible(true)` is not guaranteed to succeed.
- Loading/initializing classes from untrusted user-supplied names can trigger unwanted code. For plugins, enforce allowlists, interface contracts, class loaders, and appropriate authorization policies.
- For closed-world/native images, dynamic Reflection may require build-time metadata configuration/registration; follow the rules of your runtime/compiler.

Reflection is well used when it serves **dynamic discovery/structure**. Once loaded, if an interface is already known, switch to interface calls to simplify everything afterward.

## 6. Code Generation: Moving Analysis to Build Time or Building Specialized Executors

**Code generation** is a family of techniques, not a single API:

- **Compile-time source generation:** annotation processors (JSR 269), schema compilers, or build tasks emit `.java`/resources before or during compilation. Clients then call typed generated code.
- **Build-time bytecode generation:** a tool generates bytecode/classes during a build step before the app runs; sometimes part of framework build-time augmentation.
- **Runtime bytecode generation:** libraries generate classes/adapters/proxies at runtime from known metadata; for instance proxies/mocks/interceptors. This may still need Reflection/MethodHandle during analysis and still depends on class loaders.
- **Ahead-of-time metadata/index generation:** the build emits descriptor tables or annotation/type indexes so runtime avoids broad scanning. This complements Reflection rather than always replacing Reflection used for invocation.

Before-and-after example as a **design idea**, not a complete code generator:

```java
// Before: runtime looks up the method and invokes via Reflection.
Method method = type.getMethod("apply", String.class);
String value = (String) method.invoke(instance, "Hi");

// After: if a generator knows the class/interface and creates an adapter at build time,
// the client calls through a typed interface. The adapter is pre-generated.
Transform adapter = generatedFactory.create(config);
String value2 = adapter.apply("Hi");
```

The snippet above only illustrates the alternative and assumes `generatedFactory`, `type`, `instance`, `config`, and `Transform` exist appropriately. It is not a standalone Java program.

### Benefits When Generated Code Fits

- Many mismatch errors are caught earlier when compiling generated code.
- Reduces repeated annotation/Reflection scanning or dynamic member lookups during startup or request handling.
- Can produce dispatchers/serializers/mappers tailored to a fixed schema.
- Easier to audit which types/members are needed in AOT environments when generators emit controlled registrations/metadata.

### Trade-offs

- Introduces build steps, processors/plugins/compilers, and generated artifacts to manage.
- Schema or annotation changes require regeneration and recompilation; reproducibility/incremental builds must be tested.
- Generated code can make stack traces, debugging, source mapping, or versioning harder to follow.
- If classes are truly known only after build time and runtime must create new behavior, build-time source generation **does not solve** dynamic runtime discovery on its own.
- Runtime bytecode generation incurs class creation/storage overhead and still faces loader/module/security constraints; it does not make every call automatically faster.

**Distinction:** `ServiceLoader` discovers existing implementations; code generation **creates code** or metadata; Reflection **inspects/invokes runtime structure**; Strategy **dispatches algorithms**. These responsibilities can complement one another in one architecture.

## 7. Complete Runnable Java 17 Example: Four Ways for One Service

The following example demonstrates **interface, Strategy, Reflection, and ServiceLoader** all using `Transform`. Code generation is not run in the example because it requires additional build/processor tooling; Section 6 explains that architecture.

Create the directory structure:

```text
demo/
├── Transform.java
├── UpperCaseTransform.java
├── LowerCaseTransform.java
├── ChoiceDemo.java
└── META-INF/
    └── services/
        └── Transform
```

**File `Transform.java`:**

```java
public interface Transform {
    String apply(String input);
}
```

**File `UpperCaseTransform.java`:**

```java
public class UpperCaseTransform implements Transform {
    @Override
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

**File `LowerCaseTransform.java`:**

```java
public class LowerCaseTransform implements Transform {
    @Override
    public String apply(String input) {
        return input.toLowerCase(java.util.Locale.ROOT);
    }
}
```

**File `ChoiceDemo.java`:**

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.ServiceLoader;

public class ChoiceDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Transform viaInterface = new UpperCaseTransform();
        System.out.println("interface: " + viaInterface.apply("Hi"));

        Map<String, Transform> strategies = Map.of(
                "upper", new UpperCaseTransform(),
                "lower", new LowerCaseTransform());
        System.out.println("strategy: " + strategies.get("lower").apply("Hi"));

        Class<? extends Transform> implementation =
                Class.forName("UpperCaseTransform").asSubclass(Transform.class);
        Transform viaReflection = implementation.getDeclaredConstructor().newInstance();
        System.out.println("reflection: " + viaReflection.apply("Hi"));

        List<String> providers = ServiceLoader.load(Transform.class)
                .stream()
                .sorted(Comparator.comparing(p -> p.type().getName()))
                .map(p -> p.type().getSimpleName() + "=" + p.get().apply("Hi"))
                .toList();
        System.out.println("ServiceLoader: " + providers);
    }
}
```

**Resource `META-INF/services/Transform`** (UTF-8 text, not Java code):

```text
UpperCaseTransform
LowerCaseTransform
```

Compile inside `demo/`:

```bash
javac --release 17 Transform.java UpperCaseTransform.java LowerCaseTransform.java ChoiceDemo.java
java -cp . ChoiceDemo
```

Verified stdout:

```text
interface: HI
strategy: hi
reflection: HI
ServiceLoader: [LowerCaseTransform=hi, UpperCaseTransform=HI]
```

**Why do these four lines differ?**

1. **`interface`:** the client directly instantiates `UpperCaseTransform` and calls `apply`; method names are verified at compile time.
2. **`strategy`:** the client picks `"lower"` from a map holding `Transform` objects. Selection relies on the registry's string key, while execution remains an interface call.
3. **`reflection`:** the client knows `"UpperCaseTransform"` as a runtime class name, checks `asSubclass`, creates an instance via its constructor, and then calls the interface. No `Method.invoke` is needed for `apply` because once you have a `Transform`, a direct call suffices.
4. **`ServiceLoader`:** the JDK locates providers declared in the resource, creates instances, and runs them through the interface. The example uses `ServiceLoader.stream()` to query `Provider.type()`, sorts by class name for deterministic stdout, and only then calls `Provider.get()` to obtain instances.

**Example scope:** this is a classpath project in the **unnamed package** for quick copy/run convenience, not the recommended layout for large applications. In real projects, use packages and update the file name `META-INF/services/<fully.qualified.ServiceInterface>` accordingly. Run from the proper root directory so `META-INF/services/Transform` is on the classpath; compiling only Java files while omitting the resource leaves the provider list empty.

If switching to JPMS named modules, add `module-info.java`, valid packages, and `uses/provides` directives as shown in Section 4; do not arbitrarily mix both declaration styles.

## 8. Comparison Table by Architectural Need

| Criterion | Direct interface | Strategy | ServiceLoader | Reflection | Code generation |
|---|---|---|---|---|---|
| Client-facing contract | Compile-time interface/type | Shared algorithm interface | Service interface/abstract class | May know only runtime names/metadata | Generator-created types/adapters |
| Implementation selection | Hardcoded, injected, or factory | Registry/context/runtime policy | Provider registration and discovery | Class names, metadata, loaders, custom rules | Build/schema/processor or runtime generator |
| Auto-discovers self-registered plugin JARs? | Not built in | Not built in | Yes, when JARs/modules and provider configs are visible | Can build discovery logic, though `Class.forName` alone does not scan plugins | Not built in if build-time generation only |
| Refactor-safe | High | High on API; registry keys need management | High on interface; provider configs must stay valid | Brittle at runtime when using strings | High with generated typed APIs, depending on generator quality |
| Arbitrary metadata | Limited to contract | Limited to contract | Can use external metadata to select | Strong: fields/methods/annotations | Can extract at build time or generate indexes |
| Typical errors | Compile/type mismatch | Wrong key/config, algorithm logic | `ServiceConfigurationError`, invisible provider | `ClassNotFoundException`, `NoSuchMethodException`, `IllegalAccessException`... | Generator/build mismatch, stale output |
| Performance | Ordinary polymorphic call | Interface call + strategy lookup | Discovery/provider creation cost, then interface call | Dynamic lookup/invoke; cacheable | Build cost or runtime generation cost; often reduces repeated work |
| Post-build flexibility | Depends on wiring | Switch among existing strategies | Add providers via config/modules/class loaders | Can handle previously unknown classes/metadata | Build generation needs rebuild; runtime generation is more flexible |
| Operational complexity | Low | Low to moderate | Resource/module/loader/provider lifecycle | Access, runtime errors, security, modules, classloaders | Build pipeline, generated code, debugging, versioning |

**There is no absolute ranking of performance or flexibility.** A ServiceLoader may internally use Reflection/constructors to instantiate providers while subsequent calls go through an interface. A codegen framework may generate classes at runtime and use Reflection for initial metadata discovery. Measure the actual workload you care about before changing architecture.

## 9. Choosing a Solution via Practical Questions

### 9.1. "I already know the method to call at compile time"

**Choose an interface / direct Java call.** If multiple swappable implementations exist, use Strategy with a factory/registry or DI. Using Reflection merely to call a fixed method sacrifices type safety without adding useful capability.

### 9.2. "I have multiple algorithms and pick one per request"

**Choose Strategy** with a common interface, validated registry IDs, and a fallback policy. If algorithms are injected by a framework, it is still the same polymorphism idea. There is no need to instantiate classes from arbitrary user-supplied names.

### 9.3. "Plugin authors package separate JARs; the app knows only the service interface"

**Choose ServiceLoader** or an equivalent plugin framework. Clearly define contracts, provider metadata, version compatibility, and class loaders. Layer a Strategy registry on top if you need to select providers by ID, priority, or user permissions.

### 9.4. "I need to read fields/methods/annotations of classes with no shared interface"

**Choose Reflection** when runtime class inspection is required, paired with `ClassValue` caches or parsed descriptors when operations repeat. Separate discovery from hot paths and enforce access/module boundaries.

### 9.5. "I have stable schemas/types, high throughput, and heavy repeated Reflection"

**Consider code generation** for accessors/mappers/serializers/dispatchers if profiling confirms a bottleneck. Ensure the generator validates schemas, builds produce reproducible artifacts, and compatibility tests exist. If classes appear only after build time, consider runtime generation, metadata caching, or a hybrid approach.

### 9.6. "I must run in a native image or closed environment"

Favor designs with **statically analyzable dependency/type lists**. Interfaces and generated code are usually easier to control; Reflection and dynamic loading may require runtime-specific metadata/registration declarations. `ServiceLoader` may be supported by native-image tooling in specific ways; test the actual build rather than assuming SPI behaves identically to a traditional JVM.

## 10. Combining Techniques Along the Right Boundaries

A practical plugin architecture can follow these steps:

```text
Client -> Transform interface (stable contract)
                 |
                 v
          Strategy registry
                 |
      +----------+----------+
      |                     |
  built-in               ServiceLoader
 implementations              |
                                v
                        registered providers
                                |
                                v
                       Transform.apply(...)
```

During startup, the program:

1. Builds a registry from built-in implementations.
2. Uses `ServiceLoader` to locate new providers, validating IDs and capabilities while avoiding duplicate keys.
3. Registers providers under the shared interface.
4. When requests arrive, selects a strategy by allowlisted ID and invokes the interface.
5. If the framework also needs to read provider annotations/schemas, it uses Reflection **once during discovery**, caches validated metadata, and never forces every request to rescan.

If serialization/model binding is heavy on fixed schemas, the build tool can generate adapters and register each adapter as a provider. Thus **code generation and ServiceLoader do not conflict**, and Reflection can serve discovery/validation instead of sitting on every invocation.

## 11. Common Risks and How to Handle Them

**Mistake 1 — Using `Class.forName(userInput)` as a plugin registry.** This can load/initialize unintended classes and make version control difficult. Define contracts, validate allowed implementation IDs, perform explicit discovery, and protect class loaders.

**Mistake 2 — Thinking interfaces provide dynamic discovery automatically.** An interface is only a contract. To discover plugins, you need `ServiceLoader`, DI/container registration, or a dedicated mechanism.

**Mistake 3 — Thinking Strategy requires Reflection.** Strategy needs only objects implementing a shared interface. The Map registry example uses zero Reflection to invoke methods.

**Mistake 4 — Forgetting `META-INF/services` or writing the wrong binary name.** `ServiceLoader` does not read arbitrary config files. Verify the service file name, each provider line, packages, classpath/module path, and post-build JAR layout.

**Mistake 5 — Assuming ServiceLoader always returns one unique provider in a deterministic order.** It may find multiple providers. If the app needs to pick one, define explicit validated priority/ID/fallback rules yourself.

**Mistake 6 — Using `Method.invoke` even when an interface is already available.** After checking `asSubclass` or obtaining `Transform` from ServiceLoader, simply call `transform.apply(...)` for type safety.

**Mistake 7 — Equating code generation with always-better performance.** For small workloads, the extra processor/build/debugging cost can outweigh gains; benchmark in the real environment.

**Mistake 8 — Ignoring API and class-loader compatibility.** A plugin may be compiled against a different contract version than runtime; ServiceLoader can throw `ServiceConfigurationError`, and Reflection can throw `ClassCastException` or `LinkageError`. Specify versioning/compatibility and run integration tests.

**Mistake 9 — Assuming Reflection can bypass all access rules.** `getDeclaredMethod` locates private members, yet invocation still depends on Java access control and module openness. Do not design plugin contracts around forcing access to private methods of arbitrary libraries.

**Mistake 10 — Letting generated code become a hard-to-update source of truth.** Define clear schema/annotation contracts, let builds regenerate code reproducibly, and never hand-edit generated files expecting subsequent builds to keep your edits.

## 12. Decision and Measurement Checklist

Before choosing, answer:

1. Do you need **behavior** or **class structure**?
2. Is the contract stable at compile time?
3. Are implementations built-in, pre-selected, or dynamically added plugins?
4. Do you need discovery by service ID or by arbitrary annotation/field structure?
5. How important are startup time, hot-path latency, throughput, and class-loader unloading?
6. Does the app run on a standard JVM, modular JPMS, native image, or plugin container?
7. Who owns versioning, config validation, fallbacks, and error auditing?
8. Is there profiling or benchmarking proving Reflection is a bottleneck worth replacing with codegen?

A controlled rollout path starts with **interface + Strategy**, opens discovery via **ServiceLoader** when a plugin contract exists, uses **Reflection** for truly dynamic metadata, and moves only stable/costly parts to **code generation** after proper measurements and tests.

## 13. Self-Check Questions

1. **How do Interface and Strategy differ?** — An interface defines the contract; Strategy organizes multiple implementations of that contract and selects one at runtime.
2. **Can ServiceLoader completely replace Reflection?** — No. It discovers providers of a service contract; it does not inspect fields/methods of arbitrary classes.
3. **Is `Method.invoke` needed after obtaining a `Transform` via `Class.forName`?** — No. Call `transform.apply(...)` through the interface.
4. **Will a provider on the classpath without `META-INF/services/<service binary name>` load automatically?** — Not under ServiceLoader's classpath configuration mechanism.
5. **Can build-time code generation automatically load plugin classes that exist only after the build is packaged?** — No. It needs schemas/types at build time, or else a different runtime mechanism is required.
6. **If a `ServiceLoader` provider has broken configuration, is `catch (Exception)` guaranteed to catch it?** — No. `ServiceConfigurationError` is an `Error`.
7. **If Reflection reads metadata at startup and caches adapters, must hot-path calls still go through Reflection?** — No. They can switch to interfaces, generated adapters, or parsed structures.
8. **Why do benchmarks matter?** — Costs of loading providers, building caches, Reflection invocations, and generated adapters vary by scenario/JDK; performance cannot be deduced from technique names alone.

## 14. Key Takeaways

- **Interfaces** are compile-time contracts; **Strategy** selects an algorithm under that contract at runtime.
- **ServiceLoader** performs discovery of **registered providers**, not arbitrary scanning of all classes.
- **Reflection** provides flexible introspection and invocation when structure is unknown beforehand, in exchange for managing runtime names/signatures, access, loaders, and exceptions.
- **Code generation** produces specialized code/metadata at build time or runtime, trading off flexibility, build time, startup cost, and debuggability.
- A **controlled combination** is usually best: communicate via interfaces, use Strategy for selection, ServiceLoader for extensions, Reflection for metadata discovery, and codegen for stable paths with measured benefits.