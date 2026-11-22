# Do Not Include Data in `hashCode()` That Distinguishes Objects Considered Equal

When implementing `hashCode()`, start from **the definition of equality in `equals(Object)`**. If two objects are considered equal by `equals()`, they **must** return the same hash code, even when their other attributes differ.

The core rule:

> If `a.equals(b) == true`, then `a.hashCode() == b.hashCode()` must hold.

This is a one-way requirement. Two **unequal** objects can still share the same hash code; Java allows *hash collisions*. The mistake is including in `hashCode()` an attribute—such as a display name, notes, or an update timestamp—that can **differ between objects for which `equals()` still returns `true`**. When that happens, `HashSet` and `HashMap` may fail to recognize logically duplicate objects.

## 1. Start from the Object's Equality Relation

Suppose a customer management application has:

- `customerId`: the customer's stable identifier.
- `displayName`: the name used for display, which can be edited.

Business requirement: **two `Customer` objects with the same `customerId` represent the same customer**, even if their display names differ because the information was synchronized at different times. Therefore:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return customerId.equals(other.customerId);
}
~~~

This is an **illustrative code snippet** inside the `Customer` class. The comparison relies solely on `customerId`. If object A has ID `"C-01"` and name `"An"`, and object B has the same ID `"C-01"` and name `"Binh"`, then `A.equals(B)` must be `true`.

A matching `hashCode()` is:

~~~java
@Override
public int hashCode() {
    return customerId.hashCode();
}
~~~

Because the same `customerId` yields the same `customerId.hashCode()`, any two objects considered equal by `equals()` are guaranteed to receive the same hash code.

Do not arbitrarily add `displayName` into the hash code:

~~~java
@Override
public int hashCode() {
    return Objects.hash(customerId, displayName); // WRONG with an equals() that compares only ID.
}
~~~

`Objects.hash(...)` is a valid API; **the bug is in the choice of attributes**, not in the API. Two objects with the same ID but different names can get two different hash codes, violating the mandatory contract.

### Thinking in Terms of Equivalence Classes

If `equals()` treats every object with ID `"C-01"` as equal, we have an **equivalence class** made up of multiple instances of the same customer. The `hashCode()` function must produce the **same result for every member of that class**. It may map several distinct classes to the same integer, but it **must never split one equivalence class into multiple hash codes**.

In other words, all data affecting the hash code must satisfy this condition: whenever `equals(a, b)` is `true`, the data used must produce **identical hash results**. The easiest approach to keep under control is hashing the same equality key that `equals()` uses.

## 2. Java 17 Example: Right and Wrong in One Program

Create the file **`HashCodeEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class HashCodeEqualityDemo {

    // RIGHT: identifies a customer by customerId.
    static final class Customer {
        private final String customerId;
        private String displayName;

        Customer(String customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId);
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String newName) {
            displayName = Objects.requireNonNull(newName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Customer other)) {
                return false;
            }
            return customerId.equals(other.customerId);
        }

        @Override
        public int hashCode() {
            return customerId.hashCode();
        }
    }

    // WRONG: equals() uses only ID, but hashCode() also uses the name.
    static final class BrokenCustomer {
        private final String customerId;
        private final String displayName;

        BrokenCustomer(String customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BrokenCustomer other)) {
                return false;
            }
            return customerId.equals(other.customerId);
        }

        @Override
        public int hashCode() {
            return 31 * customerId.hashCode() + displayName.hashCode();
        }
    }

    public static void main(String[] args) {
        Customer first = new Customer("C-01", "An");
        Customer sameId = new Customer("C-01", "Binh");

        System.out.println("GOOD equals: " + first.equals(sameId));
        System.out.println("GOOD same hash: "
                + (first.hashCode() == sameId.hashCode()));

        Set<Customer> goodSet = new HashSet<>();
        goodSet.add(first);
        System.out.println("GOOD contains same ID: " + goodSet.contains(sameId));

        first.rename("An new");
        System.out.println("GOOD contains after rename: "
                + goodSet.contains(first));

        BrokenCustomer badFirst = new BrokenCustomer("C-01", "An");
        BrokenCustomer badSameId = new BrokenCustomer("C-01", "Binh");

        System.out.println("BAD equals: " + badFirst.equals(badSameId));
        System.out.println("BAD same hash: "
                + (badFirst.hashCode() == badSameId.hashCode()));

        Set<BrokenCustomer> badSet = new HashSet<>();
        badSet.add(badFirst);
        System.out.println("BAD contains same ID: "
                + badSet.contains(badSameId));

        badSet.add(badSameId);
        System.out.println("BAD set size: " + badSet.size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac HashCodeEqualityDemo.java
java HashCodeEqualityDemo
~~~

**Output:**

~~~text
GOOD equals: true
GOOD same hash: true
GOOD contains same ID: true
GOOD contains after rename: true
BAD equals: true
BAD same hash: false
BAD contains same ID: false
BAD set size: 2
~~~

**Reading the output:**

1. `first` and `sameId` have the same `customerId`, so `equals()` is `true`, even though their display names differ.
2. `Customer.hashCode()` depends only on the ID, so the two hash values are guaranteed to match. `HashSet.contains(sameId)` finds the customer that was added.
3. Changing `first`'s display name **does not change** `hashCode()` or `equals()` under the ID definition; looking up that same element in `HashSet` continues to work.
4. The two `BrokenCustomer` instances are still considered equal by `equals()`, yet the hash formula that adds the name produces different results for `"An"` and `"Binh"`. In this example, `HashSet` fails to find the object with the same ID and ends up storing two objects that `equals()` considers equal.

The broken example uses `31 * id.hashCode() + displayName.hashCode()` to clearly show the dependency on the name; it is not a recommendation for custom hashing. The exact hash integer is not what matters; **two equal objects returning different hashes** is the violation.

## 3. Why Are `HashSet` and `HashMap` Affected?

Hash-based collections organize lookups into two conceptual layers:

1. They use the value from `hashCode()` to determine where to look in the data structure.
2. Within the matching search region, they use `equals()` to decide whether it is the same logical key or element.

If `a.equals(b)` is `true` yet the two hashes differ, searching for `b` can look in a different slot from where `a` is stored, causing `contains`, `get`, or deduplication to behave unexpectedly. There is no guarantee that `equals()` will "rescue" an invalid hash code; the collection is under no obligation to scan every element to make up for a broken contract.

The example above intentionally chooses names that give the two objects different hashes so `HashSet` exhibits the failure. In another program, bucket placement and observed behavior may depend on the hash values or collection implementation, but **the contract violation itself is still a bug in the class**, even if a single run happens to pass by coincidence.

Additional note: once an object is placed in a `HashSet` or used as a `HashMap` key, **do not mutate any data that participates in `equals()`/`hashCode()`** while it remains in that structure. The good example makes `customerId` `final` with no setter. Changing only `displayName`—which is ignored by both methods—does not trigger this bug.

## 4. Rules for Choosing Fields for `hashCode()`

| Data or scenario | Should it participate in the hash code? | Why? |
| --- | --- | --- |
| `customerId` is the unique key compared by `equals()` | **Yes** | Same ID means the ID's hash is identical |
| `displayName` can differ between two customers treated as the same person | **No** | Can make hashes differ while `equals()` is `true` |
| `lastUpdated`, notes, UI state ignored by `equals()` | **No** | They can change independently of the equality relation |
| Value deterministically derived solely from the equality key | **Possible**, though usually unnecessary | Two equal objects always produce the same derived value |
| A field used by `equals()` that is omitted from the hash | **Can be valid** | Two equal objects still yield the same hash; may only increase collisions |
| A constant hash code like `return 1;` | **Contract-compliant but inefficient** | Every object collides, increasing collisions |

Thus, "use the exact fields from `equals()`" is a **safe practical rule of thumb**, not a strict requirement to hash every field compared by `equals()`. The real law is: **equal objects must have equal hash codes**. Omitting a distinguishing field only increases the chance of collisions; hashing a field that can vary between equal objects breaks the contract.

For example, if a `Person` is compared by both `countryCode` and `personalNumber`, hashing only `countryCode` is still valid, though prone to many collisions. Hashing both fields usually gives better distribution:

~~~java
@Override
public int hashCode() {
    return Objects.hash(countryCode, personalNumber);
}
~~~

This is an **illustrative snippet**, assuming `equals()` actually compares both values and both fields have consistent representations/comparisons. For `Customer` where `equals()` uses only ID, `Objects.hash(customerId, displayName)` is invalid.

## 5. Common Design Pitfalls

### A. Case-Insensitive Comparison

If `equals()` treats `"ab-1"` and `"AB-1"` as equal, while `hashCode()` hashes the raw string directly, the contract can be broken. You must use **the same normalized key form** in both methods—for example, converting an ASCII code restricted to `A–Z`, `a–z`, digits, and hyphens to lowercase with `Locale.ROOT` before storing it.

~~~java
import java.util.Locale;

// Illustrates normalizing the key before storing; input format already validated by the caller.
String canonicalId = rawId.toLowerCase(Locale.ROOT);
~~~

Then use `canonicalId.equals(...)` and `canonicalId.hashCode()`. For data with more complex Unicode or language-specific rules, you need an explicit, consistent normalization policy; lowercasing is just an example for a simple, controlled code domain. Avoid pairing `equalsIgnoreCase` in `equals()` with raw `String.hashCode()` in `hashCode()`.

### B. Arrays and Nested Objects

If `equals()` uses `Arrays.equals(bytesA, bytesB)` to compare **array contents**, do not use a hash based on **array identity**. Use the matching `Arrays.hashCode(bytes)`. Likewise, if `equals()` compares nested data fields by value, `hashCode()` must use a hash consistent with that equality.

For example, with a `byte[] payload` whose contents stay immutable during its lifetime as a key:

~~~java
@Override
public int hashCode() {
    return java.util.Arrays.hashCode(payload);
}
~~~

This is an isolated snippet, assuming `equals()` is based on `Arrays.equals(payload, other.payload)`. You should guard against external modification of the array, such as defensive copying in the constructor and getter.

### C. Derived Fields and Cached Data

A field that does not appear directly in `equals()` is **not automatically forbidden** in `hashCode()`. If it is deterministically derived from the equality fields and does not change when those fields do not change, using it can still be correct. However, pulling an uninitialized cache, a refresh timestamp, or a value that differs between two equal objects into the hash formula is dangerous.

Caching the **`hashCode()` result itself** is a separate matter: it can be valid for a truly immutable equality key with safe initialization. Do not use such caching as an excuse to ignore the contract or let equality keys mutate.

### D. Data Mutated After Insertion into a Collection

There are two independent bugs to distinguish:

- **Equality-relation bug:** two objects are equal, yet `hashCode()` depends on a field that differs between them.
- **Key-mutation bug:** an object has a field used in `equals()`/`hashCode()` modified after being placed into a `HashSet` or `HashMap`.

Even when `equals()` and `hashCode()` are written to match each other completely, mutating key fields while the object is actively used as a key can cause subsequent lookups to fail. The common solution is to use immutable keys and keep mutable display information outside the key.

## 6. Testing the Contract Effectively

Do not test only whether an object equals itself. For the `Customer` class, the key test cases are:

1. Create two objects with the **same ID, different display names**. Verify both `a.equals(b)` and `b.equals(a)` are `true`; `a.hashCode() == b.hashCode()` must also be `true`.
2. Create objects with **different IDs, same name**. `equals()` must be `false` under the ID definition. Their hash codes may be equal or different; do not assert that "different objects must have different hashes".
3. Insert `a` into a `HashSet`, then use `b` with the same ID to verify `contains(b)` is `true`.
4. If the display name can be edited, rename it and verify equality and hash remain unaffected, because the name is not part of the key.
5. Verify `equals(null) == false` and `equals` with a non-`Customer` object returns `false`.
6. With three objects sharing the same ID, verify reflexivity, symmetry, and transitivity of `equals()`. Then confirm equal hashes for every pair verified to be equal.

Do not write tests assuming every distinct ID produces a distinct hash code: in Java, `hashCode()` returns an `int`, so collisions are inevitable over a sufficiently large data domain. Test the **one-way invariant** and collection usage behavior instead.

## 7. How to Remember and Apply It

When preparing to override `hashCode()`, follow this sequence:

1. Define the **equality specification** first: which fields determine that two objects represent the same entity or logical value?
2. Ensure `equals(Object)` accurately reflects that definition and obeys reflexivity, symmetry, transitivity, consistency, and `null` handling.
3. Compute the hash code from keys/values that are **guaranteed to be identical whenever `equals()` is `true`**.
4. Exclude from the hash code fields meant only for display, notes, status, or metadata that may vary between objects already considered equal.
5. Prefer immutable keys for the entire duration an object serves as a collection key.
6. Write tests using **two distinct instances with the same logical value**, not just a single reference compared against itself.

**Remember:** `hashCode()` is not a way to list every attribute of an object. It must respect how `equals()` groups objects into equivalence classes. Hashing an extra field that can separate members of the same class is a bug; members of the same equivalence class must share the same hash code, while different classes are still allowed to collide.