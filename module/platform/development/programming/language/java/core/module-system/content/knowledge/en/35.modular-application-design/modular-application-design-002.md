# API Modules and Implementation Modules

## Objectives

After this lesson, you will be able to:

- Explain why an API contract should be separated from its implementation in a modular application.
- Design an API module that exposes only the types consumers need to use.
- Design an implementation module that depends on the API and keeps implementation packages encapsulated.
- Use `uses` and `provides` with `ServiceLoader` to locate an implementation without depending on concrete classes.
- Understand the dependency direction between application, API, and implementation.
- Recognize when to split modules and when a single module is sufficient.

## 1. Why separate API and implementation?

A module typically contains two distinct groups of content:

- **API contract**: the types, methods, and behaviors that other modules are permitted to use.
- **Implementation**: the classes, algorithms, data structures, and internal details that fulfill that contract.

If a consumer depends directly on an implementation class, changes to the implementation can force changes in the consumer. When multiple modules share a concrete implementation, replacing or upgrading it becomes difficult.

Separating an API module and an implementation module establishes clearer boundaries:

- The API module owns the stable contract.
- The implementation module provides one way of fulfilling the contract.
- The application module depends on the API and uses the contract.
- The implementation can be replaced without forcing the application to import implementation classes.

The goal is not to create an extra module for every interface. Split only when there is a sufficiently clear boundary of responsibility and change lifecycle—for instance, a domain capability with multiple implementations, plugins, or multiple independent consumers.

## 2. Desired dependency direction

A common design has three modules:

~~~text
                 +--------------------+
                 |  com.acme.app      |
                 |  application       |
                 +---------+----------+
                           |
                           | requires API
                           v
                 +--------------------+
                 | com.acme.orders.api|
                 | public contract    |
                 +---------^----------+
                           |
                           | requires API
                 +---------+----------+
                 | com.acme.orders.impl
                 | implementation     |
                 +--------------------+
~~~

Both the application and the implementation know the API contract. The application does not need to know the concrete implementation class.

Dependency direction:

- Application → API
- Implementation → API
- The application does not need a direct compile-time dependency on the implementation when using service discovery.
- The API does not depend on the implementation.

Do not create cyclic dependencies such as API → implementation → API. If the contract needs a shared abstraction, that abstraction belongs in the API or in a smaller contract module.

## 3. Designing the API module

Suppose the system has an order creation capability. The API module exposes an interface:

~~~java
package com.acme.orders.api;

public interface OrderService {

    String createOrder(String customerId);
}
~~~

Module descriptor:

~~~java
module com.acme.orders.api {
    exports com.acme.orders.api;
}
~~~

`exports` exposes the package containing the contract so that other modules can use its public types.

The API should contain:

- Interfaces or abstract contracts that consumers need.
- DTOs, request/response types, and exceptions belonging to the public contract.
- Enums, annotations, or value types that need to be shared.
- Service interfaces used for dependency injection or `ServiceLoader`.

The API should avoid containing:

- Concrete implementations.
- Database configurations or specific network clients.
- Framework adapters that do not belong to the contract.
- Internal helpers and caches.
- Types that serve only a single implementation.

If the API needs DTOs, place them in an appropriately exported package. Consumers should only see the types needed to invoke the contract.

### 3.1. Keeping the contract stable

The API is the compatibility boundary between modules. Changing public methods, constructors, record components, or semantics can affect many consumers.

Some principles:

- Name methods after business concepts, avoiding leaks of persistence details.
- Do not return internal implementation types.
- Do not let the API depend on ORM entities or database-specific types if consumers do not need them.
- Clearly define nullability, exceptions, and data ownership.
- Version the API according to the system's compatibility rules.

For example, if the implementation uses JPA, the API does not necessarily have to return a JPA entity. It can return a DTO or a persistence-independent abstraction.

## 4. Designing the implementation module

The implementation module depends on the API:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;
}
~~~

The implementation provides a class that implements the interface:

~~~java
package com.acme.orders.impl;

import com.acme.orders.api.OrderService;

public final class DefaultOrderService implements OrderService {

    public DefaultOrderService() {
    }

    @Override
    public String createOrder(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }

        return "ORDER-CREATED-FOR-" + customerId;
    }
}
~~~

The implementation package does not need to be exported. The full descriptor adds a `provides` directive:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;

    provides com.acme.orders.api.OrderService
        with com.acme.orders.impl.DefaultOrderService;
}
~~~

Key point: `com.acme.orders.impl` has no `exports com.acme.orders.impl`. The provider class can be `public` to satisfy the provider constructor rule, while the package remains unexposed to normal Java code in other modules. `ServiceLoader` can locate the declared provider without consumers having to import the implementation class.

Do not use `opens` as a substitute for `exports` in this case. Reflection openness is a different contract; a service provider does not need to open its entire implementation package just to be discovered.

## 5. Application depends on API and uses ServiceLoader

The application module declares:

~~~java
module com.acme.app {
    requires com.acme.orders.api;

    uses com.acme.orders.api.OrderService;
}
~~~

`requires` creates a dependency on the API. `uses` declares that the application is a consumer of the `OrderService` service.

Code using the service:

~~~java
package com.acme.app;

import com.acme.orders.api.OrderService;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        OrderService service = ServiceLoader
                .load(OrderService.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException(
                                "No OrderService provider found"
                        )
                );

        String result = service.createOrder("customer-42");
        System.out.println(result);
    }
}
~~~

The application only imports `OrderService`. It does not import `DefaultOrderService` and does not need to know the implementation package.

The implementation module declares `provides`; the application module declares `uses`. These two directives describe the service contract at the module level.

### 5.1. Why not use `new DefaultOrderService()`?

If the application writes:

~~~java
OrderService service = new DefaultOrderService();
~~~

then the application must:

- Know the implementation class name.
- Have a compile-time dependency on the implementation module.
- Have access to the package containing the class.
- Change its code whenever the implementation changes.

This defeats the benefit of separating the contract. `ServiceLoader` provides a lookup point for implementations through the API instead of referencing concrete classes.

If the application only has a single fixed implementation and does not need replacement, plugins, or service discovery, direct constructor injection may be simpler. Module splitting and `ServiceLoader` should serve real architectural needs.

## 6. Complete source tree structure

Example of a three-module project:

~~~text
project/
└── src/
    ├── com.acme.orders.api/
    │   ├── module-info.java
    │   └── com/acme/orders/api/
    │       └── OrderService.java
    ├── com.acme.orders.impl/
    │   ├── module-info.java
    │   └── com/acme/orders/impl/
    │       └── DefaultOrderService.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/
            └── Main.java
~~~

The descriptors:

**API**

~~~java
module com.acme.orders.api {
    exports com.acme.orders.api;
}
~~~

**Implementation**

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;

    provides com.acme.orders.api.OrderService
        with com.acme.orders.impl.DefaultOrderService;
}
~~~

**Application**

~~~java
module com.acme.app {
    requires com.acme.orders.api;

    uses com.acme.orders.api.OrderService;
}
~~~

Compile the modules:

~~~bash
javac -d mods --module-source-path src -m com.acme.orders.api,com.acme.orders.impl,com.acme.app
~~~

The output looks like:

~~~text
mods/
├── com.acme.orders.api/
│   ├── module-info.class
│   └── com/acme/orders/api/OrderService.class
├── com.acme.orders.impl/
│   ├── module-info.class
│   └── com/acme/orders/impl/DefaultOrderService.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

The API package is exported. The implementation package is not exported, even though the provider is declared in the descriptor.

## 7. Resolving the implementation module and service binding

An important point when using `ServiceLoader` with named modules is that the provider module must be present in the module layer where the service is looked up.

When running the launcher, you can explicitly include the implementation module in the graph:

~~~bash
java --module-path mods --add-modules com.acme.orders.impl -m com.acme.app/com.acme.app.Main
~~~

`--add-modules` adds the provider module to the set of resolved modules. The application still depends only on the API in source code; the implementation name is configured at launch time.

In plugin applications or when creating module layers via the API, `Configuration.resolveAndBind` can be used to resolve dependencies and bind the service providers corresponding to services used by the resolved modules. This is suitable when a host dynamically constructs layers from a set of module finders.

If `ServiceLoader` cannot find a provider, check:

1. Does the API interface have the exact same class identity as the one the provider implements?
2. Has the consumer module declared `uses`?
3. Has the provider module properly declared `provides ... with ...`?
4. Is the provider module resolved into the layer?
5. Does the provider class meet `ServiceLoader`'s requirements?
6. Are you using the right layer when invoking `ServiceLoader`?

With named modules, `ServiceLoader.load(serviceType)` searches for providers in the layer appropriate for the service type's module. If the host creates new layers itself, you may need the overload that accepts a specific layer:

~~~java
ServiceLoader<OrderService> services =
        ServiceLoader.load(pluginLayer, OrderService.class);
~~~

This lets the host find providers in the plugin layer instead of defaulting to searching another context layer.

## 8. Multiple implementations for the same API

One benefit of API/implementation separation is supporting multiple implementations:

~~~text
com.acme.orders.api
       ^
       |
       +-------------------+
       |                   |
com.acme.orders.impl.sql   com.acme.orders.impl.memory
       |                   |
       +-------- provides -+
               OrderService
~~~

For example:

- An SQL implementation using a database.
- An in-memory implementation for testing or demos.
- A remote implementation calling an external service.

Each implementation module can declare:

~~~java
provides com.acme.orders.api.OrderService
    with com.acme.orders.impl.sql.SqlOrderService;
~~~

or:

~~~java
provides com.acme.orders.api.OrderService
    with com.acme.orders.impl.memory.MemoryOrderService;
~~~

If multiple providers are resolved together, `ServiceLoader` can return multiple implementations. Do not call `findFirst()` and assume provider ordering is a stable selection rule.

If only one implementation is allowed, ensure the module graph brings only one provider into the layer. If multiple providers are supported, define an explicit selection policy, such as:

- Providers having a priority declared in separate metadata.
- A qualifier or configuration key selecting the provider.
- The host selecting the corresponding module/layer.
- The API providing a factory or registry with a deterministic contract.

Do not rely on file order on the module path or an unguaranteed scan order.

## 9. Encapsulation of the implementation module

An implementation module should export as few packages as possible.

Example descriptor:

~~~java
module com.acme.orders.impl {
    requires com.acme.orders.api;

    provides com.acme.orders.api.OrderService
        with com.acme.orders.impl.DefaultOrderService;
}
~~~

No need for:

~~~java
exports com.acme.orders.impl;
~~~

When the package is not exported:

- The application cannot import implementation classes across normal module boundaries.
- The implementation can change classes or package structure without changing the public API.
- Internal helpers, repository adapters, and caches remain behind the module boundary.
- `ServiceLoader` can still use the provider declared via the service contract.

If a framework needs reflection into an internal package, add only a qualified `opens` for the exact package and framework module that genuinely needs permission. Do not open the entire implementation module just for one library.

## 10. Avoiding implementation leaks through the API

Creating two modules is not enough if the API still returns concrete implementation types.

Example of a poor contract:

~~~java
public interface OrderService {
    JpaOrderRepository getRepository();
}
~~~

The consumer becomes dependent on the persistence implementation. When switching from JPA to another storage mechanism, both the API and consumers may have to change.

A better contract exposes only the required capability:

~~~java
public interface OrderService {
    String createOrder(String customerId);
}
~~~

Other forms of leakage:

- The API returns implementation-specific exceptions.
- The API requires consumers to pass ORM entities.
- The API exposes internal configuration classes.
- The API depends on types that exist only in one implementation module.
- The API declares framework callbacks or annotations that are not an agreed-upon shared dependency.

Keeping the contract small ensures consumers do not need to know how the implementation works internally.

## 11. Dependencies, versioning, and compatibility

The API module typically has a more critical compatibility lifecycle than the implementation module because many consumers depend on it.

When changing the API:

- Adding an abstract method to an interface can break existing implementations.
- Removing or changing a public method's signature can break consumers.
- Renaming a module or package can break `requires` and service descriptors.
- Modifying DTOs/records can affect serialization and binary compatibility.
- Changing semantics can break behavior even if signatures remain unchanged.

When changing the implementation:

- Keep the service interface unchanged.
- Keep the module name or update provider configuration in a controlled manner.
- Preserve the contract's semantics and error behavior.
- Run contract tests against each implementation.
- Do not let the application depend on implementation packages.

If the API and implementation are published as separate artifacts, explicit version compatibility is required. For example, a new implementation version must be compatible with the API version range it declares or is tested against.

## 12. Testing along module boundaries

Multiple types of tests should be included:

### API contract tests

Verify the behavior and semantics that consumers are permitted to rely on. Contract tests should be independent of database or framework details of any particular implementation.

### Implementation tests

Verify that each implementation fulfills the contract properly. Dedicated test fixtures can be used for databases or in-memory storage.

### Service discovery integration tests

Run the application on the real module path and confirm that `ServiceLoader` finds the expected provider. Tests run solely on the classpath can miss descriptor errors, `uses`/`provides` issues, or module resolution problems.

### Encapsulation tests

Confirm that the application cannot import implementation packages when those packages are not exported. If needed, inspect the module descriptor or compile a small consumer test in a named module.

### Replacement tests

Swap the implementation module for another implementation without modifying the application source code. This provides practical proof that the consumer depends on the contract.

## 13. When is separating API and implementation unnecessary?

Not every module needs to be split into two artifacts/modules.

They can remain in a single module when:

- The module is small and has only one internal consumer.
- The implementation is unlikely to be replaced and plugins are not needed.
- The public API and implementation share the same change lifecycle.
- Splitting would only add dependencies, build configuration, and versioning overhead without creating a useful boundary.

Split modules when there is at least one clear reason:

- Multiple consumers need to share the contract.
- There are multiple implementations or plugins.
- The implementation needs to be replaced independently.
- You want to keep internal packages unexported.
- The API needs independent versioning and compatibility.
- There are distinct deployment or ownership boundaries.

Do not split just because every interface looks like it should live in an API module. Module boundaries should reflect actual contracts and ownership.

## 14. Design checklist

Before introducing API/implementation separation into a modular application, confirm:

- [ ] The API module contains only the necessary contract and public types.
- [ ] The API does not depend on the implementation.
- [ ] The implementation module depends on the API without creating cyclic dependencies.
- [ ] The application depends on the API instead of a concrete implementation when replaceability is needed.
- [ ] Implementation packages are not exported if consumers do not need direct access.
- [ ] If using `ServiceLoader`, the consumer has `uses` and the provider has `provides`.
- [ ] The provider module is actually resolved into the module layer.
- [ ] There is a clear policy if multiple providers coexist.
- [ ] The API does not leak ORM entities, repositories, or framework-specific types outside the contract.
- [ ] Contract tests and integration tests run on the module path.
- [ ] The module split provides clear ownership, versioning, or replaceability benefits.

## Conclusion

The API module defines the contract that consumers are allowed to use. The implementation module depends on that contract, provides its execution, and keeps implementation packages encapsulated. The application can depend on the API and discover implementations via `uses`, `provides`, and `ServiceLoader`.

Keep the dependency direction clear: **application → API; implementation → API**. When the application knows only the contract, implementations can be replaced or extended without forcing consumers to depend on concrete implementation classes.
