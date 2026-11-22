# Mandatory Delegation for Platform Types and Shared APIs

When building a **custom class loader** for plugins, an application server, or an environment running multiple library versions, you cannot simply decide “every class is child-first so plugins are autonomous”. There are **boundaries that must be respected**: platform types provided by the Java runtime must not be arbitrarily redefined; **shared API types between the host and plugins** must have the **same JVM definition** if you want to pass objects, cast types, invoke interfaces, or exchange callbacks safely.

In this article, “mandatory delegation” has **two layers of meaning that need to be distinguished**:

1. **Constraints enforced by the runtime/API:** for example, regular ClassLoader subclasses **must not define classes in packages starting with `java.`** via `defineClass`; violations can throw `SecurityException`. Child-first cannot be used as a legitimate way to replace `java.lang.String` with a version created by a plugin.
2. **Architectural invariants that must be enforced in the application:** a shared interface or DTO such as `com.acme.api.Greeter` needs to be referenced by both the host and the plugin as the **same `Class<?>` object** from a common defining loader. Java does not automatically enforce “every `com.acme.api.*` package must be parent-first”; **the loader designer must implement that policy**.

The practical strategy is typically **parent-first for platform classes and shared API contracts; selective child-first for private implementations/dependencies that need isolation**. This protects type identity, but it must be implemented carefully so as not to accidentally let a plugin override the API or let the host load the wrong implementation.

## 1. Defining Loader Differs from Initiating Loader
A plugin can call `loadClass("com.acme.api.Greeter")` yet receive the exact `Class<?>` defined by the parent. The loader calling the API is the **initiating loader**, whereas `Greeter.class.getClassLoader()` indicates the **defining loader**. If the child defines a second copy of `Greeter` itself, the JVM recognizes it as a different type, even though the binary name and bytes are identical.

```text
Host loader defines com.acme.api.Greeter  ──┐
                                           ├── Host and plugin share Class<?> if delegated
Plugin loader delegates shared API ────────┘

Plugin loader defines duplicate Greeter  ───── Different type from the host version
```

Verify `apiFromPlugin == apiFromHost` instead of merely comparing `getName()` strings. This distinguishes the **architectural constraint** requiring shared identity from the JVM-enforced rule for protected namespaces such as `java.*` in the next section.

## 2. Why Must Platform Loaders Be Prioritized?

Java has built-in class loaders, commonly described by their roles:

| Loader | General Role |
| --- | --- |
| **Bootstrap** | Mechanism for loading core platform classes; `String.class.getClassLoader() == null` is typically observed on the API. |
| **Platform** | Loads platform classes/modules assigned to the runtime's platform loader. |
| **Application/system** | Loads various application classes, the classpath, and application modules depending on configuration. |
| **Custom/plugin** | Can load isolated implementations and libraries, typically having the host/shared API loader as its parent. |

Since Java 9, platform classes reside in a **modular runtime image**, rather than the legacy `rt.jar`. The assignment of classes/modules to bootstrap/platform/application **does not mean every class prefixed with `javax.`, `jdk.`, or every module is loaded by the bootstrap loader**. Therefore, you should not build a list saying “all `javax.*` are core Java” without considering the **actual modules, ownership, runtime, and dependencies**: some `javax.*` APIs are provided by the JDK, whereas other `javax.*` names may come from external libraries.

### What Is Actually Prohibited at the API Level?

A custom class loader must not call `defineClass` in a way that defines classes with binary names in **`java.*`**. The `ClassLoader#defineClass` API specifies `SecurityException` when attempting to define a class belonging to a package starting with `java.` from an unauthorized loader. This is a Java runtime constraint, **distinct** from a parent-first convention created by a development team.

Conversely, Java **has no universal rule** that every `com.company.api.*` name or every `javax.*` name must be defined by the parent. The loader designer must properly identify the API contracts that need to be shared and enforce delegation for them.

**Do not treat the prohibition on defining `java.*` as a complete sandbox mechanism.** A class loader does not by itself provide a comprehensive security boundary for untrusted code; you must also consider module access, permissions, and the system's isolation mechanisms.

## 3. Shared APIs: More Important Than Whether a Class “Can Be Loaded”

For example, the host and plugin communicate via:

~~~java
package com.acme.api;
public interface Greeter {
    String greet();
}
~~~

This snippet is a **contract fragment**, which can compile if saved in a `Greeter.java` file in the appropriate package.

If each plugin contains a copy of `Greeter.class` and uses child-first for `com.acme.api.*` as well:

~~~text
HostLoader
└── com.acme.api.Greeter (Greeter-H)
                 |
                 | host expects object to implement Greeter-H
                 v
PluginLoader
├── com.acme.api.Greeter (Greeter-P)       <-- redefined
└── com.acme.impl.GreeterImpl implements Greeter-P

Greeter-H != Greeter-P
hostGreeterClass.isInstance(pluginObject) == false
~~~

The consequences can include:

- The host casts `GreeterImpl` to `Greeter-H` and gets a `ClassCastException`.
- `ServiceLoader` finds the provider but concludes that the provider is not a subtype of the service type, causing a `ServiceConfigurationError`.
- Certain method signatures across classes defined by different loaders violate loader constraints, leading to a `LinkageError` during the linking phase.
- Generic erasure/reflective invocation can mask the mismatch until a cast occurs or a method is invoked.

**The right policy:** `com.acme.api.*` must be loaded through **a stable shared loader** that both the host and the plugin actually see. Implementation classes such as `com.acme.impl.*` or `plugin.impl.*` can be loaded child-first by the plugin loader when isolation is genuinely needed.

### What Kinds of Types Does a “Shared API” Include?

Not just the main interface. Consider all classes that the parties **pass directly across the boundary**:

- API interfaces and abstract base classes.
- DTOs, request/response, enum, and exception types in method signatures.
- Callbacks, event/listener interfaces, and service/provider contracts.
- Annotations or marker types that the framework/host reads by `Class<?>` identity.
- Types in method parameter and return types, including references that are still checked by the runtime.

A dependency that is “merely an internal implementation” might still need to be kept separate if the plugin depends on a different version; conversely, a DTO accidentally bundled inside a plugin that the host also uses can break the contract. Therefore, define the **sharing boundary architecturally**, rather than relying solely on whether a package name contains `api`.

## 4. Parent-First for APIs, Child-First for Implementations: A Selective Policy

A commonly used policy:

| Namespace / Kind | Recommended Lookup Direction | Rationale |
| --- | --- | --- |
| `java.*` and runtime platform classes/modules | Prefer runtime/parent; do not redefine core classes | Avoids violating namespace protection and breaking runtime assumptions. |
| `com.acme.api.*` owned by the host | **Mandatory parent-first by design** | The host and plugin must see the same `Class<?>` definition. |
| `plugin.impl.*` owned by the plugin | **Selective child-first** | The host might have a different version; the current plugin's implementation must be used. |
| Plugin's private implementation libraries | Child-first when there is a clear need for isolation | Allows different dependency versions without breaking the shared contract. |
| Packages that plugins are not allowed to override | Parent-first or an explicit policy based on ownership | Avoids accidentally loading classes outside the plugin's scope. |

You should not implement a simplistic “everything not in `java.*` is child-first” approach because that will duplicate shared APIs. Conversely, “everything is parent-first” can cause the host version of an implementation to be used instead of the child version that the plugin needs.

The JVM specification does not mandate a single child-first or parent-first model for all custom loaders. **The invariant to maintain is that types involved in shared communication share a common definition, and private classes are intentionally isolated.**

## 5. Java 17 Practice: Safe Loader and API-Duplicating Loader

This standalone example **self-compiles** an API interface for the host and a duplicate copy of the interface along with an implementation for the plugin, then tests two policies:

- **Safe loader:** child-first exclusively for `plugin.impl.*`, parent-first for `api.shared.*` and all remaining names.
- **Unsafe loader:** child-first for `plugin.impl.*` **and** `api.shared.*`, creating a duplicate definition of the interface contract.

By compiling identical source code, the test demonstrates that **identical bytecode is no substitute for sharing the defining loader**.

Create a file named **`DelegationBoundaryDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DelegationBoundaryDemo {
    private static final String API = "api.shared.Greeter";
    private static final String IMPL = "plugin.impl.GreeterImpl";

    static final class PluginLoader extends URLClassLoader {
        private final boolean shareApi;

        PluginLoader(URL[] urls, ClassLoader parent, boolean shareApi) {
            super(urls, parent);
            this.shareApi = shareApi;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            boolean pluginImplementation = name.startsWith("plugin.impl.");
            boolean privateApiCopy =
                    !shareApi && name.startsWith("api.shared.");

            if (!pluginImplementation && !privateApiCopy) {
                // JVM/platform + host API: parent-first.
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);

                if (type == null) {
                    try {
                        type = findClass(name);
                    } catch (ClassNotFoundException absent) {
                        type = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }
    }

    private static void write(Path file, String content)
            throws Exception {
        Files.createDirectories(file.getParent());
        Files.writeString(file, content);
    }

    private static void compile(JavaCompiler compiler, Path output,
                                Path... sources) {
        String[] args = new String[5 + sources.length];
        args[0] = "--release";
        args[1] = "17";
        args[2] = "-d";
        args[3] = output.toString();
        args[4] = "-g:none";

        for (int i = 0; i < sources.length; i++) {
            args[5 + i] = sources[i].toString();
        }

        int status = compiler.run(null, null, null, args);
        if (status != 0) {
            throw new IllegalStateException("Compiler failed: " + status);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        Path root = Files.createTempDirectory("delegation-boundary-");
        Path hostDir = Files.createDirectories(root.resolve("host"));
        Path childDir = Files.createDirectories(root.resolve("child"));

        Path hostApiSource =
                root.resolve("host-src/api/shared/Greeter.java");
        Path childApiSource =
                root.resolve("child-src/api/shared/Greeter.java");
        Path childImplSource =
                root.resolve("child-src/plugin/impl/GreeterImpl.java");

        String apiSource =
                "package api.shared; "
                + "public interface Greeter { String greet(); }";

        write(hostApiSource, apiSource);
        write(childApiSource, apiSource);
        write(childImplSource,
                "package plugin.impl; "
                + "public final class GreeterImpl "
                + "implements api.shared.Greeter { "
                + "public GreeterImpl() {} "
                + "public String greet() { return \"hello-plugin\"; } "
                + "}");

        compile(compiler, hostDir, hostApiSource);
        compile(compiler, childDir, childApiSource, childImplSource);

        try (URLClassLoader host = new URLClassLoader(
                    new URL[] { hostDir.toUri().toURL() }, null);
             PluginLoader safe = new PluginLoader(
                    new URL[] { childDir.toUri().toURL() }, host, true);
             PluginLoader unsafe = new PluginLoader(
                    new URL[] { childDir.toUri().toURL() }, host, false)) {

            Class<?> hostApi = host.loadClass(API);

            Object good =
                    safe.loadClass(IMPL).getDeclaredConstructor().newInstance();

            System.out.println("Safe API shared: "
                    + (safe.loadClass(API) == hostApi));
            System.out.println("Safe implementation local: "
                    + (good.getClass().getClassLoader() == safe));
            System.out.println("Safe implements host API: "
                    + hostApi.isInstance(good));
            System.out.println("Safe greeting: "
                    + hostApi.getMethod("greet").invoke(good));

            Object bad = unsafe.loadClass(IMPL)
                    .getDeclaredConstructor().newInstance();

            System.out.println("Unsafe API duplicated: "
                    + (unsafe.loadClass(API) != hostApi));
            System.out.println("Unsafe implements host API: "
                    + hostApi.isInstance(bad));

            try {
                hostApi.cast(bad);
                System.out.println("Unexpected cast success");
            } catch (ClassCastException e) {
                System.out.println("Unsafe cast: ClassCastException");
            }

            System.out.println("Platform String delegated: "
                    + (safe.loadClass("java.lang.String") == String.class
                       && unsafe.loadClass("java.lang.String") == String.class));
        }
    }
}
~~~

Compile/run from the directory containing the file using **JDK 17+**:

~~~bash
javac --release 17 DelegationBoundaryDemo.java
java DelegationBoundaryDemo
~~~

**Exact stdout** with a standard JDK that has the `jdk.compiler` compiler module:

~~~text
Safe API shared: true
Safe implementation local: true
Safe implements host API: true
Safe greeting: hello-plugin
Unsafe API duplicated: true
Unsafe implements host API: false
Unsafe cast: ClassCastException
Platform String delegated: true
~~~

### Explaining Why These Results Matter

1. The program generates **two API sources with identical content** and compiles them into two different directories, along with the implementation in the child directory. This represents the case where a plugin has a copy of the API even though the host already has one.
2. `host` (a `URLClassLoader` with a `null` parent) defines `api.shared.Greeter`; the bootstrap loader can still provide platform classes.
3. `safe` gets the implementation class from `childDir` via child-first for `plugin.impl.*`, while all `api.shared.*` requests use `super.loadClass`, thereby **delegating to the parent host**. `GreeterImpl` therefore implements **the host's exact interface**.
4. `unsafe` calls `findClass` itself for both `plugin.impl.*` and `api.shared.*`, causing the child copy of the API interface to be **redefined** by the unsafe loader. This object implements its own copy of the API, not the host API.
5. `hostApi.isInstance(good)` evaluates to `true`; `hostApi.isInstance(bad)` evaluates to `false`, and `hostApi.cast(bad)` throws `ClassCastException` even though the name `api.shared.Greeter` is identical.
6. `safe.loadClass("java.lang.String")` and `unsafe.loadClass("java.lang.String")` still go through `super.loadClass`, returning the platform's `String.class` rather than attempting to define a copy themselves.
7. The two loaders `safe` and `unsafe` are separate objects, so the same implementation name `plugin.impl.GreeterImpl` in each loader also results in two different definitions. That is **allowed** because the implementation is a private detail; what should not happen is losing the identity of the **shared contract**.
8. `getClassLoadingLock(name)`, `findLoadedClass(name)`, and `resolveClass(type)` are used to prevent duplicate loading within the loader and to respect the resolution mechanism. Any fallback to `super.loadClass` still follows the parent policy.
9. `try-with-resources` closes the URLClassLoader instances after the example; there is no guarantee that closing a loader will unload classes immediately. Files generated in the temporary directory can be cleaned up after running.

**Limitations note:** The loader in the example only handles two experimental prefixes and is not a complete plugin sandbox or production class loader. It does not handle complex dependency trees, module layers, package sealing, `ProtectionDomain` metadata, resource conflicts, or server lifecycles. The parent-first policy for the API is a choice **mandated by the example's contract**, not an automatic rule for every package named `api.shared`.

## 6. Designing Package Policies Without Losing Control

A real-world production child-first loader should classify by **ownership** rather than by arbitrarily guessed class names:

~~~text
Request: com.acme.api.PaymentService
  → parent/shared loader (shared API)
  → do not allow the plugin to redefine it

Request: plugin.payment.impl.CardProcessor
  → plugin loader first (private implementation)
  → conditional fallback if absent

Request: java.lang.String
  → delegate to runtime/parent
  → do not attempt to define it locally

Request: some.shared.dto.PaymentRequest
  → the loader that defines the shared DTO contract

Request: vendor.private.parser.ParserImpl
  → plugin's private version if isolation is needed
~~~

The key is distinguishing **APIs used by both the host and plugins** from **implementations/private dependencies**. If the same library needs part of it shared and another part isolated, you must explicitly design type boundaries, the module graph, relocation, or packaging tooling; do not simply add a few `startsWith` conditions haphazardly.

### Which APIs Must Be Present on the Parent/Shared Loader?

- Interfaces/base classes in host–plugin signatures.
- DTOs, enums, exceptions, annotations, and listener types that are exchanged directly.
- Service/provider contracts when using `ServiceLoader` or framework discovery.
- Types used as keys in a registry or checked via `instanceof` / `Class<?>` identity.
- Payload types received by host callbacks at runtime.

This does not mean putting the entire application on the parent loader. Share **only the contract portion**, while retaining isolation for private implementations and resources/dependencies that need to be isolated.

### The Chosen Loader Must Actually See the API

Choosing `parent-first` does not magically create a missing class. If the parent **does not have** the API, the child fallback path may still define its own copy of the API. For mandatory contracts, you must **ensure the parent owns the API** at deployment time and may choose to **fail fast** instead of silently falling back to avoid split identity.

A production loader can enforce a stronger rule:

~~~text
If name belongs to shared API:
    only allow parent to load; if parent does not find it → report an error immediately
If name belongs to plugin implementation:
    search locally first, with controlled fallback
Other namespaces:
    use configured policy
~~~

This is **pseudocode**, not complete Java calls. The runnable example uses `super.loadClass` for the API to illustrate default delegation, so if the API were completely absent from the parent, parent-first fallback could still look it up locally. **Do not assume that already enforces a fail-fast contract**.

## 7. Resources and Service Providers Must Align with the Class Policy

Classes are not the only concern. For plugins, `getResource`, `getResources`, and `getResourceAsStream` can look up configuration files, `META-INF/services/...`, or metadata inside parent/child JARs.

- The API contract should be defined in common; metadata/provider discovery needs to find the right provider that can implement the **same API interface**.
- If implementations are loaded child-first while `getResource` remains parent-first, the plugin may receive the **configuration or schema of the host version**.
- `getResources` is typically used to **aggregate multiple resources**, especially for SPI; you should not replace it with “take only the first entry” and drop valid providers.
- `ServiceLoader.load(Service.class)` normally uses the **thread context class loader (TCCL)**; this loader must see providers compatible with the shared interface.
- Consider module encapsulation on Java 9+, because named modules have their own rules for resource and service access.

**Do not try to fix a duplicate-interface error merely by reversing resource order.** If a provider actually implements a copy of the interface from a different defining loader, `ServiceConfigurationError` or `ClassCastException` can still occur.

## 8. Does the Module System (JPMS) Make Parent Delegation Obsolete?

No. Since Java 9, the module system adds **module identity, readability, exports, opens, services**, and the ability to construct custom module layers; it does not merge every class with the same name across all loaders into a single shared type.

It is necessary to distinguish:

| Concept | Question Answered |
| --- | --- |
| **Class loader** | Who defines this `Class<?>`? |
| **Module** | Which module does the class belong to, and which packages does the module read and access? |
| **Module layer** | Which modules are resolved and organized into which layer? |
| **Delegation policy** | When searching for a class by name, does the loader prioritize the parent or local sources? |

If a plugin lives in a named module or custom layer, you must determine the class loader assigned to the module and the appropriate `requires`/`exports`/`opens` edges. **Allowing a module to be read does not automatically unify two class definitions created by two different loaders**; conversely, a loader can be blocked by module visibility/access rules even if parent delegation locates the class.

In modern Java, you also should not assume that every JDK module is defined by the bootstrap loader; the distribution of classes across bootstrap/platform/application depends on the runtime and modules. The enduring rule is: **do not replace platform namespaces yourself, maintain a single definition of the shared API contract, and abide by valid module rules**.

## 9. Common Errors and Diagnostic Signs

| Symptom | Possible Root Cause | What to Check |
| --- | --- | --- |
| `ClassCastException: A cannot be cast to A` | Two class/interface definitions with the same name but different defining loaders. | Compare `Class<?>` with `==`, and check `getClassLoader()` on both sides. |
| `ServiceConfigurationError: ... not a subtype` | The provider does not actually implement **the interface used by the consumer**. | Verify the service type, provider type, and the discovery loader/TCCL. |
| `LinkageError` / loader constraint violation | Signatures/dependencies across the boundary link types with conflicting identities. | Inspect the full message, method descriptors, and duplicate APIs. |
| `SecurityException` when attempting to define `java.*` | A custom loader defines a class in a protected namespace itself. | Do not override platform classes; delegate to the runtime loader. |
| `ClassNotFoundException` for a shared API | The parent cannot see the contract or the classpath/module path configuration is wrong. | Ensure a single API source on the shared loader and verify visibility. |
| `NoClassDefFoundError` when using an implementation | A dependency is missing, cannot be linked, or the class previously failed initialization. | Check the cause/stack trace and the defining loaders of dependencies. |
| Plugin resources fetched from host | Resource delegation is still parent-first even though implementation loading is child-first. | Log `getResource` and `getResources`, and align the resource policy. |
| Incorrect behavior after hot redeploy | Objects/caches/threads from the old loader are carried over into the new loader. | Clean up lifecycle state, TCCL, registries, and singletons holding old references. |

### Measuring Identity Instead of Only Printing Names

The following fragment assumes `pluginType` is the implementation's `Class<?>`, `hostApi` is the API's `Class<?>`, and `pluginObject` is an instance:

~~~java
System.out.println("Impl loader: "
        + pluginType.getClassLoader());
System.out.println("Host API loader: "
        + hostApi.getClassLoader());
System.out.println("Implements host API: "
        + hostApi.isInstance(pluginObject));
System.out.println("Actual type: "
        + pluginObject.getClass().getName());
~~~

This is a **fragment**, not a standalone program; the variables must be declared properly. Cross-check further with:

~~~java
Class<?> apiSeenByPlugin =
        pluginType.getClassLoader()
                  .loadClass(hostApi.getName());

System.out.println("Same API Class: "
        + (apiSeenByPlugin == hostApi));
~~~

If the last expression is `false`, there is a **split API identity**. You should not compare only `getName()` strings because they can be equal even when the Class instances differ.

## 10. Anti-Patterns to Avoid

### 10.1. Child-First for Everything Except java.*

~~~java
// Pseudocode that is wrong regarding the sharing policy:
if (!name.startsWith("java.")) {
    return findClass(name);
}
return getParent().loadClass(name);
~~~

Aside from the fact that the snippet does not handle caching/fallback/resolution, this rule **does not protect shared APIs** such as `com.acme.api.*`. It can redefine the contract and cause cast/linkage errors.

### 10.2. “Equal Bytecode” Alone Makes Them the Same Type

Incorrect. The JVM uses **binary name + defining loader**; classes defined from the same API JAR but by two different loaders **do not automatically become the same type**.

### 10.3. Global Parent-First Without Considering Private Implementations

If both the host and the plugin have `vendor.parser.Parser` yet need two different versions, parent-first can cause the plugin to unintentionally use the host's version. Share only the contracts that must be shared; implementations can be child-first according to a specific policy.

### 10.4. Using TCCL as a Tool to Fix Type Identity

`Thread.currentThread().setContextClassLoader(loader)` changes the loader that TCCL-based APIs will use; it **does not replace classes already defined by another loader**. It does not make `ClassCastException` disappear on its own; moreover, forgetting to restore it in a worker pool can retain an old plugin loader.

### 10.5. Bundling the API JAR Inside the Plugin and Assuming Parent-First Is Enough

If the parent contains the API and the plugin uses parent-first, the API copy in the plugin may not be defined at runtime, yet it still creates configuration risk when changing the loader policy or packaging. It is best **not to redundantly bundle the API contract** unless necessary; verify dependency exclusions, scopes, and distributed artifacts.

### 10.6. Forgetting Synchronization, Caching, and Fallback When Overriding loadClass

A custom implementation must avoid duplicate definitions and race conditions; handle `findLoadedClass`, `getClassLoadingLock`, and `resolveClass` appropriately, and maintain proper parent fallback. Do not call `findClass` indiscriminately for every class; do not catch `LinkageError` and try to “retry” by defining another class with the same name.

### 10.7. Thinking a Class Loader Is a Complete Sandbox

Parent delegation and prohibiting the definition of `java.*` help protect parts of the namespace and type consistency, **not a complete security isolation model**. For untrusted plugins, you must design permission controls, module systems, process/container boundaries, and code provenance checks based on an actual threat model.

## 11. Design Checklist for Loaders/Plugins

1. **List the platform namespaces** that plugins must not define themselves; keep appropriate runtime/parent mechanisms.
2. **List the shared API contracts**, including interfaces, DTOs, enums, exceptions, annotations, callbacks, and SPI service types.
3. **Ensure the shared loader actually has those contracts**; fail fast if a mandatory API is missing.
4. **Separate the plugin's private implementations/dependencies**; use selective child-first only when there is a clear reason.
5. **Verify class identity** with `==` and `isInstance` when objects cross the host–plugin boundary.
6. **Ensure `loadClass` has proper cache/lock/resolve/fallback mechanisms**, without redefining classes within the same loader.
7. **Check that resource policies** (`getResource`, `getResources`, `META-INF/services`) are compatible with the class policy.
8. **Review TCCL/thread pools/lifecycle**, especially when frameworks discover providers via TCCL or support hot redeploy.
9. **For named modules**, verify module readability, exports/opens, and loader–module assignment.
10. **Write tests with a duplicate API in the child** to confirm the safe loader still returns the parent's same `Class<?>`. Similarly, test that the plugin implementation genuinely comes from the child and is not “swallowed” by the host.

## 12. Self-Check

**Question 1.** Does the JVM force every `com.example.api.*` to be parent-first?

**Answer:** No. This is an **application policy** that must be enforced if those classes are shared contracts. `java.*`, by contrast, has special namespace protection rules when custom loaders use `defineClass`.

**Question 2.** A plugin and the host read the same JAR containing the `Greeter` interface, but each defines it through its own loader. Do the two `Greeter` types have the same identity?

**Answer:** No. Even with the same binary name and bytes, their defining loaders differ, so they are two distinct types.

**Question 3.** Why can a plugin be child-first for `plugin.impl.*` yet must be parent-first for `api.shared.*`?

**Answer:** Implementations are private details that need isolation; API contracts are types that both the host and plugin must see in common to pass objects and cast safely.

**Question 4.** If two child loaders share the same parent, does that automatically guarantee the API is the same type?

**Answer:** Not yet. The parent must **actually define/provide the API**; if it is missing and each child falls back to defining it locally, the identities will still differ. For mandatory contracts, you should verify/fail fast.

**Question 5.** Does simply setting the TCCL to the host loader fix a provider implementing an interface with the same name but a different defining loader?

**Answer:** No. The TCCL affects the class/resource lookup path of APIs that use it, but it does not change the identity of classes that have already been defined.

**Question 6.** Should the `java.lang.String` type in a modern Java program be redefined by a plugin loader?

**Answer:** No. Use the platform class provided by the runtime; attempting to define `java.*` with a regular custom ClassLoader violates package protection rules.

## Key Takeaways

**Delegating platform classes** ensures plugins do not replace runtime-managed types on their own. **Delegating shared API contracts** ensures the host and plugins use **the same class/interface definition**, not merely the same name. The generally appropriate strategy is **parent-first for platform + shared API**, and **scoped child-first for private implementations**. For critical API contracts, the parent must genuinely own that class; otherwise, report a configuration error instead of silently creating a duplicate copy. When debugging, verify using `Class<?> ==`, `getClassLoader()`, and `isInstance(...)`.

**Authoritative references:**

- Java SE 17 API, `ClassLoader` (delegation, `loadClass`, `defineClass`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- *Java Virtual Machine Specification* §5.3, class identity/creation: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Language Specification* §12.2, loading: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
