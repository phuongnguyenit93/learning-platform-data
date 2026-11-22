# Reference Assignment Differs from Creating an Object Copy in Java

In Java, the statement `b = a` on a **reference type** does not create a new object. It only copies the **reference value**, causing `a` and `b` to point to the same object. To obtain a second object, you must use a constructor, factory, clone, or a clearly designed copying mechanism.

~~~java
Box a = new Box(10);
Box b = a;                  // Same Box object.
Box c = new Box(a.value()); // Different Box object.
~~~

Two Box objects can have the same value 10 while having different **identity**. Even more importantly: if Box contains a mutable Address/List, creating a new Box **may still share the old Address/List**. That is the difference between **aliasing**, **shallow copy**, and **deep copy**.

This lesson belongs to Java Core — **Class & Object / Object Copying**, using Java 17+. Standalone programs include a filename, compile/run commands, and stdout. Non-standalone code snippets are noted as illustrative.

## 1. Objectives

You will:

- Understand object identity, reference variables, and aliases.
- Know that `b = a` with a reference does not call a constructor or clone.
- Distinguish between modifying an object and reassigning a reference variable.
- Distinguish `==` from `equals` and value equality.
- Understand that Java is always pass-by-value, including object arguments.
- Create copies using a constructor/factory.
- Distinguish shallow copy, deep copy, structural snapshot, and live view.
- Know that reference arrays and collections usually keep the same element references after structural copying.
- Use `List.copyOf` and `ArrayList` with the correct semantics.
- Understand the benefits of sharing immutable objects and the alias risks with mutable objects.
- Understand `Object.clone`, `Cloneable`, and the limitations of cloning.
- Copy graphs with cycles/shared nodes using an identity map.
- Identify ownership, concurrency, polymorphism, and test independence.

## 2. What Is a Reference?

A reference-type variable holds a reference value or null, rather than containing the entire object like a struct that is copied on assignment.

~~~java
class Box {
    int value;
}

Box a = new Box();
a.value = 10;
Box b = a;
~~~

Diagram:

~~~text
a --------+
          |
          v
       Box #1
       value=10
          ^
          |
b --------+
~~~

There are two variables but **one** Box object. Modifying `b.value = 20` causes `a.value` to also be 20.

If `b = new Box()`, b points to Box #2 while a still points to Box #1. Java assignment updates **the value inside variable b**, and does not automatically update variable a.

## 3. Runnable Program: Mutation and Reassignment

Create **`ReferenceDemo.java`**:

~~~java
public class ReferenceDemo {
    static final class Counter {
        private int value;

        Counter(int value) {
            this.value = value;
        }

        void increment() {
            value++;
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter a = new Counter(5);
        Counter b = a;

        System.out.println("same=" + (a == b));
        b.increment();
        System.out.println("a=" + a.value());

        b = new Counter(100);
        System.out.println("same now=" + (a == b));
        System.out.println("a now=" + a.value());
        System.out.println("b now=" + b.value());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceDemo.java
java ReferenceDemo
~~~

Stdout:

~~~text
same=true
a=6
same now=false
a now=6
b now=100
~~~

`b.increment()` mutates Counter #1 because a and b reference the same object. `b = new Counter(100)` creates Counter #2 and then replaces b's reference. There is no change to variable a.

## 4. Counting Created Objects

~~~java
Box a = new Box();
Box b = a;
Box c = new Box();
~~~

There are two calls to `new Box()`, so there are two Box objects; b is not a third object.

Create **`ConstructorCountDemo.java`**:

~~~java
public class ConstructorCountDemo {
    static final class Item {
        private static int created;

        Item() {
            created++;
        }

        static int created() {
            return created;
        }
    }

    public static void main(String[] args) {
        Item a = new Item();
        Item b = a;
        Item c = new Item();

        System.out.println("created=" + Item.created());
        System.out.println("a==b=" + (a == b));
        System.out.println("a==c=" + (a == c));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorCountDemo.java
java ConstructorCountDemo
~~~

Stdout:

~~~text
created=2
a==b=true
a==c=false
~~~

Counting constructors only illustrates `new`: some other runtime mechanisms such as `Object.clone()` or deserialization have their own object creation paths. Do not take constructor call count as a general definition of every way objects are created in the JVM.

## 5. Reference Assignment and Object Copying Differ in Diagrams

**Reference assignment:**

~~~text
a ----+
      +----> Person #1 (name="Mai")
b ----+
~~~

**Creating a new object:**

~~~text
a ----> Person #1 (name="Mai")
b ----> Person #2 (name="Mai")
~~~

If we create `b = new Person(a.name())`, there are two separate Person objects. However, they can have the same String name value. We must separate three questions:

1. `a == b`: are they the same object reference?
2. `a.equals(b)`: are they equal according to the value/business contract?
3. Does mutating a affect b? This depends on mutable state and nested references.

`equals` returning true **does not prove** that a copy has been deep-copied.

## 6. Copy Constructor for a Simple Object

Create **`CopyConstructorDemo.java`**:

~~~java
import java.util.Objects;

public class CopyConstructorDemo {
    static final class Person {
        private String name;

        Person(String name) {
            this.name = Objects.requireNonNull(name);
        }

        Person(Person other) {
            this(other.name);
        }

        String name() {
            return name;
        }

        void rename(String value) {
            name = Objects.requireNonNull(value);
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai");
        Person alias = original;
        Person copy = new Person(original);

        System.out.println("alias same=" + (alias == original));
        System.out.println("copy same=" + (copy == original));
        System.out.println("before=" +
                original.name() + "/" + copy.name());

        original.rename("An");
        System.out.println("after=" +
                original.name() + "/" + copy.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CopyConstructorDemo.java
java CopyConstructorDemo
~~~

Stdout:

~~~text
alias same=true
copy same=false
before=Mai/Mai
after=An/Mai
~~~

The copy constructor creates a new Person. String is immutable, so sharing the initial String object does not lead to the String content being modified in place. The rename method only reassigns Person.original.name to a different String.

## 7. `==` Differs from `equals`

For references, `==` asks whether they point to the same object. `equals` is defined by the class; if not overridden, Object.equals is based on identity by default. String/record typically have value equality semantics.

Create **`IdentityEqualityDemo.java`**:

~~~java
public class IdentityEqualityDemo {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Point original = new Point(2, 3);
        Point alias = original;
        Point copy = new Point(original.x(), original.y());

        System.out.println("alias same=" +
                (original == alias));
        System.out.println("copy same=" +
                (original == copy));
        System.out.println("copy equals=" +
                original.equals(copy));
        System.out.println("hash equal=" +
                (original.hashCode() == copy.hashCode()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IdentityEqualityDemo.java
java IdentityEqualityDemo
~~~

Stdout:

~~~text
alias same=true
copy same=false
copy equals=true
hash equal=true
~~~

The Point record has primitive components, so its generated equals compares by values. However, for an object graph with mutable references, `equals` returning true is not enough to conclude that nested objects have been separated.

## 8. Reassigning a Reference Does Not Immediately Destroy the Object

If:

~~~java
Box a = new Box();
Box b = a;
b = null;
~~~

a still references the Box. Assigning null to b does not delete the Box or immediately run a destructor. Once the object is no longer reachable from GC roots, the JVM can reclaim the memory when appropriate.

Similarly:

~~~java
Box previous = a;
a = new Box();
~~~

previous still points to the old object. The old object can remain alive because of other references, independent of the fact that variable a has been reassigned.

## 9. Java Always Passes by Value, Including Object References

When passing an object to a method, Java copies the **reference value** into the local parameter. The method can mutate the shared object, but it **cannot** change the caller's reference variable merely by reassigning the parameter.

Create **`PassByValueDemo.java`**:

~~~java
public class PassByValueDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box box) {
        box.value = 99;
    }

    static void reassign(Box box) {
        box = new Box(700);
        System.out.println("inside=" + box.value);
    }

    public static void main(String[] args) {
        Box caller = new Box(10);
        mutate(caller);
        System.out.println("after mutate=" + caller.value);

        reassign(caller);
        System.out.println("after reassign=" + caller.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PassByValueDemo.java
java PassByValueDemo
~~~

Stdout:

~~~text
after mutate=99
inside=700
after reassign=99
~~~

The mutate method modifies the same Box instance. The reassign method changes the **local parameter** to another Box; the caller variable does not change. This is pass-by-value, not pass-by-reference.

## 10. A Reference Stored in a Field Is Still an Alias

~~~java
class Team {
    Member leader;

    Team(Member leader) {
        this.leader = leader;
    }
}
~~~

If Team retains the reference to the Member argument as-is, the caller's Member variable and `team.leader` point to the same object. If Member is mutable, Team can observe external mutations.

This can be **correct** if Member is an intentionally shared entity. However, if Team wants an immutable snapshot at creation time, you need to copy the relevant values into an immutable representation.

**Do not copy every entity reference by default.** Determine ownership and identity: sharing the same customer entity can be right, whereas sharing a mutable billing address as an immutable historical snapshot can be wrong.

## 11. A `final` Reference Does Not Turn Assignment into a Copy

~~~java
final Person original = new Person("Mai");
Person alias = original;
~~~

`final` only prevents reassigning the variable original; it does not prevent aliasing or mutating Person state. Similarly:

~~~java
final java.util.List<String> names =
        new java.util.ArrayList<>();
names.add("Mai"); // Valid.
~~~

A final reference to a mutable List is not an immutable List. `final field`, `final class`, and deep immutability are separate concepts.

## 12. What Is a Shallow Copy?

A **shallow copy** typically creates a new top-level object, copying its field values:

- Primitive field → copies the primitive value.
- Reference field → copies the reference value, **without cloning the target object**.

~~~text
Original Person #1 ----address----+
                                   |
                                   v
                                Address #7
                                   ^
                                   |
Copy Person #2 --------address----+
~~~

Even though the two Person instances are different, they share the mutable Address. Therefore, modifying city through the Person copy can affect the original.

Shallow copy is not always wrong: if Address is immutable, sharing is safe for state. The question is **whether the contract requires independence of nested data**.

## 13. Runnable Example: Shallow Copy of Person–Address

Create **`ShallowCopyDemo.java`**:

~~~java
public class ShallowCopyDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai", new Address("Hue"));
        Person copy = original.shallowCopy();

        System.out.println("same Person=" + (original == copy));
        System.out.println("same Address=" +
                (original.address == copy.address));

        copy.address.city = "Da Nang";

        System.out.println("original city=" +
                original.address.city);
        System.out.println("copy city=" + copy.address.city);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowCopyDemo.java
java ShallowCopyDemo
~~~

Stdout:

~~~text
same Person=false
same Address=true
original city=Da Nang
copy city=Da Nang
~~~

The top-level copy succeeded, yet Address is still shared. Lesson: `copy != original` only verifies top-level identity, **not** deep isolation.

## 14. Deep Copy Must Have a Clear Scope

A deep copy in a simple graph can be done as:

~~~java
Person deepCopy() {
    return new Person(name, new Address(address.city));
}
~~~

This is an illustrative method example. Both Person and Address are newly created, and String name is immutable so it can be shared.

However, if Address has a List of Phones, or the graph has cycles, we must examine further. Deep copy is **a contract about which mutable graph needs independence**, not a feature where the Java language provides a single command to copy everything.

### Runnable Example: Shallow and Deep

Create **`ShallowVsDeepDemo.java`**:

~~~java
public class ShallowVsDeepDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address copy() {
            return new Address(city);
        }
    }

    static final class Person {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }

        Person deepCopy() {
            return new Person(name, address.copy());
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai", new Address("Hue"));
        Person shallow = original.shallowCopy();
        Person deep = original.deepCopy();

        System.out.println("shallow same Address=" +
                (original.address == shallow.address));
        System.out.println("deep same Address=" +
                (original.address == deep.address));

        original.address.city = "Da Nang";

        System.out.println("original=" + original.address.city);
        System.out.println("shallow=" + shallow.address.city);
        System.out.println("deep=" + deep.address.city);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowVsDeepDemo.java
java ShallowVsDeepDemo
~~~

Stdout:

~~~text
shallow same Address=true
deep same Address=false
original=Da Nang
shallow=Da Nang
deep=Hue
~~~

For the Person→Address graph, deep copy created an independent Address. Do not generalize this to assume it has copied every kind of external resource or arbitrary cycles.

## 15. Primitive Arrays and Reference Arrays Have Two Different Copy Levels

~~~java
int[] a = {1, 2};
int[] b = a.clone();
~~~

b is a new array containing separate primitive values.

~~~java
Member[] a = {member};
Member[] b = a.clone();
~~~

b is a new array, but `a[0] == b[0]` is true; both slots hold the same Member reference.

### Runnable Example

Create **`ArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayCopyDemo {
    static final class Item {
        String name;

        Item(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        int[] primitives = {1, 2};
        int[] primitiveCopy = primitives.clone();
        primitiveCopy[0] = 9;
        System.out.println("primitive original=" +
                Arrays.toString(primitives));
        System.out.println("primitive copy=" +
                Arrays.toString(primitiveCopy));

        Item[] originals = {new Item("Mai")};
        Item[] referenceCopy = originals.clone();

        System.out.println("same arrays=" +
                (originals == referenceCopy));
        System.out.println("same item=" +
                (originals[0] == referenceCopy[0]));

        referenceCopy[0].name = "An";
        System.out.println("original item=" +
                originals[0].name);

        referenceCopy[0] = new Item("Binh");
        System.out.println("original now=" +
                originals[0].name);
        System.out.println("copy now=" +
                referenceCopy[0].name);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayCopyDemo.java
java ArrayCopyDemo
~~~

Stdout:

~~~text
primitive original=[1, 2]
primitive copy=[9, 2]
same arrays=false
same item=true
original item=An
original now=An
copy now=Binh
~~~

Modifying an **element object** can affect both reference arrays; replacing a **slot** in the copied array only affects the copied array.

## 16. Copying a `List` Structure Does Not Recreate Its Elements

Given `List<Member> original`, the expression `new ArrayList<>(original)` creates a **separate** list, yet the element slots still point to **the same Member objects**. Adding or removing elements in the new list does not modify the source list; mutating a shared `Member` causes both lists to observe that change.

## 17. `List.copyOf` Creates an Unmodifiable List, Not a Deep Copy

`List.copyOf(source)` provides an **unmodifiable structural snapshot** from a mutable source and disallows additions or removals through the result. However, mutable elements are still held by reference. It may return the same instance if the input is already in a suitable unmodifiable form; do not check `source != snapshot` as an API guarantee.

## 18. Do Views and Snapshots Differ?

`Collections.unmodifiableList(source)` creates an **unmodifiable view**: the caller cannot add or remove through the view, yet modifications to the source can be reflected in the view. `List.copyOf(source)` is a structural snapshot; subsequent structural changes to the source are not reflected in the snapshot.

The short program **`ListCopyDecisionDemo.java`** illustrates **all three** concepts in a single test:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListCopyDecisionDemo {
    static final class Task {
        String label;

        Task(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        List<Task> source = new ArrayList<>();
        source.add(new Task("A"));

        List<Task> shallow = new ArrayList<>(source);
        List<Task> snapshot = List.copyOf(source);
        List<Task> view = Collections.unmodifiableList(source);

        source.get(0).label = "X";
        source.add(new Task("B"));

        System.out.println("sizes=" + source.size() + "/" +
                shallow.size() + "/" + snapshot.size() + "/" + view.size());
        System.out.println("same child=" + (source.get(0) == shallow.get(0)));
        System.out.println("snapshot child=" + snapshot.get(0).label);
        try {
            snapshot.add(new Task("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot is unmodifiable");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListCopyDecisionDemo.java
java ListCopyDecisionDemo
~~~

~~~text
sizes=2/1/1/2
same child=true
snapshot child=X
snapshot is unmodifiable
~~~

**Conclusion for reference assignment:** Do not assume “having the word copy means all data is new.” You must distinguish **the identity of the list**, **the identity of the elements**, and **the structure update mode**. Copying Maps, arrays, and nested elements all require a similar distinction; depth knowledge is covered separately when choosing a shallow/deep-copy policy.

## 19. Immutable Objects Typically Do Not Need Copying to Protect State

String is immutable:

~~~java
String a = "Java";
String b = a;
a = "Kotlin";
~~~

`b` is still "Java". The reassignment of a does not modify the old String object.

### Runnable Example: String and StringBuilder

Create **`ImmutableVsMutableDemo.java`**:

~~~java
public class ImmutableVsMutableDemo {
    public static void main(String[] args) {
        String a = "Hi";
        String b = a;
        a = a + "!";

        System.out.println("String a=" + a);
        System.out.println("String b=" + b);

        StringBuilder builder = new StringBuilder("Hi");
        StringBuilder alias = builder;
        alias.append("!");

        System.out.println("builder=" + builder);
        System.out.println("same=" + (builder == alias));

        StringBuilder copy =
                new StringBuilder(builder.toString());
        copy.append("?");

        System.out.println("builder after copy=" + builder);
        System.out.println("copy=" + copy);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableVsMutableDemo.java
java ImmutableVsMutableDemo
~~~

Stdout:

~~~text
String a=Hi!
String b=Hi
builder=Hi!
same=true
builder after copy=Hi!
copy=Hi!?
~~~

Sharing an immutable String introduces no mutable alias risk. Sharing a StringBuilder can cause both references to observe mutations.

## 20. Copy Factory Creating an Immutable Snapshot

A mutable draft can be converted into a record snapshot:

Create **`SnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SnapshotDemo {
    static final class Draft {
        private String title;
        private final List<String> tags = new ArrayList<>();

        Draft(String title) {
            this.title = title;
        }

        void rename(String next) {
            title = next;
        }

        void addTag(String tag) {
            tags.add(tag);
        }

        String title() {
            return title;
        }

        List<String> tags() {
            return tags;
        }
    }

    record Snapshot(String title, List<String> tags) {
        Snapshot {
            tags = List.copyOf(tags);
        }

        static Snapshot from(Draft draft) {
            return new Snapshot(draft.title(), draft.tags());
        }
    }

    public static void main(String[] args) {
        Draft source = new Draft("First");
        source.addTag("java");

        Snapshot copy = Snapshot.from(source);

        source.rename("Second");
        source.addTag("object");

        System.out.println("source=" + source.title());
        System.out.println("copy=" + copy.title());
        System.out.println("source tags=" + source.tags());
        System.out.println("copy tags=" + copy.tags());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SnapshotDemo.java
java SnapshotDemo
~~~

Stdout:

~~~text
source=Second
copy=First
source tags=[java, object]
copy tags=[java]
~~~

The Snapshot record holds a String and a List<String> with an immutable structure; subsequent changes to Draft do not affect the snapshot. If elements are mutable or state is modified by another thread during copying, a stronger consistent snapshot contract and mechanism are required.

## 21. `Object.clone()`: Creates a New Object, Shallow by Default

`Object.clone()` can create another object, copying field values with shallow semantics. Regular classes need to support `Cloneable` and override clone if a public typed API is desired.

Create **`CloneDemo.java`**:

~~~java
public class CloneDemo {
    static final class Details {
        String note;

        Details(String note) {
            this.note = note;
        }
    }

    static final class Item implements Cloneable {
        String name;
        Details details;

        Item(String name, Details details) {
            this.name = name;
            this.details = details;
        }

        @Override
        public Item clone() {
            try {
                return (Item) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        Item original = new Item("A", new Details("old"));
        Item copy = original.clone();

        System.out.println("same Item=" + (original == copy));
        System.out.println("same Details=" +
                (original.details == copy.details));

        copy.name = "B";
        copy.details.note = "new";

        System.out.println("original name=" + original.name);
        System.out.println("copy name=" + copy.name);
        System.out.println("original note=" +
                original.details.note);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CloneDemo.java
java CloneDemo
~~~

Stdout:

~~~text
same Item=false
same Details=true
original name=A
copy name=B
original note=new
~~~

Clone creates a different top-level Item, yet the nested Details remains shared.

### Why Is a Copy Constructor/Factory Usually Preferred?

`Object.clone()` does not invoke a constructor through the normal path; copying final references and invariants can be difficult to handle. `Cloneable` is only a marker interface and does not itself declare a public clone method. A copy constructor/factory provides clearer control over validation and ownership.

## 22. Copying a Base Class Does Not Automatically Preserve Subtypes

Constructors do not override polymorphically. With `Dog extends Animal`, `new Animal(dog)` creates an Animal, and does not automatically preserve Dog.age or the runtime class Dog.

Create **`BaseCopyDemo.java`**:

~~~java
public class BaseCopyDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        Animal(Animal other) {
            name = other.name;
        }

        String name() {
            return name;
        }
    }

    static final class Dog extends Animal {
        private final int age;

        Dog(String name, int age) {
            super(name);
            this.age = age;
        }
    }

    public static void main(String[] args) {
        Animal original = new Dog("Milo", 3);
        Animal copy = new Animal(original);

        System.out.println("original class=" +
                original.getClass().getSimpleName());
        System.out.println("copy class=" +
                copy.getClass().getSimpleName());
        System.out.println("names=" +
                original.name() + "/" + copy.name());
        System.out.println("same object=" + (original == copy));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BaseCopyDemo.java
java BaseCopyDemo
~~~

Stdout:

~~~text
original class=Dog
copy class=Animal
names=Milo/Milo
same object=false
~~~

This is a **base projection copy** rather than a copy that preserves all subclass fields. If preserving the subtype is needed, design an instance method `copy()` with a contract and test each implementation, or restrict the hierarchy using final/sealed types.

## 23. A Deep Copy May Also Need to Preserve Reference Relationships

If in the source graph two fields point to **the same** child, a deep-copy algorithm that creates a new child for each field will lose the `left == right` relationship. If nodes also have back-references forming a **cycle**, naive recursive copying may never terminate.

Diagram:

~~~text
Source: root.left ──┐
                    ├──> shared child ──> root (cycle)
        root.right ─┘

The copy must preserve topology:
copy.left ──────┐
                ├──> cloned child ────> copy
copy.right ─────┘
~~~

## 24. Termination Rule and Reusing the Clone of the Same Node

When the contract requires preserving object graph topology, use a table of **original identity → copied node**, typically an `IdentityHashMap`. The processing order is:

1. `null` source → return `null`.
2. Source already present in the map → return **the same clone** already created.
3. New source → allocate the clone, **record the mapping first**, and only then copy child references.
4. For a graph with cycles, returning to an already-visited node lets the map break the recursion cycle.
5. Verify `original != copy`, `copy.left == copy.right`, and that the clone's back-reference points to the corresponding clone, **not** to the old graph.

This serves as a **scope boundary** for this introductory reference-vs-copy lesson; handling BFS/DFS, alias topology, mutable payloads, and graph cycles is practiced in depth when designing graph-copying algorithms. There is no need to deep-copy services, file handles, or database connections just because they reside in fields.

## 25. Deep Copy Does Not Automatically Duplicate Live Resources

Objects may hold sockets, file streams, database connections, threads, locks, or native handles. Such things have no sensible default deep copy. The domain copy policy must specify:

- Copy only configuration data?
- Keep a shared reference to the resource?
- Open a new resource?
- Or reject copying the resource owner?

Serialization/deserialization is also not a general-purpose deep-copy utility: there are issues of security, versioning, custom hooks, excluded state, and runtime resources.

## 26. Copying and Invariants

A copy operation must preserve validity conditions:

~~~java
final class Range {
    private final int start;
    private final int end;

    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("invalid range");
        }
        this.start = start;
        this.end = end;
    }

    Range(Range other) {
        this(other.start, other.end);
    }
}
~~~

This is an illustrative class; the copy constructor goes through validation. If receiving the source from an untrusted polymorphic interface with overridable getters, you need to control consistency and the behavioral contract of the getters.

A failed copy should not allow the caller to observe a partially constructed object. With an internal two-phase graph copy, publish the result only after completion, unless the API explicitly specifies a different contract.

## 27. Concurrency: Copying Does Not Automatically Create a Consistent Snapshot

If thread A reads firstName, thread B updates firstName/lastName, and then A reads lastName, the copy can combine two different versions. Deep copy guaranteeing an independent object graph **after completion** does not mean the source was read atomically.

Depending on the domain, use:

- A lock around the entire snapshot and mutations.
- Immutable state replacement with safe publication.
- Versioned read/retry.
- A DB transaction with appropriate isolation.
- Copy-on-write/immutable data structures.

Do not treat assignment, clone, or a copy constructor by itself as a synchronization primitive.

## 28. Copy-on-Write Does Not Change Java Assignment

Copy-on-write (COW) is an internal strategy of a container or data structure: copying only when a mutation occurs via the API. For example, `CopyOnWriteArrayList` creates a copy of its internal array during mutating operations according to its contract.

However, `CopyOnWriteArrayList<String> b = a;` is still a **reference assignment**, not creating a second CopyOnWriteArrayList. COW describes **how an object performs mutations**, and does not change the semantics of the `=` operator.

Immutable persistent collections can also safely use structural sharing between versions, because the shared nodes are immutable.

## 29. Comparison Table

| Operation | New top-level object? | Can nested objects be shared? |
| --- | --- | --- |
| `b = a` | No | Everything is the same object |
| `b = new Box(a.value)` | Yes | Depends on passed fields |
| `b = new Box(a)` | Yes, if the copy constructor creates an object | Depends on implementation |
| `b = a.clone()` | Per clone contract, usually yes | Usually shallow |
| `int[] b = a.clone()` | New array | Independent primitive elements |
| `Member[] b = a.clone()` | New array | Same Member elements |
| `new ArrayList<>(a)` | New List | Same elements |
| `List.copyOf(a)` | Does not promise a new identity | Same elements |
| `Collections.unmodifiableList(a)` | Typical view wrapper | Live source data |
| `deepCopy(a)` | Per domain contract | Per graph policy |
| Immutable `withX(...)` | Per API | May share immutable internals |

Do not infer identity solely from the method name `copyOf`. `List.copyOf` may reuse an existing suitable unmodifiable list; read the contract.

## 30. Independence Tests Must Check Both Directions

Asserting only `copy != original` is not enough. You need to check:

1. Initial copied values are accurate.
2. Top-level identity is different if the contract requires it.
3. Nested mutable identity is different if deep isolation is promised.
4. Modifying the original does not change the copy.
5. Modifying the copy does not change the original.
6. Collection structure and elements follow the intended ownership policy.
7. Null/error behavior, cycles, aliases, subtypes, and invariants.
8. Consistent snapshot when the API promises concurrency safety.

### Runnable Program: Copy Contract Tests

Create **`CopyContractDemo.java`**:

~~~java
public class CopyContractDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address copy() {
            return new Address(city);
        }
    }

    static final class Person {
        String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person copy() {
            return new Person(name, address.copy());
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Mai", new Address("Hue"));
        Person copy = original.copy();

        check(original != copy, "same person");
        check(original.address != copy.address, "same address");

        original.address.city = "Da Nang";
        check(copy.address.city.equals("Hue"),
                "copy changed with source");

        copy.name = "An";
        check(original.name.equals("Mai"),
                "source changed with copy");

        System.out.println("identity PASS");
        System.out.println("nested isolation PASS");
        System.out.println("reverse isolation PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 CopyContractDemo.java
java CopyContractDemo
~~~

Stdout:

~~~text
identity PASS
nested isolation PASS
reverse isolation PASS
~~~

The test covers the Person→Address model and does not prove deep-copying of arbitrary resources/graphs. In large projects, use JUnit and shared contract tests across multiple implementations.

## 31. Exercise — Identity

~~~java
class Box { int value; }
Box a = new Box();
Box b = a;
Box c = new Box();
System.out.println(a == b);
System.out.println(a == c);
~~~

**Answer:**

~~~text
true
false
~~~

## 32. Exercise — Mutate and Reassign

~~~java
Box a = new Box();
a.value = 10;
Box b = a;
b.value = 20;
b = new Box();
b.value = 30;
System.out.println(a.value);
System.out.println(b.value);
~~~

**Answer:** Prints 20 and 30. Before reassignment, the two variables share the Box; after reassignment, b points to a different Box.

## 33. Exercise — Array Clone

~~~java
StringBuilder text = new StringBuilder("A");
StringBuilder[] a = {text};
StringBuilder[] b = a.clone();
b[0].append("B");
System.out.println(a[0]);
~~~

**Answer:** `AB`. Cloning the array does not clone the StringBuilder element.

## 34. Exercise — Parameter Passing

~~~java
static void replace(Box box) {
    box = new Box();
    box.value = 100;
}
~~~

The caller passes a Box with value=5. After `replace(box)`, the caller sees 5, because the method only reassigns the local parameter reference.

## 35. Exercise — List Copy

`new ArrayList<>(old)` creates a new List. Both Lists have elements of mutable type Member; does modifying a Member through copy affect old?

**Answer:** Yes, it can, if they hold the same Member reference. Modifying the List structure is independent; modifying the shared element state affects both.

## 36. Exercise — Immutable String

~~~java
String a = "Java";
String b = a;
a = "Kotlin";
System.out.println(b);
~~~

**Answer:** `Java`. The old String is immutable and b still references it.

## 37. Exercise — Deep-Copying a Graph with Cycles

Node A.next=B, B.next=A. Why can recursively copying next without a visited map fail?

**Answer:** A→B→A→B… continues infinitely and can throw `StackOverflowError`. You must record source→target by identity before copying edges.

## 38. Exercise — equals Does Not Prove an Independent Copy

Two Point records are created separately with equal components; equals is true and == is false. What does that prove?

**Answer:** The two objects have different identities yet are value-equal; it does not prove that any nested mutable objects (if present) have been deep-copied.

## 39. Common Mistakes

| Mistake | Fact |
| --- | --- |
| `b = a` creates a new object | Only copies the reference |
| Two variables are always two objects | They can be aliases |
| Assigning null destroys the object immediately | GC is based on reachability |
| Java passes objects by reference | Always pass-by-value |
| Reassigning a parameter changes the caller variable | No |
| `==` false means contents differ | Only identity differs |
| `equals` true proves a deep copy | No |
| A final reference makes the object immutable | No |
| Array clone deep-copies elements | Reference elements remain shared |
| `new ArrayList<>(source)` deep-copies | Only copies the structure |
| `List.copyOf` deep-copies elements | No |
| An unmodifiable view is a snapshot | It usually still reflects the source |
| Cloneable/Object.clone deep-copies automatically | Shallow by default |
| Copying a base class preserves subclass fields | Constructors are not polymorphic |
| Copying graph cycles needs no memoization | Needs an identity map |
| Deep copy automatically duplicates sockets/threads | There is no universal contract |
| Copying a mutable source concurrently is always consistent | Synchronization is needed |
| Immutable objects must be copied when shared | Sharing is usually safe |

## 40. End-of-Lesson Checklist

- [ ] I know that `b = a` only copies the reference value.
- [ ] I can distinguish between variables and object identity.
- [ ] I can draw an object graph with multiple aliases.
- [ ] I understand that modifying an object differs from reassigning a variable.
- [ ] I can distinguish between `==` and `equals`.
- [ ] I know that `new` creates a different top-level object.
- [ ] I understand Java pass-by-value for references.
- [ ] I know that field/array/list reference assignment also only shares the target.
- [ ] I can distinguish between shallow and deep copy.
- [ ] I know that primitive array clone separates primitive slots.
- [ ] I know that reference array clone still shares elements.
- [ ] I know that ArrayList copying only copies the structure.
- [ ] I understand how List.copyOf differs from an unmodifiable live view.
- [ ] I know that mutable elements must be snapshotted if isolation is needed.
- [ ] I do not think a final reference automatically clones the object.
- [ ] I know that immutable String/value objects can be shared safely.
- [ ] I understand Cloneable/Object.clone limitations.
- [ ] I know that copying a base class does not automatically preserve subtypes.
- [ ] I know that graph cycles require a visited identity map.
- [ ] I determine ownership and resource policy before copying.
- [ ] I know that concurrent snapshots require consistency design.
- [ ] I test independence from both the original and the copy.
- [ ] I can explain the stdout of the Java 17+ programs.

**Conclusion:** For reference types, **`b = a` only creates an alias, not an object copy**. A constructor, factory, or clone can create a new top-level object, yet the copy may still **share nested mutable references**. Shallow copy separates the outer layer; deep copy must follow a contract regarding the mutable object graph, aliases, cycles, and resources. For immutable values, sharing the same object is usually right and efficient. Draw the object graph, determine ownership, and test mutations on both sides before asserting that a copy is independent.
