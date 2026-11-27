# Fixed Classpath and Consequences for Post-Deployment Loaded Plugins

A Java application running on the JVM can often be extended after deployment: drop an extra JAR into a plugin directory, add the path to the classpath, create a `URLClassLoader`, and load new classes. This model suits systems that need to install plugins without rebuilding the application. With **GraalVM Native Image**, that approach changes significantly.

Native Image analyzes and compiles the application at build time under the **closed-world assumption**. The required classes, dependencies, and bean definitions must be known when creating the executable. Therefore, **the classpath of a native application is fixed at build time**; copying a new plugin JAR into a directory after deployment does not automatically make the classes in that JAR appear inside the executable.

In the **`SPRING_BOOT_NATIVE_IMAGE`** module, this lesson explains that limitation and its consequences for Spring Boot plugin architectures. You will distinguish dynamic lookup of already-packaged classes from loading completely new classes, understand the roles of `ServiceLoader` and Spring AOT, and choose an appropriate architecture when a product needs extensibility after release.

> **Scope:** this content describes the standard model of Spring Boot AOT and Native Image. Some recent GraalVM releases include an experimental option for runtime class loading; this is an advanced mechanism with its own limitations and does not mean Native Image has an open classpath like the JVM. Check the documentation for your exact GraalVM and Spring Boot versions before relying on experimental features in production.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the closed-world assumption and why the native classpath is fixed.
- Distinguish classes already present in the image and looked up by name from class bytecode that only appears after deployment.
- Analyze why a new plugin JAR cannot be loaded as it is on a standard JVM.
- Understand the limitations of `Class.forName`, `URLClassLoader`, `ServiceLoader`, and Spring bean discovery.
- Design plugins that are known at build time yet selectable via runtime configuration.
- Choose between native image variants, a JVM host, separate processes/containers, or an extension DSL.
- Recognize experimental runtime class loading features and their associated risks.

## 2. What Does a Fixed Classpath Mean?

When building a Native Image, the builder reads the bytecode of the application and its dependencies on the classpath/module path. Static analysis starts from entry points, follows reachable call paths, and decides which classes, methods, fields, and resources need to be included in the binary.

The result is a standalone executable containing the necessary code and runtime support. When executed, the executable does not start a full JVM to continue reading an arbitrary JAR classpath like the `java -cp` command.

~~~mermaid
flowchart TD
    A["Application code + dependency JARs"] --> B["Build-time classpath"]
    B --> C["Spring AOT analyzes ApplicationContext"]
    C --> D["Native Image reachability analysis"]
    D --> E["Native executable"]
    E --> F["Runtime: runs code already included in the image"]
    G["New plugin.jar after deployment"] --> H["Not automatically added to the executable"]
    H --> I["Cannot be loaded like a standard JVM plugin"]
~~~

A fixed classpath does not mean every class on the build classpath is retained. Native Image can still eliminate unreachable parts. For a class to be called dynamically by name, the application must ensure that the class is in the known set of classes and has appropriate metadata for dynamic access operations.

| Concept | Meaning |
|---|---|
| Build classpath | The directories/JARs/modules that the builder sees when creating the executable |
| Reachability | Which classes/members can be called and need to be kept in the binary |
| Runtime classpath | On a traditional JVM, the list of locations a class loader can search at runtime; Native Image does not provide an equivalent open model for arbitrary JARs added after build |

## 3. Why Does Native Image Use This Model?

Native Image aims for executables with fast startup and low memory usage. To optimize, the builder needs to know ahead of time most of the code that can be executed. As a result, it can:

- Analyze the call graph and eliminate unreachable code.
- Compile Java bytecode into machine code during the build process.
- Bundle required runtime support and data into the executable.
- Prepare metadata for declared dynamic accesses.

If the application were allowed to load any arbitrary JAR after starting, the builder could not know in advance the full bytecode, dependency graph, reflection usage, and class initialization of that plugin. Many optimizations based on the closed world would become invalid or require a much more complex runtime mechanism.

Therefore, a plugin model must be designed around one of two assumptions:

1. **The plugin set is known at build time:** implementations and dependencies are placed on the classpath before creating the image.
2. **The plugin set is truly open after deployment:** the host must support loading new code, or plugins must run in a different runtime/process capable of doing so.

Merely adding reflection metadata does not turn the second assumption into the first.

## 4. Distinguishing Dynamic Class Lookup from Loading New Classes

The following two scenarios look similar but have different runtime requirements.

### 4.1. Looking Up a Class Already in the Image

~~~java
String className = "com.example.plugins.CsvExportPlugin";
Class<?> pluginType = Class.forName(className);
~~~

If `CsvExportPlugin` is already on the build classpath, retained in the image, and registered with the required metadata, looking up the class by name can work in Native Image.

Having the class name as a dynamic string does not automatically make a new class appear. Native Image needs to know the accessed type beforehand; if the class is not in the image or lacks registration, runtime may throw `ClassNotFoundException` or a missing registration error depending on the access path and version.

### 4.2. Reading Bytecode from a New JAR

~~~java
URL pluginJar = Path.of("plugins", "customer-plugin.jar")
        .toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[]{pluginJar},
        Thread.currentThread().getContextClassLoader())) {
    Class<?> pluginType = loader.loadClass(
            "com.customer.plugin.CustomerPlugin");
}
~~~

On a traditional JVM, the class loader can find the class inside that JAR. With Native Image under a standard configuration, adding a JAR after build does not integrate the bytecode of `CustomerPlugin` into the executable. Registering reflection for a class name alone does not supply that class's bytecode.

| Scenario | Standard JVM | Standard Native Image |
|---|---|---|
| `Class.forName` for a class already in the application | Can work | Can work if the class is retained and metadata is appropriate |
| Reflection invoking a method/field of a known class | Can work according to access rules | Needs appropriate hints if the builder cannot infer it |
| Adding a JAR to a folder after deployment | Can be loaded via an appropriate class loader | Does not automatically add the JAR to the image classpath |
| Loading new classes from arbitrary bytecode | Possible via custom class loader | Not in the default model; separate experimental option exists in some GraalVM versions |

## 5. Why Doesn't Reflection Metadata Solve New Plugin JARs?

Reachability metadata describes the dynamic parts of **code that the Native Image builder already knows**. Metadata can declare:

- Which classes are accessed via reflection.
- Which constructors, methods, or fields must be retained.
- Which resources must be read from the classpath.
- Which dynamic proxies, JNI, or serialization must be supported.

For example, reflection metadata can ensure that the constructor of `CsvExportPlugin`, already present in a dependency, is kept. However, metadata does not contain all the bytecode and new dependencies of a plugin installed only after deployment.

~~~text
Plugin is on the build classpath
    + class is reachable or registered
    + appropriate reflection metadata
    -> usable inside the native executable

Plugin JAR is only copied after deployment
    + reflection metadata for the class name
    -> still missing the plugin's bytecode/dependencies
~~~

If the plugin is not included in the build, adding `reflect-config.json`, `RuntimeHints`, or `@RegisterReflectionForBinding` for the class name cannot replace the step of including the plugin code in the image.

## 6. Consequences for Spring AOT and Bean Definitions

Spring Boot typically builds an ApplicationContext flexibly at runtime: component scanning, auto-configuration, `@Profile`, `@ConditionalOnProperty`, and registry callbacks can all influence which beans get registered.

When running AOT/native, Spring analyzes the ApplicationContext at **build time** and generates code/metadata to initialize the context. Decisions about bean definitions must be stable according to the classpath and Environment used during AOT.

That implies:

- The classpath and auto-configuration modules must be present at AOT/build time.
- Bean definitions cannot arbitrarily change based on a plugin JAR added after deployment.
- Conditions affecting bean presence, such as `@Profile` and `@ConditionalOnProperty`, are evaluated during AOT processing.
- Plugins that need to be managed by Spring must have a registration path recognized by AOT.

### Profiles and Conditionals Are Not Runtime Plugin Switches

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "plugins.csv",
        name = "enabled",
        havingValue = "true")
class CsvPluginConfiguration {

    @Bean
    CsvExportPlugin csvExportPlugin() {
        return new CsvExportPlugin();
    }
}
~~~

In a standard JVM application, the property can be evaluated when the ApplicationContext starts. With Spring AOT, the condition is evaluated during the AOT build; you should not expect changing `plugins.csv.enabled` after deployment to make a new bean definition appear in the native context.

If you want to enable/disable already-packaged plugins via runtime configuration, register the known plugins in the context and let a registry/service select which implementations are allowed to run. That changes **business selection**, not the set of bean definitions.

### Bean Registration Patterns Requiring Special Verification

Spring Framework AOT cannot convert every container-mutating operation into static initialization code. The AOT documentation highlights several cases to watch out for:

- Bean definitions with an application-supplied instance supplier (lambda or method reference) cannot be transformed ahead-of-time in the usual way.
- Singletons added directly via `registerSingleton` cannot be transformed by AOT into generated bean definitions.
- If beans are registered programmatically, appropriate extension points and AOT contributions must be used so Spring can process them at build time as well.

Therefore, a plugin JAR already on the classpath can still fail to work properly if its bean registration only happens via dynamic callbacks that AOT does not handle. Check both **whether the plugin bytecode is in the build** and **how Spring registers the plugin beans**.

## 7. Build-Time Available Plugins: Using ServiceLoader

`ServiceLoader` is the standard Java mechanism for finding implementations of a service interface. It is useful when the set of providers is packaged with the application.

Define the extension point:

~~~java
package com.example.export;

public interface ExportPlugin {
    String id();
    byte[] export(ExportRequest request);
}
~~~

An implementation:

~~~java
package com.example.export.csv;

public class CsvExportPlugin implements ExportPlugin {

    @Override
    public String id() {
        return "csv";
    }

    @Override
    public byte[] export(ExportRequest request) {
        // Generate CSV content.
        return new byte[0];
    }
}
~~~

Providers can be declared via the `META-INF/services/com.example.export.ExportPlugin` file inside the JAR:

~~~text
com.example.export.csv.CsvExportPlugin
com.example.export.pdf.PdfExportPlugin
~~~

Application usage:

~~~java
ServiceLoader<ExportPlugin> plugins =
        ServiceLoader.load(ExportPlugin.class);

for (ExportPlugin plugin : plugins) {
    System.out.println(plugin.id());
}
~~~

To use this in Native Image:

1. Include all required provider JARs on the build classpath.
2. Ensure service descriptor files and providers are recognized by Native Image.
3. Verify library reachability metadata or configure service registration according to your Native Image version.
4. Run tests inside the native executable to confirm the providers are actually discovered.

`ServiceLoader` can discover providers that were packaged and registered at build time. It does **not** make providers in a new JAR copied into a folder after deployment appear automatically. A service descriptor is discovery metadata; it cannot add bytecode to an already-built native executable.

## 8. Known Spring Plugins: Register Early, Select Later

If the number of plugins is determined at release time but operators need to toggle individual plugins on or off, you can include all implementations in the image and register stable bean definitions.

Interface:

~~~java
public interface PaymentPlugin {
    String providerId();
    PaymentResult pay(PaymentRequest request);
}
~~~

Two known implementations:

~~~java
@Component
class CardPaymentPlugin implements PaymentPlugin {
    @Override
    public String providerId() {
        return "card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        // Process card payment.
        return PaymentResult.approved();
    }
}
~~~

~~~java
@Component
class BankTransferPlugin implements PaymentPlugin {
    @Override
    public String providerId() {
        return "bank-transfer";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        // Process bank transfer.
        return PaymentResult.pending();
    }
}
~~~

Registry selecting implementations from runtime configuration:

~~~java
@Service
public class PaymentPluginRegistry {

    private final Map<String, PaymentPlugin> plugins;
    private final Set<String> enabledProviders;

    public PaymentPluginRegistry(
            List<PaymentPlugin> availablePlugins,
            PluginSettings settings) {
        this.plugins = availablePlugins.stream()
                .collect(Collectors.toUnmodifiableMap(
                        PaymentPlugin::providerId,
                        Function.identity()));
        this.enabledProviders = Set.copyOf(settings.enabledProviders());
    }

    public PaymentPlugin get(String providerId) {
        if (!enabledProviders.contains(providerId)) {
            throw new IllegalArgumentException("Provider is disabled");
        }
        PaymentPlugin plugin = plugins.get(providerId);
        if (plugin == null) {
            throw new IllegalArgumentException("Unknown provider");
        }
        return plugin;
    }
}
~~~

In this example, the set of classes/beans is fixed at build time. The `enabledProviders` configuration only decides which implementation is used. There is no need to add bean definitions after the native executable starts.

If configuration changes after the context has initialized, the registry may need a mechanism to refresh/reload configuration data; however, that still cannot create a new implementation class not present in the image.

## 9. When Plugin JARs Must Be Installed After Deployment

If the product requirement is that customers can upload a new plugin JAR to the server and the host must load it without rebuilding, the runtime architecture needs to be reconsidered. There are several options.

### 9.1. Run the Host on the JVM

Keep the host/plugin manager on the JVM to leverage class loaders, `URLClassLoader`, module layers, or a compatible plugin framework. This is the direct choice when the plugin ecosystem needs to load arbitrary classes/JARs after deployment.

Advantages:

- Familiar classpath and class loader model.
- Plugins can be installed or updated without rebuilding the host binary.
- Many JVM plugin libraries are already designed around this mechanism.

In return, the application no longer gets the full startup/memory benefits of a native executable for the host process. If the main workload suits native while the plugin manager needs the JVM, the two components can be separated.

### 9.2. Run Plugins in Separate Processes/Containers

Package the host as a native executable, while each plugin runs in a JVM or its own appropriate runtime. The host calls plugins over a stable protocol:

- HTTP/REST.
- gRPC.
- Message broker.
- IPC or an internal protocol.

~~~mermaid
flowchart LR
    A["Native Spring Boot host"] --> B["Plugin API / protocol"]
    B --> C["Plugin A: JVM process"]
    B --> D["Plugin B: JVM process"]
    B --> E["Plugin C: separate container"]
~~~

Advantages:

- The host can still benefit from Native Image.
- Plugins have independent deployment/rollback lifecycles.
- Different languages/runtimes can be used for plugins.
- Plugin crashes or memory leaks can be isolated at the process boundary.

In return, you must design APIs, authentication, timeouts, retries, observability, and network error handling. Do not use internal Java object serialization as a public protocol across plugin versions; define versioned schemas/APIs.

### 9.3. Create Native Image Variants per Plugin Set

If the plugin set only changes at release time, create build variants:

~~~text
application-base + plugin-csv  -> app-csv-native
application-base + plugin-pdf  -> app-pdf-native
application-base + plugin-all  -> app-full-native
~~~

Each variant has its corresponding classpath/AOT output/metadata. An automated pipeline can select dependencies per build profile, keeping in mind that the native/AOT profile is decided at build time.

The advantage is that each executable only carries the required plugins. The downside is an increase in the number of artifacts to build, test, store, and release.

### 9.4. Use a DSL or Scripting Engine

If extensibility needs are mainly **business rules** (pricing formulas, mappings, workflows, conditions), it may not be necessary to allow arbitrary Java plugins. You can define:

- A JSON/YAML schema for rules.
- An expression language with a restricted set of operators.
- A workflow definition.
- A template or mapping specification.
- Scripts in an interpreter that has been packaged and tested with Native Image.

In this model, the new rule/script file is data read at runtime; the interpreter is code already in the image. However, script execution capability depends on the specific interpreter and runtime. Not every JavaScript/Groovy/Kotlin scripting engine is automatically compatible with Native Image.

Define language boundaries, file/network access permissions, timeouts, quotas, and script validation. Do not treat a DSL as a safe way to run arbitrary Java bytecode.

## 10. GraalVM's Experimental Runtime Class Loading

Recent GraalVM documentation describes **experimental support for run-time class loading**. In versions supporting this feature, it can be enabled with build options:

~~~bash
native-image \
  -H:+UnlockExperimentalVMOptions \
  -H:+RuntimeClassLoading \
  -H:-UnlockExperimentalVMOptions \
  -jar app.jar app
~~~

When enabled, a class loader can define classes from bytecode via `ClassLoader.defineClass`. This feature targets cases where applications/libraries generate bytecode after the executable starts, such as generated proxies whose bytecode only exists at runtime.

### This Is Not an Open Classpath Like the JVM

This experimental option has important limitations according to GraalVM documentation:

- Parallel class loading is not supported.
- `URLClassLoader` and loading classes from the JDK or application class loader may require additional configuration.
- Runtime-loaded classes can link to classes already in the image, but static analysis may have eliminated methods/static fields of build-time classes that the plugin needs; `-H:Preserve=package=...` may be required.
- Enabling runtime class loading can increase image size and memory usage.
- It cannot be combined with predefined classes.
- Enabling `-H:+RuntimeClassLoading` does not automatically resolve all dependencies, resources, reflection, or classloader isolation of a plugin framework.

Because this is an **experimental** feature, it should not be treated as guaranteed by default by Spring Boot AOT for arbitrary plugin JARs. Before using it, build a prototype on the exact GraalVM version, test classloader topology, dependency linking, parallelism, and memory; then decide whether it is suitable for production.

### Predefined Classes Are a Different Mechanism

GraalVM also has a **predefined classes** mechanism based on the tracing agent: the agent records the bytecode of classes defined during a JVM run, and Native Image can then provide those recorded classes when runtime requests a class with the same name and bytecode.

This mechanism is best-effort for certain legacy applications; its metadata is not designed to be written manually, and it is not guaranteed to work for every plugin. It is not a mechanism for installing a plugin with different bytecode after the image has been built. The predefined classes feature also cannot be combined with the runtime class loading option described above.

## 11. Why Is Just Adding Plugin JARs to a Docker Image Still Not Enough?

Suppose a Dockerfile copies additional plugins:

~~~dockerfile
FROM eclipse-temurin:21-jre
COPY app-native /app/app
COPY plugins/ /app/plugins/
ENTRYPOINT ["/app/app"]
~~~

The `/app/plugins/` directory may exist in the container, but that **does not automatically add the JARs' bytecode to the native executable**. If the executable was built when the plugins were not on the classpath, copying the JARs afterward does not make Native Image re-analyze or open the classpath.

Similarly, the following approaches do not turn a native executable into a JVM:

- Changing the `CLASSPATH` environment variable.
- Setting `-Djava.class.path=/app/plugins/*`.
- Adding JARs to an existing directory.
- Placing a new `META-INF/services` file next to the executable.
- Adding reflection JSON after the binary has been created.

These files may matter to a JVM or a new build process; they do not change the compiled code inside an existing native executable.

## 12. Process for Designing Controlled Native Plugins

If you choose the build-time known plugin model, manage plugins as release dependencies.

### Step 1: Define a Stable SPI

Create a small plugin interface that does not depend on implementations:

~~~java
public interface ReportPlugin {
    String id();
    ReportResult generate(ReportRequest request);
}
~~~

Keep the API and exchange DTOs stable. Avoid letting plugins directly access internal beans or private host implementation classes.

### Step 2: Select Plugin Dependencies at Build Time

Declare plugin JARs in the Maven/Gradle dependency graph of the application variant. Each plugin must have dependencies and reachability metadata suitable for Native Image.

### Step 3: Register Providers/Beans in an AOT-Recognizable Way

Use `ServiceLoader` with providers present on the build classpath or register beans via configuration/auto-configuration processed by Spring AOT. Avoid dynamic singleton registration after AOT has analyzed the context.

### Step 4: Decide Plugin Selection via Runtime Data

Allow operators to enable/disable or select packaged plugins via configuration. Do not use runtime profiles/conditionals to try to create new bean definitions outside the set processed by AOT.

### Step 5: Run Native Tests per Plugin

Run native tests for each implementation, covering:

- Plugin discovery.
- Reflection/resource/serialization functionality.
- Plugin selection based on configuration.
- Proper handling of plugin errors.
- Absence of dependencies or classes that only exist on the JVM test classpath.

### Step 6: Version and Release Together

Record the host version, plugin versions, GraalVM version, and native build metadata. When changing plugin code or dependencies, rebuild the image and re-run compatibility tests.

## 13. Checking Whether an Existing System Relies on a Dynamic Classpath

Look for the following signs in source code/dependencies:

| Sign | Question to Ask |
|---|---|
| `URLClassLoader` / custom `ClassLoader` | Does it read JARs/bytecode installed after deployment? |
| `Class.forName(name)` | Can the class name point to a class not on the build classpath? |
| `ServiceLoader.load` | Are the providers in the build-time dependency graph? |
| Plugin folder scan | Is it expected to scan a JAR folder at runtime? |
| Spring `registerSingleton` / registry callback | Are bean definitions added after AOT processing? |
| `@Profile` / `@ConditionalOnProperty` | Are runtime properties expected to change the set of bean definitions? |
| Bytecode generation / proxy generator | Is bytecode generated at build time or runtime; does the Native Image version support that use case? |

Quick search using ripgrep:

~~~bash
rg -n "URLClassLoader|ClassLoader|Class\\.forName|ServiceLoader|registerSingleton|registerBeanDefinition|plugins/" src
~~~

This command is only a screening step. A class loader appearing in code does not automatically prove incompatibility; you need to check where bytecode is loaded from, whether the class is already in the image, and whether the use case is supported by GraalVM.

### Categorizing Findings

1. **Dynamic lookup of known classes:** can fit Native Image after checking reachability metadata.
2. **Build-time available providers/beans:** usable if service/bean registration is handled by AOT and native tests pass.
3. **New post-deployment plugin JARs:** incompatible with the standard fixed classpath.
4. **Runtime-generated bytecode:** requires checking dedicated support options, including experimental runtime class loading if available in your GraalVM version.

## 14. Architecture Decision Example

A reporting platform has three kinds of extensions:

- CSV/PDF exporters released alongside the application.
- A billing calculator updated monthly by partners.
- Report template adjustment scripts modified daily by operators.

They can be split as follows:

| Extension | Appropriate Deployment Approach |
|---|---|
| Known CSV/PDF exporters | Package plugins into the native image; select via runtime configuration |
| Independently updated billing calculator | Run as a separate service/process communicating via a versioned API |
| Report template scripts | Use a packaged, capability-restricted template/DSL/interpreter |

If all extensions are Java JARs that must be loaded freely, running the host on the JVM may be simpler and less risky than trying to emulate an open classpath inside Native Image.

## 15. Practice Exercises

**Exercise 1 — New JAR not recognized:** A native container has `/app/plugins/customer.jar`, yet `Class.forName("com.customer.Plugin")` reports class not found. Why?

**Hint:** The JAR was copied after the image build, so its bytecode is not inside the executable. Reflection metadata only supports accessing known classes; it does not add plugin code.

**Exercise 2 — ServiceLoader only finds the default plugin:** A new provider was copied into `plugins/` after deployment. Should we add `META-INF/services` next to the binary?

**Hint:** Not enough. Provider classes and service metadata must be included in the build classpath/image. Runtime descriptor files do not add bytecode.

**Exercise 3 — Selecting a plugin via config:** An application has two packaged providers. Operators need to choose provider A or B at runtime. How can this be done?

**Hint:** Register both implementations in a stable bean context, then use runtime configuration for a registry to select the implementation. Do not use conditionals to create new beans after AOT.

**Exercise 4 — Independently deployable plugins:** Customers need to upload new Java JARs without rebuilding the host. Propose an architecture.

**Hint:** Keep the host/plugin manager on the JVM or run plugins in separate processes/containers via HTTP/gRPC/message protocols. Evaluate operational cost and isolation.

**Exercise 5 — Experimental runtime class loading:** Why does enabling `-H:+RuntimeClassLoading` not mean every JVM plugin framework will work?

**Hint:** The experimental feature only opens certain bytecode-defining capabilities; limitations remain around `URLClassLoader`, parallel loading, linking, preserved members, dependencies/resources, and memory.

## 16. Checklist Before Choosing Native Image for a Plugin System

- [ ] Determine whether plugins are known at build time or must be newly installed after deployment.
- [ ] Distinguish dynamic lookup of packaged classes from loading new bytecode/JARs.
- [ ] Verify all plugin dependencies are present on the build classpath.
- [ ] Verify `ServiceLoader` providers and service descriptors are included in the image.
- [ ] Ensure Spring AOT sees the necessary bean definitions and auto-configurations.
- [ ] Do not rely on runtime profiles/conditionals to add new bean definitions.
- [ ] If toggling plugins is needed, use a registry selecting from the known set of implementations.
- [ ] If independent new plugins are required, consider a JVM host or separate processes/containers.
- [ ] If using a DSL/script, verify the specific interpreter and runtime limits.
- [ ] Treat runtime class loading as an advanced option only when supported by your GraalVM version and validated by a prototype.
- [ ] Test the native image with each actual plugin, dependency, and code path.
- [ ] Record host/plugin/GraalVM versions for reproducible builds and troubleshooting.

## 17. References

- [Spring Boot Reference — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): fixed classpath, closed-world assumption, and Spring AOT limitations.
- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): fixed classpath/Environment and bean definitions processed at build time.
- [GraalVM Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): closed-world assumption, metadata, and limitations of defining classes at runtime.
- [GraalVM Run-Time Class Loading](https://www.graalvm.org/dev/reference-manual/native-image/runtime-class-loading/): experimental feature, how to enable it, and runtime class loading limitations.
- [GraalVM Native Image Compatibility Guide](https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/): Java features requiring metadata or incompatible with the closed-world assumption.

**Key takeaway:** Native Image fixes the classpath and set of bean definitions at build time to analyze, eliminate unused code, and compile a compact executable. Reflection hints can enable dynamic access to already-packaged classes; they do not install bytecode from a post-deployment plugin JAR. If the plugin set is known, package them upfront and select via runtime configuration. If new Java plugins must be loaded after release, consider a JVM host or separate processes/containers; only use experimental runtime class loading after thoroughly testing the limitations of your deployed GraalVM version.
