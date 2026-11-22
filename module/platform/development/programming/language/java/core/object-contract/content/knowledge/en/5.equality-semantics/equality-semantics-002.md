# Choosing the Fields That Truly Determine an Object's Value

## 1. Field Selection Starts From the Definition of "Equality"

In Java, `equals(Object)` and `hashCode()` must reflect the object's meaning in the problem domain, not simply compare every field just because it is present in the class. The most important question is: **If two objects differ in field X, should they still be considered the same entity or the same value under business rules?**

For example, two accounts with the same account ID but different display names may still be the same account. Conversely, two orders with the exact same total amount but different order IDs are still two separate orders. Two coordinates `Point(2, 3)` may be considered the same value even though they are two objects created by two separate `new` expressions.

Therefore, **write a one-sentence definition of equality in business language before writing code**:

- “Two accounts are equal if their immutable account IDs are the same within the same identity scope.”
- “Two monetary amounts are equal if both currency and amount in minor units are the same.”
- “Two room booking keys are equal if they have the same hotel, check-in date, and room code.”
- “Two connection sessions are the same only if they are the exact same resource instance” (a case where default identity should be kept).

A class may carry many fields, yet only a subset truly determines identity or value. This subset must be used **consistently across `equals()` and `hashCode()`**.

## 2. Three Perspectives on Objects

| Model | When are two objects equal? | Fields to use |
| --- | --- | --- |
| **Entity** | Represent the same entity over time, even if state changes | A stable identifier, sufficiently unique within the business scope |
| **Value object** | Carry the same value described by their components | All attributes that truly constitute the value |
| **Identity object** | Exactly the same instance | Can keep `Object.equals()` and `Object.hashCode()` |

**Entity:** With `Account(accountId, displayName, loginCount)`, suppose the domain specifies that `accountId` is an immutable, unique identifier. If `displayName` changes from “An” to “An Nguyen”, the account does not turn into a different account. If `loginCount` increases from 4 to 5, identity does not change either. In that case, only `accountId` is chosen for comparison.

**Value object:** With `Money(currency, minorUnits)`, both components determine the value: `Money("VND", 100_000)` differs from `Money("USD", 100_000)`. Comparing only the monetary amount loses currency unit information; comparing only the currency unit is insufficient as well.

**Default identity:** Two objects representing two currently open sessions might share the same URL, account, or configuration yet remain two distinct runtime resources. If there is no need for logical equality comparison, keeping `Object.equals()` by reference (`==`) is a well-founded decision.

A class name alone does not determine its model. A class named `User` might have an ID from construction, or only be assigned an ID when written to the database. Equality design must account for that lifecycle.

## 3. Criteria Table for Including or Excluding Each Field

Classify each attribute instead of automatically selecting all of them:

| Field kind | Usually participates in equality? | Question to decide |
| --- | --- | --- |
| Immutable, unique ID | Yes for entities | Is the ID sufficiently unique within the tenant/scope being compared? |
| Core value component | Yes for value objects | Would omitting it cause two differently meaningful values to be treated as one? |
| Display name or description | Usually no for entities | Does changing the name change identity? |
| `updatedAt`, `lastLoginAt`, counters | Usually no for entities | Does activity change create a new entity? |
| Cache or field derived from other data | Usually no | Does it carry new information, or is it merely derived data? |
| Collection holding value data | Possibly yes | Does order, element set, or a specific snapshot matter? Can the contents mutate? |
| Database key assigned after `persist` | Requires a lifecycle policy | Before an ID exists, how are two new entities compared? |
| Fields in a superclass | Depends on the whole hierarchy's rules | Are symmetry and transitivity preserved when comparing superclass and subclass? |

To test a choice, pose two counterexample scenarios:

1. **Missing field:** Keep all selected fields unchanged, vary an excluded field X. Is there any case where two objects **must be different** yet `equals()` returns `true`?
2. **Extra field:** Keep the identifier/value components unchanged, vary a selected field Y. Is there any case where two objects **must remain equal** yet `equals()` returns `false`?

For instance, a room booking key may be `(hotelId, roomNo)`; if only `roomNo` is chosen, room “101” at two different hotels is treated as one. An `accountId` that is unique only per tenant also requires adding `tenantId` to the comparison key. Conversely, if the ID is already globally unique across the system, descriptive fields may not need to participate in equality.

## 4. Java Contracts That Must Be Preserved

`Object.equals()` requires:

1. **Reflexive:** `x.equals(x)` is always `true` for non-null `x`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` yield the same result.
3. **Transitive:** if `x` equals `y` and `y` equals `z`, then `x` equals `z`.
4. **Consistent:** repeated comparisons return stable results as long as the relevant attributes do not change.
5. **Non-null:** `x.equals(null)` must be `false`.

`Object.hashCode()` requires: whenever `x.equals(y)` is `true`, **`x.hashCode() == y.hashCode()` must also be `true`**. The converse is not mandatory: matching hashes do not prove two objects are equal. Collisions are permitted.

If `equals()` uses only `id` while `hashCode()` uses `id` and `displayName`, two equal objects can produce different hashes, violating the contract. Compute the hash from the exact same set of chosen fields; do not add timestamps, display names, or random numbers just to “avoid hash collisions”.

Another note: **a key's hash should not change while the key is inside a `HashMap` or `HashSet`**. Collections use the hash to locate the bucket; if a field participating in the hash changes after insertion, `contains()` or `get()` may fail even for the exact same object. `final` prevents reassigning the field, yet `final List<String>` still allows modifying the referenced list's contents. Immutability must consider the entire relevant object graph.

## 5. Complete Runnable Java 17+ Example

The program below illustrates two models: entity `Account` using only its identifier, and value object `Money` using all its value components. Create the file `EqualityFieldsDemo.java`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityFieldsDemo {

    static final class Account {
        private final String accountId;
        private String displayName;
        private int loginCount;

        Account(String accountId, String displayName) {
            this.accountId = Objects.requireNonNull(accountId);
            if (accountId.isBlank()) {
                throw new IllegalArgumentException("accountId must not be blank");
            }
            this.displayName = Objects.requireNonNull(displayName);
        }

        void rename(String name) {
            displayName = Objects.requireNonNull(name);
        }

        void recordLogin() {
            loginCount++;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Account)) return false;
            Account that = (Account) other;
            return accountId.equals(that.accountId);
        }

        @Override
        public int hashCode() {
            return accountId.hashCode();
        }
    }

    // Both components of the record are value components.
    record Money(String currency, long minorUnits) {
        Money {
            Objects.requireNonNull(currency);
            if (currency.isBlank()) {
                throw new IllegalArgumentException("currency must not be blank");
            }
        }
    }

    public static void main(String[] args) {
        Account a = new Account("ACC-01", "An");
        Account b = new Account("ACC-01", "Tên khác");
        Account c = new Account("ACC-02", "An");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));

        Set<Account> accounts = new HashSet<>();
        accounts.add(a);
        accounts.add(b);
        accounts.add(c);
        System.out.println(accounts.size());

        a.rename("An Nguyễn");
        a.recordLogin();
        System.out.println(accounts.contains(a));
        System.out.println(accounts.contains(b));

        Money m1 = new Money("VND", 100_000);
        Money m2 = new Money("VND", 100_000);
        Money m3 = new Money("USD", 100_000);
        System.out.println(m1.equals(m2));
        System.out.println(m1.equals(m3));
        System.out.println(m1.hashCode() == m2.hashCode());
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

Compile and run:

```bash
javac EqualityFieldsDemo.java
java EqualityFieldsDemo
```

Stdout:

```text
true
false
2
true
true
true
false
true
true
```

Explanation of output in order:

- `a` and `b` are different instances with different names, yet share the same `accountId`, so `equals()` returns `true`. `a` and `c` have different IDs, so `false`.
- `HashSet` holds two logical elements: accounts `ACC-01` and `ACC-02`. Adding `b` does not increase the count because `a` already represents the same identity.
- When `a` is renamed and its login counter increments, the identity key remains unchanged, so `accounts.contains(a)` stays `true`; another instance with the same ID (`b`) is also recognized.
- `Money` is a `record`. Java automatically generates `equals()` and `hashCode()` from its record components; two values with the same currency code and amount are equal, while different currency codes are not.
- Two objects considered equal by `equals()` must have the same hash. However, two objects with the same hash are not necessarily equal.

In the example, `Account` is `final`, so no subclass can add attributes and alter the equality policy. `accountId` is an immutable `String` and does not change after construction. `displayName` and `loginCount` are mutable but do not participate in equality. That is why the policy remains stable with `HashSet`.

**Understand the limitations of `record`:** A record generates equality across **all record components**, unaware of which component carries business meaning. A display label or cache component, if placed in a record, will affect default equality. A record does not automatically make mutable objects referenced by its components immutable.

## 6. Common Pitfalls When Selecting Fields

### 6.1. Selecting Every Available Field Because the IDE Suggests It

An entity class with 10 fields does not mean all 10 fields determine identity. `name`, `status`, `lastModifiedAt`, or `computedScore` are usually mutable information, not ID representations. Including them can cause the same entity to be treated as a different entity after an update. Tools like Generate `equals()/hashCode()`, Lombok, or an IDE only generate code for the list you choose; they do not inherently know your business model.

### 6.2. ID Not Yet Assigned Upon Construction

If the database assigns `id` after saving, two new entities both have `id == null`. The following pattern can cause them to be considered equal:

```java
// Illustrates the bug when both id values can be null.
return Objects.equals(this.id, other.id);
```

Moreover, if `hashCode()` relies directly on `id`, the hash will change when the ID is assigned. Behavior before/after persistence must be specified. One option is to assign an immutable identifier upon object creation (e.g., a UUID if appropriate for the system). In systems using database-generated IDs, two entities without an ID can be treated as equal only when they are the same reference, while designing a stable hash and avoiding placing entities into hash collections before key lifecycle is clear. With JPA/Hibernate, one must also consider proxies, ID types, sessions, and equality of detached objects. **There is no single post-save generated-ID formula that applies safely to every system.**

### 6.3. Using Mutable Fields in the Key

For example, `Person(name, address)` where `equals()/hashCode()` uses `address`, and the address is later changed while the object is already in a `HashSet`. The old hash used at insertion differs from the new hash at lookup, which can cause `contains(person)` to return `false`. If `address` is merely user state rather than identity-defining, exclude it from the key. If `address` is genuinely part of a value object, model it as immutable or use an unchanging snapshot key.

### 6.4. Choosing the Wrong Comparison Method for the Data Type

- **Array:** `Objects.equals(a, b)` on arrays compares the arrays themselves (typically by reference). Use `Arrays.equals()` for one-dimensional contents, `Arrays.deepEquals()` when comparing nested arrays, and compute the corresponding hash with `Arrays.hashCode()` or `Arrays.deepHashCode()`.
- **`BigDecimal`:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` due to differing scales, even though `compareTo()` returns `0`. If the domain considers only numeric value, a unified normalization rule is needed for both comparison and hash; do not mix `compareTo() == 0` with `BigDecimal`'s raw hash.
- **`double`/`float`:** using a threshold `Math.abs(a - b) < epsilon` for equality can violate transitivity: A is close to B, B is close to C, yet A is not close to C. If equality by rounded units is needed, normalize into a value key according to a predefined rule.
- **Collection:** `List.equals()` considers order, `Set.equals()` does not depend on element order, `Map.equals()` relies on key-value pairs. If the domain has different semantics, represent or normalize the type accordingly.
- **`null`:** `Objects.equals(x, y)` is useful for nullable fields; if null is not a valid state, reject it in the constructor instead of silently allowing two objects missing a key to become equal.

### 6.5. Inconsistent Data Normalization

For product codes or key names, stripping whitespace or unifying upper/lower case may be necessary. However, do not arbitrarily apply `toLowerCase()` to every email, person's name, SKU, or technical code: case sensitivity is a domain rule. If normalization is needed, perform it **before establishing the equality key** and ensure both hash and equality rely on the same normalized representation. For Unicode strings, accent removal, case conversion, or normalization must follow a specific policy and be tested with edge cases.

### 6.6. Inheritance Can Break Symmetry

A superclass checking `instanceof Parent` and comparing only parent fields, while a subclass additionally checks subclass fields, can cause `parent.equals(child)` to differ from `child.equals(parent)`. Checking `getClass()` is stricter, but may prevent proxies/subclasses from being treated as the same type even when the domain expects it. For value objects, `final` or `record` is usually simpler. For open hierarchies, a unified equality contract must be built across both superclass and subclass; calling `super.equals()` does not automatically resolve all conflicts.

## 7. Implementation Pattern With Two Key Fields

Suppose a class `final MyKey` has two fields `keyPartA` and `keyPartB` forming a business key. **The snippet below shows only two methods inside a class that already declares the corresponding fields, not a standalone program:**

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof MyKey)) return false;
    MyKey that = (MyKey) other;
    return Objects.equals(keyPartA, that.keyPartA)
        && Objects.equals(keyPartB, that.keyPartB);
}

@Override
public int hashCode() {
    return Objects.hash(keyPartA, keyPartB);
}
```

`Objects.hash()` is convenient when writing code, though not mandatory; on hot paths, consider varargs/boxing overhead if profiling shows it is significant. More important than micro-performance is **choosing the right fields**. If the fields do not allow null, the constructor should validate and establish clear invariants. For components that are arrays or mutable collections, apply appropriate copying and hashing rules.

If a value object holds `final List<String> tags`, making the field `final` is not enough to prevent `tags.add(...)`. You can use `List.copyOf(tags)` in the constructor to lock the list's structure, though that is a shallow copy: if the elements are mutable objects, a separate policy is still needed. Also avoid putting a time-varying collection directly into a key if long-term stability is required.

## 8. Verifying Choices With Tests

After selecting fields, create pairs of objects with concrete business meaning:

| Scenario | Expectation |
| --- | --- |
| Same reference | `equals()` is `true` |
| Different instances with the same valid identity | `equals()` is `true` and hashes are equal |
| Same display name but different identifier | `equals()` is `false` |
| Changing state fields that do not determine identity | `equals()/hashCode()` do not change |
| Two value objects differing in one core component | `equals()` is `false` |
| Comparing against `null` or an incompatible type | `equals()` is `false` |
| Three objects defined as equal | Check symmetry and transitivity |
| Used as a key in `HashMap`/`HashSet` | Lookup stays stable when non-key fields change |

An equality contract verification library can detect symmetry, transitivity, and hash mismatch bugs. However, such a library cannot know on its own which two objects the domain intends to be equal. Therefore, you must test both **business meaning** and the **Java contract**.

## 9. Self-Check

**1.** `Product` has an immutable `productId`, while `name`, `price`, and `stockCount` can change. If the same ID means the same product, what should be chosen?  
**Answer:** `productId` (add a namespace if the ID is unique only within that scope). The remaining fields are state.

**2.** `Dimension(width, height, unit)` is a value object; can `unit` be omitted from equality?  
**Answer:** Not by default. “10 cm” differs from “10 m”; omit the unit only when a consistent conversion/normalization policy is in place and values are represented in a single canonical unit.

**3.** Is it valid for two equal objects to have different hashes?  
**Answer:** No. This is a mandatory violation of `hashCode()`.

**4.** Can two different objects have the same `hashCode()`?  
**Answer:** Yes. A collision does not imply two objects are equal.

**5.** Should `updatedAt` be included in an entity's equality?  
**Answer:** Only if the data domain truly treats each snapshot/version as a distinct value. If it is the same entity across updates, then no.

**6.** Is `final List<String> tags` already an immutable key?  
**Answer:** Not yet. The contents of the list can still be modified. A defensive copy or appropriate immutability policy is required.

**7.** Does `record`-generated equality always match business rules?  
**Answer:** No. A record defaults to using all components; the domain decides which components carry value meaning.

The most important practical takeaway: **define equality using domain rules first; pick the fields that truly represent value/identity; ensure those fields are stable and used consistently by both `equals()` and `hashCode()`.**