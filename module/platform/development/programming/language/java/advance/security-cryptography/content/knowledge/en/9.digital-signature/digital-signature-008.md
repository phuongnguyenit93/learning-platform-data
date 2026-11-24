# 9.8 Distinguishing Invalid Signatures, Malformed Data, and Verification Exceptions

When verifying digital signatures in Java, **“invalid signature,”** **“malformed input data,”** and **“an exception thrown during verification”** are distinct situations. They may lead to the same business decision—**rejecting the request**—but they differ in root cause, failure layer, handling, recoverability, and what needs to be logged for operations.

The core point: `java.security.Signature.verify(byte[])` has two outcomes under the API contract: **`true`/`false`** when the verification check completes, or **`SignatureException`** when the engine cannot verify normally (e.g., invalid state, wrong signature encoding/type, or unprocessable input for the provider). Prior to `verify`, there are also parsing, Base64 decoding, public-key loading, and algorithm-selection layers, each with its own exceptions.

This lesson helps you classify errors at the right layer, write safe handling branches, and verify the behavior with Java 17+.

## 1. Ask the right question: did execution even reach cryptographic verification?

Receiving and checking an external signature typically spans multiple steps:

~~~text
External payload / request
  |
  v
[1] Validate request schema, size limits, required fields
  |  error -> MALFORMED_INPUT (has not reached Signature)
  v
[2] Decode Base64/Base64URL/hex/PEM per contract
  |  error -> MALFORMED_ENCODING (has not reached Signature)
  v
[3] Load public key in expected format, check trusted source
  |  parse error -> INVALID_KEY_FORMAT
  |  trust/certificate error -> TRUST_FAILURE
  v
[4] Select algorithm + parameters and call Signature.getInstance(...)
  |  error -> ALGORITHM_OR_CONFIGURATION_ERROR
  v
[5] Signature.initVerify(trustedPublicKey)
  |  error -> INVALID_KEY_OR_PROVIDER_ERROR
  v
[6] Signature.update(EXACT_MESSAGE_BYTES)
  |  state/processing error -> SignatureException
  v
[7] Signature.verify(signatureBytes)
  |
  +-- true  -> VALID_CRYPTOGRAPHIC_SIGNATURE
  +-- false -> NOT_VERIFIED
  +-- SignatureException -> VERIFICATION_PROCESSING_ERROR
                               (may relate to signature format)
~~~

**There is no guarantee that every malformed signature is caught before `verify`.** Some formats are only decoded by the provider inside `verify`. Depending on the scheme/provider, abnormal inputs can return `false` or throw `SignatureException`. To reliably distinguish format errors from cryptographic mismatches, establish an **explicit encoding contract and perform safe structural checks before calling verify**.

Conversely, `verify(...) == true` only proves that the **mathematical signature matches the message bytes, public key, and parameters used**. It does not by itself prove the public key belongs to the expected user, the certificate is still valid, or the request has not been replayed.

## 2. Classifying the three main outcome categories

| Category | Examples | Typical API outcome | Exact meaning |
| --- | --- | --- | --- |
| **Non-matching signature** | Tampered content, signed with someone else's private key, swapped structurally valid signature | `Signature.verify(sig) == false` | Verification under the **current message/key/algorithm/parameters** did not succeed. |
| **Malformed input** | Corrupt Base64, invalid JSON/PEM, corrupt DER public key, wrong signature representation | `IllegalArgumentException` from Base64, `InvalidKeySpecException` from `KeyFactory`, or `false`/**`SignatureException`** from `Signature` | Pinpoint the **parse/format layer** where failure happened; never lump everything into `verify == false`. |
| **Exception during verification** | Incompatible key, engine missing `initVerify`, missing algorithm/provider, bad parameters, provider failure | `InvalidKeyException`, `SignatureException`, `NoSuchAlgorithmException`, `InvalidAlgorithmParameterException`... | Could be a configuration, input, state, or provider error; classify by **API and context**, not exception class name alone. |

**Key point:** this classification describes **failure location and operational meaning**. These are not three mutually exclusive source-code branches: a malformed signature can be the exact reason `Signature.verify` throws `SignatureException`. An exception **does not automatically** mean an internal system bug; it can equally be a valid response to attacker-supplied input.

### Diagnostic questions

1. Did the request parse cleanly and pass size limits?
2. Is the signature string in the protocol's agreed encoding?
3. Does the public key have the right format, key type, and **trusted source**?
4. Was the engine initialized with `initVerify` and updated with the exact signed bytes?
5. Given input passing the layers above, did `verify` return **`false`** or throw which **exception**, on which line?

## 3. `Signature.verify`: `true`, `false`, and `SignatureException`

Standard verification lifecycle:

~~~java
Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(trustedPublicKey);
verifier.update(messageBytes);
boolean accepted = verifier.verify(signatureBytes);
~~~

This is an **API illustration snippet**, not standalone; the full example is in section 5.

- **`true`:** the signature matches the **exact bytes** passed via `update`, under the selected algorithm and public key.
- **`false`:** the signature did not verify. Wrong message, a different public key of the **same type**, an altered signature, or mismatched scheme/parameters can produce `false`.
- **`SignatureException`:** the engine encountered an error while processing. The API notes possibilities such as an uninitialized engine, invalid signature encoding/type, or inability to process the input. You must reject the request while recording a normalized error server-side.

Do not treat every `SignatureException` as a JVM failure; equally, **do not claim an input is structurally valid just because `verify` returned `false`**. Providers may behave differently at malformed-data boundaries.

For example, 2048-bit RSA produces a **256-byte** signature for standard schemes. If 255 bytes arrive, one provider might throw `SignatureException` for wrong length; do not extrapolate from one provider throwing an exception that all providers will do so. A validation layer can enforce length against the RSA public key, while still letting `Signature` perform cryptographic verification.

### Must verify byte-for-byte on the same message

~~~text
Sign:   bytes("amount=100", UTF-8) -> signature
Verify: bytes("amount=100", UTF-8) -> true (if key/scheme match)
Verify: bytes("amount=900", UTF-8) -> false
Verify: bytes("amount=100\n", UTF-8) -> false
~~~

Digital signatures operate on **bytes**, not on the “logical meaning” of a string. The following changes cause mismatches even when the screen rendering looks identical:

- JSON changes field ordering, whitespace, numeric formatting, or escaping.
- LF vs. CRLF, UTF-8 vs. another encoding.
- Visually identical Unicode sequences with different byte representations.
- Compressed/decompressed data, URL-encoding, or altered headers within the signed payload.
- Verifying the **raw payload** when the signer signed a hash/canonical form, or vice versa.

If the protocol requires canonicalization, both parties must run the **exact same canonicalization rule**. Never arbitrarily `trim()`, sort JSON, or normalize Unicode during verification unless specified by protocol: doing so alters the signed data and causes `false` or hard-to-control semantic discrepancies.

## 4. Validating input formats before cryptography

### 4.1. Base64 and Base64URL errors

Protocols commonly send signatures over JSON/HTTP as text. You must pick **one agreed encoding**:

~~~java
// Standard Base64 with '+' and '/':
byte[] sigBytes = Base64.getDecoder().decode(signatureText);

// Base64URL with '-' and '_':
byte[] sigUrlBytes = Base64.getUrlDecoder().decode(signatureText);
~~~

These two lines are **mutually exclusive choices**, not calls to invoke together. If the text contains invalid characters, the decoder may throw `IllegalArgumentException`. This is a **pre-verification input encoding error**, not `SignatureException`.

Do not default to `Base64.getMimeDecoder()` for every API because the MIME decoder silently ignores certain out-of-alphabet characters; when a protocol mandates strict encoding, use the strict decoder and enforce size and structural bounds before parsing. Base64 string length alone never proves cryptographic validity.

### 4.2. Public key format vs. certificate format

An RSA public key exported as DER **SubjectPublicKeyInfo** (SPKI) can be loaded with:

~~~java
byte[] spkiBytes = ...; // Valid DER bytes supplied by a trusted source.
PublicKey publicKey = KeyFactory.getInstance("RSA")
        .generatePublic(new X509EncodedKeySpec(spkiBytes));
~~~

This is only an illustrative fragment. The name `X509EncodedKeySpec` often confuses people: it represents an **SPKI public key**, **not a complete X.509 certificate**. For an X.509 certificate, use `CertificateFactory.getInstance("X.509")` to parse the certificate structure, then call `getPublicKey()` and **validate the trust chain, validity, certificate policies, and revocation** via the appropriate mechanism.

If `spkiBytes` has an invalid encoding/algorithm, `KeyFactory.generatePublic` may throw **`InvalidKeySpecException`**. Meanwhile, a corrupt certificate can throw **`CertificateException`** from the certificate parser. Do not label these errors “invalid signature” when `Signature.verify` has not even run.

### 4.3. Binary signatures also have formats

Not every signature is an arbitrary-length byte array:

| Signature scheme | Common representation via Java JCA | Parsing/verification consequences |
| --- | --- | --- |
| `SHA256withRSA` (PKCS#1 v1.5) | Block-sized RSA signature **equal in length to modulus** (e.g., 256 bytes for RSA-2048) | Unusually short/long signatures may be rejected with `SignatureException` or fail verification depending on implementation. |
| `RSASSA-PSS` | RSA signature also sized by modulus; requires matching **hash, MGF, saltLength, trailerField** | Parameter mismatch with the signer causes verification failure or config errors. |
| `SHA256withECDSA` | Usually ASN.1 **DER SEQUENCE of two INTEGERs `r` and `s`** | Corrupt DER signatures may trigger `SignatureException`; DER length is **not always fixed**. |
| `SHA256withECDSAinP1363Format` | IEEE P1363 representation: fixed-width **`r \|\| s`** bytes | For P-256, typically 64 bytes; **not byte-for-byte compatible** with default DER. |
| `Ed25519` | Standard Ed25519 signature of **64 bytes** | Matching length does not prove validity; only `verify` proves it. |

Note that the Java algorithm name must match the **signature representation**. For instance, calling `SHA256withECDSA` on a 64-byte `r||s` signature from another library typically fails unless properly converted, or unless the provider-supported `...inP1363Format` algorithm is used. Never slice or pad bytes arbitrarily to “make the length fit.”

For RSA signatures, **leading zero bytes** must be preserved if present: round-tripping through `BigInteger` and re-serializing carelessly can strip leading zeros or insert a sign byte, breaking the input length.

## 5. Java 17+: distinguishing valid signature, tampered message, wrong key, and truncated signature

The file **`SignatureOutcomesDemo.java`** generates a 2048-bit RSA key pair for learning, signs `"amount=100"`, and verifies multiple cases. In the example, **`SHA256withRSA`** is the RSA PKCS#1 v1.5 scheme for observing the API; for new RSA signature designs, consider RSASSA-PSS if permitted by protocol and specify full parameters.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;

public class SignatureOutcomesDemo {
    static boolean check(
            PublicKey key, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        KeyPair other = generator.generateKeyPair();

        byte[] data = "amount=100".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(data);
        byte[] signed = signer.sign();

        System.out.println("Correct signature: " +
                check(pair.getPublic(), data, signed));

        System.out.println("Changed data: " +
                check(pair.getPublic(),
                        "amount=900".getBytes(StandardCharsets.UTF_8),
                        signed));

        System.out.println("Other RSA key: " +
                check(other.getPublic(), data, signed));

        byte[] truncated = Arrays.copyOf(signed, signed.length - 1);
        boolean rejected;
        try {
            rejected = !check(pair.getPublic(), data, truncated);
        } catch (SignatureException expected) {
            rejected = true;
        }
        System.out.println("Truncated signature rejected: " + rejected);
    }
}
~~~

Run with Java 17+:

~~~bash
javac SignatureOutcomesDemo.java
java SignatureOutcomesDemo
~~~

Stdout:

~~~text
Correct signature: true
Changed data: false
Other RSA key: false
Truncated signature rejected: true
~~~

Analysis:
1. Matching **message bytes + public key + scheme + signature** → `true`.
2. Changing content to `amount=900` while keeping the old signature → `false` (signature does not attest to the new message).
3. Using another RSA public key—still the right **key type** → normally `false` because it does not match the signing private key.
4. Dropping one byte from the RSA signature → **rejected**. The example accepts **either way a provider may reject**: `verify` returning `false` or throwing `SignatureException`. The final stdout line asserts **rejection**, rather than locking to one exception behavior across all JVMs.

In the example above, catching `SignatureException` merely demonstrates the **intentionally truncated** test signature; a real service should not swallow all exceptions into `return false` and lose visibility into provider or programming bugs. The service layer should record the internal cause category while returning a normalized rejection externally.

## 6. Java 17+: exceptions before and during `verify`

The file **`VerificationErrorsDemo.java`** deliberately triggers failures at successive layers. The malformed bytes in the demo are **purely for parser testing**, not valid keys or signatures.

~~~java
import java.security.*;
import java.security.spec.*;
import java.util.Base64;

public class VerificationErrorsDemo {
    public static void main(String[] args) throws Exception {
        try {
            Base64.getDecoder().decode("not_base64!!!");
            throw new AssertionError("Base64 should have failed");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid Base64: IllegalArgumentException");
        }

        try {
            KeyFactory.getInstance("RSA").generatePublic(
                    new X509EncodedKeySpec(new byte[] {0x30, 0x00}));
            throw new AssertionError("Invalid key was accepted");
        } catch (InvalidKeySpecException expected) {
            System.out.println("Invalid public key DER: InvalidKeySpecException");
        }

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"));
        PublicKey ecKey = ec.generateKeyPair().getPublic();

        try {
            Signature.getInstance("SHA256withRSA").initVerify(ecKey);
            throw new AssertionError("EC key was accepted for RSA");
        } catch (InvalidKeyException expected) {
            System.out.println("Wrong key type: InvalidKeyException");
        }

        try {
            Signature uninitialized = Signature.getInstance("SHA256withRSA");
            uninitialized.verify(new byte[256]);
            throw new AssertionError("Uninitialized verifier was accepted");
        } catch (SignatureException expected) {
            System.out.println("Uninitialized verifier: SignatureException");
        }

        try {
            Signature.getInstance("NotARealSignatureAlgorithm");
            throw new AssertionError("Unsupported algorithm was accepted");
        } catch (NoSuchAlgorithmException expected) {
            System.out.println("Unknown algorithm: NoSuchAlgorithmException");
        }
    }
}
~~~

~~~bash
javac VerificationErrorsDemo.java
java VerificationErrorsDemo
~~~

Stdout on a JDK supporting standard RSA and EC P-256 algorithms:

~~~text
Invalid Base64: IllegalArgumentException
Invalid public key DER: InvalidKeySpecException
Wrong key type: InvalidKeyException
Uninitialized verifier: SignatureException
Unknown algorithm: NoSuchAlgorithmException
~~~

**Differences across lines:**

- `IllegalArgumentException` in `Base64.decode`: transport input has invalid syntax; **no `Signature` engine was ever created**.
- `InvalidKeySpecException` in `KeyFactory.generatePublic`: public key DER bytes could not be decoded into a valid key; not `verify == false`.
- `InvalidKeyException` in `initVerify`: an EC public key is incompatible with `SHA256withRSA`. If a different but valid RSA public key were supplied, `initVerify` would succeed and `verify` would return `false`.
- `SignatureException` in `verify` before `initVerify`: **application API lifecycle bug**, distinct from a normal cryptographic signature mismatch.
- `NoSuchAlgorithmException` in `Signature.getInstance`: fake algorithm name does not exist; this is an engine/configuration selection error, not a verification outcome.

Never depend on exact provider exception *message strings*; logs can vary across JDKs. The demo prints only **known exception class names**, avoiding coupling to implementation-specific text.

## 7. Error mapping table across Java APIs

| Stage/API | Exception/result | Meaning | Handling guidance |
| --- | --- | --- | --- |
| Parse JSON/HTTP/request schema | Parser library exception; validation error | Request missing fields, wrong types, bad encoding/size | Return input error; do not pass invalid content down to JCA. |
| `Base64.Decoder.decode` | `IllegalArgumentException` | Base64 string invalid for chosen decoder | Reject encoding; enforce size bounds against abuse. |
| Reading file/key/cert via stream | `IOException` | File/transport unreadable | Distinguish I/O failures from signature mismatches. |
| `KeyFactory.generatePublic` | `InvalidKeySpecException` | Encoded public key format/algorithm invalid or unsupported | Inspect SPKI/DER, algorithm, and key source. |
| `CertificateFactory.generateCertificate` | `CertificateException` | Certificate failed to parse cleanly | Check cert format, then handle trust chain separately. |
| `Signature.getInstance` | `NoSuchAlgorithmException` | Engine/algorithm not provided | Check allowlist, provider, and environment. |
| `Signature.getInstance(algorithm, name)` | `NoSuchProviderException` | Requested provider name not registered | Check configuration; never silently fall back if policy mandates a provider. |
| `Signature.initVerify(publicKey)` | `InvalidKeyException` | Wrong key type, format, parameters, or incompatible with provider | Check algorithm/key pair/trust, distinguishing wrong-entity keys of the same type. |
| `Signature.setParameter(spec)` | `InvalidAlgorithmParameterException` | Parameters incompatible with scheme/provider | Check PSS hash/MGF/saltLength and protocol requirements. |
| `Signature.update(data)` | `SignatureException` | Wrong engine state or unprocessable input | Check lifecycle, provider, input stream, and state. |
| `Signature.verify(signatureBytes)` | **`true`** | Cryptographic check passed | Accept only after verifying trusted key, policy, and context. |
| `Signature.verify(signatureBytes)` | **`false`** | Signature failed verification for current input | Reject; never assume “format is valid.” |
| `Signature.verify(signatureBytes)` | `SignatureException` | Engine could not process/verify; possibly state or signature encoding/type | Reject; diagnose carefully as cause is provider-dependent. |
| Other runtime/provider APIs | `ProviderException` or unchecked errors | May indicate provider/infrastructure failure | Reject and trigger operational alerts; never downgrade to weak algorithms. |

The listed exceptions are **typical**, not an exhaustive catalog for every library/protocol. For example, a certificate chain may parse cleanly yet be **untrusted** due to expiration, wrong `KeyUsage`, missing chain, revocation, or invalid hostname; those are **trust/policy** failures rather than initial `CertificateException` parse errors.

### `initVerify` with a certificate vs. `CertificateFactory`

`Signature.initVerify(Certificate)` is an overload that extracts the public key from a certificate; for X.509 certificates, the API may check `KeyUsage` constraints related to digital signatures. However, **it does not replace** PKIX path validation, trusted-anchor checks, or protocol constraints. Always validate trust **before** treating `verify == true` as proof of identity.

## 8. RSASSA-PSS: mismatched parameters can look like a wrong signature

RSA signing schemes cannot be treated as equivalent merely because both use RSA public/private keys:

- `SHA256withRSA` typically refers to RSASSA-PKCS1-v1_5 with SHA-256.
- `RSASSA-PSS` is the RSA-PSS scheme requiring explicit **digest**, **MGF**, **salt length**, and **trailer field**.
- Both sides must agree on the exact algorithm + parameters; otherwise `false` or an initialization/processing error occurs depending on the mismatch and provider.

### Java 17+ example: PSS signing/verifying with matching parameters

File **`PssParameterDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;

public class PssParameterDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        PSSParameterSpec parameters = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
        byte[] data = "contract=v1".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(parameters);
        signer.initSign(pair.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(parameters);
        verifier.initVerify(pair.getPublic());
        verifier.update(data);
        System.out.println("PSS with matching parameters: " +
                verifier.verify(signature));
    }
}
~~~

~~~bash
javac PssParameterDemo.java
java PssParameterDemo
~~~

Stdout:

~~~text
PSS with matching parameters: true
~~~

The example configures **SHA-256**, `MGF1(SHA-256)`, **32-byte salt length**, and **trailerField 1**. These are **PSS signature** parameters, not password salts. Choose parameters according to protocol requirements, not simply because a demo succeeds.

If the verifier uses a different `PSSParameterSpec` than the signer, do not assume it will always throw `SignatureException` or always return `false`: it can fail at `setParameter/initVerify` or at `verify` depending on the discrepancy. **The proper operational rule** is enforcing the exact approved scheme/parameters, never arbitrarily falling back between RSA-PSS and PKCS#1 v1.5.

Request inputs like `algorithm` or `saltLength` **must not be trusted and applied directly**: derive them from key policy, protocol version, or a fixed allowlist. This prevents algorithm-confusion/downgrade attacks.

## 9. Should “invalid signature,” “malformed data,” and “server error” be three distinct HTTP responses?

**The external security decision is usually the same:** reject any sensitive operation unless verification succeeds. Internally, however, the system needs **clear classification** for operations rather than swallowing every exception.

A practical handling model:

| Internal status | Detection layer | Action |
| --- | --- | --- |
| `VERIFIED` | `verify` returns `true` | Proceed to check trust, context, expiry, replay, and policy before approval. |
| `NOT_VERIFIED` | `verify` returns `false` | Reject; increment failure counters and monitor anomalous behavior. |
| `MALFORMED_REQUEST` | Parser/schema/size | Reject payload; record format error category without logging sensitive payloads. |
| `MALFORMED_ENCODING` | Base64/PEM/DER/key parse | Reject; internally identify the failing parse layer. |
| `VERIFICATION_EXCEPTION` | `Signature.update/verify` throws `SignatureException` | Reject; persist normalized diagnostics (stage/algorithm/provider/exception class). |
| `SECURITY_CONFIGURATION_ERROR` | Invalid algorithm/provider/key/PSS parameters | Reject; alert on misconfiguration, never auto-downgrade or bypass verification. |
| `UNTRUSTED_KEY_OR_CONTEXT` | PKI/key registry/policy | Reject even when the signature operation itself might return `true`. |

### Protecting privacy and avoiding oracle bugs

Externally, return a generic error such as **“Invalid authentication request”** with an HTTP status fitting API conventions, because you should not expose provider messages, private-key details, internal key IDs, or validation internals for an adversary to probe configurations. Not every failure has to masquerade as HTTP 401: syntactically invalid requests can return 400; infrastructure/configuration errors can return 5xx. The core principle is **rejecting the request** while limiting unnecessary information disclosure.

In internal logs, emit structured fields: `stage`, `outcome`, allowlisted `algorithm`, provider, truncated or hashed public-key identifier, correlation ID, exception type, and byte count after size checks. Never log private keys, tokens, messages holding personal data, or raw signatures in routine logs; avoid exposing unsanitized exception strings in public fields.

Never write code equivalent to:

~~~java
try {
    return verifier.verify(signatureBytes);
} catch (Exception ignored) {
    return true; // extremely dangerous: fail-open
}
~~~

And never **silently** collapse all exceptions into `false` with zero logs/correlation in a service needing diagnostics. Malformed input, provider configuration, and cryptographic mismatches have different causes; even though all lead to rejection, they require distinct operational signals.

## 10. Writing a cleanly layered verification flow

This is **illustrative pseudocode**, not a standalone Java file, since parsers, key registries, schemas, and trust policies are application-specific:

~~~text
1. validateRequestSizeAndSchema(request)
   -> if invalid: MALFORMED_REQUEST

2. algorithmPolicy = resolveApprovedSignatureSuite(request.context)
   -> never accept arbitrary dangerous/blank schemes from request

3. signatureBytes = strictDecode(request.signatureText, contract.encoding)
   -> decode error: MALFORMED_ENCODING

4. trustedPublicKey = trustedKeyRegistry.lookup(request.keyId, context)
   -> missing/untrusted: UNTRUSTED_KEY_OR_CONTEXT
   -> key format error: MALFORMED_KEY_OR_CONFIG

5. validateKnownFormatConstraints(signatureBytes, trustedPublicKey, algorithmPolicy)
   -> if clear violation: MALFORMED_SIGNATURE

6. messageBytes = exactSignedBytes(request, contract)
   -> canonicalization/encoding per protocol, matching signer

7. verifier = Signature.getInstance(algorithmPolicy.algorithm)
   -> if needed: verifier.setParameter(algorithmPolicy.parameters)
   verifier.initVerify(trustedPublicKey)
   verifier.update(messageBytes)
   result = verifier.verify(signatureBytes)

8. result == true:
     still check trust, expiry, context, anti-replay... before ACCEPT
   result == false:
     NOT_VERIFIED -> REJECT
   SignatureException:
     VERIFICATION_EXCEPTION -> REJECT and diagnose safely
   key/algorithm/provider/parameter exception:
     SECURITY_CONFIGURATION_ERROR -> REJECT + ALERT
~~~

**Note on format validation:** only assert properties guaranteed by the **selected format**. Checking RSA signature length equals modulus byte size is sound; ECDSA DER has variable length and must not be forced to 64 bytes. Never write a custom DER/PKCS#1/EdDSA parser “just to be safe” when audited provider/library validation APIs exist.

**Note on using `Signature`:** it is a **stateful** object. For each verification, create a fresh instance or isolate its lifecycle strictly; never share one `Signature` object across threads or invoke `update` after `verify` assuming initial state without understanding reset semantics.

## 11. Case studies: why does “signature invalid” happen for many reasons?

### Case A — Message bytes changed in transit

Client signs UTF-8 bytes of `{"amount":100}`; server re-serializes JSON as `{"amount":100.0}` and verifies. Because the byte sequences differ, `verify` normally returns `false` despite similar business meaning. Fix by defining exact signed bytes (raw bytes, canonical JSON, or structured signing protocol) and testing consistently on both ends.

### Case B — Base64URL decoded with standard Base64

The string contains `-` or `_` from Base64URL, yet the server calls `Base64.getDecoder()`. The standard decoder throws `IllegalArgumentException`; failure happens **before** `Signature`. Fix by locking the encoding in the protocol contract, using the matching decoder, and validating input.

### Case C — ECDSA signed by another system in P1363 while Java expects DER

The signer sends 64 bytes of P-256 `r||s`; Java uses `Signature.getInstance("SHA256withECDSA")`, which expects DER by default. The data is misinterpreted, yielding `false` or `SignatureException` depending on provider. Fix by agreeing on algorithm-format, using `SHA256withECDSAinP1363Format` where supported, or converting representations accurately via a trusted library.

### Case D — Different RSA public key that is still structurally valid

`initVerify(otherRsaPublicKey)` succeeds because it is the right **RSA key type**. Yet the signature does not correspond to it, so `verify` returns `false`. This differs from passing an **EC public key** to an RSA verifier, where `initVerify` normally throws `InvalidKeyException`.

### Case E — Expired certificate whose signature still verifies

A public key extracted from an expired certificate can still pass RSA/ECDSA verification if the matching private key created the signature. **`Signature.verify` does not replace certificate path validation**. Keep “cryptographic signature valid” distinct from “certificate trusted & valid for intended purpose.”

### Case F — RSA-PSS mismatched `saltLength`/MGF

Client uses `RSASSA-PSS` with MGF1/SHA-256 and 32-byte salt; server configures something else. Depending on provider and failure point, the call may return false or throw an exception. Fix by synchronizing parameters per protocol (as in section 8), without guessing and retrying unapproved configurations.

### Case G — Key rotated without updating key ID

The signature matches the old public key; the server uses the new public key because it ignored an authenticated `kid` version or mishandled key rotation. A `false` result does not prove malicious forgery by the client. Manage key IDs, trust bindings, rotation, and overlap windows properly.

## 12. Essential test matrix

| Test | Input | Expected layered outcome |
| --- | --- | --- |
| Happy path | Valid signature, public key, message, scheme/params | `verify == true`; then check context/trust. |
| Flip one message byte | Keep old signature, alter message | `verify == false`. |
| Swap RSA key of same type | Use key from another pair | `verify == false`. |
| Truncate RSA signature by 1 byte | Truncated signature bytes | Rejected; `verify == false` or `SignatureException` depending on provider. |
| Corrupt Base64 | Characters outside allowed alphabet | `IllegalArgumentException` in decoder; `verify` never called. |
| Corrupt DER public key | Bytes not valid SPKI | `InvalidKeySpecException` when loading key. |
| EC key in RSA verifier | `initVerify(ecPublicKey)` | `InvalidKeyException`. |
| Missing `initVerify` | Call `verify` in uninitialized state | `SignatureException`. |
| Non-existent algorithm name | `Signature.getInstance("NotARealSignatureAlgorithm")` | `NoSuchAlgorithmException`. |
| Matching PSS parameters | Both sides share hash/MGF/salt/trailer | `verify == true`. |
| ECDSA DER/P1363 mismatch | Signer and verifier use different representations | Rejected; may be `false` or `SignatureException`. |
| Untrusted/expired certificate | Signature math still passes | **Rejected by trust/policy** even if `verify` can be `true`. |
| Missing signed metadata | AAD/context/claims invalid per protocol | Rejected at policy/context layer, not inferred from signature. |
| Oversized input | Oversized request or signature | Rejected early, bounded memory/CPU, no unbounded crypto execution. |

Run tests against the **actual production provider**, because malformed-encoding reporting, parameter support, and message behaviors can differ across providers. Never write tests asserting on **English exception message strings**; assert only on exception types, stages, and contract-guaranteed outcomes.

## 13. Common mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| “`verify == false` means Base64/DER was valid” | Some providers return false even for malformed signatures. | Validate checkable formats beforehand; treat false as **not verified**. |
| “Every bad signature always throws `SignatureException`” | There is no uniform guarantee across schemes/providers. | Handle both false and exceptions; do not rely on a single failure mode. |
| “Every `SignatureException` is a hacker's signature” | Could be wrong engine state, provider inability, or internal bug. | Record stage and context; distinguish input issues from infrastructure. |
| “Base64 errors are `SignatureException`” | The decoder runs **before** `Signature`. | Catch `IllegalArgumentException` at the decode layer. |
| “`X509EncodedKeySpec` holds the whole certificate” | It represents an SPKI public key, not a complete certificate. | Use `CertificateFactory` for certificates and PKIX validation for trust. |
| “`verify == true` suffices to authenticate the sender” | Only proves the mathematical relation among message/key/signature. | Verify public-key identity, policy, expiry, and anti-replay. |
| Modifying JSON before verifying | Bytes no longer match what was signed. | Use raw/canonical bytes per protocol. |
| RSA and ECDSA share the same signature encoding | Formats differ; ECDSA has DER and P1363. | Pin algorithm + representation; convert via trusted APIs when needed. |
| Leaving RSA-PSS parameters unpinned | MGF/hash/salt can differ between sides. | Use explicit `PSSParameterSpec` aligned by protocol. |
| Catching `Exception` and returning `true` | **Fail-open**, accepting unverified signatures. | Every error must reject; accept only when checks and policy all succeed. |
| Catching all exceptions with zero logging | Loses evidence distinguishing corrupt payloads from server misconfig. | Classify stage/status and log safely; keep public responses generic. |
| Auto-falling back from strong to weak algorithms | Introduces downgrade/algorithm confusion. | Pick schemes from an allowlist and key policy; fail explicitly on mismatch. |

## 14. Self-check questions

**1.** `Signature.verify` returns `false`. Can you conclude the signature is definitely valid DER?

**Answer:** No. Depending on format/provider, a malformed signature can also yield false; conclude only **not verified**.

**2.** `Base64.getDecoder()` throws `IllegalArgumentException`. Is that an RSA signature mismatch?

**Answer:** No RSA verification occurred yet. This is a **transport encoding** error and must be rejected at the decoding layer.

**3.** When `KeyFactory.generatePublic(new X509EncodedKeySpec(bytes))` throws `InvalidKeySpecException`, should you still attempt `Signature.verify`?

**Answer:** No, there is no valid public key. Fix the key source/format and verify trust; you cannot run verification without a constructed key object.

**4.** Passing a valid EC public key to `SHA256withRSA.initVerify` returns false or throws an exception?

**Answer:** Normally throws **`InvalidKeyException` at `initVerify`** due to wrong key type, not `verify == false`. A valid RSA key from a different pair succeeds at `initVerify` and then yields `verify == false`.

**5.** A 64-byte `r||s` ECDSA signature is sent to Java's default `SHA256withECDSA`. Is it guaranteed to verify?

**Answer:** No. JCA normally expects DER for that name; both sides must align on P1363 vs. DER and the matching scheme name.

**6.** A signature verifies cleanly with a public key from an untrusted self-signed certificate. Should access be granted immediately?

**Answer:** No. You must check chain/trust/policy/identity and business context. `verify == true` is only cryptographic evidence.

**7.** What does `SignatureException` in `verify` when `initVerify` was not called indicate?

**Answer:** The engine object was used in the wrong lifecycle state; fix the program flow rather than blaming the payload.

**8.** Why shouldn't a service return raw JCA exception messages to clients?

**Answer:** They can leak provider names, scheme/key/validation details, and create oracle signals. Return a clean rejection to the client while keeping stage and error codes in internal diagnostic logs.

**9.** Signer and verifier use different `PSSParameterSpec` values with the same RSA public/private key. Is the signature guaranteed to pass?

**Answer:** No. Hash/MGF1/salt length/trailer field must match the protocol; depending on the mismatch, the provider may return false or throw an exception.

## 15. Official references

- [Java SE 17 — `Signature` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — `initVerify`, `update`, `verify`, and exceptions.
- [Java SE 17 — `SignatureSpi` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SignatureSpi.html) — `engineVerify` contract, bad encoding/type, and engine state.
- [Java SE 17 — `KeyFactory` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html) — converting public keys from key specifications.
- [Java SE 17 — `X509EncodedKeySpec` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html) — DER SubjectPublicKeyInfo, not raw certificates.
- [Java SE 17 — `PSSParameterSpec` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html) — RSA-PSS parameter suite.
- [Java 17 Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html) — `Signature`, RSA, ECDSA DER, and `inP1363Format` algorithms.
- [Oracle Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html) — engines, providers, and digital signatures.
