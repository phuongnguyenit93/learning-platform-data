# 7.9 Charset Compatibility, Unicode, and Cross-System Password Conversion Rules

Users can type **what feels like the exact same password** on the web, a Java app, Python, Node.js, or a legacy system and still get rejected at login. A subtle cause is that platforms produce **different byte sequences before running the key derivation function (KDF) or password hash**: different charsets, multiple valid Unicode representations, strings getting `trim`med or case-folded, or libraries enforcing their own byte-length rules.

This lesson walks from character → Unicode → bytes → KDF, showing how to establish a compatibility contract, test across systems, and migrate legacy password verifiers. **Password conversion policies must be explicitly specified, versioned, and verified using real bytes**; a change that locks users out, or collapses two distinct passwords into one, is a security bug.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the differences among **displayed characters, Unicode code points, UTF-16 code units, grapheme clusters, and bytes**.
2. Show why precomposed `"é"` and `"e"` + combining mark look alike yet produce different bytes; distinguish **NFC, NFD, NFKC, and NFKD**.
3. Define a **password profile**: decode, validate, normalize, encode, KDF, salt, parameters, metadata, version, and error policy.
4. Use Java 17+ to test strict UTF-8, `Normalizer`, Unicode lengths, `PBEKeySpec`, and `PBKDF2WithHmacSHA256`.
5. Design **golden vectors** to verify Java/Python/JavaScript compatibility and a migration plan from legacy password hashes without losing accounts.

## 2. Distinguishing three layers of password data

~~~text
Keystrokes / copy-paste / IME
          |
          v
User-entered Unicode sequence
          |
          | validate, defined policy, normalization (if any)
          v
Profile-normalized Unicode sequence
          |
          | encode with specified charset (usually strict UTF-8)
          v
Password byte sequence
          |
          | password KDF/hash + salt + work factor (+ pepper if any)
          v
Stored verifier: algorithm, profile id, params, salt, hash
~~~

**Displayed character** is what a human eye perceives; **Unicode code point** is the abstract code for a character; **Java `String`** stores code points as UTF-16 units; and **the KDF** operates under its library's input contract, which may accept bytes or `char[]`. Never conflate all three into a single vague notion of “password string.”

Example:

| Code point sequence | UTF-8 bytes | Appearance on UI |
| --- | --- | --- |
| `U+00E9` (LATIN SMALL LETTER E WITH ACUTE) | `C3 A9` | é |
| `U+0065 U+0301` (e + COMBINING ACUTE ACCENT) | `65 CC 81` | e + accent, commonly rendered as é |

These two strings have **different UTF-8 bytes** prior to normalization. Consequently, `hash(passwordBytes)` or a KDF on raw bytes yields different outputs, barring an astronomically improbable KDF collision. When both sides apply NFC, both representations converge to the same Unicode sequence before encoding.

**Do not use raw SHA-256 to store passwords**: `hash(passwordBytes)` here merely illustrates byte sensitivity, not an implementation recommendation. Passwords require a dedicated password hashing/KDF scheme such as Argon2id, scrypt, or PBKDF2 per standards and application constraints.

## 3. Charset: a Java `String` is not UTF-8 bytes

A **charset** defines the rule for encoding characters into bytes and decoding back. The same Unicode string can produce different bytes:

| Charset | Notes |
| --- | --- |
| **UTF-8** | Encodes every Unicode scalar value in 1–4 bytes; suitable for modern protocols handling Vietnamese/emojis. |
| **UTF-16LE / UTF-16BE** | Different byte orders; non-BMP characters use surrogate pairs (4 bytes); not the same as UTF-8. |
| **ISO-8859-1** | Single-byte encoding; cannot represent all Vietnamese characters or emojis. |
| **Windows-1252** | Common legacy encoding; differs from ISO-8859-1 on several byte codes. |
| **Default charset** | Can vary by JVM version, OS, or configuration. Insufficient as a long-term password contract. |

A non-portable Java example:

~~~java
byte[] raw = password.getBytes(); // uses the environment's default charset
~~~

If the contract is UTF-8 and input is valid:

~~~java
byte[] raw = password.getBytes(StandardCharsets.UTF_8);
~~~

The second form specifies the charset explicitly, yet you must understand **unpaired surrogates**: a Java `String` can contain a UTF-16 code unit in the surrogate range without a valid partner. Some convenience encoders/decoders silently **replace** malformed data instead of rejecting it. To control password bytes strictly, use `CharsetEncoder`/`CharsetDecoder` with `CodingErrorAction.REPORT` and **reject** invalid Unicode/byte sequences instead of substituting `?` or `U+FFFD`.

For HTTP/JSON, the **transport decoding** step must be unambiguous. `%C3%A9` in URL-form-encoded input represents UTF-8 bytes; if a gateway already decoded it to `é`, the application must **not decode a second time** or hash the literal 6 characters `%C3%A9`. Never put passwords in URL query strings: URLs are frequently logged, cached in history, or shared through analytics systems. Transmit credentials over TLS and proper authentication endpoints.

## 4. Unicode normalization and why you must pick the right form

In Java:

~~~java
String normalized = Normalizer.normalize(
        password, Normalizer.Form.NFC);
~~~

Unicode defines four normalization forms:

| Form | Normalization rule | Effect on passwords |
| --- | --- | --- |
| **NFC** | Canonical decomposition + composition | Unifies *canonically equivalent* sequences such as precomposed `é` and `e` + combining accent. |
| **NFD** | Canonical decomposition | Canonical decomposed representation; differs in bytes from NFC, must match profile. |
| **NFKC** | Compatibility decomposition + composition | Also collapses compatibility/formatting distinctions, e.g., fullwidth `Ａ` and ASCII `A`. |
| **NFKD** | Compatibility decomposition | Applies NFKC compatibility folding while remaining decomposed. |
| **No normalization** | Keeps exact user-entered code points | Distinguishes even canonically equivalent sequences; if this is a legacy policy, preserve it when verifying old hashes. |

Examples:

~~~text
NFC("\u00E9") == NFC("e\u0301")    → true
NFC("Ａ")     == NFC("A")          → false
NFKC("Ａ")    == NFKC("A")         → true
~~~

`Ａ` is FULLWIDTH LATIN CAPITAL LETTER A (U+FF21). NFKC is not “a stronger, always-safer NFC”: it **changes which passwords are treated as equivalent**, potentially merging passwords users considered distinct. Neither NFD nor NFKD inherently adds security; suitability depends on product policy and stored contracts.

**Current NIST SP 800-63B recommends NFC** for systems accepting Unicode passwords, prior to hashing: https://pages.nist.gov/800-63-4/sp800-63b.html . Per Unicode, NFC handles canonical equivalence whereas NFKC adds compatibility equivalence: https://www.unicode.org/faq/normalization.html . New systems can follow this recommendation, but **never silently change policy for a legacy hash database**, because doing so alters input bytes at login.

### 4.1. Looking alike does not mean Unicode equivalence

- Latin `a` (U+0061) differs from Cyrillic `а` (U+0430), even when fonts make them visually indistinguishable. NFC does not merge them.
- Unicode includes **variation selectors**, combining marks, zero-width joiners, and multi-code-point emojis; one rendered glyph on UI can correspond to multiple code point sequences.
- ASCII space `U+0020` differs from non-breaking space `U+00A0` and other Unicode whitespace characters.
- Vietnamese input methods (IME), mobile keyboards, and copy-paste can emit different Unicode forms; identical bytes cannot be guaranteed merely by looking at the screen.
- Normalization does not guarantee all visually similar strings become identical, nor does it make malformed Unicode valid.

**Pick one form for a new profile and enforce that exact form in the verifier.** Never normalize “just to be safe” at multiple layers using conflicting rules.

## 5. Dangerous transformations outside the contract

An application can inadvertently alter passwords through everyday operations:

| Transformation | Consequence |
| --- | --- |
| `trim()` / `strip()` | Strips leading/trailing whitespace: `" secret "` becomes `"secret"`. |
| `toLowerCase()` / `toUpperCase()` | Destroys case sensitivity; locale rules may vary. |
| Stripping Vietnamese diacritics / transliteration | Collapses distinct strings into one; shrinks distinct password space. |
| Converting to ISO-8859-1 and replacing unmappable characters | Loses information and causes post-conversion password collisions. |
| Truncating after N bytes or N `char`s | Drops the tail of the secret or splits a surrogate pair. |
| Appending BOM, newline, or terminating NUL byte | Changes KDF input bytes; can misinteract with legacy libraries. |
| Double-decoding URL/Base64/JSON escapes | Result no longer matches the user's contracted string. |
| Client normalizes NFKC while server normalizes NFC | Different client paths can produce incompatible verifiers. |

**A user entitled to use leading/trailing spaces or uppercase letters in a password must have them distinguished accurately**, unless an explicitly published protocol specifies otherwise. Never use `String.toLowerCase(Locale.ROOT)` or accent stripping to “stabilize” passwords. Case folding can be useful for **usernames**, which is a separate design from passwords.

If you must **reject** a character class (e.g., unsupported control characters), publish and check the policy at password creation and enforce it consistently at login. Explicit rejection is far better than silent mutation. Avoid unnecessary composition rules that hinder users from picking strong passwords.

## 6. Length must be measured in the right unit

A lock emoji `🔒` has:

~~~text
Java String.length()                = 2 UTF-16 code units
String.codePointCount(0, length())  = 1 Unicode code point
UTF-8 encoded length                = 4 bytes
~~~

| Unit | Meaning | In Java |
| --- | --- | --- |
| **UTF-16 code unit** | 16-bit `char` unit; non-BMP characters normally use a surrogate pair | `String.length()` |
| **Unicode code point** | Value U+0000...U+10FFFF representing an encoded character; multiple code points can form one visible cluster | `String.codePointCount(0, s.length())` on valid Unicode |
| **Grapheme cluster** | User-perceived character unit displayed on screen | Unicode grapheme segmentation; not automatically equal to code points |
| **UTF-8 byte** | Actual byte count passed to a KDF/protocol with a byte interface | `s.getBytes(StandardCharsets.UTF_8).length` when valid |

Per NIST, **Unicode password length is measured in Unicode code points**, while algorithm limits may be in **bytes**; both rules must be considered. Systems must enforce a reasonable resource ceiling to prevent overload, yet **must never silently truncate** passwords and hash only the prefix. At creation/change time, return a clear policy error; at login, handle inputs consistently with the stored account verifier.

**Legacy bcrypt:** many traditional bcrypt implementations process only the **first 72 bytes**, while newer libraries reject longer inputs instead of truncating. 72 bytes is **not 72 code points**. Legacy systems may also handle NUL bytes specially. When migrating, test the exact version/variant/provider and overflow rules; never perpetuate silent 72-byte truncation in a new profile.

## 7. Defining a cross-system password profile

To make Java, Python, JavaScript, and legacy services verify the same password, define a **byte-level contract**. Example of a **new** profile:

~~~text
profile_id: pwd-utf8-nfc-v1

Transport:
  - Request decoded per defined protocol, strict UTF-8.
  - Reject malformed Unicode/UTF-8; do not substitute U+FFFD.
Input policy:
  - Accept valid Unicode, enforcing defined length limits.
  - No trim/casefold/diacritic stripping, no double-decoding of escapes.
Transform:
  - Unicode normalization = NFC.
  - Strict UTF-8 encode, no BOM, no NUL terminator.
KDF:
  - Algorithm + implementation/variant + salt bytes + work factor
    + output length + pepper policy (if any) are all specified.
Stored verifier:
  - algorithm, profile_id, cost params, salt, derived verifier;
    never store plaintext or normalized password.
~~~

The pipeline must follow a **strict order**:

1. Decode transport input using a strict decoder; reject malformed sequences.
2. Check input policies such as resource bounds and allowed character sets.
3. Normalize using the exact form recorded in the profile; never use another form at login.
4. Encode to strict UTF-8 bytes; verify algorithm byte-length limits.
5. Run the password KDF with the account's exact salt and parameters.
6. Call the standard library verification function; return the result without logging the password.

**Number of normalizations**: applying the same fixed normalization form is idempotent (re-applying does not change the result), yet different layers must not apply **different** transformations outside the contract. New policies must state clearly who performs this step: the UI may assist users, but **the server-side verifier** must be the authority enforcing the cryptographic policy.

### 7.1. The KDF also has its own data contract

For PBKDF2, both sides must agree on:

- Exact PRF: `HmacSHA256` differs from `HmacSHA1` or `HmacSHA512`.
- **Password bytes** or how the provider converts `char[]` into password material.
- **Salt bytes**, and how hex/Base64 salt strings are decoded if stored as text; salts must be freshly and randomly generated per real verifier.
- **Iteration count**, key length, and units: `PBEKeySpec(..., keyLength)` takes **bits**, whereas many other libraries take bytes.
- Provider/version and output format; verified with **Unicode golden vectors**.
- If a pepper is used: secret outside DB, pepper version/key ID, and whether applied pre- or post-KDF per vetted design.

For Argon2id, the contract also includes memory cost, time cost, parallelism, version, and length; for bcrypt, variant `$2a$`/`$2b$`/`$2y$`, cost, input limits, and preprocessing. There is no reason to rewrite a KDF by hand for compatibility: use standard libraries and verify exact bytes.

### 7.2. Boundaries of Java's `PBEKeySpec`

`javax.crypto.spec.PBEKeySpec` accepts the password as `char[]`, **not directly as UTF-8 bytes**. JCA documentation notes that different password-based encryption mechanisms may use different bit subsets of each `char`; therefore **you cannot infer from the algorithm name alone that all Java providers and Python/Node libraries convert Unicode to bytes identically**. For `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")`, know the actual implementation and verify vectors on Unicode inputs.

Java's `PBEKeySpec` clones the input password array; calling `clearPassword()` clears its internal copy, while the `char[]` owner must wipe its own array. Because `String` is immutable and normalization typically allocates intermediate `String` objects, erasing every memory copy is not guaranteed. Keep secret lifetimes short, never log them, and avoid holding passwords as `String` long-term in production.

## 8. Runnable Java 17+ example

This program uses **harmless test samples**, not real user passwords. It demonstrates UTF-8 bytes, normalization, code unit/code point counts, malformed-charset rejection, and PBKDF2 results in **one Java provider**. The PBKDF2 section uses **10,000 iterations ONLY for fast demo execution**; production settings must follow current standards and benchmarks with a fresh salt per password.

Save with the exact filename **`PasswordInteropDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordInteropDemo {
    static byte[] strictUtf8(char[] chars) throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(chars));
        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        return result;
    }

    // Parameters for demo only; do not use 10,000 rounds in production.
    static byte[] deriveNfc(String password, byte[] salt) throws Exception {
        char[] normalized = Normalizer
                .normalize(password, Normalizer.Form.NFC).toCharArray();
        PBEKeySpec spec = new PBEKeySpec(normalized, salt, 10_000, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
            Arrays.fill(normalized, '\0');
        }
    }

    public static void main(String[] args) throws Exception {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("Raw equal           = " +
                composed.equals(decomposed));
        System.out.println("UTF-8 composed      = " +
                HexFormat.of().formatHex(
                        strictUtf8(composed.toCharArray())));
        System.out.println("UTF-8 decomposed    = " +
                HexFormat.of().formatHex(
                        strictUtf8(decomposed.toCharArray())));
        System.out.println("NFC equal           = " +
                Normalizer.normalize(composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

        String wideA = "\uFF21";
        System.out.println("NFC fullwidth == A  = " +
                Normalizer.normalize(wideA, Normalizer.Form.NFC)
                        .equals("A"));
        System.out.println("NFKC fullwidth == A = " +
                Normalizer.normalize(wideA, Normalizer.Form.NFKC)
                        .equals("A"));

        String emoji = "\uD83D\uDD12";
        System.out.println("Emoji UTF-16 units  = " + emoji.length());
        System.out.println("Emoji code points   = " +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("Emoji UTF-8 bytes   = " +
                strictUtf8(emoji.toCharArray()).length);
        System.out.println("Spaces preserved    = " +
                !" pass ".equals("pass"));

        byte[] salt = HexFormat.of().parseHex(
                "000102030405060708090a0b0c0d0e0f");
        byte[] keyA = deriveNfc(composed, salt);
        byte[] keyB = deriveNfc(decomposed, salt);
        try {
            System.out.println("NFC PBKDF2 equal    = " +
                    MessageDigest.isEqual(keyA, keyB));
        } finally {
            Arrays.fill(keyA, (byte) 0);
            Arrays.fill(keyB, (byte) 0);
        }

        boolean malformedRejected = false;
        try {
            strictUtf8(new char[] { (char) 0xD800 });
        } catch (CharacterCodingException expected) {
            malformedRejected = true;
        }
        System.out.println("Unpaired rejected   = " +
                malformedRejected);
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac PasswordInteropDemo.java
java PasswordInteropDemo
~~~

Exact stdout:

~~~text
Raw equal           = false
UTF-8 composed      = c3a9
UTF-8 decomposed    = 65cc81
NFC equal           = true
NFC fullwidth == A  = false
NFKC fullwidth == A = true
Emoji UTF-16 units  = 2
Emoji code points   = 1
Emoji UTF-8 bytes   = 4
Spaces preserved    = true
NFC PBKDF2 equal    = true
Unpaired rejected   = true
~~~

**Reading the output:**

1. The two representations of `é` differ in bytes before NFC; after NFC they yield the same string.
2. NFKC folds fullwidth `Ａ` to ASCII `A`, whereas NFC preserves the distinction.
3. `String.length()` is neither Unicode code points nor UTF-8 bytes; the emoji takes 2 code units and 4 UTF-8 bytes.
4. The strict encoder rejects unpaired surrogates; paths reading UTF-8 from the network also need a **strict decoder** before constructing a `String`.
5. PBKDF2 outputs match because NFC input, salt, iterations, keyLength, and provider are identical. **This does not yet prove Java/Python/Node interop**; run real test vectors across every implementation.
6. `10_000` iterations and the **fixed salt** serve solely for lesson testing. For real passwords, generate a **fresh, sufficiently long random salt with `SecureRandom` per password**, choose a suitable password KDF/work factor, and never log derived keys.

In the demo, `Normalizer.normalize` creates intermediate `String` objects that cannot be wiped directly. Program-managed `char[]` arrays are wiped and `PBEKeySpec.clearPassword()` wipes the internal copy; this mitigates risk, **without guaranteeing every secret copy is purged from RAM**.

## 9. Comparing Java, Python, and JavaScript

| Platform | Internal representation | Points to verify |
| --- | --- | --- |
| **Java** | `String`/`char[]` holding UTF-16 code units; `PBEKeySpec` takes `char[]` | Default charset, `Normalizer`, strict encoder, provider char→byte mapping. |
| **Python 3** | Unicode `str`; `unicodedata.normalize`; `encode` | Same Unicode form, strict UTF-8, and KDF receiving exact raw bytes. |
| **Node.js** | JS String uses UTF-16; `String.normalize`; `Buffer.from(..., "utf8")` | `length` counts code units; unpaired surrogates must be handled; hash libraries have distinct byte rules. |
| **Legacy** | May use ISO-8859-1, Windows-1252, UTF-16LE, or NUL-terminated byte arrays | Determine exact pre-hash bytes, truncation/stripping rules, and old normalization behavior. |

Python snippet converting Unicode to UTF-8 under the NFC profile:

~~~python
import unicodedata

# password has been validated according to the protocol.
password_bytes = unicodedata.normalize("NFC", password).encode(
    "utf-8", errors="strict"
)
~~~

Corresponding Node.js snippet:

~~~javascript
// Must validate Unicode, especially unpaired surrogates, before this step.
const passwordBytes = Buffer.from(password.normalize("NFC"), "utf8");
~~~

That is only the **byte-encoding step**, not a complete password-hashing method. Some JS APIs replace invalid surrogates when creating buffers, so strict input validation must precede it. When Java uses `PBEKeySpec` while Python accepts raw bytes, compare **golden vectors containing Unicode** to confirm the Java provider actually derives from the contracted byte sequence; never rely on the name `PBKDF2WithHmacSHA256` alone.

**Another trap:** Side A passes raw password bytes to the KDF, while Side B passes a **hex or Base64 string of those bytes**. Hex/Base64 are **encodings**, with no reason to add an extra encoding layer before the KDF unless a legacy profile explicitly mandates it.

## 10. Golden vectors: verifying bit-for-bit compatibility

Use fixed test samples **containing no real credentials** and record the exact post-preprocessing byte sequence:

| Vector | Test condition | Result after NFC + UTF-8 profile |
| --- | --- | --- |
| ASCII `abc` | Baseline | `61 62 63` |
| `é` = U+00E9 | Precomposed | `C3 A9` |
| `e` + U+0301 | Decomposed | **Also** `C3 A9` |
| `Ａ` = U+FF21 | NFC does not compatibility-fold | **Differs** from ASCII `A` |
| `" pass "` | No trim | Differs from `"pass"` |
| `🔒` | Non-BMP | 1 code point, 2 code units, 4 bytes |
| Latin `a` and Cyrillic `а` | Confusables | Not merged by NFC |
| Unpaired surrogate | Malformed UTF-16 | Reject |
| Malformed UTF-8 from transport | Malformed input | Reject, do not substitute U+FFFD |
| String exceeding policy limit | No truncation | Return policy error |

Golden vectors for the **KDF** must also specify salt bytes, PRF/algorithm, iteration or memory/time cost, output length, variant, dummy test pepper (if used), and **expected derived bytes**. Every implementation must return **identical bytes** for the same vector. Never test with ASCII alone: UTF-8 and many legacy encodings match on ASCII, hiding bugs with Vietnamese passwords.

Verification workflow:

~~~text
1. Parse input per protocol, reject malformed data.
2. Validate Unicode and policy rules.
3. Normalize per exact profile.
4. Strict UTF-8 encode, compare expected passwordBytes.
5. Invoke KDF with fixed test salt + params.
6. Compare derived result/verify against expected value.
7. Run negative tests: wrong charset, wrong normalization,
   whitespace, emojis, malformed input, key length, salt, cost.
~~~

Rerun vectors whenever upgrading the JVM, JCE providers, Unicode tables, or password-hashing libraries, or when changing gateways/APIs. A `decode(encode(s)) == s` round-trip **is not enough** to prove two systems choose the same charset or KDF policy, nor does it catch decoders that silently replace input characters.

## 11. Storing hashes with profiles for long-term compatibility

A stored verifier should carry enough metadata to verify under **the exact version that created it**:

~~~text
account_id
password_profile_id = pwd-utf8-nfc-v1
password_algorithm  = Argon2id / PBKDF2-HMAC-SHA256 / bcrypt...
salt                 = binary or documented Base64 form
cost_parameters      = iterations / memory / time / parallelism
hash_or_derived_key  = binary or documented encoded form
algorithm_variant    = ...
pepper_key_id        = ... (if used)
~~~

Some libraries embed algorithm/cost/salt inside the encoded hash, such as PHC format for Argon2id or modular crypt format for bcrypt. Even so, **charset and normalization policies are not necessarily encoded there**; store `password_profile_id` when clear compatibility and migration matter.

- **Salt** is public, per-password, and random; never use a static salt shared across everyone.
- **Pepper** is a server secret stored outside the DB if used; manage key IDs/versions, and never use it to replace salts.
- **Work factor** should follow security references and system benchmarks; raising cost requires a migration plan.
- Never store plaintext, normalized text, password bytes, or debug traces of them.
- Never use `String.hashCode()`, checksums, raw SHA-256, or Base64 in place of dedicated password hashing.

## 12. Migrating from existing password-hash systems

**You cannot turn an old password hash into a new hash merely by hashing the old hash** to match new Unicode bytes: KDFs are one-way and lack the original text needed for normalization/encoding. The standard approach is **verifying under the old profile first**, then rehashing **the candidate password the user just supplied** under the new profile.

~~~text
login(account, candidate):
    record = loadVerifier(account)
    profile = lookupById(record.password_profile_id)

    if !verifyWithRecordedProfile(candidate, record, profile):
        denyAccess()

    if isEligibleForUpgrade(record):
        replacement = newVerifier(candidate, newProfile, newRandomSalt)
        atomicCompareAndSwap(record, replacement)

    allowLogin()
~~~

This is **pseudocode** explaining the flow, not standalone Java. Keep in mind:

1. **Select exactly one profile from account metadata** to verify. Never blindly try a cascade of encodings/normalizations, which can **widen the set of accepted passwords** and complicate auditing and timing.
2. For legacy rows lacking metadata, rely on configuration evidence/creation timestamps/tenant records or provide a **password reset path**. You cannot guess original password bytes from the hash alone.
3. After successful authentication, rehash with the new profile and a **fresh salt**; update atomically so concurrent password changes are not overwritten.
4. Moving from “raw bytes” to NFC can cause inputs that were previously **distinct passwords** to become identical. Evaluate user impact and authentication rules.
5. For legacy bcrypt with a 72-byte cap or NUL handling, verify faithfully with the old library and consider **requiring a password change** on migration rather than preserving unsafe truncation rules.
6. Never change the DB profile ID without generating a new verifier, and never store plaintext for “batch migration.”

A concrete example: an old system used Windows-1252 + PBKDF2; the new Java service uses NFC + UTF-8. ASCII passwords may still work. Passwords with Vietnamese characters or combining accents may fail because Windows-1252 could not represent them. The solution is not **“decoding the old hash to UTF-8,”** but checking the account under the known legacy rule and replacing the verifier once the user enters the right password—or resetting if legacy behavior cannot be reproduced safely.

## 13. Common operational and security errors

| Error | Consequence | How to avoid |
| --- | --- | --- |
| Calling `password.getBytes()` with default charset | Output depends on runtime, especially on legacy hosts | Explicit UTF-8 and test vectors. |
| Counting `String.length()` as visible characters | Wrong length limits; emojis count as two | Separate code units, code points, and bytes. |
| `trim` before hashing | Two distinct passwords merge into one | Preserve whitespace unless policy explicitly dictates otherwise. |
| Unexpected NFKC after an upgrade | Compatibility characters collapse into ASCII | Version profiles and plan migrations. |
| Encoder/decoder replaces malformed input | Original bytes lost; distinct strings collide | `CodingErrorAction.REPORT` and reject. |
| Confusing hex/Base64 salt text with raw salt bytes | PBKDF2 always mismatches | Decode salts according to stored format. |
| Confusing 256-bit vs. 256-byte length | Derived key mismatch | Specify parameter units explicitly. |
| Hashing JSON text around password instead of password value | Bytes differ from other systems | Parse JSON properly and extract the exact value field. |
| Testing only `"password123"` | ASCII hides charset mismatches | Golden vectors with Unicode, emojis, and combining marks. |
| Trying every legacy charset on login | Accepts unintended passwords; hard to audit | Identify profile per record and reset if unknown. |
| Rehashing old hash under new profile | Fails to produce verifier of new password bytes | Verify candidate then rehash, or reset. |
| Logging normalized passwords or derived keys for debugging | Credential leakage | Log only error codes and non-sensitive metrics. |
| Confusing salt and pepper | Broken key/salt management | Public per-password salt; secret pepper isolated from DB. |
| Using raw SHA-256 to store passwords | Too fast against offline guessing | Use proper password hashing/KDF with strong cost. |

**Remember this common HTTP bug:** A password travels through browser, reverse proxy, framework request parser, authentication middleware, hashing library, and DB. If **each layer applies its own charset/normalization**, root causes become hard to trace. Centralize the profile inside the verifier and test end-to-end across JSON, form encoding, request lengths, byte payloads, KDF, and DB metadata. Never log passwords into traces while investigating.

## 14. Self-check questions and answers

**Question 1:** Will `é` (U+00E9) and `e` + U+0301 always yield the same KDF key?

**Answer:** Only when using the **same profile** (e.g., NFC before UTF-8), same salt/cost/algorithm/provider, and identical input bytes per KDF definition. Hashing raw UTF-8 bytes keeps them different.

**Question 2:** Are `Ａ` and `A` identical under NFC? What about NFKC?

**Answer:** NFC keeps them distinct; NFKC compatibility-folds `Ａ` to ASCII `A`, making the two passwords equivalent under an NFKC policy.

**Question 3:** The emoji `🔒` has `String.length()==2`. Is it 2 bytes long?

**Answer:** No. That is 2 UTF-16 code units, **1 code point**, and **4 UTF-8 bytes**. With combining marks, code point count need not equal visible grapheme cluster count either.

**Question 4:** Should you `strip()` passwords to make typing easier for users?

**Answer:** Not arbitrarily. Spaces can be part of a password, and stripping silently collapses distinct passwords into one.

**Question 5:** Both Java and Python use PBKDF2-HMAC-SHA256, yet Vietnamese hashes differ. What should you investigate?

**Answer:** Check Unicode code points, normalization, UTF-8 vs. legacy charsets, provider char→byte conversion, salt bytes, iterations, derived-key bit/byte length, pepper, version/variant, and concrete test vectors.

**Question 6:** Can you migrate all old hashes from Latin-1 to UTF-8/NFC without knowing the passwords?

**Answer:** No. A verifier is one-way. You must verify under the old profile with a valid candidate and then create a new verifier, or reset passwords where needed.

**Question 7:** Legacy bcrypt accepts up to 72 bytes. Is a 60-character Vietnamese password guaranteed under 72 bytes?

**Answer:** No. UTF-8 can use multiple bytes per character; measure **bytes** and verify your bcrypt implementation's actual behavior. Never truncate silently.

**Question 8:** Why does a strict encoder rejecting unpaired surrogates help security interoperability?

**Answer:** If one side substitutes `?`/U+FFFD for bad surrogates while the other rejects or substitutes differently, password data loses fidelity and yields diverging bytes. Explicit rejection keeps behavior uniform.

**Question 9:** Is a golden vector with ASCII and 1 salt enough to prove Java/Node/legacy compatibility?

**Answer:** No. You need Unicode vectors (composed/decomposed, fullwidth, emojis, spaces), malformed inputs, length limits, salt/iterations/params, and expected derived bytes, running the same suite on every runtime.

## 15. Pre-production checklist

- [ ] Defined **profile ID/version** for Unicode input, normalization, encoding, and KDF.
- [ ] HTTP/JSON/transport decoding is strict, never substituting malformed UTF-8/UTF-16.
- [ ] NFC/NFD/NFKC/none chosen explicitly; no off-contract trim, casefold, or diacritic stripping.
- [ ] UTF-8 byte inputs verified with test vectors; no stray BOM/NUL/newlines added outside protocol.
- [ ] Code point, UTF-16 code unit, and byte lengths distinguished; passwords never truncated.
- [ ] Password KDF/bcrypt limits and exact provider/version behavior verified.
- [ ] Unique random salt, explicit cost/algorithm/PRF/length/variant, and metadata sufficient to verify.
- [ ] All languages pass shared **Unicode golden vectors and negative cases**.
- [ ] Legacy accounts verify under **their creation-time policy**, migrating only after valid login or reset.
- [ ] Zero storage/logging of plaintext, normalized passwords, password bytes, derived keys, or secrets.
- [ ] Standards-compliant/trusted password hashing/KDF library used with benchmarked production cost.

**Conclusion:** **KDF input bytes are the result of an entire conversion contract**, not just the hash function. For passwords to interoperate across Java and other systems, fix and test the whole chain **transport → Unicode → normalization → UTF-8 → password KDF + salt/params**, then version it so you can upgrade or migrate without breaking verification for existing accounts.