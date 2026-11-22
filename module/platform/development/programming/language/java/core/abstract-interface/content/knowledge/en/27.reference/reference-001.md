# Comparison table of abstract class, interface, and concrete class in Java

In Java, an **interface**, an **abstract class**, and a **concrete class** address different needs when designing data types. An interface describes a contract that types can provide; an abstract class is a base class that can share state and behavior; a concrete class is a class complete enough to create objects directly.

These three concepts are not mutually exclusive choices. A concrete class can extend an abstract class and simultaneously implement one or more interfaces. To make the right choice, consider which part needs to be promised in a contract, which part needs to share code and state, and which type needs to be instantiated into an object.

## 1. Quick comparison table

| Criterion | Interface | Abstract class | Concrete class |
|---|---|---|---|
| Primary purpose | Defines a contract or capability that a type provides | Shares a common foundation and behavior among related classes | Provides a type that can be instantiated and used |
| Can `new` be used directly? | No | No | Yes, if the constructor and access level allow |
| Declaring abstract methods | Can declare methods without a body | Can declare methods without a body | Cannot have unimplemented abstract methods remaining |
| Methods with a body | Has `default`, `static`, and `private` methods per Java rules | Can have regular methods and `static` methods | Can have regular methods and `static` methods |
| Object state | No instance fields; interface fields are implicitly `public static final` | Can have instance fields and constructors | Can have instance fields and constructors |
| Inheritance / implementation | An interface can `extends` multiple interfaces; a class uses `implements` | A class can `extends` one parent class, and an abstract class can `implements` interfaces | Can `extends` one class and `implements` multiple interfaces |
| When is it useful? | Different classes need to commit to the same behavior | Classes share common data, initialization rules, or logic | A complete type is needed to create and use objects |

Key takeaway: **an interface states what a type can do; an abstract class can provide a shared foundation; a concrete class provides an implementation from which objects can be created**. This is a quick way to remember it, while the actual decision depends on the specific design.

## 2. Interface: capability contract

An interface declares the methods that an implementing type needs to provide. Classes do not need to share the same parent class to implement the same interface. This is useful when many different kinds of objects share a capability, such as payment, logging, sorting, or providing an identifier.

~~~java
interface Payable {
    double monthlyPay();
}
~~~

A class that implements `Payable` must provide the `monthlyPay()` method, unless the class itself is abstract. The caller can work with the `Payable` type without needing to know which class the object belongs to.

~~~java
final class Contractor implements Payable {
    private final double hourlyRate;
    private final int hours;

    Contractor(double hourlyRate, int hours) {
        this.hourlyRate = hourlyRate;
        this.hours = hours;
    }

    @Override
    public double monthlyPay() {
        return hourlyRate * hours;
    }
}
~~~

An interface can also have `default` methods with a default implementation, `static` methods belonging to the interface, and `private` methods to support reusing internal logic among methods within the interface. However, an interface is not meant to hold state specific to each instance. Fields declared in an interface are always `public static final` constants under Java semantics.

A class can implement multiple interfaces:

~~~java
final class Invoice implements Payable, Comparable<Invoice> {
    // Provide the required methods of both interfaces.
}
~~~

The snippet above only illustrates syntax and is not a complete class, because a real class needs to declare data and implement all remaining abstract methods. The key point is that Java allows a class to fulfill multiple interface contracts, whereas a class can only have a single direct parent class.

**Choose an interface when** you need to publish a stable contract, want multiple independent kinds of classes to provide the same capability, or want to make implementations easy to swap in tests and application configuration.

## 3. Abstract class: a base class that can share state and behavior

An abstract class is declared using the `abstract` keyword. It cannot be instantiated directly, but it can contain constructors, instance fields, implemented methods, and abstract methods. A concrete subclass extending it must implement any remaining abstract methods.

~~~java
abstract class Employee {
    private final String name;

    protected Employee(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String role();

    public String summary() {
        return name + " (" + role() + ")";
    }
}
~~~

In this example, the abstract class holds the employee's name and implements the shared behavior `summary()`. The `role()` method is left abstract because each type of employee may have a different role. The constructor helps ensure that subclasses initialize the shared state following the same rules.

A subclass can inherit the shared part and complete the missing parts:

~~~java
final class SalariedEmployee extends Employee {
    private final double salary;

    SalariedEmployee(String name, double salary) {
        super(name);
        this.salary = salary;
    }

    @Override
    public String role() {
        return "Engineer";
    }

    public double salary() {
        return salary;
    }
}
~~~

`SalariedEmployee` is a concrete class because it has implemented `role()` and has no unresolved abstract methods remaining. You can create a `SalariedEmployee` object, but you cannot write `new Employee(...)` while `Employee` remains an abstract class.

An abstract class can also implement an interface. For example, if `Employee` implements `Payable`, it can leave `monthlyPay()` abstract so that each subclass calculates pay on its own. In that case, the abstract class both provides shared state and serves as a bridge layer between the interface contract and concrete implementations.

**Choose an abstract class when** classes have a logical inheritance relationship and need to share state, constructors, invariants, or common behavior. Do not create an abstract class just to group unrelated methods; an interface is usually more appropriate for an independent capability.

## 4. Concrete class: a type that can be instantiated

A concrete class is a class not declared as `abstract` that has implemented all required abstract methods. If the class has an accessible constructor, the program can create instances of it with `new`.

Being a concrete class does not mean the class must be declared `final`. A concrete class can still be extended unless another modifier or constraint forbids inheritance. A `final class` is a concrete class that does not allow other classes to extend it.

~~~java
final class FixedContractor implements Payable {
    private final String name;
    private final double monthlyAmount;

    FixedContractor(String name, double monthlyAmount) {
        this.name = name;
        this.monthlyAmount = monthlyAmount;
    }

    public String name() {
        return name;
    }

    @Override
    public double monthlyPay() {
        return monthlyAmount;
    }
}
~~~

This class does not extend any abstract class, yet it still implements the `Payable` interface and can be instantiated. It also illustrates that classes unrelated in the inheritance hierarchy can still be handled uniformly through an interface.

A concrete class can simultaneously extend an abstract class and implement an interface:

~~~java
final class SalariedEmployee extends Employee implements Payable {
    // Complete the abstract methods of Employee and Payable.
}
~~~

This is a structural illustration; in a complete program, if both types require the same method signature, a single matching implementation can satisfy both contracts. If the contracts have conflicting signatures or return types, the design needs to be adjusted to comply with Java's compatibility rules.

## 5. Complete runnable example on Java 17

The program below uses all three concepts. `Payable` defines the pay calculation contract; `Employee` is an abstract class holding the name and shared behavior; `SalariedEmployee` is a concrete class extending that foundation. `Contractor` is a standalone concrete class that only implements the interface, showing that types not in the same inheritance tree can still share a contract.

Save the entire code into the file `TypeComparisonDemo.java`:

~~~java
public class TypeComparisonDemo {
    public static void main(String[] args) {
        Employee employee = new SalariedEmployee("Lan", 3000.0);
        Payable[] payables = {
            employee,
            new Contractor("Minh", 30.0, 40)
        };

        System.out.println("EMPLOYEE: " + employee.summary());

        for (Payable payable : payables) {
            System.out.printf(java.util.Locale.ROOT,
                    "PAY: %.2f%n", payable.monthlyPay());
        }
    }
}

interface Payable {
    double monthlyPay();
}

abstract class Employee implements Payable {
    private final String name;

    protected Employee(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String role();

    public String summary() {
        return name + " (" + role() + ")";
    }
}

final class SalariedEmployee extends Employee {
    private final double salary;

    SalariedEmployee(String name, double salary) {
        super(name);
        this.salary = salary;
    }

    @Override
    public String role() {
        return "Engineer";
    }

    @Override
    public double monthlyPay() {
        return salary;
    }
}

final class Contractor implements Payable {
    private final String name;
    private final double hourlyRate;
    private final int hours;

    Contractor(String name, double hourlyRate, int hours) {
        this.name = name;
        this.hourlyRate = hourlyRate;
        this.hours = hours;
    }

    @Override
    public double monthlyPay() {
        return hourlyRate * hours;
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 TypeComparisonDemo.java
java TypeComparisonDemo
~~~

Exact stdout:

~~~text
EMPLOYEE: Lan (Engineer)
PAY: 3000.00
PAY: 1200.00
~~~

In the example, the `employee` variable has reference type `Employee` but holds a `SalariedEmployee` object. The `payables` array has element type `Payable`, so it can hold both a salaried employee and a contractor. When calling `monthlyPay()`, Java executes the implementation corresponding to the actual object. This is polymorphism: calling code relies on a common contract while the concrete behavior is selected based on the runtime object type.

## 6. Relationships among the three concepts

The structure of the example can be visualized as follows:

~~~text
Payable (interface)
    ^                  ^
    | implements       | implements
Employee (abstract)   Contractor (concrete)
    ^
    | extends
SalariedEmployee (concrete)
~~~

The arrows represent type relationships: `Employee` implements `Payable`; `Contractor` also implements `Payable`; `SalariedEmployee` extends `Employee`. As a result, the calling layer can choose the level of abstraction suited to its needs:

- Use `Payable` if you only need to call `monthlyPay()`.
- Use `Employee` if you need shared employee behaviors and state such as `name()` or `summary()`.
- Use `SalariedEmployee` if you need behavior specific to a salaried employee such as `salary()`, or when you need to create that specific object.

Variables and parameters should be declared with the abstract type best suited to the behavior the code needs. This reduces dependency on concrete implementations and makes it easier to substitute objects.

## 7. Design differences to understand clearly

**Class inheritance is single inheritance.** A Java class can have only one direct parent class, whether that parent class is abstract or concrete. A class can implement multiple interfaces. Therefore, an abstract class fits a shared foundation within a single inheritance hierarchy, whereas an interface fits capabilities that can appear across different class hierarchies.

**Constructors belong to classes.** An interface has no constructors and is not instantiated. An abstract class has constructors, but a constructor is only invoked through subclass initialization. A concrete class can provide constructors to create objects.

**Abstract methods must be completed.** A subclass can still be abstract if it has not implemented all abstract methods. When you want to create an instance, you need a concrete class that has fulfilled all inherited abstract methods.

**Interfaces do not replace every need for an abstract class.** An interface can have default methods, but it cannot hold instance state or constructors. If multiple classes need to share a data field along with initialization rules, an abstract class can express that model more directly.

**Abstract classes do not replace every need for an interface.** If multiple classes have no natural inheritance relationship yet need to provide the same capability, forcing them under a single parent class merely to share method names makes the inheritance hierarchy rigid. An interface expresses that contract without imposing a shared parent class.

**A concrete class can still depend on abstractions.** Even when a class is instantiated directly, it can implement an interface and be used through the interface type. “Concrete” describes a class's ability to be instantiated, not that the class must be referenced directly everywhere.

## 8. Common mistakes

- **Attempting to instantiate an interface or abstract class:** `new Payable()` and `new Employee(...)` are invalid. Create a concrete class that implements or extends that type.
- **Forgetting to implement required methods:** a concrete class must implement all remaining abstract methods. If it is not ready to do so, the class must be declared `abstract`.
- **Using an abstract class solely to define a contract:** if shared state or shared behavior is not needed, an interface is usually more flexible.
- **Using an interface to store instance state:** interface fields are static constants, not per-object data. Place instance state in a class.
- **Confusing concrete with final:** a concrete class can be extended; only `final` forbids extending that class.
- **Using a concrete type for every parameter:** this can couple calling code to a single implementation. If only shared behavior is needed, accept the appropriate interface or abstract class.
- **Creating overly deep inheritance hierarchies:** an abstract class should reflect an “is-a” relationship and have genuinely shared behavior. For independent capabilities, composition and interfaces usually produce a more flexible design.
- **Forgetting `@Override`:** this annotation helps the compiler catch errors when a method name or signature does not match the method being implemented.

## 9. How to choose in real-world scenarios

Choose an **interface** when you want to define a contract that multiple classes can implement, such as `Payable`, `Runnable`, or `Comparable`. The contract keeps calling code independent of a specific type of object.

Choose an **abstract class** when subtypes belong to the same conceptual family and need to share state, constructors, behavior, or common rules. Leave abstract methods for the parts that each subtype must define for itself.

Choose a **concrete class** when you need an instantiable implementation to execute business logic. A concrete class can stand alone, extend an abstract class, or implement one or more interfaces.

A useful design workflow is: identify the behavior the caller needs, define an interface if a replaceable contract is required; add an abstract class if there is shared state and logic worth sharing; and then provide one or more concrete classes for execution. There is no need to create all three layers if the problem does not actually require them.

## 10. Self-check checklist

- Can you explain what behavior the interface publishes without referring to a specific implementation?
- Does the abstract class genuinely contain shared state or shared behavior worth sharing?
- Has the concrete class implemented every abstract method and provided a suitable constructor?
- Can calling code use an interface or abstract class instead of depending on a concrete class?
- Have you distinguished the `extends` relationship from `implements` and kept in mind that a class can have only one direct parent class?
- Does the example compile with the target Java version, and does the stdout output match the documentation?

When you understand these roles clearly, you can design more extensible Java APIs: interfaces define contracts, abstract classes provide a shared foundation when needed, and concrete classes turn that contract and foundation into objects that can execute.
