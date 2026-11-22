# Balanced Search Trees and Operation Costs

## 1. What Problem Does TreeMap Solve?

A program stores timestamps along with the data for each timestamp. It needs to find an exact timestamp, but it also needs to know the closest preceding timestamp, the next timestamp, and the timestamps that fall within a range.

If you only need key-based mapping, a hash table is a familiar choice. When you need **key ordering and the ability to navigate according to that order**, an ordered search structure becomes useful.

TreeMap organizes mappings using a balanced search tree. In Java, this class is based on a red-black tree and implements NavigableMap.

Two ideas need to be tied together:

- **Binary search by key order** eliminates a portion of candidates after each comparison.
- **Keeping the tree height bounded** prevents the search path from stretching into a linear chain.

The [Java 17 TreeMap documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) guarantees log(n) cost for containsKey, get, put, and remove. To apply that statement accurately, you need to understand that n is the number of mappings, comparisons have their own cost, and not every method of the class has the same complexity.

## 2. Binary Search Tree: Each Node Helps Choose a Direction

A node holds a key, a value, and structural links. In the standard ascending-order model:

- Keys in the left subtree are smaller than the current node's key.
- Keys in the right subtree are larger than the current node's key.
- A comparison result of 0 identifies the same key position according to the TreeMap's ordering.

"Smaller" and "larger" here are according to compareTo or the chosen Comparator, not necessarily ascending numerical order.

Illustration:

```text
             40
           /    \
         20      60
        /  \    /  \
       10  30  50  70
```

To find 50 in natural numerical order:

1. Compare with 40: larger, go right.
2. Compare with 60: smaller, go left.
3. Compare with 50: equal, mapping found.

There is no need to check every key 10, 20, 30, 40, 50 in a linear list scan.

The diagram is a search tree model to explain the path, **not a guarantee that a TreeMap after a specific sequence of puts must have the exact same root, colors, and shape as shown**.

### 2.1. An Ordered Tree Does Not Need to Re-Sort Everything After Each get

The structure is already organized by the comparison relation. Get follows the links to find the position, rather than creating a new list and sorting it every time.

Similarly, an in-order traversal can walk left–node–right over the existing structure. Ordering is a property of how the tree is organized.

### 2.2. Insertion Order and Traversal Order Are Two Different Things

Adding 40, 20, 60, 10 does not mean TreeMap traverses in that exact insertion order.

Traversal follows the map's key order. If the Comparator reverses the order, the "left/right" direction according to the comparison also serves that reversed order.

You do not need to know node colors or the current root to use the class's ordering contract.

## 3. Why Is a Plain Search Tree Not Enough?

If you only add nodes according to the search rule without balancing, an increasing sequence of keys can form a chain:

```text
1
 \
  2
   \
    3
     \
      4
       \
        5
```

Finding the last key requires walking almost the entire chain. Even though every node still obeys the search rule, the height has grown to the order of n, so a single lookup can be O(n).

The problem is not that the key sequence is invalid. The structure needs a way to maintain a suitable shape regardless of the order in which data arrives.

### 3.1. Height Determines the Length of a Search Path

Let h be the height under a consistent convention. A single search from the root only visits a number of nodes proportional to h + 1.

If h = O(log n), that path is logarithmically short. If h = O(n), having two left/right links per node does not help much on its own.

This is the relationship to keep in mind: **balance → bounded height → bounded search path**.

### 3.2. Balance Does Not Mean Every Level Must Be Full

A tree does not need to have all 2, 4, 8, ... nodes at every level to still have O(log n) height.

TreeMap is not a perfect binary tree, does not require both subtrees of every node to have the exact same number of elements, and does not need a full array to represent its shape.

The balancing conditions are designed to be strong enough to bound the height while remaining maintainable during insertions and deletions.

## 4. Red-Black Trees Bound Height Using Invariants

In the standard model:

1. Every node is colored either red or black.
2. The root is black; NIL leaves are conventionally black.
3. A red node cannot have a red child.
4. All paths from a given node to its descendant NIL leaves contain the same number of black nodes.

With n data nodes, these conditions lead to h ≤ 2 log₂(n + 1) under the standard height convention. Counting nodes instead of edges may differ by a constant.

Core reasoning: there are no two consecutive red nodes, so the number of levels increases by at most a constant factor relative to the black-height; a subtree with black-height b requires at least 2^b − 1 nodes. It follows that the height is logarithmic.

You can cross-reference the proof in [Cornell CS2110's lecture on trees](https://www.cs.cornell.edu/courses/cs2110/2018su/lectures/Lecture9-Trees.pdf). What matters in this topic is the height bound, not treating color as a business-data attribute.

### 4.1. Color Does Not Participate in Key Comparison

Color serves structural maintenance. It does not give a key "higher priority," does not replace the Comparator, and is not a new ordering for the map.

Two trees with different shapes or colors can still represent the exact same set of mappings and the exact same key order.

### 4.2. Java Does Not Require Callers to Manage Colors

TreeMap's put/remove operations maintain the internal structure. Users do not need to add color fields to their key classes or pass balancing information when calling the API.

The [OpenJDK 17u TreeMap.java source](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java) contains rotation and post-insert/post-delete fixup paths. They help explain the mechanism; application code does not rely on private method names to use the map.

## 5. Rotations and Recoloring: Changing Shape While Preserving Order

A conceptual left rotation:

```text
       x                         y
      / \                       / \
     A   y     left rotation   x   C
        / \       ---->       / \
       B   C                 A   B
```

A, B, C are subtrees. Before and after the rotation, the traversal order remains:

```text
A → x → B → y → C
```

Links are reorganized locally, while the ordering relationship between regions is preserved. Accompanying recoloring restores the required invariants.

### 5.1. A Local Rotation Is Not a Full Map Re-Sort

A rotation updates a few links around the involved nodes. There is no need to extract all keys and re-sort them.

The overall post-operation fixup procedure may walk up ancestors to resolve remaining violations. The height bound keeps that work appropriately bounded.

### 5.2. The Tree Does Not Need a Single Unique Shape

Different insertion/deletion histories can lead to different valid layouts.

The public contract does not require a specific key to always be the root or a given put call to always perform a specific number of rotations.

Correctness tests should verify mappings, ordering, and API behavior. If measuring implementation details, you must state the version and purpose of the observation.

## 6. How Do get, put, and remove Traverse the Tree?

### 6.1. get and containsKey

Starting from the root, compare the target key with the current node's key:

- Negative result: move to the left subtree.
- Positive result: move to the right subtree.
- Zero result: the key's position in the order has been found.
- Null link encountered: the target key is not present.

Such a path has length O(log n) when the tree is kept balanced.

ContainsKey does not need to scan all values. It checks existence using the same key-indexed structure.

### 6.2. put for an Existing Key

If the comparison determines that an equivalent key is already present, put replaces the value associated with that mapping. Size does not increase.

Finding the position still incurs the tree-path cost; "only replacing a value" does not make the call O(1) if the key still has to be located first.

TreeMap's ordering must be consistent with equals if it is to fully obey the general Map contract. Do not use an under-specified Comparator that causes two distinct business keys to compare as 0 and expect the tree to keep them separate on its own.

### 6.3. put for a New Key

The call finds the appropriate position, attaches the new node, and then performs structural rebalancing if needed.

Total work includes the search path and the structural adjustment. This is why O(log n) still holds when inserting keys, even if the input is already sorted in ascending or descending order.

It does not just append leaves and let the tree skew indefinitely.

### 6.4. remove Involves Both Lookup and Structural Fixup

First, the node must be located by key. Once found, deletion handles it based on the number of children and continues fixing invariants if needed.

For a node with two children, one approach is to use the in-order successor to reduce the problem to a simpler deletion case. The OpenJDK 17u source uses this path.

Do not assume remove is O(1) just because "the key is already known." Knowing the key value does not mean holding a direct reference to the node position to skip searching, and the post-deletion fixup also has a cost.

## 7. Cost Table: Distinguishing Contract from Implementation Analysis

The table below uses n as the number of mappings and assumes constant-time comparison/equality checks, with data and ordering used according to contract.

| Operation | Cost Under Standard Model | Basis |
| --- | --- | --- |
| containsKey, get, put, remove | O(log n) | Guaranteed in TreeMap documentation |
| firstKey, lastKey | O(log n) worst case | In OpenJDK, walks to the leftmost/rightmost edge of the tree |
| floor, ceiling, lower, higher by key | O(log n) along tree path | Locates neighboring position in a balanced tree |
| pollFirstEntry, pollLastEntry | O(log n) | Finds boundary then deletes/rebalances tree |
| Full entry traversal via iterator | O(n) | Follows node order rather than re-searching from root per entry |
| containsValue | O(n) worst case | Tree is indexed by key, not by value |
| size of root TreeMap | O(1) in reference implementation | Reads stored count |
| Iterating k results in a key range | O(log n + k) along iterator path | Locates start position then visits results |

For very small n or n = 0, you can write log(n + 1) to avoid reading log(0). The notation in the table describes growth rate, not nanoseconds per call.

Implementation-analysis rows should not be turned into a universal guarantee for every NavigableMap or SortedMap implementation. When using a different class, read that class's contract.

### 7.1. The Root Is Not Necessarily the Smallest or Largest

Balancing gives the root a region-splitting role; it does not mean the root holds the first or last key.

In the reference implementation, finding the smallest key may require walking an entire left edge, and finding the largest key walks a right edge. Do not assume these two operations are O(1) just because the map is "already ordered."

### 7.2. A Small View Does Not Automatically Have O(1) Operations

SubMap is a range view, not a separate, independent tree pre-populated with each result.

For example, size on a bounded view in the OpenJDK 17u source may need to traverse to count, and has a mechanism to cache the result by modification state. Do not extrapolate from the root TreeMap's size to a guarantee that every size call on every view is O(1).

Likewise, do not add O(log n) per element when using a sequential iterator over a view. Locating the start and iterating through the results play different roles.

## 8. Java 17 Example: Ascending Inserts and Counting Comparisons on Lookup

This program uses a Comparator matching natural numerical order, adding a counter for how many times compare is called. The counter does not affect ordering decisions.

The map is populated with ascending keys. If this were a simple unbalanced search tree, such input would easily form a long chain. TreeMap maintains its balancing mechanism.

Save as **TreeMapSearchCost.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Map;
import java.util.TreeMap;

public class TreeMapSearchCost {
    static final class CountingOrder implements Comparator<Integer> {
        int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }

        void reset() {
            calls = 0;
        }
    }

    public static void main(String[] args) {
        System.out.println("ascending inserts; observed comparison counts");
        for (int n : new int[] {31, 127, 1023, 8191}) {
            CountingOrder order = new CountingOrder();
            TreeMap<Integer, Integer> map = new TreeMap<>(order);
            for (int key = 0; key < n; key++) {
                map.put(key, key * 10);
            }
            order.reset();
            Integer value = map.get(n - 1);
            System.out.println("n=" + n + "; value=" + value
                    + "; get comparisons=" + order.calls);
        }

        Map<Integer, String> sample = new TreeMap<>();
        for (int key : new int[] {40, 20, 60, 10, 30, 50, 70}) {
            sample.put(key, "v" + key);
        }
        System.out.println("get 30: " + sample.get(30));
        System.out.println("put old 30: " + sample.put(30, "updated"));
        System.out.println("remove 40: " + sample.remove(40));
        System.out.println("keys after removal: " + new ArrayList<>(sample.keySet()));
        System.out.println("value after update: " + sample.get(30));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapSearchCost.java
java TreeMapSearchCost
```

Observed stdout:

```text
ascending inserts; observed comparison counts
n=31; value=300; get comparisons=8
n=127; value=1260; get comparisons=12
n=1023; value=10220; get comparisons=18
n=8191; value=81900; get comparisons=24
get 30: v30
put old 30: v30
remove 40: v40
keys after removal: [10, 20, 30, 50, 60, 70]
value after update: updated
```

The programs in this lesson are compiled with --release 17 and run on OpenJDK 24.0.2. The --release flag selects the API/language level and target bytecode; it does not turn the running JVM into Java 17.

### 8.1. Reading the Counter Within Its Proper Scope

When n grows from 31 to 8,191, the observed number of comparisons when looking up the last key grows from 8 to 24, rather than scanning through 8,191 keys.

These exact numbers belong to the stated environment and operation history. Another valid implementation or tree shape may yield different counts while still satisfying O(log n).

The program does not use reflection to measure height or inspect colors. It observes calls to the publicly passed Comparator.

### 8.2. This Is Not a Measurement of Total Time

The counter does not count allocations, rotations, recolorings, pointer chasing, memory management, or CPU time for other parts.

Counting comparisons helps clarify the search path; it does not reduce the entire cost of put/remove to just the number of compare calls. The reason those operations are bounded also comes from the balancing maintenance algorithm.

Do not take a counter value of 24 and interpret it as 24 arbitrary units of time.

### 8.3. Contents Must Still Be Correct After Updates and Deletions

The small map section checks get, put on an existing key, and remove, then iterates over the remaining keys.

Put 30 returns v30 and updates the value to updated. Remove 40 deletes that mapping. The final sequence remains sorted by key: 10, 20, 30, 50, 60, 70.

You do not need to know which node is the root after those operations to verify the public result.

## 9. Traversing the Whole Tree Is Not n Lookups from the Root

An iterator can locate the first node and then advance through each subsequent element in order.

In OpenJDK 17u, nodes have child and parent links; the successor path moves to the next element without issuing a fresh get for each key.

### 9.1. A Single next Step May Climb Multiple Links

If a node has a right subtree, the next element may be the leftmost node of that subtree.

Otherwise, the path may need to climb up to an appropriate ancestor. A single step does not necessarily perform just one link assignment.

However, across a full traversal, the total link-traversal work is amortized over the number of nodes. You do not pay the full root-search cost again for every entry.

Therefore, we can distinguish:

- Worst-case cost of a single next step.
- Amortized average cost of steps across the full traversal.
- Total cost of traversing all n entries.

### 9.2. Iterating entrySet Usually Reflects the Work More Directly

If you need both key and value, read them from the Map.Entry currently being visited.

Looping over keySet and calling get for each key performs additional key-based lookups. The total can incur an O(n log n) component, even though the iterator itself is already walking the keys in order.

Similarly, repeatedly calling higherKey from scratch for each step is a sequence of separate navigation queries. Do not equate it with a stateful iterator's successor path.

### 9.3. Processing Results Is Also Real Work

To output n mappings, you must visit at least n results. A balanced tree cannot turn reading every value into O(log n).

If the loop body processes data of varying sizes, include that processing cost as well. The O(n) bound of structural traversal does not guarantee that every piece of work inside the loop is constant time.

## 10. containsValue Does Not Benefit from the Same Index as get

TreeMap organizes its tree by key. When given only a value to search for, there is no basis to use key ordering to decide which subtree to prune.

In the reference implementation, containsValue walks the entries to compare values and can stop once a match is found.

If the value is absent, it may have to check all n mappings. If the value appears near the start of traversal, it can stop earlier. O(n) here is a worst-case bound.

If an application needs frequent lookups by both key and value, consider a separate indexing model suited to the data's one-to-many or many-to-many relationship. Do not assume TreeMap already maintains a second tree for values.

Values can also be duplicated across multiple keys. A key ordering does not impose a uniqueness rule on values.

## 11. Java 17 Example: Traversal, Value Search, and a Small Range

The next program separates two kinds of counters:

- CountingOrder counts key comparisons.
- Value.equalityChecks counts equals checks on the searched value.

These counters are solely for single-threaded experimentation and must not be used to alter comparison or equality outcomes.

Save as **TreeMapTraversalCost.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapTraversalCost {
    static final class CountingOrder implements Comparator<Integer> {
        int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }
    }

    record Value(int number) {
        static int equalityChecks;

        @Override
        public boolean equals(Object other) {
            equalityChecks++;
            return other instanceof Value value && number == value.number;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(number);
        }
    }

    public static void main(String[] args) {
        CountingOrder order = new CountingOrder();
        TreeMap<Integer, Value> map = new TreeMap<>(order);
        for (int key = 0; key < 1000; key++) {
            map.put(key, new Value(key));
        }

        order.calls = 0;
        long sum = 0;
        int visited = 0;
        for (Map.Entry<Integer, Value> entry : map.entrySet()) {
            sum += entry.getValue().number();
            visited++;
        }
        System.out.println("full visited: " + visited);
        System.out.println("full sum: " + sum);
        System.out.println("observed full key comparisons: " + order.calls);

        Value.equalityChecks = 0;
        boolean found = map.containsValue(new Value(-1));
        System.out.println("missing value found: " + found);
        System.out.println("observed value equality checks: " + Value.equalityChecks);

        NavigableMap<Integer, Value> window = map.subMap(450, true, 455, false);
        long rangeSum = 0;
        int rangeVisited = 0;
        for (Map.Entry<Integer, Value> entry : window.entrySet()) {
            rangeSum += entry.getValue().number();
            rangeVisited++;
        }
        System.out.println("range keys: " + new ArrayList<>(window.keySet()));
        System.out.println("range visited: " + rangeVisited);
        System.out.println("range sum: " + rangeSum);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TreeMapTraversalCost.java
java TreeMapTraversalCost
```

Stdout on the stated environment:

```text
full visited: 1000
full sum: 499500
observed full key comparisons: 0
missing value found: false
observed value equality checks: 1000
range keys: [450, 451, 452, 453, 454]
range visited: 5
range sum: 2260
```

### 11.1. Zero Comparator Calls Does Not Mean Zero Work

The entrySet loop visited 1,000 entries and summed to 499,500. The key comparison counter is 0 in this environment because the iterator follows the existing ordered structure.

It still has to move through the nodes, retrieve values, and accumulate the sum. Do not infer O(1) or "zero cost" just because one particular method is not called.

### 11.2. Missing Values Require Checking All Data

The map contains Value instances from 0 to 999. Searching for Value(-1) does not find it, and the equals counter is 1,000.

This result clarifies that the index is by key, not by Value's number component.

Some equality checks can cost more than constant time, so actual cost also depends on how values are represented.

### 11.3. A Key Range Only Yields Results Within the Range

SubMap uses an inclusive lower bound of 450 and an exclusive upper bound of 455, so the keys are 450 through 454, yielding 5 results with a sum of 2,260.

The view does not copy all 1,000 mappings. When iterating a range, the work model consists of locating the start and walking the entries belonging to the result.

The program does not modify the map during traversal. There is no need to introduce concurrent-modification issues just to observe cost here.

### 11.4. Limits of Observation

The counter numbers belong to the executed runtime path, not a requirement that every TreeMap implementation must call equals or compare the exact same number of times.

The data contract and complexity bounds are what must be relied upon. Experiments help explain the mechanics; they do not replace reading the contract and analyzing the algorithm.

## 12. Comparator Cost Is Part of Real Time

When writing O(log n), we usually treat a single key comparison as constant time. That assumption needs to be stated explicitly.

If one comparison costs S, the comparison portion of the cost can be described as O(S log n) in a model where S is an appropriate bound for the relevant comparisons.

### 12.1. Long Strings Are Not Like Small Integers

Comparing two strings may require inspecting a shared prefix before finding a difference. If the relevant length is L, the comparison part can depend on L.

A tree with few levels does not make the cost of processing each long key disappear.

If a Comparator re-parses text or computes an expensive quantity on every call, that work is repeated for every comparison. You can consider key representation or precomputing data, as long as the ordering rules and key contract are preserved.

### 12.2. Comparator Must Form a Valid Ordering Relation

A Comparator must satisfy the sign, transitivity, and equality-consistency requirements of its contract. Cross-reference [Java 17 Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

Using Integer.compare instead of direct subtraction avoids a common integer overflow bug when comparing integers.

Do not use random numbers, current time, or mutable state that changes across calls to make the same pair of keys compare larger one moment and smaller the next.

A balanced tree only protects its shape algorithmically. It cannot fix a self-contradictory ordering relation.

### 12.3. Do Not Mutate Sorting Fields While a Key Is in the Tree

If a key object mutates a field used by the Comparator, its old position may no longer match the new order. Subsequent lookups or navigation can produce unexpected results.

The fact that the tree still has many nodes and low height does not prove the keys are being used correctly.

Keep identity/ordering information stable; if a logical key must change, handle it through a procedure that removes the old mapping and inserts the new mapping in accordance with the application contract.

## 13. Bulk Loading and Copying: Do Not Apply One Formula to Every Path

### 13.1. N Separate puts Usually Yield O(n log n)

Loading n new keys into an empty tree via individual put calls has a total cost of O(n log n) under the constant-time comparison model.

Sorted input does not turn a red-black tree into a chain, nor does it automatically turn a loop of n put calls into a linear tree-building API.

Each call still pays for its search path and corresponding structural maintenance.

### 13.2. A Sorted Source May Offer a Dedicated Construction Path

The TreeMap constructor taking a SortedMap is documented to run in linear time and preserve the source's ordering.

The OpenJDK 17u implementation also has a buildFromSorted path to construct the structure from already-ordered data; putAll into an empty map has specific optimization conditions depending on the source type and Comparator.

Therefore, do not state "every way of copying n entries into a TreeMap must take n log n." You need to know which constructor or operation path is being used.

If the argument is just an arbitrary Map, do not assume the source is already ordered compatibly with the destination's Comparator. Different overloads and preconditions matter.

### 13.3. Check the Overall Benefit

If you have to sort unordered data solely to use a linear construction path, that sort also has a cost. Do not omit it from the total and conclude the whole pipeline has become O(n).

An optimization pays off when the input is already suitable or when the preparation work is reused elsewhere; account for the entire data pipeline.

## 14. Things a Balanced Tree Does Not Provide Automatically

### 14.1. No Index-Based Access to the k-th Element Just Because It Is Balanced

TreeMap has key ordering, but it does not have a List-like get(index) API to fetch the k-th item by position.

An order-statistic tree can store subtree node counts to serve a different kind of query. Do not attribute that capability to TreeMap just because both use balanced trees.

If you manually iterate to position k, the work must account for those traversal steps. Locating by key and locating by rank are two different requirements.

### 14.2. Not the Same Memory Footprint as a Key–Value Array

Tree nodes must store links and balancing metadata alongside the key and value. Object layout, references, and memory locality can affect real-world performance.

Do not turn O(log n) into a conclusion that TreeMap is always faster or more memory-efficient than every other structure.

TreeMap also has no hash-table-style initialCapacity parameter for callers to choose a bucket count. Growing a node-based structure and maintaining balance differs from resizing a bucket table.

### 14.3. Not Automatically Thread-Safe

Balance is an algorithmic property of the structure, not a thread-coordination mechanism.

TreeMap is not synchronized. When shared alongside structural modifications, an appropriate coordination design is required; fail-fast behavior does not replace that responsibility.

Do not treat logarithmic bounds on get/put as evidence that they are atomic or safe across concurrent operation sequences.

## 15. Choosing TreeMap by Query Type

| Primary Requirement | Consideration |
| --- | --- |
| Key lookup and maintaining key order | TreeMap provides both mapping and ordering |
| Need floor/ceiling, predecessor/successor, or key ranges | An ordered tree directly serves these queries |
| Key lookup only, no ordering needed | Compare against hash structures based on data and performance conditions |
| Need insertion order | TreeMap's key order does not represent that requirement |
| Need k-th item by index | Consider another suitable data model or API |
| Mostly immutable data, primarily iterated or searched | You can also evaluate sorted contiguous storage across the full pipeline |

Do not choose based on a single Big-O symbol. Consider query types, key comparison cost, insert/delete frequency, memory, and actual workload.

When benchmarking, separate data construction from query execution if the question requires separating them. Consume real query results, warm up the JVM, and avoid using console-printing time as a measurement of structural operations.

## 16. Common Pitfalls and How to Fix Them

| Misconception | Correct Understanding |
| --- | --- |
| Having two branches means lookup is always log n | Height must be kept bounded |
| Ascending inserts skew every TreeMap into a chain | Red-black trees maintain balance during updates |
| Balance means both sides have the exact same node count | Only invariants sufficient to bound height are needed |
| The root is always the smallest key | Left/right boundaries and the root have different roles |
| Knowing the key makes remove O(1) | Position lookup and structural maintenance are still required |
| Every TreeMap method is log n | Full traversal and containsValue have different costs |
| Iterator next is like a get from the root | The iterator maintains state to step through the structure |
| Zero Comparator calls during traversal means traversal is free | Entries must still be visited and processed |
| An expensive Comparator does not affect time conclusions | Comparison cost is part of the total |
| The tree fixes keys whose sorting fields mutate | Keys must remain stable per the contract |
| N puts on sorted data is always O(n) | Distinguish a put loop from a dedicated bulk-build path |
| Compare counts in one run are an API constant | They are an environment observation, not an exact count guarantee |
| Being ordered implies indexed access | Key ordering does not automatically provide rank queries |
| Balance means thread safety | Synchronization is a separate responsibility |

## 17. Self-Check Exercises with Solutions

### Exercise 1: A Skewed Search Tree

An unbalanced search tree receives keys 1 through n in ascending order and only attaches new keys to the right. How much can looking up n cost?

**Solution:** O(n), because it must traverse a chain of length on the order of n. The search rule alone does not guarantee logarithmic height.

### Exercise 2: Red-Black Tree with Ordered Input

TreeMap receives n ascending keys via put calls. Can we conclude the final get must be O(n) just because the input was ascending?

**Solution:** No. TreeMap maintains its balancing mechanism; its contract guarantees log(n) cost for the stated basic operations.

### Exercise 3: Visiting Every Mapping

We need to sum the values of n entries. Does a balanced tree reduce total traversal work to O(log n)?

**Solution:** No. All n results must be visited, so full traversal is O(n), not counting the cost of processing each value.

### Exercise 4: Searching for a Missing Value

TreeMap has n keys and does not contain value v. Does containsValue(v) use the same key-indexed path as get(key)?

**Solution:** No. There is no key to choose a direction according to the ordering relation. Worst case requires checking n values.

### Exercise 5: Comparator Processing Long Strings

If a key comparison takes up to O(L), is it accurate enough to simply write "get takes O(log n) time regardless of string length"?

**Solution:** Not accurate enough. Under that model, the comparison work can be O(L log n). State the assumption about per-comparison cost.

### Exercise 6: Looking Up the Value for Each Key

Does a loop iterating keySet and calling get for each key necessarily keep the same total cost as a pure entrySet path?

**Solution:** No. It adds n key-based lookups, which can introduce an O(n log n) component. If both key and value are needed, use the Map.Entry being iterated.

### Exercise 7: A Range with k Results

For a range view's iterator, what two kinds of work does the O(log n + k) model distinguish?

**Solution:** Locating the starting boundary in the tree and visiting the entries within the range. It does not need a fresh get for each result.

### Exercise 8: Building from a SortedMap

Can we say every TreeMap copy constructor is n log n without checking the source type?

**Solution:** No. The constructor taking a SortedMap is documented to run in linear time. Distinguish the construction path as well as the cost of preparing the source.

### Exercise 9: Tree Shape in Tests

Another JDK build has the same mappings, same order, and meets operation bounds, but its root/colors differ from the illustration. Is that enough to conclude it is wrong?

**Solution:** No. Illustrations are not a contract on internal layout; verify the public guarantees.

## 18. References

- [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): red-black tree, basic operation guarantees, containsValue, and constructors.
- [TreeMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/TreeMap.java): lookup, rotations, post-insert/delete fixup, iterators, and construction from sorted sources.
- [NavigableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): neighbor queries and range views.
- [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): key comparison contract.
- [Cornell CS2110 — Trees](https://www.cs.cornell.edu/courses/cs2110/2018su/lectures/Lecture9-Trees.pdf): red-black tree invariants and height bounds.

Balancing keeps key-based search paths short, while total cost depends on the operation being performed and the work at each step. Understanding both the structure and the scope of the complexity table helps you use TreeMap properly for lookups, updates, traversals, and ordered queries.
