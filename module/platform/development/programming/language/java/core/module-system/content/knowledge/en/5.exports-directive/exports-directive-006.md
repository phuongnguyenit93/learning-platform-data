# Exporting API Packages and Implementation Packages

In the Java Platform Module System (JPMS), a module can contain many packages, yet not every package is meant to be used from other modules. The **exports** directive in **module-info.java** specifies which packages are exposed across the module boundary. This is how a module separates the stable API portion that users are allowed to call from the internal implementation portion that may change according to implementation needs.

Designing this boundary reduces coupling between modules, limits external code from accessing internal details, and makes it possible to change implementations without impacting API users.

## 1. API Packages and Implementation Packages

A module typically has two groups of packages:

- **API packages** contain types that other modules need to use, such as public interfaces, classes, exceptions, and data types.
- **Implementation packages** contain internal logic, helpers, adapters, concrete repositories, or classes that only serve internal implementation within the module.

Payment module example:

~~~text
com.example.payment
├── module-info.java
└── src
    └── com.example.payment
        ├── api
        │   ├── PaymentService.java
        │   ├── PaymentRequest.java
        │   └── PaymentResult.java
        └── internal
            ├── DefaultPaymentService.java
            └── GatewayClient.java
~~~

The API package is where other modules look to invoke payment functionality. The internal package only serves logic inside the payment module. This division is a design convention; JPMS enforces the access boundary through the module descriptor.

## 2. Using exports to Expose the API Package

Suppose the module is named **com.example.payment**. The **module-info.java** file exports only the API package:

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

Another module can declare a dependency:

~~~java
module com.example.order {
    requires com.example.payment;
}
~~~

Then code in the order module can import public types belonging to the exported package:

~~~java
package com.example.order;

import com.example.payment.api.PaymentRequest;
import com.example.payment.api.PaymentResult;
import com.example.payment.api.PaymentService;

public class OrderCheckout {
    private final PaymentService paymentService;

    public OrderCheckout(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public PaymentResult checkout(PaymentRequest request) {
        return paymentService.pay(request);
    }
}
~~~

The directive **exports com.example.payment.api;** makes public types in the API package accessible to reading modules under Java rules. The consuming module must still have a readability relationship, typically declared with **requires**.

**exports** applies to the whole package, not selectively to individual classes. If a package contains multiple public classes, all public classes in that package are part of the exported API surface. Therefore, organize packages so that types intended to be public reside together in the API package, while helpers and internal details reside in separate packages.

## 3. Unexported Packages Are Internal Implementation

Suppose the payment module has an implementation:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentRequest;
import com.example.payment.api.PaymentResult;
import com.example.payment.api.PaymentService;

public class DefaultPaymentService implements PaymentService {
    @Override
    public PaymentResult pay(PaymentRequest request) {
        // Perform internal payment processing.
        return PaymentResult.success();
    }
}
~~~

The package **com.example.payment.internal** is not declared in **exports**. Therefore, even though the **DefaultPaymentService** class is public, other modules cannot access it across the JPMS boundary in the normal way.

This differs from Java's **public** modifier:

- **public** determines the access level of a type or member under the Java language.
- **exports** determines whether a package is exposed to other modules.
- To use a public type from another module, the package containing that type must be appropriately exported and the calling module must read the providing module.

A public class located in an unexported package can still be used inside the module that owns it. Implementation packages can call one another under normal Java access rules, while external modules cannot treat them as API.

If the order module tries to import **com.example.payment.internal.DefaultPaymentService**, the compiler will report that the package or type is not accessible because the package is not exported. Adding **requires com.example.payment** does not solve this error; it is necessary to use the exported API or adjust the design providing the functionality.

## 4. APIs Should Expose Abstractions, Not Implementation Classes

A common design is to export interfaces or abstractions, then keep implementation classes in internal packages.

API example:

~~~java
package com.example.payment.api;

public interface PaymentService {
    PaymentResult pay(PaymentRequest request);
}
~~~

The payment module can create an internal implementation:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentRequest;
import com.example.payment.api.PaymentResult;
import com.example.payment.api.PaymentService;

public final class DefaultPaymentService implements PaymentService {
    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.success();
    }
}
~~~

External modules only depend on **PaymentService**, **PaymentRequest**, and **PaymentResult**. They do not need to know whether the current implementation is **DefaultPaymentService**, **RemotePaymentService**, or another class.

This design brings several benefits:

- Implementations can be swapped without forcing consuming modules to change imports or instantiate concrete classes.
- Reduces the risk of external code depending on helpers or internal data structures.
- Keeps the API surface small, easier to document, and easier to test.
- Allows the owning module to control how implementations are created and configured.

One way to provide implementations is a factory method located in the API package:

~~~java
package com.example.payment.api;

public final class Payments {
    private Payments() {
    }

    public static PaymentService createDefault() {
        return com.example.payment.internal.PaymentServices.create();
    }
}
~~~

In real-world designs, a factory can delegate to an internal package or use the Service Provider Interface mechanism. The key point is that external modules only need to know the API types that the module has exported.

## 5. Qualified Exports: Exposing Only to Selected Modules

Not every API package needs to be opened to all modules. JPMS supports **qualified exports**, meaning exporting a package only to a target module list.

Example:

~~~java
module com.example.payment {
    exports com.example.payment.api;
    exports com.example.payment.integration to com.example.order,
                                               com.example.billing;
}
~~~

In this example:

- **com.example.payment.api** is exported unconditionally to modules reading the payment module.
- **com.example.payment.integration** is exported only to **com.example.order** and **com.example.billing**.
- Other modules not on the list cannot access the integration package across the module boundary.

Qualified exports are suitable when a module has a shared API and certain integration packages intended only for specific collaborating modules. However, the target module list creates extra coupling between the providing module and consuming modules. If the list changes frequently, consider extracting the integration functionality into a separate module or designing a more suitable general API.

Qualified exports are still exports for normal Java access; they are not equivalent to **opens** for deep reflection.

## 6. How Does exports Differ from opens?

Both **exports** and **opens** appear in **module-info.java**, yet they address two different needs:

| Directive | Purpose | Access Granted |
|---|---|---|
| **exports package.name;** | Expose the package's API | Access to public types under Java rules |
| **exports package.name to module.name;** | Expose API to selected modules | Normal access within the scope of target modules |
| **opens package.name;** | Allow deep reflection at runtime | Reflection into members including private ones under JPMS rules |
| **opens package.name to module.name;** | Open package to a specific framework/module | Deep reflection within the scope of target modules |

Example of an object-mapping framework needing to access private fields:

~~~java
module com.example.payment {
    exports com.example.payment.api;
    opens com.example.payment.model to com.example.mapper;
}
~~~

Package **com.example.payment.model** is opened to the mapper module so the framework can use deep reflection. This directive does not turn the model package into a normal public Java API. If other modules need to import public types in the model package, an appropriate exports directive is needed.

Do not add **opens** just to fix a package import error or normal API access. In that case, review **exports** and **requires**. Conversely, adding **exports** does not automatically solve reflection errors on private fields or constructors.

## 7. Complete Example with Two Modules

Suppose there are two modules:

~~~text
src/
├── com.example.payment/
│   ├── module-info.java
│   └── com/example/payment/
│       ├── api/
│       │   ├── PaymentService.java
│       │   └── PaymentResult.java
│       └── internal/
│           └── DefaultPaymentService.java
└── com.example.checkout/
    ├── module-info.java
    └── com/example/checkout/
        └── Main.java
~~~

The payment module exports only the API package:

~~~java
module com.example.payment {
    exports com.example.payment.api;
}
~~~

API:

~~~java
package com.example.payment.api;

public interface PaymentService {
    String pay();
}
~~~

Implementation:

~~~java
package com.example.payment.internal;

import com.example.payment.api.PaymentService;

public final class DefaultPaymentService implements PaymentService {
    @Override
    public String pay() {
        return "Payment accepted";
    }
}
~~~

The checkout module declares the dependency:

~~~java
module com.example.checkout {
    requires com.example.payment;
}
~~~

Checkout code can use the API interface:

~~~java
package com.example.checkout;

import com.example.payment.api.PaymentService;

public class Main {
    public static void main(String[] args) {
        PaymentService service = null;
        System.out.println("Checkout module can compile against PaymentService");
    }
}
~~~

Checkout code cannot import **com.example.payment.internal.DefaultPaymentService**, because the internal package is not exported. In this minimal example, the checkout module needs to receive a PaymentService instance via a factory, dependency injection, or ServiceLoader when running for real. How the implementation is instantiated does not change the principle: the consuming module depends only on the exported API.

Compile the modules using the module source path:

~~~bash
javac --module-source-path src -d out -m com.example.payment,com.example.checkout
~~~

During compilation, if checkout imports a class in the internal package, the compiler will deny access to that package. This is a useful check to protect the API boundary right at compile time.

## 8. Organizing Packages for Clear API Boundaries

When designing a new module, the following principles can be applied:

1. Place interfaces, DTOs, exceptions, and public types in clearly named API packages.
2. Place concrete implementations, helpers, and internal adapters in separate packages such as **internal**, **impl**, or dedicated packages.
3. Export only packages that consuming modules genuinely need.
4. Limit qualified exports to integrations with clear module relationships.
5. Use **opens** separately for identified reflection needs, typically for specific frameworks.
6. Avoid putting implementation classes in the same package as the API if you do not want them included in the exported surface.
7. Treat public types in exported packages as API commitments; changing their signatures can affect consuming modules.

Names like **internal** or **impl** do not create protection on their own. The boundary is enforced by JPMS through not exporting those packages. If the module descriptor accidentally exports an internal package, that package becomes part of the API regardless of its package name.

It is also worth noting that exporting a package does not automatically re-expose all of the module's dependencies. If the payment module's public API uses types belonging to another module, the providing module may need to declare **requires transitive** for the appropriate dependency so that modules consuming the API receive the readability needed by design. Exporting packages and propagating readability are two independent decisions.

## 9. Common Errors and How to Handle Them

**Module has requires, yet cannot access public class**

Check whether the package containing the class is exported. The public modifier does not cross the module boundary when the package is unexported.

**Implementation class is imported directly by another module**

If the class resides in an unexported internal package, the compiler will reject it. The consuming module should call the abstraction in the API; the owning module can provide a factory or implementation creation mechanism.

**Package exported, yet framework still cannot access private fields**

Exports only expose normal APIs. If deep reflection is needed, open the exact package using opens or qualified opens for the framework module.

**External modules can access too many packages that should not be public**

Inspect module-info.java and remove unnecessary exports directives. Then move internal classes into unexported packages and update valid usages within the owning module.

**Qualified exports break compilation of a new module**

Check whether the target module name matches the actual module name. Only listed modules have access to a qualified-exported package.

**Public API depends on a type from another module, yet consuming module cannot read the dependency**

Consider a **requires transitive** relationship in the module providing the API. Do not add transitive mechanically; use it only when the dependency is genuinely part of the API contract that consuming modules must be able to read.

## 10. Key Takeaways

- **exports** exposes packages to other modules; unexported packages remain internal implementations under JPMS boundaries.
- **public** is a Java modifier, whereas **exports** is package access permission across module boundaries.
- Individual classes cannot be exported separately; exports applies to the entire package.
- Qualified exports restrict an API package to specified target modules.
- **opens** is for deep reflection at runtime and does not replace exports.
- Expose stable abstractions and keep implementation classes in unexported packages.
- The **requires transitive** directive controls propagation of dependency readability; it is independent of exports.
- The package name **internal** does not protect an implementation by itself; the module descriptor determines whether a package is exposed.

When reviewing a module, look at the exports list in module-info.java and verify whether each package is genuinely an API that needs to support external modules. A small, intentional API surface makes it easy to change implementations, reduces coupling, and keeps contracts between modules clear.