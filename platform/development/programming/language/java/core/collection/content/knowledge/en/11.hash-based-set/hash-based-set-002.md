# Adding, Finding, Removing, and Conditions for Expected Performance of Hash-Based Sets

## 1. What problem does HashSet solve?

A program that processes many task codes often has to answer repeatedly: "has this code appeared yet?", "is this the first time receiving this code?", or "is this code still in the pending group?".

If you traverse the entire list yourself for every question, the number of comparisons can grow with the number of stored elements. `HashSet<E>` organizes data using hashing to narrow down where to search, rather than forcing every query to scan every element.

The three core operations are:

| Purpose | Method | Meaning of return value |
| --- | --- | --- |
| Add if not present | `boolean add(E value)` | true if the set added the element |
| Check membership in the set | `boolean contains(Object value)` | true if a matching element is found |
| Remove if present | `boolean remove(Object value)` | true if the set had an element removed |

The `HashSet` documentation describes basic operations as having constant-time performance when the hash function disperses elements properly among the buckets of the table. In practice, people often say `add`, `contains`, and `remove` are expected O(1); for insertions, resizing costs must also be considered under amortized analysis.

The hash distribution condition is part of the conclusion, not a detail that can be ignored. Expected O(1) does not mean every call always takes the exact same number of nanoseconds, has no collisions, performs no memory allocations, or never resizes. [HashSet: model and performance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

This lesson focuses on `HashSet` in Java 17+. When a variable only has the `Set` type, you need to know what the actual object is before inferring its performance model. The `Set` interface does not require every implementation to use hashing.

## 2. The hash-based element lookup model

### 2.1. Hash tables narrow down the search area

`HashSet` uses a `HashMap` behind the scenes to manage its elements. As a user of the set, you do not need to manipulate that map directly; what you need to understand is the relationship between two methods of an element:

- `hashCode()` helps determine the region that may contain the element.
- `equals(...)` determines whether two values are actually equal.

You can visualize a query with the following diagram:

```text
value to find
    ↓
compute hash code
    ↓
select the corresponding bucket in the table
    ↓
compare candidates in that region
    ↓
distinguish equality using the equals rule
    ↓
found / not found
```

This is a model for reasoning, not a formula for computing bucket indices or a mandatory description of every JDK version.

A `HashSet` does not sort elements by value to perform the operations above. Nor does it have indices for a user to ask to "remove the element at position 3". If you need to remove a value, pass the query value itself to `remove`.

### 2.2. Matching hash codes does not mean matching elements

Two different objects can have the same hash code. That is a **hash collision**.

For example, two task keys `id=10` and `id=20` might be routed to the same region by a poor hash function. The set still needs to use the equality rule to keep them as two separate elements if they are not equal.

Therefore:

```text
equals true  → must have the same hashCode
same hashCode → not sufficient to conclude equals is true
```

If there are only a few collisions in a well-distributed table, this mechanism remains useful. If almost every key piles into the same region, narrowing the search area loses most of its benefit.

Having the same hash code does not cause the set to silently drop distinct keys. Conversely, an incorrect `equals` definition can cause values that business logic wants to keep separate to be treated as duplicates. The correctness of the equality rule must be resolved before optimizing hash distribution. [Object: equals and hashCode contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

## 3. Reading the results of add, contains, and remove accurately

### 3.1. add answers whether the set accepted a new element

For a `HashSet` with stable element rules:

- No element equal to the value being added exists yet: the set adds the element, size increases by 1, returns `true`.
- An element equal to that value already exists: the set does not add a duplicate, size does not change, returns `false`.

Two separately created objects can still be a single value as far as the set is concerned. Therefore, "used `new` again" is not a reason to expect the size to increase.

When you only want to handle the first encounter with a code, use the result of `add` directly:

```java
// Illustrative snippet: seen is a HashSet<String> managed by the current thread.
if (seen.add(code)) {
    System.out.println("Lần đầu gặp mã: " + code);
}
```

There is no need to write `if (!seen.contains(code))` first and then `seen.add(code)`. That approach usually performs an extra lookup that `add` already has to do anyway.

### 3.2. contains is a read operation, not removing an element from the set

`contains(value)` returns a `boolean`, not the stored element or an element position. It does not change the size of the set.

The parameter is `Object`. For example, with a `HashSet<Integer>` containing `1`, calling `contains(1L)` still compiles, but a `Long` with value `1L` is not equal to an `Integer` with value `1`.

Do not assume that any value types that "look the same" in a user interface will be treated as equal by the set. The type and normalization of the query value must match the identity rule in use.

### 3.3. remove answers whether an element was removed

`remove(value)` removes the element equal to the query value if present and returns `true`. If not present, the set remains unchanged and returns `false`.

If you only need to remove and report whether the set changed:

```java
// Illustrative snippet: pending is a mutable HashSet<TaskId>.
if (pending.remove(taskId)) {
    System.out.println("Đã bỏ công việc khỏi nhóm đang chờ");
}
```

There is no need for `contains` before every `remove`. The return value of `remove` already answers whether the set changed.

| Call with a valid value | Before operation | Result | After operation |
| --- | --- | --- | --- |
| `add(x)` | x not present | `true` | Contains x; size increases by 1 |
| `add(x)` | Value equal to x already present | `false` | Unchanged |
| `contains(x)` | Value equal to x present | `true` | Unchanged |
| `contains(x)` | x not present | `false` | Unchanged |
| `remove(x)` | Value equal to x present | `true` | No longer contains x; size decreases by 1 |
| `remove(x)` | x not present | `false` | Unchanged |

The table assumes elements are not mutated in a way that changes their equality rule while inside the set, and that no other actor modifies the set concurrently.

Calling `add` or `remove` directly avoids a redundant lookup; it does not automatically make `HashSet` safe for concurrent modification by multiple threads. `HashSet` provides no built-in synchronization. [HashSet operations and synchronization limits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

## 4. Complete program: adding duplicates, finding by value, and removing

Save the code in **HashSetOperationsDemo.java**:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class HashSetOperationsDemo {
    private record TaskId(String value) {
    }

    public static void main(String[] args) {
        Set<TaskId> pending = new HashSet<>();
        TaskId original = new TaskId("t-10");
        TaskId sameValue = new TaskId("t-10");

        System.out.println("same reference: " + (original == sameValue));
        System.out.println("add first: " + pending.add(original));
        System.out.println("add equal key: " + pending.add(sameValue));
        System.out.println("size after duplicate: " + pending.size());
        System.out.println("contains equal key: "
                + pending.contains(new TaskId("t-10")));
        System.out.println("contains missing key: "
                + pending.contains(new TaskId("t-99")));
        System.out.println("remove equal key: "
                + pending.remove(new TaskId("t-10")));
        System.out.println("remove again: "
                + pending.remove(new TaskId("t-10")));
        System.out.println("empty: " + pending.isEmpty());

        Set<String> tags = new HashSet<>();
        System.out.println("add null: " + tags.add(null));
        System.out.println("add null again: " + tags.add(null));
        System.out.println("contains null: " + tags.contains(null));
        System.out.println("remove null: " + tags.remove(null));

        Set<String> seen = new HashSet<>();
        for (String value : List.of("java", "sql", "java", "http", "sql")) {
            if (seen.add(value)) {
                System.out.println("first encounter: " + value);
            }
        }
        System.out.println("distinct values: " + seen.size());
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 HashSetOperationsDemo.java
java HashSetOperationsDemo
```

Stdout:

```text
same reference: false
add first: true
add equal key: false
size after duplicate: 1
contains equal key: true
contains missing key: false
remove equal key: true
remove again: false
empty: true
add null: true
add null again: false
contains null: true
remove null: true
first encounter: java
first encounter: sql
first encounter: http
distinct values: 3
```

How to read the output:

1. The two `TaskId("t-10")` instances have different references but are equal by their record component value.
2. Adding the first object succeeds; adding an object equal to it does not increase the size.
3. A newly created key with an equal value can be used to find or remove the stored key.
4. The second removal returns `false` because the element has already been removed.
5. `HashSet` permits `null`, but still holds at most one `null` element.
6. The loop uses `seen.add(value)` to detect the first encounter with each value.

The three `first encounter` lines appear in the iteration order of the **input list**. The program prints immediately when `add` returns `true`; it does not iterate over the `HashSet` to print the results. Therefore, that stdout does not mean `HashSet` preserves insertion order.

The `TaskId` record uses an immutable `String` component, making it suitable as a simple value key in the example. Do not assume that every record automatically has immutable components.

## 5. First condition: equals and hashCode must be correct and stable

### 5.1. Equal objects must have the same hash code

If you write a class where `equals` considers two task codes equal but `hashCode` produces two different results, the program has violated the object contract.

When that happens, a lookup may start in a different region from the one used during insertion. Increasing capacity, lowering the load factor, or adding `contains` before `remove` cannot fix this contract bug.

If you define `equals` yourself, you must design `hashCode` from the corresponding data at the same time. If you use an existing value type, you need to understand that type's equality rules.

### 5.2. Do not mutate identity data while the element is in the set

Suppose an object uses a `code` field to compute both `equals` and `hashCode`. After the object is added to the set, the program changes `code`.

From then on, the object's hash code and equality meaning may differ from when it was placed into the structure. Even if you still hold the exact object reference, you cannot deduce that `contains` or `remove` will behave as they would with a stable key.

The `Set` contract does not specify behavior when an element is modified in a way that affects equality comparisons while it is an element in the set. Do not use an incidental stdout on one JDK to turn this case into a rule you can rely on. [Set: mutable elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

Prefer immutable keys. If business logic requires changing an identifier, explicitly design a workflow to remove the old key before mutating and then add the new key, along with how to handle the case where the new key already exists. This is a sequence of operations that must be managed, not an "automatic bucket position update" that the set performs when a field changes.

### 5.3. Identity rules must match real-world data

A system might decide that `"TASK-1"` and `"task-1"` are the same code or two different codes. `HashSet<String>` does not automatically choose a case-insensitive business rule by default.

If normalization is needed, perform it according to a consistent rule at the value-creation boundary. Use the same canonical form when adding, finding, and removing. Avoid normalizing on only one side and then treating a not-found result as a performance issue.

Do not include display-only fields in the identity rule if they have no identity meaning. Conversely, do not omit an important field just to reduce hash computation cost; doing so can cause two values that need to be distinguished to be treated as one.

## 6. Second condition: hash codes must be properly distributed

### 6.1. Being contract-compliant is not enough to be fast

A `hashCode` function that always returns `7` still satisfies the requirement that "two equal objects must have the same hash code." However, every distinct object is also routed to the same hash region.

That function may be valid regarding the hash code contract, yet very poor in distribution. These are two different criteria:

| Criterion | Question to answer |
| --- | --- |
| Correctness | Do two equal values have the same hash code? |
| Distribution quality | Are distinct values in real data piling into too few buckets? |
| Computation cost | Are computing the hash code and checking equality expensive? |
| Stability | Does the relevant data stay unchanged while the object is in the set? |

A formula with many fields does not automatically guarantee good distribution. If real data concentrates on a few patterns that the formula handles poorly, it can still produce many collisions.

### 6.2. Increasing capacity cannot rescue a constant hash function

If all keys have the same hash code, creating more empty buckets does not automatically spread those keys evenly across those buckets. The cause lies in the hash information of the keys.

The `HashMap` documentation—the backing structure of `HashSet`—warns that many keys with the same `hashCode` degrade performance. It has mechanisms to help handle collisions in certain cases, but that is no reason to ignore hash quality. [HashMap: collisions and lookup cost](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Do not assume that every high-collision case is rescued into O(1), or that every `HashSet` on every JDK has the same O(log n) bound for all keys. The standard performance contract remains tied to the assumption of proper distribution.

The collision program later in this lesson uses keys with a constant hash code to prove that **the set still needs to distinguish equality correctly**. The program does not measure time and does not prove that hashing approach is fast enough for a large data volume.

### 6.3. Key cost does not disappear behind O(1) notation

Calling an operation O(1) in the number of elements `n` does not mean all internal work is free.

You can think of a call in terms of its components:

```text
operation cost
    = cost to compute the key's hashCode
    + cost to search within the candidate region
    + cost of necessary equals checks
    + cost of structural changes or allocation if any
```

This is a breakdown for analysis, not an exact timing formula.

If `hashCode` has to traverse a long structure proportional to key length `k`, or `equals` has to compare a lot of data, key length becomes a separate factor. Do not lump `n` and `k` together and conclude the operation is "always constant."

Avoid designing `hashCode`/`equals` with work unrelated to identity, such as network access or file reads. Identity methods should have stable semantics and controllable cost.

## 7. Third condition: understanding capacity, load factor, and resizing

### 7.1. Three distinct quantities

In the context of a hash table:

- `size` is the number of elements currently stored.
- `capacity` is the number of buckets in the backing table.
- `load factor` relates to how full the table is allowed to get before it resizes.

`size()` does not return capacity. Nor is the argument passed to `new HashSet<>(initialCapacity)` the maximum size the set is allowed to hold.

Java 17 has these common ways to construct one:

```java
Set<String> defaults = new HashSet<>();
Set<String> withHint = new HashSet<>(1_334);
Set<String> withLoadFactor = new HashSet<>(1_334, 0.75f);
```

All the variables above start as empty sets. The numbers in the constructors do not pre-populate any elements.

The default constructor of `HashSet` uses the backing table's default initial parameters of capacity `16` and load factor `0.75`. This does not mean the set can only hold 16 elements. [HashSet constructors in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

### 7.2. Resizing makes some insertions do more work

In the model described by the backing table documentation, when the number of entries exceeds the product of capacity and load factor, the table increases its capacity and rebuilds the corresponding storage structure. Because many existing elements must be reorganized, an insertion that triggers a resize can do more work than a typical insertion.

That is why we distinguish:

- **Expected under hash distribution:** the search region is small when keys are properly distributed.
- **Amortized over many insertions:** the cost of resize operations is spread out when analyzing a sequence of operations, rather than claiming every individual insertion is equally cheap.

The word "amortized" does not mean the program pays a fixed amount of time after every insertion; it is a way of analyzing the total work of a sequence of operations. If an application cares about the latency of individual requests, resize events still need to be considered.

The model example with capacity `16` and load factor `0.75` gives a threshold related to `16 × 0.75 = 12`. Do not turn this illustrative multiplication into an exact memory reading or a rule for every internal detail of all JDKs.

### 7.3. Estimating based on the number of distinct elements

If you know you will hold around `1_000` **distinct** elements, you can use the estimate:

```text
capacity hint ≈ ceil(expectedDistinct / loadFactor)

With expectedDistinct = 1_000 and loadFactor = 0.75:
    ceil(1_000 / 0.75) = 1_334
```

Therefore, in an example with a small, clear bound:

```java
int expectedDistinct = 1_000;
int capacityHint = (int) Math.ceil(expectedDistinct / 0.75d);

Set<Integer> values = new HashSet<>(capacityHint, 0.75f);
```

This is a hint value for the constructor, not a claim that the actual table has exactly `1_334` buckets, nor a way to measure allocated memory.

Do not use the cast expression above as-is as a general-purpose function for arbitrarily huge input values. For unbounded data, you also need to consider numeric ranges, capacity limits, and actual memory. In the illustrative program, the fixed number `1_000` is small enough for the calculation to be clear without overflow issues.

A set deduplicates, so the number of stored elements is determined by the number of distinct values, not the total number of records that pass through. One million records with only one thousand distinct codes is a different situation from one million distinct codes.

### 7.4. Load factor is a trade-off, not a "smaller is faster" knob

Lowering the load factor can make the table sparser but consumes more space. Raising the load factor can reduce relative space overhead but makes lookups heavier. The default `0.75` is the balanced choice described by the backing table documentation. [HashMap: capacity, load factor, and resizing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Do not pick an enormous capacity just to avoid any possibility of resizing. That can waste memory and affect full-set iteration. Nor should you tweak the load factor to compensate for a broken or poorly distributed `hashCode`.

Start from the standard configuration, the expected number of distinct elements, and the actual operation pattern. Only change the configuration once you have identified the associated benefits and costs.

## 8. Complete program: hash collisions and capacity hints

Save the code in **HashCollisionDemo.java**:

```java
import java.util.HashSet;
import java.util.Set;

public class HashCollisionDemo {
    private record DistributedKey(int id) {
    }

    private static final class CollisionKey {
        private final int id;

        private CollisionKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof CollisionKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    public static void main(String[] args) {
        Set<DistributedKey> distributed = new HashSet<>(128);
        Set<CollisionKey> colliding = new HashSet<>(128);
        for (int id = 0; id < 100; id++) {
            distributed.add(new DistributedKey(id));
            colliding.add(new CollisionKey(id));
        }

        System.out.println("distributed size: " + distributed.size());
        System.out.println("colliding size: " + colliding.size());
        System.out.println("distributed contains 40: "
                + distributed.contains(new DistributedKey(40)));
        System.out.println("colliding contains 40: "
                + colliding.contains(new CollisionKey(40)));
        System.out.println("colliding contains 999: "
                + colliding.contains(new CollisionKey(999)));
        System.out.println("colliding add duplicate: "
                + colliding.add(new CollisionKey(40)));
        System.out.println("colliding remove 40: "
                + colliding.remove(new CollisionKey(40)));
        System.out.println("colliding contains removed: "
                + colliding.contains(new CollisionKey(40)));
        System.out.println("colliding remaining: " + colliding.size());

        int expectedDistinct = 1_000;
        int capacityHint = (int) Math.ceil(expectedDistinct / 0.75d);
        Set<Integer> sized = new HashSet<>(capacityHint, 0.75f);
        for (int value = 0; value < expectedDistinct; value++) {
            sized.add(value);
        }
        System.out.println("capacity hint: " + capacityHint);
        System.out.println("sized count: " + sized.size());
        System.out.println("sized contains 999: " + sized.contains(999));
        System.out.println("sized remove 999: " + sized.remove(999));
        System.out.println("sized final count: " + sized.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 HashCollisionDemo.java
java HashCollisionDemo
```

Stdout:

```text
distributed size: 100
colliding size: 100
distributed contains 40: true
colliding contains 40: true
colliding contains 999: false
colliding add duplicate: false
colliding remove 40: true
colliding contains removed: false
colliding remaining: 99
capacity hint: 1334
sized count: 1000
sized contains 999: true
sized remove 999: true
sized final count: 999
```

The two key types in the program have the same identity meaning—the `id` field—but different hash code quality:

- `DistributedKey` is a record with only a single `int` component; for the sequence of codes in the example, it provides hash codes based on that component.
- `CollisionKey` deliberately returns the same number `7` for every code, even though `equals` still distinguishes different codes.

Both sets retain 100 elements. That proves collisions do not mean elements are treated as duplicates. Finding a present key, rejecting duplicate additions, removing, and checking after removal still behave correctly.

**There are no timing measurements in stdout.** You cannot use the fact that both sets have the same element count and the same query results to conclude they have the same performance.

The first two sets are created with a hint of `128`, but the program does not inspect or assert how many times they resize. A capacity parameter is not empirical proof of every allocation detail.

The final part computes a hint of `1_334` for `1_000` distinct elements, adds them, and checks a value. The number `1_000` printed is `size`; the number `1_334` printed is an input variable computed by the program. They are not two ways of reading the same property of the set.

Both programs in this lesson were compiled with `--release 17` and run to verify the exact stdout. This option checks the language/API level and generates Java 17-compatible bytecode; it does not mean the executing JVM itself is JDK 17.

## 9. Structuring workflows to benefit from hash sets

### 9.1. Multiple queries should reuse an already-built set

Suppose there are `n` valid codes and you need to check `m` input codes. If for every query you sequentially scan all valid codes, the number of checks can grow as `m × n`.

One approach is to build the hash set once, then reuse it for the queries:

```java
// Illustrative snippet; validIds and requests are existing input collections.
Set<String> allowed = new HashSet<>(validIds);

for (String requestId : requests) {
    if (allowed.contains(requestId)) {
        System.out.println("Mã hợp lệ: " + requestId);
    }
}
```

Assuming properly distributed hash codes and constant key cost, building and executing the queries can be analyzed as expected work close to O(n + m), instead of an O(mn) scanning algorithm.

However, if you recreate `new HashSet<>(validIds)` inside every query iteration, the program repeatedly pays the cost of building the set. The benefit of the data structure can be lost in how the workflow is structured.

You also need to account for extra memory and the lifetime of the set. Using a hash set for a single query over a very small input may not yield a noticeable benefit. Choose based on the number of queries and actual data scale.

### 9.2. Avoid unnecessary repeated lookups

| Requirement | Direct way to write it |
| --- | --- |
| Process only the first encounter of a value | Use the return value of `add` |
| Remove only if present and know whether it changed | Use the return value of `remove` |
| Only check without modifying the set | Use `contains` |
| Retrieve the stored object by key | Revisit the data model; `contains` does not return the object |

If you need to map from a code to associated data, a `Map` may express the need better than repeatedly searching manually in a `Set`. That decision comes from data access requirements, not just from the name of the structure.

### 9.3. Avoid letting a set grow indefinitely beyond requirements

A "seen" set needs a clear scope: within a data batch, a processing session, or the entire process.

If the problem only needs deduplication within a batch, but the set is kept across infinite batches, the number of distinct elements and memory continue to grow. In that case, the issue is not just choosing the initial capacity. You need to define when data expires and is evicted according to requirements.

Do not delete arbitrarily just to save memory if deletion breaks the meaning of "already processed." Data lifecycle is part of the problem design.

## 10. Full iteration cost differs from single-element lookup cost

`contains(x)` leverages hashing to narrow the search area. A `for-each` loop walking the entire set does not have the same work model.

For `HashSet`, the documentation describes iteration time as proportional to the sum of **size + capacity** of the backing table. Therefore, a very sparse set can make iteration less efficient than predicted from `size()` alone. [HashSet: iteration cost](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

This explains why allocating an overly large capacity or choosing too low a load factor can be unsuitable when a program frequently iterates over the entire set.

If requirements call for preserving insertion order and frequent iteration, `LinkedHashSet` is an option to consider: it maintains links for iteration order, has its own memory overhead, and iteration is proportional to the number of elements rather than capacity according to the class documentation. It still relies on hashing for membership operations and still requires proper `equals`/`hashCode` rules. [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

Do not swap structures just to make an example's output "prettier" and then conclude it is the fastest choice for every workload. You need to know whether the program mainly checks membership, adds/removes, or iterates over the whole set.

When you need to remove while iterating over a `HashSet`, use a supported mechanism such as `Iterator.remove` or an appropriate filtering operation. Do not `for-each` while calling `set.remove` yourself and rely on "it didn't throw an exception this time." This is about iteration correctness, not hash optimization.

## 11. Verifying correctness and evaluating performance are two different tasks

The programs in this lesson verify behaviors such as adding duplicates, finding by equal key, removing, and handling collisions. They are not performance measurements.

A meaningful measurement needs to define a specific question, such as:

- How does `contains` for a present key differ from an absent key?
- How does `add` for a new element differ from `add` for an existing value?
- As elements grow from one thousand to more, how does the cost change?
- Is the workload mostly lookups or does it frequently trigger resizing?
- Do the hash codes of representative data distribute properly?
- Do key length and structure change with scale?

Do not measure time by placing `println` inside the section you want to compare and treating that as the time of `contains` alone. The work of printing output becomes part of the measurement.

Also avoid measuring `add` repeatedly with the same value and then describing the result as the cost of adding many new elements. After the first call, the workload has changed to attempting duplicate insertions. For `remove`, if you do not re-prepare the data, after one removal the subsequent calls may just be removing an absent value.

When you need a small, controlled benchmark on the JVM, you can use [OpenJDK JMH](https://github.com/openjdk/jmh) and read its accompanying samples. The tool helps build, run, and analyze measurements; you still have to design the data and operations to match the question you want to answer.

A results report should state at minimum the JDK version, set configuration, data scale and shape, operation type, hit/miss ratio, and how data preparation is separated from the measured operation. Do not turn a single number on one machine into a timing guaranteed by the API.

## 12. Common mistakes when expecting HashSet to be fast

| Symptom or assumption | What to check | How to address |
| --- | --- | --- |
| Finding/removing with an equal-value object does not work as expected | Are equals/hashCode correct and consistent? | Fix the identity contract first |
| Mutating a code field then unable to find it reliably | Did the key change while in the set? | Use immutable identifiers or an explicit update workflow |
| Set has many keys but all hashCodes are the same | Poor hash distribution | Design a hash code suited to the data |
| Increasing capacity a lot yet collisions remain concentrated | Is hashCode constant or taking too few values? | Do not use capacity to mask a distribution bug |
| Some add calls are much slower | Is resizing or allocation happening? | Check configuration and workload characteristics; distinguish per-call from amortized |
| Thinking new HashSet(1000) can only hold 1000 elements | Confusing capacity hint with element count limit | Separate size, capacity, and resize threshold |
| Set has few elements yet iteration is expensive | Is capacity too large relative to size? | Reconsider configuration and iteration pattern |
| Always calling contains before add/remove | Repeating the search work | Use the return flag of the mutating operation |
| Seeing stdout in the same order and assuming HashSet preserves insertion order | Relying on an unguaranteed observation | Choose a structure with an ordering contract when needed |
| One fast measurement leading to concluding all operations are O(1) | Did it measure the right operation and representative data? | Separate correctness, measurement, and complexity analysis |
| Used add directly and assumed it is safe for concurrent thread writes | Confusing fewer calls with synchronization | Design appropriate concurrent access |

If performance is not as expected, first confirm the data is correct. Only then inspect hash distribution, key cost, resizing, how often the set is rebuilt, and the actual operation pattern. Tuning a parameter without knowing what work is taking time usually does not solve the root cause.

## 13. Self-practice and verification

### Exercise 1: trace results and size

With a newly created `HashSet<String>`, execute:

```java
set.add("a");
set.add(new String("a"));
set.contains("a");
set.remove("a");
set.remove("a");
```

Check:

| Operation | Result | size after operation |
| --- | --- | --- |
| `add("a")` | `true` | 1 |
| `add(new String("a"))` | `false` | 1 |
| `contains("a")` | `true` | 1 |
| `remove("a")` | `true` | 0 |
| `remove("a")` | `false` | 0 |

Explain why a `new` call does not create a new element in the set when two strings are equal by value.

### Exercise 2: correctness or hash quality?

A key class has `equals` properly based on code and `hashCode` always returns `0`.

1. Does it necessarily violate the "equal objects must have the same hash code" condition?
2. Are distinct keys necessarily deduplicated away?
3. Can you rely on that hash function to expect good distribution?
4. Does increasing initial capacity automatically fix all keys having the same hash code?

Check: it does not necessarily violate that condition; distinct keys are still distinguished by `equals`; distribution is very poor; increasing capacity does not automatically create distinguishing information in the hash code.

### Exercise 3: capacity estimation

You expect to hold `750` distinct elements with a load factor of `0.75`. Using the estimation formula in the lesson, the hint value is:

```text
ceil(750 / 0.75) = 1_000
```

State two things that cannot be concluded from that number.

Hint: you cannot say the set already has 1,000 elements, nor can you say the actual table definitely has exactly 1,000 buckets. This is a configuration input, not an observation of internal structure.

If there are 50,000 records but only 750 distinct codes, explain why the number of distinct values is what directly relates to the number of elements the set holds.

### Exercise 4: fix a benchmark asking the wrong question

A loop calls `set.add("java")` one million times and then reports "measured adding one million elements."

What is wrong: if the set did not initially contain that string, only the first call adds a new element. All remaining calls attempt to add an existing value.

To measure adding new elements, you need to prepare data with distinct values and control the set state for each measurement. To measure adding duplicates, you can use existing data, but you must describe that workload accurately. Data preparation, resizing, and the measured work must be separated according to the question being answered.

## 14. Reference documentation

- [Java 17 HashSet — operations, performance, ordering, null, and constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- [Java 17 HashMap — backing structure, capacity, load factor, and collisions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [Object — equals/hashCode contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [Set — limitations when elements change equality](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)
- [LinkedHashSet — ordering and iteration cost trade-offs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- [OpenJDK JMH — tool for building JVM benchmarks](https://github.com/openjdk/jmh)
