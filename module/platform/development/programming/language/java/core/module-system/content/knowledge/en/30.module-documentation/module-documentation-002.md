# module-info.java with API Annotations

In the Java Platform Module System (JPMS), the `module-info.java` file is the contract declaration point of a named module: the module name, dependencies, packages exposed or opened for reflection, as well as the services the module uses or provides.

When building a modular library for others to use, the descriptor should not just be “enough to compile”. It is also the right place to write **module-level Javadoc** — explaining the module's purpose, user-facing APIs, meaningful dependencies, service usage, and compatibility limits. These annotations help API documentation convey *why* the module exists and *how* to use it, rather than merely listing technical structure.

Key point: **Javadoc placed immediately before the `module` declaration in `module-info.java` will be used by the `javadoc` tool to generate the module description page.** The `requires`, `exports`, `opens`, `uses`, and `provides` directives are still parsed by the compiler according to JPMS semantics; comments do not alter these permissions.

## 1. The role of module-info.java in public documentation

A minimal module descriptor:

~~~java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
~~~

From this descriptor, tools can determine:

- The module name is `com.acme.catalog`.
- The module has a dependency on `java.logging`.
- The `com.acme.catalog.api` package is exported.

However, the compiler cannot infer what API users need to know:

- What functionality does the module provide?
- Which type should consumers start with?
- Which packages are stable public APIs?
- Are there service providers or extension points?
- Does using the API require any configuration or lifecycle conventions?
- Which implementation packages are intentionally kept private?

Module-level Javadoc is where these questions are answered. The descriptor and documentation serve complementary roles: the descriptor enforces accessibility, while Javadoc presents meaning and usage guidance.

## 2. Writing Javadoc immediately before the module declaration

Common style:

~~~java
/**
 * Provides the product catalog management API.
 *
 * <p>Consumers use {@link com.acme.catalog.api.Catalog}
 * to look up product information. The module exposes the
 * {@code com.acme.catalog.api} package; implementation classes
 * are kept in unexported packages.
 *
 * <p>Example consumer descriptor:
 * <pre>{@code
 * module com.acme.shop {
 *     requires com.acme.catalog;
 * }
 * }</pre>
 *
 * @since 1.0
 */
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
~~~

Points to note:

- Start with `/**` and end with `*/` to create a **Javadoc comment**, not a regular comment.
- Place the comment immediately before `module com.acme.catalog { ... }`.
- Summarize the module's purpose in a clear first sentence.
- Use valid HTML/Javadoc tags such as `<p>`, `{@code ...}`, and `{@link ...}`.
- Optionally add `@since` to record the milestone when the API was introduced.

For example, using only:

~~~java
// Catalog management module
module com.acme.catalog { ... }
~~~

makes the comment helpful to source readers, but it is not treated as Javadoc describing the module in the generated API documentation page.

Nor should you put module Javadoc on an arbitrary class and expect `javadoc` to attach it to the module summary page.

## 3. What content to write at the module level?

Module-level Javadoc should focus on module-wide information.

A practical structure:

1. **A defining sentence:** what core functionality the module provides.
2. **Public API:** packages and entry points users need to call.
3. **Integration:** services, dependencies, or frameworks consumers need to know about.
4. **Usage example:** minimal descriptor and starter code snippet.
5. **Limitations:** unsupported parts or implementation details not to depend on.
6. **Compatibility:** `@since` milestones, migration notes, or significant contract changes.

There is no need to repeat the entire list of classes on the module page. Classes, methods, and packages already have their own Javadoc pages. Module-level documentation should serve as a map guiding readers to the right API.

A useful opening example:

~~~java
/**
 * Product catalog reading and searching API for retail applications.
 *
 * <p>Start with {@link com.acme.catalog.api.Catalog}.
 * Search logic can be extended via the
 * {@link com.acme.catalog.spi.CatalogPlugin} service.
 *
 * <p>The module does not expose the
 * {@code com.acme.catalog.internal} package; consumers should not
 * reference the implementation package.
 *
 * @since 1.0
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

Here, the prose explains the public usage boundary, while the `exports` directive enforces that boundary.

## 4. Module Javadoc and package Javadoc complement each other

A modular project typically has this structure:

~~~text
src/
└── com.acme.catalog/
    ├── module-info.java
    └── com/acme/catalog/
        ├── api/
        │   ├── package-info.java
        │   └── Catalog.java
        ├── spi/
        │   ├── package-info.java
        │   └── CatalogPlugin.java
        └── internal/
            └── DefaultCatalogPlugin.java
~~~

Documentation should be split across the right levels:

| Location | Appropriate content |
| --- | --- |
| `module-info.java` | Module purpose, public surface, integration model, overall examples |
| `package-info.java` | Role and conventions of the package, API scope within the package |
| Class/interface Javadoc | Type responsibility, lifecycle, thread-safety, instantiation examples |
| Method Javadoc | Parameters, return values, exceptions, side effects, pre/postconditions |
| External README | Build instructions, operations, setup, and details unsuitable for API reference |

Package documentation example:

~~~java
/**
 * Public entry points for querying the catalog.
 *
 * <p>External applications should depend only on the
 * interfaces and types described in this package.
 *
 * @since 1.0
 */
package com.acme.catalog.api;
~~~

And type Javadoc:

~~~java
package com.acme.catalog.api;

/**
 * Gateway for querying product information.
 *
 * <p>Implementations may read data from multiple sources.
 *
 * @since 1.0
 */
public interface Catalog {

    /**
     * Finds a product by identifier.
     *
     * @param id product identifier, must not be {@code null}
     * @return product if present
     * @throws IllegalArgumentException if id is invalid
     */
    java.util.Optional<Product> findById(String id);
}
~~~

Separating documentation levels keeps the module summary concise while still leading users to the details they need.

## 5. Describing requires: explain dependencies, don't just list them

A module may have directives:

~~~java
module com.acme.reporting {
    requires java.logging;
    requires com.acme.catalog;
}
~~~

Javadoc should explain notable dependencies:

~~~java
/**
 * Generates summary reports from catalog data.
 *
 * <p>The module uses {@code com.acme.catalog} as its data
 * source and {@code java.logging} to record events.
 *
 * <p>Consumers only need to depend on
 * {@code com.acme.reporting} if they do not directly
 * use types from the dependency modules.
 */
module com.acme.reporting {
    requires java.logging;
    requires com.acme.catalog;
    exports com.acme.reporting.api;
}
~~~

Distinguish clearly:

- `requires x`: the current module reads module `x`.
- `requires transitive x`: readability to `x` can be passed on to consumers that read the current module under JPMS rules.
- `requires static x`: dependency required at compile-time but not required to be present at runtime.

Javadoc can explain why `transitive` or `static` is used, but only the **actual directive in the descriptor** alters the module graph. Writing “this dependency is optional” in Javadoc does not substitute for `requires static` or the application's optional-dependency handling logic.

For public APIs returning types belonging to another module, consider `requires transitive` when that type is part of the contract consumers must read. This is a module design decision, not a documentation formatting choice.

## 6. Describing exports: what is the public API?

Example:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

These are packages exported unconditionally to modules with appropriate readability. In module-level documentation, state the purpose of each package:

~~~java
/**
 * Provides the API and extension points for catalog.
 *
 * <ul>
 *   <li>{@code com.acme.catalog.api}: API used by applications.</li>
 *   <li>{@code com.acme.catalog.spi}: service contract
 *       for provider modules.</li>
 * </ul>
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
}
~~~

If using qualified exports:

~~~java
exports com.acme.catalog.maintenance to com.acme.admin;
~~~

explicitly note that this is an integration dedicated to module `com.acme.admin`, not a public API for general consumers. The prose and directive must align: documentation should not advise general users to import a package exported only to a specific module.

A package containing `public` classes that is not exported still does not become a public API for other modules. Javadoc does not relax that boundary.

## 7. Describing opens: scoped reflection permissions

Frameworks such as ORMs or serializers may need deep reflection into implementation packages. The descriptor can declare:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;

    opens com.acme.catalog.internal
        to com.acme.serializer;
}
~~~

In module Javadoc, describe why that permission exists:

~~~java
/**
 * Product catalog API.
 *
 * <p>Package {@code com.acme.catalog.internal}
 * is not a public API. It is opened only to module
 * {@code com.acme.serializer} to read object metadata
 * during serialization.
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.serializer;
}
~~~

Distinguish:

- `exports p`: allows access to public types/members from modules that read the source module.
- `opens p`: allows deep reflection into the package from other modules.
- `opens p to m`: grants deep reflection only to target module `m`.
- `open module`: opens all packages of the module for reflection.

Documentation should not claim that `opens p to m` makes the package a compile-time API for `m`. `opens` does not replace `exports`; if consumers need to import types from a package, design a public API and export it accordingly.

If a framework lacks a module name and runs on the classpath, configuring `--add-opens ...=ALL-UNNAMED` may be used as a migration step. That is an operational option to document separately, not a valid module name to write after `to` in `module-info.java`.

## 8. Documenting uses and provides with @uses, @provides

ServiceLoader and service binding are key parts of JPMS. Javadoc has block tags supporting module-level service documentation:

- `@uses service.type description`: explains a service consumed by the module.
- `@provides service.type description`: explains a service for which the module provides an implementation.

Example:

~~~java
/**
 * Module extending catalog through service providers.
 *
 * <p>Applications can integrate custom plugins via
 * {@link com.acme.catalog.spi.CatalogPlugin}.
 *
 * @uses com.acme.catalog.spi.CatalogPlugin
 *       Discovers plugins used to supplement catalog data sources.
 *
 * @provides com.acme.catalog.spi.CatalogPlugin
 *       Provides the default implementation inside the module.
 *
 * @since 1.0
 */
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;

    uses com.acme.catalog.spi.CatalogPlugin;

    provides com.acme.catalog.spi.CatalogPlugin
        with com.acme.catalog.internal.DefaultCatalogPlugin;
}
~~~

The `uses` and `provides` directives are the **machine-readable** part of the module descriptor. The two corresponding Javadoc tags provide only **human-readable descriptions**.

Keep them synchronized:

- Whenever `uses` is declared, describe the purpose of discovering providers and when they are used.
- Whenever `provides` is declared, describe the type of implementation or feature supplied.
- Do not write tags for services that no longer exist in the descriptor or are no longer part of the published contract.
- Do not include confidential implementation details in public docs if they are not part of the API contract.

For a module that consumes a service without supplying a provider, only `uses` and `@uses` are needed. Conversely, a dedicated provider module typically has `provides` and `@provides`.

## 9. Complete module-info.java example with API annotations

A reference descriptor:

~~~java
/**
 * Provides the API, SPI, and default implementation
 * for the product catalog.
 *
 * <p>Applications start from
 * {@link com.acme.catalog.api.Catalog}.
 * Package {@code com.acme.catalog.api} is the usage surface
 * intended for clients. Package {@code com.acme.catalog.spi}
 * contains the extension contract via ServiceLoader.
 *
 * <p>Consumer module example:
 * <pre>{@code
 * module com.acme.shop {
 *     requires com.acme.catalog;
 * }
 * }</pre>
 *
 * <p>Do not use classes in
 * {@code com.acme.catalog.internal} as a stable API.
 *
 * @uses com.acme.catalog.spi.CatalogPlugin
 *       Discovers providers extending catalog data.
 *
 * @provides com.acme.catalog.spi.CatalogPlugin
 *       Provides a default provider so the application can run
 *       when no external plugin is installed.
 *
 * @since 1.0
 */
module com.acme.catalog {
    requires java.logging;

    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;

    uses com.acme.catalog.spi.CatalogPlugin;

    provides com.acme.catalog.spi.CatalogPlugin
        with com.acme.catalog.internal.DefaultCatalogPlugin;
}
~~~

In the corresponding source tree, the following must actually exist:

~~~text
com.acme.catalog/
├── module-info.java
└── com/acme/catalog/
    ├── api/
    │   └── Catalog.java
    ├── spi/
    │   └── CatalogPlugin.java
    └── internal/
        └── DefaultCatalogPlugin.java
~~~

The implementation `DefaultCatalogPlugin` must satisfy service provider rules, such as implementing the `CatalogPlugin` interface and having a valid constructor or provider method under JPMS rules.

This is an example of consumer-oriented documentation: readers see the module purpose, entry point, exported API/SPI, services, and what is not guaranteed. The compiler uses only the directives to enforce module semantics; `javadoc` uses the descriptions to build documentation.

## 10. Generating module documentation via the javadoc CLI

With a modular source tree:

~~~text
project/
└── src/
    ├── com.acme.catalog/
    │   ├── module-info.java
    │   └── com/acme/catalog/...
    └── com.acme.shop/
        ├── module-info.java
        └── com/acme/shop/...
~~~

You can generate Javadoc for a single module:

~~~bash
javadoc \
  --module-source-path src \
  --module com.acme.catalog \
  -d docs
~~~

Or for multiple modules:

~~~bash
javadoc \
  --module-source-path src \
  --module com.acme.catalog,com.acme.shop \
  -d docs
~~~

After the tool finishes, the `docs` directory contains generated HTML pages for the modules, packages, and exposed APIs according to Javadoc configuration. In the generated docs, locate the **Module com.acme.catalog** page (usually a `module-summary.html` page in the module directory) to view the description from `module-info.java`.

Operational points:

- Use a JDK that includes the `javadoc` tool and supports JPMS.
- All types referenced in `{@link ...}` must be present within the source/dependency scope analyzed by Javadoc.
- For external dependencies, supply an appropriate `--module-path` if the sources are not self-contained.
- Paths containing spaces must be quoted per shell rules.
- Projects not using the `src/<moduleName>/...` layout need to adjust `--module-source-path` accordingly.

Example with out-of-source dependencies:

~~~bash
javadoc \
  --module-source-path src \
  --module-path libs \
  --module com.acme.catalog \
  -d docs
~~~

The doc-generation command does not replace the modular JAR build step. Javadoc publishes API documentation; `javac` and `jar` are responsible for compiling and packaging runnable artifacts.

## 11. Integrating Javadoc generation into build tools

In a Maven project with source placed at `src/main/java/module-info.java`, Javadoc is typically generated using the Maven Javadoc Plugin with appropriate JDK/plugin configuration:

~~~bash
mvn javadoc:javadoc
~~~

The default output usually resides in the site directory managed by Maven, such as `target/site/apidocs`, depending on plugin configuration.

You can publish a Javadoc JAR for consumers to inspect the API:

~~~bash
mvn javadoc:jar
~~~

In the Gradle Java Plugin, the `javadoc` task generates API documentation:

~~~bash
./gradlew javadoc
~~~

Documentation is typically generated into `build/docs/javadoc`. When a project has `module-info.java`, ensure the toolchain and module path configuration are passed properly to the JavaDoc task. Task names and behavior may depend on the plugin version and build logic.

CI pipelines should run docs on the same Java release used for the source. If documentation references APIs unavailable on the target Java release, Javadoc or the compiler may report errors even though the prose looks valid.

## 12. Javadoc does not replace the module descriptor

Some common misconceptions:

| Wrong assumption | Correct understanding |
| --- | --- |
| Writing `@uses` creates a service dependency | Requires the `uses ServiceType;` directive in the descriptor |
| Writing `@provides` registers a provider | Requires `provides ServiceType with Impl;` |
| Stating a package is public in Javadoc lets consumers import it | Requires an appropriate `exports package.name;` |
| Stating “framework can reflect” grants `setAccessible` rights | Requires `opens` or appropriate runtime `--add-opens` |
| Mentioning a dependency in Javadoc text lets the module read it | Requires `requires` or a valid readability relationship |
| Having a comment in `module-info.java` documents every class | Requires sources/types and Javadoc config to generate corresponding API pages |
| Javadoc showing a module means JAR packaging is valid | Must inspect `module-info.class` in the actual artifact |

Javadoc is the **descriptive** interface. JPMS enforces permissions based on the **compiled descriptor** and runtime configuration. Both layers must agree, but neither automatically substitutes for the other.

## 13. Using Javadoc links within the right scope

A good module page should link to entry points rather than writing every detail right in the introduction.

Example:

~~~java
/**
 * Report processing module.
 *
 * <p>To generate reports, use
 * {@link com.acme.reporting.api.ReportGenerator}.
 *
 * <p>Refer to
 * {@link com.acme.reporting.api.ReportOptions}
 * for configuration options.
 */
module com.acme.reporting {
    exports com.acme.reporting.api;
}
~~~

`{@link ...}` creates a hyperlink to a type recognized by Javadoc. `{@code ...}` renders a code snippet without creating a hyperlink. Choose by intent:

- Use `{@link Type}` for types/methods readers should click into.
- Use `{@code identifier}` for module names, package names, and syntax that should simply be displayed.
- Use `<pre>{@code ...}</pre>` for multiline examples.
- Use `@see` when adding a supplementary reference entry.
- Use `@since` to record the milestone when an API appeared.

If documentation depends on the Java SE API, you can link to the platform Javadoc via the `javadoc` tool's external link configuration. For external library modules, ensure target docs exist and link configurations match versions to avoid broken links.

## 14. Documenting compatibility and evolution in module docs

When changing the module descriptor, update Javadoc if the change is meaningful to consumers.

Change example:

~~~java
// Old version:
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

To:

~~~java
// New version:
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi;
    uses com.acme.catalog.spi.CatalogPlugin;
}
~~~

Module-level documentation should clarify the new SPI, when consumers can use it, and how to install providers. `@since` on the SPI type can record the exact API version it appeared in.

If moving a public API from one package to another, documentation should point out the replacement package, deprecation policy, and migration path. Simply writing `@deprecated` in source does not create binary compatibility with code built against the old descriptor.

Changes requiring special attention in the public contract:

- Removing or narrowing `exports`.
- Renaming the module.
- Changing the service interface in `uses`/`provides`.
- Switching a package from exported to opened only.
- Introducing a type from another module into a public method signature, creating a new dependency.
- Changing Java release or runtime module requirements.

Documentation can warn users; actual migration still requires release notes, build compatibility tests, and a versioning strategy.

## 15. Inspecting generated documentation content

Once documentation builds complete, inspect both via tooling and by reading the output:

~~~bash
javadoc \
  --module-source-path src \
  --module com.acme.catalog \
  -d docs
~~~

Then open the module summary page in `docs` to check:

- Does the first descriptive sentence help identify the module's purpose?
- Are links to public entry points generated?
- Do service usages/providers match the actual descriptor?
- Do public packages have appropriate descriptions and package-info files?
- Do `requires` examples use the exact module name?
- Does the documentation avoid accidentally presenting an internal package as a stable API?
- Was Javadoc content updated when dependencies or service contracts changed?

You can enable Javadoc checks depending on your toolchain, such as `-Xdoclint:all`, to catch certain documentation and markup issues:

~~~bash
javadoc -Xdoclint:all \
  --module-source-path src \
  --module com.acme.catalog \
  -d docs
~~~

This is a quality check of the documentation build process in the sample project; it does not alter the module graph or descriptor used at runtime.

## 16. Common mistakes when writing module Javadoc

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No introduction appears on the Module page | Used `//` or `/* ... */` instead of Javadoc `/** ... */`, or comment misplaced | Place Javadoc immediately before the `module` declaration |
| `javadoc` reports type not found in `{@link}` | Source/module path lacks the type or type name is wrong | Check fully qualified name and dependencies when generating docs |
| API classes have pages, but module summary lacks description | Javadoc written only on classes, not on `module-info.java` | Add module-level Javadoc |
| Service is documented but does not work | Has `@uses`/`@provides` without the corresponding directive | Synchronize tags and descriptor |
| Module docs advise importing a package, but `javac` rejects it | Package is not exported to consumers | Fix the public API boundary or the documentation guide |
| Framework reflection fails even though module docs say “open” | Missing `opens` directive or wrong target module name | Check descriptor, module performing reflection, and runtime flags |
| Docs contain an example that compiles but fails to run properly | Example uses different module names/dependencies than actual artifact | Verify example on the appropriate module path |
| Module turns into an automatic module after packaging | `module-info.class` is misplaced or omitted by a build plugin | Inspect with `jar --describe-module --file artifact.jar` |

## 17. Recommended module documentation workflow

A consistent workflow when releasing a modular library:

1. **Choose module boundaries.** Define module name, public packages, implementation packages, and service contracts.
2. **Write the descriptor.** Correctly declare `requires`, `exports`, `opens`, `uses`, `provides`.
3. **Add module-level Javadoc.** Describe purpose, entry points, public packages, and integration.
4. **Add package-info.java.** Explain contracts of public packages, especially API and SPI.
5. **Write Javadoc for public types.** Explain method contracts, exceptions, nullability, lifecycle, and thread-safety as needed.
6. **Link across levels.** Use `{@link}` to navigate from module to classes/methods.
7. **Generate documentation.** Use `javadoc`, Maven Javadoc Plugin, or the corresponding Gradle task.
8. **Verify artifacts.** Ensure the modular JAR still contains a valid `module-info.class`.
9. **Update alongside API changes.** When the descriptor changes, update module docs and release notes accordingly.

A useful principle: **every major directive in the descriptor should have a design rationale maintainers can understand; every promise in Javadoc must be backed by the descriptor and public API.**

## Conclusion

`module-info.java` is the technical contract of a named module; Javadoc immediately before the `module` declaration is where that contract is explained to users. Good content should present the module's purpose, public API entry points, exported packages, reflection boundaries, notable dependencies, and service integration.

Combine module-level Javadoc with `package-info.java` and class/method Javadoc to provide documentation at the right level. Use `@uses` and `@provides` to explain services, but remember that tags only describe; actual directives determine service metadata. At release time, generate module pages with `javadoc` and inspect modular JAR artifacts to ensure documentation and JPMS boundaries stay consistent.
