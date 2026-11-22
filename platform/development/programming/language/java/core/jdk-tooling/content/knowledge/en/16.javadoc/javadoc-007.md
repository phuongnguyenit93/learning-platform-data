# Module Documentation with the Javadoc Tool

## 1. What is module documentation?

Module documentation is the HTML documentation that describes a named module in the Java Platform Module System (JPMS). It helps users understand the module's purpose, its exposed API, the modules it requires, the packages it exports, the services it uses or provides, and any compatibility constraints.

The `javadoc` tool reads documentation comments in Java source code and generates a set of HTML pages. For modular projects, the documentation includes a dedicated page for each module, typically `module-summary.html`. This page describes the module descriptor and links to packages, types, and related elements.

Module documentation serves as part of the release contract:

- Users know which modules need to be added to the module path.
- Users know which packages are supported as public API.
- Users know which services can be loaded with `ServiceLoader`.
- Maintainers know which modules and versions the module depends on.
- Development teams can review API changes before releasing.

Javadoc does not replace `module-info.java`. The `requires`, `exports`, `opens`, `uses`, and `provides` directives define the module structure; documentation comments explain the meaning and usage of that structure.

## 2. Where to document a module

A module's documentation is built from several types of documentation comments:

| Location | Content described | Typical HTML page generated |
|---|---|---|
| `module-info.java` | Module purpose, dependencies, exported packages, service use/provision, and release information. | `module-summary.html` |
| `package-info.java` | Package purpose, API groupings, and shared conventions. | `package-summary.html` |
| Class/interface/enum/record | Role, usage, preconditions, and behavior of the type. | Corresponding type page. |
| Constructor/method/field | Parameters, return values, exceptions, and side effects. | Summary/detail sections of the type page. |
| `overview.html` | Overview of the entire documentation set, guides, and high-level diagrams. | `overview-summary.html` |

For a named module, the comment immediately preceding the `module` declaration in `module-info.java` is the module description. Do not place this comment above a package declaration or inside a class and expect Javadoc to treat it as the module description.

Example:

~~~java
/**
 * Provides the public API for creating greetings.
 *
 * <p>Applications can use the service interface to discover
 * a greeting provider at runtime.</p>
 *
 * @since 1.0
 */
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

When Javadoc processes this module, the content above appears on the module summary page.

## 3. Documentation comments in module-info.java

A module documentation comment should explain what users cannot fully determine from the module name or directives alone:

- What functionality the module provides and who it is intended for.
- Which APIs are supported and which packages are exported.
- What roles required or optional dependencies play.
- Which services the module uses or provides.
- Any runtime, configuration, or Java version constraints.
- Important compatibility changes across versions.

API module example:

~~~java
/**
 * Provides the public API for greeting services.
 *
 * <p>Applications use {@link com.example.greeter.api.GreetingService}
 * to work with greeting providers without depending on an implementation.</p>
 *
 * @since 1.0
 */
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

Module descriptions support basic HTML inside Javadoc comments, allowing paragraphs, lists, and inline tags such as `{@link ...}` and `{@code ...}`. Link to key types so readers can navigate directly to the API.

Do not include secrets, personal machine paths, tokens, or internal configuration in release documentation. Javadoc is documentation that may be published alongside the artifact.

## 4. Documenting uses and provides

JPMS supports service providers through two directives:

- `uses service.Type;` declares that the module uses a service.
- `provides service.Type with implementation.Type;` declares that the module provides an implementation of a service.

In module documentation, you can describe these two relationships using the `@uses` and `@provides` block tags.

### Documenting a module that uses a service

~~~java
/**
 * Runs the greeting application.
 *
 * @uses com.example.greeter.api.GreetingService
 *       A service used to create the greeting shown to the user.
 */
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.GreetingService;
}
~~~

The `@uses` tag causes Javadoc to display a Uses entry in the Services section of the module page. The service name must match the service type declared in the `uses` directive.

### Documenting a module that provides a service

~~~java
/**
 * Provides the default greeting implementation.
 *
 * @provides com.example.greeter.api.GreetingService with
 *           com.example.greeter.impl.DefaultGreetingService
 *           The built-in provider for the greeting service.
 *
 * @since 1.0
 */
module com.example.greeter.impl {
    requires com.example.greeter.api;

    provides com.example.greeter.api.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

The `@provides` tag describes the service type, the implementation provided, and the purpose of the provider. The `provides ... with ...` directive must still be present in the module descriptor; documentation tags do not register a service provider on their own.

The module summary page can display a Services section with Uses and Provides groups, helping readers understand how the module participates in the service graph.

## 5. Package documentation with package-info.java

Module documentation should be paired with package documentation. A package comment describes the purpose of the package and the public types within it.

Example `src/com.example.greeter.api/com/example/greeter/api/package-info.java`:

~~~java
/**
 * Defines the public service API for greeting providers.
 *
 * <p>Applications depend on these interfaces instead of depending
 * on a particular provider implementation.</p>
 *
 * @since 1.0
 */
package com.example.greeter.api;
~~~

Package documentation is attached to the package, not the module. A module may contain multiple packages, and each package should have a clear description if it is part of the API.

For named modules:

- Exported packages are typically the API surface users need to see in public documentation.
- Non-exported packages are typically implementation details and can be excluded from API documentation.
- When internal documentation is needed for the development team, you can instruct Javadoc to show all packages using `--show-packages all`.

`package-info.java` is the standard way to write package comments. `package.html` is the legacy approach; prefer `package-info.java` in modern projects.

## 6. Complete example: generating Javadoc for three modules

This example includes three modules:

- `com.example.greeter.api` declares the service interface.
- `com.example.greeter.impl` provides the implementation.
- `com.example.greeter.app` consumes the service via `ServiceLoader`.

Source structure:

~~~text
project/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/api/
    │       ├── package-info.java
    │       └── GreetingService.java
    ├── com.example.greeter.impl/
    │   ├── module-info.java
    │   └── com/example/greeter/impl/
    │       └── DefaultGreetingService.java
    └── com.example.greeter.app/
        ├── module-info.java
        └── com/example/greeter/app/
            └── Main.java
~~~

### API module

File `src/com.example.greeter.api/module-info.java`:

~~~java
/**
 * Provides the public API for greeting services.
 *
 * <p>Applications use the service interface without depending
 * on a concrete provider implementation.</p>
 *
 * @since 1.0
 */
module com.example.greeter.api {
    exports com.example.greeter.api;
}
~~~

File `src/com.example.greeter.api/com/example/greeter/api/package-info.java`:

~~~java
/**
 * Defines the public service API for greeting providers.
 */
package com.example.greeter.api;
~~~

File `src/com.example.greeter.api/com/example/greeter/api/GreetingService.java`:

~~~java
package com.example.greeter.api;

/**
 * Creates a greeting for a recipient.
 */
public interface GreetingService {

    /**
     * Returns a greeting for the given name.
     *
     * @param name recipient name
     * @return formatted greeting
     */
    String greet(String name);
}
~~~

### Implementation module

File `src/com.example.greeter.impl/module-info.java`:

~~~java
/**
 * Provides the default implementation of the greeting service.
 *
 * @provides com.example.greeter.api.GreetingService with
 *           com.example.greeter.impl.DefaultGreetingService
 *           The built-in provider.
 *
 * @since 1.0
 */
module com.example.greeter.impl {
    requires com.example.greeter.api;

    provides com.example.greeter.api.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

File `src/com.example.greeter.impl/com/example/greeter/impl/DefaultGreetingService.java`:

~~~java
package com.example.greeter.impl;

import com.example.greeter.api.GreetingService;

/**
 * Default provider that prefixes a name with {@code Hello}.
 */
public class DefaultGreetingService implements GreetingService {

    /** Creates the default provider. */
    public DefaultGreetingService() {
    }

    /**
     * {@inheritDoc}
     */
    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### Application module

File `src/com.example.greeter.app/module-info.java`:

~~~java
/**
 * Runs the greeting application using a discovered service provider.
 *
 * @uses com.example.greeter.api.GreetingService
 *       A service used to create the greeting shown to the user.
 *
 * @since 1.0
 */
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.api.GreetingService;
}
~~~

File `src/com.example.greeter.app/com/example/greeter/app/Main.java`:

~~~java
package com.example.greeter.app;

import com.example.greeter.api.GreetingService;
import java.util.ServiceLoader;

/**
 * Starts the greeting application.
 */
public class Main {

    /** Creates the application entry point. */
    public Main() {
    }

    /**
     * Loads a greeting provider and prints a greeting.
     *
     * @param args optional recipient name
     */
    public static void main(String[] args) {
        GreetingService service = ServiceLoader
                .load(GreetingService.class)
                .findFirst()
                .orElseThrow();

        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(service.greet(name));
    }
}
~~~

### Compiling and running to verify the example

From the `project` directory:

~~~bash
mkdir -p mods

javac --release 17 \
  --module-source-path src \
  -d mods \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app
~~~

Run the application:

~~~bash
java --module-path mods \
  -m com.example.greeter.app/com.example.greeter.app.Main Ada
~~~

Stdout:

~~~text
Hello, Ada
~~~

The app module must declare `uses com.example.greeter.api.GreetingService;` because the app itself calls `ServiceLoader.load`. The impl module must declare `provides ... with ...`. Writing only `@uses` or `@provides` in a Javadoc comment without the corresponding directive will not establish the service relationship at runtime.

## 7. Documenting multiple modules with --module-source-path

For a source tree containing multiple modules, use `--module-source-path` to specify the root directory containing the module directories. The `--module` option selects which modules to document.

Command to generate API documentation for the three modules in the example:

~~~bash
javadoc --release 17 \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  -charset UTF-8 \
  --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  -d docs \
  --show-module-contents api \
  --show-packages exported \
  -Xdoclint:all \
  -Werror
~~~

Meaning of the options:

- `--release 17` sets the source/API compatibility level to Java 17.
- `-encoding UTF-8` reads source files as UTF-8.
- `-docencoding UTF-8` sets the encoding of generated HTML files.
- `-charset UTF-8` declares the charset in the HTML output.
- `--module-source-path src` locates the module sources.
- `--module ...` selects the modules to document.
- `-d docs` sets the output directory.
- `--show-module-contents api` selects the API-level display of module declarations.
- `--show-packages exported` includes only exported packages in package documentation.
- `-Xdoclint:all` enables all documentation check groups.
- `-Werror` causes Javadoc warnings to fail the build.

Using a single command across modules keeps documentation structure and check levels consistent. For large projects, you can place options into an argument file and pass it via `@options.txt`.

## 8. How do --module-path and --module-source-path differ?

These two options resolve different module sources:

| Option | Data source | When to use |
|---|---|---|
| `--module-source-path` | Source tree of multiple named modules. | When Javadoc must read `module-info.java` and sources of modules in the project. |
| `--module-path` or `-p` | Pre-built modular JARs or exploded modules. | When the documented source references pre-built dependent modules. |
| `--class-path` or `-cp` | Class files and JARs on the classpath. | When documenting source that depends on unnamed modules or legacy libraries. |

Example when the app module references a packaged library module:

~~~bash
javadoc --release 17 \
  --module-source-path src \
  --module-path lib \
  --module com.example.greeter.app \
  -d docs
~~~

`lib` contains modular JARs or compiled modules that Javadoc needs to resolve while reading the source. Do not use `--module-path` in place of `--module-source-path` when the goal is to locate the source code of the modules being documented.

If a dependency cannot be resolved, check the module name in `requires`, the JAR location, and the module path. The JAR filename does not necessarily match the module name declared inside it.

## 9. Expanding the set of documented modules

By default, Javadoc generates documentation only for the modules explicitly specified on the command line. You can expand the module set using `--expand-requires`:

~~~bash
# Include dependencies declared with requires transitive
javadoc --module-source-path src \
  --module com.example.greeter.app \
  --expand-requires transitive \
  -d docs

# Include all dependencies of the selected modules
javadoc --module-source-path src \
  --module com.example.greeter.app \
  --expand-requires all \
  -d docs
~~~

Values:

- `transitive` adds modules required via `requires transitive`.
- `all` adds all module dependencies of the selected modules.
- Without `--expand-requires`, only explicitly selected modules are documented.

This option can make the documentation set significantly larger. Only expand when readers need to view dependency documentation within the same HTML set; otherwise, use `--link` to point to published dependency documentation.

## 10. Controlling module and package detail levels

Javadoc provides options to control the scope of generated documentation.

| Option | Values | Effect |
|---|---|---|
| `--show-module-contents` | `api` or `all` | Controls the level of detail shown for module declarations. |
| `--show-packages` | `exported` or `all` | Shows only exported packages or all packages in the module. |
| `--show-types` | `public`, `protected`, `package`, `private` | Selects the access level for classes, interfaces, enums, records, and other types. |
| `--show-members` | `public`, `protected`, `package`, `private` | Selects the access level for fields, constructors, and methods. |

Public API documentation typically uses:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.app \
  --show-module-contents api \
  --show-packages exported \
  --show-types protected \
  --show-members protected \
  -d docs-api
~~~

Internal documentation can use:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  --show-module-contents all \
  --show-packages all \
  --show-types private \
  --show-members private \
  -d docs-internal
~~~

You can also use the access-level shorthands `-public`, `-protected`, `-package`, and `-private`. For named modules, `-private` includes all packages and module details. The `--show-*` options express intent more clearly when building public API docs and internal docs as separate sets.

Avoid including implementation packages in public API documentation if those packages are not exported and are not part of the supported contract for module consumers.

## 11. Understanding the HTML structure generated by Javadoc

When running Javadoc for multiple named modules, the output directory looks like this:

~~~text
docs/
├── index.html
├── overview-summary.html
├── index-all.html
├── com.example.greeter.api/
│   ├── module-summary.html
│   └── com/example/greeter/api/
│       ├── package-summary.html
│       └── GreetingService.html
├── com.example.greeter.impl/
│   └── module-summary.html
└── com.example.greeter.app/
    └── module-summary.html
~~~

Key pages:

- `index.html`: main navigation page.
- `overview-summary.html`: overview for the entire documentation set.
- `module-summary.html`: describes the module, directives, services, and related packages.
- `package-summary.html`: describes the package.
- Class/interface pages: describe types, methods, constructors, and fields.
- `index-all.html`: index for looking up all documented elements.

Each module has its own directory named after the module name. When multiple modules share the same package name, the module-based path distinguishes each module's documentation.

For modules with `@uses` or `@provides`, the module summary page can include a Services section split into Uses and Provides. This section helps readers see the module's role in the service graph.

## 12. Writing documentation comments and linking APIs

Documentation comments should describe the observable contract from the caller's perspective rather than merely repeating the method name.

Example of a thoroughly documented method:

~~~java
/**
 * Returns a greeting for the given recipient.
 *
 * <p>The result is suitable for display and is never {@code null}.</p>
 *
 * @param name recipient name; must not be {@code null}
 * @return formatted greeting
 * @throws IllegalArgumentException if {@code name} is blank
 * @see GreetingService
 * @since 1.0
 */
String greet(String name);
~~~

Commonly used tags:

- `@param` describes a parameter.
- `@return` describes the return value.
- `@throws` or `@exception` describes exceptions that may be thrown.
- `@see` creates a reference to related APIs.
- `@since` records the version in which the API was introduced.
- `@deprecated` explains that an API is obsolete and suggests a replacement.
- `{@link ...}` creates a link to a type or member.
- `{@code ...}` formats code names within text.
- `{@inheritDoc}` inherits documentation content from an overridden method.

The first sentence of a documentation comment is typically used as the summary in index pages and method lists. Write a clear first sentence with a subject that describes the action or purpose. The remainder can explain details, examples, and usage conditions.

For public APIs, document nullability, thread safety, ordering guarantees, side effects, resource limits, and exceptions whenever these are part of the contract.

## 13. Linking to documentation of other modules

When a module uses JDK APIs or external libraries, Javadoc can generate links to the published HTML documentation of those dependencies.

Use `-link` when the build machine can access the documentation URL:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api \
  --link https://docs.oracle.com/en/java/javase/17/docs/api/ \
  -d docs
~~~

Use `-linkoffline` when you want to link to a documentation URL while keeping the package/element list stored locally:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api \
  -linkoffline https://docs.example.com/library/ ./offline-library-docs \
  -d docs
~~~

`-linkoffline` takes two arguments: the URL the documentation will link to and a local directory containing the target documentation's package/module list. This is useful in offline CI environments or when building against pre-downloaded dependency docs.

If a dependency has its own module documentation, link to the matching documentation version to avoid pointing to APIs that do not exist in the artifact being used. Do not use `--expand-requires all` solely to resolve cross-links when the dependency already publishes its own documentation.

## 14. Overview, resources, and stylesheets

You can create an overview page for the entire documentation set using an HTML file:

~~~html
<!-- overview.html -->
<h1>Greeter Platform</h1>
<p>Documentation for the public greeting modules.</p>
~~~

Pass the file to Javadoc:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  -overview overview.html \
  -d docs
~~~

Additional options:

- `-overview file` uses the HTML content as the overview section.
- `-docfilessubdirs` recursively copies `doc-files` directories within packages.
- `--main-stylesheet file` replaces the main stylesheet of the documentation.
- `--add-stylesheet file` adds a supplementary stylesheet.
- `-windowtitle text` sets the browser window title.
- `-doctitle html` sets the title on the overview page.
- `-taglet` and `-tag` support taglets or custom tags when a project has custom documentation conventions.

Use `doc-files` directories for illustrations, diagrams, or static examples associated with a package or type. Verify that files are copied to the expected paths in the HTML output and do not reference files that exist only on the build machine.

## 15. Checking documentation with DocLint

Javadoc includes DocLint to check the quality of documentation comments. The check groups are:

| Group | Content |
|---|---|
| `accessibility` | Issues related to HTML accessibility. |
| `html` | HTML structure and syntax inside comments. |
| `missing` | Missing required documentation or tags based on the check level. |
| `reference` | Invalid or unresolved references to types/members. |
| `syntax` | Documentation comment and inline/block tag syntax. |

Enable all groups:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  -Xdoclint:all \
  -Werror \
  -d docs
~~~

`-Werror` causes warnings to fail the command. This is useful in CI because missing documentation or broken links are caught before release.

If a legacy project has many warnings about missing documentation, you can temporarily disable the `missing` group during a transition period:

~~~bash
javadoc --module-source-path src \
  --module com.example.greeter.api \
  -Xdoclint:all,-missing \
  -d docs
~~~

Do not disable DocLint entirely to hide HTML or reference errors. Aim to fill in missing comments and re-enable `-Xdoclint:all -Werror`.

You can scope DocLint to specific packages with `-Xdoclint/package:...` when incrementally cleaning up a large codebase. After each change, inspect actual warnings and keep configuration consistent between local builds and CI.

## 16. Integrating Javadoc into the build pipeline

Javadoc should be generated from the same source revision and module graph as the release artifact.

A typical CI workflow:

~~~bash
# Compile all modules
javac --release 17 \
  --module-source-path src \
  -d mods \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app

# Run Javadoc for the modules
javadoc --release 17 \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  -charset UTF-8 \
  --module-source-path src \
  --module com.example.greeter.api,com.example.greeter.impl,com.example.greeter.app \
  --show-module-contents api \
  --show-packages exported \
  -Xdoclint:all \
  -Werror \
  -d build/javadoc

# Verify the application after building
java --module-path mods \
  -m com.example.greeter.app/com.example.greeter.app.Main Ada
~~~

Best practices:

- Pin the JDK/toolchain and `--release`.
- Use UTF-8 consistently for both source and output.
- Explicitly select public API modules; generate a separate internal documentation set if needed.
- Enable DocLint and resolve warnings before release.
- Store the Javadoc directory as a versioned build artifact.
- Validate external links in the CI environment.
- Inspect HTML output after renaming modules or packages.
- Do not generate documentation from stale class files or a different source revision than the artifact.

With Maven or Gradle, configure the Javadoc task to receive the exact source set / module source path and module path used by the compile task. Do not assume the Javadoc task automatically uses the right module path just because the compile task succeeds; inspect the actual command in the build log if resolution errors occur.

## 17. Common errors and troubleshooting

| Symptom | Common cause | Solution |
|---|---|---|
| `module-summary.html` is not generated | No named module was selected or the source path does not contain a module descriptor. | Check `--module`, `--module-source-path`, and the location of `module-info.java`. |
| Module description is empty | Missing documentation comment immediately before the `module` declaration. | Add `/** ... */` in `module-info.java`. |
| Module page lacks expected Uses/Provides section | Missing directive or module comment lacks `@uses`/`@provides`. | Check both the module descriptor and the documentation tags. |
| Type in a dependent module not found | Dependent module is not on the module path or source path. | Place built dependencies on `--module-path`; use `--module-source-path` for source modules. |
| Internal packages do not appear | Documentation is generated only for exported packages. | Use `--show-packages all` for internal documentation. |
| Types/members do not appear | Access level restricts documentation scope. | Adjust `--show-types` and `--show-members`. |
| Broken links to dependencies | Docs URL points to the wrong version or target docs lack an element list. | Check `-link` or `-linkoffline` and verify the matching docs version. |
| Javadoc fails due to warnings | Missing `@param`, `@return`, constructor comments, or invalid HTML. | Fix the comments and re-run `-Xdoclint:all -Werror`. |
| HTML renders non-ASCII characters (e.g., Vietnamese) incorrectly | Inconsistent input or output encoding. | Use `-encoding UTF-8`, `-docencoding UTF-8`, and `-charset UTF-8`. |
| `@uses`/`@provides` appears but service is not found at runtime | Only documentation tags were written without directives in the descriptor, or the provider is not on the module path. | Declare `uses`/`provides` properly and verify the service provider module. |
| Javadoc documents too many modules | `--expand-requires all` was used or too many root modules were selected. | Specify only the required modules and choose an appropriate expansion level. |
| Internal documentation leaks into the public site | `--show-packages all` or overly broad visibility was used for public docs. | Build two separate doc sets: public API and internal. |

## 18. Pre-release checklist for module documentation

- Every named module has a module description in `module-info.java`.
- The module comment clearly describes the purpose, API scope, and key dependencies.
- `requires`, `exports`, `opens`, `uses`, and `provides` directives match the description.
- Modules that use services have `@uses`, and modules that provide services have `@provides` when the service contract needs explanation.
- Every exported package has appropriate package documentation.
- Public types and members have comments describing behavior, parameters, return values, and exceptions.
- `{@link ...}` references and external links work properly.
- The right modules are selected with `--module` and the right sources with `--module-source-path`.
- Appropriate visibility levels are set with `--show-module-contents`, `--show-packages`, `--show-types`, and `--show-members`.
- `-Xdoclint:all -Werror` passes, or a clear warning-resolution plan is in place.
- HTML output contains `module-summary.html` for each expected module.
- Module, package, type, service summary pages, and static resources have been verified.
- The documentation set is generated from the same revision and JDK release as the release artifact.

## 19. References

- [The javadoc Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Java Documentation Comments Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)

Module documentation helps users understand a module as an independent unit of API and dependencies. Write module descriptions in `module-info.java`, document packages with `package-info.java`, specify service tags clearly, and generate multi-module documentation with `--module-source-path` and `--module`. Enable DocLint in CI and verify each module's `module-summary.html` page before releasing.