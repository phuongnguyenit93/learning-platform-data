# Two `equals()` Objects Must Have the Same Hash Code

## 1. The Mandatory Rule of the `hashCode()` Contract

In Java, if two objects are considered equal according to `equals()`, then **their `hashCode()` values must be equal**. For two non-`null` references `a` and `b`:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
~~~

The `=>` symbol denotes logical implication, not a Java operator. This is a rule of the **`Object.hashCode()` contract**. It applies when two references point to the same object, and more importantly, when two **distinct** objects are considered equal in data by their class.

**Do not reverse the rule:**

~~~text
a.hashCode() == b.hashCode()  does not imply  a.equals(b) == true
~~~

Two objects can receive the same hash code while `equals()` returns `false`. This is called a **hash collision** and is completely valid. `hashCode()` returns a 32-bit `int`, which cannot assign a unique code to every value and object that could possibly exist.

Three cases to distinguish:

- `a.equals(b) == true`: the two hash codes **must** be equal.
- `a.equals(b) == false`: the hash codes may be equal or different.
- `a == b`: two variables point to the same instance; if the state determining `equals()` does not change, calls to `hashCode()` must be consistent.

For example, if a `CustomerKey` class identifies two customers by the same `customerId`, two separate `new CustomerKey("C1")` objects must return the same hash code when `equals()` returns `true`. They do not have to be the same object in memory.

## 2. Three Parts of the `Object.hashCode()` Contract

1. **Consistency within a single execution.** Calling `hashCode()` multiple times on the same object must yield the same result as long as no information used in `equals()` comparisons changes. There is no guarantee that the hash code remains the same across two executions of the application.
2. **Equal implies same hash code.** If `a.equals(b)` is `true`, calling `a.hashCode()` and `b.hashCode()` must return the same `int`.
3. **Unequal objects are allowed to share a hash code.** It is not required that two objects that are unequal according to `equals()` have different hash codes. A well-distributed hash function helps reduce collisions and improve performance, but uniqueness is not a contract requirement.

In addition, `equals()` must obey **reflexivity** (`a.equals(a)`), **symmetry** (if `a.equals(b)` then `b.equals(a)`), **transitivity**, **consistency**, and `a.equals(null)` returning `false` for non-`null` `a`. Hash codes only have stable meaning when the definition of "two equal objects" is also consistent.

> Practical rule: **If you override `equals()` to compare by value, you must override `hashCode()` accordingly.** Base both methods on the same notion of "equality."

## 3. Why Do Hash Structures Depend on This Rule?

`HashMap` and `HashSet` use hash codes to direct where to look up keys or elements, then check equality when needed to distinguish candidates. You can picture it as:

1. Insert object `a`: the structure computes `a.hashCode()` and picks a candidate storage area.
2. Look up using object `b` where `b.equals(a) == true`: the structure computes `b.hashCode()` to find the right place containing matching candidates.
3. If the hash codes of `a` and `b` are incompatible, the lookup may go to the wrong area and never compare the two objects with each other, even though `equals()` says they are equal.
4. If the two hash codes are equal while `equals()` differs, the structure can still keep both keys. This is a normal collision situation.

That is the conceptual model; `HashMap` may process or mix bits of the hash code and use different internal structures. The key's contract matters more than implementation details.

Violating the equal ⇒ same hash code rule can cause `HashSet.contains(b)` to return `false` even though an equivalent `a` was added, or `HashMap.get(b)` to fail to find the value stored under `a`. You should not claim a specific lookup is guaranteed to fail on every JVM, because bucket layout and chance collisions affect the symptoms; the core bug is **failing to uphold the contract**.

## 4. A Compilable and Runnable Java 17+ Example

The `AccountId` class in the example has an immutable `value` field. Both `equals()` and `hashCode()` use the same value, so two objects with different references but the same account are recognized as one logical key.

Create the file `HashContractDemo.java`:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashContractDemo {
    static final class AccountId {
        private final String value;

        AccountId(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof AccountId id
                        && value.equals(id.value));
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }
    }

    public static void main(String[] args) {
        AccountId first = new AccountId("ACC-100");
        AccountId equivalent = new AccountId("ACC-100");
        AccountId different = new AccountId("ACC-200");

        System.out.println("same reference: "
                + (first == equivalent));
        System.out.println("equal values: "
                + first.equals(equivalent));
        System.out.println("equal objects have same hash: "
                + (first.hashCode() == equivalent.hashCode()));
        System.out.println("different values: "
                + first.equals(different));

        Set<AccountId> ids = new HashSet<>();
        System.out.println("add first: " + ids.add(first));
        System.out.println("contains equivalent: "
                + ids.contains(equivalent));
        System.out.println("add equivalent: "
                + ids.add(equivalent));
        System.out.println("set size: " + ids.size());

        Map<AccountId, String> owners = new HashMap<>();
        owners.put(first, "Linh");
        System.out.println("lookup with equivalent: "
                + owners.get(equivalent));

        System.out.println("Aa equals BB: " + "Aa".equals("BB"));
        System.out.println("Aa and BB same hash: "
                + ("Aa".hashCode() == "BB".hashCode()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac HashContractDemo.java
java HashContractDemo
~~~

**Deterministic output:**

~~~text
same reference: false
equal values: true
equal objects have same hash: true
different values: false
add first: true
contains equivalent: true
add equivalent: false
set size: 1
lookup with equivalent: Linh
Aa equals BB: false
Aa and BB same hash: true
~~~

**Output explanation:**

- `first` and `equivalent` are two objects from two separate `new` expressions, so `first == equivalent` is `false`. They carry the same `value`, so `first.equals(equivalent)` is `true`.
- Both `hashCode()` calls use the same string value `"ACC-100"`; their hash results must be equal. There is no need to print the specific number to check the contract.
- `HashSet` adds `first` successfully, finds the equivalent key with `contains(equivalent)`, and refuses to add the equivalent key again. The size stays `1`.
- `HashMap` retrieves `"Linh"` using a key object with a different reference but the same logical value.
- `"Aa"` and `"BB"` are not equal according to `String.equals()`, yet `String.hashCode()` for both is `2112`. This is an allowed collision, proving you must not infer `equals() == true` solely from equal hashes.

## 5. Common Mistake: Overriding `equals()` but Forgetting `hashCode()`

The following **illustrative snippet** overrides only `equals()`; it is not a standalone program:

~~~java
final class BrokenKey {
    private final String code;

    BrokenKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof BrokenKey key
                    && java.util.Objects.equals(code, key.code));
    }

    // Missing hashCode(): still inherits Object.hashCode().
}
~~~

Two distinct `new BrokenKey("A")` objects have `equals() == true`, but the default `Object.hashCode()` is tied to identity, so there is **no guarantee** their hash codes are equal. Therefore this class does not satisfy the contract required by hash-based collections.

You cannot assume by default that every pair of distinct objects always has different identity hash codes; collisions can still happen. The bug is that the implementation **fails to guarantee** the rule "equal implies equal hash codes."

The fix is to also override `hashCode()` to use the same `code` field:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(code);
}
~~~

This is an **additional method for the `BrokenKey` class**, not standalone runnable code. `Objects.hashCode(code)` returns `0` if `code` is `null`, and uses `code.hashCode()` if non-`null`. This mechanism is compatible with `Objects.equals(code, key.code)` in the `equals()` method above.

## 6. Which Fields Should Be Used to Write `hashCode()`?

Start from the definition of `equals()`. For example, suppose a key object is identified by the **pair** `tenantId` and `orderNumber`. A compatible design typically compares those exact two fields in `equals()` and combines them in `hashCode()`.

Here is an **illustrative pair of methods**, assuming they belong to an `OrderKey` class with the two fields mentioned above and `java.util.Objects` imported:

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof OrderKey key
                && Objects.equals(tenantId, key.tenantId)
                && Objects.equals(orderNumber, key.orderNumber));
}

@Override
public int hashCode() {
    return Objects.hash(tenantId, orderNumber);
}
~~~

Because two keys with the same `tenantId` and `orderNumber` will generate the same hash code, the contract condition is met. `Objects.hash(...)` **does not guarantee** distinct codes for every pair of values; collisions remain valid.

**An important nuance:** Omitting a field from `hashCode()` does not automatically violate the contract. If `equals()` compares two fields and `hashCode()` returns the hash code of only the first field, every equal pair still has the same first field and therefore the same hash code. The issue here is **poor hash distribution**, which can degrade performance. Conversely, if `hashCode()` depends on an independently varying field that `equals()` ignores, two equal objects can produce different hash codes: that is a correctness bug against the contract.

### Caution with Mutable Objects

Even when `equals()` and `hashCode()` use the right fields, mutating those fields while the object is serving as a `HashMap` key or `HashSet` element can still cause lookup failures. The key was stored under its old hash code; after its value changes, searching by the new hash code may fail to find it.

Therefore, prefer **immutable keys**: `final` fields whose internal data also cannot be mutated in a way that affects `equals()`. A reference field declared `final` that points to a mutable data structure still needs to be examined.

### Built-in Data Types

- `String`, `Integer`, `Long`, and many standard value types already implement `equals()`/`hashCode()` consistently.
- `record` in modern Java automatically generates `equals()` and `hashCode()` based on its components; be careful if a component holds mutable data.
- Arrays in Java inherit identity-based comparison from `Object` by default. If you want content-based array comparison, use the corresponding pair `Arrays.equals(...)` and `Arrays.hashCode(...)`; for nested arrays, use `Arrays.deepEquals(...)` and `Arrays.deepHashCode(...)`.
- For classes using inheritance, designing `equals()` between superclass and subclass must preserve symmetry and transitivity. Breaking this can also affect the `hashCode()` contract.

## 7. Distinguishing Easily Confused Statements

| Statement | Verdict | Explanation |
| --- | --- | --- |
| `a.equals(b)` is true ⇒ hash codes are equal | **Mandatory** | `Object.hashCode()` contract |
| Hash codes are equal ⇒ `a.equals(b)` is true | **False** | Hash collisions are allowed |
| `a.equals(b)` is false ⇒ hash codes must differ | **False** | There is no such requirement |
| `a == b` ⇒ hash codes are consistent if relevant data does not change | **True** | Same object |
| `a.equals(b)` is true ⇒ `a == b` | **False** | Two separate instances can be equal by value |
| Any `hashCode()` returning a constant violates the contract | **False** | The contract can still hold, though with many collisions |
| Overriding `equals()` by value while keeping `Object.hashCode()` is always safe | **False** | Does not guarantee equal hash codes for two equivalent instances |
| Identity hash code `System.identityHashCode()` must match for two `equals()` objects | **False** | It reflects identity, not value equality |

A `hashCode()` method that always returns `0` for every object can satisfy **equal ⇒ same hash code**, but will distribute very poorly and degrade hash table performance. It is a complex, well-distributed hash that is incompatible with `equals()` that actually violates the contract.

## 8. Implementation and Testing Checklist

1. Clearly define "equality": which attributes is it based on, and can two distinct instances be equivalent?
2. Implement `equals()` to be reflexive, symmetric, transitive, consistent, and handle `null` properly.
3. Implement `hashCode()` from values compatible with `equals()`. For multiple fields, consider `Objects.hash(...)` or controlled hash combination.
4. Create two instances that have **different references but are equal according to `equals()`**, and verify their hash codes match.
5. Test the case of two distinct values with matching hash codes; the hash structure must still distinguish them using `equals()`.
6. Test `HashSet.add`/`contains` and `HashMap.put`/`get` using equivalent key instances.
7. Keep the fields that determine `equals()`/`hashCode()` stable for as long as the key resides in a hash structure.

## 9. Self-Check

**Question 1.** Two distinct `new String("java")` instances have `equals()` returning `true`. Must their hash codes be equal?

**Answer:** Yes. `String.hashCode()` is based on string contents. The two objects can still have different references.

**Question 2.** `"Aa"` and `"BB"` share the same hash code. Does Java violate the contract?

**Answer:** No. The two strings are not equal, so having matching hash codes is completely valid.

**Question 3.** If `equals()` compares only `id` while `hashCode()` uses a randomly generated code per instance, what is wrong?

**Answer:** Two instances with the same `id` can have `equals() == true` yet return different hash codes, violating the contract and potentially causing hash-based lookups to fail.

**Question 4.** Are two distinct keys with equal hash codes automatically merged into one by `HashSet`?

**Answer:** No. The hash code directs the lookup; the structure still checks equality to distinguish colliding keys.

**Takeaway:** Equal `equals()` **requires** equal `hashCode()`. Equal hash codes **do not prove** two objects are equal. Designing both methods consistently is essential for using `HashMap` and `HashSet` properly.
