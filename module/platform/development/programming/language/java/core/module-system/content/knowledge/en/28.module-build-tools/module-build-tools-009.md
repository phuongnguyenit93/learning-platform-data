# Inspecting the dependency graph before publishing

## 1. Why inspect the dependency graph before release?

With the Java Core Module System (JPMS), a library may compile cleanly on the author's machine yet still be unusable when others place the JAR on the module path. Causes often include differently resolved dependencies, unstable module names, packages hidden by `exports`, missing runtime dependencies, or a provider discovered only in the development environment.

Therefore, before publishing a modular JAR, do not merely run the build and upload the artifact. You must inspect at least two perspectives:

1. **Build tool dependency graph:** Which artifacts and dependency versions did Maven or Gradle select for each scope/configuration?
2. **JPMS module graph:** At compile time and runtime, which modules read which modules, which modules are resolved, and which packages/services are exposed?

A thorough check requires a third perspective: **the actual published artifact**. The dependency graph inside the source project may not match the dependency graph a consumer sees when downloading the artifact from a repository.

The goal is not to shrink the graph at all costs. The goal is a graph that is explainable, reproducible, and usable in the consumer's environment.

## 2. Distinguishing the build dependency graph from the JPMS module graph

Example data management library:

~~~text
com.acme.report.api
    |
    +-- com.acme.report.codec
    |        |
    |        +-- third-party JSON library
    |
    +-- java.sql
~~~

Distinguish the relationships:

| Aspect | Described by | Question to answer |
|---|---|---|
| Build dependencies | `pom.xml`, `build.gradle`, repository metadata | Which artifact, which version, which scope? |
| JPMS dependencies | `module-info.java` and compiled descriptors | Which modules need to read which other modules? |
| Runtime configuration | Module path, root modules, service binding | Which modules are actually resolved at runtime? |
| Public API dependencies | Public method signatures, superclasses/interfaces, exported packages | Does the consumer need this dependency to compile? |
| Dynamic dependencies | Reflection, `ServiceLoader`, configuration, plugin discovery | Are there dependencies that appear only at runtime? |

A Maven/Gradle dependency does not equate to a `requires` line. For example, libraries on the traditional classpath, `runtimeOnly` dependencies, or annotation-processing-only dependencies may need different handling when writing the module descriptor.

Conversely, `requires java.sql;` is a module relationship with a JDK component; it does not necessarily appear as an external dependency in POM or Gradle configurations.

**Key takeaway:** the build graph explains how artifacts are selected; the JPMS graph explains how named modules are linked and how access is controlled.

## 3. Modular library example and public API dependencies

Suppose module `com.acme.report.api` exposes a reporting API:

~~~java
module com.acme.report.api {
    requires transitive java.sql;
    requires com.acme.report.codec;

    exports com.acme.report.api;
}
~~~

Public interface:

~~~java
package com.acme.report.api;

import java.sql.Connection;

public interface ReportService {
    byte[] generate(Connection connection);
}
~~~

From the descriptor above:

- `java.sql` is part of the public contract because the `Connection` type appears in the method signature.
- `requires transitive java.sql` gives consumers of this module readability to `java.sql` through the API dependency.
- `com.acme.report.codec` is an implementation dependency in this example, so declare only `requires` if the public API does not expose types belonging to the codec module.
- `com.acme.report.api` is the exported package; internal codec packages do not need to be exported to consumers.

If `requires transitive java.sql` were changed to `requires java.sql`, a consumer declaring only `requires com.acme.report.api` might also have to add `requires java.sql` when using SQL types in the API.

Conversely, do not use `requires transitive` for every dependency. It adds extra readability edges to consumers and tightens the contract between modules unnecessarily.

## 4. Inspecting the graph in Maven

With Maven, a foundational step is inspecting the **resolved dependency tree**, rather than merely reading individual lines in `pom.xml`.

Run in the module or project to be released:

~~~bash
mvn dependency:tree
~~~

Abbreviated example output:

~~~text
com.acme:report-api:jar:1.4.0
+- com.acme:report-codec:jar:2.2.0:compile
|  \- org.example:json-core:jar:3.0.0:compile
\- org.example:logging-adapter:jar:1.1.0:runtime
~~~

Points to verify:

- What are the final selected group/artifact/version coordinates?
- Which dependencies were pulled in transitively?
- Does each dependency have `compile`, `runtime`, `test`, `provided`, or another scope?
- Was any version overridden by dependency mediation or dependency management?
- Are any unnecessary dependencies appearing in the production artifact metadata?

Maven can inherit versions from a parent POM or BOM via `dependencyManagement`. Looking only at dependency declarations in one module misses version decisions made at the parent build level.

When you need to inspect the POM merged with parent, profiles, and properties:

~~~bash
mvn help:effective-pom
~~~

This command is useful when dependency versions are not declared directly in the current POM.

A release build should use explicitly managed versions and avoid relying on repositories or profiles that exist only on the author's machine.

## 5. How Maven scopes affect consumers

Not every dependency declared in the POM needs to appear in the consumer's runtime.

Common scopes:

| Scope | Primary intent | What to audit |
|---|---|---|
| `compile` | Needed for compilation and usually included in consumer dependencies | Is it genuinely an API/runtime dependency? |
| `runtime` | Not needed to compile current sources, yet needed at runtime | Do runtime tests cover it? |
| `test` | Serves testing only | Must not leak in as a production dependency |
| `provided` | Expected to be supplied by the runtime environment | Do consumers/hosts genuinely provide it? |
| `optional` | Not propagated automatically as a mandatory dependency to downstream consumers | Do docs instruct users to add it when needed? |

For example, a library API needs a JSON codec at runtime. If the author marks the codec as optional in the POM without a fallback mechanism, consumers may download the library cleanly and then hit errors when invoking that feature.

Similarly, putting a JDBC driver in `test` scope does not mean the driver will exist in the consumer's runtime. Distinguish **dependencies used for testing** from **dependencies required in actual deployment**.

Maven scopes and JPMS `requires static` are not two spellings for the same thing. One governs build dependency resolution, while the other governs module relationships at compile/runtime. Inspect both when optional integration exists.

## 6. Inspecting the dependency graph in Gradle

With Gradle, dependency graphs are resolved per **configuration**. A commonly used configuration:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

And the runtime configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows you can use:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

The two graphs can differ, especially when the project uses `implementation`, `api`, `compileOnly`, `runtimeOnly`, or custom variants.

If a build has multiple subprojects, target the exact project:

~~~bash
./gradlew :report-api:dependencies --configuration runtimeClasspath
~~~

When you need to know why a specific library or version appears:

~~~bash
./gradlew :report-api:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency json-core
~~~

`dependencyInsight` helps trace dependency paths and version selection reasons for a specific dependency, useful when resolving conflicts.

Do not conclude the published version solely by reading `implementation 'group:artifact:version'`. Resolution strategies, dependency constraints, platforms/BOMs, and variants can all affect the final outcome.

## 7. Gradle api and implementation have distinct meanings

With the `java-library` plugin, Gradle distinguishes:

~~~groovy
dependencies {
    api 'com.acme:report-contract:1.0.0'
    implementation 'com.acme:report-codec:2.2.0'
    runtimeOnly 'com.acme:report-runtime-adapter:1.1.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
~~~

By the design of the Java Library plugin:

- `api` is for dependencies that must be exposed to consumers' compile classpaths.
- `implementation` is for implementation dependencies that do not need to be exposed as consumers' compile-time APIs.
- `runtimeOnly` is for dependencies needed only at runtime.
- `testImplementation` is not a production dependency.

With JPMS, choosing `api` or `implementation` **does not automatically write** `requires transitive` or `requires` into `module-info.java`. Ensure build metadata and descriptors align with the real contract.

If a public signature uses a type from another module while the build dependency is hidden in an implementation scope, consumers may run into compilation difficulties. Conversely, putting every dependency in `api` exposes an unnecessarily large graph.

## 8. Inspecting the packaged module descriptor

The source descriptor is not the final proof. After building, inspect the artifact intended for publishing:

~~~bash
jar --describe-module --file build/libs/report-api-1.4.0.jar
~~~

Or with Maven:

~~~bash
jar --describe-module --file target/report-api-1.4.0.jar
~~~

The output for an explicit modular JAR must confirm:

- The module name matches what consumers will write in `requires`.
- `requires` entries match actual dependencies.
- API packages have the right `exports` scope.
- Qualified exports/opens and service declarations are packaged properly.
- `module-info.class` actually resides in the artifact.

You can list files in the JAR:

~~~bash
jar --list --file build/libs/report-api-1.4.0.jar
~~~

For a normal modular JAR, you should see:

~~~text
module-info.class
com/acme/report/api/ReportService.class
~~~

If the JAR lacks an explicit descriptor, placing it on the module path may turn it into an automatic module. In that case, the module name may come from `Automatic-Module-Name` or the filename; never assume the JAR name equals the module name.

## 9. Inspecting the module graph with jdeps

`jdeps` is a JDK tool for analyzing dependencies from bytecode. After building, you can run:

~~~bash
jdeps --print-module-deps --module-path libs \
  build/libs/report-api-1.4.0.jar
~~~

Or:

~~~bash
jdeps --list-deps --module-path libs \
  build/libs/report-api-1.4.0.jar
~~~

Where:

- `--module-path libs` points to modular dependencies required for analysis.
- `--print-module-deps` prints a condensed list of module dependencies useful for cases such as preparing `jlink`.
- `--list-deps` reports discovered module/package dependencies.

If dependencies sit in multiple directories, construct the matching module path. Do not expect `jdeps` to download libraries from Maven Central or Gradle caches like a build tool.

For multi-release JARs, pass the appropriate `--multi-release` option to analyze class variants targeting the intended Java version.

Important note: `jdeps` relies primarily on static bytecode dependencies. Reflection, `ServiceLoader`, class names read from config files, and dynamically loaded plugins may not be fully reflected. Thus `jdeps` is a graph-checking aid, not a guarantee that runtime will need no further dependencies.

## 10. Comparing requires in descriptors with actual dependencies

Example:

~~~java
module com.acme.report.api {
    requires java.sql;
    requires com.acme.report.codec;

    exports com.acme.report.api;
}
~~~

Questions to ask:

1. Is `com.acme.report.codec` actually present on the consumer's module path?
2. Does the actual module name of codec match what the descriptor states?
3. Is the codec dependency an explicit module or an automatic module?
4. Does the public API use types from codec?
5. If so, do consumers need `requires transitive` instead of `requires`?
6. If codec is an optional feature, is the module descriptor making it mandatory at runtime?
7. If codec is loaded dynamically via service/provider, does the design actually need a direct `requires` on the implementation module?

Do not delete `requires` solely because a static analysis report shows no direct bytecode usage of the dependency. A dependency may be needed for reflection, service discovery, or configuration-driven code paths.

Conversely, a dependency left over in the POM yet no longer used can bloat the graph and introduce unnecessary risk.

## 11. Inspecting the module graph at runtime

If the library has a sample app or consumer smoke test, use the module path and the Java launcher's resolution diagnostics:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.report.demo/com.acme.report.demo.Main
~~~

The command prints information about modules resolved as the JVM prepares to launch the application.

Pay attention to:

- Root modules and `requires` dependencies.
- Modules added by service binding, if any.
- Dependencies from the runtime image such as `java.base`, `java.sql`, and other JDK modules.
- Third-party modules actually found on the module path.

You can check observable modules with:

~~~bash
java --module-path mods --list-modules
~~~

And inspect the descriptor of a specific module:

~~~bash
java --module-path mods \
  --describe-module com.acme.report.api
~~~

`--list-modules` and `--describe-module` are module inspection tools; an observable module is not guaranteed to be resolved in a specific run's graph. `--show-module-resolution` answers questions about a specific execution better.

## 12. Do not let a passing build mask runtime errors

A build can succeed because the IDE or test classpath happened to include extra dependencies, while consumers running on the module path hit missing modules.

A common example:

~~~java
module com.acme.report.app {
    requires com.acme.report.api;
}
~~~

Yet `com.acme.report.api` has:

~~~java
requires com.acme.report.codec;
~~~

If the publisher fails to publish or supply the codec artifact properly, consumers may get:

~~~text
java.lang.module.FindException:
Module com.acme.report.codec not found, required by com.acme.report.api
~~~

This is not an `exports` error. It is an unresolvable module dependency error.

Therefore, before publishing, test **downloading the artifacts intended for release** from a separate consumer project using a module path matching downstream environments. Do not rely solely on tests inside the source tree where IDE-prepared module outputs already exist.

## 13. Duplicate module names and split packages

Two issues frequently cause failures when moving dependencies from the classpath to the module path:

### 13.1. Duplicate module name

Two JARs can be identified by the same module name despite different filenames, for example:

~~~text
libs/report-codec-1.0.jar
libs/report-codec-2.0.jar
~~~

If both declare module name `com.acme.report.codec`, the module finder/module path may hit a conflict or select an unexpected artifact, depending on placement and configuration.

Ensure the consumer's module path does not contain competing artifact versions for the same module. Audit transitive dependencies that pull in mixed old and new versions.

### 13.2. Split packages

Suppose two named modules both contain:

~~~text
com.acme.report.common
~~~

When these modules participate together in a configuration, JPMS can detect a package ownership conflict or prevent consumers from reading both modules sharing that package simultaneously.

Do not try to solve split packages by tweaking `requires` arbitrarily. Usually you need to adjust source/module layout so one package belongs to one defined module, or move shared contracts into an explicit API module.

To help catch issues in a module path setup, you can run:

~~~bash
java --module-path mods --validate-modules
~~~

This command checks the module path at the module metadata level and reports certain issues such as module/package conflicts. It does not replace runtime smoke tests and does not catch all conflicts when modules are loaded dynamically.

## 14. Checking automatic modules and stable module names

A JAR lacking `module-info.class` placed on the module path may be treated as an automatic module.

An automatic module's name may be determined by:

- The `Automatic-Module-Name` manifest attribute, if present.
- A module name derived from the JAR filename when that attribute is absent.

Example dependency:

~~~text
legacy-serializer-2.4.jar
~~~

may have a module name derived from the filename. If the vendor renames the artifact, the derived module name can change, breaking consumers' `requires` lines.

Before publishing a library depending on an automatic module:

~~~bash
jar --describe-module --file libs/legacy-serializer-2.4.jar
~~~

Confirm the module name matches what is used in `module-info.java`.

If publishing a JAR yourself that cannot yet become an explicit module, consider declaring a stable `Automatic-Module-Name` in the manifest to reduce filename-derivation risk. This is a transitional step; it does not replace designing an explicit module descriptor.

## 15. Checking dependencies leaked through public APIs

Do not read only the POM/Gradle graph; inspect public signatures in exported packages.

Example:

~~~java
package com.acme.report.api;

import com.thirdparty.json.JsonNode;

public interface ReportParser {
    JsonNode parse(String text);
}
~~~

If `JsonNode` belongs to an external dependency, consumers using the interface will need visibility of that type. In JPMS, this may signal that module readability needs to be propagated via `requires transitive`.

An alternative architectural solution is keeping external dependencies in the implementation layer and exposing only types owned by the API module:

~~~java
package com.acme.report.api;

public record ReportDocument(String title, String content) {
}
~~~

If the API returns `ReportDocument`, consumers do not need to know which JSON library was used for parsing.

API leak checklist:

- Do public return/parameter types live outside the API module?
- Do checked exceptions belong to a private dependency?
- Do generic arguments contain implementation types?
- Do exported interfaces extend APIs from modules consumers cannot read?
- Do Gradle `api` and Maven dependency metadata accurately reflect exposed dependencies?

The public API and dependency graph must be compatible; otherwise consumers can hit compile failures even when the publisher's build passes.

## 16. ServiceLoader, reflection, and dynamic dependencies

A static graph rarely explains all runtime behavior.

### 16.1. ServiceLoader

A consumer may declare:

~~~java
module com.acme.report.app {
    requires com.acme.report.api;
    uses com.acme.report.spi.ReportProvider;
}
~~~

Provider module:

~~~java
module com.acme.report.csv {
    requires com.acme.report.api;

    provides com.acme.report.spi.ReportProvider
        with com.acme.report.csv.CsvReportProvider;
}
~~~

The provider module must be included in the configuration/layer used by `ServiceLoader`. If a library exposes a service API without shipping a provider itself, document how consumers should add an appropriate provider artifact.

Do not add `requires com.acme.report.csv` to the API module just to force a specific provider to exist. That creates reverse coupling between contract and implementation.

### 16.2. Reflection

Frameworks may require `opens` or qualified opens to access model classes.

~~~java
module com.acme.report.api {
    exports com.acme.report.api;
    opens com.acme.report.model to com.fasterxml.jackson.databind;
}
~~~

Build configuration may include the Jackson dependency, yet runtime can still fail reflection if the module graph/opens are wrong. Pre-publish graph checks should be paired with real integration tests.

### 16.3. Configuration-only dependencies

Class names read by a plugin system from configuration files may not show up in `jdeps`. Before publishing, document and test those scenarios instead of using static analysis to strip out dynamic dependencies.

## 17. Version management and reproducibility of the dependency graph

Before publishing, know how the graph will resolve on other machines and in future builds.

With Maven:

- Use explicit versions and consistent dependency management.
- Do not depend on SNAPSHOTs or unintended shifting versions in stable releases.
- Check active profiles that affect dependencies.
- Inspect the effective POM and dependency tree of the exact release configuration.

With Gradle:

- Inspect resolved graphs of `compileClasspath` and `runtimeClasspath`.
- Consider dependency locking/verification per project policy.
- Check constraints, platforms/BOMs, and resolution strategies.
- Avoid dynamic/changing versions that alter the graph between publications.

Version conflicts may not cause immediate compile errors, yet can alter behavior or public ABI when consumers resolve dependencies under different constraints.

For stable releases, record plugin versions, JDK/toolchains, and key dependencies in CI build logs or release metadata so issues remain reproducible.

## 18. Dependency graphs and supply-chain risks

Inspecting the graph also helps catch unnecessary dependencies, outdated versions, or artifacts from unclear sources.

Helpful steps:

1. Identify actual direct and transitive dependencies.
2. Remove test/dev dependencies from production graphs when unneeded.
3. Verify license policies and artifact provenance per organizational rules.
4. Run vulnerability scans on the resolved graph with project-approved tools.
5. If required by the release process, generate an SBOM for the set of dependencies actually used.
6. Record temporary exceptions and their owning maintainers.

Distinguish vulnerability scanning from JPMS resolution. A valid module graph does not prove dependencies are secure; a clean vulnerability scan also does not prove module names, exports, or runtime service bindings are accurate.

These are complementary quality gates, not replacements for running the application on the module path.

## 19. Inspecting published artifacts instead of only sources

After building, confirm the final JAR contents match what consumers will download.

For example, with Maven:

~~~bash
mvn -B -ntp clean verify
~~~

With Gradle:

~~~bash
./gradlew clean build
~~~

Next:

~~~bash
jar --describe-module --file path/to/published-artifact.jar
jar --list --file path/to/published-artifact.jar
~~~

If the release uses a copied/staged artifact, inspect **that exact staged file** before publishing. Avoid testing artifact A while uploading artifact B generated by a different task or profile.

Also verify publication metadata:

- Does the Maven POM have the right group/artifact/version?
- Do dependency scopes and optional flags reflect consumer needs?
- Does Gradle Module Metadata (if present) have accurate variants and dependencies?
- Are artifacts and metadata published at the same version?
- Are there internal dependencies existing only in a company repository that external consumers cannot download?

A modular JAR with a valid descriptor paired with a POM missing required dependencies can still cause downstream failures.

## 20. Consumer smoke test before publishing

A very valuable check is creating a **small consumer project outside the source modules**.

Example:

~~~text
consumer-smoke/
└── src/
    ├── module-info.java
    └── com/acme/smoke/Main.java
~~~

Descriptor:

~~~java
module com.acme.smoke {
    requires com.acme.report.api;
}
~~~

Main:

~~~java
package com.acme.smoke;

import com.acme.report.api.ReportService;

public final class Main {
    public static void main(String[] args) {
        System.out.println("API visible: "
                + ReportService.class.getModule().getName());
    }
}
~~~

Compile against staged artifacts and dependency modules:

~~~bash
javac --module-path dist/modules \
  -d out/consumer \
  consumer-smoke/src/module-info.java \
  consumer-smoke/src/com/acme/smoke/Main.java
~~~

To run from exploded module output, put `out/consumer` into an appropriate module path entry or package the consumer as a modular JAR. For example:

~~~bash
jar --create --file dist/modules/com.acme.smoke.jar \
  -C out/consumer .

java --module-path dist/modules \
  -m com.acme.smoke/com.acme.smoke.Main
~~~

The `dist/modules` directory in the example must exist and contain the actual required JARs or exploded modules, including the API module and mandatory dependencies.

The smoke test should verify:

- Can the consumer compile against the public API?
- Does the module name match documentation?
- Do module dependencies resolve?
- Are there any split package or duplicate module name errors?
- Do public signatures reference types unreadable by the consumer?
- If services/reflection are part of the contract, does that flow execute properly?

Prefer staged artifacts over source-project outputs, because the consumer should mirror how real users download the library.

## 21. CI checklist for modular libraries

A release pipeline may include the following gates:

| Stage | Check | Expected evidence |
|---|---|---|
| Build | Compile/package with target JDK | Passing build, stable artifacts |
| Unit/integration tests | Test APIs and implementations | Test results |
| Maven/Gradle graph | Resolve compile/runtime dependencies | Dependency tree or configuration report |
| Artifact descriptor | `jar --describe-module` | Accurate module name and requires/exports |
| Module analysis | `jdeps` with prepared module path | Explainable module dependencies |
| Module validation | `java --validate-modules` | No module path errors detected by the tool |
| Runtime resolution | `--show-module-resolution` with demo app | Module graph boots cleanly |
| Consumer smoke | Compile/run using staged artifacts | Public API works via module path |
| Dynamic behavior | ServiceLoader/reflection/plugin scenarios | Providers and reflection work if supported |
| Publication metadata | POM/Gradle metadata/version | Downstream can fetch right artifacts/dependencies |

Not every project needs a separate CI tool for every row. However, the key risks must be verified prior to publishing using reproducible tests or commands.

For example, a minimal pipeline should at least build, run tests, inspect the dependency graph, check artifact descriptors, and execute a consumer smoke test. Items like security scanning or SBOM depend on release policies.

## 22. Common symptoms when the graph is wrong

| Symptom | Possible cause | Investigation path |
|---|---|---|
| `module not found: X` | Required dependency missing on module path or wrong module name | Check descriptor, dependency tree, and module path |
| Consumer compile fails though publisher build passes | Public API exposes unreadable type or missing dependency metadata | Check exported APIs, `requires transitive`, POM/Gradle variants |
| `package ... is not visible` | Package not exported or consumer does not read module | `requires`, `exports`, qualified exports |
| Provider not found | Provider module not resolved or missing `provides` | `uses`/`provides`, `--show-module-resolution`, `ServiceLoader` |
| Reflection throws `InaccessibleObjectException` | Package not `opens` to framework module | Check `opens` and runtime flags |
| Split package error | Two named modules share a package name | Audit package contents and module path |
| Wrong library version selected | Maven mediation, Gradle resolution, or bad metadata | `dependency:tree`, `dependencyInsight` |
| Works locally, fails after publish | Dependency existed only in IDE/test/source tree or incomplete metadata | Test consumer from staged artifacts |
| Automatic module name changes | Name derived from JAR filename | `jar --describe-module`, manifest, lock module names |
| Jdeps misses dynamic dependencies | Reflection, service providers, config-driven classes | Runtime/integration tests |

Do not fix every error by putting all JARs on the classpath or scattering `--add-reads`/`--add-exports`. Identify whether the graph is missing a dependency, using the wrong module name, breaking a public contract, or blocking package access.

## 23. Practical workflow before clicking publish

A workflow applicable to both Maven and Gradle:

1. **Clean build with the target supported JDK.** Ensure `module-info.class` is produced.
2. **Resolve the dependency graph.** Inspect compile and runtime dependencies of the exact project/version.
3. **Trace transitive dependencies.** Account for the origin of key libraries, especially those with multiple versions.
4. **Audit the public API.** Types in exported packages must be usable by consumers.
5. **Read the final artifact's descriptor.** Confirm module name, `requires`, `exports`, `opens`, `uses`, `provides`.
6. **Run `jdeps` for static dependency analysis.** Provide the complete module path to avoid false conclusions.
7. **Validate the module path.** Catch duplicate module names or split packages.
8. **Run a runtime demo with `--show-module-resolution`.** Confirm the module graph resolves as intended.
9. **Test dynamic dependencies.** Providers, reflection, and plugin loading if supported by the product.
10. **Run a consumer smoke test from staged artifacts.** Do not rely on IDE classpath conveniences.
11. **Inspect publication metadata.** POM/Gradle variants must supply appropriate dependencies.
12. **Archive release evidence.** Record JDK/toolchain, resolved graph, and accepted exceptions.

If any step uncovers a missing dependency, fix it at the root source: descriptor, build configuration, published metadata, service registration, or API design. Then rerun the workflow before publishing.

## 24. Key takeaways

Inspecting the dependency graph before publishing is more than checking which libraries appear in `pom.xml` or `build.gradle`. With JPMS, reconcile all of these simultaneously:

- **Build graph:** Which artifacts, versions, and scopes did Maven/Gradle select?
- **Module graph:** Which `requires` relationships and access rules does `module-info.class` declare?
- **Runtime graph:** Which modules does the JVM actually resolve via the module path?
- **Published artifact:** Can consumers download, compile, and run using the released artifacts and metadata?

Use `mvn dependency:tree` or Gradle `dependencies`/`dependencyInsight` to understand the build graph; use `jar --describe-module`, `jdeps`, and `java --show-module-resolution` to understand JPMS; and finally use a consumer smoke test to prove the contract and dependencies genuinely work.

**Publish only when the dependency graph is explainable, the module graph resolves cleanly, the public API leaks no unintended dependencies, and the final artifact has been verified from the consumer's perspective.**