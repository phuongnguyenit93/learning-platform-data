# Choosing an Interface for a Shared Role Across Unrelated Classes

An interface enables classes with different inheritance hierarchies to fulfill a **shared role**. You choose an interface when you want a piece of code to work with a stable capability or contract, regardless of the object's actual class. For example, an invoice and a support ticket do not need to share a business superclass in order for both to provide a report line.

The core idea is: **the calling code depends on the role it needs, while each class takes responsibility for fulfilling that role**. An interface creates a clear boundary between what a consumer of the object can request and how each class satisfies that request.

## 1. An Interface Represents a Role, Not a Class Family

Suppose an application has the types **Invoice**, **SupportTicket**, and **UserAccount**. They model different concepts; forcing them to inherit from the same class just to share a single method can create a classification relationship that does not accurately reflect the business.

If multiple objects can provide a summary line to include in a report, describe that role with an interface:

~~~java
public interface Reportable {
    String reportLine();
}
~~~

The contract above states that every **Reportable** object must provide a report string. The interface does not specify how the string is constructed, what data is stored, or what methods of its own the implementing class has. Each class implements the contract according to its own data and rules.

An implementing class uses the **implements** keyword and must provide the required abstract methods:

~~~java
final class Invoice implements Reportable {
    @Override
    public String reportLine() {
        return "Invoice ...";
    }
}

final class SupportTicket implements Reportable {
    @Override
    public String reportLine() {
        return "Ticket ...";
    }
}
~~~

The snippet above illustrates the structure; the methods return fixed strings simply to show the signature. The complete runnable example in the next section will use each object's real data.

**Invoice** and **SupportTicket** do not need to inherit from each other or share a business superclass. They only commit to fulfilling the **Reportable** role together. Each class can still have its own constructors, fields, methods, and rules.

## 2. Runnable Java 17+ Example

Save the following content to a file named **ReportableDemo.java**. The example contains two independent domain classes and a service that only knows the interface.

~~~java
import java.util.List;

interface Reportable {
    String reportLine();
}

final class Invoice implements Reportable {
    private final String number;
    private final long totalCents;

    Invoice(String number, long totalCents) {
        this.number = number;
        this.totalCents = totalCents;
    }

    @Override
    public String reportLine() {
        return "Invoice " + number + ": " + totalCents + " cents";
    }
}

final class SupportTicket implements Reportable {
    private final int id;
    private final String status;

    SupportTicket(int id, String status) {
        this.id = id;
        this.status = status;
    }

    @Override
    public String reportLine() {
        return "Ticket #" + id + ": " + status;
    }
}

final class ReportPrinter {
    static void printAll(List<? extends Reportable> items) {
        for (Reportable item : items) {
            System.out.println(item.reportLine());
        }
    }
}

public class ReportableDemo {
    public static void main(String[] args) {
        List<Reportable> items = List.of(
            new Invoice("INV-42", 12_500L),
            new SupportTicket(17, "OPEN")
        );

        ReportPrinter.printAll(items);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac ReportableDemo.java
java ReportableDemo
~~~

Output:

~~~text
Invoice INV-42: 12500 cents
Ticket #17: OPEN
~~~

The key point lies in **ReportPrinter**: it does not need to check **instanceof Invoice**, **instanceof SupportTicket**, or cast to a concrete class. The loop simply calls **reportLine()** through the **Reportable** type. At runtime, Java selects the right implementation based on each object's actual class; that is polymorphism.

If **UserAccount implements Reportable** is added later, the report-printing service can still handle the new object without adding conditional branches or modifying **ReportPrinter**. This only holds true when the new class genuinely satisfies the meaning of the reporting contract.

## 3. Why Is This Approach Useful?

- **Reduces dependency on concrete classes.** The service only needs to know the provided capability, so implementation changes are less likely to propagate to the calling code.
- **Combines types from different inheritance branches.** A list or method can accept different classes as long as they share the same role.
- **Easy to extend.** A new class can join the contract without having to change every place where that contract is used.
- **Easy to test.** You can create a fake implementation of the interface to test the service without setting up the entire real system.
- **Allows a class to have multiple roles.** Java only allows a class to directly extend one parent class, yet a class can **implements** multiple interfaces. For instance, a type can be both **Reportable** and fulfill an **Exportable** role if both make sense for it.

An interface is therefore often useful at component boundaries: a service accepts a role, a repository provides a data-access contract, or a processor accepts objects that share a capability.

## 4. Choose a Contract That Is Small Enough and Meaningful

An interface name should clearly state the **role or capability** that the object commits to providing. Examples include **Reportable**, **Closeable**, **Comparable&lt;T&gt;**, or a business interface such as **Refundable**. Avoid overly generic names like **Common**, **Helper**, or **Data** if those names do not clarify the contract.

Before creating an interface, determine:

1. What action or information does the calling code need to request?
2. Can the intended implementing classes satisfy the same meaning for that method?
3. Is the method signature clear enough regarding parameters, return type, and error conditions?
4. Is it likely that multiple classes or components will need this role?
5. Can the contract remain stable when the implementation changes?

A good interface expresses what the caller has the right to expect. If **reportLine()** is specified to return a report line suitable for display to the user, every implementing class should fulfill that meaning. If one class returns an empty string while another returns an unrelated error message, they may be getting forced into an unsuitable contract.

You do not need to create an interface for every class. If there is currently only one implementation, no boundary needing substitution or polymorphism, and the contract does not yet have standalone value, a regular method can be simpler. Create an interface when it represents a meaningful role, supports substituting implementations, or helps reduce dependencies in the design.

## 5. Interface or Abstract Class?

| Need | Consider |
| --- | --- |
| Unrelated classes need to provide the same capability | Interface |
| Classes need a shared contract but have different implementations | Interface |
| Multiple classes share instance state, constructors, or foundational implementation code | Abstract class |
| Want a class to be able to combine multiple independent roles | Interface |
| Want to represent a classification relationship with shared state and behavior | An abstract class can be used, if that relationship fits the domain model |

An interface has no normal instance state and no constructors. Fields declared in an interface are **public static final** constants; abstract methods are **public** by default. An abstract class can hold instance fields, constructors, **protected** methods, and shared implementation. A class can extend one abstract class and implement multiple interfaces at the same time.

Do not choose an interface merely because "using an interface is always better." Choose based on the actual relationship and the responsibility to be represented. If two classes do not share state or an implementation foundation, yet share a capability, an interface is usually the appropriate boundary.

## 6. A Few Java Details to Keep in Mind

- **Method implementations must have sufficient accessibility.** Abstract methods in an interface are **public**, so the implementing method must be **public**; you cannot narrow it to package-private or **protected**.
- **An interface can extend another interface.** **interface AdvancedReportable extends Reportable** can add to the contract; a class implementing the subinterface must also satisfy all inherited abstract methods.
- **A class can implement multiple interfaces.** This makes it possible to combine independent roles, but you should not add an interface that the class cannot meaningfully fulfill.
- **Interfaces can have default and static methods.** **default** suits default behavior that makes general sense for all implementing classes; **static** belongs to the interface. Since Java 9, interfaces can also have **private** methods to share internal logic among the interface's own methods.
- **Be careful with multiple default methods sharing the same signature.** If a class inherits conflicting default implementations from multiple interfaces, that class must resolve the conflict by implementing the method itself.
- **An interface does not guarantee correct behavior on its own.** The compiler checks signatures, but designers and tests still have to ensure each class honors the meaning of the contract.

## 7. Common Design Mistakes

- **Using a superclass solely to group fundamentally unrelated classes.** If classes only share a single capability, forcing them into the same inheritance tree can distort the domain model. Consider a role-based interface.
- **Putting too many unrelated methods into a single interface.** A class that only needs part of the contract will be forced to implement methods that have no meaning for it. Split it into smaller interfaces by specific role.
- **Naming after implementation details.** A name like **UsesArrayList** ties the contract to how it is implemented. A name like **Reportable** expresses what the caller can do.
- **Checking concrete classes everywhere.** Many **instanceof** branches are often a sign that the code could work through a shared interface; however, only introduce an abstraction when the branches genuinely share a common meaning.
- **Using default methods to hide business differences.** A default implementation that is unsuitable for every class can make the contract hard to understand. Only share behavior when it is semantically valid.
- **Creating an interface just to rename a method.** Without a role, contract, substitution boundary, or polymorphism benefit, a new interface may simply increase the number of types to understand.

When reviewing a design, try asking: "If a new class unrelated to the existing classes is added with the same capability, can the calling code use it without knowing the concrete class?" If yes, a role-based interface may be the right contract. If the answer is no because the classes do not truly share the same meaning, adjust the contract instead of forcing them into the same interface.

## 8. Application Checklist

- [ ] The interface has a name that clearly expresses the shared role.
- [ ] Implementing classes genuinely satisfy the same meaning of the contract.
- [ ] Callers depend on the interface instead of casting to concrete classes.
- [ ] Methods have clear signatures, proper access levels, and suitable error descriptions.
- [ ] The interface does not bundle unrelated responsibilities.
- [ ] Abstractions are not created purely as a precaution without a concrete design benefit yet.
- [ ] Tests or runnable examples demonstrate that multiple unrelated classes are handled through the same contract.

Think of an interface as a meaningful commitment: classes may differ in their data and how they operate, yet all provide the exact role the caller needs.
