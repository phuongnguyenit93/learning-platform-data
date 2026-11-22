# ServiceConfigurationError and Providers Incompatible with the Service Type in Java

## 1. The Problem: Correct Interface Name, Yet ServiceLoader Still Rejects the Provider

`java.util.ServiceLoader` is the Java Service Provider Interface (**SPI**) mechanism used to find and create implementations of a service contract. The consumer chooses a **specific `Class<S>`** as the service type, for example `Greeter.class`. The provider declares the implementation `PluginGreeter` and registers it using a file in `META-INF/services/` for applications running via the classpath, or using `provides ... with ...` in a named module.

A notable error is **`java.util.ServiceConfigurationError`**, often accompanied by a description such as *provider not a subtype*. This happens when ServiceLoader finds a provider, but the provider does not satisfy the **runtime type relationship** required by the service type.

~~~text
ServiceLoader.load(api.Greeter.class, pluginLoader)
                        |
                        v
Read META-INF/services/api.Greeter
                        |
                        v
Find plugin.PluginGreeter using pluginLoader
                        |
                        v
Check if provider is compatible with api.Greeter?
          /                              \
        yes                               no
         |                                |
 instantiate provider            ServiceConfigurationError
         |
 return api.Greeter instance
~~~

The cause can be simple: the provider class **actually does not implement the service interface**. However, in a multi-`ClassLoader` system, it can be more subtle: the provider **declares that it implements the exact interface name**, yet the provider's interface is defined by the plugin loader itself as a **different runtime Class** from the host's interface.

**Decisive rule:** The JVM identifies a class/interface by **(binary name, defining class loader)**. Therefore, two interfaces with the same `getName()` are not necessarily the same type. ServiceLoader does not accept a provider merely because the text `implements api.Greeter` or `providerClass.getName()` looks reasonable.

This article focuses on SPI configuration errors, type identity, parent delegation, shared APIs, lazy discovery, how to distinguish an incorrect provider from an incorrect loader, and a standalone runnable Java 17+ experiment to reproduce the error and then fix it properly.

## 2. Components of a Service Provider Interface

An SPI typically has four components:

1. **Service contract**: the public interface or abstract class that the application wants to call.
2. **Provider implementation**: the class that supplies the behavior for that service.
3. **Provider configuration/registration**: metadata that lets Java know the implementation name.
4. **Consumer**: the application that uses `ServiceLoader<S>` to discover, instantiate, and invoke the provider.

For the classpath, an example is:

~~~text
api.Greeter                           <- shared interface
plugin.EnglishGreeter                 <- implementation
META-INF/services/api.Greeter        <- descriptor containing:
   plugin.EnglishGreeter
~~~

**The descriptor filename is the binary name of the service type**, not an arbitrary name: `META-INF/services/api.Greeter`. The file content is the **binary name of the provider class**, one provider per line. Names have dots; do not replace dots with `/` in the service filename.

A typical consumer application:

~~~java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
for (Greeter provider : loader) {
    System.out.println(provider.greet());
}
~~~

**The snippet above is illustrative only**; it assumes `Greeter` exists and declares `greet()`. ServiceLoader is an **iterable lazy discovery mechanism**: calling `load` does not prove that every provider has been loaded or instantiated successfully. Configuration errors may only appear when starting to iterate with `iterator()` / `stream()` or retrieving a provider.

## 3. When Is ServiceConfigurationError Thrown?

`ServiceConfigurationError` is an **`Error`**, not a subclass of `Exception`. It indicates a problem when finding, validating, or creating service providers.

Common categories of causes:

| Category | Example | Possible Failure Stage |
| --- | --- | --- |
| Unreadable descriptor | `META-INF/services/api.Greeter` fails with an I/O error | Reading configuration |
| Invalid descriptor content | Invalid provider name, invalid configuration syntax | Parsing descriptor |
| Provider does not exist | File lists `plugin.MissingGreeter`, but the class does not exist | Loading provider class |
| Provider is not a subtype | Class does not implement the exact runtime service type | Type checking |
| Unsuitable constructor | Classpath provider has no public no-arg constructor | Selecting instantiation method |
| Provider instantiation failed | Constructor/factory throws an exception | Creating provider |
| Invalid named module configuration | Invalid service type, `uses`/`provides`, or provider factory | Resolution/discovery/instantiation |
| Loader/version conflict | Duplicate service API definition, incompatible dependency | Load/link/type check |

**Do not assume every `ServiceConfigurationError` is caused by descriptor file configuration.** When the service has already found the provider class, yet it is incompatible with the exact service Class passed in by the consumer, the cause is **type identity** or an incorrect implementation.

Deeper issues such as `LinkageError`, `ExceptionInInitializerError`, or module access errors may appear on their own or be reported by ServiceLoader through `ServiceConfigurationError` depending on the code path and Java version. To diagnose accurately, you must inspect the **cause, message, service Class, provider Class, and defining loaders**.

## 4. What Does Provider “not a subtype” Actually Mean?

Suppose the consumer has:

~~~java
Class<?> service = api.Greeter.class;
Class<?> provider = plugin.PluginGreeter.class;

boolean compatible = service.isAssignableFrom(provider);
~~~

This is an **illustrative snippet**, using actual classes in the project. For a **conventional classpath provider using a public no-arg constructor**, ServiceLoader requires the provider class to be compatible with the service type; otherwise, it rejects the configuration.

Two cases:

### Case A: The Provider Actually Does Not Implement the API

~~~java
package plugin;

public class WrongGreeter {
    public String greet() {
        return "hello";
    }
}
~~~

`WrongGreeter` has a method named `greet` but **does not declare that it implements `api.Greeter`**. Java does not apply structural typing for this kind of classpath service provider. Matching the method signature alone is not enough.

If the descriptor registers `plugin.WrongGreeter` for `api.Greeter`, the provider genuinely is not a subtype.

### Case B: The Provider Implements the Same API Name, but from a Different Loader

~~~text
Host ClassLoader             Plugin ClassLoader
        |                            |
        v                            v
api.Greeter [H]              api.Greeter [P]
        ^                            ^
        |                            |
Consumer uses H            plugin.PluginGreeter implements P

H.getName() = P.getName() = "api.Greeter"
H == P => false
H.isAssignableFrom(plugin.PluginGreeter) => false
~~~

The provider source may correctly write `implements api.Greeter`, but the JVM resolves `api.Greeter` inside the provider to **P**, while the consumer requires **H**. Without a subtype relationship to H, ServiceLoader still rejects it.

Two different `ClassLoader`s **do not by default** have an error: this identity divergence only arises when the API Class is **defined separately**, rather than both delegating it to the parent.

## 5. Why Are ClassLoader and ServiceLoader Directly Related?

Overload:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);
~~~

It has two objects with different roles:

- **`Greeter.class`** is the **service Class that the consumer accepts as the contract**. That class has its own defining loader, usually the host/common parent loader.
- **`pluginLoader`** is the **loader used to discover and load providers** under the API contract. It can load the provider class, but supplying a different loader **does not turn the host's service Class into the plugin's service Class**.

Even if the provider loader finds the `META-INF/services/api.Greeter` file and the `plugin.PluginGreeter` class, if the implementation resolves the `api.Greeter` interface from a different classloader than the host, the type check still fails.

**Thread Context ClassLoader** is commonly used by the `ServiceLoader.load(Greeter.class)` overload. In a container/plugin, the TCCL helps provider discovery look in the right place, but **changing the TCCL does not automatically merge two separately defined runtime Classes into one**. A proper service API sharing policy is required.

A typically good organization:

~~~text
            Common / Host ClassLoader
                     |
                 api.Greeter
                 api.Request
                 api.Result
                     ^
             parent delegation
                     |
             Plugin ClassLoader
                     |
             plugin.PluginGreeter
             plugin.privateLib.*
             META-INF/services/api.Greeter
~~~

Implementation/private dependencies can belong to a separate loader; the **service interface and contract types used across the boundary** must be unified.

## 6. Complete Java 17+ Example: Reproducing the Error and Fixing It Properly

The experiment uses **the same plugin bytecode** but two loader modes:

- `isolated`: the plugin loader intentionally loads **`api.*` child-first**, defining its own copy of the interface duplicating the host. ServiceLoader reports `ServiceConfigurationError`.
- `shared`: the plugin loader still defines `plugin.*` itself, but **delegates `api.*` to the parent**. The provider is compatible and the service works.

The example requires no libraries beyond JDK 17+.

### 6.1. Source Structure

Create a `spi-loader-demo` directory with the files:

~~~text
spi-loader-demo/
├── src-api/
│   └── api/
│       └── Greeter.java
├── src-plugin/
│   └── plugin/
│       └── PluginGreeter.java
└── src-host/
    └── HostMain.java
~~~

After compilation, you will have:

~~~text
host-classes/
├── HostMain.class
├── HostMain$PluginLoader.class
└── api/
    └── Greeter.class

plugin-classes/
├── api/
│   └── Greeter.class
├── plugin/
│   └── PluginGreeter.class
└── META-INF/
    └── services/
        └── api.Greeter
~~~

Having `api/Greeter.class` appear in **two directories** is intentional. The experiment puts only `host-classes` on the **application classpath**; plugin-classes is handed to the custom loader via a URL. The descriptor is placed only under plugin-classes.

### 6.2. File src-api/api/Greeter.java

~~~java
package api;

public interface Greeter {
    String greet();
}
~~~

### 6.3. File src-plugin/plugin/PluginGreeter.java

~~~java
package plugin;

import api.Greeter;

public final class PluginGreeter implements Greeter {
    @Override
    public String greet() {
        return "hello from plugin";
    }
}
~~~

The public class has a public default constructor; this is sufficient for a standard **classpath-based ServiceLoader provider**.

### 6.4. File src-host/HostMain.java

~~~java
import api.Greeter;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public class HostMain {
    static final class PluginLoader extends URLClassLoader {
        private final boolean duplicateApi;

        PluginLoader(Path pluginClasses, boolean duplicateApi)
                throws IOException {
            super(
                    new URL[] { pluginClasses.toUri().toURL() },
                    HostMain.class.getClassLoader()
            );
            this.duplicateApi = duplicateApi;
        }

        private boolean localFirst(String name) {
            return name.startsWith("plugin.")
                    || (duplicateApi && name.startsWith("api."));
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!localFirst(name)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = findClass(name);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    private static void runCase(
            String label, Path pluginDir, boolean duplicateApi)
            throws IOException, ClassNotFoundException {

        try (PluginLoader loader = new PluginLoader(
                pluginDir, duplicateApi)) {

            Class<?> pluginApi = loader.loadClass("api.Greeter");
            System.out.println(label + " same API Class: "
                    + (pluginApi == Greeter.class));

            ServiceLoader<Greeter> services =
                    ServiceLoader.load(Greeter.class, loader);

            try {
                Greeter provider = services.iterator().next();
                System.out.println(label + " provider: "
                        + provider.greet());
            } catch (ServiceConfigurationError failure) {
                System.out.println(label + " error: "
                        + failure.getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostMain <plugin-classes-directory>");
        }

        Path pluginDir = Path.of(args[0]).toAbsolutePath();
        runCase("isolated", pluginDir, true);
        runCase("shared", pluginDir, false);
    }
}
~~~

### 6.5. Descriptor META-INF/services/api.Greeter

This file **has no `.txt` extension**. The filename is `api.Greeter`, located in `META-INF/services` relative to the **classpath root of the plugin loader**.

File content, one line:

~~~text
plugin.PluginGreeter
~~~

Place it exactly at:

~~~text
plugin-classes/META-INF/services/api.Greeter
~~~

Do not create `plugin-classes/META-INF/services/api/Greeter`. The descriptor name keeps the **dots** in the binary service name.

### 6.6. Compiling with JDK 17+

In the `spi-loader-demo` directory:

~~~bash
javac --release 17 -d host-classes src-api/api/Greeter.java src-host/HostMain.java
javac --release 17 -d plugin-classes src-api/api/Greeter.java src-plugin/plugin/PluginGreeter.java
~~~

After compiling, **create the descriptor as described in Section 6.5**. On Linux/macOS/bash, you can run:

~~~bash
mkdir -p plugin-classes/META-INF/services
printf 'plugin.PluginGreeter\n' > plugin-classes/META-INF/services/api.Greeter
java -cp host-classes HostMain plugin-classes
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force plugin-classes/META-INF/services | Out-Null
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'plugin-classes/META-INF/services/api.Greeter'),
    "plugin.PluginGreeter" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
java -cp host-classes HostMain plugin-classes
~~~

Note that in Java 17, UTF-8 is the encoding of provider-configuration files. PowerShell 5.1 does not support the `::new(...)` syntax on all configurations? If that specific PowerShell does not support it, you can create this file manually with an editor and save it as UTF-8; this is only a resource preparation step and does not change the Java code.

### 6.7. Exact Stdout

With the files above and an application classpath containing only `host-classes`, the result is:

~~~text
isolated same API Class: false
isolated error: ServiceConfigurationError
shared same API Class: true
shared provider: hello from plugin
~~~

### 6.8. Analyzing the Results

**In isolated mode:**

1. `PluginLoader.loadClass("api.Greeter")` selects the `api.Greeter` copy under `plugin-classes` because `duplicateApi=true`.
2. `HostMain` is compiled with the `api.Greeter` copy located under `host-classes`, belonging to the host application loader.
3. Both names are `api.Greeter`, yet they are different `Class<?>` objects because their defining loaders differ.
4. `plugin.PluginGreeter` is defined by the plugin loader and resolves `implements api.Greeter` to the plugin's copy of the API.
5. `ServiceLoader.load(Greeter.class, loader)` retains the **host's service Class**, without switching to the plugin's service Class. It finds the descriptor and provider, then detects that the implementation **is not a subtype of the host service Class**, so it reports `ServiceConfigurationError`.
6. The code prints the **Error type name**, not the message, because the message text can vary across JDKs.

**In shared mode:**

1. `PluginLoader` still loads `plugin.PluginGreeter` local-first.
2. However, `api.Greeter` is not chosen local-first; the loader delegates to the parent and receives the **exact Class of the host**.
3. The provider implements the host API, so the subtype check succeeds.
4. ServiceLoader instantiates the provider via the public no-arg constructor and calls `greet()`, printing `hello from plugin`.

The change lies in the **loader policy for the `api.*` package**, not in modifying the interface name, constructor, descriptor, or plugin method. This is a systematic fix for a duplicated service API error.

## 7. Why Check “Same Class” Instead of “Same Name”?

A common diagnostic:

~~~java
Class<?> expected = Greeter.class;
Class<?> actual = pluginLoader.loadClass("api.Greeter");

System.out.println(expected.getName());
System.out.println(actual.getName());
~~~

**Illustrative code**: both lines can print `api.Greeter` identically and lead the reader to think the loader has no error.

Further checks are needed:

~~~java
System.out.println(expected == actual);
System.out.println(expected.getClassLoader());
System.out.println(actual.getClassLoader());
~~~

If `expected == actual` is false, examine the **parent chain, child-first rules, and API JAR duplicates**. A provider implements **its own** interface correctly, yet does not necessarily implement the **consumer's** interface.

For the loaded provider class:

~~~java
boolean assignable = Greeter.class.isAssignableFrom(providerClass);
~~~

If false, inspect `providerClass.getInterfaces()` and the defining loaders of those interfaces. Do not merely compare the string names of the interfaces.

## 8. “Not a subtype” Is Not Always Caused by Duplicate API Loading

Two common groups of causes:

### Provider Code Has an Incorrect Declaration

The descriptor lists `plugin.WrongGreeter`, yet that class does not implement `api.Greeter`, or was compiled against the wrong version of the interface, or the class is an adapter that has not yet been declared to implement it. The provider class must be fixed to match the contract.

### The API Is Redefined

`PluginGreeter implements api.Greeter` in the source, yet `api.Greeter` in the bytecode is resolved by the plugin class loader to a different runtime Class. You need to fix **loader ownership** or the packaging approach, not add `implements` again.

A triage workflow:

| Observation | Suggested Conclusion | Fix Step |
| --- | --- | --- |
| Provider does not declare implementing the service | Wrong class/descriptor | Fix the class or descriptor |
| Provider declares implements, service/interface Class differs | Duplicate API via loaders | Share the API in the parent |
| `isAssignableFrom` is true, instantiation fails | Constructor/factory/access/init | Inspect constructor and cause |
| Class not found | Lookup/packaging | Check classpath/JAR and loader |
| Descriptor cannot be found | Provider discovery path | Check `META-INF/services` |
| Error occurs when module configuration is created | JPMS descriptor/graph | Check `uses`, `provides`, and module readability |
| ServiceLoader lists the provider, yet cast fails elsewhere | Boundary/API identity | Check all DTO/exception/annotation contracts |

## 9. Provider-Configuration Files: Requirements That Are Easy to Get Wrong

In classpath-based SPI, the `META-INF/services/<binary service name>` file has these rules:

- The filename matches the **binary service name**, for example `META-INF/services/api.Greeter`.
- The provider name inside is the **fully qualified binary class name**, not a filesystem path.
- Each line declares one provider; `#` starts a comment, and whitespace is handled according to the format rules.
- The configuration should be saved in UTF-8.
- A typical provider class must be a public concrete class with a **public zero-argument constructor** when classpath registration is used.
- A provider appearing with duplicate names across configurations normally does not produce two separate providers of the same implementation under deduplication rules, yet **do not rely on declaration order** to select an important provider.
- An unreadable resource, invalid encoding/syntax, missing class, invalid constructor, or provider that is not a valid subtype can all cause `ServiceConfigurationError` during iteration.

A useful command:

~~~bash
jar --list --file plugin.jar
~~~

When `plugin.jar` exists, check whether `META-INF/services/api.Greeter` and `plugin/PluginGreeter.class` are present. This is only **packaging verification**; it does not yet guarantee that the provider Class shares the same service type as the host.

A JAR containing both `api/Greeter.class` and the implementation can work normally if the loader is always **parent-first for the API package**. The loading policy is what determines whether that copy of the API is actually defined a second time.

## 10. Lazy Discovery: Why Does Calling load() Not Report an Error Yet?

Example:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, loader);

System.out.println("created ServiceLoader");

for (Greeter provider : services) {
    System.out.println(provider.greet());
}
~~~

This is **illustrative code** (with a matching service type and loader). The statement creating `ServiceLoader` usually does not instantiate all providers yet. Only when the program begins to iterate does Java read the configuration, validate the provider class, and instantiate instances on demand.

Therefore:

- A test that merely calls `ServiceLoader.load(...)` and concludes the SPI is valid is insufficient.
- It is possible for the first provider to work while the second provider fails as iteration continues.
- `ServiceLoader.stream()` provides a stream of `ServiceLoader.Provider<S>`; **obtaining the list of provider types** and **calling `Provider.get()`** do not occur at the exact same instantiation point.
- Do not rely on provider discovery order across every classloader/module environment to assert “which provider will be loaded first” if the API does not guarantee a fixed order.
- `ServiceLoader.reload()` clears the internal cache and causes discovery to run again on subsequent iterations; it **does not change the runtime Class already defined by a loader** or automatically fix API duplication errors.

### Note on Catching ServiceConfigurationError

Because `ServiceConfigurationError extends Error`, the snippet:

~~~java
try {
    for (Greeter g : services) {
        g.greet();
    }
} catch (Exception e) {
    System.out.println("caught");
}
~~~

**Is not the right pattern for catching configuration errors**: `catch (Exception)` does not catch `ServiceConfigurationError`.

If you want to diagnose/disable an invalid provider at the boundary:

~~~java
try {
    Greeter provider = services.iterator().next();
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("SPI discovery failed: "
            + error.getMessage());
}
~~~

This is an illustrative snippet. You may catch this specific Error type at the **plugin execution boundary** to log or transition state, but you should not catch every `Error` or every `Throwable` and continue as if nothing failed: serious VM/linkage errors require different handling.

## 11. Named Modules: Differences from Classpath Descriptors

Since Java 9, providers registered in a **named module** typically use `module-info.java` instead of a classpath descriptor.

Example API module:

~~~java
module greeter.api {
    exports api;
}
~~~

Consumer module:

~~~java
module greeter.app {
    requires greeter.api;
    uses api.Greeter;
}
~~~

Implementation module:

~~~java
module greeter.impl {
    requires greeter.api;
    provides api.Greeter with plugin.PluginGreeter;
}
~~~

**These three descriptors only illustrate the module layout**, not a complete runnable project yet; running it still requires Java sources, module paths, and valid module resolution.

Key points:

- `uses api.Greeter` declares the service dependency in the named consumer module.
- `provides api.Greeter with plugin.PluginGreeter` declares the provider of the service.
- The provider module must use the **same service contract** via module resolution, rather than shipping a separate `api.Greeter` class inside the implementation module.
- In named modules, a provider can use a **public static provider method** named `provider` (per `ServiceLoader` rules) returning the service implementation; therefore, you must not mechanically apply the condition “the provider class must implement the service” to **every kind of provider factory in a named module**.
- When using a direct provider class instead of a provider method, the provider must conform to the service type and a construction form accepted by the JDK.
- `ServiceLoader.load(ModuleLayer layer, Class<S> service)` locates providers in the layer and its parent layers according to the API contract, which has different semantics from merely scanning descriptor files from a URLClassLoader.
- Module readability, module roots, package exports/opens, and service binding can cause errors **before ServiceLoader instantiates a provider**; not every error should be lumped into “not a subtype”.

**Important distinction:** a provider class housed in a named module can be valid thanks to a `provider()` factory returning the service type, even if the provider class itself is not a direct subtype. In the classpath example above, a conventional provider implementation must be a subtype and have a public no-arg constructor.

## 12. ModuleLayer, Service Class Identity, and Plugin Architecture

A plugin system may create its own `ModuleLayer` for each plugin. When doing so, you need to ensure that the module containing the shared service API belongs to the **parent/common layer** and is referenced consistently by the plugin implementations.

Recommended diagram:

~~~text
Boot / Parent ModuleLayer
  greeter.api
    api.Greeter
       ^
       |
Plugin ModuleLayer A
  greeter.impl.a
    provides api.Greeter

Plugin ModuleLayer B
  greeter.impl.b
    provides api.Greeter
~~~

If each layer defines `api.Greeter` on its own from a copy of the API module using a different class loader, the host cannot treat those two Classes as the same contract merely because their module/binary names match.

Some other JPMS errors to separate:

| Error | Investigation Category |
| --- | --- |
| `FindException` | Required named module not found |
| `ResolutionException` | Module graph/readability/export conflict |
| `LayerInstantiationException` | Mapping modules to loaders, overlapping packages, or layer conditions |
| `IllegalAccessError` / `InaccessibleObjectException` | Module access/exports/opens |
| `ServiceConfigurationError` | Provider discovery/configuration/subtype/construction |
| `ClassCastException` | Typed cast across incompatible runtime Classes |

Switching to named modules **does not automatically fix** an API class duplicated across loaders. You must design the ownership of the service Class at the boundary.

## 13. Thread Context ClassLoader (TCCL): Necessary but Not Sufficient

Many libraries call:

~~~java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class);
~~~

This overload typically uses `Thread.currentThread().getContextClassLoader()` to choose the scope for finding providers. When host and plugins have multiple loaders, the TCCL may be pointing to a loader that cannot see the descriptor/provider.

A pattern on the host:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<Greeter> services =
            ServiceLoader.load(Greeter.class);
    // Iterate over service providers within the scope of the plugin task.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is an **illustrative snippet**; `pluginLoader` and `Greeter` must actually exist. You must restore the TCCL to avoid affecting other work on the same thread.

The TCCL helps the API find provider metadata/classes in the scope of the chosen loader, yet **does not change the defining loader of `Greeter.class` held by the caller**. If the plugin class implements a copy of `api.Greeter` that is a different runtime Class, ServiceLoader still rejects it.

In multithreaded applications, async tasks, or executors, the TCCL might not propagate across thread boundaries as desired; prefer the overload accepting an explicit loader when you explicitly manage the service discovery context.

## 14. Common Configuration/Packaging Mistakes

### Descriptor Placed in the Wrong Directory

Wrong:

~~~text
src/META-INF/services/api.Greeter
app/META-INF/services/api/Greeter
META-INF/services/plugin.PluginGreeter
~~~

Correct for service `api.Greeter`:

~~~text
META-INF/services/api.Greeter
~~~

The resource must reside at the **classpath/JAR root** that the loader searches when looking up `META-INF/services/...`.

### Content Lists a Non-Existent Class

~~~text
plugin.GreeterProviderV2
~~~

If the artifact only contains `plugin.PluginGreeter`, ServiceLoader may report that the provider was not found. This is a lookup error, not type identity.

### Provider Lacks a Suitable Constructor/Factory

A class that only has constructors requiring parameters without a no-arg constructor may not be instantiated by classpath ServiceLoader as a normal provider class. Named modules have the ability to use a provider factory per their own contract.

### API Dependency Packaged Twice

The plugin fat JAR copies `api.Greeter`, and the child-first loader defines the plugin's copy. This is the source of the “not a subtype” error even though the Java code looks right.

### Wrong API Version

A provider compiled against a version of `Greeter` with a different method signature can cause `NoSuchMethodError`, `AbstractMethodError`, or other linkage errors, not necessarily just `ServiceConfigurationError`. Inspect the dependency tree, module graph, and actual classpath/JAR.

### Multiple Providers for the Same Service

If there are multiple descriptor files with the same name, ServiceLoader may discover multiple providers. One faulty provider interrupts iteration; you should not test only the first provider. When priority ordering is needed, select using explicit metadata or application logic rather than blindly relying on the environment's JAR order.

## 15. Diagnosing ServiceConfigurationError Systematically

When encountering an SPI error:

1. **Read the full stack trace and cause**: record the service name, provider name, class loaders, and message; do not keep only the `ServiceConfigurationError` line.
2. **Verify the host's service Class**: `Greeter.class.getName()`, `getClassLoader()`, `getModule()`.
3. **Verify the provider descriptor**: is the `META-INF/services/api.Greeter` path correct? Does the content contain the correct binary name?
4. **Verify whether the provider class is found** using the exact loader that ServiceLoader uses.
5. **Compare service identity**: `hostService == pluginLoader.loadClass("api.Greeter")` in the corresponding API package scenario.
6. **Check assignability**: `hostService.isAssignableFrom(providerClass)` with the exact provider Class.
7. **Inspect provider interfaces**: `providerClass.getInterfaces()` and the defining loader of each interface.
8. **Check construction**: a public concrete class/no-arg constructor for a conventional classpath provider, or the proper provider factory in a named module.
9. **Check dependency scope**: does the plugin bundle a copy of the API in its fat JAR? Have Maven/Gradle been configured with provided/compileOnly when the host provides the API?
10. **Check loader policy**: is shared `api.*` parent-first? Is private `plugin.*` on its own proper loader?
11. **Check TCCL and module layer**: which loader is the API invoked with, and has the service been resolved in the module graph?
12. **After fixing, iterate over all providers** in the real deployment environment, rather than only calling `ServiceLoader.load`.

A helper:

~~~java
static void describe(String label, Class<?> type) {
    System.out.println(label + " name=" + type.getName());
    System.out.println(label + " loader=" + type.getClassLoader());
    System.out.println(label + " module=" + type.getModule());
}
~~~

This is an **illustrative snippet inside a Java class**, not a standalone runnable file.

In HotSpot/OpenJDK, you can enable class loading logs:

~~~bash
java -Xlog:class+load=info -cp host-classes HostMain plugin-classes
~~~

JVM stdout/stderr logging varies across environments, so no fixed transcript is published. Observing logs only helps identify the classfile origin; **directly comparing the runtime Class/defining loader** remains the best evidence of type identity.

## 16. Architecture to Avoid Duplication and Protect the Boundary

A reliable plugin design should clearly separate:

| Component | Recommended Defining Location |
| --- | --- |
| Service interface `api.Greeter` | Shared parent loader/module |
| Service DTO and callback types | Shared parent loader/module |
| Annotations the host needs to scan | Shared parent loader/module |
| Typed exception contract | Shared parent loader/module |
| Provider implementation | Plugin loader/module |
| Private third-party library | Plugin loader if isolation is needed |
| Java core types | Bootstrap/platform delegation |

Some principles:

- Do not apply child-first indiscriminately to every package present in a fat JAR.
- Do not relocate/shade a shared service API without a clear adapter contract.
- Use Maven `provided` scope or Gradle `compileOnly` when the host **actually provides** the shared API at runtime; build configuration must match deployment, rather than being a rule applied to every project.
- Inspect the built artifact itself: was the descriptor copied into the JAR? Was the provider class preserved after shading/minification? Was the resource name altered incorrectly?
- Categorize discovery errors into **missing provider**, **invalid descriptor**, **type mismatch**, **constructor/factory failure**, and **module access/linkage** for logging and operational support.
- If providers are supplied by an untrusted party, `ServiceLoader`/`ClassLoader` is not a sandbox for file/network permissions. You must protect at the process/OS/container boundary according to your threat model.
- A provider may have a static initializer that causes side effects or fails during initialization; consider lifecycle, caching, cleanup, and isolation when plugins can be reloaded.

## 17. Edge Cases to Understand Clearly

### No Providers Found

A valid ServiceLoader can return an empty iterator when there are no providers. Calling `iterator().next()` on an empty iterator leads to `NoSuchElementException`, **not** `ServiceConfigurationError` merely because there are no providers.

In the runnable example in Section 6, the descriptor file already has a provider so this situation does not occur; production code should check `hasNext()` or iterate with `for-each`.

### Descriptor Lists a Valid Class That Is Not a Subtype

This is a genuine provider configuration error. Do not “fix” it by casting through `Object` or comparing interface names. Fix the implementation or loader ownership.

### Provider Factory in a Named Module

A public static `provider()` method following ServiceLoader rules can return the service type, so the class containing the factory **does not necessarily** implement the service interface directly. Do not apply the subtype table meant for classpath constructor providers to every named-module factory.

### Hot Reload Does Not Automatically Replace the Service Class

`ServiceLoader.reload()` discards ServiceLoader's own discovery/instance cache, but Classes already defined by the old loader are not rewritten. To use new plugin bytes with the same names, you usually need a new loader and a lifecycle handoff design; keep the shared API in the parent to avoid cast errors across plugin versions.

### Exceptions from the Provider Implementation

An exception thrown from `provider.greet()` is an error during **business invocation after the provider is created**, and does not automatically become a `ServiceConfigurationError`. Conversely, errors occurring in the constructor/provider factory may be wrapped/reported by ServiceLoader as a configuration error.

### ServiceLoader Instances Are Not Thread-Safe

According to the Javadoc, `ServiceLoader` is not guaranteed to be safe for arbitrary concurrent operations. If a system wants to share an instance across multiple threads, synchronization/caching must be controlled by design. Do not simultaneously call `reload()` and iterate on the same instance and expect stable behavior.

## 18. Knowledge Self-Check

**Question 1. Is `ServiceConfigurationError` a subtype of `Exception`?**  
No; it extends `Error`.

**Question 2. Why is a class with a `greet()` method not automatically a provider of `Greeter`?**  
Java requires subtype compatibility for conventional classpath providers, rather than relying on structural method matching.

**Question 3. The plugin source writes `implements api.Greeter`. The host still reports not a subtype. What needs to be checked?**  
Compare `Greeter.class` in the host with `api.Greeter` resolved by the plugin loader; check the defining loaders and child-first policy.

**Question 4. Do two different ClassLoaders necessarily create two different service Classes?**  
No. Parent delegation can use a single Class defined by a common parent.

**Question 5. What is the name of the provider descriptor file for the `api.Greeter` service?**  
`META-INF/services/api.Greeter`.

**Question 6. Is writing the path `plugin/PluginGreeter.class` inside the descriptor correct?**  
No. It must specify the **binary provider name**, for example `plugin.PluginGreeter`.

**Question 7. Does `ServiceLoader.load(...)` returning without error prove that the provider is valid?**  
Not yet. Discovery and instantiation happen lazily during iteration.

**Question 8. Why does `Class.isAssignableFrom` return false when the service name is the same?**  
The provider may implement a runtime service Class from a different loader, or genuinely not implement the contract.

**Question 9. Does `ServiceLoader.reload()` automatically make two Classes with the same name become one?**  
No. It only refreshes ServiceLoader's internal cache.

**Question 10. Does a named-module provider factory always require the class containing the factory to implement the service interface?**  
No. A valid provider method can return the service type; the rule differs from conventional classpath constructor providers.

**Question 11. Does changing the TCCL to the plugin loader fix API duplication?**  
No. The TCCL helps with lookup; it does not change an already-defined type identity.

**Question 12. Where should shared interfaces, DTOs, annotations, and exceptions be placed?**  
In a common parent loader/module that both host and plugin reference consistently.

## 19. Official Documentation

- **Java SE 17 — ServiceLoader API:** classpath providers, `META-INF/services`, provider factories, lazy discovery, `reload`, `ServiceConfigurationError`, and module semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **Java SE 17 — ServiceConfigurationError:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html
- **Java SE 17 — ClassLoader:** delegation, `loadClass`, `findClass`, and loader identity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — Class:** `isAssignableFrom`, `getClassLoader`, `getModule`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 — ModuleLayer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- **JVMS Java 17 §5.3 — Creation and Loading:** runtime identity and defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JLS Java 17 §12.2 — Loading of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
