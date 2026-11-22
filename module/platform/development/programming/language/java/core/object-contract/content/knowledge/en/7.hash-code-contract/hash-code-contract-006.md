# Why Is `hashCode()` Not Required to Remain the Same Across Program Runs?

## 1. Exact Statement of the Contract

In Java, an object can return the same hash code repeatedly while the application is running, yet that hash code is **not required to stay the same after terminating and restarting the application**.

The `java.lang.Object.hashCode()` documentation (Java SE 17) states three main constraints:

1. **Consistency within a single execution:** Whenever `hashCode()` is invoked multiple times on the same object during **one execution of a Java application**, the method must consistently return the same integer **provided no information used in `equals` comparisons on the object is modified**. This is not a promise of immutability when content used to determine equality has changed.
2. **Compatibility with `equals()`:** If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.
3. **Collisions are allowed:** If `a.equals(b)` is `false`, Java **does not require** the two hash codes to differ. Two unequal objects can still share the same hash code.

Following those constraints, the documentation explicitly states that the integer returned by `hashCode` **need not remain consistent from one execution of an application to another execution of the same application**.

You can remember it in two lines:

- **Within the same run + unchanged equality data:** same object ⇒ same hash code.
- **Across another run:** the general `Object` contract itself **does not require** the old hash code to reappear.

The words “does not require” are important. They do **not mean** Java forces every startup to generate a new hash. A class can return the same hash code across multiple runs because its algorithm is fixed; that is still valid. Another class can return a different hash while still obeying the general contract.

## 2. How Do “One Run” and “Two Runs” Differ?

Scenario example:

- At 9:00, the application starts; it creates a `UserKey("U-42")` object and calls `hashCode()`.
- Within that process, the application calls `hashCode()` again multiple times without changing the data used in `equals`.
- The application stops completely.
- At 10:00, the application restarts; it creates a new object also representing `UserKey("U-42")` and calls `hashCode()`.

The contract requires calls in the **second step** to be consistent. The general contract **does not force** the 10:00 result to match the 9:00 result.

Why? `hashCode` is designed as an integer supporting hash-based data structures **at runtime**, not as a permanent storage identifier. Java does not publish a single hash algorithm that every class must use. A class's implementation and the runtime environment can determine the specific numeric value.

Therefore, do not conclude “I just ran it twice and got the same hash, so Java guarantees every future run will too.” Repeated observation in one environment is **evidence of the current implementation**, not enough to prove a general contract.

## 3. Java 17 Example: A Hash Depending on a Startup-Generated Value

The following class compares session keys by `id`. It generates a `RUN_SALT` number exactly once when the class is initialized during an application run. Within that run, `RUN_SALT` does not change; every object with the same `id` always has the same hash code. If you run the program again, the random value can differ, so the hash of the same `id` can also differ.

```java
import java.security.SecureRandom;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class HashAcrossRunsDemo {
    static final class SessionKey {
        private static final int RUN_SALT = new SecureRandom().nextInt();

        private final String id;

        SessionKey(String id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof SessionKey that)) {
                return false;
            }
            return id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return 31 * id.hashCode() + RUN_SALT;
        }
    }

    public static void main(String[] args) {
        SessionKey first = new SessionKey("U-42");
        SessionKey second = new SessionKey("U-42");
        Set<SessionKey> keys = new HashSet<>();
        keys.add(first);

        int before = first.hashCode();
        int after = first.hashCode();

        System.out.println(first.equals(second));
        System.out.println(before == after);
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(keys.contains(second));
    }
}
```

Save the code as UTF-8 in `HashAcrossRunsDemo.java` and run:

```bash
javac -encoding UTF-8 HashAcrossRunsDemo.java
java HashAcrossRunsDemo
```

**Deterministic output of the example:**

```text
true
true
true
true
```

Explanation:

1. `first.equals(second)` returns `true` because both objects have the same `id`.
2. `before == after` is `true` because `id` and `RUN_SALT` do not change during the current run.
3. Two equal objects share the same hash because the hash expression uses the same `id` and the same `RUN_SALT`.
4. `HashSet.contains(second)` returns `true` even though the set stores `first`, thanks to the upheld `equals`/`hashCode` contract.

Running `java HashAcrossRunsDemo` again still yields **four `true` lines**, yet the internal integer value of `hashCode()` **may** have changed. The example intentionally avoids printing the random number because a specific value cannot be predicted as standard output. Using `SecureRandom` here only illustrates that picking a per-startup parameter can still satisfy the contract; it **does not turn `hashCode` into a cryptographic hash** or a secure session management technique.

There is a small chance that two random startups receive the same `RUN_SALT`. That does not refute the lesson: Java allows both matching and differing values across runs.

### Why Can a Class Add a “Salt” and Still Be Correct?

Because the contract only requires:

- Within a single run, same object and same equality data ⇒ same result.
- Two objects with the same `id` ⇒ same hash result.
- No requirement that two different `id`s receive two different hashes.

The expression `31 * id.hashCode() + RUN_SALT` satisfies all three conditions. The number 31 is just the example's choice, not a multiplier required by Java for all classes. `int` addition/overflow under Java semantics does not break these properties.

## 4. Do Not Misread This as “Every `hashCode` Changes on Restart”

Specific data types **can publish stronger contracts** than `Object`'s general contract.

An important example is `String.hashCode()`. The Javadoc for `String` defines the algorithm based on the characters in the string, using powers of 31 by character position. Consequently, identical string contents will yield the same hash code according to `String`'s specification, even when strings are created in different runs on an API-compliant environment.

Example:

```java
String a = "java";
String b = new String("java");

System.out.println(a.equals(b));              // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

This is an **illustrative code snippet placed inside a method**, not a standalone Java file. The equal hashes in this example can be deduced from `String`'s `equals` and `hashCode` contract; and because `String.hashCode` is specified by content, the numeric result is also fixed by the string. Do not conclude from this that **every class** has a similarly fixed algorithm.

Comparison table:

| Object/Method | What Can You Rely On? | What Should You Not Infer? |
| --- | --- | --- |
| `Object.hashCode()` (general rule) | Consistent within a run if equality data does not change; equal implies same hash | That a specific numeric value must match across all runs |
| `String.hashCode()` | Algorithm specified by Javadoc based on string contents | That the hash is unique per string; two distinct strings can still collide |
| Custom class with an algorithm based solely on stable data | Can deliberately provide a stable hash across runs | That such stability automatically applies to every other class |
| Class using a per-startup salt | Can change hashes between runs while upholding the single-run contract | That the hash will **definitely** differ every time |
| `System.identityHashCode(obj)` | Gets the identity-based hash code regardless of how the class overrides `hashCode` | That the value is directly based on memory address or persists across restarts |

**Distinguish Java's general guarantees from API-specific guarantees.** If you need to rely on a stable hash value for protocol/storage reasons, there must be a specification for **the algorithm itself and the input representation**. The default `Object.hashCode` contract is not sufficient.

## 5. `Object.hashCode` and `System.identityHashCode` Are Not Persistent Identifiers

When a class does not override `hashCode`, it uses the implementation inherited from `Object`. This behavior is tied to object identity in the runtime environment; the resulting integer should not be treated as a persistent storage key.

`System.identityHashCode(x)` provides the identity-based hash value even when `x`'s class overrides `hashCode()`. However:

- Two distinct objects **can still** have the same identity hash code; the hash integer is not an absolute unique identifier.
- There is no guarantee that the identity hash code is a RAM address or an allocation sequence number.
- There is no guarantee that an object recreated after a restart will have the old identity hash.
- If `x` and `y` are equal by value due to overriding `equals`, `System.identityHashCode(x)` and `System.identityHashCode(y)` are not necessarily equal. Therefore **do not use `System.identityHashCode` as the `hashCode()` implementation for a class with value equality**, unless another mechanism guarantees compatibility.

Both `Object.hashCode` and identity hash are suitable for certain runtime needs, but they cannot replace business IDs, database IDs, or keys managed under a long-term contract.

## 6. Consequences of Persisting Hashes to Databases, Files, or External Caches

A common design mistake is saving `object.hashCode()` as a record's “fixed code”:

```java
// Example of an unsafe design when a persistent identifier is needed:
int persistedId = customer.hashCode();
```

This line is only an illustrative snippet, not a standalone program. If `customer.hashCode()` depends on implementation or mutable data, the saved value may no longer be valid in a later run. Even if the algorithm is stable, **two unequal objects can still share a hash**; thus a hash code does not meet uniqueness requirements.

Risky scenarios:

1. **Storing database keys using hash codes:** Can cause collisions and lacks stability guarantees when the class/JDK changes.
2. **Writing hashes to a file and comparing after a restart:** Two values can differ even when the business data is completely identical.
3. **Sharding or distributing data using arbitrary `Object.hashCode()`:** If different processes or code versions compute hashes differently, the same logical key may be routed to a different location. If sharding requires stability, the distribution protocol must specify the hash algorithm and canonical key format.
4. **Looking up records based on a hash saved from a previous run:** The hash can change across executions or versions; even when it does not change, collisions make lookups unsafe.
5. **Building checksums or security signatures from `hashCode()`:** `Object`'s `int` hash code is not a cryptographic digest, does not guarantee collision resistance, and does not verify tamper-proof integrity.

If you need to store an identifier, use a clearly specified ID (such as a business key or a UUID suited to the design). If you want to detect data changes, choose a digest algorithm suited to the need along with stable encoding/serialization rules; if you need tamper resistance, consider HMAC or digital signatures with proper key management. Those goals differ from the goal of `Object.hashCode()`.

## 7. What Do `HashMap` and `HashSet` Need from a Hash Within One Run?

`HashMap` and `HashSet` use hashes to organize and locate elements. Within a single execution, if a key is inserted and later looked up with another key that is **equal according to `equals`**, both must yield the same hash to preserve lookup semantics.

Internal buckets or hashes before and after a restart do not need to match. When a new application instance starts, in-memory collections are rebuilt as well. Whenever keys are added to the new collection, that run's hash mechanism is applied consistently.

For instance, the `SessionKey` class above can certainly be used as a key in a single run's `HashMap`. If the application stops and restarts, building a new `HashMap` from business keys remains valid even if the new salt/hash differs. What matters is that data recovery relies on **real IDs or value data**, not on old buckets or old hash numbers.

### A Separate Bug to Distinguish: Mutating Data Used in Equality

If a mutable key is added to a `HashSet` and then the user modifies a field participating in `equals`/`hashCode`, the hash code **within the same run** can change and `contains` can fail. This is not an issue of “hashes being unstable across restarts”; it is an issue of **mutating state while a key is inside a hash collection**.

Design the fields determining key equality to be immutable, or ensure they do not change for as long as the key is used in the collection.

## 8. Easily Confused Statements

| Statement | Assessment | Explanation |
| --- | --- | --- |
| “For the same object, calling `hashCode` twice in one run must return the same number if equality data is unchanged.” | **True** | Matches the consistency contract. |
| “The `hashCode` of the same value must stay identical across all JVM startups.” | **False if stated as a general rule** | `Object` does not require that; specific classes may publish stronger guarantees. |
| “Java forces the hash to change on every restart.” | **False** | It neither requires matching **nor requires differing**. |
| “If two objects are equal by `equals`, their hashes are equal.” | **True, mandatory** | Regardless of which algorithm the class chooses. |
| “If two hashes are equal, the two objects are equal.” | **False** | Hash collisions are allowed. |
| “`String.hashCode` has a specified content-based algorithm.” | **True** | This is `String`'s own guarantee, not a blanket rule for all classes. |
| “`System.identityHashCode` is the memory address.” | **No guarantee** | The API makes no promise of such a direct relationship. |
| “Hash codes can be used as unique IDs in a database.” | **Unsafe** | Both prone to collisions and lacking general persistence guarantees. |
| “A class can add a fixed per-run salt when computing its hash.” | **Can be valid** | Provided it preserves consistency within a run and compatibility with `equals`. |

## 9. Process for Choosing a Hash Technique Based on Real Needs

**When you need `equals`/`hashCode` for in-memory Java collections:**

1. Clearly define which fields determine whether two objects are equal.
2. Ensure two equal objects produce the same hash, even when they are two separate instances.
3. Keep the result stable as long as equality data does not change.
4. Choose a reasonable hash distribution to avoid unnecessary collisions.
5. Avoid mutating equality fields while the object is serving as a hash key.

**When you need a code stable across restarts, service versions, or different machines:**

1. Clearly identify the purpose: identifier, partitioning, checksum, or security.
2. Choose an explicitly specified algorithm and canonical input representation for that purpose.
3. Specify encoding, byte order, serialization format, and versioning (if data is complex).
4. Design collision handling/data migration if needed.
5. Test across multiple processes and versions, **without implicitly relying on `Object.hashCode()`**.

For data that must be compared across processes, even with a stable hash algorithm, a small hash code still carries collision risk; when correctness requires absolute distinction, combine it with full key/data checks or an identifier with stronger guarantees.

## 10. Practice Questions

**Question 1.** Run an application twice, creating an object representing code `"A-01"` each time. The first run yields hash `123`, the second yields hash `456`. Can you conclude `Object.hashCode()` was violated?

**Answer:** You cannot draw that conclusion. The general contract does not require the same hash across two runs. To determine correctness, you must inspect the class's specific contract and related conditions—especially whether within **each** run, equal objects share the same hash and the hash does not change spontaneously while equality data is unchanged.

**Question 2.** Run twice and receive hash `123` both times. Can you conclude Java guarantees subsequent runs will still return `123`?

**Answer:** No. Two matching observations do not establish a general guarantee. Only when a specific API defines the algorithm/inputs and appropriate conditions is there a basis to rely on results across runs.

**Question 3.** Within **one run**, two `UserKey("U-42")` objects return `true` when `equals` is called, yet their hashes are `101` and `202` respectively. Is this valid?

**Answer:** No. This violates the mandatory constraint “equal according to `equals` implies equal hash codes”.

**Question 4.** A class stores the hash code of `String code` via `code.hashCode()`. Because `String.hashCode()` is specified, can that number be used as a unique primary key for all strings?

**Answer:** No. A deterministic algorithm is not the same as uniqueness. Two different strings can have the same hash. A primary key must handle uniqueness according to data requirements.

**Question 5.** An application stores objects' `hashCode()` to route records to servers. After a deployment, the hash implementation logic changes while equality stays the same. What can happen?

**Answer:** The hash and partition location of the same logical key can change, even though the new implementation still obeys the `Object` contract. Stable distribution across deployments requires a controlled hashing protocol and a data migration strategy, not reliance on arbitrary implementation hash codes.

## 11. Key Takeaways

- `Object.hashCode()` **must be consistent within a single run** when the data used in `equals` does not change.
- `a.equals(b) == true` ⇒ `a.hashCode() == b.hashCode()`, while equal hashes do **not** prove two objects are equal.
- **There is no requirement to keep the same hash value across program runs**; nor is there a requirement that it must change.
- `String.hashCode()` is an example of a specific API publishing a content-based algorithm; always distinguish a specific class's guarantee from the general contract.
- `hashCode()` serves equality and in-memory hash-based data structures, **not as a replacement** for persistent IDs, specified checksums, or cryptographic hashes.
- Do not confuse bugs caused by *restarts* with bugs caused by mutating equality fields of a key currently inside a `HashMap`/`HashSet`.

References: [`Object.hashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()), [`String.hashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode()), [`System.identityHashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)), and [`HashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).
