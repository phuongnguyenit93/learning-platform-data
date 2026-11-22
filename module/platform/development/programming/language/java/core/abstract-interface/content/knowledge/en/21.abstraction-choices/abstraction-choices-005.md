# Trade-offs between implementation inheritance and composition, delegation

When multiple types share common behavior, Java allows code reuse through **implementation inheritance** or through **composition combined with delegation**. Both can reduce duplication, but they create different coupling between components. Choosing the right approach depends on the domain relationship, the extent to which behavior needs to change, and the stability of the reused implementation.

- **Implementation inheritance:** a subclass inherits existing state and methods from a superclass and can reuse or override behavior.
- **Composition:** an object contains or holds a reference to another object to compose its behavior.
- **Delegation:** an object forwards part of its work to an object it holds a reference to. Delegation is typically how composition uses the internal component.

Composition and delegation often appear together: the outer object holds a formatter, logger, or policy and delegates the corresponding task to that component.

## 1. Implementation inheritance: reusing through a superclass

A base class can provide a common workflow, while a subclass customizes a step through an abstract method or by overriding an existing method. For example, a notification class can hold the message preparation workflow, while a subclass defines how to format the content.

Advantages:

- Shared code resides in one place; subclasses can directly inherit accessible methods and state.
- The model is clear when the relationship is genuinely a specialization of the base type.
- Template Method can fix the processing sequence in the superclass and allow subclasses to customize defined steps.

Trade-offs:

- The relationship between subclass and superclass is quite tight. Changing an inherited method can affect every subclass, including ones that depend on implicit implementation details.
- A subclass is typically bound to a single superclass. Java does not support implementation inheritance from multiple classes.
- Overriding can break superclass assumptions if the contract is not clearly designed. Protected methods and mutable state can also create many hard-to-spot dependencies.
- Behavior is chosen primarily through the subclass type; changing a policy per object often requires additional subclasses or conditional structures.

Implementation inheritance is useful when types truly share a stable base concept, and the superclass can define a consistent contract for all subclasses.

## 2. Composition and delegation: assembling behavior from components

With composition, the outer object holds another object as a component. Instead of inheriting how formatting is done from a superclass, a notification preparer can hold an object implementing the MessageFormatter interface and delegate formatting to it.

Advantages:

- Coupling is usually looser: the outer object depends on a small interface rather than a concrete implementation class.
- Components can be chosen at object instantiation, which is convenient for configuration, dependency injection, and testing with fakes or stubs.
- Multiple independent behaviors—such as a formatter, retry policy, logger, and transport—can be combined without creating a large inheritance hierarchy.
- A component can be reused across classes that have no inheritance relationship with one another.

Trade-offs:

- Component dependencies must be declared and passed in; an object may have more fields and constructors.
- Delegation can introduce extra forwarding methods. If the outer class merely repeats the component's entire API, it can become a redundant wrapper.
- It is necessary to clearly decide who owns the component's lifecycle, configuration, and error handling.
- Composition does not automatically guarantee good design: if an object holds too many dependencies or coordinates too much work, it can still become difficult to maintain.

Composition is suitable when an object needs a replaceable capability, when capabilities vary independently, or when there is no natural "is-a" relationship between the outer object and the component.

## 3. Java 17+ example: same goal, two ways to organize

The program below builds messages in two ways. In the inheritance branch, the subclass supplies the formatting step for the common workflow in the superclass. In the composition branch, the Notifier class holds a MessageFormatter and delegates the formatting step to it.

Save the entire code in the file **NotifierDemo.java**:

~~~java
import java.util.Objects;

interface MessageFormatter {
    String format(String recipient, String message);
}

// Option 1: implementation inheritance.
abstract class InheritanceNotifier {
    protected abstract String format(String recipient, String message);

    public final String prepare(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");
        return "SEND " + format(recipient, message);
    }
}

final class PlainTextInheritanceNotifier extends InheritanceNotifier {
    @Override
    protected String format(String recipient, String message) {
        return "to=" + recipient + "; body=" + message;
    }
}

// Option 2: composition and delegation through an interface.
final class PlainTextFormatter implements MessageFormatter {
    @Override
    public String format(String recipient, String message) {
        return "to=" + recipient + "; body=" + message;
    }
}

final class BracketFormatter implements MessageFormatter {
    @Override
    public String format(String recipient, String message) {
        return "[" + recipient + "] " + message;
    }
}

final class ComposedNotifier {
    private final MessageFormatter formatter;

    public ComposedNotifier(MessageFormatter formatter) {
        this.formatter = Objects.requireNonNull(formatter, "formatter");
    }

    public String prepare(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");
        // Delegate formatting to the injected component.
        return "SEND " + formatter.format(recipient, message);
    }
}

public class NotifierDemo {
    public static void main(String[] args) {
        InheritanceNotifier inherited = new PlainTextInheritanceNotifier();
        System.out.println("Inheritance: "
                + inherited.prepare("alice", "hello"));

        ComposedNotifier plain = new ComposedNotifier(new PlainTextFormatter());
        System.out.println("Composition: "
                + plain.prepare("alice", "hello"));

        ComposedNotifier bracket = new ComposedNotifier(new BracketFormatter());
        System.out.println("Swapped formatter: "
                + bracket.prepare("bob", "welcome"));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac NotifierDemo.java
java NotifierDemo
~~~

Exact stdout:

~~~text
Inheritance: SEND to=alice; body=hello
Composition: SEND to=alice; body=hello
Swapped formatter: SEND [bob] welcome
~~~

The first two lines produce the same output format but go through two different structures. With inheritance, a dedicated subclass must be created for the implementation variant. With composition, another ComposedNotifier can be created and given a BracketFormatter without creating a new subclass of Notifier. The formatter component is chosen at instantiation; if it needs to change later, design an explicit configuration or replacement mechanism instead of implicitly making the object mutable.

The example is intentionally kept simple to clarify the relationships between types. In a real application, the workflow for preparing and sending notifications may require address validation, error handling, encryption, logging, and network calls. Those responsibilities should be separated along appropriate contracts and boundaries, rather than putting everything into a single base class or a large coordinator class.

## 4. How does delegation differ from inheritance?

In inheritance, a subclass object is also an instance of the superclass; it inherits the API and can use the inherited methods. The subclass can override methods to change behavior polymorphically.

In delegation, the outer object holds a reference to a collaborator object and calls its methods. The outer object does not automatically acquire the component's entire API. It decides what is exposed externally and can add orchestration, validation, or coordination across multiple components.

An interface is often a useful boundary for delegation because callers depend only on the contract. However, an interface does not have to be used with composition; a class can implement an interface through inheritance, through its own logic, or by delegating.

## 5. Trade-offs comparison table

| Criterion | Implementation inheritance | Composition and delegation |
|---|---|---|
| Relationship | Subclass is a kind of superclass | Object has or uses a component |
| Reuse | Inherits methods and state | Invokes the component's behavior |
| Combining multiple behaviors | Limited to a single superclass; easily produces large class hierarchies | Can hold multiple independent components |
| Changing behavior | Usually via overriding or another subclass | Usually via supplying a different implementation |
| Coupling level | Can be tight to superclass details | Can be looser if depending on an interface |
| Complexity | Less wiring code initially, but the class hierarchy can bloat | Adds constructors and collaborator objects, but boundaries are clearer |
| Testing | May require creating a subclass or testing the base class as well | Can inject fakes/stubs via an interface |
| Suitable when | There is a genuine specialization relationship and a stable base contract | Behavior needs to be replaceable, combined, or changed independently |

Neither approach is always better. Composition does not eliminate every cost, and inheritance is not always bad design. Evaluate the stability of the contract, the number of variants, the potential need to coordinate behaviors, and the degree of coupling that future changes could create.

## 6. Common design mistakes

- **Using inheritance just to get a utility method.** If the "is-a" relationship makes no sense in the domain, consider an appropriate component or utility method.
- **Creating a subclass for every combination of behaviors.** When the number of classes grows as the product of multiple independent choices, consider composing components instead of building an inheritance hierarchy for each combination.
- **Letting subclasses depend on internal details of the superclass.** Too much protected state or methods that call one another make changing the superclass risky.
- **Mechanically delegating the entire API.** Only expose the operations that the outer object actually needs to provide; if it has no responsibility beyond forwarding, consider using the component directly.
- **Hiding dependencies by instantiating them internally.** When a class creates a concrete implementation itself, replacement or testing is often harder. Pass dependencies through the constructor when configuration and replacement are real requirements.
- **Confusing composition with absolute lifecycle ownership.** A reference to a component does not by itself determine who owns a resource or when it is closed. Lifecycle rules need to be clearly defined, especially for files, connections, and threads.

## 7. Process for choosing a solution

1. Identify which parts of the behavior are genuinely the same and which parts are likely to change independently.
2. If the types have a natural specialization relationship and need a stable common workflow, consider a base class with a clear contract.
3. If the behavior is a replaceable policy or service, define a small interface and use composition and delegation.
4. Avoid letting subclasses rely on unguaranteed internal details of the superclass; avoid letting a coordinator class become a wrapper with no responsibilities.
5. Test both common behavior and variants: identical inputs produce the expected results, swapping implementations does not alter the contract, and component errors are handled according to the defined policy.

Implementation inheritance reuses code through a relatively tight type relationship. Composition and delegation reuse code by assembling collaborators through contracts. Choose based on the relationship and how the system needs to change, and keep the contract small enough that replacing an implementation does not propagate changes to the rest of the system.
