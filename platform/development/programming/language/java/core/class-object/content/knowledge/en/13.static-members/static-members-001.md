# Class Members and Instance Members in Java

In Java, a class can declare **class members** (typically associated with the `static` keyword) and **instance members** (without `static`). These two groups differ in **what owns the state, when they are used, how methods are called, and their behavior when multiple instances exist**.

An instance field such as `account.balance` belongs to a specific account object; each `new Account(...)` has its own `balance` value. Conversely, a static field such as `Account.createdCount` represents a value associated with the class at runtime and is jointly observed by instances of that class within a corresponding class-loading context.

**Foundational rules:**

- `static` field: state **associated with the class**, without creating a separate copy for each object.
- Instance field: state **associated with an object**; each object has its own instance fields.
- `static` method: called via the **class name** and has no implicit `this` receiver.
- Instance method: called on **an object** and can use `this` to read/write the current object's state.
- A static method can still work with objects through **explicit parameters or references**; "static" does not mean it cannot touch any object.
- Static state is shared **per actual class and associated class loader scope**; it does not mean an absolute shared variable across all Java processes.

This lesson applies to **Java 17+**, focusing on fields/methods, initialization, access, inheritance, API design, memory, and concurrency. Complete programs include file names, `javac`/`java` commands, and reliable stdout for self-verification.

## 1. Classes, objects, and two kinds of members

When declaring:

~~~java
class Student {
    static String schoolName = "Java Academy";
    String name;
    int grade;
}
~~~

We have:

- `schoolName` is a **static field**: shared information placed on the `Student` class.
- `name` and `grade` are **instance fields**: values belonging to each `Student` instance.

This is a class declaration snippet, without a standalone runnable `main` method.

Inside a method:

~~~java
Student first = new Student();
Student second = new Student();

first.name = "Lan";
first.grade = 9;

second.name = "Mai";
second.grade = 8;

System.out.println(Student.schoolName);
~~~

`first` and `second` point to **two different objects**, so modifying `first.grade` does not automatically modify `second.grade`. However, both objects belong to the same `Student` class used by this source code, and the shared information `Student.schoolName` is not created as two separate copies for the two objects.

Conceptual diagram:

~~~text
Class Student
  static schoolName = "Java Academy"
             |
             | shared per class
             |
      +------+------+
      |             |
      v             v
Student A       Student B
name = "Lan"    name = "Mai"
grade = 9       grade = 8
~~~

The diagram illustrates **logical ownership relationships**, not physical memory addresses or how the JVM is required to lay out objects. Not every static field necessarily "resides in the Method Area" in the way a simplified illustration suggests; the specific memory location is a JVM implementation detail.

## 2. Quick comparison table: static and instance

| Criterion | `static` member | Instance member |
| --- | --- | --- |
| Field declaration | `static int total;` | `int value;` |
| Logical ownership level | The class at runtime | Each object |
| Number of field copies when creating multiple objects | One state on the class per class-loading context | One copy in each object |
| Recommended way to access | `ClassName.field`, `ClassName.method()` | `object.field`, `object.method()` |
| Object required to call method? | No | Yes, a normal receiver object |
| Is `this` present in method? | No | Yes, in an instance context |
| Can read instance fields directly? | No, an object/receiver is required | Can use `this.field` |
| Can read static fields? | Yes | Yes, though `ClassName.field` should be specified explicitly |
| Polymorphic overriding? | Static methods undergo **hiding**, not overriding | Eligible instance methods can be overridden |
| Field initialization | When the class/interface is initialized according to the relevant rules | When each object is initialized |
| Shared state risks | Shared mutable state, race conditions, coupling | A mutable object can still be shared across multiple threads |

A more accurate observation than "static only has one copy in the JVM": **a class can be defined/initialized across different class loader scopes**, and each corresponding runtime class has its own static state. In a simple Core Java program with a single class loader, you typically observe one set of static fields for that class.

## 3. Static field: shared data belonging to the class

Example of a counter for the number of objects created:

~~~java
class Order {
    private static int createdCount;

    private final String orderId;

    Order(String orderId) {
        this.orderId = orderId;
        createdCount++;
    }

    static int getCreatedCount() {
        return createdCount;
    }

    String getOrderId() {
        return orderId;
    }
}
~~~

`createdCount` does not belong to any single `Order`. When multiple constructor calls succeed and execute `createdCount++`, they update the same static field together.

`orderId` is a `final` instance field: an order has its own ID and does not automatically match another order. `final` only prevents reassigning the reference field under Java rules; **it does not change the instance semantics**.

### 3.1. Accessing via the class name without creating an instance

~~~java
System.out.println(Order.getCreatedCount());
~~~

Calling a static method via `Order` does not require `new Order(...)`. This is a code fragment inside a method.

A few familiar static members in the JDK:

- `Math.max(a, b)` is a static method that computes a value.
- `Integer.parseInt("42")` is a static method that converts a string.
- `System.out` is a static field whose value references a `PrintStream` object.
- `Collections.emptyList()` is a static factory method in a utility class.
- `LocalDate.now()` is a static factory method that creates/obtains a date value.

Static methods do not have to be purely mathematical; they can create objects, read system data, or perform other effects according to their contract. `static` describes receiver/class membership; **it does not guarantee that a method is pure or free of side effects**.

### 3.2. A static field does not mean "as many copies as objects"

~~~java
class Flag {
    static boolean enabled = true;
}

Flag a = new Flag();
Flag b = new Flag();

Flag.enabled = false;
~~~

After the assignment, code working with both `a` and `b` can observe `Flag.enabled == false` within the same runtime class. There are not two separate `enabled` values simply because there are two objects.

## 4. Instance field: data belonging to each object

~~~java
class Counter {
    private int value;

    void increment() {
        this.value++;
    }

    int current() {
        return this.value;
    }
}
~~~

Example fragment:

~~~java
Counter a = new Counter();
Counter b = new Counter();

a.increment();
a.increment();
b.increment();

System.out.println(a.current()); // 2
System.out.println(b.current()); // 1
~~~

The two variables reference two Counter objects, so they have separate state. In `a.increment()`, `this` is instance `a`; in `b.increment()`, `this` is instance `b`.

**Important:** if you write `Counter alias = a;` and then call `alias.increment()`, the value of `a.current()` also increases, because `alias` and `a` point to **the same object**. Instance state is independent **across objects**, not across reference variables.

### 4.1. Can a static field and an instance field have the same name?

Within **the same class**, you cannot declare two fields with the same name that differ only by `static`:

~~~java
class Wrong {
    static int value;

    // int value; // Compile error: a field with the same name is already declared
}
~~~

A field does not have two "versions", static and instance, depending on how it is accessed. Different classes can declare fields with the same name; in inheritance, field hiding has its own rules, but you should not exploit it merely to make state confusing.

## 5. Complete example: shared static, independent instances

Create the file **`StaticAndInstanceDemo.java`**:

~~~java
public class StaticAndInstanceDemo {
    static final class Ticket {
        private static int issuedCount;
        private static String prefix = "T";

        private final int number;
        private int usedCount;

        Ticket() {
            number = ++issuedCount;
        }

        void use() {
            this.usedCount++;
        }

        String description() {
            return prefix + number + "/used=" + usedCount;
        }

        static int totalIssued() {
            return issuedCount;
        }

        static void setPrefix(String nextPrefix) {
            if (nextPrefix == null || nextPrefix.isBlank()) {
                throw new IllegalArgumentException(
                        "Prefix không hợp lệ");
            }
            prefix = nextPrefix;
        }
    }

    public static void main(String[] args) {
        System.out.println("Initial issued = " + Ticket.totalIssued());

        Ticket first = new Ticket();
        Ticket second = new Ticket();

        first.use();
        first.use();
        second.use();

        System.out.println("First = " + first.description());
        System.out.println("Second = " + second.description());
        System.out.println("Total issued = " + Ticket.totalIssued());

        Ticket alias = first;
        alias.use();

        System.out.println("Same object = " + (alias == first));
        System.out.println("After alias = " + first.description());

        Ticket.setPrefix("X");

        System.out.println("First renamed = " + first.description());
        System.out.println("Second renamed = " + second.description());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 StaticAndInstanceDemo.java
java StaticAndInstanceDemo
~~~

**Exact stdout:**

~~~text
Initial issued = 0
First = T1/used=2
Second = T2/used=1
Total issued = 2
Same object = true
After alias = T1/used=3
First renamed = X1/used=3
Second renamed = X2/used=1
~~~

Analysis:

1. `Ticket.totalIssued()` is a static method. It reads `issuedCount`, initially 0, **without needing to create a Ticket instance**.
2. Each call to the `Ticket()` constructor executes `++issuedCount` on the same static field. `first.number` receives 1, and `second.number` receives 2. The two `number` instance fields belong separately to each object.
3. Calling `first.use()` twice modifies only `first.usedCount`, while calling `second.use()` once modifies only `second.usedCount`.
4. `Ticket.totalIssued()` returns 2 because two Ticket objects have been created via the constructor.
5. `alias = first` copies the reference. `alias.use()` modifies `first`'s actual object, so first's usage count increases to 3. This is **aliasing of an instance object**, unrelated to static.
6. `Ticket.setPrefix("X")` changes a shared static field. Both objects now format their labels with `X`, yet their instance numbers and used counts remain independent.
7. No instance setter was called to change the prefix of each Ticket: the change to shared state takes effect when the `description()` method reads `prefix` again.

**Practical limitation:** `issuedCount++` is not safe when multiple threads concurrently create Tickets. This program demonstrates single-threaded execution. If IDs must be unique in a concurrent environment, an atomic/synchronization solution or a more suitable ID allocation mechanism is required.

## 6. Static methods do not have `this`

An **instance method** is called on a receiver:

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    String greeting() {
        return "Chào " + this.name;
    }
}
~~~

`this` in `greeting()` represents the object receiving the call. Conversely, a static method is not called on a default current instance:

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    static String normalize(String rawName) {
        // return this.name; // Compile error: this in a static context
        return rawName.trim();
    }
}
~~~

`normalize` is static, so it does not have `this`. It can still operate on a String object through the `rawName` parameter. `rawName.trim()` calls String's instance method on the explicit receiver `rawName`, **not on Person's `this`**.

### 6.1. Static methods can still access instance members through a specific object

~~~java
class Employee {
    private final String name;

    Employee(String name) {
        this.name = name;
    }

    static String display(Employee employee) {
        return employee.name;
    }
}
~~~

This is a declaration snippet. `display(Employee employee)` is a static method, yet it uses the **parameter reference** `employee` as the receiver to read an instance field. Because the code is declared inside `Employee`, it has permission to read the private field of an Employee object according to access control rules.

It is **incorrect** to say "a static method is not allowed to read instance fields in any case". The accurate way to put it is that **a static method cannot use an instance field without an appropriate receiver**, and cannot use `this` because there is no current instance.

### 6.2. Instance methods can use static members

~~~java
class Device {
    private static String manufacturer = "ACME";
    private final String serial;

    Device(String serial) {
        this.serial = serial;
    }

    String label() {
        return manufacturer + ":" + serial;
    }
}
~~~

`label()` is an instance method that reads the static field `manufacturer` and the instance field `serial`. There is no language restriction preventing combining both, provided visibility and other conditions are satisfied.

Although within the same class you can omit the prefix for a static field, for maintainable code consider writing `Device.manufacturer` rather than `this.manufacturer` so readers recognize that the state belongs to the class.

## 7. Accessing static members via the class name, not via an instance

Java **allows** many static calls through an object expression:

~~~java
class Example {
    static int count;

    static void report() {
        System.out.println(count);
    }
}

Example e = new Example();
e.report(); // Compiles, but should not be used
~~~

This illustrative fragment is valid in many cases, but the compiler/IDE typically warns that a static method should be called via the class name:

~~~java
Example.report();
~~~

Why?

- `Example.report()` clearly states that the method belongs to the class.
- `e.report()` easily misleads readers into thinking the call depends on instance `e` or involves dynamic dispatch.
- Static methods **do not perform polymorphic instance overriding** like instance methods.
- Accessing a static member through an expression can involve **evaluating the left-hand expression**; it should not be used to infer that a real instance is being processed by the method.

### 7.1. Common pitfall: a static call via a `null` variable

Example:

~~~java
class Utility {
    static String answer() {
        return "OK";
    }
}

Utility ref = null;
System.out.println(ref.answer()); // OK
~~~

This is a code fragment. The call `ref.answer()` compiles and prints `OK` because `answer` is a static method; by itself it **does not dereference a Utility object like an instance method**. If the receiver expression is simply the variable `ref`, that expression is evaluated, yet it does not require a non-null object to execute the static method.

However, **do not use `ref.answer()` to teach that null is safe when calling methods**. With an instance method, `ref.instanceMethod()` will throw a `NullPointerException`. Even for a static call, a complex expression on the left side of the dot can still have side effects or throw an exception when evaluated. Writing `Utility.answer()` is the standard and clearer approach.

## 8. When static state and instance state are initialized

A common question is: "When is a static field created, and when is an instance field created?"

At the Java conceptual level:

- **Class initialization** executes static assignments and static initializer blocks according to language rules when the class is initialized; it does not mean "every class on the classpath runs its initializers as soon as the JVM starts".
- **Instance initialization** occurs for **each object** created normally via `new`, following the corresponding constructor and initializer chain.
- Before the appropriate initializer runs, a field holds the **default value** of its type (`0`, `false`, `null`...).
- When a superclass and subclass both have initializers, each kind follows specific initialization rules and a superclass/subclass constructor order; you should not infer the order solely from the order of source files.

### 8.1. Static field initializers and static initialization blocks

~~~java
class Configuration {
    static int timeoutSeconds = 10;

    static {
        timeoutSeconds += 5;
    }
}
~~~

When `Configuration` is initialized according to Java rules, the field initializer sets `timeoutSeconds` to 10 and then the static initializer adds 5; the final value is 15. The static initialization **does not run again for each `new Configuration()`** in a normally initialized class.

### 8.2. Instance field initializers and instance initialization blocks

~~~java
class Session {
    int retries = 3;

    {
        retries += 1;
    }

    Session(int retries) {
        this.retries = retries;
    }
}
~~~

When `new Session(7)` initializes successfully, the instance initializer sets `retries` to 4 and then the constructor body assigns 7. When another object is created, the instance initializer executes again for the new object. That is a **per-instance** rule, distinct from static initialization.

## 9. Runnable program: static initializer runs only once, instance initializer runs per object

Save the file **`InitializationDemo.java`**:

~~~java
public class InitializationDemo {
    static final class Member {
        private static int createdCount;

        static {
            System.out.println("Static init");
        }

        private final int id;

        {
            System.out.println("Instance init");
        }

        Member() {
            id = ++createdCount;
            System.out.println("Constructor " + id);
        }

        static int created() {
            return createdCount;
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        System.out.println("Before first access");
        System.out.println("Count = " + Member.created());

        Member first = new Member();
        Member second = new Member();

        System.out.println("IDs = "
                + first.id() + "," + second.id());
        System.out.println("Final count = " + Member.created());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 InitializationDemo.java
java InitializationDemo
~~~

**Exact stdout:**

~~~text
Before first access
Static init
Count = 0
Instance init
Constructor 1
Instance init
Constructor 2
IDs = 1,2
Final count = 2
~~~

Analysis:

1. Before calling `Member.created()`, the program prints `Before first access`.
2. Calling the static method `Member.created()` is a case of **active use** that triggers initialization of the Member class if not already initialized; the static initializer prints `Static init` exactly once for that runtime class.
3. `Member.created()` returns 0 because no Member object has been created yet.
4. For each `new Member()`, the instance initializer prints `Instance init`, and then the constructor increments static `createdCount` and prints the object sequence number.
5. Creating two Member objects causes the instance initializer to run twice; the static initializer does not run again.
6. `id` is a final instance field, so each object holds id 1 or 2; `createdCount` is a shared static field with value 2.

Note: `Member.createdCount++` used in this example **is not suitable for concurrent object creation without synchronization**. This lesson only observes the initialization lifecycle in a single-threaded program.

### 9.1. Static initialization and understanding "initialized once" accurately

A runtime class is managed by the JVM within a corresponding class loader context; the class initialization process is coordinated according to JVM rules. "Once" should not be interpreted as "once across all class loaders, all JVM processes, or all application runs".

If class initialization fails, subsequent uses may encounter errors related to class initialization (for example, `ExceptionInInitializerError` and errors from using a class in an erroneous initialization state); **do not** assume that the JVM will retry running the static initializer until it succeeds.

## 10. `static final`: constants and shared references

The `static` modifier indicates that the member belongs to the class; `final` has its own rules regarding reassignability.

~~~java
class Limits {
    public static final int MAX_ITEMS = 100;
    public static final String DEFAULT_LABEL = "general";
}
~~~

Primitive or String values that satisfy Java's **constant variable** requirements can be **compile-time constants**. Referencing them from another class may cause the compiler to inline their values, affecting class initialization and binary compatibility when changing libraries.

### 10.1. A static final reference does not mean an immutable object

~~~java
import java.util.ArrayList;
import java.util.List;

class SharedCatalog {
    static final List<String> ITEMS = new ArrayList<>();
}
~~~

`ITEMS` is a **static final reference**: the `ITEMS` field cannot normally be reassigned after initialization, yet `ITEMS.add("A")` can still modify the **shared List object** if it is mutable.

Compare:

~~~java
class Constants {
    static final java.util.List<String> DEFAULT_TAGS =
            java.util.List.of("JAVA", "CORE");
}
~~~

`List.of(...)` creates a List that cannot be modified via its API; combined with immutable String elements, this is a more suitable shared constant-style value. However, mutable element types still require considering deep mutability.

**`static final` has two independent parts:**
- `static`: the field belongs to the class.
- `final`: restricts reassigning the reference/value field after initialization under Java rules.

### 10.2. Naming conventions and constant design

`UPPER_SNAKE_CASE` is typically used for truly stable constant fields, such as `MAX_RETRIES`. Not every static field is a constant; a changing `static int counter` should not necessarily be named in all uppercase.

Public static mutable fields often cause **global coupling**. Prefer `private static`, controlled APIs, or dependency injection depending on your needs.

## 11. Static methods and instance methods in inheritance

Here is an important distinction:

- **Instance methods** can be **overridden**, and Java selects the implementation corresponding to the runtime object when dynamic dispatch applies.
- **Static methods** are **hidden** by an appropriate static method with the same signature in a subclass, **not overridden** under ordinary polymorphism.
- Calling a static method via a reference variable can be valid, but the selected method is chosen based on the **compile-time type** of the expression, not the runtime class of the object.
- `@Override` is not used to annotate static method hiding.

### 11.1. Runnable program: overriding differs from static method hiding

Create the file **`StaticHidingDemo.java`**:

~~~java
public class StaticHidingDemo {
    static class Parent {
        static String category() {
            return "Parent-static";
        }

        String label() {
            return "Parent-instance";
        }
    }

    static final class Child extends Parent {
        static String category() {
            return "Child-static";
        }

        @Override
        String label() {
            return "Child-instance";
        }
    }

    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent polymorphic = new Child();
        Child child = new Child();

        System.out.println("Parent class = " + Parent.category());
        System.out.println("Child class = " + Child.category());

        System.out.println("Parent ref static = "
                + polymorphic.category());
        System.out.println("Child ref static = " + child.category());

        System.out.println("Parent instance = " + parent.label());
        System.out.println("Polymorphic instance = "
                + polymorphic.label());
        System.out.println("Child instance = " + child.label());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StaticHidingDemo.java
java StaticHidingDemo
~~~

**Exact stdout:**

~~~text
Parent class = Parent-static
Child class = Child-static
Parent ref static = Parent-static
Child ref static = Child-static
Parent instance = Parent-instance
Polymorphic instance = Child-instance
Child instance = Child-instance
~~~

Explanation:

1. `Parent.category()` and `Child.category()` are static methods; they belong to their two respective classes, and Child hides Parent's static method with the same signature.
2. `polymorphic` has a **declared type of `Parent`** but points to a `Child` object. `polymorphic.category()` still selects **Parent.category()** according to the compile-time type Parent. Writing it via an object like this is allowed but hard to read; in real APIs you should use `Parent.category()`.
3. `child.category()` selects Child.category() because the compile-time type is Child.
4. `polymorphic.label()` is an **instance method call**. Because the runtime receiver is Child, dynamic dispatch selects `Child.label()`, printing `Child-instance`.
5. The pair of results `Parent ref static = Parent-static` and `Polymorphic instance = Child-instance` on the same `polymorphic` variable demonstrates the difference between **static hiding** and **instance overriding**.

### 11.2. A static method does not override an instance method with the same signature

The following cases cause compilation errors if declared to attempt changing static/instance status along an overriding path:

~~~java
class Parent {
    void run() {
    }
}

class Child extends Parent {
    // static void run() {} // Cannot hide an instance method
}
~~~

Conversely, you cannot use an instance method to override an eligible static method from a superclass. Static/instance membership is not a property you can freely switch when inheriting a method with the same signature.

## 12. Static fields in inheritance: do not assume a subclass gets "its own copy"

Suppose:

~~~java
class Base {
    static int total;
}

class Derived extends Base {
}
~~~

Because Derived does not declare a new field with the same name, referencing `Derived.total` (if access permissions allow) actually refers to the static field **declared in Base**. There is no separate `total` copy automatically duplicated simply by `extends Base`.

If Derived **declares its own** separate static field `total`, there will be two distinct fields via the field hiding mechanism:

~~~java
class Base {
    static int total = 10;
}

class Derived extends Base {
    static int total = 20;
}
~~~

Accessing `Base.total` yields 10 and `Derived.total` yields 20. These are **two separate declarations**, not two per-object copies.

Avoid intentionally hiding static fields with the same name unless there is a clear reason: code accessed through different static types can see separate fields, causing confusion with instance state or inheritance.

## 13. A static nested class still has its own instances

A **static nested class** is a member type associated with its enclosing class in terms of declaration; however, each object created from a static nested class still has **its own instance fields**.

~~~java
class Container {
    private static int created;

    static class Item {
        private final int id;

        Item() {
            this.id = ++created;
        }

        int id() {
            return id;
        }
    }
}
~~~

Even though `Item` is a **static nested class**, `Item`'s `id` is an **instance field**, and each `new Container.Item()` has its own `id`. `Container.created` is Container's static field updated by the Item constructors.

Syntax:

~~~java
Container.Item a = new Container.Item();
Container.Item b = new Container.Item();
~~~

You do not need to create `Container outer = new Container()` to instantiate an `Item`, because a static nested class does not hold an **implicit enclosing Container instance** like a non-static inner class.

### 13.1. Difference from a non-static inner class

~~~java
class House {
    private String address;

    House(String address) {
        this.address = address;
    }

    class Room {
        String where() {
            return House.this.address;
        }
    }
}
~~~

Creating a non-static inner instance from an outer instance:

~~~java
House house = new House("Hà Nội");
House.Room room = house.new Room();
~~~

`House.this` inside Room points to the enclosing `House` object. A `static nested class` does not automatically have an outer `this` like that.

### 13.2. Static nested classes can declare both static and instance members

~~~java
class Outer {
    static class Nested {
        static int shared;
        int own;

        static void resetShared() {
            shared = 0;
        }

        void increaseOwn() {
            own++;
        }
    }
}
~~~

The `static` modifier on a nested class **does not turn all of its fields and methods into static members**. You must check the modifier on each member.

## 14. Static in interfaces, enums, and top-level classes

### 14.1. Interfaces have static fields and static methods under their own rules

~~~java
interface Settings {
    int MAX_RETRIES = 3; // implicitly public static final

    static boolean validRetryCount(int n) {
        return n >= 0 && n <= MAX_RETRIES;
    }
}
~~~

In an interface, the `MAX_RETRIES` field is implicitly `public static final`. The interface static method `Settings.validRetryCount(2)` is called via the appropriate interface name; it is not inherited as an instance method of an implementing class the way a default method can be provided.

An interface also has default/abstract instance methods depending on declarations. **Not every method of an interface is static** just because interface fields are static by default.

### 14.2. Enum constants are instances, and enums can still have static members

~~~java
enum Direction {
    NORTH, SOUTH;

    static boolean opposite(Direction a, Direction b) {
        return (a == NORTH && b == SOUTH)
                || (a == SOUTH && b == NORTH);
    }
}
~~~

`NORTH` and `SOUTH` are enum constants — each is an instance of the enum type; `opposite` is a static method associated with the enum class. The static-vs-instance model still applies, even though enums have a special instance creation mechanism.

### 14.3. Do not declare a top-level class with the `static` keyword

~~~java
// static class Utility {} // Invalid at the top level
~~~

`static` is allowed on a **member nested class** in a valid context, not on a top-level class. A top-level class can contain static fields/methods, but the top-level class declaration itself cannot have `static` added.

## 15. Static utility methods, factories, and when to use an instance method

### 15.1. Utility methods independent of object state

A computation that depends only on its arguments is often suitable as a static method:

~~~java
final class NumberRules {
    private NumberRules() {
        // Prevent creating instances just to call utility methods.
    }

    static boolean isPositive(int n) {
        return n > 0;
    }

    static int safeSum(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

`NumberRules.isPositive(3)` does not need a `NumberRules` object because the check does not rely on instance state. The `private` constructor prevents ordinary object creation from code outside the class, expressing the utility intent.

However, **not every** method that does not reference an existing field must be static. You may choose an instance method because it is behavior in an interface, requires polymorphism/test doubles, or belongs to a service object that has dependencies.

### 15.2. Static factories that create and return objects

~~~java
class User {
    private final String username;

    private User(String username) {
        this.username = username;
    }

    static User of(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username rỗng");
        }
        return new User(username);
    }

    String username() {
        return username;
    }
}
~~~

`User.of(...)` is a static method, yet **it can certainly create a User instance** and return a reference to that instance. Static does not mean "unrelated to objects"; it means the factory call does not require an already-existing User receiver.

A static factory can be given a meaningful name such as `of`, `from`, or `create`; validation conditions still need to be enforced.

### 15.3. Instance behavior when depending on current state

~~~java
class PriceTag {
    private final long unitPrice;

    PriceTag(long unitPrice) {
        this.unitPrice = unitPrice;
    }

    long priceFor(int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`priceFor` relies on the `unitPrice` of a specific object, so it is naturally an instance method. If written as static, you would have to pass `unitPrice` (or the entire object) into the method explicitly; that can fit a utility API, though it is not necessarily as clear as behavior on `PriceTag` itself.

## 16. Static state does not replace dependency injection

An approach that easily creates coupling is using a static mutable field as a holder for global configuration/service objects:

~~~java
class GlobalConfig {
    static String endpoint = "https://example.invalid";
}
~~~

Code in many places reading/writing `GlobalConfig.endpoint` will depend on **shared mutable global state**. This easily causes tests to interfere with one another, makes test execution order determine outcomes, and prevents multiple components from using independent configurations.

An option when multiple different configurations are needed:

~~~java
class ApiClient {
    private final String endpoint;

    ApiClient(String endpoint) {
        this.endpoint = java.util.Objects.requireNonNull(endpoint);
    }

    String endpoint() {
        return endpoint;
    }
}
~~~

Each `ApiClient` instance holds its own state; tests can create multiple clients with different endpoints. A static factory can assist with creating ApiClient instances, yet a shared static mutable dependency is not mandatory by default.

**When should static shared state be used?** When the data is genuinely a shared property of the class and has a clear lifecycle/synchronization policy: statistics, controlled caches, immutable constants, or carefully designed factories/registries.

**When should it not be used?** When the data describes each user/request/session/order, involves multiple independent configurations, or requires isolation between tests and application components. That kind of data typically fits instance state or an explicit context.

## 17. Concurrency: multiple instances still modify the same static field

One of the major risks of mutable static fields is **sharing across multiple threads**.

~~~java
class UnsafeStats {
    static int requests;

    static void record() {
        requests++;
    }
}
~~~

If multiple threads call `UnsafeStats.record()`, the expression `requests++` consists of read/compute/write steps, is **not atomic**, and can therefore suffer **lost updates**. `static` does not automatically provide a lock.

### 17.1. Using AtomicInteger for a shared counter

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class Stats {
    private static final AtomicInteger REQUESTS =
            new AtomicInteger();

    static int recordRequest() {
        return REQUESTS.incrementAndGet();
    }

    static int totalRequests() {
        return REQUESTS.get();
    }
}
~~~

`AtomicInteger` supports atomic increment operations on a shared value. `REQUESTS` is a static final reference to an AtomicInteger object, yet **the contents of the AtomicInteger still mutate in a controlled manner**.

If the count is only used for observing a system with very many threads, you can consider `LongAdder`; if a completely consistent snapshot across multiple fields is required, a single atomic counter is not sufficient.

### 17.2. Instance fields can also suffer race conditions

~~~java
class UnsafeAccount {
    private long balance;

    void add(long amount) {
        balance += amount;
    }
}
~~~

If **two threads share the same instance** `UnsafeAccount`, the instance field `balance` still has a race condition. `instance` does not mean thread-safe; it only allows **different objects to hold different state** when there is no shared reference.

### 17.3. `volatile` does not make a counter atomic

~~~java
class Stats {
    static volatile int count;

    static void increment() {
        count++; // Still not atomic
    }
}
~~~

`volatile` carries visibility and ordering semantics under the Java Memory Model; it does not automatically turn a read-modify-write sequence into an atomic operation. Choose an atomic variable, synchronized/lock, or an immutable design appropriate to your contract.

## 18. Class initialization and concurrency

The JVM coordinates **class initialization** so threads do not arbitrarily re-run static initializers concurrently like independent constructors. However, that **does not guarantee that every static field update after the class is initialized will be thread-safe**.

Example:

~~~java
class Settings {
    static final java.util.Map<String, String> FLAGS =
            java.util.Map.of("mode", "safe");
}
~~~

Static initialization creates and assigns a shared reference to an immutable map. Sharing constant-style state like this is easier to reason about than a static mutable HashMap updated by multiple threads.

Conversely:

~~~java
class Cache {
    static final java.util.Map<String, String> DATA =
            new java.util.HashMap<>();
}
~~~

`DATA` is a static final reference, yet the HashMap object is still mutable. Threads sharing a HashMap without appropriate synchronization can encounter race conditions and logic bugs. If a concurrent map is needed, consider `ConcurrentHashMap` along with the necessary thread-safe operations, or an immutable snapshots model.

## 19. Static fields and garbage collection

A static field referencing an object can contribute to **keeping the object reachable** while the corresponding class/static field remains accessible:

~~~java
class Holder {
    static Object current;
}
~~~

If code writes `Holder.current = new Object();`, the new object is kept referenced by the static field. If replaced with `Holder.current = null;`, you only **remove one reference path**. The object may still have other reference paths; Java does not guarantee immediate collection.

Common consequences:

- An unboundedly accumulating static collection can cause a logical memory leak even though the garbage collector is working properly.
- Registering listeners or caching via static fields can keep objects alive longer than expected.
- A static singleton/service has a lifecycle that requires managing its own resources; garbage collection will not automatically close files/sockets/database connections if you do not design appropriate cleanup.
- Class unloading/class loader lifecycles in plugin/container environments can be affected by remaining references. This is an advanced issue and should not be conflated with the scope of "a single JVM-wide static field".

An instance field can also keep an object reachable, but its lifetime is tied to **the object owning the field** and the entire corresponding reference chain. With a static field, broad sharing requires paying attention to long-lived data retention.

## 20. The static `main` method and why the entry point is typically static

In a typical Java program:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

`main` is static so that the Java launcher can call the entry point per the contract without needing to instantiate a `Hello` instance first. That does not mean an application must write every method as static:

~~~java
public class Hello {
    private final String audience;

    Hello(String audience) {
        this.audience = audience;
    }

    void greet() {
        System.out.println("Chào " + audience);
    }

    public static void main(String[] args) {
        Hello hello = new Hello("Java");
        hello.greet();
    }
}
~~~

In `main`, the code creates a `Hello` instance and then calls the instance method `greet()` on that object. The static entry point is only the **starting point**, not a replacement for object-oriented design.

## 21. Some common pitfalls with static

### 21.1. Using a static field for per-user data

~~~java
class WrongSession {
    static String currentUsername;
}
~~~

If a program has multiple sessions/users, a static field makes the data shared and can be overwritten by another session. A session should have an instance field:

~~~java
class UserSession {
    private final String username;

    UserSession(String username) {
        this.username = username;
    }
}
~~~

Each `UserSession` object carries its own username, avoiding lumping all users into the same field.

### 21.2. Confusing `static final` with deep immutability

`static final List<Item>` prevents reassigning the field reference, yet it does not prevent modifying `Item` objects if they are mutable. You need to design both elements and the collection according to the desired immutability contract.

### 21.3. Using `this` in a static context

~~~java
class Wrong {
    int value;

    static int read() {
        // return this.value; // No this available
        return 0;
    }
}
~~~

A static method needs to receive an object or have static state to operate on; there is no implicit receiver.

### 21.4. Thinking a constructor runs only once because the class is already initialized

Static initialization normally runs once for the runtime class, whereas **the constructor body runs for each object** created normally via an appropriate constructor invocation. A shared static field does not "prevent" new objects from existing.

### 21.5. Thinking static fields belong separately to each subclass

If a subclass inherits a static field declared in a superclass without declaring a new field, there is no separate "automatic static field copy" for the subclass. There are two fields only if there are two separate **declarations** under field hiding rules.

### 21.6. Thinking static methods are overridden

Static methods undergo hiding; they do not have dynamic dispatch based on the runtime object like instance methods. `Parent ref = new Child(); ref.staticMethod();` is resolved from the compile-time type of `ref`, even though calling through an instance is discouraged.

### 21.7. Using a static method to access an instance field without a receiver

~~~java
class Example {
    int value;

    static int read() {
        // return value; // Compile error: non-static variable...
        return 0;
    }
}
~~~

Adding `static` to a method does not turn the `value` variable into a static field. If you need an object's value, pass a reference or change the API to an appropriate instance method.

### 21.8. Static shared counter miscounting when a constructor throws an exception

~~~java
class Item {
    static int attempts;

    Item(String name) {
        attempts++;
        if (name == null) {
            throw new IllegalArgumentException("name null");
        }
    }
}
~~~

`attempts` counts **the number of times the increment executed**, not necessarily the number of objects constructed successfully. If you want to count successfully constructed objects, you must place the counting operation with the right semantics and consider side effects/exceptions; counting live objects requires yet another mechanism and cannot be inferred from a simple constructor counter.

### 21.9. Using `static` as an unbounded "global variable"

A shared mutable variable is convenient, yet it makes results depend on the order of use, especially across tests. Choose clear lifetime and ownership boundaries before deciding on class-level state.

## 22. Self-check exercises

**Question 1.** A class has `static int total` and `int value`. If you create three objects, how many field copies exist under the standard logical model?

**Answer:** One static `total` on the corresponding runtime class, and three `value` instance fields — one copy per object.

**Question 2.** Does `Counter a = new Counter(); Counter b = new Counter(); a.value++;` increase `b.value`?

**Answer:** No, if `value` is an instance field and `a` and `b` point to two different objects. If the two variables alias the same object, the change is visible through both.

**Question 3.** Can `static void report()` use `this.field`?

**Answer:** No. A static method has no current object `this`. It can read `object.field` through an appropriate receiver object if visibility allows.

**Question 4.** Does `Order.totalCreated()` require `new Order()` beforehand?

**Answer:** An Order object is not needed to call the static method. However, the corresponding class initialization may take place before the first active use.

**Question 5.** Does assigning `Device.manufacturer = "B"` automatically change a separate field inside each Device object?

**Answer:** No. This changes the shared static field. When instance methods read that static field, they can see the new value, yet no assignment happens to separate per-instance fields.

**Question 6.** Does `private static final List<String> DATA` guarantee that elements cannot be added to the list?

**Answer:** No. `final` prevents reassigning the field reference; if the List object is mutable and code with access holds a reference to it, it can still be modified.

**Question 7.** How do `Parent p = new Child(); p.staticMethod()` and `p.instanceMethod()` differ if Child hides/overrides them respectively?

**Answer:** The static method is selected according to the compile-time type Parent (hiding), while an overridable instance method can dispatch to the Child implementation according to the runtime type.

**Question 8.** Can a static nested class have instance fields?

**Answer:** Yes. `static` on a nested class means it has no implicit enclosing outer instance; each nested instance still has the instance fields declared in the nested class.

**Question 9.** Is a static field `int requests` automatically thread-safe if multiple threads call `requests++`?

**Answer:** No. Appropriate synchronization or an atomic variable is needed. Even instance fields can suffer race conditions when an object is shared across multiple threads.

**Question 10.** When Java calls static `main`, can the program use instance methods?

**Answer:** Yes. `main` can create objects or receive references and then call instance methods.

**Question 11.** If `class Base { static int total; }` and `class Child extends Base {}`, does `Child.total` have a new separate static field?

**Answer:** No. Without a new field declaration, it uses the field declared in Base according to access/inheritance rules; Java does not automatically duplicate fields just because a subclass exists.

**Question 12.** Does reading `public static final int LIMIT = 10` always trigger the static initializer of the declaring class?

**Answer:** Not necessarily. If it is a constant variable qualifying as a compile-time constant, the code may be inlined by the compiler; you should distinguish compile-time constant references from active uses that trigger class initialization.

**Question 13.** Can a static factory `User.of("Lan")` create a User instance?

**Answer:** Yes. A static method does not need a current User object to run; it can certainly call the constructor and return a reference to the new object.

**Question 14.** Does setting a local variable that held a reference to an object to `null` destroy the object and clear the class's static fields?

**Answer:** No. The local variable only loses one reference; the object may still have aliases. Static state has its own lifecycle tied to the runtime class/class loader and is not automatically cleared when an object or reference variable is no longer in use.

## 23. Checklist for choosing static or instance for a member

1. **Who does this data belong to?** Each user/order/session or an entire class/runtime component?
2. **Are multiple independent versions needed?** If so, prefer instance fields or dependency injection over a static mutable field.
3. **Does the method read/write the current object's state?** If so, an instance method usually expresses this more clearly.
4. **Is the method purely a utility computed from parameters?** A static method may fit if no polymorphic instance contract is needed.
5. **Is overriding/dynamic dispatch needed?** Static methods do not support overriding based on the runtime receiver.
6. **Is it a constant?** Consider `static final` with genuinely immutable data; do not assume a final reference makes a mutable object immutable.
7. **When is the class initialized?** Static initialization happens according to class initialization rules and does not re-run for each object.
8. **Is there shared mutable state?** Check test isolation, thread safety, lifecycle, and potential caching/memory retention.
9. **Is a clear class name used when calling static members?** Prefer `ClassName.member` over `instance.member` for static members.
10. **Is `this` used inside a static method?** It cannot be; an explicit object is needed if you want to operate on an instance.
11. **In inheritance, in which class is the static field/method declared?** Distinguish inherited fields, hiding, and overriding.
12. **In a nested class, is the static modifier on the type or the member?** A static nested class still has its own instance fields/methods.
13. **Are there multiple JVMs or class loaders?** Do not treat a static variable as system-wide state or an inter-process synchronization tool.
14. **Is there a framework/service that needs per-request state?** Avoid temporarily placing it in a shared static field just because passing dependencies is harder.

**Conclusion:** `static` members belong to the **class**, whereas non-static members belong to **each object**. Static fields help represent shared data; instance fields help each object maintain its own state. Static methods do not have `this` and do not dispatch by runtime receiver like instance methods; instance methods can use both their own state and shared state. Choosing the right kind of member based on **data ownership, lifecycle, mutability, polymorphism, and concurrency** makes Java code clear, correct, and maintainable.
