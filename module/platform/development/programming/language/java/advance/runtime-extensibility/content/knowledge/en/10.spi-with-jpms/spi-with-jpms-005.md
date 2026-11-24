# Instantiating SPI Providers in JPMS: Constructor or `public static provider()`?

`ServiceLoader` is the standard mechanism for Java applications to discover and instantiate objects that provide a **service contract** (SPI), while the consuming module depends only on the service's public interface/abstract class. With the **Java Platform Module System (JPMS)**, a service-providing module registers its provider via `provides ... with ...` and has **two mechanisms for creating a service instance**:

1. **Provider constructor:** `ServiceLoader` invokes the `public` no-arg constructor of the provider class, which must implement/extend the service.
2. **Provider method:** `ServiceLoader` invokes a no-arg `public static provider()` method on the class declared as the provider; the method returns an instance of the service. The factory class itself **does not need** to implement the service.

Choosing the right mechanism determines how you hide implementations, construct objects, detect configuration errors, inspect provider metadata, and manage instance lifecycles. This lesson focuses on how to **instantiate providers using both mechanisms in explicit named modules**, while distinguishing the rules when using the classpath or automatic modules.

## 1. Roles in a Modular SPI Contract

Suppose an application wants to use `MessageService` without knowing the specific provider:

~~~text
lesson.app                 lesson.spi                  lesson.providers
(host/consumer)              (API)                     (implementations)
requires lesson.spi  ----> exports lesson.spi <---- requires lesson.spi
uses MessageService                                         |
       |                                                    |
       +--- ServiceLoader<MessageService> <--- provides MessageService
                                               with DirectMessage, FactoryMessage
~~~

- **Service type:** an interface or class known to API consumers, such as `lesson.spi.MessageService`.
- **Consumer module:** the module performing discovery, having `uses lesson.spi.MessageService;` and normally `requires lesson.spi;`.
- **Provider module:** the module declaring `provides lesson.spi.MessageService with ...;` to register one or more providers.
- **Provider class:** the class placed **after the `with` keyword**. For the constructor path, this class is the implementation. For the factory path, this class may simply be where the `provider()` method is defined.
- **Service instance:** the actual object returned to the host when the provider is instantiated; it must always be compatible with the service type.

`uses` and `provides` are modular metadata; `ServiceLoader` uses them to locate resolved providers. `requires` expresses API dependencies between modules. The consumer module usually does **not** need `requires lesson.providers`: this keeps the extensible architecture independent of concrete implementations.

## 2. Instantiation via Provider Constructor

### 2.1. Prerequisites

For a provider declared with `provides` in a module and **without a provider method**, the provider class must:

- Be a public class declared in the same module that contains `provides`; the provider module may keep the implementation package unexported.
- Be a valid subtype of the service type: `implements ServiceInterface` or `extends AbstractService` as appropriate.
- Have a **`public` no-arg constructor**. A Java-generated default constructor satisfies this if the class is public and declares no other constructors.
- Be instantiable normally; if the constructor throws an error, service creation fails.

Example:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class DirectMessage implements MessageService {
    public DirectMessage() {
        System.out.println("constructor: DirectMessage");
    }

    @Override
    public String message(String name) {
        return "Hello, " + name;
    }
}
~~~

When this provider is requested via `ServiceLoader`, the JDK instantiates `DirectMessage` using its public no-arg constructor. The resulting object is an instance of that class; `Provider.type()` returns `DirectMessage.class`.

A parameterized constructor such as `DirectMessage(Settings settings)` **cannot** substitute for a provider constructor. `ServiceLoader` does not automatically pass configuration or DI objects into parameters. If complex configuration is needed during initialization, you can choose the factory path, or construct a simple instance and configure it through a separately defined lifecycle contract.

### 2.2. When Is This Mechanism Suitable?

The constructor path is usually easier to inspect and has fewer layers of indirection when:

- The provider class itself is the public implementation of the service.
- Initialization is simple enough and does not need to select an implementation based on runtime conditions.
- You do not want to expose a separate factory or custom instantiation rules.
- You need packaging that supports explicit named modules, **automatic modules**, and classpath-based `META-INF/services` providers alike.

Even though the provider class is `public`, the module does not have to `exports` the implementation package. Public visibility in Java declarations and JPMS package exports are two separate layers of control.

## 3. Instantiation via `public static provider()`

### 3.1. Contract of the Provider Method

In an **explicit named module**, if the provider class declares a method:

~~~java
public static MessageService provider()
~~~

then `ServiceLoader` invokes that method to obtain the service instance. A valid method must:

1. Be named exactly `provider`, be `public static`, and **take no parameters**.
2. Have a **declared return type** assignable to the service type (the service type itself or a valid subtype).
3. Be present on the provider class registered via `provides` in that same module.
4. Return **a non-`null` object** compatible with the service type; exceptions thrown from the factory cause instantiation to fail.

Example:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class FactoryMessage {
    private FactoryMessage() {}

    public static MessageService provider() {
        return new PrivateMessage();
    }
}

final class PrivateMessage implements MessageService {
    @Override
    public String message(String name) {
        return "Hi, " + name;
    }
}
~~~

`FactoryMessage` is listed in `provides`, yet it **does not implement `MessageService`** and has a **private constructor**. The created object is `PrivateMessage`, a package-private class. Code in the consuming module receives the instance as `MessageService` without needing direct access to the implementation.

With a provider factory, **`Provider.type()` returns the `Class` of the *declared* return type of `provider()`**. In this example, that is `MessageService.class`, not `FactoryMessage.class` or `PrivateMessage.class`.

### 3.2. How Is the Factory Invoked?

~~~text
Provider module declares:
provides MessageService with FactoryMessage
                            |
                            +--> public static MessageService provider()
                                      |
                                      +--> new PrivateMessage()
                                              |
                                              +--> instance of MessageService
~~~

There is no automatic constructor injection: the factory signature has no parameters. The factory can still use internal logic to choose an implementation, create a proxy/decorator, or coordinate a pre-designed cache, though it must ensure valid configuration, error handling, and avoid unexpected side effects.

Notably, **the factory class is not required to have a public no-arg constructor**; it can have a private constructor, or the provider type can even be an interface/abstract class declaring a compliant static factory under Java rules. For sample code, a `final` class with a private constructor clearly signals a "factory-only" intent.

### 3.3. What If Both a Constructor and `provider()` Exist?

For a valid provider in an explicit named module, if a provider method exists, `ServiceLoader` **chooses the `provider()` method** to create the instance. This holds true even when the provider class itself implements the service and also has a public no-arg constructor. Do not design two creation paths with differing side effects and rely on users guessing which one gets called.

Conversely, if the provider class **does not have** a valid provider method, it must satisfy the constructor and subtype requirements. A `create()` method, a `provider(String name)` method, or a static `INSTANCE` field cannot serve as a substitute provider method.

## 4. Direct Comparison of the Two Mechanisms

| Aspect | Provider Constructor | `public static provider()` |
| --- | --- | --- |
| Declaration form in JPMS | `provides S with DirectImpl;` | `provides S with FactoryClass;` |
| Must provider class be a subtype of `S`? | **Yes** | **Not required** |
| Public no-arg constructor? | **Required** | **Not required** |
| No-arg `public static provider()` factory? | None | **Required** |
| Checked return type | Instance is the provider class, a subtype of `S` | Declared return type of the method is a subtype of `S` |
| `Provider.type()` | The provider class directly | The method's declared return type |
| `Provider.get()` | Triggers the constructor | Triggers the method |
| Can it hide the concrete implementation? | The implementation class must be the public provider | Can return a package-private class or a chosen implementation |
| Supported on classpath/automatic modules | Yes, per provider constructor rules | **No** |
| Initialization cost/side effects | Inside the constructor | Inside the factory and the object creation it selects |

Both are ways of **instantiating a service provider for `ServiceLoader`**. Neither mechanism guarantees singleton semantics, thread safety, retries, lifecycle cleanup, or isolation between tenants by default.

## 5. Compilable and Runnable Java 17 Example

This example uses **three explicit named modules**: one SPI module, one module registering two providers using both mechanisms, and one consumer module. The goal is to observe when the constructor/factory is invoked, what type the returned instance has, and why reading the list of `Provider` handles does not mean instances have already been created.

File structure:

~~~text
src/
├── lesson.spi/
│   ├── module-info.java
│   └── lesson/spi/MessageService.java
├── lesson.providers/
│   ├── module-info.java
│   └── lesson/providers/
│       ├── DirectMessage.java
│       └── FactoryMessage.java
└── lesson.app/
    ├── module-info.java
    └── lesson/app/Main.java
~~~

### 5.1. Declaring the SPI Module

File `src/lesson.spi/module-info.java`:

~~~java
module lesson.spi {
    exports lesson.spi;
}
~~~

File `src/lesson.spi/lesson/spi/MessageService.java`:

~~~java
package lesson.spi;

public interface MessageService {
    String message(String name);
}
~~~

Using an interface as the service type ensures the host depends only on calling `message`, without casting to provider implementation classes.

### 5.2. Declaring the Providers Module

File `src/lesson.providers/module-info.java`:

~~~java
module lesson.providers {
    requires lesson.spi;
    provides lesson.spi.MessageService
            with lesson.providers.DirectMessage, lesson.providers.FactoryMessage;
}
~~~

`provides ... with ...` explicitly lists the registration order of the two providers **within the same module descriptor**. The `lesson.providers` package stays encapsulated because there is no `exports lesson.providers;`. The host can still discover the providers via `ServiceLoader` under the JPMS contract.

File `src/lesson.providers/lesson/providers/DirectMessage.java`:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class DirectMessage implements MessageService {
    public DirectMessage() {
        System.out.println("constructor: DirectMessage");
    }

    @Override
    public String message(String name) {
        return "Hello, " + name;
    }
}
~~~

File `src/lesson.providers/lesson/providers/FactoryMessage.java`:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class FactoryMessage {
    private FactoryMessage() {}

    public static MessageService provider() {
        System.out.println("factory: provider()");
        return new PrivateMessage();
    }
}

final class PrivateMessage implements MessageService {
    @Override
    public String message(String name) {
        return "Hi, " + name;
    }
}
~~~

Note that `PrivateMessage` is in the same source file as a **non-public** top-level class. Java allows this when a file has only one public top-level class matching the filename. The actual implementation stays hidden inside the module and communicates via `MessageService`.

### 5.3. Declaring the Consuming Module

File `src/lesson.app/module-info.java`:

~~~java
module lesson.app {
    requires lesson.spi;
    uses lesson.spi.MessageService;
}
~~~

File `src/lesson.app/lesson/app/Main.java`:

~~~java
package lesson.app;

import java.util.List;
import java.util.ServiceLoader;
import lesson.spi.MessageService;

public final class Main {
    public static void main(String[] args) {
        List<ServiceLoader.Provider<MessageService>> providers =
                ServiceLoader.load(MessageService.class).stream().toList();
        System.out.println("found=" + providers.size());
        for (ServiceLoader.Provider<MessageService> provider : providers) {
            System.out.println("type=" + provider.type().getName());
        }
        System.out.println("create:");
        for (ServiceLoader.Provider<MessageService> provider : providers) {
            MessageService instance = provider.get();
            System.out.println(instance.message("Java"));
        }
    }
}
~~~

The first loop processes `Provider.type()` without calling `Provider.get()`. Only the second loop triggers instantiation via constructor or factory. The `List` holds provider handles simply to demonstrate the two phases clearly.

### 5.4. Compile and Run Commands

From the directory containing `src/`, with JDK 17 or newer:

~~~bash
javac --release 17 --module-source-path src -d out -m lesson.app,lesson.providers
java --module-path out --add-modules lesson.providers -m lesson.app/lesson.app.Main
~~~

`javac` compiles the target modules along with the required `lesson.spi` module. At runtime, `--module-path out` makes the compiled modules visible to the JVM. `--add-modules lesson.providers` ensures the provider module is **resolved** so service binding can locate the providers in this simple example. In real applications, the module graph and runtime configuration may provide other ways to resolve providers.

**Exact stdout of the example:**

~~~text
found=2
type=lesson.providers.DirectMessage
type=lesson.spi.MessageService
create:
constructor: DirectMessage
Hello, Java
factory: provider()
Hi, Java
~~~

What the printed lines mean:

1. `found=2`: `ServiceLoader.stream()` discovered two providers. This count matches **the example's module set**; a real application may have additional providers.
2. `type=lesson.providers.DirectMessage`: the constructor provider declares a subtype implementing the service, so `type()` is the provider class.
3. `type=lesson.spi.MessageService`: the factory is declared to return `MessageService`, so `type()` is the method's return type, **not** `FactoryMessage` or `PrivateMessage`.
4. `create:` appears before both instantiation calls, proving that the metadata iteration loop in the example **did not invoke either the constructor or the factory**.
5. `constructor: DirectMessage` appears as soon as the first provider is requested via `get()`.
6. `factory: provider()` appears when the second provider is requested via `get()`; the factory returns an instance of the package-private class `PrivateMessage`.
7. Both respond successfully through the same interface: `Hello, Java` and `Hi, Java`.

**Regarding ordering:** in this example each provider belongs to **the same module** and they are listed as `DirectMessage, FactoryMessage`, so `ServiceLoader` retrieves them in descriptor order. Do not assume this ordering applies across providers from **different modules**, because the API makes no ordering guarantees across modules/layers. For systems requiring explicit prioritization, define your own priority or metadata instead of relying on discovery order.

## 6. Discovery Lifecycle, Metadata, and Lazy Instantiation

`ServiceLoader` has two typical consumption styles:

~~~java
ServiceLoader<MessageService> loader =
        ServiceLoader.load(MessageService.class);

// Iterate instances: each retrieved element is a MessageService.
for (MessageService service : loader) {
    // service is already instantiated when the iterator returns the element.
}

// Iterate provider handles: inspect metadata first, call get() when needed.
loader.stream().forEach(provider -> {
    Class<? extends MessageService> type = provider.type();
    // provider.get() is what requests instance creation.
});
~~~

This is an **illustrative API snippet**, assuming `MessageService` exists and the module has `uses`. It is not a standalone Java program.

| Operation | Purpose | Expected Consequence |
| --- | --- | --- |
| `ServiceLoader.load(Service.class)` | Creates a loader that searches for providers by context loader / module graph | Does not mean all providers have been instantiated yet |
| `iterator().next()` | Retrieves a service instance | May execute a constructor or factory; results are cached per `ServiceLoader` iterator behavior |
| `stream().toList()` | Collects provider handles/metadata | Does not require calling `provider.get()` just to read type metadata |
| `Provider.type()` | Returns the declared provider type | For a factory, this is the declared return type of `provider()` |
| `Provider.get()` | Obtains an instance through the corresponding creation path | May run custom code, fail, allocate resources, and cause side effects |
| `ServiceLoader.reload()` | Clears the loader instance's provider cache | Subsequent iteration rediscovers providers; does not close instances or unload modules |

**Distinguishing caching behavior:** when iterating via `iterator`, `ServiceLoader` caches the provider instances it has instantiated for subsequent iterations of the same loader, unless `reload()` is called. With `stream()`, the loader caches discovered providers at the provider-handle level; **do not rely on assuming calling `Provider.get()` multiple times always returns the same instance**. If an intentional singleton is required, the factory and host must establish an explicit ownership/lifecycle contract.

Calling `get()` may trigger I/O, open connections, or fail initialization depending on how the provider is implemented. Therefore, inspecting metadata before selecting a provider can reduce unnecessary instantiation, though the selector must understand that a factory's `type()` may only be the service interface and will not reveal the concrete implementation class.

## 7. Constructor and Provider Method Across Classpath, Automatic Modules, and Explicit Named Modules

The three packaging approaches **differ in their instantiation rules**:

| Deployment Environment | Registration Declaration | Constructor | `public static provider()` |
| --- | --- | --- | --- |
| **Explicit named module** with `module-info.java` | `provides Service with ProviderClass;` | Yes | **Yes** |
| **Automatic module** (JAR without full descriptor, on module path) | Can be derived from provider configuration inside the JAR | Yes | **Not supported** |
| **Classpath/unnamed module** | `META-INF/services/<binary service name>` | Yes | **Not supported** |

Classpath configuration example:

~~~text
META-INF/services/lesson.spi.MessageService
~~~

The contents of that file can be:

~~~text
lesson.providers.DirectMessage
~~~

This file must be UTF-8 encoded, named after the **full binary name of the service**, and each data line specifies the **binary name of a provider class**, optionally with comments starting with `#`.

The classpath configuration above is valid if `DirectMessage` is a subtype of `MessageService` and has a public no-arg constructor. You **cannot** simply change it to:

~~~text
lesson.providers.FactoryMessage
~~~

and expect `ServiceLoader` on the classpath to automatically call `FactoryMessage.provider()`. When a provider is declared via the classpath or an automatic module, the provider method mechanism does not operate; the factory class in the example does not implement the service and has a private constructor, so it fails the constructor-provider requirements.

Consequently, when migrating a system from classpath to JPMS or vice versa, you must re-verify **provider types**, **instantiation mechanisms**, **registration metadata**, and **the module graph**. Having a method named `provider` does not mean `ServiceLoader` will detect that method in every environment.

## 8. Compile-Time Constraints and Runtime Errors

### 8.1. Constraints in `module-info.java`

According to the Java Language Specification §7.7.4, when using `provides S with P`:

- `P` is a provider declared in **the same module**; you cannot take a provider class residing in another module and list it directly.
- The provider must be a **public top-level or public static member** type, not a non-static inner class.
- If a provider method is present, its **declared return type** must be accessible and a subtype of the service; the factory class itself does not have to be a subtype of the service.
- If there is no provider method, the provider class must be a subtype of the service and have a public no-arg provider constructor.
- Do not list the same provider twice in a single `with` clause, and do not declare duplicate services across multiple `provides` directives in the same module.

Violations can be caught by the compiler when building explicit named modules. For modified metadata/JARs, bytecode outside Java source conventions, or errors arising at runtime, `ServiceLoader` can throw `ServiceConfigurationError`.

### 8.2. Common Misconfigurations

**Mistake 1: constructor takes parameters, with no provider method.**

~~~java
// Invalid illustration for a constructor provider:
public DirectMessage(Config config) { /* ... */ }
~~~

This constructor will not be called by `ServiceLoader` with `Config`. A valid public no-arg constructor is required, or else switch to a factory in an explicit named module.

**Mistake 2: provider method takes parameters or is not `public static`.**

~~~java
// Invalid illustration, not a valid provider method:
private MessageService provider() { /* ... */ return null; }
public static MessageService provider(Config config) { /* ... */ return null; }
~~~

`ServiceLoader` does not "guess" factory calls automatically; if a valid constructor is also missing, the provider is invalid. The lines above merely illustrate invalid signatures, not a runnable Java program.

**Mistake 3: factory returns `null` or throws an exception.**

~~~java
public static MessageService provider() {
    return null; // Provider.get() will fail.
}
~~~

This method illustrates error behavior and must not be used as a real implementation. When `ServiceLoader` invokes the factory and gets `null` (or an exception), it reports `ServiceConfigurationError`; initialization may have already opened resources before failing, so the provider must clean up on failure.

**Mistake 4: provider is not resolved at runtime.**

Having a module file on the module path does not necessarily mean that module is in the resolved graph being used by the application. Check `--module-path`, root modules, `--add-modules` (where appropriate), or service binding/`ModuleLayer` configuration. Do not add `requires providerModule` to the consumer just to work around configuration issues if the architecture needs to preserve SPI-only coupling.

**Mistake 5: service type duplicated across loaders.**

A provider implements a copy of the interface loaded from a different loader than the `MessageService.class` used by the consumer. Subtype checks can fail even when binary names match. Shared SPI interfaces, DTOs, and public exceptions should live in a common API area visible to both host and plugins.

### 8.3. At Which Step Do Errors Surface?

- `javac` can report errors immediately in `module-info.java` when provider signatures fail source-level constraints.
- `ServiceLoader.load(...)` constructs a loader, but discovery is lazy; many errors only surface while processing the `iterator` or `stream`.
- With an iterator, `hasNext()`/`next()` may throw `ServiceConfigurationError` when loading or instantiating a provider.
- With a stream, errors may appear when a terminal operation actually locates/loads providers; `Provider.get()` can also report its own errors when calling the constructor or factory.
- `ServiceConfigurationError` is an `Error`, **not** a checked exception. The host must decide on a policy—skipping faulty providers or failing fast—logging the root cause properly rather than swallowing configuration errors with a broad catch and staying silent.

A factory failure does not prove the SPI interface is wrong; inspect the stack trace and root cause across the constructor, factory, classloading, or module resolution.

## 9. Choosing a Mechanism Based on Needs and Operational Responsibilities

**Prefer a constructor** when you need a straightforward implementation with a public no-arg constructor and have no need to select subclasses at runtime or hide instantiation details. This is also the required choice if you must remain deployable on the classpath/automatic modules under default `ServiceLoader` rules.

**Prefer `provider()`** if you want the provider module to decide how instances are constructed without exposing implementations—for example:

- Selecting an internal implementation based on a validated environment.
- Returning a service-compatible decorator/proxy.
- Initializing caches or complex dependencies inside the factory in a controlled way.
- Keeping the implementation class package-private and avoiding a public constructor exposed solely for discovery.

However, factories still have clear limitations:

- The method **takes no parameters**: the host cannot directly pass `Config` or `Executor` as parameters to the SPI factory. If context must be passed, design a separate initialization/configuration API, a separate dependency container, or a properly scoped extension context contract.
- A factory can return a broad type like `MessageService`; `Provider.type()` then does not reveal the runtime implementation, so filters relying on implementation class names or annotations may misfire.
- **Instance scope rules** must be documented: whether each call creates a new instance or reuses one, who closes it, whether concurrent calls are allowed, and what to do if the factory fails.
- Each registered provider is an extension point that can fail independently; the host needs a consistent fault-isolation and fallback policy.

### Design Checklist Table

| Question to Answer | Constructor Path | Factory Path |
| --- | --- | --- |
| Does the instance need a public implementation class? | Provider class must be public | Instance class can be non-public |
| Need to customize implementation selection at creation time? | Limited flexibility | Factory can select any compatible implementation |
| Required to deploy on classpath or automatic modules? | Suitable | Provider method is not used in those modes |
| Need to read metadata before instantiating? | `Provider.type()` is the implementation class | `Provider.type()` may only be the return interface |
| Need resource/singleton management? | Needs a separate contract | Also needs a separate contract |
| Need DI/input context? | No automatic constructor injection | No automatic factory parameters |
| Can the provider class be hidden behind a private constructor? | No | Yes |

## 10. Testing an Extension Point with Both Mechanisms

A useful contract test suite should include these cases:

1. **Discovery**: consumer module has `uses`, provider module has `provides`, and the module graph actually resolves; the discovered provider count matches the fixture expectation.
2. **Constructor route**: class implements the service, its public no-arg constructor is called **when an instance is needed**, and `Provider.type()` is the provider class itself.
3. **Factory route**: provider class does not implement the service, has a private constructor and a valid `public static provider()`; `get()` still returns a usable instance through the service API.
4. **Metadata and laziness**: calling `stream().map(Provider::type)` does not automatically invoke `get()`; count constructor/factory invocations via counters/logs rather than guessing.
5. **Invalid signatures**: provider lacks a valid constructor, factory is not public/static/no-arg, or return type is incompatible; distinguish compile-time validation from runtime errors.
6. **Factory failure**: factory throws an exception or returns `null`; the host catches and logs `ServiceConfigurationError` along with its cause.
7. **Lifetime**: if a provider holds sockets, threads, listeners, or files, provide a dedicated cleanup mechanism; `ServiceLoader.reload()` does not close those resources for the host.
8. **Concurrency**: do not share a single `ServiceLoader` instance arbitrarily across threads because it is **not thread-safe** itself; independently test the thread safety of instances returned by constructors/factories.
9. **Compatibility**: verify classpath/automatic modules still use the provider constructor; do not rely on a factory method when changing packaging.
10. **Ordering**: do not rely on arbitrary module ordering to decide the preferred provider; if a specific provider is needed, filter by published metadata.

Testing both paths is also valuable when upgrading Java or changing classloaders: the host must always receive an object assignable to the **exact shared `Class` of the service**, not merely an object with an interface of the same name defined by a different loader.

## 11. Summary of Rules to Remember

~~~text
Explicit named module:
    provides S with P
          |
          +-- Does P have public static S_or_Subtype provider()?
          |       |
          |       +-- YES -> ServiceLoader invokes provider()
          |                     P does not need to implement S
          |                     P does not need a public no-arg constructor
          |
          +-- NO -> P must implement/extend S
                         and have a public no-arg constructor

Automatic module / classpath provider:
    uses provider constructor
    does not support provider method

ServiceLoader.Provider<S>.type():
    constructor path -> provider implementation class
    factory path     -> declared return type of provider()
ServiceLoader.Provider<S>.get():
    requests creating/returning a service instance via the corresponding mechanism
~~~

**Decision point:** choosing between a constructor and `public static provider()` is **part of the provider packaging contract in JPMS**, not two equivalent names. With a constructor, the provider class itself is a subtype of the service; with a factory, the provider class is what produces a subtype of the service. Both communicate with the consumer through a shared service API.

### Official References

- [ServiceLoader – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider constructor rules, provider method, module/classpath, discovery, and errors.
- [ServiceLoader.Provider – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): semantics of `type()` and `get()`.
- [Java Language Specification 17, §7.7.4 Service Provision](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4): compile-time requirements for `provides ... with ...`.
- [JPMS module descriptor – java.lang.module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): declaring `uses` and `provides` in the module graph.
