# Why the Same JAR Can Behave Differently Depending on Placement

A JAR is simply a package containing classes, resources, and metadata. The JAR file itself does not decide how Java applies module rules. At launch time, placing the JAR on `--class-path` or `--module-path` determines whether it is loaded as part of the unnamed module, an explicit module, or an automatic module. Therefore, the same file may run in one mode but trigger access errors or dependency resolution failures in the other.

## 1. Placing a JAR on the Classpath

The classpath is passed via `-cp` or `--class-path`. The class loader searches for classes and resources in the listed directories/JARs. Classes loaded from the classpath belong to the unnamed module associated with the corresponding class loader.

If the JAR has `module-info.class`, Java ignores that descriptor when the JAR is on the classpath. The `requires`, `exports`, `opens`, `uses`, and `provides` declarations are not used to enforce module boundaries for this JAR. Application code is still subject to normal Java access rules such as `public`, `protected`, package-private, and `private`, but is not restricted by the module descriptor's `exports`.

If the JAR does not have `module-info.class`, the result is also classes belonging to the unnamed module. Thus, two JARs with different module structures can still behave similarly when both are placed on the classpath: the module descriptor does not participate in resolution.

## 2. Placing a JAR on the Module Path

The module path is passed via `--module-path` or `-p`. Java locates modules, reads their descriptors, and builds a module configuration before running the application.

There are two cases:

- **Explicit module:** The JAR contains `module-info.class`. The module name and dependency relationships are declared in the descriptor. A module reads only the modules it declares via `requires`; external code can access only the packages that are `exports`-ed. Deep reflection access also depends on `opens` or `open module`.
- **Automatic module:** The JAR does not have `module-info.class`. Java creates a module whose name is taken from the `Automatic-Module-Name` attribute in the manifest if present; otherwise, the name is derived from the JAR file name. An automatic module reads other modules and exports all packages, helping legacy libraries participate in the module path during a transition period.

An automatic module has a module name and participates in module resolution, even without a descriptor declared by the library author. It is a compatibility bridge and does not provide the strict encapsulation of an explicit module.

## 3. How Is the Same JAR Interpreted Differently?

| Contents of the JAR | When placed on the classpath | When placed on the module path |
|---|---|---|
| Has `module-info.class` | Descriptor is ignored; classes belong to the unnamed module | Is an explicit module; descriptor is enforced |
| Does not have `module-info.class` | Classes belong to the unnamed module | Is an automatic module; name is derived or taken from the manifest |
| Has `Automatic-Module-Name` | This attribute does not create a module on the classpath | The attribute is used as the automatic module name |
| Has a non-exported package | The package can still be used according to normal Java access modifiers | Other modules cannot access that package across the module boundary |
| Has a package needing deep reflection | No JAR module boundary blocks reflection | Requires the package to be opened via `opens` or an appropriate opening mechanism |

The biggest difference is module identity and access boundaries. A public class in a non-exported package can be used by a classpath application, whereas an application in a named module cannot access that package if the containing module does not export it. Similarly, a library using deep reflection may work on the classpath but encounter `InaccessibleObjectException` when running under an explicit module that has not opened the corresponding package.

## 4. Differences Likely to Appear in Applications

### Readability and Dependency

The unnamed module reads other modules. Conversely, a named module does not automatically read the unnamed module. Therefore, an application that has moved to the module path may not see a library placed only on the classpath, even though that library is present in the launch command. Check the module's `requires` declarations and the actual placement of each dependency.

### Export and Reflection

`exports` allows other modules to access public types in the exported package. `opens` allows frameworks or reflection libraries to perform deep reflection into the package according to the declared scope. These two directives serve different purposes: export is for Java-level type access; open is for reflection.

### Service Loading and Resource Scanning

Classpath applications commonly declare `ServiceLoader` providers via the file `META-INF/services/<interface-name>`. Modular applications can declare `uses` and `provides ... with ...` in `module-info.java`. When moving a JAR between the two locations, check how the library registers and discovers providers.

Some frameworks scan classes based on the classpath or the `java.class.path` property. When a library moves to the module path, that scanning approach may no longer see all JARs/resources as before. The outcome depends on the framework and how it supports the module path.

### Duplicate Packages

The classpath can accept classes from multiple JARs contributing to the same package. On the module path, having two named modules contain the same package can cause a split-package error when building the module configuration. Therefore, a packaging layout that previously worked on the classpath can fail once split into multiple named modules.

## 5. Launch Examples

Suppose `lib.jar` is a library with a module descriptor:

```java
module com.example.lib {
    exports com.example.lib.api;
}
```

The modular application declares:

```java
module com.example.app {
    requires com.example.lib;
}
```

When running on the classpath, the descriptors of both JARs are ignored. Example on Windows:

```shell
java -cp "app.jar;lib.jar" com.example.app.Main
```

When running as a modular application, place both JARs in the `mods` directory and launch the module:

```shell
java --module-path mods --module com.example.app/com.example.app.Main
```

In the second command, Java resolves `com.example.app`, reads `requires com.example.lib`, and allows the application to access only the packages exported by the library. If `lib.jar` does not export the package containing a type used by the application, compilation or execution will report a module access error.

For a legacy JAR without `module-info.class`, placing it on the module path turns it into an automatic module. A named-module application must use the exact automatic module name in `requires`; `Automatic-Module-Name` should be declared in the manifest so the name does not change when the JAR file name changes.

## 6. How to Determine Which Mode a JAR Is Using

The following commands can be used to inspect artifacts and module resolution:

```shell
# View the descriptor or automatic module name of a JAR
jar --describe-module --file lib.jar

# Display modules resolved when launching a modular application
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
```

When an application behaves differently across an IDE, Gradle/Maven, and the command line, compare the actual Java command from each environment. Check `-cp`, `--class-path`, `--module-path`, module descriptors, the dependency graph, and flags that open modules. Configuration in the build file is not enough to conclude which mode the JVM is receiving the JAR in; the final launch command reveals that.

## 7. Selection Guidelines

- Use the classpath when maintaining a legacy application that does not yet need module boundaries.
- Use the module path with explicit modules when you want clear dependency declarations, control over exported packages, and restricted reflection.
- Use automatic modules as a transition step for legacy libraries; prefer a stable name via `Automatic-Module-Name`, then add `module-info.java` when the library is ready.
- Do not place the same artifact on both the classpath and the module path in the same application without a clear reason; duplicate loading can create unpredictable class identities and dependencies.
- When migrating an application from the classpath to the module path, re-check `requires`, `exports`, `opens`, service providers, resource scanning, and split packages.

The Java Platform Module System has existed since Java 9. Therefore, when investigating different behaviors, verify the running JDK and the actual location of the JAR before modifying source code.
