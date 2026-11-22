# Module Javadoc and Package Javadoc

In the Java Platform Module System (JPMS), the **module descriptor** describes the technical boundaries of a module, while **Javadoc** helps readers understand its purpose, usage, limitations, and API contract. The two most important documentation levels are **module Javadoc** in `module-info.java` and **package Javadoc** in `package-info.java`.

Module Javadoc answers: *What is this module's responsibility, what APIs does it provide, what does it depend on, and how should it be used?* Package Javadoc answers: *What group of types does this package contain, what are the main concepts, and where should users start?*

Both are written as Java documentation comments `/** ... */`, but they are attached to different elements. When running the `javadoc` tool, they are compiled together with class, interface, constructor, and method documentation into a structured API documentation set.

**Principle:** documentation clarifies the API contract, but does not by itself alter `requires`, `exports`, `opens`, `uses`, or `provides`. Access control between modules is still determined by the module descriptor and JPMS rules.

## 1. Where does Module Javadoc live?

Module Javadoc is a documentation comment placed immediately before the `module` or `open module` declaration in the `module-info.java` file.

Example:

~~~java
/**
 * Provides the product catalog management API for the application.
 *
 * <p>This module exposes the
 * {@link com.example.catalog.api} package for clients
 * to create and query product information.
 *
 * <p>Implementation packages are not exported;
 * clients should not depend on internal storage details.
 *
 * @since 1.0
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

The comment sits **before** the `module` keyword. The Javadoc tool associates this description with the module's overview page.

Appropriate content at the module level includes:

- The module's role and scope of responsibility.
- Key API packages exposed.
- How to use the module and integration flow examples.
- Necessary requirements, limitations, or architectural principles.
- Service contracts that the module uses or provides.
- API version information, compatibility warnings, and operational conventions.

You should not turn module Javadoc into a duplicate listing of every method. Class and method details belong in Javadoc right on the class or method; the module page is for navigation and explaining the overall design.

## 2. Where does Package Javadoc live?

Modern package-level documentation is placed in the `package-info.java` file of that package itself.

Example for package `com.example.catalog.api`:

~~~java
/**
 * Public API for reading and manipulating catalog data.
 *
 * <p>The common entry point is
 * {@link com.example.catalog.api.CatalogService}.
 *
 * <p>This package contains stable contracts intended
 * for consumers. Implementations and persistence
 * are kept in other internal packages.
 *
 * @since 1.0
 */
package com.example.catalog.api;
~~~

The `package-info.java` file does not need to contain a public class. It typically consists of a Javadoc comment attached to the `package` declaration, and may include package annotations if the design calls for them.

Typical file placement looks like this:

~~~text
src/
└── com.example.catalog/
    ├── module-info.java
    └── com/example/catalog/
        ├── api/
        │   ├── package-info.java
        │   ├── CatalogService.java
        │   └── CatalogItem.java
        └── internal/
            ├── package-info.java
            └── InMemoryCatalogStore.java
~~~

Different `package-info.java` files in different packages have different content and purpose. The file in `api` can describe the public contract; the file in `internal` can guide maintainers, even though that package is not exported to consumers.

## 3. Comparing module and package documentation

| Criterion | Module Javadoc | Package Javadoc |
|---|---|---|
| Typical file | `module-info.java` | `package-info.java` |
| Scope | One named module | One Java package |
| Comment placement | Before the `module` declaration | Before the `package` declaration |
| Main content | Module purpose, API groups, integration, services | Package role, key types, usage rules |
| Documentation page | Module summary | Package summary |
| Encapsulation relation | Explains `exports` and module design | Explains API or internal package |
| Changes access control? | No | No |

Example of three documentation levels:

~~~text
Module: com.example.catalog
  └─ Why does it exist and what APIs does it expose?

Package: com.example.catalog.api
  └─ Which API types belong to this group?

Class: CatalogService
  └─ How is a type used and what contracts do its methods have?
~~~

Each level should complement the others. Avoid repeating long passages verbatim across module, package, and class levels, as duplicated content easily becomes inconsistent when the API design changes.

## 4. A complete modular example

Suppose there are two modules: one providing an API and an application module using that API.

~~~text
project/
└── src/
    ├── com.example.catalog/
    │   ├── module-info.java
    │   └── com/example/catalog/api/
    │       ├── package-info.java
    │       ├── CatalogItem.java
    │       └── CatalogService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Library module:

~~~java
/**
 * Shared catalog API for applications.
 *
 * <p>Clients should start with package
 * {@link com.example.catalog.api}.
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

API package:

~~~java
/**
 * Types used to describe and look up catalog items.
 *
 * <p>Includes {@link com.example.catalog.api.CatalogItem}
 * and {@link com.example.catalog.api.CatalogService}.
 */
package com.example.catalog.api;
~~~

A public record:

~~~java
package com.example.catalog.api;

/**
 * Represents an immutable catalog item.
 *
 * @param id non-blank identifier
 * @param name display name of the item
 */
public record CatalogItem(String id, String name) {
    public CatalogItem {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
    }
}
~~~

Interface:

~~~java
package com.example.catalog.api;

import java.util.Optional;

/**
 * Contract for looking up catalog items.
 */
public interface CatalogService {

    /**
     * Finds an item by its identifier.
     *
     * @param id identifier to look up
     * @return matching item or an empty Optional
     * @throws IllegalArgumentException if id is invalid
     */
    Optional<CatalogItem> findById(String id);
}
~~~

Consumer application:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

The example shows that `exports` and `requires` are module configuration, while Javadoc describes how to use them. The package comment connects `CatalogItem` and `CatalogService` into a meaningful API picture.

## 5. Javadoc does not replace the module descriptor

You can write a comment stating that a module provides the `com.example.catalog.api` package, but if the descriptor lacks the `exports` directive, other modules still cannot import the public types of that package under standard JPMS rules.

Example:

~~~java
/**
 * Has API at com.example.catalog.api.
 */
module com.example.catalog {
    // Missing exports!
}
~~~

Consumer:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Even though the comment says the API exists, the compiler still prevents the app from using an unexported package. To expose the API, there must be a real directive:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Conversely, simply adding `exports` will not make the documentation clear if module and package Javadoc are missing. Readers will see the types, but struggle to understand how to integrate, the contracts, and which parts should not be depended on.

**Documentation describes intent; the descriptor enforces technical boundaries.** The two sources must be consistent, but neither should be treated as a substitute for the other.

## 6. Module Javadoc and strong encapsulation

A named module can contain multiple packages while exporting only certain ones:

~~~java
/**
 * Data normalization library module.
 *
 * <p>The public API resides in
 * {@link com.example.normalize.api}.
 *
 * <p>Internal packages contain algorithms and adapters;
 * they are not guaranteed to be stable for consumers.
 */
module com.example.normalize {
    exports com.example.normalize.api;
}
~~~

The `com.example.normalize.internal` package can have its own documentation comment for maintainers:

~~~java
/**
 * Internal implementation components of the module.
 *
 * <p>Not a public API for other modules.
 * Classes may change without API compatibility
 * notice for external consumers.
 */
package com.example.normalize.internal;
~~~

A package having Javadoc **does not mean** that package is exported. Similarly, a class that is documented and declared `public` still does not become an API available to other modules if its package is not exported.

When publishing API documentation, the tool can be configured to display only public API content or include internal content as needed. You should not infer runtime access permissions from Javadoc visibility.

## 7. Qualified exports and documentation content

JPMS can export a package only to a specific list of modules:

~~~java
/**
 * Payment system integration module.
 *
 * <p>Package com.example.payment.bridge is an internal
 * contract intended only for designated adapters.
 */
module com.example.payment {
    exports com.example.payment.api;

    exports com.example.payment.bridge
        to com.example.checkout, com.example.admin;
}
~~~

The package Javadoc of `com.example.payment.bridge` should state clearly:

- Which modules are the intended consumers.
- Which parts of the package are stable contracts.
- Integration conditions or compatibility limitations.
- Why the package is not exported unconditionally.

This documentation helps readers understand the architecture, but qualified exports must still be declared accurately in the module descriptor. If a target module is renamed, updating only the Javadoc will not automatically update the `exports ... to` directive.

## 8. Module Javadoc with uses and provides

JPMS supports a service-oriented architecture using the `uses` and `provides` directives. Javadoc provides specialized block tags `@uses` and `@provides` to describe service semantics in module documentation.

Consumer module example:

~~~java
/**
 * Application extensible with document formatters.
 *
 * @uses com.example.spi.Formatter
 *       Discovers formatters provided by plugins.
 */
module com.example.app {
    requires com.example.spi;

    uses com.example.spi.Formatter;
}
~~~

Provider module example:

~~~java
/**
 * Provides a plain text formatting implementation.
 *
 * @provides com.example.spi.Formatter
 *           Default plain text formatter.
 */
module com.example.formatter.text {
    requires com.example.spi;

    provides com.example.spi.Formatter
        with com.example.formatter.text.TextFormatter;
}
~~~

Here:

- The `uses` or `provides` directive is module metadata that takes effect in JPMS.
- The `@uses` or `@provides` tag provides a **Javadoc description** for the corresponding service.
- Adding a documentation tag without the corresponding directive does not register a consumer or provider with ServiceLoader.
- A documentation tag does not instantiate anything on its own and does not change the behavior of `Configuration.resolveAndBind(...)`.

For a plugin system, module Javadoc is the right place to state the SPI contract, service purpose, provider requirements, and where to find implementation guides. Detailed documentation of the service interface itself should still live in that interface's Javadoc.

## 9. Linking between modules, packages, and classes

Javadoc can generate links to Java elements included in the documentation set.

Example in module-info.java:

~~~java
/**
 * Provides catalog operations.
 *
 * <p>The entry point is
 * {@link com.example.catalog.api.CatalogService}.
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

In package-info.java:

~~~java
/**
 * Catalog Public API.
 *
 * <p>To look up an item, use
 * {@link com.example.catalog.api.CatalogService#findById(String)}.
 *
 * @see com.example.catalog.api.CatalogItem
 */
package com.example.catalog.api;
~~~

Some useful syntax forms:

- `{@link Type}`: inserts an inline link to a type.
- `{@link Type#method(Type)}`: links to a method.
- `{@linkplain Type display label}`: links with a plain-text label.
- `{@code ...}`: displays a short code snippet in monospace font, avoiding markup interpretation.
- `{@literal ...}`: displays special characters literally.
- `@see`: adds a reference in the “See Also” section.
- `@since`: records the version milestone in which an API or module was introduced.
- `@deprecated`: explains why usage should not continue and the replacement if available.

When creating links, use fully qualified names or place appropriate imports/context so the tool can resolve the reference. If Javadoc reports `reference not found`, check the package/class names and whether the linked modules are within the documentation scope.

Do not replace all explanations with a list of links. Good Javadoc still needs natural-language descriptions before pointing to details.

## 10. package-info.java and package annotations

In addition to package Javadoc, `package-info.java` can hold annotations applied at the package level.

Hypothetical example with an annotation `@NonNullByDefault` declared for use on packages:

~~~java
/**
 * API for managing values and input validation rules.
 *
 * <p>This package uses a non-null-by-default convention
 * according to the static-checking library annotation.
 */
@NonNullByDefault
package com.example.validation.api;

import com.example.annotations.NonNullByDefault;
~~~

This is a syntax example; the `NonNullByDefault` annotation is **hypothetical**, provided by a library or project, not a built-in annotation in Java SE. It must have an appropriate `@Target(ElementType.PACKAGE)` and the module containing the annotation must be readable at compile time.

The file structure typically consists of:

1. Javadoc comment before the package declaration.
2. Package annotations, if any.
3. The `package qualified.name;` line.
4. Necessary imports for the annotations.

Do not use package-info.java as a place to declare regular classes or create implicit module dependencies. Relationships between named modules remain governed by `module-info.java`.

## 11. The javadoc tool for multiple source modules

The JDK provides the `javadoc` tool to generate HTML documentation from source. With a multi-module source tree:

~~~text
src/
├── com.example.catalog/
│   ├── module-info.java
│   └── com/example/catalog/api/
│       ├── package-info.java
│       ├── CatalogItem.java
│       └── CatalogService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

You can generate documentation with the command:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog,com.example.app \
        -d docs
~~~

Meaning:

- `--module-source-path src`: where to find module sources.
- `--module ...`: list of source modules to include in the documentation.
- `-d docs`: output directory for generated HTML.

After running, the documentation set typically includes module overview pages, package pages, and class or interface pages. The **module-summary.html** and **package-summary.html** pages help readers navigate from the module scope to a specific package.

If you only want documentation for one module:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog \
        -d docs/catalog
~~~

When a module depends on external precompiled JARs, add the appropriate module path so Javadoc can resolve types and dependencies:

~~~bash
javadoc --module-source-path src \
        --module-path lib \
        --module com.example.catalog \
        -d docs/catalog
~~~

If the documentation displays Vietnamese, you can configure consistent source/output encoding according to the JDK:

~~~bash
javadoc -encoding UTF-8 \
        -docencoding UTF-8 \
        -charset UTF-8 \
        --module-source-path src \
        --module com.example.catalog \
        -d docs/catalog
~~~

On Windows PowerShell or Command Prompt, you can put the entire command on a single line instead of using the Unix shell `` for line continuation. With multiple module paths on Windows, use a semicolon `;` between paths; Linux/macOS typically use a colon `:`.

## 12. Distinguishing javadoc, javac, and jar

These three tools relate to the same modular project but have different responsibilities:

| Tool | Primary output | Relation to Javadoc |
|---|---|---|
| `javac` | Compiles .java into .class and module-info.class | Reads/checks source but does not generate an API documentation website |
| `jar` | Packages classes/resources into a JAR | Can package the compiled module descriptor |
| `javadoc` | Generates API documentation, typically HTML | Reads module/package/class documentation comments |

Compilation example:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.catalog,com.example.app
~~~

Then generate docs:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog,com.example.app \
        -d docs
~~~

These are **two independent steps**. Successful compilation does not prove Javadoc references are valid; and successful Javadoc generation does not produce an executable application.

Javadoc pages should be generated from the exact released version of source/descriptors, avoiding cases where the documentation site claims a module exports a package while the actual artifact does not export it.

## 13. What does a module Javadoc page display?

Depending on the JDK version and `javadoc` options, the module summary page may include:

- Module description from the comment before the module declaration.
- Packages of the module within documentation scope.
- Information about dependencies and module relationships.
- Packages exported or opened according to the module descriptor.
- Services information from `uses` or `provides` and accompanying descriptions if present.

This is a useful view for introducing a module to newcomers joining the codebase. However, what is displayed also depends on tool visibility levels and documentation policies, such as API-only versus including implementations.

You should not rely on whether a documentation page displays a package to conclusively infer that the module is accessible at runtime. For actual diagnostics, inspect `module-info.java`, `ModuleDescriptor`, or resolved module information.

## 14. What should a package Javadoc page describe?

A good package Javadoc should answer these questions:

- What role does the package play in the module?
- Which important public types are the entry points?
- What are the package's common input, output, or error conventions?
- Which module do consumers need to read and what usage limitations apply?
- Is there a typical pattern or workflow when using the types?
- Is the package stable as a public API or just an implementation detail?
- Are there versioning and deprecation policies to be aware of?

Example for an integration package:

~~~java
/**
 * Integration contract for product data sources.
 *
 * <p>Consumers should implement
 * {@link com.example.catalog.spi.CatalogReader}.
 * The application discovers implementations via ServiceLoader.
 *
 * <p>Do not depend on implementation packages
 * of individual provider modules.
 *
 * @since 2.0
 */
package com.example.catalog.spi;
~~~

The Javadoc of `CatalogReader` then explains method details, exceptions, and implementation conditions. The package page does not need to repeat every method's `@param` and `@return`.

## 15. API documentation vs. internal documentation

A clearly organized module can use three layers of documentation:

**Public documentation.** For exported packages and public APIs. Focuses on contracts, compatibility, usage, and guaranteed boundaries.

**Restricted integration documentation.** For qualified exported packages or SPIs. Clearly states the intended consuming modules, integration conditions, and backward-compatibility policy.

**Internal documentation.** For non-exported packages. Focuses on algorithms, architecture, invariants, configuration, and implementation decisions for maintenance purposes.

Example:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;

    exports com.example.catalog.spi
        to com.example.catalog.runtime;
}
~~~

The `com.example.catalog.internal` package can still have a package-info.java so developers understand the code. Writing internal Javadoc does not force the module to export it.

You should not change the descriptor just because some packages or classes do not appear in the public API HTML docs. Documentation visibility needs and runtime access permissions are two independent concerns.

## 16. Documentation for services in a module

For a service contract, there are at least three places worth documenting:

1. **Consumer module** — why the module needs the service, described in `@uses`.
2. **Provider module** — what capability the module provides, described in `@provides`.
3. **Service interface** — required contract, exceptions, lifecycle, and implementation rules.

Service interface example:

~~~java
package com.example.spi;

/**
 * Data converter that can be supplied by plugins.
 */
public interface Converter {

    /**
     * Converts the input text.
     *
     * @param input text to process
     * @return converted text
     * @throws IllegalArgumentException if input is invalid
     */
    String convert(String input);
}
~~~

Provider descriptor:

~~~java
/**
 * Provider for uppercase normalization format.
 *
 * @provides com.example.spi.Converter
 *           Provides an uppercase converter for text.
 */
module com.example.converter.upper {
    requires com.example.spi;

    provides com.example.spi.Converter
        with com.example.converter.upper.UpperConverter;
}
~~~

Module documentation explains the provider's role, while interface Javadoc describes what every provider must obey. Module service docs do not replace the `provides` declaration or the provider class's implementation of the contract.

## 17. Versioning and stability policy

A module can change its implementation without changing its API. Therefore, Javadoc should distinguish stable commitments from internal details.

Appropriate content in public package docs:

- Meaning of public types.
- Behavior observable by consumers.
- Exception types guaranteed by the contract.
- Nullability or thread-safety conventions if specified by the API.
- Support introduction milestone via `@since`.
- Migration guidance for deprecated APIs.

Content that should not be treated as a public contract:

- Internal algorithm names that may change.
- Ordering of collection implementations.
- Class names residing in non-exported packages.
- Details that hold true only for a single implementation version.

Example when replacing an old API:

~~~java
/**
 * Old API used for legacy catalog.
 *
 * @deprecated Use
 * {@link com.example.catalog.api.CatalogService}
 * instead as of version 2.0.
 */
@Deprecated(since = "2.0")
public interface LegacyCatalog {
}
~~~

For public APIs, documentation should match annotations or actual code changes. Adding `@deprecated` in Javadoc without using `@Deprecated` on the code can send inconsistent signals to tools and users.

## 18. Using Javadoc to guide readers through the module graph

In a multi-module project, documentation should show how to navigate from the module-level overview to related packages and types.

Structure example:

~~~text
com.example.catalog.api
   exports com.example.catalog.api
             |
             v
       CatalogService
             |
             v
com.example.catalog.runtime
   requires com.example.catalog.api
             |
             v
    runtime implementation
~~~

The module Javadoc of `com.example.catalog.api` can explain that it contains only shared contracts; the runtime module implements those contracts. Package Javadoc points to the `CatalogService` interface. Interface Javadoc describes required behavior.

Good documentation does not need to list every edge in the module graph. Mention only the dependencies and integration points that truly matter to API users. If a dependency is an implementation detail, do not encourage consumers to depend on it directly.

When linking to modules or types in other modules, generate docs with the appropriate module path or source modules so the tool can resolve references. For external API documentation, consider Javadoc's linking options suited to your build and hosting environment.

## 19. Tailoring documentation to the audience

A README or package Javadoc may serve multiple groups:

- **API users:** need entry points, dependencies, and usage examples.
- **Service integrators:** need SPI interfaces, provider rules, and lifecycle.
- **Maintainers:** need module design, internal packages, and implementation boundaries.
- **Reviewers:** need to cross-check the descriptor's public surface against the documentation description.

Information should be tiered:

- Module comment: the big picture.
- Package comment: a group of related concepts.
- Type comment: class/interface meaning.
- Method comment: specific contract and edge cases.
- External README: build processes, installation, operations, or long examples.

Do not put deployment commands, personal machine details, secret configurations, or single-environment specifics into public API Javadoc.

## 20. Troubleshooting Javadoc generation errors

**Module summary page is missing.** Check whether the source has `module-info.java`, and whether `--module-source-path` and `--module` specify the correct module names.

**Package description is missing.** Check whether `package-info.java` exists with a documentation comment before the package declaration, whether the file is in the right package path, and whether the tool processes it.

**Link references cannot be resolved.** Check the fully qualified type/method name, source path, module path, and whether the linked element is within the documentation set.

**An internal package does not appear in public API docs.** Check Javadoc visibility settings and `exports` in the descriptor. Do not automatically export an internal package just to put it on the public pages.

**Javadoc reports HTML or special character errors.** Use `{@code ...}` or `{@literal ...}` to display special symbols, check HTML structure in documentation comments, and verify UTF-8 encoding.

**Compilation succeeds but javadoc fails.** The compiler and Javadoc tool serve different purposes; doc comment errors, missing links, or source/module path misconfigurations may only surface when generating documentation.

**Module Javadoc and descriptor are inconsistent.** The comment states the module exposes a package/service that the descriptor does not declare properly. Check the source descriptor; do not treat prose descriptions as a permission mechanism.

**Documentation still shows removed APIs.** Check the source version used to generate, CI cache, and output directory. Docs should be generated from the same artifact/source version as the release.

## 21. Workflow for writing module/package documentation

When a new module is created, you can follow this sequence:

1. Define module responsibilities and which API packages truly need to be exported.
2. Write module-info.java with appropriate `requires`, `exports`, `uses`, and `provides`.
3. Write a documentation comment before the module declaration.
4. Create package-info.java for key API packages.
5. In package docs, clearly indicate entry points and link to main types.
6. Write Javadoc for public classes/interfaces and the methods forming the contract.
7. If an SPI exists, add `@uses` / `@provides` describing services at the module level.
8. Use `javadoc` to generate doc pages; inspect module summary and package summary.
9. Fix Javadoc structure, reference, or encoding errors if reported by the tool.
10. Ensure published docs come from the exact released source and module descriptor version.

A reference command:

~~~bash
javadoc --module-source-path src \
        --module com.example.catalog \
        -encoding UTF-8 \
        -docencoding UTF-8 \
        -charset UTF-8 \
        -d docs
~~~

You can add lint or strict verification in CI per project policy. When checking options specific to your JDK, run `javadoc --help` and `javadoc -X`.

## 22. Self-check questions

1. Where is Module Javadoc placed in `module-info.java`?
2. Where is Package Javadoc placed in `package-info.java`?
3. Can a module comment automatically export a package by describing it in text?
4. How does Module Javadoc differ from Package Javadoc in scope and purpose?
5. Can an unexported package have a package-info.java?
6. Are `@uses` and `@provides` documentation tags or JPMS directives?
7. Which directives actually register service consumers/providers in the module system?
8. How does `{@link ...}` help readers navigate?
9. Which tool generates HTML API docs from modular source?
10. In `javadoc`, what roles do `--module-source-path` and `--module` play?
11. Why does documenting an internal package not mean that package is public?
12. When an API is deprecated, how should Javadoc and Java annotations be synchronized?
13. Why must docs be generated from the exact released source version?
14. Should long operational examples be placed in module Javadoc, package Javadoc, or a separate README?

**Conclusion:** `module-info.java` and `package-info.java` form two complementary documentation layers for JPMS. Module Javadoc explains the module's responsibilities and API surface; package Javadoc explains groups of types and each package's entry points. Placing them in the right locations, linking to appropriate types, using `@uses`/`@provides` when services exist, and generating HTML with `javadoc` makes module architecture easier to understand without weakening strong encapsulation.
