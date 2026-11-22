# Converting a List to a Set and Its Consequences for Duplicates and Ordering

## 1. From a List of Occurrences to a Set of Values

A `List` answers two questions: "which elements are present?" and "at which positions, and how many times, do they appear?". A `Set` focuses on whether an element belongs to the set; it does not store multiple elements that are considered duplicates under that set's rules.

Therefore, converting a `List` to a `Set` is a decision about data semantics. A sequence of user actions, a list of scanned items, or a state history may contain completely valid repetitions. If each occurrence carries its own meaning, deduplication can discard essential information.

For example, the following list of fruit names has five occurrences:

```text
[pear, apple, pear, banana, apple]
```

If the requirement is "the names that appeared, keeping whichever name was encountered first earlier", the appropriate result is:

```text
[pear, apple, banana]
```

If the requirement is "the distinct names in natural string order", the result is:

```text
[apple, banana, pear]
```

Both results contain the same three names, but they provide two different iteration orders. Neither tells you anymore that `pear` and `apple` each appeared twice.

There are three decisions to clarify before writing a conversion statement:

1. **By what criterion are elements duplicates?** Are two objects equal according to `equals`, or do they merely share the same business key?
2. **In what order should iteration happen?** No ordering needed, preserving first-encountered order, or sorted?
3. **What information must be preserved?** Only the unique values, or also counts, positions, and representative objects?

This lesson answers those three questions in turn using standalone Java programs. Each program is saved in a file matching its `public class` name and compiled with JDK 17 or later. The commands use `--release 17` to keep the code within Java 17.

## 2. Choosing a Set Type Based on Ordering Semantics

`Set` is an interface. Declaring a variable as `Set<String>` does not by itself determine iteration order; the concrete class and how the result is constructed determine it.

| Requirement | Creation from List | Duplicate Rule | Iteration Order |
| --- | --- | --- | --- |
| Only need a set of unique values | `new HashSet<>(source)` | `equals` with the `hashCode` contract | Not guaranteed |
| Preserve first-encountered value order | `new LinkedHashSet<>(source)` | `equals` with the `hashCode` contract | Order of first insertion |
| Both deduplicate and sort naturally | `new TreeSet<>(source)` | Natural comparison returning `0` | Natural order |
| Sort by a custom criterion | Create `TreeSet` with a `Comparator`, then `addAll(source)` | Comparator returning `0` | Comparator order |
| Create an unmodifiable set, no ordering needed | `Set.copyOf(source)` | Elements equal according to `equals` | Not guaranteed |

In the table, `source` is a valid `List`. The expressions shown are illustrative; the complete programs below include all declarations and `import` statements.

### HashSet Makes No Guarantee to Preserve List Order

`HashSet` does not guarantee iteration order, even if a particular run happens to produce the desired order. "Not guaranteed" also does not mean every run is sure to change order or shuffle randomly. Your program must be correct under any ordering permitted by the set's contract. [HashSet Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

Accordingly, do not use the string printed directly from a `HashSet` as proof that the conversion preserves order. If you need to inspect the values in an example, you can sort them separately for display while noting clearly that this is an extra step.

### LinkedHashSet Preserves First Occurrence Order

When iterating over a `List` and inserting elements into a `LinkedHashSet`, a new element is appended at the end of the iteration order. Re-inserting an element that is already present does not move it to the end. Thus, the sequence `[B, A, B, C, A]` becomes `[B, A, C]`. [LinkedHashSet Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

This is the order of first-encountered values, not the order of last occurrences. If a different policy is needed, you must specify and implement that policy separately.

### TreeSet Applies Sorted Order

`TreeSet` does not preserve the encounter order from the `List`. It organizes elements according to their natural ordering or a supplied `Comparator`. Alongside ordering, the comparison result also determines which elements are considered duplicates; this detail is verified in section 6.

## 3. Experiment: One List, Three Ordering Choices

Save the following program to `ListToSetOrderDemo.java`.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class ListToSetOrderDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("pear", "apple", "pear", "banana", "apple"));
        Set<String> hashed = new HashSet<>(source);
        Set<String> firstOrder = new LinkedHashSet<>(source);
        Set<String> sorted = new TreeSet<>(source);
        Set<String> collected = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println("source=" + source);
        System.out.println("sourceSize=" + source.size());
        System.out.println("hashSize=" + hashed.size());
        System.out.println("hashSortedForDisplay=" + new TreeSet<>(hashed));
        System.out.println("firstOrder=" + firstOrder);
        System.out.println("sorted=" + sorted);
        System.out.println("collected=" + collected);

        List<String> uniqueList = new ArrayList<>(firstOrder);
        System.out.println("uniqueList=" + uniqueList);
        System.out.println("restoresSource=" + uniqueList.equals(source));
        source.add("kiwi");
        System.out.println("setContainsNewSourceValue="
                + firstOrder.contains("kiwi"));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListToSetOrderDemo.java
java ListToSetOrderDemo
```

Stdout:

```text
source=[pear, apple, pear, banana, apple]
sourceSize=5
hashSize=3
hashSortedForDisplay=[apple, banana, pear]
firstOrder=[pear, apple, banana]
sorted=[apple, banana, pear]
collected=[pear, apple, banana]
uniqueList=[pear, apple, banana]
restoresSource=false
setContainsNewSourceValue=false
```

Reading the output by each data transformation:

- `sourceSize=5`, while `hashSize=3`: repeated occurrences have been collapsed.
- `firstOrder=[pear, apple, banana]`: `LinkedHashSet` preserves the order in which the three names were first encountered.
- `sorted=[apple, banana, pear]`: `TreeSet` sorts the names by the natural ordering of `String`.
- `collected` matches `firstOrder`: the program explicitly requested a `LinkedHashSet` when collecting elements from the stream.
- `restoresSource=false`: converting the set back to a `List` produces a new list, but it does not restore the dropped occurrences.
- `setContainsNewSourceValue=false`: adding `kiwi` to the list after creating the set does not automatically add it to the set.

The `hashSortedForDisplay` line uses `new TreeSet<>(hashed)` to obtain stable display output. The `[apple, banana, pear]` order on that line belongs to the newly created `TreeSet`, not a guarantee about `HashSet` ordering.

Printing `source` before the `source.add("kiwi")` step is also intentional: the first line describes the input at conversion time. The addition at the end verifies structural independence afterward.

### Why Set to List Is Not an Inverse Operation

Consider three lists:

```text
[B, A]
[B, A, B]
[B, B, A, A]
```

All three produce the exact same `LinkedHashSet` with order `[B, A]`. From the resulting set, there is no way to deduce which list was the original.

The lost information includes:

- The occurrence count of each value.
- The positions of the collapsed occurrences.
- The complete original sequence.
- Which equal objects were not retained.

If you only need a deduplicated `List` that preserves first-encountered order, `new ArrayList<>(new LinkedHashSet<>(source))` satisfies that requirement. The resulting list remains mutable and supports index-based access, but it contains only the selected values after deduplication.

## 4. "Equal" Does Not Mean "The Same Object"

With `HashSet` and `LinkedHashSet`, two distinct references can still be treated as the same element if the objects are equal according to `equals`. `hashCode` must obey its contract: equal objects must have the same hash code. Objects with the same hash code are not necessarily equal; a hash collision does not mean the set merges all objects in the same hash bucket.

This directly affects business data conversion. Suppose two contact objects have the same `id` but different display labels. If `equals` is based only on `id`, the set may keep only one object. The set does not automatically merge the labels, nor does it decide that the later record is newer and should replace the earlier one.

Custom classes must also define the right equality criterion. If a class uses the default `equals` from `Object`, two separately created objects generally remain distinct, even if their fields hold the exact same data. Converting to a set does not inspect all fields to infer a business key.

### Experiment on Representative Objects and Reference Sharing

Save to `SetEqualityAndSharingDemo.java`.

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class SetEqualityAndSharingDemo {
    static final class Contact {
        private final int id;
        private String label;

        Contact(int id, String label) {
            this.id = id;
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Contact contact && id == contact.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Contact earlier = new Contact(1, "earlier");
        Contact later = new Contact(1, "later");
        Contact other = new Contact(2, "other");
        List<Contact> source =
                new ArrayList<>(List.of(earlier, later, other));
        Set<Contact> result = new LinkedHashSet<>(source);
        Contact retained = result.iterator().next();

        System.out.println("sourceSize=" + source.size());
        System.out.println("setSize=" + result.size());
        System.out.println("equalById=" + earlier.equals(later));
        System.out.println("retainedIsEarlier=" + (retained == earlier));
        System.out.println("retainedLabel=" + retained.label);

        earlier.label = "edited";
        source.clear();
        System.out.println("labelAfterEdit=" + retained.label);
        System.out.println("setSizeAfterSourceClear=" + result.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SetEqualityAndSharingDemo.java
java SetEqualityAndSharingDemo
```

Stdout:

```text
sourceSize=3
setSize=2
equalById=true
retainedIsEarlier=true
retainedLabel=earlier
labelAfterEdit=edited
setSizeAfterSourceClear=2
```

The two objects `earlier` and `later` share `id=1`, so `equals` returns `true`. `LinkedHashSet` receives `earlier` first. Attempting to add `later` neither gives the set a third element nor replaces the retained object.

Consequently:

- `retainedIsEarlier=true` checks object identity directly with `==`.
- `retainedLabel=earlier` shows that data from a later equal object does not overwrite the existing one.
- `labelAfterEdit=edited` shows that the element in the set is still the very same object referenced from the list earlier.
- `setSizeAfterSourceClear=2` shows that clearing the list's structure does not clear the created set's structure.

The example intentionally keeps `id` as `final`; the `label` field does not participate in `equals` or `hashCode`. Changing `label` therefore does not alter the element's identity criterion inside the set.

If a field participating in `equals` or `hashCode` changes while the object is still in a hash-based set, lookup or removal operations may no longer behave as expected. Do not rely on converting to `HashSet` or `LinkedHashSet` to "freeze" those fields; the set does not protect element objects from mutation.

## 5. A New Container and a Deep Copy Are Two Different Things

The constructors `new HashSet<>(source)`, `new LinkedHashSet<>(source)`, and `new TreeSet<>(source)` create a new container structure. The resulting set is not a live view that updates with every addition or removal on the source list.

However, they do not create new copies of each element object:

```text
Source List ──references──> Contact object
                                ↑
New Set     ──references────────┘
```

The diagram only illustrates reference relationships. Some duplicate elements may not enter the set, but each retained element is still the existing object.

From this, two requirements must be separated:

1. **Structural independence:** adding or removing elements in the list does not automatically add or remove elements in the new set.
2. **Element state independence:** mutating an object on one side does not affect the object seen on the other side.

Conversion constructors satisfy the first requirement. To satisfy the second, you must use immutable elements or copy elements according to your data model's rules. Creating an unmodifiable set does not by itself satisfy the second requirement either.

If two objects are equal yet carry different remaining fields, clearly decide whether to keep the first record, keep the last record, reject duplicates, or merge information. For key-based merging requirements, a `Map` with a conflict-resolution policy usually expresses intent more clearly than simply placing objects into a `Set`.

## 6. TreeSet Can Deduplicate by a Criterion Different from equals

For a sorted set, comparison does two jobs: determining sorted position and determining whether two elements occupy the same position. If the comparison result is `0`, `TreeSet` treats them as duplicates.

That creates a trap when using a `Comparator` merely to "change how elements are displayed". For example, case-insensitive string comparison puts `"Java"`, `"java"`, and `"JAVA"` into the same bucket, even though `String.equals` treats them as three distinct strings.

A `TreeSet` should have an ordering consistent with `equals` to fully obey the general `Set` contract. The program below intentionally uses a comparator inconsistent with `String.equals` to observe the effect, not as a default pattern for all string sets. [TreeSet Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

Save to `TreeSetDuplicateRuleDemo.java`.

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class TreeSetDuplicateRuleDemo {
    public static void main(String[] args) {
        List<String> source = List.of("Java", "java", "JAVA", "SQL", "Java");
        Set<String> byEquals = new HashSet<>(source);
        Set<String> natural = new TreeSet<>(source);
        Set<String> caseInsensitive = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        caseInsensitive.addAll(source);

        Set<String> normalized = new LinkedHashSet<>();
        for (String value : source) {
            normalized.add(value.toLowerCase(Locale.ROOT));
        }

        System.out.println("equalsSize=" + byEquals.size());
        System.out.println("naturalSize=" + natural.size());
        System.out.println("natural=" + natural);
        System.out.println("ignoreCaseSize=" + caseInsensitive.size());
        System.out.println("ignoreCase=" + caseInsensitive);
        System.out.println("stringEquals=" + "Java".equals("java"));
        System.out.println("compareAsSame="
                + (String.CASE_INSENSITIVE_ORDER.compare("Java", "java") == 0));
        System.out.println("normalized=" + normalized);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeSetDuplicateRuleDemo.java
java TreeSetDuplicateRuleDemo
```

Stdout:

```text
equalsSize=4
naturalSize=4
natural=[JAVA, Java, SQL, java]
ignoreCaseSize=2
ignoreCase=[Java, SQL]
stringEquals=false
compareAsSame=true
normalized=[java, sql]
```

There are five occurrences in the input. The string `"Java"` appears twice, whereas the three casings `"Java"`, `"java"`, and `"JAVA"` are not equal under `String.equals`.

Read the output as follows:

- `equalsSize=4`: `HashSet` collapses only the two occurrences of the exact string `"Java"`.
- `naturalSize=4`: `String` natural ordering also distinguishes those casing variants.
- `natural=[JAVA, Java, SQL, java]`: this is the natural ordering of the strings in the example, not a locale-sensitive collation rule for every user interface.
- `ignoreCaseSize=2`: the case-insensitive comparator collapses all three casings of Java into one element.
- `stringEquals=false` yet `compareAsSame=true`: the same pair of strings is identified differently by the two mechanisms.
- `normalized=[java, sql]`: the program explicitly converts strings to lowercase before inserting them into `LinkedHashSet`.

### Key Normalization Is an Intentional Choice

The normalization snippet uses `Locale.ROOT` so lowercasing does not depend on the machine's default locale. After normalization, the set holds the transformed strings themselves, so `equals` operates on the chosen form.

In exchange, the result does not preserve the original casing. If you need to keep `"Java"` for display while detecting duplicates by the key `"java"`, you must store both the normalized key and the representative value, and specify whether to keep the first or last spelling.

Nor should "lowercasing" be treated as the right normalization rule for every kind of data. Identifiers, person names, addresses, and display strings may each have their own contracts. The takeaway is to choose the equality rule first, then choose the structure that accurately expresses that rule.

A similar bug happens when using a comparator that only checks string length: two distinct names with the same length yield a comparison result of `0`. If the goal is only to sort elements while keeping all distinct elements, the comparison criterion must break ties among elements that are equal on the primary criterion, or you should use a `List` and sort it instead of converting to a `TreeSet`.

## 7. Null Handling and Mutability Also Change by Conversion Method

There is no universal rule that every `List`-to-`Set` conversion accepts `null`, or that every resulting set allows adding elements.

| Creation Method | When Source Has Multiple nulls | Add or Remove on Resulting Set |
| --- | --- | --- |
| `new HashSet<>(source)` | Keeps at most one `null` | Allowed |
| `new LinkedHashSet<>(source)` | Keeps at most one `null`, at its first-encountered position | Allowed |
| `new TreeSet<>(source)` in natural order | Throws `NullPointerException` | Allowed if constructed successfully |
| `Set.copyOf(source)` | Throws `NullPointerException` | Not allowed |
| `Collections.unmodifiableSet(new LinkedHashSet<>(source))` | Backing set keeps at most one `null` | Not allowed through the wrapper |

The `TreeSet` row specifically describes natural ordering. You can supply a comparator that handles `null` explicitly; do not infer that every `TreeSet` configuration behaves identically.

`Set.copyOf` accepts a `Collection`, so it can take a `List` directly. It accepts duplicate elements and retains an arbitrary representative element from each equal group; it does not promise to keep the first-encountered object. The result is structurally unmodifiable, rejects `null` elements, and makes no iteration-order guarantee. [Set.copyOf Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection))

The "arbitrary representative" point matters when elements are objects like `Contact` from the previous section: two objects may be equal by ID while carrying different labels. Do not replace `new LinkedHashSet<>(source)` with `Set.copyOf(source)` while still relying on keeping the first object.

### Experiment on null, Deduplication, and Read-Only Sets

Save to `SetNullAndReadOnlyDemo.java`.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SetNullAndReadOnlyDemo {
    public static void main(String[] args) {
        List<String> withNull = Arrays.asList("A", null, "A", null, "B");
        Set<String> firstOrder = new LinkedHashSet<>(withNull);
        Set<String> hashed = new HashSet<>(withNull);
        System.out.println("firstOrder=" + firstOrder);
        System.out.println("hashSize=" + hashed.size());
        System.out.println("hashContainsNull=" + hashed.contains(null));

        try {
            new TreeSet<>(withNull);
        } catch (NullPointerException e) {
            System.out.println("naturalTree=NullPointerException");
        }
        try {
            Set.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("copyWithNull=NullPointerException");
        }

        Set<String> readOnly = Set.copyOf(List.of("B", "A", "B"));
        System.out.println("copySize=" + readOnly.size());
        System.out.println("copySortedForDisplay=" + new TreeSet<>(readOnly));
        try {
            readOnly.add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("copyAdd=UnsupportedOperationException");
        }

        Set<String> orderedReadOnly = Collections.unmodifiableSet(
                new LinkedHashSet<>(List.of("B", "A", "B")));
        System.out.println("orderedReadOnly=" + orderedReadOnly);
        try {
            Set.of("A", "A");
        } catch (IllegalArgumentException e) {
            System.out.println("ofDuplicate=IllegalArgumentException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SetNullAndReadOnlyDemo.java
java SetNullAndReadOnlyDemo
```

Stdout:

```text
firstOrder=[A, null, B]
hashSize=3
hashContainsNull=true
naturalTree=NullPointerException
copyWithNull=NullPointerException
copySize=2
copySortedForDisplay=[A, B]
copyAdd=UnsupportedOperationException
orderedReadOnly=[B, A]
ofDuplicate=IllegalArgumentException
```

In the first part, the source list is created with `Arrays.asList` so it can contain `null`. Using `List.of` here would fail immediately when creating the source, before testing the conversion to a set.

The output confirms:

1. `LinkedHashSet` keeps `[A, null, B]`: the two `"A"` values are collapsed and the two `null` values are also collapsed.
2. `HashSet` has three elements and contains `null`. The program checks size and membership rather than predicting print order.
3. `TreeSet` in natural order and `Set.copyOf` reject input containing `null`.
4. `Set.copyOf(List.of("B", "A", "B"))` produces a two-element set. The `copySortedForDisplay` line sorts a copy solely for display.
5. Calling `add` on the set returned by `Set.copyOf` throws `UnsupportedOperationException`.
6. The set wrapped with `Collections.unmodifiableSet` still iterates according to the backing `LinkedHashSet`, yielding `[B, A]`.
7. `Set.of("A", "A")` throws `IllegalArgumentException`; this call does not share `Set.copyOf`'s policy when given duplicate data.

The `catch` blocks print a fixed label for each caught case instead of printing the full exception message. As a result, stdout does not depend on machine paths or JDK-version message details.

### "Unmodifiable" Does Not Mean Preserving Order

Two requirements must be chosen independently:

- `Set.copyOf` fits when you need an unmodifiable result and do not depend on ordering.
- If you need to preserve first-encountered order while preventing the receiver from adding or removing elements, you can create a `LinkedHashSet` and wrap it with `Collections.unmodifiableSet`.

`Collections.unmodifiableSet` creates a read-only view of the backing set. If another part of the program retains a reference to the backing set and mutates it, the view reflects those changes. Therefore, to protect a structural snapshot, create a dedicated backing copy and do not expose any handle to mutate that copy. [Collections.unmodifiableSet Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

The example in the program creates the new `LinkedHashSet` directly inside the wrapper call. The source list is not the wrapper's backing set. However, element objects can still be shared; neither the wrapper nor `Set.copyOf` performs a deep copy of elements.

## 8. Using Streams Still Requires Choosing an Ordering Contract

If you already have a `List` and only need a direct conversion, a constructor is usually clear enough:

```java
// Illustrative snippet; source is an existing List<String>.
Set<String> unique = new LinkedHashSet<>(source);
```

If you also need to filter or transform elements in a stream, you must choose the appropriate collector:

```java
// Illustrative snippet; place inside a method with source and the required imports.
Set<String> uniqueInFirstOrder = source.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

For an ordered stream from the `List` in the example, the result preserves first-encountered value order. `ListToSetOrderDemo` already verified this exact expression.

Do not replace that expression with `Collectors.toSet()` when ordering is part of the requirement. `toSet()` makes no guarantee about the concrete set type, mutability, or encounter order. To specify the container class, use `toCollection` with the corresponding constructor. [Collectors.toSet and toCollection Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)

For instance, a filtering step can change which elements are encountered; a sorting step can change the order in which they are encountered. `LinkedHashSet` only preserves the order in which elements are actually fed into it—it does not recover the list's order from an earlier stage in the pipeline.

Choosing between a stream and a constructor is therefore a choice of how to express the pipeline. It does not remove the need to specify the duplicate criterion, ordering, and mutability of the result.

## 9. When Occurrence Counts Still Matter, Keep Extra Data

Converting to a `Set` is not a way to count. If the input is `[B, A, B, C, A, B]`, the set of unique values is just `[B, A, C]`. From that set, you cannot tell that `B` appeared three times, `A` twice, and `C` once.

You also need to distinguish two numbers:

- **Dropped occurrences:** list size minus unique set size.
- **Repeated value count:** how many distinct values appeared two or more times.

For the input above, there are three dropped occurrences, but only two repeated values (`B` and `A`).

A hash set's `add` method returns `false` when the element is already present and the set is unchanged. You can use that return value during iteration to detect duplicates, rather than deduplicating first and trying to reconstruct the source data afterward.

Save the following program to `DuplicatesAndCountsDemo.java`.

```java
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class DuplicatesAndCountsDemo {
    public static void main(String[] args) {
        List<String> source = List.of("B", "A", "B", "C", "A", "B");
        Set<String> seen = new LinkedHashSet<>();
        Set<String> repeated = new LinkedHashSet<>();
        Map<String, Integer> counts = new LinkedHashMap<>();

        for (String value : source) {
            if (!seen.add(value)) {
                repeated.add(value);
            }
            counts.put(value, counts.getOrDefault(value, 0) + 1);
        }

        System.out.println("sourceSize=" + source.size());
        System.out.println("uniqueFirstOrder=" + seen);
        System.out.println("repeatedValues=" + repeated);
        System.out.println("counts=" + counts);
        System.out.println("droppedOccurrences=" + (source.size() - seen.size()));
        System.out.println("repeatedValueCount=" + repeated.size());
        System.out.println("hasDuplicates=" + !repeated.isEmpty());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DuplicatesAndCountsDemo.java
java DuplicatesAndCountsDemo
```

Stdout:

```text
sourceSize=6
uniqueFirstOrder=[B, A, C]
repeatedValues=[B, A]
counts={B=3, A=2, C=1}
droppedOccurrences=3
repeatedValueCount=2
hasDuplicates=true
```

The program maintains three structures for three distinct purposes:

| Variable | Information Kept | With the Program's Input |
| --- | --- | --- |
| `seen` | Values encountered, in first-encountered order | `[B, A, C]` |
| `repeated` | Values encountered again at least once | `[B, A]` |
| `counts` | Occurrence count for each value | `{B=3, A=2, C=1}` |

In the loop:

1. `seen.add(value)` attempts to record a new value.
2. If the result is `false`, that value has already been seen, so it is added to `repeated`.
3. `counts` increments the counter on every occurrence, including repeats.

`LinkedHashMap` is used so the count table prints in the order keys first appeared. Updating the counter for an existing key does not turn that order into last-occurrence order.

In this example, the order of `repeated` is the order in which repeated values were detected: `B` was seen again first, then `A`. Do not generalize that this order always matches first-encountered order. For example, in `[A, B, B, A]`, the first value detected as a duplicate is `B`, even though `A` appeared first in the source.

### Detecting Invalid Input Differs from Silent Deduplication

If the contract says "each code may be submitted only once", converting straight to a set and continuing processing hides the violation. In that case, you should check and report an error explicitly.

Under the same equality criterion as `HashSet` or `LinkedHashSet`, comparing the source size against the set size can tell you whether at least one repeat occurred. If you need to report which codes were repeated, iterating with `add` as in the program above lets you keep the necessary evidence.

If you use a `TreeSet` with a comparator different from `equals`, a smaller size could occur because two elements differ under `equals` yet are treated as equal by the comparator. Therefore, do not use an arbitrary `TreeSet` to check for "duplicates by equals".

If you need to report all offending positions, you must also record indices while iterating over the list. A set storing only unique values does not hold enough positional information for such error reporting.

## 10. Choosing a Conversion in Real-World Scenarios

### A Label List Displayed in User-Entered Order

Requirement: remove duplicate labels while keeping the first-encountered label, with stable display order matching input.

Choose `LinkedHashSet`. If the UI still needs a `List` afterward, create an `ArrayList` from the set as in the first program. Agree upfront on whether whitespace or letter case makes two labels distinct; the constructor does not normalize those details automatically.

### A Set of Codes for Membership Checks

Requirement: answer "did this code appear?", without using iteration order as output data.

`HashSet` is usually the direct choice when `equals` and `hashCode` are appropriate. Basic operations have expected constant-time cost with a well-distributed hash function; converting n elements generally has expected linear-time cost under that condition. This is not a guarantee that every input has identical runtime.

If you still need the original list to represent each action, keep both the list and the lookup set for their separate roles. Adding a helper set does not require discarding the list.

### Unique Values That Need Sorting

Requirement: at most one element per value under the chosen rule, plus ordered iteration.

Choose `TreeSet` with natural ordering or an appropriate comparator. With element-by-element insertion, add operations have logarithmic cost in the set size; converting n elements is typically analyzed as O(n log n), aside from the actual comparison cost.

If all occurrences must remain, keep a `List` and sort the list. Sorting does not by itself require deduplication.

### Statistical or Transactional Data

Requirement: the same code can appear multiple times and each occurrence affects the result.

Keep the `List`, or build a `Map` of counts, or keep each record with its corresponding quantity. Keep only a `Set` when the question truly requires only presence.

For example, a shopping cart representing each scan as an element cannot be converted to a set and have the set size used as the total item count. Two scans of the same code may be two units of goods, not bad data.

### An Object List Requiring a Representative Record

Requirement: keep only one record per business key, though records may carry different data.

First choose the policy: first record, last record, latest timestamp, or conflict error. `LinkedHashSet` fits keeping the first-encountered equal object when `equals` matches the criterion. Other policies must be expressed explicitly, usually by key-based handling in a `Map`.

Do not let an accident of source order or set implementation become an invisible business policy to readers of the code.

## 11. Mistakes to Catch When Reading or Modifying Code

| Common Misconception or Pattern | Consequence | Fix According to Requirements |
| --- | --- | --- |
| "Every Set preserves List order" | Output order depends on set type and may not be guaranteed | Choose `LinkedHashSet` when first-occurrence order is needed |
| "HashSet printed the right order on my machine, so it's fine" | Relies on unguaranteed behavior | Check the API contract; sort separately if ordered display is needed |
| "Converting Set back to List restores the source" | Cannot recover dropped counts or positions | Keep the source or save needed data before converting |
| "If visible data matches, Set merges them automatically" | The class may lack `equals` and `hashCode` for the desired criterion | Define the equality criterion or convert by an appropriate key |
| "Duplicate key means keep the last record" | `LinkedHashSet` does not replace the first object with a later one | Use an explicit representative-selection policy |
| "Comparator only affects sorting" | `compare(a, b) == 0` also controls deduplication in `TreeSet` | Check the comparison criterion and consistency with `equals` |
| "Set.copyOf must throw on duplicate input" | Confused with `Set.of`; misunderstands representative element | Distinguish the two APIs and check duplicate requirements |
| "A new Set means elements were copied" | Mutating an object is visible from both structures | Use immutable elements or explicit copying rules |
| "An unmodifiable set preserves existing order" | Mutability and ordering are two separate contracts | Choose both the set type and how to protect the result |
| "After deduplicating, you can still count occurrences" | Only presence remains; frequency is lost | Count while original data is still available or keep a count map |

When the source is empty, valid conversions produce an empty set. When the source reference itself is `null`, that is a different case from a list containing a `null` element; handle the input according to the receiving method's contract. Do not use the rule "HashSet can contain null" to conclude that the constructor accepts a `null` source `Collection`.

## 12. Practice: Accurately Predicting Remaining Data

### Exercise 1: One Source, Two Ordering Rules

Given the list `[C, A, C, B, A]`, predict the result when converting to `LinkedHashSet` and to `TreeSet` in natural order. Can you accurately predict the direct print order of `HashSet` from the API contract?

**Answer Key:**

- `LinkedHashSet`: `[C, A, B]`.
- `TreeSet`: `[A, B, C]`.
- `HashSet`: contains the three elements `A`, `B`, `C`, but its print order cannot be predicted from the contract.
- None of the three still tells you the occurrence counts or positions of each letter in the source.

### Exercise 2: Dropped Occurrences and Repeated Values

Given the list `[A, A, A, B, B, C]`, if deduplicating by `String.equals`, how many occurrences are dropped? How many values are repeated?

**Answer Key:**

The source has six elements and three unique values, so three occurrences are dropped. Two values are repeated: `A` and `B`. To know the individual count of each value, you need the source or a count map; the set `[A, B, C]` is not enough.

### Exercise 3: Duplicate Detection Order

Replace the input in `DuplicatesAndCountsDemo` with `List.of("A", "B", "B", "A")`. Before running it, write down the results of `seen`, `repeated`, and `counts`.

**Answer Key:**

- `seen` has order `[A, B]`.
- `repeated` has order `[B, A]`, because the repeat of `B` is detected first.
- `counts` has contents and order `{A=2, B=2}`.
- There are two dropped occurrences and two repeated values.

This exercise tests not equating first-encountered order with duplicate-detection order.

### Exercise 4: Selecting One Object by Key

Two contact objects with `id=1` have labels `old` and `new`; the source puts `old` first. `equals` and `hashCode` are based only on `id`. After converting to `LinkedHashSet`, which label is kept? If you want to keep `new`, does switching to `Set.copyOf` solve the requirement?

**Answer Key:**

`LinkedHashSet` keeps the object with label `old`. `Set.copyOf` does not promise to keep the last object, so it does not express the requirement "keep new". You must write an explicit policy to select the last or newest record, such as when inserting data into a `Map` keyed by `id`.

### Exercise 5: Data That Must Not Lose Occurrences

The list `[P1, P1, P2]` represents three item scans. The processing component only receives the set `{P1, P2}`. Can it accurately compute the total of three item units from that set without other data?

**Answer Key:**

No. That set could also have come from `[P1, P2]` or many longer lists. You must keep the scans or pass quantities alongside them, such as `P1 → 2`, `P2 → 1`.

### Exercise 6: Acceptance Criteria for a Conversion

Choose your own input with duplicate elements and write a program to verify:

1. Size before and after conversion.
2. The duplicate-detection rule.
3. Whether iteration order is a mandatory requirement.
4. Which object is retained when objects are equal.
5. Whether the result is structurally modifiable.
6. Whether adding or removing in the source affects the set.
7. What happens when mutating the state of a shared object.

An acceptable solution must be able to explain why that set type was chosen. Simply printing a set that looks right on one run does not prove that the program upholds the duplicate and ordering contracts.
