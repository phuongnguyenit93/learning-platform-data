# Managing Module Versions and Compatibility

## 1. Module name, module version, and artifact version

In the Java Platform Module System (JPMS), a named module is identified by its module name, such as `com.acme.orders`. A module can carry version metadata, such as `1.4.2`, so build tools, operators, and distribution systems can identify the artifact version.

Three concepts should be distinguished:

- **Module name:** the identifier in `module-info.java`, used by `requires`, qualified `exports`/`opens`, `uses`, `provides`, and module resolution.
- **Module version:** version metadata that can be recorded in the compiled module descriptor.
- **Artifact version:** the version of a JAR/dependency in a build system such as Maven or Gradle.

For example, the Maven artifact `com.acme:orders:1.4.2` may contain the named module `com.acme.orders` with module version `1.4.2`. The module name should remain stable across releases; do not embed versions in the module name.

JPMS is not a dependency version resolver like Maven or Gradle. Module resolution primarily operates on module names and the dependency graph. Version metadata does not cause the JVM to pick the latest version, enforce semantic versioning, or resolve dependency conflicts. Selecting artifact versions is the responsibility of the build tool, package manager, or deployment system.

## 2. Recording version in the module descriptor

`module-info.java` source declares the module name and module relationships, but has no direct syntax for a version inside the module declaration. Versions are typically attached to the descriptor when packaging the modular JAR.

Example module:

~~~java
module com.acme.orders {
    requires com.acme.customer;
    exports com.acme.orders.api;
}
~~~

After compiling, package and attach the version:

~~~bash
jar --create \
    --file build/com.acme.orders.jar \
    --module-version 1.4.2 \
    -C build/classes/com.acme.orders .
~~~

The input directory must contain `module-info.class` along with the module's classes/resources. Adjust the `-C` path to match the project's output directory.

Inspect the descriptor:

~~~bash
jar --describe-module --file build/com.acme.orders.jar
~~~

The output may display the module name with its version:

~~~text
com.acme.orders@1.4.2
requires com.acme.customer
exports com.acme.orders.api
~~~

The version is stored in the module descriptor. It is useful for tooling, reporting, and artifact verification, but does not by itself decide which dependency is chosen when resolving the module graph at runtime.

### 2.1. Reading version with `ModuleDescriptor`

You can read the version using the `java.lang.module.ModuleDescriptor` API:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModuleVersion {
    public static void main(String[] args) {
        ModuleReference reference = ModuleFinder
                .of(Path.of("build"))
                .find("com.acme.orders")
                .orElseThrow();

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Module: " + descriptor.name());

        descriptor.version().ifPresentOrElse(
                version -> System.out.println("Version: " + version),
                () -> System.out.println("Version metadata is absent"));
    }
}
~~~

`ModuleDescriptor.version()` returns `Optional<ModuleDescriptor.Version>`. A module without version metadata is a valid scenario; code should not assume every descriptor has a version.

If the original version string is needed, use `rawVersion()`, which also returns `Optional<String>`. `version()` provides a parsed version object for comparison, whereas `rawVersion()` retrieves the exact string recorded in the descriptor.

### 2.2. Creating a descriptor with `Builder`

When constructing a descriptor in memory, the builder API can attach a version:

~~~java
import java.lang.module.ModuleDescriptor;

public class BuildModuleDescriptor {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleDescriptor
                .newModule("com.acme.tools")
                .version(ModuleDescriptor.Version.parse("2.1.0"))
                .exports("com.acme.tools.api")
                .build();

        System.out.println(descriptor.name());
        System.out.println(descriptor.version().orElseThrow());
    }
}
~~~

The created object is solely in-memory metadata. `build()` does not create a modular JAR, write `module-info.class`, or place the module on the module path. To publish an artifact, proper compilation and packaging are still required.

## 3. Module version is not a dependency version selection mechanism

Suppose an application module declares:

~~~java
module com.acme.app {
    requires com.acme.orders;
}
~~~

The `requires` line specifies the module name `com.acme.orders`. It cannot express constraints such as "version 1.4 or higher" or "only accept major version 1".

During a build, Gradle or Maven selects artifact versions based on dependency declarations, constraints, lockfiles, repository metadata, and the build tool's resolution rules. Then the compiler/runtime uses the module names in the descriptors to construct the module graph.

Gradle example:

~~~groovy
dependencies {
    implementation("com.acme:orders:1.4.2")
}
~~~

Maven example:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>orders</artifactId>
    <version>1.4.2</version>
</dependency>
~~~

The selected artifact must contain the module name required by the consumer. If the JAR declares a different module name, dependency declarations may resolve cleanly at the repository layer while the module graph still fails to resolve as expected.

Do not rely on the JAR filename `orders-1.4.2.jar` to infer the module name or descriptor version. Check `module-info.class` using `jar --describe-module`.

## 4. Keeping module names stable

The module name is part of the contract between modules. Consumers reference this name in `requires`; other modules may use it in qualified `exports`, `opens`, or service configurations.

Do not change a module name simply because the artifact version changes. Releases `1.4.2`, `1.5.0`, and `2.0.0` should still keep the module name `com.acme.orders` if they are releases of the same module and migrations are managed under the project's versioning policy.

Renaming a module can force every consumer to update `requires`, module paths, launchers, `jlink` configurations, service bindings, test configurations, and qualified export targets. If a rename is genuinely necessary, treat it as a user-impacting migration.

### 4.1. `Automatic-Module-Name`

A library without `module-info.class` can be used as an automatic module when placed on the module path. To keep the module name stable, the JAR can declare a manifest entry:

~~~text
Automatic-Module-Name: com.acme.legacy
~~~

Without this entry, the automatic module name may be derived from the JAR filename. Renaming the artifact or changing version suffixes can alter the derived name, affecting consumers' `requires`.

When preparing to modularize a library, provide a stable `Automatic-Module-Name` during the transition phase, then publish an explicit module descriptor when ready.

## 5. Compatibility has multiple layers

A new module version can preserve the same module name and still break consumers. Therefore, compatibility must be evaluated across multiple layers.

| Compatibility type | Question to answer | Example of impacting change |
|---|---|---|
| Source compatibility | Can consumer source still recompile? | Removing a public method, changing parameter types, or renaming a package. |
| Binary compatibility | Can precompiled consumer bytecode run against the new module? | Removing a method/field referenced by existing bytecode. |
| Module compatibility | Does the module graph resolve and do access rules remain valid? | Removing an export, renaming a module, or adding a mandatory dependency. |
| Behavioral compatibility | Does behavior still conform to the contract? | Changing exceptions, validation, or method semantics. |
| Service compatibility | Do consumer/provider SPIs remain compatible? | Changing a service interface or removing a provider declaration. |
| Operational compatibility | Can the runtime image and deployment environment still run? | Adding a required module missing from an older runtime image. |

A change might not break source compilation yet still break binary compatibility or behavior. Testing only the new module's build is insufficient; test consumers already compiled against the previous version.

## 6. Module descriptor changes that can break compatibility

### 6.1. Removing or narrowing `exports`

If an older version declared:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

but the new version removes the export:

~~~java
module com.acme.orders {
}
~~~

consumers are no longer permitted to access public types in that package across the module boundary. Source may fail to compile and precompiled bytecode may encounter access errors at runtime.

Changing from an unqualified export to a qualified export can also break consumers not listed in the target list.

### 6.2. Changing `requires`

Adding a new dependency:

~~~java
module com.acme.orders {
    requires com.acme.customer;
}
~~~

can prevent the module graph from resolving if `com.acme.customer` is missing from the module path/runtime image. New dependencies can also introduce package or module name conflicts with existing dependencies.

Distinguish the forms of `requires`:

- `requires M`: dependency required when resolving the module.
- `requires transitive M`: modules reading the current module can also read `M` via readability propagation.
- `requires static M`: dependency required at compile time that may be optional at runtime if the module is not pulled in by another runtime path.
- `requires static transitive M`: combines the meanings of `static` and `transitive`.

Changing `requires transitive` to `requires` can break consumers that relied on the propagated dependency to access another module's API.

### 6.3. Changing `opens`

Removing or narrowing `opens` can prevent frameworks from performing deep reflection into a package. The application may compile normally yet fail at runtime when an ORM, serializer, or dependency injection framework accesses private members.

Conversely, opening additional packages may not break functional compatibility, but increases the scope of reflection access. Treat this as a security/access contract change.

### 6.4. Changing `uses`/`provides`

If a consumer removes `uses` or a provider removes `provides`, service discovery may no longer locate the required implementation.

A change in the service interface can also render older providers unable to implement the new service, or newer consumers incompatible with older providers. Check both descriptors and `ServiceLoader` behavior.

## 7. Managing versions under a semantic policy

JPMS does not enforce a specific semantic versioning standard. A project may adopt SemVer or its own policy, provided it clearly defines how changes are categorized.

A common policy:

- **PATCH:** bug fixes that do not change the public contract and preserve compatible behavior under the policy.
- **MINOR:** additions of APIs or capabilities in a backward-compatible manner.
- **MAJOR:** changes that may break source, binary, module, or behavioral compatibility.

For example:

~~~text
1.4.2 -> 1.4.3   compatible bug fix
1.4.3 -> 1.5.0   add new API
1.5.0 -> 2.0.0   remove old API or change contract
~~~

This is a release convention of the project, not a rule enforced by the JVM. `ModuleDescriptor.Version` can parse and compare version metadata, but it does not enforce SemVer policy, verify API compatibility, or prevent a lower-version module from being placed on the module path.

Do not use version numbers as the sole proof that two modules are compatible. Combine release notes, API reviews, module descriptor comparisons, and consumer testing.

## 8. Analyzing module versions and compatibility with tools

### 8.1. Inspecting the module descriptor

For each artifact:

~~~bash
jar --describe-module --file libs/com.acme.orders-1.4.2.jar
~~~

Verify:

- Is the module name stable?
- Is version metadata recorded?
- Have `requires` changed?
- Have `exports`/qualified exports changed?
- Have `opens`, `uses`, and `provides` changed?
- Is an automatic module name derived differently than before?

Save the descriptor output for each release so reviewers can compare module contract changes.

### 8.2. Checking APIs and dependencies

Use `javap` to inspect public signatures of a class:

~~~bash
javap -classpath libs/com.acme.orders-1.4.2.jar \
  com.acme.orders.api.OrderService
~~~

Compare with the previous release to detect changed methods, constructors, fields, and data types. For the module path, use the appropriate `javap` options to specify the module.

Use `jdeps` to inspect the dependency/module graph:

~~~bash
jdeps --check com.acme.orders --module-path mods
~~~

`jdeps` helps detect dependencies, split packages, and several module-related issues. It does not prove behavioral compatibility and does not replace an API compatibility checker or test suite.

### 8.3. Checking internal JDK APIs

If a module relies on internal JDK APIs, run:

~~~bash
jdeps --jdk-internals libs/com.acme.orders-1.4.2.jar
~~~

The output highlights references at risk of changing or becoming more tightly encapsulated in newer JDKs. Prefer replacing them with public APIs rather than maintaining dependencies on implementation details.

## 9. Testing consumers before release

Compatibility is not solely a property of the provider module; it also depends on how consumers use the API and module descriptor.

A release pipeline should verify:

1. Build the new module from clean source.
2. Compare the new descriptor against the previous release's descriptor.
3. Compile representative consumers against the new artifact.
4. Run binary compatibility tests using bytecode compiled against the older version if the project supports drop-in upgrades.
5. Run integration tests covering service providers, reflection, and module layers.
6. Verify that `jlink`/runtime images include any new dependency modules.
7. Run tests on the baseline JDK and all supported JDKs.
8. Check dependency locking/verification to ensure consumers resolve the intended artifact.
9. Publish release notes detailing API, module graph, and runtime requirement changes.

If the module is a public library, maintain a suite of consumer compatibility tests or an automated compatibility checker. These tests should reflect actual module usage, including service registration and module access.

## 10. Safe migration strategy

When an API must be removed or a module descriptor changed, it can be executed across multiple releases:

**Phase 1 — Addition:** add the new API or new module without removing the old API. Update documentation and examples.

**Phase 2 — Deprecation:** mark the old API deprecated, provide migration guidance, and warn consumers. Do not narrow `exports` or `opens` while consumers still require them.

**Phase 3 — Consumer migration:** update applications, plugins, and dependent modules to the new API. Use dependency constraints/locks to pin tested versions clearly.

**Phase 4 — Breaking release:** remove old APIs or alter the module contract only in a major release according to policy. Update the module descriptor, module version metadata, and release notes.

**Phase 5 — Runtime verification:** rebuild runtime images, verify module lists and service binding, and test in the deployment environment. A new dependency can leave an older image missing required modules.

Never release a module with the same version metadata while making unrecorded descriptor/API changes. Versions and release notes must reflect actual changes so users can investigate and roll back if needed.

## 11. Module versions in runtime images and plugin systems

A runtime image built with `jlink` contains the set of modules selected by the linker. Version metadata in descriptors can be inspected by tooling, but the image does not automatically pick the latest module version at runtime.

For example:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --bind-services \
  --output build/runtime-image
~~~

If `com.acme.orders` is upgraded to a new version, rebuild the image from the new artifacts and test the module graph. Do not simply drop a JAR into a directory outside the image and assume the image is updated.

In plugin systems using `ModuleLayer`, plugins can be resolved in separate layers. Module version isolation must be designed carefully:

- Modules with the same name cannot be treated as two coexisting versions within a standard single module configuration.
- Separate layers can isolate different graphs/plugins, but class identity depends on the class loader/layer.
- Two interfaces with the same fully qualified name loaded by different class loaders are two distinct Java types.
- The service API should be shared from a common module/layer if the host and plugins need to exchange objects via that interface.

If two incompatible versions of a library must run simultaneously, separate layers/class loaders or distinct package/module identities may be necessary. This is an architectural decision that cannot be solved merely by placing two different JAR versions on the same module path.

## 12. Dependency locking and reproducible releases

To ensure consumers use the exact tested module versions, manage artifact versions in the build system.

With Gradle:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}

dependencies {
    implementation("com.acme:orders:1.4.2")
}
~~~

Generate/update lock state intentionally and commit lockfiles. Dependency verification can be used to verify checksums of downloaded artifacts.

With Maven, use explicit versions and `dependencyManagement`/BOMs to manage consistent versions across modules. Avoid version ranges or dynamic dependency versions in production artifacts unless controlled explicitly.

The same module name can be packaged across multiple artifact versions over different releases. The build tool must choose one specific artifact; module resolution then checks the module name and dependency graph. Record both artifact coordinates/versions and module name/version metadata to avoid confusion during investigations.

## 13. Common mistakes

| Symptom | Possible cause | Remedy |
|---|---|---|
| `requires com.acme.orders` fails to resolve | JAR lacks that module name or module is not on the module path | Run `jar --describe-module` and inspect the module path. |
| Version metadata is empty | Modular JAR was packaged without `--module-version` | Use `jar --module-version` when building artifacts if policy requires it. |
| Version metadata is present yet JVM picks an unexpected artifact | Confusing version metadata with dependency version resolution | Lock artifacts with Gradle/Maven and inspect the actual JAR in use. |
| Consumer fails to compile after module upgrade | API removed/changed or package no longer exported | Compare API and module descriptor; update consumer or publish migration. |
| Compiles cleanly but fails at runtime | Binary/module compatibility issue or runtime dependencies differ from compile path | Run integration tests with the exact runtime module path/image. |
| `ServiceLoader` cannot find provider | `uses`/`provides` or provider module changed | Check descriptors, service binding, and provider artifact. |
| Framework can no longer use reflection | Package `opens` was narrowed or removed | Review reflection contract; open the proper package/target if needed. |
| Plugin incompatible after version upgrade | Host and plugin use different API/module contracts | Run plugin compatibility tests and manage shared API versions. |
| Runtime image missing a new module | Image was not rebuilt or module set excludes the new dependency | Re-link with the right module path and verify with `--list-modules`. |

## 14. Module version management workflow

1. Keep module names stable and separate from artifact versions.
2. Choose a clear versioning policy, such as SemVer, and document it in the release process.
3. Embed version metadata in modular JARs via `jar --module-version` if tooling requires it.
4. Inspect artifact module descriptors using `jar --describe-module`.
5. Compare `requires`, `exports`, `opens`, `uses`, `provides`, and public APIs against the previous release.
6. Use Gradle/Maven to select concrete artifact versions, lock dependencies, and verify checksums.
7. Compile and test consumers with the new artifact, covering binary, service, and reflection scenarios.
8. Rebuild runtime images and test on the target JDK/OS/architecture.
9. Record artifact coordinates, module name/version metadata, JDK/toolchain, and hashes in release evidence.
10. Publish breaking changes, migration notes, and rollback paths whenever the module contract changes.

Module versions describe artifacts, whereas compatibility is determined by APIs, module descriptors, dependency graphs, and actual runtime behavior. Managing both layers well keeps module upgrades predictable, testable, and reversible.
