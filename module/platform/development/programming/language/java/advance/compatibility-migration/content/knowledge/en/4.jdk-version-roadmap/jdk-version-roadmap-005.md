# Upgrading JDK 8 to 11: Modules, Runtime Structure, and Removed Components

Upgrading from JDK 8 to JDK 11 is a major transition because several foundational changes were introduced in Java 9 and further refined in Java 10 and 11. These changes affect how the JVM organizes the runtime, how applications access classes and packages, how frameworks use reflection, and the presence of APIs previously bundled inside JDK 8.

A typical Java 8 application can still run on JDK 11 if bytecode, APIs, dependencies, and runtime configuration are compatible. However, simply swapping `JAVA_HOME` and restarting the application is not enough. You must inventory components, identify reliance on the old JDK layout, handle split or removed modules, inspect reflective access permissions, and re-verify the entire build, test, and deployment pipeline.

## 1. Overview of Changes from JDK 8 to JDK 11

Java 9 introduced the Java Platform Module System (JPMS), restructured the runtime image, and began restricting access to certain internal APIs. Java 10 continued refining this foundation. Java 11 removed several Java EE/CORBA modules previously shipped with the JDK and also stopped bundling JavaFX in the standard JDK.

Areas of change to examine:

| Category | Key Change | Common Impact |
| --- | --- | --- |
| Module system | JPMS, module path, module descriptors, readability/exports rules | Frameworks or libraries using reflection may hit access errors; applications must distinguish classpath and module path. |
| Runtime image | Removal of `rt.jar`, `tools.jar`, `jre/lib/ext`, and several legacy boot/extension mechanisms | Build scripts, plugins, packaging tools, or apps locating classes via JDK 8 paths may break. |
| Java EE and CORBA | Several modules and tools separated from the JDK starting in Java 11 | Code calling JAXB, JAX-WS, Activation, CORBA, or JTA may fail to compile/run without adding dependencies or replacements. |
| JavaFX | No longer bundled in standard JDK 11 | JavaFX desktop apps must manage OpenJFX as a separate dependency/runtime. |
| Internal APIs and reflection | Internal access triggers warnings and module enforcement; access permissions may require explicit configuration | Warnings, `IllegalAccessError`, or `InaccessibleObjectException` may occur depending on access type and config. |
| Legacy tools and features | Several tools/features deprecated or altered | Replacement planning needed, even if not all are removed immediately in Java 11. |
| Runtime and security | Changes to TLS, logging, garbage collection, JFR, and platform defaults | Connectivity, monitoring, performance, and operational configuration must be tested. |

Crucially, not every Java 8 application needs full modularization. JDK 11 still supports running applications on the classpath. Even so, the application must adapt to the new runtime and eliminate assumptions tied to the JDK 8 directory layout.

## 2. Java Platform Module System (JPMS)

### 2.1. Why Does Java Have a Module System?

Prior to Java 9, the classpath was the primary mechanism for the JVM to locate classes and resources. On large classpaths, libraries could accidentally collide on packages, lack explicit dependency boundaries, and access too many internal details of one another. The classpath also could not express which module depended on which module or which packages were public APIs.

JPMS adds a module-level organizational layer. A module can declare:

- Module name.
- Modules it depends on via `requires`.
- Packages exposed to other modules via `exports`.
- Packages opened for reflection via `opens`.
- Services provided or consumed.

The goal is explicit dependencies and access control. The module system also enables building smaller runtime images containing only required modules.

### 2.2. Module Descriptor `module-info.java`

A named module usually contains a `module-info.java` file at the root of its source set. Example:

```java
module com.example.orders {
    requires java.sql;
    requires java.logging;

    exports com.example.orders.api;
}
```

In this example:

- `module com.example.orders` declares the module name.
- `requires java.sql` declares a dependency on the module providing JDBC and SQL APIs.
- `requires java.logging` declares a dependency on the platform logging API.
- `exports com.example.orders.api` allows other modules to access `public` types in this API package under module rules.

`exports` does not mean every other package in the module is public. An unexported package can still be used inside the module, while external modules cannot access it as a normal public API.

### 2.3. How Do `exports` and `opens` Differ?

These two directives address two distinct types of access:

| Directive | Purpose | Common Use Cases |
| --- | --- | --- |
| `exports` | Exposes `public` types in a package for standard Java access by other modules | A module providing services/APIs to other modules. |
| `opens` | Permits deep reflection into a package | ORM frameworks, dependency injection, or serializers needing to read/write non-public fields and constructors. |

Example of opening a package to a specific framework:

```java
module com.example.orders {
    requires java.sql;

    exports com.example.orders.api;
    opens com.example.orders.entity to org.hibernate.orm.core;
}
```

Open only the exact package and target module required. Using `opens ... to ...` narrows access compared to opening the entire module with `open module`.

### 2.4. `requires`, Readability, and Module Dependencies

`requires` declares that the current module needs to read the public API of another module. You may see:

```java
module com.example.reporting {
    requires com.example.orders;
    requires java.sql;
}
```

Module `com.example.reporting` can use types exported by `com.example.orders` and APIs exported by `java.sql`. If a required dependency relationship is missing, compilation or startup may fail because a module cannot read another module or a package is not exported.

Other directives such as `requires transitive`, `requires static`, `uses`, and `provides` serve advanced scenarios:

- `requires transitive`: passes readability of a dependency module onward to modules depending on the current module.
- `requires static`: a dependency needed at compile time that may be optional at runtime.
- `uses`: declares that the module consumes a service via `ServiceLoader`.
- `provides ... with ...`: declares an implementation provided for a service.

You do not need to add these directives solely to move a legacy classpath application to JDK 11. Use them only when the project is genuinely designed as named modules.

### 2.5. Classpath, Module Path, and the Unnamed Module

JDK 11 continues to support the classpath. When running a legacy application, you can use:

```bash
java -cp "lib/*;app.jar" com.example.Main
```

The example above uses `;` for Windows. On Linux/macOS, the classpath separator is typically `:`:

```bash
java -cp "lib/*:app.jar" com.example.Main
```

JARs placed on the classpath belong to the unnamed module. They do not require `module-info.java`, making this the lowest-friction path for Java 8 applications starting on JDK 11.

The module path is used to locate named modules or automatic modules:

```bash
java --module-path mods -m com.example.orders/com.example.orders.Main
```

For applications with module descriptors, the JVM resolves modules by name and dependency relationships. A JAR lacking `module-info.class` placed on the module path becomes an automatic module. Its automatic module name is taken from the `Automatic-Module-Name` manifest attribute or derived from the JAR filename.

Do not blindly move every JAR from the classpath to the module path. Before doing so, check module names, duplicate packages, split packages, dependency relationships, and framework reflection requirements. A library that runs smoothly on the classpath may not yet be designed to operate as a named module.

### 2.6. Split Packages and Automatic Modules

A split package occurs when the same package is contained in multiple modules. This can cause errors when JARs are placed on the module path because JPMS enforces clearer package boundaries.

For example, two libraries both contain classes in package `com.vendor.common`. On the classpath, resolution could depend on class search order. On the module path, module resolution may fail because the package is shared across multiple modules.

Common remediation steps:

- Upgrade the library to a version that fixed its packaging.
- Remove a duplicate dependency or adjust the dependency graph.
- Switch to a vendor-supported unified library artifact.
- Keep using the classpath for application parts not yet ready for modularization.

Automatic modules serve as a bridge when placing legacy libraries on the module path, yet do not guarantee the library has a stable modular design. If a library publishes `Automatic-Module-Name`, rely on that name rather than filename-derived names.

### 2.7. Is `module-info.java` Mandatory When Moving to JDK 11?

No. A standard Java 8 application can continue running on the classpath in JDK 11. JPMS is an important platform shift, but it does not require immediately converting every existing application into named modules.

Consider modularization when:

- The application has clear module boundaries and wants to declare public APIs.
- The system needs to build custom runtime images using `jlink`.
- There are plans to split modules or supply libraries to other modular consumers.
- Strict dependency and package access control is desired.

If the current goal is purely moving the application from JDK 8 to JDK 11, first keep the working packaging approach, resolve runtime and dependency changes, and schedule modularization as a separate initiative when concrete benefits warrant it.

## 3. Runtime Structure Changes Since JDK 8

### 3.1. Removal of `rt.jar` and `tools.jar`

In JDK 8, many platform classes resided in `rt.jar`, while development tools and APIs resided in `tools.jar`. Some scripts, older plugins, or internal tools looked up these files directly to configure classpaths or invoke the compiler.

Starting in Java 9, the runtime is organized into modules inside a runtime image. JDK 11 no longer has the JDK 8 layout with `rt.jar` and `tools.jar`. Consequently, assumptions like:

```text
$JAVA_HOME/jre/lib/rt.jar
$JAVA_HOME/lib/tools.jar
```

are no longer valid.

Search build scripts, plugins, shell scripts, Dockerfiles, and source code for code that:

- Appends `$JAVA_HOME/lib/tools.jar` to the classpath.
- Reads platform classes directly from `rt.jar`.
- Locates the compiler or JDK tools by assuming they live in a JAR file.
- Calls internal `com.sun.tools.*` APIs instead of public APIs.

If invoking the compiler from Java is required, prefer the Java Compiler API (`javax.tools`) or `ToolProvider` in an appropriate JDK environment. For regular builds, invoke Maven/Gradle wrappers or JDK executables in the tool-supported manner.

### 3.2. Modular Runtime Image

JDK 11 stores platform modules inside the runtime image. Modules can be listed with:

```bash
java --list-modules
```

Inspect a specific module description:

```bash
java --describe-module java.sql
```

Tools such as `jimage` assist in inspecting runtime image contents. Do not write scripts relying on internal paths of the runtime image when official commands or APIs exist to query modules.

### 3.3. Removal of Legacy Extension Mechanisms

JDK 8 included mechanisms such as the extension directory and endorsed standards override. Some applications placed JARs inside:

```text
$JAVA_HOME/jre/lib/ext
$JAVA_HOME/jre/lib/endorsed
```

These mechanisms are no longer supported in the modern runtime. Related system properties and flags such as `java.ext.dirs`, `java.endorsed.dirs`, and certain ways of interfering with the boot classpath have also been removed or no longer function as before.

If an application used the extension directory to load libraries, move dependencies to explicit management:

- Declare dependencies in Maven or Gradle.
- Package JARs in a `lib` directory and put them on the classpath/module path per deployment design.
- Configure application server class loaders according to server documentation.
- Use supported provider or service-loading mechanisms if the library implements a service.

Do not copy the JDK 8 `ext` directory directly into JDK 11 to try restoring old behavior. That does not replace valid classpath or module configuration.

### 3.4. JRE, JDK, and Custom Runtime Images

Java 9 changed how runtime images are packaged. Do not assume the JDK always contains a `jre` subdirectory following the legacy layout, or that every vendor distributes a standalone JRE in the same way.

JDK 11 may still be distributed in various forms depending on the vendor: full JDK, runtime package, or container image. Verify which product is supported in your production environment.

`jlink` allows building a custom runtime image containing only required modules:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.sql,java.logging \
  --output custom-runtime
```

This example illustrates creating a runtime image with the specified modules. On Windows, adjust line continuation characters and environment variables to match your shell. In real applications, include all required modules—even those used indirectly by frameworks, drivers, providers, or service loading.

`jlink` best suits applications/modules whose required module set can be clearly determined. If the application still runs on the classpath with many non-modular libraries, building a custom runtime image may require extra configuration or may not suit the initial phase.

## 4. Java EE and CORBA Modules Removed from JDK 11

### 4.1. Changes Under JEP 320

JDK 8 bundled several Java EE and CORBA APIs with the JDK. In Java 9, these modules were marked deprecated for removal; in Java 11, they were removed from the standard JDK.

Notable modules:

| Module Removed from JDK 11 | Common API/Package | Purpose |
| --- | --- | --- |
| `java.xml.bind` | `javax.xml.bind` (JAXB) | Maps XML to Java objects and vice versa. |
| `java.xml.ws` | `javax.xml.ws` (JAX-WS) | SOAP web services. |
| `java.xml.ws.annotation` | Several annotations used with web services | Annotations supporting web service description and processing. |
| `java.activation` | `javax.activation` | Data typing and activation content handling. |
| `java.corba` | `org.omg.*` | CORBA and Java IDL. |
| `java.transaction` | `javax.transaction` (JTA) | Transaction APIs for applications requiring JTA. |
| `java.se.ee` | Aggregator Java EE module | Aggregates the related Java EE modules. |

Removing these modules does not mean the entire `javax.*` namespace was removed from Java. Many `javax.*` packages remain part of Java SE or are provided by standalone libraries. Identify the exact packages and APIs your application uses.

In particular, `javax.transaction.xa` is not identical to the JTA API `javax.transaction`. XA APIs needed for JDBC are still provided via the `java.sql` module; do not add a JTA dependency simply because `javax.transaction.xa` appears in source code.

### 4.2. JAXB: Java Architecture for XML Binding

JAXB commonly appears in applications reading/writing XML, SOAP, or generating classes from XML schemas. On JDK 8, applications could use classes such as:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
```

On JDK 11, JAXB is no longer bundled in the JDK. If the application requires JAXB, declare compatible API and implementation dependencies in the project.

Example Maven dependencies on the JAXB 2.x line using the `javax` namespace:

```xml
<dependencies>
    <dependency>
        <groupId>javax.xml.bind</groupId>
        <artifactId>jaxb-api</artifactId>
        <version>${jaxb.version}</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>${jaxb.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

This is an illustrative sample; pick API and runtime versions compatible with each other, your active frameworks, and your project's support policy. If using a Maven plugin to generate classes from XSD, separately check the plugin version and how it resolves its JAXB implementation.

Do not automatically switch imports from `javax.xml.bind` to `jakarta.xml.bind` solely because you are upgrading to JDK 11. Migrating namespaces to `jakarta.*` belongs to the corresponding Jakarta EE roadmap and may require broader upgrades across frameworks, libraries, and source code.

### 4.3. JAX-WS and SOAP Web Services

Classes in `javax.xml.ws.*` and tools `wsimport` and `wsgen` were previously bundled in JDK 8. On JDK 11, if the application runs SOAP clients/servers or generates code from WSDL, add a standalone JAX-WS stack.

Items to verify:

- JAX-WS APIs imported by source code.
- Runtime implementation, such as Metro.
- Plugins or tools generating code from WSDL.
- JAXB and Activation dependencies that the SOAP stack may require.
- Configuration of handlers, providers, TLS, certificates, and serialization.

Do not merely add an API JAR and assume that suffices. The application needs an appropriate implementation to execute SOAP clients/servers at runtime.

### 4.4. Java Activation Framework

The Activation API is frequently used indirectly by JAXB, mail libraries, or MIME processing. If errors occur on `javax.activation.*` classes, determine which library requires this API and add the appropriate dependency.

Do not blindly add Activation if a dependency already pulls it in transitively. Check the dependency tree first to avoid conflicting API or implementation versions.

### 4.5. JTA and Transactions

An application using `javax.transaction.UserTransaction`, `TransactionManager`, or related annotations may have relied on JTA previously supplied by JDK 8. On JDK 11, declare the API and transaction manager suited to the deployment environment.

Distinguish these cases:

- JDBC local transactions using `java.sql.Connection` remain part of Java SE.
- XA transactions using types in `javax.transaction.xa` still retain platform APIs through `java.sql`.
- JTA using `javax.transaction` requires an API/implementation or an application-server-provided transaction manager.

Check how the application is deployed. If the application server provides the JTA API, follow the server's dependency scope guidelines to avoid bundling a conflicting API JAR.

### 4.6. CORBA and Java IDL

Packages under `org.omg.*` and related tools such as `idlj`, `orbd`, `servertool`, and `tnameserv` are no longer in standard JDK 11. If an application uses CORBA, determine:

- Whether CORBA is still genuinely invoked at runtime or only unused generated code remains.
- Which ORB implementation is used.
- Replacement stub/skeleton generation tools and build workflows.
- Protocol compatibility with external CORBA systems.

If no business feature still uses CORBA, remove unnecessary dependencies and dead code. If still required, select an external implementation supporting JDK 11 and test interoperability with existing systems.

### 4.7. Removed Java EE/CORBA Tools

Beyond runtime APIs, several JDK 8 tools are no longer provided in JDK 11, for example:

- `wsimport`, `wsgen`: JAX-WS tools.
- `xjc`, `schemagen`: JAXB/XML schema tools.
- `idlj`: CORBA IDL tool.
- `orbd`, `servertool`, `tnameserv`: CORBA tools.

Search for these commands in build scripts, CI pipelines, operational runbooks, and developer setups. Replace them with Maven/Gradle plugins or tools supplied by the corresponding implementation. Do not assume an old executable still exists merely because source code does not directly import the removed APIs.

## 5. JavaFX Separated from the JDK

JavaFX is no longer bundled in standard JDK 11. JavaFX desktop applications must manage OpenJFX as a separate dependency and runtime.

Check:

- `javafx.*` imports in source code.
- Build plugins and how the JavaFX SDK is fetched.
- Required JavaFX modules such as `javafx.controls`, `javafx.fxml`, and `javafx.graphics`.
- Platform-specific native libraries by OS/architecture.
- How the application is packaged and distributed to end users.

Example OpenJFX dependencies in Maven (version shown as a configuration property):

```xml
<properties>
    <javafx.version>...</javafx.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-controls</artifactId>
        <version>${javafx.version}</version>
    </dependency>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-fxml</artifactId>
        <version>${javafx.version}</version>
    </dependency>
</dependencies>
```

Choose an OpenJFX version compatible with JDK 11 and your packaging plugin. For natively distributed applications, verify platform classifiers and runtime packaging; pure Java dependencies do not guarantee native libraries are included in the image.

Note: JavaFX inclusion in JDK 8 varied by distribution. Some common JDK 8 builds bundled JavaFX, but JavaFX should not be assumed to exist in every Java 8 build.

## 6. Reflection and Internal API Access

### 6.1. Why Can Older Frameworks Fail?

Frameworks may use reflection to access non-public constructors, fields, or methods. Before JPMS, many applications relied on deep access into JDK or third-party classes without declaring which packages were open.

JPMS establishes access boundaries between modules. In JDK 11, the `--illegal-access` compatibility mechanism still permits certain illegal reflective accesses into JDK packages that existed in JDK 8 by default while emitting warnings. That mechanism does not guarantee every type of internal access works and should not be treated as a permanent solution.

Symptoms to investigate:

- `Illegal reflective access` warnings during startup or test runs.
- `IllegalAccessError` when accessing unexported types or members.
- `InaccessibleObjectException` when performing deep reflection into an unopened package.
- Startup failures in frameworks, ORMs, serializers, proxies, or dependency injection after switching JDKs.

### 6.2. `--add-exports` and `--add-opens`

These two options address different needs:

| Option | Used When | Example |
| --- | --- | --- |
| `--add-exports` | Accessing `public` types in another module's package not exported to the calling module | `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` |
| `--add-opens` | A framework needs deep reflection into another module's package | `--add-opens java.base/java.lang=ALL-UNNAMED` |

`ALL-UNNAMED` targets code in the unnamed module, typically libraries on the classpath. If the caller resides in a named module, specify that module's name rather than opening to all.

Example temporary JVM configuration:

```bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar application.jar
```

On Windows, adjust line continuations. Add packages only when stack traces or vendor documentation confirm they are needed. Do not copy a broad list of `--add-opens` flags from the Internet into every environment.

### 6.3. Sustainable Remediation

Priority order when resolving warnings or access errors:

1. Upgrade frameworks or libraries to versions supporting JDK 11.
2. Replace internal JDK APIs with public APIs.
3. Update module descriptors with scoped `opens` or `exports` if the application is a named module.
4. If a library cannot be upgraded immediately, add minimal `--add-opens` or `--add-exports` as a transitional workaround and document a removal plan.

Do not disable access checks or open entire modules just to get the application to boot. Overly broad access weakens encapsulation and can cause further issues when upgrading to newer JDKs.

## 7. Other Features and Tools to Watch

### 7.1. Nashorn JavaScript Engine

Nashorn was marked deprecated in Java 11. It remains present in JDK 11, but applications should not treat it as a long-term supported JavaScript engine in the JDK. If the system uses `ScriptEngineManager` to locate a JavaScript engine, identify which engine actually loads and plan a standalone replacement if needed.

Do not confuse deprecated status in Java 11 with already being removed in this version. Schedule replacement according to your future JDK roadmap and product scripting requirements.

### 7.2. Pack200

Pack200 and Unpack200 were marked deprecated in Java 11. If JAR distribution pipelines or update workflows use `pack200`/`unpack200`, seek alternatives and audit packaging tools. This feature was removed in subsequent JDKs, so do not build new workflows on it.

### 7.3. TLS 1.3 and Security Changes

JDK 11 adds a TLS 1.3 implementation. When upgrading the JDK, test connections to servers, proxies, databases, and external services, especially when the system fixes specific protocols/cipher suites or uses custom security providers.

Test:

- TLS handshakes against real endpoints.
- Truststores, keystores, certificate chains, and hostname verification.
- Cipher suites and protocols mutually supported by server and client.
- TLS-enabled JDBC, LDAP, SMTP, SOAP, or HTTP clients.

Never lower security standards merely to work around a connection failure. First identify the incompatible protocol/cipher and adjust per organizational security policy.

### 7.4. Unified JVM Logging and Java Flight Recorder

Java 9 introduced unified JVM logging, changing how many internal JVM logs are configured. Scripts using legacy logging flags must be updated to `-Xlog` syntax.

Java Flight Recorder (JFR) was contributed to OpenJDK and can observe JVM activity, performance, and runtime events. If the system has profiling or monitoring workflows, check compatibility with active agents and analysis tools.

### 7.5. Garbage Collector and Performance

G1 became the default garbage collector starting in Java 9. Java 8 applications might run Parallel GC or another configured collector. When moving to JDK 11, record the actual collector before and after migration, then measure:

- GC pause durations and frequency.
- Throughput, latency, and CPU.
- Heap occupancy, allocation rate, and memory pressure.
- Behavior under peak load and during application restarts.

Do not conclude performance is better or worse based solely on collector names. Run representative workloads and compare metrics under equivalent conditions.

## 8. Inventorying Traces of JDK 8 Dependencies

Before changing the JDK, search the repository and deployment environments for traces:

| Trace | Where to Look | Handling Approach |
| --- | --- | --- |
| `rt.jar`, `tools.jar` | Scripts, build plugins, classpaths, compiler-invoking code | Use supported tools/APIs; remove JDK 8 path assumptions. |
| `jre/lib/ext`, `java.ext.dirs` | Install scripts, environment variables, server configs | Declare dependencies and classpath/module path explicitly. |
| `java.endorsed.dirs` | JVM options, startup scripts | Upgrade libraries and use modern dependency/provider mechanisms. |
| `-Xbootclasspath/p` | Startup options, test runners | Remove boot classpath prepending; find supported extension APIs. |
| `javax.xml.bind`, `javax.xml.ws`, `javax.activation` | Imports, reflection, dependency tree, generated sources | Add standalone APIs/implementations or replace the stack. |
| `javax.transaction` | Imports, application server configs, dependencies | Identify JTA provider and dependency scope. |
| `org.omg.*`, `idlj`, `orbd` | Source, generated source, build scripts | Remove or choose an external CORBA implementation. |
| `javafx.*` | Source, build files, packaging | Add OpenJFX and appropriate runtime/native components. |
| `sun.*`, `com.sun.*` | Source, dependencies, and logs | Replace internal APIs with public APIs; upgrade libraries. |
| `setAccessible(true)` | Reflection code and framework integrations | Check module access, update frameworks, open packages narrowly. |
| `pack200`, `unpack200` | Release/package scripts | Replace compression/packaging workflows. |
| Nashorn/JavaScript engine | `ScriptEngineManager`, script resources | Evaluate standalone engines and replacement roadmap. |

Text search in the repository helps locate matches quickly. For example, with `rg`:

```bash
rg -n "rt\.jar|tools\.jar|java\.ext\.dirs|java\.endorsed\.dirs|Xbootclasspath|javax\.xml\.bind|javax\.xml\.ws|javax\.activation|javax\.transaction|org\.omg|javafx\.|pack200|unpack200" .
```

This is only a screening step. Generated code, transitive dependencies, externally loaded configs, and dynamically loaded class names may not appear in ordinary source searches.

## 9. Recommended Migration Process from JDK 8 to JDK 11

### Step 1: Capture the JDK 8 Baseline

Record:

- JDK distribution, version, and vendor.
- JVM options, GC, heap, system properties, and security configuration.
- Versions of Maven/Gradle wrappers, plugins, CI runners, and application servers.
- Current dependency tree and artifacts.
- Build logs, unit/integration tests, startup logs, and performance metrics.

Run builds/tests on the current JDK 8 environment for comparison. Record actual deployment methods, not just commands run on a developer's laptop.

### Step 2: Verify JDK 11 Tooling Support

Cross-check versions of Maven/Gradle, compiler plugins, test plugins, code generators, application servers, container base images, agents, and drivers against vendor documentation. Upgrade build tools to versions supporting JDK 11 first or on a dedicated change branch.

Distinguish the build JDK from the target release. A build can run on JDK 11 while emitting Java 8 bytecode during a transition period if the project must still support a Java 8 runtime. If the product goal is dropping Java 8, align the target release and supported minimum before editing configurations.

### Step 3: Inventory Separated APIs and Modules

Locate Java EE/CORBA packages, JavaFX, internal APIs, and JDK 8 layout assumptions. Inspect the dependency tree for libraries indirectly pulling in JAXB, JAX-WS, Activation, or JTA.

Classify each finding:

- Still used in production runtime.
- Used only at build time or for code generation.
- Used only in tests.
- No longer used and removable.
- Unclear; requires deeper tracing.

### Step 4: Update Affected Dependencies and Tools

Add APIs and implementations removed from the JDK to dependency management, or upgrade frameworks to versions that manage them automatically. Replace removed code-generation tools with supported plugins/tooling. Update JavaFX, CORBA, or scripting engines if actually required by the application.

Select versions compatible with one another and with JDK 11. Avoid adding duplicate implementations or packaging APIs already supplied by the application server.

### Step 5: Run on JDK 11 and Resolve Module/Reflection Errors

Switch the build/test environment to JDK 11, run a clean build, and log the first failure in each category:

- Missing removed classes/packages.
- Compiler or plugin incompatibility with JDK 11.
- Module access errors or illegal reflective access.
- Bytecode, class loading, or dependency conflicts.
- TLS, provider, native library, or runtime configuration errors.

Upgrade frameworks/libraries before adding access-opening flags. If `--add-opens` or `--add-exports` are required, record the package, target module, rationale, and removal plan.

### Step 6: Functional and Operational Testing

Run unit tests, integration tests, end-to-end tests, and critical business flows. Verify XML/SOAP, transaction, desktop UI, CORBA, or scripting capabilities if used by the system.

Test deployment on realistic containers/servers, including agents, TLS, logging, GC, monitoring, shutdown, and recovery. Compare performance against the JDK 8 baseline under equivalent conditions.

### Step 7: Standardize and Release

Once the application runs stably, standardize:

- Build JDK and compile release.
- Runtime image/container image.
- JVM options and security configuration.
- Dependency locks/version management.
- Development, testing, and deployment guides.
- Supported JDK matrix and rollback plan.

If Java 8 support must remain during a transition phase, maintain a separate build/test matrix. Do not claim Java 8 support merely because the artifact targets Java 8 bytecode; all dependencies and runtime profiles must also meet that requirement.

## 10. Tools to Assist JDK 11 Exploration

### 10.1. List Platform Modules

```bash
java --list-modules
```

This command confirms which modules exist in the running runtime. If a Java EE/CORBA module is absent, determine whether the application depends on it and supply external implementations if required.

### 10.2. Detect Internal API Dependencies

```bash
jdeps --recursive --jdk-internals path/to/application.jar
```

The output locates static references to JDK internal APIs. Also inspect dependency JARs and dynamically loaded classes; analyzing a single artifact does not cover the entire runtime.

### 10.3. Inspect a JAR's Module Info

```bash
jar --describe-module --file path/to/library.jar
```

This command reveals whether a JAR has a module descriptor, automatic module name, or other module metadata. If a library is not designed for the module path, keeping it on the classpath may be more appropriate.

### 10.4. Check Deprecated APIs

```bash
jdeprscan --release 11 path/to/application.jar
```

This command helps detect references to certain deprecated APIs inside an artifact. Review the output alongside migration docs and tests; not every warning means the application breaks immediately on JDK 11.

## 11. Completion Criteria for JDK 8 to 11 Migration

- [ ] Build tools, plugins, CI runners, and application servers support JDK 11.
- [ ] Assumptions around `rt.jar`, `tools.jar`, extension directories, and endorsed standards overrides have been removed.
- [ ] Decided whether the application continues on the classpath or follows a modularization plan; did not move to the module path mechanically.
- [ ] Handled JAXB, JAX-WS, Activation, JTA, or CORBA dependencies separated from the JDK if needed by the app.
- [ ] Separated JavaFX into its own dependency/runtime if the app uses JavaFX.
- [ ] Audited internal APIs and reflection warnings; any remaining `--add-opens`/`--add-exports` flags have documented rationale and narrow scope.
- [ ] Reviewed Nashorn, Pack200, TLS, logging, GC, and relevant operational tools.
- [ ] Clean build and required test suites pass on JDK 11.
- [ ] Business flows, external integrations, security, and deployment are verified in a production-like environment.
- [ ] Baseline comparisons, rollback plan, and supported JDK documentation are updated.

Completing these steps allows the JDK 8 to 11 migration to be evaluated with evidence. If the application does not yet require modularization, continuing on the classpath is a valid choice during transition. What must be ensured is that every API and tool previously supplied by JDK 8 has been identified, dependencies are explicitly managed, and the JDK 11 runtime is tested in the exact deployment configuration.
