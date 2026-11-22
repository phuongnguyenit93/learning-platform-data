# Distinguishing Structural Modification, Value Replacement, and Element Mutation

All three are loosely called “modifying a collection,” yet each operation below acts on a different layer of data:

```java
students.add(new Student("S3", "Chi"));
students.set(0, new Student("S4", "Dung"));
students.get(0).rename("Anh");
```

One operation adds an element to the list; one replaces the element at an existing position; the remaining one mutates the object currently referenced by the list.

Distinguishing them helps you understand iterators, shallow copies, views, unmodifiable collections, and bugs involving mutable keys. If you look only at the printed output or only at `size()`, it is easy to miss what actually changed.

This lesson uses Java 17 and takes `ArrayList` as the primary model. Extending these ideas to `Map`, `Set`, and other structures always requires checking their specific contracts. Short Java snippets illustrate concepts in context; the complete program, along with compilation commands and output, appears in the hands-on section.

## 1. Why Do We Need Three Separate Concepts?

Suppose a list manages two students. The following requirements are different:

| Requirement | What actually needs to be done |
| --- | --- |
| Admit an additional student | Add an element to the container structure |
| Replace the student at index 0 with someone else | Change the element bound to an existing position |
| Fix the name of the student currently at index 0 | Change the state of the already-referenced object |
| Change the display order | Rearrange the position-to-element mapping |
| Allow reading the list while preventing external callers from modifying it | Determine which data layer needs protection |

If a designer says “a read-only list,” you need to ask further:

- Must adding or removing elements be disallowed?
- Must replacing elements be disallowed?
- Must mutating an element's properties be disallowed?
- Should changes made by another party be visible through it?

These questions cannot be answered by a context-free “mutable” or “immutable” label.

## 2. The Three-Layer Model: Structure, Reference, and Object

For a collection holding objects, picture three layers:

```text
Variable students
    |
    v
List object
    index 0 ----> Student object S1, name "An"
    index 1 ----> Student object S2, name "Binh"
```

### 2.1. The Container Structure Layer

The list manages positions, size, and element references. `ArrayList` also maintains an internal backing array with its own capacity.

For a map, the structure manages key–value mappings. For a set, it manages elements according to equality, hashing, or comparison rules.

### 2.2. The Element-to-Position or Element-to-Key Binding Layer

Which object reference does a given position in the list currently hold? Which value is a given key in the map currently bound to?

Replacing the reference at index 0 may leave the element count unchanged, yet the object accessed through that position is now different.

### 2.3. The Element State Layer

The `Student` object has a `name` field. Calling a rename method acts on this object without necessarily calling any mutating method on the list.

These layers are not completely isolated in business meaning: changing a field can alter `equals`, `hashCode`, ordering, or how the element is displayed. However, the path of impact and what the collection itself observes remain distinct.

## 3. What Is a Structural Modification?

### 3.1. Typical Cases: Adding and Removing Elements

Given an `ArrayList` that currently holds two elements:

```java
students.add(new Student("S3", "Chi"));
students.remove(0);
```

The first call adds an element position; the second removes a position and shifts subsequent elements' indices.

These are typical structural modifications. An iterator created beforehand may no longer traverse the structure it was tracking correctly.

Operations such as `addAll`, `removeAll`, `retainAll`, `removeIf`, or `clear` can also affect the structure if they actually add or remove elements. You must examine the concrete effect, not just the method name.

### 3.2. Do Not Define It by “Did size() Change?”

`size()` lets you observe the logical element count, but it is not the general definition of a structural modification.

For example, the sequence:

```java
students.add(new Student("S3", "Chi"));
students.remove(students.size() - 1);
```

brings the size back to what it was. That does not restore the validity of an iterator that existed before those two calls.

For `ArrayList`, the documentation also mentions explicitly resizing the backing array. Capacity and element count are two different quantities; do not infer iterator validity merely by comparing `size()` before and after. Details are described in [Java 17 ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### 3.3. A Concept Dependent on the Structure and Class Contract

For `HashMap`, adding a new mapping or removing a mapping is a structural modification; merely changing the value associated with an existing key is not considered a structural modification under that class's definition.

An access-ordered `LinkedHashMap` behaves differently still: an access operation can affect iteration order and is considered a structural modification. Therefore, you cannot state a universal rule that “calling `get` is always read-only, so it never affects an iterator.” See [LinkedHashMap: access-order mode and structural modification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

At the base class level, `AbstractList` also frames structural modifications as changes that can disrupt iteration. The key lesson is to **read the definition of the specific type in use**, rather than treating `ArrayList`'s definition as the definition for the entire framework.

## 4. Value Replacement: Keeping the Position, Changing the Element There

### 4.1. List.set Does Not Mean Mutating the Old Object

Illustrative snippet:

```java
Student previous = students.set(0, new Student("S9", "Lan"));
```

After this call:

- Index 0 still exists.
- The list size neither increases nor decreases.
- Index 0 now references the new object.
- The return value is the element previously at this position.
- The old object is not mutated into the new object.

You can picture it as:

```text
Before:
    students[0] ----> Student S1, name "An"

After set:
    students[0] ----> Student S9, name "Lan"
    previous    ----> Student S1, name "An"
```

For `ArrayList`, replacing an element's value with `set` is not a structural modification. That is a specific characteristic to distinguish from adding or removing elements.

### 4.2. Read Results Have Changed Even Without a Structural Modification

Calling `students.get(0)` after `set` returns a different object than before.

Therefore:

- “No structural modification” does not mean the observable data has not changed.
- “No iterator exception” does not mean you are iterating over a fixed snapshot.
- “No change in count” does not mean the change is unimportant to business logic.

A grading system might keep the same number of students yet place the wrong person at a position. Having the right count does not prove the contents are right.

### 4.3. With String or Integer

`String` and wrapper classes such as `Integer` represent immutable values. When you want to change a string or number in a list, you typically store a new value at that position:

```java
List<Integer> scores = new ArrayList<>(List.of(7, 8));
scores.set(0, scores.get(0) + 1);
```

The list becomes `[8, 8]`. The expression above does not mutate the `Integer` object holding `7` into `8`; it computes a new value and replaces the element at index 0.

This differs from calling a setter on a mutable object.

### 4.4. Not Every Collection Has a set Operation

`set(index, value)` belongs to `List`, not to the general `Collection` contract. Sets do not have indexed element positions like lists.

For a map, replacing a value by key carries an analogous binding meaning, but you must use the map contract. Do not mechanically transfer list method semantics to sets or maps by name.

## 5. Mutating the Element Object: Reference Stays the Same, State Changes

Consider:

```java
Student student = students.get(0);
student.rename("Anh");
```

The list still holds a reference to the same object. The `rename` method changes the name field inside that object.

Picture it:

```text
Before:
    students[0] ----> Student S1, name "An"

After rename:
    students[0] ----> same Student S1, name "Anh"
```

The list was not asked to increase its element count or replace the reference at index 0. If you print the list, the displayed string may change because the element's `toString()` reads the new state.

### 5.1. A Collection Does Not Automatically Observe Every Setter

A plain `ArrayList` does not automatically receive notifications that an object inside it was just renamed. There is no general rule causing every field change to update the collection's structural modification counter.

That explains why a setter can change the resulting contents while an iterator continues without failing.

### 5.2. One Element Can Be Shared in Multiple Places

If two lists both hold a reference to the same `Student`, renaming through the first list can be observed through the second list.

The same object can also appear at two positions in a single list. Mutating that object via the first position causes reads at the second position to see the new state as well, because there are not two independent objects to mutate.

### 5.3. Mutating an Element Can Matter Greatly Even Without a Structural Modification

Changing a `name` field only affects display if it does not participate in other rules. However, if the mutated field is used in equality, hashing, or ordering, the collection may no longer uphold its original invariants.

You must distinguish between:

- Whether the operation is detected by the structural modification counter.
- Whether the state after the operation still satisfies the collection's contract and business rules.

These two questions are independent.

## 6. Reassigning a Local Variable Does Not Replace the Element in the List

This is a common mistake:

```java
Student local = students.get(0);
local = new Student("S9", "Local");
```

The initial `get` call places a reference into the `local` variable. The subsequent assignment changes only the `local` variable, not index 0 of the list.

Compare the three statements:

| Statement | What gets changed |
| --- | --- |
| `local = new Student(...)` | The reference stored in the local variable |
| `students.set(0, new Student(...))` | The element bound to index 0 |
| `local.rename("Anh")` | The state of the object that `local` points to |

The same applies to the `for-each` loop variable:

```java
for (Student student : students) {
    student = new Student("S9", "Replacement");
}
```

The snippet above does not replace every element in the list. It only reassigns the loop variable on each iteration.

If you want to replace elements, use an appropriate operation such as `ListIterator.set`, indexed access on a type that supports it, or build a new result list. Do not use loop-variable reassignment as a substitute for mutating a collection.

## 7. Comparison Table for ArrayList

The table below assumes the operation is supported and the arguments are valid. The structural column is scoped to `ArrayList` and does not apply unconditionally to every class.

| Operation | Logical size | Element reference | Old object state | Meaning |
| --- | --- | --- | --- | --- |
| `list.add(newValue)` | Increases | Adds element | Not automatically mutated | Structural modification |
| `list.remove(i)` | Decreases | Removes element at position | Not automatically mutated or destroyed | Structural modification |
| `list.set(i, newValue)` | Unchanged | Replaced at existing position | Not automatically mutated | Element replacement, not a structural modification of `ArrayList` |
| `list.get(i).rename(...)` | Unchanged | Unchanged | Mutated by element method | Object state mutation |
| `local = newValue` | Unchanged | Does not modify list element | Not automatically mutated | Local variable reassignment |
| `list.get(i)` | Unchanged | Unchanged | Not automatically mutated | Reading an element in typical usage |

Removing a reference from a list does not mean the object is immediately reclaimed from memory. The object may still be referenced by another variable or another collection; memory reclamation depends on reachability across the entire object graph.

Replacing a position with the same old reference also differs from replacing it with a new object. Seeing a method call alone is not enough to conclude that business content has changed.

## 8. How Do Iterators Relate to These Three Kinds of Changes?

### 8.1. Why Structural Modifications Can Invalidate an Iterator

An iterator tracks traversal progress: the next position, the last returned element, and information needed to detect certain invalid modifications.

A removal outside the iterator can shift indices; an addition can change the set of elements the iterator is supposed to traverse. Many classes use a fail-fast mechanism to detect such situations.

`ConcurrentModificationException` can occur even in a single-threaded program. The exception's name does not prove two threads were involved.

### 8.2. set on ArrayList Does Not Create a Snapshot for the Iterator

With `ArrayList`, replacing a position using `set` is not a structural modification. An iterator reading that position afterward can see the new element at that index.

If the iterator already returned the old object before `set`, an external variable holding the old object does not automatically switch to pointing at the new object. Timing of reads and reference sharing still matter.

Do not generalize this behavior to every kind of iterator. For instance, a snapshot-style iterator on another class has its own contract.

### 8.3. Mutating an Element's Field Is Not Automatically Detected by Fail-Fast

A setter on `Student` is not an add or remove call on the list. The iterator typically continues returning the same object with its new state.

That is not a guarantee that the application is free to mutate any field in any structure. For hash sets, trees, or heaps, fields involved in logical placement must be handled with great care.

### 8.4. Structural Modification Through the Iterator Itself Can Be Supported

If you want to remove elements while iterating, you can write:

```java
Iterator<Student> iterator = students.iterator();
while (iterator.hasNext()) {
    Student student = iterator.next();
    if (shouldRemove(student)) {
        iterator.remove();
    }
}
```

This is an illustrative snippet requiring an application-defined `shouldRemove` predicate. It is not a complete program.

The operation still removes elements and still modifies the structure. The difference is that it is performed through the iterator managing traversal progress, along the contractually permitted path.

`Iterator.remove` is an optional operation. It requires a valid element from `next()` and adherence to call-order rules; not every iterator supports removal.

With `ListIterator`, `set` replaces the last traversed element, while `add` inserts an element at the cursor position. Valid states and supported operations must be checked in [Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html) and [ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

### 8.5. Fail-Fast Is a Bug-Detection Tool

Do not reason like this:

```text
no ConcurrentModificationException
    ⇒ no modification occurred
    ⇒ data is safe
    ⇒ thread-safe across multiple threads
```

This chain of reasoning is wrong at all three steps.

Detection is best-effort, not a data-protection lock. Correct code must organize valid operations from the start; do not rely on the presence or absence of an exception to decide whether an algorithm is right.

## 9. Same Size, Yet Iterators Can Still Be Affected

Beyond adding and then removing, there are operations that change ordering or traversal mechanics without changing element count.

### 9.1. Sorting and Bulk Replacement

`sort` alters the position-to-element mapping. `replaceAll` can replace multiple elements.

You must not take the specific rule “`ArrayList.set` is not a structural modification” and deduce that every size-preserving method leaves existing iterators valid.

In the OpenJDK 17 implementation, `ArrayList.sort` and `ArrayList.replaceAll` update the modification counter used for iterator checks. This is an implementation detail to distinguish from the rule for a single `set` call; see [ArrayList source code in OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

The clean practice is to finish sorting or replacing before creating a new iterator, rather than reusing an existing iterator.

### 9.2. Access-Ordered Maps

A `LinkedHashMap` in access-order mode can change iteration order when a mapping is accessed. The number of mappings remains unchanged.

The lesson is not “every `get` modifies structure,” but “the method name and element count are not enough to classify impact without knowing the configuration and implementation class.”

### 9.3. modCount Is Not a Business Version Number

In some classes, a counter such as `modCount` supports iterators. It is not:

- A total count of business data changes.
- A transaction ID.
- A trace of every element setter call.
- A cross-thread synchronization mechanism.
- A public API for applications to check immutability.

Reading [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html) helps explain the counter's purpose, but you should not design business logic around a protected field of an implementation class.

## 10. Mutability Has Multiple Layers

### 10.1. final Only Restricts Variable Reassignment

Illustrative snippet:

```java
final List<String> names = new ArrayList<>();
names.add("An");
names.set(0, "Binh");
```

Both calls are valid. `final` does not make the list object immutable; it prevents reassigning the `names` variable itself to another list.

Similarly, a `final` reference field in a class does not automatically make all objects it points to deeply immutable.

### 10.2. Fixed Size Does Not Mean Unmodifiable

A list from `Arrays.asList(array)` has a fixed size and is backed by the array:

- Elements can be replaced with `set`.
- Elements cannot be added or removed to change the size.
- Replacing an element through the list or the array is visible through the other.

This illustrates the difference between “size cannot be modified” and “elements cannot be replaced.”

### 10.3. List.of Disallows Modification Through the List API

A list created with `List.of(...)` does not allow adding, removing, or replacing elements with `set`.

Thus, `set` is a non-structural operation on `ArrayList` yet can still be forbidden on another list. **Impact classification and whether an operation is supported are two separate things to check.**

### 10.4. Unmodifiable Does Not Make Elements Immutable

If an unmodifiable list contains `Student` objects that have setters:

```java
readOnlyStudents.get(0).rename("Anh");
```

this call can still succeed. The wrapper blocks methods that modify structure or replace elements through the list, but it does not turn the object returned by `get` into a read-only type.

If callers are allowed to obtain a reference to a mutable object, they can invoke that object's methods according to the access its API exposes.

The [Collection: unmodifiable collections and views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) documentation clearly distinguishes unmodifiable collections from immutable data.

## 11. Views, Shallow Copies, and Data Snapshots

### 11.1. An Unmodifiable View Can Still See Source Changes

`Collections.unmodifiableList(source)` creates an unmodifiable view through a wrapper; it does not detach the data from `source`.

If the holder of `source` calls `source.add(...)`, the size read through the view can increase. If the source replaces elements or mutates element objects, the view can reflect those changes as well.

This is not a bug in the wrapper; it is the contract of a live view backed by underlying data.

### 11.2. A Shallow Copy Separates Lists While Sharing Elements

With:

```java
List<Student> copy = new ArrayList<>(source);
```

- `copy` is a different list object.
- Adding or removing in `source` does not add or remove in `copy`.
- `source.set(i, another)` does not change the reference stored at `copy.get(i)`.
- Mutating an object referenced by both sides is visible through both lists.

There is no contradiction: the structures are separate, while the element objects remain shared.

### 11.3. List.copyOf Is Not a Deep Copy

`List.copyOf(source)` provides an unmodifiable list containing the source's elements at the time of the call. Subsequent additions, removals, or element replacements on the source do not automatically update the result as they would with a view.

However, the elements themselves can still be shared objects. Calling a setter on an element can change the data observed from both sides.

Do not rely on an assumption that `copyOf` always allocates a new list with a distinct reference; rely on the result contract, `null` rules, and the fact that it does not perform a deep copy.

### 11.4. When Element State Also Needs Isolation

You must determine what data a business snapshot needs to preserve, then construct appropriate value objects or element copies.

If a student holds a list of addresses, copying the student object while continuing to share the address list still fails to isolate all state.

A `record` with reference fields also does not automatically deep-copy or make referenced objects immutable. Designing immutable elements requires considering their internal data as well.

## 12. Partial Views and Effects Back on the Source

With `subList`, you are looking at a range of the backing list.

- `subList.set(...)` can replace the corresponding element in the backing list when supported.
- Removing through a sublist can reduce the backing list's size.
- Mutating an element object is visible from both sides.
- If the backing list is structurally modified outside the paths permitted by the view's contract, you must no longer treat the sublist as a valid, independent range of data.

Do not interpret the absence of an exception as proof that the view is definitely still valid. The `List.subList` contract must be checked whenever the source may change; see [Java 17 List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

Similarly, a map's `keySet`, `values`, and `entrySet` are views of its data. Replacing a mapping's value differs from removing a key; a view reading values can see different data even though the key set remains the same.

## 13. With Set, Map, and Ordered Structures

### 13.1. HashSet: Mutating a Property Used in Hashing

Suppose an element uses a `code` field in `equals` and `hashCode`. If `code` is changed after the element has been added to a `HashSet`, the object remains at the internal bucket determined by its prior state; the set does not automatically detect the setter and relocate it.

As a result, lookups, removals, or uniqueness guarantees may stop working as expected. The `Set` contract does not guarantee behavior when an element is mutated in a way that affects equality while it is in the set; see [Java 17 Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

Do not treat a single test run that happens to produce a specific result as a general guarantee for elements that violate this condition.

Good design uses stable identity information in equality. When you genuinely need to change a relevant field, remove the element before changing it, then add it back under its new state and handle potential duplicates. Simply re-adding after mutating without removing the old state may fail to fix the problem.

### 13.2. Map: Replacing a Value vs. Mutating a Key

For `HashMap`:

```java
map.put(existingKey, anotherValue);
```

replacing the value for an existing key is not the same as adding a mapping with a new key. The key set can stay the same while the observed value changes.

However, if you mutate the state of the object serving as the key itself—especially fields participating in `equals` or `hashCode`—you face the same risk as with `HashSet` elements.

Keys should have stable values. Mutating business values should typically be expressed by replacing the value or operating on the value object under clear ownership rules. See [HashMap: structural modification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

### 13.3. TreeSet or TreeMap: Mutating a Field Used for Comparison

Trees are organized according to the comparison relation when elements or keys are added. If an object changes a field used by the comparator, the tree does not automatically re-sort when the setter is called.

Do not conclude it is safe just because there is no size change or iterator exception. Keep comparison criteria stable for as long as the object resides in the structure.

This is a clear example of the difference between not making a structural modification through the API and breaking the assumptions the structure relies on.

## 14. Complete Java Program

The program below places all three kinds of changes side by side and observes two sharing patterns: a view backed by the same underlying data, and a shallow copy that uses a different list while sharing elements.

Save to `CollectionMutationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class CollectionMutationDemo {
    static final class Student {
        private final String id;
        private String name;

        Student(String id, String name) {
            this.id = id;
            this.name = name;
        }

        void rename(String newName) {
            name = newName;
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    public static void main(String[] args) {
        List<Student> students = new ArrayList<>(List.of(
                new Student("S1", "An"),
                new Student("S2", "Binh")));

        List<Student> shallowCopy = new ArrayList<>(students);
        List<Student> readOnly = Collections.unmodifiableList(students);

        Iterator<Student> beforeSet = students.iterator();
        Student replaced = students.set(1, new Student("S3", "Chi"));

        System.out.println("size after set: " + students.size());
        System.out.println("replaced object: " + replaced);
        System.out.println("iterator after set: "
                + beforeSet.next() + ", " + beforeSet.next());

        students.get(0).rename("Anh");
        System.out.println("students after rename: " + students);
        System.out.println("shallow copy: " + shallowCopy);

        Student local = students.get(0);
        local = new Student("S9", "Local");
        System.out.println("local variable: " + local);
        System.out.println("list first element: " + students.get(0));

        readOnly.get(0).rename("Annie");
        System.out.println("rename through readOnly: " + students.get(0));

        try {
            readOnly.set(0, new Student("S8", "Blocked"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("readOnly set: blocked");
        }

        students.add(new Student("S4", "Dung"));
        System.out.println("source size after add: " + students.size());
        System.out.println("readOnly size after add: " + readOnly.size());
        System.out.println("shallow copy size: " + shallowCopy.size());

        List<String> codes = new ArrayList<>(List.of("A", "B"));
        Iterator<String> stale = codes.iterator();
        codes.add("C");
        try {
            stale.next();
        } catch (ConcurrentModificationException ex) {
            System.out.println("stale iterator: ConcurrentModificationException");
        }

        Iterator<String> remover = codes.iterator();
        while (remover.hasNext()) {
            if (remover.next().equals("B")) {
                remover.remove();
            }
        }
        System.out.println("after iterator remove: " + codes);
    }
}
```

Compile and run:

```shell
javac --release 17 CollectionMutationDemo.java
java CollectionMutationDemo
```

Output:

```text
size after set: 2
replaced object: S2:Binh
iterator after set: S1:An, S3:Chi
students after rename: [S1:Anh, S3:Chi]
shallow copy: [S1:Anh, S2:Binh]
local variable: S9:Local
list first element: S1:Anh
rename through readOnly: S1:Annie
readOnly set: blocked
source size after add: 3
readOnly size after add: 3
shallow copy size: 2
stale iterator: ConcurrentModificationException
after iterator remove: [A, C]
```

### 14.1. Tracking Element Replacement with set

`students.set(1, ...)` replaces the student at index 1 from `S2` to `S3`. The list still has two elements.

The `replaced` variable still holds `S2:Binh`. In this `ArrayList` example, the iterator created before `set` observes the new element at the position it has not yet visited.

### 14.2. Tracking Object State Mutation

Renaming the first element to `Anh` is visible from both `students` and `shallowCopy`, because both lists hold a reference to student `S1`.

Meanwhile, the second element in `shallowCopy` remains `S2:Binh`. Calling `set` on the source replaced the reference at one position in the source, without changing the reference in the copy.

### 14.3. Tracking Local Variable Reassignment

Reassigning `local` to `S9:Local` does not change `students.get(0)`. The two expressions no longer point to the same object after the assignment.

### 14.4. Tracking the Limits of an Unmodifiable View

`readOnly.get(0).rename(...)` still mutates the student. However, `readOnly.set(...)` is blocked by the wrapper.

When a student is added through `students`, `readOnly`'s size increases accordingly, while `shallowCopy`'s size remains 2.

### 14.5. Tracking Structural Modification and Iterators

The `codes` section deliberately creates an iterator, adds an element through the list, and then calls `next()`. With `ArrayList` in this single-threaded experiment, the call detects the modification and throws `ConcurrentModificationException`.

The example uses the exception to observe the mechanism, not as a synchronization guarantee or a way to control a correct algorithm.

At the end of the program, a new iterator is created, `B` is removed through that iterator itself, and `[A, C]` is produced. The removal still modifies the structure, but it follows the path supported by the iterator.

The `Student` class in the program serves only for reference and state experiments; it is not placed in structures requiring equality or hashing by business code.

## 15. From Conceptual Distinctions to API Design

### 15.1. Specify What Is Permitted to Change

An API returning `List<Student>` should make clear:

- Can the caller add or remove elements?
- Can elements be replaced?
- Can methods that mutate student state be called?
- Is the result a live view backed by the source or data at a point in time?
- Is the source or are the elements shared with other tasks?

If you need a snapshot that the caller cannot alter, wrapping the list with `unmodifiableList` alone may not be enough. You must design both the elements and data ownership.

### 15.2. Choose Data Types Based on Update Boundaries

You can choose:

- Mutable objects internally where ownership is controlled.
- Immutable value objects as keys or elements needing stable equality.
- Data snapshots for readers.
- Explicit update methods instead of letting external callers hold references and call setters directly.

The choice depends on your needs; there is no requirement that every object be immutable.

### 15.3. Do Not Treat Non-Structural Changes as Permission for Multi-Threaded Access

Two threads concurrently replacing elements with `set` may not trigger a structural exception yet still suffer from races or memory visibility issues.

Two threads concurrently mutating fields of an element are likewise not protected merely because the outer collection supports concurrency. Thread safety of the container structure and thread safety of the contained objects are two separate scopes.

You need appropriate synchronization, thread confinement, data transfer, or immutability. Do not infer multi-threaded safety from a single-threaded program running successfully.

## 16. How to Analyze a Change in Real Code

When you see a line that looks like “modifying a collection,” ask in order:

1. Does this line call a method on the collection, on an element, or merely reassign a variable?
2. What is the concrete collection type and its configuration?
3. Does it add or remove elements or mappings, or alter the traversal mechanism?
4. Does it only replace an element at a position or the value for an existing key?
5. Or does it only mutate internal state of an already-referenced object?
6. Does anyone else hold a reference to the same collection or element?
7. Are there any views, iterators, or shallow copies currently in existence?
8. Does the mutated property participate in hashing, equality, or ordering?
9. Is the operation supported on the current collection?
10. Are there multi-threaded safety or business consistency requirements?

This reading habit avoids lumping every change into one bucket and guessing behavior from `size()` or an exception.

## 17. Self-Check Exercises

### Exercise 1: Classify the Three Operations

Recreate a list with two students before each case:

- Add a third student.
- Replace the student at index 1.
- Rename the student at index 1.

For each case, record:

- Element count before and after.
- Does the reference at index 1 remain the same?
- Is the original object mutated?
- What will a variable holding the original object observe?

Expected answer: adding grows the structure; `set` replaces the binding at the position; the setter changes the state of the same object.

### Exercise 2: Two Lists, One Shared Element

Create one `Student` and add that same object to two lists. Rename it through the first list, then replace the element in the first list with a different student.

You should observe two distinct outcomes:

1. Renaming the shared object is visible in both lists.
2. Replacing the element in the first list does not replace the element residing in the second list.

### Exercise 3: Shallow Copy and View

From a source list, create:

- `new ArrayList<>(source)`.
- `Collections.unmodifiableList(source)`.
- `List.copyOf(source)`.

Then perform each kind of change separately on the source: add an element, replace an element, mutate an element object. Record which sides observe the change and explain it using a reference graph.

Note that `List.copyOf` does not accept `null` elements; use valid data so the experiment focuses on sharing.

### Exercise 4: Same Size, Stale Iterator

Create an iterator on an `ArrayList`, add and then remove an element so the final size equals the initial size. Then attempt to iterate using the old iterator.

Explain why comparing sizes does not prove the iterator is still valid. The goal is to understand contract-violating operations, not to find a way to make the exception disappear.

### Exercise 5: Designing an Element Used as a Key

A class has `id`, `name`, and `email`. Choose which field identifies the object when used as a key and specify which fields may be mutated.

Explain the consequences if a field participating in `hashCode` is changed while the key is still in a map. Redesign using a stable identifier or an immutable key object, rather than relying on the luck of a single lookup.

## 18. Conclusions to Avoid

- “If size didn't change, structure didn't change.”
- “Not structural, so contents didn't change.”
- “No `ConcurrentModificationException`, so the code is correct.”
- “An unmodifiable list means its elements can't be mutated either.”
- “Copying a list copies every object inside it.”
- “Reassigning a variable obtained from `get` updates the position in the list.”
- “Removing an element from a list immediately destroys the object.”
- “A thread-safe collection means the elements inside it are thread-safe too.”
- “`ArrayList`'s definition applies identically to every collection.”

The skill to aim for is describing **what changes, who holds a reference to it, which contract governs the change, and what readers will observe**. Once these four questions are clear, behaviors around iterators, views, copying, and immutability become explainable and verifiable.
