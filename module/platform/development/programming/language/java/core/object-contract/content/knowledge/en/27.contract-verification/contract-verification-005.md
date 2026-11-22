# Do Not Write Tests Requiring Every Distinct Object to Have a Different Hash Code

**Principle:** In Java, **two objects that are equal according to `equals()` must have the same `hashCode()`; two unequal objects are completely allowed to share the same `hashCode()`**. Therefore, a test like `assertNotEquals(a.hashCode(), b.hashCode())` for any unequal pair `a`, `b` is a contract-invalid test. A correct hash function can still produce a **hash collision**.

This topic belongs to **object contract verification**: its purpose is to verify the correctness of `equals()`/`hashCode()` and the behavior of hash-based collections, rather than imposing a uniqueness requirement that does not exist in the Java specification.

## 1. Distinguishing Different Objects, Unequal Objects, and Different Hashes

There are three comparisons to distinguish:

| Expression | Question answered | Must it imply different hashes? |
| --- | --- | --- |
| `a != b` | Do the two variables point to **two different objects**? | **No.** Two separate instances can still be equal by value or collide in hash. |
| `!a.equals(b)` | Are the two objects **unequal under the `equals` contract**? | **No.** Two different values are allowed to have the same hash. |
| `a.hashCode() != b.hashCode()` | Are the two `int` hash results different? | If two hashes differ, then `a` and `b` cannot be equal under a contract-compliant implementation; the converse is false. |

Note that `a.equals(b)` should only be called when `a` is not `null`; if you need null-safe comparison, use `Objects.equals(a, b)`. Do not call `hashCode()` on `null`.

A familiar case:

```java
String a = new String("java");
String b = new String("java");
// a != b is true because they are different instances.
// a.equals(b) is true because they have the same content.
// a.hashCode() == b.hashCode() is true by contract.
```

Conversely, when `!a.equals(b)` is true, **you cannot conclude** `a.hashCode() != b.hashCode()`.

## 2. What Does the `hashCode()` Contract Require?

According to the `java.lang.Object` API, tests should focus on what is mandatory:

1. **Stability within a single execution when state used for `equals` does not change:** multiple calls to `hashCode()` on the same object must return the same integer if no information used in `equals` comparisons is modified. Do not infer that the hash must stay constant across two separate runs of the application.
2. **Equal objects must have equal hashes:** if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`. This is the **mandatory** direction of the contract.
3. **Unequal objects may share hashes:** if `a.equals(b)` is `false`, Java **does not require** the hashes to differ. Distinct hashes generally help hash table performance, but they are not a validity condition.

Written logically, for non-`null` `a`, `b` with contract-compliant methods:

```text
a.equals(b)                         => a.hashCode() == b.hashCode()   [required]
a.hashCode() != b.hashCode()         => !a.equals(b)                  [implied]
!a.equals(b)                        =/> a.hashCode() != b.hashCode()  [false]
a.hashCode() == b.hashCode()         =/> a.equals(b)                   [false]
```

The `equals()` contract also requires **reflexivity, symmetry, transitivity, consistency**, and `x.equals(null)` returning `false`. When verifying the object contract, those properties should have their own tests; requiring two unequal objects to have different hashes is not on the list.

### Why Can Collisions Never Be Forbidden?

`hashCode()` returns a 32-bit `int`, so there are at most **2³² representable hash values**. Meanwhile, the domain of objects or strings can contain far more distinct values than that. By the pigeonhole principle, it is impossible to map without collision all distinct values of a domain larger than 2³² into 2³² outputs.

Even over a small domain, a normal hashing algorithm can still assign the same hash code to two different values. **A collision is not automatically a bug.** For example, a constant hash code can satisfy the `equals/hashCode` obligation, though it usually distributes poorly and degrades performance.

## 3. Real Counterexample With `String.hashCode()`

Java defines the `String.hashCode()` algorithm over UTF-16 code units of the string with multiplier 31. Two strings:

```text
"Aa": 31 × 65 + 97 = 2112
"BB": 31 × 66 + 66 = 2112
```

Thus `"Aa".equals("BB")` is `false` while both have `hashCode() == 2112`. This is a valid collision in a standard library class; it is not a bug in `String`.

The **wrong test** below will fail even though `String` works properly:

```java
// Wrong: assumes every pair of unequal strings has different hashes.
if ("Aa".hashCode() == "BB".hashCode()) {
    throw new AssertionError("Hash collision bi coi sai thanh loi");
}
```

A proper test can confirm both that the two strings are unequal and that the collision does not conflate the two elements in a set. Never turn "no collisions" into a mandatory criterion for accepting an implementation.

## 4. Complete, Runnable Java 17+ Example

Save the following code as **`HashCodeContractDemo.java`**. The program intentionally defines a `Key` type whose hash is always `7` to verify that unequal objects still function properly in `HashSet` and `HashMap`.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashCodeContractDemo {
    // Record generates equals() based on the 'id' value.
    // Constant hash causes many collisions but does NOT violate the contract.
    private record Key(String id) {
        @Override
        public int hashCode() {
            return 7;
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        String firstString = "Aa";
        String secondString = "BB";

        check(!firstString.equals(secondString),
                "Hai chuoi phai khac nhau");
        check(firstString.hashCode() == secondString.hashCode(),
                "Hai chuoi phai co collision theo String.hashCode");

        Key a = new Key("alpha");
        Key equalCopy = new Key("alpha");
        Key b = new Key("beta");

        check(a != equalCopy, "Hai record duoc tao rieng");
        check(a.equals(equalCopy), "Hai key cung id phai bang nhau");
        check(!a.equals(b), "Hai key khac id phai khong bang nhau");

        // Mandatory contract checks.
        check(a.hashCode() == equalCopy.hashCode(),
                "Equal objects must have equal hash codes");
        check(a.hashCode() == a.hashCode(),
                "Hash code phai on dinh khi trang thai khong doi");

        // Two distinct keys may still share the same hash.
        check(a.hashCode() == b.hashCode(),
                "Vi du co y dung constant hash");

        Set<Key> keys = new HashSet<>();
        keys.add(a);
        keys.add(equalCopy); // Duplicate per equals => no new element added.
        keys.add(b);         // Distinct per equals => second element added.
        check(keys.size() == 2, "HashSet phan biet theo equals");

        Map<Key, String> map = new HashMap<>();
        map.put(a, "value-alpha");
        map.put(b, "value-beta");
        check(map.size() == 2, "HashMap giu ca hai key khac nhau");
        check("value-alpha".equals(map.get(equalCopy)),
                "Key bang nhau phai tim duoc value");
        check("value-beta".equals(map.get(b)),
                "Key khac nhau phai doc dung value");

        System.out.println("Aa va BB equals: " +
                firstString.equals(secondString));
        System.out.println("Aa hash: " + firstString.hashCode());
        System.out.println("BB hash: " + secondString.hashCode());
        System.out.println("a equals equalCopy: " + a.equals(equalCopy));
        System.out.println("a equals b: " + a.equals(b));
        System.out.println("a va b trung hash: " +
                (a.hashCode() == b.hashCode()));
        System.out.println("HashSet size: " + keys.size());
        System.out.println("HashMap[alpha]: " + map.get(equalCopy));
        System.out.println("HashMap[beta]: " + map.get(b));
    }
}
```

Compile and run:

```bash
javac HashCodeContractDemo.java
java HashCodeContractDemo
```

**Exact standard output:**

```text
Aa va BB equals: false
Aa hash: 2112
BB hash: 2112
a equals equalCopy: true
a equals b: false
a va b trung hash: true
HashSet size: 2
HashMap[alpha]: value-alpha
HashMap[beta]: value-beta
```

**Analysis:** `a` and `b` both have hash `7` yet are unequal under `equals()`. `HashSet` stores both, and `HashMap` returns the right value for each key. The `equalCopy` instance has the same `id` as `a`, so it is recognized as an equal key; adding the copy to `HashSet` does not increase its size. This example accurately separates **correctness** from **hash distribution quality**. A constant hash code can easily make a hash table slow, but it does not make the contract self-contradictory.

The program can be run on Java 17 or any newer version supporting `record`. All `check` calls execute normally, even when the JVM is launched without `-ea`; when a condition is false, `AssertionError` is thrown.

## 5. Fixing JUnit 5 Tests to Follow the Contract

Suppose production code has a `UserId` class where `equals` uses the user ID value and `hashCode` is implemented accordingly. The two tests below are **invalid in principle**:

```java
// Wrong: "different objects" (a != b) does not require "different hashes".
assertNotEquals(a.hashCode(), b.hashCode());

// Wrong: "different values" (!a.equals(b)) can still share the same hash.
assertNotEquals(x.hashCode(), y.hashCode());
```

Replace them by checking the **mandatory implication** together with collection behavior:

```java
// Right: two equal objects => same hash.
assertEquals(sameValueA, sameValueB);
assertEquals(sameValueA.hashCode(), sameValueB.hashCode());

// Right: two unequal objects => equals must distinguish them.
assertNotEquals(differentValueA, differentValueB);

// Right: if using HashSet, it must store both distinct values.
Set<UserId> uniqueIds = new HashSet<>();
uniqueIds.add(differentValueA);
uniqueIds.add(differentValueB);
assertEquals(2, uniqueIds.size());
```

This is **illustrative code inside a test class**: it requires `UserId`, initialized variables, JUnit Jupiter 5, and `java.util.Set/HashSet`. The statements above are not a standalone Java program. Here, JUnit's `assertNotEquals(objectA, objectB)` checks object equality and **does not** require differing hashes.

A small complete JUnit 5 class for collisions (assuming the project is already configured with the JUnit Jupiter library):

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class HashCollisionTest {
    private record Key(String value) {
        @Override
        public int hashCode() {
            return 42;
        }
    }

    @Test
    void equalKeysMustShareHash() {
        Key first = new Key("A");
        Key equalCopy = new Key("A");

        assertNotSame(first, equalCopy);
        assertEquals(first, equalCopy);
        assertEquals(first.hashCode(), equalCopy.hashCode());
    }

    @Test
    void unequalKeysMayShareHash() {
        Key first = new Key("A");
        Key second = new Key("B");

        assertNotEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode()); // Intentional collision.
    }

    @Test
    void hashSetMustRetainBothUnequalKeysDespiteCollision() {
        Key first = new Key("A");
        Key equalCopy = new Key("A");
        Key second = new Key("B");

        Set<Key> set = new HashSet<>();
        set.add(first);
        set.add(equalCopy);
        set.add(second);

        assertEquals(2, set.size());
        assertTrue(set.contains(first));
        assertTrue(set.contains(second));
    }
}
```

In the JUnit example, `assertEquals(first.hashCode(), second.hashCode())` is a **fixture-specific specification that intentionally returns a constant hash** in order to create a collision scenario for testing collections. **Do not copy that assertion as a general contract for all classes**: unequal objects are *allowed* to collide, not *required* to collide.

## 6. Which Properties Should Be Tested?

| Property | Proper way to verify | What not to do |
| --- | --- | --- |
| Reflexivity of `equals` | `assertTrue(a.equals(a))` | Assume comparing with `null` is valid when invoked on `null`. |
| Symmetry | For appropriate pairs, verify `a.equals(b) == b.equals(a)` | Test only one direction. |
| Transitivity | If `a` equals `b` and `b` equals `c`, verify `a` equals `c` | Create test data that fails the premise and still require equality. |
| Consistency | With unchanged state, repeated `equals` and `hashCode` calls yield consistent results | Require hash to stay unchanged after fields participating in `equals` have been modified. |
| `null` | For `a != null`, `assertFalse(a.equals(null))` | Call `null.equals(a)`. |
| Equal ⇒ same hash | Create **two value-equal instances**, verify `equals` and hashes match | Compare only the same reference, making the check too weak. |
| Unequal | Create genuinely unequal values, verify `!equals` | Demand that hashes necessarily differ. |
| Hash collection behavior | Add two unequal keys, verify both are present; add an equal key, verify no duplication | Use hash as the sole criterion for determining whether two keys match. |

When a class has **mutable** fields participating in `equals/hashCode`, avoid modifying a key after putting it into a `HashMap/HashSet`. Doing so can cause lookup to fail because the key's hash or equality relation has changed. This is a bug in how mutable keys are used, **different from a valid collision**.

### When Writing Data-Driven or Property-Based Tests

Generate many object pairs and apply the following rule:

```java
// Pseudocode inside a loop, a and b are non-null:
if (a.equals(b)) {
    if (a.hashCode() != b.hashCode()) {
        throw new AssertionError("Vi pham hop dong equals/hashCode");
    }
}
// No general assertion on hash when !a.equals(b).
```

To make the test strong, include **equal-value but distinct-instance** pairs, **unequal** pairs, and **intentional collision** cases if the object is used as a key in hash collections. Correctness cannot be concluded from just a few examples, but these data groups catch common contract bugs.

If the goal is to evaluate **hash function performance or quality**, write a separate test with data representative of the application, measuring collision frequency, bucket distribution, or operation timings. That is a conditional performance criterion, not a contract forbidding all collisions. Do not turn the goal "reasonably good distribution" into the assertion "never collide hashes".

## 7. Common Misconceptions

**"Two different objects must have different hashes because `hashCode` identifies an object."** False. `hashCode()` is an `int` hash code, not a unique identifier. Even `System.identityHashCode(obj)` does not promise to return a unique value for every object.

**"`HashMap` only uses `hashCode()` to distinguish keys."** False. The hash helps locate candidate buckets, after which the collection uses appropriate comparison (including `equals()`) to identify matching keys. When two unequal keys share the same hash, `HashMap` can still store both. Internal handling, such as bucket structure, is an implementation detail not needed to prove the contract.

**"If hashes are equal, then `equals()` must return true."** False. Equal hashes only indicate a potential equal value or a collision; `equals()` must be used to distinguish them.

**"A test creating 1,000 different objects and requiring 1,000 distinct hashes will catch bugs."** Such a test can fail on a completely contract-compliant implementation. If distribution measurement is part of a separate performance requirement, quantitative criteria and appropriate datasets are needed rather than an absolute rule.

**"Two `new Object()` instances will have different hashes."** Java makes no such guarantee, even though many JVMs often produce distinct values in small examples. Do not turn a commonly observed behavior into a test contract.

**"Identical hashes mean the data for two keys was lost."** False: collections are designed to handle collisions. When keys go missing or are misretrieved, inspect `equals/hashCode`, mutable state, and access patterns rather than blaming the occurrence of a collision.

## 8. Self-Check Scenarios

**Scenario 1.** `a.equals(b) == true` yet `a.hashCode() == 3` and `b.hashCode() == 5`. Is this a violation?

**Yes.** Two equal objects must have the same hash. This is a contract bug.

**Scenario 2.** `a.equals(b) == false` yet `a.hashCode() == b.hashCode() == 7`. Is this a violation?

**No.** This is a valid collision. Do not write tests forcing the two hashes to differ.

**Scenario 3.** `a != b` yet `a.equals(b) == true`. How should the hashes be checked?

**Check for equality.** Two objects with different references can be equal by value; when they are equal, their hashes must match.

**Scenario 4.** Two strings `"Aa"` and `"BB"` share the same hash; when inserted into `HashSet<String>`, what must the size be?

**2.** The two strings are unequal under `String.equals()`, so the collision does not merge them into one element.

**Scenario 5.** A class always returns `hashCode() == 1`, while `equals()` implements the equality rule properly. Is this allowed?

**Yes, under the contract**, because every equal pair has the same hash. However, a poorly discriminating hash can degrade the performance of hash-based collections.

## 9. Takeaways and Official Documentation

The shortest rule for designing tests:

- **`equals == true` ⇒ `hashCode` must be equal.**
- **`equals == false` ⇒ `hashCode` may be equal or different.**
- **Different `hashCode` ⇒ the objects cannot be `equals` under a contract-compliant implementation.**
- **Collisions are valid; catch bugs through the contract and lookup behavior, not by requiring unique hashes.**

Java 17 API specification references:

- [`Object.hashCode()` and `Object.equals()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [`String.hashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode())
- [`HashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)
- [`HashSet` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
