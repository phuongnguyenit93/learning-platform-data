# Problems JPMS solves and problems it does not solve

The Java Platform Module System (JPMS), introduced into the Java platform in Java 9, adds an official module model for Java applications. Before JPMS, many applications organized libraries using JARs and the classpath. That approach worked, but dependency boundaries and package access scopes were often not thoroughly described. JPMS helps applications declare dependencies explicitly, restrict exposed packages, and build a module graph that can be checked at compile time or launch time.

To evaluate JPMS accurately, you must distinguish problems belonging to module structure from problems belonging to builds, distribution, security, and operations. JPMS establishes module-level boundaries and rules; it does not replace the entire Java tooling ecosystem.

## 1. Why did Java need a module model?

In the traditional classpath model, the JVM and compiler locate classes from a list of directories or JARs. A class can be found without a library-level dependency declaration indicating which module uses it. Packages are also primarily a way to group classes by name; packages do not by themselves create access boundaries between JARs.

This creates several difficulties:

- **Hidden dependencies:** a library can use classes from another library simply because that JAR happens to be on the classpath. Readers of build files and source code struggle to determine the full dependency relationships.
- **Overly broad access scope:** public classes in a package can become entry points for code elsewhere, even when the author only intended that package as an internal detail.
- **Late configuration errors:** missing classes or missing library versions may only surface when a specific execution path runs.
- **Difficulty creating small runtimes:** an application may ship with more JDK components than needed if the deployment process cannot determine the exact set of modules actually used.
- **Difficulty decoupling API from implementation:** calling code often has to know concrete implementation classes rather than depending solely on a service contract.

JPMS provides a module description language and runtime mechanisms to address the structural part of these problems.

## 2. Problems JPMS solves

### 2.1. Explicit dependency declarations

A named module describes its dependencies using the **requires** directive in **module-info.java**. Example:

~~~java
module com.acme.orders {
    requires com.acme.customer;
    requires java.logging;

    exports com.acme.orders.api;
}
~~~

The descriptor states that the **com.acme.orders** module needs to read the **com.acme.customer** module and the **java.logging** module. The compiler can check whether referenced types reside in modules that the current module can read. At runtime, the module system resolves the dependency graph from root modules and reports an error if a mandatory dependency cannot be found or the configuration is invalid.

This declaration helps:

- Make direct module relationships visible right in the source code.
- Distinguish mandatory dependencies from compile-time-only optional dependencies via **requires static**.
- Expose dependencies that consumers also need to read using **requires transitive** when dependency types appear in the module's API.
- Catch certain missing-module or module-configuration errors before the corresponding code path is invoked.

For example, **requires transitive** makes sense when the public API of module A returns or accepts types belonging to module B. Module C, declaring only **requires A**, can still read B via the transitive relationship published by A.

This is an improvement in structure and checkability. It does not mean JPMS downloads libraries from the Internet or selects compatible dependency versions; those jobs belong to build and distribution tools.

### 2.2. Controlling which packages are public API

JPMS elevates access boundaries to the module level. A package is only accessible to other modules as API when the module owning that package exports it.

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

A consumer can use public types in **com.acme.catalog.api** if it reads the **com.acme.catalog** module. Other packages of the module remain hidden from external named modules, even if classes inside them are declared public.

This mechanism helps library authors:

- Publish an intentional set of API packages.
- Keep implementation packages internal.
- Reduce unintended reliance on classes and packages not supported as API.
- Have room to change implementations with less impact on consumers.

Consumers can be restricted with a qualified export:

~~~java
exports com.acme.catalog.internal.spi to com.acme.application;
~~~

In this case, the package is exported to the specified target module. This is a tool for describing a controlled shared internal API, such as an SPI between two modules belonging to the same system.

### 2.3. Distinguishing API access from deep reflection

Frameworks may need reflection to read non-public fields, constructors, or methods. JPMS separates this permission from ordinary API access.

- **exports** allows access to public types in the package according to Java language rules.
- **opens** allows deep reflection into types in the package at runtime, within the scope of opened modules.

Example:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Consuming modules can import APIs from the **com.acme.domain.api** package. The **com.acme.json** module can use deep reflection on the model package opened to it. The model package does not thereby become an API that can be freely imported.

JPMS also allows opening an entire module with **open module**, or opening a package restrictively with qualified opens. Opening only the exact packages and exact consumers maintains better encapsulation than opening the whole application to every reflection library.

### 2.4. Determining a valid module graph

The module system resolves a set of modules and their dependency relationships into a **Configuration**. Required modules are located through observable module sources, such as system modules or the module path. Which modules enter the configuration depends on the root modules and required dependencies; merely having a JAR on the module path does not mean it is always resolved into the application.

The resolution process helps verify:

- Whether mandatory modules can be found.
- Whether module names and dependencies match descriptors.
- Whether the dependency graph is valid.
- Whether packages are split in disallowed ways within the same named-module configuration.
- Which modules are included in the launch configuration.

The module system also enforces readability rules: a module must read another module before code can reference public types exported from that module. Thus, having a class on disk and having permission to access the class are two separate conditions.

Because of the module graph, configuration errors can be detected during compilation or launch instead of only appearing in a rarely executed feature.

### 2.5. Reducing direct coupling with services

JPMS integrates Java's service model. A module needing a service declares **uses**; a module supplying an implementation declares **provides ... with ...**.

~~~java
module com.acme.application {
    requires com.acme.spi;
    uses com.acme.spi.ReportExporter;
}
~~~

~~~java
module com.acme.csv.exporter {
    requires com.acme.spi;

    provides com.acme.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

The application can look up providers via **ServiceLoader**:

~~~java
ServiceLoader.load(ReportExporter.class)
    .forEach(exporter -> exporter.export(report));
~~~

The application depends on the service interface instead of needing to know concrete implementation classes upfront. A new provider can be added without rewriting the service-calling code, provided the provider follows the contract and is included in the appropriate configuration/layer.

This mechanism is useful for drivers, serializers, exporters, adapters, and plugins. However, ServiceLoader only solves declaring and finding providers; it is not a complete plugin lifecycle management system.

### 2.6. Creating a runtime image tailored to the application

When an application and its required components can be described as modules, the **jlink** tool can create a runtime image containing only the selected set of modules along with the needed runtime. This supports distributing an application with a tailored runtime instead of always requiring a full JDK installation.

Illustrative example:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.application   --output app-runtime
~~~

The **com.acme.application** root module pulls in the required dependency modules into the configuration. The runtime image can be smaller than a full JDK and helps control the runtime components shipped with the application.

This benefit depends on packaging. Libraries remaining on the classpath or components incompatible with the module linking process require separate handling. **jlink** also does not automatically update the runtime image when the application changes; the build and release pipeline must still produce and distribute a new image.

### 2.7. Supporting step-by-step migration

JPMS does not force every library in the ecosystem to migrate at the same time. An application can coexist with:

- Named modules with **module-info.class**.
- Automatic modules whose names are derived from the manifest or JAR filename when placed on the module path.
- Code on the classpath belonging to the unnamed module.

This enables incremental migration. However, automatic modules and the unnamed module have different packaging, readability, and encapsulation rules than named modules. To realize the full benefits of JPMS, key components should be moved to explicit descriptors with well-defined API packages.

## 3. Problems JPMS does not solve

### 3.1. Does not replace Maven, Gradle, or dependency management tools

JPMS is not a package manager and not a library version resolution system. The **requires** directive declares modules that the application needs to read; it does not express version ranges like a Maven or Gradle dependency declaration.

JPMS does not by itself:

- Download JARs from repositories.
- Select the newest version or a version satisfying a version range.
- Resolve version conflicts according to mediation rules.
- Lock versions to produce reproducible builds.
- Manage checksums, repositories, credentials, or artifact publishing workflows.

For example, a build file still must select the artifact and version:

~~~groovy
dependencies {
    implementation 'com.acme:customer-api:2.4.0'
}
~~~

In the module descriptor, the application declares the module name provided by the artifact:

~~~java
module com.acme.orders {
    requires com.acme.customer;
}
~~~

The build tool selects the specific JAR; the module system checks the module name and dependency relationships of that JAR. The two mechanisms complement each other.

Within a resolved configuration, a module name is an identifier for resolution and there is no general version mediation mechanism. Putting two versions of the same library into the same module configuration is not a conflict-handling approach automatically supported by JPMS. Separate layers can serve certain advanced designs, but they do not replace build system dependency version management.

### 3.2. Not a security sandbox

JPMS encapsulation controls module readability and package accessibility. It does not isolate malicious code or restrict a module's operating system privileges.

A plugin loaded into the same JVM can still perform actions that the process has permission to perform, such as accessing files, opening network connections, or spawning threads, depending on the environment and execution permissions. A module descriptor does not grant an independent permission set per module.

Therefore:

- Do not run untrusted plugins simply because they reside in named modules.
- Do not treat unexported packages as a boundary against malicious code.
- Do not use **ModuleLayer** as a substitute for process isolation, containers, separate OS accounts, or an appropriate sandbox mechanism.
- Do not treat **opens** as a general security permission mechanism; it only governs deep reflection between modules.

Strong encapsulation is a structural boundary within the Java platform, not a trust boundary between two processes.

### 3.3. Does not design domain boundaries or application architecture on its own

JPMS lets you divide an application into modules, but it does not decide how to divide the domain. If you lump too many unrelated features into one module, or create tiny modules just to increase module count, the architecture can still be hard to understand.

JPMS does not by itself:

- Identify bounded contexts or domain models.
- Decide which module owns which data and business logic.
- Design stable APIs between teams.
- Prevent all architecturally backward dependencies if modules are still declared to allow them.
- Automatically detect that an API package has accumulated too many responsibilities.

The development team still must decide module boundaries, code ownership, API contracts, and dependency directions. JPMS helps enforce part of those decisions at the package/module level.

### 3.4. Does not replace a plugin system and lifecycle management

**ServiceLoader** and **ModuleLayer** provide the foundation for discovering services and defining modules in separate layers. However, a complete plugin system needs many more capabilities:

- Rules for discovering and installing plugins.
- API compatibility version checking.
- Managing initialization, active, error, and stopped states of plugins.
- Per-plugin configuration, logging, metrics, and error handling.
- Upgrade or rollback policies.
- Rules for communication and data sharing between host and plugins.

Being able to create a layer does not mean plugins have a lifecycle. The module system also does not provide a module unload operation in the sense of a single command guaranteed to immediately free all classes and resources. Class unloading depends on JVM garbage collection of the class loader and related references; if a layer or class loader remains referenced, its classes can persist.

An application needing dynamic plugins must design its own lifecycle contract and resource reclamation process. If safe plugin updates or running untrusted code is required, separate processes may be necessary.

### 3.5. Does not completely eliminate the classpath and legacy libraries

JPMS supports a transition period, but it does not automatically turn every old JAR into a well-designed module. Automatic modules are a compatibility bridge. The unnamed module lets code on the classpath keep running. Both can leave module boundaries loose.

If most code remains on the classpath:

- Module-level dependencies are not fully declared.
- Internal packages of legacy libraries may lack the desired encapsulation.
- Compatibility options such as **--add-reads**, **--add-exports**, or **--add-opens** may be used to keep legacy applications working.
- Access-control benefits of named modules apply only within the scope managed by the module system.

Thus, adding a descriptor file to one part of a project does not mean the whole application has a clear modular architecture.

### 3.6. Does not automatically guarantee API compatibility and upgradability

JPMS helps publish API packages and hide internal packages. It does not automatically guarantee that exported APIs are compatible across versions. A change can break source compatibility or binary compatibility even if the descriptor remains unchanged.

The development team still needs:

- An API versioning policy.
- Compatibility testing.
- Deprecation and migration procedures.
- Dependency checks prior to upgrading.
- Documentation of API behavior and contracts.

An exported package only means the module allows access to that package; it is not a promise that every class and method in the package will remain stable forever.

### 3.7. Does not solve all packaging and deployment problems on its own

JPMS describes modules and supports runtime images, but it does not replace the entire release pipeline. Applications still must decide:

- How to produce JARs, images, or installers.
- How to manage environment configuration and secrets.
- How to release, update, roll back, and track versions.
- How to distribute native libraries or out-of-module resources.
- How to deploy on servers, containers, or target devices.

Module descriptors do not contain application operations workflows. **jlink** creates a runtime image; the pipeline still must test and release that image.

## 4. Responsibility allocation table

| Need | How far does JPMS help? | Commonly paired mechanisms/tools |
|---|---|---|
| Declare which module depends on which module | Yes, via **requires** and module resolution | Maven, Gradle to select artifacts and versions |
| Publish API packages | Yes, via **exports** | API design, architecture reviews |
| Grant frameworks deep reflection | Yes, via **opens** | Framework configuration and access control |
| Discover service implementations | Yes, via **uses**, **provides**, and **ServiceLoader** | Plugin manager to manage lifecycle and configuration |
| Resolve the module graph at launch | Yes | Module path, launcher, and deployment configuration |
| Build a runtime image with required modules | Yes, through **jlink** | CI/CD and runtime distribution workflows |
| Download dependencies and version mediation | No | Maven, Gradle, or corresponding dependency tools |
| Sandbox untrusted code | No | Process isolation, containers, and OS policies |
| Design domain boundaries | Does not decide automatically | Application architecture and team conventions |
| Upgrade, rollback, plugin lifecycle | Not fully provided | Plugin framework or custom management logic |
| Ensure API compatibility across versions | No | Versioning, compatibility tests, and release processes |

## 5. Example: choosing the right tool for a problem

Suppose a reporting application has three parts: a business module, a CSV library, and a PDF report export plugin.

**Scenario A — the application unintentionally references an internal package**

If the business module imports a class in the CSV library's implementation package, inspect the library's descriptor. Export only the required API packages and keep implementation packages unexported. This is a problem JPMS solves directly.

**Scenario B — the build is pulling in two versions of the CSV library**

If the dependency graph contains two artifact versions, handle it with dependency constraints, version catalogs, exclusions, or Maven/Gradle resolution rules. JPMS does not choose the desired version on its own. Once the build selects the artifact, the descriptor specifies the module the code needs to read.

**Scenario C — wanting to add a PDF provider without editing service-calling code**

Define the service interface in an API module, declare **uses** in the application module, and **provides** in the plugin module. This is a good fit for ServiceLoader. If you need to enable/disable, configure, or update plugins, add a lifecycle manager.

**Scenario D — third-party supplied plugins**

Creating a custom ModuleLayer can help organize modules and class loaders. However, if plugins are untrusted, they still need to run in an isolated process or appropriate isolation environment. A layer does not restrict a plugin's file system or network privileges.

**Scenario E — wanting to reduce runtime size**

Analyze required modules and build a runtime image with jlink. This falls under JPMS/JDK tooling. Packaging the image into an installer or container and updating the image still belong to the deployment pipeline.

## 6. How to decide whether to use JPMS

Start by asking about the kind of problem:

1. **Want explicit, checkable dependencies?** Use named modules and declare **requires**.
2. **Want to limit the API visible to consumers?** Use **exports** and keep internal packages unexported.
3. **Framework needs reflection?** Open the exact packages with **opens**, restricting target modules if possible.
4. **Want to swap implementations via services?** Use **uses**, **provides**, and **ServiceLoader**.
5. **Want to create a smaller runtime image?** Consider **jlink** after identifying module dependencies.
6. **Want to download dependencies, resolve versions, or lock builds?** Configure Maven/Gradle.
7. **Want to run untrusted code?** Design sandboxing or process isolation at the operational layer.
8. **Want to upgrade and manage plugins?** Build lifecycle, compatibility, and rollback alongside ModuleLayer.

Not every application needs a full migration right away. For small applications, the classpath may remain sufficient for current goals. For shared libraries, large applications with multiple development teams, or runtimes that need trimming, named modules can deliver clearer benefits. Choose the migration scope based on the dependency and encapsulation boundaries the system genuinely needs.

## 7. Conclusion

JPMS fills an important gap in Java: describing dependencies and access permissions at the module level. It helps the compiler and runtime understand what a module needs, which packages are exposed, which packages are opened for reflection, which services are consumed, and which providers are registered. When modules are well designed, applications can achieve clearer dependency graphs and create tailored runtime images.

Other responsibilities remain at other layers. Maven/Gradle manage dependencies and versions; application architecture defines domain boundaries; ServiceLoader is only a service discovery mechanism; ModuleLayer is not a sandbox; release pipelines manage deployment and updates. Understanding these exact limits helps you use JPMS for the right job and avoid expecting it to replace tools built for different problems.