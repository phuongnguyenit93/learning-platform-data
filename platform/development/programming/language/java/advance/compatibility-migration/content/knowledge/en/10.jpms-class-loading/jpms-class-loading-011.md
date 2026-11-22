# Gradually Migrating Dependencies from Class Path to Module Path

When a long-lived Java application begins adopting the Java Platform Module System (JPMS), moving all libraries from the **class path** to the **module path** in one shot is often impractical. The application may depend on dozens of JARs, frameworks using reflection, libraries without `module-info.class`, code generation tools, Java agents, or plugins loaded by separate class loaders. Some JARs have overlapping packages; others rely on all classes on the classpath seeing one another without declaring dependency relationships.

JPMS allows **incremental migration** from the traditional classpath model to an explicit graph of named modules. Step-by-step rollout requires understanding the boundaries between unnamed modules, automatic modules, and explicit named modules, while verifying not only compilation but also class loading, resource loading, reflection, service discovery, packaging, and rollback capability.

This lesson presents a migration roadmap applicable to library or application projects, along with configuration examples, verification commands, and decision criteria for when to migrate a dependency.

## 1. Goals of the Migration Process

The **classpath** is the set of locations containing classes and resources searched by the JVM or compiler under the class loader mechanism. In the traditional model, application JARs are typically placed on the same classpath. This is convenient for legacy libraries, but does not directly express module contracts, API boundaries, access permissions, or required dependencies.

The **module path** is where JPMS searches for modules to construct a module configuration. Each named module has its own name, set of packages, and declarations of the modules it reads, packages it exports, packages it opens, and services it uses/provides.

Migration goals should be concrete:

- Keep the running system stable while changing how dependencies are organized.
- Migrate artifacts one by one based on readiness instead of forcing all libraries to modularize simultaneously.
- Precisely define public APIs via `exports` and reflection needs via `opens`.
- Detect module name conflicts, overlapping packages, hidden dependencies, and abnormal class loaders early.
- Preserve support for plugins, service providers, and resource data.
- Test the classpath/module path combinations that can actually occur at deployment.
- Gradually remove workaround JVM flags as libraries and frameworks improve their JPMS support.

Having "every JAR on the module path" should not be treated as the ultimate goal. What must be achieved is a runtime configuration with clear, supported, and verified contracts—not merely changing separators in the `java` command.

## 2. Three Module Types to Distinguish

### 2.1. Unnamed Module: The Classpath Model

Code loaded from the classpath typically belongs to the **unnamed module** of the defining class loader. An unnamed module has no name for explicit named modules to declare via `requires`. It has convenient characteristics for compatibility with legacy code, but lacks the explicit declarative structure of JPMS.

Example of a traditional application:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

In the example above, `app.jar` and the JARs in the `lib` directory share the application class loader's classpath. The classpath separator on Windows is `;` instead of `:`.

The advantage is that legacy code runs easily. The limitation is that dependencies and type visibility are typically not modeled through a module descriptor. Classpath order and how the class loader locates resources can affect results, especially when multiple versions of the same library exist.

### 2.2. Automatic Module: A Stepping Stone for Unmodularized JARs

An ordinary JAR **without a module descriptor** placed on the module path can become an **automatic module**. JPMS derives a module name from metadata or filename rules. An automatic module allows a legacy dependency to participate in the module graph without requiring the vendor to immediately release `module-info.java`.

An automatic module typically exports its packages and has transitional module-reading behavior to lower the barrier when bringing legacy classpath libraries into a modular system. However, that **does not turn the library into a well-designed explicit module**, nor does it automatically solve all package, reflection, service loading, and runtime issues.

Example:

~~~text
lib/
  payment-client-2.7.1.jar     # no module-info.class yet
  json-codec-1.9.jar           # no module-info.class yet
~~~

When placed on the module path, each JAR can be treated as an automatic module with a module name determined according to JVM rules.

Risks to verify:

- A module name derived from the filename can change when artifact naming changes.
- The module name may not match the name the vendor plans to use when releasing an explicit module.
- Overlapping packages in the module graph can make the configuration invalid.
- A JAR that "works on the classpath" is not guaranteed to work properly when it becomes an automatic module.
- How modules are resolved and loaders are selected can cause resources/services not to appear as expected.

An automatic module is a **bridge**, not a guarantee that every legacy binary is ready for modular architecture.

### 2.3. Explicit Named Module: A Fully Declared Module

An explicit named module has `module-info.java` in source and `module-info.class` in the compiled artifact. Example:

~~~java
module com.acme.order.core {
    requires java.sql;
    requires com.acme.order.api;

    exports com.acme.order.core.publicapi;
    opens com.acme.order.core.entities
        to org.hibernate.orm.core;

    uses com.acme.order.spi.AuditSink;
}
~~~

This is an illustrative example; Hibernate's module name and those of all other dependencies must be verified from the actual artifact/version before using them verbatim.

Key declarations:

| Declaration | Effect |
|---|---|
| `requires m;` | The current module reads module `m` |
| `requires transitive m;` | The readability relationship to module `m` propagates to modules that read the current module under JPMS rules |
| `requires static m;` | Dependency required at compile time but may be absent at runtime |
| `exports p;` | Exposes public types of package `p` to modules that can read this module |
| `exports p to m;` | Conditionally exports package `p` to module `m` |
| `opens p;` | Allows deep reflection into package `p` at runtime |
| `opens p to m;` | Conditionally allows deep reflection to module `m` |
| `uses S;` | Module declares that it uses service `S` |
| `provides S with Impl;` | Module provides an implementation for service `S` |

**Exports differs from opens.** Exports enables using public types in a package; opens serves deep reflection needs and related resource access rules. Opening every package just to bypass runtime errors often forfeits part of the encapsulation benefit.

## 3. Placing a JAR on the Module Path Does Not Mean the JVM Will Use It

You must distinguish **observable modules**, **resolved modules**, and **readability**.

- **Observable:** a module found in areas observable by the system (such as the module path).
- **Resolved:** a module selected to participate in the module graph configuration, starting from root modules and closing over dependencies.
- **Readable:** a module is permitted to read exported public types from another module under JPMS relationships.

A JAR sitting in a module path directory is not necessarily resolved. A resolved module is not necessarily read by code in another named module. A module may be readable while its internal packages are not exported, so external code still cannot access them.

Example of an application on the classpath needing a library placed on the module path:

~~~bash
java --module-path mods \
     --add-modules com.acme.catalog \
     -cp app.jar com.acme.app.Main
~~~

`--add-modules` requests resolving module `com.acme.catalog`, allowing classpath code to use this module's exported APIs under unnamed module rules. The module name must be the actual name, not an arbitrary package name or guessed filename.

`--add-modules ALL-MODULE-PATH` can be used in certain discovery/migration scenarios, but should not be treated as the default production setting: it pulls extra modules into the configuration, can cause package conflicts, increases initialization scope, and obscures the actual dependency list.

When the application is a named module:

~~~bash
java --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

Module `com.acme.app` is the root; `requires` modules are resolved along the graph. In the Unix-style example, `:` is used to join module path entries; on Windows use `;`.

## 4. Why Migrate Layer by Layer Instead of All at Once?

A system has many parts at different levels of readiness:

~~~text
Application (legacy)
   |
   +-- HTTP framework
   +-- ORM / JDBC
   +-- JSON / XML
   +-- In-house business libraries
   +-- Partner plugins
   +-- Annotation processors and build plugins
   +-- Java agents and monitoring
~~~

Some libraries have already released explicit module descriptors. Some only have `Automatic-Module-Name`. Some lack stable names. Some frameworks require reflective access to entities, controllers, serializers, or internal constructors. If you move all dependencies at once, it is hard to tell apart errors caused by the module graph, reflection, provider discovery, or class loading.

A generally effective strategy:

1. Inventory dependencies and actual runtime relationships.
2. Classify each artifact's JPMS readiness level.
3. Pick libraries with few dependencies and clear APIs as a pilot group.
4. Place one dependency group at a time onto the module path, keeping the rest on the classpath when design allows.
5. Use automatic modules as a controlled bridge.
6. Modularize the main application/host only once dependency relationships are sufficiently clear.
7. Gradually remove temporary configurations and test with the actual production packaging.

Keep a structural constraint in mind: **an explicit named module cannot declare `requires` to an unnamed module**. Therefore, you cannot simply assume "just modularize the application first, leave all remaining dependencies on the classpath" and expect the JVM to handle it automatically. Bridge options such as `--add-reads module=ALL-UNNAMED` can be used during the transitional phase, but that is a managed exception and does not replace defining a proper long-term module graph.

## 5. Inventory Dependencies Before Migrating

A dependency list from Gradle/Maven is an input, but not sufficient. You must consider artifacts loaded at runtime, including JARs that do not appear on the compile classpath of a main module.

You should build a table:

| Artifact | Version | Current Location | JPMS Status | Module Name | Expected Issues | Decision |
|---|---|---|---|---|---|---|
| `order-api.jar` | 1.x | Classpath | Explicit | `com.acme.order.api` | Minimal reflection | Migrate early |
| `legacy-json.jar` | 2.x | Classpath | Automatic | Needs verification | Overlapping packages? | Migrate later |
| `orm-driver.jar` | 5.x | Classpath | Needs checking | Unverified | Reflection/entity | Evaluate separately |
| `partner-plugin.jar` | 3.x | Custom loader | Unknown | Unknown | TCCL/service | Separate phase |
| `build-processor.jar` | 1.x | Processor path | Build-time | Not directly applicable | JDK/processor compatibility | Keep separate |

Minimum fields:

- Group/artifact/version and checksum of the JAR actually used.
- Whether the artifact is an explicit module, an automatic module, or in an unnamed module.
- Whether the module name is explicitly declared, taken from the manifest, or derived.
- Which packages are exported and opened; whether any packages overlap with other JARs.
- Whether other modules use public APIs or touch internal APIs.
- Whether there is dynamic loading, reflection, serialization, service providers, and resource loading.
- Which class loader loads the JAR and whether there is a custom module layer.
- Supported JDK, framework, plugin, and vendor versions.

Do not use a simple "JPMS supported: yes/no" table while ignoring runtime scenarios. A library with a valid descriptor may still not fit the application if the module path changes how frameworks access members.

## 6. Tools to Inspect Module Names and Descriptors

### 6.1. `jar --describe-module`

Use the appropriate JDK `jar` tool to view module descriptors or automatic module information:

~~~bash
jar --file lib/order-api.jar --describe-module
jar --file lib/legacy-json.jar --describe-module
~~~

If the JAR has an explicit descriptor, the tool can display the module name, `requires`, `exports`, `uses`, and `provides`. If the JAR is not yet modularized, the output can show that it will be treated as an automatic module along with the determined module name.

For a multi-release JAR, you may need to specify the appropriate release option to view the descriptor applicable to the target JDK. Check `jar --help` of the exact JDK rather than assuming all versioned entries share the same descriptor.

### 6.2. `jdeps`

`jdeps` helps analyze dependencies expressed in bytecode:

~~~bash
jdeps --summary lib/order-core.jar
jdeps --jdk-internals lib/order-core.jar
jdeps --print-module-deps --module-path lib lib/order-core.jar
~~~

Meaning:

- `--summary`: summarizes dependencies at a high level.
- `--jdk-internals`: detects bytecode references to JDK internal APIs.
- `--print-module-deps`: outputs the set of module dependencies from static analysis that can be used when preparing module configuration or a runtime image.

The `jdeps` output depends on the provided classpath/module path and the set of classes the tool actually analyzes. It does not fully detect:

- `Class.forName("...")` with names constructed from data or configuration.
- Providers looked up via `ServiceLoader` that do not appear in direct bytecode references.
- Fields/methods accessed via reflection or dynamic method handles.
- File resources, templates, schemas, or plugins loaded solely by string name.
- Optional dependencies present only in a specific environment.

Therefore, a `jdeps` report is structural evidence, not proof that the module graph is complete.

### 6.3. Generating a Draft Descriptor

`jdeps` can help generate an initial module descriptor for some JARs without a descriptor. Example command form:

~~~bash
jdeps --generate-module-info generated-module-info \
      --module-path lib \
      lib/legacy-component.jar
~~~

The exact set of options depends on the JDK version and JAR type. The generated descriptor is a **draft** from static analysis; you must review it to determine public APIs, reflective access, services, and optional dependencies. Do not treat the auto-generated output as the final contract.

In particular, `jdeps` cannot infer the full business semantics of `exports` or which packages are internal-only. Only the team owning the API can decide the stable boundaries to expose.

## 7. Establishing Stable Module Names for Dependencies

### 7.1. Explicit Module Name

In an in-house library:

~~~java
module com.acme.metrics.api {
    exports com.acme.metrics;
}
~~~

This name is recorded in the module descriptor and should be designed as part of the release contract.

### 7.2. `Automatic-Module-Name` in the Manifest

If a library is not yet ready to publish a full descriptor, the JAR author can publish a stable module name in the manifest:

~~~text
Automatic-Module-Name: com.acme.legacy.metrics
~~~

When the JAR is on the module path and treated as an automatic module, this name can be used instead of the filename-derived name. That allows consumers to declare `requires com.acme.legacy.metrics;` without depending on the versioned JAR filename.

**Note:** `Automatic-Module-Name` does not create an explicit module and does not define `exports` or `opens` boundaries according to the desired design. It only partially solves the naming problem for automatic modules.

### 7.3. Name Derived from the Filename

If the JAR has neither a descriptor nor an appropriate manifest name, the module name can be derived from the filename according to Java rules. Renaming the artifact or changing the naming convention can alter the name that consumers `requires`.

Therefore:

1. Obtain the actual name using `jar --describe-module`.
2. Record that name in the dependency inventory.
3. Prefer artifacts with a stable module name provided by the vendor.
4. Avoid deriving module names yourself simply by replacing `-` with `.`.
5. When moving from an automatic to an explicit module, confirm the new name still fits or have a migration plan.

## 8. Resolving Split Packages Before Migrating

A **split package** is a situation where multiple modules contain the same package. On the classpath, two JARs can contain classes in `com.acme.util` and the application may still run depending on lookup behavior. In a module graph, overlapping packages can cause resolution errors or prevent the compiler from letting a module read two sources containing the same package.

Example:

~~~text
legacy-core.jar
  com/acme/shared/Format.class

legacy-extra.jar
  com/acme/shared/DateUtil.class
~~~

If the two JARs become two separate named modules that both define `com.acme.shared`, the modular configuration may be rejected. No `requires` option can turn a split package into a healthy module design.

Resolution strategies:

- Upgrade the library to a version whose packages were reorganized by the vendor.
- Intentionally merge the components into one module if the team owns both and it aligns with the release contract.
- Change the namespace/package in a new development line when consumers can be controlled.
- Replace an old library with a newer-generation artifact that has no overlapping packages.
- Keep a dependency on the classpath temporarily if the loader/graph combination allows, while documenting limitations and a remediation plan.

Do not use `--patch-module` to arbitrarily "absorb" a second JAR into the first module without controlling sources, duplicate classes/resources, security, and lifecycle. It is a useful mechanism for well-defined cases such as testing/patching, not a general solution for split packages.

## 9. A Four-Phase Gradual Migration Roadmap

### Phase A — Application Remains on the Classpath

This is the common starting state:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

During this phase:

- Build the module/dependency inventory.
- Run `jdeps` and inspect module metadata.
- Upgrade dependencies to versions supporting the target JDK.
- Separate processors and build tools from runtime dependencies where appropriate.
- Resolve overlapping packages, classpath conflicts, and JDK internal APIs.
- Add integration tests for reflection, resources, and service loading.

The advantage is that the application's launch structure has not yet changed. This is a good time to reduce technical debt before modularizing.

### Phase B — Move Selected Libraries to the Module Path

Keep the app on the classpath while moving ready dependencies to the module path:

~~~bash
java --module-path "mods:lib-modular" \
     --add-modules com.acme.metrics.api,com.acme.catalog.api \
     -cp "app.jar:lib-legacy/*" \
     com.acme.app.Main
~~~

Here:

- `app.jar` and unmigrated dependencies remain on the classpath.
- Selected modules are present on the module path and resolved via `--add-modules`.
- Do not place the same artifact on both the classpath and the module path simultaneously.
- Check transitive dependencies required by the new modules.
- Modules sharing the same package must not conflict in the graph.

After migrating each group, run tests with the actual launch command. Especially test resources read via `ClassLoader` and `ServiceLoader`, because moving from an unnamed to a named module can change behavior even when the artifact stays the same.

### Phase C — Use Automatic Modules for Dependencies Without Descriptors

If a library lacks `module-info.class` but has no severe obstacles, it can be placed on the module path as an automatic module. Once the library has a stable module name, an explicit module can declare:

~~~java
module com.acme.app {
    requires com.acme.catalog.api;
    requires com.acme.legacy.metrics;
}
~~~

The condition is that the actual module name must be accurate, dependencies must be resolved, and no package conflict may break the configuration.

Automatic modules provide a bridge mechanism for legacy libraries, yet risks around reflective access, dynamic class loading, service discovery, and runtime behavior still need testing. An automatic dependency is not a default long-term solution when the team can upgrade to an explicit module with proper JPMS support.

### Phase D — Modularize the Application and Remove Workarounds

Once the dependency graph is relatively stable, add `module-info.java` for the application module, configure the build tool, and switch the entry point:

~~~java
module com.acme.app {
    requires com.acme.catalog.api;
    requires com.acme.metrics.api;

    uses com.acme.spi.ReportFormatter;
}
~~~

~~~bash
java --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

At that point, verify that dependencies used by the app have become appropriate named modules. Remaining classpath code cannot be required by a named module via `requires`, so there must be a concrete plan for bridging, replacing, or modularizing each library.

After this phase, gradually reduce `--add-reads`, `--add-exports`, and `--add-opens`; keep only necessary, reviewed openings.

## 10. Interaction Between Named Modules and Unnamed Modules

This is one of the biggest traps in migration.

Classpath code in an unnamed module can interact with many resolved named modules. Conversely, an explicit named module **cannot explicitly declare a dependency on an unnamed module** using `requires` syntax.

For example, `com.acme.app` is a named module while the library `legacy-driver.jar` remains only on the classpath. If code in `com.acme.app` directly references `legacy.driver.Client`, compilation or execution can fail because the app module has no valid readability relationship to the unnamed module and the package is not guaranteed to be visible as before.

During a transitional phase, there may be a configuration like:

~~~bash
java --module-path mods \
     --class-path "lib-legacy/*" \
     --add-reads com.acme.app=ALL-UNNAMED \
     --module com.acme.app/com.acme.app.Main
~~~

`--add-reads` adds a readability relationship from the specified module to the corresponding unnamed modules. However, it does not automatically solve all accessibility, class loading, package conflict, or missing-runtime-dependency issues. Compile-time configuration must also match; adding flags only at runtime will not fix compiler errors during the build.

Use this flag in a controlled manner:

- Explicitly document the unmodularized dependency and where the flag configuration is applied.
- Reproduce using a launch command equivalent to production.
- Define a plan to replace the flag with a real module or an adapter architecture.
- Verify how IDEs, test runners, and build tools pass the flag.
- Do not treat `ALL-UNNAMED` as a real module that can be used in `requires` in a descriptor.

## 11. Exports, Opens, and Reflective Frameworks

A library can be properly modularized for direct API calls yet still fail when a framework uses reflection. For example, an ORM, JSON serializer, dependency injection, or web framework may need access to non-public constructors, private fields, or annotations in internal packages.

With the module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Public types in `com.acme.domain.api` can be read by consumers. However, a framework attempting to access private fields of entities in `com.acme.domain.model` may encounter `InaccessibleObjectException` if the package is not opened appropriately.

If the framework library has an explicit named module, it can be opened conditionally:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.serialization;
}
~~~

The name `com.acme.serialization` is only illustrative. You must determine the exact module name of the specific framework/runtime; a framework on the classpath belongs to the unnamed module and cannot use an assumed module name.

If the framework is on the classpath and needs a package of a named module opened, a runtime flag can be used during the transitional phase:

~~~bash
--add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED
~~~

Distinguish:

- `--add-reads A=B`: adds readability from module A to module B.
- `--add-exports A/p=B`: exports package p from A to B for ordinary type access.
- `--add-opens A/p=B`: opens package p from A to B for deep reflection at runtime.

These options are not equivalent, and should not be used broadly to mask errors. If an API has been removed or an internal package renamed, `--add-opens` cannot recreate missing classes or methods.

For modern JDKs, do not rely on `--illegal-access` as a long-term solution; this flag's behavior and level of support vary across versions, and newer JDK releases enforce stronger encapsulation.

## 12. Resource Loading When Dependencies Move to the Module Path

A less obvious migration failure: source code is unchanged, the JAR still contains `config.xml`, yet `ClassLoader.getResourceAsStream` returns `null` after placing the JAR on the module path.

The cause may be that the resource resides in a package of a named module and is restricted by module encapsulation. Resource loading APIs do not all behave identically:

~~~java
// Class-relative, using the class as the anchor.
InputStream a = SomeType.class.getResourceAsStream("rules.xml");

// Loader-relative, using the name from the root.
InputStream b = SomeType.class.getClassLoader()
        .getResourceAsStream("com/acme/api/rules.xml");

// Explicitly bound to the module and caller access rules.
InputStream c = SomeType.class.getModule()
        .getResourceAsStream("com/acme/api/rules.xml");
~~~

Remember to close the stream after use and handle the `null` case. In named modules, `Module.getResourceAsStream` checks access permissions based on the caller's module; `ClassLoader.getResource` has different restriction rules for non-`.class` resources inside packages of a named module.

If a library reads internal resources itself, having code inside the module that owns the resource perform the lookup is usually clearer than having consumers guess package paths. If the resource is public data, designing an API to expose that data can be better than opening an entire package just to read a single file.

When migrating dependencies, also verify:

- Whether the resource file is actually packaged in the JAR.
- Whether relative or absolute resource names are correct.
- How the package containing the resource is `opens`.
- Which class loader is used to locate the resource.
- Whether resources with the same name exist across multiple modules or JARs.
- Whether the framework uses TCCL to locate templates or configurations.

## 13. ServiceLoader and Provider Loading via JPMS

Many libraries use a plugin/service provider mechanism. Before JPMS, a JAR commonly had:

~~~text
META-INF/services/com.acme.spi.ReportFormatter
~~~

The file content lists implementation names. When modularizing, a provider in an explicit named module can be declared via the descriptor:

~~~java
module com.acme.format.json {
    requires com.acme.format.api;
    provides com.acme.spi.ReportFormatter
        with com.acme.format.json.JsonReportFormatter;
}
~~~

The consumer module declares:

~~~java
module com.acme.app {
    requires com.acme.format.api;
    uses com.acme.spi.ReportFormatter;
}
~~~

Usage code:

~~~java
ServiceLoader<ReportFormatter> loader =
        ServiceLoader.load(ReportFormatter.class);

for (ReportFormatter formatter : loader) {
    System.out.println(formatter.getClass().getName());
}
~~~

Some errors to investigate:

- The provider module is not resolved in the configuration.
- The provider JAR resides in a different loader/layer.
- The consumer module is missing `uses`.
- The provider module is missing `provides` or has an incompatible legacy provider configuration.
- The service interface is loaded twice by different loaders.
- Code calls `ServiceLoader.load` with a TCCL that cannot see the needed provider.

Do not infer that a provider will be found just because `jar tf` shows a file under `META-INF/services`. You need to check the module descriptor, loader, and layer. For plugin applications that create their own `ModuleLayer`, the `ServiceLoader.load(layer, service)` API may be more appropriate for locating providers in that layer.

## 14. Module Path Does Not Replace Class Loader Design

JPMS adds module structure, yet class loaders still define classes and participate in runtime identity. Two classes with the same binary name loaded by two different defining loaders can still be two distinct types.

A plugin application might use:

~~~text
Application loader
   |
   +-- Main ModuleLayer
   |
   +-- Plugin layer A -> Loader A
   |
   +-- Plugin layer B -> Loader B
~~~

Moving a plugin JAR to the module path does not automatically let the plugin see APIs loaded by another loader or fix cast exceptions. You must define the module layer hierarchy, loader delegation, service discovery, and which API types are shared between plugins and the host.

If a framework uses Thread Context ClassLoader (TCCL), verify TCCL on request threads, executors, and background threads. `ClassLoader.getResource` or `ServiceLoader.load` can behave differently when the context loader is not what was expected.

For dynamic plugins, the modularization roadmap must be designed separately: the application's startup module graph and dynamically created layers do not necessarily share the same root modules or access permissions.

## 15. Gradle Configuration When Migrating Dependencies

Gradle supports JPMS through the Java plugin and module path inference in appropriate versions. An illustrative configuration:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

In the example:

- The toolchain uses JDK 21 to compile.
- `options.release = 17` sets the Java 17 source/API/bytecode baseline.
- `modularity.inferModulePath` lets the Java plugin choose the module path or classpath for dependencies based on metadata in supported contexts.

This is an example for an **already modularized module**, not a command that moves every JAR to the module path regardless of metadata. Check the Gradle/Java plugin version and the actual compile task. If the project has no `module-info.java`, configuration results and inference behavior may differ from expectations.

A Gradle dependency is still declared as usual:

~~~groovy
dependencies {
    implementation 'com.acme:catalog-api:2.0.0'
    implementation 'com.acme:legacy-json:1.9.0'
}
~~~

Whether an artifact is actually placed on the classpath or the module path in compile/runtime tasks must be confirmed via resolved configuration and the JAR's module information, not guessed from `implementation`.

For test source sets and separate plugins, additional module path/patching configuration may be needed for tests to access non-public packages. Do not run only classpath tests and conclude that the production modular configuration will behave identically.

## 16. Maven Configuration and Module-Based Testing

The Maven Compiler Plugin can support module-aware compilation starting from appropriate versions. An illustrative release baseline configuration:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version><!-- version approved by the project --></version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

The example omits a specific plugin version number because it must be chosen based on the Maven/JDK version and the project's dependency policy. When `module-info.java` is added, the compiler plugin exhibits module-aware behavior corresponding to the tool version and how dependencies are resolved.

With Maven Surefire/Failsafe, check the test engine, `useModulePath` configuration where appropriate, module descriptors of test artifacts, and flags needed for reflective access. Not all test runners or older mocking frameworks support the module path in the same way.

Some projects run the production application under JPMS while running tests on the classpath. That may be necessary during a transitional phase, but additional integration tests that actually launch the artifact under the module path are required if you want to ensure a successful migration.

## 17. Verifying Class Loading and Resolution at Runtime

Creating a module descriptor and compiling successfully does not guarantee a valid runtime graph. Possible errors include:

| Symptom | Causes to Investigate |
|---|---|
| `java.lang.module.FindException` | Module not found, name mismatch, or wrong artifact/module path |
| `java.lang.module.ResolutionException` | Conflicting module graph, package conflict, or invalid resolution requirements |
| `IllegalAccessError` | Bytecode accesses a type/member no longer accessible in the module graph |
| `InaccessibleObjectException` | Framework attempts deep reflection on an unopened package |
| `NoClassDefFoundError` | Missing class, wrong loading path, earlier initialization failure, or incompatible binary |
| `ServiceConfigurationError` | Invalid provider/service or not loaded in the proper context |
| Resource lookup returns `null` | Wrong path, missing from packaging, different loader, or resource is encapsulated |
| `ClassCastException` with the same type name | Class defined by different loaders |

To inspect the module graph in use, you can leverage the diagnostic capability of `java --show-module-resolution` in supported JDKs:

~~~bash
java --show-module-resolution \
     --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

Class loading logs help identify where classes are loaded from:

~~~bash
java -Xlog:class+load=info \
     --module-path "mods:lib" \
     --module com.acme.app/com.acme.app.Main
~~~

The commands apply to JDKs supporting the respective options. Do not leave verbose logging enabled continuously in production without assessing the impact on disk space and performance.

## 18. Problems Not Solved by JPMS Alone

Moving to the module path does not automatically fix other compatibility migration issues:

### 18.1. Dependency Version Conflicts

If the application pulls in two incompatible versions of the same library, dependency management must be resolved. The module graph may surface certain conflicts more clearly, but does not automatically guarantee semver or behavioral compatibility.

### 18.2. Deprecated/Removed JDK APIs

A library using `sun.*` or removed APIs will not start working just because it is a named module. You must upgrade the library or replace the API; `--add-exports` and `--add-opens` cannot restore removed APIs.

### 18.3. Annotation Processors and Generated Code

Annotation processors run in the compilation environment and may have their own processor path/module path. Modularizing the runtime does not mean processors must move or have already moved to the module path. Check the toolchain, compiler module visibility, and generated code.

### 18.4. Native Libraries, JNI, and Instrumentation

JNI, native images, Java agents, bytecode enhancement, and instrumentation may require separate access permissions or configuration. Check compatibility with the JDK/OS/CPU, not just the module descriptor.

### 18.5. Runtime Artifacts and Launch Packaging

A configuration that works with separate JARs may not behave the same when packaged as a fat JAR or custom runtime image. The `jlink` tool builds runtime images based on the module graph; automatic modules and some unmodularized dependencies can limit the ability to use that modular packaging workflow. Validate the packaging toolchain with the actual module set.

## 19. Designing a Per-Artifact Migration Policy

A dependency should be migrated when there is sufficient evidence, not merely because "the newer JDK supports the module path".

### 19.1. Early-Migration Group

Suitable for:

- Libraries owned by the project team.
- Clear APIs with minimal deep reflection.
- No split packages.
- Stable module names.
- Unit/integration tests and reproducible artifacts.

You can add an explicit `module-info.java`, run tests, and publish the module name and exports as part of the API contract.

### 19.2. Automatic Module Bridge Group

Suitable for:

- JARs without a descriptor that have a stable or controllable module name.
- No overlapping packages in the planned module configuration.
- Dependencies that can be resolved clearly.
- Reflective access and resource usage that have been tested.

Document clearly that this is a temporary bridge, along with conditions for upgrading to an explicit module when supported by the vendor.

### 19.3. Temporary Classpath Retention Group

Can be kept if:

- Frameworks/plugins do not yet reliably support the module path.
- Split packages exist that cannot yet be separated.
- Resource/service loading is bound to complex custom loaders.
- The vendor's module name is not yet stable.
- Migrating immediately creates unacceptable risk for production.

Keeping something on the classpath does not mean ignoring the issue. Record the owner, blocker, tests, and reassessment date.

### 19.4. Mandatory Replacement or Refactoring Group

Some dependencies rely on removed JDK internal APIs, have unresolvable package conflicts, or require class loader behavior that cannot be maintained. For this group, the solution may be a major version upgrade, library replacement, adapter extraction, or plugin architecture redesign—not adding yet another JVM flag.

## 20. Testing Matrix After Each Migration Step

Environments to verify depend on the system, for example:

| Scenario | Application | Migrated Libraries | Legacy Libraries | What to Verify |
|---|---|---|---|---|
| Baseline | Classpath | Not yet migrated | Classpath | Legacy behavior and initial test results |
| Hybrid | Classpath | Module path | Classpath | Resolution, exports, and resource/service visibility |
| Mixed library | Named module | Automatic/explicit | Classpath with bridge | Readability, reflection, class loader |
| Modular | Named module | Named modules | No longer on main dependency path | Module graph and runtime behavior |
| Plugin | Modular host | Module layer/plugin loader | Some legacy plugins | Discovery, isolation, and loader identity |
| Rollback | Previous version | Depends on deployment strategy | Previous version | Safe return to the prior configuration |

Test categories:

1. **Build and compiler:** valid `module-info.java`, matching source/API baseline, no package conflicts.
2. **Binary API:** existing consumers run with the new dependency when required.
3. **Startup:** root modules and transitive dependencies resolve completely.
4. **Reflection:** ORM, JSON, DI, proxies, test frameworks, and serialization access the right members.
5. **Resources:** templates, configuration files, locale bundles, schemas, and files in encapsulated packages.
6. **Services:** `ServiceLoader`, JDBC drivers, providers, and plugin discovery.
7. **Networking/data:** HTTP, TLS, databases, messaging, and contracts with external systems.
8. **Packaging:** JARs, containers, launcher scripts, and `jlink` images if applicable.
9. **Observability:** logging, metrics, tracing, agents, and error reporting.
10. **Rollback:** previous artifacts and launch commands remain usable if the rollback plan requires them.

You must use the **exact artifacts and launch command** of the real application. Unit tests in an IDE may run on the classpath without crossing module boundaries, and therefore cannot replace integration tests under the module path.

## 21. Change Control and Rollback

When migrating a dependency group, record:

- Baseline JDK/vendor/version and module graph.
- Artifact versions along with checksums.
- Which dependencies moved from classpath to module path.
- Actual module names and descriptors.
- `--add-modules`, `--add-reads`, `--add-exports`, and `--add-opens` flags added or removed.
- Changes to class loaders/TCCL, service providers, and resource lookups.
- Tests executed and observed results.
- Rollback conditions along with artifact/configuration versions to restore.

A rollback plan should not merely say "move JARs back to the classpath". If the application has added `module-info.java` and become a named module, it may no longer run as-is with all legacy dependencies on the classpath. Prepare artifacts or launch configurations compatible with the previous architecture, and test rollback as an actual combination.

With rolling deployments or multiple services, changing the module path is an internal runtime change, yet it can expose binary behavior, provider discovery, or serialization bugs. Do not bundle a JDK upgrade, major framework upgrade, full dependency modularization, and external protocol changes into a single rollout if they can be separated.

## 22. Checklist Before Migrating a Dependency

- [ ] Identified the exact JAR/version/checksum used at runtime.
- [ ] Determined whether the artifact is an explicit, automatic, or unnamed module in the current configuration.
- [ ] Verified the module name using JDK tools rather than guessing from the filename.
- [ ] Searched for split packages and module name conflicts.
- [ ] Reviewed relevant `requires`, `exports`, `opens`, `uses`, and `provides`.
- [ ] Determined whether `--add-modules` is needed to resolve modules.
- [ ] Checked interaction constraints between named modules and unnamed modules.
- [ ] Reviewed reflective access and only used package openings with clear scope.
- [ ] Checked resource lookup, ServiceLoader, and Thread Context ClassLoader.
- [ ] Checked custom loaders, dynamic module layers, and plugins if present.
- [ ] Ran build/test under the real module path and the exact target JDK.
- [ ] Tested scenarios that occur only in production packaging.
- [ ] Recorded bridge flags, owners, and removal plans.
- [ ] Prepared appropriate rollback artifacts and launch configurations.
- [ ] Updated the inventory after the dependency group migrated successfully.

## 23. Conclusion

Migrating dependencies from the classpath to the module path is a **process of changing the class loading architecture and API contract management**, not just replacing `-cp` with `--module-path`. JPMS provides unnamed modules for compatibility with classpath code, automatic modules as a bridge for JARs without descriptors, and explicit named modules to express dependencies, exports, opens, and service contracts explicitly.

A viable roadmap is to inventory artifacts, resolve package conflicts, verify module names, choose a low-risk library group, run a hybrid configuration, gradually transition to explicit modules, and test against the actual runtime/packaging. Each step must distinguish **whether a module can be found**, **whether the module is resolved**, **whether a module reads another module**, and **whether a package is actually opened or exported**.

Only once there is evidence across compilation, class loading, reflection, resources, services, consumer compatibility, and rollback capability should the team consider a dependency successfully migrated. A system that still keeps a few dependencies on the classpath—yet is clearly managed and thoroughly tested—is usually safer than a system moved entirely to the module path that relies on numerous untracked workarounds.