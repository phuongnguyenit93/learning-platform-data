
# Application platforms, plugins, and server-provided dependencies

When upgrading Java, an application may compile cleanly on the new JDK yet fail to boot inside the application server, fail to discover plugins, fail to find container-provided services, or throw cast errors between two classes sharing **the same name**. This is not necessarily a Java language bug or a recently removed method. Many systems depend on **the contract among the application, execution platform, class loaders, and runtime libraries outside the artifact**.

For example: a WAR compiled against Jakarta Servlet API yet deployed onto a `javax.servlet`-generation servlet container; a plugin bundling the host SDK so the host sees two definitions of an interface; an application appearing to omit a JDBC driver in its POM because the driver sits in a server module; or a new executable JAR no longer receiving services previously provided by a legacy external application server. In each case, **the compile classpath does not reflect the complete actual runtime**.

This lesson is part of *Java Advance Compatibility Migration*, chapter *Framework and Platform*. Its focus is distinguishing APIs from implementations, server-managed dependency models, plugin hosts, class-loader isolation, ServiceLoader, JPMS, and verifiable migration methods.

## 1. Overall model: applications run across multiple layers

An enterprise Java application typically spans at least three layers:

1. **Application code and packaged artifact:** classes, resources, app-owned dependencies, and configuration.
2. **Application platform:** application server, servlet container, framework runtime, plugin host, service registry, and externally supplied dependencies.
3. **Java platform and operating system:** JVM/JDK runtime image, Java SE modules, native libraries, module access rules, and security properties.

Example of a WAR deployment:

~~~text
Java runtime / JDK
└── Application server
    ├── Server modules + shared libraries
    ├── Servlet engine, transaction, naming, logging
    ├── Provider/Service discovery
    └── Deployed application.war
        ├── WEB-INF/classes
        ├── WEB-INF/lib/*.jar
        └── Configuration / resources
~~~

On an executable JAR with an embedded server, boundaries shift:

~~~text
Java runtime / JDK
└── application.jar / launcher
    ├── Application classes
    ├── Framework and embedded server
    ├── Runtime dependencies
    └── Configuration / resources
~~~

With a plugin host, there is also a host-owned SDK layer and separate plugin class loaders. Therefore, library packaging rules cannot be applied uniformly to WARs, standalone JARs, and plugin archives.

~~~mermaid
flowchart TD
    A["Application or plugin code"] --> B["Compile API"]
    A --> C["Application's own runtime"]
    A --> D["Host-provided API/runtime"]
    D --> E["Server/container/plugin host"]
    C --> F["JVM and Java SE modules"]
    E --> F
    B -. "API generation must match" .-> D
~~~

## 2. What is an application platform?

An "application platform" is the environment that supports executing and managing a set of applications or extensions. Common forms include:

- **Servlet container:** HTTP connector, servlets/filters/listeners, and web application lifecycle.
- **Application server:** may additionally provide enterprise services such as CDI, persistence integration, transactions, naming, messaging, and validation depending on profile and version.
- **Framework runtime:** dependency injection, web/data integrations, and starter dependencies shipped with the application.
- **Embedded server:** servlet/web engine bundled inside an executable app.
- **Plugin host:** SDK, extension points, plugin discovery, lifecycle, and class-loading rules.
- **Custom runtime image:** Java/JDK modules selected via `jlink`, which may omit modules present in a full JDK.

These products carry different responsibilities. Never infer "having a JDK means having a Java EE server", or "having an API dependency means automatically having the runtime engine".

### 2.1. APIs differ from implementations

An API defines contracts via classes, interfaces, annotations, and enums. Implementations execute the behavior.

| API / contract | Required implementation / runtime |
|---|---|
| `jakarta.servlet.*` | Servlet container |
| `jakarta.persistence.*` | ORM/persistence provider or server integration |
| `jakarta.validation.*` | Bean Validation provider |
| `jakarta.enterprise.inject.*` | CDI runtime |
| `jakarta.ws.rs.*` | JAX-RS server/client implementation |
| `java.sql.*` and `javax.sql.*` | JDBC driver, datasource/pool |
| SLF4J | Logging provider/backend |
| Plugin host API | Plugin runtime and extension registration |

API packages may suffice to **compile**, yet rarely create an HTTP server, connect to a database, or bootstrap a validation engine on their own.

### 2.2. What are server-provided dependencies?

A server-managed dependency is a library or API that the runtime host is responsible for supplying to the application. Examples:

- Servlet API present in an external web container.
- Shared JPA/validation services managed by the application server.
- JDBC drivers declared in a server module.
- Plugin SDK APIs exposed by the host loader.
- Host-owned logging bridges or service providers.
- Java SE modules coming from the runtime image.

Not having these components **inside the application artifact** does not mean they are absent at runtime. The converse is also true: a dependency present in a local build may be excluded from packaging due to its scope.

### 2.3. Five questions to answer

For every critical dependency:

1. **Who defines the API?** Java SE, Jakarta EE, a framework, a plugin SDK, or an internal library?
2. **Who implements the behavior?** The app, a provider, the server, an embedded runtime, or an HSM/native bridge?
3. **Who owns the version?** Application team, platform team, server vendor, or plugin host?
4. **Who loads the classes?** Application class loader, server module loader, plugin loader, or JPMS layer?
5. **Who configures providers and lifecycles?** DI container, ServiceLoader, server descriptors, or startup code?

An unanswered question in any item above creates risk when upgrading the JDK or platform.

## 3. Three distinct classpaths and one final artifact

Distinguish among:

- **Compile classpath:** APIs/classes required by javac to compile sources.
- **Runtime classpath:** classes/libraries used by the application while running.
- **Host/server/plugin classpath:** dependencies provided by an external runtime or loaded through a separate loader.
- **Test classpath:** typically broader than production, containing mocks, embedded databases, and test engines.

A project may compile because a dependency sits on the compile classpath, yet miss it at runtime if the host fails to provide the matching type.

| Stage | What is verified | What remains unproven |
|---|---|---|
| Compile succeeds | Source matches APIs on compile path | Server actually supplies that API |
| Packaging succeeds | Build creates WAR/JAR | Server can load and bootstrap it |
| Startup succeeds | Core components initialize | Every plugin, job, or code path runs properly |
| Provider discovered | Registry holds an implementation | Real calls and access permissions work |
| Unit tests pass | Logic in test environment | Integration with production server |

**The final artifact** (WAR, fat JAR, or plugin ZIP) and the execution environment are two sources of truth that must be inspected together.

## 4. Maven provided: present at compile, supplied elsewhere at runtime

A WAR deployed onto an external servlet container may declare:

~~~xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>SERVLET_API_VERSION</version>
  <scope>provided</scope>
</dependency>
~~~

`SERVLET_API_VERSION` is merely a placeholder. The real version must match the actual server.

`provided` means Maven permits compiling and testing against the API while expecting the external environment to supply the dependency at runtime per the deployment model.

It **does not mean the Servlet API does not need to exist at runtime**.

### 4.1. When provided is misused

Suppose an app compiles with a newer Servlet API generation yet deploys to a server providing an older generation. Possible errors include:

- `NoClassDefFoundError` because the server lacks a type.
- `NoSuchMethodError` because the server API version lacks a method.
- `AbstractMethodError` due to binary implementation mismatch.
- Failure to load servlets, filters, or listeners.
- `javax.*` vs. `jakarta.*` namespace incompatibility errors.
- Missing services/providers or server rejecting descriptors.

Do not fix this by tossing more API JARs into the WAR; align the server and API generation properly.

### 4.2. Which APIs should be provided?

Runtime-dependent choices:

| Deployment | Who supplies runtime? | Dependency approach |
|---|---|---|
| WAR on external Servlet container | Server provides engine/API | Servlet API typically `provided` |
| Executable JAR with embedded server | App/framework packages embedded server | Server implementation needed at runtime |
| Jakarta EE server with matching profile | Server supplies documented enterprise services | Can use `provided` for those APIs |
| Standalone main class | No built-in enterprise container | App needs real runtime providers |
| Plugin inside host | Host supplies SDK/extension API | Host API typically omitted from plugin bundle |
| Unit tests | Test runner supplies mocks/embedded components | Test dependencies differ from production |

Consult documentation for the exact deployment platform rather than copying rules from another project.

## 5. Gradle: configurations are not interchangeable

Example:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly("com.example.host:plugin-api:HOST_VERSION")
    implementation("com.example:commons:UTILS_VERSION")
    runtimeOnly("com.example:jdbc-driver:DRIVER_VERSION")
}
~~~

This illustrates syntax with placeholder coordinates.

| Configuration | Module compile | Module runtime | Purpose |
|---|---|---|---|
| `api` (java-library) | Yes | Usually yes | Public dependency exposed to consumers |
| `implementation` | Yes | Yes | Implementation detail |
| `compileOnly` | Yes | Not automatically bundled at runtime | API provided by external runtime |
| `runtimeOnly` | No | Yes | Provider/driver used only at runtime |
| `testImplementation` | Test compile | Test runtime | Test-only dependencies |
| `testRuntimeOnly` | Not for test compile | Test runtime | Test providers/engines |

### 5.1. compileOnly is a promise with the host

If a plugin references `com.example.host.PluginContext` in source, it can compile with a `compileOnly` dependency. However, the host must export that exact type to the plugin loader. A host release with an incompatible API still triggers linkage errors.

### 5.2. api and public contracts

If a public library exposes a method:

~~~java
public com.example.host.PluginContext createContext();
~~~

that external type sits inside the library's public API. When publishing a library, ensure consumers can compile against that contract. In Gradle Java Library, `api(...)` may fit when public types must be exported, whereas host SDKs also require considering `provided` semantics and published metadata. No single configuration fits every platform.

### 5.3. runtimeOnly is not for sources directly importing implementation types

If source calls `new VendorDriver()` or imports provider-specific classes, that dependency belongs on the compile path too. Whenever possible, code against standard APIs and select providers at runtime, yet keep dependency declarations aligned with actual source references.

## 6. WARs, executable JARs, and plugin artifacts

### 6.1. WAR

Common layout:

~~~text
application.war
├── WEB-INF/classes/
├── WEB-INF/lib/
└── WEB-INF/web.xml (if needed)
~~~

Not every server uses identical class-loader policies, yet most distinguish server libraries from application-bundled libraries.

### 6.2. Executable JAR

Standalone applications bundle their own runtimes inside the artifact or external runtime classpath. Frameworks may embed nested JARs with custom launchers. Hence missing a dependency at the JAR root does not prove the dependency is absent; understand the packager's layout.

### 6.3. Plugin archive

A plugin host may expect:

~~~text
plugin-package/
├── plugin.jar
├── lib/plugin-helper.jar
├── lib/third-party.jar
└── plugin-descriptor.properties
~~~

Filenames and packaging vary per host. Some platforms load a single JAR, others use ZIPs/bundles, `META-INF/services`, or JPMS module descriptors.

**Plugin APIs typically belong to the host; implementations belong to the plugin.** Packaging a duplicate copy of the host API inside the plugin can break class identity.

## 7. Class loaders: why two same-named classes are not identical

In the JVM, class identity depends on **binary name and defining class loader**. Two independent loaders can define:

~~~text
com.example.host.Plugin
~~~

in two separate spaces. The JVM treats them as two distinct types.

Example error:

~~~text
java.lang.ClassCastException:
class com.example.host.Plugin cannot be cast to
class com.example.host.Plugin
~~~

Real messages may append module/loader names distinguishing the two definitions. Never treat this as an absurd error or a bug in the cast itself; trace the source JARs and loaders.

### 7.1. Typical loader hierarchy

~~~mermaid
flowchart TD
    A["Plugin class loader"] --> B["Host / parent class loader"]
    B --> C["Platform class loader"]
    C --> D["Bootstrap classes"]
    A --> E["Plugin implementation + private libs"]
    B --> F["Host SDK + shared APIs"]
~~~

Many loaders follow parent-first delegation; plugin hosts may use child-first or package-level rules. Each platform defines its own policy, which can also change between releases.

### 7.2. How duplicate APIs cause failures

The host defines:

~~~java
package com.example.sdk;

public interface Plugin {
    void start(HostContext context);
}
~~~

If the plugin bundles another JAR defining `com.example.sdk.Plugin` and the plugin loader prefers its local copy, instances will not be recognized by the host as implementing the host-loaded interface.

Consequences can include:

- `ClassCastException`.
- `LinkageError`.
- Host failing to register the plugin.
- Annotations/interfaces missed during scanning.
- Providers failing SPI contract checks.
- Reflective lookups comparing `Class<?>` objects with mismatched identity despite equal names.

Usually **a single API must be shared from the host** while isolating implementation details. Follow the host's official mechanism, as framework module systems link classes in specific ways.

### 7.3. Inspecting class loader and code source

~~~java
import java.net.URL;
import java.security.CodeSource;

public final class ClassOrigin {
    public static void inspect(Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        CodeSource source = type.getProtectionDomain()
                .getCodeSource();
        URL url = source == null ? null : source.getLocation();

        System.out.println(type.getName());
        System.out.println("loader=" + loader);
        System.out.println("source=" + url);
        System.out.println("module=" + type.getModule().getName());
    }
}
~~~

`loader` can be `null` for bootstrap classes; module name can be `null` for unnamed modules; code source can also be `null`. This is normal. Avoid logging sensitive paths in public environments.

When encountering duplicate types, compare origins of **the host-loaded class** and **the plugin-loaded class**, rather than merely grepping filenames in the repo.

## 8. Class-loading policies: parent-first, child-first, and server modules

**Parent-first** asks the parent loader first. This helps share APIs yet may force a plugin onto an older library version carried by the host.

**Child-first** lets plugins isolate private libraries, yet readily creates duplicate copies of shared APIs without exclusion rules.

Some servers use package-level delegation or module dependency declarations rather than one simple global order.

Example with two plugins:

~~~text
Host SDK
├── Plugin A
│   └── private JSON library v1
└── Plugin B
    └── private JSON library v2
~~~

Isolating two JSON libraries can be valid if their types never cross the host–plugin boundary. If a host API method takes a JSON class from version A while the host expects version B, the binary contract breaks.

### 8.1. Distinguishing plugin-local types from shared types

Design guidelines:

- Place **host SDK/shared APIs** in a single shared loader tier.
- Keep **implementation-specific dependencies** in plugin-local classpaths where permitted by the host.
- Never expose plugin-local classes across public host contracts without a bridge/version policy.
- Pass DTOs, Java SE types, or serialized data across boundaries when decoupling versions.
- Document which libraries may be shaded or relocated.

### 8.2. When upgrading server-shared libraries

A library in a server module may serve multiple WARs or plugins. Changing its server-level version impacts many applications simultaneously.

Before upgrading:

1. List every consumer.
2. Identify the public APIs and binary signatures they call.
3. Read compatibility notes.
4. Test representative consumers.
5. Plan rollback alongside the server module.
6. Never test only the newest app and assume older apps stay safe.

## 9. Jakarta EE API generation and server compatibility

A major risk when changing frameworks/application servers is enterprise APIs shifting from `javax.*` to `jakarta.*`.

~~~java
// Legacy generation:
import javax.servlet.Filter;

// New generation:
import jakarta.servlet.Filter;
~~~

These two classes have different binary names. A WAR compiled with `javax.servlet.Filter` does not automatically become Jakarta-compatible when deployed to a server supplying only `jakarta.servlet.Filter`.

Elements to synchronize:

- Servlets, filters, and listeners.
- JPA annotations and providers.
- Validation APIs/implementations.
- CDI extension points.
- REST APIs.
- JAXB/Mail/messaging where applicable.
- Framework major versions.
- Application server or embedded runtime.
- XML and service metadata.
- Pre-compiled binary dependencies.

**Do not replace all `javax.` with `jakarta.`**: many Java SE APIs such as `javax.sql.DataSource`, `javax.crypto.Cipher`, and `javax.annotation.processing.Processor` stay in Java SE.

### 9.1. Server profiles determine which runtimes are supplied

A servlet container does not supply the full Jakarta EE Full Platform service suite. Conversely, a full application server may provide many providers yet still require checking exact versions, profiles, and enabled configs.

Never infer from a product brand or the word "Jakarta" on a website that a server includes every API; check **profile, version, and enabled extension modules**.

### 9.2. Upgrading the JDK differs from upgrading enterprise platforms

JDK 11 removed Java EE/CORBA modules formerly bundled in older JDKs under JEP 320. That is separate from enterprise APIs later shifting namespaces in Jakarta EE 9.

It is possible to upgrade the JDK while keeping legacy `javax.*` frameworks if supported with matching dependencies, or upgrade the full stack to Jakarta together. Make both decisions explicitly to avoid over-broad changes.

## 10. Plugin contracts and extension points

Plugins are loaded by a host to extend system capabilities. A host may publish:

~~~java
package com.example.host.api;

public interface Plugin {
    String id();
    void start(PluginContext context);
    void stop();
}
~~~

Plugin:

~~~java
package com.example.plugin.audit;

import com.example.host.api.Plugin;
import com.example.host.api.PluginContext;

public final class AuditPlugin implements Plugin {
    @Override
    public String id() {
        return "audit";
    }

    @Override
    public void start(PluginContext context) {
        context.log("Audit started");
    }

    @Override
    public void stop() {
        // Clean up plugin-owned resources.
    }
}
~~~

Plugins rely on stable host contracts covering:

- Interfaces and method descriptors.
- Lifecycle sequence.
- Threading model.
- Permission model.
- Registration and discovery mechanisms.
- Supported SDK versions.
- Access to host data and services.
- Error handling and hot reload, if supported.

A binary-compatible interface can still change **behavior** such as callback order, transaction context, or callback execution threads. Testing plugins therefore demands more than compilation.

## 11. ServiceLoader and SPI

`java.util.ServiceLoader` provides a standard mechanism to locate service interface implementations.

API:

~~~java
package com.example.spi;

public interface Exporter {
    String id();
    byte[] export(String content);
}
~~~

Implementation:

~~~java
package com.example.plugins.csv;

import com.example.spi.Exporter;
import java.nio.charset.StandardCharsets;

public final class CsvExporter implements Exporter {
    @Override
    public String id() {
        return "csv";
    }

    @Override
    public byte[] export(String content) {
        return content.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

With classpath-based SPI, the implementation JAR provides:

~~~text
META-INF/services/com.example.spi.Exporter
~~~

with content:

~~~text
com.example.plugins.csv.CsvExporter
~~~

Host:

~~~java
import com.example.spi.Exporter;
import java.util.ServiceLoader;

for (Exporter exporter : ServiceLoader.load(Exporter.class)) {
    System.out.println(exporter.id());
}
~~~

### 11.1. Having an implementation does not guarantee discovery

`META-INF/services` files may be missing, provider names wrong, classes stripped during minimization, descriptors overwritten during shading, or the loader unable to see the implementation JAR.

If a plugin uses a separate class loader, host code may need to pass that loader explicitly:

~~~java
ServiceLoader<Exporter> exporters =
        ServiceLoader.load(Exporter.class, pluginClassLoader);
~~~

Even then, the `Exporter` interface must retain **the exact same class identity** across host and provider.

### 11.2. More providers are not always better

When multiple implementations exist for one service:

- The host needs a selection policy.
- Never rely implicitly on classpath ordering.
- Check for duplicate provider IDs.
- Handle missing providers with explicit errors.
- Never fall back silently to a provider violating security/data policies.
- Log active provider names and versions when possible.

### 11.3. Named modules with uses/provides

~~~java
module com.example.spi.api {
    exports com.example.spi;
}
~~~

~~~java
module com.example.csv.provider {
    requires com.example.spi.api;
    provides com.example.spi.Exporter
        with com.example.plugins.csv.CsvExporter;
}
~~~

~~~java
module com.example.app {
    requires com.example.spi.api;
    uses com.example.spi.Exporter;
}
~~~

Distinguish declaring a provider inside a module from actually **resolving** that provider module in a runtime layer. Custom `ModuleLayer` setups and launchers may need explicit service binding/configuration.

## 12. JPMS modules and server modules are not identical

JDK 9 introduced the Java Platform Module System. Yet application servers and plugin hosts may also operate their own module systems:

- **JPMS modules:** `module-info.java`, `requires`, `exports`, `opens`, `uses`, `provides`.
- **Server-specific modules:** dependencies/exports/isolation defined by server configuration.
- **Plugin class loaders:** class namespace partitioning per plugin or extension.

All three models can coexist. Adding `requires` in `module-info.java` does not automatically cause a server module to export that class to every plugin.

### 12.1. Understanding requires, exports, and opens properly

~~~java
module com.example.application {
    requires com.example.api;
    exports com.example.publicapi;
    opens com.example.model to com.example.orm.runtime;
}
~~~

- `requires` establishes readability.
- `exports` grants access to public types in the package.
- `opens` permits deep reflection within the declared scope.

Never add `opens` to cure a `ClassNotFoundException` caused by wrong dependency scopes. Never add `--add-exports` to cure broken provider registration. Classify errors first.

### 12.2. Custom runtime images may lack modules

A server running on a `jlink`-built image contains only selected modules. If an extension needs `java.sql` or a missing JDK provider module, runtime errors appear even though the developer's workstation has a full JDK.

Inspect the exact target runtime:

~~~bash
java --list-modules
~~~

Never assume `java` on a developer shell matches the container/server Java binary.

## 13. Thread context class loader and plugin discovery

Several frameworks and `ServiceLoader` consult the **thread context class loader (TCCL)**. When plugins load separately, TCCL affects provider and resource lookups.

Check it:

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

System.out.println(loader);
~~~

If a callback executes on a different thread from the host thread, TCCL may differ, causing failures only in background jobs.

### 13.1. Hosts modifying TCCL must restore it

When the host intentionally wraps bootstrap:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous =
        current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    invokePluginBootstrap();
} finally {
    current.setContextClassLoader(previous);
}
~~~

This pattern applies to lifecycle-owning code; do not encourage plugins to mutate TCCL arbitrarily. When debugging, log the thread's loader, service interface, implementation, and module layer.

## 14. Hot reload, unloading, and class-loader leaks

A plugin may load cleanly once yet leak on every reload, especially after host or JDK upgrades.

Common causes:

- Host static registries retaining plugin objects.
- Threads spawned by plugins left running.
- Scheduled tasks and executors still active.
- `ThreadLocal` retaining instances from the plugin loader.
- Thread context class loaders not restored.
- Event listeners never unsubscribed.
- JDBC drivers or MBeans still registered.
- Logging appenders/callbacks holding references.
- Timers or caches retaining plugin classes/objects.

Testing should cover:

~~~text
Load plugin
→ Start
→ Execute representative operations
→ Stop and release owned resources
→ Unload
→ Load again
→ Check behavior and resource usage
~~~

Do not fix leaks by arbitrarily shutting down host global services. Plugins should clean up only the resources they own per the platform contract.

### 14.1. Threading is part of the plugin API

If a host moves a callback from synchronous threads to async workers, plugin code relying on thread-local transaction or security contexts can fail silently without compile errors.

Verify:

- Callback threading contracts.
- Security/transaction context propagation.
- Concurrency bounds.
- Shutdown/lifecycle ordering.
- Error propagation.
- Plugin resource ownership.

## 15. Shading and relocation: scoped conflict reduction

When a plugin needs a different library version from the host, relocation can be used for **implementation-private** dependencies.

Conceptual example:

~~~text
com.vendor.json.*  →  com.example.plugin.shadow.json.*
~~~

However, relocation does not automatically fix:

- Public API types referencing the original library.
- Reflection class names in strings.
- Unupdated `META-INF/services` files.
- Serialization type identifiers.
- Resource paths.
- Native libraries.
- Signed JAR metadata.
- Annotation scanning.
- ClassLoader-based service registrations.

Test the packaged artifact inside the real host runtime. Never relocate host SDK types if the host must recognize them with shared class identity.

### 15.1. Fat JARs can drop provider descriptors

Both libraries contain:

~~~text
META-INF/services/com.example.spi.Exporter
~~~

If assembly keeps only one file, the other library's providers vanish. Configure service descriptor merging in the build plugin, inspect the final JAR contents, and run service discovery tests.

## 16. Along which axes do JDK upgrades impact servers and plugins?

| Axis | Risk |
|---|---|
| Class-file version | Plugin/dependency built for a newer JVM |
| Reflection/JPMS | Framework accesses a package no longer opened |
| JDK internal APIs | Legacy plugin/agent relies on unstable internal details |
| Bytecode tooling | ASM/Byte Buddy/instrumentation cannot parse newer class files |
| Java EE-related modules | APIs previously bundled in older JDKs missing in JDK 11+ |
| Security/TLS | Algorithm policies, truststores, and providers changed |
| Default charset/locale/timezone | Data, log, or file behavior shifted |
| Native libraries | JNI, drivers, CPU/OS ABI, and vendor support |
| Runtime image | Custom `jlink` image missing required modules |
| Server framework | Server release not declared compatible with target JDK |

Upgrading the JDK **does not replace** upgrading frameworks, servers, or plugin SDKs. A system may need updates across all three, yet separating risks identifies each source of change.

### 16.1. Compile JDK vs. runtime JDK

Gradle example using a Java 21 toolchain while targeting Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`--release 17` restricts APIs and bytecode for sources compiled by this compiler; it does not downgrade bytecode inside third-party dependencies or native host components to Java 17.

Run the final artifact on **the lowest supported runtime version advertised**.

## 17. Security: class-loader isolation is not a sandbox

A plugin inside the same JVM shares many OS privileges with the host. Separating class loaders manages namespaces and certain boundaries, yet is **not a complete security sandbox**.

Untrusted plugins can still:

- Access data or files readable by the process.
- Open unintended network connections.
- Spawn threads or consume unbounded memory.
- Mutate system properties or global registries.
- Perform reflective operations where access allows.
- Load native libraries or agents when permitted.

Do not rely on the legacy Security Manager as a new sandbox strategy on modern JDKs; support policies changed substantially. For untrusted code, consider **process/container isolation**, OS/network policies, and a well-designed host permission model.

### 17.1. Never open modules globally just to get plugins running

A workaround such as:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

exposes deep reflection into that package across unnamed modules broadly. It does not solve missing APIs or class-loader conflicts.

Identify the exact caller and root cause; prefer upgrading dependencies/hosts, using public APIs, or adding minimal `opens` declarations for app-owned packages.

## 18. Error matrix and fault isolation

| Symptom | Possible failing layer | Investigation focus |
|---|---|---|
| `package ... does not exist` at compile | Compile dependency/API | Source imports, API generation, `compileClasspath` |
| `ClassNotFoundException` | Runtime class visibility | JARs, host modules, class loaders |
| `NoClassDefFoundError` | Runtime linkage or initialization | Cause chain, missing class/module |
| `NoSuchMethodError` | Binary mismatch | Version + method descriptor |
| `AbstractMethodError` | Interface/implementation mismatch | Provider/host SDK generation |
| `ClassCastException` on same class name | Duplicate defining loaders | Host API vs. plugin-local API |
| `ServiceConfigurationError` | SPI/descriptor/provider | `META-INF/services`, loaders, module resolution |
| Plugin fails to register | Host lifecycle/metadata | Plugin descriptors, extension points, versions |
| HTTP 404 despite servlet compiling | Server routing/container | Deployment logs, annotations/descriptors |
| ORM entity not managed | Provider/annotation mismatch | JPA generation, entity scanning |
| `InaccessibleObjectException` | JPMS reflection | Module openness, framework internals |
| `UnsupportedClassVersionError` | JVM baseline | Class-file versions, runtime JDK |
| Fails only after reload | Resource/loader leak | Threads, listeners, registries, TCCL |
| Fails only in background threads | Context class loader | TCCL, executor lifecycle |

The same exception can stem from different causes. Never conclude from the outermost message alone; inspect `Caused by` and verify artifacts and runtimes.

## 19. Diagnostic tools for dependencies and bytecode

### 19.1. Maven dependency tree

~~~bash
mvn dependency:tree
~~~

The tree reveals transitive dependencies and version mediation inside the app, **yet does not necessarily show libraries supplied by the server**.

### 19.2. Gradle dependency report

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-lib \
  --configuration runtimeClasspath
~~~

Inspect plugin/test-specific configurations too when used. A provider present only on the test runtime does not qualify as a production dependency.

### 19.3. Inspecting artifact contents

~~~bash
jar tf path/to/application.jar
jar tf path/to/application.war
~~~

Look for:

- `WEB-INF/lib` and `WEB-INF/classes` in WARs.
- Bundled third-party JARs.
- `META-INF/services`.
- Plugin descriptors.
- `module-info.class`.
- Manifest and Multi-Release JAR metadata.
- Classes stripped by minimization.

### 19.4. Inspecting method descriptors

~~~bash
javap -classpath path/to/host-api.jar \
  -p -s com.example.host.api.Plugin
~~~

Compare the API the plugin compiled against with the API exposed by the host, inspecting method descriptors, class/package names, visibility, and class-file versions.

### 19.5. Class loading logs

On JDKs supporting unified logging:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

On application servers, server-specific logging/management tooling may be needed because multiple class loaders participate. Avoid leaving overly verbose logs active long-term in production without assessing performance and security costs.

### 19.6. jdeps

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

`jdeps` inspects static references and misses SPI, reflection, or dynamic plugin loading. Combine it with runtime probes and artifact inspection.

## 20. Dependency ownership inventory

Migration management table:

| Component | API used | Runtime provider | Version owner | Loaded from |
|---|---|---|---|---|
| Servlet | Jakarta Servlet API | External container | Server team | Server/app loader |
| ORM | Persistence API | ORM/provider | Framework/platform | Server/app |
| JDBC | `java.sql` | Vendor driver | Platform/app | Server/app module |
| Logging | SLF4J API | Logging backend | Host/app | Shared/app |
| Plugin SDK | Extension API | Host services | Plugin host vendor | Parent/shared |
| Plugin helper | Third-party API | Plugin-local JAR | Plugin owner | Plugin loader |
| Java modules | Java SE/JDK | Runtime image | JDK/platform owner | JVM modules |

For every row, record:

- Current and target versions.
- JDK baseline.
- Build scope configuration.
- Whether it is bundled in the WAR/JAR/plugin archive.
- JAR path and class loader at runtime.
- Provider bootstrap mechanism.
- Consumers and transitive dependencies.
- Related tests.
- Owner, tracking ticket, and rollback plan.

### 20.1. Why does ownership matter?

Upgrading a server-shared library can impact multiple apps; upgrading a plugin-local library impacts only that plugin when isolation holds. When ownership is unclear, teams tend to drop extra JARs "to fix the error", producing duplicate types and version skew.

## 21. Safe migration workflow

~~~mermaid
flowchart TD
    A["Inventory JDK, server, plugin host"] --> B["Separate APIs, providers, and owners"]
    B --> C["Cross-check version/namespace/JDK baseline"]
    C --> D["Adjust scopes and packaging"]
    D --> E["Clean artifact build"]
    E --> F["Inspect class origins/SPI metadata"]
    F --> G["Run integration on target host"]
    G --> H{"All scenarios pass?"}
    H -->|Yes| I["Canary, monitoring, rollback plan"]
    H -->|No| J["Investigate loader, linkage, provider, behavior"]
    J --> C
~~~

### Step 1 — Capture baseline

Record JDK vendor/version, server/plugin host version, module list, provider list, JVM flags, and artifact checksums. Collect error logs and metrics, especially from rarely invoked plugin paths.

### Step 2 — Inventory APIs and runtimes

Classify each dependency as app-owned, server-owned, plugin-owned, shared API, Java SE/JDK, or build/test-only. Identify who has authority to upgrade each version.

### Step 3 — Select a supported combination

Cross-check compatibility matrices across:

- JDK and server.
- Frameworks and Servlet/Jakarta generation.
- Plugin host and SDK.
- ORM, validation, logging, and drivers/providers.
- Java agents and native libraries.
- App/plugin bytecode targets.

### Step 4 — Adjust scopes

Use `provided`/`compileOnly` only when the host actually supplies the matching API. Include runtime implementations in standalone artifacts where needed. Never duplicate host API JARs inside plugins when the host manages shared SDKs.

### Step 5 — Build and inspect

Build from a clean workspace and inspect JAR/WAR/plugin archives, service descriptors, and generated classes. Verify binary names with `javap` and dependency conflicts with Maven/Gradle reports.

### Step 6 — Test on the target host

Execute **the packaged artifact** inside the real server/container/plugin host. Exercise HTTP, DB, transactions, loggers, providers, and plugin callbacks. If reload is supported, test stop/unload/reload sequences too.

### Step 7 — Test legacy consumers

If the product promises binary compatibility, run plugins or apps compiled against the old API without recompiling them. Do not test only upgraded sources with the new host.

### Step 8 — Canary and rollback

Monitor:

- Deployment/startup failures.
- Linkage and class-loading exceptions.
- Provider discovery failures.
- HTTP error rates.
- Database/transaction failures.
- Plugin callback latency and errors.
- Memory, thread, or resource leaks after reload.

Rollback may require reverting both the app artifact **and** server modules/plugin SDKs; rolling back only the WAR may not suffice if an incompatible host upgrade already occurred.

## 22. End-to-end scenario: from a legacy-server WAR to a new host

Suppose a baseline system:

- Runs JDK 8.
- Deploys a WAR onto a `javax.servlet` container.
- Relies on server-provided ORM/validation providers.
- Includes plugins that accidentally bundle the host SDK.
- Places its JDBC driver inside a server module.
- Periodically reloads plugins via an admin UI.

The team plans to migrate to a newer JDK and a Jakarta-generation server.

**Potential issues:**

1. Legacy WAR retains binary references to `javax.servlet`.
2. Newer framework uses `jakarta.servlet` while several legacy filters remain unmigrated.
3. `provided` lets local builds pass while the server supplies a different API generation.
4. Plugins ship a second host SDK version, triggering class identity conflicts.
5. The JDBC driver is removed from server modules without being added to the app runtime.
6. Plugin service descriptors vanish during shading.
7. Plugins fail to stop worker threads on reload, leaking class loaders.
8. A custom runtime image misses a module needed by an extension.

**Layered solutions:**

- Align the Servlet API/server generation and update the WAR, framework, and filters together.
- Align JPA/validation providers with the server or switch them to app-owned if required by the new deployment.
- Verify JDBC datasource and driver ownership.
- Strip duplicate host SDK copies from plugins per the host contract.
- Inspect `META-INF/services` inside the final plugin artifact.
- Execute plugin lifecycle tests, especially reloads.
- Inspect JPMS/module lists, class origins, and bytecode targets.
- Perform canary rollouts with coordinated rollback covering both host and app if needed.

Here, **a missing-class error** and **a duplicate-class error** demand opposite fixes. Adding "more JARs" cannot solve every case.

## 23. Common mistakes

### 23.1. "If it compiles, the server has the dependency"

False. Compile-time dependencies may not exist on the host runtime.

### 23.2. "provided and compileOnly mean the library isn't needed"

False. They indicate the library is expected from an external environment at runtime or needed only for compilation.

### 23.3. "Bundling the host SDK inside the plugin plays it safe"

Doing so can create duplicate defining loaders and break binary type identity.

### 23.4. "Child-first and parent-first behave the same for plugins"

False. Delegation policy determines which library wins and which classes are shared.

### 23.5. "Having the provider class means ServiceLoader finds it"

False. Service metadata, class-loader/module resolution, and descriptors must align.

### 23.6. "All javax packages change to jakarta"

False. Many `javax.*` packages belong to Java SE. Enterprise namespace migration must follow specific APIs and specifications.

### 23.7. "One smoke test proves plugin compatibility"

False. Callbacks, async threads, resource cleanup, and plugin reloads can fail later at runtime.

### 23.8. "Adding --add-opens fixes all server errors"

False. Module openness is unrelated to missing APIs, binary linkage, or provider discovery.

### 23.9. "Shading always isolates dependencies safely"

False if public API types, service descriptors, reflection strings, or resources keep old names.

### 23.10. "If the JDK can upgrade, the application server definitely supports it"

False. Servers/hosts have independent compatibility matrices, dependencies, and tooling requirements.

### 23.11. "BOMs include every runtime implementation"

False. BOMs/platforms coordinate versions; they do not automatically pull every runtime dependency.

### 23.12. "Only the application needs rolling back, never the host"

Not necessarily. If host APIs or providers changed, the old app may still fail; align rollback with actual deployment topology.

## 24. Server-managed dependency record template

~~~yaml
component: servlet-api
api_generation: "Jakarta Servlet generation used by application"
runtime_provider: "External container"
version_owner: "Platform team"
compile_scope: "provided"
artifact_bundled: false
server_version: "Recorded production version"
jdk_runtime: "Approved JDK"
verification:
  - "Inspect WAR contents"
  - "Inspect server module/API generation"
  - "Deploy and call servlet/filter endpoints"
migration_state: "PENDING_REVIEW"
~~~

Version strings in the template are placeholders; replace them with real values and evidence in actual projects. Never store credentials, tokens, or sensitive configuration in broadly readable documentation.

## 25. Completion checklist

### Ownership and platform

- [ ] Recorded JDK, server, plugin host, and framework versions.
- [ ] Distinguished Java SE APIs from enterprise/platform APIs.
- [ ] Identified version owners for every dependency.
- [ ] Cross-checked compatibility matrices against the target JDK.
- [ ] Confirmed whether deployment is a WAR, embedded JAR, or plugin archive.

### Dependencies, class loaders, and packaging

- [ ] Verified Maven/Gradle scopes fit the deployment model.
- [ ] Compared compile, runtime, test, and server dependency inventories.
- [ ] Avoided duplicating host APIs inside plugins unless explicitly allowed by the host.
- [ ] Checked binary class names and method descriptors.
- [ ] Verified class-loader origins of critical types.
- [ ] Checked SPI, service descriptors, and module metadata.
- [ ] Confirmed shading/minimization does not drop provider resources.
- [ ] Audited JPMS and custom runtime images where relevant.
- [ ] Verified `javax`/`jakarta` alignment with the server.

### Runtime and operations

- [ ] Deployed the exact artifact on the target host and JDK.
- [ ] Tested HTTP, persistence, datasources, transactions, and logging where used.
- [ ] Exercised real plugin extension points and callbacks.
- [ ] Tested reload/unload and resource cleanup where supported.
- [ ] Checked TCCL inside background threads when SPI is used.
- [ ] Tested legacy binary plugins if the host promises compatibility.
- [ ] Recorded class-loading/linkage errors, metrics, and checksums.
- [ ] Prepared coordinated rollout/rollback plans for both app and host.

## Conclusion

Application platforms, plugins, and server-provided dependencies introduce a compatibility layer extending beyond Java source code. **Compiling does not guarantee deploying cleanly**; a JAR absent from the app artifact may still exist on the server; and identical class names do not guarantee identical types across separate class loaders.

When upgrading a JDK, framework, or host, establish **which API is consumed, which implementation executes it, who owns the version, which class loader loads the classes, and how providers are bootstrapped**. Validate the final packaged WAR/JAR/plugin archive on the actual target server/host and JDK, including full lifecycles and integration paths. Only when these boundaries are clear will an upgrade avoid missing providers, duplicate dependencies, namespace mismatches, and subtle behavioral regressions.
