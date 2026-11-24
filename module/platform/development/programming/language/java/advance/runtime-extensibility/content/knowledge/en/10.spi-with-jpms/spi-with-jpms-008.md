# Declarations to Change When Moving the Same Provider from Classpath to Module Path

Java allows applications to be extended via the **Service Provider Interface (SPI)** and **ServiceLoader**. On the classpath, a provider is typically registered via a `META-INF/services` file containing implementation class names. When moving to the **Java Platform Module System (JPMS)** on the module path, provider discovery for an **explicit named module** shifts to declarations inside **module-info.java**. The exact same Java class can continue implementing the existing service, but the declarations specifying **where the service is used**, **which module provides the service**, and **which modules can read the service type** must be consistent.

This lesson directly answers the question: **Which declarations must be added, modified, or kept when a provider that used to run on the classpath is packaged and run on the module path?** It uses Java 17+, clearly distinguishes explicit modules from automatic modules, gives an example of the same provider JAR running in both modes, and covers how to troubleshoot common migration errors.

## 1. Quick Comparison of Declarations

Suppose the service is **`demo.greeting.api.Greeting`** and the implementation class is **`demo.greeting.provider.VietnameseGreeting`**. There are three roles:

- **API**: defines `Greeting`.
- **Consumer/host**: calls `ServiceLoader.load(Greeting.class)`.
- **Provider/plugin**: defines `VietnameseGreeting`.

| Concern | When Running on Classpath (Unnamed Module) | When Running as Explicit Named Modules |
| --- | --- | --- |
| Where is the provider registered? | File `META-INF/services/demo.greeting.api.Greeting`, containing the provider name | **`provides demo.greeting.api.Greeting with demo.greeting.provider.VietnameseGreeting;`** in the provider's `module-info.java` |
| Where does the consumer announce service lookup? | No `module-info.java` needed | **`uses demo.greeting.api.Greeting;`** in the `module-info.java` of the module calling `ServiceLoader` |
| How does the consumer depend on the API? | API is on the classpath | **`requires demo.greeting.api;`** in the consumer descriptor if the API is in another module |
| How does the provider depend on the API? | API is on the classpath | **`requires demo.greeting.api;`** in the provider descriptor if the API is in another module |
| How does the interface module expose the API? | Public interface visible via the classpath | **`exports demo.greeting.api;`** in the API module descriptor so other modules can use it |
| Must the implementation package be exported? | JPMS export boundaries do not apply | **`exports demo.greeting.provider;` is not needed** solely for `ServiceLoader` |
| Must the implementation package be opened? | Not needed just for `ServiceLoader` to call the constructor | **`opens` is not needed** for standard service provision |
| Must the consumer `requires` the provider module? | No direct dependency on the implementation | **Should not `requires provider`** just to discover the service; keep the dependency on the API |
| Is the old `META-INF/services` file still mandatory? | **Yes**, if the provider is registered only via classpath mechanics | **Cannot replace `provides`** when the provider is an explicit named module; may be kept to support running on the classpath again |

This table applies to **explicit named modules with `module-info.class`**. If you simply put an ordinary JAR **without `module-info.class`** on the module path, that JAR usually becomes an **automatic module**: `META-INF/services` entries can still be converted into service-providing metadata for the automatic module. Therefore, "putting a JAR on the module path" and "modularizing into an explicit named module" are two separate steps.

## 2. Before Migration: Registering SPI on the Classpath

A legacy application typically has three groups of classes:

~~~text
api.jar
└── demo/greeting/api/Greeting.class

provider.jar
├── demo/greeting/provider/VietnameseGreeting.class
└── META-INF/services/demo.greeting.api.Greeting

app.jar
└── demo/greeting/app/Main.class
~~~

The **`META-INF/services/demo.greeting.api.Greeting`** file has UTF-8 content:

~~~text
demo.greeting.provider.VietnameseGreeting
~~~

The **filename** is the full binary name of the **service**, while each **content** line is the binary name of a **provider**. `ServiceLoader` uses a class loader to locate this configuration file, loads the class name listed inside, and instantiates the provider during iteration.

In the classpath version, the JARs usually sit on the launch path:

~~~bash
java -cp "api.jar:provider.jar:app.jar" demo.greeting.app.Main
~~~

On Windows, the classpath element separator in the `java` command is a semicolon (`;`), whereas on Linux/macOS it is a colon (`:`).

**Migration point to remember:** Once a JAR becomes an **explicit named module**, Java does not obtain that module's provider list solely from `META-INF/services`. The module's providers must be declared with **`provides ... with ...`**. Consequently, merely moving the exact same provider JAR from the classpath to the module path and expecting the old descriptor file to work as before can cause the provider to disappear from `ServiceLoader` results.

## 3. Changes in Each Role's `module-info.java`

### 3.1. The API Module Must `exports` the Service Package

Suppose the `Greeting` interface resides in a module named **`demo.greeting.api`**. The API's **`module-info.java`** file is:

~~~java
module demo.greeting.api {
    exports demo.greeting.api;
}
~~~

The `exports` declaration lets code in other modules access the public `Greeting` type at compile time and runtime. If the API lives in a separate module without exporting the package, consumers/providers in other modules cannot reference the interface normally.

This is an export of the **API contract**, not an export of all internal application code. If the service interface already exists in another public API module, use the existing module name rather than creating a duplicate module.

### 3.2. The Consumer Needs `requires` on the API and `uses` on the Service

**`module-info.java`** of the application module **`demo.greeting.app`**:

~~~java
module demo.greeting.app {
    requires demo.greeting.api;
    uses demo.greeting.api.Greeting;
}
~~~

These two lines have distinct meanings:

- **`requires demo.greeting.api`**: allows the `app` module to read the module containing `Greeting` and compile imports/type references. `requires` creates a dependency edge between **modules**, without declaring service usage for provider lookup.
- **`uses demo.greeting.api.Greeting`**: informs JPMS that the `app` module may use `ServiceLoader` to discover providers for that **specific service type**. For callers inside an explicit named module, omitting `uses` violates the contract and calling `ServiceLoader.load` can throw **`ServiceConfigurationError`**.

Common mistake:

~~~java
// Missing uses: this descriptor is INSUFFICIENT for code calling ServiceLoader.
module demo.greeting.app {
    requires demo.greeting.api;
}
~~~

Even though the API is visible, the consumer has not yet declared its service requirement. A `requires` declaration **does not substitute for `uses`**.

If the app directly declares:

~~~java
requires demo.greeting.provider;
~~~

just so `ServiceLoader` can find an implementation, it creates a hard dependency on the provider, defeating the goal of swapping plugins without editing the consumer. Normally the `app` module only **`requires` the API** and **`uses` the service**, without requiring the provider module. Cases where code actually references an exported type from the provider are a separate direct-dependency concern and must be evaluated individually.

### 3.3. The Provider Needs `requires` on the API and `provides` Service `with` Implementation

**`module-info.java`** of **`demo.greeting.provider`**:

~~~java
module demo.greeting.provider {
    requires demo.greeting.api;
    provides demo.greeting.api.Greeting
        with demo.greeting.provider.VietnameseGreeting;
}
~~~

Here:

- **`requires demo.greeting.api`**: the provider reads and implements the `Greeting` interface exported by the API module.
- **`provides demo.greeting.api.Greeting with demo.greeting.provider.VietnameseGreeting`**: declares this module as a provider of the `Greeting` service, with the concrete provider class residing inside **this same module**.
- **`exports demo.greeting.provider` is not needed** just for `ServiceLoader` to instantiate the provider. JPMS lets `ServiceLoader` access the provider per the service contract even when the implementation package is not directly exported to application modules.

A `provides` clause cannot be used to declare an implementation class that actually lives in a different module. If one module has multiple providers for the same service, multiple names can be listed after `with` separated by commas, or an appropriate module/provider design can be used.

The following declaration is **not the right solution** when migrating from a classpath file to an explicit module:

~~~java
// WRONG: exporting the implementation does not replace provides.
module demo.greeting.provider {
    requires demo.greeting.api;
    exports demo.greeting.provider;
}
~~~

Exporting makes a package directly accessible; it does not register a provider with `ServiceLoader`. Conversely, `provides` registers the service without exposing every implementation as public API.

### 3.4. What Does the Old Registration Line Turn Into?

Direct mapping:

~~~text
Classpath file:
  META-INF/services/demo.greeting.api.Greeting

Classpath file content:
  demo.greeting.provider.VietnameseGreeting

Explicit provider module:
  provides demo.greeting.api.Greeting
      with demo.greeting.provider.VietnameseGreeting;
~~~

This is a **declaration change**; it does not require changing interface names, processing logic, business methods, or implementation classes as long as the provider still satisfies the contract on the module path. If package/service/provider names change during refactoring, both the descriptor and any dual-mode registration file still in use must be updated together.

## 4. Complete Java 17 Example: Same Provider Running in Both Modes

This example uses **one implementation**, `VietnameseGreeting`. We build three modular JARs—API, provider, and application—while keeping the `META-INF/services` file in the provider JAR so it can run on both the **classpath** and the **module path**.

### 4.1. Project Structure

~~~text
greeting-spi/
├── src/
│   ├── demo.greeting.api/
│   │   ├── module-info.java
│   │   └── demo/greeting/api/Greeting.java
│   ├── demo.greeting.provider/
│   │   ├── module-info.java
│   │   ├── demo/greeting/provider/VietnameseGreeting.java
│   │   └── META-INF/services/demo.greeting.api.Greeting
│   └── demo.greeting.app/
│       ├── module-info.java
│       └── demo/greeting/app/Main.java
├── mods/           (generated during compilation)
└── mlib/           (holds JARs after packaging)
~~~

The **`src/<module-name>`** directories follow the layout expected by `javac --module-source-path`. In projects built with Maven/Gradle, `module-info.java` and resources typically live in source directories per build-tool conventions, but the **output JAR** must have `module-info.class` and resources in their exact positions inside.

### 4.2. API

**src/demo.greeting.api/module-info.java**

~~~java
module demo.greeting.api {
    exports demo.greeting.api;
}
~~~

**src/demo.greeting.api/demo/greeting/api/Greeting.java**

~~~java
package demo.greeting.api;

public interface Greeting {
    String sayHello(String name);
}
~~~

### 4.3. Provider

**src/demo.greeting.provider/module-info.java**

~~~java
module demo.greeting.provider {
    requires demo.greeting.api;
    provides demo.greeting.api.Greeting
        with demo.greeting.provider.VietnameseGreeting;
}
~~~

**src/demo.greeting.provider/demo/greeting/provider/VietnameseGreeting.java**

~~~java
package demo.greeting.provider;

import demo.greeting.api.Greeting;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
    }

    @Override
    public String sayHello(String name) {
        return "Xin chào, " + name;
    }
}
~~~

The provider in this example uses a **public no-args constructor** and a public concrete class implementing the service interface. This instantiation path works on the classpath, automatic modules, and explicit modules alike.

**src/demo.greeting.provider/META-INF/services/demo.greeting.api.Greeting**:

~~~text
demo.greeting.provider.VietnameseGreeting
~~~

This file is retained to support the **classpath**. For explicit named modules, `ServiceLoader` uses `provides` in `module-info.class`; an entry in `META-INF/services` pointing to a provider already deployed in a named module will not be double-counted as a provider in the unnamed module.

### 4.4. Consumer

**src/demo.greeting.app/module-info.java**

~~~java
module demo.greeting.app {
    requires demo.greeting.api;
    uses demo.greeting.api.Greeting;
}
~~~

**src/demo.greeting.app/demo/greeting/app/Main.java**

~~~java
package demo.greeting.app;

import demo.greeting.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        int count = 0;
        for (Greeting provider : ServiceLoader.load(Greeting.class)) {
            System.out.println(provider.sayHello("Lan"));
            count++;
        }
        System.out.println("providers=" + count);
    }
}
~~~

The program does not reference `VietnameseGreeting`. The code stays identical in both modes; the difference lies in **descriptors, resources, and launch options**.

### 4.5. Compiling and Packaging Three Modular JARs

Run the following commands from `greeting-spi` in Bash on Linux/macOS/Git Bash with **JDK 17+** and all files created above:

~~~bash
mkdir -p mods mlib

javac -encoding UTF-8 --module-source-path src -d mods \
  $(find src -name '*.java')

mkdir -p mods/demo.greeting.provider/META-INF/services
cp src/demo.greeting.provider/META-INF/services/demo.greeting.api.Greeting \
   mods/demo.greeting.provider/META-INF/services/

jar --create --file mlib/demo.greeting.api.jar \
  -C mods/demo.greeting.api .
jar --create --file mlib/demo.greeting.provider.jar \
  -C mods/demo.greeting.provider .
jar --create --file mlib/demo.greeting.app.jar \
  -C mods/demo.greeting.app .
~~~

The `javac` step compiles all three modules using **`--module-source-path`** and resolves module dependencies from `module-info.java`. The service descriptor file is a **resource**, not a Java file; therefore, `cp` ensures it is actually included in the provider JAR. Build tools can be configured to copy resources automatically instead of doing this manually.

Inspect the provider JAR:

~~~bash
jar --list --file mlib/demo.greeting.provider.jar
jar --describe-module --file mlib/demo.greeting.provider.jar
~~~

These key entries **must appear** in the JAR listing (this is not the entire output of `jar --list`):

~~~text
module-info.class
demo/greeting/provider/VietnameseGreeting.class
META-INF/services/demo.greeting.api.Greeting
~~~

`jar --describe-module` shows that the provider JAR is an explicit module named **`demo.greeting.provider`**, with `requires` on the API and `provides Greeting with VietnameseGreeting`. Without `module-info.class`, it is no longer an explicit module as shown in this example.

### 4.6. Running on the Classpath

Use the exact three packaged JARs and place them on the classpath:

~~~bash
java -cp "mlib/demo.greeting.api.jar:mlib/demo.greeting.provider.jar:mlib/demo.greeting.app.jar" \
  demo.greeting.app.Main
~~~

Output:

~~~text
Xin chào, Lan
providers=1
~~~

When modular JARs are placed on the **classpath**, their `module-info.class` files are not used to build module descriptors; the classes become part of the **unnamed module**. Therefore, `ServiceLoader` discovers the provider via the `META-INF/services` file inside the JAR. If that file is removed while keeping `provides` in `module-info.class`, this classpath run will fail to discover the provider.

### 4.7. Running on the Module Path

Use the exact same three JARs and the modular launch command:

~~~bash
java --module-path mlib \
  --add-modules demo.greeting.provider \
  --module demo.greeting.app/demo.greeting.app.Main
~~~

Output:

~~~text
Xin chào, Lan
providers=1
~~~

Here:

- **`--module-path mlib`** specifies the location of modules observable by the system.
- **`--module demo.greeting.app/demo.greeting.app.Main`** selects the main module and main class.
- **`--add-modules demo.greeting.provider`** explicitly adds the provider to the root modules to resolve. This is an explicit choice ensuring the example definitely has a resolved provider; in other launch configurations, the **service binding** mechanism during module resolution can also bring the provider into the graph.
- The app has **`uses Greeting`**, the provider has **`provides Greeting with VietnameseGreeting`**, and both read the API module accordingly.
- The `demo.greeting.provider` package can remain unexported; `ServiceLoader` still instantiates the provider per the contract.

The output matches the classpath run, yet the registration mechanism differs. Merely adding the provider module to the module graph only makes the module present; if **`provides`** is removed from the explicit provider descriptor, the `META-INF/services` file does not automatically act as a fallback service declaration.

**On Windows**, `--module-path` only takes a single `mlib` directory in this example, so no separator change is needed. If `--module-path` has multiple directories, Windows uses a semicolon (`;`). The `mkdir`/`cp`/`find` commands in the compilation step are Bash; in PowerShell, replace them with the corresponding directory-creation, resource-copy, and Java file-listing commands.

## 5. Do Not Confuse the Four Deployment Modes

Four scenarios appear together during migration. What declarations are needed depends on **which mode the JAR is actually launched in**:

| Provider JAR Type | Where Placed? | How `ServiceLoader` Knows About the Provider |
| --- | --- | --- |
| Regular JAR without `module-info.class` | Classpath | Reads `META-INF/services` |
| Regular JAR without `module-info.class` (**automatic module**) | Module path and resolved | Service metadata can be derived from `META-INF/services` |
| **Explicit modular JAR** with `module-info.class` | Module path and resolved | **`provides ... with ...`** in module descriptor |
| **Explicit modular JAR** with `module-info.class` | Classpath | `module-info.class` is ignored; `META-INF/services` is needed for classpath SPI |

Specifically:

- **Automatic module** has a module name (set via `Automatic-Module-Name` in the manifest or derived from the JAR filename), yet **lacks a full `module-info.java` descriptor**. Service entries present in `META-INF/services` continue to contribute to the metadata generated by the system for the automatic module. An automatic module does not have the encapsulation level of an explicit module: its packages are broadly exported/opened.
- **Explicit module** has a compiled descriptor; for providers in this module, **`provides`** must be used. Do not assume "since `META-INF/services` is present, the module path will definitely see the provider" when the module is explicit.
- **Dual-mode modular JAR** should include **both `provides`** and `META-INF/services` if a single artifact must serve both a Java 17 module path and legacy classpath applications.
- **Unnamed module** is the classpath environment. Code inside can still invoke `ServiceLoader`, but it has no `module-info.java` of its own with `uses`/`provides` for the JVM to read.

A manifest containing only `Automatic-Module-Name` **does not replace `module-info.java`** and does not turn a library into an explicit named module.

## 6. Seeing a JAR on the Module Path Does Not Mean the Module Is Resolved

Finding the provider file in `mlib` does not mean the provider participates in the process's **module graph**. Distinguish these stages:

~~~text
JAR exists on disk
       |
       v
Observable via --module-path
       |
       v
Module is resolved into active graph/layer
       |
       v
Provider is declared by module descriptor
       |
       v
Caller's ServiceLoader can discover provider
       |
       v
Instantiate provider and use per contract
~~~

At the module graph level:

- **`requires`** creates a read relationship to the named module; both consumer and provider requiring the API is the standard compile-time/runtime dependency structure.
- **`uses`** expresses service consumption needs in the consumer module.
- **`provides`** expresses service supply in the provider module.
- **Service binding** during resolution can bring provider modules into the graph when a resolved module declares usage of the corresponding service. For custom distributions, verify whether the actual launcher, plugin loader, or module layer enables this step.
- **`--add-modules demo.greeting.provider`** explicitly requests resolving the provider in this hands-on example; it is not a recommendation to manually list every provider in all plugin systems.
- When building a runtime image with **`jlink`**, the **`--bind-services`** option may be required if you want service providers included in the image via service binding.
- In dynamic **`ModuleLayer`** plugin systems, a new configuration can be created via `resolve` or `resolveAndBind`; the actual list of providers also depends on the module layer being queried.

If `ServiceLoader` returns 0 providers on the module path, inspect module resolution/graph before concluding `provides` was written incorrectly. A correctly declared provider that is **not resolved** will still not be present for `ServiceLoader` to discover in the relevant layer.

## 7. Rules on Constructors, `provider()`, and Encapsulation

### 7.1. Provider via Constructor

The straightforward path suited for classpath migration:

~~~java
package demo.greeting.provider;

import demo.greeting.api.Greeting;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
    }

    @Override
    public String sayHello(String name) {
        return "Xin chào, " + name;
    }
}
~~~

The provider class is **`public`**, concrete, implements the service, and has a **`public` no-args constructor**. This path works cleanly to keep a single implementation class functioning on both the classpath and module path.

If the class only has parameterized constructors, `ServiceLoader` does not automatically perform dependency injection for those parameters through standard constructor-provider mechanics. When migrating, design an appropriate provider-creation pattern rather than thinking `requires` or `opens` can inject dependencies automatically.

### 7.2. Provider Method Is Exclusive to Explicit Named Modules

In an explicit module, Java 17 supports declaring a provider class with a no-arg **`public static provider()`** returning a type assignable to the service. With this approach, the class listed in `provides` itself does not have to implement the service.

Illustrative API example inside an explicit module (illustrative alternative, not used in the standalone runnable program in Section 4):

~~~java
package demo.greeting.provider;

import demo.greeting.api.Greeting;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static Greeting provider() {
        return name -> "Xin chào, " + name;
    }
}
~~~

Corresponding descriptor:

~~~java
module demo.greeting.provider {
    requires demo.greeting.api;
    provides demo.greeting.api.Greeting
        with demo.greeting.provider.GreetingFactory;
}
~~~

`ServiceLoader` will call `provider()` to obtain the `Greeting` instance. However:

- On the **classpath**, `META-INF/services` does not support the module-style provider method form; the class listed in the resource must still be a compliant implementation with a public no-args constructor.
- **Automatic modules** on the module path also do not support explicit-module provider methods; a provider constructor is mandatory.
- If the goal is running the exact same provider on both the classpath and module path, continuing to use a **public concrete implementation with a no-args constructor** is usually the most convenient option.

Do not change instantiation mechanisms solely because a JAR moved locations when business logic does not require it.

### 7.3. `exports`/`opens` Is Not Needed on the Implementation for `ServiceLoader`

Declaring `provides` allows the runtime to operate through the official service-provision mechanism. A provider in an unexported package can still be discovered and instantiated as long as it meets contract rules.

**`exports`** lets other modules access public types in a package under appropriate module readability; **`opens`** pertains to deep reflective access by frameworks at runtime. Do not export the entire implementation or open the whole module as a "trick" to fix `ServiceLoader` not finding a provider. Check `provides`, `uses`, `requires`, and resolution first.

If an external application reflects into non-public fields/constructors of a provider, that is a separate requirement from `ServiceLoader` and requires evaluating a specific `opens` policy instead of opening indiscriminately.

## 8. Same Provider in a Real Host/Plugin System

When deploying runtime-loaded plugins, the host may deal with two distinct boundaries:

1. **Service boundary**: the host knows the `Greeting` type from the API and invokes `ServiceLoader`.
2. **Module/class loader boundary**: the host determines which `ModuleLayer` and class loader a provider JAR is resolved into, and whether the service type shares the same `Class` identity.

For traditional classpath plugins, the host may create a `URLClassLoader` and use:

~~~java
// ILLUSTRATIVE CALL SNIPPET WHEN pluginLoader IS KNOWN; not standalone.
ServiceLoader<Greeting> providers =
        ServiceLoader.load(Greeting.class, pluginLoader);
~~~

For providers in a **new module layer**, you can use:

~~~java
// ILLUSTRATIVE CALL SNIPPET WHEN layer AND Greeting ARE KNOWN; not standalone.
ServiceLoader<Greeting> providers =
        ServiceLoader.load(layer, Greeting.class);
~~~

`load(layer, service)` searches in **the specified layer and its ancestor layers**. It is not an arbitrary "scan the entire JVM module path" operation. Layer creation, resolution, class loaders, and module readability must be managed consistently by the host; a module sitting on disk that is not inside the relevant layer will not appear on its own.

In both cases, **the caller module invoking `ServiceLoader` must declare `uses`** if the caller is an explicit named module. Passing `Greeting.class` as an argument does not remove the `uses` requirement from the module containing the call site.

### Do Not Create Two Copies of the API

Another migration error occurs when a provider in a separate class loader/module layer loads its own copy of the service API instead of sharing the host's interface. When that happens, there are two distinct `Class` objects named `demo.greeting.api.Greeting`, and the provider may be incompatible with the service requested by the host.

The standard design is to keep the shared API in a resolved parent module/loader and have the provider read that exact module; avoid bundling duplicate copies of the API inside another plugin layer without sharing. **An identical JPMS module name does not automatically guarantee that two `ModuleLayer`s or loaders share the same `Class` identity.** This issue sits alongside `requires`/`uses`/`provides` and must be verified whenever plugins are dynamically loaded.

## 9. Analysis of Common Migration Scenarios

### Scenario A: Full Switch to Explicit Named Modules

- API exports the service package.
- Consumer has `requires` API + `uses` service.
- Provider has `requires` API + `provides` service `with` class.
- Provider is resolved into the relevant graph/layer.
- Implementation class still satisfies constructor/provider-method rules.
- For pure module-path execution, `META-INF/services` is no longer a mandatory registration source.

This is the path with the clearest encapsulation in JPMS.

### Scenario B: Still Need to Support Legacy Applications on the Classpath

Keep **both**:

~~~text
META-INF/services/demo.greeting.api.Greeting
~~~

and in the provider's `module-info.java`:

~~~java
provides demo.greeting.api.Greeting
    with demo.greeting.provider.VietnameseGreeting;
~~~

A single artifact can use the same implementation bytecode in both modes. CI pipelines must test both execution paths. If you only test the module path and delete the resource, classpath runs can lose the provider even while the module path keeps working.

### Scenario C: Regular JAR Placed on the Module Path Without `module-info`

That JAR is an **automatic module**, not an explicit module. `META-INF/services` files can still serve to declare providers for the automatic module once resolved. This is typically a transitional phase.

Although it has a module name (stabilizable via `Automatic-Module-Name`), an automatic module does not provide the same explicit encapsulation and dependency declarations as an explicit module; testing service discovery and public-constructor compatibility is essential.

### Scenario D: Consumer Still on Classpath, Provider Already a Named Module

`ServiceLoader` in unnamed-module code can discover providers in named modules **that are resolved and visible through an appropriate loader/layer**. A classpath consumer has no `module-info` of its own; the explicit-consumer `uses` requirement does not apply to it. However, the provider might not be resolved, or the service API might exist in multiple places.

Do not conclude solely from "placed the JAR in `--module-path`" that a classpath consumer will see the provider. Check `--add-modules` or service binding, API identity, and the application's actual loader.

### Scenario E: Consumer Already a Named Module, Provider Still on Classpath

An explicit consumer module needs `requires` for the API module and `uses` for the service. `ServiceLoader` can discover classpath-style providers via provider-configuration files if the provider class is visible and uses the exact same service API. At the same time, avoid placing duplicate copies of the API package on both the classpath and module path, which causes conflicts or incompatibility.

Hybrid setups should be tested under actual launcher configurations; do not mechanically apply the rules of "all three are named modules" to every combination.

## 10. When Packaging with Build Tools, Inspect the Output—Not Just the Source

If using Gradle or Maven, focus on the structure of the **final JAR**:

~~~text
api.jar
├── module-info.class
└── demo/greeting/api/Greeting.class

provider.jar
├── module-info.class
├── demo/greeting/provider/VietnameseGreeting.class
└── META-INF/services/demo.greeting.api.Greeting   (if dual-mode)

app.jar
├── module-info.class
└── demo/greeting/app/Main.class
~~~

Typically `module-info.java` goes under `src/main/java/module-info.java`, and `META-INF/services` goes under `src/main/resources/META-INF/services/<FQCN of service>`. The build tool must compile the module descriptor to the **root of the JAR** and copy resources to **`META-INF/services` at the JAR root**, not nested inside an extra `src/main/resources` directory.

When building fat/uber JARs, keep in mind:

- Merge multiple `META-INF/services` files if bundling multiple classpath providers into one artifact; keeping only one copy can silently drop other providers.
- If relocating/shading packages, update service/provider names across descriptors, resources, and relevant code; `module-info.class` must also be handled properly according to build tool capabilities. Do not equate merging resources with module resolution.
- JPMS **forbids split packages** between named modules within the same resolution scope. When splitting API/providers into modules, assign packages along clean boundaries and never duplicate classes in the same package across two modules.
- Unmodularized libraries may behave as automatic modules; a module name derived from a JAR filename can change when the artifact is renamed. If a module name is genuinely referenced in `requires`, stabilize the module name or plan to convert to an explicit module.
- Do not assume `java -jar`, `java -cp`, and `java --module-path` are equivalent ways to run. Launcher configuration determines whether an artifact is treated as unnamed, automatic, or an explicit named module.

For libraries that must support both Java 8 and Java 17, plan multi-release packaging or appropriate compilation; do not bundle a `module-info.class` compiled by a newer JDK and assume every older JVM can read it. This lesson focuses on **Java 17+**.

## 11. Diagnosing Migration Errors Layer by Layer

### 11.1. Inspect Descriptors and Resources Inside the JAR

~~~bash
jar --describe-module --file mlib/demo.greeting.provider.jar
jar --list --file mlib/demo.greeting.provider.jar
~~~

Expect to see `module-info.class` and the `provides` declaration. If `jar --describe-module` reports it as an automatic module (or lacking an explicit descriptor), you are still in automatic mode; at that point, distinguish the rules for deriving metadata from service files.

If `module-info.class` is present yet lacks `provides`, update the **provider's** module descriptor, recompile, and repackage. Merely adding or editing `META-INF/services` will not register an explicit provider in the module descriptor.

### 11.2. Check Whether the Module Was Resolved

~~~bash
java --show-module-resolution \
  --module-path mlib \
  --add-modules demo.greeting.provider \
  --module demo.greeting.app/demo.greeting.app.Main
~~~

This command shows the resolution graph constructed by the launcher. Module-resolution diagnostics are printed alongside application output; output varies by module set and JDK, so do not expect a fixed stack trace as a static template.

If the provider module is absent from the graph despite being on the module path, check `--add-modules`, service binding, root modules, and the `ModuleLayer` the application is actually using.

### 11.3. Check `uses` and `requires`

- If the consumer module fails to compile or cannot read the `Greeting` type at runtime: verify **`requires demo.greeting.api`** and **`exports demo.greeting.api`** from the API module.
- If the caller is an explicit module and `ServiceLoader.load` throws an error such as "module ... does not declare uses": add **`uses demo.greeting.api.Greeting`** to the module calling `ServiceLoader`.
- If the provider reports compile errors when declaring `provides` or implementing `Greeting`: check **`requires demo.greeting.api`**, service name, provider name, class placement within the module, and constructor/provider-method validity.
- If `ServiceLoader` iterates yet instantiation fails, check the provider constructor or `provider()`, exceptions during initialization, and runtime dependencies.

### 11.4. Distinguish Empty Results from Configuration Errors

`ServiceLoader` does not necessarily throw an error when **no providers are found**; the code may simply iterate over 0 elements. By contrast, when a provider is declared but the class name, service type, or instantiation mechanism is invalid, lazy discovery/instantiation can throw **`ServiceConfigurationError`**.

In verification tooling, avoid catching all errors and turning them into `providers=0`, which hides build issues. Record the **service name**, **caller module**, **provider module**, **module layer**, **class loader**, launch path, and exception in diagnostic logs.

In applications with multiple providers, **do not assume iteration order** is a global priority guarantee; module discovery, classpath, and layers have different ordering rules. If a specific implementation must be chosen, define selection criteria in the service contract or host configuration.

## 12. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Classpath run finds provider, module path returns 0 | JAR is an explicit module missing `provides`, or provider is unresolved | Add `provides`, check graph/module layer |
| Module path works, classpath returns 0 | `META-INF/services` was removed from dual-mode JAR | Retain the resource with exact name and contents for classpath |
| Named caller module throws `ServiceConfigurationError` about `uses` | App module is missing `uses` | Add `uses` for the service in the exact module making the call |
| Compiling app module cannot see API | Missing `requires` or API module does not export service package | Fix `requires`/`exports` |
| Provider declares `provides` yet fails to compile | Class/provider not in module, wrong type, or missing valid constructor/provider method | Fix module graph and provider contract |
| Exporting implementation still finds no provider | `exports` does not register an SPI | Add `provides ... with ...` |
| Classpath provider works, automatic module fails to instantiate | Invalid constructor or unresolved module | Keep public no-args constructor; verify module resolution |
| Trying `provider()` on classpath/automatic module | Only explicit modules support the provider-method mechanism | Use a direct implementation with a public no-args constructor |
| Regular JAR becomes an automatic module with an unexpected name | Name derived from artifact filename | Add `Automatic-Module-Name` to stabilize; or modularize explicitly |
| Dynamic module layer does not see provider | Searching wrong layer or provider not resolved | Resolve into the relevant layer and use `ServiceLoader.load(layer, service)` |
| `ClassCastException`/`not a subtype` | Two copies of the service API loaded across different loaders/layers | Unify API identity via a parent/shared module |
| CI passes, distribution misses provider | Resources/`module-info.class` packaged incorrectly | Inspect final JAR with `jar --list`/`--describe-module` |

Do not fix provider-discovery failures by opening `exports`/`opens` across the entire module without evidence of an access issue. Those changes widen the API surface without fixing missing SPI declarations.

## 13. Minimal Verification Suite for the Migration

Simply adding a descriptor to source files is not proof that the plugin runs correctly. Include independent runs on both the classpath and module path:

1. **Legacy classpath:** run the three JARs with `-cp` as in Section 4.6; must find exactly one `VietnameseGreeting`.
2. **Explicit module path:** run with `--module-path` and `--add-modules` as in Section 4.7; must find exactly one `VietnameseGreeting` even though the implementation package is unexported.
3. **Detecting missing classpath file:** with a test artifact omitting `META-INF/services` while keeping `module-info.class`, classpath mode will see 0 providers. Do not replace the dual-mode JAR with this test artifact afterward.
4. **Verify `uses`:** a consumer module missing `uses` must be flagged as misconfigured when calling `ServiceLoader`; assert the error properly instead of relying on empty output.
5. **Verify `provides`:** for an explicit module missing `provides`, the provider must not be discovered via module metadata merely because the class exists in the JAR.
6. **No `requires` on provider:** confirm the app module depends only on the API module, and swapping the provider module does not force recompiling the app.
7. **Verify `ModuleLayer`/loader:** if the host loads plugins dynamically, query the exact layer containing the provider with proper reload and reference-cleanup policies.
8. **Verify packaging:** confirm `module-info.class` sits at the root of each modular JAR, service resources are present if dual-mode, and package names were not altered by shading.
9. **Verify JDK version:** run on the target JDK, checking both compilation and runtime module resolution.

When testing descriptor modifications, build **separate test artifacts**; do not overwrite release JARs in place across parallel runs. Never hardcode provider order when multiple providers exist in real environments.

## 14. Checklist for Moving the Same Provider to the Module Path

Before moving a legacy SPI provider to JPMS, answer each item in turn:

- **JAR type:** will the provider be an automatic module or an explicit named module? Is `module-info.class` in the packaged artifact?
- **Service API:** is the package containing the service interface exported by the API module?
- **Consumer:** does the module calling `ServiceLoader` declare `requires` API and **`uses` service**?
- **Provider:** does the module containing the implementation declare `requires` API and **`provides` service `with` provider**?
- **Construction:** does the implementation match the constructor/provider-method rules of the launch mode?
- **Encapsulation:** is the implementation package kept hidden, avoiding unnecessary `exports`/`opens`?
- **Resolution:** is the provider module resolved into the graph/layer that `ServiceLoader` is inspecting?
- **Dual mode:** if classpath runs are still supported, is `META-INF/services` preserved and copied to the right place in the JAR?
- **API identity:** do the host and provider use the exact same runtime service type?
- **Distribution:** have both `java -cp` and `java --module-path` been tested with the final JARs, verifying output and lazy discovery errors?
- **Replaceability:** does the consumer remain independent of implementation class names and provider module names?

**A proper migration** preserves the provider's Java contract while shifting registration from `META-INF/services` to `provides` in the explicit provider module, declaring consumption with `uses` in the consumer, and ensuring `requires`/`exports` for the referenced API. When both launch modes must be supported, keep both the JPMS descriptor and the classpath service file in the final JAR; always verify module resolution and layers before concluding `ServiceLoader` is broken.

## References

- Java SE 17, **ServiceLoader** — contracts for classpath provider configuration, providers in modules, `uses`/`provides`, constructor/provider methods, and `ServiceConfigurationError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- dev.java, **Decoupling Modules with Services** — service directives and service binding: https://dev.java/learn/organizing/modules/services/
- dev.java, **Incremental Modularization with Automatic Modules** — automatic modules, module names, and using `META-INF/services`: https://dev.java/learn/organizing/modules/automatic-module/
