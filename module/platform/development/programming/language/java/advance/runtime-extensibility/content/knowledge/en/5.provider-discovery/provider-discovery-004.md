# Using stream, Provider.type, and Provider.get to Separate Type Inspection from Object Creation

## 1. The Problem: Discovering Providers Without Instantiating All of Them

In a Java application with extension points, a **service** is the contract known in advance by host code, typically an interface or abstract class. A **service provider** is a registered implementation that can be discovered when the application runs. For example, a text-processing application has a TextTransformer contract, while providers supply uppercase, string-reversal, or normalization implementations.

Sometimes the host only wants to **inspect which providers can satisfy a request**, and only then create an instance of the chosen provider. Instantiating a provider may trigger configuration checks, opening connections, allocating resources, registering listeners, or errors due to missing dependencies. With eager-instantiation traversal, the host may end up instantiating providers that are never selected.

Since **Java 9**, ServiceLoader provides a **stream()** method returning provider descriptors, allowing **type inspection first, instance creation later**:

~~~java
ServiceLoader<TextTransformer> loader =
        ServiceLoader.load(TextTransformer.class);

ServiceLoader.Provider<TextTransformer> selected = loader.stream()
        .filter(p -> p.type().isAnnotationPresent(Preferred.class))
        .findFirst()
        .orElseThrow();

TextTransformer transformer = selected.get();
~~~

This is an **illustrative snippet**, assuming TextTransformer and the Preferred annotation are already defined. The core idea is:

1. **stream()** produces a Stream of **ServiceLoader.Provider<TextTransformer>**, not a Stream<TextTransformer>.
2. **p.type()** gives the **Class<? extends TextTransformer>** type info for classifying, filtering, reading annotations, or getting the class name without invoking the constructor/provider factory to obtain an instance.
3. **p.get()** actually requests a TextTransformer instance from the chosen provider descriptor.

This separation is also called **discovery/selection first, instantiation later**. It is useful when providers carry class-level metadata (such as annotations) and the host can decide using that metadata.

## 2. Three APIs and Types to Remember

| API | Result | Creates service instance immediately? | Used for |
|---|---|---|---|
| **ServiceLoader.load(ServiceType.class)** | ServiceLoader<ServiceType> | Not an operation that creates all instances | Creating the loader for a service and class loader/module context |
| **loader.stream()** | Stream<ServiceLoader.Provider<ServiceType>> | No | Traversing provider descriptors on demand when a terminal operation runs |
| **provider.type()** | Class<? extends ServiceType> | Does not call the provider constructor/provider method to create a service instance | Inspecting type, name, annotations, and type metadata |
| **provider.get()** | ServiceType | Yes, requests creating/obtaining an instance | Beginning to use the provider |
| **loader.iterator()** or **for-each** loop | ServiceType instances | Yes, when advancing to an element | Directly iterating provider instances |

Provider here is **java.util.ServiceLoader.Provider<S>**, a nested interface extending **Supplier<S>** and adding **type()**. Do not confuse it with an application-defined interface named *PluginProvider* or *Factory*: they may serve a similar design purpose, but they are different abstractions.

Processing flow diagram:

~~~text
ServiceLoader.load(TextTransformer.class)
               |
               v
         loader.stream()
               |
               v
       Stream<Provider<TextTransformer>>
               |
        filter(p.type())
               |
               v
        Selected Provider
               |
             p.get()
               |
               v
       TextTransformer instance
               |
          transform(text)
~~~

**Distinguishing the two traversal styles:**

~~~java
// Illustrative snippet: operates on instances, each element created when reached.
for (TextTransformer service : ServiceLoader.load(TextTransformer.class)) {
    // Instance is already available to invoke business logic.
}

// Illustrative snippet: operates on provider descriptors first.
ServiceLoader.load(TextTransformer.class)
        .stream()
        .filter(p -> p.type().getSimpleName().contains("Upper"))
        .map(ServiceLoader.Provider::get)
        .forEach(service -> System.out.println(service.transform("java")));
~~~

In the second pipeline, **map(Provider::get)** is placed **after filter**, so only providers that pass the filter are asked to create an instance. Note: even without creating instances, discovery, class loading, reading metadata, and class linking can still incur cost or errors; "lazy" does not mean "doing no work at all".

## 3. What Exactly Is Laziness Here?

**ServiceLoader** discovers providers **on demand**. Calling **stream()** only creates a stream; when a **terminal operation** such as **findFirst()**, **toList()**, **forEach()**, or **collect()** runs, ServiceLoader proceeds to discover/load the providers the pipeline needs.

- **filter(p -> ...)** is an intermediate operation: the filter statement alone does not process any provider yet.
- **findFirst()** can stop once a matching provider is found, so it typically does not need to traverse every provider.
- **toList()** traverses all input elements; it stores Provider objects in a list and **does not automatically call get()**.
- **sorted(...)** usually must inspect every provider in order to sort, which can negate the early-exit benefit of findFirst; however, sorting by **p.type()** still does not create service instances by itself.
- Only when **get()** is called does ServiceLoader request the service object (via the corresponding constructor or factory method).

Example:

~~~java
// Illustrative snippet: reads class names of all providers, without calling get().
List<String> providerNames = ServiceLoader.load(TextTransformer.class)
        .stream()
        .map(p -> p.type().getName())
        .sorted()
        .toList();

// Illustrative snippet: creates/obtains an instance only for the chosen provider.
TextTransformer chosen = ServiceLoader.load(TextTransformer.class)
        .stream()
        .filter(p -> p.type().getSimpleName().equals("UppercaseTransformer"))
        .findFirst()
        .orElseThrow()
        .get();
~~~

**Important:** Using only **type()** avoids **instantiating the service object**, but does not guarantee no class loading, no service configuration checks, no annotation reading, or no ServiceConfigurationError. In some environments with custom classloaders, those steps still take time.

## 4. Runnable Java 17 Example: Selecting a Provider by Annotation

The following example runs on the **classpath**, has two valid providers, yet only instantiates the selected provider. We place the **@PluginKind** annotation on the provider classes. When inspecting **Provider.type()**, the host reads the annotation, selects **upper**, and only then calls **Provider.get()**.

Directory structure:

~~~text
provider-demo/
├── src/
│   └── demo/
│       ├── spi/
│       │   ├── TextTransformer.java
│       │   └── PluginKind.java
│       ├── plugins/
│       │   ├── UppercaseTransformer.java
│       │   └── ReverseTransformer.java
│       └── Demo.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.spi.TextTransformer
~~~

**File src/demo/spi/TextTransformer.java** — service contract:

~~~java
package demo.spi;

public interface TextTransformer {
    String transform(String text);
}
~~~

**File src/demo/spi/PluginKind.java** — metadata annotation retained at runtime:

~~~java
package demo.spi;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface PluginKind {
    String value();
}
~~~

Without **RetentionPolicy.RUNTIME**, calling **Class.getAnnotation(PluginKind.class)** cannot read the annotation via reflection at runtime; in that case an annotation-based filter will find no provider.

**File src/demo/plugins/UppercaseTransformer.java** — target provider:

~~~java
package demo.plugins;

import demo.spi.PluginKind;
import demo.spi.TextTransformer;
import java.util.Locale;

@PluginKind("upper")
public final class UppercaseTransformer implements TextTransformer {
    public UppercaseTransformer() {
        System.out.println("Construct: UppercaseTransformer");
    }

    @Override
    public String transform(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

**File src/demo/plugins/ReverseTransformer.java** — unselected provider:

~~~java
package demo.plugins;

import demo.spi.PluginKind;
import demo.spi.TextTransformer;

@PluginKind("reverse")
public final class ReverseTransformer implements TextTransformer {
    public ReverseTransformer() {
        System.out.println("Construct: ReverseTransformer");
    }

    @Override
    public String transform(String text) {
        return new StringBuilder(text).reverse().toString();
    }
}
~~~

**File resources/META-INF/services/demo.spi.TextTransformer** — service provider configuration file on the classpath:

~~~text
demo.plugins.ReverseTransformer
demo.plugins.UppercaseTransformer
~~~

The file name must match the **fully qualified binary name of the service**; its content lists provider class names, one per line, UTF-8 encoded. Both classes must be findable from the appropriate class loader, **public**, have a **public no-argument constructor**, and implement TextTransformer. This classpath configuration **does not use a static provider() factory method**; the static method mechanism applies to providers declared in **named modules** (explained in Section 6).

**File src/demo/Demo.java** — host inspects metadata and creates an instance only after selection:

~~~java
package demo;

import demo.spi.PluginKind;
import demo.spi.TextTransformer;
import java.util.List;
import java.util.ServiceLoader;
import java.util.ServiceLoader.Provider;
import java.util.stream.Collectors;

public final class Demo {
    public static void main(String[] args) {
        ServiceLoader<TextTransformer> loader =
                ServiceLoader.load(TextTransformer.class);

        // Discover all provider descriptors; do not invoke service constructors yet.
        List<Provider<TextTransformer>> providers = loader.stream().toList();

        System.out.println("Discovered: " + providers.size());
        String names = providers.stream()
                .map(p -> p.type().getSimpleName())
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println("Types: " + names);

        Provider<TextTransformer> chosen = providers.stream()
                .filter(p -> {
                    PluginKind kind =
                            p.type().getAnnotation(PluginKind.class);
                    return kind != null && "upper".equals(kind.value());
                })
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No upper provider"));

        System.out.println("Selected: " + chosen.type().getSimpleName());
        System.out.println("Before get");

        TextTransformer transformer = chosen.get();
        System.out.println("Result: " + transformer.transform("java"));
    }
}
~~~

**Compile and run from the provider-demo directory** with JDK 17 or later.

On macOS/Linux (bash):

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out \
  src/demo/spi/TextTransformer.java \
  src/demo/spi/PluginKind.java \
  src/demo/plugins/UppercaseTransformer.java \
  src/demo/plugins/ReverseTransformer.java \
  src/demo/Demo.java
cp -R resources/META-INF out/
java -cp out demo.Demo
~~~

On Windows (PowerShell):

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/spi/TextTransformer.java src/demo/spi/PluginKind.java src/demo/plugins/UppercaseTransformer.java src/demo/plugins/ReverseTransformer.java src/demo/Demo.java
Copy-Item -Recurse -Force resources/META-INF out/
java -cp out demo.Demo
~~~

**Stdout in an environment containing only the two example providers:**

~~~text
Discovered: 2
Types: ReverseTransformer, UppercaseTransformer
Selected: UppercaseTransformer
Before get
Construct: UppercaseTransformer
Result: JAVA
~~~

How to verify the mechanism yourself:

1. When printing the count, names, and types of providers, no **Construct:** line appears yet; the list holds Provider descriptors rather than two TextTransformer instances.
2. **type()** on each descriptor returns the corresponding class; the filter reads **@PluginKind("upper")** without needing to call the transform method.
3. Only after the **Before get** line does **Construct: UppercaseTransformer** appear, caused by **chosen.get()**.
4. There is no **Construct: ReverseTransformer** because the program never calls get() on the excluded provider.
5. The name list is **sorted()** so stdout does not depend on discovery order. In an environment with extra providers for the same service on the classpath, results may differ; in this isolated example there are exactly two.

**To observe a common mistake:** try moving **.map(Provider::get)** *before* the metadata filter. At that point the pipeline operates on **TextTransformer instances** instead of **Providers**, and filtering will require creating instances first. Therefore keep metadata filtering on Provider and only call **get() after selection**.

## 5. Ways to Select Providers Using type()

Not every selection requires annotations. If metadata is published at the class level, you can filter by:

### 5.1. Annotation on the Provider Class

~~~java
// Illustrative snippet: @Preferred requires @Retention(RUNTIME).
Provider<TextTransformer> p = loader.stream()
        .filter(d -> d.type().isAnnotationPresent(Preferred.class))
        .findFirst()
        .orElseThrow();
TextTransformer service = p.get();
~~~

Suitable when static metadata such as algorithm kind, version/capability, priority level, or experimental status is needed. Ensure annotations have stable semantics and avoid coupling the host to implementation packages where possible.

### 5.2. Class or Package Name

~~~java
// Illustrative snippet: using class names for inspection or diagnostics.
List<String> names = loader.stream()
        .map(d -> d.type().getName())
        .sorted()
        .toList();
~~~

Class names are useful for logs/diagnostics, but **are not durable business identifiers**. Refactoring, JAR shading, or swapping implementations can change class names even when functionality stays the same. If user configuration selects by ID, prefer an ID with a public contract instead of matching concrete class names.

### 5.3. Type Conditions

~~~java
// Illustrative snippet: MarkerCapability is another interface.
List<Provider<TextTransformer>> advanced = loader.stream()
        .filter(d -> MarkerCapability.class.isAssignableFrom(d.type()))
        .toList();
~~~

Use when the contract allows providers to implement an additional capability/marker interface; avoid abusing downcasts to call methods that only exist on an implementation. If the host needs extra business operations, model them explicitly with a capability interface or extension API.

### 5.4. Metadata Available Only on an Instance

If selection requires calling **service.supports(format)**, reading dynamic configuration, or checking a connection, **type() cannot provide** that information. In that case you must instantiate the necessary objects or design the service as a **factory/descriptor service** with an explicit metadata API, so a lightweight provider object itself can decide whether to create the heavyweight business object.

**Design boundary:** type() gives **class** information, get() gives an **instance**. Neither infer all dynamic capabilities from Class, nor attempt to invoke constructors via reflection from **type()**.

## 6. Important Differences Between Classpath and Named Modules

This section is especially important to remember when using **Provider.type()** for annotation filtering.

### 6.1. Providers Registered via META-INF/services on the Classpath

In the runnable example above, the provider class **directly implements TextTransformer**, and ServiceLoader creates the object using the **public no-arg constructor**.

- **Provider.type()** is typically the implementation class registered in the configuration file.
- Reading annotations placed on that class via reflection can be used for selection.
- **Provider.get()** performs instantiation via the constructor managed by ServiceLoader.
- The service configuration file and provider class must be present on the classpath/class loader used by the host.

### 6.2. Providers Declared with provides ... with ... in module-info.java

In a named module, a provider can be instantiated in **two ways**:

1. **Provider constructor:** the class implements the service and has a public no-arg constructor.
2. **Provider method:** the provider class declares a no-arg **public static provider()** method returning a type assignable to the service. The provider class itself might **not implement the service**.

Module declaration example (illustrative snippets, not part of the runnable classpath program in Section 4):

~~~java
// module-info.java of the module providing the service API
module text.spi {
    exports demo.spi;
}
~~~

~~~java
// module-info.java of the implementation module
module text.plugins {
    requires text.spi;
    provides demo.spi.TextTransformer
        with demo.plugins.UppercaseTransformer;
}
~~~

~~~java
// module-info.java of the host module
module text.app {
    requires text.spi;
    uses demo.spi.TextTransformer;
}
~~~

Providers are declared in named modules with **provides**. The host declares **uses**. Module declarations do not mean the host needs to directly **requires** the implementation module; providers should be replaceable without forcing the host to depend on implementation modules. In module-path deployments, ensure provider modules are resolved into the appropriate module graph or layer.

**Provider factory method case:**

~~~java
// Illustrative snippet for a named module, not a classpath provider.
package demo.plugins;

import demo.spi.TextTransformer;

public final class TransformerSupplier {
    public static TextTransformer provider() {
        return new UppercaseTransformer();
    }
}
~~~

With configuration **provides demo.spi.TextTransformer with demo.plugins.TransformerSupplier**, ServiceLoader calls the **provider()** method to obtain an instance; the factory class does not need to implement TextTransformer.

**Common pitfall:** in the provider factory method case, **Provider.type() returns the declared return type of the public static provider() method**, *not necessarily TransformerSupplier.class or the concrete runtime class of the returned object*. If the return signature is **TextTransformer**, type() may just be **TextTransformer.class**. Consequently, filters relying on annotations placed on the actual implementation class will **no longer work as in the classpath example**.

To select by metadata across both mechanisms, consider using a **service contract for a descriptor/factory** with explicitly published capability info, or a host-managed metadata registry. Do not rely on assuming **type() always gives the class of the final object**. The API docs also do not guarantee type() is public/accessible or has a public no-arg constructor; use **get()** to obtain the service, do not call **newInstance()** yourself from type().

### 6.3. Do Not Confuse type() with getClass()

| Expression | What it describes | When to use |
|---|---|---|
| **descriptor.type()** | Provider type exposed by ServiceLoader, which may be the return type of provider() | Select/filter by metadata before instantiation |
| **descriptor.get().getClass()** | Runtime class of the obtained instance | When you actually need to inspect the object after instantiation |
| **descriptor.type().getDeclaredConstructor().newInstance()** | Manually attempting instantiation via reflection | **Do not use**: bypasses provider() rules and encapsulation, and may fail |

With named modules, the provider's package is usually **not exported** to the host to preserve encapsulation. ServiceLoader can instantiate it through the specified mechanism, whereas host code has no permission to directly construct objects from the provider class.

## 7. Streams, Selecting a Single Provider, and Avoiding Extra Instantiation

A good pipeline places operations in order:

~~~java
// Illustrative snippet using @PluginKind and TextTransformer from the example.
TextTransformer selected = ServiceLoader.load(TextTransformer.class)
        .stream()
        .filter(p -> {
            PluginKind kind = p.type().getAnnotation(PluginKind.class);
            return kind != null && "upper".equals(kind.value());
        })
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("Provider not found"))
        .get();
~~~

Compare against an error-prone structure:

~~~java
// Illustrative snippet: get() before filter may instantiate every
// traversed provider, even though only one is finally selected.
TextTransformer eager = ServiceLoader.load(TextTransformer.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(s -> s.getClass().getSimpleName().contains("Upper"))
        .findFirst()
        .orElseThrow();
~~~

In the eager example, the Stream only creates instances *as elements are traversed*, not all at once when map is called; however, every element traversed to check the predicate must go through **get()**, including elements that are not selected. If you need to locate a provider by a fixed kind, filtering metadata before get() saves significant instantiation.

Notes on other options:

- **findFirst()** depends on provider discovery order. In named modules, order across certain modules/layers is not guaranteed; do not rely on "first provider" to decide business priority.
- If multiple providers match, use an explicit selection criterion such as ID, version/capability, or explicit priority, and define how duplicate IDs/ties are resolved.
- **sorted(Comparator.comparing(p -> p.type().getName()))** creates a deterministic diagnostic order by class name but may have to traverse every provider; that is still different from instantiating all of them.
- When you need to instantiate multiple selected providers, use **filter(...).map(Provider::get)**; when you only need one, **filter(...).findFirst().orElseThrow().get()** expresses the intent more clearly.
- A **Stream** can only be consumed once. To perform two separate traversals, create a new stream or store the **Provider** descriptors in a collection as shown in the example.

## 8. Caching, Reloading, and Instance Lifecycle

**ServiceLoader** manages locating/remembering already-loaded providers on demand. However, three concepts must be separated:

1. **ServiceLoader's cache:** lets subsequent traversals handle previously loaded providers according to ServiceLoader's rules.
2. **Provider descriptor:** describes the ability to create/obtain a service instance; it is not the service instance itself.
3. **Instance lifecycle:** ServiceLoader.Provider.get() only promises to return a valid instance. Do not infer that every call to get() always returns the same singleton, nor infer that every provider always creates a new object.

If you need singleton, per-request, per-session, or pooled semantics, the **service/provider contract itself** must specify it. In particular, a named module's provider method may return a cached object under its own policy; host code should not depend on how many times a constructor runs in environments different from the example.

**reload()** clears ServiceLoader's provider cache so lookup/loading can run again against whatever configuration is visible at that time. After calling **reload()**, you must **discard previously created streams/iterators and create new ones**, because their backing source may throw **ConcurrentModificationException**. Reload **does not automatically unload classes**, does not close old instances, and does not guarantee loading a replaced JAR version if the classloader/module layer has not changed.

If plugins hold resources, the host needs its own stop/close policy. ServiceLoader is not a replacement for a lifecycle manager.

## 9. Errors, Class Loaders, and Safety

### 9.1. ServiceConfigurationError Can Occur Before and After get()

**ServiceConfigurationError** can happen when:

- The META-INF/services file is malformed, or the declared class does not exist, is not visible, or does not implement the service.
- A named module declares a provider violating constructor/provider method rules.
- When **get()** invokes the constructor or static provider() and the method throws an exception or provider() returns null.
- Service discovery/loading encounters environment/module/classloader errors.

With streams, a terminal operation can fail **right during the discovery/type() phase**, even before calling get(). Thus the belief that "only get() can fail" is wrong.

**ServiceConfigurationError extends Error.** It is usually best to handle it at the **plugin loading boundary** to report the exact service, provider, and broken configuration; avoid swallowing the error and silently treating it as zero providers. There is no guarantee that skipping one failing provider lets you reliably continue traversing all remaining providers.

~~~java
// Illustrative snippet at the plugin loading boundary.
try {
    ServiceLoader.load(TextTransformer.class)
            .stream()
            .forEach(p -> System.out.println(p.type().getName()));
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException("Invalid TextTransformer provider setup", error);
}
~~~

### 9.2. Choosing the Right Class Loader or Module Layer

- **ServiceLoader.load(ServiceType.class)** uses the **thread context class loader**.
- **ServiceLoader.load(ServiceType.class, someClassLoader)** uses the specified class loader as the starting point for locating providers.
- **ServiceLoader.load(moduleLayer, ServiceType.class)** searches providers in the specified layer and its parent layers according to the API rules.

If the API finds **0 providers** even though the configuration file exists, check the service name, classpath/module path, context classloader, resource visibility, **uses/provides**, and module resolution. In a plugin host running multiple independent applications/modules, do not cache a single JVM-wide ServiceLoader when context classloaders can differ.

**A ServiceLoader instance is not thread-safe.** Do not let multiple threads operate on the same ServiceLoader without coordination. Also do not use **parallel()** on the loader's stream as a default speedup; ordering, caching, and provider configuration must be handled safely per contract.

### 9.3. Do Not Treat "Type-Only Inspection" as a Sandbox

Not creating service instances before selection reduces side effects of **constructor/provider()**, yet loading classes and reading metadata still involve external code and dependencies. Once **get()** is called, provider code executes inside the host process. **ServiceLoader does not provide security isolation**, timeouts, resource quotas, or automatic rollback for faulty plugins. If you need to run untrusted plugins, design appropriate isolation/monitoring outside ServiceLoader.

## 10. When Should Selection Use type() vs. get()?

| Need | Recommended Approach | Reason |
|---|---|---|
| List declared provider names for display/logging | **stream().map(p -> p.type().getName())** | Service instance not needed yet |
| Select provider by RUNTIME annotation on provider type | **stream().filter(p -> p.type().getAnnotation(...))** | Filter first, get later |
| Select one provider by metadata-level ID | **stream + metadata/registry + findFirst + get** | Does not instantiate unselected providers |
| Select by dynamic capability, e.g. supports(input) on service | May need **get()** then check capability; or design a descriptor/factory service | type() does not represent runtime state |
| Run all discovered providers | **loader.iterator()** or **stream().map(Provider::get)** | Each provider needs an instance to execute |
| Named module with static provider() returning shared interface | Avoid inferring implementation class from **type()** | type() returns the declared return type of provider() |
| Need to open/close plugins, manage scope, or unload | Add a lifecycle manager/registry/classloader policy | ServiceLoader only handles discovery and obtaining providers |

## 11. Self-Check Questions

**Question 1.** Does the following statement create all service instances?

~~~java
List<Class<? extends TextTransformer>> types =
        ServiceLoader.load(TextTransformer.class)
                .stream()
                .map(ServiceLoader.Provider::type)
                .toList();
~~~

**Answer:** It does not actively request creating service instances. It traverses and reads the types of providers, may load/verify classes and throw configuration errors, but does not call Provider.get().

**Question 2.** Why can filtering with **p.type().isAnnotationPresent(...)** fail when a named module uses **public static provider()**?

**Answer:** type() returns the **declared return type** of provider(), which might just be the service interface or another general type. Annotations placed on the factory class or the runtime class returned by the factory do not necessarily appear on that type.

**Question 3.** Does using **findFirst().get().transform(...)** mean the provider is always a singleton?

**Answer:** No. Here **get()** is the call on Provider to obtain a service instance. Singleton vs. multiple-instance semantics belong to the provider's policy; do not assume from the snippet alone.

**Question 4.** Does calling **reload()** make a previously created stream automatically refresh its provider list?

**Answer:** No. Old streams/iterators must be discarded; they may throw **ConcurrentModificationException** after the cache is cleared. Create a new stream from ServiceLoader after reload and manage the lifecycle of old instances yourself.

**Question 5.** In the complete example, why did ReverseTransformer not print a Construct line?

**Answer:** The program only traversed **Provider descriptors** for both classes and read their annotations; only **chosen.get()** on UppercaseTransformer created a service instance. There was no get() call for ReverseTransformer.

## 12. Practical Implementation Checklist

When designing an extension point with multiple providers, verify:

1. **Service contract** is small and clear; methods, exceptions, concurrency, and lifecycle are explicitly specified.
2. **Registration** is accurate: service file name and provider class on the classpath, or **uses/provides** and module resolution for named modules.
3. **Metadata used for selection** is actually available via **type()** under the provider mechanism in use; **RUNTIME** retention is present if filtering via reflection.
4. **Pipeline** places metadata filtering/sorting before **Provider.get()** and instantiates only after deciding.
5. **Do not rely on arbitrary provider order** for priority policies; handle missing providers, duplicate IDs, and configuration errors explicitly.
6. **Do not instantiate manually from type()**: use **get()** so ServiceLoader applies the proper constructor/provider-method rules and module encapsulation.
7. **Do not share ServiceLoader concurrently**; after **reload()**, create a new stream/iterator and properly manage old instances' lifecycles.
8. **Minimal tests:** two providers with only one selected, excluded provider's constructor never runs, missing provider produces an appropriate error, and ServiceConfigurationError and named-module factory method cases are explained/tested separately.

**Key takeaway:** **stream()** yields descriptors, **Provider.type()** lets you inspect/filter type information before instantiation, and **Provider.get()** is when the host requests a service instance. Designing selection policies around metadata takes full advantage of this separation, while always accounting for the differences between classpath providers and named-module provider factories.

### Standard References

- Oracle Java SE 17 API — **java.util.ServiceLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17 API — **java.util.ServiceLoader.Provider**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
