# ServiceConfigurationError Can Occur During Provider Discovery or Instantiation

## 1. Context: Provider Discovery Differs from Provider Instantiation

In Java, `java.util.ServiceLoader` is a mechanism for locating implementations of a **service contract** (interface or abstract class) without hard-coding each implementation into the program. The application acts as the **consumer/host**; each implementation is distributed as a **provider**. For example, the host defines `Greeting`, while plugins supply `EnglishGreeting` and `VietnameseGreeting`.

A usage flow can span multiple stages:

1. **Creating the loader (`ServiceLoader.load(...)`):** creates the object that manages provider lookup. This operation typically does not instantiate all providers yet.
2. **Discovery (`discovery`):** reads the provider list in `META-INF/services` or JPMS module metadata, determining which providers can be found.
3. **Loading and type checking:** the JVM/`ServiceLoader` locates the class, verifies validity, and checks compatibility with the service contract.
4. **Instantiation (`instantiation`):** creates an instance via constructor or the `provider()` mechanism supported by JPMS where applicable.
5. **Business invocation:** the host calls methods on the obtained instance.

**`java.util.ServiceConfigurationError` can occur when Java detects a provider is configured invalidly, cannot be found/loaded, does not conform to the contract, or cannot be instantiated.** An easy-to-miss detail is that the error can arrive quite late: code calling `ServiceLoader.load(...)` succeeds, only to break when traversing the iterator, reading a `Provider` from a stream, or calling `Provider.get()`.

`ServiceConfigurationError` is a subclass of `java.lang.Error`, **not `Exception`**. Therefore `catch (Exception e)` will not catch it. Although its name contains "configuration", error details can involve class loading, linking, or running constructors, not merely configuration file syntax errors.

### 1.1. Missing Providers and Broken Providers Are Two Different Situations

- **No providers found:** with normal `ServiceLoader`, an empty iterator has `hasNext() == false`; `stream().findFirst()` can return `Optional.empty()`. This is not automatically a `ServiceConfigurationError`.
- **A provider is declared, yet the declaration/implementation is broken:** while Java parses or creates the provider, it can throw `ServiceConfigurationError`.
- **The provider is created, yet a business method fails:** exceptions from that method (such as `IOException`, `IllegalStateException`) do not automatically turn into `ServiceConfigurationError` merely because the instance was discovered via `ServiceLoader`.

Distinguishing these three situations helps the host return accurate messages: "no plugin present" differs from "plugin declared but cannot load", and both differ from "plugin ran and failed during processing".

## 2. Where Do Errors Appear in the API?

Consider a common snippet:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);
for (Codec codec : loader) {
    System.out.println(codec.name());
}
```

Here `Codec` is an application-defined service interface, not a built-in JDK API. The `for-each` loop drives the iterator underneath; if metadata or a provider is broken, the failure can explode **inside the loop**, even though the `load(...)` line already completed.

| API or Operation | What Can Happen | Key Point |
| --- | --- | --- |
| `ServiceLoader.load(service)` / `load(service, classLoader)` | Creates the loader and performs some initial checks | Does not guarantee all providers were found, verified, and created; some invalid conditions may fail immediately upon calling |
| `loader.iterator()` | Obtains an iterator for lazy discovery/instantiation | Cannot conclude providers are valid just because creating the iterator succeeded |
| `iterator.hasNext()` | May read/parse provider declarations or inspect module info | Broken metadata may surface when checking for the next element |
| `iterator.next()` | May load the class, verify subtype, invoke constructor or appropriate factory | An unloadable provider or failed instantiation can throw `ServiceConfigurationError` |
| `loader.stream()` and terminal operations | Stream of `ServiceLoader.Provider<S>` objects, also processed lazily | Errors can arise while traversing the stream; do not treat `stream()` as full verification |
| `provider.type()` / `provider.get()` | Resolves provider type or obtains instance (depending on packaging) | `get()` can fail during provider instantiation |
| `loader.reload()` | Clears the loader's provider cache so the next traversal searches again | Does not fix broken configuration files, missing classes, or failing constructors |

The progression can be visualized as:

```text
ServiceLoader.load(...)
    |
    v
ServiceLoader (usually does not hold all instances yet)
    |
    v
iterator / stream: read provider declarations
    |                     |
    | bad metadata        +--> ServiceConfigurationError
    v
locate class, verify provider validity
    |                     |
    | class/type error    +--> ServiceConfigurationError
    v
instantiate provider
    |                     |
    | constructor/factory +--> ServiceConfigurationError
    v
receive instance, call business method
                          |
                          +--> business error per contract, not ServiceConfigurationError by default
```

This is a conceptual diagram. The API may merge or defer different stages depending on classpath vs. JPMS mechanics. Do not rely on assuming a specific error always occurs at exact `hasNext()` or exact `next()` across all Java versions.

## 3. Common Causes During Provider Discovery

### 3.1. Invalid Configuration File on the Classpath

For providers declared via the classpath, Java looks for a resource at path:

```text
META-INF/services/<fully qualified binary name of service>
```

For example, if the service is `com.example.spi.Codec`, the file path is:

```text
META-INF/services/com.example.spi.Codec
```

The content is usually the fully qualified binary name of each provider class, one per line, UTF-8 encoded; blank lines and `#` comments are permitted by the service configuration format. Example:

```text
# Providers supporting Codec
com.example.codec.JsonCodec
com.example.codec.XmlCodec
```

Errors to look for:

- Syntactically invalid class names in the configuration file.
- Configuration file path does not match the service name or the resource was packaged in the wrong place; this situation usually causes **no providers to be found**, though not necessarily throwing an error.
- The file declares a class that no longer exists after refactoring or was not packaged into the JAR/classpath.
- Multiple JARs contain the same service file; configurations are aggregated during discovery and one broken file can still make traversal fail.
- A shaded/relocated JAR renamed class packages while the descriptor still holds old names.
- The resource or a declared entry cannot be read/parsed properly.

Key point: a JAR that is valid as a ZIP archive can still contain a broken *service configuration*. Having `jar tf plugin.jar` succeed does not verify that each provider will load and instantiate.

### 3.2. Declared Class Does Not Match the Service Contract

For example, the resource names `com.example.codec.JsonCodec`, yet that class does not implement/extend the corresponding `com.example.spi.Codec`. Java can report `ServiceConfigurationError` instead of returning an improperly typed instance.

Pay attention to **class identity = class name + defining class loader**. Two classes with the same name `com.example.spi.Codec` defined by two independent class loaders can be two distinct Java types. A plugin might bundle a duplicate copy of the SPI interface, making the implementation "look right by name" yet fail assignability to the host's service interface.

How to reduce errors: keep the shared API/SPI in a shared class loader by design, control duplicate dependencies, and inspect actual class loaders. Do not use class name strings to conclude for certain that two `Class<?>` objects are the same type.

### 3.3. Invalid Instantiation Requirements or Unloadable Class

For classpath providers, the common form requires a provider class compatible with the service and a **public no-argument constructor** so `ServiceLoader` can instantiate it. Failure cases can include:

- The provider class is not accessible as required.
- Missing public zero-argument constructor under the corresponding classpath rules.
- The constructor throws an exception while constructing the instance.
- A dependency of the class is missing or incompatible during linking/loading, preventing the provider from being created.
- Static initialization or class linking steps fail.

In some code paths, the root failure is wrapped into `ServiceConfigurationError` and accessible via `getCause()`. However, other serious JVM/linkage errors can also arise directly; do not assume every `LinkageError` or `ExceptionInInitializerError` is wrapped identically.

### 3.4. Differences When Using JPMS

In the Java Platform Module System (JPMS), providers can be declared in `module-info.java`:

```java
module example.codec.provider {
    requires example.codec.api;
    provides com.example.spi.Codec
        with com.example.codec.JsonCodec;
}
```

Consumer modules typically need to declare `uses` for the service:

```java
module example.codec.host {
    requires example.codec.api;
    uses com.example.spi.Codec;
}
```

For providers in an **explicit named module**, JPMS supports certain cases using a **public static `provider()` factory method** to return the service instance; therefore, do not apply the rule "every provider must have a public no-arg constructor" to every module deployment style. The host must check the exact rules of the mechanism in use.

Errors can come from the consumer failing to declare `uses` when required, invalid `provides ... with ...` declarations, invalid provider class/method, uninstantiable classes, or misconfigured module layers. Do not fix JPMS errors by mechanically adding `META-INF/services`; inspect module descriptors and the actual loading path first.

## 4. Runnable Java 17+ Example: Error on Class Lookup and Error in Constructor

This example is standalone with no external libraries. It temporarily creates a service configuration resource to simulate three scenarios: a valid provider, a nonexistent provider class, and a provider constructor throwing an exception. Each scenario uses its own `URLClassLoader`; the program cleans up temporary files after running.

Create exactly **one file `SpiErrorDemo.java`**:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public class SpiErrorDemo {
    public interface Greeting {
        String sayHello();
    }

    public static final class Ready implements Greeting {
        public Ready() {}
        @Override public String sayHello() {
            return "hello";
        }
    }

    public static final class Broken implements Greeting {
        public Broken() {
            throw new IllegalStateException("constructor failed");
        }
        @Override public String sayHello() {
            return "never reached";
        }
    }

    static void runCase(String label, String providerName) throws Exception {
        Path root = Files.createTempDirectory("spi-demo-");
        Path services = root.resolve("META-INF").resolve("services");
        Path config = services.resolve(Greeting.class.getName());
        try {
            Files.createDirectories(services);
            Files.writeString(config, providerName + "\n", StandardCharsets.UTF_8);

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {root.toUri().toURL()},
                    SpiErrorDemo.class.getClassLoader())) {
                ServiceLoader<Greeting> providers =
                        ServiceLoader.load(Greeting.class, loader);
                System.out.println(label + ": loader created");
                try {
                    Iterator<Greeting> iterator = providers.iterator();
                    Greeting greeting = iterator.next();
                    System.out.println(label + ": " + greeting.sayHello());
                } catch (ServiceConfigurationError error) {
                    System.out.println(label + ": " +
                            error.getClass().getSimpleName());
                }
            }
        } finally {
            Files.deleteIfExists(config);
            Files.deleteIfExists(services);
            Files.deleteIfExists(services.getParent());
            Files.deleteIfExists(root);
        }
    }

    public static void main(String[] args) throws Exception {
        runCase("valid", Ready.class.getName());
        runCase("missing", "not.present.MissingProvider");
        runCase("broken", Broken.class.getName());
    }
}
```

Run in the directory containing the file (JDK 17 or later):

```bash
javac --release 17 SpiErrorDemo.java
java SpiErrorDemo
```

**Exact output** verified with JDK 17+:

```text
valid: loader created
valid: hello
missing: loader created
missing: ServiceConfigurationError
broken: loader created
broken: ServiceConfigurationError
```

Why does this output occur?

- `valid`: descriptor points to `SpiErrorDemo$Ready`, class exists, implements `Greeting`, and has a public no-arg constructor. `next()` returns the instance; `sayHello()` returns "hello".
- `missing`: descriptor points to `not.present.MissingProvider`, which does not exist. `load(...)` still returns a loader; when `next()` looks for the provider, Java detects the configuration error and throws `ServiceConfigurationError`.
- `broken`: class `SpiErrorDemo$Broken` exists and has a properly shaped constructor, yet the constructor throws `IllegalStateException`. `ServiceLoader` cannot create the provider; calling `next()` produces `ServiceConfigurationError`.

The example prints the **error type**, not `error.getMessage()`, because detailed messages and paths can vary by environment/JDK. In production applications, preserve the full stack trace and `getCause()` so the root cause is not lost.

One often-overlooked detail is that the Java binary name of a nested class contains the `$` character; the example uses `Ready.class.getName()` rather than guessing resource names. It also illustrates why the service file name must match the exact binary name of the service.

Creating `Files.createTempDirectory` is solely for this self-contained demo; when packaging real plugins, service configuration resources normally live inside the JAR, generated/copied by build tools. There is no need to create temporary config files on every application run.

## 5. Catching in the Right Place Without Swallowing Errors

A common anti-pattern:

```java
try {
    ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
    // Only creates the loader, has not traversed providers yet.
} catch (Exception e) {
    // Will not even catch ServiceConfigurationError.
}
```

With `Codec` as an application interface, the snippet above only illustrates catch placement; it is insufficient for validating the provider list. To catch discovery/instantiation errors, wrap **the provider-consuming operations** and catch `ServiceConfigurationError` specifically:

```java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
try {
    for (Codec codec : codecs) {
        register(codec);
    }
} catch (ServiceConfigurationError failure) {
    // Use a real logging system to preserve stack trace and cause.
    logProviderFailure(failure);
    throw failure; // Example: fail-fast when codec is a required dependency.
}
```

Both snippets above are **illustrative integration code**, not standalone runnable since `Codec`, `register`, and `logProviderFailure` belong to the application.

Choose a policy based on the service's role:

- **Required provider:** fail-fast with cause and context; do not report startup success when an essential dependency is missing.
- **Optional provider:** clearly report the broken extension, isolate when possible, and continue with independent providers verified to be safe. To skip individual plugins reliably, the architecture usually needs proper plugin/module/class-loader boundaries.
- **Business-critical or privileged provider:** verify trust, compatibility, and authorization before activation; do not use a load failure as a signal to automatically fall back to a less-trusted provider.

**Do not assume you can simply `catch` and keep calling `next()` on the same iterator until errors stop.** API documentation allows some traversals to attempt recovery after `ServiceConfigurationError`, yet recovery is not guaranteed across all failures/configurations. Unbounded retries can repeatedly hit the same broken provider. Safer approaches are fixing the configuration, isolating the failing source, or failing according to a clear policy.

Likewise, `loader.reload()` refreshes the provider discovery cache; it **does not** fix missing classes or constructors that always throw exceptions, and does not replace adjusting class loaders/module layers. Avoid overly broad `catch (Error)` or `catch (Throwable)` when you only want to handle service configuration errors, as that mixes `ServiceConfigurationError` with other critical JVM errors.

## 6. Diagnosing Errors in Real Projects

When receiving `ServiceConfigurationError`, record the **stage**, service name, declared provider (if known), class loader/module layer, and root cause; do not just log "cannot load plugin". An ordered investigation flow:

1. **Locate the actual site in the stack trace:** `ServiceLoader.load(...)`, `hasNext()`, `next()`, `Provider.get()`, or constructor code? Which API call line triggered the error matters more than where the host declared the loader variable.
2. **Read `error.getMessage()` and the `getCause()` chain:** is there a class/provider name, typo, non-assignability, constructor error, or missing dependency? Keep the original stack trace to see whether failure happened before or during instantiation.
3. **Verify the service contract and classpath configuration:** is `META-INF/services/<service binary name>` exact; is each line a valid binary name; is the provider class present in the actual deployed artifact?
4. **Check types/class loaders:** do provider and host share the same SPI class identity; are packages shaded, JARs duplicated, dependencies excluded, or class loaders isolated?
5. **Check constructor/factory and dependencies:** does the provider have a constructor matching the mechanism, does it read mandatory environment variables/credentials/configs causing the constructor to throw? For JPMS, also verify `uses`/`provides`, module readability, and provider methods.
6. **Reproduce using real deployment artifacts/runtime:** IDE classpaths, unit tests, and production can differ. Test each plugin independently, checking Java version, module path, and parent class loader.
7. **Fix the root cause, redeploy, and test lifecycle:** discovery, instantiation, and business methods must be verified separately; only use `reload()` when runtime policy allows and the environment actually changed.

Helper commands for inspecting a JAR (substitute your artifact filename):

```bash
jar tf plugin.jar
jar --describe-module --file plugin.jar
```

The first command lists entries to locate `META-INF/services/...` and expected classes. The second describes the JAR's module metadata where applicable; automatic modules and explicit modules behave differently. These commands **only check packaging**, and do not guarantee the provider can be instantiated.

In a system with multiple class loaders, you can inspect which resources a loader sees:

```java
String path = "META-INF/services/" + Codec.class.getName();
var resources = pluginClassLoader.getResources(path);
while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

This is an **illustrative diagnostic snippet**, requiring the application to have defined `Codec` and `pluginClassLoader`. Resource URLs may contain environment paths; consider sensitive data when logging in production. When the API finds no resources, an empty result only proves **the loader in use** does not see that resource, not that the source JAR lacks it.

### 6.1. Useful Information to Include in Logs

| Information | Purpose |
| --- | --- |
| Service interface/binary name | Identify the exact contract being loaded |
| Provider class (if known) | Pinpoint the broken declaration entry |
| Plugin artifact, version, checksum (if available) | Distinguish actual deployed builds |
| Class loader/module name/layer | Spot class identity conflicts and module layout issues |
| `discovery` vs. `instantiate` stage | Narrow down metadata, class loading, or constructor failure |
| Error message, full stack, cause chain | Trace root cause and decide recovery plan |

Do not log tokens, passwords, or secret configuration contents read from providers; diagnostic info should be sufficient to locate faults without leaking sensitive data.

## 7. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| "Once `ServiceLoader.load()` passes, all plugins are valid." | Providers are usually discovered/instantiated lazily | Verify during iteration/`Provider.get()` and real instantiation |
| "Having no plugins always throws `ServiceConfigurationError`." | An empty list is a different state from broken configuration | Check `hasNext()`/`Optional` and define a missing-provider policy |
| "`catch (Exception)` catches this error." | `ServiceConfigurationError extends Error` | Catch `ServiceConfigurationError` specifically at the load boundary |
| "Having a correctly named service file means the class will load." | Descriptor may point to a relocated package, missing dependency, or wrong type | Check classpath, class loader, and instantiation |
| "Every provider must have a no-arg constructor." | Explicit JPMS providers can use public static `provider()` | Apply the rules matching the deployment mode |
| "If I catch and call `next()` again, it will safely skip the broken provider." | Iterator recovery is not guaranteed | Isolate broken plugins or fail-fast per policy |
| "`reload()` fixes configuration errors." | Reload only refreshes `ServiceLoader`'s cache | Fix the underlying resource/class/config/constructor |
| "Exceptions in business methods are always configuration errors." | Provider is already instantiated; errors can happen afterward | Handle per the business method's contract |
| "Any classes with the same name are the same SPI type." | Class loaders participate in type identity | Share API/SPI classes with consistent identity |
| "Errors can be swallowed so the host always stays up." | Host may report ready while missing mandatory capabilities | Maintain clear health/status and degrade per defined policy |

## 8. Checklist for Testing Provider Discovery and Instantiation

A reliable extensibility system should have the following test cases, run with **the exact classpath/module path of the release environment**:

- **Valid provider:** discovered and method calls produce expected results.
- **No provider:** returns empty state per contract, without misinterpreting it as a broken provider.
- **Malformed configuration file:** detects the error and pinpoints which metadata is invalid.
- **Nonexistent provider class name or renamed during packaging:** detects error at the right stage; logs class name and artifact.
- **Named class not assignable to service:** does not attempt to cast and continue.
- **Missing valid constructor or constructor throws exception:** records `ServiceConfigurationError` along with its cause (when provided).
- **Missing dependency, incompatible Java version, or split SPI class loaders:** investigates linkage/class identity in the exact runtime environment.
- **Missing or incorrect JPMS `uses`/`provides` declarations:** distinguishes module errors from classpath errors.
- **Multiple providers mixing valid and broken ones:** verifies fail-fast/isolation strategy; does not depend on iterator self-recovery.
- **Provider implements method and fails later:** ensures the system handles it per business contract, without mislabeling it as service discovery failure.

The core takeaway is that **discovering a provider and successfully using a provider are two distinct levels of verification**. When designing Java extension systems, separate published metadata, loadable classes, instantiable objects, and executable business operations. Place error handling around the right stage, preserve root causes, and establish clear policies for required vs. optional providers; that turns `ServiceConfigurationError` into a useful diagnostic signal rather than a "random" startup crash.
