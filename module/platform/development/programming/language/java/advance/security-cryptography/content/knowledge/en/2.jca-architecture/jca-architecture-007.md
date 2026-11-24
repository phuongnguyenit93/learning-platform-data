# 2.7 Lifecycle of Initialization, Updating, Finalization, and Reuse of Cryptographic Objects

## 1. Why Must You Understand the Lifecycle?

In the Java Cryptography Architecture (JCA) and Java Cryptography Extension (JCE), classes such as `MessageDigest`, `Mac`, `Signature`, `Cipher`, and `KeyAgreement` are **engine objects**: the application calls a unified API while a cryptographic provider executes the algorithm. Each object typically holds **mutable state**: algorithm/provider, key, mode, parameters (IV/nonce, padding...), buffered input data, and internal buffers.

A `getInstance(...)` call only selects the requested algorithm/implementation; **it does not mean** every engine is ready to process data. An `update(...)` call may only feed additional data without yet producing a complete output. A finalizing call such as `digest()`, `doFinal()`, `sign()`, or `verify()` completes **one cryptographic operation**, which does not mean closing or destroying the object. State reset rules vary by class, algorithm, and error conditions.

After this lesson, you should be able to distinguish: (1) creating an engine vs. initializing key/mode; (2) `update` vs. `final`; (3) reset vs. re-init; (4) API-level reuse vs. **cryptographically safe** reuse, especially with AES-GCM.

## 2. General Lifecycle Model

```text
getInstance(algorithm)
        |
        v
[Engine object created]
        |
        | init(key/mode/parameters) when required by the API
        v
[Initialized for an operation type]
        |
        | update(data), can be called 0..n times
        | updateAAD(aad) before data for AEAD
        v
[Accumulating/processing a message]
        |
        | digest / doFinal / sign / verify / generateSecret
        v
[Message finalized, result or error returned]
        |
        +--> engine resets per API contract, can be reused
        |
        +--> must re-init / create new instance for new key, IV, mode, or session
        |
        +--> error: do not assume state remains usable; re-initialize
```

This is a **conceptual model**, not a universal state machine guaranteed by Java for every engine. Specifically:

- **Creation:** `MessageDigest.getInstance("SHA-256")` returns an object already in an initialized state. Conversely, `Mac` needs `init(key)`; `Signature` needs `initSign(privateKey)` or `initVerify(publicKey)`; `Cipher` needs `init(opmode, key, parameters)`.
- **Initialization:** key, operation direction, algorithm, and parameters must be compatible. `Cipher.ENCRYPT_MODE` differs from `Cipher.DECRYPT_MODE`; `Signature` in signing mode differs from verification mode.
- **Updating:** multiple sequential `update` calls are equivalent to processing the concatenation of data chunks *within the same operation*, assuming identical data and parameters. Previously fed data continues to affect the result until finalization/reset.
- **Finalization:** the finalizing method may process remaining buffered blocks, padding, MAC/tag, or verify the signature. Therefore, never call only `update` and treat the result as complete.
- **Starting a new message:** follow each API's reset contract and key/nonce security rules. `reset()` is not a universal method on every class; calling `init(...)` again establishes a new context.
- **Destruction:** these engines generally lack a universal `close()` protocol like streams. An object becoming unreachable does not mean secret keys are immediately wiped from memory.

## 3. Behavior Table by Engine

| Engine | Before feeding data | Feeding data / intermediate phase | Finalization | State after successful completion |
| --- | --- | --- | --- | --- |
| `MessageDigest` | `getInstance("SHA-256")` suffices | `update(...)` | `digest()` or `digest(bytes)` | Auto-resets to empty digest state; `reset()` can discard accumulated data |
| `Mac` | `getInstance("HmacSHA256")` then `init(secretKey)` | `update(...)` | `doFinal()` or `doFinal(bytes)` | Resets to the state right after the most recent `init`, keeping the key; `reset()` does the same |
| `Signature` | `initSign(privateKey)` or `initVerify(publicKey)` | `update(...)` | `sign()` or `verify(signature)` | Resets to the initialized sign/verify mode and corresponding key |
| `Cipher` | `init(ENCRYPT_MODE/DECRYPT_MODE, key, params)` | `update(...)`; AEAD: `updateAAD(...)` before data | `doFinal(...)` | The API states it resets to the post-`init` state on success; **still requires a fresh IV for each GCM encryption with the same key** |
| `KeyAgreement` | `init(privateKey)` | `doPhase(peerPublicKey, lastPhase)`, possibly multiple phases depending on algorithm | `generateSecret()` | Resets to the post-`init` state; a new session needs new phases, and usually new session keys depending on protocol |
| `SecureRandom` | Create/getInstance, internal seeding by provider | `nextBytes(...)`/`generateSeed(...)` | No per-message final operation | Can be called repeatedly; no `update/doFinal` model |
| `KeyGenerator` / `KeyPairGenerator` | Choose algorithm; should `init` size/parameters and an appropriate `SecureRandom` | No message-data `update` stream | `generateKey()` / `generateKeyPair()` | Can continue generating keys; each call produces fresh key material |

**Do not infer from method names that every class shares identical reset rules.** For example, `Mac.reset()` retains the current HMAC key, whereas `Cipher` has no corresponding public `reset()` that rotates the IV automatically. Nor should `getInstance` be used to check key readiness or runtime state.

## 4. Accumulating Data: `update` and Finalizing Operations

Suppose the UTF-8 data of a message is `"Hello JCA"` split into `"Hello "` and `"JCA"`:

```text
update("Hello ") + digest("JCA")
       same message
digest("Hello JCA") after engine reset
       produces the identical SHA-256 value
```

`MessageDigest.digest(byte[])` **both updates with the final data and finishes**. Likewise, `Mac.doFinal(byte[])` consumes additional trailing data. Never accidentally call `update(fullMessage)` followed by `doFinal(fullMessage)`: doing so processes the message twice. A no-argument `doFinal()` finishes all data from prior `update` calls.

For `Cipher`, `update` may return `null` or 0 bytes because the provider is buffering data to complete a block/padding/tag. `doFinal` emits the remainder; encryption and decryption must concatenate chunks in exact order. With `Cipher.getOutputSize(inputLength)`, the argument is **the number of remaining input bytes expected to be processed at that point**, and the result is the estimated output capacity needed for `update/doFinal`; when using overloads that write into an output buffer, check offsets, lengths, and `ShortBufferException`.

`Signature` does not return a signature from `update`: that method only accumulates the message to sign or verify. `sign` needs a private key; `verify` needs a public key and returns a `boolean` (or throws `SignatureException` on invalid signature/format/state). Do not switch between signing and verification without calling the corresponding `initSign`/`initVerify` method.

### Example 1 — Reusing Hash and HMAC Properly

Save as **`DigestMacLifecycleDemo.java`**; run with Java 17+.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class DigestMacLifecycleDemo {
    public static void main(String[] args) throws Exception {
        byte[] a = "Hello ".getBytes(StandardCharsets.UTF_8);
        byte[] b = "JCA".getBytes(StandardCharsets.UTF_8);
        byte[] whole = "Hello JCA".getBytes(StandardCharsets.UTF_8);

        MessageDigest md = MessageDigest.getInstance("SHA-256");
        md.update(a);
        byte[] digest1 = md.digest(b);
        byte[] digest2 = md.digest(whole);
        System.out.println("digestReset=" + Arrays.equals(digest1, digest2));
        System.out.println("sha256Bytes=" + digest1.length);

        byte[] keyBytes = "demo-key-for-hmac".getBytes(StandardCharsets.UTF_8);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(keyBytes, "HmacSHA256"));
        mac.update(a);
        byte[] tag1 = mac.doFinal(b);
        byte[] tag2 = mac.doFinal(whole);
        System.out.println("macReset=" + Arrays.equals(tag1, tag2));
        System.out.println("hmacBytes=" + tag1.length);
    }
}
```

```bash
javac -encoding UTF-8 DigestMacLifecycleDemo.java
java DigestMacLifecycleDemo
```

```text
digestReset=true
sha256Bytes=32
macReset=true
hmacBytes=32
```

After `digest(b)`, `MessageDigest` returns to an empty state, so `digest(whole)` does not accidentally append onto the previous message. After `mac.doFinal(b)`, `Mac` returns to the state initialized with the same key. `Mac.reset()` likewise discards accumulated data **without changing the key**; to change the key, call `init(newKey)`.

The hardcoded string HMAC key here is solely for observing the lifecycle. In real systems, generate/store keys with adequate entropy, such as using `KeyGenerator` or a key management service. SHA-256 is an **unkeyed** hash function; HMAC-SHA256 verifies integrity/authenticity when two parties share a secret. Do not use a plain hash as a substitute for a MAC.

## 5. `Cipher` and the Most Error-Prone Case: AES-GCM

`Cipher.getInstance("AES/GCM/NoPadding")` only creates an engine with a transformation (algorithm/mode/padding). Encryption requires `init(ENCRYPT_MODE, key, GCMParameterSpec)`; decryption requires `init(DECRYPT_MODE, key, GCMParameterSpec)`. In `GCMParameterSpec(tagBits, iv)`, `tagBits=128` is the authentication tag length in **bits**, while `iv` is typically **12 bytes (96 bits)**.

A GCM encryption session proceeds in this order:

1. Choose an **IV/nonce that never repeats under the same key**; a random 12-byte IV via `SecureRandom` can be used if nonce collision risk is managed appropriately.
2. `cipher.init(ENCRYPT_MODE, key, new GCMParameterSpec(128, iv))`.
3. If there is **AAD** (metadata requiring authentication without encryption), call `updateAAD(aad)` **before** `update/doFinal` processes plaintext.
4. Call `update` 0..n times, then `doFinal` exactly once for that message; the output contains ciphertext and the authentication tag (in Java GCM's byte-array output layout).
5. Store/transmit the IV alongside ciphertext+tag and the AAD convention for the decryption side. The IV need not be secret, but it must be unique within the key's scope.
6. For the **next encrypted message under the same key, you must re-init with a new IV**. Never treat `doFinal`'s internal reset as justification to reuse key+IV; reusing that pair breaks confidentiality and enables forgery.

The decryption side must use the **exact same key, IV, AAD** and process ciphertext+tag. `AEADBadTagException` from `doFinal` means authentication failed (possibly due to tampering, wrong key/IV/AAD, or corrupted data). **Discard all plaintext from a failed decryption**; never output or consume partial plaintext before the tag is verified.

### Example 2 — Update, doFinal, GCM Tag, and Re-init on Decryption

Save as **`AesGcmLifecycleDemo.java`**; run with Java 17+.

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmLifecycleDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        byte[] aad = "doc:123".getBytes(StandardCharsets.UTF_8);
        byte[] plain = "Hello authenticated world!".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        encrypt.updateAAD(aad);
        int middle = plain.length / 2;
        byte[] first = encrypt.update(plain, 0, middle);
        byte[] last = encrypt.doFinal(plain, middle, plain.length - middle);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        if (first != null) {
            buffer.writeBytes(first);
        }
        buffer.writeBytes(last);
        byte[] ciphertextAndTag = buffer.toByteArray();

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        decrypt.updateAAD(aad);
        byte[] recovered = decrypt.doFinal(ciphertextAndTag);
        System.out.println("roundTrip=" + Arrays.equals(plain, recovered));

        byte[] tampered = ciphertextAndTag.clone();
        tampered[tampered.length - 1] ^= 1;
        decrypt.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        decrypt.updateAAD(aad);
        try {
            decrypt.doFinal(tampered);
            System.out.println("tamperRejected=false");
        } catch (AEADBadTagException expected) {
            System.out.println("tamperRejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 AesGcmLifecycleDemo.java
java AesGcmLifecycleDemo
```

```text
roundTrip=true
tamperRejected=true
```

`encrypt.update(...)` may emit an initial ciphertext chunk or return zero bytes; the example handles `null` and combines it with `doFinal`. With the same key and IV, GCM computes a tag so the recipient verifies both ciphertext and AAD. The program explicitly calls `decrypt.init(...)` again before the tampered verification decryption to start the operation cleanly. **Never reuse this example's IV for another encryption under the same `key`**; any subsequent encryption must obtain a fresh IV and call `encrypt.init(...)` again. Because encryption produces different ciphertext each run, the example prints only deterministic check results rather than raw ciphertext.

In production, package each record into explicit fields for version/algorithm, IV, ciphertext+tag, and consistent AAD rules. Validate data lengths and buffer bounds before allocating; never pass unauthenticated data into a parser, database, or response stream.

## 6. `Signature`: One Object, Two Explicit Modes

A `Signature` operates along one of two distinct flows:

- **Signing:** `getInstance(algorithm) → initSign(privateKey) → update(message) → sign()`. After `sign` succeeds, state returns to post-`initSign`; you can `update`/`sign` a new message with the same key.
- **Verification:** `getInstance(algorithm) → initVerify(publicKey) → update(message) → verify(signatureBytes)`. After `verify`, state returns to post-`initVerify`. Returning `false` means the signature did not match; malformed signature bytes or provider errors can throw `SignatureException`.
- Switching from signing to verification, changing signers, or changing keys: you must call the appropriate `initVerify`/`initSign`, not just `update`. Signing and verification algorithms must match, including algorithm parameters if any (e.g., RSA-PSS).

### Example 3 — Sign, Verify, Then Reuse

Save as **`SignatureLifecycleDemo.java`**; run with Java 17+.

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class SignatureLifecycleDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        byte[] a = "record:".getBytes(StandardCharsets.UTF_8);
        byte[] b = "42".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(a);
        signer.update(b);
        byte[] signature1 = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(a);
        verifier.update(b);
        System.out.println("firstValid=" + verifier.verify(signature1));

        signer.update(a);
        signer.update(b);
        byte[] signature2 = signer.sign();
        verifier.update(a);
        verifier.update(b);
        System.out.println("reuseSignVerify=" + verifier.verify(signature2));

        verifier.update("record:".getBytes(StandardCharsets.UTF_8));
        verifier.update("43".getBytes(StandardCharsets.UTF_8));
        System.out.println("modifiedValid=" + verifier.verify(signature1));
    }
}
```

```bash
javac -encoding UTF-8 SignatureLifecycleDemo.java
java SignatureLifecycleDemo
```

```text
firstValid=true
reuseSignVerify=true
modifiedValid=false
```

After each successful `sign()` and `verify(...)`, the same instance can process a new message. If you forget to call `update` for a new message, the API signs/verifies an **empty message**; if you only update partially, the signed content no longer matches what was intended. Since the RSA key pair is generated at runtime, signature bytes are not printed as a fixed value. `SHA256withRSA` here is a lifecycle example; algorithm and signing policy choices in production must satisfy your specific security requirements.

## 7. Reset, Re-init, Clone, and New Objects: Choosing the Right Action

| Need | Proper handling | What to avoid |
| --- | --- | --- |
| Discard in-progress hash data | `MessageDigest.reset()`; or call `digest()` to finalize and auto-reset | Thinking old data remains buffered after `digest()` |
| HMAC another message, **same key** | After `doFinal()`, `update`/`doFinal` the next message; or `mac.reset()` before starting | Calling `reset()` and assuming the key changed |
| HMAC with a **different key** | `mac.init(newKey)` | Reusing the same instance with `reset()` alone |
| Signature for another message, **same mode/key** | After `sign/verify`, call `update` with the new message | Mistaking `verify(false)` for unfinished and mixing data |
| Change key/signer/Signature mode | `initSign(...)` or `initVerify(...)` | Using an object in the opposite mode |
| AES-GCM encrypt a new message | Unique IV/nonce for the key, then `cipher.init(ENCRYPT_MODE, key, new GCMParameterSpec(...))` | Calling `doFinal` again with the same key+IV |
| After a Cipher/Signature/KeyAgreement error | Discard unverified results; re-`init` or create a new instance before another operation | Relying on unknown internal state after an exception |
| Copy a digest's intermediate state | `clone()` only when the provider supports `Cloneable` and there is a clear need | Assuming every provider or engine is cloneable |

`reset` usually means **discarding the current message state**, not securely erasing keys from memory. `init` is the boundary for changing keys, direction, or operation parameters. Creating a **fresh instance per request** is usually easier to reason about, test, and keep free of state leaks than a complex reusable instance pool; measure initialization cost before optimizing.

`KeyAgreement` shares this distinction: `generateSecret()` finishes a `doPhase` sequence and resets to the post-`init` state, yet **does not automatically generate a new private key**. Protocols requiring ephemeral keys/forward secrecy must manage per-session key material explicitly rather than assuming security from the reset API.

## 8. Out-of-Order Calls and Error Handling

| Symptom / exception | Common cause | How to handle |
| --- | --- | --- |
| `IllegalStateException` on `Mac.update`, `Cipher.update/doFinal`, or `KeyAgreement.doPhase` | Not yet initialized (`init`); wrong mode; engine no longer in a valid state | Verify expected phase, initialize properly before operating |
| `InvalidKeyException` / `InvalidAlgorithmParameterException` | Key, IV, or parameters incompatible with algorithm/mode | Check key type, size, `AlgorithmParameterSpec`; never log keys |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Transformation or provider unsupported | Use standard algorithm names and explicit provider configuration |
| `ShortBufferException` | Output array lacks capacity in buffer-writing overloads | Size buffers via `getOutputSize` where appropriate, keep offsets accurate |
| `IllegalBlockSizeException` / `BadPaddingException` | Wrong block size/padding, wrong key, or corrupted ciphertext in applicable modes | Reject data, do not attempt to use suspect plaintext; handle errors uniformly |
| `AEADBadTagException` | GCM tag mismatch due to ciphertext, AAD, IV, or key mismatch | Discard result, do not process plaintext; treat as authentication failure |
| `SignatureException` or `verify(...) == false` | Bad state/format, or invalid signature | Distinguish technical exceptions from verification failure results |

Some **anti-patterns** (illustrative errors, not standalone programs):

```java
Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
// c.update(input); // WRONG: key, mode, and IV not initialized.

Mac m = Mac.getInstance("HmacSHA256");
// m.doFinal(message); // WRONG: key not initialized.

// After finishing an AES-GCM encryption:
// c.doFinal(nextMessage); // INSECURE if reusing key+IV.
```

After an exception, the API may not guarantee that buffers/state remain trustworthy; discard the current operation and **re-initialize** before retrying. In particular, decryption errors must never return detailed messages about padding, tags, keys, or input bytes to clients: distinct error messages can become an information-leakage side channel.

## 9. Designing Usage in Real Applications

**Message boundaries.** Each request/file/chunk is handled as an explicit operation: determine algorithm + key + mode + IV/AAD → initialize → feed data in order → finalize → verify result. Only release plaintext after authentication succeeds when using AEAD. For large file streaming, never release plaintext from GCM decryption `update` calls before verifying the final tag.

**Thread boundaries.** Avoid having multiple threads concurrently call `update/doFinal` on an active `Cipher`, `Mac`, `MessageDigest`, or `Signature`. Engines hold per-message state; concurrent sharing corrupts data and produces non-reproducible bugs. Create objects per task/thread or synchronize the entire operation sequence if there is a specific reason. Never synchronize `doFinal` alone.

**Key and nonce boundaries.** Keys are secret: never log them, hardcode them in production, or send them alongside ciphertext. A GCM IV can be public, yet the **key+IV pair must never repeat on the encryption side**. When rotating keys, switching sessions, switching users, or switching sign/verify roles, establish an appropriate engine context. For HMAC verification of received values, use a constant-time byte comparison such as `MessageDigest.isEqual(expected, received)` instead of stopping early on the first differing byte.

**Provider boundaries.** `getInstance("...")` selects an implementation from available providers; algorithm support, parameter validation, buffering, and initialization cost may differ. Rely on the public API contract, test against the real runtime provider/JDK, and do not assume `update` output always has a fixed length. When requiring a specific algorithm/hardware provider, verify `getProvider()` and configure explicitly.

**Resource boundaries.** You cannot and need not rely on a generic `close()` to scrub every engine. Limit the lifetime of references to keys and sensitive buffers; zeroing erasable byte arrays when no longer needed via `Arrays.fill` is a supplementary measure, though it does not guarantee clearing every internal copy inside the JVM/provider. Do not hold cryptographic objects in shared singletons without strict lifecycle design.

## 10. Knowledge Self-Check

1. After `MessageDigest.digest()`, does the next `digest(bytes)` continue hashing the previous message? **No**; `digest` finalizes and resets the state.
2. After `Mac.doFinal()`, to reuse the same HMAC key for a new message, do you have to call `init` again? **Not required**; `Mac` already reset to the post-`init` state. If changing keys, you **must** call `init(newKey)`.
3. After `Cipher.doFinal()` with AES-GCM, should you encrypt another message using the old key+IV? **Absolutely not**. Generate a new IV and re-initialize.
4. Does `Cipher.update` returning `null` mean no data was processed? **No**; the provider may buffer it and emit output on a later call or `doFinal`.
5. Is it safe to consume plaintext returned by GCM decryption `update` before `doFinal`? **No**; authenticity has not yet been verified.
6. After `Signature.verify(signature)` returns `false`, what does a new message require? **Feed the entire new message** (and re-init if changing key/mode); the previous message's verification state has ended.
7. Can multiple requests call `update`/`doFinal` concurrently on one engine? **No**; each message requires a sequential operation chain and independent state.

## Official API Documentation (Java SE 21)

- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html)
- [MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Cipher and GCM/IV notes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [KeyAgreement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html)
