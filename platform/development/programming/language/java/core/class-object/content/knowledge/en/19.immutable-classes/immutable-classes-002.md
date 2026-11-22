# Distinguishing `final` Classes, `final` Fields, and Immutable State in Java

In Java, the three ideas of **a class that prohibits inheritance**, **a field that prohibits reassignment**, and **an object whose state does not change** often appear together, yet they are **not synonymous**.

- `final class` **forbids creating subclasses** from that class.
- `final` placed on a field **forbids reassigning the field** after it has been validly initialized; for a reference field, it **does not lock the referenced object**.
- **Immutability** is a **contract on observable state**: once an object is completely constructed, normal application operations do not change the logical value that the object represents.

For example, `final List<String> names` can still have `names.add("An")` called on it if the reference points to a mutable `ArrayList`. Conversely, an object can be observably immutable even if the class is not declared `final` and its implementation uses an internal cache that does not alter its logical value.

This lesson belongs to **Java core - class-object**, in the **Immutable Classes** section. We will learn the exact rules of `final` in Java 17, contrast them with immutable state, distinguish between **shallow** and **deep immutability**, use defensive copying, design `withX`-style APIs, evaluate records and collections, avoid leaking mutable references, examine inheritance, and understand the limits of `final` regarding concurrency. All complete examples use Java **17+**, with `javac`/`java` commands, stdout, and solutions.

## 1. Three Different Questions

| Question | Tool/Concept | What Is Guaranteed |
| --- | --- | --- |
| Can this class be extended via `extends`? | `final class` | No valid subclass of that class can be declared |
| Can this field be assigned a different value/reference? | `final` field | It cannot be reassigned after a valid assignment under the definite assignment rules |
| Can this object change its logical state after creation? | Immutable design | There is no valid mutation path that alters the value promised by the API |
| Can this method be overridden by a subclass? | `final` method | That method cannot be overridden |
| Can a local variable/parameter be reassigned? | `final` local/parameter | The variable cannot be reassigned after being initialized according to language rules |

Do not conclude from the name of the `final` keyword that Java automatically enforces a "deep freeze" across the entire reference graph. Java **has no** mechanism to automatically freeze all objects pointed to by a `final` field.

An accurate example: `private final List<String> items = new ArrayList<>();` locks **the field's reference slot**, not the elements, length, or contents of the ArrayList.

## 2. `final class`: Prevents Inheritance, Not Mutation

Declaration:

~~~java
final class Meter {
    private int count;

    void increase() {
        count++;
    }

    int count() {
        return count;
    }
}
~~~

This is a **valid, mutable class**. No subclass is allowed to `extends Meter`, yet `increase()` still modifies `count`.

The following code intentionally **does not compile** if added to the same program:

~~~java
class ExtendedMeter extends Meter {
}
~~~

The compiler rejects it because `Meter` is `final`. This is an error in the **inheritance relationship**, not an error caused by wanting to modify the `count` field.

**Conclusion:** `final class` is a useful tool when designing an immutable class because it prevents subclasses from introducing behavior that breaks the contract, but **on its own it does not create immutable state**.

## 3. Complete Program 1 — A final class Still Changes State

Create the file **`FinalClassMutableDemo.java`**:

~~~java
final class Counter {
    private int value;

    Counter(int initial) {
        value = initial;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class FinalClassMutableDemo {
    public static void main(String[] args) {
        Counter counter = new Counter(3);

        System.out.println("before=" + counter.value());
        counter.increment();
        System.out.println("after=" + counter.value());
        System.out.println("runtime="
                + counter.getClass().getSimpleName());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FinalClassMutableDemo.java
java FinalClassMutableDemo
~~~

**Exact stdout:**

~~~text
before=3
after=4
runtime=Counter
~~~

The object still changes from 3 to 4. Neither the runtime class being named `Counter` nor the class being declared `final` affects the `increment()` method.

**Why use a final class for immutable design?** If a subclass were allowed to extend a value object, it could add mutable fields or override methods and make results hard for callers to predict. Disallowing subclassing is a **contract-protection strategy**, not a substitute for controlling fields and the API.

## 4. `final` Field: Locks Assignment, Not the Target Object

A `final` field can be a primitive or a reference.

~~~java
class Example {
    private final int id = 5;
    private final StringBuilder text =
            new StringBuilder("A");

    void append() {
        text.append("B");
    }

    String text() {
        return text.toString();
    }
}
~~~

This is a valid illustrative class. You cannot write `id = 7;` or `text = new StringBuilder();` in a normal method, but `text.append("B")` is **valid**.

For a primitive field: `final int id` does not change its value in the object through normal Java assignments after initialization.

For a reference field: `final StringBuilder text` always points to the **same StringBuilder** after initialization, yet that StringBuilder object **can still change its contents**.

**Rule to remember:** locking a reference does not mean locking the referenced object.

## 5. Complete Program 2 — A final Reference to a Mutable Object

Create the file **`FinalReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Notebook {
    private final List<String> tags = new ArrayList<>();
    private final StringBuilder title =
            new StringBuilder("Java");

    void addTag(String tag) {
        tags.add(tag);
    }

    void renameByAppending(String extra) {
        title.append(extra);
    }

    String title() {
        return title.toString();
    }

    List<String> tags() {
        return List.copyOf(tags);
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        Notebook notebook = new Notebook();

        System.out.println("before title=" + notebook.title());
        notebook.addTag("core");
        notebook.renameByAppending(" 17");

        System.out.println("after title=" + notebook.title());
        System.out.println("tags=" + notebook.tags());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

**Stdout:**

~~~text
before title=Java
after title=Java 17
tags=[core]
~~~

Both fields `tags` and `title` are final references, yet the `Notebook` object is **mutable**. `List.copyOf(tags)` only creates a read result that cannot be modified through the returned list; it does not turn the internal collection into immutable state at all. Notebook's methods still actively mutate the object.

Do not overlook the difference between **not exposing a setter for a field** and **having no mutation at all**. If the API has `addTag`, the object changes even without `setTags`.

## 6. How Is a `final` Field Initialized Properly?

A `final` field can be assigned via a **field initializer** or, if it is a **blank final instance field**, in a valid constructor according to the rules of *definite assignment*.

~~~java
final class ProductCode {
    private final String code;

    ProductCode(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code không hợp lệ");
        }
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

This is a valid illustrative class. The `code` field is assigned in the constructor after validation. For every constructor that completes normally, definite assignment rules require blank final fields to be validly assigned.

If a class has multiple constructors, **constructor chaining** can be used to centralize checks. A field that has already been validly assigned cannot be reassigned simply because it is inside a separate method.

**It does not mean** that `final` makes the compiler prove every business invariant. It only checks assignment rules; for example, a `final String code` field can still hold `null` if the constructor allows it.

## 7. Complete Program 3 — final Fields and Constructor Chaining

Create the file **`FinalInitializationDemo.java`**:

~~~java
final class Ticket {
    private final String code;
    private final int priority;

    Ticket(String code) {
        this(code, 1);
    }

    Ticket(String code, int priority) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code trống");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("priority ngoài 1..5");
        }
        this.code = code;
        this.priority = priority;
    }

    String describe() {
        return code + ":" + priority;
    }
}

public class FinalInitializationDemo {
    public static void main(String[] args) {
        Ticket standard = new Ticket("A");
        Ticket urgent = new Ticket("B", 5);

        System.out.println("standard=" + standard.describe());
        System.out.println("urgent=" + urgent.describe());

        try {
            new Ticket("C", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FinalInitializationDemo.java
java FinalInitializationDemo
~~~

**Stdout:**

~~~text
standard=A:1
urgent=B:5
reject=priority ngoài 1..5
~~~

The `code` and `priority` fields are assigned once in the constructor with validation. The one-parameter constructor calls `this(code, 1)` to reuse a single initialization flow without creating an extra object.

If the constructor throws an exception because of an invalid priority, the call `new Ticket("C",0)` does not return a valid object. This is validation designed by the developer, **not something automatically generated merely by the final keyword**.

## 8. `final` Local Variable, Parameter, and Method

The `final` keyword also has several other positions:

~~~java
class LocalRules {
    void print(final StringBuilder builder) {
        final int length = builder.length();
        builder.append("!");
        System.out.println(length + ":" + builder);
    }

    final void fixedOperation() {
        System.out.println("fixed");
    }
}
~~~

This is a valid illustrative class. The `builder` parameter cannot be **reassigned** to a different StringBuilder inside the method, yet the object it references can still have `append` called on it. The local variable `length` also cannot be reassigned after initialization.

`final void fixedOperation()` is a **final method**: subclasses are not allowed to override that method. It **does not assert that the method has no side effects** or that the object is not mutable.

Points to distinguish:

- `final class`: forbids subclassing.
- `final method`: forbids overriding.
- `final field`: forbids reassigning the field according to Java rules.
- `final local/parameter`: forbids reassigning the variable.
- **Immutable object**: guarantees behavior that does not alter logical state.

A final method can invoke code that modifies mutable fields; conversely, a non-final method can still cause no mutation at all.

## 9. Defining an Immutable Object at the API Level

An object is **immutable with respect to observable behavior** if, after complete construction, the logical state it represents **cannot be changed** by valid operations within the API's public contract.

For example, for a coordinate value `(x,y)`: the object may provide `x()`, `y()`, and `translate(dx,dy)`, but `translate` should **return a new object** instead of modifying `x/y` on the old object.

Immutability can be:

- **Shallow immutability:** direct fields cannot be reassigned, but mutable references may still be reachable.
- **Scoped deep immutability:** all mutable state owned by the object is isolated, and the API does not allow callers to modify it indirectly.
- **Logical/observational immutability:** the implementation may use an **internal cache** for optimization while the observable logical value does not change. The cache requires its own concurrency and safe publication design.

There is no single Java keyword meaning "this object graph is immutable". It is **the result of class design, input data, how references are stored, and the output API**.

## 10. Why Are All final Fields Not Enough for Deep Immutability?

Consider:

~~~java
final class UserGroup {
    private final java.util.List<String> members;

    UserGroup(java.util.List<String> members) {
        this.members = members;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

The class is final, the field is final, and there is no setter. Yet the constructor **directly retains** the list passed in by the caller, and the getter **returns that exact same list**. Callers can modify it through both the input and the getter.

This is a **representation exposure** bug (leaking the internal representation). The `final` field only forbids reassigning `members` to a different list; the list itself can still be modified.

One solution for `List<String>` is to create a snapshot `List.copyOf(members)` in the constructor, because `String` is immutable and the returned list does not allow callers to add or remove elements. With `List<MutableMember>`, copying only the list container is still not enough; you need to copy the elements or not expose a mutation API on the elements.

## 11. Complete Program 4 — Immutable `List<String>` Snapshot

Create the file **`ImmutableRosterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Roster {
    private final String teamName;
    private final List<String> members;

    Roster(String teamName, List<String> members) {
        if (teamName == null || teamName.isBlank()) {
            throw new IllegalArgumentException("teamName trống");
        }
        this.teamName = teamName;
        this.members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }

    String teamName() {
        return teamName;
    }

    List<String> members() {
        return members;
    }

    Roster withMember(String next) {
        Objects.requireNonNull(next, "next");
        List<String> updated = new ArrayList<>(members);
        updated.add(next);
        return new Roster(teamName, updated);
    }
}

public class ImmutableRosterDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Roster source = new Roster("Java", input);
        input.add("Bình");

        System.out.println("source=" + source.members());

        Roster updated = source.withMember("Chi");
        System.out.println("updated=" + updated.members());
        System.out.println("unchanged=" + source.members());
        System.out.println("team=" + updated.teamName());

        try {
            source.members().add("Dũng");
        } catch (UnsupportedOperationException ex) {
            System.out.println("readonly="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ImmutableRosterDemo.java
java ImmutableRosterDemo
~~~

**Stdout:**

~~~text
source=[An]
updated=[An, Chi]
unchanged=[An]
team=Java
readonly=UnsupportedOperationException
~~~

### Why Is Roster Immutable Within the Defined Scope?

1. The class is `final`, fields are `private final`, and there are no state-modifying methods.
2. The constructor **captures a snapshot** using `List.copyOf`, so calling `input.add("Bình")` afterward does not change source.
3. `List.copyOf` rejects null elements and returns a list that does not support mutation operations through its interface.
4. The team name and each member are `String`, which are themselves immutable.
5. `withMember` creates a new candidate list and **creates another Roster**, without modifying source.

These conditions are the result of a **combined** design, not just `final`. A final class that has `members.add(...)` in a public method is no longer immutable.

## 12. Defensive Copying Must Account for Both Input and Output

For mutable inputs such as `Date`, arrays, or `ArrayList`, there are two leak paths:

**Inbound:** the constructor retains the input reference; the caller still has the ability to modify the input object after the constructor finishes.

**Outbound:** the getter returns the internal mutable reference; the caller directly modifies the object used as the field.

Protection pattern:

~~~text
Mutable input
    |
    | constructor copies upon receipt
    v
Object's privately owned copy
    |
    | getter returns a snapshot/copy or a safe immutable view
    v
Output prevents callers from mutating internal state
~~~

If you only copy in the constructor while the getter returns the internal mutable object itself, callers can still modify it afterward. If you only copy in the getter while the constructor still retains the original mutable reference, callers can modify it through the reference they already held.

With a mutable element subtype, **shallow copying the outer list** does not protect against mutation of the elements. Always analyze ownership boundaries across the object graph.

## 13. `final Date` Is Still a Reference to a Mutable Object

`java.util.Date` has `setTime`, so `private final Date createdAt` **does not guarantee** that the timestamp inside the object will not be changed. If both the input and getter return/retain that same reference, callers can modify the state through either path.

In the following class example, both the constructor and the getter create a new `Date`:

~~~java
final class AuditStamp {
    private final java.util.Date createdAt;

    AuditStamp(java.util.Date source) {
        java.util.Objects.requireNonNull(source, "source");
        this.createdAt = new java.util.Date(source.getTime());
    }

    java.util.Date createdAt() {
        return new java.util.Date(createdAt.getTime());
    }
}
~~~

This is a **class declaration** without `main`. Counterexample: when passing `new Date(1000L)` and modifying the timestamp on the input variable or on the copy returned by the getter, the state of `AuditStamp` still represents the 1000-millisecond mark.

**Key takeaway from this `final` lesson:** the modifier only forbids reassigning the field and does not prevent mutation on the referenced object; you must examine all aliasing paths. The lesson **"Defensive Copying of Mutable Inputs and Outputs"** covers a runnable Date demo, defensive copy policies, and other mutable types. When appropriate, prefer immutable time types such as `java.time.Instant` to reduce the need for copying.

## 14. Unmodifiable Collections Differ from Immutable Object Graphs

It is necessary to distinguish:

- **Unmodifiable list view**: for example, `Collections.unmodifiableList(backing)` blocks `add/remove` operations through the view, yet **reflects changes** if code still retains and modifies `backing`.
- **Unmodifiable snapshot**: for example, `List.copyOf(backing)` creates a list of values at the time of the call with an unmodifiable contract (given valid input). It does not necessarily always create a new container identity when the source is already unmodifiable.
- **Deeply immutable data**: the contained elements are themselves immutable values, or mutable state is completely isolated.

If `List.copyOf` receives a `List<StringBuilder>`, callers **cannot add/remove** through the resulting list, yet they can still call `list.get(0).append(...)`. There is no deep copy of the StringBuilder.

`Map.copyOf` and `Set.copyOf` have similar semantics at the collection level; mutable keys/values/elements still require their own strategy. `Map.copyOf` also disallows null keys/values. Do not equate an "immutable wrapper" with "every object inside is frozen".

## 15. Complete Program 6 — Live View and Snapshot

Create the file **`ListViewSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListViewSnapshotDemo {
    public static void main(String[] args) {
        List<String> backing = new ArrayList<>();
        backing.add("A");

        List<String> view =
                Collections.unmodifiableList(backing);
        List<String> snapshot = List.copyOf(backing);

        backing.add("B");
        System.out.println("backing=" + backing);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view add rejected");
        }

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add rejected");
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ListViewSnapshotDemo.java
java ListViewSnapshotDemo
~~~

**Stdout:**

~~~text
backing=[A, B]
view=[A, B]
snapshot=[A]
view add rejected
snapshot add rejected
~~~

Both returned lists disallow `add` through that API, yet `view` still **observes the backing list** as it changes, whereas snapshot retains the values captured before B was added.

Therefore, a getter returning `Collections.unmodifiableList(internalList)` is **not necessarily** an immutable API if the object itself still has a method that modifies internalList or some caller still holds the backing list.

## 16. `final List<MutableElement>`: The Problem of Shallow Element Copying

Suppose `Order` contains a `List<Line>`, where `Line` has a `setQuantity` method. A constructor performing `List.copyOf(lines)` will forbid adding/removing through the internal list, yet it **does not separate the Line objects** from the caller.

This creates an indirect mutation path:

~~~text
Caller creates Line L1, quantity=2
Caller passes [L1] into Order
Order stores List.copyOf(...)
Caller still retains L1
Caller calls L1.setQuantity(9)
Order now observes quantity=9
~~~

If the API promises that Order is immutable including the quantity on each line, it must copy each Line into an immutable value, or copy each Line upon receipt **and** upon return, without granting mutation access to internal Lines.

A semantically meaningful deep copy must define which part of the object graph is owned. Not every external object that is a shared dependency should be copied; however, mutable data belonging to the logical state of an immutable aggregate needs to be protected.

## 17. Complete Program 7 — Immutable Order with Element Snapshots

Create the file **`ImmutableOrderDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class MutableLine {
    private final String sku;
    private int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku");
        setQuantity(quantity);
    }

    MutableLine(MutableLine other) {
        this(other.sku, other.quantity);
    }

    String sku() {
        return sku;
    }

    int quantity() {
        return quantity;
    }

    void setQuantity(int next) {
        if (next < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
        quantity = next;
    }
}

final class OrderSnapshot {
    private final List<MutableLine> lines;

    OrderSnapshot(List<MutableLine> input) {
        Objects.requireNonNull(input, "input");
        List<MutableLine> copied = new ArrayList<>();
        for (MutableLine line : input) {
            copied.add(new MutableLine(
                    Objects.requireNonNull(line, "line")));
        }
        lines = List.copyOf(copied);
    }

    List<MutableLine> lines() {
        List<MutableLine> copied = new ArrayList<>();
        for (MutableLine line : lines) {
            copied.add(new MutableLine(line));
        }
        return List.copyOf(copied);
    }

    int totalQuantity() {
        int total = 0;
        for (MutableLine line : lines) {
            total += line.quantity();
        }
        return total;
    }
}

public class ImmutableOrderDemo {
    public static void main(String[] args) {
        MutableLine inputLine = new MutableLine("P1", 2);
        List<MutableLine> input = new ArrayList<>();
        input.add(inputLine);

        OrderSnapshot order = new OrderSnapshot(input);
        inputLine.setQuantity(9);
        input.add(new MutableLine("P2", 5));

        System.out.println("order total="
                + order.totalQuantity());
        System.out.println("input size=" + input.size());

        MutableLine outputLine = order.lines().get(0);
        outputLine.setQuantity(100);

        System.out.println("output qty="
                + outputLine.quantity());
        System.out.println("order after output change="
                + order.totalQuantity());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ImmutableOrderDemo.java
java ImmutableOrderDemo
~~~

**Exact stdout:**

~~~text
order total=2
input size=2
output qty=100
order after output change=2
~~~

### Why Is Copying Needed in Both Directions?

`MutableLine` has `setQuantity`, so a reference to an internal line grants permission to modify its quantity. `OrderSnapshot` copies each line in the constructor so that modifying `inputLine` does not affect the stored object. The `lines()` getter in turn returns a list containing **new copies** of each line; modifying `outputLine` also does not affect OrderSnapshot.

This approach incurs additional allocation and copying overhead. If it is possible to replace `MutableLine` with a `record Line(String sku, int quantity)` that has validation and retains no mutable references, only a single list snapshot is needed, making the design simpler. Choosing immutable data types from the start is usually more effective than continually defending a mutable type.

## 18. Java 17 Records: Components Are final, Yet Immutability Is Only Shallow

A record such as:

~~~java
record UserTags(java.util.List<String> tags) {
}
~~~

has its associated members generated by Java, stores the `tags` component in a private final field, and provides the `tags()` accessor. However, **a record by default does not automatically defensive-copy an `ArrayList` passed in by the caller**.

Therefore, the `record` syntax itself **does not guarantee deep immutability**. If a component is a mutable reference, callers can still modify its contents through the original reference or the accessor if the implementation does not protect it.

You can write a **compact canonical constructor** in a record:

~~~java
record SafeTags(java.util.List<String> tags) {
    SafeTags {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

In Java 17, the `tags` parameter in the compact constructor can be normalized or passed through a defensive copy before Java performs the implicit assignment to the record component field. For `List<String>`, because String is immutable, an immutable list snapshot provides immutable state with respect to its elements.

If a record contains a `Date`, an array, or a `List<MutableLine>`, it must be analyzed and copied separately, and the accessor may even need to be overridden to avoid exposing mutable internal state.

## 19. Complete Program 8 — Shallow Record and Safe Record

Create the file **`RecordImmutabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record LooseTags(List<String> tags) {
}

record SafeTags(List<String> tags) {
    SafeTags {
        tags = List.copyOf(tags);
    }
}

public class RecordImmutabilityDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("A");

        LooseTags loose = new LooseTags(input);
        SafeTags safe = new SafeTags(input);

        input.add("B");

        System.out.println("loose=" + loose.tags());
        System.out.println("safe=" + safe.tags());

        try {
            safe.tags().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("safe rejects add");
        }
        System.out.println("safe after=" + safe.tags());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 RecordImmutabilityDemo.java
java RecordImmutabilityDemo
~~~

**Stdout:**

~~~text
loose=[A, B]
safe=[A]
safe rejects add
safe after=[A]
~~~

In `LooseTags`, Java generates a final `tags` field, yet the field retains the same original mutable list. In `SafeTags`, the compact constructor copies the list before storing it, so subsequent changes to `input` do not alter the safe record.

Records are well suited for **value carriers** with immutable data; however, the immutability of the **component types** remains a more decisive factor than the `record` keyword.

## 20. When Every Field Is final Yet the Class Is Still Mutable: Arrays, Builders, and Caches

Three cases that are easy to overlook:

**Arrays:** `private final int[] scores` retains the same array reference, yet `scores[0] = ...` is still valid inside a method. The constructor must copy the array upon receipt, and the getter must also clone/copy it upon return if immutability is required.

**Builders:** `private final StringBuilder title` does not turn a StringBuilder into a String. For immutable state, storing the finalized `String` is usually easier.

**Caches:** an object can hold a mutable internal cache (for example, a precomputed value) without users **seeing any change in logical value**. This is *observational immutability*, though thread-safety of the cache must use an appropriate mechanism and the cache must not make public behavior depend on update order in a way that violates the contract.

You should not infer that "an object with any internal mutable field cannot be logically immutable". Evaluate the **observable logical state** and reference exposure paths instead. However, for learners new to Java Core, designing all state to be explicitly immutable is easier to verify than designing a complex lazy cache.

## 21. Complete Program 9 — Cloning an Array in Constructor and Getter

Create the file **`ImmutableScoresDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

final class ScoreCard {
    private final int[] scores;

    ScoreCard(int[] input) {
        this.scores = Objects.requireNonNull(
                input, "input").clone();
    }

    int scoreAt(int index) {
        return scores[index];
    }

    int[] scores() {
        return scores.clone();
    }

    @Override
    public String toString() {
        return Arrays.toString(scores);
    }
}

public class ImmutableScoresDemo {
    public static void main(String[] args) {
        int[] input = {7, 8};
        ScoreCard card = new ScoreCard(input);

        input[0] = 99;
        int[] output = card.scores();
        output[1] = 100;

        System.out.println("card=" + card);
        System.out.println("first=" + card.scoreAt(0));
        System.out.println("output="
                + Arrays.toString(output));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ImmutableScoresDemo.java
java ImmutableScoresDemo
~~~

**Stdout:**

~~~text
card=[7, 8]
first=7
output=[7, 100]
~~~

Because `int[]` holds primitive values, `clone()` creates a new array container and independent elements. This is sufficient for a **one-dimensional primitive array**. With `StringBuilder[]`, clone only creates a new array while still sharing the StringBuilder elements; with `int[][]`, cloning the outer array **does not copy the rows**.

Therefore, one should not teach that "using `array.clone()` always makes a class deeply immutable". You must examine component types and the depth of the object graph.

## 22. Immutable Values and `withX` Methods

An immutable object does not have a `setX` method that mutates the object itself. When a different value is needed, you can design `withX` to create a new object.

Create the file **`ImmutablePointDemo.java`**:

~~~java
import java.util.Objects;

public final class ImmutablePointDemo {
    private final int x;
    private final int y;
    private final String label;

    public ImmutablePointDemo(int x, int y, String label) {
        this.x = x;
        this.y = y;
        this.label = Objects.requireNonNull(label, "label");
    }

    public ImmutablePointDemo moveBy(int dx, int dy) {
        return new ImmutablePointDemo(x + dx, y + dy, label);
    }

    public ImmutablePointDemo withLabel(String next) {
        return new ImmutablePointDemo(x, y,
                Objects.requireNonNull(next, "next"));
    }

    @Override
    public String toString() {
        return label + "(" + x + "," + y + ")";
    }

    public static void main(String[] args) {
        ImmutablePointDemo source =
                new ImmutablePointDemo(2, 3, "A");
        ImmutablePointDemo moved = source.moveBy(5, -1);
        ImmutablePointDemo renamed = moved.withLabel("B");

        System.out.println("source=" + source);
        System.out.println("moved=" + moved);
        System.out.println("renamed=" + renamed);
        System.out.println("same object=" + (source == moved));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ImmutablePointDemo.java
java ImmutablePointDemo
~~~

**Stdout:**

~~~text
source=A(2,3)
moved=A(7,2)
renamed=B(7,2)
same object=false
~~~

Each operation creates a new instance validated by the constructor. The original object does not change, so callers can hold multiple versions to compare, undo, or share without worrying about two places modifying the same value object.

**Trade-off:** creating new objects has a cost. However, for small objects and immutable data used as values, the clear benefits for APIs, testing, and concurrency are often worthwhile; performance optimization should be based on actual profiling rather than defaulting to mutable first.

## 23. Immutability and equality/hashCode

For a value object, `equals/hashCode` is usually based on **logical value**. If the fields used to compute the hash can change after the object has been added to a `HashSet` or used as a `HashMap` key, the collection may fail to locate the object after mutation.

Immutable value objects make the equality contract easier to uphold:

- Fields participating in `equals/hashCode` do not change.
- The hash can be cached appropriately if needed, while avoiding concurrency bugs.
- Values with the same content can be considered equal even if `==` is false.
- There is no need to use `System.identityHashCode()` as a business identifier.

Records containing immutable components generally receive useful generated `equals/hashCode`, but **a record containing an array** requires attention: default array equality is based on identity when used as a component under the generated comparison; a record does not automatically deep-compare array contents in a business-semantic sense.

Do not infer from `final class` that Java automatically generates value-based `equals`: an ordinary final class still inherits `Object.equals` if it does not override it.

## 24. `static final`: Reference Constants Are Not Necessarily Immutable

The `static final` keywords are often used for constants:

~~~java
static final int MAX_RETRIES = 3;
static final String DEFAULT_NAME = "guest";
~~~

The two declarations above (when placed in a class) are **constant variables** if their initializers are appropriate constant expressions.

However:

~~~java
static final java.util.List<String> USERS =
        new java.util.ArrayList<>();
~~~

is only a **static final reference field**. Code with access to `USERS` can still call `USERS.add("An")`. The static keyword does not change the semantics of final at the level of the referenced mutable object.

For global data, **mutable static shared state** can cause concurrency risks and test interference. If the goal is an unmodifiable set of constants, use `List.of(...)`, `Set.of(...)`, or `Map.of(...)` with appropriate immutable elements/values.

## 25. Complete Program 10 — static final Reference with Mutable Data

Create the file **`StaticFinalCollectionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class AppState {
    static final List<String> EVENTS = new ArrayList<>();
    static final List<String> DEFAULT_ROLES =
            List.of("reader", "writer");

    private AppState() {
    }
}

public class StaticFinalCollectionDemo {
    public static void main(String[] args) {
        AppState.EVENTS.add("startup");
        AppState.EVENTS.add("login");

        System.out.println("events=" + AppState.EVENTS);
        System.out.println("roles=" + AppState.DEFAULT_ROLES);

        try {
            AppState.DEFAULT_ROLES.add("admin");
        } catch (UnsupportedOperationException ex) {
            System.out.println("roles cannot add");
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StaticFinalCollectionDemo.java
java StaticFinalCollectionDemo
~~~

**Stdout:**

~~~text
events=[startup, login]
roles=[reader, writer]
roles cannot add
~~~

`EVENTS` is a final reference, yet the target list is mutable. `DEFAULT_ROLES` is also a final reference, but the object created by `List.of` does not support structural modification. Because the `String` values are immutable, the roles list is suitable as immutable data.

If you use `List.of(new MutableProfile(...))`, the list does not allow adding/removing, yet the profile can still change; again, element immutability must be considered. **`static final` does not replace the collection type and child object contracts**.

## 26. A `final class` Can Inherit Mutable State from a Superclass

A class marked `final` can still **extend another superclass**. `final` only prevents **others from extending that class itself**; it does not alter inherited code.

Create the file **`FinalSubclassStillMutableDemo.java`**:

~~~java
class MutableBase {
    private int value;

    MutableBase(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

final class FinishedCounter extends MutableBase {
    FinishedCounter(int initial) {
        super(initial);
    }
}

public class FinalSubclassStillMutableDemo {
    public static void main(String[] args) {
        FinishedCounter counter = new FinishedCounter(10);
        System.out.println("before=" + counter.value());
        counter.increment();
        System.out.println("after=" + counter.value());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FinalSubclassStillMutableDemo.java
java FinalSubclassStillMutableDemo
~~~

**Stdout:**

~~~text
before=10
after=11
~~~

`FinishedCounter` cannot be subclassed further, yet it inherited the `increment()` method from `MutableBase`. Therefore, it is still mutable. When evaluating whether a class is immutable, examine **all inherited behavior**, not just fields declared in the final class.

## 27. Can a Non-final Class Have Immutable Objects?

Yes. Immutability is not defined by Java as **requiring** the `final` keyword. A non-final class that provides no mutation API and leaks no state can still produce immutable instances.

However, if arbitrary subclassing is permitted, code using a base reference **cannot assume by default that every subclass will uphold the same contract**. A subclass could add mutable state or override a method so that observable behavior depends on new state.

Some designs that require subclassing while preserving immutable behavior can:

- Place critical invariants in `final` methods.
- Use `private` fields and defensive copies.
- Define a superclass contract strong enough for subclasses.
- Use a **sealed hierarchy** (Java 17) to restrict the set of subclasses when appropriate, though sealed also **does not guarantee immutability by itself**.
- Prefer `final` value types when inheritance is not needed.

**Do not equate "non-final class" with "every instance is mutable".** This is a question of type contracts and extensibility, not a simple check on a keyword.

## 28. Concurrency: Immutability Helps Sharing, final Fields Do Not Solve Every Race

A fully initialized and safely published immutable object is usually **easy to share across threads**: multiple threads only read the logical value without competing to update the same state.

The Java Memory Model also defines **special semantics for final fields**: if an object is properly constructed (without letting `this` escape during the constructor), other threads receive initialization safety guarantees for final fields according to JLS §17.5.

However, do not over-extrapolate:

- `final List<String> list` can still point to a **mutable ArrayList** and be modified concurrently; final does not make `add` thread-safe.
- A `final` field does not automatically make other mutable fields in the class synchronized.
- Holding a reference to an immutable object does not make **a mutable variable holding that reference** update atomically according to application intent.
- A collection of immutable elements can still be a **mutable** collection and require synchronization if multiple threads modify that collection.
- Lazy caches and concurrency-dependent resources still need their own visibility/atomicity design.
- "Immutable object" does not mean "every operation across the entire system is race-free".

Avoid publishing `this` from a constructor to a listener, static registry, or another thread before object initialization is complete. This is also a key principle for preserving the semantics of final-field initialization.

## 29. Mutable Builder + Immutable Snapshot: Separation of Roles

A useful pattern is to use a **mutable builder during the construction phase**, and then publish an **immutable snapshot**.

Example workflow:

~~~text
Receive input data
    |
    v
Builder has permission to add/modify/remove within construction scope
    |
    v
Validate invariants, reject/normalize invalid data
    |
    v
Create immutable object with defensive copies
    |
    v
Consuming APIs only read or create new snapshots
~~~

This is a way to combine **convenience during construction** and **safety during use**. However, you must ensure that the builder and the immutable result **do not unintentionally share mutable references**. If `build()` simply passes an `ArrayList` still held by the builder directly, the builder could mutate the already "packaged" object.

Not every application needs a builder. With few fields, a constructor or static factory with validation is sufficient. A builder is useful when there are many optional parameters and assembling data requires multiple steps.

## 30. Complete Program 11 — Builder Does Not Alter an Already Created Snapshot

Create the file **`BuilderSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Palette(List<String> colors) {
    Palette {
        colors = List.copyOf(colors);
    }
}

final class PaletteBuilder {
    private final List<String> colors = new ArrayList<>();

    PaletteBuilder add(String color) {
        colors.add(Objects.requireNonNull(color, "color"));
        return this;
    }

    Palette build() {
        return new Palette(colors);
    }
}

public class BuilderSnapshotDemo {
    public static void main(String[] args) {
        PaletteBuilder builder = new PaletteBuilder();
        builder.add("red");

        Palette first = builder.build();
        builder.add("blue");
        Palette second = builder.build();

        System.out.println("first=" + first.colors());
        System.out.println("second=" + second.colors());
        System.out.println("different="
                + (first != second));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BuilderSnapshotDemo.java
java BuilderSnapshotDemo
~~~

**Stdout:**

~~~text
first=[red]
second=[red, blue]
different=true
~~~

Each call to `build()` invokes the canonical constructor of the `Palette` record; the constructor uses `List.copyOf` to keep an unmodifiable snapshot. Therefore, modifying the builder after creating first does not affect first.

If the record only wrote `record Palette(List<String> colors) {}` without copying, the two objects could **share the mutable list** of the builder, breaking the snapshot expectation.

## 31. Immutable Objects with Business Invariants

Immutability is valuable because an object **protects its own contract**: no operation can skew its already validated state. For instance, a `Money` value object might require:

- A valid, non-null currency.
- The monetary amount in the correct scale/unit.
- Rejecting unrepresentable values.
- The `add` operation checking that both values share the same currency before returning a new instance.
- Fields initialized once, without exposing a mutable representation.
- Value-based `equals/hashCode` if that is the appropriate contract.

A `final` class with `final BigDecimal amount` is not enough if the constructor does not validate the currency and normalize according to the published business rules. **Immutability and validity are two distinct criteria**, even though immutable design helps preserve validity after the object is created.

Similarly, an immutable `OrderSummary` keeps `items` unmodifiable yet could still contain invalid data due to bad input. Validation is needed, not just `final`.

## 32. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "`final class` means every field cannot change." | A final class only forbids extends | Examine all mutable fields/methods |
| "A `final` field reference points to an immutable object." | Final only forbids reassigning the reference | Choose an immutable target / defensive copy |
| "No setters means immutable." | Inputs/getters can leak mutable references | Perform defensive copying in both directions |
| "Every field is final so the class is immutable." | List, Date, array, and builder can be mutable | Examine the state of the entire owned object graph |
| "An unmodifiable view is an immutable snapshot." | The view reflects changes to the backing list | Use a true snapshot when needed |
| "`List.copyOf` deep-copies elements." | Shallow copy at the collection level | Use immutable elements / copy elements |
| "`record` is always deeply immutable." | A record only locks component references itself | Use a compact constructor and safe accessors |
| "`final int[] scores` prevents modifying elements." | The array still allows mutation | Clone on both input and output |
| "A final method has no side effects." | A final method only forbids overriding | Design logic without mutation |
| "A static final list is a data constant." | A final reference can still have a mutable target | `List.of` and immutable values |
| "A final subclass is definitely immutable." | It still inherits mutable methods | Check the superclass |
| "Every non-final class is always mutable." | Not a required definition | Evaluate the observable contract |
| "Immutable objects need no validation." | Immutability differs from validity | Validate in the constructor/factory |
| "Final fields automatically make an ArrayList thread-safe." | Thread safety depends on the mutable target | Immutable snapshot / synchronization |
| "An immutable object cannot have any internal cache." | Logical immutability may have a cache | Ensure observable values do not change and handle concurrency |
| "`withX` should mutate `this` and return it." | Violates the immutable value contract | Return a newly validated instance |

## 33. Process for Designing an Immutable Class

1. **Define the logical value** that the object represents, including business invariants and which data falls under ownership.
2. Decide whether subclassing is needed. If not, consider a **`final class`** or a record with safe components.
3. Make state-representing fields `private` and choose `final` where appropriate.
4. **Validate constructor parameters** before creating a complete object.
5. **Copy mutable inputs** before storing them; do not keep aliases to collections, Dates, arrays, or mutable elements that are not permitted to be shared.
6. **Do not expose internal mutable references** through getters, callbacks, listeners, or helper methods.
7. Instead of setters, provide operations that **return a new value** such as `withName`, `moveBy`, and `withStatus`.
8. For collections, distinguish between an unmodifiable **view**, a snapshot, and deep/shallow copying. Use immutable elements when possible.
9. For records, review the canonical/compact constructor and accessors if any component holds a mutable reference.
10. If using a lazy cache, ensure it does not alter the logical value and is handled safely for concurrency.
11. Do not let `this` escape early from the constructor.
12. Implement `equals/hashCode` matching value semantics and ensure participating fields do not change.
13. **Test mutation isolation** from both inputs and output getters.
14. Test that update methods do not modify the original object.
15. If inheritance is present, inspect all inherited APIs that could cause mutation.
16. If multiple threads are involved, analyze safe publication and mutable dependencies separately.

## 34. Practice Exercises

**Exercise 1.** `final class Counter` has `int count` and `increment()`. Is Counter immutable? Why?

**Exercise 2.** Does `private final ArrayList<String> names` forbid `names.add("An")`? Which statement is blocked by `final`?

**Exercise 3.** Does `final StringBuilder buffer` make `buffer.append("!")` invalid?

**Exercise 4.** For a blank final field `private final String id;`, what must the constructor guarantee on every normal completion path?

**Exercise 5.** What does `final void save()` forbid? Does it automatically prevent `save()` from modifying mutable fields?

**Exercise 6.** A class is final, all fields are final, and the constructor directly stores a mutable `List<String>` passed in by the caller. Is deep immutability guaranteed yet?

**Exercise 7.** Why does using only `Collections.unmodifiableList(backing)` not necessarily create an immutable snapshot?

**Exercise 8.** Does `List.copyOf(List<MutableLine>)` deep-copy `MutableLine`? If not, what additional step is needed?

**Exercise 9.** `Date` is mutable. What must a class storing a Date do in its constructor and getter if it wants to be immutable?

**Exercise 10.** Does `final int[] values` prevent `values[0] = 5`? What happens if the array itself is returned through a getter?

**Exercise 11.** Does `record Box(List<String> values) {}` automatically defensive-copy the List? How can a compact constructor be used?

**Exercise 12.** Why is `List.of("a")` safe for String elements, whereas `List.of(new StringBuilder("a"))` does not make the StringBuilder immutable?

**Exercise 13.** Does `static final List<String> shared = new ArrayList<>()` guarantee that the data does not change?

**Exercise 14.** A `final class Child extends MutableParent` inherits `increment()`. Is Child automatically immutable?

**Exercise 15.** What should `withLabel("new")` in an immutable value object return, and what should it do to the original object?

**Exercise 16.** Why are immutable types generally easier to use as HashMap keys than mutable objects with a state-dependent `hashCode()`?

**Exercise 17.** What do final fields in an object help with under the Java Memory Model? Why are they insufficient to make a mutable ArrayList thread-safe?

**Exercise 18.** A record contains `List<MutableItem>`, and its constructor uses `List.copyOf`. The caller still retains the MutableItem instances. Can the record's logical state be modified?

**Exercise 19.** If an immutable object has an internal computed cache updated lazily, does that necessarily violate behavioral immutability? What conditions must be upheld?

**Exercise 20.** A builder creates an immutable snapshot via `new Snapshot(builder.list)`, yet the constructor stores the list directly. After `build`, the builder continues adding data. What is the consequence?

### Answers and Explanations

1. No; a final class only forbids subclassing, and methods still modify `count`.
2. It does not forbid add; final forbids reassigning the `names` field to a different reference.
3. No; `append` mutates the target object rather than reassigning the reference variable.
4. The blank final field must be validly assigned according to definite assignment before the constructor completes normally.
5. It forbids subclasses from overriding the method; a final method can still cause side effects.
6. Not yet. The caller can retain the list reference and modify it; an inbound defensive copy is needed.
7. Because it is a live view that reflects changes in the backing list.
8. No. You must copy the elements or convert them into immutable values and protect outbound references.
9. Copy the Date upon receipt and copy it upon return, or use an immutable time type such as Instant.
10. No; array elements are mutable. Returning the internal array to the caller can allow the caller to modify state; clone upon receipt and return.
11. No. A compact constructor can execute `values = List.copyOf(values)` before the record stores the component.
12. The list disallows add/remove, yet a mutable element object can still have content-modifying methods called on it; String is immutable.
13. No. Static final only locks the reference; the ArrayList remains mutable and also introduces concurrency issues.
14. No; Child can still use the inherited mutator.
15. Create a new object with the new label, leaving the original object's state unchanged.
16. The fields used for equality/hash remain stable, avoiding the bug of losing track of keys when mutable state changes.
17. They provide appropriate initialization safety guarantees when constructed properly; they do not automatically guarantee atomicity/visibility for subsequent mutations on a collection.
18. Possibly yes; List.copyOf retains the element references, so if the caller mutates those elements, the logical value can change.
19. Not necessarily, if the cache does not change the observable logical result and is managed properly for concurrency.
20. The snapshot is aliased to the builder's list, so later builder changes alter the resulting object; the constructor must create its own snapshot.

## 35. Official Java 17 References

- [JLS 17 §8.1.1.2 — final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): final classes and subclassing restrictions.
- [JLS 17 §8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final field rules.
- [JLS 17 §8.4.3.3 — final Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.3): final methods and overriding.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final variables and constant variables.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): blank final fields and definite assignment.
- [JLS 17 §17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): final fields in the Java Memory Model.
- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components, compact constructors, and record properties.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshots and limits regarding elements.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable views reflecting the backing collection.
- [Java SE 17 — List.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of(E...)): creating lists that do not support direct modification.
- [Java SE 17 — Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html): an example of a mutable reference type.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): an immutable time type.
- [Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): null checks.
- [Java SE 17 — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): superclass of record classes.

**Conclusion:** `final class` only **prevents inheritance**, and `final field` only **prevents reassigning the field** after proper initialization. **Immutable state** demands a deeper contract: validation, no mutators that alter the logical value, defensive copies at every mutable ownership boundary, and preventing callers from modifying state through collections, arrays, or child objects. Records and `List.copyOf` are very useful, yet provide only **shallow** immutability if their components or elements remain mutable. Design immutability based on data semantics and reference paths, not by guessing from the presence of the `final` keyword.
