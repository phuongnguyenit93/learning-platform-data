# Why Can't enum and record Extend an Arbitrary Abstract Class?

In Java, a class has only **one direct superclass**. The extends declaration specifies that superclass; implements declares the interfaces that the data type commits to implementing. Both enum and record are forms of class declarations with their own inheritance rules, so they cannot choose an additional arbitrary superclass.

- Every enum has java.lang.Enum&lt;E&gt; as its direct superclass, where E is the enum type being declared.
- Every record has java.lang.Record as its direct superclass.
- Both enum and record can implement multiple interfaces.
- If you need to use an existing abstract class, you can place the enum or record inside an adapter/wrapper object that extends that class and delegates the work to the wrapped object.

## 1. Java's Inheritance Rules

A regular class can extend an abstract class:

~~~java
abstract class Auditable {
    abstract String auditId();
}

final class Invoice extends Auditable {
    @Override
    String auditId() {
        return "INV-17";
    }
}
~~~

Invoice has Auditable as its direct superclass. Java does not allow declaring a regular class that inherits from two classes simultaneously, such as extending both Auditable and another class.

enum and record also follow the single-superclass limit, but they already have a superclass defined by the language. Therefore, the following declarations are **examples illustrating invalid syntax**:

~~~java
abstract class Auditable {
    abstract String auditId();
}

enum OrderStatus extends Auditable {
    OPEN, CLOSED;
}

record Customer(String id) extends Auditable {}
~~~

The extends Auditable clause must be removed from both declarations. There is no way to add an arbitrary superclass to enum or record syntax; this is a rule of the Java language, not a limitation specific to an IDE.

## 2. Why Does enum Extend java.lang.Enum?

An enum represents a finite, pre-declared set of constants. For example:

~~~java
enum OrderStatus {
    OPEN, PROCESSING, CLOSED
}
~~~

Java provides special behaviors for enums, such as the constant name via name(), the declaration position via ordinal(), comparability between constants of the same enum, and how enum constants are handled during serialization. The base class java.lang.Enum&lt;E&gt; provides some of these standard behaviors, while the compiler generates enum constants according to its own rules.

If an enum could extend an arbitrary class, it would need to inherit from both that arbitrary class and java.lang.Enum&lt;E&gt; at the same time. That violates the single direct superclass rule. Java solves this by fixing the superclass of an enum to java.lang.Enum&lt;E&gt;.

An enum can still contain fields, constructors, methods, and implement interfaces. An enum constructor cannot be called with new from outside to create additional arbitrary constants; the valid constants are listed in the enum declaration.

For example, an enum can implement an interface:

~~~java
interface Labelled {
    default String label() {
        return getClass().getSimpleName();
    }
}

enum OrderStatus implements Labelled {
    OPEN, CLOSED
}
~~~

OrderStatus can use the default method label() from the Labelled interface. Implementing an interface adds a contract and behavior without changing the enum's superclass. An enum constant can also have its own body to override methods, but that still does not allow the enum to extend an arbitrary class.

## 3. Why Does record Extend java.lang.Record?

A record is designed to declare data types that primarily carry data. For example:

~~~java
record Customer(String id, String name) {}
~~~

The declaration above indicates that Customer has two data components: id and name. If you do not define the corresponding members yourself, the compiler provides final component fields, accessor methods id() and name(), the canonical constructor, along with default implementations for equals(), hashCode(), and toString().

Every record has java.lang.Record as its direct superclass, and a record is a final type. Therefore, a record cannot add another superclass, even if that class is abstract. A record also has no extends syntax in its declaration.

This rule keeps the record's data model consistent: the declared components define the record's data, while shared behaviors can come from interfaces or be delegated to other objects. Arbitrary state inherited from a superclass can blur data boundaries and cause confusion when evaluating equality between records.

A record can still implement multiple interfaces, override methods, and declare an explicit constructor or a compact constructor to validate input data. Those capabilities do not change the java.lang.Record superclass and do not make a record a type that can be extended.

## 4. Runnable Example: Interfaces and Composition

The example below uses Java 17 or later. Customer is a record, and OrderStatus is an enum; both implement interfaces. CustomerAdapter is a regular class that extends the abstract class ExternalIdSource and delegates retrieving the ID to Customer.

Save all the code to the file EnumRecordDemo.java:

~~~java
interface Identified {
    String id();
}

interface Labelled {
    default String label() {
        return getClass().getSimpleName();
    }
}

enum OrderStatus implements Labelled {
    OPEN, CLOSED
}

record Customer(String id, String name)
        implements Identified, Labelled {}

abstract class ExternalIdSource {
    abstract String externalId();
}

final class CustomerAdapter extends ExternalIdSource {
    private final Customer customer;

    CustomerAdapter(Customer customer) {
        this.customer = customer;
    }

    @Override
    String externalId() {
        return customer.id();
    }
}

public class EnumRecordDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C-17", "Lan");

        System.out.println(customer);
        System.out.println(customer.id());
        System.out.println(customer.label());
        System.out.println(OrderStatus.OPEN.label());

        ExternalIdSource legacy = new CustomerAdapter(customer);
        System.out.println(legacy.externalId());
    }
}
~~~

Compile and run:

~~~text
javac EnumRecordDemo.java
java EnumRecordDemo
~~~

Expected output on stdout:

~~~text
Customer[id=C-17, name=Lan]
C-17
Customer
OrderStatus
C-17
~~~

Here, Customer does not extend ExternalIdSource. CustomerAdapter is the class that extends ExternalIdSource, holds a reference to Customer, and forwards the externalId() call to customer.id(). This is how you combine a record data type with a legacy API that requires a subclass of an abstract class.

## 5. Choosing the Right Design Approach

| Need | Appropriate Approach |
|---|---|
| Multiple types need to commit to the same set of methods | Declare an interface and have the enum/record implement that interface |
| Shared behavior is needed without depending on instance state | You can use a default method in an interface |
| An API or framework requires a subclass of an abstract class | Create an adapter/wrapper that extends the abstract class and delegates to the enum/record |
| Need to reuse instance state and superclass-based implementation | Consider a regular class in an inheritance hierarchy |
| A record needs additional data | Add appropriate record components, or hold another object for composition |

An interface describes a contract; it does not completely replace an abstract class. An interface does not provide arbitrary instance fields or inherited constructors, although it can declare default methods. If you need shared state and a superclass initialization flow, an adapter or composition is usually the clearer choice for enum and record.

## 6. Common Misconceptions

- **"An abstract class is not instantiated, so it can serve as a second superclass."** Incorrect. The single-superclass rule applies to all classes, regardless of whether the superclass is abstract.
- **"An enum is just a class with a list of constants."** An enum is a special form of declaration with java.lang.Enum&lt;E&gt; as its superclass and its own rules for creating constants.
- **"A record is a class, so it can use extends arbitrarily."** A record is a form of class declaration with a fixed superclass of java.lang.Record and does not allow an extends declaration.
- **"implements is equivalent to extends."** An interface provides a contract and can provide default methods, but it does not pass down the instance state or constructors of a superclass.
- **"You can change the superclass by overriding methods."** Overriding changes method behavior; it does not change the inheritance tree.
- **"If you need behavior from an abstract class, you must drop record or enum right away."** Not necessarily. First check whether the behavior can be modeled with an interface or by wrapping the object with an adapter. Only switch to a regular class when the model truly requires inheriting state and behavior from a superclass.

## 7. How to Remember

Enums extend java.lang.Enum&lt;E&gt; because Java manages them as enum constants with standard behavior. Records extend java.lang.Record because Java manages them as data types with explicitly declared components. Both can implement multiple interfaces, but neither can extend an arbitrary abstract class.

When you encounter a requirement that "an enum/record must be a subclass of an abstract class", check whether that requirement truly needs a method contract, needs to reuse superclass state and implementation, or simply needs compatibility with a legacy API. Use an interface for contracts; use an adapter/composition when integrating with an abstract class; use a regular class if the model genuinely requires an application-chosen superclass.
