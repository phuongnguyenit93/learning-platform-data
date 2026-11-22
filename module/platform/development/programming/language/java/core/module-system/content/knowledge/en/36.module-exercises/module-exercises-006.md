# Using jdeps to Migrate a Classpath Application to a Module Graph

## 1. Migration Objectives

Java applications running on the classpath often depend on many JARs, yet those dependencies are not declared in module descriptors. When migrating to the Java Platform Module System (JPMS), you need to identify:

- Which modules/packages the application and each library depend on.
- Which JARs are already explicit modules, which are automatic modules, and which remain non-modular.
- Which `requires`, `exports`, `uses`, and `provides` directives the module descriptors need.
- Whether there are split packages, missing dependencies, or usage of JDK internal APIs.
- Which dynamic dependencies cannot be inferred from bytecode alone.

The `jdeps` tool analyzes static dependencies of class files and JARs, helping build an initial picture of the module graph. It does not automatically convert the entire application into a complete modular system. Developers still must design module boundaries, verify runtime dependencies, and test the application after migration.

## 2. Preparing the input

Suppose the legacy application has the structure:

```text
legacy-app/
├── app.jar
├── lib/
│   ├── customer-api.jar
│   ├── json-engine.jar
│   └── logging.jar
└── config/
    └── application.properties
```

The application is run using the classpath:

```bash
java -cp "app.jar:lib/*" com.acme.app.Main
```

On Windows, the classpath entry separator is a semicolon:

```powershell
java -cp "app.jar;lib/*" com.acme.app.Main
```

Before analyzing, gather the exact JARs deployed in the real environment. Do not analyze only `app.jar` if the application also depends on libraries loaded from a plugin directory or external configuration.

You should record:

- The JDK version used to build and run.
- The list of JARs along with versions and checksums.
- The current launch command, including classpath and JVM options.
- Plugin configurations, reflection, service providers, and dynamically loaded class names.
- Packages that the application exposes to other modules or libraries.

This serves as the baseline for comparing before and after modularization.

## 3. Step 1: view an overview of dependencies with jdeps

Run `jdeps --summary` to view dependencies at a high-level module/package summary:

```bash
jdeps --summary app.jar
```

If libraries reside on a separate classpath, pass them using `--class-path`:

```bash
jdeps --class-path "lib/*" --summary app.jar
```

Illustrative output:

```text
app.jar -> java.base
app.jar -> java.logging
app.jar -> customer.api
app.jar -> json.engine
```

Displayed names depend on the artifact type and jdeps's dependency mapping capability. When a dependency is not yet a module, the tool may display a JAR name or package rather than a resolved named module.

How to read it:

- `java.base`: the foundational module that almost all Java code depends on.
- `java.logging`: the application references logging APIs belonging to this module.
- `customer.api`, `json.engine`: application dependencies whose concrete artifacts and module names need to be identified.

`--summary` is useful for a quick overview. When you need to know which class creates a dependency, use verbose mode in subsequent steps.

## 4. Step 2: trace transitive dependencies

One library may depend on several other libraries. Use `--recursive` to analyze dependencies in depth:

```bash
jdeps --recursive --class-path "lib/*" --summary app.jar
```

Example:

```text
app.jar -> java.base
app.jar -> customer-api.jar
customer-api.jar -> java.base
customer-api.jar -> json-engine.jar
json-engine.jar -> java.base
```

The illustrative result shows that dependencies do not reside solely in app.jar. When moving to the module path, transitive dependency modules must also be supplied and resolved.

Do not add only the modules the application imports directly and omit library dependencies. The module graph must contain all required dependencies for modules to be resolved.

If the output is not clear enough, inspect class-level dependencies:

```bash
jdeps --recursive -verbose:class --class-path "lib/*" app.jar
```

Illustrative output:

```text
com.acme.app.Main -> com.acme.customer.Customer
com.acme.app.Main -> java.util.logging.Logger
com.acme.customer.Repository -> com.acme.json.JsonReader
```

From the source and target classes, you can determine which packages need to be exported, which modules need to be read, and which dependencies are actually used.

## 5. Step 3: determine the module name of each JAR

Before writing `module-info.java`, you need to know the module names of the dependencies.

Use:

```bash
jar --describe-module --file lib/customer-api.jar
jar --describe-module --file lib/json-engine.jar
jar --describe-module --file lib/logging.jar
```

There are three common cases:

1. **Explicit named module:** The JAR has `module-info.class`; the module name and directives are explicitly declared.
2. **Automatic module:** The JAR has no descriptor but is placed on the module path; the module name is derived from the JAR file name or declared via `Automatic-Module-Name` in the manifest.
3. **Classpath library:** The JAR sits on the classpath and belongs to the unnamed module of the corresponding class loader.

For example, the manifest may contain:

```text
Automatic-Module-Name: com.acme.customer
```

A stable automatic module name helps other modules declare `requires com.acme.customer` without depending on minor JAR filename changes across versions.

Do not confuse Maven artifact names, JAR filenames, package names, and module names. Obtain the module name from the descriptor or `jar --describe-module` output.

## 6. Step 4: check dependencies on JDK internal APIs

Legacy applications sometimes use classes in internal JDK packages, such as `sun.*` or `com.sun.*`. These APIs are not stable public Java APIs and may be encapsulated or changed across JDK versions.

Check with:

```bash
jdeps --jdk-internals app.jar
```

If there are dependencies on internal APIs, the output points out the source class and the relevant API. Find supported public API replacements before modularizing.

Do not use `--add-exports` as a long-term solution if the dependency can be replaced with a supported API. If a temporary workaround is needed for compatibility, document the exact module/package, restrict scope, and plan for removal.

## 7. Step 5: generate module descriptors for legacy libraries

For JARs without `module-info.class`, `jdeps` can suggest a descriptor:

```bash
jdeps --generate-module-info generated-modules lib/customer-api.jar
```

With multiple JARs, run one by one for each artifact to easily review and control the results.

The tool may generate a structure similar to:

```text
generated-modules/
└── com.acme.customer/
    └── module-info.java
```

The generated descriptor may contain `requires` and `exports` directives based on static dependencies detected by the tool.

Read and edit the descriptor before using it. `jdeps` does not know the full API design intent of the library, and may fail to infer:

- Which packages are truly public API.
- Which packages are strictly internal implementation.
- Service types the module uses via `ServiceLoader`.
- Providers registered via `META-INF/services`.
- Classes loaded via reflection or configuration.
- Dependencies that only appear on a dynamic execution path.

Do not export every package just to make compilation succeed. Export only packages needed by consumers.

If a library needs deep reflective access for a framework, consider `opens` specifically for the package and target module instead of broadly exporting all implementations.

## 8. Step 6: write module-info.java for the application

Suppose the dependencies have been identified:

- `customer-api` provides package `com.acme.customer`.
- `json-engine` provides package `com.acme.json`.
- The application uses JDK logging.

The application's module descriptor can start like this:

```java
module com.acme.app {
    requires java.logging;
    requires com.acme.customer;
    requires com.acme.json;
}
```

Module names in `requires` must match the actual module names of dependencies on the module path.

If another module needs to access the application's public API, export the packages to be exposed:

```java
module com.acme.app {
    requires java.logging;
    requires com.acme.customer;
    requires com.acme.json;

    exports com.acme.app.api;
}
```

There is no need to export packages containing the main class or implementations if no other module needs to access them.

### Distinguishing requires and exports

- `requires X`: the current module reads module X.
- `exports p`: the current module allows other modules to access public APIs in package p.
- `exports p to X`: exports the package only to module X.
- `requires transitive X`: propagates readability to consumers of the current module when the dependency is part of its public API.
- `requires static X`: a dependency needed at compile time that may be optional at runtime per the directive's rules.

A common mistake is adding `exports` to the consumer while the dependency has not exported its own package. A package must be exported by the module that owns that package.

## 9. Step 7: migrate ServiceLoader and META-INF/services

Classpath applications may register providers using a file:

```text
META-INF/services/com.acme.spi.Formatter
```

The file contains the fully qualified name of the provider class, one name per line.

When converting a provider to a named module, the service must be expressed in the module descriptors:

Consumer:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
```

Provider:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

Ensure the service interface resides in a package exported by the SPI module. The provider must implement the right service type and comply with ServiceLoader's instantiation requirements.

Do not assume `jdeps` will automatically convert every `META-INF/services` file into accurate `uses`/`provides`. Inventory service files and test provider discovery after conversion.

## 10. Step 8: place dependencies on the module path and compile

Once you have descriptors, organize sources and dependencies:

```text
project/
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    ├── com.acme.customer.jar
    ├── com.acme.json.jar
    └── com.acme.spi.jar
```

Compile the application:

```bash
javac --module-path mods \\
  --module-source-path src \\
  -d out \\
  -m com.acme.app
```

If library module descriptors were generated separately, repackage the JARs with `module-info.class` or compile the corresponding module sources before placing them on the module path.

Run the application:

```bash
java --module-path "mods:out" \\
  -m com.acme.app/com.acme.app.Main
```

On Windows, the module path separator is a semicolon:

```powershell
java --module-path "mods;out" -m com.acme.app/com.acme.app.Main
```

Do not place a non-modular JAR onto the module path arbitrarily and assume it behaves just like on the classpath. On the module path, a JAR may become an automatic module and participate in module resolution with different rules.

## 11. Step 9: verify the module graph and dependencies after migration

Use `jdeps` to verify the descriptor:

```bash
jdeps --module-path mods --check com.acme.app
```

Print module dependencies:

```bash
jdeps --module-path mods \\
  --print-module-deps mods/com.acme.app.jar
```

Verify the module graph at runtime:

```bash
java --show-module-resolution \\
  --module-path "mods:out" \\
  -m com.acme.app/com.acme.app.Main
```

Validate the set of modules on the module path:

```bash
java --validate-modules \\
  --module-path mods \\
  --add-modules ALL-MODULE-PATH
```

Read the output to confirm:

- The root module matches the application.
- `requires` dependencies are resolved from the right artifacts.
- There are no conflicting modules or packages.
- Required providers are bound and discoverable by ServiceLoader.
- There are no remaining references to missing modules/classes.

`ALL-MODULE-PATH` is useful to validate all observable modules in a test directory. You do not necessarily use it as a root in production commands if the application does not need to resolve every module on the module path.

## 12. Checking split packages and dynamic dependencies

The legacy classpath may have allowed multiple JARs to contribute classes to the same package. When JARs become named or automatic modules, split packages can cause resolution to fail.

Check for duplicate packages across artifacts before modularizing. If a split package exists, consolidate the package into one owning module or split packages by responsibility.

In addition to static dependencies, also inspect:

- `Class.forName` and class names read from configuration.
- Reflection and annotation-scanning frameworks.
- JNI and native libraries.
- Plugins loaded from directories outside the module path.
- `ServiceLoader` and `META-INF/services` files.
- Resource paths, serialization, and class names stored in data.

`jdeps` analyzes static references; it cannot guarantee full detection of dependencies determined at runtime.

## 13. Common jdeps commands table

| Goal | Command |
|---|---|
| Summarize dependencies | `jdeps --summary app.jar` |
| View transitive dependencies | `jdeps --recursive --summary app.jar` |
| View classes creating dependencies | `jdeps -verbose:class app.jar` |
| View module dependencies | `jdeps --list-deps app.jar` |
| Print list of module dependencies | `jdeps --print-module-deps app.jar` |
| Find missing dependencies | `jdeps --missing-deps app.jar` |
| Check JDK internal APIs | `jdeps --jdk-internals app.jar` |
| Check module descriptor | `jdeps --check com.acme.app --module-path mods` |
| Generate module-info.java | `jdeps --generate-module-info generated-modules lib.jar` |

When analyzing a JAR requiring external dependencies, add `--class-path` or `--module-path` as appropriate. Do not use `--ignore-missing-deps` to mask errors during migration verification; if you must use it to continue analysis, record and address each missing dependency separately.

## 14. Safe migration roadmap

The conversion process can be divided into phases:

1. **Inventory:** collect JARs, versions, module names, packages, service providers, and runtime dependencies.
2. **Static analysis:** run `jdeps` at summary, recursive, and verbose levels; find JDK internal APIs and missing dependencies.
3. **Dependency classification:** classify explicit modules, automatic modules, and classpath-only libraries.
4. **Package ownership:** resolve split packages and identify API/implementation packages.
5. **Descriptor authoring:** create or edit `module-info.java`; verify `requires`, `exports`, `uses`, `provides`, and `opens`.
6. **Compile:** place needed dependencies on the module path and compile the modules.
7. **Runtime verification:** run with `--show-module-resolution`, test ServiceLoader, reflection, and plugins.
8. **Release validation:** run `jdeps --check`, `java --validate-modules`, and integration tests on the exact release artifact set.
9. **Rollout:** deploy per environment, monitor for errors, and preserve rollback capability.

You do not have to migrate all libraries at once. You can keep some legacy libraries on the classpath during a transition period, provided you understand the boundary between the unnamed module and named modules; named modules do not read the unnamed module by default.

## Remember

- `jdeps` helps discover static dependencies; it does not automatically design a complete module graph.
- Use `--summary`, `--recursive`, `-verbose:class`, `--jdk-internals`, and `--generate-module-info` step by step.
- Determine module names using `jar --describe-module`; do not confuse JAR names with module names.
- Review generated descriptors: especially `requires`, `exports`, `uses`, `provides`, and `opens`.
- Check split packages, reflection, service providers, and dynamic plugins before dropping the classpath.
- Compile and run on the module path, then verify with `jdeps --check`, `--show-module-resolution`, and `--validate-modules`.
- Only accept the migration once integration tests confirm equivalent runtime behavior.