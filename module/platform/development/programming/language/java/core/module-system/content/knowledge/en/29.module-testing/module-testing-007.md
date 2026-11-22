# Testing Custom ModuleLayer

In the Java Platform Module System (JPMS), `ModuleLayer` allows an application to create a group of named modules at runtime, separate from the boot layer while linked to one or more parent layers. This mechanism is commonly used for plugins, extensions, systems loading multiple library versions, or environments requiring class loader control.

Testing a custom `ModuleLayer` is not just confirming `defineModulesWithOneLoader(...)` runs without throwing an exception. A reliable test suite must prove **which modules were resolved, which modules actually belong to the new layer, which modules are found via the parent, which class loader defines the classes, whether service providers are discovered in the right layer, and whether failure cases fail for the right reason**.

This lesson builds a small fixture with a host, a service API, and a plugin; performs a command-line runnable smoke test; and then expands into a checklist for integration, isolation, and compatibility testing.

## 1. Three Stages to Test Separately

A custom layer is created following this flow:

~~~text
Plugin JARs / exploded modules
            |
            v
       ModuleFinder
            |
            v
 Configuration.resolve(...)
 or resolveAndBind(...)
            |
            v
 ModuleLayer.defineModules...
            |
            v
       ModuleLayer
            |
            +--> Module objects
            +--> ClassLoader mapping
            +--> ServiceLoader discovery
~~~

Each stage has distinct test questions:

1. **Discovery:** Does `ModuleFinder` see the module JARs or exploded modules in the right directory?
2. **Resolution:** Does `Configuration` contain the expected root modules, dependencies, and service providers?
3. **Definition:** Does `ModuleLayer` define those modules with the right parents/class loaders and allow the application to use them?

A `FindException` before the layer is created differs from a `LayerInstantiationException` while defining the layer. A layer created successfully that fails to locate a provider belongs to service registration or discovery scope issues.

## 2. Designing the Fixture: API and Host in Parent, Plugin in Child Layer

For clear testing, build three modules:

~~~text
Boot layer
├── com.acme.spi
└── com.acme.host

Custom plugin layer
└── com.acme.plugin.hello
       |
       └── parent: Boot layer
~~~

Service API:

~~~java
// src/host/com.acme.spi/module-info.java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

~~~java
// src/host/com.acme.spi/com/acme/spi/Greeter.java
package com.acme.spi;

public interface Greeter {
    String greet(String name);
}
~~~

Host module:

~~~java
// src/host/com.acme.host/module-info.java
module com.acme.host {
    requires com.acme.spi;
    uses com.acme.spi.Greeter;
}
~~~

Plugin module:

~~~java
// src/plugins/com.acme.plugin.hello/module-info.java
module com.acme.plugin.hello {
    requires com.acme.spi;

    provides com.acme.spi.Greeter
        with com.acme.plugin.hello.HelloGreeter;
}
~~~

Implementation:

~~~java
// src/plugins/com.acme.plugin.hello/com/acme/plugin/hello/HelloGreeter.java
package com.acme.plugin.hello;

import com.acme.spi.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Intentionally **do not export** `com.acme.plugin.hello`. The host only needs the `Greeter` service type from the API module in the parent; the provider is instantiated by `ServiceLoader` per `provides` without the host importing the implementation class.

This fixture is ideal for testing: the shared API retains identical class identity, while the implementation is defined in a custom layer.

## 3. Compiling the Fixture with Separate Module Outputs

Directory layout:

~~~text
src/
├── host/
│   ├── com.acme.spi/
│   │   ├── module-info.java
│   │   └── com/acme/spi/Greeter.java
│   └── com.acme.host/
│       ├── module-info.java
│       └── com/acme/host/LayerSmokeTest.java
└── plugins/
    └── com.acme.plugin.hello/
        ├── module-info.java
        └── com/acme/plugin/hello/HelloGreeter.java
~~~

After writing the host code in the next section, compile:

~~~bash
javac --module-source-path src/host \
      -d out/host \
      -m com.acme.spi,com.acme.host
~~~

Compile the plugin with the host API on the module path:

~~~bash
javac --module-path out/host \
      --module-source-path src/plugins \
      -d out/plugins \
      -m com.acme.plugin.hello
~~~

Output:

~~~text
out/
├── host/
│   ├── com.acme.spi/
│   └── com.acme.host/
└── plugins/
    └── com.acme.plugin.hello/
~~~

When running the host, **put only `out/host` on the boot module path**. The plugin will be located via `ModuleFinder.of(Path.of("out/plugins"))` and defined afterward in a child layer. Accidentally adding `out/plugins` to the boot module path and making it a root would prevent the test from verifying dynamic plugin loading.

On Windows PowerShell, each command can be written on one line. When separating multiple module path entries, Windows uses `;`, while Linux/macOS uses `:`.

## 4. Creating the Custom Layer and Verifying Configuration

The smoke test class resides in named module `com.acme.host`:

~~~java
// src/host/com.acme.host/com/acme/host/LayerSmokeTest.java
package com.acme.host;

import com.acme.spi.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public final class LayerSmokeTest {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected plugin directory");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder plugins = ModuleFinder.of(Path.of(args[0]));

        Configuration configuration = boot.configuration().resolve(
            plugins,
            ModuleFinder.of(),
            Set.of("com.acme.plugin.hello")
        );

        if (configuration.findModule("com.acme.plugin.hello").isEmpty()) {
            throw new AssertionError("Plugin not resolved");
        }

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(boot),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer layer = controller.layer();

        verifyLayer(boot, layer);
        verifyServices(layer);

        System.out.println("CUSTOM LAYER TEST PASS");
    }

    private static void verifyLayer(ModuleLayer boot, ModuleLayer layer) {
        Module plugin = layer
            .findModule("com.acme.plugin.hello")
            .orElseThrow();

        Module apiFromLayer = layer
            .findModule("com.acme.spi")
            .orElseThrow();

        Module apiFromBoot = boot
            .findModule("com.acme.spi")
            .orElseThrow();

        if (plugin.getLayer() != layer) {
            throw new AssertionError("Plugin not owned by child layer");
        }
        if (!layer.modules().contains(plugin)) {
            throw new AssertionError("Plugin absent from layer.modules()");
        }
        if (layer.modules().contains(apiFromBoot)) {
            throw new AssertionError("Parent API was defined again");
        }
        if (apiFromLayer != apiFromBoot) {
            throw new AssertionError("API module identity was duplicated");
        }
        if (!layer.parents().contains(boot)) {
            throw new AssertionError("Missing boot parent");
        }
        if (!plugin.canRead(apiFromBoot)) {
            throw new AssertionError("Plugin cannot read API module");
        }
        if (!apiFromBoot.isExported("com.acme.spi", plugin)) {
            throw new AssertionError("API package not exported to plugin");
        }
    }

    private static void verifyServices(ModuleLayer layer) {
        List<Greeter> providers = ServiceLoader
            .load(layer, Greeter.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .filter(p -> p.getClass().getModule().getLayer() == layer)
            .toList();

        if (providers.size() != 1) {
            throw new AssertionError(
                "Expected one provider in plugin layer, got "
                + providers.size()
            );
        }

        String output = providers.get(0).greet("JPMS");

        if (!"Hello, JPMS".equals(output)) {
            throw new AssertionError("Unexpected provider result: " + output);
        }
    }
}
~~~

The example verifies the exact boundaries: the plugin belongs to the child layer, the API remains in the boot layer, the plugin reads the API, and the provider genuinely comes from the custom layer.

**Important:** `ServiceLoader.load(layer, Greeter.class)` can discover providers in the passed layer and its parents per API rules. Therefore, the example filters instances by `getModule().getLayer() == layer` before asserting there is only one plugin provider. Without filtering, a host-installed provider in the parent could cause the test to miscount.

## 5. Running the Smoke Test

Run the following command from the project directory after compiling host and plugin:

~~~bash
java --module-path out/host \
     -m com.acme.host/com.acme.host.LayerSmokeTest \
     out/plugins
~~~

Expected result:

~~~text
CUSTOM LAYER TEST PASS
~~~

Here:

- The host and service API are named modules launched from `out/host`.
- The plugin module sits under `out/plugins`, not initialized as a boot layer root.
- The host actively uses a finder to resolve the plugin and create a custom layer.
- The service provider is defined in the child layer and discovered via `ServiceLoader.load(layer, Greeter.class)`.

If an error occurs before reaching the PASS line, inspect the **failing stage**: finder, resolution, definition, discovery, or provider execution. Do not blindly add all modules to `--add-modules ALL-MODULE-PATH`, as that can invalidate the dynamic loading test configuration.

## 6. modules() vs. findModule() in Tests

Two APIs are easily confused:

- `layer.modules()` returns the modules **directly defined** in that layer.
- `layer.findModule(name)` searches the current layer **and its parent layers**.

With our fixture:

~~~java
boolean pluginHere = layer.modules().stream()
    .anyMatch(m -> "com.acme.plugin.hello".equals(m.getName()));

boolean apiHere = layer.modules().stream()
    .anyMatch(m -> "com.acme.spi".equals(m.getName()));

boolean apiVisible = layer.findModule("com.acme.spi").isPresent();
~~~

Expected results:

~~~text
pluginHere = true
apiHere    = false
apiVisible = true
~~~

A test that only calls `findModule` and concludes a module belongs to the child layer is **insufficient**. Check `getLayer()` or `modules()` to confirm ownership.

Similarly, `configuration.modules()` returns the `ResolvedModule`s belonging to the new configuration, whereas `layer.modules()` are the `Module` objects defined at runtime. Use both when a test needs to distinguish resolution from definition.

## 7. Checking Parent Layers and API Identity

A ModuleLayer can have multiple parents, so `parents()` is a list rather than a single parent.

For the example using only the boot parent:

~~~java
if (!layer.parents().equals(List.of(ModuleLayer.boot()))) {
    throw new AssertionError("Unexpected parent layers");
}
~~~

To avoid accidentally redefining the shared API, verify object identity:

~~~java
Module bootApi = ModuleLayer.boot()
    .findModule("com.acme.spi")
    .orElseThrow();

Module childView = layer
    .findModule("com.acme.spi")
    .orElseThrow();

if (bootApi != childView) {
    throw new AssertionError("Different API module objects");
}
~~~

This is a critical check in plugin architectures. If each plugin carried its own copy of the `Greeter` API in a different loader, objects with the same class name could still be distinct runtime types, causing cast errors or incompatibility between host and provider.

The sound design is placing the shared contract in the parent layer while plugins simply `requires` the shared API.

## 8. Checking the Class Loader Strategy

Depending on the layer definition API, modules in a child layer can use one class loader, multiple loaders, or application-provided loaders.

Typical options:

~~~java
ModuleLayer.defineModulesWithOneLoader(
    configuration,
    List.of(boot),
    ClassLoader.getSystemClassLoader()
);
~~~

~~~java
ModuleLayer.defineModulesWithManyLoaders(
    configuration,
    List.of(boot),
    ClassLoader.getSystemClassLoader()
);
~~~

For the same configuration, the two loader strategies can yield different class identities and isolation levels. Never assume "one layer always has one class loader".

Verify the actual loader:

~~~java
ClassLoader pluginLoader =
    layer.findLoader("com.acme.plugin.hello");

Class<?> impl = pluginLoader
    .loadClass("com.acme.plugin.hello.HelloGreeter");

Module pluginModule = layer
    .findModule("com.acme.plugin.hello")
    .orElseThrow();

if (impl.getModule() != pluginModule) {
    throw new AssertionError("Class belongs to wrong module");
}
if (impl.getClassLoader() != pluginLoader) {
    throw new AssertionError("Wrong class loader");
}
~~~

Note: `loadClass` only verifies class loading and identity. It does not prove a class in a non-exported package can be freely invoked via reflection. For plugin providers, use `ServiceLoader` through the service interface to preserve encapsulation.

## 9. Two Independent Custom Layers to Verify Isolation

An advanced test creates **two layers from the same plugin artifact**:

~~~java
ModuleLayer first = createPluginLayer(pluginDir);
ModuleLayer second = createPluginLayer(pluginDir);

Module p1 = first.findModule("com.acme.plugin.hello").orElseThrow();
Module p2 = second.findModule("com.acme.plugin.hello").orElseThrow();

if (p1 == p2) {
    throw new AssertionError("Expected different runtime modules");
}
if (p1.getClassLoader() == p2.getClassLoader()) {
    throw new AssertionError("Expected separate plugin loaders");
}
~~~

The `createPluginLayer` helper in this example must **genuinely create a new layer on every call** using `defineModulesWithOneLoader` or an equivalent strategy; never return a cached layer.

Test goals:

- Two runtime `Module`s can have the same name yet be distinct instances when in two independent layers.
- Plugin classes with the same fully qualified name in different loaders are distinct runtime types.
- The shared API in the boot parent retains a shared class identity, so the service interface used by the host to call the plugin is not duplicated.

Do not treat different loaders as proof of security isolation. A custom layer is not a sandbox and provides no CPU, filesystem, or network limits on plugin code.

## 10. Testing ServiceLoader with the Right Scope

Distinguish three overloads:

~~~java
ServiceLoader.load(Greeter.class);

ServiceLoader.load(Greeter.class, loader);

ServiceLoader.load(layer, Greeter.class);
~~~

The first overload uses the thread context class loader (TCCL), the second uses the specified class loader, and the third locates providers scoped to a ModuleLayer.

For custom layer tests, `load(layer, service)` usually expresses intent more accurately because it binds directly to the layer under test. Avoid accidentally calling `load(service)` and mistaking a missing provider for a `ModuleLayer` failure — TCCL may not see the new child layer.

**The caller module must declare `uses`** if the caller is a named module. In the example, `verifyServices` lives in `com.acme.host`, so the host descriptor has:

~~~java
uses com.acme.spi.Greeter;
~~~

If you move the `ServiceLoader` call into another named helper module, that helper module becomes the caller and must declare `uses`. That is a common cause of `ServiceConfigurationError` in tests.

## 11. Testing resolve and resolveAndBind

To build a configuration from a finder:

~~~java
Configuration cfg = boot.configuration().resolve(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin.hello")
);
~~~

`resolve` starts from root modules and required dependencies. Because `com.acme.plugin.hello` is an explicit root, it will be present if found and the graph is valid.

If the host needs to discover providers pulled in via `uses`, consider `resolveAndBind`:

~~~java
Configuration cfg = boot.configuration().resolveAndBind(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin.hello")
);
~~~

`resolveAndBind` performs service binding for services used by modules in the configuration. Tests should distinguish whether a provider entered because it was a **root** or was pulled in by **service binding**.

To genuinely verify service binding, build a fixture with a consumer module in the new configuration declaring `uses` and another provider module outside direct roots/dependencies. Then compare `configuration.modules()` between `resolve` and `resolveAndBind`. Avoid concluding binding works just because a provider already named as a root appears.

Additionally, every provider must be within the observable scope of the module finder. Service binding does not automatically locate JARs outside the configured module sources.

## 12. Failure Test: Non-Existent Module

An important negative test requests a root that cannot be found:

~~~java
ModuleFinder plugins = ModuleFinder.of(Path.of("out/plugins"));

try {
    ModuleLayer.boot().configuration().resolve(
        plugins,
        ModuleFinder.of(),
        Set.of("com.acme.plugin.does.not.exist")
    );

    throw new AssertionError("Expected resolution failure");
} catch (java.lang.module.FindException expected) {
    System.out.println("Missing module detected");
}
~~~

The `FindException` happens during resolution, **before** layer creation. Do not assert `LayerInstantiationException` for a module that cannot be found at all.

You can expand with scenarios:

- Plugin declares `requires` on a non-existent module.
- Plugin and dependency have incompatible versions/classifications.
- A module has the wrong name in `ModuleFinder` due to JAR packaging or directory layout.
- Provider module is placed on the wrong module path so the finder does not discover it.

Negative tests should verify the **failure type and key diagnostic details**, avoiding brittle assertions on full exception message strings that may vary across JDK versions.

## 13. Failure Test: Package, Module, and Layer Definition Conflicts

Besides missing modules, a module graph can be invalid due to package or loader conflicts.

Scenarios that warrant dedicated fixtures:

1. Two modules in the same configuration cause a package conflict under JPMS rules.
2. Modules resolve successfully yet cannot be defined in the layer under the chosen loader strategy.
3. A class loader is asked to define modules with invalid layout/packages.
4. A module descriptor declares dependency/readability conflicting with the parent configuration.

Errors may be `ResolutionException` during resolution or `LayerInstantiationException` during definition, depending on the scenario. Do not expect the same exception for all cases.

Sample splitting the two phases:

~~~java
Configuration configuration = boot.configuration().resolve(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin.hello")
);

// Errors thrown at this step are definition/layer setup errors.
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );
~~~

When reporting failures, keep stack traces from the resolver and from layer definition separate to diagnose the true cause. Do not bypass errors by dumping all JARs onto the classpath if the test aims to verify JPMS boundaries.

## 14. Checking Readability, exports, and opens

A plugin in a child layer might see an API from the parent yet still be unable to use a package due to missing readability or exports.

Runtime checks:

~~~java
Module plugin = layer.findModule("com.acme.plugin.hello")
    .orElseThrow();

Module api = layer.findModule("com.acme.spi")
    .orElseThrow();

boolean readable = plugin.canRead(api);
boolean exported = api.isExported("com.acme.spi", plugin);

System.out.println("canRead=" + readable);
System.out.println("exported=" + exported);
~~~

With the fixture, both must be true. However, `canRead` and `isExported` do not replace testing actual provider behavior. If a provider throws in its constructor or misses a resource, the layer can still be defined and module permissions remain valid.

When a framework needs deep reflection into a plugin package, verify `opens` for the module performing reflection. For modules defined by a custom layer, runtime configuration can be intentionally adjusted via `ModuleLayer.Controller.addOpens(...)` if the layer owner permits it:

~~~java
controller.addOpens(
    pluginModule,
    "com.acme.plugin.hello",
    hostModule
);
~~~

This illustrative call requires `pluginModule` to belong to the layer managed by `controller` and the package to actually exist in that module. Open packages only when a framework has an explicit reflection need. Never automatically open all packages just for test convenience.

## 15. Testing Resource Loading

Not all plugins contain only classes. Some also include templates, JSON, text, configuration, or certificates.

Example resource:

~~~text
src/plugins/com.acme.plugin.hello/
└── com/acme/plugin/hello/
    ├── HelloGreeter.java
    └── greeting.txt
~~~

When compiling with `javac`, non-Java resources may require a separate copy step into the module output. Confirm the file exists in the artifact/plugin directory used at runtime.

A test can ask the provider to read a resource belonging to its own module and return a known result. This thoroughly checks:

- Whether the resource was packaged.
- Whether class loader/module resource lookup finds the right file.
- Consistent encoding, e.g., UTF-8.
- That module encapsulation does not block an unexpected access.
- That the plugin runs properly with real packaging, not only inside the IDE.

Do not merely check that the resource exists in the source directory; runtime usually executes from exploded module output or modular JARs, where resources can be omitted.

## 16. Testing Multiple Plugins and Provider Lists

If the configuration contains multiple providers:

~~~text
com.acme.plugin.hello
com.acme.plugin.goodbye
com.acme.plugin.echo
~~~

The test suite must verify the **expected set of providers**, without relying on iteration order.

Example:

~~~java
Set<String> providerModules = ServiceLoader
    .load(layer, Greeter.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(p -> p.getClass().getModule().getLayer() == layer)
    .map(p -> p.getClass().getModule().getName())
    .collect(java.util.stream.Collectors.toSet());

Set<String> expected = Set.of(
    "com.acme.plugin.hello",
    "com.acme.plugin.goodbye",
    "com.acme.plugin.echo"
);

if (!providerModules.equals(expected)) {
    throw new AssertionError("Unexpected providers: " + providerModules);
}
~~~

Do not assert "the first provider is X" if the business contract defines no ordering. Provider discovery order is not a reliable plugin prioritization mechanism to use instead of explicit configuration.

When a single module provides multiple implementations for the same service, checking only the module name may be insufficient. In that case, compare class names or specific provider metadata.

## 17. JUnit 5: Organizing the Test Harness

The fixture can be invoked by a test runner, JUnit, or a smoke test command in CI. When using JUnit with a modular project, pay attention to which module calls `ServiceLoader.load` and the test engine's reflection permissions.

Two practical approaches:

- **Integration test as an external consumer:** test/host module calls a public entry point and verifies the result. This reflects the real system and reduces the need to open packages.
- **Tests patched into the host module:** use `--patch-module` at compile/test time if access to package-private helpers inside the host is needed. With a framework on the classpath, appropriate `--add-reads` and `--add-opens` may be needed for the framework to invoke tests.

Conceptual test method example:

~~~java
@Test
void pluginProviderIsLoadedFromChildLayer() {
    ModuleLayer layer = createPluginLayer(pluginOutputDirectory);

    long count = ServiceLoader.load(layer, Greeter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(p -> p.getClass().getModule().getLayer() == layer)
        .count();

    assertEquals(1L, count);
}
~~~

This is an assertion structure template; add JUnit imports, fixture setup, and your project's module/test-runner options. If the test class lives in a different named module than the host and calls `ServiceLoader` directly, that test module must declare `uses com.acme.spi.Greeter`.

Keep test fixtures and plugin sources separate from production artifacts. Never export internal packages in production descriptors just to make testing easier.

## 18. CI: Running on the Right Artifacts and JDK

A test pipeline should include:

~~~text
compile host and SPI modules
    |
compile plugin modules
    |
inspect descriptors and dependency graph
    |
run custom layer smoke test
    |
run negative tests
    |
run plugin service/resource tests
    |
package modular JARs
    |
run smoke test on packaged artifacts
~~~

Helpful diagnostic commands:

~~~bash
jar --describe-module --file plugins/com.acme.plugin.hello.jar
~~~

~~~bash
jdeps --module-path out/host:out/plugins \
      --print-module-deps \
      plugins/com.acme.plugin.hello.jar
~~~

On Windows, `--module-path` with multiple entries uses `;`, not `:`.

Be sure to compare two cases: running from exploded module output and running from modular JARs. Testing only from output directories can miss packaging bugs such as missing resources, descriptors omitted from JARs, or mismatched filenames/module names.

There is no need to evaluate the entire README quality within this test execution workflow; the goal here is to validate the ModuleLayer technique built by the application.

## 19. Cleanup, Caching, and Lifecycle

A `ModuleLayer` has no closing API like `AutoCloseable.close()`. When tests create many new layers, manage references to:

- `ModuleLayer` and `Module`.
- Custom `ClassLoader` instances.
- `ServiceLoader` and cached provider instances.
- Threads, executors, timers, or callbacks spawned by plugins.
- Static registries, listeners, or contexts holding class loaders.

`ServiceLoader.reload()` only clears that loader's provider cache; it does not modify the module graph or reload bytecode in an existing layer. To test a new plugin version, you usually must create a new configuration/layer with an appropriate class loader.

Releasing references facilitates garbage collection, yet never write tests assuming classes/plugins are guaranteed to be unloaded at a specific moment. Stop threads and close plugin-owned resources before ending the fixture.

When running multiple tests in parallel, use isolated output/fixture directories so one test does not overwrite JARs or delete resources while another test builds a layer.

## 20. Recommended Test Matrix

| Test Case | Primary Check | Expected Outcome |
|---|---|---|
| Load valid plugin | Finder, resolution, definition | Child layer is created |
| Module ownership | `layer.modules()` and `getLayer()` | Plugin belongs to child layer |
| Parent visibility | `findModule` and `parents()` | Shared API found via parent |
| API identity | Compare `Module` objects | Parent API is not duplicated |
| Readability/export | `canRead` and `isExported` | Contract access rights are accurate |
| Provider discovery | `ServiceLoader.load(layer, service)` | Provider in right layer, right behavior |
| Class loader mapping | `findLoader` and `Class.getClassLoader` | Loader matches strategy |
| Missing module | `resolve` with non-existent name | `FindException` |
| Invalid graph | Conflicting fixture | Resolution/definition fails at right stage |
| Multiple providers | Compare provider set | All expected providers, order-independent |
| Resource loading | Templates/configs in plugin artifact | Resources are readable |
| Two independent layers | Define plugin twice | Module/loader identities are separate |
| Packaged modular JAR | Run with packaged artifacts | Same results as exploded modules |
| Plugin lifecycle | Clean up threads/registries/services | No leaked resources pinning the test process |

## 21. Diagnostic Workflow When Tests Fail

When a test fails, investigate in order:

1. **Check module path:** are API and host on the boot path; is the plugin in the plugin finder path?
2. **Check descriptor:** use `jar --describe-module`; are module name, `requires`, `provides`, and service type right?
3. **Check resolution:** does `configuration.findModule(name)` return a match; are any dependencies missing?
4. **Check definition:** did `defineModulesWithOneLoader` or another strategy hit loader/package conflicts?
5. **Check parent:** is the shared API module the exact same instance as in the boot layer?
6. **Check permissions:** can the plugin read the API and does the API export the package to the plugin?
7. **Check service discovery:** does the caller named module have `uses`; does the provider have `provides` in the right layer?
8. **Check class loader:** do TCCL, `findLoader`, and class identity match the design?
9. **Check resources:** does the plugin JAR/output contain all resources and runtime dependencies?
10. **Check lifecycle:** are caches/providers/threads from a prior test affecting the current test?

A provider-not-found error is not necessarily a `ModuleFinder` error: the module may have been defined properly while `ServiceLoader` was called with the wrong overload or mismatched service metadata. Similarly, a plugin class might load yet remain inaccessible from the host due to an unexported package; that may be intended encapsulation behavior.

## 22. Takeaways

To test a custom `ModuleLayer` reliably, verify **all three stages: discovery → resolution → definition**, then confirm runtime ownership, parent visibility, module identity, class loader mapping, and service provider behavior. Keep the shared service API in the parent layer, keep implementations in plugin modules in child layers, and discover them via `ServiceLoader.load(layer, service)`.

`layer.modules()` counts only modules directly belonging to the layer, whereas `findModule()` also searches parents. Test `resolve` separately from `resolveAndBind`, and do not confuse a root provider with a provider pulled in via service binding. Use negative fixtures for missing modules and conflicting graphs; run tests on both exploded outputs and real modular JARs.

A custom layer is not a security sandbox, does not automatically reload/unload plugins, and does not override readability, exports, or opens boundaries. A valuable test suite clearly confirms **which module is defined where, which provider runs, which error is caught at which stage, and that the deployment configuration is reproducible**.