# Collisions, Bucket Treeification, and the Limits of Implementation Details

## 1. Why Does a HashMap Need to Handle Multiple Keys in the Same Bucket?

A HashMap has a finite number of buckets, whereas an application can insert a very large number of keys. Multiple keys can be routed to the same bucket. That is a **collision**, a normal situation that the data structure must handle.

If a bucket only has a few mappings, a simple chain of nodes can handle it well. If very many keys pile into the same bucket, having to check many consecutive candidates can slow down lookups.

In modern OpenJDK implementations, a crowded bucket can be converted into a balanced tree structure, called **bucket treeification**. This mechanism helps cope with certain high-collision scenarios.

Two layers of knowledge should be kept separate:

| Layer | What to Rely On |
| --- | --- |
| Public contract | Unique keys by equality, accurate put/get/remove mappings, null policy, and iteration order |
| Implementation details | List-based or tree-based buckets, conversion thresholds, node layout, and internal algorithms |

This lesson explains the treeification mechanism and how to observe it, while pointing out what must not be turned into assumptions in application code.

## 2. A Collision Does Not Mean Two Keys Are Equal

### 2.1. Same Hash and Same Bucket Are Two Different Levels

In the OpenJDK 17u model, a hash after the mixing step is used with the table length `n` to select an index:

```java
int index = (n - 1) & hash;
```

This is an expression explaining the internal mechanism, not an API that callers of HashMap must compute themselves.

With `n` equal to 64:

```text
63 & 1  = 1
63 & 65 = 1
```

Two different hashes still land in the same bucket. If the table grows to 128:

```text
127 & 1  = 1
127 & 65 = 65
```

they can split into two buckets.

Conversely, if multiple keys return the same `hashCode` and have the same post-mixing hash, increasing the number of buckets will not automatically make those hashes different. They still follow the same index-selection path.

### 2.2. Equals Still Determines the Same Logical Key

Two keys with the same hash but `equals` returning `false` must still keep separate mappings. Calling `put` with a key equal to an existing key updates the mapping; calling `put` with a different key in the same bucket adds another mapping.

Treeification does not change this rule. It changes how candidates are organized inside the bucket, not turning a HashMap into a deduplicating structure based on a new criterion.

The public properties of the class can be checked against [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

## 3. From a Node Chain to a Balanced Tree

### 3.1. List-Based Bucket

A simple mental model:

```text
table[index]
     ↓
   node A → node B → node C → ... → node M
```

If we need to find a key near the end or prove a key is absent, the structure may have to inspect many nodes in the group. With `m` candidates in a bucket, a linear search can cost O(m).

The length of a single bucket is different from the total number of mappings in the entire map. A map can have many nearly empty buckets while one bucket is very crowded due to a poorly distributed hash function.

### 3.2. Tree-Based Bucket

OpenJDK uses a red-black tree for tree bins. This is a type of self-balancing search tree that keeps height logarithmic instead of letting a chain grow arbitrarily long.

Conceptual diagram:

```text
table[index]
     ↓
   a root node
      /    \
  branch  branch
    / \    / \
   ...    ...
```

This diagram does not depict a mandatory layout for specific keys. The implementation also retains links for other operations such as bucket traversal; it does not discard all old node links and expose a new tree API to the caller.

A tree node has more links and balancing metadata than a regular node. Therefore, treeification has memory and structural maintenance overhead; there is no reason to use a tree for every bucket that only has one or two elements.

### 3.3. This Is an Implementation Optimization, Not a New Map Type

The Java 8 enhancements introduced the use of balanced trees when many keys collide. Historical documentation also emphasizes that HashMap iteration order is not guaranteed; see [OpenJDK's Collections Framework Enhancements in Java SE 8](https://cr.openjdk.org/~naoto/idna2008/docs_www/technotes/guides/collections/changes8.html).

Callers still use HashMap with the same `put`/`get`/`remove` operations. There is no requirement to change business code to a `TreeBucket` class or to manually maintain node colors.

## 4. The Three Constants 8, 6, and 64 Must Be Read in Context

In the OpenJDK 17u source code:

| Constant | Value | Role |
| --- | --- | --- |
| TREEIFY_THRESHOLD | 8 | Participates in deciding whether to convert a crowded bucket to a tree on insertion |
| UNTREEIFY_THRESHOLD | 6 | Threshold for converting a split group back to regular nodes on the resize path |
| MIN_TREEIFY_CAPACITY | 64 | Minimum table length to treeify via the `treeifyBin` path |

Refer to [OpenJDK 17u's HashMap.java](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java).

These numbers are not public constants on the `Map` interface or a numerical guarantee of Java SE for all versions. They are a starting point for reading a specific implementation.

### 4.1. 64 Is the Table's Bucket Count, Not a Required Size

A map can have only nine mappings while its table already has 64 buckets due to the initial capacity choice. When those mappings all pile into one bucket, the table length condition may already be met.

Conversely, do not assume "there must be at least 64 entries in the map before treeification can happen." That confuses capacity with size.

Initializing a HashMap with a capacity also does not mean the constructor immediately exposes an accessible array. Allocation and capacity rounding are implementation details; the example only uses the parameter to set up conditions for the experiment.

### 4.2. A Small Table Can Be Resized Instead of Treeified

In the `treeifyBin` path of OpenJDK 17u, if the table length is less than 64, the implementation calls `resize` instead of building a tree for that bucket.

The sound mechanical reason is: many different hashes colliding because the table is still small can be separated once the table gains more index bits. Growing the table is a way to handle it before paying the cost of tree nodes.

For keys with completely identical hashes, resizing cannot disperse that group. Once the table is large enough and the group continues to grow crowded, treeification can still occur.

### 4.3. Do Not Memorize "Putting the 8th Element Always Treeifies"

`TREEIFY_THRESHOLD` being 8 is no substitute for reading where it is used.

In the regular `putVal` path of OpenJDK 17u, the conversion check happens when adding a new node to an existing chain. For a bucket that already has eight nodes, the next `put` of a different key can trigger the treeify path. Other update paths also have their own counting logic and check timing.

Therefore, you must specify enough context: which implementation, which operation path, whether the node count is before or after insertion, and what the table length is. Do not use a memorized rule of thumb that skips those conditions.

## 5. Experiment Observing Node and TreeNode

### 5.1. How to Observe and Limitations

The following program uses keys with a constant `hashCode` to force collisions. The key implements `Comparable` by `id`, consistent with the record's equality.

It retrieves a `Map.Entry` through the iteration API and prints the actual runtime class name using `getClass().getSimpleName()`. The `Node`/`TreeNode` names are observed implementation details, not public types that business code should inspect to make control-flow decisions.

The program does not access private fields of `HashMap`, nor does it need reflection opening modules or package-opening flags. Even so, being able to print the class name does not turn that class name into a stable contract.

Save as **BucketTreeObservation.java**:

```java
import java.util.HashMap;
import java.util.Map;

public class BucketTreeObservation {
    record Key(int id) implements Comparable<Key> {
        @Override
        public int hashCode() {
            return 7;
        }

        @Override
        public int compareTo(Key other) {
            return Integer.compare(id, other.id);
        }
    }

    private static String observedEntryClass(Map<Key, Integer> map) {
        return map.entrySet().iterator().next().getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Map<Key, Integer> largeStart = new HashMap<>(64);
        for (int id = 1; id <= 7; id++) {
            largeStart.put(new Key(id), id * 10);
        }
        System.out.println("observed start-64 after 7: " + observedEntryClass(largeStart));
        largeStart.put(new Key(8), 80);
        System.out.println("observed start-64 after 8: " + observedEntryClass(largeStart));
        largeStart.put(new Key(9), 90);
        System.out.println("observed start-64 after 9: " + observedEntryClass(largeStart));
        System.out.println("get equal key 5: " + largeStart.get(new Key(5)));
        System.out.println("replace equal key 5 old: " + largeStart.put(new Key(5), 500));
        System.out.println("size after replacement: " + largeStart.size());
        System.out.println("remove equal key 5: " + largeStart.remove(new Key(5)));
        System.out.println("key 6 preserved: " + largeStart.get(new Key(6)));

        Map<Key, Integer> smallStart = new HashMap<>(16);
        for (int id = 1; id <= 9; id++) {
            smallStart.put(new Key(id), id);
        }
        System.out.println("observed start-16 after 9: " + observedEntryClass(smallStart));
        smallStart.put(new Key(10), 10);
        System.out.println("observed start-16 after 10: " + observedEntryClass(smallStart));
        smallStart.put(new Key(11), 11);
        System.out.println("observed start-16 after 11: " + observedEntryClass(smallStart));
        System.out.println("small-start size: " + smallStart.size());
        System.out.println("small-start get 11: " + smallStart.get(new Key(11)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BucketTreeObservation.java
java BucketTreeObservation
```

The programs in this lesson were compiled with `--release 17` and run on OpenJDK 24.0.2. Observed stdout:

```text
observed start-64 after 7: Node
observed start-64 after 8: Node
observed start-64 after 9: TreeNode
get equal key 5: 50
replace equal key 5 old: 50
size after replacement: 9
remove equal key 5: 500
key 6 preserved: 60
observed start-16 after 9: Node
observed start-16 after 10: Node
observed start-16 after 11: TreeNode
small-start size: 11
small-start get 11: 11
```

**The `observed` lines record the behavior of the stated environment's implementation, not a class-transition sequence that every Java 17+ runtime must guarantee.** The `--release 17` flag checks the target language/API and generates corresponding bytecode; the JVM running the program is still version 24.0.2.

### 5.2. Reading the Results by Operation Path

With a starting capacity of 64, in the `put` experiment:

- After seven and eight colliding keys, the observed entry is still `Node`.
- After the ninth key, the observed entry is `TreeNode`.
- `get`, updating with an equivalent key, and `remove` still preserve the correct Map semantics.

With a smaller starting capacity, after nine and ten keys `Node` is still observed; only after eleven is `TreeNode` observed. The result aligns with the small-table handling path prioritizing table growth before creating a tree.

From a single printed class name alone, you cannot conclude all internal capacity parameters. Explaining the resize path requires checking the implementation's source code; the program does not provide an API to inspect capacity.

Do not use those `observed` lines as compatibility tests for production. Business outcomes such as `size`, `get`, and `remove` belong to the contract that must hold even when internal structures change.

## 6. Treeification Does Not Turn HashMap into TreeMap

A tree bin is a single group within a hash table. It does not create an ascending order for the entire map.

| Question | HashMap with Tree Bins |
| --- | --- |
| Must the iterator traverse keys in ascending order? | No such guarantee |
| Are there public `floorKey`/`ceilingKey` APIs because there is a tree? | No |
| Can you pass a `Comparator` via a HashMap constructor to control the tree? | No |
| Does `compareTo` returning 0 automatically deduplicate keys that are not `equals`? | Does not change HashMap's key-identity contract |
| Do `put`/`get`/`remove` by equivalent key still work properly? | Must still work when keys follow the contract |

In tree bin lookups, the hash is still important information for choosing a direction. When hashes are equal, the implementation may use a suitable `Comparable` form of the key to help distinguish branches.

Callers do not need to pick an internal comparator for HashMap. Nor should `compareTo` be turned into a replacement for `equals` for logical key equality.

If you need key-order queries or range queries as an application feature, choose a `Map` with a public contract that meets that requirement. A bucket incidentally converting into a tree does not add those features.

## 7. Limits of the Statement "A Tree Always Searches in O(log n)"

### 7.1. Tree Height and Total Search Work Are Not the Same Thing

A balanced tree bounds height. If each search step can determine the appropriate branch, searching `m` nodes can follow a path of length O(log m).

However, in a tree bin, multiple keys can have the same hash and lack a useful `Comparable` relationship to distinguish them. OpenJDK's tree search source code has a path that must search the other branch as well when it cannot pick a direction with enough information.

Therefore, do not state unconditionally: "Since Java 8, every `get` on a HashMap in the worst case is O(log n), regardless of key type and hash function."

In particular, having the same hash and being incomparable can force a lookup for an absent key to inspect many nodes. The red-black tree remains balanced, yet the total number of nodes visited is not necessarily just a single root-to-leaf path.

### 7.2. Comparable Helps the Structure, Not Broken Keys

If keys have a suitable natural ordering, the implementation can use it to handle duplicate-hash cases. The experiment program uses `Comparable<Key>` by `id` for a consistent and readable model.

An `equals`/`hashCode` contract violation, or a key whose identifying information is mutated after `put`, can still cause lookups to behave unexpectedly. Treeification does not automatically fix that problem.

### 7.3. A Good Hash Function Still Matters

Well-distributed hash codes help prevent large numbers of keys from piling into a single bucket. Treeification is a mitigation mechanism under certain conditions, not a reason to intentionally return the same `hashCode` for every key in an application.

An expensive `hashCode`/`equals`/`compareTo` also increases actual cost. When analyzing average O(1) or O(log m), you must keep in mind the assumption about the cost of comparisons.

The HashMap documentation only describes constant-time performance for basic operations under the condition of an appropriately distributed hash function. Do not drop that condition when interpreting it.

## 8. When Does a Bucket Return to Regular Form?

### 8.1. Resize Can Split One Group into Two Smaller Groups

When a table grows from 64 to 128, different hashes that previously shared the same old index can diverge to two new indices. In the hash 1 and 65 model:

```text
Before: bucket 1 of table 64
        ├─ four keys with hash 1
        └─ five keys with hash 65

After:  bucket 1  of table 128: four keys with hash 1
        bucket 65 of table 128: five keys with hash 65
```

In OpenJDK 17u's tree bin `split` path, small groups whose node count does not exceed `UNTREEIFY_THRESHOLD` can be converted back to regular nodes.

This is a sound reason to use different entry and exit thresholds: not every small fluctuation should pay the cost of converting the structure back and forth.

### 8.2. Do Not Apply "Deleting Down to 6 Always Becomes a List" to Every Removal Path

The `UNTREEIFY_THRESHOLD` constant of 6 is used in the split path during resize. The `removeTreeNode` path also has checks based on tree shape and how the operation proceeds.

Do not turn the three numbers 8/6/64 into a simplistic state machine that only looks at size. You must look at which method uses them.

An implementation may convert the form due to resize, due to a group becoming small after deletion, or keep the form in other cases. This is not an application policy to control via a fixed entry count.

### 8.3. Conversion Must Not Lose Valid Mappings

Even when nodes change representation, the remaining keys and values must preserve their lookup semantics. Correctness tests should verify that mappings are preserved, rather than asserting a specific node type.

## 9. Experiment Splitting a Tree Bin on Table Growth

Save as **BucketSplitObservation.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class BucketSplitObservation {
    record Key(int id, int rawHash) implements Comparable<Key> {
        @Override
        public int hashCode() {
            return rawHash;
        }

        @Override
        public int compareTo(Key other) {
            int byHash = Integer.compare(rawHash, other.rawHash);
            return byHash != 0 ? byHash : Integer.compare(id, other.id);
        }
    }

    private static String observedEntryClass(Map<Key, Integer> map, Key key) {
        for (Map.Entry<Key, Integer> entry : map.entrySet()) {
            if (entry.getKey().equals(key)) {
                return entry.getClass().getSimpleName();
            }
        }
        return "missing";
    }

    public static void main(String[] args) {
        Map<Key, Integer> map = new HashMap<>(64);
        List<Key> original = new ArrayList<>();
        for (int id = 0; id < 9; id++) {
            Key key = new Key(id, id < 4 ? 1 : 65);
            original.add(key);
            map.put(key, id);
        }

        Key low = new Key(2, 1);
        Key high = new Key(7, 65);
        System.out.println("before growth size: " + map.size());
        System.out.println("observed low entry before: " + observedEntryClass(map, low));
        System.out.println("observed high entry before: " + observedEntryClass(map, high));

        for (int rawHash = 2; rawHash <= 41; rawHash++) {
            map.put(new Key(100 + rawHash, rawHash), 100 + rawHash);
        }

        System.out.println("after growth size: " + map.size());
        System.out.println("observed low entry after: " + observedEntryClass(map, low));
        System.out.println("observed high entry after: " + observedEntryClass(map, high));

        boolean preserved = true;
        for (Key key : original) {
            preserved &= Integer.valueOf(key.id()).equals(map.get(new Key(key.id(), key.rawHash())));
        }
        System.out.println("original mappings preserved: " + preserved);
        System.out.println("get low key: " + map.get(low));
        System.out.println("get high key: " + map.get(high));
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 BucketSplitObservation.java
java BucketSplitObservation
```

Observed stdout in the same environment:

```text
before growth size: 9
observed low entry before: TreeNode
observed high entry before: TreeNode
after growth size: 49
observed low entry after: Node
observed high entry after: Node
original mappings preserved: true
get low key: 2
get high key: 7
```

The first nine keys consist of four keys returning hash 1 and five keys returning hash 65. For these small values, the mixing step of the referenced implementation does not alter those two hashes; when the table has 64 buckets, both groups land at index 1.

The keys added afterward use hashes from 2 to 41, which do not pile into that initial bucket in the model under consideration. They increase the total entry count from 9 to 49. With this implementation and experiment setup, the table-growth path leads to splitting the group; the observed original entries transition from `TreeNode` to `Node`.

Again, the class name and transition timing are observed results, not a structure-inspection API. The `original mappings preserved` check along with the `get` calls demonstrate what matters to calling code: the original data can still be found using equivalent keys.

The program iterates over `entrySet` to find the entry to observe. It does not rely on HashMap iteration order, because that order is not guaranteed.

## 10. Things That Should Not Be Put into an Application's Contract

### 10.1. Do Not Branch Business Logic on Node Class Names

Names like `HashMap$Node` or `HashMap$TreeNode`, which extra color or link fields an entry has, and the root structure of the tree are internal.

Code like "if the entry is a `TreeNode`, choose a different validation path" turns a memory optimization into a business condition. It can break on a JDK upgrade even while public `Map` operations still work properly.

There is no need to read private fields of `HashMap` or open internal packages to use `Map` correctly.

### 10.2. Do Not Rely on Iterator Order

HashMap does not guarantee iteration order. Resizing or structural changes can alter the observed order; an order that looks stable on small data does not become a guarantee.

If the output requires an order, express that requirement with a data structure or processing step that has an explicit ordering contract.

### 10.3. Do Not Use Thresholds to Guess Performance Without Examining Data

Knowing the threshold 8 does not tell you whether a program will be fast or slow at the ninth entry. There are also hash distribution, bucket count, `equals`/`compareTo`, operation path type, allocation, and many other factors.

Do not infer runtime from a very short measurement or from the fact that the entry class changed its name. When performance is a real requirement, use measurements suited to representative data and environments.

### 10.4. Do Not Treat Treeification as a Synchronization Mechanism

HashMap does not become safe for concurrent modifications by multiple threads just because a bucket has become a tree. Concurrent data structures and synchronization mechanisms are an independent requirement.

Also, do not use `ConcurrentModificationException` as proof that every invalid access is detected. It is a best-effort bug-detection mechanism, not a synchronization guarantee.

## 11. How to Read Implementation Source While Keeping the Right Mental Model

A useful reading sequence:

1. Read the public contract of `HashMap` and `Map`.
2. Look at `hash`/index calculation to see how multiple keys can land in the same region.
3. Look at `putVal` and `treeifyBin` to see when a conversion is proposed.
4. Look at `TreeNode.find` to understand branch-selection conditions.
5. Look at `split` and `removeTreeNode` to understand paths back to regular form.
6. Verify data through the public API; use internal diagnostics only to learn the mechanism.

State the source version explicitly when explaining. "OpenJDK 17u source has this constant" is more accurate than "Java always does this."

Source on update branches can also change over time. When needing to reproduce a performance investigation, record the JDK version, source version, or relevant commit rather than just a language name.

Do not copy a conditional snippet out of context: a threshold might count nodes before insertion; another path might use a different counter; a capacity condition might divert the operation to `resize`.

## 12. What Outcomes Should Tests Protect?

Durable properties to test:

- Multiple distinct keys with the same hash still retain all entries.
- Calling `put` with an equivalent key replaces the value properly without increasing the number of logical keys.
- Calling `get` and `remove` with an equivalent key instance remains accurate before and after many insertions.
- Keys in other buckets are unaffected by deletions in a colliding group.
- `null` and return values are handled according to the specific map class.
- Calling code does not assume HashMap iterator order.

These key-correctness tests remain valid even if the implementation changes thresholds or bucket organization.

Conversely, a test demanding "the ninth entry must have class name `TreeNode`" belongs to an implementation experiment with a fixed environment. Do not use it as a requirement for a library that only commits to using the `Map` API.

You can keep both kinds of checks in a learning exercise, but you must set clear goals: one verifies the data contract; the other records the mechanism of a specific environment.

## 13. Common Mistakes and How to Fix Them

| Reasoning Error | What Was Overlooked | Appropriate Understanding |
| --- | --- | --- |
| Same hash means the later key overwrites the earlier key | `equals` still identifies keys | Valid collisions do not merge distinct keys |
| Eight entries always form a tree | Counting path, capacity, and operation | Read the condition where the threshold is used |
| Must have 64 entries to treeify | 64 is the table length | Distinguish `size` from `capacity` |
| Small tables with many collisions always build a tree | There is a resize path first | Check `MIN_TREEIFY_CAPACITY` |
| Having a tree bin means HashMap is sorted | The tree is only a single bucket's structure | No map-wide ordering contract |
| Balanced tree means every lookup is definitely O(log n) | Some search branches cannot be distinguished by order | Consider hash and suitable `Comparable` |
| Deleting down to six always reverts to a list | The `remove` path differs from `split` | Do not use one threshold to represent the whole mechanism |
| Treeification fixes mutated keys | Key contract is still broken | Keep key identity stable |
| `Node` name is a public API | It is a runtime implementation class name | Use only for observation, not business logic |
| Treeification makes HashMap thread-safe | No new synchronization guarantee | Choose an appropriate concurrent structure/synchronization separately |

## 14. Self-Check Exercises with Solutions

### Exercise 1: Two Levels of Collision

Do post-mixing hashes 1 and 65 land in the same bucket when the table length is 64? What about when the table length is 128?

**Solution:** at 64, both go to bucket 1. At 128, they go to 1 and 65. Collisions caused by the mask of a small table can be separated when the table grows.

### Exercise 2: Completely Identical Hashes

Twenty distinct keys all have the same valid `hashCode`. Does growing the table guarantee splitting them into multiple buckets?

**Solution:** no. Identical post-mixing hashes still produce the same index with the same mask. Resizing does not create differences between equal hashes.

### Exercise 3: Meaning of 64

A map has nine entries but already has a sufficiently large table. Is it a contradiction if its bucket gets treeified?

**Solution:** no. The condition 64 refers to the table length in the referenced implementation path, not that the map must have 64 entries.

### Exercise 4: Threshold 8

A `put` observation sees `Node` after eight keys and `TreeNode` after nine keys. Does that contradict `TREEIFY_THRESHOLD` being 8?

**Solution:** no. You must check how many nodes are in the chain when the threshold is checked upon insertion and how the counter variable is used. A single number alone does not fully describe the transition timing.

### Exercise 5: Ordering

A bucket is a red-black tree. Can you use a `for` loop over the HashMap to retrieve keys in ascending order?

**Solution:** no. A tree bin does not create an ordered key-iteration contract for the whole map.

### Exercise 6: Searching for a Missing Key

A group has many keys with the same hash and no useful `Comparable` ordering. Does a balanced tree guarantee that searching for a missing key only visits a single O(log m) path?

**Solution:** you cannot assert that. The implementation's search path may need to search additional branches when it cannot determine a direction. Balanced height does not mean every search visits only one branch.

### Exercise 7: Splitting a Group

A tree bin splits into a group of four nodes and a group of five nodes during an OpenJDK 17u resize. Can they revert to regular nodes?

**Solution:** yes, via the `split` path with `UNTREEIFY_THRESHOLD`. This does not create a rule that every deletion down to six nodes under all circumstances must change representation.

### Exercise 8: JDK Upgrade Testing

Another JDK version does not print the same entry names as the experiment, yet `put`/`get`/`remove` with valid keys still preserve data. Is that enough to conclude the JDK violates `Map`?

**Solution:** no. Entry class names and treeification timing are not part of the `Map` guarantee. You must evaluate the public properties that applications are permitted to rely on.

## 15. References

- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): class contract, conditional performance, and unguaranteed order.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): mapping semantics and limitations with mutable keys.
- [OpenJDK 17u HashMap.java](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java): `treeifyBin`, `TreeNode.find`, `split`, `removeTreeNode`, and constants.
- [OpenJDK Collections Framework Enhancements in Java SE 8](https://cr.openjdk.org/~naoto/idna2008/docs_www/technotes/guides/collections/changes8.html): context for collision bucket improvements.

Treeification is a way to reorganize buckets to improve collision handling in a specific implementation. Understanding it helps with explanation and diagnosis, while code using `HashMap` should continue to rely on the mapping contract, proper key rules, and explicitly expressed ordering/concurrency requirements.
