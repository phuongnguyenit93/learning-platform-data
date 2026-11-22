# Automatic Modules and Transitioning to Explicit Modules

The Java Platform Module System (JPMS) was designed to support migrating from traditional Java libraries to modular applications. In practice, many libraries are still released as JARs without **module-info.class**. To let these JARs participate on the module path and be used by named modules, Java provides the **automatic module** mechanism.

An automatic module is a migration bridge: it allows a legacy library to be referenced by module name and join the module graph without modifying source code to add a descriptor. Once the library is ready, developers can add **module-info.java** to turn it into an **explicit module**, explicitly declaring dependencies, API packages, and service contracts.

## 1. JAR on the Classpath vs. JAR on the Module Path

A traditional JAR placed on the classpath belongs to the **unnamed module**. The JVM does not use a per-JAR module descriptor to determine which packages are exposed or which modules depend on it.

Example of running an application with the classpath:

~~~bash
java -cp "lib/*:app.jar" com.acme.app.Main
~~~

When moving a JAR without **module-info.class** to the module path, Java can treat it as an automatic module. The JVM synthesizes an automatic module descriptor based on the JAR and its metadata.

Example:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

If the modular application declares **requires** on the automatic module, that module can be resolved as a named module. This is an important difference: a JAR on the classpath belongs to the unnamed module; that same JAR on the module path can become a named automatic module.

| JAR Location | How the JVM Manages It |
|---|---|
| Classpath | Belongs to the unnamed module; has no individual module name to declare in **requires**. |
| Module path, with **module-info.class** | Is an explicit named module with a publisher-declared descriptor. |
| Module path, without **module-info.class** | Can be treated as an automatic module with a synthesized descriptor. |

A regular named module cannot declare **requires** on the unnamed module. Therefore, automatic modules are a useful intermediate step when a library lacks a descriptor yet the application wants to move to the module path.

## 2. How Is an Automatic Module's Name Determined?

An automatic module needs a name so other modules can reference it. There are two main sources:

1. The JAR's manifest has the **Automatic-Module-Name** attribute.
2. If that attribute is absent, Java derives the name from the JAR file name according to automatic module naming rules.

Example manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy.json
~~~

With this attribute, the JAR is recognized as **com.acme.legacy.json** when placed on the module path, even if the artifact file name changes across versions.

If **Automatic-Module-Name** is not declared, the module name is derived from the filename. For example, a JAR named:

~~~text
legacy-json-parser-2.4.1.jar
~~~

may be derived as a name like **legacy.json.parser**. The derivation algorithm strips an appropriate version portion and converts invalid separators to dots according to JDK rules. You should not guess the final name in your build; verify it using JDK tools.

Inspect the module name:

~~~bash
jar --describe-module --file mods/legacy-json-parser-2.4.1.jar
~~~

Or run **jar --describe-module** on the specific JAR after placing it in the project's dependency directory.

Names derived from filenames can change when an artifact is renamed or version packaging changes. For libraries intended for long-term use on the module path, publishers should declare **Automatic-Module-Name** to keep the module name stable even before adding an explicit descriptor.

## 3. Readability and Exports of an Automatic Module

Automatic modules have broader semantics than explicit modules:

- They read all other modules in the module configuration, allowing legacy libraries to continue accessing many dependencies when moved to the module path.
- All packages of an automatic module are exported, so a named module can access public types in its packages if that module reads the automatic module.
- They do not require the publisher to provide **module-info.java** in order to start participating in the module graph.

Example application:

~~~java
module com.acme.application {
    requires com.acme.legacy.json;
}
~~~

If the JAR on the module path is recognized as **com.acme.legacy.json**, the application module can read packages exported by the automatic module.

This broad compatibility makes migration easy to start, but also makes module boundaries less strict. An explicit module exports only selected packages; an automatic module exports every package in the JAR. Internal packages meant only for implementation can become accessible from other modules.

Automatic modules also have broad readability of other modules. That helps legacy libraries whose dependencies are not yet described with JPMS, but makes the module graph reflect actual dependencies less accurately. This is why automatic modules should be treated as a transitional step, not the target design for new libraries.

## 4. Why Migrate to an Explicit Module?

An explicit module has **module-info.class** compiled from **module-info.java**. The descriptor clearly specifies:

- A stable module name.
- Direct dependencies via **requires**.
- Dependencies passed on to consuming modules via **requires transitive**.
- Exposed API packages via **exports**.
- Packages needing reflection opened via **opens**.
- Services consumed by the module via **uses**.
- Services provided by the module via **provides ... with ...**.

Example:

~~~java
module com.acme.json {
    requires java.logging;

    exports com.acme.json.api;
}
~~~

With this descriptor, the **com.acme.json.api** package is exposed to other modules; implementation packages like **com.acme.json.internal** remain encapsulated if unexported. The **java.logging** dependency is also explicitly expressed.

When a library transitions from an automatic to an explicit module, consumer accessibility may change. A package previously exported by the automatic module may no longer be accessible if the explicit descriptor does not declare **exports**. Likewise, a dependency previously read broadly by the automatic module may need to be explicitly declared with **requires**.

## 5. Step-by-Step Migration Roadmap

You can migrate a legacy library to an explicit module in the following phases.

### Phase 1: Inventory Libraries on the Classpath

First, identify the JARs, dependencies, and packages used by the library. Inspect dependencies resolved by the build tool, public APIs, and frameworks that use reflection.

In this phase, the library can still be used on the classpath. The goal is to understand the scope of packages and dependencies before changing distribution.

### Phase 2: Move the JAR to the Module Path

If the JAR lacks **module-info.class**, place it on the module path so Java recognizes it as an automatic module.

Use **jar --describe-module** to view the recognized name and packages:

~~~bash
jar --describe-module --file lib/legacy-json-parser-2.4.1.jar
~~~

If the derived module name is unsuitable or unstable, request the publisher to add **Automatic-Module-Name**. If you own the library, you can add the manifest attribute to your artifact.

### Phase 3: Fix the Module Name

Before publishing a dependency module name to consumers, stabilize the name via the manifest:

~~~text
Automatic-Module-Name: com.acme.json
~~~

Keep this name unchanged when adding an explicit descriptor. Consumers can declare **requires com.acme.json** during both the automatic and explicit phases if the name is maintained consistently.

This is a key step so the transition does not force every consuming module to rename its dependency when the library gains **module-info.class**.

### Phase 4: Analyze Dependencies and Packages

You can use **jdeps** to analyze the JAR's dependencies:

~~~bash
jdeps --summary lib/legacy-json-parser-2.4.1.jar
~~~

View module-level dependencies:

~~~bash
jdeps --print-module-deps lib/legacy-json-parser-2.4.1.jar
~~~

Analyze package and module dependencies in greater detail:

~~~bash
jdeps --verbose:class lib/legacy-json-parser-2.4.1.jar
~~~

The output serves as supporting data for designing the descriptor, not a complete descriptor in every case. Tools may fail to infer dependencies involved in reflection, service loading, runtime configuration, or dynamically generated class names. Combine analysis with knowledge of the API and how the library actually runs.

### Phase 5: Create module-info.java

After identifying dependencies and API packages, create the descriptor:

~~~java
module com.acme.json {
    requires java.logging;

    exports com.acme.json.api;
}
~~~

If the library needs services, add **uses** or **provides** according to its role. If a framework needs deep reflection, open only the necessary packages via **opens** or qualified **opens**. Do not export every package just to keep all existing accesses working.

You can use:

~~~bash
jdeps --generate-module-info generated-modules lib/legacy-json-parser-2.4.1.jar
~~~

This command generates suggested descriptors in the target directory for the modules the tool can analyze. Treat the output as a starting point to edit; do not copy it blindly into the library because requirements for services, reflection, and API compatibility may need additional declarations.

### Phase 6: Compile and Package the Explicit Module

Compile the module descriptor together with the source code:

~~~bash
javac -d out --module-source-path src -m com.acme.json
~~~

Package:

~~~bash
jar --create --file mods/com.acme.json.jar -C out/com.acme.json .
~~~

Inspect the packaged descriptor:

~~~bash
jar --describe-module --file mods/com.acme.json.jar
~~~

The output should show the intended module name, dependencies, exported packages, and service declarations. Confirm that the explicit module name keeps the same name published earlier as an automatic module.

### Phase 7: Test Module Consumers

Run real consumer modules on the module path. Test compilation, unit tests, reflection, service loading, and runtime image packaging if the project requires **jlink**.

Do not test only the library module in isolation. Changes to exports, requires, and opens may only reveal errors when a consuming application tries to import packages, perform reflective access, or instantiate services.

## 6. Keeping Automatic-Module-Name Stable During Transition

Suppose the older version of the library has the manifest:

~~~text
Automatic-Module-Name: com.acme.legacy.client
~~~

Consumers declare:

~~~java
module com.acme.app {
    requires com.acme.legacy.client;
}
~~~

When the publisher adds an explicit descriptor, the name in the descriptor should continue to be:

~~~java
module com.acme.legacy.client {
    exports com.acme.legacy.client.api;
}
~~~

If the explicit module uses a different name, every consumer with **requires com.acme.legacy.client** may need updating. That creates an unnecessary migration change.

The module name is a JPMS-level identifier; JAR file names and Maven/Gradle coordinates can vary independently. You can change the artifact version or filename while preserving the module name. When moving to an explicit module, maintaining the published module name makes upgrades far less disruptive.

## 7. Changes in Export Behavior When Moving from Automatic to Explicit

This is one of the easiest differences to cause breakage. An automatic module exports all packages. An explicit module exports only the packages listed in the descriptor.

For example, a legacy JAR contains:

~~~text
com.acme.json.api
com.acme.json.internal
com.acme.json.spi
~~~

When it is an automatic module, all three packages are exported under automatic module semantics. Legacy consumers might accidentally import classes from **com.acme.json.internal**.

After transitioning to an explicit module:

~~~java
module com.acme.json {
    exports com.acme.json.api;
    exports com.acme.json.spi;
}
~~~

The **com.acme.json.internal** package is no longer an exported API. Consumers importing internal classes will fail to compile. This is an opportunity for the publisher to clearly define which packages are truly part of the public contract.

Before migrating, inventory which packages consumers have used. If a package was widely used, decide whether to preserve API compatibility, provide a deprecation period, or announce a breaking change in an appropriate release. Do not export internal packages merely to hide the fact that the API has not been defined.

## 8. Turning Broad Readability into Explicit requires

An automatic module reads other modules in the module configuration. An explicit module no longer has that broad reading privilege; it must declare appropriate dependencies.

Example new descriptor:

~~~java
module com.acme.legacy.client {
    requires java.logging;
    requires java.sql;

    exports com.acme.legacy.client.api;
}
~~~

If the implementation uses the **java.logging** or **java.sql** modules, those dependencies must be explicitly described. If the public API exposes types from a dependency, consider **requires transitive**. If the dependency is used solely by the implementation, **requires** is usually sufficient.

Dependencies downloaded by a build tool do not automatically replace **requires** directives. When running on the module path, the module graph must still be valid. Therefore, synchronize Maven/Gradle dependencies with the explicit descriptor.

## 9. Reflection and Service Loading During Migration

A legacy library may rely on broad reflection because it ran on the classpath. When moving to an explicit module, frameworks may no longer be able to access private fields or constructors unless the package has been opened.

Example:

~~~java
module com.acme.persistence {
    requires com.acme.domain;
    requires some.orm.framework;

    opens com.acme.domain.entity to some.orm.framework;
}
~~~

In an actual descriptor, **opens** must be declared in the module that owns the entity package, not the ORM module. For example, the domain module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to some.orm.framework;
}
~~~

If the library uses ServiceLoader, migrate legacy provider metadata to the appropriate JPMS declarations:

~~~java
module com.acme.codec {
    exports com.acme.codec.api;
    uses com.acme.codec.spi.Codec;
}
~~~

Provider module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec;

    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.internal.JsonCodec;
}
~~~

The provider's implementation package does not need to be exported just so ServiceLoader can discover the registered class. During migration, inspect both the legacy library's **META-INF/services** and the explicit module's **uses/provides** declarations so service discovery keeps working.

## 10. Automatic Modules Cannot Be Used Directly with jlink

Automatic modules are helpful for the module path, but are not suitable for inclusion in a linked runtime image with **jlink**. **jlink** requires input modules to be explicit modules with proper descriptors.

If an application needs to build a minimal runtime image, automatic dependencies must be upgraded or replaced with explicit module versions before linking.

You can check the application's module dependencies with:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.app
~~~

Once all needed dependencies are explicit modules, create the image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --output runtime
~~~

On Windows, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --output runtime
~~~

Test the runtime image on every target platform. An application running successfully with automatic modules on the module path does not prove it can be linked with jlink.

## 11. Transition Risks

| Risk | Symptom | Mitigation |
|---|---|---|
| Module name changes | Consumers cannot resolve dependency after upgrade. | Pin **Automatic-Module-Name** and keep the same name in the explicit descriptor. |
| Package no longer exported | Consumers fail to compile because they import a previously accessible package. | Inventory used APIs; export the right public packages and plan compatibility. |
| Missing requires | Compile or runtime reports unread module/package. | Analyze dependencies, declare requires, and test on the module path. |
| Framework loses reflection access | **InaccessibleObjectException** or **trySetAccessible()** fails. | Open the right package via **opens** or qualified **opens** for the framework. |
| ServiceLoader cannot find provider | Provider is not discovered after changing packaging. | Check **uses**, **provides**, provider registration, and service binding. |
| jlink fails | A dependency is still an automatic module. | Upgrade the dependency to an explicit module or choose another appropriate distribution approach. |
| Split package | Multiple modules contain the same package, causing resolution/linking errors. | Split packages, remove duplicate dependencies, or use artifacts with proper module boundaries. |

Migration should be rolled out library by library and tested with real consuming applications. Do not convert every dependency at once simply by adding auto-generated descriptors.

## 12. Pre-Release Checklist for an Explicit Module

- The module name is published stably and preserved from the automatic phase.
- The descriptor lists the exact direct dependencies.
- **requires transitive** is used only when the dependency is part of the public API.
- Only necessary API packages are exported; implementation packages stay hidden.
- Packages needing reflection by frameworks are opened with restrictions.
- Service consumers and providers are declared with appropriate **uses** and **provides**.
- No automatic dependencies remain if the release target requires **jlink**.
- No split packages exist in the module graph.
- The JAR contains **module-info.class** with the right name and resolves on the module path.
- Consumers compile and run with the new descriptor; frameworks and service discovery are also tested.

Automatic modules help legacy libraries join JPMS without modifying source code. Explicit modules complete the transition by accurately describing dependencies, APIs, and access rights. Keeping the module name stable, limiting exports, adding intentional opens, and testing real consumers will help a library transition to JPMS while preserving a clear integration contract.