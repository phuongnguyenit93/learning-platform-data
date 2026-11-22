# checkedCollection, checkedList, checkedSet, and checkedMap

## 1. Checking Types Right Where Data Enters

A variable declared as `List<String>` tells the reader that the list holds strings. In a program that uses generics properly, the compiler helps enforce this: a call to add an `Integer` to this list will not compile. The problem arises when the list passes through legacy code using raw types, unchecked casts, or a library that does not respect the type declaration.

Suppose a library receives a list of usernames as a raw `List` and adds the number `42`. An `ArrayList` does not remember on its own that its original type argument was `String`. The invalid write can succeed; the error only surfaces when another piece of code reads the element and uses it as a string. The stack trace then points to the read site, making it harder to find where the invalid write occurred.

The methods `Collections.checkedCollection`, `checkedList`, `checkedSet`, and `checkedMap` create a **dynamically typesafe view**. When incompatible data is inserted through the view, the operation is blocked with a `ClassCastException`. The practical goal is to pull the failure closer to the invalid write site, where it is still clear which component supplied the data.

In this lesson:

- **Backing collection/map** actually holds the elements or mappings.
- **Wrapper** is the object returned by the `checked...` method; it forwards operations to the backing structure after performing the required check.
- **Type token** is a `Class` object such as `String.class` or `Integer.class`.
- **Heap pollution** is a situation where a variable of a parameterized type refers to an object/data that is not actually of that parameterized type.

The write flow to keep in mind:

```text
Caller code
  -> checked view, holding the type token
  -> checks the element / key / value about to be written
  -> operates on the backing structure

Writing directly to the backing structure
  -> bypasses the view's check
```

The view still shares data with the backing structure. It does not make a copy, does not synchronize access on its own, and does not make element objects immutable. Therefore, the task here is to guard a data-write boundary against type mismatches, which is tied to how references pointing to that same structure are managed. The [`checkedCollection` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedCollection(java.util.Collection,java.lang.Class)) directly describes the library integration and type-error tracing use case.

## 2. Choosing the Right Method for the Contract to Keep

The signatures below are shortened for readability; these are API declarations, not a standalone runnable program:

```java
static <E> Collection<E> checkedCollection(Collection<E> c, Class<E> type);
static <E> List<E> checkedList(List<E> list, Class<E> type);
static <E> Set<E> checkedSet(Set<E> s, Class<E> type);
static <K, V> Map<K, V> checkedMap(
        Map<K, V> map, Class<K> keyType, Class<V> valueType);
```

| Method | Result seen by caller | Data checked on write | When to choose |
| --- | --- | --- | --- |
| `checkedCollection` | `Collection<E>` | Element | Only a general collection interface is needed |
| `checkedList` | `List<E>` | Added or replaced element | Index access, `set`, `ListIterator`, or `subList` is needed |
| `checkedSet` | `Set<E>` | Element inserted into the set | Set semantics and `Set` equality contract must be preserved |
| `checkedMap` | `Map<K,V>` | Key and value; including replaced values | Key–value mapping must be preserved |

The chosen method determines the interface of the wrapper. Wrapping an `ArrayList` with `checkedCollection` does not produce a `List` just because the backing structure is a list. The caller must not cast that result to `List` to call `get` or `set`. If the contract requires a list, create it with `checkedList` from the start.

Similarly, assigning the result of `checkedList` to a `Collection<String>` variable only narrows the methods callable through that variable; the object is still a `List` view. The two situations—"choosing the general wrapper factory method" and "declaring a variable with a superinterface"—have different effects.

### 2.1. Differences in equals and hashCode

`Collection` does not specify a general content-comparison rule that applies simultaneously to both lists and sets. `List` compares by element sequence; `Set` has the set contract. Therefore, `checkedCollection` uses `Object`-based equality and hash code, and does not forward `equals` and `hashCode` to the backing structure.

For example, two general collection views containing the same sequence of numbers are not equal for that reason. Conversely, a view created with `checkedList` must still satisfy the `List` equality contract, and `checkedSet` must satisfy the `Set` contract. Choose the wrapping method according to the interface you actually need to provide; do not use `checkedCollection` as a completely equivalent substitute for all three types.

This is also why you should not infer that a wrapper "forwards every single method identically" just because its `toString` looks like the backing data.

## 3. How Generics and Class Work Together

Generics detect errors based on the types the compiler sees. The type token provides an additional check at runtime. The two layers of checking serve different points in time.

The following illustration intentionally contains a line that does not compile; do not use it as a standalone runnable file:

```java
List<String> names =
        Collections.checkedList(new ArrayList<>(), String.class);

names.add("Mai");   // Valid.
names.add(42);      // Compile-time error: 42 is not a String.
```

In raw-typed code, a call adding a number can pass static checking with a warning. The wrapper still holds `String.class`, so the runtime check remains in effect. Casting the wrapper variable to a raw type does not make the wrapper object disappear.

### 3.1. "Right Type" Means Assignment-Compatible, Not the Exact Same Concrete Class

A `Collection<Number>` wrapped with `Number.class` can accept `Integer`, `Double`, and other compatible subtypes. A collection wrapped with `CharSequence.class` can accept `String` or `StringBuilder`.

The condition is not `value.getClass() == type`. A more accurate model for non-`null` values is the `type.isInstance(value)` test. [`Class.isInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isInstance(java.lang.Object)) describes accepting subtypes and interface implementations.

This explains two different outcomes:

- `Number.class` accepts an `Integer` object holding the value `7`.
- `Integer.class` does not accept a `Long` object holding the value `7L`, even though the two numbers have the same mathematical value.

The wrapper does not parse strings, convert `Long` to `Integer`, or check whether a number is positive or negative. Conversions and business rules must be handled at the data-ingestion layer.

### 3.2. Choosing Integer.class Instead of int.class

Collections hold references to objects. For `List<Integer>`, pass `Integer.class`. The value `7` in `add(7)` is boxed into an `Integer` before reaching the method.

A surprising detail is that the expression `int.class` can still be passed to a call inferring `Class<Integer>`. However, that class object represents the primitive type `int`, not the `Integer` class. `int.class.isInstance(...)` always returns `false`; the wrapper therefore rejects boxed number objects. The third program will demonstrate this situation. Do not use a primitive type token as a shorthand for a wrapper-class token.

### 3.3. Null Is a Separate Policy

A valid `Class` object does not by itself create a rule forbidding `null`. When the backing structure allows `null`, a standard type-checked view still allows `null` elements; a map may also allow `null` keys or values according to the backing map's policy.

Consequently:

- `checkedList(new ArrayList<>(), String.class)` can accept `null`.
- When wrapping a backing structure that already forbids `null`, the wrapper does not lift that prohibition.
- Passing `null` as the collection/map argument itself, or passing `null` as the type token, throws `NullPointerException` when creating the wrapper.
- With `Map.merge`, the incoming value argument is also governed by `merge`'s own contract; a map that allows storing `null` does not mean every method accepts a `null` argument in the same way.

You cannot infer "this list has no null values" from the name `checkedList`. If the business domain forbids `null`, that constraint must be validated when receiving data.

## 4. All Write Paths Must Go Through the Wrapper

For a `List`, writing data is not limited to `add`. There are also `set`, `add(index, value)`, `addAll`, `ListIterator.add`, `ListIterator.set`, and modifications through `subList`. A wrapper that properly enforces the contract must guard the type boundary across all of these paths.

For a `Set`, an element must still pass the type check before it can be accepted into the set. Duplicate-element rules continue to belong to the set. `checkedSet` does not turn the result of `add` into "always added successfully" and does not impose a new iteration order.

For a `Map`, a new mapping requires both the key and the value to match. Updating the value of an existing key must also be checked. In particular, `Map.Entry.setValue` on an entry obtained from `checkedMap.entrySet()` must not become a bypass around the check.

Methods that accept a callback can also produce new data to write. For example:

| Operation | Result to watch |
| --- | --- |
| `List.replaceAll` | Element returned by the transformation function |
| `Map.compute`, `computeIfAbsent`, `computeIfPresent` | Computed value if the operation will write a mapping |
| `Map.merge` | Input value and merged value to be stored |
| `Map.replaceAll` | Replacement value returned by the callback |
| `Map.Entry.setValue` | New value entering the entry |

With properly typed callbacks, the compiler already helps prevent many mismatches. If raw-typed code causes a callback to return an object of the wrong type, the wrapper must still block that data when it is about to be written. This does not mean the wrapper controls every side effect of the callback: the callback may already have logged, mutated another object, or performed an external action before its result is rejected.

Do not confuse type constraints with mutability permissions. Wrapping an unmodifiable list with `checkedList` does not make it support `add`. A type-valid operation can still fail with `UnsupportedOperationException`, an invalid index, a limit of the backing structure, or its comparison rules. When a call violates multiple conditions, do not build control flow on assumptions about exception precedence.

The [`List` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html) and [`Map.Entry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html) help distinguish update operations, optional operations, and entry objects tied to a map.

## 5. Program 1: Collection, List, and Set

This program uses deterministic ordering so the output is easy to compare. `LinkedHashSet` is chosen to preserve insertion order; this is a property of the chosen backing structure, not an ordering feature of `checkedSet`.

Raw-type variables and `@SuppressWarnings` are used solely for the experiment simulating legacy code. The program still halts with `AssertionError` if a case expected to be blocked is accepted instead.

File `CheckedViewsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.ListIterator;
import java.util.Set;

public class CheckedViewsDemo {
    private static void rejected(String label, Runnable action) {
        try {
            action.run();
        } catch (ClassCastException expected) {
            System.out.println(label + "=ClassCastException");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("first"));
        List<String> checked = Collections.checkedList(source, String.class);
        List rawList = checked;
        rejected("list.add", () -> rawList.add(42));
        rejected("list.set", () -> rawList.set(0, 42));

        ListIterator rawIterator = checked.listIterator();
        rawIterator.next();
        rejected("iterator.set", () -> rawIterator.set(42));
        rejected("iterator.add", () -> rawIterator.add(42));

        List rawSubList = checked.subList(0, 1);
        rejected("subList.add", () -> rawSubList.add(42));
        checked.set(0, "updated");
        checked.add(null);
        source.add("owner");
        System.out.println("list=" + checked);
        System.out.println("listEquals=" +
                checked.equals(java.util.Arrays.asList("updated", null, "owner")));

        Collection<Number> numbers = Collections.checkedCollection(
                new ArrayList<>(), Number.class);
        numbers.add(7);
        numbers.add(2.5);
        Collection rawNumbers = numbers;
        rejected("collection.add", () -> rawNumbers.add("7"));
        System.out.println("numbers=" + numbers);
        System.out.println("genericCollectionEqualsList=" +
                numbers.equals(List.of(7, 2.5)));

        Set<String> tags = Collections.checkedSet(
                new LinkedHashSet<>(), String.class);
        System.out.println("set.addFirst=" + tags.add("java"));
        System.out.println("set.addDuplicate=" + tags.add("java"));
        Set rawSet = tags;
        rejected("set.add", () -> rawSet.add(42));
        System.out.println("set=" + tags);
        System.out.println("setEquals=" + tags.equals(Set.of("java")));

        Collection<CharSequence> texts = Collections.checkedCollection(
                new ArrayList<>(), CharSequence.class);
        StringBuilder builder = new StringBuilder("a");
        texts.add(builder);
        builder.append("b");
        System.out.println("elementCanChange=" + texts);
    }
}
```

Compile and run in the directory containing the file, using a JDK supporting Java 17 or later:

```shell
javac --release 17 -encoding UTF-8 CheckedViewsDemo.java
java CheckedViewsDemo
```

Output:

```text
list.add=ClassCastException
list.set=ClassCastException
iterator.set=ClassCastException
iterator.add=ClassCastException
subList.add=ClassCastException
list=[updated, null, owner]
listEquals=true
collection.add=ClassCastException
numbers=[7, 2.5]
genericCollectionEqualsList=false
set.addFirst=true
set.addDuplicate=false
set.add=ClassCastException
set=[java]
setEquals=true
elementCanChange=[ab]
```

### 5.1. Reading the Output by Layer of Responsibility

The first five errors all protect the same `List<String>`: calls through a raw variable, through an iterator, and through a sublist all fail to insert a number into the backing data. After the blocked attempts, the list still permits valid edits. Seeing `source.add("owner")` appear in `checked` shows that both references observe the same live data.

`null` is added successfully because `ArrayList` allows it. This is not a type-checking loophole: a missing value and a wrong type are two conditions that must be defined separately.

`numbers` accepts both `Integer` and `Double` thanks to the `Number.class` token, and rejects the string `"7"`. The result `genericCollectionEqualsList=false` illustrates the difference between a general collection wrapper and a list with a content-comparison contract.

The set still returns `false` when adding `"java"` again. The set's no-duplicates constraint continues to operate alongside type checking.

Finally, `StringBuilder` is accepted through the `CharSequence.class` interface token. After that object is mutated from `"a"` to `"ab"`, the content visible through the collection changes as well. The wrapper checks the kind of object being added; it does not freeze the state of that object.

## 6. Program 2: Protecting Keys, Values, and Map Entries

A map of lesson names to example counts needs `String` keys and `Integer` values. Checking direct `put` calls alone is not enough if the recipient can also obtain an entry and call `setValue` or use callbacks to replace values.

File `CheckedMapDemo.java`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class CheckedMapDemo {
    private static void rejected(String label, Runnable action) {
        try {
            action.run();
        } catch (ClassCastException expected) {
            System.out.println(label + "=ClassCastException");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        Map<String, Integer> checked = Collections.checkedMap(
                source, String.class, Integer.class);
        checked.put("a", 1);
        Map rawMap = checked;

        rejected("put.key", () -> rawMap.put(42, 2));
        rejected("put.value", () -> rawMap.put("b", "two"));
        rejected("replace.value", () -> rawMap.replace("a", "two"));

        Map.Entry rawEntry = checked.entrySet().iterator().next();
        rejected("entry.setValue", () -> rawEntry.setValue("two"));
        rawEntry.setValue(3);
        System.out.println("afterEntry=" + checked);

        rejected("compute.result", () ->
                rawMap.compute("b", (key, value) -> "two"));
        rejected("merge.result", () ->
                rawMap.merge("a", 4, (oldValue, newValue) -> "two"));
        rejected("replaceAll.result", () ->
                rawMap.replaceAll((key, value) -> "two"));
        System.out.println("afterRejected=" + checked);
        System.out.println("missingBadKey=" + checked.get(42));

        checked.compute("a", (key, value) -> value + 1);
        checked.merge("a", 4, Integer::sum);
        checked.put(null, null);
        source.put("owner", 9);
        System.out.println("finalMap=" + checked);

        checked.values().remove(9);
        System.out.println("afterViewRemoval=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CheckedMapDemo.java
java CheckedMapDemo
```

Output:

```text
put.key=ClassCastException
put.value=ClassCastException
replace.value=ClassCastException
entry.setValue=ClassCastException
afterEntry={a=3}
compute.result=ClassCastException
merge.result=ClassCastException
replaceAll.result=ClassCastException
afterRejected={a=3}
missingBadKey=null
finalMap={a=8, null=null, owner=9}
afterViewRemoval={a=8, null=null}
```

### 6.1. Why Does the Output Have a=8?

The initial mapping is `a=1`. The call `rawEntry.setValue(3)` is valid, so the data becomes `a=3`. The callbacks that attempt to return a string are all blocked; in these specific cases, the map neither adds nor replaces with an invalid value.

Then `compute` increments `3` to `4`, and `merge` adds `4` to get `8`. Type checking does not alter the computation semantics of valid callbacks.

`checked.put(null, null)` is permitted because the backing `LinkedHashMap` allows both. `source.put("owner", 9)` appears immediately in the view, proving this is not a snapshot of the data. When `9` is removed via `checked.values()`, the corresponding mapping disappears from the backing map as well.

### 6.2. Entries Must Be Obtained from the Right Map

`rawEntry` in the experiment is obtained via `checked.entrySet()`. It still protects the value when `setValue` is called through a raw type.

If an application holds an entry obtained directly from `source.entrySet()` and hands that entry out, that entry is not automatically replaced by a wrapper entry. It is another access path to the backing data. Wrapping a map after already exposing references does not revoke the references already handed out.

Only use an entry under the conditions permitted by the `Map.Entry` contract. Do not hold onto an entry across structural modifications to the map and assume it remains a valid "update door" forever.

### 6.3. A Wrong-Type Lookup Is Not the Same as a Wrong-Type Write

`checked.get(42)` compiles because the parameter of `Map.get` is `Object`. In the experiment with `LinkedHashMap`, it returns `null` because no such key exists. No wrong-type mapping is created.

Do not infer that every checked map must throw `ClassCastException` on every wrong-type lookup, or that every backing structure must return `null`. The query contract and type restrictions of the backing structure still play a role. The boundary being guarded is the stored data, not a runtime mechanism enforcing a `get(K)` signature.

The [`Map` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) specifies lookup, view, and callback-based update operations separately; it should be read alongside the policy of the backing map.

## 7. Two Conditions to Keep Data Type-Safe Over Time

To conclude that "the collection contains no wrong-type elements," having a wrapper alone is not enough. Both of the following conditions must hold:

1. The data is already of the right type before the view is created.
2. Every path that can introduce new data or replacement values into the structure goes through a properly checked view.

For a map, the first condition applies to both keys and values. The second condition includes collection views and entries obtained from the checked map.

### 7.1. Creating a Wrapper Does Not Validate All Existing Data

A list that already contains numbers but has been declared or cast as `List<String>` is not automatically cleaned when passed to `checkedList`. A wrapper created without error is not a certificate that every existing element passed inspection.

On read, using the result as a `String` can expose the invalid data. It is important to distinguish the wrapper's write-time check from the cast the compiler inserts at the read site. A value read as `Object` may not trigger an error yet; requiring it to be used as a `String` is what causes `ClassCastException` to appear.

Therefore, "wrapped yet still failing on `get`" does not prove the wrapper is broken. The invalid data may have been there beforehand, or may have entered through another reference.

### 7.2. A Reference to the Backing Structure Can Still Bypass the Check

If the same `ArrayList` has two references, where one points to the wrapper and the other points directly to the backing list, calls through the backing list do not go through the wrapper. The declared type of the backing reference can also be weakened by raw-typed code.

A clearer boundary design is to create an empty backing structure inside the owning component, wrap it, and only expose the wrapped reference. The backing object is not "locked" by a special JVM feature; the design is reducing the number of access paths that could skip the check.

Mutating valid data through the backing reference in the first two programs was only meant to demonstrate that the view shares data. In an integration that must guarantee type safety, that write path outside the wrapper must be controlled, not assumed safe by default.

### 7.3. Outer Type Checking Does Not Verify Nested Inner Types

`List.class` can verify that an element is a `List`. It provides no information that "every element inside that list is a `String`." Java has no `List<String>.class` class literal.

This is a consequence to understand when working with type erasure: many type arguments exist only for compile-time checking. A `List<Integer>` and a `List<String>` can both be represented by a list object at runtime; a `Class` token for `List` does not carry the full nested type structure.

For example, if you wrap an outer list with `List.class`, inserting an `ArrayList<Integer>` still passes the outer class check. A subsequent cast does not turn the numbers in the inner list into strings. When those numbers are read as `String`, the error reappears.

To protect nested structures, validate each layer according to the actual data structure, control references to each inner collection, or transform the data into a domain model with explicit constraints. Casting a raw `Class` to `Class<List<String>>` via an unchecked cast does not add deep checking capability that the token lacks.

[Java's Type Erasure documentation](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html) explains why type arguments are not automatically retained as a full class token for a wrapper to use.

## 8. Program 3: Existing Dirty Data, Bypass Paths, and Nested Types

The following program intentionally violates generics assumptions at isolated points in `main`. This is a diagnostic experiment for the limitations, not a pattern for ingesting untrusted data in application code.

File `CheckedLimitationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CheckedLimitationsDemo {
    private static void rejected(String label, Runnable action) {
        try {
            action.run();
        } catch (ClassCastException expected) {
            System.out.println(label + "=ClassCastException");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List dirty = new ArrayList();
        dirty.add(42);
        List<String> claimedStrings = dirty;
        List<String> wrappedDirty =
                Collections.checkedList(claimedStrings, String.class);
        Object oldValue = ((List) wrappedDirty).get(0);
        System.out.println("existingType=" + oldValue.getClass().getSimpleName());
        rejected("existingTypedRead", () -> wrappedDirty.get(0).length());

        List<String> source = new ArrayList<>();
        List<String> checked = Collections.checkedList(source, String.class);
        List rawSource = source;
        rawSource.add(99);
        System.out.println("bypassedSize=" + checked.size());
        rejected("bypassedTypedRead", () -> checked.get(0).length());

        List<List> lists = Collections.checkedList(
                new ArrayList<>(), List.class);
        lists.add(new ArrayList<>(List.of(123)));
        System.out.println("nestedType=" +
                lists.get(0).get(0).getClass().getSimpleName());
        List<String> assumedInner = lists.get(0);
        rejected("nestedTypedRead", () -> assumedInner.get(0).length());

        List<Integer> goodIntegers = Collections.checkedList(
                new ArrayList<>(), Integer.class);
        goodIntegers.add(7);
        System.out.println("boxedToken=" + goodIntegers);

        List<Integer> primitiveToken = Collections.checkedList(
                new ArrayList<>(), int.class);
        rejected("primitiveToken", () -> primitiveToken.add(7));

        List<String> partial = Collections.checkedList(
                new ArrayList<>(List.of("a", "b")), String.class);
        List rawPartial = partial;
        rejected("replaceAll.partial", () ->
                rawPartial.replaceAll(value -> value.equals("a") ? "A" : 42));
        System.out.println("afterPartial=" + partial);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CheckedLimitationsDemo.java
java CheckedLimitationsDemo
```

Output:

```text
existingType=Integer
existingTypedRead=ClassCastException
bypassedSize=1
bypassedTypedRead=ClassCastException
nestedType=Integer
nestedTypedRead=ClassCastException
boxedToken=[7]
primitiveToken=ClassCastException
replaceAll.partial=ClassCastException
afterPartial=[A, b]
```

### 8.1. Three Different Error Sources Can All Surface on Read

`existingType=Integer` occurs because the list already had invalid data before being wrapped. Creating a wrapper does not scan and reject that data.

`bypassedSize=1` occurs because the write went directly to `source`. The wrapper sees the new element since it shares the data, but it never had a chance to check it on write.

`nestedType=Integer` occurs because the `List.class` token only checks that the inner list is a list. The elements inside the inner list had no string constraint when that list was added to the outer list.

All three cases can lead to an error in a string-reading expression. The fix depends on the root cause: validating initial data, closing off write paths outside the wrapper, or checking nested structures. Adding another cast to silence warnings does not solve any of the three sources of error.

### 8.2. Tokens and Autoboxing Are Not the Same Mechanism

`boxedToken=[7]` shows that `Integer.class` matches the number object the list actually holds. `primitiveToken=ClassCastException` shows that the `int.class` argument is not automatically converted to the wrapper-class token even though `add(7)` autoboxes the value.

This distinction is useful when a utility method accepts `Class<E>` from another component. Define the input token contract; do not merely check that the token variable is non-`null` and assume every primitive class is equivalent to its wrapper class.

### 8.3. Type Checking Does Not Imply Rollback

In the final section, `replaceAll` transforms `"a"` into `"A"`, which is type-valid. When the callback reaches `"b"`, it returns the number `42` and is rejected. The result `[A, b]` retains the change made before the error.

This is a concrete demonstration with a wrapped `ArrayList` and the implementation that ran. Guaranteeing "no wrong-type value is stored through the wrapper" does not entail "every multi-element operation rolls back if an exception occurs."

In the OpenJDK 17 source code, the `addAll` and `putAll` paths prepare/check the input data before the write step; that avoids adding elements incrementally only to discover a wrong type mid-batch. This is an implementation detail to distinguish from a general transaction: backing-structure limits, other exceptions, callbacks, and concurrent access do not thereby gain a general rollback mechanism.

The [OpenJDK 17 `Collections` source code](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/Collections.java) clearly shows the input-checking step and the checking of callback results. Do not rely on internal wrapper class names or specific exception messages when writing application code.

## 9. Input Validation and Write-Time Checking Are Two Stages

Suppose you need to receive a list from a legacy library and let other components continue updating it. There are two different questions:

- Are the existing elements already in the expected data form?
- Do subsequent updates go through a controlled checking boundary?

Simply calling `checkedList` on the received list only partially answers the second question. A more controllable workflow is:

1. Accept the input via a type that expresses the unknown, such as `Collection<?>`, rather than pretending it is already `Collection<String>`.
2. Iterate and validate each element against the defined type, `null` policy, and business constraints.
3. Build a new structure owned by the current component; validation and result creation occur before publishing that result externally.
4. Create an appropriate type-checked view if updates still need to be allowed from boundaries where type information is easily lost.
5. Do not hand out the backing structure, iterators, or entries capable of writing outside the chosen boundary.

If an invalid value is encountered, deciding whether to reject the entire input or report per-item errors must belong to the application's contract. The wrapper does not invent a policy to convert `"42"` to a number, drop invalid elements, or replace `null` with a default value.

A standard collection copy such as `new ArrayList<>(input)` only copies element references. It does not become a deep verification of the entire type structure or a deep copy of object state. If the input can change concurrently, the ingestion process also needs an appropriate consistency strategy; a wrapper does not create an atomic snapshot of data being mutated.

### 9.1. Fixing Raw Types Remains the Primary Approach

If the entire codebase is under your control and generics can be declared properly, fix the type signatures and resolve unchecked warnings at the source. Placing a type-checked view at a defensive boundary or using one temporarily for diagnosis is valuable; scattering unchecked casts with `@SuppressWarnings` and expecting a wrapper to handle all consequences throws away useful static information.

A type-checked view also does not prove that a method receiving a collection obeys all business rules. For example, a `List<String>` can still accept empty strings, duplicate names, or a nonexistent name. Those rules are not represented by `String.class`.

## 10. Distinguishing from Other Wrappers and Copies

| How data is created/provided | Primary constraint | Keeps data link to backing structure? | Deep-checks nested data automatically? |
| --- | --- | --- | --- |
| `checkedList` on a modifiable list | Type of elements written through the view | Yes | No |
| `unmodifiableList` | Disallows structural edits through the view | Yes | No |
| `synchronizedList` | Synchronizes access per the wrapper contract | Yes | No |
| `new ArrayList<>(source)` | Creates another list holding element references | Does not share list structure | No |
| `List.copyOf(source)` | Creates an unmodifiable result, forbids `null` elements | Does not reflect later edits to the source | No |

The table only compares responsibilities directly relevant to this topic. Do not infer that one mechanism replaces the others.

For example, an API that lets a legacy library append names may need a type-checked view. A read-only API needs to consider mutability permissions. An API shared across multiple threads needs to consider synchronization and atomicity of operation sequences. All three requirements can appear in the same system, but each must be designed separately.

If multiple wrappers are combined, you must identify which object is handed out and what other references still exist. An `unmodifiable` layer outside a type-checked view blocks edits through the outer layer; it does not create an opportunity for the recipient to write valid data. A `checked` layer outside an unmodifiable list likewise does not grant write permissions that the backing list lacks.

There is no need to rely on internal implementation class names, wrapper ordering in error messages, or `getClass().getName()` checks to describe a public API contract.

### 10.1. Watch Out for Set Elements and Map Keys

An element can still belong to the right class while having fields mutated that affect `equals` or `hashCode`. A type-checked view does not prevent that. If the object is currently an element of a hash set or a key of a hash map, such mutation can break lookup assumptions.

Therefore, "every key belongs to class `CustomerKey`" and "keys maintain state consistent with the map contract throughout their storage lifetime" are two different invariants. The type token only helps with the object's class; key design and mutability of key state remain the application's responsibility. The [`Set`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) and [`Map`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) contracts warn directly about objects with mutable state affecting comparison.

## 11. Cost and How to Use It for Debugging

With an empty backing structure owned by the application, you can create the wrapper right at initialization and then pass the wrapper across the library boundary. Whenever data needs to be written, the application pays the extra cost of checking type compatibility and forwarding the call. The wrapper does not change the underlying storage to turn a linear algorithm into constant-time access.

Do not infer that batch operations always require only constant auxiliary memory. As observed in OpenJDK 17, preparing a checked copy of the input data for `addAll` or `putAll` can require auxiliary memory proportional to the number of input elements. True cost must be evaluated based on the operation in use and the backing structure; there is no fixed time overhead that holds true for every type-checked view.

A useful diagnostic workflow when encountering a `ClassCastException` at a read site:

1. Identify the collection/map holding the wrong data and the expected element, key, or value type.
2. Check whether the data was already wrong before the wrapper took effect.
3. Create a type-checked view at the ownership point or where the collection is handed to the suspected component.
4. Ensure the reproduction actually uses the wrapper; check for any backing references and previously exposed views/entries.
5. Reproduce and read the stack trace of the blocked write.
6. Fix the generics signature or the site creating the wrong data, then keep or remove the wrapper depending on the boundary's defensive role.

Catching `ClassCastException` and continuing silently usually just hides invalid data. If the application needs to accept a mixed set of inputs, model the mixed type intentionally—such as a domain model or an explicit conversion pipeline—rather than mislabeling it `List<String>`.

## 12. Self-Practice and Understanding Check

### Exercise 1: Changing the Type Token

In the first program, replace the number collection with a collection checked using `Integer.class`, then try adding `7`, `7L`, `2.5`, and `"7"`.

**Point to explain:** the integer `7` is boxed into an `Integer`, so it matches; `Long`, `Double`, and `String` do not become `Integer` just because they can be interpreted as numbers. If you keep declaring `Collection<Number>` while passing `Integer.class` directly, revisit the `Class<E>` signature: the compile-time type relationship must also be consistent. Declare `Collection<Integer>` for this token experiment.

### Exercise 2: Finding an Unprotected Access Path

A component holds `Map<String,Integer> source`, provides `checkedMap(source, String.class, Integer.class)` to library A, but provides `source.entrySet()` to library B.

**Point to explain:** an entry obtained directly from the backing map is another update path. If B uses raw code to modify the entry's value, the type-checked view that A received does not intercept that call. All writable references must be managed, not just the map variable returned from one method.

### Exercise 3: Creating a Wrapper After Heap Pollution

Use a raw type to add a number to an `ArrayList`, assign it to `List<String>`, and only then call `checkedList`. Compare reading as `Object`, calling `size`, and using the element as a `String`.

**Point to explain:** `size` and reading as `Object` do not verify that every element is a string. The error surfaces in the operation that requires a `String`. The fix is to validate the initial data or fix the original write path, not to wrap it multiple times.

### Exercise 4: Distinguishing Outer and Inner Types

Wrap an outer list with `List.class`, add a list containing numbers, and then read that number as a string through an unchecked assignment.

**Point to explain:** the inner list satisfies the outer class check. The type token does not describe the type argument of the inner list. Deep guarantees require a deep structural validation step and control over subsequent edits at that layer.

### Exercise 5: Checking the Impact When a Callback Fails

Re-run the `replaceAll` snippet at the end of the third program, then write a routine that only publishes the new list after all transformed results have been checked.

**Point to explain:** the wrapper enforces the type constraint on each written value; it does not provide a general rollback. Building the result separately and publishing it after success is a different design choice, which also requires defining mutability and reference-sharing rules for the elements.

When you can explain on your own why one write is blocked, why another write can bypass the check, and why nested data can still be wrong, you have grasped the boundary that the four `checked...` methods actually protect.
