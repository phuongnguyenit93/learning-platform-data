# Designing Migration Boundaries for Legacy Systems

## 1. What is a migration boundary?

When migrating a legacy Java system from the classpath to the Java Platform Module System (JPMS), it is not necessary to modularize the entire application at once. You can define **migration boundaries**: the boundaries between parts already organized into modules and parts still running under the legacy classpath model.

A good migration boundary clearly defines:

- Which parts of the system already have module descriptors and are managed by the module graph.
- Which parts still belong to the unnamed module on the classpath.
- Which APIs are permitted to cross the boundary between the two sides.
- Which libraries are shared dependencies and which belong to a specific module.
- How reflection, service discovery, resources, and class loading are handled while both models coexist.
- The conditions under which a legacy part is promoted into a named module or retired.

The goal is to reduce migration risk while preserving the ability to build, deploy, and operate. Boundaries must be verifiable through source structure, module descriptors, build configuration, and tests.

Do not treat a migration boundary as merely placing a few JARs on the module path. A boundary is also an architectural contract: which module owns data, which APIs are exposed, who is allowed to call implementations, and how changes are rolled out safely.

## 2. Start with a system dependency map

Before drawing boundaries, inventory the components:

- Applications or services that can be built and deployed independently.
- Shared libraries and the versions currently in use.
- Packages accessed directly by multiple modules.
- Cross-layer call flows, especially database access or direct use of another module's implementation classes.
- Plugin mechanisms, reflection, `ServiceLoader`, resource lookups, and dynamic class loading.
- Dependencies on internal JDK APIs or legacy libraries.
- Modules that would form cyclic dependencies if separated.

You can start from the build tool's dependency tree, then use `jdeps` to analyze bytecode dependencies:

~~~bash
jdeps --summary build/libs/legacy-app.jar
jdeps --verbose:package build/libs/legacy-app.jar
jdeps --jdk-internals build/libs/legacy-app.jar
~~~

If the artifact needs external libraries, provide an appropriate classpath or module path for more complete analysis results. `jdeps` detects static references; reflection by class name, resource names read from configuration, and dynamically loaded plugins must still be inventoried separately.

The dependency map should capture both technical and business dependencies. Two packages can sit in the same JAR while belonging to two different responsibilities; conversely, two modules can be built separately while still tightly coupled to the same schema or database transaction.

## 3. Choose boundaries by responsibility and API

A useful boundary usually aligns with a capability or business responsibility, for example:

~~~text
legacy-system/
  app/
  customer/
  billing/
  reporting/
  integration/
  shared/
~~~

Initially, these directories may still be packages or projects within one build. Once dependency relationships are understood, each capability can be converted into a named module one at a time.

An illustrative modular structure:

~~~text
modules/
  com.example.customer.api/
  com.example.customer.core/
  com.example.billing.api/
  com.example.billing.core/
  com.example.legacy.adapter/
  com.example.application/
~~~

Each boundary should have a small, stable API. For example, if `billing` needs customer information, it should call the exposed customer API rather than directly importing customer's implementation classes, internal entities, or repositories.

The API module can contain shared interfaces and data types:

~~~java
module com.example.customer.api {
    exports com.example.customer.api;
}
~~~

The implementation module depends on the API:

~~~java
module com.example.customer.core {
    requires com.example.customer.api;
}
~~~

Consuming modules only need to read the API:

~~~java
module com.example.billing.core {
    requires com.example.customer.api;
}
~~~

This organization reduces reverse dependencies on implementations. It also provides a clear place to change customer's implementation without forcing `billing` to know internal details.

Do not create an API module for every class. Split an API only when there is a real contract that needs to be used by multiple components or remain stable across multiple deployments. Splitting too finely increases module count and graph management cost without improving boundaries.

## 4. Using the classpath as a compatibility zone during transition

A system can run named modules alongside legacy libraries on the classpath. Classes on the classpath belong to the **unnamed module** of the corresponding class loader.

This is a useful compatibility zone when libraries do not yet have module descriptors or cannot be converted immediately. Named modules can read the unnamed module, though a named module cannot name an unnamed module in a `requires` directive. Therefore, if a named module needs a legacy library's API, determine an appropriate dependency organization rather than trying to write `requires` for an unnamed module.

For example, a legacy library can continue to be loaded via the classpath while modularized parts of the application run as named modules. Keep runtime configurations consistent across development, test, and production environments.

Some library JARs without module descriptors can be recognized as **automatic modules** when placed on the module path. An automatic module derives its name from metadata or the JAR filename, unless its manifest supplies `Automatic-Module-Name`. It can serve as a stepping stone, though it is not always a good final boundary.

When using automatic modules:

- Check the actual module name using `jar --describe-module`.
- Prefer stable module names published by the library.
- Monitor exported packages and dependencies read automatically by the module.
- Avoid relying on an automatic module's broad default behavior as if it were an intentionally designed API.
- Plan to migrate to a named module with an explicit descriptor if the library is under your project's control.

The classpath, automatic modules, and named modules can coexist during migration. What matters is documenting the status of each library and never placing the same JAR on multiple loading paths simultaneously.

## 5. Designing adapters for legacy APIs

A safe way to establish a boundary is placing an adapter between the new system and the legacy library. The adapter translates data models, handles API differences, and isolates legacy rules.

For example, the legacy system provides an API:

~~~java
public class LegacyCustomerService {
    public LegacyCustomer findCustomer(String id) {
        // Legacy implementation
        return null;
    }
}
~~~

The new module defines a contract:

~~~java
package com.example.customer.api;

public interface CustomerLookup {
    CustomerView findById(String id);
}
~~~

The adapter implements the new API by calling the legacy system:

~~~java
package com.example.legacy.adapter;

public class LegacyCustomerAdapter implements CustomerLookup {
    private final LegacyCustomerService legacy;

    public LegacyCustomerAdapter(LegacyCustomerService legacy) {
        this.legacy = legacy;
    }

    @Override
    public CustomerView findById(String id) {
        LegacyCustomer oldValue = legacy.findCustomer(id);
        if (oldValue == null) {
            return null;
        }

        return new CustomerView(oldValue.getId(), oldValue.getName());
    }
}
~~~

In practice, add appropriate error handling, nullability, transactions, mapping, and logging. This illustrative example focuses on data type conversion and keeping legacy classes on the adapter side.

The module containing the adapter can depend on the new API and the legacy library as supported by the build:

~~~java
module com.example.legacy.adapter {
    requires com.example.customer.api;
}
~~~

If the legacy library is on the classpath, the build and runtime configurations must provide those classes to the adapter. If the library has been modularized, the adapter can declare `requires` on the corresponding module name.

The adapter should be the only place aware of legacy details that need to change. Do not let legacy classes leak into the new module's public API, as that causes the boundary to depend back on the legacy implementation.

## 6. Avoiding split packages when moving to named modules

A package scattered across multiple JARs on the classpath may have existed for years without causing obvious errors. When converting those JARs into named modules, **split packages** frequently cause problems because the same package cannot be arbitrarily split across multiple named modules in the same module layer.

For example, two libraries both contain:

~~~text
com/example/shared/Util.class
~~~

If both become separate named modules, the module system can reject graph resolution due to the shared package. Even if certain legacy classpath setups still run, do not treat split packages as a valid modular structure.

Remediation steps usually include:

1. Identify which JAR truly owns the package and classes.
2. Designate one module as the owner of that package.
3. Move shared classes into an API module or foundational module with a clear responsibility.
4. Update imports and dependencies so the remaining modules use the exported API.
5. Remove duplicate class copies from other artifacts.
6. Re-verify package lists and the module graph after packaging.

Do not create a `shared` module containing every class just to silence split-package warnings. A shared module must have a clear scope of responsibility; otherwise it becomes a central dependency hub and keeps the new boundaries tightly coupled.

## 7. Controlling cyclic dependencies

A poor boundary often shows up when module A needs B's implementation while B needs A's implementation. If two modules must `requires` each other, the module graph cannot resolve that cyclic dependency as a valid module relationship.

Cycles can be broken with an API or SPI:

~~~text
com.example.order.api
       ^          ^
       |          |
order.core    inventory.core
~~~

The API module holds stable interfaces and data types. Both implementation modules depend on the API in the right direction rather than importing each other's classes directly.

For example, the order module declares a service interface:

~~~java
package com.example.order.api;

public interface StockReservation {
    boolean reserve(String productId, int quantity);
}
~~~

The order module uses the SPI:

~~~java
module com.example.order.core {
    requires com.example.order.api;
    uses com.example.order.api.StockReservation;
}
~~~

The inventory module provides the implementation:

~~~java
module com.example.inventory.core {
    requires com.example.order.api;

    provides com.example.order.api.StockReservation
        with com.example.inventory.core.InventoryReservation;
}
~~~

Place the service API in a module with clear responsibility and avoid letting that API depend back on implementations. If the business relationship is genuinely cyclic, revisit how capabilities are split or identify an orchestration module coordinating both sides.

## 8. Managing reflection and deep access across boundaries

Legacy frameworks may use reflection to access private fields, constructors, or internal packages. When moving classes into named modules, these operations are governed by `exports` and `opens` rules.

If a module only exposes public APIs, use `exports`:

~~~java
module com.example.customer.core {
    exports com.example.customer.api;
}
~~~

If a framework needs deep reflection into an entity package, open the exact package to the framework module:

~~~java
module com.example.customer.core {
    exports com.example.customer.api;

    opens com.example.customer.entity
        to com.example.orm;
}
~~~

If the framework runs on the classpath, callers belong to the unnamed module. `--add-opens` can be used at runtime during the transition:

~~~bash
java \
  --add-opens com.example.customer.core/com.example.customer.entity=ALL-UNNAMED \
  -m com.example.application/com.example.application.Main
~~~

This should be an intentional configuration documented in deployment. Avoid opening entire modules or multiple JDK packages just to keep a legacy framework running.

A sustainable boundary should provide APIs or factories instead of forcing consuming modules to access private fields of an implementation. If an ORM or serializer is needed, specify which packages must be opened and to which modules right from the design phase.

## 9. `ServiceLoader` and plugins across boundaries

If a legacy system discovers plugins by scanning the classpath, it can migrate gradually to `ServiceLoader` once a clear SPI is in place.

The consumer module declares `uses`:

~~~java
module com.example.application {
    requires com.example.plugin.api;

    uses com.example.plugin.api.Plugin;
}
~~~

The provider module declares `provides`:

~~~java
module com.example.plugin.csv {
    requires com.example.plugin.api;

    provides com.example.plugin.api.Plugin
        with com.example.plugin.csv.CsvPlugin;
}
~~~

`ServiceLoader` discovers providers from service metadata. For providers on the classpath, use the corresponding `META-INF/services` file. For named modules, declare it in `module-info.java`.

If plugins are loaded in a separate `ModuleLayer`, look up providers in the proper layer:

~~~java
ServiceLoader<Plugin> plugins =
    ServiceLoader.load(pluginLayer, Plugin.class);
~~~

When creating a runtime image with `jlink`, `--bind-services` can link provider modules declared for services and their required dependencies. Providers selected by configuration or dynamic reflection may not be inferred by `jlink`; include the appropriate modules in the graph via link configuration.

`ServiceLoader` works well for SPIs with stable contracts. If a framework still relies on annotation scanning for other components, verify whether the framework supports the module path and module layers. Do not assume a classpath scanner will automatically see every named module.

## 10. Resource lookup and configuration across boundaries

Internal resources should be read from the module that owns them. If the resource sits alongside a class:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream("defaults.properties");
~~~

Or using a path from the package/module root:

~~~java
InputStream input =
    ConfigReader.class.getResourceAsStream(
        "/com/example/customer/config/defaults.properties"
    );
~~~

The `Module.getResourceAsStream` API also lets you specify the module containing the resource. Resources inside packages of a named module can be subject to encapsulation rules; if another module needs to access internal resources, consider opening the appropriate package or providing a resource-reading API.

Distinguish default resources from environment configuration:

- Default templates, schemas, or reference data can be packaged inside the module.
- Environment-specific configuration should be supplied from the filesystem, environment variables, or deployment configuration systems.
- Secrets and credentials should not be embedded in JARs.
- Do not let consuming modules directly read another module's internal files if an explicit configuration API can be provided.

When migrating resources from the classpath to modules, verify relative paths, resource names, owning packages, and class loaders. A file may still exist in the JAR yet no longer be found by URL scanning as before.

## 11. Organizing build and deployment during the mixed phase

During migration, the build must clearly specify which parts are module sources, modular JARs, automatic modules, or classpath libraries.

Example compiling a named module with libraries on the module path:

~~~bash
javac \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.application
~~~

Running the module:

~~~bash
java \
  --module-path "out:lib" \
  -m com.example.application/com.example.application.Main
~~~

On Windows, the module path separator is a semicolon instead of a colon.

If legacy JARs remain on the classpath, the runtime configuration must state both loading paths clearly. Avoid placing the same library on both the classpath and the module path. Duplicate classes or module names can cause hard-to-diagnose errors.

In CI, include separate steps:

1. Build and test legacy parts using the existing mechanism.
2. Build named modules and verify module descriptors.
3. Run integration tests across real boundaries.
4. Package the exact JARs/modules to be deployed.
5. Run tests on the module path or runtime image.
6. Verify JVM flags such as `add-opens`, service providers, and resources.
7. Record the module graph, dependency tree, and toolchain versions.

Do not test only inside an IDE if the IDE injects a classpath, module path, or VM options that differ from production.

## 12. Defining completion criteria for each boundary

A legacy portion should be considered migrated only when the required conditions are demonstrated:

- The module or project has a clear owner and responsibility.
- The public API is defined; internal implementations are not imported arbitrarily.
- The module descriptor properly declares `requires`, `exports`, `opens`, `uses`, and `provides`.
- No split packages or invalid cyclic dependencies remain.
- Reflection and resource lookups work under the real module configuration.
- Service providers are discovered in the correct module layer.
- Integration tests validate data and behavior across the boundary.
- Build and deployment are reproducible from packaged artifacts.
- Temporary runtime flags such as `add-opens` have an owner and a removal plan.
- Obsolete dependencies no longer in use have been removed from the build.

Completion criteria should be tied to a specific capability or module. There is no need to wait for the entire system to convert before recognizing that a boundary is stable.

## 13. Step-by-step migration roadmap

A practical roadmap may consist of:

1. **Inventory:** collect dependency trees, packages, reflection, services, resources, and class loaders.
2. **Choose boundary:** pick a capability with few cross-dependencies and a relatively clear API.
3. **Define contract:** create an API or SPI, separating required DTOs from legacy implementations.
4. **Add adapter:** isolate legacy APIs, mappings, and translation errors.
5. **Modularize:** add a module descriptor, declaring `requires` and `exports`.
6. **Resolve runtime access:** configure targeted `opens`, `ServiceLoader`, and resource lookups.
7. **Build and test:** run compilation, integration tests, and packaged runtime tests.
8. **Deploy gradually:** release per service or capability, monitoring logs and compatibility errors.
9. **Remove transitional paths:** once old consumers are gone, remove temporary adapters, automatic modules, or `add-opens`.
10. **Repeat:** choose the next boundary based on the updated dependency graph.

Start with a low-risk boundary with few incoming dependencies to validate the workflow. Once builds, tests, and deployments operate stably, apply the same approach to more complex capabilities.

## 14. Key takeaways

- A migration boundary defines the border between modular and legacy parts, along with the APIs allowed to cross it.
- The classpath can continue to coexist during transition; unnamed modules cannot be named in `requires`.
- Automatic modules are a useful compatibility step, but require a plan to move to explicit descriptors.
- Adapters isolate legacy APIs and translate data models.
- Split packages and cyclic dependencies must be resolved at the architectural level, not solely with command-line flags.
- Reflection requires purposeful `exports` or `opens`; `ServiceLoader` requires `uses`/`provides`; resources must be read from the proper module.
- Tests must run against packaged artifacts and production-like configurations.
- Every boundary should have completion criteria and a plan to retire transitional configurations.

A good migration boundary enables incremental conversion while preserving contracts between components. Prioritize stable APIs, clear adapter responsibilities, resolvable module graphs, and testing across real boundaries. Once a capability is independent and stably deployed, you can move on to the next boundary without rewriting the entire system at once.
