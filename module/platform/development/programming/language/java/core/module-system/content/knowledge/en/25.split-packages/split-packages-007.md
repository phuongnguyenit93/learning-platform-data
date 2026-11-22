# Moving Packages to Fix Split Packages in the Java Module System

## 1. Objectives

In a Java project running on the classpath, multiple JARs can contain classes belonging to the same package. When migrating to the Java Platform Module System (JPMS), this organization can create a **split package**: the same package name appears in multiple modules.

A split package becomes a problem when the module graph causes one module to read multiple modules that contain or export that package. The resolver cannot provide a consistent package view to the consuming module, so resolution can fail with an error like:

~~~text
Module com.example.app reads package com.example.shared
from both com.example.alpha and com.example.beta
~~~

A sustainable approach is to identify the module that owns the package, then move all related parts of the package into a single module or rename packages if the parts genuinely belong to two independent domains. Both the source tree, module descriptors, and accompanying references must be updated.

After this article, you will be able to:

- Identify a split package and understand the conditions that cause module resolution conflicts.
- Choose the owning module of a package based on responsibilities and dependencies.
- Move source files without missing package declarations, module descriptors, resources, and tests.
- Handle new dependencies without creating dependency cycles.
- Compile and re-verify the module graph after refactoring.

## 2. What Is a Split Package?

Suppose there are two modules:

- `com.example.alpha`
- `com.example.beta`

Both contain classes in the package `com.example.shared`:

~~~text
src/
├── com.example.alpha/
│   ├── module-info.java
│   └── com/example/shared/AlphaHelper.java
└── com.example.beta/
    ├── module-info.java
    └── com/example/shared/BetaHelper.java
~~~

The module descriptors may be exporting the same package:

~~~java
// com.example.alpha/module-info.java
module com.example.alpha {
    exports com.example.shared;
}
~~~

~~~java
// com.example.beta/module-info.java
module com.example.beta {
    exports com.example.shared;
}
~~~

The application consumes both:

~~~java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
~~~

When app reads both modules and both export `com.example.shared`, the resolver encounters two sources providing the same package to the same consuming module. This is a classic split package case and can prevent the configuration from resolving.

You should not assume that merely seeing the same package name in any two modules immediately causes every configuration to fail. The key resolution rule is that a module cannot read multiple modules that both export that package. Even so, splitting a package across multiple modules often makes ownership boundaries and access permissions hard to reason about; you should design so each package has one clear module owner.

## 3. Why Can the Classpath Run While Named Modules Fail?

On the classpath, JARs are typically loaded into the unnamed module. The class loader can find classes of the same package from multiple JARs, as long as no other issues arise such as duplicate class names or classpath ordering issues.

With named modules, the module descriptor specifies which module owns a package and which modules are allowed to read that package. The module system checks these relationships when building a configuration. Having a package split across multiple modules can cause a consumer to read multiple identically named package sources, creating ambiguity.

Beyond resolution errors, package-private access also requires attention. Two classes both declaring `package com.example.shared;` yet residing in two different named modules do not automatically belong to the same runtime package to access each other's package-private members. Sharing a package name in source code does not erase module boundaries.

Therefore, a split package is not merely an issue of which directory files are placed in. It involves module ownership, readability, exports, and encapsulation.

## 4. Choosing the Package-Owning Module Before Moving

Before editing files, determine which responsibility the package belongs to.

There are three common approaches:

1. **Move the entire package into an existing module:** suitable when the classes are genuinely part of that module. The other module will depend on the owning module.
2. **Create a shared module with a clear responsibility:** suitable when the package is an API or capability used independently by multiple modules. Avoid turning this module into a dumping ground for unrelated utility classes.
3. **Split into two distinctly named packages:** suitable when classes currently in the same package actually belong to two different business domains. Rename the packages so each domain has its own namespace, then place each package in its corresponding owning module.

Do not pick a module merely because it already happens to have a few classes in the package. Consider class dependencies, public APIs, lifecycles, ownership, and avoiding dependency cycles.

If alpha needs beta and beta needs alpha after moving, do not add bidirectional `requires` to force a build. Extract a stable contract into a small API module or adjust responsibility boundaries.

## 5. Example: Consolidating a Package into One Owning Module

Suppose `com.example.shared` is a genuinely shared package. We create an owning module `com.example.shared` and move both classes there.

Before moving:

~~~text
src/
├── com.example.alpha/
│   ├── module-info.java
│   └── com/example/shared/AlphaHelper.java
├── com.example.beta/
│   ├── module-info.java
│   └── com/example/shared/BetaHelper.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

After moving:

~~~text
src/
├── com.example.shared/
│   ├── module-info.java
│   └── com/example/shared/
│       ├── AlphaHelper.java
│       └── BetaHelper.java
├── com.example.alpha/
│   └── module-info.java
├── com.example.beta/
│   └── module-info.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

The owning module declares:

~~~java
module com.example.shared {
    exports com.example.shared;
}
~~~

Both alpha and beta modules declare the dependency:

~~~java
module com.example.alpha {
    requires com.example.shared;
}
~~~

~~~java
module com.example.beta {
    requires com.example.shared;
}
~~~

The app module still requires alpha and beta if it uses APIs from both:

~~~java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
~~~

If app needs to directly call classes in `com.example.shared`, app also needs to declare `requires com.example.shared;`. Readability does not automatically propagate from alpha to app in a way that lets app read all of alpha's dependencies; plain `requires` is not transitive.

After the change, only the `com.example.shared` module contains and exports the package `com.example.shared`. Alpha and beta use that package via a dependency on the owner.

If the helpers only serve internal needs of alpha or beta, consider moving them into each respective module's own package instead of creating a shared module. The goal is for one package to have one logical owner, not to create an extra module for every group of classes.

## 6. Steps for Moving Source Files

Perform the move in a controllable sequence:

1. **List classes in the package:** find every file declaring `package com.example.shared;` across module source roots. Identify classes, `package-info.java`, test files, and related resources.
2. **Choose an owner:** decide which module will contain the package after refactoring. Check class dependencies to avoid creating `requires` cycles.
3. **Move files:** place source files into the right package directory under the owner's source root. If renaming the package, update both the directory and the `package` statement in source files.
4. **Update module descriptors:** add `exports` or qualified `exports` in the owner when consumers need API access. Add `requires` in consumers; remove old exports from modules that no longer own the package.
5. **Update references:** fix imports if the package name changed. If the package name stays the same while the owning module changed, Java imports might not change, yet module descriptors and build dependencies must change.
6. **Move tests and resources:** place tests according to the new module; verify resource paths, `module-info.java`, test fixtures, and packaging configs.
7. **Build all consumers:** compile the owning module first or in the same modular compilation pass, then compile all dependent modules and run tests.

Do not leave a subset of classes from the package in the old module. After moving, the old module should no longer have source files or package outputs belonging to that package.

## 7. References Frequently Missed

Moving a package does not only affect Java files with direct imports.

- **`package-info.java`:** annotations and Javadoc attached to the package must move with the package owner or be updated when renamed.
- **`module-info.java`:** update `exports`, `opens`, `uses`, `provides` if the package contains service types or provider implementations.
- **Reflection:** class/package name strings in `Class.forName`, framework configs, dependency injection, serialization, or mappings must be updated if the package name changes.
- **Resources:** check files loaded via `Class.getResource`, `ClassLoader.getResource`, or resource paths relative to the package.
- **Service providers:** if an implementation is declared with `provides Service with Provider`, ensure the provider class stays in an appropriate module and the descriptor is updated. If using classpath service configuration, update `META-INF/services` files.
- **Tests and builds:** update source sets, test module descriptors, module paths, plugin configs, Javadoc, and launch scripts.
- **API consumers:** if public classes move to a different module, consuming modules must read the new module and the owning module must export the required package.

If the package name does not change, imports may still compile as before once module dependencies are updated. However, that does not mean migration is complete: the module graph, resources, and reflection still need verification.

## 8. When to Rename a Package Instead of Consolidating

Not every two groups of classes sharing a package name should be placed in one module. For example, a third-party library and internal code both use the package `com.example.util`, yet they do not share responsibilities or APIs.

You can rename the internal code's package to a dedicated namespace:

Before:

~~~java
package com.example.util;

public final class InternalDateParser {
    // ...
}
~~~

After:

~~~java
package com.example.app.internal.date;

public final class InternalDateParser {
    // ...
}
~~~

Corresponding directory structure:

~~~text
com.example.app/
├── module-info.java
└── com/example/app/internal/date/
    └── InternalDateParser.java
~~~

This keeps internal code inside the app module and avoids package contention with the library. Renaming a package changes the class's fully qualified name, so you must update consumers, reflection configurations, serialization, and data storing class names.

For published public APIs, renaming a package can be a breaking change. You need a versioning plan, migration guide, or facade/adapter layer during a transition period if backward compatibility is required.

## 9. Compiling and Verifying After Moving

With a modular source tree, you can compile the involved modules using:

~~~bash
javac --module-source-path src -d out \
    -m com.example.shared,com.example.alpha,com.example.beta,com.example.app
~~~

If the owner has already been built into a modular JAR, place that JAR on the module path when compiling consumers:

~~~bash
javac --module-path libs -d out \
    --module-source-path src \
    -m com.example.alpha,com.example.beta,com.example.app
~~~

Run the application:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

You can inspect the owner's descriptor:

~~~bash
java --module-path out --describe-module com.example.shared
~~~

And observe the graph at runtime:

~~~bash
java --show-module-resolution --module-path out \
    --module com.example.app/com.example.app.Main
~~~

When confirming the migration:

- Build all modules that have dependencies on the package.
- Run unit tests and integration tests of the owner and consumers.
- Confirm the owning module exports the right required packages.
- Confirm the old module no longer contains that package in its output or JAR.
- Search for package declarations again to ensure no unexpected duplicates remain.
- Verify reflection, service provider, and resource configurations.
- Inspect the final release artifacts, not just the source tree in the IDE.

If using modular JARs, you can inspect module contents with:

~~~bash
jar --describe-module --file libs/com.example.shared.jar
~~~

## 10. Why Workarounds Should Not Be Used to Mask Split Packages

Some runtime options can help handle module access issues, but they are not general solutions for split packages:

- `--add-reads` adds readability; it does not merge packages from two modules.
- `--add-exports` grants package access; it does not transfer package ownership.
- `--add-opens` serves deep reflection; it does not fix package conflicts in the module graph.
- `--patch-module` adds classes/resources to a specific module and can be used in tests or compatibility workarounds; it does not replace identifying the owning module and packaging source properly.

If a resolution error says a consumer reads the same package from two modules, fix the package/module structure or module relationships so the consumer has only one source for the package. Adding access permissions does not remove the root cause.

## 11. Key Takeaways

- A split package is the condition where the same package name appears in multiple modules.
- A typical conflict occurs when one module reads two modules that both export that package.
- Choose one owning module for the package; move all related classes to the owner or rename the package when the two code groups belong to independent domains.
- Update `requires`, `exports`, `opens`, `uses`, `provides`, and consumers accordingly.
- Check package-private access, reflection, resources, service providers, tests, and build scripts after moving.
- Build the entire module graph and verify the old module no longer contains the moved package.

Start by identifying which package has multiple owners and which module truly needs to own it. A single controlled migration, paired with updating descriptors and consumers, eliminates the conflict at the root and keeps module boundaries clear.
