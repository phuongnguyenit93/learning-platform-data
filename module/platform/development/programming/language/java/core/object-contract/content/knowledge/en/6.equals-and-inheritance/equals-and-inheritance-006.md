# `final` Classes or `final equals()` Methods to Restrict Contract Changes

## 1. The Problem When `equals` Meets Inheritance

`Object.equals(Object)` represents logical equality, not merely comparing memory addresses. The contract requires **reflexivity** (`a.equals(a)`), **symmetry** (`a.equals(b) == b.equals(a)`), **transitivity** (if `a=b` and `b=c` then `a=c`), **consistency** when comparison data does not change, and `a.equals(null) == false`. Furthermore, if `a.equals(b)` is true then `a.hashCode() == b.hashCode()` must hold. Two equal hashes do **not** require two objects to be equal.

When a parent class defines `equals` using a field like `id` while a subclass adds a `department` condition, the two calls `parent.equals(child)` and `child.equals(parent)` can differ. For instance, the parent accepts any object with the same `id`, while the subclass accepts only the subclass type itself with the same `department`. The result is **broken symmetry**; multiple objects can also break transitivity.

`HashSet` and `HashMap` depend on the `equals`/`hashCode` contract for deduplication, lookup, and removal. If the contract is broken, equivalent keys may not be found or the collection may contain “duplicate” elements unpredictably. Two strategies to prevent subclasses from arbitrarily altering the equality relation are **locking the entire type with `final class`** and **locking only equality with `final equals(Object)`**.

## 2. `final class`: Disallowing Inheritance

When a class is declared `final`, Java forbids any other class from `extends`-ing it. There are no subclasses to override `equals`, alter `hashCode`, or add identity components that the original class did not anticipate. This is a suitable choice for **value objects**, IDs, cache keys, and data types that do not need a subclass hierarchy.

Example in `AccountId.java`:

```java
import java.util.Objects;

public final class AccountId {
    private final String value;

    public AccountId(String value) {
        this.value = Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof AccountId that
                    && value.equals(that.value));
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
```

This class compiles on Java 17+ with `javac --release 17 AccountId.java`. Two `AccountId` instances with the same `value` will be equal and share the same hash. The `value` field is an immutable `String` declared `final`; the constructor rejects `null`. `final class` forbids `class ChildId extends AccountId` at compile time.

Because the class itself cannot be inherited, it is usually unnecessary to mark `equals` and `hashCode` individually as `final` to block overriding. However, **`final class` does not automatically make the logic right**: a developer can still write an asymmetric `equals` or an incompatible hash, or use a mutable field in the comparison.

Records in Java 17 are also **implicitly `final`** types. For instance, `record AccountId(String value) {}` generates `equals`/`hashCode` from the `value` component. However, a record containing a mutable object does not automatically have deep immutability; array components are compared by reference rather than automatically comparing elements one by one.

## 3. `final equals(Object)`: Still Allowing Subclasses, Keeping One Shared Definition

When subclasses are needed to extend behavior yet all classes must share the same identity, the parent class can lock `equals(Object)`:

```java
import java.util.Objects;

public class Member {
    private final String memberId;

    protected Member(String memberId) {
        this.memberId = Objects.requireNonNull(memberId);
    }

    @Override
    public final boolean equals(Object other) {
        return this == other
                || (other instanceof Member that
                    && memberId.equals(that.memberId));
    }

    @Override
    public final int hashCode() {
        return memberId.hashCode();
    }
}
```

This is a standalone illustrative class in `Member.java`. `Member` is not `final`, so subclasses are allowed to add fields and methods; however, they **cannot override** `equals(Object)` or `hashCode()`. Every `Member` with the same `memberId` is equal, even if they belong to two different subclasses. This rule is **valid only when the domain genuinely treats the same ID as the same identity across all subtypes**.

### Why Care About `hashCode()`?

Locking `equals` while allowing subclasses to override `hashCode` is not safe enough. A subclass could compute its hash from `memberId` *and* `level`, while `equals` still looks only at `memberId`. Then two equal objects would have different hash codes. Therefore, if the parent class owns a unified equality policy, it should generally declare **both `final equals(Object)` and `final hashCode()`**, and implement them using the same immutable set of attributes.

If a subclass writes:

```java
// Intentionally does not compile: Member.equals(Object) is final.
class BadMember extends Member {
    BadMember(String id) {
        super(id);
    }

    @Override
    public boolean equals(Object other) {
        return false;
    }
}
```

the compiler rejects the override. Note that `equals(BadMember)` is merely an **overload**, not an override of `equals(Object)`. Collections in Java rely on the `equals(Object)` signature; do not use overloading to try to change the notion of equality because the call outcome can depend on the static type of the parameter.

## 4. Runnable Java 17+ Demo

Create `FinalEqualityDemo.java`. The two examples use the two different locking approaches; the output shows how they behave with `HashSet`.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class FinalEqualityDemo {
    static final class AccountKey {
        private final String id;

        AccountKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof AccountKey that
                        && id.equals(that.id));
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    static class Member {
        private final String id;

        protected Member(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public final boolean equals(Object other) {
            return this == other
                    || (other instanceof Member that
                        && id.equals(that.id));
        }

        @Override
        public final int hashCode() {
            return id.hashCode();
        }
    }

    static final class BasicMember extends Member {
        BasicMember(String id) {
            super(id);
        }
    }

    static final class PremiumMember extends Member {
        private final int rewardPoints;

        PremiumMember(String id, int rewardPoints) {
            super(id);
            this.rewardPoints = rewardPoints;
        }
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey("A-7");
        AccountKey b = new AccountKey("A-7");
        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        System.out.println("key equals: " + a.equals(b));
        System.out.println("key set size: " + keys.size());

        Member basic = new BasicMember("M-9");
        Member premium = new PremiumMember("M-9", 100);
        Set<Member> members = new HashSet<>();
        members.add(basic);
        members.add(premium);
        System.out.println("member forward: " + basic.equals(premium));
        System.out.println("member reverse: " + premium.equals(basic));
        System.out.println("member hash match: "
                + (basic.hashCode() == premium.hashCode()));
        System.out.println("member set size: " + members.size());
    }
}
```

Compile and run commands:

```bash
javac --release 17 FinalEqualityDemo.java
java FinalEqualityDemo
```

Stdout:

```text
key equals: true
key set size: 1
member forward: true
member reverse: true
member hash match: true
member set size: 1
```

The two `AccountKey` keys are equal, so `HashSet` stores one element. `BasicMember` and `PremiumMember` are also equal in both directions because `Member` enforces a common key policy. The `rewardPoints` attribute **does not participate in identity**, even though it is a field of `PremiumMember`; that is a domain-model choice, not a property that `final` infers automatically.

If the domain requires a `PremiumMember` to differ from a `BasicMember` even when their IDs match, locking `equals` in the parent solely on `id` is **inappropriate**. You should not try to patch the consequence in `HashSet`: you must adjust the identity model.

## 5. `instanceof` or `getClass()` Inside a `final equals` Method?

The two type-checking choices lead to different meanings:

| Check | Interpretation of Equality | Note |
| --- | --- | --- |
| `other instanceof Member` | A parent instance can equal a subclass instance if the shared key matches; two different subtypes can also equal each other | Use only if the ID carries the same meaning across subtypes |
| `other != null && getClass() == other.getClass()` | Only instances of the **exact same runtime class** are equal | Different subtypes are not equal; subtype-specific fields still cannot be added to the locked `equals` |

For example, with a `final equals` based on `getClass()`, `Member` will not equal `PremiumMember`. Yet two `PremiumMember` objects with the same ID and different `rewardPoints` can still be considered equal because the parent method sees only `id`. The subclass cannot override to add reward points to equality.

Some frameworks create proxies via subclasses whose runtime class differs from the original domain type. Therefore, choosing `getClass()` requires considering proxy architecture and actual identity rules. For a class that is already `final`, `instanceof` or `getClass` usually makes no difference because subclassing is impossible.

## 6. Comparing the Two Strategies

| Criterion | `final class` | `final equals` on an Inheritable Class |
| --- | --- | --- |
| Are subclasses allowed? | No | Yes |
| Can subclasses alter `equals`? | No subclasses | Cannot override |
| Can subclasses add data/behavior? | No | Yes |
| Can subclasses redefine their own identity? | Not applicable | No, unless changing the parent class design |
| Can `hashCode` be overridden? | No subclasses | Must declare `final hashCode()` to forbid overriding |
| Blocks all contract bugs? | No | No |
| Best suited for | Value objects, keys, standalone identifiers | Hierarchies sharing a single common identity definition |

`final class` restricts all inheritance, which is stronger yet also reduces type extensibility. `final equals` is narrower: it continues allowing polymorphism while locking one specific policy. In the second case, you must ensure no remaining overridable method mutates the data determining identity over time.

## 7. Common Reasoning Mistakes

**Assuming final means immutable.** A `final` class can still hold a mutable `List` or array; a `final` field only fixes the reference, not the contents. If the hash depends on mutable contents, an object used as a `HashMap` key can become unfindable after mutation.

**Locking equality too early.** If a subclass needs to use its own attribute in the identity criterion, `final equals` in the parent will prevent that. In that case, either redefine the shared key so it captures full identity at construction time, or split into separate `final` value types. Composition/interfaces can be used to share behavior without tying equality to an inheritance tree.

**Locking only equals and forgetting hashCode.** A subclass can override hash, leading to two equal objects with different hash codes. Even without overrides, any change in the base method must preserve the mandatory relation between the two methods.

**Assuming all subclasses must be unequal.** A `PremiumMember` and a `BasicMember` may be the same member with one ID; membership tier or reward points are state, not necessarily identity. Conversely, if two types represent two different kinds of entities, having the same ID may not be enough. Equality decisions must follow the domain data.

**Assuming every framework accepts final.** Some ORM/proxy libraries need to subclass or override methods to provide functionality; `final class`/`final method` can interfere. Do not choose an equality formula for an entity based on value-object examples without analyzing identity and framework mechanics.

**Using `sealed` as an automatic replacement.** A `sealed class` only restricts **which subclasses are allowed to inherit**; they can still override `equals` if the method is not `final`. Sealed helps control inheritance scope, but does not automatically guarantee symmetry or transitivity.

## 8. Required Tests Before Locking the Contract

Use at least three objects representing the same key, a different key, and subtypes; check:

1. `a.equals(a)` is true; `a.equals(null)` is false.
2. `a.equals(b)` and `b.equals(a)` match, especially for parent–child pairs.
3. If `a.equals(b)` and `b.equals(c)` then `a.equals(c)`.
4. If `a.equals(b)` then `a.hashCode()==b.hashCode()`. Do **not** test the converse because hash collisions are valid.
5. When relevant state does not change, `equals`/`hashCode` results remain stable across multiple calls.
6. `HashSet` deduplicates by exact identity; `HashMap.get` retrieves values using a new but logically equal object.
7. Identity data remains stable after inserting the object into collections; audit mutable fields and reference aliases.
8. If locking `equals` in the parent, test all subtype pairs with matching/differing IDs; confirm the genuinely intended semantics, and verify `hashCode` has no remaining override path that causes inconsistency.

With `TreeSet`/`TreeMap`, you must also test `Comparable`/`Comparator` and the meaning of `compare(a,b)==0`; `final equals` does not automatically constrain comparators.

**Conclusion:** `final class` locks **the entire inheritance path**, suitable for data types that do not need subclasses. `final equals(Object)` locks **a shared equality definition for a hierarchy**, and should go together with `final hashCode()`. Both are useful only when the identity criterion is right, keys are sufficiently stable, and all involved objects are tested against the Java contract.