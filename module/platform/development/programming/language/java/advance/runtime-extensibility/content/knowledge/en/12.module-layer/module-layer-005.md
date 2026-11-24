# Discovering Services via ServiceLoader.load(layer, service)

## 1. Purpose

In the Java Platform Module System (JPMS), an application can create a dedicated **ModuleLayer** for plugin modules. After resolving dependencies and defining the layer, the host needs to discover implementations of a service interface published by the plugins.

Java provides the overload:

\`\`\`java
public static <S> ServiceLoader<S> load(ModuleLayer layer, Class<S> service)
\`\`\`

This method creates a \`ServiceLoader<S>\` to discover service providers in **the specified layer and its ancestor layers** according to JPMS rules. Unlike \`ServiceLoader.load(Service.class)\`, this overload uses **the layer as the discovery scope**, rather than starting from the thread context class loader.

For example, the host defines the \`GreetingService\` service, while the plugin module declares:

\`\`\`java
provides com.example.api.GreetingService
    with com.example.plugin.VietnameseGreeting;
\`\`\`

After the host creates the layer containing the plugin, the call:

\`\`\`java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
\`\`\`

allows the host to find usable providers without calling \`Class.forName\` on implementation names.

**Key points to remember:** \`ServiceLoader.load(layer, service)\` does not create layers, does not automatically load new JARs from disk, and does not automatically refresh when new plugin JARs appear. Discovering providers via \`ServiceLoader\` can also trigger provider instantiation during iteration; therefore, provenance and trust verification of plugins must be completed before use.

## 2. Roles of Service, Provider, and Layer

A system typically includes the following components:

| Component | Role |
|---|---|
| Service interface | Contract referenced by both host and provider |
| API module | Supplies the shared service interface |
| Provider module | Declares the implementation with \`provides ... with ...\` |
| \`ModuleFinder\` | Finds modules in JARs or plugin directories |
| \`Configuration\` | Module graph with resolved dependencies |
| \`ModuleLayer\` | Set of modules existing in a runtime layer |
| \`ServiceLoader\` | Discovers and instantiates providers per the service contract |

General flow:

\`\`\`text
        Host application
             |
        API module
             |
    ModuleFinder.of(plugins/)
             |
    Configuration.resolve(...)
             |
       ModuleLayer
             |
    ServiceLoader.load(layer, GreetingService.class)
             |
       Provider instances
             |
       Registry / selection policy
             |
          Invocation
\`\`\`

The term *service* here refers to a Java interface exposed via the service provider mechanism, not necessarily an HTTP service or microservice.

With JPMS, the provider class can reside in a package not \`exports\`ed to the host; the \`provides\` mechanism still permits \`ServiceLoader\` to instantiate and return the object through the shared service interface.

## 3. Preparing module-info.java

Suppose the system consists of three modules:

- \`com.example.greeting.api\`: declares the \`GreetingService\` interface.
- \`com.example.greeting.plugin\`: implements the service and publishes the provider.
- \`com.example.greeting.host\`: creates the layer, discovers, and invokes providers.

### API Module

\`src/com.example.greeting.api/module-info.java\`:

\`\`\`java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
\`\`\`

\`src/com.example.greeting.api/com/example/greeting/api/GreetingService.java\`:

\`\`\`java
package com.example.greeting.api;

public interface GreetingService {
    String language();
    String greet(String name);
}
\`\`\`

\`exports\` allows the host and plugin to access the interface under JPMS rules.

### Provider Module

\`src/com.example.greeting.plugin/module-info.java\`:

\`\`\`java
module com.example.greeting.plugin {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.plugin.VietnameseGreeting;
}
\`\`\`

\`src/com.example.greeting.plugin/com/example/greeting/plugin/VietnameseGreeting.java\`:

\`\`\`java
package com.example.greeting.plugin;

import com.example.greeting.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {}

    @Override
    public String language() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
\`\`\`

The provider has a public no-argument constructor so the service loader can instantiate it. In an explicit module, a provider can also use the static \`provider()\` method convention supported by the API; this example chooses a constructor for clarity. \`exports com.example.greeting.plugin\` is not required solely to supply a provider via \`provides\`.

### Host Module

\`src/com.example.greeting.host/module-info.java\`:

\`\`\`java
module com.example.greeting.host {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingService;
}
\`\`\`

\`uses\` declares that the host module consumes the service. Omitting \`uses\` in a named module can cause \`ServiceLoader\` to reject the request at runtime. \`requires\` grants access to the interface, whereas \`uses\` declares service consumption; the two directives serve different roles.

## 4. Java 17+ Example: Creating ModuleLayer and Discovering Providers

\`src/com.example.greeting.host/com/example/greeting/host/Main.java\`:

\`\`\`java
package com.example.greeting.host;

import com.example.greeting.api.GreetingService;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    public static void main(String[] args) {
        Path pluginDirectory = Path.of("plugins");

        ModuleFinder pluginFinder = ModuleFinder.of(pluginDirectory);
        ModuleLayer parent = ModuleLayer.boot();

        Configuration configuration = parent.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.greeting.plugin")
        );

        ModuleLayer pluginLayer = parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );

        List<GreetingService> providers =
                ServiceLoader.load(pluginLayer, GreetingService.class)
                        .stream()
                        .map(ServiceLoader.Provider::get)
                        .sorted(Comparator.comparing(GreetingService::language))
                        .toList();

        for (GreetingService provider : providers) {
            System.out.println(provider.language() + ": " +
                    provider.greet("Lan"));
        }
    }
}
\`\`\`

Step-by-step explanation:

1. \`ModuleFinder.of(pluginDirectory)\` discovers modules from the \`plugins\` directory.
2. \`ModuleLayer.boot()\` provides the parent layer containing the host and API module in this example.
3. \`resolve(..., Set.of("com.example.greeting.plugin"))\` locates the root module and resolves dependencies.
4. \`defineModulesWithOneLoader\` creates the layer containing the plugin per the resolved configuration.
5. \`ServiceLoader.load(pluginLayer, GreetingService.class)\` searches for service providers within the layer's scope.
6. \`Provider::get\` instantiates/obtains the instance, after which the host calls methods of the shared interface.

At the \`stream()\` step, \`ServiceLoader.Provider\` lets you inspect \`type()\` before calling \`get()\`, which is useful for filtering or checking provider types. However, class discovery and definition still follow their own linkage rules; do not treat \`type()\` as a sandbox or validation step for untrusted code.

### Directory Structure

\`\`\`text
project/
├── src/
│   ├── com.example.greeting.api/
│   │   ├── module-info.java
│   │   └── com/example/greeting/api/GreetingService.java
│   ├── com.example.greeting.host/
│   │   ├── module-info.java
│   │   └── com/example/greeting/host/Main.java
│   └── com.example.greeting.plugin/
│       ├── module-info.java
│       └── com/example/greeting/plugin/VietnameseGreeting.java
└── plugins/
\`\`\`

From the \`project\` directory, run on JDK 17+:

\`\`\`bash
javac --module-source-path src -d mods \
  src/com.example.greeting.api/module-info.java \
  src/com.example.greeting.api/com/example/greeting/api/GreetingService.java \
  src/com.example.greeting.host/module-info.java \
  src/com.example.greeting.host/com/example/greeting/host/Main.java \
  src/com.example.greeting.plugin/module-info.java \
  src/com.example.greeting.plugin/com/example/greeting/plugin/VietnameseGreeting.java

mkdir -p plugins

jar --create --file plugins/com.example.greeting.plugin.jar \
  -C mods/com.example.greeting.plugin .

java --module-path mods/com.example.greeting.api:mods/com.example.greeting.host \
  --module com.example.greeting.host/com.example.greeting.host.Main
\`\`\`

The commands above are written for a POSIX shell (\`\\\` line continuations). For Windows PowerShell, run each command on a single line and replace the module path separator \`:\` with \`;\`. Avoid putting the \`mods\` directory containing the plugin module directly on \`--module-path\` at host startup if you want to prove the plugin is only brought into the **child layer** created by code; the command above puts only the API and host on the module path.

Expected output:

\`\`\`text
vi: Xin chào, Lan
\`\`\`

If the JAR is missing or the module name is wrong, resolution will fail. If the provider fails during initialization, an error can occur while iterating \`ServiceLoader\` or calling \`Provider.get()\`.

## 5. Why Is ServiceLoader.load(layer, service) Different from Other Overloads?

Java provides several ways to create a service loader:

| API | Discovery Starting Point | When to Use |
|---|---|---|
| \`ServiceLoader.load(Service.class)\` | Thread context class loader | Applications using classpath/TCCL or default mechanisms |
| \`ServiceLoader.load(Service.class, loader)\` | Specified class loader | Need to control the loader in classpath/module setups |
| \`ServiceLoader.loadInstalled(Service.class)\` | Platform class loader | Installed services visible via the appropriate loader |
| \`ServiceLoader.load(layer, Service.class)\` | Specified module layer and ancestor layers | Plugin systems using JPMS \`ModuleLayer\` |

The difference matters when the host uses multiple layers, has implementations in multiple places, or wants to restrict the discovery source. However, layer-based discovery **does not by itself guarantee only providers from the exact target plugin appear**: the API also searches ancestor layers. If you need precisely which providers belong to the current layer/plugin, check \`provider.type().getModule().getLayer()\` and corresponding metadata/allowlists.

The order of providers returned by \`ServiceLoader\` is not a business priority policy. For single-provider selection, fan-out, or pipelines, build a dedicated selection and ordering step after discovery.

## 6. Distinguishing Module Name, Service Type, and Class Identity

Errors during provider discovery usually do not stem from \`ServiceLoader.load\` syntax, but from how modules and class loaders are organized.

**The service type must be one shared \`Class\`** between host and plugin. If host and plugin each define their own copy of \`GreetingService\` via different loaders, having matching interface names does not guarantee a valid cast. Placing the API module in a shared parent layer is the standard pattern.

**The module root must exist in the finder.** \`Set.of("com.example.greeting.plugin")\` selects a JPMS module name, not a JAR filename or class name. \`ModuleFinder.of(Path.of("plugins"))\` must see a JAR or exploded module with a valid descriptor and no name conflicts.

**The provider must match the contract.** The service implementation must satisfy \`provides\` rules and the service type. In an explicit module, the module descriptor declaration governs provider publication; merely having an implementation class in the JAR is not enough.

**An already-created layer does not update automatically.** Copying a new JAR into \`plugins\` does not cause an old layer's \`ServiceLoader\` to discover the new module. To update dynamically, the host must construct a new finder/configuration/layer following the plugin manager's lifecycle.

## 7. Handling Faulty Providers and Selection Policies

When iterating \`ServiceLoader\`, a faulty provider can cause \`ServiceConfigurationError\`. Depending on the cause, class loading/linkage errors or exceptions from a constructor/provider method can also occur. Do not catch a broad exception and silently ignore every provider.

Policies to consider:

- **Fail-fast:** if all required providers must be valid, reject layer/plugin activation upon detecting an error.
- **Best-effort:** if the service is an optional observer, log the faulty provider and continue under a controlled mechanism without masking the incident.
- **Single provider:** select exactly one provider by \`pluginId\`, capability, version, or configuration; reject if there are no candidates or if ambiguous.
- **Pipeline:** apply the host's ordering/dependency metadata after discovery; do not rely on iteration order.
- **Hot reload:** build a new provider snapshot, run health checks, then route new requests through that snapshot; drain old work before releasing references.

Avoid performing business side effects in constructors whenever possible; prefer explicit lifecycle methods such as \`initialize\`, \`start\`, \`stop\`, and \`close\` so the host controls when the plugin may accept work.

## 8. Service Discovery and Security

This is easy to overlook in plugin runtimes: \`ModuleFinder\` and \`ModuleDescriptor\` let you read metadata without executing plugin logic, whereas \`ServiceLoader\` can instantiate provider objects and run code from the JAR.

Before calling \`Provider.get()\`, the host should verify:

1. The artifact comes from an authorized source, and metadata and signatures/hashes satisfy policy.
2. Module name, version, API dependencies, and service declarations match expectations.
3. There are no duplicate/conflicting modules or unauthorized providers.
4. Loaders/layers are created from verified artifacts, avoiding JAR replacement while in use.
5. Lifecycle, timeout, logging, and rollback policies exist if initialization fails.

JPMS governs module readability, exports, and opens; \`ModuleLayer\` is not a sandbox for untrusted code in the same JVM. For untrusted plugins, use process/container isolation and a communication protocol with the host.

## 9. Frequently Asked Questions

### Why does ServiceLoader return an empty list?

Check whether the provider module is present in the layer, whether \`module-info.java\` has the right \`provides\`, whether the service type is properly shared, whether the host module has \`uses\`, and whether the layer passed to \`load\` is the layer containing the provider. If using automatic modules or the classpath, provider declaration rules may differ from explicit modules.

### Do I need to export the implementation package?

Normally **no**, not solely for \`provides ... with ...\`. The Java service loader can instantiate providers in unexported implementation packages, while the host invokes them only through the API module's interface.

### Can ServiceLoader.load(layer, service) be called multiple times?

Yes. Each call creates a separate service loader with its own provider/instance cache per API rules. Do not assume they share singleton providers. On the same \`ServiceLoader\`, \`reload()\` clears the provider cache so the next iteration re-discovers within that layer's scope, yet **does not add new modules to an existing layer**.

### Does ServiceLoader sort by priority?

It does not handle business priority automatically. The host needs to read provider metadata and apply an explicit selector/sorter. Do not assign priority meaning to accidental discovery order.

### Can I create a layer per plugin?

Yes, if the dependency graph, class identity, and lifecycle allow it. However, loader/module overhead, shared API management, service visibility, and resources become more complex. Either one layer holding multiple plugins or multiple independent layers is a valid architectural choice; test dependency conflicts and hot reload behavior.

## 10. Implementation Checklist

- The API module exports the service interface and is shared by host and plugins.
- The host named module declares \`uses\`.
- The provider module declares \`requires\` for the API and \`provides\` for the implementation.
- The finder points to the right directory/JAR and the module root is exact.
- Configuration resolves cleanly against the parent module graph.
- The layer is defined with appropriate class loaders.
- \`ServiceLoader.load(layer, Service.class)\` uses the right layer object and service type.
- Providers are selected by explicit policy; duplicates, missing providers, and init failures are handled.
- Metadata/integrity is verified before executing provider code.
- Hot reload creates a new layer/snapshot and cleans up the old lifecycle.

**Remember:** \`ServiceLoader.load(layer, service)\` is the bridge from a **JPMS ModuleLayer** to **service providers**. It helps the host discover implementations according to the module graph, while complete plugin management still requires origin verification, dependency resolution, provider selection, and lifecycle control.