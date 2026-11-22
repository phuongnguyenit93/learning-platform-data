# javadoc and module documentation

In the Java Platform Module System (JPMS), a library's documentation does more than describe classes, interfaces, and methods. Users also need to know **which module contains an API**, which packages are exported, which modules it depends on, which services it uses or provides, and the module's access boundaries. The `javadoc` tool supports generating HTML documentation for modular structures, especially the summary page for each named module.

This lesson shows how to write **module documentation** in `module-info.java`, combine it with package/class documentation, document services with `@uses` and `@provides`, run `javadoc` for multi-module projects, and explain the relationship between generated documentation and the actual JPMS rules enforced by the JVM.

## 1. What problem does module documentation solve?

A pre-JPMS Java project typically started from package documentation:

```text
com.example.catalog.api
com.example.catalog.internal
com.example.catalog.persistence
```

From package or class documentation, readers learned the purpose of individual types, yet could not easily tell implementation boundaries. Once modularized, additional questions arise:

- What is the module name to declare in `requires`?
- Which packages are exported APIs, and which are internal implementations?
- How does the public API depend on platform modules or other modules?
- Do consumers need `uses` for a service to load implementations via `ServiceLoader`?
- Which services does the module supply via `provides ... with ...`?
- Are any modules granted qualified exports or qualified opens?
- Which modules can use the stable API without needing access to internal packages?

Module-level Javadoc enables developers to put answers in a shared summary page right alongside package and public type documentation. It is also the right place to describe module integration, runtime prerequisites, service contracts, and compatibility constraints.

**Note:** Javadoc is documentation for humans. It does not create `requires`, `exports`, `opens`, or service providers. Those relationships are still determined by `module-info.java` and resolution/runtime behavior.

## 2. module-info.java is both a descriptor and a place for documentation

An explicit named module has a `module-info.java` file at the root of the module source tree. Inside are the `module` declaration and JPMS directives.

Example:

```java
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
}
```

To write module documentation, place a **Javadoc comment** immediately before the `module` declaration:

```java
/**
 * Provides product lookup APIs for components of the system.
 *
 * <p>This module exposes the
 * {@code com.example.catalog.api} package, while keeping storage
 * and data synchronization in internal packages.
 *
 * <p>Consuming modules declare:
 * {@code requires com.example.catalog;}
 *
 * @since 1.0
 */
module com.example.catalog {
    requires java.logging;
    exports com.example.catalog.api;
}
```

When running `javadoc` in modular mode, this comment is included on the module's summary page. Without a comment, Javadoc can still generate the module page from the descriptor, yet readers will miss the design intent, usage scope, and API contract description.

A few guidelines:

1. Use `/** ... */` instead of a regular `/* ... */` comment so Javadoc recognizes it.
2. Place the comment before the `module` declaration, not detached on an arbitrary class.
3. Describe the module at a high level; details of each public class belong in that class's Javadoc.
4. Do not turn module documentation into a copy of the entire source code.
5. Keep documentation content consistent with the actual descriptor.

## 3. Source structure of a multi-module project

Suppose there are three modules:

```text
project/
└── src/
    ├── com.example.codec.api/
    │   ├── module-info.java
    │   └── com/example/codec/api/
    │       ├── Codec.java
    │       └── package-info.java
    ├── com.example.codec.json/
    │   ├── module-info.java
    │   └── com/example/codec/json/
    │       └── JsonCodec.java
    └── com.example.application/
        ├── module-info.java
        └── com/example/application/
            └── Main.java
```

In the example:

- `com.example.codec.api` owns the `Codec` contract.
- `com.example.codec.json` implements `Codec`.
- `com.example.application` consumes the `Codec` service.

With the `src/<module-name>/...` layout, both `javac` and `javadoc` can use `--module-source-path src` to recognize multiple modules.

### 3.1. API module

`src/com.example.codec.api/module-info.java`:

```java
/**
 * API for the application's data encoders.
 *
 * <p>This module exposes the {@link
 * com.example.codec.api.Codec} interface. Implementations can
 * reside in independent provider modules.
 *
 * <p>Applications can declare
 * {@code requires com.example.codec.api;} to use the Codec type.
 *
 * @since 1.0
 */
module com.example.codec.api {
    exports com.example.codec.api;
}
```

`Codec` interface:

```java
package com.example.codec.api;

/**
 * Contract for converting data into a string.
 *
 * <p>Implementations must advertise their format via
 * {@link #format()} and return encoded output via
 * {@link #encode(String)}.
 *
 * @since 1.0
 */
public interface Codec {

    /**
     * Format name supported by this implementation.
     *
     * @return format name, for example {@code json}
     */
    String format();

    /**
     * Encodes the input value.
     *
     * @param value content to encode
     * @return encoded data as a string
     */
    String encode(String value);
}
```

Module-level documentation introduces the overall purpose; class/interface documentation describes the specific contract. These two levels of documentation complement each other.

## 4. package-info.java: package-level documentation

In addition to `module-info.java`, use `package-info.java` to explain an exported package.

Example `src/com.example.codec.api/com/example/codec/api/package-info.java`:

```java
/**
 * Shared data encoding APIs.
 *
 * <p>This package defines stable contracts for
 * codecs. Applications do not need to depend directly
 * on implementation packages of individual providers.
 *
 * @since 1.0
 */
package com.example.codec.api;
```

Javadoc can use this comment to build the package summary page. A sensible division of responsibility:

| Documentation level | Should describe |
|---|---|
| Module `module-info.java` | Module purpose, integration guide, module dependencies, service contracts |
| Package `package-info.java` | Package role, related types, and usage principles |
| Class/interface | Responsibilities, invariants, inheritance or implementation rules |
| Constructor/method/field | Parameters, return values, errors, behavior, and preconditions |

`package-info.java` is not mandatory for every package, but it is very helpful for large API packages or those with multiple cooperating interfaces.

## 5. Documenting services with @uses and @provides

JPMS supports service abstraction with two directives:

- `uses service.Interface;` in a module consuming the service.
- `provides service.Interface with provider.Implementation;` in a module providing the service.

Javadoc has block tags `@uses` and `@provides` to explain the meaning of these services on the module page.

### 5.1. Service-consuming module

`src/com.example.application/module-info.java`:

```java
/**
 * Application that selects a data encoder at runtime.
 *
 * <p>The application depends on the Codec API, not directly
 * on individual implementation modules.
 *
 * @uses com.example.codec.api.Codec
 *       Used to discover available codecs via ServiceLoader.
 *
 * @since 1.0
 */
module com.example.application {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Here:

- `requires` allows the module to read the API module containing `Codec`.
- `uses` declares the service dependency for JPMS.
- `@uses` supplies the description displayed in module documentation.

If you write `@uses` without declaring the corresponding `uses`, the documentation text does not create a service dependency in the module graph.

### 5.2. Service-providing module

`src/com.example.codec.json/module-info.java`:

```java
/**
 * Provider that encodes data in JSON format.
 *
 * <p>This module implements the Codec contract and can be
 * discovered through ServiceLoader once included
 * in the module graph.
 *
 * @provides com.example.codec.api.Codec
 *           Provider that encodes in JSON format.
 *
 * @since 1.0
 */
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Implementation:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

/**
 * Illustrative implementation of {@link Codec}.
 *
 * <p>Simplified example to focus on JPMS;
 * not a complete JSON implementation.
 */
public final class JsonCodec implements Codec {

    public JsonCodec() {}

    @Override
    public String format() {
        return "json";
    }

    @Override
    public String encode(String value) {
        return "\""+value.replace("\"","\\\"")+"\"";
    }
}
```

Key point: `@provides` describes the service supplied by the module; the `provides` directive is the metadata the module system actually uses during service binding.

A provider package does not have to be exported solely for `ServiceLoader` to locate a provider declared in the module descriptor. When users only need the service interface, they should interact via `Codec` rather than importing the implementation class directly.

## 6. What can Javadoc display from the module descriptor?

When `javadoc` processes a named module, the documentation page can display information from the descriptor, such as:

- Module name.
- Module description from the Javadoc comment.
- Modules required via `requires`.
- Exported packages.
- Services declared in `uses` and `provides`.
- Information related to transitive dependencies or opened packages, depending on visibility options.

Example descriptor:

```java
module com.example.catalog {
    requires transitive com.example.money;
    requires java.logging;
    exports com.example.catalog.api;
    exports com.example.catalog.integration
        to com.example.reporting;
    opens com.example.catalog.model
        to com.example.json;
}
```

Documentation should explain the rationale behind each major decision:

- `requires transitive` is usually appropriate when the module's public API exposes types belonging to another dependency.
- `exports` exposes a package to other modules with appropriate readability.
- Qualified exports expose a package only to specified target modules.
- `opens` serves deep reflection, distinct from normal public API access.

Avoid trying to duplicate the entire dependency table in comments when the descriptor already states it accurately; the prose description should explain *intent and usage*.

## 7. Generating documentation with javadoc --module-source-path

With the multi-module source layout shown earlier, the basic command is:

```shell
javadoc -d docs --module-source-path src \
        --module com.example.codec.api,com.example.codec.json,com.example.application
```

Explanation:

- `-d docs`: HTML output directory.
- `--module-source-path src`: where to find module sources following the module source path layout.
- `--module`: list of modules to include in this documentation run.

On Windows PowerShell, you can write it on a single line to avoid line-continuation escaping differences between shells:

```powershell
javadoc -d docs --module-source-path src --module com.example.codec.api,com.example.codec.json,com.example.application
```

The command generates documentation for the selected modules and packages/types within the display scope. Once finished, open `docs/index.html` in a browser; the output structure can contain module-summary pages and corresponding package/class pages.

If the project has additional modular JAR dependencies outside the source tree, supply the module path:

```shell
javadoc -d docs \
        --module-source-path src \
        --module-path libs \
        --module com.example.application
```

`--module-path` in this context helps the tool locate dependencies of documented modules. It does not mean Javadoc will automatically generate complete documentation for every dependency JAR that lacks sources.

## 8. Documenting only modules meant for release

A repository may contain dozens of modules, yet not all of them are public APIs.

Suppose you have:

```text
com.example.catalog.api
com.example.catalog.impl
com.example.catalog.integration.tests
com.example.devtools
```

When publishing API documentation, you can select only the modules users need to reference:

```shell
javadoc -d docs/public \
        --module-source-path src \
        --module com.example.catalog.api
```

If documentation is intended for an internal development team, additional modules can be included:

```shell
javadoc -d docs/internal \
        --module-source-path src \
        --module com.example.catalog.api,com.example.catalog.impl
```

Separating public and internal documentation helps protect contract boundaries. However, selecting which modules are documented does not alter the module graph; it is purely a decision about documentation publishing scope.

## 9. Documenting exported packages vs. internal packages

Under the JPMS model, packages with `exports` form the module's normal API surface. Unexported implementation packages should generally not be documented as supported APIs for external users.

Javadoc has options controlling display scope, for example:

```shell
javadoc --show-module-contents api \
        --module-source-path src \
        --module com.example.catalog.api \
        -d docs/api
```

For internal documentation, a wider scope can be chosen:

```shell
javadoc --show-module-contents all \
        --module-source-path src \
        --module com.example.catalog.api \
        -d docs/all
```

Additionally, the `--show-packages` option can be used to control which kinds of packages are included in the documentation according to values supported by the JDK version, such as `exported` or `all`.

These options determine **the generated HTML documentation content**. They do not export internal packages at runtime. A package appearing in internal documentation can still be blocked by JPMS when another module attempts to import it.

When building a public API website, prefer documenting strictly the modules and packages belonging to the stable contract.

## 10. Using links in Javadoc

A good comment should not repeat full API signatures. Instead, use inline tags to lead readers to related types and members.

Example:

```java
/**
 * Order orchestration API.
 *
 * <p>See details at
 * {@link com.example.catalog.api.CatalogService}.
 * Applications can use this interface together with
 * {@link java.util.Optional} to represent results.
 */
module com.example.orders {
    requires com.example.catalog;
    exports com.example.orders.api;
}
```

Common tags:

- `{@link Type}`: creates a link to a type or member.
- `{@linkplain Type display label}`: creates a link rendered in plain text style.
- `{@code ...}`: displays an inline code snippet without parsing HTML markup inside.
- `@see`: lists related references.
- `@since`: notes the version in which the API/module was introduced.
- `@deprecated`: notes elements no longer recommended for use; apply in appropriate documentation contexts.

If you want documentation to link to Java SE APIs, you can use:

```shell
javadoc -d docs \
        --module-source-path src \
        --module com.example.catalog \
        -link https://docs.oracle.com/en/java/javase/21/docs/api/
```

The Java 21 URL above is illustrative; when releasing, pick the documentation matching the target Java version. Linking to external sites may require network access during the documentation generation step.

## 11. requires and requires transitive in API documentation

When writing module documentation, clearly state which dependencies are part of the public contract.

For example, module catalog exports an API returning a type from module money:

```java
module com.example.catalog {
    requires transitive com.example.money;
    exports com.example.catalog.api;
}
```

If a public method of catalog has a return type or parameter belonging to the money module, consumers reading catalog may need readability to money. `requires transitive` exposes this relationship to modules reading catalog.

In module documentation, explain:

- Under what conditions do users only need to declare `requires com.example.catalog;`?
- Where do types belonging to other modules appear in the public API?
- Are there internal-only dependencies not guaranteed as part of the contract?
- Which features depend on optional providers or the runtime environment?

Documentation does not replace checking the descriptor. If the comment states that money is a transitive dependency while the source only has `requires com.example.money;`, the documentation and actual contract will disagree.

## 12. Relationship between opens and framework documentation

Some libraries are designed for use with reflection frameworks such as ORM, serialization, or dependency injection.

Example:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model
        to com.example.orm;
}
```

Module documentation can explain that:

- Package `com.example.domain.api` is the regular usage API.
- Package `com.example.domain.model` is opened only for reflection by `com.example.orm`.
- Consumers must not assume the model package is a public API merely because a framework can reflect deeply into it.

The `opens` directive is not the same as `exports`. `exports` permits access to public types under standard Java rules; `opens` serves deep reflection. Appearing in Javadoc does not make these two directives equivalent.

If a framework depends on runtime flags such as `--add-opens`, document them in deployment instructions with a clear rationale, rather than hiding them only in an arbitrary class comment.

## 13. Documentation for modules using ServiceLoader

When a module supports plugins via a service interface, users need to know how to supply or consume providers.

Example description:

```java
/**
 * Application module processing output through the codec system.
 *
 * <p>Codec plugins must declare a service provider using
 * {@code provides ... with ...} in their module descriptor.
 *
 * @uses com.example.codec.api.Codec
 *       Finds codecs installed at program runtime.
 */
module com.example.application {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

And in the provider module:

```java
/**
 * JSON codec provider.
 *
 * @provides com.example.codec.api.Codec
 *           Provides JSON formatting.
 */
module com.example.codec.json {
    requires com.example.codec.api;
    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Keep these distinct:

1. **Service declaration:** `uses` and `provides` in descriptors.
2. **Service binding:** resolution APIs such as `Configuration.resolveAndBind` that can add provider modules to the graph.
3. **Service discovery:** `ServiceLoader` finding providers in the appropriate runtime context.
4. **Service documentation:** `@uses` and `@provides` explaining the contract on the documentation page.

A documentation website can list service providers, yet it does not replace putting the actual provider module into the runtime graph.

## 14. javadoc with Maven and Gradle

In large projects, integrate documentation generation into the build instead of running manual commands for every release.

### 14.1. Maven

The Maven Javadoc Plugin can generate Javadoc for a module or a reactor project, depending on how Maven modules are organized and the plugin version.

An illustrative configuration:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.11.2</version>
    </plugin>
  </plugins>
</build>
```

Then run the appropriate goal such as `mvn javadoc:javadoc` or `mvn javadoc:aggregate` for multi-module projects when configuration supports it. The version number above is illustrative only; use a plugin version compatible with your real build and toolchain.

If the build runs under JPMS, check whether the plugin passes the right module path, module source path, and dependency scopes. Not every multi-module Maven project maps one-to-one with JPMS named modules.

### 14.2. Gradle

Gradle includes the `javadoc` task in the Java ecosystem:

```shell
./gradlew javadoc
```

For multi-project builds, aggregate tasks can be created depending on publishing needs. Verify the Gradle version and modularity configuration so Javadoc tasks receive the proper source/module paths.

Do not assume documentation was generated in JPMS mode merely because the source tree contains `module-info.java`. Inspect the output to verify that module summary pages and `requires`, `exports`, and service sections appear as expected.

## 15. Checking javadoc warnings

Javadoc can report errors or warnings when:

- A `{@link ...}` tag points to a nonexistent type or member.
- `@param` does not match a method parameter.
- Documentation uses invalid HTML markup.
- A dependency/module needed to resolve types is not on the path.
- A specified module lacks sources or a module descriptor.
- Descriptive tags are incomplete or syntactically invalid.

You can enable documentation lint levels via `-Xdoclint` as supported by your JDK version:

```shell
javadoc -Xdoclint:all \
        --module-source-path src \
        --module com.example.codec.api \
        -d docs
```

These warnings help catch markup mistakes or invalid Javadoc metadata. They do not prove that the JPMS design or runtime module graph is right. Combine documentation generation with normal builds and tests.

## 16. Common misconceptions

**Putting module docs in README while leaving module-info.java undocumented.**

A README is great supplementary documentation, yet `javadoc` does not automatically pull README text into the module summary. If you want a module page with a dedicated introduction, put a Javadoc comment before the module declaration.

**Confusing @uses with uses.**

`@uses` only describes the service in documentation. `uses` is the directive in the module descriptor.

**Confusing @provides with provides ... with ....**

`@provides` supplies the description shown in HTML; `provides` is the service provider metadata recognized by JPMS.

**Thinking a package described in docs is an exported package.**

Access permissions are governed by `exports` and readability. Javadoc can generate internal documentation for unexported packages without changing access permissions.

**Thinking every dependency on the module path is automatically documented.**

The module path helps the tool resolve dependencies. To publish documentation for a module, you must supply its sources or appropriate documentation configuration and select that module for documentation.

**Writing docs using the JAR name instead of the module name.**

JPMS uses the module name declared in the descriptor; Maven artifact names or JAR filenames can differ. Document the exact module name so users write `requires` accurately.

**Linking to JDK API docs of a different version without stating it.**

APIs can change across Java versions. Choose documentation links and compatibility targets matching the target JDK.

**Including implementation packages in public API documentation.**

This misleads users into treating implementations as stable contracts. Separate public and internal documentation intentionally.

## 17. Workflow for writing and publishing module documentation

An easy-to-apply workflow:

1. **Verify the module name:** check `module-info.java`.
2. **Finalize public packages:** which packages need `exports` and why.
3. **Write the module introduction:** purpose, scope, contract, and usage boundaries.
4. **Describe key dependencies:** especially `requires transitive` when public APIs use types from another module.
5. **Write @uses/@provides when services exist:** keep them synchronized with the corresponding directives.
6. **Write package-info.java:** describe APIs for each exported package.
7. **Add Javadoc for types/members:** `@param`, `@return`, `@throws`, `{@link}`, `@since`.
8. **Generate HTML:** use `javadoc --module-source-path ... --module ...`.
9. **Inspect the output:** module summary page, package summaries, and links to required types.
10. **Publish by scope:** separate public API documentation from internal implementation documentation when needed.
11. **Tie to releases:** regenerate documentation from the exact release commit/tag and target JDK.
12. **Maintain synchronization:** whenever changing `exports`, `uses`, `provides`, or public APIs, update module documentation in the same change.

## 18. Module documentation checklist

- [ ] `module-info.java` has a Javadoc comment before the module declaration.
- [ ] The comment accurately describes the module's responsibilities and scope.
- [ ] The module name is documented accurately in integration instructions.
- [ ] API packages have appropriate `exports`; internal packages are not misrepresented as public APIs.
- [ ] `requires transitive` is explained when dependencies appear in the public API.
- [ ] Key `uses` and `provides` entries have `@uses`/`@provides` descriptions.
- [ ] Public packages have `package-info.java` where helpful.
- [ ] Javadoc on public types and methods states contracts clearly.
- [ ] `{@link}` references to other types/members resolve cleanly.
- [ ] The Javadoc command uses the right `--module-source-path`, `--module`, and dependency module path.
- [ ] The module summary page renders expected content and service-related sections.
- [ ] Documentation is generated from the release's exact source version and toolchain.

## Conclusion

`javadoc` turns a JPMS module from a set of classes with a descriptor into a **component with a clearly documented usage contract**. Javadoc comments in `module-info.java` provide module-level descriptions; `package-info.java` explains package roles; class and member documentation details specific APIs. The `@uses` and `@provides` tags add explanations for service dependencies.

For multi-module projects, use `javadoc --module-source-path ... --module ...` to generate HTML documentation with module summary pages. Visibility options separate public APIs from internal implementations; choosing publishing scope does not alter `requires`, `exports`, `opens`, or module resolution.

Good module documentation stays consistent with the actual descriptor, teaches the exact module name, thoroughly explains service contracts, and is regenerated with every release. That way, consumers understand not only how to call a class, but also how to integrate the module intentionally into their module graph.