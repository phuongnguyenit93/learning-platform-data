# Defining Module Boundaries by Capability

When designing a modular application, an important question is how to divide the system into modules. Organizing by technical layers such as controller, service, and repository often leads to broad cross-dependencies between modules and makes changes difficult. A more suitable approach is to define module boundaries by **business capability**: each module is responsible for a meaningful business capability, owns the rules and data for that capability, and exposes a clear API to the rest of the system.

A capability is something the system needs to do for a user or organization, such as managing customers, processing payments, managing orders, issuing invoices, or sending notifications. Placing module boundaries around capabilities groups decisions that tend to change together into a single unit and restricts the details that other modules are allowed to know.

## 1. What is a capability-based module boundary?

A module boundary defines:

- Which classes, packages, and resources belong to the module.
- Which APIs the module exposes for other modules to use.
- Which dependencies the module is allowed to declare.
- Which data and business rules the module manages on its own.
- Which interactions must go through a contract rather than accessing an implementation directly.

For example, an e-commerce system can be divided into:

~~~text
com.example.shop
|-- customer
|   |-- api
|   |-- internal
|-- catalog
|   |-- api
|   |-- internal
|-- order
|   |-- api
|   |-- internal
|-- payment
|   |-- api
|   |-- internal
|-- shipping
|   |-- api
|   |-- internal
|-- notification
    |-- api
    |-- internal
~~~

Each capability owns its own rules and models. Order manages the order lifecycle; Payment manages authorization, capture, and refund; Shipping manages creating and tracking shipments.

A module does not need to know how another module stores its data. Order can ask Payment to process a payment through an API, without directly accessing `PaymentRepository` or Payment's internal database tables.

## 2. Start from business capabilities, not framework layers

A technical-layer split typically has the following structure:

~~~text
application
|-- controllers
|-- services
|-- repositories
|-- entities
|-- clients
~~~

This approach groups classes by technology type. A change in the Order capability may force edits across many different packages or modules. Conversely, a single capability typically spans multiple layers: API, application logic, persistence, integration, and domain model.

Splitting by capability:

~~~text
application
|-- order
|   |-- api
|   |-- domain
|   |-- application
|   |-- persistence
|-- payment
|   |-- api
|   |-- domain
|   |-- application
|   |-- integration
|-- shipping
    |-- api
    |-- domain
    |-- application
    |-- integration
~~~

Technical layers can still exist inside a module. The difference is that they remain within the capability's scope of ownership, rather than becoming shared modules that every capability depends on.

Start by asking: "Which business capabilities can be described, developed, and changed relatively independently?" Only then decide on packages, `module-info.java`, and build structure.

## 3. Identifying capabilities and responsibility boundaries

The following sources can be used to identify capabilities:

1. **Business language:** nouns, verbs, and rules used by domain experts.
2. **Business processes:** steps with distinct inputs, outputs, and states.
3. **Data ownership:** the team or unit responsible for data correctness.
4. **Reasons for change:** rules that tend to change together.
5. **External actors and systems:** interactions that have their own contracts, such as a payment gateway, tax service, or shipping provider.

For example, "placing an order" may involve validating the cart, checking prices, reserving inventory, processing payment, and creating a shipment. Not all of these steps necessarily belong to a single Order module. Identify the capability that owns each rule:

| Rule or data | Capability that may own it |
|---|---|
| Order status, order total | Order |
| Selling price, product description | Catalog |
| Stock quantity and reservations | Inventory |
| Authorization, capture, refund | Payment |
| Shipping address, shipment status | Shipping |

A single use case may orchestrate multiple capabilities. The orchestrating module should not take ownership of all the data and rules of the modules it calls.

## 4. Using cohesion and coupling to validate boundaries

A well-defined boundary has high cohesion and controlled coupling.

**High cohesion** means the classes inside a module serve the same capability and change for related business reasons. The Payment module can contain payment policies, payment transactions, gateway adapters, and the payment API if they all serve the payment capability.

**Low coupling** means other modules depend only on the required contract. If Order has to know table names, persistence entities, implementation classes, and internal configuration of Payment, the boundary is leaking.

Signs of a poor boundary:

- Multiple modules must import each other's internal packages.
- Changing a rule in one capability forces edits in multiple modules that do not own that rule.
- Module A and B have a cyclic dependency.
- A module contains only a few classes with no clear business responsibility.
- A shared module becomes a dumping ground for all models and utilities.
- Multiple capabilities write directly to data owned by another capability.

There is no optimal number of classes or packages for every module. Size is not the sole criterion. A small module is still justified if it has an independent contract and reason to change; a large module can be justified if its parts belong to the same capability and do not create unmanageable coupling.

## 5. Designing the module's public API

The module descriptor is where part of the boundary is expressed using the mechanisms of the Java Module System. Export only the packages that contain required contracts.

For example:

~~~java
module com.example.payment {
    exports com.example.payment.api;

    requires java.logging;
}
~~~

Package structure:

~~~text
com.example.payment
|-- api
|   |-- PaymentService.java
|   |-- PaymentRequest.java
|   |-- PaymentResult.java
|-- internal
    |-- DefaultPaymentService.java
    |-- PaymentRepository.java
    |-- GatewayClient.java
~~~

The Order module can declare:

~~~java
module com.example.order {
    requires com.example.payment;
}
~~~

And use the contract:

~~~java
package com.example.payment.api;

public interface PaymentService {
    PaymentResult authorize(PaymentRequest request);
}
~~~

The implementation in the `internal` package is not exported. Other modules cannot directly access public types in non-exported packages under the normal access rules of named modules.

Do not export an entire package just to fix a compilation error. Every export is part of a contract that the module must consider maintaining. When a package needs to be opened for reflection, distinguish `opens` from `exports` and only open the specific package to the framework or module that requires it.

## 6. Owning models and data by capability

A boundary not only restricts class access, it also defines who owns the data and the rules governing that data.

For example, Order needs payment information but should not depend on a Payment entity mapped directly from the database. Payment should return a contract tailored to Order's needs:

~~~java
public record PaymentResult(
        String transactionId,
        PaymentStatus status
) {
}
~~~

Order keeps its own order data and stores a reference to the transaction ID or required result. Payment continues to own gateway details, tokens, reconciliation status, and retry rules.

Avoid creating a `common` module containing all shared entities. A shared model can force multiple capabilities to change at the same time and blur ownership. Share a data type only when it is genuinely a stable contract that makes sense at the boundary between capabilities.

If two capabilities need the same concept but with different semantics, consider defining separate models at each boundary and translating via an adapter. For example, Customer in Order may simply be a snapshot of the name and address at the time the order was placed; Customer in Customer Management may contain the full profile and current status. Both models refer to a customer, yet they serve two different sets of rules.

## 7. Using service interfaces to reduce implementation dependency

A module can expose an API directly through an exported interface. When replaceable implementations or plugins are needed, Java `ServiceLoader` is an option.

The module defining the service contract:

~~~java
module com.example.tax.api {
    exports com.example.tax.api;
}
~~~

~~~java
package com.example.tax.api;

public interface TaxCalculator {
    TaxResult calculate(TaxRequest request);
}
~~~

The consumer module declares `uses`:

~~~java
module com.example.invoice {
    requires com.example.tax.api;
    uses com.example.tax.api.TaxCalculator;
}
~~~

The provider module declares `provides`:

~~~java
module com.example.tax.provider {
    requires com.example.tax.api;

    provides com.example.tax.api.TaxCalculator
        with com.example.tax.provider.DefaultTaxCalculator;
}
~~~

The consumer locates the implementation:

~~~java
TaxCalculator calculator = ServiceLoader
        .load(TaxCalculator.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No tax provider available"));
~~~

The service contract should belong to a stable API module. The provider module depends on the API; the consumer also depends on the API. The consumer does not need to depend on the provider's implementation package.

`ServiceLoader` is suitable when selecting a provider at runtime or extending the system with plugins. If there is only a single fixed dependency and discovery is not needed, an interface injected via a constructor can be simpler.

## 8. Managing dependencies between capabilities

Draw the dependency graph before finalizing module descriptors. For example:

~~~text
                  application
                 /     |      \
                v      v       v
              order  catalog  customer
                |
                v
              payment
                |
                v
           payment-api

shipping  <--- order-api or event contract
~~~

The actual diagram should reflect the direction of contract dependencies. A module should depend on the API it needs, not back on the implementation of the module providing that API.

Useful principles:

- Dependencies point toward stable contracts.
- Avoid cyclic dependencies between capabilities.
- Do not create a `common` module as the hub for every module.
- Use adapters to isolate external libraries or systems.
- Use events or service contracts when coupling between capabilities needs to be reduced.
- Use `requires transitive` only when consumer modules genuinely need propagated readability through the public API.

If module A needs public types from module B, A can declare `requires B`. If B is only an implementation dependency, `requires transitive` should not be used automatically. The `transitive` modifier propagates the dependency to modules that read A, so use it only when A's public contract actually exposes types belonging to B.

## 9. Split modules by capability, but do not over-split

Signs that modules should be merged:

- Two modules are always deployed and changed together.
- A module has no independent contract.
- Classes continuously call back and forth and cyclic dependencies are hard to eliminate.
- Boundaries reflect only technical packages rather than business ownership.

Signs that a module should be split:

- A part has its own business rules and cadence of change.
- A part needs to be used by multiple capabilities through a stable API.
- A part can be replaced or extended independently.
- A part requires explicit access restrictions or dependencies.
- Changing one part currently forces unrelated capabilities to know about its implementation.

Do not split a module simply because a package has accumulated many classes. Conversely, do not keep everything in one module just because the application is currently built as a single artifact. Boundaries are decisions about ownership and dependencies; the number of JAR files can be decided separately according to how deployment is structured.

## 10. Verifying boundaries with the Java Module System

The module system helps turn boundaries into rules enforced by the compiler and runtime.

### Checking exports

Ensure the module exports only API packages:

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

Internal packages are not exported. Another module attempting to import a type in an internal package will encounter an access error when compiled on the module path.

### Checking the dependency graph

Use `jdeps` to inspect dependencies:

~~~bash
jdeps --module-path mods --module com.example.order
~~~

Use the Java launcher to validate module configuration:

~~~bash
java --module-path mods --validate-modules
~~~

You can view how modules are resolved at runtime:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

These tools help detect unwanted dependencies, missing modules, and certain configuration conflicts. They do not replace business tests or data ownership checks.

### Testing the API contract

Write tests against the module's public API rather than testing the implementation via reflection into internal packages. Consumer tests should compile as a separate module on the module path to confirm the contract is genuinely usable from the outside.

If a test needs access to an internal package, consider whether it is an internal unit test of the module or whether it is testing an implementation detail that should not become part of the contract.

## 11. Example design workflow from a use case

Suppose the "place order" use case consists of:

1. The customer submits an order creation request.
2. Order validates the order details and total.
3. Inventory reserves stock.
4. Payment authorizes the payment.
5. Order transitions its state to confirmed.
6. Shipping receives a request to create a shipment.

Responsibilities can be assigned as follows:

| Capability | Owned responsibility | Contract provided |
|---|---|---|
| Customer | Customer profile and status | `CustomerLookup` |
| Catalog | Products, pricing, and sales info | `ProductQuery` |
| Inventory | Stock levels and reservations | `InventoryReservation` |
| Order | Orders and lifecycle status | `OrderService` |
| Payment | Transactions, authorization, refund | `PaymentService` |
| Shipping | Shipments and tracking | `ShippingService` |

Order orchestrates the use case but does not directly update Inventory or Payment tables. Each capability modifies its internal state through its own API.

In a single-process modular system, modules can communicate via Java interfaces and direct method calls. If a capability is later deployed as a separate service, the contract can be moved over HTTP, messaging, or RPC. Clear boundaries make changing the communication mechanism easier, though a module boundary does not automatically turn a module into a microservice.

## 12. Checklist for defining module boundaries

Before creating or splitting a module, answer these questions:

- Which business outcome is this capability responsible for?
- Which rules and data belong to its ownership?
- Which classes change together for the same reason?
- Exactly which APIs do other modules need to know?
- Are any internal packages being exported unnecessarily?
- Are there any cyclic dependencies or dependencies on another module's implementation?
- Is any shared model blurring ownership?
- Can the contract be tested independently?
- Is `ServiceLoader` needed, or is direct dependency injection sufficient?
- Can the internal implementation be changed without forcing consumers to modify code?

If you cannot yet answer the questions about ownership and contracts, do not decide on modules based solely on package names or frameworks.

## 13. Key takeaways

Defining module boundaries by capability means organizing modules around business capabilities and their ownership. A module keeps its domain rules, data, and implementation private, exporting only the contracts that other capabilities genuinely need. Other modules interact through APIs or service contracts rather than accessing repositories, entities, and internal packages.

Use cohesion, coupling, dependency graphs, and module descriptors to validate boundaries. Splitting by capability helps the system change independently and maintain clear boundaries, though it does not mean every capability must become a microservice or a separate JAR. The goal is clear ownership, small contracts, and directed dependencies.

## References

- Java Language Specification — Modules: https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html
- Java Platform Module System — Module API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html
- Oracle JDK — jdeps: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
- Oracle JDK — Java Launcher: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
