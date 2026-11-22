# Inventorying Current Packages and Dependencies

Before migrating a Java application from the classpath to the Java Platform Module System (JPMS), the most important step is not immediately writing `module-info.java`, but **knowing exactly which packages, artifacts, and dependencies the application currently has**. Without this inventory step, migration easily runs into split packages, libraries incompatible with the module path, dependencies that only surface at runtime, or access to JDK internal APIs.

This lesson guides you through creating a **baseline inventory** for the current application: a list of packages, package ownership, direct/transitive dependencies, expected module names, usage scopes, dynamic dependencies, and risks to address. Only after completing the inventory will the development team have enough data to decide module boundaries and migration order.

## 1. Goals of the Inventory Step

The results should answer the following questions:

1. Which Java packages does the application currently contain?
2. Which source set, logical module, JAR, or dependency does each package belong to?
3. Which JARs are on the compile classpath, runtime classpath, and test classpath?
4. Which artifacts are modular JARs, automatic modules, or classpath-only libraries?
5. Which library packages/classes does the application code depend on?
6. Are there packages with the same name located in multiple artifacts?
7. Are there dependencies on JDK internal packages, such as `sun.*` or `jdk.internal.*`?
8. Is there reflection, `ServiceLoader`, JNI, serialization, or dynamic class loading?
9. Which dependencies belong to the public API, and which are used only in the implementation?
10. If split into modules, what are the expected package/module boundaries and `requires` relationships?

Do not treat the inventory as merely a list of `.jar` files. A single JAR can contain many packages, a single package can be split across multiple JARs, and a dependency can appear only via runtime configuration, service providers, or reflection.

## 2. Defining Project Scope and Java Version

First, record background information:

- Application or repository name, and the branch/commit being inventoried.
- JDK used to build and JDK used to run in the actual environment.
- Build tool and version, such as Maven or Gradle.
- List of build subprojects/submodules.
- Source sets: main, test, integrationTest, generated sources.
- Execution environments: development, CI, container, server, desktop.
- Packaging architecture: runnable JAR, WAR, EAR, `lib/` directory, fat/uber JAR, or native launcher.

Example record:

```text
Project: inventory-service
Revision: <commit-hash>
Build tool: Gradle 8.x
Compile JDK: 21
Runtime JDK: 21
Artifacts: app.jar, catalog.jar, persistence.jar
Execution: java -cp ... com.example.Main
Target: migrate to named modules
```

This information makes tool runs repeatable. If one machine uses JDK 17 while CI uses JDK 21, the analysis of dependencies on JDK modules or multi-release JARs can differ.

**Inventory in the exact configuration actually in use:** for a complex system, separate inventories may be needed for the production runtime and the test runtime.

## 3. Distinguishing Artifacts, Packages, Classes, and Modules

These four concepts are not synonymous:

| Unit | Example | What to record |
|---|---|---|
| Artifact | `logging-core-2.0.jar` | File, Maven coordinates, version, origin |
| Package | `com.example.logging.api` | Set of classes in the same package, owner |
| Class | `com.example.logging.api.Logger` | Actual references from bytecode |
| Module | `com.example.logging` | Name in descriptor or automatic module name |

One artifact can contain multiple packages. One module can be packaged as a modular JAR or exist as an exploded module directory. Java packages do not automatically become modules; migration requires intentionally designing the module units that hold those packages.

Example:

```text
src/main/java/
└── com/example/
    ├── app/
    ├── catalog/api/
    ├── catalog/internal/
    ├── persistence/
    └── util/
```

You cannot conclude that `com.example.catalog` is a module just because packages share a prefix. You must determine inter-package dependencies, independence, and exposed APIs before choosing module boundaries.

## 4. Listing Packages from Source Code

For Java source, you can search for package declarations:

```java
package com.example.catalog.api;
```

Depending on the OS, use an IDE, search command, or script to collect `package` lines from `.java` files. For example, on a system with `grep`:

```shell
grep -R "^package " src/main/java --include="*.java"
```

If using PowerShell:

```powershell
Get-ChildItem src/main/java -Recurse -Filter *.java |
  Select-String -Pattern '^\s*package\s+'
```

The raw output should be normalized: strip semicolons, deduplicate, and separate packages by file path and source set.

A helpful table:

| Package | Source set | Directory | Functional group | API/implementation |
|---|---|---|---|---|
| `com.example.catalog.api` | main | `src/main/java` | Catalog contract | API |
| `com.example.catalog.internal` | main | `src/main/java` | Catalog implementation | Internal |
| `com.example.persistence` | main | `src/main/java` | Database adapter | Implementation |
| `com.example.catalog.test` | test | `src/test/java` | Unit tests | Test-only |

Do not merge packages from main and test without marking the source set. Many projects place test classes in the same package as production code to access package-private members; when migrating to JPMS, this is a design point that needs attention.

## 5. Listing Packages from JARs and Bytecode

For third-party dependencies, packages do not live in your source repository but in compiled artifacts.

Inspect JAR contents:

```shell
jar --list --file libs/catalog-library.jar
```

The output might contain:

```text
META-INF/
META-INF/MANIFEST.MF
com/vendor/catalog/Api.class
com/vendor/catalog/internal/Impl.class
```

From the class paths, you can derive:

```text
com.vendor.catalog
com.vendor.catalog.internal
```

Notes when inventorying:

- Do not count `module-info.class` as a class belonging to a regular package.
- A JAR might contain default-package classes (no package declaration), which are incompatible with explicit named modules.
- Files in `META-INF/services` represent traditional service configuration and should be recorded separately.
- Multi-release JARs may have classes under `META-INF/versions/<n>/`, so consider the target JDK version.
- Fat JARs or shaded JARs may contain multiple merged libraries; identify packages by actual contents, not just artifact name.
- Resource folders are not synonymous with Java packages; the package list should primarily rely on class metadata and bytecode structure.

If possible, export a unique `package → artifact` list, and flag packages that appear in multiple artifacts to catch split packages early.

## 6. Obtaining the Dependency Graph from Maven

In Maven projects, dependencies are declared in `pom.xml`, but the actual result is also governed by transitive dependencies, scopes, and dependency management.

View the dependency tree:

```shell
mvn dependency:tree
```

Export to a file to store alongside the inventory:

```shell
mvn dependency:tree -DoutputFile=dependency-tree.txt
```

Record at least:

- `groupId:artifactId:version`.
- Scope: `compile`, `runtime`, `provided`, `test`, or other scopes.
- Whether the dependency is direct or transitive.
- The parent dependency path that pulled the artifact into the build.
- Whether there are conflicts/omissions due to mediation.
- The version actually selected.

Example:

```text
com.example:inventory-service:1.0
+- com.vendor:json-codec:3.2:compile
|  \- com.vendor:core-api:3.0:compile
+- org.slf4j:slf4j-api:2.0:compile
\- org.junit.jupiter:junit-jupiter:5.10:test
```

The example is illustrative only. Actual names and versions must come from your project's output.

In JPMS, not every Maven dependency becomes a `requires`. For example, test-only dependencies do not necessarily belong in the production module descriptor. Therefore, scopes must be preserved in the inventory table.

## 7. Obtaining the Dependency Graph from Gradle

Gradle can place different dependencies into each configuration, such as `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath`.

Useful commands:

```shell
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

On Windows, use `gradlew.bat` if the project has a Gradle Wrapper.

When you need to explain where a dependency comes from:

```shell
./gradlew dependencyInsight --dependency json-codec --configuration runtimeClasspath
```

The `dependencyInsight` command helps explain the selected version and why an artifact is present in the configuration.

Record the inventory for both compile and runtime:

| Artifact | Compile | Runtime | Test | Direct/Transitive |
|---|---|---|---|---|
| `catalog-api.jar` | Yes | Yes | Yes | Direct |
| `jdbc-driver.jar` | No/depends on config | Yes | Yes | Runtime |
| `junit-jupiter.jar` | No | No | Yes | Test |
| `legacy-core.jar` | Yes | Yes | Yes | Transitive |

A runtime-only library, such as a JDBC driver or service provider, is easily missed if you only inspect `compileClasspath`.

## 8. Using jdeps to Analyze Dependencies from Bytecode

`jdeps` is a JDK tool that reads classes/JARs and analyzes static dependencies. It provides a different data source from the build tool's dependency tree:

- The build tool tells you which artifacts are configured or resolved into the build.
- `jdeps` tells you which classes/packages/modules the bytecode actually references that the tool can detect.

View package-level dependencies:

```shell
jdeps -verbose:package --class-path "libs/*" build/libs/inventory-service.jar
```

On Windows, quotes and wildcards must suit the shell; `--class-path` accepts an appropriate path for classpath dependencies.

View JDK module-level dependencies:

```shell
jdeps --list-deps build/libs/inventory-service.jar
```

Estimate modules needed for a runtime image:

```shell
jdeps --print-module-deps build/libs/inventory-service.jar
```

If the application already has explicit modules and dependencies on the module path:

```shell
jdeps --module-path mods --list-deps dist/com.example.app.jar
```

For multi-release JARs:

```shell
jdeps --multi-release 21 --class-path "libs/*" --list-deps build/libs/inventory-service.jar
```

Version `21` is only an example; use the version matching your target JDK.

**Do not assume jdeps fully analyzes runtime behavior.** Reflection, class names read from configuration, code generation, JNI, and service loading may leave no clear static dependency in bytecode.

## 9. Checking Dependencies on JDK Internal APIs

An important migration step is detecting usage of JDK internal APIs.

Command:

```shell
jdeps --jdk-internals --class-path "libs/*" build/libs/inventory-service.jar
```

The output helps identify references to `sun.*`, `jdk.internal.*`, or other internal JDK APIs.

You should record:

- Which class depends on the internal API.
- Which internal class/package is referenced.
- Purpose of usage.
- Standard or documented JDK API that can replace it.
- Whether the current library has a newer version that removes the internal dependency.

Example table:

| Component | Internal API | Reason | Remediation |
|---|---|---|---|
| Legacy serializer | `sun.misc.Unsafe` | Low-level memory access | Upgrade library or switch to `VarHandle`/appropriate API |
| Custom reflection | `java.lang` private fields | Framework configuration | Use public API, adjust framework, or scoped `opens` |
| Legacy encoding | Internal API | Base64 | `java.util.Base64` |

Do not simply add `--add-exports` or `--add-opens` to ignore the issue without documenting the risky dependency.

## 10. Determining Module Names of Dependencies

A library can fall into one of three main groups:

1. **Explicit named module:** contains `module-info.class` and declares an explicit module name.
2. **Automatic module:** has no explicit descriptor but is placed on the module path, getting its name from `Automatic-Module-Name` or the JAR filename.
3. **Classpath library:** currently loaded into the unnamed module from the classpath; may require a separate migration strategy.

For each JAR, run:

```shell
jar --describe-module --file libs/catalog-library.jar
```

This command displays the module name and descriptor details recognized by the `jar` tool.

Example inventory:

| Artifact | Module name | Type | Main packages | Notes |
|---|---|---|---|---|
| `catalog-api.jar` | `com.example.catalog.api` | Explicit | `com.example.catalog.api` | Has `module-info.class` |
| `legacy-codec.jar` | `com.vendor.legacycodec` | Automatic | `com.vendor.codec` | Name from manifest |
| `old-orm.jar` | TBD | Classpath | `org.example.orm` | May not be ready to migrate yet |

Do not guess module names from Maven coordinates or filenames. For automatic modules whose names are derived from filenames, renaming the JAR at release time can change the module name; therefore, explicit verification is required.

## 11. Detecting Split Packages from the Inventory

A split package is a package name appearing in multiple modules/artifacts. Example:

```text
first.jar:
    com/example/shared/First.class

second.jar:
    com/example/shared/Second.class
```

Even though the two JARs do not contain the same class, both contain the `com.example.shared` package.

On the classpath, the application might still run depending on how the class loader locates classes. When both JARs become named modules, module resolution or layer definition may reject the configuration.

A detection table:

| Package | Artifact A | Artifact B | Status |
|---|---|---|---|
| `com.example.shared` | `first.jar` | `second.jar` | Split package |
| `org.vendor.util` | `util-old.jar` | `util-new.jar` | Possibly duplicate dependency versions |
| `com.example.api` | `api.jar` | `impl.jar` | Need to clarify ownership |

After searching via the package list, you can validate the module path:

```shell
java --module-path mods --validate-modules
```

And observe the application's resolution process:

```shell
java --show-module-resolution --dry-run --module-path mods -m com.example.app/com.example.app.Main
```

These two commands help evaluate the actual module graph. They do not replace inventorying packages across all JARs because a module might sit on the path without being resolved in a specific run.

## 12. Building a Package Dependency Matrix

An artifact dependency tree and module descriptors are not enough to decide module boundaries. You need to know which packages use which packages.

Example:

| Source package | Target package | Usage level | Plan |
|---|---|---|---|
| `com.example.app` | `com.example.catalog.api` | Public API | `requires com.example.catalog` |
| `com.example.catalog.internal` | `com.example.persistence` | Implementation | Consider refactoring |
| `com.example.app` | `java.sql` | JDBC | `requires java.sql` |
| `com.example.app` | `org.slf4j` | Logging | Verify exact module name |

When converting to named modules, one Java import does not mean one new `requires`, because `requires` is a module → module relationship. Multiple packages belonging to the same module only need a single module-level dependency.

However, a dependency exposed in a public API may need `requires transitive` if consumers reading the current module also need to read the module containing that type.

Example:

```java
module com.example.catalog {
    requires transitive com.example.money;
    exports com.example.catalog.api;
}
```

If the public catalog API uses types from the money module, a transitive dependency may be appropriate. If money is only used in the internal implementation, a regular `requires` is usually the better choice.

## 13. Inventorying Dynamic Dependencies and Reflection

Dependency analysis from source or bytecode does not uncover all runtime needs. Dynamic loading mechanisms must be searched for separately:

- `Class.forName("...")` with string-based class names.
- `ClassLoader.loadClass(...)`.
- Reflection: `getDeclaredField`, `getDeclaredMethod`, `setAccessible`.
- `ServiceLoader.load(...)`.
- Legacy Java SPI via `META-INF/services`.
- JNI or native library loading.
- ORMs, JSON serializers, dependency injection frameworks.
- Dynamic proxies and bytecode generation.
- Plugins loaded from external directories.
- Class loader–based resource lookups.
- Java serialization with class names in persisted data.

Example:

```java
Class<?> type = Class.forName(
        "com.vendor.jdbc.DriverImpl"
);
```

String-based class names may not be detected by `jdeps` as static dependencies the way direct imports are.

A table should contain:

| Mechanism | Location | Runtime dependency | JPMS risk |
|---|---|---|---|
| Reflection | `JsonMapper` | Domain model private fields | May need `opens` |
| ServiceLoader | `CodecFactory` | Provider modules | `uses`/`provides` |
| JNI | `NativeBridge` | Native library | Packaging and environment |
| Class.forName | `DriverFactory` | JDBC driver | Dynamic discovery |

This helps the team avoid scenarios where the app compiles successfully but fails at runtime when a framework tries to access private members or load providers.

## 14. Distinguishing Compile, Runtime, and Test Dependencies

An important part of the inventory is **scope**. Not every dependency present in tests needs to be exported or brought into the production module graph.

Example:

```text
compile:
  catalog-api.jar
  logging-api.jar

runtime:
  catalog-impl.jar
  logging-provider.jar
  jdbc-driver.jar

test:
  junit.jar
  mockito.jar
  testcontainers.jar
```

When creating `module-info.java`, the production module should reflect production dependencies. Test libraries may need a separate strategy: separate test modules, tests on the module path, `--patch-module`, or appropriate `--add-opens` configuration.

If scope is not recorded, adding all dependencies into the module descriptor can bloat the module graph and increase coupling.

## 15. Classifying Dependencies by Migration Risk

Not all dependencies are equally difficult to migrate to JPMS. They can be grouped as:

| Group | Signs | Priority |
|---|---|---|
| Low | Explicit named module, clear API exports | Easy to verify and migrate |
| Medium | Automatic module, stable name, no split packages | Need to verify module graph |
| High | Split packages, classpath-only dependency | Need redesign or library upgrade |
| High | JDK internal API, deep reflection | Need API replacement or access configuration |
| High | Dynamic plugin loading, multiple class loaders | Need ModuleLayer/ServiceLoader testing |

Risk levels also depend on how the application uses the library. An automatic module library may run reliably in a specific environment; an explicit module can still cause problems if its dependencies/API are unsuitable.

This table is for planning work, not a compatibility verdict based solely on artifact names or formats.

## 16. Consolidated Inventory Table Template

A minimal table can include the following columns:

| Column | Purpose |
|---|---|
| `artifact` | Filename or Maven/Gradle coordinates |
| `version` | Actual resolved version |
| `scope` | Compile, runtime, test... |
| `module_name` | Module name verified from descriptor |
| `module_type` | Explicit, automatic, classpath-only |
| `packages` | List of packages owned by the artifact |
| `depends_on` | Other artifacts/modules referenced |
| `exports_needed` | Packages that need to be exposed to other modules |
| `reflection` | Whether reflection access exists |
| `services` | `uses`, `provides`, SPI files |
| `jdk_internals` | Whether there are dependencies on JDK internals |
| `split_package` | Packages overlapping with another artifact |
| `migration_action` | Keep, upgrade version, split/merge, relocate |
| `owner` | Team or person responsible |
| `evidence` | Commands/files that confirmed the information |

Example data rows:

```text
artifact,scope,module_name,module_type,migration_action
catalog-api.jar,compile,com.example.catalog,explicit,keep
legacy-codec.jar,runtime,com.vendor.codec,automatic,verify
legacy-orm.jar,runtime,unknown,classpath-only,upgrade
```

This is illustrative data, not the output of a specific project.

The inventory document should also save evidence: command lines used to generate data, `jdeps` output, dependency trees, and JDK versions. When dependencies change, the team can re-run and compare against the old baseline.

## 17. From Package Inventory to Module Boundaries

Once the inventory is ready, you can design modules step by step:

1. Group packages belonging to the same functionality with clear ownership.
2. Identify API packages that will be in `exports`.
3. Keep implementation packages unexported unless there is a valid reason.
4. Identify dependencies between package groups to translate into `requires`.
5. Detect circular dependencies between planned modules.
6. Mark dependencies appearing in public APIs that may need `requires transitive`.
7. Design service interfaces and `uses`/`provides` for replaceable implementations.
8. Record packages needing `opens` for framework reflection.
9. Resolve split packages before splitting into named modules.
10. Migrate module by module, verifying compile, runtime, and tests after each step.

There is no need to modularize every single package into its own module. Module boundaries should reflect contracts and independent evolution capability of components, not merely directory layout.

## 18. Example Analysis from a Classpath System

Suppose an application currently runs via:

```shell
java -cp "app.jar:lib/*" com.example.app.Main
```

The libraries consist of:

```text
app.jar
lib/catalog-api.jar
lib/catalog-impl.jar
lib/json-codec.jar
lib/jdbc-driver.jar
```

The inventory step reveals:

- `app.jar` contains `com.example.app`.
- `catalog-api.jar` contains `com.example.catalog.api`.
- `catalog-impl.jar` contains `com.example.catalog.internal`.
- `json-codec.jar` contains JSON providers and SPI metadata.
- `jdbc-driver.jar` is only needed at runtime.
- Some domain models are accessed by a framework via reflection.

From there, an initial modularization plan might be:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

```java
module com.example.app {
    requires com.example.catalog;
    requires java.sql;

    // Service dependencies need to be considered separately.
}
```

However, whether the two catalog JARs truly combine into one module must be decided based on package ownership, build setup, and dependencies. Do not write the descriptors above solely because two artifacts share similar names.

If the JSON provider resides in an automatic module, the actual module name must be verified before declaring dependencies or organizing service bindings.

## 19. Common Mistakes

**Reading only pom.xml or build.gradle without checking resolved dependencies.**

Build tools have transitive dependencies, dependency management, and version mediation. Use `mvn dependency:tree` or Gradle dependency reports to confirm the actual resolved versions.

**Looking only at imports in source code.**

Dynamic code, reflection, `ServiceLoader`, or runtime libraries may not appear as imports. Record dynamic dependencies separately.

**Relying solely on jdeps.**

`jdeps` analyzes bytecode and does not fully detect reflection/dynamic loading. Cross-check with build, runtime, and test data.

**Failing to inventory internal packages of JARs.**

Two JARs with different names can still contain the same package. Split packages only surface when counting packages per artifact.

**Confusing package names with module names.**

A module name can differ from packages, JAR names, and Maven coordinates. Check the descriptor.

**Mixing test dependencies into production.**

When migrating to JPMS, test setups may need separate configuration; do not turn every test dependency into a production `requires`.

**Ignoring the JDK version.**

Multi-release JARs, built-in JDK modules, and internal APIs can change across Java versions. The inventory must specify the target JDK.

## 20. Recommended Inventory Workflow

You can follow this checklist:

1. **Lock the baseline:** commit, toolchain, JDK, environment, and artifact set.
2. **Extract the build graph:** Maven dependency tree or Gradle configurations.
3. **Inventory source packages:** search for package declarations per source set.
4. **Inventory JAR packages:** use `jar --list`, compute package → artifact.
5. **Determine module names:** run `jar --describe-module` for each JAR.
6. **Analyze bytecode:** run `jdeps` to get package/module dependencies.
7. **Scan JDK internals:** run `jdeps --jdk-internals`.
8. **Find dynamic dependencies:** reflection, JNI, service files, plugin registries, generated code.
9. **Find split packages:** compare package lists and inspect the module path.
10. **Separate scopes:** compile, runtime, test, and special environments.
11. **Build the migration matrix:** planned modules, dependencies, exports, opens, services, and risks.
12. **Save evidence:** command lines, tool outputs, toolchain versions, and inventory date.

After this step, the development team can review module boundaries and incrementally migrate to `module-info.java` based on real data rather than guesswork.

## Conclusion

Inventorying current packages and dependencies is the foundational step in migrating to JPMS. You need to inventory across multiple levels: source packages, JAR packages, the build tool's dependency graph, bytecode dependencies, module names, and dynamic runtime mechanisms.

`mvn dependency:tree`, Gradle dependency reports, `jar --list`, `jar --describe-module`, `jdeps`, `java --validate-modules`, and `--show-module-resolution` complement one another. No single tool alone reveals the complete runtime structure of a large application.

A good inventory must show which artifact owns which package, where each dependency comes from, which scope uses it, what the real module name is, what split package/JDK internal API risks exist, and what the next migration options are. With a reliable baseline, designing `requires`, `exports`, `opens`, and service bindings will have a clear foundation, reducing risks when transitioning from the classpath to the module path.
