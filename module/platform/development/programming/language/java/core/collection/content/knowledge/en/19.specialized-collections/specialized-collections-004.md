# IdentityHashMap: Comparing Keys by Reference

Two objects can carry the same data and still be two distinct objects. A lookup table keyed by customer ID usually wants to group them by the ID value. A tool tracking objects in memory, on the other hand, may need to keep them separate.

`IdentityHashMap` serves the second requirement: for keys, the match condition is that two references point to the exact same object, i.e., `k1 == k2`. It does not substitute that comparison with `k1.equals(k2)`.

This lesson explains when object identity is what needs to be preserved, how to distinguish it from value equality, and the consequences of passing an `IdentityHashMap` through standard `Map` APIs. Examples use Java 17+ compatible source code and do not rely on iteration order or the numeric values of identity hash codes.

## 1. Three Different Questions

Suppose we create two keys with the same code:

~~~java
record Key(String code) {}

Key a = new Key("same");
Key b = new Key("same");
Key alias = a;
~~~

This is a partial illustrative snippet. With this record:

~~~text
a.equals(b) -> true
a == b      -> false
alias == a  -> true
~~~

The three results do not contradict each other:

- `equals` asks whether two keys are equal according to the class's value-equality rule.
- The `==` operator on references asks whether they refer to the same object.
- `alias` is another variable name holding the same reference, not a new key object.

You can visualize it as:

~~~text
a --------> object K1, code = "same"
alias ----> object K1

b --------> object K2, code = "same"
~~~

A `HashMap` using value equality treats `K1` and `K2` as the same logical key. `IdentityHashMap` treats them as two distinct keys because `K1` and `K2` are two separate objects.

### 1.1. Choosing a Map Means Choosing Key Semantics

The deciding question is not "which map is more exotic or faster?", but "should two objects with equal data be treated as the same key?".

| Requirement | Appropriate Semantics to Consider |
|---|---|
| Two requests with the same business code look up the same data | Value-based keys, typically a standard map |
| Tracking each individual object currently being processed | Reference-based keys |
| Copying a graph while keeping two distinct node objects despite identical labels | Reference-based keys |
| Looking up a username constructed from multiple strings with equal content | Value-based keys |

`IdentityHashMap` is designed for specialized scenarios such as object-graph transformations and tables associating objects with proxy/representative instances. It is not a default replacement for `HashMap`. [Java 17: IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

### 1.2. Do Not Use It to Hide `equals` or `hashCode` Bugs

If business logic expects equal codes to represent the same key, a buggy `equals`/`hashCode` implementation should be fixed to match that meaning. Switching to `IdentityHashMap` just to make a hashing bug temporarily disappear changes lookup semantics.

After switching, a new key object with the same code will fail to find the data. That is not a free optimization; the application has chosen a different key relation.

## 2. `get`, `put`, and `remove` by Exact Reference

### 2.1. Two Equal Objects Still Have Two Mappings

With `a` and `b` above:

~~~java
IdentityHashMap<Key, String> byObject = new IdentityHashMap<>();
byObject.put(a, "first");
byObject.put(b, "second");
~~~

`byObject` has two mappings. `get(a)` returns `"first"`, and `get(b)` returns `"second"`. Calling `get` with a new `Key` whose `code` is `"same"` returns neither value, because the new reference does not match `a` or `b`.

Conversely, passing `alias` to `put` reuses the exact same key `a`:

~~~java
byObject.put(alias, "updated");
~~~

The number of mappings remains two; the value associated with object `K1` is replaced. A differently named variable does not create a third key.

### 2.2. `containsKey` and Single-Argument `remove`

`containsKey` also asks whether that exact object reference is currently a key. `remove(key)` removes the mapping for the exact reference key passed in.

Creating a new object with equal content and calling `remove` does not mean "delete all objects with the same code". If that rule is needed, you must use a structure or algorithm that explicitly represents relationships by code.

The full program verifies both `remove` calls: a new key with equal content does not remove `a`, whereas `alias` removes `a`'s mapping.

### 2.3. Null Values and the Null Key

`IdentityHashMap` permits one `null` key and `null` values. Putting `null` again updates the mapping for the `null` key rather than creating multiple separate `null` keys.

`get` returning `null` still has two possible meanings: either the exact reference key was not found, or that key is currently mapped to `null`. Use `containsKey` when you need to distinguish the two, in an appropriately structured access context.

Allowing a `null` key does not make non-null references equal to one another. The `==` rule still distinguishes normal objects.

## 3. Identity Hash Code Is Not a Unique Identifier

### 3.1. Different from an Overridden `hashCode` Method

`System.identityHashCode(object)` returns the hash code according to `Object`'s default behavior even when a class overrides `hashCode`. This supports organizing lookups by object identity. [Java 17: System.identityHashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object))

Do not infer from this that:

- The hash code is the memory address.
- Two different objects always have two different numbers.
- That number is a durable key that can be persisted and reused in another run.

A hash table still has to handle collisions; the step that verifies an exact key match is reference comparison. The hash code is a distribution tool, not a replacement for `==`.

The `hashCode` contract does not require distinct objects to have distinct hash codes. [Java 17: Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode())

### 3.2. Do Not Replace `IdentityHashMap` with a `Map<Integer, V>` of `identityHashCode`

If you only use `identityHashCode` integers as keys in a `HashMap`, two colliding objects can be treated as the same integer key. That approach drops the reference-distinction step that `IdentityHashMap` provides.

Similarly, there is no need to print concrete hash code numbers to verify this lesson. Those numbers depend on the run and do not express business relationships. The program uses `==`, `equals`, `size`, and lookups with deterministic results.

### 3.3. Do Not Use Accidentally Shared Objects as Your Only Test

Strings can be interned/shared, and numeric wrapper classes can share instances in certain cases. An example using only constant/literal values may accidentally pass the same reference around.

To verify the distinction, explicitly construct two new objects and check `a != b`. The `Key` record in this lesson does that directly.

The `new String` calls in the value-comparison section are also only there to guarantee two objects with distinct references for the experiment. They are not a recommendation to allocate redundant strings in normal application code.

## 4. Hash Table Internals and Performance Implications

The Java 17 documentation describes a linear-probing implementation: the table stores keys and values interleaved, and collisions are handled by probing for an appropriate slot in the table.

Conceptual model:

~~~text
compute starting slot from identity hash code
    ↓
inspect the current slot
    ↓
compare keys with ==; if not a match, continue probing the table
~~~

This diagram explains why reference comparison is still required despite having a hash code. It is not source code or a layout guarantee across all JVM versions.

`get` and `put` have constant-time performance when the identity hash function disperses elements properly. Do not turn that condition into an unconditional timing promise for all data or all operations.

The constructor accepting `expectedMaxSize` specifies the expected maximum number of mappings. It is not an array slot count guaranteed by the API to equal the parameter, nor is it a hard limit that stops the map from accepting elements once exceeded. Choosing a value that is too large also affects iteration and memory usage. [Java 17: IdentityHashMap model and parameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

Do not choose `IdentityHashMap` just because you heard linear-probing tables can be fast. Key semantics must be right first, and only then should you examine workload measurements.

## 5. When a Key Object's Content Mutates

A class may define `equals`/`hashCode` based on a mutable field. `IdentityHashMap` still looks up the same object after that field changes, because reference identity has not changed.

Example from the program:

~~~text
mutable object with code "old"
put(mutable, "tracked")

change mutable.code to "new"
get(mutable) -> "tracked"
get(new MutableKey("new")) -> not found
~~~

This is useful when tracking the object itself across mutation steps. However, it does not prove `IdentityHashMap` is the right fix for every mutable key.

If the goal is to look up by the new code, you should design keys around stable values or manage mapping updates appropriately. Tracking objects and indexing by a field are two different requirements.

`IdentityHashMap` also holds strong references to its keys and values as map data; it does not become a weak-key map just because its name contains `Identity`. Long-lived tracking tables need a lifecycle and cleanup strategy suited to the task.

## 6. Values, Views, and the General `Map` Contract

### 6.1. `containsValue` Also Has Reference Semantics

Given a `String value` and another `String equalValue` that is a different object with the same content:

~~~text
value.equals(equalValue) -> true
value == equalValue     -> false
~~~

If the map holds `value`, `containsValue(value)` returns `true`, while `containsValue(equalValue)` returns `false`. This differs from the common expectation for value-equality maps.

Do not infer from `get` returning a string with content `"label"` that every string object with content `"label"` is treated as the same value reference in these operations.

### 6.2. Views Carry Special Semantics

`keySet` is an identity-based view of the keys. `values` and the entries in `entrySet` also follow the reference-comparison rules described by the class.

For example, an entry representing the same key and value references can be found in `entrySet`. If you replace only the value with an equal-content object that has a different reference, the check result can differ.

Do not treat `IdentityHashMap`'s `keySet` like an ordinary value-based `Set` and mix comparison operations, `removeAll`, or conversions without reading the receiver's contract. Views are also backed by the original map; supported modifications through a view mutate the underlying data.

### 6.3. `Map.equals` with Standard Maps Can Lose Symmetry

`IdentityHashMap` intentionally violates the general `Map` contract, which is based on `equals`. Therefore, comparing it with a standard map can produce different results depending on which side calls `equals`.

The program uses the same key reference with two distinct value objects that have equal content:

~~~text
normal.equals(identity) -> true
identity.equals(normal) -> false
~~~

`normal` compares values with `equals`; `identity` requires matching value references per its own semantics. This consequence is documented by the class, not a mechanism to rely on for building general equality across arbitrary maps. [Java 17: IdentityHashMap.equals and views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

Accordingly, keep identity maps behind clear internal boundaries when a task needs them. A `Map` parameter type does not by itself guarantee that every map passed in shares the same key semantics.

### 6.4. Version Differences in Conditional Overloads

There is a practical detail to separate from the key rule: Oracle noted in JDK 20 that `IdentityHashMap.remove(key, value)` and `replace(key, oldValue, newValue)` were fixed. Earlier releases used `equals` when comparing the value arguments, contrary to the reference semantics specified by the class; after the fix, those comparisons use object identity. [Oracle: JDK 20 release note for IdentityHashMap fix](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html)

Because the example targets 17+ compatible code, this lesson does not use those two overloads to produce common stdout across runtimes. When auditing an older environment or upgrading JDK versions, check the method behavior on the actual target JDK.

This does not change the core takeaway: `get`, `containsKey`, `put`, and `remove(key)` must be understood strictly in terms of key reference identity. At the same time, do not generalize a true statement about keys into an unconditional promise for every value-taking overload.

## 7. Converting Maps Can Change Data Meaning

### 7.1. Copying to a `HashMap` Can Collapse Keys

An `IdentityHashMap` can hold two keys `a` and `b` with distinct references where `a.equals(b)` is `true`. Copying into a `HashMap` subjects those keys to the target's value-equality rule, so only one mapping may remain.

Do not assume either `a`'s or `b`'s value is guaranteed to win. `IdentityHashMap` makes no iteration-order guarantee, so do not rely on accidental copy order as a conflict-resolution policy.

The program only checks the mapping count after conversion. It intentionally makes no assertion about which value is retained.

### 7.2. Converting Back Does Not Recover Lost Information

Once a `HashMap` has collapsed two value-equal objects into one mapping, constructing an `IdentityHashMap` from it cannot recover the previously discarded object or mapping.

You must decide on semantics when building the table, rather than converting types at the end and expecting to retrieve identity that was never preserved.

### 7.3. Copying an Identity Map Does Not Deep-Copy Objects

Creating a new `IdentityHashMap` from an existing identity map preserves the reference pairs with an independent mapping structure. Removing from the copy does not remove from the source.

However, the keys and values are still the same referenced objects, not deep clones. Distinguish "copying the association table" from "copying the object graph that the table describes".

## 8. The Right Use Case: Graph Copying That Preserves Reference Structure

### 8.1. Why Equal Labels Must Not Merge Nodes

Consider the graph:

~~~text
root
 ├─ left  (label = "same") ─┐
 └─ right (label = "same") ─┴─> shared ("leaf") ─> root
~~~

`left` and `right` are two distinct objects whose `equals` is defined by `label`, so they are equal. They must have two separate copies.

`shared` is a single object pointed to by both branches, so in the copied graph there must also be only one shared `shared` copy. The edge from `shared` back to `root` creates a cycle; the algorithm must terminate rather than recurse infinitely.

Thus, two invariants must hold simultaneously:

- Distinct objects in the source are not merged just because their labels are equal.
- The same object referenced from multiple places must map to the same single copy object.

This is the reference-shape relationship of the graph, not just a list of labels.

### 8.2. A Memo Table Mapping Source to Copy

Use a table:

~~~text
exact source object -> created copy object
~~~

Each time a `Node` is copied:

1. If `source` is `null`, return `null`.
2. If the table already has a copy for that exact `source`, reuse that copy.
3. Otherwise, create a target `Node`.
4. Put the source–target pair into the table before recursing into children.
5. Copy child edges using the same table.

Recording the pair in the table before recursing is what handles cycles. When traversal returns to `root`, the table already holds the target `root` to return.

In this program, every value in the `seen` table is a non-null `Node` copy, so `get` returning `null` serves as the unvisited marker. That is a property specific to this algorithm; do not apply it to an arbitrary map that may store `null` values.

### 8.3. Scope of the Example

The `copy` method only copies the `Node` class defined in this lesson and its edge list. It is not a general-purpose deep-copy library for arbitrary Java objects, nor does it automatically handle arbitrary resources or sharing policies.

The source graph is assumed to be stable during copying. For very deep graphs or concurrently mutated sources, traversal design and access policies must be organized around real-world requirements.

## 9. Complete Java Program

Save all of the following code to `IdentityKeysDemo.java`. The program does not print maps in iteration order and does not print identity hash numbers, so stdout does not depend on unspecified details.

It uses nested types inside a single class so it can be compiled from one file. The example includes `HashMap` for contrast, not to choose `IdentityHashMap` based on runtime behavior.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

public class IdentityKeysDemo {
    record Key(String code) {}

    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static final class Node {
        final String label;
        final List<Node> children = new ArrayList<>();

        Node(String label) {
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node node && label.equals(node.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected identity result");
        }
    }

    private static Node copy(Node source, IdentityHashMap<Node, Node> seen) {
        if (source == null) {
            return null;
        }
        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }
        Node target = new Node(source.label);
        seen.put(source, target);
        for (Node child : source.children) {
            target.children.add(copy(child, seen));
        }
        return target;
    }

    public static void main(String[] args) {
        Key a = new Key("same");
        Key b = new Key("same");
        Key alias = a;
        require(a.equals(b) && a != b && alias == a);
        System.out.println("keys/equals=" + a.equals(b)
                + ", sameReference=" + (a == b)
                + ", aliasSame=" + (alias == a));

        Map<Key, String> ordinary = new HashMap<>();
        ordinary.put(a, "first");
        ordinary.put(b, "second");
        require(ordinary.size() == 1);
        System.out.println("hash/size=" + ordinary.size()
                + ", getA=" + ordinary.get(a));

        IdentityHashMap<Key, String> identity = new IdentityHashMap<>();
        identity.put(a, "first");
        identity.put(b, "second");
        require(identity.size() == 2);
        System.out.println("identity/size=" + identity.size()
                + ", getA=" + identity.get(a) + ", getB=" + identity.get(b));
        Key equalNew = new Key("same");
        System.out.println("identity/equalNewContains="
                + identity.containsKey(equalNew)
                + ", get=" + identity.get(equalNew));
        String previous = identity.put(alias, "updated");
        require(identity.size() == 2 && previous.equals("first"));
        System.out.println("identity/aliasPrevious=" + previous
                + ", size=" + identity.size());
        System.out.println("identity/removeEqualNew=" + identity.remove(equalNew)
                + ", size=" + identity.size());
        System.out.println("identity/removeAlias=" + identity.remove(alias)
                + ", size=" + identity.size());

        IdentityHashMap<Key, Integer> distinct = new IdentityHashMap<>();
        distinct.put(a, 1);
        distinct.put(b, 2);
        Map<Key, Integer> hashCopy = new HashMap<>(distinct);
        IdentityHashMap<Key, Integer> identityFromHash =
                new IdentityHashMap<>(hashCopy);
        require(distinct.size() == 2 && hashCopy.size() == 1
                && identityFromHash.size() == 1);
        System.out.println("conversion/identity=" + distinct.size()
                + ", hashCopy=" + hashCopy.size()
                + ", identityFromHash=" + identityFromHash.size());
        IdentityHashMap<Key, Integer> shallowCopy =
                new IdentityHashMap<>(distinct);
        shallowCopy.remove(a);
        require(distinct.size() == 2 && shallowCopy.size() == 1);
        System.out.println("copy/sourceSize=" + distinct.size()
                + ", copySize=" + shallowCopy.size());

        Object handle = new Object();
        String value = new String("label");
        String equalValue = new String("label");
        IdentityHashMap<Object, String> values = new IdentityHashMap<>();
        values.put(handle, value);
        System.out.println("values/equals=" + value.equals(equalValue)
                + ", sameContains=" + values.containsValue(value)
                + ", equalContains=" + values.containsValue(equalValue));
        System.out.println("entries/sameReferences="
                + values.entrySet().contains(
                        new AbstractMap.SimpleEntry<>(handle, value))
                + ", equalValue=" + values.entrySet().contains(
                        new AbstractMap.SimpleEntry<>(handle, equalValue)));
        Map<Object, String> normal = new HashMap<>();
        normal.put(handle, equalValue);
        require(normal.equals(values) && !values.equals(normal));
        System.out.println("equals/normalToIdentity=" + normal.equals(values)
                + ", identityToNormal=" + values.equals(normal));

        IdentityHashMap<Object, String> nullable = new IdentityHashMap<>();
        Object presentWithNull = new Object();
        nullable.put(null, "null-key");
        nullable.put(presentWithNull, null);
        System.out.println("null/keyValue=" + nullable.get(null)
                + ", present=" + nullable.containsKey(presentWithNull)
                + ", mappedValue=" + nullable.get(presentWithNull));

        MutableKey mutable = new MutableKey("old");
        IdentityHashMap<MutableKey, String> tracking = new IdentityHashMap<>();
        tracking.put(mutable, "tracked");
        mutable.code = "new";
        require(tracking.get(mutable).equals("tracked"));
        System.out.println("mutable/sameReference=" + tracking.get(mutable)
                + ", equalNew=" + tracking.get(new MutableKey("new")));

        Node root = new Node("root");
        Node left = new Node("same");
        Node right = new Node("same");
        Node shared = new Node("leaf");
        root.children.add(left);
        root.children.add(right);
        left.children.add(shared);
        right.children.add(shared);
        shared.children.add(root);

        IdentityHashMap<Node, Node> seen = new IdentityHashMap<>();
        Node copiedRoot = copy(root, seen);
        Node copiedLeft = copiedRoot.children.get(0);
        Node copiedRight = copiedRoot.children.get(1);
        Node copiedShared = copiedLeft.children.get(0);
        require(left.equals(right) && copiedLeft != copiedRight);
        require(copiedShared == copiedRight.children.get(0));
        require(copiedShared.children.get(0) == copiedRoot);
        require(copiedRoot != root && seen.size() == 4);
        System.out.println("graph/equalSources=" + left.equals(right)
                + ", distinctCopies=" + (copiedLeft != copiedRight));
        System.out.println("graph/sharedChild="
                + (copiedShared == copiedRight.children.get(0)));
        System.out.println("graph/cycleReturnsCopiedRoot="
                + (copiedShared.children.get(0) == copiedRoot));
        System.out.println("graph/sourceSeparate=" + (copiedRoot != root)
                + ", memoSize=" + seen.size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 IdentityKeysDemo.java
java IdentityKeysDemo
~~~

Verification stdout from running the program:

~~~text
keys/equals=true, sameReference=false, aliasSame=true
hash/size=1, getA=second
identity/size=2, getA=first, getB=second
identity/equalNewContains=false, get=null
identity/aliasPrevious=first, size=2
identity/removeEqualNew=null, size=2
identity/removeAlias=updated, size=1
conversion/identity=2, hashCopy=1, identityFromHash=1
copy/sourceSize=2, copySize=1
values/equals=true, sameContains=true, equalContains=false
entries/sameReferences=true, equalValue=false
equals/normalToIdentity=true, identityToNormal=false
null/keyValue=null-key, present=true, mappedValue=null
mutable/sameReference=tracked, equalNew=null
graph/equalSources=true, distinctCopies=true
graph/sharedChild=true
graph/cycleReturnsCopiedRoot=true
graph/sourceSeparate=true, memoSize=4
~~~

The code compiled with `--release 17` and ran successfully. The release option specifies the target API and bytecode compatibility level; it does not assert that the executing JVM is specifically JDK 17.

## 10. Reading the Output Groups

### 10.1. Value-Equal Keys and Aliases

`HashMap` retains one mapping after two `put` calls with content-equal `a` and `b`. `IdentityHashMap` retains two. A new key with equal content does not find an identity mapping.

`alias` updates `a`'s mapping without increasing `size`. Removing the new key removes nothing; removing `alias` removes `a`'s mapping. These steps separate the concept of a new variable from that of a new object.

### 10.2. Conversion and Copying

Converting two value-equal identity keys into a `HashMap` leaves only one mapping. Creating an identity map from that result still yields only one. The lesson does not print or assert which entry wins the collision.

The identity copy has its own structure, so removing `a` from `shallowCopy` does not remove `a` from the source. It still uses the same key references rather than creating new `a` and `b` objects.

### 10.3. Values and Map Comparison

Two `String` values with equal content but distinct objects yield different `containsValue` results. `entrySet` also distinguishes two pairs with the same key but different value references.

The `equals` lines demonstrate asymmetry when mixing identity semantics with a standard map. This is a reminder that compatibility with an API cannot be inferred solely from the fact that an object implements `Map`.

### 10.4. Nulls and Mutable Fields

The map can hold a `null` key and another mapping with a `null` value. `containsKey` distinguishes a present mapping from an absent one.

Changing `mutable.code` does not turn it into a different object. The table still finds it by exact reference; a new object with the same `code` does not match.

### 10.5. Graphs

Two source nodes with the same `label` are copied into two separate `Node` instances. Both branches share the same `shared` copy, and the cycle edge points back to `copiedRoot`.

`seen` has four entries, corresponding to the four source objects `root`, `left`, `right`, and `shared`. If label-based `equals` were used for the memo table, `left` and `right` could be wrongly merged even though they must keep two distinct identities.

## 11. Limitations in Applications

`IdentityHashMap` makes no iteration-order guarantee and is not synchronized. If ordered display is needed, produce the output according to an explicit rule; do not guess order from hash codes or insertion order.

Its fail-fast iterator is a best-effort mechanism for detecting certain improper modifications. It is not a substitute for multi-threaded coordination and must not be relied upon for correctness.

For a memo table serving a single graph transformation, keeping it local to the task's lifecycle usually keeps the semantic boundary clear: it speaks to the identity of that task's objects. Do not turn that table into a long-lived business index if the system needs to look up by value codes.

## 12. Common Pitfalls

| Pitfall | Correct Understanding |
|---|---|
| Two `equals` objects are always the same key | `IdentityHashMap` checks `==` for keys |
| Two different variable names are two keys | Two variables can hold the same reference |
| Recreating a string with the same content is enough for `get` | You must have the exact reference when using identity keys |
| `IdentityHashMap` fixes any mutable-key bug | It changes the key relation; only right when object identity is the requirement |
| `identityHashCode` is always unique | Hash codes can collide; reference comparison is still needed |
| Identity hash is a memory address or durable ID | The API makes no such guarantee |
| `Map<Integer, V>` of identity hashes can replace an identity map | It loses the reference-distinction step when hashes collide |
| `Map.equals` is always symmetric across all maps | Identity semantics can break expectations with standard maps |
| Copying to `HashMap` preserves all mappings | `equals` keys can be collapsed |
| Converting back recovers collapsed keys | Lost information cannot be reconstructed automatically |
| Copying a map deep-copies its objects | The new structure can still hold the same references |
| Putting into memo after copying children still handles all cycles | The copy must be recorded before recursing so cycles can reuse it |
| All overloads behaved the same across older JDKs | You must account for published version fixes |
| No `ConcurrentModificationException` means thread safety | Fail-fast is not a synchronization mechanism |

## 13. Practice Exercises and Solutions

### Exercise 1. Two Objects, Three Variables

`A` and `B` are two new `Key` instances with the same `code`; `C` is assigned `A`. Put `A`, `B`, and `C` into an `IdentityHashMap`. What is the maximum number of mappings from these three `put` calls?

**Solution:** Two, if `A` and `B` have distinct references. `C` reuses key `A` and updates the same mapping. The number of variables does not determine the number of key identities.

### Exercise 2. Lookup by Business Code

A service creates a new `Key` object for each request, yet equal codes must look up the same information. Is `IdentityHashMap` appropriate just because the `Key` objects are immutable?

**Solution:** No. Immutability does not change the fact that two newly created objects have distinct references. The requirement is lookup by `code` value, which needs an appropriate structure and `equals`/`hashCode` rules.

### Exercise 3. Identity Hash Codes

Two objects have the same `identityHashCode`. Can you conclude they are the same object? Should you use that number as the sole key in a table instead of the two references?

**Solution:** No. Hash collisions do not prove same identity. You must keep the reference-comparison step; a `HashMap` keyed only by the integer can no longer distinguish the two sources from that number alone.

### Exercise 4. Converting to a Standard Map

An `IdentityHashMap` contains two keys that are distinct objects yet `equals`, with different values. Does copying to a `HashMap` and copying back preserve both mappings? Can you guarantee which value wins?

**Solution:** It does not preserve both: `HashMap` can collapse them into one logical key, and converting back does not recover the lost information. You cannot promise a winner based on the source's unspecified iteration order; if conflict resolution is needed, define an explicit policy.

### Exercise 5. Memo in a Graph

Two `Node`s with the same `label` but distinct object identities both point to the same `leaf`. When copying, how many copies are needed for the two `Node`s and the `leaf`? Why does a table using `label`-based `equals` fail to do this properly?

**Solution:** Two separate copies are needed for the two `Node`s and one shared copy for `leaf`. Label-based `equals` can merge two `Node`s with distinct identities, corrupting the graph structure.

### Exercise 6. Memo Before or After?

A graph has `A` pointing to `B`, and `B` pointing to `A`. Why must the source–target pair be placed into the memo before copying the children?

**Solution:** When traversal from `B` returns to `A`, the algorithm must find the already-created target `A`. If it has not been recorded yet, it could keep creating copies and recursing repeatedly instead of closing the cycle back to the existing copy.

### Exercise 7. Nulls and Existing Mappings

`get` returns `null` for a reference key. Is that enough to prove the key is absent?

**Solution:** No. The key could be mapped to `null`. `containsKey` distinguishes the two in a valid access context. For a memo algorithm that only stores non-null copies, that specific invariant is what allows `null` to serve as an unvisited marker.

### Exercise 8. Map Comparison Issue

A standard map matches an identity map in content when calling `equals` in one direction, but not in the reverse direction. Should you "fix" this by comparing the `toString` strings of both maps?

**Solution:** No. `toString` does not establish a proper equality relation, the iteration order of an identity map is unspecified, and printed text can look identical even when references differ. Choose the comparison relation the problem actually requires and verify data according to that relation.

## 14. Defining Identity Boundaries Yourself

Before using `IdentityHashMap`, be able to state whether two objects with equal content but different references must keep two separate mappings. Then determine how keys are created, the table's lifecycle, and which APIs will receive the map or its views.

When object identity is the requirement, `==` is the core meaning of the key. When business value is the requirement, keeping value-based semantics prevents turning a specialized collection into a source of lookup bugs.
