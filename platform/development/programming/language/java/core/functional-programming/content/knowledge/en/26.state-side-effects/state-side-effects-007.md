# Immutability of Result Objects and Input Objects in Java

## 1. Goal: transforming data without unintended changes

In Java functional programming, lambdas and Stream operations are often used to **take input → transform → produce output**. They help reduce reliance on mutable state, but they **do not automatically make data immutable**. In particular, two properties must be distinguished:

- **Not mutating the input object**: the function does not change the state of the passed-in object, does not add or remove elements, and does not call setters or modify mutable fields inside the input.
- **Immutable result object**: after creation, the state of the result cannot be changed through references exposed by the API, including any publicly exposed nested components.

These two properties are independent. A function can avoid mutating the input yet return **the very same mutable input object**, causing subsequent changes to still affect the result. Conversely, a function can corrupt the input via mutation and then return an immutable `String`: an immutable output **cannot undo** side effects that have already occurred.

~~~java
// Illustration inside a method, with List imported.
StringBuilder source = new StringBuilder("A");

List<StringBuilder> shared = List.of(source);  // Shared reference.
List<String> detached = List.of(source.toString()); // Immutable string.

source.append("B");
System.out.println(shared.get(0));   // AB
System.out.println(detached.get(0)); // A
~~~

In both cases, the outer lists do not allow structural modification, yet `shared` still holds a reference to a mutable `StringBuilder`. `detached` holds a `String` value created at the time of transformation.

**Foundational rule:** Do not judge immutability solely by the outer collection type name or whether the code uses `map()`, `record`, or `final`. Examine **all observable state, aliasing, and how data is copied**.

## 2. Commonly confused concepts

| Concept | Explanation | Example |
|---|---|---|
| **Mutable object** | Has state that can change after creation | `StringBuilder`, `ArrayList`, `int[]` array |
| **Immutable object** | Observable state does not change after creation | `String`, `Integer`, a properly designed value object |
| **Unmodifiable collection** | Disallows structural changes through that collection's API | `Stream.toList()`, `List.of()` |
| **Shallow copy** | Creates a new structure but may retain references to child objects | `new ArrayList<>(source)` |
| **Deep immutability** | All accessible mutable components are protected from external modification | A DTO composed of immutable values and copied lists |
| **Aliasing** | Multiple variables referencing the same object | `a.get(0) == b.get(0)` can be true |
| **Side effect** | A change outside the return value or other observable behavior | Logging, mutating input, updating a counter |
| **Pure function** | Output depends on input and causes no observable side effects | A deterministic String normalization operation |

**Immutability does not equal purity.** A function that returns an immutable string while reading the current time or updating a static variable is still not pure. Conversely, a function may accept a reference to a mutable object and only read it to produce a new value; although it causes no mutation, the function still needs to know whether the input can be modified by another thread.

**Unmodifiable does not equal deeply immutable.** Being unable to call `list.add(...)` does not mean you cannot call `list.get(0).setName(...)`.

## 3. Immutable input and avoiding input mutation

### 3.1. Easy-to-reason-about approach: creating new values

Suppose we have a record:

~~~java
record Product(String code, int price) {}
~~~

The `String` and `int` components fit an immutable value model. When prices need to be increased:

~~~java
List<Product> updated = products.stream()
        .map(p -> new Product(p.code(), p.price() + 10))
        .toList();
~~~

This snippet illustrates code inside a method that has `products` of type `List<Product>`. Each `Product` in the result is newly created, while the original elements remain unmodified. The benefit is that you can compare old and new versions, write simpler tests, and avoid changing data in another component that still holds a reference to the old version.

### 3.2. Approach with a hidden side effect inside map

~~~java
// WARNING CODE: assuming MutableProduct has getPrice/setPrice.
List<MutableProduct> changed = products.stream()
        .map(p -> {
            p.setPrice(p.getPrice() + 10);
            return p;
        })
        .toList();
~~~

Even though the code calls `map`, it still **mutates the input objects**. Many other references can observe the new price. If the pipeline is run again on the same objects, the price could be incremented a second time. In a parallel stream, if the same objects are shared, the situation becomes even more complicated due to race conditions.

Not all mutation is forbidden. For persistence entities that genuinely need to be updated, make the operation explicit at the business layer (a loop or a command with a transaction), rather than having a transformation expected to produce new values carry a hidden side effect.

## 4. Java 17 program: shared-object result vs. detached result

Save as **`InputOutputImmutabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class InputOutputImmutabilityDemo {
    public static void main(String[] args) {
        List<StringBuilder> input = new ArrayList<>();
        input.add(new StringBuilder("alpha"));
        input.add(new StringBuilder("beta"));

        List<StringBuilder> shared = input.stream().toList();
        List<String> snapshot = input.stream()
                .map(sb -> sb.toString().toUpperCase(Locale.ROOT))
                .toList();

        input.get(0).append("!");
        input.add(new StringBuilder("gamma"));

        System.out.println("input=" + input);
        System.out.println("shared=" + shared);
        System.out.println("snapshot=" + snapshot);

        try {
            shared.add(new StringBuilder("delta"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("shared.add=blocked");
        }

        shared.get(0).append("?");
        System.out.println("inputAfterEdit=" + input);
        System.out.println("snapshotAfterEdit=" + snapshot);
    }
}
~~~

Run on JDK 17+:

~~~bash
javac InputOutputImmutabilityDemo.java
java InputOutputImmutabilityDemo
~~~

Stdout:

~~~text
input=[alpha!, beta, gamma]
shared=[alpha!, beta]
snapshot=[ALPHA, BETA]
shared.add=blocked
inputAfterEdit=[alpha!?, beta, gamma]
snapshotAfterEdit=[ALPHA, BETA]
~~~

**Analysis:**

1. `shared` is obtained via `toList()`, so **the list structure cannot be modified**, but the `StringBuilder` elements inside remain mutable.
2. `snapshot` is created using `StringBuilder.toString()` and `String.toUpperCase(Locale.ROOT)`, producing immutable `String` elements.
3. When `gamma` is added to the input list after collection, the two collected lists do not gain the new element. They are snapshots of the **collected structure**.
4. When the contents of the first `StringBuilder` are modified, the change is visible through `shared` because they reference the same object. `snapshot` retains the value `ALPHA` and does not change.
5. `shared.add(...)` throws `UnsupportedOperationException`. However, `shared.get(0).append("?")` is still valid because it mutates the **element object**, not the list.
6. The output proves that **an unmodifiable outer list does not make its elements immutable** and **not mutating input during mapping is not enough for the result to be independent of mutable input**.

The `System.out.println` lines in the program are for explanation; they are not inside the mapper and are not used as a guarantee about Stream intermediate callback ordering.

## 5. An unmodifiable collection can still share mutable state

Common APIs:

| API | Outer list modifiability | Deep to elements? |
|---|---|---|
| `Stream.toList()` (Java 16+) | Unmodifiable | No |
| `Collectors.toUnmodifiableList()` (Java 10+) | Unmodifiable | No |
| `List.copyOf(source)` | Structural unmodifiable snapshot | No |
| `Collections.unmodifiableList(backing)` | Unmodifiable **view** | No; changes to backing can still be seen |
| `Collectors.toCollection(ArrayList::new)` | Mutable `ArrayList` | No |
| `Collectors.toList()` | No guarantee on list type or modifiability | No |

**View vs. structural snapshot:**

~~~java
List<String> backing = new ArrayList<>(List.of("a"));
List<String> view = Collections.unmodifiableList(backing);
List<String> snapshot = List.copyOf(backing);
backing.add("b");

System.out.println(view);     // [a, b]
System.out.println(snapshot); // [a]
~~~

This snippet uses imports `java.util.List`, `java.util.ArrayList`, and `java.util.Collections`. `Collections.unmodifiableList` blocks modifications through the view, but the view still reflects the backing list. `List.copyOf` provides a structural snapshot that does not automatically update on subsequent additions or removals.

**Structural copy is not a deep copy:**

~~~java
StringBuilder item = new StringBuilder("draft");
List<StringBuilder> copy = List.copyOf(List.of(item));
item.append("-edited");
System.out.println(copy.get(0)); // draft-edited
~~~

`List.copyOf` does not clone the `StringBuilder` object; the source and result still share the same reference. When building an immutable API, you must check whether element objects have setters, collections, arrays, or any mutable state.

## 6. Record and final do not automatically guarantee deep immutability

A record stores its components in `private final` fields, but `final` locks the **reference**, not the state of the referenced object.

~~~java
record Report(String name, List<Integer> scores) {}

List<Integer> scores = new ArrayList<>(List.of(2, 3));
Report report = new Report("A", scores);
scores.add(99);

System.out.println(report.scores()); // [2, 3, 99]
~~~

If the record constructor does not make a defensive copy, the caller can still modify the list through the source reference. To protect at the entry boundary:

~~~java
record ScoreSnapshot(String name, List<Integer> scores) {
    public ScoreSnapshot {
        scores = List.copyOf(scores);
    }
}
~~~

`List.copyOf` creates an unmodifiable list and a snapshot of the elements at the time of copying. Because `Integer` is immutable, this model does not expose a mutable reference at the scores level. However, if `Integer` were replaced with `MutablePerson`, the elements could still be modified; each element must be converted into an immutable DTO.

### 6.1. Java 17 program: defensive copy and independent output

Save as **`DefensiveSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveSnapshotDemo {
    record InputGroup(String name, List<Integer> values) {}

    record ResultGroup(String name, List<Integer> values, int total) {
        public ResultGroup {
            values = List.copyOf(values);
        }
    }

    static ResultGroup transform(InputGroup input) {
        List<Integer> copied = List.copyOf(input.values());
        int sum = copied.stream().mapToInt(Integer::intValue).sum();
        return new ResultGroup(input.name(), copied, sum);
    }

    public static void main(String[] args) {
        List<Integer> sourceValues = new ArrayList<>(List.of(2, 3));
        List<InputGroup> source = new ArrayList<>();
        source.add(new InputGroup("A", sourceValues));

        List<ResultGroup> output = source.stream()
                .map(DefensiveSnapshotDemo::transform)
                .toList();

        sourceValues.add(99);
        source.add(new InputGroup("B", List.of(7)));

        System.out.println("sourceValues=" + sourceValues);
        System.out.println("sourceSize=" + source.size());
        System.out.println("outputSize=" + output.size());
        System.out.println("output=" + output);

        try {
            output.get(0).values().set(0, 100);
        } catch (UnsupportedOperationException ex) {
            System.out.println("inner.set=blocked");
        }

        try {
            output.add(new ResultGroup("X", List.of(), 0));
        } catch (UnsupportedOperationException ex) {
            System.out.println("outer.add=blocked");
        }
    }
}
~~~

Compile/run:

~~~bash
javac DefensiveSnapshotDemo.java
java DefensiveSnapshotDemo
~~~

Stdout:

~~~text
sourceValues=[2, 3, 99]
sourceSize=2
outputSize=1
output=[ResultGroup[name=A, values=[2, 3], total=5]]
inner.set=blocked
outer.add=blocked
~~~

**Detailed explanation:**

- `InputGroup` holds a reference to the mutable `sourceValues`; the record does not prevent the caller from mutating the source.
- `transform` takes a copy before computing the sum, then returns a `ResultGroup` with a defensively copied list. `ResultGroup` also copies in its constructor to protect callers outside this pipeline.
- `sourceValues.add(99)` after collection does not change `ResultGroup.values()`; adding an `InputGroup` to `source` also does not change the outer `output`.
- `output` does not allow adding elements; the inner `values` list also does not allow `set`.
- With immutable `String` and `Integer` in this example's object graph, the result can be considered immutable with respect to its exposed data.
- Copying a source **that is being concurrently modified** still requires an appropriate snapshot/synchronization mechanism; `List.copyOf` does not create a transactional snapshot on its own.

## 7. Arrays are mutable: copy in both directions

Java arrays always allow element mutation, even when a record contains a `final` array field:

~~~java
record UnsafePacket(byte[] data) {}

byte[] raw = {1, 2};
UnsafePacket packet = new UnsafePacket(raw);
raw[0] = 9;
System.out.println(packet.data()[0]); // 9
~~~

This is an illustrative snippet. `UnsafePacket` retains the original reference to the array; the caller can mutate it via `raw` or the `data()` accessor.

To prevent external modification of internal data:

~~~java
record Packet(byte[] data) {
    public Packet {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Copying in the **constructor** prevents the caller from mutating state through the input array. Copying in the **accessor** prevents the caller from obtaining the internal array and mutating it. For custom types containing `List<MutableItem>`, you must also consider how to copy **each element object** and any deeply nested collections.

An important detail: a record containing an array still has default `equals()/hashCode()` semantics for arrays, which **do not automatically compare element contents**. If you design a value object with array content equality, you need to define an appropriate equality policy in addition to defensive copying.

## 8. Not mutating input can still cause side effects

A mapper can produce a new `String` while still doing work outside the input data:

~~~java
// Illustration with externalCounter as application state.
List<String> result = names.stream()
        .map(name -> {
            externalCounter.incrementAndGet();
            return name.toUpperCase(Locale.ROOT);
        })
        .toList();
~~~

Here the input String is not mutated and the result is also an immutable String, but the callback **modifies externalCounter**, so it is not a pure function. Other sources of side effects/nondeterminism include:

- Writing logs, writing files, making database/network calls.
- Reading time, random values, or environment state such that the same input can yield different output.
- Modifying a cache, static field, or mutable collection outside the pipeline.
- Modifying the source collection itself while the stream is traversing it.
- Calling a method that looks like a getter but has a side effect.

**Note on Streams:** intermediate callbacks such as those in `map` or `peek` should not contain side effects **that must run for every element**. Short-circuiting can stop early, and valid optimizations may skip callbacks that are not needed for the result.

~~~java
// Do not use as a mandatory audit mechanism:
long count = records.stream()
        .peek(this::audit)
        .count();
~~~

For a source with a known size, `count()` can derive the result without traversing each element, so `peek` is not guaranteed to be called.

### 8.1. Final/effectively final does not mean an immutable object

~~~java
final List<String> log = new ArrayList<>();

List<String> values = List.of("a", "b").stream()
        .map(s -> {
            log.add(s);
            return s.toUpperCase(Locale.ROOT);
        })
        .toList();
~~~

The `log` variable is `final`: you cannot reassign a different reference to `log`, but you can certainly call `log.add`. Therefore, a lambda capturing an *effectively final* variable can still be **stateful** or affect external mutable state.

If executed in parallel, updating a shared `ArrayList` can also cause a race condition. Prefer stateless, non-interfering callbacks and avoid mutation inside mappers when the task is purely value transformation.

## 9. Reduce and immutable result objects

A data aggregation program can use an immutable accumulator to avoid sharing mutable state. With `reduce`, you must also ensure **a valid identity**, an **associative** combining operation, and a compatible accumulator/combiner.

### 9.1. Java 17 program: not mutating transactions or Summary

Save file as **`ImmutableReductionDemo.java`**:

~~~java
import java.util.List;

public class ImmutableReductionDemo {
    record Transaction(String code, int amount) {}

    record Summary(long count, long total) {
        Summary plus(Transaction transaction) {
            return new Summary(count + 1, total + transaction.amount());
        }

        Summary combine(Summary other) {
            return new Summary(count + other.count, total + other.total);
        }
    }

    public static void main(String[] args) {
        List<Transaction> source = List.of(
                new Transaction("A", 7),
                new Transaction("B", 5),
                new Transaction("C", -2)
        );

        Summary summary = source.parallelStream()
                .reduce(
                        new Summary(0, 0),
                        Summary::plus,
                        Summary::combine
                );

        List<Transaction> increased = source.stream()
                .map(t -> new Transaction(t.code(), t.amount() + 1))
                .toList();

        System.out.println("source=" + source);
        System.out.println("increased=" + increased);
        System.out.println("summary=" + summary);
    }
}
~~~

Run commands:

~~~bash
javac ImmutableReductionDemo.java
java ImmutableReductionDemo
~~~

Stdout:

~~~text
source=[Transaction[code=A, amount=7], Transaction[code=B, amount=5], Transaction[code=C, amount=-2]]
increased=[Transaction[code=A, amount=8], Transaction[code=B, amount=6], Transaction[code=C, amount=-1]]
summary=Summary[count=3, total=10]
~~~

**Why is this pattern sound?**

1. `Transaction` consists of `String` and `int`, with no exposed mutable components; the mapper creates new records instead of mutating the source transactions.
2. `Summary` holds only two `long` values. `plus` and `combine` always create a new `Summary`; they do not mutate a shared identity.
3. `new Summary(0,0)` is the proper identity for adding `count`/`total`. `Summary::combine` is associative, and `plus` is compatible with the combiner.
4. `parallelStream` may split the data and merge results in different groupings, yet the logical value remains 3 transactions and total `7+5-2=10`.
5. Immutability mitigates certain concurrency bugs; it **does not automatically guarantee** that shared services, source data, or side effects elsewhere are thread-safe.
6. For financial data or large numeric ranges, overflow/rounding rules must be specified and `BigDecimal` or the smallest integer unit should be considered; the example only illustrates small integers.

### 9.2. Do not mutate the identity in reduce

~~~java
// WARNING: avoid using a shared mutable StringBuilder as the identity.
StringBuilder result = words.parallelStream().reduce(
        new StringBuilder(),
        (builder, word) -> builder.append(word),
        (left, right) -> left.append(right)
);
~~~

Although such code can be written, it violates the identity/accumulator assumptions of `reduce` when an object is mutated and shared, especially in parallel streams. When concatenating strings, prefer `Collectors.joining()`; when collecting into a mutable collection, use `collect` with a contract-compliant collector.

**Distinction:** immutable reduction is a way of combining **values**. Mutable collections are gathered under the `collect` contract; you should not misuse `reduce` to covertly mutate a shared object.

## 10. Designing immutable DTOs layer by layer

Suppose we need to convert mutable source entities into a public result:

~~~text
MutableOrder -> OrderView
                 ├── id: String
                 └── lines: List<LineView>
                                 ├── sku: String
                                 └── quantity: int
~~~

We can define:

~~~java
record LineView(String sku, int quantity) {}

record OrderView(String id, List<LineView> lines) {
    public OrderView {
        lines = List.copyOf(lines);
    }
}
~~~

If the `LineView` instances are new records built from mutable source lines, `String` and primitive fields are stable, the inner list is copied, and the outer list is collected with `toList()`, the output model can achieve deep immutability for its exposed data.

~~~java
// Illustration: inputOrders is a List<MutableOrder> with appropriate getters.
List<OrderView> result = inputOrders.stream()
        .map(order -> new OrderView(
                order.getId(),
                order.getLines().stream()
                        .map(line -> new LineView(
                                line.getSku(), line.getQuantity()))
                        .toList()
        ))
        .toList();
~~~

This illustrative snippet omits the `MutableOrder` definition, so it is not a standalone runnable file. It demonstrates the conversion boundary:

1. Do not retain direct references to `MutableOrder` or `MutableLine`.
2. Convert each element's data into an immutable value object.
3. Copy the structure of the nested list in the `OrderView` constructor.
4. Collect the outer list as unmodifiable.
5. Validate `null` and business rules before passing to `List.copyOf` (this API rejects null elements).

If a field of `LineView` were a `byte[]` or `List<MutableItem>`, further copying would be required. There is no generic, business-accurate, safe `deepCopy()` function for every Java object.

## 11. Immutability and parallel processing

In a parallel Stream, Java can invoke callbacks on multiple threads and split the source into chunks. Therefore:

- Immutable input values reduce the risk of one worker modifying data another worker is reading.
- Mappers that create new objects reduce aliasing and order dependence.
- Immutable/associative accumulators allow `reduce` to merge branch results according to contract.
- However, callbacks can still use caches, databases, static fields, or external mutable logs, so the code is not guaranteed to be pure.
- If another thread is modifying the source collection itself without synchronization, traversing/copying does not automatically produce a consistent snapshot.
- `Collections.unmodifiableList(backing)` is only an unmodifiable view; it does not stop another thread from modifying `backing`.

**Do not use the immutability of captured variables as proof of thread safety.** A `final List<String> list` can still be modified via `list.add`. If multiple threads share a list, you must choose an appropriate data structure, synchronization, or ownership model.

Nor should you assume an immutable result can be safely built from input being mutated concurrently without synchronization. You may need locking while taking a snapshot, versioning, or ensuring the source remains stable during the transformation.

## 12. When mutation is business logic: separating effects from transformations

Applications still need to write to databases, emit events, update state, and create files. Java functional programming does not require eliminating all mutation, but it recommends **placing side effects at clearly identifiable boundaries**:

~~~java
// Illustration with methods already defined in the application class.
List<OrderView> views = orders.stream()
        .map(this::toImmutableView)
        .toList();

repository.saveAll(views);
~~~

Transformation and I/O are separated into two steps. `toImmutableView` should produce new data without mutating the source, while `saveAll` represents the write operation where transactions and exceptions can be controlled.

If actual entities need to be updated one by one, a loop or command with a clear contract on execution count and operation order can be more readable than hiding setters inside `map()`. In particular, do not use `peek` to guarantee a mandatory business action on all elements: intermediate operation callbacks may be skipped or the pipeline may short-circuit.

## 13. Common mistakes and how to fix them

| Mistake | Why is it dangerous? | How to fix |
|---|---|---|
| Assuming `map` is always pure | The mapper can still call setters or write logs | Inspect callback body, avoid mutation |
| Using `map(x -> x)` and expecting an independent snapshot | Shares the input references | Create new DTO/value objects, copy when needed |
| Believing `Stream.toList()` makes all elements immutable | Only blocks structural changes to the outer list | Convert mutable elements to immutable ones |
| Assuming `List.copyOf` performs a deep copy | Copies structure only, does not clone elements | Copy each mutable layer |
| Assuming record/final means deep immutability | Final fields can still point to mutable objects | Defensive copy and safe accessors |
| Copying input while exposing an array via getter | Caller can still mutate the internal array | Copy the array in both constructor and accessor |
| Not mutating input so assuming it is definitely pure | May mutate external state or read clock/random | Control all side effects |
| Using a captured `ArrayList` in a parallel mapper | Race conditions, nondeterministic callback order | Stateless callbacks or a contract-compliant collector |
| Mutating the identity in parallel reduce | Incorrect merging, aliasing | Immutable accumulator or collector |
| Copying a concurrently modified list and trusting it as a transactional snapshot | No point-in-time consistency guarantee | Synchronize or use an appropriate snapshot |
| Skipping data validation because the object is immutable | Initial state can still be invalid | Validate in constructor/API boundary |
| Relying on unmodifiable output to forbid input mutation | Two object graphs can share aliases | Define ownership and copy |

### 13.1. Distinguishing structural immutability from observable content

A `List<StringBuilder>` may disallow adding or removing elements, yet `get(0).append` still alters an element's value. When an immutable snapshot is needed, identify **exactly which objects can be mutated** and **which references remain outside**. Without analyzing aliasing, two structures that look similar can have very different semantics.

### 13.2. Do not overuse copying

Copying entire object graphs at every step can waste CPU/memory and complicate object identity and relationship management. Place copies at **ownership boundaries and public APIs** rather than copying indiscriminately. For immutable leaves like `String`, keeping a reference poses no mutation risk. Mutable values like `Date`, arrays, nested lists, or entities with setters require a clear copying policy.

## 14. Pipeline review checklist

1. Does the input contain mutable objects, arrays, nested lists/maps, setters, or references held elsewhere?
2. Does the mapper mutate the input or external state?
3. Is the result a new object or the same old reference?
4. If the outer result is unmodifiable, are the inner elements immutable?
5. Do you need a snapshot independent of the source structure? Are you using a view or a copy?
6. Does the DTO/record constructor copy mutable components on input?
7. Do getters/accessors expose mutable references externally?
8. Are there any unprotected nested collections or mutable elements?
9. Can the data be modified concurrently during the transformation?
10. Does the callback depend on time, random values, I/O, counters, or caches?
11. Are parallel Streams, short-circuiting, or terminal optimizations used in a way that makes side effects unpredictable?
12. If using `reduce`, are the identity, associativity, and combiner valid?
13. Should actual mutations be placed in a command/transaction layer instead of inside `map`/`filter`?
14. Do tests try mutating the input **after creating the output**, mutating output elements, and mutating lists/arrays through accessors?

A useful test for deep immutability is: create the output; mutate the input objects through every available reference; try modifying the outer collection; try modifying nested collections; try modifying mutable leaves; verify the output still satisfies its contract. That test verifies behavior rather than relying on class names.

## 15. Self-check questions

**Q1.** Does `Stream.toList()` guarantee that `StringBuilder` elements are immutable?

**Q2.** Does `map(x -> x)` create an independent snapshot of the input objects?

**Q3.** Is a function that does not mutate its input but logs or reads the clock guaranteed to be a pure function?

**Q4.** Why can a record with a `List<Integer>` still be mutated if its constructor does not copy?

**Q5.** Does `List.copyOf(List.of(new StringBuilder("x")))` create a deeply immutable graph?

**Q6.** Does `final ArrayList<String>` prevent calling `add`?

**Q7.** Why is it necessary to copy `byte[]` in both the constructor and the accessor?

**Q8.** When should `Collectors.joining()` be used instead of `reduce` with a mutable `StringBuilder` identity?

**Q9.** If a snapshot is created with `List.copyOf` while another thread modifies the source, does Java automatically guarantee a transactional snapshot?

**Q10.** How should you structure code that keeps a mutable source at persistence while returning an immutable API output?

**Short answers:**

1. No; only the outer list is unmodifiable.
2. No; it returns the exact same references.
3. No; side effects and nondeterminism must be evaluated separately.
4. The record holds a reference to the mutable list; the caller can mutate the list afterward.
5. No; the `StringBuilder` element remains mutable and shared.
6. No; `final` prevents reassigning the reference, not mutating the object.
7. To prevent callers from mutating state through the input array or the array returned by the getter.
8. Whenever you want to concatenate multiple strings using contract-compliant mutable accumulation with the proper collector.
9. No; concurrency must be controlled and the source kept stable during copying.
10. Convert entities through a mapper that creates new value DTOs, copy nested mutable data, return the outer collection according to contract, and separate write side effects.

## 16. Official references

- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `map`, `toList`, `reduce`, and callback guarantee limits.
- [Java SE 17 — java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): stateless/non-interfering behavioral parameters, side effects, and parallelism.
- [Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `copyOf`, immutable collection factories.
- [Java SE 17 API — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): collectors for mutable accumulation and `joining`.
- [Java SE 17 — Records](https://docs.oracle.com/en/java/javase/17/language/records.html): records, compact constructors, and component accessors.

**Takeaway:** Not mutating the input object and returning an immutable result are **two separate guarantees**. A `map` pipeline can still share mutable references; `Stream.toList()` only blocks modifications to the outer list. To achieve a reliably immutable result, use **immutable value types**, intentionally construct new objects, **defensively copy every mutable layer that must be exposed**, and avoid hidden side effects in callbacks.