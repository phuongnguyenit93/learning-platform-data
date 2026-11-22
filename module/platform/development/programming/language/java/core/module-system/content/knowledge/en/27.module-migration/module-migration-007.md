# Maintaining Tests and Plugin Builds During Migration

When migrating a Java project from the **classpath** to the **Java Platform Module System (JPMS)**, the goal is not merely getting `module-info.java` to compile. The system must also keep its **unit tests**, **integration tests**, **plugin tests**, Maven/Gradle build tasks, and runtime plugin discovery working.

Migration should proceed step by step, using a working build pipeline as a reference baseline. If all dependencies, test runners, and plugin loaders are moved to the module path simultaneously, pinpointing root causes when errors arise becomes very difficult. A more practical approach is controlling three tracks separately: **application compilation**, **test execution**, and **plugin packaging/loading**.

## 1. Why Do Tests and Plugins Break Easily When Modularizing?

On the classpath, classes typically belong to the class loader's unnamed module. A test framework or plugin can use reflection to find constructors, call non-public methods, and scan the classpath or `META-INF/services` files.

In named modules, JPMS adds constraints:

- A module wanting to use another module's API needs **readability**, usually via `requires`.
- A package wanting other modules to access its public types needs `exports`.
- A package wanting frameworks to use **deep reflection** needs appropriate `opens`.
- A provider in a named module must be declared with `provides ... with ...` when using the module service mechanism.
- A module on the module path must be **resolved**; merely placing a JAR in a directory does not guarantee it participates in the runtime configuration.
- A package cannot arbitrarily be split across multiple named modules in the same configuration.

Therefore, the same test can pass when every JAR is on the classpath yet fail after moving core libraries onto the module path.

## 2. Classifying the Three Scopes to Keep Running

| Scope | Example | What to check |
|---|---|---|
| Application build | `javac`, Maven Compiler, Gradle Java plugin | Module path, descriptors, dependencies, module names |
| Test execution | JUnit, Mockito, integration tests | Test classpath/module path, reflection permissions, test fixtures |
| Build plugins and runtime plugins | Maven/Gradle plugins, service providers, plugin JARs | Build tool class loader, packaging metadata, `ServiceLoader`, and module layers |

"Plugin build" can refer to **plugins executing inside the build tool** such as Maven/Gradle plugins, or **plugin artifacts built by the application and loaded at runtime**. These two cases have different lifecycles.

Maven/Gradle plugins usually execute inside the build tool's own environment and do not automatically become modules read by the application. Conversely, runtime plugins using JPMS may need `uses`, `provides`, the module path, service binding, or module layers.

## 3. Setting a Pre-Migration Baseline

Before adding `module-info.java`, establish a stable build state:

1. Build the application from a clean workspace.
2. Run all existing unit tests and integration tests.
3. Package the JARs distributed by the application.
4. Run a real plugin-loading scenario.
5. Record the modules/JARs, JDK, dependencies, and build tools in use.

Example with Maven:

    mvn clean verify

Example with Gradle:

    ./gradlew clean build

If the project has custom test tasks or integration tests outside the default pipeline, include them in the baseline. Do not assume `build` or `verify` always includes every test in every project.

A useful baseline records not just "BUILD SUCCESS", but also which tests actually ran and which plugins were actually discovered and instantiated.

## 4. Migrating in Layers Rather Than All at Once

You can divide migration into steps:

**Step A — Standardize dependencies.** Identify which libraries already have explicit modules, which become automatic modules, and which remain on the classpath. Check for overlapping package names across artifacts.

**Step B — Modularize the core.** Add `module-info.java` for well-bounded API or core modules. Avoid exporting internal packages just to make all tests pass quickly.

**Step C — Keep existing tests running.** Temporarily use a test classpath configuration or add test-specific runtime options, then incrementally move toward testing inside named modules if needed.

**Step D — Migrate plugins.** Standardize service APIs, service providers, JAR packaging, and module resolution. Legacy plugins can stay on the classpath during an intermediate phase if the architecture supports it.

**Step E — Narrow exceptions.** Once tests and plugins run reliably, reduce `--add-opens`, `--add-exports`, and `--add-reads` flags that are no longer needed.

Each step should have a repeatable build/test command. Having two launch modes during the transition is reasonable as long as it is controlled and has a clear end goal.

## 5. Minimal Modular Application Example

Suppose an application has a core module:

    src/
      com.example.core/
        module-info.java
        com/example/core/api/Calculator.java
        com/example/core/internal/DefaultCalculator.java
      com.example.app/
        module-info.java
        com/example/app/Main.java

Core module:

    module com.example.core {
        exports com.example.core.api;
    }

Core API:

    package com.example.core.api;

    public interface Calculator {
        int add(int a, int b);
    }

App module:

    module com.example.app {
        requires com.example.core;
    }

Compile using module source path:

    javac --module-source-path src -d out -m com.example.core,com.example.app

Run:

    java --module-path out -m com.example.app/com.example.app.Main

Only after this step works should you adjust the test runner and plugin configurations accordingly. Do not change all build/test paths before verifying the application's module graph.

## 6. Keeping Unit Tests Running While Tests Stay on the Classpath

Many projects place tests under `src/test/java` and load them via the test framework on the classpath. Early on, you can keep tests in the unnamed module while production code becomes a named module.

This is a transitional option, not automatically equivalent to running tests under full JPMS rules.

For example, test code can call the core's public API if the package is exported:

    module com.example.core {
        exports com.example.core.api;
    }

If tests try to access private fields in an internal package, exporting the public API is not enough to permit deep reflection. The test JVM configuration may need:

    --add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED

That option opens the internal package of `com.example.core` to code in unnamed modules, such as a test framework running on the classpath.

If the test framework resides in a **named module**, `ALL-UNNAMED` does not grant it permission. In that case, the target must be the actual module name of the framework invoking reflection.

Only add these permissions to the test JVM that needs them, not necessarily to the production JVM.

## 7. When to Use --patch-module for Tests?

Some tests need access to package-private members of production code. When production code resides in a named module, placing tests in the same package name inside the unnamed module does not put them in the same runtime package.

JPMS supports `--patch-module` to inject classes/resources into a module during compilation or execution:

    --patch-module com.example.core=path/to/test-classes

The idea is to make test classes part of the patched `com.example.core` module in the test environment. This can allow same-package tests to access package-private members without exporting the package to the entire application.

However, distinguish:

- `--patch-module` alters the contents of the patched module.
- `--add-reads` adds readability between modules.
- `--add-opens` opens a package for deep reflection.
- `--add-exports` grants access to public types of a package.

If test classes are patched into a named module while JUnit or the test framework remains on the classpath, the test module may need readability to unnamed modules in the test JVM:

    --add-reads=com.example.core=ALL-UNNAMED

Only apply these flags when the test structure truly demands them. Let Maven Surefire, Gradle Test, or your test runner manage them when the tool already supports modular testing; avoid copying a generic set of flags without considering the actual module path and class loaders.

## 8. Reflection in Tests: exports Does Not Replace opens

Unit tests and frameworks may use reflection to invoke constructors or read private fields:

    Field field = target.getClass()
            .getDeclaredField("id");

    field.setAccessible(true);

If the class belongs to a package not opened to the reflecting code's module, the program may throw:

    java.lang.reflect.InaccessibleObjectException

The fix is opening the appropriate package:

    --add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED

Or, if the project intentionally allows a framework in named module `com.example.test.framework` to access it:

    opens com.example.core.internal to com.example.test.framework;

in the source module's `module-info.java`.

If this permission is solely for testing, prefer configuring it on the test JVM rather than broadening the production module contract.

Do not use `--add-opens` to fix a compile-time `package ... is not visible` error when a test imports a public type: in that case, check readability and `exports`.

## 9. Configuring Maven During Transition

With Maven, projects containing `module-info.java` are usually handled by the Maven Compiler Plugin and Maven Surefire Plugin according to module configurations appropriate for the plugin and JDK versions.

Some projects choose to temporarily keep tests running on the classpath during migration. Example Surefire configuration:

    <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <configuration>
            <useModulePath>false</useModulePath>
        </configuration>
    </plugin>

This is only **a transitional choice**: tests may run in a classpath environment without fully checking production module-path constraints.

When stricter JPMS testing is needed, Surefire can use the module path with appropriate patch/reads/opens settings for the test layout. Options depend on how tests are compiled, whether tests have their own `module-info.java`, and the plugin version.

Test-specific VM options can be passed via `argLine` where appropriate:

    <configuration>
        <argLine>
            --add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED
        </argLine>
    </configuration>

Only use this example if the reflection code actually runs in the unnamed module. Do not overwrite an existing `argLine` containing Java agent, JaCoCo, or other flags without merging them.

When operating Maven, distinguish:

- `maven-compiler-plugin`: compiles sources/modules.
- `maven-surefire-plugin`: typically runs unit tests.
- `maven-failsafe-plugin`: typically runs integration tests when configured.
- Packaging plugins: produce JARs, distributions, images, or plugin artifacts.

A build can compile cleanly while the test runner or produced JAR still needs separate adjustments.

## 10. Configuring Gradle During Transition

With Gradle and the Java plugin, you can enable module-path inference for code with module descriptors:

    plugins {
        id 'java'
    }

    java {
        modularity.inferModulePath = true
    }

Configure test execution with JUnit Platform if using JUnit Jupiter:

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }

If a test framework runs on the classpath and needs deep reflection, add test-only flags:

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
        jvmArgs(
            '--add-opens=com.example.core/com.example.core.internal=ALL-UNNAMED'
        )
    }

Depending on Gradle, JDK, source sets, and how modules are compiled, tests may need additional patch-module or module-path configuration. Do not assume `inferModulePath = true` alone automatically configures every test framework and plugin accurately.

Gradle plugins executing during the build have their own class loaders and dependencies managed by Gradle. Do not confuse Gradle's plugin classpath with the application's module path compiled/executed by Java tasks.

## 11. Separating Build-Tool Plugins from Runtime Plugins

Two types of "plugins" are often conflated during migration:

**Build-tool plugins** run inside Maven or Gradle to perform tasks like compiling, generating sources, testing, packaging, and publishing—for example, Maven Compiler/Surefire or Gradle Java/Application plugins. They depend on the build tool's API and runtime.

**Runtime plugins** are components discovered and loaded by the application at runtime, for example via `ServiceLoader` or `ModuleLayer`.

Migrating an application to JPMS does not require every build-tool plugin to have its own module-info in your project. However, plugins must support your JDK/build tool and pass the right compiler/test VM options for modular tasks.

For runtime plugins, you must manage service APIs, provider registration, the module path, or plugin class loaders. These two concerns can be handled on two separate tracks in the migration plan.

## 12. ServiceLoader Example for Preserving a Plugin Mechanism

Suppose an application supports report-export plugins.

Service interface in the API module:

    package com.example.spi;

    public interface ReportExporter {
        String format();
        byte[] export(String content);
    }

API descriptor:

    module com.example.spi {
        exports com.example.spi;
    }

A plugin provider implementing the service:

    package com.example.csv;

    import com.example.spi.ReportExporter;
    import java.nio.charset.StandardCharsets;

    public final class CsvExporter implements ReportExporter {
        public CsvExporter() {}

        @Override
        public String format() {
            return "csv";
        }

        @Override
        public byte[] export(String content) {
            return content.getBytes(StandardCharsets.UTF_8);
        }
    }

Provider descriptor:

    module com.example.csv.provider {
        requires com.example.spi;
        provides com.example.spi.ReportExporter
            with com.example.csv.CsvExporter;
    }

Application descriptor:

    module com.example.app {
        requires com.example.spi;
        uses com.example.spi.ReportExporter;
    }

Application discovering plugins:

    ServiceLoader<ReportExporter> exporters =
            ServiceLoader.load(ReportExporter.class);

    for (ReportExporter exporter : exporters) {
        System.out.println(exporter.format());
    }

This way, the app does not need `requires com.example.csv.provider;` just to call the service via `ServiceLoader`. However, the provider module must be present in the module graph examined by ServiceLoader.

When running the demo, you can add the provider to the root set:

    java --module-path mods --add-modules com.example.csv.provider -m com.example.app/com.example.app.Main

If the provider is merely placed on the module path without being resolved, provider discovery may behave unexpectedly. For plugins placed in a separate module layer, use the layer-based overload as shown next.

## 13. Differences Between Classpath and Module-Path Plugins

In legacy systems, classpath providers are usually registered via a file:

    META-INF/services/com.example.spi.ReportExporter

Contents:

    com.example.csv.CsvExporter

When packaged as a named module, provider declaration typically moves to `provides ... with ...` in `module-info.java`.

Do not delete `META-INF/services` from legacy artifacts if older classpath applications still need to read it during the transition. At the same time, avoid registering the wrong provider type or carrying multiple copies of the service API that break class identity compatibility.

Named-module providers can use a public no-arg constructor or a provider method per `ServiceLoader` rules. Classpath providers listed in `META-INF/services` must satisfy the corresponding constructor contract.

During a migration phase, you may need to maintain two packaging modes or two artifact variants, provided their scopes, dependencies, and tests are clearly managed.

## 14. ModuleLayer for Dynamic Plugins

If the application discovers plugin JARs from a directory and loads them dynamically, simply calling `ServiceLoader.load(service)` on the current class loader will not always see plugins placed in a new module layer.

With named-module plugins, you can create a separate module configuration and module layer, then look up providers via the overload taking a layer:

    ServiceLoader<ReportExporter> exporters =
            ServiceLoader.load(pluginLayer, ReportExporter.class);

This overload searches for providers in the specified layer and its ancestor layers. It fits plugin systems that manage module layer lifecycles directly.

Plugins need a module descriptor and an appropriate `provides` declaration. The module layer must be defined from a resolved configuration with an appropriate class loader strategy.

If plugins remain legacy JARs on the classpath or a separate `URLClassLoader`, you can use the overload taking a class loader:

    ServiceLoader<ReportExporter> exporters =
            ServiceLoader.load(
                ReportExporter.class,
                pluginClassLoader
            );

Choose the overload matching your actual plugin architecture; do not arbitrarily switch to `ModuleLayer` just because the application began modularizing.

## 15. Contract Testing for Plugins

An effective plugin test does more than verify the JAR builds. It needs to verify the runtime contract:

1. **API compatibility:** does the provider implement the application's exact service interface?
2. **Provider discovery:** does `ServiceLoader` find the provider in the actual deployment configuration?
3. **Construction:** can the provider be instantiated without throwing `ServiceConfigurationError`?
4. **Behavior:** does the provider return expected results for test data?
5. **Isolation:** do multiple plugins with similar package and service names avoid class-loader conflicts?
6. **Cleanup:** are `URLClassLoader` instances, resources, and plugin objects released properly?

Example minimal check:

    ServiceLoader<ReportExporter> loader =
            ServiceLoader.load(ReportExporter.class);

    boolean csvFound = loader.stream()
            .map(ServiceLoader.Provider::get)
            .anyMatch(exporter -> "csv".equals(exporter.format()));

    if (!csvFound) {
        throw new AssertionError("CSV plugin not discovered");
    }

Tests must run in the same kind of service discovery setup that production uses. A provider discovered in classpath tests may go undiscovered in a named-module runtime if the provider module is not resolved.

## 16. Structuring the Test Suite During Migration

Tests can be grouped by purpose:

| Test group | Recommended setup | Goal |
|---|---|---|
| Fast unit tests | Classpath or modular tests, depending on phase | Preserve legacy business behavior |
| Module boundary tests | Run with real module path | Verify `requires`, `exports`, `opens`, and package ownership |
| Service/Plugin tests | Launch with exact provider modules or layers | Verify discovery and provider instantiation |
| Integration tests | Production-like runtime packaging | Catch test/production differences |
| Packaging checks | Inspect modular JARs and descriptors | Verify `module-info.class`, service metadata, main class |

Do not replace all integration tests with unit tests just because compilation succeeds. Module resolution, service discovery, or reflection failures often surface only when the JVM actually boots the final module configuration.

## 17. CI: Maintaining Both Old and New Build Lanes

During migration, you can run two lanes in CI:

**Legacy lane:** builds/tests with the current classpath configuration, ensuring existing behavior does not break.

**JPMS lane:** compiles and runs the application/tests or plugins on the module path, verifying module boundaries and service discovery.

Example for a project with a predefined Maven `jpms` profile:

    mvn clean verify

    mvn -Pjpms clean verify

Note: `-Pjpms` is only meaningful if the project actually defines a `jpms` profile in its POM or Maven configuration. This illustrates a two-lane model, not a built-in default Maven profile.

With Gradle, you can create tasks or properties to select the right configuration, then run both in CI. Regardless of build tool, both lanes should run on the JDK/version matching the deployment target.

After each migration step, update your checklist based on actual failures rather than disabling failing tests en masse. Disabling tests or skipping test suites destroys evidence that migration preserves behavior.

## 18. Diagnosing Common Errors

| Error/symptom | Common cause | Remediation |
|---|---|---|
| `module not found` or `FindException` | Module path missing JAR, wrong module name | Check artifact, descriptor, module path |
| `package ... is not visible` | Missing readability or unexported package | Check `requires`, `exports` |
| `InaccessibleObjectException` | Test/framework accesses private member in an unopened package | Check reflecting module, use `opens` or `--add-opens` appropriately |
| `ServiceConfigurationError` | Invalid provider declaration or instantiation failure | Check `provides`, `META-INF/services`, constructor/provider method |
| Tests not discovered | Mismatched test runner/source set/module path | Check test plugin, test runtime, test engine |
| Plugin JAR builds cleanly but is not loaded | Provider module unresolved or wrong layer | Check root modules, `ServiceLoader` overload, plugin layer |
| `ClassCastException` using plugin | Service API loaded by multiple class loaders | Share API via parent loader or unify loader setup |
| Split package / resolution conflict | Multiple named modules contain the same package | Consolidate package into one module or rename packages by responsibility |

Do not use `--add-opens` to fix a genuinely missing class, and do not use `--add-exports` as a substitute for `provides` in ServiceLoader. Each JPMS mechanism solves a distinct category of problem.

## 19. Reducing Reliance on Workarounds Over Time

Options such as `--add-reads`, `--add-exports`, `--add-opens`, and `--patch-module` can be helpful during transition. However, document them alongside their rationale and where they apply.

One way to manage them is tracking:

- The module/package being opened or granted readability.
- The test framework or plugin requiring that access.
- Whether it applies only to the test JVM or also the production JVM.
- Which code or dependency will be updated to remove the workaround.
- Which test confirms the flag can be dropped in the future.

When upgrading build tools, test frameworks, or plugins, try removing unneeded flags step by step. Do not open all packages of a module just to make a single test pass.

## 20. Common Misconceptions

- **Assuming adding `module-info.java` completes migration.** Runtime packaging, test runners, and plugin discovery still require verification.
- **Assuming tests passing on the classpath prove module boundaries are right.** Classpath tests do not necessarily enforce the same access mechanisms as the production module path.
- **Assuming `--add-opens` and `--add-exports` are the same.** One serves deep reflection, while the other serves public type access.
- **Assuming build-tool plugins and runtime plugins are identical.** Maven/Gradle plugins run inside the build tool, whereas runtime plugins are loaded by the application.
- **Assuming a plugin JAR on the module path is automatically discovered by ServiceLoader.** Provider modules must be resolved into the effective configuration or loaded via an appropriate layer.
- **Assuming a service API with the same name in two loaders is the same type.** Class identity also depends on the defining class loader.
- **Assuming `--patch-module` alone suffices for all tests.** Test configuration also depends on readability, the framework's classpath/module path, and required access levels.
- **Assuming the application's JVM configuration applies to the test JVM.** Each JVM has its own VM options.
- **Assuming you can skip all failing tests to speed up migration.** Doing so removes the mechanism that catches regressions when moving to JPMS.

## Takeaways

- Maintain **compilation, testing, plugin builds, and runtime discovery** as separate tracks requiring verification during migration.
- You can keep a stable classpath lane alongside a JPMS lane, then gradually phase out reliance on legacy setups.
- Tests using reflection may need `--add-opens`; tests sharing a package with production code may need `--patch-module` depending on layout.
- With Maven/Gradle, distinguish build-executing plugins from the application's module path.
- Runtime plugins via `ServiceLoader` must have proper provider metadata, consistent class identity, and properly resolved modules/layers.
- Do not treat a green compile as sufficient: test discovery, plugin discovery, and packaging must run in a production-like configuration.
- Permission-widening flags should be narrowly scoped, clearly justified, and removed once architectural migration finishes.

As you move incrementally toward JPMS, the goal is keeping tests and plugins working continuously while narrowing legacy dependency boundaries. Designing a two-lane build, explicitly managing module path/classpath, and directly testing ServiceLoader flows makes the transition controllable, recoverable, and completable without losing system behavior.
