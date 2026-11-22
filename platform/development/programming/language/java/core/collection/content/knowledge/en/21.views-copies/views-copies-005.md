# Copying with Constructors, addAll, and putAll

## 1. Before copying, clarify what must be independent

A function receives a list of tasks and wants to sort its own copy to build a report. If it only assigns `List<Task> report = source;` and modifies the list, the source structure is also modified because both variables reference the same object.

Creating a new collection solves sharing the **container structure**, but it does not automatically solve sharing the **element objects**. These are two levels of independence to distinguish before choosing a copying approach.

Three common tools are:

- a constructor that accepts a source, such as `new ArrayList<>(source)` or `new LinkedHashMap<>(source)`;
- `destination.addAll(source)` to add elements to an existing destination collection;
- `destination.putAll(sourceMap)` to put mappings into an existing destination map.

This article explains the semantics, return types, duplicate data, colliding keys, ordering, comparators, mutability, and the limits regarding deep copying and concurrency. All complete examples below are compatible with **Java 17 and later**.

## 2. Reference assignment, structural copying, and element copying

### 2.1. Assignment does not create a new collection

~~~java
List<String> alias = source;
~~~

This is an illustrative snippet inside a method with the appropriate variables and imports. `alias == source` is `true`. Adding or removing through one variable affects the same object that the other variable sees.

There is no "wait until modification and Java will copy it automatically" step. Standard Java collections do not have copy-on-write structural separation behavior like that.

### 2.2. A constructor creates a new container structure

~~~java
List<String> copy = new ArrayList<>(source);
~~~

`copy` is a different list from `source`. Adding or removing elements from one list does not automatically add or remove them in the other.

The `ArrayList(Collection)` constructor creates a list containing the source elements in the order returned by the source's iterator. The destination class is a dynamic array list, supporting standard list operations and `null`. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

However, if the elements are objects, the new list receives references to them. That is a **shallow copy**.

### 2.3. Shallow copying shares element objects

Model:

~~~text
source ----> list S ----+
                        +----> task object T
copy ------> list C ----+

S and C are different.
Element references in S and C both point to T.
~~~

If you change the state of `T`, both lists can observe that state because both point to it. If you replace a slot in `C` with a different object, you change the reference structure of `C`; the corresponding slot in `S` is not automatically changed.

Examples that only use `String` often cause learners to overlook this because strings do not allow in-place content mutation. The main program uses a `Note` class with a mutable field to demonstrate this clearly.

### 2.4. Deep copying is the data model's responsibility

If independent elements are needed, new elements must be created according to the application's rules. For a flat object containing only an immutable string, creating `new Note(old.text)` may suffice.

For objects containing sublists, shared references, or cycles, you must determine how many levels deep to copy and how shared relationships should be preserved. Collection constructors, `addAll`, and `putAll` do not automatically traverse the entire object graph to do that.

Do not use the phrase "independent copy" without answering whether independence applies to the structure or also to element state.

## 3. Copying with constructors: the destination class determines the contract

Common examples:

~~~java
List<E> listCopy = new ArrayList<>(sourceCollection);
Set<E> setCopy = new LinkedHashSet<>(sourceCollection);
Map<K, V> mapCopy = new LinkedHashMap<>(sourceMap);
~~~

These are patterns with type parameters `E`, `K`, `V` declared in context. A constructor accepting a collection or map is a common convention among general-purpose JDK classes; it is not a method on the `Collection` or `Map` interface itself.

Read it as: "create **this destination type** from the source data," not "clone every property of the source as-is."

### 3.1. Changing the collection type can change element count and ordering rules

Source list:

~~~text
[B, A, B, C]
~~~

Different destination choices have different semantics:

| Destination | Result under its contract |
| --- | --- |
| `new ArrayList<>(source)` | Preserves occurrences and iteration order: `[B, A, B, C]` |
| `new LinkedHashSet<>(source)` | Deduplicates by set semantics, preserving first-insertion order: `[B, A, C]` |
| `new TreeSet<>(source)` with natural string order | Deduplicates and sorts: `[A, B, C]` |

`LinkedHashSet` maintains insertion order, and re-adding an already present element does not change its position. [Java 17: LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

A reduced element count when converting a list to a set is not necessarily a copying bug; deduplication may be the exact goal. However, if duplicate entries represent multiple orders, converting to a set loses meaning. Choose according to your domain model.

### 3.2. Capacity constructors do not accept data

Two statements look similar but do different things:

~~~java
new ArrayList<String>(10);
new ArrayList<String>(existingItems);
~~~

The first creates an empty list with an expected initial capacity. `size()` is still 0. It does not create ten `null` elements and does not create any copy.

The second takes a source collection to create a list containing data. Do not use the integer constructor and then call `set(0, value)` when there is no element at index 0 yet.

### 3.3. Source mutability policy does not automatically carry over to the copy

A `List.of("A")` does not allow additions or removals. However, `new ArrayList<>(thatList)` creates a new list with `ArrayList` mutability.

Similarly, an unmodifiable source map can be read to build a modifiable `LinkedHashMap`. This does not unlock mutation on the source; it simply creates a new object with a different contract.

Conversely, collection constructors do not automatically produce an unmodifiable copy. If an API requires a read-only output, choose the appropriate factory or wrapper after determining requirements for `null`, ordering, and lifecycle.

## 4. addAll: add to an existing destination, not replace the whole destination

General signature:

~~~java
boolean addAll(Collection<? extends E> source);
~~~

If it completes, the method has applied adding the source elements according to the destination collection's rules. The returned flag indicates whether the destination collection changed.

**addAll does not clear the destination first.** Example:

~~~text
destination before      [start]
source                  [B, A, B, C]
destination.addAll(source)
destination after       [start, B, A, B, C]
~~~

The `start` element remains. If the goal is a new structure containing only the source, a constructor usually expresses the intent more directly than accidentally adding to a destination that still holds old data.

`Collection.addAll` is an optional operation; the source must not be modified while the operation is in progress under the general contract. The returned flag is `true` when the destination changes. [Java 17: Collection.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#addAll(java.util.Collection)).

### 4.1. On List: preserves occurrences and inserts in sequence

For a standard list that supports addition, `addAll(source)` appends elements to the end in the order of the source iterator.

`List` also has an overload:

~~~java
boolean addAll(int index, Collection<? extends E> source);
~~~

It inserts the group at `index`, shifting subsequent elements. The insertion index can range from `0` to `size()`, inclusive (`size()` appends to the end).

For example, with destination `[start, B, A]`, inserting `[X, Y]` at `1` yields `[start, X, Y, B, A]`. Within the inserted group, `X` remains before `Y`. [Java 17: List.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#addAll(int,java.util.Collection)).

If the source is an unordered set, the destination list only preserves the source order observed during that copy; it does not reconstruct a business order that the source itself did not guarantee.

### 4.2. On Set: does not increase membership for existing elements

With a `LinkedHashSet` currently containing `[B, A, C]`:

~~~text
addAll([B, A])          false, remains [B, A, C]
addAll([C, D])          true, becomes [B, A, C, D]
~~~

A `false` return does not mean "the source was not read" or "the copy failed." It means no membership change occurred from the operation. Existing values do not create duplicates.

Uniqueness is determined by the set contract and implementation. If using custom elements in a hash set, proper `equals`/`hashCode` are required; if using a sorted set, comparison rules also apply. `Set` does not allow duplicate elements by its contract. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 4.3. addAll does not deep-copy and does not transfer ownership

If the source contains `Note` objects, `addAll` puts references to them into the destination. Removing an element from the source afterward does not automatically remove it from the destination, but mutating the shared object itself is visible through both.

The operation also does not "drain" elements from the source. A source retains its data unless you explicitly remove it with a separate action.

### 4.4. Source is a view of the destination: avoid unclear overlapping contracts

The general contract states undefined behavior when the source is modified while `addAll` is running; the case where `source` is the non-empty destination collection itself falls under this warning.

Do not rely on a particular `ArrayList` implementation handling `list.addAll(list)` to write a general-purpose helper. The destination can also overlap with the source through a `subList` or another view.

If you genuinely want to duplicate the current elements, create a structurally independent intermediate collection and then add:

~~~java
List<E> snapshot = new ArrayList<>(items);
items.addAll(snapshot);
~~~

This is a pattern inside a context with type `E`, where source/destination support the operation and there is no concurrent modification. Element data is still shared via shallow copying.

## 5. putAll: merge mappings by key, not synchronize two maps

Signature:

~~~java
void putAll(Map<? extends K, ? extends V> source);
~~~

`Map` is not a `Collection`, so its bulk operation works with key–value mappings. The effect is specified as equivalent to applying `put(k, v)` for each source mapping. It does not return a `boolean` flag or a resulting map. [Java 17: Map.putAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#putAll(java.util.Map)).

### 5.1. Duplicate keys are updated; destination keys absent from source are kept

Suppose:

~~~text
destination           {timeout=5, mode=SAFE, owner=team}
source                {mode=FAST, retries=3}
~~~

After `destination.putAll(source)`:

~~~text
{timeout=5, mode=FAST, owner=team, retries=3}
~~~

`mode` is replaced because the key already existed; `retries` is added; `timeout` and `owner` remain because `putAll` does not remove keys absent from the source.

A clear-intent pattern for combining configuration is:

~~~java
Map<String, String> effective = new LinkedHashMap<>(defaults);
effective.putAll(overrides);
~~~

This is an illustrative snippet inside a method. `defaults` is not structurally modified; `effective` receives the defaults first and then the override layer. Application order matters: reversing the two steps could cause defaults to overwrite user-provided values.

### 5.2. putAll is not business-level accumulation

If two maps both contain `"apples"` with counts `2` and `3`, `putAll` does not automatically sum them to `5`. It applies the destination's `put` rule, which replaces the value for matching keys.

If you need to sum, keep the old value, or detect conflicts and report an error, you must choose a dedicated combining rule, such as a loop using `merge` with an appropriate function. Do not treat every kind of merge as the same "copy" operation.

### 5.3. Null values are data when the destination permits them

Putting the mapping `owner=null` into a `LinkedHashMap` via `putAll` leaves key `owner` present with value `null`. It does not automatically remove that key.

Some external configuration formats may treat `null` as deletion, but that convention requires an application-level processing step. It is not built-in behavior of `Map.putAll`.

### 5.4. Does not create a live link between two maps

After `target.putAll(source)` completes, changing mappings in `source` does not automatically update `target`. The two map structures are independent if they are separate objects without a view relationship.

However, keys and values are copied references. If a value is a list, both maps can point to that same list. Changing a mapping differs from mutating the state of a value object.

### 5.5. Order after putAll is determined by the destination

For an insertion-ordered `LinkedHashMap`, existing keys keep their positions when `put` updates their values; new keys are appended in the order the source mappings are processed. An access-order map has different access rules.

The `LinkedHashMap(Map)` constructor creates an insertion-ordered map for the new instance; it does not automatically copy access-order mode or all policies of the source. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

For sorted maps, order is determined by keys and the comparator, not insertion sequence. Do not guess the printed order of a map that does not guarantee ordering merely from how `putAll` is written.

## 6. Comparators and constructor overloads: same source object, different selection

A copy constructor does not always have just one form. The declared static type of the argument expression participates in compile-time overload resolution.

### 6.1. TreeSet(Collection) and TreeSet(SortedSet)

Suppose the source is a set of integers in descending order:

~~~java
SortedSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
descending.addAll(List.of(3, 1, 2));

Collection<Integer> broad = descending;
TreeSet<Integer> a = new TreeSet<>(descending);
TreeSet<Integer> b = new TreeSet<>(broad);
~~~

This is an illustrative snippet with the corresponding imports.

- `new TreeSet<>(descending)` selects the `SortedSet` constructor, preserving the source's ordering rule: `[3, 2, 1]`.
- `new TreeSet<>(broad)` selects the `Collection` constructor, using natural order: `[1, 2, 3]`.

Both source variables point to the same object, but different overloads are chosen because their static types differ. The `Collection` constructor does not automatically become the `SortedSet` constructor just because the runtime object is a sorted set. [Java 17: TreeSet constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

If you want to build a new set with a specific comparator from a general source, construct the destination with that comparator and then call `addAll`:

~~~java
TreeSet<Integer> copy = new TreeSet<>(Comparator.reverseOrder());
copy.addAll(broad);
~~~

Using a default empty `TreeSet` and calling `addAll` does not automatically learn the source's comparator.

### 6.2. TreeMap(Map) and TreeMap(SortedMap)

`TreeMap` has a similar distinction:

- the `SortedMap` constructor preserves the source's comparison order;
- the `Map` constructor uses the natural order of the keys.

If the keys do not have a suitable natural order, losing the comparator not only changes the sequence but can also cause the constructor to fail. [Java 17: TreeMap constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

The main program uses integers so both approaches run and the difference is clearly visible in key order.

### 6.3. Copying can also change the "duplicate" relation

If the destination compares elements using a different rule than the source, the number of elements or mappings can change according to the destination's equivalence relation.

Do not use a comparator based solely on name length and assume all distinct names will still be preserved. In tree sets/maps, values that compare as `0` may be treated as the same logical slot. To preserve standard set/map contracts, the comparison relation should be consistent with the required equality semantics of the data type.

This is a data modeling choice, not a bug that a copy constructor is responsible for fixing automatically.

## 7. Type rules, null handling, and mutability still apply

### 7.1. Subtypes of source elements can go into a supertype destination

`Collection<? extends E>` allows a source whose elements are a subtype of `E`:

~~~java
List<Integer> source = List.of(1, 2);
List<Number> target = new ArrayList<>();
target.addAll(source);
target.add(3.5);
~~~

This is a snippet runnable inside a method. It does not mean `List<Integer>` becomes a subtype of `List<Number>`. You read `Integer`s from the source and place them into a destination capable of holding `Number`.

`putAll` likewise accepts sources with matching subtype keys and values through its corresponding wildcards. There is no need to use raw types or unsafe casts just to transfer valid data.

### 7.2. The destination decides whether null is accepted

A valid source may contain a `null` element, but the destination does not necessarily accept it. `new ArrayList<>(sourceWithNull)` can succeed, whereas `new ArrayDeque<>(sourceWithNull)` throws `NullPointerException` because `ArrayDeque` forbids `null` elements. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

For maps, `null` key/value policy also depends on the destination type. The fact that "data is already in a valid map" does not prove it is valid for every other map.

Distinguish between a source containing a `null` element and the source reference itself being `null`. Constructors and bulk operations do not treat a `null` source reference as an empty source.

### 7.3. addAll and putAll require destination mutability

Destinations from `List.of` or `Map.of` do not permit modification. Thinking of an operation as a "copy" does not grant permission to mutate that object.

Unmodifiable wrappers also enforce their corresponding restrictions. An unmodifiable source can still be read to build a modifiable destination, but to update in place, the destination itself must support the operation.

Do not use a call with an empty source to probe mutability and assume all subsequent calls will be valid. APIs may reject optional operations even when you believe nothing would change.

## 8. Exceptions and concurrent modification: no automatic "all-or-nothing"

### 8.1. Bulk operations are not general transactions

`addAll` and `putAll` can fail due to type, `null`, comparator, or destination constraints. The general contract does not promise rolling back all changes made before an exception across all implementations.

If you want a data-replacement function that publishes new state only after valid preparation, you can build a separate candidate, validate it, and then swap the reference at the appropriate ownership layer. Do not `clear` the current source before knowing the new data is valid and treat an exception as having no consequences.

Building a candidate does not by itself solve concurrency: state publication, lifetimes of old views, and locking rules must still be designed.

### 8.2. clear then addAll is not equivalent in all reference relationships

Suppose two variables point to the same list. If you call `target.clear()` and then `target.addAll(source)` when `source` is actually `target` or a view backed by it, you may have erased the data you needed to read before starting to add.

When the goal is to replace contents, determine whether source and destination share structure. If the source must be preserved first, copy the appropriate data before clearing. However, if the destination object's identity must be preserved because other code holds references to it, reassigning a variable to a new object also has different semantics from mutating in place.

### 8.3. Copying does not automatically create an atomic snapshot

If the source is modified while a constructor or bulk operation is reading, you must follow the concurrency policy of the source and the tool used. Do not treat the fact that the result is a new object as proof that all elements were captured at the exact same instant.

A `ConcurrentHashMap` supports concurrent access, but aggregate observations and multi-mapping updates do not automatically become a whole-map transaction. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

If the domain requires a consistent snapshot across multiple fields or mappings, you need an appropriate mechanism covering the read, or an explicit immutable/versioned data model. Do not rely on the presence or absence of fail-fast exceptions to prove consistency.

## 9. Complete program

Save all the code below into **`BulkCopyDemo.java`**. The example uses a single thread and sources with deterministic ordering so stdout can be verified precisely.

The `Note` class intentionally has a mutable field to show shared references. Explicit element copying in the example only needs to copy an immutable string; do not treat that approach as a general deep-copy algorithm for arbitrary object graphs.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class BulkCopyDemo {
    static final class Note {
        String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public String toString() {
            return text;
        }
    }

    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | NullPointerException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("B", "A", "B"));
        List<String> alias = source;
        List<String> copied = new ArrayList<>(source);
        System.out.println("alias same list: " + (alias == source));
        System.out.println("constructor same list: " + (copied == source));
        source.add("C");
        System.out.println("source after add: " + source);
        System.out.println("constructor list stays: " + copied);

        List<String> merged = new ArrayList<>(List.of("start"));
        boolean changed = merged.addAll(source);
        System.out.println("list addAll: " + changed + ", result=" + merged);
        merged.addAll(1, List.of("X", "Y"));
        System.out.println("indexed addAll: " + merged);
        System.out.println("empty addAll: " + merged.addAll(List.of()));
        ArrayList<String> reserved = new ArrayList<>(10);
        System.out.println("capacity constructor size: " + reserved.size());

        LinkedHashSet<String> unique = new LinkedHashSet<>(source);
        System.out.println("set constructor: " + unique);
        System.out.println("set addAll existing: " + unique.addAll(List.of("B", "A")));
        changed = unique.addAll(List.of("C", "D"));
        System.out.println("set addAll new: " + changed + ", result=" + unique);

        Note shared = new Note("draft");
        List<Note> notes = new ArrayList<>(List.of(shared));
        List<Note> constructorNotes = new ArrayList<>(notes);
        List<Note> bulkNotes = new ArrayList<>();
        bulkNotes.addAll(notes);
        shared.text = "reviewed";
        System.out.println("shared element in both copies: "
                + (notes.get(0) == constructorNotes.get(0)
                && notes.get(0) == bulkNotes.get(0)));
        System.out.println("after element edit: " + notes + " / "
                + constructorNotes + " / " + bulkNotes);
        notes.add(new Note("extra"));
        System.out.println("independent list sizes: "
                + notes.size() + " / " + constructorNotes.size());

        List<Note> independentNotes = new ArrayList<>();
        for (Note note : notes) {
            independentNotes.add(new Note(note.text));
        }
        notes.get(0).text = "final";
        System.out.println("shallow after second edit: " + constructorNotes);
        System.out.println("explicit element copies: " + independentNotes);

        Map<String, String> defaults = new LinkedHashMap<>();
        defaults.put("timeout", "5");
        defaults.put("mode", "SAFE");
        defaults.put("owner", "team");
        Map<String, String> overrides = new LinkedHashMap<>();
        overrides.put("mode", "FAST");
        overrides.put("retries", "3");
        Map<String, String> combined = new LinkedHashMap<>(defaults);
        combined.putAll(overrides);
        System.out.println("map constructor plus putAll: " + combined);
        System.out.println("defaults unchanged: " + defaults);
        overrides.put("mode", "LATER");
        System.out.println("combined mode stays: " + combined.get("mode"));

        Map<String, String> nullOverride = new LinkedHashMap<>();
        nullOverride.put("owner", null);
        combined.putAll(nullOverride);
        System.out.println("null is a value, not deletion: " + combined);

        Map<String, List<String>> groups = new LinkedHashMap<>();
        groups.put("alpha", new ArrayList<>(List.of("one")));
        Map<String, List<String>> groupCopy = new LinkedHashMap<>(groups);
        groupCopy.get("alpha").add("two");
        groupCopy.put("beta", new ArrayList<>(List.of("x")));
        System.out.println("map shared value: " + groups);
        System.out.println("map structures independent: "
                + groups.keySet() + " / " + groupCopy.keySet());

        SortedSet<Integer> descending = new TreeSet<>(Comparator.reverseOrder());
        descending.addAll(List.of(3, 1, 2));
        Collection<Integer> broadCollection = descending;
        TreeSet<Integer> keepSetOrder = new TreeSet<>(descending);
        TreeSet<Integer> naturalSetOrder = new TreeSet<>(broadCollection);
        System.out.println("SortedSet constructor: " + keepSetOrder);
        System.out.println("Collection constructor: " + naturalSetOrder);

        SortedMap<Integer, String> descendingMap =
                new TreeMap<>(Comparator.reverseOrder());
        descendingMap.put(3, "c");
        descendingMap.put(1, "a");
        descendingMap.put(2, "b");
        Map<Integer, String> broadMap = descendingMap;
        TreeMap<Integer, String> keepMapOrder = new TreeMap<>(descendingMap);
        TreeMap<Integer, String> naturalMapOrder = new TreeMap<>(broadMap);
        System.out.println("SortedMap constructor keys: " + keepMapOrder.keySet());
        System.out.println("Map constructor keys: " + naturalMapOrder.keySet());

        List<String> nullable = Arrays.asList("ok", null);
        System.out.println("ArrayList accepts copied null: " + new ArrayList<>(nullable));
        System.out.println("ArrayDeque rejects copied null: "
                + failure(() -> new ArrayDeque<>(nullable)));

        List<String> readOnlyList = List.of("A");
        System.out.println("read-only list addAll: "
                + failure(() -> readOnlyList.addAll(List.of("B"))));
        List<String> writableList = new ArrayList<>(readOnlyList);
        writableList.add("B");
        System.out.println("new mutable list from read-only source: " + writableList);

        Map<String, Integer> readOnlyMap = Map.of("A", 1);
        System.out.println("read-only map putAll: "
                + failure(() -> readOnlyMap.putAll(Map.of("B", 2))));
        Map<String, Integer> writableMap = new LinkedHashMap<>(readOnlyMap);
        writableMap.put("B", 2);
        System.out.println("new mutable map from read-only source: " + writableMap);

        List<Number> numbers = new ArrayList<>();
        numbers.addAll(List.of(1, 2));
        numbers.add(3.5);
        System.out.println("subtype source: " + numbers);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 BulkCopyDemo.java
java BulkCopyDemo
~~~

Use JDK 17 or later to compile at release level 17 and a Java 17 or later runtime to execute. The example was compiled at release level 17 and ran successfully on OpenJDK 24.0.2.

Exact stdout:

~~~text
alias same list: true
constructor same list: false
source after add: [B, A, B, C]
constructor list stays: [B, A, B]
list addAll: true, result=[start, B, A, B, C]
indexed addAll: [start, X, Y, B, A, B, C]
empty addAll: false
capacity constructor size: 0
set constructor: [B, A, C]
set addAll existing: false
set addAll new: true, result=[B, A, C, D]
shared element in both copies: true
after element edit: [reviewed] / [reviewed] / [reviewed]
independent list sizes: 2 / 1
shallow after second edit: [final]
explicit element copies: [reviewed, extra]
map constructor plus putAll: {timeout=5, mode=FAST, owner=team, retries=3}
defaults unchanged: {timeout=5, mode=SAFE, owner=team}
combined mode stays: FAST
null is a value, not deletion: {timeout=5, mode=FAST, owner=null, retries=3}
map shared value: {alpha=[one, two]}
map structures independent: [alpha] / [alpha, beta]
SortedSet constructor: [3, 2, 1]
Collection constructor: [1, 2, 3]
SortedMap constructor keys: [3, 2, 1]
Map constructor keys: [1, 2, 3]
ArrayList accepts copied null: [ok, null]
ArrayDeque rejects copied null: NullPointerException
read-only list addAll: UnsupportedOperationException
new mutable list from read-only source: [A, B]
read-only map putAll: UnsupportedOperationException
new mutable map from read-only source: {A=1, B=2}
subtype source: [1, 2, 3.5]
~~~

### 9.1. Lists and sets

The first lines distinguish an alias from a new structure. Adding `C` to the source does not increase the size of the constructor copy. Calling `addAll` on the list containing `start` keeps the old element and appends the source; the indexed overload inserts the entire group at the desired position.

The destination set deduplicates. `addAll` with only existing members returns `false`; adding a new `D` returns `true`.

### 9.2. Mutable Note objects and map values

Both copied lists receive references to the same `Note`, so they observe the `reviewed` and `final` edits. However, adding a new note to the source does not automatically grow the copy's structure.

The loop creating new notes produces independent objects for this simple model. That copy keeps `reviewed` after the source changes to `final`.

A map with list values demonstrates the same principle: modifying the `alpha` list is visible through the source, whereas adding key `beta` to the copy does not automatically add that key to the source.

### 9.3. putAll and configuration overrides

The combined map receives defaults first, then updates `mode` and adds `retries`. `owner` does not disappear because it is absent from the override map.

Changing `overrides` after the operation completes does not update the combined map. Putting `owner=null` into the combined map keeps the key and only changes its value.

### 9.4. Comparators and destination constraints

The two constructor pairs produce descending or ascending results solely because of different overloads, even though the runtime source is the same descending-sorted object.

The final lines distinguish `null` policies and destination mutability. A new `ArrayList`/`LinkedHashMap` created from an unmodifiable source has mutability according to the chosen destination class.

## 10. Similar-looking tools with different meanings

### 10.1. Views are not copy constructors

`subList`, `keySet`, or view wrappers can stay backed by the source. `new ArrayList<>(view)` creates a new list structure containing data read from the view; it does not turn the copy into a component that continues automatic write-through.

Be especially cautious with `Map.Entry` elements: copying a collection containing entries does not by itself prove each entry is independent of the source. When you need stable pairs, copy each pair or build a new map for the purpose. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

### 10.2. Collections.copy is not addAll

`Collections.copy(destination, source)` overwrites existing positions in the destination list; the destination must have sufficient **size**, not just capacity. It is not a way to create a new collection or append elements. [Java 17: Collections.copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)).

Therefore, `new ArrayList<>(10)` is not sufficient as a destination for copying ten elements with this tool if the list is still empty. For creating a modifiable copy, a collection-accepting constructor is usually the direct choice.

### 10.3. List.copyOf and Map.copyOf have different goals

The `copyOf` factories produce unmodifiable results under their contracts and impose restrictions such as rejecting `null`. They are not another name for modifiable destination constructors.

Do not infer ordering guarantees for all map factories or assume "unmodifiable" means deeply immutable elements. Determine the goal first: does the new result need to be modifiable, preserve order/comparator, allow `null`, or share elements?

## 11. Choosing a copying approach by requirement

| Requirement | Usually appropriate approach | What to check |
| --- | --- | --- |
| Create a modifiable list from source data | `new ArrayList<>(source)` | Source order, shared elements |
| Append data to an existing list | `target.addAll(source)` | Old data is kept, add permission |
| Insert a group at a position | `target.addAll(index, source)` | Index, group order, shift cost |
| Deduplicate while keeping first source occurrence | `new LinkedHashSet<>(source)` | Equality/hashing and meaning of duplicates |
| Create a map with its own structure | `new LinkedHashMap<>(source)` | Iteration order, shared keys/values |
| Apply an override layer to an existing map | `target.putAll(overrides)` | Duplicate keys replaced, other keys not deleted |
| Preserve a sorted source's comparator | Constructor/destination configured with the right comparator | Overload selected by static type |
| Keep element state independent | Copy elements per the data model | Depth, shared references, cycles |
| Publish replacement state after preparation | Build candidate, validate, publish per ownership policy | Concurrency, partial failure, old views/aliases |

Performance also depends on the destination type. Creating a shallow copy of *n* references still requires working through the source data; it is not free just because it is not a deep copy. For array lists, reasonable pre-sizing or bulk addition can reduce some resizing/shifting overhead, but you should not assume every constructor is always faster than every form of `addAll`. Measure real cases when performance matters.

## 12. Common mistakes

1. **Assigning a variable and calling it a copy:** both variables still share the same structure.
2. **Assuming a new collection means new elements:** standard constructors and bulk operations copy references.
3. **Thinking addAll replaces old data:** it adds according to the destination contract without clearing first.
4. **Thinking putAll makes the destination identical to the source:** keys present only in the destination remain.
5. **Assuming duplicate keys are summed or merged automatically:** `putAll` uses `put` semantics, not custom addition.
6. **Assuming an unmodifiable source produces an unmodifiable copy:** the destination class/factory determines that contract.
7. **Confusing capacity with size:** integer constructors do not create elements.
8. **Assuming the comparator always travels with the data:** overload selection or destination configuration determines it.
9. **Assuming valid nulls in the source are accepted by every destination:** destination policies may differ.
10. **Treating bulk operations as transactions:** there is no automatic rollback or atomic snapshot.
11. **Assuming self-copy or overlapping view sources are always safe:** follow the contract; separate the data when needed.
12. **Assuming a copy preserves every mode of the source class:** the destination type can change ordering, uniqueness, comparator, and access policy.

## 13. Practice with answers

### Exercise 1 — Distinguishing an alias from a new list

`a` is an `ArrayList` containing `[A, B]`. Set `b = a` and `c = new ArrayList<>(a)`. After `b.add("C")`, what are the three lists?

**Answer:** `a` and `b` are both `[A, B, C]` because they share the same object. `c` remains `[A, B]` structurally. If elements are objects with mutable state, `c` can still share those objects.

### Exercise 2 — Does addAll clear existing elements?

The destination is `[old]`, and the source is `[X, X]`. After `ArrayList.addAll(source)` and after `LinkedHashSet.addAll(source)` on two separate destinations each initially containing `old`, what is the difference?

**Answer:** the list becomes `[old, X, X]`; the linked set becomes `[old, X]`. Both keep `old`. Duplicate elements are handled according to the destination type's contract, not a universal copy rule that forces preserving the count.

### Exercise 3 — Duplicate keys and destination-only keys

Destination `{A=1, B=2}`, source `{B=20, C=3}`. After `putAll`, is `A` lost? What is `B`?

**Answer:** `A` still has value `1`, `B` becomes `20`, and `C` is added with `3`. This applies the source mappings, not a synchronization operation that removes all keys outside the source. Print order depends on the specific source/destination.

### Exercise 4 — Copying a list of objects

You create `copy = new ArrayList<>(notes)` and then modify `notes.get(0).text`. Why does `copy` see the change even though `copy != notes`?

**Answer:** the two lists have different structures but hold references to the same `Note` object. You must create a new `Note` if independence of that state is required. Copy depth must follow the data model rather than assuming every nested field is independent.

### Exercise 5 — Sorted set constructors

A `SortedSet<Integer>` using a descending comparator is also assigned to a `Collection<Integer> broad` variable. Why can `new TreeSet<>(sorted)` and `new TreeSet<>(broad)` produce different orders?

**Answer:** static type selects the overload. The `SortedSet` form preserves the source's comparison order; the `Collection` form uses natural order. To get a specific comparator from a general source, construct the destination with that comparator and then add the data.

### Exercise 6 — Capacity vs. data

A developer creates `new ArrayList<String>(100)` and assumes the list has 100 slots for calling `set` or `Collections.copy`. What is wrong?

**Answer:** the number is the initial capacity, while `size` is still 0. Actual elements must exist if an operation requires existing positions. If you need a copy of source data, use a collection-accepting constructor or `addAll` as appropriate.

### Exercise 7 — Overwriting with null

A map allows `null` and has `mode=SAFE`. The source contains `mode=null`. Does `putAll` remove the `mode` key?

**Answer:** no; the mapping remains present with value `null`. If the domain specifies `null` as a deletion signal, a separate algorithm is needed to handle that convention. Do not confuse external data rules with standard map semantics.

### Exercise 8 — Failures and overlapping sources

A function does `target.clear(); target.addAll(source);` to replace data. What issues should be checked before considering this a safe replacement?

**Answer:** whether the source is the same object or a view backed by the destination; whether the destination supports removal/addition; whether the data satisfies type, `null`, comparator, or capacity/size constraints; whether the operation can fail partway through; whether concurrent modification can occur; and whether other aliases/views should see the same object or a new state. There is no automatic rollback. You may need to build a candidate first and publish it under the appropriate ownership policy.

When practicing on your own, write down four lines for each copy operation: whether the container object is new or existing, whether elements/keys/values share references, what the destination's data rules are, and how the operation affects data already in the destination. Those four answers define the behavior far more accurately than just seeing the word "copy" in a name.
