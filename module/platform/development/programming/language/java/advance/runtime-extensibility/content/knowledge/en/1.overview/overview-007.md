# Prerequisite Knowledge and Learning Order for Java Extensibility Mechanisms

## 1. Understand the Goal Properly: What Is "Runtime Extensibility"?

A Java application has runtime extensibility when it has **pre-designed extension points** to locate, load, initialize, or compose additional behavior without modifying core logic for every variant. "Dynamic" has multiple levels: choosing a pre-built implementation from configuration; discovering providers in JARs; creating invocations or proxies at runtime; loading code via a dedicated class loader; or even intervening in bytecode via a Java agent. Not every problem needs the most powerful level.

Always separate five questions:

1. **Contract:** Which interface/API must the extension component implement, what data does it receive, and what results does it return?
2. **Discovery:** How does the application know which implementations exist—via configuration, a registry, `ServiceLoader`, or metadata scanning?
3. **Loading/linking:** Which class path, module path, or `ClassLoader` makes classes/JARs/modules visible to the JVM?
4. **Invocation/lifecycle:** Who instantiates objects, calls methods, manages dependencies, configuration, errors, and stops plugins?
5. **Isolation/operations:** How are versions, access permissions, resources, logging, reliability, updates, and class loader reclamation controlled?

For example, a report-export system has `ReportExporter` and implementations `CsvExporter`/`JsonExporter`. If the export types are known at compile time, choosing via constructor injection or a factory is enough. If you want to add new vendor JARs to the distribution, start with SPI/`ServiceLoader`. Consider dedicated loaders only when you genuinely need to load JARs from custom paths or isolate versions; use instrumentation only when you need to observe or adjust bytecode behavior that standard APIs do not permit.

## 2. Prerequisite Knowledge to Have First

| Foundation | Must Know Well | Why It Matters |
| --- | --- | --- |
| Java Core & OOP | `interface`, `abstract class`, overriding, polymorphism, generics, exceptions, visibility, `equals`/`hashCode` | Build stable extension contracts and handle errors when plugins run |
| API Design | Dependency inversion, composition, immutable DTOs, backward compatibility, versioning | Prevent plugins from depending on internal implementations |
| Compilation & Packaging | `javac`, `java`, `jar`, packages, JAR manifests, resources, basic Maven/Gradle | Understand why classes/providers are present or fail to be discovered |
| JVM Fundamentals | Bytecode, `Class<?>`, class loading → linking → initialization, heap/GC, exception stack traces | Explain class initialization effects, linkage, and unloading capability |
| Code Distribution | Class path, module path, dependencies, JAR conflicts, semantic versioning | Distinguish missing-class errors from binary incompatibility errors |
| Inspection Tools | Unit/integration tests, `jar tf`, `javap`, `jdeps`, logs | Verify both when plugins are present and when they are absent |

**Entry checkpoint:** build an interface, two implementations, and a factory selecting an implementation by parameter; package the application into a JAR and run it with Java 17+. If you are not yet comfortable with `-cp`, resources inside JARs, public/package-private visibility, and the difference between compile-time type and runtime object, practice those parts first.

## 3. Recommended Learning Order (From Low Risk to Advanced)

| Stage | Core Topics | Minimum Hands-On Practice | Ready to Advance When |
| --- | --- | --- | --- |
| **0. Foundations & Contracts** | Java 17+, interfaces, class path/JAR, DIP, semantic versioning | App with two implementations swapped via config | Can swap implementations without editing business logic |
| **1. JVM Class Model** | `Class`, class loaders, delegation, resources, load/link/init | Print class loader of each class; try `Class.forName` | Can explain `ClassNotFoundException` and initialization |
| **2. SPI/`ServiceLoader`** | Service contract, provider, `META-INF/services`, lazy discovery, caching | Load one provider from class path, add a second provider | Can add JAR/provider without editing host code |
| **3. JPMS** | `module-info.java`, `requires`/`exports`/`opens`, `uses`/`provides` | Port the SPI example to the module path | Can explain access errors and module resolution |
| **4. Reflection/Annotations** | `Class`/`Method`/`Constructor`, annotation retention, type/access checks | Read plugin annotation and invoke an allowed method | Do not rely on private APIs or arbitrary class names |
| **5. Proxies & Dynamic Calls** | `Proxy`/`InvocationHandler`, decorators, basic `MethodHandle` | Add logging/validation around an interface | Distinguish proxies from provider discovery and instrumentation |
| **6. Dedicated Loaders & Plugin Architecture** | `URLClassLoader`, TCCL, identity, resource cleanup, `ModuleLayer` as needed | Load provider from a plugin JAR outside the class path | Can manage lifecycle, versions, and cast errors |
| **7. Bytecode/Agents (advanced track)** | `java.lang.instrument`, `premain`, `ClassFileTransformer`, retransformation limits | Agent logging loaded classes in a test app | Know clearly when agents help and their deployment risks |

This is a **knowledge-dependency order**, not a requirement that every project complete all stages. Most business extensibility systems should stop at stages 2–5; stages 6–7 are meant for plugin platforms, frameworks, observability tools, profilers, or analysis tools.

## 4. Stage 1 — Class, Class Loading, and Initialization Lifecycle

### 4.1. Distinguish Three Often-Conflated Steps

- **Loading:** a class loader locates bytecode and defines the `Class` object; it may delegate to a parent loader.
- **Linking:** the JVM verifies bytecode, prepares structures, and resolves symbolic references at a time chosen by the JVM.
- **Initialization:** runs static initializers and initializes static fields according to language rules.

`Class.forName("demo.Plugin")` via its one-argument overload requests initialization by default; `ClassLoader.loadClass("demo.Plugin")` normally only loads without forcing initialization. When control is needed, use `Class.forName(name, initialize, loader)`. Do not use class initialization as a disguised "plugin registry" via static blocks: side effects and testing become hard to predict.

A Java class is identified by **(binary name, defining class loader)**. Two different loaders can define two classes both named `demo.Plugin`, yet the JVM treats them as **two distinct types**. This is the root cause of seemingly inexplicable `ClassCastException`s in plugin systems.

### 4.2. Understand Delegation Before Writing Custom Loaders

Standard loaders ask their parent first before searching for a class themselves. Bootstrap, platform, and application/system class loaders play distinct roles; do not assume implementation class loaders always have fixed class names. Class loaders also locate **resources**, such as provider configurations at `META-INF/services/...`.

Observe on Java 17+:

~~~java
public class LoaderMap {
    public static void main(String[] args) {
        System.out.println(String.class.getClassLoader()); // Usually null: bootstrap
        System.out.println(LoaderMap.class.getClassLoader());
        System.out.println(Thread.currentThread().getContextClassLoader());
    }
}
~~~

Save as `LoaderMap.java`, run `javac LoaderMap.java` then `java LoaderMap`. The first line typically prints `null` because platform classes are defined by the bootstrap loader; **the next two lines depend on the environment**, so do not assume fixed stdout. The thread context class loader (TCCL) matters to frameworks/`ServiceLoader` because library code may need visibility into application providers.

**Distinguish errors carefully:** `ClassNotFoundException` usually occurs when name-based lookup fails to find a class; `NoClassDefFoundError` can appear when the JVM needs a class but cannot define/initialize it (including a class that previously failed initialization); `NoSuchMethodError` often hints at binary incompatibility between compile time and runtime. Do not blindly fix everything by "adding more JARs" before reading the cause and actual class path.

## 5. Stage 2 — Designing Extension Points and Service Provider Interface

`ServiceLoader` is the first step to use when plugins are already available on the class path or module path. It discovers providers of a **service type** through standard metadata, then instantiates them lazily during iteration. The contract is usually a small, stable interface documenting inputs/outputs and exceptions.

### 5.1. Runnable SPI Example with Class Path (Java 17+)

Create the structure:

~~~text
src/
├── demo/
│   ├── Greeting.java
│   ├── VietnameseGreeting.java
│   └── Main.java
└── META-INF/
    └── services/
        └── demo.Greeting
~~~

`src/demo/Greeting.java`:

~~~java
package demo;

public interface Greeting {
    String greet(String name);
}
~~~

`src/demo/VietnameseGreeting.java`:

~~~java
package demo;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {}

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

`src/demo/Main.java`:

~~~java
package demo;

import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeting> loader = ServiceLoader.load(Greeting.class);
        for (Greeting provider : loader) {
            System.out.println(provider.greet("An"));
        }
    }
}
~~~

The **verbatim** content of the `src/META-INF/services/demo.Greeting` resource is a single line containing the fully qualified provider class name:

~~~text
demo.VietnameseGreeting
~~~

Run from the directory containing `src` (PowerShell, machine with JDK 17+):

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/Greeting.java src/demo/VietnameseGreeting.java src/demo/Main.java
Copy-Item -Recurse -Force src/META-INF out/META-INF
java -cp out demo.Main
~~~

Application stdout:

~~~text
Xin chào, An
~~~

The `META-INF/services/demo.Greeting` resource must exist on the **runtime class path** (here `out`), not merely in the source tree. In real JARs, inspect with `jar tf plugin.jar`. To have multiple providers, add class names to the provider file or package providers in separate JARs; the host depends only on `Greeting`. In real deployments, `api.jar`, `host.jar`, and individual `provider.jar`s are usually split.

### 5.2. Understand the Limitations Accurately

- `ServiceLoader.load(ServiceType.class)` defaults to using the thread's context class loader for this common overload; there is also an overload accepting a class loader to choose the provider search scope. With named modules, services can be declared directly in the module descriptor.
- Providers are discovered by name and metadata, yet iteration/instantiation can throw `ServiceConfigurationError` due to a wrong name, inaccessible class, malformed configuration, missing dependency, or invalid constructor/provider method. Errors thrown while executing provider code can also be other business errors.
- `ServiceLoader` caches loaded providers; `reload()` clears that loader instance's cache to re-iterate. It **does not automatically load new JARs into the old class loader**, does not destroy plugin objects currently in use, and does not create a complete hot-reload mechanism.
- Do not rely on provider order as a business priority rule. If multiple implementations exist, clearly define `id`, capability, priority, duplicate-ID handling, selection policy, and error reporting.
- When providers need configuration, database connections, secrets, or large dependencies, use a provider factory/adapter or a DI container; `ServiceLoader` only performs **discovery/instantiation per SPI rules**, not full dependency injection container or lifecycle management.

**Exercise:** add `EnglishGreeting` so both providers are discovered. Then define `String id()`, select the provider by `id`, and test missing or duplicate provider cases. Complete this exercise before moving to automatic reflection.

## 6. Stage 3 — Java Platform Module System (JPMS)

JPMS (Java 9+) adds module-level dependency declarations and encapsulation. Learn it after class path/SPI to recognize the difference between **a class existing** and **a module being able to read/access the class**.

| Keyword in `module-info.java` | Essential Meaning |
| --- | --- |
| `requires x;` | Current module depends on and reads module `x` |
| `exports pkg;` | Allows other modules to access public types in package `pkg` per module rules |
| `exports pkg to x;` | Exports the package's public API only to specified modules |
| `opens pkg;` / `opens pkg to x;` | Allows deep reflection within the declared scope; not equivalent to `exports` |
| `uses pkg.Service;` | Declares that the module consumes the service |
| `provides pkg.Service with impl.Provider;` | Registers a provider inside a named module |

Example of **three illustrative descriptor files**, belonging to three independent modules (not placed together in one file):

~~~java
// module-info.java of greeting.api
module greeting.api {
    exports greeting.spi;
}

// module-info.java of greeting.host
module greeting.host {
    requires greeting.api;
    uses greeting.spi.Greeting;
}

// module-info.java of greeting.provider
module greeting.provider {
    requires greeting.api;
    provides greeting.spi.Greeting with greeting.impl.VietnameseGreeting;
}
~~~

The provider implementation must satisfy the contract/conditions required by `ServiceLoader` in modules. When using the module path, what also matters is **whether the module is resolved into the active layer**; when necessary, verify launch flags/`--add-modules` or create an appropriate layer. Do not assume simply moving a JAR onto the module path makes all providers automatically present.

`exports` grants access to public APIs; `opens` serves deep reflective access to non-public members. With JDK 17+, code relying on reflection into internals is blocked by strong encapsulation by default. `--add-opens` is a scoped compatibility/diagnostic tool, not an ideal API design. A named module is not synonymous with a security sandbox for plugins.

**Exercise:** run the SPI example with three modules, giving the host visibility only to the API package; try reflecting into a private field of a class in another module and explain the access failure; fix with a narrow `opens` declaration when that access is legitimately permitted.

## 7. Stage 4 — Reflection and Annotations: Reading Metadata, Invoking Permitted Behavior

Reflection answers "which constructors/methods/annotations does this class have?" via `Class`, `Constructor`, `Method`, `Field`, and `Annotation`. It suits framework binding, serialization, dependency injection, or building a metadata-driven registry. **Prefer direct interface calls** when the contract is known at compile time; reflection only adds value when types/members are determined dynamically.

Self-contained example (Java 17+), file `ReflectionDemo.java`:

~~~java
public class ReflectionDemo {
    public static class Greeting {
        public Greeting() {}

        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName("ReflectionDemo$Greeting");
        Object instance = type.getDeclaredConstructor().newInstance();
        Object result = type.getMethod("greet", String.class).invoke(instance, "An");
        System.out.println(result);
    }
}
~~~

Run `javac ReflectionDemo.java` then `java ReflectionDemo`; stdout:

~~~text
Hello, An
~~~

The `$` symbol in the binary name denotes a nested class in the example; if moved to a dedicated package, use the appropriate fully qualified name. `getMethod` searches public methods; `getDeclaredMethod` inspects only directly declared methods and **does not automatically grant access to private members**.

### Annotations to Learn Alongside Reflection

- Create annotations with `@Retention(RetentionPolicy.RUNTIME)` if you want to read them at runtime; `SOURCE` or `CLASS` does not provide runtime visibility.
- Choose the right `@Target` (TYPE, METHOD, FIELD...). When designing a plugin registry, annotations are merely **metadata**; you still need mechanisms for class discovery, type validation, instantiation, and lifecycle management.
- Do not scan every package or every JAR arbitrarily. Class path/module path scanning depends on packaging, scope, performance, and deployment environment; choose a battle-tested library/framework when scanning is genuinely needed.

**Common errors:** wrong casts; invoking methods with mismatched parameter types; inaccessible constructors; method exceptions wrapped in `InvocationTargetException`; `InaccessibleObjectException` because a module did not open a package; class/method renames breaking string-based lookups during refactoring. Always preserve error context and restrict the allowlist of loadable types.

## 8. Stage 5 — Dynamic Proxies, Decorators, and MethodHandle

### 8.1. Choose a Proxy to Wrap Interface Behavior

A JDK dynamic proxy creates an object implementing one or more **interfaces**. `InvocationHandler` receives the method/arguments and decides whether to forward, add logging, metrics, transaction boundaries, or validation. It **does not discover providers**, is not a class loader, and does not modify the target class's original bytecode. If you only need to wrap a specific component in static code, a decorator is often simpler to understand and debug.

Standalone example `ProxyDemo.java` on Java 17+:

~~~java
import java.lang.reflect.Proxy;

public class ProxyDemo {
    public interface Greeting {
        String greet(String name);
    }

    static final class RealGreeting implements Greeting {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        Greeting target = new RealGreeting();
        Greeting proxy = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[] { Greeting.class },
                (self, method, arguments) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return method.invoke(target, arguments);
                    }
                    System.out.println("Before: " + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } finally {
                        System.out.println("After: " + method.getName());
                    }
                });

        System.out.println(proxy.greet("An"));
    }
}
~~~

Commands: `javac ProxyDemo.java` and `java ProxyDemo`. Exact stdout:

~~~text
Before: greet
After: greet
Hello, An
~~~

In production, handle `Object` methods (such as `equals`/`hashCode`/`toString`), default methods, exception unwrapping (`InvocationTargetException`), null arguments, concurrent calls, and module access limits. Having a handler call back into the same proxy can cause infinite recursion. For classes without interfaces, JDK `Proxy` is insufficient; subclass/bytecode-generating libraries carry their own trade-offs around `final`, constructors, methods, and module access.

### 8.2. Learn MethodHandle After Understanding Reflection

`MethodHandle` in `java.lang.invoke` represents a callable method/field target with an explicit type (`MethodType`) and the ability to compose/adapt calls. `MethodHandles.Lookup` is tied to the caller's access rights; it is not a "pass to bypass encapsulation". `privateLookupIn` must satisfy module/`opens` rules when crossing module boundaries.

You do not need to dive deeply into `invokedynamic` or `LambdaMetafactory` at the start. That track fits when building runtimes/frameworks, code generation, or optimizing dynamic call mechanics after **measuring with appropriate benchmarks**. Do not assume by default that `MethodHandle` is always faster than `Method.invoke` in every scenario; JIT, call-site shape, and warmup all have an impact.

## 9. Stage 6 — Plugin JARs Outside the Class Path, Dedicated Class Loaders, and Isolation

Once SPI works inside a fixed distribution, new problems typically involve loading libraries from `plugins/*.jar`, letting plugins depend on different versions, enabling/disabling plugins, and reclaiming resources. Only then should you consider `URLClassLoader` (classpath-style plugins) or `ModuleLayer` (modular plugins) with a clear architecture.

**Basic model:**

~~~text
Host application
    |
    +-- Parent / shared API loader --> plugin-api.jar (interface, DTO)
    |
    +-- Plugin loader A -----------> plugin-a.jar + dependencies A
    |
    +-- Plugin loader B -----------> plugin-b.jar + dependencies B
~~~

Keep the shared communication API in a class loader visible to both host and plugins. Plugin implementations can live in child loaders; if a plugin packages a duplicate copy of the API and redefines it in another loader, casting to the host's interface can fail despite identical full names.

An **illustrative snippet, not a standalone program**, for when a plugin JAR already exists and the API is shared:

~~~java
try (var loader = new java.net.URLClassLoader(
        new java.net.URL[] { pluginJar.toUri().toURL() },
        Greeting.class.getClassLoader())) {
    var services = java.util.ServiceLoader.load(Greeting.class, loader);
    for (Greeting provider : services) {
        provider.greet("An"); // Use within the loader lifecycle scope
    }
}
~~~

Here `pluginJar` is a `Path` variable and `Greeting` is a service API already defined in the application; running the example requires supplying a valid JAR with provider metadata. `URLClassLoader.close()` closes opened resources/files, and **does not immediately unload classes or destroy instances**. For a loader to become eligible for GC, you must shut down the plugin, stop threads/executors, remove listeners/timers/registries/static caches, clean up `Thread.contextClassLoader`, and drop all strong references retaining the loader/classes/instances. Hot-reload is **the lifecycle of the entire plugin/class loader**, not merely calling `reload()`.

Only implement child-first loading with a clear reason and an understanding of which packages/APIs must always be defined by the parent; flawed custom delegation causes split packages, duplicate types, `LinkageError`, and hard-to-debug bugs. `ModuleLayer` addresses module scoping/resolution under JPMS, but does not by itself turn a plugin into a secure isolation environment or complete lifecycle manager.

### Designing a Real-World Plugin Contract

A mature plugin system typically defines:

- **Identity/capability:** ID, name, API version, supported feature set, and duplicate-ID conflict policy.
- **Lifecycle:** `discover → validate → configure → start → invoke → stop → release`; each step has explicit states and errors.
- **Compatibility:** semantic versioning, stable API/DTOs; test binary compatibility between the host and providers compiled against older versions.
- **Resource ownership:** threads, sockets, connection pools, file handles, shutdown hooks, listeners, TCCL; whoever opens them is responsible for closing them.
- **Failure isolation:** timeouts, circuit breakers, or business-level provider-disabling rules; one failing plugin should not halt everything when recovery is possible.
- **Trust:** load JARs only from trusted sources, verifying distribution/signatures/hashes when required. **Class loaders and JPMS are not a sandbox** for running malicious or untrusted code in the same JVM.

## 10. Stage 7 — Instrumentation and Java Agents (Learn Last)

`java.lang.instrument` lets agents observe/transform bytecode as classes are loaded or via capabilities supported by the JVM. Use it when building APMs, profilers, coverage tools, tracing, or framework tooling that must intervene where no interface-based extension point exists. This solution has broad impact and is harder to diagnose than SPI/proxies.

Concepts to learn in order:

1. **Class files/bytecode:** constant pool, method descriptors, verifier, stack frames; try `javap -c -p SomeClass`.
2. **Agent startup:** JAR with `Premain-Class` manifest entry, agent class having `public static void premain(String, Instrumentation)`, run the app with `-javaagent:path/to/agent.jar`.
3. **Transformer:** `ClassFileTransformer` receives class bytes along the JVM lifecycle; understand class loader context, package filtering, idempotency, and avoiding self-instrumenting agent classes.
4. **Redefine/retransform:** distinguish `redefineClasses` from `retransformClasses`; support is an **optional capability**, requires corresponding manifest/capabilities, and carries JVM limits on structural class changes.
5. **Bytecode libraries:** consider Byte Buddy for common use cases; ASM/JVMS fit when low-level intervention is truly needed and you understand the verifier.
6. **Operations:** overhead, ordering of multiple transformers/agents, startup failures, class loader leaks, logging, deployment policies, JDK compatibility.

**Illustrative signature example, not standalone runnable**:

~~~java
import java.lang.instrument.Instrumentation;

public final class ObservationAgent {
    public static void premain(String arguments, Instrumentation instrumentation) {
        System.out.println("Agent started before main");
        // Register ClassFileTransformer if there is a specific requirement.
    }
}
~~~

To run, this class must be packaged into an agent JAR with `Premain-Class: ObservationAgent` in the manifest and passed to the JVM with `-javaagent:...`; merely writing a `premain` method in source code is not enough. Do not conflate instrumentation with plugin business logic, and do not abuse agents to "patch" poorly designed APIs.

## 11. Choosing a Mechanism by Situation

| Practical Need | Starting Choice | When to Upgrade |
| --- | --- | --- |
| Swapping strategies known upfront in the app | Interface + DI/factory/strategy | Need externally built providers → SPI |
| Vendors distribute implementations as JARs | `ServiceLoader` + service API | Need post-startup JAR loading/dependency isolation → loaders/layers |
| Reading metadata/annotations or calling methods by config | Reflection with allowlist and validation | Need composed calls/specialized optimization → `MethodHandle` |
| Attaching logging, metrics, validation around an interface | Decorator or JDK dynamic proxy | Need to intercept concrete classes → bytecode proxy tool with clear constraints |
| Multiple plugins use conflicting library versions | Dedicated loaders + shared API + lifecycle | Complex modular plugins → JPMS layers |
| Tracing methods in code with no extension point | Instrumentation/agent | Need fine-grained bytecode control → Byte Buddy/ASM |
| Running **untrusted** code | Separate process/container and OS-level permission controls | Do not use custom class loaders/JPMS as a security barrier |

**Selection principle:** solve at the lowest layer that still meets requirements. A stable API + explicit discovery usually beats reflection scanning the entire class path; proxies around interfaces are usually easier to test than bytecode instrumentation; custom loaders need a lifecycle plan before implementation.

## 12. Integrated Hands-On Labs by Milestone

### Lab A — Extension Contract (Stages 0–1)

- Design `ReportExporter` with `String format()` and `byte[] export(Report input)`.
- Implement `CsvExporter` and `TextExporter`; use a factory selecting by input; test outputs, unsupported-format errors, and exception policies.
- Observe the class loaders and packages of both implementations; package and run from a JAR.

**Done when:** the host knows only the interface, swapping exporters does not touch report-export logic, and you understand where API and implementations reside.

### Lab B — Service Discovery (Stages 2–3)

- Package service API, host, and provider separately; register `META-INF/services`.
- Add a second provider without editing the host. When a provider is missing, print a clear message instead of silently producing empty output.
- Deliberately test misspelled resource names, providers lacking a proper constructor, and missing dependencies, and observe root causes.
- Migrate to JPMS `uses/provides`; inspect differences between class path and module path.

**Done when:** you know exactly where providers are discovered from and why failures occur.

### Lab C — Metadata and Cross-Cutting Behavior (Stages 4–5)

- Create a runtime annotation `@PluginInfo(id="csv")`; read it from the provider class and validate the ID.
- Call only the public API via the interface; test a counterexample of `setAccessible(true)` when a module does not open the package.
- Wrap `ReportExporter` with a JDK proxy, measure duration, and log each invocation; catch provider errors and preserve the cause.

**Done when:** you distinguish contract, metadata, discovery, and interception as four separate responsibilities.

### Lab D — Small Plugin Platform (Stage 6, Optional)

- Host reads a single JAR at an operator-specified path; uses a dedicated loader and `ServiceLoader.load(ServiceType.class, loader)`.
- Ensure the service API is shared via the proper loader; test rejecting a plugin with an incompatible API version.
- Shut down the plugin: stop executors/listeners, close resources, drop references, close the loader; verify with logs/heap dumps when leaks are suspected.
- Test a failing plugin and two plugins needing different dependency versions; document the practical limits of the chosen approach.

**Done when:** the host reports lifecycle, errors, versions, and JAR source; never rely on arbitrary restarts to hide resource management bugs.

### Lab E — Agent Only for the Advanced Track (Stage 7)

- Write an agent logging when `premain` runs; verify the agent starts before the application's `main`.
- Once you understand class files, add a transformer that only observes specific classes and returns bytes unchanged; then try safe transformations using a battle-tested library.
- Measure overhead, test class loading, and verify fallback when the agent is disabled.

**Done when:** you can explain manifests, transformer lifecycles, and why agents require broader testing than ordinary plugins.

## 13. Common Errors and Systematic Diagnosis

| Symptom | First Direction to Check |
| --- | --- |
| `ServiceLoader` does not see provider | Is provider resource exactly `META-INF/services/<FQCN>`; is it in the JAR; is context loader/module layer right; was the module resolved |
| `ServiceConfigurationError` | Class name, implements service, provider instantiation/constructor, visibility, dependencies, and root exception |
| `ClassNotFoundException` | Binary name, class path/module path, active loader, actual JAR contents |
| `NoClassDefFoundError` / `NoSuchMethodError` | Transitive dependencies, class initialization failure, binary version mismatch between compile/runtime |
| `ClassCastException` despite identical class names | Compare `type.getClassLoader()` and the interface/shared API's loader; check if plugin bundled duplicate API |
| `InaccessibleObjectException` | `module-info.java`, `opens`, which module performs reflection; limit `--add-opens` workarounds |
| Memory leak after stopping plugin | Threads/TCCL, registries, static caches, listeners, instances, references to `Class` and loader |
| Agent does not run | `-javaagent`, `Premain-Class`, exact method signature, JAR, and JVM capabilities |
| Slow execution or hard-to-trace errors | Measure latency/initialization, exception cause, discovery scope, test without proxy/agent, benchmark before optimizing |

Tools to use at the right time: `jar tf file.jar` to inspect packaged resources/classes; `javap -p -c ClassName` to inspect signatures/bytecode; `jdeps` to inspect dependencies; `java --show-module-resolution ...` to view the module graph; `java -Xlog:class+load=info ...` to view class loading logs on JVMs supporting unified logging. Do not assume output formatting, class loading order, or unloading timing are stable across environments.

## 14. Self-Assessment Criteria and Priority Order When Applying

After this roadmap, learners should be able to answer and demonstrate with small programs:

1. **When are interfaces + DI enough, and when is SPI needed?** Know how to choose without introducing unnecessary reflection or class loaders.
2. **How does `Class.forName` differ from `ServiceLoader`?** One loads a class by name; the other discovers registered providers under a service contract.
3. **Why can a plugin with the same class name still fail to cast?** Point out that class identity equals name + defining loader.
4. **Why does `exports` not replace `opens`?** State the difference between public API access and deep reflection.
5. **Does a proxy make the host discover plugins?** No; a proxy wraps/routes calls along an already-known interface.
6. **Does `reload()` "hot deploy" a new JAR?** No; class loader and plugin lifecycle must be handled explicitly.
7. **Why is a Java agent the last step?** It intervenes broadly in the runtime, has capability/verification conditions, compatibility risks, and higher overhead than ordinary extension points.
8. **How do you test reliability?** Test missing providers, broken providers, version mismatches, shutdown, reloading, logging, resource leaks, and maintaining compatibility.

**Pragmatic roadmap for most projects:** master Java Core + JAR/class path → understand class loading → design contracts → use `ServiceLoader` → learn JPMS/strong encapsulation → reflection/annotations → proxies/MethodHandle → only then learn dedicated loaders and instrumentation if the problem genuinely requires them. The most important outcome is not using as many "dynamic" techniques as possible, but **building clear, stable, observable, and lifecycle-managed extension points**.

## 15. Standard References for Further Lookup

- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API, `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Proxy` and `InvocationHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- Java SE 17 API, `MethodHandles`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 API, `java.lang.instrument`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JPMS and `--add-opens`: https://dev.java/learn/organizing/modules/add-exports-opens/
- JDK 17 migration and strong encapsulation: https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html