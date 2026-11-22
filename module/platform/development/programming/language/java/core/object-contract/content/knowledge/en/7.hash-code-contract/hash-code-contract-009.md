# Do Not Use `hashCode()` as a Unique Identifier or Security Code

In Java, `hashCode()` returns an `int` integer used primarily to support hash-based data structures such as `HashMap` and `HashSet`. This number helps distribute and look up elements efficiently, but it is **not a unique identifier**, **not a secret**, and **not a cryptographic hash function**. Two different objects can have the same `hashCode()`, and an easily computed hash does not prove who created the data.

This lesson sits within **Java's `hashCode` contract**: understanding exactly what is guaranteed, why using a hash as an ID or security mechanism is wrong, and choosing replacement tools according to purpose.

## 1. What Does the `hashCode()` Contract Actually Say?

Every Java class has `hashCode()` inherited from `Object`, and a class can override that method. The core contract is:

1. When state participating in `equals` does not change within **the same application execution**, repeated calls to `hashCode()` on an object must yield consistent results.
2. **If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be true.**
3. If `a.equals(b)` is `false`, the two hash codes **are allowed to be equal**. Producing different values usually improves performance, but is not a mandatory requirement.

Expressed logically:

```text
a.equals(b) == true  => a.hashCode() == b.hashCode()
a.hashCode() == b.hashCode() =/=> a.equals(b) == true
```

The second implication is **invalid**. A hash is a tool for narrowing down lookup candidates, not a substitute for the equality check.

A note on `null`: you cannot call `null.hashCode()`. If you need a `null`-safe hash, use `Objects.hashCode(x)` (returns `0` for `null`) or `Objects.hash(...)` when computing a combined hash across multiple fields.

## 2. Why Can a Hash Code Never Be Treated as a Unique Code?

### 2.1. The `int` Value Range Is Finite

`hashCode()` returns a **32-bit `int`**, meaning there are only `2^32` (4,294,967,296) distinct bit patterns, including negative numbers. The set of objects or input values that may need to be distinguished is not limited by the bit patterns of an `int`. By the pigeonhole principle, if the number of values to assign exceeds the available hashes, **collisions are inevitable**.

Even before reaching that limit, a specific hash algorithm can already produce collisions. No contract states that all `2^32` values must be used or that values must be distributed perfectly.

### 2.2. Two Different Values Can Produce the Same Hash

In Java, the two strings **`"FB"` and `"Ea"`** have different contents yet share the same `String.hashCode()`:

```text
"FB": 31 * 'F' + 'B' = 31 * 70 + 66 = 2236
"Ea": 31 * 'E' + 'a' = 31 * 69 + 97 = 2236
```

For these two-character strings, the calculation follows the `String.hashCode()` algorithm specified by Java; this is a **deterministic collision**, not something you have to wait to happen by chance. `"FB".equals("Ea")` is still `false`.

A custom `hashCode()` class can also return the exact same number for every object. That causes poor hash performance, but **does not by itself violate the contract** as long as `equals` and `hashCode` remain consistent.

### 2.3. Matching Hashes Do Not Mean the Same Instance

`System.identityHashCode(obj)` bypasses a class's `hashCode()` override and retrieves the hash according to `Object`'s default identity semantics. However, **identity hash codes can still collide** and are not memory addresses. If you need to check whether two references point to the same object in Java, use `a == b`.

Do not create a `Map<Integer, Object>` using `obj.hashCode()` as a unique key and assume matching hashes represent the same object. Doing so can wrongly overwrite another object's record.

## 3. Java 17+ Example: `HashMap` Resolves Collisions Using `equals`

The program below combines a real `String` collision with a class that intentionally returns the same hash, to make clear that **matching hashes do not erase the distinctness of keys**.

Save as `HashCodeNotIdentityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

final class Key {
    private final String id;

    Key(String id) {
        this.id = Objects.requireNonNull(id);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof Key other)) {
            return false;
        }
        return id.equals(other.id);
    }

    @Override
    public int hashCode() {
        return 7; // Contract still holds, but every Key collides.
    }
}

public class HashCodeNotIdentityDemo {
    public static void main(String[] args) {
        String first = "FB";
        String second = "Ea";

        System.out.println("FB hash: " + first.hashCode());
        System.out.println("Ea hash: " + second.hashCode());
        System.out.println("FB equals Ea: " + first.equals(second));

        Set<String> words = new HashSet<>();
        words.add(first);
        words.add(second);
        System.out.println("HashSet size: " + words.size());

        Key a1 = new Key("A");
        Key a2 = new Key("A");
        Key b = new Key("B");
        System.out.println("A equals B: " + a1.equals(b));
        System.out.println("A equals another A: " + a1.equals(a2));
        System.out.println("A/B hashes equal: "
                + (a1.hashCode() == b.hashCode()));

        Map<Key, String> labels = new HashMap<>();
        labels.put(a1, "first");
        labels.put(b, "second");
        System.out.println("HashMap size: " + labels.size());
        System.out.println("Lookup new A: " + labels.get(a2));
    }
}
```

Compile and run from the folder containing the file:

```bash
javac HashCodeNotIdentityDemo.java
java HashCodeNotIdentityDemo
```

**Deterministic** output:

```text
FB hash: 2236
Ea hash: 2236
FB equals Ea: false
HashSet size: 2
A equals B: false
A equals another A: true
A/B hashes equal: true
HashMap size: 2
Lookup new A: first
```

Points to understand from the output:

- `"FB"` and `"Ea"` have the same hash 2236, yet `equals` returns `false`, so `HashSet` stores both.
- `Key.hashCode()` intentionally returns `7` for every instance; `Key("A")` and `Key("B")` remain two distinct keys because `Key.equals` compares `id`.
- Both `Key("A")` instances share the same `id` value and the same hash, so `labels.get(a2)` finds the record put under `a1`, even though `a1` and `a2` are two distinct instances.
- `HashMap` uses the hash to pick a lookup area, then uses key-matching logic (including `equals`) to distinguish colliding elements. **Using `hashCode` directly as an ID and bypassing `equals` loses this vital distinction step.**
- Returning a constant in `Key.hashCode()` is only to demonstrate correctness under collisions; **it is not a recommended implementation** because excessive collisions degrade performance. In practice, hash the fields participating in `equals` using `Objects.hash(...)` or an appropriate consistent algorithm.

## 4. Why Should You Not Use `hashCode()` as a Long-Term Stored ID?

Even when collisions have not been observed yet, a hash code lacks the properties required of an identifier.

| Requirement for an ID | Limitation of `hashCode()` |
| --- | --- |
| Uniquely distinguish entities within the system scope | Hashes can collide, even for two unequal objects |
| Stay stable across storage lifecycle, restarts, and deployments | `Object.hashCode()`/identity hash has no stability guarantee across runs; how a class overrides hash can also change |
| Not change when presentation attributes change | Hashes based on mutable fields will change with state |
| Compatible across services or languages | No general contract ensures a custom `hashCode` algorithm is compatible across systems |
| Not expose a predictable value in sensitive contexts | `hashCode()` is not designed to be secret or unpredictable |

Distinguish two cases:

1. **`String.hashCode()`** is specified by character contents, so for the same string, the algorithm produces the same result across Java runs. This **does not turn it into a unique or secure ID**: different strings can still share a hash and anyone can recompute the result.
2. **Default `Object.hashCode()`** is tied to the JVM's identity hashing mechanism and carries no stability contract across runs. That hash code cannot be treated as a database key or object address.

If a class overrides `hashCode()` using mutable fields, the hash value can even change when a field changes. Using that object as a `HashMap` key before and after mutation often leads to lookup bugs. Prefer immutable key values, and assign a **separate hash-independent ID** when objects need long-term identification.

### Choosing an Alternative ID by Scope

- **Database ID:** a primary key managed by the database, such as a sequence/identity-generated `BIGINT` or UUID; enforce `PRIMARY KEY`/`UNIQUE` constraints to prevent duplicate records within the specified scope.
- **ID exchanged across multiple processes or services:** a system-allocated UUID (for example `UUID.randomUUID()`) is a common choice when there is no centralized allocator. Random UUIDs reduce collision probability to very low levels under proper usage, though **not an absolute mathematical guarantee**; storage should still check uniqueness.
- **Only need to check for the same object within one JVM:** use `==` on references; for maps needing instance distinction, consider `IdentityHashMap` if it fits the problem semantics.
- **Monotonically increasing ID within a single process:** a counter like `AtomicLong` can issue distinct numbers within range, though restarts, overflow, and cross-process uniqueness must be managed explicitly. This is an intentional ID-allocation solution, not `hashCode()`.

Do not call `Integer.toHexString(obj.hashCode())` and treat the hexadecimal string as a new ID; changing representation **adds no information and does not prevent collisions**.

## 5. Why Is `hashCode()` Not a Security Code?

A hash function for collections and a cryptographic primitive have different goals:

| Property | Java `hashCode()` | Appropriate Security Tool |
| --- | --- | --- |
| Primary goal | Distributing keys, supporting lookups | Tamper resistance, key derivation, password storage, or purpose-specific token generation |
| Output | 32-bit `int` | Size and algorithm per requirement, typically much larger |
| Resisting input recovery given the hash | No guarantee | Slow password hashing/KDF with salt and computational cost |
| Resisting an attacker deliberately finding collisions | No guarantee | Cryptographic hash function when collision resistance is required |
| Authenticating data origin | No | Properly keyed HMAC or digital signature |
| Generating unpredictable secrets for authentication | No | Cryptographic random generator such as `SecureRandom` |

Common mistakes:

- **Storing passwords as `password.hashCode()`:** the 32-bit space is tiny, the algorithm is cheap, unsalted, and trivial to brute-force. When storing passwords, use a dedicated algorithm such as **Argon2id**, **scrypt**, **bcrypt**, or **PBKDF2**, with a random salt, appropriate cost parameters, and a maintained library.
- **Using `userId.hashCode()` as a session ID, password reset code, confirmation code, or API token:** inputs are predictable and hashes can be recomputed. An attacker needs no secret to reproduce the value.
- **Attaching `message.hashCode()` to prove data was not tampered with:** anyone who modifies the data can recompute the hash; furthermore, collisions are trivial to produce. To verify integrity and origin under a shared-key model, use **HMAC**; under a public-key model, consider **digital signatures**.
- **Assuming converting the hash to hex or Base64 makes it secure:** that is merely representation encoding, providing neither secrecy nor authentication.

`MessageDigest` with SHA-256 provides a **cryptographic hash function**, yet SHA-256 itself is neither an optimal password storage mechanism (because it is too fast) nor a sender authentication mechanism without a key. Each security need requires the right primitive.

### Example: Generating a Secret Token with `SecureRandom`

To compile and run standalone, save the following Java 17 example as `SecureTokenDemo.java`. The program prints only the **length** of the token, avoiding leaking secret tokens to stdout.

```java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();
        byte[] bytes = new byte[32]; // 256 random bits
        secureRandom.nextBytes(bytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
        System.out.println("token length = " + token.length());
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 SecureTokenDemo.java
java SecureTokenDemo
```

Stdout (256 bits = 32 bytes, unpadded URL-safe Base64 yields 43 characters):

```text
token length = 43
```

`SecureRandom` generates cryptographically unpredictable bytes; URL-safe Base64 simply represents those bytes as a string convenient for sending over HTTP. A token is an **access secret**: transmit it over HTTPS, limit its lifetime and permissions, protect it at rest, and never log raw tokens. There is no fixed token stdout value because tokens are generated randomly. Do not replace `SecureRandom` with `hashCode()`, `System.currentTimeMillis()`, or `java.util.Random` when secrecy is required.

## 6. Distinguishing Easily Confused APIs

- **`obj.hashCode()`:** per class implementation; for value objects, typically depends on fields significant to `equals`.
- **`Objects.hashCode(obj)`:** `null`-safe utility returning `0` for `null`, otherwise calling `obj.hashCode()`.
- **`Objects.hash(a, b, ...)`:** combined hash of multiple values, useful when writing `hashCode()` manually. Still just an `int` hash, neither unique nor cryptographically backed.
- **`System.identityHashCode(obj)`:** default identity-based hash, even when the class overrides `hashCode`; still has collisions, and is neither a memory address nor a stable cross-run ID.
- **`MessageDigest` (such as SHA-256):** cryptographic hashing tool for byte data; does not replace `equals` in collections and does not create secrets on its own.
- **`SecureRandom`:** generates cryptographically random values for appropriate tokens/nonces. Random identifiers also need collision and lifecycle management.
- **`UUID.randomUUID()`:** utility generating version 4 UUIDs; useful for distributed IDs, though publicly visible UUIDs do not inherently act as passwords or access credentials.

## 7. Design Checklist

Before choosing a field as a key, ask yourself:

1. **Do you need equality comparison or uniqueness?** If using hash-based collections, write `equals`/`hashCode` per the contract; collections handle collisions themselves. If you need a unique ID, allocate and manage a separate ID.
2. **Does the key outlive a single JVM run?** If so, do not rely on identity hashes or any hash code without an appropriate stability contract.
3. **Is the data used for authentication or tamper prevention?** If so, use the corresponding cryptographic APIs; `hashCode` provides no such protection.
4. **Does a token need to remain secret?** If so, the token must be unpredictable, have sufficient entropy, and have an appropriate lifecycle; do not derive it from public info via `hashCode()`.
5. **Can fields participating in `equals`/`hashCode` change?** If they change after the object is used as a key, lookup mechanisms can break; prefer immutability or choose a different key.

**Takeaway:** `hashCode()` is a **grouping/lookup hint**; many distinct objects can share the same hash number. It does not prove identity, does not replace stored IDs, and does not satisfy security requirements. Use `equals` when you need to determine equality, assign IDs scoped to your data, and pick dedicated security primitives for authentication or secret generation.
