# emptyList, singleton, nCopies, and Use Cases

Not every collection result needs a list built through multiple `add` calls. Some methods always return zero elements, exactly one element, or a single value repeated across multiple positions. The `java.util.Collections` utility class provides factory methods that directly express those data shapes.

The three names to recognize are `emptyList`, `singleton`, and `nCopies`. They do not have the same return type: `emptyList` returns an empty list; `singleton` returns a single-element **set**; `nCopies` returns a list with `n` positions all holding the passed element. Their relatives `singletonList` and `singletonMap` cover the single-element list and single-mapping map cases.

The most important part of this lesson is understanding mutability and reference sharing. `nCopies(3, object)` does not invoke the constructor three times and does not deep-clone the object. A result that disallows adding, removing, or replacing slots can still hold mutable objects.

The examples use Java 17 and require no external libraries. Familiarity with `List`, `Set`, `Map`, and object references is needed before running the program.

## 1. Choosing a Factory by Result Shape

Start with the meaning of the data to return or pass:

| Need | Suitable factory | Return type | Number of elements/mappings |
| --- | --- | --- | --- |
| No elements in a sequence | `Collections.emptyList()` | `List<T>` | 0 |
| No members in a set | `Collections.emptySet()` | `Set<T>` | 0 |
| No mappings | `Collections.emptyMap()` | `Map<K,V>` | 0 |
| One member of a set | `Collections.singleton(value)` | `Set<T>` | 1 |
| One element of a sequence | `Collections.singletonList(value)` | `List<T>` | 1 |
| One key–value pair | `Collections.singletonMap(key, value)` | `Map<K,V>` | 1 |
| The same element repeated at `n` positions | `Collections.nCopies(n, value)` | `List<T>` | `n` if `n >= 0` |

These are static factory methods. Callers work with the result through its interface type, without depending on the internal implementation class.

The documentation refers to these results as “immutable” collections. When applying them, understand the exact scope: the element/mapping structure of the result cannot be modified; the objects held inside are not automatically frozen or deep-copied. See the declarations and contracts in the [Collections API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

Do not choose based on method name length. If an API needs a list with index 0, `singleton` does not replace `singletonList` because the return type differs. If the goal is to have `n` independent new objects, `nCopies` does not meet that requirement even though its name contains the word “copies”.

## 2. `emptyList`: A List That Exists with Zero Elements

### Empty Differs from `null`

~~~java
List<String> result = Collections.emptyList();
~~~

This is illustrative code inside a method with all necessary imports. `result` is a valid list object with `size() == 0` and `isEmpty() == true`. It can be iterated over with a loop; the loop body will execute zero times.

`null`, on the other hand, means there is no list object on which to call methods. An API that promises to “return all labels found, possibly none” is usually expressed cleanly with an empty list. Callers can use the same iteration code for both non-empty and empty results.

Do not use an empty list to hide errors. If a query fails, data has not been loaded, or the caller lacks access permissions, turning every case into “no elements” can lose critical information. The API contract must distinguish necessary business states.

### Empty Does Not Mean a List for Appending Later

Intentionally wrong snippet:

~~~java
List<String> names = Collections.emptyList();
names.add("Lan"); // UnsupportedOperationException
~~~

If you need to accumulate names gradually, create `new ArrayList<>()`. If you need to return a result with no elements and prevent the receiver from adding to that result itself, `emptyList` expresses that intent clearly.

There is also no element at index 0. `emptyList.get(0)` does not return `null`; it throws `IndexOutOfBoundsException`. “Having no elements” is different from “having one element whose value is `null`”.

### Typed Even Without Elements

~~~java
List<String> a = Collections.emptyList();
List<String> b = Collections.<String>emptyList();
~~~

The first form uses target typing to infer `T`. The second specifies the type argument explicitly when context requires disambiguation. You do not need to put a dummy element into a list to help the compiler infer the type.

Prefer the generic method over the raw-type field `Collections.EMPTY_LIST` in new code. The raw field can lead to unchecked conversion warnings; `emptyList()` preserves type information in source code.

Do not check for an empty list using `result == Collections.emptyList()`. Implementations may reuse the same instance; the existence of instance reuse does not turn object identity into a business condition. Use `isEmpty()` when checking whether a list has elements.

### Two Common Relatives

~~~java
Set<String> noPermissions = Collections.emptySet();
Map<String, Integer> noOverrides = Collections.emptyMap();
~~~

The meaning of “empty” is the same in terms of count, but operations and equality contracts still follow each interface. An empty list and an empty set are not interchangeable types just because both have `size() == 0`.

## 3. `singleton`: A Single-Element Set, Not the Singleton Design Pattern

### The Method Name Refers to Element Count

~~~java
Set<String> requested = Collections.singleton("report");
~~~

A set with one member, `"report"`. It can often be passed to an API that accepts multiple codes when the current call only needs one.

The word “singleton” here does not claim there is only one instance across the entire application, does not prescribe a `getInstance` method, and does not turn the element into a global variable. It states that the resulting set has exactly one element.

If a method accepts `Set<String>`, this factory expresses a single-member requirement without creating a `HashSet` and calling `add`. If the method accepts `List<String>`, choose `singletonList` instead of trying to force a cast.

### `singletonList` Has Index 0

~~~java
List<String> oneStep = Collections.singletonList("validate");
~~~

A list of size 1 where `oneStep.get(0)` is `"validate"`. It does not allow replacing via `set(0, other)`, adding a second element, or removing the sole element.

Do not confuse this with a fixed-size list that still supports element replacement. “Single-element” by itself does not determine mutability; mutability here comes from the factory's contract.

### `singletonMap` Has One Mapping

~~~java
Map<String, String> override =
        Collections.singletonMap("mode", "fast");
~~~

A map with exactly one key `"mode"` mapped to `"fast"`. It does not allow `put` to replace the value or add another key.

Useful when passing a single option to an API that accepts a map, creating test data with one mapping, or publishing a single-entry lookup table. When options need to be updated later, create an appropriate mutable map instead of relying on the `Map` interface type and assuming `put` will succeed.

### The Element Can Still Be a Mutable Object

If `singletonList` holds a `StringBuilder`, calling `get(0).append(...)` mutates that object. If `singletonMap` holds a list as its value, that list can still receive elements through another reference.

The single-element structure does not change, but the observable internal state can. For set elements or map keys, take special care to keep data participating in `equals`/`hashCode` stable while the object is stored. This is a requirement of [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) and [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), and is not waived by having a size of one.

## 4. `nCopies`: Repeating an Element at Multiple Positions

### Count and Repeated Value

~~~java
List<String> states = Collections.nCopies(4, "pending");
~~~

The result has size 4. Every valid index from 0 to 3 returns the same passed element. When printed, it formats as `[pending, pending, pending, pending]`.

Rules for the count:

- `n > 0`: contains `n` elements.
- `n == 0`: empty list.
- `n < 0`: throws `IllegalArgumentException`.

Valid indices still follow `List`: `0 <= index < size()`. `nCopies(0, value)` has no index 0 even though a value was passed to the call.

The result does not support replacing elements with `set`. If each position needs to receive a different state later, create a working container from the initial data, as shown in the next section.

### “Copies” Does Not Mean Calling the Constructor Multiple Times

Consider:

~~~java
List<StringBuilder> buffers =
        Collections.nCopies(3, new StringBuilder("start"));
~~~

The expression `new StringBuilder("start")` is evaluated once to produce the argument. `nCopies` receives that single reference and exposes it at three positions.

The relationship can be illustrated as:

~~~text
index 0 ─┐
index 1 ─┼──> the same StringBuilder("start")
index 2 ─┘
~~~

There are not three different `StringBuilder` instances. Mutating through `buffers.get(0)` will be observed when reading positions 1 and 2 because all three point to the same object.

For a `String` or an already immutable value, sharing a reference is usually desirable. For buffers, sublists, session objects, or cells with setters, this easily causes unintended shared-state bugs.

### Compact Representation Does Not Eliminate the Cost of Subsequent Steps

The API describes the internal representation of `nCopies` as small, holding only a single reference to the element. Therefore, do not assume it always allocates an array of `n` references upon invocation. [nCopies API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#nCopies(int,T)).

However, if you later iterate over every position, convert to an array, or create an `ArrayList` containing all `n` positions, those steps still have to process data proportional to the work they perform. A compact repeated representation does not guarantee that all subsequent operations are cheap or allocation-free.

The demonstration program creates a repeated list with one million positions but only prints `size` and reads the last position. It does not print all one million elements and does not create a large copy to demonstrate this concept.

## 5. Creating Initial Slots for a Mutable List

An application might need four status slots initialized to `"pending"`, then update individual slots and append new ones.

~~~java
List<String> slots =
        new ArrayList<>(Collections.nCopies(4, "pending"));

slots.set(2, "done");
slots.add("extra");
~~~

`nCopies` supplies the initial data; the `ArrayList(Collection)` constructor creates a new container holding those elements. The new container supports `set` and `add`.

There is no change to the mutability of the source list. The source list created by `nCopies` remains unmodifiable; the `ArrayList` instance is a separate container.

The constructor copies elements in the iteration order of the source collection. For mutable elements, references are still shared; creating a new list does not recreate each element. [ArrayList constructors, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### How This Differs from Only Setting Capacity

~~~java
List<String> reserved = new ArrayList<>(4);
~~~

The argument `4` in this constructor is the initial capacity, not the number of existing elements. `reserved.size()` is still 0. Therefore, `reserved.set(2, "done")` has no index 2 to replace.

Comparison:

| Expression | Initial `size()` | Replace with `set(0, ...)` | Can append? |
| --- | --- | --- | --- |
| `new ArrayList<String>(4)` | 0 | No index 0 yet | Yes |
| `Collections.nCopies(4, "pending")` | 4 | Not supported | No |
| `new ArrayList<>(Collections.nCopies(4, "pending"))` | 4 | Yes | Yes |

An alternative is creating an empty list and calling `add` the required number of times. The choice depends on whether you genuinely need “already-existing slots” or merely want to reserve memory for gradual additions.

Do not use `nCopies` merely to increase capacity when initial elements are not needed; it also changes the `size` of the copy when used to initialize an `ArrayList`.

## 6. Padding Data and Interacting with List Algorithms

### Appending the Same Value Multiple Times with `addAll`

~~~java
List<String> columns = new ArrayList<>(List.of("Ada", "Lin"));
columns.addAll(Collections.nCopies(2, "-"));
~~~

The target list becomes `[Ada, Lin, -, -]`. The repeated data only serves as a source for `addAll`; the target list must support appending.

If you want to pad up to a target length, calculate the **number of missing slots**, and do not mistakenly pass the total desired length:

~~~java
int targetSize = 6;
int missing = targetSize - columns.size();
if (missing > 0) {
    columns.addAll(Collections.nCopies(missing, "-"));
}
~~~

This snippet only appends when slots are missing; it does not truncate if the list is already longer than the target. If an exact length is required, the longer case must be handled by a separate business rule.

For size inputs coming from outside, validate bounds meaningful to the application before creating many elements. Do not convert every negative number to 0 if a negative number is actually a configuration error that should be reported.

### `Collections.copy` Requires Existing Slots and Slot Replacement Support

`Collections.copy(dest, src)` replaces destination elements by index; it does not call `add` to grow the destination list. `dest.size()` must be at least `src.size()`, and the destination must support element replacement.

Thus, two independent errors can occur:

1. `new ArrayList<>(source.size())` has capacity but `size` is 0: there are not enough slots yet, so it is not a valid destination for copying a non-empty source.
2. `Collections.nCopies(source.size(), initial)` has enough slots but does not allow replacement, so it is not a valid destination either.

A suitable setup for this experiment:

~~~java
List<String> source = List.of("A", "B", "C");
List<String> destination =
        new ArrayList<>(Collections.nCopies(source.size(), "?"));

Collections.copy(destination, source);
~~~

The destination result is `[A, B, C]`. If you simply want a new copy right away, `new ArrayList<>(source)` is simpler. Using `copy` here illustrates the requirements of the in-place replacement algorithm and the role of initialized slots.

`Collections.copy` is also not a deep-cloning operation for elements; it transfers element values into the destination positions according to the list contract.

### `nCopies` and `fill` Solve Two Different Problems

`nCopies` creates a list representing repetition. `Collections.fill(existing, value)` replaces elements at the existing positions of an already-present list. `fill` does not change `size` from 0 to `n`.

If the list is currently empty, calling `fill` does not create slots. If the list does not support element replacement, calling `fill` to actually change data is not a way around mutability restrictions. Choose the factory or algorithm based on the operation you need to perform, not on a vague idea of “filling values”.

## 7. Nested List Trap: Multiple Positions Sharing One Row

A tempting idea when creating a three-row table:

~~~java
List<List<String>> rows = new ArrayList<>(
        Collections.nCopies(3, new ArrayList<String>()));
~~~

The outer list is an `ArrayList`, so it is mutable. However, the three inner elements are all the **same** `ArrayList<String>`. The outer copy wrapper does not change this reference relationship.

~~~java
rows.get(0).add("X");
~~~

After this call, printing `rows` outputs `[[X], [X], [X]]`. It is not that a loop inside `add` modified three rows. Only one row actually exists, and it is visible through three positions.

To get three independent rows, create a row object on each iteration:

~~~java
List<List<String>> rows = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    rows.add(new ArrayList<>());
}
~~~

Now adding `"X"` to the first row produces `[[X], [], []]`.

The decisive factor is **where the new-object creation call is placed**. It must execute separately for each element. Wrapping the outer list with `new ArrayList<>(...)` or repeatedly calling a method that still returns the same child object is not enough.

The same bug pattern also appears when creating multiple buffers from one `StringBuilder`, multiple shopping carts from one cart object, or multiple editable configs from the same config instance with setters. Before using `nCopies`, decide whether sharing the element is intentional or a bug.

If the rows are finalized, unmodifiable data, sharing can be completely appropriate. “Same reference” is not inherently a bug; the bug lies in needing independence while allowing shared updates.

## 8. `null`, Types, and Differences from `of`

### These Small Factories Can Hold `null`

All of the following can be created:

~~~java
Set<String> oneNull = Collections.singleton(null);
List<String> nullItem = Collections.singletonList(null);
Map<String, String> nullPair = Collections.singletonMap(null, null);
List<String> nullSlots = Collections.nCopies(3, null);
~~~

`nullItem` has size 1, not 0. `nullSlots` has size 3. `nullPair` has one mapping with a `null` key and a `null` value.

With maps, `get(null) == null` by itself does not distinguish an absent key from a `null` value; use `containsKey` if you need to determine whether a mapping exists. The program prints both pieces of information.

Being able to hold `null` does not mean `null` should be used in every model. Use it only when the element contract and downstream processing clearly understand its meaning.

### Switching to Newer Factories Can Change Behavior

The following expressions do not share the same `null` policy:

| Factory | With a `null` element |
| --- | --- |
| `Collections.singletonList(null)` | Creates a list of size 1 |
| `List.of((String) null)` | `NullPointerException` |
| `Collections.singleton(null)` | Creates a set of size 1 |
| `Set.of((String) null)` | `NullPointerException` |
| `Collections.singletonMap(null, null)` | Creates a single mapping |
| `Map.of((String) null, (String) null)` | `NullPointerException` |

`List.of`, `Set.of`, and `Map.of` reject `null` according to their own contracts. Therefore, migrating legacy code from these small factories to `of` requires checking input data; do not treat it as a behavior-neutral syntax swap. [List.of contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable), [Set.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable), [Map.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

Similarly, `List.copyOf(nullItem)` is rejected because the source contains a `null` element. A list that is valid with one factory is not guaranteed to be valid when passed to another.

### Generics May Need to Be Specified Explicitly

In many places using `null` or empty results, target typing helps the compiler infer the desired type:

~~~java
List<String> slots = Collections.nCopies(3, null);
List<String> explicit = Collections.<String>nCopies(3, null);
~~~

Both describe a list of strings according to the declared type. Raw-type casts are not needed to accomplish this.

It is also important to identify what the element actually is. `Collections.singletonList(array)` always creates a list with one element—the passed array itself; it has no varargs overload to treat each array slot as a separate element. Use `Arrays.toString` when printing that array's contents rather than guessing from the default string representation of an array object.

## 9. Runnable Demonstration Program

Save all the code into **`SmallCollectionsDemo.java`**. The `rejects` helper only accepts the exact expected exception type. If the operation unexpectedly succeeds or throws a different type, the program stops with an `AssertionError`.

All mutability checks target real modifications: adding an element to an empty list, replacing an existing element, or replacing a mapping. The program does not use no-op calls such as `clear` on an already empty list to infer the contract.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SmallCollectionsDemo {
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

    private static List<String> labelsFor(boolean enabled) {
        if (!enabled) {
            return Collections.emptyList();
        }
        return Collections.singletonList("active");
    }

    public static void main(String[] args) {
        List<String> empty = Collections.emptyList();
        System.out.println("empty.isEmpty=" + empty.isEmpty());
        System.out.println("empty.family.sizes="
                + empty.size() + "/"
                + Collections.emptySet().size() + "/"
                + Collections.emptyMap().size());
        rejects("empty.add", UnsupportedOperationException.class,
                () -> empty.add("x"));
        rejects("empty.get", IndexOutOfBoundsException.class,
                () -> empty.get(0));

        Set<String> oneSet = Collections.singleton("solo");
        List<String> oneList = Collections.singletonList("solo");
        Map<String, String> oneMap =
                Collections.singletonMap("mode", "fast");
        System.out.println("singleton.set=" + oneSet);
        System.out.println("singleton.list=" + oneList);
        System.out.println("singleton.map=" + oneMap);
        rejects("singleton.add", UnsupportedOperationException.class,
                () -> oneSet.add("other"));
        rejects("singletonList.set", UnsupportedOperationException.class,
                () -> oneList.set(0, "other"));
        rejects("singletonMap.put", UnsupportedOperationException.class,
                () -> oneMap.put("mode", "safe"));

        Set<String> nullSet = Collections.singleton(null);
        List<String> nullList = Collections.singletonList(null);
        Map<String, String> nullMap =
                Collections.singletonMap(null, null);
        System.out.println("null.set.contains=" + nullSet.contains(null));
        System.out.println("null.list=" + nullList);
        System.out.println("null.map.containsKey=" + nullMap.containsKey(null));
        System.out.println("null.map.value=" + nullMap.get(null));

        List<String> repeated = Collections.nCopies(3, "idle");
        System.out.println("repeat=" + repeated);
        System.out.println("repeat.size=" + repeated.size());
        rejects("repeat.set", UnsupportedOperationException.class,
                () -> repeated.set(1, "done"));
        System.out.println("repeat.zero.size="
                + Collections.nCopies(0, "unused").size());
        rejects("repeat.negative", IllegalArgumentException.class,
                () -> Collections.nCopies(-1, "idle"));
        System.out.println("repeat.null="
                + Collections.<String>nCopies(2, null));

        StringBuilder shared = new StringBuilder("start");
        List<StringBuilder> aliases = Collections.nCopies(3, shared);
        System.out.println("repeat.shared="
                + (aliases.get(0) == aliases.get(2)));
        aliases.get(0).append("!");
        System.out.println("repeat.afterEdit=" + aliases);

        List<String> slots =
                new ArrayList<>(Collections.nCopies(4, "pending"));
        slots.set(2, "done");
        slots.add("extra");
        System.out.println("slots=" + slots);

        List<String> padded = new ArrayList<>(List.of("Ada", "Lin"));
        padded.addAll(Collections.nCopies(2, "-"));
        System.out.println("padding=" + padded);

        List<String> source = List.of("A", "B", "C");
        List<String> capacityOnly = new ArrayList<>(3);
        System.out.println("capacity.size=" + capacityOnly.size());
        rejects("capacity.copy", IndexOutOfBoundsException.class,
                () -> Collections.copy(capacityOnly, source));
        List<String> destination =
                new ArrayList<>(Collections.nCopies(3, "?"));
        Collections.copy(destination, source);
        System.out.println("copy.destination=" + destination);
        rejects("copy.readonlyDestination", UnsupportedOperationException.class,
                () -> Collections.copy(
                        Collections.nCopies(3, "?"), source));

        List<List<String>> sharedRows = new ArrayList<>(
                Collections.nCopies(3, new ArrayList<String>()));
        sharedRows.get(0).add("X");
        System.out.println("grid.shared=" + sharedRows);

        List<List<String>> independentRows = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            independentRows.add(new ArrayList<>());
        }
        independentRows.get(0).add("X");
        System.out.println("grid.independent=" + independentRows);

        List<String> compact = Collections.nCopies(1_000_000, "same");
        System.out.println("compact.size=" + compact.size());
        System.out.println("compact.last=" + compact.get(999_999));

        System.out.println("return.none=" + labelsFor(false));
        System.out.println("return.one=" + labelsFor(true));
        rejects("List.of.null", NullPointerException.class,
                () -> List.of((String) null));
        rejects("List.copyOf.null", NullPointerException.class,
                () -> List.copyOf(nullList));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 SmallCollectionsDemo.java
java SmallCollectionsDemo
~~~

JDK 17 or newer is required for this compile command. `--release 17` restricts syntax and APIs to Java 17; the code was compiled with that option and run on OpenJDK 24.0.2, exiting successfully. Exact stdout:

~~~text
empty.isEmpty=true
empty.family.sizes=0/0/0
empty.add=UnsupportedOperationException
empty.get=IndexOutOfBoundsException
singleton.set=[solo]
singleton.list=[solo]
singleton.map={mode=fast}
singleton.add=UnsupportedOperationException
singletonList.set=UnsupportedOperationException
singletonMap.put=UnsupportedOperationException
null.set.contains=true
null.list=[null]
null.map.containsKey=true
null.map.value=null
repeat=[idle, idle, idle]
repeat.size=3
repeat.set=UnsupportedOperationException
repeat.zero.size=0
repeat.negative=IllegalArgumentException
repeat.null=[null, null]
repeat.shared=true
repeat.afterEdit=[start!, start!, start!]
slots=[pending, pending, done, pending, extra]
padding=[Ada, Lin, -, -]
capacity.size=0
capacity.copy=IndexOutOfBoundsException
copy.destination=[A, B, C]
copy.readonlyDestination=UnsupportedOperationException
grid.shared=[[X], [X], [X]]
grid.independent=[[X], [], []]
compact.size=1000000
compact.last=same
return.none=[]
return.one=[active]
List.of.null=NullPointerException
List.copyOf.null=NullPointerException
~~~

### Matching Output Against Mechanics

**`empty.isEmpty` and `empty.family.sizes`:** valid containers exist, all with an element/mapping count of 0. `empty.add` is blocked; `empty.get` shows that an empty list has no index 0.

**Three `singleton` lines:** the name `singleton` does not imply a list by itself. Set, list, and map are created by three distinct methods. All actual mutating operations are rejected.

**`null` group:** a set containing `null` can still look up the `null` member; a list containing one `null` element still has one position. A map with a `null` key returns `null` as its value, while `containsKey` confirms the mapping exists.

**`repeat` group:** counts of 3, 0, and negative values are tested separately. The repeated list allows `null`, but does not allow `set`. The `==` comparison between two elements in this experiment verifies the shared-reference relationship created by `nCopies`; it is not meant for predicting the identity of the factory list instances themselves.

**`repeat.afterEdit`:** the same `StringBuilder` changed to `"start!"`, so all three positions display the new text. No call replaced a slot in the list.

**`slots` and `padding`:** repeated data is used to initialize or append to a mutable target list. String values are shared safely because there is no operation that mutates string contents.

**`capacity` and `copy`:** allocating capacity alone does not create elements. The `ArrayList` with initialized slots receives the source data; the `nCopies` list used directly as a destination does not support slot replacement.

**Two `grid` lines:** copying the outer list does not clone the sublists. Only the loop creating `new ArrayList<>()` per iteration yields independent rows in this example.

**`compact`:** the repeated list represents one million positions, but the experiment only reads two small pieces of information. Do not infer from this that converting the entire list to an array or printing all elements has the same cost.

**`return.none` and `return.one`:** an API with 0 or 1 result elements can return a valid collection in both branches. The final two exception lines show that a list containing `null` cannot be passed directly to the non-`null` policy of `List.of`/`List.copyOf`.

## 10. Real-World Use Cases

### Returning No Results While Preserving the Collection Contract

An analyzer may find multiple warnings or none at all. If the API promises to return a list and disallows modifying the result, the no-warnings branch can return `Collections.emptyList()`.

Keep the contract consistent across branches. If the empty branch disallows adding, while the non-empty branch returns an internal `ArrayList` directly, callers may accidentally depend on mutability varying with the data.

Not every API should be forced to return a collection. If the business logic is “one object present or absent,” a type representing absence may be clearer. `emptyList` and `singletonList` make sense when the API is genuinely designed to process a sequence of results, including sequences of 0 or 1 element.

### Passing Exactly One Value to an API Expecting Multiple Values

An API searching by a set of codes can accept `Collections.singleton(code)`. An API processing a sequence of steps can accept `Collections.singletonList(step)`. An API accepting options can accept `Collections.singletonMap(key, value)`.

The condition is that the receiving API respects read-only access and does not attempt to add/remove on the input. A parameter typed as `Collection` or `List` does not by itself promise mutability.

If a method needs to mutate data for its own computation, it should create an appropriate working copy or clearly document a mutable-input requirement. Clear contracts save callers from having to guess internal list types.

### Repeated Data for Initialization and Formatting

`nCopies` is suitable for creating initial slots with the same immutable value, appending padding to a sequence, or supplying repeated data to read-only algorithms.

If slots will later receive different values, create a mutable list copy from the repeated data. If each slot will hold its own stateful object, construct each object independently rather than using `nCopies` as an object generator.

### Meaningful Test Data

Empty, single-element, and repeated shapes help test algorithm boundaries. Choose repeated values according to your goal:

- If you want to test handling multiple positions with the same value, `nCopies` can be appropriate.
- If you want to test multiple objects that are equal in data but distinct in reference, you must construct multiple objects.
- If you want to test independent state changes per element, you definitely must not use a single shared repeated object.

A test with the wrong reference relationship can hide bugs or produce behavior that does not represent real data.

## 11. Common Mistakes and How to Reason About Them

### “Singleton Means a System-Wide Unique Instance”

Here it means one element in the resulting collection. Element count is not allocation count, not a design pattern, and not global ownership.

### “With Only One Element, `set` Must Work”

Support for `set` comes from the specific list contract. `singletonList` and `nCopies` are not lists that merely block resizing while still allowing element replacement.

If replacement is needed, use a mutable working copy. Do not try casting to another class to bypass the contract.

### “Empty Means One `null` Slot”

`emptyList()` has `size() == 0`. `singletonList(null)` has `size() == 1`. `nCopies(3, null)` has `size() == 3`. These are three different shapes and affect every loop, indexed access, and downstream algorithm.

### “Creating an Outer `ArrayList` Makes Every Element Independent”

The list constructor copies element references. In the nested-row case, it still keeps multiple references to the same row. Independence requires designing the element creation/copying step properly.

### “No Exception on a No-Op Means It Is Mutable”

Some optional operations or mutating algorithms may not throw an exception when a call produces no actual change. Do not use `clear` on an empty list, removing an absent element, or sorting already-sorted data as a way to detect mutability.

The `Collections` documentation notes that mutating algorithms may or may not throw when a call has no effect. Rely on the API contract and the actual operations required by the problem.

### “Unmodifiable Means All Shared Data Is Thread-Safe”

A `singletonList` holding an object being mutated, or `nCopies` repeating a stateful object, still shares that state. The list disallowing slot replacement does not coordinate writes to the element.

If you need to share stable data, choose immutable elements or apply an appropriate coordination mechanism for mutable data. The distinction between container and elements is explained in [Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

### “Having Size `n` Means Every Operation Matches an `ArrayList` of Size `n`”

Two structures can be equal in elements under `equals` while differing in mutability and internal representation. Do not write code that depends on internal class names or expects every operation to have the same cost.

Even a compact repeated list can cause significant work if you export its entire contents or materialize every position. Choose algorithms based on actual operations.

## 12. Practice Exercises with Answers

### Exercise 1 — Are Three Forms of “No Data” the Same?

Compare:

~~~java
List<String> a = Collections.emptyList();
List<String> b = Collections.singletonList(null);
List<String> c = Collections.nCopies(3, null);
~~~

**Question:** What is the size of each list? Which lists can call `get(0)` without an index error?

**Answer:** Their sizes are 0, 1, and 3, respectively. `a.get(0)` throws `IndexOutOfBoundsException`; both `b.get(0)` and `c.get(0)` return `null`. Having a `null` element still means having a position in the sequence, unlike an empty sequence.

### Exercise 2 — Needing a List for an Indexed API

A method accepts `List<String>` and reads the element at index 0 after checking the size.

**Question:** Can `Collections.singleton("x")` be passed directly? Which factory from this lesson has the right type?

**Answer:** No, because `singleton` returns `Set<String>`. Use `Collections.singletonList("x")`. Do not force a set into a list just because it has one element; the type and access contract differ.

### Exercise 3 — Do Two Positions Have Two Buffers?

~~~java
List<StringBuilder> items =
        Collections.nCopies(2, new StringBuilder("a"));
items.get(1).append("b");
~~~

**Question:** When reading the text at positions 0 and 1, what do you see? Was a slot in the list replaced?

**Answer:** Both display `"ab"` because they hold the same `StringBuilder`. No slot was replaced; the shared object changed state. If two independent buffers are needed, call `new StringBuilder("a")` separately for each element when building the list.

### Exercise 4 — Capacity Is Not Size

~~~java
List<String> a = new ArrayList<>(5);
List<String> b =
        new ArrayList<>(Collections.nCopies(5, "pending"));
~~~

**Question:** Do `a.set(4, "done")` and `b.set(4, "done")` produce the same result?

**Answer:** No. `a` is still empty, so index 4 does not exist and it throws `IndexOutOfBoundsException`. `b` has 5 real elements and supports replacement, so `set` succeeds. If you only need to append gradually, `a` makes sense; if you need existing positions, you must create the elements as in `b` or add enough elements in a loop.

### Exercise 5 — Does Copying the Outer List Fix the Shared-Row Bug?

~~~java
List<List<Integer>> grid = new ArrayList<>(
        Collections.nCopies(2, new ArrayList<Integer>()));

grid.get(0).add(7);
~~~

**Question:** What is the resulting representation of `grid`? Write how to create two independent rows.

**Answer:** The result is `[[7], [7]]`. The new outer list does not clone the row. You can create them as follows inside a method:

~~~java
List<List<Integer>> grid = new ArrayList<>();
for (int i = 0; i < 2; i++) {
    grid.add(new ArrayList<>());
}
~~~

With this setup, adding `7` to the first row produces `[[7], []]`.

### Exercise 6 — Padding to a Target Length

A list already has 3 elements; you want to append `"-"` so it has 8 elements.

**Question:** Should you pass 8 or 5 to `nCopies` in `addAll`? What if the list currently has 10 elements?

**Answer:** Pass the missing count, 5. Passing 8 would make the list 11 elements long. If it already has 10, the “pad only when short” snippet adds nothing; truncating to 8 requires a separate requirement and operation. Do not let a negative number enter `nCopies` and rely on the exception as normal branch control.

### Exercise 7 — What Does `Collections.copy` Need in a Destination?

The source has three strings. There are two destination candidates:

~~~java
List<String> a = new ArrayList<>(3);
List<String> b = Collections.nCopies(3, "?");
~~~

**Question:** Why are neither suitable? What is a suitable way to create the destination?

**Answer:** `a` has size 0, so it has no slots to receive data; `b` has size 3, but does not allow slot replacement. You can use `new ArrayList<>(Collections.nCopies(3, "?"))` to have both enough slots and mutability. If you simply want to create a copy of the source right away, `new ArrayList<>(source)` is simpler than preparing slots and calling `Collections.copy`.

### Exercise 8 — Does Switching to `List.of` Always Preserve Behavior?

A method has a contract that accepts a `null` element and currently returns `Collections.singletonList(value)`. A proposed change plans to replace it with `List.of(value)`.

**Question:** What must be checked before making the replacement? Can the fact that both are unmodifiable be used as proof of equivalence?

**Answer:** You must check the `null` policy. When `value == null`, the old approach returns a list of size 1, whereas the new approach throws `NullPointerException`. Having the same container mutability does not prove that all behavior is identical. If you want to change the contract to disallow `null`, it must be handled as an intentional API change with callers updated accordingly.

When using these small factories, clearly identify the required number of elements, the collection type to return, and whether elements are shared or must be independent. Those three pieces of information distinguish a concise, fit-for-purpose result from a list that looks plausible but has the wrong mutability or reference relationship.
