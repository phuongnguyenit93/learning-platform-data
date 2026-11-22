# Using Identity When Traversing and Tracking Object Graphs

In Java, an object graph consists of **instances** (vertices) and the references connecting them (edges). When traversing a graph to export data, analyze links, clone a structure, mark visited nodes, or detect cycles, we often need to answer: **"Has this exact instance appeared before?"** This is a question about **object identity**.

This lesson distinguishes identity from value equality, shows how to use `IdentityHashMap` to manage visited sets and per-instance state, and clarifies the difference between shared references and cycles.

## 1. Why is `equals()` not enough for traversing an object graph?

Consider the following model:

```text
          root
          /  \
         v    v
       left  right        Two different instances,
         \    /           but equals() == true can hold.
          v  v
         shared           Two branches point to the exact same instance.
            |
            +---> root    Edge creating a cycle.
```

Three cases must be handled distinctly:

1. **Different instances, equal data.** `left == right` is `false` while `left.equals(right)` may be `true`, such as two nodes with the same `value` field. If the goal is to process each instance, a node must not be skipped just because its data matches another node.
2. **Same instance via multiple paths.** `left.next` and `right.next` both point to `shared`; the algorithm should process `shared` only once even though two paths reach it.
3. **Cycles.** If `shared` points back to `root`, uncontrolled traversal can loop infinitely or cause a `StackOverflowError`.

The problem of "processing **each instance** once" requires identity; the problem of "grouping objects with **equivalent values**" typically requires `equals()` and `hashCode()`. Because the two problems have different criteria, visited sets cannot be interchanged arbitrarily.

## 2. Tools comparing by the right criterion

| Tool | Mechanism | When to use |
| --- | --- | --- |
| `a == b` | Both variables point to the exact same instance, or both are `null` | Identity comparison |
| `a.equals(b)` | Checks equivalence relation defined by the object's type | Value/semantic comparison |
| `HashSet` / `HashMap` | Uses `hashCode()` and `equals()` | Grouping keys considered equal |
| `IdentityHashMap` | Compares keys with `==` and uses `System.identityHashCode()` for hashing | Tracking individual instances |
| `System.identityHashCode(x)` | Returns identity-based hash code, independent of overridden `hashCode()` | Hashing/diagnostic support; **not a unique ID** |

`System.identityHashCode()` **can collide across two different instances**; do not use the result as a unique identifier key or as a substitute for `==` comparison. Nor should you treat that number as a stable memory address or an ID preserved across Java runs.

`IdentityHashMap` is a specialized structure: it intentionally has different key semantics from a normal `Map`. Do not replace `HashMap` with `IdentityHashMap` for business problems where keys truly should be considered equal under `equals()`.

## 3. Creating an identity-based visited set

When you only need to know whether an instance has already been visited, create a `Set` backed by an empty `IdentityHashMap`:

```java
Set<Node> visited =
        Collections.newSetFromMap(new IdentityHashMap<Node, Boolean>());
```

`java.util.Set`, `java.util.Collections`, and `java.util.IdentityHashMap` must be imported. The map passed to `Collections.newSetFromMap(...)` must be empty at the moment the set is created.

Then, a simple traversal pattern is:

```java
if (!visited.add(node)) {
    continue; // This exact instance has already been recorded.
}
// Process node, then push linked nodes onto the worklist.
```

`add` returns `true` only the first time an instance is recorded, even if the set already contains another instance with an equivalent `equals()`. Marking before expanding edges prevents infinite reprocessing when encountering cycles. There is no need to call `contains` followed by `add` when a single `add` call already returns the needed information.

## 4. Java 17+ example: two equal nodes, one shared reference, and a cycle

The following program intentionally defines `equals()` using only `value`: the two nodes `left` and `right` are different instances yet both have `value = "same"`. Distinct `id` fields make it easy to observe whether traversal skips any node.

Save as **`IdentityGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class IdentityGraphDemo {
    static final class Node {
        final int id;
        final String value;
        final List<Node> next = new ArrayList<>();

        Node(int id, String value) {
            this.id = id;
            this.value = value;
        }

        Node link(Node... targets) {
            Collections.addAll(next, targets);
            return this;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node that
                    && Objects.equals(value, that.value);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(value);
        }
    }

    static List<Integer> dfs(Node root, Set<Node> visited) {
        List<Integer> order = new ArrayList<>();
        if (root == null) {
            return order;
        }

        Deque<Node> stack = new ArrayDeque<>();
        stack.push(root);
        while (!stack.isEmpty()) {
            Node node = stack.pop();
            if (!visited.add(node)) {
                continue;
            }

            order.add(node.id);
            // Push in reverse order so the left branch is traversed first.
            for (int i = node.next.size() - 1; i >= 0; i--) {
                stack.push(node.next.get(i));
            }
        }
        return order;
    }

    enum Mark { ACTIVE, DONE }

    static boolean hasCycle(
            Node node, IdentityHashMap<Node, Mark> marks) {
        Mark mark = marks.get(node);
        if (mark == Mark.ACTIVE) {
            return true; // Returned to a node on the current DFS branch.
        }
        if (mark == Mark.DONE) {
            return false; // Node already finished in a previous branch.
        }

        marks.put(node, Mark.ACTIVE);
        boolean cycle = false;
        for (Node child : node.next) {
            if (hasCycle(child, marks)) {
                cycle = true;
            }
        }
        marks.put(node, Mark.DONE);
        return cycle;
    }

    public static void main(String[] args) {
        Node root = new Node(0, "root");
        Node left = new Node(1, "same");
        Node right = new Node(2, "same");
        Node shared = new Node(3, "shared");

        root.link(left, right);
        left.link(shared);
        right.link(shared);
        shared.link(root); // Create a cycle.

        Set<Node> identityVisited =
                Collections.newSetFromMap(
                        new IdentityHashMap<Node, Boolean>());

        System.out.println("left == right: " + (left == right));
        System.out.println(
                "left.equals(right): " + left.equals(right));
        System.out.println(
                "DFS by identity: " + dfs(root, identityVisited));
        System.out.println(
                "DFS by equals:   " + dfs(root, new HashSet<>()));
        System.out.println(
                "Has cycle: " + hasCycle(root, new IdentityHashMap<>()));

        shared.next.clear(); // Remove edge shared -> root.
        System.out.println(
                "Has cycle after removing edge: "
                        + hasCycle(root, new IdentityHashMap<>()));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac IdentityGraphDemo.java
java IdentityGraphDemo
```

Deterministic output:

```text
left == right: false
left.equals(right): true
DFS by identity: [0, 1, 3, 2]
DFS by equals:   [0, 1, 3]
Has cycle: true
Has cycle after removing edge: false
```

**Explanation:**

- `left` and `right` are created by two `new` expressions, so their identities differ. `equals()` returns `true` because both hold the string `"same"`.
- Identity-based DFS visits `root (0) → left (1) → shared (3) → right (2)`. When encountering `root` again from `shared`, the visited set prevents reprocessing; `shared` is also not processed a second time from `right`.
- DFS with `HashSet` using `equals()` only produces `[0, 1, 3]`, because `right` is merged with `left`. For a problem requiring visiting every instance, this is a missed-vertex bug.
- The `hasCycle` method marks a node currently on the DFS branch as `ACTIVE`, and when finished as `DONE`. The edge `shared → root` returns to an `ACTIVE` node, so a cycle is detected. Removing that edge makes the result `false`, even though `shared` still has two incoming references.

`equals()` in the example is intentionally simplified to clearly show the difference between value and identity; in real systems, the `equals()`/`hashCode()` contract should be designed according to the data type's semantics.

## 5. Encountering the same instance again is not necessarily a cycle

You must distinguish **visited** from **the current DFS branch**:

| Observation | Correct conclusion |
| --- | --- |
| `visited.add(node)` returns `false` | This instance was already seen. It may just be a shared link. |
| Moving from the current node to an `ACTIVE` node in directed DFS | There is a back-edge to an ancestor on the DFS branch: a cycle exists. |
| Moving to a `DONE` node | The node was already processed in an earlier branch; this edge alone does not prove a cycle. |

In the diagram, `root→left→shared` and `root→right→shared` converge on `shared`. Removing the `shared→root` edge leaves a directed **acyclic** graph, even though DFS still encounters an instance twice. Therefore, do not use a rule like "already visited means a cycle".

An identity set suffices for **visiting each instance once**. To detect cycles in a directed graph, use three implicit states: unseen, `ACTIVE`, and `DONE`, which must also be attached **by identity**. You can use `IdentityHashMap<Node, Mark>` as in the example method. When there are multiple disconnected root vertices, keep the same state map across the entire check so nothing is processed redundantly.

The recursion in `hasCycle` can hit a `StackOverflowError` on very deep graphs. In that case, implement DFS with an explicit stack, where each frame records the node and current edge index, transitioning `ACTIVE → DONE` when the frame finishes. A plain `visited` set cannot replace information about the active stack.

## 6. Storing separate data for each instance

A `Set` only records present/absent. When you need state, analysis results, or clone objects attached to each node, use `IdentityHashMap` directly:

```java
IdentityHashMap<Node, Integer> depthByInstance =
        new IdentityHashMap<>();

depthByInstance.put(left, 1);
depthByInstance.put(right, 1); // Two separate keys even though equals() == true.
```

Common scenarios:

- **Two-state DFS marking**: `IdentityHashMap<Node, Mark>` storing `ACTIVE`/`DONE`.
- **Cloning a graph with cycles**: store `sourceInstance → cloneInstance` immediately after creating the empty clone, *before* traversing edges; encountering `source` again returns the registered clone. Thus an object shared in the source stays shared in the clone, and cycles do not cause infinite cloning.
- **Serializing a graph preserving reference sharing**: store `instance → id` assigned by the algorithm, so subsequent edges can reference the existing ID instead of re-expanding the same instance.
- **Analysis/caching in a single traversal**: attach temporary results per instance without merging value-equal nodes.

For a map, `get(key) == null` is not enough to distinguish "key absent" from "key present with value `null`". Use `containsKey(key)` when you need to distinguish them; `IdentityHashMap.containsKey` still checks by identity.

Do not use `IdentityHashMap` as long-term storage for state that ought to be shared by business key; each time a new instance is created representing the same business entity, it becomes a different key.

## 7. DFS/BFS techniques and costs

**Iterative DFS** can use `ArrayDeque<Node>` with `push`/`pop`; **BFS** can use `addLast`/`removeFirst`. For both, the identity-based visited set decides which nodes need processing.

In the example, a node is added to `visited` when **popped from the stack**. If multiple edges point to the same node, the stack may hold that reference multiple times, yet the main processing only runs once. Another variant marks immediately when **pushing onto the stack/queue** to reduce duplicate queued entries; when changing the marking point, ensure traversal order and rules remain correct.

With `V` reachable instances and `E` edges read, expected time is `O(V + E)`; `visited` holds `O(V)` references. When duplicate queued entries are allowed, the stack can take up to `O(E)` memory in the worst case. Deep graphs should use an explicit-stack loop to avoid recursion stack limits.

**`null` data:** `ArrayDeque` does not accept `null` elements. If the link list may contain `null`, only push `child` when `child != null`. The fact that an identity map accepts a `null` key does not make `null` a valid graph vertex.

**Concurrent modification:** `IdentityHashMap` does not guarantee thread safety when multiple threads update it. If the edge structure is also modified during traversal, results may reflect different points in time. Define an appropriate synchronization model, snapshot, or mutation restriction; a separate map per traversal is an easy-to-control default.

**Memory lifecycle:** `IdentityHashMap` holds strong references to keys. Use a local map within a single traversal and release it upon completion so you do not accidentally retain the entire graph in memory. `WeakHashMap` is not a weak-identity equivalent: it still uses `equals()`/`hashCode()`; designing weak keys by identity requires a separate mechanism.

## 8. Common pitfalls

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Using `HashSet<Node>` for visited in an instance-based problem | Two value-equal nodes get merged | Use a set backed by `IdentityHashMap` |
| Treating every revisited node as a cycle | Converging links are falsely reported | Track `ACTIVE` and `DONE` when detecting cycles |
| Marking a node only after traversing all branches | Cycles can cause non-terminating recursion | Register the instance before expanding branches |
| Creating a new visited set per branch | Other branches do not know the instance was seen | Share one visited set across the traversal |
| Reusing visited across independent traversals | Later runs skip instances | Create a fresh visited set per run, unless intentionally retained |
| Using `identityHashCode` as a unique identifier | Two objects can share the same hash code | Compare identity with `==` or an identity key |
| Treating an identity ID as a memory address | False assumption about the JVM | Do not infer addresses from standard APIs |
| Using recursion on graphs of unbounded depth | `StackOverflowError` | Use an explicit frame stack |
| Keeping an uncleaned global identity map | Keeps instances alive unnecessarily | Scope the lifecycle and clear/discard the map when done |

## 9. Choosing a solution for a real problem

1. Identify **the unit of processing**: a specific instance or a value/business entity? Choose identity only for the first case.
2. Determine whether the graph may contain **sharing, cycles, or null nodes**. If so, design marking from the start; never assume data is always a tree.
3. If you only need "visit once", use a `Set` backed by `IdentityHashMap`; if you need per-instance state, use `IdentityHashMap<Instance, State>`.
4. If you must **detect directed cycles**, track current-branch `ACTIVE` and completed `DONE` states by identity.
5. Choose DFS/BFS, marking timing, `null` handling, depth strategy, and memory budget according to data scale.
6. Create a dedicated state scope per traversal, and end the map's lifecycle at the right time.

**Remember:** two `equals()` objects can still be two distinct vertices in a Java object graph. `IdentityHashMap` accurately tracks each instance, while `ACTIVE`/`DONE` states distinguish a true cycle from a shared reference.