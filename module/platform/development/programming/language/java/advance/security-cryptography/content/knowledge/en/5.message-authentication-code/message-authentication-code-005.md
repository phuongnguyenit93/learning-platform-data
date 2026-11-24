# 5.5. Aligning Input Data, Field Ordering, and Tag Format Between Two Parties

In a system using a **Message Authentication Code (MAC)**, having both parties choose `HmacSHA256` and hold the same secret key is **still not enough** for authentication to succeed. Sender and receiver must also compute the MAC over the **exact same byte sequence**, following the **same field ordering and encoding rules**, and agree on **how the authentication tag is represented, transmitted, and verified**.

A seemingly small mismatch—such as swapping two JSON fields, using different newline characters, formatting monetary amounts differently, or confusing standard Base64 with Base64URL—can cause both sides to compute different tags. More dangerously, an ambiguous concatenation rule can allow **two distinct business messages to produce the same byte sequence before MACing**, even when HMAC itself is completely secure.

Lesson objectives:

- Identify the exact bytes that must be authenticated, required fields, and the business meaning of each field.
- Design a **deterministic, unambiguous** input format across two languages/systems.
- Specify field ordering, UTF-8, field lengths, numeric types, version, domain, and handling of missing/null/empty values.
- Distinguish **raw byte tags** from hex/Base64/Base64URL strings on the wire.
- Write and verify an HMAC-SHA-256 contract with **reproducible test vectors** in Java 17+.
- Recognize bugs leading to MAC mismatches, algorithm/key confusion, replay, and missing authorization.

## 1. A MAC Computes a Tag Over Bytes, Not Abstract "Meaning"

Given a symmetric secret key `K` and a message as bytes `M`, the operation takes the form:

\[
T = \operatorname{MAC}_{K}(M)
\]

The receiving partner computes `MAC_K(M_received)` and checks whether the result matches the received tag.

```text
Sender                                          Receiver
------                                          --------
Business data                                   Business data
        |                                               |
Canonical encoding (shared rules)               Canonical encoding (same rules)
        |                                               |
Exact byte sequence M                           Exact byte sequence M'
        |                                               |
MAC(K, M)                                       MAC(K, M')
        |                                               |
Tag bytes T -------- wire encoding ----------> Decode tag -> T'
                                                        |
                                               Compare T' with MAC(K, M')
                                                        |
                                               Process only if all checks pass
```

For authentication to succeed meaningfully, both parties must agree on at least:

1. **Key and key-usage policy**: which key bytes, which `keyId`, which purpose, who is allowed to hold the key, and which identity is bound to the key.
2. **Algorithm and configuration**: e.g., `HmacSHA256` producing a full 32-byte tag; truncation rules if any.
3. **Input/schema**: which fields must be protected (including tenant, resource, action, amount, requestId), their order, and data types.
4. **Canonical encoding**: exact input bytes, UTF-8, lengths, integer endianness, Unicode handling, JSON, and nulls.
5. **Tag wire format**: raw bytes, hex, Base64, or Base64URL; padding, length, letter casing, and where the tag is placed.
6. **Version, context, and rejection rules**: which protocol the message belongs to; whether replay protection, time bounds, authorization checks, and error handling apply.

**Determinism of HMAC**: given the same algorithm, same key bytes, and same message bytes, the tag will match. If the tag differs, do not rush to blame the algorithm; inspect the bytes fed into the MAC first.

### 1.1. HMAC differs from an unkeyed hash

`SHA-256(M)` is a public digest; anyone knowing `M` can recompute it. `HMAC-SHA256(K, M)` uses a **secret `K`** in a standardized MAC construction, letting another party holding the same key verify integrity and that the tag originated from the group knowing the key.

When an HMAC key is shared among multiple services, a valid tag proves **the message is consistent with the shared key**, without uniquely identifying which service computed the tag. To tie it to an identity, the receiver must map the key to a principal and enforce business authorization. A MAC is not a public-key digital signature and has no public verification mechanism like signatures.

**AEAD** modes such as AES-GCM also produce an authentication tag, but a GCM tag depends on the nonce, ciphertext, and AAD under AEAD rules. Never substitute an HMAC tag for a GCM tag, or assume "a tag is just a piece of text so any two tags are interchangeable."

## 2. "Same Data" Yet Different Bytes

A MAC sees **bytes**; it does not understand object structures, JSON, monetary meaning, or users. The "nearly identical" pairs below can yield different bytes:

| Same Business Intent, Different Representation | Example | Impact |
| --- | --- | --- |
| JSON property order | `{"amount":100,"currency":"USD"}` vs `{"currency":"USD","amount":100}` | When signing raw JSON bytes, tags differ |
| JSON whitespace | `{"a":1}` vs `{ "a": 1 }` | Different bytes despite logically equivalent objects |
| Line endings | LF `\n` vs CRLF `\r\n` | Different hash/MAC |
| Encoding | UTF-8 vs UTF-16LE | Different bytes |
| Combining Unicode | `é` (U+00E9) vs `e` + U+0301 | May render identically yet have different UTF-8 bytes |
| Monetary numbers | `1`, `1.0`, `01`, `1e0` | Different strings; JSON numbers can also suffer type/rounding differences |
| Timestamps | `2026-10-31T12:00:00Z` vs `2026-10-31T19:00:00+07:00` | Same instant in time yet different strings |
| Base64 | `+`/`/`/`=` vs `-`/`_` without padding | Same binary data yields different wire text |
| Null/missing/empty | Field omitted, `null`, `""` | Usually three distinct business states |
| URL | `/a%2Fb` vs `/a/b`; different query order | May carry different semantics across proxies/routers |
| HTTP headers | Ordering, header name casing, whitespace, merged headers | Canonical string may differ |

Example:

```json
{"tenant":"shop-1","amount":1299}
```

and

```json
{
  "amount": 1299,
  "tenant": "shop-1"
}
```

may represent the same business object, yet they are not the same byte sequence. If the sender computes the MAC over formatted JSON while the receiver parses and re-serializes in a different order, the HMAC will not match.

There are **two valid strategies**, and you must pick one consistently:

- **MAC the exact transmitted bytes:** the receiver computes over the exact transmitted payload bytes without re-serializing before verification. Clearly specify when bytes are captured, e.g., before/after compression or content transformation. This avoids re-canonicalizing JSON, though the MAC must still cover relevant context outside the body if required.
- **MAC a canonical representation:** both parties transform logical data into a single byte encoding per a published schema. Pick length-prefixed binary, a deterministic CBOR profile, or a suitable canonical JSON rule; both sides must follow the exact same rule.

Never mix the two strategies—for instance, sender signing raw JSON while receiver signs a re-parsed object.

## 3. Field Ordering and Preventing Ambiguity

A dangerous rule is direct string concatenation:

```text
M = tenantId + requestId

tenantId = "ab"; requestId = "c"   -> "abc"
tenantId = "a";  requestId = "bc"  -> "abc"
```

Two **different** messages produce **the exact same input bytes**. Thus they share the same HMAC under the same key, **without breaking HMAC or finding a cryptographic collision**. This is a formatting bug prior to MAC computation.

Joining fields with a simple delimiter is also unsafe if that delimiter can appear in the data. For example:

```text
tenantId + "|" + requestId

("a|b", "c") -> "a|b|c"
("a", "b|c") -> "a|b|c"
```

Good solutions:

1. **Length prefix before each field:** write a fixed 4-byte length followed by that exact number of bytes; a parser can unambiguously recover boundaries.
2. **Standardized structured encoding:** use a specified deterministic CBOR / canonical JSON profile and cross-test it.
3. **Strict delimiter + escaping:** only if the protocol publishes unambiguous escape rules and tests them thoroughly; avoid inventing ad-hoc escaping.
4. **Fixed-type/fixed-width fields:** 64-bit integers, version byte, boolean 0/1, bounded-domain enums.

### 3.1. Concrete binary contract for a payment example

Let's choose an illustrative profile `PAYMENTS-HMAC-V1`, containing fields in exact order:

| Position | Field | Encoding | Notes |
| --- | --- | --- | --- |
| 1 | `version` | 1 byte with value `0x01` | Fixed per protocol version |
| 2 | `domain` | 4-byte length + UTF-8 bytes of `payments.request` | Prevents reusing the same tag in another protocol |
| 3 | `tenantId` | 4-byte length + UTF-8 bytes | Binds the tenant |
| 4 | `requestId` | 4-byte length + UTF-8 bytes | Used by the replay/idempotency layer |
| 5 | `amountMinor` | Signed 64-bit integer, **big-endian**, exact 8 bytes | 1299 means 12.99 units when the currency has 2 decimal places |
| 6 | `currency` | 4-byte length + UTF-8 bytes | e.g. `USD`, validated/normalized per policy |
| 7 | `tag` | **Not** in MAC input | Compute HMAC after serializing the 6 fields above |

Where:
- Each length prefix is a non-negative value written via 4-byte big-endian `writeInt` and capped at **65,535 bytes** in this example.
- Java's `writeLong` uses **8 bytes big-endian**. Other languages must match the exact byte count and signed representation; do not send monetary amounts as `double` or locale-formatted strings.
- Strings are encoded using `StandardCharsets.UTF_8`. In this illustration, no implicit Unicode normalization is performed. Real systems must clearly specify their input accept/reject/normalize policy prior to serialization.
- `version` and `domain` make explicit that this message is a "payment request, v1", preventing the same byte sequence from being misinterpreted as another message type (cross-protocol confusion).
- `tenantId` and `requestId` **must be verified by the receiver against trusted identity and business state**, never treating client-declared values as automatically authorized.

Byte layout:

```text
01
00000010 | UTF-8("payments.request")
00000008 | UTF-8("tenant-A")
00000005 | UTF-8("req-7")
0000000000000513
00000003 | UTF-8("USD")
   |
   +--> HMAC-SHA256(K, all preceding bytes) => 32 tag bytes
```

Lengths: `0x10 = 16` bytes for `payments.request`; `0x08 = 8` for `tenant-A`; `0x05 = 5` for `req-7`; `0x0513 = 1299` in the 8-byte numeric field.

Fixed input pair used as a test vector:

```text
version = 1
domain = payments.request
tenantId = tenant-A
requestId = req-7
amountMinor = 1299
currency = USD
key = UTF-8("0123456789abcdef0123456789abcdef")  // only for a public demo

Canonical input (hex):
01000000107061796d656e74732e726571756573740000000874656e616e742d41000000057265712d37000000000000051300000003555344
```

**Never use this public fixed key in production.** It is a fixture so both sides can compare byte-for-byte in this lesson, like a test vector.

### 3.2. Principles for missing values and data types

The protocol definition must answer for every field:

- Missing **required** fields must be rejected before computation/verification; never silently treat them as empty strings.
- If **nullable** is meaningful, add a state marker byte or an encoding that clearly distinguishes `absent/null/value`.
- If **arrays** are allowed, write the count and encoding of each element, and specify whether order is significant or must be sorted. If sorted, use the exact same byte/standard comparator, never machine-specific locale.
- If **maps** are allowed, specify key ordering, duplicate key handling, and Unicode rules. Never rely on `HashMap` iteration order as a wire contract.
- For **decimals**, choose integer minor units (`amountMinor`) or an explicit canonical decimal format; do not rely on `BigDecimal.toString()` across systems without a contract.
- For **timestamps**, prefer UTC epoch in a fixed unit, such as signed int64 milliseconds; if choosing ISO 8601, enforce a single exact format including fractional digits and timezone.

Out-of-domain data must be rejected cleanly. **Canonicalization does not replace schema validation or authorization checks.**

## 4. For JSON and HTTP, Decide the Signed Byte Domain

### 4.1. JSON can be used, but needs a specific profile

If choosing canonical JSON, do not merely say "sort keys." Publish a specific standard, such as **JSON Canonicalization Scheme (JCS, RFC 8785)** when applicable: rules for property ordering, string and number serialization, and JSON/I-JSON constraints. JSON interoperability also requires attention to large integers beyond IEEE 754 exact precision, duplicate properties, Unicode, escape sequences, and data types.

Traditional example:

```json
{"currency":"USD","amount":1299,"requestId":"req-7"}
```

Do not assume an arbitrary Java or JavaScript serializer will emit identical bytes merely because both produce logically equivalent JSON. If choosing JCS, use a compliant implementation and cross-system test vectors. If exact 64-bit integers are needed between Java and JavaScript, you may need **canonical numeric strings** or a binary format supporting deterministic integers.

Especially when verifying signatures/MACs on raw JSON, the application parser **should not accept ambiguous forms** (such as duplicate properties handled differently) that cause the verified bytes and executed object to carry different semantics.

### 4.2. For HTTP requests

When authenticating APIs with a MAC, "signing the body" is only part of it. The contract must specify which details affect the request's meaning:

- Method (`POST` vs `GET`) and which path, route, and query parameters are included?
- Which host, tenant, resourceId, user/service principal, content type, and body must be protected?
- Is there a MAC-protected timestamp, nonce, or requestId?
- At which layer are body bytes captured: after parsing, before compression, or after reverse proxy transformations?
- If a proxy reorders headers, rewrites URLs, or converts line endings, will both parties still produce the same canonical representation?

Do not sign arbitrary uncontrolled headers hoping client and server agree, as proxies can add or remove headers. Nor should you omit meaningful data: if a MAC protects only the body while the route changes from `/orders` to `/refunds` without binding, the receiver could interpret the request as a different action.

For HTTP, consider using an established request-signature standard and clearly publishing the canonicalization profile. If designing an internal protocol, maintain fixtures from both sides and test across proxy/HTTP stack variations.

## 5. Tag Bytes and Wire Representation of Tags

With **full HMAC-SHA256**, `Mac.doFinal(...)` outputs **32 bytes = 256 bits**. Ways to represent the same tag:

| Representation | Size for a 32-Byte Tag | Characteristics |
| --- | --- | --- |
| Raw bytes | 32 bytes | Suitable for binary protocols; not arbitrary UTF-8 text |
| Lowercase hex | 64 ASCII characters | Easy to read/debug, twice the size of raw bytes |
| Standard Base64 with padding | 44 characters (typically ends with `=`) | Uses `+` and `/`, includes padding |
| Base64URL without padding | 43 ASCII characters | Uses `-` and `_`, convenient for URLs/headers |

Because **the exact same 32 bytes** have multiple encodings, both sides must agree on:

1. Permitted wire format (e.g., Base64URL without padding), exact alphabet, and padding rules.
2. Case sensitivity for hex strings; are uppercase letters allowed? If so, specify consistently.
3. Decoded tag length (e.g., **exactly 32 bytes**). Never compare string lengths instead of validating byte lengths.
4. Are whitespace, newlines, `0x` prefixes, or separators allowed? Pick a single canonical form and reject all others.
5. Which field carries the tag, whether duplicate headers/fields with the same name exist, and whether URL/form decoding alters it?
6. Rejection policy for invalid/expired tags and error responses that do not leak internal details.

**Never** convert raw tag bytes using `new String(tagBytes, UTF_8)`: a tag is binary data and is not guaranteed to form valid UTF-8. Nor should you compare a sender's hex string with a receiver's Base64 string: decode according to the profile before comparing.

### 5.1. Should you truncate an HMAC tag?

Some protocols specify truncating tags to `t` bits to save bandwidth. That is a **protocol decision** with forgery-resistance tradeoffs, not "chopping off a few Base64 characters for brevity." When truncating, specify the exact number of **leading bits/bytes**, encoding rules, minimum length, attempt limits, and threat model. For new designs, prefer **full 32-byte HMAC-SHA256** unless a specific standardization constraint requires truncation.

If an adversary gets many online guesses against a short tag, guessing odds grow with attempts. Rate limits, timeouts, nonce/replay checks, and safe failure handling remain essential. Never let the client choose the tag length and compare only as many bytes as the client sends.

### 5.2. Safe tag verification

In principle, verify by:

1. Validating framing, format, length, and allowed algorithm/version; rejecting malformed data.
2. Resolving the key from a trusted source and policy configuration; **never trust a self-declared `keyId` as identity proof**.
3. Re-serializing the exact canonical bytes from validated input data.
4. Recomputing HMAC over all bytes, using a byte-comparison API with minimal content-dependent timing, such as `MessageDigest.isEqual(...)`, once both digests have the expected length.
5. Only after the MAC passes, evaluating freshness/replay and business authorization before causing side effects.

Avoid `String.equals(...)` or `Arrays.equals(...)` as the final comparison between **the expected tag and a client-supplied secret tag**, as ordinary comparisons can vary in timing based on content/mismatch position. Other requirements around authentication, error handling, and networking still apply; a safe comparison alone does not guarantee the entire protocol leaks no information.

## 6. Java 17+: HMAC Test Vector Over Canonical Binary Encoding

The following example fixes the algorithm, ordering, and format; HMAC results for an identical request must be reproducible across implementations.

Create `MacWireDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MacWireDemo {
    record Payment(String tenantId, String requestId, long amountMinor, String currency) {}

    // Public demo key for reproducing a test vector; never use in production.
    private static final byte[] KEY = "0123456789abcdef0123456789abcdef"
            .getBytes(StandardCharsets.UTF_8);

    private static void field(DataOutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > 65_535) throw new IllegalArgumentException("field too long");
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] canonical(Payment p) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeByte(1);                    // protocol version
            field(out, "payments.request");      // domain separation
            field(out, p.tenantId());
            field(out, p.requestId());
            out.writeLong(p.amountMinor());      // 8 bytes, big endian
            field(out, p.currency());
        }
        return buffer.toByteArray();
    }

    static byte[] hmac(Payment p) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(KEY, "HmacSHA256"));
        return mac.doFinal(canonical(p));
    }

    static String base64url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static boolean verify(Payment p, String wireTag) throws Exception {
        byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(wireTag);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        if (received.length != 32 || !base64url(received).equals(wireTag)) return false;
        return MessageDigest.isEqual(hmac(p), received);
    }

    public static void main(String[] args) throws Exception {
        Payment original = new Payment("tenant-A", "req-7", 1299, "USD");
        String tag = base64url(hmac(original));
        System.out.println("Input hex: " + HexFormat.of().formatHex(canonical(original)));
        System.out.println("Tag (base64url): " + tag);
        System.out.println("Tag bytes: " + Base64.getUrlDecoder().decode(tag).length);
        System.out.println("Original verified: " + verify(original, tag));
        System.out.println("Amount changed verified: "
                + verify(new Payment("tenant-A", "req-7", 1399, "USD"), tag));
        System.out.println("Tenant changed verified: "
                + verify(new Payment("tenant-B", "req-7", 1299, "USD"), tag));
        System.out.println("Malformed tag verified: " + verify(original, "invalid+tag"));
        System.out.println("Same request replay verified: " + verify(original, tag));
    }
}
```

Compile and run:

```bash
javac MacWireDemo.java
java MacWireDemo
```

Exact stdout of the example on JDK 17+:

```text
Input hex: 01000000107061796d656e74732e726571756573740000000874656e616e742d41000000057265712d37000000000000051300000003555344
Tag (base64url): nEOzXhbbnYCVX0rn1leWKWA-OR9mZLAraX4FJOfZArU
Tag bytes: 32
Original verified: true
Amount changed verified: false
Tenant changed verified: false
Malformed tag verified: false
Same request replay verified: true
```

**Explanation of essential points:**

- `canonical()` is the **byte contract**, not implicit Java record serialization. DataOutputStream writes in a fixed order; `writeInt` is a 4-byte length prefix, `writeLong` is an 8-byte big-endian integer.
- `field()` uses the UTF-8 byte length, **never Java's `String.length()`** because `String.length()` counts UTF-16 code units. For non-ASCII characters, the UTF-8 byte count generally differs from Java string length.
- `Mac.getInstance("HmacSHA256")` computes **HMAC-SHA256**; `SecretKeySpec` only represents key bytes and algorithm name and does not itself protect the key from disclosure.
- `base64url()` enforces the URL-safe alphabet without padding. The receiver decodes, checks for exact 32 bytes, and re-encodes to require **canonical wire representation** before comparing.
- `MessageDigest.isEqual(...)` compares **tag bytes**, not encoded strings or plaintext messages.
- Changing the amount from 1299 to 1399, or changing the tenant, produces different MAC input so `verify` returns `false`.
- `"invalid+tag"` contains `+`, which is not in the Base64URL alphabet, and is rejected. Other invalid wire encodings/lengths must likewise be rejected.
- **Worth noting:** the line `Same request replay verified: true` is **expected**. HMAC does not prevent replay on its own. Two identical requests yield the same tag; a real server must enforce `requestId` through freshness, anti-replay, or stateful idempotency.
- The hardcoded key, incomplete business validation, and lack of a replay store are intentional because the example demonstrates **the byte contract and tag format**. In real environments, load keys from a secret management system, validate input domains, and enforce authorization and time limits.

### 6.1. How to create a test vector for a second system

Send the team implementing in another language **all** of the following:

1. Protocol version and byte layout from Section 3's table, including byte order and length prefixes.
2. Exact input values: `tenant-A`, `req-7`, integer `1299`, `USD`.
3. Demo key of exact **32 ASCII bytes**, not a hex-decoded key: `0123456789abcdef0123456789abcdef`.
4. Canonical input in hex: the entire string must match byte-for-byte before computing HMAC.
5. HMAC-SHA256 tag in Base64URL **without padding**: `nEOzXhbbnYCVX0rn1leWKWA-OR9mZLAraX4FJOfZArU`.
6. Negative tests: changed amount/tenant, wrong key, wrong version, swapped field order, malformed tag, and wrong tag length.

When one party fails to produce the right tag, the first step is comparing **hex of the canonical bytes**, then checking key bytes, algorithm, and tag encoding. Never "make it work" by silently trimming, sorting, or converting Base64/hex on the server.

### 6.2. Same data model yet different order = different MAC input

Suppose a client writes fields in the order `tenantId, requestId, currency, amountMinor`, while the server writes `tenantId, requestId, amountMinor, currency`. Even with identical business values, the bytes will differ; the client's tag cannot verify under the server's rules.

Similarly, if the client writes 4-byte length prefixes in little-endian while the server reads big-endian, the parser may misread lengths or verify HMAC over different bytes. **Endianness is part of the protocol**, not a runtime detail left to chance.

Do not fix this by having the server try multiple orderings, multiple encodings, or multiple algorithms until one tag passes. A "try everything" mechanism can open ambiguous representations and defeat versioning and security policy.

## 7. Boundaries Between Canonicalization, Integrity, Identity, and Replay

### 7.1. A MAC proves the protected bytes, not everything

A tag only protects **the fields actually included in the input**. If amount is signed while currency is not, an adversary may find a way to change `USD` to another currency undetected unless the server binds currency elsewhere.

For example, in a multi-tenant system:
- `tenantId` must be inside the MAC input **and** the server must verify that this tenant is permitted to use the current key/principal.
- `resourceId` or authorization-relevant routes should also be bound when they affect business semantics.
- Fields like `keyId` and `algorithm`, if carried in the envelope, must follow a trusted profile: `keyId` looks up an authorized key, and algorithm is chosen by server allowlist/policy; never let the client force verification under another algorithm.
- `version` must be authenticated or included in the signed/MAC input to prevent reinterpreting the payload while keeping the tag.

**Integrity-protected data is not automatically business-trusted data.** If a valid client holds an HMAC key yet has no permission to pay for another tenant, the MAC can still verify; authorization must independently check permissions.

### 7.2. A valid MAC does not prove a request is fresh

Imagine a transfer command with the same `tenantId`, `requestId`, `amountMinor`, and tag sent twice. Both can pass HMAC. The server must check whether the request has already been processed.

Mechanisms commonly combined:
- **Request ID/idempotency key:** recorded in a state store scoped to principal/tenant; repeated submissions of the same command return the prior result or are rejected per contract.
- **Timestamp + allowed clock skew:** included in MAC input; reject expired requests, though timestamp alone does not stop replay within the time window.
- **Nonce or sequence number:** included in MAC input; receiver tracks uniqueness/order appropriately (handling retries and multi-instance deployments).
- **One-time tokens or challenge-response** when workflows require stronger freshness guarantees.

In distributed systems, the replay store needs atomicity/consistency; if two servers concurrently handle the same `requestId` using only local caches, the command can execute twice even with a valid MAC.

## 8. Versioning, Rotation, and Multi-Version Compatibility

A MAC protocol must carry an **explicit version identifier**. When adding `merchantId`, changing `amountMinor` precision, or switching from text delimiters to length-prefixing, create a new profile rather than silently altering v1's encoding.

Illustrative envelope showing wire components, not the final byte contract:

```json
{
  "version": 1,
  "keyId": "payments-prod-2026-10",
  "tenantId": "tenant-A",
  "requestId": "req-7",
  "amountMinor": 1299,
  "currency": "USD",
  "tag": "nEOzXhbbnYCVX0rn1leWKWA-OR9mZLAraX4FJOfZArU"
}
```

The tag above is the **test vector for the demo key, domain, and canonical bytes from Section 6**, not a tag generated by a production key corresponding to the sample `keyId`. The `keyId` field in the envelope merely illustrates routing metadata; in a production profile with key rotation, you must publish how `keyId` is bound into the MAC input and how the receiver maps it to the right trusted key. **Do not treat the illustrative envelope as a verbatim implementation specification.**

When migrating versions:
1. Document v1/v2 profiles independently: algorithms, fields, byte order, domain, tag length, encoding.
2. Server accepts only policy-permitted versions; validate version inside the MAC input.
3. Map `keyId` to a key with permitted scope, principal, status, and algorithm; bound the overlap window accepting old keys.
4. Maintain test vector suites per version and test invalid cases.
5. Set a sunset date for old versions/keys; avoid automatic fallbacks on verification failure.

Key rotation and format upgrades are separate concerns. A v1 payload may still need a v1 key during a compatibility window, but the server should never relax canonicalization just so "most legacy clients work."

## 9. Cross-Party Interoperability Testing: What to Test?

At minimum, maintain a grouped test matrix:

| Group | Scenario | Expected Behavior |
| --- | --- | --- |
| Golden vector | Same key, same input, same version | Input hex and tag match 100% |
| Fields/ordering | Swap `tenantId` and `requestId`, alter amount/currency | Tag fails verification under v1 profile |
| Boundaries | `("ab","c")` vs `("a","bc")` | Canonical bytes differ |
| Unicode | NFC/NFD, emoji, empty string, combining characters | Per policy; length measured in UTF-8 bytes |
| Encoding | LF/CRLF, UTF-8/UTF-16, BOM | Reject/mismatch if outside profile |
| Numbers | Negative, overflow, 1.0 vs 1, big-/little-endian | Explicit parser/schema; no silent type coercion |
| Tag format | Hex instead of Base64URL, padding, invalid chars, whitespace, wrong length | Reject |
| Key/algorithm | Wrong key, revoked keyId, disallowed algorithm | Reject |
| Protocol | Wrong version, domain, or message type | Reject |
| Replay | Resend valid request | Reject or return idempotent result per business rules |
| Authorization | Valid HMAC but tenant/resource does not belong to principal | Reject |
| Concurrency | Two requests with same ID hitting two instances | Side effects execute at most once |

**Cross-language interop testing:** at least one golden vector suite computed independently by both implementations. Do not only test that a Java client verifies MACs produced by the same Java code: that misses bugs where Java and the partner serialize differently.

### 9.1. Byte-by-byte debugging on mismatch

Pragmatic debugging sequence, keeping keys and sensitive data secret:

1. Confirm both parties actually use **the same profile** (version, domain, algorithm, tag length, encoding).
2. Compare schema/validation and the fields selected into the MAC; check route, tenant, and requestId.
3. Compare **length and canonical input bytes** in a test environment using non-sensitive fixtures. If bytes differ, find the first mismatch: delimiter, UTF-8, endianness, ordering, newlines, numbers, or escaping.
4. If bytes match, check key loading (raw text bytes vs. hex/Base64 decoded bytes), key version, and key derivation. **Never log production keys** to debug.
5. If MAC bytes match while tag text differs, check Base64/Base64URL/hex, padding, casing, and whitespace.
6. If the tag is valid yet the request is rejected, check time policy, replay/idempotency, identity mapping, authorization, and validation; never bypass checks just to "pass the test."

In production, log only what is needed to locate failures, such as profile ID, input length, field group names, error code, and correlation ID. Never log keys, sensitive tags unnecessarily, or bodies containing personal or payment data. Even hashes of sensitive data can leak information when input entropy is low; do not assume logging digests is automatically safe.

## 10. Typical Mistakes and Fixes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Client signs original JSON, server signs parsed and re-serialized JSON | Bytes differ due to ordering/spacing | Sign exact raw bytes on both sides or apply a canonical profile |
| Concatenating `tenantId + requestId` without separation | Two different field pairs yield the same input | Length prefixing / unambiguous serialization |
| Using a delimiter without escaping | `a\|b` causes ambiguity | Length prefixing or standard escaping rules |
| Using `String.length()` for UTF-8 string length | UTF-16 length does not equal byte length | Use `value.getBytes(UTF_8).length` |
| One side writes 1299 as 4-byte little-endian, the other as 8-byte big-endian | Different type and byte order | Standardize width, signedness, endianness |
| Strings with different Unicode composition | Different input bytes | Pin normalization and canonical encoding policy |
| One side treats `null` as empty, the other omits the field | Different schemas | Define absent/null/empty separately |
| Server accepts truncated tags of whatever length client sends | Unconstrained tag length | Enforce fixed length and profile |
| Sender emits hex, receiver decodes Base64 | Wrong wire tag codec | One canonical encoding and test vector |
| Comparing tags with ordinary string equality | Can introduce timing leaks | Decode, validate length, compare bytes with appropriate API |
| Letting client pick `alg` or set `keyId` freely | Algorithm/key confusion | Server allowlist, key registry, and scope |
| Signing only body, omitting tenant/action | MAC does not cover business context | Bind sufficient context in input, check authorization |
| Valid tag accepted, transaction re-executed | Missing replay/idempotency | Atomic state keyed by principal/requestId |
| Trying multiple schemas until one tag passes | Ambiguous fallback | Strict versioning, try only defined configurations |
| Testing only positive cases | Misses tampering, replay, encoding bugs | Negative test vectors and cross-platform interop tests |

## 11. Checklist for Designing an Implementable MAC Profile

Before both teams start coding, document a **verifiable contract**:

- **Purpose:** which message types, identities, tenants, and permissions the protocol authenticates; boundaries of MAC guarantees.
- **Version/domain:** version byte, domain separation, algorithm, list of permitted versions.
- **Keys:** generation/storage source, byte length, owning identity, lifecycle, `keyId`, safe key selection, and rotation policy.
- **Input fields:** ordered list, required/optional, value ranges, and protected business fields.
- **Canonical encoding:** UTF-8/Unicode policy, length prefix, integer width/endianness, decimal/time, null/missing/empty, map/list ordering, JSON or binary format.
- **Tag:** raw length, algorithm, truncation policy, encoding, padding/case, and placement in the request.
- **Verification:** where canonicalization/validation happens, fail closed on tag mismatch, safe comparison, handling of duplicate fields/headers.
- **Freshness and authorization:** timestamp/nonce/requestId, replay store, idempotency, binding to principal, and per-operation authorization.
- **Conformance:** golden vectors run by both sides, negative cases, documented version/rotation/error behavior.

### Review Questions

**1. Both sides use HMAC-SHA256 and the same key, yet produce different tags. Is HMAC broken?**

No. Check canonical input bytes first: serialization, fields, order, UTF-8, numbers, newlines, version. Only then check key bytes and wire tag encoding.

**2. Why is signing `tenantId + requestId` without a delimiter dangerous, even though HMAC is very strong?**

Because different value pairs can produce **the exact same input bytes** (e.g., `ab`+`c` and `a`+`bc`). Business-distinct messages get identical MACs by design; the bug is in encoding, not an attack on HMAC.

**3. When two JSON fields swap order, must the MAC remain the same?**

If the MAC is computed over raw JSON bytes, they **differ**. If both sides use a canonical JSON profile that produces identical bytes, they **match** for data defined as equivalent. There is no implicit profile-independent behavior.

**4. How long is a full HMAC-SHA256 tag? How long is an unpadded Base64URL string?**

The raw tag is **32 bytes**. For 32 bytes, unpadded Base64URL is **43 ASCII characters**. The corresponding hex string is **64 characters**.

**5. Why must the server still check requestId after the MAC is valid?**

Because an attacker can resend **the exact request and tag**. HMAC does not detect freshness; stateful anti-replay/idempotency and business authorization checks are required.

**6. Can you simply verify the HMAC and then grant full access to the payload's tenant?**

No. A party holding a key can create a valid tag for data they are not authorized to act on. The server must bind the key to a trusted principal and verify the principal's authorization for the specific tenant/action/resource.

**7. In the Java example, why must we use `writeInt(bytes.length)` instead of `writeInt(value.length())`?**

`DataOutputStream` writes byte length so the parser can read exact boundaries. `String.length()` counts UTF-16 code units and does not equal the UTF-8 byte count when non-ASCII characters are present.

**8. When adding a new field to the MAC message, should we try both the old and new formats per request until verification passes?**

No. Publish a new version/schema, authenticate the version inside the MAC input, and strictly control acceptance policies. Trying multiple ad-hoc formats invites ambiguity and weakens the protocol.

## 12. Conclusion

A MAC authenticates **only the exact bytes both parties agreed upon**. The strength of HMAC-SHA256 cannot compensate for ambiguous field concatenation, mismatched JSON serialization, missing business fields, tag encoding confusion, or trusting a valid request to execute twice.

An interoperability contract must be clear from **data semantics → field ordering/types → canonical byte encoding → algorithm/key → raw tag → wire tag → verification and application policy**. A test vector stating **demo key, canonical input hex, and expected tag** is the fastest way to prove both parties agree before handling real data.

### References

- RFC 2104 — *HMAC: Keyed-Hashing for Message Authentication*: https://www.rfc-editor.org/rfc/rfc2104
- RFC 4231 — *Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512*: https://www.rfc-editor.org/rfc/rfc4231
- RFC 8785 — *JSON Canonicalization Scheme (JCS)*: https://www.rfc-editor.org/rfc/rfc8785
- Java SE 17, `javax.crypto.Mac`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
- Java SE 17, `java.io.DataOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html
- Java SE 17, `java.util.Base64`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html
- Java SE 17, `java.security.MessageDigest`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
