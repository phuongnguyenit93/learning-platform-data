# 3.1 Converting String to byte[] with Explicit Charset and Data Normalization Rules

In Java, `String` represents text; `byte[]` represents a sequence of bytes. Cryptography, hashes, HMACs, digital signatures, storage, and network protocols all ultimately process **concrete bytes**, not "characters that look alike". Therefore, before passing text into a cryptographic algorithm, you must explicitly decide the **character encoding (charset)** and **data normalization/canonicalization rules**. An inconsistent decision can produce different digests, cause signature verification to fail, lead to decrypted data mismatches, or create identity/authorization discrepancies.

For example, two strings that both display roughly as "Café":

- `"Café"`: the letter `é` is a single Unicode code point U+00E9.
- `"Cafe\u0301"`: the letter `e` U+0065 followed by the combining acute accent U+0301.

They may look identical, but **`String.equals` returns `false` and their initial UTF-8 bytes differ**. NFC normalization can bring them to an equivalent representation before UTF-8 encoding, if that is the policy agreed upon by both parties.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish `String`, UTF-16 code units, Unicode code points, user-perceived characters (*grapheme clusters*), and bytes.
2. Convert text using `StandardCharsets.UTF_8` deterministically, instead of relying on the environment's default charset.
3. Understand NFC, NFD, NFKC, and NFKD; choose the right normalization for **each data type**, and recognize cases where you should not normalize.
4. Detect and proactively handle invalid Unicode/UTF-8 input.
5. Design consistent input bytes for digests, HMACs, digital signatures, AEAD AAD, and storage; distinguish text normalization from protocol canonicalization.
6. Test byte outputs, cross-system compatibility, and tricky Unicode edge cases.

## 2. Representation Layers: From Reader to Byte

There are at least four layers to separate clearly:

| Layer | Unit or structure | Example | Key takeaway |
| --- | --- | --- | --- |
| Displayed text | Grapheme cluster; may consist of multiple code points | Letter `e` with acute accent | "One visible character" is not necessarily one element of `char[]` |
| Unicode | Code points such as U+00E9, U+0301, U+1F510 | `é`, combining mark, emoji | A code point is an abstract value; not identical to byte count |
| Java `String` | Sequence of **UTF-16 code units**; `char` is 16-bit | Emoji 🔐 requires a surrogate pair, i.e., two `char`s | `String.length()` counts code units, not code points |
| Byte | Sequence of octets according to the chosen charset | `é` becomes `C3 A9` when using UTF-8 | Cryptography operates on these exact bytes |

Be sure to distinguish:

- `String.length()`: number of **UTF-16 code units**.
- `String.codePointCount(0, s.length())`: number of **code points** in UTF-16 representation; does not accurately count grapheme clusters.
- `s.getBytes(StandardCharsets.UTF_8).length`: number of bytes after encoding; often differs from both numbers above.
- `byte[].length`: actual byte length to store, transmit, hash, or sign.

For example, the emoji **🔐** is a single Unicode code point, yet in Java it has `length() == 2` and when validly UTF-8 encoded it is **4 bytes** long. Never use `substring` or arbitrary `char`-index slicing in the middle of a surrogate pair.

### Charset Is a Mapping Rule, Not a UI "Font Set"

A charset specifies how characters map to bytes and vice versa:

```text
String (Unicode/UTF-16 in Java)
    -- [charset encoder: UTF-8] -->
byte[] (concrete octets)
    -- [charset decoder: UTF-8] -->
String (Unicode/UTF-16 in Java)
```

For the same text, different charsets can yield different bytes. For `"é"`:

- UTF-8: `C3 A9` — two bytes.
- UTF-16BE: `00 E9` — two bytes, big-endian.
- UTF-16LE: `E9 00` — two bytes, little-endian.

For non-ASCII characters, decoding with a **different charset** can produce mojibake, replacement characters, or errors. For purely binary data such as ciphertext, salt, nonce, keys, or digests, there is no "right charset" to arbitrarily convert them to a String; use binary formats or **Base64/hex** when a text representation is genuinely needed.

## 3. Java Rule: Specify Charset Explicitly

In modern applications, use UTF-8 whenever the protocol contract does not require another charset:

```java
import java.nio.charset.StandardCharsets;

String message = "Hello Java 🔐";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

This is an **illustrative code snippet** that can be placed inside a method with the import above. `StandardCharsets.UTF_8` is a built-in constant in the JDK, avoiding runtime charset name lookup. Similarly, the JDK provides `US_ASCII`, `ISO_8859_1`, `UTF_16`, `UTF_16BE`, and `UTF_16LE`; use them only when the protocol actually mandates them.

Avoid building security contracts on:

```java
byte[] bytes = message.getBytes();    // Charset not explicitly specified
String text = new String(bytes);       // Charset not explicitly specified
```

The no-argument overloads use the runtime's default charset. Java 18+ defaults to UTF-8 per JEP 400 in standard situations, whereas Java 17 and certain environments/configurations may differ; **protocols must not depend on this detail**. Even if every current machine uses UTF-8, still specify the charset in code and in the data specification.

Also avoid `getBytes("UTF-8")` when `StandardCharsets.UTF_8` is available, unless an API requires a charset name; the `Charset` object is strongly typed and avoids checked exceptions from looking up invalid charset names.

### Determinism Is Needed in Both Directions

For valid Unicode input and the same charset, UTF-8 encoding is deterministic. However, `new String(bytes, UTF_8)` **can replace invalid UTF-8 bytes with the replacement character U+FFFD**, and `String.getBytes(UTF_8)` can replace an invalid lone surrogate `char` with a replacement byte. This convenience is useful for displaying corrupted text, but can discard information about the input bytes.

If bytes must be strictly validated—for example in signing protocols, identifiers, message decryption, or security APIs—use `CharsetEncoder` / `CharsetDecoder` with `CodingErrorAction.REPORT` and handle `CharacterCodingException`. The full runnable example in Section 6 illustrates both directions.

**Rule:** binary input arriving from the network/files must be decoded under a published charset with a clear error policy; do not silently "fix" strings that you are about to feed into cryptographic verification.

## 4. Unicode Normalization: Same Display Meaning Does Not Guarantee Same Bytes

Unicode allows multiple canonically equivalent representations. Java provides `java.text.Normalizer` with four forms:

| Form | Type | Characteristics | Typical usage |
| --- | --- | --- | --- |
| **NFC** | Canonical composition | Decomposes by canonical equivalence, then composes into precomposed form where possible | Sensible default for many text fields requiring stable comparison |
| **NFD** | Canonical decomposition | Decomposes canonically equivalent characters into decomposed form | Text processing requiring separated diacritics, when there is a clear purpose |
| **NFKC** | Compatibility composition | Adds compatibility decomposition then composes; may merge representations with different meanings/styles | Certain carefully specified identifier policies, not a system-wide default |
| **NFKD** | Compatibility decomposition | Compatibility decomposition while keeping decomposed form | Specialized processing pipelines, not an automatic choice for secrets |

Java API:

```java
import java.text.Normalizer;

String nfc  = Normalizer.normalize(input, Normalizer.Form.NFC);
String nfd  = Normalizer.normalize(input, Normalizer.Form.NFD);
String nfkc = Normalizer.normalize(input, Normalizer.Form.NFKC);
String nfkd = Normalizer.normalize(input, Normalizer.Form.NFKD);
```

This is an illustrative snippet; assume `input` is a valid `String`. An easily verifiable example:

```text
"Café"           -> UTF-8 raw: 43 61 66 C3 A9
"Cafe\u0301"      -> UTF-8 raw: 43 61 66 65 CC 81

normalize(NFC) both   -> "Café"
UTF-8 after NFC       -> 43 61 66 C3 A9
```

Compatibility example: the ligature character `ﬃ` (U+FB03) remains `ﬃ` under NFC; under NFKC it can become the sequence `ffi`. Therefore, NFKC **can collapse representations that carry distinctions the application cares about**.

Do not infer that normalization solves all "looks alike" cases:

- Latin `a` and a visually similar letter from another script may look alike, but **are not the same code point** and do not automatically become one character after NFC.
- Uppercase/lowercase, whitespace, hyphens, line endings `\r\n`/`\n`, zero-width characters, URL percent-encoding, HTML entities, and JSON property ordering are **separate concerns**. NFC does not replace any of those canonicalization steps.
- `Normalizer` is not an API for detecting Unicode spoofing or identifier safety. Public IDs require character-set policies, confusable detection, and product-level name registration controls.
- A string may contain code points invalid at the Unicode scalar value level due to lone surrogates in Java; normalization does not replace strict encoding.
- Using `toLowerCase(Locale.ROOT)` if a case-insensitive policy exists is **not equivalent** to full Unicode case folding. Do not arbitrarily mix lowercase into cryptographic identifier rules unless both systems have agreed on the exact algorithm.

### Should Normalization Happen Before or After Encoding?

Normalization applies to **Unicode text**. Intentional pipeline:

```text
input text -> check field policy
           -> chosen Unicode normalization
           -> re-verify validity of canonical form
           -> strict UTF-8 encode
           -> byte[] for algorithm/protocol
```

If the source is UTF-8 bytes: **strict decode -> normalize per policy -> strict encode**. If you need to verify a signature over **raw body bytes**, verify the signature per spec on the raw bytes; do not decode/normalize and then assume the resulting bytes are still the body the sender signed.

*Idempotency* is a good property for a pipeline: after applying the same form to already-normalized data, repeating it should not keep changing the data. However, if the pipeline also includes trim, lowercase, collapse whitespace, URL decode, JSON serialization, or business rules, evaluate those steps **separately** and define their exact order.

## 5. Choose Policy Per Data Field, Do Not Apply One Function to Everything

**NFC + UTF-8 is not a "silver bullet."** Charset can be uniform across the protocol, but normalization should be based on field semantics and compatibility requirements.

| Input data | Suggested policy | Why |
| --- | --- | --- |
| Display name or search text | May store/compare in NFC if the contract specifies; keep original when needed | Reduces canonical differences while respecting user input |
| User-chosen account/tenant identifier | Dedicated identifier policy: form, allowed character set, case handling, length, reserved names, uniqueness | Prevents two visually similar/different names from passing inconsistent checks; mitigates impersonation |
| Machine-formatted document ID, transaction ID | Validate against explicit grammar (e.g., restricted ASCII); do not mutate outside rules | IDs are business keys and authorization inputs |
| Password, passphrase | Follow the published convention **exactly** at both registration and authentication; do not silently trim/lowercase/change form midway | Any byte difference yields a different verification result; policy changes require intentional migration |
| Data/JSON signed by another party | Sign/verify over **exact bytes** or the canonicalization published by the signature protocol | Two serializations of "the same data" often yield different bytes |
| Strings placed in AES-GCM AAD | Use defined bytes and field order, versioned; preserve reproducibility at decryption time | A single-byte AAD mismatch causes tag verification to fail |
| Base64 of ciphertext/nonce/salt/key | Base64-decode to bytes; do not Unicode-normalize binary content | Secrets/ciphertexts are bytes, not natural text |
| Email, internationalized hostname, or URL | Follow the **domain-specific** processing specification (IDNA, URL parser, case rules, etc.) | NFC alone does not cover full syntax, security, and comparison rules |

**Especially for passwords:** if a system uses a raw-string preservation policy, login must follow the exact same rules as registration. If business standards require normalization, both ends must agree from the start and plan data versioning. Do not silently strip diacritics, change case, trim, or apply NFKC just to make "login easier." Once the bytes are determined, passwords must pass through a **dedicated password hashing/KDF** with salt and cost parameters (such as Argon2id per policy), not standalone SHA-256, and never pass `getBytes` directly as an AES key.

For random tokens, keys, IVs/nonces, and ciphertexts, the right choice is **preserving bytes**. Base64/hex strings are a *transport encoding*, not something that turns binary data into "text needing normalization."

## 6. Complete Java 17+ Example: Charset, NFC, and Strict Error Handling

Save verbatim as **`UnicodeBytesDemo.java`** with the following content:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public class UnicodeBytesDemo {
    static byte[] strictUtf8(String text) throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(text));
        byte[] bytes = new byte[buffer.remaining()];
        buffer.get(bytes);
        return bytes;
    }

    static String strictDecode(byte[] bytes) throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    static byte[] canonicalBytes(String text) throws CharacterCodingException {
        if (text == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        return strictUtf8(Normalizer.normalize(text, Normalizer.Form.NFC));
    }

    static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    public static void main(String[] args) throws Exception {
        String composed = "Café";
        String decomposed = "Cafe\u0301";
        System.out.println("Same raw String: " + composed.equals(decomposed));
        System.out.println("Composed UTF-8: " + hex(strictUtf8(composed)));
        System.out.println("Decomposed UTF-8: " + hex(strictUtf8(decomposed)));

        byte[] a = canonicalBytes(composed);
        byte[] b = canonicalBytes(decomposed);
        System.out.println("NFC bytes equal: " + Arrays.equals(a, b));
        System.out.println("NFC UTF-8: " + hex(a));
        System.out.println("NFC digest equal: " + Arrays.equals(
                MessageDigest.getInstance("SHA-256").digest(a),
                MessageDigest.getInstance("SHA-256").digest(b)));

        System.out.println("NFKC of ligature: " +
                Normalizer.normalize("ﬃ", Normalizer.Form.NFKC));

        String emoji = "🔐";
        System.out.println("Emoji UTF-16 units: " + emoji.length());
        System.out.println("Emoji code points: " + emoji.codePointCount(0, emoji.length()));
        System.out.println("Emoji UTF-8 bytes: " + strictUtf8(emoji).length);
        System.out.println("UTF-8 round trip: " +
                composed.equals(strictDecode(strictUtf8(composed))));

        try {
            strictUtf8(String.valueOf((char) 0xD800));
            System.out.println("Malformed surrogate accepted");
        } catch (CharacterCodingException e) {
            System.out.println("Malformed surrogate rejected");
        }

        try {
            strictDecode(new byte[] {(byte) 0xC3, 0x28});
            System.out.println("Malformed UTF-8 accepted");
        } catch (CharacterCodingException e) {
            System.out.println("Malformed UTF-8 rejected");
        }
    }
}
```

Run commands in the directory containing the file, using JDK **17 or later**:

```bash
javac --release 17 UnicodeBytesDemo.java
java UnicodeBytesDemo
```

**Exact stdout:**

```text
Same raw String: false
Composed UTF-8: 436166c3a9
Decomposed UTF-8: 43616665cc81
NFC bytes equal: true
NFC UTF-8: 436166c3a9
NFC digest equal: true
NFKC of ligature: ffi
Emoji UTF-16 units: 2
Emoji code points: 1
Emoji UTF-8 bytes: 4
UTF-8 round trip: true
Malformed surrogate rejected
Malformed UTF-8 rejected
```

Explanation of each output group:

1. `equals` on the two raw `String`s is `false`. The hex strings differ because `C3 A9` encodes U+00E9, whereas `65 CC 81` encodes the two code points U+0065 and U+0301.
2. `Normalizer.Form.NFC` makes the bytes of these two strings equal. The final SHA-256 digests are also equal because **the input bytes are already equal**; SHA-256 does not normalize Unicode itself.
3. `NFKC` turns the ligature `ﬃ` into `ffi`. This is why you should not choose NFKC merely because it "looks more normal."
4. The emoji demonstrates that code units, code points, and byte count are three distinct quantities.
5. The encoder/decoder in `REPORT` mode rejects lone surrogates and invalid UTF-8 bytes, rather than silently losing the ability to inspect the original bytes.

`MessageDigest` in this example is used solely to **illustrate byte dependence**, not as a password-storage example. `HexFormat` was added in Java 17; on Java 11 this example cannot be used verbatim without changing the hex formatting portion.

### When Should Strict Encoding/Decoding Be Used?

There are two common modes:

- **Convenience:** `text.getBytes(UTF_8)`, `new String(bytes, UTF_8)`. Reasonable for already-validated text or display under a policy that permits replacement.
- **Validity preservation:** `CharsetEncoder/Decoder` with `REPORT`. Worth considering for identifiers, signatures, strictly parsed messages, and anywhere character replacement could alter a security decision.

Do not handle errors by "trying another charset" after UTF-8 fails, unless the protocol **genuinely has an explicit charset detection mechanism**. Falling back across multiple encodings can cause two components to interpret the same data differently.

## 7. Application in Hashes, HMACs, and Digital Signatures

Cryptographic primitives depend on exact bytes: `SHA256(byte[])`, `Mac.doFinal(byte[])`, and `Signature.update(byte[])`. Therefore, saying "both sides sign the text content" is insufficient as a specification. Both parties must agree on:

1. **Which data is signed:** raw HTTP body, a parsed string field, or a serialized canonical structure?
2. **Character encoding:** usually UTF-8; with or without BOM; are invalid UTF-8 bytes accepted?
3. **Normalization:** no normalization, NFC, or a specific profile/version?
4. **Structure and field boundaries:** field order, separators, escape rules, null/empty, lengths, how numbers and timestamps are formatted.
5. **Policy lifecycle:** version field in signed data, how legacy records are handled if policy changes.

### 7.1 Digest of a String

Example:

```text
Digest A = SHA-256( UTF8("Café") )
Digest B = SHA-256( UTF8("Cafe\u0301") )
Digest A != Digest B

Digest C = SHA-256( UTF8(NFC("Café")) )
Digest D = SHA-256( UTF8(NFC("Cafe\u0301")) )
Digest C == Digest D
```

This result does not come from "SHA-256 understanding Unicode"; SHA-256 only receives a byte sequence. For original data that must remain intact (uploaded files, artifacts, forensic logs), **hash the raw bytes**, do not normalize them. Only hash NFC-normalized bytes for strings defined under an NFC policy.

### 7.2 HMAC and Signatures for HTTP/JSON

Suppose a partner sends JSON:

```json
{"name":"Café","amount":10}
```

Another party might generate JSON with the same data but add whitespace, reorder fields, escape characters as `\uXXXX`, or write `10.0` instead of `10`. Those bodies can produce **different bytes**, even if a parser builds a similar structure. Unicode NFC **does not canonicalize JSON**.

Two valid approaches must be explicitly specified:

- **Sign raw body bytes:** the sender computes the HMAC/signature over the exact body bytes transmitted; the receiver verifies over the **intact received bytes**, before deserializing/re-serializing. Do not convert the body to a String and rebuild JSON to verify the signature.
- **Sign a canonical representation:** both sender and receiver follow the same canonical serialization specification (covering UTF-8, key ordering, numbers, escaping, and other constraints), along with a version. If using JSON Canonicalization Scheme (RFC 8785), understand its exact rules; **do not assume it normalizes Unicode strings to NFC**.

When concatenating multiple fields to build signing input, avoid unframed concatenation: `("ab", "c")` and `("a", "bc")` both yield `"abc"`. Use a canonical serialization with an unambiguous grammar or **length-prefixing** over bytes, together with domain separation for the signing purpose. A single `:` delimiter is insufficient if data is allowed to contain `:` without escaping.

**Error-prone scenario:** the sender signs `method + path + body` after URL-decoding once, while the receiver canonicalizes the path differently or decodes twice. This can cause signature mismatches or authorization bypasses. Unicode normalization does not replace protocol-specified URL, path, query, header, and request body canonicalization.

### 7.3 Timing and Security Result Comparison

Comparing signatures/HMACs must use the secure verification mechanism provided by the library/protocol. When comparing two fixed-format digest/MAC byte arrays in plain Java code, `MessageDigest.isEqual(a, b)` is more appropriate than `Arrays.equals` for security verification checks; however, the security of the whole workflow also depends on length analysis, protocol, key, algorithm, and steps prior to comparison. In the Section 6 example, `Arrays.equals` is used solely to illustrate two equal byte arrays or digests from public data; **it is not MAC verification logic**.

Do not roll your own cryptography, MAC, or ad-hoc canonicalization parser when maintained libraries and protocol standards already exist.

## 8. Encryption, Decryption, and AAD: Byte Consistency Over Years

When AES-GCM is used with **AAD** (*Additional Authenticated Data*), the ciphertext is protected by an authentication tag bound to the original AAD bytes. For instance, AAD may encode `tenantId`, `documentId`, and schema version. If the system encrypts using `UTF8(NFC(tenantId))` but decrypts using raw UTF-8 or reorders the fields, tag verification can fail even though the visible content looks identical.

Proper design:

- Define an **unambiguous binary format or serialization** for AAD; for example version + purpose domain + length-prefixed fields.
- Normalize only **text fields permitted to be normalized**, prior to serializing per spec; do not normalize `byte[]` ciphertext/nonce/salt/key.
- Store the version or sufficient metadata to reconstruct the AAD bytes when reading old records; if possible, store the exact authenticated AAD or a durable specified canonical representation.
- Use AEAD APIs properly, including the requirement **never to reuse a nonce with the same key** for AES-GCM. Choosing a charset/normalization **does not replace** those secure cryptographic usage requirements.

### Transporting Binary Data with Base64

**Fundamentally wrong:**

```java
String ciphertextAsText = new String(ciphertext, StandardCharsets.UTF_8);
```

This is an **anti-pattern illustration**, assuming `ciphertext` is a `byte[]`. Random ciphertext can contain invalid UTF-8 byte sequences. Forcing it into a String typically causes data loss; re-encoding it back will not recover the original byte sequence.

**Correct when storing/transmitting as text:**

```java
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(ciphertext);
byte[] restoredCiphertext = Base64.getDecoder().decode(encoded);
```

These lines are illustrative; the variable `ciphertext` already exists. Base64 is a **representation encoding**, not security encryption: anyone with the Base64 string can decode it. Do not log ciphertexts, keys, or tokens merely because they are Base64-encoded.

## 9. Security Risks from Inconsistent Canonicalization

A system may perform multiple checks on the same string: gateway, input filter, authorization, cache, DB, file system. If each layer interprets the string differently, data may be checked under one identity yet accessed under another.

Practical examples:

- The gateway checks authorization on a path decoded **once**, while a downstream service or proxy decodes it **a second time** and accesses a different path.
- The application stores `username` in NFC, but the uniqueness check compares against raw input. Two canonically equivalent representations can yield different decisions.
- The API authorizes `tenantId` using a trimmed string, while the DB query uses the untrimmed value; authorization and retrieval can diverge.
- A client compares Unicode using different case-insensitive rules than the server, then selects the wrong account or object.
- The application normalizes `\r\n` newlines to `\n` before checking HMAC while the partner signed raw bytes; valid signatures get rejected.

Prevention is not simply "normalize everything." The proper workflow:

1. **Read bytes according to an explicit protocol.** HTTP, JSON, path, query, and form data each have their own decoding rules.
2. **Parse structure and validate**, rejecting malformed encodings, ambiguous encodings, or out-of-bounds inputs per policy.
3. **Normalize at the appropriate business boundary**, only for fields governed by policy and in the exact defined order.
4. **Compare, authorize, store, and query using the same identifier form**, never raw in one layer and normalized in another.
5. **Preserve original data when required:** files, raw bodies for signature verification, forensic logs, receipts, third-party payloads; do not alter evidence before hashing.
6. **Version and run cross-system integration tests** if canonicalization is part of a long-term contract.

Avoid double decoding, double normalization combined with arbitrary whitespace edits; calling NFC repeatedly is stable, yet a chain of differing transformations across layers can create discrepancies. During authentication/authorization, treat incoming data as untrusted even over TLS.

## 10. Managing Data Contracts in Multi-Language Integrations

Java, JavaScript, Python, Go, and other SDKs access Unicode and bytes differently. Do not hand a partner a vague statement like "encode strings as UTF-8"; publish a **canonicalization profile** with test vectors:

| Attribute | Example specification description |
| --- | --- |
| Name and version | `canonical-text-v1` |
| Data source | `displayName` field decoded from UTF-8 JSON |
| Unicode form | NFC, no trim, no case folding |
| Output charset | UTF-8, no BOM |
| Invalid input | Reject malformed UTF-8 and invalid Unicode scalars |
| Limits | UTF-8 byte length and normalized character count per policy; clearly distinguish units |
| Other transforms | Do not alter newlines, HTML/URL escapes, or punctuation |
| Multi-field serialization | Dedicated canonical format defining order, null/empty, length-prefix |
| Policy updates | Create a new version; keep reading v1 data during migration |

Even when the same Unicode normalization form is named, long-lived systems should document library/runtime details and Unicode version compatibility when needed. Unicode normalization provides standard stability guarantees, yet never skip **cross-platform testing** of the entire pipeline (including parser, validation, case mapping, JSON, and storage).

A minimal *golden vector* should include:

```text
Input visible: Café
Unicode source A: U+0043 U+0061 U+0066 U+00E9
Unicode source B: U+0043 U+0061 U+0066 U+0065 U+0301
Policy: NFC + UTF-8 strict
Expected canonical hex for both: 436166c3a9
```

Golden vectors should be executed by both producer and consumer. To test cross-language signatures, add the HMAC/signature output for a **dedicated test-only** key and message, never using real keys.

## 11. Testing and Edge-Case Handling

A good test suite covers both correctness and cases likely to cause two systems to disagree:

| Input / scenario | What to verify |
| --- | --- |
| ASCII `Hello` | UTF-8 is exact `48 65 6C 6C 6F`; stable round trip |
| `é` vs `e\u0301` | Raw bytes differ; NFC then UTF-8 must match |
| Ligature `ﬃ` vs `ffi` | NFC does not force equality; NFKC may merge; which policy is permitted? |
| Emoji, non-BMP characters | `String.length()` differs from code point count and byte length; no slicing mid-surrogate |
| String with lone surrogate | Strict encoder rejects; do not silently substitute bytes before signing |
| Invalid UTF-8 bytes, e.g. `C3 28` | Strict decoder rejects; clear HTTP status/error handling defined |
| Strings with NUL, tab, newline | Parser, validation, and serialization share consistent rules |
| `\r\n`, `\n`, leading/trailing spaces | Transform only if protocol/field profile permits |
| Visually similar usernames across scripts | Unicode NFC does not solve confusables/homographs; identifier policy required |
| `null`, empty string, whitespace-only | Distinguish data semantics, avoid ambiguity with missing fields |
| Ciphertexts, nonces, digests with arbitrary bytes | Base64 decode/encode round trip; never use `new String(ciphertext, UTF_8)` |
| Semantically identical JSON with different serialization | Raw-body signature differs; canonical JSON matches only if both follow the same standard |
| Multiple services on different versions | Golden vectors match across languages and deployment times |
| Very large input | Check size limits before and after normalization; prevent excessive CPU/memory usage |

When logging errors, you may record **error codes, request IDs, and sanitized length/encoding type info**; avoid printing raw passwords, tokens, keys, sensitive payloads, or Strings containing control characters. If debugging problematic bytes is necessary, use only synthetic test data or controlled observability mechanisms.

### Separating Encoding Errors from Normalization Errors

- `MalformedInputException`/`CharacterCodingException`: invalid input at the character encoding/decoding layer.
- Unicode normalization: a policy-driven **representation transform**, not implicitly a validation step.
- Validation: character restrictions, length, structure, and business rules. Apply on the form the system stores/compares, while also bounding raw input size to prevent abuse.
- Authorization: access decisions based on an authenticated identity and a consistent canonical representation. Cannot be substituted by charset conversion.

On error, reject explicitly instead of silently fixing the input and letting signatures or identities be verified against a different string.

## 12. Common Mistakes and Fixes

**1. Using the default charset:** `getBytes()` / `new String(bytes)` causes environment-dependent behavior. Fix with a `Charset` explicitly stated in the contract, usually `StandardCharsets.UTF_8`.

**2. Assuming visually identical Strings have identical bytes:** precomposed characters and combining mark sequences can yield different bytes. Fix with a per-field equivalence/normalization policy, or intentionally preserve raw bytes if required.

**3. Using `String.length()` to bound transmitted bytes, DB column size, or keys:** UTF-8 is variable-length, and emojis use surrogate pairs. Fix by measuring the right unit, especially `strictUtf8(text).length` after normalization, plus raw input limits to prevent abuse.

**4. "Normalizing everything for equivalence" via NFKC/lowercase/trim:** can alter names, passwords, and identifier keys. Fix with an intentional policy and test pairs that might be collapsed into one.

**5. Decoding ciphertext as UTF-8 for convenience:** arbitrary bytes are not text. Fix by using `byte[]`, Base64, or hex at the transport layer.

**6. Verifying JSON HMAC by re-serializing an object:** whitespace/order/escaping/numbers can change. Fix by signing the exact raw bytes or implementing the agreed protocol canonicalization.

**7. Normalizing content before verifying a raw-body signature:** alters bytes and breaks signatures in some cases. Fix by verifying at the exact representation layer required by the protocol.

**8. Letting encoder/decoder silently replace bad data:** replacement can turn corrupted input into different bytes and mask issues. Fix by using `REPORT` when byte accuracy is a security requirement.

**9. Changing policy mid-flight without versioning:** old signatures, old AAD records, or old usernames may fail verification. Fix with versioned policies, migration, and golden vectors.

**10. Letting validation and lookup use two string forms:** authorization checks a different ID than the one retrieved. Fix with one end-to-end defined representation, tested at parser–authorization–storage boundaries.

## 13. Hands-On Exercise

A Java API receives a document creation request with `title` (user-facing), `externalId` (partner ID), and `payload` (JSON signed by the partner using HMAC over the raw request body).

Design the solution before writing code:

1. For `title`, decide whether to use NFC or preserve verbatim; define the UTF-8 bytes for storage/search and a golden vector for `é` vs `e\u0301`.
2. For `externalId`, publish the grammar, validation, canonicalization, and case sensitivity; ensure uniqueness checks, cache keys, authorization, and DB lookups consistently apply the exact same rules.
3. For `payload`, describe how to capture **raw request body bytes** and verify the HMAC **before re-parsing JSON**, assuming the sender's contract signs raw bytes. Test that adding a single space to the body changes the HMAC.
4. Specify behavior when a request contains malformed UTF-8 or a `String` input has a lone surrogate; write unit tests for the strict decoder/encoder.
5. Test two-way round trips `UTF8 -> String -> UTF8` with valid text and `byte[] -> Base64 -> byte[]` with random data. Explain why the first round trip must not be applied to ciphertext.
6. If the `title` policy later changes from "preserve verbatim" to NFC, specify how to handle existing records, lookup keys, already-signed data, and rule versioning.

**Completion criteria:** know **exact bytes** being hashed/signed/encrypted, **why** a string is or is not normalized, when raw bytes must be preserved, and how to prove Java and partner systems produce identical output.

## References

- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets.
- [Java 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC, NFD, NFKC, NFKD.
- [Java 17 — CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html) and [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): handling invalid data.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): canonical and compatibility definitions.
- [RFC 3629 — UTF-8](https://www.rfc-editor.org/rfc/rfc3629): UTF-8 representation rules.
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785): canonical JSON when deterministic serialization is needed.
