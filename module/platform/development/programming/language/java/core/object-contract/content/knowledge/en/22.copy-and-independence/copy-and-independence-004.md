# Shared References and Cycles in Object Graphs (Java)

**Context:** Copying and independence. When copying a Java object, you need to look at the entire network of objects it points to, because a copy of the root object is not necessarily independent of the original.

## 1. What Is an Object Graph?

An **object graph** can be visualized as follows:

- **Node:** an object in memory.
- **Edge:** a reference field, array element, or collection element pointing to another object.
- **Root:** the reference from which traversal starts, for example a `customer` or `head` variable.
- **Identity:** two references pointing to *the exact same object*, checked with `==`; different from `equals()`, which may check value according to the class's convention.

A graph is not required to be a tree: multiple edges can reach the same node, and a node can point back to itself or return to an already visited node.

~~~text
A.next --------> B
^                 |
|                 |
+------ B.next ---+

A.shared ---+
            +----> S
B.shared ---+
~~~

In the example, `A` and `B` form a **cycle** (`A → B → A`); at the same time both `A.shared` and `B.shared` point to **one** object `S`. These two properties exist independently: there can be sharing without a cycle, or a cycle without an extra shared node.

### Shared References (Aliasing)

~~~java
StringBuilder shared = new StringBuilder("x");
StringBuilder left = shared;
StringBuilder right = shared;
left.append("y");
System.out.println(right); // xy
System.out.println(left == right); // true
~~~

`left` and `right` are two reference variables, yet there is only **one** `StringBuilder`. A mutation through one access path appears in the other path. The object is still allocated only once.

This differs from two objects with equal content but different identities, such as `new StringBuilder("x")` and `new StringBuilder("x")`. Do not rely on `toString()`, `equals()`, or identical content to conclude that two nodes are one.

## 2. Why Copying an Object May Not Yet Be Independent

**Shallow copy** creates a new shell object and copies the field values. For primitive fields, the value is copied. For reference fields, the *logical reference address* is copied: the child object remains the old object.

For example, if you create `A'` by shallow-copying `A`:

~~~text
A  --next--> B --next--> A
|            |
shared       shared
|            |
+----> S <---+

A' --next--> B     (still old B)
 |
 shared-----> S     (still old S)
~~~

`A' != A` is true, but `A'.next == A.next` and `A'.shared == A.shared` are also true. If you follow `A'.next.next`, you land back at the **original `A`**, not `A'`. Changing data inside `S` via `A'` can change the data that `A` sees.

Familiar operations also usually only shallow-copy reference elements:

- `Object.clone()` defaults to a field-by-field copy; mutable fields must be handled manually if deep independence is desired. Calling `clone()` also depends on the `Cloneable` contract and how the class implements it.
- `array.clone()` creates a new array, but for an object array, each element is still a reference to the old object.
- `new ArrayList<>(oldList)` creates a new list structure without cloning each element object.
- `List.copyOf(oldList)` creates a list that disallows structural modification through that API, **without turning mutable elements into immutable ones**. The resulting list may even reuse the input list if eligible.

Conversely, **deep copy** within a defined scope must copy the mutable objects that need independent ownership in the graph. The word “deep” must come with a clear contract: which nodes are copied, which immutable nodes may be shared, and how external resources are handled.

## 3. Correct Contract When Copying a Graph

Suppose `f(x)` is the copy of the original object `x`. For all nodes within the copy scope, the goals are:

1. **Separate identity:** `f(x) != x` for mutable nodes requiring independence.
2. **Preserve edges:** if `x.next == y` then `f(x).next == f(y)` (including `null`).
3. **Preserve shared references:** if `x.left == x.right` then `f(x).left == f(x).right`. An original node reached by multiple paths produces only **one** copied node.
4. **Preserve cycles:** if `A.next.next == A` then `A'.next.next == A'`.
5. **Do not mistakenly merge nodes:** two original nodes with *different identities*, even if `equals()` returns `true`, must still have two copies with different identities if both are in the copy scope.

If you create two new copies each time `S` is reached, sharing is lost (`A'.shared != B'.shared`). If you keep recursing through `A → B → A` without remembering already-processed nodes, the program can recurse infinitely and cause a `StackOverflowError`.

Therefore, **one graph copy pass needs an identity-based mapping table**: `original object → copied object`.

## 4. Algorithm: Create Shell, Record, Then Connect Edges

For a node `source`:

1. If `source == null`, return `null`.
2. If the table already contains `source`, return the **already created copy**, without creating a new node.
3. Create the initial copy object with its non-reference data fields.
4. **Insert the `source → copy` pair into the table immediately**, before traversing any edges.
5. Copy the edges one by one using the same table; return `copy`.

Step 4 is the crux. When going from `A` through `B` and back to `A`, the table already has `A'` to connect the back edge. When reaching `S` the second time, the table returns the same `S'` already created.

### Why Use `IdentityHashMap`?

`IdentityHashMap<K,V>` compares keys with `==` and hashes by identity, matching the requirement “one original node maps to only one copied node”.

Regular `HashMap` relies on `equals()` and `hashCode()`; two different objects that are equal by value can be collapsed into one key. Worse, programmer-written `equals()`/`hashCode()` might traverse circular references or depend on mutating fields. `IdentityHashMap` avoids confusing *value equality* with *same identity*.

## 5. Runnable Java 17 Example: Shallow Copy, Sharing, and Cycles

Save the entire program as **`GraphCopyDemo.java`**:

~~~java
import java.util.IdentityHashMap;

public class GraphCopyDemo {
    static final class Node {
        final String label;  // Immutable String so it can be shared
        int count;           // mutable state
        Node next;           // edge that can form a cycle
        Node shared;         // edge that can have multiple incoming references

        Node(String label, int count) {
            this.label = label;
            this.count = count;
        }
    }

    static Node shallowCopyRoot(Node original) {
        if (original == null) {
            return null;
        }
        Node result = new Node(original.label, original.count);
        result.next = original.next;
        result.shared = original.shared;
        return result;
    }

    static Node deepCopy(Node root) {
        return copy(root, new IdentityHashMap<>());
    }

    private static Node copy(
            Node original,
            IdentityHashMap<Node, Node> visited) {
        if (original == null) {
            return null;
        }

        Node existing = visited.get(original);
        if (existing != null) {
            return existing;
        }

        Node result = new Node(original.label, original.count);
        visited.put(original, result); // Record BEFORE traversing edges

        result.next = copy(original.next, visited);
        result.shared = copy(original.shared, visited);
        return result;
    }

    public static void main(String[] args) {
        Node a = new Node("A", 1);
        Node b = new Node("B", 2);
        Node s = new Node("S", 7);

        a.next = b;
        b.next = a;       // cycle A -> B -> A
        a.shared = s;
        b.shared = s;     // same S

        Node shallow = shallowCopyRoot(a);
        Node deep = deepCopy(a);

        System.out.println("shallow root new: " + (shallow != a));
        System.out.println("shallow B is original: " + (shallow.next == b));
        System.out.println("shallow back edge to original A: "
                + (shallow.next.next == a));

        System.out.println("deep root new: " + (deep != a));
        System.out.println("deep B new: " + (deep.next != b));
        System.out.println("deep cycle closes on copy: "
                + (deep.next.next == deep));
        System.out.println("deep sharing preserved: "
                + (deep.shared == deep.next.shared));
        System.out.println("deep S separate: " + (deep.shared != s));

        deep.shared.count = 99;
        System.out.println("S counts original/copy: "
                + s.count + "/" + deep.shared.count);
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac GraphCopyDemo.java
java GraphCopyDemo
~~~

Expected output:

~~~text
shallow root new: true
shallow B is original: true
shallow back edge to original A: true
deep root new: true
deep B new: true
deep cycle closes on copy: true
deep sharing preserved: true
deep S separate: true
S counts original/copy: 7/99
~~~

**Reading the output:**

- `shallow` has a new identity, but `shallow.next` is still the old `b` and the loop still returns to the old `a`.
- `deep.next.next == deep` confirms the cycle was rebuilt *inside* the new graph.
- `deep.shared == deep.next.shared` confirms the two edges in the new graph still share the same node; `deep.shared != s` confirms it is a new node.
- Changing `deep.shared.count` to `99` does not change `s.count` of the original (`7`). This is evidence of independence for the mutable state copied in the example.

The program only uses `String` (immutable), `int`, and links to `Node`. For fields containing `List`, `Map`, arrays, or another mutable class, the copy policy must continue to be applied to those corresponding objects; you cannot simply reassign the reference and call it a complete deep copy.

## 6. Easy-to-Miss Cases

### Multiple Roots Sharing One Graph

If two root variables `root1` and `root2` both point to `S`, calling `deepCopy(root1)` and `deepCopy(root2)` **separately** creates two mapping tables and can produce two different copies of `S`. If the contract requires preserving sharing *across roots*, the entire set of roots must be copied in **the same session** with a single `IdentityHashMap`. Initialize the table before looping over the roots and reuse it across every `copy(root, visited)` call.

### Self-References and Long Cycles

`node.next = node` is a cycle of length one. The cycle `A → B → C → A` has length three. The same algorithm above handles both because each node is recorded before moving to the next node. Do not test only two-node cycles.

### Two “Equal” Objects That Are Not One

Suppose two mutable objects `p` and `q` have the same data and `p.equals(q) == true`, yet `p != q`. Correctly copying identity structure still requires `copy(p) != copy(q)`. This is why an identity map is needed, especially when copying graphs of entities whose `equals()` is based on an identifier code.

### Immutable Data and Intentional Sharing

Immutable values like `String` in the example can be safely shared; copying them does not increase the independence of mutable state. A “deep copy” graph does not necessarily have to clone *every* physical object if the contract permits sharing immutable nodes. Similarly, an **immutable graph** or **copy-on-write** design can share structure to save memory, provided shared paths are not mutated uncontrollably.

### Collections, Arrays, and Mixed-Type Graphs

A `List<Node>` can contain the same `Node` twice, or a collection can reference itself through an appropriate element type. Copying a collection needs to register the container in the table before traversing elements if cycles are to be handled. A graph spanning multiple object classes needs a generic identity mapping mechanism (such as `IdentityHashMap<Object, Object>`), then handles each type according to the contract. Merely calling `new ArrayList<>(oldList)` or `array.clone()` keeps element references intact.

### `final` Fields, Constructors, and Class Invariants

The algorithm above instantiates the node first, then assigns edges; this is convenient because `next` and `shared` are not `final`. For models with `final` reference fields or constructors requiring all links to be valid immediately at creation, edges cannot be arbitrarily assigned after construction. It may be necessary to redesign a two-phase copy/builder API, a separate immutable model, or a dedicated mechanism preserving invariants. Do not use reflection to break `final` merely to force this algorithm to work.

### Off-Heap Resources and Special State

Do not blindly copy `Thread`, sockets, file handles, synchronization locks, database connections, or system resources. An entity with a database ID may need a new-ID policy, keep-ID policy, or must not be cloned. `transient`, caches, and relationships to services outside the graph also need clear decisions. **Copying an object** and **creating a new business record** are two different contracts.

### Cycles and the Garbage Collector

Cycles do not by themselves cause memory leaks in Java: the garbage collector is based on *reachability from GC roots*, so an entire group of circularly referencing objects can still be collected if no path from live roots remains. Retention leaks usually happen when caches, static fields, listeners, or collections hold unnecessary paths to the graph.

## 7. Cost, Limits, and How to Test

With `V` distinct-identity nodes and `E` copied edges, the algorithm visits each node once and each edge once: expected time is **`O(V + E)`**, and memory for the mapping table and copies is **`O(V)`** (excluding variable-sized data inside each node). Recursion also uses stack space up to the traversal depth; an extremely long chain can cause a `StackOverflowError`. If the graph is very deep, replace recursion with an explicit stack/queue and still record `visited` **before** enqueueing edges.

When data is being mutated concurrently by multiple threads, there is no guarantee the copy reflects a consistent point in time. An immutable snapshot, synchronization, or an appropriate versioning policy is needed. `IdentityHashMap` itself is not thread-safe.

Tests should cover:

1. `null`, an isolated node, and `null` reference fields.
2. Self-reference (`node.next == node`) and multi-node cycles.
3. Two edges to the same node (diamond) and two nodes with equal content but different identities.
4. Multiple roots sharing nodes if the API supports copying multiple roots.
5. Mutating mutable state of the copy and checking that the original does not change; mutating the original and checking that the copy does not change.
6. Preserving edges accurately with `==`; while ensuring all mutable nodes requiring independence differ from their corresponding original nodes.
7. Large or very deep data if used in production systems.

Some common mistakes and symptoms:

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only creating a new root and assigning old child references | Copy and original still mutate shared state | Continue copying mutable objects within scope |
| Creating a new node for every edge encountered | Loses sharing relationships; with cycles can recurse infinitely | Use an identity-based `original → copy` table |
| Adding to the table **after** copying all children | Cycle returns to a node not yet recorded | Register the copy immediately after instantiation |
| Using `HashMap` when `equals()` merges distinct nodes | Wrong topology, may lose nodes | Use `IdentityHashMap` |
| Giving each root a separate table in the same copy session | Loses sharing across new roots | Share one table across the session |
| Copying the container while keeping mutable elements as-is | Only shallow-copies the container layer | Copy elements using the same mapping table |
| Thinking `List.copyOf` is a deep copy | Container is hard to mutate, but elements remain mutable | Separate container and element immutability contracts |
| Recursing on an extremely deep graph | `StackOverflowError` | Iterate with an explicit stack/queue |

## 8. Self-Check

**Scenario 1:** `A.left == A.right` before copying. After a proper deep copy, `A'.left == A'.right` must be `true`; at the same time `A'.left != A.left` if that child is mutable and within the scope needing copying.

**Scenario 2:** `A.next = B; B.next = A`. If the copy of `A` is `A'` then `A'.next.next` must be `A'`, not `A`. A new root copy whose back edge points to the old node is evidence of a shallow copy.

**Scenario 3:** There are two nodes `X`, `Y` with different identities, yet `X.equals(Y)` returns `true`. The copy mapping table must treat these as two separate keys; use `IdentityHashMap` because the goal is to preserve graph identity.

**Takeaway:** When copying an object graph, you must accurately preserve **who points to whom**, **which paths point to the same object**, and **which cycles return to an existing point**. The core pattern is **create copy → register by identity → connect edges using the same table**; then verify the independence of all mutable state within the copy scope.
