# Avoid Creating an Interface for Every Class Before There Is a Need

In Java, an `interface` is a tool for describing a contract that multiple types can implement. However, **not every class needs its own interface**. If you create a `SomeService`/`SomeServiceImpl` pair for every class even when there is no need for substitution, extension, or separating dependency boundaries, the codebase may have more layers without becoming more flexible.

The practical principle is: **start with the simplest design that meets current needs; add an interface when it expresses a meaningful boundary or substitutability**. This is an application of YAGNI (*You Aren’t Gonna Need It*): do not build speculative flexibility just because you might need it in the future. That does not mean forbidding an interface with a single implementation; what matters is the design rationale.

## 1. What Problem Does an Interface Solve?

An interface declares the operations that a type commits to providing, without forcing callers to depend on a specific implementation.

For example, `PaymentGateway` can define a payment operation. One implementation uses a real payment gateway, another uses a sandbox, and tests can use a fake to record calls. `OrderService` only needs to know the payment contract, not the specific provider.

Conversely, if a class merely formats strings according to a stable rule, has only one caller, and has no need to change behavior, creating a `Formatter` interface, a `DefaultFormatter` implementation, and adding a forwarding class just to call one method can add extra type names, files, and navigation steps without solving a real problem.

An interface is useful when it creates **genuine substitutability**, boundaries between components, or a public contract. It does not automatically make a design better merely because the code has been "abstracted".

## 2. Why Not Create Interfaces Mechanically?

- **Increased indirection:** readers must trace from the interface to the implementation to understand the behavior, even when there is only a single execution path.
- **Increased number of types and files:** a simple class can turn into an unnecessary interface, default implementation, factory, and delegating class.
- **False extension points:** multiple implementations may never exist; a flexible API based on unverified assumptions can make the design harder to change.
- **Increased maintenance cost:** when the contract changes, every implementation and configuration site may need to be updated as well.
- **Tests overly dependent on structure:** if you mock every internal class, tests tend to verify how things are implemented rather than the outcomes/behavior that users care about.
- **Obscured responsibilities:** an interface without a clear business meaning or boundary makes the names and roles of components harder to understand.

This is not a reason to avoid interfaces in general. It is a reason to require a specific benefit before adding an abstraction layer.

## 3. When Is an Interface Worth Creating?

### 3.1 Multiple Genuine Implementations

When the same contract has implementations with different behaviors or mechanisms, an interface helps the caller select an implementation without containing `if/else` logic for each concrete class.

For example: `FileStorage` and `CloudStorage`, multiple pricing policies, multiple sorting strategies, or different payment providers. Multiple implementations must conform to a single stable contract; otherwise, merely having multiple classes does not necessarily call for an interface.

### 3.2 A Boundary with External Systems

Databases, HTTP clients, email gateways, queues, or payment services are dependencies that can vary by environment and are difficult to run in unit tests. An interface at that boundary prevents business logic from depending directly on a library or provider.

You do not necessarily have to create an interface for every wrapper around a library. Place the contract where it makes sense for the consuming component, and expose only the operations that the component actually needs.

### 3.3 A Public API, Plugin, or Explicitly Designed Extension Point

If other code will implement the contract, or the system supports plugins/extensions, an interface can be the part of the API that needs to remain stable. In this case, even if there is initially only one implementation, the contract still has value because it is a deliberately published boundary.

### 3.4 A Need to Substitute Dependencies in Tests

Interfaces are useful when a fake or stub helps test a component's behavior without starting up external systems. However, you should not infer that "to be testable, every class must have an interface". Pure functions, small classes with deterministic behavior, and many internal components can be tested directly. Extract a contract only at boundaries where substitution brings clear value.

### 3.5 A Need to Depend on a Contract Rather Than Implementation Details

According to the *Dependency Inversion Principle*, high-level policy should not be tightly coupled to low-level details; both should depend on appropriate abstractions. However, this **does not mean every dependency must be an interface**. A small, stable concrete class that does not introduce concerning coupling can be a simpler, more readable choice.

## 4. When Should You Keep a Concrete Class?

It is usually best to start with a concrete class when most of the following conditions hold:

- It has a clear, stable behavior and currently only one reasonable way to implement it.
- The class is not an extension API for external code and does not sit at a boundary prone to change.
- No actual caller needs to choose or swap implementations.
- Adding an interface would merely rename the type, forward calls, or duplicate the exact same contract without an independent purpose yet.
- Tests can verify results through the class's public API without needing to mock internal details.

For example, `ReceiptFormatter` only combines an order ID into a receipt line according to a simple rule. If there is no need yet to select a format by region, channel, or policy, a concrete class is sufficient. When a real requirement emerges, such as multiple interchangeable receipt formats, you can extract a `ReceiptFormatter` interface at that time with names and methods reflecting the new need.

Do not use "only one implementation" as an absolute rule. A single-implementation interface is still reasonable if it is a port at an infrastructure boundary, a public API, or an important substitution seam. Conversely, two implementations that differ only in name without any need for substitution do not necessarily make a good abstraction either.

## 5. Java 17+ Example: Abstracting at the Right Boundary

In the following example, `PaymentGateway` is an interface because the way payment is performed can change or be substituted during testing. `ReceiptFormatter` remains a concrete class because the current formatting rule is simple and stable. `OrderService` depends on the payment contract, but does not create a separate interface for every collaborator.

Save the complete code to `InterfaceWhenNeededDemo.java`:

```java
public class InterfaceWhenNeededDemo {
    @FunctionalInterface
    interface PaymentGateway {
        void charge(String orderId, int amountCents);
    }

    static final class SandboxPaymentGateway implements PaymentGateway {
        @Override
        public void charge(String orderId, int amountCents) {
            System.out.println("Charged " + orderId + ": "
                    + amountCents + " cents");
        }
    }

    static final class ReceiptFormatter {
        String format(String orderId) {
            return "Receipt for " + orderId;
        }
    }

    static final class OrderService {
        private final PaymentGateway paymentGateway;
        private final ReceiptFormatter receiptFormatter =
                new ReceiptFormatter();

        OrderService(PaymentGateway paymentGateway) {
            this.paymentGateway = paymentGateway;
        }

        void checkout(String orderId, int amountCents) {
            paymentGateway.charge(orderId, amountCents);
            System.out.println(receiptFormatter.format(orderId));
        }
    }

    public static void main(String[] args) {
        OrderService service =
                new OrderService(new SandboxPaymentGateway());
        service.checkout("ORD-42", 1250);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac InterfaceWhenNeededDemo.java
java InterfaceWhenNeededDemo
```

Exact stdout:

```text
Charged ORD-42: 1250 cents
Receipt for ORD-42
```

### Reading the Design in the Example

- `OrderService` calls `PaymentGateway.charge(...)` instead of depending directly on `SandboxPaymentGateway`. Another implementation can be substituted without modifying the checkout logic.
- `SandboxPaymentGateway` is an illustrative runnable implementation. In a real system, an adapter can call a payment provider; a sandbox should not be treated as a real-money transaction.
- `ReceiptFormatter` is used directly because it currently performs only a small, deterministic formatting rule. There is no clear benefit to adding a `ReceiptFormatter` interface just to have one more type.
- `PaymentGateway` has a single abstract method, so it is annotated with `@FunctionalInterface`. In tests, a lambda can be supplied as a fake, for example:

```java
PaymentGateway fake = (orderId, amountCents) ->
        System.out.println("Fake charge: " + orderId + ", " + amountCents);
OrderService service = new OrderService(fake);
service.checkout("TEST-1", 500);
```

The test snippet above is placed in a context that can access the nested types of `InterfaceWhenNeededDemo` (for example, inside the demo class or a test in the same package with appropriate access). It illustrates dependency substitutability and is not part of `main` in the main program execution. As the project grows larger, you can move the types to top-level types and adjust modifiers according to package/API boundaries.

## 6. Choosing a Class, Interface, or Abstract Class?

| Option | Choose when | Typical examples |
| --- | --- | --- |
| Concrete class | There is a deterministic, stable behavior; no need to substitute implementations yet. | `ReceiptFormatter`, pure calculation classes. |
| Interface | A contract/capability is needed that multiple implementations or external components can conform to. | `PaymentGateway`, `Storage`, `Clock` at boundaries requiring substitution. |
| Abstract class | Classes in the same family need to share state, implementation code, or a common workflow; Java allows inheriting from only one class. | A base class with a template method and genuinely shared state. |

An interface primarily describes a contract; an abstract class can hold state and implement part of shared behavior. Do not create an abstract class just to avoid duplicating a few lines, and do not create an interface just because a class has public methods.

## 7. How to Decide Before Adding an Interface

You can ask yourself in order:

1. **Who is the consumer?** Does any component need to call through a contract instead of knowing the concrete class?
2. **What needs to be substituted?** Are there genuinely different implementations, environments, or policies? If not yet, does that boundary have another public/architectural reason?
3. **Are changes blocked by coupling?** If the concrete class changes, does it force business logic or tests to depend on a library/infrastructure?
4. **What does the interface express?** Do its name and methods describe a meaningful capability or contract, or do they just repeat the class name with `I`, `Default`, or `Impl` added?
5. **Is the cost worth it?** Do the benefits for substitution, testing, APIs, or module boundaries outweigh the number of new types and navigation points?
6. **Can it be safely deferred?** If there is no current need and no critical boundary to protect, start with a concrete class and extract an interface when design evidence emerges.

Not every answer has to be "there are multiple implementations". An interface can also protect a boundary before a second implementation exists. However, that reason should be concrete and explainable, not merely vague speculation.

## 8. Practices That Tend to Cause Problems

### Creating Interfaces Just to Follow Naming Conventions

For example, every class is forced to have a `CustomerService` and `CustomerServiceImpl` pair even when there is no contract or independent consumer. This convention may make sense within a clearly defined framework or architecture, but it is not a general Java rule. Base your decision on the system's requirements, rather than creating intermediate layers out of habit.

### Using an Interface to Hide an Unclear Design

Using generic names like `Manager`, `Processor`, or `Handler` does not make responsibilities any clearer. Before creating an abstraction, define the capability, inputs/outputs, and conditions that every implementation must comply with.

### Mocking All Classes in Unit Tests

Mocks can be useful at external boundaries, but mocking every small collaborator makes tests brittle when internal structure changes. Prefer testing observable behavior; use a fake/mock where you need to control dependency outcomes or avoid real I/O.

### Keeping an Abstraction That No Longer Has Value

If multiple implementations have been removed and the contract is no longer needed by any consumer, consider controlled simplification. Conversely, do not delete an interface merely because it has only one implementation today if it remains an important API/infrastructure boundary.

## Conclusion

An interface is a tool for expressing contracts and providing meaningful substitutability, not a mandatory step for every class. Keep concrete classes when behavior is simple and stable; create interfaces when you need multiple implementations, infrastructure boundaries, extension APIs, or a genuinely useful substitution point. Good design is not about having the most abstraction, but about **placing abstractions right where they are needed and avoiding indirection that provides no value**.
