# Null Element Policies and Per-Implementation Type Restrictions

## 1. A Value Can Have the Right Type Yet Still Be Rejected

Consider two collections that both hold strings:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> names = new ArrayList<>();
Deque<String> jobs = new ArrayDeque<>();

names.add(null); // Allowed.
// jobs.add(null); // Compiles, but throws NullPointerException at runtime.
```

Both calls are type-valid at compile time. The difference lies in the contract of the actual object: `ArrayList` allows `null` elements, whereas `ArrayDeque` does not.

When working with collections, there are three layers of questions:

1. **What does the declared type allow passing?** For example, `List<String>` does not allow adding an `Integer` through a normal type-checked call.
2. **What values does the implementation accept?** For example, `null` may be prohibited.
3. **What additional conditions does the structure require?** For example, elements must be mutually comparable to be stored in an ordered tree.

The `null` policy and type restrictions belong to the **contract of the implementation or factory/wrapper**, not merely to the interface name `List`, `Set`, or `Map`.

This lesson uses APIs available in Java 17. The goal is to know what to check before swapping data structures, diagnose exceptions to their true root cause, and design clear input boundaries.

## 2. Distinguishing Three Places Where null Appears

### 2.1. The collection variable is null

```java
// Illustrative snippet inside a method; requires import java.util.List.
List<String> names = null;
// names.add("A"); // NullPointerException because there is no collection object.
```

There is no collection object yet to even evaluate an element policy. The error occurs because a method is invoked on a `null` reference.

### 2.2. The collection exists and contains a null element

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> names = new ArrayList<>();
names.add(null);

System.out.println(names.size()); // 1
System.out.println(names.get(0)); // null
```

The list is not empty. It has one element whose value is `null`.

`null` is not the string `"null"`, not the empty string `""`, and not "no element" in this structure.

### 2.3. The element exists, but an internal field is null

A `List<Person>` can contain a non-`null` `Person` object whose `name` field is `null`. Standard collections do not automatically validate every property of their elements.

Similarly, prohibiting `null` elements does not guarantee that elements satisfy business rules such as non-empty names, non-negative prices, or complete data. That is the responsibility of the data type and input-validation layer.

## 3. General Contract for Invalid Values

The Collections Framework allows implementations to restrict elements, such as prohibiting `null` or accepting only values with compatible comparability.

When inserting an invalid element, the most common exceptions are:

| Exception | Meaning to Check |
| --- | --- |
| `NullPointerException` | The implementation does not accept `null`, or an internal operation cannot handle `null` |
| `ClassCastException` | The element/key is incompatible with the type or comparison requirements |
| `IllegalArgumentException` | A property of the element/argument does not meet a documented constraint |
| `UnsupportedOperationException` | Modification operations are not supported, even if the value has the right type and is non-`null` |

For queries such as `contains` or removal by object, the general contract may allow returning `false` or throwing an exception for an incompatible element. Do not infer that "prohibiting adding `null`" means every `contains(null)` behaves the same way.

See [Collection API: restrictions on elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). When a concrete class provides a stronger guarantee, rely on that guarantee.

## 4. Null Policy Table for Common Collections

The following table describes **storing elements**, not every query with a `null` argument.

| Implementation or Creation Method | Accepts `null` Elements? | Notes |
| --- | --- | --- |
| `ArrayList` | Yes | Can hold multiple `null` positions |
| `LinkedList` | Yes | When used as a queue, still avoid ambiguity with `poll` results |
| `HashSet` | Yes | At most one `null` element |
| `LinkedHashSet` | Yes | At most one `null`, preserving insertion order |
| `TreeSet` with natural ordering | No | `null` cannot be compared using natural ordering |
| `TreeSet` with a comparator | Depends on the comparator | A comparator with an explicit `null` policy can be used |
| `ArrayDeque` | No | `add/offer` of a `null` element is rejected |
| `PriorityQueue` | No | A comparator that accepts `null` does not override this prohibition |
| `EnumSet` | No | Elements must belong to the exact enum type and be non-`null` |
| `Arrays.asList(...)` | Can contain `null` | Fixed-size list backed by an array |
| `List.of`, `List.copyOf` | No | Factories reject sources containing `null` elements |
| `Set.of`, `Set.copyOf` | No | In addition to the `null` rule, they also have their own duplicate rules |
| `Collections.unmodifiableList(backing)` | Can contain `null` from the source | The wrapper prevents modification; it does not sanitize the source's contents |

References for these implementation groups:

- [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).
- [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).
- [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).
- [EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html), [List factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable), [Set factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable).

Do not turn this table into family-wide rules by name: neither "every list accepts `null`" nor "every structure with a comparator accepts `null`" is true.

## 5. Map Must Be Checked Separately for Keys and Values

`Map` does not extend `Collection`, but it belongs to the same framework and is frequently chosen alongside collection structures. With maps, there are two positions to check independently.

| Implementation or Factory | `null` Keys | `null` Values |
| --- | --- | --- |
| `HashMap` | Allows one `null` key | Allowed |
| `LinkedHashMap` | Allows one `null` key | Allowed |
| `TreeMap` natural ordering | Not allowed | Allowed |
| `TreeMap` with comparator | Depends on the comparator | Allowed |
| `EnumMap` | Not allowed | Allowed |
| `ConcurrentHashMap` | Not allowed | Not allowed |
| `Map.of`, `Map.ofEntries`, `Map.copyOf` | Not allowed | Not allowed |

Corresponding documentation: [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html), [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html), [Map factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

### 5.1. get Returning null Can Have Two Meanings

```java
// Illustrative snippet inside a method; requires import java.util.*.
Map<String, Integer> scores = new HashMap<>();
scores.put("pending", null);

System.out.println(scores.get("unknown"));       // null
System.out.println(scores.get("pending"));       // null
System.out.println(scores.containsKey("unknown")); // false
System.out.println(scores.containsKey("pending")); // true
```

For a map that allows `null` values:

- The key is absent.
- The key is present and mapped to `null`.

Both cases cause `get` to return `null`. If you need to distinguish between them in single-threaded code, check key presence according to the contract.

Do not treat a `get` followed by `containsKey` sequence as an atomic operation when the map may be modified by another thread. Concurrency requires its own design.

### 5.2. Why Must You Check When Switching Implementations?

Replacing `HashMap` with `ConcurrentHashMap` can turn previously accepted inputs into errors. It is not only concurrency characteristics that change; the `null` key/value policy changes as well.

Replacing `HashMap` with `TreeMap` also adds a key comparability requirement. The declared type `Map<K, V>` does not erase these differences.

## 6. null and the Sentinel Value Meaning "Absent"

`Queue.poll` or `Deque.poll` uses `null` to signal an empty structure. If an implementation also allows storing `null` elements, the same return value becomes ambiguous.

```java
// Illustrative snippet inside a method; requires import java.util.*.
Queue<String> queue = new LinkedList<>();
queue.add(null);

System.out.println(queue.size()); // 1
System.out.println(queue.poll()); // null: just retrieved the null element.
System.out.println(queue.size()); // 0
System.out.println(queue.poll()); // null: no element left to retrieve.
```

`LinkedList` allows storing `null`, but that is not a good reason to use `null` as real work in a queue. Choose a data representation that models work explicitly, or require elements to be non-`null`.

With `ArrayDeque`, prohibiting `null` makes a non-`null` `poll` result clearly distinguishable from an empty queue. Do not generalize this reasoning into a rule that "every `Queue` prohibits `null`", because `LinkedList` shows the opposite.

Likewise, do not assume a sequence of `isEmpty` followed by `poll` is automatically thread-safe.

## 7. Ordered Structures: Having the Right Declared Type Is Not Enough

### 7.1. Natural ordering requires comparability

`TreeSet<E>` and the keys of `TreeMap<K, V>` need to be ordered by natural ordering or by a comparator. With natural ordering, the elements/keys must be mutually comparable.

```java
// Illustrative snippet inside a method; requires import java.util.*.
Set<Number> numbers = new TreeSet<>();
numbers.add(1);
// numbers.add(2.5); // ClassCastException: Integer and Double do not have
                    // a compatible cross-type natural ordering in this structure.
```

`Integer` and `Double` are both `Number`, so the API allows passing them according to the declared type. However, "both being `Number`" does not create a shared natural ordering across all numeric types.

If the business requirement genuinely calls for sorting different kinds of values together, design a comparator that defines a consistent ordering over the entire data domain. Do not paper over the error with raw types or blind casts.

### 7.2. A Comparator can define the position of null

```java
// Illustrative snippet inside a method; requires import java.util.*.
Comparator<String> nullFirst =
        Comparator.nullsFirst(Comparator.naturalOrder());

NavigableSet<String> sorted = new TreeSet<>(nullFirst);
sorted.add("B");
sorted.add(null);
sorted.add("A");

System.out.println(sorted); // [null, A, B]
```

This comparator places `null` before non-`null` strings; non-`null` strings are compared using natural ordering. You can use `nullsLast` if the opposite is needed. [Comparator.nullsFirst](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator))

The comparator must handle all values the structure is expected to receive and must obey the comparison contract. Do not simply add a `null` branch and ignore consistency for the remaining cases.

Important: a comparator that accepts `null` only takes effect if **the implementation itself allows it**. `PriorityQueue` still prohibits `null` even when passed a comparator with this policy.

### 7.3. Comparability and "equality" must be consistent

In `TreeSet`, a comparison result of `0` is used to treat elements as occupying the same structural position. If a comparator only compares string lengths, `"An"` and `"Bo"` may be treated as duplicates even though `equals` differs.

This is a different issue from `null`, yet it falls under the same question: "what does the implementation require of its elements?" For a `Set`, the ordering should be consistent with `equals` to preserve the general contract of a set. For an ordered map, key comparison must likewise be designed appropriately.

## 8. What Do Generics Check and What Do They Not Check?

### 8.1. Compile-time type checking

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> words = new ArrayList<>();
words.add("hello");
// words.add(123); // Does not compile.
words.add(null);  // Reference types allow null; ArrayList accepts it as well.
```

Generic type arguments are reference types, not primitive types. Therefore, you use `List<Integer>`, not `List<int>`. However, `Integer` can be `null`; when unboxed to `int`, a `null` value will cause a `NullPointerException`.

The `String` type does not encode a "non-`null`" guarantee in Java's standard type system. If an API requires that condition, it must document and validate it appropriately.

### 8.2. A list of a subtype is not automatically a list of the supertype

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<Integer> integers = List.of(1, 2, 3);
// List<Number> numbers = integers; // Does not compile.

List<Number> numbers = new ArrayList<>();
numbers.addAll(integers);
numbers.add(2.5);

System.out.println(numbers); // [1, 2, 3, 2.5]
```

If assigning `List<Integer>` directly to `List<Number>` were allowed, other code could add a `Double` into the same list that was expected to contain only `Integer`s. The invariance of generic type parameters prevents that corruption.

`addAll` has a signature accepting a `Collection<? extends E>` source, so it can copy `Integer`s into a destination holding `Number`s. Copying elements and assigning references are two different operations.

### 8.3. Type erasure does not create a runtime element-checking barrier on every add

For most Java generics, type arguments are erased from the runtime type representation. `new ArrayList<String>()` does not keep a dedicated `String.class` barrier to automatically check every raw call to `add`.

If raw types or unchecked casts are used, mismatched data can slip in and fail only later when read. There is no contradiction with generics here: the code crossed a boundary that bypassed type checking.

The rules for parameterized types, raw types, type erasure, and heap pollution are described in [JLS Chapter 4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html), especially sections 4.5, 4.6, 4.8, and 4.12.2.

## 9. Raw Code and Checked Collections

### 9.1. Errors can surface late at the read site

```java
// Intentionally unsafe illustration; place inside a method.
// Requires import java.util.*; the compiler emits raw/unchecked warnings.
List<String> words = new ArrayList<>();
List raw = words;
raw.add(123);

// String first = words.get(0); // ClassCastException when casting the result to String.
```

`ArrayList` does not know on its own that it is expected to hold `String` through another reference. Unchecked warnings must be treated as a risk signal, not a nuisance to suppress indiscriminately.

### 9.2. Checked wrappers validate immediately at the insertion boundary

```java
// Illustration when forced to interoperate with legacy code using raw types.
// Requires import java.util.*; raw.add is an intentionally unsafe call.
List<String> checked =
        Collections.checkedList(new ArrayList<>(), String.class);
List raw = checked;

// raw.add(123); // ClassCastException immediately when inserting through the wrapper.
checked.add("A");
checked.add(null); // Allowed: the backing ArrayList allows null.
```

`checkedList` provides a dynamically type-checked view:

- Checks data passing through the view's insertion/replacement operations.
- Does not automatically prohibit `null` if the backing collection allows it.
- Does not automatically fix mistyped data already present in the backing collection.
- Does not prevent another reference from inserting directly into the backing collection, bypassing the wrapper.
- Does not deeply check nested type parameters such as "every inner `List` contains `String`".

It is useful when you must cross legacy code boundaries, but it does not replace proper generic design and business input validation. See [Collections.checkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)).

## 10. Factories, Wrappers, and Copy Operations

### 10.1. Both are Lists, yet their policies differ

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> nullable = new ArrayList<>();
nullable.add(null);

List<String> view = Collections.unmodifiableList(nullable);
System.out.println(view); // [null]

// List<String> snapshot = List.copyOf(nullable);
// The line above throws NullPointerException because the source contains null.
```

"Unmodifiable" and "disallowing `null`" are two independent policies. An unmodifiable wrapper can expose `null` data from its backing source, whereas `List.copyOf` rejects that element when creating the result.

`Set.of` does not accept duplicate elements among the passed arguments; `Set.copyOf` can deduplicate equal elements from the source into a set. Do not infer every rule of the `of` factories onto the `copyOf` factories simply because both produce unmodifiable results.

### 10.2. Watch out for inside-out expression evaluation

```java
// Illustrates an expression that will throw NullPointerException.
// Requires import java.util.*.
// List<String> values = new ArrayList<>(List.of("A", (String) null));
```

`List.of` fails before the `ArrayList` constructor ever receives the data. This does not prove that `ArrayList` prohibits `null`.

If you genuinely need to create a modifiable list containing `null`, use an appropriate source:

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> values =
        new ArrayList<>(Arrays.asList("A", null));
System.out.println(values); // [A, null]
```

### 10.3. A null varargs array is different from a null element

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> oneNull = Arrays.asList((String) null);
System.out.println(oneNull.size()); // 1

// Arrays.asList((String[]) null); // NullPointerException: the source array is null.
```

The casts in the example make the intent explicit: pass a single `String` element that is `null`, or pass the entire array as `null`. See [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 11. contains, remove, and the Risk of Inferring from Queries

`contains(Object)` and `remove(Object)` accept `Object`, so passing an argument whose type differs from the type parameter is not necessarily blocked at compile time.

```java
// Illustrative snippet inside a method; requires import java.util.*.
Collection<String> words = new ArrayList<>(List.of("one"));

System.out.println(words.contains(123)); // false in this ArrayList example.
System.out.println(words.remove(123));   // false.
```

An ordered structure may need to compare the query argument against its elements, leading to a `ClassCastException` for an incompatible type. Similarly, querying `null` on an implementation that prohibits `null` may be rejected according to its contract.

Conclusions to avoid:

- "`contains(null)` returns `false`, so the collection must allow adding `null`."
- "Every method that takes `Object` is safe for any object."
- "Testing successfully on an empty collection is enough to prove the data is valid."
- "Adding one incomparable element didn't fail, so adding subsequent elements will work too."

You must read the rules operation by operation. A comparison may only occur once the structure already has data, and classes may also validate eagerly.

## 12. Designing Policies at Application Boundaries

If the business domain does not accept `null` elements, decide that explicitly up front rather than relying accidentally on whichever collection happens to be used.

```java
// Illustrative method inside a class; requires import java.util.*.
static List<String> validatedNames(Collection<String> source) {
    Objects.requireNonNull(source, "source");

    List<String> result = new ArrayList<>(source.size());
    for (String name : source) {
        result.add(Objects.requireNonNull(name, "name"));
    }
    return List.copyOf(result);
}
```

This method:

1. Rejects a `null` source collection.
2. Rejects any `null` element while building its own result.
3. Does not add or remove elements from the source.
4. Returns an unmodifiable list that cannot contain `null`.

It does not yet check for empty or whitespace-only names. If the business rules require that, add checks with appropriate messages.

Do not silently strip out `null` if position or element count carries meaning, such as a list of scores ordered by subject. "Dropping invalid elements" and "rejecting invalid input" are two different policies.

For a field meaning "no value yet", you can choose an explicit data type or state instead of stuffing `null` into a structure where other operations cannot easily distinguish it. There is no need to wrap every element in `Optional` as a blanket rule; the choice must serve the data model.

## 13. Complete Program

Save as `NullAndTypePolicyDemo.java`. The legacy section intentionally uses raw types to observe when the failure occurs; do not copy that pattern into normal application code.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.NavigableSet;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;

public final class NullAndTypePolicyDemo {
    private static void showRejection(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": accepted");
        } catch (NullPointerException ex) {
            System.out.println(label + ": NullPointerException");
        } catch (ClassCastException ex) {
            System.out.println(label + ": ClassCastException");
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void putThroughLegacyCode(List target, Object value) {
        target.add(value);
    }

    public static void main(String[] args) {
        List<String> nullable = new ArrayList<>();
        nullable.add(null);
        nullable.add("A");
        nullable.add(null);
        System.out.println("List: " + nullable);

        Set<String> unique = new LinkedHashSet<>(nullable);
        System.out.println("Set: " + unique);

        Deque<String> deque = new ArrayDeque<>();
        showRejection("Deque add null", () -> deque.add(null));
        System.out.println("Empty deque poll: " + deque.poll());

        NavigableSet<String> natural = new TreeSet<>();
        showRejection("Natural TreeSet add null", () -> natural.add(null));

        Comparator<String> nullFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        NavigableSet<String> sorted = new TreeSet<>(nullFirst);
        sorted.add("B");
        sorted.add(null);
        sorted.add("A");
        System.out.println("Null-friendly TreeSet: " + sorted);

        Map<String, Integer> map = new HashMap<>();
        map.put(null, 7);
        map.put("missingValue", null);
        System.out.println("Null key value: " + map.get(null));
        System.out.println("Absent value: " + map.get("absent"));
        System.out.println("Present null value: " + map.get("missingValue"));
        System.out.println("Contains absent: " + map.containsKey("absent"));
        System.out.println("Contains missingValue: "
                + map.containsKey("missingValue"));

        Map<String, Integer> concurrent = new ConcurrentHashMap<>();
        showRejection("ConcurrentHashMap null key",
                () -> concurrent.put(null, 1));
        showRejection("ConcurrentHashMap null value",
                () -> concurrent.put("A", null));

        showRejection("List.of null", () -> List.of("A", (String) null));
        showRejection("List.copyOf nullable", () -> List.copyOf(nullable));

        List<String> fixed = Arrays.asList("A", null);
        System.out.println("Arrays.asList: " + fixed);
        List<String> view = Collections.unmodifiableList(nullable);
        System.out.println("Unmodifiable view contains null: "
                + view.contains(null));

        List<String> unsafe = new ArrayList<>();
        putThroughLegacyCode(unsafe, 123);
        showRejection("Read polluted List<String>", () -> {
            String value = unsafe.get(0);
            System.out.println(value);
        });

        List<String> checked =
                Collections.checkedList(new ArrayList<>(), String.class);
        showRejection("Checked legacy insert",
                () -> putThroughLegacyCode(checked, 123));
        checked.add(null);
        System.out.println("Checked allows backing null: " + checked);

        Collection<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        numbers.addAll(integers);
        numbers.add(2.5);
        System.out.println("Numbers: " + numbers);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 NullAndTypePolicyDemo.java
java NullAndTypePolicyDemo
```

The code was verified using `--release 17` on a newer JDK. `@SuppressWarnings` is placed only on the illustrative legacy helper method to keep the output focused; it does not fix the unsafety of raw types.

Stdout:

```text
List: [null, A, null]
Set: [null, A]
Deque add null: NullPointerException
Empty deque poll: null
Natural TreeSet add null: NullPointerException
Null-friendly TreeSet: [null, A, B]
Null key value: 7
Absent value: null
Present null value: null
Contains absent: false
Contains missingValue: true
ConcurrentHashMap null key: NullPointerException
ConcurrentHashMap null value: NullPointerException
List.of null: NullPointerException
List.copyOf nullable: NullPointerException
Arrays.asList: [A, null]
Unmodifiable view contains null: true
Read polluted List<String>: ClassCastException
Checked legacy insert: ClassCastException
Checked allows backing null: [null]
Numbers: [1, 2, 3, 2.5]
```

### What the example demonstrates

- `ArrayList` retains two `null` positions; `LinkedHashSet` retains only one `null` element.
- `ArrayDeque` prohibits `null`; `poll` on an empty instance returns `null`.
- Natural-order `TreeSet` prohibits `null`; the chosen comparator can produce the order `null, A, B`.
- `HashMap` accepts `null` keys and values. `get` does not by itself distinguish an absent key from a key mapped to `null`.
- `ConcurrentHashMap` rejects both kinds of `null`.
- `List.of` and `List.copyOf` reject sources containing `null` elements.
- `Arrays.asList` can hold `null`; an unmodifiable wrapper does not automatically remove `null` from its source.
- Inserting the wrong type through a raw `ArrayList` may only surface when read as `String`. Through a checked wrapper, the error is caught at insertion time.
- Copying `Integer`s into a `List<Number>` via `addAll` is valid; directly assigning `List<Integer>` to `List<Number>` is a different matter.

The `showRejection` helper is only for observing expected exceptions. It does not prove that every input source in an application has been validated.

## 14. Common Mistakes and How to Check

| Misconception | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| `List<String>` definitely has no `null` | Generics do not express non-nullability | Document and validate input conditions |
| Every `List` accepts `null` | Factories such as `List.of` prohibit it | Check how the object was created |
| Every `TreeSet` prohibits `null` | A comparator can define an order for `null` | Check the comparator and class contract |
| If a comparator accepts `null`, every collection accepts `null` | `PriorityQueue` has its own prohibition | Check both the comparator and the implementation |
| `Map.get` returning `null` means the key is absent | It could be a stored `null` value | Use the appropriate contract to distinguish |
| Switching `HashMap` to a concurrent map does not affect inputs | `ConcurrentHashMap` prohibits `null` keys/values | Check policies before swapping |
| `List.of` failing inside an `ArrayList` constructor means `ArrayList` prohibits `null` | The source expression failed first | Check expression evaluation order |
| Both being `Number` means they can be naturally ordered | Numeric types are not mutually comparable under one shared natural order | Choose the right data type or comparator |
| A checked wrapper sanitizes the entire source | It only guards operations going through the wrapper | Validate the source and avoid keeping bypass references |
| Suppressing unchecked warnings solves the problem | Mistyped data can still slip in | Reduce raw types and guard legacy boundaries |
| Unmodifiable means no `null` | These are two independent properties | Document each property separately |

## 15. Self-Check and Practice

### Questions

1. How does `List<String> x = null;` differ from `List<String> x = new ArrayList<>(); x.add(null);`?
2. Why does `new ArrayDeque<String>().add(null)` compile yet fail at runtime?
3. At most how many `null` elements can a `HashSet` contain?
4. What is needed for `TreeSet<String>` to intentionally accept `null`?
5. Is a comparator that accepts `null` enough for `PriorityQueue` to accept `null`?
6. Why can `get` on a `HashMap` return `null` even when the key exists?
7. `List<Number>` can hold `Integer` and `Double`; does a natural-order `TreeSet<Number>` automatically support both?
8. When does a checked wrapper perform its check, and does it automatically prohibit `null`?
9. Why is `Arrays.asList((String) null)` different from `Arrays.asList((String[]) null)`?
10. When switching implementations, besides the generic type, what constraints should you check?

### Exercises

- Create your own test table for `add(null)`, `contains(null)`, and `remove(null)`; distinguish what the documentation guarantees from what you observe on the running implementation.
- Use `TreeSet` with `nullsFirst`, then switch to `nullsLast`; predict the order before running.
- Create a `HashMap` with the key `"pending"` mapped to `null` and compare it against a nonexistent key.
- Refactor a snippet using raw types so that no unchecked warnings remain.
- Wrap a legacy boundary with `Collections.checkedList` and verify that the wrong type is rejected immediately on insertion.
- Write a helper method that validates a source has no `null` elements before passing it into a collection with a stricter policy.
- Try converting data containing `null` from an `ArrayList` to `List.copyOf`; explain the error and choose a business-appropriate handling policy instead of silently dropping data.

### Reference Answers

1. The first case has no collection object; the second has a list containing one `null` element.
2. Reference types allow passing `null`, but the implementation class rejects that value.
3. One.
4. An appropriate comparator that handles `null` and obeys the comparison contract.
5. No; the implementation has its own prohibition rule.
6. The map may store a `null` value for that key.
7. No; sharing a supertype does not create cross-type natural comparability.
8. It checks when data is inserted through the view; `null` handling depends on the backing collection.
9. One passes a single `null` element; the other passes a `null` source array.
10. `null` policy, comparability, equality semantics, element/key type constraints, value limits, and per-operation behavior.
