## 6. How Does ServiceLoader Iterate Over Providers?

`ServiceLoader` supports **lazy** provider access: creating a `ServiceLoader` object does not mean immediately instantiating every provider instance.

Example:

```java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class);

for (Greeting service : loader) {
    System.out.println(service.message());
}
```

- The `loader` object represents the provider discovery/caching mechanism.
- When `iterator()` is traversed, `ServiceLoader` can load the provider class and create a provider instance on demand.
- Loaded provider instances are retained by `ServiceLoader` in **the ServiceLoader object's own cache** per the API contract. Therefore, iterating over the same loader again can return the cached instances rather than creating new ones.
- Calling `loader.reload()` clears the cache so that provider discovery and instantiation are performed again under the current conditions of the source/provider; **it does not automatically change the defining class loader of already-loaded classes**.
- `ServiceLoader` **is not safe for concurrent use across multiple threads** when accessed/mutated as the same object without external synchronization.

Another usage form in Java 17:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);

services.stream().forEach(provider -> {
    Class<? extends Greeting> type = provider.type();
    System.out.println(type.getName());

    Greeting instance = provider.get();
    System.out.println(instance.message());
});
```

`ServiceLoader.Provider<S>` provides `type()` to inspect the provider's type and `get()` to obtain an instance. Note that with named modules using a **provider factory method**, `type()` may reflect the factory's return type per the API contract; do not infer that it is always the class name declared in configuration like on the classpath.

### reload() Does Not Replace Plugin Lifecycle Management

If a plugin JAR changes on disk while still using the **same loader** and the same `ServiceLoader`, merely calling `reload()` does not guarantee the JVM will redefine already-loaded classes, nor does it automatically close old provider instances. A hot-reload system needs an explicit workflow: stop using old instances, release resources/threads, create a new defining loader when appropriate, rediscover providers, and avoid mixing types across loader generations.

## 7. When There Are Multiple Providers

A service interface can have multiple implementations. Example provider descriptor:

```text
plugins.EnglishGreeting
plugins.VietnameseGreeting
plugins.FrenchGreeting
```

Each line must reference a valid provider class that can be found by the loader and assigned to the service interface. The snippet above is only a **metadata sample**; the illustrative classes are not defined in the runnable program in Section 5.

The order in which the iterator traverses providers is governed by specific rules of `ServiceLoader` and the class loader/module source. With multiple JARs/modules, **do not design business logic to depend strictly on the first provider's order** unless a contract guarantees it. If there are multiple implementations, use a configuration property, an explicitly designed priority, or a provider filtering/identification step rather than assuming the "first provider" is the desired version.

Also, do not assume that service discovery filters out providers based on runtime health: a provider can be discovered, yet its **constructor** or **provider() factory** may report an error when actually instantiated.

## 8. Provider Registration Mechanism in Named Modules (JPMS)

Java 9+ supports SPI in **named modules** without necessarily requiring `META-INF/services` for providers located in a module.

Example module containing the API:

```java
module demo.api {
    exports spi;
}
```

Consumer module:

```java
module demo.app {
    requires demo.api;
    uses spi.Greeting;
}
```

Provider module:

```java
module demo.provider {
    requires demo.api;
    provides spi.Greeting with plugins.HelloGreeting;
}
```

The three snippets are **separate illustrative `module-info.java` files**; to run them in practice, you must construct an appropriate module source tree, class definitions, and module path. Do not combine all three `module` declarations into a single file.

Meaning:

- `uses spi.Greeting;` indicates that the consumer module uses that service contract.
- `provides spi.Greeting with plugins.HelloGreeting;` registers the provider for the service.
- `requires demo.api;` allows the consumer/provider to read the API module.
- `exports spi;` allows other modules to use the public type `spi.Greeting`.

For a provider module, `ServiceLoader` can discover providers through module metadata; `META-INF/services/...` is not necessarily required if the provider is already registered in the module descriptor. A named-module provider can have a **public no-args constructor** or a **public static provider() method** with specific constraints checked by `ServiceLoader`. The `provider()` factory method is a named-module provider mechanism, **not** an arbitrary substitute for a constructor when the provider is declared only via a classpath configuration file.

If you need to discover providers in a set of modules organized by **ModuleLayer**, consider:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(layer, Greeting.class);
```

This is an illustrative snippet requiring an already-constructed `ModuleLayer` variable `layer`; it is not a standalone runnable program. Using a module layer is useful when a framework creates multiple separate module layers instead of relying solely on the thread's context loader.

### Do Not Confuse Modules with Loaders

Modules and class loaders are two distinct concepts. A single loader can define classes belonging to multiple modules according to the JVM/JDK mapping; a class can belong to a named module or an unnamed module. Module readability, exports, and service binding requirements form an additional layer that cannot be resolved merely by setting the TCCL.

## 9. Other APIs That May Involve the Context Loader

`ServiceLoader` is the canonical Java SE API where the TCCL is clearly visible. Other ecosystems also have **provider discovery**, but they must not all be treated as identical:

| API/Ecosystem | Relationship to the Context Loader | What to Check |
|---|---|---|
| `ServiceLoader.load(service)` | Uses the **TCCL** per contract | Can the TCCL see the provider declaration/class? |
| `ServiceLoader.load(service, loader)` | Uses an **explicit loader** | Was the right plugin loader passed? |
| `Class.forName(name)` | Uses the **caller defining loader**, does not automatically use the TCCL | Which loader defines the calling code? |
| `ClassLoader.getSystemClassLoader()` | Returns the system loader, not the TCCL | Can the system loader see the plugin? |
| `javax.xml.parsers.DocumentBuilderFactory.newInstance()` (JAXP) | Provider lookup procedure may use the context class loader per JAXP documentation, along with other configuration/fallback sources | Provider factory, system property, service declarations, module context |
| `javax.xml.transform.TransformerFactory.newInstance()` (JAXP) | Provider lookup mechanism and TCCL may be involved | Provider discovery and JDK version |
| `java.sql.DriverManager` / JDBC driver SPI | Driver discovery uses the service-provider mechanism along with its own registration/access rules | Driver's loader, module, driver visibility, lifecycle |
| JNDI and container/plugin libraries | May use the TCCL depending on the API/provider/framework | Specific provider contract and configuration |

**Do not turn this table into an assertion that every API always reads the TCCL in every version.** For example, `ResourceBundle` has overloads tied to the caller/module or an explicitly supplied loader; simply seeing the label "resource loading" is not enough to conclude it defaults to the TCCL. `java.util.logging`, JDBC, and frameworks also have their own caching, singleton, module, and classloader check rules. Read the exact JavaDoc of the overload you are using.

### Example with JAXP

`DocumentBuilderFactory.newInstance()` and `TransformerFactory.newInstance()` are factory APIs that have a configuration/provider-discovery-based mechanism for locating alternative implementations. They are not directly equivalent to calling `ServiceLoader.load` manually: the procedure may inspect system properties, JDK configuration, service providers, and the default implementation. The TCCL can determine which provider is visible in certain lookup branches.

Illustrative example:

```java
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();
System.out.println(factory.getClass().getName());
```

This is an **illustrative snippet inside a method**, not a standalone application. The printed implementation name **should not be hardcoded** because it varies by JDK, provider configuration, and class loader. If you need to select a specific provider, refer to the factory overload accepting a class name/loader or the configuration mechanism documented by that API.

## 10. Common Pitfalls When Using TCCL and ServiceLoader

### 10.1. Descriptor Placed in the Wrong Location

Incorrect:

```text
META-INF/service/spi.Greeting
META-INF/services/spi/Greeting
META-INF/services/plugins.HelloGreeting
```

Correct:

```text
META-INF/services/spi.Greeting
```

The entry name is the service **binary name**, and the content is the provider implementation **binary name**. For archives, ensure the descriptor is actually inside the JAR readable by the selected loader, not merely present in the source directory.

### 10.2. Provider Code Exists, but ServiceLoader Does Not See It

Possible causes:

- The descriptor was not copied into the build output/JAR.
- The TCCL points to the **parent/application loader** while the plugin provider belongs only to a child loader.
- The overload accepting an explicit loader was called, but the **wrong loader** was passed.
- The named module `provides`/`uses` declaration or module layer does not match.
- The provider class resides in a source that the loader cannot see, or a dependency of the provider cannot be resolved.
- A container/framework overrides parent-first/child-first by namespace, causing the API contract and implementation not to share the same runtime type.

**Minimal diagnostics:**

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

System.out.println("TCCL = " + context);
System.out.println("API defining loader = "
        + Greeting.class.getClassLoader());
```

This snippet requires the `Greeting` interface in the project. Do not compare loaders using their `toString()` strings: each custom loader can log differently. If you need to compare runtime types, use `==` on `Class<?>` or `ClassLoader` references.

### 10.3. ServiceConfigurationError

`ServiceLoader` can throw **`java.util.ServiceConfigurationError`** when configuration/provider information is invalid, for example when the provider class cannot be found, is incompatible with the service type, lacks a suitable constructor/provider factory, fails during provider initialization, or cannot be instantiated according to the contract.

For example, if the descriptor specifies:

```text
plugins.DoesNotExist
```

`ServiceLoader` may detect the error **when actually iterating/streaming providers**, not necessarily immediately at `ServiceLoader.load(...)`. `ServiceConfigurationError` is an `Error` (not a checked exception), so do not rely on `catch (Exception ex)` to catch all provider discovery problems. During startup or in a plugin manager, log the service/provider/loader and cause; you can fail fast or isolate the faulty plugin depending on your designed policy.

### 10.4. Unrestored TCCL

A task using a thread pool sets the TCCL to `PluginLoaderA` and forgets to restore it. A subsequent task for plugin B running on the same thread may find A's provider or retain a long-lived reference to A. Use `try/finally` as in the example in Section 2 and scope the loader to the smallest scope.

### 10.5. Adding an Implementation Dynamically While Still Using the Old Cache

`ServiceLoader` caches discovered providers. Adding a JAR or changing the TCCL after creating a `ServiceLoader` **should not be considered an automatic update to all providers in the old object**. Create a new `ServiceLoader` with the right loader or call `reload()` as needed, and understand that already-loaded classes have their own identity/lifecycle.

### 10.6. Duplicate Service API Under Child-First

If a plugin bundles and child-first loads its own copy of `spi.Greeting`, the implementation may not be considered a subtype of `spi.Greeting` in the application loader. The result can be `ServiceConfigurationError`, `ClassCastException`, or `LinkageError` depending on the loading/invocation path. Place the service API in the parent/shared loader and ensure the plugin delegates the API namespace.

## 11. Loader-Safe SPI/Plugin Design Checklist

1. **Identify the service contract**: which class/interface it is, and which defining loader defines it.
2. **Place the shared API in the parent/shared class loader** if callers and providers need to exchange objects using the same Java type.
3. **Choose the registration source**: classpath descriptor `META-INF/services/<service-binary-name>` or named module `provides ... with ...`.
4. **Verify the exact package/class entry** in the JAR output, not only in source.
5. **Select the discovery loader intentionally**: TCCL (`ServiceLoader.load(service)`), explicit loader, or `ModuleLayer`.
6. **Do not omit the provider's dependencies** in the appropriate namespace.
7. **Set and restore the TCCL** around framework calls when needed; watch out for thread pools and asynchronous tasks.
8. **Iterate over providers and handle configuration errors explicitly**, instead of assuming constructors never fail.
9. **Manage caching, lifecycle, and unloading** of provider instances/class loaders; `reload()` does not automatically close resources.
10. **Avoid relying on provider ordering** if the contract does not require it; use configuration/metadata to select the desired implementation.

### A Note on Security

The TCCL and `ServiceLoader` are **application extensibility** mechanisms, not security mechanisms. Provider code executes in-process with the capabilities of deployed code; do not automatically load untrusted providers simply because a `META-INF/services` entry exists. Control JAR provenance, signatures/deployment pipelines, module/access policies, and permissions outside the JVM according to system needs.

## 12. Self-Check Questions

**1. Which loader does `ServiceLoader.load(MyService.class)` use by default?** The calling thread's TCCL.

**2. Does `Class.forName("my.Provider")` automatically use the TCCL?** No. The single-parameter overload uses the defining loader of the **calling class**; to specify a concrete loader, use the three-parameter overload.

**3. Why can't a parent framework see a provider in a child without using a context loader?** Parent delegation goes from child to parent, not searching downward from parent to all children.

**4. What is the classpath descriptor name for `spi.Greeting`?** `META-INF/services/spi.Greeting`. The content is the binary name of the provider class.

**5. Does `ServiceLoader.load(...)` necessarily instantiate all providers immediately?** No. The discovery/instantiation mechanism is lazy when iterating over providers.

**6. Does `ServiceLoader.reload()` force the JVM to redefine an already-loaded class?** No. It clears the cache inside the ServiceLoader object; class loading and loader lifecycle remain separate.

**7. If the TCCL has changed but `ServiceLoader.load(service, appLoader)` still does not see the plugin, is that a bug?** No, because the overload taking a loader parameter uses the **passed** loader, not the TCCL.

**8. A Service API is defined in both the parent and the child, with both copies having the same name. Is compatibility guaranteed?** No. Class identity also depends on the defining loader.

**9. Must a provider in a named module always be registered using `META-INF/services`?** No. It can be registered in `module-info.java` using `provides ... with ...`.

**10. Which Java APIs besides ServiceLoader may have a TCCL-based provider lookup mechanism?** Certain JAXP factory APIs and plugin/container ecosystems; you must check the JavaDoc of the specific API and overload rather than mechanically applying the same rule.
