# 9.2 The Lifecycle of `Signature.initSign`, `update`, `sign` and `initVerify`, `verify`

## Learning objectives

`java.security.Signature` is the **Java Security Architecture (JCA) engine API** for creating and verifying **digital signatures**. A `Signature` object operates as a stateful lifecycle: you must select an algorithm, initialize the right **key** and **operation direction**, supply all message bytes, and then call `sign()` or `verify()`.

By the end of this lesson, you can:

- Distinguish the two lifecycles: **signing with a private key** and **verifying with a public key**.
- Understand each call—`getInstance`, `initSign`, `initVerify`, `update`, `sign`, and `verify`—valid ordering, and **state reset** after an operation.
- Feed a message into `update()` across **multiple chunks** while ensuring all bytes are signed and verified in the exact order.
- Configure signature algorithm parameters such as `RSASSA-PSS` explicitly and practice on **Java 17+**.
- Distinguish `verify() == false` from an **exception**, and avoid bugs involving encoding, wrong keys, missing content, providers, or processing unauthenticated data.

> **Scope:** This lesson covers the `Signature` API and signature lifecycle in Java. Digital signatures **do not encrypt data**: others can still read the message unless the application encrypts it separately. Verifying a signature with a public key only becomes *signer identity* authentication when the public key is reliably bound to that identity.

## 1. The big picture: who signs, who verifies?

Suppose Alice sends a message to Bob:

```text
ALICE (signer)                             BOB (verifier)
-----------------                          --------------------
Message M (bytes)                          Receives Message M + Signature S
      |                                                |
Alice's private key                        Alice's authenticated public key
      |                                                |
Signature.initSign(private)                    Signature.initVerify(public)
      |                                                |
Signature.update(M)                            Signature.update(M)
      |                                                |
Signature.sign()  -> signature S               Signature.verify(S) -> true/false
      |                                                |
Send M and S ----------------------------------------->|
```

- `initSign(privateKey)` requires a **private key** authorized for signing and compatible with the chosen algorithm.
- `initVerify(publicKey)` requires the **public key** corresponding to the key the signer used; the verifier must **trust how the public key was obtained**.
- `update(...)` supplies the **message bytes** in the exact order. Both sides must produce the **exact same byte sequence**: changing content, chunk order, encoding, or signed metadata alters what is verified.
- `sign()` returns a `byte[]` containing the signature, **not** ciphertext of the message.
- `verify(signatureBytes)` typically returns `true` or `false` if the signature parses validly; an exception may occur if the state or signature format is invalid.

For a real-world document, you usually transmit/store **(message, signature, key identifier, algorithm ID / parameters)** in a versioned format. Never transmit the private key with the signature.

## 2. Signature is a three-stage state machine

According to the Java SE 17 API, a `Signature` object has three conceptual states:

| State | When entered? | Main valid operations |
| --- | --- | --- |
| **UNINITIALIZED** | Right after `Signature.getInstance(...)`, before key/operation is set | `initSign(...)` or `initVerify(...)`; `update`, `sign`, `verify` are not allowed yet. |
| **SIGN** | After `initSign(privateKey)` | One or more `update(...)` calls followed by `sign()`. |
| **VERIFY** | After `initVerify(publicKey)` / `initVerify(certificate)` | One or more `update(...)` calls followed by `verify(signature)`. |

```text
                       Signature.getInstance("RSASSA-PSS")
                                      |
                                      v
                               UNINITIALIZED
                                 /         \
                 initSign(private)      initVerify(public)
                             |               |
                             v               v
                           SIGN             VERIFY
                             |               |
                       update(...)       update(...)
                             |               |
                             v               v
                          sign()          verify(S)
                             |               |
                     outputs byte[] S     true / false
                             |               |
             Resets to SIGN state        Resets to VERIFY state
               (same initialized key)      (same initialized key)
```

**Reset upon completion:** The API specification states that `sign()` returns the object to the state it was in after the previous successful `initSign`, and `verify()` returns it to the state after the previous successful `initVerify`. Thus you can call `update()` and `sign()`/`verify()` for a **new message** without re-initializing the same key, provided the provider/algorithm honors the API contract. The example in section 6 verifies this behavior.

**Resetting does not clear the key, nor does it automatically switch directions.** If you need to change keys, switch from signing to verifying, or change parameter sets, you must perform the appropriate initialization/configuration. On a server, the cleanest practice is **one dedicated instance per operation** and never sharing a mutable `Signature` across threads or requests.

Do not call `sign()` while in `VERIFY`, or `verify()` while in `SIGN`. A `SignatureException` typically signals an inappropriate state.

## 3. Signing phase: `getInstance` → `initSign` → `update` → `sign`

### 3.1 `Signature.getInstance(algorithm)` selects the signature scheme

```java
// Illustration placed inside a method handling GeneralSecurityException:
Signature signer = Signature.getInstance("SHA256withRSA");
```

- `getInstance` selects the **signature scheme** via the JCA provider registry; it **does not sign or verify yet**. `Signature` **has no default algorithm**; the name must be explicitly specified.
- `SHA256withRSA` is an RSA signature scheme with SHA-256 per standard algorithm names (typically tied to RSASSA-PKCS1-v1_5).
- `RSASSA-PSS` is the RSA-PSS signature scheme with digest/MGF1/salt length parameters; `Ed25519` is an EdDSA scheme with a different algorithm. Do not swap names interchangeably just because they all use public/private keys.
- Java SE 17 **requires** implementations to include `SHA256withRSA` in the minimum `Signature` set; names like `RSASSA-PSS` or `Ed25519` should be checked against the target JDK/provider per deployment requirements.

If you pin a provider using `Signature.getInstance(name, "ProviderName")`, the code depends on that provider being registered and supporting the scheme; only specify a provider intentionally when an HSM or policy mandates it.

### 3.2 `initSign(privateKey)` sets the signing direction and key

```java
signer.initSign(privateKey);
```

`privateKey` must belong to a compatible algorithm/scheme; an RSA private key cannot automatically be used to sign with Ed25519. `initSign` has an overload `initSign(privateKey, secureRandom)` if the scheme needs application-supplied randomness. Most applications should use a cryptographically secure random source from the provider/JDK; never pass `java.util.Random`.

**Do not pass a public key to `initSign`.** Passing the wrong key variable typically fails compilation because the required type is `PrivateKey`; if the private key has the wrong type, size, or usage permissions, an `InvalidKeyException` may be thrown.

Keys can be generated by `KeyPairGenerator`, loaded from a keystore, backed by KMS/HSM via a provider, or supplied through a trusted mechanism. In the demo, a fresh RSA-2048 key pair is generated **in memory** so it runs standalone.

### 3.3 `update(...)` feeds the message bytes

```java
signer.update(headerBytes);
signer.update(payloadBytes, 0, payloadBytes.length);
byte[] signature = signer.sign();
```

Each `update` call contributes bytes to the **same logical message**, in the **order of the calls**. In terms of signed content, the calls above are equivalent to a single `update()` with `headerBytes || payloadBytes`.

The overloads:

| API | Meaning |
| --- | --- |
| `update(byte value)` | Supplies a single byte. |
| `update(byte[] data)` | Supplies the entire array. |
| `update(byte[] data, int off, int len)` | Supplies exactly `len` bytes starting at offset `off`; `len` is a **byte count**, not an ending index. |
| `update(ByteBuffer data)` | Supplies the bytes in the `remaining()` region, from `position()` to `limit()`; upon return, `position` equals `limit`. |

Calling `update()` in an uninitialized state throws `SignatureException`. It **does not** return a signature and does not automatically extract bytes from a `String`. Always choose the charset/encoding explicitly, e.g., `message.getBytes(StandardCharsets.UTF_8)`.

For schemes like `SHA256withRSA` or RSA-PSS configured with SHA-256, the engine typically performs hashing internally. **Do not manually hash the message with `MessageDigest` and pass the digest instead of the message into `Signature.update()`**, unless the chosen protocol/algorithm explicitly specifies that contract. Doing so typically signs the **digest as if it were a new message**, causing wrong data scope or “double hashing.”

### 3.4 `sign()` finishes and returns the signature

```java
byte[] result = signer.sign();
```

- The output is a **binary signature**, which may be Base64-encoded for transport over JSON/text, though Base64 **provides no security**.
- Length and encoding depend on the scheme and key. For a 2048-bit RSA modulus, an RSA-PSS signature is **256 bytes** long regardless of whether the message is short or long; other schemes have different formats and sizes.
- Some schemes use randomness (such as PSS), so **re-signing the same message and key can produce different signature bytes**, even though both verify cleanly. Never compare raw signature bytes as proof that two messages are equivalent.
- After `sign()`, the engine returns to the **SIGN initialized state**, and the bytes just passed to `update()` do not automatically remain as the next message. To sign a new message, you must supply the new message's bytes.
- Calling `sign()` without `update()` may sign an **empty message**, not a copy of the previous message. This is a subtle logic bug if an application expects to “reuse old data.”

The overload `sign(outbuf, offset, len)` writes into a slice of an output array and returns the actual number of bytes written; verify buffer size and bounds carefully. For most cases, `byte[] sign()` is clearer.

## 4. Verification phase: `getInstance` → `initVerify` → `update` → `verify`

```java
// Illustration inside a method handling GeneralSecurityException:
Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(trustedPublicKey);
verifier.update(receivedMessageBytes);
boolean valid = verifier.verify(receivedSignatureBytes);
```

### 4.1 `initVerify(publicKey)` initializes with the public key

Use the **signer's corresponding public key**, authenticated through the application's trust system. If the sender used `private_A`, the receiver uses `public_A`; `public_B` belonging to someone else will not verify A's signature (under secure key pairs and schemes).

There is an overload `initVerify(Certificate certificate)` that reads the public key from a certificate. **Do not assume that merely calling `initVerify(certificate)` validates the certificate chain, hostname, revocation status, or application identity.** X.509 trust/path validation, subject identity, and key usage must be handled per system rules; `Signature.verify` only checks the signature under the supplied key. `initVerify(certificate)` may also reject keys/certificates unsuitable for signing purposes.

### 4.2 `update` on the receiver must also feed the *entire* message

`verifier.update(...)` must receive the **exact byte sequence that was signed**, even if the signer and verifier split chunks differently:

```text
Signer:    update([A B]) ; update([C D E])    => A B C D E
Verifier:  update([A]) ; update([B C D E])    => A B C D E
                                              (equivalent)

Verifier:  update([C D E]) ; update([A B])    => C D E A B
                                              (different message)
```

Chunk sizes do not need to match; **the order and exact bytes must match**. Do not sign only the body and then trust an unsigned header: critical data such as version, message type, algorithm/key ID, tenant, user, amount, recipient, expiry, or context must be included in the signed data with an unambiguous encoding.

### 4.3 `verify(signature)` returns a boolean, not the data

`verify()` checks the signature against the message fed via `update` and the public key set in `initVerify`:

- **`true`:** The signature is valid **for the exact message bytes, scheme, parameters, and public key in use**.
- **`false`:** The signature parsed validly but does not match the message/key/parameters; it must be rejected.
- **`SignatureException`:** The object was not properly initialized, the signature has an invalid format/type, or the provider could not process it; this must **also be rejected**. Never assume every bad signature input returns `false`.
- **After `verify()`:** The engine resets to the **initialized VERIFY state**; to check another message next, call `update()` with the new message and `verify()` on the new signature.

`verify()` **does not decrypt** data and **does not evaluate the signer's identity by itself**. If the public key is supplied freely by the request, an attacker can generate a key pair, sign a message, and send their own public key to get `verify == true`. The system must bind the public key to an identity/authorization before treating a signature as evidence from a specific entity.

## 5. Lifecycle and state errors to remember

| Scenario | Outcome or risk | Proper usage |
| --- | --- | --- |
| `Signature.getInstance(...)` then `update(...)` immediately | Uninitialized; usually `SignatureException` | Call `initSign(private)` or `initVerify(public)` first. |
| `initSign(private)` then `verify(signature)` | Wrong operation direction | Call `sign()` in SIGN mode; or call `initVerify(public)`, feed message, and `verify()`. |
| `initVerify(public)` then `sign()` | Wrong operation direction | Use VERIFY mode. |
| `initSign(private)` → `update(A)` → `sign()` → `update(B)` → `sign()` | Two signatures for **A** and **B**; messages do not accumulate across `sign` calls | This is documented reset behavior; you may re-call `initSign` to separate operations more clearly. |
| `initVerify(public)` → `update(A)` → `verify(SA)` → `update(B)` → `verify(SB)` | Two consecutive verifications; object resets to VERIFY after each | Use a separate instance per request under concurrency. |
| Signer updates `A\|\|B`, receiver updates `B\|\|A` | Invalid signature due to different bytes | Standardize layout, order, and encoding. |
| Receiver only updates body, omitting signed header | Verification fails; or missing metadata authenticity if header was unsigned | Sign/verify the **complete defined envelope bytes**. |
| Mismatched PSS params between sign and verify | Verification may fail or throw a parameter error | Enforce identical digest, MGF1, salt length, and trailer field. |
| Signing algorithm incompatible with public/private key | `InvalidKeyException` or provider error | Verify key algorithm, purpose, provider, and scheme. |
| Sharing the same `Signature` instance across requests/threads | Mutable state mixes bytes and keys | Create a separate instance per operation; never let multiple threads call `update` concurrently. |

## 6. Complete Java 17+ example: RSA-PSS, multiple `update` calls, and proper lifecycle reuse

The program **`SignatureLifecycleDemo.java`** below:

1. Generates an RSA-2048 key pair; creates an `RSASSA-PSS` engine with **SHA-256**, **MGF1(SHA-256)**, **32-byte salt**, and **trailer 1**.
2. Signs `header || body` using two `update` calls.
3. Uses the matching public key and same parameters to `verify()`.
4. Tests modifying the body and reordering chunks: both become invalid.
5. Signs and verifies a second message on the same objects after the first calls reset their state.
6. Verifies that `update` on an uninitialized object is rejected.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class SignatureLifecycleDemo {
    private static final PSSParameterSpec PSS =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    32, 1);

    private static Signature createPss() throws GeneralSecurityException {
        Signature engine = Signature.getInstance("RSASSA-PSS");
        engine.setParameter(PSS);
        return engine;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] header = "order=42;".getBytes(StandardCharsets.UTF_8);
        byte[] body = "amount=100".getBytes(StandardCharsets.UTF_8);

        Signature signer = createPss();
        signer.initSign(pair.getPrivate());
        signer.update(header);
        signer.update(body);
        byte[] signature = signer.sign();

        Signature verifier = createPss();
        verifier.initVerify(pair.getPublic());
        verifier.update(header);
        verifier.update(body);
        System.out.println("First verification: " + verifier.verify(signature));

        verifier.update(header);
        verifier.update("amount=101".getBytes(StandardCharsets.UTF_8));
        System.out.println("Modified content accepted: " + verifier.verify(signature));

        verifier.update(body);
        verifier.update(header);
        System.out.println("Reordered chunks accepted: " + verifier.verify(signature));

        byte[] secondMessage = "second document".getBytes(StandardCharsets.UTF_8);
        signer.update(secondMessage);
        byte[] secondSignature = signer.sign();
        verifier.update(secondMessage);
        System.out.println("Second verification: " + verifier.verify(secondSignature));

        System.out.println("Signature bytes: " + signature.length);

        Signature uninitialized = createPss();
        boolean rejected = false;
        try {
            uninitialized.update(header);
        } catch (SignatureException expected) {
            rejected = true;
        }
        System.out.println("Uninitialized update rejected: " + rejected);
    }
}
```

Compile and run with JDK 17+ with a provider supporting **RSA-PSS**:

```bash
javac --release 17 SignatureLifecycleDemo.java
java SignatureLifecycleDemo
```

Expected output when running the program (the internal binary signature is randomized, but the stdout below is deterministic):

```text
First verification: true
Modified content accepted: false
Reordered chunks accepted: false
Second verification: true
Signature bytes: 256
Uninitialized update rejected: true
```

**Explanation of results:**

- Two calls `signer.update(header)` and `signer.update(body)` produce the exact message formed by concatenating those two byte arrays in that order. `verifier.update` feeds the same data, so the first line is `true`.
- `amount=101` differs from `amount=100`, even by a single byte; the old signature no longer matches, so the second line is `false`.
- Reversing the two byte arrays changes the message to `body || header`; the old signature is invalid.
- `signer.sign()` **resets to SIGN state** and `verifier.verify()` **resets to VERIFY state**, so for the second message you can call `update` and finish without re-initializing. **Never reuse the same instance across concurrent requests.**
- With RSA-2048, the modulus is 256 bytes, so the RSA-PSS signature is also 256 bytes; that is not proof that “message length = 256.”
- An uninitialized `Signature` cannot accept `update`; `SignatureException` is caught and prints `true` for the final check.
- RSA-PSS uses a salt, so signature bytes may differ when re-signing the same message; the proper check is calling `verify`, **never comparing bytes between two fresh signatures**.
- This lesson calls `setParameter(PSS)` **before init** with identical parameters on both sides. Different providers/HSMs may have requirements on when parameters are set or PSS capabilities; read the target provider's documentation and test `getInstance → setParameter → initSign/initVerify → sign/verify`. If unsupported, fail with a configuration error; never silently downgrade the scheme.

**Demo limitations:** the private key lives only in RAM; re-running the program generates a new key pair, so old signatures cannot verify under the new public key. A real environment must have protected private keys, trusted public keys/certificates, key IDs/versions, verification policies, and consistent message formatting.

## 7. Streaming large data for signing/verifying with `update`

For multi-megabyte files, there is no need to call `Files.readAllBytes()` just to pass data to `Signature.update()`. You can feed bytes from a stream in chunks:

```java
// Illustrative snippet inside a method declaring throws IOException, GeneralSecurityException;
// signer has already called initSign(privateKey), path is the chosen Path.
try (java.io.InputStream input = java.nio.file.Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        if (count > 0) {
            signer.update(buffer, 0, count);
        }
    }
}
byte[] signature = signer.sign();
```

The verifier performs the same reading logic over the **exact same file bytes**, except the engine must call `initVerify(trustedPublicKey)` and end with `verify(signature)`:

```java
// verifier has already called initVerify(trustedPublicKey).
try (java.io.InputStream input = java.nio.file.Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        if (count > 0) {
            verifier.update(buffer, 0, count);
        }
    }
}
boolean accepted = verifier.verify(signatureBytes);
```

These two snippets are **integration code fragments**, not standalone programs: `path`, engines, keys, and signature must be supplied by application logic. `update(data, off, len)` must use the **actual byte count read `count`**, not the full `buffer.length` on the final chunk, since the tail of the buffer may hold leftover data.

**Memory cost:** feeding data in chunks avoids holding the whole file in a `byte[]` at the application layer; however, do not assume every provider processes internally in strict constant-memory streaming. If reading from a file that can change concurrently, lock down an immutable snapshot/source or validate the final data before trusting the result to avoid TOCTOU issues.

For `update(ByteBuffer)`, the method consumes the entire `remaining()` span and advances `position()` to `limit()`. If you want to reuse the buffer elsewhere, manage `flip`/`rewind`/`duplicate` properly; do not call `update(buffer)` twice on a buffer with zero `remaining()` and assume you fed the same message twice.

## 8. Which exact *bytes* are signed? Encoding and trust scope

A valid signature only guarantees the integrity of the **actual byte sequence fed in**. It does not guarantee the displayed content “looks the same” if encoding or normalization differs. Common pitfalls:

- Signer calls `text.getBytes()` using the default charset; verifier uses UTF-8: the same characters can produce different bytes. Use `StandardCharsets.UTF_8` or the specified protocol encoding.
- Signer creates JSON with one field order, receiver parses and re-serializes in another order: bytes changed even though the object has the same content. You need a defined canonical serialization or verification over the **raw signed bytes**.
- Signer concatenates multiple strings without length prefixes: `"ab" || "c"` collides byte-for-byte with `"a" || "bc"`. When field semantics matter, use a versioned schema with tags/lengths, fixed order, and context.
- Signer feeds only the payload to `update()` while the application trusts `amount`, `recipient`, `tenant`, and `expiry` in an unsigned header: an attacker can alter the header while `verify` still passes on the old payload. **Sign all data that affects business decisions.**
- Signer applies Unicode normalization while receiver does not (or vice versa): bytes differ. Normalize and sign according to the protocol specification.
- If the signed content includes `algorithmId`, `keyId`, or type/version, prevent unauthenticated fields from steering selection of a weak algorithm; the parser must enforce an allowlist and proper signature policy.

A message structure might be defined as:

```text
signed_input = domain_separator
            || format_version
            || type_length || message_type
            || payload_length || payload
            || context_length || context
```

This is only a conceptual diagram: you must specify every field (byte count, unsigned/signed, endianness, byte encoding, max length). A **domain separator** such as `invoice-signature-v1` prevents a signature valid in one protocol from being misused in another protocol that shares the same key and payload bytes.

Signatures do not automatically prevent **replay**. A validly signed message can be replayed multiple times. If the use case requires “use once,” you must verify transaction ID, nonce, sequence, expiration, and recipient, and maintain spent state; these fields must be part of the signed data.

## 9. Algorithms, providers, and parameters in the `Signature` lifecycle

| Java scheme | Notable properties | Role of `Signature` |
| --- | --- | --- |
| `SHA256withRSA` | Uses SHA-256 with PKCS#1 v1.5-style RSA signature scheme; part of Java SE 17 minimum `Signature` requirements | `initSign(RSA private)`, `update(message)`, `sign()` and `initVerify(RSA public)`, `update(message)`, `verify(sig)`. |
| `RSASSA-PSS` | RSA-PSS using salt, digest, MGF, and trailer parameters; must match on both signing and verifying sides | Same lifecycle; set `PSSParameterSpec` explicitly. |
| `SHA256withECDSA` | ECDSA; signature is typically ASN.1 DER encoded in Java when using the standard name, depending on scheme/variant | Same lifecycle, except key type is EC rather than RSA. |
| `Ed25519` | EdDSA; does not use PSS params; key and signature scheme differ from RSA | `Signature.getInstance("Ed25519")` with Ed25519 private/public keys when provider supports it. |

Do not switch `SHA256withRSA` to `RSASSA-PSS` merely by name on the verifier while ignoring encoding/params; a v1.5 signature is not a PSS signature. You must store/communicate an **approved algorithm/suite ID**, parameters, key ID, and version.

`Signature.getInstance()` selects an implementing provider, but **is not a certificate** that the key, scheme, params, and runtime environment are secure. Errors can surface at `initSign`, `setParameter`, `update`, `sign`, `initVerify`, or `verify`. Always test the entire lifecycle against the target provider, especially when using HSM/KMS keys or a runtime different from the development JDK.

`Signature` is the `java.security` API for signing/verifying; other engines serve different goals:

- `MessageDigest` only hashes data, with no private key: does not authenticate an entity.
- `Mac` uses a shared symmetric secret key: parties holding the key can both create and verify MACs, not equivalent to a public-key signature.
- `Cipher` encrypts/decrypts: confidentiality does not equal authenticated origin.
- `KeyAgreement` establishes a shared secret: does not itself produce a digital signature.

## 10. Exceptions and safe error handling

| Issue type | When it happens | How to handle |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `Signature.getInstance("RSASSA-PSS")` when runtime/provider lacks the scheme | Check required version/provider/algorithm; never silently fall back to an unapproved scheme. |
| `InvalidKeyException` | `initSign(private)`/`initVerify(public)` uses wrong key type, disallowed usage, or invalid key | Check key algorithm, size, key usage, key storage/HSM, and policy. |
| `InvalidAlgorithmParameterException` | `setParameter(PSS)` rejected by provider | Check digest/MGF1/salt/trailer, implementation support, and configuration on both sides. |
| `SignatureException` in `update` | Init not called properly, wrong object state, or provider cannot process | Initialize in the proper direction, create a fresh engine per operation as needed. |
| `SignatureException` in `sign`/`verify` | Invalid state, improper signature encoding, or provider error | Reject the operation; ensure errors are logged safely and categorized under controls. |
| `verify(...) == false` | Signature does not match supplied message/public key/params | Reject; never “fix” the message or strip metadata to retry. |
| `verify(...) == true` but wrong identity | Public key unauthenticated or substituted by attacker | Verify source, trust chain, identity, and key usage before attributing a signer. |
| `verify(...) == true` but operation replayed | Signatures do not prevent replay automatically | Include expiry/id/sequence in signed data and enforce replay checks/state. |

Do not handle exceptions by letting data pass through. The safe flow is **fail closed**: if verification does not succeed, do not execute the transaction or accept the data as authenticated.

## 11. Testing the lifecycle and review checklist

Tests should cover:

1. **Happy path:** identical message bytes, right public key, matching scheme/params → `verify == true`.
2. **Tampered data:** flip one byte in the signed message → `verify == false`.
3. **Wrong order or missing chunk:** sign `A||B`, verify `B||A` or just `A` → fail.
4. **Wrong public key:** use public key from another pair → does not verify as valid.
5. **Wrong scheme parameters:** different PSS digest/MGF1/salt → fail or parameter error.
6. **Uninitialized:** `update`/`sign`/`verify` before init → appropriate `SignatureException`.
7. **After `sign`/`verify`:** test a new message with `update`, ensuring no leftover data from the prior message.
8. **Encoding and canonicalization:** sign and verify across runtimes/languages with identical test vectors, UTF-8, layout, and specified keys/params.
9. **Metadata:** alter `tenant`, `role`, `amount`, `expiry`, `audience` inside the signed part → fail; if altering metadata outside the signed part still passes, the protocol needs improvement.
10. **Replay and trust:** valid signature that is expired/ID already used/public key unapproved → business layer must reject.

Code review checklist:

- [ ] `getInstance` uses an **explicit signature algorithm name**, not taken arbitrarily from unauthenticated data.
- [ ] `initSign` receives the right signer/purpose **private key**; `initVerify` uses a **trusted public key** for the expected signer.
- [ ] All critical bytes are fed to `update` in the right order, charset, and schema; when streaming, `len` is the actual bytes read.
- [ ] `sign()` and `verify()` only run after valid init/update; callers understand engine reset after an operation and do not share across threads.
- [ ] PSS and other params are specified/compatible; key length and provider meet policy.
- [ ] The `verify` result **must be checked**; `false` and all related exceptions lead to rejection.
- [ ] Certificates, identity, and key usage are validated **outside** the signature check; signed messages are not assumed confidential or replay-proof.
- [ ] Tests cover altered signature, altered content, wrong key, stale/replayed message, wrong params, and cross-provider checks where needed.

## 12. Self-check questions

**Question 1:** Can you call `Signature.getInstance("SHA256withRSA")` and immediately call `update`?  
**No.** You must call `initSign(privateKey)` or `initVerify(publicKey)` first.

**Question 2:** If the signer calls `update(A)` and `update(B)`, can the verifier call `update(A||B)`?  
**Yes**, provided the concatenated bytes are in the exact same order with the same scheme/params. Chunk boundaries do not alter the message.

**Question 3:** Does `Signature.sign()` return ciphertext or a signature?  
**Signature bytes.** The message is not encrypted by `Signature`.

**Question 4:** Why does changing `amount=100` to `amount=101` cause `verify` to fail?  
Because the signature is bound to the **message bytes that were fed in**. The modified content no longer matches the old signature.

**Question 5:** After `verify()`, can you feed another message?  
**Yes**, per the API contract: the object resets to the initialized VERIFY state with the same key; you must `update` the new message. In concurrent code, use a separate engine per operation.

**Question 6:** Is `verify() == true` enough to conclude “Alice signed this”?  
**Not yet.** You must verify that the public key truly belongs to Alice and is authorized for signing, plus check expiry, replay, and application context.

**Question 7:** When re-signing the same message with RSA-PSS and the same private key, must it produce the exact same signature bytes?  
**No.** PSS uses randomness (salt); validate with `Signature.verify`, never by byte equality.

## Primary sources and further reading

- [Java SE 17 — `java.security.Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): primary documentation for the **three stages**, `UNINITIALIZED`/`SIGN`/`VERIFY` states, `update`, `sign`, `verify`, and reset upon completion.
- [Java SE 17 — `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html): SHA-256, MGF1, salt length, trailer.
- [Java SE 17 — `MGF1ParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html): digest used inside MGF1.
- [Java SE 17 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): `Signature` engine, providers, service architecture, and usage examples.
- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): standard names and required/available `Signature` algorithms.
- [RFC 8017 — PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): RSASSA-PSS, encoding, salt, and verification model.

**Key takeaway:** `initSign(private) → update(message bytes) → sign()` creates a signature; `initVerify(trustedPublic) → update(same message bytes) → verify(signature)` checks it. Both sides must agree on **bytes, algorithm, parameters, and key identity**. `Signature` handles integrity and key-bound authentication; it does not automatically provide confidentiality or replay protection.
