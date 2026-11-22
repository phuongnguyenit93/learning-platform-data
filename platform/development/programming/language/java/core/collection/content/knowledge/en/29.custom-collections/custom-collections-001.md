# When to Implement a Custom Collection

## 1. The Decision Starts with an Unmet Requirement

Implementing a custom collection means taking responsibility for a data aggregation type with a clear usage contract: how elements are stored or represented, and how they are accessed, traversed, compared, and modified when allowed.

Having multiple elements in a problem is not enough reason to create a new collection. There are usually three distinct choices:

1. Use existing collections and configure or combine them.
2. Write a domain class that encapsulates a collection internally.
3. Implement a collection interface by providing a custom data representation or creating a new view.

A `TagCatalog` class containing a `LinkedHashSet` does not mean a new set data structure has been written. Conversely, a class extending `AbstractList` that computes elements from a formula is a new `List` implementation, even without an array holding all elements.

The third option should be considered when there is a specific gap:

- Existing data representations are unsuitable in terms of memory footprint or operation cost.
- Data or a view needs to be integrated into standard collection APIs.
- There are valid collection semantics that existing options do not satisfy.
- There is a measurable, verifiable requirement valuable enough to justify maintaining a custom implementation.

Even then, further questions must be answered: can the interface contract be properly fulfilled, can all usage paths be tested, and can long-term maintenance be sustained?

The goal is not to avoid all custom code. The goal is to choose the right part to own. If only a single business rule is missing, you should not automatically assume responsibility for an entire `List`, `Set`, or `Map`.

This article uses Java 17 or later. The four standalone programs below include filenames, compilation commands, and stdout. They illustrate the levels of choice, an intentional inheritance pitfall, and a well-justified custom collection implementation.

## 2. Check Existing Tools First

### 2.1. Most Needs Have a Closer Solution

| Practical Requirement | What to Check Before Writing a New Collection |
|---|---|
| Read-only access for the recipient | Unmodifiable view or unmodifiable copy |
| A fixed result list after taking a snapshot | Appropriate copy factory and element mutability policy |
| A LIFO queue API backed by a deque | Built-in interface adapter |
| Iteration order matching insertion order | An implementation with the appropriate iteration order |
| Elements belonging to a single enum type | `EnumSet` |
| Non-negative integer positions representable as bits | `BitSet`, if a bit-level API fits |
| Business constraints and domain-specific operation names | A domain class wrapping a collection |

`EnumSet` is a specialized set for constants of a single enum type. `BitSet` is a bit vector indexed by non-negative integers; it does not directly implement `Set<Integer>`. Both representational capability and the actual interface required by callers must be compared. See [EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html) and [BitSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html).

An existing data structure that meets the requirement reduces the amount of contract surface you must manage yourself. That is a benefit in verifiability and maintainability, not just lines of code.

### 2.2. Program with Views, Copies, and Adapters

File `ExistingToolsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Queue;

public class ExistingToolsDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("alpha", "beta"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("gamma");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        try {
            view.add("delta");
        } catch (UnsupportedOperationException ex) {
            System.out.println("viewWrite=" + ex.getClass().getSimpleName());
        }

        Queue<String> stackView =
                Collections.asLifoQueue(new ArrayDeque<String>());
        stackView.offer("A");
        stackView.offer("B");
        System.out.println("lifo=" + stackView.poll() + "," + stackView.poll());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ExistingToolsDemo.java
java ExistingToolsDemo
```

Stdout:

```text
view=[alpha, beta, gamma]
snapshot=[alpha, beta]
viewWrite=UnsupportedOperationException
lifo=B,A
```

An `unmodifiableList` view prevents modification through the view itself while still reading from the backing source. When `"gamma"` is added to the source, the view reflects that change.

`List.copyOf` creates a list that does not reflect subsequent structural changes to the source. In this example, the elements are immutable strings, making the difference easy to observe. Structural copying is not automatically a deep copy of mutable element objects. See [unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) and [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

The second part uses `Collections.asLifoQueue` to view a deque as a LIFO queue. `B` is offered after `A` and polled before `A`. If only this perspective is needed, there is no need to implement a custom queue class with a new storage algorithm.

The lesson from this example is to state the requirement accurately. "Cannot be modified through the returned API" and "result does not change when the source changes" are two different things. A custom collection has no special privilege to ignore that distinction.

### 2.3. Combining Data Structures Does Not Necessarily Mean a New Collection

If an application needs both ordering and key-based lookup, it may need to combine structures or introduce an index-management class. That combination carries its own consistency cost: adding, removing, or replacing data must properly update all related parts.

Even so, that logic can live inside a domain class exposing a few clear operations. It does not have to be exposed as a new `List` or `Map`.

A narrow API usually makes it easier to preserve clear mutation boundaries. Callers cannot arbitrarily perform every update operation simply because they hold a reference to a broad collection interface.

## 3. Business Rules Usually Fit a Wrapper Class

### 3.1. When Operation Names Express More Than add and remove

Suppose an application manages text tags:

- Strip leading and trailing whitespace.
- Normalize to lowercase according to a chosen rule.
- Reject blank values.
- Prevent duplicate registration based on the normalized form.
- Return a list in registration order.

This is a registration workflow with its own data identity rules. Callers need `register`, `isRegistered`, and `snapshot`—not full permission to replace arbitrary indices, mutate via iterators, or slice sublists.

File `DomainWrapperDemo.java`:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class DomainWrapperDemo {
    static final class TagCatalog {
        private final LinkedHashSet<String> tags = new LinkedHashSet<>();

        private static String normalize(String input) {
            String value = Objects.requireNonNull(input, "input")
                    .strip().toLowerCase(Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("tag must not be blank");
            }
            return value;
        }

        boolean register(String input) {
            return tags.add(normalize(input));
        }

        boolean isRegistered(String input) {
            return tags.contains(normalize(input));
        }

        List<String> snapshot() {
            return List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        var catalog = new TagCatalog();
        System.out.println("first=" + catalog.register(" Java "));
        System.out.println("duplicate=" + catalog.register("java"));
        System.out.println("second=" + catalog.register("SPRING"));
        List<String> before = catalog.snapshot();
        catalog.register("Gradle");

        System.out.println("before=" + before);
        System.out.println("now=" + catalog.snapshot());
        System.out.println("find=" + catalog.isRegistered(" JAVA "));
        try {
            catalog.register("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DomainWrapperDemo.java
java DomainWrapperDemo
```

Stdout:

```text
first=true
duplicate=false
second=true
before=[java, spring]
now=[java, spring, gradle]
find=true
invalid=IllegalArgumentException
```

The class uses `LinkedHashSet` internally to preserve uniqueness and registration order; insertion-ordered iteration is a built-in property of that class. See [LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

The two inputs `" Java "` and `"java"` resolve to the same tag under `TagCatalog`'s policy. The `false` result on the second registration is a well-defined domain outcome, not an arbitrary alteration to a general-purpose collection contract.

The `before` list is captured prior to registering `"Gradle"`, so it does not change as the catalog evolves. The backing collection is never exposed directly to the outside.

### 3.2. This Class Does Not Assume the Responsibilities of Set

`TagCatalog` does not declare itself as a `Set<String>`. It can define its own input normalization rules without forcing recipients of a standard `Set` to guess what `contains` or `equals` mean.

If you tried to build a collection that stores only normalized strings, you would have to re-evaluate the entire contract. For instance, if `add(" Java ")` returns normally while `contains(" Java ")` returns `false`, that cannot be treated as a standard `Collection.add` implementation fulfilling its contract without issue.

A wrapper class also restricts mutation paths: every registration passes through a single normalization function rather than requiring you to police dozens of mutator methods inherited from a public superclass.

### 3.3. Keep the Scope of the Example Clear

This example is single-threaded and provides no concurrency contract. Using an existing collection internally does not automatically make multi-step wrapper methods thread-safe under concurrent calls.

`Locale.ROOT` is a deliberate normalization choice for this example. Tag identity in a real product might require different rules; those rules must be specified before choosing the backing collection.

If operations such as "rename tag" or "merge tags" are needed later, they can be added as explicit domain operations with their own invariants. There is no need to open up every set mutation method to all callers.

## 4. Genuine Reasons That Can Lead to a New Implementation

### 4.1. Specialized Representation That Still Needs a Standard Interface

A numeric sequence can be defined by its initial term, common difference (step), and element count. If a caller needs a `List<Integer>` for positional access, there is no need to allocate and store every number upfront.

This is a concrete reason for a custom implementation: store a compact description and compute values on demand, while still providing a finite size and a well-defined positional order.

Compressed representations, custom memory regions, or computed views can also fall into this category. Each case must clearly define the data semantics and the cost of operations that the API may trigger.

### 4.2. Operational Models Not Satisfied by Existing Structures

If data requires specialized access patterns, a custom algorithm or index structure may be necessary. Before implementing one, however, you must characterize the workload:

- Which operations occur most frequently?
- What is the ratio of reads, insertions, and removals?
- How large is the dataset?
- Does the observed bottleneck lie in the data structure or in external processing?
- Which metric does the new solution improve, and what trade-offs does it make?

"It seems faster" is not a sufficiently clear requirement. If profiling shows that the cost is dominated by network queries or input parsing, rewriting a collection will not solve the primary problem.

### 4.3. Creating a View for Interoperability with Other Libraries

A third-party library might require a `List` while the application holds data in a different representation. A well-designed view can enable integration without copying the entire dataset.

That benefit comes with important questions: does the view reflect changes to the source or is it fixed, is mutation supported, who manages the lifecycle of the underlying source, and do traversal or `size` operations incur I/O?

Do not use `List` merely to disguise a source that lacks a well-defined size or lifecycle. If the data requires resource closing or supports only single-pass consumption, an API that explicitly models its lifecycle is clearer than a collection that looks like an in-memory structure.

### 4.4. Learning Data Structures Is a Different Goal

Writing a collection from scratch to study algorithms, verify invariants, or understand iterators is a completely valid goal. It should be clearly documented as an experimental or educational implementation with known capabilities and limitations.

A data structure that passes a few study examples does not automatically become a drop-in replacement for battle-tested standard library implementations. The level of verification, documentation, and maintenance commitment must match its intended deployment environment.

Success should not be judged merely by whether the class name resembles a standard collection or whether the code compiles.

## 5. The Biggest Cost Is the Contract Callers Are Entitled to Rely On

### 5.1. An Interface Is More Than a List of Method Signatures

When an object is passed to other code as a `List`, the recipient is entitled to use any operation in accordance with the `List` contract—not just the methods the author happened to call in a single unit test.

Key areas that must be defined include:

| Area | Questions That Must Be Answered |
|---|---|
| Element domain | Are duplicates allowed, is `null` permitted, are there domain restrictions? |
| Ordering | Positional, comparator-based, insertion-ordered, or unordered? |
| Mutability | Which additions, removals, and replacements are supported? Which are unsupported? |
| Traversal | Are all elements visited in the proper order, and what happens when exhausted? |
| Equality & Hashing | Do `equals` and `hashCode` conform to the specific collection interface contract? |
| Related views | How do iterators, sublists, or map views interact with the backing collection? |
| Complexity / Cost | What is the cost of `get`, `contains`, `size`, `toArray`, and iteration? |
| Concurrency | Is multi-threaded access supported, and with what consistency guarantees? |

A class that only adds and removes elements properly is still broken if its iterator skips elements, `toArray` returns incorrect contents, or `equals` is not symmetric with another valid `List`.

### 5.2. Operations Can Be Restricted, but Must Be Restricted Properly

Collections are allowed to omit optional mutation operations; when rejecting them, throw `UnsupportedOperationException` according to the contract. An unmodifiable collection is a completely valid implementation as long as its remaining behaviors conform to the specification.

Element restrictions can also be valid, such as rejecting `null` or out-of-range values. However, they require proper documentation and standard exceptions—never silently dropping elements.

In particular, `Collection.add` must ensure that the collection contains the specified element whenever the method returns normally. If an element is rejected for any reason other than already being present under a duplicate-rejection policy (such as a set), it must throw an exception rather than arbitrarily returning `false`. See the [Collection.add contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#add(E)).

Consequently, a "bounded-capacity list" must not silently ignore an insertion and return `false` as if nothing happened. If you genuinely want a "try-add that returns `false` when full" policy, choose an API with matching semantics (such as `Queue.offer`) or define a dedicated domain operation.

### 5.3. Do Not Redefine Interface Semantics for Implementation Convenience

A `List` must uphold positional semantics and element ordering. Automatically re-sorting elements after a positional insertion without preserving the positional contract cannot be justified simply by naming the class `SortedList`.

A `Set` must preserve uniqueness and equality rules consistent with the `Set` contract. You cannot simply wrap a comparator-based structure and ignore its relationship with `equals`.

A `Map` also exposes key, value, and entry views with defined backing relationships to the map itself. Note that `Map` is part of the Java Collections Framework even though it does not extend the `Collection` interface.

Do not force a type with incompatible semantics into a standard collection interface just to pass it into a method signature. If callers have to relearn the fundamental meaning of most methods, a distinct domain API is likely more appropriate.

## 6. Subclassing a Concrete Collection Can Open More Mutation Paths Than Expected

### 6.1. A Single Override Does Not Automatically Cover the Entire API

If you only want to add input validation, the shortest path might appear to be extending `ArrayList` and overriding `add`. However, the superclass also exposes `addAll`, `add(index, element)`, `set`, list iterators, and subList views.

There is no general guarantee that every mutator method in a concrete superclass funnels its updates through the single override you chose to write.

The following file is intentionally incomplete to demonstrate this pitfall; do not use it as a valid list implementation for enforcing a "no blank strings" rule.

File `IncompleteSubclassDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class IncompleteSubclassDemo {
    // Intentionally incomplete: overriding add does not protect all writes.
    static final class NonBlankList extends ArrayList<String> {
        @Override
        public boolean add(String value) {
            Objects.requireNonNull(value, "value");
            if (value.isBlank()) {
                throw new IllegalArgumentException("blank value");
            }
            return super.add(value);
        }
    }

    public static void main(String[] args) {
        var values = new NonBlankList();
        try {
            values.add("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("directAdd=" + ex.getClass().getSimpleName());
        }

        values.add("valid");
        values.addAll(List.of("   "));
        System.out.println("afterAddAllHasBlank=" +
                values.stream().anyMatch(String::isBlank));
        values.set(0, "");
        System.out.println("afterSetFirstLength=" + values.get(0).length());
        System.out.println("size=" + values.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 IncompleteSubclassDemo.java
java IncompleteSubclassDemo
```

Stdout:

```text
directAdd=IllegalArgumentException
afterAddAllHasBlank=true
afterSetFirstLength=0
size=2
```

The direct call to `add("   ")` is rejected. However, `addAll` successfully inserts a blank string, and `set` replaces the first element with an empty string.

On JDK 17 (used to run this example), `ArrayList.addAll` uses its own internal array-copy path rather than calling the subclass's `add(E)` for each element. You can compare this in the [OpenJDK 17 ArrayList implementation](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/ArrayList.java).

You should not treat internal self-use details as a cross-version guarantee unless explicitly documented. The more important design takeaway is that a concrete superclass contract does not promise that overriding a single method will intercept every mutation path.

### 6.2. Overriding More Methods Still Requires Auditing the Entire API Surface

You could continue overriding additional mutator methods, but you must account for:

- Positional insertion and bulk addition variants.
- Positional replacement and functional bulk replacement (`replaceAll`).
- Mutations performed through `Iterator` or `ListIterator`.
- Mutations performed through returned views (`subList`).
- How constructors initialize data.
- Inherited behavior when the standard library evolves in future releases.

This does not mean inheritance is always wrong. It means that when subclassing a concrete class, you must rely only on extension points that are explicitly designed and documented.

If you only need a handful of domain operations like the catalog in Section 3, encapsulating the data structure inside a wrapper class keeps the mutation surface narrow and much easier to verify.

If you truly need a full custom collection, the skeletal abstract base classes make explicit which primitive methods form the foundation for all other derived operations, rather than relying on fragile assumptions about a concrete class.

## 7. When You Truly Need a Custom Implementation: Start from the Right Skeletal Base Class

### 7.1. Skeletal Base Classes Reduce Boilerplate

| Target Type to Provide | Skeletal Class to Explore | Core Primitives to Understand |
|---|---|---|
| General `Collection` | `AbstractCollection` | `iterator()` and `size()`, plus `add()` if mutable |
| Positional random-access `List` | `AbstractList` | `get(int)`, `size()`, and required mutation hooks |
| Sequential-access `List` | `AbstractSequentialList` | `listIterator(int)` and `size()` |
| `Set` | `AbstractSet` | Uniqueness enforcement, `iterator()`, and `size()` |
| `Map` | `AbstractMap` | `entrySet()` and advertised mutation capabilities |

This table is a starting point for reading the Javadoc contracts—not a guarantee that "implementing two methods makes every requirement automatically work."

`AbstractCollection` implements many bulk and query operations in terms of `iterator()` and `size()`. `AbstractSet` adds set equality and hash code semantics, but it does not automatically deduplicate an underlying source that contains duplicate elements. See [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) and [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html).

`AbstractSequentialList` builds positional operations on top of `listIterator(int)`, which is better suited for sequentially accessed data sources. `AbstractMap` uses `entrySet()` as the foundation for most of its operations. See [AbstractSequentialList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSequentialList.html) and [AbstractMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

Always inspect the performance characteristics of inherited methods. A functionally correct implementation may still be unusable if every `contains` call linearly scans a massive dataset or every `get` triggers blocking I/O.

### 7.2. A Well-Justified Case: A List Computed from an Arithmetic Progression Description

Suppose a numeric sequence is defined by:

```text
value(index) = first + index × step
valid index: from 0 to count - 1
```

We need a finite, read-only list accessible via `List<Integer>`. Instead of pre-populating all elements in memory, we can store the progression description using just three `int` parameters.

`AbstractList` allows creating an unmodifiable list by implementing `get(int)` and `size()`; iterators, `subList`, `equals`, `hashCode`, and other read operations are built on top of those primitives. See [AbstractList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html).

File `ComputedListDemo.java`:

```java
import java.util.AbstractList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.RandomAccess;

public class ComputedListDemo {
    static final class ProgressionList extends AbstractList<Integer>
            implements RandomAccess {
        private final int first;
        private final int step;
        private final int count;

        ProgressionList(int first, int step, int count) {
            if (count < 0) {
                throw new IllegalArgumentException("negative count");
            }
            if (count > 0) {
                long last = first + (long) (count - 1) * step;
                if (last < Integer.MIN_VALUE || last > Integer.MAX_VALUE) {
                    throw new IllegalArgumentException("values exceed int range");
                }
            }
            this.first = first;
            this.step = step;
            this.count = count;
        }

        @Override
        public Integer get(int index) {
            Objects.checkIndex(index, count);
            return Math.toIntExact(first + (long) index * step);
        }

        @Override
        public int size() {
            return count;
        }
    }

    public static void main(String[] args) {
        List<Integer> values = new ProgressionList(10, 3, 5);
        List<Integer> reference = List.of(10, 13, 16, 19, 22);
        System.out.println("values=" + values);
        System.out.println("get2=" + values.get(2));
        System.out.println("subList=" + values.subList(1, 4));
        System.out.println("equalsForward=" + values.equals(reference));
        System.out.println("equalsBackward=" + reference.equals(values));
        System.out.println("sameHash=" +
                (values.hashCode() == reference.hashCode()));
        System.out.println("array=" + Arrays.toString(values.toArray()));
        System.out.println("sum=" +
                values.stream().mapToInt(Integer::intValue).sum());

        var large = new ProgressionList(0, 1, 1_000_000);
        System.out.println("largeSize=" + large.size());
        System.out.println("largeLast=" + large.get(large.size() - 1));
        System.out.println("descending=" + new ProgressionList(10, -2, 3));
        System.out.println("repeated=" + new ProgressionList(5, 0, 3));
        System.out.println("emptyHasNext=" +
                new ProgressionList(7, 1, 0).iterator().hasNext());

        try {
            values.add(25);
        } catch (UnsupportedOperationException ex) {
            System.out.println("write=" + ex.getClass().getSimpleName());
        }
        try {
            values.get(5);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("badIndex=" + ex.getClass().getSimpleName());
        }
        try {
            new ProgressionList(Integer.MAX_VALUE, 1, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("overflow=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ComputedListDemo.java
java ComputedListDemo
```

Stdout:

```text
values=[10, 13, 16, 19, 22]
get2=16
subList=[13, 16, 19]
equalsForward=true
equalsBackward=true
sameHash=true
array=[10, 13, 16, 19, 22]
sum=80
largeSize=1000000
largeLast=999999
descending=[10, 8, 6]
repeated=[5, 5, 5]
emptyHasNext=false
write=UnsupportedOperationException
badIndex=IndexOutOfBoundsException
overflow=IllegalArgumentException
```

### 7.3. Why Is This a Well-Grounded Custom Collection Implementation?

The internal representation is not an `ArrayList` hidden behind a new name. It stores the formula parameters and computes elements on demand by index. The constructor does not allocate one million `Integer` objects to set up `large`.

Every index has a clear meaning, the size is finite, the order is deterministic, and the values are derived from immutable fields. The `List` interface accurately matches what is provided to callers.

Furthermore, the example does not reinvent `iterator()`, `equals()`, `hashCode()`, `toArray()`, or `subList()`. It leverages the `AbstractList` skeletal implementation and verifies key contract interactions:

- Positional contents are accurate.
- Equality with a standard `List` holds symmetrically in both directions.
- Equal lists produce equal hash codes.
- Range views (`subList`) and array conversions contain the exact expected elements.
- Streams traverse all elements to compute the sum.
- Write operations throw `UnsupportedOperationException`.
- Out-of-bounds indices and progressions exceeding the `int` range are rejected early.

### 7.4. Boundary and Overflow Checks Are Part of the Design

A negative `count` has no valid meaning, so the constructor rejects it immediately. When `count > 0`, the last element is computed using `long` arithmetic to prevent intermediate multiplication overflow in `int`.

For a linear arithmetic progression, every element lies between the first and last values. If both endpoints fit within the 32-bit signed `int` range, all intermediate terms are guaranteed to fit within `int` as well. Checking the endpoints at construction time is therefore both necessary and sufficient for this representation.

`get` calls `Objects.checkIndex` before computing the value. It never returns a dummy default value for an invalid index, which would hide caller bugs and violate positional `List` semantics.

A negative step produces a descending list, and a zero step produces repeated elements; both are completely valid for a `List`. We avoid accidentally imposing a "strictly increasing" constraint just because the first sample input happened to be increasing.

### 7.5. A Compact Representation Does Not Make Every Operation O(1)

In this example, `get` and `size` perform constant work independent of the element count. The class therefore implements `RandomAccess` to signal fast positional access. This marker interface helps generic algorithms (such as `Collections.binarySearch`) choose index-based loops over iterator-based traversal; it does not magically speed up a slow implementation. See [RandomAccess](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html).

Conversely, printing the entire list, calling `toArray()`, computing `hashCode()`, or running a linear search (`contains`) still visits every element. Calling `toArray()` on a one-million-element progression will still allocate and populate an array of one million elements.

Values are returned as `Integer` references; a computed representation does not eliminate boxing overhead when accessed through generic object-based collection APIs.

The scope of this example is a finite, read-only arithmetic progression with simple rules. It is not a full numerical library, nor is it a claim that every computed `List` implementation shares the exact same performance profile.

## 8. Evidence Required Before Adopting a Custom Implementation

### 8.1. Verify Contract Compliance Before Optimization

A worthwhile test plan must verify the behavior callers are entitled to rely on, not merely mirror the internal algorithm.

For a `List`, you can test a custom implementation against a reference list (such as `List.of(...)` or `ArrayList`) across all advertised operations: mutations (if supported), boundary access, iteration, array conversion, symmetric `equals`/`hashCode`, and `subList` views.

For specialized structures, not every behavior will match a general-purpose collection. You must identify which behaviors are equivalent and which have valid documented restrictions, then test exactly what is promised.

For instance, `ProgressionList` does not pretend to support additions or removals. What must be verified is that it rejects writes cleanly while all read and comparison operations remain 100% compliant with `List`.

### 8.2. Iterator Is a Real API, Not Just a for-each Loop Helper

If you write a custom `Iterator`, it must strictly honor its state machine: `hasNext()`, `next()` when elements remain versus when exhausted, and `remove()` if supported. When no elements remain, `Iterator.next()` must throw `NoSuchElementException`—never return `null` as an end-of-stream sentinel. See [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

For mutable lists, you must also define behavior when the collection is structurally modified during iteration. If you rely on `AbstractList`'s `modCount` mechanism, update it consistently according to the skeletal class specification. Remember that fail-fast concurrent modification detection is for bug detection, not a multi-threaded synchronization lock.

If you customize a `Spliterator` or stream support, never declare characteristics like `ORDERED`, `SIZED`, `DISTINCT`, or `IMMUTABLE` merely to make stream pipelines run faster. Those flags must accurately reflect the underlying data and mutation model.

An implementation that works properly using the inherited skeletal iterator is often much easier to verify than a hand-rolled iterator written without a compelling reason.

### 8.3. Test Every Mutation Path and Failure Mode

For classes enforcing domain constraints on elements, you must test `addAll`, positional updates (`set`), iterators (`ListIterator.add`/`set`), views (`subList`), and relevant default methods (`replaceAll`). As the incomplete subclass example demonstrated, testing only `add(E)` is insufficient.

If a bulk operation encounters an invalid element midway through, the post-failure state must match what your contract documents. Do not assume that general collection contracts automatically guarantee atomic rollback of prior elements when a bulk operation throws an exception.

If business logic requires a batch of changes to either succeed completely or fail atomically without partial state updates, design that transactional boundary explicitly. That requirement alone is often a strong reason to provide a dedicated domain method rather than making implicit promises under the name `addAll`.

For optional mutation operations that would be a no-op (such as `removeAll(Collections.emptyList())` or `clear()` on an already empty read-only collection), whether `UnsupportedOperationException` is thrown may depend on the specific implementation contract. When writing tests, verify against the documented contract of the chosen API rather than assuming an overly broad rule for all read-only collections.

### 8.4. Performance Must Be Benchmarked Against Realistic Alternatives

A custom collection should be evaluated against properly configured standard collections using representative datasets and workloads—not just the best-case scenario for which the new algorithm was tuned.

Be sure to account for:

- Allocation and garbage collection overhead.
- Common-case operations as well as rare but expensive operations.
- Actual memory footprint under steady-state load.
- Latency distribution (tail latency), not just aggregate throughput.
- Conversion or copying costs when crossing API boundaries.
- Retention costs of keeping views or backing sources alive in memory.

Our computed progression example proves that we do not need to pre-allocate one million elements just to read an index. Because the demo program does not measure heap bytes or benchmark throughput, its stdout should not be cited as quantitative performance proof.

## 9. Lock In the Decision with a Brief Design Summary

Before writing a custom collection, write down the following seven points:

1. **Requirement:** What operations do callers need, and on what kind of data?
2. **Gap:** What specifically do existing standard tools or combinations fail to satisfy?
3. **Interface:** Why choose `List`, `Set`, `Map`, `Collection`, or a dedicated domain API?
4. **Representation:** How is data stored, computed, or fetched from an underlying source?
5. **Contract:** Ordering, valid elements, mutability, views, and lifecycle rules.
6. **Evidence:** What has been verified regarding functional compliance, edge cases, and cost?
7. **Maintenance Ownership:** Who will maintain and update it when requirements or JDK versions change?

Documenting these points makes the decision reviewable based on requirements and evidence rather than the subjective appeal of clever code or an interesting algorithm.

Applied to our four examples:

| Scenario | Well-Grounded Decision |
|---|---|
| Need an unmodifiable view, defensive copy, or LIFO queue view | Use built-in JDK utilities |
| Need tag registration with normalization and domain rules | Use a domain class wrapping `LinkedHashSet` |
| Want to forbid blank strings by overriding a single `add` method | Flawed design; fails to enforce invariants across all mutation paths |
| Need a finite `List<Integer>` defined by an arithmetic formula | A read-only custom `List` extending `AbstractList` is well justified |

If you cannot clearly articulate the gap or the verifiable benefit, keep looking for a simpler composition of existing tools before expanding your API surface.

If your desired semantics intentionally diverge from most of a standard collection contract, a distinct domain type will serve users much better than a misleading `List` or `Set` label.

If your requirements involve concurrency, off-heap memory, compressed storage, or external resource management, the verification surface expands dramatically. Never treat those concerns as minor flags that can be bolted onto a sequential prototype later.

## 10. Practice and Self-Check

### Exercise 1: Do You Really Need a New Collection?

A service needs to return a list of configuration items to callers without allowing callers to modify it. After returning, the service's internal configuration source may continue to be updated.

Distinguish between two different requirements:

- The caller always sees the latest configuration updates through a live read-only view.
- The caller receives an isolated snapshot fixed at the moment of the call.

Why shouldn't you lump both requirements under the vague term "immutable list" and write a custom class? Use `ExistingToolsDemo` to explain what must be decided regarding the relationship to the backing source and the mutability of element objects themselves.

### Exercise 2: Domain API or Set?

A code registry needs to normalize case, validate format patterns, and support a code-merging operation.

Do callers genuinely need every method of `Set`, or do they need a focused set of registration operations? If you were to implement `Set<String>` directly, what invariants would you have to preserve regarding `contains`, `equals`, and the stored values?

Discussion guide: A domain API can express normalized identity rules explicitly. Only take on the `Set` contract when standard interface compatibility is strictly required and you can honor the full contract consistently.

### Exercise 3: Spot the Missed Mutation Paths

In the intentionally flawed `NonBlankList` example, list additional mutation paths beyond `add(E)`. Then explain why adding one or two more overrides without auditing the entire superclass contract still does not constitute a complete proof of safety.

Do not "fix" validation by returning `false` for invalid inputs. Choose the proper exception contract or narrow the exposed API using composition.

### Exercise 4: Trade-offs of a Computed List

With `ProgressionList`, reading the last element of a one-million-number sequence does not require pre-allocating all values. Why do calling `toArray()`, printing the entire list, or computing `hashCode()` still require proportional work?

If a caller only needs a single sequential pass and never requires positional random access, what narrower interface might suffice? Conversely, if you must interoperate with a library that expects a `List`, why does the example implementation have a clear justification?

Discussion guide: A compressed or computed representation accelerates specific operations, but it cannot eliminate the output requirements of bulk operations. The chosen interface should derive directly from how callers consume the data.

### Exercise 5: Write Acceptance Criteria for Maintaining a Custom Implementation

Pick a real requirement from your own work and write a brief design summary following the seven points in Section 9.

If you were forbidden from writing a custom collection, what would the best standard alternative be? What specific gap does it leave? What tests and benchmarks are required to prove that your custom implementation preserves contract semantics and delivers real value?

A well-grounded answer must clearly separate what must be custom-owned, what can be reused from skeletal classes, and how thoroughly the risks have been verified.

### Final Questions Before You Start

1. Is the missing piece a data structure, a data view, or a domain business rule?
2. Can built-in collection utilities or a domain wrapper solve it cleanly?
3. Does the standard collection interface truly match the semantics you want to provide?
4. Do you know every read, traversal, and mutation path opened by that interface?
5. Have you chosen the skeletal base class that matches your access pattern?
6. Is the benefit explained by a clear representational advantage or concrete measurements?
7. Have you tested boundaries, exceptions, symmetric equality, and views?
8. Are concurrency, resource lifecycle, and maintenance boundaries explicitly stated?

Implementing a custom collection is valuable when it fills a concrete gap while faithfully upholding everything callers are entitled to rely on. Choosing a domain wrapper or built-in utility is an equally complete design decision when it accurately satisfies the requirement.
