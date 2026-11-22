# Shallow Copy and Deep Copy in Java

## 1. Why Is the Distinction Needed?

In Java, a variable of a reference type stores a **reference to an object**, not the entire object itself. When you assign one reference variable to another, Java copies the **reference value**: both variables point to the same object. Variable assignment does not create a new object.

```java
Person a = new Person(...);
Person b = a; // b and a reference the same Person
```

The declaration above is an illustrative snippet; `Person` must be defined separately. To get a copy, the program must actively create another object, for example via a constructor, a copy method, `clone()`, or an appropriate mapping mechanism.

An important issue arises when an object contains **fields referencing other objects**. A `Person` object has an `address` field referencing an `Address`; `Address` may in turn have another list of data. The entirety of those objects and links is called an *object graph*.

- **Shallow copy:** creates a new root object and copies the field values; primitive fields are copied by value, while reference fields still reference the old child objects.
- **Deep copy:** creates independent copies for those child objects that **need to be independent** within the defined copying scope; links in the copy point to the corresponding copies. Immutable values such as `String` can usually be shared safely.
- **Independence** must be understood in terms of *mutable state*: modifying the state of the copy must not accidentally modify the state of the original, and vice versa, within the committed scope.

Illustration with a mutable reference field:

```text
Original:         Person P1 ──address──> Address A1
Shallow copy:     Person P2 ──address──> Address A1  (shared)
Deep copy:        Person P3 ──address──> Address A2  (independent of A1)
```

`P1`, `P2`, and `P3` are three different `Person` objects. The difference lies in the `Address` object they hold.

## 2. Java 17 Example: Observing the Difference

Create the file `CopyDemo.java`:

```java
public class CopyDemo {
    static class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static class Person {
        String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }

        Person deepCopy() {
            return new Person(name, new Address(address.city));
        }
    }

    public static void main(String[] args) {
        Person original = new Person("An", new Address("Hà Nội"));
        Person shallow = original.shallowCopy();
        Person deep = original.deepCopy();

        System.out.println("original == shallow: " + (original == shallow));
        System.out.println("same address in shallow: "
                + (original.address == shallow.address));
        System.out.println("same address in deep: "
                + (original.address == deep.address));

        shallow.address.city = "Đà Nẵng";
        System.out.println("original after shallow edit: " + original.address.city);

        deep.address.city = "Huế";
        System.out.println("original after deep edit: " + original.address.city);
        System.out.println("deep after edit: " + deep.address.city);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 CopyDemo.java
java CopyDemo
```

Output:

```text
original == shallow: false
same address in shallow: true
same address in deep: false
original after shallow edit: Đà Nẵng
original after deep edit: Đà Nẵng
deep after edit: Huế
```

Step-by-step explanation:

1. `shallowCopy()` creates a new `Person` but passes the old `address` directly into the constructor; modifying `shallow.address.city` also modifies the city seen from `original`.
2. `deepCopy()` creates both a new `Person` and a new `Address`; modifying `deep.address.city` does not affect `original.address.city`.
3. `name` is an immutable `String`, so sharing the `name` reference does not cause state-mutation leaks.
4. The example assumes `address` is non-`null` and `Address` has only a single `String` field. When the data structure is more complex, the copy method must handle additional fields and corresponding relationships.

**Note:** `original == shallow` returning `false` only confirms that the two `Person` objects are different. It does **not** prove that all child objects have been copied.

## 3. Comparison by Key Criteria

| Criterion | Reference assignment | Shallow copy | Deep copy |
| --- | --- | --- | --- |
| Root-level object | Shared | Newly created | Newly created |
| Primitive fields | Same root object | Copied by value | Copied by value |
| Mutable reference fields | Shared | Usually shares child objects | Copies child objects within the scope needing independence |
| Changing a field of the root object | Visible through all variables pointing to it | Does not change the corresponding field of the copy if reassigned on a separate root object | Does not change the corresponding field of the copy |
| Changing the *internal state* of a child object | Visible in both | May propagate to the other | Does not propagate to the other within the copy scope |
| Cost | Usually a tiny assignment operation | Usually lower than deep copy | Depends on the number of objects/relationships actually created |
| Suitable for | Intentionally sharing a single object | Wanting a new wrapper object while being able to share internals | Needing to isolate mutable state |

You cannot tell the type of copy merely from whether `new` is used. `new Person(old.name, old.address)` only shallow-copies `address`; a copy constructor can also be shallow or deep depending on how it is implemented.

## 4. Collections and Arrays: Creating a New Container Is Not Yet a Deep Copy

`new ArrayList<>(source)` creates a new list and copies the **element references**, without automatically creating copies of each object. The `HashMap` copy constructor is similar: a new map structure, while keys and values are usually still shared. `array.clone()` or `Arrays.copyOf(...)` copies the array; if the elements are references, the element objects are still shared.

Standalone runnable example in `CollectionCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionCopyDemo {
    static class Task {
        String title;

        Task(String title) {
            this.title = title;
        }
    }

    public static void main(String[] args) {
        List<Task> original = new ArrayList<>();
        original.add(new Task("Học Java"));

        List<Task> shallow = new ArrayList<>(original);
        List<Task> unmodifiable = List.copyOf(original);

        shallow.get(0).title = "Học Java 17";
        System.out.println(original.get(0).title);
        System.out.println(unmodifiable.get(0).title);

        shallow.add(new Task("Viết test"));
        System.out.println(original.size());
        System.out.println(shallow.size());
    }
}
```

Run:

```bash
javac -encoding UTF-8 CollectionCopyDemo.java
java CollectionCopyDemo
```

Output:

```text
Học Java 17
Học Java 17
1
2
```

`List.copyOf(original)` creates a list that **does not allow structural modification through the resulting list**, but it does not make each `Task` immutable and does not deep-copy `Task`. If the input list is already an unmodifiable list, Java may reuse that list object. `List.copyOf` also does not accept `null` elements.

Further distinctions:

- `Collections.unmodifiableList(list)` is usually a *view*: it disallows modification through the view, but structural changes on the original `list` can appear in the view.
- `List.copyOf(list)` yields an unmodifiable list with the elements present at call time; it does not protect the mutable state of the elements.
- Deep-copying a `List<Task>` requires creating an appropriate container **and** creating a new `Task` for each element that needs independence, while also considering reference fields inside `Task`.
- If all elements are immutable values (for example `String`), copying the container can suffice to isolate structural changes; additionally copying each `String` brings no benefit.

Example approach for handling a simple list, when `Task` only has a `title` field as above:

```java
List<Task> deepTasks = original.stream()
        .map(task -> new Task(task.title))
        .toList();
```

This is an **illustrative snippet in the context** of `CollectionCopyDemo`, not a standalone runnable file. `Stream.toList()` (Java 16+) returns an unmodifiable list; the new `Task` instances remain mutable. If you need to add/remove elements, wrap the result in `new ArrayList<>(...)`.


## 5. From Concept to Copy Contract

Shallow copy and deep copy are ways of describing the **degree of reference sharing**, not the name of a specific API. A copy constructor, factory, `clone()`, or mapping mechanism only achieves the level of independence that its implementation actually guarantees. A class may share immutable `String`s while having to copy arrays, collections, or mutable elements if the contract requires separating state.

For a graph with two edges pointing to the same node or containing cycles, recursively copying each branch can lose structure or loop infinitely. When relationships need to be preserved, each original node must be recorded by **identity** within the same copy session. For a `final` field pointing to mutable data, `super.clone()` still shallow-copies it and does not allow reassigning the field after cloning; a constructor/factory can initialize the final field with its own copy.

Subsequent lessons dive into immutable sharing, defensive copying, cyclic graphs, `final` constraints, copy constructors/factories, ownership, two-way testing, and serialization limits. In this lesson, you only need to grasp the principles and know how to choose the copying scope.

## 6. Choosing a Strategy in Practice

1. **Only need another reference name for the same object:** use assignment, understanding that state is shared.
2. **Need a new object/container while intentionally sharing elements:** use shallow copy and clearly document the sharing contract.
3. **Need to edit the copy without affecting the original:** build a deep copy over the appropriate mutable scope; prefer a clear copy constructor/factory.
4. **Want to avoid copy overhead and bugs:** consider immutable value objects, defensive copies at API boundaries, or dedicated snapshots.
5. **Graphs with cycles/aliases:** design a traversal algorithm with an identity table, and check link relationships and data depth.
6. **Objects holding resources or participating in concurrency:** determine lifecycle, ownership, and snapshot consistency before choosing how to copy.

When designing a copy API, specify: whether the copy has a new root instance; which mutable fields are detached; which values are intentionally shared; whether alias/cycle relationships are preserved; how `null`, inheritance, and errors are handled; and whether copying is consistent under concurrent updates.

## 7. Self-Check Knowledge

- If a `List<Employee>` is created with `new ArrayList<>(oldList)`, does calling `add()` on the new list affect `oldList`? If `newList.get(0).name` is modified, what happens when `Employee` is mutable?
- If `a.left == a.right`, what relationship must a proper deep copy satisfy between `copy.left` and `copy.right`? Why can merely cloning each field recursively be wrong?
- Why does sharing `String` usually not break independence, whereas sharing `ArrayList` can break it?
- A copy method creates a new root object but keeps the same `Socket` and `List<MutableItem>`. Explain which parts are only shallow-copied and how to describe a safe contract.

**Takeaway:** Shallow/deep does not depend on the method name or the presence of `new`. What decides it is **the reference graph and which mutable state is shared after copying**.
