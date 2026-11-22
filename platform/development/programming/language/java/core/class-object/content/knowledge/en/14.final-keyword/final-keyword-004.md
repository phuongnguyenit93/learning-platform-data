# A `final` Reference Can Still Point to a Mutable Object in Java

## 1. Core Idea: Locking the Reference Variable, Not the Object

In Java, the **`final` keyword placed on a reference-type variable** means: **after the variable is assigned a value according to the definite assignment rules, it cannot be reassigned to another reference value**. It **does not automatically make the referenced object immutable**.

Consider:

```java
final StringBuilder message = new StringBuilder("Java");

message.append(" Core"); // Valid: modifies the object's content.
// message = new StringBuilder("Other"); // Invalid: reassigning a final variable.
```

In this example:

- `message` is a **reference variable** declared as `final`.
- `new StringBuilder("Java")` creates **a mutable `StringBuilder` object**.
- `message.append(" Core")` is **a method call that modifies the object's state**, not a reassignment of the `message` variable.
- If you uncomment the assignment `message = ...`, the compiler rejects it: **a final variable that has already been assigned cannot receive a new reference**.

Before and after diagram:

```text
Before append:
message (final) ──────────> StringBuilder A {text="Java"}

After append:
message (final) ──────────> StringBuilder A {text="Java Core"}

The arrow from the variable to object A does not change.
Only the state inside object A changes.
```

The diagram illustrates **reference relationships according to Java semantics**, not a description of the object's physical address, memory cells, or how the JVM lays out the heap/stack.

> **Key takeaway:** `final` on a reference **forbids changing the object the variable points to via variable assignment**, but **does not forbid calling mutating methods or modifying the object's fields/array slots if access permissions allow**.

## 2. Distinguishing Three Conceptual Layers: Variable, Reference, and Object

Let's place each one in its proper role:

| Concept | Example | How does `final` affect it? |
| --- | --- | --- |
| **Reference variable** | `final Box box` | The `box` variable cannot be reassigned after it has been assigned |
| **Reference value** | A value pointing to a specific `Box`, or `null` | `final` does not make the target object read-only |
| **Object** | A `Box` with a `count` field | The object remains mutable if its design allows modifying `count` |
| **Object field** | `box.count` | Can be modified if the field and access permissions allow |
| **Object array** | `final Box[] boxes` | The `boxes` variable cannot point to another array; the array slots can be changed |
| **Child object** | `person.address().setCity(...)` | The child object can be mutated if a valid reference path exists |

Avoid the vague statement “`final` makes an object unchangeable”. The accurate statement depends on **where `final` is placed**:

- `final` on a **primitive variable** forbids reassigning the primitive value.
- `final` on a **reference variable** forbids reassigning the reference value.
- `final` on an **instance field** forbids reassigning the field after it has been initialized according to the rules; if the field holds a reference, the object behind the reference can still be mutable.
- `final` on a **class** prevents inheritance.
- `final` on an **instance method** prevents method overriding according to the applicable rules.
- `final` **is not** a mechanism to deep-freeze the entire object graph.

The scope of this article focuses on **reference-type variables/fields/parameters with `final`**, without conflating them with the last two cases.

## 3. Complete Runnable Java 17+ Example: Final Reference and Mutable Object

Create the file **`FinalReferenceDemo.java`**:

```java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    void add(int amount) {
        value += amount;
    }

    int value() {
        return value;
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final Counter counter = new Counter(10);

        System.out.println("before=" + counter.value());
        counter.increment();
        counter.add(4);
        System.out.println("after=" + counter.value());

        // counter = new Counter(99);
        // Uncommenting this will cause a compile error because counter is final.
    }
}
```

Compile and run:

```bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
```

**Standard output:**

```text
before=10
after=15
```

Step-by-step explanation:

1. `new Counter(10)` creates Counter object A with `value=10`.
2. `final Counter counter = ...` assigns the reference value pointing to A exactly once.
3. `counter.increment()` increments **A's state** from 10 to 11.
4. `counter.add(4)` increases **A's state** to 15.
5. The `counter` variable **still points to A**, with no `counter = ...` assignment anywhere in the executed code.
6. A new assignment to `counter` is rejected by the compiler, even an assignment pointing back to the very same old object.

**Notable point:** `Counter.value` here is `private`. The caller is not allowed to write `counter.value = 15`; however, the `increment`/`add` methods of the Counter class still have permission to modify the state. `private` access control and the `final` rule on the caller's variable are **two different mechanisms**.

## 4. Why Calling a Setter Is Allowed, but Reassigning the Variable Is Not

Compare these two expressions:

```java
final Counter counter = new Counter(1);

counter.increment();        // Valid: calls a method on the object.
// counter = new Counter(2); // Invalid: changes the value of the counter variable.
```

The first snippet has no assignment to **the `counter` variable**. At runtime, the method receives object A as its receiver and changes A's `value` field. The second snippet (if uncommented) assigns a **new reference value** into the `counter` variable slot itself, violating the final constraint.

A mutating method call may contain an assignment **inside the method**, for example:

```java
void increment() {
    value = value + 1;
}
```

The assignment here targets **the `value` field of the Counter object**, not the caller's final variable.

**Analysis tip:** Pause at the `=` sign or assignment operator and ask, “Where is the **lvalue** (the location being assigned to)?”:

- `counter = other` → assigns to **the final variable**: invalid after initialization.
- `counter.value = 5` → assigns to **an object field**: can be valid if the field is accessible and not final.
- `counter.increment()` → calls a method, which may indirectly assign to a field: valid if the method/receiver is accessible.
- `counters[0] = other` → assigns to **an array slot**, not the `counters` variable.

Java checks **the location being assigned to**, rather than checking “because the caller declared final, any reachable object must also be frozen”.

## 5. `final` and Aliasing: Multiple Variables Pointing to the Same Object

`final` does not prevent other variables from holding the same reference value. The phenomenon of multiple variables/fields/slots pointing to the same object is called **aliasing**.

Example:

```java
Counter shared = new Counter(5);
final Counter left = shared;
Counter right = shared;

right.increment();

System.out.println(left.value());  // 6
```

This is **a code snippet using the Counter class from the previous example**. Both `left` and `right` reference Counter A. The fact that `left` is final **does not forbid** `right` from calling a mutating method on A.

Diagram:

```text
shared ─────┐
left final ─┼─────────> Counter A {value=5}
right ──────┘

After right.increment():

shared ─────┐
left final ─┼─────────> Counter A {value=6}
right ──────┘
```

### Runnable Program: Mutation Through a Non-Final Alias

File **`FinalAliasDemo.java`**:

```java
class Label {
    private String text;

    Label(String text) {
        this.text = text;
    }

    void rename(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class FinalAliasDemo {
    public static void main(String[] args) {
        Label shared = new Label("old");

        final Label fixed = shared;
        Label movable = shared;

        movable.rename("updated");

        System.out.println("fixed=" + fixed.text());
        System.out.println("same=" + (fixed == movable));

        movable = new Label("new object");

        System.out.println("fixed=" + fixed.text());
        System.out.println("movable=" + movable.text());
        System.out.println("same=" + (fixed == movable));
    }
}
```

```bash
javac FinalAliasDemo.java
java FinalAliasDemo
```

```text
fixed=updated
same=true
fixed=updated
movable=new object
same=false
```

Explanation:

- `fixed` is final and `movable` is non-final, yet initially both point to `Label A`.
- `movable.rename("updated")` mutates A; reading through `fixed` also sees `updated`.
- `movable = new Label("new object")` only **reassigns the `movable` variable**; it does not make `fixed` switch to the new object.
- Final restricts assignment **per variable**; it does not create an immutable link across all aliases.

## 6. Reassigning the Same Old Reference Is Also Forbidden

It is not only “pointing to a different object” that violates final. The compiler enforces the rule against **reassigning the variable after initialization**, regardless of whether the new value is `==` to the old value or not.

```java
final StringBuilder b = new StringBuilder("A");

// b = b;              // Invalid: still a reassignment of the final variable.
// b = null;           // Invalid: reassigning the final variable.
// b = new StringBuilder("A"); // Invalid even though the text looks the same.
b.append("B");         // Valid: modifies object state.
```

One case worth remembering:

```java
final StringBuilder b = null;

// b = new StringBuilder(); // Invalid: b has already been assigned null.
```

`null` is also a **valid value for initializing a final reference variable**. Once `b` is assigned `null`, it can no longer be assigned another object. Calling `b.append(...)` will throw a `NullPointerException` because there is no object receiving the call.

**Do not say that `final` guarantees non-null.** `final` and “cannot be null” are two different properties.

## 7. A `final` Local Variable Can Be Assigned Once Later

An initializer does not have to be present on the declaration line itself. For local variables, Java applies the **definite assignment** and **final assignment** rules:

```java
final StringBuilder buffer;

if (System.currentTimeMillis() >= 0) {
    buffer = new StringBuilder("A");
} else {
    buffer = new StringBuilder("B");
}

buffer.append("!");
System.out.println(buffer);
```

This is **an illustrative snippet inside a method**. Each branch assigns the `buffer` variable once along its execution path; after the `if/else` statement, the variable is definitely assigned, so it can be used. The output depends on a runtime condition, so this snippet **is not presented as a program with fixed stdout**.

You should also avoid:

```java
final StringBuilder buffer = new StringBuilder("A");

// buffer = new StringBuilder("B"); // Invalid: second assignment.
```

**Core point:** “`final`” means **the variable is initialized according to the rules and then not reassigned**; it does not mean you must use the `final T x = ...` syntax on the same line in every case.

## 8. `final` Parameters: You Cannot Reassign the Parameter, but You Can Still Modify the Object

A method parameter is a **local variable belonging to the method call**. If declared `final`, that parameter cannot be reassigned. However, if the parameter receives a reference to a mutable object, the method can still modify the object.

File **`FinalParameterDemo.java`**:

```java
class Note {
    private String text;

    Note(String text) {
        this.text = text;
    }

    void append(String suffix) {
        text += suffix;
    }

    String text() {
        return text;
    }
}

public class FinalParameterDemo {
    static void edit(final Note note) {
        note.append("!");

        // note = new Note("other");
        // Invalid: cannot reassign a final parameter.
    }

    public static void main(String[] args) {
        Note note = new Note("Hello");

        edit(note);

        System.out.println(note.text());
    }
}
```

```bash
javac FinalParameterDemo.java
java FinalParameterDemo
```

```text
Hello!
```

**Why does the caller see the change?**

Java passes arguments by **value** (*pass-by-value*). For reference types, the copied value is **the reference value pointing to the same Note object**, not a deep copy of Note. The caller's variable and the final parameter can both point to the same Note A, so `note.append(...)` mutates the shared object. `final` only restricts reassigning **the method's parameter**.

If you omit `final` on the parameter and assign `note = new Note("other")`, that operation still **does not reassign the caller's variable**. However, that is due to Java pass-by-value, **not because of `final`**.

### `final` Does Not Guarantee a “Read-Only” Method

A method accepting `final List<String> values` can still call `values.add(...)` if the list is mutable. Therefore, the promise “this method does not modify the input” must be enforced through **contract, implementation, types, and defensive copying**, and cannot be inferred solely from the `final` keyword.

## 9. Reference-Type `final` Fields: The Field Does Not Change, the Object Remains Mutable

A field declared `final` can hold a reference to a mutable object:

```java
class Task {
    private final StringBuilder description;

    Task(String initial) {
        description = new StringBuilder(initial);
    }

    void addDetail(String detail) {
        description.append(detail);
    }

    String description() {
        return description.toString();
    }
}
```

If `Task task = new Task("A");` is executed and then `task.addDetail("B")` is called:

- The `description` field was initialized exactly once in the constructor.
- The constructor and methods do not assign the field to a different `StringBuilder`.
- The `StringBuilder` behind the field still changes its content from `A` to `AB`.

**Distinguishing three data layers:**

```text
task variable
      |
      v
Task object
   |
   +-- description [final reference] ───> StringBuilder A
                                         mutable text
```

`final` is placed on Task's **`description` reference field**, not on every byte of data reachable from that field.

### Blank Final Field

A `final` field may be left uninitialized at its declaration:

```java
class Holder {
    private final StringBuilder content;

    Holder(String text) {
        this.content = new StringBuilder(text);
    }

    void append(String text) {
        content.append(text);
    }
}
```

For a **blank final instance field**, every constructor that completes normally must ensure the field is initialized according to Java rules. Afterward, `content` cannot be reassigned from an instance method. However, `content.append(...)` remains valid.

**This protects the identity of the object whose reference the field holds, not automatically the content of that object.**

## 10. Standalone Java 17+ Example: Final Field and Object State

File **`FinalFieldDemo.java`**:

```java
class Journal {
    private final StringBuilder text;

    Journal(String initial) {
        this.text = new StringBuilder(initial);
    }

    void write(String line) {
        text.append("|").append(line);
    }

    String read() {
        return text.toString();
    }
}

public class FinalFieldDemo {
    public static void main(String[] args) {
        final Journal journal = new Journal("start");

        journal.write("first");
        journal.write("second");

        System.out.println(journal.read());

        // journal = new Journal("new");  // Invalid: the journal variable is final.
        // Inside Journal, the text field cannot be reassigned after initialization either.
    }
}
```

```bash
javac FinalFieldDemo.java
java FinalFieldDemo
```

```text
start|first|second
```

Two underlying `final` layers to distinguish:

1. The local variable `journal` is final and cannot point to a different `Journal` object.
2. The `Journal.text` field is also final and cannot point to a different `StringBuilder` object after initialization.

**However,** the `StringBuilder` object is still mutable, so calls to `journal.write(...)` modify its content. True encapsulation comes from `Journal` only allowing callers to modify content through the `write` method, not from a deep immutability guarantee automatically generated by `final`.

## 11. Arrays: `final T[]` Does Not Mean the Elements Are Final

A Java array is an **object**, and its elements are **slots whose values can be changed**, unless otherwise constrained by design (standard Java arrays do not have `final` on individual slots merely because the array variable is final).

```java
final int[] numbers = {1, 2, 3};

numbers[0] = 99;           // Valid: modifies slot 0 of the array.
// numbers = new int[3];  // Invalid: reassigns the final variable.
```

Similarly for a reference array:

```java
final StringBuilder[] builders = new StringBuilder[2];

builders[0] = new StringBuilder("A");  // Modifies a slot of the array object.
builders[0].append("B");             // Modifies the element object.
builders[1] = builders[0];           // Copies the reference to another slot.
```

Here there are **three layers**:

1. **The final variable `builders`** cannot point to a different array object.
2. **The array object** has slots `[0]`, `[1]`, and these slots can still be assigned.
3. **The StringBuilder element object** is also mutable; multiple slots can point to it at the same time.

### Runnable Program: Both Replacing Slots and Mutating Elements

File **`FinalArrayDemo.java`**:

```java
public class FinalArrayDemo {
    public static void main(String[] args) {
        final StringBuilder[] parts = new StringBuilder[2];

        parts[0] = new StringBuilder("A");
        parts[1] = parts[0];

        parts[1].append("B");

        System.out.println(parts[0]);
        System.out.println(parts[1]);
        System.out.println(parts[0] == parts[1]);

        parts[1] = new StringBuilder("C");

        System.out.println(parts[0]);
        System.out.println(parts[1]);
        System.out.println(parts[0] == parts[1]);

        // parts = new StringBuilder[3]; // Invalid: final reference.
    }
}
```

```bash
javac FinalArrayDemo.java
java FinalArrayDemo
```

```text
AB
AB
true
AB
C
false
```

Explanation:

- `parts[1] = parts[0]` creates an **alias**: both slots point to StringBuilder A.
- `parts[1].append("B")` modifies A, so both positions read `AB`.
- `parts[1] = new StringBuilder("C")` modifies **slot 1** to point to object B. Slot 0 still points to A.
- No step reassigns **the final variable `parts`**; it always points to the original array object.

**Common mistake:** seeing `final StringBuilder[]` and assuming that both the array and the StringBuilders inside it are immutable. That is incorrect.

## 12. `final` on a Collection Reference Does Not Make the Collection Immutable

Consider:

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();

names.add("An");
names.add("Binh");
names.set(0, "Chi");
names.remove("Binh");

// names = new java.util.ArrayList<>(); // Invalid: final.
```

The `names` variable keeps the same reference to the `ArrayList`, but `add`, `set`, and `remove` mutate **the collection object**.

A similar case:

```java
final java.util.Map<String, Integer> scores =
        new java.util.HashMap<>();

scores.put("An", 10);
scores.put("An", 20);
```

`scores` is final, yet the map's contents still change from `{"An":10}` to `{"An":20}`.

### Runnable Example: A Final List Still Allows Adding and Removing Elements

File **`FinalCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalCollectionDemo {
    public static void main(String[] args) {
        final List<String> colors = new ArrayList<>();

        colors.add("red");
        colors.add("blue");

        System.out.println("initial=" + colors);

        colors.set(0, "green");
        colors.remove("blue");

        System.out.println("updated=" + colors);

        // colors = List.of("black"); // Invalid: colors is final.
    }
}
```

```bash
javac FinalCollectionDemo.java
java FinalCollectionDemo
```

```text
initial=[red, blue]
updated=[green]
```

**Key distinction:** “Not changing the List's reference” is different from “not changing the List's elements”. `final` only means the first one.

## 13. A `static final` Collection Can Still Be Modified and Widely Shared

This is an API design pitfall:

```java
public final class SharedNames {
    public static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();

    private SharedNames() {
    }
}
```

Even though `NAMES` is `public static final`:

- `static`: the field belongs to the class, not to each individual instance.
- `final`: the field cannot be reassigned from places not permitted to assign to it according to the rules.
- `public`: many callers can see the reference.
- **The `ArrayList` object is still mutable**: callers can call `SharedNames.NAMES.add("X")`.

**Consequences:** other components in the same process may observe unexpected data changes; tests may pollute each other's state; multiple threads may access it unsafely if synchronization is lacking.

An option for a fixed list of values:

```java
public final class SharedNames {
    public static final java.util.List<String> NAMES =
            java.util.List.of("An", "Binh");

    private SharedNames() {
    }
}
```

`List.of` returns an **unmodifiable** list, so `NAMES.add(...)` throws `UnsupportedOperationException` instead of modifying the list's structure. However, **an unmodifiable collection does not imply deep immutability of every element object**. In this example, the `String` elements are immutable, so it is easy to reason about.

**Do not confuse them:** `static final` is suitable for a constant reference, but protecting all reachable values as well requires examining **the type and implementation of the referenced object**.

## 14. `final` Differs from `Collections.unmodifiableList`

`Collections.unmodifiableList(source)` creates a **view that does not allow mutating operations through the view**. However, if `source` is a mutable list and has another alias, the view can reflect changes made through the source.

Example:

```java
java.util.List<String> source = new java.util.ArrayList<>();
source.add("A");

final java.util.List<String> view =
        java.util.Collections.unmodifiableList(source);

source.add("B");

System.out.println(view); // [A, B]
```

This is **an illustrative code snippet inside a method**.

Two independent points:

- `view` is final: the `view` variable cannot be reassigned.
- `view` is unmodifiable: `view.add("C")` cannot succeed according to the view contract.
- However, `source.add("B")` modifies the backing list; `view` can see the new data.

### Complete Program Illustrating Alias and View

File **`UnmodifiableViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        final List<String> view =
                Collections.unmodifiableList(source);

        System.out.println("before=" + view);

        source.add("B");
        System.out.println("after source change=" + view);

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view cannot add");
        }

        System.out.println("source=" + source);
    }
}
```

```bash
javac UnmodifiableViewDemo.java
java UnmodifiableViewDemo
```

```text
before=[A]
after source change=[A, B]
view cannot add
source=[A, B]
```

**Conclusion:** to call a variable “read-only”, you must specify **which reference it is read through**, **whether the object is shared with another alias**, and **whether a snapshot or a live view is needed**. `final` alone does not answer these questions.

## 15. `List.copyOf`: Detaches the List's Structure, but Is a Shallow Copy of the Elements

In Java 17+, `List.copyOf(collection)` returns an unmodifiable list containing the corresponding elements at the time of creation. For an ordinary mutable list source, it creates a **structural snapshot copy** (the implementation may reuse the source object if the source is already an immutable list conforming to the contract).

Example:

```java
java.util.List<String> source = new java.util.ArrayList<>();
source.add("A");

final java.util.List<String> snapshot = java.util.List.copyOf(source);

source.add("B");

System.out.println(snapshot); // [A]
System.out.println(source);   // [A, B]
```

Here, `snapshot` does not automatically become `[A, B]` when new elements are later added to the mutable source list.

**However:** if the elements are mutable objects, `List.copyOf` **does not deep-copy each object**. They remain element reference values, which can be shared.

### Runnable Example: Snapshot Structure with Shared Mutable Elements

File **`ShallowSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Task {
    String title;

    Task(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return title;
    }
}

public class ShallowSnapshotDemo {
    public static void main(String[] args) {
        List<Task> source = new ArrayList<>();
        Task shared = new Task("Draft");
        source.add(shared);

        final List<Task> snapshot = List.copyOf(source);

        source.add(new Task("Review"));
        shared.title = "Updated";

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot);
        System.out.println("same element=" +
                (source.get(0) == snapshot.get(0)));
    }
}
```

```bash
javac ShallowSnapshotDemo.java
java ShallowSnapshotDemo
```

```text
source=[Updated, Review]
snapshot=[Updated]
same element=true
```

Reading each difference:

- `source.add(new Task("Review"))` mutates **the source list structure**; it does not add a slot to the snapshot.
- `shared.title = "Updated"` mutates **the shared Task object** referenced by both lists, so `snapshot` prints `Updated`.
- `final List<Task> snapshot` does not make the `Task` objects immutable.

**Warning:** `List.copyOf` does not accept null elements by contract; if nulls need to be preserved, choose another strategy and document it clearly. With a mutable source modified concurrently without synchronization, thread-safety and snapshot consistency must also be considered.

## 16. Defensive Copies and Object Ownership

A class with a `private final List<...>` field might appear encapsulated, but if it directly stores the input reference, the caller can still mutate the same object.

Example:

```java
class UnsafeTeam {
    private final java.util.List<String> members;

    UnsafeTeam(java.util.List<String> members) {
        this.members = members;
    }

    int size() {
        return members.size();
    }
}
```

If the caller continues calling `input.add(...)`, `UnsafeTeam`'s `members` field still points to **the same input list**, because the constructor only assigned the reference. The fact that the field is final does not prevent the caller's alias from modifying the list.

Defensive design:

```java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> source) {
        this.members = java.util.List.copyOf(source);
    }

    java.util.List<String> members() {
        return members;
    }
}
```

With immutable `String` elements and non-null input, using `List.copyOf` creates an appropriate unmodifiable snapshot. The caller cannot add or remove elements via the getter or via the source list to alter the internal structure. However, with `List<MutablePerson>`, you must decide **whether each MutablePerson needs a defensive copy**.

### Complete Example: Final Field + Copying the Input

File **`DefensiveFinalFieldDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> names;

    Team(List<String> source) {
        names = List.copyOf(source);
    }

    List<String> names() {
        return names;
    }
}

public class DefensiveFinalFieldDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        final Team team = new Team(input);

        input.add("Binh");

        System.out.println("input=" + input);
        System.out.println("team=" + team.names());

        try {
            team.names().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("team list unmodifiable");
        }
    }
}
```

```bash
javac DefensiveFinalFieldDemo.java
java DefensiveFinalFieldDemo
```

```text
input=[An, Binh]
team=[An]
team list unmodifiable
```

Here there are **two final references** in two places:

1. The local variable `team` is final and cannot be reassigned to another Team object.
2. The `Team.names` field is final and cannot be assigned to another list.

More importantly, **the internal list object** itself is designed to be unmodifiable and is created from a separate snapshot. **The observable immutability** in this example comes from combining an **immutable element type (`String`)**, a **snapshot**, and **not exposing mutable state**, not merely from the two final keywords.

## 17. A Getter Returning a Reference to a Mutable Field: `final` Does Not Replace Encapsulation

Suppose:

```java
class EventLog {
    private final StringBuilder log = new StringBuilder();

    StringBuilder getLog() {
        return log;
    }
}
```

The `getLog()` getter returns **the exact same reference** held by the final `log` field. If the caller runs:

```java
EventLog event = new EventLog();
event.getLog().append("injected");
```

the caller mutates the content of **EventLog's StringBuilder** even though the `log` field is `private final`.

A safer API can:

- Return only a **String snapshot** via `return log.toString();`.
- Provide methods with contract checks to add log entries.
- If complex mutable objects are needed, return a defensive copy instead of the internal reference.
- If multiple threads are involved, manage synchronization/visibility according to the contract.

**`private` forbids direct field access from classes without permission, and `final` forbids reassigning the field; neither forbids all indirect operations on the object referenced by the field if the API leaks the reference.**

## 18. Java 17+ Example: Returning a Snapshot Instead of a Mutable Reference

File **`SafeLogDemo.java`**:

```java
class EventLog {
    private final StringBuilder content = new StringBuilder();

    void append(String event) {
        if (event == null || event.isBlank()) {
            throw new IllegalArgumentException("event required");
        }
        if (content.length() > 0) {
            content.append("|");
        }
        content.append(event);
    }

    String snapshot() {
        return content.toString();
    }
}

public class SafeLogDemo {
    public static void main(String[] args) {
        final EventLog log = new EventLog();

        log.append("start");

        String captured = log.snapshot();
        log.append("done");

        System.out.println("captured=" + captured);
        System.out.println("current=" + log.snapshot());
    }
}
```

```bash
javac SafeLogDemo.java
java SafeLogDemo
```

```text
captured=start
current=start|done
```

Why does `captured` not change? `snapshot()` creates/returns an immutable `String` value representing the content at the time of the call. `log.append("done")` mutates the internal `StringBuilder`, not the `captured` String. Note that this is a **single-threaded** demo; `StringBuilder` is not inherently thread-safe if multiple threads call `append` and `snapshot` concurrently.

Distinguishing the semantics of the two APIs:

- `StringBuilder getMutableContent()` (if it existed) exposes a mutable reference.
- `String snapshot()` only returns a value containing the content at the time of the call.

API design should state clearly whether it returns a **live mutable view** or a **snapshot**.

## 19. `final` and Immutable Objects: Two Independent Properties

There are two important symmetrical examples:

**Final reference to a mutable object:**

```java
final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Object changes to "AB".
```

**Non-final reference to an immutable object:**

```java
String text = "A";
text = text + "B";    // The text variable changes to a new String value.
```

In the first example, **the variable does not change**, while the object changes. In the second example, **the variable can change**, while the old `String` object is not mutated.

| Reference variable | Referenced object | Behavior example |
| --- | --- | --- |
| final | mutable | `final StringBuilder b`; `b.append(...)` is valid |
| non-final | mutable | Can reassign the variable **and** mutate the object |
| final | immutable | Cannot reassign the variable; the object has no mutable API |
| non-final | immutable | Can assign the variable to a different immutable object; the old object is not mutated |

**Immutability is a property of a type/implementation/object graph**, whereas `final` on a reference is **an assignment restriction on a specific variable**. These are two independent axes.

## 20. String and StringBuilder: A Memorable Contrasting Example

File **`FinalStringVsBuilderDemo.java`**:

```java
public class FinalStringVsBuilderDemo {
    public static void main(String[] args) {
        final String text = "Hi";
        final StringBuilder builder = new StringBuilder("Hi");

        String next = text.concat("!");
        builder.append("!");

        System.out.println("text=" + text);
        System.out.println("next=" + next);
        System.out.println("builder=" + builder);

        // text = next; // Invalid: final String variable.
        // builder = new StringBuilder(); // Invalid.
    }
}
```

```bash
javac FinalStringVsBuilderDemo.java
java FinalStringVsBuilderDemo
```

```text
text=Hi
next=Hi!
builder=Hi!
```

Explanation:

- `String.concat` returns a String result; it does not change the content of the String object `text`.
- Because `text` is final, `text` cannot be reassigned to `next`. The value of `text` remains `Hi`.
- `StringBuilder.append` mutates the builder object referenced by `builder`; the final `builder` variable still holds the old reference.

Do not think that only `final String` makes a String immutable. **Even a non-final `String` is an immutable object**; the difference lies in whether **the variable can be reassigned**.

## 21. An Object with `final` Fields That Contains a Mutable Child Object

An object can have multiple `final` fields and still not be considered immutable if one field points to a mutable object or if there is a method that modifies a child object.

Example:

```java
class Profile {
    private final String id;
    private final StringBuilder notes;

    Profile(String id) {
        this.id = id;
        this.notes = new StringBuilder();
    }

    void addNote(String text) {
        notes.append(text);
    }

    String notes() {
        return notes.toString();
    }
}
```

Both fields are final, yet `Profile.addNote` mutates the `StringBuilder` object, so **Profile's observable state can change**.

### Shallow Immutability and Deep Immutability

- **Shallow**: the field references do not change, but objects reachable from them can change.
- **Deep**: all state considered an immutable part of the object **cannot be modified through any valid access path**, including mutable elements/child objects according to the contract.

In practice, deep immutability typically requires:

1. Providing no mutating methods on the object designed to be immutable.
2. Final fields for the appropriate state components.
3. Immutable primitive/value components whenever possible.
4. Defensive copies of mutable arguments passed into the constructor.
5. Not returning internal mutable references through getters.
6. Appropriate copying or wrapping for collections/arrays.
7. Not letting `this` escape during initialization.

**Merely adding `final` to every field does not automatically satisfy that checklist.**

## 22. Records in Java 17+ Can Also Hold Mutable References

Java records have component fields with their own final rules, yet a record containing a mutable object such as `StringBuilder` can still expose mutation.

File **`RecordMutabilityDemo.java`**:

```java
record NoteRecord(StringBuilder text) {
}

public class RecordMutabilityDemo {
    public static void main(String[] args) {
        StringBuilder original = new StringBuilder("A");

        final NoteRecord note = new NoteRecord(original);

        original.append("B");
        System.out.println(note.text());

        note.text().append("C");
        System.out.println(original);

        // note = new NoteRecord(new StringBuilder("X"));
        // Invalid: the note variable is final.
    }
}
```

```bash
javac RecordMutabilityDemo.java
java RecordMutabilityDemo
```

```text
AB
ABC
```

Observations:

- The `NoteRecord` record holds a reference field for the `text` component via the record mechanism; that field cannot be reassigned after initialization.
- `original` and `note.text()` hold references to the same `StringBuilder`, so both paths can mutate that object.
- The `note` variable is also final, yet two layers of final still **do not make StringBuilder immutable**.

**How to improve:** if the contract requires the record to be immutable, use an immutable component type such as `String`, or perform a defensive copy and have the accessor return a copy for mutable components. When designing a record containing an array or list, do not assume the record has deep-frozen them.

## 23. `final` on a Reference Does Not Automatically Guarantee Thread Safety

A `final` field can help enforce the initialization/safe-publication rules of the Java Memory Model for the field itself and related effects when the object is properly constructed. However, **you cannot infer from this that mutations occurring after the constructor become thread-safe**.

Example:

```java
class SharedCounter {
    private final int[] counts = {0};

    void increment() {
        counts[0]++;
    }

    int count() {
        return counts[0];
    }
}
```

`counts` is a final reference field and cannot be reassigned after initialization. However, the `counts[0]` slot is still a mutable `int` value inside the array object. Two threads calling `increment()` concurrently can cause a **lost update** because `counts[0]++` is a read-modify-write operation, which is not made atomic merely by a final field.

**Do not confuse these guarantees:**

- **Final field semantics**: has specific rules for initialization and visibility of final fields when the object is not improperly published inside the constructor.
- **Thread-safe mutation**: requires proper synchronization or atomic operations for state modified after the object is published.
- **Deep immutability**: a type that does not allow observable state to change per its contract, which differs from both of the above.

For shared mutable state, consider `synchronized`, `Lock`, or `AtomicInteger`; readers and writers must coordinate using the same mechanism. Do not treat `final` as a “lock” protecting the increment operation.

### Example Using `AtomicInteger` with a Final Reference

File **`FinalAtomicDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class FinalAtomicDemo {
    private final AtomicInteger counter = new AtomicInteger();

    void increment() {
        counter.incrementAndGet();
    }

    int value() {
        return counter.get();
    }

    public static void main(String[] args) {
        final FinalAtomicDemo demo = new FinalAtomicDemo();

        demo.increment();
        demo.increment();

        System.out.println(demo.value());
    }
}
```

```bash
javac FinalAtomicDemo.java
java FinalAtomicDemo
```

```text
2
```

Here, the `counter` field is a final reference **and** the `AtomicInteger` object is **intentionally mutable**; the `incrementAndGet` method provides an atomic update according to the atomic type's contract. `final` prevents replacing the entire AtomicInteger object with a new reference; it is not required for that atomic method to behave atomically.

**Conversely:** a `final AtomicInteger` does not guarantee that complex compound operations—such as “reading two atomic variables and then checking a condition”—are atomic as a single transaction. Concurrency design must be based on the contract of each behavioral combination.

## 24. A `final` Variable Does Not Prevent Another Method from Mutating the Object Through an Alias

Even when a method only takes a non-final parameter, if it is passed an object that the caller holds in a final variable, the method can still modify the object.

```java
static void update(StringBuilder text) {
    text.append("!");
}
```

Caller:

```java
final StringBuilder buffer = new StringBuilder("Hi");

update(buffer);

System.out.println(buffer); // Hi!
```

These are **code snippets** placed inside a valid class/method.

Diagram:

```text
Caller:
buffer (final) ───────┐
                      ├────> StringBuilder A ("Hi")
Method:
text (parameter) ─────┘

After text.append("!"):
buffer (final) ───────┐
                      ├────> StringBuilder A ("Hi!")
text ─────────────────┘
```

**Difference from having `final StringBuilder text` as the parameter:** adding `final` to the parameter only forbids the method from writing `text = other`; it does not forbid `text.append(...)`. The caller also does not “pass the reference by reference” in the sense of allowing the callee to reassign the caller's variable; Java still uses **pass-by-value of the reference value**.

## 25. Comparing State-Mutating Methods and Methods Returning a New Object

When designing an API, you can choose:

**Mutating API:**

```java
class MutablePoint {
    int x;
    int y;

    void move(int dx, int dy) {
        x += dx;
        y += dy;
    }
}
```

`final MutablePoint p = new MutablePoint(); p.move(1,2);` is valid: the object state changes.

**Immutable value API:**

```java
record Point(int x, int y) {
    Point moved(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
```

The caller can write:

```java
final Point original = new Point(0, 0);
Point moved = original.moved(1, 2);
```

`original` is final and `Point` is immutable with respect to its two primitive components, so original keeps its old value, while `moved` is a record instance holding the new state.

**Note:** the `x + dx` operation on `int` can overflow. If a contract that prevents overflow is needed, use `Math.addExact`. This is an issue of **arithmetic correctness**, independent of whether the reference is final or not.

### Runnable Example Comparing Both APIs

File **`MutationVsImmutableDemo.java`**:

```java
class MutablePoint {
    private int x;
    private int y;

    MutablePoint(int x, int y) {
        this.x = x;
        this.y = y;
    }

    void move(int dx, int dy) {
        x += dx;
        y += dy;
    }

    String location() {
        return x + "," + y;
    }
}

record Point(int x, int y) {
    Point moved(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}

public class MutationVsImmutableDemo {
    public static void main(String[] args) {
        final MutablePoint mutable = new MutablePoint(1, 2);
        mutable.move(3, 4);

        final Point immutable = new Point(1, 2);
        Point moved = immutable.moved(3, 4);

        System.out.println("mutable=" + mutable.location());
        System.out.println("original=" + immutable);
        System.out.println("moved=" + moved);
    }
}
```

```bash
javac MutationVsImmutableDemo.java
java MutationVsImmutableDemo
```

```text
mutable=4,6
original=Point[x=1, y=2]
moved=Point[x=4, y=6]
```

Because `Point` is a record with primitive components, the record instances in the example have no mutable referenced components. `MutablePoint` changes the object state even though the caller uses a final reference; `Point.moved` returns a new object.

## 26. `final` Does Not Guarantee Side-Effect-Free Behavior or Rollback on Error

Suppose:

```java
static void update(final java.util.List<String> names) {
    names.add("A");

    if (names.size() > 3) {
        throw new IllegalStateException("too many names");
    }
}
```

This is an illustrative method snippet. If `names` is a mutable list that already has three elements, the method:

1. **Adds the fourth element**.
2. Then checks and throws an exception.
3. The caller receives the exception, **but the list has already been modified**.

`final` on the parameter does not fix this **partial mutation** bug at all.

A safer approach when the capacity and input are known:

```java
static void addIfRoom(final java.util.List<String> names, String value) {
    if (names.size() >= 3) {
        throw new IllegalStateException("too many names");
    }
    names.add(value);
}
```

With multiple steps that could fail, you can consider **copy → validate → commit** or immutable data. If multiple threads mutate the list concurrently, a dedicated synchronization mechanism is needed for check-and-update to avoid TOCTOU.

**Do not call a method “read-only” just because its parameter is declared final.** To have a non-mutating contract, you must examine the implementation, the object types, and alias sharing.

## 27. `final`, Access Control, and Encapsulation: Applying Each in Its Proper Role

A data design can combine:

- **`private` field**: restricts where in the source code the field can be directly accessed.
- **`final` field**: ensures the field cannot be reassigned after valid initialization.
- **Immutable implementation/value type**: prevents the object itself from changing state.
- **Defensive copy**: prevents callers from holding aliases to mutable internal data.
- **Controlled mutator methods**: provide state changes with invariant checks.
- **Synchronization/atomic APIs**: control concurrent access when needed.

No single modifier replaces all of them.

Example:

```java
class BankAccount {
    private final String accountId;
    private int balance;

    BankAccount(String accountId, int balance) {
        if (accountId == null || accountId.isBlank() || balance < 0) {
            throw new IllegalArgumentException("invalid account");
        }
        this.accountId = accountId;
        this.balance = balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("invalid amount");
        }
        balance = Math.addExact(balance, amount);
    }

    int balance() {
        return balance;
    }

    String accountId() {
        return accountId;
    }
}
```

Here, `accountId` is a final String reference to an immutable String; in the application contract, the ID does not change after construction. `balance` is non-final because the balance is designed to change via `deposit`. This can be a **clearer design** than trying to mark everything final while hiding the balance inside a mutable array or child object just so it can be mutated.

**Choose final according to the meaning of the data**; do not try to “sprinkle final onto every declaration” if doing so makes the state model more convoluted.

## 28. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| “`final Object obj` makes the object immutable” | Only forbids reassigning the `obj` variable |
| “`obj.method()` is forbidden if the method modifies state” | Still allowed if the method is accessible and the object is mutable |
| “Calling a setter means reassigning the final variable” | The setter modifies object state; the reference variable does not change |
| “`final` forbids every assignment with `=` involving the object” | It forbids reassigning the final variable/field itself; it does not automatically forbid writing to other fields |
| “`final` prevents other aliases from modifying the object” | Multiple aliases can point to the same mutable object and mutate it |
| “Reassigning the same old reference is valid” | Reassigning a final variable is still invalid even if the value is `==` to the original |
| “A final variable cannot be null” | It can be initialized to `null` and then not reassigned |
| “`final T[]` makes the array slots final” | The slots can still be changed |
| “`final List` is equivalent to `List.of`” | `final` on a variable does not change the List implementation |
| “`public static final List` is always immutable” | A mutable List object can still be modified through the public reference |
| “`Collections.unmodifiableList` is a deep immutable snapshot” | It is an unmodifiable view; a source alias can still modify the backing data |
| “`List.copyOf` deep-copies every element” | No; references to mutable elements can still be shared |
| “A `private final List` cannot be modified by callers” | If the constructor/getter exposes an alias to a mutable list, the caller can mutate the list |
| “Records have final fields, so all component objects are immutable” | A record can contain mutable objects |
| “`final String` and `final StringBuilder` are equally immutable” | String is immutable; StringBuilder is mutable |
| “A `final` parameter prevents the method from modifying the argument” | It only prevents reassigning the parameter; it does not forbid mutating the shared object |
| “A `final` field automatically guarantees thread safety” | Mutations after construction still require an appropriate concurrent access mechanism |
| “A `final AtomicInteger` cannot be incremented” | The reference cannot be reassigned; the AtomicInteger object is designed to be updated |
| “`final` makes exceptions automatically roll back mutations” | Exceptions do not automatically undo field/list updates |
| “`final class` and `final reference` are the same rule” | A final class forbids inheritance; a final variable forbids reassignment |
| “Final fields alone are enough to build an immutable class” | You must also examine the mutable object graph, constructors, getters, and copy policy |

## 29. Reference Tracing Exercise: Predict the Output

Create **`FinalReferenceTraceDemo.java`**:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class FinalReferenceTraceDemo {
    static void increase(final Box target) {
        target.value += 3;

        // target = new Box(99); // Invalid: final parameter.
    }

    public static void main(String[] args) {
        final Box first = new Box(2);
        Box second = first;

        increase(first);
        second.value *= 2;

        System.out.println("first=" + first.value);
        System.out.println("second=" + second.value);
        System.out.println("same=" + (first == second));

        second = new Box(100);

        System.out.println("first=" + first.value);
        System.out.println("second=" + second.value);
        System.out.println("same=" + (first == second));
    }
}
```

```bash
javac FinalReferenceTraceDemo.java
java FinalReferenceTraceDemo
```

```text
first=10
second=10
same=true
first=10
second=100
same=false
```

### Step-by-Step Execution

```text
A = Box object {value=2}

first (final) ──┐
                ├──────> A {value=2}
second ─────────┘

increase(first):
target (final parameter) ────> A
A.value += 3                  => A.value=5

second.value *= 2:
A.value=10

second = new Box(100):
first (final) ────────────────> A {value=10}
second ───────────────────────> B {value=100}
```

Observations:

- `increase` has a final parameter yet still mutates Box A from 2 to 5.
- `second.value *= 2` mutates A to 10 because it is an alias.
- `second = new Box(100)` cannot cause `first` to change its reference, because the assignment only affects the `second` variable.
- `final` on `first` forbids the caller from writing `first = B`; it does not forbid B and A from coexisting or object A from changing state.

## 30. Self-Check Questions with Answers

**Question 1.** Is `final StringBuilder b = new StringBuilder("A"); b.append("B");` valid?

*Answer:* Yes. The `b` variable is not reassigned; the StringBuilder object is mutated.

**Question 2.** Is `final StringBuilder b = new StringBuilder("A"); b = b;` valid?

*Answer:* No. The statement `b = b` is still a reassignment of an already-initialized final variable.

**Question 3.** Is `final List<String> values = new ArrayList<>(); values.add("A");` valid?

*Answer:* Yes. `ArrayList` is a mutable list; `final` only restricts the reference variable.

**Question 4.** Is `final int[] nums = {1,2}; nums[0] = 9;` valid?

*Answer:* Yes. An array is a mutable object, so slot 0 changes; the `nums` variable still points to the old array.

**Question 5.** Does `final String text = "A"; text.concat("B");` change the content of `text`?

*Answer:* No. String is immutable; `concat` returns a new String result (aside from optimizations that do not alter semantics). If the result is discarded, `text` remains `A`.

**Question 6.** If a `final Person p` and a `Person q` both point to the same mutable Person object, can `q.rename(...)` affect `p.name()`?

*Answer:* Yes, if `rename` mutates the same Person object and `name()` reads that state.

**Question 7.** Is `final Person p = null; p = new Person();` valid?

*Answer:* No. The variable has already been initialized to `null`; it cannot be reassigned.

**Question 8.** Is `final Person p; p = new Person();` valid for a local variable?

*Answer:* Yes, if `p` is assigned exactly once according to definite-assignment rules and is not read before being assigned.

**Question 9.** Does `private final List<Person> people` guarantee that the object graph is immutable?

*Answer:* No. The field cannot be reassigned, but the list or Person elements may be mutable, especially if aliases are shared.

**Question 10.** Can a method accepting `final List<String> items` call `items.clear()`?

*Answer:* Yes with respect to syntax and `final` semantics; whether it succeeds at runtime depends on the List implementation (an unmodifiable list can throw `UnsupportedOperationException`).

**Question 11.** Is `Collections.unmodifiableList(source)` guaranteed to be a snapshot detached from `source`?

*Answer:* No. It is a view; if the source changes via another alias, the view can reflect those changes.

**Question 12.** Does `List.copyOf(source)` deep-copy every mutable element?

*Answer:* No. It does not automatically deep-copy element objects.

**Question 13.** Is a record containing a `StringBuilder` automatically deep immutable?

*Answer:* No. The component reference follows final rules, but the StringBuilder can be mutated via an alias.

**Question 14.** Is `final AtomicInteger count = new AtomicInteger(); count.incrementAndGet();` valid?

*Answer:* Yes. A final reference and a mutable atomic object are two different things.

**Question 15.** Does `final` on a reference field automatically replace `synchronized`/atomic operations?

*Answer:* No. Mutations after object initialization require concurrency control according to the contract.

**Question 16.** To make a class truly immutable when it has a `List<String>` field, what else is needed besides `final`?

*Answer:* Design the list to be unmodifiable with an appropriate snapshot in the constructor/getter; with immutable String elements, that suffices for this part. If the elements are mutable, the elements themselves must also be protected.

**Question 17.** Does `final class Person` prevent Person's methods from modifying mutable fields?

*Answer:* No. A final class only prevents subclassing; it does not make the object immutable.

**Question 18.** Does `final` prevent partial state changes if a method mutates first and then throws an exception?

*Answer:* No. Validation/compute-before-commit or exception-safety design is required; this cannot be inferred from a final reference.

## 31. Checklist Before Using `final` with References

- [ ] Do I want to **keep the variable's reference unchanged** or **keep the object's state unchanged**?
- [ ] What mutating methods/fields does the object behind the reference have?
- [ ] Can the final variable hold `null`? Is non-null validation needed?
- [ ] Can any other aliases mutate the same object?
- [ ] If it is an array, can its slots be changed and are the element objects mutable?
- [ ] If it is a list/map/set, is the collection implementation mutable or unmodifiable?
- [ ] With `Collections.unmodifiableList`, where does a mutable alias to the source still exist?
- [ ] With `List.copyOf`, are element references shared?
- [ ] Does a private final field have a mutable reference exposed by a getter or constructor?
- [ ] If a snapshot is needed, have the container structure and mutable elements been copied appropriately?
- [ ] If using a record, do its components hold mutable references?
- [ ] When returning a String from a StringBuilder, does the caller receive a snapshot or a live mutable reference?
- [ ] When a method takes a `final` parameter, am I confusing it with a promise not to mutate?
- [ ] If multiple threads are involved, does the mutation have proper synchronization/atomicity?
- [ ] Are final class and final method being confused with final variable/field?
- [ ] Are there tests for mutation through an alias to verify the contract?
- [ ] Are invariants protected and errors handled before mutating to avoid partial state?
- [ ] If a truly immutable object is desired, can mutable data be replaced with immutable value types?

---

**Final takeaway:** In Java, **`final` on a reference-type variable/field/parameter fixes the assignment of the reference value**, **without freezing the object behind it**. Therefore, a `final StringBuilder` can still call `append`, a `final int[]` can still have its slots changed, a `final List` can still be mutated if the list supports it, and **other aliases can also modify the same object**. Achieving content immutability must rely on **immutable types, unmodifiable collections, defensive copies, encapsulation, and API contracts**; achieving multi-threaded safety also requires appropriate synchronization/atomic design. Clearly distinguishing **“the reference cannot be reassigned”** from **“the object does not change”** is the foundation for using `final` properly in Java.
