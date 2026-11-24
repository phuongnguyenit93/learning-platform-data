# 7.1. Distinguishing Password Verifier Storage from Password-Based Data Encryption

**Passwords can participate in two very different security problems:**

1. **Storing a password verifier:** the system wants to know whether the user logging in provided the right registered password. The system **does not need to recover the original password** to do this.
2. **Encrypting data with a password-derived key (password-based encryption, PBE):** the system wants to protect data so that someone with the appropriate password **can regenerate the decryption key** and recover the plaintext.

Both problems often use a password-based key derivation function, a salt, and cost parameters, but **their output values, storage format, lifecycle, password-loss consequences, and verification mechanisms are completely different**. Mixing them up easily leads to severe flaws: storing passwords in a decryptable form, using the verifier directly as an encryption key, reusing one key for multiple purposes, or losing the ability to decrypt data after a password change.

This lesson focuses on **distinguishing and properly connecting the two models**, not on designing new cryptographic algorithms from scratch. After studying it, you will be able to:

- Explain password verifiers, password hashing, password-based key derivation, encryption keys, and authentication tags according to their exact roles.
- Design a verifier storage record with salt, algorithm, cost parameters, and derived result; verify re-entered passwords without storing plaintext.
- Design an encrypted data storage envelope with KDF salt, nonce/IV, ciphertext, and authentication tag; recover data using the password and verify integrity.
- Distinguish **KDF salt**, **AEAD nonce**, **pepper**, and **master key/DEK**, and explain why they cannot substitute for one another.
- Recognize risks of offline password guessing attacks, password changes/resets, key loss, replay, format/version issues, and implement them in Java 17+ using standard APIs.

## 1. Ask the right question: “verify a secret” or “recover data”?

Consider the same user setting password `p`, while two systems use it for two different purposes:

**System A — login:** the application only needs to answer *does the password just entered match the account?* On registration, the system computes a verifier from the password and stores that verifier. On login, it recomputes using the same rules and compares. The system has no “decrypt password verifier” step.

**System B — unlock a data vault:** the user has an encrypted document. To recover the contents, the system must recreate the exact key (or the key used to unlock the data key), decrypt the ciphertext, and **verify the authentication tag**. If the password is forgotten and no other recovery path exists, access to the data can be permanently lost.

| Question | Store password verifier | Encrypt data with password-derived key |
| --- | --- | --- |
| Goal | **Authenticate** the registered password | **Keep confidential and recover plaintext** |
| Sensitive input | Password supplied by the user | Password/secret used to unlock the data |
| KDF/password hashing | Produce a verifier resistant to offline guessing | Derive an encryption key or key-encryption key |
| What is stored | Salt, algorithm, parameters, verifier | KDF salt, parameters, nonce, ciphertext, tag; optionally wrapped DEK |
| Store original password? | No | No |
| Need to decrypt verifier? | No, only recompute and compare | No; must decrypt **ciphertext** using the derived key |
| Result when entered correctly | Login accepted **after other checks** | Plaintext is decrypted and tag is valid |
| Result when entered incorrectly | Verifier does not match | Wrong key derived; AEAD tag is typically invalid |
| Forgotten password | Can regenerate verifier via authenticated reset flow | Cannot automatically recover old data without a key/recovery path |
| Database leak | Verifier can be attacked with offline password guessing | Ciphertext can be attacked with offline password guessing to attempt decryption |
| Primary defense | Password hashing with appropriate cost + online attack defenses | Suitable KDF + AEAD + key management + recovery strategy |
| Identity/authorization | Must combine with account identity, rate limiting, MFA, authorization | Needs access control on ciphertext and verification of the data owner |

**A password is not ready to use as an AES key.** Passwords remembered by humans typically have low entropy and arbitrary length/encoding. Never do `new SecretKeySpec(password.getBytes(UTF_8), "AES")` and treat it as a secure design. A dedicated mechanism is required to handle the password, salt, cost parameters, and intended purpose.

## 2. Storing a password verifier: Password hashing

### 2.1. Registration and login flow

Notation:

- `P`: original password entered by the user.
- `S_v`: random salt unique to a single verifier.
- `params_v`: algorithm/version and computational cost parameters.
- `V = PasswordHash(P, S_v, params_v)`: stored verifier.

```text
Registration / valid password change         Login
------------------------------------         ----------------------------
Password P entered over secure channel       Newly entered password P'
             |                                         |
    Generate random salt S_v                      Read user record
             |                                  (salt, params, verifier)
 PasswordHash(P, S_v, params_v)                        |
             |                              PasswordHash(P', S_v, params_v)
             v                                         |
 Store: algorithm, params, salt, verifier              v
 Do not store password P                    Compare verifier with safe API
                                                       |
                                               Match    -> pass password check
                                               Mismatch -> reject
```

For passwords, choose a **tunable-cost password-hashing/KDF scheme**, such as **Argon2id** via a vetted library (often preferred when policy permits), or **scrypt/bcrypt/PBKDF2** depending on compatibility and compliance requirements. Argon2id can enforce memory cost; PBKDF2 uses many computation iterations and is common in environments requiring compatibility/FIPS. Do not choose raw `SHA-256(password)`, because it is far too fast to resist password-guessing attacks.

In Java 17, JCA/JCE provides `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`. This is an example of **standard library compatibility**, not a claim that PBKDF2 is always preferable to Argon2id in every system. Argon2id requires a suitable security library implementation; do not implement Argon2 from scratch.

### 2.2. What does a password verifier record contain?

Logical template:

```json
{
  "accountId": "user-42",
  "passwordVerifier": {
    "scheme": "PBKDF2WithHmacSHA256",
    "iterations": 600000,
    "salt": "base64-of-random-salt",
    "derivedVerifier": "base64-of-derived-bytes"
  }
}
```

The `base64-of-...` values illustrate where binary data belongs, **not a ready-to-use valid record**. In production, the format may be a PHC string or a versioned object depending on the scheme.

- **Salt:** each record has an independent salt generated by a CSPRNG, typically 16 bytes or more. A salt **does not need to be kept secret**; the same password with different salts produces different verifiers.
- **Cost:** iterations/memory/time/parallelism (depending on the algorithm) are stored so the system knows how to verify and plan upgrades. Choose according to current recommendations, benchmark on deployment hardware, and bound DoS load.
- **Verifier:** the stored result used for comparison; do not use it as a password, API token, AES key, or a secret sent back to the client.
- **Pepper (design-dependent):** a system-wide secret stored separately from the database, e.g., in a vault/HSM, which can add protection if only the database leaks. Pepper **does not replace** salt or password hashing; it requires its own rotation/recovery policy.

If the system uses a library with a standard password-hash format, let the library manage records, verification, versioning, and upgrades where appropriate. Do not write a custom parser that might accept overly large parameters, malformed values, or weak algorithms. Storing per-user verifiers does not by itself control who is authorized to reset a password.

### 2.3. Why can a “one-way” verifier still be guessed?

A password-hashing function is not an unconditionally uninvertible transformation. When an adversary obtains `S_v`, `params_v`, and `V`, they can pick a candidate `P_i`, compute `PasswordHash(P_i, S_v, params_v)`, and compare with `V`. This is **offline guessing**; weak passwords can still be discovered.

Protection comes from the **cost per guess**, per-record salt, and actual password strength, combined with restricting data read access and protecting any pepper used. Against **online** attacks on the login endpoint, you also need rate limiting, monitoring, proper session binding/locking, MFA, and responses that do not leak whether an account exists. A slow KDF alone does not prevent high-volume online requests.

A commonly misunderstood example:

```text
Password = "123456"
Salt random 128-bit
Verifier = PBKDF2(password, salt, cost)
```

A good salt ensures other users' records do not share the same verifier, but it does not turn `123456` into a high-entropy password. Someone who has the record can still try `123456` in their guess list.

### 2.4. Password reset functionality

When a user forgets their login password, the application can use an authenticated account recovery flow to **replace the verifier**:

```text
User proves recovery identity
        -> authorize password reset
        -> set NEW password
        -> generate NEW verifier salt
        -> store NEW verifier/params
        -> revoke sessions/tokens as policy requires
```

The application does not need to know the old password again. This is the design benefit of a verifier: **it only needs to verify true/false**, without needing the old secret to create a new record.

However, replacing the verifier **does not automatically re-encrypt** data encrypted with a key derived from the old password. This is the next critical boundary.

## 3. Encrypting data: Derive a key from the password, then use AEAD

Simplified model:

\[
K_e = KDF(P, S_e, params_e)
\]

\[
(C,T) = AEAD.Encrypt(K_e, nonce, plaintext, AAD)
\]

The decrypting side must have `P`, `S_e`, and `params_e` to recreate the exact `K_e`, then pass `C`, `T`, `nonce`, and `AAD` into AEAD decryption. **Accept the plaintext only after tag verification succeeds.**

```text
DATA ENCRYPTION                                     DATA DECRYPTION
---------------                                     ---------------
Password P                                          Password P'
   +-- KDF salt S_e / params_e                         +-- Read S_e / params_e
   |                                                       |
   +----> KDF --------> Encryption key K_e                 +----> KDF ---> K'_e
                             |                                             |
Plaintext -----> AES-GCM(K_e, fresh nonce, AAD)     Ciphertext+tag --> AES-GCM decrypt
                             |                                             |
         Store envelope (salt, params, nonce,          Auth tag valid and metadata valid?
         ciphertext, tag, version...)                    /              \
                                                       Valid           Invalid
                                                        |                |
                                                    Plaintext           Reject
```

Use a standard AEAD such as **AES-GCM** or ChaCha20-Poly1305 depending on library and deployment policy. AES-GCM provides confidentiality for plaintext and integrity checks for ciphertext/AAD via the tag. If decryption throws `AEADBadTagException`, it could be due to a wrong password/key, wrong nonce/AAD, or modified ciphertext/tag: the application usually **cannot reliably conclude which specific cause occurred** from that exception alone.

### 3.1. What must be stored so ciphertext can be reopened

An illustrative envelope (schema illustration, not an official wire standard):

```json
{
  "formatVersion": 1,
  "kdf": {
    "name": "PBKDF2WithHmacSHA256",
    "iterations": 600000,
    "saltBase64": "base64-of-independent-16-byte-salt",
    "outputBits": 256
  },
  "encryption": {
    "name": "AES-256-GCM",
    "nonceBase64": "base64-of-12-byte-nonce",
    "ciphertextAndTagBase64": "base64-of-ciphertext-and-16-byte-tag"
  }
}
```

In Java, `Cipher.doFinal` with AES-GCM typically returns ciphertext with the tag appended in the same byte array; the interchange format must **explicitly specify** where the tag goes, its length, and its encoding. Do not arbitrarily truncate or drop the tag.

Information such as algorithm, salt, parameters, and nonce **does not necessarily have to be secret**. Security relies on a password with sufficient entropy, a KDF that is not too fast to guess, the correct key, and proper data authentication. **You must preserve all metadata needed for decryption**: losing the salt/nonce/format can make it impossible to reopen the ciphertext even with the right password.

An envelope supplied by an untrusted source must not automatically dictate arbitrary algorithms or unbounded computation costs. The reader must enforce a version/algorithm allowlist, validate required fields and sizes, cap iterations and payload sizes, and bind security metadata into authenticated AAD/format where appropriate.

### 3.2. KDF salt is not the AES-GCM nonce

| Value | Where is it used? | Key requirement | Can it be public? |
| --- | --- | --- | --- |
| `S_v` — verifier salt | Password hashing to store verifier | Random, unique per verifier | Yes |
| `S_e` — encryption KDF salt | Deriving key from password for data | Separate purpose; stored for re-derivation | Yes |
| `nonce/IV` of GCM | One encryption operation under an AEAD key | **Never reuse the same (key, nonce) pair** | Yes |
| `AAD` | AEAD before encryption/decryption | Identical bytes/context on both sides; integrity-checked | Yes |
| `authentication tag` | AEAD verification of ciphertext/AAD | Must be verified before using plaintext | Yes |
| `pepper` if present | Additional credential/server policy defense | Secret, stored separately from database | No |
| `K_e` — encryption key | AES-GCM or key wrap | Secret; proper scope, lifecycle, and protection | No |

A salt is generated when creating **a new key derivation context**; a nonce is generated/assigned **for each encryption under the same key** according to the mode's rules. Do not take a salt and reuse it directly as the nonce merely because both are random bytes.

If you want to encrypt multiple messages with the same password and salt (i.e., the same key), you must manage a **unique nonce per key** and stay within AEAD message limits; multi-instance systems need a collision-avoidance mechanism. If the design always generates a fresh salt for every envelope, the derived key generally differs; you must still generate the nonce according to the algorithm's requirements and never assume salt guarantees all nonce properties.

### 3.3. Within what scope is “having the password lets you decrypt” true?

Distinguish **access control** from **cryptographic confidentiality**:

- If the server holds the data decryption key itself (KMS/DEK) and only uses the password verifier to grant access, **the server can still decrypt without the user's password** according to policy.
- If data is genuinely encrypted under a key only the user can recreate, then for the server to decrypt it needs the password or an equivalent-privilege key/recovery path.
- If the application sends the password to the backend to derive the key, the backend can see the password during processing. Do not claim “zero knowledge” merely because the password is not saved in the database.
- If choosing client-side encryption, evaluate where the password travels, which devices hold keys, how sharing and recovery work, and how data is stored on the server.

There is no default model that simultaneously lets the server read all data and guarantees the server can never decrypt it. Document clearly **who is trusted to possess plaintext/keys** in the threat model.

## 4. Why not use the verifier itself as the encryption key?

A common flawed design:

```text
storedVerifier = PBKDF2(password, salt, cost)
encryptionKey  = storedVerifier
ciphertext     = AES-GCM(encryptionKey, data)
```

If an attacker reads the database containing `storedVerifier`, they already hold **the encryption key itself** without needing to know the password. The purpose of a password verifier is inverted: a verifier is meant to be stored for checking, and must never simultaneously be the secret that unlocks data.

Another flawed design takes `SHA-256(password)` as both the verifier and AES key, then reuses that same key for HMAC, cookie signing, and encryption. Such reuse expands the blast radius when one value leaks, blurs key roles, and makes rotation/revocation difficult.

**Principle:** separate **credential-verification material** from **encryption key material**. Both purposes may originate from the same password if the threat model permits, but they must use **independent salts, parameters, and derivation contexts**, and never reuse a readable verifier value as a key.

One way to visualize this:

```text
                         Password P
                        /          \
           verifier purpose        encryption purpose
             salt S_v                  salt S_e
            cost_v                    cost_e
               |                        |
          PasswordHash               Password KDF
               |                        |
          Stored verifier            Secret K_e
           (can be stored)           (not stored as public verifier)
               |                        |
          Compare at login          AES-GCM / wrap DEK
```

Many systems should not even use the login password as the data encryption password. They can use an independently managed random data key (KMS/HSM), or a separate passphrase for encryption, depending on security and usability goals.

## 5. A better model for long-lived data: DEK and KEK

To avoid re-encrypting all data when changing a password, systems commonly use **envelope encryption**:

- **DEK (Data Encryption Key):** a sufficiently strong random key generated independently of the password; used with AEAD to encrypt data.
- **KEK (Key Encryption Key):** a key derived from the password via a password KDF, or issued by a KMS; used to **wrap/encrypt the DEK** via an authenticated mechanism.
- **Wrapped DEK:** the DEK encrypted under the KEK; stored alongside metadata enabling safe unwrapping.

```text
Random DEK ────────────────> AEAD encrypt data ──> ciphertext + data nonce/tag
    |
    +-- AEAD wrap using KEK <──── KDF(password, independent salt, params)
                         |
                   wrappedDEK + wrap nonce/tag + KDF metadata

Open data:
password -> KDF -> KEK -> verify/unwrap DEK -> verify/decrypt ciphertext
```

When the user **knows both the old password and the new password**, the application can use the old password to unwrap the DEK, derive a new KEK from the new password with a fresh salt, and **rewrap the same DEK**. Large data ciphertexts can remain untouched if the DEK does not change. Ensure atomic updates, consistent metadata/versions, and no key leakage.

This does not mean a password reset without the old password can do the same. Without **the old password or a recovery key**, you cannot recreate the old KEK to unwrap the DEK solely from the verifier and ciphertext.

### 5.1. Password change and password reset are not the same

| Event | Login verifier | Data encrypted directly from password | Data via DEK/KEK |
| --- | --- | --- | --- |
| Password change, old password known | Generate new verifier | Must decrypt with old key, then re-encrypt with new key | Unwrap DEK with old KEK, rewrap with new KEK |
| Forgot old password, only account reset privilege | Can replace verifier after recovery flow | **Cannot automatically decrypt old data** without recovery | Cannot unwrap DEK without a recovery path |
| Pre-issued recovery key available | Reset verifier per policy | Can decrypt if recovery key actually has a path to unlock data | Can unwrap/rewrap DEK via recovery key/wrapped copy |
| Server holds DEK in KMS | Reset verifier independently | Architecture-dependent | Server can rewrap under KMS permissions, no longer user-only key model |

**A successful account reset does not mean encrypted data is recoverable.** Product UX must inform users clearly before they rely on password-only encryption. If a recovery key, escrow, or organizational recovery privilege exists, explicitly state who holds decryption-equivalent authority.

## 6. Java 17+: implementing both flows separately

The following example uses **standard APIs built into Java 17+**:

- `SecretKeyFactory` + `PBEKeySpec` with `PBKDF2WithHmacSHA256` as a salted, cost-tunable KDF.
- `SecureRandom` to generate salts and nonces.
- `MessageDigest.isEqual` to compare the derived verifier.
- `Cipher` `AES/GCM/NoPadding` for authenticated encryption and tag verification before returning plaintext.
- **Two independent salts:** one for the password verifier, one for the encryption key.

This is a demonstration of **PBKDF2 illustrating both purposes**. For new system designs, evaluate Argon2id via an audited library and current regulations; do not assume the iteration count in this demo is permanently secure. Passwords in the code are public demo data, **not secrets to reuse**.

File `PasswordVerifierVsEncryptionDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public class PasswordVerifierVsEncryptionDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int ITERATIONS = 600_000;
    private static final byte[] CONTEXT =
            "private-note:v1".getBytes(StandardCharsets.UTF_8);

    static byte[] randomBytes(int length) {
        byte[] bytes = new byte[length];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    static byte[] derive(char[] password, byte[] salt) throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static boolean verify(char[] candidate, byte[] salt, byte[] storedVerifier)
            throws Exception {
        byte[] calculated = derive(candidate, salt);
        try {
            return MessageDigest.isEqual(storedVerifier, calculated);
        } finally {
            Arrays.fill(calculated, (byte) 0);
        }
    }

    static byte[] encrypt(char[] password, byte[] salt, byte[] nonce, byte[] plaintext)
            throws Exception {
        byte[] derivedKey = derive(password, salt);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(derivedKey, "AES"),
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(CONTEXT);
            return cipher.doFinal(plaintext);
        } finally {
            Arrays.fill(derivedKey, (byte) 0);
        }
    }

    static byte[] decrypt(char[] password, byte[] salt, byte[] nonce, byte[] ciphertext)
            throws Exception {
        byte[] derivedKey = derive(password, salt);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(derivedKey, "AES"),
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(CONTEXT);
            return cipher.doFinal(ciphertext);
        } finally {
            Arrays.fill(derivedKey, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "example demo password".toCharArray();
        char[] incorrect = "incorrect".toCharArray();

        // Purpose A: store verifier; no password decryption needed.
        byte[] verifierSalt = randomBytes(16);
        byte[] storedVerifier = derive(password, verifierSalt);
        System.out.println("Correct login: "
                + verify(password, verifierSalt, storedVerifier));
        System.out.println("Wrong login: "
                + verify(incorrect, verifierSalt, storedVerifier));

        // Purpose B: encrypt and recover plaintext with the password.
        // This salt is independent of verifierSalt.
        byte[] fileSalt = randomBytes(16);
        byte[] nonce = randomBytes(12);
        byte[] ciphertext = encrypt(password, fileSalt, nonce,
                "Confidential note".getBytes(StandardCharsets.UTF_8));
        byte[] recovered = decrypt(password, fileSalt, nonce, ciphertext);
        System.out.println("Decrypted: " + new String(recovered, StandardCharsets.UTF_8));

        boolean wrongPasswordRejected = false;
        try {
            decrypt(incorrect, fileSalt, nonce, ciphertext);
        } catch (AEADBadTagException expected) {
            wrongPasswordRejected = true;
        }
        System.out.println("Wrong decryption password rejected: "
                + wrongPasswordRejected);

        byte[] tampered = ciphertext.clone();
        tampered[0] ^= 1;
        boolean tamperingRejected = false;
        try {
            decrypt(password, fileSalt, nonce, tampered);
        } catch (AEADBadTagException expected) {
            tamperingRejected = true;
        }
        System.out.println("Tampering rejected: " + tamperingRejected);

        Arrays.fill(password, '\0');
        Arrays.fill(incorrect, '\0');
        Arrays.fill(storedVerifier, (byte) 0);
    }
}
```

Compile and run:

```bash
javac PasswordVerifierVsEncryptionDemo.java
java PasswordVerifierVsEncryptionDemo
```

**Stdout** (salts, nonces, and ciphertexts are randomly generated and not printed, so the output lines remain the same):

```text
Correct login: true
Wrong login: false
Decrypted: Confidential note
Wrong decryption password rejected: true
Tampering rejected: true
```

### 6.1. Detailed explanation of each part

**Verifier part:**

```java
byte[] verifierSalt = randomBytes(16);
byte[] storedVerifier = derive(password, verifierSalt);
boolean ok = verify(password, verifierSalt, storedVerifier);
```

`storedVerifier` is the value **used for comparison during authentication**. When saved to a database, it must be stored alongside `verifierSalt`, `ITERATIONS`, and the KDF id. The data that must be kept secret during processing is the password; the verifier/salt record must not be treated as material enabling decryption, though it remains sensitive security data because it can aid offline attacks.

**Encryption part:**

```java
byte[] fileSalt = randomBytes(16);
byte[] nonce = randomBytes(12);
byte[] ciphertext = encrypt(password, fileSalt, nonce, plaintext);
byte[] restored = decrypt(password, fileSalt, nonce, ciphertext);
```

In practice, you must store at least `fileSalt`, nonce, ciphertext with tag, profile version/KDF params, and any necessary AAD context. The demo uses a fixed AAD `private-note:v1` to bind **data type/version**; in multi-user/multi-file designs, bind id/tenant/resource into AAD under a clear schema and enforce corresponding authorization checks.

**Why can the same password yield two different KDF outputs?** `verifierSalt` and `fileSalt` are generated independently. Even when using the same password, differing KDF inputs generally produce different outputs. In advanced designs, enforce explicit **domain separation** between verifier and encryption rather than relying only on call sites not mixing them up. For password hashing and password-based encryption, you can also use different algorithms/profiles.

**Handling wrong passwords and modified data:** AEAD rejects when tag verification fails. The system must never pass plaintext from an unauthenticated operation into business logic. Besides a wrong password, tag failure can also result from modified data, metadata, nonce, or AAD. Do not use exceptions to leak to clients which specific part of the ciphertext was altered.

### 6.2. Intentional limitations of the demo

- The password is written directly in source solely to make the lesson runnable; real applications must receive it over a secure channel, never log it, and never hardcode it.
- `PBKDF2WithHmacSHA256` with 600,000 iterations is an **illustrative value**, not a substitute for benchmarking/current parameter planning under your environment and policy. Execution time depends on CPU, service scale, and DoS limits.
- `derive()` uses a fixed profile and does not serialize metadata. Real products must store/version the algorithm, cost, salt, nonce, AAD policy, and ciphertext; enforce input size checks and cost caps when reading external files.
- Each encryption in the demo generates a fresh salt and nonce. When reusing a derived key across multiple messages, you must have a unique nonce allocation mechanism suited to the mode and traffic scale. Never reusing an AES-GCM nonce with the same key is an independent requirement, **not solved by having a verifier salt**.
- `byte[]` arrays are zeroed after use and `PBEKeySpec.clearPassword()` is called; this **does not absolutely guarantee** every internal copy inside JCE/JVM is cleared immediately. Avoid creating multiple `String` copies of the password in production code where alternatives exist.
- `SecretKeySpec` and `Cipher` may create internal copies of keys; do not treat the Java heap as hardware-secure key storage. For high-security requirements, consider a KMS/HSM or a key service with appropriate policies.
- The demo encrypts small data directly with the password-derived key to illustrate the mechanism. Long-lived data should generally use a **random DEK and KEK** as in section 5 to simplify key management and support rotation.

## 7. Comparing the two storage models to avoid data-model confusion

### 7.1. Account credential record

```text
users
  accountId
  credentialVersion
  passwordHashScheme
  passwordHashParameters
  passwordHashSalt
  passwordVerifier
  passwordChangedAt
```

This record serves **account authentication**. It has no `nonce`, `ciphertext`, or `authenticationTag` because those are not components of a password verifier. A system may store the verifier as a self-describing string from a password-hash library instead of separate columns; the chosen schema must be consistent.

Having `passwordChangedAt` does not automatically grant access to files encrypted under a previous password. If the password changes, encryption logic requires a separate key migration plan.

### 7.2. Password-encrypted file envelope

```text
encryptedFiles
  ownerId
  fileFormatVersion
  kdfAlgorithm
  kdfCostParameters
  encryptionSalt
  aeadAlgorithm
  nonce
  ciphertextAndTag
  authenticatedContext
```

This record serves **data recovery**. `ownerId` and `authenticatedContext` are context bound into the format/AAD when needed, which does not automatically mean a logged-in user is authorized. The receiving side must enforce authorization separately.

Even without a password verifier here, decryption can still be attempted by trying passwords and checking whether the tag validates. In effect, the ciphertext's authentication tag itself creates an offline check for each candidate password: **encryption does not eliminate password-guessing risk if the password is weak**.

### 7.3. Envelope encryption with wrapped DEK

```text
encryptedFiles
  ownerId
  fileFormatVersion
  dataCiphertextAndTag
  dataNonce
  wrappedDEK
  wrappingAlgorithm
  wrapNonce
  passwordKdfSalt
  passwordKdfCostParameters
  versionedAAD
```

A principal holding the corresponding password/recovery key can unwrap the DEK and then decrypt the data. To support multiple devices or multi-user sharing, you can store **multiple wrapped copies of the same DEK** for authorized recipients, though distribution and revocation must be designed carefully. Revoking access to data that a recipient has already downloaded/decrypted cannot be guaranteed merely by deleting a wrapped key.

## 8. Threat model and cases that must be tested

### 8.1. Adversary limited to online login attempts

- **Verifier:** apply rate limiting, session controls, credential stuffing detection, risk-based MFA, and appropriate error messages. Password hashing needs suitable cost while enforcing resource limits to prevent DoS.
- **PBE data:** if an API exists to “try password to decrypt”, that API can also become an online guessing oracle. Rate-limit requests, restrict access, and avoid returning overly specific error distinctions.

### 8.2. Adversary obtains the database or encrypted files

- **Leaked verifier:** can be guessed offline using `password + salt + cost`. Salt defeats precomputed lookup tables; cost increases work; neither protects weak passwords from being guessed.
- **Leaked PBE ciphertext:** can be guessed offline by deriving keys and checking the AEAD tag, even without an explicit verifier field.
- **Random DEK wrapped by a password-derived KEK:** if the file contains a wrapped DEK and a verifiable tag, an adversary can also try passwords offline to unwrap it. A random DEK aids lifecycle management, but does not make a weak passphrase stronger.

Never advertise that “the ciphertext uses AES-256 so weak passwords are safe too.” Effective key strength from a password depends on **password entropy**, KDF cost, and how fast an attacker can test candidates.

### 8.3. Adversary can read both the verifier and encrypted files

If the system uses **`storedVerifier` as the key**, an attacker can decrypt immediately upon reading the DB. If verifier and encryption material are properly separated, the attacker still has to work against separate derivations; however, if the same password is used, successfully guessing the password from one asset compromises the other. Preferably consider independent secrets per purpose or server/KMS key management aligned with your threat model.

### 8.4. Password changes

Test all of the following:
1. Old password known, changed to new password: old verifier stops validating; encrypted data remains accessible per the re-encrypt/rewrap plan.
2. Reset without knowing old password: login works, but old data must be **reported as inaccessible** or use a predefined recovery path; never promise automatic decryption.
3. Rotate KDF parameters: verifiers can be upgraded on successful login; encrypted files must be migrated/re-encrypted/rewrapped via proper workflow, not by merely editing metadata iterations and expecting decryption to keep working.
4. Environment/library migration: preserve salt, nonce, KDF id, encoding, iterations, tag format, and AAD. Golden vectors are essential to avoid interop bugs.

## 9. Practical design checklist

### When designing a password verifier

- Choose a dedicated password-hashing scheme with a vetted library and current parameter policy; prefer Argon2id where suitable, PBKDF2 where compatibility/FIPS is required by applicable standards.
- Generate an independent salt per verifier; store salt + algorithm/version + cost + verifier. Never store plaintext passwords or reversible encryption of passwords.
- Perform verification via a dedicated library API or constant-time byte comparison after deriving with the same parameters. Bound inputs and costs; never let client data arbitrarily select weak algorithms.
- Apply login defenses: rate limiting, MFA, reset token protection, session revocation, auditing, and identity/authorization checks.
- Have a rehash/upgrade strategy upon successful login, ensuring migration does not break existing accounts.

### When designing password-based encryption

- Define who actually needs to decrypt, where the password appears, who holds keys, and whether server/recovery access is needed.
- Choose a suitable password KDF and cost, with a random salt dedicated to the encryption context. Derive the exact key length required by the algorithm (e.g., 32 bytes for AES-256).
- Encrypt with a proven AEAD and a unique nonce per key; bind metadata/context into AAD and verify the tag before using plaintext.
- Store all parameters needed for decryption (salt, KDF id/cost, nonce, ciphertext, tag, version), validating file/envelope format with strict limits and policy.
- For long-lived or multi-file data, consider a random DEK with a password-derived KEK, and design rewrapping and recovery before users onboard.
- Explicitly define flows for password change/reset, forgotten password, lost metadata/backups, key rotation, sharing, and access revocation.
- Never store a verifier as an encryption key; never use raw password bytes directly as an AES key; never use `AES/ECB/PKCS5Padding` or unauthenticated encryption for data requiring tamper protection.

## 10. Dangerous misconceptions

| False claim | Reality |
| --- | --- |
| “Once a password is hashed, you can still decrypt it if you want” | A password verifier has no decryption operation to recover the password; it can only be guessed |
| “Login needs to read the password back, so we must encrypt passwords” | Login only needs verification, not reading the password back; never store reversible passwords |
| “The PBKDF2 verifier is 256 bits, so let’s use it directly as the AES-256 key” | If the DB verifier leaks, the attacker immediately has the key; separate purposes/secrets |
| “Salt is a secret, so hide it alongside the key” | Salt is typically public; the real secrets are the password/secret and key |
| “A fresh salt means we don’t need a GCM nonce” | Nonce is an AEAD parameter with per-key uniqueness rules, distinct from KDF salt |
| “Wrong password in AES-GCM produces garbage, so checking UTF-8 is enough” | You must verify the tag; if AEAD fails, reject and never process plaintext |
| “Since it’s password-encrypted, resetting via email lets you read old data” | Resetting the verifier does not restore old KEK/DEK without a recovery path |
| “Hashing/password KDF increases password entropy” | A KDF only increases the cost per guess; input entropy does not increase |
| “Pepper replaces salt and password hashing” | Pepper is an extra layer with its own lifecycle, not a replacement for salt/hash |
| “Leaked ciphertext is 100% safe because it uses AES-256” | An adversary can guess passwords offline and check the tag if the password is weak |
| “Updating iterations in the envelope is enough to migrate” | Changing cost changes the KDF output; you must re-encrypt or rewrap properly |
| “Using the same password forces verifier and encryption to share salt/key” | Contexts and keys must be separated, using distinct salts or distinct secrets |
| “Java `String` erases the password from RAM when set to null” | Memory management may retain copies; use appropriate APIs, avoid logging, and minimize secret lifetime |
| “Having the right password grants access to all files” | Authentication does not replace authorization checks for owner, tenant, and resource |

## 11. Self-check exercises

**Question 1.** A system only needs to determine whether a login password is correct. What should it store?

**Answer:** Store a **password verifier** produced by a password-hashing scheme, along with salt, cost, and version/algorithm. Do not store the password or encrypted data that allows “decrypting the password.”

**Question 2.** Someone has a file encrypted with a password-derived key. Why must they store the salt and nonce?

**Answer:** The KDF salt is an input needed to regenerate the exact key; the nonce is an AEAD input needed to decrypt/verify the tag. Losing required metadata can make the file unopenable even with the correct password.

**Question 3.** If `storedVerifier = PBKDF2(password, salt)`, should you do `AES-GCM(storedVerifier, data)`?

**Answer:** No. The verifier is stored for authentication and may leak in a database breach; if also used as a key, an attacker reading the verifier can decrypt directly. Use separate key material and manage it with proper scope.

**Question 4.** Why is PBE vulnerable to offline password guessing even when no verifier is stored?

**Answer:** An adversary with salt, params, nonce, and ciphertext+tag can test candidate passwords, derive the key, and check the AEAD tag. Weak passwords can be guessed; a slow KDF raises cost but does not eliminate guessing.

**Question 5.** A user forgets their login password but proves account ownership via a recovery email. Can login be reset? Can files encrypted under the old password always be read?

**Answer:** The verifier can be reset via the account recovery flow; old files cannot be automatically decrypted without the old password, a DEK escrow/recovery key, or another pre-designed recovery path.

**Question 6.** Why can changing a password with KEK/DEK be cheaper than direct encryption?

**Answer:** You can unwrap a random DEK with the old KEK and rewrap it with the new KEK, leaving large data ciphertexts untouched. However, this still requires access to the DEK via the old password or a recovery path.

**Question 7.** In the Java example, why do both a wrong password and a modified ciphertext byte throw `AEADBadTagException`?

**Answer:** Both cause tag verification to fail; AEAD only confirms whether the inputs/key/nonce/AAD match the tag or rejects, without reliably classifying the cause for the application.

**Question 8.** Is encrypting data under a server-controlled KMS and storing a password verifier for login a password-only encryption model?

**Answer:** No. The server can open the data via KMS without knowing the user's password; the password is only a means of authenticating access, not the sole secret protecting data decryption.

## 12. Remember the architectural boundary

```text
                    PASSWORD
                       |
           +-----------+-------------+
           |                         |
      AUTHENTICATE              UNLOCK DATA
           |                         |
  Password hashing              Password KDF
  + verifier salt               + encryption salt
  + cost parameters             + cost parameters
           |                         |
      STORE VERIFIER              SECRET KEK/KEY
      (cannot decrypt)                 |
           |                     AEAD / unwrap DEK
      COMPARE AT LOGIN                 |
           |                      CIPHERTEXT
      AUTHENTICATION                   |
           |                      RECOVER PLAINTEXT
   then AUTHORIZATION               verify tag
```

**A password verifier answers “is this password right?”; a password-derived encryption key answers “can this password unlock the ciphertext?”.** Both involve a password, yet serve different goals, storage records, and recovery mechanisms. Solid design separates key roles, stores metadata for the right purpose, uses standard algorithms, and makes the consequences of forgetting/resetting a password explicit before real user data is stored.

### References

- OWASP Password Storage Cheat Sheet — password hashing, salt, pepper, cost parameters: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- RFC 9106 — Argon2 Memory-Hard Function: https://www.rfc-editor.org/rfc/rfc9106
- RFC 8018 — PKCS #5 Password-Based Cryptography Specification, PBKDF2: https://www.rfc-editor.org/rfc/rfc8018
- NIST SP 800-132 — Recommendation for Password-Based Key Derivation, Part 1: https://csrc.nist.gov/pubs/sp/800/132/final
- NIST SP 800-38D — Galois/Counter Mode (GCM) and IV/nonce: https://csrc.nist.gov/pubs/sp/800/38/d/final
- Java SE 17 `PBEKeySpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html
- Java SE 17 `SecretKeyFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/SecretKeyFactory.html
- Java SE 17 `Cipher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html
- Java SE 17 `MessageDigest`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
