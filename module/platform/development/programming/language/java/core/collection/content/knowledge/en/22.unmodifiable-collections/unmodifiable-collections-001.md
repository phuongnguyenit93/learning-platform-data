# Distinguishing Unmodifiable, Fixed-Size, and Deeply Immutable Collections

A list can reject `add` while still allowing `set`. A list that rejects `add`, `remove`, and `set` can still show new elements after its source is modified. Even when a list is detached from its source, an object retrieved via `get` can still be mutated.

Those three situations live at three different layers: container mutation rights, linkage to external data, and element state. Understanding each layer accurately helps you design return values, configurations, and data snapshots with clear contracts.

This article uses Java 17 as the minimum API baseline. You should be familiar with `List`, `ArrayList`, object references, and exceptions before running the experiments. `Map` is used in a short example to show that the same analysis applies to both keys and values.

## 1. Start from What the Data Consumer Is Allowed to Do

Suppose a service returns a list of items. Saying “read-only” leaves out critical details. May the caller reorder the list? May they replace the item at index 0? If the service later adds an item, should the returned list reflect it? May the caller change the quantity of the item itself?

Consider four separate questions:

1. **Changing the number of elements:** can elements be added, removed, or cleared from the container?
2. **Changing elements or positions:** can `list[i]` be replaced with another reference, reordered, or can a map's mappings be changed?
3. **Observing source changes:** is the result a live view, or does it hold its own membership?
4. **Mutating inner objects:** do elements, keys, values, or nested objects beneath them expose state-mutating methods?

Do not collapse all of these into a single question: “is it mutable?” The same `List<E>` type can have different answers to all four questions. The declared type `List<E>` does not express these guarantees; callers must know the contract of the factory or method returning the result.

Also separate **observing a change** from **calling a mutating method directly**. When a view's source is updated, the holder of the view can observe new data even though they have no right to mutate through the view.

## 2. Three Concepts and a Comparison Table

### Fixed-Size

A fixed-size list does not allow increasing or decreasing the number of element slots. This alone does not determine whether the reference stored in a slot can be replaced.

`Arrays.asList(array)` is the classic example: the list is backed by the passed-in array, supports replacing elements, and reflects changes bidirectionally with the array. Size-changing operations such as `add` or `remove` are rejected. Thus, “fixed-size” describes the size, not the full mutation rights. [Arrays.asList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### Unmodifiable via the Collection API

An unmodifiable collection rejects container-mutating methods according to its contract. For a list, those operations include adding, removing, and replacing elements. Mutating the contents of an object returned by `get` is a separate call outside container modification.

The `Collection` specification also distinguishes between an unmodifiable collection and an unmodifiable view. A view can observe changes in its source; elements can have their own mutable state. Therefore, the label “unmodifiable” alone does not prove deep immutability. [Collection definition, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

### Deep Immutability

In this article, **deep immutability** means that once a value is constructed, its observable data state and the state of the objects composing that value cannot be mutated through shared references.

For a `List<List<String>>`, protecting the outer list is not enough: the inner lists must also have stable state. For a `List<Order>`, you must also examine what `Order` holds. If `Order` contains a list of line items, each line item may hold other objects. The proof scope follows the data model, not a single call to `copyOf`.

Cloning every object is not strictly required to achieve deep immutability. Values that are already immutable, such as strings, can be shared safely. What must be eliminated is any shared mutable state path that could alter the protected value.

| Typical construction | Add/remove via list | Replace element with `set` | Do source structural changes appear in the result? | Automatically guarantees deeply immutable elements? |
| --- | --- | --- | --- | --- |
| `new ArrayList<>(source)` | Yes | Yes | Not linked to source structure | No |
| `Arrays.asList(array)` | Cannot change size | Yes | Yes, shares the array slots | No |
| `Collections.unmodifiableList(source)` | No | No | Yes, if the source changes | No |
| `List.copyOf(source)` | No | No | Does not reflect subsequent membership changes in the source | No |
| `List.of(a, b)` | No | No | No source container to track | No |
| Unmodifiable outer list whose elements are fully protected immutable values | No | No | No exposed mutation path for published data | Yes, by that model's contract |

“Not linked to source structure” does not mean every inner object is distinct. For example, `new ArrayList<>(source)` can still hold the same references to each `Order`. The table distinguishes the container from the inner data; it does not claim a deep copy.

Rows can also share multiple properties at once. An unmodifiable list naturally prevents the caller from resizing it; that does not make `Arrays.asList` unmodifiable, because the list returned by `Arrays.asList` still supports `set`.

## 3. Why Can a Fixed-Size List Still Be Modified?

An array has a fixed number of elements, but each array slot can be assigned a different value. When a list provides access to those slots, replacing an element does not require adding or removing slots.

The following snippet is **illustrative code inside a method**, not a standalone program file:

~~~java
String[] names = {"Lan", "Minh"};
List<String> fixed = Arrays.asList(names);

fixed.set(0, "An");   // Replace the reference at index 0.
names[1] = "Binh";    // Modify the same element storage via the array.
~~~

`fixed.size()` remains 2. After both assignments, both the array and the list represent the two names `An` and `Binh`. No element-adding operation occurs.

Sorting can also simply reorder values within existing slots. A list does not need to grow or shrink to be sorted. The program in the demonstration section sorts a list created by `Arrays.asList` and prints the backing array.

This explains a common mistake: receiving an `Arrays.asList` result and calling `add` because the variable has type `List`. An interface declaring a method does not mean every implementing object supports that operation. Several mutating operations in the Collections Framework are optional.

If you need a list that can add and remove elements independently of the array, create a container with the appropriate contract:

~~~java
List<String> editable = new ArrayList<>(Arrays.asList(names));
editable.add("Chi");
~~~

This is still only a list-level copy. With `String`, sharing elements creates no path to mutate string contents; with mutable domain objects, further analysis is needed.

Do not assume that all lists of the same size have the same mutation rights. `List.of("Lan", "Minh")` also has two elements, yet rejects `set` as well. Current size, element-replacement rights, and resizing rights are distinct properties.

One detail when taking array input: `Arrays.asList` expects reference-type elements. If you pass an `int[]` directly, the result is typically a list containing **a single `int[]` array object**, not a list of `Integer` values. That further underscores the need to identify which object is actually the “element” before discussing copying and immutability.

## 4. Read-Only Views and Membership Snapshots Serve Different Purposes

### Unmodifiable View: The Source Owner Can Still Update

`Collections.unmodifiableList(source)` returns a read-through view backed by the source list. Callers cannot mutate via the view or its iterator. The source owner can still mutate the source, and the view sees those changes. [Collections.unmodifiableList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

This makes sense in a task-schedule manager: external callers can read the current schedule while the manager updates the source through controlled methods. The contract is “read the current state,” not “preserve the schedule as of the call time.”

Illustrative code:

~~~java
List<String> source = new ArrayList<>(List.of("queued"));
List<String> live = Collections.unmodifiableList(source);

source.add("running");
// live now represents [queued, running].
~~~

If a method's documentation only states “returns an unmodifiable list,” callers cannot assume that storing that list in a report will preserve historical state. You must explicitly document that it is a live view backed by the source.

Wrapping also does not transfer ownership. If a constructor stores a caller-supplied list directly and wraps it, the caller still retains a mutation path to the source. Rejecting `result.add(...)` does not eliminate `input.add(...)`.

### Membership Snapshot: Detached at the Outer Layer

`List.copyOf(source)` creates an unmodifiable result that preserves the input iteration order and does not reflect subsequent membership changes in the source collection. It rejects `null` elements. The API allows reusing a suitable list as an optimization; do not use `==` or assume “always allocates a new object” to test independence. [List.copyOf API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Here, “membership snapshot” refers to which references are present, their count, and their order in the list. There is no promise that the full state of each object is cloned.

~~~java
List<String> source = new ArrayList<>(List.of("queued"));
List<String> saved = List.copyOf(source);

source.add("running");
// saved still represents [queued].
~~~

With `String` elements, this is usually sufficient for a stable list value. With `MutableTask` elements, adding a new task to the source will not lengthen the saved list, but mutating a task referenced by both lists can still show up in both.

You can achieve similar outer-layer independence by wrapping a private copy:

~~~java
List<String> saved =
        Collections.unmodifiableList(new ArrayList<>(source));
~~~

You must ensure the inner `ArrayList` is never exposed. This approach also has a different `null` contract; it is not identical to `List.copyOf`. Choose based on API requirements rather than swapping one line for something “more modern.”

### A View Can Be Stable If the Source Has No Remaining Mutation Path

A read-only view does not guarantee immutability by itself, nor does it guarantee that the data will change. If the source is kept strictly private and is never mutated after publication, the view can have stable state.

That stability comes from **ownership discipline**, not from any freezing capability of the wrapper. If a future maintainer adds a source mutation path, the stability guarantee can break even though the `unmodifiableList` line remains untouched.

To keep an API maintainable, choose one intent clearly: expose current updatable state, or publish a finalized value. Both the method name and documentation should reflect that intent.

## 5. An Unmodifiable Container Is Different from Unmodifiable Elements

Consider an item with a `quantity` field and a `tags` list:

~~~text
outer list
  └── reference to item
        ├── quantity
        └── reference to tag list
              └── String elements
~~~

If the outer list is unmodifiable, the caller cannot remove the item from the list or replace it with another object. However, `item.setQuantity(7)` targets the item object. It does not call `list.set` and needs no permission to mutate the outer list.

Similarly, `item.getTags().add("sale")` mutates the tag list. There are at least two layers to analyze before reaching the strings.

This snippet highlights the seam between layers:

~~~java
List<StringBuilder> messages =
        List.of(new StringBuilder("draft"));

messages.get(0).append("-edited");
~~~

The list still has one element, the same reference, and the same index. The `StringBuilder` object changes its contents. The statement “the list is unmodifiable” remains true; the statement “the entire value cannot change” is false.

You cannot fix this by wrapping the outer list a second time. A second wrapper does not turn a `StringBuilder` into an immutable string. You must transform elements into an appropriate representation, or copy and protect them under an explicit contract.

An intentional transformation captures each `StringBuilder`'s contents as a `String` at snapshot time:

~~~java
List<String> savedMessages = messages.stream()
        .map(StringBuilder::toString)
        .toList();
~~~

This is a data-model transformation, not an automatic deep-copy feature of `toList`. `map` decides what gets captured; `toList` merely collects the results into an unmodifiable list.

In Java 17, `Stream.toList()` has been available since Java 16. Its result is unmodifiable, though no specific implementation class is guaranteed. [Stream.toList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

When elements hold live resources, locks, threads, or cyclic object graphs, “copy the entire graph” is often no longer a sensible requirement. Identify the business value to preserve—such as item code, quantity, and tags—and build a stable representation for that value.

## 6. Protecting Nested Data According to the Concrete Model

### Two-Level List Containing Strings

Suppose the input has type `List<List<String>>`. `List.copyOf(input)` only isolates the references to the inner lists. Each inner list remains an independent object that can still be mutated by whoever holds it.

If the contract requires freezing the string groups, you can snapshot each inner list first, then snapshot the outer list:

~~~java
List<List<String>> groups = input.stream()
        .map(group -> List.copyOf(group))
        .toList();
~~~

This is illustrative code using an existing `input` variable. It assumes the source is not mutated while being read and that inner lists and elements satisfy `List.copyOf`'s non-`null` policy.

Because the leaf type here is `String`, there is no normal path to mutate string contents. Each resulting inner list is unmodifiable, the resulting outer list is unmodifiable, and the source lists no longer control their membership. For this two-level model, the immutability argument reaches the leaves.

If `String` is replaced with `MutableItem`, the same snippet is no longer enough. It freezes the list layers while still sharing the items. Do not name a generic helper `deepCopy` and use it for arbitrary element types when it only handles two list layers.

### Elements as Business Data

Instead of trying to turn an updatable domain object into an immutable one, you can define a type dedicated to finalized data:

~~~java
record ItemSnapshot(
        String code,
        int quantity,
        List<String> tags
) {
    ItemSnapshot {
        Objects.requireNonNull(code);
        tags = List.copyOf(tags);
    }
}
~~~

The code above is an illustrative type declaration; it requires `import java.util.List` and `import java.util.Objects`. The complete program below includes this declaration and its usage.

The reasoning for this model proceeds in steps:

- `quantity` is a primitive value, not a reference to an externally mutable quantity cell.
- `code` is a `String` and is required to be non-`null`.
- `tags` is stored as an unmodifiable list, detached from the input list's membership.
- Each tag is a `String`. No shared mutable tag object remains.
- No method is added that exposes a hidden mutable source behind these fields.

The constructor is the data-ingestion boundary. If you only provide read-only accessors while the constructor stores the caller's list directly, the creator can still mutate through the old list.

Guidance on designing immutable objects emphasizes controlling references to mutable data on both input and output. Defensive copying must serve the specific data model. [Oracle's Immutable Objects Strategy](https://docs.oracle.com/javase/tutorial/essential/concurrency/imstrat.html).

In this model, you do not need to return a fresh copy of `tags` on every accessor call: the list itself is already locked down and the leaves are strings. With a `byte[]` field, the situation differs: an array always has assignable slots, so you must copy on both input and output, or use a representation with an appropriate contract.

### Deep Copy and Deep Immutability Are Not Synonyms

If you copy an item into a new object that still has public setters, the caller can still mutate the copy. That may be an independent editable copy—very useful for a form—but it is not a deeply immutable value.

Conversely, a deeply immutable structure can share many already-immutable parts. A frozen list of `ItemSnapshot` values does not need to recreate every string. The key guarantee is that data changes cannot propagate through a shared mutable part.

So state precisely what you need: “a copy for the caller to edit privately” or “a value that cannot change after publication.” Those two goals lead to different designs.

## 7. How Far Do `final` and `record` Protect You?

### `final` Locks the Reference Variable

~~~java
final List<String> labels = new ArrayList<>();
labels.add("new");
~~~

This snippet is valid. `final` prevents reassigning `labels` to another list after initialization; it does not revoke the `add` capability of the referenced `ArrayList`.

The same applies to `final String[]`: the variable always holds the same array, but each slot can still be reassigned. This is a language rule about variables, not an object freezer. [JLS 17, Section 4.12.4 on final variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4).

Do not treat seeing several `private final` fields as sole proof of deep immutability. You must still check what objects those fields point to and all access paths to them.

### `record` Does Not Automatically Copy Components

~~~java
record Tags(List<String> values) {
}
~~~

A `record` like this accepts and stores the component's reference value. If external code retains the input list, it can still mutate that list. The default accessor also returns the component's reference, so callers can invoke `values().add(...)` if the underlying list supports it.

The `Record` API describes records as shallowly immutable data carriers; constructors and accessors may need to be declared explicitly for input validation or defensive copying. [Record API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

The `ItemSnapshot` model handled this with a compact constructor. Writing `tags = List.copyOf(tags)` reassigns the parameter used to initialize the field. Even so, the deep guarantee comes from both the `String` leaf type and locking down the list; `record` syntax alone does not provide it.

A record holding a list of mutable elements can change its `equals` or `hashCode` result as component state changes. Never use such a value as a map key or set element and then mutate data involved in equality comparisons. The name “record” does not remove the responsibility to control state.

## 8. Runnable Demonstration: Checking Every Mutation Path

Save all of the code below into **`CollectionProtectionDemo.java`**. The program uses Java 17-compatible APIs and syntax with no external libraries.

`MutableItem` intentionally retains the input tag list to create a shared-data scenario. It serves as the experimental model. `ItemSnapshot` is the protected representation of the same selected information.

The `rejected` helper treats an operation as blocked only when it receives `UnsupportedOperationException`. If the operation unexpectedly succeeds, the program aborts with `AssertionError`. Similarly, `rejectsNull` checks specifically for `NullPointerException`. The program does not rely on exception messages, internal implementation class names, or map iteration order.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionProtectionDemo {
    static final class MutableItem {
        private final String code;
        private int quantity;
        private final List<String> tags;

        MutableItem(String code, int quantity, List<String> tags) {
            this.code = Objects.requireNonNull(code);
            this.quantity = quantity;
            this.tags = Objects.requireNonNull(tags);
        }

        ItemSnapshot snapshot() {
            return new ItemSnapshot(code, quantity, tags);
        }

        @Override
        public String toString() {
            return code + ":" + quantity + ":" + tags;
        }
    }

    record ItemSnapshot(String code, int quantity, List<String> tags) {
        ItemSnapshot {
            Objects.requireNonNull(code);
            tags = List.copyOf(tags);
        }
    }

    record PlainTags(List<String> values) {
    }

    record SafeTags(List<String> values) {
        SafeTags {
            values = List.copyOf(values);
        }
    }

    private static void rejected(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    private static void rejectsNull(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (NullPointerException ex) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        String[] words = {"pear", "apple"};
        List<String> fixed = Arrays.asList(words);
        fixed.set(0, "plum");
        System.out.println("array.afterSet=" + Arrays.toString(words));
        words[1] = "apricot";
        System.out.println("fixed.afterArrayEdit=" + fixed);
        Collections.sort(fixed);
        System.out.println("array.afterSort=" + Arrays.toString(words));
        rejected("fixed.add", () -> fixed.add("orange"));
        rejected("fixed.remove", () -> fixed.remove(0));

        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> live = Collections.unmodifiableList(source);
        List<String> detached = List.copyOf(source);
        source.set(0, "A2");
        source.add("C");
        System.out.println("live=" + live);
        System.out.println("detached=" + detached);
        rejected("live.set", () -> live.set(0, "X"));
        Iterator<String> iterator = live.iterator();
        iterator.next();
        rejected("live.iterator.remove", iterator::remove);

        List<String> itemTags = new ArrayList<>(List.of("school"));
        MutableItem item = new MutableItem("pen", 2, itemTags);
        List<MutableItem> outer = List.of(item);
        List<ItemSnapshot> snapshots = outer.stream()
                .map(MutableItem::snapshot)
                .toList();
        item.quantity = 7;
        itemTags.add("sale");
        System.out.println("outer.afterItemEdit=" + outer);
        System.out.println("snapshot=" + snapshots);
        rejected("outer.set", () -> outer.set(0, item));
        rejected("snapshot.tags.add",
                () -> snapshots.get(0).tags().add("extra"));

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> nested = new ArrayList<>();
        nested.add(inner);
        List<List<String>> shallow = List.copyOf(nested);
        List<List<String>> deepForStrings = nested.stream()
                .map(xs -> List.copyOf(xs))
                .toList();
        inner.add("y");
        nested.add(List.of("new"));
        System.out.println("nested.source=" + nested);
        System.out.println("nested.shallow=" + shallow);
        System.out.println("nested.deep=" + deepForStrings);
        rejected("nested.deep.inner.add",
                () -> deepForStrings.get(0).add("z"));

        List<String> incoming = new ArrayList<>(List.of("base"));
        PlainTags plain = new PlainTags(incoming);
        SafeTags safe = new SafeTags(incoming);
        incoming.add("later");
        System.out.println("record.plain=" + plain.values());
        System.out.println("record.safe=" + safe.values());
        rejected("record.safe.accessor.add", () -> safe.values().add("x"));

        final List<String> finalReference = new ArrayList<>();
        finalReference.add("still mutable");
        System.out.println("final.reference=" + finalReference);

        Map<String, List<String>> map =
                Map.of("items", new ArrayList<>(List.of("one")));
        map.get("items").add("two");
        System.out.println("map.value=" + map.get("items"));
        rejected("map.put", () -> map.put("items", List.of("other")));

        List<String> withNull = Arrays.asList("ok", null);
        System.out.println("fixed.null=" + withNull);
        rejectsNull("copyOf.null", () -> List.copyOf(withNull));
        rejectsNull("of.null", () -> List.of("ok", (String) null));

        List<String> streamList = Stream.of("s", "t").toList();
        rejected("stream.set", () -> streamList.set(0, "S"));
        ArrayList<String> editable = Stream.of("s", "t")
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("u");
        System.out.println("stream.editable=" + editable);
    }
}
~~~

Compile and run from the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 CollectionProtectionDemo.java
java CollectionProtectionDemo
~~~

Use JDK 17 or later to compile. The `--release 17` option restricts language features and APIs to Java 17; it does not turn the running JDK into JDK 17. The example was compiled with that option and run on OpenJDK 24.0.2, exiting cleanly with the following exact stdout:

~~~text
array.afterSet=[plum, apple]
fixed.afterArrayEdit=[plum, apricot]
array.afterSort=[apricot, plum]
fixed.add=UnsupportedOperationException
fixed.remove=UnsupportedOperationException
live=[A2, B, C]
detached=[A, B]
live.set=UnsupportedOperationException
live.iterator.remove=UnsupportedOperationException
outer.afterItemEdit=[pen:7:[school, sale]]
snapshot=[ItemSnapshot[code=pen, quantity=2, tags=[school]]]
outer.set=UnsupportedOperationException
snapshot.tags.add=UnsupportedOperationException
nested.source=[[x, y], [new]]
nested.shallow=[[x, y]]
nested.deep=[[x]]
nested.deep.inner.add=UnsupportedOperationException
record.plain=[base, later]
record.safe=[base]
record.safe.accessor.add=UnsupportedOperationException
final.reference=[still mutable]
map.value=[one, two]
map.put=UnsupportedOperationException
fixed.null=[ok, null]
copyOf.null=NullPointerException
of.null=NullPointerException
stream.set=UnsupportedOperationException
stream.editable=[s, t, u]
~~~

### Reading the Output by Cause and Effect

**First three lines:** `fixed.set` mutates the array, assigning into the array mutates the list, and sorting the list reorders the array. The size is always 2. The next two exception lines confirm that add/remove operations are indeed rejected.

**`live` and `detached`:** both results were created before the source changed. `live` sees both `A2` and `C`; `detached` keeps `A` and `B`. It is not that `live` has mutation rights—the source owner mutated it through another reference. The view's iterator also does not provide a removal backdoor past the wrapper.

**`outer.afterItemEdit` and `snapshot`:** the outer list `outer` forbids `set` yet still reflects the item with quantity 7 and tag `sale`. `snapshots` captured quantity 2 and froze the tags beforehand. Thus, the two results differ in how elements are represented, not just in outer-list mutation rights.

**Three `nested` lines:** the source gained a new group and the first inner list gained `y`. The shallow copy did not pick up the new group, but still saw `y` because it shared the inner list. The per-group snapshot kept `[[x]]`. Adding to the resulting inner list is blocked.

**Two records:** `PlainTags` tracks the input list and therefore sees `later`. `SafeTags` froze the list in its constructor and kept `[base]`; its accessor also does not hand out an addable list. This checks both the input and output paths of the string-list model.

**`final.reference`:** a `final` variable can still point to a list that allows additions. There is no variable reassignment in the program.

**Two `map` lines:** the mapping `"items" → list` cannot be replaced, yet `"two"` can still be added to the list serving as the value. Map mutation rights and value-object mutation rights are separate.

**Final lines:** `Arrays.asList` can hold `null`, whereas `List.copyOf` and `List.of` reject `null` in the tested cases. The `Stream.toList` result forbids element replacement; when an editable `ArrayList` is genuinely needed, the program requests it explicitly via `Collectors.toCollection(ArrayList::new)`.

No line attempts to modify a source while iterating over it. The verified output reflects single-threaded behavior with a clear operation order; do not use it to infer atomic snapshot guarantees under concurrent multi-threaded updates.

## 9. Applying This to `Set`, `Map`, and Stream Results

### Set: No `set(index)`, Yet Elements Still Have State

A `Set` has no positional index concept like a `List`. Therefore, the distinction of “replacing an element at a position” does not apply literally, but container protection and element state remain separate.

`Set.of` and `Set.copyOf` create unmodifiable sets. A mutable element can still alter the observable state of the set; in particular, data participating in `equals` and `hashCode` must remain stable while the element is in the set. [Set API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

Do not test and rely on a specific `contains` result after mutating an element's comparison data. The right approach is to avoid that state altogether: use elements with stable identity or finalized values.

### Map: Protecting Mappings Does Not Freeze Keys or Values

`Map` is not a subtype of `Collection`, yet the same reasoning applies. An unmodifiable map means you cannot add, remove, or replace mappings through the `Map` API. Keys and values can still hold their own mutable data.

`Map.of` and `Map.copyOf` create unmodifiable maps and reject `null` keys and values. They neither promise to freeze key or value objects nor promise to preserve the iteration order of an input `LinkedHashMap`. [Map API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

For a `Map<String, List<String>>` used as a frozen configuration, protect each value list before freezing the outer map. If a specific presentation order is required, choose a contract that preserves order and control the source separately; do not treat an accidental order from `Map.copyOf` as a guarantee.

If a key is a mutable object, protecting the outer map also does not prevent someone from mutating the key itself. That is a strong reason to use stable value keys.

### Stream: Collectors Do Not Determine Every Layer

Do not treat the following three expressions as equivalent:

~~~java
List<String> a = streamA.toList();
List<String> b = streamB.collect(Collectors.toList());
ArrayList<String> c =
        streamC.collect(Collectors.toCollection(ArrayList::new));
~~~

This is an illustrative snippet with three independent existing streams; a consumed stream cannot be reused.

- `Stream.toList()` has an unmodifiable-result contract.
- `Collectors.toList()` makes no guarantee about mutability or the concrete implementation class of the resulting list.
- `toCollection(ArrayList::new)` explicitly requests the editable container type the program wants.

The `Collectors.toList` contract does not let you infer “always an `ArrayList`” from a single run. [Collectors API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()).

None of the three automatically converts `MutableItem` into `ItemSnapshot`. Element transformation must be written explicitly in `map` or an equivalent data-construction step. Nor should you infer the `null` policy of every collector from `List.of`; each API has its own contract.

## 10. Choosing Guarantees Based on API Needs

### The Caller Needs to Edit a Private Copy

Returning a mutable container copy can be the right choice. For example, an editing UI fetches a list of item codes and adds/removes entries in a form:

~~~java
List<String> editableCodes = new ArrayList<>(storedCodes);
~~~

With string codes, sharing elements creates no path to mutate code contents. If the list holds objects with setters, you must decide whether the form is allowed to mutate them directly. A list copy does not automatically create an “isolated editing session” for the entire model.

### The Caller Needs to Read Current State

An unmodifiable view can be appropriate when the owner manages updates. Documentation should clearly state that the result may reflect subsequent updates, along with any concurrency rules.

A name like `currentTasksView` helps signal intent, though it does not replace a contract. Callers still need to know the source's lifecycle and element mutation rights.

### The Caller Needs Finalized Values for Reports or Configuration

When elements are already immutable, freezing the container is usually enough. When elements are mutable, map them to a finalized data type such as `ItemSnapshot`. For multi-level nested models, write protection rules for every mutable layer.

Do not promise a vague “snapshot.” It might mean only a snapshot of reference counts and order, or a full snapshot of fields needed for a report. Explicitly stating which fields are frozen helps callers understand and test it properly.

### Keeping Slot Count Fixed While Allowing Value Replacement

A fixed-size list fits operations on existing positions or bridging with arrays. There is no need to switch to an unmodifiable collection if the actual requirement still allows replacing elements.

What is worth checking is what rights the downstream algorithm requires. An algorithm that only swaps or sorts positions can work with a fixed-size list; an algorithm that adds or removes elements needs a different contract.

### Costs Must Match the Actual Work Done

Wrapping a view does not have the same goal as traversing and copying data. Freezing groups or converting each element to a snapshot incurs read and allocation costs proportional to element count, nesting depth, and retained data. You cannot compare performance by counting characters in an API call.

Choose the right guarantee first, then measure if cost matters. Arbitrary deep copying can be expensive and semantically wrong; freezing the exact data needed is usually easier to explain and verify.

## 11. Conclusions to Avoid When Reading “Read-Only” Code

### “Seeing `UnsupportedOperationException` Means Immutable”

An exception from `add` only proves that this `add` call was rejected in the tested case. It does not prove `set` is blocked, that the source cannot change, or that elements are immutable.

Do not probe mutation rights by calling no-op operations and guessing the contract—such as removing an element that is not present. Some optional methods may not throw when there is nothing to change. Read the API contract and test the operations that actually matter.

### “Same Size Means Unchanged”

A list can keep the same `size()` while replacing every reference and changing its order. A map can keep the same key count while changing its values. A list can even keep the exact same references while inner element state changes.

Tests should observe what the API promises to protect—such as report contents after the source is updated—rather than only comparing sizes.

### “Once Copied, It Is Immutable”

`new ArrayList<>(source)` is often used precisely because the caller wants to keep mutating the copy. Detaching from the source and forbidding mutation are two independent decisions.

If you need to forbid mutating the result, choose a container with that contract; if you need to forbid all observable value changes, you must also handle the elements.

### “Wrapping a List in a Getter Finishes Protecting the Object”

Mutation paths can still exist via constructor parameters, another getter, an update method, or an element containing a nested list. Check both inputs and every data-returning path.

For data such as arrays, copying on input while returning the internal array still exposes a mutation path. Conversely, copying on output while storing the input array directly still lets the creator mutate internally.

### “Unmodifiable Means Thread-Safe”

An unmodifiable view over a source being updated is still live data. An unmodifiable outer list containing objects mutated by multiple threads still has concurrency issues on those objects.

Deeply immutable values make sharing data easier because no write coordination on the value itself is needed after construction. Even so, you must still publish references safely and properly handle full-version replacement, external resources, or multi-step invariants. [Immutable Objects in Oracle's Concurrency Tutorial](https://docs.oracle.com/javase/tutorial/essential/concurrency/immutable.html).

Calling `List.copyOf` or looping to build a snapshot does not automatically turn reading multiple concurrently mutated objects into an atomic transaction. You need a protocol coordinated with writers, such as shared locking, versioned sources, or already-finalized data.

### “Deep Immutability Means No Need to Specify Scope”

A result may freeze display fields while still holding an ID referencing external data that will change. That is not wrong if the contract only freezes the ID and selected fields. It is only wrong when advertised as freezing the entire state of the system.

Prove immutability over the data graph that actually forms the return value. Do not pull resources outside the value, such as a live database, into a list's immutability promise.

## 12. Practice Exercises with Answers

Try answering each exercise before reading the explanation. For each one, identify **which reference path** allows observing or making a change, rather than just labeling it “mutable/immutable.”

### Exercise 1 — Cannot Add, Yet Can Still Replace

This snippet runs inside a method with all required imports:

~~~java
String[] data = {"a", "b"};
List<String> values = Arrays.asList(data);
values.set(1, "B");
~~~

**Question:** What is `data[1]`? Is `values.add("c")` supported? How should construction change if the caller must add elements?

**Answer:** `data[1]` is `"B"`, because the list uses the slots of the same array. Adding changes the size and is rejected with `UnsupportedOperationException`. You can use `new ArrayList<>(Arrays.asList(data))` to get an addable list structurally detached from the array. Because the elements are strings, you do not need to clone the strings to prevent content mutation.

### Exercise 2 — A View Changes Even Though the Caller Does Not Mutate

~~~java
List<String> original = new ArrayList<>(List.of("a"));
List<String> result = Collections.unmodifiableList(original);
original.add("b");
~~~

**Question:** How many elements does `result` have? What contract fits this result?

**Answer:** It has 2 elements. `result` reads through `original`; updates through `original` are observed through the view. The fitting contract is “cannot be mutated through the result; observes source state.” If you want to preserve the strings as of the call time, take a snapshot such as `List.copyOf(original)` **at the moment you need to freeze it**, not after `b` has already been added if the goal was the earlier data.

### Exercise 3 — A Shallow Copy Retains Element References

~~~java
StringBuilder text = new StringBuilder("a");
List<StringBuilder> source = new ArrayList<>(List.of(text));
List<StringBuilder> saved = List.copyOf(source);
source.clear();
text.append("b");
~~~

**Question:** What is `saved.size()`? What is `saved.get(0).toString()`? How can you preserve the original text content?

**Answer:** The size is 1; the text is `"ab"`. Calling `clear` on the source does not change `saved`'s membership, but `text` is a shared object. You must convert to `String` at snapshot time—for example, `source.stream().map(StringBuilder::toString).toList()` **before `clear` and before `append`**. Once the source has been cleared, copying from it alone cannot recover the old contents.

### Exercise 4 — Which Layer Should Be Frozen?

~~~java
List<String> row = new ArrayList<>(List.of("x"));
List<List<String>> table = List.of(row);
row.add("y");
~~~

**Question:** What is the observed value of `table`? What is the minimal change in construction to preserve the initial string group?

**Answer:** `table` represents `[[x, y]]`. The outer list forbids adding/removing, yet shares `row`. At snapshot time, construct `List.of(List.copyOf(row))` or, for multiple groups, map each group through `List.copyOf` and collect into an unmodifiable outer list. If constructed after adding `y`, a valid snapshot will contain `y`; copying cannot turn back time.

### Exercise 5 — Which Record Protects the Label List?

Compare the two declarations:

~~~java
record DraftLabels(List<String> labels) {
}

record SavedLabels(List<String> labels) {
    SavedLabels {
        labels = List.copyOf(labels);
    }
}
~~~

**Question:** When constructed from an `ArrayList<String>`, which type does not track membership changes to the input list? Why does this conclusion depend on the `String` leaf type here?

**Answer:** `SavedLabels` freezes the list in its constructor. `DraftLabels` merely stores the input reference. With `SavedLabels`, the accessor returns an unmodifiable list and strings cannot have their contents mutated, so this model has a stable value. If changed to `List<MutableLabel>`, `copyOf` does not protect each label's state; you would need an immutable label representation or to convert each label into finalized data.

### Exercise 6 — A Deep Copy Can Still Be Mutable

A method creates `new ArrayList<MutableItem>()` and constructs a new `MutableItem` for each element. Each new item has its own tag list, yet still exposes a quantity setter and an add-tag method.

**Question:** Is the result independent of the source? Is it deeply immutable? What if the outer list is wrapped with `unmodifiableList`?

**Answer:** If every mutable part that needed isolation was genuinely copied, the caller can have an independent editable copy. It is not deeply immutable because the new objects can still be mutated. Wrapping the outer list only blocks container mutation; the quantity setter and tag-adding method on each item remain. You must switch to a value model with no exposed mutation paths, or fully control all references to inner parts.

### Exercise 7 — An Unmodifiable Map Containing a Mutable List

~~~java
Map<String, List<String>> options =
        Map.of("modes", new ArrayList<>(List.of("fast")));
options.get("modes").add("safe");
~~~

**Question:** Do `options.put("modes", List.of("other"))` and the `add` call above target the same object? What must be done to freeze the two modes at construction time?

**Answer:** `put` targets the map and is rejected. `add` targets the value list and is supported in the example. To freeze string data, construct the value with `List.copyOf(inputModes)` and place that value into an unmodifiable map, or use `List.of` when all strings are known upfront. If another list still shares mutable element objects, that layer must be handled as well.

### Exercise 8 — Write the Contract Before Choosing the API

Three methods must return:

1. A list of codes for the caller to add/remove freely without altering the service's code list.
2. A read-only task list that must reflect subsequent updates made by the service.
3. An item report preserving codes, quantities, and tags as of snapshot time.

**Question:** Choose an appropriate construction for each and name one limitation of each choice.

**Answer:**

1. You can use `new ArrayList<>(codes)`. It detaches the container and allows editing; if `codes` held mutable elements instead of strings, element mutation rights would still need analysis.
2. You can use `Collections.unmodifiableList(tasks)`. It tracks the source; you must document inner task mutation rights and concurrency rules. It does not promise to preserve history.
3. Convert each item into an `ItemSnapshot` with the reported fields protected, then collect into an unmodifiable list. You must ensure reading the source for the snapshot is consistent with business requirements; copy calls by themselves do not create a system-wide atomic snapshot point.

When evaluating any “read-only” result, trace every mutation path: from variable to container, from container to element, and down into nested data. A guarantee is only meaningful when it specifies which paths it blocks and which paths still allow observing changes.
