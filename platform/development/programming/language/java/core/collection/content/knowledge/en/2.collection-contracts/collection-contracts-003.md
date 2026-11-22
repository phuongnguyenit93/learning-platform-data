# add, remove, clear, and Optional Operation Rules

## 1. Understanding "Having a Method" vs. "Supporting an Operation"

A collection is an object that manages a group of elements. When working with one, you often want to add an element, remove an element, or empty the entire group.

The three general methods on `Collection<E>` are:

```java
boolean add(E element);
boolean remove(Object element);
void clear();
```

These are API signatures for reading the contract, not a standalone runnable program.

The key point is: **a method existing on an interface does not mean every object implementing that interface supports the corresponding modification**.

```java
// Illustrative snippet inside a method; requires import java.util.*.
Collection<String> editable = new ArrayList<>();
Collection<String> readOnly = List.of("A", "B");

editable.add("C"); // Can be added.
// readOnly.add("C"); // Compiles, but throws UnsupportedOperationException at runtime.
```

Both variables have the same declared type `Collection<String>`. The difference lies in the object: the first object allows adding; the second does not allow modification.

"Optional operation" is a term in the Collections Framework contract. It allows an implementation class to not support a modification operation and signal that with `UnsupportedOperationException`. It does not mean the method is allowed to disappear, or that the caller can arbitrarily ignore the result.

This lesson focuses on add/remove contracts, easily confused variants, and safe usage on Java 17. You should already be familiar with reference variables, basic generics, `List`, and `Set`.

Foundational reference: [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 2. Purpose and Results of the Three Operations

| Method | Intent | Result on normal completion |
| --- | --- | --- |
| `add(e)` | Insert `e` into the collection according to its contract | `true` if the collection changed; `false` when a duplicate element is rejected by a structure that does not allow duplicates |
| `remove(o)` | Remove a single occurrence matching `o` | `true` if an element was removed; `false` if no matching element was present |
| `clear()` | Remove all elements | Returns no value; the collection is empty after the operation succeeds |

"Normal completion" means the call does not throw an exception. Do not infer results from the table if the operation is rejected or the input is invalid.

For an object that the program is allowed to modify, the return value helps express what happened. For example, adding to a set that already contains the element does not change the set; this is not an error that requires throwing an exception.

The tutorial [The Collection Interface](https://docs.oracle.com/javase/tutorial/collections/interfaces/collection.html) explains the same idea: general methods need to work across many kinds of collections, even though they store elements differently.

## 3. add(E): Adding Elements According to the Structure's Contract

### 3.1. Lists Usually Retain Duplicate Elements

```java
// Place inside a method; requires import java.util.*.
List<String> names = new ArrayList<>();

boolean first = names.add("An");
boolean second = names.add("An");

System.out.println(first);  // true
System.out.println(second); // true
System.out.println(names);  // [An, An]
```

Each `add` appends an element to the end of the list. Adding the same string twice still creates two positions, so both calls modify the list.

Here, `true` does not mean "it did not previously contain this value." It means the collection changed as a result of the call.

The append contract of `List.add(E)` is described in [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#add(E)).

### 3.2. Sets Do Not Create Duplicate Copies

```java
// Place inside a method; requires import java.util.*.
Set<String> codes = new LinkedHashSet<>();

boolean first = codes.add("A");
boolean second = codes.add("A");

System.out.println(first);  // true
System.out.println(second); // false
System.out.println(codes);  // [A]
```

The second call does not change the set. `false` is a valid result, not a sign of a system error.

You can use the result directly when business logic needs to know whether the element was just added:

```java
// Place inside a method; requires import java.util.*.
Set<String> registered = new LinkedHashSet<>();
if (registered.add("ID-01")) {
    System.out.println("New registration");
}
```

This single-threaded example avoids writing `contains` followed by `add` separately. However, it does not by itself make `LinkedHashSet` thread-safe.

For application-defined objects, the equality rules must be correct. Hash-table-based sets also rely on the `equals/hashCode` contract. Comparison-based sets have an additional requirement of consistency between the comparison and `equals`. This matters whenever "duplicate" differs from two references having the same address. [Set API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 3.3. add Does Not Use false to Represent Every Failure Reason

Do not interpret `false` as "any case where adding fails." A collection that refuses an addition for a reason other than the element already being present must report an appropriate error according to its contract.

For example:

- Object does not support adding: `UnsupportedOperationException`.
- Object does not accept `null`: may throw `NullPointerException` when adding `null`.
- Type or value restrictions apply: may throw `ClassCastException` or `IllegalArgumentException`.
- Cannot add right now due to capacity restrictions: may throw `IllegalStateException`.

For capacity-bounded queues, `Queue.offer` is typically the API that expresses no space remaining via its return value; `Queue.add` uses an exception for this situation. Do not carry `offer`'s interpretation over to `add`. [Queue API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)

### 3.4. List.add(index, element) Is a Different Method

```java
// Place inside a method; requires import java.util.*.
List<String> values = new ArrayList<>(List.of("A", "C"));
values.add(1, "B");
System.out.println(values); // [A, B, C]
```

`List.add(int, E)` returns `void`, not `boolean`. It inserts at the specified position rather than replacing the element there. Valid indices for insertion are from `0` to `size()`, inclusive of `size()` for inserting at the end.

To replace an element without changing the list size, the operation is `set(index, element)`. Supporting `set` does not imply supporting `add`.

## 4. remove(Object): Removing by Value, One Occurrence

### 4.1. true/false Results and Duplicate Elements

```java
// Place inside a method; requires import java.util.*.
List<String> values =
        new ArrayList<>(List.of("a", "b", "a"));

boolean removed = values.remove("a");
boolean missing = values.remove("missing");

System.out.println(removed); // true
System.out.println(missing); // false
System.out.println(values);  // [b, a]
```

`remove("a")` removes only **one** occurrence. For a `List`, that is the first occurrence in list order. It does not remove all elements equal to `"a"`.

Not finding a matching element to remove is normal for a collection that supports this operation. You do not need to catch an exception just to handle "element not present."

If business logic needs to remove all occurrences or filter by a condition, choose an appropriate operation such as `removeAll` or `removeIf`, and check the object's modification contract. Do not call `remove` once and assume that value is completely gone.

### 4.2. The Parameter Is Object Because This Is a Search/Remove Operation

The signature is `remove(Object)`, not `remove(E)`. The following example compiles:

```java
// Place inside a method; requires import java.util.*.
Collection<String> words = new ArrayList<>(List.of("one"));
System.out.println(words.remove(123)); // false with ArrayList in this example.
```

This does not allow putting integers into a `Collection<String>`. Adding and searching/removing have different signatures.

You also should not generalize that every collection returns `false` for an incompatible argument. Some structures may throw an exception by contract when the argument has the wrong type or is an unaccepted `null`. Check the documentation for the specific class and operation.

For data involving `null`, distinguish between:

- Removing a `null` element in a structure that allows `null`.
- Calling `remove(null)` on a structure that forbids `null`.
- Calling `remove` on a collection that does not allow modification at all.

These are different contract axes, not the same kind of error.

## 5. remove(int) and remove(Object) in List<Integer>

This is one of the harder bugs to spot because the code still compiles.

```java
// Place inside a method; requires import java.util.*.
List<Integer> numbers =
        new ArrayList<>(List.of(10, 20, 30));

Integer removedAtIndex = numbers.remove(1);
System.out.println(removedAtIndex); // 20
System.out.println(numbers);       // [10, 30]

boolean removedValue = numbers.remove(Integer.valueOf(10));
System.out.println(removedValue);  // true
System.out.println(numbers);       // [30]
```

There are two overloads:

| Call | Selected method | Meaning | Return type |
| --- | --- | --- | --- |
| `numbers.remove(1)` when `numbers` is `List<Integer>` | `remove(int index)` | Removes at index `1` | `Integer` |
| `numbers.remove(Integer.valueOf(10))` | `remove(Object value)` | Removes the value equal to `10` | `boolean` |

The index for `remove(int)` must be from `0` to `size() - 1`. An out-of-range index can cause `IndexOutOfBoundsException`; it does not return `false` to say "this index does not exist."

The declared type also affects which methods can be selected:

```java
// Place inside a method; requires import java.util.*.
Collection<Integer> values =
        new ArrayList<>(List.of(1, 2, 3));

boolean changed = values.remove(1);
System.out.println(changed); // true
System.out.println(values);  // [2, 3]
```

`Collection` does not have `remove(int index)`. The number `1` is boxed into an `Integer` to be passed to `remove(Object)`. The actual object is still an `ArrayList`; that does not make the compiler automatically add `List` overloads to a variable declared as `Collection`.

Another `remove` method is `Queue.remove()` with no arguments: it retrieves and removes the head of the queue, and can throw `NoSuchElementException` when empty. That is not `Collection.remove(Object)`.

Positional list operations are introduced in [The List Interface](https://docs.oracle.com/javase/tutorial/collections/interfaces/list.html).

## 6. clear(): Emptying an Existing Object

```java
// Place inside a method; requires import java.util.*.
List<String> tasks =
        new ArrayList<>(List.of("code", "test"));
tasks.clear();

System.out.println(tasks.isEmpty()); // true
System.out.println(tasks.size());    // 0
```

`clear` returns `void`. Therefore, `boolean changed = tasks.clear();` does not compile.

### 6.1. clear Differs from Reassigning a Variable to a New Collection

```java
// Place inside a method; requires import java.util.*.
List<String> original = new ArrayList<>(List.of("A"));
List<String> alias = original;

original.clear();
System.out.println(alias); // []
```

Both variables reference the same object. `clear` mutates that object, so the change is observed through `alias`.

Conversely:

```java
// Place inside a method; requires import java.util.*.
List<String> original = new ArrayList<>(List.of("A"));
List<String> alias = original;

original = new ArrayList<>();
System.out.println(original); // []
System.out.println(alias);    // [A]
```

The assignment only points the `original` variable to a new object. It does not empty the old object.

### 6.2. clear Does Not Deep-Delete or Securely Wipe Sensitive Data

The collection drops the elements from its managed structure. This does not mean:

- Calling a destructor or cleanup method on each element.
- Closing resources such as files or connections held by the elements.
- Clearing the state of elements that are still referenced elsewhere.
- Guaranteeing that data is overwritten in RAM.
- Guaranteeing that memory is immediately returned to the operating system.
- Guaranteeing that internal storage capacity shrinks according to a universal policy.

For resources that need closing, manage resource lifecycles separately. For sensitive data, do not use `clear` as proof of secure erasure.

## 7. Four Object Groups and Different Support Levels

### 7.1. Modifiable Collections

A standard `ArrayList` supports adding, removing, replacing elements, and clearing. That does not mean every operation is error-free: indices must still be valid, and inputs must still meet the required preconditions. [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 7.2. Fixed-Size Lists

```java
// Place inside a method; requires import java.util.*.
String[] array = {"red", "blue"};
List<String> fixed = Arrays.asList(array);

fixed.set(0, "green");
System.out.println(Arrays.toString(array)); // [green, blue]
// fixed.add("yellow"); // UnsupportedOperationException.
// fixed.remove("blue"); // UnsupportedOperationException.
// fixed.clear(); // UnsupportedOperationException for this non-empty data.
```

`Arrays.asList` returns a list backed by the array. It allows replacing existing elements but does not support resizing.

"Fixed-size" does not mean "cannot modify content." Modifying an element through the list is reflected in the array and vice versa. [Arrays.asList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...))

### 7.3. Unmodifiable Objects

`List.of(...)` creates an unmodifiable list that does not accept `null`. Modification operations such as add, remove, replace, or clear are rejected per the factory contract.

```java
// Place inside a method; requires import java.util.List.
List<String> values = List.of("x", "y");
// values.add("z");    // UnsupportedOperationException.
// values.remove("x"); // UnsupportedOperationException.
// values.clear();     // UnsupportedOperationException.
```

An unmodifiable collection does not automatically make each element immutable. If an element is an object with mutable state, code that still holds a reference to that element can still modify its state.

### 7.4. Unmodifiable Views

```java
// Place inside a method; requires import java.util.*.
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(backing);

backing.clear();
System.out.println(view); // []
```

`view.clear()` is rejected. However, `backing.clear()` still changes the data that the view is observing. Do not treat this view as an independent copy.

In contrast, `List.copyOf(backing)` produces a result that does not reflect subsequent structural changes to the source collection; it is still a shallow copy of element references and does not promise to create a new object in every case.

View rules and delegated operations are described in [Collections.unmodifiableCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableCollection(java.util.Collection)) and its sibling wrappers.

## 8. Optional Operation Rules

### 8.1. Support Is Defined Per Operation, Not by a Single Flag

An object can allow `set` without allowing `add`. A view can allow `remove` and `clear` to modify the underlying structure, while disallowing `add` because it lacks the information needed to add.

Therefore, do not infer:

- "Since `set` works, `add` must work too."
- "`remove` failed, so all operations are unsupported."
- "The object is a `List`, so it can definitely be removed from."
- "The current size is 0, so `clear` can be called anywhere."

When writing a custom collection class, skeletal classes such as [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) and [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html) provide default implementations. To support modification, implementers must override the corresponding extension points; merely extending a skeletal class does not guarantee all modification operations will work.

### 8.2. No-Op Operations Can Still Be Rejected

The general contract allows an unsupported operation to throw `UnsupportedOperationException` even when the specific call appears to cause no change. Some implementation classes may complete normally if there is nothing to do; specific factories or wrappers may provide stronger guarantees.

Examples where you must check the specific contract:

- `clear()` on a collection that is already empty.
- `remove(x)` when `x` is not present.
- `addAll` with an empty source.

Do not take a single successful `clear` on an empty collection as proof that it supports removing elements when non-empty. Do not use "trying a harmless operation" as a mechanism to detect whether a collection is modifiable.

### 8.3. There Is No Universal Type Check for Modifiable Collections

`instanceof List` or `instanceof Collection` only checks type relationships. It does not answer whether the `add` operation is supported.

Checking `instanceof ArrayList` is also not a general design for an API that accepts multiple data types. Instead:

1. State the preconditions clearly if the method modifies its argument.
2. Only pass objects that satisfy those preconditions.
3. Or create a separate collection when the method should not modify the source.

If a clearer read-only API is needed, parameter choices and ownership design must express that; the `Collection` interface itself still includes mutating methods.

## 9. Classifying Errors Properly to Handle Them Properly

| Symptom | Meaning to consider | What not to conclude |
| --- | --- | --- |
| `add` on a `Set` returns `false` on duplicate | No change because the element already exists | The system has a bug |
| `remove(Object)` returns `false` | No element was removed in a valid call | The collection is definitely unmodifiable |
| `UnsupportedOperationException` | Operation rejected by the object's contract | The input is always wrong |
| `IndexOutOfBoundsException` from a positional operation | Invalid index | Should retry with the same index |
| `NullPointerException` | Could be a `null` collection or `null` input, depending on the call site | Every collection forbids `null` |
| `ClassCastException` or `IllegalArgumentException` | Type or value does not meet constraints | Every collection has the same constraints |
| `IllegalStateException` when adding to a bounded queue | Cannot add in the current state | `add` should return `false` |

The order of exceptions when a request violates multiple conditions at once is not a universal guarantee. Do not write business logic that depends on "the index must be checked first, then modifiability" unless the documentation specifies it.

Also do not catch `RuntimeException` and ignore everything. Doing so can hide contract bugs, data errors, and programming mistakes.

## 10. Modifying During Iteration and Atomicity Boundaries

Adding or removing structurally inside a `for-each` loop by calling the collection directly can invalidate the iterator. With many implementations like `ArrayList`, you may encounter `ConcurrentModificationException`, but you must not rely on this exception always occurring to ensure correctness.

If you need to remove the current element and the iterator supports it, use `Iterator.remove` after `next`:

```java
// Place inside a method; requires import java.util.*.
List<String> values =
        new ArrayList<>(List.of("keep", "drop", "keep"));

Iterator<String> iterator = values.iterator();
while (iterator.hasNext()) {
    if (iterator.next().equals("drop")) {
        iterator.remove();
    }
}
System.out.println(values); // [keep, keep]
```

`Iterator.remove` is also an optional operation. It may only be called once per `next` call; not every iterator supports it. [Iterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

For a sequence of multiple operations:

```java
// Illustrative idea; no general transaction guarantee.
target.clear();
target.add("replacement");
```

There is no general contract that two calls form a transaction. If the later call fails, do not assume the removed elements will be restored automatically.

When multiple threads access a collection concurrently, an operation being supported does not mean the object is thread-safe. You need proper synchronization or an appropriate concurrent structure, not just a different declared type.

## 11. Designing Methods When Data Modification Is Needed

### 11.1. Mutating Directly: Document Effects and Preconditions

```java
// Method declaration snippet; requires import java.util.Collection.
// Mutates the caller's collection; requires the collection to support clear.
static void reset(Collection<?> target) {
    target.clear();
}
```

The name `reset` alone is not enough to convey all effects. Documentation should state:

- The method mutates the argument rather than returning a copy.
- Views or other references may observe the change.
- The collection must support `clear`.
- `null` must not be passed unless the method handles it explicitly.

Do not call `isEmpty` first just to dodge an exception. That approach can make the API sometimes "succeed" and sometimes fail depending on input data, while leaving the modifiability requirement unclear.

### 11.2. Preserving the Source: Create a Modifiable Copy

```java
// Place inside a method; requires import java.util.*.
List<String> source = List.of("A", "B");
List<String> result = new ArrayList<>(source);

result.remove("A");
result.add("C");

System.out.println(source); // [A, B]
System.out.println(result); // [B, C]
```

This is a good choice when the input only supplies data, rather than serving as a container the method is entitled to mutate.

Creating an `ArrayList` is also a contract decision: it preserves source iteration order and allows duplicate elements. Do not use this copy if the problem requires preserving `Set` behavior or a comparator-ordered structure. Choose a copy type that matches the requirements.

### 11.3. Do Not Use Exception Catching as a Blind Mutate-Then-Copy Strategy

Avoid the pattern of "try a sequence of mutations, and if `UnsupportedOperationException` occurs, copy and rerun" without knowing how far the state was already modified. An earlier step may have succeeded.

Choosing between mutating in place and creating a new result should be a method contract decision. Catching `UnsupportedOperationException` can be appropriate at an error-display boundary or in a learning program to observe behavior; it is not a substitute for ownership design.

## 12. Complete Program

Save as `OptionalOperationsDemo.java`. The program demonstrates concrete collections so the output can be verified precisely.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class OptionalOperationsDemo {
    private static void showUnsupported(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": completed");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + ": UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> list = new ArrayList<>();
        System.out.println("List add A: " + list.add("A"));
        System.out.println("List add A again: " + list.add("A"));
        list.add("B");
        System.out.println("List: " + list);

        Set<String> set = new LinkedHashSet<>();
        System.out.println("Set add A: " + set.add("A"));
        System.out.println("Set add A again: " + set.add("A"));
        System.out.println("Set: " + set);

        Collection<String> values =
                new ArrayList<>(List.of("a", "b", "a"));
        System.out.println("Remove a: " + values.remove("a"));
        System.out.println("After remove: " + values);
        System.out.println("Remove missing: " + values.remove("missing"));
        values.clear();
        System.out.println("After clear: " + values);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        System.out.println("remove(1): " + numbers.remove(1));
        System.out.println("Numbers: " + numbers);
        System.out.println("remove(Integer 10): "
                + numbers.remove(Integer.valueOf(10)));
        System.out.println("Numbers: " + numbers);

        Collection<Integer> numberCollection =
                new ArrayList<>(List.of(1, 2, 3));
        System.out.println("Collection remove(1): "
                + numberCollection.remove(1));
        System.out.println("Collection numbers: " + numberCollection);

        String[] array = {"red", "blue"};
        List<String> fixed = Arrays.asList(array);
        System.out.println("Fixed set old: " + fixed.set(0, "green"));
        System.out.println("Array: " + Arrays.toString(array));
        showUnsupported("Fixed add", () -> fixed.add("yellow"));
        showUnsupported("Fixed remove", () -> fixed.remove("blue"));
        showUnsupported("Fixed clear", fixed::clear);

        List<String> readOnly = List.of("x", "y");
        showUnsupported("Read-only add", () -> readOnly.add("z"));
        showUnsupported("Read-only remove", () -> readOnly.remove("x"));
        showUnsupported("Read-only clear", readOnly::clear);

        List<String> backing = new ArrayList<>(List.of("secret"));
        List<String> view = Collections.unmodifiableList(backing);
        List<String> copy = List.copyOf(backing);
        backing.clear();
        System.out.println("View after backing clear: " + view);
        System.out.println("Copy after backing clear: " + copy);

        List<String> editable = new ArrayList<>(readOnly);
        editable.add("z");
        editable.remove("x");
        System.out.println("Editable copy: " + editable);
        System.out.println("Original read-only: " + readOnly);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 OptionalOperationsDemo.java
java OptionalOperationsDemo
```

A JDK with `javac` is required. The code was compiled with `--release 17` and run on a newer JDK; no post-Java 17 APIs are used.

Stdout:

```text
List add A: true
List add A again: true
List: [A, A, B]
Set add A: true
Set add A again: false
Set: [A]
Remove a: true
After remove: [b, a]
Remove missing: false
After clear: []
remove(1): 20
Numbers: [10, 30]
remove(Integer 10): true
Numbers: [30]
Collection remove(1): true
Collection numbers: [2, 3]
Fixed set old: red
Array: [green, blue]
Fixed add: UnsupportedOperationException
Fixed remove: UnsupportedOperationException
Fixed clear: UnsupportedOperationException
Read-only add: UnsupportedOperationException
Read-only remove: UnsupportedOperationException
Read-only clear: UnsupportedOperationException
View after backing clear: []
Copy after backing clear: [secret]
Editable copy: [y, z]
Original read-only: [x, y]
```

### Reading the Results by Mechanism

- Both additions of `A` to `ArrayList` mutate the data, whereas the second addition in `LinkedHashSet` returns `false`.
- The collection containing `a, b, a` loses only the first `a`. Removing `missing` returns `false`.
- `clear` empties the collection; there is no return value to print.
- `List<Integer>.remove(1)` removes the element at index `1` and returns `20`.
- `remove(Integer.valueOf(10))` removes by value and returns `true`.
- Through a `Collection<Integer>` variable, `remove(1)` removes the value `1`.
- `Arrays.asList` allows `set`, modifying the source array, but rejects the attempted resizing operations.
- `List.of` rejects the modification operations in the example.
- The unmodifiable view still sees the source being cleared via `clear`. The `List.copyOf` copy does not reflect that structural change.
- The `ArrayList` copy is structurally modified independently of the unmodifiable source list.

The `showUnsupported` helper is only for demonstration: it prints the expected exception instead of letting the program terminate. It does not catch all exception types and does not prescribe a production error-handling policy.

## 13. Mistakes to Recognize When Reading Code

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `add` returning `true` means the value did not exist | Misinterpretation for `List` | Read the result as "did the collection change?" |
| Assuming `remove` removes all duplicate elements | Duplicate data remains | Choose an operation that removes all or matches a condition |
| Using `remove(1)` to remove the number `1` from `List<Integer>` | Accidentally removes the element at index `1` | Pass `Integer.valueOf(1)` when removing by value |
| Assuming `clear` returns `boolean` | Fails to compile | Call `clear` as a `void` operation |
| Treating `Arrays.asList` as a resizable `ArrayList` | Encounters `UnsupportedOperationException` | Create `new ArrayList<>(...)` if resizing is needed |
| Treating an unmodifiable view as a copy | Sees source data change unexpectedly | Choose a copy or a view intentionally |
| Testing `clear` on an empty collection to detect modifiability | Unwarranted conclusion | Rely on the specific contract |
| Catching all exceptions and continuing | Hides bad data or incomplete operations | Classify errors and keep state clear |
| Modifying a collection directly inside `for-each` | Iterator may become invalid | Use a supported removal mechanism while iterating |
| Using `clear` as secure erasure of secrets | Incorrect security assumption | Manage sensitive data with dedicated mechanisms |

## 14. Self-Check and Practice

### Questions

1. Why can two `add("A")` calls on a `List` both return `true`?
2. Is `Set.add` returning `false` on a duplicate an error?
3. How many occurrences does `remove(Object)` remove?
4. How does `List<Integer>.remove(1)` differ from `Collection<Integer>.remove(1)`?
5. Why does `Arrays.asList` allow `set` but not adding elements?
6. Does a successful `clear` on empty data prove the object can remove elements when non-empty?
7. Why can a `Collection` variable still point to an unmodifiable object?
8. Does an unmodifiable view continue to observe changes from the source collection?
9. Does `clear` close resources or securely wipe data from memory?
10. What must a method that mutates an incoming collection declare?

### Exercises

- Run the full program and explain each `true/false` line using before-and-after state.
- Add another `remove("A")` call on a list containing `A, A, B`; verify that one `A` still remains.
- Change the integer example to remove the **value** `1` from the list `10, 20, 1`, without removing by index.
- Create a new list using `new ArrayList<>(Arrays.asList(...))` and verify that adding/removing works without changing the original array's size.
- Write a method that creates a copy, removes unwanted elements, and returns the result; verify that the source is not mutated.
- Compare the contracts of the three sources `new ArrayList<>()`, `Arrays.asList(...)`, and `List.of(...)`, without using the result of an empty-collection operation as a modifiability test.

### Answer Hints

1. Each addition creates a new position, so the list changes.
2. No; the set already contains the element and does not create duplicates.
3. One occurrence; `List` removes the first matching occurrence.
4. On `List`, the index-based overload is selected; on `Collection`, only the object-based overload exists.
5. It is a view of a fixed-length array; replacing element contents does not change the length.
6. No; the rule for no-op operations does not provide that guarantee.
7. The declared type specifies the API, while the object's contract determines the level of support.
8. Yes, if it is a live view of the source like the demonstrated wrapper.
9. No; those are separate responsibilities.
10. Effects on the argument, operations that must be supported, input constraints, relationship to views/other references, and relevant error behavior.
