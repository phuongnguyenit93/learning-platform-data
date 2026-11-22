# Reviewing Which Packages Truly Need to Be Exported

In the Java Platform Module System (JPMS), the `exports` directive exposes a module's packages to other modules. Every exported package becomes part of the API surface that the module provides. Therefore, export decisions directly affect the degree of coupling between modules, the ability to change implementations, and the compatibility scope that the library must maintain.

A module may contain many public packages, yet that does not mean all of them should be exported. A review should begin with the question: **do external modules truly need to use this package as part of the module's contract?**

## Objectives

After this lesson, you will be able to:

- Inventory packages of a named module and classify them by role.
- Identify which packages need to become public APIs.
- Distinguish API packages, implementation packages, and framework-only packages.
- Decide between not exporting, unqualified export, and qualified export.
- Recognize cases that require `opens` or a Service Provider instead of exporting a package.
- Review a module descriptor and assess the impact of narrowing the API.

## 1. What Does exports Expose?

The `exports` directive is declared in `module-info.java`:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

This declaration exposes package `com.acme.orders.api` to modules that read `com.acme.orders`.

A module using the API still needs to declare the dependency:

~~~java
module com.acme.application {
    requires com.acme.orders;
}
~~~

Two conditions work together:

- `requires` specifies that the consuming module reads the providing module.
- `exports` specifies which packages of the providing module are exposed to other modules.

Exporting a package does not make every type or member public. Java access rules still apply. A top-level class needs an appropriate access level; constructors, methods, and fields remain governed by `public`, `protected`, package-private, and `private`.

### 1.1. Exporting by Package, Not by Class

JPMS exports entire packages. There is no syntax like:

~~~java
exports com.acme.orders.api.OrderService;
~~~

Instead, the module exposes a package:

~~~java
exports com.acme.orders.api;
~~~

Subpackages are separate packages. For example:

- `com.acme.orders.api`
- `com.acme.orders.api.dto`
- `com.acme.orders.internal`

Exporting package `com.acme.orders.api` does not automatically export `com.acme.orders.api.dto` or `com.acme.orders.internal`. If you want to expose a subpackage, you must declare it separately.

Therefore, how packages are organized directly affects the breadth of the module's API. Placing internal classes in the same package as the API can force that package to be exported just so certain classes can be accessed. Separating API and implementation into distinct packages usually yields better boundary control.

## 2. Start with a Package Inventory

Before editing the module descriptor, list the actual packages in the module. For each package, record:

- Package name.
- Important classes, interfaces, enums, and annotations.
- Which modules are importing or using types in the package.
- Whether the package appears in public API signatures of other modules.
- Which frameworks or tools need to access the package at runtime.
- Whether the package contains stable API or implementation details subject to change.

You can use the following table structure as a review sheet:

| Package | Consumers | Role | Initial Decision |
|---|---|---|---|
| `com.acme.orders.api` | App, integration | Public API | Export |
| `com.acme.orders.dto` | App, integration | Exchange data types | Export if part of the API contract |
| `com.acme.orders.internal` | Orders module only | Implementation | Do not export |
| `com.acme.orders.persistence` | ORM via reflection | Internal persistence | Consider opens |
| `com.acme.orders.bootstrap` | Internal initialization code only | Implementation | Do not export |

The table above is only a classification example. The final decision must be based on the actual structure and usage of the module under review.

## 3. Criteria for Deciding Whether a Package Needs Exporting

### 3.1. Packages Containing APIs That Other Modules Call Directly

This is the clearest candidate for exporting.

For example, package `com.acme.payment.api` provides a service that external applications need to call:

~~~java
package com.acme.payment.api;

public interface PaymentService {
    PaymentResult pay(PaymentRequest request);
}
~~~

If other modules need to import `PaymentService`, `PaymentResult`, and `PaymentRequest`, the package containing those types must be exported to the consuming modules.

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
}
~~~

A public API should have a clear purpose, stable data types, and a contract that the providing module is prepared to maintain.

### 3.2. Packages Containing Only Internal Implementation

Packages containing helpers, adapters, repository implementations, internal algorithms, or wiring classes usually do not need to be exported if other modules do not access them directly.

Example:

~~~text
com.acme.payment
├── api
│   ├── PaymentService.java
│   └── PaymentResult.java
├── internal
│   ├── DefaultPaymentService.java
│   └── PaymentValidator.java
└── persistence
    └── JpaPaymentRepository.java
~~~

The module descriptor can expose only the API:

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
}
~~~

Classes in the `internal` and `persistence` packages are still used inside the module. Other modules cannot access them through normal Java APIs if the packages are not exported.

Keeping implementations in unexported packages lets the module change classes, structures, and internal algorithms with minimal impact on clients.

### 3.3. Packages with Public Types but No External Clients

The `public` keyword on a class does not automatically mean the package needs to be exported.

Example:

~~~java
package com.acme.payment.internal;

public class PaymentRetryPolicy {
    public boolean shouldRetry(int attempt) {
        return attempt < 3;
    }
}
~~~

If only other classes within the payment module use `PaymentRetryPolicy`, there is no reason to export package `com.acme.payment.internal`.

The decision to export is based on module boundaries and the contract to be published, not solely on whether a class is declared public.

### 3.4. Packages Accessed Only by Frameworks via Reflection

Some frameworks need to read annotations, instantiate objects, access fields, or invoke constructors via reflection. In this case, determine whether the framework needs public API access or deep reflection.

- If the framework uses public APIs normally, the package may need to be exported.
- If the framework needs deep reflection into non-public members, the package may need to be opened with `opens`.
- If the framework only needs one package for a specific framework module, prefer restricting the granted target.

Example:

~~~java
module com.acme.payment {
    exports com.acme.payment.api;
    opens com.acme.payment.persistence to com.acme.orm;
}
~~~

The API package is exported for normal usage. The persistence package is opened to the ORM module to perform reflection at runtime.

Do not export all internal packages just because a framework needs deep access to a few members.

### 3.5. Service Provider Implementation Packages

With the `ServiceLoader` mechanism, a providing module can declare a provider in its module descriptor:

~~~java
module com.acme.payment.provider {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentService
        with com.acme.payment.provider.internal.DefaultPaymentService;
}
~~~

The consuming module declares:

~~~java
module com.acme.application {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentService;
}
~~~

The package containing the service interface must be exposed to clients. The provider implementation package usually does not need to be exported just for `ServiceLoader` to locate and instantiate the provider declared via `provides ... with ...`.

This is an example showing that a package can be used indirectly through module mechanisms without needing to become a public API package.

## 4. Three Options During Review

After determining a package's purpose, choose one of the following paths.

### 4.1. Do Not Export

Use when the package only serves internal implementation and does not need to be accessed directly by other modules.

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Package `com.acme.orders.internal` does not appear in the descriptor and therefore remains internal to the module.

### 4.2. Unqualified Export

Use when the package is an API that modules reading the current module can use:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Every module reading `com.acme.orders` is permitted to access eligible public APIs in the exported package.

This is a broader API commitment than a qualified export. Consider stability and client needs before exposing it.

### 4.3. Qualified Export

Use when the package needs to be exposed only to specific named modules:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.plugin;
}
~~~

In this example:

- Package `com.acme.orders.api` is exposed to every module reading `com.acme.orders`.
- Package `com.acme.orders.spi` is exposed only to module `com.acme.plugin` via this declaration.

The target module still needs to read the providing module, for example:

~~~java
module com.acme.plugin {
    requires com.acme.orders;
}
~~~

Qualified exports are useful for SPIs, internal integration among a few modules, or APIs intended only for controlled components. They do not replace `requires` and do not open packages for deep reflection.

## 5. Step-by-Step Package Review Process

You can apply the following process to a module that currently has many packages or was broadly exported previously.

### Step 1: List all packages

List packages containing source code in the module. Group them by role:

- Public API.
- DTOs/models exchanged between modules.
- SPIs or extension points.
- Implementations.
- Persistence and adapters.
- Bootstrap, configuration, and helpers.
- Packages serving frameworks or reflection.

Do not assume a package named `api` is definitely a stable API; inspect its actual contents and clients.

### Step 2: Find consuming modules

Search for other modules that have:

- `requires` on the module under review.
- Import statements for types belonging to the package under consideration.
- Public signatures using types belonging to that package.
- ServiceLoader or framework configurations requiring that package.

A package used only internally within the same module usually does not need to be exported.

### Step 3: Identify the type of access

For each client, determine how the package is used:

- Importing and calling public APIs.
- Extending or implementing public interfaces.
- Passing types via parameters, return types, or generics.
- Being located via `ServiceLoader`.
- Being accessed by frameworks via reflection.
- Being called only from internal module code.

Each usage pattern can lead to a different decision. For example, public APIs usually need exports; deep reflection usually needs opens; providers declared in the descriptor usually do not need the implementation package exported.

### Step 4: Choose the exposure scope

For packages that need exporting, ask further:

- Do all modules reading this module need access?
- Does only one module or a group of integration modules need access?
- Does the package contain internal classes unrelated to clients?
- Can the API be separated into its own package to reduce the public surface?

Choose unqualified export, qualified export, or splitting packages based on actual needs.

### Step 5: Update module-info.java

Example before review:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.internal;
    exports com.acme.orders.persistence;
    exports com.acme.orders.bootstrap;
}
~~~

After checking clients, suppose only the API needs to be exposed, while persistence needs reflection from the ORM:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.persistence to com.acme.orm;
}
~~~

The `internal` and `bootstrap` packages are no longer exported. The persistence package is opened specifically for the ORM once the deep reflection requirement has been confirmed.

This is only an illustrative example. Do not remove exports currently used by clients before identifying and handling the impact of the change.

### Step 6: Verify clients and runtime

After editing the descriptor:

1. Compile the providing module.
2. Compile each client module using the API.
3. Run the relevant integration flows.
4. Test frameworks that require reflection.
5. Test ServiceLoader if the module has providers.
6. Look for access errors on packages or types no longer exposed.

If a client fails because a package is not exported, determine whether that client is using a supported API or depending on an implementation. Review results must reflect the module's actual contract.

## 6. Tools to Support Inventory and Analysis

### 6.1. Finding packages in source code

You can use search tools in your IDE or command line to list package declarations and import locations. For example, with ripgrep:

~~~bash
rg "^package " src
rg "^import com\.acme\.orders" ../
~~~

Adjust search directories according to the repository structure. Search results help locate references in source code, but do not automatically detect every case of reflection, framework configuration, or separately compiled clients.

### 6.2. Using jdeps

The `jdeps` tool in the JDK helps analyze dependencies at the package and module levels.

List module dependencies:

~~~bash
jdeps --module-path libs --list-deps app.jar
~~~

Restrict analysis to APIs:

~~~bash
jdeps --api-only --module-path libs app.jar
~~~

Check the module descriptor and dependencies:

~~~bash
jdeps --module-path libs --check com.acme.orders
~~~

`jdeps` results assist in identifying dependencies and types appearing in APIs. They do not replace reviewing business requirements, reflection, runtime configuration, or integration contracts. Combine static analysis with actual client testing.

### 6.3. Inspecting descriptors and the module graph

You can inspect the module descriptor of a JAR:

~~~bash
jar --describe-module --file libs/orders.jar
~~~

When running an application, you can view module resolution:

~~~bash
java --show-module-resolution --module-path out -m com.acme.app/com.acme.app.Main
~~~

These commands help verify module names, requires, and which modules are resolved in the runtime configuration.

## 7. Exercise Caution When Narrowing Exports

Removing an export line can prevent existing client source code from compiling. If a client imports a class belonging to that package, errors can appear immediately at compile time.

A previously exported package may also have become an unofficial dependency in the system. Before narrowing:

- Identify all known consuming modules.
- Check source code and integration configurations outside the repository, if any.
- Determine whether the package is a supported public contract.
- If necessary, move APIs that need to be preserved into a separate public package.
- Update clients before or alongside the change.
- Re-run compilation and integration tests.

Do not remove an export merely because a package is named `internal` or does not show up in a single search. Verify valid usages and the scope of clients the system must support.

Conversely, overly broad exports also carry risk: clients may begin depending on internal classes, making it difficult for the module to change implementations and maintain compatibility.

## 8. Checklist for Each Package

Use this checklist when recording decisions:

- [ ] The package has been properly identified in the module.
- [ ] Client modules and how they use the package have been identified.
- [ ] Public APIs have been distinguished from internal implementation.
- [ ] Checked whether the package appears in API signatures of other modules.
- [ ] Reflection and ServiceLoader requirements have been verified.
- [ ] Chosen between not exporting, unqualified export, qualified export, or opens.
- [ ] If narrowing exports, impact on clients has been assessed.
- [ ] Related modules have been compiled and run.
- [ ] The module descriptor accurately reflects the contract to be published.

A final decision table can be saved alongside design documentation:

| Package | Clients Needing Access | Decision | Reason |
|---|---|---|---|
| `com.acme.orders.api` | App, integration | Export | Public API |
| `com.acme.orders.spi` | Specific plugin module | Qualified export | Extension contract |
| `com.acme.orders.internal` | No external clients | Do not export | Implementation |
| `com.acme.orders.persistence` | ORM via deep reflection | Opens to ORM | Runtime access |
| `com.acme.orders.provider.internal` | ServiceLoader | Do not export | Provider declared via provides |

## 9. Self-Check

**Scenario 1:** Module A declares `requires B;`. Which module is the dependent module?

**Answer:** A is the dependent module; B is the required module. The direct readability relationship goes from A to B.

**Scenario 2:** A requires B, and B requires C via `requires C;`. Does A automatically read C?

**Answer:** No. Normal `requires` does not propagate readability to indirect dependencies. A needs to declare a direct dependency on C, or B must use `requires transitive C;`.

**Scenario 3:** Why is a module present on the module path yet still unused by the app?

**Answer:** The module path only provides the location for Java to find modules. The app must still declare an appropriate `requires` relationship; the used package must also be exported, and the type must satisfy access rules.

**Scenario 4:** A module uses a dependency only at compile time. Which modifier can be chosen?

**Answer:** `requires static` can be used if the dependency is optional at runtime and runtime code does not depend on that class's presence.

**Scenario 5:** When should `requires transitive` be used?

**Answer:** When a module wants modules reading it to also read the dependency, typically because types from the dependency appear in the public API that clients need to use.

**Scenario 6:** A package is not exported, yet is declared in `provides ... with ...`. Is it mandatory to export the provider package?

**Answer:** No. The provider is declared in the module descriptor so ServiceLoader can find it; the provider implementation package can usually remain internal. The package containing the service interface still needs to be exposed to consuming modules.

When reviewing a `requires` line, identify the declaring module, the required module, the dependency edge direction, modifiers, and how the dependency is used in the API. Then check the module path, package exports, and clients to ensure the module graph accurately reflects the intended architecture.