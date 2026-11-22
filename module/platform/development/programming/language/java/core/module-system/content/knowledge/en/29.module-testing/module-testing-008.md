# Testing Split Packages and Duplicate Module Names

In the Java Platform Module System (JPMS), a project may compile and run fine on the classpath yet fail when its JARs are placed on the module path. Two error categories to test early are **split packages** (multiple modules containing the same package) and **duplicate module names** (multiple artifacts identified by the same module name). Both involve dependency structure, yet their causes and detection methods differ.

Testing these scenarios before release catches conflicts caused by transitive dependencies, leftover old artifacts, automatic modules, or packaging mistakes. The goal is not only confirming the application starts successfully, but also proving the module path configuration **rejects invalid dependency combinations** and surfaces clear information to fix them.

## 1. Distinguishing the Two Conflict Types

### Split package

Suppose two JARs contain:

```text
alpha.jar
└── com/acme/shared/Alpha.class

beta.jar
└── com/acme/shared/Beta.class
```

If both artifacts are two independent named modules, both contribute classes to package `com.acme.shared`. This is a split package even if no class names collide.

The issue can surface when a consumer module reads the same-named package exported by two different modules, or when multiple modules are defined in the same class loader in a way that violates JPMS package constraints.

### Duplicate module name

Suppose:

```text
plugins/
├── formatter-v1.jar  → module com.acme.formatter
└── formatter-v2.jar  → module com.acme.formatter
```

Two different JARs are both identified as module `com.acme.formatter`. This is a **module identity** conflict. It does not depend on whether the two JARs share any package or class names.

A JAR setup could suffer from both errors, yet you should not treat them as the same problem.

| Criterion | Split package | Duplicate module name |
|---|---|---|
| Duplicated entity | Package name across multiple modules | Module name across multiple artifacts |
| Example | Two modules containing package `com.acme.shared` | Two JARs declaring `module com.acme.foo` |
| Common symptom | Consumer reads same package from two modules; conflict defining layer | Module finder reports multiple definitions or one artifact shadows another |
| Remediation | Separate packages, merge modules, remove duplicate dependency | Keep only one artifact/version per module name in the configuration |
| Fixable with `exports`/`opens`? | Does not resolve duplicate package origin | Does not resolve duplicate module names |

Do not assume that any two modules sharing a package fail immediately at module path scanning. Outcomes also depend on which modules are resolved, readability edges, exports, module path positions, and class loaders. Tests must construct the exact graph that triggers the failure.

## 2. Preparing an Isolated Fixture for Split Packages

Use a small experimental project separate from the production application. Example structure:

```text
split-package-fixture/
├── src-alpha/
│   ├── module-info.java
│   └── com/acme/shared/Alpha.java
├── src-beta/
│   ├── module-info.java
│   └── com/acme/shared/Beta.java
└── src-app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

First module:

```java
// src-alpha/module-info.java
module com.acme.alpha {
    exports com.acme.shared;
}
```

```java
// src-alpha/com/acme/shared/Alpha.java
package com.acme.shared;

public final class Alpha {
    public static String name() {
        return "alpha";
    }
}
```

Second module:

```java
// src-beta/module-info.java
module com.acme.beta {
    exports com.acme.shared;
}
```

```java
// src-beta/com/acme/shared/Beta.java
package com.acme.shared;

public final class Beta {
    public static String name() {
        return "beta";
    }
}
```

Consumer:

```java
// src-app/module-info.java
module com.acme.app {
    requires com.acme.alpha;
    requires com.acme.beta;
}
```

```java
// src-app/com/acme/app/Main.java
package com.acme.app;

import com.acme.shared.Alpha;

public class Main {
    public static void main(String[] args) {
        System.out.println(Alpha.name());
    }
}
```

Both `com.acme.alpha` and `com.acme.beta` export `com.acme.shared`, while `com.acme.app` requires reading both. This intentionally creates a package visibility conflict.

## 3. Compiling the Fixture and Confirming the Expected Failure

Compile each library module separately so they do not compete in the same compilation run:

```shell
mkdir -p out/alpha out/beta out/app mods

javac -d out/alpha \
  src-alpha/module-info.java \
  src-alpha/com/acme/shared/Alpha.java

jar --create --file mods/com.acme.alpha.jar -C out/alpha .

javac -d out/beta \
  src-beta/module-info.java \
  src-beta/com/acme/shared/Beta.java

jar --create --file mods/com.acme.beta.jar -C out/beta .
```

The example commands use Linux/macOS shell syntax. On Windows, create directories in PowerShell and run each `javac`/`jar` command on a single line.

Next, attempt to compile the consumer:

```shell
javac --module-path mods \
  -d out/app \
  src-app/module-info.java \
  src-app/com/acme/app/Main.java
```

**Expectation:** compilation fails because the consumer reads package `com.acme.shared` from both `com.acme.alpha` and `com.acme.beta`. Depending on the JDK version, the message may state the module reads the same package from two modules or that the package cannot be accessed consistently.

The failure in this fixture is the **expected outcome**, not a bug in the test suite. If the compiler unexpectedly succeeds, inspect the module path, descriptors, and whether both libraries were truly compiled as named modules.

Do not merely check for a non-zero exit code while ignoring the cause; a syntax error in the fixture also fails the command without proving split package detection.

## 4. Writing Negative Tests with Explicit Outcome Conditions

A negative test should check two things:

1. The command is rejected (non-zero exit code).
2. The diagnostic mentions the expected package/module conflict, not an unrelated error.

Shell example:

```shell
if javac --module-path mods \
    -d out/app \
    src-app/module-info.java \
    src-app/com/acme/app/Main.java \
    2> split-package-error.txt; then
  echo "FAIL: compilation unexpectedly succeeded"
  exit 1
fi

if grep -Eiq 'reads package|from both|package.*module' \
    split-package-error.txt; then
  echo "PASS: expected package conflict was detected"
else
  echo "FAIL: compilation failed for an unexpected reason"
  cat split-package-error.txt
  exit 1
fi
```

The regex phrases are examples for English output. Error messages can vary across JDKs or locales, so a long-lived test suite may configure the locale or use a pattern set suited to supported compilers.

Matching an entire exact message line, stack trace line numbers, or module ordering in output is discouraged; those details can change across JDK versions.

## 5. Creating a Duplicate Module Name Fixture

To illustrate two JARs with the **same module name**, build two different implementations that each use the descriptor:

```java
module com.acme.duplicate {
    exports com.acme.duplicate.api;
}
```

Artifact A can contain:

```java
package com.acme.duplicate.api;

public final class Version {
    public static String value() {
        return "A";
    }
}
```

Artifact B uses the same module name and package yet returns `"B"`. Package both versions into:

```text
duplicate-fixture/
└── mods/
    ├── duplicate-a.jar
    └── duplicate-b.jar
```

Compile and package the two JARs **separately**. Do not pass both source trees into one compilation and treat that as a duplicate module name test: errors then could come from source layout rather than the module finder observing two artifacts.

Run the module path validation tool:

```shell
java --module-path mods --validate-modules
```

When two artifacts with the same module name sit in **the same module-path directory** and both are observed, the module finder can report multiple definitions of `com.acme.duplicate`. This is a useful test for accidentally packaging two versions into one directory.

### Note on module path ordering

If two same-named artifacts sit in **two different module path entries**, lookup behavior can select the first definition encountered and shadow the one in a later entry rather than always raising a duplicate-name error. Example:

```shell
java --module-path "mods-v1:mods-v2" \
  --validate-modules
```

On Windows, use `;` instead of `:`. Because shadowing is possible, **do not treat a single successful `--validate-modules` run as absolute proof that all dependency artifacts have unique module names**. Inspect the input artifact list independently.

## 6. Inspecting the Actual Module Name of Each JAR

A JAR filename does not necessarily match its module name. There are three common cases:

- **Explicit module:** name taken from `module-info.class`.
- **Automatic module with `Automatic-Module-Name`:** name taken from the manifest.
- **Automatic module without an explicit name:** name derived from the filename per module system rules.

Example:

```shell
jar --describe-module --file libs/formatter-1.0.jar
jar --describe-module --file libs/formatter-2.0.jar
```

Two files with different versions can still declare the same `module com.acme.formatter`. That is usually **correct** for module identity: two versions of the same library should share the same logical name, yet **must not coexist as two competing definitions of one module in the same configuration**.

Two automatic JARs can also accidentally receive the same name after filename derivation. Therefore, do not only check for files with matching basenames; extract the exact module name as seen by the module finder.

A useful duplicate-name check must compare **module names**, not just file paths.

## 7. Inspecting Each Artifact Individually with ModuleFinder

To avoid masking by first-match rules on the module path, inspect each JAR separately with `ModuleFinder` and group by module name.

Example inspection program:

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class DuplicateModuleNames {
    public static void main(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                "Pass JAR paths to inspect"
            );
        }

        Map<String, List<Path>> byName = new TreeMap<>();

        for (String arg : args) {
            Path jar = Path.of(arg).toAbsolutePath();

            for (ModuleReference ref :
                    ModuleFinder.of(jar).findAll()) {
                String name = ref.descriptor().name();
                byName.computeIfAbsent(
                    name, key -> new ArrayList<>()
                ).add(jar);
            }
        }

        boolean foundDuplicate = false;

        for (var entry : byName.entrySet()) {
            if (entry.getValue().size() > 1) {
                foundDuplicate = true;
                System.err.println(
                    "Duplicate module: " + entry.getKey()
                );
                entry.getValue().forEach(path ->
                    System.err.println("  " + path)
                );
            }
        }

        if (foundDuplicate) {
            System.exit(1);
        }

        System.out.println("No duplicate module names");
    }
}
```

Compile with a JDK supporting the API/module syntax in the example and run with a list of JARs:

```shell
javac DuplicateModuleNames.java

java DuplicateModuleNames \
  libs/formatter-1.0.jar \
  libs/formatter-2.0.jar
```

The check creates a **separate `ModuleFinder` per JAR**, so it does not depend on which copy a shared module finder picks first. If two JARs report the same `ModuleDescriptor.name()`, the test flags a duplicate.

You can integrate this logic into a Gradle/Maven verification task, passing the JARs resolved by the build tool. If you also need to inspect modules inside JARs nested in another archive, unpack/read the actual artifacts properly before running.

## 8. Distinguishing ModuleFinder Errors and ResolutionException

JPMS has distinct phases, so errors can surface in different places:

**Module discovery:** the module finder locates modules on the module path. Multiple indistinguishable definitions of the same module name in a single source can raise `FindException`.

**Module resolution:** the module system builds the module graph from root modules and `requires` dependencies. If the graph makes a module read the same package from incompatible modules, you may get `ResolutionException`.

**Layer definition:** after resolution, the runtime defines modules in class loaders. Invalid package/class loader combinations can raise `LayerInstantiationException`.

**Compilation:** `javac` enforces module readability and package visibility checks on sources; errors can appear before runtime.

Therefore, the test suite should not catch only a single exception class. Design fixtures per target stage: compile failure, resolution failure, layer-definition failure, or artifact-name collision.

## 9. Testing Split Packages via the Configuration API

With a dedicated Java verification program, you can use `ModuleFinder` and `Configuration.resolve` to force resolution of two modules under test:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

Configuration config =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.alpha", "com.acme.beta")
    );
```

The snippet above only forces the two modules to resolve as roots; **it does not necessarily reproduce the error of a consumer reading two exports**, because no `com.acme.app` module reads both yet. To test the conflict at resolution time, include a consumer module like in the fixture or establish conflicting readability edges.

A better root example:

```java
Configuration config =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.app")
    );
```

When `com.acme.app` requires both alpha and beta and both export `com.acme.shared`, resolution can reject the graph. This allows testing at the module configuration level without running `Main`.

When writing unit tests for this, catch the resolution error at the right stage and log which package/module caused the conflict; never catch a broad `RuntimeException` and treat it as a pass.

## 10. Split Package Cases Not Immediately Detected

Two situations easily mislead a test suite:

**One module is not resolved:** two JARs contain an overlapping package yet only one module enters the runtime graph. The application may start normally. Therefore, explicitly pick roots or consumers that pull both modules into the fixture.

**Packages are not exported to the same consumer:** in some graphs, overlapping package names do not cause a readability conflict the way the fixture above does. However, if modules are defined in the same class loader, constraints may still apply during layer definition.

This explains why `java --list-modules` or scanning package names alone is not enough to declare a full graph valid. To verify JPMS behavior, test resolution and, where appropriate, create layers or run modules with the real configuration.

## 11. Split Packages in Automatic Modules

Automatic modules let legacy JARs run on the module path during migration. Yet a JAR without `module-info.class` can still contain a package that overlaps another explicit module.

Example:

```text
explicit-api.jar  → module com.acme.api
legacy-tools.jar  → automatic module legacy.tools
```

If both contain `com.acme.shared`, placing them on the module path can cause conflicts when the relevant graph resolves. Automatic modules also generally export their packages broadly, so overlapping packages easily become visible to consumers from multiple sources.

To test this, do not convert the JAR into an explicit module just to reproduce the bug. Put the actual legacy JAR onto the fixture's module path, confirm its automatic module name, and build a consumer reading both modules.

Do not use `--add-exports`, `--add-opens`, or `open module` to mask split packages. Those flags adjust access, not which artifact owns which package.

## 12. Testing with Maven and Gradle

In real builds, conflicts often come from transitive dependencies rather than directly declared JARs.

With Maven:

```shell
mvn dependency:tree
```

With Gradle:

```shell
./gradlew dependencies --configuration runtimeClasspath
```

This step identifies **which artifacts were resolved**. Next, implement these checks:

1. Collect the actual list of JARs on the runtime module path and compile module path.
2. Determine the module name of each JAR; detect duplicate names before layer creation.
3. Inspect packages inside each JAR to find package names appearing in multiple modules.
4. Run `java --validate-modules` against the corresponding module path.
5. Run compile/module-resolution tests using the application's real root modules.
6. Smoke test the application with the exact JDK/module path used for deployment.

In Gradle, you can define a custom verification task reading artifact files from resolved configurations; in Maven, you can run a check script during the verify phase. What matters is checking **resolved artifacts**, not only dependencies declared directly in build files.

## 13. Designing a CI Gate for the Module Path

A useful CI gate can split into three check types:

| Gate | Input | Pass Condition |
|---|---|---|
| Module-name uniqueness | All JARs intended for the module path | Each module name maps to only one selected artifact |
| Package ownership | Package contents of artifacts | No unintended split packages; overlapping packages investigated |
| Module resolution/run | Module path, root modules, test fixtures | Valid module configuration; app launches and uses required APIs |

Illustrative pipeline:

```text
Resolve dependencies (Maven/Gradle)
               |
               v
Collect actual modular JAR files
               |
               v
Read module names and package inventories
               |
               v
Reject unintended duplicates
               |
               v
java --validate-modules
               |
               v
Compile / resolve application root modules
               |
               v
Launch modular smoke tests
```

Run negative tests on isolated fixtures and verify the exact error type. Never put "intentionally broken" JARs onto the main build's module path and expect the rest of the pipeline to stay healthy.

## 14. How to Fix Split Packages Found by Tests

Remediation approaches in priority order:

- **Remove redundant dependencies or versions:** e.g., pulling both a monolithic uber-JAR and split modular JARs of the same library.
- **Assign package ownership to one module:** move related classes into a single module instead of scattering same-named packages.
- **Rename packages:** use distinct namespaces per module or bounded context.
- **Relocate shaded libraries:** when third-party dependency sources cannot be changed and API constraints permit.
- **Update module descriptors:** after reorganizing packages, adjust `requires` and `exports` accordingly.

For example, instead of:

```text
com.acme.alpha → com.acme.shared.Alpha
com.acme.beta  → com.acme.shared.Beta
```

refactor to:

```text
com.acme.alpha → com.acme.alpha.api.Alpha
com.acme.beta  → com.acme.beta.api.Beta
```

or create a shared API module owning `com.acme.shared` when both classes genuinely belong to the same contract.

Relocation can affect reflection, `ServiceLoader` metadata, and serialization, so update related configs and resources as well.

## 15. How to Fix Duplicate Module Names Found by Tests

A valid module name should correspond to **one selected definition** in a given deployment environment.

Common fixes:

1. Remove old JARs or unused versions.
2. Use dependency constraints/lockfiles to ensure only one version resolves.
3. Avoid adding the same artifact to the module path via two different paths.
4. If two genuinely independent libraries accidentally use the same module name, rename one module carefully and update consumers.
5. If a JAR is an automatic module, have the publisher configure a stable module name (e.g. `Automatic-Module-Name`) or switch to a properly modularized artifact.
6. Inspect the final launch command, as unexpected module path assembly by a launcher or plugin manager can cause duplicates.

Do not "fix" duplicate module names with `--add-reads`, `--add-exports`, or `--add-opens`. They do not change module identity and do not decide which artifact version gets selected.

## 16. Distinguishing These Test Failures from Other JPMS Errors

| Message/Exception | Investigation Direction |
|---|---|
| `reads package P from both M1 and M2` | Split package causing visibility conflict for consumer |
| `FindException` mentioning two module definitions | Duplicate module name in module finder source |
| `ResolutionException` | Module graph unresolvable, possibly due to package/readability |
| `LayerInstantiationException` | Class loader or package/module constraint when defining layer |
| `module not found: X` | Missing module, wrong module path, or wrong module name; do not assume duplicate |
| `package ... is not visible` | Missing `requires` or unexported package; do not assume split package |
| `InaccessibleObjectException` | Deep reflection blocked; check `opens` |
| `IllegalAccessError` | Bytecode violates runtime access permissions |

Reading the first exact error message matters more than guessing JVM flags. A closed package due to missing export is not the same as a split package across two modules.

## 17. Pre-Release Testing Checklist

- [ ] Collect the exact list of JARs actually used, including transitive dependencies.
- [ ] Determine module names via descriptors, manifests, or module finders.
- [ ] Detect duplicate module names even when JARs reside in separate module-path entries.
- [ ] Inventory packages to detect potential split packages.
- [ ] Run `java --validate-modules` against the production module path.
- [ ] Compile named modules against actual dependencies.
- [ ] Test resolution with the application's root modules or plugin layers.
- [ ] Perform negative verification using intentionally faulty fixtures.
- [ ] Do not treat every non-zero exit code as the expected failure.
- [ ] Verify behavior on the target JDK and custom runtime images when applicable.
- [ ] Never use `opens`/`exports` to mask broken module structure.
- [ ] Keep only one module definition per module name in the final configuration.

**Conclusion:** Testing split packages and duplicate module names requires two complementary checks: inspecting **package ownership** to catch repeated package names across modules, and inspecting **module identity** to catch multiple artifacts sharing one module name. Combining independent artifact scanning with real resolution/layer tests catches both overt failures and silent shadowing.