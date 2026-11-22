# Controlling Inheritance to Protect Immutability Commitments in Java

An **immutable object** is an object whose observable state does not change after it is successfully constructed, according to a clear contract. In Java, declaring a `private final` field is an important factor, **but not sufficient** to guarantee that every object of a type — especially **subclasses** — is always immutable.

For example:

~~~java
class Value {
    private final int amount;

    Value(int amount) {
        this.amount = amount;
    }

    public int amount() {
        return amount;
    }
}
~~~

`Value` stores `amount` in a final field. However, because the class is **not final**, a subclass can add mutable state or override `amount()` so that the result changes over time. Therefore, you cannot conclude with certainty that “every object viewed through type Value is immutable” merely from seeing a final field in the parent class.

To **protect the immutability commitment across inheritance boundaries**, you need to choose a strategy: **forbid inheritance** using a `final class`; or **tightly control the entire hierarchy** using sealed types, protected/final APIs, constructors, and checking each subtype; or **prefer composition** over subclassing when you want to extend behavior.

This article belongs to **Java Core — Class & Object / Immutable Classes**, using **Java 17+**. Complete programs include the filename, `javac`/`java` commands, and stdout for self-verification. Incomplete illustrative code is explicitly noted.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between an **immutable object**, an **immutable class**, an **immutability contract**, and an **immutable view**.
2. Explain how a `final field` differs from a `final class` and a `final method`.
3. Point out why **allowing arbitrary inheritance** weakens the promise that “every instance of this type is immutable”.
4. Write an immutable class that cannot be subclassed using `public final class`.
5. Recognize that a `final class` still requires validation, defensive copying, and avoiding exposing mutable state.
6. Detect how a subclass can override a getter to make observable behavior change.
7. Understand that adding mutable fields to a subclass remains valid if the superclass is not final.
8. Distinguish a superclass's immutable state from **the immutability of the entire object**.
9. Use a `final method` to lock down critical behavior, and understand its limitations.
10. Identify the risk of **calling an overridable method in a constructor**.
11. Understand why `this` must not be published before the object is fully constructed.
12. Distinguish between a **defensive copy**, an **unmodifiable live view**, a **shallow snapshot**, and **deep immutability**.
13. Use appropriate immutable element/value types in collections.
14. Understand the roles of `record`, `sealed class/interface`, and subclass permissions in Java 17.
15. Recognize that a sealed hierarchy **does not automatically make every permitted subtype immutable**.
16. Prefer composition, interfaces, and immutable snapshots when behavioral diversity is needed.
17. Design constructors/factories that do not break their own invariants.
18. Understand the risks of inheritance for `equals`, `hashCode`, and stable value semantics.
19. Evaluate the safety of using objects across threads.
20. Write tests proving that behavior and state remain stable after external mutation attempts.

## 2. “Immutability” Is a Behavioral Commitment, Not Just a Modifier

An immutable type should have a contract similar to:

> After the constructor/factory returns successfully, the observable logical state of this object is not modified by operations provided by the API or by aliases to mutable state that it holds.

Properties typically required:

- No methods that modify the constructed state.
- Core fields are fully initialized in the constructor, usually `private final`.
- Do not directly publish references to mutable internal state.
- Incoming mutable data is **copied or converted into an immutable representation**.
- If nested objects are held, the nested state is also controlled according to the contract.
- Subclasses are prevented from breaking the contract via extra mutable state, method overrides, or constructor hooks.
- The object is fully constructed before being shared with other code, without letting `this` escape.

“Immutability” can be **deep immutability** (the entire object graph observed by the API is also stable) or **shallow immutability** (reference fields are not reassigned, but target objects remain mutable). You must state the level clearly rather than using `final` as the sole proof.

### An Easy-to-Get-Wrong Example

~~~java
final class BadContainer {
    private final java.util.List<String> items;

    BadContainer(java.util.List<String> items) {
        this.items = items;
    }

    java.util.List<String> items() {
        return items;
    }
}
~~~

The `final` class forbids subclasses, but a caller holding `items` can call `add/remove` and the getter returns the same mutable List. **A final class is still not enough**.

## 3. Three Kinds of `final` to Distinguish

| Syntax | Direct Guarantee | Does Not Guarantee by Itself |
| --- | --- | --- |
| `private final int count` | Field is assigned according to the rules and then not reassigned | That inherited/overridden methods are stable |
| `private final List<T> values` | Reference field is not reassigned | That the List or its elements are immutable |
| `public final class Money` | No subclass of Money can exist | That fields/reference graph are not mutated |
| `public final int amount()` | Subclass cannot override the method | That a subclass has no other mutable fields/methods |
| `final localVariable` | Local variable is not reassigned | That the object referenced by the local variable becomes immutable |

**Final on a class** and **final on a field** serve two dimensions of the contract:

1. `final class` closes **extensibility via inheritance**.
2. `final fields` restrict **changing the stored references/values**.
3. Defensive copying and API design protect **the state behind references**.

A robust immutable design typically uses multiple elements together.

## 4. Why Can a Subclass Make the Contract “Every Value Is Immutable” False?

Parent class:

~~~java
class BaseValue {
    private final int amount;

    BaseValue(int amount) {
        this.amount = amount;
    }

    public int amount() {
        return amount;
    }
}
~~~

A subclass can do two things:

- Add a mutable field, causing **the entire object** to contain changeable state.
- Override `amount()`, causing the behavior that the caller observes through the BaseValue type to change.

~~~java
class MutableValue extends BaseValue {
    private int current;

    MutableValue(int original) {
        super(original);
        current = original;
    }

    public void change(int next) {
        current = next;
    }

    @Override
    public int amount() {
        return current;
    }
}
~~~

Even though `BaseValue.amount` is private final, the `amount()` method is not final, so a subclass is allowed to override it. A caller sees `BaseValue reference = new MutableValue(5)` and observes the amount change from 5 to 9.

### Runnable Program: Breaking the Commitment via Override

Create **`MutableSubclassDemo.java`**:

~~~java
public class MutableSubclassDemo {
    static class BaseValue {
        private final int original;

        BaseValue(int original) {
            this.original = original;
        }

        public int amount() {
            return original;
        }
    }

    static final class MutableValue extends BaseValue {
        private int current;

        MutableValue(int original) {
            super(original);
            current = original;
        }

        void change(int next) {
            current = next;
        }

        @Override
        public int amount() {
            return current;
        }
    }

    public static void main(String[] args) {
        MutableValue concrete = new MutableValue(5);
        BaseValue abstractView = concrete;

        System.out.println("before=" + abstractView.amount());
        concrete.change(9);
        System.out.println("after=" + abstractView.amount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableSubclassDemo.java
java MutableSubclassDemo
~~~

Stdout:

~~~text
before=5
after=9
~~~

**Meaning:** The superclass only protects the private final field `original`; it does not protect the contract that the result of `amount()` for **all subclasses** is always stable.

## 5. A Mutable Subclass Might Not Override Any Method

For example:

~~~java
class ImmutableCore {
    private final int core;

    ImmutableCore(int core) {
        this.core = core;
    }

    public final int core() {
        return core;
    }
}

class MutableExtension extends ImmutableCore {
    private int counter;

    MutableExtension(int core) {
        super(core);
    }

    void increment() {
        counter++;
    }

    int counter() {
        return counter;
    }
}
~~~

`ImmutableCore.core()` is always stable in every subclass thanks to the `final` method and private final field. However, a `MutableExtension` object is **not wholly immutable** because `counter` changes.

### Two Very Different Statements

- **True in the example:** “The value of `core()` belonging to ImmutableCore's API does not change through normal operations.”
- **False:** “Any object that extends ImmutableCore is immutable.”

If the superclass documentation only commits that **its own state** does not change, the hierarchy can still be reasonable. However, if the public contract declares that **every instance of this type is a completely immutable value object**, you must control its subclasses.

## 6. The Simplest Approach: `final class`

For a value object that does not need subclassing:

~~~java
public final class Money {
    private final long cents;

    public Money(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative money");
        }
        this.cents = cents;
    }

    public long cents() {
        return cents;
    }

    public Money plus(Money other) {
        java.util.Objects.requireNonNull(other, "other");
        return new Money(Math.addExact(cents, other.cents));
    }
}
~~~

`final class` means normal Java code cannot declare `class SpecialMoney extends Money`. This **closes off the path for subclasses to add mutable fields or override methods**.

For an immutable value object, operations like `plus` create **a new object**, without modifying the state of the receiver.

### Complete Runnable Example

Create **`FinalMoneyDemo.java`**:

~~~java
import java.util.Objects;

public class FinalMoneyDemo {
    static final class Money {
        private final long cents;

        Money(long cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            this.cents = cents;
        }

        long cents() {
            return cents;
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            return new Money(Math.addExact(cents, other.cents));
        }
    }

    public static void main(String[] args) {
        Money first = new Money(125);
        Money second = new Money(75);
        Money total = first.plus(second);

        System.out.println("first=" + first.cents());
        System.out.println("second=" + second.cents());
        System.out.println("total=" + total.cents());
        System.out.println("same object=" + (first == total));

        try {
            new Money(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalMoneyDemo.java
java FinalMoneyDemo
~~~

Stdout:

~~~text
first=125
second=75
total=200
same object=false
rejected=negative amount
~~~

`Money` cannot be subclassed; the cents state is private final, constructor validation rejects negative values, and plus returns a new Money. `Math.addExact` detects overflow instead of silently wrapping numbers.

**Limitation:** The example only models a hypothetical “cents” unit and carries no currency. Real financial software must represent currencies, scale, rounding, and appropriate domain rules. Immutability does not by itself equate to a complete business model.

## 7. A `final class` Does Not Freeze Mutable Fields

Even when a class is locked against inheritance, the following code is not safe:

~~~java
final class CalendarState {
    private final java.util.Date date;

    CalendarState(java.util.Date date) {
        this.date = date;
    }

    java.util.Date date() {
        return date;
    }
}
~~~

`Date` is mutable. The caller can modify the passed-in object after the constructor runs, or call the getter to obtain the same Date reference and modify it. `final` only freezes the **reference field**, not the referenced object.

### Defensive Copying on Both Sides

~~~java
final class CalendarState {
    private final java.util.Date date;

    CalendarState(java.util.Date supplied) {
        java.util.Objects.requireNonNull(supplied);
        this.date = new java.util.Date(supplied.getTime());
    }

    java.util.Date date() {
        return new java.util.Date(date.getTime());
    }
}
~~~

Copying on **input** prevents modification through an alias already held by the caller. Copying on **output** prevents direct modification of internal state via the getter.

In modern Java APIs, `java.time.Instant`, `LocalDate`, or other immutable time types are usually easier to manage than mutable `Date`, when suitable for the problem. Use value types with clear contracts to reduce the need for defensive copying.

## 8. Runnable Example: Defensive Copying of an Array in a Final Class

Create **`SafeBytesDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class SafeBytesDemo {
    static final class SafeBytes {
        private final byte[] data;

        SafeBytes(byte[] source) {
            Objects.requireNonNull(source, "source");
            this.data = source.clone();
        }

        byte[] toArray() {
            return data.clone();
        }

        int size() {
            return data.length;
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        SafeBytes bytes = new SafeBytes(source);

        source[0] = 9;
        byte[] copy = bytes.toArray();
        copy[1] = 8;

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("copy=" + Arrays.toString(copy));
        System.out.println("stored=" +
                Arrays.toString(bytes.toArray()));
        System.out.println("size=" + bytes.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeBytesDemo.java
java SafeBytesDemo
~~~

Stdout:

~~~text
source=[9, 2, 3]
copy=[1, 8, 3]
stored=[1, 2, 3]
size=3
~~~

The array is cloned on both input and output, so holders of external references cannot change the internal bytes by mutating source or the returned copy. `SafeBytes` is final and provides no mutator, creating a clear immutability contract.

For an array of mutable **reference elements**, `clone()` only shallow-copies the array structure; you must check whether each element is immutable or whether a deep defensive representation is needed.

## 9. `private` and `final` Must Go Together with API Control

Three principles:

1. **`private`** restricts callers/subclasses from directly modifying fields through normal source-level access.
2. **`final`** prevents a field from being reassigned after initialization according to Java rules.
3. **The API does not return mutable internals** and does not allow methods to alter logical state.

Incorrect example:

~~~java
public final class UnsafeRoster {
    private final java.util.List<String> names;

    public UnsafeRoster(java.util.List<String> names) {
        this.names = names;
    }

    public java.util.List<String> names() {
        return names;
    }
}
~~~

The `names` reference is final and the class is final, yet the underlying List is mutable and exposed.

### Using an Immutable Snapshot

~~~java
public final class Roster {
    private final java.util.List<String> names;

    public Roster(java.util.List<String> names) {
        this.names = java.util.List.copyOf(names);
    }

    public java.util.List<String> names() {
        return names;
    }
}
~~~

`List.copyOf` protects the collection structure and rejects null elements; String is immutable, so the elements in this example are suitable value objects. If elements are mutable, copying only the structure is not enough to guarantee deep immutability.

## 10. Runnable Example: `List.copyOf` Prevents Mutation via Aliases

Create **`ImmutableRosterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableRosterDemo {
    static final class Roster {
        private final List<String> names;

        Roster(List<String> source) {
            names = List.copyOf(source);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Roster roster = new Roster(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("roster=" + roster.names());

        try {
            roster.names().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot mutate roster list");
        }

        System.out.println("roster again=" + roster.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableRosterDemo.java
java ImmutableRosterDemo
~~~

Stdout:

~~~text
input=[Mai, An]
roster=[Mai]
cannot mutate roster list
roster again=[Mai]
~~~

The input List changes after the constructor runs, but the snapshot inside Roster does not change. The getter returns an unmodifiable List. Because the element type is String, there is no way to alter the state of any individual name.

**Note:** `Collections.unmodifiableList(source)` typically creates an unmodifiable **view** over the source List: you cannot add through the view, but if the source is modified, the view still reflects the changes. `List.copyOf(source)` creates a snapshot structure decoupled from the mutable source (per its contract). The two mechanisms are different.

## 11. Shallow Immutability: Mutable Elements Can Still Change

Suppose you hold a `List<Member>`, where Member has a `rename` method:

~~~java
final class Group {
    private final java.util.List<Member> members;

    Group(java.util.List<Member> members) {
        this.members = java.util.List.copyOf(members);
    }

    java.util.List<Member> members() {
        return members;
    }
}
~~~

The List cannot have elements added or removed, but the caller can modify the provided Member object. `List.copyOf` does not clone Members.

### Runnable Program Demonstrating the Flaw

Create **`ShallowImmutableDemo.java`**:

~~~java
import java.util.List;

public class ShallowImmutableDemo {
    static final class Member {
        private String name;

        Member(String name) {
            this.name = name;
        }

        void rename(String next) {
            name = next;
        }

        String name() {
            return name;
        }
    }

    static final class Group {
        private final List<Member> members;

        Group(List<Member> source) {
            members = List.copyOf(source);
        }

        String firstName() {
            return members.get(0).name();
        }
    }

    public static void main(String[] args) {
        Member member = new Member("Mai");
        Group group = new Group(List.of(member));

        System.out.println("before=" + group.firstName());
        member.rename("An");
        System.out.println("after=" + group.firstName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowImmutableDemo.java
java ShallowImmutableDemo
~~~

Stdout:

~~~text
before=Mai
after=An
~~~

The Group class is final, the members field is final, and List.copyOf is unmodifiable, yet the **observable state** through `firstName()` changes. This is why talking about “protecting the immutability commitment” must consider the **object graph**, not just field modifiers or forbidding subclassing.

## 12. Converting Mutable Elements into Immutable Snapshots

Solution: convert mutable data into an immutable value type when constructing the object.

~~~java
record MemberSnapshot(String name) {
    MemberSnapshot {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
    }
}
~~~

Instead of storing mutable `Member` instances, Group stores a `List<MemberSnapshot>` created from the state of the Members at constructor time.

### Runnable Example

Create **`DeepSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DeepSnapshotDemo {
    static final class MutableMember {
        private String name;

        MutableMember(String name) {
            this.name = name;
        }

        void rename(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    record MemberSnapshot(String name) {}

    static final class Group {
        private final List<MemberSnapshot> members;

        Group(List<MutableMember> source) {
            List<MemberSnapshot> snapshots = new ArrayList<>();
            for (MutableMember member : source) {
                snapshots.add(new MemberSnapshot(member.name()));
            }
            members = List.copyOf(snapshots);
        }

        String firstName() {
            return members.get(0).name();
        }
    }

    public static void main(String[] args) {
        MutableMember member = new MutableMember("Mai");
        Group group = new Group(List.of(member));

        System.out.println("before=" + group.firstName());
        member.rename("An");
        System.out.println("after=" + group.firstName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DeepSnapshotDemo.java
java DeepSnapshotDemo
~~~

Stdout:

~~~text
before=Mai
after=Mai
~~~

Group stores **a snapshot of the String values** from the source. Modifying the original mutable Member does not affect the snapshot. For complex or cyclic object graphs, a “deep copy” requires deliberate design; here, the example converts to a small **immutable representation** without pretending that all objects can be cloned automatically.

## 13. Inheritance Widens Paths for State Mutation

When a class is not final, the superclass author does not control all the state that subclasses can declare:

~~~java
class StableBase {
    private final int base;

    StableBase(int base) {
        this.base = base;
    }

    public final int base() {
        return base;
    }
}
~~~

A subclass is permitted:

~~~java
class MutableChild extends StableBase {
    private int revision;

    MutableChild(int base) {
        super(base);
    }

    void advance() {
        revision++;
    }

    int revision() {
        return revision;
    }
}
~~~

The superclass cannot prohibit all new state in arbitrary subclasses merely by making its own fields private final. `final int base()` still ensures that the base method cannot be overridden, but **does not guarantee that a MutableChild object is wholly immutable**.

### The Contract Must State the Level Clearly

If the library wants “**`StableBase.base()` is always stable**”, this design may be reasonable.

If the library wants “**every `StableBase` object is an immutable value object**”, a design that allows arbitrary subclassing does not prove that promise.

You should choose a **final class** for a concrete immutable value object unless there is a clear reason to support a hierarchy.

## 14. `final method` Helps Protect Invariants but Does Not Close the Hierarchy

Suppose:

~~~java
class AccountView {
    private final String id;

    AccountView(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public final String id() {
        return id;
    }
}
~~~

Subclasses cannot override `id()`, so every call to that method executes the body of AccountView. However, a subclass can still add mutable state:

~~~java
class RichAccountView extends AccountView {
    private int refreshCount;

    RichAccountView(String id) {
        super(id);
    }

    void refresh() {
        refreshCount++;
    }
}
~~~

**Exact conclusion:** A final method protects **a single observation/behavior path**. It does not make every subclass immutable.

### When Should You Still Use Final Methods?

- To protect a method that checks an internal invariant of the base class.
- To prevent subclasses from altering the security or consistency semantics of an operation.
- When a framework intentionally provides extension hooks while **locking down critical operations**.

However, you need to check whether other methods call overridable hooks; if they do, the overall behavior may still depend on a mutable subclass.

## 15. Method Overriding Can Make a “Getter” Unstable

A subclass can override a method that callers assume only reads a private final field of the superclass.

Create **`FinalMethodBoundaryDemo.java`**:

~~~java
public class FinalMethodBoundaryDemo {
    static class Base {
        private final int id;

        Base(int id) {
            this.id = id;
        }

        public final int id() {
            return id;
        }

        public String label() {
            return "base";
        }
    }

    static final class Child extends Base {
        private String label = "first";

        Child(int id) {
            super(id);
        }

        void changeLabel(String next) {
            label = next;
        }

        @Override
        public String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Child child = new Child(7);
        Base view = child;

        System.out.println("id=" + view.id());
        System.out.println("label before=" + view.label());
        child.changeLabel("second");
        System.out.println("id again=" + view.id());
        System.out.println("label after=" + view.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalMethodBoundaryDemo.java
java FinalMethodBoundaryDemo
~~~

Stdout:

~~~text
id=7
label before=first
id again=7
label after=second
~~~

A contract that “`id()` does not change” is protected. A contract that “every observable method on a Base view is immutable” is **not** guaranteed because `label()` is overridable.

If a public class describes itself as completely immutable, users can draw false conclusions when a method is non-final and subclassing is unrestricted.

## 16. The Risk of Calling an Overridable Method in a Constructor

A superclass constructor might call a method **overridden** by a subclass:

~~~java
abstract class Base {
    Base() {
        System.out.println(value());
    }

    abstract int value();
}
~~~

Do not assume that inside a Base constructor the JVM always calls Base's implementation. Through virtual dispatch, it can dispatch to **the subclass implementation**, while the subclass fields **have not yet run their initializers**.

### Runnable Example: Uninitialized State of a Subclass

Create **`ConstructorDispatchDemo.java`**:

~~~java
public class ConstructorDispatchDemo {
    static abstract class Base {
        Base() {
            System.out.println("during=" + value());
        }

        abstract int value();
    }

    static final class Child extends Base {
        private final int number = 42;

        @Override
        int value() {
            return number;
        }

        void show() {
            System.out.println("after=" + value());
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.show();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorDispatchDemo.java
java ConstructorDispatchDemo
~~~

Stdout:

~~~text
during=0
after=42
~~~

**Why?** When the Base constructor runs, the entire object has been allocated and fields initially hold default values, but the Child field initializer `number = 42` has not executed yet. The virtual call to Child.value reads number=0. After the superclass constructor finishes, the subclass initializer assigns number=42.

### Relevance to Immutability

If a Base constructor calls an overridable `validate()` or `hashCode()`, a subclass may read uninitialized state, write invalid state, or cause side effects. That is why you should:

- Not call overridable methods from a constructor.
- Use a `private` or `final` helper if you need constructor logic that cannot be overridden.
- Perform validation using the arguments/fields belonging to the class being constructed itself.
- Publish the object only after construction is complete.
- If extension hooks are needed, invoke them from a **post-construction** lifecycle phase, with clear documentation.

## 17. Do Not Let `this` Escape While a Constructor Is Running

An object with private final fields can still cause problems if it exposes the `this` reference externally before the constructor finishes:

~~~java
class Dangerous {
    Dangerous(Registry registry) {
        registry.register(this); // May publish an incompletely constructed object.
        // Continue initialization...
    }
}
~~~

This is illustrative code; Registry would need to be defined. After registration, other code or another thread could call methods on the incomplete object.

### Common Escape Paths

- Registering a listener/callback using `this` directly inside the constructor.
- Starting a thread with a closure/reference to `this`.
- Storing `this` in a static mutable collection.
- Calling an overridable method so that a subclass publishes the reference.
- Passing `this` to a helper whose lifecycle cannot be controlled.

An immutability invariant must hold **when the object is observed**. If the object is exposed partway through construction, callers may see incomplete state.

### Better Design

Create the complete object first:

~~~java
final class Listener {
    private final String id;

    Listener(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    String id() {
        return id;
    }
}
~~~

Only after the constructor returns does the caller invoke `registry.register(listener)`. A factory can coordinate creating and then registering, without publishing prematurely from the constructor.

## 18. Java Memory Model, `final` Fields, and Immutable Objects

Java defines **final field semantics** that provide proper visibility for fields initialized in constructors when objects are validly constructed and shared.

However:

- `final` does not make a mutable referenced object thread-safe.
- `final` does not replace synchronization for operations that modify another object's state.
- If `this` escapes during construction, certain safe-construction guarantees no longer apply in the expected way.
- A true immutable graph can be easily shared across threads **without locking for read-only operations**, because there are no races on unchanging state.
- Mutable external resources/I/O/caches used inside methods still require their own thread-safety policies.

You should not claim that “simply making a `final class` makes every method automatically thread-safe”. A final class can hold a mutable `ArrayList` and update it, which still requires concurrency control.

## 19. What Should Be Done When a Superclass Is Designed for Inheritance?

Sometimes inheritance genuinely serves the domain. Define the **extension surface** and only allow subclasses at controlled points.

A base type can:

1. Keep fields `private final`, with no setters.
2. Use constructors to validate invariants.
3. Make immutable getters `final` if semantics need to be locked down.
4. Avoid calling overridable methods in constructors.
5. Only allow subclasses to interact through extension points with clear contracts.
6. Restrict the visibility of internal state; avoid `protected mutable fields`.
7. Control the set of subclasses via a `sealed` hierarchy or module/package restrictions.
8. Check each subclass for mutable fields/aliases/side effects.
9. Consider a final value object holding an interface-backed strategy instead of subclassing.

**Important:** Taking these steps does not turn arbitrary untrusted subclasses into immutable objects. If the public API genuinely promises that the entire hierarchy is immutable, only a **closed/audited hierarchy** or a non-subclassable structure is trustworthy under the usual model.

## 20. `protected` Mutable State Is Easily Corrupted by Subclasses

Bad example:

~~~java
class BaseConfig {
    protected java.util.List<String> hosts =
            new java.util.ArrayList<>();

    public java.util.List<String> hosts() {
        return java.util.List.copyOf(hosts);
    }
}
~~~

A subclass can call `hosts.add(...)` because the field is protected, even when the getter returns an unmodifiable snapshot. Adding `final` on the protected reference does not stop a subclass from mutating the List either:

~~~java
protected final List<String> hosts = new ArrayList<>();
~~~

`final` only prevents reassigning the reference; it does not prevent List mutation.

### Alternatives

- Use `private final List<String> hosts = List.copyOf(input)`.
- Return an immutable snapshot or an immutable value DTO.
- Do not provide a protected method that exposes a mutable alias.
- If a subclass needs to construct the object, pass the state into a protected constructor and validate/copy it before storing.
- For libraries exposing extension points, clearly document which operations are permitted rather than relying on “subclasses will keep themselves safe”.

## 21. Runnable Example: A Protected Reference Breaks the Assumption

Create **`ProtectedLeakDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ProtectedLeakDemo {
    static class BaseConfig {
        protected final List<String> hosts = new ArrayList<>();

        List<String> snapshot() {
            return List.copyOf(hosts);
        }
    }

    static final class SubConfig extends BaseConfig {
        void addHost(String host) {
            hosts.add(host);
        }
    }

    public static void main(String[] args) {
        SubConfig config = new SubConfig();
        BaseConfig view = config;

        System.out.println("before=" + view.snapshot());
        config.addHost("server-1");
        System.out.println("after=" + view.snapshot());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ProtectedLeakDemo.java
java ProtectedLeakDemo
~~~

Stdout:

~~~text
before=[]
after=[server-1]
~~~

The `snapshot()` getter returns a List that cannot be modified by the caller, yet a subclass still alters the internal List. If BaseConfig advertises immutability, this is a flawed design. `protected final` does not replace a `private immutable representation`.

## 22. Does `record` Help Protect Against Subclasses?

In Java 17, a `record` is a special class that is **implicitly final**. You cannot define a class that inherits from your record type.

~~~java
record Point(int x, int y) {}
~~~

`Point` is protected against subclasses adding mutable state or overriding accessors. Record components are stored according to the final-fields model, and the compiler generates the constructor/accessors/equals/hashCode/toString according to record rules.

However, **a record does not automatically guarantee deep immutability**. If a component is a mutable array or List, the caller can modify the shared reference if the constructor/accessor does not control it.

### Incorrect Example

~~~java
record UnsafeRecord(java.util.List<String> names) {
}
~~~

The caller creates the record from a mutable List and then adds elements; the generated `names()` accessor returns the same List reference. The record is still final, but the observable names change.

## 23. Record Compact Constructor and Defensive Copying

Create **`SafeRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeRecordDemo {
    record Roster(List<String> names) {
        Roster {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Roster roster = new Roster(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("roster=" + roster.names());

        try {
            roster.names().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("record list is unmodifiable");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeRecordDemo.java
java SafeRecordDemo
~~~

Stdout:

~~~text
input=[Mai, An]
roster=[Mai]
record list is unmodifiable
~~~

In the compact constructor, the component parameter `names` is replaced with the snapshot `List.copyOf(names)`; the record mechanism assigns the field from the final value of the parameter according to Java rules. The generated accessor returns the immutable List.

Because the element type is immutable `String`, this record has stable logical state per the demo's API. If the component held mutable Person objects, you would need to convert them into immutable snapshots similarly to the Group example above.

## 24. Record with an Array: Copy Both on Input and on Return

Mutable arrays require two-way control. With a record, the default generated accessor returns the reference, so when you want an immutable array-backed value, you must **override the accessor** to clone it.

Create **`SafeArrayRecordDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class SafeArrayRecordDemo {
    record Bytes(byte[] value) {
        Bytes {
            Objects.requireNonNull(value);
            value = value.clone();
        }

        @Override
        public byte[] value() {
            return value.clone();
        }

        int length() {
            return value.length;
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2};
        Bytes record = new Bytes(input);

        input[0] = 9;
        byte[] external = record.value();
        external[1] = 8;

        System.out.println("input=" + Arrays.toString(input));
        System.out.println("external=" + Arrays.toString(external));
        System.out.println("stored=" +
                Arrays.toString(record.value()));
        System.out.println("length=" + record.length());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeArrayRecordDemo.java
java SafeArrayRecordDemo
~~~

Stdout:

~~~text
input=[9, 2]
external=[1, 8]
stored=[1, 2]
length=2
~~~

**An additional point:** The generated `equals/hashCode` of a record with an array component typically uses array **reference equality/hashCode**, rather than comparing elements like `Arrays.equals`. If the record needs **value equality by byte contents**, you should design compatible equals/hashCode methods yourself or use a different representation. Preventing mutable aliases does not by itself decide all value semantics.

## 25. `sealed class` in Java 17: Controlling the Set of Subclasses

`sealed` allows restricting **which direct subclasses are permitted**. For example:

~~~java
sealed abstract class Shape permits Circle, Rectangle {
}

final class Circle extends Shape {
}

final class Rectangle extends Shape {
}
~~~

If Shape, Circle, and Rectangle belong to a valid scope/module/package, only the permitted types can directly extend Shape. Permitted subclasses must satisfy the rules for `final`, `sealed`, or `non-sealed` depending on the context.

### Does Sealed Protect Immutability?

**Not automatically.** `sealed` restricts **who is allowed to inherit**. It does not automatically make permitted subclass fields final, does not copy mutable values, and does not forbid mutators.

A hierarchy's immutability is ensured when:

1. The superclass state is immutable and its constructor is correct.
2. **Each permitted subtype** is audited for its state/methods.
3. There is no `non-sealed` branch open to arbitrary subclasses if the contract of the entire hierarchy requires immutability.
4. The API does not expose mutable state.
5. There are no invalid construction/escape paths.
6. Future changes to the permitted set are also reviewed against the contract.

## 26. Runnable Example: A Sealed Hierarchy with All Permitted Subtypes Final

Create **`SealedImmutableHierarchyDemo.java`**:

~~~java
public class SealedImmutableHierarchyDemo {
    sealed abstract static class Measure
            permits Length, DurationValue {
        private final long baseUnits;

        protected Measure(long baseUnits) {
            if (baseUnits < 0) {
                throw new IllegalArgumentException("negative units");
            }
            this.baseUnits = baseUnits;
        }

        public final long baseUnits() {
            return baseUnits;
        }

        public abstract String unit();
    }

    static final class Length extends Measure {
        Length(long millimeters) {
            super(millimeters);
        }

        @Override
        public String unit() {
            return "mm";
        }
    }

    static final class DurationValue extends Measure {
        DurationValue(long milliseconds) {
            super(milliseconds);
        }

        @Override
        public String unit() {
            return "ms";
        }
    }

    public static void main(String[] args) {
        Measure a = new Length(120);
        Measure b = new DurationValue(300);

        System.out.println(a.baseUnits() + " " + a.unit());
        System.out.println(b.baseUnits() + " " + b.unit());
        System.out.println("sealed=" + Measure.class.isSealed());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SealedImmutableHierarchyDemo.java
java SealedImmutableHierarchyDemo
~~~

Stdout:

~~~text
120 mm
300 ms
sealed=true
~~~

The base Measure holds a private final long, validates in the constructor, and declares `baseUnits()` final. Both permitted concrete classes are final, contain no mutable fields, and return only constant unit strings. Because the hierarchy is closed and audited in the demo, there is a basis for protecting the immutable contract.

**You should not infer** that a Measure value is equivalent in units between Length and DurationValue just because they share the same baseUnits number; they are two different domain quantities. Inheritance must be evaluated by substitutability and domain meaning, not merely syntactic convenience.

## 27. A `non-sealed` Branch Can Reopen Inheritance

Illustrative example:

~~~java
sealed interface Value permits FixedValue, ExtensibleValue {
}

record FixedValue(int number) implements Value {
}

non-sealed class ExtensibleValue implements Value {
    private int number;

    public void change(int value) {
        number = value;
    }
}
~~~

`Value` is sealed, yet the permitted `ExtensibleValue` is `non-sealed`, reopening the possibility of further subclassing and introducing mutable state. Therefore, **a sealed interface by itself is not sufficient** to promise that all Value implementations are immutable.

Similarly, if a `sealed` base permits a `sealed` child that in turn allows mutable descendants, you must audit the entire subtree all the way down to every concrete leaf.

### When Should You Choose Sealed?

- The domain has a known, fixed set of variants, such as a success/failure `Result`.
- You want to reason exhaustively about variants when supported by the API.
- You want to control subtype authors and protect the contract.
- You accept the versioning cost when adding a new permitted subtype.

If you do not need a subtype hierarchy, **a final class or record is simpler**.

## 28. Composition Replaces Inheritance for Extending Behavior

The need to “add behavior” does not necessarily require subclassing an immutable value. You can keep **immutable state** in a final class while placing behavior into a separate strategy object.

For example:

~~~java
final class Message {
    private final String text;

    Message(String text) {
        this.text = java.util.Objects.requireNonNull(text);
    }

    String text() {
        return text;
    }
}

interface Formatter {
    String format(Message message);
}
~~~

Different Formatter implementations do not modify Message. The caller passes Message into a Formatter and receives different strings **without needing to subclass Message**.

### Benefits

- Message remains final, protecting its contract.
- Strategy instances can be swapped independently.
- Behavior can be tested using a fake formatter.
- No reliance on protected state or constructor hooks.
- New formatters can be added without modifying Message's hierarchy.

## 29. Runnable Example: Final Value + Strategy Interface

Create **`CompositionStrategyDemo.java`**:

~~~java
import java.util.Objects;

public class CompositionStrategyDemo {
    static final class Message {
        private final String text;

        Message(String text) {
            this.text = Objects.requireNonNull(text);
        }

        String text() {
            return text;
        }
    }

    interface Formatter {
        String format(Message value);
    }

    static final class Plain implements Formatter {
        @Override
        public String format(Message value) {
            return value.text();
        }
    }

    static final class Bracketed implements Formatter {
        @Override
        public String format(Message value) {
            return "[" + value.text() + "]";
        }
    }

    static void show(Message value, Formatter formatter) {
        System.out.println(formatter.format(value));
    }

    public static void main(String[] args) {
        Message message = new Message("Java");
        show(message, new Plain());
        show(message, new Bracketed());
        System.out.println("original=" + message.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompositionStrategyDemo.java
java CompositionStrategyDemo
~~~

Stdout:

~~~text
Java
[Java]
original=Java
~~~

Adding new presentation styles does not require extending Message. Even if Formatter itself holds mutable state, that does not make Message mutable, as long as the API does not allow Formatter to mutate the internals of Message. **Separate transformation/presentation responsibilities** from the immutable data value.

## 30. Interfaces and Immutability Contracts: The Compiler Does Not Automatically Enforce Immutable Implementations

Suppose:

~~~java
interface StableItem {
    String label();
}
~~~

There is no modifier on an interface that forces all implementing classes to be immutable. A class can implement `label()` from a mutable field and change it via a setter.

~~~java
class MutableItem implements StableItem {
    private String label;

    MutableItem(String label) {
        this.label = label;
    }

    @Override
    public String label() {
        return label;
    }

    void rename(String next) {
        label = next;
    }
}
~~~

If `StableItem` documents that “label never changes”, MutableItem violates the **behavioral contract**, yet the Java compiler does not prove deep immutability.

### When Using an Interface Is Still Reasonable

An interface can describe a **read-only API** or a **snapshot contract**, but that is documentation/behavior that needs testing. If a caller needs a guaranteed immutable value, a factory can **copy into a final concrete type** or the API can return an immutable record/final class, rather than trusting every arbitrary implementation.

An interface “without setters” does not mean all implementing objects are immutable: they can still be modified through another reference or a background task.

## 31. Public Immutable Base Class and equals/hashCode Inheritance

Even when subclasses have no mutable state, allowing inheritance can make value semantics hard to preserve:

- A subclass may add new data that must participate in equality.
- A superclass `equals` using `instanceof Base` may consider a Child object equal to a Base object based on the base fields.
- Meanwhile, Child `equals` requires the same Child type and the additional fields.
- The result easily breaks the **symmetry** or **transitivity** of `equals`.
- Hash codes must be consistent with equals and must not rely on mutable fields.

Conceptual example:

~~~java
class Point {
    final int x, y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Point point
                && point.x == x && point.y == y;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(x, y);
    }
}
~~~

If a subclass `ColoredPoint extends Point` adds `color` and overrides equals to require the same color, a Point can consider a ColoredPoint “equal” to it, whereas the ColoredPoint does not consider the Point “equal” to it — violating symmetry.

### Solutions

- A **final value class** with equals/hashCode consistent across all immutable state.
- A record when it fits the value semantics.
- Avoid subclassing value types in a way that “adds new state altering equality”.
- If a hierarchy is strictly required, define a clear equals strategy, test symmetry/transitivity, and control subclasses.

Forbidding subclasses does not automatically make equals right, but it **significantly reduces the space of types that can break the contract**.

## 32. Runnable Example: Equality Broken by Open Inheritance

Create **`EqualityInheritancePitfallDemo.java`**:

~~~java
import java.util.Objects;

public class EqualityInheritancePitfallDemo {
    static class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Point p
                    && p.x == x && p.y == y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = color;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof ColoredPoint p
                    && super.equals(p)
                    && Objects.equals(color, p.color);
        }

        @Override
        public int hashCode() {
            return Objects.hash(super.hashCode(), color);
        }
    }

    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        ColoredPoint red = new ColoredPoint(1, 2, "red");

        System.out.println("plain.equals(red)=" +
                plain.equals(red));
        System.out.println("red.equals(plain)=" +
                red.equals(plain));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EqualityInheritancePitfallDemo.java
java EqualityInheritancePitfallDemo
~~~

Stdout:

~~~text
plain.equals(red)=true
red.equals(plain)=false
~~~

This is an **intentional anti-example**, not a recommended way to write equals. Both classes have only final fields, yet equals is broken because the subclass alters the criteria. When immutable value objects are used as Map/Set keys, a broken equality contract leads to confusing behavior. A `final class` prevents this kind of subclass from breaking the base class's semantics.

## 33. Constructors and Factories Should Use a Final Instance Type When a Guarantee Is Needed

If a public API returns an interface or a non-final base type:

~~~java
StableValue value = supplier.get();
~~~

the caller must rely on the contract of the **implementation** to know whether the object is truly immutable. If the supplier can return a mutable implementation, the interface type by itself is not enough.

A stronger approach is to **copy inputs into a final snapshot type**:

~~~java
final class StableName {
    private final String text;

    StableName(String text) {
        this.text = java.util.Objects.requireNonNull(text);
    }

    String text() {
        return text;
    }
}
~~~

Factory:

~~~java
static StableName snapshot(NameSource source) {
    return new StableName(source.text());
}
~~~

The snippets above require an appropriately declared `NameSource` interface. The key point is that the factory does not keep an alias to the potentially mutable NameSource; it extracts the immutable String value and creates a StableName.

### A Concurrency Note

If NameSource is mutable and modified concurrently while multiple fields are being read, the factory needs a domain-level **consistent snapshot** (lock/transaction/versioning), rather than simply reading fields sequentially and assuming the state is consistent. A final output type by itself cannot repair input data that was read inconsistently.

## 34. A Copy Constructor Must Not Trust an Overridable Getter from an Arbitrary Source

A “copy constructor” for a non-final base:

~~~java
class Value {
    private final int amount;

    Value(int amount) {
        this.amount = amount;
    }

    Value(Value other) {
        this.amount = other.amount();
    }

    int amount() {
        return amount;
    }
}
~~~

If `other.amount()` can be overridden in a subclass, an externally supplied source object can return varying values or produce side effects. The copy constructor appears to be reading immutable base state, when in reality it is performing dynamic dispatch.

**Safe alternatives** when still within the same class implementation's control: a private helper directly accessing the private final state of a Value instance, or a static factory with well-defined validation, or forbidding subclasses with a final class.

The point is not “never call a method from a constructor”, but rather **do not call an overridable method on untrusted objects to derive an immutable invariant**. Define the contract and data flow clearly.

## 35. Constructor Normalization, Invariants, and Inheritance

An immutable class should have a constructor that:

- Validates null/range/format.
- Normalizes data into a canonical representation.
- Copies mutable inputs before publishing.
- Does not retain references through which state can be modified externally.
- Does not call overridable methods.
- Does not let `this` escape.
- Does not leave the object in a temporary state observable by callers.

Example `DurationValue`:

~~~java
public final class DurationValue {
    private final long millis;

    public DurationValue(long millis) {
        if (millis < 0) {
            throw new IllegalArgumentException("negative duration");
        }
        this.millis = millis;
    }

    public long millis() {
        return millis;
    }
}
~~~

With a `final class`, no external subclass can introduce another method that makes `millis()` vary or add mutable state under the guise of DurationValue.

### Validation Does Not Come Automatically from final

A `final class` still allows a flawed constructor, for example accepting `millis = -10` even when the domain invariant requires non-negative values. Controlling inheritance is **one piece of immutable design**, not a substitute for validation.

## 36. Immutability and Caching/Lazy Initialization

A final class can hold an immutable logical value while using an internal cache:

~~~java
final class ParsedText {
    private final String text;
    private String cachedNormalized;

    ParsedText(String text) {
        this.text = text;
    }
}
~~~

This is **logical immutability** with a mutable implementation detail, which requires careful design. If the cache is updated from multiple threads, visibility and data races must be considered. Do not assume that “final class + private field” means the physical state is immutable.

### Two Clearer Approaches for Beginners

1. Compute the value in the constructor and store it in a `private final` field.
2. If lazy computation is required, use a valid synchronization/volatile/caching policy under the Java Memory Model, ensuring that the logical value does not change.

You should only declare an immutability contract based on **verified observable semantics and thread-safety guarantees**, rather than unconditionally hiding mutable state and calling it “fully immutable”.

## 37. Immutability and Serialization/Framework Construction

Some frameworks construct objects via reflection, deserialization, or bytecode generation. Those processes may follow different rules from normal constructor invocation.

When designing an immutable type for a framework:

- Check whether the framework supports final classes/records.
- Ensure that every valid instance-creation path performs validation/copying.
- Do not expose a public no-arg constructor and invariant-breaking setters just for framework compatibility if a better solution exists.
- Be careful with deserialization bypasses, class proxies, and lazy-loaded associations.
- Do not assume framework proxies are allowed to subclass a `final class`.
- If a framework truly requires proxy subclassing, consider separating the mutable persistence entity from the immutable domain/DTO snapshot.

A Java language-level final class prevents **ordinary source-level subclassing**, but does not replace JVM-wide security mechanisms against privileged reflection/agents/instrumentation.

## 38. Choosing Between `final`, `sealed`, and Composition

| Need | Recommendation | Reason |
| --- | --- | --- |
| An immutable value type that needs no subtypes | `final class` or `record` | Prevents subclass overrides and mutable state |
| A fixed and controlled set of variants | `sealed` base + audited final leaves | Keeps the hierarchy closed |
| Unforeseen plugin implementations needed | Interface + contract tests; copy into immutable snapshots when a guarantee is needed | Immutability of an arbitrary plugin cannot be enforced at compile time |
| Additional ways to display or transform a value | Composition/strategy | Adds behavior without changing the value type |
| Only one base operation needs protection | `final method` | Prevents overriding that operation; does not guarantee the whole object is immutable |
| Mutable state shared by an owner | Separate the mutable owner and an immutable read model | Does not pretend the entire object graph is immutable |
| Stable collection elements desired | Immutable elements + `List.copyOf` | Blocks both structural aliases and element aliases |
| Framework requires proxy subclasses | Separate the persistence model from the immutable value object when appropriate | Avoids conflicts with the final subclass restriction |
| Type used as a `HashMap` key | Immutable value + stable equals/hashCode | Avoids key mutation and hierarchy equality pitfalls |

No single modifier replaces **choosing ownership, representation, and contract**.

## 39. Process for Designing a Trustworthy Immutable Class

**Step 1 — Define the logical state:** What properties are callers permitted to observe? Are those properties allowed to change after construction?

**Step 2 — Choose an extension policy:** If inheritance is not needed, declare the class `final` (or use a record). If variants are needed, consider a `sealed` hierarchy with final leaves and audit each subtype.

**Step 3 — Choose an immutable representation:** Prefer primitives, String, immutable Java time types, custom final value classes, and records with immutable components.

**Step 4 — Validate all inputs:** Nulls, ranges, duplicates, overflow, and cross-field constraints.

**Step 5 — Defensive copy on input:** Do not retain aliases to mutable arrays/Lists/Dates held by the caller.

**Step 6 — Protect outputs:** Do not return raw mutable internal fields; use snapshots/copies or genuinely immutable typed views.

**Step 7 — No mutators:** Operations that transform the logical value should return a new immutable instance or a clear result.

**Step 8 — Control constructors:** Do not call overridable hooks, do not publish `this` prematurely, and do not leave inconsistent intermediate states.

**Step 9 — Protect equality:** For value objects, ensure equals/hashCode/toString are stable, adhere to their contracts, and cannot be broken by subclasses.

**Step 10 — Test aliases and inheritance:** Mutate inputs after construction, attempt to mutate getter results, attempt subclassing/overriding (with compile-fail tests where appropriate), and verify concurrency behavior.

**Step 11 — Check framework boundaries:** Through what paths might serializers/ORMs/mappers/reflection construct or alter state?

**Step 12 — Document the exact level of guarantee:** Deeply immutable, shallowly immutable, read-only view, or snapshot — document it clearly.

## 40. Testing Immutability Protection: Combined Example

Create **`ImmutableContractTestDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableContractTestDemo {
    static final class Preferences {
        private final List<String> tags;

        Preferences(List<String> source) {
            tags = List.copyOf(source);
        }

        List<String> tags() {
            return tags;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("java");

        Preferences pref = new Preferences(input);
        input.add("spring");

        check(pref.tags().equals(List.of("java")),
                "input alias changed snapshot");

        boolean rejected = false;
        try {
            pref.tags().add("kotlin");
        } catch (UnsupportedOperationException ex) {
            rejected = true;
        }

        check(rejected, "getter leaked mutable collection");
        check(pref.tags().equals(List.of("java")),
                "observable value changed");

        System.out.println("input alias test PASS");
        System.out.println("output mutation test PASS");
        System.out.println("immutable value test PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableContractTestDemo.java
java ImmutableContractTestDemo
~~~

Stdout:

~~~text
input alias test PASS
output mutation test PASS
immutable value test PASS
~~~

The example tests mutability from two directions: an external alias to the constructor input and attempted mutation through the getter. If elements are mutable, tests must also attempt to modify elements via an alias. If the class allows subclassing, additional tests for implementing subclasses are needed to confirm they do not break the behavioral contract.

`private final` is useful, but **every external path that could affect observable state** is what needs to be tested.

## 41. Testing Subclass Prevention: Compile-Time Negative Test

Suppose you have written:

~~~java
public final class ImmutableId {
    private final String value;

    public ImmutableId(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    public String value() {
        return value;
    }
}
~~~

Attempting:

~~~java
// class BrokenId extends ImmutableId {
//     BrokenId() {
//         super("X");
//     }
// }
~~~

If you uncomment and declare it in an appropriate context, javac rejects it due to **cannot inherit from final ImmutableId**.

This is an **intentionally non-compiling** example used to verify the language restriction; do not put it into a normal runnable program expecting stdout.

### Records Behave the Same Way

~~~java
record Coordinate(int x, int y) {}
// class MutableCoordinate extends Coordinate {} // Invalid.
~~~

A record is implicitly final, so it cannot be subtyped in the way an ordinary class can. However, defensive copying is still needed if a component is mutable.

## 42. Exercise 1 — Is a Final Class with a Final List Immutable?

Given:

~~~java
final class Notes {
    private final List<String> values;

    Notes(List<String> values) {
        this.values = values;
    }

    List<String> values() {
        return values;
    }
}
~~~

**Question:** The class is `final`, and the field is `private final`. Why is it still not immutable?

**Answer:** The mutable List is shared on both input and output. The caller can modify the source List or the getter result, causing observable values to change. You need `List.copyOf`/defensive copying, and to check the element types.

## 43. Exercise 2 — Overriding a Getter Breaks the Contract

A base class has `private final int number` and a non-final getter `public int number()`. A subclass overrides the getter to return a mutable field. Will a caller with `Base value = new Subclass(...)` see `value.number()` change?

**Answer:** It can change. Dynamic dispatch selects the subclass override based on the runtime type. If you want all Base objects to be immutable, you must prevent arbitrary subclassing (final class/sealed controlled hierarchy), not just declare a private final field.

## 44. Exercise 3 — Is a Final Getter Enough?

Base has `public final int id()` returning a private final field, but a subclass adds `int counter` and `increment()`.

**Answer:** `id()` does not change, but **the subclass object has mutable state**. Therefore, you can only commit that “id is stable”; you cannot assert that the entire subtype instance is immutable.

## 45. Exercise 4 — Overridable Call in a Constructor

Inside Base's constructor, an abstract/overridable `value()` is called. The subclass has `private final int value = 42` and overrides `value()` to return the field.

**Answer:** The call from Base's constructor can observe 0 because the subclass initializer has not run yet. Do not call overridable methods before initialization finishes; use final/private helpers and reason carefully about construction order.

## 46. Exercise 5 — Mutable Record Component

~~~java
record Box(byte[] data) {
}
~~~

If the input byte[] changes after creating Box, does `box.data()[0]` change?

**Answer:** It can change, because by default a record holds a reference to the array and the accessor returns that reference. Clone the array in the constructor and the getter. If using the record as a value object, also consider equals/hashCode semantics for arrays.

## 47. Exercise 6 — Is a Sealed Hierarchy Automatically Immutable?

A sealed interface permits a final immutable record and a `non-sealed` mutable class.

**Answer:** No. Sealed only restricts direct permitted types; the non-sealed child reopens inheritance and can contain mutable state. To make a hierarchy immutable, you must audit all permitted implementations and leave no uncontrolled open branch.

## 48. Exercise 7 — Composition Instead of Inheritance

An immutable `ReportData` needs to support HTML, Markdown, and Plain Text formatting.

**Suggested answer:** Keep `final ReportData` with String/immutable content, and create a `Formatter` interface with three implementations taking ReportData. There is no need for `HtmlReportData extends ReportData` to change the presentation, avoiding opening the door to mutable subclasses of the immutable data type.

## 49. Exercise 8 — Shallow Snapshot

What does `List.copyOf(List.of(mutableMember))` protect, and what does it not protect?

**Answer:** It protects the List structure, not deep-copying the Member object. If Member is mutable and an external alias still exists, observed member state can still change. Use an immutable MemberSnapshot or convert/copy element values according to the contract.

## 50. Exercise 9 — Equals and Subclasses

The superclass `Point.equals` uses `other instanceof Point`. The subclass `ColoredPoint.equals` only accepts a ColoredPoint with the same color.

**Answer:** It can violate symmetry: plain.equals(colored) is true while colored.equals(plain) is false. For value objects, final classes/records or a tightly designed equality contract helps avoid this.

## 51. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| “Every field being final means the object is immutable.” | Referenced objects may be mutable | Copy and choose immutable representations |
| “A final class means all internals are immutable.” | The class can still hold a mutable List/Date/array | Validate, use private fields, and make defensive copies |
| “Superclass final fields make all subclasses immutable.” | A subclass can add mutable state | Final class or closed/audited hierarchy |
| “A private field prevents a getter from varying.” | The getter can be overridden | Final methods/controlled inheritance |
| “A final method makes the entire object immutable.” | Subclasses can still add mutable fields | Distinguish an API invariant from whole-object immutability |
| “A protected final List cannot be modified by subclasses.” | Final only forbids reassigning the reference | Private immutable snapshot |
| “A constructor calls subclass overrides after the subclass is initialized.” | Dispatch can occur before subclass initializers run | Do not call overridable methods in constructors |
| “Publishing an object from a constructor is safe because fields are final.” | Callers may observe an incomplete object | Do not let this escape |
| “List.copyOf deep-copies elements.” | It only makes a shallow structural snapshot | Immutable elements/snapshot values |
| “Collections.unmodifiableList creates a frozen snapshot.” | It is typically a live view reflecting source changes | Use List.copyOf when a snapshot is needed |
| “A record is deep immutable by default.” | Components may be mutable | Compact constructor copy + safe accessors |
| “Sealed automatically makes permitted classes immutable.” | Mutable or non-sealed subclasses can be permitted | Audit every leaf and close the hierarchy |
| “A read-only interface guarantees an immutable implementation.” | Implementing classes can still have mutable aliases | Behavioral contract + snapshots |
| “A copy constructor using an overridable getter is always safe.” | A subclass can alter behavior | Direct trusted state/validate/final class |
| “Open value inheritance does not affect equals.” | A subclass adding value state can break symmetry | Final value types/consistent equality |
| “A final class is automatically thread-safe.” | Mutable internals can still race | Deep immutability or synchronization |
| “Reflection is always harmless.” | It can construct, invoke, and mutate depending on permissions | Design boundaries and error handling |

## 52. Final Checklist

- [ ] I distinguish between immutable state and merely a final reference.
- [ ] I understand that `final class` prevents subclasses and `final method` prevents overrides.
- [ ] I know that private final fields do not guarantee arbitrary subclasses are immutable.
- [ ] I can demonstrate how a subclass overriding a getter changes the result.
- [ ] I know that a subclass can add mutable fields even when the superclass has final getters.
- [ ] I distinguish “stable base projection” from “whole object immutable”.
- [ ] I know that `final class` does not automatically prevent mutation via List/Date/array aliases.
- [ ] I defensively copy mutable inputs.
- [ ] I do not return mutable internal state through getters.
- [ ] I know that `List.copyOf` snapshots the structure and does not deep-copy elements.
- [ ] I know that `Collections.unmodifiableList` is typically a live unmodifiable view.
- [ ] I know how to convert mutable element data into immutable snapshots when needed.
- [ ] I do not call overridable methods in constructors.
- [ ] I do not publish `this` before construction is complete.
- [ ] I understand the limits of Java's final-field visibility semantics.
- [ ] I use final records while still checking for mutable components.
- [ ] I copy record array components on both input and output.
- [ ] I know that record array equality needs special attention.
- [ ] I know that sealed controls permitted subclasses but does not automatically guarantee immutability.
- [ ] I audit every permitted subtype and pay attention to any non-sealed branch.
- [ ] I know how to use composition/strategy to extend behavior without subclassing a value object.
- [ ] I know that an interface does not automatically enforce immutable implementations.
- [ ] I avoid protected mutable references that expose internals.
- [ ] I consider equals/hashCode when designing a value hierarchy.
- [ ] I know how to test input aliases, output mutation, and subclass behavior.
- [ ] I know that frameworks may require a separate snapshot model alongside ORM/proxies.
- [ ] I use the exact Java 17 programs and understand the given stdout.

**Conclusion:** A solid immutability commitment does not start and end with the `final` keyword on a field. If a class can be arbitrarily subclassed, a subclass can add mutable state or alter getter behavior, invalidating any promise about **the entire instance**. For a concrete immutable value type, **`final class` or record + private final state + validation + defensive copying** is the simplest and clearest choice. When a hierarchy is genuinely needed, **close and control it with sealed types**, audit each permitted subtype, and protect the methods that uphold invariants. When you only want to extend how values are processed, **composition/strategy** usually avoids the risks of inheritance. Strong protection means there is no valid path through the API, aliases, or subclasses that can alter the logical state the contract has promised will remain stable.
