# 6.5. Distinguishing ECB, CBC, CTR and Ciphertext Integrity Protection Requirements

## Learning Objectives

After this lesson, you will be able to:

1. Correctly interpret Java transformation names such as `AES/ECB/NoPadding`, `AES/CBC/PKCS5Padding`, and `AES/CTR/NoPadding`; understand that **AES** is the block cipher algorithm while **ECB, CBC, CTR** are *modes of operation*.
2. Explain how these three modes transform plaintext into ciphertext; distinguish requirements for **IV, nonce, counter**, padding, and data length.
3. Identify the issues of **ECB pattern leakage**, **CBC with IV/padding oracles**, **CTR upon keystream reuse**, and why all three modes on their own **do not authenticate ciphertext integrity**.
4. Experiment in Java 17+ to observe how modifying ciphertext/IV alters plaintext undetected by decryption; implement **Encrypt-then-MAC** properly if legacy CBC/CTR is unavoidable, and prefer **AEAD** such as AES-GCM for new designs.
5. Know how to store/transmit IV and tag, handle authentication errors, design nonce uniqueness, and avoid conflating confidentiality, integrity, authentication, and replay protection.

**Scope:** this lesson focuses on symmetric encryption with AES in Java. The *unauthenticated* CBC/CTR examples are strictly for observing the problem; do not use them as complete security templates for production.

## 1. AES Is a Block Cipher; ECB, CBC, and CTR Decide How Blocks Are Used

**AES (Advanced Encryption Standard)** is a symmetric encryption algorithm operating on **128-bit = 16-byte blocks**, with 128-, 192-, or 256-bit keys. **The block size remains 16 bytes even when using an AES-256 key**. AES itself encrypts or decrypts *a single block*; processing longer messages requires a mode of operation, IV/counter handling, and sometimes padding.

In the Java Cryptography Architecture/Extension, `javax.crypto.Cipher` takes the name format:

```text
<algorithm>/<mode>/<padding>

AES/ECB/NoPadding
AES/CBC/PKCS5Padding
AES/CTR/NoPadding
AES/GCM/NoPadding
```

In the list above, `NoPadding` instructs the cipher not to add padding—it **does not mean the message needs no validity checking**; and `PKCS5Padding` in JCE naming for AES applies PKCS#7-compatible padding rules on 16-byte blocks.

Never write `Cipher.getInstance("AES")` in security-sensitive applications: the default mode/padding depends on the provider and may unexpectedly select ECB. Always specify the **full** transformation according to the protocol design.

### 1.1. Four Properties Commonly Confused

| Property | Practical Question | Provided by ECB/CBC/CTR Encryption Alone? |
| --- | --- | --- |
| **Confidentiality** | Can someone without the key read the plaintext? | Can be provided to varying degrees **only when mode/IV/counter are used properly**; ECB is generally unsuitable for structured data |
| **Integrity** | Has the data been modified since it was sent/stored? | **No**; plaintext can be altered when ciphertext/IV is modified |
| **Authentication** | Was the data created by a party holding the valid key? | **No**; encryption does not replace a MAC/signature |
| **Replay protection** | Will a valid old message re-sent later be rejected? | **No**, even with a MAC or AEAD unless sequence numbers/nonces/state tracking exist |

This is the core principle of the entire lesson: **"successfully decrypting" does not mean "the ciphertext was not tampered with"**. An application whose padding check succeeds may still receive adversary-manipulated plaintext.

## 2. ECB – Electronic Codebook: Independent Blocks and Repeating Pattern Leakage

Given plaintext split into full 16-byte blocks `P1, P2, ...` and key `K`, ECB applies AES to **each block independently**:

```text
P1 ── AES-Encrypt(K) ──> C1
P2 ── AES-Encrypt(K) ──> C2
P3 ── AES-Encrypt(K) ──> C3

C_i = E_K(P_i)
```

If `P1 = P2`, then **necessarily `C1 = C2` under the same key**. An observer cannot directly decrypt the content, yet clearly sees which blocks repeat, inferring structure, format, and data patterns. For images, records with repeated fields, or templated data, this is a significant leak.

- **IV:** ECB uses no IV; there is no nonce mechanism to break block patterns.
- **Padding:** `AES/ECB/NoPadding` only accepts input lengths that are multiples of 16; `AES/ECB/PKCS5Padding` pads messages that do not fill whole blocks.
- **Integrity:** none. An attacker can also swap or substitute ciphertext blocks without knowing the key; decryption yields duplicated or relocated plaintext blocks.
- **Suitability:** rarely appropriate directly for real-world messages. ECB may serve as an internal primitive inside another proven construction, but never pick ECB to "encrypt files/JSON/database records".

For example, a 16-byte block of `'A'` characters repeated twice: the first two ECB ciphertext blocks are completely identical. This stems from **deterministic per-block mapping**, independent of whether the AES key is 128 or 256 bits long.

**You cannot fix ECB merely by changing padding:** adding PKCS5 padding does not eliminate repeating patterns across identical full plaintext blocks.

## 3. CBC – Cipher Block Chaining: Linking Blocks and the IV

CBC uses the previous ciphertext block to influence encryption of the current block. Let `IV` be a 16-byte initialization vector, `P_i` be the `i`-th plaintext block, and `C_i` be the `i`-th ciphertext block:

```text
C_0 = IV

P1 ─ XOR(IV) ─ AES-Encrypt(K) ─> C1
P2 ─ XOR(C1) ─ AES-Encrypt(K) ─> C2
P3 ─ XOR(C2) ─ AES-Encrypt(K) ─> C3

C_i = E_K(P_i XOR C_(i-1))
P_i = D_K(C_i) XOR C_(i-1)
```

This is a *chaining* mode: each prior block affects the next. With a properly generated random, unpredictable IV, encrypting the same message twice produces different ciphertexts starting from the very first block.

### 3.1. What Must a CBC IV Look Like?

- A CBC/AES IV is **16 bytes**, matching the AES block size, unlike GCM which typically uses a 12-byte nonce.
- For secure CBC encryption, the IV must be **unpredictable under chosen plaintext**; in practice, generating a fresh IV via `SecureRandom.nextBytes(new byte[16])` per message is the standard choice.
- The IV **does not need to be kept secret** and can be prepended to the ciphertext; however, it must be **integrity-bound** to the message in a MAC/AEAD scheme.
- **Never** use a fixed 16-byte zero IV, an IV derived from a timestamp/`Random`, or reuse the same IV across messages under the same key.
- Do not confuse "storing the IV alongside the ciphertext" with "authenticating the IV": if an adversary modifies an unauthenticated IV, the first plaintext block can be altered directly.

### 3.2. CBC Typically Needs Padding

`AES/CBC/PKCS5Padding` in Java adds padding automatically; even when plaintext length is an exact multiple of 16, it appends **a full padding block**, so CBC ciphertext can be longer than plaintext. With `NoPadding`, the application must supply data in multiples of 16 bytes and must not invent ambiguous custom padding.

With `AES/CBC/PKCS5Padding`, decryption may throw `BadPaddingException` if padding is invalid. **Padding errors are not an authentication mechanism.** An attacker can modify ciphertext and observe application behavior to deduce plaintext if the system distinguishes valid/invalid padding errors or varies processing time.

### 3.3. CBC Can Be Deliberately Modified

Decryption formula for the first block:

```text
P1 = D_K(C1) XOR IV
```

If an adversary flips a bit in the **IV**, the corresponding bit of `P1` flips without needing the key. Similarly, modifying `C_i` scrambles block `P_i` and flips targeted bits in `P_(i+1)`. This is called **malleability**.

For instance, data structures containing permission flags or monetary amounts are especially dangerous if a backend decrypts CBC and trusts the plaintext without authenticating first. Bit-flipping does not always yield valid plaintext, yet **successful decryption must never be treated as proof of data integrity**.

### 3.4. Padding Oracle: Why Authenticate Before Decrypting?

Suppose an API accepts `IV || ciphertext`, calls `Cipher.doFinal`, and returns:

- `400 Padding error` on `BadPaddingException`;
- `401 Invalid message` when decryption succeeds but application data is invalid.

This distinction can create an **oracle**: an adversary probes modified ciphertexts and observes responses to learn plaintext bytes without the key. Even with a uniform error message, timing differences can still act as a signal.

If CBC is unavoidable, a proven authenticated design is required, such as **Encrypt-then-MAC** with an independent key; the receiver **verifies the MAC before CBC decryption**. You must also enforce policies for IVs, formatting, padding, key rotation, and uniform error responses. For new designs, standard AEAD such as AES-GCM is simpler and safer to use correctly.

## 4. CTR – Counter: Turning AES into a Keystream

CTR does not encrypt plaintext blocks directly with AES. Instead, it encrypts a dedicated **counter block**, then XORs the result with plaintext. Counter blocks must **never repeat under the same key**.

```text
T1 = nonce || counter1  ─ AES-Encrypt(K) ─> S1
T2 = nonce || counter2  ─ AES-Encrypt(K) ─> S2
T3 = nonce || counter3  ─ AES-Encrypt(K) ─> S3

C1 = P1 XOR S1
C2 = P2 XOR S2
C3 = P3 XOR S3

P_i = C_i XOR S_i
```

`T_i` is the counter block fed into AES; `S_i` is the keystream. The notation `nonce || counter` is merely **one protocol layout for counter blocks**: exact bit widths for nonce/counter, increment rules, and endianness must be strictly agreed upon. In Java with AES, the initial counter block is passed via a 16-byte `IvParameterSpec`. Different providers may manage counters differently, so interoperable systems must specify the exact format.

### 4.1. Useful Properties of CTR

- No padding required: `AES/CTR/NoPadding` encrypts plaintexts that are not multiples of 16 bytes; ciphertext has the **exact same byte length** as plaintext.
- Keystream blocks can be computed independently once counter blocks are known, enabling parallelization and random-access reads.
- Encryption/decryption share the same XOR principle; `Cipher` distinguishes `ENCRYPT_MODE`/`DECRYPT_MODE`, though both apply the corresponding keystream.
- No CBC-style chaining, so an error in one ciphertext byte affects only the corresponding plaintext byte when the counter is aligned.

**Critical trade-off:** CTR does not authenticate data. If an adversary flips a bit in ciphertext, the corresponding plaintext bit flips **predictably**. The application will decrypt cleanly without any exception.

### 4.2. The Cardinal Rule: Never Reuse a Keystream

If the same key `K` and same counter block `T_i` encrypt two different plaintexts, the keystream `S_i` is identical:

```text
C1 = P1 XOR S
C2 = P2 XOR S

C1 XOR C2 = P1 XOR P2
```

An observer sees the XOR relationship of the two plaintexts. If one plaintext is known or guessed, the other can be recovered at corresponding positions. This is a dangerous **two-time pad**.

- For CTR, the exact condition is to **never reuse the same AES input counter block under the same key**, even across separate messages.
- Each message must have a disjoint nonce/counter range; counter overflow/wraparound must be prevented, accounting for each message's block count.
- Never use a fixed IV/counter block, a counter that resets after restart/snapshot, or bare randomness without understanding collision probabilities/bounds.
- Do not conclude "CTR needs no padding so it must be safer than CBC": CTR has strict nonce/counter requirements and still lacks integrity.

The demo below uses a random 16-byte IV for **a single encryption**. In large production systems, designing per-key unique nonce/counters and block limits per standards matters far more than a short example.

## 5. Comparing ECB, CBC, and CTR from a Security Perspective

| Criterion | ECB | CBC | CTR |
| --- | --- | --- | --- |
| How it operates | Each plaintext block encrypted independently | XOR plaintext with previous ciphertext block, then encrypt | Encrypt counter block into keystream, XOR plaintext |
| Leaks repeating patterns in message | **Yes**, equal plaintext blocks → equal ciphertext blocks | Does not leak ECB-style patterns when IV/key are proper; chaining links blocks | Does not leak ECB-style patterns when counter blocks never repeat |
| IV/nonce/counter | No IV | 16-byte IV, fresh and unpredictable for encryption | 16-byte counter block, guaranteed non-repeating under same key |
| Padding with AES | Needed if not multiple of 16 | Needed if not multiple of 16 | **Not needed** |
| Ciphertext size | Multiple of 16 | Multiple of 16; adds padding if using PKCS5Padding | Equal to plaintext size |
| Parallel block encryption | Yes | Depends on previous ciphertext block | Keystream blocks can be computed independently |
| Effect when ciphertext is modified | Replacing/reordering blocks replaces/reorders plaintext | Scrambles block or causes structured change in next; altering IV alters first block | Flipping ciphertext bit → flips corresponding plaintext bit |
| Built-in MAC/tag? | **No** | **No** | **No** |
| Safe to use bare for new sensitive data? | **No** | No, needs proper authentication; usually prefer AEAD | No, needs proper authentication; usually prefer AEAD |

**Do not equate "has an IV" with "checks integrity".** CBC IVs and CTR nonces serve confidentiality; detecting data modification requires a separate authentication mechanism.

### 5.1. Quick Look at Data Modification Behavior

```text
ECB:
  P_block → E_K → C_block
  Reorder/copy C_block ⇒ reorder/copy P_block (undetected)

CBC (without MAC):
  P1 = D_K(C1) XOR IV
  IV[0] ^= 1 ⇒ P1[0] ^= 1 (without knowing K)

CTR (without MAC):
  P = C XOR keystream
  C[0] ^= 1 ⇒ P[0] ^= 1 (without knowing K)

GCM (authenticated):
  C or tag modified ⇒ tag verification fails ⇒ plaintext rejected
```

The diagram models relationships—it does not imply every CBC modification produces valid plaintext or that GCM solves replay.

## 6. Java 17+ – Standalone Demo Showing the Differences

Create **`ModeComparisonDemo.java`** as follows. This is an **educational** program: the ECB/CBC/CTR parts intentionally omit a MAC so you can observe what happens with encryption-only modes. Keys and IVs/nonces are freshly generated using cryptographic APIs; the program prints no secrets, keeping stdout deterministic.

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.IvParameterSpec;

public class ModeComparisonDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey key = generator.generateKey();

        // Two identical 16-byte blocks.
        byte[] plain = new byte[32];
        Arrays.fill(plain, (byte) 'A');

        // ECB: same plaintext block -> same ciphertext block.
        Cipher ecb = Cipher.getInstance("AES/ECB/NoPadding");
        ecb.init(Cipher.ENCRYPT_MODE, key);
        byte[] ecbCipher = ecb.doFinal(plain);
        boolean ecbRepeats = Arrays.equals(
                Arrays.copyOfRange(ecbCipher, 0, 16),
                Arrays.copyOfRange(ecbCipher, 16, 32));

        // CBC: IV must be 16 bytes and integrity-protected.
        byte[] cbcIv = new byte[16];
        random.nextBytes(cbcIv);
        Cipher cbc = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cbc.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(cbcIv));
        byte[] cbcCipher = cbc.doFinal(plain);

        cbc.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(cbcIv));
        boolean cbcRoundTrip = Arrays.equals(plain, cbc.doFinal(cbcCipher));

        // If IV is unauthenticated, flipping an IV bit flips a bit in P1.
        byte[] changedCbcIv = cbcIv.clone();
        changedCbcIv[0] ^= 1;
        cbc.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(changedCbcIv));
        byte[] cbcModifiedPlain = cbc.doFinal(cbcCipher);
        byte[] expectedCbcPlain = plain.clone();
        expectedCbcPlain[0] ^= 1;
        boolean cbcIvMalleable =
                Arrays.equals(expectedCbcPlain, cbcModifiedPlain);

        // CTR: no padding, ciphertext length = plaintext length.
        byte[] ctrIv = new byte[16];
        random.nextBytes(ctrIv);
        Cipher ctr = Cipher.getInstance("AES/CTR/NoPadding");
        ctr.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(ctrIv));
        byte[] ctrCipher = ctr.doFinal(plain);

        ctr.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(ctrIv));
        boolean ctrRoundTrip = Arrays.equals(plain, ctr.doFinal(ctrCipher));

        // Flipping a CTR ciphertext bit flips the corresponding plaintext bit.
        byte[] changedCtrCipher = ctrCipher.clone();
        changedCtrCipher[0] ^= 1;
        ctr.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(ctrIv));
        byte[] ctrModifiedPlain = ctr.doFinal(changedCtrCipher);
        byte[] expectedCtrPlain = plain.clone();
        expectedCtrPlain[0] ^= 1;
        boolean ctrMalleable =
                Arrays.equals(expectedCtrPlain, ctrModifiedPlain);

        // GCM: still AES, but protected by an authentication tag.
        byte[] gcmNonce = new byte[12];
        random.nextBytes(gcmNonce);
        GCMParameterSpec gcmParams =
                new GCMParameterSpec(128, gcmNonce);
        Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding");
        gcm.init(Cipher.ENCRYPT_MODE, key, gcmParams);
        byte[] gcmCipherAndTag = gcm.doFinal(plain);

        gcm.init(Cipher.DECRYPT_MODE, key, gcmParams);
        boolean gcmRoundTrip =
                Arrays.equals(plain, gcm.doFinal(gcmCipherAndTag));

        // Flipping a bit at the end of the tag: decryption must be rejected.
        byte[] changedGcm = gcmCipherAndTag.clone();
        changedGcm[changedGcm.length - 1] ^= 1;
        gcm.init(Cipher.DECRYPT_MODE, key, gcmParams);
        boolean gcmRejected = false;
        try {
            gcm.doFinal(changedGcm);
        } catch (AEADBadTagException expected) {
            gcmRejected = true;
        }

        System.out.println("ecbRepeatedBlocks=" + ecbRepeats);
        System.out.println("cbcRoundTrip=" + cbcRoundTrip);
        System.out.println("cbcIvMalleable=" + cbcIvMalleable);
        System.out.println("ctrSameLength=" +
                (ctrCipher.length == plain.length));
        System.out.println("ctrRoundTrip=" + ctrRoundTrip);
        System.out.println("ctrMalleable=" + ctrMalleable);
        System.out.println("gcmRoundTrip=" + gcmRoundTrip);
        System.out.println("gcmTamperRejected=" + gcmRejected);
    }
}
```

Run in the folder containing the file:

```shell
javac ModeComparisonDemo.java
java ModeComparisonDemo
```

**Expected stdout on a standard JDK 17+ supporting these transformations:**

```text
ecbRepeatedBlocks=true
cbcRoundTrip=true
cbcIvMalleable=true
ctrSameLength=true
ctrRoundTrip=true
ctrMalleable=true
gcmRoundTrip=true
gcmTamperRejected=true
```

**Accurate interpretation of the results:**

- `ecbRepeatedBlocks=true` is a mathematical property of ECB on two identical plaintext blocks; it does not depend on the random key value.
- `cbcRoundTrip=true` and `ctrRoundTrip=true` show that decryption works when key and IV match. They **do not prove integrity**.
- `cbcIvMalleable=true` shows that **modifying an unauthenticated IV** alters the first plaintext block accordingly without `Cipher` noticing. The trailing padding bytes of the message are unaffected in this demo.
- `ctrMalleable=true` shows that flipping a CTR ciphertext bit flips the corresponding plaintext bit, with no exception thrown during CTR-only decryption.
- `gcmTamperRejected=true` demonstrates that the tag in the example detects modification; the receiver must reject and never use unauthenticated plaintext.
- The snippet **does not demonstrate nonce persistence or long-term encryption count management**. In real deployments, you must guarantee GCM/CTR key–nonce pairs are never reused.

### 6.1. What Can Be Concluded from the Example?

**Valid conclusions:** ECB leaks repeated blocks; CBC and CTR only provide confidentiality when mode/IV/counter are used properly and still permit ciphertext manipulation; AEAD verifies authentication during decryption.

**Invalid conclusions:** `gcmTamperRejected=true` alone does not mean an application has complete security controls. You still need key management, nonce uniqueness, AAD, access control, replay protection, and safe error handling. The CBC/CTR demos intentionally lack a MAC—**never copy them verbatim into production**.

## 7. Why Authenticate Ciphertext Before Trusting Plaintext?

Suppose a backend stores:

```text
IV || ciphertext
```

and simply calls `Cipher.doFinal(ciphertext)`. When bytes are altered:

- ECB may accept copied/reordered ciphertext blocks.
- CBC may return altered data or throw a padding error; differing responses easily create an oracle.
- CTR always XORs every ciphertext byte (given valid length/counter) and never detects flipped bits itself.

**Unauthenticated encryption creates a false trust boundary:** the application sees "decrypted" bytes and assumes they were produced by an authorized party.

When tamper resistance is needed, use one of two standardized approaches:

1. **AEAD** (*Authenticated Encryption with Associated Data*): an algorithm providing confidentiality + integrity/authentication in a single mechanism, e.g., `AES/GCM/NoPadding`. The tag authenticates ciphertext, nonce, and AAD per the algorithm specification. This is the **preferred option for new systems** when nonce/key lifecycle constraints are met.
2. **Encrypt-then-MAC (EtM)**: use an appropriate encryption mode plus a cryptographic MAC (e.g., HMAC-SHA256 with a **separate key** from the AES key); verify framing/IV/ciphertext and context metadata before decrypting. Choose this only for legacy compatibility or carefully designed, reviewed, and tested protocols.

**Never** replace a MAC with a checksum, CRC32, unkeyed SHA-256, or "try decrypting to see if it errors". An unkeyed hash can be recomputed by an adversary after altering the data. A MAC must use a secret key/standard algorithm. Digital signatures can also authenticate under an asymmetric key model, though symmetric messages do not need to be turned into digital signature problems.

### 7.1. Encrypt-then-MAC Rules

Example self-describing versioned format:

```text
message = version || IV || ciphertext
tag     = HMAC_SHA256(macKey, message)
packet  = message || tag
```

Sender:

1. Holds independent **AES key** and **HMAC key**, securely managed.
2. Generates a fresh CBC IV using `SecureRandom`.
3. Encrypts plaintext with `AES/CBC/PKCS5Padding`.
4. Computes HMAC over **version + IV + ciphertext** (also covering external metadata/AAD if the protocol includes it).
5. Sends `packet`; the IV need not be hidden, while keys must remain secret.

Receiver:

1. Parses framing and checks lengths within appropriate resource bounds.
2. Recomputes HMAC over **all data requiring authentication**.
3. Compares tags using a constant-time comparison to reduce timing leaks, such as `MessageDigest.isEqual`.
4. **Only if the tag is valid**, checks version/format and decrypts CBC; handles exceptions uniformly per policy.

If CBC is decrypted **before** verifying HMAC, the scheme may still expose a padding oracle. If the MAC covers only ciphertext while omitting IV/version/metadata, an adversary can alter the omitted fields. If the same key is reused for both AES and HMAC without explicit key separation, the design lacks necessary cryptographic separation.

### 7.2. Why Doesn't Authentication Alone Prevent Replay?

Suppose a valid packet has an HMAC tag. An adversary **does not alter** the packet, just re-sends it verbatim. The MAC remains valid because the content genuinely has not changed. Systems must defend against replay using **sequence numbers, transaction IDs, timestamps with acceptance windows, one-time tokens, anti-replay state**, or standardized protocol mechanisms. Anti-replay identifier fields must also be integrity-protected.

## 8. Java 17+ – Encrypt-then-MAC Example for Legacy CBC

This problem uses two independent keys: AES-128 for encryption and HMAC-SHA256 (32-byte secret) for authentication. Example format: `1-byte version || 16-byte IV || ciphertext || 32-byte HMAC`. Decrypt only when the MAC is valid.

This is an **educational example for legacy protocols**. In new systems, prefer standard AEAD; rolling your own packet format additionally requires versioning, key IDs, size limits, rotation, metadata management, and security review.

Create **`AuthenticatedCbcDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class AuthenticatedCbcDemo {
    private static final int IV_SIZE = 16;
    private static final int TAG_SIZE = 32;
    private static final int HEADER_SIZE = 1 + IV_SIZE;
    private static final byte VERSION = 1;

    private static byte[] hmac(SecretKey macKey, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(macKey);
        return mac.doFinal(message);
    }

    private static byte[] seal(byte[] plaintext, SecretKey aesKey,
            SecretKey macKey, SecureRandom random)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_SIZE];
        random.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.ENCRYPT_MODE, aesKey, new IvParameterSpec(iv));
        byte[] encrypted = cipher.doFinal(plaintext);

        byte[] body = new byte[HEADER_SIZE + encrypted.length];
        body[0] = VERSION;
        System.arraycopy(iv, 0, body, 1, IV_SIZE);
        System.arraycopy(encrypted, 0, body, HEADER_SIZE, encrypted.length);

        byte[] tag = hmac(macKey, body);
        byte[] packet = Arrays.copyOf(body, body.length + tag.length);
        System.arraycopy(tag, 0, packet, body.length, tag.length);
        return packet;
    }

    private static byte[] open(byte[] packet, SecretKey aesKey,
            SecretKey macKey) throws GeneralSecurityException {
        // At least 1 header + 16 IV + 16 ciphertext + 32 tag.
        if (packet.length < HEADER_SIZE + 16 + TAG_SIZE) {
            throw new GeneralSecurityException("Invalid message");
        }
        int bodyEnd = packet.length - TAG_SIZE;
        byte[] body = Arrays.copyOf(packet, bodyEnd);
        byte[] suppliedTag = Arrays.copyOfRange(
                packet, bodyEnd, packet.length);
        byte[] computedTag = hmac(macKey, body);

        // Critical: verify MAC before CBC decryption.
        if (!MessageDigest.isEqual(computedTag, suppliedTag)) {
            throw new GeneralSecurityException("Invalid message");
        }

        int encryptedLength = body.length - HEADER_SIZE;
        if (body[0] != VERSION || encryptedLength % 16 != 0) {
            throw new GeneralSecurityException("Invalid message");
        }

        byte[] iv = Arrays.copyOfRange(body, 1, HEADER_SIZE);
        byte[] encrypted = Arrays.copyOfRange(
                body, HEADER_SIZE, body.length);
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.DECRYPT_MODE, aesKey, new IvParameterSpec(iv));
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey aesKey = generator.generateKey();

        byte[] macBytes = new byte[32];
        random.nextBytes(macBytes);
        SecretKey macKey =
                new SecretKeySpec(macBytes, "HmacSHA256");

        byte[] plain = "CBC needs integrity"
                .getBytes(StandardCharsets.UTF_8);
        byte[] sealed = seal(plain, aesKey, macKey, random);
        boolean valid = Arrays.equals(
                plain, open(sealed, aesKey, macKey));

        byte[] changed = sealed.clone();
        changed[changed.length - 1] ^= 1;
        boolean rejected = false;
        try {
            open(changed, aesKey, macKey);
        } catch (GeneralSecurityException expected) {
            rejected = true;
        }

        System.out.println("authenticatedRoundTrip=" + valid);
        System.out.println("tamperRejected=" + rejected);
    }
}
```

Compile/run:

```shell
javac AuthenticatedCbcDemo.java
java AuthenticatedCbcDemo
```

Expected stdout:

```text
authenticatedRoundTrip=true
tamperRejected=true
```

**Interpretation:** ciphertext altered after encryption no longer has a valid MAC, so `open()` rejects **before calling CBC decrypt**. HMAC authenticates header version, IV, and ciphertext. `MessageDigest.isEqual` reduces timing leakage from tag comparison; it does not eliminate every side channel in the entire system on its own.

**Intentional limitations of the demo:** no replay protection, no key IDs, no maximum packet size limit, no long-term key management, no user/request/AAD binding, no HTTP error hardening, and no key rotation. Production applications must address all of those; never replace standard protocols/AEAD with this pedagogical example when standardized options exist.

### 8.1. What If CTR + MAC Must Be Used?

Similar principles apply: the MAC must cover **the full nonce/counter + ciphertext + version + context** under a separate key; verify the MAC **before emitting plaintext**; counters must never repeat under the same key. Because CTR uses no padding, there is no `BadPaddingException`, yet **bit-flipping and keystream reuse** remain extremely dangerous without authentication and nonce discipline.

## 9. AEAD and AES-GCM: A Better Default for New Designs

**AEAD** combines encryption and authentication verification in one scheme; it can also authenticate **AAD – Additional Authenticated Data** without encrypting the AAD. Example AAD metadata: message type, protocol version, tenant ID, or transaction context. The AAD supplied must be **identical** on both encryption and decryption.

Java:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
GCMParameterSpec params = new GCMParameterSpec(128, nonce);
cipher.init(Cipher.ENCRYPT_MODE, aesKey, params);
cipher.updateAAD(aad);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
```

This snippet is **not standalone**: it requires `aesKey`, `nonce` (typically 12 bytes, **never repeated under the same AES key**), `aad`, `plaintext`, and exception handling. In JCE, `doFinal()` for GCM encryption typically returns **ciphertext concatenated with the authentication tag**; on decryption, pass the same key/nonce/AAD and the full ciphertext+tag for verification.

### 9.1. GCM Does Not Automatically Fix Every Mistake

- **Nonce reuse:** reusing a **key + nonce** pair with GCM is a severe security flaw that can break both confidentiality and authentication. Enforce unique nonce generation, message count limits, and state persistence across restarts.
- **Tag:** typically 128 bits—do not shorten it arbitrarily. Handle `AEADBadTagException` by rejecting the entire message; never feed plaintext to business logic before verification finishes.
- **AAD:** AAD is authenticated but **not encrypted**. Do not put secrets into AAD expecting them to be hidden. Identical AAD on both sides is mandatory.
- **Replay:** an attacker replaying an identical old ciphertext+tag still produces a valid tag. Replay defense requires state/protocol design.
- **Key storage and authorization:** AEAD does not manage keys, access permissions, or accidental key logging.
- **Streaming:** avoid passing unverified bytes downstream as trusted plaintext; APIs/frameworks must enforce processing along authentication boundaries.

**Never simply swap `AES/CBC/PKCS5Padding` for `AES/GCM/NoPadding` while keeping a 16-byte IV layout, IV-reuse habits, or ignoring tag handling.** Changing modes requires updating protocol, format, usage limits, and error handling.

### 9.2. When Should You Not "Just Switch Modes" in a Running System?

A system storing millions of CBC ciphertexts cannot decrypt them as GCM merely by changing the transformation string. Migrating requires version identifiers, reading old data safely, authenticating before using data, re-encrypting with AEAD under fresh nonces, and updating the format. If the legacy CBC protocol lacked a MAC, decrypting untrusted data should be treated as a dedicated risk rather than exposing a broad legacy endpoint.

## 10. Key, IV, Nonce, MAC, Tag, and Operational Format

An encrypted record design should answer:

- **Algorithm/mode/version:** is it AES-GCM or CBC+HMAC? Clear markers/metadata are required for accurate decryption and migration.
- **Key identity:** which key, which version? AES and MAC keys must be independent if using EtM; managed in an appropriate keystore/KMS/HSM.
- **IV/nonce:** how many bytes, how is it generated, could it repeat after crashes/retries/concurrent writers? IV/nonce can be stored alongside ciphertext.
- **Ciphertext:** how long, how is encoding/layout constrained? When storing Base64, encoding adds no confidentiality.
- **Authentication:** does the tag/MAC cover every field affecting how ciphertext is interpreted (version, IV, ciphertext, metadata, or AAD)?
- **Associated context:** which user/tenant/object/route does this record belong to? Should context be authenticated to prevent swapping valid ciphertexts between objects?
- **Replay/order:** are sequence numbers, request IDs, single-use tokens, or monitored counters needed?
- **Failure behavior:** reject on authentication failure, discard plaintext, and avoid leaking detailed reasons via API, logs, or timing.

Conceptual AEAD format example:

```text
version || key-id || nonce || ciphertext || tag
                   \_____ authenticated ______/
AAD: version, key-id, tenant/context (decided by protocol definition)
```

Diagram for learning only: what is "authenticated" depends on **the exact bytes passed into AAD and the MAC/tag**. Never assume every header in a file format is automatically authenticated. Getting schema, field order, encoding, lengths, and field separation right is part of security.

## 11. Error Handling in Java and Diagnostic Clues

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `InvalidKeyException` | AES key has wrong type/length, or incompatible provider/policy | Verify algorithm, key bit length, provider; never log secret key |
| `InvalidAlgorithmParameterException` | IV/nonce has wrong size/type, or provider rejects parameter | Check transformation and `IvParameterSpec`/`GCMParameterSpec` |
| `IllegalBlockSizeException` | ECB/CBC `NoPadding` where plaintext/ciphertext is not a block multiple | Use proper protocol format/padding; do not pad with arbitrary bytes |
| `BadPaddingException` on CBC decrypt | Corrupted padding, wrong key/IV/ciphertext, or tampered data | With EtM, **verify MAC before decrypt**; do not expose padding oracle |
| `AEADBadTagException` on GCM decrypt | Wrong key/nonce/AAD/tag or modified data | Reject message; check metadata and lifecycle, never ignore tag |
| CTR plaintext changes a few bytes without exception | CTR is unauthenticated; ciphertext modified or counter misaligned | Use AEAD/MAC and proper nonces |
| Two ECB ciphertexts share many identical blocks | Mode leaks repeating blocks | Do not use ECB for real messages; replace with AEAD |
| CTR leaks information about two plaintexts | Keystream/counter reused under same key | Fix nonce/counter generation, assess exposed data, and rotate keys |
| Decryption succeeds yet API business data is wrong | Possibly missing authentication/validity checks, swapped record, or replay | Enforce integrity, AAD/context, and authorization/replay controls |
| GCM fails with bad tag after migration | Wrong nonce/tag layout, AAD, or format/version | Define explicit format; test vectors and check exact version |

A common design flaw: returning HTTP 400 with text `invalid padding` and HTTP 401 with `bad MAC`, giving an adversary a strong oracle. On external interfaces, handle unauthenticated messages with uniform errors and observe controlled internal telemetry. Never expose raw provider exception messages as public responses.

### 11.1. Watch the Processing Order

**Wrong:**

```text
Receive IV+ciphertext
→ Decrypt CBC
→ Parse JSON
→ Check role inside JSON
→ Finally check HMAC (or skip checking)
```

**Right for Encrypt-then-MAC:**

```text
Receive packet, check framing/size
→ Verify HMAC over version+IV+ciphertext+context
→ If invalid, reject; do not decrypt
→ Only if valid, decrypt CBC
→ Parse data
→ Validate schema and business authorization
```

**Right for GCM:**

```text
Receive packet, parse metadata and enforce size limits
→ Supply key+nonce+AAD to GCM Cipher
→ doFinal verifies tag
→ If tag fails, reject all plaintext
→ If tag succeeds, parse/validate schema and business authorization
```

MAC/AEAD establishes an authentication boundary over bytes; **schema validation and authorization** remain separate steps.

## 12. Self-Check Questions with Answers

**1. Why is ECB considered unsuitable for encrypting an image?** Because identical plaintext blocks produce identical ciphertext blocks under the same key, revealing patterns/edges/structures even though pixel bytes are encrypted.

**2. Does using AES-256 solve ECB's repeating pattern leak?** No. A longer key does not change ECB's deterministic block-by-block mapping.

**3. CBC has a random 16-byte IV but no HMAC. Does the data have integrity?** No. Either the IV or ciphertext can be modified; a padding oracle can also emerge if the application responds differently to decryption errors.

**4. Is a CBC IV a secret?** No, it can usually be public. However, it must be fresh/unpredictable when needed and **integrity-authenticated** alongside the message under EtM.

**5. Why does `AES/CTR/NoPadding` encrypt 17 bytes without padding?** CTR turns AES output on counter blocks into a keystream XORed with plaintext; the final block uses only as many keystream bytes as needed, yielding a 17-byte ciphertext.

**6. If CTR uses the same key and counter block for two messages, what does an adversary learn?** By computing `C1 XOR C2`, the adversary gets `P1 XOR P2`; structured or known plaintext can expose significant data.

**7. Why does successful CTR decryption not prove the ciphertext is intact?** CTR decryption is XOR with the keystream; flipping a ciphertext bit flips the corresponding plaintext bit without any tag check.

**8. Why must CBC+HMAC verify the MAC before decrypting?** So unauthenticated data never enters padding decryption and creates an observable channel leading to a padding oracle.

**9. Can HMAC be replaced by SHA-256(ciphertext)?** No. An unkeyed public hash has no secret key; an adversary can alter ciphertext and recompute the hash.

**10. Does GCM prevent replay?** No. GCM authenticates a packet's contents, yet an old valid packet with a valid tag can still be replayed; sequence/state or single-use mechanisms are needed.

**11. Must a GCM nonce be kept secret?** No, but it **must never repeat under the same key**; startup/retry/concurrency bugs must not cause nonce reuse.

**12. When should CBC+HMAC be chosen instead of GCM?** Primarily for compatibility with an audited legacy format/protocol, designed with MAC-before-decrypt, separate keys, and versioning. New systems generally prefer properly provided and managed AEAD.

## 13. Pre-Production Checklist for Symmetric Encryption

1. **Never use ECB** to encrypt structured messages or user data.
2. Specify the full transformation; never call ambiguous `Cipher.getInstance("AES")`.
3. **Prefer AEAD** such as AES-GCM; if using CBC/CTR, add a proper authentication scheme with a separate key and verify before decrypting.
4. Generate **keys** from an appropriate cryptographic source and store them in a key management system; never hardcode in source, logs, or URLs.
5. Define IV/nonce size/format; **fresh unpredictable CBC IVs**; CTR/GCM **never repeat counters/nonces under the same key**, with usage limits and crash/retry handling.
6. Authenticate **version, IV/nonce, ciphertext, and semantic metadata/AAD**; do not omit critical fields from MAC/tag.
7. Never emit plaintext or execute business logic if authentication fails; external errors are uniform without padding/timing leaks.
8. Include **replay protection**, authorization, and schema validation per your threat model; MAC/AEAD does not supply these automatically.
9. Storage formats include version/key ID and a migration path; do not change modes while ignoring old data.
10. Write tests for **round-trip**, rejecting single-bit modifications in ciphertext/tag/IV/AAD on authenticated paths, context binding, and failure behavior.

## Official References

- [NIST SP 800-38A – Recommendation for Block Cipher Modes of Operation: Methods and Techniques](https://csrc.nist.gov/pubs/sp/800/38/a/final): definitions of ECB, CBC, CTR; IV/counter requirements and operational properties.
- [NIST SP 800-38D – Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): AES-GCM authentication and IV/nonce management requirements.
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): `Cipher` engine, providers, and Java crypto APIs.
- [Java SE 17 – Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformations, padding, AEAD/GCM, `updateAAD`, and encryption/decryption behavior.
- [Java SE 17 – GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag length and nonce/IV in Java.
- [Java SE 17 – Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html) and [MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): HMAC and tag comparison in an authenticated design.