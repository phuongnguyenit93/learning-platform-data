# Provider Discovery and Lazy Instantiation with ServiceLoader in Java

## 1. What Is a Service Provider and Why Is Dynamic Discovery Needed?

In Java, a **service** is typically a public interface or abstract class describing a contract that an application needs; a **service provider** is an implementation that can be installed and discovered at runtime. Consuming code depends only on the **service contract**, not on the concrete implementation class name.

For example, an application supports multiple decoders:

```java
package example.spi;

public interface Codec {
    String decode(byte[] input);
}
```

This is an **illustrative interface file**, not a standalone example program. Providers A and B can implement this interface and register via metadata or `module-info.java`. The application uses `ServiceLoader<Codec>` to discover the available providers.

`java.util.ServiceLoader<S>` is the standard API for **service-provider loading (SPI)**, not a general-purpose dependency injection container. It can locate implementations from:
- **Classpath/unnamed modules**: the metadata file `META-INF/services/<binary-service-name>`.
- **Named modules (JPMS)**: a `provides ... with ...` declaration in the module descriptor; the consumer declares `uses ...`.
- **ModuleLayer** created dynamically: an overload is provided to find providers in the layer and its parent layers.

The key point of this topic is that **provider discovery** and **lazy instantiation** are **two operations that can occur at different times**.

## 2. What Does “Lazy” Actually Mean?

The statement:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);
```

**does not mean** Java immediately finishes reading every service descriptor, loads every provider class, and invokes the constructors of all providers. Instead, `ServiceLoader` provides an **on-demand** lookup mechanism:

1. Creates a `ServiceLoader` object for a service type and a class loader/layer context.
2. When iteration begins, finds matching provider declarations from module descriptors or `META-INF/services`.
3. Loads and verifies the provider type when needed.
4. **Instantiates the provider** when the consumer needs a provider instance (for example, `Iterator.next()`, `findFirst()`, or `Provider.get()`).
5. Caches the discovered/loaded/instantiated providers according to the traversal method's semantics, so that subsequent traversals can reuse them.
6. `reload()` clears the cache of that `ServiceLoader` object itself; providers will be rediscovered/reloaded/re-instantiated on the next traversal, but already-defined classes and static initializers that have run successfully **are not automatically reset**.

Diagram:

```text
ServiceLoader.load(Service.class)
             │
             ▼
       ServiceLoader object
             │
             ├── iterator()
             │      ├── hasNext() → discovers name/provider when needed
             │      └── next()    → gets/creates provider instance
             │
             ├── findFirst()      → gets/creates first provider if present
             │
             └── stream()
                    └── Provider<S>
                          ├── type() → Class<?> of provider type
                          └── get()  → provider instance
             │
             ▼
          Provider is used
```

**Note:** lookup methods (`hasNext()`/stream traversal) **can perform I/O, search for configuration files, load classes, and raise errors**. “Lazy” does not mean they are always free. What is deferred is **on-demand discovery and instantiation**, instead of creating every provider immediately upon calling `ServiceLoader.load`.

## 3. Two Concepts to Separate: Loading and Initialization

In the JVM:
- **Loading**: The ClassLoader/JVM finds and defines the runtime class.
- **Linking**: JVM verification, preparation, and resolution according to the rules.
- **Initialization**: The JVM executes static field initialization expressions and `static { ... }` blocks upon an appropriate active use.
- **Instantiation**: Creates an **object instance**, running the constructor and related initializers.

A provider class can be **loaded without being initialized**. When `ServiceLoader.Provider.type()` returns `Class<?>`, obtaining the provider type normally does not require creating an instance. Conversely, when `Provider.get()` creates an object via a constructor or a provider factory method, the class is initialized according to Java rules if it has not been initialized yet.

Example:

```java
// Excerpt: providerClass already exists in the selected loader.
Class<?> providerClass =
        Class.forName("demo.impl.Alpha", false, providerLoader);
// Does not actively request running Alpha.<clinit> yet.

Object provider = providerClass.getDeclaredConstructor().newInstance();
// Can force Alpha initialization and run the constructor.
```

This snippet is a reflection excerpt, **not a complete replacement process for ServiceLoader**. ServiceLoader also checks the service contract, metadata, module rules, and the provider constructor/factory.

**Do not equate** “the provider has been discovered” with “the provider instance has been created”, and likewise do not equate “the ServiceLoader object has been created” with “a provider has been found”.

## 4. Core APIs of ServiceLoader

| API | Result | Laziness Level to Remember |
|---|---|---|
| `ServiceLoader.load(S.class)` | Creates a service loader using the current **TCCL** | Does not instantiate all providers yet |
| `ServiceLoader.load(S.class, loader)` | Uses an explicit `ClassLoader` | Also discovers on demand |
| `ServiceLoader.load(layer, S.class)` | Finds providers from `ModuleLayer` and its parent layers | Does not find providers from unnamed modules with this overload |
| `serviceLoader.iterator()` | `Iterator<S>` | `hasNext` may discover; `next` gets/creates an instance |
| `serviceLoader.findFirst()` | `Optional<S>` | Equivalent to taking the first provider from the iterator |
| `serviceLoader.stream()` | `Stream<ServiceLoader.Provider<S>>` | Inspects provider descriptions/type before creating an instance |
| `provider.type()` | `Class<? extends S>` | Inspects the type without instantiating the provider |
| `provider.get()` | `S` | Gets or creates an instance according to the provider contract |
| `serviceLoader.reload()` | `void` | Clears the providers cache of the ServiceLoader itself |

The `load` overloads **do not have the same lookup context**. For plugin applications, choosing the right loader or layer is just as important as choosing the service interface.

## 5. Complete Java 17+ Example: Classpath Providers and Lazy Instantiation

We will create a service interface `demo.spi.Greeting`, two provider classes, and a host. Each provider contains a static initializer and a constructor that print to the console, so we can clearly see **when** Java actually creates an instance.

### 5.1. Directory Structure

```text
spi-demo/
├── src/
│   ├── demo/
│   │   ├── spi/Greeting.java
│   │   ├── impl/AlphaGreeting.java
│   │   ├── impl/BetaGreeting.java
│   │   └── app/Host.java
│   └── META-INF/
│       └── services/
│           └── demo.spi.Greeting
└── out/
    ├── demo/...
    └── META-INF/services/demo.spi.Greeting
```

### 5.2. Service contract: src/demo/spi/Greeting.java

```java
package demo.spi;

public interface Greeting {
    String message();
}
```

### 5.3. Provider A: src/demo/impl/AlphaGreeting.java

```java
package demo.impl;

import demo.spi.Greeting;

public final class AlphaGreeting implements Greeting {
    static {
        System.out.println("Alpha initialized");
    }

    public AlphaGreeting() {
        System.out.println("Alpha constructed");
    }

    @Override
    public String message() {
        return "alpha";
    }
}
```

### 5.4. Provider B: src/demo/impl/BetaGreeting.java

```java
package demo.impl;

import demo.spi.Greeting;

public final class BetaGreeting implements Greeting {
    static {
        System.out.println("Beta initialized");
    }

    public BetaGreeting() {
        System.out.println("Beta constructed");
    }

    @Override
    public String message() {
        return "beta";
    }
}
```

### 5.5. Provider configuration file

Create the file at the exact path:

```text
src/META-INF/services/demo.spi.Greeting
```

Contents with **two lines in order**:

```text
demo.impl.AlphaGreeting
demo.impl.BetaGreeting
```

The **file** name must match the **binary name** of the service type, not the provider name; the contents contain the binary names of the implementations. Do not append `.class` to the metadata file name.

### 5.6. Host: src/demo/app/Host.java

```java
package demo.app;

import demo.spi.Greeting;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Host {
    private static void iteratorDemo() {
        ServiceLoader<Greeting> services =
                ServiceLoader.load(
                        Greeting.class,
                        Host.class.getClassLoader()
                );

        System.out.println("loader created");
        Iterator<Greeting> items = services.iterator();
        System.out.println("iterator created");

        System.out.println("has first: " + items.hasNext());
        System.out.println("before first next");
        Greeting first = items.next();
        System.out.println("first message: " + first.message());

        System.out.println("has second: " + items.hasNext());
        System.out.println("before second next");
        Greeting second = items.next();
        System.out.println("second message: " + second.message());

        Greeting cached = services.iterator().next();
        System.out.println("first cached object: " + (cached == first));

        services.reload();
        System.out.println("after reload");
        Greeting recreated = services.iterator().next();
        System.out.println("new first instance: " + (recreated != first));
    }

    private static void streamDemo() {
        ServiceLoader<Greeting> services =
                ServiceLoader.load(
                        Greeting.class,
                        Host.class.getClassLoader()
                );

        System.out.println("loader created");
        ServiceLoader.Provider<Greeting> provider =
                services.stream().findFirst().orElseThrow();

        System.out.println("provider type: "
                + provider.type().getName());
        System.out.println("before provider get");

        Greeting instance = provider.get();
        System.out.println("message: " + instance.message());
    }

    public static void main(String[] args) {
        if (args.length == 1 && "stream".equals(args[0])) {
            streamDemo();
        } else {
            iteratorDemo();
        }
    }
}
```

The program has two modes run in **two separate JVM processes** so that Alpha's static initializer has not already been called by the other mode. Both modes use the same interface, implementations, and metadata.

### 5.7. Compiling and Preparing Resources

In the `spi-demo` directory, use JDK 17+.

On Bash:

```bash
mkdir -p out/META-INF/services
javac --release 17 -d out src/demo/spi/Greeting.java src/demo/impl/AlphaGreeting.java src/demo/impl/BetaGreeting.java src/demo/app/Host.java
cp src/META-INF/services/demo.spi.Greeting out/META-INF/services/demo.spi.Greeting
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac --release 17 -d out src/demo/spi/Greeting.java src/demo/impl/AlphaGreeting.java src/demo/impl/BetaGreeting.java src/demo/app/Host.java
Copy-Item src/META-INF/services/demo.spi.Greeting out/META-INF/services/demo.spi.Greeting
```

The provider configuration file **is not automatically compiled/copied by javac**; you must copy the resource or use a build tool (Maven/Gradle) to include it in the final artifact.

The result should contain:

```text
out/
├── demo/
│   ├── spi/Greeting.class
│   ├── impl/AlphaGreeting.class
│   ├── impl/BetaGreeting.class
│   └── app/Host.class
└── META-INF/services/demo.spi.Greeting
```

### 5.8. Running Iterator Mode

```bash
java -cp out demo.app.Host
```

Stdout:

```text
loader created
iterator created
has first: true
before first next
Alpha initialized
Alpha constructed
first message: alpha
has second: true
before second next
Beta initialized
Beta constructed
second message: beta
first cached object: true
after reload
Alpha constructed
new first instance: true
```

Explanation:

1. `load(Greeting.class, loader)` creates the service loader object: nothing is printed from Alpha/Beta yet.
2. `iterator()` creates the iterator; `hasNext()` locates the metadata and reports that there is a first provider, without calling Alpha's constructor yet.
3. `next()` obtains the first instance, so Alpha's static initializer runs for the first time, then Alpha's constructor runs, and then `message()` returns `alpha`.
4. Provider B has not been initialized yet at the time Alpha is used. Only when `next()` is called the second time is Beta instantiated.
5. A new iterator from the **same ServiceLoader** returns the cached provider objects before looking up any remaining providers. Therefore `cached == first` prints `true`.
6. `reload()` clears the provider cache. The next traversal creates a **new Alpha instance**, but **does not re-run** `Alpha.<clinit>`: successful static initialization happens once for the same runtime class.
7. `reload()` does not redefine Alpha with a new ClassLoader, does not change its binary name or bytecode, and does not automatically “hot reload” an overwritten JAR.

### 5.9. Running Stream Mode in a Separate JVM

```bash
java -cp out demo.app.Host stream
```

Stdout:

```text
loader created
provider type: demo.impl.AlphaGreeting
before provider get
Alpha initialized
Alpha constructed
message: alpha
```

`stream().findFirst()` returns a `Provider<Greeting>` descriptor. `provider.type()` reveals the provider class **without creating an instance**, so Alpha's static initializer has not run at this step. `provider.get()` is what obtains the provider instance, triggering initialization and the constructor if this is the first time.

**Do not infer** that `ServiceLoader.Provider.get()` always memoizes a specific object across multiple calls. Do not use `get() == get()` as a singleton contract. When sharing an instance according to a lifecycle is needed, the application should manage it, or use an explicitly designed provider factory/lifecycle.

## 6. Metadata Lookup Mechanism on the Classpath

When using provider configuration in an unnamed module/classpath, `ServiceLoader` searches for resources at the path:

```text
META-INF/services/<binary-name-of-service>
```

For the example above:

```text
META-INF/services/demo.spi.Greeting
```

Provider configuration files have important rules:

- Must be **UTF-8** encoded.
- Each valid line contains the **full binary name** of a provider class.
- Blank lines and whitespace/tabs surrounding the name are ignored.
- The `#` character starts a comment; the remainder of the line after `#` is ignored.
- A provider class name repeated in one or more configuration files will be ignored on duplicate occurrences when processed by the loader according to the contract.
- A provider can reside in a different JAR from the service configuration file, as long as the classloader being used **sees** the implementation.
- The order of providers within **a single configuration file** affects traversal order; with multiple resources, the order depends on `ClassLoader.getResources` and the rules for coordinating provider modules. You should not treat “first provider” as a stable global order in complex deployments.

Example of valid metadata:

```text
# Providers for Greeting
demo.impl.AlphaGreeting    # prioritized according to this file

demo.impl.BetaGreeting
```

### Wrong Location and Wrong Name

The following structures **are not equivalent**:

```text
META-INF/services/demo.spi.Greeting      [correct service name]
META-INF/services/demo.impl.AlphaGreeting [wrong: provider name]
META-INF/service/demo.spi.Greeting       [wrong directory]
META-INF/services/demo.spi.Greeting.txt  [wrong: extra extension]
```

If metadata is missing or located at the wrong path, `ServiceLoader` may fail to see the provider even if `AlphaGreeting.class` is on the classpath. Conversely, metadata containing a nonexistent, non-assignable provider name, or one without a suitable constructor, can cause a `ServiceConfigurationError` during traversal.

## 7. When Is a Provider Loaded, Linked, Initialized, and Instantiated?

For a constructor-based classpath provider, events can occur as follows:

```text
ServiceLoader.load(S.class, loader)
         │
         └── yields ServiceLoader object

iterator.hasNext() / stream operation
         │
         ├── searches for provider configuration
         ├── parses provider names
         └── may load/verify provider classes
                    │
                    ▼
iterator.next() / findFirst() / Provider.get()
         │
         ├── ensures provider is ready to create
         ├── initialization of provider class if needed
         ├── invokes public no-arg constructor
         └── returns object S
```

This is a **conceptual diagram**, not a guarantee that `hasNext` strictly avoids all class loading; different implementations/JVMs may link types at different times.

When testing, distinguish **signals from the static initializer** and **the constructor**:

```java
static {
    System.out.println("Provider class initialized");
}

public ExampleProvider() {
    System.out.println("Provider object constructed");
}
```

This is an **in-class snippet**, not a standalone file. A static initializer normally runs once for **each runtime class** upon successful initialization. The constructor may run multiple times if the application creates multiple provider instances, including after `ServiceLoader.reload()` or with different ServiceLoader objects.

If the constructor throws an exception, `ServiceLoader` typically reports the error as a `ServiceConfigurationError` when the consumer actually traverses/instantiates the provider.

## 8. Iterator, findFirst, and stream: Choosing the Right API

### 8.1. iterator() When You Want Instances

```java
ServiceLoader<Greeting> services = ServiceLoader.load(Greeting.class);
for (Greeting greeting : services) {
    System.out.println(greeting.message());
}
```

This is an **excerpt**, assuming `Greeting` is available and `ServiceLoader` has been imported. The enhanced for-loop uses `iterator()`, so it may instantiate providers during traversal.

Note that **traversal does not require locating every provider immediately**: if the loop executes `break` after the first provider, subsequent providers may not be instantiated yet.

### 8.2. findFirst() When You Only Need One

```java
Greeting selected = ServiceLoader
        .load(Greeting.class)
        .findFirst()
        .orElseThrow();
```

This is an excerpt. `findFirst()` uses lazy iteration to obtain the first provider if present; it does not need to instantiate all providers. If there is no provider, the `Optional` is empty. If metadata/provider is broken, it is **not** guaranteed to return `Optional.empty()`: it can still throw `ServiceConfigurationError`.

**Provider order** is part of the contract and the deployment environment. Do not use `findFirst()` to enforce business priority ordering in a system with multiple JARs/modules without explicitly defining the order.

### 8.3. stream() When Selecting by Provider Type Metadata

```java
ServiceLoader<Greeting> services = ServiceLoader.load(Greeting.class);
ServiceLoader.Provider<Greeting> selected = services.stream()
        .filter(p -> p.type().getSimpleName().startsWith("Alpha"))
        .findFirst()
        .orElseThrow();

Greeting instance = selected.get();
```

This is an excerpt. `Provider.type()` allows inspecting the provider type **before** instantiation. This is useful if you need to select a provider by annotation/class metadata or by class name, avoiding instantiating expensive candidates.

However:
- The provider type may still have to be **loaded/verified**.
- Reading annotations via reflection has its own overhead and constraints.
- `type()` does not necessarily return a class with a public no-arg constructor.
- For a **named-module provider factory method**, `type()` returns the **return type of provider()**, not necessarily the factory class declared in `provides`.

**Important note:** Traversing `stream()` and calling `Provider.get()` should not be assumed to have the same instance-caching behavior as `iterator()`. Explicitly design where the provider object is owned.

## 9. ServiceLoader Cache and the Meaning of reload()

`ServiceLoader` maintains a cache of providers already loaded during traversal. With `iterator()`, subsequent traversals of the **same object** first return the **cached instances** in instantiation order, and then continue discovering any remaining providers.

`reload()`:
- Clears the cache of the `ServiceLoader` object, allowing subsequent traversals to rediscover provider declarations.
- Can create a **new instance** from the same provider class, if requested.
- Does not remove objects that still have references elsewhere.
- Does not “unload” the class from the JVM.
- Does not guarantee reloading class bytes previously defined by the defining loader.
- Does not automatically restore a stopped/resource-disposed provider back to an active state.

### After reload, Can the Old Iterator Still Be Used?

You should not continue using an iterator or stream obtained from `ServiceLoader` before calling `reload()`. With an iterator, `hasNext()` and `next()` may throw `ConcurrentModificationException` once the cache has been cleared. Create a **new iterator/stream** after reloading.

### Re-reading Modified Resources

If you modify the `META-INF/services` file in a source visible to the loader, `reload()` can cause ServiceLoader to attempt discovering the new list of providers. However, whether the updated file is reflected also depends on how the ClassLoader/resource cache behaves; if the loader is closed, or if the JAR remains in cache, simply calling `reload()` may not achieve hot deployment.

**To truly reload a new version of a class**, you generally need a new defining ClassLoader, managing plugin stop/start and existing references. `ServiceLoader.reload()` does not replace a hot-reload architecture.

## 10. Thread Context ClassLoader and Provider Visibility Scope

The overload:

```java
ServiceLoader.load(Greeting.class)
```

uses the **Thread Context ClassLoader (TCCL)** of the current thread according to the `ServiceLoader` contract. This is useful when the framework resides in a parent loader while the provider implementation exists only in a child plugin loader.

The explicit overload:

```java
ServiceLoader.load(Greeting.class, pluginLoader)
```

selects `pluginLoader` directly. This is an excerpt that requires a valid `pluginLoader` variable and service interface.

### Host/Plugin Model

```text
Application ClassLoader
   ├── service API: demo.spi.Greeting
   └── host framework
             │
             ▼ uses TCCL or explicit loader
Plugin URLClassLoader
   ├── demo.impl.AlphaGreeting
   └── META-INF/services/demo.spi.Greeting
```

If the framework queries only its own loader, it may **not see** providers in the child. Switching the TCCL for the proper scope or passing a specific loader enables provider discovery.

The TCCL is ambient state on a thread. When temporarily changing it, you must restore it:

```java
// Excerpt in host code:
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<Greeting> services =
            ServiceLoader.load(Greeting.class);
    services.findFirst().ifPresent(
            greeting -> System.out.println(greeting.message())
    );
} finally {
    thread.setContextClassLoader(previous);
}
```

**Do not** call `Class.forName("demo.impl.AlphaGreeting")` and expect it to automatically use the TCCL: the `Class.forName(String)` overload uses the caller's loader, not the TCCL.

### Inside a Thread Pool

A thread pool has **pre-created** workers. Changing the TCCL on the main thread when submitting a task does not guarantee that the worker uses the new TCCL. If a task needs a plugin's provider, pass the loader explicitly or use a set/restore wrapper directly inside the worker thread.

Do not leave a plugin TCCL stored on a thread pool after a request finishes: it can both cause the wrong provider to be resolved and hold a strong reference to the plugin ClassLoader, preventing unloading on redeploy.

## 11. JPMS: uses/provides in Named Modules

On the module path, a service provider is registered using `module-info.java` rather than needing `META-INF/services`.

Create the service contract:

```java
package svc.api;

public interface Greeting {
    String message();
}
```

API module:

```java
module svc.api {
    exports svc.api;
}
```

Consumer module:

```java
module svc.host {
    requires svc.api;
    uses svc.api.Greeting;
}
```

Provider module:

```java
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting
            with svc.provider.HelloGreeting;
}
```

With the descriptors above:
- `requires svc.api`: the consumer/provider reads the service contract.
- `uses svc.api.Greeting`: the consumer declares that it uses this service; this is an important requirement when the caller resides in an explicit named module.
- `provides ... with ...`: the provider module declares the implementation.
- The `svc.provider` package **does not need to be exported** merely for ServiceLoader to instantiate the provider according to module rules.

There is no need to force every implementation package into becoming public API of the provider module.

### Named-Module Provider Constructor vs. Factory Method

For an **explicit named module** with `provides`, a provider has two options:

1. The provider class has a **public no-arg constructor**, creating the object directly; the provider class must be assignable to the service.
2. The provider class has a parameterless **public static provider()** method, with a return type assignable to the service; ServiceLoader calls the factory method. In this case, the class containing the factory **does not necessarily implement the service**.

Example of a provider factory in a module:

```java
// Class excerpt in an explicit named provider module:
package svc.provider;

import svc.api.Greeting;

public final class GreetingFactory {
    public static Greeting provider() {
        return new HelloGreeting();
    }
}
```

This is an **excerpt with dependencies**, not a standalone program. A suitable descriptor can use `provides svc.api.Greeting with svc.provider.GreetingFactory;`. With a module factory, `Provider.type()` returns the **return type** of `provider()`, not necessarily the `GreetingFactory` class.

**Specifically:** providers listed in `META-INF/services` on the classpath, or providers of an **automatic module**, require a public no-arg constructor under their respective contracts; **a provider factory method is not supported for these forms as it is for explicit named module provides**.

## 12. Complete JPMS Example: Lazy Provider from a Module Descriptor

The next example provides a module-path demonstration that runs independently of the classpath example.

### 12.1. Structure

```text
mod-spi/
└── src/
    ├── svc.api/
    │   ├── module-info.java
    │   └── svc/api/Greeting.java
    ├── svc.provider/
    │   ├── module-info.java
    │   └── svc/provider/HelloGreeting.java
    └── svc.host/
        ├── module-info.java
        └── svc/host/Main.java
```

Create the exact files:

`src/svc.api/module-info.java`

```java
module svc.api {
    exports svc.api;
}
```

`src/svc.api/svc/api/Greeting.java`

```java
package svc.api;

public interface Greeting {
    String message();
}
```

`src/svc.provider/module-info.java`

```java
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting with svc.provider.HelloGreeting;
}
```

`src/svc.provider/svc/provider/HelloGreeting.java`

```java
package svc.provider;

import svc.api.Greeting;

public final class HelloGreeting implements Greeting {
    static {
        System.out.println("Module provider initialized");
    }

    public HelloGreeting() {
        System.out.println("Module provider constructed");
    }

    @Override
    public String message() {
        return "hello JPMS";
    }
}
```

`src/svc.host/module-info.java`

```java
module svc.host {
    requires svc.api;
    uses svc.api.Greeting;
}
```

`src/svc.host/svc/host/Main.java`

```java
package svc.host;

import svc.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeting> services =
                ServiceLoader.load(Greeting.class);

        System.out.println("ServiceLoader created");
        Greeting provider = services.findFirst().orElseThrow();
        System.out.println("Provider message: " + provider.message());
    }
}
```

### 12.2. Compiling and Running

In the `mod-spi` directory with JDK 17+:

```bash
javac --module-source-path src -d mods src/svc.api/module-info.java src/svc.api/svc/api/Greeting.java src/svc.provider/module-info.java src/svc.provider/svc/provider/HelloGreeting.java src/svc.host/module-info.java src/svc.host/svc/host/Main.java
java --module-path mods --add-modules svc.provider --module svc.host/svc.host.Main
```

Use `--add-modules svc.provider` to ensure the provider module is included in the module graph for this run. Merely placing the artifact on the module path **is not always sufficient** for the module to be resolved.

Stdout:

```text
ServiceLoader created
Module provider initialized
Module provider constructed
Provider message: hello JPMS
```

Here the provider module **does not export the implementation package**, yet ServiceLoader still instantiates the provider thanks to the `provides` declaration. The consumer only needs the service API. The static block/constructor runs when `findFirst()` obtains the instance, not merely when creating the ServiceLoader object.

### 12.3. If Creating a Separate Plugin ModuleLayer

For modules loaded into a child `ModuleLayer`, use:

```java
// Excerpt: layer has already been created and Greeting.class is the shared service API.
ServiceLoader<Greeting> services =
        ServiceLoader.load(layer, Greeting.class);
```

This overload searches for providers in the layer and ancestor layers according to the contract; **it does not find providers belonging to unnamed modules**. You must ensure the service API is properly shared with the right defining loader/module between the host and providers; otherwise type identity or service configuration errors may occur.

## 13. When Does ServiceConfigurationError Occur?

`ServiceLoader` can defer **even errors** until a provider is actually discovered or instantiated. Do not infer that a successful `ServiceLoader.load(...)` call means the metadata/providers are completely valid.

Some typical errors:
- A `META-INF/services/...` file has invalid syntax, wrong encoding, or encounters an I/O error while being read.
- Incorrect provider binary name or missing class file.
- The provider is not assignable to the service interface/class.
- A classpath provider lacks a **public no-arg constructor**, is an unsuitable abstract class/interface, or its constructor throws an exception.
- An explicit named-module provider factory method has an invalid signature, returns `null`, or throws an error.
- Provider code cannot be loaded/linked due to dependency or class version issues.
- The named-module caller lacks a matching `uses` directive or the service type is not accessible.

When encountering an issue, `ServiceLoader` uses **`ServiceConfigurationError`**, a subclass of `Error`, instead of returning “no provider” in all cases.

### Catching Errors at the Discovery Boundary

```java
// Excerpt in an application that has the Greeting service.
try {
    for (Greeting g : ServiceLoader.load(Greeting.class)) {
        System.out.println(g.message());
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("Broken service registration: " + error);
    Throwable cause = error.getCause();
    if (cause != null) {
        cause.printStackTrace();
    }
}
```

This is an excerpt; a valid Greeting interface and ServiceLoader import are required. Errors can arise in `Iterator.hasNext()`, `next()`, or `stream()` processing; therefore error handling must wrap **the traversal operation itself**, not only `ServiceLoader.load()`.

Do not catch `Throwable` and ignore it to pretend the system has 0 providers. If metadata declares a provider that is invalid, that is a **configuration error**, which is different from declaring no provider.

### Should You Automatically Skip a Broken Provider and Take the Next One?

The API documentation states that after an error, the iterator may **attempt** to locate the next provider, but **recovery is not guaranteed**. Depending on system requirements, you can fail fast and report a configuration error, or implement a controlled retry policy. Do not write a `while(true)` loop that catches every error and continues indefinitely.

## 14. Provider Ordering and Configuring Implementation Selection

`ServiceLoader.findFirst()` is convenient, yet “first” depends on the source of provider declarations and lookup order, especially in these situations:
- Multiple `META-INF/services` files on the classpath.
- Multiple named modules providing the same service.
- Multiple modules residing in the same `ModuleLayer`.
- Parent/child ClassLoaders with their own providers.

On the classpath, according to the ServiceLoader contract, ordering is based on `ClassLoader.getResources` along with the order of provider names within each file. Within a single named module, the order of providers declared in the descriptor is preserved, but **the order across modules in the same layer is unspecified**.

Therefore, if an application needs a provider with the highest **business priority**:
- Do not blindly rely on `findFirst()` over a changing module graph.
- Discover candidate types via `stream()`.
- Read defined priority annotations/metadata and check suitability.
- Select according to explicit rules and instantiate only the chosen provider if possible.
- If priority cannot be determined without instantiation, define an appropriate lifecycle/resource model and do not invoke constructors indiscriminately.

The example of selecting by class name is a demo, not a priority configuration strategy sufficient for large products.

## 15. A Provider Is Not Necessarily a Singleton

`ServiceLoader` creates providers on demand; this **does not automatically provide an application-wide singleton contract**.

- A single `ServiceLoader` instance caches providers already instantiated by its iterator.
- Calling `ServiceLoader.load(...)` again creates a **new ServiceLoader object** with its own cache.
- `reload()` can cause an existing ServiceLoader to re-instantiate a provider.
- `Provider.get()` must be viewed under the “returns an instance” contract; **you should not assume stable identity**.
- The provider class's static initializer does not necessarily run again when a new provider object is created.

If a provider opens a connection pool, spawns threads, holds sockets, or registers listeners in its constructor, its lifecycle must be managed **at the application level**. ServiceLoader has no `close()` method to automatically close all provider instances. When a service interface requires cleanup, you can design:

```java
// Contract design excerpt:
public interface ManagedService extends AutoCloseable {
    String name();

    @Override
    void close() throws Exception;
}
```

This is a complete interface that can be compiled in `ManagedService.java`, but **it is not enough to create a standalone SPI application**. Consumers must call `close()` on the provider instances they actually own, in the appropriate order and under appropriate conditions. Do not close shared objects yourself if the provider is managed by another container.

## 16. Is ServiceLoader Thread-Safe?

**No.** The `ServiceLoader` documentation states that instances are **not safe for concurrent access by multiple threads**. A ServiceLoader's cache, iterator, stream, and `reload()` contain mutable state.

Consequences:
- Do not share a single `ServiceLoader` object across multiple threads for concurrent traversal and reload without coordination.
- If multiple tasks need providers, consider creating a separate `ServiceLoader` per scope/thread or using locking at the orchestration layer.
- Do not call `reload()` while another thread is using an iterator/stream of the same object.
- Whether a provider instance is thread-safe is **the implementation's own contract**, not something to be inferred from ServiceLoader.
- A ClassLoader may be parallel-capable, but **that does not make a ServiceLoader instance thread-safe**.

For example, application-level synchronization wrapping can serialize discovery/reload operations, though you must still check whether provider methods call back into the loader/callbacks and avoid deadlocks. Simply slapping `synchronized` indiscriminately across the whole system can create new bottlenecks.

## 17. Does Provider Discovery Have Side Effects?

Possibly. Even though ServiceLoader is designed to be lazy, discovery time can still perform:
- Finding/reading provider config resources via the ClassLoader.
- Loading provider classes and dependencies when needed.
- Linking/verifying runtime types.
- Calling constructors or factory methods during instantiation.
- Running static initialization upon active use.
- Performing I/O depending on custom ClassLoaders (remote URLs, network JARs).
- Triggering exceptions/errors when metadata/bytecode is invalid.

Therefore, do not say “`ServiceLoader.load()` is completely safe and does nothing” in the sense that no exceptions or costs could ever happen. It **creates the service loader object**, while most discovery/instantiation is deferred. The exact outcome of subsequent operations depends on the module/loader environment.

If you want to build an application with low startup latency, use `stream` to filter when possible and avoid instantiating every provider just to read its name. However, filtering by `Provider.type()` can still load classes, so actual profiling is necessary.

## 18. Typical Error Example: Provider Class Exists but Is Not Found

Scenario:
- `demo.impl.AlphaGreeting.class` exists in a directory.
- The host uses `ServiceLoader.load(Greeting.class)`.
- There is no `META-INF/services/demo.spi.Greeting` file in the output or `provides` module descriptor.

**The result may be that no provider is found**, even though calling `Class.forName("demo.impl.AlphaGreeting")` succeeds. `ServiceLoader` does not scan all classes on the classpath on its own to find implementations.

How to diagnose:

1. Verify the **exact** service interface binary name.
2. Check whether the `META-INF/services/...` file has been copied into the JAR/out directory.
3. Check whether the contents contain provider binary names, use UTF-8 encoding, and do not append `.class`.
4. Check whether the provider class has a public no-arg constructor if deployed on the classpath.
5. Check the loader used to find the configuration and classes: explicit loader or TCCL.
6. If using named modules, check `uses`/`provides`, whether the module is resolved, and whether it is in the right layer.
7. If the same service interface binary name is defined in two different loaders, the provider may not be assignable to the consumer's service type.
8. Distinguish **no provider present** (Optional.empty) from **broken provider** (ServiceConfigurationError).

For a provider JAR:

```bash
jar --list --file provider.jar
```

Look for the corresponding entries, for example:

```text
META-INF/services/demo.spi.Greeting
demo/impl/AlphaGreeting.class
```

These are the two entries to look for, not the entire stdout. Do not inspect only the source tree: verify the **final artifact that the JVM actually runs**.

## 19. Duplicate API Error Across Multiple ClassLoaders

A common plugin-system error:

```text
Host ClassLoader
  └── demo.spi.Greeting       [runtime class A]

Plugin ClassLoader
  ├── demo.spi.Greeting       [runtime class B]
  ├── demo.impl.AlphaGreeting [implements B]
  └── META-INF/services/demo.spi.Greeting

Class A != Class B
```

If the provider implements interface B defined by the plugin loader, while the host queries `ServiceLoader.load(ClassA, pluginLoader)`, the provider may **not be assignable** to service class A. This is a **class identity** problem, not merely a missing class name in configuration.

Common solutions:
- Place the service API in a parent loader/shared module.
- Have the plugin loader use that exact API without redefining the interface itself.
- The provider implementation can reside in its own loader.
- Inspect `providerClass.getClassLoader()` and `serviceClass.getClassLoader()`; do not compare only name strings.

If a custom loader is child-first for all packages, you must whitelist the shared service API to be parent-first, avoiding duplicate contract definitions.

## 20. Reload and ClassLoader Lifecycle When Swapping Plugins

There are three distinct lifecycle layers:

| Component | Meaning of the Operation |
|---|---|
| `ServiceLoader.reload()` | Clears the provider discovery/instances cache of the ServiceLoader object |
| `URLClassLoader.close()` | Closes the URLClassLoader's resources for locating new classes/resources |
| JVM class unloading | Can collect runtime classes/loaders when no longer reachable and GC executes appropriately |

They are not interchangeable.

A plugin manager can perform:

```text
stop requests
  ↓
finish/cancel in-flight provider operations
  ↓
unregister callbacks, close provider-owned resources
  ↓
restore TCCL, clear caches/references
  ↓
discard old ServiceLoader and provider instances
  ↓
close old URLClassLoader (if owned)
  ↓
build a new ClassLoader/ModuleLayer for new plugin generation
  ↓
create new ServiceLoader and discover providers again
```

Do not use `ServiceLoader.reload()` as the sole hot-deployment solution when bytecode has already been defined by an old loader. Likewise, `URLClassLoader.close()` does not force old classes to disappear and does not stop threads created by a provider.

## 21. Common Misconceptions

| Misconception | Fact |
|---|---|
| `ServiceLoader.load` creates all providers immediately | The API is designed to be lazy: discovery/instantiation happens on demand |
| `iterator()` creates all provider objects | Creation occurs during traversal, especially on `next()` |
| `hasNext()` is always free and cannot fail | It can search configs, load/verify providers, and throw ServiceConfigurationError |
| `stream()` returns Stream<S> | It returns `Stream<ServiceLoader.Provider<S>>` |
| `Provider.type()` and `Provider.get()` are the same | One returns the type, the other returns an instance |
| `Provider.get()` is always a singleton cache | Global instance identity must not be assumed |
| `findFirst()` always returns a provider or empty | Broken metadata can cause ServiceConfigurationError |
| Having the implementation .class is enough | Classpath requires `META-INF/services`; named modules use `provides` |
| ServiceLoader always takes the caller's loader | `load(S.class)` uses the TCCL; an explicit overload exists |
| A provider class must export its package in JPMS | `provides` can register a non-exported implementation |
| Classpath providers use a static provider() factory | The factory provider method is only under the explicit named-module contract |
| `reload()` unloads classes and replaces bytes | It only clears the provider cache |
| ServiceLoader automatically closes providers after use | The application/container must manage their lifecycle separately |
| ServiceLoader is thread-safe | ServiceLoader instances are not safe for uncoordinated concurrent use |
| `findFirst()` is a stable business priority in every environment | Order depends on JAR/module/loader configuration |
| `ServiceConfigurationError` is like a missing provider | It is a configuration error, not Optional.empty |

## 22. Self-Check Questions

1. **How do a service and a provider differ?** A service is the contract interface/class; a provider is an implementation discovered at runtime.
2. **Does `ServiceLoader.load(...)` instantiate all providers immediately?** No; discovery and instantiation are lazy.
3. **Can `iterator().hasNext()` cause I/O or errors?** Yes, when searching for metadata/providers.
4. **What does `iterator().next()` return?** A provider instance of the service type.
5. **What type of Stream does `stream()` return?** `Stream<ServiceLoader.Provider<S>>`.
6. **How do `Provider.type()` and `get()` differ?** Type returns the Class of the provider type, and get returns an instance.
7. **Is `findFirst()` guaranteed not to throw ServiceConfigurationError?** No.
8. **What happens if a provider class file is placed in a JAR without a service configuration?** The class may exist, but ServiceLoader will not automatically discover it via classpath SPI.
9. **What is the file name in META-INF/services?** The binary name of the service interface/class.
10. **Which constructor does a classpath provider typically need?** A public no-arg constructor.
11. **What does a named-module consumer declare?** `uses service.Type;` along with the read dependency when needed.
12. **What does a named-module provider declare?** `provides service.Type with provider.Type;`.
13. **Does a provider module need to export its implementation package?** Not necessarily for ServiceLoader.
14. **Which loader does `ServiceLoader.load(S.class)` use?** The TCCL according to the contract.
15. **Does `reload()` re-run the static initializer of a class already initialized successfully?** No.
16. **After reload, is it safe to use an old iterator?** No; create a new iterator/stream.
17. **Does ServiceLoader automatically clean up provider resources?** No.
18. **Are two service classes with the same name but defined by different loaders compatible?** Not automatically.
19. **To hot reload new bytecode, is simply calling reload() enough?** No; a new loader generation is usually required.
20. **How should a broken metadata error be handled?** As `ServiceConfigurationError`, distinct from having no provider.

## Official References

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, lazy timing, iterator/stream, provider cache, reload, ordering, module/classpath formats, ServiceConfigurationError errors.
- [Java SE 17 — ServiceLoader.Provider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()` and `get()`.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): binary names, parent delegation, and loader identity.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): plugin modules and module layers.
- [JLS 17 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): `uses`, `provides`, and module access.
- [JLS 17 — §12.2–12.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization.

**Conclusion:** `ServiceLoader` separates **provider registration/discovery** from **provider instance creation**. `iterator()` instantiates during traversal, `findFirst()` retrieves only the first provider, and `stream()` supports inspecting the type before calling `Provider.get()`. When building an SPI or plugin system, you must choose the right ClassLoader/ModuleLayer, distinguish “no provider” from “misconfigured provider”, and manage caching, concurrency, and provider lifecycles instead of treating `reload()` as class unloading.
