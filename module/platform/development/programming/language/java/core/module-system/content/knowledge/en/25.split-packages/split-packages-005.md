# How Automatic Modules Expose Split Packages

A split package occurs when the same Java package is contained in multiple modules. On the classpath, multiple JARs can contain classes belonging to the same package; the class loader typically searches for classes in classpath order and the application can run even though that structure is unclear. When moving the JARs to the module path, each JAR can become a separate module. The module system can then detect that a package is divided across modules and refuse to resolve the configuration.

Automatic modules often expose this problem during migration. A JAR without module-info.class placed on the module path can be treated as an automatic module. It has a module name, can be required via requires, reads other modules, and exports its packages. However, becoming an automatic module does not merge that JAR's package with an identically named package in another dependency.

This article explains why errors appear when moving from the classpath to the module path, how to find modules causing duplicate packages, and safe ways to resolve them.

## 1. What Is a Split Package?

Suppose there are two libraries:

~~~text
lib/
|-- customer-api.jar
|   |-- com/example/model/Customer.class
|   |-- com/example/model/Address.class
|
|-- customer-legacy.jar
    |-- com/example/model/LegacyCustomer.class
    |-- com/example/model/CustomerMapper.class
~~~

Both JARs contain the package com.example.model. On the classpath, the class loader can load classes from both JARs according to search order. This may work, but package ownership is split across two artifacts. The outcome depends on packaging, classpath order, and which class gets loaded first.

If the two JARs are recognized as two separate modules on the module path, the module system must determine which module owns the package. A module configuration cannot rely on two modules co-owning a package to form a single unified package. Resolution can fail with a split package error, typically reported via ResolutionException or a message stating that modules contain the same package.

A split package is not solely a duplicate class name issue. Two JARs can contain different classes in the same package; that is still a split package. Conversely, two JARs having the same class name in different packages do not create a split package in this sense.

## 2. Why Do Automatic Modules Make the Error Appear?

A JAR without a module descriptor can be treated by the module finder as an automatic module when placed on the module path. The module name can be taken from the Automatic-Module-Name attribute in the manifest; if absent, the name can be derived from the JAR filename according to automatic module naming rules.

For example:

~~~text
customer-api.jar
    Automatic-Module-Name: com.example.customer.api

customer-legacy-2.4.jar
    (no module-info.class)
    (no Automatic-Module-Name)
~~~

When placing these JARs on the module path, they can be recognized as separate modules. If both contain the package com.example.model and are both in the resolved configuration, the overlapping package will be detected.

Automatic modules have several special characteristics:

- Have a module name and can be referenced via requires.
- Read all other modules in the configuration according to the rules for automatic modules.
- Export all of their packages.
- Can be used to carry legacy libraries forward during the migration phase.
- Do not turn identically named packages in other JARs into a single package.

Because an automatic module exports all its packages, a named module can read its packages. That does not mean two automatic modules are allowed to co-own a package in the same module configuration.

Automatic-Module-Name only stabilizes the module name when the filename changes. It does not fix split packages, does not merge two JARs, and does not replace a module descriptor.

## 3. Common Scenario When Moving from the Classpath to the Module Path

Before modularizing, an application might run with:

~~~bash
java -cp "app.jar;lib/*" com.example.app.Main
~~~

On Windows, a semicolon separates the classpath. On Linux and macOS, use a colon.

When moving libraries to the module path:

~~~bash
java --module-path "mods;lib" \
     --module com.example.app/com.example.app.Main
~~~

A legacy JAR without module-info.class can become an automatic module. If the dependency graph contains two JARs with the same package, module resolution can fail before the main method is invoked.

This explains why an application runs normally on the classpath yet fails to start on the module path. The module path enforces stricter rules on module identity, readability, and package ownership.

Not every JAR in the lib directory automatically becomes a module. Only artifacts discovered under module path rules and included in the configuration participate in resolution. A JAR remaining on the classpath belongs to the unnamed module and has different access scope.

## 4. How to Read a Split Package Error

The error message usually names the package and the two modules containing that package. Illustrative example:

~~~text
java.lang.module.ResolutionException:
Module com.example.customer.api contains package
com.example.model, module customer.legacy exports package
com.example.model to com.example.customer.api
~~~

The exact module names and wording depend on the JDK, configuration, and detection stage. Use the package named in the error as the starting point.

When reading the error:

1. Note the overlapping package, for example com.example.model.
2. Note all mentioned modules.
3. Determine which JAR or directory on the module path each module comes from.
4. Check the dependency tree to see why both artifacts are brought in.
5. Determine which classes actually belong to each artifact and which module should own that package.

Do not rush to add --add-exports or --add-reads. These options adjust access permissions and readability relationships; they do not merge packages and do not resolve package ownership conflicts.

## 5. Finding Overlapping Packages Using JDK Tools

### Inspect each JAR's module descriptor

Use jar --describe-module to view the module name, packages, and descriptor information of each archive:

~~~bash
jar --describe-module --file lib/customer-api.jar
jar --describe-module --file lib/customer-legacy-2.4.jar
~~~

If the JAR is an automatic module, the output can show the automatic module name and packages recognized by the tool. If the JAR has module-info.class, the output displays the module descriptor.

Inspect the manifest to see whether a stable automatic module name is declared:

~~~bash
unzip -p lib/customer-api.jar META-INF/MANIFEST.MF
~~~

Look for the Automatic-Module-Name attribute. This attribute prevents the module name from depending on filename conventions, but does not change the package list.

### Validate the module path

Use the Java launcher to check the module configuration:

~~~bash
java --module-path "mods;lib" --validate-modules
~~~

This command validates observable modules on the module path and reports conflicts detected by the module system. Adjust the path separator for your operating system.

To see which modules are resolved when launching the application:

~~~bash
java --show-module-resolution \
     --module-path "mods;lib" \
     --module com.example.app/com.example.app.Main
~~~

If resolution fails before the application runs, combine the error details with jar --describe-module output to pinpoint the JARs involved.

### Inspect application dependencies

jdeps helps show which module depends on which modules:

~~~bash
jdeps --module-path "mods;lib" --print-module-deps app.jar
~~~

You can use:

~~~bash
jdeps --module-path "mods;lib" --check com.example.app
~~~

The results help identify unnecessary dependencies, transitive dependencies, and which modules participate in the configuration. jdeps does not replace inspecting packages inside each JAR; combine it with jar --describe-module and --validate-modules.

## 6. Automatically Finding Overlapping Packages with ModuleFinder

If you have many JARs and need a report of which packages appear in multiple modules, you can write a small tool using ModuleFinder and ModuleDescriptor.packages().

For example:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

public class FindSplitPackages {

    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(
                Path.of("lib/customer-api.jar"),
                Path.of("lib/customer-legacy-2.4.jar"));

        Map<String, String> packageOwners = new HashMap<>();

        for (ModuleReference reference : finder.findAll()) {
            ModuleDescriptor descriptor = reference.descriptor();
            String moduleName = descriptor.name();

            for (String packageName : descriptor.packages()) {
                String previous = packageOwners.putIfAbsent(
                        packageName, moduleName);

                if (previous != null && !previous.equals(moduleName)) {
                    System.out.printf(
                            "Split package %s: %s and %s%n",
                            packageName, previous, moduleName);
                }
            }
        }
    }
}
~~~

This code maps each package to the first module seen. When a package appears in another module, the program prints a potential conflict.

This is a static scan over the artifacts passed into ModuleFinder. It does not replace actual module resolution: some modules may not end up in the final configuration together, and actual outcomes also depend on root modules, module path, upgrade module path, and dependency relationships.

For an automatic module, packages() reflects the packages recognized from archive contents. For an explicit module, the descriptor holds the module's package list. Use the exact set of JARs that the application actually places on the module path.

## 7. Ways to Handle Split Packages

There is no universal launcher option to turn two modules co-owning a package into one valid module. Choose a handling approach based on package ownership and your ability to modify dependencies.

### Prefer upgrading or replacing dependencies

Check whether the vendor has released a new version that eliminates overlapping packages, merges artifacts, or changes packaging.

If two libraries share a package because an older release was split, upgrading to a fixed version may solve it cleanly. Check release notes and the dependency tree before upgrading.

Do not just bump versions randomly. Two libraries may depend on different API versions; you must run compatibility tests and verify binary linkage.

### Remove unnecessary duplicate dependencies

A dependency may be pulled in transitively via another library. If the application already has an artifact providing the corresponding classes, you can exclude the redundant dependency from Maven or Gradle.

With Maven, an illustrative exclusion:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>customer-client</artifactId>
    <version>3.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>customer-legacy</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

After excluding, inspect the dependency tree and run tests. Only exclude when certain the application does not need classes or resources present only in the removed artifact.

### Merge the package into one module

If two artifacts are genuinely parts of the same component and the package needs to be shared, the architectural solution may be to merge the classes into a single module.

For example:

~~~text
Before:
customer-api.jar       -> com.example.model
customer-legacy.jar    -> com.example.model

After:
customer-module.jar    -> com.example.model
~~~

Merging may require changes to the build, module descriptors, and release process. If the original artifacts cannot be modified, you can create an internal module repackaging the necessary classes, but you must manage licenses, service metadata, resources, and binary compatibility.

### Relocate packages of a dependency

If a library carries an internal package used only internally and does not need to share types with the application, you can use shading/relocation to move the package into a dedicated namespace.

For example:

~~~text
Before:
com.example.model.LegacyCustomer

After:
com.example.shaded.legacy.model.LegacyCustomer
~~~

Relocation changes binary class names. You must check reflection, serialization, resource paths, service provider configurations, annotation processors, and class name strings stored in configs. Do not relocate an API package that consumers interact with directly unless there is an explicit compatibility plan.

### Keep some dependencies on the classpath during the transition phase

You can leave a legacy library on the classpath so it belongs to the unnamed module while modularized modules sit on the module path. This can serve as a transitional step for components not yet ready for modularization.

However, a named module does not read the unnamed module via normal readability rules. If a named module directly needs classes from a classpath library, placing the library on the classpath does not resolve that dependency. An appropriate adapter or integration boundary is needed.

The classpath approach also does not make the split package disappear in terms of design; it merely keeps the JARs in one class loader/unnamed module space instead of turning each JAR into a separate module.

## 8. Role of --patch-module and the add-* Options

--patch-module can add classes or resources to an existing module:

~~~bash
java --patch-module com.example.customer=patches/customer \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Patched content is treated as part of the target module. This is a useful mechanism for testing, instrumentation, or intentional module content patching. It is not the default solution for masking two independent libraries owning the same package.

Other options have different scopes:

| Option | Adjusts | Does it solve split packages? |
|---|---|---|
| --add-exports | Allows other modules to access additionally exported public packages | No |
| --add-opens | Opens packages for deep reflection | No |
| --add-reads | Adds a readability relationship between two modules | No |
| --patch-module | Adds classes/resources to a target module | Can be used in intentional repackaging cases, but requires careful design |

Do not use add-exports, add-opens, or add-reads to handle duplicate package errors. They alter access permissions, not which module contains the package.

## 9. Recommended Migration Process

When an application starts reporting a split package after moving dependencies to the module path, proceed in order:

1. **Preserve the error log:** record the package name and the modules mentioned.
2. **Identify artifacts:** use jar --describe-module to map module names back to JARs.
3. **Inspect packages:** see which module descriptors contain the package; ModuleFinder can be used to scan automatically.
4. **Find dependency sources:** use the build tool's dependency tree and jdeps to identify direct/transitive dependencies.
5. **Choose an owner:** decide which module is the logical owner of the package.
6. **Fix dependencies or packaging:** upgrade, exclude, merge, or relocate packages depending on the case.
7. **Re-validate:** run java --validate-modules and start the application with --show-module-resolution.
8. **Functional testing:** verify APIs, service loading, reflection, serialization, and binary compatibility.
9. **Stabilize module names:** for automatic modules that must still be kept, declare a stable Automatic-Module-Name if possible.
10. **Plan removal of automatic modules:** gradually migrate toward explicit module descriptors and intentional dependency graphs.

## 10. Common Mistakes

- **Merely renaming the JAR:** a new filename may change the automatic module name, but does not change the packages inside.
- **Adding Automatic-Module-Name and expecting the error to vanish:** this attribute only stabilizes the module name; it does not fix overlapping packages.
- **Adding --add-exports or --add-reads:** these options do not change package ownership.
- **Checking only class names:** a split package can occur even when two JARs contain different classes.
- **Checking only one JAR:** packages must be compared across the entire relevant module path.
- **Excluding a dependency without testing:** can remove classes or resources needed at runtime.
- **Relocating an API package:** can break binary compatibility, reflection, or serialization.
- **Confusing the classpath with the module path:** on the classpath, JARs usually share the unnamed module; on the module path, JARs can become separate modules.
- **Treating automatic modules as complete modules:** an automatic module is a migration bridge; its name, packages, and dependencies still need to be controlled.

## 11. Key Takeaways

Automatic modules help bring legacy libraries onto the module path without requiring module-info.class yet, but they do not merge packages split across multiple JARs. Once JARs become separate modules, module resolution can detect split packages and reject the configuration.

Identify the package and its owning modules using jar --describe-module, jdeps, --validate-modules, or ModuleFinder. Then establish a single clear package owner: upgrade dependencies, remove duplicates, merge artifacts, or relocate internal packages. The add-exports/add-opens/add-reads options do not resolve package ownership conflicts.

## References

- Java Platform Module System — ModuleFinder and Configuration API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
- Java Launcher — --validate-modules, --module-path and --show-module-resolution: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
- The jar Command — --describe-module: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html
- jdeps — Java Dependency Analysis Tool: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
