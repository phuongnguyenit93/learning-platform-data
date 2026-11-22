# Stable Module Names and `Automatic-Module-Name`

When migrating a Java application from the classpath to the Java Platform Module System (JPMS), a JAR library is not identified solely by its filename or Maven/Gradle coordinates. On the **module path**, each module has a **module name** used in `requires`, command-line options such as `--add-reads`, `--add-opens`, `--add-exports`, as well as when analysis and launch tools build the module graph.

The module name is an important part of the integration contract. If a JAR is identified today as `billing.client`, but the next version changes to `billing.sdk` simply because the publisher renamed the artifact, applications declaring `requires billing.client;` may fail to compile or launch. **`Automatic-Module-Name`** is a JAR manifest attribute that allows developers to set a stable module name in advance when the JAR does not yet have `module-info.class`.

This lesson focuses on how module names are chosen, how to publish the name via the manifest, how to configure it when releasing a library, and what needs to be done to maintain compatibility when upgrading the JDK, renaming artifacts, or transitioning to an explicit module.

## 1. Why Is a Module Name a Compatibility Contract?

A JPMS application can declare a dependency on a library as follows:

```java
module com.example.checkout {
    requires com.example.billing.client;
}
```

Here, `com.example.billing.client` is the **module name**. It is not necessarily the package name, JAR name, Maven `artifactId`, or class name.

Suppose an application is working with the artifact:

```text
billing-client-1.4.0.jar
```

A migration renames the file to:

```text
billing-sdk-2.0.0.jar
```

If the module name is derived automatically from the filename, the module name can change with the artifact. However, if both JARs publish the same `Automatic-Module-Name: com.example.billing.client`, the application continues to declare the same `requires`.

Stability is valuable across multiple layers:

- **Source compatibility:** the consumer's `module-info.java` continues to reference the right module name upon recompilation.
- **Build compatibility:** Maven/Gradle and JPMS tools do not have to update every `requires` just because the release filename changed.
- **Deployment compatibility:** scripts using `--module-path` or specifying the module with `-m`/`--module` have a consistent name.
- **Tooling compatibility:** `jlink`, `jdeps`, and `jpackage` configurations, module graph checks, and module layers can reuse the module identifier.
- **Migration compatibility:** when a library transitions from an automatic module to an explicit module, consumers can continue using the previously published name.

A stable name does not by itself guarantee that APIs, bytecode, or behavior remain unchanged. It helps prevent **one kind of breaking change caused by changing the module identifier**.

## 2. Three Ways a JAR Participates in the Module System

Before choosing a name, you need to know which mode the JAR is being used in.

| Case | How the Module Is Determined | Effect of `Automatic-Module-Name` |
|---|---|---|
| Explicit named module | Has a `module-info.class` recognized by JPMS | The name from the descriptor is the primary source; the header does not replace the descriptor |
| Automatic named module | Regular JAR without a module descriptor, placed on the module path | The header, if present and valid, provides a stable module name |
| Unnamed module | JAR or classes loaded from the classpath | The header does not turn the JAR into a named module; code stays in the unnamed module |

### 2.1. Explicit Module

A library can declare its name using `module-info.java`:

```java
module com.example.billing.client {
    exports com.example.billing.api;
}
```

After compilation, `module-info.class` resides inside the modular artifact. The name `com.example.billing.client` comes from the module descriptor. This is the most official and complete declaration method, because the descriptor also specifies `requires`, `exports`, `opens`, `uses`, and `provides` relationships.

### 2.2. Automatic Module

A traditional JAR without a module descriptor can still be placed on the module path. JPMS can treat it as an **automatic module** and assign a name according to the manifest or, if the manifest does not specify one, derive the name from the filename.

Example:

```text
lib/
  billing-client-1.4.0.jar
```

When a JAR has no descriptor and sits on the module path, `Automatic-Module-Name` can stabilize its identifier for consumers:

```text
Automatic-Module-Name: com.example.billing.client
```

An automatic module has relaxed package exporting/reading rules to support migrating from classpath libraries. It is a useful transitional step, **not equivalent to having finished designing a modular API**.

### 2.3. Unnamed Module

If the same JAR is still placed on the classpath:

```bash
java -cp "lib/*:app.jar" com.example.app.Main
```

then the `Automatic-Module-Name` attribute does not automatically make it a named module. It continues to belong to the unnamed module corresponding to that class loader.

You need to distinguish between placing the JAR on the **classpath** versus the **module path**. Simply adding a manifest entry without changing how the application is launched does not change the existing application's class loading model.

## 3. Module Names Derived Automatically from Filenames: Convenient but Prone to Change

If a JAR has neither `module-info.class` nor `Automatic-Module-Name`, the system can derive an automatic module name from the JAR filename.

The derivation rules include steps such as stripping the `.jar` extension, removing the matching version suffix, converting certain separator characters into dots, and normalizing the string into a module name. The actual result must be verified using tools from the exact target JDK, because complex or invalid filenames can cause module recognition errors.

Illustrative examples:

| Filename | Typically Derived Name |
|---|---|
| `billing-client-1.4.0.jar` | `billing.client` |
| `commons-lang3-3.12.0.jar` | `commons.lang3` |
| `reporting_api-2.1.jar` | `reporting.api` |
| `example-core-2.0.0.jar` | `example.core` |

If a later version changes `billing-client-1.4.0.jar` to `billing-sdk-2.0.0.jar`, the derived name will shift from `billing.client` to `billing.sdk`, even though the packages inside have not changed.

There are other risks:

- Auto-derived names do not necessarily have a sufficiently distinct namespace, so two libraries can collide on the same name.
- Changing filename conventions or classifiers can change the module name.
- Artifacts with unusual characters or version formats can produce unpredictable names.
- A filename-based module name does not necessarily match the name the publisher intends to use when creating the official `module-info.java`.
- Consumers may inadvertently depend on the derived name and then have to make widespread edits when the library changes how it is released.

Therefore, **a filename-derived name should not be treated as a stable API if the publisher has not committed to it**.

## 4. Declaring `Automatic-Module-Name` in the Manifest

A JAR has a standard manifest file at `META-INF/MANIFEST.MF`. For libraries without a module descriptor, you can add the header:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.billing.client

```

Key points to understand accurately:

1. The attribute is a manifest header, not a Java annotation or an attribute inside `module-info.java`.
2. The value is the full module name; it does not include a version or `.jar` filename.
3. The header is meaningful when the JAR is an automatic module on the module path.
4. The header does not define individual `requires`, `exports`, or `opens`; the automatic module retains its transitional characteristics.
5. Once a JAR has a module descriptor used by JPMS, the name in the descriptor determines the explicit module name.
6. You must inspect the **final released JAR** because shading, repackaging, or creating an executable JAR can alter the manifest.

The name `com.example.billing.client` should be a name intended for long-term use, not a temporary name just to bypass a compiler error.

### 4.1. Module Names Are Not Versions

You should not declare:

```text
Automatic-Module-Name: com.example.billing.client.v2
```

just because the artifact bumps from 1.x to 2.x. Artifact versions should be managed via Maven/Gradle coordinates, release metadata, and a separate versioning policy.

The same module name can be used across multiple versions:

```text
billing-client-1.4.0.jar  -> com.example.billing.client
billing-client-1.5.0.jar  -> com.example.billing.client
billing-sdk-2.0.0.jar     -> com.example.billing.client
```

That does not mean multiple versions with the same name can be placed simultaneously on a single module path: module resolution must determine a consistent module definition. If two JARs share the same module name within the same search scope, JPMS may reject them due to duplicate identifiers.

## 5. Stable Module Naming Conventions

For public libraries or libraries used by multiple teams, the module name should be managed as part of the public API.

### 5.1. Use a Distinct Namespace

An easy-to-manage convention is reverse-domain naming:

```text
com.example.billing.client
com.example.billing.api
com.example.platform.logging
org.example.analytics.core
```

Choose name components that are valid under Java's module name rules. Avoid hyphens, spaces, overly short collision-prone names, keywords, or invalid structures.

The module name can resemble the primary package, though it does not need to match a package name identically. A module typically contains multiple packages and only one module name.

### 5.2. Independent of Artifact and Repository Names

For example, the following three pieces of information serve three different purposes:

| Identifier Type | Example | Where It Is Used |
|---|---|---|
| Maven group/artifact | `com.example.billing:billing-client` | Resolving dependencies in Maven/Gradle |
| Filename | `billing-client-1.4.0.jar` | Distribution, storage, module path |
| JPMS module name | `com.example.billing.client` | `requires`, module graph, launcher, and tooling |

Changing repositories, transferring owning teams, or renaming artifacts does not require changing the JPMS name.

### 5.3. Defining Name Ownership

A shared library should maintain a record of:

- Official module name.
- Artifact and release repository.
- Owner or maintaining team.
- First version containing the `Automatic-Module-Name` header.
- Status: automatic module or explicit module.
- Direction when transitioning to `module-info.java`.
- Previous names that were published or derived and the consumer support plan.

This convention is especially necessary in multi-module, multi-repository systems or when libraries are published outside the organization.

### 5.4. Avoiding Module Name Collisions

JPMS identifies modules by name within a module layer. Two different artifacts should not publish the same module name. If both are placed on the module path, resolution may fail; if only one is selected depending on the environment, runtime results may also become inconsistent.

Do not use `java.*` names or names easily confused with platform modules. Choose a namespace genuinely owned by the library.

## 6. Configuring Maven to Release a JAR with a Fixed Module Name

With Maven, you can configure the Maven JAR Plugin to add a manifest entry to the library's JAR:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifestEntries>
                        <Automatic-Module-Name>com.example.billing.client</Automatic-Module-Name>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Then package:

```bash
mvn clean package
```

Inspect the generated artifact:

```bash
jar --describe-module --file target/billing-client-1.4.0.jar
```

The `jar --describe-module` command from a JPMS-capable JDK indicates whether the JAR has an explicit descriptor or is an automatic module, along with the recognized module name.

If the project uses a parent POM, `pluginManagement`, or multiple profiles, ensure the configuration is applied to the proper packaging goal and released artifact.

### 6.1. Maven Shade Plugin and the Final Manifest

When using `maven-shade-plugin` to build an uber JAR, the final artifact may use a different manifest than the JAR generated by `maven-jar-plugin`. You need to set or preserve `Automatic-Module-Name` in the **actual shaded artifact**.

For example, you can declare `ManifestResourceTransformer`:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <manifestEntries>
            <Automatic-Module-Name>com.example.billing.client</Automatic-Module-Name>
        </manifestEntries>
    </transformer>
</transformers>
```

This is a fragment inside a `maven-shade-plugin` configuration, not a complete POM. With a shaded JAR, you must also evaluate package relocation, duplicate packages, service provider resources, and descriptors that may come from dependencies; merely editing the manifest does not automatically solve those issues.

### 6.2. Avoid Introducing Duplicate Manifest Headers

If multiple plugins modify the manifest, inspect the final output instead of checking only the POM. A header existing in configuration does not prove it appeared properly in the released JAR.

For a library, there should be a single clear configuration source for the module name and a repeatable packaging process.

## 7. Configuring Gradle

With the Gradle Groovy DSL, you can add the attribute to the `jar` task:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.example.billing.client'
        )
    }
}
```

For a multi-project build, each library needs its own name. Do not set the same fixed name for every subproject if each subproject publishes a separate JAR.

Example in the `:billing-client` module:

```groovy
project(':billing-client') {
    tasks.named('jar', Jar) {
        manifest {
            attributes(
                'Automatic-Module-Name': 'com.example.billing.client'
            )
        }
    }
}
```

With the Gradle Kotlin DSL:

```kotlin
tasks.named<Jar>("jar") {
    manifest {
        attributes["Automatic-Module-Name"] = "com.example.billing.client"
    }
}
```

You can build the JAR with:

```bash
./gradlew :billing-client:jar
```

Then run `jar --describe-module --file` on the actual artifact path inside `build/libs`.

If the module uses the Shadow plugin, Spring Boot `bootJar`, or another packaging plugin, they may produce a different JAR from the `jar` task. Identify which artifact is the actual JPMS library being released, then inspect that artifact's manifest.

## 8. Example of a Consumer Using a Stable Automatic Module

Suppose the library `billing-client-1.4.0.jar` contains:

```text
META-INF/MANIFEST.MF
com/example/billing/api/BillingClient.class
com/example/billing/model/Invoice.class
```

Manifest:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.billing.client

```

The consumer application is an explicit module:

```java
module com.example.checkout {
    requires com.example.billing.client;
}
```

Application code:

```java
package com.example.checkout;

import com.example.billing.api.BillingClient;

public class Main {
    public static void main(String[] args) {
        BillingClient client = new BillingClient();
        System.out.println(client);
    }
}
```

To compile the modular application, the JAR must be on the module path and required dependencies must also be resolved:

```bash
javac --module-path lib \
  -d out \
  src/com.example.checkout/module-info.java \
  src/com.example.checkout/com/example/checkout/Main.java
```

The example command above assumes the module source has the path layout shown, and that `lib` contains the JAR with the right module name. If `BillingClient` has a different constructor or API, replace the illustrative code with the actual library API.

Running the modular consumer:

```bash
java --module-path "lib:out" \
  --module com.example.checkout/com.example.checkout.Main
```

On Windows, the separator between path entries is typically a semicolon instead of a colon. Use syntax appropriate for your shell and operating system.

If the library changes its filename in the next version while keeping `Automatic-Module-Name`, the consumer's `requires com.example.billing.client;` line stays unchanged.

## 9. Characteristics of Automatic Modules: Convenience and Limitations

An automatic module is a bridge between traditional JARs and the explicit module system.

In the automatic module model, JPMS allows many permissive behaviors to support libraries that have not yet been modularized:

- Packages in an automatic module are exported and opened under the automatic module mechanism.
- Automatic modules have broad readability relationships with other modules, aiming to reduce migration barriers for legacy libraries.
- It does not declare precisely which public APIs need `exports` or which packages need `opens` for reflection.
- It does not express required dependencies with `requires` the way an explicit descriptor does.
- The JAR can still contain classes, resources, and legacy classpath mechanisms without clear module boundaries designed yet.

This makes `Automatic-Module-Name` very useful for **stabilizing identifiers**, but it does not turn a library into a fully modular library.

### 9.1. Do Not Confuse Automatic Modules with Strictly Encapsulated Named Modules

An explicit module can export only API packages:

```java
module com.example.billing.client {
    exports com.example.billing.api;
}
```

Implementation packages such as `com.example.billing.internal` can be encapsulated, depending on `opens` configuration and other accessibility settings.

Meanwhile, an automatic module cannot selectively declare `exports`/`opens` in that manner. Therefore, consumers accessing internal packages while the JAR is still an automatic module may break when the library transitions to an explicit module.

### 9.2. Classpath Dependency Issues

Automatic modules are designed to support migration and have broad readability, including interacting with code still on the classpath according to JPMS rules. However, **an explicit named module cannot simply `requires` a library that resides only on the classpath**, because the classpath produces an unnamed module with no name for `requires`.

When a project moves from the classpath to the module path, you must accurately categorize which dependencies already have an explicit descriptor, which are automatic modules, and which remain in the unnamed module.

### 9.3. A Stable Name Does Not Fix Split Packages

JPMS enforces restrictive rules when multiple named modules contain the same package. For example:

```text
billing-api.jar      -> com.example.billing.api.Account
billing-impl.jar     -> com.example.billing.api.InternalHelper
```

If two JARs are treated as two named modules and share the package `com.example.billing.api`, the module graph or compiler may report a split package conflict.

Adding `Automatic-Module-Name` to both artifacts does not solve the issue. You need to reorganize packages, merge appropriate components, or adjust how they are packaged.

## 10. From Automatic Module to Explicit Module

A common roadmap for a library wanting to maintain legacy Java support while starting to support JPMS:

1. Keep the traditional JAR and add `Automatic-Module-Name` to publish a stable name.
2. Release it and let consumers begin using this name in `module-info.java`.
3. Review public APIs, dependencies, reflection, service providers, and package boundaries.
4. Create `module-info.java` with the **exact same name previously published**.
5. Test consumers using both the module path and the classpath.
6. Release the explicit module according to the library's versioning policy.

Example manifest in the initial version:

```text
Automatic-Module-Name: com.example.billing.client
```

After modularizing:

```java
module com.example.billing.client {
    requires java.net.http;

    exports com.example.billing.api;
    exports com.example.billing.model;
}
```

The key point is that the name in the descriptor stays `com.example.billing.client`. If changed to `com.example.billing.sdk`, consumers with `requires com.example.billing.client;` will have to update even when public classes have not changed.

### 10.1. New Issues When Transitioning to an Explicit Module

Previously, an automatic module could expose many packages. Once a descriptor is added, access becomes selective:

- Consumers importing non-exported packages may no longer compile.
- Frameworks using deep reflection into unopened packages may throw `InaccessibleObjectException`.
- Dependencies that were previously read automatically may need to be declared with `requires` or `requires transitive`.
- Service provider discovery may require `uses`/`provides` or appropriate metadata.
- Resource and native library loading must be checked on the module path.
- Duplicate package names across modules may be detected more explicitly.

Therefore, **keeping the module name stable is a helpful condition, but not sufficient to guarantee that migrating to an explicit module will not break compatibility**.

### 10.2. Multi-Release JAR for Libraries Supporting Both Java 8 and JPMS

A library that wants to continue releasing Java 8 bytecode while providing a descriptor starting from Java 9 can use a multi-release JAR, for example:

```text
META-INF/MANIFEST.MF
com/example/billing/api/BillingClient.class
META-INF/versions/9/module-info.class
```

The manifest must declare multi-release properly:

```text
Manifest-Version: 1.0
Multi-Release: true
Automatic-Module-Name: com.example.billing.client

```

On a JVM supporting multi-release/module descriptors, the JAR can be recognized as an explicit module according to the selected descriptor. On older JVMs that do not support JPMS, regular Java 8 classes can still be loaded via the classpath, provided the artifact and other dependencies are truly compatible.

This is an advanced packaging technique: you need to check multi-release rules, the manifest, compiler options, and actual plugin output. You should not manually insert `module-info.class` into an arbitrary location and assume the JDK will recognize it properly.

## 11. Common Errors When Module Names Are Unstable

### 11.1. `module not found`

A consumer has:

```java
requires com.example.billing.client;
```

but the module path only contains a JAR recognized as `billing.sdk`. The compiler or launcher may report that module `com.example.billing.client` cannot be found.

Check the module name that the JDK actually reads from the JAR and the entries on the module path.

### 11.2. Duplicate Names Between Two JARs

Two different JARs both declare:

```text
Automatic-Module-Name: com.example.shared
```

If both are on the module path, the system may report a duplicate module during module lookup and resolution.

Resolve ownership/name collisions; do not use classpath ordering to mask the problem because the module path follows different identification rules.

### 11.3. Name in the Manifest Differs from `module-info.java`

During an upgrade, the development team adds a descriptor:

```java
module com.example.billing.sdk { }
```

whereas earlier versions published:

```text
Automatic-Module-Name: com.example.billing.client
```

At this point, consumers must change `requires` when switching versions. The name in the explicit descriptor should be kept consistent with the previously published stable name.

### 11.4. Header Does Not Appear in the Final JAR

The build script may declare the manifest entry, but the deployed JAR is produced by a different task or plugin. As a result, `jar --describe-module` on the released JAR shows a filename-derived name instead.

Inspect the final artifact after all shade, repackage, sign, or copy steps; do not inspect only the source configuration.

### 11.5. Header Contains an Invalid Name

A name such as `billing-client` contains a hyphen and is not valid for a Java module name. Choose a name with valid identifier components, such as `com.example.billing.client`, and confirm with JDK tools.

### 11.6. Stable Name Set, Yet the Library Still Cannot Be Modularized

If a JAR contains split packages, depends on encapsulated internal APIs, has incorrect service provider metadata, or relies too heavily on reflection, adding a manifest entry will not solve those issues.

Separate **module identification** errors from **module graph, encapsulation, or runtime behavior** errors so you fix the root cause properly.

## 12. Inspecting Module Names in Released Artifacts

### 12.1. Viewing the Name Recognized by the JDK

Use the `jar` tool from a JPMS-capable JDK:

```bash
jar --describe-module --file build/libs/billing-client-1.4.0.jar
```

The output helps identify whether it is an automatic module or an explicit module, along with the module name the JDK uses.

With Maven:

```bash
jar --describe-module --file target/billing-client-1.4.0.jar
```

The path must match the final released artifact. If the file is an executable JAR with nested dependencies, do not assume that structure is equivalent to a standard set of modules on the module path.

### 12.2. Viewing the Module Graph

When there are multiple dependencies on the module path:

```bash
java --module-path libs --list-modules
```

The command shows the modules visible to the launcher in the current configuration. For a modular application with an entrypoint, you can run it directly to verify actual resolution.

### 12.3. Checking Module Path Conflicts

You can use:

```bash
java --module-path libs --validate-modules
```

This option helps detect certain module path and resolution issues before running the application. Run it with the set of artifacts matching the deployment environment, not just a few isolated JARs.

### 12.4. Dependency Analysis

`jdeps` helps observe dependencies at the bytecode/module level:

```bash
jdeps --module-path libs --print-module-deps app.jar
```

Static analysis does not see every dependency created via reflection, configuration, or code generation. Combine it with compile/run tests and inspecting each artifact's module descriptor.

### 12.5. Storing Evidence in CI

A library release pipeline can store:

- Artifact name and checksum.
- Module name recognized by the `jar --describe-module` tool.
- JDK vendor/release used for verification.
- `Automatic-Module-Name` or module descriptor version.
- List of artifacts on the module path when running integration tests.
- Consumer compile and smoke test results.

If the module name changes unexpectedly between two versions, CI can detect it before the official release.

## 13. Migration Strategy for Multi-Library Systems

For a product with many modules and internal dependencies, transitioning to JPMS should have a simple **module name registry**:

| Artifact | Committed JPMS Name | Status | Typical Consumers |
|---|---|---|---|
| `billing-client` | `com.example.billing.client` | Automatic | Checkout Service |
| `shared-contracts` | `com.example.shared.contracts` | Automatic | Billing, Checkout |
| `inventory-core` | `com.example.inventory.core` | Explicit | Inventory API |
| `reporting-sdk` | `com.example.reporting.sdk` | Automatic | Reporting Job |

These values are illustrative examples and do not describe a real project.

The process can be rolled out in phases:

**Phase 1 — Inventory.** Identify JARs on the classpath/module path, resolved versions, current module names, and dependencies. Use `jar --describe-module` to obtain actual results.

**Phase 2 — Choose Official Names.** Prioritize clear namespaces that change rarely, contain no versions, and do not collide with other modules. Publish them together with the artifact-owning teams.

**Phase 3 — Release Stable Automatic Modules.** Add `Automatic-Module-Name` to each traditional JAR planned to support JPMS. Inspect the final artifact after packaging.

**Phase 4 — Move Consumers to the Module Path.** Add `requires` using the stable names; resolve unmodularized dependencies, split packages, and classpath/module path issues.

**Phase 5 — Modularize Each Library.** Add `module-info.java` with the same committed name. Declare `requires`, `exports`, `opens`, and services intentionally.

**Phase 6 — Cross-Testing.** Rebuild consumers, run existing binaries when binary compatibility must be preserved, verify reflection/service providers, and run smoke tests on the target runtime.

Not every library needs to become an explicit module in a single release. Automatic modules with stable names allow each team to migrate on its own schedule, provided the limitations of the transitional model are clearly understood.

## 14. Checklist Before Publishing a Module Name

- [ ] Identified the final released artifact and actual module path.
- [ ] Chosen JPMS name has a clear and valid namespace.
- [ ] Name is not tied to a version, filename, classifier, or repository name that may change.
- [ ] No two artifacts within the same scope share the same module name.
- [ ] JARs without a descriptor have `Automatic-Module-Name` properly set in the manifest.
- [ ] Maven/Gradle shade, repackage, or custom packaging does not strip the header.
- [ ] `jar --describe-module --file` confirms the right name in the final artifact.
- [ ] Consumers use `requires` with the published name.
- [ ] Reviewed split packages and dependencies on the classpath/module path.
- [ ] If the library transitions to an explicit module, the name in `module-info.java` remains unchanged.
- [ ] Checked `exports`/`opens` permissions, service loading, and reflection during modularization.
- [ ] CI records the module name and detects unexpected changes.
- [ ] Migration guidance exists if an earlier version previously published a different name.

## 15. Conclusion

The module name is the identifier that JPMS consumers use to establish dependencies and launch on the module path. If the name is left to be derived from the filename, changing the artifact or packaging convention can inadvertently become a breaking change. `Automatic-Module-Name` allows traditional JAR libraries to publish a stable module name even before having `module-info.class`.

A sustainable approach is to choose a name under a clear namespace, publish it in the manifest of the final artifact, verify it using JDK tools, and keep that same name when transitioning to an explicit module. After naming, continue addressing the module graph, encapsulation, reflection, service providers, and consumer testing to ensure a successful Java Compatibility Migration.
