# Migrating a System to Explicit Modules and Discovering Providers in a Child ModuleLayer

## 1. Exercise Objectives

A Java application may start with the **classpath**, loading plugin JARs via **URLClassLoader** and discovering implementations with **ServiceLoader** using **META-INF/services** files. As the system grows, we want clearer module boundaries: the SPI in a public module, the host in its own module, and the plugin implementation inside an **explicit named module** that the host does not need to import. At the same time, the plugin is loaded into a **child ModuleLayer** so versions can be added or replaced without placing every plugin into the JVM boot layer.

This exercise builds an **end-to-end runnable Java 17+ example** consisting of three named modules:

- **lab.api**: contains the shared SPI interface **lab.api.Greeting**.
- **lab.host**: the host application, which uses the SPI and calls **ServiceLoader.load(layer, Greeting.class)**.
- **lab.provider**: the plugin implementing the SPI, declaring its provider with **provides ... with ...** and **without exporting its implementation package**.

We will compile all three modules with javac, package **lab.provider** into a JAR, **place only lab.api and lab.host on the module path to launch the host**, and then have the host construct a child ModuleLayer from the plugin JAR. By the end, you will distinguish **discovery** from **module resolution**, verify the actual runtime classes and modules, handle module graph errors, and understand how to evolve the architecture for plugin upgrades.

Expected outcomes:

1. The plugin **is not in the boot layer**.
2. The host dynamically creates a **child ModuleLayer** containing lab.provider.
3. **ServiceLoader** discovers the implementation from the child layer.
4. The host invokes the SPI successfully without source dependencies on the implementation class.
5. The implementation package **does not need exports or opens** to the host.
6. The SPI interface still uses a **single Class identity** in the parent/boot layer.

**Scope:** This exercise focuses on migration, build/launch steps, and module discovery in a child layer; it does not treat ModuleLayer as a security sandbox or a complete plugin lifecycle management system.

## 2. Before and After Migration

### 2.1. Traditional classpath architecture

~~~text
app.jar + api.jar + provider.jar   (classpath)
  |
  +-- lab.api.Greeting
  +-- lab.provider.internal.SimpleGreeting
  +-- META-INF/services/lab.api.Greeting
  |
  +-- ServiceLoader.load(Greeting.class)
          -> finds provider via service configuration resource
~~~

Provider registration on the classpath typically lives in a text file **META-INF/services/lab.api.Greeting** containing **lab.provider.internal.SimpleGreeting**. The host can use an appropriate ClassLoader to bring the provider JAR into discovery scope.

Limitations of a shared classpath:
- No module descriptor to explicitly specify **requires, exports, uses, provides**.
- Public classes can be imported directly by other consumers even if the author only intended to expose the SPI.
- Dependency JARs can collide across versions on the classpath.
- Dropping a plugin JAR into a directory does not mean the running application class loader sees it.
- Replacing class definitions of an already-loaded plugin still requires managing class loaders, caches, and lifecycle.

**Classpath is not wrong**: for small applications or stable SPIs, ServiceLoader + JARs on the classpath is a reasonable choice. Moving to JPMS is an architectural decision that requires matching build/deployment practices.

### 2.2. Explicit named modules and child layer architecture

~~~text
BOOT LAYER
  lab.api  [exports lab.api]
     ^
     | requires
     |
  lab.host [requires lab.api; uses lab.api.Greeting]
     |
     | 1. ModuleFinder.of(pluginsDirectory)
     | 2. Configuration.resolve(..., root lab.provider)
     | 3. defineModulesWithOneLoader(...)
     v
CHILD MODULE LAYER
  lab.provider
    requires lab.api ---------------> uses API from BOOT LAYER
    provides lab.api.Greeting
       with lab.provider.internal.SimpleGreeting
    [does not export lab.provider.internal]

  ServiceLoader.load(childLayer, Greeting.class)
     -> provider object
     -> host uses via Greeting
~~~

**lab.api** is defined only in the boot layer, not copied into the child layer. lab.provider belongs to the new layer and depends on the API from the parent. Thus, when the host receives a **Greeting** instance from the provider, it shares the exact same interface without needing access to the implementation package.

**Conceptual warning:** A ModuleLayer is a group of resolved named modules along with their class loader mappings. It is neither a directory of JARs nor necessarily a single class loader under every strategy. A ModuleLayer has parent layers; modules in a child can depend on modules in a parent, but the parent does not automatically gain access to import implementations in a child.

## 3. Checklist of Changes When Migrating from Classpath to JPMS

| Concern | Before (classpath) | After (explicit named modules) |
| --- | --- | --- |
| API/SPI | A shared JAR or package | Module **lab.api** with **exports lab.api** |
| Host | Classes using SPI; loader/JAR access depends on design | Module **lab.host** with **requires lab.api** and **uses lab.api.Greeting** |
| Provider registration | **META-INF/services/lab.api.Greeting** | **provides lab.api.Greeting with ...** in module-info.java |
| Provider dependencies | Compile/runtime classpath dependencies | **requires lab.api** and needed module dependencies |
| Implementation visibility | Public classes can be imported if on classpath | Implementation package is not exported or opened |
| Plugin discovery | ServiceLoader using class loader or TCCL | **ServiceLoader.load(childLayer, Greeting.class)** |
| Runtime visibility | JAR visible to the loader | Module **found by finder, resolved, defined** in layer |
| Plugin replacement | Manage JARs and new loaders if classes already loaded | Manage JARs, new layers/loaders, and cutover; no automatic hot swap |
| Error management | ClassNotFoundException, ServiceConfigurationError, and linkage | Also FindException, ResolutionException, LayerInstantiationException, access checks |
| Testing | Classpath-only tests can hide module errors | Compile and run on a **real module path** |

**There is no need to maintain two parallel registration sources** for the same provider just to support explicit modules. For explicit named modules, **provides** is the primary provider declaration. A JAR lacking module-info.class placed on the module path becomes an **automatic module**; automatic modules are not equivalent to explicit modules and do not provide the same encapsulation.

## 4. Preparing the Environment

This example requires:
- **JDK 17 or newer** with **java**, **javac**, and **jar** on PATH.
- Permission to create files in a demo directory.
- A bash terminal on Linux/macOS or PowerShell on Windows.
- No Maven/Gradle and no dependencies outside the JDK.

Verify the toolchain:

~~~bash
java -version
javac -version
jar --version
~~~

**The build target** is Java 17 via **javac --release 17**, even if your local compiler is newer. This flag controls language/class-file/platform API compatibility, while the demo runs in an environment supporting the module system and Java 17 APIs.

Create the following file layout (paths are relative to the **demo** directory):

~~~text
demo/
├── src/
│   ├── lab.api/
│   │   ├── module-info.java
│   │   └── lab/api/Greeting.java
│   ├── lab.provider/
│   │   ├── module-info.java
│   │   └── lab/provider/internal/SimpleGreeting.java
│   └── lab.host/
│       ├── module-info.java
│       └── lab/host/Main.java
├── mods/                    # Generated during compilation
│   ├── lab.api/
│   ├── lab.provider/
│   └── lab.host/
└── plugins/                 # Generated during packaging
    └── lab.provider.jar
~~~

**Directory names under src are module names**, matching **--module-source-path src**. Each module has a **module-info.java** at its module root. The lab.provider.jar file is kept outside the host's startup module path so the plugin is resolved inside the child layer.

## 5. Writing the API Module: lab.api

File **src/lab.api/module-info.java**:

~~~java
module lab.api {
    exports lab.api;
}
~~~

File **src/lab.api/lab/api/Greeting.java**:

~~~java
package lab.api;

public interface Greeting {
    String greet(String name);
}
~~~

Explanation:
- **exports lab.api** grants other modules access to the public types in the API package.
- **Greeting** is the contract shared by both host and providers.
- Keep implementation logic out of lab.api.
- Greeting's versioning and behavioral contract must be published by the platform; modularization does not replace binary compatibility management.

If lab.api has internal implementation/helpers, place them in an unexported package. If the SPI uses DTOs in its signatures, those DTOs and their packages must also be accessible by design.

## 6. Writing the Provider Module: lab.provider

File **src/lab.provider/module-info.java**:

~~~java
module lab.provider {
    requires lab.api;
    provides lab.api.Greeting with lab.provider.internal.SimpleGreeting;
}
~~~

File **src/lab.provider/lab/provider/internal/SimpleGreeting.java**:

~~~java
package lab.provider.internal;

import lab.api.Greeting;

public final class SimpleGreeting implements Greeting {
    public SimpleGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Meaning of the directives:
- **requires lab.api**: allows the provider module to read the module containing the SPI.
- **provides lab.api.Greeting with lab.provider.internal.SimpleGreeting**: provider registration is declared in the **module descriptor**, no longer relying on locating a META-INF/services resource on the classpath.
- **No exports lab.provider.internal**: lab.host code cannot import the implementation class as public API.
- **No opens lab.provider.internal**: does not open the internal package for deep reflection by the host.

The **SimpleGreeting** class remains public and has a **public no-arg constructor**, satisfying the constructor-based provider requirement in an explicit named module. ServiceLoader has built-in support for instantiating providers declared in a module descriptor without requiring the implementation package to be exported to consumers.

**A very common misconception:** "Not exporting a package" and "a non-public provider class" are two separate things. Not exporting a package is a boundary between modules; the class listed directly after **with** must still satisfy provider-type rules. In Java 17, explicit named modules also allow a valid public static **provider()** factory method, though this example intentionally uses a constructor for clarity.

Do not add **exports lab.provider.internal to lab.host** just to make ServiceLoader work; doing so breaks the API boundary we are trying to preserve.

## 7. Writing the Host Module: lab.host

File **src/lab.host/module-info.java**:

~~~java
module lab.host {
    requires lab.api;
    uses lab.api.Greeting;
}
~~~

File **src/lab.host/lab/host/Main.java**:

~~~java
package lab.host;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import lab.api.Greeting;

public final class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Main <plugins-directory>");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration config = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("lab.provider"));
        ModuleLayer child = boot.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        System.out.println("Provider in boot: " +
                boot.findModule("lab.provider").isPresent());
        System.out.println("Provider in child: " +
                child.findModule("lab.provider").isPresent());

        int count = 0;
        for (Greeting provider : ServiceLoader.load(child, Greeting.class)) {
            System.out.println("Provider module: " +
                    provider.getClass().getModule().getName());
            System.out.println("Greeting: " + provider.greet("Java"));
            System.out.println("API in boot layer: " +
                    (Greeting.class.getModule().getLayer() == boot));
            System.out.println("Implementation exported: " +
                    provider.getClass().getModule().isExported(
                            "lab.provider.internal", Main.class.getModule()));
            count++;
        }
        System.out.println("Providers found: " + count);
        if (count == 0) {
            throw new IllegalStateException("No plugin provider discovered");
        }
    }
}
~~~

Step-by-step walkthrough of Main:

1. **ModuleLayer.boot()** retrieves the initial layer containing lab.host, lab.api, and the Java modules resolved at launch.
2. **Path.of(args[0])** retrieves the **plugins** directory path supplied by the caller; here it holds the packaged **lab.provider.jar**.
3. **ModuleFinder.of(Path.of(args[0]))** builds a module finder that locates modular JARs or exploded modules at that path.
4. **boot.configuration().resolve(finder, ModuleFinder.of(), Set.of("lab.provider"))** creates a **new Configuration** with boot as its parent configuration and **lab.provider** as the required root module. Because lab.provider **requires lab.api**, resolution finds lab.api already resolved in the parent configuration.
5. **boot.defineModulesWithOneLoader(config, ClassLoader.getSystemClassLoader())** defines the modules in the new configuration within a child ModuleLayer. This strategy uses **one new class loader for the modules defined in the new layer**, with the supplied parent class loader. It does not move lab.api out of the boot layer.
6. **ServiceLoader.load(child, Greeting.class)** discovers service providers in the child layer and parent layers according to the API rules, returning providers for the host to iterate.
7. The host calls **greet()** through the interface, prints the actual module name, and verifies that the implementation package is not exported to the host.
8. If no provider is found, the host throws IllegalStateException so the exercise fails loudly instead of exiting silently.

**Why does lab.host have uses?** When a module invokes ServiceLoader for a service, declaring **uses lab.api.Greeting** is part of the JPMS contract. **requires lab.api** only lets the host reference the Greeting type; it **does not replace** uses.

**Why does lab.host not require lab.provider?** The host must not create a static dependency on a plugin implementation. The host only requires the API. The provider module is the root chosen by the host when resolving the child layer, so host code never imports or requires the provider module.

**Subtle detail:** **child.findModule("lab.provider")** searches both the child and parent layers; in this example, boot does not have lab.provider, so the two lines "in boot: false" and "in child: true" prove the provider was placed in the new layer. If you need to list only the modules defined directly in the child, use **child.modules()**.

**Security check:** ModuleFinder reads module metadata, which is not a verification of signature, origin, or plugin safety. In production, verify JAR files and permissions before building a layer or instantiating providers.

## 8. Compiling the Three Modules with javac

### 8.1. Standard commands on Linux/macOS

From the **demo** directory (containing src/), run:

~~~bash
mkdir -p plugins
javac --release 17 --module-source-path src -d mods \
  -m lab.api,lab.provider,lab.host
jar --create --file plugins/lab.provider.jar -C mods/lab.provider .
~~~

**javac** uses module-source-path to map directories to module names and generates **module-info.class** along with the class files. **jar** packages lab.provider's compiled output into an explicit modular JAR.

### 8.2. Equivalent commands on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force plugins | Out-Null
javac --release 17 --module-source-path src -d mods -m lab.api,lab.provider,lab.host
jar --create --file plugins/lab.provider.jar -C mods/lab.provider .
~~~

These commands use relative directory separators that Java tools handle on Windows. Note that PowerShell does not use bash's **\\** for line continuation; in the Windows example each javac command is on a single line.

### 8.3. Verify plugin.jar is truly an explicit named module

~~~bash
jar --describe-module --file plugins/lab.provider.jar
~~~

Output may contain machine-specific absolute artifact paths, while the essential parts to verify are:

~~~text
lab.provider
requires java.base mandated
requires lab.api
provides lab.api.Greeting with lab.provider.internal.SimpleGreeting
contains lab.provider.internal
~~~

**lab.provider** must show a descriptor and the **provides** directive. If jar --describe-module reports an **automatic module** or omits provides, inspect your build and the module-info.class inside the JAR instead of assuming everything is modularized.

Because lab.provider.internal is neither exported nor opened, the descriptor typically shows **contains lab.provider.internal** rather than an exports line for that package. This is intentional.

## 9. Launching the Host Without Resolving the Plugin in Boot

This is the **pivotal step** of the exercise. At launch, place only **lab.api** and **lab.host** on **--module-path**; the plugin JAR sits separately in the **plugins** directory for the host's **ModuleFinder** to locate and load into a new layer.

**Linux/macOS:**

~~~bash
java --module-path "mods/lab.api:mods/lab.host" \
  -m lab.host/lab.host.Main plugins
~~~

**Windows PowerShell:**

~~~powershell
java --module-path "mods/lab.api;mods/lab.host" -m lab.host/lab.host.Main plugins
~~~

The separator between module-path entries is **:** on Linux/macOS and **;** on Windows. The **plugins** path is an **argument to Main**, not part of boot's --module-path.

**Exact output of the example:**

~~~text
Provider in boot: false
Provider in child: true
Provider module: lab.provider
Greeting: Hello, Java!
API in boot layer: true
Implementation exported: false
Providers found: 1
~~~

Explanation of each line:
- **Provider in boot: false**: JVM startup did not resolve lab.provider into the boot layer.
- **Provider in child: true**: the host resolved and defined lab.provider in the child layer.
- **Provider module: lab.provider**: the object comes from the plugin's named module, not the classpath/unnamed module.
- **Greeting: Hello, Java!**: the host invokes the lab.api.Greeting interface and gets the result from the implementation.
- **API in boot layer: true**: the SPI comes from the parent/boot layer, with no duplicated API definition in the child.
- **Implementation exported: false**: the provider package is not exported to lab.host, yet ServiceLoader still works.
- **Providers found: 1**: one provider is registered per the example configuration.

**Additional observation:** Output prints no absolute file paths or class loader addresses, as those vary across machines. The print statements intentionally use stable booleans and module names so results can be compared across operating systems.

## 10. Putting the Pieces Together: Who Is Responsible for What?

| Step | API/Mechanism | Who is responsible? |
| --- | --- | --- |
| Publish lab.provider.jar | javac, jar, build pipeline | Provider developer / build system |
| Verify JAR/version/trust | Registry, checksum, policy | Host / deployment pipeline |
| Choose plugins directory | Path and application configuration | Host |
| Locate module artifacts | ModuleFinder.of(...) | Provided by Java API; host picks the path |
| Resolve module graph | Configuration.resolve(...) | Module system; host chooses roots/finder |
| Define layer/loader | ModuleLayer.defineModulesWithOneLoader(...) | Module system per host configuration |
| Discover providers | ServiceLoader.load(child, Greeting.class) | ServiceLoader, given the layer by the host |
| Instantiate provider | Provider constructor or provider method | ServiceLoader when iterated/requested |
| Select plugin by ID/version/policy | Registry and business rules | Host |
| start(), health, handle(), stop() | Application-defined SPI lifecycle | Host |
| Version upgrades and rollback | New layer, routing, cleanup | Host |
| Contain untrusted code | Process/container isolation, permissions | Host / platform |

**ModuleLayer does not replace ServiceLoader**, and ServiceLoader **does not automatically resolve or define a ModuleLayer from a plugins directory**. They are two halves of the workflow: the host builds a valid module graph, then asks ServiceLoader to discover providers within that graph.

## 11. Why Use ModuleFinder, resolve, and define in This Order?

### 11.1. ModuleFinder only discovers available metadata

~~~java
// Illustrative snippet; path is a validated Path.
ModuleFinder finder = ModuleFinder.of(path);
~~~

A finder locates module descriptors in modular JARs, exploded modules, and automatic modules in supported locations. **Finding a JAR** does not mean it has been resolved, its classes loaded, or its providers instantiated. To inspect discoverable module names, you can use **finder.findAll()** according to host validation policies.

A legacy JAR lacking module-info.class placed on the module path may be treated as an automatic module. This exercise requires an explicit module, so inspect the descriptor rather than assuming every name returned by ModuleFinder represents a completed migration.

### 11.2. Configuration.resolve validates dependencies

~~~java
// Illustrative snippet given an existing parent configuration and finder.
Configuration config = parent.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("lab.provider"));
~~~

**Set.of("lab.provider")** specifies the root module to resolve. **requires** dependencies are resolved from the finder and parent configurations according to JPMS rules. If lab.api is missing or a module name is wrong, resolution fails before any provider can be invoked.

In the demo, lab.api is already resolved in boot. This matters for type identity: **do not create a new copy of lab.api in the child if you intend to use the host's Greeting.class from boot**. If a plugin has private dependencies, version resolution must be designed carefully; JPMS is not a Maven/Gradle-style version solver.

**resolve** and **resolveAndBind** are not the same. **resolveAndBind** performs service binding during resolution to pull in modules providing services used according to API rules; the demo uses **resolve** with an explicit provider root for clarity and deterministic results. When multiple plugins or modules use other services, choose the resolution mode that fits your system's requirements.

### 11.3. defineModulesWithOneLoader defines modules and loader

~~~java
// Illustrative snippet; config has already been resolved against parent.
ModuleLayer child = parent.defineModulesWithOneLoader(
        config, ClassLoader.getSystemClassLoader());
~~~

This call defines the modules in config using one new loader paired with the specified parent loader. Since the example has only one new provider module, this is simple enough.

For multiple plugins with conflicting dependencies or differing isolation needs:
- Consider **defineModulesWithManyLoaders** or multiple independent child layers.
- Place shared API/SPI in a parent layer rather than letting a plugin create a separate API with a different identity.
- Carefully review package rules within a module graph and duplicate/split package cases.
- Do not rely on class loaders as a sandbox for untrusted code.
- Test actual class identity and ServiceLoader visibility when adding nested layers.

A ModuleLayer can be garbage-collected once unreachable, but **there is no standard ModuleLayer.close() operation to proactively unload all classes immediately**. Managing plugin lifecycles is the host's responsibility.

## 12. How Does ServiceLoader.load(layer, service) Work?

With JPMS, **ServiceLoader.load(childLayer, Greeting.class)** discovers providers in the child layer and ancestor layers according to the API contract. This has two consequences:

1. **Providers from parent layers can also appear**. Do not assume the result contains only modules defined directly in the child. If you need "only plugins in the child", the host must enforce a filter policy by module/layer/registry.
2. **Providers are declared in the module descriptor** via provides, not by the host importing the implementation class. The provider class can reside in an unexported package.

**Provider discovery and instantiation are usually lazy.** Creating a ServiceLoader does not mean all providers have been instantiated. While iterating or calling Provider.get(), the JDK may load and instantiate them; configuration errors may surface during iteration rather than at ServiceLoader creation.

One way to inspect provider types before obtaining instances is **ServiceLoader.stream()**:

~~~java
// Illustrative Java snippet: child and Greeting are already available.
// Must run inside a module declaring uses lab.api.Greeting.
ServiceLoader<Greeting> services = ServiceLoader.load(child, Greeting.class);
for (ServiceLoader.Provider<Greeting> entry : services.stream().toList()) {
    System.out.println(entry.type().getName());
}
~~~

**type()** lets you inspect the type without immediately invoking the provider constructor; **get()** requests the provider instance. For an explicit module with a valid provider() factory, the type from Provider.type() can be the return type rather than the factory itself. **Do not treat type() as a security audit** of the bytecode.

If you want to accept only providers belonging to the new layer once instantiated:
~~~java
// Illustrative snippet after selecting the right child; not a standalone program.
for (Greeting item : ServiceLoader.load(child, Greeting.class)) {
    if (item.getClass().getModule().getLayer() != child) {
        continue;
    }
    // Host verifies ID, version, contract, and permissions before activation.
}
~~~

The filter above **may have already instantiated the provider before checking**. For untrusted sources, validate artifacts/metadata before resolving or calling ServiceLoader, rather than relying on post-constructor filtering to prevent side effects.

## 13. Why Are uses and provides Different Requirements from requires?

**requires lab.api** in host/provider lets code reference the Greeting type via module readability. **exports lab.api** exposes the public interface to other modules. Neither directive states that host code consumes the service dynamically or that the provider module registers an implementation.

**uses lab.api.Greeting** states that **lab.host** is a consumer of the service. Calling ServiceLoader from a named module must satisfy the uses requirement under JSR 376/JPMS rules.

**provides lab.api.Greeting with lab.provider.internal.SimpleGreeting** states that **lab.provider** supplies an implementation. The **with** target must name a provider type located inside that provider module and meeting the requirements of JPMS/ServiceLoader.

A common counterexample:

~~~java
// Intentionally wrong module-info.java snippet: DOES NOT replace uses.
module lab.host {
    requires lab.api;
    // missing uses lab.api.Greeting;
}
~~~

Even if the host compiles code referencing the Greeting class, omitting uses can cause **service loading from the named module to be rejected**. Fix **module-info.java** rather than adding requires lab.provider or exporting internal packages.

**Another counterexample:** a provider module has a class implementing Greeting but omits provides. The JVM does not scan every .class file in a named module to look for implementations. Providers must be registered in the module descriptor; automatic/classpath providers follow different rules.

**Do not fix this by adding exports lab.provider.internal** just so the host can call the provider constructor via reflection. That breaks encapsulation and masks a discovery design error.

## 14. Verification Exercises and Intentional Failure Modes

### 14.1. Removing plugin.jar from the plugins directory

If **ModuleFinder.of** cannot find lab.provider while **Set.of("lab.provider")** is still passed as the root, resolution fails because the root module is not found. This is distinct from "ServiceLoader runs and returns zero providers".

**Distinguish:**
- Root module not found → error in **module discovery/resolution**.
- Root module present without provides → may yield **no matching provider**.
- provides present but provider class invalid → **ServiceConfigurationError** during service loading.
- Instance exists but greet() fails → error in **application contract/runtime**, not ModuleFinder.

### 14.2. Renaming the module in the provider descriptor

If module-info.java declares **module lab.other** while the host still resolves root **lab.provider**, the module finder lacks root lab.provider. Choose module names deliberately and keep build, registry, and resolution code synchronized.

### 14.3. Removing requires lab.api from the provider

Provider source needs the lab.api.Greeting type; without valid readability, compiling the named module fails. Add the proper requires directive rather than copying the interface into the implementation package.

### 14.4. Removing uses from the host

The host can still reference Greeting through requires, but the module calling ServiceLoader lacks the service consumption declaration. Inspect the service loading error and module descriptor. **requires does not replace uses**.

### 14.5. Removing provides from the provider

The provider still compiles as a normal class, but ServiceLoader is never informed that this module supplies Greeting. Even though the module resolves in the child, **being resolved does not mean being registered as a service provider**.

### 14.6. Putting provider.jar on the boot module path as well

If lab.provider.jar is placed on the boot module path and resolved at launch (via roots or service binding), the provider may end up in the boot layer. The exercise then no longer tests "provider only in child", and redefining the same module in a child can produce unintended module graph/layer behavior.

To keep the test clean: **boot has only lab.api and lab.host; the plugins directory is searched via ModuleFinder at runtime**.

### 14.7. Placing a different copy of lab.api in the child layer

If a plugin ships its own copy of the API/SPI and the graph/loader defines that class separately, the host can encounter class identity mismatches, linkage errors, or ClassCastException. Keep the stable API in the parent and place only the provider + private dependencies in the child, with contract version checks.

### 14.8. Making the implementation class package-private

The provider class named directly after with must satisfy JPMS visibility and provider constructor/factory method requirements. Not exporting a package does not mean the provider class can arbitrarily be package-private. In this example, SimpleGreeting is a **public class** with a public no-arg constructor; keeping the package unexported simply restricts access from other modules.

## 15. Error Types to Watch For

| Symptom/Exception | Where does it usually occur? | How to handle |
| --- | --- | --- |
| **FindException** | ModuleFinder / resolve cannot find or read a module | Check paths, module name, JAR file, and descriptor |
| **ResolutionException** | Configuration cannot solve the module graph | Check requires, module dependencies, constraints, and packages |
| **LayerInstantiationException** | Defining layer/loader fails | Check module graph structure, loader, and package conflicts |
| **ServiceConfigurationError** | ServiceLoader fails reading provides or instantiating provider | Check uses/provides, constructor/provider method, cause |
| **NoClassDefFoundError** | Linking/loading provider or dependency | Check actual classes on module path, JNI/dependencies, and cause |
| **IllegalAccessError** | Module access or Java member visibility | Check exports/opens/readability and API contract |
| **ClassCastException** | API identity mismatch or wrong type | Check defining loader, module, and shared SPI |
| **NoSuchMethodError** | Plugin bytecode calls binary API missing at runtime | Pin SPI/dependency versions and run contract tests |
| Provider exists but business call fails | Host lifecycle or API behavior | Check version, thread safety, config, and tests |
| Old layer retains memory | Provider/loader/thread/callback remains reachable | Host manages stop/close/reference cleanup |

**ServiceConfigurationError is an Error**, not a checked exception; catch it intentionally at the discovery boundary to quarantine/reject the plugin rather than swallowing every Throwable. Exceptions from **greet()**, **start()**, or **stop()** are handled by the host according to the application contract, not silently turned into a ServiceLoader fallback policy.

Diagnostic tools you can use:
- **jar --describe-module --file plugins/lab.provider.jar**: inspect the module descriptor and provides.
- **jar --list --file plugins/lab.provider.jar**: inspect packaged module-info.class and class files.
- **jdeps --module-path ... plugins/lab.provider.jar**: inspect static module/library dependencies appropriately for the artifact.
- **ModuleLayer.boot().modules()** and **child.modules()**: inspect modules directly inside each layer.
- **provider.getClass().getModule()**: identify the module of the returned provider.
- **provider.getClass().getClassLoader()**: inspect the loader used by the JVM.
- **ServiceLoader.load(child, Greeting.class)**: verify discovery bound to the right layer.

These tools complement one another; no single command replaces integration tests.

## 16. Upgrading Plugins in the Child ModuleLayer Model

This exercise loads a plugin once initially. In production, hot updates are a **host-orchestrated workflow**, not merely replacing a JAR file and calling **ServiceLoader.reload()**:

~~~text
Plugin v1 ACTIVE (child layer L1)
      |
      +--> Receive plugin-v2.jar, verify signature/hash/version/permissions
      |
      v
Host creates ModuleFinder for artifact v2
      |
      v
Resolve Configuration v2 and define separate ModuleLayer L2
      |
      v
ServiceLoader.load(L2, SPI) + contract checks
      |
      v
Host configures, starts, and health-checks provider v2
      |
      +-- FAIL --> Keep v1, clean up v2 resources, report error
      |
      v
Route new traffic to v2
      |
      v
Drain old requests, stop v1, remove callbacks/threads/TCCL/references
      |
      v
Allow layer L1 and its loader to be GC'd when no longer referenced
~~~

**ModuleLayer has no general close/unload method.** Libraries/plugins may hold threads, schedulers, connections, static callbacks, or the thread context class loader, preventing old objects from being collected. The host needs lifecycle policies, timeouts, rollback, and leak detection. ServiceLoader.reload() only clears one ServiceLoader's cache; it does not redefine module code already loaded in an existing layer.

Multiple child layers can declare the same plugin **module name** at different versions if constructed as separate graphs/layers properly, though isolation and version routing must be managed carefully. Do not place two JARs with the same module name and conflicting packages into a single finder/configuration hoping JPMS will pick the "newest" one.

In multi-tenant systems or with independent plugins, consider a separate layer/loader per plugin group when dependency isolation warrants it. Avoid overusing layers for a handful of stable extensions; operational complexity can outweigh the benefits.

## 17. Incremental Migration Architecture Without Converting Every JAR at Once

A large application can migrate step by step:

1. **Extract the API/SPI into a stable module** and eliminate implementation classes directly imported by the host.
2. **Convert the host to a named module** with requires + uses, and verify launching via the module path.
3. **Convert each provider JAR to an explicit module**, declaring requires + provides while keeping implementation packages unexported.
4. **Keep the API in the parent boot layer**, avoiding copying the SPI into each plugin artifact.
5. **Add a plugin resolver/layer builder** to the host, initially supporting a single tested provider as in this exercise.
6. **Add validation and a registry**: module name, version, artifact hash, API range, and dependency policy.
7. **Add a lifecycle manager**: start/health/stop, update/rollback, routing, and leak detection.
8. **Migrate remaining plugins**, testing multiple concurrent providers, dependency failures, and class/module visibility.
9. **Remove the legacy classpath path** once all supported plugins have migrated, or maintain an intentionally designed compatibility bridge.

If third-party libraries lack module-info.java, automatic modules can ease migration onto the module path, though they do not offer the strong encapsulation of explicit modules. Do not confuse "putting a JAR on the module path" with authors explicitly declaring requires/exports/uses/provides.

For legacy plugins that only ship service configuration files, a practical path is rebuilding with module-info.java and accurate **provides** declarations. When migrating, verify with both **jar --describe-module** and discovery tests inside a **child ModuleLayer**, since module bugs go undetected if tests still run purely on the classpath.

## 18. Exercise Acceptance Criteria

| Check | Passing Criterion |
| --- | --- |
| javac --release 17 compiles all three explicit modules | No compiler errors |
| lab.provider.jar contains module-info.class | jar --describe-module shows lab.provider |
| lab.provider descriptor has requires lab.api | Explicit SPI dependency |
| lab.provider descriptor has provides Greeting with SimpleGreeting | Valid service registration |
| lab.host descriptor has uses lab.api.Greeting | Consumer declares service usage |
| Launch module path contains only lab.api and lab.host | lab.provider is not resolved in boot |
| ModuleFinder sees lab.provider.jar | Root module available for resolution |
| Configuration.resolve + defineModulesWithOneLoader succeed | child layer contains lab.provider |
| ServiceLoader.load(child, Greeting.class) finds a provider | At least one instance in the example |
| Greeting returns "Hello, Java!" | Host uses shared API successfully |
| Greeting.class belongs to a module in boot layer | No duplicated SPI in child |
| provider.internal package is not exported to host | Implementation properly encapsulated |
| No source changes needed when adding a compliant new provider | Host depends on contract, not implementation |

### Self-Check Questions

**1. Why must the host call ServiceLoader.load(childLayer, Greeting.class) instead of the default load(Greeting.class)?**  
Because a plugin resolved in a child layer may not be within the lookup scope used by the default overload via the thread context class loader. Specifying the layer lets the host explicitly target where services are discovered.

**2. Why is uses required in the host module?**  
requires only establishes readability to the API. uses declares that the host module dynamically consumes the service, enabling ServiceLoader to enforce the JPMS contract.

**3. Why can the host still call greet() when the implementation package is not exported?**  
The host invokes the method on the **lab.api.Greeting** interface exported by the parent. ServiceLoader has built-in privileges to instantiate valid providers in a named module even when the implementation package is not exported to the host.

**4. Why is merely copying lab.provider.jar into the plugins directory not enough?**  
No module has been resolved or layer/loader defined yet; the host must use ModuleFinder/Configuration/ModuleLayer and discover via ServiceLoader bound to the proper layer.

**5. Does resolve automatically call the provider constructor?**  
No. resolve constructs the module configuration; defining classes, obtaining providers, and invoking constructors happen in a separate phase, typically lazily via ServiceLoader.

**6. Can reload() upgrade lab.provider.jar from v1 to v2?**  
No. reload() clears the ServiceLoader cache without replacing module/class definitions in the old layer. The host needs a versioning workflow, a new layer/loader, and cutover.

**7. When ServiceLoader.load(childLayer, ...) returns multiple providers, do all of them belong to the child?**  
Not necessarily; per the API, it can discover providers in ancestor layers as well. The host must apply a selection policy and verify module/layer if needed.

## 19. Production Project Checklist

- [ ] SPI resides in a shared, versioned API module exporting the necessary packages.
- [ ] Host is a named module declaring **requires + uses** accurately.
- [ ] Provider is an **explicit named module** with **requires + provides**, keeping implementation packages unexported unless needed.
- [ ] Host does not require or import implementation modules.
- [ ] Provider artifacts include module-info.class and descriptors are verified after packaging.
- [ ] Plugin JARs stay off the boot module path when intended for child-layer loading.
- [ ] Host verifies artifact origin/version/hash before passing JARs to ModuleFinder.
- [ ] ModuleFinder, resolution roots, and module dependencies are managed explicitly.
- [ ] Parent API is shared to avoid duplicating SPI Class identity.
- [ ] Host uses **ServiceLoader.load(layer, SPI.class)** to discover in the proper scope.
- [ ] Host handles **missing providers**, configuration errors, and initialization failures per policy.
- [ ] Host selects providers by ID/capability/version rather than treating iteration order as business ranking.
- [ ] Tests run on a real module path and across Windows/Linux if both are supported.
- [ ] Plans exist for multiple modules, dependency conflicts, class loaders/layers, and service visibility.
- [ ] Lifecycle covers start/health/stop/rollback, TCCL hygiene, and reference cleanup to prevent leaks.
- [ ] ModuleLayer, ServiceLoader, and Java module encapsulation are not treated as a security sandbox.

**Conclusion:** Migrating to explicit named modules is more than adding **module-info.java**. To discover plugins in a child ModuleLayer, the host must **isolate the shared SPI in the parent**, **declare uses/provides in the right places**, **find and resolve plugin modules**, **define the child layer with a suitable loader strategy**, and **call ServiceLoader against the new layer**. This exercise demonstrates that the boot layer retains only API/host while plugin implementations load separately without exporting internal packages.

## Java 17 Reference Documentation

- ModuleLayer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- ModuleFinder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Configuration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java module declarations: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- JDK javac: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- JDK jar: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
