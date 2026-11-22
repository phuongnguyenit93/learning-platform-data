# Abstraction in Java: What Is It and What Problem Does It Solve?

## 1. Core Concept

**Abstraction** is a way of describing an object or a capability through the characteristics and behaviors **essential to the consumer**, while leaving the implementation details in the implementation layer behind it. When invoking a behavior, consumer code needs to know **what it can request** and **what the result/contract is**; it does not necessarily need to know the algorithm, internal data, or external systems used to fulfill the request.

Everyday example: a user clicks the "Pay" button and cares about the amount, success/failure status, and receipt; they do not need to know whether the transaction is routed through a bank or an e-wallet, how the network request is constructed, or how internal reconciliation is performed.

In Java, an abstraction boundary can be expressed using an **interface**, an **abstract class**, or even regular classes with a clear public API. Abstraction is a **design principle**; `interface` and `abstract` are **language constructs** supporting that principle. Simply creating an interface does not mean you have created a good abstraction.

Keep three questions in mind:

- **What?** What behaviors can the caller request?
- **What guarantees?** How are valid inputs, outputs, errors, and side effects understood?
- **How?** Who performs it and by what mechanism? This is the part that can be hidden behind the abstraction boundary.

## 2. Why Do We Need Abstraction?

Suppose a sales service handles payment directly using a concrete bank transfer class:

```java
// Illustrates direct dependency; not a standalone program.
final class CheckoutService {
    private final BankTransferGateway gateway = new BankTransferGateway();

    Receipt checkout(long totalVnd) {
        return gateway.pay(totalVnd);
    }
}
```

This snippet may suffice for a small problem, but as requirements grow, issues will emerge:

1. **Tight coupling to the implementation:** `CheckoutService` itself decides to use `BankTransferGateway`. If switching to an e-wallet, you may have to modify the business logic class.
2. **Hard to substitute for testing:** testing checkout rules might accidentally call the real payment integration or require setting up a mock bank environment.
3. **Technical details leaking into business logic:** if the service knows each provider's endpoint names, request signing mechanism, or response structure, the business logic becomes increasingly harder to read and maintain.
4. **Cascading changes:** multiple places that know about the concrete class will all be affected when the library or provider changes.

The idea: have the business code depend on a **stable capability** named `PaymentGateway`; each provider implements that capability. Then "payment" is the published business concept, while "where to send the request and how to do it" are details behind the scenes.

The desired relationship:

```text
CheckoutService --> PaymentGateway (contract)
                         ^
                         |
             +-----------+-----------+
             |                       |
   BankTransferGateway          WalletGateway
   (first approach)             (second approach)
```

The diagram shows the direction of the **type** dependency in the calling code. Creating and selecting an implementation still needs to happen somewhere, such as in `main` or in the application configuration.

## 3. A Complete, Runnable Example with Java 17+

Create the file **`AbstractionDemo.java`** with the following content. To keep the focus on abstraction, the gateways only return mock receipts with deterministic values; the example **does not connect to or execute any real payment transactions**.

```java
import java.util.Objects;

interface PaymentGateway {
    Receipt pay(long amountVnd);
}

record Receipt(String provider, long amountVnd, String reference) {
}

final class BankTransferGateway implements PaymentGateway {
    @Override
    public Receipt pay(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
        return new Receipt("BankTransfer", amountVnd, "BANK-001");
    }
}

final class WalletGateway implements PaymentGateway {
    @Override
    public Receipt pay(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
        return new Receipt("Wallet", amountVnd, "WALLET-001");
    }
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    Receipt checkout(long totalVnd) {
        if (totalVnd <= 0) {
            throw new IllegalArgumentException("totalVnd must be positive");
        }
        return gateway.pay(totalVnd);
    }
}

public class AbstractionDemo {
    public static void main(String[] args) {
        CheckoutService bankCheckout =
                new CheckoutService(new BankTransferGateway());
        CheckoutService walletCheckout =
                new CheckoutService(new WalletGateway());

        System.out.println(bankCheckout.checkout(120_000));
        System.out.println(walletCheckout.checkout(120_000));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac AbstractionDemo.java
java AbstractionDemo
```

Exact output:

```text
Receipt[provider=BankTransfer, amountVnd=120000, reference=BANK-001]
Receipt[provider=Wallet, amountVnd=120000, reference=WALLET-001]
```

**Role-by-role breakdown:**

- `PaymentGateway` states the **payment capability** through the `pay(long)` method. Consumers work through this type name and method.
- `BankTransferGateway` and `WalletGateway` are **two interchangeable implementations** of the same contract. Both must provide `pay(long)`.
- `Receipt` is the common result data, so the calling code does not have to understand two different response structures.
- `CheckoutService` holds a field of type `PaymentGateway`, receives the implementation through its constructor, and only calls the contract method. This is **constructor dependency injection** in plain Java.
- `main` selects the concrete implementation when wiring the objects together. The selection is placed where the application is assembled, separated from the `checkout` logic.
- When calling `gateway.pay(totalVnd)`, Java selects the method of the actual object being referenced (runtime polymorphism). **Abstraction** defines the common interface; **polymorphism** enables multiple implementations to respond to calls through that interface.

Key takeaway: replacing `new BankTransferGateway()` with `new WalletGateway()` at the initialization site lets you switch the payment method without modifying the source code of `CheckoutService`. This is useful when the business genuinely needs multiple implementations or needs to substitute components during testing.

## 4. What Does "Hiding Details" Mean, and What Does It Not Mean?

Abstraction **does not necessarily hide everything**. A good contract must publish enough information for the caller to use it correctly: currency unit, positive-amount requirement, return type, error conditions, synchronous/asynchronous behavior, side effects, and meaningful guarantees. In the example, `amountVnd` indicates the value is denominated in VND, `long` represents an integer, `Receipt` standardizes the output, and `IllegalArgumentException` is used for invalid amounts.

What is hidden from `CheckoutService` are decisions **unnecessary for the checkout business logic**: API calling protocol, provider authentication mechanism, digital signing method, retries, or converting JSON into Java objects. In a real implementation, these details must be implemented and tested separately.

An overly vague interface such as `execute(Object value)` is not a good abstraction merely because it is generic. Callers have a hard time knowing what data types are valid and what the result will be. Conversely, the name `pay(long amountVnd)` paired with a clear contract accurately conveys the component's capability.

## 5. Interfaces, Abstract Classes, and Regular Classes

| Java Construct | Common Role in Abstraction | What to Understand |
| --- | --- | --- |
| `interface` | Defines a shared **capability/contract** for implementations that may differ. | A class can `implements` multiple interfaces; an interface can also declare `default` and `static` methods. |
| `abstract class` | Defines a **base type** that can hold state, constructors, shared behavior, and abstract methods for subclasses to complete. | You cannot directly `new` an abstract class; a Java class can `extends` only one parent class. |
| Regular class with a public API | Exposes easy-to-use operations and hides details inside methods/private fields. | No need to create a separate interface if there is no reason for substitution or a useful dependency boundary yet. |

A short example of `abstract class` (component illustration snippet, without `main`):

```java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    public String color() {
        return color;
    }

    public abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(String color, double radius) {
        super(color);
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

The `Shape` type declares "every shape has a color and can compute its area," while sharing the `color` state. The `Circle` class decides the concrete formula. In the gateway problem, an `interface` fits because we mainly need a shared capability; there does not necessarily have to be shared state or a shared inheritance hierarchy among providers.

**Note the distinction:** `abstract class` and `interface` are not synonymous with the entire concept of "abstraction." They help declare boundaries; the quality of the boundary still depends on the problem and the designed contract.

## 6. How Does Abstraction Differ from Encapsulation and Polymorphism?

The three concepts are related, yet they answer different questions:

- **Abstraction:** what **does the consumer need to know and what can they request?** For example, `PaymentGateway.pay` is the shared capability.
- **Encapsulation:** **who is allowed to access or modify internal state/details?** For example, using `private` fields, providing appropriate public methods, and preserving object invariants.
- **Polymorphism:** **which object types can execute the same call?** For example, `PaymentGateway gateway` can reference a bank gateway or a wallet gateway.

A class with `private` fields can be well-encapsulated yet still have a poorly abstracted public API if it forces calling code to know too many technical details. Conversely, declaring an interface does not by itself guarantee that the data inside its implementations is properly encapsulated.

## 7. How Does Testing Become Simpler?

One of the clearest benefits is using a **test double**: providing a controlled substitute implementation to test the `CheckoutService` logic in isolation. Because `PaymentGateway` has only one abstract method, you can write a lambda like the following in a Java program that has the types from the example above:

```java
PaymentGateway fakeGateway =
        amount -> new Receipt("Fake", amount, "TEST-001");
CheckoutService service = new CheckoutService(fakeGateway);

Receipt receipt = service.checkout(500);
System.out.println(receipt.provider()); // Fake
```

This is an **illustrative snippet**, not a standalone file: place it inside a method where the declarations of `PaymentGateway`, `Receipt`, and `CheckoutService` already exist. The goal is to test the checkout flow without communicating with an external payment system. Note that this fake cannot replace integration tests that verify the real gateway works properly.

When multiple implementations rely on the same contract, you should test their shared behaviors: handling invalid amounts, the unit and meaning of the amount, consistency of the result data, and error rules. If two gateways return values that contradict the contract, substitutability is lost even though both compile successfully.

## 8. When Should You Create an Abstraction? When Is It Not Needed Yet?

**There is a solid case for creating an abstraction** when a capability has two or more reasonable ways to be implemented; when business logic needs to be decoupled from libraries, providers, or infrastructure; when dependencies need to be substituted during testing; or when there is a stable contract used by multiple components. An interface at the boundary of "paying," "sending notifications," or "reading data" is usually easy to explain because it maps to a clear capability.

**Creating an interface is not necessarily needed** if the program is very small, has only one implementation, has no need to decouple dependencies yet, or the contract name merely repeats the concrete class name without adding new meaning. Creating dozens of interfaces just so every class has a matching `I...Service` can increase the file count, lookup steps, and maintenance cost.

Avoid common mistakes:

1. **Premature abstraction:** anticipating many variants that do not yet exist, designing overly generic common methods, and then having to modify them continuously.
2. **Leaking provider details:** the interface returns concrete SDK objects, forcing every caller to still depend on that SDK.
3. **Vague contract:** failing to clearly specify data units, valid values, errors, `null`, side effects, or pre/postconditions.
4. **Forcing incompatible implementations into the same interface:** each class interprets `pay` differently, forcing callers to use `instanceof` or `if` to tell them apart.
5. **Confusing substitutability with being identical:** implementations may differ in how they work and in performance, yet must still respect the shared guarantees observable from the caller's side.
6. **Confusing abstraction with security:** hiding API details or using `private` does not replace access control, authentication, encryption, and secrets management.

A useful design test: **if implementation A is replaced with B, will the calling code continue working correctly without needing to know who B is?** If the answer is "yes" within the scope of the published guarantees, the abstraction boundary is useful.

## 9. Process for Applying This to a Real-World Problem

1. **Identify what the business logic needs to do.** For example, checkout needs to request a payment and receive a uniform result.
2. **Write a small, clear, and stable contract.** Define the method name, parameters, units, return value, errors, and necessary guarantees; do not copy an SDK's interface verbatim.
3. **Have consumer code depend on the contract.** Accept `PaymentGateway` via the constructor instead of instantiating the gateway inside the business logic.
4. **Build the concrete implementations.** Each gateway maps the contract to its corresponding technology or provider and respects the shared guarantees.
5. **Wire objects together at the configuration point.** In plain Java, you can use `new` in `main`; a DI framework can manage this creation/wiring automatically when needed.
6. **Test substitutability.** Run the same logic with two implementations, a test double, and the defined input/error cases.

**Check your understanding:**

- If `CheckoutService` still has to check `if (gateway instanceof WalletGateway)` to decide the processing flow, what might be missing or wrong with the abstraction boundary?
- If a system only needs to store a fixed string, what practical value does creating `StringProvider`, `DefaultStringProvider`, and a separate factory provide?
- If the `PaymentGateway` API returns `BankSdkResponse`, has the business logic truly been decoupled from the provider?

**Conclusion:** abstraction lets you program against **the required capabilities and contracts**, so each side can change its implementation details within the bounds of its commitments. The goal is not to add more classes/interfaces, but to create a boundary that makes consumer code easier to understand, easier to test, and less likely to change when the implementation changes.
