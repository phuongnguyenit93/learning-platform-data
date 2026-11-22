# Choosing a Mutable Class, Immutable Class, Record, or Enum — Java 17

## 1. Goal of the Design Decision

When representing a business concept in Java, we should not choose `class`, `record`, or `enum` simply because of which syntax is shorter. The more important question is **whether the object represents an identity with a lifecycle and changing behavior, a stable value, a finite set of values, or a combination of multiple variants**.

In Java 17, the typical options are:

1. **Mutable class**: the internal state of an instance can be updated over the object's lifecycle, for example a shopping cart, counter, session, or business aggregate with state changes.
2. **Immutable class**: once validly initialized, its observable state does not change; when a new value is needed, a new object is created, for example money, date range, coordinates, or configuration snapshot.
3. **`record`**: concise syntax for a **data carrier** with a defined set of components and constructor/accessors/`equals`/`hashCode`/`toString` based on component state; a record itself **does not automatically guarantee deep immutability**.
4. **`enum`**: describes a **predefined set of constants** with singleton identity for each enum constant within the same class loader, for example finite statuses, payment methods with a fixed list, or compass directions.

This lesson focuses on **how to choose**, not just listing syntax. After this lesson, you will be able to answer:

- When is a mutable class reasonable, and when does it make testing/concurrency difficult?
- When do you need to write an immutable class yourself instead of using a record?
- Why does `record` only provide "shallow" immutability by reference, and how do you perform a defensive copy?
- Why is `enum` suitable for a **finite, stable** set rather than dynamic data from a database?
- When do you need to add a static factory, builder, or sealed interface alongside record/enum variants?
- How do identity equality (`==`), value equality (`equals`), hashing, API compatibility, serialization, and ORM affect the choice?
- How do you design resource-owning objects, mutable entities, immutable snapshots, and status constants?

The programs below are **standalone Java 17**: each example has a file name matching its public class, a `javac --release 17` command, and stdout output; intentionally incorrect fragments are clearly marked **compile-negative** or **snippet**.

## 2. A Ready-to-Use Decision Tree

Start with the question **"Is this a fixed set of symbols defined by the source code?"**

- **Yes** → consider **`enum`**. For example `Direction.NORTH`, `OrderStatus.PAID`. An enum constant does not represent each individual order.
- **No** → ask **"Do we need to keep the same object identity while the state changes?"**
  - **Yes** → consider a **mutable class** with clear invariants and ownership. For example, an account with a changing balance, or an entity with its own ID.
  - **No** → ask **"Is this a value bundle with a simple schema, defined components, and equality based on those components?"**
    - **Yes** → consider **`record`**, while checking whether the components are truly immutable/snapshots.
    - **No, or need control over representation/field layout/inheritance/a different API** → consider a hand-written **immutable class**.
- If there are **multiple value forms with different structures** (for example, a successful payment contains a receipt, while a failed one contains a reason) → consider a **sealed interface + final record/class variants**, instead of forcing everything into an enum.

This is a heuristic, not a mandatory rule. A **mutable class can be value-oriented**, an immutable class might not override `equals`, a record can contain mutable fields, and an enum can declare its own mutable state (though that should usually be avoided). Examine the actual contract.

## 3. Key Comparison Table

| Characteristic | Mutable class | Immutable class | `record` | `enum` |
| --- | --- | --- | --- | --- |
| Object state changes after creation | Yes, via the API | No, if designed properly | Component fields are final; **referent may be mutable** | Usually designed as immutable; the language does not inherently forbid mutable instance fields |
| Definition syntax | `class` | `final class` is common | `record Name(...)` | `enum Name { ... }` |
| Constructors | Any valid constructor | Usually validate + defensive copy | Canonical constructor and overload delegation | Internal enum constructors, no `new` from clients |
| Accessors | Hand-written | Hand-written | Auto-generated named `component()` | Hand-written if needed |
| `equals/hashCode/toString` | Usually custom-defined or inherited from `Object` | Hand-written if value equality is needed | Auto-generated from component state, can be overridden subject to Java's conditions | `equals` uses constant identity; `==` is appropriate |
| Inheritance | Yes, if not final | Usually final to preserve invariants | Implicitly final, extends `Record` | Cannot extend other classes; `Enum` base |
| Number of instances | Depends on `new`/factories | Depends on `new`/factories | Depends on `new`/factories | Predefined constants, no runtime constants added |
| Well-suited for | Lifecycle, entities, state machine holders | Money/value objects, snapshots | DTO/value tuple, API responses | Fixed options/states/categories |
| Typical risks | Side effects, aliasing, concurrency | Incorrect defensive copies and boilerplate | Mistaking for deep immutability, array equality | Persistent use of ordinals, mutable enum state, changing constants causes API breaks |

**Note:** "immutable class" is a **semantic design**, not a Java keyword. Meanwhile, `record` and `enum` are syntactic constructs of the language, yet they do not guarantee that all referent contents are immutable.

## 4. Identity or Value?

Two different questions:

- **Is this *that exact same instance*?** Use identity (`==` on references) or an explicit business ID.
- **Do two instances have the same value?** Use `equals` according to appropriate value semantics.

Examples:

- Two `Customer` objects with the same name can still be **two different customers** (different business identity).
- Two `Point(2,3)` objects should generally be considered **the same coordinate value**, even if they are two instances.
- Two `Status.ACTIVE` enum constants have fixed identity within the enum type, so `==` is appropriate.
- Two mutable carts with the same items at a given moment are not necessarily the same business cart.

**Do not choose a record just because "you want a class with data"** if equality is based on ID rather than on all components.

## 5. Mutable Class: Identity and State Changes

A mutable object has state that changes through methods:

```java
final class Counter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
```

Here `count` is not final and has a mutation operation `increment()`. The caller holds a reference to the **same object** throughout incrementing the count.

### When to Choose a Mutable Class

- State represents progression: `NEW → PROCESSING → DONE`.
- The object is an aggregate/entity with an identity that must be maintained.
- There are multiple operations updating state that must check invariants.
- It needs to track transactions or interactions with a resource/lifecycle.
- A framework has lifecycle/proxy/constructor constraints that make a mutable non-final class more suitable (check the specific framework/version).

### When to Be Cautious

- Methods that mutate a shared object cause other callers to observe side effects.
- Aliasing: multiple references to the same instance.
- Concurrency: mutation requires synchronization/thread confinement/atomic operations.
- Hash-based collections can break lookups if mutable fields are used in `equals/hashCode`.

## 6. Runnable: A Mutable Object Preserving Identity While State Changes

Save **`MutableCounterDemo.java`**:

```java
final class Counter {
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

public class MutableCounterDemo {
    public static void main(String[] args) {
        Counter first = new Counter(1);
        Counter alias = first;

        first.increment();
        alias.increment();

        System.out.println(first.value());
        System.out.println(alias.value());
        System.out.println(first == alias);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableCounterDemo.java
java MutableCounterDemo
```

Stdout:

```text
3
3
true
```

Both references point to the same Counter. This is the core difference between "updating an object" and "creating a new immutable value".

## 7. Mutation Should Be Controlled via Behavior, Not by Exposing All Fields

A mutable class does not necessarily have setters for every field. For an object with business rules, the API should express valid operations:

```java
account.deposit(amount);
account.withdraw(amount);
```

Instead of:

```java
account.setBalance(-1000);
account.setStatus("anything");
```

Reasons:
- Constructors verify the initial invariant.
- Methods preserve the invariant after each valid state.
- The API helps audit/log/test behavior.
- Users do not have to remember to modify multiple fields at the same time.

### Note on Concurrency

A mutable class that checks `if (balance >= amount)` and then executes `balance -= amount` is **not automatically thread-safe**. For concurrency, you must design appropriate synchronization/locking/transactions. `final class` only prevents subclassing; it does not replace atomicity.

## 8. Runnable: Mutable Progress Tracker with Stable Identity

To see why a **mutable class** fits when an object must preserve its identity across multiple updates, we use a task progress tracker instead of the bank account example, which already has its own separate practice lesson.

Create **`ProgressTrackerDemo.java`**:

~~~java
public class ProgressTrackerDemo {
    static final class ProgressTracker {
        private final String taskId;
        private final int totalSteps;
        private int completed;

        ProgressTracker(String taskId, int totalSteps) {
            if (taskId == null || taskId.isBlank()
                    || totalSteps <= 0) {
                throw new IllegalArgumentException(
                        "invalid task");
            }
            this.taskId = taskId.strip();
            this.totalSteps = totalSteps;
        }

        void advance(int steps) {
            if (steps <= 0) {
                throw new IllegalArgumentException(
                        "steps must be positive");
            }
            if (steps > totalSteps - completed) {
                throw new IllegalStateException(
                        "too many steps");
            }
            completed += steps;
        }

        String taskId() {
            return taskId;
        }

        int completed() {
            return completed;
        }

        int remaining() {
            return totalSteps - completed;
        }

        boolean finished() {
            return completed == totalSteps;
        }
    }

    public static void main(String[] args) {
        ProgressTracker work =
                new ProgressTracker(" JOB-7 ", 5);
        work.advance(2);
        work.advance(3);

        System.out.println("id=" + work.taskId());
        System.out.println("done=" + work.completed());
        System.out.println("remaining=" + work.remaining());
        System.out.println("finished=" + work.finished());

        try {
            work.advance(1);
        } catch (IllegalStateException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ProgressTrackerDemo.java
java ProgressTrackerDemo
~~~

Expected stdout:

~~~text
id=JOB-7
done=5
remaining=0
finished=true
rejected=too many steps
~~~

`taskId` and `totalSteps` are fixed data, whereas `completed` changes through **guarded behavior**. The object keeps the same identity from the start until the completion of the task. A `record ProgressSnapshot(String taskId, int completed, int totalSteps)` can store a report value at a point in time, but by itself it does not provide in-place mutation of the same progress tracker.

**Lesson boundary:** here the example is used to compare *a mutable entity with an immutable/record value*. The business operation design lesson delves deeper into guards and invariants; the account lesson implements deposit/withdrawal with its own amount logic. If multiple threads update `completed`, the demo needs to add a concurrency policy rather than relying solely on `final` for the two fixed fields.

## 9. Immutable Class: A Value That Does Not Change After Creation

An immutable class is designed so that **the observable state of an instance does not change** after the constructor/factory completes.

Common principles:
- A `final` class or one designed to prevent subclasses from altering its contract.
- Necessary fields are `private final`.
- Validate invariants during construction.
- No methods that mutate the object.
- Mutable input data is **defensively copied** if needed.
- Accessors do not return references that allow callers to modify the internal representation.
- Do not publish `this` before the constructor completes.
- If a component contains another object, ensure that **transitive state** cannot be modified unintentionally either.

**`final` is not synonymous with immutable.** A `final List<String> values` field can still point to a mutable ArrayList. A `final class` can contain mutable fields.

### When to Choose a Hand-Written Immutable Class

- The representation needs hidden fields that do not match the API components.
- Complex constructor/factory logic.
- Need accessor API names that differ from the record convention.
- Want specific control over equality/hashCode/toString or exposure.
- Need to preserve compatibility with an existing class API instead of switching to a record.
- Need separate implementation details, and controlled caches/derived attributes without violating semantic immutability.

## 10. Runnable: Immutable `Range` Class

Save **`ImmutableRangeDemo.java`**:

```java
import java.util.Objects;

final class Range {
    private final int start;
    private final int end;

    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }

    int length() {
        return end - start;
    }

    Range shift(int delta) {
        return new Range(
                Math.addExact(start, delta),
                Math.addExact(end, delta));
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Range range)) return false;
        return start == range.start && end == range.end;
    }

    @Override
    public int hashCode() {
        return Objects.hash(start, end);
    }

    @Override
    public String toString() {
        return "Range[" + start + "," + end + "]";
    }
}

public class ImmutableRangeDemo {
    public static void main(String[] args) {
        Range a = new Range(2, 7);
        Range b = a.shift(3);
        Range same = new Range(2, 7);

        System.out.println(a);
        System.out.println(b);
        System.out.println(a.equals(same));
        System.out.println(a == same);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableRangeDemo.java
java ImmutableRangeDemo
```

Stdout:

```text
Range[2,7]
Range[5,10]
true
false
```

The `shift` method **returns a new instance** without modifying `a`. Value equality is written manually, which is appropriate for a value object with two coordinates.

**Watch out for overflow:** `length()` uses int subtraction; if a range can span the entire int domain, use long to compute the length. This example focuses on immutability and equality, not extremely large range data types.

## 11. Record: Concise Data Syntax, Not "Magic Immutable"

A Java 17 record declaration:

```java
record Point(int x, int y) {
}
```

the compiler provides:
- Private final **component fields** `x` and `y`.
- Public accessors `x()`, `y()`.
- Corresponding canonical constructor `Point(int,int)`.
- `equals`, `hashCode`, `toString` based on components, unless validly overridden.
- Inheritance from `java.lang.Record`; a record is implicitly final.

Usage:

```java
Point a = new Point(2, 3);
Point b = new Point(2, 3);
```

`a.equals(b)` is true by default; `a == b` is false because two `new` invocations create two different instances.

### A Record Is a Data Carrier

The header `(int x, int y)` declares the underlying data that makes up the record. It is not a way to hide every implementation detail like an immutable class with a private representation and a custom API.

A record can have:
- Instance methods.
- Static fields/static methods.
- Validation and normalization in the canonical constructor.
- Additional constructors, which must delegate to the canonical constructor via `this(...)`.

A record cannot declare additional non-static instance fields or instance initializer blocks. It has no optional superclass and cannot be subclassed.

## 12. Runnable: Record with Value Semantics

Save **`RecordPointDemo.java`**:

```java
record Point(int x, int y) {
    int squaredDistance() {
        return x * x + y * y;
    }
}

public class RecordPointDemo {
    public static void main(String[] args) {
        Point a = new Point(3, 4);
        Point b = new Point(3, 4);

        System.out.println(a);
        System.out.println(a.x());
        System.out.println(a.y());
        System.out.println(a.squaredDistance());
        System.out.println(a.equals(b));
        System.out.println(a == b);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordPointDemo.java
java RecordPointDemo
```

Stdout:

```text
Point[x=3, y=4]
3
4
25
true
false
```

Adding a computation instance method is completely normal for a record. The reason for choosing a record is that **x/y is the representation and equality based on the components makes sense**.

## 13. A Record Is Not Automatically Deeply Immutable

Consider:

```java
record Team(java.util.List<String> members) {
}
```

The `members` field is final: it cannot be reassigned after the constructor finishes. However, if the caller passes in a mutable `ArrayList`, the caller can modify the list after constructing the record; by default, `team.members()` returns **the same list reference**.

This leads to:
- The value state observed through the accessor changes even though the record object does not reassign the field.
- `toString`/`equals`/`hashCode` can change with the list contents.
- A HashMap/HashSet using the record as a key risks unstable lookups if the component list is mutated.
- A thread can observe mutations of the referent without concurrency discipline.

**What a record guarantees:** shallow component field finality. **What it does not guarantee:** deep immutability of the entire object graph.

## 14. Runnable: A Record Containing a Mutable List Modified from Outside

Save **`MutableRecordComponentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
}

public class MutableRecordComponentDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team(source);
        source.add("Binh");

        System.out.println(team.members());
        System.out.println(team.members() == source);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableRecordComponentDemo.java
java MutableRecordComponentDemo
```

Stdout:

```text
[An, Binh]
true
```

Even though `Team` is a record, source and the team accessor still share the same mutable ArrayList. Do not choose a record assuming "everything is automatically safe" when designing an immutable DTO/snapshot.

## 15. Defensive Copy in a Compact Canonical Constructor

Java 17 supports compact constructors:

```java
record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
```

Explanation:
- `members` in the compact body is the implicit constructor parameter.
- `List.copyOf(members)` creates or reuses an **unmodifiable list** per the API, and rejects null elements.
- After the compact body, the compiler assigns the component field from the `members` parameter.
- If the caller modifies the source list after creating Team, it does not change the snapshot list.
- The default accessor `members()` returns an unmodifiable list, so callers cannot add or remove elements.
- **However**, if the list contains **mutable elements**, `List.copyOf` does not deep-clone the elements.

**Caveat:** unmodifiable **is not synonymous with** "all objects reachable from the list are immutable". For `List<String>`, String is immutable, so this is a good value-oriented representation. For `List<MutableItem>`, you also have to consider whether the elements can be mutated.

## 16. Runnable: Record Compact Copy with List<String>

Save **`RecordDefensiveListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}

public class RecordDefensiveListDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team(source);
        source.add("Binh");

        System.out.println(team.members());
        System.out.println(source);

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordDefensiveListDemo.java
java RecordDefensiveListDemo
```

Stdout:

```text
[An]
[An, Binh]
unmodifiable
```

This pattern is suitable for a record **containing a list of Strings**, because both the collection structure and the observed elements are immutable in the example.

## 17. An Unmodifiable View Differs from a Snapshot Copy

Two APIs:

```java
List<String> view =
        Collections.unmodifiableList(source);

List<String> snapshot = List.copyOf(source);
```

**They are not the same**:
- `Collections.unmodifiableList(source)` is a **view that disallows modification through the view**, but still reflects valid changes made to `source`.
- `List.copyOf(source)` returns an unmodifiable list with a snapshot of the elements at creation time (shallow).
- `List.copyOf` may return an existing suitable instance that is already unmodifiable; it does not guarantee that a new list object is always allocated.
- `List.copyOf` rejects null elements; consider the semantics if the input contains null.

### Runnable

Save **`ViewVsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> snapshot =
                List.copyOf(source);

        source.add("B");

        System.out.println(view);
        System.out.println(snapshot);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

Stdout:

```text
[A, B]
[A]
```

If a value object must not change, a **view** is usually not enough when the caller still holds the mutable source list.

## 18. Record with an Array: A Different Trap from a List

`record Packet(byte[] data)` has a final reference to the array, **but the array is mutable**:
- The caller changes `data[0]` after the constructor → the record observes the new content.
- The default accessor `data()` returns the array reference → the caller can modify it through the accessor.
- Record-generated `equals/hashCode` for an array component relies on array **reference equality/hashCode**, **not** element-by-element comparison like `Arrays.equals`.

Defensive cloning:

```java
record Packet(byte[] data) {
    Packet {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

solves aliasing on input/output, but **does not automatically base component equality on array content**. Two Packets cloned from two arrays with the same bytes are typically **not equal** under default record equals.

**Design guidance:** if value equality by byte contents is important, consider a custom immutable wrapper with consistent `Arrays.equals/hashCode`, or another representation with an API that has clear semantics. Do not choose a record just because the header is short while overlooking array behavior.

## 19. Runnable: Defensive Cloning Still Does Not Make Arrays Value-Equal

Save **`RecordArrayDemo.java`**:

```java
import java.util.Arrays;

record Packet(int[] numbers) {
    Packet {
        numbers = numbers.clone();
    }

    @Override
    public int[] numbers() {
        return numbers.clone();
    }
}

public class RecordArrayDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Packet first = new Packet(source);
        Packet second = new Packet(new int[] {1, 2});

        source[0] = 9;
        int[] leakedCopy = first.numbers();
        leakedCopy[1] = 8;

        System.out.println(Arrays.toString(first.numbers()));
        System.out.println(first.equals(second));
        System.out.println(Arrays.equals(
                first.numbers(), second.numbers()));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordArrayDemo.java
java RecordArrayDemo
```

Stdout:

```text
[1, 2]
false
true
```

First and second hold **two arrays with different references** after cloning. The record's generated equals does not deep-compare arrays. This is why **record + array** needs careful review for both immutability and equality.

## 20. Hand-Written Immutable Class When a Special Representation Is Needed

An immutable object may want to:
- Hide a primitive array.
- Expose a `bytes()` method that returns a clone.
- Compare array contents using `Arrays.equals`.
- Forbid subclassing via `final`.
- Have a custom cache/hash structure (if semantics are preserved).
- Not expose the array as a record component in the API.

Example:

```java
final class BytesValue {
    private final byte[] bytes;

    BytesValue(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    byte[] toArray() {
        return bytes.clone();
    }

    // equals/hashCode use Arrays.equals/hashCode
}
```

This is a **design snippet**, not a full class yet, because equals/hashCode are omitted to illustrate the representation choice.

### When a Record Can Still Be Used

A record can override equals/hashCode to handle arrays appropriately, but that increases boilerplate and requires checking record equality rules, consistency, defensive copies, and toString. When the representation is too specialized, a **hand-written immutable class** usually conveys the contract more clearly.

## 21. Runnable: Immutable Array Value Class

Save **`ImmutableBytesDemo.java`**:

```java
import java.util.Arrays;

final class BytesValue {
    private final byte[] bytes;

    BytesValue(byte[] bytes) {
        this.bytes = bytes.clone();
    }

    byte[] toArray() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof BytesValue that)) return false;
        return Arrays.equals(bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }

    @Override
    public String toString() {
        return Arrays.toString(bytes);
    }
}

public class ImmutableBytesDemo {
    public static void main(String[] args) {
        byte[] source = {1, 2, 3};
        BytesValue a = new BytesValue(source);
        BytesValue b = new BytesValue(new byte[] {1, 2, 3});

        source[0] = 9;
        byte[] snapshot = a.toArray();
        snapshot[1] = 8;

        System.out.println(a);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableBytesDemo.java
java ImmutableBytesDemo
```

Stdout:

```text
[1, 2, 3]
true
true
```

A hand-written immutable class handles both **defensive copies** and **content equality** for arrays. With a default record, array component equality is not compared element-by-element.

## 22. Enum: A Fixed Set of Constants Defined by the Program

An enum is appropriate when all valid values are defined by the code:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}
```

Client:

```java
Priority priority = Priority.HIGH;
```

Enum constants are **predefined instances**; do not use `new Priority()` outside the enum.

Familiar APIs:
- `Priority.values()` returns an array of constants in declaration order.
- `Priority.valueOf("HIGH")` retrieves an enum constant by exact name (throws `IllegalArgumentException` if invalid).
- `priority.name()` returns the declared name.
- `priority.ordinal()` returns the 0-based declaration position — **do not use it as a persistent data code**.
- `EnumSet` and `EnumMap` take advantage of enum types for specialized sets/maps.

### When an Enum Is Appropriate

- The value set is small, finite, and not added arbitrarily at runtime.
- Each value has a stable meaning in the source code.
- You can add custom behavior, display labels, or stable codes.
- Callers need exhaustiveness via `switch` on the enum (Java 17 supports enum switch).

### When an Enum Is Not Appropriate

- Lists of countries/products/users updated dynamically from a database.
- Each instance needs a different payload per request.
- The same status enum constant cannot independently store different mutable per-order state.

## 23. Runnable: Enum Constants and Switch

Save **`EnumPriorityDemo.java`**:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

public class EnumPriorityDemo {
    static String handle(Priority priority) {
        return switch (priority) {
            case LOW -> "later";
            case MEDIUM -> "normal";
            case HIGH -> "now";
        };
    }

    public static void main(String[] args) {
        Priority value = Priority.HIGH;

        System.out.println(handle(value));
        System.out.println(value.name());
        System.out.println(value == Priority.HIGH);
        System.out.println(Priority.values().length);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumPriorityDemo.java
java EnumPriorityDemo
```

Stdout:

```text
now
HIGH
true
3
```

The `switch` expression on an enum is a standard Java 17 feature and does not require preview. This is a simple choice for a fixed set of categories.

## 24. An Enum Is Not Automatically Immutable If You Declare Mutable Fields

Most enums should be designed to be **immutable**:

```java
enum Status {
    NEW, PAID
}
```

However, Java allows enums to have instance fields and methods; if you declare a mutable field and a setter, the constants are **shared objects**, so mutation affects everywhere the same constant is used.

This is a design flaw that easily causes unintended global shared state.

### Do Not Write Runtime Data to an Enum Constant

Do not write `Status.PAID.setCurrentOrderId("123")` to store per-order state. The same `PAID` constant can be used for many orders; there is no separate enum instance per order.

Place per-instance data in `Order` or `OrderSnapshot`, and use `Status` only as a **status symbol**.

## 25. Runnable: Enum Mutable State Is Shared Data

Save **`MutableEnumPitfallDemo.java`**:

```java
enum Mode {
    ACTIVE;

    private int hits;

    void hit() {
        hits++;
    }

    int hits() {
        return hits;
    }
}

public class MutableEnumPitfallDemo {
    public static void main(String[] args) {
        Mode first = Mode.ACTIVE;
        Mode second = Mode.ACTIVE;

        first.hit();
        second.hit();

        System.out.println(first == second);
        System.out.println(first.hits());
        System.out.println(second.hits());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableEnumPitfallDemo.java
java MutableEnumPitfallDemo
```

Stdout:

```text
true
2
2
```

The demo **intentionally shows an anti-pattern**: `hits` is shared state of the enum constant, not the individual hit count of each user/request. Production code usually makes enum fields final and places per-instance mutable state elsewhere.

## 26. Enums with Stable Codes: Avoid Using `ordinal()` as an ID

An enum:

```java
enum PaymentState {
    NEW, PAID, CANCELLED
}
```

`ordinal()` reflects the declaration **position**. If you insert an enum constant at the beginning or reorder them, the ordinals of the other constants change. Therefore, do not store ordinal as:
- A persistent database status code.
- A public API numeric identifier.
- A JSON event field serving consumers across multiple versions.
- A Kafka message schema.
- A persisted value that needs to stay stable for many years.

A better design: define a separate **stable code**.

```java
enum PaymentState {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
```

When adding or reordering constants, the code stays unchanged if you intentionally preserve it. Database/API migrations require specific versioning and compatibility contracts.

## 27. Runnable: Enum Stable Code and Parsing

Save **`EnumStableCodeDemo.java`**:

```java
enum PaymentState {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static PaymentState fromCode(String code) {
        for (PaymentState state : values()) {
            if (state.code.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException("unknown code");
    }
}

public class EnumStableCodeDemo {
    public static void main(String[] args) {
        PaymentState state = PaymentState.PAID;

        System.out.println(state.code());
        System.out.println(PaymentState.fromCode("C"));
        System.out.println(state == PaymentState.fromCode("P"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumStableCodeDemo.java
java EnumStableCodeDemo
```

Stdout:

```text
P
CANCELLED
true
```

Do not print ordinal as a persistent ID. `fromCode` throws an exception on unknown input so the caller handles it explicitly. If an enum has many constants, you can use an immutable lookup map validated for uniqueness at initialization.

## 28. Enum + Instance Data: Combine Properly Instead of Choosing One or the Other

An `Order` entity can be mutable while containing an enum status:

```java
final class Order {
    private OrderStatus status = OrderStatus.NEW;

    void markPaid() {
        status = OrderStatus.PAID;
    }

    OrderStatus status() {
        return status;
    }
}

enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Here:
- `Order` is an object carrying its own identity/lifecycle.
- `OrderStatus` is an enum symbol belonging to a finite set.
- Updating the status modifies **the field of Order**, without modifying the state of the `OrderStatus.PAID` enum singleton.

**Good design often combines multiple kinds**: a mutable aggregate + enum state + an immutable/record snapshot, rather than forcing the entire system to pick the same kind.

## 29. Runnable: A Mutable Entity Using an Enum Status

Save **`OrderWithEnumDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID
}

final class Order {
    private final String id;
    private OrderStatus status = OrderStatus.NEW;

    Order(String id) {
        this.id = id;
    }

    void pay() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("already paid");
        }
        status = OrderStatus.PAID;
    }

    String id() {
        return id;
    }

    OrderStatus status() {
        return status;
    }
}

public class OrderWithEnumDemo {
    public static void main(String[] args) {
        Order order = new Order("O-1");

        System.out.println(order.status());
        order.pay();
        System.out.println(order.status());
        System.out.println(order.id());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrderWithEnumDemo.java
java OrderWithEnumDemo
```

Stdout:

```text
NEW
PAID
O-1
```

If payment is executed across multiple threads or involves a database transaction, additional concurrency/consistency controls are needed. The example only illustrates the choice of **mutable entity + immutable enum symbol**.

## 30. Time and Money: Typically Use Immutable Values

An address, price, time interval, or coordinate is usually a **value**, not an object with its own identity.

The JDK already has many immutable types:
- `String`.
- `BigInteger`, `BigDecimal` (noting that `equals` also considers scale).
- `LocalDate`, `LocalTime`, `Instant`, `Duration`.
- `UUID` (value object).
- `Enum` constants by design are typically used as symbols.

Your value objects can be a record or an immutable class:
- `Money(long cents, Currency currency)` when using an appropriate currency type.
- `Coordinates(double latitude, double longitude)`.
- `DateRange(LocalDate start, LocalDate end)`.

### Monetary Amounts: Do Not Arbitrarily Use double

`double` is binary floating-point and does not fit all currency rules. A Money value object can store **minor units in a long** or use `BigDecimal` with an explicit scale/rounding policy.

Do not assume a currency has 2 decimal digits in every case; the domain determines the minor unit contract.

## 31. Runnable: Immutable Money Record with Validation

Save **`MoneyRecordDemo.java`**:

```java
import java.util.Objects;

enum Currency {
    VND, USD
}

record Money(long minorUnits, Currency currency) {
    Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        Objects.requireNonNull(currency, "currency");
    }

    Money plus(Money other) {
        if (currency != other.currency) {
            throw new IllegalArgumentException("currency mismatch");
        }
        return new Money(
                Math.addExact(minorUnits, other.minorUnits),
                currency);
    }
}

public class MoneyRecordDemo {
    public static void main(String[] args) {
        Money first = new Money(100, Currency.VND);
        Money second = new Money(50, Currency.VND);
        Money total = first.plus(second);

        System.out.println(first);
        System.out.println(total);
        System.out.println(total.currency());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MoneyRecordDemo.java
java MoneyRecordDemo
```

Stdout:

```text
Money[minorUnits=100, currency=VND]
Money[minorUnits=150, currency=VND]
VND
```

`plus` creates a **new** Money record. Both the currency symbol and minor units are kept in the immutable representation. Use `Math.addExact` to detect overflow instead of silently wrapping long.

## 32. Canonical Constructor and Record Invariants

A record header defines components, but **does not automatically validate business rules**:

```java
record Percentage(int value) {
}
```

Allows `new Percentage(-300)` if there is no validation.

Compact canonical:

```java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("0..100");
        }
    }
}
```

Advantages:
- All constructor paths must ultimately go through the canonical constructor.
- No need to manually assign component fields in the compact body.
- Centralized constructor validation.
- Clearer API invariants.

### Modifying Implicit Parameters During Normalization

`record Email(String address) { Email { address = address.strip().toLowerCase(Locale.ROOT); } }` is a valid pattern. Pay attention to null handling, and real-world email address validation is more complex than just containing `@`.

### Runtime Initialization Differs from Mutation

Normalization in the constructor does not make the object mutable. The value is determined before the object is fully published.

## 33. Runnable: Compact Validation of a Record

Save **`ValidatedRecordDemo.java`**:

```java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("0..100");
        }
    }
}

public class ValidatedRecordDemo {
    public static void main(String[] args) {
        Percentage valid = new Percentage(75);

        System.out.println(valid);

        try {
            new Percentage(101);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ValidatedRecordDemo.java
java ValidatedRecordDemo
```

Stdout:

```text
Percentage[value=75]
0..100
```

A record is a **language convention for a data carrier**, but invariants are still defined by the author.

## 34. Mutable Elements Keep `List.copyOf` Shallow

Consider the record:

```java
record Snapshot(List<MutableItem> items) {
    Snapshot {
        items = List.copyOf(items);
    }
}
```

`items` is now unmodifiable in list structure, but each `MutableItem` still has methods that change its state. If the caller keeps a reference to an item, or the accessor returns the same item, the snapshot value can still change.

To achieve deep immutable semantics, there are two common approaches:
1. Convert each mutable element into an **immutable value representation** (for example, a separate record) and then store an unmodifiable list.
2. Create deep copies to the required depth, with a clear contract and tests for nested graphs.

**Deep copying is not simple** if the graph has cycles, shared identities, resource handles, and subtype polymorphism. Designing input data to be immutable from the start is usually simpler than copying everything afterward.

## 35. Runnable: List.copyOf Does Not Deep-Copy Elements

Save **`ShallowCopyDemo.java`**:

```java
import java.util.List;

final class MutableItem {
    private String name;

    MutableItem(String name) {
        this.name = name;
    }

    void rename(String value) {
        name = value;
    }

    String name() {
        return name;
    }
}

record BasketView(List<MutableItem> items) {
    BasketView {
        items = List.copyOf(items);
    }
}

public class ShallowCopyDemo {
    public static void main(String[] args) {
        MutableItem item = new MutableItem("old");
        BasketView view = new BasketView(List.of(item));

        item.rename("new");

        System.out.println(view.items().get(0).name());
        System.out.println(view.items().size());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ShallowCopyDemo.java
java ShallowCopyDemo
```

Stdout:

```text
new
1
```

Even though the list is unmodifiable, the element is still mutable. You cannot conclude that a record is deeply immutable just by seeing `List.copyOf`.

## 36. Snapshots Convert Mutable State into Immutable Values

A very useful pattern: a mutable aggregate has a method that returns a **record snapshot**.

```java
record AccountView(String id, long balance) {
}
```

The Account object has `deposit` and `withdraw`; the snapshot is read-only, has value semantics, and can be passed across an API/reporting boundary.

Advantages:
- Consumers are not permitted to mutate the entity through the snapshot.
- The snapshot describes the state at a point in time.
- UI/cache/reporting can easily work with values.
- Easy to compare/test snapshots.

Consider consistency when snapshotting multiple mutable fields under concurrent updates: creating the snapshot must read a consistent state if the domain requires it; locks/transactions may be needed.

## 37. Runnable: Mutable Account → Immutable Record Snapshot

Save **`MutableToRecordSnapshotDemo.java`**:

```java
final class Account {
    private final String id;
    private long balance;

    Account(String id, long balance) {
        this.id = id;
        this.balance = balance;
    }

    void deposit(long amount) {
        balance = Math.addExact(balance, amount);
    }

    AccountSnapshot snapshot() {
        return new AccountSnapshot(id, balance);
    }
}

record AccountSnapshot(String id, long balance) {
}

public class MutableToRecordSnapshotDemo {
    public static void main(String[] args) {
        Account account = new Account("A", 100);

        AccountSnapshot before = account.snapshot();
        account.deposit(50);
        AccountSnapshot after = account.snapshot();

        System.out.println(before);
        System.out.println(after);
        System.out.println(before.equals(after));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableToRecordSnapshotDemo.java
java MutableToRecordSnapshotDemo
```

Stdout:

```text
AccountSnapshot[id=A, balance=100]
AccountSnapshot[id=A, balance=150]
false
```

`before` does not automatically change when the entity state changes. This design is usually better than turning a mutable entity into a record containing the entire business lifecycle.

## 38. Equality Affects How You Choose a Type

### Mutable Class

For a mutable object with a fixed ID, equality should be designed carefully. Do not auto-generate `equals/hashCode` based on all mutable fields if the object will be used as a key in a `HashMap`.

### Immutable Value Class

You should define value-based `equals/hashCode` if the semantics require it (and ensure they are consistent). An immutable class is **not required** by the language to override equals, but value objects usually need to.

### Record

Generated equality inspects component values. For primitive components, it compares according to record rules. For reference components, equality uses the semantics of the component objects. Mutable components can cause a record's equality/hashing to change.

### Enum

Enum constants have fixed identity within the enum class; `==` is usually the appropriate way to compare them. `name()` is a source identifier that can change during refactoring and affect persisted contracts if you store the name; an explicit stable code is the solution if wire compatibility is needed.

## 39. A Mutable Key Can Make Map Lookups Unstable

If you use an object whose `hashCode()` changes after inserting it as a key in a HashMap, the original bucket/hash placement no longer corresponds to the new hash. In that case, lookup/removal may fail to find the mapping.

This is an anti-pattern:

```java
Map<MutableKey, String> map = new HashMap<>();
MutableKey key = new MutableKey("A");
map.put(key, "value");
key.setCode("B");
```

This is a snippet; `MutableKey` could be defined with equals/hashCode based on code. The lookup result depends on implementation/hash distribution; the key point is **violating the invariant of a stable hashCode while the key is inside a hash map**, without needing a chance-dependent stdout demonstration.

### Safe Alternatives

- Use an immutable key record/class with deeply immutable components.
- Use an immutable business ID as the key (`String`, `UUID`).
- If a mutable key object is needed, avoid modifying fields that contribute to equality/hashCode while the key is in the collection.
- Use an identity-based collection only when the semantics genuinely require object identity.

## 40. Value Equality on Decimal Numbers Needs a Policy

`BigDecimal.equals` checks both **value and scale**. For example:

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00"))
```

returns `false` even though `compareTo` returns 0.

If the record is:

```java
record Price(BigDecimal amount) {
}
```

Price's generated equals uses BigDecimal's equals. Therefore, two prices representing equivalent monetary amounts in the business domain may not be equal if their scales differ.

Solutions depending on the domain:
- Normalize `amount` in the canonical constructor according to a fixed scale/rounding policy.
- Use minor units `long` if the business supports it.
- Clearly define the numeric equality policy for a custom immutable class/record.
- Do not change `equals` while forgetting `hashCode`.
- Do not alter the amount after using it as a map key.

## 41. Runnable: BigDecimal Scale Affects Value Equality

Save **`BigDecimalRecordDemo.java`**:

```java
import java.math.BigDecimal;

record Price(BigDecimal amount) {
}

public class BigDecimalRecordDemo {
    public static void main(String[] args) {
        Price first = new Price(new BigDecimal("1.0"));
        Price second = new Price(new BigDecimal("1.00"));

        System.out.println(first.equals(second));
        System.out.println(
                first.amount().compareTo(second.amount()) == 0);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BigDecimalRecordDemo.java
java BigDecimalRecordDemo
```

Stdout:

```text
false
true
```

Do not call the record "wrong" when getting false: it uses component equality based on `BigDecimal`. You need to choose and document appropriate business equality semantics.

## 42. Enum Ordinal Is Not a Persistent Business Identity

`Status.ACTIVE.ordinal()` is the index of the constant in the declaration. It can change when:
- Inserting an enum constant before it.
- Reordering the source.
- Removing/reorganizing constants.

**Do not write `ordinal` to a database or wire protocol as a persistent ID**. When migrating legacy ordinals, you must have an accurate mapping based on **historical versions**; you cannot always deduce old codes from the current enum order.

`name()` is more stable than ordinal against reordering, but the constant name can still be renamed. For external long-lived data, an explicit stable code/contract makes managing migrations clearer.

### EnumMap and EnumSet

These specialized collections may use the enum ordinal internally for optimization. That does **not** mean you should persist ordinal as a public protocol. Use `EnumMap/EnumSet` through their API, without depending on internal layout.

## 43. Runnable: EnumSet for a Set of Constants

Save **`EnumSetDemo.java`**:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, DELETE
}

public class EnumSetDemo {
    public static void main(String[] args) {
        EnumSet<Permission> granted =
                EnumSet.of(Permission.READ, Permission.WRITE);

        System.out.println(granted.contains(Permission.READ));
        System.out.println(granted.contains(Permission.DELETE));
        System.out.println(granted.size());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSetDemo.java
java EnumSetDemo
```

Stdout:

```text
true
false
2
```

EnumSet is suitable for a **set of permissions belonging to an enum type**. It is not a place to store dynamic permissions that the source code does not know in advance.

## 44. When to Use a Sealed Interface + Record Instead of an Enum?

An enum represents a set of constants. However, sometimes each **variant** has a payload with a different schema:

- `Success(receiptId, timestamp)`.
- `Failure(errorCode, reason)`.
- `Pending(retryAt)`.

Forcing them into an enum with nullable fields corresponding to each variant creates invalid combinations and makes checking invariants difficult.

Java 17 has sealed interfaces/classes and records to represent **a finite set of variant types where each variant has its own payload**.

```java
sealed interface Result permits Ok, Error {
}

record Ok(String data) implements Result {
}

record Error(String message) implements Result {
}
```

`Result` restricts direct permitted subtypes. Each record leaf is implicitly final. This is a form of *sum type* modeled with a sealed hierarchy, different from enum constants.

**Java 17 note:** pattern matching for `instanceof` is stable; pattern matching in `switch` over type patterns was still in preview at the time and is not used in standard `javac --release 17` examples.

## 45. Runnable: Sealed Interface and Record Variants

Save **`SealedRecordResultDemo.java`**:

```java
sealed interface Result permits Ok, Error {
}

record Ok(String data) implements Result {
}

record Error(String message) implements Result {
}

public class SealedRecordResultDemo {
    static String describe(Result result) {
        if (result instanceof Ok ok) {
            return "ok:" + ok.data();
        }
        if (result instanceof Error error) {
            return "error:" + error.message();
        }
        throw new IllegalStateException("unexpected result");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ok("A")));
        System.out.println(describe(new Error("invalid")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedRecordResultDemo.java
java SealedRecordResultDemo
```

Stdout:

```text
ok:A
error:invalid
```

If each result needs a different payload, a sealed interface + record variants can be clearer than an enum with unrelated nullable fields. When adding a new variant, update the dispatching code and tests; do not assume a chain of `if` statements is exhaustively checked by the compiler.

## 46. Enum for Status or a State Machine in a Class?

Suppose a workflow has `NEW`, `PAID`, `SHIPPED`, `CANCELLED`:
- An enum serves as **the set of state symbols**.
- A mutable Order/Process object holds the **current state**.
- Methods control transitions according to business constraints.

```java
void ship() {
    if (status != Status.PAID) {
        throw new IllegalStateException("not paid");
    }
    status = Status.SHIPPED;
}
```

If there are side effects on payment, inventory, network, or database, transaction/process orchestration is needed. An enum does not guarantee state machine consistency merely by existing.

### When Transitions Are Purely Value-Based

If the domain wants immutability, you can use an immutable record that returns a new instance on each transition:

```java
record OrderState(String id, Status status) {
    OrderState shipped() {
        if (status != Status.PAID) {
            throw new IllegalStateException();
        }
        return new OrderState(id, Status.SHIPPED);
    }
}
```

Choose based on the identity/lifecycle/consistency model, not a rule forcing every state machine to be mutable.

## 47. Runnable: Immutable State Transitions with a Record

Save **`ImmutableStateTransitionDemo.java`**:

```java
enum State {
    NEW, PAID, SHIPPED
}

record OrderState(String id, State state) {
    OrderState pay() {
        if (state != State.NEW) {
            throw new IllegalStateException("not new");
        }
        return new OrderState(id, State.PAID);
    }

    OrderState ship() {
        if (state != State.PAID) {
            throw new IllegalStateException("not paid");
        }
        return new OrderState(id, State.SHIPPED);
    }
}

public class ImmutableStateTransitionDemo {
    public static void main(String[] args) {
        OrderState original = new OrderState("A", State.NEW);
        OrderState paid = original.pay();
        OrderState shipped = paid.ship();

        System.out.println(original.state());
        System.out.println(paid.state());
        System.out.println(shipped.state());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableStateTransitionDemo.java
java ImmutableStateTransitionDemo
```

Stdout:

```text
NEW
PAID
SHIPPED
```

Each transition returns a **new value**; the original does not change. This kind of model is especially easy to test when the state is small and does not require shared mutable identity.

## 48. Thread Safety Does Not Come Automatically from a Keyword

- A mutable class usually needs concurrency control if multiple threads share it.
- An immutable value that is **properly designed and safely published** is usually simpler to share.
- Final record fields help construct component state, but if referents are mutable, concurrency hazards still exist.
- Enum constants are shared objects; if they have mutable fields, they can become a global race condition.
- `volatile` addresses certain visibility/happens-before concerns, **does not make every compound update atomic**, and does not make the whole object immutable.
- `synchronized` or `AtomicInteger` solves specific needs; it does not replace ownership architecture.

### What Does Immutability Help With?

When an object is truly immutable, consumers can use the same reference without worrying about competing updates to the object's state; caching and reasoning become easier. However, if the constructor publishes `this` before completion or component graphs mutate, the benefits are compromised.

**Do not claim "every immutable object automatically solves all concurrency bugs"**: transactions, ordering, external services, and atomic snapshots across multiple objects still require separate strategies.

## 49. Runnable: An Immutable Point Reused Multiple Times Without Changing

Save **`ImmutableReuseDemo.java`**:

```java
record Point(int x, int y) {
    Point move(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}

public class ImmutableReuseDemo {
    public static void main(String[] args) {
        Point original = new Point(1, 2);
        Point moved = original.move(3, 4);

        System.out.println(original);
        System.out.println(moved);
        System.out.println(original.equals(moved));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImmutableReuseDemo.java
java ImmutableReuseDemo
```

Stdout:

```text
Point[x=1, y=2]
Point[x=4, y=6]
false
```

Creating a new object when changing a value is a suitable pattern for small data. With very frequent updates or extremely large object graphs, evaluate the actual cost rather than prematurely optimizing with mutation before measuring.

## 50. Performance: Avoid Concluding "Record Is Faster Than Class"

There is no language guarantee that:
- `record` always uses less memory than a hand-written class.
- Immutable objects are always faster than mutable ones.
- Enum is always the fastest across all usages.
- Creating many immutable copies is always slow enough to abandon.

The JVM JIT, allocation optimizations, GC, object layout, access patterns, and workload determine the outcome.

A Java 17 record is still a **reference object**, not a C struct guaranteed to be stack-allocated. Object creation may be optimized by the JVM, but this is not promised at the source level.

### How to Decide on Optimization

1. Choose the right semantics (identity/mutation/value/fixed set).
2. Measure allocation rate, throughput, latency, and retained memory with appropriate benchmarking/profiling (for example, JMH/JFR).
3. Change the representation only if there is a real bottleneck.
4. If the data is large, consider batch processing, primitive arrays/streams, and bounded caches; avoid changing API semantics just to save a few source characters.

**A record is syntax and a transparent contract, not a performance annotation.**

## 51. API Compatibility When Choosing Record

Switching from a regular class to a record can change:
- Superclass and finality.
- Constructor signatures.
- Accessor naming (a getter `getX()` differs from a component accessor `x()`).
- Reflection metadata.
- Java serialization semantics.
- Framework binding/proxy behavior.
- Equality/hashCode/toString behavior.
- Public API compatibility.
- How clients subclass the old class.

Do not treat `class Person` → `record Person` as a purely syntactic refactoring. Check public callers, serializers, ORMs, and backward compatibility.

### An Existing Immutable Class Can Still Be a Good Choice

If an API is already stable with `getName()`, private class fields, custom equality, and generated proxies, there is no need to switch to a record even though the object is logically immutable.

## 52. ORM/Persistence: Entity vs. DTO

ORM/JPA implementations may have requirements regarding:
- No-arg constructor visibility.
- Entity mutability.
- Proxies or enhancement.
- Class/method finality.
- Field/property access.
- Mapping and identity equality.

Because a record is implicitly final and has a distinct canonical constructor, **do not assume a record is a compatible JPA entity**. Some frameworks support records for **DTO projections**, embeddables, or serialization use cases depending on the version; you must check the specific framework.

### Common Patterns

- **Persistence entity:** mutable class (per the framework contract), with business identity and invariants.
- **API/request/response DTO:** record when components and equality semantics are appropriate.
- **Domain value object:** record or immutable class.
- **Static status column:** enum with a stable mapping strategy; do not arbitrarily persist ordinal.

**Do not force ORM rules onto every domain class.** If the code does not use an ORM, you can choose records/immutable classes more freely.

## 53. Serialization and Wire Format

Data transmitted over HTTP/JSON/Kafka/database has a contract that outlives an in-memory object.

### Mutable Class

Can be constructed by many serializers using a no-arg constructor and setters; however, actual libraries may support constructor binding or builders. Do not assume all of them require setters.

### Immutable Class

May require constructor/factory annotations, mapper configuration, or adapters depending on the framework.

### Record

Component names/types appear in record reflection. Many modern serializers support record constructor binding, but you must check the version/configuration. Changing component names/types can break schemas for external clients.

### Enum

Can be serialized by name/code/ordinal depending on the framework. **Choose a clear, stable wire representation**, avoiding accidental defaulting to ordinal. Support unknown codes/version evolution if external data may come from future versions.

**Separate in-code types from wire schemas:** an enum with stable codes is a better choice than ordinal for durable data, yet you still need a migration policy when adding/removing codes.

## 54. Null and Validation for Each Choice

All four types need clear design:
- Mutable class: constructor + mutation methods protect invariants and the null policy.
- Immutable class: validate before publishing; final fields; do not allow invalid state.
- Record: canonical/compact constructor validates component arguments; accessors may need defensive copies.
- Enum: enum constants are non-null when referenced, but a **variable of an enum type can still hold null**; `switch(null)` on an enum does not automatically handle "unknown" safely in Java 17.

### Cases Needing "No State"

Do not invent an `UNKNOWN` enum constant if the domain does not want it; you can use `Optional` at an appropriate boundary, or an explicit status. `Optional` is primarily suited as a return type per JDK guidance, not used by default for every field/parameter.

### An Empty Object Is Not Automatically Invalid

`List.of()` is a valid unmodifiable empty list. Rules forbidding empty/null depend on the domain.

## 55. Runnable: Validating a Value Record and Enum

Save **`ValidatedProfileDemo.java`**:

```java
import java.util.Objects;

enum Membership {
    BASIC, PREMIUM
}

record Profile(String name, Membership membership) {
    Profile {
        name = Objects.requireNonNull(name, "name").strip();
        Objects.requireNonNull(membership, "membership");

        if (name.isEmpty()) {
            throw new IllegalArgumentException("empty name");
        }
    }
}

public class ValidatedProfileDemo {
    public static void main(String[] args) {
        Profile profile = new Profile(
                "  An  ", Membership.PREMIUM);

        System.out.println(profile);

        try {
            new Profile(" ", Membership.BASIC);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ValidatedProfileDemo.java
java ValidatedProfileDemo
```

Stdout:

```text
Profile[name=An, membership=PREMIUM]
empty name
```

Normalization in the compact constructor is part of **construction**; it does not allow subsequent mutation through record fields.

## 56. Builder When an Immutable Object Has Many Optional Attributes

An immutable class or record with too many overloaded constructors (especially many parameters of the same type) can make the API hard to understand:

```java
new Config("api", 30, true, false, 4, "asia", ...)
```

Solutions:
- Named static factories.
- A builder storing **mutable intermediate state** and then constructing an **immutable final object**.
- Group parameters into small, meaningful record value types.
- Use defaults where business rules are clear, without guessing.

The builder itself can be mutable while the **result** is immutable. This is a very common and completely reasonable combination.

## 57. Runnable: Mutable Builder Creating an Immutable Record

Save **`BuilderToRecordDemo.java`**:

```java
record Config(String host, int port, boolean tls) {
    Config {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port");
        }
    }
}

final class ConfigBuilder {
    private String host = "localhost";
    private int port = 8080;
    private boolean tls;

    ConfigBuilder host(String host) {
        this.host = host;
        return this;
    }

    ConfigBuilder port(int port) {
        this.port = port;
        return this;
    }

    ConfigBuilder tls(boolean tls) {
        this.tls = tls;
        return this;
    }

    Config build() {
        return new Config(host, port, tls);
    }
}

public class BuilderToRecordDemo {
    public static void main(String[] args) {
        Config config = new ConfigBuilder()
                .host("example.com")
                .port(443)
                .tls(true)
                .build();

        System.out.println(config);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BuilderToRecordDemo.java
java BuilderToRecordDemo
```

Stdout:

```text
Config[host=example.com, port=443, tls=true]
```

The builder uses mutable fields as a construction helper; the `Config` record is created at the end and validates invariants. The client can discard the Builder after building.

## 58. When Should You Not Turn a Class into a Record?

Signs:
- The class needs its own superclass (a record already extends `java.lang.Record`).
- The class must be subclassed/proxied by a framework architecture.
- The object undergoes many internal state changes that require identity.
- The API wants to completely hide its representation behind public methods.
- Additional non-static instance fields beyond the components are needed.
- Equality should not automatically be tied to the record header.
- Field data is a mutable graph that is hard to snapshot/defensively copy.
- Backward compatibility with existing getters/constructors is important.
- The class holds a file/socket/resource lifecycle and should have an explicit `close()`.

**There is no absolute prohibition:** a record can implement `AutoCloseable` if its components hold resources; however, a record does not automatically solve ownership, aliasing, idempotency, and premature closing. For a resource-owning lifecycle, an explicit class usually represents state better.

## 59. When Is an Immutable Class Better Than a Record?

Examples:
- An immutable wrapper around a mutable array needing custom value equality and input/output cloning.
- A class that hides internal indexing/caching/layout.
- Multiple construction forms with a normalized representation that you do not want to expose in record components.
- The public API keeps `getX()` or an existing abstraction.
- Value semantics require custom invariants where record-generated methods do not truly fit.

**Nor should you conclude that records are only for DTOs:** if the components make sense, a domain value object such as `Money`, `DateRange`, or `Coordinate` fits a record very well. What matters is the contract.

## 60. When Should an Enum Not Be the Source-of-Truth Data?

Do not choose an enum when:
- Hundreds/millions of products/countries/users are managed dynamically.
- Users/admins are allowed to add options without deploying code.
- Each option has its own data that varies per tenant/request.
- There are complex effective date ranges/versioning for category entries.
- IDs from the database are not stable across deployments.
- The system must handle future codes not yet present in the source.

Replace it with an immutable class/record describing **an entity/value from the database**, with a stable ID and repository/service. An enum can still be used for the **kind** of the entity, rather than replacing the entire entity.

## 61. Runnable: Dynamic Data as a Record, Fixed Category as an Enum

Save **`DynamicDataVsEnumDemo.java`**:

```java
enum ProductKind {
    BOOK, TOOL
}

record Product(String id, String name, ProductKind kind) {
}

public class DynamicDataVsEnumDemo {
    public static void main(String[] args) {
        Product one = new Product("P-1", "Guide", ProductKind.BOOK);
        Product two = new Product("P-2", "Hammer", ProductKind.TOOL);

        System.out.println(one.name());
        System.out.println(two.kind());
        System.out.println(one.equals(two));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DynamicDataVsEnumDemo.java
java DynamicDataVsEnumDemo
```

Stdout:

```text
Guide
TOOL
false
```

The Products are data instances with different IDs; `ProductKind` is a fixed set of symbols. If Product needs to update inventory/status on the instance itself, consider a mutable entity + record snapshot instead of a record entity.

## 62. A Class Can Be Immutable Yet Still "Entity-Like"

Not every entity is **forced to be mutable in-memory**. An event-sourced domain can represent entities using immutable state snapshots and replace references when a new event arrives, while the business identity remains a fixed ID.

Example:

```java
record AccountState(String accountId, long balance) {
    AccountState deposit(long amount) {
        return new AccountState(
                accountId, Math.addExact(balance, amount));
    }
}
```

Here the `accountId` is the same across different snapshots, while AccountState's `equals` distinguishes different balances. If the application asks "same entity?", compare `accountId`; if it asks "same snapshot value?", use `equals` based on components.

**Do not equate "business identity" with Java object identity or auto-generated record equals**.

## 63. API Boundaries: What Is Shared and Who Can Modify It?

An effective strategy:
- Inside the application/domain core, mutable aggregates can exist under a clear owner.
- When sending data across a boundary (API, queue, UI state), create an immutable snapshot/record.
- Enums represent finite category codes.
- Immutable value objects hold address, money, and time invariants.
- Collections at boundaries should be snapshotted/copied, without exposing mutable internal references unless the API intentionally allows mutation.

In a multi-threaded system, immutable snapshots reduce aliasing, yet you still need to serialize/coordinate updates to the mutable source.

### Do Not "Transfer Ownership" with Comments Alone

If you return a direct reference to an internal mutable list, the consumer can mutate the state even if documentation says read-only. The API should protect the representation with a copy/unmodifiable wrapper matching the semantics, or clearly declare a shared ownership contract.

## 64. API and Testing: What to Test for Each Type?

**Mutable class:**
- State before/after operations.
- Invariants on every mutation path.
- Aliasing and concurrent updates if multiple threads are involved.
- Identity/business ID.
- Unsubscribe/close lifecycle if applicable.

**Immutable class:**
- State cannot be modified after creation.
- Input/output defensive copies (including nested mutables).
- Equality/hash consistency.
- Factory/constructor validation.
- No publishing of partially initialized state.

**Record:**
- Canonical validation, normalization.
- Generated component accessors/toString/equality semantics match the domain.
- No mutable aliasing if intended to be immutable.
- Array/list component caveats.
- Serialization/mapper compatibility according to the environment.

**Enum:**
- Constants, switch behavior.
- Stable code uniqueness and reverse lookup.
- Unknown code/null policy.
- No mutable per-request state.
- Persisted schema migration compatibility when changing constants.

## 65. A Test Suite Without External Libraries

Save **`DesignContractTestDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

enum Level {
    BASIC, PRO
}

record Config(List<String> names, Level level) {
    Config {
        names = List.copyOf(names);
        if (level == null) {
            throw new IllegalArgumentException("level");
        }
    }
}

public class DesignContractTestDemo {
    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("contract");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Config config = new Config(source, Level.PRO);
        source.add("B");

        require(config.names().equals(List.of("A")));
        require(config.level() == Level.PRO);
        require(config.equals(
                new Config(List.of("A"), Level.PRO)));

        try {
            config.names().add("C");
            throw new AssertionError("expected unmodifiable");
        } catch (UnsupportedOperationException expected) {
            // OK.
        }

        System.out.println("PASS");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DesignContractTestDemo.java
java DesignContractTestDemo
```

Stdout:

```text
PASS
```

The test verifies record value semantics, snapshot copy, unmodifiable list, and enum identity. It does not rely on GC, timing, or external frameworks.

## 66. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| "`final class` = immutable" | Instance fields can still be mutable | Private final fields + defensive copies + no mutation |
| "`final List` = unmodifiable list" | Final only prevents reassigning the reference | `List.copyOf` or an immutable collection per the contract |
| "`record` = deep immutable" | Components can hold mutable references | Clone/copy + immutable elements |
| "Record array equals compares content" | Array component uses reference equality by default | Custom value wrapper / consistent deep comparator |
| "Immutable needs every setter to deserialize" | Frameworks differ; constructor binding may be supported | Check the serializer/version |
| "Enum has one instance per order" | Enum constant is a shared value | Mutable Order containing an enum field |
| "Enum is always immutable" | Mutable enum instance fields are allowed by the language | Do not use mutable enum global state |
| "Enum ordinal is stable" | Declaration order can change | Stable explicit code |
| "Record works like an ORM entity in every framework" | Finality/canonical constructor/proxies have constraints | Use DTO/embeddable according to framework support |
| "HashMap keys can be mutated freely" | Hash/equality can change | Immutable keys or do not modify key-state |
| "Value equality is the same as identity" | Two objects with equals true can still differ by `==` | Separate ID and component equality |
| "An immutable object is always thread-safe" | Unsafe publication/transitive mutation can still exist | Deep immutable design + proper publication |
| "`List.copyOf` deep copies" | Shallow-copies the element references | Convert elements to immutable |
| "Mutable class is always inferior to record" | There are use cases requiring identity/mutation | Design according to lifecycle |
| "Record is definitely faster than class" | There is no performance guarantee | Benchmark the workload |
| "Enum fits data added from DB" | Constants are fixed at compile/deploy time | Record/class with stable IDs |
| "Sealed variants use stable pattern switch in Java17" | Java17 pattern switch is preview | Stable `instanceof`/polymorphism |

## 67. Design Decision Checklist

- [ ] Is this a **fixed set of symbols** or arbitrary values?
- [ ] If a fixed set, are the enum constants stable and finite?
- [ ] If the enum is persisted, does it have a stable code beyond ordinal?
- [ ] If constants are renamed/reordered, are external consumers protected?
- [ ] Does the enum accidentally store mutable per-request data?
- [ ] Does the object have its own business identity?
- [ ] Do we need to update the **same instance** after initialization?
- [ ] If mutable, do the operations protect invariants?
- [ ] If mutable, are concurrency/transactions designed?
- [ ] Do we want equality based on all component values?
- [ ] If a value carrier, does the record header accurately describe the representation?
- [ ] Does the record need custom normal/compact canonical validation?
- [ ] Does the record have a mutable list/array/component object?
- [ ] Are defensive copies applied to both input and output where needed?
- [ ] Is `List.copyOf` sufficient, or are there still mutable elements?
- [ ] If there is an array component, have you considered generated equals/hashCode?
- [ ] If an immutable class, have subclasses been prevented from altering invariants?
- [ ] If an immutable class, are private final state and escape safety complete?
- [ ] Do you need to hide the representation more than a record allows?
- [ ] If BigDecimal, have scale/rounding/equality rules been defined?
- [ ] Do hash-based keys have stable equals/hashCode throughout their time in the map?
- [ ] Do the mutable entity and immutable snapshot have distinct roles?
- [ ] Is DTO/request/response suitable for record mapping in the actual framework?
- [ ] If the ORM needs proxies/no-arg constructors, have the constraints been checked?
- [ ] If inheritance is needed, have record/enum been ruled out from unsuitable superclass positions?
- [ ] If there are multiple variants each with its own payload structure, is sealed interface + record better than enum?
- [ ] Does the API need a builder/named factory instead of hard-to-read constructor overloads?
- [ ] Is the null/unknown/invalid value policy enforced in constructors/factories?
- [ ] Are live mutable internal collections prevented from being exposed if the contract is read-only?
- [ ] Is source/binary/serialization compatibility preserved when changing a class to a record?
- [ ] Have you benchmarked before making "optimization" changes that go against semantics?
- [ ] Are there tests for value semantics, identity, mutation, and defensive copies?
- [ ] Are there tests for stable enum codes and unknown data?
- [ ] Is every choice justified by domain rules, not just syntax preference?

## 68. Exercise 1 — A Coordinate

You need to store longitude/latitude, do not want mutation, and compare equality by the two values.

**Answer:** Record `Coordinates(double latitude,double longitude)` or an immutable class if there is special validation/representation. With a record, use a compact canonical constructor to validate ranges according to the domain.

## 69. Exercise 2 — Shopping Cart

A shopping cart has a fixed ID, and the user adds/removes items within the same session.

**Answer:** A mutable class/aggregate with `addItem/removeItem` operations and invariants. It can provide an immutable record snapshot for the UI.

## 70. Exercise 3 — Payment Status

The set of states `NEW, PAID, CANCELLED` is fixed.

**Answer:** Enum. If the status belongs to each Order, place an `OrderStatus status` field inside Order; do not put per-order state into the enum constant.

## 71. Exercise 4 — Countries from a Database

An admin can add a new country/category in the database without deploying.

**Answer:** Do not force it into an enum; use a class/record data type with a stable ID and repository. An enum is only appropriate if it is a fixed set controlled by source code.

## 72. Exercise 5 — HTTP Response DTO

The response has `id`, `name`, `createdAt`, is not mutated, and the mapper supports Java 17 records.

**Answer:** A record makes sense, with immutable components and validation if needed. You should check the serialization names/types of the specific framework.

## 73. Exercise 6 — Final Field

Does `private final List<String> names = new ArrayList<>();` guarantee that names cannot be modified?

**Answer:** No. The field reference cannot be reassigned, but the ArrayList contents can be mutated.

## 74. Exercise 7 — Array Record

`record Bytes(byte[] data) {}`. Why should it not be considered deeply immutable?

**Answer:** The caller and accessor can mutate the same array; generated record equality compares array references rather than deep content. You need cloning and a custom equality policy or an immutable wrapper.

## 75. Exercise 8 — New Immutable Value

An immutable Range has a `shift(5)` method. What should it do?

**Answer:** Return a new Range; do not mutate the current instance.

## 76. Exercise 9 — Record State Update

`record OrderState(String id, Status status)` wants to transition NEW→PAID.

**Answer:** A method can validate the transition and then return a new `OrderState(id,PAID)`. If you want the same entity instance to mutate, use a mutable class with an enum field.

## 77. Exercise 10 — Enum Ordinal

Persisting `Status.PAID.ordinal()` as an integer. What is the risk?

**Answer:** Reordering/inserting constants changes the meaning of the code; use an explicit stable code with a migration strategy.

## 78. Exercise 11 — Enum Mutable Field

`enum Mode { ACTIVE; int counter; }` and multiple requests increment counter.

**Answer:** The counter is shared across everywhere ACTIVE is used, making races/global state likely. Do not store request data in an enum.

## 79. Exercise 12 — Mutable Map Key

A key has equals/hashCode based on name, and name is modified after `map.put(key,value)`.

**Answer:** It can cause hash lookups to fail or become inconsistent. Use an immutable key or stable identity fields.

## 80. Exercise 13 — List.copyOf

A record stores `List<MutableItem>` via `List.copyOf`; is it deeply immutable?

**Answer:** No. The list structure is unmodifiable, while elements remain mutable if references allow it.

## 81. Exercise 14 — Unmodifiable View

Is `Collections.unmodifiableList(source)` a snapshot?

**Answer:** No. Source mutations are still reflected in the view, unlike the `List.copyOf(source)` shallow snapshot.

## 82. Exercise 15 — Record Constructor

If you want to disallow `new Percentage(150)`, where do you place the validation?

**Answer:** In Percentage's compact canonical constructor (or explicit normal canonical constructor), throwing an exception when out of range.

## 83. Exercise 16 — Business Identity

Should two Accounts with the same balance but different IDs be equal?

**Answer:** It depends on the contract, but if Account is an identity-based entity, they are usually different entities; do not treat "same balance" as business identity.

## 84. Exercise 17 — Record equals

`new Point(1,2).equals(new Point(1,2))` with a Point record having primitive components.

**Answer:** True according to generated component equality; `==` between two new objects is false.

## 85. Exercise 18 — BigDecimal

What does `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` return?

**Answer:** False due to different scale; `compareTo==0`. Record component equality will reflect this if not normalized.

## 86. Exercise 19 — ORM Entity

A JPA framework requires proxy/no-arg constructors by implementation. Should you replace entities with records by default?

**Answer:** No. Check the spec/framework; a final record and its constructor conventions may not satisfy entity requirements. A record DTO projection can be a suitable use case if supported.

## 87. Exercise 20 — Variants with Payloads

A successful Result carries receiptId, while a failure carries error code + reason; you do not want many null fields.

**Answer:** A sealed interface + record/final class leaves, with Java 17 `instanceof` pattern matching or polymorphism.

## 88. Exercise 21 — Enum Singleton Identity

Is `Priority.HIGH == Priority.HIGH` reasonable?

**Answer:** Yes; an enum constant is a named singleton instance of the enum type within the runtime classloader context.

## 89. Exercise 22 — Immutable Factory

An object has 15 optional attributes; the constructor is very long.

**Answer:** A builder or named factories can help. The builder is mutable at the construction stage, and the result is an immutable class/record if copied/validated properly.

## 90. Exercise 23 — Thread Safety

Is `final class Counter { int n; void inc(){n++;}}` automatically thread-safe?

**Answer:** No. Final prevents subclassing; it does not guarantee the atomicity of `n++`.

## 91. Exercise 24 — Resource-Owning Class

An object holds a socket and has a close/reopen/error lifecycle.

**Answer:** A class with `AutoCloseable`/explicit resource state is usually more suitable than a pure data record. Do not wait for the GC finalizer to close.

## 92. Exercise 25 — Performance

Is "convert all immutable classes to records because records are definitely faster" correct?

**Answer:** No. Records carry no general performance guarantee; choose semantics first and benchmark if truly needed.

## 93. Exercise 26 — API Compatibility

Is changing `class User { String getName(); }` to `record User(String name)` completely source-compatible?

**Answer:** Not automatically. A record generates the `name()` accessor rather than automatically providing `getName()`, and has different finality/constructor/serialization behavior. You need to keep the API or do an explicit migration.

## 94. Exercise 27 — Mutable Snapshot

When entity state changes, should an already-created record snapshot update itself automatically?

**Answer:** No, if the snapshot properly contains primitive/immutable value copies; a snapshot describes the state at the time it was constructed.

## 95. Exercise 28 — Stable Enum Code

An enum has `code="P"` for PAID and the constant is reordered. What remains stable?

**Answer:** The explicit code P remains stable if the developer keeps the contract. Ordinal can change; `name()` can change if the source name is renamed.

## 96. Exercise 29 — Dynamic Set of Values

A workflow status table is configured per customer/tenant.

**Answer:** Do not use an enum by default for all dynamic statuses; you can use data-driven immutable status records/classes and validation from configuration. An enum can still be used for system-level categories that remain fixed.

## 97. Exercise 30 — Comprehensive Decision

A sales system needs: mutable Order, fixed OrderStatus, Money value, and OrderResponse sent via API.

**Answer:** Mutable class Order for lifecycle; enum OrderStatus for status symbols; immutable Money record/class for money; record OrderResponse for the API snapshot if the serialization framework supports it and the components are safe.

## 98. True/False Review

1. A mutable class is always a worse design than a record.
2. `final class` does not automatically prevent all mutation.
3. A record has private final fields for its components.
4. A record automatically deep-copies arrays and lists.
5. Record-generated equals for an array component deep-compares elements.
6. `List.copyOf` is a shallow snapshot with respect to mutable elements.
7. An enum is suitable for a predefined set of named constants.
8. An enum constant can have its state modified if the developer declares a mutable field.
9. An enum ordinal is a persistent database code across reordering.
10. A mutable entity can contain an enum status field.
11. An immutable record can return a new instance for a state transition.
12. A `HashMap` key whose hashCode changes is a safe design.
13. A record is always faster than a hand-written class on every JVM.
14. A sealed interface + record variants can model multiple payload shapes.
15. Java 17 `instanceof` pattern matching is a standard feature.
16. Java 17 pattern matching switch on sealed variants works without preview.
17. Two record Points with the same primitive components typically equal true.
18. `BigDecimal("1.0")` and `BigDecimal("1.00")` equal true.
19. A builder can be mutable while its result is immutable.
20. Type selection should follow the domain identity/value/lifecycle contract.

**Answers:** 1 false; 2 true; 3 true; 4 false; 5 false; 6 true; 7 true; 8 true; 9 false; 10 true; 11 true; 12 false; 13 false; 14 true; 15 true; 16 false; 17 true; 18 false; 19 true; 20 true.

## 99. Concise Decision Formula

- **"An object with identity and a changing progression?"** → mutable class with encapsulation/invariants and ownership.
- **"An unchanging value whose representation needs to be hidden?"** → hand-written immutable class.
- **"A value bundle with clear components, equality based on them, without wanting boilerplate?"** → record, with validation/defensive copy if needed.
- **"A finite set of constants from the source code?"** → enum, with a stable code for external data.
- **"A set of types with different payloads?"** → sealed interface + record/final variants.
- **"A process involving entities, values, and statuses?"** → combine multiple choices; do not force everything into the same construct.

**Most importantly:** the data type must reflect **what the program promises to API users**. Concise syntax and default generated behavior are means, not the goal.

## 100. Official Java SE 17 Documentation

- **JLS `8.10 — Record Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
- **JLS `8.10.4 — Record Constructors**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4
- **JLS `8.9 — Enum Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- **JLS `8.1 — Class Declarations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1
- **JLS `8.1.1.2 — Sealed and Final Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2
- **Java SE 17 `java.lang.Record` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html
- **Java SE 17 `java.lang.Enum` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
- **Java SE 17 `List.copyOf` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- **Java SE 17 `EnumSet` / `EnumMap` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html
- **Java SE 17 `BigDecimal` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
