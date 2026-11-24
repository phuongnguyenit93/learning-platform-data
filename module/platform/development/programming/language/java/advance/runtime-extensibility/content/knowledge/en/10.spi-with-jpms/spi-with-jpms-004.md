# Declaring `provides ... with ...` and Keeping Implementation Packages Encapsulated in JPMS

## 1. Problem: Exposing Extensibility Without Exposing Implementations

In a Java application using the **Java Platform Module System (JPMS)**, a host needs to invoke a **Service Provider Interface (SPI)** while independent modules supply implementations. The host must discover and use providers without importing implementation classes. At the same time, provider developers want to prevent external modules from directly depending on internal packages.

JPMS supports this model through two groups of declarations in **module-info.java**:

- **provides <Service> with <Provider>**: the provider module declares which service it implements and with which providers.
- **uses <Service>**: the consumer module indicates that code inside it may discover that service via **java.util.ServiceLoader**.

Only the **package containing the SPI interface or public contract types** needs to be exported to consumers. **The package containing implementation classes can remain unexported and unopened**, even though the provider class itself must satisfy the public requirements of the ServiceLoader mechanism.

Key insight: **registering a provider does not mean exporting the implementation package**. JPMS has a dedicated, controlled access path for locating and instantiating service providers. As a result, another module can receive an object through a shared interface without having permission to import or arbitrarily reflect into the implementation.

## 2. Three-Module Roles and Dependency Boundaries

A basic structure:

~~~text
ext.api
  └── exports ext.api
          ^
          | requires
          |
ext.app                 ext.provider
  ├── requires ext.api     ├── requires ext.api
  ├── uses ext.api.Greeting├── provides ext.api.Greeting
  └── ServiceLoader       │     with ext.provider.internal.GreetingImpl
                          └── NO exports/opens for ext.provider.internal
~~~

The three modules have distinct roles:

| Module | What It Contains | Core Declarations |
| --- | --- | --- |
| **ext.api** | `Greeting` interface and contract data types | **exports ext.api** |
| **ext.provider** | `GreetingImpl` class and processing details | **requires ext.api**; **provides ... with ...**; does not export the implementation package |
| **ext.app** | Host consuming the SPI, selecting and invoking providers | **requires ext.api**; **uses ext.api.Greeting** |

The host **does not need `requires ext.provider`** and does not need to know the `GreetingImpl` class name at compile time. Swapping implementations or adding another provider module does not force the host to modify imports or module descriptors, as long as the published SPI is satisfied.

**requires** controls module readability; **exports** controls access to a package's public types; **uses/provides** controls service registration and discovery. These mechanisms complement one another rather than replacing one another.

## 3. What Exactly Does `provides ... with ...` Declare?

In the provider module's **module-info.java**:

~~~java
module ext.provider {
    requires ext.api;

    provides ext.api.Greeting
        with ext.provider.internal.GreetingImpl;
}
~~~

Reading each part:

1. **module ext.provider**: this is the named module containing the provider.
2. **requires ext.api**: the provider compiles when referencing the `Greeting` interface located in the exported **ext.api** package.
3. **provides ext.api.Greeting**: the module announces that it supplies an implementation for this exact service type.
4. **with ext.provider.internal.GreetingImpl**: specifies the provider class; this name must be recognizable by the compiler within **the ext.provider module itself**.
5. Neither **exports ext.provider.internal** nor **opens ext.provider.internal** is present: the implementation package maintains strong encapsulation against other modules.

Do not write **provides** in the interface module to announce a provider located in a different module. The provider type listed after **with** must be declared within the same module containing the `provides` directive. A module can supply multiple providers for the same service:

~~~java
// Illustrative module-info.java snippet when both implementations exist in the same module.
provides ext.api.Greeting
    with ext.provider.internal.GreetingImpl,
         ext.provider.internal.AlternativeGreeting;
~~~

The multi-provider snippet is not a standalone program; `AlternativeGreeting` must be defined and valid before compiling. You cannot repeat the same service in two separate `provides` directives within the same module, or repeat the same provider in the same list.

**A `provides` directive does not mean an object is already instantiated when the JVM starts.** The module descriptor carries information for the service binding/discovery mechanism to locate providers; ServiceLoader typically finds and instantiates them when iterated.

## 4. Why Can an Implementation Class Be Public While Its Package Remains Hidden?

Java has two levels of access that must be distinguished:

- **public class**: a class with `public` access in the Java language. This is a requirement for a type listed after **with** to act as a provider in a named module.
- **exports package**: the module permits code in eligible modules to access public types in that package, subject to readability rules.

Therefore, you can declare:

~~~java
package ext.provider.internal;

import ext.api.Greeting;

public final class GreetingImpl implements Greeting {
    public GreetingImpl() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Even though `GreetingImpl` is **public**, code in `ext.app` **cannot directly import `ext.provider.internal.GreetingImpl`** when `ext.provider` does not export that package. If you try to modify the host to use the implementation directly, the compiler will reject it across the module boundary—even if you add **requires ext.provider** without a corresponding `exports`.

Conversely, ServiceLoader has a specialized mechanism to instantiate providers listed in the module descriptor, even when the provider's package is **not exported** to the calling module. This is an intentional feature of JPMS, not ServiceLoader arbitrarily bypassing access checks via ordinary reflection.

Helper classes inside an unexported package can remain package-private. However, the provider class declared directly in **provides ... with ...** must be a valid public top-level or public static nested type. Do not make the provider class package-private and expect leaving the package unexported to substitute for the `public` requirement.

## 5. How Do `exports`, `opens`, `requires`, `uses`, and `provides` Differ?

| Directive | Placed in Which Module? | Purpose | Needed for This Example? |
| --- | --- | --- | --- |
| **exports ext.api** | ext.api | Lets other modules use public API interfaces/DTOs | Yes |
| **requires ext.api** | ext.app and ext.provider | Allows code in the module to read the API module | Yes |
| **uses ext.api.Greeting** | ext.app | Declares the module containing ServiceLoader calls for `Greeting` | Yes |
| **provides ext.api.Greeting with ...** | ext.provider | Registers the provider residing in this module | Yes |
| **exports ext.provider.internal** | ext.provider | Exposes public implementation types to other modules | No; should be avoided |
| **opens ext.provider.internal** | ext.provider | Allows deep reflection into the package within the declared scope | Not needed |
| **open module ext.provider** | ext.provider | Opens all packages of the module for deep reflection | Not needed; weakens encapsulation |

**Exports** primarily serves access to public types and members under module rules. **Opens** grants reflective access according to the declared scope; it is not equivalent to exporting for normal imports. An unexported package can still be exposed to reflection if `opens` is declared, so maintaining true encapsulation usually means **neither exporting nor opening the implementation package**.

If an external framework genuinely needs reflection, you can consider **opens package to framework.module** for that specific module only, though that is a separate access-control decision. **ServiceLoader does not require opening the provider package**. Avoid reflexively adding `opens` just to fix a provider instantiation error: check provider requirements, the `provides` declaration, module resolution, and constructor/provider method code first.

**Qualified exports** such as **exports ext.api to ext.app, ext.provider** restrict interface consumers, requiring you to ensure every legitimate consuming module is authorized. For a public SPI aimed at multiple plugin developers, `exports ext.api` is usually easier to evolve.

## 6. Complete Java 17 Example: ServiceLoader Using a Provider from an Unexported Package

The example consists of three **explicit named modules**. One module owns the interface, one declares the provider, and the host module iterates over ServiceLoader. The code compiles with **javac --release 17** and runs on JDK 17 and later.

### 6.1. File Structure

~~~text
demo/
├── src/
│   ├── ext.api/
│   │   ├── module-info.java
│   │   └── ext/api/Greeting.java
│   ├── ext.provider/
│   │   ├── module-info.java
│   │   └── ext/provider/internal/GreetingImpl.java
│   └── ext.app/
│       ├── module-info.java
│       └── ext/app/Main.java
└── mods/                           # Generated during compilation
    ├── ext.api/
    ├── ext.provider/
    └── ext.app/
~~~

The directory names under **src/** are module names following the **--module-source-path** convention. The implementation package is intentionally named **ext.provider.internal** as a reminder that host code should not depend on it directly; the word "internal" is merely a naming convention, while actual encapsulation is enforced by **module-info.java**.

### 6.2. Module Containing the Public SPI

**src/ext.api/module-info.java**

~~~java
module ext.api {
    exports ext.api;
}
~~~

**src/ext.api/ext/api/Greeting.java**

~~~java
package ext.api;

public interface Greeting {
    String greet(String name);
}
~~~

`ext.api` exports only the required interface. Other types not belonging to the contract can be placed in another package and left unexported.

### 6.3. Provider Module Registering the Service While Hiding the Implementation Package

**src/ext.provider/module-info.java**

~~~java
module ext.provider {
    requires ext.api;

    provides ext.api.Greeting
        with ext.provider.internal.GreetingImpl;
}
~~~

**src/ext.provider/ext/provider/internal/GreetingImpl.java**

~~~java
package ext.provider.internal;

import ext.api.Greeting;

public final class GreetingImpl implements Greeting {
    public GreetingImpl() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Notice there is **no** `exports` or `opens` line for `ext.provider.internal`. `GreetingImpl` remains public and has a public no-arg constructor; this serves ServiceLoader's provider constructor mechanism and does not turn the package into an API for the host.

### 6.4. Application Module Depending Only on the SPI

**src/ext.app/module-info.java**

~~~java
module ext.app {
    requires ext.api;
    uses ext.api.Greeting;
}
~~~

**src/ext.app/ext/app/Main.java**

~~~java
package ext.app;

import ext.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        int count = 0;

        for (Greeting service : ServiceLoader.load(Greeting.class)) {
            System.out.println("Service: " + service.greet("Java"));
            System.out.println("Provider module: " +
                    service.getClass().getModule().getName());
            System.out.println("Provider package exported: " +
                    service.getClass().getModule().isExported(
                            "ext.provider.internal", Main.class.getModule()));
            System.out.println("Provider package open: " +
                    service.getClass().getModule().isOpen(
                            "ext.provider.internal", Main.class.getModule()));
            count++;
        }

        System.out.println("Providers: " + count);
    }
}
~~~

`Main` does not import `GreetingImpl`. It only knows **Greeting** and `ServiceLoader`. After receiving the object, `Main` can invoke methods on the `Greeting` interface. Calling **getClass()** and **getModule()** lets you observe runtime descriptor metadata; it does not grant permission to import or directly access private members of the implementation.

### 6.5. Compiling and Running

Run from the **demo/** directory created with the structure above. The following command compiles all three modules in a single invocation; `javac` will create the **mods** directory:

~~~bash
javac --release 17 --module-source-path src -d mods -m ext.api,ext.provider,ext.app
~~~

Launch the application with the **module path**. In this example, **--add-modules ext.provider** ensures the provider module is resolved at runtime, while **-m ext.app/ext.app.Main** specifies the module and main class:

~~~bash
java --module-path mods --add-modules ext.provider -m ext.app/ext.app.Main
~~~

Both commands above work on Windows, Linux, and macOS terminals when the JDK is on `PATH`; there is no OS-dependent classpath separator because **mods** is a single module-path entry.

**Exact standard output:**

~~~text
Service: Hello, Java!
Provider module: ext.provider
Provider package exported: false
Provider package open: false
Providers: 1
~~~

Interpreting the output:

1. **Service: Hello, Java!** shows that the host received and used an object implementing `Greeting`, even without importing the implementation class.
2. **Provider module: ext.provider** confirms the actual instance comes from the named provider module.
3. **Provider package exported: false** proves `ext.provider.internal` is not exported to module `ext.app`.
4. **Provider package open: false** proves the package is also not opened for deep reflection by `ext.app`.
5. **Providers: 1** because the example declares only one provider for `Greeting`.

This is the key verification: **ServiceLoader still instantiates the provider successfully while the implementation package is neither exported nor open**.

The `--add-modules` flag in the example makes provider resolution explicit. In JPMS configurations that support service binding, a provider can be brought into the module graph via service resolution without this flag; however, do not rely on an implicit assumption when moving to a custom `ModuleLayer`, a custom-packaged runtime image, or a different launch environment.

## 7. Why Does `app` Need `uses` Without Needing `requires provider`?

**uses ext.api.Greeting** belongs to the **module containing the code that calls ServiceLoader**. In the example, `Main` calls `ServiceLoader.load(Greeting.class)` directly, so **ext.app** declares `uses`.

If all ServiceLoader logic is moved into a standalone library/module, that module making the call must have `uses` per the Java contract; `uses` is not automatically inferred for another module merely because it calls the library.

**requires ext.api** is still required because `ext.app` directly references `Greeting` in source code. However, **requires ext.provider** is not needed to iterate over providers. Adding `requires ext.provider` creates an unwanted module dependency; even if the app could read the provider module, it still could not import `ext.provider.internal` because that package is not exported.

This is the advantage of service binding: the consumer depends on the **contract**, not on implementation names. The provider module can be swapped or additional providers can be added. Provider count and order should not be treated as a business contract if the system does not fully control discovery configuration/sources.

**When no provider is found**, ServiceLoader may iterate over zero elements without throwing an error. Distinguish this from a provider that is declared but has a configuration or instantiation error, which is typically reported via **ServiceConfigurationError** during iteration. Depending on the application, the host must decide whether having no provider is a fatal error or a situation where a fallback can be used.

## 8. Provider Constructor and Provider Method: Two Instantiation Paths for Named Modules

For an **explicit named module** declaring **provides ... with ...**, Java 17 supports two ways to create a provider:

| Creation Mechanism | Requirements | Type Listed After `with` |
| --- | --- | --- |
| **Provider constructor** | Public, concrete provider type assignable to the SPI, with a **public no-arg** constructor | The implementation class itself or a subclass of the SPI |
| **Provider method** | Public provider type with a no-arg **public static provider()** method whose return type is assignable to the SPI | Can be a factory class that does not implement the SPI |

The example in Section 6 uses the **provider constructor** path. An alternative design can use a factory to control object creation and keep the concrete implementation package-private.

**Alternative example in module `ext.provider`** (illustrative code; do not use simultaneously with Section 6's provider configuration):

The provider module's **module-info.java** changes to:

~~~java
module ext.provider {
    requires ext.api;

    provides ext.api.Greeting
        with ext.provider.internal.GreetingFactory;
}
~~~

**ext/provider/internal/GreetingFactory.java** inside the provider module:

~~~java
package ext.provider.internal;

import ext.api.Greeting;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static Greeting provider() {
        return new InternalGreeting();
    }
}

final class InternalGreeting implements Greeting {
    @Override
    public String greet(String name) {
        return "Factory: " + name;
    }
}
~~~

The factory type **GreetingFactory** is public and resides in the provider module, yet it is not a subtype of `Greeting` and needs no public no-arg constructor. ServiceLoader for an explicit named module invokes **public static provider()** and receives an object implementing `Greeting`. **InternalGreeting** can even be package-private and does not need to appear in the `provides` clause. The package containing both can still remain unexported and unopened.

This is **an alternative**, not a mandatory requirement for every provider. When the same provider type has a valid provider method, ServiceLoader prioritizes the method path under named-module rules. If `provider()` returns `null` or throws an exception, iterating providers can result in `ServiceConfigurationError`.

**Important limitation:** the provider method cannot be used as a constructor substitute for providers configured via **META-INF/services on the classpath** or providers in an **automatic module**. Those cases still require a provider class assignable to the service with a matching provider constructor. Do not mix rules across the two deployment models.

## 9. What Benefits Does Keeping Internal Packages Encapsulated Provide?

A provider module often contains details that change frequently: algorithms, caches, configuration, connections, adapters, factories, and helper classes. If the implementation package is exported, external modules can import its public types and begin depending on structures never meant to be stable.

Keeping packages unexported yields practical benefits:

- **Reduced coupling:** the host compiles only against `ext.api.Greeting`, so replacing `GreetingImpl` does not force changes to host source code.
- **Freedom to refactor:** implementation packages/classes can be renamed (while updating `provides`), provided the published contract and behavior remain compatible.
- **Smaller API surface:** module users do not accidentally treat internal constructors or helper classes as public API.
- **Separation of contract from instantiation strategy:** a factory can change how implementations are chosen while callers still receive a valid `Greeting`.
- **Early detection of invalid dependencies:** the compiler flags imports from unexported packages instead of letting implementation refactors break the host later.

Encapsulation does not mean completely hiding **class names**, **bytecode**, or **logic** from someone who can read the artifact. The module descriptor contains `provides` metadata; the runtime can reveal the class and module names. This is a mechanism for access control and maintaining API boundaries, **not a sandbox for untrusted plugins**.

## 10. Distinguishing Classpath SPI from JPMS Named Modules

| Topic | Provider JAR on Classpath | Explicit Named Module on Module Path |
| --- | --- | --- |
| Where service is registered | **META-INF/services/<binary-service-name>** file | **provides <Service> with <Provider>** in `module-info.java` |
| Consumer declares `uses` | No `module-info.java` in unnamed module | Module containing `ServiceLoader` call must declare **uses** |
| Instantiation path | Public no-arg provider constructor | Provider constructor or valid `public static provider()` |
| Implementation package protection | No `exports`/`opens` mechanism of named modules | Can leave implementation package unexported and unopened |
| Compile-time dependencies | Classpath and Java access rules | `requires` + readability + `exports` on API module |
| Provider discovery | ServiceLoader reads service configuration resources | ServiceLoader uses module descriptor/module graph metadata |

For **automatic modules** (ordinary JARs placed on the module path so JPMS derives a module), the rules differ from explicit named modules in several ways. Do not take the `static provider()` mechanism of explicit named modules and assume it works with automatic modules. If you want encapsulation and explicit `provides` declarations, use a real `module-info.java` and verify the output artifact's module descriptor.

With named modules, you **do not need to create `META-INF/services`** merely to register a provider already declared in `provides`; avoid maintaining two inconsistent registration sources. If a provider class in a named module also appears in a service configuration file, ServiceLoader has specific rules to avoid duplicate classpath-style processing.

## 11. Compilation Rules and Common Error Handling

### 11.1. Conditions for a Valid `provides`

In an explicit named module:

1. The specified service must be a suitable type accessible to the provider module.
2. Each provider type must be a **public top-level or public static nested type** declared within **the same module containing `provides`**.
3. If there is no provider method, the provider must be a subtype of the service and have a public no-arg constructor.
4. If there is a provider method, it must be a no-arg public static **provider()** method with a return type assignable to the service.
5. The module containing the `ServiceLoader` call must declare `uses` for the service; other modules only need `requires` to use public types according to their accessibility.
6. If the provider requires external classes/libraries, those dependencies must still be present and valid on the module path/runtime according to actual module relationships.

Violations of `provides` constraints may be caught by the compiler; other errors such as constructors/provider() throwing exceptions, missing dependencies, or unresolved modules only surface at runtime.

### 11.2. Diagnostic Table

| Symptom | Common Cause | How to Address |
| --- | --- | --- |
| No providers found | `ext.provider` not resolved, missing `provides`, wrong service/module layer | Check module path, module graph, and `provides`; for the demo use `--add-modules ext.provider` |
| Compiler reports implementation package not visible | Host imports provider from an unexported package | Follow the design: remove the implementation import, use the interface and ServiceLoader |
| Compiler reports service/provider not accessible | Missing `requires`/`exports` for service, wrong or non-public provider type | Check API module and `provides` rules |
| `ServiceConfigurationError` during iteration | Provider missing valid constructor/method, wrong return type, constructor/method throws error, missing dependency | Check the cause, verify type/constructor/factory and runtime module graph |
| Host calls ServiceLoader from named module without `uses` | Missing **uses <Service>** in calling module | Add `uses` to the exact caller module |
| Reflection into implementation fails | Package is not exported/opened to caller | Use SPI; only open packages when there is a clearly designed reflection requirement |
| Provider class exists but service is not discovered | Wrong loading path or module layer, `provides` declared in wrong module | Inspect resolved modules and the layer used in ServiceLoader |
| Provider artifact updated but old result persists | Old loader/layer or ServiceLoader cache still in use | Manage lifecycle, create new layer/loader, and reload appropriately |

**ServiceLoader loads providers lazily.** `ServiceConfigurationError` can arise in `Iterator.hasNext()`, `Iterator.next()`, `Stream`, or `Provider.get()` depending on when discovery/instantiation occurs. Catch errors at the discovery management layer to attach provider/service context rather than scattering `catch(Throwable)` throughout business code.

To inspect registration from compiled artifacts, you can use:

~~~bash
java --describe-module ext.provider --module-path mods
~~~

The command above illustrates inspecting the module descriptor; depending on how the JVM is invoked, you can write **java --module-path mods --describe-module ext.provider** to ensure options are parsed properly. The module descriptor output helps verify whether `provides` names the right service and provider type. Do not use the mere presence of a `.class` file as proof of SPI registration.

### 11.3. Runtime Module Graph and Module Layers

Placing a JAR/exploded module on the module path **does not guarantee that the module has been resolved and participates in the active layer**. For the simple example, **--add-modules ext.provider** solves this explicitly. In service-binding configurations, JPMS may also add provider modules when resolving service dependencies; launch mode, module graph, custom `ModuleLayer`, or runtime images can affect the result.

When a host loads plugins in a separate **ModuleLayer**, consider **ServiceLoader.load(layer, Greeting.class)** to discover providers in that layer and its parent layers per the API contract, rather than assuming `ServiceLoader.load(Greeting.class)` searches the right place. Designing custom `ModuleLayer` initialization is a broader topic; this lesson only requires understanding that **provides** must be paired with proper layer/visibility configuration.

Do not add **requires ext.provider** to the application module just because the provider is on the module path. That direct relationship forfeits the provider-swapping benefit that service abstraction provides.

## 12. Testing Encapsulation

A minimal test suite should include both **positive** checks (SPI still works) and **negative** checks (cannot access implementations as APIs):

| Test Case | Expected Result |
| --- | --- |
| Compile the three modules with `--release 17` | Succeeds; no need to export implementation |
| Run `ext.app` with `ext.provider` resolved | ServiceLoader instantiates provider and runs `Greeting.greet` |
| Check `isExported` for `ext.provider.internal` from `ext.app` | `false` |
| Check `isOpen` for `ext.provider.internal` from `ext.app` | `false` |
| Add `import ext.provider.internal.GreetingImpl` in host | Invalid across module boundary when package is unexported |
| Remove `uses` in `ext.app` while still calling ServiceLoader | Caller module lacks `uses` permission; service loading error |
| Change `provides` to wrong provider name or incompatible type | Compile-time error or appropriate registration failure |
| Provider constructor/`provider()` throws an exception | Observe `ServiceConfigurationError` during instantiation |
| Swap in another provider module implementing the same `Greeting` | Host keeps its source code unchanged; discovery is reconfigured |
| Run via a custom `ModuleLayer` | Provider found in the right layer as configured |

In CI, run the example on **real named modules** instead of dumping all `.class` files onto the classpath. If unit tests only run in the unnamed module, they may miss a forgotten `uses`, an accidentally exported implementation package, or incorrect module resolution.

Check the `exports`/`opens` list in module descriptors after building artifacts: a build or `module-info.java` change can inadvertently expose internal packages even while functional tests still pass.

## 13. Design Checklist Before Publishing a Provider Module

- The API module exports **only the contract packages** for consumers/providers.
- The provider module declares **requires API** and **provides Service with Provider** with the exact binary types.
- The provider class resides **within the provider module itself**, is public, and has a valid provider constructor or provider method.
- The implementation package **is neither exported nor opened** unless there is a specific external access requirement.
- The consumer module **requires API**, **uses Service** where ServiceLoader is called, and has no compile-time dependency on the implementation module.
- Runtime configures the module path, module resolution, and module layer appropriately; never treat "JAR is present" as "module is used."
- Test that **ServiceLoader works** while verifying **isExported/isOpen is false** for the implementation package.
- Handle missing providers, multiple providers, or faulty providers with a clear policy; do not rely on arbitrary order.
- Distinguish explicit named modules, automatic modules, and classpath providers before applying constructor/factory rules.

**Key takeaway:** **provides ... with ...** is how a module publishes a provider to **ServiceLoader**, not a command to export implementation classes. Keep interfaces/DTOs in exported API packages, and implementation classes in packages that are **neither exported nor open**; the host calls through SPI, and JPMS enforces encapsulation boundaries while still supporting runtime extensibility.

Official documentation references for Java 17:

- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
