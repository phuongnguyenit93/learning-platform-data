# Do Not Optimize by Removing Necessary Boundaries

## Objectives

After this lesson, you will be able to evaluate the real cost of module boundaries in JPMS, distinguish startup cost from request-processing cost, explain why `exports`, `opens`, and explicit dependencies are rarely reasons to merge modules, choose an appropriate module granularity, and optimize packaging/runtime while preserving necessary encapsulation.

## 1. What Do Module Boundaries Protect?

A named module defines a unit of dependency and an access boundary. The module descriptor specifies which modules the module needs to read (`requires`), which packages are exposed externally (`exports`), which packages are opened for deep reflection (`opens`), and which services are used or provided (`uses`, `provides`).

Example:

~~~java
module com.acme.orders {
    requires com.acme.money;
    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

This design expresses three distinct decisions:

- The orders module depends on the money module.
- Consumers can use the public API in package `com.acme.orders.api`.
- The ORM is allowed to deep-reflect into the persistence package.

Other implementation packages remain internal to the module. Consumers cannot arbitrarily depend on every public class inside the module simply because it has the `public` modifier.

Boundaries help a module control the contract it provides. If you remove boundaries merely to be "faster," the application can lose the ability to change implementations, increase coupling between components, and make upgrades or testing harder.

## 2. Do Not Confuse a Module Boundary with a Network Call

A JPMS module is a unit of organization, dependency resolution, and access control within the same JVM. It is not a process boundary, a network boundary, or a mechanism that automatically routes method calls through a proxy layer.

A normal Java call:

~~~java
Order order = orderService.findById(orderId);
~~~

remains a method call within the same JVM. Once a consumer holds a reference to the object and the method is accessible, having the class reside in a separate module does not turn the call into an RPC or add a network hop.

It is important to distinguish:

- **Module resolution** occurs when the JVM starts or when the application creates a new module layer. This is graph and metadata resolution work.
- **Access/linkage checks** are applied when classes are linked and when the JVM needs to verify access rights to a type/member.
- **Method execution** is the actual business processing after the call is established.
- **Reflection/service loading** carries its own cost from dynamic discovery or access mechanisms; this cost does not apply to every method call between two modules.

Therefore, do not assume every method call across a module boundary carries significant overhead. JPMS does not insert a mandatory proxy or dispatcher on every call.

## 3. Where Should Real Costs Be Measured?

A modular application still incurs costs across multiple phases, so you must identify the right phase before optimizing.

| Area | Work That Can Occur | How to Evaluate |
| --- | --- | --- |
| Startup | Finding modules, reading descriptors, resolving the graph, creating layers, and loading initial classes | Measure time from process start to readiness |
| Class loading | Finding, reading, verifying, and defining classes | Use profiling or class-loading logs when appropriate |
| Reflection | Looking up constructors/fields/methods, checking access, and invoking | Measure actual reflection paths vs. direct APIs |
| Service loading | Discovering providers and instantiating implementations | Measure provider count, load timing, and initialization cost |
| Request handling | Business logic, I/O, allocations, locks, and algorithms | Profile hot paths with representative data |
| Deployment | Runtime image size, file count, startup environment | Measure artifact size, cold start, and install/run time |

Module resolution is typically a startup cost, not a repeated per-request cost. If the issue is request latency after the application has warmed up, profile request-handling code before modifying module descriptors.

If the issue is cold start, measure the entire process from process start until the application is ready to serve requests. Do not measure only the `main` call or the time to resolve one module and extrapolate total startup latency.

## 4. Keeping Boundaries Does Not Mean Creating Too Many Tiny Modules

Good encapsulation does not mean splitting every package into its own module. Module granularity should match units of change, ownership, dependencies, and deployment.

A module is usually reasonable when the packages inside it:

- Together serve a clear capability or business responsibility.
- Share a relatively uniform change and release lifecycle.
- Can manage dependencies as a unit.
- Need a stable public API for other consumers.
- Have implementation details that should stay hidden from consumers.

Do not split into dozens of modules just so each class has its own descriptor. Too many small modules can increase dependency management, build configuration, versioning, testing, and packaging overhead. It can also cause frequent internal changes to force descriptor updates across many modules.

For example, a billing module may contain API, domain logic, and persistence implementation:

~~~text
com.acme.billing/
  module-info.java
  com/acme/billing/api/
  com/acme/billing/domain/
  com/acme/billing/internal/
  com/acme/billing/persistence/
~~~

The descriptor exports only the packages consumers need:

~~~java
module com.acme.billing {
    requires com.acme.money;
    exports com.acme.billing.api;
}
~~~

When domain logic and persistence develop distinct ownership, release, or runtime isolation needs, consider splitting them into separate modules. Base decisions on architecture and operations, not on an assumption that more modules are always faster or fewer modules are always faster.

## 5. Do Not Widen Public Surface to Avoid Managing Dependencies

A common misguided "optimization" is exporting every package or opening an entire module so frameworks and consumers can access anything arbitrarily.

Example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.internal;
    exports com.acme.orders.persistence;
    opens com.acme.orders;
}
~~~

This configuration makes the public surface larger than necessary. Consumers may start depending on implementation classes, repositories, or persistence details. Frameworks may also deep-reflect into unnecessary packages.

A tighter design:

~~~java
module com.acme.orders {
    requires com.acme.money;

    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

If only one module needs SPI access, use a qualified export:

~~~java
exports com.acme.orders.spi to com.acme.integration;
~~~

If a framework needs deep reflection, open only the right package to the right target module. Do not use `ALL-UNNAMED` if the framework is running as a named module and its module name can be specified.

Keeping exports and opens minimal protects the ability to evolve implementations. It also makes dependency and reflection errors easier to trace because access permissions are declared explicitly.

## 6. Avoid Merging Modules Just to Remove One Dependency

Suppose `com.acme.orders` uses the `Money` type from `com.acme.money`. If that type appears in the public API, the dependency should be expressed clearly:

~~~java
module com.acme.orders {
    requires transitive com.acme.money;
    exports com.acme.orders.api;
}
~~~

If the money type is only used in internal implementation, a regular dependency suffices:

~~~java
module com.acme.orders {
    requires com.acme.money;
    exports com.acme.orders.api;
}
~~~

Choose `requires transitive` when consumers of orders need readability to the money module because money's types appear in the public API. Do not add transitive just to "make everything run."

Merging two modules merely to delete one `requires` line can leave a module owning too many responsibilities and blur API ownership. An explicit dependency is usually a far lower architectural cost than losing the boundary between two capabilities that can evolve independently.

Before merging, ask: do the two modules truly share the same ownership and lifecycle? Do they need independent releases or testing? Do consumers need a stable API between them? If the answers indicate the boundary is meaningful, keep the dependency and measure real costs if you suspect performance issues.

## 7. Optimizing Startup and Module Resolution Properly

If profiling shows startup is the bottleneck, consider solutions targeting the startup phase:

- Reduce heavy work in static initializers and constructors executed at startup.
- Defer initialization of components used only on certain paths.
- Avoid creating new module layers/plugin graphs repeatedly when unnecessary.
- Avoid broad classpath or module path scanning to discover components when the required module list is already known.
- Control the number of providers discovered if the application uses `ServiceLoader`.
- Use an appropriate runtime image to exclude unnecessary Java platform modules.

If the application creates dynamic plugin layers, measure the cost of resolving configurations, creating class loaders, and initializing plugins. Keep one layer per plugin only when isolation or lifecycle requires it; never create a new layer per request.

Do not delete `requires` or drop service declarations solely to make the graph look smaller if the code still needs the corresponding capabilities. The dependency graph must reflect the types and services the application actually uses.

## 8. Optimizing the Runtime Image While Preserving Module Boundaries

For a modular application, `jlink` can build a runtime image containing only the needed Java platform modules and selected dependencies. This is often helpful for deployment size, runtime control, and removing the requirement to install a full JDK.

Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --strip-debug   --no-header-files   --no-man-pages   --output runtime-image
~~~

On Windows, use the `;` path separator instead of `:` and the corresponding JDK path.

You can instruct the linker to bind service providers if the application needs bound providers:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --bind-services   --output runtime-image
~~~

Then use the runtime image with `jpackage`:

~~~bash
jpackage --type app-image   --name AcmeOrders   --dest dist   --runtime-image runtime-image   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Removing unused Java platform modules can reduce runtime image size. It does not require exporting every package or merging application modules. Test service loading, reflection, charsets, logging, TLS, native libraries, and less-common execution paths before releasing a trimmed image.

Do not conclude that a smaller runtime image automatically makes every request faster. Deployment size, runtime download time, memory footprint, and throughput are distinct metrics; measure them separately.

## 9. Reflection Is Not a Reason to Remove Encapsulation

Reflection may be necessary for frameworks, but you should not open every package to avoid configuration.

Example opening a persistence package to an ORM:

~~~java
module com.acme.orders {
    requires org.example.orm;

    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

If the framework sits on the class path, the JVM option might be:

~~~bash
--add-opens com.acme.orders/com.acme.orders.persistence=ALL-UNNAMED
~~~

Use `--add-opens` when needed to support runtimes or libraries that cannot yet declare qualified opens in module descriptors. Document the reason, target, and specific package so it can be reviewed when upgrading frameworks.

If reflection occurs on a hot path, measure member lookup, access check, and invocation costs separately. You can cache metadata or switch to direct APIs when the design permits. However, do not alter module boundaries before knowing which part of reflection is causing cost and can be safely replaced.

## 10. Measure Performance Instead of Inferring from Module Count

When comparing two designs, build a representative benchmark:

- Same workload, input data, and request volume.
- Same JDK version, JVM flags, and hardware.
- Appropriate warm-up before collecting metrics.
- Measure throughput, percentile latencies, allocations, and memory footprint.
- Measure cold start separately from steady state.
- Repeat enough times to recognize noise and environmental variance.

JMH is suited for JVM microbenchmarks when measuring a small operation such as a method call, lookup, or reflection. For startup and packaging, use end-to-end measurements on fresh processes rather than trying to extrapolate from microbenchmarks.

Do not benchmark a single method call and conclude an entire module architecture is fast or slow. Real-world performance is usually dominated by I/O, lock contention, allocations, algorithms, databases, or networking before module resolution becomes an issue.

When comparing the class path against the module path, keep workload and runtime equivalent. Measurements from one specific application do not prove one mechanism is always faster in every application.

## 11. Deploying with Controlled Boundaries

Before releasing, verify that artifacts still preserve the intended descriptors and behavior:

1. Inspect `module-info.class` of each modular JAR.
2. Use `jar --describe-module` to review `requires`, `exports`, `opens`, `uses`, and `provides`.
3. Run the application using the module path as in the expected production environment.
4. If using `jlink`, check the module list in the runtime image and test required services/providers.
5. If using `jpackage`, run the launcher from the app image or installed installer.
6. Verify framework reflection, JVM option configurations, resources, and native libraries.
7. Measure startup, memory, and key workloads on the final artifact.

You can inspect a descriptor:

~~~bash
jar --describe-module --file mods/com.acme.orders.jar
~~~

You can check dependencies:

~~~bash
jdeps --module-path mods --check com.acme.orders
~~~

These commands help verify metadata and dependencies. They do not replace running integration tests or measuring performance on the distributed artifact.

## 12. When Should Boundaries Be Changed?

Consider changing boundaries when:

- Two modules share the same ownership and lifecycle, and splitting them creates circular dependencies or unnecessary configuration.
- An exported package no longer has consumers and can be closed after confirming compatibility.
- A module is unintentionally exposing implementation types.
- Plugins require isolation and independent lifecycles, so clearer layer or module boundaries are needed.
- Public APIs should be separated from implementations to reduce coupling.

Do not change boundaries solely because:

- There is one extra `requires` line.
- The number of modules looks large.
- There is an unmeasured assumption that cross-module method calls are slow.
- A framework reports a reflection error and the suggested fix is opening the entire module.
- The runtime image is large, yet no analysis has been done on which modules are actually used.

A good boundary serves ownership, API stability, dependencies, and deployability. If a boundary no longer reflects the architecture, adjust it deliberately; if the boundary remains valuable, optimize the startup, runtime, reflection, or packaging parts that measurements show are costly.

## Takeaways

JPMS module boundaries primarily govern dependencies and access permissions within the same JVM; they do not turn every method call into a network call. Module resolution mainly affects startup, while reflection, service loading, and business processing have their own separate costs. Measure the right phase, choose module granularity based on ownership and lifecycle, keep exports/opens minimal, and optimize runtime images with `jlink` / `jpackage` where appropriate. Never remove necessary boundaries based solely on performance assumptions.
