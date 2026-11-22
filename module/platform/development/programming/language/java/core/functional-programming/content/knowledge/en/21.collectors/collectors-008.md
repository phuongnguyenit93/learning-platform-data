# Duplicate Keys, Merge Functions, and Choosing Map Types When Collecting Streams

## 1. Real-world problem: multiple elements can produce the same key

When collecting results from a Stream into a `Map<K,V>`, we often use `Collectors.toMap()`. Each source element is transformed into a **key** and a **value**:

```text
Person(name="An",  team="A", score=10) → key="A", value=10
Person(name="Binh",team="B", score=20) → key="B", value=20
Person(name="Chi", team="A", score=15) → key="A", value=15
                                           ↑ duplicate key "A"
```

Two objects with the same key `"A"` raise a business question: keep `10`, keep `15`, sum to `25`, group into a list, or throw an error?

**There is no default policy that is right for every problem.** Two-argument `Collectors.toMap(keyMapper, valueMapper)` **throws an `IllegalStateException` when a duplicate key occurs**. That is a way to detect collisions, not an automatic choice to keep the first or last record.

This topic guides you through three separate decisions to make before collecting:

1. **How is the key determined?** Which records are considered to have the same key?
2. **When a key is duplicated, what should happen?** Throw an error, pick a value, accumulate a sum, combine, or keep all?
3. **What properties does the resulting Map need?** Unconcerned with order, preserving insertion order, sorted by key, optimized for enum keys, or supporting concurrent operations?

Do not pick a merge function just to "make the code stop throwing errors" without answering the actual business rule.

## 2. Overloads of Collectors.toMap()

Key API forms in Java 17:

```java
Collectors.toMap(keyMapper, valueMapper)

Collectors.toMap(keyMapper, valueMapper, mergeFunction)

Collectors.toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
```

These are **abbreviated signatures for readability**; in real Java code, `keyMapper`, `valueMapper`, `mergeFunction`, and `mapFactory` must be expressions/interfaces with appropriate generic types.

| Form | Duplicate keys | Concrete Map type |
| --- | --- | --- |
| Two arguments | Throws `IllegalStateException` | Specific implementation **not guaranteed by the API** |
| Three arguments | Uses `BinaryOperator<U>` to combine two values | Specific implementation **not guaranteed by the API** |
| Four arguments | Uses merge function | Obtained from the `Supplier<M>` you pass, e.g. `LinkedHashMap::new`, `TreeMap::new` |

When using two arguments, `keyMapper` selects the key and `valueMapper` selects the value. Even if two elements produce the same key and **the same value**, it is still a duplicate key; the collector does not automatically treat that as valid.

**Distinguishing collector from Stream:** `toMap` is a collector passed to the terminal operation `collect(...)`. After collecting, the Stream is consumed and cannot be reused. To test a different merge policy, create a new stream from the same source such as `list.stream()`.

## 3. Two arguments: duplicate keys cause IllegalStateException

Short example:

```java
record Person(String name, String team, int score) {}
List<Person> people = List.of(
        new Person("An", "A", 10),
        new Person("Chi", "A", 15));
Map<String, String> byTeam = people.stream()
        .collect(Collectors.toMap(Person::team, Person::name));
```

This snippet **intentionally causes a runtime exception** (place the declarations in an appropriate class/method context and import `List`, `Map`, `Collectors`). Both `Person` instances have the same key `"A"`, so collection will throw `IllegalStateException`. The complete program in section 8 catches the exception so execution can continue.

If the system requires **every identifier to be unique**, this fail-fast behavior is very appropriate: it helps detect bad data instead of silently overwriting. For example, building a `userId → user` map where `userId` must be unique is a place where you should not arbitrarily pick the first or last element.

**Do not confuse with Map.put:** a regular `map.put(key, value)` replaces the value associated with an existing key. However, two-argument `Collectors.toMap(k,v)` has a **fail-on-duplicate** policy; it does not perform an overwriting `put` as beginners often expect.

## 4. Merge function: resolving conflicts according to business rules

The three- or four-argument form accepts a **merge function** applied to two values with the same key:

```java
Map<String, Integer> totals = people.stream()
        .collect(Collectors.toMap(
                Person::team,
                Person::score,
                Integer::sum));
```

These statements illustrate using `people` and the `Person` record from section 3, though a list with more elements like in the main program can be used. For team `"A"`, `10 + 15 = 25`; team `"B"` might have `20 + 7 = 27`.

`Integer::sum` is computationally equivalent to `(a,b) -> a+b`. The two parameters `a`, `b` are the **mapped values**, not the two original `Person` objects. If you need a name, order ID, timestamp, or another attribute to choose a record, design `valueMapper` to produce an object containing enough information and write an appropriate merge policy.

Common policies:

| Policy | Merge function | Result when encountering old value A, new value B |
| --- | --- | --- |
| Keep existing value | `(oldValue, newValue) -> oldValue` | A |
| Use incoming value | `(oldValue, newValue) -> newValue` | B |
| Sum scores / counts | `Integer::sum` or `Long::sum` | A + B |
| Pick larger number | `Integer::max` | max(A,B) |
| Concatenate descriptions | `(a,b) -> a + "+" + b` | Combined string |
| Combine objects | `(a,b) -> combine(a,b)` | According to the `combine` contract defined by the application |

The expressions in the table are patterns for **compatible types** and not standalone programs. `Integer::sum` only works when the merged values are compatible with `Integer`; `String` requires a different merge function.

**Keep first / keep last are easily misunderstood concepts in parallel and unordered streams.** With a list that has an encounter order, a sequential stream, and the illustrative collection operation, the `oldValue`/`newValue` patterns yield clear results. However, in problems that need to pick the "latest by time" record, **compare the timestamp field directly** rather than assuming the element arriving later in the execution structure is the newest.

## 5. Contract of the merge function: associative, pure, and deterministic

During collection, especially with **parallel streams**, partial maps may be accumulated separately and then **combined**. The merge function must fit how the reducer/collector groups values.

**Associativity:**

```text
merge(merge(a,b),c) == merge(a,merge(b,c))
```

For `Integer::sum` without overflow, integer addition is associative. `Integer::max` is also associative. Conversely, `(a,b) -> a-b` is generally **not associative**, so the result can depend on how elements are grouped. In particular, with `double`, floating-point addition has rounding errors and is not strictly associative in representation, which should be considered when financial or high-precision results matter.

In addition, a merge function should:

- **Have no side effects** such as writing to a database, processing payments, or mutating shared state. How often and when the function is called depends on collisions, execution plans, and how sub-maps are merged.
- **Not rely on invocation count** for business statistics. The collector is allowed to split work and merge according to its implementation structure.
- **Not corrupt input values** if mutable value objects are shared.
- Have clear rules for anomalous data, duplicate records, equal values, and ordering requirements.

Not every merge needs to be **commutative** (`merge(a,b)==merge(b,a)`) to be semantically usable, but if it is not commutative, order can become an important part of the contract. When results must be independent of processing order, prefer a merge operation that is both associative and commutative, or establish a clear order before collecting.

## 6. Choosing a Map type: iteration order and key equality

The Map API does not guarantee ordering by default for all implementations. Choose a Map type based on actual requirements, not just because a single printout "looks right".

| Map Type | Key Characteristics | When to Choose |
| --- | --- | --- |
| `HashMap<K,V>` | No iteration order guarantee, fast average lookup | When **order does not matter** |
| `LinkedHashMap<K,V>` | Preserves insertion order by default | When you want to **iterate in insertion order** after collecting |
| `TreeMap<K,V>` | Sorts keys by natural ordering or `Comparator` | When you want a **map sorted by key** |
| `EnumMap<E,V>` | Keys belong to the same enum type, ordered by enum declaration order | When keys are a fixed enum |
| `ConcurrentHashMap<K,V>` | Supports concurrent access/updates | When you **genuinely need** a concurrently updated map, not merely because a stream runs in parallel |

The four-argument form lets you choose the Map:

```java
Map<String, Integer> byTeam = people.stream()
        .collect(Collectors.toMap(
                Person::team,
                Person::score,
                Integer::sum,
                LinkedHashMap::new));
```

This needs to be placed inside a method with imports for `Map`, `LinkedHashMap`, `Collectors`, and the `Person` class. `LinkedHashMap::new` is the **map factory**. If you want sorting by key: replace it with `TreeMap::new`. If you do not care about the concrete type, you can use the three-argument overload; the API does not promise the default map is always `HashMap`, even if an implementation often returns that type.

**Important with LinkedHashMap:** it preserves **map insertion order**, and does not turn duplicate keys into multiple entries. When key `"A"` is encountered a second time and values are merged, `"A"`'s entry does not automatically move to a new position at the end under default insertion-order mode. To store **all** records for key `"A"`, you must use a list of values or another structure.

## 7. Choosing TreeMap: key ordering and comparators can change "duplicate keys"

`TreeMap` distinguishes keys using a **comparator/natural ordering**. Two keys `a`, `b` are considered equivalent in a `TreeMap` when `compare(a,b) == 0`, even if `a.equals(b)` is `false`.

Example:

```java
Map<String, Integer> caseInsensitive =
        List.of("java", "Java").stream()
            .collect(Collectors.toMap(
                s -> s,
                String::length,
                Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
```

These statements belong in a method with imports for `Map`, `List`, `TreeMap`, `Collectors`. Under `String.CASE_INSENSITIVE_ORDER`, `"java"` and `"Java"` have a comparator result of `0`, so they are **the same key to TreeMap**. The result has only one entry `{java=8}` in the Java 17 run of the demo program.

In contrast, `new TreeMap<>()` with natural ordering is case-sensitive; those two keys can exist separately. Therefore, **the definition of a duplicate key lies not only in `keyMapper`, but also in the Map's key comparison rule**.

When using a comparator that is inconsistent with `equals`, `TreeMap` behavior still follows the comparator for key lookups, which may differ from intuition about `Map`/set equality. Document the comparator choice, especially if data is exchanged with a `HashMap` or JSON.

## 8. Complete Java 17 program: duplicate keys and merge policies

Save the entire following content to `ToMapDuplicateKeysDemo.java`:

```java
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

public class ToMapDuplicateKeysDemo {
    record Person(String name, String team, int score) {}
    public static void main(String[] args) {
        List<Person> people = List.of(
            new Person("An", "A", 10),
            new Person("Binh", "B", 20),
            new Person("Chi", "A", 15),
            new Person("Dung", "B", 7));
        try {
            people.stream().collect(Collectors.toMap(Person::team, Person::name));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate=" + ex.getClass().getSimpleName());
        }

        Map<String, Integer> totals = people.stream()
            .collect(Collectors.toMap(Person::team, Person::score, Integer::sum));
        System.out.println("totalsA=" + totals.get("A"));
        System.out.println("totalsB=" + totals.get("B"));

        Map<String, String> first = people.stream()
            .collect(Collectors.toMap(Person::team, Person::name,
                (oldValue, newValue) -> oldValue, LinkedHashMap::new));
        System.out.println("first=" + first);

        Map<String, String> last = people.stream()
            .collect(Collectors.toMap(Person::team, Person::name,
                (oldValue, newValue) -> newValue, LinkedHashMap::new));
        System.out.println("last=" + last);

        Map<String, String> merged = people.stream()
            .collect(Collectors.toMap(Person::team, Person::name,
                (a,b) -> a + "+" + b, TreeMap::new));
        System.out.println("mergedTree=" + merged);

        Map<String, List<String>> groups = people.stream()
            .collect(Collectors.groupingBy(Person::team,
                TreeMap::new, Collectors.mapping(Person::name, Collectors.toList())));
        System.out.println("groups=" + groups);

        Map<String, String> immutable = people.stream()
            .collect(Collectors.toUnmodifiableMap(Person::name, Person::team));
        System.out.println("immutableSize=" + immutable.size());
        try {
            immutable.put("New", "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=" + ex.getClass().getSimpleName());
        }

        Map<String, Integer> parallelTotals = people.parallelStream()
            .collect(Collectors.toMap(Person::team, Person::score,
                Integer::sum, TreeMap::new));
        System.out.println("parallelTotals=" + parallelTotals);

        Map<String, Integer> naturalSorted = people.stream().collect(
            Collectors.toMap(Person::name, Person::score,
                (a,b) -> a, TreeMap::new));
        System.out.println("naturalKeys=" + naturalSorted.keySet());

        Map<String, Integer> linkedOrder = people.stream().collect(
            Collectors.toMap(Person::name, Person::score,
                (a,b) -> a, LinkedHashMap::new));
        System.out.println("linkedKeys=" + linkedOrder.keySet());
    }
}
```

Run with JDK 17:

```bash
javac --release 17 -encoding UTF-8 ToMapDuplicateKeysDemo.java
java ToMapDuplicateKeysDemo
```

Verified output:

```text
duplicate=IllegalStateException
totalsA=25
totalsB=27
first={A=An, B=Binh}
last={A=Chi, B=Dung}
mergedTree={A=An+Chi, B=Binh+Dung}
groups={A=[An, Chi], B=[Binh, Dung]}
immutableSize=4
unmodifiable=UnsupportedOperationException
parallelTotals={A=25, B=27}
naturalKeys=[An, Binh, Chi, Dung]
linkedKeys=[An, Binh, Chi, Dung]
```

Output explanation:

1. **`duplicate=IllegalStateException`:** the two-argument overload rejects two people on the same team.
2. **`totalsA=25`, `totalsB=27`:** sums scores using `Integer::sum` grouped by team key.
3. **`first` and `last`:** two different merge functions. Because the input is a `List` with encounter order and a sequential pipeline, `first` keeps the first person's name appearing for each team, and `last` keeps the later person's name.
4. **`mergedTree`:** concatenates names into a string and uses `TreeMap` to print team keys in sorted order.
5. **`groups`:** when you want to **keep all names** in each team, `groupingBy` + `mapping` to a list is more appropriate.
6. **`immutableSize=4`:** `toUnmodifiableMap` when keys are distinct names creates an unmodifiable map; attempting `put` throws `UnsupportedOperationException`.
7. **`parallelTotals`:** summing scores produces totals per team when collected in parallel; the resulting Map chosen is `TreeMap`.
8. **`naturalKeys` and `linkedKeys`:** on this dataset they look identical, but for different reasons: `TreeMap` sorts keys alphabetically, while `LinkedHashMap` preserves insertion order. **Do not infer that the two Map types share the same ordering contract.**

The program intentionally **catches the duplicate key error to continue the demonstration**. In an application where keys must be unique, treat that exception as a data error to be resolved, rather than catching and ignoring it by default.

## 9. When to use groupingBy() instead of toMap()?

If one key corresponds to **multiple values** and you need to keep every record, writing a custom merge function to concatenate lists can be cumbersome, especially in parallel streams. In that case, `Collectors.groupingBy` usually expresses intent more clearly:

```java
Map<String, List<String>> peopleByTeam = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                TreeMap::new,
                Collectors.mapping(Person::name, Collectors.toList())));
```

These are illustrative statements inside a method with the `Person` record and imports for `Map`, `List`, `TreeMap`, `Collectors`. Result on the main program's data: `{A=[An, Chi], B=[Binh, Dung]}`.

Choose an approach based on the **target data structure**:

| Goal | Recommended Collector |
| --- | --- |
| Each key must be unique; duplicates are errors | `toMap(key, value)` |
| Each key takes one value via a selection policy | `toMap(key, value, merge)` |
| Each key has a total count/score | `toMap(key, number, Integer::sum)` or `groupingBy(key, summingInt(...))` |
| Each key has a list of values | `groupingBy(key, mapping(value, toList()))` |
| Want sorting by key | Pass `TreeMap::new` to a collector with `mapFactory` |
| Want an immutable Map with unique keys | `toUnmodifiableMap(key, value)` |

`groupingBy` is not a way to "automatically deduplicate". It **groups all elements** by key; the number of elements in each `List` can be greater than one. If you only need a sum, using a direct reducer can avoid creating unnecessary `List`s.

## 10. EnumMap and enum keys

When the key is an enum, `EnumMap` can provide specialized storage and iteration order following the **declaration order of the enum constants**:

```java
enum Level { LOW, MEDIUM, HIGH }

EnumMap<Level, Integer> levels = tickets.stream()
    .collect(Collectors.toMap(
        Ticket::level, Ticket::points, Integer::sum,
        () -> new EnumMap<>(Level.class)));
```

These illustrative lines must be inside a class with the `Level` enum, an appropriate `Ticket` record, and imports for `EnumMap`, `Collectors`. The full example in section 11 defines these types. Specifying `Level.class` to the factory makes clear which enum type the Map uses.

Do not choose `EnumMap` for a `String` or `Integer` key; keys must belong to the appropriate enum type. `EnumMap` does not accept a **null key**. If business logic has an undetermined key case, handle it before collecting rather than relying on incidental behavior.

## 11. Complete Java 17 example: EnumMap, comparator, null merge, and groupingBy

Create the file `MapTypeChoiceDemo.java`:

```java
import java.util.*;
import java.util.stream.Collectors;

public class MapTypeChoiceDemo {
    enum Level { LOW, MEDIUM, HIGH }
    record Ticket(Level level, int points) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
            new Ticket(Level.LOW, 3),
            new Ticket(Level.HIGH, 7),
            new Ticket(Level.LOW, 4));

        EnumMap<Level, Integer> levels = tickets.stream()
            .collect(Collectors.toMap(Ticket::level, Ticket::points,
                Integer::sum, () -> new EnumMap<>(Level.class)));
        System.out.println("enumMap=" + levels);
        System.out.println("enumType=" + (levels instanceof EnumMap));

        Map<String, Integer> caseSensitive = List.of("java","Java").stream()
            .collect(Collectors.toMap(s -> s, String::length,
                (a,b)->a, TreeMap::new));
        System.out.println("caseSensitiveSize=" + caseSensitive.size());

        Map<String, Integer> caseInsensitive = List.of("java","Java").stream()
            .collect(Collectors.toMap(s -> s, String::length,
                Integer::sum, () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
        System.out.println("caseInsensitive=" + caseInsensitive);

        Map<String, Integer> mergedNull = List.of("x", "x").stream()
            .collect(Collectors.toMap(s -> s, s -> 1,
                (a,b) -> null, LinkedHashMap::new));
        System.out.println("nullMergeRemoves=" + mergedNull);

        Map<String, List<Integer>> multiValue = List.of(1,2,3,4).stream()
            .collect(Collectors.groupingBy(n -> n % 2 == 0 ? "even":"odd",
                LinkedHashMap::new, Collectors.toList()));
        System.out.println("multiValue=" + multiValue);

        System.out.println("type=" + levels.getClass().getSimpleName());
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 MapTypeChoiceDemo.java
java MapTypeChoiceDemo
```

Verified output:

```text
enumMap={LOW=7, HIGH=7}
enumType=true
caseSensitiveSize=2
caseInsensitive={java=8}
nullMergeRemoves={}
multiValue={odd=[1, 3], even=[2, 4]}
type=EnumMap
```

Highlights:

- Two tickets with key `LOW` have their points summed `3+4=7`; ticket `HIGH` has `7`; `EnumMap` iterates in declaration order `LOW, MEDIUM, HIGH` (key `MEDIUM` is absent so it is not printed).
- Natural `TreeMap` treats `java` and `Java` as two distinct keys; the case-insensitive comparator makes them **duplicate keys** and sums them to `8`.
- A merge function returning `null` causes the mapping to be **removed** according to `Map.merge` semantics. With two `"x"` keys and `(a,b) -> null`, an empty map is produced. This is a property to know to avoid bugs, **not recommended for use as an implicit deletion rule**.
- `groupingBy` with `LinkedHashMap::new` demonstrates preserving the `odd`, `even` group lists in a sequential example.

An easily overlooked counterexample: if three consecutive records share the same key and the merge returns `null` on the second collision, the third record can recreate a new mapping. Therefore, `(a,b)->null` is **not** a mechanism to "permanently delete all duplicate keys".

## 12. Null key, null value, and null merge result

Three different matters:

1. **Key `null`:** whether it is supported depends on the concrete Map and collector; `HashMap` accepts a null key, whereas `TreeMap` with natural ordering generally does not and `EnumMap` does not. Collectors may also impose other constraints. Do not rely on a `null` key unless the contract is clearly established.
2. **Value `null` from `valueMapper`:** `Collectors.toMap` implementations that use merge/check mechanisms can throw `NullPointerException`; `toUnmodifiableMap` **forbids null keys/values** by contract. If a value may be absent, `filter` it out or use a non-null representation such as an appropriate `Optional`/record.
3. **Return value `null` from the merge function:** according to `Map.merge`, when the remapping function returns `null`, the existing mapping **is removed**, which is different from storing `null` as the map value.

You can see these three concepts are distinct even when the debugger output shows the word "null" in all of them. To make intent clear, check for null at data transformation boundaries and avoid side effects.

A better approach when a team code is missing: decide that team code is required and fail-fast with validation; or filter out records without a code; or assign a meaningful non-null placeholder code. Do not assume a null key is a safe "other" group across all implementations.

## 13. toUnmodifiableMap() and immutability requirements

Since Java 10, `Collectors.toUnmodifiableMap` creates a Map that does not support modification operations:

```java
Map<String, Integer> scores = people.stream()
        .collect(Collectors.toUnmodifiableMap(
                Person::name, Person::score));
```

These are illustrative statements inside a method with appropriate `people` and `Person`. When names are unique, the collector returns an unmodifiable map; `scores.put("New", 42)` will throw `UnsupportedOperationException`.

Points to remember:

- The two-argument version of `toUnmodifiableMap` still **fails on duplicate keys**.
- The three-argument version can accept a merge function to handle duplicate keys.
- `toUnmodifiableMap` **does not accept null keys/values**.
- Do not assume a specific iteration order for the result.
- Structural immutability of the Map **does not make mutable value objects immutable**; if `V` is a mutable object, the object itself can still be modified through another reference.

`Map.copyOf(map)` also creates an unmodifiable Map from an existing map with null restrictions; however, choosing the collector early is usually clearer if you want an immutable result immediately after `collect`.

## 14. Parallel streams, combiners, and ConcurrentMap

When calling:

```java
Map<String, Integer> totals = people.parallelStream()
        .collect(Collectors.toMap(
                Person::team,
                Person::score,
                Integer::sum,
                TreeMap::new));
```

In the context of the complete example, the result `{A=25, B=27}` has been verified. `Integer::sum` is convenient because it is associative and order-independent for small numbers that do not cause overflow issues.

**However, `parallelStream()` does not automatically turn the target map into a concurrently updated Map.** The regular `toMap` collector is a **non-concurrent** collector; the framework may create local maps and then combine them via the combiner. This can be expensive when there are many keys, because intermediate maps have to be merged.

If you truly want a concurrent collector, Java provides `Collectors.toConcurrentMap`. It produces a `ConcurrentMap` by contract, typically used with pipelines that can process in parallel, but **does not guarantee insertion order** by encounter order like `LinkedHashMap`.

Notes:

- Do not arbitrarily switch `toMap` to `toConcurrentMap` if business logic requires "keeping the first/last value" by order of appearance.
- The merge function must still obey the proper contract and avoid side effects.
- `ConcurrentHashMap` does not accept null keys/values; choose the Map type according to real constraints.
- A thread-safe Map does not make steps **outside the Map** (sending emails, DB calls, computing mutable shared state) thread-safe or exactly-once.
- Do not default to parallel for speed: for small datasets, few keys, and high merge cost, sequential execution can be more efficient.

## 15. Understanding Map iteration order properly

There are three different concepts that are easy to mix up:

1. **Stream encounter order**: the order of source elements determined by the pipeline.
2. **LinkedHashMap insertion order**: the order in which a key is first added to the map under default mode.
3. **TreeMap key order**: determined by comparator/natural ordering, not by the order of appearance in the stream.

For example, with sequential source `["B", "A", "C"]`: putting into `LinkedHashMap` typically gives key order `B, A, C`; putting into `TreeMap` with natural ordering gives `A, B, C`. `HashMap` promises no order at all, even if one run happens to match insertion order by coincidence.

When you need to *both* pick the latest record *and* maintain key order, separate the two decisions: the merge function selects by `timestamp` (or a criterion with a total ordering), while the map factory determines the iteration order of the resulting map. Do not use `newValue` as a synonym for "latest".

An ordered Map does not automatically guarantee that **values for each key are merged in the desired order** under other execution modes. If you concatenate strings or lists in order, verify whether encounter order and your collector/parallel choice are appropriate.

## 16. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `toMap(key,value)` when keys are not actually unique | `IllegalStateException` | Define a merge function or use `groupingBy` |
| Thinking `toMap` defaults to "keep the last element" | Not true for the two-argument overload | Specify the policy explicitly |
| Using `(a,b)->b` to pick the latest record | Ignores actual timestamp/priority | Compare business fields |
| Using a merge function with side effects | Call count/order depends on pipeline | Use a pure, contract-compliant merge function |
| Using subtraction as merge in parallel | Depends on grouping | Choose an associative merge operation |
| Thinking `HashMap` preserves input order | No iteration order guarantee | Use `LinkedHashMap` if insertion order is needed |
| Thinking `TreeMap` only treats keys as duplicates via `equals()` | Comparator determines key equivalence | Check `compare(a,b)==0` |
| Returning `null` from merge to "keep null" | `Map.merge` can **remove the mapping** | Return a non-null result, handle removal explicitly |
| Expecting `toMap` to support null values everywhere | Can throw `NullPointerException` | Sanitize data beforehand |
| Using `EnumMap` with non-enum keys | Incompatible key type | Choose an appropriate Map or change the key model |
| Thinking `toUnmodifiableMap` makes mutable values immutable | Only protects Map structure | Use immutable value types or defensive copies |
| Using `toConcurrentMap` while still relying on order | Concurrent collector does not preserve insertion order | Design ordering separately, avoid depending on concurrent order |

## 17. Practice exercises with answers

**Exercise 1 — Recognizing duplicate keys.** Given two people `("An","A")` and `("Chi","A")`, is `toMap(Person::team,Person::name)` valid at runtime?

Answer: **No**, because both keys are `"A"`. The two-argument overload throws `IllegalStateException`.

**Exercise 2 — Summing.** Scores by team are: `A:10`, `B:20`, `A:15`. Write a merge function so the Map has `A=25`, `B=20`.

Answer: `Integer::sum` with `toMap(Person::team,Person::score,Integer::sum)` if the input is `Person` as in the program.

**Exercise 3 — Choosing key order.** You need key iteration order to be alphabetical, not by order of appearance. Which map factory do you choose?

Answer: `TreeMap::new` with `String` keys and natural ordering. If case-insensitive sorting is needed, pass a factory creating `TreeMap<>(String.CASE_INSENSITIVE_ORDER)`, while understanding it may treat some keys as duplicates.

**Exercise 4 — Preserving insertion order.** You need to iterate keys in the order they were first added in a sequential pipeline. Which Map type do you choose?

Answer: `LinkedHashMap::new`, with default insertion-order. Duplicate keys replace/merge the value without creating a second entry.

**Exercise 5 — Keeping all elements.** For team `A` with two people, why is `groupingBy(Person::team, mapping(Person::name,toList()))` better suited than `toMap(...,(old,new)->old)`?

Answer: `groupingBy` keeps **both names**; a keep-first merge only yields one person and loses the other record's information.

**Exercise 6 — Comparator.** Can `"java"` and `"Java"` become duplicate keys in a TreeMap?

Answer: **Yes**, if using `String.CASE_INSENSITIVE_ORDER`. `TreeMap` uses a comparator result of `0` to treat two keys as equivalent.

**Exercise 7 — Merge returning null.** With `toMap(s->s,s->1,(a,b)->null,LinkedHashMap::new)` on two `"x"` strings, what is the result?

Answer: An empty map `{}` in the test program, because the merge returning `null` causes the existing entry to be removed. Do not use this if you only want to "keep a null value".

**Exercise 8 — Parallel.** Is a merge function `(a,b)->a-b` suitable for stable parallel aggregation?

Answer: **No**, in the sense of a reduction needing results independent of grouping, because subtraction is not associative. Choose an appropriate merge operation or switch to a different collector design.

**Exercise 9 — Enum.** Your key is the `Level` enum and you need a Map optimized for enums, iterating in declaration order. What do you choose?

Answer: `EnumMap<Level,V>`, passing the factory `() -> new EnumMap<>(Level.class)` to the four-argument overload.

## 18. Checklist before going to production

1. Verify key **uniqueness**; if duplicates indicate bad data, use the overload without merge to fail-fast.
2. If duplicates are valid, write out the **business merge policy**; it receives two **mapped values**, not two original source elements.
3. Determine whether you need to **keep all values**; if so, consider `groupingBy` + a downstream collector.
4. Determine the **Map implementation**: `HashMap` when order is not needed, `LinkedHashMap` when insertion order is needed, `TreeMap` when key order is needed, `EnumMap` for enums.
5. Check the **comparator**: when comparison returns 0, `TreeMap` treats keys as equivalent, even if `equals` differs.
6. Handle **null keys/values** and avoid letting merge accidentally return null and delete mappings.
7. If running in **parallel**, verify associativity, side effects, ordering, and combiner cost.
8. If result immutability is needed, consider `toUnmodifiableMap`/immutable value objects and understand the null contract.
9. Test at least: **no duplicates**, **two duplicate keys**, **three duplicate keys**, **duplicates with equal values**, **duplicates due to comparator**, **insertion order vs sorted order**, and **parallel** where applicable.

## 19. Key takeaways

- `Collectors.toMap(keyMapper,valueMapper)` **throws IllegalStateException** on duplicate keys; it does not automatically pick the first or last value.
- The three/four-argument overloads accept a **merge function** to define how to merge; that function should be pure, associative, and fit parallel processing needs.
- `LinkedHashMap` preserves **insertion order**, `TreeMap` sorts by **key**, and `EnumMap` suits **enum keys**; the default overload does not guarantee a specific implementation.
- `TreeMap` determines key equivalence via comparator, which can **create new collisions**.
- `groupingBy` is the natural choice when you need **one key → multiple values**; it does not lose data by picking only the first or last.
- A merge function returning `null` can **remove the mapping**; do not do so without a clear rule.
- `toUnmodifiableMap` protects the Map structure, does not automatically make value objects immutable, and does not accept null keys/values.
- When processing concurrently/in parallel, do not trade away correctness of ordering or value selection rules just for speed.

Official documentation: [Java SE 17 Collectors.toMap/toUnmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html), [Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)), [LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html).