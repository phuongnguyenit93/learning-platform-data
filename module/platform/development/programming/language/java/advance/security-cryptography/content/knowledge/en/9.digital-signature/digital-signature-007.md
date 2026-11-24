# 9.7 ECDSA DER and P1363 Signature Formats When Interoperating with Other Systems

## Learning objectives

After this lesson, you can:

1. Explain why the same **ECDSA** algorithm and same public key can still fail verification when two systems use **two different signature encodings**.
2. Distinguish an **ASN.1 DER** signature of form `SEQUENCE { INTEGER r, INTEGER s }` from an **IEEE P1363** fixed-length raw byte signature `r || s`.
3. Calculate exact P1363 length from the **curve group order bit length**, including P-521 with 66-byte components.
4. Use **Java 17 `Signature`** to sign and verify in both formats; convert DER ↔ P1363 with canonical validation.
5. Integrate cleanly with **JWS/JWT ES256, ES384, ES512**, distinguishing Base64URL from signature encoding.
6. Diagnose wrong curves, wrong hashes, differing signed message bytes, confusing DER signatures with DER keys/certificates, wrong integer padding, and low-S issues.

## 1. ECDSA produces an (r, s) integer pair; encoding comes next

**ECDSA (Elliptic Curve Digital Signature Algorithm)** is a digital signature scheme over elliptic curves. The signer uses a **private key**, and the verifier uses a **public key**. After hashing the signed data and performing the ECDSA math, the logical output is **two integers**:

```text
                 private key d
                      |
Message bytes -> Hash -> ECDSA sign -> (r, s)
                                        |
                                 ENCODE / SERIALIZE
                                  /               \
                                 v                 v
                       ASN.1 DER bytes       P1363 raw bytes
                        SEQUENCE(r,s)           r || s
```

**`(r, s)` is the mathematical meaning of the signature; DER and P1363 are two ways to serialize that exact pair of numbers into bytes.** Changing the encoding **does not change the key**, **does not change the curve**, **does not change the hash**, and **does not create a new signature**. If decoded and re-encoded accurately, the peer system still verifies the exact same ECDSA signature.

Successful verification also requires both parties to agree on:

- **Signed bytes**: byte-for-byte identical, including UTF-8, newlines, whitespace, JSON canonicalization, or Base64URL signing input.
- **Digest algorithm**: e.g., SHA-256 in `SHA256withECDSA`.
- **Curve and public key**: e.g., P-256, P-384, or P-521; keys must not be substituted.
- **Signature encoding**: ASN.1 DER or IEEE P1363 raw; some protocols add wrappers or canonicalization rules.
- **Protocol policy**: allowlisted algorithms, key ID, signature for the intended entity, and authenticated context fields.

Sending a valid signature under the wrong encoding label causes the verifier to error or reject even when data, key, and cryptographic math are all correct.

## 2. The two formats: DER and P1363

| Criterion | ECDSA ASN.1 DER | IEEE P1363 raw |
| --- | --- | --- |
| Structure | ASN.1 `SEQUENCE` containing two `INTEGER`s `r` and `s` | Direct concatenation of `r` and `s`: `r \|\| s` |
| Number representation | **Signed** DER integers (ECDSA values must be positive), big-endian, minimal length | **Unsigned** integers, big-endian, **left-padded with zeros to full width** |
| Leading byte | Usually `0x30` (ASN.1 SEQUENCE) | First byte is `r` data, **no standard tag** |
| Size | Varies with `r`, `s` values and ASN.1 length bytes | **Fixed by curve order** |
| Java 17 | `SHA256withECDSA` (JCA's standard DER format) | `SHA256withECDSAinP1363Format` (when supported by provider) |
| Real-world interoperability | Many crypto APIs, X.509/TLS, and traditional ASN.1 tools | JWS/JOSE ES256, ES384, ES512; certain IEEE P1363 SDKs/APIs |

Do not call P1363 “DER without a header.” P1363 requires **fixed width for both r and s**, whereas DER allows each `INTEGER` to vary in byte count and occasionally prepends a `00` byte to prevent negative interpretation. Simply stripping `30, 02` bytes does not produce valid P1363.

### 2.1 DER: two ASN.1 INTEGERs inside one SEQUENCE

In a standard DER ECDSA signature, the logical structure is:

```asn1
Ecdsa-Sig-Value ::= SEQUENCE {
    r INTEGER,
    s INTEGER
}
```

Bytes under **DER (Distinguished Encoding Rules)**:

```text
30 <SEQUENCE length>
   02 <r length> <r bytes, signed-positive, minimal>
   02 <s length> <s bytes, signed-positive, minimal>
```

- `0x30`: ASN.1 `SEQUENCE` tag.
- `0x02`: `INTEGER` tag.
- Length fields use DER length encoding (short form if below 128, long form if 128 or greater).
- `INTEGER` uses big-endian two's-complement signed representation, **with no redundant zeros**.
- Because `r, s > 0` in valid signatures, if the most significant bit of the first significant byte is `1`, DER **must prepend a `0x00` byte** so the positive integer is not read as negative.

Example purely to explain **encoding**, not a real ECDSA signature for any message/key:

```text
r = 1, s = 2

DER:
30 06  02 01 01  02 01 02

30 06       : SEQUENCE, 6 bytes of content
02 01 01    : INTEGER r = 1
02 01 02    : INTEGER s = 2
```

For a value starting with `0x80` (sign bit set), a DER `INTEGER` requires:

```text
Value r = 128 = 0x80
INTEGER DER = 02 02 00 80
                   ^^ mandatory 00 byte to keep number positive
```

Conversely, `02 02 00 01` is **non-canonical** DER because value 1 only needs `02 01 01`. When handling untrusted input, reject negative `INTEGER`s, invalid lengths, redundant zeros, trailing data, or non-canonical `SEQUENCE`s.

**Never assume a fixed DER length.** For ECDSA P-256, signatures are commonly around 70–72 bytes, yet can be shorter when `r`/`s` omit leading zeros; parse structurally rather than inferring by length. For P-521, the `SEQUENCE` content often exceeds 127 bytes, so DER uses **long-form length**, such as `30 81 ...`. Parsers assuming “a one-byte length” will break on large curves.

### 2.2 P1363: two fixed-width unsigned integers

For IEEE P1363:

```text
P1363 = I2OSP(r, width) || I2OSP(s, width)

width = ceil(bitLength(curve_order) / 8)
length(P1363) = 2 * width
```

Here `I2OSP` means converting an **unsigned** integer into exactly `width` big-endian bytes; if it has fewer significant bytes, **left-pad with `00`**. No ASN.1 tags, length bytes, or sign bytes are added. The first half is `r`, the second half is `s`; **never swap their order**.

| Common curve | Order bit length | Component width | Total P1363 |
| --- | ---: | ---: | ---: |
| NIST P-256 (`secp256r1`) | 256 | 32 bytes | **64 bytes** |
| NIST P-384 (`secp384r1`) | 384 | 48 bytes | **96 bytes** |
| NIST P-521 (`secp521r1`) | 521 | 66 bytes | **132 bytes** |

Note that **P-521 is 521 bits**, so each component takes `ceil(521/8) = 66` bytes, not 65. Total raw signature length is `132` bytes; the 7 unused high bits of the leading byte must still be represented cleanly.

An illustrative pair `r=1, s=2` for P-256:

```text
r: 00 00 ... 00 01   (32 bytes total)
s: 00 00 ... 00 02   (32 bytes total)
=> r || s is exactly 64 bytes
```

When converting DER to P1363, strip DER's positive-sign `00` byte if present, then **left-pad with enough zeros** so each part is exactly `width` bytes. When converting back, strip redundant raw zeros, then prepend `00` if the top byte has the sign bit set, and encode the DER `INTEGER`s/`SEQUENCE`.

## 3. Why can two systems return “invalid signature”?

Suppose Java signs with:

```java
Signature signer = Signature.getInstance("SHA256withECDSA");
```

This is an **embedded snippet** (requiring imports, key, and `initSign/update/sign`). In standard JDKs, it returns **DER-encoded** ECDSA `SEQUENCE(INTEGER r, INTEGER s)`.

Another API's contract states “ECDSA SHA-256, signature is IEEE P1363 r||s,” or requires **JWS ES256**. If you send raw DER bytes to it, it receives roughly 70 bytes instead of **64 bytes**. Both sides still use SHA-256/P-256, yet **differ in serialization contract**, causing failure.

The reverse is identical: passing 64-byte raw `r||s` into a verifier expecting ASN.1 DER causes the parser to miss `SEQUENCE` and two `INTEGER`s. Depending on the provider, Java may return `false` or throw `SignatureException` with an encoding error. Never catch an exception and treat it as “signature valid,” nor blindly try both formats on unlabeled input.

Correct integration flow:

```text
Party A computes (r, s)
       |
       +--> serialize DER ----> protocol expecting DER
       |
       +--> serialize P1363 --> protocol expecting raw r||s

Party B reads per specified format
       |
       v
Split r, s and validate 0 < r,s < order
       |
       v
ECDSA.verify(hash(bytes), publicKey, r, s)
```

If format conversion is required, perform it **once at the system boundary** with explicit expectations; keep test vectors and fail closed on invalid input rather than using heuristics like “first byte `0x30` means DER,” because raw P1363 can also happen to start with `0x30`.

## 4. Java 17 can handle both formats directly

Java 17 defines standard algorithm names including:

- `SHA256withECDSA` → ECDSA signature using SHA-256, standard ASN.1 DER encoding.
- `SHA256withECDSAinP1363Format` → same hashing/ECDSA, IEEE P1363 encoding.
- Correspondingly `SHA384withECDSA` / `SHA384withECDSAinP1363Format` for P-384.
- Correspondingly `SHA512withECDSA` / `SHA512withECDSAinP1363Format` for P-521.

**The Java algorithm name does not automatically enforce the curve.** For example, `SHA256withECDSA` specifies digest/ECDSA, while the curve comes from the **EC key**. The `ES256` protocol requires **P-256 + SHA-256**, so you must check both curve and algorithm rather than trusting only the name.

These algorithms are listed in **standard algorithm names** and supplied by SunEC on many JDKs; availability depends on runtime providers and configuration. Prefer `Signature.getInstance(name)` and verify support at startup, avoiding hardcoding a provider name unless necessary.

### 4.1 Practice 1: generating DER and P1363 signatures and verifying with matching APIs

Create **`EcdsaSignatureFormatsDemo.java`** (Java 17+):

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;

public class EcdsaSignatureFormatsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = generator.generateKeyPair();
        byte[] message = "document:v1".getBytes(StandardCharsets.UTF_8);

        Signature derSigner = Signature.getInstance("SHA256withECDSA");
        derSigner.initSign(pair.getPrivate());
        derSigner.update(message);
        byte[] der = derSigner.sign();

        Signature p1363Signer =
                Signature.getInstance("SHA256withECDSAinP1363Format");
        p1363Signer.initSign(pair.getPrivate());
        p1363Signer.update(message);
        byte[] p1363 = p1363Signer.sign();

        Signature derVerifier = Signature.getInstance("SHA256withECDSA");
        derVerifier.initVerify(pair.getPublic());
        derVerifier.update(message);

        Signature rawVerifier =
                Signature.getInstance("SHA256withECDSAinP1363Format");
        rawVerifier.initVerify(pair.getPublic());
        rawVerifier.update(message);

        int componentBytes =
                ((((ECPublicKey) pair.getPublic()).getParams()
                        .getOrder().bitLength()) + 7) / 8;
        System.out.println("component bytes: " + componentBytes);
        System.out.println("DER starts with SEQUENCE: " +
                (der.length > 0 && (der[0] & 0xff) == 0x30));
        System.out.println("P1363 bytes: " + p1363.length);
        System.out.println("DER verifies: " + derVerifier.verify(der));
        System.out.println("P1363 verifies: " + rawVerifier.verify(p1363));

        Signature changed = Signature.getInstance("SHA256withECDSAinP1363Format");
        changed.initVerify(pair.getPublic());
        changed.update("document:v2".getBytes(StandardCharsets.UTF_8));
        System.out.println("changed message verifies: " + changed.verify(p1363));
    }
}
```

Compile and run:

```bash
javac --release 17 EcdsaSignatureFormatsDemo.java
java EcdsaSignatureFormatsDemo
```

Verified output:

```text
component bytes: 32
DER starts with SEQUENCE: true
P1363 bytes: 64
DER verifies: true
P1363 verifies: true
changed message verifies: false
```

Explanation:

1. `KeyPairGenerator("EC")` generates a key on curve `secp256r1` (NIST P-256); each ECDSA signature uses the same key pair but is signed **separately twice**.
2. `SHA256withECDSA` returns DER; `SHA256withECDSAinP1363Format` returns fixed-width raw bytes. `der[0]==0x30` is a **structural observation in the demo**, not a rule for classifying arbitrary input formats.
3. `ECPublicKey.getParams().getOrder().bitLength()` yields the component width from the **group order**. P-256 has 32 bytes per part, so raw length is 64.
4. Each verifier receives the encoding expected by its `Signature.getInstance(...)`, so verification succeeds.
5. When message bytes change from `document:v1` to `document:v2`, the signature is no longer valid.

**Two separately generated signatures can differ in `r, s` due to ECDSA's internal nonce.** This demo does not directly compare the DER bytes and P1363 bytes from two independent signings; to prove conversion preserves *the same* signature, run the next practice exercise.

## 5. Converting DER ↔ P1363 properly

In applications, prefer selecting the **right format directly when calling `Signature`**. If a provider or SDK only supplies the other format, converting at the API boundary makes sense, yet **DER is a format with strict canonical rules**.

### 5.1 DER → P1363 procedure

1. Read an ASN.1 `SEQUENCE` tag `0x30` and **exact** length, with no trailing bytes.
2. Inside the `SEQUENCE` there must be **exactly two** `INTEGER`s in order `r, s`, with no extra fields.
3. DER `INTEGER`s must be positive, minimally encoded, with no negative sign or redundant `00` prefix.
4. Verify scalars `1 <= r,s < n`, where `n` is the EC group order from the public key's curve.
5. Convert each number to unsigned big-endian with exact width `ceil(bitLength(n)/8)` bytes. Left-pad with zeros if it has fewer significant bytes.
6. Concatenate both arrays without any separator, preserving `r||s` order.

### 5.2 P1363 → DER procedure

1. Require **exactly** `2 * width` bytes; reject truncated or oversized raw input.
2. Split into `rBytes` and `sBytes`, each of length `width`.
3. Construct `BigInteger(1, bytes)` to interpret as **unsigned**; using `new BigInteger(bytes)` without `signum=1` can misread values starting with a `1` bit as negative.
4. Check `1 <= r,s < n` per the actual curve.
5. Encode each number as a minimal DER `INTEGER`: strip redundant zeros, **prepend one `00` byte** if needed to preserve positive sign.
6. Wrap both `INTEGER`s in a `SEQUENCE`; apply DER short/long length encoding properly.

**Never slice or drop bytes at fixed offsets like “`DER.substring(4)`”.** P-256 DER signatures can vary in byte length, and P-521 additionally uses long-form lengths. Parsers must reject non-canonical DER, length overflows, trailing data, negative/zero `INTEGER`s, redundant zeros, and out-of-range scalars. Enforcing canonical encoding also prevents different systems from interpreting the same value across multiple arbitrary byte representations.

### 5.3 Practice 2: minimal format bridge with canonical checks

The following example is a **standalone Java 17 program**. It:

- Parses DER according to the minimal rules needed for ECDSA `SEQUENCE(INTEGER r, INTEGER s)`.
- Encodes DER lengths in both short and long forms, working cleanly with P-521.
- Checks `r`/`s` within the valid group order range rather than relying solely on bit counts.
- Uses `BigInteger(1, bytes)` for raw inputs and handles DER sign-zero padding properly.
- Signs once in DER, converts to P1363, converts back to DER, and verifies the signature using **both Java APIs**.
- Rejects a DER `INTEGER` containing a redundant leading `00`.

**Limitation:** this is a learning codec for ECDSA signatures, not a replacement for an audited ASN.1/cryptography library when handling complex multi-structure protocols. Never rely on `sun.security.util.*` or reflection into JDK internals.

Create **`EcdsaDerP1363Bridge.java`**:

```java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

public class EcdsaDerP1363Bridge {
    private static int width(BigInteger order) {
        return (order.bitLength() + 7) / 8;
    }

    private static void checkScalar(BigInteger x, BigInteger order) {
        if (x.signum() <= 0 || x.compareTo(order) >= 0) {
            throw new IllegalArgumentException("ECDSA scalar outside (0, n)");
        }
    }

    private static void requireTag(byte[] in, int[] pos, int end, int tag) {
        if (pos[0] >= end || (in[pos[0]++] & 0xff) != tag) {
            throw new IllegalArgumentException("Wrong DER tag");
        }
    }

    private static int readLength(byte[] in, int[] pos, int end) {
        if (pos[0] >= end) throw new IllegalArgumentException("Missing length");
        int first = in[pos[0]++] & 0xff;
        if (first < 128) return first;
        int count = first & 0x7f;
        if (count == 0 || count > 4 || count > end - pos[0]) {
            throw new IllegalArgumentException("Invalid DER length");
        }
        if (in[pos[0]] == 0) throw new IllegalArgumentException("Non-minimal length");
        long length = 0;
        for (int i = 0; i < count; i++) {
            length = (length << 8) | (in[pos[0]++] & 0xff);
        }
        if (length < 128 || length > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid long length");
        }
        return (int) length;
    }

    private static BigInteger readInteger(byte[] in, int[] pos, int end) {
        requireTag(in, pos, end, 0x02);
        int length = readLength(in, pos, end);
        if (length < 1 || length > end - pos[0]) {
            throw new IllegalArgumentException("Invalid INTEGER length");
        }
        int first = in[pos[0]] & 0xff;
        if ((first & 0x80) != 0) {
            throw new IllegalArgumentException("Negative INTEGER");
        }
        if (length > 1 && first == 0 &&
                (in[pos[0] + 1] & 0x80) == 0) {
            throw new IllegalArgumentException("Redundant 00 prefix");
        }
        BigInteger out = new BigInteger(
                1, Arrays.copyOfRange(in, pos[0], pos[0] + length));
        pos[0] += length;
        return out;
    }

    private static byte[] fixed(BigInteger n, int width) {
        byte[] bytes = n.toByteArray();
        int start = bytes.length > 1 && bytes[0] == 0 ? 1 : 0;
        int bytesToCopy = bytes.length - start;
        if (bytesToCopy > width) {
            throw new IllegalArgumentException("Scalar too wide");
        }
        byte[] result = new byte[width];
        System.arraycopy(bytes, start, result, width - bytesToCopy, bytesToCopy);
        return result;
    }

    public static byte[] derToP1363(byte[] der, BigInteger order) {
        int[] pos = {0};
        requireTag(der, pos, der.length, 0x30);
        int sequenceLength = readLength(der, pos, der.length);
        if (sequenceLength != der.length - pos[0]) {
            throw new IllegalArgumentException("Trailing data or bad SEQUENCE length");
        }
        BigInteger r = readInteger(der, pos, der.length);
        BigInteger s = readInteger(der, pos, der.length);
        if (pos[0] != der.length) {
            throw new IllegalArgumentException("Wrong SEQUENCE contents");
        }
        checkScalar(r, order);
        checkScalar(s, order);
        int width = width(order);
        byte[] result = new byte[2 * width];
        System.arraycopy(fixed(r, width), 0, result, 0, width);
        System.arraycopy(fixed(s, width), 0, result, width, width);
        return result;
    }

    private static byte[] derLength(int length) {
        if (length < 128) return new byte[] {(byte) length};
        int count = 0;
        for (int n = length; n != 0; n >>>= 8) count++;
        byte[] bytes = new byte[1 + count];
        bytes[0] = (byte) (0x80 | count);
        for (int i = count; i > 0; i--) {
            bytes[i] = (byte) length;
            length >>>= 8;
        }
        return bytes;
    }

    private static byte[] tlv(int tag, byte[] value) {
        byte[] len = derLength(value.length);
        byte[] result = new byte[1 + len.length + value.length];
        result[0] = (byte) tag;
        System.arraycopy(len, 0, result, 1, len.length);
        System.arraycopy(value, 0, result, 1 + len.length, value.length);
        return result;
    }

    public static byte[] p1363ToDer(byte[] raw, BigInteger order) {
        int width = width(order);
        if (raw.length != width * 2) {
            throw new IllegalArgumentException("P1363 must be 2*width bytes");
        }
        BigInteger r = new BigInteger(1, Arrays.copyOfRange(raw, 0, width));
        BigInteger s = new BigInteger(1, Arrays.copyOfRange(raw, width, 2 * width));
        checkScalar(r, order);
        checkScalar(s, order);
        byte[] ri = tlv(0x02, r.toByteArray());
        byte[] si = tlv(0x02, s.toByteArray());
        byte[] both = new byte[ri.length + si.length];
        System.arraycopy(ri, 0, both, 0, ri.length);
        System.arraycopy(si, 0, both, ri.length, si.length);
        return tlv(0x30, both);
    }

    public static void main(String[] args) throws Exception {
        String[] curves = {"secp256r1", "secp384r1", "secp521r1"};
        String[] hashes = {"SHA256", "SHA384", "SHA512"};
        byte[] data = "signed-record-v1".getBytes(StandardCharsets.UTF_8);

        for (int i = 0; i < curves.length; i++) {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
            generator.initialize(new ECGenParameterSpec(curves[i]));
            KeyPair pair = generator.generateKeyPair();
            BigInteger order = ((ECPublicKey) pair.getPublic()).getParams().getOrder();

            Signature signer = Signature.getInstance(hashes[i] + "withECDSA");
            signer.initSign(pair.getPrivate());
            signer.update(data);
            byte[] der = signer.sign();

            byte[] raw = derToP1363(der, order);
            byte[] derAgain = p1363ToDer(raw, order);

            Signature verifyRaw =
                    Signature.getInstance(hashes[i] + "withECDSAinP1363Format");
            verifyRaw.initVerify(pair.getPublic());
            verifyRaw.update(data);

            Signature verifyDer =
                    Signature.getInstance(hashes[i] + "withECDSA");
            verifyDer.initVerify(pair.getPublic());
            verifyDer.update(data);

            System.out.println(curves[i] + ": P1363=" + raw.length +
                    ", both verify=" + (verifyRaw.verify(raw) && verifyDer.verify(derAgain)) +
                    ", DER exact=" + Arrays.equals(der, derAgain));
        }

        // Used only for testing the DER parser; this is not a production curve order.
        BigInteger exampleOrder = BigInteger.ONE.shiftLeft(256)
                .subtract(BigInteger.valueOf(189));
        byte[] malformed = {0x30, 0x07, 0x02, 0x02, 0x00, 0x01,
                0x02, 0x01, 0x01};
        boolean invalidDerRejected;
        try {
            derToP1363(malformed, exampleOrder);
            invalidDerRejected = false;
        } catch (IllegalArgumentException expected) {
            invalidDerRejected = true;
        }
        System.out.println("non-minimal DER rejected: " + invalidDerRejected);
    }
}
```

Compile and run:

```bash
javac --release 17 EcdsaDerP1363Bridge.java
java EcdsaDerP1363Bridge
```

Verified output with a provider supporting P-256/P-384/P-521 and the corresponding JCA names:

```text
secp256r1: P1363=64, both verify=true, DER exact=true
secp384r1: P1363=96, both verify=true, DER exact=true
secp521r1: P1363=132, both verify=true, DER exact=true
non-minimal DER rejected: true
```

**Explanation of results:**

- Each curve generates **one DER signature**, then converts the bytes of **that exact `(r,s)` pair** to P1363; the P1363 verifier accepts the signature, proving no re-signing is needed.
- Converting back P1363 → DER and comparing `Arrays.equals(der, derAgain)` returns `true`, because canonical DER has a unique representation for that pair.
- P-521 has `width=66`, yielding 132-byte P1363; the codec handles DER long-form lengths rather than assuming a single length byte.
- The `malformed` check uses an `INTEGER 00 01` with an **unnecessary** leading zero. The parser rejects it; `exampleOrder` simply supplies a sufficiently large bound for **syntax testing**, never used as a real signing key/curve order.
- The boolean results are deterministic whenever the environment provides the algorithms; actual DER bytes and DER lengths may vary from run to run.

**Never replace the converter with string splitting at fixed DER byte offsets.** Beyond parsing accurately, production systems must test parsers with intentionally malformed inputs and cap input sizes to avoid unsafe ASN.1 processing. Even when using a dedicated ASN.1 library, enforce **canonical DER** and **`r`/`s` range checks**, rather than merely parsing into two `BigInteger`s.

## 6. JWS/JWT ES256, ES384, and ES512 use raw P1363

This is a widespread format mismatch when Java applications integrate with external SDKs or identity providers. In **JSON Web Signature (JWS)**:

| JOSE `alg` | Required curve | Hash | JWS signature (before Base64URL) | Unpadded Base64URL signature segment |
| --- | --- | --- | ---: | ---: |
| **ES256** | P-256 | SHA-256 | **64 bytes** | 86 chars |
| **ES384** | P-384 | SHA-384 | **96 bytes** | 128 chars |
| **ES512** | P-521 | SHA-512 | **132 bytes** | 176 chars |

**ES512** does not mean “curve P-512”; it uses **P-521** and **SHA-512** per RFC 7518. A JWS signature is defined as fixed `r||s`, not DER. Hence doing:

```text
Base64URL(ASN1_DER_ECDSA_SIGNATURE)
```

does **not** produce a valid JWS ES256 token, even though externally it looks like a Base64URL segment. You must obtain the 64-byte raw `r||s` (or properly convert DER → raw) before unpadded Base64URL encoding.

### 6.1 The signed data in JWS is the “signing input”

A JWS Compact token has three segments:

```text
base64url(header).base64url(payload).base64url(raw_ECDSA_signature)
```

The signature is computed over the **ASCII bytes of the string**:

```text
base64url(header) + "." + base64url(payload)
```

not directly over the standalone raw JSON payload. Two semantically equivalent JSON objects differing in field order, spaces, escaping, or Base64URL encoding produce **different signing inputs**.

Having `"alg": "ES256"` in the header does not by itself justify trusting that header. When verifying a JWS, the server must determine **permitted algorithms, trusted keys, issuer/audience/expiry, and application context** from policy, never letting an attacker select the algorithm or key via untrusted header fields.

### 6.2 Practice 3: Java 17 properly signing JWS ES256 raw P1363

The example builds a minimal **JWS signing input**, signs it with `SHA256withECDSAinP1363Format`, and verifies the exact bytes. This is a demo of **encoding and the Signature API**, not a JWT library, and it does not implement claims, trust, issuer, or expiry checks for real authentication.

Create **`EcdsaJwsEs256Demo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Base64;

public class EcdsaJwsEs256Demo {
    private static String b64url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = generator.generateKeyPair();

        String header = b64url(
                "{\"alg\":\"ES256\"}".getBytes(StandardCharsets.UTF_8));
        String payload = b64url(
                "{\"sub\":\"demo\"}".getBytes(StandardCharsets.UTF_8));
        byte[] signingInput = (header + "." + payload)
                .getBytes(StandardCharsets.US_ASCII);

        Signature signer =
                Signature.getInstance("SHA256withECDSAinP1363Format");
        signer.initSign(pair.getPrivate());
        signer.update(signingInput);
        byte[] raw = signer.sign();
        String signatureSegment = b64url(raw);

        Signature verify = Signature.getInstance("SHA256withECDSAinP1363Format");
        verify.initVerify(pair.getPublic());
        verify.update(signingInput);
        boolean valid = verify.verify(Base64.getUrlDecoder().decode(signatureSegment));

        Signature changed = Signature.getInstance("SHA256withECDSAinP1363Format");
        changed.initVerify(pair.getPublic());
        changed.update((header + "." + b64url(
                "{\"sub\":\"changed\"}".getBytes(StandardCharsets.UTF_8)))
                .getBytes(StandardCharsets.US_ASCII));
        boolean tamperedValid = changed.verify(raw);

        System.out.println("signature bytes: " + raw.length);
        System.out.println("signature segment chars: " + signatureSegment.length());
        System.out.println("correct input verifies: " + valid);
        System.out.println("changed input verifies: " + tamperedValid);
    }
}
```

Run commands:

```bash
javac --release 17 EcdsaJwsEs256Demo.java
java EcdsaJwsEs256Demo
```

Verified output:

```text
signature bytes: 64
signature segment chars: 86
correct input verifies: true
changed input verifies: false
```

The actual `signatureSegment` string changes because `r,s` vary, yet **raw length is always 64 bytes**, and unpadded Base64URL of 64 bytes is always **86 characters**. The structure signs the exact signing input with a dot separating the two encoded parts; altering the payload causes verification to fail.

In real systems, use a **tested JOSE/JWT library with explicit algorithm and key policies**. Never hand-roll JWT authorization by string concatenation from this example. The key takeaway here is: **JOSE ECDSA signature segment = Base64URL(P1363 raw)**.

## 7. A signature's ASN.1 DER is not every kind of “DER”

In Java and PKI, the term “DER” appears in several places:

| Object | Java example / structure | Contents |
| --- | --- | --- |
| **ECDSA signature value** | `SEQUENCE { INTEGER r, INTEGER s }` | Only the two numbers of the signature |
| **X.509 certificate** | DER `Certificate` structure | Contains TBS certificate, signing algorithm, `signatureValue`, and many fields |
| **X.509 public key (SPKI)** | `publicKey.getEncoded()`, usually `X.509` | Contains algorithm/curve and public-key bitstring, **not a signature** |
| **PKCS#8 private key** | `privateKey.getEncoded()` (if exportable) | ASN.1-encoded private key structure, **not a signature** |
| **PEM** | Base64 wrapping DER/key/cert with markers | Textual armor around content, does not define DER vs. P1363 of an API signature |

For instance, when an X.509 certificate carries an ECDSA signature, `signatureValue` is a **BIT STRING containing the DER encoding of `ECDSA-Sig-Value`**. Never pass the entire certificate DER or the outer BIT STRING wrapper straight to `Signature.verify(...)`, which expects only the **signature bytes**.

Likewise, calling `publicKey.getEncoded()` for X.509/SPKI yields the encoded **key** bytes, not an “X.509-encoded signature.” Parsing signatures and parsing public keys require distinct APIs.

## 8. Curve order, valid r/s, and the high-S/low-S issue

### 8.1 Why use `order` instead of key file length?

ECDSA operates over a point group of order `n`. Both signature integers must lie in:

```text
1 <= r < n
1 <= s < n
```

In Java, given an `ECPublicKey`, read:

```java
BigInteger order = ((ECPublicKey) publicKey)
        .getParams().getOrder();
int width = (order.bitLength() + 7) / 8;
```

This is an **embedded snippet** inside a method that already has `publicKey` and imports `ECPublicKey`/`BigInteger`. P1363 length is computed from **order bit length**, not key DER length or hash size. For common P-curves, width matches the curve coordinate width, yet the authoritative rule comes from the `r/s` domain.

If a partner API sends a 64-byte raw P1363 signature when P-384 is required, never “pad a few zeros” to force it through: reject the wrong length and confirm the protocol's mandated curve.

### 8.2 Canonical DER encoding vs. low-S canonicalization

ECDSA exhibits a form of **signature malleability**: for a valid signature `(r,s)` under the standard equations, `(r, n-s)` also verifies validly since `s` stays in the valid range. Some ecosystems enforce **low-S**, typically `s <= n/2`, to pick a unique representative from the mathematical equivalence class.

Distinguish clearly:

- **Canonical DER**: every `(r,s)` pair has **one canonical DER encoding** (no redundant zeros, no non-minimal lengths).
- **Low-S policy**: a constraint **on the value of `s`**, not on DER tag/length encoding.
- **DER ↔ P1363 conversion**: only changes the representation of **the same `r,s`**; it does not silently replace `s` with `n-s`.

Never silently “normalize to low-S” inside a format converter unless the protocol specifies it. Changing `s` produces a **different signature value**, even though it verifies for the same message/key; that can break byte comparisons, key attestation, transaction IDs, or another system's canonicalization rules. If a protocol requires low-S, handle it explicitly and test against official vectors.

**Never reuse the secret nonce `k` when signing with ECDSA.** That is a critical private-key compromise bug regardless of DER or P1363. Let a trusted crypto provider manage randomness or deterministic signing; never supply `k` from application code. RFC 6979 specifies deterministic ECDSA; a signature produced with deterministic `k` can still be encoded in either DER or P1363.

## 9. Two-system integration checklist

When a Java team receives “signature invalid” from another system, ask in order:

1. **Byte format?** Does the contract expect DER `SEQUENCE(INTEGER r,s)` or raw `r||s`? For JOSE ES256, it must be 64 raw bytes **before** Base64URL.
2. **Curve?** Do P-256/P-384/P-521 match? Inspect the actual key, not just the Java algorithm name.
3. **Hash?** `SHA256withECDSA` or SHA-384/SHA-512 per protocol? Do not pre-hash and then feed into an API with built-in hashing.
4. **Are signed bytes byte-for-byte identical?** JSON whitespace, UTF-8, `LF/CRLF` newlines, field ordering, compression, JWS signing input encoding.
5. **Raw length?** 64/96/132 bytes depending on curve; validate before calling verify.
6. **Does the DER parser enforce canonical encoding?** No negative `INTEGER`s, redundant leading zeros, trailing data, bad lengths, or out-of-range `r`/`s`.
7. **Base64 or Base64URL?** JWS uses the URL-safe alphabet `-` and `_`, typically unpadded; do not confuse with hex/PEM.
8. **Right public key?** Check key ID, trusted origin, certificate chain/metadata/permissions; never trust keys proposed by an untrusted payload.
9. **Low-S policy?** If a peer rejects high-S, recognize it as a **protocol policy rule**, not a broken DER parser.
10. **Provider/version?** Java 17 specifies P1363 names in standard names, yet does the target provider implement that algorithm/curve? Log algorithm and provider names in test environments without logging private keys.
11. **Fail-closed error handling?** `Signature.verify(...)` may return `false` or throw an exception on bad encoding. Catch errors to **reject**, never trying multiple unapproved variants.
12. **Shared test vectors?** Both sides need the same public key, message/signing input, format, and signature bytes. Test both directions, leading sign bits, `r`/`s` with leading zeros, P-521 long-form lengths, and malformed data.

### 9.1 Anti-patterns to avoid

- **“DER and P1363 are both ECDSA so the bytes are identical.”** False: they serialize the same `r,s` using two distinct structures.
- **“P-256 DER is always 70/71/72 bytes.”** False: DER has variable length; never hard-code it.
- **“Drop the first two DER bytes and split in half.”** False: there are `INTEGER` tags, lengths, sign-padding zeros, and long-form lengths.
- **“Trim leading zeros from raw to shorten the signature.”** False: P1363 requires **fixed width**.
- **“Using `BigInteger(rawBytes)` is enough.”** False: the signed constructor can read positive values as negative; use `BigInteger(1, rawBytes)` and validate range.
- **“`SHA256withECDSA` alone gives ES256.”** Insufficient: ES256 mandates **P-256 + SHA-256 + JWS P1363 encoding** over the exact signing input.
- **“`Base64URL(DER)` is P1363.”** False: Base64URL only encodes bytes as text; it does not convert ASN.1.
- **“The public key returns DER, so the signature must also be DER.”** False: key encoding and signature encoding are independent.
- **“Changing formats requires re-signing.”** False: proper conversion needs no private key; only `r,s` and curve order to determine width and range.
- **“Low-S is a kind of DER.”** False: low-S constrains scalar values, while DER specifies serialization.
- **“Different signature bytes mean invalid.”** ECDSA can use a different nonce when re-signing the same message/key; always **verify** rather than comparing two independent signatures.
- **“A parser error in the verifier should try all encodings and accept the first match.”** Never: allowed algorithms/encodings must come from a trusted contract to avoid expanding interpretation surfaces unexpectedly.

## 10. Self-check exercises

**1.** Which two values does ECDSA produce prior to serialization?  
**Answer:** Two positive scalars `r` and `s` in the range `1..n-1`.

**2.** For P-256, how long is a raw P1363 signature?  
**Answer:** `32 + 32 = 64` bytes, regardless of how many leading zeros `r`/`s` have.

**3.** Why might DER prepend a `00` byte to an `INTEGER`?  
**Answer:** So a number whose high bit is `1` is still read as a **positive** signed ASN.1 `INTEGER`.

**4.** Does P-521 use 65 or 66 bytes for each `r`/`s` component?  
**Answer:** `ceil(521/8) = 66` bytes; the entire raw signature is 132 bytes.

**5.** How does `SHA256withECDSAinP1363Format` differ from `SHA256withECDSA`?  
**Answer:** Primarily **signature output/input encoding** (P1363 vs. DER); the underlying hash + ECDSA primitives are the same for the same EC key.

**6.** How do you send a signature from Java DER to JWS ES256?  
**Answer:** Parse DER to extract `r,s`, encode both as 32-byte unsigned big-endian, concatenate into 64 raw bytes, then **unpadded Base64URL** encode.

**7.** Can you use SHA-256 with a P-384 key and call it ES384?  
**Answer:** No. ES384 requires **P-384 and SHA-384** per the JOSE specification.

**8.** Can a verifier distinguish DER from P1363 purely by checking if the first byte is `0x30`?  
**Answer:** Not reliably. Raw P1363 can also start with `0x30`; rely on the protocol contract and strict structural parsing.

**9.** Does “canonical DER” guarantee low-S?  
**Answer:** No. Canonical DER only guarantees a unique encoding for a given `(r,s)` pair; low-S is a policy constraining the value of `s`.

**10.** Why can verifying a JWS against the raw JSON payload fail?  
**Answer:** JWS signs the **ASCII bytes of `base64url(header).base64url(payload)`**, not the raw JSON.

## Key takeaway

The most important mental model when integrating ECDSA is:

```text
ECDSA math -> (r, s) -> signature encoding -> bytes on wire

ASN.1 DER: SEQUENCE(INTEGER r, INTEGER s), signed-positive/minimal, variable length
IEEE P1363: unsigned fixed-width r || s, length from curve order

Java: SHA256withECDSA  <->  SHA256withECDSAinP1363Format
JWS ES256: P-256 + SHA-256 + raw 64-byte P1363 + Base64URL segment
```

By **aligning curve, hash, exact signed bytes, and signature encoding**, and validating `r,s` plus canonical DER at system boundaries, you can exchange signatures across Java, ASN.1 libraries, and JOSE systems without re-signing or changing keys.

## Official references

- [Java 17 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): `SHA256withECDSA` and `...inP1363Format` names, Java signature structures.
- [Java 17 — Signature API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `initSign/update/sign` and `initVerify/update/verify` lifecycles.
- [Java 17 — Oracle JDK Providers](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): SunEC support scope and provider behavior.
- [RFC 3279 2.2.3 — ECDSA Signature Algorithm](https://www.rfc-editor.org/rfc/rfc3279#section-2.2.3): `ECDSA-Sig-Value` as DER `SEQUENCE(r INTEGER, s INTEGER)`.
- [RFC 5759 4.2 — ECDSA signatureValue in X.509](https://www.rfc-editor.org/rfc/rfc5759#section-4.2): positive `INTEGER`/`00` byte and BIT STRING wrapping DER signature.
- [RFC 7518 3.4 — ECDSA for JWS](https://www.rfc-editor.org/rfc/rfc7518#section-3.4): ES256/384/512, P1363 byte-width, and JWS signature lengths.
- [RFC 6979 — Deterministic ECDSA](https://www.rfc-editor.org/rfc/rfc6979): deterministic signing nonce generation, independent of DER/P1363 encoding.
