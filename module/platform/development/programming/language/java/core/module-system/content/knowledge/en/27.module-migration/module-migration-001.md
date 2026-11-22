# Assessing a Classpath Application Before Modularization

## 1. Why Assess Before Migrating to JPMS?

The Java Platform Module System (JPMS) adds explicit module boundaries to Java applications: each named module has a descriptor, declares dependencies via `requires`, publishes packages via `exports`, and governs deep reflection access via `opens`. By contrast, a traditional classpath application typically only needs a collection of JARs and classes placed on the class loading path.

Migrating from the classpath to the module path is not simply switching a JVM flag. Many things that the classpath permits may be invalid in the module graph, for example:

- Different JARs containing classes that belong to the same package.
- Code in library A accessing a public class that belongs to an internal package of library B.
- Two libraries referencing each other mutually without clear module boundaries.
- Frameworks using setAccessible(true) on private constructors or fields.
- Providers discovered from META-INF/services, configuration, or string-based class names.
- Some dependencies appearing only at runtime through plugins, reflection, or custom class loaders.
- The application using JDK internal packages that have become strongly encapsulated.
- Builds using fat JARs that strip away information about individual libraries and service descriptors.

Therefore, the goal of the assessment phase is to build a **dependency and compatibility risk map**, and then determine an appropriate migration order. You should only write module-info.java once you understand what components the application depends on and how they are loaded.

## 2. Identifying the Current State of the Application

Before using JPMS tools, document how the system currently runs:

| Inventory item | Example questions |
|---|---|
| Java version | Which JDK is used to build, and which JRE/JDK runs in production? |
| Main artifact | Is it run with -cp, -jar, an executable JAR, a WAR, or a container? |
| Dependencies | How many direct, transitive, optional, and test-only JARs are there? |
| Frameworks | Are there Spring, Hibernate, Jackson, CDI, logging, or bytecode agents? |
| Dynamic class loading | Are there Class.forName, ServiceLoader, URLClassLoader, or a plugin manager? |
| Native integration | Are there JNI, JNA, native images, native libraries, or agents? |
| Packaging | Does it use Maven Shade, Gradle Shadow, a distribution ZIP, or a Docker image? |
| Deployment requirements | Are a custom runtime image, size reduction, or separate plugin layers needed? |
| Compatibility contracts | Are there legacy binary APIs, serialization, configurations, and data to preserve? |

The output should be an inventory table containing artifact name, version, source, function, modular status, key packages, and the owner responsible for upgrading.

Do not only inventory dependencies declared in pom.xml or build.gradle. A library might be copied manually into a lib directory, loaded by class name from a configuration file, or loaded by plugins themselves at runtime. Those dependencies must also appear in the catalog.

## 3. Locking Down a Reproducible Baseline

Before modularizing, run the classpath application as-is and record the evidence:

1. JDK version and vendor.
2. Actual build and run commands.
3. List of JARs along with checksums or versions.
4. Test suite and critical use cases.
5. Representative input/output data.
6. Startup logs, plugin discovery, service discovery, and access warnings.
7. Startup time, memory, and throughput at levels that need monitoring.

Example of running a classpath application:

~~~bash
java -cp "app.jar:lib/*" com.acme.legacy.Main
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "app.jar;lib/*" com.acme.legacy.Main
~~~

If using an executable JAR with java -jar, do not assume external classpath arguments behave the same as when running with -cp. You need to inspect the manifest Main-Class, Class-Path, fat JAR structure, and the product's actual launcher.

A baseline is the yardstick for knowing whether an error comes from module changes or already existed beforehand. Do not upgrade the Java version, replace major frameworks, and modularize everything in a single change unless you have sufficient testing to isolate causes.

## 4. Mapping Static Dependencies with jdeps

jdeps is a tool that analyzes dependencies at the class/package/module level from Java bytecode.

Analyzing a JAR:

~~~bash
jdeps --summary app.jar
~~~

Performing a deep analysis with dependencies located in the lib directory:

~~~bash
jdeps --recursive \
      --class-path "lib/*" \
      app.jar
~~~

Viewing detailed dependencies down to the class level:

~~~bash
jdeps --verbose:class \
      --class-path "lib/*" \
      app.jar
~~~

Getting the list of module dependencies inferred by the tool:

~~~bash
jdeps --print-module-deps \
      --class-path "lib/*" \
      app.jar
~~~

During this phase, pay attention to:

- Which dependencies are Java SE/JDK modules.
- Which dependencies come from external libraries.
- Which packages are used in public signatures.
- Which classes reference implementation types of another library.
- Which dependencies appear only indirectly.

jdeps is not an absolute source of truth on its own: it analyzes references observable from bytecode, but cannot fully infer class names constructed from strings, dependencies loaded via reflection, service files, JNI, or runtime plugins. Combine its results with your inventory and testing.

## 5. Checking Internal JDK APIs Before Migrating

One of the barriers when upgrading the JDK or using named modules is depending on internal JDK APIs.

Run:

~~~bash
jdeps --jdk-internals --recursive \
      --class-path "lib/*" \
      app.jar
~~~

If the tool points out classes belonging to sun.*, jdk.internal.*, or unsupported implementation packages, record the call site and the module/JAR owning that code.

Remediation approach:

- Prefer the corresponding public Java API.
- Upgrade libraries to versions that have removed dependencies on JDK internal APIs.
- Isolate the integration part if it cannot be replaced immediately.
- Only use narrowly scoped --add-exports or --add-opens as a transitional step.

For example, replace legacy Base64 APIs with java.util.Base64, atomic operations with java.util.concurrent.atomic or VarHandle, file/buffer operations with java.nio, and cryptographic operations with java.security or javax.crypto.

Not every internal API has a one-to-one replacement. When switching from an internal API to a public API, compare performance, memory ordering, resource lifetime, and compatibility behavior—do not merely rename classes so the code compiles.

## 6. Classifying Each JAR by Modularization Readiness

Each dependency should be tagged with one of the following statuses:

**Explicit named module:** A JAR that has module-info.class with an explicit descriptor. The module name, requires, exports, opens, uses, and provides are declared in the descriptor.

**Automatic module:** A JAR without an explicit descriptor that is placed on the module path and recognized by Java as an automatic module. The module name can come from Automatic-Module-Name in the manifest or be derived from the JAR filename. An automatic module exports all of its packages and has broader transitive readability rules than an explicit module.

**Classpath library / unnamed module:** A JAR still used on the classpath. Classes on the classpath belong to the unnamed module of the corresponding class loader and cannot be referenced by a module name in requires.

Inspecting an artifact:

~~~bash
jar --describe-module --file lib/example.jar
~~~

If the JAR does not contain a descriptor, the command can show the derived automatic module name. A JAR with Automatic-Module-Name is not yet an explicit module: the manifest entry provides a stable module name when used on the module path, but does not replace module-info.class.

When migrating, do not assume every library can be placed on the module path without changes. Watch especially for split packages, the default package, incompatible dependencies, and code relying on classpath discovery.

## 7. Checking Module Name Stability

An automatic module may have a name derived from the JAR filename. For instance, artifact names changing by version or normalization rules can result in a different module name than expected.

For libraries that are not yet explicitly modularized but need to be used on the module path, prefer versions that have a fixed Automatic-Module-Name maintained by the vendor.

A consumer named module needs to requires the exact module name:

~~~java
module com.acme.app {
    requires com.acme.reporting;
}
~~~

If the actual library artifact is recognized under a different name, resolution will fail.

For external dependencies, avoid committing a module descriptor to source before confirming a stable module name in the target release version.

Whenever possible, upgrade to an explicit module version of the library published by the maintainers themselves rather than renaming JARs manually with uncontrolled rules.

## 8. Detecting Split Packages

The classpath allows multiple JARs to contain classes in the same package. A named module graph generally does not allow a module to read packages with the same name from multiple different modules in a conflicting manner.

Example:

~~~text
lib/
  order-api.jar
    com/acme/order/Order.class
  order-impl.jar
    com/acme/order/DefaultOrderService.class
~~~

Two artifacts share the package com.acme.order. If you try to turn them into two separate named modules, you may encounter a split package error or module resolution/layer instantiation failure.

Remediation approach:

1. Identify all JARs containing the same package.
2. Check whether they are intentionally a single library split across build artifacts.
3. If they are effectively the same logical module, consider merging the code/artifacts into one named module.
4. If they are independent components, restructure the package on one side and update imports.
5. For third-party libraries, prefer newer versions that have resolved the issue.
6. Check especially packages generated by code generation, annotation processors, and shading.

Do not fix a split package by adding --add-exports. Exporting does not change package ownership between modules.

## 9. Detecting Dependency Cycles

A classpath system may contain bidirectional reference relationships:

~~~text
billing -> customer
customer -> billing
~~~

When turned into two separate explicit named modules:

~~~java
module com.acme.billing {
    requires com.acme.customer;
}
~~~

~~~java
module com.acme.customer {
    requires com.acme.billing;
}
~~~

a requires cycle cannot form a valid module configuration.

Analyze cycles at the package/class level before choosing module boundaries. Some ways to break a cycle:

- Extract shared interfaces or data types into a small API module.
- Invert the dependency direction via interfaces and dependency injection.
- Use events, callbacks, or service contracts to avoid bidirectional implementation imports.
- Merge two groups of classes into one module if they truly share the same lifecycle and release cadence.

Do not mechanically create one module per existing JAR. Module boundaries should reflect intentional dependency directions and API contracts.

## 10. Assessing Public APIs and Package Visibility

On the classpath, code can import a public class from any package if that class can be found and access modifiers permit it. With JPMS, a named module only exposes a package to consumers if there is a matching exports directive.

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

If the application imports com.acme.customer.internal.DefaultCustomerRepository, then after modularization, that import may be blocked because the internal package is not exported.

Before writing descriptors, classify packages:

- **Public API:** types officially used by other consumers.
- **SPI:** service types or extension points.
- **Internal implementation:** not intended for consumers to depend on directly.
- **Generated/integration package:** needs inspection of actual frameworks and build setup.

The output should include the list of packages to export and the list of consumers that must be updated to stop depending on implementation details.

Every module does not need to export all packages. Specify exports based on the API you want to support long-term; qualified exports can be suitable if a package is meant only for a known set of named modules.

## 11. Reflection and Frameworks as a Dedicated Risk

Serializer, ORM, dependency injection, or test runner frameworks may instantiate objects and read fields/constructors using reflection. JPMS distinguishes:

- exports: allows normal access to public types in a package.
- opens: allows deep reflection according to the declared scope.
- open module: opens all packages of the module for deep reflection.
- --add-opens: opens a package at runtime to the specified target module.

Example of models processed by a serialization framework:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.model to com.fasterxml.jackson.databind;
}
~~~

The example above is only valid if the framework's actual module name is com.fasterxml.jackson.databind in the configuration the application uses; you must verify the JAR's module name.

Questions to check:

- Does the framework look up private constructors/fields with setAccessible?
- Does it use proxies, subclass generation, method handles, or bytecode enhancers?
- Does the test framework need test packages opened when running on the module path?
- Does any library choose its own ClassLoader or context class loader?
- Is any package being opened completely just because one specific access is missing?

Do not turn every package into opens or make the entire module open just to avoid updating frameworks. Upgrade to frameworks that support JPMS and open the right packages to the right consumers when needed.

## 12. ServiceLoader and Provider Configuration

The classpath typically registers service providers via a file:

~~~text
META-INF/services/com.acme.payment.api.PaymentProcessor
~~~

Its content holds the provider class name:

~~~text
com.acme.payment.card.CardPaymentProcessor
~~~

When migrating to an explicit module, providers are registered via module-info.java:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

The consumer named module needs uses:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

Inventory all META-INF/services, ServiceLoader.load calls, factory/plugin registries, and configuration files that select implementations. A provider can disappear after modularization if:

- Service registration is not migrated properly.
- The provider module is not in the resolved module graph.
- The consumer is missing uses.
- The service API is loaded as different classes in different layers/class loaders.
- A fat JAR or shading dropped or overwrote service resources.

For plugins using a custom ModuleLayer, consider Configuration.resolveAndBind to include the appropriate providers in the graph, and use ServiceLoader.load(layer, ServiceType.class) to discover them in the proper layer.

## 13. Resources, Manifests, and Class Loader Assumptions

Migration does not only involve .class files. An application may locate resources using:

~~~java
SomeClass.class.getResource("/config/defaults.properties");
~~~

or:

~~~java
Thread.currentThread()
    .getContextClassLoader()
    .getResource("config/defaults.properties");
~~~

Resource lookup in a named module depends on module ownership, resource encapsulation rules, and certain constraints when accessing resources from outside the module. A path that works on the classpath is not guaranteed to yield the same result after moving the resource into a named module.

You should inventory:

- Configuration files inside JARs and external directories.
- Whether resource paths use absolute or relative paths.
- Usage of Class.getResource, ClassLoader.getResource, and context class loaders.
- Service descriptors in META-INF/services.
- Manifest Main-Class, Class-Path, Automatic-Module-Name, and related entries.
- Plugin JARs scanned from the filesystem and their discovery order.
- Classes/resources dynamically generated by annotation processing or code generation.

In particular, do not rely on enumerating all JARs from a module layer's class loader: JPMS may use multiple class loaders and dedicated module loading mechanisms. Design resource lookups according to module or framework contracts, then test on the final packaged artifact.

## 14. JNI, Agents, and Off-JVM Integrations

A classpath project may contain JNI, Java agents, native code, instrumentation, or runtime bytecode-generation libraries. These components need to be assessed independently from pure Java dependencies.

Examples:

- Native libraries loaded via System.loadLibrary.
- Agents running with -javaagent or using Instrumentation.
- Frameworks generating subclasses/proxies or redefining classes.
- Runtime tools needing access to unexported/unopened modules or packages.
- Applications using custom class loaders to create isolated namespaces.

When modularizing, verify the module of the instrumented classes, the agent's class loader, and the required package access permissions. If temporary access must be opened, explicitly document --add-opens or --add-exports in the test/runtime configuration and plan to remove them once libraries adopt appropriate APIs.

Do not assume that changing a JVM flag is enough to handle every JNI issue. Native dependencies also have requirements regarding OS, architecture, ABI, loading paths, and resource lifecycles.

## 15. Reviewing Build and Test Configurations

Maven/Gradle may automatically distinguish between the module path and classpath depending on plugins, versions, and project structure. Check the actual javac/test JVM commands, not just source configurations that look modular.

Key points:

- Does the JDK toolchain match the target?
- Is module-info.java compiled and included in the final JAR?
- Are dependencies placed on the module path or classpath in each phase?
- Do tests use the module path, patch-module, opens, or the classpath?
- Are annotation processors placed on the appropriate processor path/module path?
- Does a shaded JAR break module-info.class or META-INF/services?
- Does the runtime launcher use the correct module name/main class?

Example recommended layout for a modular component:

~~~text
customer-api/
  src/main/java/
    module-info.java
    com/acme/customer/api/Customer.java
  src/test/java/
    com/acme/customer/api/CustomerTest.java
~~~

Before applying this structure across all projects, experiment on a module with few dependencies to confirm that the build, tests, packaging, and IDE work consistently together.

## 16. Phased Migration Strategy

It is not mandatory to modularize the entire application in a single release. A typical roadmap:

### Phase 1: Stay on the classpath, eliminate risks

- Upgrade the JDK to the target version in a test environment.
- Use jdeps to find dependencies and internal JDK APIs.
- Upgrade libraries that already support the target JDK.
- Eliminate or isolate split packages and dependency cycles.
- Reduce unnecessary deep reflection.
- Create regression tests for service/resource/class loading.

No need to add module-info.java across the entire application yet.

### Phase 2: Standardize API boundaries

- Identify true API packages.
- Separate implementation and API interfaces if necessary.
- Remove direct dependencies on internal classes of other components.
- Agree on stable library module names.
- Convert eligible plugin registries to public SPIs.

### Phase 3: Pilot a small module

- Pick a library with few dependencies and no split packages.
- Add module-info.java with accurate requires/exports.
- Build a modular JAR and test it from a representative consumer.
- Verify resources, reflection, service discovery, and unit tests.
- Maintain compatibility for classpath consumers if required by the product.

### Phase 4: Expand the graph

- Gradually migrate components following the dependency direction.
- Use controlled automatic modules as a bridge for libraries not yet explicitly modularized.
- Verify each dependency layer, avoiding cycles.
- Convert the main application into a named module once its dependencies are ready.

### Phase 5: Validate runtime and packaging

- Run the application from the module path.
- Inspect the graph using --show-module-resolution.
- Test the actual packaged artifact, Docker/runtime image, and plugins.
- If using jlink, ensure linked modules are explicit modules and service providers are included in the image as required.
- Remove --add-exports/--add-opens flags that were only masking unresolved issues.

This strategy keeps each change small in scope, easy to roll back, and easy to diagnose when errors occur.

## 17. Automatic Modules Are a Bridge, Not the Destination

When a library lacks module-info.class yet can be placed on the module path, JPMS can treat it as an automatic module.

Advantages:

- Other named modules can requires it by its automatic module name.
- The library does not need to be rewritten immediately.
- Packages of an automatic module are exported, lowering some initial migration barriers.

However, an automatic module lacks exact dependency descriptors, has broad export visibility, and may rely on legacy classpath assumptions. It also has limitations when building a runtime image with jlink.

Do not treat automatic modules as a permanent solution if your application has strong plans around encapsulation and custom runtime images. Once an official explicit module version of a library becomes available, replace the bridge with the supported artifact.

With the main application still on the classpath, you can move some independent libraries to the module path first and use --add-modules when needed. Still, do not assume every library on the module path automatically becomes a resolved module, and do not rush to convert the main application into a named module while it still depends on classes that exist only in the unnamed module.

## 18. The Boundary Between Named Modules and the Unnamed Module

Code on the classpath belongs to the unnamed module. A named module with a descriptor cannot write:

~~~java
module com.acme.app {
    requires unnamed;
}
~~~

There is no standard module name representing the entire classpath for use in requires.

When converting a consumer into a named module, you must resolve how it depends on remaining classpath libraries. Depending on your strategy, you can:

- Move suitable libraries onto the module path as automatic modules.
- Upgrade libraries to explicit module releases.
- Separate components that are not ready into a launcher/adapter that continues running on the classpath.
- Design a public SPI or a process/service boundary to reduce direct dependencies.

Runtime flags like --add-reads can help diagnose certain scenarios, but they do not replace clean dependency architecture and do not automatically turn classpath JARs into named modules.

## 19. Prototyping the Module Path Before Editing All Source

A practical approach is to build a proof of concept with a few representative JARs:

~~~text
prototype/
  app.jar
  lib/
    customer-api.jar
    customer-impl.jar
    logging.jar
~~~

Determine module names:

~~~bash
jar --describe-module --file lib/customer-api.jar
jar --describe-module --file lib/customer-impl.jar
~~~

If dependencies can be used on the module path, verify the graph in a prototype launcher:

~~~bash
java --module-path "lib:app.jar" \
     --show-module-resolution \
     --module com.acme.app/com.acme.app.Main
~~~

This command only applies when com.acme.app is actually recognized as a named or automatic module with an appropriate main class; if the application is still a classpath artifact, keep running it on the classpath and test modularizing libraries incrementally first.

Compare against the classpath baseline: program startup, service discovery, reflection, resource loading, and critical plugin paths must work.

If an error occurs right at the resolution step, focus on module names/dependencies/split packages. If resolution succeeds but the application fails at runtime, inspect access permissions, dynamic class loading, and framework configuration.

## 20. Modularization Readiness Criteria

You can use the following criteria to decide whether a component is ready to be converted into an explicit named module:

| Criterion | Signs of readiness |
|---|---|
| Module boundary | Has a clear name and scope of responsibility |
| Dependency direction | No intractable cycles; dependencies are sufficiently clear |
| Package ownership | No conflicting split packages remain |
| API contract | Has a well-defined set of exported packages |
| Third-party libraries | Module names and module-path usability have been verified |
| Reflection | Necessary opens have been scoped and justified |
| Service registration | Uses/provides and provider discovery work |
| Resource/class loader | Tested on real modular JAR layout and launcher |
| Build/test | Compiler, test runner, IDE, and CI share the same configuration |
| Runtime compatibility | Runs properly on the target JDK with representative use cases |
| Observability | Has module resolution logging and error analysis mechanisms |
| Rollback | Has a path back to a working configuration if migration hits an error |

Do not try to reach a state where "every JAR is a module" just by placing everything on the module path. The goal is a designed and verified module graph, not merely changing how JARs are located.

## 21. Pre-Start Checklist

- [ ] Locked JDK, application, and dependency versions as a baseline.
- [ ] Built an inventory of direct, transitive, optional, and runtime-only dependencies.
- [ ] Ran jdeps, including JDK internal API analysis.
- [ ] Checked automatic module names and descriptor status of all JARs.
- [ ] Searched for split packages and dependency cycles.
- [ ] Separated public APIs from implementation packages.
- [ ] Identified deep reflection points, bytecode generation, and agents.
- [ ] Inventoried META-INF/services, ServiceLoader, and dynamically loaded providers.
- [ ] Reviewed resources, manifests, and context class loaders.
- [ ] Checked native dependencies if any.
- [ ] Have integration tests on the target JDK and real release artifacts.
- [ ] Have a layered migration plan and rollback strategy.
- [ ] Track --add-exports/--add-opens flags as migration debt, not as permanent long-term APIs.

## Conclusion

Assessing a classpath application before modularization is the step of identifying the **actual dependency graph**, implicit classpath assumptions, and risks when JPMS enforces readability, exports, opens, and module resolution.

Start from a reproducible baseline, use jdeps to analyze bytecode, inventory dynamic dependencies, identify split packages/cycles, classify automatic and explicit modules, and then pilot converting a component with clear boundaries. Only expand to the main application once the build, runtime, ServiceLoader, reflection, and resource loading have been verified.

A successful migration does not have to convert all code at once. It produces an intentional module graph, preserves necessary compatibility, and gradually reduces unsupported internal dependencies.
