# Resolving the Diamond Problem with Multiple Interfaces

In Java, a class can `extends` only one superclass, but it can `implements` multiple interfaces. This allows an object to have multiple roles and multiple type contracts. However, when interfaces form a diamond inheritance graph and each branch provides a `default method` with the same signature but a different implementation, the class at the bottom of the diamond must decide which behavior is correct.

That is the **diamond problem**. Java allows multiple inheritance of types through interfaces, yet it does not arbitrarily choose between two conflicting default methods. The compiler requires the class to resolve the ambiguity at compile time.

## 1. Identifying the Diamond Structure

Consider a device that has both a network connectivity role and a storage role:

~~~text
                 Device
                /      \
       NetworkDevice   StorageDevice
                \      /
                SmartDevice
~~~

- `Device` is the common interface.
- `NetworkDevice` and `StorageDevice` both extend `Device`.
- `SmartDevice` implements both branches to provide two roles for the same object.

If `Device` declares a default method named `status()`, both branches can inherit that method. In that case, they are using the same original implementation, so there are not two different implementations to choose from. A true conflict occurs when each branch **overrides** `status()` with its own meaning:

~~~java
interface NetworkDevice extends Device {
    @Override
    default String status() {
        return "network";
    }
}

interface StorageDevice extends Device {
    @Override
    default String status() {
        return "storage";
    }
}
~~~

If `SmartDevice` implements both `NetworkDevice` and `StorageDevice` without overriding `status()`, Java does not know which implementation to inherit. The result is a compile-time error, not a random choice at runtime.

## 2. Rules Java Uses to Resolve Conflicts

When multiple interfaces provide methods with the same signature, consider them in the following order:

1. **A class's concrete instance method takes precedence over an interface's default method.** If the superclass is a class with a matching concrete method, that method takes precedence according to Java's resolution rules.
2. **A more specific interface takes precedence over a superinterface.** If a subinterface overrides a superinterface's default method, a class implementing the subinterface receives the more specific version, provided there is no other conflict between unrelated branches.
3. **Two conflicting default methods from interfaces with no specific inheritance relationship must be overridden by the implementing class.** The class can define new behavior itself or explicitly invoke the desired implementations using the `InterfaceName.super.method()` syntax.
4. **Abstract methods with identical signatures can usually be implemented by a single method.** If the declarations are incompatible—for example, if return types cannot be satisfied simultaneously—the program will not compile.
5. **Do not rely on the order in which interfaces are listed in `implements`.** Changing `implements A, B` to `implements B, A` is not a way to resolve a conflict.

It is important to distinguish two cases: inheriting the same default method from an ancestor interface does not necessarily cause ambiguity; only when two branches override that method with different implementations does it create a conflict that needs to be resolved.

## 3. How to Write a Class That Resolves the Conflict

There are two common options:

- **Redefine the behavior yourself** when the combining class has its own rules. This is often the clearest choice if the object's behavior is not simply one of the two branches.
- **Explicitly invoke each interface's implementation** using `NetworkDevice.super.status()` or `StorageDevice.super.status()` when you want to reuse existing logic.

The `InterfaceName.super.method()` syntax is used only to call a default method from a direct interface that the class implements. In the example, `NetworkDevice` and `StorageDevice` are direct interfaces of `SmartDevice`, so those calls are valid. You cannot use `Device.super.status()` here to bypass the intermediate branches, because `Device` is not a direct interface implemented by `SmartDevice`.

Combining both implementations is not mandatory. The class can return a combined status, choose one branch based on business rules, or provide a new definition — as long as that decision is clear and consistent with the public contract.

## 4. Complete, Runnable Java Example

Save all of the following code into a file named `InterfaceDiamondDemo.java`. The example uses three interfaces and one class that implements both branches. `SmartDevice` resolves the `status()` conflict by explicitly calling each interface's default method; at the same time, it implements the abstract methods for the network ID and storage capacity.

~~~java
import java.util.Objects;

interface Device {
    default String status() {
        return "generic";
    }
}

interface NetworkDevice extends Device {
    @Override
    default String status() {
        return "network";
    }

    String networkId();
}

interface StorageDevice extends Device {
    @Override
    default String status() {
        return "storage";
    }

    long capacityGb();
}

final class SmartDevice implements NetworkDevice, StorageDevice {
    private final String networkId;
    private final long capacityGb;

    SmartDevice(String networkId, long capacityGb) {
        this.networkId = Objects.requireNonNull(networkId, "networkId");
        if (capacityGb <= 0) {
            throw new IllegalArgumentException("capacityGb must be positive");
        }
        this.capacityGb = capacityGb;
    }

    @Override
    public String status() {
        return NetworkDevice.super.status() + "+" + StorageDevice.super.status();
    }

    @Override
    public String networkId() {
        return networkId;
    }

    @Override
    public long capacityGb() {
        return capacityGb;
    }
}

public class InterfaceDiamondDemo {
    public static void main(String[] args) {
        SmartDevice smart = new SmartDevice("net-7", 512);

        Device device = smart;
        NetworkDevice network = smart;
        StorageDevice storage = smart;

        System.out.println("status=" + device.status());
        System.out.println("networkId=" + network.networkId());
        System.out.println("capacityGb=" + storage.capacityGb());
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac InterfaceDiamondDemo.java
java InterfaceDiamondDemo
~~~

Exact output:

~~~text
status=network+storage
networkId=net-7
capacityGb=512
~~~

### Reading the Output

- The variable `device` has reference type `Device`, but the actual object is a `SmartDevice`. The call `device.status()` dispatches to the overriding method in `SmartDevice`, so the result is `network+storage`.
- The variable `network` has reference type `NetworkDevice`; it can call `networkId()` because that method belongs to this interface's contract.
- The variable `storage` has reference type `StorageDevice`; it can call `capacityGb()`.
- The same object implements multiple interfaces without needing multiple class inheritance. Each interface represents one role, while the concrete class combines those roles.

The constructor also validates its inputs: the network ID must not be null, and the capacity must be positive. These checks are rules of the object, not the mechanism for resolving the diamond problem, but they illustrate where the concrete class is responsible for protecting invariants.

## 5. Seeing the Error Before Fixing It

If you omit the `status()` override from `SmartDevice` while keeping the implementations of `networkId()` and `capacityGb()`, the following structure will not compile:

~~~java
final class AmbiguousDevice implements NetworkDevice, StorageDevice {
    @Override
    public String networkId() {
        return "net-7";
    }

    @Override
    public long capacityGb() {
        return 512;
    }

    // Missing status() override:
    // two unrelated default methods both provide status().
}
~~~

The compiler reports that the class inherits unrelated default methods with the same signature `status()`. The fix is not to cast the object at the call site, reorder the interfaces, or choose using an external `if/else`. You need to define `status()` explicitly inside the implementing class (or redesign the interfaces if the two contracts should not conflict in the first place).

## 6. Related Cases to Distinguish

### A Subinterface Overrides a Superinterface

If `FastNetworkDevice` extends `NetworkDevice` and overrides `status()`, the subinterface's implementation is more specific than the one inherited from `NetworkDevice`. When a class inherits only non-conflicting inheritance paths, Java gives precedence to the method from the more specific interface.

### A Superclass Already Has a Concrete Method

If the implementing class extends a class that has a concrete instance method matching the signature, the class's method takes precedence over the default method. This ensures that an interface's default method does not arbitrarily replace existing behavior of the superclass.

### Two Interfaces Only Declare the Same Abstract Method

If two interfaces declare a compatible abstract method, the class usually only needs to implement it once to satisfy both contracts. There are no two competing default implementations to choose between. However, the return type, visibility, and signature constraints must still be valid in Java.

### Interface Static Methods

A static method belongs to the interface that declares it and is called using the interface name, for example `Device.someUtility()` if that method is declared in `Device`. Static method conflicts are not handled like default method conflicts; static methods are not inherited and overridden via instance polymorphism.

## 7. Common Mistakes and How to Avoid Them

- **Assuming Java forbids multiple interfaces:** Java allows a class to implement multiple interfaces. The single-superclass limit applies to class inheritance, not the number of interfaces.
- **Assuming every diamond is an error:** if the branches inherit the same original implementation without overriding it differently, there is not necessarily a conflict.
- **Forgetting to override when two default methods differ:** the error occurs at compile time. Resolve it in the combining class so the behavior is transparent.
- **Calling `Device.super.status()` from a class that does not directly implement `Device`:** call the default method through the appropriate direct interface instead, or write the combined behavior yourself.
- **Using multiple interfaces just to create a diamond:** an inheritance structure does not create value on its own. Each interface should represent a meaningful contract or role, such as connectivity and storage.
- **Using the same method name for two different meanings:** if two interfaces use `status()` with incompatible semantics, consider renaming, separating responsibilities, or using an adapter instead of forcing every combining class to resolve the same conflict.
- **Using default methods for object state:** interfaces do not carry instance state like classes do. Object-specific data should be kept in the implementing class or an appropriate collaborator.

## 8. Design Principles for Multiple Interfaces

Each interface should describe a clear, highly cohesive contract. A class can implement multiple interfaces to combine independent capabilities, but you should not split interfaces mechanically just to have a large number of them.

When designing APIs with default methods, choose sufficiently specific names and semantics, consider the impact when interfaces are combined, and override explicitly if default methods may conflict. In the implementing class, decide the combined behavior in one place rather than leaving clients to choose on their own or cast to individual branches.

**In summary:** Java supports multiple inheritance of types through interfaces, yet requires behavior to be disambiguated when multiple incompatible default methods appear together. Identify which branch owns the contract, understand Java's precedence rules, and then override in the combining class or explicitly call an implementation using `InterfaceName.super.method()`.
