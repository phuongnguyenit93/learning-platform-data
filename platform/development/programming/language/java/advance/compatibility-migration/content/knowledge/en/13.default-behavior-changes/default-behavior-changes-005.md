# Iteration order and behaviors not guaranteed by APIs

## 1. Why “still runs like before” does not necessarily mean compatible?

When upgrading the JDK, frameworks, libraries, or changing an implementation, many Java applications continue to compile and run without throwing exceptions, yet the observed data differs from before. A common cause is application code relying on **iteration order**, **processing order**, or a behavioral detail that the API never guaranteed.

For example, an application puts data into a `HashMap` and then iterates over `map.keySet()` to generate a report. Across many runs, the keys may appear in the same order. The development team easily mistakes that order for a “Java default”. After upgrading the JDK or changing the number of elements, the report reverses or scrambles its order; snapshot tests start failing, or users see unstable display order. However, `HashMap` does not guarantee iteration order, so an order change is not necessarily a bug in the new JVM or library.

Similar situations arise when:

- Using `HashSet` to build a list sent via an API and expecting elements to match insertion order.
- Using `Map.of(...)`, `Set.of(...)`, or `Collectors.toSet()` and relying on the observed order.
- Changing `stream()` to `parallelStream()` while continuing to use `forEach` for ordered side effects.
- Using the output of `Files.list(...)` or `Class.getDeclaredMethods()` and assuming it reflects filesystem order or source declaration order.
- Reading SQL data without `ORDER BY` and treating the returned row order as stable.
- Using `PriorityQueue.iterator()` and expecting elements to be iterated in priority order.
- Comparing JSON/text serializations as strings when key or metadata ordering has no defined contract.

The goal of this lesson is to recognize behaviors that are **guaranteed**, **not guaranteed**, and **conditional on specific prerequisites**; from there, design code and tests so results do not depend on accidental implementation details.

## 2. Three contract tiers to distinguish

### 2.1. Behavior guaranteed by specification

An API may provide an explicit guarantee regarding order or observable effects. For example:

- `List` is an ordered collection whose elements have index-based positions.
- `LinkedHashMap` maintains insertion order during iteration by default, while an access-order mode can be configured.
- `TreeMap` iterates entries according to key order determined by natural ordering or a comparator.
- An ordered stream collected into a list using operations that preserve encounter order will retain the corresponding order.

When relying on these guarantees, application code has grounds to expect a new implementation to continue complying. If behavior changes contrary to the specification, it may be an implementation regression or because a contract condition is no longer satisfied.

### 2.2. Behavior not guaranteed by specification

“Not guaranteed” does not mean every run will necessarily be random. An implementation can iterate through elements in a very consistent order for years, yet still retain the right to change internal structure, table sizing, hash distribution, or optimization strategies.

For example, `HashMap` might coincidentally return keys in ascending order for a simple set of `Integer`s in one JDK version. That result **does not form a contract**. Changing keys, changing capacity, adding elements, or switching JDKs can alter the order.

Rule of thumb: **When API documentation does not promise order, do not infer order from a sample output.**

### 2.3. Behavior guaranteed only when conditions are met

Some APIs have conditional contracts:

- `Stream.findFirst()` returns the first element by **encounter order if the stream has an encounter order**. If the source is unordered, the notion of “first” does not provide a stably meaningful choice.
- `Stream.forEachOrdered()` respects encounter order when the stream has such order; it does not create order for an unordered source.
- `Collections.sort(...)` or `List.sort(...)` relies on a comparator; the result may be underdetermined if the comparator does not distinguish two objects that business logic requires ordering separately.
- `LinkedHashMap` guarantees order according to its mechanism, but when **access-order** is enabled, read operations can change iteration order.

When reviewing a migration, clearly document which conditions establish the guarantee, rather than merely writing “ordered” or “unordered”.

## 3. Concepts to understand accurately

**Iteration order** is the order of elements returned by an `Iterator` or a `for-each` loop.

**Encounter order** in the Stream API is the order in which the pipeline receives elements from the source and intermediate operations, if the source/pipeline defines such an order.

**Insertion order** is the order in which elements were first added, commonly seen in `LinkedHashMap` and `LinkedHashSet` under default configuration.

**Access order** is the order updated according to accesses, which can be configured in `LinkedHashMap`.

**Sorted order** is the order determined by natural ordering or a `Comparator`, as in `TreeMap` or `TreeSet`.

**Execution order** is the order in which operations, callbacks, or side effects actually occur. It does not always match iteration order, especially in multithreaded environments or asynchronous processing.

**Determinism** is predictability: the same input under the same contract conditions yields the same observable result. An algorithm may process using different internal orders yet still produce deterministic output, or vice versa.

**Behavioral compatibility** is the ability to preserve the observable results and effects that consumers are entitled to rely upon. Binary compatibility only indicates that bytecode can link; it does not guarantee behavior in this category.

## 4. Comparison table of common Java collections

| Structure | Iteration/order contract | Migration notes |
| --- | --- | --- |
| `ArrayList` | Preserves element order by position in list | Index and order are meaningful |
| `LinkedList` | Preserves element order of the list | Do not confuse “ordered” with “sorted” |
| `HashSet` | Does not guarantee iteration order | Does not preserve insertion order by default |
| `LinkedHashSet` | Preserves insertion order per collection mechanism | Does not sort by value automatically |
| `TreeSet` | Elements are ordered by natural ordering/comparator | Comparator also decides which elements are considered duplicates |
| `HashMap` | Does not guarantee key, entry, or value order | Output can change when hash structure changes |
| `LinkedHashMap` | Insertion-order by default; access-order selectable | Accesses can alter order if access-order is enabled |
| `TreeMap` | Entries are traversed in key order | Comparator also affects key equality condition |
| `ConcurrentHashMap` | Does not guarantee iteration order | Iterator is weakly consistent, does not create an atomic snapshot |
| `CopyOnWriteArrayList` | List-ordered; iterator uses array snapshot at creation time | Does not see changes made after iterator creation |
| `PriorityQueue` | `poll()` returns highest-priority element per comparator/natural order | `iterator()` has no guaranteed priority order |
| `List.of(...)` | Preserves order of passed elements | List cannot be modified via mutation APIs |
| `Set.of(...)` | Does not guarantee iteration order | Rejects `null` or duplicate elements |
| `Map.of(...)` | Does not guarantee iteration order | Rejects `null` keys/values or duplicate keys |

Do not look at one output and infer that every collection in the table behaves the same way. This table only summarizes common contracts; you still need to check specific overloads, wrappers, and API conditions.

### 4.1. `HashMap` is not `LinkedHashMap`

~~~java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> unordered = new HashMap<>();
unordered.put("third", 3);
unordered.put("first", 1);
unordered.put("second", 2);

for (String key : unordered.keySet()) {
    System.out.println(key);
}
// Not guaranteed to print in the order third, first, second.

Map<String, Integer> insertionOrdered = new LinkedHashMap<>();
insertionOrdered.put("third", 3);
insertionOrdered.put("first", 1);
insertionOrdered.put("second", 2);

for (String key : insertionOrdered.keySet()) {
    System.out.println(key);
}
// In insertion order: third, first, second.
~~~

With `HashMap`, the fact that a JDK version produces a neat order does not make it a `LinkedHashMap`. Do not write tests expecting a specific order for `HashMap.keySet()`, `entrySet()`, or `values()`.

### 4.2. `LinkedHashMap` can be in access-order mode

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> cache = new LinkedHashMap<>(
        16, 0.75f, true); // accessOrder = true

cache.put("a", 1);
cache.put("b", 2);
cache.put("c", 3);

cache.get("a");

System.out.println(cache.keySet()); // [b, c, a]
~~~

In access-order mode, accessing an entry can move it to the end of the order. This is the basis for some least-recently-used caches, yet can surprise consumers assuming the map always maintains insertion-order. In particular, avoid modifying structure or unexpectedly changing order while an iterator is active.

### 4.3. `TreeMap` is a sorted map, not an insertion-ordered map

~~~java
import java.util.Map;
import java.util.TreeMap;

Map<String, Integer> byKey = new TreeMap<>();
byKey.put("z", 1);
byKey.put("a", 2);
byKey.put("m", 3);

System.out.println(byKey.keySet()); // [a, m, z]
~~~

The order comes from the natural ordering of `String` keys, not insertion order. Using a different comparator yields a different order. Adding a case-insensitive comparator or key normalization can make some keys equivalent under the comparator, even changing the entry count.

## 5. `HashMap` and `HashSet`: order can be stable yet is not a contract

### 5.1. Why can you not infer from current hashing behavior?

`HashMap` organizes data using hash buckets and internal management mechanisms. Iteration order can be affected by hash codes, capacity, resizing, the key set, hash collisions, and the JDK implementation. A few key sets make iteration order look regular, but that is solely a result of internal structure.

Do not write code like:

~~~java
Map<Integer, String> map = new HashMap<>();
for (int i = 0; i < 10; i++) {
    map.put(i, "value-" + i);
}

// Wrong if treating this observation as a contract:
// "keySet() always returns 0, 1, 2, ..., 9"
~~~

Running the code repeatedly and getting the same order only proves what was observed in those runs; it does not prove Java guarantees that outcome.

### 5.2. `HashSet` relies on a hash structure, not preserving insertion order

~~~java
Set<String> tags = new HashSet<>();
tags.add("backend");
tags.add("mobile");
tags.add("security");

for (String tag : tags) {
    System.out.println(tag);
}
~~~

Do not treat the console order as the input order. If the requirement is **iterating in insertion order**, use `LinkedHashSet`. If the requirement is **sorting by value**, use `TreeSet` or sort a list with a comparator.

### 5.3. You cannot recover the “original insertion order” from a map without that contract

A common migration mistake:

~~~java
Map<String, Integer> source = new HashMap<>();
// ... source has already been populated beforehand.

Map<String, Integer> copied = new LinkedHashMap<>(source);
~~~

`copied` will maintain **the order it received when iterating the source**, yet `source` does not guarantee that order. Copying afterward does not turn lost insertion history into recoverable information.

If the original order matters, you must use an ordered collection from the moment data is collected or store an explicit order/sequence field.

## 6. Immutable collections do not imply order either

Since Java 9, collections can be concisely created using factories:

~~~java
List<String> steps = List.of("validate", "charge", "notify");
Set<String> roles = Set.of("reader", "writer", "admin");
Map<String, Integer> priority = Map.of(
        "high", 1,
        "normal", 2,
        "low", 3);
~~~

Points to distinguish:

- `List.of(...)` preserves element order when creating the list.
- `Set.of(...)` does not guarantee iteration order.
- `Map.of(...)` does not guarantee iteration order of entries/keys/values.
- These collections do not support direct add/remove/modify operations.
- `Set.of(...)` forbids duplicate or `null` elements; `Map.of(...)` forbids duplicate keys, `null` keys, or `null` values.

Changing:

~~~java
Map<String, Integer> result = new LinkedHashMap<>();
// ...
~~~

to:

~~~java
Map<String, Integer> result = Map.of(
        "high", 1, "normal", 2, "low", 3);
~~~

does not only change mutability. It can also drop the order guarantee. Consumers using `result.keySet()` to render UI will no longer have grounds to rely on the order written in source.

### 6.1. `copyOf` and wrappers do not “normalize” order by themselves

`List.copyOf(collection)` creates an unmodifiable list preserving the iteration order of the input collection at copy time. If the source is a `HashSet`, the resulting list only reflects an iteration not guaranteed by the source.

`Set.copyOf(...)` and `Map.copyOf(...)` provide no contract preserving the source's insertion-order. `Collections.unmodifiableMap(...)` preserves the iteration behavior of the wrapped map, yet only prevents modifications **through the wrapper**; it does not turn a `HashMap` into an ordered map and does not prevent changes if other code still holds a reference to the backing map.

An unmodifiable collection is not necessarily an immutable snapshot of source data; check whether the collection-creating API returns a copy or a view.

## 7. `PriorityQueue`: priority does not equal iterator order

`PriorityQueue` is designed to access the head element of the queue according to natural ordering or a comparator. It does not guarantee that its iterator will traverse all elements in priority order.

~~~java
import java.util.PriorityQueue;

PriorityQueue<Integer> queue = new PriorityQueue<>();
queue.add(30);
queue.add(10);
queue.add(20);

for (Integer value : queue) {
    System.out.println(value);
}
// Not guaranteed to print 10, 20, 30.
~~~

If you need **consumption by priority**, use `poll()`:

~~~java
while (!queue.isEmpty()) {
    System.out.println(queue.poll());
}
// In priority order of the comparator/natural ordering.
~~~

Note that `poll()` mutates the queue. If you need non-destructive reporting, copy the queue and poll the copy, or transfer elements to a list and sort:

~~~java
List<Integer> sorted = new ArrayList<>(queue);
sorted.sort(Integer::compareTo);
~~~

If multiple elements share the same priority level, a standard priority queue does not provide an insertion-order tie-breaker. For deterministic order, the comparator needs an additional distinguishing key such as a sequence number.

## 8. Stream API: encounter order and execution order

### 8.1. The stream source determines a lot

~~~java
List<String> list = List.of("c", "a", "b");
List<String> fromList = list.stream()
        .map(String::toUpperCase)
        .toList();
// [C, A, B] because list has an encounter order.

Set<String> set = new HashSet<>(list);
List<String> fromSet = set.stream()
        .map(String::toUpperCase)
        .toList();
// No guarantee that it is [C, A, B].
~~~

`Stream.toList()` (Java 16+) creates a result list matching the stream's encounter order **if the stream has an encounter order**. It does not create meaningful order for an unordered source. Additionally, the list returned by `Stream.toList()` does not allow mutation operations; migrating from `collect(Collectors.toList())` can affect consumers that used to mutate the result list.

### 8.2. `forEach` and `forEachOrdered`

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

numbers.parallelStream()
        .forEach(System.out::println);
// Does not guarantee side-effect order as 1, 2, 3, 4, 5.
~~~

If side effects are needed in encounter order:

~~~java
numbers.parallelStream()
        .forEachOrdered(System.out::println);
// Respects the stream's encounter order.
~~~

`forEachOrdered` does not mean every action runs on the same thread or strictly sequentially like hand-written application code. It guarantees the corresponding order per the API contract; assumptions about thread identity, locks, or performance still need evaluation.

When side effects must be strictly ordered and there is no clear parallelism benefit, a sequential pipeline is usually simpler:

~~~java
numbers.stream().forEachOrdered(System.out::println);
~~~

### 8.3. `findFirst()`, `findAny()`, and `unordered()`

~~~java
String first = names.stream().findFirst().orElseThrow();
String any = names.parallelStream().findAny().orElseThrow();
~~~

`findFirst()` means first according to encounter order when order exists; `findAny()` is permitted to pick any element to allow optimization, especially in parallel streams. Switching from `findFirst()` to `findAny()` can change the result, even though both return `Optional<T>`.

`unordered()` declares that the pipeline does not need to preserve encounter order requirements. Do not add `unordered()` just to improve performance if the output serves pagination, display, or ordered events.

### 8.4. `sorted()` and stability

`Stream.sorted()` sorts by natural ordering; `sorted(comparator)` uses the specified comparator. For ordered streams, the sort is stable; for unordered streams, there is no matching guarantee to preserve relative order among elements considered equal by the comparator.

If two objects share the same `priority` yet need a stable order, add a tie-breaker:

~~~java
Comparator<Task> order = Comparator
        .comparingInt(Task::priority)
        .thenComparing(Task::id);

List<Task> sorted = tasks.stream()
        .sorted(order)
        .toList();
~~~

The condition is that `id` must have stable meaning and be able to distinguish tasks when needed. The comparator must align with business goals; a comparator where multiple elements compare equal does not guarantee deterministic output if the source is unordered.

## 9. Collectors and resulting data structures

### 9.1. `Collectors.toSet()` does not promise to preserve order

~~~java
Set<String> names = users.stream()
        .map(User::name)
        .collect(Collectors.toSet());
~~~

Do not assume this set preserves user order from the stream. If you need a collection preserving insertion order per the source's encounter order, specify the supplier explicitly:

~~~java
Set<String> names = users.stream()
        .map(User::name)
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

If sorting by value is required:

~~~java
Set<String> names = users.stream()
        .map(User::name)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Note that `TreeSet`'s comparator/natural ordering can affect whether elements are treated as duplicates. When handling natural language, `String`'s comparator is not automatically equivalent to the user's locale-specific collation.

### 9.2. `Collectors.toMap()` does not guarantee map type or order

~~~java
Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(User::id, Function.identity()));
~~~

Do not rely on the order of `byId.entrySet()`. If you need key order by first appearance in a **stream with encounter order**, specify a map factory and merge function:

~~~java
Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(
                User::id,
                Function.identity(),
                (first, duplicate) -> first,
                LinkedHashMap::new));
~~~

If you want sorting by key, you can use `TreeMap::new` instead of `LinkedHashMap::new`, provided the keys and comparator are appropriate.

### 9.3. `groupingBy` and group order

~~~java
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(Order::status));
~~~

The key order of the grouping map is not derived from order sequence or status enum order. If you want to maintain group order by first encounter in a sequential stream with encounter order:

~~~java
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(
                Order::status,
                LinkedHashMap::new,
                Collectors.toList()));
~~~

If you want a report in business order `NEW` → `PAID` → `SHIPPED`, the clearest way is to represent that order explicitly with a defined list or comparator, not infer it from group appearance order in the source data.

### 9.4. `Collectors.toList()` and mutability

Do not assume a specific implementation or mutability for the list returned by `Collectors.toList()` across all versions/implementations. If you need a mutable list, you can specify:

~~~java
List<String> mutable = stream.collect(
        Collectors.toCollection(ArrayList::new));
~~~

If an unmodifiable result is needed, state that intent with the appropriate API, such as `Stream.toList()` on supported JDKs or `Collectors.toUnmodifiableList()` when element constraints allow. Mutability and ordering are two independent contract dimensions.

## 10. Thread concurrency: iterators are not ordered snapshots

### 10.1. Fail-fast is not a synchronization mechanism

Iterators of some collections like `ArrayList` and `HashMap` have a mechanism to detect improper structural modifications and may throw `ConcurrentModificationException`. However, the fail-fast mechanism is **best effort**, not a guarantee of catching every race condition.

~~~java
List<String> values = new ArrayList<>(List.of("a", "b", "c"));
for (String value : values) {
    if (value.equals("b")) {
        values.remove(value); // Not a safe way to modify during a loop.
    }
}
~~~

When removing elements in a loop, use `Iterator.remove()` if supported by the iterator, or an API like `removeIf(...)` per the collection contract. When multiple threads modify concurrently, use a proper concurrency strategy rather than taking the absence of exceptions as proof of safety.

### 10.2. `ConcurrentHashMap` has a weakly consistent iterator

`ConcurrentHashMap` permits concurrent operations; its iterator may observe some changes occurring during iteration, yet does not provide an atomic snapshot of the entire map and does not guarantee order.

~~~java
ConcurrentHashMap<String, Integer> counters = new ConcurrentHashMap<>();
counters.put("a", 1);
counters.put("b", 2);

for (Map.Entry<String, Integer> entry : counters.entrySet()) {
    System.out.println(entry);
}
~~~

This code should not be used to generate a report requiring both a **consistent snapshot** and **stable order**. If business requirements demand both properties, implement an appropriate snapshot/locking/versioning mechanism, then sort by a deterministic key.

### 10.3. `CopyOnWriteArrayList` has a snapshot iterator

With `CopyOnWriteArrayList`, the iterator traverses a snapshot of the array at iterator creation time, so it does not automatically reflect elements added afterward:

~~~java
CopyOnWriteArrayList<String> values =
        new CopyOnWriteArrayList<>(List.of("a", "b"));

Iterator<String> iterator = values.iterator();
values.add("c");

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
// This iterator only sees a and b.
~~~

A snapshot iterator differs from a weakly consistent iterator. Both collections may avoid fail-fast errors in the scenario above, yet have different contracts regarding which elements are visible.

### 10.4. Completion order is not submission order

~~~java
List<CompletableFuture<Result>> futures = submitTasks();
~~~

Tasks may complete in an order different from creation order. Placing results into a shared collection immediately upon completion can make output reflect completion order. If results are needed in input order, attach an index/sequence to each task and re-sort or collect in the designed index order.

Do not treat the moment a thread is scheduled as a default business order. The scheduler, CPU, GC, and I/O can alter completion order without violating the API.

## 11. Filesystem-related APIs: `Files.list` and `DirectoryStream`

Do not assume files are returned sorted by name, modification date, or on-disk order:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
// Not guaranteed to be ordered by file name.
~~~

If ascending file names are desired:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<Path> sorted = paths
            .sorted(Comparator.comparing(
                    path -> path.getFileName().toString()))
            .toList();

    sorted.forEach(System.out::println);
}
~~~

`Files.list` returns a stream backed by a system resource and therefore must be closed using try-with-resources. Filesystem traversal order is not a business contract.

`Files.walk` follows depth-first traversal rules, yet does not mean entries within the same directory are sorted by name. If a globally deterministic ordered list is needed, define a comparator and collect/sort as required. When symlinks exist or the directory tree changes during traversal, also check traversal semantics and limits.

If the criterion is “newest file”, do not merely take `findFirst()` from `Files.list`. Read timestamp metadata using the appropriate API, handle duplicate timestamps, and define a tie-breaker; if files may change during scanning, consider consistency.

## 12. Reflection and class member order

Reflection APIs such as:

~~~java
Method[] methods = MyType.class.getDeclaredMethods();
Field[] fields = MyType.class.getDeclaredFields();
~~~

do not guarantee returning arrays in source declaration order. A framework picking the first method, or serializing fields in the order returned by reflection, can create behavior dependent on the JDK/compiler implementation.

If a meaningful order is needed, specify it:

~~~java
Method[] methods = MyType.class.getDeclaredMethods();

Arrays.sort(methods,
        Comparator.comparing(Method::getName)
                .thenComparing(method -> Arrays.toString(
                        method.getParameterTypes())));
~~~

This is only an illustrative comparator. With overloaded methods, bridge/synthetic members, return types, and type names, choose distinguishing keys suited to the goal. If order is a business contract, an `@Order` annotation, configuration list, or explicit metadata is usually better than inferring from reflection names.

Similarly, do not use the order of `getDeclaredConstructors()` or `getMethods()` to determine a “preferred constructor/method” when the API provides no such contract.

### 12.1. Metadata and code generation

Tools such as ORMs, serializers, mappers, or DI containers may discover members via reflection. When upgrading JDK/framework versions, the discovered order may change. If a code generator relies on that order to generate schemas, request signatures, or source code, the output can change even though the source model did not.

The solution is to declare order through a stable structure: framework-supported property order annotations, an explicit order schema, or a deterministic comparator. Do not fix it by hoping “reflection in older JDKs always returns source order”.

## 13. Database data: without `ORDER BY`, no row order is promised

A Java application may read results via JDBC/JPA/Hibernate:

~~~sql
SELECT id, created_at, total
FROM orders;
~~~

Without `ORDER BY`, SQL does not guarantee record order, regardless of current indexes or execution plans. After upgrading a driver, database, ORM, or adding an index, the result set may stay identical while the order differs.

If the API needs newest orders first:

~~~sql
SELECT id, created_at, total
FROM orders
ORDER BY created_at DESC, id ASC;
~~~

`id` acts as a tie-breaker to distinguish records with the same `created_at`, provided `id` is a stable, data-unique key.

### 13.1. Pagination requires deterministic order

A query like:

~~~sql
SELECT id, created_at
FROM orders
LIMIT 20 OFFSET 20;
~~~

is not sufficient to define the second page without an order. Consequences can include records reappearing or disappearing across pagination calls.

Even with `ORDER BY` added, data inserted/deleted concurrently between requests can still cause offset pagination to drift. When stronger consistency is needed, consider snapshot transactions, cursor/keyset pagination, or an appropriate pagination contract.

When migrating ORMs/frameworks, inspect the actual query, not just the method name. A repository previously “coincidentally returning by ID” may have been an artifact of an execution plan rather than a guarantee.

## 14. JSON, serialization, and text-based results

### 14.1. JSON arrays are ordered; JSON objects should not use key order as business logic

Example:

~~~json
{
  "items": ["A", "B", "C"],
  "metadata": {
    "name": "report",
    "version": 2
  }
}
~~~

Element order in the `items` array is meaningful when defined by the protocol. For members of the JSON object `metadata`, consumers should not assume order carries business meaning just because the old serializer wrote `name` before `version`.

A library serializing a `Map` may emit fields according to the map's iteration order. If the map is a `HashMap`, the resulting JSON text can differ after migration even though the data has the same keys/values.

This especially matters when:

- Saving snapshots or golden files as raw strings.
- Hashing the raw JSON string as a cache key.
- Digitally signing the byte representation without a canonicalization step.
- Generating diffs or configs from an unordered map.

If a deterministic representation is required, use a well-defined canonical serialization, or sort fields according to a schema before emitting text. Do not merely swap the map for `TreeMap` and assume all nested types, floating-point numbers, Unicode, and nulls are fully canonicalized.

### 14.2. `toString()` is usually not a storage protocol

`Map.toString()` and many other `toString()` implementations primarily serve debugging. If an application parses that string to recover data, it is relying on a representation that can change.

Example that should not be used as a durable data format:

~~~java
String saved = someMap.toString();
~~~

Instead, define an explicit schema and public serializer/deserializer. If using a format for logs, do not require downstream parsers to rely on the exact order of fields that have no ordering contract.

### 14.3. Reflection-based serializers

If a serializer iterates `getDeclaredFields()` and writes fields in iteration order, the output may differ when the compiler or runtime changes. Specify field order via schemas/annotations or use an encoder with canonical output when deterministic formatting is genuinely needed.

## 15. String ordering, locale, timezone, and environment-dependent defaults

Another easily mistaken assumption is “Java defaults will be the same everywhere”. Several APIs depend on environment configuration or context when code does not specify them explicitly:

- `Locale.getDefault()` can affect formatting, case mapping, and collators.
- `ZoneId.systemDefault()` can affect time display.
- The default charset of certain APIs/systems must be checked against the JDK version and runtime configuration.
- Filesystem ordering, OS configuration, and native providers can differ across machines.

When sorting strings for users, `String.compareTo` compares using Java's natural ordering, which is not automatically the proper alphabetical sort across all languages. Use `Collator` when business logic requires locale-specific rules:

~~~java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

List<String> names = new ArrayList<>(inputNames);
names.sort(collator);
~~~

A locale-based comparator may treat two strings as equivalent at a given comparison strength. If strictly deterministic results are needed for ties, add a tie-breaker and define normalization/case handling.

Do not assume that “having called `sorted()`” suffices in every case. Know which rules, locale, null handling, and tie-breaker govern the sort.

### 15.1. Rules for choosing sort keys

A stable comparator usually needs:

1. A primary business field, such as `priority` or `createdAt`.
2. Null-handling rules for each field where applicable.
3. A stable tie-breaker, such as a unique ID.
4. Documented ascending/descending order.
5. Attention to whether the comparator meets `TreeMap`/`TreeSet` requirements when used to determine key uniqueness.

Example:

~~~java
Comparator<Order> ordering =
        Comparator.comparing(
                Order::createdAt,
                Comparator.nullsLast(Comparator.reverseOrder()))
            .thenComparing(Order::id);

List<Order> result = orders.stream()
        .sorted(ordering)
        .toList();
~~~

Here the result depends on the contract of `Order.id()` and `Order.createdAt()`. If `id` can be `null`, the comparator needs its own null rule; if the ID is not unique, add a distinguishing key or accept that the order of equivalent elements is unspecified.

## 16. Java 21 `SequencedCollection`: expressing order more clearly

Java 21 adds the sequenced collections API family, comprising `SequencedCollection`, `SequencedSet`, and `SequencedMap`, for structures with a well-defined encounter order. APIs such as `getFirst()`, `getLast()`, `reversed()`, and related sequenced operations help programs express ordering intent.

Example on JDK 21+:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SequencedCollection;

SequencedCollection<String> workflow =
        new ArrayList<>(List.of("validate", "charge", "notify"));

System.out.println(workflow.getFirst()); // validate
System.out.println(workflow.getLast());  // notify
System.out.println(workflow.reversed()); // view in reverse order
~~~

Key points:

- Using sequenced APIs communicates an encounter order contract more clearly than declaring a generic `Collection` when order truly matters.
- Not every collection is ordered; `HashSet`/`HashMap` do not automatically become ordered structures simply by upgrading the JDK.
- `reversed()` returns a view with reversed encounter order; distinguish between a view and a snapshot if the collection may be mutated.
- If the target runtime is below JDK 21, you cannot use the new API directly without raising the supported Java level.

When evolving a public API, changing a return type from `Collection<T>` to `SequencedCollection<T>` requires evaluating source/binary compatibility. Even though the intent to “preserve order” is clearer, changing the descriptor can still impact already-compiled bytecode consumers.

## 17. When to sort, when to leave as-is?

Not every requirement needs `sort()`. Categorize the purpose:

| Need | Appropriate choice | Avoid |
| --- | --- | --- |
| Preserve insertion order | `ArrayList`, `LinkedHashSet`, `LinkedHashMap` | `HashSet`/`HashMap` |
| Sort by key/value | `TreeMap`, `TreeSet`, `List.sort`, `Stream.sorted` | Trusting hash order |
| Prioritize next element | `PriorityQueue.poll` | Using priority queue's iterator expecting sorted output |
| Maintain workflow step order | `List` or model with sequence | Representing workflows as an unordered `Set` |
| Export deterministic report | Comparator with tie-breaker, explicit schema | Serializing `HashMap` in accidental order |
| Return unordered result set | `Set` with clear “unordered” contract | Writing snapshot tests locking down unpromised order |
| Parallel processing without order | `parallelStream`/`unordered` when matching contract | Still unconsciously using `findFirst()`/ordered side effects |
| Parallel processing requiring ordered output | Preserve encounter order or collect by index and reorder | Treating completion order as input order |

Replacing `HashMap` with `TreeMap` is not always a harmless “order fix”: a comparator might treat two keys distinct under `equals` as equivalent, causing data loss. Choose data structures based on key contracts, performance, and semantics.

## 18. Designing tests independent of accidental order

### 18.1. Testing the exact result contract

If an API returns a **set of elements**, tests should compare as sets:

~~~java
Set<String> expected = Set.of("reader", "writer");
Set<String> actual = permissionService.roles();

assertEquals(expected, actual);
~~~

If an API returns a **list with promised order**, tests should verify order:

~~~java
List<String> expected =
        List.of("validate", "charge", "notify");

assertEquals(expected, workflowService.steps());
~~~

Do not convert every test to `Set` comparison just to make it pass easily. If order is part of the contract, dropping order assertions hides regressions. Conversely, do not hardcode `HashSet` order in snapshots when the API does not promise order.

### 18.2. Testing properties instead of just one output

You can verify properties such as:

- Output contains the exact elements/results, with no extras or omissions.
- For ordered APIs, every pair of consecutive elements obeys the comparator.
- For pagination, no duplicate records appear within a defined snapshot.
- For grouping, elements belong to the right groups, regardless of map key order when order is not contracted.
- For side effects, callback order is checked if the API promises order; if not, check only real business conditions.

Example checking a list ordered by a comparator:

~~~java
for (int index = 1; index < actualOrders.size(); index++) {
    Order previous = actualOrders.get(index - 1);
    Order current = actualOrders.get(index);
    assertTrue(ordering.compare(previous, current) <= 0);
}
~~~

Tests need fixtures with duplicate primary sort keys, varied sizes/capacities, and edge cases. With only two elements or all keys unique on the first field, tests may fail to detect a missing tie-breaker.

### 18.3. Testing across multiple JDKs is not enough to “prove a guarantee”

Running the same test on JDK 17 and JDK 21 is helpful for catching regressions, yet if a behavior is not guaranteed by the API, observing identical behavior across two JDKs **creates no guarantee**.

Tests should be specification-based. If stable output is needed, establish determinism in code via explicit collections/ordering rather than relying on the test environment coincidentally producing repeatable output.

## 19. Investigation techniques when migration changes order

### 19.1. Tracing from the source through each transformation

When receiving a report that “newer Java changed the order”, ask:

1. Is the result produced from a `List`, `Set`, `Map`, `Stream`, SQL, or the filesystem?
2. Does the source have an ordering contract? If so, what is it?
3. Is there a `collect(toSet())`, `toMap`, `groupingBy`, `Map.copyOf`, or conversion to `HashMap`/`HashSet` step?
4. Was there a switch from sequential to parallel stream, or from `forEachOrdered` to `forEach`?
5. Are there a comparator/tie-breaker and null handling?
6. Is code generating JSON/logs from a map or reflection?
7. Does the consumer genuinely require order or is it only comparing text snapshots?
8. Did data volume, key distribution, DB query planner, or indexes change?

Instead of patching the end with an arbitrary `sort()`, identify **the first point where the ordering contract is lost**. If insertion-order is required, preserve order from the beginning; sorting alphabetically at the end cannot reconstruct that order.

### 19.2. Root-cause flowchart template

~~~mermaid
flowchart TD
    A[Output order changed] --> B{Does the API guarantee order?}
    B -->|Yes| C[Check source, comparator, transforms]
    B -->|No| D[Determine if consumer actually needs order]
    C --> E{Where is order lost?}
    E --> F[Fix at the exact transformation point]
    D --> G{Is there a business requirement for order?}
    G -->|Yes| H[Design explicit order via collection or sort]
    G -->|No| I[Update tests or consumer not to depend on order]
    F --> J[Contract tests and rollout]
    H --> J
    I --> J
~~~

The diagram does not replace per-API analysis; it helps distinguish genuine implementation bugs from cases where the application relied on unguaranteed behavior.

### 19.3. Minimal analysis log

A report should record:

~~~text
Observed behavior:
  report keys changed from [A, B, C] to [B, C, A]
Baseline:
  JDK 17 + framework vOld
Target:
  JDK 21 + framework vNew
Data source:
  HashMap<String, ReportEntry>
API contract:
  HashMap iteration order unspecified
Consumer assumption:
  CSV writer used map.entrySet() as output order
Decision:
  Define CSV sorting by reportOrder ASC, id ASC
Evidence:
  contract test on sorted output, integration test with duplicate reportOrder
~~~

The proper conclusion is not “the new HashMap is broken”; the conclusion is that the CSV writer lacks a sorting step matching the business contract. If customers actually require “entry order”, the fix must preserve insertion-order from the moment data is recorded rather than inventing a new sort.

## 20. Behavioral compatibility and library releases

When a library changes implementation while keeping public signatures, review whether consumers treat any behaviors as stable:

- Does the return value contain the same set of elements?
- Is any order promised in Javadoc or the API contract?
- Does order affect hash/cache key calculation, signatures, or serialization?
- Do side effects occur in the same order and expected count?
- Did it change from eager to lazy or sequential to concurrent?
- Was the result switched to an unmodifiable/snapshot wrapper?
- Were new default locale/timezone/platform dependencies introduced?

If order is guaranteed, switching from an ordered collection to an unordered collection without re-sorting is a behavioral change that must be treated as a regression/breaking change. If order is **not** guaranteed, the project should still document differences likely to affect consumers in the migration guide, especially when the ecosystem has long-lived clients.

### 20.1. When an API truly needs order, state it in the contract

API example:

~~~java
/**
 * Returns a snapshot of all matching orders sorted by
 * createdAt descending, then orderId ascending.
 * Never returns null.
 */
List<Order> findOrders(String customerId);
~~~

The Javadoc clearly states the criteria and tie-breaker. Consumers can legitimately rely on the order, and tests can guard the exact requirement. If an API only returns an unordered set, document that clearly as well:

~~~java
/**
 * Returns the matching roles. Iteration order is unspecified.
 */
Set<String> rolesFor(String userId);
~~~

For APIs with existing consumers, contract changes must be evaluated for source/binary/behavioral compatibility. For example, changing a return type from `Set<T>` to `List<T>` to promise order changes the method descriptor, impacting precompiled clients. Adding a new method like `rolesInDisplayOrder()` while keeping the old method can be a lower-risk path.

### 20.2. Do not turn implementation details into unnecessary promises

If business logic does not require order, do not promise “insertion-order” simply because a current version uses `LinkedHashMap`. Over-specifying details can restrict future optimizations.

A good contract should be strong enough for consumers to do their job properly, yet avoid locking the implementation into unnecessary characteristics.

## 21. Migration workflow to avoid relying on unguaranteed behaviors

### Step 1: Audit output generation points

List APIs emitting collections, streams, file listings, reflection metadata, query results, serialized text, and events. Identify consumer code paths relying on order by selecting first/last elements, using indices, or comparing text.

### Step 2: Read each API's contract

Cross-check Javadoc, Java specifications, and framework/dependency contracts. Classify into:

- Guaranteed order.
- Conditional order (ordered source, comparator, access-order).
- Unguaranteed order.
- Other unguaranteed behaviors, such as snapshots, timing, mutability, or execution threads.

### Step 3: Define explicit business rules

If insertion order is needed, use an order-preserving structure from the source. If sorting is needed, define a comparator and tie-breaker. If a snapshot is needed, build a snapshot with proper synchronization. If order is unnecessary, remove ordering assumptions in consumers and tests.

### Step 4: Separate implementation changes from contract changes

Do not bundle JDK/framework upgrades, collection changes, serialization changes, and sort criteria changes into one giant change when they can be separated. This helps pinpoint causes if behavior differs.

### Step 5: Test both behavior and migration

Run tests against written contracts with duplicate primary keys, element counts large enough to trigger resizing, null cases, and concurrent updates where relevant. Test on the target runtime, without using matching outputs as a substitute for API guarantees.

### Step 6: Communicate and deploy

Release notes must describe genuinely meaningful behavioral changes rather than merely saying “upgrade Java”. If previous JSON/CSV/protocol outputs relied on unpromised order that consumers nonetheless depended on, prepare a migration plan, coordinate downstream, and provide transition support where needed.

### Step 7: Monitor post-release

Observe message processing error counts, checksum/signature mismatches, CSV diffs, pagination failures, unstable reports, and data/collection exceptions. When regressions appear, investigate from source and contracts rather than assuming the new JVM is wrong.

## 22. Common misconceptions

**“It ran a thousand times with the same order, so Java guarantees the order.”** False. Observed stability does not replace Javadoc or the API specification.

**“HashMap always sorts by ascending hashCode.”** False. There is no such contract; do not build algorithms on internal bucket structures.

**“Map.of returns keys from its iterator in the exact order written.”** False. `Map.of` does not promise iteration order.

**“Copying a HashMap into a LinkedHashMap recovers insertion order.”** False. You only copy the source's iteration order at copy time.

**“PriorityQueue is a sorted collection, so its iterator is sorted.”** False. `poll()` and `iterator()` have different contracts.

**“When using parallelStream, `forEach` still follows list order.”** False. Distinguish encounter order from execution order; use `forEachOrdered` when the contract requires it.

**“Because `sorted()` was called, equal elements have a deterministic order.”** Not necessarily. Check encounter order, stability, and the comparator's tie-breaker.

**“Files.list was sorted by name on my Linux machine.”** That is not a guarantee of `Files.list`; sort explicitly if needed.

**“Reflection returns methods in declaration order.”** There is no such guarantee for common member-listing reflection APIs.

**“ResultSet always follows primary key because the table has an index.”** SQL does not promise row order without `ORDER BY`.

**“JSON object key order is part of business data.”** Do not treat it as a general contract; if signing or hashing, apply appropriate canonicalization.

**“Switching to `TreeMap` is always safe.”** A comparator can alter key equality semantics and inadvertently drop entries.

**“A ConcurrentHashMap iterator sees complete point-in-time data.”** A weakly consistent iterator is not an atomic snapshot.

**“Tested on two JDK versions, so that order is guaranteed.”** Tests prove what happened during those test runs; they do not create new API contracts.

## 23. Checklist for changes involving ordering and default behavior

- [ ] Identified which ordering is an actual business requirement.
- [ ] Read the contract of the data source and container/collection used for iteration.
- [ ] Not relying on `HashMap`/`HashSet`/`Map.of`/`Set.of` when insertion/sorted order is needed.
- [ ] If using `LinkedHashMap`, clarified insertion-order vs. access-order.
- [ ] If using `TreeMap`/`TreeSet`, checked whether the comparator makes two valid keys count as duplicates.
- [ ] If using `PriorityQueue`, not treating iteration order as priority order.
- [ ] If using Stream, identified encounter order and distinguished `forEach` from `forEachOrdered`.
- [ ] If collecting into a Set/Map, specified a collection factory when order is needed.
- [ ] If sorting, defined an appropriate comparator, null policy, and tie-breaker.
- [ ] If using concurrent collections, defined snapshot/weak consistency and concurrency policy.
- [ ] If using `Files.list`/reflection/SQL, sorted explicitly when deterministic output is required.
- [ ] If serializing JSON/CSV, specified genuinely required ordering and canonicalization when signing/hashing.
- [ ] If using locale/timezone/charset, configured defaults that affect business logic.
- [ ] Tests verify the actual contract rather than locking in accidental order.
- [ ] Consumer inventory includes downstreams relying on output order.
- [ ] Release notes distinguish guaranteed behaviors from previously unspecified behaviors that changed.
- [ ] Rollout monitors pagination errors, serialization, signatures, and business outcomes.

## 24. Comprehensive scenario: upgrading JDK and changing a reporting framework

Suppose a service fetches orders from a database, groups them by status, and exports CSV. Before migration:

~~~java
Map<String, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(Order::status));

for (Map.Entry<String, List<Order>> group : grouped.entrySet()) {
    writeCsvSection(group.getKey(), group.getValue());
}
~~~

The team used to see the `NEW`, `PAID`, `SHIPPED` sections exported in that exact order. After upgrading the JDK/framework, the report changed to `PAID`, `SHIPPED`, `NEW`. The code compiles cleanly and all data is still present.

### 24.1. Root-cause analysis

`groupingBy` creates a map without promising the iteration order of groups. If the `orders` source was also queried via SQL without `ORDER BY`, that adds another layer of unguaranteed order. Thus, the old output was accidental behavior.

### 24.2. Redesigning the contract

If business logic wants a fixed status order, represent that order directly:

~~~java
List<String> sectionOrder =
        List.of("NEW", "PAID", "SHIPPED");

Map<String, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(Order::status));

for (String status : sectionOrder) {
    List<Order> group = grouped.getOrDefault(status, List.of());
    writeCsvSection(status, group);
}
~~~

If orders within each group must follow creation time then ID:

~~~java
Comparator<Order> orderWithinSection =
        Comparator.comparing(Order::createdAt)
                .thenComparing(Order::id);

for (String status : sectionOrder) {
    List<Order> sortedGroup = grouped.getOrDefault(
                    status, List.of())
            .stream()
            .sorted(orderWithinSection)
            .toList();
    writeCsvSection(status, sortedGroup);
}
~~~

The result no longer depends on map or SQL iteration order. If a new status appears outside `sectionOrder`, define a handling contract: reject, place in an “other” section, or extend configuration. Never silently drop data outside known statuses.

### 24.3. Testing after conversion

Tests should intentionally shuffle input order, create multiple orders with the same `createdAt`, and verify:

- Sections are exported in `sectionOrder` order.
- Each section contains the exact orders belonging to that status.
- Orders within each section are sorted by `createdAt` then `id`.
- Unlisted statuses follow the specified handling path.
- The CSV does not depend on the order returned by `HashMap` or the database.

Takeaway from this scenario: the migration **exposed an assumption not guaranteed by the API**. The right fix is turning order into an explicit contract, rather than trying to artificially recreate the old iteration order.

## 25. Conclusion

Iteration order is a classic example of the boundary between **guaranteed behavior** and **accidental implementation behavior**. `List`, `LinkedHashMap`, or `TreeMap` have their own ordering contracts; `HashMap`, `HashSet`, `Map.of`, `Set.of`, and many other APIs make no such promise. Streams further distinguish encounter order from execution order; concurrency, the filesystem, reflection, databases, and serialization add other sources of indeterminacy.

In Java Advance Compatibility Migration, do not treat every output change as a bug in the new JDK, yet do not assume that “not guaranteed” means users are unaffected. Locate where consumers rely on implicit order or behavior, decide the true business requirement, and express it through explicit collections, comparators, schemas, queries, or API contracts. Test against contracts rather than an accidental output; version upgrades will then depend far less on details outside the application's control.
