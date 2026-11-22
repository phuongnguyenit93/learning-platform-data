# Implementing `equals()` with Multiple Fields According to the Chosen Equality Definition

## 1. Focus: Choose the Right Fields Before Writing Code

When implementing `equals(Object)` for a Java class, the first question is **not** “how many fields does this class have?” but rather: **“According to the problem domain's rules, when are two instances considered equal?”** From that answer, you determine the set of fields to combine in the comparison.

An object can contain many kinds of data:

- **Identity fields:** form the key identifying an entity (for example, `tenantId` and `memberNumber` combined).
- **Core value fields:** determine the value of a value object (for example, `currency` and `amount` of a monetary sum).
- **Descriptive or status fields:** display name, update timestamp, processing status, login count; these may not belong to the equality definition.
- **Computed/auxiliary fields:** caches, counters, loggers, derived data; normally do not participate in equality if they carry no comparison meaning.

**There is no rule to always include every field in `equals()`.** For a *value object*, all meaningful components are usually compared; for an *entity*, stable identity is usually compared, which may be one field or a combination of fields. Two objects with the same name or status are not necessarily the same entity; two representations of the same ID may have different statuses.

For example: in a multi-tenant enterprise system, the member code `"M-17"` is only unique **within each tenant**. If the enterprise also specifies that the same code can appear in multiple regions and the region is part of the immutable identity, the identification key must consist of **`(tenantId, memberNumber, region)`**. Comparing only `memberNumber` would mistakenly merge non-equivalent members. If in another design `region` is merely a changeable place of residence, that field *must not* be put into the equality key; the definition of that domain must be used.

## 2. The Contract of `equals()` and `hashCode()`

The `Object` class defines `equals(Object)`. The default implementation checks reference identity; overriding allows replacing it with equality meaningful to the application. Whether comparing one or multiple fields, `equals()` must satisfy:

| Property | Requirement |
| --- | --- |
| Reflexive | For a non-`null` object `x`, `x.equals(x)` is `true` |
| Symmetric | `x.equals(y)` and `y.equals(x)` must return the same result |
| Transitive | If both `x.equals(y)` and `y.equals(z)` are `true`, then `x.equals(z)` must be `true` |
| Consistent | When the data used for comparison does not change, consecutive calls yield the same result |
| Against `null` | `x.equals(null)` is always `false` if `x` is non-`null` |

The mandatory rule of `hashCode()`: **if `x.equals(y) == true`, then `x.hashCode() == y.hashCode()`**. Equal hashes do not imply two objects are equal because collisions can occur.

Consequence when choosing multiple fields: if `equals()` uses `a`, `b`, `c`, then `hashCode()` must also be based on those exact equality-defining components with consistent value handling. If `equals()` ignores `displayName`, then `hashCode()` must not include `displayName`. Do not use `System.identityHashCode()` as a hash for value-based object equality.

## 3. Recipe for Safely Combining Multiple Fields

A typical implementation pattern for a `final` class with reference fields:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Example that)) return false;

    return Objects.equals(fieldA, that.fieldA)
        && Objects.equals(fieldB, that.fieldB)
        && Objects.equals(fieldC, that.fieldC);
}

@Override
public int hashCode() {
    return Objects.hash(fieldA, fieldB, fieldC);
}
```

This is an **illustrative code snippet**, which must be placed in an actual `Example` class with `import java.util.Objects`. The condition `instanceof Example that` uses pattern matching available since Java 16; Java 17 runs it.

Role of each part:

1. `this == other` is a valid optimization: the same instance is always equal to itself.
2. The type check eliminates `null` and objects not belonging to the appropriate type; with a `final` class, no subclasses arise to break the comparison rule.
3. The `&&` operator requires **all** selected components to satisfy the comparison together. If just one field differs, the two objects are not equal.
4. `Objects.equals(a, b)` handles `null` safely: both `null` yields `true`; one `null` yields `false`; two non-`null` values use `a.equals(b)`.
5. `Objects.hash(a, b, c)` aggregates the hash of multiple fields in order. Calls with the same tuple of values have consistent hashes; differing order can change the hash, so a stable order must be kept in code.

**Choose the comparison per field type:** `==` for primitives `int`/`boolean`; `Objects.equals` or `.equals` for references with value semantics; `Arrays.equals`/`Arrays.deepEquals` for arrays depending on structure. Do not use `==` to compare two strings or wrapper objects when the goal is content. For `double` and `float`, consider `Double.compare`/`Float.compare` along with the corresponding hash function to handle NaN and signed zeros consistently.

## 4. Complete Java 17 Example: Three-Field Membership Key

Assume the following business rules:

- A member is identified by the **tuple tenant + member number + region**. In this example all three are stable identity components; `region` is allowed to be `null` and `null` is a valid distinct value in the illustrative model.
- `displayName` is only a display attribute, can change, and **does not** participate in equality.
- Each identity part is compared verbatim, case-sensitively; cases needing case-insensitivity must have a separate data normalization rule applied uniformly everywhere.

Save to the file **`MultiFieldEqualsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MultiFieldEqualsDemo {
    static final class Membership {
        private final String tenantId;
        private final String memberNumber;
        private final String region; // Allowed to be null in the example
        private String displayName;  // Mutable, does not participate in equals

        Membership(String tenantId, String memberNumber,
                   String region, String displayName) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            this.memberNumber = Objects.requireNonNull(memberNumber, "memberNumber");
            this.region = region;
            this.displayName = displayName;
        }

        void setDisplayName(String newDisplayName) {
            this.displayName = newDisplayName;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Membership that)) {
                return false;
            }
            return tenantId.equals(that.tenantId)
                && memberNumber.equals(that.memberNumber)
                && Objects.equals(region, that.region);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, memberNumber, region);
        }
    }

    record Coordinate(int x, int y) {}

    public static void main(String[] args) {
        Membership a = new Membership("ACME", "M-17", "VN", "An");
        Membership b = new Membership("ACME", "M-17", "VN", "Nguyen An");
        Membership c = new Membership("ACME", "M-17", "SG", "An");
        Membership d = new Membership("BETA", "M-17", "VN", "An");
        Membership e = new Membership("ACME", "M-17", null, "An");
        Membership f = new Membership("ACME", "M-17", null, "Khac");

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.equals(c): " + a.equals(c));
        System.out.println("a.equals(d): " + a.equals(d));
        System.out.println("e.equals(f): " + e.equals(f));
        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("hash(a) == hash(b): " + (a.hashCode() == b.hashCode()));

        Set<Membership> members = new HashSet<>();
        members.add(a);
        members.add(b);
        members.add(c);
        members.add(d);
        members.add(e);
        members.add(f);
        System.out.println("HashSet size: " + members.size());

        a.setDisplayName("An moi");
        System.out.println("Contains a after rename: " + members.contains(a));
        System.out.println("Contains same identity: " + members.contains(
            new Membership("ACME", "M-17", "VN", "Ten khac")));

        Coordinate p = new Coordinate(2, 5);
        Coordinate q = new Coordinate(2, 5);
        Coordinate r = new Coordinate(2, 6);
        System.out.println("record p.equals(q): " + p.equals(q));
        System.out.println("record p.equals(r): " + p.equals(r));
    }
}
```

Compile and run using **JDK 17 or higher** in the directory containing the file:

```bash
javac MultiFieldEqualsDemo.java
java MultiFieldEqualsDemo
```

Expected output:

```text
a == b: false
a.equals(b): true
a.equals(c): false
a.equals(d): false
e.equals(f): true
a.equals(null): false
hash(a) == hash(b): true
HashSet size: 4
Contains a after rename: true
Contains same identity: true
record p.equals(q): true
record p.equals(r): false
```

**Output analysis:**

- `a` and `b` are **two instances** so `a == b` is `false`; yet all three identity components are identical, so `a.equals(b)` is `true`, even though the display names differ.
- `c` differs only in `region` and `d` differs only in `tenantId`, and they still must be two entities distinct from `a`. This is why all fields according to the chosen definition must be combined.
- `e` and `f` share `region == null`; `Objects.equals(null, null)` returns `true`. `region == null` is **not** synonymous with `"VN"`. In real business logic, you need to determine whether `null` is truly a valid identity value or must be rejected right at construction.
- `HashSet` has only four distinct keys by equality: the groups `(ACME, M-17, VN)`, `(ACME, M-17, SG)`, `(BETA, M-17, VN)`, and `(ACME, M-17, null)`. `b` matches `a`; `f` matches `e`.
- Changing `a`'s `displayName` does not affect `hashCode()` because that attribute does not participate in equality. Hence `contains(a)` remains true; a new instance with the same three identity components is also recognized as already present.
- `record Coordinate` automatically generates `equals()` and `hashCode()` based on the components `x`, `y`. This is a concise choice for a value object when the equality definition is simply all record components. A record does not automatically understand business identity rules: to ignore a component, you need to redesign it.

## 5. Process for Choosing and Combining Multiple Fields

### Step 1 — Write the equality definition in words

For example: “Two `Membership` objects are equal if and only if they have the same `tenantId`, `memberNumber`, and `region`.” Specify the value domain, meaning of `null`, case-sensitivity rules, and whether an object not yet assigned an ID can be compared by ID.

A simple decision table:

| Field | Belongs to equality? | Reason |
| --- | --- | --- |
| `tenantId` | Yes | Member number is only unique within a tenant's scope |
| `memberNumber` | Yes | Assigned code to identify the member |
| `region` | Yes, **per the example's assumption** | Region is a fixed component of the identity namespace |
| `displayName` | No | Descriptive only; can change without changing the entity |

**Do not copy this table to another domain** without properly identifying that domain's business invariants.

### Step 2 — Keep equality components stable

In the example, the three identity components are declared `final`. `final` keeps the field's reference from being reassigned, but **does not make the referenced object immutable**. For components that are `List`, `Set`, arrays, or mutable objects, use defensive copies and immutable element designs if you want to use them in stable equality/hashing.

### Step 3 — Compare each field according to its type

- Primitives `int`, `long`, `boolean`: usually use `==` (for floating-point numbers see the notes on NaN and signed zero).
- `String` and immutable value objects: `Objects.equals(a, b)` (safe when `null` is possible) or `a.equals(b)` when guaranteed non-`null`.
- `List`: `List.equals` compares order and element values according to each element's rules.
- `Set`: `Set.equals` compares the elements of the set, regardless of iteration order.
- `Map`: `Map.equals` compares key-value mappings.
- Arrays: use `Arrays.equals` or `Arrays.deepEquals` according to nesting level; `Objects.equals` with two ordinary arrays only checks **same array reference**, not content.
- Types with special comparisons like currency/decimals: clearly determine the canonical form before choosing a comparison method.

### Step 4 — Implement `hashCode()` using the same definition

If you chose the tuple `(tenantId, memberNumber, region)` in `equals()`, use only this tuple to compute the hash. For a class with few fields, `Objects.hash(...)` is easy to read and reduces omission bugs. If measured performance requires optimization, you can combine via `31 * result + fieldHash`, while ensuring the comparison method and hash method remain compatible.

Note **ordering**: `Objects.hash(a, b)` and `Objects.hash(b, a)` can differ; hashing does not substitute for comparison. Do not rely on hashes to uniquely distinguish objects.

### Step 5 — Create test cases distinguishing each component

For a three-field equality definition, test at least:

1. Same reference; two different instances with all three fields equal.
2. Only **one field** out of the three differing, repeated for each field.
3. Both `null` in a nullable field; one side `null`, the other having a value.
4. A field outside the definition (`displayName`) differing while still having to be equal.
5. Two equal objects must have the same hash; `HashSet`/`HashMap` recognize keys consistently.
6. Call `equals(null)` and `equals` with an object of a different type; verify reflexivity, symmetry, transitivity.

Testing only with “all fields identical” is not enough: it can hide the bug of forgetting a field or mistakenly including a descriptive field in equality.

## 6. Situations Requiring Special Handling

### 6.1. Cases with arrays

Two separate arrays containing the same elements still normally return `false` when calling `array1.equals(array2)` directly. If an array is a component of equality, use a synchronized pair of functions:

```java
// Illustration inside a class with int[] scores:
return Arrays.equals(this.scores, that.scores);
```

```java
// Corresponding part in hashCode():
return Arrays.hashCode(scores);
```

Both snippets need `import java.util.Arrays;`, an appropriate `that` type, and any other components of the class if present. For multidimensional arrays containing sub-arrays, `Arrays.deepEquals(...)` combined with `Arrays.deepHashCode(...)` is commonly used. Note that arrays can be mutated; defensive copies are needed when they affect the hash or are components of a record.

### 6.2. `BigDecimal`: same numeric value does not necessarily mean equal by `equals()`

`new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` because `scale` differs, even though `compareTo(...) == 0`. If the value object's equality definition is **exact equality per `BigDecimal.equals`**, use `Objects.equals` and `BigDecimal.hashCode` consistently. If the domain wants to treat `1.0` and `1.00` as the same value, a uniform normalization approach is needed and the hash must be defined on the normalized value, rather than just changing the comparison to `compareTo(...) == 0` while keeping the original `BigDecimal.hashCode()`. For money, both currency unit and scale/rounding rules must be specified.

### 6.3. Strings with normalization

Whether codes `"ab-01"` and `"AB-01"` are equal depends on business policy. If case-insensitivity is desired, prefer **normalizing the ID when receiving/creating the object** and storing one stable canonical form, rather than comparing with `equalsIgnoreCase` while `hashCode` uses `String.hashCode` of the original string. If normalization is locale-dependent, avoid calling `toLowerCase()` without specifying a locale (for example, use `Locale.ROOT` for technical codes when appropriate). Do not automatically `trim`/strip accents/decompose characters if the domain rules do not allow it.

### 6.4. Inheritance and symmetry

A subclass adding a field to `equals()` while the superclass compares only common fields can break symmetry or transitivity. For instance, the parent considers two objects equal by code, whereas the child demands both code and subtype; `parent.equals(child)` and `child.equals(parent)` can easily differ. One straightforward direction is to use a `final` class for a value type/entity with a fixed equality definition. In an open hierarchy, a consistent type policy (such as `getClass()` or an appropriate `instanceof` rule) must be defined and designed across all classes; do not mix arbitrarily. ORM proxies can make runtime class comparison more complex, so follow the equality strategy recommended for the specific framework.

### 6.5. Post-persistence assigned IDs and objects with mutable state

If a new entity has `id == null`, the snippet `Objects.equals(this.id, that.id)` can make **all unsaved entities** equal because both IDs are `null`. If the ID is assigned after the object has been added to a `HashSet`, `hashCode()` changing with the ID can cause `contains` or `remove` to fail. A clear strategy is needed for transient/persisted entities, ensuring stable hashes when needed, or assigning stable IDs early. Do not “quick-fix” by putting all fields into equality.

### 6.6. Record, Lombok, and auto-generated code

- A Java `record` auto-generates `equals/hashCode` based on **all** components, suitable when that is the value object's definition. For arrays, the default equality of an array component does not automatically become deep content equality.
- IDEs and libraries like Lombok can generate `equals/hashCode`, but **the right fields must be chosen** (e.g., include/exclude) according to the written rules. Syntactically valid generated code can still be domain-wrong if it includes mutable/cache fields or omits a tenant ID.
- When adding/removing class fields, always ask whether the equality definition changes; do not automatically update it just because the list of attributes is different from before.

## 7. Common Mistakes and How to Spot Them

| Mistake | Consequence | How to prevent |
| --- | --- | --- |
| Comparing only `memberNumber`, forgetting `tenantId` | Mixes data across two tenants | Write out the composite key definition and test each field differing |
| Including mutable `displayName` in `equals/hashCode` | The same entity can become different after renaming; key in `HashSet` gets “lost” | Use only stable identity components |
| `equals()` uses three fields but `hashCode()` uses all four | `equals` objects can have different hashes; `HashMap/HashSet` misbehave | Use the exact same field set and normalization |
| Comparing references with `==` when content comparison is desired | Two instances with the same value are treated as different | `Objects.equals`/`equals` appropriate to the type |
| Comparing arrays with `Objects.equals` expecting element comparison | Two different array instances with the same content are treated as different | `Arrays.equals/deepEquals` and corresponding hash |
| Using `compareTo` for `BigDecimal` while keeping original hash | Violates `equals/hashCode` contract | Normalize values and hash uniformly |
| Comparing unnormalized data in one place, normalized in another | Unstable or inconsistent equality | Normalize at the data creation boundary |
| Comparing parent/child classes without a shared policy | Breaks symmetry or transitivity | Design inheritance and equality uniformly; consider `final` |
| Comparing/hashing only by ID that is `null` before saving | New entities get mistakenly merged, hash changes after insert | Dedicated strategy for identity lifecycle |

## 8. Self-Check Exercises

**Exercise 1.** In a multi-tenant system, `ticketNo` can repeat across tenants. If only `ticketNo` is compared, are the pairs `(T1, A-10)` and `(T2, A-10)` equal according to the domain?

**Answer:** No, if the namespace is per tenant. `equals()` must combine `tenantId` and `ticketNo`; `hashCode()` follows the same pair.

**Exercise 2.** Two versions of the same `Membership` have the same `tenantId`, `memberNumber`, `region`, but different `displayName`. By the definition in the example, what does `equals` return?

**Answer:** `true`. The display name is not a member identity component.

**Exercise 3.** A developer updates `equals()` to also compare `region` but forgets to update `hashCode()`, so the hash currently relies only on the two old fields. Is it guaranteed to always violate the contract?

**Answer:** Not necessarily: if two objects are equal across all three fields, they are also equal across the two old fields, so they still have the same hash. However, the hash may have poorer distribution by ignoring `region`, and the code becomes hard to maintain. The **dangerous contract violation** case is when the hash uses fields that `equals()` ignores (or uses an inconsistent normalization): two equal objects can produce different hashes. Even if the contract is not guaranteed to break, keep the definition and hash code synchronized for easy verification.

**Exercise 4.** `new BigDecimal("1.0")` and `new BigDecimal("1.00")` have the same mathematical numeric value; does `BigDecimal.equals` treat them as equal? If `compareTo==0` is used in equality, what else must be done?

**Answer:** `BigDecimal.equals` returns `false`; if numeric-value equality is desired, `hashCode` must also be computed from a corresponding normalized representation.

**Exercise 5.** Two `record Pair(int left, int right)` instances have equal `left` and different `right`. What does the default `record.equals` return?

**Answer:** `false`, because a record compares all of its components by default.

---

**Key takeaway:** The most important step when implementing `equals()` for multiple fields is **first determining which fields form the equality relation according to the business domain**. Then compare each field with the appropriate comparison, handle `null`/data types/inheritance consistently, and build a compatible `hashCode()`. The set of fields used for identification should remain stable for as long as the object is used in hash-based structures.