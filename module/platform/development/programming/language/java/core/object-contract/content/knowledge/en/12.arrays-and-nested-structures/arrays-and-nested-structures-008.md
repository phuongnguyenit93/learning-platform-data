# Limits When Structures Have Circular References in Java

## 1. The problem: nested structures are not necessarily trees

In Java, an array or object graph can contain **references back to itself**. When a reference chain leads back to an already-encountered object, we have a **reference cycle**. This differs from ordinary nested structures, where every branch eventually terminates at a value or `null`.

Example with reference arrays:

~~~java
Object[] direct = new Object[1];
direct[0] = direct; // Array directly contains itself.

Object[] outer = new Object[1];
Object[] inner = new Object[1];
outer[0] = inner;
inner[0] = outer; // Indirect cycle: outer -> inner -> outer.
~~~

This is an **illustrative snippet**, not a standalone runnable file. Both cases are type-valid: an `Object[]` array can contain references to other `Object[]` arrays, including itself.

An **acyclic** structure can also share elements:

~~~java
Object[] shared = {"leaf"};
Object[] acyclic = {shared, shared};
~~~

Both positions in `acyclic` point to the same `shared`. **Reusing a reference** does not automatically create a cycle, because there is no path from `shared` back to `acyclic`. Distinguishing these two cases is critical when performing deep comparison, computing hashes, printing contents, and traversing graphs.

## 2. Official limits of the `Arrays` APIs

Methods in `java.util.Arrays` behave differently when encountering nested arrays or arrays with cycles:

| API | For acyclic nested arrays | For arrays containing cycles |
| --- | --- | --- |
| `Arrays.equals(Object[], Object[])` | Compares elements using `Objects.equals` at the direct level; sub-arrays default to reference comparison | Does not actively descend into sub-arrays so does not recurse over array structure; result is not deep comparison |
| `Arrays.hashCode(Object[])` | Hashes direct elements; sub-arrays use the array object's `hashCode()` | Does not actively deep-hash sub-arrays; still must be careful if another element has a self-recursing `hashCode()` |
| `Arrays.toString(Object[])` | Prints direct elements; sub-arrays normally appear as type name + identity hash code | Does not produce a deep representation or fully describe circular links |
| `Arrays.deepEquals(Object[], Object[])` | Recursively compares reference arrays and compares contents of corresponding primitive arrays | **Undefined behavior** if either array contains itself directly or indirectly |
| `Arrays.deepHashCode(Object[])` | Computes hash code from nested contents | **Undefined behavior** for directly or indirectly self-referential arrays |
| `Arrays.deepToString(Object[])` | Prints contents of nested arrays | **Handles cycles between arrays**: replaces the cyclic reference branch with `[...]` to avoid infinite recursion in this case |

**Most important point:** `deepEquals` and `deepHashCode` are specified for **acyclic** nested array structures. The word “deep” does not mean these methods are general algorithms handling arbitrary object graphs with circular references.

According to the Java API documentation, calling `Arrays.deepHashCode` on an array containing itself through one or more levels is *unacceptable* and has undefined behavior; the `Arrays.deepEquals` documentation specifies the same. Therefore, **do not rely on a return value or a specific exception type** if passing a cyclic structure.

## 3. Why do `deepEquals` and `deepHashCode` hit a limit?

For **acyclic** data, deep semantics can be implemented by following sub-arrays down to leaf elements:

- `deepEquals(a, b)` compares corresponding positions; if both are reference arrays, it continues deep comparison; if they are two primitive arrays of the same type, it uses the corresponding comparison such as `Arrays.equals(int[], int[])`.
- `deepHashCode(a)` computes a hash code based on each element; when encountering an inner reference array, it continues deep hashing.
- For acyclic arrays, `Arrays.deepEquals(a, b) == true` implies `Arrays.deepHashCode(a) == Arrays.deepHashCode(b)`.

A recursive traversal that does not track visited objects can follow a path:

~~~text
A -> B -> C -> A -> B -> C -> ...
~~~

The path never terminates at a leaf. An implementation may enter infinite recursion and throw `StackOverflowError`; in some other cases, reference comparison might cause a branch to stop early. However, **the API specification does not define cyclic behavior**, so you must not rely on behavior observed on one JDK to conclude that the methods support cycles.

In particular, do not use `Arrays.deepEquals(cycle, cycle)` as a test claiming “the API tolerates cycles”. If identical references are detected early, a specific call might return `true`, but that does not make calling it on cyclic structures valid per the specification.

### Do not try dangerous code in sample programs

The statements below only illustrate **calls to avoid**; do not run them in applications or hands-on examples:

~~~java
Object[] cycle = new Object[1];
cycle[0] = cycle;

// DO NOT CALL on cyclic data:
// Arrays.deepHashCode(cycle);
// Arrays.deepEquals(cycle, anotherCyclicArray);
~~~

You should not catch `StackOverflowError` and treat that as normal cycle handling. That is a stack resource exhaustion error; a proper algorithm must detect and handle cyclic structures **before uncontrolled recursion**.

## 4. Special case: `Arrays.deepToString` handles array cycles

`Arrays.deepToString(Object[])` is designed to build a string representation of multidimensional arrays. For **nested reference arrays with a path returning to an array already on the recursion path**, it replaces the self-referential branch with the string `[...]`.

For example, an array containing only itself prints as `[[...]]`. If an array contains `"root"` followed by a reference back to itself, the result is `[root, [...]]`. Indirect cycles are also handled; for instance `outer -> inner -> outer` produces `[[[...]]]`.

The `[...]` markers are **display notation**, not meaning the object actually contains that character sequence. `deepToString` does not provide a single canonical representation for every graph, does not number object identities, and does not decide whether two cyclic graphs are equal.

Limitation to remember: cycle protection is described for **nested arrays**. If an element is a custom object whose `toString()` traverses an uncontrolled cyclic graph on its own, `deepToString` cannot fix that `toString()` algorithm. Similarly, a cyclic `List` or `Map` still requires considering the specific contract of the class and its elements.

## 5. Complete runnable Java 17+ example

The following program illustrates three safe groups of results: deep comparison on acyclic arrays, displaying cyclic arrays, and traversing a singly linked graph while recording encountered objects.

Create file **`CyclicStructureDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;

public class CyclicStructureDemo {
    static final class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    static String describe(Node start) {
        Map<Node, Integer> seen = new IdentityHashMap<>();
        StringBuilder out = new StringBuilder();
        Node current = start;

        while (current != null) {
            if (out.length() > 0) {
                out.append(" -> ");
            }

            Integer oldId = seen.get(current);
            if (oldId != null) {
                out.append("#").append(oldId).append("(cycle)");
                break;
            }

            int id = seen.size() + 1;
            seen.put(current, id);
            out.append("#").append(id)
               .append("(").append(current.label).append(")");
            current = current.next;
        }

        return out.toString();
    }

    // Only compares Node graphs with one "next" edge per node,
    // requiring preserved labels and exact reference/cycle pattern.
    static boolean sameShape(Node left, Node right) {
        Map<Node, Node> leftToRight = new IdentityHashMap<>();
        Map<Node, Node> rightToLeft = new IdentityHashMap<>();

        while (left != null && right != null) {
            if (leftToRight.containsKey(left)
                    || rightToLeft.containsKey(right)) {
                return leftToRight.get(left) == right
                        && rightToLeft.get(right) == left;
            }

            if (!Objects.equals(left.label, right.label)) {
                return false;
            }

            leftToRight.put(left, right);
            rightToLeft.put(right, left);
            left = left.next;
            right = right.next;
        }

        return left == null && right == null;
    }

    public static void main(String[] args) {
        Object[] first = {
            new int[] {1, 2},
            new Object[] {"x", new int[] {3}}
        };
        Object[] equivalent = {
            new int[] {1, 2},
            new Object[] {"x", new int[] {3}}
        };

        System.out.println("shallow equals: "
                + Arrays.equals(first, equivalent));
        System.out.println("deep equals: "
                + Arrays.deepEquals(first, equivalent));
        System.out.println("deep hash equal: "
                + (Arrays.deepHashCode(first)
                   == Arrays.deepHashCode(equivalent)));
        System.out.println("deep text: " + Arrays.deepToString(first));

        Object[] direct = new Object[2];
        direct[0] = "root";
        direct[1] = direct;
        System.out.println("direct cycle: "
                + Arrays.deepToString(direct));

        Object[] outer = new Object[1];
        Object[] inner = new Object[1];
        outer[0] = inner;
        inner[0] = outer;
        System.out.println("indirect cycle: "
                + Arrays.deepToString(outer));

        // Three graphs with cyclic structure; do not use deepEquals/deepHashCode.
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        Node c = new Node("A");
        Node d = new Node("B");
        c.next = d;
        d.next = c;

        Node e = new Node("A");
        Node f = new Node("B");
        e.next = f;
        f.next = f; // Differs from the cycle pattern of a -> b -> a.

        System.out.println("graph walk: " + describe(a));
        System.out.println("same graph shape: " + sameShape(a, c));
        System.out.println("different graph shape: " + sameShape(a, e));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac CyclicStructureDemo.java
java CyclicStructureDemo
~~~

Deterministic output:

~~~text
shallow equals: false
deep equals: true
deep hash equal: true
deep text: [[1, 2], [x, [3]]]
direct cycle: [root, [...]]
indirect cycle: [[[...]]]
graph walk: #1(A) -> #2(B) -> #1(cycle)
same graph shape: true
different graph shape: false
~~~

### Output explanation

1. The two arrays `first` and `equivalent` have separately created sub-arrays. `Arrays.equals` compares direct elements, so it does not treat new sub-arrays as equal by content and gives `false`.
2. `Arrays.deepEquals` traverses sub-arrays and leaf elements. Both structures are **acyclic** and content-equivalent, so it returns `true`; deep hashes are also equal.
3. `Arrays.deepToString(first)` presents nested data as `[[1, 2], [x, [3]]]`.
4. The two cyclic arrays are only passed to `Arrays.deepToString`. This function marks circular references with `[...]` instead of recursing forever.
5. `describe` uses `IdentityHashMap` to accurately record each **Node reference** encountered. When returning to node `a`, it detects ID `#1` and stops.
6. `sameShape` maintains a bidirectional mapping between Nodes by identity, checking `label` and `next` relationships; the two cycles `A -> B -> A` match, whereas `A -> B -> B` has a different cycle pattern.

**Example scope:** `sameShape` is only an illustrative algorithm for graphs where each Node has **at most one `next` link**. It checks node-by-node correspondence and the reference cycle of that specific model. Do not treat it as a general algorithm for multi-edge graphs, nested collections, or all Java structures.

## 6. Why use `IdentityHashMap` to track visited objects?

When checking cycles in an **object graph**, the first question to answer is: “Have we seen **this exact instance** before?”, meaning using `==` on references.

`IdentityHashMap` compares keys using `==` instead of content-based `equals()`. That is helpful because:

- Two Nodes with different references that are business-equal under `equals()` are still distinguished.
- Adding a Node to the visited set does not invoke user-defined `equals()` or `hashCode()`, which might themselves traverse the cyclic structure.
- Traversal relies on object identity, matching the goal of detecting repeated references.

An identity-based `Set` can be created with:

~~~java
Set<Object> seen =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<>());
~~~

This is an **illustrative snippet** that must be placed in a context with `import java.util.Set;` or using fully qualified names. Note that `IdentityHashMap` does not have the same key semantics as `HashMap`: only choose it when you genuinely need **identity**-based equality.

In graphs with multiple branches, at least two situations must be distinguished:

- **Globally visited**: a Node appears in two branches without forming a cycle. It is a *shared reference*, not automatically a cycle.
- **Currently on the active traversal path**: re-encountering a Node still on the current path stack signals a back-edge to an ancestor, forming a cycle during depth-first traversal.

With a singly linked list `next` like the example, re-encountering the same reference while walking linearly suffices to identify a cycle. For graphs with multiple edges, DFS uses states *unvisited / visiting / visited* or separate `visiting` and `visited` sets as appropriate for cycle detection.

## 7. Comparing two cyclic structures requires defining “equal”

There is no single definition of “two cyclic graphs are equal”. For example:

- **Identity equality:** two variables must point to the same object (checked with `==`).
- **Node-value equality:** nodes with the same business ID might be considered equal even if edges differ.
- **Structural (topology) equality:** preserves a mapping between nodes, labels, and edges; shared branches or differing cycles must be distinguished.
- **Business-implementation equality:** an application might only care about a selected set of properties.

`sameShape` in the example implements **one specific definition**: matching corresponding labels and a one-to-one correspondence in `next` reference structure. When both traversals return to an already-mapped pair of Nodes, the algorithm stops successfully; if one side returns to a structurally different Node, it returns `false`.

For general graphs, you must manage bidirectional (*one-to-one*) mapping, edge order if order matters, shared aliases, and cycles. A set of already-compared pairs sometimes avoids infinite recursion yet **does not automatically prove** two graphs have the same structure under every definition. Define semantics before choosing an algorithm.

## 8. Custom `equals()`, `hashCode()`, `toString()` can also loop infinitely

The risk does not only appear in `Arrays.deepEquals` or `Arrays.deepHashCode`. If a class overrides methods and follows links without cycle checks, recursion can run forever.

Illustrative example, **not standalone runnable**:

~~~java
@Override
public String toString() {
    return "Node(" + label + ", next=" + next + ")";
}
~~~

If `next` points back to the current Node or is part of a cycle, string concatenation calls `next.toString()` and loops back to the old object. With this implementation, we can hit `StackOverflowError`.

A safer approach for logging is printing only **non-recursive information**:

~~~java
@Override
public String toString() {
    return "Node(" + label + ")";
}
~~~

If you genuinely need to print the **full graph**, provide a dedicated display function accepting visited state, such as `describe`. A similar approach applies to `equals()`/`hashCode()`: do not let them recurse unrestrictedly across all edges, especially when the object is intended as a `HashMap` key.

A hash function for **cyclic graphs** must be designed according to a deterministic convention (such as immutable node identifiers, traversal order, and consistent alias marking). The mandatory condition must be preserved: if two values are equal under the chosen `equals()`, they have the same hash code. Choosing random hashes or `System.identityHashCode()` will be incompatible if `equals()` treats graphs with different references as structurally equal.

## 9. Distinguishing arrays, collections, and circular references

Several cases are often conflated:

- **Primitive arrays** such as `int[]` cannot contain themselves as primitive elements. Cycles only form from references, such as in `Object[]`, Nodes, or collections.
- **Multidimensional arrays like `int[][]`** have primitive sub-arrays; an `int[][]` itself cannot contain itself as an `int[]` element because types do not match. However, an `Object[]` can contain `int[]` and circular references to `Object[]` arrays.
- **`List`, `Set`, `Map`** can organize data containing mutual references. The contracts and handling of each API are not identical to `Arrays.deepToString`. Do not assume they all protect against cycles in `equals()`, `hashCode()`, or `toString()`.
- **Very deeply nested acyclic arrays** can still exhaust the stack if an algorithm recurses too deeply. Being acyclic does not mean every recursive operation is safe at arbitrary depth.
- **A `record` containing an array** does not automatically perform deep comparison of elements. Generated `equals()`/`hashCode()` for a record handles array components according to the array object's own semantics (usually identity), rather than substituting `Arrays.deepEquals`/`deepHashCode`.

In particular, `Objects.deepEquals(a, b)` is **also not a solution for cyclic arrays**: when both arguments are arrays, this method delegates to `Arrays.deepEquals`; the limitation on cyclic structures remains.

## 10. Practical handling strategies

1. **If data is acyclic nested arrays and content comparison is desired:** use `Arrays.deepEquals` with `Arrays.deepHashCode`, and use `Arrays.deepToString` when display is needed.
2. **If you only need to log an array with circular references:** `Arrays.deepToString` handles array cycles; do not use the printed output as a unique key or structural equality definition.
3. **If you need to detect cycles in a graph:** traverse by identity; track visiting and visited states with `IdentityHashMap` or a `Set` backed by it.
4. **If you need to compare two cyclic graphs:** first define equality, then use node-pair mapping or an appropriate graph algorithm with termination and alias preservation where needed.
5. **If you need to use a structure as a hash key:** prefer immutable keys by business ID or a normalized immutable representation. Avoid computing `equals()`/`hashCode()` via unrestricted deep traversal in cyclic graphs.
6. **If data comes from external sources:** validate upfront for validity and potential cycles, limiting node count, edge count, or depth according to the application's resource protection requirements.

### Quick checklist

- Is there a **reference returning to the same object** directly or across multiple levels?
- Are `Arrays.deepEquals` or `deepHashCode` being used on cyclic arrays?
- Is `deepToString`'s array cycle handling being confused with a cycle-prevention mechanism for all Java objects?
- Is the visited-object set based on **reference identity** when the goal is tracking the exact same instance?
- Does the algorithm distinguish **shared references** from **true cycles**?
- Is the meaning of “equal” defined beforehand when comparing cyclic structures?
- Are resource limits and excessively deep nesting cases accounted for?

## 11. Self-check questions

**Question 1.** An `Object[]` contains itself. Can you safely call `Arrays.deepHashCode(array)`?

**Answer:** No. The Java API specifies undefined behavior for arrays that directly or indirectly reference themselves.

**Question 2.** Does `Arrays.deepToString(array)` face the same problem as `Arrays.deepHashCode(array)` when the array itself reappears inside the structure?

**Answer:** `deepToString` has a mechanism to represent cyclic array branches as `[...]`. That is a content-printing mechanism and does not automatically provide deep comparison or deep hashing on cyclic structures.

**Question 3.** Two branches both point to a sub-array, yet the sub-array does not point back to the parent. Is that a cycle?

**Answer:** No. That is a *shared reference*. Having a shared edge does not imply there is a path back to the starting point.

**Question 4.** Why is `IdentityHashMap` useful when detecting visited objects?

**Answer:** It distinguishes keys using `==` instead of calling the object's `equals()`/`hashCode()`, thereby accurately tracking each instance and avoiding triggering custom recursive comparison logic.

**Question 5.** Can the same hashing algorithm be used for every equality definition of cyclic graphs?

**Answer:** No. You must choose the equality semantics first, then design a compatible hashing algorithm; in particular, “equal `equals()` ⇒ equal `hashCode()`” must be maintained.

**Key takeaway:** `Arrays.deepEquals` and `Arrays.deepHashCode` are intended for deep comparison/hashing of **acyclic** arrays; using them on cyclic arrays has undefined behavior. `Arrays.deepToString` handles circular branches between arrays for display. For general reference graphs, proactively detect visited identities and explicitly define comparison semantics.

## API References

- [Java `Arrays` API — deepEquals, deepHashCode, deepToString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)
- [Java `IdentityHashMap` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)