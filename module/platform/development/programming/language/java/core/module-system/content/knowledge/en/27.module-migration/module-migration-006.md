# Handling Reflection, ServiceLoader, and Resource Lookup

## 1. Why Should These Three Mechanisms Be Reviewed During Modularization?

When migrating an application from the classpath to the Java Platform Module System (JPMS), source code may still compile while several discovery or resource-access behaviors change. Areas commonly affected include:

- Frameworks using reflection to read private fields, invoke constructors, or create proxies.
- Applications discovering plugins or implementations using **ServiceLoader**.
- Code reading configuration files, templates, schemas, or metadata packaged inside JARs.
- Libraries scanning packages by enumerating resources through a classloader.
- Applications loading classes or modules by names read from configuration.

On the traditional classpath, many libraries assume all JARs reside in a relatively flat search space. With named modules, JPMS introduces readability boundaries, exports, opens, and module layers. Therefore, a class or resource existing inside a JAR does not guarantee other modules can locate or access it.

Three activities must be distinguished:

1. **Discovery:** finding implementations, classes, or resources.
2. **Loading:** loading classes or creating instances.
3. **Access:** being permitted to call APIs, read members, or open resource contents.

An error in one step is not necessarily fixed by granting permissions in another. For example, **opens** can allow deep reflection but does not register providers for ServiceLoader; **uses** declares a service consumer but does not turn a provider's package into a public API.

## 2. Inventorying Dependency Points Before Migration

Before adding module descriptors, locate dynamic mechanisms across the application and its libraries:

- Calls to **Class.forName**, **getDeclaredField**, **getDeclaredMethod**, **setAccessible**, or **trySetAccessible**.
- Calls to **ServiceLoader.load** and **META-INF/services** files.
- Calls to **Class.getResource**, **getResourceAsStream**, **ClassLoader.getResource**, or **getResourceAsStream**.
- Frameworks doing package scanning, annotation scanning, plugin registries, or class-name configuration.
- Class names, module names, and resource paths constructed from configuration strings.
- Plugins loaded in separate module layers or custom classloaders.

Classify each point by purpose. If discovering an SPI implementation, ServiceLoader is usually the right mechanism. If a framework needs access to private fields, identify the packages that must be opened. If simply reading configuration files, use resource APIs appropriate for the module holding those files.

Bytecode analysis tools like **jdeps** can help find static dependencies and some references to internal APIs, but cannot fully infer dynamically constructed class names, resource paths read from configuration, or all reflection behaviors. Confirm these points via source inspection, configuration review, and testing.

## 3. Reflection in Named Modules

Reflection still works in JPMS, but access permissions depend on module boundaries.

### Public API Access

If a library module wants to expose types to other modules, it must export the package:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

The framework module needs to read that module:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

The framework can invoke exported public methods. This is normal Java access and does not require opening packages for deep reflection.

### Deep Reflection into Private Members

Suppose a framework needs to read a private field on an entity:

~~~java
Field field = Customer.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
        "Package is not open for deep reflection"
    );
}

String email = (String) field.get(customer);
~~~

If the package containing **Customer** is not open to the framework module, **trySetAccessible()** may return false. If **setAccessible(true)** is called directly, the JVM may throw **InaccessibleObjectException**.

The module owning the entity can open the specific package to the framework:

~~~java
module com.example.model {
    exports com.example.model.api;

    opens com.example.model.entity
        to com.example.framework;
}
~~~

**exports** permits access to public types; **opens** permits deep reflection into the package. Targeted package opening keeps other implementation packages encapsulated.

If the framework runs from the classpath and belongs to the unnamed module, you can open the package at launch:

~~~bash
java \
  --add-opens com.example.model/com.example.model.entity=ALL-UNNAMED \
  -jar app.jar
~~~

If the framework is a named module, replace **ALL-UNNAMED** with the specific module name. **--add-opens** is a Java launcher runtime option; it does not replace API declarations and is not a javac fix option.

### MethodHandles and Proxies

Some frameworks use **MethodHandles.privateLookupIn** to gain access to non-public members. This mechanism is also subject to module encapsulation rules. The target class's package must be appropriately open to the module containing the lookup caller.

With proxies and reflection, check whether the framework generates proxies via public interfaces, subclassing, or accessing private implementations. Not every proxy failure requires opening an entire module. Exporting an API interface or opening a specific model package may suffice.

### Do Not Use Reflection to Access JDK Internal APIs

If a library accesses internal packages like **sun.*** or private fields inside JDK modules, prioritize upgrading the library and switching to public APIs. Strong encapsulation of JDK modules protects internal implementations from unstable dependencies.

You can use:

~~~bash
jdeps --jdk-internals path/to/library.jar
~~~

to locate some static references to internal APIs. Its output does not replace checking dynamic reflection call paths.

## 4. ServiceLoader in JPMS

ServiceLoader provides a mechanism to discover implementations against a declared service contract. It fits SPIs, plugins, and extension points where consumers do not want direct dependencies on each implementation.

Suppose an API module provides a service interface:

~~~java
package com.example.spi;

public interface PaymentProvider {
    String name();
    void pay(int amount);
}
~~~

The API module exports the package containing the interface:

~~~java
module com.example.payment.api {
    exports com.example.spi;
}
~~~

The consumer module declares **uses**:

~~~java
module com.example.payment.app {
    requires com.example.payment.api;

    uses com.example.spi.PaymentProvider;
}
~~~

The provider module declares the implementation:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.spi.PaymentProvider
        with com.example.payment.card.CardPaymentProvider;
}
~~~

Then the consumer locates providers:

~~~java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.pay(100);
}
~~~

In a named module, the module calling ServiceLoader must declare **uses** for the service. The provider module declares **provides ... with ...** in its module descriptor. The service interface must be exported so consumers can read and use that type.

If the application uses a separate **ModuleLayer** to load plugins, it can look up providers in that layer:

~~~java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(pluginLayer, PaymentProvider.class);
~~~

This matters for applications with dynamically loaded plugin modules. Calling **ServiceLoader.load(PaymentProvider.class)** and loading providers in a separate layer have different scopes; use the layer matching where plugins are defined.

### Providers on the Classpath

Unmodularized applications can still use ServiceLoader. Providers on the classpath are registered in a file:

~~~text
META-INF/services/com.example.spi.PaymentProvider
~~~

The file contains the fully qualified name of each provider, one class per line:

~~~text
com.example.payment.card.CardPaymentProvider
com.example.payment.wallet.WalletPaymentProvider
~~~

When converting a provider into a named module, this metadata is typically converted into a **provides** declaration in **module-info.java**. Do not maintain both registration mechanisms for the same provider unless there is an explicit compatibility need.

### Troubleshooting Undiscovered Providers

If ServiceLoader returns no providers, check in order:

1. Does the consumer declare **uses** for the exact service type?
2. Does the provider module declare **provides** for the exact interface?
3. Is the provider module on the module path or inside the module layer being searched?
4. Do the service interface module name and package match what both consumer and provider reference?
5. If the provider is on the classpath, are the **META-INF/services** path and class names accurate?
6. If using a custom layer, does the ServiceLoader call pass the right layer?

ServiceLoader does not scan every annotated class or every class implementing an interface. It uses registered service metadata. If the application uses package scanning to locate plugins, decide clearly whether to migrate to SPI/ServiceLoader or keep a framework-specific scanner.

## 5. Resource Lookup in Named Modules

Resources can be properties, XML, JSON, templates, schemas, images, or metadata packaged in JARs. When moving to modules, determine which package owns the resource and which module reads it.

### Using Class.getResourceAsStream

If the resource sits in the same package as the class, use a relative path:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream("config.properties");
~~~

A resource name without a leading **/** is interpreted relative to the class's package.

You can use an absolute path from the module root:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream(
        "/com/example/config/config.properties"
    );
~~~

This ties resource lookup to a specific class, useful when the resource belongs to the same module as the code consuming it.

### Using Module.getResourceAsStream

You can access the module containing the class directly:

~~~java
Module module = ConfigReader.class.getModule();

try (InputStream input =
         module.getResourceAsStream(
             "com/example/config/config.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Read the resource
}
~~~

The resource name is passed as a path from the module root, separated by forward slashes. The Module API helps code specify unambiguously which module a resource is searched in.

In a named module, resources inside an unopened package may be encapsulated against other modules. If a framework module needs to read internal resources of an application module, open the package containing the resources to the appropriate caller:

~~~java
module com.example.app {
    opens com.example.app.config
        to com.example.framework;
}
~~~

Opening a package also affects deep reflection access into that package. Therefore, place resources in dedicated packages and open them only to modules that need to read them.

### Using ClassLoader

Classpath applications often use:

~~~java
InputStream input =
    Thread.currentThread()
          .getContextClassLoader()
          .getResourceAsStream("config/app.properties");
~~~

This remains useful for libraries that need to respect an application or container's context classloader. However, do not assume classloader lookups will enumerate every resource packaged inside named modules. Resources in named modules are subject to JPMS encapsulation rules; lookup behavior depends on the resource location and module.

If a resource belongs to a specific module, prefer **Class.getResourceAsStream** or **Module.getResourceAsStream** to identify the owning module clearly.

### Resources Should Not Package Deployment Configuration

Configuration files may need to change across development, staging, and production. If a file must be edited by operators after build, consider reading from the filesystem, environment variables, or a deployment configuration service instead of hard-packaging it inside a module.

Internal resources are suitable for defaults, templates, or schemas shipped with the application. Secrets and environment-specific settings should not be embedded inside JARs.

## 6. Package Scanning and ClassLoader Limitations

Some frameworks discover classes by calling **ClassLoader.getResources("com/example/plugins")**, iterating over the returned URLs, and listing class files in directories or JARs. This often works on the classpath, but is not a general discovery model for named modules.

On the module path:

- Modules may not be represented as directories/JARs traversable the way classpath scanners assume.
- Resources and packages inside named modules may be encapsulated.
- A single classloader may not represent all module layers.
- Plugins may be loaded from separate layers or custom ModuleFinders.
- Class names constructed from configuration may not appear in static scan results.

If a framework requires package scanning, pick a version with JPMS support and verify how it inspects modules. Frameworks may use Module APIs, module layers, or **ModuleReader** to read module contents. Do not assume enumerating system classloader URLs is sufficient.

When building a new plugin system, ServiceLoader is usually easier to integrate with JPMS if each plugin supplies a clear SPI. If a framework needs annotation scanning across many component types, consult the framework documentation regarding the module path, opens, and resource scanning.

## 7. Combining Reflection, ServiceLoader, and Resource Lookup

A modular plugin can combine all three mechanisms in a clear flow:

1. The consumer module declares **uses** for the SPI.
2. The provider module declares **provides** with the implementation.
3. ServiceLoader discovers the provider in the appropriate module layer.
4. The framework reads provider metadata or resources via module-aware APIs.
5. If deep reflection into the implementation is required, the provider module opens the specific package to the framework.
6. Resources needing external access are opened in a targeted manner or exposed via public APIs.

Consumer example:

~~~java
module com.example.host {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

Provider:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.csv.CsvPlugin;

    opens com.example.plugin.csv.config
        to com.example.framework;
}
~~~

In this example, ServiceLoader finds **CsvPlugin** according to the provider declaration. The framework can read configuration in package **com.example.plugin.csv.config** if resources reside there and package opening permits it. If the framework only invokes public methods of Plugin, there is no need to open the implementation package for deep reflection.

Do not use reflection scanning instead of ServiceLoader if you only need to locate registered providers. Likewise, do not add **opens** to an entire module if the framework only needs to read a single configuration package.

## 8. Migration Workflow from Classpath to JPMS

You can proceed along these steps:

1. **Inventory:** locate all reflection, ServiceLoader, resource lookup, package scanning, and dynamic class loading sites.
2. **Classify:** identify which sites are SPIs, which require deep reflection, and which only read resources.
3. **Separate APIs:** move service interfaces into an API module with exported packages.
4. **Register providers:** add **uses** to consumers and **provides ... with ...** to provider modules.
5. **Limit reflection:** use public APIs when possible; if deep reflection is needed, open the specific package to the specific framework module.
6. **Migrate resources:** use Class or Module APIs for internal resources; use the filesystem or a configuration service for deployment settings.
7. **Check frameworks:** confirm scanners and classloaders support named modules and module layers.
8. **Verify the module graph:** confirm all modules and service providers are present on the required module path or layer.
9. **Test packaged artifacts:** run from modular JARs or runtime images, not solely from an IDE.
10. **Test dynamic code paths:** test plugins, reflection, resources, configurations, and features activated only in deployment environments.

You may keep some legacy libraries on the classpath during transition, but clearly track which belong to the unnamed module and which are named modules. Once libraries move to the module path, re-test resource scanning and access permissions because behavior can change.

## 9. Common Errors

**Class is found but setAccessible fails**

Check the module owning the class and the package containing the private member. Use **opens package to framework.module** or runtime **--add-opens** if deep reflection is needed.

**ServiceLoader does not find providers**

Check **uses**, **provides**, the module path, and the module layer. If the provider is on the classpath, check the **META-INF/services** file.

**Resource exists in the JAR but getResourceAsStream returns null**

Check the resource name, relative vs. absolute path, the module owning the resource, and package encapsulation. If the caller is in another module, the package may need to be opened to the caller.

**Package scanner does not see classes in a named module**

Check whether the framework supports JPMS/module layers or only scans classpath URLs. You can switch extension points to ServiceLoader or use a module-aware scanner.

**Works in the IDE but fails when running the JAR**

The IDE may run the application using the classpath or add extra access flags. Test using the exact module path command and module descriptors used in deployment.

**Plugin works on the module path but not in a runtime image**

The provider module may not have been included in the image, or the provider is discovered via configuration/reflection instead of service metadata. Check **jlink --bind-services**, **--add-modules**, and module layers at launch.

## 10. Takeaways

- **Reflection** must distinguish public access from deep reflection; **exports** and **opens** serve different purposes.
- **ServiceLoader** relies on **uses** and **provides** in named modules, or **META-INF/services** on the classpath.
- **ModuleLayer** matters when plugins are loaded dynamically into separate layers.
- **Class.getResourceAsStream** and **Module.getResourceAsStream** clearly identify the module holding a resource.
- Resources in a named module's packages may be encapsulated; open packages selectively when another module needs to read them.
- Classpath package scanning is not automatically equivalent to scanning on the module path.
- Testing must include modular artifacts and real dynamic execution paths.

When migrating to JPMS, describe providers clearly with service metadata, grant reflection access per package, and pick resource APIs matching the owning module. These three changes help applications retain plugin, framework, and configuration functionality while respecting module encapsulation boundaries.
