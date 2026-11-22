# Module Graphs in Architecture Documentation

When designing a Java application using the Java Platform Module System (JPMS), package diagrams or Maven/Gradle dependency lists are not enough to describe boundaries between parts of the system. JPMS organizes code into **named modules**, links them via `requires` directives, and controls API access through `exports`, `opens`, and readability relationships. In architectures with service providers or custom ModuleLayers, the set of modules present at runtime also depends on root modules, ModuleFinder, and runtime configuration.

A valuable **module graph** in architecture documentation must clarify which modules exist, their dependency relationships, which packages are exposed, which providers are used via service contracts, and which modules are actually resolved in each runtime environment. This documentation helps reviewers assess dependency direction, helps operators launch with the right configuration, and helps developers know where to make updates when a module is renamed, changes its descriptor, or is missing at runtime.

A module graph should not be treated as a decorative picture. It needs clear definitions, verifiable data sources, and a process to keep it updated alongside the source code.

## 1. Purpose and scope

A module architecture page should help answer these questions:

- Which named modules is the system divided into? What is each module's responsibility?
- Which module is the application entry point? Which modules are merely libraries?
- Does the dependency direction between modules respect layering and domain boundaries?
- Which relationships are **requires**, **requires transitive**, or **requires static**?
- Which module owns the API, which packages are exported, and which are purely implementation?
- Which services are consumed via **uses**, and which implementations declare **provides**?
- Which root modules exist at runtime? Are provider modules actually resolved?
- Do plugins live in the boot layer or custom layers, and which class loaders do they use?
- Which consumers and launcher configurations are affected by changes to a module name or package boundary?

Documentation can include one overview graph for the whole system and several detailed graphs per subsystem. For large systems, group modules instead of putting every JDK module and library into one overloaded diagram.

A module graph **does not replace** `module-info.java`: the descriptor remains the enforcement source of the module system. Documentation adds architectural meaning and explains why those boundaries were chosen.

## 2. Distinguishing graph types

Not every arrow between two modules carries the same semantics. Place the **Graph type** right at the top of the diagram.

| Graph type | Source of truth | Meaning |
|---|---|---|
| Declared dependency graph | `requires` directives in descriptors | Which module directly declares a dependency on which |
| Resolved module graph | Root set, module finder, module configuration | Which modules are included in the runtime configuration |
| Readability graph | JPMS rules and runtime additions | Which module can read which module |
| Service relationship graph | `uses` and `provides` | Which service types consumers need and which modules supply them |
| ModuleLayer topology | Parent/child layer and class loader setup | In which runtime context modules are defined |

A **requires** graph does not by itself represent deep reflection permissions. A **uses/provides** graph does not prove the consumer has **requires** on the provider module. A JAR may be observable on the module path without belonging to the resolved graph.

Documentation should separate these views, or use very clear labels and legends if combining them into one diagram.

## 3. Nodes and edges must be based on module names

A node in a declared dependency graph typically represents a module name taken from the module descriptor:

~~~java
module com.acme.orders.app {
    requires com.acme.orders.api;
    requires java.logging;
}
~~~

Related nodes:

- **com.acme.orders.app**: orchestrating application.
- **com.acme.orders.api**: API contract.
- **java.logging**: system module provided by the Java runtime.

Two edges go from **com.acme.orders.app** to **com.acme.orders.api** and **java.logging**, because that is the direction declared in `requires`. Do not reverse arrows in the direction of “library module serves application”; doing so makes the dependency graph misleading.

Nodes should use the **JPMS module name**, not the JAR filename or Maven `artifactId`, as the primary label. Example:

~~~text
JPMS module name: com.acme.orders.api
Maven coordinates: com.acme:orders-contract:2.1.0
Artifact filename: orders-contract-2.1.0.jar
Source descriptor: modules/orders-contract/src/main/java/module-info.java
~~~

The three names may overlap partially, but do not have to match. Module names and package names are also distinct concepts. A module can own multiple packages; whether a package is exposed is determined by `exports`/`opens`.

## 4. Module graph example for a reporting system

Suppose a system has four application modules and two provider modules:

- **com.acme.report.app**: application entry point, orchestrates report export requests.
- **com.acme.report.api**: public API and `ReportExporter` service interface.
- **com.acme.report.csv**: CSV export implementation.
- **com.acme.report.json**: JSON export implementation.

API descriptor:

~~~java
module com.acme.report.api {
    exports com.acme.report.api;
}
~~~

App descriptor:

~~~java
module com.acme.report.app {
    requires com.acme.report.api;
    requires java.logging;

    uses com.acme.report.api.ReportExporter;
}
~~~

CSV provider descriptor:

~~~java
module com.acme.report.csv {
    requires com.acme.report.api;

    provides com.acme.report.api.ReportExporter
        with com.acme.report.csv.CsvReportExporter;
}
~~~

JSON provider descriptor:

~~~java
module com.acme.report.json {
    requires com.acme.report.api;

    provides com.acme.report.api.ReportExporter
        with com.acme.report.json.JsonReportExporter;
}
~~~

The application depends only on the interface and API. Adding the JSON provider does not force the app to declare `requires` on the JSON implementation. That independence is an architectural decision that should be clearly reflected in documentation.

## 5. Drawing a declared requires graph with Mermaid

Markdown in the repository can hold Mermaid diagram source so readers can review it like source code.

~~~mermaid
flowchart LR
    App["com.acme.report.app"]
    Api["com.acme.report.api"]
    Csv["com.acme.report.csv"]
    Json["com.acme.report.json"]
    Logging["java.logging"]

    App -->|"requires"| Api
    App -->|"requires"| Logging
    Csv -->|"requires"| Api
    Json -->|"requires"| Api
~~~

This diagram represents only the **declared requires graph**. It does not claim that the CSV/JSON providers are resolved into the boot layer, nor does it assert that the app directly `requires` the providers.

Place a metadata block alongside the diagram:

~~~text
View: declared requires graph
Scope: report application modules
Entry module: com.acme.report.app
Source: module-info.java of each module
JDK target: JDK version in build/release
Runtime variant: service binding not yet shown
Owner: report architecture team
~~~

If Mermaid is unsupported, it can be rendered as an image while keeping the Mermaid/DOT source file in the repository. Diagrams stored solely as images are hard to diff, review, and maintain.

## 6. Recording differences between requires, transitive, and static

Modifiers in the descriptor change how modules connect.

Example:

~~~java
module com.acme.shop.facade {
    requires transitive com.acme.shop.api;
    requires static com.acme.annotations;
    requires java.logging;
}
~~~

Documentation should distinguish:

- **requires**: mandatory direct dependency in the module configuration.
- **requires transitive**: mandatory dependency that also propagates readability under JPMS rules to modules reading `facade`.
- **requires static**: dependency needed at compile time that may be absent at runtime; code must still manage execution branches needing it.

Diagram:

~~~mermaid
flowchart LR
    Facade["com.acme.shop.facade"]
    Api["com.acme.shop.api"]
    Anno["com.acme.annotations"]
    Log["java.logging"]

    Facade -->|"requires transitive"| Api
    Facade -.->|"requires static"| Anno
    Facade -->|"requires"| Log
~~~

Dashed lines are a documentation convention for **requires static**, not JPMS syntax. The legend must explain this.

Do not change an edge from `requires` to `requires transitive` just to reduce lines of `requires` in consumers. The `transitive` modifier typically reflects the exposed API and affects downstream modules.

## 7. Readability does not equal package access

One named module reading another does not mean it can access every public class in the target module.

Example:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

And:

~~~java
module com.acme.web {
    requires com.acme.customer;
}
~~~

**com.acme.web** has readability to **com.acme.customer**, but the package **com.acme.customer.internal** is not exported. Consumers cannot import classes in internal packages merely because they have `requires`.

Therefore, documentation needs a package boundary table:

| Source module | Package | Directive | Access scope |
|---|---|---|---|
| com.acme.customer | com.acme.customer.api | exports | Named modules reading customer |
| com.acme.customer | com.acme.customer.spi | exports ... to com.acme.integrations | Designated consumers |
| com.acme.customer | com.acme.customer.model | opens ... to com.acme.json | Deep reflection from designated framework |
| com.acme.customer | com.acme.customer.internal | Not exported/opened | Internal implementation |

Permissions to distinguish:

- **exports**: allows access to public types in the package given readability.
- **qualified exports**: exports only to specified named modules.
- **opens**: allows deep reflection at runtime for the scope declared in the descriptor.
- **qualified opens**: opens a package to specific reflection modules.
- **open module**: opens packages more broadly and should be recorded as an architectural decision.

Do not draw a **requires** edge simply because a module owns a package opened to another framework. That is a reflection permission relationship, not necessarily a dependency from the source module to the framework.

## 8. Drawing service graphs separately from dependency graphs

A service graph illustrates consumer and provider relationships through a **service type**:

~~~mermaid
flowchart LR
    App["com.acme.report.app"]
    Contract["ReportExporter"]
    Csv["com.acme.report.csv"]
    Json["com.acme.report.json"]

    App -->|"uses"| Contract
    Csv -->|"provides"| Contract
    Json -->|"provides"| Contract
~~~

In documentation, state clearly that a **provides** arrow does not replace the provider's **requires** dependency on the API module. Likewise, an app declaring **uses** does not mean the app directly reads the implementation module.

When the application runs, provider modules must be resolved in an appropriate layer. One option is selecting providers as roots via **--add-modules**; another option in programmatic configuration is **Configuration.resolveAndBind(...)** to add provider modules based on used services.

Each runtime variant should record:

~~~text
Service contract: com.acme.report.api.ReportExporter
Consumer: com.acme.report.app
Providers: com.acme.report.csv, com.acme.report.json
Provider discovery: ServiceLoader
Provider resolution: added root or service binding
Service API owner: com.acme.report.api
~~~

Do not use a service edge to convey that the provider already exists in the runtime graph; separate resolution evidence is needed if documentation asserts that.

## 9. Distinguishing observable and resolved modules

A JAR sitting on the module path only means it is **observable** by the corresponding module finder. Whether a module enters the configuration depends on the root set and resolution process.

Suppose:

~~~text
dist/modules/
├── com.acme.report.app.jar
├── com.acme.report.api.jar
├── com.acme.report.csv.jar
└── com.acme.report.json.jar
~~~

If launched with only root **com.acme.report.app**, the app resolves dependencies from its `requires`, but the two providers do not appear automatically just because their JARs are in the same folder.

Therefore, documentation must separately record:

- The set of **observable modules** or finder sources.
- Selected root modules for resolution.
- Dependency closure.
- Provider modules added via service binding or extra roots.
- Which modules are actually defined in the boot layer or custom layers.

If **--limit-modules** is used, the set of observable modules can be restricted further. If **--add-reads** is used, the runtime readability graph may differ from the `requires` edges declared in descriptors.

Do not draw an entire JAR folder as a set of resolved modules without verifying the launch configuration.

## 10. Recording runtime variants of the module graph

A system can have multiple valid graphs for different purposes:

- Production application.
- Application in integration tests.
- Runtime image built with jlink.
- Host with the CSV plugin.
- Host with both JSON and CSV plugins.
- Application portion running in a custom ModuleLayer.

Maintain a **runtime variants** page, with metadata per variant:

~~~text
Variant name: production-report
Entry module: com.acme.report.app
Main class: com.acme.report.app.Main
JDK target: version in build manifest
Module path: dist/modules
Root modules: com.acme.report.app
Extra roots: com.acme.report.csv
Service binding: describe if applicable
Runtime image: dist/runtime (if any)
VM module flags: list if any
~~~

Two variants may share the same source descriptors yet have different resolved graphs. When comparing design against runtime, state clearly which variant is being inspected and which release/commit the artifacts belong to.

This matters when a bug only happens in CI or inside a container, where the module path and runtime image can differ from a developer machine.

## 11. Automatic modules and unnamed modules in migration docs

A project migrating from classpath to module path may contain multiple module kinds.

| Status | How to depict in diagrams |
|---|---|
| Explicit named module | Node carrying module name from `module-info.class` |
| Automatic module | Node carrying automatic name and **automatic** label |
| Unnamed module/classpath | Separate block labeled **classpath / unnamed**, not masquerading as a named module |
| System module | JDK module group, e.g., `java.base` and `java.logging` |

An automatic module is a named module whose descriptor is generated automatically; it has broader compatibility mechanics than an explicit module. Documentation should label it to avoid treating an automatic module's export surface as an API contract reviewed by the library author.

An unnamed module has no name usable in a **requires** directive. Do not draw a regular `requires` edge from an explicit named module to a classpath block as if JPMS could resolve an unnamed module by name.

If a transitional workaround uses **--add-reads** or **--add-exports**, document it as a runtime escape hatch with an owner and removal deadline. Omitting that label can hide unmodularized dependencies.

## 12. ModuleLayer topology for plugin architectures

In plugin systems, a declared requires graph alone is often insufficient. There may be a boot layer holding the host and API, plus child layers holding providers.

~~~text
Boot layer
├── com.acme.host
└── com.acme.plugin.api

CSV plugin layer
└── com.acme.plugin.csv

JSON plugin layer
└── com.acme.plugin.json
~~~

Topology diagram:

~~~mermaid
flowchart TB
    Boot["Boot layer: host + plugin API"]
    Csv["CSV plugin layer"]
    Json["JSON plugin layer"]

    Boot -->|"parent of"| Csv
    Boot -->|"parent of"| Json
~~~

The **parent of** edges are not `requires`. Documentation should explicitly record:

1. ModuleFinder and artifact directory for each child layer.
2. Root set and parent configuration.
3. Class loader strategy: shared loader, per-plugin loaders, or custom mapping.
4. Service API module shared from the parent layer.
5. Which layer ServiceLoader searches for providers.
6. Plugin lifecycle relationship with the host.

Two modules in independent layers can have the same name while belonging to different runtime contexts. Do not use a single module name string as a unique identifier for every module object across the entire JVM.

Sibling layers do not automatically read each other's modules. If two plugins need the same API, place the service contract in an appropriate parent layer instead of copying multiple copies of the API into each plugin.

## 13. Tools to cross-check docs against real modules

Architecture docs should show how to reproduce technical checks from the JDK.

### 13.1. Reading the descriptor inside a modular JAR

~~~bash
jar --describe-module --file dist/modules/com.acme.report.app.jar
~~~

Used to verify the module name, `requires`, `exports`, `opens`, and service declarations in the built artifact. This is a reliable source to check whether diagrams match actual releases.

### 13.2. Observing module resolution at runtime

~~~bash
java --show-module-resolution \
     --module-path dist/modules \
     -m com.acme.report.app/com.acme.report.app.Main
~~~

The output helps inspect resolved modules and runtime dependency relationships. When a module is missing or the graph is invalid, the launcher may abort before `main`. Keep exact module names and exceptions for diagnostics.

### 13.3. Analyzing dependencies with jdeps

~~~bash
jdeps --module-path dist/modules \
      --print-module-deps dist/modules/com.acme.report.app.jar
~~~

**jdeps** helps analyze dependencies in bytecode and module metadata. However, it cannot fully describe dependencies introduced only via reflection, dynamically chosen service providers, or runtime configurations external to bytecode.

Do not present a raw `jdeps` output as the entire architecture graph without explaining its source, generation method, and limitations.

### 13.4. Reading the runtime module graph via Java API

~~~java
ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
~~~

You can check for a specific module:

~~~java
boolean present = ModuleLayer.boot()
    .findModule("com.acme.report.api")
    .isPresent();
~~~

These snippets reflect modules in the boot layer or search parent layers per relevant APIs. For a custom plugin layer, inspect that layer directly instead of assuming the boot layer holds all defined modules in the JVM.

## 14. Module catalog template

Alongside diagrams, maintain a searchable module catalog.

| Field | Example |
|---|---|
| Module name | com.acme.report.api |
| Responsibility | Report contracts and service types |
| Source path | modules/report-api |
| Artifact | com.acme:report-api |
| Descriptor | modules/report-api/src/main/java/module-info.java |
| Owner | Report API maintenance team |
| Exported packages | com.acme.report.api |
| Required modules | java.base (implicit) |
| Service contracts | ReportExporter |
| Runtime layer | Boot layer |
| Stability | Public API, versioned per policy |
| References | ADR on service interface, integration tests |

This catalog helps readers move from graph nodes to source and owners. Prefer relative repository paths or versioned documentation links rather than links to branches mismatched with the release.

Do not copy descriptors verbatim into every page. Include only key elements and point to `module-info.java` to reduce the risk of descriptions falling behind source.

## 15. Suggested architecture documentation layout

A project can organize as follows:

~~~text
docs/
└── architecture/
    └── modules/
        ├── README.md
        ├── graph.md
        ├── catalog.md
        ├── packages.md
        ├── services.md
        ├── runtime-variants.md
        └── decisions/
            └── adr-0007-service-providers.md
~~~

A graph page should include at least:

- **Scope**: subsystem, JDK target, application variant, and release/commit.
- **Graph definition**: declared requires, readability, services, or runtime resolution.
- **Diagram**: diagram with module name nodes and consistent edge directions.
- **Legend**: requires, transitive, static, service, or parent layer.
- **Module catalog**: links to owners, source descriptors, and artifacts.
- **Boundary table**: important package exports/opens.
- **Runtime differences**: root set, service binding, ModuleLayer, and escape hatches.
- **Verification**: artifact and runtime verification commands, links to CI runs.
- **Architecture decisions**: rationale for dependency direction and migration plans.

Diagrams provide quick visual orientation; tables and explanations let readers verify precision. Avoid cramming every detail of exports, opens, versions, and owners directly onto arrows, making diagrams unreadable.

## 16. Managing graph updates alongside source code

Module graphs risk going stale if `module-info.java` changes without updating docs. Add these steps to pull request reviews:

1. Identify which module descriptors changed.
2. Compare module names and `requires` before/after.
3. Update edge labels if `requires` changed to `transitive` or `static`.
4. Update the module catalog when adding, removing, or renaming modules.
5. Update boundary tables if `exports` or `opens` changed.
6. Update the service graph when `uses`/`provides` changed.
7. Update runtime variants if root modules or launcher flags changed.
8. Run compile/integration tests on the module path for relevant variants.
9. Check downstream consumers affected by module names or package visibility.
10. Link to an ADR if the change shifts architectural boundaries or dependency direction.

Major changes must record their rationale. For instance, switching from app `requires` provider implementation to app `uses` service contract is an important architectural shift, not merely editing two lines in a descriptor.

## 17. Using CI to detect documentation drift

Parts of this can be automated:

- Verify every published named module has a catalog entry.
- Compare module names in artifacts against documented module names.
- Flag `requires`/`exports` diffs so reviewers update the graph.
- Detect new automatic modules in a runtime variant with an explicit-only policy.
- Enforce layering rules, e.g., domain API does not depend on infrastructure adapters.
- Run startup tests with **--show-module-resolution** for target deployment configurations.
- Run integration tests for service providers and custom layers.
- Keep check evidence tied to commits and built artifacts.

Automated checks have limits. Bytecode analysis tools cannot replace inspecting framework reflection feedback or dynamically selected providers. Architecture documentation still requires explanation from those responsible for module boundaries.

## 18. Common documentation mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Labeling nodes with JAR filenames | Confuses module name with artifact | Read names from `module-info.class` |
| Reversing `requires` arrows | Misunderstands dependency direction | Draw from consumer to dependency |
| Drawing `uses` as `requires` to provider | Misrepresents service relationship | Separate the service graph |
| Omitting `transitive`/`static` | Loses readability/compile-dependency semantics | Label modifiers on edges |
| Merging `exports` and `opens` into one category | Confuses API access with reflection | Use a package boundary table |
| Assuming all JARs on path are resolved | Inaccurate runtime graph | Document root set and verify resolution |
| Treating unnamed modules as named nodes | Hides classpath dependencies | Label migration boundaries |
| Omitting layer topology when plugins exist | Unclear module identity/runtime context | Record parent layers and class loaders |
| Keeping only static PNGs | Hard to diff and review | Keep Mermaid/DOT sources |
| Not tying graphs to a release/JDK | Readers don't know which diagram is current | Add source revision and runtime variant |
| Not showing how to verify the graph | Hard to use for troubleshooting | Attach JDK commands and CI artifacts |

Reliable graph documentation must allow readers to trace from the diagram to actual descriptors and artifacts, rather than merely making undated claims like “module A depends on module B”.

## 19. Assessing impact of architectural changes

Suppose the team wants to remove an `export` from **com.acme.report.api**. From the dependency graph, you can find modules with readability to the API module. However, readability alone does not prove which modules actually import specific classes from that package; combine source search with compile tests.

If renaming a module, update:

- Consumers' `requires` directives.
- `--module`/`-m` and `--add-modules` in launch scripts.
- `ModuleFinder` root names in custom layer creation code.
- Build plugins, `jlink` configuration, and runtime variant docs.
- Tests checking module names or service provider resolution.

If changing a **requires** to **requires transitive**, update edge labels on the graph and explain downstream readability impacts. If adding a new provider, the app may keep the same `requires`, while the service graph and runtime configuration may change.

A graph is a tool to locate impact points, not proof on its own that every consumer's source code is affected.

## 20. Practice exercises

1. Create the API, app, and two provider modules as in the report example.
2. Draw the declared dependency graph using Mermaid.
3. Draw a separate service relationship graph, distinguishing `uses`/`provides` from `requires`.
4. Add a facade module using **requires transitive** and update the legend.
5. Add a **requires static** dependency and explain runtime limits.
6. Build a table of `exports`, qualified exports, and `opens` for a demo module.
7. Package as modular JARs and inspect with **jar --describe-module**.
8. Run the app with **--show-module-resolution** and compare against the diagram.
9. Try adding a provider via **--add-modules** and document a new runtime variant.
10. Place a provider in a custom ModuleLayer and draw the parent/child topology.
11. Add an automatic module node with a clear migration label.
12. Rename a module in its descriptor and list the docs and consumers needing updates.
13. Create a CI check detecting `requires` changes in built artifacts.
14. Write an ADR explaining why the app depends on API instead of implementation.
15. Review the graph to spot dependencies pointing against intended architectural direction.

## 21. Principles to remember

- Module graphs must state clearly whether they depict **declared dependencies**, **resolved modules**, **readability**, **service relationships**, or **layer topology**.
- JPMS nodes should use **module names**; Maven coordinates, packages, and JAR filenames are separate metadata.
- **requires**, **requires transitive**, and **requires static** need distinct labels.
- **exports** and **opens** describe package access, and do not create `requires` edges.
- Being present on the module path does not guarantee a module is resolved.
- Service contracts help consumers avoid direct `requires` on provider implementations.
- Automatic modules and unnamed modules must be accurately labeled during migration.
- Custom ModuleLayers and class loaders need separate explanation when plugins exist.
- Diagrams should have Mermaid/DOT source and link to `module-info.java`.
- Documentation must state scope, commit/release, JDK, root modules, and runtime variant.
- Verify against artifacts and runtime via **jar --describe-module**, **jdeps**, **--show-module-resolution**, and integration tests.
- Update graphs alongside module descriptors to avoid drift from the real design.

**Module graphs in architecture documentation must answer: which module depends on which, what access is exposed, and which runtime configuration actually connects them.** When diagrams are clearly defined and verifiable against descriptors, they become valuable tools for code review, migration, troubleshooting, and managing system boundaries.
