# Supporting Module Migration with jdeps

## Objectives

After this lesson, you will be able to use `jdeps` to prepare and perform a migration from a classpath-based Java application to the Java Platform Module System (JPMS); inventory dependencies; detect JDK internal APIs and missing dependencies; generate a draft `module-info.java`; understand the role of unnamed modules and automatic modules during the transition phase; design `requires`, `exports`, `opens`, `uses`, and `provides` directives; handle split packages, reflection, and service providers; and verify the module graph after migration.

## 1. What Is Module Migration?

**Module migration** is the process of transitioning Java applications and libraries from the traditional classpath model to the JPMS named module model introduced in Java 9.

In the classpath model, JARs are typically loaded into the class loader's unnamed module. Code on the classpath can access public types found by the class loader, and encapsulation boundaries rely primarily on packages, the classpath, and project conventions.

In JPMS, each explicit named module has a module descriptor, typically a `module-info.java` file in source and `module-info.class` in the artifact. The descriptor declares:

- Which modules the module depends on using `requires`.
- Which packages are exposed publicly using `exports`.
- Which packages are opened for reflection using `opens`.
- Which services the module consumes using `uses`.
- Which service providers the module supplies using `provides ... with ...`.

The module system introduces two key concepts: **readability** (whether a module can read another module) and **accessibility** (whether a package/type can be accessed across module boundaries).

Migration is more than just adding `module-info.java`. You must understand actual dependencies, public APIs, reflection, service loading, package ownership, third-party libraries, and how the application is deployed.

## 2. How Does jdeps Support Migration?

`jdeps` is a bytecode analysis tool. It helps answer critical questions before and during migration:

| Question | Tool or option |
|---|---|
| Which packages/classes does the application reference? | `-verbose:package`, `-verbose:class` |
| Which JDK modules are required? | `--list-deps`, `--print-module-deps` |
| Does it depend on JDK internal APIs? | `--jdk-internals` |
| Are there any unresolved dependencies? | `--missing-deps` |
| What module descriptor can a legacy JAR start with? | `--generate-module-info` |
| Does a library relying on deep reflection need an open module? | `--generate-open-module` |
| What dependencies does an existing module descriptor have? | `--check` |
| Which packages are exposed by the public API? | `--api-only` |
| Which artifacts reverse-depend on a module/package? | `--inverse` combined with `--require` or `--package` |

`jdeps` helps map dependencies and generate draft descriptors. It does not automatically convert all source code into modules, design APIs for you, identify every reflection requirement with certainty, or guarantee that the application will work after migration.

Treat `jdeps` results as evidence for making design decisions, then verify with the compiler, module resolver, and runtime tests.

## 3. Understanding the Three States During Transition

JPMS supports mixing legacy and new code through unnamed modules, automatic modules, and explicit named modules.

### Unnamed Module: JARs on the Classpath

Classes loaded from the classpath belong to the unnamed module of the corresponding class loader. An unnamed module reads all observable modules, and its packages are treated as exported and open.

Key point: an explicit named module cannot use `requires` to read an unnamed module. Therefore, if a library exists only on the classpath and is not an automatic module, code in a named module cannot declare a normal dependency on that library.

This is why dependent libraries usually need to be moved onto the module path or converted into named/automatic modules before modularizing the application.

### Automatic Module: JAR Without module-info on the Module Path

A JAR without `module-info.class` placed on the module path becomes an automatic module. It has a module name and is handled by the module system with migration-compatibility rules:

- An automatic module reads all modules in the configuration.
- When created in the JVM, it also reads unnamed modules.
- All packages of an automatic module are treated as exported and open.
- An automatic module's descriptor does not explicitly declare `requires`, `exports`, `opens`, `uses`, or `provides` (aside from the foundational `java.base` relationship in the descriptor model).

The automatic module name is taken from the `Automatic-Module-Name` attribute in the manifest if present; otherwise, the name is derived from the JAR filename. As a result, renaming the file can change the module name.

Check a JAR's module name and status:

~~~bash
jar --describe-module --file lib/legacy-library.jar
~~~

If you control a library but cannot add `module-info.java` yet, you can ask the publisher to set a stable `Automatic-Module-Name` in the manifest. This is a useful bridge, though you should still move to an explicit module when the library is ready.

### Explicit Named Module: Module with a Descriptor

An explicit module has `module-info.java`/`module-info.class`. It only reads modules declared via `requires` (along with inferred readability edges), only exposes packages declared with `exports`, and only opens packages declared with `opens` or via `open module`.

This is the usual target state because dependencies and API boundaries are explicitly declared.

### Quick Comparison

| Characteristic | Unnamed module | Automatic module | Explicit module |
|---|---|---|---|
| Common location | Classpath | Module path, JAR without descriptor | Module path, with `module-info` |
| Module name | No name | Derived from manifest/JAR name | Declared in `module-info` |
| Reads other modules | Reads all observable modules | Reads all modules in configuration | According to `requires` and module resolution |
| Exported packages | All packages | All packages at runtime | Only packages declared in `exports` |
| Open packages | All packages | All packages at runtime | Only packages declared in `opens`, unless `open module` |
| Migration role | Running legacy code | Bridge for legacy libraries | Clear target state |

Automatic modules are convenient for migration, but they should not become a long-term API contract. When a library switches to an explicit module, its module name and exported packages can change; the JLS recommends that compilers emit a warning when `requires` targets an automatic module, especially with `requires transitive`.

## 4. Phased Migration Workflow

A practical roadmap usually starts by keeping the application running, then modularizing dependencies layer by layer.

### Phase 1: Establish a Baseline

Before making module changes:

1. Record the current JDK, target JDK, build tool, and dependency versions.
2. Run existing tests and save the results.
3. Document how the application starts, its classpath, JVM flags, and system properties.
4. List libraries, plugins, JDBC drivers, logging providers, serializers, and frameworks.
5. Note features using reflection, `ServiceLoader`, JNI/JNA, or dynamic class loading by name.

Migration is an iterative process. Running the application on the target JDK before recompiling can help uncover runtime issues and libraries that need upgrading. Afterward, update libraries, compile, and run `jdeps` to gather additional information.

### Phase 2: Bytecode and Dependency Analysis

Run basic commands on the built artifact:

~~~bash
jdeps -summary app.jar
jdeps -verbose:package app.jar
jdeps --missing-deps --class-path "lib/*" app.jar
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

- `-summary` gives a high-level overview.
- `-verbose:package` helps reveal relationships between packages.
- `--missing-deps` finds unresolved dependencies.
- `--jdk-internals` finds references to JDK internal APIs.

If you need to know which dependencies appear in a library's public/protected API:

~~~bash
jdeps --api-only --verbose:package library.jar
~~~

API-only analysis focuses on types appearing in public/protected signatures of public classes, such as field types, parameters, return types, and checked exceptions. The output helps identify which dependencies may need `requires transitive` when converting the library into a module.

### Phase 3: Move Dependencies to the Module Path

Place third-party libraries on the module path to observe how the module system sees them:

~~~bash
jdeps --module-path "mods:lib" --list-deps app.jar
~~~

On Windows, use a semicolon to separate the module path:

~~~powershell
jdeps --module-path "mods;lib" --list-deps app.jar
~~~

Use `jar --describe-module` to see whether each JAR is an explicit module or an automatic module, and what module name the compiler/runtime will use.

At this stage, the application can still run on the classpath while dependencies are checked on the module path. Once you begin converting the application into a named module, every dependency it needs to read must be present as an observable, resolvable module.

### Phase 4: Modularize Foundational Libraries First

It is usually best to convert libraries with the fewest dependencies first, then upper-layer libraries, and finally the application itself.

For JARs without a descriptor, `jdeps` can generate a draft `module-info.java`:

~~~bash
jdeps --generate-module-info build/generated-modules lib/legacy-library.jar
~~~

If a library relies on deep reflection across many packages and needs an open descriptor initially, you can try:

~~~bash
jdeps --generate-open-module build/generated-open-modules lib/legacy-library.jar
~~~

These two commands analyze the specified JARs and generate `module-info.java` in the target directory. Do not combine `--class-path` or `--dot-output` with these generate options.

Generated files are drafts. Review the module name, `requires`, `exports`, packages, services, and reflection behavior before using them in the official build.

### Phase 5: Convert the Application into an Explicit Module

Once required dependencies can be placed on the module path, create `module-info.java` for the application. Declare `requires` for the API modules that the source actually uses; export application packages only when other modules need to call those APIs.

Compile and run on the module path, then verify the module graph with `jdeps --check`.

### Phase 6: Remove Bridge Options

During migration, you may temporarily use `--add-reads`, `--add-exports`, or `--add-opens` for diagnostics or compatibility. Record each option, the modules/packages involved, and the reason.

Once module descriptors and code are properly fixed, remove each option and re-run tests. The goal is a descriptor that accurately represents dependencies and access boundaries, not maintaining a permanent list of special flags.

## 5. Generating and Reviewing module-info.java with jdeps

### --generate-module-info

Syntax:

~~~bash
jdeps --generate-module-info output-dir library.jar
~~~

`jdeps` analyzes the JAR and creates `module-info.java` based on the dependencies and packages it observes. You can use the output as a starting point for converting the library into an explicit module.

For example, after running the command, inspect the generated `module-info.java` in the output directory. The actual directory structure and module name depend on the module name derived from the JAR.

Review the following points:

- Is the module name stable and aligned with naming conventions?
- Does `requires` match direct dependencies accurately?
- Which packages are truly public API and need `exports`?
- Are any internal packages being exported too broadly?
- Does the public API expose types from other modules?
- Are there any undeclared service providers or service consumers?
- Which packages do frameworks need reflection access to?
- Is any package split across another JAR/module?
- Were any dependencies missing during `jdeps` analysis?

The `-q` or `--quiet` option can suppress missing dependency notices in `generate-module-info` output. Avoid quiet mode during initial investigation because missing dependencies are information that needs to be addressed.

### --generate-open-module

Syntax:

~~~bash
jdeps --generate-open-module output-dir library.jar
~~~

This command generates an `open module` descriptor. An open module allows deep reflection on all of its packages at runtime.

This can serve as a bridge for libraries heavily dependent on reflection, but its scope is broader than necessary. If you know a framework only needs access to certain packages, use `opens package to framework.module` in the final descriptor instead of keeping an open module.

### jdeps Does Not Decide Module Design

Bytecode analysis can find type dependencies, but it cannot determine which packages should become public API, which packages are implementation-only, which services are selected dynamically, or which packages a framework needs opened for reflection.

Therefore, `module-info.java` generated by `jdeps` must be reviewed alongside source code, public APIs, framework documentation, and runtime tests.

## 6. Designing Directives in module-info.java

### requires

Declares that the current module depends on another module:

~~~java
module com.example.orders {
    requires com.example.customer.api;
    requires java.sql;
}
~~~

Use `requires` for dependencies that the current module's code directly uses. Do not add `requires` just because a module happens to be on the module path.

### requires transitive

If a module's public API uses types from another module in public/protected signatures, consumers of that module may need to read that dependency. In that case, consider `requires transitive`:

~~~java
module com.example.orders.api {
    requires transitive com.example.customer.api;
    exports com.example.orders.api;
}
~~~

Do not use `transitive` for every implementation dependency. It extends readability to consumers and can complicate the dependency graph.

Combine `jdeps --api-only` with a review of public signatures to find dependencies exposed through the API.

### requires static

`requires static` declares a dependency required at compile time that may be absent at runtime:

~~~java
module com.example.report {
    requires static java.compiler;
}
~~~

Use it only when the application can genuinely run without that module. If code accesses types or invokes functionality from the module at runtime, the dependency must still be present when that code path executes.

### exports

`exports` exposes a package so other modules can access its public types:

~~~java
module com.example.customer.api {
    exports com.example.customer.api;
}
~~~

Do not export an implementation package simply because `jdeps` sees a dependency on it. Referenced dependencies and public APIs are two different concepts.

You can use a qualified export to grant access only to specific modules:

~~~java
exports com.example.customer.internal to com.example.customer.test;
~~~

Use qualified exports when there is a clear architectural reason, such as supporting a test module or a specific integration module.

### opens

`opens` allows deep reflection into a package:

~~~java
module com.example.orders {
    opens com.example.orders.model to com.example.json;
}
~~~

Serialization, dependency injection, ORM, or binding frameworks may need `opens` to access non-public members via reflection.

`exports` does not replace `opens`: `exports` allows access to public types/members under standard Java rules; `opens` grants deep reflection permissions. Open only the packages that the framework actually needs.

### uses and provides

If a module looks up services via `ServiceLoader`, declare `uses`:

~~~java
uses com.example.codec.spi.Codec;
~~~

If a module supplies an implementation:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.Utf8Codec;
~~~

`jdeps` cannot fully infer all service-loading decisions from ordinary class references alone. Check `META-INF/services` files, `ServiceLoader.load`, JDBC drivers, security providers, logging providers, and plugin systems during migration.

## 7. Automatic Modules and Stable Module Names

Automatic modules are a very useful compatibility mechanism when third-party dependencies do not yet have `module-info.class`.

For example, if `lib/legacy-json-2.4.0.jar` is on the module path, the module name may be derived from the JAR filename. If the publisher sets the manifest attribute:

~~~text
Automatic-Module-Name: com.example.legacy.json
~~~

then the automatic module name is stably determined by this attribute.

Check the module name:

~~~bash
jar --describe-module --file lib/legacy-json-2.4.0.jar
~~~

In your module descriptor, you can temporarily declare:

~~~java
module com.example.app {
    requires com.example.legacy.json;
}
~~~

Notes:

- A module name derived from a filename can change when the artifact is renamed or re-versioned.
- When a library adds `module-info.java`, its module name and list of exported packages may change.
- Compilers may warn when `requires` points to an automatic module.
- Automatic modules do not provide narrow `exports`/`opens` boundaries like explicit modules.
- Avoid letting a library's long-term public API depend on an automatic module name if possible.

If you publish a library, announce a stable module name and a plan to transition to an explicit module. If you are a consumer, check dependency release notes before upgrading major/minor versions.

## 8. Resolving Split Packages Before Migration

A **split package** occurs when multiple artifacts/modules contain classes in the same package. For example:

- `legacy-core.jar` contains `com.example.shared.Config`.
- `legacy-util.jar` also contains `com.example.shared.Helper`.

On the classpath, two JARs can contribute classes to the same package. When moving to named modules, package ownership and module readability are strictly enforced; split packages can cause compilation, resolution, or module layer errors.

How to handle them:

1. Use `jdeps -verbose:package` to detect package relationships across JARs.
2. Use `jar --describe-module` to inspect the packages contained in each module.
3. Determine which artifact owns the package and which APIs are actually needed.
4. If possible, merge the related classes into a single module.
5. Or relocate the package through a controlled build/shading process, updating all references and resources.
6. If it cannot be fixed immediately, keep the involved JARs on the classpath during a transition phase before modularizing components that depend on them.

Do not create two explicit modules owning the same package just to preserve legacy JAR layout. The module system requires clear package/module boundaries.

## 9. Reflection and Bridge Options in Migration

An application may compile successfully yet fail at runtime when a framework accesses non-public fields/methods via reflection.

Distinguish between the options:

| Option | Effect | Common use case |
|---|---|---|
| `--add-reads` | Adds a readability edge between two modules | A module temporarily needs to read another module |
| `--add-exports` | Exports a source module's package to a target module | Accessing public types in a non-exported package |
| `--add-opens` | Opens a source module's package for deep reflection from a target | Frameworks needing access to non-public members |
| `open module` | Opens all packages of a module for deep reflection | Legacy libraries relying on broad reflection |

Example runtime bridge for classpath code:

~~~bash
java --add-opens com.example.app/com.example.app.model=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Example exporting a package to a specific module:

~~~bash
java --add-exports java.management/sun.management=com.example.monitor -m com.example.monitor/com.example.monitor.Main
~~~

These options alter access permissions at runtime (and some have compiler variants). They can keep an application running during migration, but they do not turn internal APIs into supported APIs and do not replace a proper descriptor.

Good practice is to document each bridge option, identify the framework/module needing that permission, fix the code or module descriptor, and remove the option once tests pass.

## 10. Checking JDK Internal APIs When Upgrading JDK and Modules

JDK internal APIs are not stably supported Java SE APIs. For example, `sun.*` or `com.sun.*` packages may change or be more strongly encapsulated across releases.

Run:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

`jdeps` can identify classes referencing internal APIs and suggest replacement APIs when known.

For example, if code uses `sun.misc.BASE64Encoder`, it can be replaced with `java.util.Base64`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64Example {
    public static void main(String[] args) {
        String input = "Java";
        String encoded = Base64.getEncoder().encodeToString(
                input.getBytes(StandardCharsets.UTF_8));
        System.out.println(encoded);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -d out src/Base64Example.java
java -cp out Base64Example
~~~

Exact output:

~~~text
SmF2YQ==
~~~

Do not keep internal API dependencies by permanently adding `--add-exports` or `--add-opens`. Prefer public, documented, and supported APIs.

## 11. Hands-On Example: Converting Two Parts of an Application into Named Modules

This example creates two modules: a library providing an API and an application consuming that API.

### Source Structure

~~~text
project/
└── src/
    ├── com.example.library/
    │   ├── module-info.java
    │   └── com/example/library/api/MessageFormatter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### Library Module

File `src/com.example.library/module-info.java`:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

File `src/com.example.library/com/example/library/api/MessageFormatter.java`:

~~~java
package com.example.library.api;

public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

This module only exports the API package. Consumers cannot access internal packages unless they are exported.

### Application Module

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.library.api.MessageFormatter;

public class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = new MessageFormatter();
        System.out.println(formatter.format("JPMS"));
        System.out.println("module-migration-ok");
    }
}
~~~

### Compiling Modules

Run from the `project` directory with JDK 17 or later:

~~~bash
javac --module-source-path src -d mods -m com.example.library,com.example.app
~~~

The compiler locates `module-info.java` in each module directory, resolves `requires`, and compiles the specified modules.

### Analyzing the Module Graph

~~~bash
jdeps --module-path mods --module com.example.app --list-deps
~~~

Verify the descriptor and dependency graph:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

The output should show that `app` depends on `library` and `java.base`. If there are redundant dependencies or incorrect module descriptors, review the output before proceeding.

### Running on the Module Path

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Exact output:

~~~text
Hello, JPMS
module-migration-ok
~~~

This is a minimal migration example: the application reads the API via `requires` and an exported package. In real projects, add services, reflection, resources, test modules, and third-party dependencies to the module graph as actually needed.

## 12. Verifying Modules After Migration

After adding module descriptors, run the following commands:

### View Module Dependencies

~~~bash
jdeps --module-path mods --module com.example.app --list-deps
~~~

### Check Module Graph and Qualified Exports

~~~bash
jdeps --module-path mods --check com.example.app
~~~

`--check` prints the module descriptor, analyzed dependencies, and the graph after transitive reduction; it also identifies unused qualified exports.

### Inspect the Module Descriptor in a JAR

~~~bash
jar --describe-module --file build/com.example.app.jar
~~~

Confirm that the module name, `requires`, `exports`, `opens`, `uses`, and `provides` match the design.

### Show Module Resolution Process

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

This command shows which modules are resolved at application startup. It is useful when a dependency is not found or a provider module is not included in the configuration.

### Find Missing Dependencies

~~~bash
jdeps --missing-deps --module-path mods --class-path "lib/*" app.jar
~~~

Compare the classpath and module path against the actual build. A missing dependency in analysis may be caused by incomplete inputs rather than a bug in the source code.

## 13. Service Providers in Migration

A legacy library may register a provider via a file:

~~~text
META-INF/services/com.example.codec.spi.Codec
~~~

When moving to explicit modules, declare service consumers and providers in the module descriptor:

Consumer:

~~~java
uses com.example.codec.spi.Codec;
~~~

Provider:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.impl.Utf8Codec;
~~~

If the application is packaged into a runtime image with `jlink`, check service binding. Depending on the architecture, `--bind-services` may be needed to include provider modules in the image.

Do not assume `jdeps` will automatically generate complete `uses`/`provides` directives from class references alone. Check service configuration files, JDBC drivers, security providers, logging implementations, and plugin registries.

## 14. Functional Testing for Migration

Once the project compiles on the module path, run the following tests:

| Area | What to verify |
|---|---|
| Startup | Main module/class and launcher work properly |
| Class loading | No `ClassNotFoundException` or `NoClassDefFoundError` |
| API access | Consumers only use exported packages |
| Reflection | ORM, JSON binding, DI, and serializers access the right `opens` packages |
| ServiceLoader | All required providers are discovered and instantiated |
| Resource | Properties, `ResourceBundle`, templates, and config files are found |
| Serialization | Reading/writing old and new data remains compatible |
| Native code | JNI/JNA loads the right libraries on target OS/architecture |
| Security | TLS, certificates, and security providers work |
| Test framework | Test modules, annotation processors, and build plugins still work |
| Packaging | JAR, module path, `jlink`/`jpackage`, and launcher are properly configured |
| Compatibility | API behavior and business results match the baseline |

Run tests on the actual module path. A test suite that still runs on the classpath does not prove that explicit modules are configured correctly.

## 15. Common Migration Errors

### Module Not Found

**Symptom:** The compiler or launcher reports `module not found`.

**Cause:** Missing JAR on the module path, wrong module name, or unresolved dependency.

**Resolution:** Use `jar --describe-module` to confirm the module name; check the module path and `requires`.

### Package Not Exported

**Symptom:** The compiler reports that a package is not exported or a type is not accessible.

**Cause:** The module contains the package but does not export it to the consumer.

**Resolution:** Add `exports` only if the package is genuinely public API; if it is an implementation package, update the consumer to use the public API.

### Framework Cannot Use Reflection

**Symptom:** `InaccessibleObjectException` or member access errors in ORM/serializer/DI frameworks.

**Cause:** The package has not been opened (`opens`) to the framework module.

**Resolution:** Add `opens package to framework.module`; use `--add-opens` temporarily to confirm the cause, then move it into the module descriptor as appropriate.

### Split Package

**Symptom:** Errors stating a package belongs to multiple modules, or module resolution fails.

**Cause:** Multiple JARs/modules contain classes in the same package.

**Resolution:** Consolidate package ownership, relocate classes, or keep the dependencies on the classpath during a transition phase.

### Automatic Module Name Changed

**Symptom:** A `requires` module name is no longer found after updating a library.

**Cause:** The module name was derived from the JAR filename, or the library changed its descriptor.

**Resolution:** Use a stable `Automatic-Module-Name` when possible; update `requires` to the module name published by the maintainer; prefer explicit modules.

### ServiceLoader Cannot Find Provider

**Symptom:** Empty provider list or `ServiceConfigurationError`.

**Cause:** Missing `uses`/`provides`, provider module not resolved, or service metadata not migrated.

**Resolution:** Check `META-INF/services`, module descriptors, module path, and service binding.

### jdeps Reports No Missing Dependencies, Yet Runtime Fails

**Symptom:** `jdeps` reports no errors, but the application fails when using plugins or reflection.

**Cause:** Dependencies are loaded dynamically by name, reflection, configuration, or native libraries.

**Resolution:** Audit frameworks, resources, service providers, and native dependencies; add integration tests for each code path.

### Keeping Too Many --add-opens or --add-exports Flags

**Symptom:** The application only runs with a long list of flags.

**Cause:** Migration is incomplete, or frameworks still rely on implementation details.

**Resolution:** Identify each flag, upgrade frameworks, fix module descriptors, and remove flags in batches.

## 16. Recommended Migration Strategy

A safe strategy typically includes:

1. Run the application and tests on the target JDK before making architectural changes.
2. Update build tools and third-party libraries.
3. Run `jdeps` across the entire application and its dependencies.
4. Address JDK internal APIs and missing dependencies.
5. Identify automatic module names, split packages, services, and reflection usage.
6. Modularize foundational libraries first; use automatic modules as a time-boxed bridge.
7. Generate and review `module-info.java` with `jdeps` where appropriate.
8. Modularize the application, declaring `requires`/`exports`/`opens`/`uses`/`provides`.
9. Compile, run, and test on the module path.
10. Use `jdeps --check` and `java --show-module-resolution` to verify the graph.
11. Gradually remove temporary `--add-reads`, `--add-exports`, and `--add-opens` flags.
12. Create a runtime image only after the module graph and integration tests are stable.
13. Save the module list, test results, and build commands so the migration is reproducible.

If a library cannot be modularized yet, you can keep it as an automatic module during the transition phase. Document the owner, version, and plan to switch to an explicit module; avoid letting a filename-derived module name become a long-term public dependency.

## 17. Limitations of jdeps in Migration

`jdeps` analyzes static bytecode references. It cannot guarantee finding all dependencies in the following cases:

- Reflection or `Class.forName` with class names loaded from configuration.
- Dynamically selected `ServiceLoader`, plugins, or providers.
- Frameworks that scan packages/modules on their own.
- Resource bundles, templates, properties files, and metadata.
- JNI/JNA and OS native libraries.
- Dynamically generated classes or classes loaded over the network.
- File, network, process access, and environment configuration.

`jdeps` also does not decide which packages are public API, which packages should be opened with `opens`, which services need `provides`, or which dependencies have business significance.

Therefore, migration requires combining static analysis, architectural review, descriptor checks, module-path testing, and integration tests in a production-like environment.

## 18. Pre-Completion Migration Checklist

- [ ] Recorded baseline JDK, build tool, dependencies, and tests.
- [ ] Ran `jdeps` on the app and all relevant libraries.
- [ ] Resolved `--missing-deps` findings.
- [ ] Resolved `--jdk-internals` findings.
- [ ] Checked public API dependencies with `--api-only`.
- [ ] Confirmed module names of automatic modules.
- [ ] Checked for split packages.
- [ ] Reviewed `module-info.java` generated by `jdeps`.
- [ ] `requires` includes only necessary dependencies.
- [ ] `requires transitive` is used only when the public API exposes the dependency.
- [ ] `exports` exposes only necessary packages.
- [ ] `opens` opens only packages requiring deep reflection.
- [ ] `uses`/`provides` accurately reflect service contracts.
- [ ] Verified the module graph with `jdeps --check`.
- [ ] Ran the application and tests on the module path.
- [ ] Tested reflection, service loading, resources, and native libraries.
- [ ] Removed bridge flags that are no longer needed.
- [ ] Verified packaging and runtime image if applicable.
- [ ] Saved test results and module descriptors in build/release artifacts.

## 19. Official References

- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — dependency analysis, `--api-only`, `--jdk-internals`, `--generate-module-info`, `--generate-open-module`, `--check`, and `--missing-deps`.
- [Java Language Specification, Java SE 26 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html) — explicit, automatic, and unnamed modules; `requires`, `exports`, `opens`, `uses`, and `provides`.
- [ModuleDescriptor API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html) — representation of module descriptors, automatic modules, exports, opens, and service metadata.
- [Oracle JDK Migration Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/index.html) — migration preparation workflow, updating libraries, compiling, and using `jdeps`.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — module path, module resolution, `--add-reads`, and `--add-exports`.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — runtime module options, `--add-reads`, `--add-exports`, and `--add-opens`.
- [The jar Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html) — inspecting module descriptors with `jar --describe-module`.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — JPMS design and migration mechanisms.

`jdeps` supports migration by clarifying dependencies, uncovering risks, and generating draft module descriptors. Migration succeeds when module boundaries accurately reflect the application's APIs, services, and reflection needs, and all tests run on the module path without temporary bridge flags.
