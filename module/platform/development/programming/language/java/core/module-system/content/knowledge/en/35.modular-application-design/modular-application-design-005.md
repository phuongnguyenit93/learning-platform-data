# Avoiding Overly Deep or Overly Dense Module Graphs

## Objectives

After this lesson, you will be able to read the module graph of a JPMS application, recognize overly long dependency chains and modules with too many `requires` relationships, understand their impact on changeability and maintainability, and organize modules around sensible API, domain, and service boundaries.

## 1. What is a module graph?

A module graph is a directed graph describing modules and the dependency relationships between them. Each module is a vertex (node). A directed edge from A to B indicates that module A declares `requires B`, meaning A needs to read module B.

For example:

~~~text
com.acme.app
    |
    v
com.acme.orders
    |
    v
com.acme.customers
    |
    v
com.acme.database
~~~

In this diagram, `app` depends on `orders`, `orders` depends on `customers`, and `customers` depends on `database`. When a module is resolved, JPMS continues resolving the dependencies it requires to construct a consistent graph.

A good graph clearly reveals architectural boundaries: upper-layer modules use the APIs of lower layers, sibling modules have reasonable dependency levels, and implementation details do not leak across the entire system.

Two characteristics to watch:

- **Depth:** the number of dependency steps along a long path in the graph. The chain `A -> B -> C -> D -> E` is deeper than `A -> B -> C`.
- **Edge count:** the number of dependency relationships between modules. A module with too many outgoing edges typically knows about or depends on too many components; a module with too many incoming edges may be becoming a foundational hub that many modules are forced to use.

Depth and edge count are not standalone quality metrics. A small graph with wrong boundaries is still hard to maintain. Use them as signals for investigation, combined with cohesion, API scope, and each module's reasons to change.

## 2. Why do overly deep graphs hurt maintainability?

Long dependency chains make the architecture hard to understand and allow changes at lower layers to ripple through many layers.

~~~text
app -> workflow -> order-service -> customer-service -> persistence -> database-driver
~~~

When `app` needs a simple operation, passing through many modules forces readers to understand numerous intermediate layers. If each module merely forwards calls without owning a distinct responsibility, those modules add navigation overhead without providing useful boundaries.

Deep graphs can lead to:

- Difficulty tracing the origin of an API or dependency.
- Signature changes in low-level modules forcing edits across multiple intermediate modules.
- Difficulty testing part of a feature because an entire chain of modules must be assembled.
- Intermediate modules becoming thin pass-through layers that only forward calls or data types.
- Difficulty reusing an individual module because it drags along an entire chain of dependencies.

Not every multi-layer chain is bad. Domain, application, adapter, and infrastructure can be necessary layers. Problems arise when an intermediate layer has no distinct responsibility, or when lower-layer APIs are passed straight through multiple layers without adding value.

## 3. Why do overly dense graphs hurt maintainability?

Modules with many direct `requires` must know about many other modules. This increases coupling and causes changes in one module to affect many places.

For example:

~~~text
             +--> customer
             +--> order
app ---------+--> inventory
             +--> payment
             +--> shipping
             +--> reporting
             +--> notification
~~~

If `app` directly invokes every feature module, it may be a reasonable composition root at the startup layer. However, if all business logic is concentrated in `app`, that module will know too much and become the single place where orchestration, conversion, and dependencies for the entire system accumulate.

Dense graphs can also arise when:

- Modules share an overly broad utility module.
- An API module exports too many packages and is used by many modules.
- Multiple modules depend on a central module holding all kinds of data types.
- `requires transitive` is used to pass dependencies even when the API does not need to expose those dependencies.
- Modules are split too finely, turning every operation or class into its own module.

As a result, a small change can require updating multiple modules, resolution and testing become more complex, and source-code ownership boundaries become hard to identify.

## 4. Split modules by responsibility, not by class

A module is a unit of encapsulation, resolution, and access control at the architectural level. Do not turn every class into a module just because JPMS allows it.

A module should contain a group of packages with closely related responsibilities and relatively similar reasons to change. Ask yourself:

- Which types tend to change together?
- Which group of capabilities can be described by a clear API?
- Which modules genuinely need to use that group's API?
- Can the internal implementation remain inside the same module?
- Can the module be tested or reused independently?

For example, the `orders` module can contain the `domain`, `application`, and internal `adapter` packages of the order scope if they belong to the same deployment unit:

~~~text
com.acme.orders
  com.acme.orders.api
  com.acme.orders.domain
  com.acme.orders.application
  com.acme.orders.internal
~~~

Separate `orders.api` into its own module only when there is a real need: multiple other modules require a stable contract, implementations can be replaced independently, or the API needs to be published and versioned separately.

Splitting too finely adds extra descriptors, build configurations, and dependency declarations. Splitting too coarsely gives a module too many responsibilities and forces it to export too much API. The goal is modules with high cohesion and just enough dependencies.

## 5. Design clear dependency directions

An understandable way to organize modules is to divide them into layers with distinct responsibilities:

~~~text
             com.acme.app
                  |
                  v
        com.acme.orders.application
             /           \
            v             v
  com.acme.orders.domain  com.acme.orders.spi
            ^                    ^
            |                    |
  com.acme.orders.adapter  com.acme.shipping.provider
~~~

The diagram illustrates the idea: `application` orchestrates use cases; `domain` contains business rules; `adapter` connects external systems; `provider` implements service contracts. Choose `requires` directions so that stable APIs do not depend back on implementation details.

Example with API and implementation:

~~~text
com.acme.app ----requires----> com.acme.orders.api
com.acme.orders.impl ----requires----> com.acme.orders.api
~~~

Implementation descriptor:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;
}
~~~

Consumer descriptor:

~~~java
module com.acme.app {
    requires com.acme.orders.api;
}
~~~

If `app` must instantiate the implementation directly, it has to know the implementation module or implementation class. That dependency can be avoided with `ServiceLoader`: `app` declares `uses` on the service API, while the implementation declares `provides`. The consumer depends only on the contract and does not need to `requires` the provider directly.

There is no need to force every project into the same layer diagram. What matters is that dependencies have an explainable direction and implementation details are not pushed back into the API.

## 6. Keep APIs small and use `exports` intentionally

Exported packages become the API surface that other modules can use. Exporting too many packages makes a module prone to consumers depending on internal details.

For example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Unexported `domain` or `internal` packages cannot be accessed by other modules through normal means, even if classes inside are declared `public`.

If only one specific module needs access to a package, a qualified export can be used:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.orders.adapter;
}
~~~

This keeps the API scope narrow. However, a qualified export also creates a specific coupling between two modules; use it only when it represents an intentional architectural boundary.

Avoid creating a `common` or `shared` module containing all shared types. Such a module easily becomes a hub attracting many edges. Divide APIs by domain or stable capability, and move shared types into a dedicated module only when they genuinely have independent semantics.

## 7. Use `requires transitive` at the right time

`requires transitive` propagates readability of a dependency to modules that depend on the current module. It is useful when the public API exposes types from another module and callers need to read those types.

For example:

~~~java
module com.acme.orders.api {
    requires transitive com.acme.money;
    exports com.acme.orders.api;
}
~~~

If a public type in the `orders` API has a method returning `Money`, a module using the API may need to read `com.acme.money` to compile and use that signature.

Conversely, if `orders.api` only uses logging in its internal implementation, do not use `requires transitive` for logging. Use a normal `requires` in the module that actually needs that dependency.

Using `transitive` too broadly causes upper-layer modules to inadvertently read many modules they do not directly need. When the API changes, the blast radius is also wider.

Practical guidelines:

- Use `requires` when only the current module needs the dependency.
- Use `requires transitive` when the dependency is a necessary part of the public API that module consumers must read.
- Avoid turning utility modules or implementation details into dependencies propagated across multiple layers.
- Re-evaluate `transitive` whenever the API changes.

## 8. Avoid cyclic and reversed dependencies

JPMS requires a valid module graph and forbids cycles in `requires` relationships. If A requires B and B requires A, resolution will fail.

Example of an invalid relationship:

~~~text
com.acme.orders  ----requires----> com.acme.customers
      ^                                  |
      |                                  |
      +-------------requires-------------+
~~~

A cyclic dependency usually indicates that two modules were not split along appropriate boundaries or that a shared contract is in the wrong place.

One fix is extracting a stable API or service contract:

~~~text
com.acme.orders ----requires----> com.acme.customer.spi
com.acme.customers --requires--> com.acme.customer.spi
~~~

If `orders` needs to notify `customers`, a service interface or event contract can be declared in an independent API module. The implementing module registers the provider, and the consumer uses `ServiceLoader` or an appropriate orchestration mechanism.

Do not create a contract module solely to break a cycle if it bundles unrelated types. A contract should have clear semantics and belong to an identifiable capability or functional group.

## 9. Use `ServiceLoader` to reduce edges between consumers and providers

The consumer declares `uses` for the service API:

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

The provider declares:

~~~java
module com.acme.payment.stripe {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.stripe.StripeGateway;
}
~~~

The consumer does not need `requires com.acme.payment.stripe`. It only knows the `PaymentGateway` contract. At runtime, `ServiceLoader` can locate the provider in the appropriate module layer.

This model reduces direct dependencies between consumers and individual implementations, making it easier to swap providers or load plugins. However, the service API is still a real dependency; do not turn every internal call into a service just to reduce the edge count on a diagram.

A service boundary is appropriate when implementations can be replaced, plugin discovery is needed, or consumers must remain independent of providers. For simple internal calls between two parts always deployed together, a direct module dependency can be easier to understand.

## 10. Identifying modules with too many edges

When inspecting descriptors or graph diagrams, ask:

- How many other modules does this module `requires`?
- Is any dependency used in only a single class or internal package?
- Do many modules depend on a single overly broad `common` module?
- Is `requires transitive` declared without the API actually exposing types from that dependency?
- Does the module export packages that no other module needs?
- Are there reversed dependencies across layers or responsibilities?
- How many other modules are typically forced to change when this module changes?
- Does any module exist solely to forward calls or data types?

There is no fixed edge-count threshold for every project. An `app` module at the composition root may have many edges because its job is wiring components together. A core domain module with excessive outgoing dependencies deserves closer scrutiny.

Evaluate edges by meaning: is the dependency necessary, stable, properly directed, and expressed through a small API?

## 11. Observing the graph with JDK tools

Before changing the architecture, gather facts using the available tools.

**`jar --describe-module`**

Inspect a module descriptor:

~~~bash
jar --describe-module --file mods/com.acme.orders.jar
~~~

This command displays the module name, exported packages, `requires`, and service declarations. It helps spot modules exporting too broadly or declaring unnecessary dependencies.

**`jdeps --check`**

Check dependencies and module-related warnings:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

View an application's dependencies:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.app
~~~

The output helps identify modules the application needs directly or indirectly. Compare this with `module-info.java` to see which dependencies should be declared directly and which are already propagated via APIs.

**`jdeps --dot-output`**

Export dependency information as DOT files:

~~~bash
jdeps --module-path mods \
      --dot-output build/module-graph \
      --module com.acme.app
~~~

DOT files can be opened with Graphviz-compatible tools to inspect nodes and edges. When the graph is large, filter by module or functional group to focus on areas with many edges.

**`java --show-module-resolution`**

When launching the application, this option prints module resolution details:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

It helps clarify which modules are resolved and which relationships brought each module into the graph. This is runtime information that complements reading descriptors and `jdeps` results.

## 12. Graph refactoring workflow

When you discover an overly deep or dense graph, do not split or merge modules based solely on diagram shape. Proceed step by step:

1. Identify the problematic module and its direct dependencies.
2. Inspect exported packages and public APIs to see which dependencies actually appear in contracts.
3. Locate modules used solely to forward calls or data types.
4. Identify domain/capability boundaries and group code that changes together.
5. If there are cycles or reversed dependencies, identify a stable contract that can sit in the right place.
6. Remove unused `requires` and narrow `exports` when consumers no longer need them.
7. Add `requires transitive` only when public API signatures require it.
8. Update the build, test the module graph, and re-run the application.
9. Compare the before and after graphs to confirm edge counts dropped because unnecessary dependencies were removed, rather than because APIs were hidden or turned into implicit dependencies.

Refactoring should preserve stable application behavior. Small incremental changes help pinpoint the exact module descriptor, package access, or build configuration causing an issue.

## 13. Common design mistakes

| Symptom | Cause | Remedy |
|---|---|---|
| A `common` module has dozens of incoming dependencies from many domains | The shared module holds too many responsibilities | Split by capability and move contracts to the semantically owning modules |
| A small change forces edits across many modules | The public API is too broad or dependencies propagate across many layers | Narrow the API, reduce `requires transitive`, and stabilize contracts |
| A chain of modules merely forwards calls | Intermediate layers have no distinct responsibility | Merge pass-through parts or define actual layer responsibilities |
| Two modules fail to resolve due to cyclic `requires` | Wrong module boundaries or misplaced contracts | Extract a stable SPI/API or invert dependencies via an abstraction |
| Every module depends on a large utility module | The utility module has become a central hub | Split into small, semantically clear APIs |
| A provider module is referenced directly by consumers | The consumer knows concrete implementations | Consider a service contract and `ServiceLoader` if providers need to be replaceable |
| Too many small modules complicate the build | Decomposed by class/package instead of responsibility | Merge parts with high cohesion and shared change lifecycles |

## Key takeaways

A module graph describes the direction of `requires` between modules. An overly deep graph increases the number of layers to understand and lets changes ripple across many tiers; an overly dense graph increases coupling and blast radius. Organize modules around highly cohesive capabilities, keep APIs and `exports` small, use `requires transitive` at the right time, avoid cyclic dependencies, and use `ServiceLoader` when consumers need to be decoupled from providers. Tools like `jar --describe-module`, `jdeps`, and `java --show-module-resolution` help inspect the graph before refactoring.
