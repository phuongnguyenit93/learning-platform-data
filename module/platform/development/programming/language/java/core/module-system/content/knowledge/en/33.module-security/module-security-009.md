# Auditing the Module Graph in the Release Pipeline

A modular Java application can compile successfully yet still fail to start after packaging. Causes may include missing modules, incorrect transitive dependencies, provider modules excluded from runtime, unexported packages, or a module path configuration that differs from the build environment.

Therefore, the release pipeline needs to inspect **the module graph of the artifacts to be deployed**, rather than checking only `module-info.java` files in source. The audit must verify which modules are found, which modules are resolved, whether dependency relationships are valid, and whether the application can start with the expected runtime configuration.

## 1. Distinguishing the Source Dependency Graph from the Runtime Module Graph

In a modular project, there are several distinct dependency layers:

- **Source dependency graph:** the modules declared in source code via `requires`, `uses`, and `provides`.
- **Observable module set:** the modules that the JVM can locate from system modules, the module path, and configured module sources.
- **Resolved module graph:** the root modules together with required dependencies after resolution.
- **Runtime environment:** the actual module graph together with classpath, module path, JVM arguments, module layers, and launch configurations.

These layers are related but not identical. A JAR on the module path may be observable without being resolved. A resolved module is also not guaranteed to supply the exact methods required by consumer bytecode.

For example:

~~~text
com.example.app
    └── requires com.example.api

com.example.api
    └── requires java.base

com.example.plugin.audit
    └── requires com.example.api
~~~

If `app` does not declare a dependency on `plugin.audit` and no mechanism brings the plugin into the graph, the plugin may sit on the module path without appearing in the resolved graph.

At release time, clearly determine whether that plugin is a required dependency, an optional module, or a service provider selected by configuration. Do not look only at the list of JARs in the distribution directory and conclude that runtime uses all of them.

## 2. Why Audit in the Release Pipeline?

Auditing the module graph catches errors early that otherwise only appear on deployment machines:

- Missing modules or dependencies in the distribution directory.
- Module name mismatch with `requires`.
- Transitive dependencies changing after a library version upgrade.
- Needed packages not being exported.
- Provider modules not being resolved or services not being discovered.
- Production module path or JVM arguments differing from the test environment.
- Two artifacts declaring the same module name or containing conflicting packages.
- Runtime modules incompatible with compiled consumer bytecode.
- Packages opened too broadly via `opens` or to the wrong target modules.
- Application depending on classpath or JDK internals no longer provided by the release runtime.

A green build only proves that the steps executed in the build succeeded. If the pipeline does not inspect the runtime image or release artifact set, it has not proven that the deployed module graph is valid.

## 3. Defining Inputs for an Audit

Before running tools, pin down the following inputs:

| Input | What to Specify |
| --- | --- |
| JDK | JDK version used for compiling and running tests |
| Application module | Main startup module |
| Module path | Directories or JARs containing named modules |
| Classpath | Libraries still running in the unnamed module, if any |
| Root modules | Startup module and modules added via `--add-modules` |
| Module limit | Whether `--limit-modules` is used |
| Module patch/upgrade | Whether `--patch-module` or `--upgrade-module-path` is used |
| Runtime flags | `--add-reads`, `--add-exports`, and `--add-opens` options |
| Service declarations | Modules declaring `uses` and `provides` |
| Artifact manifest | File list, module names, version metadata, and checksums |

Inputs must reflect the configuration that will run the release. If production adds a JVM argument or a module path directory unknown to CI, audit results will not represent production.

Save the standardized command line or launch configuration so builds remain reproducible.

## 4. Inspecting the Descriptor of Each Module Artifact

Use the `jar` tool to view the module descriptor packaged inside the artifact:

~~~shell
jar --describe-module --file build/dist/com.example.api.jar
~~~

The output helps confirm:

- Module name.
- Version metadata, if present.
- Exported packages.
- Opened packages (`opens`).
- `requires`, `uses`, and `provides`.
- Whether the module is explicit, automatic, or matches the artifact format.

Example descriptor:

~~~java
module com.example.api {
    exports com.example.api;
    exports com.example.api.spi;

    uses com.example.api.spi.AuditProvider;
}
~~~

Provider:

~~~java
module com.example.audit.provider {
    requires com.example.api;

    provides com.example.api.spi.AuditProvider
        with com.example.audit.internal.DefaultAuditProvider;
}
~~~

The consumer declares `uses` for the service it needs. The provider declares `provides` to register an implementation. These declarations must be checked alongside whether the provider is brought into the runtime graph and discovered by service loading.

Do not inspect only source `module-info.java`. Inspect the descriptor inside the final JAR, because artifacts can be generated, replaced, or repackaged in another step.

## 5. Checking Dependencies with `jdeps`

`jdeps` analyzes class and module dependencies. This tool helps find referenced modules, missing dependencies, and discrepancies between descriptors and dependencies actually used by bytecode.

### Listing Artifact Dependencies

~~~shell
jdeps --module-path build/dist --list-deps build/dist/com.example.app.jar
~~~

This command displays module dependencies detected by `jdeps` from the artifact and the provided module path.

### Printing the Module Dependency List

~~~shell
jdeps --module-path build/dist --print-module-deps build/dist/com.example.app.jar
~~~

The output is a comma-separated list of module names. This output can serve as reference data when creating a runtime image or comparing against the expected module list.

### Checking a Named Module's Descriptor

~~~shell
jdeps --module-path build/dist --check com.example.app
~~~

The `--check` option analyzes the specified module, showing its descriptor and dependencies to help uncover inconsistencies in module declarations.

If the pipeline audits multiple modules, run checks for each application module or critical module and retain results per artifact.

### Checking JDK APIs and Dependencies

You can use:

~~~shell
jdeps --module-path build/dist --api-only build/dist/com.example.app.jar
~~~

Or check usage of JDK internal APIs:

~~~shell
jdeps --jdk-internals build/dist/com.example.app.jar
~~~

`jdeps` is a static bytecode analysis tool. It cannot fully detect dependencies loaded dynamically via reflection, class names read from configuration, custom class loaders, or runtime service discovery. Dynamic dependencies must be added to the audit list and integration tests.

## 6. Validating Observable Modules and Resolution

After preparing the module path, you can ask the JVM to validate the discovered modules:

~~~shell
java --module-path build/dist --validate-modules
~~~

The `--validate-modules` option asks the JVM to validate modules in the observable configuration and exit. This is a useful check to detect module configuration errors before running the application.

Next, launch the main module and display the resolution process:

~~~shell
java \
  --module-path build/dist \
  --show-module-resolution \
  --module com.example.app/com.example.app.Main
~~~

The output helps observe:

- Which modules are resolved.
- Which dependencies are required.
- Which module sources are used during resolution.
- Which service bindings or related modules are brought into the graph by runtime configuration.

If the application needs an optional module as a root, include that exact option in the audit:

~~~shell
java \
  --module-path build/dist \
  --add-modules com.example.audit.provider \
  --show-module-resolution \
  --module com.example.app/com.example.app.Main
~~~

Do not use `ALL-MODULE-PATH` in the audit if production only resolves a specific set of modules. The audit must reproduce the actual configuration; otherwise it may validate a different graph from the one released.

## 7. Checking `requires` Relationships and Package Boundaries

A valid module graph may still fail to satisfy the application's access contract.

Check declarations:

- `requires`: module needs to read another module.
- `requires transitive`: dependency forwarded to modules reading this module.
- `requires static`: dependency needed at compile time that may be optional at runtime.
- `exports`: package exposed to other modules.
- `opens`: package opened for deep reflection.
- `uses`: module consumes a service.
- `provides`: module supplies an implementation for a service.

In particular, verify whether types in a public API come from properly declared dependencies. If a module's API exports types belonging to another dependency, the `requires` relationship may need `transitive` so consumers can use the API properly.

For `requires static`, the pipeline should determine whether that module is genuinely needed in production or only at compile time. If an optional feature is enabled at runtime while its corresponding dependency is missing, the application may fail when executing that feature.

For `opens`, verify the exact package and exact target module. Do not put a broad `--add-opens` flag into shared configuration merely to get smoke tests to pass.

## 8. Checking Service Providers and Optional Modules

`ServiceLoader` is an important part of modular applications with plugins or adapters.

Example service API:

~~~java
module com.example.audit.api {
    exports com.example.audit.api;

    uses com.example.audit.api.AuditProvider;
}
~~~

Provider:

~~~java
module com.example.audit.file {
    requires com.example.audit.api;

    provides com.example.audit.api.AuditProvider
        with com.example.audit.file.internal.FileAuditProvider;
}
~~~

A pipeline that only checks `app` and `audit.api` modules may miss the provider if the provider is not brought into the graph or is omitted from distribution artifacts.

Check across three layers:

1. Does the provider's descriptor declare `provides` for the right service type?
2. Is the provider module in the observable module set and resolved per configuration?
3. Does the runtime test actually discover the provider via `ServiceLoader`?

Test example:

~~~java
long providerCount =
    ServiceLoader.load(AuditProvider.class)
        .stream()
        .count();

if (providerCount == 0) {
    throw new IllegalStateException(
        "No AuditProvider was discovered"
    );
}
~~~

If the provider is optional, tests should reflect application policy: whether having zero providers is a valid state or a release failure. Do not force every environment to include all providers if the architecture allows selecting them by configuration.

## 9. Creating an Audit Step in CI

A pipeline can be divided into the following steps:

~~~text
Compile
  |
  v
Package modular JARs
  |
  v
Assemble release module path
  |
  v
Inspect module descriptors
  |
  v
Run jdeps analysis
  |
  v
Validate observable modules
  |
  v
Launch with production JVM arguments
  |
  v
Run module and service smoke tests
  |
  v
Generate audit evidence
  |
  v
Publish release artifact
~~~

Minimal Bash script example:

~~~shell
#!/usr/bin/env bash
set -euo pipefail

DIST="build/dist"
AUDIT="build/module-audit"
APP_MODULE="com.example.app"
MAIN_CLASS="com.example.app.Main"

mkdir -p "$AUDIT"

java -version 2> "$AUDIT/jdk-version.txt"

# Inspect each modular artifact.
for artifact in "$DIST"/*.jar; do
  name=$(basename "$artifact")
  jar --describe-module --file "$artifact" \
    > "$AUDIT/$name.module.txt"
done

# Validate the observable module set.
java --module-path "$DIST" --validate-modules \
  > "$AUDIT/validate-modules.txt" 2>&1

# Analyze application module dependencies.
jdeps --module-path "$DIST" --check "$APP_MODULE" \
  > "$AUDIT/module-check.txt" 2>&1

jdeps --module-path "$DIST" --list-deps "$DIST/$APP_MODULE.jar" \
  > "$AUDIT/module-dependencies.txt" 2>&1

# Resolve modules and run the application smoke test.
java \
  --module-path "$DIST" \
  --show-module-resolution \
  --module "$APP_MODULE/$MAIN_CLASS" \
  > "$AUDIT/runtime-resolution.txt" 2>&1
~~~

The script above illustrates the check structure. JAR names, main class, module path, and JVM arguments must be tailored to actual artifacts. If the application uses a classpath, `--add-modules`, `--add-reads`, `--add-opens`, or a custom runtime image, include that exact configuration in the audit step.

In real CI, split outputs into separate files so reviewers can easily locate causes. A failed command must stop the pipeline before publishing artifacts.

## 10. Integrating the Audit into a Gradle Pipeline

With the Gradle Java plugin, you can create a task depending on the packaged artifact. The idea is to audit the actual JAR after the `jar` task completes, rather than only running `javac` on sources.

Illustrative configuration example:

~~~groovy
tasks.register('auditModuleDescriptor') {
    dependsOn tasks.named('jar')

    doLast {
        def artifact = tasks.named('jar').get().archiveFile.get().asFile
        exec {
            commandLine 'jar',
                '--describe-module',
                '--file',
                artifact.absolutePath
        }
    }
}
~~~

Separate tasks can be added for:

- `jdeps --check` on the application module.
- `jdeps --print-module-deps` to save the dependency list.
- `java --validate-modules` on the release module path directory.
- Smoke tests run with the exact same JDK and JVM arguments as production.

For Gradle multi-project builds, gather the exact runtime artifacts of the application module and its dependencies. Do not use all JARs in the Gradle cache as the module path because the cache may contain multiple versions or artifacts not released with the application.

Audit tasks should use artifacts resolved via the runtime configuration rather than guessing from directory names or compile-time declared dependencies.

## 11. Generating Audit Evidence Tied to the Release

Audit results should be bound to the exact set of artifacts released. An evidence directory might include:

~~~text
module-audit/
├── jdk-version.txt
├── artifact-checksums.txt
├── app.module.txt
├── module-check.txt
├── module-dependencies.txt
├── validate-modules.txt
├── runtime-resolution.txt
└── smoke-test-result.txt
~~~

Record:

- Commit or source revision that produced the artifact.
- JDK vendor and version.
- Name, version metadata, and checksum of each modular JAR.
- Inspected module path or runtime image.
- Root modules and JVM arguments used.
- Descriptor, `jdeps`, validation, and smoke test results.
- Optional modules or providers enabled in each profile.

Checksums bind evidence to the exact artifact. If a JAR is replaced after the audit, the old evidence no longer proves anything for the new artifact.

SHA-256 can be used to create a manifest:

~~~shell
sha256sum build/dist/*.jar > build/module-audit/artifact-checksums.txt
~~~

On Windows, you can use `Get-FileHash` in PowerShell or the corresponding checksum tool of your CI environment.

Do not save only a log saying `"audit passed"`. Save the configuration and list of inspected modules so you can explain why a release was accepted.

## 12. What Static Audits Cannot Prove

`jdeps` and module descriptors provide a static view. They do not prove all runtime behavior.

Some dependencies may not appear explicitly in bytecode:

- Classes loaded via `Class.forName` with names read from configuration.
- Frameworks scanning packages or using reflection.
- Service providers selected by environment.
- Dynamically created module layers.
- Resources or configurations loaded by name.
- Code depending on the order or contents of a runtime image.

Therefore, the pipeline needs smoke tests and integration tests for critical execution paths. For dynamic module layers, create tests that initialize layers like production and verify the expected modules appear.

If the application supports multiple profiles, audit each profile with a different module graph. For example, a database profile, plugin profile, or batch profile may use different sets of modules.

## 13. Common Misconceptions

1. **Having a JAR in the `dist` directory means the module is resolved:** a module can be observable yet absent from the graph.
2. **Successful compilation proves the runtime graph is valid:** runtime may miss artifacts or use different JVM arguments.
3. **`jdeps` is a complete runtime test:** `jdeps` analyzes static dependencies and does not detect all dynamic loading.
4. **Module version guarantees API compatibility:** version metadata does not replace binary compatibility checks.
5. **Auditing only needs reading `module-info.java` in source:** the descriptor inside the released artifact must be inspected.
6. **`ALL-MODULE-PATH` makes the audit more thorough:** if production does not use that selector, results may not reflect the real graph.
7. **The service API resolving means the provider works:** the provider module must be verified and `ServiceLoader` invoked in runtime tests.
8. **One audit for every JDK is enough:** module behavior and JDK internal access can differ across runtime versions.
9. **Saving logs without attaching checksums is enough:** artifacts can be swapped after the audit.

## Conclusion

Auditing the module graph should be a quality gate before releasing a modular Java application. The pipeline needs to inspect artifact descriptors, analyze dependencies with `jdeps`, validate the module set, observe the resolution process, and run smoke tests with exact production configurations. Archive results along with release checksums and revisions for traceability. Static audits uncover structural issues; runtime tests confirm that critical modules, services, and features actually work in the deployment environment.