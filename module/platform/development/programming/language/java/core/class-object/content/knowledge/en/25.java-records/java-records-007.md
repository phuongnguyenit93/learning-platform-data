# Rules for Instance Fields, Inheritance, and Interface Implementation of Records in Java

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **record components** in the header from **instance fields** implicitly declared by the compiler; understand that `record Point(int x, int y)` already has two `private final` component fields and the accessors `x()`/`y()`.
- Explain why a record **cannot declare additional instance fields** or an **instance initializer block**, while it can still declare **static fields**, **static initializer blocks**, **static/instance methods**, and valid nested types.
- Distinguish *instance state belonging to each record object* from *static state belonging to the record class*, and know that static state does not participate in the generated `equals`/`hashCode`/`toString`.
- Understand that a record is **implicitly final** and directly extends `java.lang.Record`; you cannot write `extends SomeClass`, use it as a superclass for another subclass, or declare `abstract record`, `sealed record`, or `non-sealed record`.
- Understand the ability to specify `implements` for one or more interfaces, especially when a generated component accessor automatically satisfies an interface method signature.
- Use `@Override`, generic interfaces, interface default methods, sealed interfaces, and record implementations according to Java 17 rules.
- Know when you need to write a method yourself to implement an interface, because `record User(String name)` **only has the `name()` accessor**, and does not automatically generate `getName()` or `get()`.
- Write canonical/compact constructors properly to validate and normalize component values; understand that constructors do not grant permission to declare additional arbitrary instance state.
- Distinguish **final component references** from **deep immutability** of nested mutable objects, and handle them using immutable component types or defensive copies.
- Avoid confusing **inheritance of methods from Object/Record**, **inheritance of default methods from interfaces**, and **class inheritance prohibited for records**.
- Know the limitations of custom `equals`/`hashCode`, method overriding, interface contracts, and Java record reflection/serialization at the necessary level.
- Run Java 17+ programs yourself, compare stdout, fix compilation errors, and choose between a record or a normal class suited to the domain design.

> **Scope:** This lesson covers **instance fields, inheritance, and interface implementation of records**, not an overview of all Java record features. Snippets explicitly state when they do not have `main`; only sections with a filename, `javac`/`java` commands, and stdout are complete standalone programs. Java records have been a standard feature since Java 16; the examples use JDK 17 or later.

## 1. A Record Is Still a Class, but with Representation Restrictions

A record is a specialized kind of class used to describe a **group of named component values**. For example:

~~~java
record Point(int x, int y) {
}
~~~

The record header `(int x, int y)` tells the compiler that Point's *representation* consists of two components. According to JLS `8.10.3`, each component corresponds to:

- A `private final`, **non-static** **component field** with the same name and type as the component.
- A **public instance accessor** `x()` or `y()`, implicitly declared by the compiler if you do not declare a valid method yourself.
- A canonical constructor with parameters corresponding to the component list and state-management methods such as `equals`, `hashCode`, and `toString` according to record semantics.

In other words, this declaration is not “without fields”; it has **exactly the necessary instance fields specified by the header**. The difference from a normal class is that you cannot add instance fields beyond those the compiler has already declared for the components.

One way to visualize this (for understanding, **not Java source allowed to be declared at the same time**):

~~~java
// Conceptual simulation of what the compiler provides, DO NOT paste into the record:
private final int x;
private final int y;

public int x() { return x; }
public int y() { return y; }
~~~

Because components are part of the public structural contract, a record has a **transparent representation**: users reading the record header know the set of values stored according to the record model.

## 2. Program: Component Fields and Accessors Are Two Different Aspects

Save **`RecordComponentAccessDemo.java`**:

~~~java
public class RecordComponentAccessDemo {
    record Point(int x, int y) {
        int sum() {
            return x + y;
        }

        String summary() {
            return "x=" + x() + ",y=" + y();
        }
    }

    public static void main(String[] args) {
        Point point = new Point(3, 4);

        System.out.println(point);
        System.out.println("x()=" + point.x());
        System.out.println("y()=" + point.y());
        System.out.println("sum=" + point.sum());
        System.out.println("summary=" + point.summary());

        // System.out.println(point.x); // Not accessible:
        // component field x is private.
    }
}
~~~

Run:

~~~bash
javac RecordComponentAccessDemo.java
java RecordComponentAccessDemo
~~~

**Stdout:**

~~~text
Point[x=3, y=4]
x()=3
y()=4
sum=7
summary=x=3,y=4
~~~

Inside the record body, the `sum()` method can read fields `x`/`y` directly because it is in the same class, while callers use `point.x()` or `point.y()`. Java does not generate JavaBeans-style getters `getX()`/`getY()` by default.

**Rule:** a component's name determines both the **private field name** and the **public accessor name**; a component declaration does not allow callers to modify the field with `point.x = 9`.

## 3. Prohibiting Additional Instance Field Declarations in the Record Body

JLS `8.10.2` specifies: **a non-static field declaration in a record body is a compile-time error**.

~~~java
record Point(int x, int y) {
    // private int z;            // Invalid: additional instance field.
    // private final int extra=1; // Still invalid even with final.
    // int cache;                 // Invalid even when package-private.
}
~~~

Why? The record header must be the **complete description of the instance state** that the record exposes as its representation. If mutable or hidden instance fields were allowed outside the header, generated equality, reconstruction, and data transparency would be hard to keep consistent.

### 3.1. Do Not Redeclare Component Fields

~~~java
record Name(String value) {
    // private final String value; // Invalid: the compiler already provides this field.
}
~~~

Do not confuse “a record cannot declare fields” with “a record has no fields”. A record **has private final component fields**; it is you who **cannot** add non-static fields in the body.

### 3.2. Do Not Bypass with an Instance Initializer Block

~~~java
record Counter(int value) {
    // { System.out.println(value); } // Invalid: instance initializer.
}
~~~

A record **does not allow** an instance initializer `{ ... }` in its body. To validate/normalize object state, use a **canonical constructor** (especially the compact form). A static initializer `static { ... }` is a different matter and is allowed.

### 3.3. `transient`/`volatile` Are Also Prohibited for Extra Instance Fields

If you write a declaration `private transient int cache;` or `private volatile long lastUsed;` in the record body, it is still a **non-static field declaration**, so it violates the rule. Adding a modifier does not create an exception.

If you genuinely need per-instance cache/transaction mutable state, consider a **normal class** instead of forcing a record to break the representation model.

## 4. Derived Data: Compute via Methods, Do Not Store Additional Instance Fields

Rectangle example:

~~~java
record Rectangle(int width, int height) {
    long area() {
        return (long) width * height;
    }
}
~~~

`area()` is an **allowed** instance method. It adds no persistent state to the record; the result is computed from the two components.

Do not write:

~~~java
record InvalidRectangle(int width, int height) {
    // private final long area = (long) width * height;
    // Invalid: a record body cannot declare additional non-static fields.
}
~~~

If the computation is very expensive and requires a per-instance cache, a record may not be the right representation. Use a normal immutable class with an explicit cache field, or precompute and place the cached data into a **component** only when it is genuinely part of the representation needed for the public API and equality.

### 4.1. Program Computing Derived Data

Save **`RecordDerivedStateDemo.java`**:

~~~java
public class RecordDerivedStateDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        long area() {
            return (long) width * height;
        }

        long perimeter() {
            return 2L * (width + (long) height);
        }

        boolean isSquare() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(4, 3);
        Rectangle b = new Rectangle(5, 5);

        System.out.println("a area=" + a.area());
        System.out.println("a perimeter=" + a.perimeter());
        System.out.println("a square=" + a.isSquare());
        System.out.println("b area=" + b.area());
        System.out.println("b square=" + b.isSquare());
    }
}
~~~

Run:

~~~bash
javac RecordDerivedStateDemo.java
java RecordDerivedStateDemo
~~~

Output:

~~~text
a area=12
a perimeter=14
a square=false
b area=25
b square=true
~~~

The statements computing `area()` and `perimeter()` execute when you call the methods; there is no third per-object field `area` inside the record. Casting to long helps avoid int arithmetic overflow in common cases; a real domain still needs to account for long limits for extremely large numbers.

## 5. Static Fields of a Record Are **Allowed**

A record body may declare **static fields**; the prohibition applies only to **non-static field declarations outside the header**.

~~~java
record Point(int x, int y) {
    static final String KIND = "point";
    private static int created;
}
~~~

- `KIND` is a static constant for the entire record class.
- `created` is a static mutable field shared across all Point objects.
- Neither of these two static fields is a record component. They do **not** appear in the compiler-generated `toString()` and do not participate in component equality/hashing.
- Mutable static fields can cause data race/lifecycle issues just like in a normal class; a record does **not** automatically make static state thread-safe.

### 5.1. Static Initializers Are Also Valid

~~~java
record Status(int code) {
    private static final java.util.Map<Integer, String> LABELS;

    static {
        LABELS = java.util.Map.of(
                200, "OK",
                404, "Not Found");
    }

    String label() {
        return LABELS.get(code);
    }
}
~~~

This is a static initializer that runs according to class initialization rules, not a block that runs separately for each Status instance. If a block is not needed, you can write `private static final Map<...> LABELS = Map.of(...);`.

**Distinguish clearly:** **instance initializers** are prohibited; **static initializers** are allowed.

## 6. Program: Static Shared State Does Not Change Record Components

Save **`RecordStaticFieldDemo.java`**:

~~~java
public class RecordStaticFieldDemo {
    record Ticket(String code) {
        private static int constructed;

        Ticket {
            constructed++;
        }

        static int constructedCount() {
            return constructed;
        }

        String label() {
            return "Ticket-" + code;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket("A");
        Ticket second = new Ticket("A");

        System.out.println("same values=" + first.equals(second));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("count=" + Ticket.constructedCount());
    }
}
~~~

Run in a new JVM:

~~~bash
javac RecordStaticFieldDemo.java
java RecordStaticFieldDemo
~~~

Output:

~~~text
same values=true
first=Ticket[code=A]
second=Ticket[code=A]
count=2
~~~

`constructed` does not belong to the record components, so two Tickets with `code="A"` are still `equals` true even though the shared counter was incremented. In multithreaded production code, `constructed++` is not atomic; for thread-safe counting, consider `AtomicInteger` or synchronization. Do not put side effects in a constructor just to keep the code short: this example serves to distinguish static vs. instance state.

## 7. Static Fields and Interface Constants Are Not Equivalent to Record Instance Fields

An interface can declare a field:

~~~java
interface Versioned {
    int CURRENT = 1;
}
~~~

That field is **implicitly public static final** on the interface. When a record implements Versioned, it does not receive a **per-record instance field** `CURRENT`. The clearest way to access it is `Versioned.CURRENT`.

Similarly, static fields of a record are shared members of the **record class**, not “cloned” per instance like component fields. The mindset to apply when designing:

- **Instance data**: list in the **record header**.
- **Derived behavior**: write instance methods.
- **Shared metadata/config**: static fields/methods, if they truly belong to the record type.
- **Separate mutable workflow state**: service/entity/normal class; do not cram hidden fields into a record.

## 8. The Constructor Is Where Invariants Are Established for Component Fields

Prohibiting extra instance fields does not prevent a record from validating input or normalizing values.

~~~java
record AccountId(String value) {
    AccountId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value");
        }
        value = value.strip();
    }
}
~~~

This is a **compact canonical constructor**. The parameter `value` is implicit from the record header. When the block completes normally, Java automatically assigns the transformed parameter to the backing component field. You do not declare an additional “normalizedValue” field alongside it.

### 8.1. Normal Canonical Constructor

~~~java
record Pair(int left, int right) {
    Pair(int left, int right) {
        this.left = left;
        this.right = right;
    }
}
~~~

If you write a normal canonical constructor, you must properly initialize each component field according to Java's definite assignment rules. Conversely, a compact constructor **cannot directly assign component fields** in its body by writing `this.left = ...`; instead, mutate/normalize the implicit parameters so that Java assigns them afterward.

### 8.2. Constructor Overloads Other Than the Canonical Constructor

~~~java
record Label(String text, int priority) {
    Label(String text) {
        this(text, 0);
    }
}
~~~

A non-canonical constructor must delegate to another constructor of the same record using `this(...)` according to the rules. It does not grant permission to “have separate state” by assigning a different field.

## 9. Program: Validation, Normalization, and Derived Behavior

Save **`RecordInvariantDemo.java`**:

~~~java
import java.util.Objects;

public class RecordInvariantDemo {
    record User(String name, int age) {
        User {
            Objects.requireNonNull(name, "name");
            name = name.strip();

            if (name.isEmpty()) {
                throw new IllegalArgumentException("name blank");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("age");
            }
        }

        boolean adult() {
            return age >= 18;
        }
    }

    public static void main(String[] args) {
        User lan = new User("  Lan  ", 21);

        System.out.println("value=" + lan);
        System.out.println("adult=" + lan.adult());

        try {
            new User("  ", 30);
        } catch (IllegalArgumentException expected) {
            System.out.println("blank name rejected");
        }

        try {
            new User("Minh", -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid age rejected");
        }
    }
}
~~~

Run:

~~~bash
javac RecordInvariantDemo.java
java RecordInvariantDemo
~~~

Output:

~~~text
value=User[name=Lan, age=21]
adult=true
blank name rejected
invalid age rejected
~~~

A record does not need an instance initializer block to validate. The constructor guarantees that immediately after construction, the object satisfies the invariant. If validation fails, construction does not return a valid value.

## 10. Records Are Implicitly `final`: No Subclasses

Java 17 specifies that a record class is **implicitly final** (JLS `8.10`). For example:

~~~java
record Point(int x, int y) {
}
~~~

A record already disallows subclassing even if you do not write the `final` keyword:

~~~java
// class ColoredPoint extends Point { } // Compile-time error.
// Point cannot be extended because a record is final.
~~~

You can write `final record Point(...)` as a valid redundant modifier in certain appropriate scopes, but normally there is no need to do so: a record is already final by default.

### 10.1. Do Not Declare an `abstract`, `sealed`, or `non-sealed` Record

~~~java
// abstract record Shape(int size) { } // Invalid.
// sealed record Shape(int size) { }   // Invalid.
// non-sealed record Shape(int size) {} // Invalid.
~~~

An abstract record would require the ability to have subclasses to complete abstract members, whereas a record is final. Furthermore, the JLS directly prohibits the `abstract`, `sealed`, and `non-sealed` modifiers on record declarations.

A common point of confusion: **a record cannot be a sealed class**, but **a record can implement a sealed interface** if permitted. The two rules do not contradict each other: `sealed` on an interface controls its implementors, while the record implementing it is a concrete final type.

## 11. A Record Directly Extends `java.lang.Record`

Every record class has `java.lang.Record` as its **direct superclass** according to the specification. Because a record declaration does not have an `extends` clause, you cannot write:

~~~java
// record Data(int x) extends Object { } // Syntax error.
// record Data(int x) extends Record { } // Also invalid.
~~~

With a normal class, you can write `class Child extends Parent`. With a record, the superclass is preselected by the language: `Record`. Of course, the class `java.lang.Record` ultimately sits within the object hierarchy, meaning a record object is still an `Object`.

### 11.1. Which Methods Relate to `Record` and `Object`?

- `equals(Object)`, `hashCode()`, and `toString()` are provided with implementations by the record class matching the record components (implicitly or declared by you).
- Methods from `Object` such as `getClass()` are still usable; calling `record.getClass()` returns the runtime class.
- `Record` is a specialized abstract superclass, not a place where you declare per-instance fields.
- The constructor of Record is not an API you call directly from a record canonical constructor.
- You cannot add `extends Parent` to inherit fields/methods from Parent.
- **Interfaces are the appropriate polymorphism mechanism** when multiple record types need to share a contract.

### 11.2. Cannot Extend Another Record

~~~java
record Coordinate(int x, int y) {
}

// record Colored(int x, int y, String color)
//         extends Coordinate { } // Invalid.
~~~

To compose values, declare:

~~~java
record Colored(Coordinate point, String color) {
}
~~~

This is **composition**, not inheritance. The `point` component is a Coordinate value; `Colored` does not become a subtype of Coordinate. If you want polymorphism, both can implement a common appropriate interface.

## 12. Program: Verifying the Runtime Class and Superclass

Save **`RecordSuperclassDemo.java`**:

~~~java
public class RecordSuperclassDemo {
    record Point(int x, int y) {
    }

    public static void main(String[] args) {
        Point point = new Point(2, 5);

        System.out.println("record=" + point);
        System.out.println("is Object=" + (point instanceof Object));
        System.out.println("is Record=" + (point instanceof Record));
        System.out.println("superclass=" +
                point.getClass().getSuperclass().getName());
    }
}
~~~

Run:

~~~bash
javac RecordSuperclassDemo.java
java RecordSuperclassDemo
~~~

Output:

~~~text
record=Point[x=2, y=5]
is Object=true
is Record=true
superclass=java.lang.Record
~~~

Reflection here only checks the **superclass type** using the JDK API, without assuming compiler synthetic field/constructor names. `Record` in `instanceof Record` is `java.lang.Record`, built into Java 17.

## 13. A Record Can Implement Interfaces

A record can declare one or more superinterfaces right after the record header:

~~~java
interface Named {
    String name();
}

record Person(String name, int age) implements Named {
}
~~~

`Person` does not extend a user superclass; it **implements Named**. When the interface requires the method `String name()`, the **generated record accessor `name()`** has the same signature and public accessibility, so it automatically satisfies the contract. You are not required to rewrite the accessor if the generated one is sufficient.

This is an advantage: record components both serve as the data representation and can participate in an interface API **when the name/type/parameters of the corresponding methods match**.

### 13.1. The Method Contract Determines Automatic Implementation

If the interface requires:

~~~java
interface JavaBeanNamed {
    String getName();
}
~~~

Then `record Person(String name) implements JavaBeanNamed {}` **does not automatically satisfy the contract** via the generated accessor `name()`, because `getName()` has a different name and signature. You need to write it yourself:

~~~java
record Person(String name) implements JavaBeanNamed {
    @Override
    public String getName() {
        return name;
    }
}
~~~

Do not assume “if an interface has a method with a semantically similar name, Java automatically matches the fields”. Java matches by **method signatures**, not by inferring business meaning from names.

## 14. Program: Generated Accessor Automatically Implements an Interface

Save **`RecordAccessorInterfaceDemo.java`**:

~~~java
public class RecordAccessorInterfaceDemo {
    interface Named {
        String name();
    }

    record Employee(String name, int salary)
            implements Named {
    }

    static void printName(Named value) {
        System.out.println("name=" + value.name());
    }

    public static void main(String[] args) {
        Employee employee = new Employee("Lan", 100);

        printName(employee);
        System.out.println("salary=" + employee.salary());
        System.out.println("implements Named=" +
                (employee instanceof Named));
    }
}
~~~

Run:

~~~bash
javac RecordAccessorInterfaceDemo.java
java RecordAccessorInterfaceDemo
~~~

Output:

~~~text
name=Lan
salary=100
implements Named=true
~~~

The Employee accessor `name()` is generated by the compiler and has `public` visibility, so it directly implements the `name()` method of Named. The interface reference `Named value` exposes only `name()`, because `salary()` does not belong to the interface contract.

## 15. If an Interface Requires a Method Whose Name Differs from the Accessor, You Must Write It Yourself

A record can keep a component and provide an adapter method:

~~~java
interface HasId {
    String getId();
}

record Account(String id) implements HasId {
    @Override
    public String getId() {
        return id;
    }
}
~~~

`getId()` here is a **custom method**. The record still has the generated `id()`. Both methods return the component value, while callers using each API call the corresponding method.

### 15.1. Runnable Program

Save **`RecordExplicitInterfaceDemo.java`**:

~~~java
public class RecordExplicitInterfaceDemo {
    interface HasId {
        String getId();
    }

    record Account(String id, boolean active)
            implements HasId {
        @Override
        public String getId() {
            return id;
        }

        String label() {
            return id + (active ? ":active" : ":inactive");
        }
    }

    static void show(HasId item) {
        System.out.println("interface id=" + item.getId());
    }

    public static void main(String[] args) {
        Account account = new Account("A-1", true);

        show(account);
        System.out.println("component id=" + account.id());
        System.out.println("label=" + account.label());
    }
}
~~~

Run:

~~~bash
javac RecordExplicitInterfaceDemo.java
java RecordExplicitInterfaceDemo
~~~

Output:

~~~text
interface id=A-1
component id=A-1
label=A-1:active
~~~

**Takeaway:** records support interfaces just like normal classes, but they do not automatically turn all component getters into methods with arbitrary names. You must write the method if the signature does not match.

## 16. Interface Default Methods: Records Can Inherit Behavior

Interfaces in Java can declare a **default method**. A record implementing that interface can use the default method without duplicating the implementation if the method does not conflict.

~~~java
interface Named {
    String name();

    default String label() {
        return "Hello " + name();
    }
}

record User(String name) implements Named {
}
~~~

The record `User` provides `name()` via its generated accessor; the default `label()` calls that method through the interface contract.

### 16.1. Runnable Program

Save **`RecordDefaultInterfaceDemo.java`**:

~~~java
public class RecordDefaultInterfaceDemo {
    interface Named {
        String name();

        default String greeting() {
            return "Hello " + name();
        }
    }

    record User(String name) implements Named {
    }

    public static void main(String[] args) {
        Named person = new User("Lan");

        System.out.println("name=" + person.name());
        System.out.println("greeting=" + person.greeting());
    }
}
~~~

Run:

~~~bash
javac RecordDefaultInterfaceDemo.java
java RecordDefaultInterfaceDemo
~~~

Output:

~~~text
name=Lan
greeting=Hello Lan
~~~

This is **inheriting behavior from an interface**, not inheriting instance fields from a user superclass. The generated accessor in User supplies data to the default method.

### 16.2. Default Methods Can Be Overridden

If the record wants a different rule, declare:

~~~java
record User(String name) implements Named {
    @Override
    public String greeting() {
        return "Xin chao " + name;
    }
}
~~~

You must preserve the exact method signature/visibility. An interface default method does not force every implementor to use the same implementation.

## 17. Default Method Conflicts from Multiple Interfaces

A record is allowed to implement multiple interfaces:

~~~java
record Point(int x, int y)
        implements java.io.Serializable, Comparable<Point> {
    @Override
    public int compareTo(Point other) {
        int byX = Integer.compare(x, other.x());
        return byX != 0 ? byX : Integer.compare(y, other.y());
    }
}
~~~

However, if two interfaces provide **the same default method signature** without a clear precedence, the record generally must override it to resolve the conflict. This principle is the same as for normal classes.

### 17.1. Program Reconciling Default Methods

Save **`RecordDefaultConflictDemo.java`**:

~~~java
public class RecordDefaultConflictDemo {
    interface A {
        default String label() {
            return "A";
        }
    }

    interface B {
        default String label() {
            return "B";
        }
    }

    record Item(int id) implements A, B {
        @Override
        public String label() {
            return A.super.label() + "+" + B.super.label() +
                    ":" + id;
        }
    }

    public static void main(String[] args) {
        Item item = new Item(7);

        System.out.println(item.label());
        System.out.println("A=" + ((A) item).label());
        System.out.println("B=" + ((B) item).label());
    }
}
~~~

Run:

~~~bash
javac RecordDefaultConflictDemo.java
java RecordDefaultConflictDemo
~~~

Output:

~~~text
A+B:7
A=A+B:7
B=A+B:7
~~~

Even if the receiver is cast to A or B, virtual dispatch still selects Item's override. The syntax `A.super.label()`/`B.super.label()` **can only be used inside Item's override** to invoke each default implementation individually.

If the override is omitted, the compiler rejects it due to a default method conflict. Records have no special exception for this conflict.

## 18. Interface Static Fields Are Shared Constants, Not Instance State

An interface:

~~~java
interface Measurement {
    String UNIT = "cm";

    int magnitude();
}
~~~

`UNIT` is `public static final`. A record can implement it:

~~~java
record Length(int magnitude) implements Measurement {
}
~~~

The generated `magnitude()` satisfies the interface method. To use the static constant, write `Measurement.UNIT` so the meaning is clear.

This does not generate an extra `UNIT` component field on each Length object and does not participate in generated equality. An interface does not contain mutable instance fields for a record to “inherit”.

## 19. Program: Generic Interface with a Generic Record

Save **`RecordGenericInterfaceDemo.java`**:

~~~java
public class RecordGenericInterfaceDemo {
    interface ValueSource<T> {
        T value();

        default String describe() {
            return "value=" + value();
        }
    }

    record Box<T>(T value) implements ValueSource<T> {
    }

    public static void main(String[] args) {
        ValueSource<String> first = new Box<>("Java");
        ValueSource<Integer> second = new Box<>(17);

        System.out.println(first.describe());
        System.out.println(second.describe());
        System.out.println("string=" + first.value());
        System.out.println("integer=" + second.value());
    }
}
~~~

Run:

~~~bash
javac RecordGenericInterfaceDemo.java
java RecordGenericInterfaceDemo
~~~

Output:

~~~text
value=Java
value=17
string=Java
integer=17
~~~

The record `Box<T>` declares the type variable T itself. The generated accessor `T value()` satisfies the generic method `ValueSource<T>.value()` after type substitution/erasure according to Java generic rules. Callers preserve safer compile-time typing compared to Object[].

**Caution:** `Box<List<String>>` still holds a List reference; a generic type parameter does not make the nested list immutable.

## 20. Implementing `Comparable` to Define Ordering

Generated record `equals`/`hashCode` **do not automatically make a record implement Comparable**. If an application needs to sort by natural order, a record can implement `Comparable<RecordType>` and write `compareTo` itself.

~~~java
record Version(int major, int minor)
        implements Comparable<Version> {
    @Override
    public int compareTo(Version other) {
        int first = Integer.compare(major, other.major);
        return first != 0 ? first
                : Integer.compare(minor, other.minor);
    }
}
~~~

Use `Integer.compare` instead of `major - other.major` to avoid integer overflow. For records used in sorted collections, design `compareTo` to be consistent with `equals` if the collection/domain contract requires it. If compareTo returns 0 for two records that are not equals, `TreeSet` may treat them as occupying the same sort position even though `HashSet` treats them as distinct.

### 20.1. Sorting Program

Save **`RecordComparableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordComparableDemo {
    record Version(int major, int minor)
            implements Comparable<Version> {
        @Override
        public int compareTo(Version other) {
            int first = Integer.compare(major, other.major);
            return first != 0 ? first
                    : Integer.compare(minor, other.minor);
        }
    }

    public static void main(String[] args) {
        List<Version> versions = new ArrayList<>(
                List.of(new Version(2, 0),
                        new Version(1, 9),
                        new Version(1, 2)));

        versions.sort(null);
        for (Version version : versions) {
            System.out.println(version);
        }
    }
}
~~~

Run:

~~~bash
javac RecordComparableDemo.java
java RecordComparableDemo
~~~

Output:

~~~text
Version[major=1, minor=2]
Version[major=1, minor=9]
Version[major=2, minor=0]
~~~

Each Version object remains final in its component fields. Sorting the List changes **the order of references in the collection**, without mutating the record instances.

## 21. Records Can Implement a Sealed Interface (Java 17)

A sealed interface restricts **the list of direct implementing types**. Because a record is implicitly final, it is well suited as a permitted concrete implementation.

~~~java
sealed interface Shape permits Circle, Rectangle {
    long area();
}

record Circle(int radius) implements Shape {
    @Override
    public long area() {
        return 3L * radius * radius; // Simulated formula with coefficient 3.
    }
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public long area() {
        return (long) width * height;
    }
}
~~~

These are **illustrative declarations**, with no main. Real geometry requires an appropriate π formula/precision. A sealed interface is useful when the set of variants is known in advance, and each record represents immutable data for each variant.

### 21.1. Two Non-Conflicting Restrictions

- A record **cannot** be declared `sealed record`.
- A record **can implement a `sealed interface`** if permitted according to Java rules.
- A record remains **final** and cannot be further subclassed.
- A sealed interface does not automatically let a record inherit instance fields of another type.

## 22. Complete Program: Sealed Interface with Record Implementations

Save **`RecordSealedInterfaceDemo.java`**:

~~~java
public class RecordSealedInterfaceDemo {
    sealed interface Figure permits Square, Rectangle {
        long area();
    }

    record Square(int side) implements Figure {
        @Override
        public long area() {
            return (long) side * side;
        }
    }

    record Rectangle(int width, int height)
            implements Figure {
        @Override
        public long area() {
            return (long) width * height;
        }
    }

    static void show(Figure value) {
        System.out.println(value.getClass().getSimpleName() +
                "=" + value.area());
    }

    public static void main(String[] args) {
        show(new Square(3));
        show(new Rectangle(2, 5));
    }
}
~~~

Run:

~~~bash
javac RecordSealedInterfaceDemo.java
java RecordSealedInterfaceDemo
~~~

Output:

~~~text
Square=9
Rectangle=10
~~~

Although the nested record classes are inside a top-level demo, the simple class names `Square`/`Rectangle` are stably determined by `getSimpleName()` for these named member record declarations. The sealed interface controls the direct implementations `Square`/`Rectangle`, without changing the semantics of the record component fields.

## 23. Composition Instead of Inheritance for Record Classes

When you want a type that adds data based on another record, use **composition**:

~~~java
record Point(int x, int y) {
}

record ColoredPoint(Point point, String color) {
}
~~~

You cannot do:

~~~java
// record ColoredPoint(int x, int y, String color)
//         extends Point { } // Invalid.
~~~

If the domain needs shared polymorphism, design an interface:

~~~java
interface HasPoint {
    Point point();
}

record Marker(Point point) implements HasPoint {
}

record ColoredPoint(Point point, String color)
        implements HasPoint {
}
~~~

Both record types implement the same interface, but do not inherit fields from each other. This is Java **composition + interface polymorphism**, which is usually clearer than forcing record inheritance.

### 23.1. Composition Program

Save **`RecordCompositionDemo.java`**:

~~~java
public class RecordCompositionDemo {
    record Point(int x, int y) {
    }

    interface Located {
        Point point();
    }

    record Labelled(Point point, String label)
            implements Located {
    }

    record Colored(Point point, String color)
            implements Located {
    }

    static String coordinates(Located value) {
        return value.point().x() + "," +
                value.point().y();
    }

    public static void main(String[] args) {
        Point origin = new Point(1, 2);
        Located a = new Labelled(origin, "A");
        Located b = new Colored(origin, "red");

        System.out.println("a=" + coordinates(a));
        System.out.println("b=" + coordinates(b));
        System.out.println("shared point=" +
                (a.point() == b.point()));
    }
}
~~~

Run:

~~~bash
javac RecordCompositionDemo.java
java RecordCompositionDemo
~~~

Output:

~~~text
a=1,2
b=1,2
shared point=true
~~~

The two records share an immutable Point value object safely with respect to mutation because Point only has int components. If a component is a mutable object, sharing the reference requires a clear ownership contract.

## 24. Interfaces Do Not Turn a Record into a Mutable Bean

An interface can require a setter-like method:

~~~java
interface Renameable {
    void rename(String name);
}
~~~

Syntactically, a record can implement a `void rename(String)` method that performs side effects with an external service, but it **cannot reassign a record component field**:

~~~java
record User(String name) implements Renameable {
    @Override
    public void rename(String newName) {
        // this.name = newName; // Compile-time error: final field.
        throw new UnsupportedOperationException("immutable value");
    }
}
~~~

This is an **illustrative snippet**, not a recommendation to implement Renameable just to throw an exception. A better design is **not** to force a record into an interface that demands mutable object identity/state. Use an appropriate immutable-value interface or return a new record.

### 24.1. Return-New-Instance Design

~~~java
interface WithName<T> {
    T withName(String name);
}

record User(String name) implements WithName<User> {
    @Override
    public User withName(String next) {
        return new User(next);
    }
}
~~~

This is an immutable evolution API with more appropriate behavior. The interface contract expresses an operation that produces a new value rather than mutating the current object.

## 25. Program: Interface Returning a New Record Value

Save **`RecordWithInterfaceDemo.java`**:

~~~java
public class RecordWithInterfaceDemo {
    interface WithTitle<T> {
        T withTitle(String title);
    }

    record Document(String title, int pages)
            implements WithTitle<Document> {
        @Override
        public Document withTitle(String next) {
            return new Document(next, pages);
        }
    }

    public static void main(String[] args) {
        Document before = new Document("Draft", 2);
        Document after = before.withTitle("Final");

        System.out.println("before=" + before);
        System.out.println("after=" + after);
        System.out.println("same object=" + (before == after));
        System.out.println("same pages=" +
                (before.pages() == after.pages()));
    }
}
~~~

Run:

~~~bash
javac RecordWithInterfaceDemo.java
java RecordWithInterfaceDemo
~~~

Output:

~~~text
before=Document[title=Draft, pages=2]
after=Document[title=Final, pages=2]
same object=false
same pages=true
~~~

Record fields are not modified after construction. The `WithTitle<Document>` interface clearly describes the operation of returning a new Document value.

## 26. Final Component Fields Do Not Guarantee Deep Immutability of Nested Objects

The `private final` property of a component field only fixes the **field reference/value**. If a record component is a mutable container:

~~~java
record Basket(java.util.List<String> items) {
}
~~~

A caller can retain the same mutable List object and mutate it, because the generated accessor `items()` returns the reference. The record still declares no additional instance fields, yet the **component itself** can point to mutable state.

A record whose components are value-stable types such as primitives, String, LocalDate, or immutable value records makes it easier to guarantee invariants.

### 26.1. Program: A Mutable List Can Still Be Modified

Save **`RecordShallowFieldDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordShallowFieldDemo {
    record Basket(List<String> items) {
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);

        source.add("B");
        basket.items().add("C");

        System.out.println("source=" + source);
        System.out.println("record items=" + basket.items());
        System.out.println("same list=" +
                (source == basket.items()));
    }
}
~~~

Run:

~~~bash
javac RecordShallowFieldDemo.java
java RecordShallowFieldDemo
~~~

Output:

~~~text
source=[A, B, C]
record items=[A, B, C]
same list=true
~~~

The finality of a component field does not mean `List.add` is prohibited. When using a record to represent an immutable value, **component type selection** and a defensive-copy contract are still necessary.

## 27. Defensive Copying in the Constructor When a Snapshot Is Needed

Use a compact constructor to normalize a mutable List into an unmodifiable snapshot:

~~~java
record Basket(java.util.List<String> items) {
    Basket {
        items = java.util.List.copyOf(items);
    }
}
~~~

`List.copyOf` preserves an immutable structure (disallowing add/remove) while also rejecting null elements. With immutable String elements, this is usually a sufficiently safe snapshot. However, if the component is `List<MutableItem>`, values can still change through aliases to each MutableItem.

### 27.1. Snapshot Program

Save **`RecordDefensiveListDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordDefensiveListDemo {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket snapshot = new Basket(source);
        source.add("B");

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot.items());
        System.out.println("count=" + snapshot.count());

        try {
            snapshot.items().add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot immutable structure");
        }
    }
}
~~~

Run:

~~~bash
javac RecordDefensiveListDemo.java
java RecordDefensiveListDemo
~~~

Output:

~~~text
source=[A, B]
snapshot=[A]
count=1
snapshot immutable structure
~~~

No hidden instance field is added: the record `Basket` still contains only a single component `items`. Constructor normalization makes the component reference point to an unmodifiable list representation.

## 28. Array Components and Equality: An Important Note

Given:

~~~java
record Bytes(byte[] data) {
}
~~~

`Bytes` has a private final array reference, but the array has mutable elements. Generated `equals`/`hashCode` **do not** use `Arrays.equals`/`Arrays.hashCode` to compare array contents; arrays use reference equality semantics in component comparison.

If content-based value semantics are needed, consider a different representation (an immutable List of Byte or a domain type) or custom `equals`/`hashCode` with defensive copies and proper technique.

Do not override `equals` while forgetting a compatible `hashCode`. Do not use a record with a mutable component as a HashMap key unless the equality/hash-relevant state is protected/stable.

### 28.1. Program Distinguishing Reference and Content

Save **`RecordArrayEqualityDemo.java`**:

~~~java
import java.util.Arrays;

public class RecordArrayEqualityDemo {
    record Bytes(byte[] data) {
    }

    public static void main(String[] args) {
        byte[] left = {1, 2};
        byte[] right = {1, 2};

        Bytes a = new Bytes(left);
        Bytes b = new Bytes(right);
        Bytes c = new Bytes(left);

        System.out.println("arrays content=" +
                Arrays.equals(left, right));
        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("same raw ref=" +
                (a.data() == c.data()));
    }
}
~~~

Run:

~~~bash
javac RecordArrayEqualityDemo.java
java RecordArrayEqualityDemo
~~~

Output:

~~~text
arrays content=true
a equals b=false
a equals c=true
same raw ref=true
~~~

This example illustrates **generated array-component equality**; it does not prove that an array is immutable. `a.data()`/`c.data()` return the same raw array reference when the accessor is not overridden.

## 29. A Custom Record Accessor Is Still a Method of the Record Class

You can explicitly declare an accessor when a defensive copy is needed:

~~~java
record Packet(byte[] bytes) {
    Packet {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Here, the `bytes()` accessor has the exact return type of the component, is public, has no parameters, and has no `throws` clause. The body returns a cloned array so as not to expose the internal array. It does not create a new instance field.

**However:** generated equality still compares array component references and does not automatically switch to content equality. Two Packet instances with the same bytes contents whose constructor clones separate arrays can evaluate `equals` as false without custom methods. Check the entire contract: immutable snapshot, getters, equality, hashing, and serialization.

## 30. Static Nested Member Records and Local Records Are Both Implicitly Static

A **member record** inside a class is implicitly static:

~~~java
class Outer {
    private final String id;

    record Item(String code) {
    }
}
~~~

It is instantiated with `new Outer.Item("A")` if accessible, without needing `outer.new Item(...)`. The `Item` record does not automatically have an enclosing Outer instance, so it cannot access `Outer.this.id`.

A **local record** inside a method is also implicitly static:

~~~java
void process(int amount) {
    record Result(int value) {
    }

    Result result = new Result(amount);
}
~~~

A local record does not capture the method variable `amount` in its body: the caller passes `amount` explicitly via the canonical constructor.

**Key takeaway of this topic:** implicit-static nesting is about **not holding an outer instance**, whereas not being allowed to declare additional instance fields is a **separate rule of record representation**. The two restrictions have different reasons, yet both help make a record a transparent value carrier.

## 31. Program: A Member Record Does Not Inherit Outer Instance Fields

Save **`RecordNestedStaticDemo.java`**:

~~~java
public class RecordNestedStaticDemo {
    static class Outer {
        private final String label;

        Outer(String label) {
            this.label = label;
        }

        record Item(String name) {
            String describe() {
                return name;
            }
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("Owner");
        Outer.Item item = new Outer.Item("Book");

        System.out.println("outer=" + outer.label());
        System.out.println("item=" + item.describe());
        System.out.println("value=" + item);
    }
}
~~~

Run:

~~~bash
javac RecordNestedStaticDemo.java
java RecordNestedStaticDemo
~~~

Output:

~~~text
outer=Owner
item=Book
value=Item[name=Book]
~~~

`Item` does not implicitly hold an Outer, so there is no `Outer.this.label` inside Item. If Item needs owner data, pass `label` or an Outer reference explicitly into a record component/method; that in turn creates an **explicit reference path** with lifetime implications.

## 32. `Serializable` Is an Interface, Not a Default for Every Record

A record can declare `implements java.io.Serializable`:

~~~java
record Event(String type, long time)
        implements java.io.Serializable {
}
~~~

Not every record automatically implements Serializable simply because records have generated accessors/constructors. If a domain needs Java Object Serialization, that is a separate **interface/format policy**, and record deserialization has special semantics: the canonical constructor is used.

In modern applications, JSON/protobuf/etc., depending on the ecosystem, require library/tooling support for records and schema migrations. Do not use the generated `toString()` as a stable wire format.

### 32.1. Avoid Confusing Serialization with Instance Field Rules

`Serializable` is a marker interface that does not require a record to have an additional mutable instance field. A record still only has component fields. If a record contains a non-serializable component, it must be handled according to the corresponding serialization contract; do not assume every graph serializes successfully on its own.

## 33. Generic Records and Interface Variance

A generic record can implement a generic interface:

~~~java
interface Holder<T> {
    T get();
}

record Box<T>(T value) implements Holder<T> {
    @Override
    public T get() {
        return value;
    }
}
~~~

Because `Holder<T>` requires `get()`, the generated accessor `value()` does not satisfy it, so a custom method `get()` is needed. If the interface required `T value()`, the generated accessor would be sufficient.

### 33.1. Generic Program with an Adapter Method

Save **`RecordGenericAdapterDemo.java`**:

~~~java
public class RecordGenericAdapterDemo {
    interface Holder<T> {
        T get();
    }

    record Box<T>(T value) implements Holder<T> {
        @Override
        public T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Holder<String> text = new Box<>("hello");
        Holder<Integer> number = new Box<>(42);

        System.out.println("text=" + text.get());
        System.out.println("number=" + number.get());
        System.out.println("box accessor=" +
                new Box<>("raw").value());
    }
}
~~~

Run:

~~~bash
javac RecordGenericAdapterDemo.java
java RecordGenericAdapterDemo
~~~

Output:

~~~text
text=hello
number=42
box accessor=raw
~~~

No anonymous adapter object is stored in the record; the `get()` method simply delegates to the component field. The type parameter T belongs to Box itself, which is valid under Java generics.

## 34. Interface Contracts Do Not Define Component Equality

Example of two record types:

~~~java
interface Identified {
    String id();
}

record Person(String id, String name)
        implements Identified {
}

record Product(String id, String description)
        implements Identified {
}
~~~

Both implement `Identified`, yet the record's generated equality **does not** conclude that Person("A",...) equals Product("A",...) merely because they have the same id. They are **different record classes**, with component-based equality for the same record type.

An interface acts as a contract for **behavior/accessors**; it does not turn multiple classes into the same value type.

### 34.1. Program: Polymorphism Does Not Mean Cross-Type Equality

Save **`RecordInterfaceEqualityDemo.java`**:

~~~java
public class RecordInterfaceEqualityDemo {
    interface Identified {
        String id();
    }

    record Person(String id, String name)
            implements Identified {
    }

    record Product(String id, String description)
            implements Identified {
    }

    public static void main(String[] args) {
        Identified person = new Person("X", "Lan");
        Identified product = new Product("X", "Book");

        System.out.println("same ids=" +
                person.id().equals(product.id()));
        System.out.println("record equals=" +
                person.equals(product));
        System.out.println("types=" +
                person.getClass().getSimpleName() + "/" +
                product.getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac RecordInterfaceEqualityDemo.java
java RecordInterfaceEqualityDemo
~~~

Output:

~~~text
same ids=true
record equals=false
types=Person/Product
~~~

The `Identified` interface does not automatically alter the generated `equals`/`hashCode`. If the domain wants entity identity based on id across types, a mutable identity entity/reference model may be more suitable than record generated value semantics.

## 35. Interface Methods Can Conflict with Component Accessors

Suppose:

~~~java
interface HasNumber {
    int value();
}
~~~

`record Count(int value) implements HasNumber {}` satisfies this automatically. However, if the interface requires `String value()` while the record component has type `int value`, the generated accessor `int value()` **does not** have a compatible return type to implement the method, so the record declaration fails to compile.

The compiler does not convert int→String based on matching names. Choose a record component type matching the interface contract or design an adapter method with a **different name**. You also cannot write two methods with the same parameter signature that differ only by return type in the same record body to “satisfy both”.

Similarly, a component name must not conflict with the no-arg Object method names prohibited by the JLS for record components (for example, `toString`, `hashCode`, `getClass`). These are name/signature restrictions serving valid record accessors.

## 36. Interfaces Can Contain Static Methods: Records Do Not Inherit Them as Instance Methods

Interface:

~~~java
interface Identified {
    String id();

    static String normalize(String raw) {
        return raw.strip();
    }
}
~~~

The method `Identified.normalize(...)` is a **static interface method**. When a record implements Identified, you cannot simply call `myRecord.normalize(...)` as if it were an inherited instance method.

A record can use the static method via the **interface type name** in a compact constructor:

~~~java
record Id(String id) implements Identified {
    Id {
        id = Identified.normalize(id);
    }
}
~~~

A static method belongs to the interface, creates no per-record-instance state, and does not become a component. Distinguish instance/default interface behavior from static interface utilities.

## 37. What Are the Limitations on Method Overriding in a Record?

A record is **final**, so subclasses of a record cannot override methods. However, **the record itself** can still:

- Override the `Object/Record` methods `equals`, `hashCode`, and `toString` in accordance with the rules.
- Override concrete interface default methods.
- Implement abstract interface methods.
- Explicitly declare a component accessor method with a valid signature/visibility.
- Overload instance/static methods like a normal class, except for record-specific restrictions.

A record **cannot declare an abstract/native method** in its record body (JLS `8.10.2`), because a record is a complete final concrete value class. If an interface requires an abstract method, the record must provide an implementation (directly or via an appropriate generated/inherited concrete method).

### 37.1. Overriding `toString()` Can Change the Presentation

~~~java
record Coordinate(int x, int y) {
    @Override
    public String toString() {
        return "(" + x + "," + y + ")";
    }
}
~~~

Generated equality/hashCode still rely on components if you do not override them. However, `toString()` now returns a representation different from the default record syntax. Do not use `toString` as a JSON/persistent wire schema.

## 38. When Are Interfaces/Default Methods No Longer Suitable?

If you want to reuse substantial mutable implementation state across multiple classes, an interface only has default methods/static constants and does not provide per-object instance fields. A record, in turn, cannot inherit a base class containing state or declare additional fields.

Reasonable design approaches:

1. **Interface + component data**: when behavior can be computed from record components.
2. **Interface + helper service**: when behavior needs long-lived services, resource ownership, or external dependencies.
3. **Composition**: a record contains other immutable value components.
4. **Normal class**: when mutable identity/state, inheritance of implementation, caches, locks, or resources are needed.
5. **Sealed interface + record variants**: when the domain is a finite sum of immutable case variants.
6. **Factory/validation layer**: when construction requires complex logic, while the record representation remains simple.

It is not that “a record is always better than a class”; it is the right choice if **component-based transparent value semantics** genuinely describe the object.

## 39. Summary Rules Table

| Topic | Java 17 Record | Notes |
| --- | --- | --- |
| Component field | Yes, implicitly declared `private final` | One field per header component |
| Declaring additional instance fields | **No** | All non-static field declarations in the body are prohibited |
| Declaring instance initializer blocks | **No** | Use a constructor |
| Static field | Yes | Shared by the record class, not a component |
| Static initializer | Yes | Runs during class initialization, not per instance |
| Instance method | Yes | Derived behavior from components |
| Static method | Yes | Class-level helper/factory |
| Canonical constructor | Yes | Generated, normal, or compact |
| Non-canonical constructor | Yes | Delegates via `this(...)` |
| Extends user class | **No** | Direct superclass is java.lang.Record |
| Record extends record | **No** | Records are final |
| Abstract/sealed/non-sealed record | **No** | Prohibited |
| Implicit final | Yes | Disallows subclassing |
| Explicit redundant final | Allowed | Usually unnecessary |
| Implements interface | Yes | One or more, according to Java rules |
| Implements generic interface | Yes | Match type parameters/signatures |
| Generated accessor implements interface method | Possible | When return type/signature are compatible |
| Interface default method | Can be inherited | Can be overridden; resolve conflicts |
| Implements sealed interface | Yes if permitted | Final record is a permitted implementation |
| Custom equals/hashCode/toString | Yes | Follow Object/record contract |
| Deeply immutable component references | **Not guaranteed** | Mutable nested graphs require ownership/copying |
| Member/local record implicitly static | Yes | No implicit enclosing instance |
| `implements Serializable` | Allowed | Does not apply automatically to every record |

## 40. Common Compilation Errors and How to Fix Them

### 40.1. Additional Instance Field

~~~java
record R(int x) {
    // private int cache; // Compile-time error.
}
~~~

**Fix:** compute the cache from the component using a method, use an external service/cache, or use a normal class if per-instance caching is essential.

### 40.2. Instance Initializer Block

~~~java
record R(int x) {
    // { System.out.println(x); } // Compile-time error.
}
~~~

**Fix:** compact constructor `R { ... }` if validation/normalization is needed.

### 40.3. Attempting to Extend a Normal Superclass

~~~java
class Base {
}

// record R(int x) extends Base {} // Compile-time error.
~~~

**Fix:** records do not have extends; use composition or an interface.

### 40.4. Attempting to Subclass a Record

~~~java
record BaseRecord(int x) {
}

// class Child extends BaseRecord {} // Compile-time error.
~~~

**Fix:** you cannot extend a final record; create a record containing a BaseRecord component or a shared interface.

### 40.5. Not Implementing an Interface with the Exact Signature

~~~java
interface Named {
    String getName();
}

// record Person(String name) implements Named { } // Error.
~~~

**Fix:** write a public `getName()` delegating to `name()`, or change the interface contract to `name()` if the API permits.

### 40.6. Interface Return Type Conflicts with Accessor

~~~java
interface HasValue {
    String value();
}

// record R(int value) implements HasValue { } // Error.
~~~

**Fix:** choose a compatible component type/contract or design a conversion method with a different name. Do not overload solely by return type.

### 40.7. Abstract Method in the Record Body

~~~java
record R(int x) {
    // abstract int compute(); // Error.
}
~~~

**Fix:** write a concrete method; or use a sealed interface with multiple implementing records if abstract behavior across variants is needed.

### 40.8. Mutating a Final Component Field

~~~java
record R(int x) {
    // void change(int n) { this.x = n; } // Error.
}
~~~

**Fix:** create a new record `new R(n)`; or use a mutable normal class if the contract requires in-place updates.

### 40.9. Treating a Static Field as a Component

~~~java
record R(int x) {
    static int total;
}
~~~

`total` is a static class field; the generated equals, hashCode, and toString consider only `x`. If you want each instance to store total, add `total` to the header if that matches the intended representation.

### 40.10. Misunderstanding Shallow Immutability

~~~java
record R(java.util.List<String> items) {
}
~~~

If a mutable list is passed, `items()` can allow mutating the list. **Fix** this with an immutable list snapshot when the contract requires it; there is no need to add an instance field.

## 41. Integrated Program: Interface + Record Components + Static Catalog

Save **`RecordInterfaceIntegrationDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;

public class RecordInterfaceIntegrationDemo {
    interface ProductView {
        String sku();
        long total();

        default String summary() {
            return sku() + ":" + total();
        }
    }

    record Product(String sku, long unitPrice, int quantity)
            implements ProductView {
        static final Map<String, String> LABELS =
                Map.of("PEN", "Pen", "BOOK", "Book");

        Product {
            Objects.requireNonNull(sku, "sku");
            if (unitPrice < 0 || quantity < 0) {
                throw new IllegalArgumentException("numbers");
            }
        }

        @Override
        public long total() {
            return Math.multiplyExact(unitPrice, quantity);
        }

        String displayName() {
            return LABELS.getOrDefault(sku, sku);
        }
    }

    static void report(ProductView value) {
        System.out.println(value.summary());
    }

    public static void main(String[] args) {
        Product first = new Product("PEN", 10, 2);
        Product second = new Product("BOOK", 50, 1);

        report(first);
        report(second);

        System.out.println("first name=" + first.displayName());
        System.out.println("second name=" + second.displayName());
        System.out.println("same first value=" +
                first.equals(new Product("PEN", 10, 2)));
    }
}
~~~

Run:

~~~bash
javac RecordInterfaceIntegrationDemo.java
java RecordInterfaceIntegrationDemo
~~~

Output:

~~~text
PEN:20
BOOK:50
first name=Pen
second name=Book
same first value=true
~~~

Analysis:

- The `sku` component automatically generates the public accessor `sku()`, satisfying the method of `ProductView`.
- The interface method `total()` **does not match any component**, so Product implements it using an explicit instance method.
- The interface default `summary()` properly calls `sku()`/`total()` on the receiver record.
- The static field `LABELS` is a shared catalog and is not included in component equality.
- The compact constructor validates the fields without adding any new instance field.
- The Product record is final; it does not need to and cannot be subclassed to add state.
- `Math.multiplyExact` detects multiplication overflow; real-world code needs standardized pricing/currency; here the example uses small long units.

## 42. Contract Testing in Plain Java (No JUnit Required)

Save **`RecordRulesContractTest.java`**:

~~~java
public class RecordRulesContractTest {
    interface Identified {
        String id();
    }

    record Item(String id, int count)
            implements Identified {
        static final String PREFIX = "ITEM";

        Item {
            if (count < 0) {
                throw new IllegalArgumentException("count");
            }
        }

        String display() {
            return PREFIX + ":" + id + ":" + count;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        Item first = new Item("A", 2);
        Item second = new Item("A", 2);
        Identified view = first;

        check(first != second, "different objects");
        check(first.equals(second), "component equality");
        check(first.hashCode() == second.hashCode(),
                "hash consistency");
        check("A".equals(view.id()), "interface accessor");
        check(first.getClass().getSuperclass() == Record.class,
                "direct superclass");
        check("ITEM:A:2".equals(first.display()),
                "static shared constant");

        try {
            new Item("B", -1);
            throw new AssertionError("invalid item accepted");
        } catch (IllegalArgumentException expected) {
            // Invariant is enforced at construction.
        }

        System.out.println("record rules checks passed");
    }
}
~~~

Run:

~~~bash
javac RecordRulesContractTest.java
java RecordRulesContractTest
~~~

Output:

~~~text
record rules checks passed
~~~

The test verifies identity, generated value equality/hashing, interface implementation, direct superclass, static constant, and invariants. The `check` method always runs; it does not depend on Java `assert`, which can be disabled by default.

## 43. Practice Exercises

### Exercise A: Why Is Declaring an Additional Field Invalid?

~~~java
record Temperature(double celsius) {
    // private double fahrenheit; // Invalid.
}
~~~

**Answer:** The record representation is fixed by the header. Write:

~~~java
double fahrenheit() {
    return celsius * 9.0 / 5.0 + 32.0;
}
~~~

inside the record body, or make Fahrenheit a separate component **only if the domain genuinely treats it as stored state** and wants equality/constructors to reflect that value.

### Exercise B: Is the Interface Implemented Automatically?

~~~java
interface Named {
    String name();
}

record User(String name) implements Named {
}
~~~

**Answer:** Yes. The generated `public String name()` satisfies the `Named.name()` signature.

### Exercise C: What About a JavaBeans Method?

~~~java
interface NamedBean {
    String getName();
}

// record User(String name) implements NamedBean { }
~~~

**Answer:** Insufficient. A custom `public String getName(){return name;}` is needed in the record.

### Exercise D: Can a Record Extend a Class with Fields?

~~~java
class Base {
    int id;
}

// record Item(int n) extends Base { }
~~~

**Answer:** No. A record directly extends Record and is implicitly final; use composition/an interface or a normal class depending on the goal.

### Exercise E: Is a Static Field Allowed?

~~~java
record Item(String code) {
    private static int count;
}
~~~

**Answer:** Yes. `count` is shared class state and does not participate in generated record equality.

### Exercise F: Is a Sealed Interface with a Record Valid?

~~~java
sealed interface State permits Ready {
}
record Ready(int code) implements State {
}
~~~

**Answer:** Yes, within a valid scope/file. A record is implicitly final, satisfying the permitted implementation requirement of a sealed interface.

### Exercise G: Do Interface Constants Add Instance Fields to a Record?

~~~java
interface Flags {
    int MASK = 7;
}
record Value(int amount) implements Flags {
}
~~~

**Answer:** No. `Flags.MASK` is a static constant, not a record component field.

### Exercise H: Can a Built-in Default Method Be Used?

~~~java
interface NameView {
    String name();
    default String title() {
        return "Mr/Ms " + name();
    }
}
record Person(String name) implements NameView {
}
~~~

**Answer:** Yes. The record's generated `name()` and the inherited default `title()` work together. Check business-specific title rules before applying this in practice.

### Exercise I: What If Two Interfaces Have Conflicting Default Methods?

**Answer:** The record generally must declare an override with the full signature to resolve the conflict. Inside the override, it can call `A.super.method()` when Java allows it.

### Exercise J: Does a Final Field Referencing a List Guarantee Deep Immutability?

**Answer:** No. Identify mutable aliases and use `List.copyOf`/immutable elements or an appropriate defensive copy.

## 44. Quick Review Questions and Answers

**Question 1.** What access modifiers does the field generated for each record component have?  
**Answer:** `private final` and non-static.

**Question 2.** Can you declare an additional non-static field in the record body?  
**Answer:** No; compile-time error.

**Question 3.** Can there be a static field in a record body?  
**Answer:** Yes.

**Question 4.** Can there be an instance initializer block?  
**Answer:** No.

**Question 5.** Can there be a static initializer block?  
**Answer:** Yes.

**Question 6.** What should be used to validate component values?  
**Answer:** A canonical constructor, typically a compact canonical constructor.

**Question 7.** Can a record extend `SomeClass`?  
**Answer:** No, a record does not have an extends clause.

**Question 8.** What is the direct superclass of a record?  
**Answer:** `java.lang.Record`.

**Question 9.** Is a record implicitly `final`?  
**Answer:** Yes.

**Question 10.** Can you declare `abstract record`?  
**Answer:** No.

**Question 11.** Can you declare `sealed record`?  
**Answer:** No.

**Question 12.** Can a record implement a sealed interface?  
**Answer:** Yes, if the record is a permitted implementation.

**Question 13.** Can a record implement multiple interfaces?  
**Answer:** Yes, provided there are no unresolvable conflicts.

**Question 14.** Can the generated accessor `value()` implement an interface's `value()` method?  
**Answer:** Yes, when the method return type/signature are compatible.

**Question 15.** Does the generated accessor `value()` automatically implement `getValue()`?  
**Answer:** No.

**Question 16.** If a record implements `Comparable`, is `compareTo` generated?  
**Answer:** No; an appropriate implementation must be provided.

**Question 17.** If a record implements an interface with a default method, does it need to rewrite it?  
**Answer:** No, if there is no conflict and the default implementation is suitable.

**Question 18.** When is `A.super.method()` used?  
**Answer:** It can call a specific default method inside an override when resolving a multiple-interface conflict.

**Question 19.** Does an interface field `int X=1` become an instance field in a record?  
**Answer:** No; it is a static constant belonging to the interface.

**Question 20.** Does the generated `equals` consider static fields?  
**Answer:** No; equality is based on record components.

**Question 21.** Are two different record types that implement the same interface and share the same ID equal by default?  
**Answer:** No; generated record equality has type and components semantics.

**Question 22.** Can a record override `toString()` itself?  
**Answer:** Yes; keep the behavior/presentation consistent with the contract.

**Question 23.** Can a record declare an abstract instance method for subclasses to override?  
**Answer:** No; records are final and abstract method declarations are prohibited.

**Question 24.** Can a mutable component in a record be mutated outside the record?  
**Answer:** Yes, if the reference is shared and the data type is mutable.

**Question 25.** Does a mutable static field automatically make a record thread-safe?  
**Answer:** No.

**Question 26.** If a per-instance mutable cache is needed, what should you do?  
**Answer:** Consider a normal class or an external cache design; records prohibit extra instance fields.

**Question 27.** Does a member/local record have an implicit enclosing instance?  
**Answer:** No; they are implicitly static.

**Question 28.** Is the `Serializable` interface automatically implemented by records?  
**Answer:** No; it must be declared if needed.

**Question 29.** Can you declare a generic record `Box<T>` implementing a generic interface?  
**Answer:** Yes, if the type arguments/signatures are valid.

**Question 30.** What is the biggest difference between inheritance and implements for records?  
**Answer:** A record **cannot extend a user class or be subclassed**, but **can implement interfaces to participate in polymorphism**.

## 45. Code Review Checklist

- [ ] Does the header completely list the instance state meaningful to the representation?
- [ ] Does the body contain any invalid non-static field declaration?
- [ ] Is there any prohibited instance initializer block?
- [ ] Are validation/normalization placed in an appropriate canonical constructor?
- [ ] Do static fields contain only shared metadata/state that is genuinely necessary?
- [ ] Has static mutable state handled concurrency/lifecycle properly?
- [ ] Does it avoid using `extends SomeBase` or inheriting from another record?
- [ ] Does it avoid declaring `abstract`/`sealed`/`non-sealed` on the record?
- [ ] Are interfaces used to express shared behavior instead of class inheritance?
- [ ] Does the generated accessor signature match the interface method?
- [ ] If an interface requires a JavaBeans getter with a different name, has an adapter method been written?
- [ ] Are there any unresolved conflicts among multiple default methods?
- [ ] Does the Comparable comparator have any overflow/collision/consistency risk?
- [ ] Does the sealed interface `permits` clause follow Java 17 rules?
- [ ] Are `private final` component fields not mistakenly assumed to be deeply immutable?
- [ ] Do List/array/custom mutable types have an appropriate defensive-copy policy?
- [ ] Are generated equals/hashCode compatible with usage as a Map/Set key?
- [ ] Are there any custom equals/hashCode/toString implementations violating the contract?
- [ ] Is the record being forced into a mutable entity with in-place setter semantics?
- [ ] If there is a per-instance cache/resource/lock, would a normal class be more appropriate?
- [ ] Is a member/local record inadvertently trying to use an enclosing instance `this`?
- [ ] Do serialization/framework use cases support Java records according to their contract?
- [ ] Have the examples been compiled on JDK17 and has stdout been cross-checked?

## 46. References

- Java Language Specification Java SE 17, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): a record is a special class, implicitly final, superclass `Record`, can implement interfaces.
- JLS Java SE 17, [`8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): record header/components, names and types.
- JLS Java SE 17, [`8.10.2 — Record Body Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.2): prohibits non-static field declarations, instance initializers, abstract/native methods; allows static fields/initializers.
- JLS Java SE 17, [`8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): private final component fields, public accessors, generated Object methods.
- JLS Java SE 17, [`8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical/compact/non-canonical constructors.
- JLS Java SE 17, [`8.1.2 — Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): type parameters.
- JLS Java SE 17, [`8.1.5 — Superinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.5): implements interfaces.
- JLS Java SE 17, [`8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): sealed interface implementation constraints.
- JLS Java SE 17, [`9.4.3 — Interface Method Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.3): default/static interface methods.
- Oracle Java 17 Language Guide, [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): record model, limitations, interface support.
- OpenJDK [JEP 395 — Records](https://openjdk.org/jeps/395): design of value-oriented transparent carriers.
- Java API 17, [java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): superclass.
- Java API 17, [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable copies.
- Java API 17, [Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html): natural ordering contract.
- Java API 17, [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): marker interface, not enabled by default for every record.

## Summary

A record describes **a group of named values** through the record header; those values are stored by the compiler using **private final instance component fields**. Precisely because its representation must be transparent, a record **does not allow declaring additional instance fields or instance initializer blocks**. You can still have static fields/static initializer blocks and instance/static methods, but static data does not automatically become a component or participate in component equality.

Regarding inheritance, a record is **implicitly final**, directly extends `java.lang.Record`, and has no `extends` clause. It cannot inherit from a user superclass, cannot be subclassed, and cannot be an abstract/sealed record. When code reuse/polymorphism is needed, choose **implementing interfaces**, default methods, sealed interface variants, and **composition**.

A generated accessor such as `name()` can automatically implement an interface method with a matching signature; a differently named method such as `getName()`, `get()`, or `compareTo()` usually needs to be written explicitly by you. Finally, remember that **a final component field does not mean deeply immutable data**: if a component holds mutable objects, choose a snapshot/defensive copy according to the contract.

Properly understanding the three boundaries **the record header determines instance state — a final record restricts class inheritance — interfaces provide behavior polymorphism** will help you use Java 17 records accurately and avoid designing mutable objects that misfit the model.
