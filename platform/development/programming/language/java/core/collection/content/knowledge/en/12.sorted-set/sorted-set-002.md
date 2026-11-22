# TreeSet and Balanced Search Tree Structure

## 1. What Problem Does TreeSet Solve?

A system that manages timestamps needs to keep each timestamp once, iterate in order, check whether a timestamp is already present, and find the nearest timestamp before or after a given value. Data is also added and removed while the program is running.

That is a situation where `TreeSet` is worth considering: a set of elements organized by an ordering relation that can maintain that order as data changes.

Three ideas should be separated right from the start:

- **Set:** if a value is considered already present, adding it again does not create a new member.
- **Ordering:** elements are iterated according to natural ordering or a chosen comparator.
- **Balanced tree structure:** search paths are kept short, even when the input data is already in ascending order.

"Sorted" does not mean that every time an element is added, TreeSet takes all the data out and re-sorts it. It places the element at an appropriate position in the tree, then adjusts the structure locally when needed.

According to the [Java 17 TreeSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), TreeSet is a `NavigableSet` implementation backed by `TreeMap`; the three basic operations `add`, `remove`, and `contains` have a guaranteed logarithmic cost. [Java 17 TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) uses a red-black tree, a form of self-balancing binary search tree.

This article moves from the search rule in a tree to the reason balancing is necessary, and then connects that mechanism to the behavior and cost of TreeSet. You do not need to write a red-black tree yourself to use TreeSet, but understanding the structure helps you choose the right API and avoid wrong assumptions about performance.

## 2. The Relationship Between Set, SortedSet, and NavigableSet

The interfaces can be read according to the capabilities they add:

```text
Set<E>
    membership and uniqueness

SortedSet<E>
    adds an ordering over elements

NavigableSet<E>
    adds neighbor lookups and bounds

TreeSet<E>
    concrete implementation backed by a balanced search tree
```

TreeSet is not a sorted List. It does not have a `get(index)` operation to retrieve "the i-th element" like List does. An ordered tree does not automatically store element counts per subtree to support positional access.

A common way to declare it is:

```java
// Excerpt; requires importing java.util.NavigableSet and java.util.TreeSet.
NavigableSet<Integer> milestones = new TreeSet<>();
milestones.add(30);
milestones.add(10);
milestones.add(20);
```

The variable uses the `NavigableSet` interface because the calling code needs order-based navigation capabilities. The actual object is a TreeSet, so the implementation and costs come from TreeSet.

If the variable were only declared as `Set<Integer>`, the object would still be a TreeSet and would still preserve order, but the navigation methods are not on the `Set` type. Choose the variable type according to the capabilities the calling code needs to express, rather than always picking the concrete class or always narrowing to the point of losing needed information.

## 3. Rules of a Binary Search Tree

A node in a binary search tree can have a left subtree and a right subtree. For a valid ordering, the rule must hold for the **entire subtree**, not just the two immediate child nodes:

```text
every value in the left subtree < value at node < every value in the right subtree
```

Here `<` means "comes before according to the comparison relation", not necessarily numerically smaller. If descending order is used, a larger number can come before a smaller number.

An illustrative example in ascending integer order:

```text
             40
           /             20      60
        /      /        10   30  50   70
```

This is a valid illustrative tree shape, not an internal snapshot of a TreeSet after a specific sequence of operations.

### 3.1. Searching for 30

Start at the root:

```text
30 vs 40: comes before -> go left
30 vs 20: comes after  -> go right
30 vs 30: equal        -> found
```

There is no need to inspect nodes 50, 60, or 70. The ordering rule lets us discard an entire subtree after each comparison.

### 3.2. Searching for 35

```text
35 vs 40: go left
35 vs 20: go right
35 vs 30: go right
no node on the next branch -> not found
```

If we want to add 35, the empty branch position just found is a suitable candidate according to the search rule. After insertion, the balancing mechanism may change the shape of the tree, but it must continue to preserve the ordering relation.

### 3.3. A Comparison Result of 0 Plays a Special Role

For TreeSet, encountering a comparison result of `0` means an equivalent member in the ordering has already been found. `add` does not continue to store a separate node just because the new object has a different reference.

That is why the comparator both guides the path through the tree and affects the uniqueness of TreeSet. The comparator is not only called when printing data.

## 4. Why a Plain Search Tree Is Not Enough

A binary search tree that obeys the ordering rule can still become very tall. If we simply insert at the found position without adjustment, the ascending sequence `1, 2, 3, 4, 5, 6, 7` can produce:

```text
1
   2
       3
           4
               5
                   6
                       7
```

Finding the largest element or a value greater than all elements has to traverse nearly the entire chain. When the tree has `n` nodes, the path can grow with `n`, leading to `O(n)` cost.

A more balanced shape with the same contents is:

```text
          4
        /          2     6
      /    /      1   3 5   7
```

Both shapes can produce the exact same ascending traversal output:

```text
1, 2, 3, 4, 5, 6, 7
```

Therefore, checking only that the printed output is sorted does not prove the tree is balanced. Content order and structural height are two different properties.

Self-balancing trees add rules to prevent search paths from degenerating into a long chain. TreeSet maintains this during additions and removals; callers do not have to shuffle input data to "help the tree stay balanced."

Nor should balance be understood as every node's two subtrees always having the exact same number of elements, or every leaf always being at the exact same depth. Those conditions are too strict and are not what TreeSet needs to maintain.

## 5. How Red-Black Trees Keep Height Low

A red-black tree is still a binary search tree. Each node carries an extra color bit to support balancing invariants.

A standard description consists of:

1. Every node is colored red or black.
2. The root is black.
3. Conventional empty leaves, often denoted `NIL`, are black.
4. A red node has no red children.
5. From any node down to the empty leaves below it, every path has the same number of black nodes under the same counting convention.

`NIL` is an empty leaf used in the algorithmic model; it is not a `null` element added by the user to the Set. In a Java implementation, an empty link can be represented by a `null` reference, without allocating a separate leaf object for every branch.

Red and black information is metadata of the tree structure. It does not determine value order and does not appear in iterator results.

### 5.1. A Long Path Cannot Be Arbitrarily Long

Because there cannot be two consecutive red nodes, a long chain of red nodes cannot be inserted between black nodes. On the other hand, every path from the same node down to an empty leaf has the same number of black nodes.

Combining these two conditions, a path with extra red nodes still cannot be arbitrarily many times longer than another path. Height is bounded logarithmically in the number of nodes.

The idea can be seen through representative paths:

```text
shorter path:  black -> black -> black -> NIL
longer path:   black -> red -> black -> red -> black -> NIL
```

This diagram only illustrates the idea of placing red nodes between black levels; it does not claim every tree has exactly two paths like these.

### 5.2. A Common Height Bound

For `n >= 1` data nodes, a red-black tree satisfies the bound:

```text
h <= 2 * log2(n + 1)
```

Here `h` can be taken as the number of edges on the longest path from the root to a conventional empty leaf. Changing to a different height convention can shift a small constant, but does not change the `O(log n)` conclusion.

Brief proof sketch:

- Let `b` be the number of black nodes after the root down to an empty leaf on each path.
- A subtree with black-height `b` requires at least `2^b - 1` data nodes; this can be seen by induction on the two subtrees.
- Therefore, `b <= log2(n + 1)`.
- Since there are no two consecutive red nodes, `h <= 2b`.
- The height bound above follows.

What to remember when using the collection is: search paths remain logarithmically short even with ordered input data. You do not need to use the formula to predict the exact root or the exact number of comparisons for a particular lookup.

### 5.3. Balanced in Height, Not in Pretty Drawing

A valid red-black tree can look skewed to one side in a drawing. As long as the invariants still hold, the height remains within the required bound.

It is also not an AVL tree: the two families of structures use different balancing criteria. When learning TreeSet, it is better to understand the specific red-black mechanism used by TreeMap rather than lumping all "balanced trees" into one identical algorithm.

## 6. Rotations and Recoloring Preserve Order

After an insertion or deletion, the tree may temporarily violate color rules. The fix-up mechanism uses recoloring and local rotations.

### 6.1. Left Rotation

A left rotation can be illustrated as follows:

```text
Before rotation:            After rotation:

      x                          y
     /                         /     A   y                      x   C
       /                     /       B   C                  A   B
```

In the diagram, `A`, `B`, `C` are subtrees, possibly empty. For the initial diagram to be a valid search tree, the values satisfy:

```text
A < x < B < y < C
```

After the rotation, an in-order traversal still yields:

```text
A, x, B, y, C
```

The rotation changes the parent-child relationship and the local root of that small region. It does not need to re-sort all the elements.

### 6.2. Right Rotation

Right rotation is the symmetric operation:

```text
Before rotation:            After rotation:

        y                        x
       /                       /       x   C                    A   y
     /                           /     A   B                        B   C
```

A rotation adjusts a fixed number of links, so it has `O(1)` local cost. However, an insertion or deletion still has to find the position and may have to process ancestor levels. You must not infer from "each rotation is O(1)" that "inserting an element is O(1)."

### 6.3. What Does Recoloring Solve?

Recoloring keeps the links unchanged while adjusting how black and red levels are distributed. Depending on the case, the fix-up mechanism may:

- Only recolor and continue examining ancestors.
- Rotate to change the local shape, combined with recoloring.
- Stop once the invariants have been restored.

Rotating according to the search rule alone is not enough to automatically guarantee all red-black rules. Conversely, recoloring alone cannot handle every case either. The two tools work together in the balancing algorithm.

The [OpenJDK 17 TreeMap source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/TreeMap.java) contains the post-insertion fix-up, post-deletion fix-up, and left/right rotation methods. These are implementation details for inspecting the mechanism; applications using TreeSet do not call those methods directly.

## 7. How Do Insertion and Deletion Relate to a Balanced Tree?

### 7.1. On Insertion

You can picture the process at a conceptual level:

```text
new value
    -> compare from the root, go left or right
    -> if comparison is 0: an equivalent member already exists
    -> if an empty slot is reached: create a new entry
    -> fix color invariants and shape as needed
    -> done
```

In the standard red-black algorithm, a new node starts as red so it does not increase the black count on the new path alone. If the parent is also red, the red-red violation must be fixed; the root must end up black.

Not every insertion triggers a rotation. Some only perform a valid insertion, some require recoloring, and some require rotations. Do not build application code that depends on an expected number of rotations for a given input sequence.

### 7.2. On Deletion

First, the matching node must be located by order. Unlinking depends on how many children the node has:

- No children: handle a data leaf.
- One child: splice across through the appropriate child node.
- Two children: the in-order successor can be used to reduce the problem to a simpler case.

If removing a node drops a black node on a single path, the algorithm must restore the equal black-count condition. The fix-up may inspect siblings and ancestors, recolor, or rotate.

The key takeaway when using the API is: deletion is not just "setting a slot to empty," and after deletion, the tree must still satisfy the conditions needed for subsequent lookups. The cost accounts for both finding the node and adjusting the structure.

You do not need to memorize every branch of the deletion fix-up algorithm to use TreeSet properly. If you want to implement a red-black tree yourself as a data structures exercise, that is a separate task that requires testing the invariants after every update.

### 7.3. Tree Rotations Do Not Change the Meaning of the Set

After rebalancing:

- The existing members remain the same members, aside from the element just added or removed as requested.
- Traversal order still matches the comparison relation.
- The root and parent-child relationships may have changed.
- Callers do not receive a stable positional index for each element.

Thus, TreeSet provides an observable ordering through its API, not a contract on internal tree shape.

## 8. Program 1: Observing Basic Capabilities

Save the file `TreeSetBasicsDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class TreeSetBasicsDemo {
    public static void main(String[] args) {
        List<Integer> input = List.of(40, 10, 30, 20, 10, 50);
        NavigableSet<Integer> values = new TreeSet<>();

        for (int value : input) {
            values.add(value);
        }

        System.out.println("input = " + input);
        System.out.println("ascending = " + values);
        System.out.println("add duplicate 20 = " + values.add(20));
        System.out.println("contains 30 = " + values.contains(30));
        System.out.println("remove 30 = " + values.remove(30));
        System.out.println("after remove = " + values);
        System.out.println("first = " + values.first());
        System.out.println("last = " + values.last());
        System.out.println("lower 25 = " + values.lower(25));
        System.out.println("floor 20 = " + values.floor(20));
        System.out.println("ceiling 25 = " + values.ceiling(25));
        System.out.println("higher 40 = " + values.higher(40));
        System.out.println("descending = " + values.descendingSet());
        System.out.println("poll first = " + values.pollFirst());
        System.out.println("poll last = " + values.pollLast());
        System.out.println("remaining = " + values);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 TreeSetBasicsDemo.java
java TreeSetBasicsDemo
```

Verified run output:

```text
input = [40, 10, 30, 20, 10, 50]
ascending = [10, 20, 30, 40, 50]
add duplicate 20 = false
contains 30 = true
remove 30 = true
after remove = [10, 20, 40, 50]
first = 10
last = 50
lower 25 = 20
floor 20 = 20
ceiling 25 = 40
higher 40 = 50
descending = [50, 40, 20, 10]
poll first = 10
poll last = 50
remaining = [20, 40]
```

The code uses language features and APIs available in Java 17 and later. The programs in this article were compiled with `--release 17` and verified on Azul OpenJDK 24.0.2.

### 8.1. Input Order and Traversal Order

The input is `40, 10, 30, 20, 10, 50`. The TreeSet result is `10, 20, 30, 40, 50`: ascending by Integer's natural ordering, with only one `10`.

A TreeSet iterator follows the ordering, not insertion order. Nor does this output mean the values sit contiguously in an internal array.

### 8.2. Lookup and Removal Operations

`contains(30)` and `remove(30)` search using the comparison relation. After removal, the remaining elements are still iterated in the right order.

Adding `20` again returns `false` because an equivalent member is already present. That is the difference between a Set and a List that allows multiple occurrences.

### 8.3. Finding Neighboring Elements

After removing 30, the contents are `[10, 20, 40, 50]`:

| Call | Search condition | Result |
|---|---|---|
| `lower(25)` | Greatest element strictly before 25 | 20 |
| `floor(20)` | Greatest element not after 20 | 20 |
| `ceiling(25)` | Least element not before 25 | 40 |
| `higher(40)` | Least element strictly after 40 | 50 |

Thinking in terms of "before" and "after" helps remember that these concepts depend on the Set's ordering. With a reversed comparator, do not reason using an ascending number line and ignore the comparator.

These capabilities tie directly to the ordered tree structure: while searching, the program can record a suitable boundary candidate and continue down into the needed subtree.

### 8.4. Both Ends and the Reversed View

`first` and `last` inspect the two ends in order. `pollFirst` and `pollLast` both retrieve and remove the element at the respective end.

In the example, `descendingSet()` provides a reversed-order view, rather than sorting and copying all data into an independent TreeSet. Updates through views are backed by the original set; do not treat it as an isolated snapshot.

On an empty Set, `first` and `last` throw `NoSuchElementException`; neighbor probes or `pollFirst`/`pollLast` return `null` when there is no result. Choose the API depending on whether missing data is a normal case or a violation of the processing flow's assumptions.

## 9. Cost: Know What You Are Counting

Let `n` be the number of members currently in a full TreeSet, and assume first that a single comparison takes constant time.

| Operation or process | Cost to understand | Basis |
|---|---|---|
| `contains` | `O(log n)` | Follows one search path in a balanced tree |
| `add` | `O(log n)` | Finds position and maintains balance |
| `remove` | `O(log n)` | Finds entry and maintains balance on removal |
| `size` on a full TreeSet | `O(1)` in the TreeMap implementation | Member count is maintained |
| Full single traversal | `O(n)` in visited nodes | Visits members sequentially in order |
| Adding n values via regular add calls | `O(n log n)` total bound | Sums the cost of updates as size grows |
| Memory for storing n members | `O(n)` for the storage structure | Requires entries and tree links |

The table does not claim that every method on every sub-view has the exact same cost as on a full TreeSet. For example, do not take the `size` analysis of the backing structure and automatically assume the same `size` cost for every range view.

### 9.1. O(log n) Is a Growth Bound, Not an Exact Step Count

A lookup might find the value immediately at the root and need very few comparisons. Another might have to travel near a leaf. The logarithmic bound describes how search path length scales as `n` grows, not that every call performs exactly `log2(n)` comparisons.

Red-black balancing is also not binary search on an array: a tree has links and dynamic shape, whereas a sorted array uses indexed access to pick midpoints. Both approaches have logarithmic search paths, but their update costs and memory layouts differ.

### 9.2. Include the Cost of the Comparator

If a single comparison costs `C`, the search part can be described as:

```text
O(C * log n)
```

For simple integer comparisons, treating `C` as constant is usually appropriate. For long strings, multi-criteria comparisons, expensive derived computations, or off-memory data, the cost per comparison can be significant.

Do not put slow operations or side effects—such as service calls, writing data, or mutating elements—inside a comparator. A comparator needs to express a stable ordering relation; TreeSet may invoke it multiple times across different operations.

### 9.3. Memory and Locality

A tree uses entries and links rather than just a contiguous sequence of references. That carries memory overhead and pointer chasing. You cannot look at `O(log n)` alone and conclude TreeSet always runs faster than every other structure.

If data is built once and read heavily, a sorted List may be worth considering. If you mainly check membership without needing order, a hash-based structure may fit better. TreeSet earns its keep when ordering and dynamic updates both serve the actual requirement.

Do not state a fixed byte count per element without specifying the JVM, reference mode, and measurement method. An `O(n)` memory analysis does not replace measuring footprint in a concrete environment.

## 10. Program 2: Ascending Input Does Not Turn the Tree Into a Chain

The program below adds numbers in strictly ascending order, then searches for a number larger than all added numbers. The comparator counts comparison calls while still returning the result of `Integer.compare`.

Save the file `TreeSetSearchCostDemo.java`:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class TreeSetSearchCostDemo {
    static final class CountingComparator implements Comparator<Integer> {
        private int calls;

        @Override
        public int compare(Integer left, Integer right) {
            calls++;
            return Integer.compare(left, right);
        }

        void reset() {
            calls = 0;
        }

        int calls() {
            return calls;
        }
    }

    static int ceilLog2(int value) {
        if (value <= 1) {
            return 0;
        }
        return 32 - Integer.numberOfLeadingZeros(value - 1);
    }

    public static void main(String[] args) {
        for (int n : new int[] {31, 127, 511, 2047}) {
            CountingComparator order = new CountingComparator();
            TreeSet<Integer> values = new TreeSet<>(order);

            for (int value = 0; value < n; value++) {
                values.add(value);
            }

            order.reset();
            boolean found = values.contains(n);
            int comparisons = order.calls();
            int conservativeBound = 2 * ceilLog2(n + 1);

            System.out.println("n=" + n
                    + ", found=" + found
                    + ", comparisons=" + comparisons
                    + ", bound=" + conservativeBound
                    + ", withinBound=" + (comparisons <= conservativeBound));
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 TreeSetSearchCostDemo.java
java TreeSetSearchCostDemo
```

Verified run output:

```text
n=31, found=false, comparisons=8, bound=10, withinBound=true
n=127, found=false, comparisons=12, bound=14, withinBound=true
n=511, found=false, comparisons=16, bound=18, withinBound=true
n=2047, found=false, comparisons=20, bound=22, withinBound=true
```

The counter is reset **after building the Set**, so the numbers belong solely to a single `contains(n)` call and do not include the insertion phase.

### 10.1. Reading the Results Appropriately

In this run, the number of elements grows from 31 to 2047, while the comparison count of the measured lookup grows from 8 to 20. In a naive search tree that degenerated after ascending insertions, searching for a number larger than every element could walk the entire chain.

The `bound` column is `2 * ceil(log2(n + 1))`, a conservative bound based on the red-black height idea. For the sizes in this program, `n + 1` is a power of 2, so rounding does not obscure the numbers.

This counter does not measure nanoseconds and does not prove TreeSet is faster than another collection. It only observes how many times the comparator is called in one specific scenario.

### 10.2. Do Not Hardcode the Numbers Into an API Contract

The values 8, 12, 16, and 20 are verified outputs from the runtime environment used in this article. Exact tree shape, specific traversal paths, and comparator call counts can depend on update history or implementation.

When writing application tests, do not assert "a TreeSet with 511 elements must call the comparator exactly 16 times during contains." What is worth protecting is correct membership results, correct ordering, and choosing a structure that fits its guarantees.

A finite set of measurements is also not a mathematical proof of `O(log n)`. The general guarantee comes from the balancing invariants and height analysis; the program connects the theory to a reproducible observation.

### 10.3. Why Does the Counter Not Break the Ordering?

This comparator has a mutable counter field, but that field does not participate in deciding the comparison result. Given the same two values, the ordering result stays the same.

This differs from a comparator that uses a call count to alternate between returning greater-than or less-than. Such a comparator does not express a stable ordering and cannot serve as a valid foundation for a search tree.

## 11. The Comparator Is Part of the Structure, Not Decorative

TreeSet has two common ways to determine ordering:

```java
// Illustrative excerpt; requires importing the corresponding java.util types.
TreeSet<Integer> natural = new TreeSet<>();

TreeSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());
```

In the first case, elements must support a suitable natural ordering, typically via `Comparable`. In the second case, the comparator supplies the rule.

In both cases, the exact same rule must be used consistently for every left step, right step, or equivalence conclusion.

According to the [Java 17 Comparator contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#compare(T,T)), the sign of the result must invert properly when swapping the two arguments, the relation must be transitive, and two values that compare equal to 0 must have consistent ordering relationships with any third value.

If a comparator creates a cycle such as `A < B`, `B < C`, yet `C < A`, discarding an entire subtree after a single comparison no longer has any basis. The tree may still have a low shape, but it cannot provide valid search semantics under a consistent order.

These are two axes to keep separate:

```text
balanced shape -> short paths
valid ordering -> meaningful paths
```

A balanced tree cannot fix a broken comparator.

### 11.1. Comparing Equal to 0 and equals

For TreeSet, `compare(a, b) == 0` or `a.compareTo(b) == 0` defines two elements as equivalent for membership storage.

To conform to the general Set contract, that equivalence relation should be consistent with `equals`. If it is not consistent, TreeSet's order-based behavior can still be well-defined, but Set's "unique according to equals" expectation is no longer satisfied.

Therefore, if you add a new object and `add` returns `false`, ask whether the comparator considers it equal to an existing member. Do not check only `equals` and conclude that the tree lost data.

### 11.2. Do Not Compare ints by Naive Subtraction

An easy-to-make mistake is:

```java
// Do not use for general int comparison: subtraction can overflow.
(left, right) -> left - right
```

Use:

```java
// Excerpt: compare ints without relying on subtraction that can overflow.
Integer::compare
```

Or use helpers like `Comparator.comparingInt` when comparing a property. The ordering relation is the foundation of search, so an overflow bug in a comparator does not just make printed output look slightly off; it can break branching assumptions.

## 12. Program 3: Ordering Determines Which Members Are Kept

Save the file `TreeSetComparisonDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class TreeSetComparisonDemo {
    record Entry(int priority, String name) {
    }

    public static void main(String[] args) {
        TreeSet<String> words = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

        System.out.println("add java = " + words.add("java"));
        System.out.println("add JAVA = " + words.add("JAVA"));
        System.out.println("String equals = " + "java".equals("JAVA"));
        System.out.println("contains JaVa = " + words.contains("JaVa"));
        System.out.println("case-insensitive members = " + words);

        TreeSet<String> natural = new TreeSet<>(List.of("java", "JAVA"));
        System.out.println("natural members = " + natural);

        Comparator<Entry> byPriorityThenName =
                Comparator.comparingInt(Entry::priority)
                        .thenComparing(Entry::name);
        TreeSet<Entry> entries = new TreeSet<>(byPriorityThenName);
        entries.add(new Entry(2, "B"));
        entries.add(new Entry(1, "A"));
        entries.add(new Entry(2, "A"));

        System.out.println("entry count = " + entries.size());
        for (Entry entry : entries) {
            System.out.println("entry = "
                    + entry.priority() + ":" + entry.name());
        }
        System.out.println("add equal entry = "
                + entries.add(new Entry(2, "A")));
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 TreeSetComparisonDemo.java
java TreeSetComparisonDemo
```

Verified run output:

```text
add java = true
add JAVA = false
String equals = false
contains JaVa = true
case-insensitive members = [java]
natural members = [JAVA, java]
entry count = 3
entry = 1:A
entry = 2:A
entry = 2:B
add equal entry = false
```

### 12.1. Case-Insensitive Strings

`String.CASE_INSENSITIVE_ORDER` treats `"java"` and `"JAVA"` as equivalent in comparison. As a result:

- The first `add("java")` succeeds.
- `add("JAVA")` returns `false`.
- `contains("JaVa")` returns `true`.
- The original string `"java"` remains the stored representative.

Meanwhile, `String.equals` is case-sensitive. This example intentionally demonstrates inconsistency between the ordering relation and equals; do not hide that fact when designing an API that accepts a Set.

A TreeSet using natural ordering keeps both `"JAVA"` and `"java"` because String's natural ordering distinguishes those two values.

### 12.2. Secondary Criteria Help Express True Distinctions

The `Entry` record has two components: `priority` and `name`. The comparator checks priority first, then name. Consequently, `Entry(2, "A")` and `Entry(2, "B")` are not merged.

With non-null names as in this example, the comparison returns 0 when both components are equal, matching the record's equality rule.

If we only used:

```java
// Excerpt: only appropriate if at most one representative per priority should be kept.
Comparator<Entry> onlyPriority =
        Comparator.comparingInt(Entry::priority);
```

then two Entries with the same priority would be equivalent according to TreeSet, even with different names. That is not an insufficiently balanced tree; it is the membership relation that was programmed.

Do not add secondary criteria mechanically just to "avoid losing elements." Choose criteria that reflect the actual distinctions the model intends to preserve. If you need multiple occurrences of the same value across all components, a Set is not the structure for representing multiplicity.

## 13. Maintaining Order When Data Changes

TreeSet can only organize elements properly when the data used for comparison remains stable while the element is in the tree.

Suppose a task object is placed in the tree by `priority`. After insertion, calling code changes `priority` through a setter. The object remains at the position chosen under its old value, while subsequent lookups use the new value.

Red-black balancing does not automatically track setters. The color rules may still hold structurally, while the value-ordering rule is already broken. Consequences can include iteration no longer appearing in the expected order, lookups failing to find the item, or removals not behaving as expected.

Good design practices include:

- Use immutable values as elements when the entire value determines the order.
- Or keep the compared attributes stable, allowing changes only to data that does not affect the ordering relation.
- If a compared attribute must change, remove the element while the old value is still valid and re-add it with the new value through a controlled workflow.
- Where possible, create a new object instead of mutating a key held in multiple places.

A comparator should also not depend on external configuration that can be arbitrarily flipped after the tree already holds data. For example, toggling an "ascending/descending" flag inside an active comparator does not rebuild the tree.

Changing a comparator means changing the organization rule. Create a new structure with the new rule and populate it with valid data as needed, rather than assuming the old tree will rewire itself after an external variable changes.

Do not rely on fail-fast exceptions as a mechanism to catch all such bugs. Mutating a field on an element is not a structural operation performed through TreeSet.

## 14. Important Limitations to Know in Practice

### 14.1. null Depends on the Comparison Rule

A TreeSet using natural ordering does not accept `null`. With an explicitly supplied comparator that supports `null`, an ordering can be defined for that value—for example, via `Comparator.nullsFirst`.

What matters is that elements can be validly compared under a single consistent rule. Do not assume "every Set accepts null" or "no TreeSet can ever accept null."

If `null` is allowed, methods that return `null` when nothing is found must also be read carefully in context. Disallowing `null` often makes the data model clearer when the domain does not need that missing value.

### 14.2. Elements Must Be Comparable With One Another

Having a generic type `TreeSet<MyType>` does not mean `MyType` naturally has an ordering. `MyType` needs a suitable `Comparable` rule or a supplied `Comparator`.

A comparison error can appear immediately on insertion, rather than waiting until many elements exist. Compiling and forming a valid ordering relation are two different things.

### 14.3. Range Views Are Not Copies

Methods such as `subSet`, `headSet`, and `tailSet` let you work with an ordered range. These are range-bounded views backed by the original set.

This is useful when a problem needs a value interval, because the ordering is already available to locate the bounds. However, do not treat creating a view as separating the data into an independent snapshot.

Adding out-of-bounds elements through a bounded view can be rejected. When you need an independent copy, create a new collection with the appropriate ordering and data policy.

### 14.4. No Rank-Based Access

`first()` retrieves the first value in order; it is not `get(0)` on an indexed list. TreeSet does not directly provide "the 1000th element" in logarithmic time via the standard API.

If a problem frequently accesses elements by position in a sorted sequence, reconsider the right data structure. Do not loop from the start repeatedly and assume each lookup is `O(log n)` just because the data sits in a balanced tree.

### 14.5. Not Automatically Thread-Safe

A standard TreeSet does not provide synchronization for concurrent updates across multiple threads. Self-balancing is a property of the organization algorithm, not a guarantee of thread safety.

When multiple threads are involved, choose an appropriate coordination mechanism or concurrent structure for the requirements. Either way, the comparator and the data used for comparison must still have stable semantics.

## 15. Choosing TreeSet When Ordering Serves Real Operations

TreeSet fits requirements such as:

- Checking membership while frequently adding and removing elements.
- Iterating over unique values in a single stable order.
- Finding the milestone before or after a given value.
- Working with intervals over an ordered domain.
- Reading or removing elements at either end in order.

A few questions help choose the structure:

| Primary need | What to consider |
|---|---|
| Only check existence, no ordering needed | You may not need to pay the cost of maintaining an ordered tree |
| Preserve exact insertion order | That is not the ordering TreeSet expresses |
| Keep every occurrence of a value | Need a model that allows duplicates or counts occurrences |
| Sort once and read by index | A sorted list may be a better fit |
| Frequently update and find ordered neighbors | That is the direct strength of an ordered tree structure |

Do not choose TreeSet just because of the word "Tree" or because you heard trees are always fast. The benefit comes from one structure simultaneously maintaining uniqueness, ordering, and low search paths.

Nor should you force TreeSet to do the job of a Map. If each key has an associated value that needs independent updates, TreeMap can express the requirement more clearly. TreeSet manages members; adding an equivalent element is not an operation that overwrites a data record.

## 16. Verifying Correct Order, Membership, and Assumptions

When writing tests for code that uses TreeSet, protect the observable behavior the application depends on:

1. Iterated data follows the chosen ordering relation.
2. Two elements equivalent under the intended rule do not create an extra member.
3. Two distinct elements that the domain wants to keep both remain present.
4. `contains`, `remove`, and boundary lookups handle the representative data correctly.
5. Mutable properties permitted to change do not break the comparison rule.
6. The comparator handles boundary values properly, avoids overflow, and preserves transitivity.

You can compare the traversal sequence against an expected list in small examples with deterministic ordering. Unlike an unordered Set, here the ordering is part of the requirement.

However, do not assert that the root must be a specific value, which nodes must be red, or that a lookup must perform the exact number of comparisons observed on your current machine, unless the application itself implements the tree. Those belong to internal shape, not to the contract TreeSet provides.

If you are writing your own red-black tree to study the algorithm, the test scope is different: after every update, you need to check the search-tree property, parent-child links, root color, no red-red violations, black height, and node count. Do not treat a few sorted outputs as sufficient proof for a custom tree implementation.

## 17. Practice Exercises

### Exercise 1: Already-Ascending Input

Insert the numbers from 1 to n into a TreeSet. Do you need to shuffle them beforehand to avoid a degenerate tree?

**Suggested answer:** No. TreeSet relies on a self-balancing mechanism. Shuffling the input is not required for basic operations to maintain a logarithmic bound.

### Exercise 2: Same Output, Different Structure

Two trees both iterate `1, 2, 3, 4, 5, 6, 7`. One tree is a chain, and the other has low height.

Can you conclude they have the same search cost from the output alone?

**Suggested answer:** No. The output reflects content order, whereas search path cost depends on height and structure.

### Exercise 3: Does Left Rotation Change Order?

Use the diagram `A, x, B, y, C` from the rotations section to explain why traversal order does not change.

**Suggested answer:** The rotation preserves the relations `A < x < B < y < C`. It changes local links, not the in-order traversal sequence.

### Exercise 4: Comparing Only by String Length

A TreeSet uses `Comparator.comparingInt(String::length)`. Add `"cat"` and `"dog"`.

Will both be kept, and is this a balancing bug?

**Suggested answer:** The two strings have the same length, so the comparator returns 0; TreeSet keeps only one representative. This is a consequence of the equivalence rule, not a tree-shape bug. If both must be kept, you need a distinguishing relation that matches the domain.

### Exercise 5: Mutating the Comparison Key

A task sits in a TreeSet ordered by priority, and then its priority is mutated directly.

Does red-black balancing automatically move the task to its new position?

**Suggested answer:** No. The structure does not automatically track setters. You need stable keys or a properly managed remove-mutate-reinsert flow.

### Exercise 6: A Very Slow Single Comparison

A comparator has to process a long string or compute an expensive property. Can you look at `O(log n)` alone and assume lookup time is small?

**Suggested answer:** No. You must include the cost of each comparison. A logarithmic number of comparisons does not make an expensive comparator free.

### Exercise 7: Finding the k-th Element

A requirement frequently asks for the k-th element in the ordered sequence. Does TreeSet provide `get(k)` in `O(log n)`?

**Suggested answer:** No. The standard API does not provide rank-based access like that. Choose a data structure suited to the operations the problem actually uses.

When reviewing an application that uses TreeSet, clearly identify which ordering relation guides the structure, which members must be treated as equivalent, and why the data used in comparisons remains stable for as long as it stays in the tree.
