# Collecting dependency trees, build plugins, and code generation tools

During a Java compatibility migration, inventorying JDK versions and source code reveals only part of the system. Build outcomes and application runnability also depend on the libraries loaded by the application, plugins used by Gradle or Maven, annotation processors, and tools that generate source code or resources. A dependency may not appear in direct declaration files yet still be pulled in across multiple dependency layers. A build plugin may also run on the build process's JDK while the application is compiled or run on a different JDK.

Therefore, system assessment must collect three related yet independent groups of information: **application dependencies**, **build system plugins and logic**, and **code generation tools**. Each group must have its version, declaration source, execution environment, impact scope, and verification evidence. This inventory output serves as input for determining which components support the target JDK, which components require upgrading, and which changes may alter generated source code or published artifacts.

## 1. Distinguishing the three groups to assess

### 1.1. Application dependencies

Application dependencies are libraries needed by a module's source code or runtime to compile, test, or execute. Examples include Spring Framework, JSON libraries, JDBC drivers, logging APIs, HTTP clients, security libraries, and shared business libraries.

Dependencies may be declared directly in `build.gradle`, `build.gradle.kts`, or `pom.xml`, yet the actual graph also includes transitive dependencies. If an application declares library A, A can pull B and B in turn can pull C. In that case, the application can load C even without a line declaring C in the module's build file.

Not every dependency is used in the same phase:

| Group | Purpose | Common configuration examples |
|---|---|---|
| Compile/API | Needed to compile source code or exposed via the module's API | Gradle `api`, `implementation`; Maven `compile` |
| Runtime | Needed when running the application, though not necessarily on the compile classpath | Gradle `runtimeOnly`; Maven `runtime` |
| Compile-only | Needed at compile time, yet supplied by the environment or another component at runtime | Gradle `compileOnly`; Maven `provided` |
| Test | Used only in test code | Gradle `testImplementation`, `testRuntimeOnly`; Maven `test` |
| Annotation processing | Runs inside the compiler to analyze annotations and generate code | Gradle `annotationProcessor`; Maven Compiler Plugin processor path |
| Build logic | Used to configure and execute builds, not an application runtime library | Gradle plugins/buildscript; Maven build plugins |

Configuration and scope names can vary by plugin, language, and build tool version. Read the project's actual configuration rather than inferring solely from library names.

### 1.2. Plugins and build logic

Build plugins extend Gradle or Maven to provide tasks, goals, compilation rules, testing, packaging, code analysis, documentation generation, and artifact publishing. Examples: Java, Spring Boot, Kotlin, JaCoCo, Checkstyle, SpotBugs, Sonar, Docker image plugins, or internal organizational plugins.

Plugins typically run inside the build process and may use Gradle/Maven APIs, bytecode libraries, ASM, Groovy, Kotlin, or JDK APIs. Consequently, a plugin can be incompatible with the JDK running the build even when application dependencies are fully compatible. Plugins may also require a minimum Gradle/Maven version or depend on other plugins.

With Gradle, distinguish at least two declaration mechanisms:

- Plugin DSL, typically inside `plugins {}` and identified by plugin id and version.
- The legacy `buildscript { dependencies { classpath(...) } }` mechanism, where plugins or build libraries are placed onto the buildscript classpath.

The Plugin DSL can be resolved via `pluginManagement.repositories` in `settings.gradle` or `settings.gradle.kts`. Plugins applied from `buildSrc`, included builds, or internal convention plugins must also be inventoried. The `buildEnvironment` command does not fully represent all plugins declared through the Plugin DSL.

With Maven, plugins are declared in `build/plugins` or `build/pluginManagement` of the POM, and may be inherited from a parent POM or activated by profile. Plugin dependencies have their own classpath separate from application dependencies. Do not confuse a Maven build plugin with a library packaged by the application at runtime.

### 1.3. Code generation tools

Code generation tools produce Java source, bytecode, resources, schemas, or documentation from annotations, schemas, models, or API definitions. Some tools operate inside the compiler, some run in separate tasks/goals, some run prior to compilation, and some run during packaging.

Common examples:

- **Lombok:** annotation processor generating accessors, constructors, builders, and other members from annotations.
- **MapStruct:** annotation processor generating implementations for mapper interfaces.
- **QueryDSL or metamodel tools:** generating entity or query representation classes from models and annotations.
- **OpenAPI Generator:** generating clients, server interfaces, models, or documentation from OpenAPI specifications.
- **Protocol Buffers / gRPC:** generating Java classes and stubs from `.proto` files.
- **Avro:** generating Java classes from Avro schemas.
- **jOOQ code generation:** generating Java representations from database schemas.
- **ANTLR:** generating lexers/parsers from grammars.
- **Internal tools:** generating sources, resources, registries, metadata, or configurations from custom YAML/JSON/schemas.

A single tool can be both a build plugin and a generator. For example, OpenAPI Generator may be integrated as a Gradle plugin or Maven plugin; code generation is the generator function, while the plugin is the mechanism for the build tool to invoke that function. When inventorying, record both roles and the actual executed version.

## 2. Preparing scope and assessment evidence

Before running commands, identify modules, subprojects, Maven modules, and shared build logic within migration scope. In multi-module repositories, do not assess only the first application module. A shared module or convention plugin can affect dozens of other modules.

Prepare the following checklist:

- Module/project names and build file paths.
- Build tool and Wrapper version in use.
- JDK running the build, compiler/toolchain JDK, and expected runtime JDK.
- Profiles, flavors, targets, or configuration variables that alter the dependency graph.
- Build environments that differ: local, CI, release, container, or builds on another OS.
- Key tasks/goals run by CI to compile, test, package, generate, and publish.

Record the commit or tag under assessment. If dependencies change between two runs, results will no longer share the same baseline. For each command, save the command line, working directory, timestamp, tool version, and required output excerpt. There is no need to paste entire long logs into the inventory table; store log artifacts separately and link to their locations.

Do not include tokens, passwords, private keys, repository credentials, or URLs containing credentials in reports. Some debug logs and effective settings files can display sensitive information. Save only filtered copies or required metadata, following organizational security policy.

## 3. Collecting the dependency graph with Gradle

### 3.1. Identify projects and configurations

First, identify the projects recognized by the build:

```bash
./gradlew --version
./gradlew projects
```

`--version` shows the Gradle version and JVM details used by Gradle. The `projects` command lists projects in the build. On Windows, `gradlew.bat` can be used instead of `./gradlew`.

For each key project, inspect tasks and configurations created by plugins. Common Java configurations include:

| Configuration | Content to assess |
|---|---|
| `compileClasspath` | Dependencies needed to compile main source code |
| `runtimeClasspath` | Application runtime dependencies |
| `testCompileClasspath` | Dependencies needed to compile tests |
| `testRuntimeClasspath` | Dependencies used when running tests |
| `annotationProcessor` | Processors running when compiling main source code |
| `testAnnotationProcessor` | Processors running when compiling test code |

Projects using Kotlin KAPT, KSP, Android plugins, or specialized plugins may have other configurations such as `kapt`, `kaptTest`, `ksp`, or plugin-defined configurations. Assess configurations that actually exist and are used.

### 3.2. Print the dependency tree

The `dependencies` command displays the dependency graph of a project or configuration:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencies --configuration annotationProcessor
```

Replace `:app` with the actual project path. If multiple modules need assessment, run for each module in scope rather than relying solely on the root project's graph.

A shortened dependency tree might look like this:

```text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- org.example:service-client:2.4.0
|    +--- org.example:http-core:1.8.0
|    \--- com.fasterxml.jackson.core:jackson-databind:2.17.1
|         +--- com.fasterxml.jackson.core:jackson-annotations:2.17.1
|         \--- com.fasterxml.jackson.core:jackson-core:2.17.1
\--- org.slf4j:slf4j-api:2.0.13
```

This graph shows direct dependencies and transitive branches. When the same module is requested at multiple versions, Gradle may select one version via conflict resolution, constraints, rules, or build resolution settings. Therefore, the dependency tree reflects **selected versions**, not merely the versions written in declaration files.

Common notations in Gradle output:

- `group:artifact:version`: dependency module and selected version.
- `requested -> selected`: the requested version was replaced by the selected version.
- `(c)`: constraint, meaning a version constraint rather than necessarily a direct dependency.
- `(*)`: branch already displayed elsewhere, so the full subtree is omitted.
- `FAILED`: dependency could not be resolved; inspect the cause and repository.
- `strictly`, `prefer`, `reject`, or selection reason info: signs of rules governing version selection.

Do not read the `->` arrow as an error. It indicates the request and selection outcome differ; find the reason and confirm whether that outcome is intentional.

### 3.3. Trace a specific dependency

When identifying a library at risk of incompatibility, use `dependencyInsight` to see which dependency pulls it in and why Gradle selected the current version:

```bash
./gradlew :app:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

On Windows PowerShell, you can write the command on one line or use PowerShell's backtick line continuation. Single-line example:

```powershell
.\gradlew.bat :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Repeat with appropriate configurations. The version on `compileClasspath` can differ from the version on `runtimeClasspath` or test classpaths if dependency branches and resolution rules differ.

When reading the output, look for:

- Which module requested the dependency.
- How many paths bring the library into the graph.
- Requested version and selected version.
- Whether the version was selected due to conflict resolution, constraint, platform/BOM, force, substitution, or another rule.
- Whether any dependency was excluded or substituted.

If a library appears only on the test classpath, you cannot conclude it is packaged in the application. If a library appears on `runtimeClasspath`, determine whether it is actually included in the final artifact or provided by the deployment environment.

### 3.4. Inventory buildscript and plugin dependencies

With Gradle, the following commands help inspect the buildscript classpath:

```bash
./gradlew buildEnvironment
./gradlew :app:buildEnvironment
```

However, this output is not a complete list of plugins applied via the Plugin DSL. Therefore, also read:

- `settings.gradle` or `settings.gradle.kts`, especially `pluginManagement` and repositories used to resolve plugins.
- `plugins {}` in the root and each subproject build file.
- `buildscript { dependencies { classpath(...) } }` in build files.
- `gradle/libs.versions.toml` if a version catalog is used to declare plugins/dependencies.
- `buildSrc/`, convention plugins, and included builds declared in `includeBuild(...)`.
- Plugins applied conditionally by property, environment, or build configuration.

`buildEnvironment` can reveal buildscript dependencies, yet is not enough to conclude no DSL plugins exist. The Plugin DSL is typically resolved via plugin marker mechanisms and repositories in `pluginManagement`; record declared id/version and resolution source. For internal plugins, inspect both the build source and that build's dependencies.

If you need to understand the plugin resolution process, you can run a lightweight configuration task with info logging:

```bash
./gradlew help --info
```

Output can be very long and varies by Gradle version. Extract only lines related to plugin resolution and repositories. Avoid saving unfiltered debug logs because they may contain internal details.

## 4. Collecting the dependency graph with Maven

### 4.1. View the dependency tree

With Maven Wrapper, basic commands include:

```bash
./mvnw -version
./mvnw dependency:tree
./mvnw dependency:tree -Dverbose
```

In a multi-module project, you can run from root to inspect modules or use `-pl` to select a specific project:

```bash
./mvnw -pl app dependency:tree
./mvnw -pl app dependency:tree -Dscope=runtime
./mvnw -pl app dependency:tree -Dincludes=org.example:service-client
```

`-Dverbose` adds information about dependencies omitted from the resulting tree, useful for understanding conflicts. `-Dincludes` can be used to focus on a group/artifact instead of reading an entire huge tree.

Maven resolves dependencies across scopes such as `compile`, `provided`, `runtime`, `test`, `system`, and `import` in the case of BOMs. Scopes affect dependency transitivity and each phase's classpath. Read the resulting tree alongside the effective POM to understand where dependencies are inherited, managed, or excluded.

### 4.2. Understand how Maven selects versions

When the same artifact is requested at multiple versions, Maven applies mediation rules in which the nearest path generally takes precedence; dependency management can manage or override versions. Therefore, the version written in a child library's POM is not necessarily the final version used.

In verbose output, pay attention to branches omitted due to conflict or duplication. Identify:

- Which paths request the artifact.
- Which version was selected and which versions were omitted.
- Whether parent POM or BOM dependency management controls the version.
- Whether any exclusion drops a dependency expected by a library.
- Whether another module in the same reactor picks a different version.

Do not simply edit the version at the first place it appears. Identify where versions are intentionally managed, typically `dependencyManagement`, a BOM, or a parent POM.

### 4.3. Collect the effective POM and plugins

The actual POM may be formed from parent POMs, properties, profiles, dependency management, and plugin management. Use:

```bash
./mvnw help:effective-pom
./mvnw help:effective-pom -Dverbose
./mvnw dependency:resolve-plugins
```

The effective POM shows the configuration after Maven applies inheritance and active profiles. `dependency:resolve-plugins` helps resolve dependencies of build plugins. Also inspect:

- `build/plugins` and `build/pluginManagement`.
- Plugins declared in the parent POM and plugins inherited by child modules.
- Plugin versions, executions, goals, phases, and custom settings.
- Profiles activated by properties, JDK, OS, or file presence.
- Dependencies declared inside each plugin.
- Plugin extensions or lifecycle mappings if used by the project.

Plugin dependencies have their own class realm. They do not automatically become runtime dependencies of the application. When a plugin uses an old bytecode library or JDK API, an error can occur when executing a Maven goal even if the application's dependency tree does not contain that library.

`help:effective-pom` and Maven logs can contain internal paths, repository URLs, or sensitive properties. Before sharing, filter authentication info and keep only fields needed for inventory.

## 5. Inventorying build plugins by compatibility

A plugin list is only valuable when accompanied by execution context. For each plugin, record at least:

| Field | Meaning |
|---|---|
| Plugin id or coordinates | Gradle plugin id or Maven `groupId:artifactId` |
| Version | Declared version and actually resolved version |
| Declaration source | Root build, subproject, parent POM, plugin management, convention plugin |
| Distribution source | Plugin Portal, Maven repository, internal repository, or local build logic |
| Role | Compile, test, package, quality, code generation, container, publish... |
| Execution phase | Configuration, task/goal, lifecycle phase, or CI stage |
| Build JDK | JDK on which the plugin actually runs inside the build process |
| Tool requirements | Minimum Gradle/Maven version, supported JDKs, and plugin dependencies |
| Evidence | Release notes, compatibility matrices, build logs, and test results |

Plugin groups typically needing attention during Java migration:

- Java/Kotlin compiler and language plugins.
- Spring Boot, application packaging, and executable archives.
- Test framework integrations, test runners, and test fixtures.
- Coverage, static analysis, lint, and quality gates.
- Annotation processing or generator integrations.
- Javadoc, documentation, and API/spec generation.
- Database migration, schema inspection, and jOOQ generation.
- Container image, deployment, and release/publishing.
- Internal plugins, convention plugins, and team-authored plugins.

### 5.1. Check relationships between plugins and JDKs

Plugins can be constrained by several different versions:

1. The JDK used to launch Gradle or Maven.
2. The Gradle/Maven version supported by the plugin.
3. The JDK used by a task/plugin to fork child processes, if any.
4. The compiler toolchain used to compile the application.
5. The Java version to which code is generated or compiled.

For example, a plugin may run on JDK 21 yet generate source code targeting Java 17; another plugin may call new JDK APIs inside the build process and therefore fail to run on JDK 17 even while the application still targets Java 17. Record each relationship separately; do not infer plugin compatibility from `sourceCompatibility` or `targetCompatibility`.

### 5.2. Evaluating legacy or lightly maintained plugins

For plugins without recent releases, lacking a clear support matrix, or depending on internal APIs, determine:

- Whether the plugin is still used in CI or merely sits in build files.
- Which tasks/goals actually invoke the plugin.
- Whether it can be replaced by official Gradle/Maven functionality or a maintained tool.
- Whether the plugin can be upgraded independently or requires build logic/configuration changes.
- If it must be kept, whether the plugin can be isolated into a task or child process.
- Which tests are needed to prove the plugin still produces the right artifact.

Do not delete a plugin solely because application source code does not appear to call it directly. A plugin can generate resources, modify manifests, emit metadata, or drive release workflows. Before removing, trace its tasks/goals and impact across the pipeline.

## 6. Collecting code generation tools and generated outputs

### 6.1. Listing generators

Search for generators across multiple locations, not only the keyword `generate` in source code:

- Dependency configurations dedicated to annotation processors.
- Gradle tasks and plugins whose names contain `generate`, `compile`, `schema`, `openapi`, `proto`, `avro`, `jooq`, or similar.
- Maven plugin executions, especially `generate-sources`, `generate-resources`, `process-sources`, and `compile`.
- `annotationProcessorPaths` or compiler plugin configurations.
- Source directories additionally registered as generated source directories.
- Schema, specification, grammar, template, and generator config files.
- Shell scripts, Gradle scripts, Maven profiles, or CI steps running generators outside the main lifecycle.

For example, a generator may not appear in the runtime dependency tree yet remain essential for compilation because it produces Java source before the compiler runs.

### 6.2. Distinguishing annotation processors from generator tasks

Annotation processors are invoked by the compiler during compilation. Processors typically read annotations and type models, then emit sources or resources into a generated output directory. For instance, Lombok and MapStruct are typically configured on the annotation processor path. Processor dependencies must be separated from application runtime dependencies.

A generator task/goal runs as a separate step. It may read a schema or OpenAPI file, load templates, apply options, and write source into a directory recognized by the compiler. For example, OpenAPI Generator, Protobuf, Avro, ANTLR, or jOOQ may be invoked this way depending on the build tool and plugin.

A tool may use both models or integrate in a custom way. Identify the project's actual mechanism rather than classifying purely by product name.

### 6.3. Recording generator inputs and configuration

For each generator, collect:

- Tool name, plugin/processor, and version.
- JDK running the generator and JDK/toolchain used to compile output.
- Inputs: annotations, Java types, OpenAPI documents, `.proto`, schemas, database metadata, grammars, YAML/JSON, or templates.
- Configuration: package names, naming strategies, nullable handling, date/time mappings, serialization, framework targets, and compatibility options.
- Output directory, source set, or source root added to the build.
- Task/goal invoking the generator and dependency ordering relative to compile/package.
- How the generator handles stale files, deleted files, and outputs no longer generated.
- Whether regenerated output is verified to be stable.

For generators reading databases or external services, also record database version, schema snapshot, access permissions, and data source. Do not store passwords or secrets; record only connection/profile names and how the environment supplies credentials.

### 6.4. Identifying ownership of generated source

Generated source is typically not content edited directly by developers. Determine:

- Whether the output directory is committed to Git.
- Whether the source of truth is the schema/specification/annotation or the generated Java files themselves.
- Whether manual edits happen after the generator runs.
- Whether any generated files are included in the release artifact.
- Whether a clean build workflow can fully regenerate the output.

If generated files are also edited manually, clearly document the merge mechanism or source of truth. If generated files are edited without updating inputs or templates, the next generation run may overwrite changes. During migration, compare outputs before and after upgrading the generator to catch changes in APIs, data types, annotations, imports, or package layouts.

## 7. Compatibility risks specific to code generation tools

A generator does not only need to run on the new JDK. Its output must also be compatible with the compiler, frameworks, runtime libraries, and the Java level committed by the module.

### 7.1. JDK executing the generator

A generator may run in the same Gradle/Maven process, inside the compiler, or in a forked child process. If running in-process, it is constrained by the JDK running the build. If forked, inspect the selected executable/JDK, JVM options, and child process classpath.

Do not assume the compiler's Java toolchain setting automatically controls the JDK running every generator. Some plugins support their own toolchain; some use Gradle/Maven's JVM; some look up `JAVA_HOME` themselves. Check plugin documentation and execution logs.

### 7.2. Compatibility between processor and compiler

Annotation processors use compiler APIs, `javax.lang.model`, `com.sun.source`, or related APIs. When upgrading the JDK/compiler, older processors may hit module access errors, reflection errors, type model errors, or fail to understand new language constructs.

Common symptoms:

- `IllegalAccessError`, `InaccessibleObjectException`, or internal package access errors.
- Processor is not discovered or does not run.
- Errors when processing records, sealed classes, generic types, or new annotations.
- Generated source missing methods, having wrong types, or carrying outdated annotations.
- Errors appearing only when compiling on the target JDK, even though application source did not change.

When errors occur, determine whether the stack trace belongs to the compiler, processor, or processor-integrating plugin. Do not rush to add `--add-opens` across the entire build. Prefer upgrading the processor to a supported version, replacing the tool, or applying scoped module-opening configurations with documented justification and a removal plan.

### 7.3. Compatibility of generated source

Generated source may use APIs present only on newer JDKs, newer language syntax, or different annotation/framework versions. Verify:

- The source level and API target aimed at by the generator.
- Whether the output compiles with the chosen compiler/toolchain.
- Whether generated classes depend on matching runtime libraries.
- Whether output is compatible with current framework versions and serialization contracts.
- Whether the generator introduces new warnings or deprecated APIs.

A generator completing successfully only proves it emitted files; it does not prove those files are correct or compatible. Evidence requires compiling the output, testing generated behavior, and inspecting the final artifact.

### 7.4. Reproducibility and output stability

Run the generator twice on the same inputs, same version, and same configuration to test whether output is stable. Output can differ due to timestamps, file ordering, locale settings, timezones, absolute paths, database metadata, or template versions.

If output is unstable, locate the source of variation and determine whether it affects artifacts. For generators whose output is committed, diffing after each run provides useful evidence to spot unintended changes.

### 7.5. Security risks and input sources

A generator can execute code inside plugins, templates, or processors; it can also access databases, repositories, or the filesystem. Inspect tool download sources, pinned versions, permitted repositories, CI permissions, and input contents. Do not run generators from untrusted sources in environments holding production secrets.

## 8. Checking version management, BOMs, and dependency reproducibility

A dependency tree is a snapshot of the graph at a single build. For migration results to be reproducible, you must understand where versions are managed and how dependencies are locked.

### 8.1. Gradle version catalogs, platforms, and constraints

Gradle projects may manage versions in `gradle/libs.versions.toml`, platforms/BOMs, dependency constraints, resolution strategies, or convention plugins. A version catalog centralizes aliases and versions, yet does not automatically prove every transitive dependency is locked.

Check:

- Version catalogs and plugin aliases.
- `platform(...)` or `enforcedPlatform(...)` and imported BOMs.
- `constraints {}` and dependency constraints added by plugins.
- `resolutionStrategy.force`, substitutions, and component selection rules.
- Dependency lock files if the project enables dependency locking.
- Dependency verification metadata if the project uses verification.

If dependency locking is enabled, verify whether lock state is updated and committed alongside changes. If verification metadata is used, determine whether checksums/signatures cover new artifacts. Do not disable verification mechanisms merely so builds pass resolution errors.

### 8.2. Maven BOMs and dependencyManagement

Maven can centralize version management through parent POMs and BOMs imported with scope `import`. `dependencyManagement` manages versions without adding dependencies to the classpath itself. A dependency enters the graph only when declared where needed or inherited via appropriate configuration.

When upgrading frameworks or the JDK, check which foundational libraries the BOM manages, which version overrides the project added, and whether plugin versions are managed separately. Do not upgrade a single library beyond the BOM without verifying compatibility across the entire related library group.

### 8.3. Repositories and distribution sources

Record repositories used to download dependencies and plugins: Maven Central, Gradle Plugin Portal, internal repositories, mirrors, or artifact registries. The same coordinates may be served from multiple sources; repository ordering and mirror rules affect reproducibility and trustworthiness.

Do not record credentials in reports. Record only repository names, repository types, resolution order/priority, and governance policies. If a dependency exists only in an internal repository, confirm that repository still serves the corresponding artifact in CI and release environments.

## 9. Step-by-step practical assessment workflow

The following workflow can be applied per module or group of modules sharing build logic.

### Step 1: Lock baseline

Record commit, build tool version, JDK running the build, project path, and profile/variant under assessment. Identify the exact command CI uses to build the module.

### Step 2: List dependency configurations

For Gradle, list compile, runtime, test, processor, and custom configurations. For Maven, identify relevant scopes, profiles, and reactor modules.

### Step 3: Export dependency graphs

Run `dependencies`/`dependencyInsight` or `dependency:tree` for the necessary configurations. Save outputs and trace libraries with multiple versions, foundational libraries, and libraries with known compatibility issues.

### Step 4: List plugins

Read plugin declarations in root and child modules, plugin management, buildscript classpaths, parent POMs, pluginManagement, convention plugins, and included builds. Record versions and tasks/goals supplied by plugins.

### Step 5: Find generators and processors

Inspect annotation processor paths, KAPT/KSP, compiler plugins, generator tasks/goals, generated source sets, and out-of-lifecycle scripts. Record inputs, outputs, versions, executing JDK, and regeneration steps.

### Step 6: Cross-check support

For each component, consult official documentation regarding supported JDKs, Gradle/Maven, and frameworks. Clearly separate “vendor declares support” from “project verified by running”.

### Step 7: Verify on a clean build

Once a baseline exists, run a clean build in the assessment environment to verify dependencies re-download and generators regenerate outputs. This step belongs to verification; use exact commands/pipelines approved by the team and save results. During initial collection, do not alter versions or settings merely to turn the build green.

### Step 8: Record gaps and owners

Any version of unclear origin, plugin of unclear purpose, generator with unclear inputs, or dependency with unconfirmed support status must be logged as an item needing clarification. Assign module, owner, and evidence to gather.

## 10. Inventory table templates

### 10.1. Application dependency table

| Module | Configuration/scope | Group:artifact | Requested version | Selected version | Declaration source/path | Role | Target JDK | Status |
|---|---|---|---|---|---|---|---|---|
| app | runtimeClasspath | `org.example:client` | 2.x | 2.x | directly declared | HTTP client | needs check | Undetermined |
| app | runtimeClasspath | `com.example:core` | 1.x | 1.x | transitive via client | core API | needs check | Undetermined |
| app | annotationProcessor | `org.example:processor` | 3.x | 3.x | processor config | Codegen | needs check | Undetermined |

Versions in the table above only illustrate structure; replace with data taken from real builds. If the same artifact appears across multiple configurations, record separate rows or link to each graph so classpaths are not conflated.

### 10.2. Build plugin table

| Build/module | Plugin id or coordinates | Version | Declaration source | Task/goal | Required JDK/Build tool | Support evidence |
|---|---|---|---|---|---|---|
| root | Java plugin | actual version | root build | compile/test/jar | actual Gradle and JDK | release notes + build log |
| app | framework plugin | actual version | module build | package/run | framework matrix | official documentation |
| build logic | internal convention plugin | commit/version | included build | module config | JDK running Gradle | source and build test |

### 10.3. Code generation tool table

| Generator/processor | Version | Invocation method | Input | Output | Executing JDK | Source of truth | Verification method |
|---|---|---|---|---|---|---|---|
| Processor A | actual version | annotation processing | Java annotations/types | Java source | compiler/build JDK | source + annotations | compile and test generated behavior |
| Generator B | actual version | Gradle task/Maven goal | API/schema file | client/model source | plugin/build JDK | schema/spec | diff output and compile |
| Generator C | actual version | task/goal outside compiler | database schema | metamodel source | task's JDK | database/schema snapshot | clean generate and integration test |

### 10.4. Compatibility issue table

| ID | Component | Symptom/evidence | Impact scope | Priority | Action needed | Closure criteria |
|---|---|---|---|---|---|---|
| COMPAT-DEP-001 | Dependency X | Target JDK support unconfirmed | Modules A, B | Needs evaluation | Check release notes and test | Support source and test results available |
| COMPAT-PLUGIN-001 | Plugin Y | Requires old Gradle | Build root | High if blocking Wrapper upgrade | Find replacement version/plugin | Build on target Wrapper succeeds |
| COMPAT-GEN-001 | Processor Z | Compiler API access error | Module C | Blocks compile if reproduced | Upgrade processor or replace | Generated source compiles and tests pass |

## 11. Example tracing an issue from dependency graph to migration

Suppose module `billing-service` runs on an older JDK and the dependency tree shows library `proxy-engine` pulled in through `data-client`. When attempting to build on the target JDK, test compilation or startup tests fail with a JDK internal API access error.

Do not immediately modify `billing-service` code, because the offending library may be a transitive dependency. Tracing workflow:

1. Identify the failing configuration: `compileClasspath`, `testRuntimeClasspath`, `annotationProcessor`, or build plugin classpath.
2. Run `dependencyInsight` or `dependency:tree -Dverbose` to trace the path from `billing-service` to `proxy-engine`.
3. Record requested version, selected version, where the version is managed, and selection reason.
4. Determine whether the library belongs to application runtime, processor, or build plugin. Each case has different upgrade and test procedures.
5. Check newer versions of `data-client`/`proxy-engine`, JDK support matrices, and relationships with the current framework.
6. If the library sits inside a build plugin, check plugin compatibility with Gradle/Maven and the JDK running the build. If it sits in runtime, inspect the packaged artifact and application behavior.
7. Upgrade within a small scope, regenerate the dependency graph, and compare selected versions.
8. Run build, tests, and smoke tests on the target JDK; save logs and update issue status.

Another scenario: application compilation fails because the MapStruct processor is incompatible with the new compiler. Runtime dependencies may be completely fine. Inspect the annotation processor configuration, processor version, compiler plugin, and generated source. Upgrading the MapStruct runtime library without upgrading the corresponding processor may not solve the error, because the component directly executing inside the compiler is the processor.

These two examples show that classifying configurations and classpaths accurately dictates remediation direction. Merely searching for library names in `build.gradle` or `pom.xml` can miss the real root cause.

## 12. Common assessment mistakes

| Insufficient approach | Why it easily goes wrong | Proper assessment approach |
|---|---|---|
| Reading only directly declared dependencies | Misses transitive dependencies and selected versions | Export graphs for each configuration/scope |
| Running `dependencies` only at root | Root graph may not represent each module's classpath | Assess each relevant project/module |
| Inspecting only `runtimeClasspath` | Misses processors, test dependencies, and build plugins | Collect compile, runtime, test, processor, and build logic |
| Treating `buildEnvironment` as all Gradle plugins | Plugin DSL resolves via its own mechanism | Read `plugins {}`, `pluginManagement`, version catalog, and included builds |
| Reading only the Maven module's POM | Misses parents, profiles, and plugin management | Capture effective POM along with dependency tree and plugin resolution |
| Merging plugin dependencies into app dependencies | Confuses build classpath with runtime artifact | Record plugins, plugin dependencies, and application dependencies separately |
| Treating a generator as just a library | Misses tasks/goals, inputs, and generated outputs | Inventory invocation mechanism, source sets, and generated outputs |
| Checking only that the generator runs | Output may fail to compile or change behavior | Compile generated source, test, and compare outputs |
| Recording build-file versions as actual versions | Versions can be altered by BOMs, constraints, or conflict resolution | Verify selected versions in the graph |
| Running debug logs and saving verbatim | Can expose internal URLs or credentials | Filter logs and strip sensitive data |
| Upgrading all libraries/plugins at once | Hard to trace root cause of regressions | Batch changes by group and keep step-by-step evidence |

## 13. Assessment completion criteria

Collection is considered sufficient to move to compatibility analysis when the team can answer the following questions with evidence:

- Have all modules and build logic in scope been fully identified?
- Are direct and transitive dependencies selected for compile, runtime, test, and processors known?
- Have overridden, forced, excluded, or BOM/constraint-managed versions been traced?
- Have Gradle/Maven plugins, versions, declaration sources, tasks/goals, and JDK/build tool requirements been listed?
- Have Plugin DSL, buildscript, parent POMs, plugin management, convention plugins, and included builds been inspected?
- Have annotation processors, KAPT/KSP, and generator tasks/goals running outside the compiler been found?
- Have inputs, outputs, versions, executing JDK, and source of truth been recorded for each generator?
- Have runtime dependencies been separated from processor/plugin dependencies?
- Have baselines, commands, outputs, and traceable evidence sources been saved?
- Do undetermined items have owners and next actions assigned?

Do not transition a component to “compatible” simply because its version was recorded. You need an authoritative support statement and/or verification test results on the target combination per project criteria. If documentation or test environments are not yet available, mark “undetermined” to place in the gap/risk register.

## 14. Handoff deliverables for compatibility analysis

After assessment, the team should have a reusable dossier:

1. **Module/build catalog:** module paths, build tools, Wrapper versions, JDK running the build, and relevant profiles/variants.
2. **Dependency inventory:** dependency graphs by configuration/scope, requested and selected versions, dependency paths, and version management locations.
3. **Plugin inventory:** plugin ids/coordinates, versions, resolution sources, tasks/goals, private dependencies, and JDK/build tool requirements.
4. **Generator inventory:** processors/generators, versions, inputs, outputs, invocation methods, executing JDKs, sources of truth, and reproducibility checks.
5. **Version governance:** BOMs, version catalogs, dependency constraints, lock files, verification metadata, repositories, and related policies.
6. **Evidence archive:** commands, filtered logs, effective POMs, dependency trees, release notes, and test results.
7. **Gap register:** unsupported or undetermined components, impact scope, priority, owner, and closure criteria.

### Handoff checklist

- [ ] Baseline tied to a specific commit and build configuration.
- [ ] Dependency graphs collected for required classpaths/configurations.
- [ ] Transitive dependencies and version selection reasons traced for key components.
- [ ] Build plugins cataloged separately from application dependencies.
- [ ] Plugin DSL, buildscript, plugin management, and internal build logic reviewed.
- [ ] Annotation processors and code generation tools identified.
- [ ] Generator inputs, outputs, executing JDK, and output regeneration steps recorded.
- [ ] BOMs, version catalogs, constraints, locks, and verification policies inspected.
- [ ] Evidence stored securely, containing no credentials or secrets.
- [ ] Every gap has an assigned owner and next verification step.

Collecting dependency trees, build plugins, and code generation tools gives the team visibility into every component participating in building and running the application. By separating classpaths accurately, tracing selected versions, and determining where generators execute, the team can pinpoint compatibility causes at the right layer. This forms the foundation for building a support matrix, assessing risks, and designing verifiable migration steps.
