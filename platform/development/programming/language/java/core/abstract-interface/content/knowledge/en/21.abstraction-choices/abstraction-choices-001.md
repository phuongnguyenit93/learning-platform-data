# Comparing Abstract Classes and Interfaces by Design Goal

In Java, both `abstract class` and `interface` help describe the behaviors that a concrete class must provide. The core difference lies in the design goal: an **abstract class** is suitable when classes belonging to the same family need to share state, rules, and implementation; an **interface** is suitable when you want to define a role or capability that many different classes can take on.

The examples below use Java 17 or later.

## 1. Quick Comparison

| Criterion | Abstract class | Interface |
|---|---|---|
| Primary goal | Share an implementation foundation among classes related in the same family | Describe a contract or capability that a class can take on |
| Inheritance/implementation | A class can directly `extends` only one class | A class can `implements` multiple interfaces |
| Object state | Can have mutable or immutable instance fields | No instance fields; fields declared in an interface are `public static final` constants |
| Instantiation | Has constructors to set up shared state; cannot directly `new` an abstract class | Has no constructors and cannot instantiate an interface directly |
| Methods | Can have concrete, abstract, final, protected methods, and the access levels a class permits | Can have abstract, `default`, `static`, and `private` methods (private methods in interfaces since Java 9) |
| Access levels | Methods can be public, protected, package-private, or private depending on the purpose | The contract is exposed through public methods; private methods are only internal helpers inside the interface |
| Contract changes | Can add shared logic, state, or hooks; changes still require evaluating the impact on subclasses | Can add default methods to extend behavior, but conflicts and semantic changes must be considered |
| When appropriate | Template method, shared state and invariants, processing framework with parts required to be overridden | Independent roles, capabilities, open APIs for multiple implementation types, combining multiple contracts |

You should not choose based solely on whether there are implemented methods or not. Modern interfaces can contain `default` and `static` methods; an abstract class can have no state. Start from the relationships and responsibilities that the model needs to express.

## 2. Choose an Abstract Class When You Need a Shared Foundation

An abstract class is useful when subclasses genuinely belong to the same family and need to share data or rules that should not be duplicated. It can:

- Hold object state using instance fields.
- Initialize and validate state through constructors.
- Provide shared methods so subclasses do not reimplement them.
- Declare abstract methods as mandatory extension points.
- Lock down part of the rules with `final` methods, while allowing subclasses to customize steps designed for extension.

For example, document types that share an identifier, validation rules, and lifecycle can inherit from a base class `Document`. The base class holds the identifier and validates data once; each document type defines how to render its content.

This pattern usually makes sense when the relationship is “is a kind of” and classes need to inherit a substantive part of the implementation. Do not create an abstract class just to group utility methods that lack a clear modeling relationship.

### Template Method

An abstract class can also hold the order of steps in an algorithm while delegating specific work to abstract methods or protected hooks. If that order is an invariant, a coordinating method can be `final` so subclasses do not accidentally break the workflow. Only use this approach when the common steps truly belong to a stable workflow.

## 3. Choose an Interface When You Need to Describe a Role or Capability

An interface is suitable when callers only need to know what an object **can do**, without needing to know how the object is built or which inheritance hierarchy it belongs to.

For example, `Comparable<T>`, `Runnable`, and `AutoCloseable` describe different contracts. Classes that do not share a superclass can still implement the same interface. A class can simultaneously take on multiple roles, such as both having a name and being able to export data.

Prefer an interface when:

- You want an API to accept different implementations without depending on a concrete class.
- You want to combine multiple capabilities on the same class.
- You want implementations to be easy to swap in tests or application configuration.
- You want to define a contract at the boundary between modules or components.
- You do not need to store shared instance state or force every implementation to share a base algorithm.

An interface can provide `default` methods when there is a reasonable default behavior for all or most implementations. However, `default` methods cannot replace instance state, constructors, or all the needs of a base class.

## 4. Limitations and Rules to Remember

**Java allows a class to directly inherit from only one other class.** Therefore, if a class already `extends` an abstract class, it cannot add a second superclass to get shared code. It can still `implements` multiple interfaces.

**An interface cannot `extends` a class.** An interface can `extends` one or more other interfaces; a class can `extends` one class and `implements` multiple interfaces.

**Interface fields are constants.** Fields declared in an interface are implicitly `public static final`. Do not use interfaces to store per-object state. If implementations need their own state, keep that state in the class or a collaborating object.

**An abstract class can contain constructors, but cannot be instantiated directly.** Its constructor runs when a subclass is instantiated and helps ensure shared state is valid. Concrete subclasses must implement any remaining abstract methods.

**Interface methods are not always abstract.** An interface can declare abstract methods, `default` methods, `static` methods, and private helper methods. However, public contract methods still need to be implemented appropriately by concrete classes.

**Default methods can cause conflicts.** If a class inherits two unrelated interfaces with the same default method, the class usually has to override it to decide the behavior. A matching instance method in a superclass also has higher precedence than an interface's default method. Therefore, adding a default method to a public API requires considering existing implementations.

**Abstract classes and interfaces are not mutually exclusive.** An abstract class can `implements` one or more interfaces. This is often a good design: the interface expresses the contract, while the abstract class provides a base implementation for classes that want to reuse it.

## 5. Complete Java Example

In this example, `Named` describes the naming capability, `Exportable` describes the ability to export data, and the abstract class `Task` holds the shared state and rules of a task. `BuildTask` inherits the foundation from `Task` and also implements `Exportable`.

Save as `DesignChoiceDemo.java`:

~~~java
interface Named {
    String name();

    default String label() {
        return name().trim();
    }
}

interface Exportable {
    String export();
}

abstract class Task implements Named {
    private final String name;

    protected Task(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name.trim();
    }

    @Override
    public final String name() {
        return name;
    }

    public abstract String execute();
}

final class BuildTask extends Task implements Exportable {
    private final int steps;

    BuildTask(String name, int steps) {
        super(name);
        if (steps < 0) {
            throw new IllegalArgumentException("steps must be non-negative");
        }
        this.steps = steps;
    }

    @Override
    public String execute() {
        return "Built " + name() + " in " + steps + " steps";
    }

    @Override
    public String export() {
        return name() + "," + steps;
    }
}

public class DesignChoiceDemo {
    public static void main(String[] args) {
        Task task = new BuildTask("Java", 3);

        System.out.println(task.label());
        System.out.println(task.execute());

        Exportable exportable = (Exportable) task;
        System.out.println(exportable.export());
    }
}
~~~

Compile and run:

~~~text
javac DesignChoiceDemo.java
java DesignChoiceDemo
~~~

Exact stdout:

~~~text
Java
Built Java in 3 steps
Java,3
~~~

The example shows that each type has a distinct responsibility:

- `Task` holds the `name` state, validates input data, provides `name()`, and requires subclasses to implement `execute()`.
- `Named` describes the naming contract and provides a default way to generate a label without storing its own state.
- `Exportable` allows callers to export data without needing to know the concrete class is `BuildTask`.
- `BuildTask` combines a base class with an additional capability. Callers can work through the `Task` or `Exportable` type depending on their goal.

The cast in the example is safe because the actual object is a `BuildTask`, which implements `Exportable`. In application code, if you are not certain the object has that capability, accept an `Exportable` reference from where the object is created or check the type before casting.

## 6. Common Design Choices

| Need | Typically suitable choice | Reason |
|---|---|---|
| Multiple implementations not in the same inheritance hierarchy that need the same contract | Interface | Does not force them to share a superclass |
| Subclasses need the same state and constructors to enforce invariants | Abstract class | Keeps shared state and rules in one place |
| A class needs to fulfill multiple independent roles | Multiple interfaces | Java allows a class to implement multiple interfaces |
| Want to share a skeleton algorithm with a few customizable steps | Abstract class | Can hold the processing order and define hooks |
| Only want to define an API so calling code does not depend on the implementation | Interface | Decouples the contract from concrete classes |
| Want to provide small default behavior for a capability | Interface with default methods | Allows implementations to inherit behavior if they do not need to override it |
| Want to reuse code without a reasonable “is a kind of” relationship | Prefer composition | Collaborating objects usually avoid rigid dependency on an inheritance hierarchy |

## 7. Composition Is the Third Option

Not all shared code should be placed in an abstract class. If two classes only need to share a service or algorithm without belonging to the same conceptual family, consider composition: extract that logic into a separate object and pass or inject it where needed.

Composition makes it easier to change behavior at runtime, avoids Java's single-inheritance limitation, and reduces dependency on superclass details. In return, it may require an extra object or collaborating class; choose based on actual complexity rather than creating abstractions prematurely.

For example, different notification types can share a `Formatter` through composition, whereas task types that genuinely share state and invariants may reasonably inherit from `Task`.

## 8. Decision Process

1. Identify what calling code needs to know: a contract/capability or a stateful implementation foundation.
2. If multiple classes need the same data, constructors, invariants, or a template method, consider an abstract class.
3. If different types need the same role, or one class needs multiple roles, prefer interfaces.
4. If you only want to reuse logic between classes not in the same family, consider composition.
5. Check extensibility: Java allows only one superclass; interfaces allow combining multiple contracts, though default methods can conflict.
6. Have calling code depend on an interface when it benefits implementation substitutability; depend on an abstract class only when its base behavior is truly an essential part of the design.
7. Write a small example and check constructors, substitutability, error cases, and behavior when adding a new implementation.

There is no rule that an interface is always better or an abstract class is always stronger. Good design chooses the abstraction that accurately expresses the goal, keeps responsibilities clear, and does not lock implementations into an unnecessary inheritance relationship.
