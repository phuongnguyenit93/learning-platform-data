# Do Not Use open or export to Mask Split Package Errors

## 1. What Is a Split Package?

In Java, a package is part of a class's fully qualified name. For example, the class \`com.acme.shared.Strings\` belongs to the package \`com.acme.shared\`.

A **split package** occurs when the same package name is contained in multiple modules or multiple artifacts. For example:

~~~text
library-a.jar
  com/acme/shared/Strings.class

library-b.jar
  com/acme/shared/DateFormats.class
~~~

Both JARs contain the package \`com.acme.shared\`. When two libraries are used together on the classpath, this situation can exist in traditional class loader systems. However, when migrating to JPMS, packages have clear module boundaries, and having the same package appear in multiple named modules can cause conflicts in the module graph or when creating a module layer.

Example of two modules:

~~~java
// module-info.java of com.acme.library.a
module com.acme.library.a {
    exports com.acme.shared;
}
~~~

~~~java
// module-info.java of com.acme.library.b
module com.acme.library.b {
    exports com.acme.shared;
}
~~~

If an application module reads both modules and both export \`com.acme.shared\`, the module graph can be rejected because the consumer sees the same package from multiple modules. Depending on configuration and detection stage, the error can appear when resolving the configuration, creating a ModuleLayer, or compiling source referencing the package.

This is an issue of **package ownership and module structure**, not an issue of missing reflection permissions.

## 2. Why Do open or export Not Fix Split Packages?

The \`exports\` and \`opens\` directives control access permissions to packages belonging to a module. They do not move classes, merge packages, or change which module owns a class.

- \`exports p\`: allows other modules to access public APIs in package \`p\` under normal Java rules.
- \`exports p to m\`: exports the package only to the specified target module(s).
- \`opens p\`: allows deep reflection into the package.
- \`opens p to m\`: opens the package for reflection from the target module(s).
- \`open module\`: opens all packages of the module for deep reflection.

If two modules both contain the package \`com.acme.shared\`, adding \`exports com.acme.shared\` to both only exposes that package from both modules. Adding \`opens com.acme.shared\` also does not resolve the ownership conflict; it only changes reflection permissions.

Runtime options such as \`--add-exports\` and \`--add-opens\` do not merge packages either. They can alter access permissions and even make the conflicting package observable by more modules.

Therefore, do not add \`open\`, \`opens\`, \`exports\`, \`--add-exports\`, or \`--add-opens\` merely to make a split package error disappear. First, you must address where the packages and classes are actually packaged.

## 3. Distinguishing Split Packages on the Classpath and Module Path

### 3.1. On the classpath

On the classpath, multiple JARs can contain classes belonging to the same package name. Classes loaded by the same class loader can belong to the same runtime package, because a runtime package is defined by the package name and class loader.

This explains why a legacy application can run even though a package is split across multiple JARs. However, it also creates risks:

- Classes with the same fully qualified name can be selected based on classpath order.
- Package-private access may inadvertently rely on classes using the same class loader.
- When changing JAR order, the loaded class or found resource can change.
- When converting JARs into named modules, assumptions about package ownership no longer hold.

The fact that the classpath runs does not prove the package structure is sound or can be migrated as-is to JPMS.

### 3.2. On the module path

On the module path, each named module has a module descriptor and a set of packages belonging to the module. JPMS checks packages in the module graph. Conflicts typically arise when multiple modules in the same configuration contain a package that can be read by another module or participate in a module layer in an invalid way.

You should not rely on a specific graph accidentally failing to trigger a conflict. When designing modules, aim for one clear module owner for each shared package.

Automatic modules also need checking. A JAR without \`module-info.class\` when placed on the module path can become an automatic module; moving from the classpath to the module path does not automatically eliminate overlapping packages across dependencies.

## 4. Example of a Dependency Graph with a Split Package

Suppose two libraries are developed independently:

~~~text
com.acme.legacy-a
  com/acme/common/Strings.class
  com/acme/common/Checks.class

com.acme.legacy-b
  com/acme/common/DateFormats.class
  com/acme/common/LocaleNames.class
~~~

When modularizing each library, descriptors might be written as follows:

~~~java
module com.acme.legacy.a {
    exports com.acme.common;
}
~~~

~~~java
module com.acme.legacy.b {
    exports com.acme.common;
}
~~~

Application module:

~~~java
module com.acme.app {
    requires com.acme.legacy.a;
    requires com.acme.legacy.b;
}
~~~

The application reads both modules, while both modules provide the package \`com.acme.common\`. This is a sign that the dependency/package layout needs to be fixed.

You should not try to work around it by adding:

~~~java
module com.acme.legacy.a {
    exports com.acme.common;
    opens com.acme.common;
}
~~~

or adding flags:

~~~bash
--add-exports=com.acme.legacy.a/com.acme.common=com.acme.app
--add-opens=com.acme.legacy.b/com.acme.common=com.acme.app
~~~

These declarations do not change the fact that both JARs contain classes in that package. Nor do they decide which one is the valid owner of the package.

## 5. How to Find Overlapping Packages

Inspect the actual artifacts placed on the module path, not just the source tree. Overlapping packages can come from transitive dependencies, shaded JARs, old JARs leftover in the distribution directory, or an internal module packaged twice.

### 5.1. Inspect each JAR's module descriptor

Use:

~~~bash
jar --describe-module --file libs/library-a.jar
jar --describe-module --file libs/library-b.jar
~~~

This command shows the module name, dependencies, and packages that the JAR exports or contains in its descriptor. For a JAR without a descriptor, the output can show the module name derived under automatic module rules.

Note: the \`exports\` list is not the complete list of packages inside a JAR. Internal packages can exist without being exported.

### 5.2. List classes in JARs

Use:

~~~bash
jar --list --file libs/library-a.jar
jar --list --file libs/library-b.jar
~~~

Look for identical package paths, such as:

~~~text
com/acme/common/Strings.class
com/acme/common/Checks.class
~~~

You can use an archive tool or script to extract the list of \`.class\` entries from all JARs on the module path, convert paths to package names, and compare them. When doing this, ignore \`module-info.class\` and entries that do not represent normal classes.

### 5.3. Use jdeps

\`jdeps\` has a mode to check modules and split packages:

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

The command checks dependencies/module graph of the specified module and can report split packages or unused qualified exports. Read the entire output to identify the involved modules and packages.

You can inspect dependencies of a JAR:

~~~bash
jdeps --list-deps --module-path mods app.jar
~~~

If you need to analyze JDK internal APIs or deeper dependencies, choose \`jdeps\` options matching your JDK version. \`jdeps\` results assist dependency investigation; you still need to cross-check the class list in the actual artifacts.

### 5.4. Inspect the build tool's dependency tree

With Gradle:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

To see why a dependency appears:

~~~bash
./gradlew :app:dependencyInsight --dependency library-a --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn -pl app dependency:tree
~~~

The dependency tree helps find versions or transitive dependencies pulled in multiple times. However, two artifacts with different coordinates can still contain the same package; the dependency tree does not replace inspecting JAR contents.

## 6. Proper Ways to Fix It

### 6.1. Merge the package into one owning module

If two libraries are parts of the same subsystem and the same team can modify the source, move classes of the same package into a single owning module.

For example:

~~~text
com.acme.common
  Strings
  Checks
  DateFormats
  LocaleNames
~~~

packaged in one module:

~~~java
module com.acme.common {
    exports com.acme.common;
}
~~~

The old modules can become facades or be removed after updating callers. This preserves the API package and establishes one place to manage ownership.

### 6.2. Rename packages to separate boundaries

If two libraries have different responsibilities, move classes to packages reflecting the right module:

~~~text
com.acme.legacy.a
  com/acme/legacy/a/common/Strings.class
  com/acme/legacy/a/common/Checks.class

com.acme.legacy.b
  com/acme/legacy/b/common/DateFormats.class
  com/acme/legacy/b/common/LocaleNames.class
~~~

Descriptors:

~~~java
module com.acme.legacy.a {
    exports com.acme.legacy.a.common;
}
~~~

~~~java
module com.acme.legacy.b {
    exports com.acme.legacy.b.common;
}
~~~

This is an API change if the old package was already used by consumers. You must update imports, module descriptors, reflection configurations, class names stored in configs, and integrations relying on fully qualified names.

### 6.3. Remove duplicate or unnecessary dependencies

If the same library is pulled in across multiple versions or via transitive dependencies, select one appropriate version and exclude the unnecessary artifact.

In Gradle, you can use dependency constraints, version catalogs, resolution strategies, or intentional excludes. In Maven, use dependency management and exclusions.

Do not remove a JAR solely because artifact names look similar. Confirm the classes and APIs that modules actually use, then rerun compile/test and inspect the module graph.

### 6.4. Relocate packages when shading third-party libraries

If you cannot modify the source of third-party libraries and need to include both libraries in the same application, you can relocate one package when creating a shaded JAR.

Conceptual example:

~~~text
com.vendor.common
    -> com.acme.shaded.vendor.common
~~~

After relocation, the library's classes are renamed to a separate package and no longer collide with the original package.

You must also check data containing class/package names as strings, service provider files, resources, serialization metadata, reflection configurations, and module descriptors. The shading tool must update those related metadata files; merely renaming \`.class\` files while missing referenced contents will create hard-to-find runtime errors.

Relocation should be configured in the build, reproducible, and verified on the final artifact.

### 6.5. Create an adapter or facade module

If you need to preserve the legacy public API while moving implementations, create a facade module with a single API package and move implementations into separate internal packages/modules.

For example:

~~~text
com.acme.common.api
com.acme.common.impl.strings
com.acme.common.impl.dates
~~~

The facade can provide the necessary public interfaces or classes, while implementations reside in non-overlapping packages. This enables gradual migration while still maintaining one clear owning module for each package.

## 7. Approaches That Should Not Be Used to Mask Errors

| Attempted approach | Why it does not solve a split package |
| --- | --- |
| Adding \`exports\` to both modules | Exposes the package from multiple modules; does not merge classes or establish one owner. |
| Adding \`opens\` or using \`open module\` | Only grants deep reflection permissions; does not change package ownership. |
| Adding \`--add-exports\` | Adds access permissions to public types; does not remove duplicate packages. |
| Adding \`--add-opens\` | Adds reflection permissions; does not fix the module graph. |
| Changing JAR order on the classpath | May change which class is loaded, but does not eliminate duplicate classes or an unstable package structure. |
| Moving all dependencies back to the classpath | May bypass some JPMS checks short-term, but forfeits module benefits and boundaries; not a modularization approach. |
| Only renaming the module in \`module-info.java\` | The module name changes, while the packages inside still overlap. |

## 8. Workflow for Handling Split Packages in a Modular Project

1. Record the full error and identify the modules/packages appearing in the message.
2. Determine the exact module path and set of artifacts passed into the failing compile or runtime run.
3. Use \`jar --describe-module\` and \`jar --list\` to determine which modules contain that package.
4. Use \`jdeps --check\` and the dependency tree to find direct or transitive dependencies bringing the conflicting modules into the graph.
5. Choose one owner for the package, or rename packages/relocate artifacts to separate ownership.
6. Update dependencies, source imports, descriptors, and related metadata.
7. Rebuild from a clean state to avoid stale JARs left in the output.
8. Rerun \`jdeps --check\`, compile modules and the application using the exact deployment module path.
9. Inspect the final artifacts and run integration tests in the exact runtime/module layer.

## 9. Conclusion on Package Ownership

A package should have one clear module owner in JPMS design. \`exports\` determines which modules can use the package's public API; \`opens\` determines which modules can perform deep reflection into the package. These two mechanisms do not resolve a package being split across multiple modules.

When encountering a split package, trace back from the module graph to the JARs containing the classes, then merge, rename, remove duplicate dependencies, or relocate packages. Resolving ownership at the artifact/source level keeps the module graph stable and avoids granting broad access permissions just to mask a structural flaw.
