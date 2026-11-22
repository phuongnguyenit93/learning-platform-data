# Calling Abstract Methods from Default Methods in Java

A default method can define a common workflow but delegate a specific step to an abstract method provided by each implementing class. This pattern helps reuse an algorithm without tying the interface to a specific class.

## 1. Contract and Customization Points

```java
interface Greeter {
    String displayName();

    default String greet() {
        return "Xin chào, " + displayName();
    }
}
```

`displayName()` declares the contract; `greet()` provides the shared greeting. A default method is allowed to call an abstract method because that method belongs to the interface type. At runtime, the instance call is dispatched to the actual object's implementation.

## 2. Tracing the Execution Flow

```java
public class Main {
    interface Greeter {
        String displayName();

        default String greet() {
            return "Xin chào, " + displayName();
        }
    }

    static final class Employee implements Greeter {
        private final String name;

        Employee(String name) {
            this.name = name;
        }

        @Override
        public String displayName() {
            return name;
        }
    }

    static final class Guest implements Greeter {
        @Override
        public String displayName() {
            return "bạn";
        }
    }

    public static void main(String[] args) {
        Greeter employee = new Employee("An");
        Greeter guest = new Guest();

        System.out.println(employee.greet());
        System.out.println(guest.greet());
    }
}
```

Output:

```text
Xin chào, An
Xin chào, bạn
```

When `employee.greet()` is called, Java uses the default body of `Greeter` because `Employee` does not override `greet`. Inside that body, `displayName()` runs on the current object, so the result comes from `Employee.displayName()`. The `Guest` object goes through the same common workflow but returns a different name.

The compiler checks that `Greeter` declares `displayName()`. The JVM executes the implementation matching the actual object at runtime. `this` inside a default method refers to the implementing object receiving the call, not a separate instance of the interface.

## 3. Two Independent Decisions

If a class overrides `greet()`, the outer call will use that overridden body. When the chosen body in turn calls `displayName()`, the second call is still dispatched according to the object's actual implementation. Therefore, it is necessary to distinguish:

1. Which method provides the overall workflow: the default method or the class's override.
2. Which implementation provides each abstract step that the workflow calls.

This pattern is useful when multiple classes need the same workflow but differ in data or a processing step, such as formatting a message, generating a label, or determining a value by object type.

## 4. Keeping the Contract Clear Enough

A default method should rely on the operations that the interface exposes. If an abstract method can return `null`, throw an exception, or change state, the contract needs to explain how the default method handles those cases. A valid signature does not by itself guarantee that every implementation has the same semantics.

If an algorithm requires multiple state-changing operations that must run as a single transaction, do not assume that grouping them inside a default method will make them atomic. Let the class that owns the state provide an appropriate abstract operation.

## Self-Check

1. Why can `greet()` call `displayName()` even though the interface has no body for that method?
2. When `employee.greet()` runs, why is the name `An`?
3. If `Employee` overrides `greet()`, does `displayName()` automatically lose its polymorphism?
4. Why should a default method rely on the interface contract instead of casting to a specific class?

**Remember:** A default method defines the shared workflow; an abstract method is the extension point for the actual object to provide its own data or behavior. Dynamic dispatch determines which instance method implementation is called at each step.
