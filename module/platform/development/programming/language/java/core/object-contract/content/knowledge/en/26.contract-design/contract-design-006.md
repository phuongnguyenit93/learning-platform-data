# Assessing the Impact of Adding Fields or Changing Class Versions

## 1. Why Is This a Contract Change, Not Just a Structural Change?

In Java, a class is a bundle of multiple **observable contracts**: public data and methods, how two objects are determined to be equal, how hash codes are computed, how objects are ordered, how they are represented as strings, and sometimes how data is persisted or transmitted. Adding a field or releasing a new class version can affect each contract to a different degree.

For example, an account object has `accountId` and `displayName`. If you add `membershipTier`, you must answer: should two objects with the same `accountId` but different `membershipTier` still be considered the same account? If the answer is **yes**, the new field is a descriptive attribute and should not automatically join the logical identity comparison. If the answer is **no**, adding the new field to `equals()` changes **equality semantics**; any code relying on sets, maps, caches, or legacy data may be affected.

Distinguish the types of changes:

- **Structural change:** adding, removing, renaming, changing the type of, or changing the mutability of a field; adding a `record` component.
- **API change:** changing constructors, accessors, methods, parameter order, or visibility.
- **Semantic change:** changing the conditions of `equals()`, `hashCode()`, `compareTo()`, a comparator, or information in `toString()`.
- **Data compatibility change:** how a new version reads data written by an old version and vice versa; changes to Java serialization, JSON, database schemas, or cache structures.

A change can keep the program **compiling** yet still break business behavior. Therefore, contract assessment must examine source code, compiled binaries, runtime state, and persisted data.

## 2. Invariants to Preserve When Changing `equals()` and `hashCode()`

For non-null objects, `equals` must adhere to Java's fundamental contract:

1. **Reflexive:** `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` produce the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)` are both true, `x.equals(z)` must be true.
4. **Consistent:** the result does not change on its own while the information used for comparison remains unchanged.
5. **For null:** `x.equals(null)` returns `false`.

`hashCode()` must remain consistent with `equals()`:

- If `a.equals(b)` is true, `a.hashCode() == b.hashCode()` must be true.
- Two **unequal** objects may still share a hash code; a hash code is not a unique identifier.
- Within a single execution and while the information used for `equals` does not change, the hash code must remain stable per contract.
- There is no requirement that an object's hash code stay identical across different Java executions.

**Checkpoint when adding a field:** if the new field participates in `equals`, update `hashCode` over the **same equivalent set of information**. Conversely, adding a display-only field generally does not require changing `equals` and `hashCode`.

| Handling of New Field | Impact on Equality | Consequences Worth Checking |
| --- | --- | --- |
| Excluded from `equals`/`hashCode` | Old and new objects can still be equal by the defined key | Do not omit the field if the business actually requires distinguishing it |
| Included in both | Previously equal objects may become unequal | `HashMap`, `HashSet`, cache keys, deduplication, tests, and migration |
| Included in `equals` but forgotten in `hashCode` | Risk of contract violation when two equal objects have different hash codes | Incorrect or unpredictable lookup/element counts in hash structures |
| Included in `hashCode` but omitted from `equals` | Can directly violate the rule that two equal objects share the same hash code | Key lookup with an equivalent object fails |

The decision to include a field in comparison must come from the business domain's **definition of same value/same logical entity**, not simply from the fact that the class gained a new member variable.

## 3. Example: Adding an Attribute While Preserving Logical Identity

A system uses `accountId` as its logical key. `displayName` and `tier` can change while remaining the same account. If these attributes only describe the account, they should not turn two representations of the same ID into two separate keys.

Create the file **`AccountContractDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class AccountContractDemo {
    static final class Account {
        private final String accountId;
        private final String displayName;
        private final String tier;

        Account(String accountId, String displayName, String tier) {
            this.accountId = Objects.requireNonNull(accountId);
            this.displayName = Objects.requireNonNull(displayName);
            this.tier = Objects.requireNonNull(tier);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Account that)) return false;
            return accountId.equals(that.accountId);
        }

        @Override
        public int hashCode() {
            return accountId.hashCode();
        }

        @Override
        public String toString() {
            return "Account[id=" + accountId
                    + ", name=" + displayName
                    + ", tier=" + tier + "]";
        }
    }

    public static void main(String[] args) {
        Account before = new Account("A-07", "Lan", "BASIC");
        Account after = new Account("A-07", "Lan Nguyen", "GOLD");

        System.out.println("same instance: " + (before == after));
        System.out.println("equal by accountId: " + before.equals(after));
        System.out.println("same hash: " + (before.hashCode() == after.hashCode()));

        Map<Account, String> statusByAccount = new HashMap<>();
        statusByAccount.put(before, "ACTIVE");
        System.out.println("status via updated view: "
                + statusByAccount.get(after));
        System.out.println("map size: " + statusByAccount.size());
    }
}
```

Run with JDK 17 or higher:

```bash
javac AccountContractDemo.java
java AccountContractDemo
```

Output:

```text
same instance: false
equal by accountId: true
same hash: true
status via updated view: ACTIVE
map size: 1
```

Two `new Account(...)` calls create **two different instances**, yet both represent the same logical key `A-07`. `HashMap` still looks up the value because both `equals` and `hashCode` are based on `accountId`.

This example is only valid when the business domain guarantees that **one `accountId` is never reused to refer to a different account** within the comparison scope. If the real logical key consists of both `tenantId` and `accountId`, both must participate in `equals` and `hashCode`. If `tenantId` is added to resolve duplicate IDs across tenants, that is an **intentional** contract change requiring a data migration plan.

## 4. Counterexample: Mutating a Key Field After Putting It into a `HashMap`

For a key whose `hashCode` depends on a mutable field, changing the value after adding it to a map can make the entry unreachable by that key. This risk is especially high when a new version switches from comparing an immutable ID to also comparing a mutable field.

Create the file **`MutableKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class MutableKeyDemo {
    static final class Key {
        String id;

        Key(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key that && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        Map<Key, String> map = new HashMap<>();
        Key key = new Key("A");

        map.put(key, "stored");
        System.out.println("before mutation: " + map.get(key));

        key.id = "B";
        System.out.println("after mutation: " + map.get(key));
        System.out.println("map size: " + map.size());
    }
}
```

Run:

```bash
javac MutableKeyDemo.java
java MutableKeyDemo
```

Output:

```text
before mutation: stored
after mutation: null
map size: 1
```

The entry still exists in the map, but the lookup uses the new hash code `"B".hashCode()` and therefore cannot find the entry stored under `"A"`'s hash. You cannot fix the root bug simply by rewriting `hashCode()`: information participating in a key must remain **stable while the key is inside the collection**. Prefer immutable keys, or remove the entry before changing its value and re-insert under the new key when there is a clear business requirement.

Even a class with `final` fields still needs **deep immutability** review: a `final List<String> tags` reference cannot be reassigned, yet the list's contents can still be mutated. Putting a mutable list into `equals`/`hashCode` carries the same risk. Defensively copy and keep components immutable where needed.

## 5. Impact Matrix by Type of Class Change

| Change | Contract Risk | What to Check |
| --- | --- | --- |
| Add a descriptive field not in equality | Usually preserves current value equality; `toString` or JSON may change | Output, logging, serialization, schema |
| Add a field participating in equality | Previously equal objects may become unequal | `equals`/`hashCode`, collections, keys, and legacy data |
| Rename a field while preserving meaning | May not alter equality, yet breaks field name/API/serialization | Accessors, constructors, JSON properties, database columns |
| Change a field type, e.g. `int` to `long` | Can alter API/bytecode descriptors; coercion and equality | Call sites, binary linkage, data conversion, boundary values |
| Remove a field | Old APIs and data may expect the removed field | Constructors, getters, persisted data, legacy apps |
| Make an immutable field mutable | Risk of hash keys changing while in use | `HashMap`/`HashSet`, race conditions, defensive copies |
| Add a component to a `record` | Equality, hash, string representation, and canonical constructor change by default | Callers, comparisons, serialization |
| Change superclass or type-check strategy | Can cause symmetry/transitivity bugs in `equals` | Base/subclass tests, inheritance rules |
| Change comparator or `compareTo` | `TreeSet`/`TreeMap` may treat two keys as the same element under ordering | Consistency with `equals` and business ordering |
| Change `toString` | Integration code parsing the string may break; logs may leak data | Do not treat `toString` as a machine-readable API; check sensitive data |

A **new field does not automatically belong in every method**. Each method's contract is designed independently: logical key for equality; business order for ordering; clear, leak-free representation for `toString`.

## 6. Special Considerations for `record` and Generated Code

For `record`, Java automatically generates `equals`, `hashCode`, and `toString` from the record components unless overridden. Adding a component can alter the equality relation even when the developer **did not directly touch `equals`**.

Example illustrating two data shapes before and after adding a component; create the file **`RecordEvolutionDemo.java`**:

```java
public class RecordEvolutionDemo {
    record InvoiceV1(String invoiceId) {}
    record InvoiceV2(String invoiceId, String label) {}

    public static void main(String[] args) {
        InvoiceV1 oldA = new InvoiceV1("I-1");
        InvoiceV1 oldB = new InvoiceV1("I-1");

        InvoiceV2 newA = new InvoiceV2("I-1", "draft");
        InvoiceV2 newB = new InvoiceV2("I-1", "paid");

        System.out.println("V1 equal: " + oldA.equals(oldB));
        System.out.println("V2 equal: " + newA.equals(newB));
        System.out.println("V1 text: " + oldA);
        System.out.println("V2 text: " + newA);
    }
}
```

Run:

```bash
javac RecordEvolutionDemo.java
java RecordEvolutionDemo
```

Output:

```text
V1 equal: true
V2 equal: false
V1 text: InvoiceV1[invoiceId=I-1]
V2 text: InvoiceV2[invoiceId=I-1, label=draft]
```

In real code, changing `record Invoice(String invoiceId)` to `record Invoice(String invoiceId, String label)` also changes the **canonical constructor**: old `new Invoice("I-1")` calls cease to be valid at the source level unless the developer explicitly supplies a compatibility constructor. Already-compiled classes can hit linkage errors if the constructor they invoke no longer exists.

The two types `InvoiceV1` and `InvoiceV2` in the example only illustrate **structural and result changes**, not proof that objects of two types can be compared directly as the same class across deployments. With Java records, you also cannot rely on inheritance from a record to share equality across versions: records are final.

If equality semantics must rely solely on `invoiceId`, consider overriding `equals` and `hashCode` consistently, or better yet, separate a **stable business key type** (such as `InvoiceId`) from records carrying multi-version data. Do not arbitrarily alter a record's equality merely to ignore a difference that the business actually needs to distinguish.

## 7. Source, Binary, Behavioral, and Data Compatibility Are Four Separate Questions

### 7.1. Source Compatibility: Does Old Caller Source Code Still Compile?

Consider these cases:

- Adding a `private` field while keeping the old constructor intact may have minimal impact on callers.
- Adding a required parameter to a constructor and **removing the old constructor** causes prior calls to stop compiling.
- Renaming a getter, renaming a `public` field, or changing a return type can break caller compilation.
- Adding a component to a record changes the canonical constructor and adds a new accessor; the old constructor remains only if supplied for compatibility.
- Changing generic signatures can cause compile errors at callers despite JVM type erasure creating certain special cases; verify directly against the published API.

### 7.2. Binary Compatibility: Does Already-Compiled Bytecode Still Run?

Independently deployed modules or libraries may still use previously compiled `.class` files. Removing or changing the descriptor of a field, method, or constructor invoked by bytecode can trigger runtime errors such as `NoSuchFieldError`, `NoSuchMethodError`, or `IllegalAccessError` during linking/access.

A change can be **binary-compatible** yet **behavior-incompatible**: for example, the API remains identical, but `equals` now compares `tier` as well, causing `HashSet` element counts to grow unexpectedly. Checking binary compatibility is not enough to guarantee object contracts.

### 7.3. Behavioral Compatibility: Do Object Usage Results Remain the Same?

Specifically verify:

- `equals` results for two instances representing the same entity.
- `hashCode` values matching equality within the same version.
- Element counts in `HashSet`, `TreeSet` and duplicate keys in `HashMap`, `TreeMap`.
- Deduplication, cache keys, memoization, grouping, batching, and idempotency logic relying on equality.
- Comparisons between superclasses and subclasses, as well as through framework-generated proxies/types.
- Logs and `toString` if external callers have inadvertently depended on them as a data format.

### 7.4. Data Compatibility: Can New and Old Versions Read Each Other's Data?

Examine actual data paths: Java object serialization (if used), JSON/XML, caches, databases, events/messages, and snapshots. "A field was added" does not by itself answer whether **old data missing the field** is usable or whether **old consumers seeing an unknown field** will accept it; that depends on the library, configuration, schema, and default-handling policy.

Clarify **both directions** of compatibility:

| Direction | Question |
| --- | --- |
| New reader ← Old data | When the new field is absent, is there a valid default/backfill/migration? |
| Old reader ← New data | Will old consumers accept the new field or fail with an error? |
| Old service ↔ New service | During rolling deployment, are messages and logical keys stable? |
| Persistence/cache | Can data/keys from an earlier version be misread, missed, or duplicated? |

If equality/hash codes participate in cache keys or long-lived stored ID formats, plan for key migration or versioning. Java's `hashCode` is **not** suitable to store as a durable identifier across versions or JVMs.

## 8. Java Serialization: Special Handling If the Class Implements `Serializable`

Native Java serialization stores information as an object stream and enforces class-version compatibility rules. Key points:

- `serialVersionUID` checks serialization version compatibility for standard serializable classes. If the UID read from the stream differs from the local class's UID and validation applies, deserialization can throw `InvalidClassException`.
- When `serialVersionUID` is omitted, the JVM computes a default value from the class structure; class changes can cause this value to shift unexpectedly. If compatibility is required, declare the UID explicitly from the start and test against legacy data.
- With a **compatible change** and matching UID, an old stream lacking a new field can be read with Java's default value for that field: `null`, `0`, `false`, etc. This is not necessarily a **business-valid** value.
- Serialization compatibility does **not** imply equality compatibility: a restored object whose new field is `null` may yield different `equals`/`hashCode` results and cause processing code to throw `NullPointerException`.
- Changing types, inheritance hierarchies, object kinds, or custom serialization mechanisms carries distinct constraints; keeping the UID unchanged does not make every change compatible.
- Java records have specialized serialization mechanics, including reconstruction via the canonical constructor; do not mechanically extrapolate regular class `serialVersionUID` rules to records.

Conceptual example—**not two versions running together in one file**:

```java
// Old version:
class Profile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String id;
}

// New version, with the same binary class name when replaced in the application:
class Profile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String id;
    String region; // old data may read as null in compatible cases
}
```

These are two **separate version sketches** and must not be compiled simultaneously under the same class name. A valuable test is using the old version to write a fixture file, reading that fixture with the new version, and verifying default values, object invariants, and equality. Test the reverse direction as well when the system must support old consumers. Native Java serialization is not recommended as a new data-exchange format between untrusted services; consider formats with explicit schemas and compatibility policies.

## 9. Ordering Contracts: `compareTo()` and `Comparator`

Adding a field can change display order. This is separate from equality. For instance, products were previously sorted by `sku`, and later by `category` then `sku`. If a comparator is used inside `TreeSet` or `TreeMap`, two keys are considered equivalent when `compare(a, b) == 0`; the tree structure uses ordering results to determine key uniqueness.

An example of inconsistency: `equals` compares `sku` **and** `revision`, whereas the comparator compares only `sku`. Two objects with the same SKU and different revisions are not `equals`, yet a `TreeSet` using that comparator keeps only one element per SKU. Java recommends that `Comparable`'s natural ordering be consistent with `equals` for predictable `Set`/`Map` contract behavior; intentionally inconsistent comparators must be documented and tested for their intended purpose.

To maintain stability:

1. Specify clearly which fields determine **equality** and which determine **ordering**.
2. For `TreeSet`/`TreeMap`, check the impact when `compareTo` or a comparator treats different objects as the same key.
3. If a separate display order is needed, pass a comparator when sorting an appropriate collection rather than using it as the uniqueness definition.
4. If a field used for sorting is mutable, modifying it while the object is inside a tree structure can break internal ordering invariants; remove–update–reinsert or use immutable keys.

## 10. Inheritance and Type Changes: Avoiding Symmetry Violations

A superclass whose `equals` allows `instanceof Base`, combined with a subclass adding a field to equality, can create a situation where `base.equals(child)` is true while `child.equals(base)` is false. That is a **symmetry** violation.

Example of a **dangerous design pattern** (illustrative, not recommended for application use):

```java
class Base {
    final String id;

    Base(String id) { this.id = id; }

    @Override
    public boolean equals(Object o) {
        return o instanceof Base that && id.equals(that.id);
    }

    @Override
    public int hashCode() { return id.hashCode(); }
}

class Child extends Base {
    final String zone;

    Child(String id, String zone) {
        super(id);
        this.zone = zone;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof Child that
                && id.equals(that.id)
                && zone.equals(that.zone);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(id, zone);
    }
}
```

With `Base b = new Base("X"); Child c = new Child("X", "north");`, the expression `b.equals(c)` is `true`, whereas `c.equals(b)` is `false`. This scenario often arises when a new version extends a hierarchy and decides to include the subtype's extra information in comparisons.

Common remedies: design immutable `final` value types where appropriate; strictly specify how comparisons work across subtypes; or avoid inheritance for complex value equality and use composition. Comparing with `getClass()` enforces stricter type boundaries, though with trade-offs when framework proxies/subtypes must be supported. Do not change the equality strategy of an entire hierarchy just to accommodate one new field.

## 11. Assessing Impact on APIs, Caches, Data, and Distributed Systems

A class change should be traced along actual dependency paths:

```text
Field / constructor / record component changes
              |
              +--> equals / hashCode ----> HashMap, HashSet, cache, dedupe
              |
              +--> compareTo / Comparator -> TreeMap, TreeSet, sorting
              |
              +--> toString -------------> logs, diagnostics, representation
              |
              +--> public API -----------> source/binary callers
              |
              +--> serialization --------> file, JSON, event, DB, cache
```

For example, a system caches by an object key whose `equals` is based on `customerId`. A new version adds `country` to equality. During a mixed deployment of old and new versions:

- Logical keys that previously grouped records with the same ID may fragment by country in the new version.
- Cache hit rates and entry counts may shift, affecting memory, performance, and deduplication results.
- If the system uses durable string keys built from fields, the key format must also be versioned or migrated.
- When old data lacks `country`, a valid classification rule is needed rather than treating `null` as a real country.

Do not pass JVM-generated hash codes directly as cross-service identifiers. If you need cross-service identity, use a business ID with a stable schema, or build a well-specified identifier key (including namespace/tenant if needed).

## 12. Controlled Process for Modifying a Class

### Step 1 — State the Nature of the New Field

Pick one of the roles (there may be more than one; state specifically): logical key, value attribute, descriptive data, display field, runtime state, derived field, or protocol-version-only value. Ask: "Should two objects differing only in this field be considered the same value?"

### Step 2 — List Affected Contracts

Review `equals`, `hashCode`, `compareTo`/comparators, `toString`, constructors, accessors, serialization mappings, schemas, cache keys, validation, and ORM entity constraints. For `record`, review compiler-generated methods. For classes using Lombok or code-generation libraries, inspect field include/exclude configurations for equality/toString and the actual generated code.

### Step 3 — Determine the Required Compatibility Level

Classify explicitly: source, binary, behavioral, data. Check rollout requirements: are there previously compiled consumers, multiple versions running concurrently, legacy cache data, legacy serialized files, or in-flight messages? Only build compatibility strategies for the directions you truly need to support.

### Step 4 — Prepare Migration When Semantics Change

You may need to extract an independent logical key, apply valid defaults for the new field, migrate stored data, version cache keys, rebuild indexes, or roll out changes in phases so both producers and consumers understand the same schema during transition. The choices depend on the system; there is **no** automatic operation safe for every class.

### Step 5 — Test Contracts and Integration Behavior

Write tests with both old and new data versions. Test equality/hash consistency, distinguish immutable and mutable keys, and test actual collections/maps in use. Run compatibility fixtures with schemas/serialized data when persistence exists.

### Step 6 — Document and Publish Changes

If a public library/API changes, write migration guides, release notes, new defaults, constructor changes, JSON fields, and equality behavior. Bump the version according to the project's release policy; never assume bumping a version number creates compatibility on its own.

## 13. Practical Test Matrix

| Test Case | Purpose | Expected Result |
| --- | --- | --- |
| `x.equals(x)`; `x.equals(null)` | Reflexivity/null | `true`; `false` |
| `x.equals(y)` and `y.equals(x)` | Symmetry, including base/subclass | Both results match |
| `x == y` vs. independent data copies | Distinguish identity/value equality | Decision matches defined contract |
| `x.equals(y)` is true | Hash contract | `x.hashCode() == y.hashCode()` |
| Change only descriptive field excluded from equality | Logical key stability | `equals` unchanged, map still finds key |
| Change field truly participating in equality | Verify new semantics | Pair can flip from equal to unequal; intentional test |
| Mutable key already inside a map | Risk detection | Disallow direct mutation or have a reinsert strategy |
| Change comparator/`compareTo` | Compatibility with tree uniqueness | No unintended loss of items |
| Deserialize old fixture with new class | Legacy data | Defaults/migration valid; invariants preserved |
| Read new data with old consumer | Rolling deployment | Succeeds or actively rejected per policy |
| Compile old callers and run old binaries | API/bytecode | No compile/linkage errors outside announced breaking scope |
| Log output from `toString` | Security and observability | No leaked tokens, passwords, or sensitive info |

When changing equality, a test checking only `equals` is not enough: verify how `HashMap` retrieves the same key, how `HashSet` deduplicates elements, and how `TreeSet` determines duplicates via its comparator. If the application uses caches or storage, testing with real data from the previous version matters more than only creating new test objects.

## 14. Misconceptions to Avoid

**"When adding a field, let the IDE regenerate `equals/hashCode` with all fields."** Auto-generation cannot decide identity/value semantics for you. It can accidentally turn display fields, timestamps, or mutable fields into key components.

**"Keeping `serialVersionUID` unchanged makes every version compatible."** UID does not solve every type/structure change, business invariant, or post-deserialization equality change.

**"Unchanged method signatures mean clients won't break."** Clients can still break because `equals` changed, a comparator changed order, or JSON representation shifted.

**"Same hash code means same object/same value."** Collisions can occur; always pair with `equals` per the appropriate contract when comparing value equality. For reference identity, use `==` and identity-based data structures.

**"Every field in a record is business identity."** Records are value-oriented with equality generated across all components by default; component selection must match semantics. Separate descriptive objects from value keys when you do not want every field in equality.

**"Bidirectional compatibility is always required."** Build only the directions needed by the deployment topology and data lifecycle; however, decide them explicitly before release. In rolling deployments, running two versions concurrently is often critical.

## 15. Thought Exercises

**Scenario 1.** `User` has an immutable `id` and `displayName`. A later version adds `avatarUrl`. Goal: one ID maps to one unique user in the cache. Should `avatarUrl` automatically be added to `equals`/`hashCode`?

**Hint:** No, if business equality is defined by ID. Descriptive fields can change frequently; ensure the contract uses an ID that is truly unique within its scope (for example `tenantId + id`).

**Scenario 2.** `record Price(String currency, long minorUnits)` is extended with `taxCategory`, and the system suddenly keeps more price keys in a `HashMap`. What must be checked first?

**Hint:** `record` generates equality/hash from its components; verify whether `taxCategory` genuinely makes two price values distinct in the business domain. If yes, the distinction is right and consumers/caches need updating; if not, redesign the value/key representation or implement equality deliberately.

**Scenario 3.** A new version of a `Serializable` class adds `region`. Reading an old file gives `region == null`, and then `equals` calls `region.equals(...)` and throws `NullPointerException`. Which compatibility layer failed?

**Hint:** Even though the read step succeeded at the serialization level, **object invariants and behavioral compatibility** were not protected. Valid migration/defaults are needed before using the object in logic.

**Scenario 4.** Class `Task` bases `hashCode` on `status`, and `status` changes from `QUEUED` to `DONE` while the task is a `HashMap` key. Can this design be kept?

**Hint:** Unsafe if the same entry must be looked up again. Design a stable key (`taskId`) or index by status with a consistent remove–update–reinsert workflow.

**Remember:** when adding fields or changing class versions, answer all four questions together: **(1) what makes objects equal, (2) are keys stable in collections, (3) can old callers still use the API/bytecode, and (4) how is old/new data converted**. These are contract decisions that must be actively tested and communicated.