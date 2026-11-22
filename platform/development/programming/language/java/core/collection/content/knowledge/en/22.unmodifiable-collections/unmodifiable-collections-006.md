# Null, Duplicate Element, and Duplicate Key Rules of Factories

## 1. Creating an Unmodifiable Collection Is Also Choosing a Data Policy

A list of permission codes may need to keep two occurrences of the same code. A set of permission codes only needs each code once. A configuration table requires each key to have exactly one value. All three results can be unmodifiable, yet their input data rules are not the same.

Static factory methods such as `List.of`, `Set.of`, and `Map.of` both create the result and enforce the contract of each type:

- `List` preserves order and can hold multiple equal elements.
- `Set` keeps only one representative for each element according to equality; creation may reject or deduplicate duplicate inputs.
- `Map` requires unique keys; multiple distinct keys are still allowed to have the same value.
- The policy of disallowing `null` is a separate condition and is not automatically implied merely by the word "unmodifiable".

The easiest point to confuse: **`Set.of` rejects duplicate elements, whereas `Set.copyOf` accepts a collection with duplicate elements and keeps one representative.** Sharing `Set` in the name and returning an unmodifiable result is not enough to infer the same input rules.

This lesson focuses on the factories of `List`, `Set`, and `Map`, the `copyOf` variants, `Map.entry`/`Map.ofEntries`, and the collectors that produce unmodifiable results. The final section compares several legacy factories to avoid applying the `null` rules of the `of` family to every Java API.

Three complete programs use Java 17 or later and the standard library. Expressions that throw exceptions are placed inside a helper check method so the programs still run to completion. Results of sets/maps are only printed when order has been clarified or converted into an ordered structure for presentation.

## 2. Rule Tables to Distinguish Immediately

### 2.1. The Main Factories

| Method | `null` in directly passed elements/keys/values | Duplicate input | Result when valid |
|---|---|---|---|
| `List.of(...)` | Disallows `null` elements | Allows duplicate elements | `List` preserving positions in argument order |
| `List.copyOf(collection)` | Collection and all elements must be non-`null` | Keeps duplicate elements | `List` in input iteration order |
| `Set.of(...)` | Disallows `null` elements | Rejects duplicate elements with `IllegalArgumentException` | `Set` without duplicate elements |
| `Set.copyOf(collection)` | Collection and all elements must be non-`null` | Deduplicates equal elements, keeping one representative with no guarantee of first or last | `Set` without duplicate elements |
| `Map.of(k,v,...)` | Disallows `null` keys or values | Rejects duplicate keys with `IllegalArgumentException`; duplicate values are allowed | `Map` with unique keys |
| `Map.ofEntries(entries...)` | Disallows `null` entries, keys, or values | Rejects duplicate keys with `IllegalArgumentException` | `Map` taking keys/values from the entries |
| `Map.copyOf(map)` | Map, all keys, and all values must be non-`null` | Takes the current mappings of the input map; does not detect prior overwrite history already lost | `Map` that does not reflect subsequent mapping updates of the source map |
| `Map.entry(k,v)` | Disallows `null` keys or values | Creates only a single entry, so no multi-entry duplication issue yet | Entry that disallows `setValue` |

For the cases where `null` is prohibited in the table, an invalid call throws `NullPointerException`. This is a failure at the creation step, different from `UnsupportedOperationException` when attempting to modify an already successfully created result.

`Map.copyOf` accepts a `Map`, not a sequence of key/value pairs. An ordinary map has already enforced the unique-key rule before `copyOf` is called; keep this difference in mind when checking for duplicate data.

Specific collection types can still have different policies. For example, a mutable `HashMap` allows one `null` key and `null` values; that does not allow `Map.copyOf` to accept those `null`s.

### 2.2. Argument Arity and API Versions

`List.of` and `Set.of` provide convenience overloads for small numbers of elements, along with a varargs overload for more elements. `Map.of` has overloads from zero mappings up to ten mappings; for more pairs, `Map.ofEntries` is typically used.

The `of` methods, `Map.ofEntries`, and `Map.entry` have been available since Java 9. The `copyOf` methods have been available since Java 10. All of these APIs are available on Java 17 used in this lesson.

`List.of()`, `Set.of()`, `Map.of()`, and `Map.ofEntries()` can create empty results. Empty does not mean a factory starts accepting a `null` element; "having no elements" and "having one `null` element" are two different inputs.

## 3. `null`: Distinguishing the Input Object, Elements, and Inner Data

### 3.1. `null` Is Not Silently Ignored

`List.of("a",null)` does not create a list containing only `a`. `Set.of("a",null)` does not skip `null` and continue. `Map.of("a",null)` does not drop the mapping or replace `null` with an empty string.

If business logic wants to filter, substitute missing values, or reject with a custom message, it must do so explicitly. The factory does not choose a business policy on behalf of the application.

It is also necessary to distinguish `null` from other data:

- The string `"null"` is a four-character `String`, not a `null` reference.
- The empty string `""` is still a non-`null` `String`.
- An empty collection is a collection object, not `null`.
- An object with an internal field equal to `null` can still be a non-`null` element.

### 3.2. `copyOf` Checks Both the Source and the Contents to Be Copied

`List.copyOf(null)` has no collection to copy, so it throws `NullPointerException`. Calling `List.copyOf` on a non-`null` `ArrayList` that contains a `null` element is also invalid.

`Set.copyOf` has the same conditions: no `null` source and no `null` elements. `Map.copyOf` requires the source map to be non-`null` and to contain no `null` keys or values.

Do not look at the `ArrayList` or `HashMap` type of the source and assume the contents are guaranteed to be suitable: those very source classes permit certain `null`s that the target factory rejects.

### 3.3. With Varargs, Write Unambiguous `null` Examples

In Java, a call written simply as `List.of(null)` can involve overload resolution and how varargs parameters are interpreted, and may also produce a compiler warning. When you want to express the exact case being tested, write it explicitly:

- `List.of((String) null)`: a single `String` element that is `null`.
- `List.of((String[]) null)`: a `null` varargs array.

Both cases fail, but their input meanings differ. Use casts in examples to explain the contract, not to bypass the `null` condition.

### 3.4. Factories Do Not Recursively Inspect Every Field of an Element

A `List` containing a non-`null` `String[]` array can be validly created even if a slot inside the array is `null`, as long as that array is genuinely **one element** of the list.

The factory only applies its condition to the element it receives at that level. It does not walk into every array, list, or business object to verify there is no `null` anywhere inside.

The varargs section at the end of the second program will verify this with `List.<String[]>of(...)`. If a business API prohibits `null` inside child objects as well, it must have corresponding model validation.

## 4. Program Testing Factories That Accept Direct Arguments

`DirectFactoryRulesDemo` isolates each invalid input into a separate call. The `expect` method prints only the verified exception type name, without depending on the message or stack trace of a specific JDK build.

File **DirectFactoryRulesDemo.java**:

```java
import java.util.AbstractMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class DirectFactoryRulesDemo {
    private static void expect(String label,
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (RuntimeException failure) {
            if (!type.isInstance(failure)) {
                throw failure;
            }
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("listDuplicates=" + List.of("x", "x"));
        System.out.println("emptySizes=" +
                List.of().size() + "," + Set.of().size() + "," + Map.of().size());

        expect("listNullElement", NullPointerException.class,
                () -> List.of((String) null));
        expect("listNullArray", NullPointerException.class,
                () -> List.of((String[]) null));
        expect("setNullElement", NullPointerException.class,
                () -> Set.of((String) null));
        expect("setDuplicate", IllegalArgumentException.class,
                () -> Set.of("x", "x"));

        Map<String, Integer> repeatedValues = Map.of("a", 7, "b", 7);
        System.out.println("repeatedMapValueSize=" + repeatedValues.size());
        expect("mapNullKey", NullPointerException.class,
                () -> Map.of((String) null, 1));
        expect("mapNullValue", NullPointerException.class,
                () -> Map.of("a", (Integer) null));
        expect("mapDuplicateKey", IllegalArgumentException.class,
                () -> Map.of("a", 1, "a", 1));

        expect("entryNullValue", NullPointerException.class,
                () -> Map.entry("a", (Integer) null));
        expect("ofEntriesNullEntry", NullPointerException.class,
                () -> Map.ofEntries((Map.Entry<String, Integer>) null));
        expect("ofEntriesNullKey", NullPointerException.class,
                () -> Map.ofEntries(
                        new AbstractMap.SimpleEntry<String, Integer>(null, 1)));
        expect("ofEntriesNullValue", NullPointerException.class,
                () -> Map.ofEntries(
                        new AbstractMap.SimpleEntry<String, Integer>("a", null)));
        expect("ofEntriesDuplicateKey", IllegalArgumentException.class,
                () -> Map.ofEntries(Map.entry("a", 1), Map.entry("a", 2)));

        Map.Entry<String, Integer> entry =
                new AbstractMap.SimpleEntry<>("a", 1);
        Map<String, Integer> extracted = Map.ofEntries(entry);
        entry.setValue(9);
        System.out.println("extractedValue=" + extracted.get("a"));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DirectFactoryRulesDemo.java
java DirectFactoryRulesDemo
```

Exact stdout:

```text
listDuplicates=[x, x]
emptySizes=0,0,0
listNullElement=NullPointerException
listNullArray=NullPointerException
setNullElement=NullPointerException
setDuplicate=IllegalArgumentException
repeatedMapValueSize=2
mapNullKey=NullPointerException
mapNullValue=NullPointerException
mapDuplicateKey=IllegalArgumentException
entryNullValue=NullPointerException
ofEntriesNullEntry=NullPointerException
ofEntriesNullKey=NullPointerException
ofEntriesNullValue=NullPointerException
ofEntriesDuplicateKey=IllegalArgumentException
extractedValue=1
```

### 4.1. `List` Keeps Duplicates; `Set` Treats Duplicates as an Error in the `of` Family

`List.of("x","x")` creates two positions with the same value `x`. `Set.of("x","x")` is rejected. Do not use `Set.of` as a "convenient deduplication" operation for unknown arguments.

Rejecting duplicates is appropriate when a repeated declaration is considered an error to detect. If you want to collect distinct values from a source that may have repeats, `Set.copyOf` or a set collector with the corresponding contract expresses a different intent.

### 4.2. `Map` Only Requires Unique Keys

`Map.of("a",7,"b",7)` is valid because there are two different keys. Using the value `7` for both mappings does not create a conflict.

`Map.of("a",1,"a",1)` is still rejected even though the values are also identical. The factory does not choose "if the value is the same, ignore the duplicate key", nor does it apply a "last pair wins" rule like repeated `put` calls on a mutable map.

The contract of [Map.of and Map.ofEntries](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#ofEntries(java.util.Map.Entry...)) clearly distinguishes duplicate keys from duplicate values.

### 4.3. `Map.entry` Can Fail Before `Map.ofEntries`

`Map.entry("a",null)` fails immediately when creating the entry. If it appears in an argument to `Map.ofEntries`, the program does not even have a valid entry to pass along yet.

`Map.ofEntries` must also check entries coming from other sources. `AbstractMap.SimpleEntry` in the example can hold `null`, so the two `null`-key and `null`-value checks test the data extraction step of `ofEntries` itself.

A `null` entry reference is also rejected. Therefore, three separate levels must be checked: the entry array/sequence, each entry object, and the key/value inside each entry.

### 4.4. `Map.ofEntries` Extracts Data Rather Than Retaining the Input Entry Object

At the end of the program, the mutable entry initially holds `a→1`. After `extracted` is created, `entry.setValue(9)` does not change `extracted.get("a")`, which remains `1`.

This illustrates the contract of extracting the key/value out of the entry. It does not deep-copy the key or value objects; if a value is a shared mutable object, the internal state of that object still needs to be considered separately.

## 5. "Duplicate" Is Based on Equality, Not on Display Form

### 5.1. Different References Can Still Be Duplicate Elements or Keys

Two `String`s created as two distinct objects with the same content are still equal according to `equals`. `Set.of` does not treat them as two separate elements just because `==` returns `false`.

For a business class, the equality rule is defined by `equals()`, along with the corresponding `hashCode()` contract. If two objects with the same business code are considered equal by `equals`, they can be duplicate elements or duplicate keys in these factories, even if descriptive fields differ.

Conversely, two objects that print the same string are not necessarily equal according to `equals`. Do not rely on `toString()` to check for duplicates.

### 5.2. The Same `hashCode` Does Not Mean Duplicate

Hash codes assist lookup organization; they do not replace the `equals` relation. Two different elements can have a hash collision and still coexist.

For example, `"FB"` and `"Ea"` have the same `String` `hashCode` but are not equal according to `equals`. `Set.of("FB","Ea")` therefore has two elements and does not fail as a duplicate.

If a custom class violates the `equals`/`hashCode` contract, do not use an accidental factory result to infer that Java is changing the definition of equality. Fix the class contract first.

### 5.3. No Automatic String Normalization or `Comparator` Instead of `equals`

`"admin"` and `"ADMIN"` are two different `String`s according to `equals`. The factory does not automatically lowercase, trim whitespace, or apply a case-insensitive `Comparator`.

If business logic treats them as a single code, you must normalize or map the keys according to a defined policy before creating the collection. Doing so can introduce new conflicts that were not present in the raw data, so you must choose explicitly whether to reject, merge, or report an error.

## 6. `copyOf`: Important Differences in Handling Duplicate Data

`List.copyOf` preserves duplicate elements and input iteration order. `Set.copyOf` accepts a `Collection`, so the input can certainly be a `List` with repeated elements. It creates a set with one representative for each equivalence group.

According to the specific contract of [Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)), when there are multiple equal objects, the retained representative is not guaranteed to be the first or the last object encountered.

### 6.1. Program Demonstrating Copying, Equality, and Arrays

`Label` in the program uses only `id` for `equals`/`hashCode`. Two `Label`s with the same `id` but different `text` are therefore distinct object references that are still equal under the class's rule.

File **CopyFactoryRulesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CopyFactoryRulesDemo {
    static final class Label {
        final int id;
        final String text;

        Label(int id, String text) {
            this.id = id;
            this.text = text;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Label label && id == label.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    private static void expect(String label,
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (RuntimeException failure) {
            if (!type.isInstance(failure)) {
                throw failure;
            }
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("b", "a", "b"));
        List<String> listCopy = List.copyOf(source);
        Set<String> setCopy = Set.copyOf(source);
        System.out.println("copiedList=" + listCopy);
        System.out.println("copiedSetSorted=" + new TreeSet<>(setCopy));

        expect("copyListNull", NullPointerException.class,
                () -> List.copyOf(Arrays.asList("x", null)));
        expect("copySetNull", NullPointerException.class,
                () -> Set.copyOf(Arrays.asList("x", null)));

        Label first = new Label(1, "first");
        Label second = new Label(1, "second");
        System.out.println("differentObjects=" + (first != second));
        System.out.println("equalElements=" + first.equals(second));
        expect("ofEqualElements", IllegalArgumentException.class,
                () -> Set.of(first, second));
        Set<Label> labels = Set.copyOf(List.of(first, second));
        Label chosen = labels.iterator().next();
        System.out.println("copyDedupSize=" + labels.size());
        System.out.println("representativeIsInput=" +
                (chosen == first || chosen == second));

        System.out.println("sameHash=" + ("FB".hashCode() == "Ea".hashCode()));
        System.out.println("collisionSetSize=" + Set.of("FB", "Ea").size());

        String[] row1 = {"same"};
        String[] row2 = {"same"};
        System.out.println("differentArraySetSize=" + Set.of(row1, row2).size());
        expect("sameArrayRepeated", IllegalArgumentException.class,
                () -> Set.of(row1, row1));
        List<int[]> primitiveArrayElement = List.of(new int[]{1, 2});
        System.out.println("primitiveArrayListSize=" + primitiveArrayElement.size());
        List<String[]> nested = List.<String[]>of(new String[]{"x", null});
        System.out.println("nestedListSize=" + nested.size());
        System.out.println("nestedNullAllowed=" + (nested.get(0)[1] == null));

        Map<String, Integer> staged = new LinkedHashMap<>();
        staged.put("k", 1);
        staged.put("k", 2);
        Map<String, Integer> mapCopy = Map.copyOf(staged);
        System.out.println("stagedSize=" + staged.size());
        System.out.println("copiedMapValue=" + mapCopy.get("k"));

        Map<String, Integer> nullValue = new LinkedHashMap<>();
        nullValue.put("k", null);
        expect("copyMapNullValue", NullPointerException.class,
                () -> Map.copyOf(nullValue));
        Map<String, Integer> nullKey = new LinkedHashMap<>();
        nullKey.put(null, 1);
        expect("copyMapNullKey", NullPointerException.class,
                () -> Map.copyOf(nullKey));
    }
}
```

Run command:

```shell
javac --release 17 -encoding UTF-8 CopyFactoryRulesDemo.java
java CopyFactoryRulesDemo
```

Exact stdout:

```text
copiedList=[b, a, b]
copiedSetSorted=[a, b]
copyListNull=NullPointerException
copySetNull=NullPointerException
differentObjects=true
equalElements=true
ofEqualElements=IllegalArgumentException
copyDedupSize=1
representativeIsInput=true
sameHash=true
collisionSetSize=2
differentArraySetSize=2
sameArrayRepeated=IllegalArgumentException
primitiveArrayListSize=1
nestedListSize=1
nestedNullAllowed=true
stagedSize=1
copiedMapValue=2
copyMapNullValue=NullPointerException
copyMapNullKey=NullPointerException
```

### 6.2. The Retained Representative Is Not a Business Data Selection Rule

`Set.of(first,second)` fails because the two `Label`s are equal. `Set.copyOf(List.of(first,second))` succeeds with size `1`.

The program only checks that the representative is one of the two input objects. It does not print which `text` label was kept and declare that to be a "keep first" rule.

If two records have the same `id` but different information that the business logic needs to handle, arbitrary deduplication can lose important data. You should explicitly check for conflicts or choose a merge operation, rather than using `Set.copyOf` as a data reconciler.

### 6.3. `Map.copyOf` Does Not See Overwritten Key History

`staged.put("k",1)` followed by `staged.put("k",2)` leaves the source map with only one mapping `k→2`. `Map.copyOf(staged)` receives that exact current state, so there are no two mappings `k→1` and `k→2` to check against each other.

If the requirement is to detect repeated keys in a configuration file or a sequence of records, you must check while reading that sequence, before overwriting erases the information. Do not build a `HashMap` with `put` and expect `copyOf` to detect earlier occurrences.

For maps with special key rules such as `IdentityHashMap`, you also need to consider the policy for converting key equality. `Map.copyOf` is not a promise to preserve the identity-comparison semantics of every input map type.

### 6.4. Printed Order Was Intentionally Normalized

`copiedSetSorted` is printed using `new TreeSet<>(setCopy)`. Therefore, `[a,b]` in stdout is the order of `TreeSet` used for presentation, not a guarantee that `Set.copyOf` preserves insertion order or sorts automatically.

`Set.of`/`Set.copyOf` and `Map.of`/`Map.ofEntries`/`Map.copyOf` are not APIs for choosing insertion order. If you need an order for reporting or testing, choose an appropriate ordered structure/contract or compare as sets/maps.

## 7. Arrays and Varargs: Must Determine What Counts as One Element

### 7.1. A Reference Array Can Be Used as the Argument Sequence

With `String[] words`, calling `List.of(words)` normally takes the `String`s inside the array as elements through the varargs call. If `words` contains `null`, the elements passed into the list contain `null` and the call is rejected.

If you want a list with **one element that is the `String[]` array itself**, you can write `List.<String[]>of(words)`. In the program, that array is non-`null`, so the outer-level element is valid; an inner slot being `null` is not recursively checked.

This is a difference in how data is passed and in element type, not a secret exception for `null`.

### 7.2. Primitive Arrays Do Not Automatically Become Lists of Boxed Numbers

`List.of(new int[]{1,2})` creates a list with one element of type `int[]`. It does not automatically create a `List<Integer>` of two elements.

Therefore, checking `list.size()` yields `1`. If you want a `List<Integer>` from the numbers in a primitive array, you must use an appropriate conversion, such as an `IntStream` followed by `boxed()`; do not read `List.of` as an automatic primitive-array flattening operation.

### 7.3. Ordinary Arrays Do Not Compare Contents with `equals`

`row1` and `row2` are two `String[]` arrays with the same contents. They are two distinct array objects, and ordinary array `equals` does not compare slot-by-slot contents, so `Set.of(row1,row2)` has size `2`.

`Set.of(row1,row1)` repeats the exact same object and is rejected. If you want equality by array contents, you need a data/key type that defines it appropriately; calling `Arrays.equals` separately somewhere does not make the factory automatically use that comparison.

The `equals` rule of [Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)) and the content comparison methods of [Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html) are two mechanisms that must be distinguished.

## 8. Collectors That Produce Unmodifiable Results Have Their Own Rules

A `Stream` pipeline can produce unmodifiable data using `Collectors.toUnmodifiableList`, `toUnmodifiableSet`, and `toUnmodifiableMap`. They share the goal of creating unmodifiable results, yet do not have every exception rule identical to direct `of` calls.

### 8.1. Collector Comparison Table

| Collector | `null` | Duplicates | Order |
|---|---|---|---|
| `toUnmodifiableList()` | Rejects `null` elements | Keeps duplicate elements | Preserves encounter order if the stream is ordered |
| `toUnmodifiableSet()` | Rejects `null` elements | Deduplicates equal elements, keeping a representative per contract | No insertion order guarantee |
| `toUnmodifiableMap(keyMapper,valueMapper)` | Rejects `null` keys/values returned by the mapping functions | Duplicate keys throw `IllegalStateException` | No insertion order guarantee |
| `toUnmodifiableMap(keyMapper,valueMapper,mergeFunction)` | Still disallows mapping functions from producing `null` keys/values | Uses `mergeFunction` to handle values for the same key | No insertion order guarantee |

The mapping functions and merge function passed in must also be non-`null`. When designing a merge function, read its contract rather than using a `null` return as an arbitrary way to keep a mapping with a `null` value.

A notable difference is **`IllegalStateException` from the collector overload without a merge function**, compared to **`IllegalArgumentException` from `Map.of`/`Map.ofEntries` on duplicate keys**.

### 8.2. Program for Stream Collection and Legacy Factory Comparison

The example explicitly writes separate `Stream` sources and does not reuse an already terminated stream. Maps are printed via `TreeMap` when stable stdout is needed.

File **CollectorFactoryRulesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorFactoryRulesDemo {
    private static void expect(String label,
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (RuntimeException failure) {
            if (!type.isInstance(failure)) {
                throw failure;
            }
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("collectedList=" + Stream.of("x", "x")
                .collect(Collectors.toUnmodifiableList()));
        System.out.println("collectedSetSize=" + Stream.of("x", "x")
                .collect(Collectors.toUnmodifiableSet()).size());

        expect("collectorListNull", NullPointerException.class,
                () -> Stream.of("x", null)
                        .collect(Collectors.toUnmodifiableList()));
        expect("collectorSetNull", NullPointerException.class,
                () -> Stream.of("x", null)
                        .collect(Collectors.toUnmodifiableSet()));
        expect("collectorDuplicateKey", IllegalStateException.class,
                () -> Stream.of("x", "x").collect(
                        Collectors.toUnmodifiableMap(Function.identity(), x -> 1)));
        expect("collectorNullKey", NullPointerException.class,
                () -> Stream.of("x").collect(
                        Collectors.toUnmodifiableMap(x -> (String) null, x -> 1)));
        expect("collectorNullValue", NullPointerException.class,
                () -> Stream.of("x").collect(
                        Collectors.toUnmodifiableMap(
                                Function.identity(), x -> (Integer) null)));

        Map<String, Integer> counts = Stream.of("red", "blue", "red").collect(
                Collectors.toUnmodifiableMap(
                        Function.identity(), x -> 1, Integer::sum));
        System.out.println("mergedCountsSorted=" + new TreeMap<>(counts));
        System.out.println("streamToListNull=" + Stream.of("x", null).toList());

        System.out.println("legacySingletonList=" +
                Collections.singletonList(null));
        System.out.println("legacySingletonSetHasNull=" +
                Collections.singleton(null).contains(null));
        Map<String, Integer> legacyMap =
                Collections.singletonMap(null, null);
        System.out.println("legacySingletonMap=" +
                legacyMap.size() + "," + legacyMap.containsKey(null));
        System.out.println("legacyNCopies=" + Collections.nCopies(2, null));
        List<String> nullableSource =
                new ArrayList<>(Arrays.asList("x", null));
        System.out.println("wrappedNullable=" +
                Collections.unmodifiableList(nullableSource));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectorFactoryRulesDemo.java
java CollectorFactoryRulesDemo
```

Exact stdout:

```text
collectedList=[x, x]
collectedSetSize=1
collectorListNull=NullPointerException
collectorSetNull=NullPointerException
collectorDuplicateKey=IllegalStateException
collectorNullKey=NullPointerException
collectorNullValue=NullPointerException
mergedCountsSorted={blue=1, red=2}
streamToListNull=[x, null]
legacySingletonList=[null]
legacySingletonSetHasNull=true
legacySingletonMap=1,true
legacyNCopies=[null, null]
wrappedNullable=[x, null]
```

### 8.3. Merging Keys Is an Explicit Decision

`Stream.of("x","x")` with `toUnmodifiableMap(identity,x→1)` has two elements mapping to the same key `x`. It still fails even though both values are `1`; this collector overload does not automatically accept "duplicate but same value".

In the color-counting example, `mergeFunction` is `Integer::sum`. Two occurrences of `red` contribute to the same key and are summed to `2`. This is a clear counting policy, unlike silently keeping an arbitrary entry.

Depending on business requirements, you may need to keep one entry by a specific criterion, accumulate values, collect entries into a list, or reject conflicts. The merge function must express that exact intent. For pipelines that may run in parallel, it must also satisfy the requirements of collection and merging; do not use a function that depends on arbitrary execution order.

The contract in [Collectors.toUnmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableMap(java.util.function.Function,java.util.function.Function)) and related collectors is the basis for distinguishing exception types and duplicate policies.

### 8.4. `Stream.toList` Differs from `toUnmodifiableList` Regarding `null`

`Stream.toList()` has been available since Java 16, returns an unmodifiable list, and in the example retains `null`. `Collectors.toUnmodifiableList()`, on the other hand, rejects `null`.

Two ways of writing that both yield unmodifiable results do not mean switching between them preserves the same data policy. You must read the contract of the method in use; the [Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) specification defines how the list is collected and does not apply the `null`-rejection rule of `toUnmodifiableList`.

`Collectors.toList()` is yet another method: do not use it as a general guarantee of the implementation type or mutability of the result. If you explicitly need a mutable `ArrayList`, choose a collector that creates that structure by contract.

## 9. Do Not Apply `of`-Family Rules to Every Factory or Wrapper

### 9.1. Some Legacy Factories Allow `null`

The third program shows:

| API | Input in example | Result |
|---|---|---|
| `Collections.singletonList(null)` | One `null` element | `List` with one `null` |
| `Collections.singleton(null)` | One `null` element | `Set` with one `null` |
| `Collections.singletonMap(null,null)` | `null` key and value | One mapping with a `null` key |
| `Collections.nCopies(2,null)` | Repeating the same `null` value twice | `List` with two `null` elements |
| `Collections.unmodifiableList(nullableSource)` | Source already containing `null` | View reading the `null` element from the source |

These factories/wrappers do not share the same input conditions as `List.of`, `Set.of`, and `Map.of`. Therefore, "an unmodifiable collection can never contain `null`" is a false statement if applied to all of Java Collections.

`Collections.nCopies` also does not clone the element object. If you pass a mutable object, the repeated positions share the same reference; this differs from creating `n` separate mutable objects.

The contracts of methods in [Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html) must be read per API, not replaced by assumptions from the general label "factory".

### 9.2. A Wrapper Is Not a Data Filter

`Collections.unmodifiableList(source)` primarily blocks modifications through the returned interface; it does not proactively check and remove `null`s already in `source`. For `Set` or `Map`, the wrapper likewise relies on the source data and the source's inherent policy.

If `source` is an `ArrayList` with repeated elements, wrapping it with `unmodifiableList` still keeps the repeated elements. If the source map overwrote keys during `put`, wrapping it does not restore the history of replaced entries.

Consequently, replacing a wrapper with `copyOf` can change the `null` policy, the relationship to the source, and the timing of error detection. Do not treat it as a purely stylistic change.

## 10. Choose the Policy Before Choosing the Method

Start from the data requirements, rather than picking an arbitrary factory and fixing errors until the code runs:

1. Is missing data allowed, and is missingness represented by `null`, absence of the element/key, or a specific value?
2. Are duplicate elements meaningful, supposed to be merged, or an error?
3. For a map, by what rule are keys normalized before checking for duplicates?
4. If two records share the same key/code but have different contents, what is the conflict policy?
5. Does the result need a specific iteration order?
6. Do you need a snapshot detached from the source or a view that continues to reflect the source?

### 10.1. Do Not Silently Drop `null` If It Is a Data Error

Filtering with `Objects::nonNull` before `List.copyOf` can be right if the contract intentionally discards missing items. It can also hide an invalid record that the user needs to be notified about.

Similarly, `Set.copyOf` may fit a tag list where repetition does not matter, but it is unsuitable for verifying that a declaration file has no duplicate entries. Both cases have the same input shape yet different business requirements.

If an error needs a position, field name, or record ID, validate and report at the data boundary. A factory's default exception message is not a guaranteed business diagnostic format.

### 10.2. Example Accepting a `Collection` While Intentionally Rejecting Duplicates

If the requirement is to create an unmodifiable set while ensuring the input is non-`null` and has no duplicate elements, you can write a dedicated method like the following.

This is a method placed in a class that imports `Collection`, `Set`, `LinkedHashSet`, and `Objects`; it is not a standalone `main` program. Elements must have proper `equals`/`hashCode` implementations and must not mutate the relevant properties during processing:

```java
static <T> Set<T> requireDistinct(Collection<? extends T> values) {
    Objects.requireNonNull(values, "values");
    Set<T> unique = new LinkedHashSet<>();
    int index = 0;
    for (T value : values) {
        Objects.requireNonNull(value, "null element at index " + index);
        if (!unique.add(value)) {
            throw new IllegalArgumentException("duplicate at index " + index);
        }
        index++;
    }
    return Set.copyOf(unique);
}
```

The method validates each value before building the result. When `LinkedHashSet.add` returns `false`, an equal element has already been seen, so it throws an error instead of silently deduplicating.

`LinkedHashSet` here is a temporary structure for validation. The final result uses `Set.copyOf`, so **it does not guarantee insertion order**. If the contract requires preserving order, you must choose an appropriate return structure/wrapper rather than attributing a guarantee that does not exist in this method.

The message uses a 0-based index to illustrate diagnostics. Real applications can use a line number or field name, as long as the contract is clear. This is not a recursive check of child objects, nor does it make mutable elements immutable.

### 10.3. For Maps, Validate Before Data Is Lost

If you are processing a sequence of entries and want to reject repeated keys, check while collecting the sequence into a map. `Map.ofEntries` fits when you already have all entries and want the factory's duplicate-key rejection rule.

With `Stream`, you can use the `toUnmodifiableMap` overload without a merge function if that exception type fits, or provide your own business conflict-reporting mechanism. If you want to merge, use the overload with a merge function implementing a defined policy.

A `HashMap` that has already been overwritten by `put` no longer has enough information to know whether there were previously two records. Calling `Map.copyOf` at the end only freezes the current state; it is not an audit step over all raw data.

## 11. What These Checks Do Not Guarantee

### 11.1. They Do Not Validate All Business Properties

`List.of` accepts `""` because that string is non-`null`. `Set.of` can accept `"admin"` and `"ADMIN"` because they are not equal under `equals`. `Map.of` accepts a negative number as a value if the type allows it; it does not know whether that number is valid under business limits.

Being valid according to the factory only means the factory's own conditions are satisfied. It does not prove every value is meaningful to the application.

### 11.2. They Do Not Deep-Copy or Protect Mutable Keys

The factories store elements/keys/values according to their contracts; they do not automatically deep-clone all internal state. An element can still change properties even though the collection disallows adding, removing, or replacing positions.

If a set element or map key has properties affecting `equals`/`hashCode` mutated while it is stored, lookup behavior may no longer conform to the contract. Disallowing structural modification does not automatically forbid setters on the key object.

Duplicate detection policies therefore depend on a correct and stable equality relation. Choosing immutable keys usually helps maintain that condition.

### 11.3. They Do Not Automatically Make Concurrent Source Reads Consistent

`copyOf` produces a result that does not follow subsequent structural changes to the source, yet reading the source to build the result still requires a coordination contract if the source is updated by multiple threads.

Unsynchronized mutable data is not fixed simply by adding `copyOf` at the end. This lesson uses sequential data to focus on verifying `null` and duplicate policies.

### 11.4. They Do Not Guarantee Iteration Order or Object Identity as Desired

Do not use the print order of a `Set.of` in one run as proof of insertion order. Do not use `==` on collections returned by factories to verify "it was copied properly": a factory may reuse an eligible object per its contract.

If you need a deterministic order for display, choose or convert to a model with a clearly stated order. If you need to compare sets of elements, use `Set` equality; if you need to compare sequences, use `List` equality with its corresponding order.

## 12. Distinguishing Errors and Avoiding Reliance on Implementation Details

| Situation | Outcome type to remember |
|---|---|
| `null` in input prohibited by `List.of`/`Set.of`/`Map.of` | `NullPointerException` |
| Duplicate element in `Set.of` | `IllegalArgumentException` |
| Duplicate key in `Map.of`/`Map.ofEntries` | `IllegalArgumentException` |
| Duplicate element in `List.of`/`List.copyOf` | Valid; all occurrences are kept |
| Duplicate element in `Set.copyOf`/`toUnmodifiableSet` | Valid; one representative is kept |
| Duplicate key in `toUnmodifiableMap` without merge function | `IllegalStateException` |
| Attempting `add`/`remove`/`put` on an unmodifiable factory result | `UnsupportedOperationException` |
| Repeated value on two different `Map` keys | Valid if remaining data is valid |

### 12.1. No Guarantee on Detection Order When Multiple Errors Coexist

If an input has both `null` and duplicate elements/keys, do not write a generic test across all factories expecting one specific error to always be detected first. The contract may not specify that check order.

The programs in this lesson isolate each error for clear conclusions. When validating application data and needing a consistent error-reporting order, design your own check order at the data boundary.

### 12.2. Do Not Depend on Exception Message Strings or Internal Class Names

The message of `IllegalArgumentException` or `IllegalStateException` may contain useful details for debugging, but should not be used as a stable data-parsing protocol across versions.

Similarly, the internal class names of lists/sets/maps created by the JDK are not an API for applications to branch behavior on. Test against the method contract and the specified exception types.

### 12.3. Do Not Use `contains(null)` as a General Validity Probe

A collection containing no `null`s does not automatically guarantee `contains(null)` always returns `false`. Collection APIs have rules on disallowed arguments; such a query may be rejected depending on the contract.

To validate an input collection before calling a factory, check each element according to your own policy. Once a factory has created a valid result under a non-`null` contract, there is no need to test a `null` query to "re-confirm".

## 13. Exercises and Solutions

### Exercise 1 — Same Data, Different Factories

Compare `List.of("a","a")`, `Set.of("a","a")`, and `Set.copyOf(List.of("a","a"))`.

**Solution:** `List` has two `"a"` elements; `Set.of` throws `IllegalArgumentException`; `Set.copyOf` creates a set of size `1`. "Unmodifiable" does not determine the policy for duplicate input.

### Exercise 2 — Repeated Map Values

Is `Map.of("left",10,"right",10)` valid? What about `Map.of("left",10,"left",10)`?

**Solution:** The first case is valid because the keys are different. The second case throws `IllegalArgumentException` because the key is repeated, even though the values are the same.

### Exercise 3 — `null` at Which Level?

Compare `List.of((String)null)`, `List.of((String[])null)`, and `List.<String[]>of(new String[]{null})`.

**Solution:** The first two cases throw `NullPointerException`; one is a `null` element, and the other is a `null` varargs array. The third case creates a one-element list whose element is a non-`null` array, with `null` inside the array. The factory does not recursively check every slot of an array element.

### Exercise 4 — Entry Not Yet Constructed

In `Map.ofEntries(Map.entry("k",null))`, which call can fail first?

**Solution:** `Map.entry("k",null)` throws `NullPointerException` when evaluated to produce the argument. There is not yet a valid entry to pass into `Map.ofEntries`. An entry obtained from another source with a `null` key/value would also be rejected by `ofEntries` when it extracts the data.

### Exercise 5 — Two Equal Objects, Different Descriptions

Two `Label`s with different references have the same `id` and `equals`/`hashCode` based on `id`, but different `text`. Can you use `Set.copyOf` and be guaranteed to get the `text` of the first `Label`?

**Solution:** No. The result only keeps one representative from the equivalence group and does not guarantee a "first wins" rule. If differing descriptions need to be handled, you must define conflict detection or a selection criterion.

### Exercise 6 — Identical Hash Codes

Two `String`s with different contents have the same `hashCode`. Must `Set.of` reject them?

**Solution:** No. Duplication is determined by the equality relation, not by `hashCode` alone. `"FB"` and `"Ea"` in the example have the same hash yet both exist in the set.

### Exercise 7 — Error Detected Too Late

Two configuration lines `k=1` and `k=2` are read by calling `put` twice on a `HashMap`, followed by `Map.copyOf`. Will you get a duplicate-key error from the two input lines?

**Solution:** You cannot rely on the `copyOf` step to detect that history. After the second `put`, the map only holds `k=2`. You must check for repeated keys when converting the configuration lines into a map, before the information is overwritten.

### Exercise 8 — Collector with Identical Values

A `Stream` contains `"x","x"`, using `toUnmodifiableMap(identity,x→1)` without a merge function. Will the two equal values cause the collector to accept them?

**Solution:** No. Duplicate keys throw `IllegalStateException`. If you want to count occurrences, you can use a merge function that sums the counts. That is an explicitly written policy, not default behavior.

### Exercise 9 — Replacing `Stream.toList` with a Collector

A stream has one `null` element. Can you change `stream.toList()` to `collect(toUnmodifiableList())` and assume the data policy is unchanged?

**Solution:** No. `toUnmodifiableList` rejects `null`; in the example `Stream.toList` retains `null`. Both yield unmodifiable results, but their input conditions differ.

### Exercise 10 — Switching from `singleton` to `of`

Legacy code uses `Collections.singletonMap(null,null)`. Can it be replaced directly with `Map.of(null,null)` to make it shorter?

**Solution:** That does not preserve behavior. `singletonMap` in the example allows that mapping; `Map.of` rejects `null`. Before replacing, you must decide how missing data should be represented and validated.

### Exercise 11 — Same Array Contents

`a` and `b` are two distinct `int[]` objects, both containing `1,2`. Must `Set.of(a,b)` treat them as duplicates?

**Solution:** No. Ordinary arrays use object-identity equality and do not automatically compare contents. Repeating the exact same reference `a` twice is a duplicate. If you need a key/set by content, use a representation with appropriate content-based `equals`/`hashCode`.

### Exercise 12 — Normalizing Before Creating a `Map`

Two codes `"A"` and `"a"` are considered one code after lowercasing. If creating a `Map` directly from raw data reports no duplicates, does that prove the data is valid under business rules?

**Solution:** Not yet. Key equality after normalization differs from `equals` on raw data. You must normalize according to a defined policy, then check for conflicts on the normalized keys before freezing the result.

## 14. How to Self-Verify When Using Factories in a Project

A small test suite should separate the following scenarios into independent cases:

1. Valid empty, single-element, and multi-element inputs.
2. `null` source reference for `copyOf`.
3. `null` elements; for `Map`, test both `null` keys and `null` values.
4. Equal elements/keys that are different references.
5. Elements with the same hash code that are not `equals`.
6. Repeated `Map` values with different keys.
7. Duplicate policy: reject, keep all occurrences, or merge.
8. Varargs/array cases if your API accepts arrays.
9. Do not assert `Set`/`Map` order unless a specific ordering contract was chosen.
10. Do not rely on the detection order of an input intentionally containing multiple different errors.

If the data includes mutable objects, add tests for property mutation or convert to immutable values as needed. If reading from multiple threads, also test timing and consistency when creating the result.

The programs in this lesson print exception names or deterministic values to distinguish contracts, without relying on internal class names, error messages, or arbitrary set/map order.

## 15. References

- [List — `of` and `copyOf` factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).
- [Set.copyOf — deduplicating elements and selecting a representative](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- [Map — `of`, `ofEntries`, `entry`, and `copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).
- [Collectors — unmodifiable collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Guide to creating unmodifiable lists, sets, and maps](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html).
- [Collections — `singleton`, `nCopies`, and wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).
