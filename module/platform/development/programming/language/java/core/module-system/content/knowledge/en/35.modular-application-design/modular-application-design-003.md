# Do Small Modules Actually Reduce Dependencies?

## 1. Small modules do not automatically have fewer dependencies

Splitting an application into many small modules can make boundaries clearer, but increasing the number of modules does not automatically reduce the level of dependencies. A small module can still depend on many other modules; conversely, a larger-scoped module with strong cohesion and a stable API can create fewer dependency relationships.

Three factors should be distinguished:

- **Module size:** how many packages, classes, or features a module contains.
- **Cohesion:** whether the components inside the module serve the same responsibility and change together.
- **Coupling:** how many other modules a module must know about, call, or depend on to fulfill its responsibility.

The design goal is not to create the smallest possible modules. The goal is to create modules with clear responsibilities, intentional dependencies, and an API surface small enough to change independently.

For example, splitting a billing module into tiny modules:

    com.example.billing.invoice
    com.example.billing.tax
    com.example.billing.discount
    com.example.billing.customer
    com.example.billing.persistence
    com.example.billing.validation

If each module must directly call several of the remaining modules, the dependency graph can become dense. Changing a business rule may require editing multiple modules and updating multiple `module-info.java` files.

A design with fewer modules organized by business capability can be easier to understand:

    com.example.billing
    com.example.customer
    com.example.catalog
    com.example.infrastructure

This does not mean modules must always be merged. You need to evaluate the responsibility, dependency direction, and independent changeability of each part.

## 2. Evaluating dependencies using the module graph

Modules can be modeled as vertices in a directed graph. A `requires` directive creates a readability edge from the declaring module to the required module.

For example:

    module com.example.application {
        requires com.example.billing;
        requires com.example.customer;
    }

    module com.example.billing {
        requires com.example.customer;
        requires com.example.persistence;
    }

    module com.example.persistence {
        requires java.sql;
    }

This graph shows that `application` depends on `billing` and `customer`; `billing` in turn depends on `customer` and `persistence`. A change in `persistence` can affect `billing` and indirectly `application` if the API or behavior they rely on changes.

When analyzing coupling, examine:

- **Fan-out:** how many other modules a module depends on.
- **Fan-in:** how many modules depend on this module.
- **Dependency depth:** how many dependency layers must be traversed to reach a component.
- **Cycles:** whether modules form cyclic dependencies.
- **API surface:** how many packages and types a module exposes to other modules.

JPMS requires a valid module graph and forbids cycles in `requires` relationships. Therefore, a cyclic dependency chain causes an error when building or resolving the module graph. However, having no cycles does not mean the architecture is loosely coupled; a module can still directly depend on a large number of modules.

A small module with high fan-out can be an overloaded orchestration point. An API module used by many modules has high fan-in, which can be reasonable if the API is stable and has a clear responsibility.

## 3. Cohesion matters more than class count

A module should group components that change together because they serve the same responsibility. This is the practical meaning of cohesion in module design.

For example, the following classes usually belong together in a single billing module:

    com.example.billing.api.InvoiceService
    com.example.billing.internal.InvoiceValidator
    com.example.billing.internal.InvoiceCalculator
    com.example.billing.internal.InvoiceRepository

They work together to deliver one business capability and will likely need to change together when invoicing rules change. Splitting each class into its own module increases configuration and dependency relationships without creating a meaningful architectural boundary.

Conversely, if the billing module also contains email sending, user management, catalog access, and external payment integration, the module may be combining unrelated responsibilities. In that case, splitting by business capability can reduce coupling and allow each part to change independently.

A useful question when deciding whether to split is: **If this responsibility changes, which parts genuinely need to change with it?** If two groups always have to change together and have no need for independent deployment or governance, splitting them into two modules may merely create an artificial boundary.

## 4. How does JPMS help control dependencies?

A module descriptor makes dependency relationships explicit:

    module com.example.billing {
        requires com.example.customer;
        requires java.sql;

        exports com.example.billing.api;
    }

The `requires` directive declares which modules the current module needs to read. `exports` specifies which packages other modules can access under JPMS rules.

This separates two questions:

- Which modules does this module need to depend on?
- Which packages does this module want to expose to consumers?

A module can require another module without needing to export all of its own packages. Conversely, exporting a package does not automatically create a `requires` dependency; consumer modules still need appropriate readability.

JPMS expresses static boundaries, but it does not automatically choose the right business boundaries. If module A directly calls many internal classes across B, C, and D, adding `module-info.java` merely makes those relationships visible. It does not eliminate the coupling.

A good design typically has small, stable API modules and encapsulated implementation modules. Consumers depend on contracts rather than concrete implementation classes.

## 5. `requires`, `requires transitive`, and `requires static`

The three forms of `requires` affect the dependency graph differently.

### `requires`

    module com.example.billing {
        requires com.example.customer;
    }

The `billing` module needs to read the `customer` module. This is a standard dependency relationship and is expressed directly in the module descriptor.

### `requires transitive`

    module com.example.billing.api {
        requires transitive com.example.money;
        exports com.example.billing.api;
    }

If another module `requires com.example.billing.api`, readability to `com.example.money` is propagated according to the `requires transitive` rule. This is useful when public types in the billing API use types from `money` and consumers also need to read the `money` module to work with that API.

However, overusing `requires transitive` can cause dependencies to spread widely. A module consuming the API may end up reading extra modules it did not actively choose. Therefore, use `transitive` only when the dependency is genuinely part of the public contract.

### `requires static`

    module com.example.billing {
        requires static com.example.metrics;
    }

`requires static` indicates a dependency required at compile time that may be absent in the runtime configuration. It is commonly used for annotations, tooling, or optional integrations that a module does not need in every runtime environment.

If actual code requires classes from that module at runtime and the module is absent from the runtime configuration, the application can still encounter linkage or class-loading errors. `requires static` is not a way to skip a mandatory runtime dependency.

### Keeping dependencies explicit

A small module should not declare `requires transitive` for every dependency just to make compilation convenient for consumers. Identify which dependencies actually appear in the public API, which serve only the implementation, and which are optional.

## 6. Splitting modules toward stable dependencies

A useful principle is to make frequently changing parts depend on stable contracts, rather than having core APIs depend directly on frequently changing implementations.

For example, if billing needs to send notifications, an interface can be declared:

    package com.example.notification.api;

    public interface NotificationService {
        void send(String recipient, String message);
    }

The billing module depends on the contract:

    module com.example.billing {
        requires com.example.notification.api;
    }

An email or SMS implementation module can depend on that API:

    module com.example.notification.email {
        requires com.example.notification.api;
    }

Billing does not need to know the details of the SMTP client, HTTP client, or messaging provider. When the implementation changes, the billing module does not necessarily have to change.

You can go further with `ServiceLoader`:

    module com.example.notification.api {
        exports com.example.notification.api;
    }

    module com.example.billing {
        requires com.example.notification.api;
        uses com.example.notification.api.NotificationService;
    }

    module com.example.notification.email {
        requires com.example.notification.api;

        provides com.example.notification.api.NotificationService
            with com.example.notification.email.EmailNotificationService;
    }

The consumer knows the service type and the provider module registers the implementation. This reduces direct dependencies between the consuming module and the implementing module, though providers, module resolution, and runtime configuration still need to be managed.

Do not create a service abstraction for every method. Interfaces and service layers are only useful when there is a real boundary of change, replaceable implementations, or extensibility needs.

## 7. When should you split a module?

Splitting a module is usually beneficial when a group of features has one or more of the following characteristics:

- It has a distinct business responsibility and an independently describable API.
- It can be changed or released independently from the rest of the system.
- It has clearly distinct dependencies—for example, only the persistence module needs `java.sql`.
- Implementation packages need to be hidden from consumers.
- Multiple consumers need to share a stable contract.
- It can be tested, deployed, or lifecycle-managed separately.
- An optional dependency or external integration needs to be isolated.
- A clear one-way dependency direction can be established.

For example, an application might split:

    com.example.order.api
    com.example.order.core
    com.example.order.persistence
    com.example.order.integration

However, if `order.core` must directly call dozens of public types from `persistence` and `integration`, the boundary may be wrong. You may need to put repository or gateway interfaces in `core` and have implementations depend back on those contracts.

## 8. When should you avoid over-splitting?

Splitting too finely can create more cost than benefit:

- Many `module-info.java` files to maintain.
- Numerous `requires` and `exports` directives making the graph hard to read.
- Inter-module APIs easily becoming overly granular internal communication.
- A simple change forcing builds and versioning across multiple artifacts.
- Difficulty coordinating startup order, service discovery, and module layers.
- Many small packages being exported just so other modules can access them.
- Modules locked into the same release cycle despite being nominally separate.

If two modules are always built, tested, versioned, and deployed together while constantly calling each other's detailed APIs, they may not yet be good independent units.

On the other hand, do not keep everything in one huge module simply to minimize module count. If a module holds multiple unrelated responsibilities, its API bloats, and changes in one area constantly impact others, splitting can deliver real value.

## 9. A JPMS module is not synonymous with a Maven/Gradle subproject

A JPMS module should be distinguished from a build tool module/subproject.

- A **JPMS module** is a module system unit described by `module-info.java` or inferred as an automatic module.
- A **Maven module** is typically a subproject in a multi-module build.
- A **Gradle subproject** is a project within a build structure.

A Maven module or Gradle subproject can produce a JAR that is not an explicit JPMS module. Conversely, a single project can contain multiple source sets or artifacts depending on its build setup.

Dividing a repository into many subprojects does not automatically produce a good JPMS architecture. You need to specify clearly which module each artifact becomes, which packages are exported, and what the actual dependency graph looks like.

## 10. Measuring and inspecting the dependency graph

You can start by reading module descriptors:

    jar --describe-module --file billing.jar

Inspect class and package dependencies with `jdeps`:

    jdeps --module-path mods --check com.example.billing

Analyze package dependencies:

    jdeps --module-path mods --summary mods/com.example.billing.jar

Depending on the goal, you can also use:

    jdeps --module-path mods --list-deps mods/com.example.application.jar

The output of `jdeps` helps identify direct dependencies and required modules through bytecode analysis. It does not measure all coupling related to business logic, source changes, data, or runtime behavior.

When evaluating a module, examine:

1. How many modules it `requires`.
2. Whether those `requires` are genuinely direct dependencies.
3. Whether there are unnecessary `requires transitive` directives.
4. How many packages are exported.
5. How many other modules depend on its API.
6. Whether there are cycles or circular dependencies at the source/build level even though the module graph forbids them.
7. How many other modules typically must be modified or released when this module changes.

Do not use module count or lines of `requires` as the sole metric. Numbers only prompt questions; combine them with an understanding of responsibilities and change flows.

## 11. Comparing two ways of splitting modules

### Over-granular splitting by technical layer

    module com.example.invoice.entity { }
    module com.example.invoice.validation { }
    module com.example.invoice.calculation { }
    module com.example.invoice.repository { }
    module com.example.invoice.service { }

If each module must `requires` several of the others, the system can produce many dependency edges. Closely related business logic is scattered, and even a small change requires coordinating multiple modules.

### Splitting by responsibility and contract

    module com.example.invoice.api {
        exports com.example.invoice.api;
    }

    module com.example.invoice.core {
        requires com.example.invoice.api;
    }

    module com.example.invoice.persistence {
        requires com.example.invoice.api;
    }

    module com.example.application {
        requires com.example.invoice.api;
    }

In this design, `core` and `persistence` can implement contracts according to a chosen dependency architecture. This simple example does not show all repository injection or runtime wiring details, but it shows the API separated into a shared contract.

Another option is merging `core` and `persistence` if they always change and deploy together. The final decision depends on whether `persistence` needs independent replacement, has other consumers, or requires dependency isolation.

## 12. Key takeaways

- Small modules do not automatically reduce coupling; fewer modules do not automatically create a good architecture either.
- Cohesion and dependency direction matter more than size or class count.
- Evaluate fan-in, fan-out, dependency depth, API surface, and architectural cycles.
- `requires` creates a direct dependency; `requires transitive` propagates readability and must be used intentionally.
- `requires static` fits compile-time dependencies that are optional at runtime, not mandatory runtime dependencies.
- Stable API modules allow implementations to change independently.
- `ServiceLoader` can reduce direct dependencies between consumers and providers when implementations need to be replaceable.
- Split modules only when boundaries of responsibility, change, release, or governance are genuinely independent.
- Do not confuse a JPMS module with a Maven module or Gradle subproject.
- Use `jar --describe-module` and `jdeps` to observe dependencies, combined with change and business-responsibility analysis.

**Small modules only reduce dependencies when their boundaries reflect an independent responsibility and modules communicate through stable contracts.** If splitting merely increases the number of `requires`, `exports`, and coordination points, the architecture can become more complex even though each module has fewer classes.

## References

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 Tool Specifications — jdeps: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html