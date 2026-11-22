# Do Not Replace HashMap with IdentityHashMap When Business Logic Needs Value Equality

## 1. Key decision: what does "same key" mean?

When choosing a Map structure in Java, you must first answer **which two keys are considered the same key**. For Java objects, there are two distinct concepts:

- **Logical equality**: two objects can be two separate instances yet represent the same business value. This rule is expressed through **equals(Object)** and its companion contract **hashCode()**.
- **Same object (reference identity)**: two references point to **the exact same instance**. Java checks this with the **==** operator on references.

**HashMap** chooses **value** semantics: keys that are different instances yet have **equals true** (with compatible hashCode) must be recognized as the same key. **IdentityHashMap** chooses **reference identity** semantics: only references where **==** holds are treated as the same key. Therefore, switching **HashMap** to **IdentityHashMap** is **a change in business logic**, not merely a memory, speed, or hashing algorithm optimization.

Example: two **CustomerId("C-17")** objects created from two different requests. If business rules specify that the same customer code means the same customer, HashMap must allow using the second instance to find the record inserted with the first instance. IdentityHashMap does not guarantee this and usually returns not found, even though **equals** between them returns true.

**Default selection rule:** When keys are customer IDs, order IDs, UUIDs, Strings, records, value objects, or combinations of business-identifying attributes, normally use **HashMap<K,V>** (or LinkedHashMap if order is needed). Only use **IdentityHashMap** when the requirement is genuinely to distinguish individual objects **by reference**.

## 2. HashMap's equals/hashCode contract

**HashMap<K,V>** uses **hashCode()** to help locate lookup buckets and **equals(Object)** to check key equivalence. Foundational conditions of the Java contract:

1. **Reflexive:** a.equals(a) must be true.
2. **Symmetric:** a.equals(b) has the same result as b.equals(a).
3. **Transitive:** if a equals b and b equals c, then a equals c.
4. **Consistent:** when data participating in comparison does not change, equals results remain stable.
5. **With null:** a.equals(null) is false for non-null a.
6. **Compatible hash:** if a.equals(b) is true, then a.hashCode() **must equal** b.hashCode().

The converse of the hash rule is **not** true: two keys with the same hashCode may be unequal. HashMap handles hash collisions by continuing to inspect keys.

When a new key is inserted via **put** and is equivalent to an existing key, the value associated with that key is **replaced**; size does not increase. In ordinary HashMap implementations, the stored representative key is kept when only updating the value for the same logical key. Do not rely on the "representative key" reference unless an API or requirement truly needs it.

**HashMap** allows one null key and null values. Because **get(key)** can return null either when there is no mapping or when mapped to null, use **containsKey(key)** to distinguish if needed. This is a Map property independent of choosing equals or reference identity.

## 3. IdentityHashMap replaces equals with ==

**java.util.IdentityHashMap<K,V>** is a specialized Map:

- Compares **keys** using **==**, instead of calling value-based equals.
- Hashes keys using **System.identityHashCode(key)**, instead of hashCode overridden in the key class.
- Two objects with the same content and equals true that have **different references** are still **two keys**.
- Two variables referencing the same instance are **one key**, even if that object overrides equals unusually.
- Allows a null key and null values; identity checks with null are still handled as a distinct Map key.
- Does not guarantee iteration order. Do not use entrySet iteration results to infer insertion order.

IdentityHashMap **intentionally violates the value-based equals convention** commonly used by Maps and related views. In particular, in programs mixing regular Maps with IdentityHashMap, do not assume checking **mapA.equals(mapB)** always has the same meaning or symmetry as between two ordinary Maps; the Java documentation warns about this.

**System.identityHashCode(obj)** is not a Java-guaranteed memory address and is not guaranteed unique across objects. Identity hash collisions can occur; IdentityHashMap still relies on **reference ==** to distinguish keys. Do not use identity hash numbers as permanent IDs or business keys.

## 4. Java 17 example: same value, two different Map results

Create the file **HashVsIdentityMapDemo.java**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class HashVsIdentityMapDemo {
    record CustomerId(String value) {}

    public static void main(String[] args) {
        CustomerId first = new CustomerId("C-17");
        CustomerId second = new CustomerId("C-17");
        CustomerId lookup = new CustomerId("C-17");

        System.out.println("same reference: " + (first == second));
        System.out.println("same value: " + first.equals(second));
        System.out.println("hash equal: " +
            (first.hashCode() == second.hashCode()));

        Map<CustomerId, String> byValue = new HashMap<>();
        byValue.put(first, "created");
        byValue.put(second, "updated");

        System.out.println("HashMap size: " + byValue.size());
        System.out.println("HashMap lookup: " + byValue.get(lookup));

        Map<CustomerId, String> byIdentity =
            new IdentityHashMap<>();
        byIdentity.put(first, "created");
        byIdentity.put(second, "updated");

        System.out.println("IdentityHashMap size: " +
            byIdentity.size());
        System.out.println("IdentityHashMap first: " +
            byIdentity.get(first));
        System.out.println("IdentityHashMap second: " +
            byIdentity.get(second));
        System.out.println("IdentityHashMap fresh: " +
            byIdentity.get(lookup));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac HashVsIdentityMapDemo.java
java HashVsIdentityMapDemo
~~~

Output:

~~~text
same reference: false
same value: true
hash equal: true
HashMap size: 1
HashMap lookup: updated
IdentityHashMap size: 2
IdentityHashMap first: created
IdentityHashMap second: updated
IdentityHashMap fresh: null
~~~

**Why does HashMap have only one entry?** Record **CustomerId** auto-generates equals/hashCode from its String component. Both first and second contain "C-17", so the two keys are equal. The second put updates the logical key's value. A third CustomerId instance with the same code still finds **"updated"**.

**Why does IdentityHashMap have two entries?** first and second are created by two **new CustomerId(...)** expressions, so their references differ. IdentityHashMap does not use the record-generated equals/hashCode to decide key equality. A new **lookup** instance is neither first nor second, so **get(lookup)** returns null.

If the program needs to represent "customer C-17", the IdentityHashMap result is **semantically wrong in business terms**: the same customer is split across multiple entries. Neither an exception nor a compiler warning flags this issue.

## 5. String and wrappers: deceptive cases when testing with ==

A mistake is testing IdentityHashMap with **string literals** and assuming keys match by content:

~~~java
String a = "paid";
String b = "paid";
System.out.println(a == b); // often true because string literals are interned
~~~

This snippet is illustrative only. Java interns corresponding string literals; this causes both variables in the example to point to the same object. However, strings read from files, JSON, databases, or created with **new String(...)** can be different instances despite identical values.

Create the file **StringIdentityDemo.java**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class StringIdentityDemo {
    public static void main(String[] args) {
        String first = new String("paid");
        String second = new String("paid");

        Map<String, Integer> byValue = new HashMap<>();
        Map<String, Integer> byIdentity = new IdentityHashMap<>();

        byValue.put(first, 1);
        byValue.put(second, 2);
        byIdentity.put(first, 1);
        byIdentity.put(second, 2);

        System.out.println("same object: " + (first == second));
        System.out.println("same text: " + first.equals(second));
        System.out.println("value map size: " + byValue.size());
        System.out.println("identity map size: " + byIdentity.size());
        System.out.println("value lookup: " +
            byValue.get(new String("paid")));
        System.out.println("identity lookup: " +
            byIdentity.get(new String("paid")));
    }
}
~~~

Run command:

~~~bash
javac StringIdentityDemo.java
java StringIdentityDemo
~~~

Output:

~~~text
same object: false
same text: true
value map size: 1
identity map size: 2
value lookup: 2
identity lookup: null
~~~

Wrapper types such as **Integer** may also be cached for certain values; do not infer business semantics of **==** from a few test results involving caching. If values are numbers, strings, or data keys, rely on **equals** or appropriate primitive comparisons, not on accidental reference sharing.

Do not "fix" IdentityHashMap misuse by calling **String.intern()** indiscriminately. Interning alters reference-sharing policy rather than replacing a value contract; forcing all data through interning can incur memory-management costs or consequences and still easily miss other input sources.

## 6. Consequences in real data processing

A business map is commonly used to:

- **Aggregate data by customerId:** a customer may appear multiple times across different logs or payloads.
- **Deduplicate by orderId:** two records with the same identifier must be counted as one order.
- **Look up state by correlationId:** a request passing through multiple layers can create multiple new Strings with identical content.
- **Count logical entities:** two value-object copies representing the same ID must collapse into one group.
- **Cache by parameter key:** two keys with equal parameter sets must access a shared entry.

In these problems, IdentityHashMap can **duplicate entries**, miscount totals, miss caches, lose the ability to look up using newly constructed equivalent keys, or make results depend on **whether the system happens to reuse the same instance**.

For example, distributed data processing often deserializes two independent JSON payloads into two independent Java objects. They may have **equals true**, yet not be the same object. IdentityHashMap treats them as two different customers if that object is used as the key, even though the business domain considers the same ID one customer.

This is why you should not pick IdentityHashMap just because its name contains **HashMap** and assume it is "more optimized". It is **a structure with its own semantics**, intended for problems requiring physical references.

## 7. Example: composite business key from a record

Another mistake is grouping by ID code while forgetting the namespace. In a multi-tenant system, the same customer code in two tenants can represent two different customers. **HashMap** still needs a properly designed logical key.

Create the file **BusinessKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class BusinessKeyDemo {
    record CustomerKey(String tenant, String customerCode) {}

    public static void main(String[] args) {
        CustomerKey first = new CustomerKey("A", "C-17");
        CustomerKey duplicate = new CustomerKey("A", "C-17");
        CustomerKey otherTenant = new CustomerKey("B", "C-17");

        Map<CustomerKey, Integer> counts = new HashMap<>();
        counts.merge(first, 1, Integer::sum);
        counts.merge(duplicate, 1, Integer::sum);
        counts.merge(otherTenant, 1, Integer::sum);

        System.out.println("entries: " + counts.size());
        System.out.println("tenant A: " +
            counts.get(new CustomerKey("A", "C-17")));
        System.out.println("tenant B: " +
            counts.get(new CustomerKey("B", "C-17")));
    }
}
~~~

Run:

~~~bash
javac BusinessKeyDemo.java
java BusinessKeyDemo
~~~

Output:

~~~text
entries: 2
tenant A: 2
tenant B: 1
~~~

Record **CustomerKey** auto-generates equals/hashCode from **both components**. Two records with the same tenant and same customerCode form one key, whereas the same customerCode in another tenant does not. HashMap accurately expresses this key contract.

If IdentityHashMap were used, tenant A's two records would become two keys because they were created separately. If only String customerCode were used as the HashMap key without tenant, customers across different tenants would be wrongly merged. Hence **choosing HashMap and designing the key properly** are both essential.

## 8. When is IdentityHashMap actually appropriate?

IdentityHashMap is designed for situations where **object identity has a distinct meaning apart from equals value**.

Examples:

1. **Tracking objects in object-graph algorithms:** two nodes have identical data yet are two distinct physical nodes; the algorithm must remember each visited node.
2. **Deep copying or serializing graphs with shared references:** requires mapping **original object → cloned object**, where two original objects with equal content still need two separate clones when they are two different nodes.
3. **Tracking auxiliary state per instance:** diagnostics, heap analysis, or object-structure walkers needing to distinguish references.
4. **Checking reference identity:** storing an attribute tied to **a specific object itself**, not to any object having the same value.

In such situations, if you used HashMap and the node class overrode equals by data, **two distinct nodes** could accidentally be merged. IdentityHashMap fulfills the requirement to distinguish instances.

If tracking nodes with `Collections.newSetFromMap(new IdentityHashMap<>())`, adding each instance once keeps two distinct nodes even if their labels match. DFS/BFS algorithms and cycle detection are covered in full in the lesson **Using Identity When Traversing and Tracking Object Graphs**.

**Caution:** IdentityHashMap holds strong references to keys and values like a normal map while entries remain; do not use it as a weak-reference mechanism. If you need to associate metadata with objects while allowing garbage collection, evaluate structures like **WeakHashMap** and its own contract. Do not equate the two structures merely because both contain the word Map.

## 9. Special case: objects with a broken equals contract

Someone might switch HashMap to IdentityHashMap because **HashMap "cannot find" keys**. Yet the usual root causes are:

- A class overrides **equals** but forgets to override a compatible **hashCode**.
- Fields participating in equals/hashCode mutate after the object is used as a key.
- Array fields use identity equals/hashCode even though business rules require content comparison.
- Keys contain only part of the identifier, wrongly merging distinct records.
- Using **LocalDateTime**, **OffsetDateTime**, **BigDecimal**, or another value type whose equals contract does not match business requirements.

**IdentityHashMap can mask some symptoms** because it bypasses custom equals/hashCode, but the consequence is changing "one key per value" into "one key per instance". If the system needs value-based equals, the proper fix is to **repair the key type's contract and make keys immutable**, or extract a dedicated immutable value key.

### Mutable key example: this is not a reason to switch to IdentityHashMap

Create the file **MutableKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;

public class MutableKeyDemo {
    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof MutableKey other
                && Objects.equals(code, other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    public static void main(String[] args) {
        MutableKey key = new MutableKey("A");
        Map<MutableKey, String> byValue = new HashMap<>();
        Map<MutableKey, String> byIdentity = new IdentityHashMap<>();

        byValue.put(key, "found");
        byIdentity.put(key, "found");

        key.code = "B";

        System.out.println("HashMap after edit: " + byValue.get(key));
        System.out.println("IdentityHashMap after edit: " +
            byIdentity.get(key));

        System.out.println("IdentityHashMap equivalent new key: " +
            byIdentity.get(new MutableKey("B")));
    }
}
~~~

Run:

~~~bash
javac MutableKeyDemo.java
java MutableKeyDemo
~~~

Output:

~~~text
HashMap after edit: null
IdentityHashMap after edit: found
IdentityHashMap equivalent new key: null
~~~

**Explanation:** HashMap stores the key in a bucket organized by the hash of String **"A"**. After editing code to **"B"**, hashCode changes, so a new get using B's hash fails to find the old entry in this example. IdentityHashMap still finds it when using **the same key reference**, because identity does not change; however, for another object with the same code B, it still does not find it.

**Business fix:** use **record MutableKeySnapshot(String code)** or an immutable key class; when code needs to change, create **a new key** and update the Map intentionally. Do not change the Map type merely to avoid symptoms of mutable keys.

## 10. Do not use identityHashCode as an ID value

Two important concepts:

- **obj == other** proves two references are the same object in the running context.
- **System.identityHashCode(obj) == System.identityHashCode(other)** **does not prove** two references are the same object, because identity hashes can collide.

Do not write identityHashCode to a database as a unique key or use it to correlate objects across processes or JVM restarts. That number carries neither business identification meaning nor a durable memory address.

If the application needs entity IDs, use explicitly managed IDs in the model (such as UUIDs or database keys). If a temporary algorithm needs to distinguish references, use **==** or IdentityHashMap/identity set to preserve direct reference relationships directly.

## 11. HashMap and IdentityHashMap in public APIs

The **Map<K,V>** signature hides differences in key comparison. Both implementations can be passed into a method accepting Map, yet lookup/put behavior depends on the actual map instance.

For instance, a method calling **containsKey(new CustomerId("C-17"))** may work with HashMap and fail with an IdentityHashMap that received an equivalent CustomerId with a different reference. If an API requires "logical key equality", passing IdentityHashMap **violates a precondition**. Documentation and tests must express this condition, or the module should proactively construct a HashMap with explicit value-object keys.

Some places attempt to use IdentityHashMap to "speed up" by skipping complex equals calls. That alters business outcomes rather than being a safe optimization. Optimize only after proving with real data and applying a **semantics-preserving** transformation. For value-based Maps, you can improve hashCode, key immutability, capacity allocation, or dedicated key design while keeping HashMap.

Do not use **IdentityHashMap** to infer that a key's **equals** does not matter to the system: other APIs still use equals, such as HashSet, other HashMaps, List.contains, and many value-comparison operations.

## 12. Verifying semantics with a minimal test suite

For problems that need grouping by value, test at least:

1. **Two independently created instances, same value:** equals true, hashCode equal; when put into HashMap, size increases only once.
2. **Lookup with a third instance:** HashMap returns the right value even though the reference differs from the inserted key.
3. **Different business values:** equals false and kept as two keys; hashCode may happen to collide yet must not merge.
4. **Composite keys:** components such as tenantId, entity type, code, and version are evaluated per domain definition.
5. **Stable keys:** do not mutate fields affecting equals/hashCode while the key remains in the Map.
6. **Null:** if null is allowed, check containsKey to distinguish "no entry" from "entry with null value".
7. **Arrays:** if business rules treat content as value, use Arrays.equals/hashCode or a contract-compliant wrapper.
8. **Data instances:** deserialize the same record twice, creating two independent objects, then test lookup/grouping.
9. **If truly using identity:** assert via tests that two equals objects with different references **must** be two separate keys.

Testing with independent data matters because string literals, boxing, or instance-reuse mechanisms can cause overly simple examples to accidentally share identity and hide bugs.

## 13. Decision table for applications

| Real requirement | Typically suitable structure | Equality criterion |
| --- | --- | --- |
| State by **customerId**, **orderId**, UUID, record key | **HashMap** | Key's **equals/hashCode** |
| Lookup by **String** constructed from multiple sources | **HashMap<String,V>** | String content |
| Grouping by **tenant + id** | **HashMap<BusinessKey,V>** | Composite value key's equals/hashCode |
| Need group ordering by insertion order | **LinkedHashMap** | Still **equals/hashCode** |
| Need sorted order by Comparator | **TreeMap** | **compare == 0** per comparator; must check consistency with equals |
| Tracking **individual node objects** even when equals matches | **IdentityHashMap** | **==** and identity hash |
| Set of objects **by identity** | **Collections.newSetFromMap(new IdentityHashMap<>())** | **==** |
| Metadata attached to objects, needing weak-reference management | Consider **WeakHashMap** or an appropriate reference mechanism | **WeakHashMap still has its own semantics and uses equals**, not a drop-in replacement for IdentityHashMap |

**Core takeaway:** **HashMap** and **IdentityHashMap** answer two different questions. If the system requires "two records with the same business value are one key", keep **HashMap** with keys having a correct and stable equals/hashCode. **IdentityHashMap** is only appropriate when the primary requirement is **the same object reference**; substituting it into a value-based Map breaks data correctness without causing a compilation error.

Official references: [HashMap (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [IdentityHashMap (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html), [Object.equals/hashCode (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).