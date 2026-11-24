# 9.5. PSSParameterSpec, Digest, MGF1, and Signature Salt Length

## Learning objectives

In the Java Cryptography Architecture (JCA), `RSASSA-PSS` is an **RSA digital signature** mechanism using probabilistic padding (Probabilistic Signature Scheme) standardized in PKCS #1 (RFC 8017). For two parties to produce and verify compatible signatures, knowing just “RSA” or “SHA-256” is **not enough**: both must agree on the **message digest, MGF function, digest inside MGF1, salt byte length, and trailer field**.

After this lesson, you can:

- Read every field of `java.security.spec.PSSParameterSpec` and distinguish the **message digest** from the **MGF1 digest**.
- Configure an **RSA-PSS SHA-256 / MGF1-SHA256 / 32-byte salt / trailer 1** profile on Java 17+.
- Use `Signature.getInstance("RSASSA-PSS")`, `setParameter(...)`, `initSign/initVerify`, `update`, and `sign/verify` for an exact message byte sequence.
- Compute the salt length limit from the RSA `modulusBits` and digest length; understand why changing the salt length causes verification to fail.
- Diagnose mismatches between Java and OpenSSL/JWS/X.509 or across providers; distinguish RSA-PSS from RSA PKCS#1 v1.5.

The examples use a 2048-bit RSA key generated **in-process solely for learning the API**. In real applications, private keys must be managed securely (KeyStore/KMS/HSM per architecture), signed data sources must use consistent formatting/canonicalization, and public keys must be verified as genuinely trusted.

## 1. How does RSA-PSS work differently from RSA PKCS#1 v1.5 signatures?

Both use an RSA private key to sign and an RSA public key to verify. The difference lies in **how the message is encoded before the RSA operation**:

| Component | RSA PKCS#1 v1.5 (usually `SHA256withRSA` in JCA) | RSASSA-PSS (`RSASSA-PSS` in JCA) |
| --- | --- | --- |
| Signature padding/encoding | EMSA-PKCS1-v1_5 | EMSA-PSS |
| Randomness | For a fixed message/key, the signature under the basic scheme is deterministic | Typically uses a **fresh random salt on each signing call** |
| Parameters to agree on | Hash and scheme, plus key rules | Hash, MGF, MGF digest, salt length, trailer field, and key |
| Compatibility | Cannot verify a PSS signature with a v1.5 verifier | Cannot verify a v1.5 signature with a PSS verifier |
| JCA example | `Signature.getInstance("SHA256withRSA")` | `Signature.getInstance("RSASSA-PSS")` then `setParameter(PSSParameterSpec)` |

The name `SHA256withRSA` is **not** synonymous with `RSA-PSS with SHA-256`. If the signer chooses PSS, the verifier must also choose PSS with matching configuration. Names such as `SHA256withRSAandMGF1` may appear in specific providers/libraries, but you should not rely on such aliases for provider-independent JCA code; choose `RSASSA-PSS` and declare `PSSParameterSpec` explicitly.

**A digital signature is not data encryption:** `Signature.sign()` creates a signature for the supplied input; it **does not** keep the message secret. Successful verification only confirms that the signature matches the public key and message, whereas whether the public key belongs to the right entity/organization is a separate trust-management step (certificates, trust store, pinning, identity policies...).

## 2. The five fields of `PSSParameterSpec`

Full constructor:

```java
PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256",                   // message digest
        "MGF1",                      // mask generation function
        MGF1ParameterSpec.SHA256,    // digest used inside MGF1
        32,                          // salt length in BYTES
        PSSParameterSpec.TRAILER_FIELD_BC
);
```

This is a snippet; you must import `java.security.spec.PSSParameterSpec` and `java.security.spec.MGF1ParameterSpec`.

| Field | Getter API | Meaning | SHA-256 PSS example |
| --- | --- | --- | --- |
| Message digest | `getDigestAlgorithm()` | Hash function used to hash the **message** and inside EMSA-PSS encoding | `"SHA-256"` |
| MGF algorithm | `getMGFAlgorithm()` | Mask generation function, typically **MGF1** | `"MGF1"` |
| MGF parameters | `getMGFParameters()` | For MGF1: an `MGF1ParameterSpec` specifying the digest used inside MGF1 | `MGF1ParameterSpec.SHA256` |
| Salt length | `getSaltLength()` | Number of random **bytes** used for each PSS encoding when signing | `32` bytes |
| Trailer field | `getTrailerField()` | Trailer identifier per PKCS#1; value `1` corresponds to trailer octet `0xBC` | `PSSParameterSpec.TRAILER_FIELD_BC` (value 1) |

**Three common pitfalls to avoid:**

1. `"SHA-256"` and `MGF1ParameterSpec.SHA256` describe **two distinct hash roles**. Although they should match in many modern profiles, the PSS design conceptually does not equate the two fields; the verifier must read **both** accurately.
2. `saltLength=32` means **32 bytes = 256 bits**, not 32 bits. It is also **not** the length of the RSA public/private key and does not determine the RSA signature size.
3. `TRAILER_FIELD_BC` has the constructor value **1**; do not pass `0xBC` (188) as the trailer parameter. The value 1 denotes the trailing padding byte `0xBC` per the scheme definition.

### Warning about default values

`PSSParameterSpec.DEFAULT` is a **historical** profile: message digest `SHA-1`, `MGF1` with `SHA-1`, **20-byte** salt, trailer `1`. The short constructor `new PSSParameterSpec(int saltLen)` also builds on those SHA-1/MGF1-SHA1 defaults, changing only the salt length.

Therefore, **`new PSSParameterSpec(32)` does not automatically become SHA-256-PSS**. In new systems, invoke the five-argument constructor based on your chosen security profile rather than relying on `DEFAULT` or provider-chosen defaults. SHA-1 in the defaults exists only for legacy/API comprehension, not as a recommendation for new signatures.

### `MGF1ParameterSpec` is not `MGF1` itself

`MGF1ParameterSpec.SHA256` is an object carrying the **hash name used to generate the mask**, and does not itself sign or hash data. `MGF1` (Mask Generation Function 1) generates a mask of the required length from a seed via repeated hash invocations with a counter. PSS encoding uses that mask to mask part of the encoded data; the MGF1 digest **does not replace** the message digest that the signer applies to the original message.

## 3. Just enough detail on the EMSA-PSS mechanism

RFC 8017 describes the encoding prior to the RSA operation with `emBits = modBits - 1` and `emLen = ceil(emBits / 8)`. Given message `M`:

```text
M (message bytes)
   |
   v
mHash = Hash(M)                  Hash = message digest (e.g., SHA-256)
   |
   +----------- random salt (sLen bytes)
   |                 |
   v                 v
M' = 0x00 (8 bytes) || mHash || salt
   |
   v
H = Hash(M')                    Same message digest of the PSS profile
   |
   v
dbMask = MGF1(H, targetLength)  MGF1 uses separate digest from MGF1ParameterSpec
   |
   v
maskedDB = DB XOR dbMask
   |
   v
EM = maskedDB || H || 0xBC      encoded message before RSA operation
```

Here `DB` has the form `PS || 0x01 || salt`, where `PS` is a zero-byte padding string of sufficient length; certain high bits of `maskedDB` are cleared according to `emBits`. The RSA operation then converts `EM` into signature bytes. The verifier uses the public key to recover the encoding, recompute/check the mask, extract the salt, and compare the hash.

Meaning of each component:

- **`mHash`:** hash of the **exact bytes the signer received via `Signature.update(...)`**.
- **`salt`:** a byte sequence generated per PSS signing operation, not a password-hashing salt; it can cause two signatures of the same message/key to have **different bytes**. The salt is encoded inside EMSA-PSS and checked by the verifier; there is no need to transmit the salt in a separate field under standard RSASSA-PSS.
- **`MGF1`:** generates a mask from `H`; the mask is not an encryption key or IV.
- **`trailer 0xBC`:** trailing marker of the encoding; Java getters/setters use code `1`.
- **`RSA key`:** the modulus length bounds the total space available for the digest, salt, and overhead bytes.

Do not re-implement EMSA-PSS/MGF1/RSA primitives in application code. Use Java `Signature` and understand the structure only to select parameters, investigate errors, and configure signature formats.

## 4. Why must signer and verifier match the entire profile?

Suppose one side signs with:

```text
algorithm=RSASSA-PSS
messageDigest=SHA-256
MGF=MGF1
mgfDigest=SHA-256
saltLength=32 bytes
trailerField=1
```

The verifier may hold the right public key and message yet still **fail to verify** if it expects `saltLength=20`, MGF1 with SHA-1, message digest SHA-384, or uses scheme `SHA256withRSA`. With a valid key/type/params and a non-matching signature, `Signature.verify` normally returns `false`; if the algorithm, provider, or parameters are unsupported, it may throw an exception before or during verify. Never swallow all failures into a single vague reason.

**Practical recommendation:** define the profile in one clearly named place (e.g., `PSS_SHA256_MGF1_SHA256_SALT32`), use the exact same profile for signer and verifier, and test interoperability across two processes/libraries. When interoperating with an external standard, the profile **must follow that standard** rather than picking an arbitrary salt count.

How to inspect the profile in a Java application:

```java
AlgorithmParameters params = signer.getParameters();
if (params != null) {
    PSSParameterSpec actual =
            params.getParameterSpec(PSSParameterSpec.class);
    System.out.println(actual.getDigestAlgorithm());
    System.out.println(actual.getSaltLength());
}
```

This snippet uses `java.security.AlgorithmParameters` and assumes `signer` is a `Signature` that has called `setParameter`. `Signature.getParameters()` may return `null` if the implementation does not support exporting parameters via this API. Therefore, to guarantee strict protocol configuration, retain the `PSSParameterSpec` instance passed in by code, run actual verification tests, and never infer from `null` what provider defaults were used.

## 5. Java 17: signing and verifying RSASSA-PSS with explicit parameters

Save the following full code into **`RsaPssDemo.java`**. The program generates a 2048-bit RSA key pair (for demo purposes), signs the string `hello PSS` using **two `update` calls**, and then verifies all four cases: matching profile, modified message, different salt length, and different MGF digest.

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class RsaPssDemo {
    private RsaPssDemo() {}

    private static PSSParameterSpec profile(int saltBytes,
            MGF1ParameterSpec mgfDigest) {
        return new PSSParameterSpec("SHA-256", "MGF1", mgfDigest,
                saltBytes, PSSParameterSpec.TRAILER_FIELD_BC);
    }

    private static boolean verify(PublicKey key, PSSParameterSpec spec,
            byte[] message, byte[] signature) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(key);
        verifier.setParameter(spec);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
        gen.initialize(2048);
        KeyPair pair = gen.generateKeyPair();

        PSSParameterSpec spec = profile(32, MGF1ParameterSpec.SHA256);
        byte[] first = "hello ".getBytes(StandardCharsets.UTF_8);
        byte[] second = "PSS".getBytes(StandardCharsets.UTF_8);
        byte[] whole = "hello PSS".getBytes(StandardCharsets.UTF_8);
        byte[] modified = "hello Pss".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.initSign(pair.getPrivate());
        signer.setParameter(spec);
        signer.update(first);
        signer.update(second);
        byte[] signature = signer.sign();

        PSSParameterSpec actual = signer.getParameters()
                .getParameterSpec(PSSParameterSpec.class);

        System.out.println("modulusBits=" +
                ((RSAPublicKey) pair.getPublic()).getModulus().bitLength());
        System.out.println("signatureBytes=" + signature.length);
        System.out.println("digest=" + actual.getDigestAlgorithm());
        System.out.println("mgf=" + actual.getMGFAlgorithm());
        System.out.println("mgfDigest=" +
                ((MGF1ParameterSpec) actual.getMGFParameters())
                        .getDigestAlgorithm());
        System.out.println("saltBytes=" + actual.getSaltLength());
        System.out.println("verified=" + verify(pair.getPublic(), spec,
                whole, signature));
        System.out.println("modifiedMessageAccepted=" +
                verify(pair.getPublic(), spec, modified, signature));
        System.out.println("wrongSaltAccepted=" +
                verify(pair.getPublic(),
                        profile(20, MGF1ParameterSpec.SHA256),
                        whole, signature));
        System.out.println("wrongMgfAccepted=" +
                verify(pair.getPublic(),
                        profile(32, MGF1ParameterSpec.SHA1),
                        whole, signature));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 RsaPssDemo.java
java RsaPssDemo
```

**Stdout on a tested JDK 24/OpenJDK provider** (the mismatching verification cases may be rejected with an exception on another provider when validating parameters rather than returning `false`):

```text
modulusBits=2048
signatureBytes=256
digest=SHA-256
mgf=MGF1
mgfDigest=SHA-256
saltBytes=32
verified=true
modifiedMessageAccepted=false
wrongSaltAccepted=false
wrongMgfAccepted=false
```

Key takeaways:

1. `KeyPairGenerator.getInstance("RSA")` and `initialize(2048)` create a key sufficient for the example, and `Signature.getInstance("RSASSA-PSS")` selects the PSS scheme. Real-world security also depends on policy-compliant key sizes, random sources, private key access control, and key lifecycle.
2. `signer.initSign(privateKey)` sets the private key; `setParameter(spec)` configures digest/MGF/salt/trailer. `update(first)` followed by `update(second)` supplies the exact bytes `hello PSS` without inserting any separator.
3. `signer.sign()` completes signing and generates a random salt per the profile; the signature is **256 bytes** because the RSA modulus is **2048 bits**, **not** because of SHA-256 or `sLen=32`.
4. `verifier.initVerify(publicKey)` + `verifier.setParameter(spec)` + `update(whole)` + `verify(signature)` returns true when message/key/profile match. The signer's two `update` calls and the verifier's single call are equivalent because the **byte sequence** is identical.
5. `modifiedMessageAccepted=false` shows that changing `PSS` to `Pss` alters the message. This operates on UTF-8 bytes, with no automatic “case-insensitive text comparison.”
6. `wrongSaltAccepted=false`: the verifier expects a **20-byte salt** while the signer signed with **32 bytes**.
7. `wrongMgfAccepted=false`: the verifier expects MGF1-SHA1 instead of MGF1-SHA256. Even though the message digest is still SHA-256, the **different MGF digest** prevents a match.
8. `signer.getParameters()` reports the active configuration on the demo provider. The example assumes the provider returns `AlgorithmParameters`; if you get `null` on another provider, retain the `spec` your code supplied and diagnose per that provider's contract.

**Never** store private keys in source code, print private keys for debugging, or accept an arbitrary public key supplied by an untrusted data sender and declare the sender “valid.” The demo generates both keys in-process solely to demonstrate the API flow.

## 6. How do the message digest and MGF1 digest differ?

`PSSParameterSpec.getDigestAlgorithm()` specifies the hash function computing `mHash = Hash(M)` and `H = Hash(0x00... || mHash || salt)`. `MGF1ParameterSpec.getDigestAlgorithm()` specifies the hash used **inside MGF1** to generate the mask from `H`.

| Profile | Message digest | MGF | MGF digest | Salt bytes | Meaning |
| --- | --- | --- | --- | ---: | --- |
| Common SHA-256 PSS | SHA-256 | MGF1 | SHA-256 | 32 | Compatible with the `PS256` profile in JOSE when other rules match. |
| Common SHA-384 PSS | SHA-384 | MGF1 | SHA-384 | 48 | `PS384` profile. |
| Common SHA-512 PSS | SHA-512 | MGF1 | SHA-512 | 64 | `PS512` profile. |
| SHA-256 + MGF1-SHA1 | SHA-256 | MGF1 | SHA-1 | 32 | Expressible structurally in PSS; not the `PS256` profile, and provider support varies. |
| `PSSParameterSpec.DEFAULT` | SHA-1 | MGF1 | SHA-1 | 20 | Legacy defaults; do not implicitly use for new signatures. |

In many modern protocols, the message digest and MGF digest **must be the same hash**; for instance, RFC 7518 defines **JOSE PS256** as SHA-256 for both, `saltLength=32`, standard PSS trailer, and an RSA key of at least 2048 bits. Similarly, `PS384` uses a 48-byte salt and `PS512` uses a 64-byte salt.

**There is no rule that “SHA-256 makes Java automatically pick a 32-byte salt” when you just call `getInstance("RSASSA-PSS")`.** Salt length is an **independent parameter**, and protocol requirements must be declared explicitly. If you must verify a signature using a 20-byte salt with SHA-256, use that profile only when required by a legacy protocol/system and after reviewing acceptance policy.

### Should you call `MessageDigest` yourself before `Signature.update`?

**No**, when using `Signature.getInstance("RSASSA-PSS")` with `PSSParameterSpec("SHA-256",...)`. `Signature.update(message)` takes **message bytes**; the engine computes the hash internally per the profile. If you write:

```java
byte[] prehashed = MessageDigest.getInstance("SHA-256").digest(message);
signer.update(prehashed);
```

then the PSS signer hashes the **32-byte `prehashed` value** as if it were a new message; that signature is **not** a direct signature over the original `message` under standard protocols. The snippet above only illustrates the bug (assuming `message` is a `byte[]`, `signer` is initialized, and exceptions are declared/caught); never use it in a standard flow. Do not “optimize” by prehashing since the PSS engine already includes hashing. Any specialized prehashed API, if offered by a provider/protocol, has its own contract and must not be confused with standard `RSASSA-PSS` `Signature`.

## 7. Salt length is bounded by digest and RSA modulus

RFC 8017, EMSA-PSS encoding specifies:

```text
modBits = bit length of RSA modulus n
emBits  = modBits - 1
emLen   = ceil(emBits / 8)       // bytes of encoded message
hLen    = output bytes of message digest
sLen    = byte length of salt

Basic requirement: emLen >= hLen + sLen + 2
Or: sLen <= emLen - hLen - 2
```

Example with a **2048-bit RSA modulus**:

- `emBits=2047`, `emLen=256 bytes`.
- SHA-256: `hLen=32`, so **maximum sLen = 256 - 32 - 2 = 222 bytes** from an encoding-size standpoint.
- SHA-512: `hLen=64`, maximum sLen is **190 bytes**.
- When `sLen=32` with SHA-256, ample padding room remains and the profile **fits comfortably** in RSA-2048.

**Maximum salt length does not mean it is the right choice.** Protocols typically mandate salt equal to digest length (e.g., `PS256` `sLen=32`); raising it to 222 bytes does not make the signature “6.9x stronger” and can break interoperability. Some providers or RSA-PSS keys impose stricter constraints than the mathematical bound; always test against the real implementation and protocol.

Quick reference table (for RSA keys with the exact listed modulus bits):

| RSA modulus | Message digest | hLen | emLen | Maximum sLen by formula |
| ---: | --- | ---: | ---: | ---: |
| 1024 bits | SHA-256 | 32 bytes | 128 bytes | 94 bytes |
| 2048 bits | SHA-256 | 32 bytes | 256 bytes | 222 bytes |
| 2048 bits | SHA-512 | 64 bytes | 256 bytes | 190 bytes |
| 3072 bits | SHA-256 | 32 bytes | 384 bytes | 350 bytes |
| 4096 bits | SHA-512 | 64 bytes | 512 bytes | 446 bytes |

The RSA-1024 row is solely for the **size math**, **not** a recommendation to use RSA-1024 for new signatures. Use RSA key sizes compliant with current standards and policies.

### Computing the budget in Java instead of guessing

Save **`PssSaltBudgetDemo.java`**:

```java
import java.security.MessageDigest;

public final class PssSaltBudgetDemo {
    private PssSaltBudgetDemo() {}

    private static int maxSaltBytes(int modulusBits, int hashBytes) {
        if (modulusBits < 2 || hashBytes < 0) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
        int emBits = modulusBits - 1;
        int emLen = (emBits + 7) / 8;
        return emLen - hashBytes - 2;
    }

    public static void main(String[] args) throws Exception {
        int sha256Bytes = MessageDigest.getInstance("SHA-256")
                .getDigestLength();
        int sha512Bytes = MessageDigest.getInstance("SHA-512")
                .getDigestLength();

        System.out.println("SHA256Bytes=" + sha256Bytes);
        System.out.println("RSA2048_SHA256_MaxSalt=" +
                maxSaltBytes(2048, sha256Bytes));
        System.out.println("RSA2048_SHA512_MaxSalt=" +
                maxSaltBytes(2048, sha512Bytes));
        System.out.println("RSA3072_SHA256_MaxSalt=" +
                maxSaltBytes(3072, sha256Bytes));
        System.out.println("salt32FitsRSA2048_SHA256=" +
                (32 <= maxSaltBytes(2048, sha256Bytes)));
        System.out.println("salt223FitsRSA2048_SHA256=" +
                (223 <= maxSaltBytes(2048, sha256Bytes)));
    }
}
```

```bash
javac -encoding UTF-8 PssSaltBudgetDemo.java
java PssSaltBudgetDemo
```

**Stdout:**

```text
SHA256Bytes=32
RSA2048_SHA256_MaxSalt=222
RSA2048_SHA512_MaxSalt=190
RSA3072_SHA256_MaxSalt=350
salt32FitsRSA2048_SHA256=true
salt223FitsRSA2048_SHA256=false
```

This program only performs the **RFC encoding-bound calculation**; it does not probe provider support, prove any algorithm policy is accepted, or create signatures. For an existing key, obtain the actual bit length via `((RSAPublicKey) publicKey).getModulus().bitLength()` rather than assuming the key matches a documented config size.

### What happens when salt exceeds the limit?

For RSA-2048/SHA-256, requesting `sLen=223` makes `hLen+sLen+2=257 > emLen=256`. PSS cannot encode the message under those parameters; JCA/the provider may reject it at `setParameter`, `initSign`, or `sign` with an appropriate exception. Do not assume a single exception type across all providers. Always **validate `sLen`** beforehand, choose a sufficiently large key, and use a protocol-compliant profile.

`sLen=0` is permitted structurally by the PSS encoding standard; in that case the salt is empty and randomness from the salt is gone. This is not the default for `PS256`/`PS384`/`PS512`; use it only when an explicit protocol/policy specifies it, never setting it to 0 arbitrarily to obtain byte-comparable signatures.

## 8. Proper `Signature` usage: call order and input bytes

Lifecycle of a signing operation:

```text
Signature.getInstance("RSASSA-PSS")
   |
initSign(privateKey, [SecureRandom])
   |
setParameter(matching profile)
   |
update(messageByteChunk1)
update(messageByteChunk2)
   |
sign() -> signatureBytes
```

Verification lifecycle:

```text
Signature.getInstance("RSASSA-PSS")
   |
initVerify(trustedPublicKey)
   |
setParameter(SAME profile)
   |
update(SAME message bytes in order)
   |
verify(signatureBytes) -> true/false or exception
```

Depending on the provider, `setParameter` may be allowed before `initSign/initVerify` or only after the engine has been initialized with a key; this lesson's example uses **init first, `setParameter` second**, which ran on the tested provider. With an RSA-PSS key that has pre-bound algorithm constraints, the engine may reject a profile violating the key's constraints.

**Points to remember:**

- `Signature.update(...)` **does not** produce a per-chunk signature. It only feeds bytes into the message being signed/verified. Splitting `"hello PSS"` across two `update` calls or one yields identical verification outcomes because the byte sequence is the same.
- `Signature.sign()` returns signature bytes matching the RSA modulus length (256 bytes for RSA-2048), not the 32-byte SHA-256 digest or 32-byte salt.
- Each PSS signing call normally generates a new salt; **the same message and key can produce different signature bytes**. Never write tests requiring two PSS signatures to be byte-equal. Check `verify(...) == true` and account for expected randomness.
- `initSign(privateKey, SecureRandom random)` has an overload allowing an explicit RNG; use a proper CSPRNG, avoiding fixed seeds or exposed RNG state. In standard code, the provider manages random salt generation internally; do not generate and inject a salt as an external parameter.
- `Signature` holds mutable state and should not be shared across threads/requests; use a dedicated instance per operation or strict isolation.
- When converting `String` to bytes, specify `StandardCharsets.UTF_8`. Structured JSON/XML data needs a protocol ensuring **identical canonicalized byte sequences**; signing raw JSON and verifying re-ordered/re-serialized JSON can make `verify` return false even when the “logical content” is equivalent.
- When verifying, the public key must come from a **trusted source**; do not trust an algorithm name or key path requested by untrusted input. Enforce key/algorithm metadata and acceptance policy from trusted configuration/identities.

## 9. Interoperating with JOSE/JWT, X.509, and other libraries

### JWS/JWT: PS256 is not RS256

RFC 7518 section 3.5 specifies:

| JWS `alg` | Scheme | Message digest | MGF1 digest | Salt length |
| --- | --- | --- | --- | ---: |
| `PS256` | RSASSA-PSS | SHA-256 | SHA-256 | 32 bytes |
| `PS384` | RSASSA-PSS | SHA-384 | SHA-384 | 48 bytes |
| `PS512` | RSASSA-PSS | SHA-512 | SHA-512 | 64 bytes |
| `RS256` | RSASSA-PKCS1-v1_5 | SHA-256 | No MGF1 | No PSS salt |

In JWS, the actual signed input is the standard **JWS Signing Input** (such as the ASCII string `BASE64URL(UTF8(protectedHeader)) || "." || BASE64URL(payload)` subject to `b64` extension rules), not arbitrarily feeding parsed/re-serialized JSON into `Signature.update`. When applying `PS256`, the `PSSParameterSpec` from section 2 matches in digest/MGF/salt/trailer, yet the application must still enforce **all JWS rules**, not just call raw `Signature` on the payload.

**Never allow an untrusted `alg` header to open up arbitrary scheme/key selection.** The verifier must maintain an application- and key-specific allowlist of permitted algorithms, rather than automatically honoring whatever algorithm the token requests. A maintained JWT/JWS library with proper verification handles format, key, and policy checks; direct `Signature` fits custom protocols with explicit specs.

### X.509 and encoded parameters

An RSASSA-PSS signature can carry an **algorithm identifier and ASN.1 parameters** inside certificates or protocol structures. Java `AlgorithmParameters` can export PSS parameters from a provider, whereas the raw `byte[] signature` returned by `Signature.sign()` **does not embed a self-describing header declaring every profile field**. Thus when transmitting “raw” signatures alongside files/messages, both sides must pre-define or know the algorithm, digest/MGF/saltLen/trailer, and corresponding key.

If using a public key restricted to RSASSA-PSS or a certificate binding specific parameters, do not arbitrarily alter digest/salt; apply the key and algorithm per verified certificate metadata/policy. Do not hand-write ASN.1 encoders/decoders when standard libraries exist.

### Comparing with OpenSSL

An OpenSSL peer might configure `rsa_padding_mode:pss`, `rsa_mgf1_md:sha256`, and `rsa_pss_saltlen:32` for RSA-PSS SHA-256. If OpenSSL is using automatic salt-length detection (`auto`), max salt, or another policy, the output may fail verification against a verifier strictly requiring `saltLength=32`. When debugging, write down all **five profile fields and key length**, then test verification with a known test vector.

Do not blame every `verify=false` on text encoding. Check **all** of input bytes, key, padding mode, primary digest, MGF1 digest, salt length, and trailer.

## 10. Diagnostic checklist when a signature fails verification

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| Java signs cleanly, OpenSSL/JWS verifies false | Mismatched MGF1 digest or salt length | Explicitly record message/MGF SHA, `sLen`, and protocol profile; compare sign vs verify. |
| `verify=false` despite both using SHA-256 primary digest | MGF1-SHA1 on one side, or `sLen` 20 vs 32 | Inspect `PSSParameterSpec` and set every field explicitly on both sides. |
| Right RSA key, yet `SHA256withRSA` verifies false | PKCS#1 v1.5 differs from PSS scheme | Select `RSASSA-PSS` with complete params. |
| `InvalidAlgorithmParameterException` | Provider rejects the profile | Check MGF, digest, key constraints, and provider support. |
| `InvalidKeyException` or `SignatureException` on sign | Unsuitable RSA key, salt too long, or key restrictions | Inspect `modulusBits`, `emLen/hLen/sLen`, and error details. |
| `verify=false` only on Unicode messages | Byte/charset/canonicalization mismatch | Compare exact input bytes before `Signature.update`; standardize UTF-8 and canonicalization. |
| Signing the same message twice yields different bytes | PSS generates random salt | Verify each signature rather than comparing signature bytes. |
| Used `PSSParameterSpec.DEFAULT` while peer expects PS256 | `DEFAULT` uses SHA-1/MGF1-SHA1/`sLen=20` | Use the five-arg constructor SHA-256/MGF1-SHA256/`sLen=32`/trailer 1. |
| Salt length set to 256 because “SHA-256 is 256” | Confusing bits and bytes | SHA-256 output is 256 bits = 32 bytes; `sLen=32` for PS256. |
| Salt length too large for a small RSA key | Insufficient encoding space | Check `emLen >= hLen+sLen+2`; adjust profile/key per standard. |
| Called `Signature.update(digestBytes)` instead of message | PSS engine hashes digest as if it were a new message | Feed original signed-input bytes into `Signature`. |
| API returns `getParameters()==null` | Provider does not expose `AlgorithmParameters` | Retain/check the application's spec and test interoperability on the real provider. |
| Verification “succeeds” with attacker-supplied public key | Identity/key origin was not verified | Use a trusted trust store / certificate chain / key policy. |

**Error handling discipline:** when processing signatures from external data, handle invalid inputs cleanly. Do not treat `verify=false` and an exception as two “almost-valid” grades of a signature; neither is **acceptable** unless fully verified.

## 11. Hands-on exercises

1. **Reading a profile:** Explain each getter—`getDigestAlgorithm`, `getMGFAlgorithm`, `getMGFParameters`, `getSaltLength`, and `getTrailerField`. Why does `MGF1ParameterSpec.SHA256` not replace the message digest field?
2. **Running the demo:** Compile `RsaPssDemo.java` and explain why the signature is 256 bytes even though both the digest and salt are 32 bytes.
3. **Altering the message:** Change one letter of `hello PSS` on the verifier side and describe the result while keeping key and profile unchanged.
4. **Changing MGF digest:** Keep SHA-256 in `PSSParameterSpec.getDigestAlgorithm` but switch the verifier to MGF1-SHA1; per the RFC and test, why does this break matching? If a provider rejects mismatched params, at which step does that error occur?
5. **Changing `sLen`:** Sign with `sLen=32`, verify with `sLen=20`. Then re-sign **with `sLen=20` on both sides** and explain why it can verify true yet is no longer the JOSE `PS256` profile.
6. **Encoding limit:** For RSA-2048/SHA-256, compute `emBits`, `emLen`, and `maxSalt`; try `sLen=223` with the signer and record the exception on your runtime provider. Never use such nonsensical parameters in production.
7. **Changing message digest:** For RSA-2048/SHA-512, compute `hLen=64` and `maxSalt=190`; write out the `PSSParameterSpec` corresponding to `PS512` (SHA-512, MGF1-SHA512, salt 64, trailer 1).
8. **Chunk splitting:** Signer calls `update("hello ")` and `update("PSS")`, verifier calls `update("hello PSS")`. Why does verification still return true? How does `hello` vs `hello ` differ?
9. **JWS:** Describe every difference between `PS256` and `RS256`, including JWS message input bytes, scheme, MGF, and salt length.
10. **API design:** Sketch a function `verify(byte[] message, byte[] signature, PublicKey trustedKey, PSSParameterSpec approvedProfile)` and explain why the profile must come from trusted policy rather than the unverified message.
11. **Interoperability test:** Build a test vector across two providers/applications. Record algorithm metadata, modulus bit length, hash, MGF, MGF digest, salt length, trailer, and exact signed bytes; categorize every `verify=false` or exception failure.

**Completion criteria:** you can construct an explicit PSS profile, run `sign/verify` over exact bytes, distinguish the message digest from the MGF1 digest, choose salt length per protocol while checking RSA bounds, and name at least three reasons a PSS signature fails interoperability despite using the right public key.

## Official documentation

- [Java SE 17 `PSSParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html)
- [Java SE 17 `MGF1ParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html)
- [Java SE 17 `Signature` — `initSign`, `initVerify`, `setParameter`, `update`, `sign`, `verify`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [RFC 8017 — PKCS #1 v2.2, `8.1 RSASSA-PSS` and `9.1 EMSA-PSS`](https://www.rfc-editor.org/rfc/rfc8017.html)
- [RFC 7518 3.5 — JWS algorithms PS256, PS384, PS512](https://www.rfc-editor.org/rfc/rfc7518.html)
