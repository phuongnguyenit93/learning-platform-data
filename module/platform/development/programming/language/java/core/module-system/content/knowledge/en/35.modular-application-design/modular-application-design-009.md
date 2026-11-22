# Reviewing the Graph Using Dependency and Access Evidence

## Objectives

After this lesson, you will be able to review the module graph of a JPMS application using evidence from module descriptors, dependency analysis, and runtime; identify which dependencies are direct, transitive, or implementation-only; verify readability, `exports`, and `opens` in the right direction; detect unintentionally exposed packages or dependencies; and document verifiable findings before making architectural changes.

## 1. Why review the module graph using evidence?

A module graph is more than a list of `requires` lines. It describes resolved modules, readability relationships among them, exported or opened packages, and services used/provided.

A sound graph should answer:

- Which modules are the roots of the application or plugin layers?
- Which modules are required to compile and run each capability?
- Which dependencies appear in the public API and need to be propagated?
- Which consumers genuinely need to read another module or package?
- Which packages must be opened for reflection, and which modules are the targets?
- Which provider modules are pulled into the graph via service binding?
- Are any dependencies, exports, or opens unused or opened too broadly?

Do not conclude a dependency is redundant merely because a module name does not appear in a short code snippet. A dependency may be used in public signatures, reflection, service loading, resource lookup, generated code, or a code path exercised only at runtime. Combine multiple sources of evidence and verify both build and runtime.

## 2. Four layers of evidence to collect

### Module descriptors

`module-info.java` and `module-info.class` state the module's intent: `requires`, `exports`, `opens`, `uses`, and `provides`. This is the starting point for understanding the declared graph.

### Static dependency analysis

Tools such as `jdeps` analyze bytecode to find dependencies across modules/packages/classes. The output helps uncover direct dependencies, dependencies on internal JDK APIs, or dependencies not properly reflected in descriptors.

### Runtime resolution

The launcher can print resolved module information via `--show-module-resolution`. This provides evidence of the graph built in a specific launch, with a specific module path, root modules, and JVM options.

### Runtime access checks

APIs such as `Module.canRead`, `Module.isExported`, and `Module.isOpen` verify access relationships between two specific modules. This is runtime-state evidence, particularly useful when debugging reflection or plugin layers.

No single source answers every question on its own. Descriptors describe declarations, `jdeps` observes bytecode, the launcher reflects a specific resolution pass, and runtime access APIs check a specific relationship at runtime.

## 3. Start from each module's descriptor

For a modular JAR, run:

~~~bash
jar --describe-module --file mods/com.acme.orders.jar
~~~

The output shows the module name and packaged directives. Cross-check against source `module-info.java` if available; the running artifact is what determines runtime behavior.

Example descriptor:

~~~java
module com.acme.orders {
    requires com.acme.money;
    requires transitive com.acme.customer.api;

    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.integration;
    opens com.acme.orders.persistence to org.example.orm;

    uses com.acme.orders.spi.PaymentGateway;
}
~~~

During review, classify each directive:

| Directive | Review question |
|---|---|
| `requires` | Does the module genuinely need this dependency to compile or run? |
| `requires transitive` | Do types from the dependency appear in the public API such that consumers need readability? |
| `requires static` | Is the dependency intentionally compile-time only or optional at runtime by design? |
| `exports` | Is the package an API that consumers are supported in using? |
| Qualified `exports` | Do the listed target modules genuinely need this package? |
| `opens` | Which framework needs deep reflection into this package? |
| `uses` | Does the module actually load this service type? |
| `provides` | Is the provider registered with the right service type and implementation? |

Do not edit descriptors just to make output shorter. Each directive needs a corresponding justification and evidence.

## 4. Using `jdeps` to inspect bytecode dependencies

Run dependency analysis for a module:

~~~bash
jdeps --module-path mods --check com.acme.orders
~~~

`--check` validates the module's descriptor and dependencies and can suggest appropriate `requires` declarations. Read the full output to distinguish declared dependencies, bytecode-discovered dependencies, and related warnings.

View dependencies at the module level:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.orders
~~~

View dependencies appearing in the public API:

~~~bash
jdeps --module-path mods --api-only --module com.acme.orders
~~~

`--api-only` is useful for identifying which dependencies leak through public signatures. If the `orders` module returns type `Money` from the `money` module, consumers may need readability to `money`. This is when `requires transitive` should be considered.

You can print the minimal list of module dependencies to assist runtime image creation:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.orders
~~~

`jdeps` output is static evidence from analyzed bytecode. It does not automatically know about every dependency loaded dynamically via reflection, class names read from configuration, service providers discovered at runtime, or resources accessed by name. Treat the output as part of a review, not proof that every execution path is covered.

## 5. Distinguishing direct, transitive, and implementation-only dependencies

Suppose:

- `com.acme.orders` uses `Money` from `com.acme.money`.
- The public API of `orders` returns `Money`.
- `com.acme.client` only declares `requires com.acme.orders`.

The descriptor of `orders` may need:

~~~java
module com.acme.orders {
    requires transitive com.acme.money;
    exports com.acme.orders.api;
}
~~~

Because `Money` appears in the public API of `orders`, readability to `com.acme.money` is part of the contract consumers require.

Conversely, if `orders` only uses `Money` in an unexported implementation package, the dependency can be:

~~~java
module com.acme.orders {
    requires com.acme.money;
    exports com.acme.orders.api;
}
~~~

Do not turn every `requires` into `requires transitive`. Propagating dependencies widens consumers' graphs and turns implementation dependencies into part of the contract.

For `requires static`, verify whether the dependency is truly optional at runtime and whether code handles the module's absence. The `static` keyword does not mean the module system ignores the dependency in every step; it indicates a dependency required at compile time that may be absent at runtime.

## 6. Reviewing `exports` and public surface

For each exported package, identify:

1. Which consumers are using the package?
2. Which public types genuinely need to be supported?
3. Does the package contain implementation classes, adapters, or persistence details?
4. Can the API be separated into a distinct package to shrink the public surface?
5. Should a qualified export be used instead of an unrestricted export?

For example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.integration;
}
~~~

`com.acme.orders.api` is the public API for general consumers. The SPI is exported only to the specified `integration` module.

Do not confuse `public` in Java with a package being exported. A `public` class in an unexported package is still not normal accessible API for other modules. Conversely, once a package is exported, all `public` types inside it can become dependency targets for consumers.

For each export, document its rationale: public API, SPI, compatibility contract, or integration point. If no consumer or use case can be identified, investigate further before removing the export, as consumers may reside outside the current repository.

## 7. Reviewing `opens` and reflection evidence

`opens` grants deep reflection access at runtime. It is a separate boundary from `exports`.

For example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

During review, require concrete evidence:

- Which framework performs reflection?
- Does the framework run in a named module or the unnamed module?
- Which packages contain the fields/constructors/methods that need access?
- Do runtime errors or framework docs specify the exact package and target module?
- Can reflection be replaced with a public API or extension point?

If the framework runs in a named module, qualified `opens` is usually the clearest option:

~~~java
opens com.acme.orders.persistence to org.example.orm;
~~~

If the framework runs on the classpath, the runtime option may be:

~~~bash
--add-opens com.acme.orders/com.acme.orders.persistence=ALL-UNNAMED
~~~

Do not open an entire module just to resolve a reflection error in one package. Likewise, do not remove `opens` solely because no reflection calls appear in source: a framework may access fields by metadata, annotations, or names loaded from configuration.

The `Module.isOpen(packageName, targetModule)` API checks the current open state. It does not explain why the package was opened; cross-reference with descriptors and JVM options.

## 8. Checking readability and exports in the right direction

For a client module to use a public type in an API module, two key conditions are readability and export.

For example:

~~~java
Module client = Client.class.getModule();
Module api = PublicApi.class.getModule();

boolean readable = client.canRead(api);
boolean exported = api.isExported("com.acme.orders.api", client);

System.out.println("readable = " + readable);
System.out.println("exported = " + exported);
~~~

Pay attention to call direction:

- `client.canRead(api)`: `client` is the module needing to read the API.
- `api.isExported(packageName, client)`: `api` is the module owning the package and `client` is the target.

To check deep reflection, use:

~~~java
boolean open = api.isOpen("com.acme.orders.persistence", client);
~~~

A package can be exported without being opened. Consumers can call the public API without being allowed to deep-reflect into private fields. Likewise, a package opened for reflection does not automatically become public API that consumers can compile dependencies against.

When inspecting a specific class, start with:

~~~java
Module module = SomeType.class.getModule();

System.out.println("module = " + module.getName());
System.out.println("layer = " + module.getLayer());
System.out.println("loader = " + module.getClassLoader());
~~~

Layer and class loader information is useful when an application has multiple module layers or plugins. Two modules with the same name in two different layers can be two distinct module instances.

## 9. Observing the actual graph at startup

Run the application with:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

The launcher prints details of the module resolution process. Use the output to verify:

- Are the root modules correct?
- Are required dependencies found?
- Which modules are resolved from the module path?
- Are any JDK modules or providers pulled into the graph?
- Are there differences between local, test, and production environments?

Results depend precisely on the module path, root modules, parent configuration, and JVM options of that specific run. Therefore, when reporting a finding, record the launcher command or configuration used.

You can list runtime modules:

~~~bash
java --module-path mods --list-modules
~~~

And inspect a module's descriptor:

~~~bash
java --module-path mods --describe-module com.acme.orders
~~~

These commands verify modules visible to the launcher and individual module descriptors. They do not replace validating module layers created dynamically by the application at runtime if dynamic plugin loading is used.

## 10. Reviewing service binding and providers

Services can make the runtime graph wider than what is visible from direct `requires` lines.

Consumer declares:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
~~~

Provider declares:

~~~java
module com.acme.formatter.upper {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.formatter.upper.UppercaseFormatter;
}
~~~

When creating a configuration with `resolveAndBind(...)`, the module system can bind matching provider modules into the graph. If you inspect only `requires`, you can miss providers added via service binding.

During review, verify:

- Does the consumer declare `uses` for the right service type?
- Does the provider declare `provides` for the right interface?
- Is the provider in the module finder used for resolution?
- Does the provider have its own dependencies that must be resolved?
- Does the runtime layer searched by `ServiceLoader` contain the provider?

Configurations can be inspected with `Configuration.modules()` and `findModule(name)`. A provider being present in the configuration does not prove the provider instance initialized successfully; test service loading in integration tests.

## 11. Distinguishing static evidence from runtime evidence

Several situations commonly cause misunderstandings:

| Observation | What can be concluded | What cannot yet be concluded |
|---|---|---|
| `jdeps` finds a dependency | Analyzed bytecode references that module/package | Every runtime execution path uses the dependency |
| `jdeps` finds no dependency | No static dependency found within analyzed scope | No reflection, service, or dynamically loaded class names exist |
| Descriptor exports a package | Package is declared exported for targets | Every consumer can read the module |
| `canRead` returns `true` | Current module has readability to the target module | Specific package is exported |
| `isExported` returns `true` | Package is exported to target module | Deep reflection into private members is allowed |
| `isOpen` returns `true` | Package is open for deep reflection from target | Framework actively uses reflection or API can be changed safely |
| `--show-module-resolution` lists a module | Module was resolved during that launch | Every provider initializes or every plugin layer matches this graph |

When stating conclusions, specify the type of evidence and its scope. For example, "`jdeps` on the release artifact found dependency X" differs from "production runtime resolved module X" and differs from "consumer Y can access package Z".

## 12. Repeatable module graph review workflow

A practical per-release workflow:

1. Collect the exact modular JARs or exploded modules to be released.
2. Use `jar --describe-module` to record actual descriptors.
3. Run `jdeps --check`, `--list-deps`, and `--api-only` for critical modules.
4. Reconcile bytecode dependencies against `requires` and `requires transitive`.
5. List every `exports`, qualified export, and `opens`, tying each entry to a concrete consumer/framework.
6. Check `uses`/`provides` and providers found in the configuration.
7. Launch the application with `--show-module-resolution` in a production-like environment.
8. Use runtime access checks or integration tests to confirm readability, exports, and opens along critical access paths.
9. Record commands, JDK version, module path, JVM options, and artifact checksums/versions so results are reproducible.
10. Propose changes only after identifying issues and consumer impact.

If the application uses dynamically created plugin layers, add checks for each significant layer type and class loader. The boot layer's graph does not automatically represent graphs created later by the application.

## 13. How to document review findings

A solid finding should state:

- **Subject**: the module, package, or relationship under review.
- **Evidence**: descriptor, `jdeps` output, launcher resolution, runtime check, or integration test.
- **Scope**: artifact, JDK version, module path, root modules, and layer.
- **Finding**: missing/excess dependency, overly broad export, unjustified `opens`, or missing required access.
- **Impact**: which modules/consumers are affected, and at compile time or runtime.
- **Action**: descriptor change, JVM option, build configuration, or keep as-is with rationale.
- **Verification**: which command/test proves the change resolves the issue.

Example:

~~~text
Finding: com.acme.orders exports com.acme.orders.internal
Evidence: jar --describe-module shows an unqualified export;
         client module has no documented use of internal types.
Scope: release artifact 2.4, JDK 21, production module path.
Impact: implementation package is part of the accessible module surface.
Action: confirm external consumers, then consider qualified export
        or removing the export in a compatibility release.
Verification: compile supported consumers and run integration tests.
~~~

Do not label a dependency "unnecessary" based solely on searching for a class name in a repository. There may be external consumers, reflection, or service configurations. When evidence is missing, explicitly record what needs verification.

## 14. Common mistakes during review

- **Reading only `module-info.java`**: ignoring descriptors in actual artifacts, bytecode dependencies, and the runtime graph.
- **Treating `jdeps` output as complete runtime dependencies**: reflection, service loading, and dynamic class names may not be fully represented.
- **Reversing access check direction**: calling `api.canRead(client)` instead of `client.canRead(api)`.
- **Equating `exports` with `opens`**: public API access and deep reflection are two distinct permissions.
- **Removing `opens` without evidence**: frameworks may rely on metadata or dynamic reflection.
- **Keeping `exports` overly broad "just in case"**: public surface becomes a commitment hard to shrink later.
- **Adding `transitive` to every `requires`**: leaks implementation dependencies to consumers.
- **Checking only the boot layer**: overlooking plugin layers or dynamically created configurations.
- **Omitting runtime environment details**: resolution results can differ between local machines and production.

## Key takeaways

Reviewing a JPMS graph requires combining descriptors, static dependency analysis, runtime resolution, and access checks. `jdeps` uncovers bytecode dependencies and dependencies in public APIs; `jar --describe-module` reveals packaged descriptors; `--show-module-resolution` shows the graph for a specific run; `canRead`, `isExported`, and `isOpen` verify access relationships in the proper direction. State the scope and type of evidence clearly before removing dependencies, narrowing exports, or changing `opens`.
