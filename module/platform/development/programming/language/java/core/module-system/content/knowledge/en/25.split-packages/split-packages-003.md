# Split Packages Between the Module Path and Classpath

## 1. What Is a Split Package?

A **split package** occurs when the same package name is contained in multiple independent deployment units, such as multiple JARs. For example:

```text
lib-core.jar
└── com/acme/util/StringHelper.class

lib-extra.jar
└── com/acme/util/DateHelper.class
```

Both JARs contribute classes to the package `com.acme.util`. How Java handles this structure depends on where the JARs are placed:

- On the **classpath**, classes usually belong to the unnamed module of the class loader. Multiple JARs on the classpath can contribute classes to the same package.
- On the **module path**, each explicit module or automatic module has its own boundary. A package is bound to the module that owns it; having the same package appear in multiple named modules can cause module resolution to fail when a module simultaneously reads those package sources.

Therefore, a structure that runs on the classpath might not run after moving the JARs onto the module path. This is a common issue when modularizing a legacy Java application.

## 2. Classpath: Multiple JARs Contributing to the Unnamed Module

When launching with `-cp` or `--class-path`, the specified directories and JARs are searched by the class loader. For the standard application class loader, classes on the classpath belong to the corresponding unnamed module.

For example:

```text
app.jar
lib-core.jar
lib-extra.jar
```

Run:

```bash
java -cp "app.jar:lib-core.jar:lib-extra.jar" com.acme.app.Main
```

On Windows, the classpath separator is a semicolon:

```powershell
java -cp "app.jar;lib-core.jar;lib-extra.jar" com.acme.app.Main
```

If `lib-core.jar` and `lib-extra.jar` contain different classes in the same package `com.acme.util`, the application can usually still load both. The package is not split across two named modules; the classes are loaded into the same unnamed module of that class loader.

This is why many legacy Java libraries can split a package across multiple JARs and still work on the classpath.

However, the classpath does not make all conflicts disappear:

- If two JARs contain the same binary class name, for example both have `com.acme.util.StringHelper`, the class loader typically loads the version found first in search order (after the loader's delegation mechanism).
- Classpath order can affect the result and cause bugs to appear only in a specific deployment environment.
- If classes are loaded by different class loaders, they do not automatically belong to the same runtime package; package-private access may fail.

The classpath allows multiple JARs to contribute classes to a package, but does not guarantee that duplicate class names or different class loaders are compatible.

## 3. Module Path: Packages Belong to Modules

When JARs are placed on the module path, Java determines modules from:

- `module-info.class` of an explicit named module; or
- The rules for deriving the name and contents of an automatic module if the JAR has no corresponding descriptor.

The module descriptor specifies the packages owned by the module and which packages are exported. Modules are no longer merely JARs dumping classes into a shared classpath.

For example:

```text
com.acme.core
└── exports com.acme.util

com.acme.extra
└── exports com.acme.util

com.acme.app
├── requires com.acme.core
└── requires com.acme.extra
```

If both `com.acme.core` and `com.acme.extra` export the package `com.acme.util` to `com.acme.app`, the module system cannot choose a single package source for the consumer. Resolution can fail with `ResolutionException`, accompanied by a message stating that two modules export the same package to a module.

You should not design based on a split package coincidentally not causing an error in one specific graph. When adding dependencies or changing which modules read those packages, conflicts can emerge.

With named modules, having the same package name does not mean the classes belong to the same module or share package-private access. Package ownership is part of the module boundary.

## 4. Why Do the Classpath and Module Path Produce Different Results?

Comparison:

| Aspect | Classpath | Module path |
|---|---|---|
| Unit of organization | Entries searched by the class loader | Explicit or automatic modules |
| Module containing classes | Typically the loader's unnamed module | Named module |
| Multiple JARs with the same package | Can usually co-contribute to the unnamed module's package | Can cause a split-package conflict in the module graph |
| Package visibility | Traditional Java access rules within the runtime package | Combines Java access rules and module exports/opens |
| Dependency declaration | No `requires` in a module descriptor | Has `requires`, `exports`, `uses`, `provides` |
| Module resolution | Does not resolve a graph for classpath JARs | Resolves root modules and dependencies |
| Duplicate binary class names | Search order/class loader may determine the loaded class | Module ownership and resolution must be consistent; there should not be two competing package sources |

On the classpath, JARs are viewed as class sources for the unnamed module. On the module path, each module is an independent unit with explicit package ownership and dependencies. Therefore, merely changing the launch argument from `-cp` to `--module-path` is not a complete modularization step.

## 5. Split Packages When Mixing the Classpath and Module Path

An application can use both the classpath and module path simultaneously:

```bash
java --module-path mods \
  --class-path legacy-libs/* \
  -m com.acme.app/com.acme.app.Main
```

In this configuration:

- Modules in `mods` are named or automatic modules.
- Libraries in `legacy-libs` belong to the unnamed module of the corresponding class loader.
- Packages with the same name on both sides remain in different modules/loading contexts; they do not automatically merge into a single shared package.

An important point is that a named module does not read the unnamed module by default. Therefore, if `com.acme.app` is a named module and needs a library still left on the classpath, declaring `requires` to that JAR's name will not turn the classpath library into a named module.

Conversely, code running in the unnamed module can read named modules placed in an appropriate module layer. This asymmetry makes partial migration require careful design.

If the same package appears on both the module path and classpath, check which module actually owns each class and which class loader loads them. Do not rely on two identical package names to assume package-private access, class identity, or loading order will behave the same as when all JARs are on the classpath.

Symptoms of improper mixing can include packages not being visible at compile time, classes not found at runtime, access errors, or linking the wrong class version. The exact cause depends on the module graph, class loaders, and how the application is compiled/launched.

## 6. Example of Moving Two JARs from the Classpath to the Module Path

Suppose initially you have:

```text
legacy-app.jar
legacy-core.jar
legacy-extra.jar
```

The two libraries contain:

```text
legacy-core.jar
└── com/acme/util/StringHelper.class

legacy-extra.jar
└── com/acme/util/DateHelper.class
```

Legacy launch command:

```bash
java -cp "legacy-app.jar:legacy-core.jar:legacy-extra.jar" \
  com.acme.app.Main
```

This structure can work because classes in the same package are loaded in the unnamed module.

If both libraries are moved as two automatic modules onto the module path, the package `com.acme.util` appears in two separate modules. Automatic modules have broad package export rules, so package conflicts can surface during resolution when a consumer reads both.

If `legacy-core.jar` is moved to the module path while `legacy-extra.jar` is left on the classpath, the two parts of the package sit in a named module and the unnamed module. The named module does not automatically read the remaining classpath part. A dependency that used to work on the classpath may therefore no longer function.

The sustainable fix is to determine which module owns each package and organize artifacts along those boundaries, rather than just moving JAR locations.

## 7. How to Inspect Packages in Each JAR

List classes in JARs:

```bash
jar --list --file legacy-core.jar
jar --list --file legacy-extra.jar
```

Look for paths sharing the same package directory, for example:

```text
com/acme/util/StringHelper.class
com/acme/util/DateHelper.class
```

Inspect module descriptors or automatic module names:

```bash
jar --describe-module --file legacy-core.jar
jar --describe-module --file legacy-extra.jar
```

This command helps determine the module name, recognized packages, and module directives. If a JAR has no `module-info.class`, the output can show that it is an automatic module and the name inferred or declared via the manifest.

To check the module graph on the module path:

```bash
java --validate-modules \
  --module-path mods \
  --add-modules ALL-MODULE-PATH
```

The validation command can detect package conflicts and other module graph issues. If you need to see which modules are actually resolved when running the application:

```bash
java --module-path mods \
  --show-module-resolution \
  -m com.acme.app/com.acme.app.Main
```

You can use `jdeps` to inspect dependencies and check descriptors:

```bash
jdeps --check com.acme.app --module-path mods
```

You should inspect the entire set of artifacts that will be deployed together. Checking each JAR individually cannot detect a package split between two JARs.

## 8. Approaches When Migrating to the Module Path

### Consolidate the package into one owning module

If classes in the same package belong to the same component, move them into a single module:

```text
com.acme.util
├── StringHelper
└── DateHelper
```

The module descriptor exports the package if it is an API needed by consumers:

```java
module com.acme.util {
    exports com.acme.util;
}
```

### Separate packages by responsibility

If the classes belong to two independent components, rename packages so each module owns its own package:

```text
com.acme.core.util.StringHelper
com.acme.extra.util.DateHelper
```

You must update imports, serialization/reflection configurations, and class names stored in configurations if they are referenced by their fully qualified names.

### Modularize dependencies

Move required dependencies onto the module path and create appropriate module descriptors. You can start with automatic modules to determine module names and verify dependencies, then add explicit `module-info.java` files to control `requires` and `exports`.

The `Automatic-Module-Name` manifest attribute keeps the automatic module name stable across JAR versions, but it does not fix split packages. Packages still belong to separate modules and still need to be organized without conflicts.

### Temporarily keep legacy library groups on the classpath

If an entire group of libraries with interdependent packages cannot be modularized yet, you can keep that group on the classpath and let the legacy application portion run in the unnamed module during the transition phase. However, named modules do not read the unnamed module by default; you cannot assume a named module will directly use legacy classes merely because the JAR is on the classpath.

## 9. Special Mechanisms and Limitations

### --patch-module

`--patch-module` allows adding classes or resources into an existing module, making the patched content become part of the target module for that run.

For example:

```bash
java --patch-module com.acme.core=patches/core \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

This is an intentional mechanism for certain patching or testing scenarios. It should not be used as the default fix for release structures with unclear package ownership. When patching, you must specify the target module and strictly control the added content.

### --add-reads and --add-exports

These options can adjust readability or package access in special compatibility situations. They do not turn two modules owning the same package into one module and do not by themselves resolve split packages.

### Automatic modules

A JAR without a descriptor placed on the module path can become an automatic module. Automatic modules are convenient for migration, but they are not the classpath's unnamed module. They still have a module name, participate in the module graph, and can cause package conflicts with other modules.

## 10. Verification Workflow in CI

A modular migration or release pipeline should:

1. Create a staging directory containing the exact JARs to be deployed.
2. Scan the package inventory of all JARs to find packages appearing in multiple artifacts.
3. Run `jar --describe-module` on dependencies to confirm module names and packages.
4. Run `java --validate-modules` on the staging module path.
5. Run integration tests using the exact intended modular launch command.
6. Check libraries remaining on the classpath and confirm no named module implicitly depends on the unnamed module.
7. Only release when all required checks pass.

For a project undergoing migration, you should run tests on both the legacy classpath configuration and the new module path. Differences between the two results help uncover hidden dependencies, package-private coupling, and packages split across artifacts.

## Key Takeaways

- On the classpath, multiple JARs typically contribute classes to the class loader's unnamed module; split packages can work.
- On the module path, packages belong to separate modules; two modules exporting the same package to a consumer reading both can cause resolution to fail.
- Sharing a package name between a named module and the unnamed module does not turn them into one shared package.
- Named modules do not read the unnamed module by default.
- Automatic modules are still modules and can still create split-package conflicts.
- Inspect the entire set of JARs using `jar --describe-module`, `java --validate-modules`, `jdeps`, and integration tests.
- Fix by consolidating packages into one module or separating packages by responsibility; `--patch-module` is only for controlled special situations.
