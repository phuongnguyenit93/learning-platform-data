# Testing Lookup With Equal Objects in HashMap and HashSet

## 1. Learning Objectives

Suppose a system stores account state in a HashMap keyed by an organization ID and a user ID. Once stored with **new UserKey("team-a", 42)**, the system must be able to look it up using **another UserKey object with those exact same values**. Similarly, a HashSet must recognize two objects with distinct references yet equal logical keys as the same element.

The test does not stop at an isolated **map.get()** or **set.contains()**; it must prove the relationship among **identity**, **equals()**, **hashCode()**, lookup/update behavior, and uniqueness, while also confirming that different keys are not mistakenly matched.

Concepts to distinguish:

- **a == b:** two variables reference the exact same object.
- **a.equals(b):** two objects are considered equal according to the equality contract defined by the class.
- **a.hashCode():** an integer used for hash partitioning when organizing data. Two objects that are equal under equals() must return the same hashCode().
- **Logical key:** the business identity determined by the fields participating in equals/hashCode. Two separate objects can represent the same logical key.

A program that only inserts an object a and then looks it up again using **the same a** is a weak test: even a class inheriting Object's default equals/hashCode can pass it. Always construct **b** independently from a yet equal in value.

## 2. How Do HashMap and HashSet Recognize Equal Objects?

**HashMap<K, V>** uses the key's hash to locate the appropriate search bucket and compares keys via the equals relation to find the entry. After **put(a, "ACTIVE")**, **get(b)** and **containsKey(b)** can find the right entry if b equals a and satisfies the hash contract. When subsequently calling **put(b, "UPDATED")**, the Map must update that same logical key without creating a new entry.

**HashSet<E>** stores unique elements based on equality/hashing. After **add(a)**, **contains(b)** must return true and **add(b)** must return false if b equals a; the Set's size does not increase.

| Check | Expected result for equal-value, distinct-reference a and b |
| --- | --- |
| **a != b** | true |
| **a.equals(b)** and **b.equals(a)** | true |
| **a.hashCode() == b.hashCode()** | true |
| **map.put(a, v); map.get(b)** | v |
| **map.containsKey(b)** | true |
| **map.put(b, v2)** | updates value for the same logical key; Map still has 1 entry if initially empty |
| **set.add(a); set.contains(b)** | true for contains |
| **set.add(a); set.add(b)** | first add returns true, second returns false; Set still has 1 element |

Do not conclude two objects are equal merely because their hashes match: **collisions are permitted**. HashMap/HashSet must still distinguish two objects whose equals() returns false even if their hashCodes are equal.

## 3. The equals() and hashCode() Contract

**equals()** must satisfy these conditions, assuming relevant state does not change:

1. **Reflexive:** a.equals(a) is true.
2. **Symmetric:** a.equals(b) and b.equals(a) return the same result.
3. **Transitive:** if a equals b and b equals c, then a equals c.
4. **Consistent:** repeated comparisons on objects with unchanged state return the same result.
5. **Non-null:** a.equals(null) is false for non-null a.

**hashCode()** requires:

- Repeated calls on the same object with unchanged equality information during a single execution must return the same result.
- **If a.equals(b) == true then a.hashCode() == b.hashCode().**
- If a does not equal b, hashes may collide or differ; they are not required to be different.

If you override equals() to compare by fields without overriding a compatible hashCode(), two instances can have equals true yet different hash codes, causing lookup failures in HashMap/HashSet. Use the exact same components defining the logical key for both methods. For keys that must stay stable long-term in collections, choose immutable data; if a field participating in hashing is modified after insertion, the collection does not automatically re-index it under the new hash.

## 4. Standalone, Runnable Java 17+ Program

The UserKey class is declared **final**, and the **tenantId** and **userId** fields are also final. The equals() method compares both fields; hashCode() is computed from those same two fields. The code below tests with a new object having the same values, inserts into Map/Set, updates using an equivalent object, and rejects a different key.

Create the file **EqualKeyLookupDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualKeyLookupDemo {
    static final class UserKey {
        private final String tenantId;
        private final int userId;

        UserKey(String tenantId, int userId) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.userId = userId;
        }

        @Override
        public boolean equals(Object object) {
            if (this == object) {
                return true;
            }
            if (!(object instanceof UserKey other)) {
                return false;
            }
            return userId == other.userId
                    && tenantId.equals(other.tenantId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, userId);
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        UserKey first = new UserKey("team-a", 42);
        UserKey equivalent = new UserKey("team-a", 42);
        UserKey different = new UserKey("team-a", 43);

        System.out.println("Khác tham chiếu: "
                + (first != equivalent));
        System.out.println("Bằng nhau theo equals: "
                + first.equals(equivalent));
        System.out.println("Hash bằng nhau: "
                + (first.hashCode() == equivalent.hashCode()));

        require(first != equivalent, "Phải tạo hai instance khác nhau");
        require(first.equals(equivalent)
                        && equivalent.equals(first),
                "equals phải nhất quán hai chiều");
        require(first.hashCode() == equivalent.hashCode(),
                "Đối tượng bằng nhau phải cùng hash");

        Map<UserKey, String> map = new HashMap<>();
        map.put(first, "ACTIVE");

        System.out.println("Map tra bằng đối tượng khác: "
                + map.get(equivalent));
        System.out.println("Map containsKey: "
                + map.containsKey(equivalent));

        require("ACTIVE".equals(map.get(equivalent)),
                "Map không tìm được khóa bằng nhau");
        require(map.containsKey(equivalent),
                "Map không nhận ra khóa bằng nhau");

        String oldValue = map.put(equivalent, "UPDATED");
        System.out.println("Giá trị cũ khi put: " + oldValue);
        System.out.println("Số entry của Map: " + map.size());
        System.out.println("Giá trị bằng khóa ban đầu: "
                + map.get(first));

        require("ACTIVE".equals(oldValue), "Put không cập nhật đúng");
        require(map.size() == 1, "Map sinh khóa logic trùng");
        require("UPDATED".equals(map.get(first)),
                "Map không trả value đã cập nhật");

        Set<UserKey> set = new HashSet<>();
        boolean addedFirst = set.add(first);
        boolean addedAgain = set.add(equivalent);

        System.out.println("Set thêm ban đầu: " + addedFirst);
        System.out.println("Set thêm đối tượng bằng nhau: "
                + addedAgain);
        System.out.println("Set contains: "
                + set.contains(equivalent));
        System.out.println("Số phần tử của Set: " + set.size());

        require(addedFirst && !addedAgain,
                "Set phải ngăn phần tử bằng nhau");
        require(set.contains(equivalent) && set.size() == 1,
                "Set không tìm thấy phần tử tương đương");

        System.out.println("Map chứa khóa khác: "
                + map.containsKey(different));
        System.out.println("Set chứa khóa khác: "
                + set.contains(different));

        require(!map.containsKey(different), "Map nhầm khóa khác");
        require(!set.contains(different), "Set nhầm khóa khác");

        System.out.println("Tất cả kiểm thử thành công.");
    }
}
~~~

Compile and run commands for JDK 17 or later:

~~~bash
javac -encoding UTF-8 EqualKeyLookupDemo.java
java EqualKeyLookupDemo
~~~

**Exact expected stdout:**

~~~text
Khác tham chiếu: true
Bằng nhau theo equals: true
Hash bằng nhau: true
Map tra bằng đối tượng khác: ACTIVE
Map containsKey: true
Giá trị cũ khi put: ACTIVE
Số entry của Map: 1
Giá trị bằng khóa ban đầu: UPDATED
Set thêm ban đầu: true
Set thêm đối tượng bằng nhau: false
Set contains: true
Số phần tử của Set: 1
Map chứa khóa khác: false
Set chứa khóa khác: false
Tất cả kiểm thử thành công.
~~~

Explanation: **first** and **equivalent** have different identities, yet are equal across the exact two key fields. HashMap looks up using equivalent, updates using equivalent while keeping exactly one entry, and reading via first sees the updated value; HashSet recognizes the equivalent value and does not add a duplicate. **different** does not equal first because userId differs. The **require(...)** helper throws AssertionError immediately when a condition is not met, unlike Java's **assert** statement which can be disabled when the **-ea** flag is omitted.

The test does not print the entire HashMap/HashSet to assert element order because **there is no guaranteed iteration order** for these two collections.

## 5. Writing JUnit Jupiter (JUnit 5) Tests

In real applications, use assertions with clear messages. The snippet below is **supplementary test code**, requiring the JUnit 5 dependency and the EqualKeyLookupDemo class in the same package, not a standalone program run solely with the java command.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class EqualKeyLookupDemoTest {

    @Test
    void equalDistinctKeysFindOneMapEntry() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var b = new EqualKeyLookupDemo.UserKey("team-a", 42);

        assertNotSame(a, b);
        assertEquals(a, b);
        assertEquals(b, a);
        assertEquals(a.hashCode(), b.hashCode());

        Map<EqualKeyLookupDemo.UserKey, String> map = new HashMap<>();
        map.put(a, "ACTIVE");

        assertTrue(map.containsKey(b));
        assertEquals("ACTIVE", map.get(b));
        assertEquals("ACTIVE", map.put(b, "UPDATED"));
        assertEquals(1, map.size());
        assertEquals("UPDATED", map.get(a));
    }

    @Test
    void equalDistinctElementsCountOnceInSet() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var b = new EqualKeyLookupDemo.UserKey("team-a", 42);

        Set<EqualKeyLookupDemo.UserKey> set = new HashSet<>();
        assertTrue(set.add(a));
        assertTrue(set.contains(b));
        assertFalse(set.add(b));
        assertEquals(1, set.size());
    }

    @Test
    void differentKeysDoNotMatch() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var otherId = new EqualKeyLookupDemo.UserKey("team-a", 43);
        var otherTenant = new EqualKeyLookupDemo.UserKey("team-b", 42);

        assertNotEquals(a, otherId);
        assertNotEquals(a, otherTenant);
        assertNotEquals(a, null);

        Map<EqualKeyLookupDemo.UserKey, String> map = new HashMap<>();
        map.put(a, "ACTIVE");
        assertFalse(map.containsKey(otherId));
        assertFalse(map.containsKey(otherTenant));

        Set<EqualKeyLookupDemo.UserKey> set = new HashSet<>();
        set.add(a);
        assertFalse(set.contains(otherId));
        assertFalse(set.contains(otherTenant));
    }

    @Test
    void equalityContract() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var b = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var c = new EqualKeyLookupDemo.UserKey("team-a", 42);

        assertEquals(a, a);
        assertEquals(a, b);
        assertEquals(b, a);
        assertEquals(b, c);
        assertEquals(a, c);
        assertEquals(a.hashCode(), b.hashCode());
        assertEquals(b.hashCode(), c.hashCode());
    }
}
~~~

When writing dedicated tests for a project class, replace UserKey with your actual key. If a key consists of multiple fields, test at least one case **differing in each field participating in equality**; otherwise, an overly broad equals() may mistakenly treat two different keys as the same key.

## 6. Distinguishing Collisions From Equality

Two objects that are **unequal yet have the same hashCode** must still be stored and looked up independently by HashMap/HashSet. You can intentionally create a collision using a class whose hashCode() always returns 1. This **still satisfies the contract** (equal keys definitely have the same hash), though it performs severely poorly on large sets.

Supplementary illustrative example, assuming imports for **java.util.Map** and **java.util.HashMap**:

~~~java
record CollisionKey(int id) {
    @Override
    public int hashCode() {
        return 1;
    }
}

Map<CollisionKey, String> map = new HashMap<>();
map.put(new CollisionKey(1), "ONE");
map.put(new CollisionKey(2), "TWO");

// Two keys have colliding hashes yet unequal equals.
if (!"ONE".equals(map.get(new CollisionKey(1)))
        || !"TWO".equals(map.get(new CollisionKey(2)))
        || map.size() != 2) {
    throw new AssertionError("Hash collision bị xử lý sai");
}
~~~

This illustrative snippet is not a standalone Java file: place the record and statements in an appropriate declaration context, such as the record at class level and the statements inside a test method. A collision does not prove an equals/hashCode bug. **Do not use a constant hash in production applications** merely to simplify hash computation.

## 7. Common Failure Scenarios

### 7.1. Overriding equals() While Forgetting hashCode()

Suppose a class only overrides equals() to compare tenantId and userId while letting hashCode() inherit from Object. Two distinct instances can have equals true yet different hashCodes, causing HashMap/HashSet to search the wrong bucket and return unexpected results.

**Do not intentionally write tests that always expect lookup failure** for this kind of broken class, because identity hashes can collide by chance; failure is not guaranteed across every run. Tests must directly assert **a.equals(b) ⇒ a.hashCode()==b.hashCode()** alongside lookup behavior.

### 7.2. Using == to Compare Strings in equals()

**tenantId == other.tenantId** compares references, whereas two distinct String objects can contain the same text. Use **tenantId.equals(other.tenantId)** when guaranteed non-null; use **Objects.equals(...)** when null support is required.

### 7.3. Misaligned Equality and Hash Criteria

If equals() treats two keys with the same userId as equal regardless of tenantId, while hashCode() includes tenantId in its calculation, two keys deemed equal by equals may have different hashes: a contract bug. Conversely, if hashCode() only uses userId while equals() uses both tenantId and userId, the contract can remain valid, though it tends to produce more collisions.

### 7.4. Mutating a Key After Insertion

If equals/hashCode depends on a mutable **code** field, **map.put(key, value)** stores the entry under the initial hash. After **key.code = "new-code"**, calling **map.containsKey(key)** even with the exact same old reference **can still fail** because the collection does not move the entry to the new hash bucket. HashSet faces the exact same risk.

Prefer **final fields with immutable components**, or a record containing only safe components. If a key truly must change, manage removing the key under its old state and inserting the new key in a controlled manner; avoid letting external objects directly mutate data serving as a key.

### 7.5. Asymmetric equals() Between Parent and Subclass

A parent class might consider itself equal to a subclass instance, whereas the subclass requires an extra field and does not consider itself equal to the parent. When **a.equals(b) != b.equals(a)**, the contract is broken and collection lookup can depend on comparison direction. For value key types, a **final class** or **record** usually helps express equality cleanly. If inheritance is needed, test symmetry and transitivity across all related types.

### 7.6. Using map.get() == null to Conclude a Key Does Not Exist

**HashMap permits null values**: a key b may exist, with **map.containsKey(b)==true**, while **map.get(b)==null**. If the use case needs to distinguish an absent key from a key mapped to null, check **containsKey**. HashSet.contains directly returns a boolean.

### 7.7. Testing With Only One Instance

Inserting a and then calling get(a) does not prove lookup by an equivalent key. A test must construct b with a distinct identity, assert they are equal, and look up using b. Checking only for matching hashes is also insufficient to prove equality.

### 7.8. Confusing record With Deep Immutability

A **record** auto-generates equals/hashCode from its components, yet a component can be a List, array, or mutable object. If a component has mutable state and participates in hashCode, the record key can still lose stability. Simple records with Strings and primitives are safer; with mutable components, a defensive copy and suitable equality contract are needed.

## 8. Matrix of Important Test Cases

| Case | Data | Result to prove |
| --- | --- | --- |
| Positive equality | Two distinct instances, all key fields identical | Map get/containsKey and Set contains find the entry |
| Duplicate logical key put/update | put(a), then put(b) | Map has only one entry and holds the new value |
| Duplicate element add | add(a), then add(b) | add(b) returns false and size does not grow |
| Negative by user ID | Same tenant, different userId | Does not match |
| Negative by organization | Same userId, different tenant | Does not match |
| Reflexive/symmetric/transitive | Create equal a, b, c | All equals properties hold |
| Hash contract | a.equals(b) is true | hashCode(a)==hashCode(b) |
| Collision | Two distinct keys, intentionally identical hash | Collection still distinguishes them |
| Null value in Map | put(a, null) | containsKey(b) is true even though get(b) is null |
| Mutable key | Hash field mutates after insertion | Identify risk and fix key design |
| Inheritance / proxy | Related key types per design | Does not break symmetry/transitivity |
| Multiple elements | Insert multiple duplicate and non-duplicate keys | Counts and values are accurate; do not rely on order |

**Do not assert that hashCodes of distinct objects must differ** or that Map/Set always have a specific iteration order. Those expectations lie outside the Java contract.

## 9. Using record to Represent Value Keys

With Java 17+, a record is concise when its components are the exact information identifying the logical key. The example below is an **illustrative code snippet**, requiring corresponding Map and HashMap imports and placing the statements inside a method:

~~~java
record UserKey(String tenantId, int userId) {}

UserKey first = new UserKey("team-a", 42);
UserKey equivalent = new UserKey("team-a", 42);
Map<UserKey, String> map = new HashMap<>();
map.put(first, "ACTIVE");

// map.get(equivalent) returns "ACTIVE".
// map.containsKey(equivalent) returns true.
~~~

A record automatically provides equals/hashCode across its components; you must still check that **all components** genuinely belong to the logical key. If a field is only descriptive metadata that should not participate in equality, define a separate key type containing only the required fields rather than using a record that includes descriptive fields. Declaring a record does not guarantee the objects referenced by its components are deeply immutable.

## 10. PASS Evaluation Checklist

A test suite should conclude PASS for the lookup contract when:

- Two **separate objects** with identical key content are proven to have different identities yet are equal in both directions of equals().
- equals() is reflexive, symmetric, transitive, consistent, and returns false for null; equal objects share the same hashCode().
- A Map that stored a still finds it using b, updating via b does not increase the logical key count, and reading via a sees the new value.
- A Set containing a still finds it using b; adding b does not increase element count.
- Unequal keys are not confused, even when hashes collide.
- No mutable field alters a key's meaning/hash after insertion; if state is shared, the design handles it according to contract.
- Assertions actually execute; results do not depend on HashMap/HashSet iteration order or lucky identity hashes.

**Conclusion:** the decisive check is **inserting one instance into HashMap/HashSet and looking it up with another instance that is equal under equals() and has a compatible hashCode()**. Combine that check with update/deduplication, negative cases, collisions, and key stability to properly verify the object contract in Java applications.
