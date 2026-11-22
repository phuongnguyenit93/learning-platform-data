# Choosing a Record or an Ordinary Class in Java 17+

**Both `record` and `class` define reference types in Java, but they convey different design intents.** A record is suitable when the object is primarily **a transparent data bundle with defined components and value-like semantics**. An ordinary class is suitable when the object needs **identity, lifecycle, complex internal state, controlled mutability, representation hiding, or inheriting from another class**.

Brief comparison:

~~~java
record Point(int x, int y) {}
~~~

~~~java
final class PointClass {
    private final int x;
    private final int y;

    PointClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    int x() {
        return x;
    }

    int y() {
        return y;
    }

    // If value equality is needed, you also have to write equals/hashCode.
}
~~~

A record is shorter not only because Java generates methods for it; it also declares a contract: **the observable state of an instance is the set of record components**. The fact that a type has only two fields does not mean it should always be a record.

This standalone lesson belongs to **Java Core — Class & Object / Record**, prioritizing **Java 17+**. Complete examples include filenames, `javac`/`java` commands, and expected stdout. Snippets intended to explain a specific point are clearly marked. The goal is to choose the right design before optimizing syntax.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Identify a **transparent data carrier** and distinguish it from an **entity with identity**.
2. Decide when a record makes sense and when an ordinary class is better.
3. Explain how the compiler generates the constructor, accessors, `equals`, `hashCode`, and `toString` for a record.
4. Understand that a record has final component fields but is not deeply immutable by default.
5. Distinguish between value equality and identity equality.
6. Know that records are implicitly final, implicitly extend `java.lang.Record`, and cannot extend an arbitrary class.
7. Understand that a class can be mutable or immutable, final or extensible.
8. Know that a record cannot declare additional instance fields or instance initializer blocks.
9. Know that a record can still have instance/static methods, static fields, and implement interfaces.
10. Write a compact/canonical constructor for validation and normalization.
11. Recognize issues with shallow copies, mutable Lists, Maps, and arrays.
12. Understand why an array component affects the default equals/hashCode.
13. Know that an ordinary class can deliberately hide its internal representation.
14. Predict the impact on the API of adding, removing, or changing the type of record components.
15. Choose a model for a DTO, value object, domain entity, service, repository, and resource.
16. Know that records are not automatically suitable for every ORM/entity framework.
17. Understand that the method naming `component()` differs from JavaBean-style `getComponent()`.
18. Understand that identity, version, lifecycle, concurrency, thread-safety, and serializability do not depend solely on syntax.
19. Choose a class when inheritance/hook points or mutable caching/locking are needed.
20. Evaluate performance through measurement rather than assuming a record is always smaller/faster.
21. Refactor from a class to a record and vice versa while still verifying the contract.
22. Test invariants, aliasing, equality, hash stability, and the public API for their intended purpose.

## 2. The First Question: “Is This Data a Value or an Entity?”

A **value object** is usually defined primarily by its data:

- A coordinate point (x, y).
- A start/end date range.
- A currency code and monetary amount.
- A computation result.
- An immutable configuration snapshot.
- A data transfer record with stable components.

Two instances carrying the same components are expected to be **equivalent by value**. This is a good candidate for a record.

An **entity** usually has its own identity over time:

- An account with an ID and a changing balance.
- An order with transitioning states and a lifecycle.
- A session, socket, database transaction, or thread owner.
- An aggregate root that must guard state changes.
- An object with audit history or optimistic locking.

Two entities having the same data fields **are not necessarily the same entity**. An ordinary class usually allows expressing identity/lifecycle more clearly.

**Note:** There is no rule that “every domain entity must be a class, every DTO must be a record”. Examine the invariants and API of each type.

## 3. Core Decision Table

| Criterion | Record is usually suitable | Ordinary class is usually suitable |
| --- | --- | --- |
| Characteristic | Transparent value data | Identity, behavior, lifecycle, encapsulated state |
| Fields | From components, final | Arbitrary instance fields and mutability |
| Constructor | Canonical constructor tied to components | Constructors flexible with respect to representation |
| Accessors | `name()`, `age()` matching components | Custom-designed getter/command API |
| Default equality | By record components | By Object identity if not overridden |
| Default `hashCode` | Based on components | Identity-based Object behavior if not overridden |
| Default `toString` | Prints name/components | `ClassName@...` per Object implementation |
| Extends base class | Cannot choose a superclass | Can extend a non-final class |
| Implements interfaces | Yes | Yes |
| Additional instance fields | No | Yes |
| Instance initializer blocks | No | Yes |
| Automatically deeply immutable | No | Also no |
| Mutable business state | Usually unsuitable | Can be represented with control |
| Hidden internal representation | More limited due to transparent components | Flexible |
| Framework requiring no-arg mutable bean | May be unsuitable | May be suitable |
| Stable API across representation changes | Requires special consideration | Can hide state |
| Reusable service/resource | Usually not recommended | Usually suitable |

The design choice must be based on the **logical nature of the object**, not just the number of source lines.

## 4. What Java Generates for a Record

Given:

~~~java
record Coordinate(int x, int y) {}
~~~

Java provides:

- Two private final component fields `x`, `y`.
- Accessors `x()` and `y()`.
- Canonical constructor `Coordinate(int x, int y)` if you do not declare one yourself.
- `equals(Object)` with component-based equality.
- `hashCode()` based on components.
- `toString()` consisting of the record name and component names/values.

A record type is final, extends `java.lang.Record`, and can implement interfaces. A record has no arbitrary instance fields outside its components.

### What a record does **not** generate

- Validation for null/range/format.
- Defensive copying of a List, array, or mutable object.
- Deep immutability.
- Database persistence, JSON conversion, or ORM mapping.
- Builder, setter, or lifecycle callback.
- External stable ID for each instance.
- Custom business formatting or privacy-safe logging policy.

Those needs still require explicit design.

## 5. Runnable Program: Record Auto-Generates Operations

Create **`RecordBasicsDemo.java`**:

~~~java
public class RecordBasicsDemo {
    record Coordinate(int x, int y) {}

    public static void main(String[] args) {
        Coordinate first = new Coordinate(3, 4);
        Coordinate second = new Coordinate(3, 4);

        System.out.println("x=" + first.x());
        System.out.println("y=" + first.y());
        System.out.println("equal=" + first.equals(second));
        System.out.println("same object=" + (first == second));
        System.out.println(first);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordBasicsDemo.java
java RecordBasicsDemo
~~~

Stdout:

~~~text
x=3
y=4
equal=true
same object=false
Coordinate[x=3, y=4]
~~~

The two references are different (`== false`), yet the record values are equal via the generated `equals`. Do not use `==` to compare the logical values of records you create with independent `new` calls.

## 6. Can an Ordinary Class Emulate a Record?

Yes. An ordinary class can define final fields, a constructor, accessors, `equals`, `hashCode`, and `toString` to achieve similar value semantics.

What a record provides is:
- less boilerplate when the representation is simply the data components;
- compiler checks for certain structural restrictions;
- clear value-carrier intent in the declaration;
- standard reflection support for record components.

What a **class** still provides:
- control over a hidden representation;
- freedom to choose constructors/APIs;
- mutable or immutable state;
- the ability to extend a suitable superclass;
- fields and internal helpers that do not necessarily need to be exposed as record components.

Therefore, the question is not “Can a class do it?” but “Is the public contract truly those component values?”.

## 7. Runnable Program: Immutable Class with Explicit Value Equality

Create **`ImmutableClassDemo.java`**:

~~~java
import java.util.Objects;

public class ImmutableClassDemo {
    static final class Coordinate {
        private final int x;
        private final int y;

        Coordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        int x() {
            return x;
        }

        int y() {
            return y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Coordinate point)) {
                return false;
            }
            return x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }

        @Override
        public String toString() {
            return "Coordinate[x=" + x + ", y=" + y + "]";
        }
    }

    public static void main(String[] args) {
        Coordinate a = new Coordinate(3, 4);
        Coordinate b = new Coordinate(3, 4);

        System.out.println("equal=" + a.equals(b));
        System.out.println("hash equal=" +
                (a.hashCode() == b.hashCode()));
        System.out.println(a);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ImmutableClassDemo.java
java ImmutableClassDemo
~~~

Stdout:

~~~text
equal=true
hash equal=true
Coordinate[x=3, y=4]
~~~

Thus, a record is not the only option for a value object; it is suitable when explicit components accurately reflect the desired representation and API.

## 8. Comparing Value Identity and Domain Identity

Consider:

~~~java
record CustomerSnapshot(long id, String name) {}
~~~

Two snapshots with the same id and name will have `equals` return true. If the customer id is the same but the name changes, the snapshots will have `equals` return false. That can be **correct** if a snapshot means “the state at the time of observation”.

Conversely, for a domain `Customer` entity:
- id may determine identity;
- name may change;
- persistence version, state, and business operations have a lifecycle;
- equality may be based on domain identity or strictly on reference, depending on the design.

If a record `Customer(id, name)` is used instead of an entity where the business considers only the id important, the generated equality may have the wrong semantics.

**Rule:** State this upfront: “When are two instances considered the same value? When are they considered the same entity?”

## 9. Runnable Example: Same Entity ID but Different Snapshots

Create **`SnapshotVsIdentityDemo.java`**:

~~~java
public class SnapshotVsIdentityDemo {
    record CustomerSnapshot(long id, String name) {}

    static final class Customer {
        private final long id;
        private String name;

        Customer(long id, String name) {
            this.id = id;
            this.name = name;
        }

        long id() {
            return id;
        }

        void rename(String newName) {
            if (newName == null || newName.isBlank()) {
                throw new IllegalArgumentException("name");
            }
            name = newName;
        }

        CustomerSnapshot snapshot() {
            return new CustomerSnapshot(id, name);
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer(7, "Mai");
        CustomerSnapshot before = customer.snapshot();

        customer.rename("Mai Anh");
        CustomerSnapshot after = customer.snapshot();

        System.out.println("same customer ID=" +
                (before.id() == after.id()));
        System.out.println("same snapshot=" + before.equals(after));
        System.out.println(after);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SnapshotVsIdentityDemo.java
java SnapshotVsIdentityDemo
~~~

Stdout:

~~~text
same customer ID=true
same snapshot=false
CustomerSnapshot[id=7, name=Mai Anh]
~~~

This is a very useful hybrid design: a **mutable entity class** executes domain commands, while a **record snapshot** transfers the current state into a data value.

## 10. Is an “Immutable Record” Always True?

The record fields corresponding to components are `final`. However, if a component type is a mutable object, Java only fixes the **reference**, not the contents of that object.

~~~java
record Team(java.util.List<String> members) {}
~~~

The `members` field cannot be reassigned to another List after construction, but the List object itself can mutate if the caller retains an alias.

### Runnable Program

Create **`ShallowRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowRecordDemo {
    record Team(List<String> members) {}

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Mai"));
        Team team = new Team(source);

        source.add("An");
        System.out.println(team.members());

        team.members().add("Binh");
        System.out.println(source);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ShallowRecordDemo.java
java ShallowRecordDemo
~~~

Stdout:

~~~text
[Mai, An]
[Mai, An, Binh]
~~~

A record without setters can still expose a mutable component. If the API promises an immutable snapshot, you must perform defensive copying.

## 11. A Record Can Be an Immutable Value Carrier with Explicit Validation/Copy

Example:

~~~java
record Team(java.util.List<String> members) {
    Team {
        members = java.util.List.copyOf(members);
    }
}
~~~

`List.copyOf` creates an unmodifiable snapshot of the list structure (it may reuse a suitable unmodifiable source), forbids null elements, and does not deep-copy mutable element objects.

With `List<String>`, because String is immutable, this pattern is usually sufficient to protect value semantics. With `List<MutablePerson>`, achieving deep immutability also requires snapshotting the elements.

### A Class Can Do This Too

An ordinary class is no less safe if the constructor defensively copies and accessors do not expose the representation. Protecting state is a **design contract**, not the “magic” of a record.

## 12. Runnable Program: Record with Defensive Copy

Create **`SafeTeamRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeTeamRecordDemo {
    record Team(List<String> members) {
        Team {
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Mai"));
        Team team = new Team(source);

        source.add("An");
        System.out.println("source=" + source);
        System.out.println("record=" + team.members());

        try {
            team.members().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SafeTeamRecordDemo.java
java SafeTeamRecordDemo
~~~

Stdout:

~~~text
source=[Mai, An]
record=[Mai]
unmodifiable
~~~

The record is stable against external structural List changes. If you do not want `List.copyOf` forbidding null elements or do not want snapshot semantics, a different design is needed and must be documented clearly.

## 13. Arrays Are a Case Requiring Special Consideration

~~~java
record Payload(byte[] bytes) {}
~~~

An array is mutable, and the default record accessor `bytes()` returns the array reference itself. Furthermore, the generated `equals`/`hashCode` handles array components by identity, **without automatically comparing byte contents**.

A record with an array component that wants value semantics needs to:
- copy the input in the constructor;
- copy the output in the accessor;
- override `equals`/`hashCode` if element-wise equality is desired;
- consider making `toString` not print overly long or sensitive binary data.

When those customizations make up most of the implementation, an ordinary immutable class with explicit `byteAt(index)`, `size()`, and `copyBytes()` may be easier to manage.

## 14. Runnable Program: Record with Array and Custom Content Equality

Create **`RecordBytesDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class RecordBytesDemo {
    record Blob(byte[] bytes) {
        Blob {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Blob blob &&
                    Arrays.equals(bytes, blob.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }

        @Override
        public String toString() {
            return "Blob[length=" + bytes.length + "]";
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Blob a = new Blob(input);
        Blob b = new Blob(new byte[]{1, 2, 3});

        input[0] = 99;

        System.out.println("equal=" + a.equals(b));
        System.out.println("first=" + a.bytes()[0]);
        System.out.println(a);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordBytesDemo.java
java RecordBytesDemo
~~~

Stdout:

~~~text
equal=true
first=1
Blob[length=3]
~~~

When the accessor performs a defensive copy and equality is based on bytes, the record can be stable. However, an ordinary class can also express the same contract; representation complexity is a reason to consider a class.

## 15. Representation Scope: What Does a Record Expose?

In:

~~~java
public record Address(String city, String postalCode) {}
~~~

`city()` and `postalCode()` are public accessors, and the canonical constructor has component parameters matching that shape. The record expresses that the two components are **the API surface carrying data meaning**.

With an ordinary class:

~~~java
public final class Address {
    private final String normalizedKey;

    public Address(String city, String postalCode) {
        // Can store a different internal representation.
        normalizedKey = city + "|" + postalCode;
    }

    public String display() {
        return normalizedKey;
    }
}
~~~

A class can hide its representation and expose only the `display()` behavior. If later you change from two fields to a normalized key or switch the backend structure, the public API can remain unchanged when the design allows it.

**Choose a record when exposing the components is the actual goal**, not just because the first version has a few fields.

## 16. Component Names Are Part of the API

In a record:

~~~java
public record Employee(String firstName, String lastName) {}
~~~

Clients use `employee.firstName()` and `employee.lastName()`. Renaming a component to `givenName` can cause code calling the old accessor to fail to compile.

Adding a component to a record:
- changes the canonical constructor signature;
- creates a new accessor;
- may change the generated `equals/hashCode/toString` behavior;
- affects deconstruction/serialization/framework bindings according to the compatibility contract.

You can provide overloaded constructors or compatibility methods if appropriate, but that does not mean every change is binary/source compatible.

### An Ordinary Class Also Has an API Cost

A class changing its public constructors/getters also breaks callers. The difference is that a class has more freedom to keep the API **not tied to the representation**.

## 17. Runnable Example: Constructor Overload Helps Keep Old Call Sites

Create **`RecordOverloadDemo.java`**:

~~~java
public class RecordOverloadDemo {
    record Product(String code, int quantity, String note) {
        Product {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code");
            }
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity");
            }
            note = note == null ? "" : note;
        }

        Product(String code, int quantity) {
            this(code, quantity, "");
        }
    }

    public static void main(String[] args) {
        Product oldForm = new Product("A", 2);
        Product newForm = new Product("A", 2, "gift");

        System.out.println(oldForm);
        System.out.println(newForm);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordOverloadDemo.java
java RecordOverloadDemo
~~~

Stdout:

~~~text
Product[code=A, quantity=2, note=]
Product[code=A, quantity=2, note=gift]
~~~

The `Product(String,int)` overload can allow source clients to continue passing two arguments. However, the record shape now has three components, and generated equality also considers `note`; this is still a semantic API change that requires review.

## 18. Record Constructors: Canonical and Compact

A canonical constructor has parameters matching the record components. The compact form reduces boilerplate:

~~~java
record Age(int value) {
    Age {
        if (value < 0 || value > 150) {
            throw new IllegalArgumentException("age");
        }
    }
}
~~~

If you want to normalize:

~~~java
record Code(String text) {
    Code {
        text = text.strip().toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

In a compact constructor:
- the names `value`/`text` are implicit canonical parameters;
- the compiler automatically assigns the component fields at the normal end of the body;
- assigning `this.text = ...` inside a compact constructor is invalid;
- if an invariant is violated, throw before the object is published.

An ordinary class constructor decides its assignments and internal fields on its own. This is an advantage when a complex representation is needed, though it also requires writing everything out in full.

## 19. Runnable Program: Validation in a Record and a Class

Create **`ValidationComparisonDemo.java`**:

~~~java
import java.util.Objects;

public class ValidationComparisonDemo {
    record UsernameRecord(String value) {
        UsernameRecord {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toLowerCase(java.util.Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
        }
    }

    static final class UsernameClass {
        private final String value;

        UsernameClass(String value) {
            String normalized =
                    Objects.requireNonNull(value, "value")
                            .strip()
                            .toLowerCase(java.util.Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
            this.value = normalized;
        }

        String value() {
            return value;
        }
    }

    public static void main(String[] args) {
        UsernameRecord record = new UsernameRecord("  Admin ");
        UsernameClass clazz = new UsernameClass("  Admin ");

        System.out.println(record.value());
        System.out.println(clazz.value());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValidationComparisonDemo.java
java ValidationComparisonDemo
~~~

Stdout:

~~~text
admin
admin
~~~

A record expresses this with less code; **both can protect invariants properly**. Do not choose based solely on validation capability.

## 20. Records Do Not Allow Arbitrary Additional Instance Fields

A record declaration cannot declare extra instance fields beyond the fields from its components:

~~~java
record Request(String id) {
    // private int retryCount; // Compile error.
}
~~~

Nor may it contain instance initializer blocks like an ordinary class. A record may have static fields/methods, instance methods, compact/canonical/overloaded constructors, and valid nested type declarations.

### Why Does This Restriction Make Sense?

A record declares that its instance state is described by its components. If hidden instance fields were added, the default structural equality and transparent data-carrier model could easily become inconsistent.

An ordinary class allows adding retryCount, caches, locks, lazy computation state, or resource handles that are not part of the public API.

## 21. Runnable Program: Class with an Internal Cache

Create **`CachingClassDemo.java`**:

~~~java
public class CachingClassDemo {
    static final class Document {
        private final String text;
        private Integer cachedLength;

        Document(String text) {
            this.text = java.util.Objects.requireNonNull(text);
        }

        int length() {
            if (cachedLength == null) {
                cachedLength = text.length();
            }
            return cachedLength;
        }
    }

    public static void main(String[] args) {
        Document document = new Document("Java");

        System.out.println(document.length());
        System.out.println(document.length());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CachingClassDemo.java
java CachingClassDemo
~~~

Stdout:

~~~text
4
4
~~~

This is only an example of **hidden instance state** that an ordinary class can hold. If run in a multithreaded environment, a lazy cache needs a thread-safety policy; a record is not incapable of computation or external caching, but it cannot freely add per-instance fields like a class.

## 22. Records Have Methods, Not Just Getters

A record can contain pure business operations based on its components:

~~~java
record Rectangle(int width, int height) {
    Rectangle {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("dimensions");
        }
    }

    long area() {
        return (long) width * height;
    }

    boolean isSquare() {
        return width == height;
    }
}
~~~

Methods do not turn a record into an ordinary class; they interpret the data components.

**Signal favoring a record:** The method takes the current state, performs computations/lookups, and returns a new result or a new record without mutating the current record.

**Signal favoring a class:** The method coordinates a lifecycle, modifies internal state, holds a transaction/session, or changes identity over a long period.

## 23. Runnable Program: Behavior Can Live Inside a Record

Create **`RectangleRecordDemo.java`**:

~~~java
public class RectangleRecordDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        long area() {
            return (long) width * height;
        }

        boolean isSquare() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(3, 4);
        Rectangle b = new Rectangle(5, 5);

        System.out.println("area=" + a.area());
        System.out.println("square=" + b.isSquare());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RectangleRecordDemo.java
java RectangleRecordDemo
~~~

Stdout:

~~~text
area=12
square=true
~~~

You should not conclude that “a record cannot contain logic”. It can have methods, as long as the overall value-carrier contract remains valid.

## 24. Mutation and Domain Commands

An entity often needs operations based on state transitions:

~~~java
final class Wallet {
    private int cents;

    Wallet(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("initial");
        }
        cents = initial;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        cents = Math.addExact(cents, amount);
    }

    int balance() {
        return cents;
    }
}
~~~

If you use a record `Wallet(int cents)`, the final record field cannot be mutated by `deposit`. You can design an immutable value wallet where `deposit` returns a new record, but it will have **identity/lifecycle differences**. Choose according to the domain: does an account entity need commands that change its current state, or a value state snapshot?

## 25. Runnable Program: Class with Mutable State

Create **`WalletEntityDemo.java`**:

~~~java
public class WalletEntityDemo {
    static final class Wallet {
        private int cents;

        Wallet(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial");
            }
            cents = initial;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount");
            }
            cents = Math.addExact(cents, amount);
        }

        int balance() {
            return cents;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);

        wallet.deposit(50);
        wallet.deposit(25);

        System.out.println("balance=" + wallet.balance());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WalletEntityDemo.java
java WalletEntityDemo
~~~

Stdout:

~~~text
balance=175
~~~

`Wallet` preserves the identity of the same object across both operations. If multiple threads can update it concurrently, a synchronization/transaction policy is needed; this demonstration does not promise thread safety.

## 26. What If You Choose an Immutable Record Instead of a Mutable Class?

You can design the method to return a **new record**:

~~~java
record Balance(int cents) {
    Balance {
        if (cents < 0) {
            throw new IllegalArgumentException("cents");
        }
    }

    Balance deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        return new Balance(Math.addExact(cents, amount));
    }
}
~~~

Calling code must retain the returned value:

~~~java
Balance before = new Balance(100);
Balance after = before.deposit(50);
~~~

`before` still has 100. `after` holds 150.

This is a **functional/value-oriented update**, not a mutating command. In a concurrent system, replacing a shared reference to a Balance still requires separate synchronization, such as an atomic update or a transaction.

## 27. Runnable Program: Immutable Update Returning a New Record

Create **`ImmutableBalanceDemo.java`**:

~~~java
public class ImmutableBalanceDemo {
    record Balance(int cents) {
        Balance {
            if (cents < 0) {
                throw new IllegalArgumentException("cents");
            }
        }

        Balance deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount");
            }
            return new Balance(Math.addExact(cents, amount));
        }
    }

    public static void main(String[] args) {
        Balance before = new Balance(100);
        Balance after = before.deposit(50);

        System.out.println("before=" + before.cents());
        System.out.println("after=" + after.cents());
        System.out.println("same object=" + (before == after));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ImmutableBalanceDemo.java
java ImmutableBalanceDemo
~~~

Stdout:

~~~text
before=100
after=150
same object=false
~~~

If the use case treats Balance as an **amount value**, a record makes sense. If it is an account that lives across transactions, a class entity holding business state and emitting a Balance snapshot may make more sense.

## 28. Class Inheritance: Records Are Intentionally Restricted

Every record implicitly extends `java.lang.Record` and is implicitly final. Therefore:

~~~java
// record Child(...) extends Base { } // Invalid.
// class Sub extends MyRecord { }       // Invalid.
~~~

An ordinary class can:

~~~java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}
~~~

If a design needs a base class with common implementation/state and a polymorphic subclass hierarchy, ordinary classes are suitable.

However, **prefer interfaces/composition when possible**; do not choose a class merely because you want to inherit a small amount of boilerplate.

## 29. Records Can Still Implement Interfaces

~~~java
interface Measurable {
    long area();
}

record Rectangle(int width, int height)
        implements Measurable {
    @Override
    public long area() {
        return (long) width * height;
    }
}
~~~

A record is final, yet implements interfaces normally. An API taking Measurable can accept record and class implementations.

This is an important choice for separating **contract behavior** from **representation data**:
- A record when behavior is determined by components.
- A class when different state/identity/lifecycle is needed.
- Callers depend only on the interface.

## 30. Runnable Program: Record and Class Sharing an Interface

Create **`CommonInterfaceDemo.java`**:

~~~java
public class CommonInterfaceDemo {
    interface Measurable {
        long area();
    }

    record Rectangle(int width, int height)
            implements Measurable {
        @Override
        public long area() {
            return (long) width * height;
        }
    }

    static final class Square implements Measurable {
        private final int side;

        Square(int side) {
            this.side = side;
        }

        @Override
        public long area() {
            return (long) side * side;
        }
    }

    static void show(Measurable shape) {
        System.out.println("area=" + shape.area());
    }

    public static void main(String[] args) {
        show(new Rectangle(3, 4));
        show(new Square(5));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CommonInterfaceDemo.java
java CommonInterfaceDemo
~~~

Stdout:

~~~text
area=12
area=25
~~~

An interface can contain both record and class implementations; there is no need to choose a single form for the entire hierarchy.

## 31. Records and Sealed Interfaces (Java 17)

Java 17 supports sealed interfaces to restrict direct implementations:

~~~java
sealed interface Outcome permits Success, Failure {}

record Success(String value) implements Outcome {}

record Failure(String message) implements Outcome {}
~~~

Because records are implicitly final, they are a natural choice for the variant data values of a sealed interface. However, ordinary final classes can also be permitted implementations.

**Limitation:** A record cannot extend an arbitrary sealed **class**, because it already extends Record; it can implement a sealed **interface** when allowed by permits.

The sealed interface + records structure is useful for finite result models; combining it with switch/instanceof handling in Java 17 syntax is already supported without requiring preview features.

## 32. Runnable Program: Sealed Interface with Two Records

Create **`SealedRecordResultDemo.java`**:

~~~java
public class SealedRecordResultDemo {
    sealed interface Result permits Success, Failure {}

    record Success(String value) implements Result {}

    record Failure(String message) implements Result {}

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "ok:" + success.value();
        }
        if (result instanceof Failure failure) {
            return "error:" + failure.message();
        }
        throw new IllegalStateException("unknown");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("data")));
        System.out.println(describe(new Failure("missing")));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedRecordResultDemo.java
java SealedRecordResultDemo
~~~

Stdout:

~~~text
ok:data
error:missing
~~~

Java 17 supports `instanceof` pattern matching; the code does not use record patterns or pattern-matching switch, which differ in Java version milestones.

## 33. Are Generic Records Allowed?

Yes, a record can declare type parameters:

~~~java
record Pair<L, R>(L left, R right) {}
~~~

This differs from an enum declaration (which cannot be generic in the same way). A generic record is still subject to the rules on components, constructors, and shallow immutability.

### Runnable Program

Create **`GenericRecordDemo.java`**:

~~~java
public class GenericRecordDemo {
    record Pair<L, R>(L left, R right) {}

    public static void main(String[] args) {
        Pair<String, Integer> item = new Pair<>("Java", 17);

        System.out.println(item.left());
        System.out.println(item.right());
        System.out.println(item);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericRecordDemo.java
java GenericRecordDemo
~~~

Stdout:

~~~text
Java
17
Pair[left=Java, right=17]
~~~

Generics increase expressiveness, but do not turn a generic record into a mutable container with hidden state. If `L` or `R` is a mutable object, the record field is still only a final reference.

## 34. Local Records and Nested Records

A record can be declared as a nested member type or a local type inside a method/block according to Java 17 rules.

A **nested record is implicitly static**; a **local record is also implicitly static**, and does not capture an enclosing instance or method locals like an ordinary local inner class:

~~~java
static int measure(int value) {
    record Data(int count) {}

    Data result = new Data(value);
    return result.count();
}
~~~

`value` is passed through the constructor, not automatically captured by the local record.

Similarly, a static nested record is a good candidate for an immutable result from a service class.

### When Do You Need an Inner Class with an Outer Instance?

If the type genuinely depends on the enclosing outer object/lifecycle and needs captured context, an ordinary inner/member/local class has different semantics and may be more appropriate than a record.

## 35. Runnable Program: Local Record Inside a Method

Create **`LocalRecordDemo.java`**:

~~~java
public class LocalRecordDemo {
    static String summarize(String name, int points) {
        record Score(String name, int points) {}

        Score score = new Score(name, points);
        return score.name() + "=" + score.points();
    }

    public static void main(String[] args) {
        System.out.println(summarize("Mai", 90));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LocalRecordDemo.java
java LocalRecordDemo
~~~

Stdout:

~~~text
Mai=90
~~~

A local record helps encapsulate a small data intermediary within a method, without forcing you to turn every tuple in a method into a local record.

## 36. Persistence Entities and ORM: Consider the Framework Contract

Many ORM/entity frameworks require characteristics such as:
- specific constructors (for example, an accessible no-arg constructor per the spec);
- managed identity;
- lazy-loading/proxy support;
- mutable persistent state or enhancement;
- field/property access conventions;
- entity lifecycle callbacks;
- inheritance/proxy mechanisms.

Because a record is implicitly final, has final components, and has a canonical constructor tied to its shape, **it is not automatically a suitable replacement for every persisted entity**.

Use an ordinary class for an entity when the framework contract/lifecycle genuinely requires it. A record can still be suitable as a:
- query projection;
- immutable DTO;
- API response;
- value snapshot;
- event payload;
- read model.

**Do not make a blanket claim that no ORM supports records**: capabilities for DTO projection, embedding, and mapping vary by framework/version/configuration. Check the documentation of the specific stack.

## 37. JSON, HTTP, and Data Transfer Boundaries

Records are often convenient as request/response DTOs because:
- component names are schema-like data attributes;
- there is little boilerplate;
- generated `toString/equals/hashCode` are useful in tests;
- canonical validation can guard minimal invariants.

However, JSON serialization/deserialization depends on the library:
- does it support record components?
- how does it accept constructor parameters?
- how does it follow field naming/annotations?
- how does it handle missing fields/null/defaults?
- does it invoke the canonical constructor and validations?
- are there backward-compatibility schema requirements?

Do not assume that merely using a record means the API boundary is validated. Bean validation annotations or framework-level checks may require explicit activation.

### DTO vs. Domain Object

A record DTO may hold raw parsed data; a domain value record has stricter invariants. Do not force a single type to take on too many responsibilities across conversion, validation, persistence, and business behavior.

## 38. Runnable Program: Entity Class Emitting a Record DTO

Create **`EntityDtoDemo.java`**:

~~~java
public class EntityDtoDemo {
    record AccountDto(long id, String owner, int cents) {}

    static final class Account {
        private final long id;
        private final String owner;
        private int cents;

        Account(long id, String owner, int cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("balance");
            }
            this.id = id;
            this.owner = java.util.Objects.requireNonNull(owner);
            this.cents = cents;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit");
            }
            cents = Math.addExact(cents, amount);
        }

        AccountDto snapshot() {
            return new AccountDto(id, owner, cents);
        }
    }

    public static void main(String[] args) {
        Account account = new Account(7, "Mai", 100);
        AccountDto before = account.snapshot();

        account.deposit(50);
        AccountDto after = account.snapshot();

        System.out.println("before=" + before.cents());
        System.out.println("after=" + after.cents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EntityDtoDemo.java
java EntityDtoDemo
~~~

Stdout:

~~~text
before=100
after=150
~~~

The class manages lifecycle and mutation; the record is an immutable-by-field snapshot for passing across boundaries. Not every type in an application needs to choose the same syntax.

## 39. JavaBean Naming and Interoperability

A record component accessor is named `name()`, not automatically `getName()`. A class with a JavaBeans-style API typically has `getName()` or `isActive()`.

An older framework or library that only introspects JavaBeans getters may not treat record accessors like property getters if it lacks record-aware support.

You can add appropriate custom methods to a record when needed, but do not turn a record into a mutable JavaBean lookalike with setters (component fields are final) just to force framework compatibility.

**Decision criterion:** If library integration relies primarily on a no-arg constructor and mutable setters, an ordinary class may present fewer obstacles. If the library supports Java records, a record DTO can be very natural.

## 40. Records and Serialization

A record **does not automatically implement Serializable**. To use Java serialization, you must declare the `Serializable` interface and examine the object graph.

Records have special Java serialization semantics (reconstruction through the canonical constructor according to the serialization model); validation in the canonical constructor is a notable reason to be careful with deserialized data.

However, you must also consider:
- serialized compatibility when changing record components;
- null and missing component policies;
- mutable component graphs;
- security of untrusted deserialization;
- versioning and migration.

Do not casually use Java native serialization for long-lived/public storage protocols. For application contracts requiring a stable schema, consider explicit data format/schema management.

## 41. Records and `toString`: Information Security

The generated `toString()` displays **component names and values**, which is very convenient for debugging:

~~~java
record Request(String user, String token) {}
~~~

However, if token is a secret, logging `request.toString()` can leak data.

Solutions:
- Do not place secrets directly in a type that is easily logged as a whole when unnecessary.
- Override `toString` so that it does not print sensitive components.
- Do not rely solely on toString; design a logging policy at the boundary.
- For mutable secret arrays, you must also address defensive copying and cleanup/lifecycle.

Both records and classes need privacy-aware logging. A class does not print all fields by default, yet if a developer auto-generates toString with an IDE, it can also leak secrets.

## 42. Runnable Program: Customizing `toString` to Hide Data

Create **`SafeToStringDemo.java`**:

~~~java
public class SafeToStringDemo {
    record Credentials(String user, String token) {
        Credentials {
            java.util.Objects.requireNonNull(user, "user");
            java.util.Objects.requireNonNull(token, "token");
        }

        @Override
        public String toString() {
            return "Credentials[user=" + user + ", token=<redacted>]";
        }
    }

    public static void main(String[] args) {
        Credentials credentials =
                new Credentials("mai", "secret-token");

        System.out.println(credentials);
        System.out.println("user=" + credentials.user());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SafeToStringDemo.java
java SafeToStringDemo
~~~

Stdout:

~~~text
Credentials[user=mai, token=<redacted>]
user=mai
~~~

The example only addresses logging from toString; the `token()` accessor still exposes the String token per the data-carrier API. If stronger protection is needed, design a different storage/ownership/lifecycle model, typically a dedicated class or secret wrapper.

## 43. Equality Defaults: Records and Classes Differ

**Record:**

~~~java
record Color(int r, int g, int b) {}
~~~

Two Color objects with the same component values have `equals` return true. Their corresponding hash codes must be equal.

**Class without overrides:**

~~~java
class ColorClass {
    int r, g, b;

    ColorClass(int r, int g, int b) {
        this.r = r;
        this.g = g;
        this.b = b;
    }
}
~~~

Two different `new ColorClass(1,2,3)` instances default to `equals` returning false because `Object.equals` uses reference equality.

You should not assume that all classes need to override equals. An entity/service identity object may intentionally use reference equality.

## 44. Runnable Program: Different Default Equality

Create **`EqualityChoiceDemo.java`**:

~~~java
public class EqualityChoiceDemo {
    record ColorRecord(int r, int g, int b) {}

    static final class ColorClass {
        final int r, g, b;

        ColorClass(int r, int g, int b) {
            this.r = r;
            this.g = g;
            this.b = b;
        }
    }

    public static void main(String[] args) {
        ColorRecord ra = new ColorRecord(1, 2, 3);
        ColorRecord rb = new ColorRecord(1, 2, 3);

        ColorClass ca = new ColorClass(1, 2, 3);
        ColorClass cb = new ColorClass(1, 2, 3);

        System.out.println("record equal=" + ra.equals(rb));
        System.out.println("class equal=" + ca.equals(cb));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EqualityChoiceDemo.java
java EqualityChoiceDemo
~~~

Stdout:

~~~text
record equal=true
class equal=false
~~~

If ColorClass is a value object, you must add equals/hashCode yourself. If the class represents a unique entity, reference identity can be a valid choice (depending on the domain).

## 45. Hash-Based Collections Require Stable Value Semantics

A record is a convenient Map key if its components:
- have immutable/hash-stable values;
- compare appropriately for the domain;
- do not expose mutable references that cause the hash to change.

For example, `record Key(String region, int number) {}` is usually suitable.

Conversely, `record Key(List<String> tags) {}` storing a mutable List directly can easily break HashMap lookups when the List changes. An ordinary immutable class would also suffer the same bug if equality/hash depended on mutable aliases.

**Protect the reference graph**: constructor copying, immutable elements, an accessor policy, and content equality if needed.

## 46. Runnable Program: Record as a HashMap Key

Create **`RecordHashMapDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RecordHashMapDemo {
    record Key(String region, int number) {}

    public static void main(String[] args) {
        Map<Key, String> lookup = new HashMap<>();
        lookup.put(new Key("VN", 1), "present");

        String found = lookup.get(new Key("VN", 1));
        System.out.println("found=" + found);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordHashMapDemo.java
java RecordHashMapDemo
~~~

Stdout:

~~~text
found=present
~~~

The generated equals/hashCode enables record lookup by value. When components are mutable, you must not rely on the assumption that the record automatically protects the key.

## 47. Encapsulation: “Getters” Are Not the Only Decision

A good class does not necessarily have getters for every field. For example:

~~~java
final class Account {
    private int cents;

    void deposit(int amount) {
        // validate and update invariant
    }

    boolean canPay(int amount) {
        return amount >= 0 && amount <= cents;
    }
}
~~~

A record `Account(int cents)` exposes `cents()` and equality based on cents. That can be a **different contract** from an object with identity and domain commands.

**Behavior-driven design:** When callers of an object need to issue commands like `pay`, `reserve`, or `close` instead of reading/writing arbitrary fields, a class is usually more natural.

### However, a Record Can Still Hide Secondary Details

A record can add derived methods and validate. It is not limited to an anemic DTO. What matters is that the components genuinely describe the logical state.

## 48. Lifecycle/Resource Objects Should Prefer a Class

A resource usually needs:
- `open`/`close` or `AutoCloseable`;
- changing open/closed state;
- ownership of handles, buffers, and sockets;
- cleanup when an exception occurs;
- concurrency coordination;
- idempotent shutdown.

Final record fields cannot easily express lifecycle state; there are no arbitrary instance fields, and `equals` based on handle data may be incorrect.

An ordinary class can implement AutoCloseable, hold a boolean closed field, private resource fields, and validate commands.

## 49. Runnable Program: Lifecycle Class Implementing `AutoCloseable`

Create **`CloseableClassDemo.java`**:

~~~java
public class CloseableClassDemo {
    static final class Session implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("using session");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("closed");
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.use();
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CloseableClassDemo.java
java CloseableClassDemo
~~~

Stdout:

~~~text
using session
closed
~~~

Session has a mutable `closed` state and a lifecycle; it is not a set of components needing value equality. This is a sound example of a class.

## 50. Concurrency and Thread Safety

Record component fields are final, but they can reference mutable objects. A record containing `List.copyOf` of Strings is usually easier to share than a record containing an uncopied mutable map, yet **the record keyword is not a guarantee of thread safety**.

An ordinary class can be immutable and thread-safe when designed properly; it can also be mutable, lock-protected, or atomic.

For example:
- `record Config(String host, int port)` is immutable-by-value → easy to publish.
- `record Config(Map<String,MutableValue> values)` → must check deep mutability.
- `class Counter` with AtomicInteger → can provide thread-safe increments.
- `class Session` with lock/lifecycle → designs synchronized ownership.

**Do not choose a record merely hoping to avoid data races automatically.**

## 51. Runnable Program: Mutable Class with an Atomic Operation

Create **`AtomicClassDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicClassDemo {
    static final class Counter {
        private final AtomicInteger value = new AtomicInteger();

        int incrementAndGet() {
            return value.incrementAndGet();
        }

        int current() {
            return value.get();
        }
    }

    record CounterSnapshot(int value) {}

    public static void main(String[] args) {
        Counter counter = new Counter();

        counter.incrementAndGet();
        counter.incrementAndGet();

        CounterSnapshot snapshot =
                new CounterSnapshot(counter.current());

        System.out.println("current=" + counter.current());
        System.out.println("snapshot=" + snapshot.value());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AtomicClassDemo.java
java AtomicClassDemo
~~~

Stdout:

~~~text
current=2
snapshot=2
~~~

The class owns the mutable atomic state; the record represents the snapshot. Counter and CounterSnapshot have different responsibilities.

## 52. Validation: Both Records and Classes Need Invariants

Record:

~~~java
record Port(int value) {
    Port {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("port");
        }
    }
}
~~~

Class:

~~~java
final class PortClass {
    private final int value;

    PortClass(int value) {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("port");
        }
        this.value = value;
    }

    int value() {
        return value;
    }
}
~~~

Both protect the range. The record is easier to read when a single component is the entire logical value.

### When Does a Class Make More Sense?

When the public representation **is not** a plain number, but rather a private efficient encoding, cache, derived states, or operations that should only expose meaningful behaviors.

## 53. Runnable Program: Record Distinguishing Parse Errors and Domain Errors

Create **`RecordPortDemo.java`**:

~~~java
public class RecordPortDemo {
    record Port(int value) {
        Port {
            if (value < 1 || value > 65535) {
                throw new IllegalArgumentException("port range");
            }
        }

        static Port parse(String text) {
            return new Port(Integer.parseInt(text.strip()));
        }
    }

    public static void main(String[] args) {
        System.out.println("port=" + Port.parse(" 8080 ").value());

        try {
            Port.parse("70000");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordPortDemo.java
java RecordPortDemo
~~~

Stdout:

~~~text
port=8080
invalid=port range
~~~

Factory parsing is a valid utility, yet the canonical constructor still protects the invariant so that `new Port(70000)` cannot slip through.

## 54. Should the Representation of “Sensitive” Data Use a Record?

It depends on the policy. A record automatically generates accessors for all components, and `toString()` normally displays component values. If it contains a password, token, secret key, or personal data, you must review:
- who can call the accessor;
- logging/toString;
- retention of Strings or arrays;
- whether equals/hashCode inadvertently compare secrets;
- whether clearing/rotation/revocation/lifecycle management is needed.

An ordinary class can expose **commands** such as `verify(candidate)` instead of exposing the raw secret. For secrets, use dedicated security abstractions and avoid assuming that either a record or a class automatically guarantees confidentiality.

A record DTO receiving secrets for a short duration is not necessarily wrong, but it must have a clear lifecycle/handling policy.

## 55. Adding a Component to a Record Can Change Equality

Initially:

~~~java
record Product(String code, int price) {}
~~~

Two `new Product("A",100)` objects are equal.

If upgraded to:

~~~java
record Product(String code, int price, String currency) {}
~~~

the generated equality considers currency as well. This is a change in **logical value semantics**, not merely adding a field cosmetically.

Consider:
- is currency part of the identity/value?
- is there a reasonable migration/default?
- how do existing callers construct it?
- is serialized/JSON data compatible?
- how did tests and cache keys assume equality previously?

If the public abstraction only needs `priceInCents()` and currency conversion behavior, a class can hide the representation better; however, compatibility planning is still needed.

## 56. Refactoring a Class to a Record: Technical Checklist

A class may be a candidate if:
1. it is final or does not need subclassing.
2. its instance state is completely described by final components.
3. it has no hidden mutable caches/resources/lock fields.
4. its public contract accepts exposing component accessors.
5. equality by component values is correct.
6. the constructor is formed from those component values.
7. validation/normalization can be placed in the canonical constructor.
8. the component graph is immutable or properly defensively copied.
9. framework integration supports records.
10. the API/versioning impact is acceptable.

### What Likely Needs to Change
- `getX()` → `x()` (if callers/frameworks care).
- Constructors/overloads.
- `equals/hashCode/toString` behavior.
- Reflection expectations.
- Serialization/deserialization binding.
- Visibility modifiers.
- Mutations/setters.
- Required superclass extension.

**Do not refactor automatically when behavior changes** without tests.

## 57. Runnable Program: Example of Refactoring a DTO Class to a Record

Create **`RefactorDtoDemo.java`**:

~~~java
import java.util.Objects;

public class RefactorDtoDemo {
    static final class OldDto {
        private final String name;
        private final int score;

        OldDto(String name, int score) {
            this.name = Objects.requireNonNull(name);
            this.score = score;
        }

        String getName() {
            return name;
        }

        int getScore() {
            return score;
        }
    }

    record NewDto(String name, int score) {
        NewDto {
            Objects.requireNonNull(name);
        }
    }

    public static void main(String[] args) {
        OldDto old = new OldDto("Mai", 90);
        NewDto newer = new NewDto("Mai", 90);

        System.out.println(old.getName() + "=" + old.getScore());
        System.out.println(newer.name() + "=" + newer.score());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RefactorDtoDemo.java
java RefactorDtoDemo
~~~

Stdout:

~~~text
Mai=90
Mai=90
~~~

The output may be equivalent, but getter calls are renamed and the equals/hashCode defaults change. Refactoring is only complete when the public contract and tests have been reviewed.

## 58. Refactoring a Record to a Class: When State Needs to Evolve

Suppose initially:

~~~java
record Download(int bytes) {}
~~~

Later, the system requires:
- status lifecycle `QUEUED/RUNNING/DONE`;
- cancel;
- progress updates;
- listener registration;
- resource cleanup;
- synchronization.

A new `DownloadSession` class with private state usually makes more sense than cramming all state into components, creating a new record on every event, and trying to use it as a resource owner.

You can keep a record:

~~~java
record DownloadProgress(int completed, int total) {}
~~~

as an immutable snapshot returned by `DownloadSession.progress()`. This is a sustainable division of roles.

## 59. Runnable Program: Stateful Class Returning a Progress Record

Create **`DownloadProgressDemo.java`**:

~~~java
public class DownloadProgressDemo {
    record Progress(int completed, int total) {
        Progress {
            if (total < 0 || completed < 0 ||
                    completed > total) {
                throw new IllegalArgumentException("progress");
            }
        }
    }

    static final class Download {
        private final int total;
        private int completed;

        Download(int total) {
            if (total < 0) {
                throw new IllegalArgumentException("total");
            }
            this.total = total;
        }

        void advance(int bytes) {
            if (bytes < 0 || bytes > total - completed) {
                throw new IllegalArgumentException("bytes");
            }
            completed += bytes;
        }

        Progress progress() {
            return new Progress(completed, total);
        }
    }

    public static void main(String[] args) {
        Download download = new Download(100);

        Progress before = download.progress();
        download.advance(25);
        Progress after = download.progress();

        System.out.println(before);
        System.out.println(after);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DownloadProgressDemo.java
java DownloadProgressDemo
~~~

Stdout:

~~~text
Progress[completed=0, total=100]
Progress[completed=25, total=100]
~~~

Download is a lifecycle-bearing class; Progress is a value snapshot. If multiple threads update/download concurrently, a synchronization policy beyond this demonstration is required.

## 60. Frameworks and Reflection: Record Metadata Is Explicit

Reflection provides:
- `Class.isRecord()` to identify a record type declaration.
- `Class.getRecordComponents()` to retrieve component descriptors.
- component names, types, and accessors according to the record metadata.

An ordinary class has fields/getters/constructors, but does not have the same record structural contract.

### When Reflection-Based Binding Is Needed

Record metadata can be useful for mappers and schema generation **if the library supports it properly**. However, the fact that reflection provides metadata does not mean an arbitrary framework has automatic record constructor binding. Verify in practice.

## 61. Runnable Program: Reflection for a Record and a Class

Create **`RecordReflectionDemo.java`**:

~~~java
public class RecordReflectionDemo {
    record Person(String name, int age) {}

    static final class PersonClass {
        private final String name;
        private final int age;

        PersonClass(String name, int age) {
            this.name = name;
            this.age = age;
        }
    }

    public static void main(String[] args) {
        System.out.println("record=" + Person.class.isRecord());
        System.out.println("class=" + PersonClass.class.isRecord());

        for (java.lang.reflect.RecordComponent component
                : Person.class.getRecordComponents()) {
            System.out.println(component.getName() + ":" +
                    component.getType().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordReflectionDemo.java
java RecordReflectionDemo
~~~

Stdout:

~~~text
record=true
class=false
name=String
age=int
~~~

Reflection confirms structural record components; `PersonClass` does not become a record even though it has the same logical fields.

## 62. Records Are Not Necessarily Faster or Smaller Than Classes

There is no Java specification guarantee that every record:
- occupies less heap memory than an equivalent class;
- is stack-allocated;
- is interned by the JVM;
- does not require garbage collection;
- has faster constructors;
- has faster equals than a custom class;
- is passed by value instead of by reference.

Records are still reference objects. JVM JIT/inlining/escape analysis can optimize many kinds of code, including ordinary classes.

**Choose based on correctness and API first; profile with JFR/JMH/benchmarks if performance is an actual concern.**

A record with List.copyOf or deep-copied arrays may cost more allocations than a mutable class that deliberately shares references — yet protecting state has value and must be compared against equivalent requirements, not just syntax.

## 63. Use Records for Event Payloads When Data Is Complete

An event payload is usually suitable if:
- it describes **an event that occurred** rather than a live service;
- its components are immutable values or immutable snapshots;
- no identity is needed except an event ID belonging to the data;
- publishing/consuming follows a clear contract;
- the event schema is versioned when it changes.

Example:

~~~java
record OrderPlaced(
        long orderId,
        java.time.Instant occurredAt,
        int totalCents) {}
~~~

`Instant` is immutable, and primitive values are easy to serialize/protect. A record is a natural candidate for a read-only data snapshot.

If there are a long-lived consumer offset, retry tracker, and connection lifecycle, those objects are usually classes/services separate from the event payload.

## 64. Runnable Program: Immutable Event Data and Consumer Interface

Create **`EventRecordDemo.java`**:

~~~java
import java.time.Instant;

public class EventRecordDemo {
    record OrderPlaced(
            long orderId,
            Instant occurredAt,
            int totalCents) {
        OrderPlaced {
            if (orderId <= 0 || totalCents < 0) {
                throw new IllegalArgumentException("event");
            }
            java.util.Objects.requireNonNull(
                    occurredAt, "occurredAt");
        }
    }

    interface EventConsumer {
        void accept(OrderPlaced event);
    }

    public static void main(String[] args) {
        OrderPlaced event = new OrderPlaced(
                7L, Instant.parse("2026-10-18T00:00:00Z"), 1250);

        EventConsumer consumer = value ->
                System.out.println(
                        value.orderId() + ":" + value.totalCents());

        consumer.accept(event);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EventRecordDemo.java
java EventRecordDemo
~~~

Stdout:

~~~text
7:1250
~~~

Event data does not contain an event processing queue, database transaction, or mutable connection handle. Those behaviors belong to separate services/classes.

## 65. The “Less Code” Criterion Should Come After Semantics

Mistake:

> “If a class has three private final fields, convert them all to records.”

Proper analysis:

- Are those fields the entirety of the logical state meant to be exposed?
- Is equality based on all fields?
- Are there hidden representations/caches?
- Are the constructor parameters documented as stable?
- Do frameworks/serialization require JavaBeans semantics?
- Do security/logging policies allow toString to contain every component?
- Is the object's lifetime a snapshot or an entity?
- Is subclassing or private mutable state needed?
- Will changing a component break the API?

A record that is longer than a class can still be right, and a class that is longer than a record can still be worthwhile.

## 66. Selection Table by Example

| Use case | Recommendation | Reason |
| --- | --- | --- |
| `Point(x,y)` | Record | Components describe the value |
| `DateRange(start,end)` | Record | Cross-field invariant, immutable java.time |
| `CurrencyAmount(currency,amount)` | Record or immutable class | Value; consider normalization/representation |
| `HTTP response DTO` | Record if mapper supports it | Transparent data transport |
| `SearchResult(title,url)` | Record | Snapshot data |
| `Customer entity` | Class | Identity, rename/lifecycle |
| `BankAccount` | Class | Transactions and state mutations |
| `Session`/`Connection` | Class | Resource ownership/close |
| `DownloadProgress` | Record | Snapshot |
| `DownloadSession` | Class | Long-lived state and commands |
| `PolicyConfig` | Record with immutable components | Stable input values |
| `PolicyEngine` | Class/service | Behavior and dependencies |
| `Secret credential holder` | Consider a class | Access/lifecycle/logging |
| `ByteBlob(byte[])` | Depends on contract | Defensive copy + equality; a class can hide representation |
| `Value object extensible via superclass` | Class | Records cannot extend a class |
| `Sealed Result variants` | Records | Data variants of a sealed interface |
| `Plugin implementation` | Class | Constructor/DI/lifecycle |
| `JPA-style managed entity` | Usually a class | ORM requirements |
| `Read-only query projection` | Record if supported | Read data |
| `Mutable cache` | Class | Hidden mutable state |

## 67. Decision Flow in the Right Order

~~~text
Define a new type
    |
    +-- Does the type represent an entity/resource with identity/lifecycle?
    |       |
    |       +-- Yes --> Ordinary class.
    |
    +-- Does it need to extend an arbitrary superclass?
    |       |
    |       +-- Yes --> Ordinary class.
    |
    +-- Does it need hidden mutable instance fields/cache/lock?
    |       |
    |       +-- Yes --> Ordinary class.
    |
    +-- Is the logical state fully described by public components?
    |       |
    |       +-- No --> Ordinary class or another abstraction.
    |
    +-- Is component-based equality appropriate?
    |       |
    |       +-- No --> Class or custom semantics with a clear reason.
    |
    +-- Can mutable components be reasonably protected/snapshotted?
    |       |
    |       +-- No --> Class/another representation.
    |
    +-- Does framework/API compatibility allow it?
            |
            +-- No --> Class or adapter DTO.
            |
            +-- Yes --> A record is usually an appropriate choice.
~~~

This is not a heuristic without exceptions. For example, a record can customize equals/hashCode or use an array with clone, but that is a **signal to review value semantics more carefully**, not proof that using a record is wrong.

## 68. Common Anti-Patterns

| Anti-pattern | Problem | Approach |
| --- | --- | --- |
| Turning every DTO into a record unconditionally | Mapper/API compatibility may differ | Verify the integration contract |
| Using a record as a mutable entity | Final fields, unsuitable identity/equality | Class entity + record snapshot |
| Using `record User(id,name)` and assuming equals only checks id | Generated equals uses all components | Choose a class/design semantics |
| Assuming records are deeply immutable | Mutable reference components still change | Copy/immutable elements |
| Putting an `ArrayList` directly into a record | Aliasing, changing hash | List.copyOf and validation |
| Getter returning an internal array | External mutation | Defensive copy |
| Cloning an array without checking equals | Identity vs content equality | Arrays.equals/hashCode or a class |
| Using a record to hold secrets and logging the object | toString leaks component values | Logging/data policy |
| Using a class just because a few methods are needed | Records also have instance methods | Consider logical state |
| Trying to make a record extend BaseClass | Invalid | Interface/composition/class |
| Choosing a mutable class for every value | Boilerplate and state bugs | Record/immutable class |
| Choosing based on imaginary benchmarks | No performance guarantee | Measure in practice |
| Renaming a component without considering clients | API break | Versioning/migration strategy |
| Using a record with an unsupported framework | Deserialization/proxy failures | Check version/contract |
| Assuming `@NotNull` automatically validates every `new` | Annotations do not run by themselves | Constructor/framework validation |
| Making business logic depend on generated toString | Not a durable serialization schema | Explicit formatting/schema |
| Class with public setters for a value object | Invariants are easily broken | Immutable class/record |
| Failing to check concurrency of captured data | Thread safety does not come automatically | Synchronization/ownership |

## 69. Exercise 1 — Coordinate Point

A type holds only `x` and `y` integers, has no separate identity, uses equality based on both, and has a `distanceSquared` method.

**Answer:** A record is very suitable. A method computing a derived value can be placed inside the record. Use `long` or overflow-checked computation for large values if the domain requires it.

## 70. Exercise 2 — Bank Account

An account has an immutable ID, a changing balance, deposit/withdraw commands, and a transaction history. Two accounts with the same balance are not the same entity.

**Answer:** An ordinary class entity is clearer. A record can represent an `AccountSnapshot(id,balance)` or an immutable transaction event.

## 71. Exercise 3 — Record Containing a List

~~~java
record Report(java.util.List<String> tags) {}
~~~

The caller passes an ArrayList and then mutates the source. Does Report change?

**Answer:** Possibly yes, because a record retains the reference by default. Add a compact constructor `tags = List.copyOf(tags);` if an unmodifiable structural snapshot is needed, and then consider mutable elements.

## 72. Exercise 4 — Record Containing an Array

~~~java
record Data(byte[] values) {}
~~~

What are three notable risks?

**Answer:** Mutation via the input alias; mutation via the default accessor; generated equals/hashCode not being element-wise over array content. Copy input/output and define domain-appropriate equality if needed.

## 73. Exercise 5 — Adding a Hidden Cache

A value object wants to add a private mutable per-instance lazy cache that is not in the component list.

**Answer:** A record does not allow adding arbitrary instance fields. Use an ordinary class, an external cache, or uncached computation; consider concurrency if state is mutable.

## 74. Exercise 6 — Inheritance

A type must `extends AbstractService`, which already has logic/fields, and implement `Runnable`.

**Answer:** An ordinary class, because a record cannot extend a custom superclass. A record only implicitly extends java.lang.Record and can implement interfaces.

## 75. Exercise 7 — Equality

Two `new PersonRecord("Mai",20)` instances have the same components; two `new PersonClass("Mai",20)` instances where the class does not override equals.

**Answer:** The two records have equals return true; the two classes use Object.equals, so it returns false if they are two distinct references. Custom equals/hashCode are needed for the class to have value semantics.

## 76. Exercise 8 — API Changes

A public record `Point(x,y)` needs to add a `unit` component. What are the risks?

**Answer:** The canonical constructor, accessors, equals/hashCode/toString shape, and serialization/mapping schema can change. Versioning/migration/overloads must be checked; do not treat it like merely adding a private field.

## 77. Exercise 9 — Immutable Class vs. Record

An ordinary final class has private final fields, defensive copies, and custom equals. Can it be as immutable as a record?

**Answer:** Yes, and it can even encapsulate its representation more thoroughly. A record is a choice of syntax/structural contract, not a monopoly on immutability.

## 78. Exercise 10 — Sealed Interface Result

There is `sealed interface Result permits Success, Failure`; Success only carries data, and Failure only carries an error message.

**Answer:** Two final records implementing Result are usually appropriate in Java 17. If one variant manages a resource lifecycle, an ordinary class can also be a permitted implementation according to the rules.

## 79. Exercise 11 — Framework Projection

An SQL query returns read-only columns and the library mapper supports constructor mapping for records, with no managed entity needed.

**Answer:** A record DTO/projection can be good. If it must be a managed JPA-style entity per specific requirements, a class is usually more suitable; check the framework documentation.

## 80. Exercise 12 — Choosing Based on Performance?

Someone says “a record is always cheaper than a class and the JVM puts it on the stack”.

**Answer:** There is no such language guarantee. Records are reference objects; JIT optimization depends on the runtime/workload. Choose based on semantics and benchmark when needed.

## 81. Exercise 13 — Resource with `close()`

A file writer needs to close the file, track the closed state, and prevent writing after close.

**Answer:** An ordinary class implementing AutoCloseable is more suitable, because it needs lifecycle/hidden mutable state; a record can be used for immutable write request parameters.

## 82. Exercise 14 — Cannot Use a Record If It Has Logic?

A `record Rectangle(width,height)` has `area()` and `isSquare()`.

**Answer:** Completely valid. Methods derived from components do not break the value-carrier design.

## 83. Exercise 15 — Data Privacy

A record contains `password` in a component and gets logged via `toString()`. What is the issue?

**Answer:** The generated toString can expose the component value. Redesign the security boundary/logging; overriding toString is only one layer of defense and does not guarantee full secret ownership.

## 84. Exercise 16 — Record or Class for Configuration Information?

A configuration consists of `host` and `port`, does not change after creation, and needs validation and equality based on the two components.

**Answer:** A record is suitable, with a canonical constructor checking for a nonblank host/port range. If the config holds live mutable connections/caches, separate `ConnectionManager` into a class.

## 85. Exercise 17 — Domain Snapshot vs. Same Entity

A `Customer` class changes its name from "Mai" to "Mai Anh". Are the two snapshots before and after equal?

**Answer:** No if the record snapshot has components `(id,name)`; generated equals compares name as well. However, both can point to the same domain entity ID, so snapshot value identity differs from entity identity.

## 86. Exercise 18 — Does Converting From Class to Record Preserve Behavior?

Class `Person` has the default Object.equals and getters `getName()`. Convert directly to `record Person(String name)`.

**Answer:** It does not automatically preserve the contract: equality changes to component value, getter name changes, and constructor/API/serialization may differ. A compatibility strategy and tests are needed.

## 87. Architecture Review Process

Before choosing, answer each in turn:

1. **Is this a value or an entity?** Write one sentence describing identity/equality.
2. **What does the state consist of?** Do the components fully represent the logical state?
3. **Is mutation valid?** If so, mutate the object itself or create a new value?
4. **Is there hidden state?** Cache, lock, connection, audit fields, lifecycle?
5. **Is inheritance needed?** Extend a class or only implement interfaces?
6. **What is the public API?** Is exposing record components truly what you want?
7. **Are there mutable references?** Defensive copies, nested objects, arrays?
8. **Are equality/hash stable?** Will Map/Set keys use it?
9. **Security/logging?** Do accessors/toString leak data?
10. **Framework mapping?** No-arg constructor, getters, reflection, proxies?
11. **Versioning?** How does adding a component affect clients/schema?
12. **Concurrency?** Is there shared state or atomic operations?
13. **Performance?** Profile only after the requirements are right.
14. **Tests?** Compare behavior, equality, mutation, invariants, and compatibility.

**Decision outcome:** If it is a transparent, stable bundle of values whose components match the logical state, choose a record. If the object manages identity/lifecycle/representation or needs extensibility/complex state, choose a class.

## 88. End-of-Lesson Checklist

- [ ] I know that both records and classes are Java reference types.
- [ ] I understand that a record auto-generates accessors/canonical constructor/equals/hashCode/toString.
- [ ] I do not confuse a record's final fields with deep immutability.
- [ ] I know that a record is implicitly final and extends java.lang.Record.
- [ ] I know that a record cannot extend a custom superclass.
- [ ] I know that a record can still implement interfaces.
- [ ] I know that a record can have methods and static members.
- [ ] I know that a record cannot have arbitrary instance fields or an instance initializer.
- [ ] I understand compact/canonical constructors and validation.
- [ ] I know that an immutable class can have value equality like a record.
- [ ] I know that a class's default Object.equals is reference-based.
- [ ] I separate snapshot values from entity identity.
- [ ] I consider a Record DTO for immutable data transfer.
- [ ] I use a class when there are mutable domain commands.
- [ ] I use a class for resource/lifecycle/AutoCloseable owners.
- [ ] I do not automatically use records to replace every ORM entity.
- [ ] I check mapper/framework record support.
- [ ] I understand that the record component accessor `name()` differs from `getName()`.
- [ ] I understand that component changes affect constructor/API/equality.
- [ ] I know that List.copyOf is only a structural snapshot and does not deep-copy elements.
- [ ] I know that arrays need defensive copying and revisiting equals/hashCode.
- [ ] I do not use mutable value objects as unstable HashMap keys.
- [ ] I know that a record's `toString` can expose sensitive components.
- [ ] I know that records are reference objects, not guaranteed to be stack-only.
- [ ] I do not assume that a record is always faster than a class.
- [ ] I consider sealed interface + record variants in Java 17.
- [ ] I distinguish an implicitly static local record from an ordinary local class.
- [ ] I evaluate Java serialization and external schemas separately.
- [ ] I test type behavior rather than just line count.
- [ ] I have a decision flow before refactoring class ↔ record.
- [ ] I choose based on semantics, API stability, and lifecycle.

**Conclusion:** Choose **`record` when the public components truly are the entire logical value of the object**, component-based equality is right, and complex mutation/lifecycle is not in the contract. Choose **ordinary class when you need identity, state transitions, hidden representation, constructors/APIs not directly dependent on components, inheritance, caches, or resources**. You do not have to choose one for the entire program: Java 17 architecture is often strongest when **classes manage behavior and lifecycles, records carry immutable snapshots/value data, and interfaces define shared contracts**. Shorter code is a secondary benefit, not the deciding criterion.
