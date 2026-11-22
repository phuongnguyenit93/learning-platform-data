# Module Boundaries and Changing Implementations

The Java Platform Module System (JPMS) helps an application clearly define which packages are public API and which belong to the internal implementation. This boundary enables the development team to change internal algorithms, class structures, or storage mechanisms without forcing every consuming module to change alongside them.

To swap implementations safely, you first need to design a **stable contract at the module boundary**. Consumers depend only on the exposed types and behavior; the concrete implementation resides in unexported packages. When making internal changes, compatibility with that contract must be preserved.

## 1. What Does a Module Boundary Protect?

A module can contain multiple packages. In the module descriptor file (module-info.java), the exports declaration specifies which packages are used by other modules as standard Java APIs.

For example:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

In this module:

- The com.example.orders.api package is the exposed API surface.
- Other packages, such as com.example.orders.internal, are not exported and are kept inside the module.
- A public class in an unexported package can still be used by code belonging to the same module, but other modules cannot access it as a normal API.

The module boundary operates at a broader level than individual class access modifiers. The public modifier indicates that a class/member can be accessed according to Java rules; exports determines whether the package is exposed across the module boundary.

Note the distinction:

| Mechanism | Scope and Meaning |
| --- | --- |
| private | Accessible only within the declaring class |
| package-private | Accessible within the same package |
| protected | Accessible by package and inheritance rules |
| public | Public according to Java access rules |
| exports | Allows other modules to access public APIs in the exported package |
| opens | Allows deep reflection into the package under JPMS rules |

An unexported package does not become a public API merely because it contains a public class.

## 2. Separating API from Implementation

Suppose the orders module provides order creation functionality. Consumers only need to know how to invoke the service and receive the result. Consumers do not need to know which database the implementation uses, how the pricing algorithm works, or which classes perform the work.

Suggested structure:

~~~text
com.example.orders/
├── module-info.java
├── com/example/orders/api/
│   ├── OrderRequest.java
│   ├── OrderResult.java
│   ├── OrderService.java
│   └── OrderServices.java
└── com/example/orders/internal/
    └── DefaultOrderService.java
~~~

The module descriptor exports only the API package:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

### API Contract

OrderRequest and OrderResult are the data types consumers are allowed to use:

~~~java
package com.example.orders.api;

public record OrderRequest(String productId, int quantity) {
}
~~~

~~~java
package com.example.orders.api;

public record OrderResult(String orderId, boolean accepted) {
}
~~~

The interface describing the behavior:

~~~java
package com.example.orders.api;

public interface OrderService {
    OrderResult place(OrderRequest request);
}
~~~

The factory creates the implementation and returns only the interface:

~~~java
package com.example.orders.api;

import com.example.orders.internal.DefaultOrderService;

public final class OrderServices {

    private OrderServices() {
    }

    public static OrderService create() {
        return new DefaultOrderService();
    }
}
~~~

### Internal Implementation

The implementation class resides in an unexported package:

~~~java
package com.example.orders.internal;

import com.example.orders.api.OrderRequest;
import com.example.orders.api.OrderResult;
import com.example.orders.api.OrderService;
import java.util.UUID;

public final class DefaultOrderService implements OrderService {

    @Override
    public OrderResult place(OrderRequest request) {
        if (request.quantity() <= 0) {
            return new OrderResult(null, false);
        }

        String orderId = UUID.randomUUID().toString();
        return new OrderResult(orderId, true);
    }
}
~~~

The DefaultOrderService class can be public so the factory in another package of the same module can instantiate it. Because the internal package is not exported, external consumers cannot depend directly on this class.

### Consumer Using the API

The consuming module only needs to declare a dependency on the orders module:

~~~java
module com.example.shop {
    requires com.example.orders;
}
~~~

Consumer code:

~~~java
import com.example.orders.api.OrderRequest;
import com.example.orders.api.OrderResult;
import com.example.orders.api.OrderService;
import com.example.orders.api.OrderServices;

public class Checkout {

    public OrderResult submit(String productId, int quantity) {
        OrderService service = OrderServices.create();
        return service.place(new OrderRequest(productId, quantity));
    }
}
~~~

The consumer knows the interface, request, and result. The consumer does not need to import DefaultOrderService or know that the internal package exists.

## 3. Changing Implementations Without Changing Consumers

When the contract is clearly separated, the module can replace implementation classes without altering the API.

For example, the initial version uses:

~~~java
public OrderService create() {
    return new DefaultOrderService();
}
~~~

A later version switches to:

~~~java
public OrderService create() {
    return new OptimizedOrderService();
}
~~~

OptimizedOrderService also resides in an internal package and implements OrderService. If the API signatures and promised behavior remain compatible, consumers keep calling OrderServices.create() as before.

Changes that can typically be made inside the module:

- Changing processing algorithms or data structures.
- Adding caching, batching, or query optimizations.
- Splitting a large implementation into multiple internal classes.
- Replacing internal libraries or infrastructure connection mechanisms.
- Renaming, moving, or deleting classes in unexported packages.
- Adding internal packages to organize code.
- Changing the default implementation in the factory.

This is the primary benefit of module-level encapsulation: consumers depend on the contract, not on implementation details.

However, preserving method signatures is not enough to guarantee compatibility. The new implementation must also honor the semantics of the contract: outputs, error conditions, validation rules, data consistency, thread-safety, and ordering guarantees if published by the API.

## 4. Changes That Can Break the API Contract

When modifying exported packages, assess the impact on source compatibility, binary compatibility, and behavioral compatibility.

| Change | Possible Impact |
| --- | --- |
| Removing an already published public class or public method | Consumers may fail to compile or encounter runtime linkage errors |
| Renaming an exported package | Consumers must update imports and module descriptors |
| Changing parameter types or return types | Method signature changes; already compiled code may fail to link |
| Changing an instance method to static or vice versa | Calling convention and binary contract change |
| Changing an interface that consumers implement | Can make consumer implementations incompatible |
| Removing a package from exports | Consumers in other modules lose access to the package |
| Changing result semantics or error conditions | Can break behavioral compatibility even if signatures stay unchanged |
| Changing unexported internal classes | Generally has no direct impact on consumers respecting the module boundary |

One case requiring care is adding an abstract method to a public interface. Consumers might be providing their own implementations of that interface. When an interface adds an abstract method, older implementations may no longer satisfy the new contract. Where semantically appropriate, consider a default method or create a separate extended interface to represent the new capability.

Do not place internal implementation classes in API signatures. For example:

~~~java
// Avoid: exposes implementation type in public contract.
public DefaultOrderService create();
~~~

Return an exposed interface or abstraction instead:

~~~java
// Better: consumer depends only on the contract.
public OrderService create();
~~~

If a public method returns a type residing in an unexported package, consumers may struggle to compile and use the result. Data types appearing in API signatures are also part of the public boundary.

## 5. Exports, Qualified Exports, and Opens in Boundary Design

An export declaration that does not reference specific modules exposes the package to every module that reads this module:

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

If a package should only be used by certain specific modules, JPMS supports qualified exports:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.integration
        to com.example.reporting;
}
~~~

This can be useful when an integration API reserved for another module is needed. However, a qualified export creates an explicit dependency between the two modules. If overused, it can reduce the ability to change independently.

opens serves a different purpose:

~~~java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model
        to com.example.json;
}
~~~

The model package is opened to the com.example.json module so the framework can perform deep reflection. This does not make the package a normal Java API.

An open module opens all packages for deep reflection under JPMS rules:

~~~java
open module com.example.legacy {
}
~~~

This is a broad scope and lowers the level of encapsulation. For new module designs, consider opening only the exact packages and exact modules needing access.

## 6. Keeping Implementations Changeable Over the Long Term

Some principles help modules evolve cleanly:

**Expose abstractions instead of concrete classes.** Consumers should depend on interfaces, records, or data types belonging to the API package. Factories or public constructors are responsible for providing an appropriate implementation.

**Keep internal types out of API signatures.** Do not let public methods return or accept types that only exist in internal packages. If data must be exchanged across the boundary, define contract types in the API package.

**Keep contract semantics clear.** Document nullability, exceptions, validation, state, thread-safety, and operational conditions that consumers are permitted to rely on. New implementations must uphold these commitments.

**Separate optional capabilities.** If some implementations have additional features, consider extended interfaces or separate capabilities instead of continually adding mandatory methods to the base interface.

**Hide implementation selection.** Let factories, dependency injection, or service discovery decide the implementation. Consumers should not instantiate internal classes themselves.

**Limit package exports.** Only export packages that the module genuinely commits to supporting as API. Do not export an entire package just so one consumer can access an internal class.

**Manage deprecation with a roadmap.** When an old API needs replacement, mark it deprecated, provide the new API, migration documentation, and a compatibility period before removing it in an appropriate major version.

## 7. When Multiple Implementations Are Needed: Use ServiceLoader

An internal factory fits when a module chooses its own implementation. If other modules need to supply plugins, you can design a public service interface and use ServiceLoader.

The module containing the service API declares:

~~~java
module com.example.payment.api {
    exports com.example.payment.api;
}
~~~

Service contract:

~~~java
package com.example.payment.api;

public interface PaymentProcessor {
    boolean supports(String method);
    void process(String paymentId);
}
~~~

The provider module depends on the API and registers the implementation:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProcessor
        with com.example.payment.card.CardPaymentProcessor;
}
~~~

The provider class can reside in an unexported package:

~~~java
package com.example.payment.card;

import com.example.payment.api.PaymentProcessor;

public final class CardPaymentProcessor
        implements PaymentProcessor {

    public boolean supports(String method) {
        return "CARD".equals(method);
    }

    public void process(String paymentId) {
        System.out.println("Processing card payment: " + paymentId);
    }
}
~~~

The consumer module declares usage of the service:

~~~java
module com.example.checkout {
    requires com.example.payment.api;

    uses com.example.payment.api.PaymentProcessor;
}
~~~

Consumer discovers implementations:

~~~java
import com.example.payment.api.PaymentProcessor;
import java.util.ServiceLoader;

ServiceLoader.load(PaymentProcessor.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(processor -> processor.supports("CARD"))
    .forEach(processor -> processor.process("PAY-001"));
~~~

ServiceLoader lets consumers depend on the service contract rather than directly depending on provider modules. Providers must be included in module resolution and appropriate service binding to be found at runtime. With named modules, uses and provides declarations express this relationship in the module descriptor.

This design approach is useful for plugin architectures, multiple adapters, or implementations chosen based on the deployment environment.

## 8. Verifying Module Boundaries When Making Changes

When refactoring implementations or modifying the module descriptor, check the following points:

1. List the packages exported in module-info.java.
2. Confirm that public APIs only reference types in exposed packages or appropriate module dependencies.
3. Confirm that internal packages are not accidentally exported.
4. Check that consuming modules still compile and call the API as before.
5. Check provider modules or service implementations if any exist.
6. Run contract tests to compare results and behavior of the new implementation.
7. Check binary compatibility when replacing a module that consumers were previously compiled against.
8. Check opens and qualified exports to ensure access permissions are granted only according to design intent.

JDK tools can be used to assist analysis:

~~~shell
# View dependencies and packages used in the JAR
jdeps --module-path mods --module com.example.orders

# Analyze dependencies by module
jdeps --module-path mods --print-module-deps app.jar

# View descriptor of a module JAR
jar --describe-module --file mods/com.example.orders.jar
~~~

jdeps helps detect dependencies and supports evaluating module migration. It does not replace behavioral contract testing or API compatibility checks.

## 9. Before-and-After Mindset Example When Replacing an Implementation

Suppose the initial version has:

~~~text
com.example.orders
├── api
│   ├── OrderService
│   └── OrderServices
└── internal
    └── DefaultOrderService
~~~

Consumers only call:

~~~java
OrderService service = OrderServices.create();
service.place(request);
~~~

In a later version, the development team needs to change the processing approach:

~~~text
com.example.orders
├── api
│   ├── OrderService
│   └── OrderServices
└── internal
    ├── OptimizedOrderService
    ├── OrderValidator
    ├── PricingEngine
    └── OrderRepositoryAdapter
~~~

If the module descriptor and API contract remain compatible, consumers continue using the same call pattern. Internal classes can be added, removed, or reorganized according to implementation needs.

Conversely, if consumers directly instantiate DefaultOrderService, import the internal package, or call methods present only on a specific implementation, consumers have depended on implementation details. When replacing the class, the orders module will have to keep a compatibility adapter or require consumers to modify their code.

That is why clear boundaries must be maintained from the beginning, rather than relying solely on naming conventions such as Internal, Default, or Impl.

## Conclusion

The module boundary defines which part is the exposed contract and which belongs to the internal implementation. When consumers depend only on API packages, a module can change algorithms, classes, libraries, and internal structures without forcing consumers to change. To preserve that capability, manage exports, keep internal types out of API signatures, maintain the behavioral contract, and verify compatibility when releasing new versions.
