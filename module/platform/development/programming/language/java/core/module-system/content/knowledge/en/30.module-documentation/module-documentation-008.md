# Changelog When Changing Module Boundaries

In the Java Platform Module System (JPMS), a **module boundary** defines which module owns which packages, which modules can read others, which packages are accessible as public APIs, and which packages are opened for reflection. Consequently, modifying `module-info.java` can affect library users even if no public Java method was changed.

A good changelog should clearly answer: **which boundary changed, who is affected, what the compile-time or runtime impact is, how code or run commands must be updated, and from which version the change takes effect**. Simply writing “refactor module structure” or “cleanup module-info” is usually insufficient for dependent projects.

This article explains how to write changelogs and migration notes when changing module boundaries in Java modular libraries or applications.

## 1. Why are module boundaries part of the compatibility contract?

A named module has a descriptor:

```java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.json;
    uses com.acme.catalog.spi.Connector;
}
```

This descriptor expresses multiple architectural decisions:

- `requires java.logging`: the module has a read dependency on the logging module.
- `exports com.acme.catalog.api`: other modules can access public types in the API package if they have appropriate readability.
- `opens com.acme.catalog.model to com.acme.json`: the JSON module is permitted deep reflection into the model package at runtime.
- `uses ... Connector`: the module intends to discover a service type via `ServiceLoader`.

Suppose a later release removes `exports com.acme.catalog.api`. The classes and methods in the JAR may still exist, yet consumers importing them can fail to compile; already-compiled bytecode may also encounter `IllegalAccessError` when running on the new module graph.

If an `opens` is changed to close the package, serializer/ORM frameworks may hit `InaccessibleObjectException` even though unit tests not using reflection pass normally.

Therefore, **module descriptor diffs must be reviewed like public API diffs** when preparing release notes.

## 2. Changes that belong in the changelog

| Change | Possible impact | What to document |
|---|---|---|
| Add `exports P` | Exposes new public API to consumers | Package name, module, support scope |
| Remove `exports P` | Consumers lose access to the package | Replacement API, how to migrate, release version |
| Change `exports P` to `exports P to A` | Modules other than `A` become restricted | Supported consumer set, migration path |
| Add/remove `opens P` | Alters deep reflection availability | Affected frameworks and alternative config |
| Add/remove `requires M` | Changes dependency graph and resolution requirements | Module name and runtime requirements |
| Switch `requires` <-> `requires transitive` | Changes readability propagated to consumers | Whether consumers must declare `requires` directly |
| Switch `requires` <-> `requires static` | Changes dependency requirement at runtime resolution | Whether dependency is still needed when code executes |
| Add/remove `uses S` | Changes service discovery needs | Service contract and default behavior |
| Add/remove/change `provides S with I` | Available provider set and plugin behavior change | Added/removed/replaced implementations and selection |
| Rename module | Old `requires` descriptors no longer match | Old name, new name, artifact coordinates, migration |
| Move package between modules | Changes package owner and `requires` | Import paths, module path, compatibility |
| Split or merge modules | Graph and distributed artifacts change | Old/new module mapping, dependencies, run commands |

Not every change in the table always breaks callers. Actual impact depends on which packages/services consumers use, whether the artifact sits on the module path or classpath, and build/runtime configuration. The changelog must **describe the impact scope with evidence**, rather than assuming every descriptor edit is a breaking change.

## 3. Distinguishing artifact name from module name in release notes

An application may use a Maven dependency:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>catalog-client</artifactId>
    <version>2.0.0</version>
</dependency>
```

Yet the JPMS module name could be `com.acme.catalog`. The two names do not have to match. If an artifact or module changes, the changelog should record them separately:

```text
Old artifact: com.acme:catalog-client:1.x
New artifact: com.acme:catalog-client:2.x
Old JPMS module: com.acme.catalog
New JPMS module: com.acme.catalog.api
```

The above is illustrative. What matters is avoiding instructing consumers to edit `requires com.acme.catalog;` using the Maven `artifactId` instead of the **actual module name** from `module-info.class`.

You can check an artifact's module name with:

```shell
jar --describe-module --file catalog-client-2.0.0.jar
```

If the JAR is an automatic module, the name may come from `Automatic-Module-Name` or be derived from the filename. Changes to automatic module naming should also be noted if consumers declare `requires` on that name.

## 4. Changelog template for exports changes

### Before the change

Library version 1.x:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.legacy;
}
```

Consumer usage:

```java
module com.acme.report {
    requires com.acme.catalog;
}
```

```java
import com.acme.catalog.legacy.LegacyCatalog;
```

### After the change

Library version 2.x:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Package `com.acme.catalog.legacy` is no longer exported. Even if the classes remain present without being exposed, consumers can no longer access them directly from another named module.

A helpful changelog entry:

```markdown
### Changed — JPMS module boundary

- Module: `com.acme.catalog`
- Removed export: `com.acme.catalog.legacy`
- Supported public API: `com.acme.catalog.api`
- Affected consumers: named modules importing classes from
  `com.acme.catalog.legacy`
- Migration: replace `LegacyCatalog` with `CatalogClient`
  from `com.acme.catalog.api`
- Runtime impact: previously compiled consumers may encounter
  `IllegalAccessError` when accessing the non-exported package
```

The changelog should include concrete migration steps, not just “removed deprecated export”. If the replacement API is not strictly equivalent, describe which behaviors or data need adjustment.

**Note:** leaving `public` on a class inside an unexported package does not make that class a public API across named-module boundaries.

## 5. Qualified exports: narrowing the allowed consumer group

Changing from:

```java
exports com.acme.catalog.integration;
```

to:

```java
exports com.acme.catalog.integration to com.acme.partner;
```

means that package is now exported only to module `com.acme.partner`. Other consumers may be affected.

In the changelog, state:

1. The module owning the package and the narrowed package name.
2. Which modules retain the qualified export after the change.
3. That consumers previously relying on the unqualified export will lose access.
4. The replacement API or supported integration path.

If a consumer is renamed from `com.acme.partner` to `com.acme.partner.v2`, the qualified export must also be updated as needed. Do not claim “qualified export remains compatible” if the target module set changed.

Concise format:

```markdown
### Breaking — Qualified export

`com.acme.catalog.integration` is now exported only to
`com.acme.partner`. Other named modules must migrate to the
public `com.acme.catalog.api` package.
```

Do not use `--add-exports` as a long-term substitute for a stable public API. If a time-bound workaround is necessary, note which releases support it and the expected removal timeline.

## 6. opens and reflection must have their own release notes

`exports` and `opens` do not replace each other:

- `exports P`: allows accessing public types in the package when a module has readability.
- `opens P`: allows deep reflection into the package at runtime.
- `opens P to M`: allows deep reflection only from module `M`.
- `open module`: opens packages in the module for deep reflection, often more broadly than needed.

Example before the change:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model;
}
```

After the change:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.json;
}
```

This changes broad reflection openness to openness for a specific module. When writing the changelog, do not just write “security hardening”. Specify which framework modules remain supported, which frameworks or tests must adjust, and the expected error if not migrated:

```text
java.lang.reflect.InaccessibleObjectException
```

Example release note entry:

```markdown
### Changed — Reflection access

The package `com.acme.catalog.model` is now opened only to
`com.acme.json`. Custom serializers running in other named
modules must use the supported mapping API or request a
documented integration path.
```

For frameworks running in the unnamed module, verify opening the package to `ALL-UNNAMED` if applying a workaround. State the execution environment clearly rather than dropping a generic JVM flag into release notes.

## 7. requires and the dependency graph: which changes to announce?

If version 1.x has:

```java
module com.acme.catalog {
    requires java.logging;
    exports com.acme.catalog.api;
}
```

and version 2.x adds:

```java
requires java.net.http;
```

then the library's runtime graph gains a `java.net.http` dependency. Users running on a full JDK usually have this module, whereas custom runtime images built with `jlink` or custom module paths may need rebuilding.

In the changelog, state clearly:

```text
Added JPMS dependency: java.net.http
Affected environments: custom jlink images and constrained runtimes
Action: rebuild the runtime image and verify module resolution
```

If the dependency is a third-party library module, record both the **artifact dependency** and the **JPMS module name**, since consumers or build tools must supply the corresponding artifact.

When removing a `requires`, the changelog can also note which module is no longer required, especially if the change helps shrink runtime image size. However, do not promise the image shrinks automatically if another dependency keeps that module in the graph.

## 8. requires transitive affects API consumers

Suppose a library exports an interface returning a type from another module:

```java
package com.acme.catalog.api;

import com.acme.model.Product;

public interface Catalog {
    Product find(String id);
}
```

Initial descriptor:

```java
module com.acme.catalog {
    requires transitive com.acme.model;
    exports com.acme.catalog.api;
}
```

Thanks to `requires transitive`, consumers reading `com.acme.catalog` also receive readability to `com.acme.model`.

If changed to:

```java
module com.acme.catalog {
    requires com.acme.model;
    exports com.acme.catalog.api;
}
```

consumers no longer receive readability to `model` transitively through that path. Some consumer sources may need to add:

```java
module com.acme.report {
    requires com.acme.catalog;
    requires com.acme.model;
}
```

The changelog should specify concretely:

```markdown
### Changed — Transitive readability

`com.acme.model` is no longer a transitive dependency of
`com.acme.catalog`. Consumer modules using types from
`com.acme.model` must declare `requires com.acme.model;`
directly.
```

Do not equate this with Maven/Gradle transitive artifact dependencies: the build tool may still download the model JAR, yet JPMS readability for a named module is determined by descriptors and the module graph.

## 9. requires static and optional dependencies

`requires static M` denotes a dependency needed at compile time but not required to be present during runtime module resolution.

Example:

```java
module com.acme.catalog {
    requires static com.acme.annotations;
}
```

If a release changes `requires com.acme.annotations;` to `requires static com.acme.annotations;`, the changelog can note the dependency is no longer required at runtime resolution. However, that **does not mean** every code path using that module's API will automatically work without the JAR.

Conversely, changing `requires static` to `requires` means deployments must ensure the new module is always present at runtime.

A good notice should separate:

- Requirements at compile time.
- Requirements at runtime resolution.
- Actual requirements of features using classes from the dependency module.
- Necessary updates in Maven/Gradle scopes or dependency configurations.

Do not write “module dependency removed” when the module still appears with `requires static` and sources still need it to compile.

## 10. Service boundaries: uses and provides

Service contracts are part of module boundaries even when consumers do not import implementation classes directly.

Consumer:

```java
module com.acme.catalog.app {
    requires com.acme.catalog.spi;
    uses com.acme.catalog.spi.ExportService;
}
```

Provider:

```java
module com.acme.catalog.csv {
    requires com.acme.catalog.spi;
    provides com.acme.catalog.spi.ExportService
        with com.acme.catalog.csv.CsvExporter;
}
```

Changes that should be announced include:

- New provider modules or removed provider modules.
- Renamed service interfaces or interfaces moved to another module.
- Changed provider implementations or default behaviors.
- Consumer modules starting or stopping service usage.
- Changes in how providers are added to runtime images or `ModuleLayer`s.
- Services replaced by another API or requiring explicit provider configuration.

Changelog example:

```markdown
### Changed — Service provider

The CSV exporter is now provided by module
`com.acme.catalog.csv` instead of `com.acme.catalog`.
Deployments must include the provider module and ensure it is
resolved (for example, through an explicit root or service binding).
```

Distinguish “JAR is on the module path” from “provider module is resolved”. A provider may sit in the deployment folder without being included in the graph. Release notes should state launch or linking requirements if a service boundary change alters how providers are discovered.

## 11. Renaming or splitting a module is a clear migration change

Suppose consumers previously had:

```java
module com.acme.report {
    requires com.acme.catalog;
}
```

The new version splits into:

```text
com.acme.catalog.api
com.acme.catalog.impl
```

If the API moves to module `com.acme.catalog.api`, consumers usually need to update:

```java
module com.acme.report {
    requires com.acme.catalog.api;
}
```

The changelog must include a name mapping:

| Before | After | Consumer action |
|---|---|---|
| `com.acme.catalog` | `com.acme.catalog.api` | Update `requires` and dependency artifact if changed |
| `com.acme.catalog.internal` | `com.acme.catalog.impl.internal` | Do not import directly; use public API instead |
| Provider inside original module | Provider in `com.acme.catalog.impl` | Ensure provider module is present in runtime graph |

If package names also changed, supply before/after import examples, not just `module-info.java` examples.

Renaming a module may require rebuilding all consumer modular JARs. Runtime configurations, launcher scripts, `--add-opens`, `--add-exports`, `--add-modules`, `--module-path`, and plugin config files may also need updates.

## 12. Binary compatibility, source compatibility, and runtime compatibility

The changelog should categorize impact by phase rather than using a single “breaking” label:

| Compatibility type | Considerations |
|---|---|
| Source compatibility | Does recompiling consumer source require changing `requires`, imports, or APIs? |
| Binary/runtime linkage | Can existing consumer bytecode still access classes/members through the new runtime graph? |
| Runtime behavior | Do `ServiceLoader`, reflection, provider discovery, and runtime features still work? |
| Deployment compatibility | Must custom images, module path, launchers, or JDK versions change? |
| Build tooling compatibility | Did Maven/Gradle module paths, compiler options, test runners, or processor paths change? |

For example, removing an export can break compilation for new consumer projects, while precompiled bytecode may hit `IllegalAccessError` if it still references public classes in the unexported package.

Changing an `opens` may not affect compiling regular code, yet cause reflection to fail at runtime.

Changing `provides` may not impact API source or linkage, yet cause `ServiceLoader` to pick a different implementation or find none at all.

These distinctions belong in the “Impact” section of the changelog so users know which tests to run.

## 13. Structured changelog template

A uniform structure can be used for every module boundary change:

```markdown
## [2.0.0] - YYYY-MM-DD

### Breaking changes

**JPMS boundary: <module-name>**

- Change: <exports / opens / requires / uses / provides / rename>
- Before: <old module descriptor behavior>
- After: <new module descriptor behavior>
- Affected consumers: <module names / packages / frameworks>
- Compile-time impact: <what compilation may reject>
- Runtime impact: <linkage, reflection, services, resolution>
- Migration: <concrete code / module-info / command changes>
- Workaround (if any): <temporary action and removal plan>

### Added

- <new public export, module or provider>

### Changed

- <behavioral or dependency changes>

### Removed

- <module, package export or service removed>

### Verification

- <supported JDK/runtime configurations and verification commands>
```

The `<...>` tokens in the template are placeholders to be replaced with actual release data. Do not repeat the same change under multiple sections if doing so hurts readability; prefer one thorough entry linking to a detailed migration guide.

If a project uses the Keep a Changelog format, entries can be placed under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security` per project conventions. The essence is that users clearly see the JPMS impact, not specific section titles.

## 14. Full release note example for a boundary change

Suppose release 2.0.0 of a hypothetical library `com.acme.catalog` narrows its API, extracts a provider, and adds a dependency. The changelog could look like:

```markdown
## [2.0.0] - 2026-11-11

### Breaking changes

**JPMS module `com.acme.catalog`**

- Removed export `com.acme.catalog.legacy`.
  Consumers must switch to `com.acme.catalog.api`.
- Changed `com.acme.catalog.model` from unqualified
  `opens` to `opens ... to com.acme.json`.
  Other reflection frameworks need a supported integration.
- Module `com.acme.catalog.csv` now supplies
  `com.acme.catalog.spi.ExportService`.

### Changed

- Added dependency `requires java.net.http;`.
  Rebuild custom runtime images.
- `com.acme.model` is no longer a transitive
  readability dependency. Consumers that use its types
  must declare `requires com.acme.model;` directly.

### Migration

1. Replace legacy imports with the public API package.
2. Update any qualified reflection configuration.
3. Include and resolve the CSV provider module when needed.
4. Review module descriptors and runtime images.
5. Recompile and run modular integration tests.
```

This is an illustrative formatting example, not the release history of a real library.

For official releases, include links to commits/PRs, issues, migration guides, or API references if the project maintains them. Users need a clear path from noticing the change to executing upgrade steps.

## 15. Migration guides should have before/after examples

When breaking changes exist, a concise changelog should point to an upgrade guide with before/after code. Example of renaming a module:

Before:

```java
module com.acme.report {
    requires com.acme.catalog;
}
```

After:

```java
module com.acme.report {
    requires com.acme.catalog.api;
}
```

Before:

```java
import com.acme.catalog.legacy.LegacyCatalog;
```

After:

```java
import com.acme.catalog.api.CatalogClient;
```

If an API also changed semantics, show how to migrate parameters, exceptions, lifecycle, or provider configuration. Renaming imports alone is insufficient when implementations behave differently.

For runtime images, the guide can include rebuilding the image:

```shell
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.report \
  --output runtime
```

Paths and root modules in examples must be replaced to match actual builds. On Windows, module path elements are separated by semicolons rather than colons.

If providers must be linked into the image via service binding, `--bind-services` or an explicit root module may be needed. The guide should state the right option for the deployment architecture.

## 16. Changelogs for classpath vs. module path scenarios

A JAR can be used in two modes:

1. **Classpath:** classes are placed in the unnamed module; the descriptor inside the JAR is not enforced as a named module boundary.
2. **Module path:** the module system recognizes the module name and enforces readability, `exports`, and `opens`.

Consequently, a change affecting only `exports` may strongly impact named-module consumers without having the same direct effect on classpath consumers.

The changelog should document them separately:

```text
Affected: consumers running the library on the JPMS module path.
Classpath usage: no direct export-boundary change; verify API and
runtime behavior separately.
```

Do not infer that the classpath is completely unaffected: classes, methods, or dependencies may still change independently of the descriptor.

If a library transitions from an automatic module to an explicit module, record old/new module names and packages no longer exported broadly. An explicit module usually has tighter boundaries than an automatic module; many existing imports may need adjustment.

## 17. Using tools to gather release note details

When preparing a changelog, compare **the before and after release artifacts**, not only the source descriptor diff.

### Inspecting descriptors of each JAR

```shell
jar --describe-module --file catalog-client-1.9.0.jar
jar --describe-module --file catalog-client-2.0.0.jar
```

The output shows the packaged module name, `requires`, `exports`, `opens`, `uses`, and `provides`. For multi-release JARs, inspect the descriptor matching the target Java release.

### Inspecting modules in the current runtime

```shell
java --list-modules
```

For modules on the module path:

```shell
java --module-path mods --describe-module com.acme.catalog
```

With custom runtime images, use the executable inside the image rather than a `java` command that might point to a different JDK.

### Tracing resolution

```shell
java --show-module-resolution \
  --module-path mods \
  -m com.acme.report/com.acme.report.Main
```

This tool helps identify which modules are resolved in a specific run. It does not by itself prove reflection or service code paths work, so matching integration tests are still required.

### Analyzing dependencies

```shell
jdeps --summary --module-path mods catalog-client-2.0.0.jar
```

`jdeps` helps uncover static dependencies, and does not replace inspecting service providers, reflection, or artifact packaging. When writing “removed dependency”, verify against actual descriptors and build/runtime dependency graphs.

## 18. Evaluating version bump severity

No JPMS rule dictates that changing `exports` must increment a major version. Version bump levels are decided by the project's compatibility policy, typically combined with SemVer or another release convention.

One way to weigh them:

- **Breaking boundary change:** removing a published export, renaming a module currently used by consumers, removing a supported contracted provider, changing required reflection contracts. For projects strictly following SemVer, these are typically considered for a major release.
- **Backward-compatible API addition:** adding a new exported API package or adding an optional service without altering existing behavior. May fit a minor release depending on policy.
- **Bug fix / maintenance:** fixing a descriptor to match an already-documented contract without impacting compliant consumers. May fit a patch release, though still worth describing if actual behavior changes.

What matters is **the published contract and supported consumer scope**, not the line count changed in `module-info.java`. If an internal package was never publicly supported yet was accidentally exported, closing it can still break consumers that depended on it; the changelog should still warn of the practical impact.

## 19. Relationship between the changelog and API docs

The changelog answers “what changed in this release”, while other docs answer “what is the current state”:

- **Module descriptor:** machine-readable contract for readability, exports, opens, and service bindings.
- **Javadoc/API reference:** supported types, methods, and packages.
- **Architecture documentation:** rationale for module splits and dependency direction.
- **Migration guide:** upgrade steps between two releases.
- **Changelog:** change history, impact scope, and migration starting points.

Do not replace the changelog with a snapshot of the new descriptor. Users need to know what differs **compared to the previous release**, especially when their dependencies and configs were written for old module or package names.

In architecture docs, you can add a diagram:

```text
Before:
  com.acme.report --> com.acme.catalog
                           |
                           +--> com.acme.model

After:
  com.acme.report --> com.acme.catalog.api
                           |
                           +--> com.acme.model

Provider:
  com.acme.catalog.csv --> com.acme.catalog.spi
```

This diagram is illustrative; how dependencies are shown must reflect actual descriptors. The changelog can link to diagrams or migration guides instead of repeating lengthy details.

## 20. Maintainer checklist when releasing boundary changes

Before publishing a release with JPMS changes:

1. Determine module names and package exports of both old and new versions from packaged artifacts.
2. List changed `requires`, `requires transitive`, `requires static`, `exports`, `opens`, `uses`, and `provides` directives.
3. Categorize affected consumers: compile-time imports, binary runtime access, deep reflection, service discovery, or deployment.
4. State exact module/package/service names; avoid writing only Maven artifact coordinates.
5. If changes are not fully backward compatible, supply migration steps with before/after `module-info.java` and code.
6. Note required changes to launcher flags, module paths, or `jlink` configurations.
7. If suggesting workarounds like `--add-exports` or `--add-opens`, describe them as temporary measures, state their scope, and note the risk of relying on internal implementations.
8. Distinguish impact on classpath consumers vs. module path consumers.
9. Verify release notes using the exact target JDK version and artifacts.
10. Place breaking changes prominently; link to migration docs when details exceed a concise changelog.

**Conclusion:** Every module boundary change can alter how consumer code compiles, links, loads providers, or works with reflection. A changelog must clarify **before/after states, impact scope, and upgrade actions** for every significant change. Treating `module-info.java` as part of the API contract and documenting changes in a structured way reduces puzzling failures when users upgrade library versions or rebuild runtime images.
