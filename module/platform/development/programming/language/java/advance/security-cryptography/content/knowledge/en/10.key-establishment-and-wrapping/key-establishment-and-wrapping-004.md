# 10.4 Shared Secret, Key Derivation, Usage Context, and Purpose-Based Key Separation

In an encryption protocol, two parties can perform key agreement such as **X25519/ECDH** and obtain the same **shared secret**. Yet going from having that secret to safely using keys for **bidirectional encryption, MAC, data-key wrapping**, and other purposes requires a mandatory step: **key derivation with the proper context and purpose labels**.

Never take raw shared secret bytes directly as an AES key, never slice them arbitrarily into multiple keys, and certainly never reuse the same key across multiple algorithms or transmission directions. This lesson dives into **HKDF Extract/Expand, transcript/context binding, domain separation, sender–receiver role separation, and DEK/KEK distinction**, along with a standalone runnable Java 17+ example.

## 1. Objectives and Terminology

After completing this lesson, you will be able to:

1. Explain why **key agreement does not mean you already have a safe session key** and does not authenticate identities on its own.
2. Distinguish **shared secret/IKM**, **PRK** after HKDF-Extract, and **OKM** after HKDF-Expand; understand the roles of `salt` and `info`.
3. Bind keys to **protocol version, algorithm, transcript, role, channel, direction, and purpose** to prevent key confusion.
4. Derive separate **c2s/s2c AES-GCM keys**, HMAC keys, and **key-encryption keys (KEK)**; know when to use AES key wrap.
5. Implement an X25519 + HKDF-HMAC-SHA256 + AES-GCM + AESWrap example in Java 17+, verifying both outputs and failure cases.
6. Identify MITM risks, context mismatches, label collisions, nonce reuse, replay, rekeying, key confirmation, and secret lifecycle management.

Key terminology:

| Term | Meaning | Must be kept secret? |
| --- | --- | --- |
| **ECDH / X25519** | Mechanism for agreeing on a secret from one side's private key and the other side's public key | Private key must be secret; public key may be public |
| **Z / shared secret** | Raw output of key agreement; valid peers obtain identical bytes | **Yes**; never leak or log |
| **IKM (Input Keying Material)** | Secret material fed into HKDF-Extract, usually the shared secret | **Yes** |
| **PRK (Pseudorandom Key)** | Pseudorandom key produced by HKDF-Extract | **Yes**; intermediate secret |
| **OKM (Output Keying Material)** | Key bytes derived per `info`, used as traffic keys, MAC keys, KEK, etc. | **Yes** |
| **HKDF Salt** | Input parameter to Extract; may be public, must follow the protocol | Does not need secrecy |
| **Info/context** | Labels and context used in Expand to produce separated keys | Usually public, but must be consistent and properly bound |
| **DEK** | Data Encryption Key: encrypts actual data | **Yes** |
| **KEK** | Key Encryption Key: used to wrap/protect a DEK or other keys | **Yes**, must be purpose-isolated |

**Key distinction:** HKDF does not strengthen a weak password into a high-entropy shared secret; passwords require a dedicated **password KDF/hash**. HKDF is suited for inputs that already possess appropriate randomness/secrecy, such as an ECDH secret or a securely generated master secret.

## 2. Path from Key Agreement to Application Keys

Overall diagram:

~~~text
Client                                       Server
  private a                                  private b
  public A = X25519(a, G)                    public B = X25519(b, G)
       \                                     /
        ---- exchange public keys A, B -----
       /                                     \
  Zc = X25519(a, B)                     Zs = X25519(b, A)
                    Zc == Zs
                         |
                HKDF-Extract(salt, Z)
                         |
                        PRK
                         |
    +--------------------+-------------------------+
    |                    |                         |
HKDF-Expand(         HKDF-Expand(             HKDF-Expand(
  info="c2s/enc")     info="s2c/enc")          info="wrap/kek")
    |                    |                         |
 client→server key   server→client key             KEK
                         |
               ...separate MAC/confirm/export keys...
~~~

At the API level, never treat `Z` as a “ready-to-use AES key” even though it is 32 bytes long for X25519. Having the right length **does not mean** the bytes are uniformized, context-bound, identity-bound, or possess properties suited for every primitive. In particular, the same `Z` could appear across different purposes/protocols when a design lacks domain separation.

A **key schedule** is the exact set of rules specifying how keys are generated, named, distributed, and used: from secret inputs, transcript, and roles to algorithms and lifetimes. A proper key schedule must be computed **byte-for-byte identically** by both sides, not merely “both calling HKDF”.

## 3. Why Shouldn't the Shared Secret Be Used Directly?

### 3.1. The Shared Secret Is Input Material, Not a Multi-Purpose Key

For example, X25519 returns a 32-byte array via `KeyAgreement.generateSecret()`. Even though 32 bytes looks just right for AES-256, you still must establish:

- **Which session does this secret belong to?** If reused across contexts, the key does not automatically isolate sessions/protocols.
- **Are the two roles symmetric or directional?** Sharing the same key for c2s and s2c can cause nonce-collision risks if nonce allocation is not coordinated.
- **What purpose will the key serve?** Encryption, MAC, handshake confirmation, and key wrapping have different requirements and lifecycles.
- **Which algorithm was negotiated?** A new suite must not accidentally derive the same key as an old suite.
- **Which context/object is being protected?** If keys span multiple tenants, channels, or message types, cross-context/key-confusion must be prevented.

Using HKDF helps **normalize the material, derive multiple keys with distinct labels, and bind them to context**. A KDF cannot fix flaws such as leaked private keys, forged public keys, or protocol designs lacking authentication.

### 3.2. What Happens If You Just Slice the Secret?

Example mistake:

~~~java
// Do not do this:
byte[] raw = agreement.generateSecret();
byte[] encryptionKey = Arrays.copyOfRange(raw, 0, 16);
byte[] macKey = Arrays.copyOfRange(raw, 16, 32);
~~~

This is not a vetted key schedule. The two slices have no purpose labels, are not derived from transcript/roles, and assume raw bytes have independent cryptographic properties suited to every algorithm. The right approach is **one HKDF-Extract**, followed by **HKDF-Expand with full labels and explicit lengths** per key.

If a protocol feeds one key into multiple KDFs without domain separation, output collisions or key confusion can occur. Never invent `SHA-256(Z + "enc")` out of habit; use HKDF or a standard KDF per specification.

## 4. HKDF-HMAC-SHA256: Extract and Expand

**HKDF** (HMAC-based Extract-and-Expand Key Derivation Function, RFC 5869) has two stages:

### 4.1. Extract: Normalizing Input Secret Material

~~~text
PRK = HKDF-Extract(salt, IKM)
    = HMAC-Hash(key = salt, message = IKM)
~~~

With `HmacSHA256`, PRK is **32 bytes** long. `salt` may be public; it is not a password/pepper and does not need to be secret. RFC 5869 handles an absent salt by using `HashLen` zero bytes; however, when a protocol specifies a salt, **both sides must use the exact same bytes**, never arbitrarily substituting an empty string, timestamp, or different digest.

Salt may be a public handshake value or derived deterministically from transcript components per spec; the example below computes a labeled SHA-256 value from the transcript so both sides compute the same salt. **Salt does not authenticate identity**, nor does it replace signature/certificate checks or stop MITM.

Extract concentrates potentially structured IKM into a PRK suitable for Expand; it does not increase the true entropy of a weak input. Raw ECDH secrets must still follow algorithm rules, public-key validation, and protocol/provider checks for anomalous shared secrets.

### 4.2. Expand: Creating Purpose-Specific Keys

~~~text
OKM = HKDF-Expand(PRK, info, L)

T(0) = empty
T(1) = HMAC(PRK, T(0) || info || 0x01)
T(2) = HMAC(PRK, T(1) || info || 0x02)
...
OKM  = first L bytes of T(1) || T(2) || ...
~~~

Where:

- `PRK`: secret input to Expand, held only by authorized parties.
- `info`: bytes describing the context and derivation purpose, e.g., `"c2s/aes-gcm"`; **not a secret key**.
- `L`: output length **in bytes**, capped at `255 × HashLen`; for SHA-256 this is **8160 bytes**. An AES-128 traffic key needs 16 bytes; HMAC-SHA256 typically uses a key of appropriate designed length such as 32 bytes.
- Blocks have a 1-byte counter starting from **`0x01`**, not the ASCII string `"1"` or a 4-byte integer.

Given the same `PRK`, `info`, and `L`, HKDF-Expand **returns the same bytes**. That determinism is how both parties align. To get a different key for a different purpose, you must use **different info/labels**; PRK must never be sent to client logs or stored alongside public ciphertext.

### 4.3. Distinguishing HKDF from PBKDF2

| HKDF | PBKDF2/Argon2id/scrypt |
| --- | --- |
| Used when you already have **strong secret key material**, like an X25519 secret or random master key | Used for **human-chosen passwords**, which typically have low entropy |
| Goal is extract/expand and context-based key separation | Goal is to make offline password guessing slow/expensive |
| `info` and purpose labels play a central role | Salt, work factor/cost, and password-hashing mechanisms are central |
| Cannot turn a guessable password into a brute-force-resistant secret | Designed specifically to raise the cost of password-guessing attacks |

Never use HKDF alone as a new password-hashing scheme, and do not run PBKDF2 on an ECDH secret out of habit when the protocol specifies HKDF.

## 5. `info`, Transcript, and Context Binding

A mature design must agree **not only on HKDF as the algorithm, but on the exact bytes of `info` and salt**. For example, `info` may include:

| Component | Why is it important? |
| --- | --- |
| **Protocol ID/version** | Avoids accidentally reusing the same key across different protocols or versions |
| **Algorithm suite** | Ties the key to the chosen X25519, HKDF-SHA256, AES-GCM/AEAD mode |
| **Handshake transcript hash** | Binds to negotiated messages, public keys, nonces, roles, and defined fields |
| **Identity or peer binding** | Distinguishes communication with the specific authenticated peer |
| **Direction/role** | `c2s` differs from `s2c`, initiator differs from responder |
| **Purpose label** | `enc`, `mac`, `wrap`, `confirm` produce distinct outputs |
| **Tenant/channel/record context** | Prevents key confusion across usage domains when required by business logic |
| **Epoch/rekey counter** | Transitions to new keys with clear context/periods |

**Do not concatenate strings ambiguously**, such as:

~~~text
info = tenant + ":" + channel + ":" + purpose

("a:b", "c", "enc") and ("a", "b:c", "enc")
  → can produce the exact same string if joined solely with ":"
~~~

Instead, define an **unambiguous binary encoding**: each field has a fixed length or length prefix, defined field order, UTF-8 charset, version, and canonical ID representation. The Java example below uses `DataOutputStream.writeInt(length)` (4-byte big-endian) followed by the exact field bytes.

### 5.1. What Is a Handshake Transcript?

A transcript is the **exact sequence of messages/values in a key-agreement session**, such as version, suite, both public keys, authenticated identities, nonces, and negotiated options. Both sides compute the same `transcriptHash` over canonicalized bytes and feed it into the key schedule.

~~~text
transcriptBytes = encode(
    protocol/version,
    offered/chosen cipher suite,
    initiator role and public key,
    responder role and public key,
    relevant identities/nonces ...
)
transcriptHash = SHA-256(transcriptBytes)
info = encode("key-schedule/v1", suite, transcriptHash, purpose)
~~~

**Do not misunderstand:** putting a transcript hash into HKDF **does not authenticate the transcript on its own**. If an attacker controls the exchange and neither side verifies public keys/identities, the attacker can still run two separate X25519 sessions and sit in the middle. Transcript binding helps prevent key confusion and supports authentication, but **real authentication is required** (properly configured TLS, signatures over the transcript, PSK authentication, or a vetted AKE protocol).

### 5.2. A Handshake May Need Key Confirmation

Both sides computing the same shared secret does not prove the peer received the right messages and holds the same key. A protocol can use a **handshake Finished/confirmation MAC** from a dedicated key, bound to the transcript **with the right direction**. This detects mismatches and confirms the peer knows the current secret, but **without prior/proper identity authentication in the protocol**, key confirmation **does not stop a MITM** running two separate sessions.

Never use the AES-GCM traffic key to sign arbitrary Finished messages; if a confirmation key is needed, **derive a dedicated `confirm` label**, or use a standard protocol key schedule such as TLS 1.3 rather than assembling your own.

## 6. Separating Keys by Direction and Purpose

From one session PRK, derive **distinct labeled outputs**:

~~~text
K_c2s_enc   = HKDF-Expand(PRK, info("c2s/aes-gcm"),      16)
K_s2c_enc   = HKDF-Expand(PRK, info("s2c/aes-gcm"),      16)
K_wrap      = HKDF-Expand(PRK, info("wrap/aes-kw"),      16)
K_hmac      = HKDF-Expand(PRK, info("auth/hmac-sha256"), 32)
K_confirm_c = HKDF-Expand(PRK, info("confirm/client"),   32)
K_confirm_s = HKDF-Expand(PRK, info("confirm/server"),   32)
~~~

These are **illustrative labels** for a hypothetical protocol. In real designs, both sides must follow a single specification and **never invent extra keys/purposes ad hoc**. HKDF produces distinct values per label under the assumption that HMAC acts as a PRF; there is no absolute mathematical promise of “zero collisions ever”, but accidental collision probability at proper lengths is negligible.

| Key | Used by | Primitive | Purpose |
| --- | --- | --- | --- |
| `K_c2s_enc` | Client encrypt → Server decrypt | AES-GCM | Client → server traffic |
| `K_s2c_enc` | Server encrypt → Client decrypt | AES-GCM | Server → client traffic |
| `K_wrap` | Party authorized to wrap/unwrap DEKs | AES Key Wrap / KEK | Protecting other data keys |
| `K_hmac` | Party needing non-AEAD message authentication per protocol | HMAC-SHA256 | Authenticating a dedicated message type, not shared with GCM by default |
| `K_confirm_*` | Party responsible for handshake confirmation | MAC/protocol Finished | Verifying handshake with separate label/direction |

**Directional naming:** Client and server must **both agree** on `c2s`/`s2c`, not each side labeling its own key `"send"` and expecting them to match. In a peer-to-peer connection without fixed client/server roles, establish `initiator`/`responder` roles or an authenticated ordering rule. If both sides invert roles, key mismatch or key reflection can occur.

**Purpose separation is not nonce separation:** Even with two distinct AES-GCM keys, **each key must still use a unique nonce for every encryption** under that key. Nonce/replay sequencing is the next problem. If deriving an IV base from the secret as well, use an **`iv` label distinct from `key`**, combined with a sequence number per a vetted protocol.

### 6.1. Key Lifecycle and Rekeying

A single traffic key must not be used for an unlimited number of messages. Systems need policy limits matched to the algorithm and nonce model, for example:

- Allocate a unique 96-bit nonce for each AES-GCM encryption under a key; coordinate counters across threads/processes or use a vetted nonce strategy.
- Track/limit message counts and byte volumes under one traffic key, rotating keys per security policy.
- When rekeying from a prior secret, use a defined **KDF epoch/sequence label**, changing context so the same key is never re-derived; prevent key rollback.
- Manage retention/zeroization of old secrets once no longer needed for decryption, while satisfying operational/recovery requirements.
- If reusing a master secret to wrap stored DEKs, **KEK lifetimes differ from traffic key lifetimes**; do not arbitrarily couple their lifetimes simply because both came from one PRK.

## 7. Is the Shared Secret Authenticated? MITM Risks

**Plain X25519/ECDH is secret agreement, not a digital signature.** Both sides compute the same secret if the input public key truly belongs to the peer, but an attacker on the channel can swap public keys:

~~~text
Alice ---- A_pub ----> Mallory ---- M1_pub ----> Bob
Alice <--- M2_pub ---- Mallory <--- B_pub ----- Bob

Alice ↔ Mallory: Z1 (secret of the spoofed connection)
Mallory ↔ Bob:   Z2 (secret of the spoofed connection)
Alice and Bob do not directly share the same secret.
Mallory can decrypt and re-encrypt data between both sides.
~~~

In this scenario, valid HKDF execution and perfect key separation **do not stop the attacker** without verifying the peer's public identity. You need an **authenticated key exchange (AKE)**: a signature over the transcript with a trusted key, a certificate verified for the right identity, a securely distributed PSK, or an independently audited authenticated key-agreement protocol. For network applications, **TLS 1.3** already implements the key schedule and authentication; prefer TLS over building a custom X25519 handshake.

Beyond MITM, other checks are essential:

- Public keys received from the network must be **parsed/validated per algorithm**; reject mixed curves/algorithms, wrong lengths, or special values that produce unsafe secrets per standard/provider.
- For X25519, implementations/protocols must handle **low-order public inputs / all-zero shared secrets** per algorithm rules. Rely on trusted provider/library checks and specification rules rather than assuming parseable public keys are sufficient.
- If long-term private keys are used across multiple sessions, consider **forward secrecy**: per-session ephemeral keys are typically critical in authenticated protocols.
- Authenticating identity does not grant resource access; you still need **authorization**, tenant boundaries, endpoint binding, and safe logging.

The standalone example in section 9 only simulates two parties in the same process and **does not prove a MITM-resistant network channel or authenticate Alice/Bob**.

## 8. Key Wrapping: KEK, DEK, and Separation of Privileges

In envelope encryption, a system typically generates a **random DEK** to encrypt bulk data, then uses a **KEK** to wrap the DEK:

~~~text
                 DEK (AES random)
                       |
             +---------+---------------------+
             |                               |
    AES-GCM Encrypt(data)            AES-KW Wrap(DEK, KEK)
             |                               |
    ciphertext + tag                wrapped DEK
             \                              /
              +---- store with metadata ----+
~~~

**DEK (Data Encryption Key)** and **KEK (Key Encryption Key)** serve different roles and should not share the same bytes. When a key schedule is authorized to derive a KEK, use a dedicated label such as `"wrap/aes-kw"`; never reuse `K_c2s_enc` as a KEK.

**AES Key Wrap (AES-KW)** is a key-material wrapping algorithm; Java 17 providers commonly support the `"AESWrap"` transformation in JCE. It is not a cipher mode for arbitrary metadata or long payloads; with RFC 3394 AES-KW, the wrapped key input must satisfy the algorithm's length/block rules. Systems that must protect **associated metadata** or arbitrary-length keys may need AES-KWP or AEAD wrapping per specification.

- **Never output a wrapped DEK and discard KEK-identifying metadata.** You need key ID/version/algorithm to unwrap after rotation.
- **Never assume AESWrap binds tenant/record IDs on its own**. AES-KW checks integrity of the wrapped key material, but takes no AAD like AES-GCM. If metadata determines the object/algorithm, bind it via proper protocol/authenticated metadata design.
- For long-term stored keys, **KEKs typically come from a KMS/HSM or managed key hierarchy**, not from a short-lived traffic shared secret discarded after a network session. The example below wraps a DEK with a session-derived key solely to demonstrate **key-purpose separation**, not to recommend a production storage workflow.
- Do not confuse **key wrapping** with sending a plaintext DEK over an “encrypted” unauthenticated channel, or with Base64-encoding a key.

## 9. Complete Java 17+ Example: X25519, HKDF, AES-GCM, AESWrap

The following program uses JCA/JCE in JDK 17+ with no Maven dependencies. It performs:

1. Verification of HKDF Extract/Expand against **RFC 5869 test vector 1** (without printing secret bytes).
2. Generation of two X25519 key pairs, with each side computing the shared secret; prints a **match check** without exposing the secret.
3. Hashing of a length-prefixed encoded handshake transcript; derives a public salt from the transcript using a **hypothetical demo convention**.
4. Extracts two PRKs with HMAC-SHA256; Expands `c2s/aes-gcm`, `s2c/aes-gcm`, `wrap/aes-kw`, and `auth/hmac-sha256` keys with **independent labels/contexts**.
5. Uses the c2s AES-GCM key to encrypt and the other side to decrypt; wrong direction/wrong context fails the authentication tag.
6. Wraps an AES DEK with the `wrap` key and the other side unwraps it successfully.

**Save as `KeyScheduleDemo.java`:**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class KeyScheduleDemo {
    static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    // Unambiguous framing: 4-byte length (big-endian) + bytes.
    static byte[] frame(byte[]... fields) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        for (byte[] f : fields) {
            out.writeInt(f.length);
            out.write(f);
        }
        out.flush();
        return bytes.toByteArray();
    }

    static byte[] sha256(byte[] bytes) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(bytes);
    }

    static byte[] agree(PrivateKey me, PublicKey peer) throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(me);
        agreement.doPhase(peer, true);
        return agreement.generateSecret();
    }

    // HKDF-Extract (RFC 5869), SHA-256 HashLen = 32.
    static byte[] extract(byte[] salt, byte[] ikm) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                salt == null ? new byte[32] : salt, "HmacSHA256"));
        return mac.doFinal(ikm);
    }

    // HKDF-Expand with exact T(i) blocks, counter starting at 0x01.
    static byte[] expand(byte[] prk, byte[] info, int length)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(prk, "HmacSHA256"));
        int hashLen = mac.getMacLength();
        if (length < 1 || length > 255 * hashLen) {
            throw new IllegalArgumentException("Bad HKDF length");
        }
        byte[] okm = new byte[length];
        byte[] last = new byte[0];
        int offset = 0;
        for (int counter = 1; offset < length; counter++) {
            mac.update(last);
            mac.update(info);
            mac.update((byte) counter);
            byte[] block = mac.doFinal();
            int n = Math.min(block.length, length - offset);
            System.arraycopy(block, 0, okm, offset, n);
            offset += n;
            Arrays.fill(last, (byte) 0);
            last = block;
        }
        Arrays.fill(last, (byte) 0);
        return okm;
    }

    static byte[] info(String purpose, byte[] transcriptHash)
            throws Exception {
        return frame(
                utf8("lesson-key-schedule/v1"),
                utf8("X25519-HKDF-SHA256"),
                transcriptHash,
                utf8(purpose));
    }

    static byte[] seal(byte[] aesKey, byte[] nonce, byte[] aad, byte[] plain)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(aesKey, "AES"),
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(plain);
    }

    static byte[] open(byte[] aesKey, byte[] nonce, byte[] aad,
            byte[] cipherAndTag) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"),
                new GCMParameterSpec(128, nonce));
        cipher.updateAAD(aad);
        return cipher.doFinal(cipherAndTag);
    }

    static boolean rejects(byte[] aesKey, byte[] nonce, byte[] aad,
            byte[] encrypted) throws Exception {
        try {
            open(aesKey, nonce, aad, encrypted);
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        // RFC 5869 TC1 vector (IKM=0x0b * 22), verify HKDF.
        byte[] ikm = new byte[22];
        Arrays.fill(ikm, (byte) 0x0b);
        byte[] testSalt = HexFormat.of().parseHex(
                "000102030405060708090a0b0c");
        byte[] testInfo = HexFormat.of().parseHex(
                "f0f1f2f3f4f5f6f7f8f9");
        byte[] known = HexFormat.of().parseHex(
                "3cb25f25faacd57a90434f64d0362f2a"
                + "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
                + "34007208d5b887185865");
        System.out.println("HKDF RFC5869       = "
                + MessageDigest.isEqual(known,
                        expand(extract(testSalt, ikm), testInfo, 42)));

        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();
        byte[] aliceSecret = agree(alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(), alice.getPublic());
        System.out.println("Shared match       = "
                + MessageDigest.isEqual(aliceSecret, bobSecret));
        System.out.println("Shared bytes       = " + aliceSecret.length);

        // Hypothetical transcript: two public keys and roles in fixed order.
        byte[] transcriptHash = sha256(frame(
                utf8("handshake-demo-v1"),
                utf8("initiator=Alice"),
                alice.getPublic().getEncoded(),
                utf8("responder=Bob"),
                bob.getPublic().getEncoded()));
        byte[] salt = sha256(frame(utf8("extract-salt/v1"), transcriptHash));
        byte[] aPrk = extract(salt, aliceSecret);
        byte[] bPrk = extract(salt, bobSecret);

        byte[] aC2s = expand(aPrk,
                info("c2s/aes-gcm", transcriptHash), 16);
        byte[] bC2s = expand(bPrk,
                info("c2s/aes-gcm", transcriptHash), 16);
        byte[] s2c = expand(aPrk,
                info("s2c/aes-gcm", transcriptHash), 16);
        byte[] aWrap = expand(aPrk,
                info("wrap/aes-kw", transcriptHash), 16);
        byte[] bWrap = expand(bPrk,
                info("wrap/aes-kw", transcriptHash), 16);
        byte[] macKey = expand(aPrk,
                info("auth/hmac-sha256", transcriptHash), 32);

        System.out.println("C2S key bytes      = " + aC2s.length);
        System.out.println("Wrap key bytes     = " + aWrap.length);
        System.out.println("MAC key bytes      = " + macKey.length);
        System.out.println("Same role keys     = "
                + MessageDigest.isEqual(aC2s, bC2s));
        System.out.println("C2S != S2C         = "
                + !MessageDigest.isEqual(aC2s, s2c));
        System.out.println("C2S != wrap        = "
                + !MessageDigest.isEqual(aC2s, aWrap));

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] sealed = seal(aC2s, nonce, transcriptHash,
                utf8("hello key schedule"));
        System.out.println("Decrypt C2S        = "
                + new String(open(bC2s, nonce, transcriptHash, sealed),
                StandardCharsets.UTF_8));
        System.out.println("Wrong role rejected= "
                + rejects(s2c, nonce, transcriptHash, sealed));
        byte[] wrongContext = sha256(utf8("different transcript"));
        byte[] wrongKey = expand(bPrk,
                info("c2s/aes-gcm", wrongContext), 16);
        System.out.println("Wrong ctx rejected = "
                + rejects(wrongKey, nonce, transcriptHash, sealed));

        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(128);
        SecretKey dataKey = keyGenerator.generateKey();
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, new SecretKeySpec(aWrap, "AES"));
        byte[] wrapped = wrapper.wrap(dataKey);
        Cipher unwrapper = Cipher.getInstance("AESWrap");
        unwrapper.init(Cipher.UNWRAP_MODE,
                new SecretKeySpec(bWrap, "AES"));
        Key restored = unwrapper.unwrap(
                wrapped, "AES", Cipher.SECRET_KEY);
        System.out.println("Wrapped DEK matches= "
                + MessageDigest.isEqual(
                        dataKey.getEncoded(), restored.getEncoded()));

        // Shorten lifetime of application-held secrets; provider may hold copies.
        Arrays.fill(aliceSecret, (byte) 0);
        Arrays.fill(bobSecret, (byte) 0);
        Arrays.fill(aPrk, (byte) 0);
        Arrays.fill(bPrk, (byte) 0);
        Arrays.fill(aC2s, (byte) 0);
        Arrays.fill(bC2s, (byte) 0);
        Arrays.fill(s2c, (byte) 0);
        Arrays.fill(aWrap, (byte) 0);
        Arrays.fill(bWrap, (byte) 0);
        Arrays.fill(macKey, (byte) 0);
    }
}
~~~

Compile and run:

~~~bash
javac KeyScheduleDemo.java
java KeyScheduleDemo
~~~

Expected output **remains stable even though keypairs, nonce, and DEK are randomly generated**:

~~~text
HKDF RFC5869       = true
Shared match       = true
Shared bytes       = 32
C2S key bytes      = 16
Wrap key bytes     = 16
MAC key bytes      = 32
Same role keys     = true
C2S != S2C         = true
C2S != wrap        = true
Decrypt C2S        = hello key schedule
Wrong role rejected= true
Wrong ctx rejected = true
Wrapped DEK matches= true
~~~

### 9.1. Step-by-Step Explanation

1. **`HKDF RFC5869 = true`:** verifies the 42-byte output against the standard vector, catching mistakes in the formula, counter byte, or block copying. Do not hand-roll HKDF in production if an appropriate standard library/provider is available.
2. **`Shared match = true`:** `KeyAgreement("X25519")` gives both sides identical bytes with matching private/public pairs. `Shared bytes = 32` is the X25519 output length; it is not a claim that this is already a traffic key.
3. **`transcriptHash`:** encodes length-prefixed fields, role order, and both public keys, then hashes with SHA-256. The demo derives `salt` from this hash using a custom convention so both sides match. Real protocols must have **explicitly specified messages and salt/transcript rules**—do not copy the demo as a standard handshake.
4. **`aPrk/bPrk`:** both sides Extract with the same IKM/salt to get the same PRK; each `expand` with the same PRK but **different info purpose** yields different outputs.
5. **`Same role keys = true`:** Alice sends with `aC2s`, Bob receives with `bC2s`. Bob does not use the `"s2c"` label when receiving c2s traffic. `C2S != S2C` demonstrates distinct labels in this demo run; do not treat a single equal/unequal run as a cryptographic proof over all inputs.
6. **`Wrong role rejected` / `Wrong ctx rejected`:** AES-GCM rejects ciphertext when using a different key; `Wrong ctx` is derived via Expand with a different transcript. This illustrates key binding; **it does not prove MITM resistance**.
7. **`Wrapped DEK matches`:** the `wrap` key derived on both sides is used with `AESWrap`. Wrapping protects the DEK itself during transfer under this KEK; it does not replace KMS policy, authorization, or metadata protection.

Byte arrays are cleared with `Arrays.fill` after use to shorten secret lifetime in application-controlled memory. This does not guarantee wiping copies inside the provider/JVM or secrets remaining in `PrivateKey`/`SecretKey` objects. The demo has no network communication, certificates, key confirmation, replay protection, or persistence; those layers must be added via a **standard protocol**.

## 10. KDF and Real Messages: Choosing the Right AAD, IV, and Role Context

Purpose separation is only part of the picture. When storing/transmitting encrypted data, the receiver also needs the right **nonce, ciphertext, authentication tag, suite, key epoch, and sequence**:

~~~text
handshake metadata:
    protocol version, suite, roles, public keys, identity/auth evidence
    -> transcript hash -> HKDF context

application record:
    version | epoch | sequence | nonce | ciphertext || tag
    AAD = canonical(version, epoch, direction, sequence, type, ...)
    key = K_direction_for_epoch
~~~

**Key derivation context and AEAD AAD are two distinct layers.** The KDF binds keys to a session/role; AAD binds **each individual message** to unencrypted metadata. Having transcript binding in the KDF still does not protect all application header fields, and proper AAD still cannot fix duplicate nonces.

A complete record may need:

- **Key epoch/generation**: selects the right key after rekeying; prevents unauthorized use of old epochs per policy.
- **Sequence / message ID**: authenticates ordering/prevents replay; a valid tag on an old message remains valid if the protocol does not remember having seen it.
- **Nonce**: 96 bits for standard GCM; unique under a given traffic key.
- **Ciphertext + tag**: never accept plaintext upon `AEADBadTagException`/verification failure.
- **Header/AAD**: binds to the exact channel, tenant, type, or direction that must be protected from tampering.
- **Algorithm/key ID**: uses mapping and verification policy against downgrade, preventing an attacker from steering arbitrary key/suite selection.

**Never concatenate untrusted data into HKDF `info` expecting security to appear automatically**: you must validate/check critical context before treating it as a trusted claim, or bind it through an authenticated protocol transcript.

## 11. Common Design Scenarios

### 11.1. Bidirectional Chat Application

A client/server session uses X25519 to establish Z. If the same `K_enc` is chosen for both sending and receiving, client and server may both start nonce counters at 0 and accidentally reuse the **same (key, nonce)** in AES-GCM. Separating `K_c2s_enc` and `K_s2c_enc` with distinct labels reduces domain-overlap risk, yet **each direction must still guarantee unique nonces**. Use protocol sequences/AAD and replay protection.

### 11.2. Same Library Used by Two Products

Product A has `"sync/v1"` and B has `"backup/v1"`, sharing the same root secret in a key hierarchy. If both call `HKDF-Expand(PRK, "enc", 16)`, they could derive the same key. Put distinct **protocol/product IDs, versions, and usage labels** into `info` to prevent cross-protocol key reuse. If the design requires tenant or device isolation, put meaningful, verified IDs into the context.

### 11.3. Wrapping DEKs for Record Storage

A system stores encrypted record ciphertexts under a DEK, with the DEK wrapped by a KEK in a KMS. On rotation, `keyId` metadata is needed to locate the right KEK; by rewrapping the DEK, you may avoid re-encrypting all data. **Long-term storage KEKs should not by default be derived from an ephemeral X25519 session Z**, because once the session ends that KEK disappears or lacks recovery mechanisms. Design a separate key hierarchy, unwrap permissions, auditing, and backup for storage.

### 11.4. Handshake Confirmation

Alice/Bob compute the shared secret and PRK, then compute a confirmation MAC over the transcript using `K_confirm_client`/`K_confirm_server`. This detects if one party lacks the secret or has a different transcript, but **does not prove identity** if public keys are unauthenticated: a MITM can produce valid confirmation MACs on each session it participates in. You need an AKE design with real identity binding.

### 11.5. Algorithm Migration and Rekeying

When a system upgrades from AES-128-GCM to AES-256-GCM or another suite, do not merely change the length from 16 to 32 bytes while omitting the **suite ID in transcript/info**. Algorithm negotiation must resist downgrade, and both sides must derive matching key lengths, key IDs, and be authenticated. A server supporting old and new versions needs explicit versioning and a deprecation policy for weak suites.

## 12. Frequent Security Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using the first 16/32 bytes of an ECDH secret directly as an AES key | No context/purpose/role separation; ad-hoc key schedule | HKDF Extract/Expand per protocol with full labels |
| Taking SHA-256(Z) and reusing it for all purposes | Fails to separate encryption, MAC, and wrapping | HKDF Expand with distinct `info` per purpose |
| Client uses `"send"` and Server also uses `"send"`, confusing direction | Sides derive mismatched keys or identical keys for both directions | Define immutable `c2s/s2c` or initiator/responder labels |
| Same HKDF `info` for MAC and AES | Cross-primitive key reuse | Domain separation via labels/algorithms/roles |
| `info = a + ":" + b` without field framing | Two context tuples can produce the same byte string | Length-prefixed or canonical binary encoding |
| Omitting version and suite binding | Keys across versions/protocols can collide or be confused | Include version, suite, and transcript hash in `info` |
| Treating a transcript hash as a digital signature | Does not prevent MITM swapping public keys | Use AKE with certificate/signature/PSK authentication |
| Assuming HKDF salt must be a secret | Hard to synchronize across parties, wrong assumption | Salt is typically public; follow exact protocol rules |
| Treating HKDF as a password KDF | Weak passwords are cracked very quickly | Use Argon2id/scrypt/PBKDF2 for passwords |
| Using one AES-GCM key starting at nonce 0 on both sides | Nonce reuse breaks GCM security | Direction-separated keys + unique nonce per key |
| Deriving a KEK from a short-lived session to store long-term DEKs | After restart/session end, no KEK remains to unwrap | Use KMS/HSM/storage key hierarchy |
| Assuming AES-KW has AAD like AES-GCM | No automatic metadata binding | Authenticate context/metadata via separate protocol layer |
| Logging `generateSecret()` or PRK | Compromises all derived traffic/wrap keys | Never print/log secrets; minimize lifetime in RAM |
| Skipping public key validation or X25519 all-zero checks | May accept malformed or unsafe inputs | Parse/validate per algorithm and provider/standard |
| Not bounding HKDF `L` | Violates or overflows HKDF output limit | Enforce `1 ≤ L ≤ 255×HashLen` in demos/implementations |
| Testing only happy-path encrypt/decrypt without negative tests | Misses context, role, length, and tamper bugs | Test expected failures, key separation, and interoperability |
| Using demo code as a production network protocol | Lacks identity, replay, metadata, and rotation | Use TLS 1.3 or a standard AKE/record protocol |

## 13. Testing the Key Schedule and Cross-System Interoperability

**Verify bytes, not just whether users see readable output.** Two implementations in Java/Python/Go might both call X25519/HKDF yet frame public keys or labels differently, deriving different keys.

A test suite should include:

1. **RFC 5869 HKDF known-answer vectors:** fixed IKM/salt/info/length inputs and expected PRK/OKM. The demo runs vector 1.
2. **Role symmetry:** Alice's c2s encryption key must equal Bob's c2s decryption key; c2s differs from s2c and wrap.
3. **Purpose separation:** changing label `"enc"` to `"wrap"` must produce a different key; using the old label to unwrap must fail.
4. **Context separation:** changing transcript, suite version, bound tenant/channel, or identity must yield different keys.
5. **Transcript canonicalization:** identical fields with different serialization/byte order produce different hashes; specify and test exact field order/lengths.
6. **Negative AEAD tests:** wrong key, nonce, AAD, tag, or modified ciphertext must be rejected; never emit unauthenticated plaintext.
7. **Public key validation:** malformed peer keys, wrong curves, wrong encodings, low-order inputs, and safe error mapping.
8. **Replay/sequence:** old valid packets must not be accepted as new messages if the protocol requires replay protection; track state properly.
9. **Rekey/rotation:** new epochs derive distinct keys, select the right key ID, and reject policy-disallowed rollbacks.
10. **Wrap/unwrap:** DEKs wrapped with the right KEK unwrap cleanly; wrong KEKs or tampered wrapped bytes must fail per primitive/provider.
11. **Cross-provider:** Java JCE providers and C/Go/Python libraries must agree on X25519 encoding, HKDF info, nonce format, AES-KW variant, and test vectors—do not test only simple ASCII labels.

**Testing note:** known-answer fixtures may contain fixed public dummy bytes, but **never log production secrets** for comparison. Use `MessageDigest.isEqual` on bytes in checks; production verification should use primitive verification APIs and consider timing behavior per threat model.

## 14. Exercises (with Solutions)

**Exercise 1.** Two X25519 peers share a 32-byte secret. Should they use the entire secret as an AES-256 key and also reuse it as an HMAC key?

**Answer:** No. You need an HKDF Extract/Expand key schedule with distinct labels and lengths for AES and HMAC. Having the same size does not ensure proper purpose or context isolation.

**Exercise 2.** Why do `K_c2s = HKDF-Expand(PRK, "c2s", 16)` and `K_s2c = HKDF-Expand(PRK, "s2c", 16)` differ?

**Answer:** To **separate the two traffic directions**, avoiding accidental key reuse across bidirectional traffic and role/nonce confusion. Each key still requires unique nonces.

**Exercise 3.** Must HKDF `salt` and `info` be kept secret?

**Answer:** Usually **no**. They can be public, though they must be consistent and bound into the protocol, whereas IKM, PRK, and OKM must remain secret. Salt does not replace identity authentication.

**Exercise 4.** If you change `info` from `"wrap"` to `"enc"`, will you get the same key?

**Answer:** No. HKDF-Expand with different labels is designed to produce **computationally independent keys** under the PRF assumption. Both sides must use the same label for the same purpose; mismatched labels cause decrypt/unwrap failure.

**Exercise 5.** If Alice and Bob include the transcript hash in HKDF `info` without signing or verifying public keys, have they prevented MITM?

**Answer:** Not yet. Mallory can run two separate sessions with Alice and Bob, each having a valid transcript/key. You need real identity/public-key authentication via an AKE or standard protocol.

**Exercise 6.** Two applications both use `info = "enc"` with the same PRK. What bug can occur?

**Answer:** **Cross-protocol key reuse/confusion**. You must include distinct protocol ID/version, cipher suite, purpose, direction, and context fields.

**Exercise 7.** In Java, `new GCMParameterSpec(128, nonce)` specifies a 128-bit tag. Is that related to an AES-128 key being 16 bytes?

**Answer:** Those are **two separate parameters**: AES-128 uses a 128-bit (16-byte) key; a 128-bit GCM tag is the authentication tag length. Additionally, a 96-bit (12-byte) nonce is typically used. Never confuse tag size with key size.

**Exercise 8.** A DEK is wrapped using a KEK derived from an ephemeral X25519 shared secret, then stored for 5 years. What is the problem?

**Answer:** The KEK disappears with the session if not persisted/recovered; it is unsuitable for long-term storage without a designed key hierarchy. Use a KEK managed in a KMS/HSM or persistent key-storage system with rotation, backup, and authorization.

**Exercise 9.** The c2s/s2c AES-GCM keys are separated; two processes sending in the same direction both start a nonce counter at 0 under the same key. Is this safe?

**Answer:** No. Nonces must be unique **across all encryptions under a key**, not merely per process. You need counter partitioning/coordination or a vetted nonce strategy.

**Exercise 10.** An AES-KW record contains a valid wrapped key, but the tenant/record ID metadata was altered. Does AES-KW automatically detect the altered tenant?

**Answer:** No. AES-KW checks the wrapped key material itself and **has no tenant/record ID AAD** like AES-GCM. Metadata must be bound via authentication/authorization layers or a wrapping format with AAD per specification.

## 15. Design and Implementation Checklist

- [ ] Public-key agreement uses X25519/ECDH via standard libraries; **peer keys/identities are authenticated** by AKE/TLS/certificate/PSK policy.
- [ ] Never use raw shared secrets directly as AES/MAC/KEK; handle malformed public keys and all-zero secrets per standard/provider.
- [ ] HKDF-Extract uses proper HMAC hash/salt/IKM; HKDF-Expand uses exact info/counter/length bytes; verified with known-answer tests.
- [ ] `info` data is unambiguously framed, containing **protocol/version/suite/transcript/role/purpose** and any required domain bindings.
- [ ] Keys for `c2s`, `s2c`, MAC, confirmation, and wrapping use distinct labels and primitive-appropriate lengths.
- [ ] With AES-GCM, use a **unique nonce** per encryption under each key, verify tags before using plaintext, and bind message metadata in AAD as needed.
- [ ] Enforce replay protection, sequence/epoch tracking, key-usage limits, and rekey/rotation per protocol.
- [ ] DEKs encrypt data, KEKs wrap DEKs; long-term KEKs use proper key management rather than binding to ephemeral sessions.
- [ ] Never log or publicly store private keys, shared secrets, or PRK/OKM; minimize secret lifetime and enforce unwrap permissions.
- [ ] Run interoperability test vectors across implementations, testing negative cases and metadata/algorithm negotiation.
- [ ] If the application needs real-world secure transport, prefer a **vetted standard protocol** (typically TLS 1.3) over stitching key agreement, KDF, and AEAD into a custom handshake.

## 16. Summary

**A shared secret is only the input to a key schedule**, not a single key for everything. With X25519, two parties obtain identical secret bytes; **HKDF-Extract** produces the PRK, and **HKDF-Expand** with canonical `info` and purpose labels derives keys matched to **algorithm, direction, and usage scope**. Handshake/transcript context must be bound, while **identity authentication and algorithm negotiation** remain mandatory per protocol. Separating `c2s/s2c`, AES-GCM, HMAC, and KEK reduces key confusion; combining this with unique nonces, AAD, replay protection, and proper key lifecycles builds a secure cryptographic system.

Algorithm specifications: **RFC 5869 (HKDF)** https://www.rfc-editor.org/rfc/rfc5869 ; **RFC 7748 (X25519/X448)** https://www.rfc-editor.org/rfc/rfc7748 ; **RFC 3394 (AES Key Wrap)** https://www.rfc-editor.org/rfc/rfc3394 . These RFCs define primitives and do not replace designing or auditing an end-to-end authenticated protocol.
