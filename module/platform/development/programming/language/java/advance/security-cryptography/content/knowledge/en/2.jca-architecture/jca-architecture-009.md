# 2.9 Compatibility and Mutable State When Using Cryptographic Services Concurrently

## 1. Why Must These Two Issues Be Considered Together?

A Java application may execute thousands of concurrent cryptographic operations: hashing uploaded content, verifying webhook signatures, computing HMACs, encrypting user data, or decrypting messages arriving from another service. These tasks may run across multiple web server threads, thread pools, async tasks, or multiple application instances.

For results to be both accurate and secure, **two independent yet related problem areas** must be solved simultaneously:

1. **Compatibility (interoperability / compatibility):** Do the producer and consumer of cryptographic data agree on algorithms, parameters, byte formats, key representations, and protocol versions? Do different Java Security Providers mutually support those choices?
2. **State and concurrency:** What data from a previous operation is a JCA object currently holding, which key, sign/verify mode, or encrypt/decrypt mode? If multiple threads call `update`, `init`, or `doFinal` on that object concurrently, could one request mix its data/state with another request's?

**Key point:** “Same algorithm name” is not enough to guarantee compatibility between two systems; “sharing one Java object” also does not guarantee concurrent calls are permitted.

### Lesson Objectives

After studying this lesson, you will be able to:

- Distinguish **engine API**, **provider implementation**, and **per-engine-instance state** in JCA.
- Identify mutable state in `MessageDigest`, `Mac`, `Signature`, and `Cipher`, and the semantics of `init`, `update`, `digest`/`sign`/`verify`/`doFinal`, and `reset`.
- Choose a safe ownership scope for cryptographic objects in multithreaded execution.
- Recognize failures caused by providers/defaults, parameters, encodings, key formats, and reused nonces/IVs.
- Design and test byte/algorithm contracts so multiple applications, versions, or providers can interoperate.


## 2. Separating Provider Configuration from Per-Operation State

In JCA/JCE, `getInstance` creates an engine (e.g., `Cipher`, `Mac`, `Signature`) via a provider's implementation. The **provider registry** describes JVM-level capabilities/configuration, whereas an **engine instance** holds the key, mode, parameters, and in-progress data of **one specific operation**. The same provider can back many independent engines; sharing one in-progress engine instance across two requests is a completely different matter.

| Boundary | Shareable under policy? | Risk if confused |
| --- | --- | --- |
| Algorithm names, immutable config, registered providers | Yes | Config drift across environments causes behavioral differences |
| Key objects / handles | Conditionally per provider and usage permissions | Key exposure, HSM incompatibility, or mid-flight key changes |
| In-progress `MessageDigest`, `Mac`, `Cipher`, `Signature` | Not by default; should be owned per task | Interleaved `init/update/final` from another request, causing wrong results or state leakage |
| `SecureRandom` | API permits concurrent use | Still need to measure contention/entropy per provider |

Therefore, checking **protocol compatibility** and **state ownership** must go hand in hand: the right algorithm/byte format cannot save a computation interleaved by another thread; isolating engines per request also cannot fix two parties disagreeing on IV, AAD, key, or signature format.

## 3. What Layers Does “Compatibility” Actually Encompass?

| Layer | What must agree | Incompatibility example |
| --- | --- | --- |
| **API / support capabilities** | Provider has the required algorithm and operation; JDK/library/hardware supports it | JVM A has AES/GCM; provider B does not support that configuration or key size. |
| **Algorithm and mode** | Name/variant/algorithm for signing, encryption, MAC, digest | Same AES key, yet one side uses GCM and the other uses CBC; or one signs with RSASSA-PSS while the other verifies with SHA256withRSA/PKCS#1 v1.5. |
| **Cryptographic parameters** | Nonce/IV, tag length, salt, iteration count, padding, hash/MGF, and matching params | One side uses a 128-bit GCM tag, the other interprets 96 bits; RSA-PSS uses different salt lengths. |
| **Input bytes** | UTF-8, field ordering, canonical serialization, AAD, line endings, exact signed bytes | Both sides think they sign “the same JSON” while whitespace, key order, or Unicode encoding differs. |
| **Wire format** | How version, key ID, IV, ciphertext, tag, and signature are framed; Base64/hex if any | One side sends ciphertext||tag while the other expects tag in a separate field; IV position swapped. |
| **Key format / trust** | Algorithm, intended usage, how public/private/secret keys are imported, trust anchor | Public key in X.509 SubjectPublicKeyInfo yet the receiver reads it as PKCS#8 private key. |
| **Lifecycle and versioning** | Message version, key rotation, validity period, algorithm acceptance policy | Legacy records lack a key ID once the application has rotated keys. |
| **Execution environment** | Provider, policy/FIPS, token/hardware, operational capability | HSM forbids exporting private keys, or one provider rejects keys belonging to another provider. |

**Functional compatibility** means consistently decrypting/verifying when using the same protocol; **security** additionally requires sound algorithms, parameters, key sources, and usage rules. A design using ECB might be “compatible” between two providers yet fail application data security requirements.

### Practical Rules

- Require an explicit transformation, such as **AES/GCM/NoPadding**, rather than **AES** alone and relying on provider default mode/padding.
- Specify signature algorithms together with exact parameters. With **RSASSA-PSS**, agree on hash, MGF, salt length, and trailer field; with **RSA-OAEP**, agree on the OAEP parameters used by the protocol.
- Separate **wire/storage format** from engine objects. Never try to serialize an active `Cipher`/`Signature` object or rely on provider internal state as an interchange format.
- Define encoding, field ordering, framing/version, and byte sequences before signing or computing a MAC. Semantically equal JSON objects are not automatically identical at the byte level.
- Treat capability conditionally: **`getInstance` succeeding does not prove `init`/`doFinal` will succeed** with specific keys, tags/IVs, or parameters. Test the exact deployment combination.


## 4. The Unit of Safety Is the Whole Operation Sequence, Not Each Method Call

Individual engine lifecycles were covered in detail in the previous lesson. From a **multithreading** perspective, what matters even more is that a **cryptographic transaction** must retain exclusive ownership of the engine from initialization through the final result. Even when `doFinal` or `digest` auto-resets state, they **do not automatically lock the entire operation sequence** against other threads.

| Engine | State mutated across calls | Race when sharing one instance | Safe ownership pattern |
| --- | --- | --- | --- |
| `MessageDigest` | Bytes passed to `update`, digest state | Hashing mixed data from another request; another thread calls `digest/reset` early | One instance per hash operation |
| `Mac` | Initialized key, bytes accumulating for MAC | Interleaved `update/doFinal` produces wrong MAC even with the same key | One instance per message; may reuse **sequentially** once API resets |
| `Signature` | `initSign/initVerify` mode, key, pending message | Another request changes mode/key or appends bytes before `sign/verify` | One instance per signature |
| `Cipher` | Encrypt/decrypt mode, key, IV, AAD, buffers, authentication state | Key/IV overwritten, plaintext/ciphertext interleaved; severe GCM failure | One instance per message, fresh IV for every GCM **encryption** under the same key |
| `KeyAgreement` | Private key and active agreement phase | Peer public keys from two sessions mixed | One instance per agreement session |
| `SecureRandom` | Implementation-owned PRNG state | **API-documented exception:** object may be called concurrently | Shareable after checking performance/provider behavior |

### 4.1. Why Isn't Synchronizing Each Method Call Enough?

Suppose thread A runs `mac.update(a)`, then thread B runs `mac.update(b)`, and finally thread A calls `mac.doFinal()`. **Even if each individual method is synchronized**, the value A computes may be the HMAC of `a || b`, not `a`. If you genuinely share one instance, you must synchronize the entire `init → update → doFinal` sequence as a single transaction; creating a dedicated instance is usually simpler.

With GCM, there is also the invariant **never duplicate `(key, IV)` across encryptions**. A race in the nonce allocator can cause a cryptographic break even when every `Cipher` instance is completely isolated; IV allocation is tested in section 8. For AEAD decryption, never release plaintext before verifying the tag.

### 4.2. Why Is `SecureRandom` an Exception?

Java specifies `SecureRandom` as thread-safe, either through a thread-safe SPI or wrapper-managed synchronization. However, a provider may wait for entropy/reseeding or suffer contention. This guarantee **does not extend** to `MessageDigest`, `Mac`, `Signature`, `Cipher`, or `KeyAgreement`; those engines require explicit ownership policies.

## 5. Typical Concurrency Failure Scenarios

### 5.1. Placing a Stateful Engine in a Static Field or Singleton

A service in a web framework is typically a singleton, meaning many requests invoke the same service instance concurrently. If the service holds a `Cipher`, `Mac`, or `MessageDigest` as a **shared field**, `update`/`init`/`doFinal` calls mutate the same state. Under light load the program may appear normal; under heavy load it yields wrong outputs, sporadic exceptions, or risk of cross-request data leakage.

**Better design:** each request handler creates/initializes an independent engine, uses it end-to-end, and discards it; share only immutable configuration, key ID metadata, and key handles with appropriate concurrency contracts.

### 5.2. Synchronizing Individual Methods While Forgetting the Whole Transaction

If you only have `synchronized(update)` and `synchronized(doFinal)` individually, another thread can still interleave between the two calls. To share a stateful engine via locking, the entire operation sequence must be serialized. That is hard to maintain, deadlock-prone, and sacrifices parallelism. Per-task instances are usually simpler.

### 5.3. Using `ThreadLocal` or an Object Pool and Forgetting to Reset

**ThreadLocal** can keep one engine per thread, yet it does not automatically handle reuse across requests on the same thread pool. You must `init`/reset properly to avoid leftover context from a previous user; consider calling `remove` when no longer needed and managing thread lifecycles. An object pool additionally requires a checkout → initialize → process → error-handling → return workflow, checking provider type, keys, and parameters.

Specifically for **AES-GCM**, reusing a `Cipher` in `ThreadLocal` does not automatically generate a fresh nonce; **you must change the IV and re-initialize before every encryption**. Never retain the previous request's IV for the sake of optimization.

### 5.4. Sharing Mutable Buffers

Even if every thread has its own engine, bugs can still arise if they operate concurrently on a shared **`ByteBuffer`**, a `byte[]` being mutated, or a mutable parameter set. One task modifying input after another starts signing/HMAC can cause signature mismatches. Share only truly immutable data, transfer buffer ownership explicitly, or copy when necessary.

### 5.5. Nonce Collisions Across Threads or Application Instances

If two threads read the same counter value due to unsynchronized read/modify/write, they may reuse the same IV. Using **`AtomicLong`** or a unique allocator prevents collisions **within the scope that allocator actually governs**. That is **not enough** if multiple JVMs/containers share the same key while each starts its counter at 0.

A production IV/nonce strategy must be designed **per key** and cover restarts, multiple nodes, backup/restore, and expected message volume. If using random 96-bit IVs, evaluate collision probability and enforce per-key message limits per algorithm guidance; do not call a small probability an absolute guarantee. Never use raw timestamps, `Random`, or a fixed IV as a nonce generation scheme.

### 5.6. “Mismatching Results” Caused by Inconsistent Data and Providers

Even with zero data races, two systems can produce different signatures/MACs due to charsets, field order, JSON canonicalization, salt length, tag length, or different algorithm variants. **Do not blame every `BadPaddingException`, `AEADBadTagException`, or `Signature.verify(false)` on concurrency.** First verify the exact byte protocol and key ID, then isolate concurrency bugs.

## 6. Safe Ownership Model: Shared Config, Per-Task Engines

| Component | Shareable? | Conditions |
| --- | --- | --- |
| Algorithm/transformation `String`, immutable config parameters | Yes | Well-defined and never mutated mid-transaction. |
| `SecretKey`/`PublicKey`/`PrivateKey` | Conditionally | Key object/handle and provider support the chosen usage; enforce permissions and key lifecycle; never mutate source bytes or casually share private key material. |
| `SecureRandom` | Yes | API guarantees thread safety; benchmark throughput/latency of the specific provider. |
| `MessageDigest`, `Mac`, `Signature`, `Cipher` for independent requests | **Keep separate** | Create a dedicated engine per operation so state is never shared. |
| IV counter, key-version state | Yes with properly scoped synchronization | Must guarantee uniqueness/consistency across workers/processes sharing the key. |
| Byte arrays holding plaintext/keys/material | With care | Mutable; control ownership, copying, and zeroing when appropriate. |
| Provider configuration / Security provider order | Runtime configuration | Establish at startup and treat as a deployment contract; do not mutate the provider list per request. |

**Pattern for multithreaded handlers:**

1. Explicitly determine operation, algorithm, key ID/version, nonce/AAD, and request input bytes.
2. Create a new engine via **`getInstance`** (and provider if pinning is truly required).
3. Initialize with the right key and parameters for the request.
4. Execute the entire `update`/finalize sequence within **the same task/thread owning the engine**; never expose the engine via a singleton.
5. Return **result bytes plus format metadata**, never the `Cipher`/`Mac`/`Signature` object.
6. Handle exceptions without continuing to use errored state; release resources/close sessions when required by the API/provider.
7. Protect key lifecycle, check authorization, and audit appropriately at the application layer.

A per-operation design is usually the safe starting point. **Optimize with reuse only after profiling performance, verifying provider contracts, and controlling the full lifecycle.**

## 7. Java 17+ Example: Running Multiple SHA-256 and HMAC Tasks in Parallel

The program launches **32 tasks** in a thread pool. Each task uses its **own `MessageDigest`** and **own `Mac`**, then compares against two standard test vectors (fixed input and expected output). The final section verifies that `digest()` and `Mac.doFinal()` reset state when reused **sequentially**.

Create the file **`ConcurrentJcaStateDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class ConcurrentJcaStateDemo {
    private static final byte[] HASH = HexFormat.of().parseHex(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    private static final byte[] HMAC = HexFormat.of().parseHex(
            "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8");

    private static boolean calculate() throws Exception {
        byte[] abc = "abc".getBytes(StandardCharsets.US_ASCII);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        boolean hashOk = Arrays.equals(HASH, digest.digest(abc));

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                "key".getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] data = "The quick brown fox jumps over the lazy dog"
                .getBytes(StandardCharsets.US_ASCII);
        boolean macOk = Arrays.equals(HMAC, mac.doFinal(data));
        return hashOk && macOk;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<Boolean>> futures = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                futures.add(pool.submit(() -> calculate()));
            }
            int ok = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    ok++;
                }
            }
            System.out.println("32 tasks correct: " + ok + "/32");
        } finally {
            pool.shutdown();
        }

        Mac sequential = Mac.getInstance("HmacSHA256");
        sequential.init(new SecretKeySpec(
                "key".getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] bytes = "abc".getBytes(StandardCharsets.US_ASCII);
        System.out.println("Mac doFinal resets state: " +
                Arrays.equals(sequential.doFinal(bytes), sequential.doFinal(bytes)));

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("MessageDigest digest resets state: " +
                Arrays.equals(digest.digest(bytes), digest.digest(bytes)));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 --release 17 ConcurrentJcaStateDemo.java
java ConcurrentJcaStateDemo
~~~

Output:

~~~text
32 tasks correct: 32/32
Mac doFinal resets state: true
MessageDigest digest resets state: true
~~~

### What the Example Demonstrates

1. **Each `calculate()` call creates its own engines**, so `update`/`digest`/`doFinal` calls across tasks never share an engine's state.
2. **Test vectors verify the exact output bytes**, rather than merely comparing two computations that could both fail due to another implementation bug.
3. **The same `Mac` or `MessageDigest` can be reused sequentially** after `doFinal`/`digest` per the API contract. That does not mean sharing that same instance across concurrent tasks is safe.
4. The string **`"key"`** is solely a public test vector, **not a production secret**. In real systems, HMAC keys must have adequate entropy and proper storage/access controls.
5. The `32/32` count only shows this example run succeeded; a single run cannot “prove” that all operations, providers, or race cases are safe.

In the example, we deliberately **avoid** creating a shared static `MessageDigest`/`Mac`. Putting them in a singleton and calling from multiple threads is not guaranteed to remain correct by the general contract.

## 8. Java 17+ Example: Multithreaded AES-GCM and Non-Repeating IVs Within the Example Scope

This is a more critical case because concurrency bugs can become cryptographic vulnerabilities even when decryption results occasionally look right.

The program generates **a fresh AES key per run**, uses a randomly generated **4-byte prefix** and an **8-byte `AtomicLong`** to issue distinct values per message within the same JVM. Each task creates its **own `Cipher`**, uses a fresh 12-byte IV and fixed AAD, then encrypts and decrypts the same message. Afterward, it tampers with the tag to verify decryption is rejected.

The goal of this IV allocator is solely to illustrate **non-repeating IVs within one run using one freshly generated key**. This is **not a production IV allocation algorithm for keys reused across restarts or multiple nodes**.

Create the file **`ConcurrentGcmDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class ConcurrentGcmDemo {
    private static final byte[] AAD =
            "orders:v1".getBytes(StandardCharsets.UTF_8);

    private record Envelope(byte[] iv, byte[] ciphertextWithTag) {}

    private static Envelope encrypt(
            SecretKey key, byte[] iv, String message) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        cipher.updateAAD(AAD);
        byte[] result = cipher.doFinal(message.getBytes(StandardCharsets.UTF_8));
        return new Envelope(iv, result);
    }

    private static String decrypt(SecretKey key, Envelope envelope)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, envelope.iv()));
        cipher.updateAAD(AAD);
        byte[] plain = cipher.doFinal(envelope.ciphertextWithTag());
        return new String(plain, StandardCharsets.UTF_8);
    }

    private static byte[] nextIv(byte[] prefix, AtomicLong sequence) {
        long number = sequence.getAndIncrement();
        if (number < 0) {
            throw new IllegalStateException("IV sequence exhausted");
        }
        return ByteBuffer.allocate(12).put(prefix).putLong(number).array();
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] prefix = new byte[4];
        new SecureRandom().nextBytes(prefix);
        AtomicLong sequence = new AtomicLong();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<Boolean>> futures = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                final int index = i;
                futures.add(pool.submit(() -> {
                    byte[] iv = nextIv(prefix, sequence);
                    String message = "order-" + index;
                    return message.equals(decrypt(key, encrypt(key, iv, message)));
                }));
            }
            int ok = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    ok++;
                }
            }
            System.out.println("Parallel GCM: " + ok + "/32");

            Envelope original = encrypt(key, nextIv(prefix, sequence), "order-99");
            byte[] modified = original.ciphertextWithTag().clone();
            modified[modified.length - 1] ^= 1;

            try {
                decrypt(key, new Envelope(original.iv(), modified));
                System.out.println("Error: modified ciphertext accepted");
            } catch (AEADBadTagException expected) {
                System.out.println("Bad tag: rejected");
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 --release 17 ConcurrentGcmDemo.java
java ConcurrentGcmDemo
~~~

Output:

~~~text
Parallel GCM: 32/32
Bad tag: rejected
~~~

### Carefully Read What Is and Is Not Guaranteed

- **Dedicated `Cipher` per operation:** two tasks never call `init`/`updateAAD`/`doFinal` on the same `Cipher` instance.
- **Reusing an AES key across operations is a valid design**, provided **every AES-GCM encryption with that key uses a unique IV**. `AtomicLong` guarantees non-repeating numbers within the example's counter scope; the prefix bytes stay unchanged during the run.
- **The key is freshly generated at runtime**. In deployments with long-lived keys, multiple JVMs, restarts, or snapshot restores, an in-memory counter gives no global uniqueness guarantee. Design an IV allocator coordinated with key versions and usage limits per algorithm guidance.
- **`Envelope`** is a record holding `byte[]` references: a record does not make `byte[]` deeply immutable. In the example, buffers are only read or cloned before modification; in real applications, control ownership, copying, and concurrent mutation.
- **`CiphertextWithTag`** is the byte sequence returned by JCE GCM with the tag appended to the ciphertext. When storing or transmitting, define the format clearly (version, key ID, IV length, IV, ciphertext/tag, AAD rule); the recipient cannot guess these values.
- **AAD** is unencrypted yet authenticated. If the recipient passes different AAD, the tag fails validation. `AEADBadTagException` does not uniquely prove an attacker is present; it can also stem from corrupted data, wrong key, wrong IV, or wrong AAD.

The example illustrates only concurrency, state, and integrity. Production data protection also requires KMS/secret management, per-key data volume limits, rotation, access policies, and legacy message decryption.

## 9. Designing Formats So Providers and Application Versions Interoperate

**Do not transmit engine objects; transmit explicitly defined data and parameters.** Example for AES-GCM:

~~~text
Envelope V1 (application-defined format, design example only)
  version:          1 byte
  keyIdLength:      1 byte
  keyId:            UTF-8 bytes, keyIdLength bytes
  iv:               12 bytes
  ciphertextAndTag: remainder (16-byte tag at the end)
  AAD:              bytes defined separately by protocol contract
~~~

The layout above is merely an **illustrative protocol proposal**, not a JCA-standardized format. If implemented, define length limits, malformed-input handling, version upgrades, and which bytes belong to AAD to protect metadata against tampering. Never allow critical key ID/tenant ID values to be altered without authentication or verification against trusted context.

A record typically needs:

1. **Version:** allows reading legacy data when packaging or supported algorithms change.
2. **Key ID / key version:** selects the right key during rotation; verify authorization to use the key and never let untrusted IDs grant arbitrary key access.
3. **Algorithm parameters:** IV, tag length, and required parameters. May be fixed per version to reduce metadata overhead, provided it is documented in the specification.
4. **Payload:** ciphertext and tag, or signature/MAC, in an agreed format/encoding.
5. **AAD / canonicalization:** specifies the exact bytes treated as authenticated data.
6. **Validation policy:** reject unknown versions, invalid keys, and bad tags/signatures; never auto-fallback to weak mechanisms.

### Can Keys Be Used Across Different Providers?

JCA aims for interoperability across implementations, yet **you should not assume every `Key` object transfers to every provider**.

- Standard public keys can typically be represented in **X.509 `SubjectPublicKeyInfo`** format; software private keys in **PKCS#8** if exportable. Use **`KeyFactory`** with the appropriate key spec.
- `SecretKeySpec` can construct a symmetric key from bytes, whereas an **HSM/PKCS#11** key may be a non-exportable handle bound to its provider/token.
- `Key.getEncoded()` **can return `null`** when a key does not permit encoded export. Never rely on `getEncoded()` as a universal step to “migrate” private keys.
- When passing a key to a new provider, still verify algorithm, intended purpose, policy, and `init` compatibility. A key from provider A is not automatically compatible with every API/provider B.

### Do Hashes, MACs, and Signatures Need Formatting?

Yes. For instance, SHA-256 produces **32 bytes**, yet another party may display lowercase hex, uppercase hex, or Base64: those are different representations of **the same bytes**. HMAC also requires agreeing on input bytes and computation order. Digital signatures further have algorithm-specific signature encodings (e.g., distinct ECDSA signature encodings cannot be treated as interchangeable). The name “RSA” alone does not fully specify padding, digest, and signature profile.

If signing JSON data, canonicalize using an explicit rule or sign the exact raw payload defined by the protocol; never re-serialize an object back to JSON on the receiving side and assume the bytes match the original.

## 10. Providers and Deployment Compatibility

### 10.1. Identifying Providers in Diagnostics

The statements below are an **illustrative snippet used inside a method with appropriate `throws`**, not a standalone Java program:

~~~java
var digest = java.security.MessageDigest.getInstance("SHA-256");
System.out.println(digest.getAlgorithm());
System.out.println(digest.getProvider().getName());

var cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding");
System.out.println(cipher.getAlgorithm());
System.out.println(cipher.getProvider().getName());
~~~

Printed provider names **depend on the runtime**, so do not hardcode expected output when teaching or testing cross-platform. You can inspect registered providers via **`Security.getProviders()`**. During testing, record JDK version, actual provider, algorithm/transformation, key type, and parameters; never log key contents, plaintext, or secrets.

### 10.2. Should You Specify a Specific Provider?

- **Without specifying a provider:** lets the application use the appropriate implementation on the running JVM; you must still test support preconditions and cryptographic contracts.
- **Specifying a provider:** useful when mandating an HSM, a vetted provider, FIPS/policy compliance, or verified provider-specific behavior/capabilities; may reduce portability across environments.
- Changing Security provider order, JDK configuration, or provider dependencies at runtime affects **subsequent engine creations**; existing engines do not magically switch implementations.

Do not mutate provider configuration per request to “make it work”. Choosing a provider is an architectural/deployment configuration decision and requires explicit testing.

### 10.3. Do Not Rely on Defaults

Anti-pattern: **`Cipher.getInstance("AES")`** lets the provider choose default mode/padding. That is both potentially insecure and inconsistent across environments. **`Cipher.getInstance("AES/GCM/NoPadding")`** states the requirement explicitly, though you must still align IV, tag, AAD, and format.

Similarly, specify exact HMAC algorithm names, signature algorithms, and associated parameters; avoid undocumented, uncontrolled fallbacks like “if standard signing fails, switch to an older weaker algorithm”.

## 11. Proper Testing: Separating Compatibility Tests from Concurrency Tests

| Test group | How to execute | Bugs caught |
| --- | --- | --- |
| **Known-answer test** | Fixed input/key/params against expected digest/HMAC/ciphertext when standard vectors exist | Wrong algorithm, encoding, padding, profile, implementation. |
| **Cross-provider / cross-version** | Provider A produces, provider B reads/verifies; reverse direction where applicable | Different key/signature formats, modes, parameters, support capabilities. |
| **Tamper / negative test** | Flip 1 bit of ciphertext/tag/AAD, swap signature/key, wrong key ID | Missing tag/signature verification, improper error handling/fallback. |
| **Concurrency / stress test** | Run hundreds/thousands of independent tasks with expected outputs across multiple threads | Races on shared engines/buffers/counters, mixed request data. |
| **Lifecycle test** | `init` → `update` → `doFinal`; sequential reuse; trigger exception then re-initialize | Misunderstood reset, wrong mode usage, reusing errored state. |
| **Nonce / key lifecycle test** | Concurrent runs across nodes, restarts/snapshots, key rotation | Duplicate IVs per key, old key IDs failing decryption, inconsistent keys. |
| **Runtime matrix** | Test across JDK environments, providers, FIPS/HSM, policies, key lengths | `NoSuchAlgorithm`/`NoSuchPadding`/`InvalidKey`/`InvalidAlgorithmParameter` in production. |
| **Performance & liveness** | Measure throughput, contention, provider locks, HSM session pools, entropy waits | Bottlenecks, starvation, timeouts, and `getInstance`/`init` overhead. |

A green stress test **does not prove the absence of data races**. Proving design safety relies first on ownership, API contracts, and invariants (such as one IV per encryption), followed by tests to catch implementation bugs.

### Checklist for Reviewing a Multithreaded Service

- Is any stateful engine stored in a singleton field/static field or shared across requests?
- Does each task exclusively own the entire `init` → `update` → finalize sequence?
- Can input buffers, key parameters, or IV/AAD be mutated by another thread mid-processing?
- For AES-GCM, can you prove or evaluate by design **no `(key, IV)` reuse** across scaling and restarts?
- Is there a canonical byte protocol: charset, fields, version, key ID, tag/padding, parameters, and ordering?
- Are there negative tests for bad data, wrong keys, and replay where required by the protocol?
- Have you tested on real target environments/providers and tracked provider/JDK changes?
- Are secrets kept out of logs, private/secret keys protected, and access properly restricted?

## 12. Distinguishing State Errors, Support Errors, and Data Errors

| Symptom | Where to investigate |
| --- | --- |
| **`NoSuchAlgorithmException`** or **`NoSuchPaddingException`** | Does the provider supply the exact algorithm/transformation name? Do JDK and security policies differ? |
| **`InvalidKeyException`** | Are key size, key type, purpose, and import/provider handle valid? |
| **`InvalidAlgorithmParameterException`** | Do IV, tag length, and PSS/OAEP/GCM parameters match the contract/provider? |
| **`IllegalStateException`** during update/finalize | Was `init` called? What is the current mode? Did another thread re-init or finalize the same engine? |
| **`AEADBadTagException`** | Wrong key/IV/AAD, corrupted or tampered ciphertext/tag; check format, byte serialization, and nonce. |
| **`Signature.verify` returns `false`** | Do public key, input bytes, algorithm/profile, signature encoding, and parameters match? |
| **Errors appearing only under high load** | Singleton engine/buffer, `ThreadLocal` reuse, IV counter, provider/HSM contention, key rotation race. |

Do not include detailed error messages containing keys, plaintext, or sensitive metadata in client-facing API responses. Log technical causes at a level sufficient for diagnostics, with request ID/approved algorithm version, never logging secrets.

## 13. A Practical Java Application Design

Suppose you have a concurrent webhook verification web service:

1. Each request carries exact **raw payload bytes**, signature/MAC, key ID, and timestamp per the agreed protocol.
2. The server validates format, payload size limits, expiration window, and replay/idempotency as required.
3. The key lookup component accepts the key ID and returns the permitted key/version; provider configuration is fixed at deployment.
4. The service creates a **new `Mac` or `Signature` instance inside the method**; initializes it with the right key, updates over the defined raw/canonical bytes, and checks the result.
5. Only after message authentication succeeds does execution proceed to business logic and authorization checks.
6. At the business layer, handle requests idempotently so valid duplicate deliveries do not create duplicate transactions.
7. When changing providers/JDKs, rerun compatibility vectors, negative tests, and concurrency tests before rollout.

Similarly, for a data encryption service, **each encryption operation** needs a `Cipher` with the right key/IV/AAD; records must store versioned decryption metadata, while IV management and key lifecycle must remain safe under concurrent load, restarts, and multiple instances.

## 14. Self-Check Questions

**1. `Mac.doFinal()` resets to the post-`init` state. Can one `Mac` instance be shared across multiple concurrent requests?**  
That does not follow. Reset supports **sequential reuse**; `update` and `doFinal` sequences across threads can still interleave. Create a separate `Mac` per task.

**2. Why can the same AES-GCM program running on two JVMs fail to interoperate?**  
Having the same transformation is not enough. Both sides must agree on key, IV, tag length, AAD, and byte format; each side's provider must also support that configuration.

**3. `Cipher.doFinal()` resets state, so is it safe to reuse the GCM `Cipher` that just encrypted to encrypt another message?**  
No if still using the old key/IV pair. You must configure a valid new IV unique for that key; typically you create a new `Cipher` for the next operation.

**4. Can one `SecureRandom` be placed in a singleton for threads to share?**  
Yes, Java specifies `SecureRandom` as thread-safe. Still evaluate throughput, blocking/reseed behavior, and the actual provider. Do not apply the same conclusion to `Cipher`, `Signature`, `Mac`, or `MessageDigest`.

**5. Does `Signature.verify(false)` definitely prove a race condition?**  
No. The mismatch could also stem from the public key, algorithm/parameters, signature encoding, or differing input bytes. Check the compatibility contract first before analyzing concurrency.

**6. Is an `AtomicLong` generating unique nonces in one JVM sufficient for a cluster sharing the same key?**  
No. Another node can reuse the same counter sequence; restarts or state restores can do the same. Uniqueness must be guaranteed across **the entire scope sharing that key**.

**7. Why shouldn't you rely on `getEncoded()` for every private key?**  
HSM/PKCS#11 keys may be non-exportable key handles. Key exportability depends on provider, key type, and security policy; `getEncoded` can return `null`.

## 15. Takeaways and Official References

Compatibility in JCA is the ability for parties to agree on **algorithm + parameters + bytes + key/format + protocol/version + provider policy**. Correctness under concurrency depends on **stateful engine ownership**, call ordering, and security invariants such as **never repeating key/IV per AES-GCM encryption**. Good design typically shares configuration and controlled key management, creates dedicated engines per task, and tests compatibility in the real deployment environment.

Standard API documentation for JDK 21:

- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html)
- [MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
