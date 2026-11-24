# 5.1 What Does a MAC Prove When Two Parties Share a Secret Key?

## Learning Objectives

After this lesson, you can accurately explain the meaning of a **Message Authentication Code (MAC)** in a system where two parties share a secret key; identify the assumptions that must hold before trusting a verification result; distinguish message authentication from identity proof and non-repudiation; implement HMAC-SHA-256 in Java 17+; and design MAC verification, key protection, and replay protection at the protocol level.

**Core answer:** When Bob verifies the MAC of a message M using a secret key K shared between Alice and Bob, a valid result provides **cryptographic evidence, within the security assumptions**, that M has been authenticated with K and has not been modified in a way the MAC fails to detect. Bob can conclude that **an entity knowing K created a valid tag** (or that a forgery occurred with very small probability). However, **Bob cannot use the MAC to prove to a third party that Alice specifically created the tag**, because Bob could also create the exact same tag using the same K.

That distinction determines how MACs are used in APIs, webhooks, service-to-service communication, and systems that require accountability tracking.

## 1. What Is a MAC, and What Do the Parties Share?

Suppose Alice is a service sending a request and Bob is a service receiving it. Both parties have received the same **secret key K** through a secure key distribution process. K is not exposed publicly to network observers.

A MAC has two conceptual operations:

- **Tag generation:** T = MAC(K, M), producing an authentication tag T from key K and message byte sequence M.
- **Tag verification:** Verify(K, M, T) returns valid or invalid. With HMAC, the verifier recomputes the expected tag from K and M and compares it safely against the received T.

Typical flow:

~~~text
Alice                                          Bob
Holds the same key K                     Holds the same key K

M = request data
T = MAC(K, M)
              M, T  --------------------->
                                         T' = MAC(K, M)
                                         Compare T' with T
                                         Match -> MAC valid
                                         Mismatch -> Reject
~~~

**The message M is not necessarily encrypted for confidentiality.** In this scheme, an eavesdropper can read M if there is no TLS or encryption. A MAC adds integrity checking and authentication based on key possession, rather than making the data unreadable.

An important property: **the same key and the same input byte sequence** produce the same tag in deterministic MACs such as HMAC. If Bob runs MAC(K, M) himself, he produces the exact same result as Alice, because the system has no private signing key exclusive to Alice.

## 2. What Does a Valid MAC Actually Tell You?

### 2.1 Message integrity

If M is modified to M' by someone who does not know K, the tag T generated for M will generally **fail to verify for M'**. Thus a MAC helps detect unauthorized modification of **the bytes actually included in the MAC-protected input**.

For example: Alice sends a payment request with amount 100. An attacker changes the data to 900 while keeping the original tag. Bob recomputes the MAC for the altered message; the old tag does not match and Bob rejects it.

However, a MAC does not automatically understand business fields. If Alice only computes the MAC over the amount field while omitting currency, recipient, or operation, an attacker can modify the fields **outside the MAC scope** and verification will still pass. Selecting the exact data to authenticate is a mandatory part of protocol design.

### 2.2 Shared-key message authentication

With a secure MAC algorithm, K kept secret, and no procedural flaws, an adversary **who does not know K** cannot forge a valid tag for a new message with non-negligible probability, even after observing many valid message–tag pairs.

Therefore, a successful verification is evidence that the tag **is consistent with a party knowing K**, or is the result of a highly improbable successful forgery. That is what **message authentication** means in a symmetric-key model.

To state this precisely:

- Bob knows that **K and the message bytes M match the tag T**.
- Bob has grounds to believe that **an entity holding K created or was authorized to create the tag** within the defined threat model.
- Bob **has no independent cryptographic proof** identifying exactly which entity within the group holding K created the tag.

If only Alice and Bob hold K, and Bob knows he did not create the tag and K has not leaked, Bob can **infer from operational context** that Alice sent it. But this is an inference based on assumptions outside the MAC computation; the MAC evidence alone does not distinguish Alice from Bob.

### 2.3 A MAC does not provide non-repudiation

Suppose Bob brings the message "Alice agrees to transfer funds" and a MAC tag before an arbitrator. Alice can counter: "Bob also knows K; Bob could have created that (M, T) pair himself." Because both have the ability to compute MAC(K, M), the arbitrator **cannot conclude solely from the MAC that Alice created the tag**.

This is a fundamental limitation of **symmetric cryptography with shared keys**, not a flaw specific to HMAC.

When evidence is needed that can be verified with a public key and tied to a single signer, **digital signatures** are typically used: only the holder of the private key signs; others use the public key to verify. Digital signatures enable a stronger accountability model, though practical non-repudiation still depends on private key control, identity binding to the key, timestamps, certificate issuance processes, and incident handling. One should not promise that any digital signature automatically carries legal weight.

## 3. What a MAC Does Not Prove

| Common Claim | Proven by a MAC? | Reason |
| --- | --- | --- |
| "This message matches a valid tag under key K." | **Yes, if verified correctly.** | A MAC verifies the binding between K, the message bytes, and the tag. |
| "The protected data was not altered by someone without K." | **Yes, under the MAC's security assumptions.** | Changing bytes invalidates the old tag with overwhelming probability. |
| "Alice specifically, not Bob, created the tag." | **No.** | Both Alice and Bob know K and both can produce the tag. |
| "Alice cannot deny sending the message." | **No.** | Any party holding the same K can produce equivalent forged evidence. |
| "The content is kept confidential." | **No.** | A MAC does not encrypt plaintext; encryption/TLS is needed for confidentiality. |
| "This is a fresh request that was never sent before." | **No.** | A valid (M, T) pair can be replayed verbatim. |
| "The data was sent in order and on time." | **No.** | A MAC has no built-in clock, sequence number, or protocol state. |
| "The sender is authorized to perform this business action." | **No.** | Message authentication does not replace authorization, policy, and resource checks. |
| "The content is truthful, business-valid, and error-free." | **No.** | A party knowing K can still send incorrect or fraudulent data. |
| "The key has never been compromised." | **No.** | A valid MAC says nothing about K's secrecy status; a leaked key allows forgery. |

**Therefore, always name the guarantee accurately:** A MAC supports message integrity and authentication of a party **possessing a shared key**. It does not by itself prove the unique identity of the creator, the freshness of the request, or business correctness.

## 4. Prerequisites for Trusting a MAC Result

Do not interpret Verify = true in isolation from the system. At minimum, the following conditions must be verified:

1. **K is genuinely secret and sufficiently strong.** The key must be generated from a cryptographically secure random source (or a KDF designed for the appropriate purpose), not hardcoded in source code, not printed in logs, and not shared across entities beyond the trust boundary.
2. **Secure algorithm and parameters.** Choose a well-studied MAC such as HMAC-SHA-256, with an adequate tag length and the algorithm fixed by the protocol; do not build a MAC by naively concatenating a secret with the message and hashing.
3. **Both parties compute the MAC over the exact same byte sequence.** Charset, field ordering, canonicalization, headers, path, HTTP method, and body must be precisely specified. Different bytes produce a different tag.
4. **All fields affecting the request's meaning are protected.** For example, operation, path, tenant, user, amount, currency, recipient, payload version, request ID, and timestamp if needed.
5. **The tag is verified before performing any action with side effects.** Verification failure must reject processing. Do not accept the request first and only log the MAC error afterward.
6. **Replay protection is in place when the business logic requires it.** An old valid MAC can still verify today if the system does not check timestamps/nonces/sequences.
7. **Independent business authorization checks.** A party holding key K may be allowed to call the API, yet still be forbidden from transferring funds from a specific account or reading another tenant's data.
8. **Clear knowledge of which parties share K.** If multiple services share one key, the MAC only proves the sender belongs to **the group holding K**, without attributing it to a single service.

In the standard security model, a secure MAC is expected to resist **forging a tag for a new message even when an attacker has observed valid tags** (known as unforgeability under chosen-message attack). This is not an absolute guarantee for every system: weak keys, mishandled input bytes, or key leakage can break the entire model.

## 5. HMAC-SHA-256: The MAC Commonly Used in Java

### 5.1 HMAC is not plain SHA-256

**SHA-256** is an unkeyed hash function: anyone with the message can compute SHA-256(M). Therefore, attaching a public SHA-256 digest to a request **does not prove origin**; someone modifying the request simply computes a new digest.

**HMAC-SHA-256** uses a **secret key K** combined with SHA-256 in a dedicated HMAC construction, so only parties holding K are expected to produce valid tags for new messages. Intuitively:

~~~text
SHA-256(M)          : anyone with M can compute it.
HMAC-SHA-256(K, M)  : K is required to compute the correct tag.
~~~

Conceptual construction of HMAC:

~~~text
HMAC(K, M) = H( (K' XOR opad) || H( (K' XOR ipad) || M ) )
~~~

Where H is the underlying hash, K' is the key prepared to the block size, ipad/opad are two constants defined by the HMAC specification, and || is byte concatenation. **Do not implement this construction yourself** for applications: Java already provides Mac in JCA/JCE.

Do not replace HMAC with homegrown patterns such as SHA256(K || M). Especially with Merkle–Damgård hash constructions, prepending the key before the message can be vulnerable to length extension attacks in common designs. HMAC was designed to avoid these pitfalls.

### 5.2 Java 17+ APIs

Java provides:

- **javax.crypto.Mac**: initializes the algorithm, configures the key, processes bytes, and generates the tag.
- **javax.crypto.KeyGenerator**: generates keys for HMAC algorithms when supported by the provider.
- **javax.crypto.SecretKey**: represents a symmetric key.
- **javax.crypto.spec.SecretKeySpec**: wraps existing key bytes when the application receives a valid key from a key management system.
- **java.security.MessageDigest.isEqual**: compares two digest/tag byte arrays in a way that avoids content-dependent timing variations, making it more suitable than ordinary comparisons for tags.

The standard algorithm name commonly used in JCA is **HmacSHA256**; HMAC-SHA-256 produces a full **32-byte (256-bit)** tag. When transmitted as text, the tag can be represented in Base64 or hex. Converting to Base64/hex is only for protocol compatibility; **the key K must never be exported as text or sent alongside the message**.

A **Mac instance is stateful and should not be shared concurrently across threads** without dedicated synchronization or management. Each operation can create a new instance, or use safe per-thread/per-request instance management.

## 6. Java 17+ Example: Two Parties Sharing a Key, Testing Tampering and Replay

The example uses **KeyGenerator** to generate a 256-bit HMAC key for a single run; the sharedKey variable represents the key that Alice and Bob exchanged beforehand over a secure channel. In a real system, both processes must receive **the same key securely** from a KMS/secret manager or key distribution protocol; running KeyGenerator separately in two processes will generate **two different keys** and they will not be able to authenticate each other.

Create the file **SharedKeyMacDemo.java** (UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public class SharedKeyMacDemo {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int TAG_BYTES = 32;

    private static byte[] mac(SecretKey key, byte[] message)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance(ALGORITHM);
        hmac.init(key);
        return hmac.doFinal(message);
    }

    private static boolean verify(SecretKey key, byte[] message,
                                  byte[] receivedTag)
            throws GeneralSecurityException {
        if (receivedTag == null || receivedTag.length != TAG_BYTES) {
            return false;
        }

        byte[] expectedTag = mac(key, message);
        return MessageDigest.isEqual(expectedTag, receivedTag);
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance(ALGORITHM);
        generator.init(256);
        SecretKey sharedKey = generator.generateKey();

        // In this example, both Alice and Bob use the same sharedKey.
        byte[] original = "amount=100|currency=VND"
                .getBytes(StandardCharsets.UTF_8);
        byte[] modified = "amount=900|currency=VND"
                .getBytes(StandardCharsets.UTF_8);

        // Alice computes the tag and sends original + aliceTag.
        byte[] aliceTag = mac(sharedKey, original);

        // Bob uses the same key to verify.
        System.out.println("Bob verifies original: "
                + verify(sharedKey, original, aliceTag));

        // Someone on the network changes 100 to 900 without having the key.
        System.out.println("Bob verifies modified: "
                + verify(sharedKey, modified, aliceTag));

        // Bob can also produce the exact same tag for the same message bytes.
        byte[] bobTag = mac(sharedKey, original);
        System.out.println("Bob can produce the same tag: "
                + MessageDigest.isEqual(aliceTag, bobTag));

        // A MAC is stateless: replaying the exact message still verifies.
        System.out.println("Replay is still valid under MAC: "
                + verify(sharedKey, original, aliceTag));

        // The tag can be encoded as text; it contains none of key K.
        String encodedTag = Base64.getEncoder().encodeToString(aliceTag);
        System.out.println("Tag length in bytes: " + aliceTag.length);
        System.out.println("Base64 length: " + encodedTag.length());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SharedKeyMacDemo.java
java SharedKeyMacDemo
~~~

Typical output on Java 17+:

~~~text
Bob verifies original: true
Bob verifies modified: false
Bob can produce the same tag: true
Replay is still valid under MAC: true
Tag length in bytes: 32
Base64 length: 44
~~~

Explanation of each result:

1. **Original is valid:** Bob recomputes HMAC(K, original) with the same K so the tags match.
2. **Modified is rejected:** changing a byte changes the tag; with secure HMAC-SHA-256, the probability that a modified message accidentally produces the same tag is negligible.
3. **Bob can produce the same tag as Alice:** this is why **you cannot deduce who created the tag from MAC evidence alone**.
4. **Replay is valid as far as the MAC is concerned:** a deterministic MAC for the same K and M has no memory of previous uses. The system needs external freshness/nonce/sequence rules.
5. **32 bytes and 44 characters:** those are the tag bytes and its padded Base64 representation; Base64 is not a security guarantee or a secret key.

The example uses a simple text payload for clarity, **not a production-ready authenticated request format**: canonicalization, scope, timestamps, nonces, replay protection, authorization, and key storage policies are still needed. The program does not log or display key bytes.

**Regarding output accuracy:** the true/false lines rely on using the same key and bytes or modified bytes; an HMAC collision on a modified message is cryptographically negligible. The specific Base64 tag value changes across runs because the key is randomly generated, so the example only prints the tag **length**, without asserting a specific tag value.

## 7. HMAC Checks Bytes, Not "Meaning"

### 7.1 The ambiguous field concatenation problem

Consider two sets of fields:

~~~text
Set 1: user="ab", action="c"
Set 2: user="a",  action="bc"
~~~

If both sides build the message by directly concatenating **user + action**, both sets become **abc**. The MAC is still valid for the bytes **abc**, but it cannot distinguish the two ways of splitting the fields. This is a **data representation for authentication** bug, not an HMAC algorithm bug.

How to prevent it:

- Use a format with **per-field lengths**, explicit type tags, or a serializer with canonicalization and an agreed schema.
- Pin the **protocol version** so both sides apply the same interpretation.
- Protect **every field that can alter meaning or authorization**: method, path, query, body, tenant, user ID, amount, currency, recipient, timestamp, nonce, and operation type as appropriate.
- Clearly separate domains where keys or messages are used, such as requests and responses. When sharing a key across multiple purposes, use **separate keys** per purpose or a clearly designed domain separation mechanism.

Example of a protocol MAC input structure:

~~~text
version = 1
context = "payment-request"
method = "POST"
path = "/v1/payments"
timestamp = "1730000000"
nonce = "request-unique-id"
bodySha256 = SHA-256(rawBodyBytes)

MAC_input =
    encodeWithLengths(version, context, method, path,
                      timestamp, nonce, bodySha256)
tag = HMAC-SHA-256(K, MAC_input)
~~~

This is an **encapsulation algorithm description**, not standalone Java code and not a specific protocol standard. The encodeWithLengths function must be **uniquely defined for both parties**. How path/query, Unicode encoding, headers, body, and timestamp are extracted must be agreed upon beforehand, not changed ad hoc after deployment.

If the MAC is based on the raw HTTP body, the verifier must authenticate **the exact body bytes over which the sender computed the MAC**. Parsing JSON and re-serializing it may, depending on the library, change key order, whitespace, or number formatting and cause a tag mismatch. If you want to sign canonicalized content, choose a **specified canonical JSON rule** used consistently on both sides.

### 7.2 Verification order and input controls

A sound request-handling pipeline:

1. Limit the request size and read the minimum required metadata fields.
2. Determine the key ID/algorithm **only from an allowlist**; client-supplied data must not force the server to use a weak algorithm or an arbitrary key.
3. Reconstruct the exact protected bytes according to the agreed protocol version and algorithm.
4. Compute the expected tag and compare it against the received tag using a safe mechanism.
5. Check the time window, nonce/sequence, or idempotency per the replay-protection policy; make nonce recording **atomic** when running multiple instances.
6. Verify the caller's identity and **resource/business authorization**.
7. Only after the required conditions pass, proceed with business side effects.

The ordering of steps 4–6 may depend on architecture (for example, looking up a tenant's key before verification), but the invariant requirement is **never execute sensitive side effects before mandatory verifications succeed**. Return controlled errors; avoid putting keys, full tags, sensitive messages, or raw payloads into logs.

## 8. A Valid MAC Can Still Be Replayed

### 8.1 Replay attack

Suppose Alice sends:

~~~text
POST /transfer
amount=100
requestId=R1
tag=HMAC(K, protectedRequestBytes)
~~~

An attacker modifies nothing, merely **captures and resends the exact request and tag**. Bob still computes the matching tag. If the transfer business logic executes twice, the MAC did its job properly, but **the protocol lacks a mechanism to recognize old requests**.

Additional measures commonly combined:

- **MAC-protected timestamp:** limits the age of a request, e.g., a few minutes depending on the environment and allowed clock skew. A timestamp is only useful when the server **actually enforces the time limit**.
- **MAC-protected unique nonce or request ID:** the server remembers processed nonces within the replay window and rejects reuse. Recording must be safe across multiple servers so two concurrent requests are not both accepted.
- **Sequence number:** suitable for a session or ordered channel; requires state and handling of packet loss/recovery.
- **Idempotency key and business constraints:** especially for payments, repeating the same request ID must not execute the transaction a second time. Results/idempotency keys must be stored according to policy.

**Merely putting a timestamp or nonce into the MAC string without checking freshness or duplicates still does not prevent replay.** Likewise, a successful MAC does not tell you whether the message was already processed earlier.

### 8.2 Replay protection cannot replace authorization

A fresh request, valid under K and nonce, can still request access to an account that does not belong to the client. The MAC protects that request's integrity, but **authorization** must reject it. On an API, "knowing a key" must never be treated as unlimited permission over all resources.

## 9. Why "Who Holds the Key" Determines Attribution?

### 9.1 Only Alice and Bob hold K

Bob receives a valid tag: in a workflow where Bob is certain he did not create the request, K has not leaked, and no third party holds K, Bob can use the tag as **a basis for authenticating the counterparty within the system**. But if a dispute arises, Bob cannot prove to an outsider that Alice specifically created the tag because Bob has the same capability to fabricate the evidence.

**This is the difference between operational authentication and public proof.**

### 9.2 A group of services shares K

If services A, B, C, and D all use K, every service can produce valid tags. Receiving a tag only allows saying that **someone holding K** created it (assuming no key compromise). You cannot attribute it specifically to A based on the tag alone.

A better design when services need to be distinguished: use **per-client/per-service keys or pairwise trust keys**, with a key ID bound to clear identity and permissions; never issue one client's key to another client. However, a verifier server that shares the same key with a client still has the capability to generate that client's tags: a two-way MAC **still does not provide non-repudiation before a third party**.

### 9.3 K is stolen or a key holder is compromised

If K leaks, an attacker can forge valid MACs and impersonate any entity that the system equates with K. The verifier cannot detect this through tag comparison alone. When key compromise is suspected, revoke and rotate the key, restrict permissions, and audit requests and the incident.

Reliable logs and audit trails can supplement an investigation (timestamps, host, mTLS identity, request ID, authorization flow), but **logs controlled by the same party holding the key do not by themselves turn a MAC into non-repudiation evidence**.

## 10. MAC, Hash, Digital Signature, AEAD, and TLS: Use Each for Its Purpose

| Mechanism | Key and Verifier | Primary Guarantee | What It Does Not Automatically Provide |
| --- | --- | --- | --- |
| **Plain SHA-256** | No key; anyone can compute it | Digest for deduplication/comparison depending on context | Does not authenticate origin against an adversary who can alter data and recompute the hash |
| **HMAC-SHA-256** | Parties share a secret key | Message integrity and authentication under the shared key | No confidentiality, does not uniquely distinguish individual key holders, no replay protection |
| **Digital Signature** (e.g., Ed25519, RSA-PSS) | Signer holds private key, verifier uses public key | Authentication under a private key bound to an identity, public verification | No confidentiality by itself; requires trust/identity/key management and application-level freshness checks |
| **AEAD** (e.g., AES-GCM) | Encryptor/decryptor use a symmetric key | Data confidentiality and integrity authentication of ciphertext/AAD | Does not prove which key holder created the ciphertext; no automatic replay protection |
| **TLS** | Negotiates session keys, authenticates endpoints per configuration | Protects traffic within each TLS connection | Does not automatically protect data after TLS termination at proxies, logs, DBs, or downstream systems |

A request over HTTPS may still need an application-level HMAC if the system wants to authenticate **the payload independently of the transport connection** across parties or multiple intermediaries. Conversely, an application-level HMAC **does not replace TLS** when payloads or credentials must remain confidential and transport channel authentication is needed.

For data requiring both confidentiality and integrity, prefer **AEAD with a properly designed protocol**. Do not invent ad-hoc combinations of encryption and MAC or reuse one key for multiple purposes without a security review.

## 11. Shared Key Management in Java Applications

### 11.1 Key distribution and scoping

Use **SecureRandom/KeyGenerator** or an appropriate KMS/HSM system to generate high-entropy key bytes with an appropriate length policy. Both parties must receive the same K via an authenticated confidential channel or be granted key-usage permissions through a key management service. Never place K in URLs, frontend code, repositories, build artifacts, container images, logs, traces, or public configuration files.

Use **separate keys per environment**, client/service, and purpose. Do not reuse the same HMAC key across all tenants, all systems, and all roles. If multiple keys must be derived from one root secret, use a KDF designed for key derivation and context separation, such as HKDF in an appropriate architecture.

A **Key ID** (a non-secret key identifier) can accompany a request so the verifier selects the right key. The Key ID must stay under server control, bound to permissions/tenant, and never become a mechanism allowing a client to request an arbitrary key. Include identifiers that affect semantics in the authenticated content when the protocol requires it to prevent key or context confusion.

### 11.2 Rotation, lifetimes, and auditing

- Rotate keys periodically per policy or immediately upon suspected compromise; avoid using one key indefinitely.
- During rotation, define a grace window for the old key, associating key IDs with the active key and expiring keys.
- Avoid accepting weak algorithms solely for backward compatibility; the allowed algorithm list must be server-controlled.
- Monitor repeated verification failures, replays, and unauthorized key usage. Logs should contain **necessary metadata with sensitive data filtered out**, never secrets or full payloads when unnecessary.
- Revoke permissions of a compromised party; if multiple parties share one K, an incident at **one party may force key rotation for the entire group**.
- Recovery procedures must ensure both parties do not accidentally map the same key ID to different key bytes.

### 11.3 JCA/JCE practices and tag comparison

**MessageDigest.isEqual(expectedTag, receivedTag)** is preferable to **Arrays.equals** when comparing tags because it does not stop early based on the position of the first mismatching byte. Still required:

1. Validate the expected tag length before comparing (e.g., 32 bytes if the protocol uses full HMAC-SHA-256).
2. Bound input length before computing HMAC; reading an enormous payload still consumes CPU/memory.
3. Do not log tags or sensitive payloads in error messages. A tag may be public in the MAC threat model, but the request can contain secrets, PII, and sensitive metadata.
4. Handle Base64/hex decoding errors for the tag properly; reject strings with invalid alphabet/length and do not silently truncate or fix up data.
5. Initialize **Mac with the right key per request**; do not share unsynchronized mutable instances across threads.
6. Do not accept arbitrary client-declared MAC variants or tag lengths unless explicitly designed into the protocol and permitted by the server.

Tag length may be truncated under an **explicitly designed and reviewed protocol**, but arbitrarily shortening a tag to a few bytes or accepting any prefix increases forgery probability. In this lesson, examples keep the full 32-byte HMAC-SHA-256 tag.

## 12. Common Mistakes to Recognize

1. **"The tag is valid, so Alice must have created it."** False if Bob also holds K; Bob can create the tag himself.
2. **"A MAC is a type of non-repudiable digital signature."** No; a MAC authenticates with a symmetric secret key, whereas a digital signature has a private signing key and a public verification key.
3. **"A MAC hides information."** No; confidentiality requires TLS or appropriate encryption.
4. **"A valid MAC means it wasn't replayed."** No; an old tag still verifies against the old message bytes.
5. **"We signed amount, so we don't need to sign currency/recipient."** Wrong: unprotected fields can be tampered with.
6. **"Using SHA256(secret || message) is HMAC."** Wrong: that is a different construction and can be insecure; use JCA HmacSHA256.
7. **"Giving every service the same key makes management easy while still identifying the sender."** Wrong: attribution is lost and the blast radius of a key leak grows.
8. **"A Base64 tag is hard to forge because it's hard to read."** Wrong: Base64 only changes representation; strength comes from HMAC and the secret key.
9. **"Both sides understand the same JSON, so the MAC bytes must be identical."** Wrong: field order, whitespace, encoding, number formatting, and Unicode normalization can differ.
10. **"Arrays.equals is good enough for every security application."** Not recommended; compare tags using a content-independent mechanism like MessageDigest.isEqual and enforce fixed length.
11. **"A valid MAC means the user is allowed to perform any operation."** Wrong: authorization must evaluate permissions in the business context.
12. **"No need to rotate the key even though one client using K was compromised."** Wrong: every entity holding K can generate valid tags; an incident must trigger revocation/rotation and impact assessment.

## 13. Analysis Scenarios

### Scenario A — Two parties dispute who created a request

Alice and Bob use the same K. Bob presents a request and a valid tag and claims "Alice definitely created this request." That evidence is insufficient because **Bob could have computed MAC(K, request) himself**. Within the internal system Bob can still use the MAC to filter out forged requests from someone **without K**, but he cannot elevate it into independent proof that Alice was the author.

### Scenario B — Payment webhook

A provider sends a webhook with HMAC(K, canonicalRequest). The server verifies it successfully and processes the payment. Someone else captures the legitimate webhook and resends it. The MAC still succeeds because the request/tag pair is unchanged. The fix is to bind and **verify** event ID, timestamp, and nonce/idempotency, while protecting these fields in the MAC input; the server processes idempotently to avoid duplicate transactions.

### Scenario C — Two tenants sharing one key

Tenant A and tenant B are issued the same K. If tenant A generates a tag for a request with tenantId=B, the receiver may see a valid MAC. If the server does not check tenant authorization or does not use separate keys, the MAC **cannot distinguish** A from B. Per-tenant/per-client keys and authorization checks are needed; including tenantId in the MAC is **also insufficient** if both still share K and are allowed to choose any tenantId arbitrarily.

### Scenario D — Proxy transforms the request

Alice computes the tag over the original JSON bytes; a proxy parses and re-emits the JSON with a different property order. Bob computes the HMAC over the new bytes and sees a tag mismatch, even though the JSON objects may be logically equivalent. Specify signing the raw incoming bytes or a canonical standard agreed upon by both sides; avoid stripping fields or characters that affect business meaning.

## 14. Knowledge Check

**Question 1.** If Bob successfully verifies HMAC(K, M), what is guaranteed under the secret-K model?

**Answer:** The tag matches K and the exact protected bytes M; an adversary without K cannot easily forge a tag for new data. It does not uniquely identify the creator when multiple parties hold K.

**Question 2.** Why can Bob not present a MAC as standalone legal proof that Alice signed a message?

**Answer:** Bob also knows K and could have created the same message and tag. MAC evidence lacks public verifiability that distinguishes the creator.

**Question 3.** If an attacker changes 100 to 900 in the message, will the MAC detect it?

**Answer:** Yes, **if the amount is included in the protected bytes** and K has not leaked; the probability of a successful forgery with a secure HMAC is negligible.

**Question 4.** What happens if an attacker replays the exact message and tag?

**Answer:** The MAC still verifies. To reject replays, the system must check timestamps, nonces/sequences, idempotency, or business state.

**Question 5.** How does SHA-256(M) differ from HMAC-SHA-256(K, M)?

**Answer:** SHA-256 requires no key and anyone with M can compute it; HMAC uses a secret key K and therefore provides shared-key authentication.

**Question 6.** Does sending the tag in Base64 make the MAC more secure?

**Answer:** No. Base64 only encodes the tag as text; security comes from HMAC, key management, protected data scope, and proper verification.

**Question 7.** If Alice, Bob, and Carol all share K, can Bob know that Alice specifically sent a tag?

**Answer:** Not from the MAC alone. The tag is only consistent with some party holding K having created it; keys should be separated by identity with appropriate identification/authentication mechanisms added.

**Question 8.** Does a valid tag grant access to another user's account?

**Answer:** No. Independent authorization must verify permissions to act on the resource and enforce tenant boundaries.

**Question 9.** Why must the MAC be computed over bytes canonicalized by a clear rule?

**Answer:** HMAC only sees bytes. Logically identical data serialized differently produces different tags; ambiguous concatenation also allows different field sets to yield the same signed bytes.

**Question 10.** When should you consider digital signatures instead of a MAC?

**Answer:** When the verifier **must not hold the ability to create signatures** and should verify using the signer's public key, supporting a stronger accountability model; identity and private key management must still be handled properly.

---

**Takeaway:** In a system where two parties share a secret key, a MAC lets you verify that **the protected message is consistent with that key** and makes it very difficult for someone without the key to forge a new message. Because **both the sender and the receiver can create the same tag**, a MAC alone does not prove authorship and does not provide non-repudiation. Replay protection, confidentiality, authorization, and key management must be designed separately.
