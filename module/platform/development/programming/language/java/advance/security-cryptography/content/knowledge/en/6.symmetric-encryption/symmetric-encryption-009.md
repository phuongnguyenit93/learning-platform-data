# 6.9 ChaCha20, ChaCha20-Poly1305, and Nonce Management

**ChaCha20** is a modern stream cipher that uses a 256-bit secret key to generate a pseudorandom byte stream (*keystream*) and XORs it with the data to encrypt. **ChaCha20-Poly1305** combines ChaCha20 with the Poly1305 authenticator to form an **AEAD** (*Authenticated Encryption with Associated Data*): it both protects plaintext confidentiality and detects modifications to the content and authenticated metadata. Both require careful **nonce** management. Repeating a nonce with the same key can leak plaintext information; with ChaCha20-Poly1305 it also breaks the security assumptions of the authentication tag.

This lesson belongs to the **symmetric encryption** section of the Java Cryptography Architecture/Extension (JCA/JCE). The goal is to understand the algorithm, use the Java 17+ APIs properly, and design a safe nonce lifecycle when an application handles multiple messages, threads, processes, or crash recovery.

## 1. Clearly Distinguish Three Concepts

| Component | Function | Sizes in IETF/RFC 8439 Variant | What Not to Confuse |
| --- | --- | --- | --- |
| **ChaCha20** | Encrypt/decrypt by XORing with a keystream | **256-bit** key; **96-bit** nonce; **32-bit** block counter; **64-byte** keystream block | Protects content secrecy only; **does not detect ciphertext modification**. |
| **Poly1305** | Message authenticator using a **one-time key** | **128-bit (16-byte)** tag | Never use standalone Poly1305 with a single key reused across multiple messages. |
| **ChaCha20-Poly1305** | AEAD: encryption plus integrity/authenticity check | **256-bit** key; **96-bit (12-byte)** nonce; **128-bit (16-byte)** tag | Tag is verified on decryption; **the nonce must still be unique per encryption key**. |

In both modes, the nonce is a value distinguishing one invocation of the key; it **need not be secret**. You can transmit the nonce alongside the ciphertext so the receiver can decrypt. However, "need not be secret" **does not** mean "may be repeated".

For AEAD, **AAD** auxiliary data (e.g., format version, record ID, tenant, message sequence) is **authenticated but not encrypted**. It remains visible if sent in cleartext. The exact same AAD must be supplied as **identical bytes** during encryption and decryption.

**Choosing the right protection layer:** using `ChaCha20` alone gives the receiver no proof that the ciphertext is intact. For content exposed to tampering, prefer `ChaCha20-Poly1305` or an approved AEAD rather than combining a stream cipher with a checksum like SHA-256.

## 2. How Does ChaCha20 Work?

ChaCha20 is an ARX cipher (*addition, rotation, XOR*). The algorithm's core operates on a state of sixteen 32-bit words, running **20 rounds** of transformations using addition modulo `2^32`, bit rotations, and XOR. Each block evaluation generates **64 bytes of keystream** from:

- A **32-byte key**;
- A **12-byte nonce**;
- A **32-bit block counter**.

For a single block, encryption can be visualized as:

```text
                          256-bit key
                              |
96-bit nonce -----------> ChaCha20 block function <---------- 32-bit block counter
                              |
                        64-byte keystream
                              |
plaintext block -------------XOR---------------------------> ciphertext block
```

Decryption is also an XOR with the exact same keystream:

```text
C = P XOR KS(key, nonce, counter)
P = C XOR KS(key, nonce, counter)
```

Because `x XOR y XOR y = x`, the same key, nonce, and counter must be used to recover the plaintext. The **block counter** increments when processing consecutive blocks of *the same message*. That differs from the **message counter** a system uses to generate a fresh nonce for the next message.

### 2.1 Two Different Counters

| Counter | Where It Lives | Responsibility |
| --- | --- | --- |
| **ChaCha20 block counter (32-bit)** | Inside the encryption of one message | Selects the next keystream block for the same key/nonce pair; must avoid wrapping and overlapping keystream ranges. |
| **Message sequence / nonce counter** | Managed by the application or protocol | Allocates a **fresh 96-bit nonce** for each encryption under the same key; must be uniquely allocated across concurrency and restarts. |

In the IETF variant, each `(key, nonce)` pair has a finite block counter space—roughly 256 GiB of keystream maximum given `2^32 × 64` bytes, and AEAD additionally reserves block counter 0 for the Poly1305 key. Never design an unboundedly large message relying on counter wraparound. In practice, split data into **bounded-size records**, give each record a fresh nonce, and apply tighter limits per protocol/provider.

### 2.2 Why Is Nonce Reuse Dangerous?

If two messages are encrypted with the **same key, same nonce, and overlapping counter ranges**, the corresponding keystream repeats:

```text
C1 = P1 XOR KS
C2 = P2 XOR KS

C1 XOR C2 = P1 XOR P2
```

An observer can compute the XOR of the two plaintexts from the two ciphertexts. If one plaintext is known, they recover the corresponding portion of the other plaintext. If messages have predictable structure, the leakage can be severe. This is **not** a vague matter of a nonce feeling "less random"; the core flaw is **reusing a keystream region**.

Changing `counter` must not be treated as a casual trick to "rescue" a repeated nonce. If an application manually partitions counter ranges, it must guarantee keystream regions never overlap, track block limits, and maintain protocol consistency; in typical systems, the simpler and safer rule is **one unique nonce per message**.

## 3. What Does ChaCha20-Poly1305 Add?

ChaCha20-Poly1305 per RFC 8439 is an **AEAD** construction. One encryption uses:

```text
Input:
  key       = 32 bytes
  nonce     = 12 bytes, non-repeating under this key
  plaintext = byte[] to keep confidential
  AAD       = byte[] to authenticate without hiding

Output:
  ciphertext
  authentication tag = 16 bytes
```

High-level flow:

1. Run ChaCha20 with `counter = 0` to **derive a one-time Poly1305 key** from the key/nonce pair. This key is not an independent long-term key.
2. Run ChaCha20 starting at `counter = 1` to encrypt plaintext into ciphertext.
3. Compute the Poly1305 tag over **AAD, ciphertext, padding, and encoded lengths per RFC 8439**. The 16-byte tag is sent with the ciphertext.
4. On decryption, verify the tag against the exact AAD and ciphertext. If invalid, **reject the message**; never use unauthenticated plaintext.

```text
                       (key, nonce)
                             |
                 +-----------+-----------+
                 |                       |
         ChaCha20 counter=0      ChaCha20 counter=1,2,...
                 |                       |
         one-time Poly1305 key       ciphertext
                 |                       |
                 +-----------+-----------+
                             |
              Poly1305 authenticates AAD + ciphertext
                             |
                         16-byte tag
```

From a Java perspective, you **do not manually implement** Poly1305 key derivation, padding alignment, or tag verification. `Cipher.getInstance("ChaCha20-Poly1305")` performs these steps. Manually gluing `ChaCha20` and `Poly1305` together easily breaks data boundaries, counters, lengths, and error handling.

### 3.1 What Does AAD Mean?

Suppose a record contains:

- `version`: format version;
- `recordId`: record identifier;
- `tenantId`: ownership scope;
- `ciphertext`: actual data.

The application can encode `version`, `recordId`, and `tenantId` deterministically into bytes and pass them into **AAD**. If someone alters `tenantId` or `recordId` in the authenticated metadata, decryption with the mismatched AAD fails. However, if that metadata is omitted from AAD, AEAD **does not automatically know** which fields the application intended to protect.

AAD is not secret; never put passwords/keys into it. Avoid concatenating strings with ambiguous delimiters (`a|bc` vs. `ab|c`) or relying on unstable field ordering. Pick a fixed encoding (e.g., binary field ID + length + bytes, or a defined canonical structure) and keep both sides consistent.

### 3.2 AEAD Does Not Prevent Replay on Its Own

If a **valid** ciphertext, nonce, AAD, and tag are re-sent verbatim, tag verification will still succeed. AEAD protects data authenticity—it does not remember whether a message was already processed. Stateful protocols need an **authenticated** `messageId`, sequence, or timestamp plus anti-replay/anti-rollback tracking on the receiving side.

## 4. Java 17+ API: Using the Right Algorithm Name and ParameterSpec

JCA/JCE provides two related `Cipher` names with distinct contracts:

| Task | JCA/JCE | Key | Initialization Parameters |
| --- | --- | --- | --- |
| Raw stream cipher | `Cipher.getInstance("ChaCha20")` | `SecretKeySpec(rawKey32, "ChaCha20")` | `new ChaCha20ParameterSpec(nonce12, initialBlockCounter)` |
| AEAD | `Cipher.getInstance("ChaCha20-Poly1305")` | `SecretKeySpec(rawKey32, "ChaCha20")` | `new IvParameterSpec(nonce12)` |
| AAD for AEAD | `cipher.updateAAD(aad)` | Uses `init` key | **Must be called before** payload `update`/`doFinal` |
| Finalize | `cipher.doFinal(input)` | Uses `init` key | AEAD returns `ciphertext \|\| tag` on encrypt; verifies tag on decrypt |

**Important detail:** `ChaCha20ParameterSpec` is for **raw ChaCha20**, holding a 12-byte nonce and a 32-bit counter. For **ChaCha20-Poly1305** on standard JDK providers, use `IvParameterSpec` with the 12-byte nonce; the counter is managed internally by AEAD. Do not pass AES-GCM's `GCMParameterSpec` to initialize ChaCha20-Poly1305, and do not append `/GCM/NoPadding` to ChaCha20 names.

Java 17+ includes `javax.crypto.Cipher`, `javax.crypto.AEADBadTagException`, `javax.crypto.spec.ChaCha20ParameterSpec`, `javax.crypto.spec.IvParameterSpec`, and `javax.crypto.spec.SecretKeySpec`. Providers must be verified on the **actual JDK where the application deploys**; third-party/HSM providers may differ in algorithm, key, and parameter support.

When `Cipher.init(..., key, params)` is called, the decryptor **must know the exact nonce and AAD bytes**. The nonce is usually transmitted outside the ciphertext; protect and authenticate critical metadata via AAD or protocol framing.

## 5. Runnable Program: Raw ChaCha20 Does Not Authenticate Ciphertext

Save the following as **`ChaCha20StreamDemo.java`**. The program generates a key/nonce for one demo run, encrypts a message, and decrypts it back. It then flips one bit of the ciphertext, decrypts again, and shows that decryption **still returns bytes** even though the data was altered.

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ChaCha20StreamDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        byte[] rawKey = new byte[32];
        byte[] nonce = new byte[12];
        random.nextBytes(rawKey);
        random.nextBytes(nonce);

        SecretKeySpec key = new SecretKeySpec(rawKey, "ChaCha20");
        ChaCha20ParameterSpec params = new ChaCha20ParameterSpec(nonce, 1);
        byte[] plaintext = "Hello ChaCha20".getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("ChaCha20");
        encryptor.init(Cipher.ENCRYPT_MODE, key, params);
        byte[] ciphertext = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance("ChaCha20");
        decryptor.init(Cipher.DECRYPT_MODE, key, params);
        byte[] recovered = decryptor.doFinal(ciphertext);
        System.out.println("Decrypted: "
                + new String(recovered, StandardCharsets.UTF_8));

        // Only tamper with ciphertext to demonstrate lack of integrity;
        // do not encrypt a second message using the same key/nonce pair.
        byte[] tampered = ciphertext.clone();
        tampered[0] ^= 1;

        Cipher decryptor2 = Cipher.getInstance("ChaCha20");
        decryptor2.init(Cipher.DECRYPT_MODE, key, params);
        byte[] altered = decryptor2.doFinal(tampered);
        System.out.println("Tampered ciphertext decrypted: succeeded");
        System.out.println("Content still identical: "
                + Arrays.equals(plaintext, altered));

        Arrays.fill(rawKey, (byte) 0);
    }
}
```

```bash
javac -encoding UTF-8 ChaCha20StreamDemo.java
java ChaCha20StreamDemo
```

Stdout on a JDK with a provider supporting ChaCha20:

```text
Decrypted: Hello ChaCha20
Tampered ciphertext decrypted: succeeded
Content still identical: false
```

Running two decryptions with the same key/nonce pair is **re-reading ciphertext**, not generating two keystreams for two new plaintexts. The altered output after flipping a ciphertext bit proves raw ChaCha20 does not detect tampering: the library throws no authentication exception because there is no tag.

**Never use this example as a tamper-resistant storage format.** Whenever integrity/authenticity is required, switch to AEAD. `Arrays.fill(rawKey,...)` clears the buffer held by the program, without guaranteeing every key copy inside `SecretKeySpec`, `Cipher`, or JVM memory is erased.

## 6. Runnable Program: ChaCha20-Poly1305, AAD, and Tag Failure

Save the following as **`ChaCha20Poly1305Demo.java`**. This is a self-contained example using a fresh key/nonce for exactly one encryption. To keep focus on the API, the nonce is randomly generated **solely for one demo message**. Sections 7–9 cover non-repeating nonce allocation for production services.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class ChaCha20Poly1305Demo {
    private static byte[] encrypt(
            SecretKeySpec key, byte[] nonce, byte[] aad, byte[] plaintext)
            throws GeneralSecurityException {
        if (nonce.length != 12) {
            throw new IllegalArgumentException("Nonce must be 12 bytes");
        }
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad); // Always before operations on plaintext.
        return cipher.doFinal(plaintext); // ciphertext || 16-byte tag
    }

    private static byte[] decrypt(
            SecretKeySpec key, byte[] nonce, byte[] aad,
            byte[] ciphertextAndTag) throws GeneralSecurityException {
        if (nonce.length != 12 || ciphertextAndTag.length < 16) {
            throw new IllegalArgumentException("Invalid data frame");
        }
        Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag); // Verifies tag.
    }

    public static void main(String[] args) throws GeneralSecurityException {
        SecureRandom random = new SecureRandom();
        byte[] rawKey = new byte[32];
        byte[] nonce = new byte[12];
        random.nextBytes(rawKey);
        random.nextBytes(nonce);

        SecretKeySpec key = new SecretKeySpec(rawKey, "ChaCha20");
        byte[] plaintext = "Hello AEAD".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "record=v1".getBytes(StandardCharsets.UTF_8);
        try {
            byte[] ciphertextAndTag = encrypt(key, nonce, aad, plaintext);
            byte[] recovered = decrypt(key, nonce, aad, ciphertextAndTag);
            System.out.println("Decrypted: "
                    + new String(recovered, StandardCharsets.UTF_8));
            System.out.println("Tag bytes: "
                    + (ciphertextAndTag.length - plaintext.length));

            byte[] tampered = ciphertextAndTag.clone();
            tampered[tampered.length - 1] ^= 1;
            try {
                decrypt(key, nonce, aad, tampered);
                throw new AssertionError("Accepted invalid tag");
            } catch (AEADBadTagException expected) {
                System.out.println("Tampered tag: rejected");
            }

            byte[] wrongAad = "record=v2".getBytes(StandardCharsets.UTF_8);
            try {
                decrypt(key, nonce, wrongAad, ciphertextAndTag);
                throw new AssertionError("Accepted wrong AAD");
            } catch (AEADBadTagException expected) {
                System.out.println("Tampered AAD: rejected");
            }
        } finally {
            Arrays.fill(rawKey, (byte) 0);
        }
    }
}
```

```bash
javac -encoding UTF-8 ChaCha20Poly1305Demo.java
java ChaCha20Poly1305Demo
```

Stdout on common JDK providers:

```text
Decrypted: Hello AEAD
Tag bytes: 16
Tampered tag: rejected
Tampered AAD: rejected
```

**Explanation of each check:**

1. `Cipher.getInstance("ChaCha20-Poly1305")` selects AEAD; `IvParameterSpec` passes the 12-byte nonce. The block counter and Poly1305 key derivation are handled by the provider.
2. `updateAAD(aad)` runs before `doFinal`. On decryption, AAD must match byte-for-byte.
3. `encrypt` returns `ciphertext || tag`, which is **16 bytes** longer than plaintext. The example does not prepend the nonce to the output array; real systems must persist/transmit the nonce alongside the record.
4. Flipping one tag bit triggers `AEADBadTagException`; changing AAD while keeping old ciphertext/tag is likewise rejected.
5. `decrypt` returns no plaintext when the tag fails. Never `catch (AEADBadTagException)` to strip the tag and decrypt with raw ChaCha20.

**Demo limitation:** generating a random nonce for one demo message is not a long-term nonce allocation mechanism; if a key is reused across multiple messages, the entire system must enforce a **non-repeating** nonce policy. Never store raw keys in source code, logs, plaintext databases, or service responses.

## 7. The Most Important Rule: Nonces Must Be Unique Per Key

With IETF ChaCha20-Poly1305, each **encryption** under a key `K` must use a nonce `N` never previously used to encrypt under `K`. This is a **uniqueness** requirement, not a requirement that the nonce be secret or unpredictable.

```text
(key K, nonce N0) -> message 0    VALID
(key K, nonce N1) -> message 1    VALID  (N1 != N0)
(key K, nonce N0) -> message 2    WRONG! (N0 already used with K)
(key K2, nonce N0) -> message 3   Potentially valid, if K2 is genuinely a different key
```

Reusing `(K, N)` causes ChaCha20 to repeat its keystream and Poly1305 to reuse its one-time authentication key. Consequences extend beyond leaking the XOR of plaintexts; authenticity guarantees are also compromised. **Never "fix" a nonce collision by advancing Cipher's internal counter or dropping the tag.** If a system detects suspected nonce reuse, halt writes under that key, investigate scope, and remediate/rotate keys per policy.

### 7.1 96-Bit Nonce: Random or Counter?

Two strategy families are commonly discussed:

| Nonce Allocation Method | Advantages | Limitations / Risks |
| --- | --- | --- |
| **12 bytes from `SecureRandom`** | Easy in demos/low traffic, minimal state. | Randomness **does not guarantee absolute uniqueness**; collision odds grow with message count under one key; hard to prove non-collision across multiple writers. |
| **Deterministic unique nonce**: partitioned prefix + monotonic counter | Can guarantee zero repetition with coordinated allocation, durable state, and no wraparound. | Requires careful partition management, restarts, concurrency, sequence allocation, and key rotation. |

For `n` nonces chosen uniformly at random in a `2^96` space, the approximate collision probability when `n` is small relative to the square root of the space is:

```text
P(collision) ~ n(n - 1) / (2 * 2^96)
```

This formula is solely for **risk assessment**—it does not turn random nonces into a deterministic uniqueness proof. RFC 8439 emphasizes that every invocation under the same key must have a unique nonce; for long-lived/multi-writer designs, prefer **counters and nonce-space partitioning** per protocol policy. The random nonce in Section 6 focuses solely on demonstrating the Java API.

### 7.2 Writer + Sequence Nonce Partitioning Pattern

One way to structure 96 bits is:

```text
        12 bytes / 96 bits
+----------------+--------------------------------+
| writerId/prefix| monotonically increasing seq   |
| 4 bytes        | 8 bytes                        |
+----------------+--------------------------------+
         both parts must be allocated consistently per key scope
```

- `writerId`/prefix **must be unique among writers sharing the same key**, assigned in a controlled way; never assume a random 4-byte prefix cannot collide.
- `seq` must increment **without repeating** within the same prefix and key. Two threads must never receive the same number. Never wrap back to 0 when hitting the limit.
- After a crash/restart, a writer must recover from **durable state** that has never been re-issued; an in-RAM `AtomicLong` alone is **insufficient**.
- A nonce that was **allocated and used** must be treated as consumed, even if the write operation failed or the response was lost. Retrying a new encryption must acquire a **fresh** nonce, or resend the exact already-saved ciphertext without re-encrypting.
- If multiple processes, containers, regions, or shards share a key, a system-wide unique partition/sequence allocator is required. Each process counting from 0 on its own is insufficient.

This is **one bit-layout example**, not a universal mandatory format for all protocols. Protocols like TLS construct nonces in their own way tied to sequence numbers and session secrets; **never** replace standard protocol rules with a homegrown pattern.

## 8. Runnable Program: Counter-Based Nonce Allocator Illustration

This example solely illustrates combining a 4-byte prefix with an 8-byte sequence and issuing values atomically within **one JVM**. It has no durable persistence or prefix authority, so it is **not a production allocator**. Prefix `01 02 03 04` is fixed so stdout is deterministic; never copy a fixed prefix and zero initial counter across multiple workers sharing a key in real life.

Save as **`NonceCounterDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicLong;

public final class NonceCounterDemo {
    private final byte[] prefix;
    private final AtomicLong nextSequence;

    NonceCounterDemo(byte[] prefix, long initialSequence) {
        if (prefix == null || prefix.length != 4 || initialSequence < 0) {
            throw new IllegalArgumentException(
                    "Invalid prefix or sequence");
        }
        this.prefix = prefix.clone();
        this.nextSequence = new AtomicLong(initialSequence);
    }

    byte[] nextNonce() {
        long current;
        do {
            current = nextSequence.get();
            if (current == Long.MAX_VALUE) {
                throw new IllegalStateException("Nonce space exhausted");
            }
        } while (!nextSequence.compareAndSet(current, current + 1));

        return ByteBuffer.allocate(12)
                .put(prefix)
                .putLong(current) // Big-endian convention for sequence in demo.
                .array();
    }

    public static void main(String[] args) {
        NonceCounterDemo allocator =
                new NonceCounterDemo(new byte[]{1, 2, 3, 4}, 0);
        System.out.println(HexFormat.of().formatHex(allocator.nextNonce()));
        System.out.println(HexFormat.of().formatHex(allocator.nextNonce()));
    }
}
```

```bash
javac -encoding UTF-8 NonceCounterDemo.java
java NonceCounterDemo
```

Stdout:

```text
010203040000000000000000
010203040000000000000001
```

Key takeaways from the example:

- `compareAndSet` prevents threads sharing **one** `AtomicLong` from receiving duplicate numbers due to an in-JVM race.
- Using `ByteBuffer.putLong` in default big-endian byte order defines the **message sequence layout**, not ChaCha20's internal word endianness. ChaCha20 takes the nonce as **12 bytes**; uniqueness is the primary requirement.
- For simplicity, the example uses only non-negative sequence values `0..Long.MAX_VALUE-1` and throws upon exhaustion, avoiding `long` wraparound bugs. Exhausting the full 64-bit space is not required.
- Running `new NonceCounterDemo(..., 0)` again emits **old nonces**. If the key is reused, that is a critical bug. Production requires persistent/atomic state or designed key/domain separation.

**Multi-writer cases:** assign non-overlapping prefixes per writer sharing a key; or allocate sequence ranges centrally; or derive per-sender keys via a proper KDF and manage nonces within each key domain. Every approach must prove non-repetition across scaling, failover, rollback, and redeployment.

## 9. Nonce Management Architecture in Real Applications

This is a reference architecture showing required components; it is **not** a complete database/distributed implementation.

```text
           Key Vault/KMS                         Durable allocator
               |                                (per keyId + writer)
       keyId -> secret key                           |
               |                            issues unique nonces
               +---------------+---------------------+
                               |
                         Encrypt service
                               |
           header(version, keyId, nonce, flags) + AAD
                               |
                   ChaCha20-Poly1305 encrypt
                               |
               ciphertext || authentication tag
                               |
           Store/transmit record in a versioned format
```

### 9.1 Key and Nonce Constraints

**Key:** generate 32 random bytes using an approved cryptographic RNG, or obtain from KMS/keystore via an approved key generation flow. Never use `new Random()`, timestamps, usernames, or `password.getBytes()` directly as a ChaCha20 key. If the source is a password/shared secret, use an appropriate KDF and manage salt/parameters by design; never cobble together hashes to make keys. Avoid sharing one key across unrelated purposes unless the protocol proves compatibility.

**Key ID:** records must identify which key decrypts them; during key rotation, old records still need to resolve the old key until migrated or expired. Key IDs can be public, yet must come from a trusted domain; authenticate sensitive metadata with AAD.

**Nonce uniqueness domain:** keys and nonces must be managed as a pair. Counters may restart **with a genuinely independent new key**, but must never reset while reusing an old key. KMS/rotation and the allocator must coordinate `keyId` lifecycles to prevent re-issuing nonce ranges.

### 9.2 Versioned Records

A possible format:

```text
version (1 byte)
keyIdLength + keyId
nonce (12 bytes)
ciphertextLength + ciphertext
tag (16 bytes)

AAD = exact encoding of version + keyId + recordId/tenant/context
```

Length fields and encodings must be **unambiguously** defined, with bounds rejecting anomalous payloads; the sketch above is only a schema outline. Java `Cipher.doFinal` with ChaCha20-Poly1305 typically returns `ciphertext || tag` in **one byte array**, so serialization must know where the 12-byte nonce and 16-byte tag sit. Never treat tags or nonces as secrets, and never let the receiver guess key/nonce/version.

If `recordId` or `tenant` drives access control, include them in AAD and simultaneously **enforce authorization** at the application layer; AEAD does not replace access control. Never put sensitive data in AAD to hide it, because AAD remains visible.

### 9.3 Durable Allocation Before Encryption

A system with long-lived keys can follow this strategy:

1. Uniquely identify `(keyId, writerId)` and its dedicated sequence range.
2. Atomically **reserve** a sequence number or range in a trusted transactional store/allocator, **committing the issued high-water mark before use**.
3. Build the nonce from the assigned prefix + newly issued sequence number, never repeating.
4. Encrypt one record with AEAD and persist `(keyId, nonce, AAD schema, ciphertext, tag)` in a stable format.
5. If the process crashes after allocating a nonce but before saving the record, **burn** the issued nonce; never reclaim it just because no ciphertext appears in the DB.
6. If a response is lost after the record is saved, **return the previously saved ciphertext record** by idempotency key. If re-encryption is truly needed, reserve a **fresh nonce**.
7. Never let sequences wrap; alert at a threshold and rotate keys per policy.

Uniqueness cannot be guaranteed solely by `synchronized`, `AtomicLong`, an in-pod mutex, or a Redis key that does not survive failover. Systems must verify durability and handle network partitions, DB rollbacks, backup restores, autoscaling, and workload migrations.

### 9.4 Common Nonce Mistakes

| Mistake | Why It Is Wrong | How to Prevent |
| --- | --- | --- |
| Every encryption uses `new byte[12]` (all zeros) with a long-lived key | Repeats `(key,nonce)` starting on the second message. | Use unique nonces per encryption; a zero nonce is valid only if the key itself is genuinely fresh per message per protocol design. |
| Using `System.currentTimeMillis()` or `Random` | Predictable/collision-prone with no uniqueness guarantee; `Random` is not a CSPRNG. | Durable coordinated counters, or an approved random policy with proven risk bounds. |
| Each pod counts from 0 with the same key/prefix | Pods emit identical nonces. | Assign exclusive prefixes/domains or use a centralized sequence allocator. |
| Restarting counter from 0 | Re-issues nonces already used before crash. | Persist high-water mark before use; never re-issue after rollback. |
| Retrying record encryption with the same nonce after payload/AAD changes | Reuses `(key,nonce)` for a different encryption. | Retry the saved ciphertext or allocate a fresh nonce for a new encryption. |
| Treating nonce as secret; omitting it from transmission | Receiver lacks decryption parameters and resorts to guessing. | Store/transmit nonce explicitly with the record while protecting the key. |
| Allowing counter wraparound or processing an unbounded message | Repeats keystream blocks / hits algorithm limits. | Cap record sizes, check overflow, rotate keys/nonces. |
| Trying to "work around" a bad AEAD tag by decrypting as raw stream cipher | Bypasses authentication, risking forged data in business logic. | Reject the entire record; investigate key/nonce/AAD/tag. |

## 10. Java Error Handling and Things to Avoid

| Error or Symptom | Typically Occurs When | Resolution |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Cipher.getInstance("ChaCha20")` or `getInstance("ChaCha20-Poly1305")` has no implementation | Verify JDK/provider, configuration, and algorithm name; fail fast at startup. |
| `InvalidKeyException` | `Cipher.init` receives wrong algorithm/size key or provider rejects it | Verify 256-bit key and key source; never fall back to weak keys/other algorithms. |
| `InvalidAlgorithmParameterException` | Wrong nonce size or parameter spec mismatched with engine/provider | Match `ChaCha20ParameterSpec` with stream cipher, `IvParameterSpec` with AEAD; 12-byte nonce. |
| `IllegalArgumentException` | `ChaCha20ParameterSpec` constructor receives non-12-byte nonce or app validation fails | Fix input; do not confuse with ciphertext authentication failure. |
| `IllegalStateException` | `updateAAD` in wrong order/state; reusing cipher or re-initializing with unsafe nonce per provider check | Create a fresh operation and fresh nonce; never rely on providers detecting all cross-process reuse. |
| `AEADBadTagException` | `doFinal` on decryption sees mismatched ciphertext/tag/AAD/key/nonce | **Reject the message**, return no plaintext. Keep responses uniform to avoid detailed oracles. |

`AEADBadTagException` does not specifically mean "wrong password" or "reused nonce": the exact same exception occurs when ciphertext is altered, key is wrong, nonce is wrong, tag is wrong, or AAD mismatches. Receivers should return a uniform authentication-failure response and log bounded diagnostics securely; never log keys, plaintext, or KMS secrets.

**Never reuse the same `Cipher` to encrypt again with an old key/nonce.** Some providers reject reuse on the same instance, yet a single `Cipher`'s duplicate guard does not protect other instances or processes. Nonce allocation belongs in system design.

### 10.1 Startup Configuration Check

The snippet below illustrates only provider lookup (not a standalone program):

```java
// Snippet inside a method declaring throws GeneralSecurityException.
Cipher cipher = Cipher.getInstance("ChaCha20-Poly1305");
System.out.println(cipher.getProvider().getName());
```

If a specific provider is mandated (e.g., policy/FIPS), use the appropriate overload and do not silently fall back when that provider is missing. A JDK having ChaCha20-Poly1305 **does not mean** that provider or module is certified under your system's policy; verify compliance requirements separately.

## 11. ChaCha20-Poly1305, AES-GCM, and XChaCha20-Poly1305

| Criterion | ChaCha20-Poly1305 (IETF) | AES-GCM | XChaCha20-Poly1305 |
| --- | --- | --- | --- |
| Type | AEAD | AEAD | AEAD using ChaCha's extended-nonce variant |
| Key | 256 bits | 128/192/256 bits per implementation and policy | Typically 256 bits |
| Nonce | **96 bits** in RFC 8439 | **96 bits** common/recommended | **192 bits** |
| Tag | 128 bits | Typically 128 bits (other lengths allowed per policy) | 128 bits |
| Java JCA/JCE | `ChaCha20-Poly1305` on supporting JDKs | `AES/GCM/NoPadding` | Do **not** assume a built-in standard JCA name; requires supporting library/provider |
| Primary warning | Never repeat nonce per key | Never repeat IV/nonce per key | Different format/nonce; never substitute one name for another |

Never claim one algorithm is **always** faster; performance depends on CPU, hardware acceleration, provider, and workload. Both AES-GCM and ChaCha20-Poly1305 are strong AEAD choices when used with proper policies, keys, nonces, AAD, and error handling. Choose based on protocol interoperability, compliance requirements, library availability, and real-environment benchmarks.

**XChaCha20-Poly1305 is not wire-compatible with IETF ChaCha20-Poly1305**: you cannot pass a 24-byte nonce into a 12-byte `IvParameterSpec` under the same name and expect XChaCha. Using XChaCha requires its specific library/format and nonce rules—never invent a custom subkey derivation step.

## 12. Self-Check Scenarios

**Scenario A — Two threads share a key, each with its own `AtomicLong(0)`:** Is this safe?  
**Answer:** No. Each thread has its own counter, so sharing a prefix produces identical nonces. You need a shared atomic allocator or uniquely assigned prefixes/domains.

**Scenario B — Incrementing block counter to 2 for a second message while keeping the same key/nonce:** Does this solve nonce reuse?  
**Answer:** Not a safe policy for new messages. If keystream regions overlap, the two plaintexts leak their XOR; manual range partitioning demands strict bounds and tracking. By default, require a **fresh nonce** for each independent encryption.

**Scenario C — Changing AAD from `tenant=alpha` to `tenant=beta` while keeping nonce/ciphertext/tag:** Result?  
**Answer:** AEAD rejects due to tag mismatch (when AAD bytes change). That does not replace application-layer tenant authorization checks.

**Scenario D — Restoring a DB from an old backup causes the allocator to re-issue previously used sequences:** Can the same key keep being used?  
**Answer:** No. You must ensure allocator state never rolls back, or rotate to a new key/domain before encrypting again; scope any potentially collided nonces and handle as an incident.

**Scenario E — Valid tag, yet an old message is re-sent:** Does AEAD block it automatically?  
**Answer:** No. You need deduplication, authenticated sequence/timestamp checks, and protocol-level anti-replay state.

**Scenario F — Encrypting a huge file with ChaCha20's 32-bit counter without size limits:** Issue?  
**Answer:** The block counter is finite; wrapping risks keystream repetition. Split into bounded records, use a fresh nonce per record, and enforce protocol/provider size limits.

**Scenario G — A developer calls `cipher.update(plaintext)` then `cipher.updateAAD(header)`:** Is this valid?  
**Answer:** No. For AEAD, AAD must be fed before plaintext/ciphertext; providers may throw `IllegalStateException`. Authenticate the entire header before processing payload.

## 13. Design and Review Checklist

- **Security goal:** need both confidentiality **and** authenticity? Use AEAD instead of raw ChaCha20.
- **Right API:** `ChaCha20ParameterSpec(nonce12, counter)` for `ChaCha20`; `IvParameterSpec(nonce12)` for `ChaCha20-Poly1305`.
- **Key:** 32 sufficiently random bytes managed in KMS/keystore or equivalent secure store, never hardcoded.
- **Nonce:** non-repeating per key; clear scope, unique across multi-writers, durable across restarts/crashes, no wraparound.
- **AAD:** fixed encoding, includes version/identifiers/relevant context if needed; supplied before payload and re-checked byte-for-byte.
- **Record:** store/transmit version, keyId, nonce, ciphertext, and tag in an unambiguous format with length bounds.
- **Decryption:** reject on tag failure; never return unauthenticated plaintext, log secrets, or fall back to raw stream cipher.
- **Replay:** if business logic requires it, verify sequence/ID/timestamp on authenticated data and maintain receiver state.
- **Lifecycle:** coordinate key rotation with the allocator, backup/restore, and nonce-collision incident response; verify payload/counter ceilings.
- **Testing:** test round-trip, tampered ciphertext, tampered tag, tampered AAD, wrong key/nonce, truncated records, allocator restarts, and concurrent multi-writer allocation.

## Official References

1. [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439.html): ChaCha20 structure, 96-bit nonce, block counter, Poly1305 key derivation, AEAD, reuse warnings.
2. [Java SE 21 — `ChaCha20ParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): 12-byte nonce and 32-bit initial counter.
3. [Java SE 21 — `Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): `getInstance`, `init`, `updateAAD`, `doFinal`, exceptions, and AEAD.
4. [Java SE 21 — `AEADBadTagException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/AEADBadTagException.html): tag verification failure on decryption.
5. [Java SE 21 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): standard names `ChaCha20` and `ChaCha20-Poly1305` in JCA/JCE.

**Technical conclusion:** ChaCha20 turns a key and nonce into a keystream for encryption; ChaCha20-Poly1305 adds an authentication tag and AAD. Both depend on **never reusing a nonce under the same key**. In Java, use the proper `Cipher`/`ParameterSpec`, while at the system level manage nonces durably, uniquely across writers, and resiliently across crashes/restarts.