# Distinguishing Mandatory Requirements, Conventions, and Implementation Details in Java Object Contracts

## 1. Reading a Java Rule at the Right Level

When saying that a Java object has a "contract" (behavioral contract), we need to distinguish three levels:

1. **Mandatory requirement (contract/API specification):** A condition that a published method or data type must obey so other code can rely on it. Violating it leads to semantically incorrect behavior even though the program still compiles.
2. **Convention or recommendation (convention/best practice):** A way of writing code that makes an API easier to understand, easier to maintain, less error-prone, or more efficient. In some cases, violating a convention does not break Java's contract.
3. **Implementation detail:** An internal choice inside a class, library, or JDK version. It may be observable in a specific environment, but it is not a general guarantee for application code to depend on.

In the `object-contract` topic, the starting point is `java.lang.Object`: every class inherits methods such as `equals(Object)`, `hashCode()`, and `toString()`. These three methods carry different levels of obligation. Memorizing an implementation example without distinguishing levels easily leads to wrong conclusions, especially when objects are placed into a `HashMap`, `HashSet`, or third-party libraries.

A helpful self-check question is: **"If I replace the implementation while preserving all behavior promised in the documentation, will the caller's program still be correct?"** If yes, the replaced part is usually an implementation detail.

## 2. Mandatory Requirements of `equals(Object)`

When a class defines the concept of "two equal values" via `equals`, that relation must have the following properties:

| Property | Requirement | Example |
| --- | --- | --- |
| Reflexive | For non-`null` objects, `x.equals(x)` is `true`. | A `UserId("u1")` equals itself. |
| Symmetric | For non-`null` `x` and `y`, `x.equals(y)` and `y.equals(x)` must return the same result. | If ID A equals ID B, the reverse is also equal. |
| Transitive | If `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`. | Three objects representing the same ID must be consistent. |
| Consistent | Repeated calls return the same result when the information used for comparison has not changed. | If the ID field does not change, the result does not change on its own. |
| Comparison with `null` | For non-`null` `x`, `x.equals(null)` is `false`. | No valid object equals `null`. |

This is a **behavioral contract**, not a coding-style suggestion. `Object.equals` defaults to reference identity: two references pointing to the same object are equal. A class may override it to use *value equality* (equality by value), provided it preserves all the properties above.

Distinguish the two comparisons:

- `a == b` checks whether two reference variables point to the same object.
- `a.equals(b)` calls the class's definition of "equal"; it may match `==` or compare data.

**Note on inheritance:** Using `instanceof` or `getClass()` inside `equals` is a **design decision**, with no universal rule forcing every class to choose one approach. If a class is open to inheritance, both symmetry and transitivity between superclass and subclass objects must be considered. A `final` class with immutable value fields generally makes defining equality easier to keep safe.

## 3. The `hashCode()` Contract Tightly Coupled to `equals()`

`hashCode` has three important points in Java's documentation:

1. Within a single execution of an application, invoking `hashCode()` multiple times on an object must return the same integer **provided no information used in `equals` comparisons on that object is modified**. There is no promise that hash codes remain identical across two separate program runs.
2. **If `a.equals(b) == true`, then `a.hashCode() == b.hashCode()` is mandatory.** Therefore, when overriding `equals` to define value equality, you normally must override `hashCode` accordingly.
3. If `a.equals(b) == false`, it is **not required** for the two hash codes to be different. Hash *collisions* are valid.

Logical form to remember:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

The converse is **not true in general**: having the same hash code does not mean two objects are equal.

Why is this rule needed? Hash-based data structures such as `HashSet` and `HashMap` use hash codes to organize element lookup and then use equality comparisons to distinguish matching keys. If two equal keys produce different hash codes, add/search/remove operations may yield wrong results compared to expectations for equal keys.

Using a "nice" hash algorithm or a `31 * result + fieldHash` formula is an **implementation convention**, not a mandatory contract requirement. Even `hashCode() { return 1; }` satisfies the "equal objects have the same hash" condition for every pair of objects, though it usually degrades performance significantly due to excessive collisions.

## 4. Runnable Java 17 Example: Preserving the Contract Correctly

The following example considers two `UserId` instances equal when they have the same ID string, regardless of whether they are two separately created objects.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectContractDemo {
    static final class UserId {
        private final String value;

        UserId(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof UserId that)) {
                return false;
            }
            return value.equals(that.value);
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }

        @Override
        public String toString() {
            return "UserId[" + value + "]";
        }
    }

    public static void main(String[] args) {
        UserId a = new UserId("U-42");
        UserId b = new UserId("U-42");
        Set<UserId> ids = new HashSet<>();
        ids.add(a);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(ids.contains(b));
        System.out.println(a);
    }
}
```

Save the file `ObjectContractDemo.java`, then run:

```bash
javac ObjectContractDemo.java
java ObjectContractDemo
```

Standard output:

```text
false
true
true
true
UserId[U-42]
```

Line-by-line explanation:

1. `false`: `a` and `b` are created by two `new` calls, so they are two different objects.
2. `true`: the `equals` method compares `value`, not reference addresses.
3. `true`: equal `value` strings produce the same hash code.
4. `true`: `HashSet` recognizes the equal-valued key thanks to the consistent `hashCode`/`equals` pair.
5. `UserId[U-42]`: this is the format **chosen by the class** for `toString`, not a mandatory Java output pattern for all objects.

This class is `final`, the `value` field is `final`, and there is no setter, so the value used in equality stays stable after initialization. That is advantageous when using `UserId` as a key in hash-based data structures.

## 5. Same Topic, Three Different Levels

| Statement | Classification | Reason |
| --- | --- | --- |
| "`equals` must be reflexive, symmetric, transitive, consistent, and return `false` when compared to `null`." | **Mandatory** | It is the published contract of `Object.equals`. |
| "Two objects equal according to `equals` must have the same `hashCode`." | **Mandatory** | It is the constraint between the two methods. |
| "Two unequal objects must have two different hash codes." | **False** | Java allows hash collisions. |
| "Every class must override `equals`, `hashCode`, and `toString`." | **False** | `Object`'s default behavior can be kept if it fits the problem. |
| "A class with value equality should avoid mutating fields used to compute equality while acting as a hash key." | **Very important recommendation** | Keeps lookup reliable; mutating keys breaks collection usage. |
| "Use `Objects.equals`, `Objects.hash` to write clear code." | **Convention/choice** | They are utilities, not the only contract-compliant way to write it. |
| "Pick the number 31 to combine fields when computing a hash." | **Implementation choice** | Common, but not required by the contract. |
| "The iteration order of a `HashMap` is always insertion order." | **False** | There is no iteration order guarantee like `LinkedHashMap`. |
| "`hashCode` values must stay identical across JVM restarts." | **False** | The contract does not promise stability across runs. |
| "`toString` should be readable, helpful for logging/debugging, and not leak sensitive information." | **Design convention** | The exact format is decided by the class/API. |
| "The VM must generate identity hashes from the object's RAM address." | **False** | How identity hashes are generated is an implementation detail, not a Java commitment of that sort. |

Key takeaway: a statement that looks "very common in Java code" is not necessarily an official constraint. To evaluate accurately, read the API's commitments, then distinguish them from design guidelines and specific algorithms.

## 6. `toString()`: Descriptive Purpose and Specific Format

The `Object.toString()` documentation describes its purpose as providing a concise, informative representation for human readers, and encourages classes to override it to supply appropriate details. Default `Object.toString` produces a string consisting of the class name, `@`, and the hash code in hexadecimal. However, **there is no universal contract** forcing every class overriding `toString` to keep that form or output all fields in a single common format.

For example, both styles below can be reasonable implementation choices, depending on the API:

`UserId[U-42]`

`UserId(value=U-42)`

Practical lessons:

- Use `toString` for diagnostics and reading logs, but do not treat the default representation as a stable data-exchange format.
- Do not parse a third-party library's `toString` output for business rules, unless the library itself **explicitly publishes** that format as part of its API.
- Avoid putting passwords, tokens, secret keys, or sensitive personal data into `toString` because logs may be stored long-term.
- If the system needs a machine-readable representation, use a separately defined serialization contract, such as an explicit JSON schema.

A class can successfully persist business data even without overriding `toString`. Therefore, "must always override `toString`" is an overstatement.

## 7. Failure Cases: Contract Violations vs. Convention Violations

### 7.1. Genuine Violation: Equality by Value, Hash by Identity

Suppose a class defines `equals` based on `id`, yet writes:

```java
@Override
public int hashCode() {
    return System.identityHashCode(this);
}
```

This is an **illustrative snippet to place inside a class**, not a standalone program. `System.identityHashCode` returns a hash code based on object identity without using the overridden equality. Two different instances can share the same `id` (and therefore `equals` returns `true`) while having different identity hashes. This design **fails to guarantee** the requirement "equal `equals` implies equal hashes". You cannot excuse it by saying "the code runs" to claim it obeys the contract.

The fix is to compute the hash from the same fields that determine equality, such as `return id.hashCode();` if `id` is non-`null`. You must also ensure every field used in `equals` is handled consistently when determining `hashCode`; not every field has to be used in the hash, provided the condition that two equal values produce equal hashes is preserved.

### 7.2. Not a Contract Violation: Many Values Sharing One Hash

```java
@Override
public int hashCode() {
    return 1;
}
```

This is also just an illustrative method placed inside a class. If `equals` is correct and every object returns the hash code `1`, the compatibility rule still holds. The issue here is **performance**, not validity of the equality contract. To improve hash distribution, another algorithm can be chosen as long as the mandatory constraint is preserved.

### 7.3. Usage Bug: Mutating a Key After Adding It to `HashSet`/`HashMap`

If an object changes a field participating in `equals` and `hashCode` after being used as a key, its previously organized lookup slot may no longer match the new hash code. `contains` or `get` may fail to find a key the developer thought was still there.

This is why you should use *immutable* key objects, or at least keep fields participating in equality unchanged while the key remains in the collection. Distinguish carefully: hash consistency is required by Java **when information used for comparison has not changed**; Java does not forbid objects from having mutable state.

### 7.4. Reasoning Error: Confusing Equal Hashes With Equality

`a.hashCode() == b.hashCode()` only says two integer results match. It **does not prove** `a.equals(b)`. In business code, never use a hash code as a unique identifier key or a replacement for full value comparison unless the risk of hash collision is handled.

## 8. Boundaries Commonly Confused With Object Contracts

**`Comparable.compareTo` and `equals`:** `compareTo` belongs to the `Comparable` interface, not `Object`. Natural ordering should be designed to be consistent with `equals` when possible—meaning `compareTo(x) == 0` corresponds to equality—especially when intending to use `TreeSet`/`TreeMap`. But this is a **recommendation** regarding consistency with equals, not a universal requirement of `Object.equals`. For example, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, yet `equals` is `false` because the two representations have different scales. Sorted collections can treat two elements as the same key based on the comparator even if their `equals` differs.

**Arrays inside objects:** Java arrays do not automatically compare element contents via `Object.equals`; `Objects.equals(array1, array2)` still uses array equality (typically by reference). If desired equality depends on array contents, choose `Arrays.equals`/`Arrays.deepEquals` according to the data structure, and use corresponding hash computations such as `Arrays.hashCode`/`Arrays.deepHashCode`. Consistency of **result** is the requirement, while the specific helper API is an implementation choice.

**`record`:** In Java 17, `record UserId(String value) {}` gets `equals`, `hashCode`, and `toString` generated by the compiler from its record components. That is a way to reduce boilerplate for suitable data types; it does not turn every Java class into a record, nor does it force ordinary classes to use the exact same source-code algorithm.

**Internal collection structure:** The API guarantees the semantics of public operations as documented. Bucket counts, hash-spreading techniques, resize timing, or how the JVM stores objects can vary across implementations. Do not infer your program's contract from an internal `HashMap` diagram of a specific JDK release.

## 9. How to Determine Obligation Level Yourself When Reading Documentation

When encountering a claim about Java objects, follow this sequence:

1. **Identify where the rule is published.** Is it the Javadoc of `Object`, `Comparable`, a specific library class, or just a blog post/example code snippet?
2. **Look for normative language.** "Must/shall", specified properties, and accompanying conditions signal a contract; "recommended", "typically", "generally" are usually advice or common descriptions. Do not rely solely on one word while ignoring context.
3. **Construct counterexamples.** If two unequal objects share the same hash, does Java fail? No. If two equal objects have different hashes, is that wrong? Yes.
4. **See who can change that part.** If changing a hash algorithm, bucket ordering, or `toString` format keeps the API within its commitments, it is usually an implementation choice. If a change causes `equals` to lose symmetry, it is a contract violation.
5. **Check usage conditions.** Does the code run on Java 17, a specific library, a mutable or immutable type? Which conditions are assumptions of an example rather than universal rules?

### Practice Questions

**Question 1.** Two objects share the same hash, yet `equals` returns `false`. Does this violate the `Object` contract?

**Answer:** No. Hash collisions are allowed; only the direction equal `equals` ⇒ equal hash is mandatory.

**Question 2.** A class overrides `equals` by customer ID while leaving `hashCode` inherited from `Object`. Why should this be reviewed?

**Answer:** Two different instances can be equal by customer ID, yet the default hash is not designed to match the new equality. This risks violating the mandatory constraint.

**Question 3.** A library changes its `toString` format in a new version, without previously publishing that format as part of its API. An application parsing `toString` breaks. Where does the primary design fault lie?

**Answer:** The application depended on an unpromised format. A structured data-retrieval API or dedicated serialization contract should be used instead.

**Question 4.** Is a `hashCode` algorithm returning the constant `1` wrong with respect to the contract?

**Answer:** No, though its distribution is poor and it can cause collections to handle far more collisions.

## 10. Takeaways

- **Mandatory:** the properties of `equals`; equal `equals` implies equal `hashCode`; consistent hash when data used in equality has not changed.
- **Good conventions:** equality/hash based on meaningful data, preferring immutable keys, readable and log-safe `toString`, considering consistency between ordering and equality.
- **Implementation details:** hash multipliers, field-combining techniques, internal hash collection structures, how the JVM generates identity hashes, `toString` format decided by the class unless explicitly promised.
- **Do not reverse-infer:** same hash does not mean `equals`; collection iteration order is not by default insertion order; code running successfully does not prove the contract is satisfied.

Reference API documentation: [`Object` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), [`Comparable` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html), and [`HashMap` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).