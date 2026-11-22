# Creating Same-Reference, Equal-Value, and Different-Value Objects to Verify the Object Contract

## 1. Goal of the Verification

When testing the `equals()` and `hashCode()` contract in Java, you need to **intentionally** create objects belonging to three different situations:

1. **Same reference:** two variables point to the exact **same object**; `a == b` is `true`.
2. **Equal values, distinct instances:** two separately created objects carrying the same properties used to define equality; `a == b` is `false`, but `a.equals(b)` must be `true` if the class has value comparison semantics.
3. **Different values:** two objects where at least one property participating in `equals()` differs; `a.equals(b)` must be `false` under the chosen equality rule.

These three situations are **test data**, not three special kinds of Java objects. The third situation should use two distinct instances; if you keep a single instance and mutate its state, the verification also introduces issues of mutability and object lifecycle.

A key distinction: Java has **object identity** and **logical equality**. The `==` operator on two reference variables checks identity; `equals()` checks according to the class's implementation. The default `Object.equals()` also compares identity until the class overrides this method.

## 2. Setting Up the Three Data Groups Properly

Suppose an identifier key `UserKey` has two properties: `id` and `version`; **both** participate in the equality comparison. Use the following values:

| Variable | Creation | Content | Relation to `first` |
| --- | --- | --- | --- |
| `first` | `new UserKey("U-01", 1)` | `("U-01", 1)` | Original object |
| `alias` | `alias = first` | Same data and same instance | `alias == first` |
| `equalValue` | `new UserKey("U-01", 1)` | `("U-01", 1)` | Different instance, equal value |
| `differentValue` | `new UserKey("U-02", 1)` | `("U-02", 1)` | Different instance, different value |
| `thirdEqual` | `new UserKey("U-01", 1)` | `("U-01", 1)` | Third equal-value instance; used to check transitivity |

Do not write `UserKey equalValue = first;` to test **equal values, distinct references**: that statement only creates an alias. Conversely, `new UserKey(...)` creates a separate instance, so comparing `==` with the old instance is `false` (while both remain live).

To avoid confusion from automatic string interning or boxed number caching, here `UserKey` instances are explicitly created with `new`. You must define `equals()` to specify precisely what "equal values" means in the business domain.

## 3. Complete, Runnable Java 17+ Program

Save the code below as `ObjectRelationsDemo.java`. The `UserKey` class is immutable: `final` fields, no setters; `equals()` checks both properties and `hashCode()` uses those exact two properties.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectRelationsDemo {
    static final class UserKey {
        private final String id;
        private final int version;

        UserKey(String id, int version) {
            this.id = Objects.requireNonNull(id, "id");
            this.version = version;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof UserKey other)) {
                return false;
            }
            return version == other.version && id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, version);
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("FAILED: " + name);
        }
        System.out.println("PASS: " + name);
    }

    public static void main(String[] args) {
        UserKey first = new UserKey("U-01", 1);
        UserKey alias = first;
        UserKey equalValue = new UserKey("U-01", 1);
        UserKey differentValue = new UserKey("U-02", 1);
        UserKey thirdEqual = new UserKey("U-01", 1);

        check("same reference", first == alias);
        check("equal values, different references",
                first != equalValue && first.equals(equalValue));
        check("different values", !first.equals(differentValue));

        check("reflexive", first.equals(first));
        check("symmetric",
                first.equals(equalValue) && equalValue.equals(first));
        check("transitive",
                first.equals(equalValue)
                        && equalValue.equals(thirdEqual)
                        && first.equals(thirdEqual));
        check("not equal to null", !first.equals(null));
        check("equal implies same hash",
                first.hashCode() == equalValue.hashCode());

        Set<UserKey> keys = new HashSet<>();
        keys.add(first);
        keys.add(alias);
        keys.add(equalValue);
        keys.add(differentValue);
        check("HashSet deduplicates equal keys", keys.size() == 2);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ObjectRelationsDemo.java
java ObjectRelationsDemo
```

Standard output:

```text
PASS: same reference
PASS: equal values, different references
PASS: different values
PASS: reflexive
PASS: symmetric
PASS: transitive
PASS: not equal to null
PASS: equal implies same hash
PASS: HashSet deduplicates equal keys
```

The `check` method throws `AssertionError` if any check fails. Therefore, the `PASS` lines are evidence that each condition is satisfied; the example **does not depend** on Java's `-ea` flag for `assert`.

### Explaining the Output

- `alias = first` copies the **reference value**, not cloning the object. Therefore `first == alias` is true and `first.equals(alias)` is also true.
- `equalValue = new UserKey("U-01", 1)` creates a different instance, so `first != equalValue`; however, the two compared properties are equal, so `equals()` is true.
- `differentValue` has a different `id`: `first.equals(differentValue)` is false. If the class checks `version` in `equals()`, changing `version` is also a way to create different-value data.
- The three objects `first`, `equalValue`, `thirdEqual` test **transitivity**: when the first object equals the second and the second equals the third, the first object must equal the third.
- Two equal objects have equal hash codes by contract; the example only asserts this implication, and **does not** require two unequal objects to have different hashes.
- `HashSet` keeps two logical values: key `("U-01", 1)` and key `("U-02", 1)`; alias references and equal-value instances do not create additional distinct elements.

## 4. Table Distinguishing `==`, `equals()`, and `hashCode()`

| Comparison pair | `==` | `equals()` | Conclusion |
| --- | --- | --- | --- |
| `first` and `alias` | `true` | `true` | Same instance; definitely same current state |
| `first` and `equalValue` | `false` | `true` | Different instances but logically equal across both properties |
| `first` and `differentValue` | `false` | `false` | Different instances and logically unequal across both properties |
| `first` and `thirdEqual` | `false` | `true` | Provides the third object to verify transitivity |
| `first` and `null` | `false` | `false` | `first.equals(null)` must return `false` |

**Note on hashing:** `equals(x, y) == true` implies `x.hashCode() == y.hashCode()`. The converse is **not true**: hash collisions are valid. Therefore, do not use `hashCode()` as an identity check or a sufficient condition for `equals()`, and do not test `first.hashCode() != differentValue.hashCode()` as a mandatory requirement.

The `==` operator can also be applied to **primitive values** such as `int`, in which case it compares primitive values; the examples in this lesson apply `==` to **reference variables**.

## 5. Full Verification of the `equals()` / `hashCode()` Contract

Testing with the three data groups above forms the foundation for the properties of `equals()`:

| Property | Condition to check | Suitable data |
| --- | --- | --- |
| Reflexive | `x.equals(x)` is always `true` when `x != null` | `first` with itself |
| Symmetric | `x.equals(y)` and `y.equals(x)` return the same result | `first`, `equalValue` |
| Transitive | `x=y`, `y=z` ⇒ `x=z` under `equals()` | `first`, `equalValue`, `thirdEqual` |
| Consistent | Without changing information used in comparison, results must remain stable | Re-compare multiple times when state does not change |
| Non-null | `x.equals(null)` is `false` for `x != null` | `first`, `null` |
| Matching hash | `x.equals(y)` is true ⇒ `x.hashCode() == y.hashCode()` | `first`, `equalValue` |
| Stable hash | Without changing information used by `equals()`, calling `hashCode()` multiple times in one run yields a stable result | Immutable `first` |

Additional lines that can be placed inside `main` of the program above to verify consistency (this is an **inline addition**, not a separate Java file):

```java
boolean before = first.equals(equalValue);
boolean after = first.equals(equalValue);
check("consistent equals", before == after);

int firstHash = first.hashCode();
check("stable hash", firstHash == first.hashCode());
```

Although calling it twice in the example is an easy-to-understand practical check, two passing calls **cannot absolutely prove** every case for every class. Contract verification should run with diverse datasets, especially boundary values, `null` if permitted in properties, and mutable states. The definition of `equals()` must reflect the class's intent, not just fit a single example.

### Why Must Both `equals()` and `hashCode()` Be Overridden?

Hash-based structures, such as `HashSet` and `HashMap`, use the hash code to group entries into buckets before confirming with `equals()`. If two instances are considered equal by `equals()` yet produce different hash codes, the set/map may fail to find an element or store logically duplicate elements.

To reduce mistakes, `UserKey.hashCode()` computes from the exact same `id` and `version` fields checked by `equals()`. Conversely, if you include a field that does not participate in `equals()` in `hashCode()`, you risk giving two equal objects different hashes and violating the contract.

## 6. When a Class Does Not Override `equals()`

Two instances containing the same fields **are not automatically equal** just because they were created with the same arguments:

```java
final class PlainKey {
    final String id;

    PlainKey(String id) {
        this.id = id;
    }
}

PlainKey a = new PlainKey("U-01");
PlainKey b = new PlainKey("U-01");

// a == b            -> false
// a.equals(b)       -> false (inherits Object.equals)
// a.equals(a)       -> true
```

This is an illustrative snippet placed in an appropriate Java code context (variable creation statements must be inside a method, constructor, or initializer). Because `PlainKey` does not override `equals()`, the expression `a.equals(b)` uses the default identity semantics of `Object`. If the goal is to compare `id`, implement `equals()` together with `hashCode()`, or use a data type that provides built-in value comparison.

### Concise Option with `record` (Java 17)

`record` automatically generates `equals()` and `hashCode()` based on the declared components:

```java
record UserKeyRecord(String id, int version) {}

UserKeyRecord x = new UserKeyRecord("U-01", 1);
UserKeyRecord alias = x;
UserKeyRecord sameValue = new UserKeyRecord("U-01", 1);
UserKeyRecord other = new UserKeyRecord("U-02", 1);

// x == alias                 -> true
// x == sameValue             -> false
// x.equals(sameValue)        -> true
// x.equals(other)            -> false
```

This is also **illustrative code**, assuming the variable declarations are placed inside a method. A record does not by default guarantee deep immutability of all components: if it contains an array or a mutable object, you need to understand how those components implement `equals()` / `hashCode()`. The example uses `String` and `int` so that equality behavior is clear and stable.

## 7. Common Mistakes When Constructing Test Objects

**Confusing an alias with an equal-value instance**

```java
UserKey b = a; // a == b is true; two distinct objects have not been tested at all.
```

To test `equals()` semantics between two separate instances, invoke `new UserKey(...)` a second time.

**Using `String` literals or boxed numbers to infer identity**

```java
String s1 = "java";
String s2 = "java";
// s1 == s2 may be true due to string interning;
// the result does not represent == semantics for two arbitrary objects.
```

String literals with the same content are interned according to Java rules. Some boxed values may use cached objects, causing `==` to occasionally return true. To verify the contract of the **type under study**, create instances of that exact type rather than inferring from the caching behavior of another type.

**Mutating fields involved in hashing after adding to a `HashSet`**

When an object used as a key has its `equals()` / `hashCode()`-related state mutated while residing in a `HashSet` or `HashMap`, lookup/removal can become broken. Prefer immutable keys like `UserKey` in the full program. If mutable objects are needed, design their usage in collections appropriately.

**Comparing hashes as the sole evidence**

Matching `hashCode` values do not prove two objects are equal; differing hashes prove two objects **cannot be equal if the class obeys the contract**. Do not use hashes to determine whether two variables point to the same instance; `System.identityHashCode()` can also collide between two distinct objects and does not substitute for `==`.

**Forgetting an important field in the dataset**

If `equals()` checks `id` and `version`, create an additional case differing only in `version`; otherwise, you may miss a bug where `equals()` accidentally compares only `id`. For example:

```java
UserKey differentVersion = new UserKey("U-01", 2);
check("different version", !first.equals(differentVersion));
```

This is an addition to `main` of the full program. Do not write tests requiring a difference in value from a field **not specified** to participate in `equals()`.

## 8. Minimum Dataset to Include in Real Tests

| Data group | Sample creation | Primary check |
| --- | --- | --- |
| Same object | `alias = first` | `first == alias`, `first.equals(alias)` |
| Two equal-value instances | `equalValue = new UserKey("U-01", 1)` | `first != equalValue`, `first.equals(equalValue)` |
| Different `id` field | `new UserKey("U-02", 1)` | `!first.equals(...)` |
| Different `version` field | `new UserKey("U-01", 2)` | `!first.equals(...)` |
| Three equal-value instances | `first`, `equalValue`, `thirdEqual` | Transitivity |
| `null` | `first.equals(null)` | Returns `false`, throws no exception |
| Hash-based collection | Add alias, equal-value object, different-value object | Does not store logically duplicate keys |

There is no need to conclude that every Java class must compare by value. For an object representing an entity with its own identity, `equals()` may be designed differently. **Define the contract first, construct the dataset according to that contract, and then verify across all three reference/value relationships.**

## 9. Self-Check Questions

1. Given two variables `a` and `b` assigned with `b = a`. Can this pair be used to verify that `equals()` recognizes two instances with the same values? **No**, because there is only one instance.
2. Two objects are created with `new` using the same properties. Does `==` return `true`? **No**, they are two distinct instances (assuming both exist).
3. Do two equal-value instances always have `equals()` equal to `true`? **No**: it depends on the implementation; `Object.equals()` defaults to comparing identity.
4. If `x.equals(y)` is true, is `x.hashCode() == y.hashCode()` required? **Yes**, that is the contract.
5. If two hash codes are equal, must the two objects be equal? **No**, a collision can occur.
6. Why is adding three equal-value instances useful? **To test transitivity**, in addition to reflexivity and symmetry.

**Practical takeaway:** construct the three types of relationships by (1) assigning an alias, (2) creating a new instance with the same fields that determine `equals()`, and (3) creating a new instance with a field that determines `equals()` altered. Then verify **`==` to determine identity**, **`equals()` to determine logical equality**, and **`hashCode()` to protect the contract when working with hash-based structures**.
