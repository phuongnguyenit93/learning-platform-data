# UnsupportedOperationException on factories, wrappers, and views

## 1. Why does a method call compile yet get rejected at runtime?

The following snippet compiles validly but fails at runtime:

```java
List<String> names = List.of("An", "Binh");
names.add("Chi"); // UnsupportedOperationException
```

This is an illustrative snippet inside a method with `java.util.List` imported.

The `List` type declares the `add` method, but it does not promise that every object implementing `List` supports this operation. Some mutating methods in Java Collections are **optional operations**. If an object does not support the requested operation, it may throw `UnsupportedOperationException`, abbreviated in this explanation as UOE. [Java 17 Collection documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

UOE is a runtime exception, not a compile-time error. It usually indicates that the code is requesting a mutation capability that the current object does not provide. To fix it properly, you need to examine where the collection was created and which exact operation was rejected.

Three common sources:

- **Factory:** a method that creates/returns a collection, such as `List.of`, `Arrays.asList`, or `Stream.toList`.
- **Wrapper:** an object wrapping another collection, such as `Collections.unmodifiableList`.
- **View:** a view linked to underlying source data, such as `subList`, `keySet`, or `values`.

These are not three mutually exclusive labels. `Arrays.asList` is a factory that returns a view of an array; `Collections.unmodifiableList` is a wrapper that also provides a view disallowing modifications through the wrapper.

## 2. Separate the three questions about mutability

When reading a collection's contract, do not simply ask "is it mutable?". Ask specifically:

1. Can elements be added or removed, meaning can its size change?
2. Can existing elements or values be replaced?
3. If the underlying source data or element objects change from elsewhere, does the collection observe those changes?

| Creation example | Add/remove elements | Replace elements via `set` | Relationship to source data |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Yes | Yes | New structure; element references may still be shared |
| `Arrays.asList(array)` | No size change | Yes | View of the array itself |
| `List.of(...)` | No | No | No backing list modifiable through a source reference held by the caller |
| `List.copyOf(source)` | No | No | Result does not reflect adding/removing/replacing references in source after copying |
| `Collections.unmodifiableList(source)` | Not through wrapper | Not through wrapper | Read view over source; source can still be modified through another reference |
| `source.subList(from, to)` | Depends on source capabilities | Depends on source | View of a range within source |

The table describes operations on the collection structure and stored references. It does not promise that the element objects have become deeply immutable.

A `final List<String>` variable does not change this contract either: `final` prevents reassigning the variable to another list, not mutating the list object itself.

## 3. Factories do not always return the same kind of collection

### 3.1. List.of, Set.of, and Map.of disallow mutation through their API

The `List.of`, `Set.of`, and `Map.of` factories return collections/maps that disallow modification through the result's API. With `List.of`, even `set(index, value)` is unsupported. It is not just size-changing operations that are rejected.

For example:

```java
List<String> values = List.of("A", "B");
values.set(0, "X"); // UnsupportedOperationException
```

These factories also have their own data rules: `List.of` disallows null elements; `Map.of` disallows null keys and values. A failure at creation time due to null is not a UOE caused by mutating an already-created collection. [List documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Do not infer the internal implementation type from a factory. Casting the result to `ArrayList` does not turn it into a modifiable collection; the cast can also throw a `ClassCastException`.

### 3.2. Arrays.asList: fixed size, yet elements can still be replaced

`Arrays.asList(array)` returns a fixed-size list backed by the given array. `set` is supported, and changes are visible from both the array and the list. Operations that change the size are unsupported. [Java 17 Arrays.asList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...))

Illustrative example:

```java
String[] array = {"A", "B"};
List<String> fixed = Arrays.asList(array);
fixed.set(0, "X");  // valid; array[0] is also "X"
fixed.add("C");     // UnsupportedOperationException
```

Requires importing `java.util.List` and `java.util.Arrays`.

Because the number of elements does not change, an operation like replacing all values or sorting can be performed on this list using its supported capabilities. Do not label it "completely unmodifiable" just because `add` fails.

Type note: the internal list returned by `Arrays.asList` is not `java.util.ArrayList` merely because its internal class name happens to contain `ArrayList`. Rely on the method contract rather than a class name observed in a debugger.

### 3.3. Stream.toList differs from Collectors.toList

In Java 17:

- `stream.toList()` returns an unmodifiable list; calling a mutating method throws UOE.
- `stream.collect(Collectors.toList())` makes no guarantees about the implementation type or mutability of the returned list.
- When you specifically need a modifiable `ArrayList`, use `collect(Collectors.toCollection(ArrayList::new))`.

Do not fix a bug by relying on a particular implementation version happening to return an `ArrayList`. [Stream.toList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()), [Collectors.toList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList())

This is a difference in return contracts; methods with similar names are not guaranteed to be equivalent.

## 4. An unmodifiable wrapper does not mean the data is frozen

### 4.1. Unmodifiable wrappers block mutation paths through the wrapper

For example:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> exposed = Collections.unmodifiableList(source);
```

This snippet requires importing `java.util.List`, `java.util.ArrayList`, and `java.util.Collections`.

`exposed.add(...)`, `exposed.set(...)`, and mutation through `exposed`'s iterator are rejected. However, if a reference to `source` is retained, other code can still add or replace elements in the source; those changes are observed through `exposed` because the wrapper is a read view over the source. [Collections.unmodifiableList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

```text
source -----> backing ArrayList
                  ^
                  |
exposed ---> read-only wrapper along this access path
```

A wrapper controls one access path; it does not revoke mutation rights from all other references to the backing object.

Not every wrapper is intended to forbid modification. For example, a synchronized wrapper has a different responsibility. Read the contract of the method that creates the wrapper; do not infer behavior from the word "wrapper" alone.

### 4.2. A structural snapshot differs from a live view

If you need a result that does not reflect subsequent changes to the source list after creation, you can use `List.copyOf(source)` when its null policy fits. The API permits reusing a suitable unmodifiable instance; do not write tests that rely on whether the reference is guaranteed to be distinct from or identical to the source.

The difference can be verified by behavior:

```text
Create source = [A]
Create live = unmodifiableList(source)
Create snapshot = List.copyOf(source)
Add B to source

live observes [A, B]
snapshot still observes [A]
```

"Snapshot" here refers to the elements/references stored in the collection. If an element is a mutable object, mutations inside that object can still be observed through both.

### 4.3. An unmodifiable collection does not mean deeply immutable elements

Illustrative example:

```java
StringBuilder item = new StringBuilder("A");
List<StringBuilder> values = List.of(item);
item.append("!"); // values.get(0).toString() is now "A!"
```

No operation added, removed, or replaced an element in `values`. The referenced object mutated its own state. Therefore, a test that only verifies `add` throws UOE does not prove that the entire data graph is immutable.

If the contract requires deep immutability, you must design the element types and copying policy accordingly, and test them separately.

## 5. Views may allow mutation in some directions and reject others

### 5.1. subList inherits the capabilities of the backing list

`subList(from, to)` is a view of the range `[from, to)`, not an independent copy. With a modifiable `ArrayList` source, `set`, add, or remove operations through the sublist are reflected in the source. If the source is unmodifiable or fixed-size, those corresponding restrictions also apply to the view. [List.subList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int))

State example:

```text
base = [A, B, C, D]
part = base.subList(1, 3)   -> [B, C]
part.set(0, X)             -> base = [A, X, C, D]
part.remove(1)             -> base = [A, X, D]
part.add(Y)                -> base = [A, X, Y, D]
```

Therefore, do not conclude that "views always throw UOE on modification".

Another issue: if the backing list is structurally modified directly outside the sublist path, the semantics of the view become undefined by contract. Do not design general tests expecting every implementation to throw `ConcurrentModificationException` in every such situation. Nor is that a UOE caused by a forbidden operation.

### 5.2. keySet, values, and entrySet do not support add like standalone collections

For a modifiable map, the standard views from `keySet()`, `values()`, and `entrySet()` allow removing mappings via supported removal operations. However, they do not support `add`/`addAll` under the contract of these views. [Map collection views documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#keySet())

Reasons to understand the model:

- Adding a key to `keySet` provides no value for the new mapping.
- Adding a value to `values` provides no key.
- Even `entrySet` is not treated by default as a standalone set that supports adding entries.

Add mappings using `map.put(key, value)` or an appropriate map API. When removing through a view, remember that the underlying source data is also removed; this may be the desired behavior or an unintended side effect.

If the backing map is unmodifiable, removal paths through the views are also blocked. You must identify both the kind of view and the capabilities of the backing map.

### 5.3. Map entries have their own value-mutation path

An entry obtained from the iterator of a `HashMap`/`LinkedHashMap` can support `setValue`, updating the backing map. An entry obtained through `Collections.unmodifiableMap(...).entrySet()` does not provide a backdoor around the wrapper: `setValue` is rejected.

Therefore, when testing an unmodifiable map, do not check only `put`. Check related mutation paths as well, such as removal through `keySet` or updating entries if the API contract exposes those access paths.

## 6. Do not use no-op mutations to probe mutability

The following checks are not reliable tests of general mutability:

```java
collection.addAll(List.of());
collection.remove("gia-tri-khong-ton-tai");
collection.clear(); // when the collection is empty
```

These are illustrative expressions. At the general collection contract level, a mutating operation that has no actual effect may be permitted to do nothing or throw UOE unless the specific API specifies a stronger rule. Therefore, "not throwing an exception" in a no-op case does not prove that an effective mutation will be supported. [Collection documentation on no-op operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

A specific factory may specify a stricter guarantee—for example, mutating methods on `List.of` results are rejected. Respect that guarantee, but do not generalize it to every object just because it shares the `List` type.

To test mutation rejection, choose an operation that would genuinely alter the contents and uses valid arguments: adding a new element, removing an existing element, or calling `set` at an existing index with a different value.

## 7. Complete runnable Java 17+ program

The program below checks both rejected operations and valid modifications. It uses self-checking helper methods and does not depend on `-ea` or external libraries.

Save as `UnsupportedOperationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnsupportedOperationsDemo {
    private static int passed;

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static void expectUoe(String label, Runnable action) {
        try {
            action.run();
        } catch (UnsupportedOperationException expected) {
            passed++;
            return;
        }
        throw new AssertionError(label + ": expected UnsupportedOperationException");
    }

    public static void main(String[] args) {
        List<String> factory = List.of("A", "B");
        expectUoe("List.of add", () -> factory.add("C"));
        expectUoe("List.of set", () -> factory.set(0, "X"));
        expectUoe("List.of remove", () -> factory.remove(0));
        Iterator<String> factoryIterator = factory.iterator();
        factoryIterator.next();
        expectUoe("List.of iterator remove", factoryIterator::remove);
        expectUoe("Set.of add", () -> Set.of("A", "B").add("C"));
        expectUoe("Map.of put", () -> Map.of("A", 1).put("B", 2));

        String[] array = {"A", "B"};
        List<String> fixed = Arrays.asList(array);
        fixed.set(0, "X");
        checkEquals("set updates backing array", "X", array[0]);
        array[1] = "Y";
        checkEquals("array update visible in list", List.of("X", "Y"), fixed);
        expectUoe("fixed size add", () -> fixed.add("Z"));
        expectUoe("fixed size remove existing", () -> fixed.remove(0));
        fixed.replaceAll(String::toLowerCase);
        checkEquals("replace values without resizing", List.of("x", "y"),
                Arrays.asList(array));

        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> live = Collections.unmodifiableList(backing);
        expectUoe("wrapper add", () -> live.add("B"));
        expectUoe("wrapper set", () -> live.set(0, "X"));
        backing.add("B");
        checkEquals("wrapper observes backing add", List.of("A", "B"), live);
        List<String> snapshot = List.copyOf(backing);
        backing.set(0, "X");
        checkEquals("wrapper observes backing set", List.of("X", "B"), live);
        checkEquals("copyOf snapshot stays unchanged", List.of("A", "B"), snapshot);
        expectUoe("copyOf add", () -> snapshot.add("Z"));

        StringBuilder item = new StringBuilder("A");
        List<StringBuilder> shallow = List.of(item);
        item.append("!");
        checkEquals("unmodifiable is not deep immutability", "A!",
                shallow.get(0).toString());

        List<String> base = new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> part = base.subList(1, 3);
        part.set(0, "X");
        checkEquals("subList set updates parent", List.of("A", "X", "C", "D"), base);
        part.remove(1);
        checkEquals("subList remove updates parent", List.of("A", "X", "D"), base);
        part.add("Y");
        checkEquals("subList add updates parent", List.of("A", "X", "Y", "D"), base);
        List<String> readOnlyPart = Collections.unmodifiableList(base).subList(1, 3);
        expectUoe("unmodifiable subList set", () -> readOnlyPart.set(0, "Z"));
        List<String> fixedPart = fixed.subList(0, 1);
        expectUoe("fixed size subList add", () -> fixedPart.add("Z"));
        fixedPart.set(0, "Z");
        checkEquals("fixed size subList still supports set", "Z", array[0]);

        Map<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        expectUoe("keySet add", () -> map.keySet().add("C"));
        expectUoe("values add", () -> map.values().add(3));
        expectUoe("entrySet add", () -> map.entrySet().add(Map.entry("C", 3)));
        map.keySet().remove("A");
        checkEquals("keySet removal updates map", false, map.containsKey("A"));
        Map.Entry<String, Integer> entry = map.entrySet().iterator().next();
        entry.setValue(20);
        checkEquals("entry setValue updates map", 20, map.get("B"));
        Map<String, Integer> readOnlyMap = Collections.unmodifiableMap(map);
        Map.Entry<String, Integer> readOnlyEntry =
                readOnlyMap.entrySet().iterator().next();
        expectUoe("unmodifiable map entry setValue", () -> readOnlyEntry.setValue(30));
        expectUoe("unmodifiable map keySet remove", () -> readOnlyMap.keySet().remove("B"));
        checkEquals("map unchanged by rejected view edits", Map.of("B", 20), map);

        List<String> streamResult = Stream.of("A", "B").toList();
        expectUoe("Stream.toList add", () -> streamResult.add("C"));
        List<String> collected = Stream.of("A", "B")
                .collect(Collectors.toCollection(ArrayList::new));
        collected.add("C");
        checkEquals("explicit mutable collector", List.of("A", "B", "C"), collected);
        List<String> editable = new ArrayList<>(factory);
        editable.add("C");
        checkEquals("mutable copy", List.of("A", "B", "C"), editable);
        checkEquals("factory source preserved", List.of("A", "B"), factory);

        System.out.println("fixed-size list = " + fixed);
        System.out.println("live wrapper = " + live);
        System.out.println("snapshot = " + snapshot);
        System.out.println("mutable subList parent = " + base);
        System.out.println("map after view operations = " + map);
        System.out.println("PASS: " + passed + " checks");
    }
}
```

Compile and run:

```shell
javac --release 17 UnsupportedOperationsDemo.java
java UnsupportedOperationsDemo
```

Stdout when all checks pass:

```text
fixed-size list = [Z, y]
live wrapper = [X, B]
snapshot = [A, B]
mutable subList parent = [A, X, Y, D]
map after view operations = {B=20}
PASS: 36 checks
```

`expectUoe` treats only UOE as the expected outcome; any other failure still causes the program to fail. The checked mutation attempts use valid elements or indices so that they do not accidentally test input validation errors instead of modification limits.

The `replaceAll` check uses ASCII letters to focus on element replacement capability. In a real-world text normalization task, casing and locale policies should be specified separately.

## 8. Read the stack trace and fix according to code intent

### 8.1. Trace back to where the collection was created

When encountering a UOE, inspect:

1. Which line of code requests the mutation: `add`, `remove`, `set`, `sort`, `replaceAll`, an iterator, or an entry operation?
2. Which constructor, factory, wrapper, or view created the object?
3. Does the object's contract support that operation?
4. Is the program's intent to mutate the source, mutate a copy, or only read?

Internal class names in a stack trace can help trace the origin, but they should not become branching conditions in application code or implementation-dependent test assertions.

### 8.2. Need a modifiable copy: create a collection you own and can mutate

For example:

```java
List<String> editable = new ArrayList<>(readOnlyValues);
editable.add("new-value");
```

This snippet creates a new modifiable structure; it does not change the capabilities of `readOnlyValues`. For a map, you can use `new HashMap<>(sourceMap)` or `new LinkedHashMap<>(sourceMap)` depending on the guarantees you need to preserve.

Check the implications:

- Modifying the copy does not update the source structure.
- Element objects may still share references.
- Changing the collection type may affect ordering, key handling, or support for special values.

Do not blindly copy if the business intent is to update the actual source. In that case, you need to change how the data is designed/supplied or call a supported API on the object that owns the source.

### 8.3. Only need to read: remove out-of-contract mutations

A method designed to be read-only should not sort its argument in place before processing, because `sort` mutates the list. If you need a sorted sequence for computation while preserving the source, copy it and sort the copy.

Similarly, do not call `clear()` to "clean up" a collection that the method does not have permission to mutate. Receiving a `List` or `Map` parameter does not automatically grant permission to modify every object passed in.

### 8.4. Do not catch UOE and ignore it

Ignoring the error can cause new data to never be added while the execution flow still reports success. Automatically trying to mutate the source and falling back to creating a copy on failure also easily makes behavior dependent on data and implementation details.

Furthermore, general bulk mutation operations do not carry an automatic transactional guarantee just because they use the Collections API. If an operation fails after completing part of its work, you must not assume the entire state has been rolled back. Rely on specific contract guarantees, or prepare the result separately before replacing data that you own.

## 9. Test modification limits as part of the contract

### 9.1. Test both forbidden operations and promised capabilities

A fixed-size list needs to be tested differently from an unmodifiable list:

| Target object | Operations to verify as valid | Operations to verify as rejected |
| --- | --- | --- |
| `Arrays.asList` over a two-element array | `set` reflects into the array | Adding an element or removing an existing index |
| Populated `List.of` | Reading expected contents | `add`, `set`, `remove` |
| Unmodifiable wrapper | Observing valid updates made to the backing collection | Mutating directly or through the wrapper's iterator/views |
| `ArrayList.subList` | Mutating through the view updates the source properly | Do not expect UOE for every mutating operation |
| View from a modifiable map | Removing an existing mapping through the view | `add` on standard collection views |
| View from an unmodifiable map | Reading expected mappings | Removing through a view or calling `Entry.setValue` |

Do not just test that "the right exception is thrown" and forget to verify the remaining data. For the specific API under test, verify that rejected operations do not alter the data protected by the contract.

### 9.2. Isolate the exact call when testing exceptions

In an environment with JUnit Jupiter available, you can write a test method like this:

```java
List<String> values = List.of("A", "B");
assertThrows(UnsupportedOperationException.class, () -> values.add("C"));
assertEquals(List.of("A", "B"), values);
```

This is an illustrative snippet inside a test method with static imports from `org.junit.jupiter.api.Assertions`. It is not a standalone program.

Setting up data before the assertion separates setup failures from the operation being tested. Do not pass an invalid index or invalid element and expect a particular exception when multiple contract violations occur simultaneously.

With an iterator, call `next()` before `remove()` when the goal is to test modification limits. If the iterator has not yet returned an element, an object may throw an illegal-state exception instead; that is a different test target.

### 9.3. Test views, snapshots, and elements in separate test cases

Three independent checks:

- Attempt mutation through the result's API: is it rejected according to the contract?
- Mutate the source through a valid path: should the result observe the change or remain unchanged?
- Mutate the state of an element object: does the contract require deep independence?

Mixing all three and concluding "immutable" overall easily causes tests to promise more than the code actually provides.

## 10. Common misconceptions

| Misconception | Correction |
| --- | --- |
| "If it's declared as a List, `add` must work." | Mutating methods can be optional operations on a specific object. |
| "`Arrays.asList` cannot be modified at all." | Its size cannot change, but elements can be replaced and reflected in the array. |
| "An unmodifiable wrapper is a copy." | It reads through to the backing collection; distinguish it from a snapshot. |
| "Every view is read-only." | A sublist of a modifiable source and map views support certain mutation/removal directions. |
| "If a Map is modifiable, `keySet.add` works too." | Collection views are not equivalent to standalone collections that support adding. |
| "If `add` is disallowed, the elements cannot change." | Element objects may still mutate their own internal state. |
| "Removing a non-existent element didn't throw, so `remove` is supported." | A no-op operation does not prove general mutability. |
| "`Collectors.toList` always returns a modifiable `ArrayList`." | The contract does not guarantee that; specify a collection factory when explicit mutability is needed. |
| "Catching UOE means the problem is handled." | You must fulfill the intended behavior or fail clearly, not swallow the exception. |

## 11. Self-check and practice

### Question 1: Why does `set` succeed on `Arrays.asList` but fail on `List.of`?

`Arrays.asList` provides a fixed-size view that allows element replacement. `List.of` returns a list that disallows modification through its API, including `set`. The two factories have different contracts.

### Question 2: Is it a contradiction when an unmodifiable list sees new elements added externally to its source?

No. The wrapper blocks modifications through the wrapper path, while reading from the linked backing source. It is not a guarantee of a frozen content snapshot.

### Question 3: Why can `keySet.remove` modify a map while `keySet.add` is rejected?

Removing a key identifies which mapping to remove. Adding a key alone does not provide a complete key/value pair, and the view contract does not support add operations. To add a mapping, use the map API.

### Question 4: Does copying into an `ArrayList` solve deep immutability of elements?

No. It creates a structurally independent and modifiable list structure, but the element references may still be shared. A separate policy is needed for the element objects themselves.

### Practice exercises

1. Add a check verifying that removing through the iterator of an unmodifiable wrapper is rejected after a valid call to `next()`.
2. Create a `subList` from `Arrays.asList` and verify that `set` updates the original array while `add` is rejected.
3. Compare `unmodifiableList(source)` with `unmodifiableList(new ArrayList<>(source))` when the source changes after the result is created.
4. Write a method that returns a sorted list while leaving the input untouched, then test it with `ArrayList`, `List.of`, and `Arrays.asList`.
5. Specify clearly in one of your own APIs: is the caller allowed to mutate the result, is the result a view or a snapshot, and are the elements mutable?

When encountering a UOE, identify the requested operation, the actual object's contract, and the data-modification ownership the program requires. The proper fix stems from those three factors rather than guessing at another factory name or catching the exception blindly.
