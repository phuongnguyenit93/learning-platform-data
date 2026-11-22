# Copying Structures Containing Shared or Cyclic References in Java

## 1. Goal: Copy the object graph rather than just copying each field

In Java, an object can contain references to other objects via fields, arrays, Lists, Maps, etc. A collection of these objects and references forms an **object graph**. Not every graph is a tree: two objects can reference the same child, an object can point back to an ancestor, or it can point to itself.

Example:

~~~text
        A
       / \
      B   C
       \ /
        D
        |
        +------> A
 A also has a self-pointing edge A --> A
~~~

B and C both point to **a single D instance**, not two objects with the same content. D points back to A, forming the cycle A→B→D→A; A also has a self-loop.

When copying this structure into an independent graph, we want:

- A, B, C, D in the copy to be new objects A', B', C', D'.
- If B.child and C.child both point to D in the source, B'.child and C'.child both point to **D'**.
- D'.next must point to **A'**, not back to the source A.
- A'.self must point to A' to preserve the self-loop.
- If the mutable payload of D' changes, the source D does not change.
- References that are intentionally allowed to be shared, such as an immutable String or an external service, must be explicitly specified in the copy policy.

A simple algorithm that calls `new Child(...)` whenever it encounters a child can **duplicate shared references**, **recurse infinitely on cycles**, or **mistakenly retain references to the original graph**. Therefore, proper copying must preserve both the *data values* and the *identity relationships between nodes*.

This Knowledge README is written for **Java 17+**, under Java Core → Class/Object → **Object Copying**, focusing specifically on **copying structures containing shared or cyclic references**: copy policy, identity vs equals, IdentityHashMap, memoization, the allocate→register→populate sequence, DFS/BFS, null/duplicate links, mutable nested state, heterogeneous types, final fields, snapshots using IDs, concurrency, common pitfalls, and runnable examples with exact stdout.

## 2. Core concepts: graph identity and sharing

Each reference to a Java object can be compared using the `==` operator within a valid type context. If:

~~~java
Node a = new Node("A");
Node b = new Node("B");
Node c = new Node("C");
Node d = new Node("D");

b.next = d;
c.next = d;
~~~

then `b.next == c.next` is true: B and C both hold a reference to the **D instance**. This is **aliasing**.

In the example fragment above, class Node has a `next` field and a corresponding constructor; this is an illustration rather than a standalone runnable program.

### 2.1. Identity differs from equality

- `x == y`: whether they are the same reference or not.
- `x.equals(y)`: can compare logical value if the class overrides it.
- It is entirely possible for `x != y` while `x.equals(y)` is true.
- For an algorithm that preserves graph topology, **two source objects with different references must not be merged into one solely because equals is true**.

If the graph has two nodes X1 and X2 with the same label `"X"` that are two separate instances, the copy must have **two clones** for X1 and X2 when the policy is to preserve reference topology.

### 2.2. Preserving sharing within the cloned graph differs from sharing nodes with the source

There are two types of “sharing” to distinguish:

1. **B' and C' both point to D'**: sharing **within the cloned graph**, which is what should be preserved.
2. **B' or C' still points to the original D**: sharing mutable state **between the source graph and the copied graph**, which usually violates deep copy independence.

A single `equals` comparison cannot be used to prove both requirements.

### 2.3. Cycles and self-loops

A cycle can be A→B→A or longer, or a self-loop A→A. When deep-copying under a graph-preserving policy:

~~~text
 A --> B --> A

 A' --> B' --> A'
~~~

The back edge must point to the **corresponding clone**. If a child node in the cloned graph points back to the source A, the new graph is no longer independent and the topology is wrong.

## 3. Shallow copy, deep copy, and unfolding into a tree

**Shallow copy** creates a new wrapper/root object while keeping references to the old children. For example, copying a Node with `newNode.next = oldNode.next` leaves both holding the original neighbor. If it is an immutable object or an intentionally shared collaborator, this may be appropriate; if a mutable child belongs to the graph to be copied, it is not sufficient.

**Deep copy preserving graph topology** creates clones for mutable nodes in scope and connects all references via a source→clone mapping. A source node encountered multiple times still has only **one clone**.

**Unfolding a graph into a tree** intentionally duplicates shared nodes along each path. This can be useful when outputting individual paths of a DAG, but it differs from a graph deep-copy; with cycles, a cutoff/depth-limit policy is required because infinite unfolding is impossible.

An **immutable snapshot using IDs** can represent nodes and edges using IDs instead of Java reference cycles. This is a good choice when the goal is an immutable data snapshot rather than a new mutable graph.

No single definition of deep copy such as “copy every reachable object in the JVM” fits every domain. You must clearly specify which types of fields/references belong to the copy scope and which dependencies continue to be shared.

## 4. Why is a simple tree-copying algorithm not enough?

A commonly written method is:

~~~java
Node copy(Node original) {
    if (original == null) {
        return null;
    }
    Node result = new Node(original.name);
    for (Node child : original.children) {
        result.children.add(copy(child));
    }
    return result;
}
~~~

This is a **method fragment**, assuming Node has `name`, `children`, and an appropriate constructor.

It works correctly provided the graph is truly a tree with no shared mutable nodes or cycles, and the fields that need copying have already been handled.

### 4.1. When the same D has two parents

~~~text
Source:     B ──┐
                ├──> D
            C ──┘

Naive copy: B'──> D1'
            C'──> D2'
~~~

`D1' != D2'`, even though the source only has one D. If clone D1' is modified, clone D2' does not see the change; the behavior differs from the original graph.

### 4.2. When there is a cycle

~~~text
A -> B -> D -> A -> B -> D -> ...
~~~

If previously seen nodes are not recorded, recursive copying has no stopping condition; it can cause a `StackOverflowError`. **Catching StackOverflowError is not the right way to copy a graph.**

## 5. Identity memo table: the core solution

We need a single mapping for an entire copy pass:

~~~text
Source reference     Cloned reference
A                    A'
B                    B'
C                    C'
D                    D'
~~~

In Java, the usual choice is:

~~~java
IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
~~~

`IdentityHashMap` compares keys by reference identity, not by `equals`/`hashCode` defined by the class.

### 5.1. Why not always use `HashMap<Node,Node>`?

If class Node overrides `equals` based on the label, two source instances with the same label could be treated as the same key in a HashMap. The algorithm would merge references that were originally distinct. For graph topology, that is wrong.

`IdentityHashMap` is suitable for visited-by-reference, graph copying, and cycle analysis; it does not replace HashMap in business problems requiring logical key equality.

### 5.2. Do not use name/id in place of identity by default

Two source nodes can have the same name or the same temporary business ID. If you use `Map<String,Node>` to cache copies, you risk merging two nodes with different references. When you need to **copy references**, memoize by **source object identity**. When the domain wants to merge by a stable business ID, that is a **separate normalization/deduplication operation**, not an implicit graph copy.

### 5.3. Memo is used across the entire copy session

Do not create a new memo for each child; if you do, all sharing will be lost. If you copy multiple roots of the same graph and want to preserve shared nodes across roots, use **the same memo** for all roots in the same pass.

Do not clear the memo when backtracking from recursion. A node may appear again through another branch; its clone must be reused.

## 6. The golden rule: allocate → register → populate

A correct algorithm for cycles typically follows this sequence:

1. If the input is null, return null or handle it according to the policy.
2. Check `memo`: if the source already has a clone, **return that clone immediately**.
3. If not, **allocate a clone shell** with fields that can be initialized early.
4. **Record `memo.put(source, clone)` immediately**, before following child references.
5. Copy mutable scalar/value payloads according to the ownership policy.
6. Traverse edges, connecting each cloned edge to `copy(child, memo)`.
7. Return the clone once populated.

**Registration order is key:**

~~~text
CORRECT
allocate A' -> memo[A]=A' -> copy B -> B copies A again -> reuse A'

WRONG
allocate A' -> copy B -> B copies A again -> allocate A'' -> ...
~~~

A clone that has already been placed in the memo may **still have incomplete fields/edges**; this is an intentional mechanism to handle backreferences. Therefore, do not publish the clone to observers/callbacks before the entire graph copy is complete.

## 7. Complete Program 1: DFS with `IdentityHashMap` preserving cycles and sharing

Create the file **`GraphDeepCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class GraphDeepCopyDemo {
    static final class Node {
        private String name;
        private final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = Objects.requireNonNull(name);
        }

        Node add(Node next) {
            links.add(next);
            return this;
        }

        String name() {
            return name;
        }

        void rename(String next) {
            name = Objects.requireNonNull(next);
        }
    }

    static Node deepCopy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    private static Node copy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        Node target = new Node(source.name);
        memo.put(source, target); // Before following links.

        for (Node neighbor : source.links) {
            target.links.add(copy(neighbor, memo));
        }
        return target;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");

        a.add(b).add(c).add(a);
        b.add(d);
        c.add(d);
        d.add(a);

        Node copiedA = deepCopy(a);
        Node copiedB = copiedA.links.get(0);
        Node copiedC = copiedA.links.get(1);
        Node copiedDfromB = copiedB.links.get(0);
        Node copiedDfromC = copiedC.links.get(0);

        System.out.println("Root independent = " + (copiedA != a));
        System.out.println("Shared D = "
                + (copiedDfromB == copiedDfromC));
        System.out.println("Cycle to cloned root = "
                + (copiedDfromB.links.get(0) == copiedA));
        System.out.println("Self-loop = "
                + (copiedA.links.get(2) == copiedA));
        System.out.println("D independent = "
                + (copiedDfromB != d));

        copiedDfromB.rename("D-copy");
        System.out.println("Original D = " + d.name());
        System.out.println("Copied D = " + copiedDfromC.name());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 GraphDeepCopyDemo.java
java GraphDeepCopyDemo
~~~

**Exact stdout:**

~~~text
Root independent = true
Shared D = true
Cycle to cloned root = true
Self-loop = true
D independent = true
Original D = D
Copied D = D-copy
~~~

### 7.1. Copying step for A

When `copy(A)` starts, the algorithm creates A' and **stores memo[A] = A'**. It then traverses A→B. B' is created, memoized, and then B→D; D' is created. D→A encounters A, which is already in the memo, so D' points to A'. The recursion cycle back to A terminates normally.

### 7.2. Copying step for C

When the algorithm returns to A and traverses A→C, C' is created. C→D encounters D, which already has clone D'; C' is connected to the **same D'** that B' points to. Finally, A→A is remapped to A'→A'.

### 7.3. Why does mutation produce the correct result?

`copiedDfromB == copiedDfromC` is true, so modifying D' through path B' can be observed through path C'. `copiedDfromB != d` is true, so the source D still has the name `"D"`, while D' has the name `"D-copy"`. The copy both protects independence and preserves the aliasing topology.

### 7.4. Recursion limits

With V reachable nodes and E reachable edges, the algorithm visits each node once and each edge once: expected time is **O(V+E)** with average constant-time lookups, memo O(V), and cloned structure O(V+E). However, the call stack can reach O(depth); a very long graph, even without cycles, can still cause a `StackOverflowError`. When depth is large or untrusted, use iterative BFS/DFS.

## 8. Complete Program 2: Naive copy preserves values but loses sharing

To isolate the shared reference bug, use a **DAG without cycles**. Both the naive and memoized algorithms run to completion, but only the memoized one preserves the correct topology.

Create the file **`SharingPreservationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class SharingPreservationDemo {
    static final class Node {
        final String label;
        final List<Node> children = new ArrayList<>();

        Node(String label) {
            this.label = label;
        }

        Node add(Node next) {
            children.add(next);
            return this;
        }
    }

    static Node naiveCopy(Node source) {
        if (source == null) {
            return null;
        }
        Node result = new Node(source.label);
        for (Node child : source.children) {
            result.children.add(naiveCopy(child));
        }
        return result;
    }

    static Node smartCopy(Node source) {
        return smartCopy(source, new IdentityHashMap<>());
    }

    private static Node smartCopy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }
        Node result = new Node(source.label);
        memo.put(source, result);
        for (Node child : source.children) {
            result.children.add(smartCopy(child, memo));
        }
        return result;
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node left = new Node("left");
        Node right = new Node("right");
        Node shared = new Node("shared");

        root.add(left).add(right);
        left.add(shared);
        right.add(shared);

        Node naive = naiveCopy(root);
        Node proper = smartCopy(root);

        Node naiveLeft = naive.children.get(0).children.get(0);
        Node naiveRight = naive.children.get(1).children.get(0);
        Node goodLeft = proper.children.get(0).children.get(0);
        Node goodRight = proper.children.get(1).children.get(0);

        System.out.println("Source shared = "
                + (left.children.get(0) == right.children.get(0)));
        System.out.println("Naive preserves sharing = "
                + (naiveLeft == naiveRight));
        System.out.println("Memo preserves sharing = "
                + (goodLeft == goodRight));
        System.out.println("Clone independent = "
                + (goodLeft != shared));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 SharingPreservationDemo.java
java SharingPreservationDemo
~~~

**Exact stdout:**

~~~text
Source shared = true
Naive preserves sharing = false
Memo preserves sharing = true
Clone independent = true
~~~

**Important:** the naive version still creates clones separate from the source; however, because it copies the shared node twice, it **is no longer a topology-preserving graph**. If the API intentionally aims to “unfold each branch into an independent tree”, this behavior may be correct, but the contract must be stated clearly and infinite cycles must be avoided.

## 9. Complete Program 3: Two `equals` nodes are not the same source reference

A regular `HashMap` memo can merge two nodes if the class overrides `equals` based on data. The following program intentionally creates two instances with label X and verifies that `IdentityHashMap` does not merge them.

Create the file **`IdentityMemoDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class IdentityMemoDemo {
    static final class Node {
        final String label;
        final List<Node> edges = new ArrayList<>();

        Node(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node n && label.equals(n.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    static Node copy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        Node cloned = new Node(source.label);
        memo.put(source, cloned);
        for (Node edge : source.edges) {
            cloned.edges.add(copy(edge, memo));
        }
        return cloned;
    }

    public static void main(String[] args) {
        Node root = new Node("R");
        Node firstX = new Node("X");
        Node secondX = new Node("X");
        root.edges.add(firstX);
        root.edges.add(secondX);

        IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
        Node clonedRoot = copy(root, memo);

        System.out.println("Values equal = "
                + firstX.equals(secondX));
        System.out.println("References distinct = "
                + (firstX != secondX));
        System.out.println("Copied nodes distinct = "
                + (clonedRoot.edges.get(0)
                        != clonedRoot.edges.get(1)));
        System.out.println("Not original X = "
                + (clonedRoot.edges.get(0) != firstX));
        System.out.println("Memo count = " + memo.size());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 IdentityMemoDemo.java
java IdentityMemoDemo
~~~

**Exact stdout:**

~~~text
Values equal = true
References distinct = true
Copied nodes distinct = true
Not original X = true
Memo count = 3
~~~

Both firstX and secondX have true logical equality (because both have label X) but different identities. The memo contains Root, firstX, and secondX, producing three clones. Copying an object graph by references must not be mixed with the business operation to **deduplicate by value**.

## 10. Recursive DFS or iterative BFS/DFS?

A recursive algorithm with a memo handles cycles but can still cause a stack overflow on a long chain. A **work queue** allows performing an iterative BFS:

1. Clone the root, put root→clone into the memo, and add the root to the queue.
2. Take a source node from the queue.
3. Retrieve the corresponding clone from the memo.
4. Iterate over each neighbor:
   - If null, handle null according to the policy.
   - If the neighbor is not yet in the memo, create a clone and add it to the queue.
   - Add an edge pointing to the **neighbor's clone**.
5. Repeat until the queue is empty, then return the cloned root.

All clone allocations and registrations occur **before the node is used as a neighbor in the cloned graph**, so backreferences do not cause infinite loops.

### 10.1. Complete Program 4: BFS with cycles, shared nodes, and null/duplicate edges

Create the file **`IterativeGraphCopyDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class IterativeGraphCopyDemo {
    static final class Node {
        String id;
        final List<Node> edges = new ArrayList<>();

        Node(String id) {
            this.id = id;
        }

        Node add(Node next) {
            edges.add(next);
            return this;
        }
    }

    static Node copyGraph(Node root) {
        if (root == null) {
            return null;
        }

        IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
        ArrayDeque<Node> pending = new ArrayDeque<>();

        memo.put(root, new Node(root.id));
        pending.add(root);

        while (!pending.isEmpty()) {
            Node original = pending.removeFirst();
            Node cloned = memo.get(original);

            for (Node neighbor : original.edges) {
                if (neighbor == null) {
                    cloned.edges.add(null);
                    continue;
                }

                if (!memo.containsKey(neighbor)) {
                    memo.put(neighbor, new Node(neighbor.id));
                    pending.addLast(neighbor);
                }
                cloned.edges.add(memo.get(neighbor));
            }
        }

        return memo.get(root);
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");

        a.add(b).add(c).add(b).add(null);
        b.add(d);
        c.add(d);
        d.add(a);

        Node clonedA = copyGraph(a);
        Node clonedB = clonedA.edges.get(0);
        Node clonedC = clonedA.edges.get(1);
        Node clonedD = clonedB.edges.get(0);

        System.out.println("Duplicate edge preserved = "
                + (clonedA.edges.get(0) == clonedA.edges.get(2)));
        System.out.println("Shared D = "
                + (clonedD == clonedC.edges.get(0)));
        System.out.println("Cycle to cloned A = "
                + (clonedD.edges.get(0) == clonedA));
        System.out.println("Null preserved = "
                + (clonedA.edges.get(3) == null));
        System.out.println("Independent root = " + (clonedA != a));

        clonedB.id = "B-copy";
        System.out.println("Original B = " + b.id);
        System.out.println("Cloned B = " + clonedB.id);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 IterativeGraphCopyDemo.java
java IterativeGraphCopyDemo
~~~

**Exact stdout:**

~~~text
Duplicate edge preserved = true
Shared D = true
Cycle to cloned A = true
Null preserved = true
Independent root = true
Original B = B
Cloned B = B-copy
~~~

### 10.2. Why is null not enqueued?

`ArrayDeque` does not accept null values. If the graph policy permits null edge slots, the copy preserves null in the cloned List instead of putting null into the queue. If the domain forbids null edges, you should validate and throw an exception rather than silently ignoring them.

### 10.3. Complexity and practical limits

With V reachable nodes and E edges, memoized DFS/BFS has expected time **O(V+E)**, O(V) memo, and O(V+E) copied structure. Iterative BFS avoids a deep Java call stack, but the queue can take O(V) and heap memory must still be sufficient. If the object graph is extremely large, memory/size limits are needed or you should switch to streaming immutable snapshots.

## 11. Copy mutable payloads, not just remap edges

A graph clone that correctly preserves A'→B' but still shares a mutable `byte[]`, `Date`, or `List<MutableItem>` with the source may still not be independent.

Example:

~~~java
class Node {
    byte[] data;
    List<Node> edges;
}
~~~

If `clone.data = original.data`, a caller mutating bytes in the clone will change the source. There must be a per-field policy:

- `String`, `Instant`, immutable value classes: can be reused.
- Primitive fields: copy values.
- `byte[]`, `int[]`: clone/copy arrays.
- `List<Node>`: create a new List and remap each Node through the memo.
- `Map<String,Node>`: create a new Map, remap values.
- `List<MutableItem>`: copy the List and each Item when the Item is within the mutable ownership scope.
- Services/resources: typically not deep-cloned automatically.
- Final references: can still point to mutable content; final is not automatically deeply immutable.

### 11.1. Complete Program 5: Copy both payload and self-cycle

Create the file **`GraphPayloadCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class GraphPayloadCopyDemo {
    static final class Node {
        final String name;
        private final byte[] payload;
        private final List<Node> edges = new ArrayList<>();

        Node(String name, byte[] input) {
            this.name = Objects.requireNonNull(name);
            payload = Objects.requireNonNull(input).clone();
        }

        byte[] payload() {
            return payload.clone();
        }
    }

    static Node deepCopy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    private static Node copy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        Node target = new Node(source.name, source.payload);
        memo.put(source, target);
        for (Node edge : source.edges) {
            target.edges.add(copy(edge, memo));
        }
        return target;
    }

    public static void main(String[] args) {
        byte[] external = {1, 2};
        Node source = new Node("A", external);
        source.edges.add(source);

        external[0] = 9;
        Node cloned = deepCopy(source);

        // Only the enclosing demo can access the private payload for testing.
        cloned.payload[0] = 7;

        System.out.println("Source payload = "
                + Arrays.toString(source.payload()));
        System.out.println("Cloned payload = "
                + Arrays.toString(cloned.payload()));
        System.out.println("Arrays independent = "
                + (source.payload != cloned.payload));
        System.out.println("Cloned self-cycle = "
                + (cloned.edges.get(0) == cloned));
        System.out.println("Nodes independent = "
                + (source != cloned));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 GraphPayloadCopyDemo.java
java GraphPayloadCopyDemo
~~~

**Exact stdout:**

~~~text
Source payload = [1, 2]
Cloned payload = [7, 2]
Arrays independent = true
Cloned self-cycle = true
Nodes independent = true
~~~

The Node constructor copies the input byte array, so modifying `external` does not affect the source Node. The graph copier creates a new Node via the constructor, so the cloned payload is also a separate byte array. The `payload()` getter returns a copy without exposing internals. The enclosing demo intentionally modifies the cloned Node's private payload to prove that the source remains unchanged; this is not a recommendation to provide a public mutable accessor.

## 12. Immutable snapshots using IDs: representing shared references and cycles without object cycles

Users do not always need a **new mutable graph**. When you need to store, export data, or capture state at a point in time, you can use an **immutable graph snapshot**:

~~~text
Node 1: A, outgoing=[2,3,2]
Node 2: B, outgoing=[1]
Node 3: C, outgoing=[2]
~~~

- Node 1 has two edges pointing to node 2: duplicate links are still preserved.
- Node 2 points to node 1: a cycle.
- No need for Java records to directly hold cyclic references.
- Every outgoing ID can be validated to exist.
- The graph can be modeled as immutable records/collections.

### 12.1. Complete Program 6: Graph snapshot with records

Create the file **`GraphIdSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class GraphIdSnapshotDemo {
    record NodeView(int id, String name, List<Integer> outgoing) {
        NodeView {
            if (id < 1) {
                throw new IllegalArgumentException("ID không hợp lệ");
            }
            Objects.requireNonNull(name);
            outgoing = List.copyOf(outgoing);
        }
    }

    record Snapshot(Map<Integer, NodeView> nodes, int rootId) {
        Snapshot {
            nodes = Map.copyOf(nodes);
            if (!nodes.containsKey(rootId)) {
                throw new IllegalArgumentException("Thiếu root");
            }
            for (Map.Entry<Integer, NodeView> e
                    : nodes.entrySet()) {
                if (e.getKey() != e.getValue().id()) {
                    throw new IllegalArgumentException("ID mismatch");
                }
                for (int next : e.getValue().outgoing()) {
                    if (!nodes.containsKey(next)) {
                        throw new IllegalArgumentException("Dangling edge");
                    }
                }
            }
        }

        NodeView root() {
            return nodes.get(rootId);
        }
    }

    public static void main(String[] args) {
        List<Integer> edges = new ArrayList<>(List.of(2, 3, 2));
        Map<Integer, NodeView> input = new HashMap<>();

        input.put(1, new NodeView(1, "A", edges));
        input.put(2, new NodeView(2, "B", List.of(1)));
        input.put(3, new NodeView(3, "C", List.of(2)));

        Snapshot snapshot = new Snapshot(input, 1);

        edges.add(1);
        input.clear();

        System.out.println("Root = " + snapshot.root().name());
        System.out.println("Outgoing = " + snapshot.root().outgoing());
        System.out.println("Unique nodes = "
                + snapshot.nodes().size());
        System.out.println("Cycle to root = "
                + (snapshot.nodes().get(2).outgoing().get(0)
                        == snapshot.rootId()));
        System.out.println("Duplicate link = "
                + snapshot.root().outgoing().get(0).equals(
                        snapshot.root().outgoing().get(2)));

        try {
            snapshot.root().outgoing().add(4);
        } catch (UnsupportedOperationException ex) {
            System.out.println("Edges unmodifiable");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GraphIdSnapshotDemo.java
java GraphIdSnapshotDemo
~~~

**Exact stdout:**

~~~text
Root = A
Outgoing = [2, 3, 2]
Unique nodes = 3
Cycle to root = true
Duplicate link = true
Edges unmodifiable
~~~

### 12.2. Why is the snapshot here immutable by contract?

`NodeView` contains primitives, an immutable String, and an unmodifiable List snapshot of Integer IDs. `Snapshot` captures the outer Map via `Map.copyOf`. If the caller modifies `edges` or `input` after construction, it does not change the internal snapshot. Generated record accessors return appropriate immutable references.

Do not assume `Map.copyOf` preserves the source's insertion order, so the program only looks up by ID and prints the List with explicit order. If the Map values are mutable objects, `Map.copyOf` will **not deep-copy** them; the representation must be controlled at every layer.

### 12.3. Copying a graph using IDs and identity mapping

If the input is an object-reference graph, the snapshot creation process needs to map **source reference → generated integer ID** by identity. When encountering the same reference again, reuse the ID to preserve sharing/cycles; for two distinct source instances even if equals is true, the IDs must differ if preserving topology is the goal.

Storing IDs in a snapshot does not mean using `System.identityHashCode` as a long-term ID. `identityHashCode` is not guaranteed to be unique. You should assign IDs per controlled traversal/session or use stable domain IDs if the contract allows.

## 13. Graphs composed of multiple concrete classes

A real graph often contains multiple object types:

~~~text
Order --> Customer
  |
  +----> Line --> Product
                  |
                  +--> Price
~~~

There may be `Order`, `Customer`, and `Product` with different constructors and fields. A copier that always calls `new BaseNode(...)` will lose subtype-specific state/behavior.

Approach:

1. Identify the set of supported types.
2. Allocate a clone shell of the **exact concrete type** or an appropriate immutable DTO.
3. Record source→clone in the **shared memo** before populating references.
4. Copy scalar fields and mutable components according to the policy.
5. Remap outgoing links to clones using the same memo.
6. After the graph is complete, validate invariants and publish the root.

### 13.1. `final` fields make two-phase construction harder

A class with `private final Node parent` does not allow creating an empty shell and then assigning the parent field in any instance method. For cycles in final references, you may need:

- Builders/a wiring stage that then creates another representation.
- An ID-based snapshot, avoiding directly creating a reference cycle.
- Indirection through a carefully designed holder.
- A copy factory that supports its own construction order and invariants.

Do not use reflection/Unsafe to modify final fields outside the language rules as a default solution; that breaks encapsulation, module access, and can cause memory visibility issues.

### 13.2. Constructors with side effects

Copying a domain entity with its normal constructor may emit events, generate IDs, open resources, or register into a registry. If only a snapshot is needed, those side effects are usually wrong. Design a **dedicated copy constructor/factory** with a clear contract, or convert to immutable DTOs.

### 13.3. Should business identity be kept or changed?

`source != cloned` only proves that reference identity is different. It does not by itself determine whether **CustomerId, OrderId, or database ID** must differ. If the clone is a snapshot of the same entity, keeping the ID may be right. If the clone creates a new business entity, a new ID and updating all relationships may be required. Decide based on the domain, not on the graph algorithm.

## 14. Collections in a graph: List, Set, Map, arrays

### 14.1. List

Clone a new outer List, iterating through each element in sequence:

~~~java
for (Node n : source.links) {
    target.links.add(copy(n, memo));
}
~~~

Preserve **order**, **null slots** if allowed, and **duplicate edges**. Converting a List to a Set will change semantics when the source has a repeated edge.

### 14.2. Arrays

For `Node[]`, create a new array of the same length and remap each slot via the memo; simply calling `sourceArray.clone()` will shallow-copy the Node references without cloning the graph.

For primitive arrays such as `byte[]`, cloning each array may be sufficient because the elements do not contain references.

### 14.3. Map

`Map<String,Node>`: create a new Map; String keys are immutable, and Node values are remapped via the memo. If iteration order is part of the contract, choose an appropriate Map implementation/order contract; do not assume every HashMap has a stable iteration order.

`Map<Node,Node>`: consider remapping **both keys and values**. Choose the map type according to the logical/identity equality of the new graph.

### 14.4. Set and mutable keys

If Node.equals/hashCode depends on fields that have not yet been populated, inserting the cloned Node into a `HashSet`/`HashMap` **before those fields stabilize** can cause mutable hash key bugs. Solutions:

- Populate equality-relevant fields before inserting into a hash collection.
- Use an identity-based Set/Map if the relation is defined by identity.
- Use immutable IDs/keys for the output collection.

The `IdentityHashMap` memo is only an internal tracking table; **it does not require the cloned business Map to also use IdentityHashMap**.

## 15. Graphs with multiple roots or disconnected components

A `deepCopy(root)` only copies **reachable nodes** along the edges traversed by the algorithm. If a component is not reachable from the root, it is not automatically copied.

If you need to copy multiple roots and preserve sharing between them, you must use the same memo:

~~~java
IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
Node copiedFirst = copy(firstRoot, memo);
Node copiedSecond = copy(secondRoot, memo);
~~~

This is a fragment, assuming the `copy` method and Node class exist. If you use a separate memo for each root, a shared descendant may be cloned twice, losing sharing between intersecting components.

### 15.1. Null roots and dangling references

The API may define `deepCopy(null) == null` or throw an exception, depending on the contract. With ID snapshots, an outgoing ID that does not exist in the nodes table is a **dangling edge** and must be validated or explicitly permitted to represent an external link according to a clear schema.

### 15.2. Recursive processing does not clear the memo on return

The memo serves the **entire copy session**, not a local recursion path. If you remove the mapping after a node finishes processing, another node reaching it via a different path will clone it again; sharing is lost.

## 16. Speed, stack, and memory

For a graph with V nodes and E edges:

- Standard memoized DFS/BFS traverses each node once and each edge once: expected **O(V+E)** time when identity lookup is O(1) on average.
- The memo requires O(V) references; cloned edges require O(E) memory.
- Recursive DFS has an O(depth) call stack and can hit a StackOverflowError on very deep graphs.
- Iterative BFS avoids recursion-stack growth, but the queue can take O(V).
- Cloning mutable payload arrays/collections adds time and memory proportional to the size of the payloads.
- An overly large graph can still cause an `OutOfMemoryError`; iterative traversal is not immune to memory limits.

**Do not copy a huge graph just to return a few fields** if an immutable projection/snapshot of the needed portion suffices. Evaluate performance based on actual workload and input bounds.

## 17. Concurrency: a correct memo alone does not guarantee a consistent snapshot

If other threads modify the graph while the copier is traversing:

- A is copied before an edge changes, while B is copied after the change.
- A List can change mid-iteration.
- A mutable payload can be modified while being copied.
- The new graph may combine data from multiple points in time, not corresponding to any atomic snapshot.

`IdentityHashMap` only resolves the **identity/topology of the references observed by the copier**; it does not resolve data races or provide an atomic snapshot.

You may need:

1. The entire graph protected by the owner using a read/write lock with the same protocol.
2. Immutable/versioned graph state, taking a snapshot of a single version.
3. A transactional read from persistence if the graph originates from a database.
4. Optimistic version validation capable of detecting all relevant changes.
5. Copy-on-write if most of the data is immutable.

Putting `volatile` on a single edge field does not make multi-node traversal atomic. A builder/copier should also not publish the cloned root before its edges have been populated and invariants checked.

## 18. External resources and ownership

An object graph may contain references to:

- Database Connection, transaction/session.
- Socket, file channel, InputStream/OutputStream.
- Thread, ExecutorService, locks.
- Logger, cache, dependency injection service.
- Native handles or resources outside the JVM.

These should generally **not be deep-cloned unconditionally**. Copying a String reference to a file path does not copy the file contents. Copying an object holding a Connection does not create an equivalent database transaction.

Choose a clear policy:

- **Share the service reference** because it is a dependency outside the copy scope.
- **Omit the resource** from an immutable snapshot.
- **Rebind/reinject** the resource from the owner.
- **Copy an immutable resource descriptor/ID** rather than copying a live handle.
- **Transfer ownership** instead of copying if the API allows it.

For locks, copying a monitor object can alter coordination semantics; keeping the same lock makes the clone depend on the source. Therefore, concurrency resources must be treated as a special case, not like ordinary mutable data.

## 19. Errors and partial copies

If a clone's constructor throws an exception mid-copy:

- The memo may contain partially initialized clones.
- The graph is still incomplete.
- Callers must not receive the clone as a successful result.
- External side effects that already occurred do not roll back automatically because of a Java exception.

Practical design:

- Use a local memo that exists only for a single copy operation.
- Validate inputs/schema before publishing.
- Use copy constructors/factories with minimal side effects.
- If copying creates resources, have an appropriate cleanup/close policy.
- Do not mutate the source graph while building the copy.
- Return the cloned root **only after the entire copy completes normally**.

A cloned graph object **should not escape** via an event, callback, or global registry before wiring completes; otherwise, another thread could observe incomplete edges.

## 20. Do `clone()` and serialization solve the problem automatically?

### 20.1. `Object.clone()` is usually shallow

If a class implements Cloneable and uses `super.clone()`, it usually produces a shallow copy of fields. A `Node next` can still point to the source child. For cycles and sharing, a memo and remapping are required; calling `child.clone()` recursively without a memo can still loop infinitely or duplicate a shared node.

### 20.2. Copy constructors do not handle cycles automatically

A `new Node(oldNode)` that accepts fields can be useful for copying scalar/mutable payloads, but if the constructor recursively creates children before registering the clone in the memo, the cycle problem remains. A copy constructor only handles the fields and constructor graph protocol it was designed to support.

### 20.3. Java serialization round-trip is not a universal deep copy

Serialization can preserve sharing/cycles of serializable object graphs under appropriate conditions and hooks, but:

- Not every class/resource is serializable.
- `transient`/`static` fields and custom hooks have specific behaviors.
- Deserialization of untrusted data carries security risks.
- Constructors, invariants, and compatibility must be considered.
- External resources and business identity are not automatically copied correctly.

Native serialization should not be treated as a default copy strategy. Explicit mapping or ID snapshots are usually more transparent.

## 21. Testing graph copies: `==` must be used in the right places

A `source.equals(clone)` test may pass even when sharing/cycles are wrong, because equals often compares only a few scalar fields. You should verify:

1. **Independence:** copied root != original root; cloned mutable nodes differ from all original mutable nodes within the copy scope.
2. **Preserved sharing:** if two source edges share the same target, the two cloned edges share the same target via `==`.
3. **Preserved cycles:** a clone's back edge points to the cloned ancestor, not to the source.
4. **Self-loop:** clonedSelf == clonedRoot.
5. **Repeated edges:** Lists preserve exact positions and references.
6. **Null edges:** null slots remain intact according to policy.
7. **Scalar values:** corresponding labels/data values match.
8. **Mutable payload isolation:** modifying the clone does not change the source, and vice versa if the source can still be mutated.
9. **Equals-equal but reference-distinct nodes:** are not merged.
10. **Multiple roots:** shared descendants are reused when sharing a memo.
11. **Very deep chain:** choose an iterative approach to avoid stack overflow.
12. **Concurrency:** if the snapshot must be atomic, include tests/validation for the locking/versioning protocol.

### 21.1. Mutation test for sharing

In the source graph, if B and C both point to D, the copy must make B' and C' point to the same D'. Then modify D' via B', and reading D' via C' sees the new value; the source D retains the old value.

This is a stronger test than just comparing the names of B'/C' because it verifies **aliasing behavior**.

### 21.2. One source node ↔ one clone node

A topology-preserving graph-copy mapping must neither create two clones for the same source reference nor merge two distinct source references. It is a bijection within the scope of copied mutable nodes.

## 22. Strategy comparison table

| Strategy | Preserves shared references | Handles cycles | Cost/limits |
| --- | --- | --- | --- |
| Shallow copy | Shares with **source** | May keep links back to source | Not independent of mutable children |
| Naive copy tree | Not guaranteed | Can be infinite | Only suitable for true trees |
| Memoized DFS | Yes | Yes | Recursion stack can become deep |
| Memoized iterative BFS/DFS | Yes | Yes | Queue/memo consumes memory |
| Immutable ID snapshot | Via repeated IDs | Via ID links | Requires schema/ID mapping/validation |
| Domain-specific mapper | Per policy | When designed for it | Must define type/field semantics |
| Serialization round-trip | Depends on mechanism | Possible | Security/compatibility/resource constraints |
| Persistent immutable graph | Intentional structural sharing | Depends on data model | Custom design, updated by versions |

## 23. Common mistakes

1. Using naive recursion for a graph with cycles.
2. Registering in the memo after cloning children.
3. Using a `HashMap` memo when Node.equals can merge distinct references.
4. Using a label or mutable business ID as the source's identity.
5. Creating a separate memo for each child/root even when graphs share descendants.
6. Using a visited Set without storing source→clone references.
7. Clearing the memo when backtracking from recursion.
8. Failing to remap self-loops/back edges to the cloned node.
9. Copying the outer List while keeping source Node references.
10. Failing to copy mutable payload arrays/Date/nested Lists.
11. Unnecessarily copying immutable Strings.
12. Using a Set to replace a List of edges, losing duplicates/order.
13. Not handling null edges and enqueueing null into an ArrayDeque.
14. Using recursive DFS on a graph with a very long chain, hitting stack overflow.
15. Using BFS but forgetting the memo, still duplicating nodes/cycles.
16. Copying Maps with wrong key/value semantics, especially mutable hash keys.
17. Using a domain constructor that triggers event/registry side effects when only a snapshot is wanted.
18. Choosing the clone type from a compile-time superclass, losing subtype fields.
19. Trying to populate final cyclic references via reflection/Unsafe.
20. Deep-cloning external resources that have no copy contract.
21. Changing business IDs arbitrarily when copying.
22. Publishing a clone before the graph is complete.
23. Treating identity memoization as an atomic snapshot mechanism under concurrent graph mutation.
24. Comparing with `equals` instead of `==` in topology tests.
25. Assuming Object.clone automatically performs a deep copy.
26. Using native serialization with untrusted data.
27. Failing to validate dangling IDs when using an ID-based snapshot.
28. Relying on the iteration order of Map.copyOf.
29. Not handling partially created nodes if copying fails.
30. Failing to explicitly specify the copy scope and shared resources.

## 24. Self-check exercises with answers

**Question 1.** B and C both point to D in the source graph. In a topology-preserving clone, what relationship is required?

**Answer:** B'.link == C'.link and both point to a D' distinct from the source D.

**Question 2.** Why must `memo.put(source, clone)` be called before traversing children?

**Answer:** So that backreferences/cycles find the already allocated clone, avoiding creating another clone and avoiding infinite recursion.

**Question 3.** Why is `IdentityHashMap` more suitable than `HashMap` for a graph-copy memo?

**Answer:** It uses reference identity as the key, so it does not merge two source instances simply because equals is true.

**Question 4.** Does `a.equals(b)` being true prove a==b?

**Answer:** No. Value equality differs from identity.

**Question 5.** Can a graph copy return the original immutable String label and still be a valid deep copy?

**Answer:** Yes, if the copy policy allows reusing immutable values. There is no need to duplicate immutable strings.

**Question 6.** Is copying a List of Nodes with `new ArrayList<>(source.links)` enough?

**Answer:** No if the Nodes need to be cloned; the new List still holds references to the source nodes.

**Question 7.** A points to itself; how should it be cloned?

**Answer:** A' must point to A' itself: `A'.self == A'`.

**Question 8.** With A→B→A, what can happen with naive recursion?

**Answer:** Non-termination/stack overflow if there is no memo or cycle policy.

**Question 9.** Does the memo need to be shared across multiple roots that have shared descendants?

**Answer:** Yes, if you want to preserve sharing across those cloned roots.

**Question 10.** Can memoized DFS cause a stack overflow?

**Answer:** Yes, when graph depth is very large; the memo prevents cycles, but it does not eliminate the call stack.

**Question 11.** Does iterative BFS need a memo?

**Answer:** Yes, to reuse clones and avoid infinite loops.

**Question 12.** Does ArrayDeque accept null entries?

**Answer:** No. Handle null edges separately.

**Question 13.** If the source List contains [B,C,B], what does the clone need?

**Answer:** [B',C',B'] with two references to B' having the same identity.

**Question 14.** If clone D' shares a `byte[]` payload with the source D, is it independent yet?

**Answer:** Not for a mutable payload; the array must be copied appropriately.

**Question 15.** Why does cloning a graph not necessarily clone a database Connection?

**Answer:** A Connection is a resource with a lifecycle/ownership; deep-copying in-heap objects does not mean copying a transaction/service.

**Question 16.** The source graph has two distinct nodes with the same label. What should the memo do?

**Answer:** Create two separate clones if the goal is to preserve reference identity.

**Question 17.** Can a cyclic `final Node parent` relationship make shell-then-populate difficult?

**Answer:** Yes; final assignment constraints may require a builder, indirection, or an ID representation.

**Question 18.** Can copying a graph using an immutable ID snapshot represent cycles?

**Answer:** Yes, through edges containing IDs that point back to an existing node.

**Question 19.** Does Map.copyOf automatically deep-copy mutable NodeView values?

**Answer:** No. Values must be immutable or copied according to policy.

**Question 20.** If a graph is modified by another thread during copying, does IdentityHashMap provide an atomic snapshot?

**Answer:** No. Appropriate locking, versioning, or immutable graph state is required.

**Question 21.** What is the typical time complexity for memoized traversal?

**Answer:** Expected O(V+E) when each node/edge is processed once and identity lookup is O(1) on average.

**Question 22.** Is `source != clone` sufficient to prove a deep copy?

**Answer:** No; cloned neighbors/payloads may still point to the source.

**Question 23.** What needs to be checked besides labels?

**Answer:** Sharing via ==, cycles, independence via !=, repeated/null edges, and mutable payload isolation.

**Question 24.** If a copy constructor produces a database event, what is the risk?

**Answer:** Copying the graph duplicates side effects even when only a snapshot is intended; use a copy factory without those effects.

**Question 25.** Is a source node outside the portion reachable from the root copied by `copy(root)`?

**Answer:** No, unless the API selects additional roots or traverses other references.

**Question 26.** Why shouldn't the memo be cleared when entering a new branch?

**Answer:** A source node may be encountered again in another branch; clearing would duplicate the cloned node.

**Question 27.** What happens if a HashMap in a cloned graph uses a mutable clone still being populated as a key?

**Answer:** You should not insert it before equality/hash-relevant fields stabilize; it can cause stale hash lookups.

**Question 28.** When should an ID-based snapshot be used instead of a mutable graph?

**Answer:** When the goal is to store, report, or compare an immutable state, validate references, and represent cycles/sharing more easily.

**Question 29.** Does copying a graph require assigning new business IDs?

**Answer:** No; copy reference identity differs from domain identity. It must follow whether the intent is a snapshot or creating a new entity.

**Question 30.** What core principle prevents both duplicating shared nodes and cyclic recursion?

**Answer:** Using a shared source identity→clone mapping, **registering the clone before following references**.

## 25. Design checklist before copying an object graph

1. Does the graph have shared references?
2. Are there cycles/self-loops/backreferences?
3. Are there null edges or duplicate links?
4. Do you want to copy the graph topology or unfold paths into a tree?
5. Has the scope of nodes/edges to copy been defined?
6. Does the memo use source reference identity?
7. Is allocate→register→populate performed in the right order?
8. Is the memo shared across the entire session/multiple roots?
9. Are all graph links remapped to clones?
10. Are arrays, Lists, Maps, and nested mutable payloads copied appropriately?
11. Are immutable values intentionally shared?
12. Are there external resources/services that should not be cloned?
13. Are there heterogeneous subclasses whose runtime type must be preserved?
14. Are there final fields or cyclic construction constraints?
15. Do constructors have side effects that should be avoided?
16. Are cloned HashMap/HashSet keys stable before insertion?
17. Is an iterative queue used when depth can be very large?
18. Are there V/E/memory limits for untrusted input?
19. Is there a concurrency snapshot/locking policy?
20. Are partially built clones prevented from escaping?
21. Is there an error/rollback/cleanup policy?
22. Does copying keep or assign new business IDs according to the domain?
23. Do tests use == and != to check graph identity?
24. Do tests verify shared targets and cycles properly?
25. Do tests verify mutation isolation for mutable payloads?
26. Are null/dangling IDs validated for immutable snapshots?
27. Is reliance on the iteration order of unordered Maps avoided?
28. Are the clone method, serialization, and a true graph copy distinguished?
29. Is it documented which fields are copied and which fields are shared?
30. Is reliance on reflection/Unsafe to bypass final fields avoided?

## Conclusion

**Copying structures containing shared or cyclic references** requires preserving **identity topology**, not just copying values. A source node must be allocated only one cloned node within the copy scope; repeated references must all point to that cloned node, and cycles must point back to clones rather than the original objects.

In Java 17+, a common approach is **`IdentityHashMap<Source,Clone>`** combined with the **allocate → memoize → populate** order, then traversing the graph using DFS or BFS. Memoization avoids infinite recursion from cycles and preserves shared references. Recursive DFS is simpler but can overflow the call stack on deep graphs; iterative BFS/DFS handles large depths while still requiring O(V) memo space and memory for the new graph.

Equally important is the **copy policy**: arrays/collections/nested mutable state must be copied when owned by the graph; immutable values can be shared; services/resources and business IDs require separate decisions. If the goal is an immutable snapshot, a nodes-by-ID representation can preserve sharing/cycles without needing mutable reference cycles. Finally, test **reference identity, cycles, duplicate edges, and mutation isolation** — these are checks that calling `equals()` on the root cannot replace.
