# 9.9 Limitations of a Successful Verify When the Public Key Is Not Bound to a Trusted Identity

## Learning objectives

After this lesson, you will explain precisely what `Signature.verify(...) == true` means in Java; recognize why a **mathematically valid signature does not equate to data coming from the expected person or organization**; distinguish **public key**, **identity**, **certificate**, **trust chain**, and **authorization to perform an action**; simulate the vulnerability of trusting an adversary-supplied public key; and design the proper verification order for messages, APIs, update files, or JWTs.

This lesson belongs to **9. Digital Signatures** in Java Advance – security-cryptography. The focus is not on implementing Ed25519/RSA/ECDSA from scratch, but on the **limits of the verify step** and how to **bind verification keys to trusted identities**. Examples include standalone Java 17 code; certificate/PKIX sections explain system-level checks without pretending a single `verify` call can replace them.

## 1. What does `verify == true` actually tell us?

A digital signature is typically described by four elements:

- `M`: the **exact byte sequence** of the signed message, not “content that looks alike.”
- `S`: the signature byte sequence.
- `PK`: the public key used to check the signature, paired with a secret private key.
- `algorithm/parameters`: a scheme such as `Ed25519`, `SHA256withECDSA`, or `RSASSA-PSS` with matching PSS parameters.

The verification check can be written as:

```text
Verify(algorithm, publicKey, messageBytes, signatureBytes) = true/false
```

Assuming secure algorithms/implementations and a protected secret key, **`true` indicates that the signature matches `PK` and `M` under the chosen scheme**. It does not automatically imply that `PK` belongs to “Bank A,” “Software Publisher B,” “Account C,” or “server example.com.”

Two questions must be kept separate:

1. **Cryptographic verification:** “Is this signature valid for this message under the public key being used?”
2. **Identity/trust binding:** “Is that public key genuinely authorized to represent the exact party the application trusts, in the right role and context?”

Answering “yes” to question 1 alone **does not satisfy** question 2.

Two additional layers are usually needed to make an acceptance decision:

3. **Authorization:** “Is the authenticated party permitted to perform *this action* on *this resource*?”
4. **Freshness/protocol context:** “Does the message match the intended recipient, purpose, version, validity window, and has it not been replayed?”

A valid signature does not mean “safe to execute.” These concepts must be checked **together** under an explicit policy.

### Comparing valid vs. invalid conclusions

| Observation | Sound conclusion | Unfounded conclusion |
| --- | --- | --- |
| `Signature.verify(signature)` returns `true` | Signature matches the supplied message bytes and public key | “The message was definitely sent by Alice” |
| Public key is included in the payload with the signature | Key exists as parseable bytes | Key is endorsed by Alice/a CA/the publisher |
| Self-signed certificate passes `cert.verify(cert.getPublicKey())` | Certificate's self-signature is valid under the key inside that certificate itself | Certificate is trusted by an organization's trust anchor |
| Certificate chain accepted against a set of trust anchors | Signature chaining and path constraints passed per the applied validation policy | Certificate necessarily belongs to the **exact expected hostname/tenant/role** |
| Update file signature passes against a pinned key | File bytes match the pinned update key | File was not rolled back, is a newer version, or installation is always permitted |

## 2. Classic vulnerability: letting the sender choose the verification key

Suppose an API accepts data shaped like:

```json
{
  "sender": "trusted-publisher",
  "message": "publish-version-42",
  "publicKey": "<sender-supplied-public-key>",
  "signature": "<sender-supplied-signature>"
}
```

In this illustrative payload, `publicKey`, `sender`, and `signature` are **all client-controlled**. If the server executes:

```text
publicKey = parse(request.publicKey)
verified  = Verify(publicKey, request.message, request.signature)
if (verified) accept(request.sender, request.message)
```

then calling `Verify` may be cryptographically sound while the **acceptance rule** is broken:

1. The attacker generates their own new key pair.
2. They sign whatever message they want with their own private key.
3. They send the signature, their own public key, and claim `sender = "trusted-publisher"`.
4. The receiver parses the supplied key, calls `verify`, and gets `true`.
5. The application **mistakes the attacker's key for the publisher's key**.

No need to break Ed25519, RSA, or ECDSA. The flaw lies in **determining which public key is trusted**, not in the signature check itself.

**Core rule:** A public key can travel over the network, yet its **origin and usage authority** must be authenticated via an independent trusted channel or workflow. The `sender` field is merely an unverified **claim**. In a sound protocol, the verification public key must come from a pre-provisioned trust store, a validated certificate chain bound to the right identity, or an equivalent binding mechanism.

### Three distinct scenarios

- **Trusted key, invalid signature:** reject because `verify` fails.
- **Valid signature, untrusted key or bound to wrong identity:** **must still reject** even though `verify` succeeds.
- **Valid signature, trusted key, yet unauthorized or expired request:** **must still reject** because policy/authorization/freshness fails.

A system must satisfy **all mandatory conditions** before treating a message as valid at the business layer.

## 3. Runnable Java 17 example: verification succeeds, yet forged identity is blocked

The following program uses **Ed25519** purely for illustration (the exact same issue applies to RSA-PSS and ECDSA signatures). It generates two independent key pairs:

- `trusted`: key pair representing an **identity already trusted by the application** in the simulation.
- `attacker`: key pair controlled by an adversary.
- `trustedPin`: SHA-256 fingerprint of the **SubjectPublicKeyInfo (SPKI) DER** of the trusted public key. In this self-contained demo, the pin is computed at startup to represent an existing trust anchor; **this is not a real trust-distribution workflow**.
- `verifyWithPinnedKey`: accepts a signature only when the candidate public key matches the chosen pin **and** the signature verifies cleanly.

Create **`SignatureIdentityDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;

public final class SignatureIdentityDemo {
    private static final String SIGNATURE_ALGORITHM = "Ed25519";

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance(SIGNATURE_ALGORITHM);
        KeyPair trusted = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        byte[] message = "transfer=100&to=alice"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changedMessage = "transfer=900&to=alice"
                .getBytes(StandardCharsets.UTF_8);

        byte[] trustedSignature = sign(trusted, message);
        byte[] attackerSignature = sign(attacker, message);

        KeyFactory factory =
                KeyFactory.getInstance(SIGNATURE_ALGORITHM);
        PublicKey trustedFromSpki = factory.generatePublic(
                new X509EncodedKeySpec(trusted.getPublic().getEncoded()));
        PublicKey attackerFromSpki = factory.generatePublic(
                new X509EncodedKeySpec(attacker.getPublic().getEncoded()));
        byte[] trustedPin = spkiSha256(trustedFromSpki);

        System.out.println("Trusted signature verifies: "
                + verify(trustedFromSpki, message, trustedSignature));
        System.out.println("Attacker signature with attacker key verifies: "
                + verify(attackerFromSpki, message, attackerSignature));
        System.out.println("Attacker signature with trusted key verifies: "
                + verify(trustedFromSpki, message, attackerSignature));
        System.out.println("Attacker key matches trusted pin: "
                + MessageDigest.isEqual(trustedPin,
                        spkiSha256(attackerFromSpki)));
        System.out.println("Policy accepts attacker message: "
                + verifyWithPinnedKey(attackerFromSpki, trustedPin,
                        message, attackerSignature));
        System.out.println("Policy accepts trusted message: "
                + verifyWithPinnedKey(trustedFromSpki, trustedPin,
                        message, trustedSignature));
        System.out.println("Policy accepts changed message: "
                + verifyWithPinnedKey(trustedFromSpki, trustedPin,
                        changedMessage, trustedSignature));
        System.out.println("Replay cryptographic verification succeeds: "
                + verify(trustedFromSpki, message, trustedSignature));
    }

    private static byte[] sign(KeyPair pair, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(SIGNATURE_ALGORITHM);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(PublicKey publicKey, byte[] message,
                                  byte[] signatureBytes)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(SIGNATURE_ALGORITHM);
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signatureBytes);
    }

    private static byte[] spkiSha256(PublicKey publicKey)
            throws GeneralSecurityException {
        byte[] spki = publicKey.getEncoded();
        if (spki == null) {
            throw new GeneralSecurityException(
                    "This public key cannot be exported as SPKI");
        }
        return MessageDigest.getInstance("SHA-256").digest(spki);
    }

    private static boolean verifyWithPinnedKey(
            PublicKey candidate, byte[] trustedPin,
            byte[] message, byte[] signatureBytes)
            throws GeneralSecurityException {
        if (!MessageDigest.isEqual(trustedPin, spkiSha256(candidate))) {
            return false;
        }
        return verify(candidate, message, signatureBytes);
    }
}
```

Compile and run on JDK 17 or later with an Ed25519 implementation:

```bash
javac --release 17 SignatureIdentityDemo.java
java SignatureIdentityDemo
```

**Verified actual stdout** (key/signature values are randomly generated, yet the program only prints boolean results):

```text
Trusted signature verifies: true
Attacker signature with attacker key verifies: true
Attacker signature with trusted key verifies: false
Attacker key matches trusted pin: false
Policy accepts attacker message: false
Policy accepts trusted message: true
Policy accepts changed message: false
Replay cryptographic verification succeeds: true
```

**Line-by-line explanation:**

1. `Trusted signature verifies: true`: signature created with the trusted private key matches the trusted public key re-imported from SPKI.
2. `Attacker signature with attacker key verifies: true`: **this is the dangerous case** if an application lets the client supply a public key and treats `true` as a trusted identity. This result is completely valid cryptographically, yet does not authenticate the sender as the trusted publisher.
3. `Attacker signature with trusted key verifies: false`: the attacker's signature does not match the trusted public key; selecting the right key changes the decision.
4. `Attacker key matches trusted pin: false` and `Policy accepts attacker message: false`: checking key binding before accepting the signature blocks the forged key.
5. `Policy accepts trusted message: true`: both the key and signature satisfy the example's trust record.
6. `Policy accepts changed message: false`: a signature for `transfer=100` is invalid for content modified to `transfer=900`.
7. `Replay cryptographic verification succeeds: true`: resending the exact valid message and signature still passes `verify`. Signatures **do not automatically prevent replay**.

**Distinguishing simulation from real systems:** the demo's `trustedPin` is computed from a public key **freshly generated in-process**, so it **does not prove this key genuinely belongs to an external organization**. In production, pins or trusted public keys must be **pre-provisioned over an authenticated channel** (e.g., an application shipped with hardcoded keys under release controls, an audited trust store, or authenticated configuration). Never compute a pin on first sight from the very `candidate` brought in by an untrusted request and immediately use it to accept that request: doing so brings back the original vulnerability.

`getEncoded()` typically returns **SPKI DER** for software public keys; the demo checks for `null` because not all keys/providers allow exporting encodings. The SHA-256 hash of SPKI is **not an X.509 certificate**, nor does it manufacture trust on its own. `MessageDigest.isEqual` compares fingerprint bytes cleanly, yet the fundamental problem is the **provenance of the trusted fingerprint**, not the byte comparison.

## 4. Binding a public key to a trusted identity

A trusted key binding can be described by a tuple:

```text
(expectedIdentity, allowedPurpose, trustedPublicKey,
 algorithmPolicy, validity/rotationPolicy, provenance)
```

For example, a software updater must know beforehand **which key is allowed to sign updates**, for **which product**, valid during **which period**, and **who has authority to modify the key registry**. Storing a bare public key without identity/purpose invites confusing different publishers or staging/production environments.

### Ways to establish trust

| Mechanism | Where does initial trust come from? | When is it suitable? | Operational risks to manage |
| --- | --- | --- | --- |
| **Public-key pinning** | SPKI bytes/fingerprint provisioned over a trusted channel | Closed apps, updaters with a small known set of publishers | Rotation, backup keys, revocation, shipping software fixes if old pin breaks |
| **Trust store/allowlist** | Approved key/identity list with change control | Internal systems, multiple publishers/tenants | Admin privilege separation, key ID collisions, policy expiry, retiring old keys |
| **PKI / X.509** | Pre-trusted CA/trust anchors, then path validation and name/role checks | TLS, mTLS, enterprise/server/user certificates | Revocation, CA changes, hostname/SAN, EKU/KeyUsage, path policies |
| **TOFU (trust on first use)** | First-seen public key recorded when no other auth channel exists | Certain SSH/peer-to-peer workflows per policy | First contact vulnerable to MITM; must alert on key changes and verify out-of-band |
| **Keys published via authenticated channel** | Endpoint/metadata bound to trusted issuer, protected by HTTPS/TLS, policy, or another trusted signature | JWKS/JWT, federated systems | Never take URL from arbitrary payload; bind issuer/tenant/`kid` and caching |

No single mechanism is universally best: the choice depends on signer count, identity policy, rotation scale, protocol standards, and threat model. **Every mechanism must have an anchor where trust begins.** If an adversary simultaneously controls payload, signature, public key, and the “pin list,” cryptographic checks cannot recover authentic identity.

### Key pinning: what are you pinning?

There are at least two distinct concepts easily confused:

- **SPKI pin:** SHA-256 over the public key's DER `SubjectPublicKeyInfo` bytes, binding to the **public key** and associated algorithm.
- **Certificate fingerprint:** SHA-256 over the **entire certificate DER**; renewing/re-issuing a certificate changes the fingerprint even if the public key stays the same.

Both values render similarly in hex/Base64; inspecting the hash string alone **cannot tell them apart**. If a design uses an SPKI pin, state clearly that source bytes are `publicKey.getEncoded()` in SPKI format, not `certificate.getEncoded()`. A pin is **not** a secret, yet its integrity and provisioning channel must be protected.

In a multi-key trust store, look up by **expected identity** and valid **key ID**, then verify with the resolved key. A `kid` field arriving in a request may be used as a **lookup hint within an allowlist**, never as “proof the key is trusted” or to fetch keys arbitrarily from a sender-specified URL.

## 5. X.509 certificates: proving a trust path differs from proving identity

A certificate can carry a public key, subject, Subject Alternative Name (SAN), validity dates, issuer, Key Usage, Extended Key Usage, and issuer signature. Yet merely parsing the certificate or calling `certificate.verify(issuerPublicKey)` is **not enough**.

### Required steps when relying on PKI

1. **Select appropriate trust anchors** from a trusted trust store. Never trust a root CA merely because its self-signature is valid. A “trusted root” is a prior trust-distribution decision.
2. **Validate the certification path** (issuer→subject, signatures, Basic Constraints, path length, validity dates, policies, algorithm/key strength, and standard path constraints). Java provides `CertPathValidator.getInstance("PKIX")` and `PKIXParameters` with application-configured trust anchors.
3. **Check the exact expected application identity**, not just “any certificate from a trusted CA.” For HTTPS/TLS servers, verify the hostname in SAN per endpoint identification rules; for mTLS clients, map certificate identity to an authorized account/service.
4. **Check intended purpose/role and key policies**: KeyUsage, ExtendedKeyUsage (EKU), service name, tenant or namespace, certificate policies, and organizational constraints. A certificate authorized for TLS server authentication does **not automatically** have authority to sign product updates or invoices.
5. **Account for validity and revocation**: `notBefore`/`notAfter`, CRL/OCSP, or another revocation mechanism per required trust configuration. Do not assume calling `CertPathValidator.validate(...)` always handles revocation properly in every environment; policy/provider settings and data sources affect this step.
6. **Verify the message signature using the end-entity certificate's public key**, with the matching scheme and input bytes, after confirming the key fits identity/usage. Only succeeding here combines a **valid signature** with a **policy-accepted identity**.

**Frequently missed point:** PKIX path validation **does not automatically ensure hostname or subject identity matches your target entity**. Path validation proves a trust structure passes checks; checking the subject name is an **application-context** decision. A valid certificate for `service-b.example` cannot stand in for `service-a.example` just because the same CA issued both.

For HTTPS, use TLS/JSSE configured with proper certificate chain validation **and endpoint identification**; avoid writing custom trust managers that accept all certificates. In Java, merely importing a certificate into a `KeyStore` without identity/authorization checks suited to your use case is likewise insufficient.

### Self-signed does not inherently mean trusted or untrusted

A self-signed certificate can be **intentionally trusted** when its public key/fingerprint is securely installed as a trust anchor in a scoped system. Conversely, an attacker-sent self-signed certificate passes `cert.verify(cert.getPublicKey())`, since they possess both their private key and certificate. **The difference is the approved distribution source / trust anchor**, not the bare label self-signed vs. CA-signed.

## 6. `Signature` in Java does not check a trust store

Core steps when verifying an Ed25519/RSA/ECDSA signature with JCA look similar:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(candidatePublicKey);
verifier.update(exactMessageBytes);
boolean cryptographicallyValid = verifier.verify(signatureBytes);
```

This is an **illustrative snippet**, not a standalone program: it requires `import java.security.Signature;`, appropriate `candidatePublicKey`/`exactMessageBytes`/`signatureBytes`, and checked exception handling. There are no parameters for “Alice,” “right tenant,” or “trusted domain” in this API.

Notes:

- `Signature.initVerify(PublicKey)` checks certain **key-type and provider** constraints, not identity. `Signature.initVerify(Certificate)` **does not replace** PKIX/path/identity validation either; the API may enforce certain KeyUsage limits, yet does not make an untrusted certificate trusted.
- `Signature.verify(...)` may return `false` or throw `SignatureException` on signature/format issues depending on algorithm/provider. Never equate every error with “company X committed fraud”; treat the input as invalid and report errors safely.
- `RSA-PSS` must align hash, MGF1, salt length, and parameters. `ECDSA` requires the right curve and signature format (e.g., DER or IEEE P1363 per protocol). `Ed25519` is a specific signature scheme; never choose an algorithm solely by signature length or an attacker-proposed field.
- `KeyFactory.getInstance("Ed25519").generatePublic(new X509EncodedKeySpec(bytes))` only checks/decodes **key data**, not where that data came from.
- `getInstance` succeeding only shows the provider has the engine; it has nothing to do with the application's trusted key/identity list.

If using `X509EncodedKeySpec` or a certificate public key loaded from a file/HTTP response, the first question must still be: **where did that file/HTTP response come from, and was it authenticated?**

## 7. Proper verification order for a digitally signed message

Below is a conceptual flow for a **message transmitted with a signature**. Field names are merely examples, not a production protocol format to copy verbatim:

```text
Input:
  claimedIssuer, keyId, algorithm, payload, signature, context
       |
       v
[Validate size limits, encoding, schema, version]
       |
       v
[Determine expectedIssuer/expectedRole from trusted context]
       |
       v
[Look up trusted key registry / validate certificate path + identity]
       |
       +-- untrusted key/wrong role/wrong issuer --> REJECT
       |
       v
[Allow only policy-specified algorithm/params]
       |
       v
[Canonicalize/match exact signed bytes + context]
       |
       v
[Signature.verify using accepted public key]
       |
       +-- false/exception ------------------------> REJECT
       |
       v
[Check expiry, nonce/replay, audience, action authorization]
       |
       +-- policy failed --------------------------> REJECT
       |
       v
                 ACCEPT
```

Steps may be implemented in varying technical order for performance or minimizing exposed info, yet the **ACCEPT decision must depend fully on trust binding, cryptographic verification, and policy**. Never execute side effects before mandatory conditions pass.

### Where must expected identity come from?

For instance, a service accepting updates only from publisher A: `expectedIssuer="publisher-A"` must come from **approved configuration/policy** or an independent authenticated context, **never copied blindly from a `sender` claim and trusted immediately**.

If a system supports multiple publishers, a registry might map:

```text
publisher-A / signing-v3  -> trusted public key A, allowed for product X
publisher-B / signing-v7  -> trusted public key B, allowed for product Y
```

When a request carries `keyId=signing-v7`, the server uses it only to look up in the **trusted registry** and confirms the claimed issuer/purpose matches the record. The server never accepts an arbitrary URL from the request to download a new key and treat it as publisher A's key. During key rotation, apply authenticated governance processes, overlap windows, and clear revocation.

### A key does not automatically grant permissions

A signer might genuinely be a trusted service yet be authorized only to **submit reports**, not to **approve money transfers**. A valid signature establishes origin per key binding; authorization must be enforced independently based on action, resource, tenant, amount, scope, or role.

## 8. With JWT/JWS and key metadata: similar pitfalls

Protocols such as JSON Web Signature (JWS) or JSON Web Token (JWT) commonly carry `alg`, `kid`, `iss`, `aud`, and a signature. This is a prime use case for **“signature passes yet identity is invalid”**:

- `kid` is only a **key selection hint**; it does not prove the key belongs to the right issuer. Only look up keys inside the **trusted configured issuer's key set**.
- `alg` sits inside sender-controlled data; implementations must enforce an **algorithm allowlist** and bind the algorithm to the key type/policy. Never let a token force switching to an insecure algorithm, disabling signatures, misusing a shared secret, or causing algorithm confusion.
- `jku`/`x5u` or JWKS addresses inside a token **must never** serve as arbitrary URLs to download and trust keys. If using JWKS, fetch from the configured trusted issuer's endpoint protected by configuration, TLS validation, redirect/address restrictions, and proper caching/rotation.
- After the signature validates, you must still verify **issuer (`iss`)**, **audience (`aud`)**, timestamps (`exp`, `nbf`), subject/tenant, scope, and system policies. A token validly signed by **issuer B** must never automatically be accepted as a token from **issuer A**.
- JSON canonicalization, detached payloads, and base64url encoding can affect signed bytes. Use a vetted JOSE/JWT library rather than manually assembling/parsing JWS via string concatenation.

A small example: a server is configured to accept tokens from issuer `https://id.example.org`, yet a client sends a valid token signed by a key issued by another issuer. If the server queries JWKS unrestricted by issuer based on client hints, the token can yield `verify == true`; even so, **the application must still reject it** because issuer/key binding fails.

## 9. A valid signature still does not protect every context

### 9.1 Replay

As seen in the program: `verify` on the same repeated message and signature remains `true`. If a signed payment order is re-sent, the signature algorithm does not know it is an old transaction.

To prevent replay where needed, the protocol must place **transaction ID, sequence number, timestamp, nonce, or expiration** inside the **signed bytes**, then enforce used-state/time-window checks at the receiver. Adding a timestamp to the payload without including it in the signed bytes creates no security binding.

### 9.2 Cross-protocol / cross-tenant

A signature on “approve 100” can be misused elsewhere if recipient, system, tenant, or purpose bindings are missing. Protocols should sign messages with explicit **domain separation**, such as including version, action type, audience, tenant, canonical resource ID, and all critical fields.

Do not reuse one key across unrelated protocols assuming a signature from protocol A cannot be replayed in protocol B. Separate keys by purpose or bind purpose strictly inside the signed data with explicit verification rules.

### 9.3 Data that “looks the same” does not mean identical bytes

`Signature.update(byte[])` operates on **bytes**, with no understanding of text/JSON. Strings with different UTF-8, `\n`/`\r\n` newlines, BOMs, JSON field ordering, Unicode normalization, or spacing yield different signed messages. When one side signs raw bytes while the other verifies re-serialized JSON, verification can fail even though “the content” looks identical.

When signing structured data, define an **unambiguous** encoding or apply the protocol's canonicalization standard. Guard against parser differentials as well: two programs must not interpret the same validly signed bytes differently.

### 9.4 Compromised keys or compromised signers

A valid signature does not by itself prove the private key remains exclusively in its legitimate owner's possession. If a private key is stolen or a signing service is compromised, an attacker can create valid signatures using the **exact trusted public key**. Detection, revocation, rotation, auditing, HSM/KMS, least-privilege signer permissions, and incident scoping are required. Digital signatures also **do not encrypt content**; observers can still read signed content if sent in plaintext.

## 10. Integrating identity authentication into a Java system

### 10.1 Internal trusted key registry

For a small set of publishers/devices, maintain a managed configuration registry, such as `issuer -> keyId -> publicKey + allowedPurposes + algorithmPolicy`. Key material must be provisioned out-of-band via authenticated channels, trusted installation artifacts, or verified administrative changes. Then:

- Determine the **expected issuer** from policy/context.
- Accept only public keys mapped to that issuer; SPKI fingerprints may be used to detect substitution.
- Call `Signature.verify` only with keys from the registry.
- Check expiration, key rotation, revocation status, and authorization.
- Write audit logs capturing key ID, chosen issuer, version, and result; never log private keys or unnecessary sensitive data.

If the key registry can be altered by the very request being verified, it is no longer a trusted registry.

### 10.2 PKIX and TLS

Java provides `CertificateFactory`, `CertPathValidator`/`CertPathBuilder`, `PKIXParameters`, `TrustAnchor`, and `KeyStore`. For TLS, prefer JSSE/`SSLContext` with a properly configured trust manager and **endpoint identification**; for mTLS, map the client's certificate identity to the right account and role after validating the chain.

To avoid misunderstandings, the snippet below only illustrates **instantiating the engine**, not performing full validation:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
// Requires CertPath/PKIXParameters/trusted anchors prepared reliably
// and checks for identity, purpose, and status per use case.
```

Never assume calling `validator.validate(...)` with any client-supplied trust anchor is meaningful. What matters most is **application-selected trust anchors**, combined with use-case-appropriate policies. Hostname/SAN verification is not included by default when calling `Signature.verify(...)` or `CertPathValidator.validate(...)` directly.

### 10.3 Safe error handling

- `Signature.verify == false`: invalid signature for the chosen key/message; reject.
- `SignatureException`/`InvalidKeyException`/`NoSuchAlgorithmException`: inspect format/algorithm/provider/key policy; reject invalid input or address configuration errors. Never “try every arbitrary key until one returns true” and accept a request-claimed identity.
- `CertificateException`, `CertPathValidatorException`: review trust path/constraints; never disable chain validation just to “make it work.”
- Public error messages should avoid leaking excessive detail about key states, certificates, or internal systems unnecessarily. Internal logs should record correlation ID, key ID, **trust** step outcome, **signature** step outcome, and authorization reason with controlled data.

## 11. Decision table once verify succeeds

| Scenario | `verify` | Trust binding | Policy/freshness | Accept? |
| --- | --- | --- | --- | --- |
| Alice signs; Alice's key is provisioned and right purpose; valid request | `true` | Passed | Passed | **Yes** |
| Mallory signs with her own private key and sends her chosen public key | `true` for Mallory's key | **Failed** | Irrelevant | **No** |
| Alice signs, yet verifier uses Bob's key | `false` | Even if Bob is trusted, wrong entity | Irrelevant | **No** |
| File signed by trusted publisher, yet signature altered | `false` | Passed | Irrelevant | **No** |
| Valid signature, yet request expired / duplicate nonce | `true` | Passed | **Failed** | **No** |
| Valid certificate chain, yet wrong hostname/scope | Can be `true` | **Wrong expected identity** | Irrelevant | **No** |
| Right key and message, yet signer only has read role and request asks to delete | `true` | Passed | **Unauthorized** | **No** |
| Trusted key was revoked after an incident | Can be `true` | Current trust policy rejects key | Irrelevant | **No** |

**Mental model to remember:** `valid signature != trusted signer != authorized operation`. The verify step is **one necessary condition in many systems**, not a sufficient condition for an acceptance decision.

## 12. Pre-production checklist for digital signatures

- [ ] Expected identity/issuer is determined from configuration or an independent authenticated context, **never blindly trusting a sender claim**.
- [ ] Public key comes from a trust store/PKIX/pin provisioned over a trusted channel; never take an arbitrary key from the payload and accept it.
- [ ] Every key has a `keyId`, issuer, purpose, allowed algorithms, rotation/revocation policy, and tenant boundary.
- [ ] If using certificates: validate path to trust anchor, validity, constraints, purpose, SAN/endpoint identity, and revocation per policy.
- [ ] `Signature.verify` uses the matching scheme/parameters, right public key, and **exact signed byte sequence**.
- [ ] If data uses structured formatting, encoding/canonicalization follows protocol rules and is tested bidirectionally.
- [ ] Claims such as audience, expiration, nonce/sequence, signed context, and action permissions are checked **outside** the signature.
- [ ] Token `alg`/`kid` fields are used strictly within an allowlist/trusted key namespace; never fetch keys from arbitrary URLs.
- [ ] No side effects execute before trust + verify + policy all complete.
- [ ] Tests cover valid signature, tampered signature, tampered message, swapped key, wrong issuer, replay, revoked key, and unauthorized action.

## 13. Practice exercises

1. Explain why the line `Attacker signature with attacker key verifies: true` in `SignatureIdentityDemo` is not a flaw in Ed25519.
2. Remove the pin check from `verifyWithPinnedKey`. What happens if a request supplies both `attackerFromSpki` and `attackerSignature`? Does editing the code “create a vulnerability” or merely expose an existing trust-binding flaw?
3. If an X.509/SPKI public key is downloaded from an Internet URL, what additional evidence is required to trust it belongs to the right publisher? Is a SHA-256 hash served from that very same URL sufficient?
4. A self-signed certificate can pass `cert.verify(cert.getPublicKey())`; explain why this does not prove it is trusted by the company.
5. Describe the mandatory steps to authenticate a TLS server: from trust anchors, chain, validity/purpose to **hostname SAN**. Which steps are outside `Signature.verify`?
6. Design a software update system using key rotation. If an old `keyId` is revoked after compromise, how must the application handle files whose signatures are still mathematically valid?
7. Design a signed transfer request with tenant, amount, payee, unique transaction ID, timestamp, and audience; specify which fields belong inside the signed bytes, and where replay/authorization checks run.
8. In multi-tenant JWTs, why is a valid signature against issuer B's JWKS **not enough** to accept a token as issuer A? Propose a registry mapping issuer → allowlisted JWKS keys and algorithm policy.

## References

- [Java SE 17 — `Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `initVerify`, `update`, `verify`, and exceptions, including the `Certificate` overload.
- [Java SE 17 — `KeyFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html): parsing keys via `X509EncodedKeySpec` (format decoding only, no identity authentication).
- [Java SE 17 — `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): SubjectPublicKeyInfo format for public keys.
- [Java SE 17 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html), [`PKIXParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): validating certification paths to application-selected trust anchors.
- [Java SE 17 — `X509Certificate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): SAN, KeyUsage, EKU, validity, and certificate signature.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): PKIX path validation and certificate constraints.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): Ed25519 algorithm.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515) and [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `alg`, `kid`, `iss`, `aud`, and token verification.
