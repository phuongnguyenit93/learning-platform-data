# 1.6 Protecting Data in Transit, at Rest, and in Memory

## Learning Objectives

After this lesson, you can distinguish the three states of data (in transit, at rest, in use in memory), identify the protection boundary of each control, choose suitable protection mechanisms in Java applications, and recognize implementation mistakes that expose sensitive data even when a system has "encryption enabled."

## 1. Looking Through the Data Lifecycle and Threat Model

A sensitive value such as personal information, a token, a secret key, or payment data typically passes through multiple states:

1. **Data in transit:** data moving across networks, e.g., browser → API, API → database, application → message broker or internal services.
2. **Data at rest:** data sitting on disk, in database tables, object storage, persistent caches, backups, snapshots, or log files.
3. **Data in use (in memory):** data already decrypted/read into the Java heap, native memory, buffers, in-process caches, or CPU registers for business processing.

| State | Typical Risks | Core Controls | Limitations to Remember |
| --- | --- | --- | --- |
| In transit | Eavesdropping, endpoint spoofing, packet tampering | TLS, certificate verification, mTLS when needed, API authorization | TLS protects the **connection segment** between two TLS endpoints; data may be decrypted at a proxy/gateway |
| At rest | Disk, backup, snapshot exposure, unauthorized datastore access | Disk/storage encryption; application-level AEAD encryption; KMS; IAM | Processes authorized to read can still retrieve plaintext; storing keys next to ciphertext weakens protection |
| In memory | Heap dumps, unauthorized debugging, crash dumps, logging, cache leaks | Minimize copies and lifetime; restrict dumps/logs/debugging; reduce process privileges | Java and GC do not guarantee immediate erasure of every copy of data |

**Cryptography protects against a specific class of threats; it does not replace authentication, authorization, key management, server access control, or monitoring.** Ask: which data needs protection, who can access it, where does it become plaintext, who holds keys, and what copies remain?

Example real-world flow:

~~~text
Client app -- HTTPS/TLS --> Java API -- TLS/mTLS --> Database
                               |
                          Java heap (plaintext
                          during business logic)
                               |
                         Store ciphertext in DB
                         + encrypted backups
                         + keys in KMS
~~~

If TLS terminates at a load balancer, the hop from load balancer to API is **another connection** and must be evaluated separately. If the DB stores ciphertext yet the API must read data, the API still holds plaintext in RAM at times.

## 2. Protecting Data in Transit: TLS and Endpoint Identity

### 2.1 What Does TLS Provide?

**TLS (Transport Layer Security)** protects network connections with three key properties:

- **Confidentiality:** network eavesdroppers cannot read application content.
- **Integrity:** unauthorized modifications to protected data are detected.
- **Endpoint authentication:** the client verifies the connected server via certificate chain and hostname; mTLS adds client certificate authentication if configured.

Conceptually, the TLS handshake negotiates algorithms, authenticates, and establishes session keys; application data is then protected with authenticated encryption. Modern TLS sessions use ephemeral key exchange to achieve **forward secrecy**: later compromise of the server's private key does not automatically decrypt all previously recorded traffic, provided ephemeral session secrets were not leaked.

Prefer **TLS 1.3** when systems support it and maintain **securely configured TLS 1.2** if compatibility is required. Never use legacy SSL, TLS 1.0/1.1, or weak cipher suites. Simply "using HTTPS" is only the starting point; certificate configuration, protocol versions, and TLS termination points still determine actual security.

### 2.2 Certificates, Truststores, Keystores, and Hostname Verification

- **Certificate (X.509 certificate):** binds a public key to a server or client identity; must validate trust chain, validity period, and matching identity.
- **Truststore:** the set of CAs/certificates the program trusts to verify peers. Java typically uses the JVM's default truststore unless configured otherwise.
- **Keystore:** stores the private key alongside the certificate of a party needing to prove its own identity; e.g., a TLS server or an mTLS client.
- **Hostname verification:** the domain name in the URL must match an identity in the certificate (typically in the Subject Alternative Name field). Trusting a CA while skipping hostname checks is insufficient.

**mTLS** requires both sides to present certificates for TLS-layer authentication. It is useful between services, yet does not replace business authorization: a TLS-authenticated client is still permitted to perform only the actions granted to that identity.

Strictly avoid patterns like "trust all certificates," ignoring certificate errors, or disabling hostname verification to fix connection errors. If a system uses an internal CA, import the proper CA into the truststore and manage certificate lifecycles; do not tear down verification.

### 2.3 Java 17+ Example: HTTPS with Standard HttpClient

File **TlsClientDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class TlsClientDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com"))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac TlsClientDemo.java
java TlsClientDemo
~~~

This example uses HTTPS and Java's default certificate verification mechanism. The HTTP status value depends on the server's actual response; if network, DNS, or certificate validation fails, the command may throw an error instead of printing a status. Never catch a TLS exception and fall back to plain HTTP. When configuring a custom CA or mTLS, supply an `SSLContext` with appropriate trust/key managers while preserving server identity verification.

**TLS scope:** TLS does not protect content from the decrypted endpoint itself, admins with process access, logs containing payloads, or network hops behind a TLS-terminating proxy. Therefore, every connection among API, DB, broker, cache, and internal services must be evaluated separately; highly sensitive data may also require application-layer encryption.

## 3. Protecting Data at Rest: Choosing the Right Encryption Layer

### 3.1 Complementary Protection Layers

- **Disk/volume or storage service encryption:** protects when disks, snapshots, devices, or backup media are stolen; usually transparent to applications. However, authorized accounts or processes can read data once the disk is unlocked.
- **Database-layer encryption:** e.g., encrypting data/log/backup files; protects physical storage, yet queries from authorized accounts can still return plaintext depending on architecture.
- **Application/field-level encryption:** the application encrypts selected values **before** storing them. The database only holds ciphertext; decryption rights and keys must be controlled separately. Search, sorting, and indexing over encrypted data must be designed explicitly.
- **Authorization, auditing, and backups:** restrict read/export permissions; encrypt all copies, test restores, and enforce retention periods. Prevent logs, CSV exports, or test environments from becoming uncontrolled plaintext copies.

Not every piece of information should be reversibly encrypted. **Login passwords** must be processed with a slow password hashing function using a unique salt per password, such as Argon2id, scrypt, bcrypt, or PBKDF2 with appropriate parameters; never store passwords with reversible AES and never use plain SHA-256 for password storage. **Hashing** for verification/comparison is not **encryption**; Base64 is merely representation encoding and provides no confidentiality.

### 3.2 AES-GCM: Both Confidentiality and Tamper Detection

For sensitive data requiring decryption, prefer an **AEAD (Authenticated Encryption with Associated Data)** algorithm like AES-GCM instead of manually combining encryption and integrity checks.

Components of an AES-GCM record:

- **Key:** a secret AES key, e.g., 256-bit, generated from a secure random source and managed via an appropriate KMS/secret manager.
- **Nonce/IV:** typically 12 bytes for GCM; **must never repeat under the same key**. The nonce need not be secret and can be stored alongside ciphertext. Random nonces require volume limits/key rotation schedules to bound collision probability; very high-volume systems need an explicit unique-nonce allocation strategy.
- **Ciphertext and authentication tag:** encrypted data plus tag (typically 128-bit) enabling detection of wrong key, wrong AAD, or ciphertext tampering. In JCA, `Cipher.doFinal()` for AES/GCM typically returns ciphertext with the tag appended.
- **AAD (Additional Authenticated Data):** data that need not be secret yet must be tightly bound to the ciphertext, such as record/tenant IDs and schema versions. The decryptor must provide the **exact same AAD**. AAD does not prevent replaying old ciphertexts by itself; anti-replay requires versions/sequences and business checks.
- **Version:** format version and key version (or key ID) to support decryption and future key changes; never write secret keys into the record.

**Never reuse a nonce with the same AES-GCM key**; doing so can destroy confidentiality and integrity. Never use AES/ECB or unauthenticated AES/CBC for data that could be modified by an adversary. Never invent cryptographic algorithms.

### 3.3 Java 17+ Example: Encrypting, Decrypting, and Detecting Tampered Ciphertext

This standalone program demonstrates a simple format: version byte + 12-byte nonce + ciphertext with tag. `KeyGenerator` creates a fresh key **for a single run only**; real applications need persistent key management and separate key IDs via KMS/HSM or a secret manager.

Save as **AesGcmDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmDemo {
    private static final byte VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] encrypt(byte[] plaintext, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce); // Fresh for each encryption with the same key.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(1 + NONCE_BYTES + ciphertextAndTag.length)
                .put(VERSION)
                .put(nonce)
                .put(ciphertextAndTag)
                .array();
    }

    static byte[] decrypt(byte[] payload, SecretKey key, byte[] aad)
            throws GeneralSecurityException {
        if (payload.length < 1 + NONCE_BYTES + TAG_BITS / 8) {
            throw new IllegalArgumentException("Invalid payload");
        }

        ByteBuffer input = ByteBuffer.wrap(payload);
        if (input.get() != VERSION) {
            throw new IllegalArgumentException("Unsupported version");
        }
        byte[] nonce = new byte[NONCE_BYTES];
        input.get(nonce);
        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] aad = "record:42".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Sensitive data"
                .getBytes(StandardCharsets.UTF_8);
        byte[] packed = encrypt(plaintext, key, aad);
        byte[] restored = decrypt(packed, key, aad);

        try {
            System.out.println("Restored accurately: "
                    + Arrays.equals(plaintext, restored));

            packed[packed.length - 1] ^= 1; // Simulate modifying one tag byte.
            try {
                decrypt(packed, key, aad);
                System.out.println("Tampering not detected");
            } catch (AEADBadTagException expected) {
                System.out.println("Tampering detected: true");
            }
        } finally {
            Arrays.fill(plaintext, (byte) 0);
            Arrays.fill(restored, (byte) 0);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 AesGcmDemo.java
java AesGcmDemo
~~~

Output when run with standard JDK JCA AES-GCM providers:

~~~text
Restored accurately: true
Tampering detected: true
~~~

Explanation: the encrypted data is restored with the original key and AAD. When one tag byte is altered, decryption throws `AEADBadTagException` before returning plaintext. Supplying wrong AAD or wrong key also causes authentication to fail. A tamper-detecting tag **does not prove who created the ciphertext** when multiple principals hold the key and does not prevent replay on its own.

**Example limitations:** the key lives only in RAM, so it cannot decrypt data across runs; random nonce usage requires scale assessment before production; the program does not address secure storage, key rotation, access control, replay protection, error handling, or preventing in-memory data copies. Never print keys, plaintext, or sensitive `byte[]` to console/logs. When storing real records, govern version, key ID, algorithm, nonce, and ciphertext/tag with a vetted format and clear operational procedures.

### 3.4 Key Management Matters Just as Much as the Algorithm

A common design is **envelope encryption**:

1. KMS/HSM manages the root/key-encryption key (KEK) under separate permissions.
2. The application generates or requests a **data encryption key (DEK)** to encrypt data.
3. Store ciphertext alongside the KEK-wrapped/encrypted DEK, key ID, nonce, and needed metadata; never store plaintext DEKs alongside data.
4. When reading, an authorized component asks KMS to unwrap the DEK, decrypts for the shortest duration needed, then releases controlled copies.

Apply least privilege to key usage; separate DB read rights from decrypt rights when the model allows; manage auditing, quotas, and revocation. **Rotation** must account for historical data: change the KEK, re-wrap DEKs, or re-encrypt data on schedule. Distinguish key loss (losing ability to recover data) from key compromise (data exposure risk). Key backups must be protected with verified recovery drills.

Never hardcode keys in Java source, `application.yml`, Git, Docker images, dumped/logged environment variables, URLs, or widely distributed config files. Environment variables/secret injection can serve as delivery channels, yet the application must still control who can view process configuration, dumps, and logs.

## 4. Protecting Data While in JVM Memory

Encrypting transport and disk **does not make plaintext vanish in memory**: to execute business logic, the JVM normally must see plaintext or hold references to objects containing it at some point.

### 4.1 Where Data Can Exist

- **Java heap:** `String`, `char[]`, `byte[]`, DTOs, collections, exception messages, caches, and object graphs.
- **Native/off-heap memory:** direct `ByteBuffer`, JNI/native libraries, TLS providers, drivers, and I/O buffers.
- **Unintended copies:** converting `byte[]` to `String`, string concatenation, JSON serialization, tracing, request/response logging, profiler memory.
- **Diagnostic artifacts:** heap dumps, core dumps, crash dumps, debugger/JMX/JFR, or copies generated by incidents and ops tools.

GC reclaiming an object does not mean erasing old data bytes in RAM promptly. **`String` is immutable**, so applications cannot reliably wipe `String` contents; even when wiping a `byte[]`/`char[]` you own, the JVM, libraries, or OS may still hold other copies. Absolute zeroization guarantees are not a default property of Java.

### 4.2 Practical Measures

1. **Minimize data and plaintext lifetime:** decrypt only the exact fields needed, never retain sensitive payloads long-term in sessions/caches, and release references once finished. Never read an entire sensitive record if business logic only needs one field.
2. **Use wipeable data containers when APIs permit:** for passwords read from a terminal, `Console.readPassword()` returns `char[]`. Wrap usage in `try/finally` and call `Arrays.fill(password, '\0')` in `finally`; avoid unnecessary conversion to `String`. For application-controlled plaintext `byte[]`, call `Arrays.fill(bytes, (byte) 0)` after use. This is risk reduction, not a guarantee of erasing all copies.
3. **Reduce copies/serialization:** avoid `toString()` on secret objects, logging DTOs, or stack dumps carrying sensitive parameters; log only masked identifiers or non-sensitive metadata.
4. **Protect operational tooling:** restrict debugger attach, JMX, heap dumps, and core dumps; control dump files and storage in CI/CD artifacts, support tickets, and object storage. When enabling heap-dump-on-OOM flags, enforce procedures to secure/delete dumps since they may hold plaintext and keys.
5. **Restrict runtime privileges:** dedicated OS/service accounts, container/host isolation, least-privilege access to secrets and KMS, timely library/JDK updates, and strict environment access control.
6. **Narrow key access:** keys may reside in application RAM while encrypting, yet HSM/KMS can keep root keys out-of-process; avoid keeping persistent key copies in singletons/caches unnecessarily.

For example, password input flows in Java should prefer `char[]`-returning methods like `Console.readPassword()`; always handle missing consoles in IDEs or background services. Do not call `Arrays.fill` on an array after exposing its contents via `String`/logs expecting those other copies to disappear on their own.

**There is no "flip one flag to safely encrypt the entire heap."** If an adversary controls the process, attaches a debugger, or reads service memory, most data the application processes is at risk of exposure. Identify and restrict such access according to your actual threat model.

## 5. Combining the Three Protection Layers in a Java Architecture

Suppose a Java API receives customer data, stores it in a DB, and returns results to another service:

| Step | Proposed Design | What to Verify |
| --- | --- | --- |
| Client calls API | HTTPS/TLS, user authentication, and API authorization | Valid certificates/hostnames; no HTTP fallback; no sensitive data in URLs |
| Gateway calls app | Dedicated TLS for gateway → service hop; mTLS if appropriate | TLS termination points and mutual identity |
| Service calls DB/broker | TLS per connection; dedicated accounts, least privilege | Never implicitly trust internal networks; proper certs and access rights |
| Service stores sensitive fields | App-level AES-GCM/AEAD when required by threat model; disk, backup, snapshot encryption | Unique nonce per key; context-bound AAD; no key/DEK leaks |
| Service uses plaintext | Decrypt close to usage, limit caches and copies, mask logs/traces | No plaintext/keys in exceptions, heap dumps, or error reports |
| Operations and recovery | KMS/IAM/auditing, rotation, backup/restore, and incident response | Valid data recovery works, privileges can be revoked, anomalous access detected |

**Defense in depth:** TLS protects transit; at-rest encryption protects stored copies; memory hygiene and runtime privileges reduce exposure during processing. These three layers work alongside authentication, authorization, key management, and operations. No single layer covers the others.

## 6. Common Misconceptions and Mistakes

| Misconception | Correct Principle to Remember |
| --- | --- |
| "With HTTPS, data is safe everywhere." | HTTPS protects configured TLS connections; plaintext can still sit at endpoints, gateways, DBs, caches, and logs. |
| "The DB has disk encryption, so staff with SQL access can't read the data." | Disk encryption is usually transparent once unlocked; authorization and sometimes field-level encryption are still needed. |
| "Using AES is enough; integrity isn't needed." | AES-GCM with tags/AAD provides authenticated encryption; unauthenticated AES/ECB and CBC are prone to abuse. |
| "GCM nonces are like salts; reusing them is fine." | Nonces **must be unique per key**; reuse in GCM can have severe consequences. |
| "Base64 or SHA-256 is secret encryption." | Base64 only changes representation; hashes are not reversible encryption; passwords need dedicated password hashing. |
| "Clearing `char[]` guarantees no password remains in RAM." | It only overwrites the managed array; copies created by the JVM/libraries/OS may still remain. |
| "mTLS decides which service may view records." | mTLS authenticates connection identity; business logic must still authorize each resource/action. |
| "Keys and ciphertext in the same DB still protect against DB leaks." | If the same access reads both keys and data, an attacker can decrypt; separate key management permissions. |

## 7. Scenario-Based Self-Check

**Scenario A.** An API runs HTTPS, the DB connection lacks TLS inside the same VPC, and backups are exported to object storage. Identify three boundaries to evaluate: the API → DB path, backup read permissions, and data state in API RAM. Add TLS for the DB hop, encrypt and restrict backups, audit logs/dumps and process privileges; client-side HTTPS does not cover these points.

**Scenario B.** A column is encrypted with AES-GCM, yet every record reuses the same fixed IV. This is a severe design flaw due to nonce reuse with the same key. Design a unique nonce mechanism, key/rotation governance, assess affected data, and re-encrypt securely; do not just rename variables or wrap in Base64.

**Scenario C.** An app masks passwords in the UI yet logs full request bodies and saves heap dumps on OOM. Data remains at risk of leaking via logs/dumps. Strip secrets from logs, bound sensitive data lifetime in the JVM, secure/isolate diagnostic artifacts, and review access permissions.

**Self-assessment questions:**

1. Which segment does TLS protect in an architecture with a reverse proxy? → Each individual TLS connection segment, up to its termination point.
2. Can an AES-GCM nonce be stored alongside ciphertext? → Yes; a nonce is not secret, though it must be unique per key.
3. What happens when decrypting AES-GCM with the wrong AAD? → Tag authentication fails; plaintext must not be used.
4. Why is disk encryption insufficient for a DB shared by multiple application accounts? → Accounts permitted to query can read plaintext; fine-grained permissions and sometimes field-level encryption are needed.
5. Why is `Arrays.fill()` risk reduction rather than an absolute guarantee? → It only overwrites the referenced array; copies created by the JVM/libraries/OS may still persist.

**Takeaway principle:** clearly map where data lives, who can read it, where it gets decrypted, and how keys are protected. Use TLS for every transport hop, AEAD with solid key management for data requiring encryption at rest, and minimize plaintext and sensitive traces in memory, logs, and diagnostic tools.
