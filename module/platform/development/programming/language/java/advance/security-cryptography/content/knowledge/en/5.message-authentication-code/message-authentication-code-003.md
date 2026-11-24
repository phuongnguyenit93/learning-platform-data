# 5.3 Using Mac with init, update, doFinal, and State Management

In the Java Cryptography Architecture (JCA), the `javax.crypto.Mac` class computes a **Message Authentication Code (MAC)**: a short value derived from a **secret key** and the **exact byte sequence of a message**. When the receiver holds the corresponding key, recomputes the MAC, and compares properly, they can detect whether a message was modified or created by a party that does not possess the key under the algorithm's security assumptions.

This lesson focuses on the **lifecycle and state** of `Mac` in Java: `getInstance` → `init` → `update` → `doFinal`, when to use `reset`, how to handle multiple messages, how to feed data in chunks, and how to verify a MAC. Understanding state properly is essential: the same `Mac` object can be reused sequentially **after completion and proper reset**, yet it is very easy to produce wrong MACs if bytes from two messages get mixed or an instance is shared across threads.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain how a MAC protects **integrity and shared-key authentication**, differing from plain hashes, digital signatures, and data encryption.
2. Initialize `Mac` with an HMAC algorithm such as `HmacSHA256`, an appropriate `SecretKey`, and a well-defined protocol.
3. Use `update(byte)`, `update(byte[])`, `update(byte[], offset, len)`, and `update(ByteBuffer)` to feed data incrementally in chunks.
4. Distinguish `doFinal()`, `doFinal(byte[])`, `doFinal(byte[], int)`, and the **automatic reset** behavior upon completion.
5. Know that `reset()` discards data **that was updated but not yet finalized**, whereas `init(...)` sets the key/parameters and starts a new state.
6. Avoid unsafe `Mac` reuse across requests/threads, handle exceptions, and enforce message boundaries.
7. Verify tags by recomputing the MAC over the exact bytes and using a comparison appropriate for security contexts; separate MAC verification from replay protection.
8. Test an HMAC-SHA-256 implementation with standard test vectors, then apply it to file/API processing in Java systems.

## 2. MAC, HMAC, Hash, and Digital Signatures

General notation:

```text
tag = MAC(secretKey, messageBytes)

sender:   messageBytes + tag
receiver: recomputedTag = MAC(secretKey, receivedMessageBytes)
          -> verify received tag against recomputedTag
```

A MAC is the result of a **keyed** computation, unlike an unkeyed `MessageDigest`. HMAC is a standardized way to build a MAC from a hash function; `HmacSHA256` uses SHA-256 inside the HMAC construction. SHA-256 alone **does not replace HMAC** for message authentication, and you should not design a MAC yourself by concatenating `SHA256(key || message)`.

| Tool | Has Secret Key? | Purpose | Key Limitation to Remember |
| --- | --- | --- | --- |
| `MessageDigest` / SHA-256 | No | Produces a digest of a byte sequence | Anyone can compute a new digest after modifying data; does not authenticate sender |
| `Mac` / HMAC-SHA-256 | Yes, shared key | Detects tampering and authenticates messages between key holders | Both sides with the key can create the MAC; provides neither confidentiality nor asymmetric non-repudiation |
| `Signature` (e.g., Ed25519) | Private key to sign, public key to verify | Digital signature verifiable with a public key | Requires key-pair management and public key authentication |
| `Cipher` / AEAD (e.g., AES-GCM) | Yes | Provides confidentiality and/or authenticity via authenticated encryption | Requires proper management of keys, nonces, AAD, and tags |

**A MAC does not encrypt data.** The message can still be read in transit; use TLS or appropriate encryption when confidentiality is required. Nor does a MAC **prevent replay by itself**: an attacker can resend an unmodified message and its valid tag if the protocol lacks nonces, counters, timestamps, or idempotency and lifecycle validation.

Because both parties hold the HMAC key, a valid MAC shows that the data came from **a party holding the key** (assuming a secure algorithm and implementation), not which specific individual sent it when multiple components share the key. To reason about business authorization, you still need identity, authorization, key separation, and contextual auditing.

## 3. Java API Architecture: Mac Is a Stateful Object

The relevant APIs are in JCA/JCE:

```java
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
```

This is an illustrative import set, not a standalone program. Common algorithm name: `HmacSHA256`; `HmacSHA384`, `HmacSHA512`, and others exist depending on the provider. **Do not accept arbitrary client-chosen algorithm names** without validation, and do not use HMAC-SHA1 in new designs unless an evaluated compatibility requirement demands it.

Logical lifecycle:

```text
                  Mac.getInstance("HmacSHA256")
                               |
                               v
                    [Uninitialized with key]
                               |
                         init(secretKey)
                               |
                               v
                     [Initialized, empty]
                       /             \
                 update(...)       doFinal(input)
                     |                   |
                     v                   |
                 [Accumulating bytes]    |
                   /           \         |
             update(...)     doFinal()   |
                 |              |        |
                 v              v        v
          [Accumulating]   [Emit tag, reset]
                                 |
                                 v
                         [Initialized, empty]
```

This model describes the **logical content processed by the object**, without exposing provider-internal buffers. A MAC can be computed incrementally in chunks; the program does not need to allocate a single byte array holding an entire large file.

### Distinguishing each method

| Method | Effect | State After Call |
| --- | --- | --- |
| `Mac.getInstance("HmacSHA256")` | Obtains an implementation from a provider | Object exists, **cannot call update/final until initialized** |
| `mac.init(key)` | Supplies the key and initializes MAC computation state | Initialized with no message bytes; prior pending data is discarded on successful re-init |
| `mac.init(key, params)` | Initializes with algorithm parameters when supported | Fresh state with key/params; standard HMAC typically needs no extra parameters |
| `mac.update(byte)` | Feeds a single byte into the current message | Accumulating data |
| `mac.update(byte[])` | Feeds the entire byte array into the current message | Accumulating data |
| `mac.update(data, offset, len)` | Feeds a specific byte slice into the current message | Accumulating data; avoids creating a subarray |
| `mac.update(ByteBuffer)` | Feeds bytes from current position to buffer limit | Buffer position advances to limit; MAC accumulates those bytes |
| `mac.doFinal()` | Computes the tag of **all updated bytes** | Automatically resets to the state after the most recent `init` |
| `mac.doFinal(input)` | Updates with **all of input**, finalizes, returns tag | Automatically resets to the state after `init` |
| `mac.doFinal(output, offset)` | Writes tag into output array starting at offset; returns void | Automatically resets to the state after `init`; output needs `getMacLength()` bytes |
| `mac.reset()` | Discards pending updated data | Initialized, empty, **retaining the same key/parameters** |
| `mac.getMacLength()` | Returns tag length in **bytes** | Does not modify message data |
| `mac.getAlgorithm()` | Returns the algorithm name used by the instance | Does not modify message data |

**Two key behaviors to remember:**

- After finishing, `doFinal()` and its overloads **automatically reset** the object so it can compute a new message with the key/parameters supplied to `init`. You do not need to re-call `init` with the same key after every `doFinal` just to reset, though in isolated request handlers it is often cleaner to create a new instance.
- `reset()` **does not return a tag**; it only discards data passed to `update`. Calling `reset` before `doFinal` drops pending data. `reset` does not change the key and does not wipe the key from memory.

Calling `update` or `doFinal` before initialization can throw `IllegalStateException`. Calling `init` with a wrong or unsupported key type can throw `InvalidKeyException`; using `init(key, params)` can involve `InvalidAlgorithmParameterException`. If the output buffer lacks capacity, `doFinal(output, offset)` can throw `ShortBufferException`. Validate and handle errors at the application boundary; never swallow exceptions and treat the MAC as valid.

## 4. Mini Examples: Understanding update and doFinal Precisely

Assume `mac` has been initialized with HMAC-SHA-256 and a valid key.

### 4.1 Multiple updates form one concatenated message

```java
mac.update("order=".getBytes(StandardCharsets.UTF_8));
mac.update("123".getBytes(StandardCharsets.UTF_8));
byte[] tag = mac.doFinal();
```

This is an illustrative snippet (`mac` and imports are already present). Here the tag equals the HMAC of the exact UTF-8 byte sequence `order=123`. **Two `update` calls do not produce two independent tags**; they build a single message.

### 4.2 doFinal(input) appends input to already updated bytes

```java
mac.update("A".getBytes(StandardCharsets.UTF_8));
byte[] tag = mac.doFinal("B".getBytes(StandardCharsets.UTF_8));
```

This tag authenticates `AB`, **not just `B`**. If the intent is to compute a MAC only for `B`, there must be no pending `A` left over from a prior operation. After `doFinal`, a new `mac.doFinal("B".getBytes(UTF_8))` on the same reset object processes `B` alone.

### 4.3 reset discards pending data

```java
mac.update("draft".getBytes(StandardCharsets.UTF_8));
mac.reset();
byte[] tag = mac.doFinal("final".getBytes(StandardCharsets.UTF_8));
```

The resulting tag is the HMAC of `final`. This is how you cancel an incomplete operation before reusing **the same key**. It neither replaces creating a fresh context for independent requests nor implies that sensitive key material was wiped from the JVM.

### 4.4 init starts a fresh lifecycle

```java
mac.init(otherSecretKey);
mac.update(messageBytes);
byte[] tag = mac.doFinal();
```

This is an illustrative snippet; `otherSecretKey` is an algorithm-compatible `SecretKey` and `messageBytes` is a `byte[]`. Re-calling `init` replaces the key/parameters and discards any previous message-processing state; do not share one `Mac` instance and swap keys across concurrent requests.

## 5. Standalone Java 17+ Example with HMAC-SHA-256 Test Vector

The example below uses the **RFC 4231 test vector**: a 20-byte key of `0b`, ASCII message `Hi There`, and expected tag `b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7`.

**Note:** the hardcoded key in the example is **for testing only**. Real systems require secret keys generated randomly from an appropriate source and protected in a secret manager/KMS/HSM or equivalent boundary.

Save as **`MacLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MacLifecycleDemo {
    private static final String ALGORITHM = "HmacSHA256";

    static Mac newMac(byte[] key) throws GeneralSecurityException {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(key, ALGORITHM));
        return mac;
    }

    public static void main(String[] args) throws Exception {
        byte[] testKey = HexFormat.of().parseHex("0b".repeat(20));
        byte[] message = "Hi There".getBytes(StandardCharsets.US_ASCII);
        Mac mac = newMac(testKey);

        mac.update(message, 0, 2);
        ByteBuffer remainder = ByteBuffer.wrap(message, 2, message.length - 2);
        mac.update(remainder);
        byte[] chunksTag = mac.doFinal();

        byte[] oneShotTag = mac.doFinal(message);
        mac.update((byte) 0x01);
        mac.reset();
        byte[] afterResetTag = mac.doFinal(message);

        boolean valid = MessageDigest.isEqual(
                chunksTag, newMac(testKey).doFinal(message));
        boolean changedValid = MessageDigest.isEqual(
                chunksTag,
                newMac(testKey).doFinal("Hi there".getBytes(StandardCharsets.US_ASCII)));

        System.out.println("Algorithm: " + mac.getAlgorithm());
        System.out.println("MAC length: " + mac.getMacLength());
        System.out.println("Tag: " + HexFormat.of().formatHex(chunksTag));
        System.out.println("Buffer consumed: " + (remainder.position() == remainder.limit()));
        System.out.println("Chunks equal one-shot: " + Arrays.equals(chunksTag, oneShotTag));
        System.out.println("Reset discards pending input: " + Arrays.equals(chunksTag, afterResetTag));
        System.out.println("Fresh verifier: " + valid);
        System.out.println("Changed message accepted: " + changedValid);
    }
}
```

Compile and run with JDK 17 or later (e.g., `javac --release 17`):

```bash
javac --release 17 MacLifecycleDemo.java
java MacLifecycleDemo
```

**Exact stdout:**

```text
Algorithm: HmacSHA256
MAC length: 32
Tag: b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
Buffer consumed: true
Chunks equal one-shot: true
Reset discards pending input: true
Fresh verifier: true
Changed message accepted: false
```

Explanation:

1. `newMac` creates a new instance and initializes it with the HMAC key.
2. `mac.update(message, 0, 2)` feeds `Hi`; `ByteBuffer.wrap(message, 2, message.length - 2)` supplies the remaining ` There`. `update(ByteBuffer)` processes from `position` to `limit` and advances the position to limit.
3. `doFinal()` produces the 32-byte tag matching RFC 4231. After finalizing, `Mac` auto-resets, so the immediately following `doFinal(message)` computes the MAC of `Hi There` alone and matches the previous tag.
4. `mac.update((byte) 0x01)` attempts to feed another byte, but `reset()` discards it. Thus the post-reset tag still matches.
5. The verifier creates a fresh `Mac` with the same key and computes the MAC over the exact message. Changing `Hi There` to `Hi there` alters the bytes; verification fails.
6. `HexFormat` was added in Java 17; `Arrays.equals` here only checks **equivalence in the demo**. When authenticating tags, the example uses `MessageDigest.isEqual` on the two byte arrays.

This is a **public test vector**: do not treat the key or tag values in the example as real secrets. When using tags in APIs, they are commonly transmitted in Base64 or hex per protocol and decoded back to bytes before verification.

## 6. Managing State Across Multiple Messages

### 6.1 One Mac does not equal one request

`Mac` holds mutable state. A single instance is not designed for multiple threads to interleave `update` calls without synchronization. If requests A and B share one instance, the following sequence can occur:

```text
A: update(bytesA_1)
B: update(bytesB_1)
A: update(bytesA_2)
B: doFinal()
A: doFinal()
```

Then B's tag may include bytes from A, and A's state gets reset by B; the outcome depends on interleaving, producing hard-to-reproduce authentication failures. Even if code uses `synchronized` to avoid data races, interleaving request B into A's update sequence still breaks message boundaries unless the entire session is locked. Simple, verifiable implementation practices:

- **Create a new `Mac` instance for each computation** or each request; initialize with an appropriately authorized key.
- Keep `Mac` **local to a method** or sequential processing scope. Never hold a `static Mac` reused across all requests.
- If implementing a pool purely for performance, enforce clear ownership, exclusive checkout, cleanup/reset, key isolation, and exception handling; optimize only after benchmarking and security review.
- `Mac.clone()` may be supported by some providers, but it is not a cross-provider guarantee, and cloning an already-updated state also copies pending data; do not use `clone` as a default thread-safety mechanism.

### 6.2 doFinal and reset per business unit

Suppose a system processes two files or two webhooks:

```java
Mac mac = newMac(key);
byte[] tagA = mac.doFinal(fileA);
byte[] tagB = mac.doFinal(fileB);
```

This is an illustrative snippet (`key`, `fileA`, `fileB` are method-scoped variables, `newMac` as in the sample). Two separate tags are produced because `doFinal` resets. By contrast:

```java
Mac mac = newMac(key);
mac.update(fileA);
mac.update(fileB);
byte[] combinedTag = mac.doFinal();
```

The second tag is the HMAC of `fileA || fileB` in the order fed. This may be right if the contract defines a multi-chunk message, but **wrong if you want two independent MACs for two files**.

### 6.3 Handling mid-operation errors

If reading a file fails after calling `update` on partial data, **do not** call `doFinal` and mark the file as authenticated; the result only reflects the bytes successfully read. Abort the operation, discard the instance, or reset under a controlled workflow before computing another message.

For example, a stream timeout does not make the `Mac` state aware that the message is "incomplete." `Mac` knows nothing about file size, message length, or message semantics unless the application provides them. Therefore, business code must confirm that **all expected bytes per the protocol were received** before treating a tag as the MAC of a complete message.

## 7. Processing Large Messages with Chunked updates

To authenticate a large file, you do not need to read the entire file into a `byte[]`. The following is an **illustrative snippet inside a method**; assume an appropriate `Path path` and `SecretKey key`, corresponding imports, and exception handling:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(key);

byte[] buffer = new byte[8192];
try (var input = java.nio.file.Files.newInputStream(path)) {
    int n;
    while ((n = input.read(buffer)) != -1) {
        if (n > 0) {
            mac.update(buffer, 0, n);
        }
    }
}
byte[] tag = mac.doFinal();
```

Points to note:

- `update(buffer, 0, n)` feeds only the **n bytes actually read** into the MAC, avoiding leftover bytes in the buffer from a previous iteration. Calling `update(buffer)` here is wrong when the final read is smaller than `buffer.length`.
- Every loop iteration contributes to **a single message**; call `doFinal` **only after** the entire file has been read.
- Enforce size limits, file read permissions, checks ensuring the file is not unexpectedly modified during reading, timeouts/cancellation, and an I/O error policy. Do not authenticate a file being mutated mid-read under an immutability assumption.
- If the MAC must also protect filename, tenant, content type, or metadata, include those fields in the MAC message using unambiguous serialization; computing HMAC over the file bytes alone does not protect external metadata.
- `Files.newInputStream` provides a byte stream; in HTTP APIs, the signed byte stream must match the exact raw/canonical version agreed upon by sender and receiver—never deserialize and re-serialize before verifying.

For example, when receiving a JSON webhook: if the sender defines the MAC over **raw body bytes**, the receiver must fetch those exact raw bytes to verify the MAC (along with any other fields specified by the signature spec). Adding whitespace, reordering fields, or normalizing Unicode before MAC verification can cause a tag mismatch.

## 8. Designing Keys, Algorithms, and Usage Context

### 8.1 Test keys vs. production keys

In the learning example, `"0b".repeat(20)` is an RFC 4231 key. Production systems never take keys from examples, plain passwords, or hardcoded strings in source code.

A new HMAC-SHA-256 key can be generated using `KeyGenerator`:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
generator.init(256, new SecureRandom());
SecretKey secretKey = generator.generateKey();
```

This is an illustrative snippet inside a method handling `GeneralSecurityException`. A 256-bit size is a common choice for an HMAC-SHA-256 key in new deployments, though key/algorithm requirements must be documented in policy and compatible with the provider. To use the key, call `mac.init(secretKey)`. For raw keys retrieved from a secret store, `SecretKeySpec(keyBytes, "HmacSHA256")` can be used, though wrapping bytes in this class **does not** prove the key source had sufficient randomness, access control, or safe rotation.

Key management rules:

- Generate keys with a suitable cryptographic random generator, or obtain them from an approved KMS/HSM; avoid exporting key bytes when the key management system offers a dedicated signing/MAC API.
- Protect keys in configs, logs, memory dumps, backups, and service account permissions; avoid committing keys or sending them over message queues.
- Use **key ID/version** to identify the key when verifying older messages. Maintain a plan for rotation, revocation, grace periods for old keys, and compromise response.
- Separate keys by purpose/protocol, tenant, or trust domain when isolation is required; do not use the same key for HMAC and AES or across multiple protocols without an explicit design and key derivation with clear domain separation.
- If using key derivation, use a standard KDF designed for that purpose, such as HKDF per the applicable standard; do not concatenate a key with text, hash it, and call it key management.
- Restrict which principals have permission to generate MACs: anyone holding the key can forge tags within that key's scope. Merely reading a tag does not allow forging a valid tag if HMAC and the key are secure.

### 8.2 The algorithm is part of the contract

`HmacSHA256` produces a **32-byte** tag per HMAC-SHA-256. `mac.getMacLength()` returns the length in bytes, not the number of Base64/hex characters. Hex for a 32-byte tag is 64 ASCII characters; standard Base64 encodes the same tag with a different length.

Do not unilaterally switch `HmacSHA256` to `HmacSHA512` or swap providers based on receiver preference: both parties must agree on the algorithm, key, tag length, serialization, and policy. When the protocol carries an algorithm ID on the wire, the receiver must **restrict allowed algorithms to a trusted allowlist**; never accept every algorithm proposed by the client.

Tag *truncation* is a protocol choice that must be analyzed, tested, and specified with exact length and algorithm, not "taking the first few characters for brevity." This lesson uses **the full 32-byte tag**.

## 9. How to Verify a MAC Safely

Typical verification flow:

1. Receive the message bytes in the published format. Distinguish **raw bytes** from parsed/canonicalized data.
2. Look up the key by server-controlled key ID/context; never let the request supply a raw key.
3. Create a fresh `Mac`, call `init`, and compute `doFinal(messageBytes)` or stream via `update` then `doFinal`.
4. Decode the attached tag (e.g., from Base64) to bytes; validate proper encoding and protocol-expected length.
5. Use `MessageDigest.isEqual(calculatedTag, receivedTag)` to compare the two tag arrays; handle verification failures with a uniform policy-driven response.
6. After authentication, still verify **replay protection, access permissions, message expiration, and binding to the target resource/action**.

Example inside a method that already has `key`, `messageBytes`, and `receivedTag`:

```java
Mac verifier = Mac.getInstance("HmacSHA256");
verifier.init(key);
byte[] calculated = verifier.doFinal(messageBytes);

boolean accepted = receivedTag != null
        && receivedTag.length == verifier.getMacLength()
        && MessageDigest.isEqual(calculated, receivedTag);
```

This is an illustrative snippet, not a standalone program. Length checking rejects protocol-invalid data; `MessageDigest.isEqual` is more suitable in Java than `Arrays.equals` for security tag comparison. However, **do not assume the whole endpoint runs in constant time**: key lookup, error handling, length checks, decoding, DB queries, and business logic can still exhibit timing differences. Evaluate the entire protocol if side-channels matter in your threat model.

Do not use `Arrays.equals(tag, received)` as the default way to authenticate sensitive MACs, and do not compare Base64/hex strings directly with `String.equals` when you can decode and check bytes. MAC verification must not be treated as a permission check: a valid tag can come from a client holding a shared key that is **not authorized** to act in another tenant.

### 9.1 Do not confuse byte comparison with anti-replay logic

A signed request can be replayed verbatim. For instance, `POST /pay` with a valid body and tag replayed later will **still have a valid tag**. You must bind timestamp/nonce/request ID/sequence number and operation scope into the MAC data, then enforce expiration policies, detect reused nonces, verify business idempotency, and guard against race conditions in the data store.

Merely "signing a nonce" without **persisting/checking used nonces** will not stop replays. Merely attaching a timestamp without enforcing a time window or handling clock skew is also incomplete.

### 9.2 Do not forget to define exactly what the MAC protects

For example, a token with an HMAC over `userId` that omits `role` or `tenantId`: tampering with fields outside the MAC can subvert the authentication meaning. For webhooks, if the signature covers only the body without method/path/time while the protocol requires route binding, an attacker can try replaying the same body/tag to a different endpoint.

Every format should publish: **field order, encoding, null/empty representation, version, algorithm, key ID, tag encoding, time window, nonce, and where verified identity is obtained**.

## 10. Unambiguous Byte Structure When Using Multiple updates

Because `update(partA); update(partB)` is equivalent to processing concatenated bytes, an ad-hoc string concatenation protocol can produce the same bytes for different field pairs.

Example:

```text
("ab", "c") -> UTF8("abc")
("a", "bc") -> UTF8("abc")
```

If these represent two distinct business tuples, the HMAC of the identical byte sequence will be **identical**; that is not an HMAC weakness, but a **lack of serialization boundaries**. Define an explicit format, for example:

```text
version | domain | length(field1) | field1 | length(field2) | field2
```

Length-prefix fields must specify width, endianness, and unit (bytes), all values must be encoded in an explicit charset, and the version/domain bytes must also be included in the MAC. Canonical protobuf/CBOR or an established specified format can be used; avoid inventing one if a suitable standard exists.

Across services, settle rules for Unicode normalization, JSON numbers, URL decoding, newlines, empty values, field ordering, and literal escaping. **NFC, UTF-8, canonical JSON, and canonical HTTP requests are distinct layers.** Do not assume calling `String.getBytes(UTF_8)` is enough for two systems to sign the same JSON object.

### Domain separation

With a single key or broad key hierarchy, lacking context allows a valid tag from protocol A to be accepted as valid for message B with matching bytes. Separating keys by purpose is a strong option; additionally, include a **context label and protocol version** directly in the MAC-protected data, such as an ASCII label `"invoice-webhook:v1"` alongside clearly delimited fields.

Do not allow users to freely alter purpose labels or key IDs to bypass policy. In multi-tenant systems, bind the tenant into the authenticated data and **enforce authorization** in the service. Domain separation helps prevent cross-context tag misuse, but does not replace authorization.

## 11. Special Pitfalls with State and ByteBuffer

### 11.1 ByteBuffer state

`mac.update(buffer)` only processes bytes between the `position` and `limit` of `buffer`. Upon completion, the buffer position advances to limit; never assume data from the start of the backing array was processed if position was not 0. To read the same bytes again, use `duplicate`, `rewind`, or adjust position/limit under controlled ByteBuffer rules.

In the demo, `ByteBuffer.wrap(message, 2, message.length - 2)` creates a buffer with position 2 and limit 8, so it processes the exact **remaining 6 bytes**. Do not mistake it for a new 6-byte array. When reusing buffers in an I/O pipeline, check `flip`/`clear` per the producer/consumer contract so you neither sign leftover bytes nor skip bytes.

### 11.2 doFinal output buffer

To avoid allocating a new array, `doFinal(byte[] output, int outOffset)` writes the tag into a preallocated array. The array must have room from `outOffset` for `mac.getMacLength()` bytes; this method returns `void`. Illustrative example with `mac` initialized and updated:

```java
byte[] output = new byte[mac.getMacLength()];
mac.doFinal(output, 0);
```

Do not mistake `doFinal(output, 0)` for "authenticating the output array"; this is **the destination array receiving the tag**, unlike `doFinal(byte[] input)` where the array is **the message being MACed**. This overload difference is easy to misread in code reviews.

### 11.3 reset, init, and clearing keys are different

- `reset()` only discards pending update results and returns the object to a fresh MAC state **with the same key**.
- `doFinal()` finalizes and then resets, keeping the ability to compute a new message with the same key.
- `init(newKey)` installs a new key/parameters and a fresh state upon success.
- There is no universal `Mac.destroyKey()` API guaranteeing erasure of all key copies in the provider/JVM; `SecretKey` may be managed by a provider/HSM, and clearing/revocation depends on key type, memory, object lifetime, and key management mechanisms.

For strict secret-lifecycle requirements, define the provider, key store/KMS, rotation, and disposal mechanisms clearly; never rely on `reset()` as a security operation to wipe keys.

### 11.4 Mid-stream errors and retries

For instance, a streaming system computes the HMAC of a partially read body, then retries by calling `update` with the body from the beginning **on the same un-reset Mac**. The result is the HMAC of `partial || full`, not `full`. When retrying an operation, it is best to **create a new instance** or reset under exclusive ownership, then recompute from the start. Ensure results from a failed attempt are never published.

Do not log sensitive key/tag bytes, payloads containing personal data, or entire files just to debug a failure. You may log request ID, allowlisted algorithm, non-sensitive key version, byte length, and policy-compliant error codes.

## 12. Authentication Differs from Transport Security and Authorization

A valid MAC answers the question: "Was this message created by **a party holding the key** and kept intact over the signed byte scope?" It does **not** by itself answer:

- Who is the user/client calling the API? (authentication/identity)
- What is that user permitted to do on this object/tenant? (authorization)
- Has this message already been processed before? (anti-replay/idempotency)
- Is the payload valid in schema, business logic, and resource limits? (validation)
- Is the content confidential in transit and at rest? (confidentiality)
- Has the key been leaked or shared beyond the trust boundary? (key management)

For example, with a partner webhook, after verifying the MAC you must still check tenant mapping, business order ID, order status, and duplicate-processing prevention. For authorization requests, do not trust a field like `role=admin` merely because multiple services share an HMAC key; policy must rely on trusted context and granted permissions.

## 13. Common Mistakes Table

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Forgetting `init` before `update`/`doFinal` | `IllegalStateException` or broken processing flow | Create and init `Mac` in the same tag-computation scope; fail fast |
| Using one shared `static Mac` for concurrent requests | Mixed bytes, cross-resets, race results | One dedicated `Mac` per computation/request |
| Thinking `update` produces an independent MAC each time | Concatenates multiple messages into one MAC | Call `doFinal` at exact message boundaries |
| Calling `doFinal(input)` after an unintended prior update | Tag computed over `prefix \|\| input` | Reset or create a new instance before an independent input |
| Calling `reset` before finalizing data to authenticate | Drops pending bytes | Only reset when intentionally aborting a computation |
| Retrying without reset or a new instance | HMAC of `partial \|\| retry` | Retry with a fresh context |
| Calling `getBytes()` without a charset | Bytes vary by runtime environment | Specify UTF-8 or the agreed charset |
| Re-serializing JSON before verifying a raw-body signature | Bytes differ from the original body | Verify over exact bytes per the sender's specification |
| Concatenating fields without lengths/boundaries | Two distinct tuples yield the same bytes | Canonical serialization, length-prefixing, version/domain |
| Using `Arrays.equals` / string equality to verify tags | Unsuitable for timing control goals | Decode bytes and use `MessageDigest.isEqual`, evaluate whole pipeline |
| Arbitrarily truncating tags or accepting algorithm from request | Weakened protection, protocol mismatch | Allowlist algorithms, enforce contract tag length |
| Hardcoded keys or overly broad key reuse | High forgery blast radius if key leaks | Generate keys securely, scope, rotate, use key versions |
| Using HMAC to "encrypt" | Payload remains readable | Use TLS/encryption when confidentiality is needed |
| No replay protection | Old valid message/tag can be resent | Nonce/counter/time window and duplicate-processing checks |
| Omitting permission-critical fields from the MAC | Valid tag while resource/action is altered | Cover all sensitive fields in scope and verify permissions separately |
| Treating unit tests alone as sufficient proof | Provider, keys, and wire protocol may differ in practice | Integration tests with provider, vectors, and real protocol |

## 14. Design and Testing Checklist

For a Java service computing or verifying HMACs, walk through this checklist:

1. **Algorithm:** use `HmacSHA256` chosen server-side and compatible with the partner's specification.
2. **Key:** high-entropy key, never hardcoded; clear usage permissions and rotation; key ID cannot lead to fetching the wrong key.
3. **Data:** input bytes match contract, explicit charset/serialization, never silently mutated on the verifier side.
4. **Boundaries:** one tag per **single message**; `update` in the right order, `doFinal` right after the last byte.
5. **State:** never share `Mac` across threads; reset when canceling pending work; never reuse errored state.
6. **Errors:** fail closed on invalid tag, invalid input, missing key, or provider error; never treat an incompletely read payload as authenticated.
7. **Tag check:** length/encoding per standard; `MessageDigest.isEqual` on bytes, evaluate response timing if needed.
8. **Replay protection:** stateful timestamp/nonce/idempotency with expiration per design.
9. **Authorization:** verify actor, action, and resource independently of MAC; log adequate audit info.
10. **Tests:** RFC vectors, chunked vs. one-shot, reset, single-byte flip, stream errors, metadata fields outside body, concurrent requests, and key rotation.

Minimal useful test cases:

| Case | Setup | Expected Result |
| --- | --- | --- |
| RFC 4231 vector | 20-byte `0b` key, payload `Hi There`, HmacSHA256 | Tag equals `b0344c61...e32cff7` |
| Chunked | Feed same bytes across multiple `update` calls then `doFinal` | Matches tag from `doFinal(fullInput)` |
| Post-`doFinal` | Compute same input immediately afterward | Tags match because state auto-resets |
| `reset` before final | `update(bad)`, `reset`, `doFinal(good)` | Tag equals HMAC of `good` alone |
| Single-byte flip | Change `Hi There` to `Hi there` | Verification rejects |
| Forgot `init` | Attempt update/final on uninitialized Mac | Error; no valid tag produced |
| Streaming | 20,000-byte file, read in 8192-byte chunks | Tag matches one-shot over entire file |
| Streaming error | Stream fails after partial content | Do not accept tag; abort processing |
| Two concurrent requests | Same service, two different messages | Each message's tag is stable, no state mixing |
| Replay | Resend valid request and tag | MAC still verifies, but anti-replay/idempotency blocks duplicate when policy requires |
| Key rotation | Verify old tag with still-permitted old key version | Valid during transition window; revoked keys rejected per policy |

**Major testing tip:** Do not only check tags from the same library against itself. Keep at least one **independent golden vector** (RFC 4231 or from your partner) to catch bugs in algorithm, charset, key parsing, and serialization.

## 15. Hands-on Exercises

### Exercise 1 — Three update methods

Use the test key `0b` repeated 20 times and message `Hi There`. Write three computations:

1. `mac.doFinal(messageBytes)`.
2. `mac.update(messageBytes, 0, 2)` then `mac.update(messageBytes, 2, messageBytes.length - 2)`, finally `mac.doFinal()`.
3. `mac.update(ByteBuffer.wrap(messageBytes))` then `mac.doFinal()`.

Compare all three tags against RFC 4231. Explain why chunking does not change the tag when **byte order and content remain unchanged**.

### Exercise 2 — Catching a state management bug

A developer writes:

```java
static final Mac SHARED_MAC = createAndInitializeMac();
byte[] sign(byte[] requestBody) {
    SHARED_MAC.update(requestBody);
    return SHARED_MAC.doFinal();
}
```

This is **illustrative buggy pseudocode**, not a standalone Java program: `createAndInitializeMac()` is not defined here. Point out why this code can fail in a web service handling concurrent requests, even when a single isolated request appears to work. Fix it by creating a fresh `Mac` per computation and keeping the key in a secret manager/KMS. Write a two-thread test demonstrating independence.

### Exercise 3 — Designing a webhook signature

A partner sends fields `timestamp`, `eventId`, `tenantId`, `body`, and an HMAC tag.

- Define the exact bytes fed into the MAC, version, charset, and field boundaries.
- Decide when to verify the MAC and when to parse JSON.
- Propose how to store nonces/event IDs to prevent duplicate processing under concurrent requests.
- Verify the tenant and permission to update a specific business record.
- Test a valid request, a 1-byte modified body, wrong tag, expired timestamp, duplicate event ID, altered `tenantId`, and a revoked key.

### Exercise 4 — Streaming a file

Write a method to compute the HMAC-SHA-256 of a file block by block; the result must match one-shot over all bytes. Then simulate a 1 MB file, an empty file, partial read followed by an I/O error, two consecutive files, and a retry. Ensure failures do not emit a tag as if the file authenticated successfully.

**Lesson completion criteria:** you can explain accurately which bytes passed through each `update`, why `doFinal` establishes a message boundary and resets state, when to re-initialize `Mac`, and why having a valid HMAC tag still requires separate authorization and anti-replay checks.

## 16. References

- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): API, init/update/doFinal/reset state, overloads, and exceptions.
- [Java SE 17 — SecretKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): representing a secret key from bytes.
- [Java SE 17 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)): byte comparison for tag verification.
- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): specification of the HMAC construction.
- [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512](https://www.rfc-editor.org/rfc/rfc4231): standard test vectors for HMAC-SHA-256 and variants.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): key management, algorithms, and data protection notes.
