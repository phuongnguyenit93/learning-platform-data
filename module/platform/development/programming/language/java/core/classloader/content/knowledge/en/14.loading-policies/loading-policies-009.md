# Trade-offs Between Isolation, Compatibility, and Diagnosability in Java Class Loading Policies

When implementing a plugin system, application server, test runner, dynamic scripting engine, or an application that supports multiple library versions, you must choose a **class loading policy**. The key decision is not merely writing `new ClassLoader(...)`, but deciding **which class is defined by which loader, which classes are shared, and how loading activity is observed**.

Three goals often pull in different directions:

- **Isolation:** restricts different versions or components from seeing or interfering with one another; allows the same binary class name to be defined in different loaders.
- **Compatibility / interoperability:** ensures the host and plugins use **the same runtime type** for communication APIs, without breaking resolution, visibility, method linkage, and framework contracts.
- **Diagnosability / observability:** when a `ClassCastException`, `NoSuchMethodError`, `ClassNotFoundException`, or incorrect resource lookup occurs, allows you to determine precisely **who requested the load, who defined the class, what the bytecode source is, and what delegation policy was applied**.

No single policy optimizes all three. **Parent-first** generally prioritizes sharing and compatibility; **selective child-first** increases isolation for private dependencies; **recording loader identity and the resolution process** aids diagnosis at the cost of added operational complexity.

## 1. Foundational Model: Runtime Type Is More Than Just Class Name

Java identifies a runtime class or interface by two factors:

~~~text
Runtime type identity = (binary name, defining class loader)
~~~

For example:

~~~text
plugin.impl.Greeting defined by loader A
plugin.impl.Greeting defined by loader B
~~~

These two types share the same name `plugin.impl.Greeting`, but they are **two distinct runtime types** if A and B are different defining loaders.

Conversely, two child loaders A and B can call `loadClass("api.Plugin")` and both receive **the exact same** `Class<?>` defined by the parent. In that case, the `api.Plugin` API is shared.

Common diagram:

~~~text
                     Bootstrap / platform
                             |
                         App loader
                       defines api.Plugin
                        /            \
                       /              \
            Plugin loader A       Plugin loader B
            defines ImplA         defines ImplB
                       \              /
                        \            /
                   Host uses api.Plugin
~~~

If a plugin loader redefines `api.Plugin` instead of delegating to the app loader, a class `implements api.Plugin` inside the plugin may implement **a different runtime interface** from the host's `api.Plugin`, even though the package and class name are completely identical.

### Defining Loader and Initiating Loader

The **defining loader** is the loader that actually creates the class definition (typically via `defineClass`). `Class.getClassLoader()` returns the defining loader.

The **initiating loader** may be the loader that initiated the `loadClass` request and then delegated to its parent; it is not necessarily the defining loader.

~~~java
Class<?> target = pluginLoader.loadClass("api.Plugin");
ClassLoader defining = target.getClassLoader();

System.out.println(defining == pluginLoader);
~~~

This is an **illustrative snippet**, assuming `pluginLoader` has been created and the API can be found. A `false` result is completely normal if the API is defined by the parent.

Do **not** infer the defining loader from the JAR name, loader name, classpath, or whether a `loadClass` method logs receiving a request.

## 2. Parent-First: Compatibility First, Versions Depend on the Parent
`ClassLoader.loadClass` by default asks the parent first and only falls back to the child's `findClass` if no definition is found. This allows plugins to share APIs and libraries managed by the host. In return, `lib.Parser` in the parent can **shadow** a version bundled in a plugin; the class loads, but a method the plugin compiled against may be missing, leading to `NoSuchMethodError`.

The operational benefit is fewer loader-specific overrides, but this only holds when dependency ownership and **binary compatibility** are controlled. Parent-first does not guarantee that every plugin is compatible with every library in the parent.

## 3. Child-First: Selective Isolation, Must Protect Boundaries
For private dependencies shadowed by the host, child-first can prefer the plugin's bytecode first. This allows two plugins to use the same binary name with two different versions, but it only works effectively if they do not exchange those implementation types directly across the host API.

Keep `java.*`/platform classes and shared interfaces, DTOs, annotations, and exception types in the shared loader. Child-first does not automatically change `getResource`/ServiceLoader or bypass JPMS, is not a security sandbox, and increases diagnostic and metadata overhead when creating multiple class definitions. The real question is **which namespaces truly must be independent**, rather than switching the entire application to child-first.

## 4. Policy Comparison

| Criterion | Parent-first | Full child-first | Selective child-first |
|---|---|---|---|
| Host/plugin API sharing | Favorable | Easy to accidentally duplicate types | Favorable if API is kept in parent |
| Isolating same-named library versions | Limited | Higher | High for selected namespaces |
| Default predictability | Easier | Depends on overrides | Depends on prefix list / rules |
| `ClassCastException` risk from duplicate API | Lower | High | Low if boundaries are well-designed |
| Method/linkage incompatibility risk | Yes, if parent version is wrong | Yes, at shared boundaries | Yes, requires testing |
| Resource lookup aligned with class | Easier to understand with default delegation | **Not automatically synchronized** | Must be designed explicitly |
| Debugging loader identity | Usually simpler | More complex | Requires logging specific policy |
| Configuration management overhead | Lower | Higher | Medium–high |
| Suitability for multi-version plugins | When APIs/dependencies are uniform | Only in controlled designs | Usually the balanced choice |

No column is "more secure" in the sense of safely running untrusted code. All three options still run inside the same JVM/process unless you design real isolation boundaries on top.

## 5. Design the Shared Boundary Before Choosing a Policy

A sound organization for a plugin runtime:

~~~text
Application classloader
  api.Plugin
  api.PluginContext
  shared DTO / public contracts
          |
          +-- Child loader A
          |    plugin.impl.Greeting
          |    plugin.internal.*
          |    private dependencies v1
          |
          +-- Child loader B
               plugin.impl.Greeting
               plugin.internal.*
               private dependencies v2
~~~

Principles:

1. **Shared APIs must have a single, unified defining loader.** Place `api.Plugin`, callback interfaces, and truly shared DTOs in the parent.
2. **Each plugin's implementation can be child-first** if the host does not need to link directly to implementation classes by name.
3. **Restrict private implementation types from crossing boundaries.** Communicate through `api.Plugin` or shared DTOs defined by the parent.
4. **Inspect transitive dependencies**, not just top-level plugin classes. A plugin dependency may reference a class for which the parent already provides an incompatible version.
5. **Have a strategy for resources and services.** Child-first for classes **does not automatically** make `getResource` child-first; a resource with the same name may still come from the parent.
6. **Design the lifecycle.** A loader does not automatically unload classes when a plugin is "disabled"; you must release retained references and resources.
7. **Respect JPMS boundaries** when using named modules. Module readability/exports/opens differ from custom `URLClassLoader` policies.

## 6. Case Study: Choosing a Policy for Two Plugins When the Host Has an Older Dependency
Suppose the host contains `lib.Parser` v1 and the public SPI `api.Plugin`; plugin A uses Parser v1, while plugin B is compiled against Parser v2, which adds `parse(byte[])`. Both plugins must implement **the exact same runtime `api.Plugin`** from the host.

| Option | Behavior for plugin B | API contract and operations |
| --- | --- | --- |
| Keep parent-first with v1 in parent | B may receive Parser v1 and throw `NoSuchMethodError` when calling the v2-only method | Easy loader management, but fails functional requirements |
| Remove Parser from parent, place matching version in each plugin URL | Both A and B define their own Parser version even under standard parent-first | Preferred when this dependency is truly private; API remains defined by parent |
| Keep Parser v1 in parent, use selective child-first for private `lib.*` | B prefers Parser v2 if the child JAR contains all required dependencies | Must audit transitive dependencies, fallback, resources, and sealed packages |
| Shading/relocating Parser v2 | Renames binary names to avoid colliding with the host | Build must update reflection, resources, and service descriptors where needed |
| Run plugin B in a separate process/JVM | No direct class identity with the host | Requires IPC protocol/schema, higher deployment and operational cost |

### 6.1. Diagnostic Outcomes by Case

```text
B calls lib.Parser.parse(byte[])
  ├─ Parser defined by parent, missing signature      → NoSuchMethodError
  ├─ Parser v2 defined by child, signature exists     → call can succeed
  ├─ child redefines api.Plugin                       → host may fail to cast
  └─ v2 class + config from parent v1                 → may misbehave without linkage error
```

Before deciding, record the failing class, `getClassLoader()`, `CodeSource` when available, the actual class JAR, method name/descriptor via `javap -s`, resource URLs, and the loader used by `ServiceLoader`. Finding a class does not prove the runtime used the right version.

### 6.2. Post-Change Verification Matrix

1. **Host API:** `api.Plugin` from the plugin loader must be the exact `api.Plugin.class` of the host; test casting an implementation instance.
2. **Dependency ownership:** Parser A and B must be defined by their intended loaders; compare two `Class<?>` instances with the same name using `==` and invoke the actual v2 method.
3. **Missing local class:** test a name that exists only in the parent. Choose fallback if approved, or fail closed for private namespaces that must remain strictly isolated.
4. **Resource/SPI:** place a resource with the same name in both parent and child, and test both `getResource` and `getResources`; for service descriptors, ensure all valid providers are preserved.
5. **Lifecycle:** reload B with a new loader, stop threads/callbacks, and clean up TCCL and caches; `close()` does not guarantee immediate unloading.
6. **Observability:** provide a stable loader ID, the matched class/package rule, and the actual source; do not log secret contents.

This case study does not mandate a single custom classloader. It forces you to define **which dependencies belong to the parent**, **the shared communication channel**, and **how to prove the actual version at runtime** before deploying.

## 7. Why Does Full Child-First Easily Break Compatibility?

Suppose the host compiles against:

~~~java
package api;
public interface Plugin {
    String message();
}
~~~

If full child-first redefines `api.Plugin` from a copy inside the plugin JAR, the class in the plugin implements **a different `api.Plugin`**. The host cannot directly cast that object to its own interface.

~~~text
Host:  (api.Plugin, AppLoader)
Plugin:(api.Plugin, ChildLoader)

Same name, different runtime type.
~~~

This typically leads to a `ClassCastException` when the host casts the object directly. In addition, the JVM may encounter loading constraints or other linkage errors if the two type definitions are combined in a signature. Not every failure produces the same exception; read the stack trace and identify **whether it occurred at load, resolve, initialize, or cast time**.

**A balanced approach:**

- Parent-first: `java.*`, `javax.*` where appropriate, host/plugin public APIs, shared DTOs/exceptions, logging facades, or contracts used across the boundary.
- Selective child-first: `plugin.impl.*` and private implementation namespaces that genuinely require isolation.
- For shaded/relocated libraries, verify that binary names have changed and avoid letting plugins export private library classes directly through the shared API.
- Shared namespaces should be planned as a list with clear ownership; do not add uncontrolled "exceptions".

## 8. Compatibility Covers API, ABI, Modules, and Lifecycle

### 8.1. Binary Compatibility

Sharing a class from the parent does not guarantee that a plugin compiled against v2 will run with v1. For example, if `foo(int)` only exists in the newer version, the plugin may load the older `lib.Util` class, but when resolving the call to `foo(int)`, the JVM throws `NoSuchMethodError`.

Therefore, you need to test:

- Method/field signatures and inheritance used by the plugin.
- Bytecode `--release` version and runtime JDK.
- Transitive dependencies and the versions actually loaded by the JVM.
- Reflection calls, method handles, and service provider discovery.

### 8.2. Package-Private and Runtime Packages

The JVM determines a runtime package from **package name + defining loader**. Two classes in the same `package p;` but loaded by different loaders **do not automatically have package-private access** to each other. You can hit `IllegalAccessError` even though `javac` allowed the same package at compile time.

Do not split classes that rely on package-private access across different defining loaders unless you have deliberately redesigned the boundary into an appropriate public API.

### 8.3. JPMS Does Not Replace Classloader Policies

Named modules have `requires`, `exports`, `opens`, readability, and encapsulation. A loader hierarchy does not automatically bypass those boundaries.

Creating `new URLClassLoader(urls, parent)` does not automatically resolve a JAR into a named module just because the JAR contains `module-info.class`. For modular applications, evaluate `ModuleLayer`, module configuration, and module loaders using the proper mechanism.

### 8.4. Serialization and Communication Across Loader Boundaries

If the host and plugin share a DTO or exception, place that type in the shared loader. Java serialization with classes defined by separate loaders can run into type resolution issues on the receiving side. Do not rely on matching class names to treat them as interchangeable.

For long-lived boundaries, use explicitly versioned APIs or stable schemas/formats (JSON, protocol messages, etc.) when deployment or process separation is needed.

### 8.5. Unloading and Leaks

Closing a `URLClassLoader` closes file handles, but classes are not unloaded immediately. References to `Class<?>`, plugin instances, thread context class loaders, static caches, `ThreadLocal`s, running threads, or callbacks can keep a loader alive indefinitely.

If hot redeploy is a priority, design the **plugin lifecycle** from the start: stop threads, close resources, unregister callbacks, clear caches, reset TCCL, and drop references. Isolation supports redeployment, but it does not perform those cleanup steps for you.

## 9. Diagnosability: What to Log and What Not to Log

### 9.1. Minimum Diagnostic Context

When investigating a classloading failure, log the following information:

| Field | Example / meaning |
|---|---|
| Binary name | `plugin.impl.Greeting` |
| Defining loader class | `PolicyLoader` or built-in app loader |
| Loader name | `"child-first"`, label only |
| Loader object identity | Compare with `==`; `identityHashCode` only helps within-process logging and is **not strictly unique** |
| Parent chain | Which loader is the parent at each step |
| CodeSource / source URL | JAR/file source if the JVM provides this metadata |
| Resource URL | The specific resource selected |
| TCCL | `Thread.currentThread().getContextClassLoader()` |
| Runtime module | `type.getModule()` |
| Error chain | Class/linkage exception and nested causes |

Do not log secrets, API keys, or the full contents of sensitive configuration files just for diagnostics. For dynamic policies, log **which prefix rule was applied** and which loader actually defined the class.

### 9.2. Class Diagnostic Snippet

~~~java
static void explain(Class<?> type) {
    ClassLoader loader = type.getClassLoader();

    System.out.println("name=" + type.getName());
    System.out.println("module=" + type.getModule().getName());
    System.out.println("loader-name="
            + (loader == null ? "<bootstrap>" : loader.getName()));
    System.out.println("loader-class="
            + (loader == null ? "<bootstrap>"
                : loader.getClass().getName()));
    System.out.println("loader-id="
            + (loader == null ? 0
                : System.identityHashCode(loader)));
}
~~~

This is an **illustrative method**, without a `main`. `Module.getName()` can return `null` for an unnamed module. `identityHashCode` can collide between two objects in the same JVM, so use it only as a logging clue, **not as a unique immutable identifier**; if possible, record a logical ID assigned to each loader from your application's registry.

To trace a class's origin:

~~~java
Class<?> type = obj.getClass(); // obj must be non-null

var domain = type.getProtectionDomain();
var codeSource = domain == null ? null : domain.getCodeSource();

System.out.println(codeSource == null
        ? "source unavailable"
        : codeSource.getLocation());
~~~

This is an **illustrative snippet**; not every class has a useful `CodeSource`, and the value may be `null`. Do not guess the source URL from the string `type.getName()`.

### 9.3. HotSpot Logging

On HotSpot/JDK 17+, you can enable Unified Logging:

~~~bash
java -Xlog:class+load=info,class+unload=info -jar app.jar
~~~

The output depends on the JDK and can include information for a very large number of classes; this is a **diagnostic command**, not part of a demo's expected stdout. To investigate issues in production, enable focused logging for a short window, filter by class/plugin, and preserve enough context about the defining loader.

Tools like `jcmd`, Java Flight Recorder (JFR), or a profiler can supplement classloader counts, classloading/unloading events, and allocations when supported by the runtime. Do not assume a single event contains full details of every delegation step.

### 9.4. When a Resource Has the Same Name but the Wrong Version

Always verify the actual URL returned:

~~~java
URL found = loader.getResource("plugin/config.txt");
System.out.println(found);
~~~

This is an illustrative snippet and may return `null`. With `URLClassLoader`, you can compare `getResource` (which includes parent delegation) against `findResource` (which searches only the loader's own sources) to pinpoint conflicts.

## 10. Troubleshooting Playbook by Symptom

### `ClassCastException: X cannot be cast to X`

1. Identify the source `Class<?>` and target `Class<?>` — do not just read `getName()`.
2. Print `getClassLoader()` for both and compare with `==`.
3. Check which interface/DTO was defined redundantly by the child as well as the parent.
4. Move the shared API to the parent or change the boundary to an explicit contract.
5. If two independent versions must run side by side, do not cast directly across private implementation classes.

### `NoSuchMethodError` / `NoSuchFieldError`

1. Identify the binary name of the class containing the failing method/field.
2. Check the defining loader and `CodeSource` of the class actually loaded.
3. Compare the actual signature against the version the plugin was compiled with.
4. If parent-first is shadowing a newer dependency, consider child-first **for the appropriate implementation library**, rather than changing the entire policy.
5. Run integration tests with a classpath and deployment layout matching production.

### `ClassNotFoundException`

1. Verify that the binary name matches the package.
2. Check URL roots/JAR entries and file access permissions.
3. Identify which loader received the request: host, plugin loader, TCCL, or framework loader.
4. Check policy prefixes and parent fallback.
5. Do not fix it by adding every JAR to the global classpath if doing so breaks isolation.

### `NoClassDefFoundError`

This does not always mean "a `.class` file is missing." It can also arise from missing dependencies, linkage errors, or a type whose initialization previously failed. Read the `Caused by` chain and the timing of the failure instead of immediately creating a new loader.

### `IllegalAccessError`

Check runtime package identity and module/class access permissions. Having the same package string is not enough if the defining loaders differ. If using JPMS, `exports` and `opens` serve different purposes; do not blindly fix it by "opening all packages."

### `ServiceLoader` Cannot Find a Provider

`ServiceLoader.load(PluginService.class)` typically uses the **thread context class loader (TCCL)** depending on the API overload. If the TCCL is not a loader that can see the provider, lookup can fail even when `pluginLoader.loadClass` finds the class.

In a plugin workflow, you can temporarily set the TCCL within a controlled scope and **must restore it in `finally`**:

~~~java
Thread thread = Thread.currentThread();
ClassLoader original = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Call framework / ServiceLoader when the contract allows.
} finally {
    thread.setContextClassLoader(original);
}
~~~

This is an **illustrative snippet** requiring a valid `pluginLoader` variable. Never change a thread pool's TCCL and forget to restore it; doing so can keep an old plugin loader alive and cause unintended cross-plugin visibility.

## 11. Performance and Operational Impact

| Factor | Strong isolation (many loaders) | Strong sharing (fewer loaders) |
|---|---|---|
| Number of runtime `Class<?>` for duplicate libraries | Can increase | Fewer duplicates |
| Metaspace and metadata overhead | Can increase due to duplicate definitions | Generally lower |
| Ability to run separate dependency versions | Higher | More limited |
| CPU for class loading and resource lookup | Can increase with number of loaders/URLs/delegations | Can be simpler |
| Updating a plugin without updating the host | Favorable when lifecycle is proper | Difficult if classes live in a long-lived loader |
| Diagnosing duplicate class errors | More complex | Fewer cases, though version conflicts still occur |
| Impact of changing a shared API | Requires versioned contracts | Can affect the entire system |

Do not assume "more loaders" is slower by a fixed number: performance depends on class count, JAR size, caching, I/O, JPMS/frameworks, loading patterns, and loader creation/destruction frequency. Measure under realistic workloads using JFR, JVM metrics, and controlled benchmarks.

Avoid creating a new `URLClassLoader` for **every request**. A plugin with a clear lifecycle typically needs a single loader tied to that lifecycle, closed after all plugin work completes.

## 12. A Verifiable Policy Selection Strategy

**Step 1 — Map the boundary types.** List the APIs, DTOs, exceptions, callbacks, and service interfaces used across host and plugins. Where should they be defined?

**Step 2 — Classify packages.** Identify which namespaces are shared APIs and which contain only private implementations or dependencies.

**Step 3 — Default to parent-first.** Keep standard delegation for Java core, platform, and shared APIs.

**Step 4 — Enable child-first only for proven needs.** If a plugin genuinely needs a different dependency version from the host, keep the prefix/namespace as narrow as possible; consider shading/relocation if appropriate.

**Step 5 — Align resource policies.** Verify `getResource`, `getResources`, `ServiceLoader`, TCCL, and config sources; do not assume a class policy automatically carries over to resources.

**Step 6 — Test both happy paths and failure modes.** Include at least tests for parent has class / parent misses / duplicate API / duplicate resource / missing dependency / wrong bytecode version / plugin redeploy.

**Step 7 — Design diagnostics.** Log class name, defining loader, parent chain, `CodeSource`, module, policy branch, and resource URL (without logging secrets).

**Step 8 — Design the lifecycle.** Close streams/JAR handles, stop plugin tasks, reset TCCL, and drop references so the JVM can unload classes when appropriate.

## 13. Testing Checklist

- [ ] Shared APIs are owned by a single defining loader, and both host and plugin see the same runtime type.
- [ ] Child-first is applied only to intentional namespaces, never blindly to `java.*`.
- [ ] A plugin with a different private dependency version still uses the exact bytecode it needs.
- [ ] Tests exist for same-named classes in parent and child to verify the intended loading order.
- [ ] Tests exist for same-named resources in parent and child to verify the order and actual resource URL.
- [ ] `Class.getClassLoader()` is used to confirm the defining loader, rather than relying only on the loader name.
- [ ] Tests cover casting across a shared public interface as well as when the interface is duplicated.
- [ ] Tests cover `ServiceLoader` / TCCL if used by the framework.
- [ ] Tests cover `ClassNotFoundException`, `NoClassDefFoundError`, and `NoSuchMethodError` in meaningful scenarios.
- [ ] Plugins retain no threads, callbacks, static caches, or file handles after stopping.
- [ ] Classloader diagnostics do not log secret contents or cause logging overload.
- [ ] If using JPMS, module layer/readability/exports/opens are evaluated separately.

## 14. Common Misconceptions to Avoid

1. **"Child-first is always better because isolation is stronger."** False: isolating duplicate APIs breaks casts/linkage and adds operational cost.
2. **"Parent-first always guarantees compatibility."** False: the parent may provide a dependency version lacking the binary API a plugin requires.
3. **"Same class name means same type."** False: they must also share the same defining loader.
4. **"If a loader calls `loadClass`, it must be the defining loader."** False: delegation may return a class defined by the parent.
5. **"Child-first for classes automatically makes resources child-first."** False: overriding `loadClass` does not change `getResource`.
6. **"Giving two loaders the same name makes them identical."** False: the name is just a label, not runtime identity.
7. **"Multiple classloaders create a security sandbox."** False: the JVM process still shares access unless separate isolation mechanisms are used.
8. **"Simply closing a `URLClassLoader` unloads its classes immediately."** False: references and GC still govern unloading.
9. **"A JAR with `module-info.class` automatically becomes a named module in `URLClassLoader`."** False: module resolution is a separate mechanism.
10. **"`ClassCastException` can only happen between two differently named classes."** False: duplicate defining loaders can produce a message about casting X to X.
11. **"`NoClassDefFoundError` always means the file was not found."** False: it can also stem from failed class initialization and other linkage causes.
12. **"The TCCL is always the same as the system class loader."** False: the TCCL varies by thread and framework.
13. **"`identityHashCode` is a globally unique loader ID."** False: it can collide and is not stable across processes.
14. **"Turning off logging improves diagnostics."** False: keep traceability at a level appropriate for overhead and security.
15. **"Shading only requires renaming the JAR file."** False: relocation actually rewrites package/binary names; accompanying service and resource metadata must be checked.

## 15. Self-Check Questions

**Question 1.** Plugin A wants to use a newer `lib.Parser`, while the host already has an older `lib.Parser`. Which version will parent-first pick if the parent finds it?

**Answer:** The version defined by the parent, risking missing methods that the plugin needs. You can consider selective child-first for `lib.Parser`, shading/relocation, or aligning dependency versions.

**Question 2.** Why can full child-first cause a `ClassCastException` when casting a plugin to the host's `api.Plugin` interface?

**Answer:** Because the child may define its own `api.Plugin` with a different defining loader; that runtime interface is not the same type as the one used by the host.

**Question 3.** Two child loaders have the same name `"plugin"` and identical bytecode. Do they share a single runtime class?

**Answer:** No, if each loader defines the type itself; matching loader names and bytecode do not make runtime identity equal.

**Question 4.** The class policy is already child-first for `plugin.impl.`. Why might `loader.getResource("plugin/config.txt")` still return a resource from the parent?

**Answer:** Because `ClassLoader.getResource` has its own delegation policy, which searches the parent first by default. Overriding `loadClass` does not alter it.

**Question 5.** When investigating `NoSuchMethodError`, why should you inspect the defining loader and `CodeSource`?

**Answer:** To know which version/JAR the class was actually loaded from, rather than relying only on the build-time dependency tree or expected URL order.

**Question 6.** Is `URLClassLoader.close()` enough to unload a plugin?

**Answer:** No. You must stop plugin tasks, release references, reset TCCL, and close handles; the JVM only unloads classes when conditions allow.

**Question 7.** If you need to test two different implementation versions while still casting objects to a common `Plugin`, where should `Plugin` be placed?

**Answer:** In the shared parent loader, with child loaders configured to delegate loading of `api.Plugin` to the parent.

## 16. Mental Model Summary

~~~text
                   Choose a class loading policy
                                |
                   Shared API, DTOs, callbacks?
                         /               \
                       Yes                No
                        |                  |
                Define in parent     Need a different
                        |            dependency version?
                Parent-first for API    /        \
                                      No          Yes
                                       |           |
                                 Parent-first   Selective
                                usually enough  child-first
                                                   |
                                         verify type identity
                                                   |
                                         verify resource policy
                                                   |
                                         log defining loader / URL
                                                   |
                                         manage lifecycle / TCCL
~~~

**Conclusion:** **Share the types that are genuinely communication contracts**, **isolate the implementation details that truly require separate versions**, and **retain enough trace information to prove which class the JVM defined from where**. That is the maintainable balance between isolation, compatibility, and diagnosability in Java class loading.

### Official Documentation

- [Java SE 17 — ClassLoader: loadClass, getResource, getResources](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader: findClass, findResource, close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JVMS §5.3 — Creation and Loading; defining/initiating loaders](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
- [JLS §13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [Java SE 17 — ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
