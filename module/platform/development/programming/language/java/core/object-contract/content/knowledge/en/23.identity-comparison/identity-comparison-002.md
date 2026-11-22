# IdentityHashMap: Comparing Both Keys and Values with == Instead of equals()

## 1. Core idea

**java.util.IdentityHashMap<K, V>** is a specialized Map implementation: it uses **reference identity** instead of **logical equality** when comparing **both keys and values**.

Two easily confused operators/relationships:

- **a == b**, when a and b are object references, means both are pointing to **the exact same object** (or both are null).
- **a.equals(b)** is a logical comparison defined by the class of a. For example, String.equals examines character content; two Strings with identical content can still be two separate objects.

IdentityHashMap chooses the first relationship. Therefore:

- Two keys with different references **are treated as two separate keys**, even if key1.equals(key2) returns true.
- Looking up with a new object having the same content as a stored key **will not find** that key if the reference differs.
- Operations involving checking **values** also use identity; for instance, containsValue looks for a value with the same reference, rejecting an object that is merely equal by equals.
- This is **an intentional design choice**, not a misconfigured HashMap.

Important condition: the == operator between **two primitive types** compares primitive values; in IdentityHashMap, keys and values belong to type parameters K, V, so elements are handled as **object references**. With Integer or other wrapper types, do not let autoboxing obscure the boundary between reference identity and numeric value.

## 2. Comparison with ordinary HashMap

| Behavior | HashMap<K, V> | IdentityHashMap<K, V> |
| --- | --- | --- |
| Determining duplicate keys | Based on equals, coordinated with hashCode | Based on == (same reference) |
| Finding key with another object where equals is true | Can be found, if hashCode is consistent | Not found |
| Checking value with containsValue | Uses equals (null is handled) | Uses == (same reference) |
| Two keys with different references where equals is true | Treated as one key | Can coexist as two keys |
| Common goal | Map by value or logical identifier | Map by **specific object in memory** |
| Hash function for key lookup | Based on key.hashCode | Based on identity hashing mechanism |
| Accepts null | One null key, allows null values | One null key, allows null values |

An example:

~~~java
String k1 = new String("ID");
String k2 = new String("ID");

System.out.println(k1.equals(k2)); // true
System.out.println(k1 == k2);      // false
~~~

Using new String creates two separate objects; therefore String.equals returns true while the == operator returns false. For HashMap, k1 and k2 represent one logical key for the string "ID"; for IdentityHashMap, they are two distinct identity keys.

**Do not replace the example with two string literals** like "ID" and "ID" and conclude Java always treats strings with identical content as the same object. String literals may reference the same object via the string pool, whereas objects created separately with new still have different references. Identity comparison does not replace String.equals when you want to check content.

## 3. IdentityHashMap uses identity for both keys and values

### 3.1. Keys: get, put, containsKey, and remove

Suppose:

~~~java
String first = new String("account");
String second = new String("account");
IdentityHashMap<String, Integer> identities = new IdentityHashMap<>();
identities.put(first, 10);
identities.put(second, 20);
~~~

The lines above are an excerpt in a context where java.util.IdentityHashMap is imported.

Because first != second under the == operator, the map has **two entries** even though first.equals(second) is true.

- identities.get(first) returns 10.
- identities.get(second) returns 20.
- identities.get(new String("account")) returns null if that exact newly created object has not been stored, because the new object does not share the same reference as first or second.
- identities.containsKey(new String("account")) returns false.
- identities.remove(new String("account")) does not remove either of the two entries above.

Note that a null value returned from get can mean **the key is absent** or **the key exists and holds a null value**. If you need to distinguish them, check containsKey with the exact key reference.

### 3.2. Values: containsValue and key–value pair checks

In IdentityHashMap, searching for a **value** also uses ==:

~~~java
String stored = new String("ACTIVE");
IdentityHashMap<String, String> map = new IdentityHashMap<>();
String key = new String("user-1");
map.put(key, stored);

System.out.println(map.containsValue(stored));               // true
System.out.println(map.containsValue(new String("ACTIVE"))); // false
~~~

The new String object has the same content "ACTIVE" but a different reference, so containsValue returns false. This is an easily overlooked point: **IdentityHashMap does not only use == for keys**.

Several checks on the entry set or Map operations involving both key and value simultaneously are also affected by the identity rule. When you need the exact behavior of an API such as remove(key, value), contains, replace, or equals between two maps, rely on IdentityHashMap's documentation rather than applying HashMap intuition.

This relationship does not mean **each value can only be used once**: multiple keys can point to the same value object; the map still allows such entries.

### 3.3. null

IdentityHashMap supports **one null key** and null values. Because null == null is true, two put(null, value) calls update the same null key rather than creating another key.

~~~java
IdentityHashMap<Object, Object> map = new IdentityHashMap<>();
map.put(null, null);
System.out.println(map.containsKey(null));   // true
System.out.println(map.containsValue(null)); // true
~~~

You cannot call the equals instance method on a null reference. The == identity relation handles null directly without invoking a method on that object.

## 4. Complete Java 17+ program

Save as **IdentityHashMapDemo.java**:

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Set;

public class IdentityHashMapDemo {
    static final class Node {
        final String label;

        Node(String label) {
            this.label = label;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Node other
                    && label.equals(other.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    public static void main(String[] args) {
        String k1 = new String("code");
        String k2 = new String("code");
        String v1 = new String("ready");
        String v2 = new String("ready");

        IdentityHashMap<String, String> identity =
                new IdentityHashMap<>();
        identity.put(k1, v1);
        identity.put(k2, v2);

        Map<String, String> ordinary = new HashMap<>();
        ordinary.put(k1, v1);
        ordinary.put(k2, v2);

        System.out.println("keys equals: " + k1.equals(k2));
        System.out.println("keys ==: " + (k1 == k2));
        System.out.println("values equals: " + v1.equals(v2));
        System.out.println("values ==: " + (v1 == v2));
        System.out.println("IdentityHashMap size: " + identity.size());
        System.out.println("HashMap size: " + ordinary.size());

        System.out.println("identity get same key: "
                + (identity.get(k1) == v1));
        System.out.println("identity get equal new key: "
                + identity.get(new String("code")));
        System.out.println("identity contains equal new key: "
                + identity.containsKey(new String("code")));
        System.out.println("identity contains exact value: "
                + identity.containsValue(v1));
        System.out.println("identity contains equal new value: "
                + identity.containsValue(new String("ready")));
        System.out.println("HashMap contains equal new value: "
                + ordinary.containsValue(new String("ready")));
        System.out.println("HashMap get equal new key: "
                + (ordinary.get(new String("code")) == v2));

        IdentityHashMap<Object, Object> withNull =
                new IdentityHashMap<>();
        withNull.put(null, null);
        System.out.println("null key present: "
                + withNull.containsKey(null));
        System.out.println("null value present: "
                + withNull.containsValue(null));

        Node n1 = new Node("same");
        Node n2 = new Node("same");
        IdentityHashMap<Node, Boolean> visited =
                new IdentityHashMap<>();
        visited.put(n1, Boolean.TRUE);
        visited.put(n2, Boolean.TRUE);

        Set<Node> ordinaryNodes = new HashSet<>();
        ordinaryNodes.add(n1);
        ordinaryNodes.add(n2);

        Set<Node> identitySet =
                Collections.newSetFromMap(
                        new IdentityHashMap<Node, Boolean>());
        identitySet.add(n1);
        identitySet.add(n2);

        System.out.println("nodes equals: " + n1.equals(n2));
        System.out.println("visited identities: " + visited.size());
        System.out.println("ordinary HashSet nodes: "
                + ordinaryNodes.size());
        System.out.println("identity Set nodes: "
                + identitySet.size());
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac -encoding UTF-8 IdentityHashMapDemo.java
java IdentityHashMapDemo
~~~

Stdout output:

~~~text
keys equals: true
keys ==: false
values equals: true
values ==: false
IdentityHashMap size: 2
HashMap size: 1
identity get same key: true
identity get equal new key: null
identity contains equal new key: false
identity contains exact value: true
identity contains equal new value: false
HashMap contains equal new value: true
HashMap get equal new key: true
null key present: true
null value present: true
nodes equals: true
visited identities: 2
ordinary HashSet nodes: 1
identity Set nodes: 2
~~~

### Why is the output like this?

1. **Two keys k1/k2:** equals for String is true, but == is false. IdentityHashMap has two entries; HashMap only has one entry and the second put overwrites the value of the logical key "code".
2. **Lookup with a new key:** IdentityHashMap does not find the new String with the same content. HashMap finds it because String.equals and String.hashCode examine content.
3. **Values v1/v2:** two Strings equal in content but with different references. containsValue(v1) is true, while containsValue(new String("ready")) is false on IdentityHashMap; HashMap accepts an equivalent value object under equals.
4. **null:** one null key and null values are supported. containsKey/containsValue distinguish the presence of null once put.
5. **Two Nodes with the same label:** equals is true and hashCode is identical by Node's definition, yet n1 and n2 are two separate objects. HashSet merges them into one element; IdentityHashMap and a Set created from IdentityHashMap keep both.

The program creates a Node class that intentionally defines equals/hashCode by label, demonstrating that identity comparison **is independent** of the equality criteria implemented by the Node class. Map iteration order is not used in the output so there is no dependency on entry traversal order.

## 5. Identity hashing mechanism and System.identityHashCode

IdentityHashMap is still a hash structure, but it does not use the **key.hashCode()** method as the logical hash criterion for key lookup. It hashes based on the object's **identity**; System.identityHashCode(object) is the API that provides the identity-style hash code even when the class overrides hashCode.

~~~java
Object value = new String("same");
int identityHash = System.identityHashCode(value);
int logicalHash = value.hashCode();
~~~

These are two different concepts:

- **value.hashCode()** can be customized by the class. String.hashCode is computed from content, so two Strings with different references and identical content have the same logical hash.
- **System.identityHashCode(value)** returns the hash code per the default identity-based implementation, even if the class overrides hashCode. Do not interpret it as a memory address or a globally unique identifier number.
- **Two different objects can still share the same identity hash**: int only has a finite number of values. The map resolves hash collisions by checking key identity with ==, rather than concluding it is the same key because the hash codes match.
- **Identity hash code is not a durable key to store in a database**: there is no guarantee of uniqueness or stability across JVM runs.

You do not need to call System.identityHashCode yourself when using IdentityHashMap; the structure implements the identity mechanism internally. Recomputing an overridden hashCode in a class cannot turn HashMap into IdentityHashMap either if equality logic still relies on equals.

## 6. Why does IdentityHashMap differ from the standard Map contract?

The general Map interface defines operations based on the notion of keys being **equal according to equals** and compatible hashCode. Java documentation explicitly states that IdentityHashMap is an implementation that intentionally **violates Map's general contract of object-equality**: replacing it with the == relation.

This causes surprises if you swap implementation types while keeping the same API:

~~~java
Map<String, Integer> map = new IdentityHashMap<>();
String saved = new String("item");
map.put(saved, 42);

// A new key object with the same content cannot look it up:
Integer result = map.get(new String("item")); // null
~~~

The code still compiles because IdentityHashMap implements Map, but **the meaning of equality has changed**. Assigning to a Map-typed variable does not "switch" comparison back to equals.

Practical consequences:

- When comparing maps, entry sets, or performing equals/hashCode-related operations across different Map types, you may get unexpected results due to inconsistent equality rules.
- Two maps whose data looks identical when printed do not guarantee they have the same key/value relationships; do not rely on toString to determine equality.
- Using IdentityHashMap in a public API requires clearly documenting that **object identity** is part of the contract. If the system expects keys to be recreatable from IDs/strings, use HashMap or a value-based Map structure.
- Do not "performance-upgrade" HashMap to IdentityHashMap just because it avoids calling equals; changing the structure can break program correctness.

## 7. When should it be used?

### 7.1. Recording visited objects in a graph

When traversing an object graph with cycles, two Node instances with different references—even if equals is true—may still be **two physical nodes needing separate processing**. An IdentityHashMap<Node, Boolean> is a useful choice to mark each visited instance, especially if Node's equals compares by content or is expensive to compute.

~~~java
// Declared inside a graph processing method:
IdentityHashMap<Node, Boolean> visited = new IdentityHashMap<>();

if (visited.put(node, Boolean.TRUE) == null) {
    // First time encountering this exact node reference.
    // Traverse the node's links here.
}
~~~

The condition here is only valid when the application consistently stores Boolean.TRUE as the marker value, **never storing null as a value**. If a node was previously stored with a null value, put returning null does not prove it is the first visit; use containsKey if you need to handle null values reliably.

### 7.2. Mapping metadata per specific object

A structure checker, alias tracker, serialization tool, or source-to-clone object mapper sometimes needs to attach metadata to **each specific instance**, not to every instance equal under equals.

If two different objects represent the same content yet are two separate nodes in memory, IdentityHashMap can store two separate records. That matters when preserving information about object sharing or detecting cycles in reference structures.

### 7.3. Creating an identity-based Set

If you want a set that keeps elements with different references even when equals is true, you can create:

~~~java
Set<Node> seen = java.util.Collections.newSetFromMap(
        new java.util.IdentityHashMap<Node, Boolean>());
~~~

The map passed to newSetFromMap must **be empty**. The resulting Set uses IdentityHashMap's key rules, namely == identity. For a requirement needing only an identity Set, this approach expresses intent more clearly than using IdentityHashMap<Node, Boolean> and manipulating values directly.

## 8. When should it not be used?

**Do not use IdentityHashMap** when keys represent values, content, or logical IDs:

- Strings that are usernames, product codes, URLs, or configuration keys;
- Integer/Long that are serial numbers, database IDs, or status codes;
- records or value objects designed with equals/hashCode over their components;
- keys that can be recreated from a request, JSON, database row, or an equivalent copy.

In these cases, HashMap usually makes more sense, because objects with the same value are found even with different references.

**Mistake-prone example with boxing:**

~~~java
IdentityHashMap<Integer, String> values = new IdentityHashMap<>();
values.put(Integer.valueOf(1000), "found");

// Do not assume a new Integer with the same numeric value
// will share the same reference as the key stored above.
String answer = values.get(Integer.valueOf(1000));
~~~

Wrapper objects may be cached or newly allocated depending on the API and value range, so do not use wrapper == or IdentityHashMap to express numeric equality. The example above only illustrates **a design risk**, not a claim that every JVM always yields answer as null.

When you need value checks, use equals and a value-based Map. When you need identity, create or pass **the exact original key object**, rather than recreating a new object with equivalent data.

## 9. Implementation characteristics and operational notes

- **Does not maintain order:** IdentityHashMap does not guarantee element order by insertion time or by value. Do not rely on the order of keySet, entrySet, values, or toString.
- **Not synchronized by default:** like HashMap, it does not provide synchronization for concurrent reads/writes. Use synchronization or a thread-safe design if multiple threads update the map.
- **initial expectedMaxSize:** the constructor accepts an expected element count to size the internals; it is not a hard cap on the number of entries allowed. Negative values are invalid.
- **Memory and lifecycle:** the map holds strong references to stored keys and values. Therefore, using it as a metadata table can keep objects alive longer than desired if entries are not removed; manage lifecycles or consider another structure when weak keys are needed.
- **Mutating key fields:** unlike HashMap which uses value-based hashCode, IdentityHashMap still identifies the same key by its exact reference when the object's internal state changes. However, mutating an object can still affect program logic, so this does not mean mutable objects can be modified arbitrarily in every application.
- **Do not equate identity hash with uniqueness:** collisions can still occur and object identity is decided by ==, not by comparing two identityHashCode numbers.

## 10. Misconceptions and how to verify

| Misconception | Reality |
| --- | --- |
| IdentityHashMap only uses == for keys | Uses identity for both keys **and values** |
| If two keys have equals true, the later put always overwrites | Only overwrites when it is **the exact same key reference** |
| The class name IdentityHashMap means a map of unique hash codes | identity hashes can collide; == confirms identity |
| Can look up with a new String having the same content | Only works if the reference matches; use HashMap to compare content |
| containsValue uses equals like any Map | IdentityHashMap checks == between values |
| Using the same Map generic parameters means both implementations share the same equality | Generics specify types, not equality policy |
| null cannot be used with an identity map | null keys and null values are still supported |
| An identity map is always faster than HashMap | Performance depends on size, hash distribution, and usage; choose by semantics first |

**Code review checklist:**

1. Does the problem care about the same object or the same value? If the same value, usually do not choose IdentityHashMap.
2. Do callers recreate keys from Strings/IDs? If so, calling get with a new object will not work as expected.
3. Do value-search operations need equals? If so, IdentityHashMap's containsValue will behave differently than expected.
4. Are there null keys/values? Distinguish absent entries from entries containing null.
5. Is the map exposed via the Map interface to code assuming the standard equals contract? If so, clarify or change the structure.
6. If used as a visited set, do you need to distinguish each node instance even when Node.equals is true?
7. Are there memory lifecycle issues or multi-threaded operations? Manage strong references, entry removal, and appropriate synchronization.

## 11. Remember

**IdentityHashMap asks "is this the exact object?"**, not "do two objects have the same value?". Therefore:

- Keys are identified using **==**, not equals.
- Values are also checked using **==**, notably in containsValue.
- Two objects with different references where equals is true are kept separately as keys.
- The map fits object graphs, per-instance metadata, and detecting shared references; it is unsuitable as a map keyed by IDs or content.

Use it only when **reference identity is precisely what the business logic requires**. If you want lookup by logical value, prefer HashMap with a contract-compliant equals/hashCode.