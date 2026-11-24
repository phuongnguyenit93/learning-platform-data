# Provider Method Limitations for Automatic Modules and Classpath

## 1. The Distinction to Make

In the Java Platform Module System (JPMS), `ServiceLoader` can locate services and create service provider objects across multiple packaging formats. A common source of confusion is **`public static provider()`**: this method can be invoked by `ServiceLoader` to create a service in an **explicit named module**, yet it is **not supported by `ServiceLoader` as a provider factory mechanism for automatic modules or providers on the classpath**.

Consider two provider styles:

~~~java
// Illustrative snippet: Greeter is the service interface.
public final class DirectGreeter implements Greeter {
    public DirectGreeter() { }
    @Override public String greet() { return "direct"; }
}
~~~

~~~java
// Illustrative snippet: FactoryGreeter does not implement Greeter.
public final class FactoryGreeter {
    private FactoryGreeter() { }
    public static Greeter provider() {
        return () -> "factory";
    }
}
~~~

The first class is instantiated via a **public no-arg constructor**. The second class has a no-arg **`public static provider()`** returning `Greeter`, so it can be listed in **`provides ... with ...`** of an explicit named module even though `FactoryGreeter` itself does not implement `Greeter`. However, if you simply write `FactoryGreeter` into a **`META-INF/services`** file on the classpath, or place a legacy JAR containing that registration on the module path as an automatic module, `ServiceLoader` **will not switch to calling `provider()`**; it requires a provider class directly compatible with the service that has a provider constructor.

This is a rule about **provider deployment mechanisms**, separate from the fact that an application can call any static factory method directly through normal Java code. Merely having a method named `provider()` does not make `ServiceLoader` recognize it in every mode.

This lesson explains the three deployment environments, provider registration paths, actual `ServiceLoader` behavior, a runnable Java 17 example, and how to design a compatible SPI when migrating from the classpath to JPMS.

## 2. Three Deployment Environments Are Not Identical

| Environment | How Is the JAR/Module Identified? | Provider Declaration for ServiceLoader | Supported Instantiation Mechanism |
|---|---|---|---|
| **Classpath / unnamed module** | Classes reside on the classpath, belonging to the class loader's unnamed module | File **`META-INF/services/<binary.name.of.Service>`** | Provider class must be assignable to the service and have a **public no-arg constructor** |
| **Automatic module** | JAR **without `module-info.class`**, placed on the **module path** and resolved as an automatic named module | **`META-INF/services`** files can be mapped into `provides` entries in the derived module descriptor | Must also have a **provider constructor**; **provider method is not supported** |
| **Explicit named module** | Module has **`module-info.class`** with an explicit module descriptor | **`provides Service with ProviderClass`** directive in **`module-info.java`** | No-arg **`public static provider()`** returning a valid service type, **or** if no provider method exists, a public no-arg constructor |

**Remember two independent axes:**

1. **Where is the JAR placed?** The classpath puts classes in an unnamed module; the module path can turn a legacy JAR into an automatic module if resolved; a modular JAR with `module-info.class` is an explicit named module.
2. **How does `ServiceLoader` create instances?** Classpath and automatic modules use the **constructor route**; explicit named modules can use the **provider-method route**.

An automatic module is a **named module**, but it is not an **explicit named module**. It exists to ease migrating legacy libraries onto the module path. Being a named module, having a module name derived or set via the **`Automatic-Module-Name`** manifest attribute, and having `ServiceLoader` read service metadata do not grant an automatic module the right to use a provider factory method.

Example with **`greeter-plugin.jar`** lacking `module-info.class`:

~~~text
java -cp greeter-plugin.jar ...
    -> classpath / unnamed module

java --module-path greeter-plugin.jar --add-modules greeter.plugin ...
    -> automatic module named greeter.plugin

# When packaged with module-info.class containing provides:
java --module-path mods --add-modules greeter.plugin ...
    -> explicit named module
~~~

The lines above only illustrate the modes; the full runnable program is in Section 6.

## 3. `ServiceLoader` Rules for Explicit Named Modules

Suppose a module declares:

~~~java
// module-info.java: illustrative snippet
module greeting.plugin {
    requires greeting.spi;
    provides greeting.spi.Greeter
        with greeting.impl.FactoryGreeter;
}
~~~

When looking up providers, `ServiceLoader` knows the module declared `FactoryGreeter` as a provider for `Greeter`. The provider class inside the module can supply a **provider method**:

~~~java
// Illustrative snippet: class in module greeting.plugin.
package greeting.impl;

import greeting.spi.Greeter;

public final class FactoryGreeter {
    private FactoryGreeter() { }

    public static Greeter provider() {
        return () -> "Xin chào từ factory";
    }
}
~~~

Requirements to remember for a **provider method**:

- The method name must be exactly **`provider`**.
- The method must be **`public static`** and **accept no parameters**.
- The declared return type must be assignable to the **service type**; for example, `Greeter` or a subtype of `Greeter`.
- The class listed after **`with`** is a provider class belonging to the declaring module itself. That class **does not have to implement `Greeter`**, because the result returned by `provider()` is the service instance.
- If the provider class has a valid provider method, `ServiceLoader` will **invoke the provider method** to obtain the instance; the provider class's constructor is not the service creation path in this case.
- If the provider class has no provider method, it must be a subtype of the service and have a **public no-arg constructor** for `ServiceLoader` to instantiate directly.
- The `provider()` method may return **`null`** or throw an error at runtime; this is a configuration/service-creation failure, typically reported by `ServiceLoader` via **`ServiceConfigurationError`**.

The two branches can be illustrated as:

~~~text
Explicit named module:
  module-info: provides Greeter with ProviderClass
                         |
                         v
             Does ProviderClass have
             public static provider()?
                  /           \
                Yes            No
                |               |
      Invoke provider()     Check subtype
      to get Greeter        and public no-arg ctor
                |               |
             Greeter        new ProviderClass()
~~~

**Note:** This is a logic diagram of the rule; `ServiceLoader` also performs discovery, loading, module/class validation, and error reporting when configuration is invalid.

A static method named `provider()` does not mean the entire static factory pattern is restricted. Applications can still write **`Factory.create(...)`** and call it directly in any environment. The rule only governs **the entry point that `java.util.ServiceLoader` uses automatically**.

## 4. Why Don't Automatic Modules Use `provider()`?

An automatic module is derived from a legacy JAR on the module path, **without an explicit `module-info.class`**. It might contain:

~~~text
legacy-greeter.jar
├── example/impl/LegacyGreeter.class
└── META-INF/services/example.spi.Greeter
~~~

Where **`META-INF/services/example.spi.Greeter`** lists:

~~~text
example.impl.LegacyGreeter
~~~

When the module path tooling derives a descriptor for an automatic module, entries in `services` files can be translated into **`provides`** directives in the derived descriptor. However, `ServiceLoader` specifies that **an automatic-module provider must have a provider constructor**, meaning a **public no-arg constructor**. There is no branch to call `static provider()` in this deployment style.

Therefore:

- An automatic module is still discovered by `ServiceLoader` through its derived service metadata.
- The provider class must **implement/extend the service** and must have a **public no-arg constructor**.
- If the provider class only has `static provider()` without implementing the service or lacking a valid constructor, it is not a valid provider for an automatic module.
- Moving a legacy JAR onto the module path and setting **`Automatic-Module-Name`** in the manifest only gives it a more stable module name—it **does not turn it into an explicit named module**, nor does it enable factory method support.
- To use `ServiceLoader`'s factory branch, you must provide a proper explicit module descriptor and declare **`provides ... with ...`** for the provider.

**Watch out for a configuration difference:** on the classpath, a service file can list a provider residing in another JAR as long as the class loader finds the class. When deriving an automatic module, service declarations inside the JAR must be valid for the generated module, where listed providers belong to that module; incorrectly copied service file data after shading/relocation can cause module descriptor derivation to fail early. Inspect JAR contents and run **`jar --describe-module`** before relying on an automatic module.

## 5. Why Don't Classpath Providers Use `provider()`?

When a provider sits on the classpath, `ServiceLoader` reads resources by convention:

~~~text
META-INF/services/example.spi.Greeter
~~~

Its contents are **binary names of provider classes** one per line, for example:

~~~text
example.impl.DirectGreeter
example.impl.AnotherGreeter
~~~

The file must be saved in **UTF-8** encoding. `ServiceLoader` loads each class by name, verifies that it is assignable to the service type and has a **public no-arg constructor**, and instantiates it when needed. It does not treat a name in the service file as a factory class with `static provider()`.

A class that implements `Greeter`, has a public no-arg constructor, and also happens to have `public static provider()` can still be a valid classpath provider; however, `ServiceLoader` **calls the constructor** and does not pick the method.

Comparison:

~~~java
// Illustrative snippet: both mechanisms exist.
public final class DualGreeter implements Greeter {
    public DualGreeter() {
        System.out.println("CONSTRUCTOR");
    }

    @Override
    public String greet() {
        return "direct";
    }

    public static Greeter provider() {
        System.out.println("PROVIDER_METHOD");
        return () -> "factory";
    }
}
~~~

In a **classpath/automatic module**, if this class is properly registered, `ServiceLoader` instantiates it via **`DualGreeter()`**; in an **explicit named module with `provides ... with DualGreeter`**, `ServiceLoader` can use **`provider()`**. The standalone runnable example in Section 6 verifies this exact difference.

**Do not confuse:** **`META-INF/services`** is metadata identifying a *provider class*. It has no syntax to point to a method or pass parameters to `provider()`. Appending **`#provider`** to a class name or writing **`Class::provider`** in a service file does not make it a valid method reference.

## 6. Runnable Java 17 Example: Same Provider, Three Deployment Modes

This example uses **the same `Greeter` interface**, **the same `DualGreeter` class**, and **the same host `App`** to compare:

1. JAR on the **classpath** → constructor.
2. Legacy JAR on the **module path** as an **automatic module** → constructor.
3. Provider compiled as an **explicit named module** with **`provides ... with ...`** → `static provider()`.

All output uses ASCII so results do not depend on console encoding.

### 6.1. Source Tree

Create the structure:

~~~text
service-modes/
├── spi/
│   └── src/demo/spi/Greeter.java
├── plugin/
│   ├── src/demo/impl/DualGreeter.java
│   └── resources/META-INF/services/demo.spi.Greeter
├── host/
│   └── src/demo/host/App.java
└── modules/
    ├── demo.spi/module-info.java
    ├── demo.plugin/module-info.java
    └── demo.host/module-info.java
~~~

All three modes reuse the same three regular Java files. Only **the packaging and module descriptors** change.

### 6.2. Service Contract

**spi/src/demo/spi/Greeter.java**

~~~java
package demo.spi;

public interface Greeter {
    String message();
}
~~~

The interface belongs to the shared API, compiled identically for both host and plugin. In the classpath example, it sits on the classpath; in the named modules example, it belongs to **`demo.spi`** and is exported.

### 6.3. Provider Having Both Constructor and `static provider()`

**plugin/src/demo/impl/DualGreeter.java**

~~~java
package demo.impl;

import demo.spi.Greeter;

public final class DualGreeter implements Greeter {
    public DualGreeter() {
        System.out.println("CONSTRUCTOR");
    }

    @Override
    public String message() {
        return "direct";
    }

    public static Greeter provider() {
        System.out.println("PROVIDER_METHOD");
        return () -> "factory";
    }
}
~~~

The provider is deliberately designed to be valid for both the **constructor route** and the **provider-method route**. The constructor prints **`CONSTRUCTOR`**; the method prints **`PROVIDER_METHOD`**. The message values also differ to prove which branch produced the received instance.

Note that the return type of `provider()` is **`Greeter`**. In an explicit named module, **`Provider.type()`** will return that declared type, not necessarily **`DualGreeter.class`**.

### 6.4. Host Using `ServiceLoader` and Printing the Provider Type

**host/src/demo/host/App.java**

~~~java
package demo.host;

import demo.spi.Greeter;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        ServiceLoader<Greeter> loader =
                ServiceLoader.load(Greeter.class);

        ServiceLoader.Provider<Greeter> descriptor = loader.stream()
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No Greeter provider"));

        System.out.println("type=" + descriptor.type().getSimpleName());

        Greeter greeter = descriptor.get();
        System.out.println("value=" + greeter.message());
    }
}
~~~

Calling **`descriptor.type()`** only inspects the type advertised by `ServiceLoader` without instantiating the service. **`descriptor.get()`** is what triggers the instantiation branch.

The example assumes the environment has exactly one `Greeter` provider published by this project; when multiple providers are visible, avoid using **`findFirst()`** as a critical provider-selection policy without explicit criteria.

### 6.5. Service File for Classpath and Automatic Module

**plugin/resources/META-INF/services/demo.spi.Greeter**

~~~text
demo.impl.DualGreeter
~~~

The filename is **`demo.spi.Greeter`**, matching the service's exact fully qualified binary name. Its content is the implementation class name. The legacy JAR built in the next step **does not contain `module-info.class`**.

### 6.6. Compiling the Legacy JAR and Host

Run the commands below from the **`service-modes`** directory on JDK 17 or later.

Linux/macOS (bash):

~~~bash
mkdir -p build/api build/plugin build/host

javac --release 17 -encoding UTF-8 -d build/api \
  spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin \
  plugin/src/demo/impl/DualGreeter.java

cp -R plugin/resources/META-INF build/plugin/

jar --create --file build/demo-plugin.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host \
  host/src/demo/host/App.java
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/api, build/plugin, build/host | Out-Null

javac --release 17 -encoding UTF-8 -d build/api spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin plugin/src/demo/impl/DualGreeter.java

Copy-Item -Recurse -Force plugin/resources/META-INF build/plugin/

jar --create --file build/demo-plugin.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host host/src/demo/host/App.java
~~~

The `jar` command creates **`build/demo-plugin.jar`** containing **`demo/impl/DualGreeter.class`** and the service file **`META-INF/services/demo.spi.Greeter`**. It contains no **`module-info.class`** and does not need to package a duplicate copy of `Greeter.class`.

Inspect the contents:

~~~bash
jar --list --file build/demo-plugin.jar
~~~

The output may also include `META-INF/MANIFEST.MF`, but the two key entries mentioned above should be present. Do not rename the service file to **`demo.impl.DualGreeter.provider`** because `ServiceLoader` expects the class name.

### 6.7. Running on the Classpath

Linux/macOS:

~~~bash
java -cp build/api:build/host:build/demo-plugin.jar demo.host.App
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/host;build/demo-plugin.jar" demo.host.App
~~~

**Stdout:**

~~~text
type=DualGreeter
CONSTRUCTOR
value=direct
~~~

Explanation: classes on the classpath belong to the unnamed module; `ServiceLoader` locates the class via `META-INF/services`, reads the `DualGreeter` class type, and calls **`public DualGreeter()`**. It **does not call** `public static provider()`, so there is no `PROVIDER_METHOD` line.

### 6.8. Running That Same JAR as an Automatic Module

Because **`build/demo-plugin.jar`** does not contain `module-info.class`, placing it on the module path makes it an automatic module. Given the filename **`demo-plugin.jar`**, the derived module name is **`demo.plugin`**.

Linux/macOS:

~~~bash
java --module-path build/demo-plugin.jar \
  --add-modules demo.plugin \
  -cp build/api:build/host \
  demo.host.App
~~~

Windows PowerShell:

~~~powershell
java --module-path build/demo-plugin.jar --add-modules demo.plugin -cp "build/api;build/host" demo.host.App
~~~

**Stdout:**

~~~text
type=DualGreeter
CONSTRUCTOR
value=direct
~~~

This is the key observation: **the module is now a named module**, yet **`ServiceLoader` still uses the constructor**, because automatic modules do not support the provider factory method. The JAR's service file supplies the service description in the automatic module. The host and SPI remain in the unnamed module on the classpath; the automatic module can read the required types under automatic-module rules.

The **`--add-modules demo.plugin`** flag requests resolving the automatic module into the module graph. Simply placing the file on the module path without resolving the module can prevent `ServiceLoader` from seeing the provider as expected. Use **`jar --describe-module --file build/demo-plugin.jar`** to inspect the derived name and descriptor.

### 6.9. Creating Explicit Named Modules

Keeping the interface, provider, and host unchanged, add the following three module descriptors.

**modules/demo.spi/module-info.java**

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

**modules/demo.plugin/module-info.java**

~~~java
module demo.plugin {
    requires demo.spi;
    provides demo.spi.Greeter with demo.impl.DualGreeter;
}
~~~

**modules/demo.host/module-info.java**

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.Greeter;
}
~~~

Here, the provider module declares **`provides ... with ...`**. The host module declares **`uses`**. The host does not declare `requires demo.plugin` because the core only knows the contract and does not need a direct dependency on the implementation module. The plugin module must be resolved at runtime; the command below uses **`--add-modules`** to ensure this.

Recompile into three **exploded named modules**. Linux/macOS (bash):

~~~bash
mkdir -p build/mods/demo.spi build/mods/demo.plugin build/mods/demo.host

javac --release 17 -encoding UTF-8 \
  -d build/mods/demo.spi \
  modules/demo.spi/module-info.java \
  spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.plugin \
  modules/demo.plugin/module-info.java \
  plugin/src/demo/impl/DualGreeter.java

javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.host \
  modules/demo.host/module-info.java \
  host/src/demo/host/App.java

java --module-path build/mods \
  --add-modules demo.plugin \
  --module demo.host/demo.host.App
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/mods/demo.spi, build/mods/demo.plugin, build/mods/demo.host | Out-Null

javac --release 17 -encoding UTF-8 -d build/mods/demo.spi modules/demo.spi/module-info.java spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 --module-path build/mods -d build/mods/demo.plugin modules/demo.plugin/module-info.java plugin/src/demo/impl/DualGreeter.java

javac --release 17 -encoding UTF-8 --module-path build/mods -d build/mods/demo.host modules/demo.host/module-info.java host/src/demo/host/App.java

java --module-path build/mods --add-modules demo.plugin --module demo.host/demo.host.App
~~~

**Stdout of explicit named modules:**

~~~text
type=Greeter
PROVIDER_METHOD
value=factory
~~~

Explanation:

1. Unlike the legacy JAR, **`demo.plugin`** now has **`module-info.class`** and **`provides demo.spi.Greeter with demo.impl.DualGreeter`**.
2. `ServiceLoader` sees a valid **`public static Greeter provider()`** on the provider class, so it uses the provider method. The **`DualGreeter()`** constructor is not called in this branch.
3. **`Provider.type()`** returns **`Greeter`** because that is the **declared return type of `provider()`**; it does not necessarily return `DualGreeter`, nor does it return the runtime class of the lambda.
4. When **`descriptor.get()`** is called, `provider()` prints **`PROVIDER_METHOD`** and returns an instance implementing `Greeter`.
5. The lambda instance's `message()` returns **`factory`**.

This is a comparison over **the exact same Java source**: the difference comes from **how the provider is deployed and its module metadata**, not method names or how the host calls `ServiceLoader`.

### 6.10. Results Comparison Table

| Mode | Registration Path | `Provider.type().getSimpleName()` | How `ServiceLoader` Obtains Instance | `message()` |
|---|---|---|---|---|
| Classpath | `META-INF/services` | `DualGreeter` | public no-arg constructor | `direct` |
| Automatic module | Service metadata derived from `META-INF/services` | `DualGreeter` | public no-arg constructor | `direct` |
| Explicit named module | `provides ... with ...` | `Greeter` | `public static provider()` | `factory` |

If the environment contains additional `Greeter` providers from other JARs/modules, **`findFirst()`** could pick a different provider. Keep the example in a clean environment, or add explicit provider-selection criteria for independent testing.

## 7. Case of a Class Having Only `provider()` and Not Implementing the Service

Suppose the following class is used as a provider:

~~~java
package demo.impl;

import demo.spi.Greeter;

public final class FactoryOnly {
    private FactoryOnly() { }

    public static Greeter provider() {
        return () -> "from-factory";
    }
}
~~~

In an **explicit named module**, change the declaration:

~~~java
module demo.plugin {
    requires demo.spi;
    provides demo.spi.Greeter with demo.impl.FactoryOnly;
}
~~~

This is valid because `FactoryOnly` has a provider method with the right signature, and its return value has type `Greeter`.

On the **classpath**, if **`META-INF/services/demo.spi.Greeter`** lists **`demo.impl.FactoryOnly`**, `ServiceLoader` will not call `provider()`. `FactoryOnly` does not implement `Greeter` and has no matching public constructor, so it is an invalid provider configuration: iteration/loading can throw **`ServiceConfigurationError`**.

For an **automatic module** created from a JAR containing the corresponding service file, this case is also **not supported**. Do not assume that because an automatic module resolves to a named module, `ServiceLoader` will apply explicit-module rules.

**Note:** At compile time, an explicit module can validate the provider method via **`javac`** when reading `module-info.java`. Classpath/automatic setups have no explicit `module-info.java` to represent a factory-only provider, so they require a direct provider class or migration to an explicit module.

## 8. Solution When You Want a Factory While Supporting Classpath/Automatic Modules

An SPI meant to be distributed easily across all three environments typically avoids having `ServiceLoader` invoke `static provider()` itself. Instead, **the service created by `ServiceLoader` is itself a factory with a valid constructor**, and that factory exposes an instance method to create the domain object.

Example:

~~~java
package demo.spi;

// Illustrative snippet of a service factory contract.
public interface GreeterFactory {
    String id();
    Greeter create(String prefix);
}
~~~

~~~java
package demo.impl;

import demo.spi.Greeter;
import demo.spi.GreeterFactory;

// Illustrative snippet of a provider usable for classpath/automatic.
public final class DefaultGreeterFactory implements GreeterFactory {
    public DefaultGreeterFactory() { }

    @Override
    public String id() {
        return "default";
    }

    @Override
    public Greeter create(String prefix) {
        return () -> prefix + " Java";
    }
}
~~~

The host will do:

~~~java
// Illustrative snippet, not a standalone Java program.
GreeterFactory factory = ServiceLoader.load(GreeterFactory.class)
        .findFirst()
        .orElseThrow();

Greeter greeter = factory.create("Hello");
System.out.println(greeter.message());
~~~

**Stdout of the snippet above**, assuming `Greeter` has a `message()` method as in the main example and `DefaultGreeterFactory` is the sole provider:

~~~text
Hello Java
~~~

Mechanism:

- **Classpath:** `ServiceLoader` calls **`DefaultGreeterFactory()`** via the service file `META-INF/services/demo.spi.GreeterFactory`.
- **Automatic module:** also calls the **public no-arg constructor**, using service metadata inside the JAR.
- **Explicit named module:** can declare **`provides demo.spi.GreeterFactory with demo.impl.DefaultGreeterFactory`**, still using the constructor as long as there is no valid `static provider()` in the class.
- **Parameterized object creation** belongs to the **`create(prefix)`** instance method of the factory service, after the host has obtained the factory.

A factory service can manage configuration, caches, dependencies, and lifecycles under its own contract; domain object construction is no longer constrained by `ServiceLoader`'s **no-arg `public static provider()`** signature.

**Do not confuse the two uses of "factory":** a **provider method** is `ServiceLoader`'s special instantiation protocol for explicit named modules; a **factory service** is an application-defined design pattern that works regardless of module mode.

## 9. Common Mistakes and Misconceptions

### 9.1. "An automatic module is a named module, so `provider()` must work"

False. An automatic module has a name and is resolved in the module graph, but `ServiceLoader` **specifically requires** that an automatic-module provider have a **provider constructor**. If you need `static provider()` as the `ServiceLoader` entry point, compile an **explicit named module** with the corresponding `provides` directive.

### 9.2. "Just add `Automatic-Module-Name` in the manifest"

False. The **`Automatic-Module-Name`** manifest attribute gives a JAR without `module-info.class` a more stable module name. It **does not generate an explicit module descriptor** with author-written `uses`/`provides`, and it does not unlock the provider method mechanism.

### 9.3. "Moving the JAR to the module path while keeping the services file is enough to invoke the factory"

False. A service file can be used to identify providers for an automatic module, yet the service file itself only lists **class names**, not provider methods. To use `provider()` under JPMS, you need an explicit named module and **`provides ... with ...`**; the provider class in that module must declare the valid method.

### 9.4. "A class listed in the service file only needs `static provider()`"

False on the classpath and in automatic modules. The provider class must be **assignable to the service** and have a **public no-arg constructor**. A factory-only class lacking these traits prevents `ServiceLoader` from obtaining the service and can throw **`ServiceConfigurationError`**.

### 9.5. "`ServiceLoader.Provider.type()` is always the class listed after `with`"

Not true for a provider method. If an explicit named module uses **`public static Greeter provider()`**, **`Provider.type()`** returns **`Greeter.class`** per the return type signature, not the factory class. If the host tries to filter providers by annotations on the factory class, filtering based on `type()` will fail; publish explicit metadata or use a factory service/registry instead.

### 9.6. "Use `static provider(String config)` for `ServiceLoader` to pass configuration"

Not supported: **`ServiceLoader`'s provider method takes no parameters**. Methods named `provider` that take parameters are not recognized provider entry points. When dynamic configuration is needed, use a **service factory with a `create(config)` method**, a DI container, or another explicit initialization protocol.

### 9.7. "Once `module-info.java` exists, there's no need to declare `uses`"

An **explicit consumer module** using `ServiceLoader` must declare **`uses`** for the service in `module-info.java` per the API contract. The provider module declares `provides`; the application should not hard-couple to the implementation module via `requires` unless there is a specific reason. If the provider module is not resolved, `ServiceLoader` may still find no providers even if the module JAR sits on the module path.

### 9.8. "No provider was found, so the `provider()` code must be wrong"

Insufficient evidence. Inspect each layer properly: classpath/module path mode, module descriptors, service files, module names, whether the module was resolved, visibility of the provider class, type assignability, constructor/method access, class loader, and underlying cause. **No provider found** and **misconfigured provider** are two distinct situations.

## 10. Checklist When Migrating an SPI from Classpath to JPMS

1. **Identify the artifact:** a JAR without `module-info.class` on the module path is an automatic module; `Automatic-Module-Name` in the manifest only supplies a module name.
2. **Verify the service file:** named **`META-INF/services/<service binary name>`**, UTF-8 encoded, containing valid provider class names belonging to the intended JAR/module.
3. **Choose the instantiation route:** to run on classpath/automatic modules, the provider must implement the service and have a public no-arg constructor; to have `ServiceLoader` invoke `provider()`, provide an explicit named module.
4. **Write module descriptors:** the explicit provider module declares **`provides Service with ProviderClass`**; the explicit consumer module declares **`uses Service`** and `requires` the API module as needed.
5. **Ensure a valid provider method:** public, static, named `provider`, no parameters, return type assignable to the service; never assume `ServiceLoader` calls this method in automatic/classpath modes.
6. **Keep the API shared:** identical service interface identity/runtime `Class`, compatible API versions, and aligned module resolution/class loaders.
7. **Do not rely on arbitrary provider order:** select based on metadata/IDs or a defined policy; check **`Provider.type()`** behavior when a factory method returns a general interface.
8. **Test at least all three modes:** legacy classpath, automatic module, explicit named module; observe whether the constructor or `provider()` is called, test missing providers, invalid constructors/methods, and inspect the module graph.
9. **Plan a compatibility path:** if all three modes must be supported and initialization requires parameters, prefer a **factory-as-service** with a public no-arg constructor rather than relying on `static provider()`.

## 11. Self-Check Questions

**Question 1.** A JAR has a `META-INF/services` file and a class containing `public static provider()`, but does not implement the service. When placed on the module path as an automatic module, will `ServiceLoader` call `provider()`?

**Answer:** No. Automatic-module providers require a provider constructor and a matching subtype of the service. This factory-only declaration is invalid for an automatic module; convert it to an explicit named module or refactor the service into a factory class that directly implements the contract.

**Question 2.** A class implements the service, has a public no-arg constructor, and also has a valid `public static provider()`. What changes when moving from the classpath to an explicit named module?

**Answer:** On the classpath, `ServiceLoader` invokes the constructor. In an explicit named module with `provides ... with ...` and the valid method, `ServiceLoader` invokes `provider()`. This can change the returned instance and causes **`Provider.type()`** to return the method's declared return type.

**Question 3.** Does setting `Automatic-Module-Name` in `MANIFEST.MF` make `ServiceLoader` use `provider()`?

**Answer:** No. That attribute only stabilizes the automatic module's name. To use `ServiceLoader`'s provider method, an appropriate explicit module descriptor is required.

**Question 4.** Why shouldn't you write method-call syntax after a provider class name in `META-INF/services`?

**Answer:** Service configuration files only list binary names of **provider classes**. `ServiceLoader` has no syntax for invoking methods in that file; the method route is determined by explicit named module configuration and the `provider()` signature.

**Question 5.** You need to pass a prefix and dependencies to create a `Greeter`, yet the plugin must still run on the classpath. How should you design it?

**Answer:** Have `ServiceLoader` instantiate a simple **`GreeterFactory`** with a public no-arg constructor, then let the host call **`factory.create(prefix, dependencies)`** under a custom contract. That is a factory service, not a `ServiceLoader` provider method.

## 12. Standard References and Key Takeaways

- Oracle Java SE 17 API, **ServiceLoader** — sections Developing service providers, Deploying service providers as modules, Deploying service providers on the class path, and Errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17 API, **ServiceLoader.Provider** — semantics of `type()` when a module uses a provider factory method: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 17 **ModuleFinder**, rules for deriving module descriptors from JARs/service metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java Language Specification 17, **§7.7.4 Service Provision**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4
- Dev.java, **Incremental Modularization with Automatic Modules**: https://dev.java/learn/organizing/modules/automatic-module/

**Key takeaway:** `ServiceLoader`'s provider method (**no-arg `public static provider()`**) belongs to the provider declaration mechanism of **explicit named modules**. Providers in **automatic modules or on the classpath** are instantiated by `ServiceLoader` via the **public no-arg constructor** of a class implementing the service. When multi-environment support is needed alongside parameterized object creation, design a **factory as a service** instead of relying on `provider()` in unsupported environments.
