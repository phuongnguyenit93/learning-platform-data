# Service Binding with resolveAndBind

In JPMS, module resolution usually starts from a set of root modules and follows **requires** directives to locate required dependencies. However, a module may declare **uses** for a service without declaring a direct **requires** on the module providing the implementation. If resolution only follows ordinary dependencies, the provider module may not be included in the runtime configuration.

**Service binding** solves this case. When using **Configuration.resolveAndBind(...)**, the module system resolves the root modules and their dependencies, then locates provider modules for services declared as used by the resolved modules. Providers and the providers' dependencies are added to the configuration; the provider search continues if newly added providers in turn use other services.

It is important to distinguish three things: the descriptor declares the service contract, **resolveAndBind** includes provider modules in the configuration, and **ServiceLoader** discovers as well as instantiates providers when the application needs to use the service.

## 1. Why Is Service Binding Needed?

Suppose a reporting application knows only the **ReportExporter** interface. The application module declares that it needs the service:

~~~java
module com.acme.application {
    requires com.acme.report.spi;
    uses com.acme.report.spi.ReportExporter;
}
~~~

Another module supplies an implementation:

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;

    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

The application depends on the API module **com.acme.report.spi**. It does not declare **requires com.acme.csv.exporter**, because the goal is to allow replacing or adding providers without making the application module depend on each implementation.

If the configuration only resolves the root **com.acme.application** and its required dependencies, the provider module may not be included in the configuration. In that situation, the service contract exists and the application has declared **uses**, yet the provider module is not in the layer being searched.

Service binding allows the module system to locate observable provider modules for services needed by the resolved graph. This mechanism is useful for plugins, drivers, serializers, exporters, and other extension points.

## 2. Three Directives and APIs to Understand

### 2.1. uses

The **uses** directive is declared in the module that needs to find service implementations:

~~~java
module com.acme.application {
    requires com.acme.report.spi;
    uses com.acme.report.spi.ReportExporter;
}
~~~

It tells the module system which service type the module consumes. A service type is usually an interface or abstract class located in a stable API module.

A named module calling **ServiceLoader.load(...)** for a service must declare **uses** for that service in its descriptor. If that declaration is missing, using ServiceLoader from that module may fail with **ServiceConfigurationError**.

### 2.2. provides ... with ...

The provider module declares its implementation:

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;

    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

This directive registers a provider for the service type. The provider module must read the module containing the service API so the implementation can reference the contract.

The package containing the provider does not necessarily have to be exported to the application module. The application works against the service interface; the module system and ServiceLoader handle the provider using the metadata in the descriptor.

### 2.3. ServiceLoader

Once the provider module is present in the appropriate layer, the application locates providers using **ServiceLoader**:

~~~java
ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(ReportExporter.class);

for (ReportExporter exporter : exporters) {
    exporter.export(report);
}
~~~

In an application using a custom ModuleLayer, specify the layer in which to search for providers:

~~~java
ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(pluginLayer, ReportExporter.class);
~~~

ServiceLoader provides the mechanism to iterate over and instantiate providers according to how the provider is declared. Instantiation occurs when the application iterates the results or requests a provider; **resolveAndBind** does not instantiate providers and does not invoke their business logic.

## 3. How Do resolve and resolveAndBind Differ?

**Configuration.resolve(...)** resolves the root modules and dependencies according to declared module relationships. Modules are added only because they are roots or required dependencies in the graph.

**Configuration.resolveAndBind(...)** performs resolution together with service binding. After resolving the initial graph, the module system locates providers for services used by modules in the graph. Provider modules are added along with their dependencies. If a newly added provider in turn declares **uses** for another service, service binding can continue locating providers for that service.

| Criterion | resolve(...) | resolveAndBind(...) |
|---|---|---|
| Resolves root modules | Yes | Yes |
| Resolves dependencies via requires | Yes | Yes |
| Automatically adds providers for used services | Does not perform the service binding step | Yes |
| Adds dependencies of providers | No providers are added from a binding step | Yes, when a provider is brought into the configuration |
| Instantiates provider objects | No | No |
| Creates a ModuleLayer | No | No |

Service binding only considers provider modules observable from the module finder sources used during resolution. A provider outside the supplied module sources will not appear automatically. Merely having a JAR on the classpath does not turn it into a provider module in a named module configuration.

This keeps a clear boundary between locating modules at resolution time and loading provider instances when the application uses the service.

## 4. How Does the Service Binding Loop Work?

Suppose the initial graph has application module A:

- A declares **uses ServiceX**.
- Provider module PX declares **provides ServiceX with ProviderX**.
- PX in turn declares **uses ServiceY**.
- Provider module PY declares **provides ServiceY with ProviderY**.

When resolveAndBind runs:

1. Resolve root A and A's required dependencies.
2. Read the services declared as used by modules in the resolved graph.
3. Locate observable provider modules for those services.
4. Add PX and resolve PX's dependencies.
5. Because PX uses ServiceY, continue locating providers for ServiceY.
6. Add PY and PY's dependencies.
7. Continue until no new providers need to be added.

This process ensures the configuration contains indirect providers needed through chains of services. A provider is not included merely because it exists on the module path; it must provide a service used by a module in the graph.

One provider can provide multiple services. When multiple modules need the same service, a provider module resolved into the configuration is shared within that layer according to the layer's module identity.

## 5. Using Configuration.resolveAndBind in Java

The API can be invoked on a parent configuration, usually the boot configuration:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

Configuration parent = ModuleLayer.boot().configuration();

ModuleFinder applicationFinder =
    ModuleFinder.of(Path.of("app-mods"));

ModuleFinder providerFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.resolveAndBind(
        applicationFinder,
        providerFinder,
        Set.of("com.acme.application")
    );
~~~

Meaning of the parameters:

- **parent** is the existing configuration, in this example the boot layer's configuration.
- **applicationFinder** is the module source searched before the parent configurations during resolution.
- **providerFinder** is the module source searched after the parent configurations.
- **Set.of("com.acme.application")** specifies the root module to launch.

Both ModuleFinders must point to the actual observable modules in the deployment environment. Root names must match module names in the descriptors. If a dependency or provider cannot be found, or the graph has an error such as an invalid dependency, resolution will fail with the corresponding error.

With the overload taking a list of parent configurations, you can write:

~~~java
Configuration configuration =
    Configuration.resolveAndBind(
        applicationFinder,
        java.util.List.of(ModuleLayer.boot().configuration()),
        providerFinder,
        Set.of("com.acme.application")
    );
~~~

This overload is useful when the module configuration has multiple parent configurations. In the common case with a single parent, calling **parent.resolveAndBind(...)** is easier to read.

## 6. Creating a ModuleLayer from a Bound Configuration

**resolveAndBind** only returns a **Configuration**. To have the modules defined at runtime and be able to use ServiceLoader per layer, the application needs to create a ModuleLayer:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

ModuleLayer parentLayer = ModuleLayer.boot();

ModuleFinder applicationFinder =
    ModuleFinder.of(Path.of("app-mods"));

ModuleFinder providerFinder =
    ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parentLayer.configuration().resolveAndBind(
        applicationFinder,
        providerFinder,
        Set.of("com.acme.application")
    );

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(parentLayer),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer applicationLayer = controller.layer();

ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(applicationLayer, ReportExporter.class);

for (ReportExporter exporter : exporters) {
    exporter.export(report);
}
~~~

Read this flow in order:

1. Obtain the boot layer as the parent layer.
2. Create finders for the application modules and the provider/plugin modules.
3. Resolve the root module along with dependencies and service providers using **resolveAndBind**.
4. Define the configuration as a new layer using **defineModulesWithOneLoader**.
5. Obtain the layer from the controller.
6. Use **ServiceLoader.load(layer, serviceType)** to locate providers in that layer and relevant parent layers.
7. Iterate providers to instantiate them and invoke functionality.

In this example, the service interface **ReportExporter** must be the exact same API type read by both the application module and the provider module. Typically, the module containing the service API resides in the boot layer or is shared via a parent layer. If the host and plugin accidentally load two separate copies of the service API through different class loaders, they may have two different class identities and fail to communicate via the same service type.

## 7. Observing Bound Modules

After resolution completes, you can inspect the modules in the configuration:

~~~java
configuration.modules().stream()
    .map(resolvedModule -> resolvedModule.name())
    .sorted()
    .forEach(System.out::println);
~~~

If a provider module is present in the configuration, its name will appear in the resolved module set. You can inspect each module's descriptor to check service providers:

~~~java
configuration.modules().forEach(resolvedModule -> {
    System.out.println("Module: " + resolvedModule.name());
    System.out.println("Provides: "
        + resolvedModule.reference().descriptor().provides());
});
~~~

You can also observe the launcher's resolution process using the **--show-module-resolution** option. When you want the launcher to perform service binding for the module path, the **--bind-services** option can be used with an appropriate module configuration:

~~~bash
java --show-module-resolution --bind-services --module-path "app-mods;plugins" -m com.acme.application/com.acme.application.Main
~~~

The path separator in the example above is Windows's semicolon. On Linux/macOS, the module path normally uses a colon. When running via Gradle or Maven, ensure the actual launcher configuration passes the right module path and root module.

## 8. Conditions Required for Service Binding to Work

**resolveAndBind** does not automatically find arbitrary classes whose names resemble a service. The components need a consistent configuration:

- The module using the service declares **uses** for the exact service type.
- The provider module declares **provides ServiceType with ProviderType**.
- The provider module can be located by a ModuleFinder passed into the resolution process.
- The provider module has valid dependencies, including the module containing the service API.
- The service type referenced by the consumer and the provider must share the same module/type identity in the runtime configuration.
- The selected root modules must lead to the module using the service; if no module in the graph uses that service, the provider is not added simply because it sits in the plugin directory.
- When calling ServiceLoader with a specific layer, the provider must reside in that layer or a parent layer searched by the lookup mechanism.

If a provider does not appear, inspect the descriptor with **jar --describe-module**, verify that the finder points to the right directory, and then check **uses** and **provides**. If the provider is already in the configuration yet ServiceLoader still reports an error, check the service type, provider constructor/provider method, and class loader/layer.

## 9. Common Errors

| Symptom | Cause to Check | How to Fix |
|---|---|---|
| resolveAndBind does not add provider | No module in the finder provides a service used by the graph | Check **uses**, **provides**, and the provider's module path |
| Provider module not found | Finder points to wrong directory, wrong module name, or missing artifact | Check ModuleFinder and **jar --describe-module** |
| ServiceLoader reports module does not declare uses | The module invoking the service has not declared **uses** | Add the service type to the consumer's module-info.java |
| ServiceLoader cannot instantiate provider | Provider class or provider method does not follow rules, or dependencies are missing | Check the descriptor, constructor/provider method, and dependencies |
| Provider is in configuration yet not visible to the application | Wrong layer is being used or the service API has a different class identity | Use **ServiceLoader.load(layer, ServiceType.class)** and share the API from a parent layer |
| Resolution fails after adding provider | Provider dependency missing, duplicate module name, split package, or invalid graph | Fix the provider's dependency graph before creating the layer |
| Provider is not instantiated right after resolveAndBind | Resolution only adds modules to the configuration | Iterate ServiceLoader to request provider instances |

Do not work around errors by adding all plugins to the root set without defining the service contract. That makes the module graph directly coupled to implementations and undermines the benefits of service binding.

## 10. When Should You Use resolveAndBind?

Use **resolveAndBind** when the application wants to determine provider modules based on a service contract at configuration creation time, especially when providers are distributed separately or reside in a plugin directory.

Suitable cases:

- An application has multiple implementations for a service and wants to discover providers on the module path.
- Plugins can use other services, forming a chain of providers that must be fully resolved.
- An application wants to create a ModuleLayer containing root modules and bound provider modules.
- A packaging or runtime tool needs to determine the required set of provider modules from services used by the graph.

Use **resolve** when you want explicit control over the module set through roots and declared dependencies, without service binding automatically adding provider modules. Whichever you choose, layer creation and service instantiation remain separate steps.

## 11. Practice Exercises

1. Create an API module **com.acme.report.spi** with the **ReportExporter** interface and export the package containing the interface.
2. Create an application module declaring **requires com.acme.report.spi** and **uses com.acme.report.spi.ReportExporter**.
3. Create two provider modules, CSV and JSON; each module declares **provides** for the same service type.
4. Place the provider JARs in a separate plugin directory and create a ModuleFinder for that directory.
5. Resolve the application using **resolve(...)** and inspect which modules are in the configuration.
6. Replace it with **resolveAndBind(...)** and compare the provider modules added to the configuration.
7. Create a ModuleLayer from the bound configuration, then locate providers using **ServiceLoader.load(layer, ReportExporter.class)**.
8. Have one provider use a second service; create a provider for the second service and observe binding adding modules in a chain.
9. Try removing **uses** from the application module or removing **provides** from a provider module to observe the error and explain the cause.
10. Use **--show-module-resolution** and print **configuration.modules()** to confirm which modules are actually resolved.

## 12. Key Points to Remember

- **uses** declares a service that a module needs.
- **provides ... with ...** registers an implementation in a provider module.
- **resolve(...)** resolves root modules and dependencies via requires.
- **resolveAndBind(...)** performs resolution together with service binding, adding provider modules for services used in the graph.
- Service binding can continue through providers that use other services until no more new providers need to be added.
- **resolveAndBind** returns a Configuration; it does not create a ModuleLayer and does not instantiate provider instances.
- **ServiceLoader** locates and creates providers when requested by the application, typically using the overload taking a ModuleLayer in multi-layer architectures.
- Providers must be among the modules observable via finders and have valid dependencies/service descriptors.
- The service API must have the same class identity between host and provider.

Once you understand the differences between module resolution, service binding, layer definition, and provider instantiation, you can design plugin mechanisms around service contracts while keeping the application module independent of individual implementations.
