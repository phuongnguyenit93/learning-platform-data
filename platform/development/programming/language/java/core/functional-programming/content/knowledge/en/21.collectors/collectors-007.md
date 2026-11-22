# `Collectors.toMap()` with Key and Value Mapper Functions in Java Stream

In Java Stream, `Collectors.toMap()` is used to **collect** elements into a `Map<K,V>`. The most important point is that the two functions you provide determine **what key and what value each source element becomes**:

~~~java
Map<K, V> result = stream.collect(
        Collectors.toMap(keyMapper, valueMapper));
~~~

Here, `keyMapper` takes **a source element** and returns a key `K`; `valueMapper` also takes **a source element** and returns a value `V`. Each element is passed through both functions to create a key–value pair. The collector completes when the terminal operation `collect(...)` runs.

For example, from `Stream<Employee>` you can create a `Map<Long,String>` using employee ID as the key and employee name as the value:

~~~java
Map<Long, String> nameById = employees.stream()
        .collect(Collectors.toMap(Employee::id, Employee::name));
~~~

The first two snippets are **in-method illustrations** with already-declared variables/types. The following sections have complete Java 17+ programs to compile and run.

**Three rules to remember right away:**

1. The two-argument overload **does not automatically handle duplicate keys**: if two elements produce the same key, the collector throws `IllegalStateException`.
2. Do not use a `valueMapper` that returns `null`: standard `Collectors.toMap` overloads do not accept null map values; it may throw `NullPointerException`.
3. `toMap(keyMapper, valueMapper)` **does not guarantee the Map type or iteration order**. If you need insertion order, sorted keys, or a specific map type, choose the overload with `mapSupplier`.

## 1. Reading the signature: two key and value mapper functions

The basic overload of `Collectors` has the form:

~~~java
// Simplified API signature for learning, not a standalone program.
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);
~~~

Reading by data types:

~~~text
Stream<T>
   keyMapper:   T → K
   valueMapper: T → U
   collect(toMap(...))
                ↓
             Map<K, U>
~~~

- `T`: the type of the **source element** flowing through the pipeline.
- `K`: the type of the **key** produced from each element.
- `U`: the type of the **value** produced from each element.
- `Function<T,R>`: a functional interface that takes a `T` and returns an `R`.
- `Collectors.toMap(...)`: is a **Collector**; `stream.collect(...)` is the terminal operation that executes the collection.

`keyMapper` and `valueMapper` can be lambdas, method references, or expressions that create new data. `K` and `U` do not need to be the same type as `T`.

Example with `T = Employee`, `K = Long`, `U = String`:

~~~java
Collectors.toMap(Employee::id, Employee::name)
~~~

If you want to keep the entire employee as the value, you can use `Function.identity()`:

~~~java
Collectors.toMap(Employee::id, java.util.function.Function.identity())
~~~

Then the result type is `Map<Long,Employee>`. `Function.identity()` returns the input object itself, **does not copy the object**, and does not create a clone.

## 2. Standalone example: creating keys and values different from the source type

Create the file `BasicToMapDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class BasicToMapDemo {
    record Employee(long id, String name, int score) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee(3, "Chi", 90),
                new Employee(1, "An", 80),
                new Employee(2, "Bình", 85));

        Map<Long, String> nameById = employees.stream()
                .collect(Collectors.toMap(
                        Employee::id,
                        Employee::name));

        Map<Long, Integer> doubledScoreById = employees.stream()
                .collect(Collectors.toMap(
                        e -> e.id(),
                        e -> e.score() * 2));

        System.out.println("nameById[2]=" + nameById.get(2L));
        System.out.println("size=" + nameById.size());
        System.out.println("doubleScore[1]=" + doubledScoreById.get(1L));
    }
}
~~~

~~~bash
javac --release 17 BasicToMapDemo.java
java BasicToMapDemo
~~~

Output:

~~~text
nameById[2]=Bình
size=3
doubleScore[1]=160
~~~

Explanation:

1. `employees.stream()` returns `Stream<Employee>`.
2. `Employee::id` retrieves `long`, which is boxed to `Long` because the generic key of `Map` is a reference type.
3. `Employee::name` returns `String`, so the first result is `Map<Long,String>`.
4. `e -> e.score() * 2` returns `int`, which is boxed to `Integer`, so the second result is `Map<Long,Integer>`.
5. Read results via `get(2L)` and `get(1L)`, instead of printing the entire `Map`, so you **do not depend on the iteration order** of the Map created by the two-argument overload.

Note that `2L` is `Long`; `map.get(2)` boxes `int` to `Integer`, which differs from `Long` and usually returns `null` even though key `2L` is present.

## 3. Duplicate keys: why does the two-argument overload throw an error?

A `Map` can only have **one value associated with each key**. If two source elements produce the same key, the `toMap(keyMapper,valueMapper)` overload cannot guess which value to choose.

For example, two employees both have `department = "IT"`:

~~~java
// Illustration: assumes Employee has a department() method.
employees.stream()
        .collect(Collectors.toMap(
                Employee::department,
                Employee::name));
~~~

If there are at least two employees with the key `"IT"`, this collection throws `IllegalStateException` due to a duplicate key. **Even when the two values are equal**, the basic overload does not treat that as a reason to allow overwriting a duplicate.

Duplicate keys are determined by the key equivalence mechanism of the created Map type (usually `equals`/`hashCode`; with `TreeMap`, by the tree's comparator). It is not based solely on being the same object reference.

Create the file `DuplicateKeyToMapDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class DuplicateKeyToMapDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Anna", "Adam", "Bình");

        try {
            names.stream().collect(Collectors.toMap(
                    s -> s.substring(0, 1),
                    s -> s));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate=" + ex.getClass().getSimpleName());
        }

        Map<String, String> firstByInitial = names.stream()
                .collect(Collectors.toMap(
                        s -> s.substring(0, 1),
                        s -> s,
                        (first, later) -> first));

        System.out.println("A=" + firstByInitial.get("A"));
        System.out.println("B=" + firstByInitial.get("B"));
    }
}
~~~

~~~bash
javac --release 17 DuplicateKeyToMapDemo.java
java DuplicateKeyToMapDemo
~~~

Output:

~~~text
duplicate=IllegalStateException
A=Anna
B=Bình
~~~

In the example, Anna and Adam both produce the key `"A"`; the two-argument overload throws an exception, whereas the overload with a **merge function** actively keeps the existing value when encountering a duplicate key.

Do not rely on the **exact content of the exception message** for business logic because messages may differ across Java versions; the exception type and the duplicate-key cause are what should be checked.

## 4. Three-argument overload: actively handling duplicate keys

When duplicate keys are **valid according to business logic**, choose:

~~~java
// Simplified API signature; not a standalone program.
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction);
~~~

`mergeFunction` takes **two `U` values of the same key**; it does not take two `T` elements of the stream and does not take the key `K` directly.

Common strategies:

| Situation | `mergeFunction` | Meaning |
| --- | --- | --- |
| Keep existing value | `(oldValue, newValue) -> oldValue` | Ignore the new value when the key is duplicated. |
| Take new value | `(oldValue, newValue) -> newValue` | The new value replaces the previous value. |
| Sum quantities | `Integer::sum` | Aggregate values that share the same key. |
| Keep higher value | `Integer::max` | Choose the largest value for the same key. |
| Concatenate strings | `(a, b) -> a + ", " + b` | Combine values into a string; order must be defined. |

A complete illustration to sum quantities by item code. Create the file `MergeQuantitiesDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MergeQuantitiesDemo {
    record Line(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("B", 4),
                new Line("A", 2),
                new Line("B", 3),
                new Line("A", 5));

        Map<String, Integer> totals = lines.stream()
                .collect(Collectors.toMap(
                        Line::sku,
                        Line::quantity,
                        Integer::sum,
                        TreeMap::new));

        System.out.println(totals);
    }
}
~~~

~~~bash
javac --release 17 MergeQuantitiesDemo.java
java MergeQuantitiesDemo
~~~

Output:

~~~text
{A=7, B=7}
~~~

Here `Line::sku` produces the `String` key; `Line::quantity` produces the `Integer` value via boxing from `int`; `Integer::sum` handles quantities on duplicate keys. `TreeMap::new` makes the result iterate keys in natural order, so stdout has the order `A`, `B`.

**Important when running in parallel:** the merge function should be **associative**, stateless, and non-interfering with the source. For example, addition is suitable; logic depending on external state or callback order can yield unpredictable results. For "keep first/last value", you must define "first/last" according to encounter order and consider whether the stream is ordered; do not assume by default that it means the latest record by timestamp.

## 5. Four-argument overload: controlling the Map type

If the application needs a specific Map, use the overload:

~~~java
// Simplified API signature for learning.
static <T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction,
        Supplier<M> mapSupplier);
~~~

Components:

1. `keyMapper`: `T -> K`.
2. `valueMapper`: `T -> U`.
3. `mergeFunction`: `(U,U) -> U`, applied when two keys are considered duplicates by the Map.
4. `mapSupplier`: `() -> M`, creates the target Map (and any necessary intermediate Maps).

Choose a supplier based on requirements:

| Map | Supplier example | Notable characteristics |
| --- | --- | --- |
| `HashMap` | `HashMap::new` | Does not guarantee iteration order. |
| `LinkedHashMap` | `LinkedHashMap::new` | Iterates in **insertion order** under default configuration. |
| `TreeMap` | `TreeMap::new` | Iterates keys in **comparator/natural order**; requires suitable key comparison. |

Create the file `MapSupplierDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapSupplierDemo {
    record Item(String code, int price) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("C", 30),
                new Item("A", 10),
                new Item("B", 20));

        Map<String, Integer> insertionOrder = items.stream()
                .collect(Collectors.toMap(
                        Item::code,
                        Item::price,
                        (existing, incoming) -> existing,
                        LinkedHashMap::new));

        Map<String, Integer> sortedKeys = items.stream()
                .collect(Collectors.toMap(
                        Item::code,
                        Item::price,
                        (existing, incoming) -> existing,
                        TreeMap::new));

        System.out.println("insertion=" + insertionOrder);
        System.out.println("sorted=" + sortedKeys);
    }
}
~~~

~~~bash
javac --release 17 MapSupplierDemo.java
java MapSupplierDemo
~~~

Output with the ordered `List` source and sequential pipeline above:

~~~text
insertion={C=30, A=10, B=20}
sorted={A=10, B=20, C=30}
~~~

`LinkedHashMap` maintains insertion order; `TreeMap` iterates in key order. However, this does **not** guarantee that every parallel/unordered stream has an insertion order matching a business requirement. If the output requires an exact order, ensure encounter order from the source and clear sorting/collection rules, or sort after collecting.

## 6. Handling `null` values: do not assume they are automatically skipped

A common bug is `valueMapper` returning `null`:

~~~java
// Snippet illustrating the risk:
Collectors.toMap(Product::sku, Product::description)
~~~

If `description()` returns `null`, the `toMap` collector may throw `NullPointerException`. With common JDK implementations and the standard collection contract, you should **avoid passing null values into toMap** in all overloads.

Clearly choose one of the following policies:

**A. Reject missing values:** validate elements or use `Objects.requireNonNull` with a message before putting into the Map.

~~~java
// Illustration snippet in a context where Product exists.
Collectors.toMap(
        Product::sku,
        p -> java.util.Objects.requireNonNull(
                p.description(), "Missing description: " + p.sku()))
~~~

**B. Use a business-appropriate default value:**

~~~java
Collectors.toMap(
        Product::sku,
        p -> p.description() == null ? "(unknown)" : p.description())
~~~

**C. Skip records without a value:** add `filter` before `collect` if business rules allow.

~~~java
products.stream()
        .filter(p -> p.description() != null)
        .collect(Collectors.toMap(Product::sku, Product::description))
~~~

The snippets above are **illustrations**, assuming `Product` and `products` are declared, and `sku` is unique. Option B must still handle duplicate keys if any; option C changes the **dataset** and is not equivalent to "keeping an entry with a null value".

Full runnable example, file `NullValueToMapDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NullValueToMapDemo {
    record Product(String sku, String description) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("A", "Bút"),
                new Product("B", null));

        try {
            products.stream().collect(Collectors.toMap(
                    Product::sku,
                    Product::description));
        } catch (NullPointerException ex) {
            System.out.println("null value=NullPointerException");
        }

        Map<String, String> fallback = products.stream()
                .collect(Collectors.toMap(
                        Product::sku,
                        p -> p.description() == null
                                ? "(unknown)" : p.description(),
                        (first, second) -> first,
                        TreeMap::new));

        System.out.println("fallback=" + fallback);
    }
}
~~~

~~~bash
javac --release 17 NullValueToMapDemo.java
java NullValueToMapDemo
~~~

Output:

~~~text
null value=NullPointerException
fallback={A=Bút, B=(unknown)}
~~~

**Null keys:** `toMap` overloads should also not be used with the assumption that null keys will be accepted. Some Map implementations/types may accept null keys, but there is no general guarantee across all overloads and suppliers; `TreeMap` with natural order normally does not allow null keys. Establish a non-null key contract, filter/reject null keys, or design explicit key-mapping rules.

## 7. Duplicate keys can appear even when data looks different

It is not only two "identical" elements that can produce duplicate keys. This happens when:

- `String::toLowerCase` turns `"ABC"` and `"abc"` into the same key (with uniform normalization).
- Extracting `emailDomain`: multiple addresses belong to the same domain.
- Extracting the year from a timestamp: multiple events occur in the same year.
- Extracting the first character of a name: multiple people start with the same letter.
- Using `TreeMap` with a case-insensitive comparator: two keys that differ under `String.equals` can still be treated as equivalent by the comparator.

Therefore, before choosing the two-argument overload, you must know that `keyMapper` **produces unique keys** according to the rules of the Map to be used. Otherwise, you must choose between `mergeFunction`, `groupingBy`, or changing the key type.

In particular, if multiple elements need to retain **all values** under the same key, `groupingBy` is usually more direct than `toMap`:

~~~java
// Illustration: multiple Employees have the same department.
Map<String, List<Employee>> grouped = employees.stream()
        .collect(Collectors.groupingBy(Employee::department));
~~~

Here the value type is `List<Employee>`, so no elements are lost on duplicate keys. Note that `groupingBy` also generally does not accept null grouping keys; validate the data or map to an explicit default key.

If you want to aggregate into counts, you can use `groupingBy(..., counting())` for `Map<K,Long>`. If you want to combine into a sum, `toMap(keyMapper, valueMapper, Integer::sum)` is also suitable.

## 8. When to use `toMap`, `groupingBy`, `toUnmodifiableMap`?

| Goal | Appropriate API | Notes |
| --- | --- | --- |
| Each element has a unique key, take one value | `toMap(keyMapper, valueMapper)` | Duplicate keys fail. |
| Duplicate keys are valid, need to combine into one value | `toMap(keyMapper, valueMapper, mergeFunction)` | Merge must have clear semantics. |
| Need a specific Map type | `toMap(keyMapper, valueMapper, mergeFunction, mapSupplier)` | Can choose `LinkedHashMap`, `TreeMap`... |
| One key holds multiple records | `groupingBy(classifier)` | Returns `Map<K,List<T>>` by default. |
| Need a Map that does not support modification after collection | `toUnmodifiableMap(keyMapper, valueMapper)` | Java 10+; null keys/values are invalid; duplicate keys still fail without merge. |

`Collectors.toUnmodifiableMap` has an overload for a merge function, but it does **not** have a `mapSupplier` overload like `toMap`. The resulting Map does not support updates via its API; nor should you rely on iteration order or implementation class unless guaranteed by the documentation.

`toMap` overloads without a supplier **do not guarantee** mutability, thread-safety, Map type, or serializability of the result. If you need a well-defined structure for a public API, choose an overload with a supplier or copy into a precisely defined structure, and check immutability requirements separately.

## 9. Method references and lambdas: choosing the right type at each step

A pipeline can transform types **before** calling `toMap`:

~~~text
List<Employee>
  .stream()                              → Stream<Employee>
  .filter(e -> e.active())               → Stream<Employee>
  .map(Employee::name)                   → Stream<String>
  .collect(toMap(String::length,
                 String::toUpperCase))   → Map<Integer, String>
~~~

After `map(Employee::name)`, the input element to both mappers in `toMap` is **`String`**, no longer `Employee`. Choosing `String::length` as the key can produce duplicates if two names have the same length — requiring a merge function or a different key.

A pattern that keeps the original object as the value:

~~~java
// Assume employees: List<Employee>, with unique and non-null id.
Map<Long, Employee> byId = employees.stream()
        .collect(Collectors.toMap(
                Employee::id,
                java.util.function.Function.identity()));
~~~

`Function.identity()` is an explicit way to write "the value is the source element itself". Although the map holds references to the original objects, there is no deep copy: if a mutable object is modified after collection, the value pointed to by the map reflects that change as well.

If the key is created from a **mutable** property, changing the property after insertion does not automatically update the map key. With a mutable key used directly whose `equals/hashCode` changes, lookup can break. Prefer immutable keys such as IDs, `String`, or immutable value objects.

## 10. Choosing a `Map` with normalized keys

If business logic requires grouping product codes case-insensitively, you should define the normalization operation and handle collisions.

Create the file `NormalizeKeyDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizeKeyDemo {
    record Product(String sku, int stock) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("ABC", 3),
                new Product("abc", 4),
                new Product("XYZ", 2));

        Map<String, Integer> stockBySku = products.stream()
                .collect(Collectors.toMap(
                        p -> p.sku().toLowerCase(Locale.ROOT),
                        Product::stock,
                        Integer::sum,
                        LinkedHashMap::new));

        System.out.println(stockBySku);
    }
}
~~~

~~~bash
javac --release 17 NormalizeKeyDemo.java
java NormalizeKeyDemo
~~~

Output with an ordered sequential source:

~~~text
{abc=7, xyz=2}
~~~

Use `Locale.ROOT` to avoid case normalization depending on the environment's default locale. Depending on the data domain, normalization may need other steps such as trim, Unicode normalization, or custom ID rules; do not arbitrarily apply `toLowerCase` to keys that are case-sensitive by contract.

The key point is the **merge policy**: `Integer::sum` adds stock from two codes normalized to the same key. If you do not want to merge, validate key uniqueness and let the error surface, rather than silently picking one record.

## 11. Collecting on empty streams and in parallel environments

When the source is truly empty, `collect(toMap(...))` returns an **empty Map** per a valid collector. There are no elements on which to call `keyMapper`, `valueMapper`, or `mergeFunction`. The supplier may be used to create the result container.

Illustrative example:

~~~java
// Inside a method where the corresponding classes are already imported.
Map<String, Integer> result = java.util.stream.Stream.<String>empty()
        .collect(java.util.stream.Collectors.toMap(
                s -> s,
                String::length));
System.out.println(result.isEmpty()); // true
~~~

With a **parallel stream**, the collector may create multiple intermediate maps and then merge them. Therefore:

- Do not rely on the number of invocations or call order of mappers/merge to perform side effects.
- Mappers and merge should be **stateless** and non-interfering; merge needs appropriate associativity so results do not depend on grouping.
- Do not assume the output `Map` of standard `toMap` is a concurrent map or can be safely modified by multiple threads. The final result is a Map; thread-safety depends on the implementation and subsequent usage.
- If you truly need a concurrent collector, look into `Collectors.toConcurrentMap` along with its constraints, rather than calling `parallel()` and thinking the Map type changes automatically.
- For requirements on insertion order, tie-breaking, or "keeping the first record", define encounter order and test with real data, especially when the initial source is unordered.

## 12. Common mistakes and how to spot them

1. **Forgetting both mappers use the same source element type**: after `map`, `toMap` no longer receives the previous type.
2. **Assuming all keys are unique**: real data produces duplicates and the two-argument overload throws `IllegalStateException`.
3. **Confusing duplicate keys with duplicate values**: multiple keys can validly share the same value; **the same key** is the issue.
4. **Using a nullable `valueMapper`**: hits `NullPointerException`. Explicitly choose to skip, default, or fail-fast.
5. **Relying on `HashMap` accepting null keys**: the collector and supplier contracts do not allow generalizing to all maps; validate keys.
6. **Assuming `toMap` always sorts**: two/three-argument overloads do not guarantee iteration order or Map type.
7. **Thinking `mergeFunction` receives the key and new value**: it receives two **old/new values** for the same key.
8. **Using `(a,b) -> a` when all records must be saved**: loses information; `groupingBy` is usually more suitable.
9. **Using `toMap` for summing and forgetting merge**: a key appearing multiple times causes an error instead of summing.
10. **Using mappers/merge with side effects**: results can vary with execution, especially in parallel.
11. **Using mutable keys**: changing `equals/hashCode` or key properties can break lookups.
12. **Confusing `toMap` with `Map.of`**: `Map.of` creates a Map directly from fixed pairs and does not accept null/duplicate keys; `toMap` is a collector for Streams.
13. **Assuming the resulting Map is mutable by contract**: basic `Collectors.toMap` does not guarantee mutability, so do not design around characteristics of the current implementation.
14. **Thinking `TreeMap` uses `equals/hashCode` like `HashMap`**: TreeMap relies on comparator/natural order to determine key equivalence.
15. **Overlooking `Map.get` with a mismatched key type**: `Map<Long,V>` must be looked up with `Long` (e.g. `1L`), not `Integer` (`1`).
16. **Reusing a single stream for multiple `collect` calls**: a terminal operation consumes the stream; you must create a new stream from a re-readable source.

## 13. `toMap()` design checklist

Before writing the collector, confirm:

- What is the **source `T`** type right before `collect`?
- Where is the **key `K`** created from, and is it immutable, non-null, and unique?
- Is the **value `U`** a property, transformed data, or the whole element via `Function.identity()`?
- If two elements share the same key, should it **error**, keep one value, sum, pick min/max, or **keep all** via `groupingBy`?
- Are there clear rules for **null values** and **null keys**?
- Do you need `HashMap`, `LinkedHashMap`, `TreeMap`, or an unmodifiable Map?
- Is result ordering required? If so, is ordering based on encounter order or key comparator?
- Is it running a parallel stream, or are mappers/merge expensive, side-effecting, or accessing mutable state?
- Do tests cover **empty streams**, **duplicate keys**, **null values**, **null keys**, **mismatched key types on lookup**, and **Map ordering**?

**Remember:** `Collectors.toMap(keyMapper, valueMapper)` is the way to express **each element `T` becomes a `K → U` pair**. It does not handle duplicate keys automatically, is not a tool that allows null values, and does not implicitly guarantee Map order. When you need merging or a specific Map type, choose the three/four-argument overload, describe merge semantics clearly, and preserve correctness on real datasets.