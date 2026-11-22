# Collectors.toCollection() for Explicitly Choosing the Collection Type in Java

## 1. The problem: which Collection type do we get after collecting a Stream?

In the Java Stream API, operations such as `filter`, `map`, and `sorted` describe how elements are processed. When you need to **collect the results into a Collection**, you use a terminal operation like `collect(...)`. If business requirements explicitly specify **the output collection type**, `Collectors.toCollection(...)` is the direct tool:

~~~java
ArrayList<String> names = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

This is an illustrative snippet, assuming `source` is a collection containing Strings, with imports for `java.util.ArrayList` and `java.util.stream.Collectors`.

With the snippet above, the author is **explicitly choosing `ArrayList`**, rather than letting a general-purpose collector pick the implementation. This matters when the caller needs:

- **ArrayList**: an indexed list that preserves duplicate elements and is generally convenient for index-based access.
- **LinkedList**: another list that also implements Deque, suitable when its contract and characteristics are actually needed.
- **LinkedHashSet**: removes duplicate elements according to `equals/hashCode` and iterates in insertion order.
- **HashSet**: removes duplicate elements, with no guarantee on iteration order.
- **TreeSet**: removes elements considered duplicates by a comparator or natural ordering and iterates in sorted order.
- **EnumSet**: a specialized set for constants of the same enum type.

**Key rule:** `Collectors.toCollection(factory)` does not transform elements via mapping, does not perform sorting beyond the semantics of the chosen Collection, and is not an exact equivalent of `toList()` or `toSet()`. It creates a **Collector** aimed at accumulating elements into **a Collection provided by the factory**.

## 2. Signature and meaning of Supplier

General signature:

~~~java
public static <T, C extends Collection<T>>
Collector<T, ?, C> toCollection(Supplier<C> collectionFactory)
~~~

This is an **abbreviated API signature** for explanation; it is not a standalone method to place into a Java file. It resides in `java.util.stream.Collectors`.

Key parts:

| Component | Role |
| --- | --- |
| `T` | Element type of the source Stream |
| `C extends Collection<T>` | Target Collection type, e.g., `ArrayList<T>`, `TreeSet<T>` |
| `Supplier<C>` | Factory that creates a new Collection instance when the collector needs one |
| `Collector<T, ?, C>` | Collector that accepts elements of type T and produces a final result of type C |
| `collect(...)` | Terminal operation that runs the pipeline and produces the result |

**Supplier** has a parameterless `C get()` method. For example:

~~~java
Supplier<ArrayList<String>> factory = ArrayList::new;
ArrayList<String> result = Stream.of("a", "b")
        .collect(Collectors.toCollection(factory));
~~~

This is an illustrative snippet requiring imports for `Supplier`, `ArrayList`, `Stream`, and `Collectors`. `ArrayList::new` is a **constructor reference**: each time the Supplier is invoked, it creates a new list.

Equivalent ways to provide the factory:

~~~java
Collectors.toCollection(ArrayList::new)
Collectors.toCollection(() -> new ArrayList<>())
~~~

These are two illustrative expressions for comparison. A constructor reference is usually concise and readable; a lambda is useful when configuration arguments need to be passed, such as a comparator for TreeSet or an initial capacity for ArrayList.

**An important note:** `toCollection` is a factory for a Collector; intermediate or result Collections are created **when collect executes**. In parallel mode, the collection process may create **multiple intermediate collections** and then combine them; you must not assume the factory is called exactly once in every execution mode.

## 3. Complete Java 17 example: ArrayList, LinkedHashSet, and TreeSet

Create the file **CollectionChoicesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class CollectionChoicesDemo {
    public static void main(String[] args) {
        List<String> source = List.of(
                "Lan", "An", "Lan", "Binh", "An");

        ArrayList<String> list = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<String> distinctInOrder = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        TreeSet<String> distinctSorted = source.stream()
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("List: " + list);
        System.out.println("Ordered set: " + distinctInOrder);
        System.out.println("Sorted set: " + distinctSorted);

        list.add("Mai");
        System.out.println("Mutable list: " + list);
    }
}
~~~

Compile/run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 CollectionChoicesDemo.java
java CollectionChoicesDemo
~~~

Stdout:

~~~text
List: [Lan, An, Lan, Binh, An]
Ordered set: [Lan, An, Binh]
Sorted set: [An, Binh, Lan]
Mutable list: [Lan, An, Lan, Binh, An, Mai]
~~~

**Detailed breakdown:**

1. `source` is a List with 5 elements, where **Lan** and **An** appear twice.
2. `ArrayList::new` accumulates all elements in the encounter order of this ordered Stream. The list keeps duplicates: **[Lan, An, Lan, Binh, An]**.
3. `LinkedHashSet::new` removes duplicates while preserving the insertion order of first occurrences: **[Lan, An, Binh]**.
4. `TreeSet::new` uses the natural ordering of String, removes duplicates according to the comparison rules, and iterates in sorted order: **[An, Binh, Lan]**.
5. `list.add("Mai")` succeeds because the `ArrayList` created by the factory is **mutable**; the output shows the new element.

This is the clearest advantage of `toCollection`: **the final collection type is explicitly specified right in the collection code**.

## 4. Comparison with Stream.toList(), Collectors.toList(), and toSet()

Collection APIs are often confused with one another:

| Expression | Declared type | Order, duplicates, and mutability |
| --- | --- | --- |
| `stream.toList()` (Java 16+) | `List<T>` | Preserves encounter order if present; the list is **unmodifiable** |
| `collect(Collectors.toList())` | `List<T>` | No guarantee on specific implementation, mutability, serialization, or thread safety |
| `collect(Collectors.toSet())` | `Set<T>` | No guarantee on implementation or iteration order; removes duplicates per Set contract |
| `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` | Specific ArrayList; keeps duplicates/order; mutable |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet<T>` | Specific LinkedHashSet; removes duplicates, insertion order |
| `collect(Collectors.toCollection(TreeSet::new))` | `TreeSet<T>` | Specific TreeSet; sorted and comparator rules |
| `collect(Collectors.toUnmodifiableList())` | `List<T>` | Unmodifiable, **does not accept null elements** |

**Key takeaway:** `Collectors.toList()` may currently return a common List type in a given implementation, but the API **does not promise** that it is an ArrayList or that it will always allow `add`. If the caller requires a **mutable ArrayList**, choose `toCollection(ArrayList::new)`. If the caller only needs an unmodifiable list, `Stream.toList()` has the right contract and is more concise.

**Do not equate `unmodifiable` with `deeply immutable`:** a list that disallows adding or removing elements can still hold mutable objects; the state of those inner objects can still change. Likewise, do not infer thread safety just because a list cannot be structurally modified.

### 4.1. Choosing by contract

- Need an output `List` that **cannot be structurally modified**: consider `stream.toList()`.
- Need **specifically an ArrayList** for compatibility with another API or to use `add/remove`: `toCollection(ArrayList::new)`.
- Need to remove duplicates **and preserve first-seen order**: `LinkedHashSet::new`.
- Need a **sorted** set: `TreeSet::new` or a factory with a comparator.
- Need a set specialized for enums: the factory `EnumSet.noneOf(EnumType.class)`.
- No specific collection type required: prefer the shorter API that matches the contract; do not add `toCollection` just for unnecessary complexity.

Choosing a Collection type should be driven by **semantics and subsequent operations**, not merely by a habit of using ArrayList.

## 5. ArrayList and LinkedList: both are Lists, different structures

`ArrayList` uses a resizable array; it is generally well-suited for indexed access and general-purpose lists. `LinkedList` is a doubly-linked list and implements both `List` and `Deque`. You should not claim LinkedList is always better for insertions/removals: positional lookup cost, memory locality, node allocation, and access patterns all play a role.

Example:

~~~java
ArrayList<Integer> a = IntStream.rangeClosed(1, 4)
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));

LinkedList<Integer> b = IntStream.rangeClosed(1, 4)
        .boxed()
        .collect(Collectors.toCollection(LinkedList::new));
~~~

This is an **illustrative snippet** requiring imports for `ArrayList`, `LinkedList`, `IntStream`, and `Collectors`.

Both contain **[1, 2, 3, 4]**, but the concrete results are an ArrayList and a LinkedList. `boxed()` converts `IntStream` into `Stream<Integer>`, allowing `Collectors.toCollection` to be used as shown here.

**Important:** `Collectors.toCollection` is a collector for an **object Stream<T>**. Primitive streams `IntStream`, `LongStream`, and `DoubleStream` do not have a `collect(Collector<...>)` overload with the same signature. If you need to collect Integers into an ArrayList from an IntStream, call `boxed()` first or use the appropriate primitive stream collect mechanism.

### 5.1. Choosing initial capacity

When you know or can estimate the number of elements beforehand, you can provide a factory with capacity:

~~~java
ArrayList<String> result = source.stream()
        .collect(Collectors.toCollection(
                () -> new ArrayList<>(128)));
~~~

This is an illustrative snippet where `source` is a String-compatible collection/stream. `new ArrayList<>(128)` sets the **initial capacity**, **not** 128 pre-populated elements. `result.size()` is still the actual number of collected elements.

**Avoid premature optimization:** the factory is called to create containers used during collection; especially in a parallel pipeline, multiple containers can exist simultaneously. Allocating a large capacity for every container can sometimes waste memory. Only choose an explicit capacity after understanding the workload and measuring performance.

## 6. LinkedHashSet: removing duplicates while preserving appearance order

A common requirement is deduplicating items while still showing them to the user in the order they first appeared.

~~~java
LinkedHashSet<String> selected = Stream.of(
        "java", "go", "java", "kotlin", "go")
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

This is an illustrative snippet with the corresponding imports. When printing the set, the result is:

~~~text
[java, go, kotlin]
~~~

`LinkedHashSet` is based on the insertion order of distinct elements. With a stream that has an encounter order and standard collection, elements are accumulated in encounter order, so the resulting set reflects the first occurrence of each value.

**Distinguishing from `HashSet`:**

~~~java
HashSet<String> selected = Stream.of(
        "java", "go", "java", "kotlin")
        .collect(Collectors.toCollection(HashSet::new));
~~~

This is an illustrative snippet. HashSet also removes duplicate elements but **does not guarantee iteration order**. Do not state a specific stdout for HashSet as a stable rule because the order depends on the implementation, hashes, data, and environment changes.

**Do not use LinkedHashSet as a substitute for sorting:** it preserves insertion order, **not alphabetical or score-based sorting**. To sort, use `sorted(...)` before collecting into a LinkedHashSet, or choose an appropriate sorted collection type if you want to maintain sorting semantics in the set.

## 7. TreeSet: choosing natural ordering or a custom Comparator

`TreeSet` implements `NavigableSet`, keeping elements sorted based on **Comparable** or a **Comparator**. It is useful when you need a result set that maintains order and supports operations like `first`, `last`, `floor`, `ceiling`, and `subSet` per its contract.

### 7.1. Natural ordering

~~~java
TreeSet<Integer> numbers = Stream.of(9, 2, 5, 2)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

This is an illustrative snippet. The sorted result is **[2, 5, 9]**; the duplicate 2 is kept only once.

`TreeSet::new` has no explicit comparator, so the elements must have an appropriate natural ordering and be mutually comparable. If elements are not Comparable or cannot be compared with each other, adding to the TreeSet can throw a **ClassCastException** at runtime.

### 7.2. Custom Comparator via a lambda factory

When sorting according to a business policy is needed:

~~~java
TreeSet<String> byLengthThenText = Stream.of(
        "java", "go", "kotlin", "rust", "go")
        .collect(Collectors.toCollection(() ->
                new TreeSet<>(
                        Comparator.comparingInt(String::length)
                                .thenComparing(
                                        Comparator.naturalOrder()))));
~~~

This is an illustrative snippet requiring imports for TreeSet, Comparator, Stream, and Collectors. The order will be:

~~~text
[go, java, rust, kotlin]
~~~

- `Comparator.comparingInt(String::length)` places shorter strings first.
- `thenComparing(Comparator.naturalOrder())` uses lexicographical order when lengths are equal.
- "java" and "rust" both have length 4, so they are ordered lexicographically, java before rust.
- "go" appears twice but is kept only once because two equal Strings have the same ordering.

**Why is `() -> new TreeSet<>(comparator)` needed?** The factory takes no parameters in the Supplier signature, but inside the lambda body we can instantiate TreeSet with a configured comparator. The no-argument **`TreeSet::new`** defaults to natural ordering; it does not automatically know your business comparator.

### 7.3. The Comparator also decides what counts as a duplicate in TreeSet

A crucial point: with `TreeSet`, **two elements are treated as occupying the same position in the Set when comparator.compare(a,b) == 0**. Therefore, if the comparator only compares a non-unique property, you can lose distinct elements:

~~~java
record Product(String sku, int price) {}

Comparator<Product> byPriceOnly =
        Comparator.comparingInt(Product::price);

TreeSet<Product> items = Stream.of(
        new Product("A", 100),
        new Product("B", 100))
        .collect(Collectors.toCollection(
                () -> new TreeSet<>(byPriceOnly)));
~~~

This is an illustrative snippet requiring imports for Comparator, TreeSet, Stream, and Collectors, with the Product record placed in a valid scope. **items.size() is 1**, because both A and B have price=100, so the comparator returns 0. This may not match the intended meaning of "unique products by SKU".

If you need to keep both A and B while still sorting by price, add a tie-breaking key:

~~~java
Comparator<Product> byPriceThenSku =
        Comparator.comparingInt(Product::price)
                .thenComparing(Product::sku);
~~~

With the new comparator, two products priced at 100 with different SKUs are both retained. When choosing a comparator for TreeSet, check whether it is **consistent with equals** if you need to adhere strictly to general Set semantics. A comparator inconsistent with equals can cause surprising Set behavior in other APIs.

## 8. Complete Java 17 example: TreeSet with Comparator on a record

Create the file **SortedProductsDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

record Product(String sku, int price) {}

public class SortedProductsDemo {
    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("B", 20),
                new Product("A", 30),
                new Product("C", 20),
                new Product("A", 30)
        );

        Comparator<Product> priceThenSku =
                Comparator.comparingInt(Product::price)
                        .thenComparing(Product::sku);

        TreeSet<Product> sorted = products.stream()
                .collect(Collectors.toCollection(
                        () -> new TreeSet<>(priceThenSku)));

        System.out.println("Count: " + sorted.size());
        System.out.println("SKUs: " + sorted.stream()
                .map(Product::sku)
                .toList());
        System.out.println("First: " + sorted.first().sku());
        System.out.println("Last: " + sorted.last().sku());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SortedProductsDemo.java
java SortedProductsDemo
~~~

Stdout:

~~~text
Count: 3
SKUs: [B, C, A]
First: B
Last: A
~~~

**Breakdown:**

1. There are four input Products, with `Product("A",30)` appearing twice.
2. The Comparator sorts by price ascending; when prices are equal, SKUs are ordered lexicographically.
3. Products B and C both have price 20 but different SKUs, so both are kept; B comes before C.
4. The two A Products match on both price and SKU, so they are treated as duplicates and only one is kept.
5. The final TreeSet has the order `B(20), C(20), A(30)`. Operations `first()` and `last()` follow the comparator, not the appearance order in the input List.

**Do not confuse this with `Stream.sorted(comparator).toList()`:** that approach sorts but **keeps duplicate elements**. TreeSet simultaneously applies set rules, so the number of elements may decrease.

## 9. EnumSet: a Collection specialized for enums

When elements belong to the same **enum** type, `EnumSet` is an efficient and semantically rich choice for a set of enum constants. It maintains order **according to the declaration order of constants in the enum**, not the input order.

A suitable factory is typically:

~~~java
() -> EnumSet.noneOf(Permission.class)
~~~

This is an illustrative Supplier expression, assuming the Permission enum is already defined. Do not use `EnumSet::new` because EnumSet does not have a public no-argument constructor to invoke like ArrayList.

Create the file **EnumSetCollectorDemo.java**:

~~~java
import java.util.EnumSet;
import java.util.List;
import java.util.stream.Collectors;

enum Permission {
    READ, WRITE, EXECUTE
}

public class EnumSetCollectorDemo {
    public static void main(String[] args) {
        List<Permission> granted = List.of(
                Permission.WRITE,
                Permission.READ,
                Permission.WRITE
        );

        EnumSet<Permission> permissions = granted.stream()
                .collect(Collectors.toCollection(
                        () -> EnumSet.noneOf(Permission.class)));

        System.out.println("Permissions: " + permissions);
        System.out.println("Has write: "
                + permissions.contains(Permission.WRITE));

        permissions.add(Permission.EXECUTE);
        System.out.println("Updated: " + permissions);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumSetCollectorDemo.java
java EnumSetCollectorDemo
~~~

Stdout:

~~~text
Permissions: [READ, WRITE]
Has write: true
Updated: [READ, WRITE, EXECUTE]
~~~

**Explanation:**

- WRITE appears twice in the source, and EnumSet contains only one WRITE constant.
- READ is declared before WRITE, so the list prints in the order READ, WRITE even though the source has WRITE first.
- `noneOf(Permission.class)` creates an empty EnumSet bound to the exact Permission type.
- The result is a mutable EnumSet; adding EXECUTE succeeds.
- EnumSet **does not allow null elements**; if the source contains null, there must be a policy to check, filter, or report an error before collecting.

EnumSet is a classic example where `toCollection` lets you create a collection type **that is hard to express with `Collectors.toSet()`**, because toSet does not guarantee choosing EnumSet.

## 10. Null: the chosen Collection determines data acceptance

Not every Collection has the same policy for `null`:

- **ArrayList** and **LinkedList** can contain null elements.
- **HashSet** and **LinkedHashSet** can contain one null element.
- **TreeSet** with natural ordering **does not accept null** in normal usage; adding null causes an NPE. A custom comparator can support null if explicitly designed to, but this should not be assumed by default.
- **EnumSet** does not accept null.
- **Collectors.toUnmodifiableList/Set** do not accept null; unlike the mutable collections listed above.
- **Stream.toList()** can contain null, but the resulting list is unmodifiable.

Example:

~~~java
List<String> values = Arrays.asList("A", null, "B");

ArrayList<String> list = values.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

This is an illustrative snippet with imports for List, Arrays, ArrayList, and Collectors. **list** contains `["A", null, "B"]`, and `System.out.println(list)` prints **[A, null, B]**.

However:

~~~java
// MAY THROW NPE if the source contains null:
TreeSet<String> sorted = values.stream()
        .collect(Collectors.toCollection(TreeSet::new));
~~~

This is an **illustrative snippet that causes a runtime error** when TreeSet using natural ordering encounters null. If null is allowed to appear in the input but should not enter the result set:

~~~java
TreeSet<String> sorted = values.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

This is an illustrative snippet requiring an additional import for Objects. The sorted result is **[A, B]**.

**Do not automatically filter out null if null indicates invalid data that must be reported as an error.** When the policy requires failing fast, consider `Objects.requireNonNull` at the boundary and report invalid data. Choosing a collector does not replace validation.

## 11. Relationship between Stream order, collection order, and Collection iteration order

There are **three distinct concepts of order**:

1. **Stream encounter order:** the order defined by the source or operation chain, e.g., List has an order, while HashSet has no ordering requirement.
2. **Accumulation order into the Collection:** `toCollection` collects elements in encounter order if the Stream is ordered, per the collector contract.
3. **Iteration order of the resulting Collection:** depends on the collection type: ArrayList/LinkedList by position, LinkedHashSet by insertion, TreeSet by comparator, and HashSet with no order guarantee.

Therefore:

~~~java
LinkedHashSet<Integer> chosen = Stream.of(4, 2, 4, 3, 2)
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

This is an illustrative snippet; when iterated, `chosen` yields **[4, 2, 3]**. However:

~~~java
TreeSet<Integer> chosen = Stream.of(4, 2, 4, 3, 2)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Yields **[2, 3, 4]** due to natural ordering.

**A note on `unordered()` or unordered sources:** if a Stream has no encounter order, do not assume LinkedHashSet will be as deterministic as an ordered List. LinkedHashSet only preserves **the insertion order it receives**, rather than inventing a business order not defined by the source.

## 12. The collector factory must create a new, suitable Collection

This is a point that is very easy to overlook. A Supplier used with `toCollection` should create **an empty, independent Collection** capable of receiving elements. Do not return a Collection that already has data, or return the same shared instance across multiple Supplier calls.

Anti-pattern:

~~~java
List<String> shared = new ArrayList<>();

// DESIGN FLAW: the factory returns the same object.
// Collectors.toCollection(() -> shared)
~~~

This is an illustrative anti-pattern snippet, assuming appropriate imports. With a parallel stream, the collector may need multiple accumulation containers and **combine them**. If the factory returns the same object, the result can be wrong, duplicated, racy, or violate the contract; even sequentially, reusing a container makes separate collections non-independent.

Correct:

~~~java
Collectors.toCollection(ArrayList::new)
~~~

or when configured:

~~~java
Collectors.toCollection(() -> new TreeSet<>(comparator))
~~~

with an appropriately defined comparator.

**Do not use an immutable singleton collection** like `() -> List.of()` as an accumulation factory: the Collector needs to call element-adding methods; an unmodifiable collection will throw **UnsupportedOperationException**. Similarly, a factory returning a collection that already contains data can introduce elements not from the source.

### 12.1. Each collect call should be independent

Create the file **IndependentCollectionsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class IndependentCollectionsDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3);

        ArrayList<Integer> first = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        ArrayList<Integer> second = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        first.add(99);

        System.out.println("first: " + first);
        System.out.println("second: " + second);
        System.out.println("same instance: " + (first == second));
    }
}
~~~

Compile/run:

~~~bash
javac IndependentCollectionsDemo.java
java IndependentCollectionsDemo
~~~

Stdout:

~~~text
first: [1, 2, 3, 99]
second: [1, 2, 3]
same instance: false
~~~

The two `collect` calls run on **two new Streams** created from `source` and use the factory to create new collections. Modifying `first` does not affect `second`; this is the desired behavior.

**Note:** The new collection results are **structurally** independent, not necessarily a deep copy of **every element**. If T is a mutable object, both collections may still reference the same element objects from `source`. To perform a deep copy, you need a dedicated policy and element transformation.

## 13. Parallel Stream: do not manually share Collections across workers

When using `parallelStream()`, a standard collector can:

1. Create multiple intermediate containers from the Supplier.
2. Accumulate elements into each container.
3. Combine the containers using the combiner.
4. Return the final Collection.

`Collectors.toCollection` has its own combining mechanism; with factories like `ArrayList::new`, `LinkedHashSet::new`, and `TreeSet::new`, you do not need to write synchronized blocks yourself just to use the collector under the standard mechanism.

~~~java
ArrayList<Integer> result = IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

This is an illustrative snippet requiring imports for IntStream, ArrayList, and Collectors. With a source having encounter order 1..1000, the collector preserves the result in encounter order; the resulting ArrayList contains 1000 elements in the corresponding order.

**However, do not infer that:**

- The Supplier is always called exactly once in a parallel stream.
- The ArrayList created by the Supplier is shared directly and safely across multiple threads for concurrent `add` calls.
- Each branch or worker of the Stream runs on a fixed schedule.
- Choosing parallel is guaranteed to be faster: there is overhead for splitting work, merging, and allocation.
- HashSet/TreeSet automatically becomes thread-safe just by appearing in a parallel collector.

In terms of terminology, the `toCollection` collector is not a **CONCURRENT** collector in the sense of letting all workers accumulate concurrently into the same container. Intermediate containers are combined according to the collect mechanism. After collection finishes, **the resulting ArrayList/TreeSet/LinkedHashSet is not automatically thread-safe** if you let multiple threads mutate it afterward.

### 13.1. When does parallel cause issues?

If `collectionFactory` has side effects, such as incrementing a global counter or pointing to shared mutable state, the number of factory invocations should not be used as business data. If a mapper/filter has side effects or depends on mutable state, the result may be unstable. Prefer **pure functions** and independent factories.

Elements in a TreeSet need a comparator with a consistent contract that does not depend on temporal order or mutable state. If the comparator changes meaning while elements are already in the set, the sorted set structure may no longer reflect the correct order.

## 14. Business design example: sorting without losing orders

Suppose a system wants to display all orders by total amount ascending, including multiple orders with the same total amount. If you use a TreeSet with a comparator based only on total amount, multiple orders with equal values will be treated as duplicates and records will be lost.

Anti-pattern:

~~~java
Comparator<Order> byTotal =
        Comparator.comparingLong(Order::totalCents);

TreeSet<Order> ordersByPrice = orders.stream()
        .collect(Collectors.toCollection(
                () -> new TreeSet<>(byTotal)));
~~~

This is an illustrative snippet where Order is an already-defined type with `totalCents()`. If two orders have the same total amount, the comparator returns 0 and TreeSet keeps only one. This is unsuitable if the requirement is to **sort all orders**, not to create a deduplicated set.

The right approach when you want to keep all orders:

~~~java
ArrayList<Order> sortedOrders = orders.stream()
        .sorted(Comparator.comparingLong(Order::totalCents)
                .thenComparing(Order::id))
        .collect(Collectors.toCollection(ArrayList::new));
~~~

This is an illustrative snippet, assuming Order.id is an appropriate key and the necessary imports are present. `Stream.sorted` orders elements without automatically removing duplicates; `ArrayList` keeps all records, including equal ones.

When you **do want to deduplicate** by a key, you must explicitly define the priority rule: keep the first record, keep the latest record, keep the highest price, or report an error. A TreeSet with a key-only comparator may discard distinct elements without indicating why; sometimes `Map<Id,Order>` and a merge function following the business contract are more appropriate.

## 15. Common mistakes with Collectors.toCollection()

| Mistake / Misconception | Consequence | How to handle |
| --- | --- | --- |
| Thinking `Collectors.toList()` is always a mutable ArrayList | Implementation-dependent, not promised by the API | Use `toCollection(ArrayList::new)` when specifically needed |
| Thinking `stream.toList()` supports `add` | UnsupportedOperationException | Choose a mutable collection if mutation is actually needed |
| Using `HashSet::new` and relying on print order | No order guarantee | Use LinkedHashSet or TreeSet depending on the goal |
| Using `TreeSet::new` with non-Comparable objects | ClassCastException during collection | Pass a valid comparator |
| Comparator compares only a non-unique property | TreeSet drops records where comparator == 0 | Add a tie-breaker or use List if all must be kept |
| Assuming TreeSet always uses `equals` to determine duplicates | Actually uses compareTo/comparator == 0 | Design the comparator consistently with desired identity |
| Not checking for null before TreeSet/EnumSet | NPE when adding invalid elements | Validate or filter according to policy |
| Using `() -> shared` returning the same collection | Incorrect collection, especially in parallel | Create a new instance each time the Supplier is called |
| Using `() -> List.of()` as a factory | Collector cannot add elements | Supplier must return an accumulable collection |
| Assuming `IntStream.collect(Collectors.toCollection(...))` is valid | Wrong primitive stream collect API | Use `boxed()` or an appropriate primitive collect |
| Assuming the factory is called only once | False for some parallel collection strategies | Do not attach side effects to the factory |
| Confusing a mutable collection with mutable elements | Structural mutability does not mean deep copy | Define ownership and object mutability |
| Relying on order with an `unordered()` source | No stable order to preserve | Define an order or sort explicitly |
| Using a collector as a substitute for validation | Corrupted data may be silently dropped or altered in meaning | Validate the input contract explicitly |

## 16. Checklist for choosing an explicit Collection

Before writing `collect(Collectors.toCollection(...))`, ask yourself:

1. **Is a specific Collection type needed?** If only an unmodifiable List is needed, `toList()` may be cleaner.
2. **Do duplicates need to be preserved?** List keeps duplicates; Set removes duplicates according to its semantics.
3. **What order is required?** Encounter order, insertion order, natural ordering, or a custom comparator?
4. **After collecting, do you need to add/remove/re-sort?** Choose a factory with appropriate mutability.
5. **Can the source contain null?** Choose a policy matching the Collection and business contract.
6. **If using TreeSet, can the comparator return 0 for two distinct entities?** Consider a tie-breaker or use a List.
7. **If using an enum, can EnumSet be used?** The factory must specify the enum type explicitly.
8. **Does the Supplier create a new object every time?** Do not use a shared mutable instance.
9. **Will it run in parallel?** Do not rely on the number of Supplier calls or execution schedule.
10. **Is a deep copy needed?** `toCollection` typically only collects element references; it does not copy state.
11. **Should callers work through an interface or a concrete type?** Expose the minimal return type in public APIs, keeping the implementation choice local when possible.
12. **Have you tested empty sources, nulls, duplicate elements, comparators, and ordering?** These are the cases most likely to expose design flaws.

## 17. Practice exercises

### Exercise 1: Deduplicating and preserving order

Source `["a", "b", "a", "c", "b"]`. Collect using `ArrayList::new`, `LinkedHashSet::new`, and `TreeSet::new`. Predict the results and explain why Set does not keep duplicates.

### Exercise 2: Choosing a mutable type

Given `Stream.of("A", "B")`. Collect the results using `toList()` and `toCollection(ArrayList::new)`. Try calling `add("C")` on both results. Predict which one throws UnsupportedOperationException and explain why.

### Exercise 3: Comparator dropping records

Given two Products `("A", 100)` and `("B", 100)`. Write a TreeSet with a comparator based only on price and observe the size. Then add `thenComparing(Product::sku)` to keep both. If the real requirement is to keep every single record (even records with the same SKU), which collection type makes more sense?

### Exercise 4: Factory for EnumSet

Create an enum `Role { VIEWER, EDITOR, ADMIN }`. From a stream containing multiple occurrences of VIEWER, collect into an `EnumSet<Role>` using `toCollection(() -> EnumSet.noneOf(Role.class))`. Predict the print order based on the enum declaration.

### Exercise 5: Primitive stream needs boxed()

Create `IntStream.rangeClosed(1, 5)`, convert it to Stream<Integer> using `boxed()`, then collect into a `LinkedList<Integer>`. Why doesn't `IntStream` use the same `collect(Collector)` overload as Stream<Integer>?

### Exercise 6: Verifying an independent factory

Create two results using `source.stream().collect(toCollection(ArrayList::new))`. Modify the first list and verify that the second list remains structurally unchanged. Explain why `() -> sharedList` is not a valid Supplier for this case.

### Exercise 7: Choosing Collection types for business requirements

A website needs to:
- Display **all** orders sorted by total amount ascending.
- Display a **deduplicated** list of tags in first-seen order.
- Store access permissions using an **enum**.
- Find the minimum/maximum value in a set with a comparator.

Propose an appropriate Collection for each item, pointing out where a List is needed instead of a TreeSet to avoid losing elements.

## 18. Takeaways

**`Collectors.toCollection(Supplier<C>)` lets you explicitly choose the resulting Collection type** of an object Stream: `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, `TreeSet`, `EnumSet`, etc. The Supplier provides **a new accumulable collection**. When you need to configure a comparator, capacity, or enum type, use a lambda factory.

**The Collection type determines output semantics:** List keeps duplicates and has positions; Set removes duplicates; LinkedHashSet preserves insertion order; TreeSet sorts and uses a comparator to determine duplicates; EnumSet uses enum declaration order. Choosing the wrong type can **lose data**, not merely change the Java type.

**`Stream.toList()` cannot be structurally modified**, while `Collectors.toList()` does not guarantee implementation or mutability. If the caller needs a **mutable ArrayList**, `toCollection(ArrayList::new)` expresses the contract more clearly.

Before using a collector, ask: **"Do I really need to keep all elements, preserve order, remove duplicates, or use a specialized collection type — and does the factory create a new object suitable for those requirements?"**