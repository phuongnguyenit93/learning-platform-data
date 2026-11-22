# List.of, Set.of, Map.of, and Map.ofEntries

When a list of states, a set of permissions, or a lookup table is already known at construction time, writing a series of `add` and `put` calls easily buries the intent in initialization boilerplate. The `List.of`, `Set.of`, `Map.of`, and `Map.ofEntries` methods let you write the required data directly and return an unmodifiable container.

What matters is not only the concise syntax. Each method expresses a contract regarding ordering, duplicate elements, `null` values, and mutability. Choosing the wrong contract can cause the program to throw an exception right when creating the data, or cause a test to depend on an iteration order that is not guaranteed.

These methods have been available since **Java 9**. All programs in this lesson target Java 17 and require no external libraries. Learners should know the basic meaning of `List`, `Set`, `Map`, type parameters, and exceptions. [JDK 9 New Features](https://docs.oracle.com/javase/9/whatsnew/).

## 1. Choose the data semantics before choosing the call

Consider a task management tool:

- The steps `"receive"`, `"validate"`, and `"store"` have an order. Repeating a step may be meaningful. This is list-shaped data.
- The permissions `"READ"` and `"WRITE"` are members of a set. The declaration order is not necessarily the display order. This is set-shaped data.
- The status code `"NEW"` corresponds to a display label. Each code must map to a value. This is map-shaped data.

The following snippet is illustrative code inside a method with all necessary imports:

~~~java
List<String> pipeline = List.of("receive", "validate", "store");
Set<String> permissions = Set.of("READ", "WRITE");
Map<String, String> labels = Map.of(
        "NEW", "Mới",
        "DONE", "Hoàn tất"
);
~~~

Do not use a set just to make elements "unmodifiable" if order and repetition still matter. A list can also be unmodifiable. Conversely, do not use a list instead of a permission set and let duplicate elements create ambiguity about the data.

A map is not a list containing pairs in parameter order. The syntax `"NEW", "Mới", "DONE", "Hoàn tất"` describes mappings; it does not create a guarantee that `"NEW"` will be iterated before `"DONE"`.

These methods are **static factory methods** on the interfaces. They create and return an object that satisfies the interface contract; the program does not need to know the internal implementation class. Store the result using the appropriate `List<E>`, `Set<E>`, or `Map<K,V>` type.

## 2. Contract table to remember

| Creation method | Input data | Duplicates | `null` at creation | Resulting order |
| --- | --- | --- | --- | --- |
| `List.of(e1, e2, ...)` | Elements | Allows equal elements | Disallows `null` elements | Preserves argument order |
| `Set.of(e1, e2, ...)` | Elements | Rejects duplicate elements with `IllegalArgumentException` | Disallows `null` elements | No guarantee on iteration order |
| `Map.of(k1, v1, k2, v2, ...)` | Alternating key–value pairs | Rejects duplicate keys; values may repeat | Disallows `null` keys or values | No guarantee on iteration order |
| `Map.ofEntries(entry1, entry2, ...)` | `Map.Entry` instances | Rejects duplicate keys; values may repeat | Disallows `null` entries, keys, or values | No guarantee on iteration order |

The results of all four creation methods are **unmodifiable through the container API**: you cannot add, remove, or replace elements/mappings. However, the element, key, and value objects themselves can still be modified if their types allow it.

Read the "Duplicates" and "Resulting order" columns together. A set having no duplicate elements does not mean the set is sorted. A map having no duplicate keys does not mean the first key in the call is the first key during iteration.

The Java 17 documentation describes separately the guarantees of [unmodifiable lists](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable), [unmodifiable sets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable), and [unmodifiable maps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

## 3. `List.of`: an ordered sequence that allows repetition

### Syntax from empty to many elements

~~~java
List<String> empty = List.of();
List<String> single = List.of("ready");
List<String> repeated = List.of("start", "retry", "retry", "finish");
~~~

In the last list, the two occurrences of `"retry"` are two positions in the sequence. There is no deduplication step. `get(0)` is `"start"`, and the sequence order matches the argument order.

Java provides overloads with fixed argument counts from 0 to 10 and a variable-argument (varargs) form. Therefore, **`List.of` is not limited to 10 elements**:

~~~java
List<Integer> months = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);
~~~

You do not need to know which overload is selected to use the list contract correctly. Nor should you infer a performance threshold or a stable storage structure from the number of overloads.

### Disallows adding, removing, and replacing elements

For a list created by `List.of`, `add` and `remove` are rejected; `set` is also rejected. This is not a "fixed-size only but still allows replacing slots" list.

The following snippet is an **example of an operation that will throw an exception**, not a way to update the list:

~~~java
List<String> steps = List.of("draft", "review");
steps.set(0, "editing"); // UnsupportedOperationException
~~~

An in-place sorting algorithm or `replaceAll` is also a modification operation. If you need those operations, create a working copy with a modifiable contract, or build a new result via a transformation.

### The element type of an empty result needs context

~~~java
List<String> declared = List.of();
var inferred = List.of();
List<String> explicit = List.<String>of();
~~~

`declared` gets its element type from the target type. In the `var` example, there is no specific target type such as `List<String>`, so you should not assume the compiler automatically knows it is a list of strings just because of the author's intent.

You can write the type explicitly when an API or complex expression needs it. The target type solves the data typing issue; it does not change the mutability of the result.

## 4. `Set.of`: declaring a valid set of members

### A duplicate error is an input data error

~~~java
Set<String> states = Set.of("NEW", "RUNNING", "DONE");
~~~

This declaration style is appropriate when each member is listed only once. If the argument list contains two equal values, the call throws `IllegalArgumentException` instead of silently keeping one.

~~~java
Set<String> invalid = Set.of("NEW", new String("NEW"));
// IllegalArgumentException: two strings are equal according to equals.
~~~

The intentionally invalid example above helps distinguish `Set.of` from a pipeline that collects data and then deduplicates it. If user input can genuinely repeat and the requirement is to merge duplicates, use a workflow suited to that requirement; do not pick a method that rejects duplicates and treat the exception as an unexpected bug.

### Duplicates are determined by value equality

Two objects with different references can still be duplicate elements. Conversely, having the same `hashCode` is not enough to make two elements duplicates if they are not equal according to `equals`.

The complete program uses `"Aa"` and `"BB"`: these two strings have the same hash code but are not equal, so a set containing both strings is still valid. The result must not be inferred solely by comparing hash codes.

If you use a custom class as elements, the class's `equals`/`hashCode` contract must be correct. Do not mutate state that participates in comparison while the object is a set element; the unmodifiability of the outer set does not prevent modifying the object itself.

### Not a sorted set or an insertion-ordered set

`Set.of("z", "a", "m")` does not guarantee iterating in `z, a, m` order, nor does it guarantee `a, m, z`. On a given run, you might happen to see one of those orders by chance.

If output for the user needs to be sorted, perform sorting explicitly. For example, the program uses `new TreeSet<>(colors)` only to **produce an ordered printable representation** for string data. That does not change the contract of the original set.

If order is the core meaning of the data, consider using a list or an order-preserving structure with a clear contract. You cannot deduce business order by reading the first iteration of `Set.of`.

Like `List.of`, `Set.of` has a varargs form so it also supports more than 10 elements, provided the elements are unique and non-`null`.

## 5. `Map.of`: reading as key–value pairs

### Alternating syntax must be grouped for readability

~~~java
Map<String, Integer> retries = Map.of(
        "network", 3,
        "database", 2,
        "validation", 0
);
~~~

Each key stands immediately before its value. The result has three mappings. `get("network")` returns 3.

Put each pair on its own line. With a long call on a single line, accidentally mismatching keys and values can still compile if the parameters have compatible types, even though the data semantics are already wrong.

The limit of `Map.of` is **at most 10 pairs**, not 10 individual arguments. It has overloads for 0 to 10 mappings; there is no varargs form taking an arbitrary sequence `k1, v1, k2, v2, ...`. A need for 11 pairs requires `Map.ofEntries` or another construction approach.

### Duplicate values are allowed; duplicate keys are not

~~~java
Map<String, Integer> aliases = Map.of("one", 1, "single", 1);
~~~

The map has two distinct keys pointing to a value equal to 1. This is valid data.

However, the following intentionally invalid snippet throws `IllegalArgumentException`:

~~~java
Map<String, Integer> invalid = Map.of("x", 1, "x", 2);
~~~

It does not follow a "last write wins" rule like two ordinary `put` calls on many modifiable maps. Even `Map.of("x", 1, "x", 1)` still has a duplicate key and is rejected, even though the two values are identical.

This creation method is useful for catching errors in declared lookup tables: a mistyped duplicate code will not silently overwrite an earlier mapping.

### A missing key is different from a key with a `null` value

This map does not allow `null` values. Calling `get` with a valid key that is absent still returns `null` according to the standard map contract.

Therefore, `map.get("missing") == null` does not prove that the map stored a `null` value. In the demonstration program, it indicates that there is no mapping for the string `"missing"`.

Nor should you infer from the prohibition on storing `null` keys that every query with `null` will return `false` or `null`. Operations that query invalid elements/keys have their own rules and may throw exceptions. If a lookup input can be `null`, handle that condition explicitly before querying.

## 6. `Map.ofEntries` and the role of `Map.entry`

### Each pair becomes a structured argument

~~~java
Map<String, Integer> thresholds = Map.ofEntries(
        Map.entry("low", 10),
        Map.entry("medium", 20),
        Map.entry("high", 30)
);
~~~

`Map.entry(k, v)` creates a `Map.Entry<K,V>` object holding a key–value pair. Creating an entry does not create a map, nor does it add the pair to an existing map.

`Map.ofEntries` takes the entries and extracts their keys and values to create an unmodifiable map. It uses varargs, so it supports more than 10 entries; the practical limits are ordinary resource and platform limits, with no promise of "unlimited" size.

You can use a static import for large tables:

~~~java
import static java.util.Map.entry;
~~~

Once this import is present, you write `entry("low", 10)` inside `Map.ofEntries`. This is a stylistic choice; writing `Map.entry` in full is often easier for beginners to recognize.

### Input entries are not the backing storage for later mappings

`Map.ofEntries` extracts keys and values; it does not retain the input entry objects themselves. Therefore, changing the value of a modifiable entry after creation is not a way to update the resulting map. [Map.ofEntries API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#ofEntries(java.util.Map.Entry...)).

Illustrative example:

~~~java
AbstractMap.SimpleEntry<String, Integer> sourceEntry =
        new AbstractMap.SimpleEntry<>("limit", 3);

Map<String, Integer> result = Map.ofEntries(sourceEntry);
sourceEntry.setValue(9);
~~~

Afterward, `sourceEntry.getValue()` is 9, but `result.get("limit")` is still 3. That changed a value reference in the source entry; the map had already extracted the pair of references earlier.

If the value is a modifiable list, the map and the source entry can still hold references to that same list. Not retaining the entry itself does not mean deep-cloning the key and value objects.

### `Map.entry` does not allow `setValue`

An entry created by `Map.entry` is unmodifiable, rejects `null` keys or values, and is not attached to any map. Calling `entry.setValue(...)` throws `UnsupportedOperationException`.

Distinguish the contract of a specific entry from the `Map.Entry` interface itself. The interface is also used for many entries with different origins and mutability; you cannot look at the `Map.Entry` type and conclude that all of them support or all of them reject `setValue`. [Map.Entry Interface, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

One detail when serialization is needed: entries created by `Map.entry` **do not support serialization**. That does not prevent a map created by `Map.ofEntries` from supporting serialization when the keys and values satisfy the corresponding contract, because the map does not retain the input entries. Do not extrapolate the capabilities of an intermediate object to the resulting object.

## 7. `null` and duplicates: pinpointing errors at the right layer

### Use explicit types in `null` examples

~~~java
List.of("ok", (String) null);
Set.of("ok", (String) null);
Map.of("x", (Integer) null);
Map.entry("x", (Integer) null);
~~~

All of the calls above are intentionally invalid examples and throw `NullPointerException`. Casting in the examples clearly shows which `null` data position is being tested.

With varargs, there is also a difference between "one `null` element" and "the entire parameter array is `null`":

~~~java
List.of((String) null);    // One null element.
List.of((String[]) null);  // Null varargs array.
~~~

Both are invalid. Do not use a bare call like `List.of(null)` to explain element count if you have not yet determined which overload and type the compiler selects.

### `Map.ofEntries` has multiple places that can be `null`

Invalid input can be:

- The entry array itself is `null`.
- An entry element in the array is `null`.
- A non-`null` entry that contains a `null` key or `null` value.

`Map.entry` already rejects `null` when creating the pair. To demonstrate that `Map.ofEntries` also checks the contents of entries coming from elsewhere, the program uses a `SimpleEntry` with a `null` key and verifies the error at the map creation step.

In the expression `Map.ofEntries(Map.entry("x", null))`, the error can already occur inside `Map.entry` before the outer call is executed. When reading a stack trace, distinguishing the exact place where the data is constructed makes diagnosis easier.

If the data has multiple errors simultaneously—such as both duplicates and `null`—do not write tests that enforce a specific error detection order that the contract does not specify. Test each constraint with data that violates only the constraint under test.

### This is not an automatic data-sanitization step

These factories are suited for asserting that data already has a valid shape. They do not automatically replace `null` with an empty string, do not automatically merge duplicate keys, and do not automatically pick the "right" value on conflict.

If input comes from a form or configuration file, validate and report errors with business context before creating the final structure. A `NullPointerException` or `IllegalArgumentException` from a factory does not replace a clear message such as "status code DONE is declared twice".

## 8. Arrays, varargs, and the actual elements of a collection

### Passing a reference array to get multiple elements

~~~java
String[] codes = {"a", "b"};
List<String> list = List.of(codes);
Set<String> set = Set.of(codes);
~~~

In this call style, the array supplies the elements to the factory. The list has two strings in array order. The set also contains two strings, provided there are no duplicates. If the array contains `null` or duplicate elements when creating a set, the constraints still apply.

The result is not a write-through view over the slots of the input array. Changing `codes[0]` afterward does not change the elements of the created list/set. The demonstration program checks this directly.

This is an important difference from `Arrays.asList(codes)`: the list from `Arrays.asList` is backed by the array and still supports replacing elements. [Arrays.asList API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### To make the array itself a single element, state it explicitly

~~~java
List<String[]> oneArray = List.<String[]>of(codes);
~~~

Here the list has only **one element**, and that element is the `codes` array object. Changing `codes[0]` will be observed through `oneArray.get(0)[0]` because the array is a shared element.

There is no contradiction with the previous example: the two calls chose two different data models. One call takes the strings as elements; the other takes the array as an element.

Passing arrays and writing explicit type arguments are described in the `List.of(E...)` and `Set.of(E...)` APIs. Java resolves overloads based on expression types and the phases for determining applicable methods—not based on the author's implicit intent. [Method Invocation Rules in JLS 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2).

### Primitive arrays do not automatically become multiple wrappers

~~~java
List<int[]> numbers = List.of(new int[]{3, 4});
~~~

The list has one `int[]` element, not two `Integer`s. An `int[]` object is not an `Integer[]`, and the factory does not automatically walk into the array to box each number.

To declare a sequence of wrapper integers, use `List.of(3, 4)`. To convert data from an existing primitive array, choose an explicit conversion step; do not guess the element type from the array brackets.

Also be careful when passing an existing collection:

~~~java
List<String> existing = new ArrayList<>(List.of("a", "b"));
List<List<String>> oneList = List.of(existing);
~~~

`oneList` has one element, which is the `existing` list; `of` is not an operation that "unpacks" every collection. When the goal is to create an unmodifiable copy from the elements of an existing collection, `copyOf` is the other API family to consider. Identify the exact element type before choosing.

## 9. Complete program verifying the contracts

Save the code to **`CollectionFactoriesDemo.java`**. The program does not directly print sets/maps whose iteration order is not guaranteed. Ordered print lines use `TreeSet` or `TreeMap` for string keys and elements; other checks use `size`, `get`, `contains`, or `equals`.

The `rejects` helper verifies the expected exception type. If an operation unexpectedly succeeds or throws the wrong type, the program stops with an `AssertionError`. It does not rely on the exception message text because the message is not what is being verified here.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionFactoriesDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("empty.sizes="
                + List.of().size() + "/"
                + Set.of().size() + "/"
                + Map.of().size() + "/"
                + Map.ofEntries().size());

        List<String> levels = List.of("low", "high", "low");
        System.out.println("list=" + levels);
        System.out.println("list.index1=" + levels.get(1));
        rejects("list.add", UnsupportedOperationException.class,
                () -> levels.add("medium"));
        rejects("list.set", UnsupportedOperationException.class,
                () -> levels.set(0, "medium"));

        Set<String> colors = Set.of("red", "blue", "green");
        System.out.println("set.sorted=" + new TreeSet<>(colors));
        System.out.println("set.containsGreen=" + colors.contains("green"));
        rejects("set.add", UnsupportedOperationException.class,
                () -> colors.add("black"));
        System.out.println("set.hashCollision.size="
                + Set.of("Aa", "BB").size());

        Map<String, Integer> limits = Map.of("small", 2, "large", 4);
        System.out.println("map.sorted=" + new TreeMap<>(limits));
        System.out.println("map.small=" + limits.get("small"));
        System.out.println("map.missing=" + limits.get("missing"));
        System.out.println("map.sameValues.size="
                + Map.of("one", 1, "single", 1).size());
        rejects("map.put", UnsupportedOperationException.class,
                () -> limits.put("small", 9));
        rejects("map.keySet.remove", UnsupportedOperationException.class,
                () -> limits.keySet().remove("small"));
        Map.Entry<String, Integer> fromMap =
                limits.entrySet().iterator().next();
        rejects("map.entry.setValue", UnsupportedOperationException.class,
                () -> fromMap.setValue(9));

        Map<String, Integer> many = Map.ofEntries(
                Map.entry("k01", 1),
                Map.entry("k02", 2),
                Map.entry("k03", 3),
                Map.entry("k04", 4),
                Map.entry("k05", 5),
                Map.entry("k06", 6),
                Map.entry("k07", 7),
                Map.entry("k08", 8),
                Map.entry("k09", 9),
                Map.entry("k10", 10),
                Map.entry("k11", 11));
        System.out.println("ofEntries.size=" + many.size());
        System.out.println("ofEntries.k11=" + many.get("k11"));

        Map.Entry<String, Integer> pair = Map.entry("limit", 3);
        rejects("entry.setValue", UnsupportedOperationException.class,
                () -> pair.setValue(9));
        AbstractMap.SimpleEntry<String, Integer> seed =
                new AbstractMap.SimpleEntry<>("limit", 3);
        Map<String, Integer> captured = Map.ofEntries(seed);
        seed.setValue(9);
        System.out.println("seed.value=" + seed.getValue());
        System.out.println("ofEntries.captured=" + captured.get("limit"));

        rejects("list.null", NullPointerException.class,
                () -> List.of("ok", (String) null));
        rejects("set.null", NullPointerException.class,
                () -> Set.of("ok", (String) null));
        rejects("map.nullKey", NullPointerException.class,
                () -> Map.of((String) null, 1));
        rejects("map.nullValue", NullPointerException.class,
                () -> Map.of("x", (Integer) null));
        rejects("entry.nullValue", NullPointerException.class,
                () -> Map.entry("x", (Integer) null));
        rejects("ofEntries.nullEntry", NullPointerException.class,
                () -> Map.<String, Integer>ofEntries(
                        (Map.Entry<String, Integer>) null));
        rejects("ofEntries.nullKey", NullPointerException.class,
                () -> Map.ofEntries(
                        new AbstractMap.SimpleEntry<String, Integer>(null, 1)));
        rejects("set.duplicate", IllegalArgumentException.class,
                () -> Set.of("red", new String("red")));
        rejects("map.duplicateKey", IllegalArgumentException.class,
                () -> Map.of("x", 1, new String("x"), 1));
        rejects("ofEntries.duplicateKey", IllegalArgumentException.class,
                () -> Map.ofEntries(Map.entry("x", 1), Map.entry("x", 2)));

        String[] codes = {"a", "b"};
        List<String> expanded = List.of(codes);
        Set<String> expandedSet = Set.of(codes);
        List<String[]> oneArray = List.<String[]>of(codes);
        codes[0] = "changed";
        System.out.println("array.expandedList=" + expanded);
        System.out.println("array.expandedSet.sorted="
                + new TreeSet<>(expandedSet));
        System.out.println("array.singleElement.size=" + oneArray.size());
        System.out.println("array.singleElement.value="
                + Arrays.toString(oneArray.get(0)));
        List<int[]> primitiveArray = List.of(new int[]{3, 4});
        System.out.println("primitive.size=" + primitiveArray.size());
        System.out.println("primitive.first.length="
                + primitiveArray.get(0).length);

        System.out.println("list.eleven.size="
                + List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11).size());
        System.out.println("set.eleven.size="
                + Set.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11).size());

        List<String> steps = new ArrayList<>(List.of("draft"));
        Map<String, List<String>> nested = Map.of("steps", steps);
        steps.add("published");
        System.out.println("nested.value=" + nested.get("steps"));
        rejects("nested.map.put", UnsupportedOperationException.class,
                () -> nested.put("steps", List.of("other")));

        List<String> editable = new ArrayList<>(levels);
        editable.add("medium");
        System.out.println("editable=" + editable);
        System.out.println("original=" + levels);
        System.out.println("list.valueEquality="
                + levels.equals(List.of("low", "high", "low")));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 CollectionFactoriesDemo.java
java CollectionFactoriesDemo
~~~

JDK 17 or later is required to compile with this command. `--release 17` restricts syntax and APIs to level 17. The code was compiled with that command and run on OpenJDK 24.0.2, exiting successfully with the following exact stdout:

~~~text
empty.sizes=0/0/0/0
list=[low, high, low]
list.index1=high
list.add=UnsupportedOperationException
list.set=UnsupportedOperationException
set.sorted=[blue, green, red]
set.containsGreen=true
set.add=UnsupportedOperationException
set.hashCollision.size=2
map.sorted={large=4, small=2}
map.small=2
map.missing=null
map.sameValues.size=2
map.put=UnsupportedOperationException
map.keySet.remove=UnsupportedOperationException
map.entry.setValue=UnsupportedOperationException
ofEntries.size=11
ofEntries.k11=11
entry.setValue=UnsupportedOperationException
seed.value=9
ofEntries.captured=3
list.null=NullPointerException
set.null=NullPointerException
map.nullKey=NullPointerException
map.nullValue=NullPointerException
entry.nullValue=NullPointerException
ofEntries.nullEntry=NullPointerException
ofEntries.nullKey=NullPointerException
set.duplicate=IllegalArgumentException
map.duplicateKey=IllegalArgumentException
ofEntries.duplicateKey=IllegalArgumentException
array.expandedList=[a, b]
array.expandedSet.sorted=[a, b]
array.singleElement.size=1
array.singleElement.value=[changed, b]
primitive.size=1
primitive.first.length=2
list.eleven.size=11
set.eleven.size=11
nested.value=[draft, published]
nested.map.put=UnsupportedOperationException
editable=[low, high, low, medium]
original=[low, high, low]
list.valueEquality=true
~~~

### What does each line prove?

**`empty.sizes`** confirms that all four factories work for empty data. There is no need to create and then clear a modifiable container to get an empty result.

**The `list` group** confirms that the list preserves order and duplicate elements, supports indexed access, and disallows adding or replacing elements.

**The `set` group** uses a separate sorted representation so stdout is stable. `set.hashCollision.size=2` shows that a hash collision does not automatically turn two distinct strings into duplicate elements.

**The `map` group** confirms mappings, valid duplicate values, and that an absent key returns `null`. `put`, removal via `keySet`, and `setValue` on a map entry all fail to open a path to modify the result.

**The `ofEntries` group** creates 11 mappings. The final value is looked up by key, so it does not depend on where that key appears during iteration.

**`seed.value` and `ofEntries.captured`** separate modifying the source entry from the created map. The data here is `String` and `Integer`; there are no nested modifiable value objects that would make the result ambiguous.

**The exception lines** test each violation individually. Two strings with different references but equal values still trigger a duplicate error. Duplicate keys are rejected both when the values are the same and when they are different.

**The `array` group** confirms two different interpretations of an array: taking the strings as multiple elements, or keeping the array itself as a single element. Only the latter continues to observe assignments to the array after creation.

**The two `eleven` lines** prevent mistakenly applying `Map.of`'s limit to `List.of` or `Set.of`. Both collections can be created with 11 elements.

**The `nested` group** confirms that an unmodifiable map can still hold a modifiable list. Modifying the source list shows up through the same value object; `put` on the map is still blocked.

**The final lines** show that when editing is needed, creating a new `ArrayList` gives a separate working copy at the list layer. `equals` checks value equality between two lists; the program does not predict whether two factories return the same object instance.

## 10. What are the limits of "unmodifiable"?

### It does not make nested objects deeply immutable

~~~java
List<StringBuilder> notes =
        List.of(new StringBuilder("draft"));

notes.get(0).append("-edited");
~~~

This is valid illustrative code. The list still holds the same element at the same position, while the `StringBuilder` element changes its state.

For a map, `map.get(key).add(...)` can modify a value list even though `map.put(...)` is blocked. For a set or map keys, modifying data that participates in `equals`/`hashCode` can even break lookup assumptions.

If the goal is stable configuration data, use immutable leaf types or convert mutable data into a finalized representation before passing it to a factory. The factory methods do not recursively traverse every layer to copy objects.

The documentation on unmodifiable collections distinguishes container mutability from element state and from views over a source. [Definition in Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

### It does not guarantee an implementation class or object identity

Do not cast the result of `List.of` to `ArrayList`, do not inspect internal class names, and do not use them as a business condition.

These results have value-based semantics. Use `equals` to compare contents according to the list/set/map contract. Do not rely on `==`, `System.identityHashCode`, or the assumption that a factory "always returns a new object".

Also do not use factory results as synchronization lock objects. If you need a lock, create a dedicated lock object with clear ownership. Data guarantees are not a lock allocation mechanism for your program.

### It does not turn data initialization into a concurrent transaction

If the arguments are references to objects currently being modified by another thread, the factory still receives only those references. If data is collected across multiple reads, those reads do not automatically become an atomic snapshot just because the final step calls `ofEntries`.

Use stabilized data or a reading protocol appropriate for the source. The core purpose of these factories is to create structures with clear contracts, not to provide thread-coordination mechanisms.

### It does not make data a compile-time constant

A `static final List<String>` field can hold a list created by a factory, but the list object is still initialized at runtime. This is not a new "collection literal" in the language syntax, nor is it a string/numeric constant treated as a constant expression by the compiler.

`final` only prevents reassigning the variable after initialization. Container unmodifiability comes from the factory; deep immutability still depends on the data inside.

## 11. Practical choices and common migration mistakes

### Creating known declarative data

These factories are suited for data such as lists of modes, sets of supported codes, constant mapping tables, and fixed experiment inputs. They immediately express the intent not to modify the container and catch certain mistakes at construction time. [Oracle's Guide to Using Factories](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html).

For example, a set of valid codes should reject accidentally declaring the same code twice; a list of processing steps may need to preserve repeated elements. The data contract determines whether to use a set or a list.

### Needing updates later

~~~java
List<String> work = new ArrayList<>(List.of("draft", "review"));
work.add("publish");
~~~

The `ArrayList` copy supports modification. For a map, you can build a modifiable map from the initial data when requirements allow updates.

Do not replace existing `ArrayList`/`HashMap` code with `of` just for shorter syntax while overlooking subsequent updates. Any calls to `add`, `sort`, `removeIf`, `put`, `compute`, or updates through views must be evaluated against the new contract.

If you want versioned data changes without mutating the old version, create a new value and swap the owning reference appropriately. Do not catch `UnsupportedOperationException` and silently treat the update as having succeeded.

### Needing order for a set or map

If data must be displayed in declaration order, do not start with `Map.of` and hope `new LinkedHashMap<>(thatMap)` will restore the argument order. The copy can only preserve the order it observes from the input map; it does not know the order of arguments in source code.

Insertion-order preservation must be built from the start via ordered insertions into a `LinkedHashMap`, then wrapped with the appropriate read-only view if needed. [LinkedHashMap Ordering Contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

If the requirement is key order, sort by key explicitly. If the requirement is a sequence of steps, use a list. The three requirements—"having the same mappings", "preserving insertion order", and "sorting by key"—are not interchangeable.

### Converting existing data

`List.of(existingList)` keeps that list as a single element. `Set.of(existingSet)` likewise does not automatically convert into a set of the input set's members. The `copyOf` family serves a different need: taking data from an existing collection/map to create an unmodifiable result.

Do not infer all constraints of `copyOf` from `of`. For example, a collection conversion API may handle duplicate elements differently from a factory declaring a set from multiple arguments. When converting data, read the exact contract of the method being called.

### Understanding errors during program initialization

A `static final` table with a duplicate key or `null` can cause class initialization to fail before business logic runs. In that case, inspect the underlying cause inside the initialization error to locate the exact factory and faulty data pair.

Do not just look at an outer error and conclude the JVM or library is broken. A lookup table validated at creation time is precisely where invalid declarative data ought to be caught.

## 12. Practice with answers

### Exercise 1 — Keep a repetition or report an error?

Consider two calls:

~~~java
List<String> attempts = List.of("read", "retry", "retry");
Set<String> actions = Set.of("read", "retry", "retry");
~~~

**Question:** Which call succeeds? If the goal is to describe sequentially what happened, which structure should you choose?

**Answer:** The list succeeds and has 3 elements in order. The set throws `IllegalArgumentException` because `"retry"` is declared twice. An event log needs to preserve order and occurrence counts, so a list is appropriate; using a set would lose meaning even if another workflow allowed automatic deduplication.

### Exercise 2 — Having the same value does not mean duplicate keys

~~~java
Map<String, Integer> a = Map.of("small", 1, "tiny", 1);
Map<String, Integer> b = Map.of("small", 1, "small", 1);
~~~

**Question:** Which map is valid? Does the second map pick one of the two pairs?

**Answer:** `a` is valid with 2 mappings. `b` is not created and instead throws `IllegalArgumentException`. `Map.of` checks for duplicate keys; it does not use a rule like "skip duplicate pairs if values match" and does not pick one pair as the result.

### Exercise 3 — How do you write 11 mappings?

A table needs to map from `"A01"` through `"A11"` to corresponding numbers.

**Question:** Can you call `Map.of` with 11 pairs? Which factory within the scope of this lesson should you use to declare all of them?

**Answer:** `Map.of` has no overload accepting 11 pairs; this is a compile-time method-matching issue, not a runtime size error. Use `Map.ofEntries` and 11 calls to `Map.entry`. Do not split them into two maps and assume they are automatically merged. `List.of` and `Set.of` do not share this 10-element limit because they have element varargs forms.

### Exercise 4 — Is an array read as elements or kept intact?

~~~java
String[] values = {"x", "y"};
List<String> a = List.of(values);
List<String[]> b = List.<String[]>of(values);
values[0] = "X";
~~~

**Question:** What are the size and observed data of each list?

**Answer:** `a` has size 2 and still contains `"x"` and `"y"`. `b` has size 1; that element is the same array, so `b.get(0)[0]` is `"X"`. Do not print the array directly and guess the default string representation; use `Arrays.toString` if you need to display the slots.

### Exercise 5 — An int array with two numbers

~~~java
var values = List.of(new int[]{8, 9});
~~~

**Question:** Is this a `List<Integer>` of size 2? If you want two wrapper integer elements, how do you write it?

**Answer:** No. It is a list with one `int[]` element. Use `List.of(8, 9)` to get two `Integer` elements. Passing a primitive array as an argument does not ask Java to unpack the slots and box each one.

### Exercise 6 — Does modifying a source entry update the map?

~~~java
AbstractMap.SimpleEntry<String, Integer> pair =
        new AbstractMap.SimpleEntry<>("count", 5);

Map<String, Integer> counts = Map.ofEntries(pair);
pair.setValue(6);
~~~

**Question:** What is `counts.get("count")`? If `pair` were created with `Map.entry`, what would `setValue` do?

**Answer:** The map still returns 5, because it extracted the key/value from the entry at creation time and did not retain that entry as the mapping storage. If `Map.entry` were used, `setValue` would be rejected with `UnsupportedOperationException`. In both cases, do not use an input entry as an interface to update the resulting map.

### Exercise 7 — Can you write a fixed stdout assertion like this?

One test prints `Set.of("c", "a", "b")` directly and asserts the string must be `[c, a, b]`. Another test prints `Map.of("z", 1, "a", 2)` directly and asserts key `z` must come first.

**Question:** Which missing contract do both tests rely on? How should the checks be fixed?

**Answer:** The set/map factories do not guarantee that iteration order. Check set membership or map mappings using `equals`/`contains`/`get` and size. If an ordered string is genuinely needed, sort explicitly before printing; string data can use a `TreeSet`/`TreeMap` copy as in this lesson's program. If insertion order is a product requirement, choose an order-preserving structure from construction time.

### Exercise 8 — Why does a "read-only" map still change its observed data?

~~~java
List<String> modes = new ArrayList<>(List.of("fast"));
Map<String, List<String>> config = Map.of("modes", modes);
modes.add("safe");
~~~

**Question:** What does `config.get("modes")` contain? Is `config.put("modes", List.of("other"))` supported? If stable configuration values are needed, what should be changed?

**Answer:** The list value represents `[fast, safe]` because that list is shared. `put` on the map is rejected. If the model only contains strings, freeze the value list with `List.copyOf(modes)` **at the time it needs to be stored** and then pass it into the unmodifiable map; if the modes are already known beforehand, you can use `Map.of("modes", List.of("fast"))`. When elements still contain mutable objects, you must protect that layer as well, not just wrap the outer map.

A proper factory call aligns three things: the data shape is a sequence, a set, or a mapping; the arguments satisfy the `null` and duplicate policies; and consumers of the result understand the mutability and ordering guarantees. Concise syntax is only helpful once those three things are clear.
