# 23.3. Encrypting Stored Tokens and Managing Encryption Keys

## 1. Why Does an OAuth2 Client Need to Encrypt Tokens at Rest?

In **Spring Security OAuth 2.0 OIDC Client**, an application typically receives an **Access Token** after authorization and may also receive a **Refresh Token** to maintain API access when the Access Token expires. When using `OAuth2AuthorizedClientManager`, Spring Security can reload or update `OAuth2AuthorizedClient` from a store such as an HTTP session, in-memory service, or database.

Storing tokens makes the application more convenient to use, but it also creates a high-value **credential store**. Anyone who reads a valid token can send it to a Resource Server as a Bearer Token if no additional sender-constraining mechanism is in place. For a Refresh Token, the impact can last much longer: an attacker can obtain new Access Tokens until the token is revoked, expires, or the Authorization Server's policy blocks it.

Example of an employee calendar integration system:

~~~text
User Alice
   |
   | OIDC/OAuth2 Login + calendar.read
   v
Spring Boot OAuth2 Client
   |
   +-- Access Token: call Calendar API
   +-- Refresh Token: request new Access Token when needed
   |
   v
OAuth2AuthorizedClientService
   |
   v
Database / backup / replica
~~~

If the database stores tokens in **plaintext**, a leaked backup or a SQL account with `SELECT` privileges can be enough to steal credentials. Therefore, many systems need to encrypt tokens **before writing to the persistence layer**, paired with a key management process separate from the database.

**Lesson objectives:**

- Understand which tokens require protection and which adversaries encryption at rest defends against.
- Distinguish application-layer token encryption from HTTPS, TDE, hashing, JWT signing, and session cookie security.
- Design **authenticated encryption (AEAD)** with AES-GCM, unique nonces/IVs, and **Additional Authenticated Data (AAD)**.
- Manage **Data Encryption Keys (DEKs)** and **Key Encryption Keys (KEKs)** via KMS/HSM, storing `keyId` or `keyVersion` with the ciphertext.
- Integrate encryption into `OAuth2AuthorizedClientService` / repositories without breaking refresh flows, principal ownership, or OIDC Login.
- Organize **key rotation**, legacy data migration, re-encryption, key loss handling, auditing, and incident response.
- Review Java 17 examples, storage formats, decision tables, diagrams, and test scenarios.

> **Foundational principle:** never invent your own encryption algorithm. Use standard primitives, actively maintained libraries, and infrastructure key management services. The Java examples below illustrate **how to use JCA AES-GCM and design boundaries**; production systems require cryptography review, key management, threat modeling, and KMS integration tailored to your infrastructure.

## 2. Credentials Commonly Present in an OAuth2/OIDC Client

| Data Type | Where Is It Used? | Why Must It Be Protected? |
| --- | --- | --- |
| **Access Token** | Sent to Resource Server to access APIs | Can be used to call APIs until the token ceases to be valid |
| **Refresh Token** | Sent to Authorization Server Token Endpoint | Can mint new Access Tokens; typically longer-lived |
| **Client Secret** | Client authentication at Token Endpoint | Can allow a machine/client to obtain tokens when combined with client ID and grant |
| **Private key for `private_key_jwt`** | Signs JWT client assertions | If leaked, allows impersonating the confidential client |
| **ID Token** | Used by OIDC client to verify login identity | Contains identity claims, often sensitive; not used in place of Access Token |
| **Authorization code** | Exchanged once for tokens at Token Endpoint | Sensitive during callback; should not be stored long-term like tokens |
| **Session ID/cookie** | Associates browser with login session | If stolen, compromises session security |

### 2.1. Bearer Tokens Are Especially Sensitive

With an OAuth2 Bearer Token:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

anyone who obtains the token can attempt to use it. Scopes, audience, expiry, sender constraints, or additional verification can reduce damage, but **an Access Token can never be treated as public data**.

### 2.2. Refresh Tokens Need Priority Protection

A Refresh Token is generally never sent to business APIs; it should only be sent to the Token Endpoint. In many systems, it outlives many Access Token expirations. Consequently, stealing a Refresh Token can be far more dangerous than stealing a short-lived Access Token.

The Authorization Server may implement **refresh token rotation**, sender-constrained tokens, or replay detection policies. Those measures help, but **do not replace encrypting Refresh Tokens at rest**.

### 2.3. Should the ID Token Be Encrypted at Rest?

An ID Token can contain personal information, groups, and sensitive claims. If the application stores the ID Token long-term, evaluate confidentiality, retention, and purpose. However, Spring Security's standard `OAuth2AuthorizedClient` focuses on Access Tokens and Refresh Tokens; the ID Token belongs to a different part of OIDC authentication state.

Do not assume encrypting `OAuth2AuthorizedClient` alone automatically protects all `OidcUser`, ID Token, or session authentication data serialized in another store.

## 3. Threat Model: What Does Encryption Protect Against?

A sound design starts with **adversaries, data surfaces, and protection boundaries**, not just picking AES-256.

| Scenario | Does App-Layer Encryption Help? | Limitations |
| --- | --- | --- |
| Theft of database backup | **Yes**, if decryption keys are not in the backup | If backups also include keys or powerful service credentials, protection weakens |
| Abused SQL account running SELECT on token table | **Yes**, if app encrypts before INSERT and DB lacks keys | Attacker can still corrupt/delete rows or overwrite ciphertext |
| Exposed database snapshot/replica | **Yes** | Unencrypted metadata may still be exposed |
| Lost disk/volume | Yes; disk encryption/TDE also plays a role | Must work alongside infrastructure encryption at rest |
| Attacker achieves remote code execution in app | **Not guaranteed**, since the app can call decrypt | Requires runtime isolation, egress policies, secret management, and monitoring |
| Cloud account holds both KMS decrypt + DB read permissions | Limited protection | Needs separation of duties and anomaly alerting |
| Token written to HTTP/application logs | **No**, DB encryption cannot hide plaintext logs | Must redact and never log credentials |
| Browser XSS steals session cookie | Not directly | Must use `HttpOnly`/`Secure`/`SameSite`, CSP, and session security |
| Resource Server accepts token with wrong audience | No | Must validate issuer/audience/scope at the API |
| Refresh Token replay | Not completely | Needs rotation, revocation, and sender constraining if available |

### 3.1. What Must Be Protected

Locations that commonly hold copies of tokens:

~~~text
Spring Security OAuth2AuthorizedClient
  |
  +-- JDBC database / ORM entity
  +-- HTTP session state / Redis
  +-- distributed cache
  +-- backups, replicas, snapshots
  +-- migration/export scripts
  +-- application logs, traces, APM  <-- should never have tokens
  +-- heap dumps / crash artifacts   <-- needs restrictive policies
  +-- support/debug screenshots       <-- should never have tokens
~~~

Application-layer encryption is effective when placed **in front of persistent or shared storage**, and when key management ensures the same party cannot arbitrarily obtain both the ciphertext and the decryption key.

### 3.2. Do Not Promise What Encryption Cannot Do

Encrypting tokens at rest **does not**:

- Stop legitimate application code from reading the token after decryption.
- Stop an attacker with RCE inside the app from invoking the app's decryption capability.
- Automatically revoke an OAuth2 token that was stolen earlier.
- Validate the scope/audience of an Access Token.
- Replace session authorization, access control, MFA, or API security.
- Guarantee safety if keys, ciphertext, and decrypt permissions all sit in the same backup.

Therefore, a strong system uses **defense in depth**.

## 4. Token Encryption vs. Hashing, JWT Signatures, TLS, and TDE

### 4.1. Hashing Does Not Support Calling APIs

If the application needs to send an Access Token to a Resource Server or a Refresh Token to an Authorization Server, it must **recover the original token value**. One-way hashes like SHA-256 do not allow recovering the input.

~~~text
Token -> SHA-256 -> digest
              |
              +-- cannot recover token to call API
~~~

Hashing/HMAC can be useful when you **only need to match tokens** or produce a non-disclosing fingerprint (such as a keyed HMAC fingerprint for deduplication audits). It cannot replace **reversible encryption** for tokens that must be reused.

Do not arbitrarily log short/truncated hashes to identify tokens unless the system has anti-disclosure/correlation policies; even fingerprints can be sensitive data.

### 4.2. Signed JWTs Do Not Mean Encrypted Content

Many Access Tokens or ID Tokens use JWT/JWS format:

~~~text
header.payload.signature
~~~

The signature enables tamper detection and issuer verification using the appropriate algorithm/trusted keys. **The payload can usually be base64url-decoded and read**; a signed JWT does not encrypt its contents by default.

Encrypting a JWT via JWE is a separate mechanism. If a provider issues JWT/JWS tokens, the application may still need to **encrypt them when storing in a database**, especially because the credential value can be replayed.

### 4.3. HTTPS/TLS Protects Data in Transit

HTTPS protects tokens exchanged with the Token Endpoint and Resource Server, provided hostname/certificate validation is properly enforced. However, TLS **does not encrypt a token column already written to a database**.

### 4.4. Database TDE and Disk Encryption

**Transparent Data Encryption (TDE)**, encrypted volumes, and backup encryption protect primarily at the device or storage layer. However, any process authorized to query the database can still receive **plaintext column values**.

**Application-level encryption** ensures the database receives only ciphertext:

~~~text
App memory: Access Token plaintext
     |
     | AES-GCM encrypt
     v
DB column: encrypted payload
~~~

Both layers complement each other: TDE protects the storage medium, while application encryption protects sensitive fields against overly broad DB read permissions.

## 5. Architecture Diagram: Encrypt Before Save, Decrypt After Load

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application Service
    participant M as OAuth2AuthorizedClientManager
    participant Vault as Encrypted Authorized Client Store
    participant KMS as KMS/HSM
    participant DB as Token Database
    participant AS as Authorization Server
    App->>M: authorize(registrationId, principal)
    M->>Vault: loadAuthorizedClient(registrationId, principal)
    Vault->>DB: SELECT encrypted record
    DB-->>Vault: ciphertext + metadata + keyId
    Vault->>KMS: unwrap/resolve matching data key (if needed)
    KMS-->>Vault: key material or crypto operation
    Vault->>Vault: AEAD decrypt + verify tag/AAD
    Vault-->>M: OAuth2AuthorizedClient
    alt Needs refresh or new grant
        M->>AS: Token Endpoint grant request
        AS-->>M: New Access Token / optional Refresh Token
        M->>Vault: saveAuthorizedClient(new client)
        Vault->>KMS: generate/unwrap data key per design
        Vault->>Vault: AEAD encrypt payload + nonce + AAD
        Vault->>DB: UPSERT ciphertext, metadata, key references
    end
    M-->>App: Appropriate authorized client
~~~

In an **envelope encryption** system, obtaining the data key can happen via a `GenerateDataKey` call or a DEK unwrap operation. The KMS may return the plaintext data key to an authorized process, or execute the operation inside hardware/service depending on the product. The diagram does not require sending **raw OAuth2 tokens** to the KMS; the app can use the DEK locally in memory to encrypt the payload.

### 5.1. Where Should Encryption Live?

Typically:

~~~text
OAuth2AuthorizedClientManager
  -> OAuth2AuthorizedClientService / Repository
      -> Encrypted persistence adapter
          -> DAO / JDBC / Redis / session serializer
~~~

Placing encryption at the **persistence adapter** layer lets the application call the manager normally. Do not force every controller to encrypt tokens manually.

### 5.2. Do Not Create a Parallel Plaintext Store

Design to avoid:

~~~text
Manager -> Default JdbcOAuth2AuthorizedClientService -> plaintext DB
                     |
                     +-- custom audit store -> encrypted copy
~~~

because the plaintext copy still exists. Ensure **the actual save path used by Spring Security** passes through the encryption layer, and no other repository/session store unintentionally persists plaintext.

## 6. Appropriate Algorithm: Authenticated Encryption with Associated Data (AEAD)

### 6.1. Why Is "Encryption Only" Insufficient?

An attacker who can read or modify the database might not know the plaintext, yet could **alter ciphertext or swap records**. With encryption that lacks integrity protection, the application risks processing tampered data.

AEAD provides two properties:

1. **Confidentiality:** plaintext cannot be read without the key.
2. **Integrity/authenticity:** if the ciphertext or associated data is modified, decryption fails.

In Java JCA, the standard algorithm is:

~~~java
Cipher.getInstance("AES/GCM/NoPadding");
~~~

AES-GCM supports an **authentication tag** typically 128 bits long and a **nonce/IV** typically 96 bits long.

### 6.2. Recommended Parameters in the Example

| Parameter | Choice in This Lesson | Meaning |
| --- | --- | --- |
| Algorithm | AES-GCM | Encryption with integrity verification |
| AES key | 256-bit if supported by policy/JRE/KMS | Symmetric key for record/token |
| Nonce/IV | 96 bits = 12 bytes | Must differ across encryptions **under the same key** |
| Tag | 128 bits | Detects tampered data |
| AAD | registration/principal/tenant/token kind/record context | Binds ciphertext to its rightful place |
| Key reference | `keyId` / `keyVersion` | Decrypts older records after rotation |
| Format version | e.g., `v1` | Enables controlled format/algorithm upgrades |

### 6.3. A Nonce Is Not a Password or Secret

The nonce/IV is normally stored alongside the ciphertext:

~~~text
version | keyId | nonce | ciphertext_and_tag
~~~

A nonce **does not need to be secret**, but **must never be reused for two different plaintexts under the same AES-GCM key**. Nonce reuse in GCM can severely break both confidentiality and integrity.

For typical traffic, a 96-bit nonce generated via `SecureRandom` is common. For keys encrypting very high volumes, enforce **per-key encryption count limits**, key rotation, and/or deterministic/counter-based nonce uniqueness guarantees. Never use timestamps, user IDs, or a fixed IV.

### 6.4. Every Token Update Must Re-Encrypt with a New Nonce

Refresh Token rotation:

~~~text
Current record:
  accessToken = A1
  refreshToken = R1

Authorization Server refresh succeeds:
  accessToken = A2
  refreshToken = R2

Persistence:
  encrypt new payload with a NEW nonce
  write new ciphertext in an appropriate operation/transaction
~~~

Never reuse the old nonce just because you are updating the same database row.

## 7. AAD: Binding Ciphertext to the Right Owner

**Additional Authenticated Data (AAD)** is data that is not encrypted itself, yet is included in the authentication tag computation. If the AAD during decryption differs from the AAD during encryption, AEAD verification fails.

In an OAuth2 Client, AAD can include:

~~~text
application-domain
format-version
key-id
tenant-id
client-registration-id
principal-name
token-kind
stable-record-id (if available in the system)
~~~

Example:

~~~text
AAD for Alice's Access Token:
  tenant=company-a
  registration=calendar
  principal=alice-sub-123
  kind=access-token

AAD for Bob's Refresh Token:
  tenant=company-a
  registration=calendar
  principal=bob-sub-456
  kind=refresh-token
~~~

Alice's ciphertext **cannot simply be copied** into Bob's row and decrypted validly if the application reconstructs AAD from verified identity.

### 7.1. AAD Must Be Built with Canonical Encoding Rules

Do not concatenate fields using ambiguous delimiters:

~~~text
tenant + "|" + registration + "|" + principal
~~~

if values themselves can contain delimiters or differ in Unicode encoding/canonicalization. In the Java example, **length-prefixed UTF-8** is used per field to avoid ambiguity.

### 7.2. AAD Does Not Authenticate the Request Identity by Itself

If code lets the browser pass `principalName="admin"` or `tenantId="other-tenant"` to fetch tokens from the database, AAD will not fix that **authorization bug**. AAD only provides cryptographic binding; record access permissions must be checked **before loading/decrypting**.

### 7.3. When Changing Principal or Registration

If AAD includes the principal name, changing a user's identifier key makes old ciphertext fail decryption under the new AAD. This is **by design**, not a random bug.

When migrating identity:

1. Read the record using the **old AAD** from a trusted identity source.
2. Decrypt using the valid old key.
3. Re-encrypt with the **new AAD** and a new nonce.
4. Write the new record atomically with version control.
5. Delete or invalidate the old record per migration policy.

With OIDC, a durable user identifier is typically based on **issuer + subject** rather than a mutable display email.

## 8. Encrypted Data Structure and Key Version

Do not store a bare Base64 string and guess the algorithm on decryption. An envelope with explicit metadata supports safe upgrades:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyId": "token-store-key-v3",
  "nonce": "BASE64URL_NONCE",
  "ciphertext": "BASE64URL_CIPHERTEXT_AND_TAG"
}
~~~

This is an **illustrative format**, not a built-in Spring Security schema. This public metadata contains no plaintext tokens. When using envelope encryption with per-record DEKs:

~~~json
{
  "formatVersion": 2,
  "algorithm": "AES-256-GCM",
  "kekId": "kms-key-reference",
  "wrappedDek": "BASE64URL_ENCRYPTED_DATA_KEY",
  "nonce": "BASE64URL_NONCE",
  "ciphertext": "BASE64URL_CIPHERTEXT_AND_TAG"
}
~~~

### 8.1. What Can Remain Plaintext?

Depending on the threat model, the database may need these columns for lookups:

~~~text
registration_id
principal_key
tenant_id
key_id
format_version
ciphertext
updated_at
row_version
~~~

Even when token values are encrypted, **principal IDs, tenants, registrations, and timestamps can still be sensitive metadata**. Enforce read permissions, retention, masking, or pseudonymization as required.

### 8.2. Do Not Encrypt Only the Token Value While Leaving Metadata Unauthenticated

If the database stores:

~~~text
access_token_value -> encrypted
access_token_expires_at -> plaintext, unbound
access_token_scopes -> plaintext, unbound
~~~

an attacker able to modify the database could alter `expiresAt` or `scopes` if the application trusts those columns. Solutions:

- Encrypt **the entire token payload and related metadata** in one AEAD envelope; or
- Bind critical metadata into AAD using canonical serialization and verify it on decryption.

In this lesson, the Java example encrypts **plaintext `byte[]`**; the application should bundle Access Token, Refresh Token, and protected metadata into a safe record/DTO before encrypting.

### 8.3. Can Access Token and Refresh Token Be Encrypted Separately?

Yes, if data/rotation requirements justify it, but each field needs its **own nonce** and AAD distinguishing the token kind:

~~~text
access_ciphertext  -> AAD(..., kind=access_token)
refresh_ciphertext -> AAD(..., kind=refresh_token)
~~~

Both fields must be updated consistently when a Refresh Token rotates. One way to reduce complexity is to **encrypt a single bundle** containing the Access Token, Refresh Token, and metadata for one authorized client, then update the bundle atomically.

## 9. Java 17: Implementing AES-GCM with AAD and Key Versions

Below is a **pure Java Cryptography Architecture (JCA)** example, independent of specific Redis/JDBC/Spring Security classes. It defines clean boundaries:

- `KeyProvider`: provides the active key for encryption and resolves older keys for decryption; **production implementations must integrate with KMS/HSM/envelope policies**.
- `TokenContext`: trusted information used to construct AAD.
- `AeadTokenCipher`: encrypts/decrypts `byte[]` with AES-GCM; does not persist to DB itself.
- Ciphertext format: `v1.{base64url(keyId)}.{base64url(nonce)}.{base64url(ciphertextAndTag)}`.

**Never hard-code keys in source code.** The example intentionally **omits a production class reading an AES key from `application.yml`**, because key management must integrate with each system's KMS.

### 9.1. KeyProvider and TokenContext

~~~java
package com.example.security.crypto;

import java.util.Objects;
import javax.crypto.SecretKey;

public interface KeyProvider {

    // Returns the current key version for NEW encryptions.
    ActiveKey currentKey();

    // Resolves older key versions to read stored data.
    // If revoked or missing, must fail closed.
    SecretKey keyById(String keyId);

    record ActiveKey(String keyId, SecretKey key) {
        public ActiveKey {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(key);
        }
    }
}
~~~

~~~java
package com.example.security.crypto;

import java.util.Objects;

public record TokenContext(
        String tenantId,
        String registrationId,
        String principalName,
        String tokenKind) {

    public TokenContext {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(registrationId);
        Objects.requireNonNull(principalName);
        Objects.requireNonNull(tokenKind);

        if (tenantId.isBlank()
                || registrationId.isBlank()
                || principalName.isBlank()
                || tokenKind.isBlank()) {
            throw new IllegalArgumentException(
                "Token context must contain nonblank identity fields");
        }
    }
}
~~~

These classes/interfaces belong in **separate Java files** per Java's rules for public top-level types. `tenantId` and `principalName` must come from verified application/authentication/store state, never from caller-supplied query parameters.

### 9.2. AeadTokenCipher

~~~java
package com.example.security.crypto;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AeadTokenCipher {

    private static final String VERSION = "v1";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int MAX_ENVELOPE_LENGTH = 256_000;

    private final KeyProvider keys;
    private final SecureRandom random = new SecureRandom();
    private final Base64.Encoder encoder =
        Base64.getUrlEncoder().withoutPadding();
    private final Base64.Decoder decoder =
        Base64.getUrlDecoder();

    public AeadTokenCipher(KeyProvider keys) {
        this.keys = Objects.requireNonNull(keys);
    }

    public String encrypt(byte[] plaintext, TokenContext context) {
        Objects.requireNonNull(plaintext);
        Objects.requireNonNull(context);

        KeyProvider.ActiveKey current = keys.currentKey();
        String keyId = current.keyId();
        SecretKey key = current.key();

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce); // Fresh IV on every encryption

        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(context, keyId));

            // JCA GCM returns ciphertext concatenated with the authentication tag.
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            return VERSION + "."
                + encode(keyId.getBytes(StandardCharsets.UTF_8)) + "."
                + encode(nonce) + "."
                + encode(ciphertextAndTag);
        } catch (GeneralSecurityException ex) {
            throw new TokenCryptoException(
                "Could not encrypt token payload", ex);
        }
    }

    public byte[] decrypt(String envelope, TokenContext context) {
        Objects.requireNonNull(envelope);
        Objects.requireNonNull(context);

        if (envelope.length() > MAX_ENVELOPE_LENGTH) {
            throw new TokenCryptoException(
                "Invalid encrypted token envelope");
        }

        try {
            String[] parts = envelope.split("\\.", -1);
            if (parts.length != 4 || !VERSION.equals(parts[0])) {
                throw new IllegalArgumentException("Bad envelope version");
            }

            String keyId = new String(
                decoder.decode(parts[1]),
                StandardCharsets.UTF_8);
            byte[] nonce = decoder.decode(parts[2]);
            byte[] ciphertextAndTag = decoder.decode(parts[3]);

            if (keyId.isBlank()
                    || nonce.length != NONCE_BYTES
                    || ciphertextAndTag.length < TAG_BYTES) {
                throw new IllegalArgumentException(
                    "Malformed encrypted token");
            }

            // KeyProvider must reject unauthorized keyIds,
            // with no default fallback key.
            SecretKey key = keys.keyById(keyId);
            if (key == null) {
                throw new IllegalStateException("Unknown key version");
            }

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(context, keyId));

            // If ciphertext, nonce, key, or AAD is wrong:
            // doFinal fails and returns no plaintext.
            return cipher.doFinal(ciphertextAndTag);
        } catch (GeneralSecurityException
                | IllegalArgumentException
                | IllegalStateException ex) {
            throw new TokenCryptoException(
                "Could not decrypt encrypted token payload", ex);
        }
    }

    private String encode(byte[] value) {
        return encoder.encodeToString(value);
    }

    private static byte[] aad(
            TokenContext context,
            String keyId) {

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(buffer)) {
            writeField(data, "oauth2-authorized-client-store");
            writeField(data, VERSION);
            writeField(data, keyId);
            writeField(data, context.tenantId());
            writeField(data, context.registrationId());
            writeField(data, context.principalName());
            writeField(data, context.tokenKind());
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Could not encode encryption context", ex);
        }

        return buffer.toByteArray();
    }

    private static void writeField(
            DataOutputStream data,
            String text) throws IOException {

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        data.writeInt(bytes.length);
        data.write(bytes);
    }
}
~~~

### 9.3. Exceptions Must Not Contain Plaintext Tokens

~~~java
package com.example.security.crypto;

public final class TokenCryptoException extends RuntimeException {

    public TokenCryptoException(String message) {
        super(message);
    }

    public TokenCryptoException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Never attach plaintext, raw token responses, or full envelopes to exception messages. In production, when logging or returning API errors, **do not automatically print the entire exception chain** if a KMS/client library might include sensitive details in `cause`. Design internal error codes and filtered logs.

### 9.4. Usage

~~~java
TokenContext context = new TokenContext(
    "company-a",
    "calendar",
    "issuerA-sub123",
    "authorized-client-payload");

byte[] serializedPayload =
    /* byte[] from controlled DTO serializer */;

String encrypted = tokenCipher.encrypt(
    serializedPayload, context);

// DB stores encrypted (never serializedPayload).

byte[] restored = tokenCipher.decrypt(encrypted, context);
// Use restored to reconstruct OAuth2AuthorizedClient.
~~~

This is an **integration pattern**, with `tokenCipher` and the serializer supplied by the application. Never do `new String(restored)` and log it. When handling `byte[]`, you can zero the buffer after use with `Arrays.fill(...)` where code structure permits, though Java does not guarantee wiping all heap copies and Spring Security token values are normally represented as immutable `String` objects.

### 9.5. Why Is This Design Better Than Hard-Coded Keys?

The crypto code contains no key values. `KeyProvider` can:

- Resolve the active key from a KMS-backed key registry.
- Decrypt wrapped DEKs per an envelope encryption layout.
- Reject unauthorized key versions.
- Support reading with old keys while writing with a new key.
- Audit decryption operations at the KMS layer without logging tokens.

This snippet **must not be mistaken for a complete KMS implementation**, and it provides no real protection if `KeyProvider` simply returns a hard-coded AES key stored alongside the database or committed in the source repository.

## 10. Never Use a Fixed Secret Key in Source Code or Config Files

An anti-pattern:

~~~java
// ANTI-PATTERN: never commit an AES key into source code.
byte[] keyBytes =
    "0123456789abcdef0123456789abcdef"
        .getBytes(StandardCharsets.UTF_8);
~~~

Even though 32 bytes looks long enough for AES-256, this is a predictable value, appears in source control, and may be shared across environments.

Another anti-pattern:

~~~yaml
security:
  token-store:
    encryption-key: "base64:REAL_PRODUCTION_KEY_HERE"
~~~

If configuration is committed or stored in the same database alongside tokens, protection against source/backup leaks is very weak.

**Better option:** use cloud KMS/HSM, a secured secret manager, or centralized key management; the application authorizes key usage via short-lived workload identity/roles, keeping raw keys out of the repository.

### 10.1. Are Environment Variables Enough?

Environment variables can be better than hard-coding in source, but are **not automatically** equivalent to a KMS:

- Values can appear in process dumps or diagnostic output.
- Anyone with access to deployment configs can read them.
- All instances may share a single unversioned key.
- Rotation and revocation are hard to audit without a key-management lifecycle.

In high-security environments, favor key hierarchies, KMS authorizations, and separating database read access from decryption rights.

## 11. Envelope Encryption: DEK and KEK

**Envelope encryption** is a common architecture for managing many ciphertexts without sending every large payload to the KMS.

- **DEK (Data Encryption Key):** the symmetric key that actually encrypts the token payload using AES-GCM.
- **KEK (Key Encryption Key):** the key used to **wrap/encrypt the DEK**; typically protected by KMS/HSM and never exported as raw key material to the application.
- **Wrapped DEK:** the encrypted DEK, which can be stored beside the ciphertext without exposing the plaintext DEK.

### 11.1. Envelope Encryption Diagram

~~~mermaid
flowchart TB
    A["OAuth2AuthorizedClient containing tokens"] --> B["Serialize payload"]
    C["KMS/HSM: managed KEK"] --> D["GenerateDataKey / wrap DEK"]
    D --> E["Temporary plaintext DEK in app memory"]
    D --> F["Wrapped DEK"]
    B --> G["AES-256-GCM encrypt with DEK + nonce + AAD"]
    E --> G
    G --> H["Ciphertext + nonce + auth tag"]
    F --> I["Database record"]
    H --> I
    I --> J["On load: fetch wrapped DEK and ciphertext"]
    J --> K["KMS unwraps DEK per key policy"]
    K --> L["AES-GCM decrypt + verify AAD"]
    J --> L
    L --> M["OAuth2AuthorizedClient in app memory"]
~~~

In some KMS offerings, `GenerateDataKey` returns both a **plaintext DEK and an encrypted DEK** to an authorized principal; the application uses the DEK in memory and limits the buffer's lifetime. Other systems use `Encrypt`/`Decrypt` or HSM operations. APIs, encryption context, limits, and key policies must follow your provider.

### 11.2. Why Not Encrypt Tokens Directly with the KEK in KMS?

Direct KMS encryption can work for small payloads in some setups, but:

- KMS APIs impose payload size limits.
- Every encrypt/decrypt incurs cost, latency, quota, and network dependency.
- Sending raw tokens in KMS requests requires evaluating logging/telemetry and trust boundaries.
- Key rotation and per-record isolation may require separate controls.

Envelope encryption lets the data plane encrypt in application memory while the KMS focuses on protecting DEKs/KEKs.

### 11.3. One DEK per Record or Shared Across Records?

| Model | Pros | Trade-offs |
| --- | --- | --- |
| One DEK per record | Limits blast radius if one DEK leaks; no cross-record nonce reuse under the same key | More wrapped DEKs, KMS/caching overhead |
| One DEK per tenant | Isolates blast radius by tenant | More complex key lifecycle management |
| Shared DEK per service/key version | Simple, fewer wrapped keys | Must strictly enforce nonce uniqueness and encryption count limits; larger blast radius |
| Per-field DEK | Separates Access/Refresh Tokens | More keys, metadata, and operations |

No single model fits every project. For high-value Refresh Tokens, per-record DEKs or tenant isolation can help. When using a shared DEK, enforce key usage limits, rotation, and reliable monitoring.

### 11.4. Where Does the Plaintext DEK Live?

In envelope encryption, a plaintext DEK may exist temporarily in process memory. Make sure to:

- Never log keys or dump `KeyProvider` objects.
- Keep buffers only as long as necessary.
- Restrict key retrieval/decryption by authorization.
- Consider zeroing `byte[]` when APIs allow, without promising Java removes all copies.
- Never write plaintext DEKs to Redis, databases, config files, or exceptions.

## 12. KMS/HSM: Separating Ciphertext Access from Key Usage

### 12.1. Two Permission Sets Should Not Overlap Arbitrarily

~~~text
Database reader
   -> SELECT ciphertext
   -> CANNOT call KMS Decrypt

Application runtime
   -> SELECT ciphertext
   -> calls KMS unwrap/decrypt via workload identity

Key administrator
   -> manages versions/rotation/policies
   -> does not get default read access to token tables
~~~

This is **separation of duties**. If one cloud account can read the database, download all backups, and call KMS decrypt unrestrictedly, application-layer encryption is significantly weakened.

### 12.2. Required Policies

1. **Least privilege:** only authorized services may decrypt keys belonging to their token store.
2. **Workload identity:** prefer short-lived roles/service accounts/mTLS identities; never commit key access credentials.
3. **Environment isolation:** production, staging, and development use separate keys and permissions.
4. **Tenant isolation** if required by the threat model.
5. **Audit trail:** record key usage, policy changes, and rotations; never log plaintext tokens.
6. **Key lifecycle:** active, decrypt-only, disabled, retired, destroyed.
7. **Break-glass control:** emergency access must be approved, monitored, and revoked afterward.
8. **Regional/availability design:** KMS outages must fail closed and remain recoverable.

### 12.3. KMS Encryption Context

Some KMS platforms support **encryption context**—key-value pairs authenticated alongside key wrap/unwrap operations. You can bind:

~~~text
application=oauth2-token-store
environment=production
tenant=company-a
purpose=authorized-client-dek
~~~

Never put Access Tokens, Refresh Tokens, Client Secrets, or unnecessary personal data into the encryption context; it can appear in KMS audit logs or policy metadata. The context on unwrap must match the context on wrap.

**KMS encryption context** and **AES-GCM AAD** can be used together, operating at two different layers: context binds the wrapped DEK inside KMS, while AAD binds the token ciphertext to the record identity inside the application.

### 12.4. Never Use JWT Signing Keys as AES Storage Keys

An OIDC Provider publishes **public signing keys** via JWKS for clients to verify ID Tokens/JWTs. Those keys are not application secrets for encrypting stored tokens.

Distinguish clearly:

~~~text
OIDC JWKS public key
  -> verify ID Token signature

Application token-store encryption key
  -> AES-GCM encrypt/decrypt stored credentials

OAuth2 client private key
  -> sign private_key_jwt client assertion
~~~

Never reuse a single key across three distinct purposes just because all of them fall under "security".

## 13. Where Does Spring Security Store Authorized Clients?

For Servlet OAuth2 Client:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
~~~

For Reactive:

~~~java
org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService
org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository
~~~

### 13.1. Common Implementations

| Storage Layer | Example | Key Considerations |
| --- | --- | --- |
| Process memory | `InMemoryOAuth2AuthorizedClientService` | Not persistent across restarts, yet tokens can appear in heap dumps |
| Servlet HTTP session | `HttpSessionOAuth2AuthorizedClientRepository` | Serialized sessions/replication/Redis may contain tokens |
| JDBC service | `JdbcOAuth2AuthorizedClientService` | Must control how token values are written to tables |
| Servlet repository adapter | `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Can delegate to a service for authenticated users |
| Reactive service | `InMemoryReactiveOAuth2AuthorizedClientService` or custom service | Watch reactive storage semantics and non-blocking I/O |
| Reactive server repository | `ServerOAuth2AuthorizedClientRepository` implementation | Can store via `WebSession` or delegate |

**Spring Security does not have a single global switch to encrypt all OAuth2 tokens across every store by default.** Do not simply enable JDBC/TDE or `oauth2Client()` and assume Access Tokens/Refresh Tokens are application-encrypted before persistence.

### 13.2. Clean Integration Points

A sound design can look like:

~~~text
DefaultOAuth2AuthorizedClientManager
  -> OAuth2AuthorizedClientRepository
     -> AuthorizedClientService-backed repository
        -> EncryptedOAuth2AuthorizedClientService (custom)
           -> EncryptedAuthorizedClientDao
              -> database
~~~

In Reactive:

~~~text
DefaultReactiveOAuth2AuthorizedClientManager
  -> ServerOAuth2AuthorizedClientRepository
     -> custom reactive encrypted store
        -> nonblocking DAO / Redis / R2DBC
~~~

**Do not decorate a service that the manager does not actually use.** Verify the real wiring across OAuth2 Login, client managers, repositories, HTTP sessions, and background jobs.

### 13.3. When Using HttpSession/Redis

An application might not write to any `oauth2_authorized_client` table, yet Access Tokens are still serialized inside sessions. If a Redis session store is shared, make sure to:

- Enforce Redis ACLs, TLS, authentication, and network isolation.
- Check whether Redis persistence snapshots/AOF/backups contain serialized tokens.
- Consider encrypting sensitive session/token payloads at the serializer layer or delegating via a repository to an encrypted service.
- Configure session TTLs, cookie security, and session invalidation workflows.

**Encrypting a JDBC token table does not protect tokens serialized inside an HTTP session in Redis.**

## 14. Persistence Adapter Example: Encrypting the Whole Token Bundle

A straightforward option is to serialize the **required token state** into a DTO, encrypt the entire payload with AES-GCM, and store only the ciphertext alongside controlled lookup keys.

### 14.1. DTO Holding Data Before Encryption

~~~java
package com.example.security.store;

import java.time.Instant;
import java.util.Set;

public record AuthorizedClientPayload(
    String tokenType,
    String accessTokenValue,
    Instant accessIssuedAt,
    Instant accessExpiresAt,
    Set<String> accessScopes,
    String refreshTokenValue,
    Instant refreshIssuedAt,
    Instant refreshExpiresAt) {
}
~~~

**This DTO holds plaintext credentials in memory** and **must never be logged, serialized into HTTP responses, or persisted directly to the database**. If `refreshTokenValue` is null, the provider did not issue a Refresh Token.

For JPA/JDBC, the persisted entity should contain only the **encrypted payload**, key reference, record identity, version, and approved metadata—never persisting the plaintext DTO alongside it.

### 14.2. DAO Sees Only Ciphertext

Illustrative interface:

~~~java
package com.example.security.store;

import java.util.Optional;

public interface EncryptedAuthorizedClientDao {

    Optional<EncryptedRow> find(
        String registrationId,
        String principalName);

    void save(
        String registrationId,
        String principalName,
        String encryptedPayload);

    void remove(
        String registrationId,
        String principalName);
}
~~~

~~~java
package com.example.security.store;

public record EncryptedRow(
    String registrationId,
    String principalName,
    String encryptedPayload) {
}
~~~

These interfaces/records are **custom application types**, not built-in Spring Security classes. They demonstrate that the DAO never needs to see raw token values. A production DAO must add transaction/concurrency control, tenant keys, ownership validation, row versioning, data migration support, and error handling.

### 14.3. Adapter for OAuth2AuthorizedClientService

The application can implement:

~~~java
public interface OAuth2AuthorizedClientService {

    <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId,
        String principalName);

    void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

    void removeAuthorizedClient(
        String clientRegistrationId,
        String principalName);
}
~~~

This is a **signature summary** illustrating Spring Security's contract, not an instruction to redeclare the framework interface. Custom implementation flow:

~~~text
saveAuthorizedClient(client, authentication)
  -> verify trusted registration and principal
  -> convert tokens + metadata into AuthorizedClientPayload
  -> JSON/CBOR serializer with schema version
  -> AeadTokenCipher.encrypt(payloadBytes, TokenContext)
  -> dao.save(ciphertext, metadata, rowVersion)

loadAuthorizedClient(registrationId, principalName)
  -> verify read permission for the right principal/tenant
  -> dao.find(record)
  -> AeadTokenCipher.decrypt(ciphertext, TokenContext)
  -> parse payload according to schema version
  -> construct OAuth2AccessToken / OAuth2RefreshToken
  -> construct OAuth2AuthorizedClient with known ClientRegistration

removeAuthorizedClient(registrationId, principalName)
  -> dao.remove matching record, audit per policy
~~~

Key takeaway: **encryption must happen before `dao.save`** and **decryption after `dao.find`**, while Spring Security continues working with `OAuth2AuthorizedClient` when calling APIs or refreshing tokens.

### 14.4. Converting Token Objects to the DTO

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

static AuthorizedClientPayload toPayload(
        OAuth2AuthorizedClient client) {

    OAuth2AccessToken access = client.getAccessToken();
    OAuth2RefreshToken refresh = client.getRefreshToken();

    return new AuthorizedClientPayload(
        access.getTokenType().getValue(),
        access.getTokenValue(),
        access.getIssuedAt(),
        access.getExpiresAt(),
        access.getScopes(),
        refresh == null ? null : refresh.getTokenValue(),
        refresh == null ? null : refresh.getIssuedAt(),
        refresh == null ? null : refresh.getExpiresAt());
}
~~~

This method uses the `AuthorizedClientPayload` application record shown earlier, imported according to your project package structure. Plaintext values exist only transiently in application memory/serializer.

### 14.5. Reconstructing OAuth2AuthorizedClient

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

static OAuth2AuthorizedClient fromPayload(
        AuthorizedClientPayload payload,
        ClientRegistration registration,
        String principalName) {

    if (!"Bearer".equalsIgnoreCase(payload.tokenType())) {
        throw new IllegalStateException(
            "Unsupported token type in encrypted store");
    }

    OAuth2AccessToken access = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        payload.accessTokenValue(),
        payload.accessIssuedAt(),
        payload.accessExpiresAt(),
        payload.accessScopes());

    OAuth2RefreshToken refresh = null;
    if (payload.refreshTokenValue() != null) {
        refresh = new OAuth2RefreshToken(
            payload.refreshTokenValue(),
            payload.refreshIssuedAt(),
            payload.refreshExpiresAt());
    }

    return new OAuth2AuthorizedClient(
        registration, principalName, access, refresh);
}
~~~

Note: `ClientRegistration` should be loaded from a **trusted configuration repository** by the registration ID in the row key, rather than deserializing a full registration from a mutable DB. Validate schema version, required fields, and token timestamps when reading the payload.

### 14.6. The Serializer Is Also Part of Security

If using JSON, configure Jackson/your serializer carefully:

- Never enable unsafe polymorphic default typing on untrusted data.
- Serialize only a strictly bounded DTO schema—never arbitrary `Authentication` object graphs.
- Support `Instant`, `Set<String>`, and metadata types via appropriate modules.
- Limit payload/envelope size to prevent memory exhaustion.
- Distinguish **AEAD authentication errors** from **schema/migration errors** operationally without leaking ciphertext/token contents.

Encrypt before storing; on decryption, **verify the AEAD tag before trusting any data**. Never parse tampered content as a valid token object.

### 14.7. Avoid Uncontrolled Double Encryption

If the persistence adapter already encrypts, do not let another layer re-encrypt the same plaintext with another key without version/ownership metadata. Accidental double encryption complicates migrations, backup recovery, and troubleshooting.

By contrast, TDE underneath application encryption is not "broken double encryption": it operates at a separate storage layer and can remain enabled per policy.

## 15. Do Not Just Wrap JdbcOAuth2AuthorizedClientService and Assume Encryption

Spring Security's `JdbcOAuth2AuthorizedClientService` provides JDBC persistence for authorized clients. A wrapper doing:

~~~java
delegate.saveAuthorizedClient(authorizedClient, principal);
~~~

still **passes plaintext tokens to the delegate**. If the default delegate writes token values into columns, encrypting a second copy elsewhere in the wrapper **does not fix plaintext in the DB**.

To guarantee encryption before storage, choose one of these approaches:

1. **Custom `OAuth2AuthorizedClientService`** performing encrypt/decrypt in front of the DAO.
2. **Custom JDBC mapper/parameters strategy** if your version/implementation provides the proper extension points to transform token bytes on both write and read.
3. **Persistence-layer encryption** properly integrated into the entity/serializer and verified so that **every** token field passes through the encryption path.
4. **Custom repository/session serializer** if tokens are primarily stored in `WebSession`/HTTP sessions.

Never assume a JPA `@Convert` on an entity unused by Spring Security will encrypt tokens in Spring Security's JDBC table.

### 15.1. With OAuth2AuthorizedClientManager

A manager typically has a **default success handler** that invokes save after a successful grant/refresh:

~~~text
Manager.authorize(...)
  -> Token Endpoint issues/refreshes token
  -> OAuth2AuthorizationSuccessHandler
  -> authorizedClientService.saveAuthorizedClient(...)
  -> custom encrypted DAO
~~~

If a custom success handler only logs without delegating the save, new tokens may never be persisted. This is especially dangerous when Refresh Tokens **rotate**: retaining an old token causes `invalid_grant` on the next refresh.

### 15.2. Do Not Leak Plaintext Tokens Back Into Debug Caches

When adopting an encrypted store, audit:

- `@Cacheable` or Caffeine/Redis caches holding token objects.
- HTTP session serializers.
- Tracing/metrics interceptors.
- SQL parameter logging.
- Exception handlers and debug endpoints.
- Job exports and backups.

If a cache keeps objects only in memory, you must still restrict heap dumps, memory inspection, and key lifetimes; if a cache is persistent or distributed, verify whether it stores plaintext tokens.

## 16. Session Cookies and Session Stores: Two Different Surfaces

In a web application using OIDC Login, the browser typically receives a **session cookie** while tokens reside server-side:

~~~text
Browser:
  Cookie: SESSION=<opaque session identifier>

Server:
  WebSession/HttpSession -> OAuth2 Authentication
  Authorized Client Store -> Access/Refresh Tokens
~~~

Do not send Access Tokens/Refresh Tokens in cookies by default merely to avoid database storage.

### 16.1. Protecting Cookies

Session cookies must be configured per policy:

- `Secure` over HTTPS.
- `HttpOnly` when JavaScript does not need to read the cookie.
- `SameSite` compatible with browser/callback mode and CSRF policy.
- Reasonably narrow `Domain`/`Path`.
- Session rotation/fixation protection, TTL, and logout invalidation.

Cookie flags **do not encrypt tokens inside Redis/session stores**. Conversely, DB token encryption **does not replace** CSRF/session security.

### 16.2. Tokens in Session Serialization

If Redis-backed sessions store serialized `Authentication` or authorized clients, a Redis snapshot may contain sensitive data. Verify:

1. Do tokens actually live in the session or in an authorized client service?
2. How many copies, replicas, and backups exist?
3. Does the serializer encrypt sensitive payloads before Redis receives them?
4. Does session expiration also remove persistent tokens stored elsewhere?

### 16.3. Avoid Cookies Holding Encrypted Refresh Tokens Unless Necessary

Even when a cookie holds an encrypted Refresh Token, the browser can attach it to every matching domain/path request, subject to size limits and replay risks if stolen. For a BFF/backend OAuth2 Client, **storing Refresh Tokens server-side** is usually easier to control.

## 17. Key Management: Creation, Usage, Rotation, Revocation, and Destruction

A key does not merely have "present or absent" states. Systems need a **key lifecycle**:

~~~mermaid
flowchart LR
    A["Create key / version"] --> B["Active: encrypt + decrypt"]
    B --> C["Decrypt-only: no new ciphertexts written"]
    C --> D["Retired: kept only if old data/backups need it"]
    D --> E["Disabled per policy"]
    E --> F["Destroy once approved and no readable data remains"]
~~~

Disabling or destroying a key **can render all ciphertexts dependent on that key undecryptable**. This is a high-risk operation; maintain a record inventory and backups before destroying key material.

### 17.1. Key ID/Version Must Be Stored Alongside Ciphertext

~~~text
Record 1001: keyId = k3
Record 1002: keyId = k2
Record 1003: keyId = k1
~~~

After rotation, the app can **write with `k3`** while still **decrypting with `k1`/`k2`** during migration. Never change `keyId` in the database without performing the corresponding cryptographic re-encryption or rewrap.

### 17.2. Policy-Driven vs. Incident-Driven Rotation

Two distinct situations:

- **Planned rotation:** the key is not suspected of compromise; transition gradually, keep old keys decrypt-only, and control rate limits and rollbacks.
- **Compromise-driven rotation:** key compromise is suspected; trigger incident response, restrict permissions, assess data exposure, issue a new key, **re-encrypt**, and evaluate **revoking OAuth2 tokens** that may have been stolen.

Rotating the encryption key alone **does not invalidate Access Tokens/Refresh Tokens** that an attacker already extracted in plaintext.

### 17.3. How Long to Keep Old Keys

You cannot base old key TTL solely on Access Token expiry if:

- Refresh Tokens live for months.
- Older backups must still be restorable.
- Rarely accessed records rely on lazy re-encryption.
- Older instances have not finished rolling out.

Key retirement must be driven by **data inventory and backup retention**, not simply "30 days have passed".

## 18. Two Rotation Approaches: Rewrap and Re-Encrypt

### 18.1. Rewrapping the DEK

In envelope encryption:

~~~text
KEK v1 -> wrapped DEK -> AES-GCM ciphertext

Rotate KEK:
  unwrap DEK using KEK v1
  wrap same DEK using KEK v2
  token ciphertext can remain unchanged
~~~

Advantage: no need to decrypt and re-encrypt every token payload in the database when rotating only the **KEK**. Keep in mind:

- If the **DEK** itself was compromised, rewrapping the same DEK **does not fix** that compromise.
- If policy requires rotating the **data encryption key**, you must re-encrypt the payload.
- Old and new wrapped DEKs may need to coexist during a controlled rollout.

### 18.2. Re-Encrypting the Payload with a New DEK

~~~text
Old ciphertext -> decrypt with old DEK and old AAD
               -> re-encrypt with new DEK, new nonce, and AAD
               -> write new record with new key version
~~~

This performs a **true data key rotation**. Transactions/concurrency controls are required so you do not overwrite a newer Refresh Token just saved by the manager.

### 18.3. Read-Old, Write-New

A common migration strategy:

1. New app instances are configured with **current key = `k3`**.
2. Decryption still supports `k1`/`k2` per policy.
3. All **new saves** use `k3`.
4. A migration job reads `k1`/`k2` records, decrypts them, and re-encrypts with `k3`.
5. Only after all legacy records are migrated and backup policy permits are old keys disabled/destroyed.

**Never re-encrypt every record simultaneously in an unbounded-concurrency job** when the KMS enforces quotas. Use batches, rate limits, checkpoints, bounded retries, and monitoring.

### 18.4. Lazy Rotation vs. Eager Rotation

| Approach | How It Works | Pros/Cons |
| --- | --- | --- |
| Lazy re-encryption | On reading an old record, re-encrypt with the new key | Reduces migration spikes, but rarely accessed records may stay on old keys indefinitely |
| Eager migration | Batch-scan records and re-encrypt | Measurable completion, requires handling concurrency/quotas |
| Hybrid | Write new with new key + lazy + batch for older records | Usually flexible, requires telemetry/key inventory |

If an organization must **urgently revoke an old key** due to compromise, lazy-only rotation will not meet incident timelines.

## 19. Race Conditions Between Refresh Token Rotation and Key Rotation

A tricky edge case:

~~~mermaid
sequenceDiagram
    autonumber
    participant R as OAuth2 Refresh Worker
    participant M as Key Migration Worker
    participant DB as Encrypted Client DB
    participant OP as Token Endpoint
    R->>DB: Read record version 7 (refreshToken R1)
    M->>DB: Read record version 7
    R->>OP: Refresh Token R1
    OP-->>R: Access Token A2, Refresh Token R2
    R->>DB: Save R2 encrypted, version 8
    M->>DB: Write re-encrypted stale version 7
    Note over DB: With a blind update, R2 can be overwritten by R1
~~~

This is a **lost update**, not an AES-GCM failure. Data encryption does not solve database concurrency.

### 19.1. Optimistic Locking / Compare-and-Swap

Records should include a `row_version` or concurrency token:

~~~sql
-- Illustrative SQL, not a production migration.
UPDATE oauth2_authorized_client_secure
SET encrypted_payload = :new_ciphertext,
    key_id = :new_key_id,
    row_version = row_version + 1
WHERE registration_id = :registration_id
  AND principal_key = :principal_key
  AND row_version = :expected_version;
~~~

If the update affects **0 rows**, another writer modified the record or it no longer exists. The migration worker must **re-read, verify, and decide whether to retry**—never overwrite newer tokens with stale ciphertext.

### 19.2. Concurrency After Refresh Failure

If Request A refreshes successfully while Request B uses the old Refresh Token and receives `invalid_grant`, Request B's failure handler must not mistakenly delete Request A's newly saved `R2` record. Evaluate conditional deletes/version checks or single-flight coordination per `registrationId + principalName`.

### 19.3. Separate Encryption Rotation from OAuth2 Authorization

A rotation job **should never call the Token Endpoint to refresh every user's token solely to rotate encryption keys**. It only needs to decrypt/re-encrypt existing data; OAuth2 grant operations are a separate responsibility and could trigger rate limits or unintentionally rotate Refresh Tokens.

## 20. Migrating from a Plaintext Database to an Encrypted Store

Many applications start with `JdbcOAuth2AuthorizedClientService` or a custom plaintext token table. Transitioning to encryption requires a plan that avoids breaking all active connections.

### 20.1. You Cannot Just Alter the Column Type

If existing code reads:

~~~text
access_token_value = "eyJ..."
refresh_token_value = "opaque-value..."
~~~

while new code only knows how to decrypt `v1....` envelopes, deploying directly will prevent loading all existing records.

### 20.2. Suggested Migration Workflow

1. **Inventory:** locate all token stores: JDBC, Redis, sessions, replicas, exports, and backups.
2. **Design schema:** add encrypted payload, key/version metadata, row version, and schema version fields.
3. **Grant KMS policies:** app gets encrypt/decrypt for the right keys; migration worker gets minimal permissions.
4. **Read legacy data through a trusted pipeline:** never export plaintext to shared files.
5. **Encrypt each record:** use AAD bound to registration/principal/tenant and a fresh nonce.
6. **Write safely:** use transactions or optimistic locking, keeping token pairs consistent.
7. **Roll out code supporting both formats during a short approved window**, while all new saves write encrypted payloads.
8. **Measure progress:** remaining plaintext count, failed conversions, active key versions.
9. **Disable plaintext fallback:** once migration completes and is verified.
10. **Address legacy plaintext in snapshots/backups** per retention/secure deletion policies; do not assume `DROP COLUMN` immediately scrubs all backups.

### 20.3. Risks of "Dual-Write"

A prolonged dual-write setup:

~~~text
save client
  -> plaintext table
  -> encrypted table
~~~

still maintains a plaintext store. If parallel migration is required, bound its duration, access permissions, and deletion plan, and ensure no older instance keeps writing plaintext after cutover.

### 20.4. Do Not Detect Format by Checking "Does the Token Have Dots?"

Both JWTs and ciphertexts can contain dots or base64url strings depending on format. Use an **explicit format/version field**—never guess whether a record is encrypted by checking if it starts with `eyJ` or by string length.

## 21. Testing Encryption: Properties That Must Hold

Having AES-GCM code does not prove tokens are properly protected. Test cryptographic properties and persistence behavior at the right layers.

### 21.1. Test Scenario Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Encrypt then decrypt with identical context/key | Exact original `byte[]` recovered |
| Encrypt same plaintext/context twice | Ciphertexts differ due to **fresh nonce** |
| Modify 1 byte of ciphertext | Decryption fails, returns no plaintext |
| Modified or missing tag | Decryption fails |
| Wrong nonce size | Envelope rejected |
| Non-existent Key ID | Fails closed; never tries an arbitrary fallback key |
| Modified Key ID | Decryption fails or key lookup rejects |
| Principal Alice swapped to Bob | AAD mismatch, decryption fails |
| Registration `calendar` swapped to `billing` | AAD mismatch |
| Tenant A swapped to Tenant B | AAD mismatch |
| Token kind swapped from `access` to `refresh` | AAD mismatch |
| Key rotation: write `k2`, still read `k1` | Legacy records remain readable per policy |
| Disable key `k1` while records still need `k1` | Categorized, alerted error; never returns fake token |
| Migration races with refresh | CAS prevents overwriting newer Refresh Token |
| Database write fails after encrypt | Payload not logged; not marked persisted |
| Oversized/malformed ciphertext | Size-bounded, safely rejected |
| Alice and Bob log in | Authorized clients never cross-assigned |
| SQL/HTTP logging enabled | No plaintext tokens/secrets appear |
| Backup restore | Required key material/versions remain safely managed |

### 21.2. JCA AES-GCM Unit Test with Test-Only Key

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AeadTokenCipherTest {

    @Test
    void encryptionRoundTripAndContextBinding() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey testKey = generator.generateKey();

        KeyProvider keys = new KeyProvider() {
            @Override
            public ActiveKey currentKey() {
                return new ActiveKey("unit-test-v1", testKey);
            }

            @Override
            public SecretKey keyById(String keyId) {
                if (!"unit-test-v1".equals(keyId)) {
                    throw new IllegalStateException("Unknown test key");
                }
                return testKey;
            }
        };

        AeadTokenCipher cipher = new AeadTokenCipher(keys);
        TokenContext alice = new TokenContext(
            "test-tenant", "calendar", "alice", "refresh");
        TokenContext bob = new TokenContext(
            "test-tenant", "calendar", "bob", "refresh");

        byte[] plaintext =
            "TEST_ONLY_REFRESH_TOKEN".getBytes(StandardCharsets.UTF_8);

        String first = cipher.encrypt(plaintext, alice);
        String second = cipher.encrypt(plaintext, alice);

        assertNotEquals(first, second);
        assertArrayEquals(plaintext, cipher.decrypt(first, alice));
        assertThrows(
            TokenCryptoException.class,
            () -> cipher.decrypt(first, bob));

        Arrays.fill(plaintext, (byte) 0);
    }
}
~~~

This test uses a randomly generated key **only in memory/tests**, never saved to production config. `assertNotEquals` across two ciphertexts is a practical check for fresh random nonces, not mathematical proof that an RNG can never collide: production still needs usage limits/rotation and an appropriate nonce uniqueness strategy.

### 21.3. Testing Tampering

In tests, decode the envelope into parts, flip a byte in the ciphertext or tag, re-encode, and assert decryption fails. Avoid changing only the final Base64url character if padding bits make that character ineffective under encoding/canonicalization.

### 21.4. Testing KMS and Application Authorization

Unit testing AES-GCM **does not prove** KMS policies or workload identities are correct. Write integration tests verifying:

- Production service role can decrypt only its authorized keys.
- Migration role cannot read unrestricted data outside scope.
- Staging cannot decrypt production ciphertexts/keys.
- KMS unavailability causes the application to **fail closed**.
- Old keys are disabled only when no records/backups still depend on them.
- Key usage is audited without plaintext tokens.

## 22. Operational Key Rotation Runbook

A rotation procedure can be documented as a runbook:

### Before Rotation

- Inventory records by `keyId`/`formatVersion`.
- Confirm backups exist and **key + ciphertext** recovery meets policy.
- Check KMS quotas, latency, and role permissions.
- Verify migration code uses optimistic locking.
- Plan service instance rollout timing.
- Prepare monitoring: decrypt failures, KMS errors, count of old-key records.

### During Rotation

1. Create/activate the new key version and set it as `currentKey` for encryption.
2. Keep the old key **decrypt-only** during transition.
3. Perform canary rollout and verify token reads/writes.
4. Run batch rewrap or re-encrypt per target scope.
5. Monitor remaining old-key records, AEAD/KMS errors, and token refresh rates.
6. Never delete the old key just because a canary passed a few requests.

### After Rotation

- Confirm all active records requiring migration have moved versions.
- Review rollback plan and backups still holding older versions.
- Retire/disable the old key only when policy allows and data recovery remains viable.
- Record audit details: who rotated, when, key versions involved, record counts processed.
- Verify no credentials were printed in migration logs.

### 22.1. When KMS Experiences an Outage

If the system cannot decrypt tokens:

~~~text
Database row has ciphertext
  -> KMS / key provider unavailable
  -> never fabricate fake plaintext
  -> return controlled dependency error / pause job
  -> alert + bounded retry by error category
~~~

Never fall back to a hard-coded emergency key in source code or save unencrypted tokens "just to keep things running". Doing so destroys the threat model.

### 22.2. Caching DEKs

To reduce KMS latency, some systems cache plaintext DEKs in memory with TTL and size bounds. Evaluate:

- Key exposure risk upon process compromise.
- How long cached keys persist after KMS revokes access.
- Number of records sharing a DEK (blast radius).
- Invalidation/rotation hooks and bounded memory limits.

Never cache plaintext DEKs or tokens in an inadequately protected **persistent distributed cache**.

## 23. Responding to Suspected Key or Token Compromise

### 23.1. Ciphertext Leaked with No Evidence of Key Compromise

1. Scope which database/snapshot/backup was accessed.
2. Verify ciphertexts used proper AES-GCM and keys were stored separately.
3. Inspect KMS audit logs for anomalous decryption calls.
4. Restrict DB read permissions and stop ongoing exposure.
5. Assess exposed metadata (tenant/principal/registration).
6. Decide on rotation/re-encryption per threat assessment and policy.

Never declare "no impact because of AES-256" without investigating key storage, AAD, nonce uniqueness, and runtime compromise.

### 23.2. Suspected Encryption Key Compromise

1. Activate incident response procedures.
2. Isolate credentials/roles that may have used the key anomalously.
3. Plan key disabling **while preserving recovery options**, avoiding abrupt unrecoverable data destruction.
4. Issue new DEKs/KEKs and re-encrypt affected records.
5. Investigate whether anyone obtained **plaintext Refresh Tokens/Access Tokens**.
6. Consider revoking/resetting OAuth2 connections via the Authorization Server if tokens may be exposed.
7. Re-initiate OAuth2 authorization for affected users/services as needed.
8. Conduct a post-incident review and update key policies/monitoring.

**Re-encrypting the database with a new key alone does not stop an attacker from using plaintext tokens they already stole.**

### 23.3. Key Lost with No Recovery Copy

AEAD has no valid backdoor: if the key required for decryption is lost, tokens may be **unrecoverable**. The business remediation is usually deleting unreadable records and prompting reauthorization or requesting fresh tokens, depending on grant:

- Authorization Code/OIDC: users may need to re-consent.
- Client Credentials: the service can obtain a new Access Token if client credentials remain valid.
- Lost Refresh Token: cannot be recovered by guessing or reversing a hash.

That is why key backups, access policies, and retention must be designed **before** using encryption in production.

## 24. Protecting Access Control and Authorized Client Lifecycle

### 24.1. Encryption Does Not Replace Principal Ownership

The system must still enforce:

~~~text
(tenantId, clientRegistrationId, principalName)
    -> exact encrypted authorized client record
~~~

In a multi-IdP system, `principalName` can be derived from issuer + subject or a reliably linked internal identity. Never use unverified emails as a global key across multiple tenants.

### 24.2. Never Use a Client Credentials Token in Place of a Delegated User Token

A machine token carries the application's own privileges. If the backend uses that token to serve a user, the backend must enforce user/tenant authorization before calling APIs. Having the machine token encrypted safely in the DB **does not legitimize** confused-deputy behavior or authorization bypasses.

### 24.3. Do Not Write Tokens After a User Disconnects

A sync job may still be running when the user revokes a connection. Design for:

- Checking that the connection is still active before using tokens.
- Handling in-flight requests racing with disconnect.
- Deleting local encrypted records per policy.
- Calling the Token Revocation Endpoint if supported by the provider and required by the app.
- Never restoring a disconnected token record simply because it exists in backups.

### 24.4. Data Minimization

Do not store every OAuth2/OIDC claim "just in case". Store only the Access Token, Refresh Token, and metadata essential to the lifecycle. Claims from ID Tokens/UserInfo should have separate retention and purpose policies, especially when containing PII.

## 25. Common Implementation Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Storing plaintext tokens in JDBC | SQL readers/backups can extract credentials | Encrypt before save; separate keys from DB |
| Thinking TDE alone is enough | `SELECT` still returns plaintext to privileged DB accounts | Application-level encryption when threat model requires |
| Hashing Refresh Tokens that must be reused | Cannot recover value to refresh | Use reversible authenticated encryption |
| Hard-coding AES keys in Java/YAML | Source/config leaks expose keys | KMS/HSM/secret manager, workload identity |
| AES-CBC without MAC, or ECB | Fails to provide proper authenticated encryption | Use AEAD such as AES-GCM |
| Static or reused AES-GCM nonces | Can catastrophically break confidentiality/integrity | Fresh/unique nonce per key, enforce key usage limits |
| Same AAD for every user/tenant | Ciphertexts can be swapped across rows | Bind tenant, registration, principal, token purpose |
| AAD built from unverified user input | Does not enforce record access authorization | Server-side authorization before decryption |
| Storing `keyId` without retaining old keys | Cannot read older records after rotation | Read-old/write-new, key inventory |
| Rotating KEK and assuming DEK changed | If DEK leaked, exposure remains | Re-encrypt with a new DEK when needed |
| Disabling old key before migration/backups finish | Irrecoverable token data loss | Plan key retirement carefully |
| Encrypting Access Token but leaving Refresh Token plaintext | Exposes longest-lived credential | Encrypt the entire sensitive token payload |
| Unauthenticated expiry/scope metadata | DB tampering can alter behavior | Encrypt metadata or bind it in AAD |
| Adding a plaintext debug column in DAO | Still leaks tokens | Never maintain persistent plaintext copies |
| Migration overwrites newer Refresh Token | Client loses ability to refresh | Versioning/CAS or per-record locking |
| Keys and ciphertexts in the same backup | Defeats key separation | Separate key management from data backups |
| KMS error -> fallback to plaintext save | Breaks confidentiality during outages | Fail closed and alert |
| Logging ciphertext alongside plaintext/token | Undoes security controls | Redact, log safe structured metadata |
| Encrypting DB while leaving Redis sessions plaintext | Tokens remain exposed via session store | Inventory all persistence paths |
| Assuming encryption = revocation | Already-leaked tokens still work | Token revocation/rotation per incident response |
| Using JWT signing key for storage encryption | Mixes key purpose and trust boundaries | Separate keys by purpose |
| Never testing backup restores with key versions | Disaster recovery can fail | Run controlled restore drills |

## 26. Practical Scenarios

### Scenario A — Protecting Refresh Tokens in JDBC

An OIDC portal holds Refresh Tokens for thousands of users in a JDBC table; backups flow through multiple systems.

**Design:** custom `OAuth2AuthorizedClientService` encrypts the token bundle before INSERT/UPDATE, stores ciphertext with key version, keeps KMS keys separate from DB backups, restricts `SELECT`, and audits decryption.

### Scenario B — TDE Enabled, Yet BI Account Can SELECT Tokens

The database has TDE enabled, but a data-analytics account has read access to `oauth2_authorized_client`.

**Problem:** the database decrypts data transparently for any authorized SQL reader. **Solution:** application-level encryption, column/table privileges, masked views, and KMS decrypt separation.

### Scenario C — KMS Rotation Makes Old Tokens Unreadable

The app deploys key `v3` and immediately disables key `v2` upon deploy, while many rows still have `keyId=v2`.

**Solution:** read-old/write-new; planned re-encryption/rewrap, inventorying records and backups before retiring `v2`.

### Scenario D — Refresh Token Rotation During Key Migration

A migration worker is re-encrypting an older row while a user request refreshes the token and saves a new one.

**Solution:** optimistic locking/CAS, retry migration against the fresh record; never blind-update with ciphertext from a stale row.

### Scenario E — Token Copied from User A to User B

Someone able to edit DB rows copies Alice's ciphertext into Bob's row.

**Solution:** AEAD AAD must bind principal/tenant/registration. Decryption with Bob's AAD fails, preventing the app from using Alice's token for Bob.

### Scenario F — Scheduled Job Using Client Credentials

A job only uses short-lived Access Tokens and can request a new token at any time.

**Design:** if persistence is unnecessary, consider an in-memory store with least privilege and process isolation. If a shared token cache or audit store is needed, use an encrypted store, key management, and appropriate TTL; do not arbitrarily issue Refresh Tokens.

### Scenario G — Tokens in Redis Session Snapshots

A team encrypted JDBC, yet authorized clients still reside in Redis sessions.

**Solution:** verify which repository/service Spring Security actually uses, encrypt session payloads/token fields or switch to an appropriate encrypted repository, and secure Redis snapshots/AOF.

### Scenario H — Key Provider Outage

Both the database and APIs are healthy, yet KMS fails to return data keys.

**Right behavior:** fail closed, report service degradation, perform bounded retries for infrastructure errors, and never write plaintext tokens or fall back to a hard-coded emergency key.

### Scenario I — Encrypting with Static Key and Timestamp IV

A developer uses `System.currentTimeMillis()` as the IV for easier debugging.

**Problem:** across multiple instances, IVs can collide under the same key—catastrophic for AES-GCM. **Solution:** use a nonce uniqueness strategy with cryptographic randomness and monitor per-key encryption limits.

### Scenario J — Signed JWT Not Encrypted in Storage

A team assumes that because a JWT has a signature, attackers cannot read it.

**Problem:** JWS payloads are usually readable and Bearer tokens can still be replayed. **Solution:** separate signing/integrity from storage confidentiality; encrypt at rest per threat model.

### Scenario K — Changing User Email Breaks Token Decryption

AAD bound `principal=email`, the user's email changed, and decryption under the new email failed.

**Solution:** use a stable principal ID; if the identity key must change, migrate using the old context and re-encrypt with the new context.

### Scenario L — Both Ciphertext and KMS Decrypt Permissions Exposed

A compromised service account had rights to read the DB and decrypt all wrapped DEKs.

**Solution:** full incident response, restrict IAM, audit usage, rotate/re-encrypt keys, and consider revoking affected OAuth2 tokens; never claim "the DB was encrypted so we're safe".

### Scenario M — Encrypted Store, Yet Logs Leak Tokens

On refresh failures, the application logs the entire `OAuth2AuthorizedClient` for support.

**Solution:** never log token objects, redact in HTTP clients/SQL/APM, and audit non-sensitive metadata. Encryption at rest cannot stop decrypted tokens from leaking inside the process.

## 27. Pre-Production Design Checklist

| Question | Requirement |
| --- | --- |
| Where are tokens stored? | Inventory JDBC, sessions, caches, backups, replicas, logs |
| Which tokens are most sensitive? | Access/Refresh Tokens, ID Token where needed, client credentials |
| What is the threat model? | DB dumps, backup theft, SQL insiders, runtime compromise |
| Which algorithm is used? | Reviewed AEAD: AES-GCM or suitable alternative |
| Are nonces unique per key? | RNG/nonce allocation and per-key usage limits |
| What does AAD include? | Application domain, version, tenant, registration, principal, token purpose |
| Are keys hard-coded? | No; KMS/HSM/secret manager and workload identity |
| Where is key version stored? | Store sufficient metadata to decrypt and rotate |
| How are DEK/KEK managed? | Envelope design, permissions, TTL, wrapped data keys |
| Can the app read another user's token? | Ownership checks, principal namespaces, and tenant isolation |
| Is token metadata authenticated? | Encrypt bundle or bind critical metadata in AAD |
| Does Spring Security use the encrypted store? | Verify actual manager/repository/service wiring |
| Do session stores hold plaintext copies? | Serializers, Redis, snapshots, retention |
| Is Refresh Token rotation atomic? | CAS/transactions, preventing stale writes |
| Does rotation have a rollback plan? | Read-old/write-new, inventory, backups, runbook |
| What if a key is lost/disabled? | Fail closed, alert, recovery/reauthorization |
| What if KMS is unavailable? | Degradation policy, bounded retries, no plaintext fallback |
| Do logs/APM leak tokens? | Redaction, no raw tokens in error messages |
| Are tokens revoked on disconnect/incident? | Local deletion vs. provider revocation |
| How are encryption and storage tested? | Tampering, context mismatch, key rotation, concurrency |

## 28. References

- Spring Security — OAuth2 Client (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — `OAuth2AuthorizedClientService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html
- Spring Security — `OAuth2AuthorizedClientRepository` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html
- Spring Security — `ReactiveOAuth2AuthorizedClientService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientService.html
- Spring Security — `OAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Java Cryptography Architecture / Cipher: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html
- Java `GCMParameterSpec` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html
- NIST SP 800-38D — Galois/Counter Mode (GCM): https://csrc.nist.gov/pubs/sp/800/38/d/final
- NIST SP 800-57 Part 1 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- OWASP Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

## 29. Summary: Token Encryption and Key Management Are Two Inseparable Halves

~~~text
Authorization Server
    |
    | Access Token / Refresh Token
    v
OAuth2AuthorizedClientManager
    |
    v
Custom encrypted authorized client store
    |
    +-- Serialize token payload + essential metadata
    |
    +-- Build AAD:
    |     tenant / registration / principal / token purpose
    |
    +-- AES-GCM encrypt:
    |     key/dek + NEW nonce + AAD
    |
    +-- KMS/HSM:
    |     key lifecycle, KEK, wrapped DEK, audit, access policy
    |
    v
Database:
    ciphertext + nonce + key version + wrapped DEK (if used)
    NO plaintext tokens
    |
    | load + verify AAD/tag + decrypt with matching key
    v
OAuth2AuthorizedClient in app memory
    |
    +-- Access Token -> call Resource Server with right scope/audience
    +-- Refresh Token -> Token Endpoint when refresh is needed
~~~

**Five principles to remember:**

1. **Encrypt before saving, not just at the disk layer.** Access Tokens and especially Refresh Tokens must be protected across every persistence path the application actually uses: JDBC, sessions, Redis, or custom stores.
2. **Use standard AEAD such as AES-GCM with non-reused nonces and record-bound AAD.** This ensures ciphertexts are not only unreadable, but also rejected if tampered with or swapped across principals/tenants/registrations.
3. **Keep key management separate from the database.** KMS/HSM, DEK/KEK, key versions, least privilege, and auditing matter just as much as the cipher algorithm. Hard-coding keys in source defeats the design.
4. **Rotation requires migration and concurrency control.** Use read-old/write-new, targeted rewrapping or re-encryption, optimistic locking to avoid overwriting fresh Refresh Tokens, and retire old keys only once no data remains to decrypt.
5. **Encryption does not replace token authorization or incident response.** Resource Servers must still validate issuer/audience/scope; encryption does not stop log/runtime leaks; and re-encryption does not revoke stolen plaintext tokens.

When crypto boundaries, key lifecycles, and integration with Spring Security authorized client storage are implemented properly, the application can reuse OAuth2/OIDC tokens while substantially reducing risks from database snapshots, backups, and unintended data access—while preserving safe long-term operations and key rotation.
