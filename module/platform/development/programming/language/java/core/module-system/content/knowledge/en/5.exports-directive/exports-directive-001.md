# Exporting Packages for Other Modules to Compile and Access

## 1. The Role of exports in JPMS

In the Java Platform Module System (JPMS), each named module can declare which packages other modules are allowed to use. The `exports` directive in `module-info.java` performs that exposure.

Example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

This declaration exposes the package `com.acme.orders.api` as part of the API of module `com.acme.orders`. Other packages in the module remain internal if they do not have a corresponding export directive.

For a consuming module to use an exported package, two conditions must be met:

1. The consuming module must **read** the module that provides the package, typically via `requires`.
2. The providing module must **export** the package that the consuming module wants to access.

You can remember the division of responsibilities as follows:

- `requires` specifies which modules the current module needs to read.
- `exports` specifies which packages other modules are allowed to access.

The two declarations complement each other. Having `requires` alone does not automatically open every package of the required module; having `exports` alone does not automatically create a readability relationship from a consuming module either.

## 2. Basic Syntax

Syntax to export a package to every module that reads the current module:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

The package name in `exports` is the fully qualified name and is case-sensitive. The directive is placed inside the module declaration of the `module-info.java` file, usually at the root directory of the module's source.

A module can export multiple packages:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.dto;
    exports com.acme.orders.spi;
}
~~~

Each package is exposed independently. If you want to expose a subpackage, you must declare that package separately.

For example, the declaration:

~~~java
exports com.acme.orders.api;
~~~

does not automatically expose:

~~~text
com.acme.orders.api.internal
com.acme.orders.api.model
~~~

Packages in Java do not have a recursive export mechanism down the directory tree.

## 3. Example of Two Modules Using an API

Suppose there are two modules:

~~~text
orders/
├── module-info.java
└── com/acme/orders/
    ├── api/
    │   └── OrderService.java
    └── internal/
        └── OrderRepository.java

checkout/
├── module-info.java
└── com/acme/checkout/
    └── CheckoutService.java
~~~

The `orders` module exposes its API package:

~~~java
// orders/module-info.java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

A public type resides in the exported package:

~~~java
// orders/com/acme/orders/api/OrderService.java
package com.acme.orders.api;

public class OrderService {
    public String findOrder(long id) {
        return "Order " + id;
    }
}
~~~

The `checkout` module declares its dependency:

~~~java
// checkout/module-info.java
module com.acme.checkout {
    requires com.acme.orders;
}
~~~

Then, code in the `checkout` module can import and call the API:

~~~java
package com.acme.checkout;

import com.acme.orders.api.OrderService;

public class CheckoutService {
    public void checkout() {
        OrderService orders = new OrderService();
        System.out.println(orders.findOrder(1001));
    }
}
~~~

At compile time, the compiler checks whether module `checkout` reads `com.acme.orders` and whether package `com.acme.orders.api` is exported by that module. At runtime, the JVM continues to enforce the corresponding module boundaries.

If `exports com.acme.orders.api;` is removed, module `checkout` cannot use this package through normal Java access, even though it has written `requires com.acme.orders;`.

If `requires com.acme.orders;` is removed, module `checkout` lacks the readability relationship needed to use the `orders` module's API.

## 4. How Far Does exports Allow Access?

`exports` exposes a package for normal Java access. Exposing a package does not make every member in the package public.

Java access rules still apply:

- Public types in an exported package can be used by reading modules.
- Public members are accessed according to normal Java rules.
- Protected members remain subject to protected access rules, including inheritance and package rules.
- Package-private types or members do not become public just because the package is exported.
- Private members remain accessible only according to Java's private access rules.

Example:

~~~java
package com.acme.orders.api;

public class Order {
    public String id;

    String internalCode;

    private String secret;
}
~~~

Other modules can access the public type `Order` and the public field `id`. The field `internalCode` has package-private access, and `secret` is private; `exports` does not change those access levels.

Therefore, an exported package should be treated as part of the API visible from outside the module. The development team should carefully consider which public types belong in this package and keep implementation details in internal packages.

## 5. Qualified Exports: Exposing Only to Specific Modules

JPMS allows exporting a package conditionally, intended only for specified modules. This approach is called **qualified exports**.

Syntax:

~~~java
module com.acme.orders {
    exports com.acme.orders.spi to
        com.acme.checkout,
        com.acme.admin;
}
~~~

In this example, the package `com.acme.orders.spi` is exposed only to the two modules `com.acme.checkout` and `com.acme.admin`. Other modules do not receive access to this package through that directive.

Qualified exports are useful when:

- A package is an integration API dedicated to specific internal modules.
- A module wants to limit the number of consumers allowed to depend on an API not yet intended for general public use.
- A group of modules needs to share an SPI or technical contract without exposing it to every module in the application.

Complete example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.checkout;
}
~~~

Module `com.acme.checkout` can read both the public API and the granted SPI. Another module can only read the public API package.

Qualified exports still follow the readability principle: a named module must read the providing module if it wants to use the package.

## 6. exports Is Not the Same as opens

Both `exports` and `opens` directives relate to package boundaries, but they serve two different types of access.

| Directive | Purpose | Main Capability |
|---|---|---|
| `exports` | Normal Java access | Other modules import and call public APIs of the package |
| `opens` | Deep reflection | Allows frameworks or libraries to perform deep reflection into the package |
| `opens ... to ...` | Restricted deep reflection | Opens the package only to specified modules |

Example of a module exposing an API to all consumers while opening a model package only to a serialization library:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.model to com.fasterxml.jackson.databind;
}
~~~

In this case:

- Other modules can import public types from `com.acme.orders.api`.
- The Jackson module is granted deep reflection access to `com.acme.orders.model`.
- Other modules do not automatically receive that deep reflection permission.

`exports` does not replace `opens`. If a framework needs to access private fields or non-public constructors via reflection, merely exporting the package is usually not enough. Conversely, opening a package for reflection does not mean the package has become an API that can be imported and used normally.

## 7. Is exports Transitive?

No. The `exports` directive exposes a package of the module that declares it; it does not automatically propagate export rights to other modules.

You need to distinguish:

- `exports p;` exposes package `p`.
- `requires transitive m;` propagates readability of module `m` to modules that depend on the current module.

For example, the public API of module `com.acme.orders` uses public types from module `com.acme.money`:

~~~java
module com.acme.orders {
    requires transitive com.acme.money;

    exports com.acme.orders.api;
}
~~~

`requires transitive` may be necessary so that consumers of `com.acme.orders` can also read `com.acme.money` when using types from that module through the orders API.

This does not mean packages of `com.acme.money` are exported by module `com.acme.orders`. Module `com.acme.money` must still expose its own API packages.

## 8. Common Mistakes and Misconceptions

### 8.1. Having requires but Missing exports

The consuming module declares:

~~~java
module com.acme.checkout {
    requires com.acme.orders;
}
~~~

But the providing module does not export the required package:

~~~java
module com.acme.orders {
    // com.acme.orders.api is not exported yet
}
~~~

As a result, the consuming module still cannot access that package. `requires` only creates readability; it does not bypass the encapsulation of the required module.

### 8.2. Exporting a Parent Package and Thinking Subpackages Are Also Exposed

The declaration:

~~~java
exports com.acme.orders.api;
~~~

does not expose `com.acme.orders.api.internal`. If you truly want other modules to access a subpackage, you must add a separate export directive. Before doing so, consider whether the subpackage should actually become part of the API.

### 8.3. Thinking exports Makes Every Class Public

A package-private class still cannot be imported from another module just because its package is exported. `exports` controls module boundaries; class and member modifiers continue to control accessibility according to the Java Language Specification.

### 8.4. Using exports When a Framework Needs Deep Reflection

If an error occurs when a framework tries to access a private field or non-public constructor, determine whether the package needs `opens`. Adding `exports` may not resolve deep reflection issues.

### 8.5. Exporting Too Many Packages

Exporting all packages turns many implementation details into an API surface that other modules can depend on. When internal structure changes, consumers can be affected.

You should start with a small set of API packages and export more only when there is an actual, intentional usage need.

## 9. How to Choose Packages to Export

When designing a module, evaluate each package by its role:

- **Public API:** contains abstractions, data types, and operations that consumers need to use; usually exported unconditionally.
- **SPI or integration API:** intended for specific modules; qualified exports can be used.
- **Implementation:** contains repository implementations, mappers, helpers, and internal classes; usually not exported.
- **Packages needing reflection:** open with `opens` only for frameworks that actually need it, with the narrowest possible scope.

Example:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.checkout;

    opens com.acme.orders.model to com.fasterxml.jackson.databind;
}
~~~

In this module, the API is exposed to every module reading `com.acme.orders`; the SPI is reserved for checkout; the model is opened to Jackson for reflection. Other implementation packages remain hidden.

Before adding an `exports` line, answer these questions:

1. Which consumer modules need to use this package?
2. Which public types do consumers need to import?
3. Is the package part of a stable API that the team is willing to support?
4. Should it be exported to all modules or only specific modules?
5. Do consumers need normal access or deep reflection?

## 10. Key Takeaways

`exports` is the directive that specifies **which packages of a named module are exposed for other modules to access under normal Java rules**. Consuming modules usually also need `requires` to read the providing module.

- `requires` creates a readability relationship.
- `exports` exposes a package.
- `exports p to m;` restricts which consumers are allowed to access the package.
- `exports` does not automatically export subpackages.
- `exports` does not change `public`, `protected`, package-private, or `private` modifiers.
- `opens` is for deep reflection and serves a different purpose from `exports`.

Good design typically exports only the packages that form the necessary API, keeps implementation inside the module, and opens reflection only for the exact libraries that require it. This is how JPMS helps modules maintain clear boundaries and reduce coupling to internal details.
