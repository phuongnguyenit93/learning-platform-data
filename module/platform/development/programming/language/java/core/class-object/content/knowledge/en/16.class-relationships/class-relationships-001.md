# Objects Holding References to Other Objects in Java

## Learning Objectives

By the end of this lesson, you will be able to:

- Understand that an object can **hold a reference to another object** via an instance field, thereby representing relationships between classes (commonly called *has-a*, association).
- Distinguish between **reference type**, **reference variable**, **actual object in memory**, and **`null`**; avoid confusing declaring a field with automatically creating an object.
- Model `Customer` containing `Address`, `Order` containing `OrderLine`, and `Car` using `Engine`, and invoke methods through reference chains.
- Identify when multiple variables/fields point to **the same object** (*aliasing*), and the difference between replacing the referenced object and changing that object's state.
- Distinguish *association*, *aggregation*, and *composition* as **design/ownership concepts**, not Java keywords with automatic lifecycle management mechanisms.
- Apply constructor injection, non-null checks, encapsulation, immutable values, defensive copying, and collections for one-to-one and one-to-many relationships.
- Explain the meaning of `final` on a reference field, shallow copy/deep copy, the difference between `==` and `equals`, and how Java passes reference-type parameters **by value**.
- Understand bidirectional references, reference cycles, reachability/garbage collection, `NullPointerException` risks, recursive `toString()`, and concurrency.
- Compile/run standalone Java 17+ programs, read stdout accurately, and design reasonable APIs to represent relationships.

## 1. Core Idea: An Object Can Know and Use Another Object

An object-oriented program typically consists of **multiple collaborating objects**. For example:

- A `Customer` has an `Address`.
- An `Order` contains a list of `OrderLine` objects.
- A `Library` knows which `Book` objects are being managed.
- A `Car` uses an `Engine` to perform operating behavior.
- A `Student` references a `School` that multiple students can share.

In Java, a common way to represent this is to declare a **field whose type is another class/interface/record**:

~~~java
class Address {
    String city;
}

class Customer {
    Address address;
}
~~~

The two declarations above only describe **data types**. They do not automatically create an `Address` every time a `Customer` is created.

Specifically:

~~~java
Customer customer = new Customer();
// customer.address currently has the default value null.
customer.address = new Address();
customer.address.city = "Ha Noi";
~~~

This is an **illustrative** snippet placed inside an appropriate method, within the same scope that has access to the fields. `new Customer()` creates a Customer object, and then `new Address()` creates **a separate object**; the `address` field only holds a **reference** to that Address object.

Importantly: **an object holding a reference does not necessarily have exclusive ownership of the referenced object**, and replacing the reference does not automatically copy or destroy the old object.

### 1.1. Visual Model

~~~text
customer (reference variable)
   |
   v
Customer object
   address -----+
                |
                v
            Address object
              city = "Ha Noi"
~~~

There are two separate objects with their own identities. `Customer.address` is a **reference field**, not an `Address` “embedded as a whole object” as mandated by the language.

Java hides physical memory address details and does not provide arbitrary pointer arithmetic for Java references. Arrow diagrams help with reasoning about relationships, **not as a guarantee of a specific JVM memory layout**.

## 2. Reference Variables, Objects, and `null`

Let us distinguish:

| Entity | Example | Meaning |
| --- | --- | --- |
| **Reference type** | `Address` | Type name used to declare variables and check assignments |
| **Local reference variable** | `Address a` | A variable that can hold a reference or `null`; a local variable must be definitely assigned before being read |
| **Reference field** | `private Address address;` | Member of another object, defaulting to `null` if not yet assigned |
| **Object** | `new Address()` | An instance created according to Java rules |
| **Reference assignment** | `customer.address = a;` | Copies the **reference value**, does not clone the Address |
| **`null`** | `address = null;` | References no object |
| **Method call via reference** | `address.getCity()` | Operates on the pointed-to object, if the reference is valid |

The snippet:

~~~java
Address first = new Address();
Address second = first;
~~~

creates **one Address object**, but the two variables `first` and `second` both reference that object. It **does not call the constructor a second time**.

Whereas:

~~~java
Address first = new Address();
Address second = new Address();
~~~

creates **two separate Address instances** even if the fields inside them have identical values.

### 2.1. `new` for Which Object?

If:

~~~java
class Invoice {
    Customer customer;
}
~~~

then `new Invoice()` **does not automatically** call `new Customer()`. The `customer` field receives the default `null` unless a field initializer/constructor or some other logic assigns a valid reference.

To require that an invoice has a customer, you should require a parameter in the constructor and validate it explicitly; later sections will implement this.

## 3. First Program: A Customer Containing an Address

Save the file **`CustomerAddressDemo.java`**:

~~~java
public class CustomerAddressDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }

        void changeCity(String newCity) {
            city = newCity;
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        void print() {
            System.out.println(name + " lives in " + address.city());
        }
    }

    public static void main(String[] args) {
        Address address = new Address("Ha Noi");
        Customer customer = new Customer("Lan", address);

        customer.print();

        address.changeCity("Hue");
        customer.print();
    }
}
~~~

Compile/run:

~~~bash
javac CustomerAddressDemo.java
java CustomerAddressDemo
~~~

Stdout:

~~~text
Lan lives in Ha Noi
Lan lives in Hue
~~~

**Step-by-step analysis:**

1. `new Address("Ha Noi")` creates an Address object.
2. `new Customer("Lan", address)` creates a Customer object, then assigns the reference from the `address` parameter to the `Customer.address` field.
3. `customer.print()` reads information through the call chain `address.city()`.
4. `address.changeCity("Hue")` modifies **the same Address object** from outside Customer.
5. When Customer reads `address.city()` again, it sees `Hue` because both references point to the same object.

This is an example of **aliasing**. The `final` modifier on the `Customer.address` field does **not** make the Address object immutable; it only prevents Customer's reference field from being reassigned after proper initialization.

### 3.1. The Constructor in the Example Lacks Sufficient Validation

The initial example is intentionally short to highlight reference sharing. If the caller writes `new Customer("Lan", null)`, the constructor accepts `null`, and calling `print()` will risk throwing a `NullPointerException`.

In an application that requires the invariant “every Customer always has an Address”, use:

~~~java
Customer(String name, Address address) {
    this.name = java.util.Objects.requireNonNull(name, "name");
    this.address = java.util.Objects.requireNonNull(address, "address");
}
~~~

In addition, you need to validate `name.isBlank()` or the Address fields according to business rules. A non-null check only prevents a null reference; it **does not automatically guarantee** that the referenced object has a valid state or is immutable.

## 4. “Has-a” Is a Relationship, Not Synonymous with Inheritance

Compare the two statements:

- **Car has an Engine** → usually represented by a field `Engine engine`.
- **ElectricCar is a Car** → can be represented using `extends Car` if it is a true type relationship.

~~~java
class Engine {
    void start() {
        System.out.println("Engine started");
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void start() {
        engine.start();
    }
}
~~~

These are valid **illustrative declarations** within an appropriate source file/package. `Car` does not inherit from Engine; it **delegates behavior** to the Engine whose reference it holds.

A class can both extend a superclass and hold references to other objects. However, do not use `extends` merely because “A uses B”. Inheritance describes a type relationship (*is-a*) and enables polymorphism; a reference field describes an object relationship (*has-a/uses-a*).

### 4.1. Choose Composition When You Want to Swap Components

For example:

~~~java
interface Engine {
    void start();
}

class ElectricEngine implements Engine {
    public void start() {
        System.out.println("Electric engine started");
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void start() {
        engine.start();
    }
}
~~~

This is an illustrative multi-class model without a `main` method. `Car` depends on the **`Engine` interface**. It can use a different implementation without inheriting from a concrete engine class.

An `interface` itself does not create an object; at runtime, the `engine` field references an object of a class that implements that interface.

## 5. A Program Delegating Through an Interface Reference

Save **`CompositionStrategyDemo.java`**:

~~~java
public class CompositionStrategyDemo {
    interface Notifier {
        void send(String message);
    }

    static final class ConsoleNotifier implements Notifier {
        public void send(String message) {
            System.out.println("console: " + message);
        }
    }

    static final class PrefixNotifier implements Notifier {
        private final String prefix;

        PrefixNotifier(String prefix) {
            this.prefix = prefix;
        }

        public void send(String message) {
            System.out.println(prefix + message);
        }
    }

    static final class OrderService {
        private final Notifier notifier;

        OrderService(Notifier notifier) {
            this.notifier = java.util.Objects.requireNonNull(
                    notifier, "notifier");
        }

        void complete(String orderId) {
            notifier.send("completed " + orderId);
        }
    }

    public static void main(String[] args) {
        OrderService first = new OrderService(
                new ConsoleNotifier());
        OrderService second = new OrderService(
                new PrefixNotifier("event: "));

        first.complete("A-1");
        second.complete("B-2");
    }
}
~~~

Compile/run:

~~~bash
javac CompositionStrategyDemo.java
java CompositionStrategyDemo
~~~

Output:

~~~text
console: completed A-1
event: completed B-2
~~~

**Why is this example useful?**

- `OrderService` **holds a reference of an interface type**.
- Constructor injection supplies the dependency from outside instead of hard-coding `new ConsoleNotifier()` inside `complete`.
- When calling `notifier.send(...)`, dynamic dispatch executes the implementation corresponding to the object currently referenced.
- `private final Notifier notifier` fixes the reference after the constructor, but the concrete implementation may have its own mutable state.
- `Objects.requireNonNull` protects the invariant that the reference exists.

This is **composition through object collaboration**. It differs from `extends`, while also allowing behavior to be swapped via a dependency. In tests, you can also pass a fake implementation to record messages without sending real notifications.

## 6. Association, Aggregation, and Composition: A Reference Does Not Determine Ownership

Holding a field `Department department` or `List<OrderLine> lines` shows that object A **knows about or references** object B, but it is not enough to conclude **who owns** B.

| Relationship | Meaning to Verify | Example Illustration |
| --- | --- | --- |
| **Association** | A relates to, knows about, or navigates to B | Employee → Department |
| **Aggregation** | A whole groups parts that may have independent lifecycles or be shared | Team ↔ Member |
| **Composition** | A whole is tightly responsible for its parts and their invariants/lifecycle according to the domain model | Order → OrderLine |

Java **has no keywords** `association`, `aggregation`, or `composition`, nor does it automatically call “delete” when a reference is removed. All three often use similar fields/collections; **domain rules and the API for creating/removing/sharing objects are what determine the meaning of the relationship**.

At this introductory lesson level, identify: “Which reference does A hold?”, “Can B be held by another object?”, and “Who checks invariants when the link changes?”. The lesson **Object Usage, Association, and Ownership Relationships** covers dependency, association, aggregation, composition, UML multiplicity, and ownership transfer in full; this lesson continues to focus on referencing **the object itself** and aliases in the Java runtime.

## 7. Aliasing: Two Places Holding the Same Reference

**Aliases** are variables/fields that reference the same object.

~~~java
Address shared = new Address("Ha Noi");
Customer a = new Customer("Lan", shared);
Customer b = new Customer("Minh", shared);
~~~

If both Customers keep the same reference, an operation changing `shared.city` will be observed by both. This is **sharing the same object**, not two Address objects automatically synchronizing.

### 7.1. A Program to Observe Sharing

Save **`SharedReferenceDemo.java`**:

~~~java
public class SharedReferenceDemo {
    static final class Box {
        private int value;

        Box(int value) {
            this.value = value;
        }

        int value() {
            return value;
        }

        void setValue(int value) {
            this.value = value;
        }
    }

    static final class Holder {
        private Box box;

        Holder(Box box) {
            this.box = box;
        }

        int read() {
            return box.value();
        }

        void replace(Box replacement) {
            box = replacement;
        }
    }

    public static void main(String[] args) {
        Box shared = new Box(10);
        Holder a = new Holder(shared);
        Holder b = new Holder(shared);

        System.out.println("initial=" + a.read() + "," + b.read());

        shared.setValue(20);
        System.out.println("mutated=" + a.read() + "," + b.read());

        a.replace(new Box(99));
        System.out.println("replaced=" + a.read() + "," + b.read());

        shared.setValue(30);
        System.out.println("original=" + a.read() + "," + b.read());
    }
}
~~~

Run:

~~~bash
javac SharedReferenceDemo.java
java SharedReferenceDemo
~~~

Output:

~~~text
initial=10,10
mutated=20,20
replaced=99,20
original=99,30
~~~

**Correctly reading the two different operations:**

- `shared.setValue(20)` **modifies the state of a single object**. Both holders point to that object, so both see 20.
- `a.replace(new Box(99))` **replaces the reference** stored in the `a.box` field. It does not modify `b.box` and does not turn `shared` into Box(99).
- After replacing the reference in `a`, `shared.setValue(30)` only affects the old Box that `b` still holds. `a` now points to the new Box with value 99.

A very common logic error is confusing `holder.box = new Box(...)` with `holder.box.setValue(...)`: reference assignment changes the target object; the method call modifies the object currently pointed to.

### 7.2. What Does a `final` Field Prevent?

~~~java
class Holder {
    private final Box box;

    Holder(Box box) {
        this.box = box;
    }

    void update(int value) {
        box.setValue(value); // May be valid.
    }
}
~~~

This is an illustrative class (assuming `Box` has an appropriate method). `final` prevents the `update` method from reassigning `box = new Box(...)`, yet it can still call a method to **mutate the Box object**. `final` is a constraint on **field reference assignment**, not **deep immutability**.

## 8. How Does Java Pass Reference Parameters?

**Java always passes parameters by value.** For a reference-type parameter, the value copied is the **reference value**, not the underlying object.

This has two consequences:

1. A method can modify the object through the passed reference if the object has a mutable API.
2. Assigning the parameter to a different reference **does not change the reference of the caller's variable**.

### 8.1. Runnable Program

Save **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Person {
        String name;

        Person(String name) {
            this.name = name;
        }
    }

    static void mutate(Person p) {
        p.name = "Changed";
    }

    static void reassign(Person p) {
        p = new Person("Replacement");
        System.out.println("inside reassign=" + p.name);
    }

    public static void main(String[] args) {
        Person person = new Person("Original");

        mutate(person);
        System.out.println("after mutate=" + person.name);

        reassign(person);
        System.out.println("after reassign=" + person.name);
    }
}
~~~

Commands:

~~~bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Output:

~~~text
after mutate=Changed
inside reassign=Replacement
after reassign=Changed
~~~

`mutate` uses the copied reference to modify **the same Person object**. `reassign` only changes the reference in the local parameter `p`; the caller's `person` variable still points to the old object.

Do not call Java “pass by reference” in the sense that a variable on the caller side can be reassigned through a normal parameter. The accurate phrasing is: **pass by value, and the value here is the reference**.

### 8.2. Passing `null`

If the caller passes `null` and the method accesses `p.name` or calls `p.method()`, it will usually encounter a `NullPointerException`. A method that accepts a nullable reference should state a clear contract: whether null is allowed, and if not, reject it at the boundary.

## 9. Constructor Injection and the Invariant of a Required Relationship

If an `Invoice` must always be associated with a `Customer`, the design:

~~~java
class Invoice {
    private Customer customer;

    Invoice() {
    }

    void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
~~~

creates a period during which the Invoice exists while `customer == null`. This may be reasonable for a builder or a partially filled form, but it is unsuitable if a domain Invoice **always** needs a Customer.

A design that enforces the dependency right in the constructor:

~~~java
import java.util.Objects;

class Invoice {
    private final Customer customer;

    Invoice(Customer customer) {
        this.customer = Objects.requireNonNull(
                customer, "customer");
    }

    Customer customer() {
        return customer;
    }
}
~~~

This snippet requires the `Customer` type to be declared in the source/project. `Objects.requireNonNull` throws a `NullPointerException` immediately in the constructor with a clear parameter name. `final` makes the Invoice's reference fixed once the object is properly constructed.

**Nothing forces a constructor to create `new Customer()` itself.** Passing the dependency in from the caller (*constructor injection*) is often useful when the Customer already exists or is shared by multiple invoices.

### 9.1. When Should a Part Be Created Internally?

If the part is an implementation detail and does not need to be shared:

~~~java
class Device {
    private final Controller controller = new Controller();
}
~~~

this is a reasonable design when Controller is genuinely a private component of Device. However, Controller needs to be a class with an appropriate constructor. Creating the part implicitly makes swapping implementations/testing harder; consider factory injection if flexible behavior changes or ownership are required.

**Principle:** who creates the part, who holds the reference, who is allowed to modify the part, and whether the part can be shared must be decided by domain requirements, not merely by field syntax.

## 10. Encapsulating Mutable References and Defensive Copying

Even `private final Address address` can still be modified **indirectly** if the mutable Address object is shared.

There are three common strategies:

1. **Intentional sharing:** keep a reference to a shared object and accept that updates appear in multiple places. The ownership/concurrency contract must be clearly specified.
2. **Immutable value object:** use a record or final class with immutable components and no setters, making sharing safer with respect to state.
3. **Defensive copy/snapshot:** copy mutable inputs when receiving them and mutable outputs when returning them to protect the representation.

### 10.1. An Immutable Record for a Simple Address

~~~java
record Address(String city) {
    Address {
        java.util.Objects.requireNonNull(city, "city");
        if (city.isBlank()) {
            throw new IllegalArgumentException("city required");
        }
    }
}
~~~

With only `String city` (since String is immutable), each `Address` record has observable state that does not change through its accessor. Consumers can hold/share references to the same record without being able to change city via a setter.

However, a Java **record does not automatically provide deep immutability** if a component is a mutable array, list, or custom mutable class; you still need to copy/protect components when necessary.

### 10.2. Complete Program with Immutable Parts

Save **`ImmutableRelationshipDemo.java`**:

~~~java
import java.util.Objects;

public class ImmutableRelationshipDemo {
    record Address(String city) {
        Address {
            Objects.requireNonNull(city, "city");
            if (city.isBlank()) {
                throw new IllegalArgumentException("blank city");
            }
        }
    }

    static final class Customer {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = Objects.requireNonNull(name, "name");
            this.address = Objects.requireNonNull(address, "address");
        }

        String describe() {
            return name + "@" + address.city();
        }

        Customer moveTo(Address destination) {
            return new Customer(name, destination);
        }
    }

    public static void main(String[] args) {
        Address hanoi = new Address("Ha Noi");
        Customer first = new Customer("Lan", hanoi);
        Customer second = new Customer("Minh", hanoi);

        System.out.println(first.describe());
        System.out.println(second.describe());

        Customer moved = first.moveTo(new Address("Hue"));

        System.out.println("old=" + first.describe());
        System.out.println("new=" + moved.describe());
        System.out.println("second=" + second.describe());
    }
}
~~~

Run:

~~~bash
javac ImmutableRelationshipDemo.java
java ImmutableRelationshipDemo
~~~

Stdout:

~~~text
Lan@Ha Noi
Minh@Ha Noi
old=Lan@Ha Noi
new=Lan@Hue
second=Minh@Ha Noi
~~~

The two initial Customers share **the same Address record**, yet no method mutates it. The `moveTo` method returns a **new** Customer object, keeping the old object intact. `second` remains in Ha Noi.

Note that `Customer` here is one way to illustrate immutable design; not every customer system has to be immutable. You should choose the data model according to business requirements.

## 11. Copying a Mutable Object Both When Receiving and When Returning

If `Address` needs to be mutable, a class that owns an independent snapshot can copy it in the constructor and return a copy from the getter.

Save **`DefensiveAddressCopyDemo.java`**:

~~~java
public class DefensiveAddressCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        Address(Address source) {
            this.city = source.city;
        }

        void setCity(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }
    }

    static final class Customer {
        private final Address address;

        Customer(Address input) {
            if (input == null) {
                throw new IllegalArgumentException("address required");
            }
            address = new Address(input); // Copy when receiving.
        }

        Address address() {
            return new Address(address); // Copy when returning.
        }
    }

    public static void main(String[] args) {
        Address source = new Address("Ha Noi");
        Customer customer = new Customer(source);

        source.setCity("Hue");
        System.out.println("source=" + source.city());
        System.out.println("customer=" + customer.address().city());

        Address snapshot = customer.address();
        snapshot.setCity("Da Nang");

        System.out.println("snapshot=" + snapshot.city());
        System.out.println("customer after=" + customer.address().city());
    }
}
~~~

Run:

~~~bash
javac DefensiveAddressCopyDemo.java
java DefensiveAddressCopyDemo
~~~

Output:

~~~text
source=Hue
customer=Ha Noi
snapshot=Da Nang
customer after=Ha Noi
~~~

**Why is two-way copying needed?**

- Constructor copy: if the caller modifies `source` afterward, it does not alter Customer.
- Getter copy: if the caller modifies the returned `snapshot` object, it does not modify the Address held inside Customer.

In the example, Address only contains an immutable `String`, so a simple copy constructor is sufficient. If Address has mutable subobjects such as `List<String>` or `int[]`, copying a reference to the new object is still a **shallow copy**, and you may need to copy the subobjects to the required depth.

### 11.1. Shallow Copy and Deep Copy

| Copy Type | What Does It Do? | Risk |
| --- | --- | --- |
| Shallow copy | Creates a new outer object while keeping references to inner objects | Inner mutable objects remain shared |
| Appropriate deep copy | Creates independent copies of the entire mutable graph that needs protection | More expensive, complex when the graph has cycles/shared identities |
| Immutable snapshot | Uses immutable value types + unmodifiable structures | Mutable elements remain shared if not protected |
| No copy | Intentionally shares the object | Aliasing and concurrency must be clear |

There is no single Java operator that guarantees a deep copy for **every object graph**. `Object.clone()` (if used) defaults to shallow behavior under its foundational contract; meanwhile, serialization- or reflection-based copying carries its own risks and preconditions. When independence is required, design copying according to the **specific type/domain**.

## 12. One-to-Many Relationships: An Object Holding a List of References

An object does not always reference just a single part. For example, an `Order` has multiple order lines.

~~~java
class Order {
    private final java.util.List<OrderLine> lines;
}
~~~

`List<OrderLine>` describes a **collection containing references to OrderLine objects**. Java does not clone each OrderLine merely because an element is added to a list.

With a mutable element, both the list and the caller can hold a reference to **the same OrderLine object**. With a mutable list exposed through a getter, the caller can also add or remove references in the internal collection.

### 12.1. Questions a One-to-Many Contract Must Answer

- Can the list be **empty**?
- Can a part be **null**?
- Can a part be shared across multiple Orders?
- Who is allowed to **add/remove/modify** elements?
- Does Order store a snapshot or a live view?
- When removed from the list, is the part's data permanently deleted?
- Does every OrderLine satisfy the invariants (positive quantity, non-negative unit price)?

Those questions are not automatically answered by a `List<OrderLine>` declaration.

## 13. A Controlled One-to-Many Example

Save **`OrderLinesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderLinesDemo {
    record OrderLine(String sku, int quantity, long unitPrice) {
        OrderLine {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long amount() {
            return Math.multiplyExact((long) quantity, unitPrice);
        }
    }

    static final class Order {
        private final String id;
        private final List<OrderLine> lines;

        Order(String id, List<OrderLine> input) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            this.id = id;
            this.lines = List.copyOf(input);
        }

        List<OrderLine> lines() {
            return lines;
        }

        long total() {
            long result = 0;
            for (OrderLine line : lines) {
                result = Math.addExact(result, line.amount());
            }
            return result;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        List<OrderLine> draft = new ArrayList<>();
        draft.add(new OrderLine("PEN", 2, 10));
        draft.add(new OrderLine("BOOK", 1, 35));

        Order order = new Order("O-7", draft);
        draft.clear();

        System.out.println("draft size=" + draft.size());
        System.out.println("order size=" + order.lines().size());
        System.out.println("total=" + order.total());

        try {
            order.lines().clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("order lines are read-only");
        }

        System.out.println("total after=" + order.total());
    }
}
~~~

Run:

~~~bash
javac OrderLinesDemo.java
java OrderLinesDemo
~~~

Stdout:

~~~text
draft size=0
order size=2
total=55
order lines are read-only
total after=55
~~~

**Explanation:**

1. `draft` is an external mutable list containing two immutable `OrderLine` records.
2. `Order` stores `List.copyOf(input)`: Order's list structure is an unmodifiable snapshot.
3. Clearing all of `draft` afterward does not remove the lines saved inside Order.
4. The caller cannot modify the structure of `order.lines()` via `clear()`.
5. `Math.multiplyExact` and `Math.addExact` help detect integer overflow when calculating totals, preventing silently wrong amounts.
6. The `OrderLine` records use `String` + primitives without nested mutable components; this makes sharing elements safer.

**Not equivalent to automatic composition:** In the example, `Order` cannot have its structure modified by the caller through its API, yet an `OrderLine` record can still be created and used elsewhere. If domain rules require a part to belong strictly to a single Order, an additional identity/ownership contract must be designed.

### 13.1. `List.copyOf` Is Not a Deep Copy

`List.copyOf` prevents structural mutation of the returned/stored list and takes a snapshot of the current elements; it does **not** deep-copy each element object.

In addition, `List.copyOf` **does not accept null elements** and may reuse an input list that is already suitably unmodifiable. Do not rely on every `copyOf` call creating a new list object by identity; rely on the unmodifiability/snapshot contract.

If `OrderLine` is a mutable class with `setUnitPrice(...)`, holding shared references to elements can break Order's invariant. In that case, prefer immutable elements or deep copying/immutable DTOs as needed.

## 14. Unmodifiable View, Snapshot, and Live Sharing

There are two approaches that are easy to confuse:

~~~java
List<Member> view = java.util.Collections.unmodifiableList(source);
List<Member> copy = List.copyOf(source);
~~~

Suppose `source` is a mutable list:

- `view` is a **read-only view** pointing to the backing list `source`. The caller cannot modify through `view`, but if someone modifies `source`, `view` can reflect those changes.
- `copy` is an unmodifiable snapshot of the element references at the time of the call. Adding or removing elements in `source` afterward does not change the structure of `copy`.
- **Both** can hold references to **the same Member objects**. If Member is mutable, Member contents can change via an alias.
- `new ArrayList<>(source)` creates a mutable shallow copy; if the caller modifies the copy's structure it does not affect the source's structure, though the elements may still be shared.

### 14.1. A Program Distinguishing a View from a Snapshot

Save **`ViewVsSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot add");
        }
    }
}
~~~

Run:

~~~bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

Output:

~~~text
source=[A, B]
view=[A, B]
snapshot=[A]
view cannot add
~~~

This is an important distinction in designing one-to-many relationships. Returning a read-only view does not always mean the caller receives data that is immutable over time.

## 15. `null`, Optional Relationships, and Safe Handling

A reference field can be `null` if unassigned. For an **optional** relationship, this may be valid intent; for a **required** relationship, it may represent an invalid domain state.

### 15.1. Required Relationships

~~~java
class Order {
    private final Customer customer;

    Order(Customer customer) {
        this.customer = java.util.Objects.requireNonNull(
                customer, "customer");
    }
}
~~~

Here `customer` is always non-null once the constructor completes normally. If the Customer object is mutable, non-null does **not** mean all state of Customer is always valid; Customer's contract must be designed as well.

### 15.2. Optional Relationships

If an Employee may not have a manager yet, the API can represent this with a nullable field and a method returning `Optional`:

~~~java
import java.util.Optional;

class Employee {
    private Employee manager;

    Optional<Employee> manager() {
        return Optional.ofNullable(manager);
    }

    void assignManager(Employee manager) {
        this.manager = manager;
    }
}
~~~

This is an example where **a null value carries contract meaning**, not a default bug. `Optional` is usually suitable as a **return type** for the caller to handle presence/absence. You do not need to turn every nullable field into an `Optional<Field>` field; choose the API based on the domain and coding conventions.

### 15.3. Reference Access Chains Can Throw NPE

~~~java
customer.address().city()
~~~

If `customer` or `address()` returns null, the next access can throw a `NullPointerException`. Do not chain method calls merely because the current test data always has all objects present.

A better approach when the relationship is required: validate in the constructor and never return null. When optional: use `Optional`, explicit check branches, or a clear domain value.

## 16. Optional Manager Example Using `Optional`

Save **`OptionalRelationshipDemo.java`**:

~~~java
import java.util.Optional;

public class OptionalRelationshipDemo {
    static final class Employee {
        private final String name;
        private Employee manager;

        Employee(String name) {
            this.name = name;
        }

        void setManager(Employee manager) {
            this.manager = manager;
        }

        Optional<Employee> manager() {
            return Optional.ofNullable(manager);
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Employee lan = new Employee("Lan");
        Employee minh = new Employee("Minh");

        System.out.println("Lan manager=" +
                lan.manager().map(Employee::name).orElse("none"));

        lan.setManager(minh);

        System.out.println("Lan manager=" +
                lan.manager().map(Employee::name).orElse("none"));
        System.out.println("Minh manager=" +
                minh.manager().map(Employee::name).orElse("none"));
    }
}
~~~

Run:

~~~bash
javac OptionalRelationshipDemo.java
java OptionalRelationshipDemo
~~~

Output:

~~~text
Lan manager=none
Lan manager=Minh
Minh manager=none
~~~

This only illustrates an optional reference; it does **not** implement real organizational rules such as “an employee cannot manage themselves” or “no management cycles”. Those invariants require validation if the domain requires them.

## 17. Identity Differs from Equality: Same Object or Same Data?

Another question is whether two references point to **the same object** or to two different objects that **have the same contents**.

- `a == b` with two references: compares **reference identity** (whether it is the same object or not), except for the null case.
- `a.equals(b)`: calls the object's equality logic according to its implementation; for a class that does not override it, `Object.equals` defaults to identity-based comparison.
- Java records provide `equals` based on record components with appropriate semantics; two separate record instances can be equal by value.

### 17.1. Program Illustrating Identity/Value

Save **`ReferenceEqualityDemo.java`**:

~~~java
public class ReferenceEqualityDemo {
    record Address(String city) {
    }

    static final class Box {
        private final int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Address a1 = new Address("Hue");
        Address a2 = new Address("Hue");
        Address alias = a1;

        System.out.println("record identity=" + (a1 == a2));
        System.out.println("record equals=" + a1.equals(a2));
        System.out.println("alias identity=" + (a1 == alias));

        Box b1 = new Box(5);
        Box b2 = new Box(5);

        System.out.println("box identity=" + (b1 == b2));
        System.out.println("box equals=" + b1.equals(b2));
    }
}
~~~

Compile/run:

~~~bash
javac ReferenceEqualityDemo.java
java ReferenceEqualityDemo
~~~

Output:

~~~text
record identity=false
record equals=true
alias identity=true
box identity=false
box equals=false
~~~

**Design note:** `equals`/`hashCode` should be defined together if a custom class requires value-based equality and is used in `HashSet`/`HashMap`. For entities carrying domain identity, equal values do not necessarily mean “the same entity”; a clear equality contract is needed.

### 17.2. Avoid Using `==` to Compare Text Information

If `Customer` holds `String name`, comparing two names with `==` compares the reference identity of the String objects. You should use `name.equals(otherName)` when non-null or `Objects.equals(name, otherName)` when nullable.

## 18. Bidirectional Relationships: Two Objects Holding References to Each Other

A link can be **unidirectional**:

~~~text
Employee ----> Department
~~~

or **bidirectional**:

~~~text
Employee ----> Department
          <----
~~~

If `Employee` holds a `Department` and `Department` holds a list of `Employee` references, these are two reference directions that are **independent in terms of field assignment**. Java **does not automatically** update both directions when you change one side.

### 18.1. The Issue of Synchronizing Both Ends

If you only run:

~~~java
employee.department = newDepartment;
~~~

and the old Department still keeps the employee in its list, the object graph can become inconsistent. Besides encapsulating the fields, a relationship-managing method is needed:

~~~java
void transfer(Employee employee, Department destination) {
    // Validate input/state
    // Remove employee from source department
    // Add employee to destination department
    // Update employee.department
}
~~~

This is **design pseudocode**, not a runnable method because the full classes/APIs are not defined here. It illustrates that a bidirectional relationship is a **multi-object invariant** and must be updated in a controlled manner.

When concurrency or persistence is involved, coordinated operations may require locks, transactions, or an aggregate boundary; a few separate assignments do not provide atomicity.

### 18.2. Reference Cycles Are Not Necessarily Memory Leaks

Suppose A points to B and B points to A. **The Java garbage collector evaluates reachability from GC roots**, rather than simply counting references. If neither object in the pair remains reachable from roots, the Java GC can reclaim the entire cycle (without guaranteeing timing). A cycle by itself **does not equal a memory leak**.

Conversely, if a static collection still holds a reference to A, then the A↔B graph can remain reachable and occupy memory even when the business task is already “done”. That is the real risk of holding references too long.

## 19. Program with a Cyclic Object Graph

Save **`CyclicReferencesDemo.java`**:

~~~java
public class CyclicReferencesDemo {
    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void connect(Node next) {
            this.next = next;
        }

        String nextName() {
            return next == null ? "none" : next.name;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.connect(b);
        b.connect(a);

        System.out.println("A -> " + a.nextName());
        System.out.println("B -> " + b.nextName());
        System.out.println("same A=" + (a == b.next));
    }
}
~~~

Run:

~~~bash
javac CyclicReferencesDemo.java
java CyclicReferencesDemo
~~~

Output:

~~~text
A -> B
B -> A
same A=true
~~~

The two objects reference each other; the `next` field only stores a reference. If `toString()` is implemented by **recursively printing the entire next object** without visited/depth guards, a cyclic graph can cause infinite recursion/`StackOverflowError`.

**Good design:** print a short ID/name instead of recursively rendering every object; or traverse the graph using a visited set when necessary.

## 20. Garbage Collection, Lifecycles, and Ownership Relationships

Java has automatic garbage collection, yet **no Java field reference syntax automatically enforces the delete/cascade-delete semantics of UML composition**.

Some situations:

- `customer.address = null` (if the field is mutable) only drops **one reference path** to the Address object; Address may still be referenced by other variables/objects.
- Removing via `order.lines().remove(line)` (if the list is mutable) only alters the collection structure; it does not necessarily delete the line from the database or immediately reclaim the object.
- When no longer reachable from GC roots, an object becomes **eligible** for collection. The JVM does not promise that the collector runs at the exact moment you assign `null`.
- GC reclaims **managed memory**; it does not automatically close files, sockets, or DB transactions in a timely manner. Non-heap resources should have an explicit lifecycle, typically via `try-with-resources` and `AutoCloseable`.
- An object reference can be held from places outside an imagined “owner” model; merely making a field public/private does not automatically block all aliases.

**Strong domain composition** requires real APIs and ownership rules; it cannot rely on an assumption that `new Owner()` automatically controls the memory of all parts.

### 20.1. `static` References Completely Change Lifecycles

A `static List<Object> cache` holding references can keep an entire object graph reachable in the runtime. Do not use mutable global static collections as a “list of existing objects” without an appropriate eviction policy or lifecycle.

## 21. `private` Does Not Always Protect the Data Behind a Reference

Consider:

~~~java
class Customer {
    private final java.util.List<String> tags;

    Customer(java.util.List<String> tags) {
        this.tags = tags;
    }

    java.util.List<String> tags() {
        return tags;
    }
}
~~~

The `tags` field is `private final`, yet:

1. The caller holding the input `tags` can add/remove elements after Customer is created.
2. The getter returns **the same mutable list** to other code.
3. `final` prevents reassigning `this.tags`, not mutating the list.

If the API wants to keep a **read-only snapshot**, use:

~~~java
class Customer {
    private final java.util.List<String> tags;

    Customer(java.util.List<String> tags) {
        this.tags = java.util.List.copyOf(tags);
    }

    java.util.List<String> tags() {
        return tags;
    }
}
~~~

The two versions above are **alternative designs** and must not both define a class named Customer in the same package during compilation.

If the list elements are mutable custom objects, `List.copyOf` still shares each element. Choose an immutable element type or appropriate defensive copying.

## 22. References via Interfaces and Polymorphism

A field can have an **interface or superclass type**:

~~~java
private PaymentMethod paymentMethod;
~~~

At runtime, it can point to `CardPayment`, `WalletPayment`, or another implementation. The caller sees behavior according to the static type `PaymentMethod`, while overridden methods execute according to the runtime object.

Benefits:

- The object holding the field depends on an **abstraction** rather than an implementation detail.
- Easy to swap implementation objects and write unit tests.
- Avoids requiring the outer object's constructor to understand the entire nested implementation.
- Allows organizing small and clear responsibilities.

Limitations:

- If an uncontrolled mutable reference is kept, other code can change behavior/state at runtime.
- If an implementation is not thread-safe, injecting it does not make the containing class thread-safe.
- An interface does not guarantee that every implementation satisfies the contract without proper testing and design.

**Using composition over inheritance** is often beneficial when “A uses B to get a job done” rather than “A is a kind of B”.

## 23. Concurrency: An Object Graph Sharing State Also Shares Risk

If two objects A and B both hold a reference to a mutable Counter and are used across two threads, they both access **the same Counter object**. Making the reference field `private` in A and B does not create two copies of Counter.

For example:

~~~java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
~~~

`value++` is not atomic. If multiple threads use a shared Counter, lost updates or visibility issues under the Java Memory Model can occur.

Solutions depending on the case:

- Use immutable values and replace references under a controlled model.
- Use consistent synchronization/locks for mutable state that needs protection.
- Use `AtomicInteger` for a simple counter, but do not assume that multiple fields will automatically be updated atomically.
- Avoid sharing mutable state when possible; define ownership clearly.
- If an object returns a snapshot and other threads update the state right afterward, the snapshot may represent a point-in-time picture rather than a live view.

In Java 17, a `final` field ensures the reference cannot be reassigned after valid initialization; it does **not** automatically make the referenced object thread-safe.

## 24. Common Mistakes When Designing Class Relationships

| Mistake/Misconception | Problem | How to Handle |
| --- | --- | --- |
| “`Address address;` automatically creates an Address object.” | The field only holds a reference, usually defaulting to null | Assign the reference via a constructor/initializer |
| “`new Customer()` surely creates Address inside.” | There is no such automatic mechanism | Define who creates and injects/owns Address |
| “`a = b` clones the object.” | It only copies the reference | Use a copy/factory if independent state is needed |
| “Two references with equal fields must be the same object.” | Identity differs from value equality | Distinguish between `==` and `equals` |
| “`private final Address` makes Address immutable.” | Final only prevents reassigning the field reference | Use an immutable Address or defensive copy |
| “If a getter returns a private list, no one can mutate it.” | The getter may expose a mutable reference | Return an unmodifiable snapshot/copy per contract |
| “`Collections.unmodifiableList` is a snapshot.” | It may be a live view of the backing list | Use `List.copyOf` if a snapshot is needed |
| “`List.copyOf` deep-copies elements.” | Elements are still shared | Use immutable elements/deep copy |
| “Having a field means UML composition.” | Ownership is not proved by syntax | Define lifecycle/invariants through the API |
| “Aggregation/Composition have Java keywords.” | They are modeling concepts | Express them with fields, constructors, factories, and contracts |
| “Bidirectional relationships stay synchronized automatically.” | The two references/collections are separate fields | Use a method that manages both sides |
| “Reference cycles prevent GC reclamation.” | Reachability is the deciding factor | Avoid keeping the graph reachable from GC roots unnecessarily |
| “Setting a reference to null immediately frees the object.” | Aliases may remain; GC is not immediate | Manage lifecycle and resources explicitly |
| “Java passes objects by reference.” | Java uses pass-by-value of the reference | Distinguish mutation from reassignment |
| “`null` is always a bug.” | A nullable association may be valid in the domain | Use Optional/clear contracts |
| “Having `final` makes it thread-safe.” | A mutable referent still has data races | Synchronize or design it as immutable |
| “Recursive `toString` across all fields is always safe.” | Bidirectional cycles can recurse infinitely | Print IDs, limit depth, or use a visited set |
| “Removing a Line from Order's list deletes the line in the DB.” | A collection update differs from a persistence operation | Design a separate repository/transaction |

## 25. Checklist for Designing a Reference Field

Before writing `private B b;` inside class A, ask yourself:

1. **What is the domain relationship?** Does A have, know, use, manage, or own B?
2. **Multiplicity:** 1–1, 0–1, 1–n, 0–n, or n–n?
3. **Required or optional?** Are `null`/empty allowed?
4. **Who creates B?** Does A create it itself, does the caller inject it, or is it created by a factory or repository?
5. **Who owns B?** Can multiple A instances reference the same B?
6. **Is B mutable?** How do mutations from A, B, or a third party affect each other?
7. **Does the field need `final`?** Is the relationship fixed, or does the reference need to change?
8. **What should the getter return?** The original mutable reference, a read-only view, a snapshot, an immutable value, or only computed data?
9. **Do B's contents need a defensive copy?** Is a shallow copy enough, or is a deep copy across the graph required?
10. **Is the relationship bidirectional?** Who guarantees that both sides stay synchronized?
11. **Are there multi-object invariants?** For example, a line belonging to an order, or an employee belonging to a department.
12. **Are there reference cycles?** How are `toString`, serialization, and graph traversal handled?
13. **What is the concurrency contract?** Can it be shared across threads?
14. **Who owns the resource/persistence lifecycle?** GC does not replace transaction/close.
15. **How are identity and equality defined?** Entity by ID or value object by content?
16. **Do tests verify the behavior?** Aliases, null, replacement, copying, getter mutation, and cycles.

## 26. Review Questions with Answers

**Question 1.** Does writing `class Customer { Address address; }` create an Address object yet?  
**Answer:** No. That is a reference field declaration; if unassigned, the field's default value is null.

**Question 2.** How many Address objects does `Address a = new Address(); Address b = a;` create?  
**Answer:** One. Both variables hold the same reference value.

**Question 3.** Is `Address b = new Address();` different from `b = a`?  
**Answer:** Yes. `new` creates a new object; assignment copies an existing reference.

**Question 4.** If `Customer.address` holds a reference to a mutable Address provided by the caller and the caller changes the city, will Customer see the change?  
**Answer:** Possibly yes, if it still references the same object and no copy was made.

**Question 5.** Does `private final Address address` prevent `address.setCity(...)`?  
**Answer:** Not by itself. Final locks the reference field, not the state of Address.

**Question 6.** What does `customer.address = new Address(...)` (when field write access is permitted) do?  
**Answer:** It replaces the reference of the customer.address field; it does not mutate the old Address object.

**Question 7.** Can `Customer` hold a field of the `Notifier` interface type?  
**Answer:** Yes. The field can reference an instance of a class that implements Notifier.

**Question 8.** How does `Car has Engine` differ from `ElectricCar extends Car`?  
**Answer:** One is an object/has-a relationship (composition/association); the other is a type/is-a relationship (inheritance).

**Question 9.** Does a `Team` containing `List<Member>` by itself prove strong composition?  
**Answer:** No. Ownership, sharing, and lifecycle are design contracts, not determined by List syntax alone.

**Question 10.** Why can returning an internal mutable `ArrayList` from a getter be dangerous?  
**Answer:** The caller receives the same reference and can add/remove/modify the list structure directly.

**Question 11.** Does `List.copyOf` automatically deep-copy mutable `Member` objects?  
**Answer:** No. It protects the list snapshot structure, but references to Member objects may still be shared.

**Question 12.** Does `Collections.unmodifiableList(source)` automatically preserve the old snapshot when `source.add(...)` is called?  
**Answer:** It does not guarantee a snapshot; an unmodifiable view can reflect changes in the backing list.

**Question 13.** Why does constructor injection help a class with a required dependency?  
**Answer:** It forces the caller to supply the dependency at creation time, and the class can check for non-null before object construction finishes.

**Question 14.** If B has mutable state, what is needed for A to keep an independent snapshot?  
**Answer:** Defensively copy the input when receiving it and avoid exposing the internal mutable reference when returning, copying to the required depth.

**Question 15.** How can `record Address(String city)` with a String component be shared more safely than a mutable Address?  
**Answer:** A record has an immutable component reference and String is immutable; there is no setter to modify city in place.

**Question 16.** Is a record containing `int[]` guaranteed to be deeply immutable?  
**Answer:** No. Arrays are mutable; copying in the constructor/accessor is needed if you want to prevent aliasing.

**Question 17.** Does Java pass the parameter `Person p` by reference or by value?  
**Answer:** Java passes **a copy of the reference value**. A method can mutate the object through p, but reassigning p does not reassign the caller's variable.

**Question 18.** What do `a == b` and `a.equals(b)` check for references?  
**Answer:** `==` compares identity; `equals` follows the object's equality implementation/contract.

**Question 19.** What happens with two Address Java records that have the same city but are created with separate `new` expressions?  
**Answer:** `==` is generally false because they are different instances; `equals` can be true because they have the same components.

**Question 20.** Why do an Employee and a Department holding bidirectional references not stay synchronized automatically?  
**Answer:** Both sides have separate fields/lists; Java does not automatically update the other side. Controlled methods are required.

**Question 21.** A references B and B references A: are both guaranteed to be a memory leak?  
**Answer:** No. GC evaluates reachability from roots; an unreachable graph can be reclaimed even if it has a cycle.

**Question 22.** Does removing an object from a list automatically close its resources or delete a DB record?  
**Answer:** No. That is a change to a collection's references, not an automatic lifecycle or persistence operation.

**Question 23.** What does a static cache holding a reference to an object graph do to memory lifetimes?  
**Answer:** It can keep the graph reachable and occupy memory longer than necessary; an eviction policy/lifecycle is needed.

**Question 24.** Are two threads sharing a mutable object B through two holders automatically thread-safe because the holders keep their fields private?  
**Answer:** No. B is still shared; a thread-safe contract or synchronization/immutability is required.

**Question 25.** Should an `Address` field be nullable or required?  
**Answer:** It depends on the domain: if required, validate in the constructor; if optional, document the absent semantics clearly.

**Question 26.** How do you avoid recursive `toString()` in a graph with cycles?  
**Answer:** Print identifiers/summary fields, limit depth, or use a visited set when traversing the graph.

**Question 27.** If Order creates immutable `OrderLine` objects and only returns an unmodifiable list snapshot, is that enough to ensure an OrderLine belongs to only one Order?  
**Answer:** Not yet. Ownership/domain identity requires an explicit contract; the line value object could still be used elsewhere.

**Question 28.** When should composition via an interface be preferred over inheritance?  
**Answer:** When a class needs to **use/delegate** behavior to a dependency whose implementation can change, rather than having a true “is-a” type relationship.

## References

- Java Language Specification (Java SE 17), [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference types and values.
- Java Language Specification, [`4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.5): default `null` for reference fields.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object creation.
- Java Language Specification, [`15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `new` expressions.
- Java Language Specification, [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): method calls and runtime dispatch.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): field declarations, `final`.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable list snapshot.
- Java Platform API, [`Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): required reference validation.
- Java Platform API, [`Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): representing potentially absent values in an API.
- Java Platform API, [`Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): equality contract.

## Summary

An object **holds a reference to another object** through a reference-typed field. This creates a **has-a/association** relationship and enables objects to collaborate; it does **not** automatically create, copy, exclusively own, or destroy the referenced object. Multiple references can point to the same object (*aliasing*), so modifying the state of a shared object is observed wherever those references are held.

Design relationships with explicit decisions: **required or optional**, **where objects are created**, **shared or owned**, **mutable or immutable**, **whether getters return the original/a view/a snapshot**, **whether two-way synchronization is needed**, and **what thread-safety/lifecycle rules apply**. `private` and `final` protect at the field level but do not automatically make an object graph immutable. Constructor injection, immutable records, defensive copying, and controlled methods are key tools for modeling class relationships accurately, testably, and maintainably.
