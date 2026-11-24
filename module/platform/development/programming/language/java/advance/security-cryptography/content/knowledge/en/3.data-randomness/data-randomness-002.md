# 3.2 Base64, HexFormat, and the Difference Between Data Representation and Secret Protection

## Learning Objectives

After this lesson, you will be able to:

- Explain how **encoding (data representation)** differs from **encryption**, hashing, MACs, and digital signatures.
- Understand how bytes are converted to Base64 and hexadecimal (hex), size overhead, and appropriate use cases.
- Properly use **java.util.Base64** and **java.util.HexFormat** (Java 17+) for representation encoding, decoding, and round-trip checks; distinguish Base64 Basic, URL-safe, and MIME.
- Properly handle bytes, UTF-8 charset, invalid inputs, binary data, and canonicalization risks.
- Recognize security mistakes: treating Base64/hex as secrecy, putting encoded secrets into logs/URLs, or misunderstanding Basic Authentication, JWTs, or hash strings.

## 1. Start from Bytes, Not Display Strings

Computers store and transmit information as **bytes**. When bytes need to enter text-oriented environments (JSON, config files, HTTP headers, diagnostic logs, QR codes, text files, protocols accepting only printable characters), we use a **representation** that turns bytes into safely readable/transmissible strings according to specific rules.

For example, the character string **Java!** in UTF-8 produces five bytes:

~~~text
Text:                 Java!
UTF-8 bytes (hex):    4a 61 76 61 21
Base64 of bytes:      SmF2YSE=
Hex of bytes:         4a61766121
~~~

Both **SmF2YSE=** and **4a61766121** represent **the same five original bytes**. Anyone who knows the Base64/hex rules can recover those exact five bytes. No password or secret key is needed.

Distinguish the two conversion layers:

~~~text
Unicode characters --[UTF-8 encode]--> byte[]
                                        |
                                 +------+------+
                                 |             |
                              [Base64]       [Hex]
                                 |             |
                                text          text
                                 |             |
                               decode        parse
                                 |             |
                                 +------v------+
                                        |
                                      byte[]
                              --[UTF-8 decode]--> Unicode characters
~~~

**UTF-8** is how characters become bytes; **Base64/hex** turn bytes into characters from a restricted alphabet. They solve representation compatibility problems, not secrecy. Bytes of arbitrary binary data—such as images, signatures, nonces, or ciphertexts—are not necessarily valid UTF-8 text: do not arbitrarily convert any `byte[]` into a String to "read" its contents.

### 1.1 Four Commonly Confused Operation Groups

| Operation | Goal | Input → Output | Secret key required? | Recovers original? |
| --- | --- | --- | --- | --- |
| **Encoding** (Base64, hex, UTF-8) | Change representation for storage/transmission/display | Bytes ↔ characters by rules | No | Yes, given the right format/charset |
| **Encryption** (e.g., AES-GCM) | Keep data confidential, often with integrity authentication | Plaintext → ciphertext | Yes | Yes, with valid key and parameters |
| **Hash** (e.g., SHA-256) | Create fixed-length fingerprint of data | Bytes → digest | No for standard hashes | No reverse decryption; weak data can be guessed/brute-forced |
| **MAC/digital signature** (HMAC, Ed25519, etc.) | Verify integrity/authenticity under a key model | Data + key → auth tag/signature | Secret key or private key to create | Not used to recover original data |

**A string that looks like random characters is not necessarily secure.** Visual unreadability is not a security property.

## 2. How Does Base64 Work?

### 2.1 The 6-Bit Mechanism and Padding

Base64 reads a bitstream in **6-bit** groups, mapping each group to one of 64 characters. Three bytes containing 24 bits are represented as four Base64 characters. Therefore:

- Three input bytes → four characters.
- One input byte → two data characters and typically two **==** padding characters.
- Two input bytes → three data characters and typically one **=** character.
- If the input is divisible by three bytes, no padding is needed.

With **Base64 Basic with padding**, the output character length is **4 × ceil(byte_count / 3)**. This is roughly a 33.3% size expansion for sufficiently large data, plus padding overhead when data is short. Never use the String length of a Unicode string instead of the byte count when computing size.

**Padding holds no secrecy**; it clarifies the trailing byte remainder of the data. Some variants omit padding because protocol rules allow the receiver to infer it. Adding or removing padding does not turn Base64 into a security encryption mechanism.

### 2.2 Three Variants in Java

Java provides three main encoder/decoder pairs in **java.util.Base64**:

| Variant | Java API | Alphabet/characteristics | Use case |
| --- | --- | --- | --- |
| **Basic** | Base64.getEncoder() / getDecoder() | A–Z, a–z, 0–9, **+** and **/**; **=** padding when needed; no line breaks | JSON, configs, binary data in text without + and / restrictions |
| **URL-safe** | Base64.getUrlEncoder() / getUrlDecoder() | Uses **-** instead of **+**, **_** instead of **/**; padding can be omitted via withoutPadding() | URL components, Base64URL-formatted tokens, protocol-defined names/IDs |
| **MIME** | Base64.getMimeEncoder() / getMimeDecoder() | May wrap lines (typically 76 chars, CRLF); MIME decoder accepts and ignores certain non-alphabet characters | MIME/email content per matching specifications |

**Do not swap variants arbitrarily.** Base64 Basic contains **+** and **/**: **+** can be interpreted as a space in some query/form encodings, while **/** acts as a path separator. Base64URL replaces those two characters, yet still does not provide confidentiality, tamper resistance, or replay protection.

**The MIME decoder is not suitable as a strict validator for security tokens**, because its character-ignoring rules are more permissive than Basic/URL. Choose the decoder according to the protocol; enforce length bounds and validate contents before use.

### 2.3 Base64 Is Not Tied to the Original Data Type

Base64 only knows **byte[]**; it does not know whether those bytes are a PNG image, UTF-8 JSON, an AES key, a digital signature, or random data. To recover meaning, the application must know from **protocol/metadata**:

- Which bytes are being represented?
- Once decoded, should they be treated as UTF-8, protobuf, an image, or ciphertext?
- If ciphertext, which key, nonce, and algorithm decrypt it?
- Is the payload authenticated and authorized before trusting it?

Never use a Base64 appearance as proof that data has been encrypted, signed, or integrity-checked.

## 3. Hexadecimal and Java 17 HexFormat

**Hex** uses base 16: each **4-bit nibble** is represented by a digit from 0–9, a–f. One 8-bit byte corresponds to **two hex digits**.

Example:

~~~text
Binary byte:          1111 1011
Hex:                  FB
Binary byte:          0000 0000
Hex:                  00
Three bytes:          FB FF 00
Contiguous hex:       fbff00
Delimited hex:        FB:FF:00
~~~

Hex is well suited for reading byte dumps, printing hash values, identifiers, fingerprints, nonces/IVs, and addresses in text form. Without separators, raw hex size is **exactly twice the byte count**: 32 bytes → 64 hex characters. Hex is usually longer than Base64, trading compactness for easy byte-by-byte inspection.

Java 17 introduced **java.util.HexFormat**, avoiding custom byte-to-hex loops or external dependencies for basic operations.

- **HexFormat.of().formatHex(bytes):** produces a contiguous hex string, lowercase by default.
- **HexFormat.of().parseHex(text):** converts a valid hex string back to byte[], expecting no delimiters by default.
- **HexFormat.of().withUpperCase():** selects uppercase A–F when formatting.
- **HexFormat.ofDelimiter(":"):** places **:** between bytes; parsing and formatting must agree on the defined format.
- **formatHex** does not automatically add **0x** prefixes, spaces, or arbitrary characters; such formatting must be explicitly specified and handled.

Inputs with an odd number of digits, non-hex characters, or mismatched delimiters are rejected (e.g., IllegalArgumentException). Do not silently drop invalid characters, truncate, or auto-repair inputs with unclear rules.

## 4. Java 17+ Practice: Base64, Base64URL, and HexFormat Round-Trips

Create file **RepresentationDemo.java** (saved as UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;

public class RepresentationDemo {
    public static void main(String[] args) {
        byte[] textBytes = "Java!".getBytes(StandardCharsets.UTF_8);

        String basic = Base64.getEncoder().encodeToString(textBytes);
        String hex = HexFormat.of().formatHex(textBytes);

        byte[] fromBase64 = Base64.getDecoder().decode(basic);
        byte[] fromHex = HexFormat.of().parseHex(hex);

        System.out.println("Base64: " + basic);
        System.out.println("Hex: " + hex);
        System.out.println("Base64 round-trip: "
                + Arrays.equals(textBytes, fromBase64));
        System.out.println("Hex round-trip: "
                + Arrays.equals(textBytes, fromHex));
        System.out.println("Text round-trip: "
                + new String(fromBase64, StandardCharsets.UTF_8));

        // These bytes have high 1 bits and are not directly readable UTF-8 text.
        byte[] binary = {(byte) 0xFB, (byte) 0xFF, 0x00};

        System.out.println("Basic binary: "
                + Base64.getEncoder().encodeToString(binary));
        System.out.println("URL binary: "
                + Base64.getUrlEncoder().encodeToString(binary));
        System.out.println("Hex binary: "
                + HexFormat.ofDelimiter(":")
                        .withUpperCase()
                        .formatHex(binary));
        System.out.println("Base64URL one byte: "
                + Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(new byte[] {(byte) 0xFF}));
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 RepresentationDemo.java
java RepresentationDemo
~~~

Exact stdout:

~~~text
Base64: SmF2YSE=
Hex: 4a61766121
Base64 round-trip: true
Hex round-trip: true
Text round-trip: Java!
Basic binary: +/wA
URL binary: -_wA
Hex binary: FB:FF:00
Base64URL one byte: _w
~~~

Explanation:

1. **getBytes(StandardCharsets.UTF_8)** explicitly defines how text becomes bytes. Restoring text also uses matching UTF-8; do not rely on the environment's default charset.
2. **encodeToString** creates a string representation from bytes; **decode** returns byte[]. The two operations are inverses for valid inputs.
3. **formatHex/parseHex** perform the analogous pair of transforms, using two hex digits per byte. `Arrays.equals` confirms the bytes are preserved.
4. For bytes **FB FF 00**, Base64 Basic is **+/wA** and Base64URL is **-_wA**; different alphabets, yet both represent the same three bytes.
5. A single byte **FF** becomes **_w** when Base64URL omits padding; with a padded encoder, the result is **_w==**. Padding is not a security mechanism.
6. **HexFormat.ofDelimiter(":").withUpperCase()** formats three bytes as **FB:FF:00**; to parse this format, use matching HexFormat.ofDelimiter(":").parseHex(...).

**Memory note:** Converting data to Base64/hex Strings creates new copies. If the original data is a secret, the copy is also a secret. Do not print real secrets to logs just to "check formatting."

## 5. Why Base64/Hex Do Not Protect Confidentiality

**Encoding has no key.** Anyone who intercepts or reads the string can decode it using the public algorithm. For example, a config line:

~~~text
apiKeyBase64: ZGVtby1zZWNyZXQ=
~~~

A simple Base64 decode recovers the text **demo-secret**. Naming a variable **encryptedPassword**, adding a cryptic prefix, or Base64-encoding multiple times does not create confidentiality.

A hex string of a token, card number, password, private key, or personal data is **just as sensitive as the original bytes**. The string may be long and hard to read, yet it can still be recovered intact. Never send it to logs, analytics, URLs, tickets, or public places just because it is "encoded."

### 5.1 Java 17+ Example: Encoding Is Reversible, Digests Are Merely Represented

Create **RepresentationVsProtectionDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;

public class RepresentationVsProtectionDemo {
    public static void main(String[] args) throws Exception {
        // Public illustrative string only, NOT a real secret.
        byte[] sample = "demo-secret".getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(sample);
        String recovered = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(sample);
        String digestHex = HexFormat.of().formatHex(digest);
        String digestBase64 = Base64.getEncoder().encodeToString(digest);

        System.out.println("Recovered: " + recovered);
        System.out.println("SHA-256 bytes: " + digest.length);
        System.out.println("Digest hex chars: " + digestHex.length());
        System.out.println("Digest Base64 chars: " + digestBase64.length());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 RepresentationVsProtectionDemo.java
java RepresentationVsProtectionDemo
~~~

Stdout:

~~~text
Recovered: demo-secret
SHA-256 bytes: 32
Digest hex chars: 64
Digest Base64 chars: 44
~~~

Key observation: Base64 recovers **demo-secret** immediately. Conversely, **SHA-256** returns a 32-byte digest; hex or Base64 are just two ways of **displaying the same digest**, adding or removing zero cryptographic properties of the hash.

A hash has no "decrypt" function to recover the input string. However, data with a small guessing space, such as weak passwords, can still be searched by hashing candidates and comparing. **Never use plain SHA-256 to store passwords**; use a password hashing scheme with unique salts and cost parameters, such as Argon2id/scrypt/bcrypt/PBKDF2 per system requirements.

### 5.2 What Real Security Encryption Requires

If the goal is **confidentiality**, use proper **encryption** such as AES-GCM (AEAD) with a secret key, a unique nonce per key scope, tag verification, and proper key management. Only then, when an API accepts only text, represent the ciphertext bytes with Base64 or hex:

~~~text
Plaintext bytes
    |
[AES-GCM encrypt: secret key + nonce + AAD]
    |
Ciphertext + authentication tag (binary bytes)
    |
[Base64 / hex, text packaging only]
    |
Text carrying ciphertext over JSON / config / protocol
    |
[Base64 / hex decode]
    |
Ciphertext + tag (binary bytes)
    |
[AES-GCM decrypt + verify tag]
    |
Plaintext bytes
~~~

A Base64 decoder **does not** verify the GCM tag, authenticate the sender, or decrypt plaintext itself. Keys, nonces, AAD, and format versions must be handled at the cryptographic layer. Never confuse **can decode** with **authorized to decrypt**.

For origin authentication and integrity, use a **MAC** such as HMAC or a **digital signature** per protocol. A Base64 string containing a signature does not become a signature because of Base64; there must be real signing and signature verification logic.

## 6. Formatting at Protocol Boundaries

### 6.1 HTTP Basic Authentication

An HTTP Basic Authentication header format can contain:

~~~text
Authorization: Basic <Base64 of user-id:password>
~~~

The **user-id:password** string can be recovered by Base64 decoding. Therefore, Basic Authentication **must only be used over a properly authenticated TLS connection**; never treat Base64 as password protection. Avoid copying the Authorization header into logs, error trackers, or debug dumps. Credential verification and authorization remain the system's responsibility, not Base64's.

### 6.2 JWT/JWS/JWE and Visible Information

A **compact JWS JWT** typically has three dot-separated Base64URL segments: header.payload.signature. The payload can be decoded and read without any private key. **The JWS signature detects tampering and authenticates under a key**, but does not keep the payload confidential. If confidentiality is needed, use a payload encryption mechanism designed for that purpose, such as JWE or appropriate application-layer encryption.

Do not place passwords, private keys, or sensitive personal data in a standard signed JWT payload assuming it is "hidden" because it is Base64URL. Decoding a token is not equivalent to verifying its signature, issuer, audience, expiration, and usage constraints.

### 6.3 JSON APIs, byte[], Key Fingerprints, and Ciphertexts

- **Binary in JSON:** Base64 is usually more compact than hex. Metadata should declare content type and encoding. Never guess from characters that merely look like Base64.
- **Digests/fingerprints/debugging:** hex is intuitive for comparing byte-by-byte. Fingerprint values may be public or sensitive depending on context.
- **Ciphertext stored in text DB columns:** Base64/hex supports text columns; real encryption and full metadata (key ID/version, nonce, tag, AAD if protocol requires) are still mandatory.
- **Raw binary:** if the protocol/database supports BLOB or binary frames, you can store/transmit bytes directly, avoiding text encoding overhead.
- **Random tokens:** high-entropy tokens can be generated with SecureRandom and represented in Base64URL. **Unpredictability comes from the entropy of the random bytes**, not from Base64URL. A token remains a bearer secret if anyone holding it can use it.

## 7. Unicode, Charsets, and Data Normalization

Binary encoding does not determine character encoding. If the initial data is a String, both sides must **agree on the charset**, typically UTF-8:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
~~~

These two lines illustrate part of a program, requiring a `text` variable and `import java.nio.charset.StandardCharsets` when used; this is not a standalone program.

A classic bug is using different charsets at the two ends, or calling **new String(rawBinaryBytes, UTF_8)** on arbitrary ciphertext/digests. Binary data can contain invalid UTF-8 byte sequences, causing replacement characters and breaking round-trips. For binary bytes, use Base64/hex first and parse back to bytes.

Even with the same UTF-8 charset, visually identical text is not guaranteed to have the **same bytes**. For example, **é** can be a single code point U+00E9 (UTF-8: **c3a9**) or **e** plus combining mark U+0301 (UTF-8: **65cc81**). If a system signs/hashes bytes, those two forms yield different inputs. Apply Unicode normalization only when the protocol consistently specifies it prior to hashing/signing; never arbitrarily normalize already-signed data or alter bytes after verification.

### 7.1 Do Not Confuse Canonicalization with Decoding

A decoder may accept multiple spellings representing the same bytes, depending on variant and padding. For instance, some Base64 strings with or without trailing **=** still decode to the same bytes. Never assume **comparing encoded strings** is equivalent to comparing bytes or safely verifying contents.

For tokens/signatures, always follow the exact **canonical form and signing input defined by the protocol**. Some protocols sign canonicalized payload bytes; others like JWS sign the encoded segments directly. Arbitrarily stripping padding, changing hex case, inserting newlines, or switching Base64 Basic ↔ URL-safe before verification can break signatures or create inconsistent-handling vulnerabilities.

If a protocol mandates a canonical representation, when accepting external strings you can **decode and re-encode with the canonical encoder**, compare against the original input, and handle mismatches per policy. This is a format check, **not a replacement for a MAC/digital signature**.

## 8. Designing Parsers and Handling Errors for Untrusted Data

Treat Base64/hex strings received from outside as **untrusted input**, even if syntactically valid. Recommended pipeline:

1. **Bound string size** before decoding to avoid oversized byte[] allocations. For large uploads, consider streaming and enforcing raw data size limits at the transport layer.
2. **Choose the exact variant/format**: Base64 Basic, URL-safe, MIME, or delimited hex. Document clearly in the API contract.
3. **Reject malformed data**: catch IllegalArgumentException from the decoder/parser at the input boundary and return a controlled error, without logging payloads/secrets.
4. **Bound decoded size** and validate structure: nonce, digest, key ID, field lengths, media type, version.
5. **Authenticate/verify integrity and authorization** per the application model. Decodable data does not mean trustworthy data.
6. **Handle sensitive data carefully**: avoid storing encoded strings in logs, metric labels, exception messages, URLs, or crash dumps; limit memory lifetime and unnecessary copies.

Error cases to separate clearly:

| Input | Expected outcome |
| --- | --- |
| Base64 Basic containing non-alphabet characters | Basic decoder fails; do not silently skip |
| Base64URL containing **+** or **/** instead of **-** or **_** | Use proper URL decoder, do not arbitrarily swap characters without a rule |
| Hex with odd digit count or characters outside 0–9/A–F/a–f | HexFormat.parseHex fails |
| Hex with **:** when default parser expects no delimiter | Select HexFormat.ofDelimiter(":") or reject per API contract |
| Decodes to byte[] but content shape mismatches (e.g., expected 32-byte digest, got 5 bytes) | Reject after type/length constraint checks |
| Valid Base64 decode, but ciphertext is modified or wrong tag | AEAD verification fails; do not trust plaintext |
| Valid token decode, but invalid signature or expired token | Token verification layer must reject |

**Do not** auto-fix data by dropping arbitrary characters, retrying multiple charsets, or truncating until a parser accepts it. Tolerant parsing should only be applied when the protocol specification requires it and its security implications have been evaluated.

## 9. Quick Comparison Guide

| Criterion | Base64 | Hex |
| --- | --- | --- |
| Representation unit | 6-bit group → one character | 4 bits → one character |
| Text size | ~4/3 of byte count, padding depends on variant | Exactly 2× byte count (no delimiter) |
| Byte-by-byte readability | Harder | Very convenient, two digits per byte |
| Special characters | Basic has + / and =; URL-safe has - _ | Usually only 0–9 a–f or A–F |
| Java 17+ | java.util.Base64 | java.util.HexFormat |
| Confidentiality/integrity security | None | None |
| Common uses | JSON, binary-to-text, token strings, text-wrapped ciphertext | Digests, fingerprints, safe diagnostic logs, addresses/buffers/debugging |

Example with 32 bytes of arbitrary data:

- Contiguous hex: **64 characters**.
- Padded Base64 Basic: **44 characters** (one trailing **=**).
- Unpadded Base64URL: **43 characters**.

**Choose based on protocol requirements and readability/size overhead.** If data requires confidentiality, select and implement an independent protection mechanism before considering representation formats.

## 10. Common Pitfalls and Fixes

1. **"I Base64-encoded the password/API key, so it's safe to commit to Git."** False: anyone can decode it. Use a secret manager/KMS, keep secrets private, and avoid committing them; store login passwords with proper password hashing.
2. **"Putting secrets in a URL after Base64URL hides them."** False: Base64URL does not obscure data. URLs end up in browser history, access logs, referrers, and monitoring. Use proper channels and auth mechanisms, never put long-lived secrets in URLs.
3. **"HexFormat on a checksum is enough against tampering."** False: hex is just representation. A public hash digest does not prove sender authenticity; use HMAC/digital signatures against intentional tampering.
4. **"Base64URL has no + / so the data must be securely encrypted."** False: URL-safe only changes the alphabet for syntax compatibility.
5. **"A JWT with three Base64URL segments is unreadable."** False for standard compact JWS: header/payload are readable after decoding; the signature authenticates rather than keeping them secret.
6. **"Base64 decoded cleanly, so the contents are trustworthy."** False: valid parsing only confirms syntax; authentication, authorization, and schema validation are still required.
7. **"String.length() tells me how many bytes to encode."** False for Unicode/UTF-8; use the length of byte[] after charset encoding.
8. **"Ciphertext can go straight into new String(bytes, UTF_8)."** False: ciphertext is arbitrary binary bytes. Use Base64/hex or binary transport.
9. **"MIME decoder is always the most flexible and safest choice."** False: it can skip non-alphabet characters; tokens require strict format enforcement.
10. **"Encoding two or three times is secure enough."** False: every public encoding layer can be reversed; it creates neither a secret key nor an authentication tag.

## 11. Practice Scenarios and Self-Check Questions

**Scenario A – Storing a SHA-256 digest:** a system has a 32-byte digest to store in a text column and inspect visually. 64-character hex is convenient; 44-character Base64 is more compact. Both represent the same digest, so SHA-256 security does not change with format. This digest is not a password hash designed for passwords.

**Scenario B – Token in a URL:** a system generates a 32-byte token using SecureRandom, then represents it as unpadded Base64URL, length 43 characters. Unpredictability comes from the 32 properly generated random bytes; the 43-character presentation adds no entropy. The token remains sensitive and requires controls on transport/storage, expiration, and authorization.

**Scenario C – API receiving ciphertext:** a JSON field holds Base64 of AES-GCM ciphertext. The server must Base64-decode, validate format/version/nonce, verify the tag with the right key, and only then use plaintext. Syntactically valid Base64 can still carry forged, corrupted, or unauthorized ciphertext.

**Self-check:**

1. Which key is required to read **SmF2YSE=**? → No key; it is the Base64 of the five UTF-8 bytes for **Java!**.
2. How many hex characters and padded Base64 Basic characters do 16 bytes become? → **32** hex characters and **24** Base64 characters.
3. Why does Base64URL differ from Base64 Basic? → Replaces **+ / ** with **- _** for better URL compatibility; does not change secrecy or authenticity.
4. How does HexFormat.of().formatHex(byte[]) differ from HexFormat.of().parseHex(String)? → One converts byte[] → hex text, the other converts valid hex text → byte[].
5. Can a Base64-encoded password be stored in a DB as a password hash? → No. Base64 is reversible; use password hashing with salt and appropriate cost.
6. If a Base64 value decodes cleanly and has 32 bytes, is it a valid SHA-256? → Only the length matches; you do not yet know the origin, calculation, or integrity of the value.
7. Why specify charset when converting text to byte[]? → The same characters under a different charset or Unicode normalization can yield different bytes, affecting round-trips, digests, and signatures.

**Lasting principle:** **Base64 and HexFormat are ways to write data as text.** They can wrap plaintext, ciphertext, hashes, signatures, or tokens, yet by themselves they **do not encrypt for secrecy, check integrity, authenticate, or grant access**. Security design must establish confidentiality/integrity/authentication requirements first; encoding is only the representation layer when bytes need to be stored, transmitted, or displayed.
