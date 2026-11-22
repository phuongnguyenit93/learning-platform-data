# Grouping Objects into Same-Value Groups According to the equals Contract

## 1. The Problem and the Meaning of "Same Value"

Given a set or list of Java objects, we want to partition them into groups such that **two objects are in the same group if and only if they are considered equal according to the chosen rule**. This is a partition: every input element belongs to exactly one group; no element is left out, and no element is placed into two groups. A group may contain multiple distinct **instances** that share the same **logical value**.

In the context of the **equals** contract, the "same value" relation is usually defined by **a.equals(b)**, not **a == b**:

- **==** on references asks whether they point to the exact same object in memory.
- **equals(Object)** asks whether they are equivalent in logical value, according to how that class implements it.
- **hashCode()** supports efficient lookup and grouping in hash-based structures such as **HashMap**, **LinkedHashMap**, and **HashSet**; it does not by itself define what makes objects equal.

For example, two employee records that are different instances yet share the same business identifier can belong to the same group, if the class specifies that **equals** inspects only the employee ID. Conversely, if the domain considers both the ID and version to be part of the value, they must belong to different groups. **There is no single "correct" grouping for every system**: the exact equality criteria must be defined first.

### Conditions for a Valid Grouping

Define `a ~ b` when `a.equals(b)` is true. To partition into consistent equivalence classes, this relation must satisfy:

1. **Reflexive:** `a.equals(a)` is always true for non-null `a`.
2. **Symmetric:** if `a.equals(b)`, then `b.equals(a)`.
3. **Transitive:** if `a.equals(b)` and `b.equals(c)`, then `a.equals(c)`.
4. **Consistent:** repeated calls for the same two objects must give the same result as long as the information used for comparison has not changed.
5. **Non-null:** `a.equals(null)` is always false when `a` is non-null.

These are the core conditions of the **Object.equals** contract. Violating symmetry or transitivity makes the notion of a "group" contradictory: an element might belong to one group when compared against representative A yet belong to a different group when compared against B. Violating consistency can cause grouping results to change mid-processing.

**Companion rule:** if `a.equals(b)` is true, `a.hashCode()` **must** equal `b.hashCode()`. Two objects with the same hash code are **not required** to be equal (hash collisions are valid). As long as a key does not change in the fields participating in **equals/hashCode**, its `hashCode` value must also remain stable while used as a key.

## 2. Choosing the Key Object: Group by Element's equals or by Business Key?

There are two related but distinct problems:

| Grouping Approach | Same-Group Criterion | When Appropriate |
| --- | --- | --- |
| Use the object itself as the key | Two elements whose **equals** returns true | The class's **equals** already expresses the right meaning of "same value" |
| Derive an immutable key from the element | Two keys whose **equals** returns true | Wanting to group by specific fields without **changing** the equality definition of the whole object |

Example: an order object may use **equals** by order ID, while a report wants to group by customer ID. In that case, extract the customer ID as the key; do not alter **Order.equals** merely to serve a single report.

For HashMap/LinkedHashMap keys, Java uses both **hashCode** and **equals** to identify equivalent keys. When two equal keys are placed into the map, the map keeps **one entry for the group**. The entry's value can be a **List<T>** storing every member of the group, including duplicate values.

## 3. Complete Example: Grouping by Object's equals

Suppose the system specifies that **employees with the same id are logically the same employee**. The display name is not part of identity: names can change, yet versions carrying the same id need to be grouped together.

Create the file **GroupByEqualsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class GroupByEqualsDemo {
    static final class Employee {
        private final String id;
        private final String name;

        Employee(String id, String name) {
            this.id = Objects.requireNonNull(id, "id");
            this.name = Objects.requireNonNull(name, "name");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Employee other)) {
                return false;
            }
            return id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        List<Employee> input = List.of(
            new Employee("E02", "An"),
            new Employee("E01", "Binh"),
            new Employee("E02", "An (new)"),
            new Employee("E03", "Chi"),
            new Employee("E01", "Binh (new)")
        );

        Map<Employee, List<Employee>> groups = new LinkedHashMap<>();

        for (Employee employee : input) {
            groups.computeIfAbsent(employee, key -> new ArrayList<>())
                  .add(employee);
        }

        for (Map.Entry<Employee, List<Employee>> entry : groups.entrySet()) {
            String names = entry.getValue().stream()
                .map(employee -> employee.name)
                .collect(Collectors.joining(", "));

            System.out.println(entry.getKey().id + " -> [" + names + "]");
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac GroupByEqualsDemo.java
java GroupByEqualsDemo
~~~

Exact output:

~~~text
E02 -> [An, An (new)]
E01 -> [Binh, Binh (new)]
E03 -> [Chi]
~~~

**Step-by-step explanation:**

1. Two instances with **id = "E02"** return true when compared with **equals**, while also having the same **hashCode**. They become **one logical key** in the map.
2. For the first employee of a group, **computeIfAbsent** creates a new ArrayList. For a later employee with the same id, it returns the existing list and appends the new element.
3. **List<Employee>** stores **each occurrence**, so group E02 contains both objects without losing the "An (new)" record.
4. **LinkedHashMap** preserves key order by **first insertion**: E02, then E01, then E03. Each list preserves the order in which elements were added.
5. The representative key object of a group is the first inserted one. Therefore, do not arbitrarily assume the representative key is the newest record or the "canonical" record; if you need to select a representative record by timestamp/version, handle that rule separately.

**Why implement Employee this way?** The class is declared **final** so no symmetry issues arise from a subclass adding equality criteria; **id** is **final** and non-null for stable identity. The name participates in neither method. Depending on the business domain, a composite key (such as tenantId + employeeId) may be needed to avoid treating identical IDs across two tenants as one.

### Stream Variant

With the **input** list and **Employee** class in the example above, the loop can be replaced with:

~~~java
Map<Employee, List<Employee>> groups = input.stream().collect(
    Collectors.groupingBy(
        employee -> employee,
        LinkedHashMap::new,
        Collectors.toList()
    )
);
~~~

This is a **replacement snippet inside main**, not a standalone Java program. **groupingBy** uses the element itself as the key, so it still relies on Employee's **equals/hashCode**. Passing **LinkedHashMap::new** is intentional to preserve the appearance order of groups when running a sequential stream; the single-argument **Collectors.groupingBy** makes no guarantee about the specific map type or key iteration order. The resulting lists still contain all elements in each group.

## 4. Complete Example: Grouping by Value Key Instead of Altering the Object's equals

Suppose **Customer** is a complete record, yet a report must group by **(tenantId, customerCode)**. The report's business rule explicitly states that leading/trailing whitespace and letter casing in **customerCode** are not significant. We create **CustomerKey** containing only the two normalized key components, while Customer keeps its full record value definition.

Create the file **GroupByBusinessKeyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class GroupByBusinessKeyDemo {
    record Customer(String tenantId, String customerCode, String displayName) {}

    record CustomerKey(String tenantId, String normalizedCode) {}

    public static void main(String[] args) {
        List<Customer> input = List.of(
            new Customer("A", " c123 ", "Lan"),
            new Customer("B", "C123", "Ha"),
            new Customer("A", "C123", "Lan (new)"),
            new Customer("A", "x7", "Minh")
        );

        Map<CustomerKey, List<Customer>> groups = new LinkedHashMap<>();

        for (Customer customer : input) {
            String normalized = customer.customerCode()
                .strip()
                .toUpperCase(Locale.ROOT);
            CustomerKey key = new CustomerKey(customer.tenantId(), normalized);

            groups.computeIfAbsent(key, ignored -> new ArrayList<>())
                  .add(customer);
        }

        for (Map.Entry<CustomerKey, List<Customer>> entry : groups.entrySet()) {
            CustomerKey key = entry.getKey();
            System.out.printf("%s/%s -> %d%n",
                key.tenantId(), key.normalizedCode(), entry.getValue().size());
        }
    }
}
~~~

Run:

~~~bash
javac GroupByBusinessKeyDemo.java
java GroupByBusinessKeyDemo
~~~

Output:

~~~text
A/C123 -> 2
B/C123 -> 1
A/X7 -> 1
~~~

**Explanation:** Two Customers of tenant A have differently formatted codes that become the same **CustomerKey("A", "C123")** after normalization; the tenant B customer remains in a separate group. **record** automatically provides equals/hashCode based on **all components**, making composite keys more concise and less error-prone than writing them manually. Normalization is valid only when the domain permits it; do not change casing by default for all codes, emails, names, or identifiers.

Do not create a record containing mutable fields and then use that entire record as a grouping key if the goal is only to group by ID. **record Customer** above has equals across tenantId, customerCode, and displayName, so grouping by Customer itself will yield a different result than grouping by CustomerKey.

## 5. Result Representations and Their Suitability

**Map<K, List<T>>** is the most convenient representation for retaining all members in each group: the key represents one logical value and the list holds equivalent elements. Use **LinkedHashMap** if you want groups iterated in appearance order, **HashMap** if order does not matter, or another structure when requirements differ.

Other variants serve other goals:

- **Set<T>** (such as **LinkedHashSet**) retains only one representative element per logical value, useful for deduplication. It **does not preserve the full list** of group members.
- **Map<K, Long>** or **Map<K, Integer>** counts frequencies per key value, without keeping the member objects.
- **List<List<T>>** keeps each group without needing a map key object; it can be built by comparing elements against each group's representative. This linear scan typically costs **O(n²)** comparisons in the worst case, whereas grouping with a hash map is usually near **O(n)** on average when hashes distribute well.
- **TreeMap** or **TreeSet** determines duplicate keys using **Comparator.compare(a, b) == 0** or **compareTo(a, b) == 0**, not directly via equals. If the comparator is inconsistent with equals, grouping results can differ from grouping under the equals contract. Use only when that is specifically the desired rule.

If choosing **Map<K, List<T>>**, decide clearly whether the output must preserve **input order**, **sorted key order**, or whether order is unimportant. Two objects being equal does not by itself imply any specific order.

## 6. Common Mistakes and Why Grouping Fails

### 6.1. Overriding equals Without hashCode

~~~java
@Override
public boolean equals(Object obj) {
    // Comparison logic by id
    // (illustrates a design flaw only, not a standalone program)
}
~~~

This is an **illustration using comments**, not a compilable method: if a class overrides equals by id while leaving hashCode inherited from Object, two equal objects can have different hash codes. **HashMap/HashSet** may store them in different slots and produce **two erroneous groups**. Always override **equals** and **hashCode** together, using the same set of identifying properties.

### 6.2. Using == to Check Object Values

Two independent objects **new Employee("E02", ...)** typically have distinct references. **==** returns false for those two references even when equals returns true. With String and wrapper types, caching/interning makes == appear to "sometimes work", so you must always use the comparison matching the intended semantics.

### 6.3. Using Mutable Fields as Hash Keys

If id (or a component participating in hashCode) changes **after** inserting the object into a HashMap, the entry stays in the slot organized under the old hash; subsequent lookups/groupings may fail or become inconsistent. Prefer **immutable keys** (record keys, immutable String IDs, final fields); if an identifier must change, rebuild the map with the new key.

### 6.4. Relying Solely on hashCode to Conclude Equality

**a.hashCode() == b.hashCode()** is not sufficient to prove **a.equals(b)**. Hash collisions happen validly, and HashMap still calls equals to distinguish keys sharing a hash.

### 6.5. Confusing equals with compareTo / Comparator

~~~java
new java.math.BigDecimal("1.0").equals(
    new java.math.BigDecimal("1.00"))  // false
~~~

With BigDecimal, **compareTo** returns 0 between these two values yet **equals** returns false because their scales differ. Therefore, grouping with **HashMap<BigDecimal, ...>** may separate them; grouping with **TreeMap** under natural ordering may merge them. If the domain considers only numeric value, decide on and represent a consistently normalized key, such as considering **stripTrailingZeros()** along with zero handling and data domain bounds.

### 6.6. Confusing Array equals with Element-Wise equals

Arrays do not override Object.equals to compare contents: **new int[]{1,2}.equals(new int[]{1,2})** is false. If a key is an array, comparing values element-wise requires **Arrays.equals** (1D arrays) or **Arrays.deepEquals** (nested arrays), along with building a key that has a compatible **hashCode** (Arrays.hashCode/deepHashCode). Another convenient approach is converting to an appropriate immutable value structure.

### 6.7. Using a "Nearly Equal" Relation That Is Not Transitive

For example, the rule **|a - b| < 2** for numbers 1, 2, 3: 1 is near 2 and 2 is near 3, yet 1 is not near 3. This is not an equivalence relation; it should not be placed directly into **equals** to partition into equivalence classes. Distance/proximity clustering problems must use separate clustering algorithms and grouping rules.

### 6.8. Pitfalls with null, Entities, and Inheritance

- **a.equals(null)** must be false; if `a` can be null, never call **a.equals(...)** directly. You can use **Objects.equals(a, b)** for null-safe comparison. **List.of** disallows null elements; the JDK's **Collectors.groupingBy** rejects null grouping keys. If data can contain null, establish a policy to filter them out, separate them, or use a meaningful sentinel.
- Entities whose ID is generated upon persistence (for example, unpersisted entities) should not automatically treat all null IDs as the same value: multiple new entities can be distinct entities. Design equals/hashCode to fit the identity lifecycle.
- Comparing between a superclass and a subclass that adds state easily breaks symmetry or transitivity; consider `final` classes, `record`s, or a tightly designed inheritance rule.

## 7. Verifying the Contract Before Trusting Grouping Results

For each sample **a, b, c**, test with concrete examples:

1. **a.equals(a)** is true; **a.equals(null)** is false.
2. **a.equals(b)** equals **b.equals(a)**.
3. If **a.equals(b)** and **b.equals(c)** are both true, then **a.equals(c)** is also true.
4. If **a.equals(b)** is true, **a.hashCode() == b.hashCode()** must also be true.
5. If **a** and **b** are considered different values, grouping creates two separate groups when needed; if equal, they must end up in the same group.
6. Adding duplicate elements or shuffling input order must not alter **same-group membership**; when using LinkedHashMap, group display order may change according to first-appearance order.
7. The total number of **elements across all group lists** must equal the number of input elements retained after any filtering policy; the number of groups must equal the number of distinct key values.

You can also test three instances with the same logical key, keys with hash collisions, keys across two different tenants, null, and normalized values. In automated tests, use clear assertions or an equals/hashCode verification library if the project already includes one. A few passing examples do not fully prove the contract for all inputs, but they help catch many common design mistakes.

## 8. Process for Applying to Real Data

1. **Write down the exact definition of "same value"** for the business case: same ID, same tenant + ID combination, or full value match.
2. **Choose the key:** use the object itself if the class's equals fits; otherwise, extract a dedicated immutable key. Ensure the key's equals/hashCode obey the contract.
3. **Normalize intentionally**, before grouping and only for business differences meant to be ignored (such as surrounding whitespace or casing).
4. **Choose the result shape:** member lists, occurrence counts, or only the set of unique values; pick a map/set structure matching ordering requirements.
5. **Perform grouping and verify:** each element goes into exactly one group; no elements lost, no distinct keys merged by mistake; specifically verify null keys and mutable keys.
6. **Keep the contract stable while keys are in use:** do not mutate identifying key fields while stored in the map.

**Key takeaway:** the ability to partition objects into same-value groups rests on **a valid equivalence relation**. In hash structures, **equals determines equality** and **hashCode must be consistent with equals**. When grouping is needed by only part of the data, design a **separate value key** instead of distorting the meaning of the original object's equals.