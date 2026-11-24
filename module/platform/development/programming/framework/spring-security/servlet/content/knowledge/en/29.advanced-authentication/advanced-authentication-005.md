# Relying Party ID, Origin, HTTPS, and WebAuthn Credential Storage

## 1. Goals and Security Model

**WebAuthn** (Web Authentication) lets an application authenticate users with public-key credentials bound to a **Relying Party (RP)**. An authenticator (such as a hardware security key, phone platform, or synced passkey) creates and uses a key pair. The **private key** is managed by the authenticator; the server stores the **public key** and necessary metadata to verify signatures.

WebAuthn resists phishing by binding credentials to website identity: the browser enforces the **Relying Party ID (RP ID)** and populates data with the **origin** of the page calling WebAuthn; the server must verify both when completing registration and login. WebAuthn is not merely “signing a challenge.” A valid signature under a public key **is not enough** if the challenge, origin, RP ID, user state, and user verification policy do not match.

In a **Spring Security Servlet** application, treat the following as distinct layers:

- **RP ID:** domain identifier scoping where a credential may be used, e.g., `example.com`. Contains no `https://`, port, or path.
- **Origin:** specific website origin, essentially the `scheme://host[:port]` triple, e.g., `https://login.example.com`. Must be matched against the application’s approved origins.
- **HTTPS / secure context:** security requirement for browsers to expose the WebAuthn API in production, while also protecting challenges and login sessions in transit.
- **Public-key credential store:** stores credential ID, public key, user handle, counter, and metadata; **never stores private keys** or treats credential IDs like passwords.
- **Ceremony verification:** verifies registration (`navigator.credentials.create`) or authentication (`navigator.credentials.get`), especially `challenge`, `clientDataJSON`, `authenticatorData`, and the signature.

Goal by the end of this lesson: configure RP ID/origins properly, understand verification steps, design a secure credential storage table, test key invariants with Java 17+, and avoid common pitfalls when deploying passkeys with Spring Security.

## 2. RP ID and Origin: Related Yet Different

### 2.1. What Is a Relying Party ID?

The RP ID is the domain identifier an authenticator uses to scope a credential to a relying party. It is typically the hostname or a valid domain suffix of the web page’s hostname calling WebAuthn; **it must not arbitrarily pick an unrelated domain or a public suffix like `com`** in standard cases.

Example of an application logging in at `https://login.example.com`:

- RP ID `login.example.com`: scoped strictly to the login host.
- RP ID `example.com`: can support multiple subdomains under `example.com` if architecture and origin policy permit.
- RP ID `accounts.other.example`: not a valid RP ID under standard domain rules for origin `login.example.com`.
- RP ID `com`: invalid because it is a public suffix.
- RP ID `https://example.com` or `example.com:443`: **malformed**; these are not RP ID hostnames.

**Security principle:** choose a fixed RP ID as narrow as possible for your actual access scope. If subdomains belong to different administrative/risk groups, separate RP IDs appropriately and use strict origin allowlists. Do not automatically set the RP ID to the parent domain just because you “want passkeys on every subdomain.”

There are extension mechanisms for **related origins** in certain WebAuthn/browser versions; those follow constrained processes and do not allow arbitrary unrelated domains to share an RP ID freely. Before using them, check the specification, browser support, and trust configuration. For standard architectures, follow host/valid-domain-suffix rules.

### 2.2. What Is an Origin?

The origin describes the **exact website calling the WebAuthn API**. For standard web apps, an origin consists of scheme (HTTP/HTTPS), hostname, and port (with default-port normalization rules). Examples:

| Website Calling API | RP ID `example.com` | Server Origin to Check |
| --- | --- | --- |
| `https://example.com` | Valid per domain relationship | `https://example.com` |
| `https://login.example.com` | Valid per domain relationship | `https://login.example.com` |
| `https://app.example.com` | Valid per domain relationship | `https://app.example.com` |
| `https://login.example.com:8443` | RP ID domain still matches | **Different origin** from `https://login.example.com` due to port |
| `https://evil-example.com` | **Not** the same domain/valid suffix | `https://evil-example.com` must be rejected |
| `http://login.example.com` | HTTPS not guaranteed | Not a safe production origin for WebAuthn |

One RP ID can correspond to **multiple valid origins**: for example, the server only permits `https://login.example.com` and `https://account.example.com` to share `example.com`. However, the list must be **explicit** and controlled—never match strings carelessly with `endsWith("example.com")` because `evil-example.com` also matches naive comparisons.

**Origin differs from the HTTP `Origin` request header.** During WebAuthn verification, the server must read the `origin` field inside **`clientDataJSON`** produced by the WebAuthn client alongside signature and challenge checks. Never treat `Host`, `X-Forwarded-Host`, or the `Origin` header alone as proof that an assertion came from a valid origin. Infrastructure headers can help with routing/CSRF, but do not replace WebAuthn verification.

### 2.3. Why Are Both RP ID and Origin Needed?

The two checks prevent different problems:

1. The authenticator computes `rpIdHash = SHA-256(rpId)` inside `authenticatorData`, binding the assertion to the RP ID.
2. `clientDataJSON.origin` reports the origin where the browser ran the WebAuthn ceremony; the server compares it against allowed origins.
3. The signed data binds `authenticatorData` with `clientDataJSON`, so neither origin nor `rpIdHash` can be altered arbitrarily while keeping a valid signature.

Checking only `rpIdHash` without verifying origin leaves an untrusted subdomain within the RP ID scope as a risk. Checking only origin without `rpIdHash` fails to prove the credential is being used for the intended RP ID. **Always verify both.**

## 3. rpIdHash, clientDataJSON, and Signature

During WebAuthn authentication, the server typically receives these key components:

```text
credential.id / rawId       -> Credential ID used to look up public key
response.clientDataJSON     -> client data JSON bytes
response.authenticatorData  -> Authenticator data bytes
response.signature          -> Signature from authenticator
response.userHandle         -> Optional user handle (discoverable credential)
```

At minimum, the server verifies:

- `clientDataJSON.type` is `webauthn.get` for authentication or `webauthn.create` for registration.
- `clientDataJSON.challenge` matches the challenge **issued for this ceremony**, unexpired and unused; handle base64url and bytes accurately.
- `clientDataJSON.origin` is in the RP’s origin allowlist, not merely a similar-looking domain.
- `authenticatorData.rpIdHash` matches `SHA-256` of the configured RP ID.
- **User Presence (UP)**, **User Verification (UV)** flags, and additional rules are checked per policy and ceremony type.
- For authentication, the signature is verified using the credential’s stored public key over the byte sequence **`authenticatorData || SHA-256(clientDataJSON)`**, never by re-serializing parsed JSON.
- Credential ID, user handle, and account fields are consistent with the credential store; account access must never be decided solely from a browser-sent user ID.

If any check fails, **do not create a login session or record a credential as registered**.

### 3.1. Java 17+ Demo: RP ID Hash and Domain Suffix Relationship

The following program is standalone, using only JDK 17. It demonstrates the SHA-256 length of an RP ID and dot-separated domain suffix matching. **Do not use this demo function to replace a real WebAuthn verifier**, as it does not check public suffixes, IDN, related origins, client data, or signatures.

File `WebAuthnRpIdDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;

public final class WebAuthnRpIdDemo {
    static byte[] rpIdHash(String rpId) throws NoSuchAlgorithmException {
        return MessageDigest.getInstance("SHA-256")
            .digest(rpId.getBytes(StandardCharsets.UTF_8));
    }

    static boolean hasRpIdSuffix(String host, String rpId) {
        String h = host.toLowerCase(Locale.ROOT);
        String rp = rpId.toLowerCase(Locale.ROOT);
        return h.equals(rp) || h.endsWith("." + rp);
    }

    public static void main(String[] args) throws Exception {
        String rpId = "example.com";
        byte[] expected = rpIdHash(rpId);

        System.out.println(expected.length);
        System.out.println(hasRpIdSuffix("login.example.com", rpId));
        System.out.println(hasRpIdSuffix("evil-example.com", rpId));
        System.out.println(MessageDigest.isEqual(
            expected, rpIdHash("example.com")));
        System.out.println(MessageDigest.isEqual(
            expected, rpIdHash("other.example.com")));
    }
}
```

Run:

```bash
javac WebAuthnRpIdDemo.java
java WebAuthnRpIdDemo
```

Exact stdout:

```text
32
true
false
true
false
```

**Real-deployment note:** the RP ID must pass WebAuthn/browser validity checks, including public suffix rules and IDN cases; do not build policy solely by matching a suffix string. Signatures must be verified over raw bytes using a tested, securely maintained WebAuthn library.

## 4. HTTPS, Secure Contexts, and Reverse Proxies

### 4.1. HTTPS Is a Foundational Requirement

In modern browsers, WebAuthn is available only in a **secure context**. In production, registration/login websites must use HTTPS with valid certificates and no downgrade to HTTP.

- `https://login.example.com` is a valid production origin when TLS and RP configuration are correct.
- `http://login.example.com` is not an appropriate production WebAuthn origin.
- Browsers have an exception for **potentially trustworthy localhost** during development, e.g., `http://localhost`. **Do not infer** that HTTP on arbitrary staging/production domains also works.
- When developing on IP addresses, custom hostnames, or proxies, secure-context/RP ID behavior may differ; test directly on real environments rather than relaxing production policies.

HTTPS does not replace WebAuthn origin verification. A phishing site can also hold a valid HTTPS certificate for the *attacker’s domain*. WebAuthn prevents phishing only when RP ID/origin/challenge and signatures are verified accurately.

### 4.2. TLS Termination Behind a Proxy

Architecture:

```text
Browser -- HTTPS --> Gateway / Load Balancer
                      |
                      +-- TLS / trusted internal link -->
                          Spring Boot Servlet application
```

The server must know its true public domain to configure RP ID and allowed origins. Never derive RP ID from `request.getServerName()` when requests can be routed internally; nor should you blindly trust any `X-Forwarded-*` values coming from the Internet.

Requirements:
1. Trust forwarded headers only from **authenticated/controlled reverse proxies**.
2. Proxies must strip client-supplied `Forwarded` / `X-Forwarded-*` headers before setting new values.
3. Set RP ID and allowed origins explicitly per environment, e.g., production RP ID `example.com` and origin `https://login.example.com`.
4. Enable HTTP → HTTPS redirects and HSTS for appropriate hosts after verifying long-term HTTPS capability; use `Secure`/`HttpOnly`/`SameSite` session cookies where applicable.
5. Protect the link between proxy and application per architecture; never expose backend endpoints directly to the public internet over uncontrolled HTTP.

Ports matter for **origins**: `https://login.example.com:8443` is not the same as `https://login.example.com`. RP IDs never include ports. When moving from dev to production, never copy dev origins into the production allowlist.

## 5. Credential Registration Flow (Registration / create)

Registration is when a key pair is created and the public key is bound to an account.

```text
(1) User logs in with a trusted method
    -> requests passkey registration, with reauthentication check if needed
(2) Server generates random, short-lived, unique challenge for the ceremony
    -> returns PublicKeyCredentialCreationOptions
(3) Browser calls navigator.credentials.create({ publicKey: ... })
    -> checks origin/RP ID; authenticator creates credential
(4) Browser returns credential ID + attestation response to server
(5) Server verifies challenge, type, origin, RP ID hash,
    UP/UV flags, credential public key, format/algorithm...
(6) Only after successful verification, persist credential to database
    -> bind it to the right account and mark ceremony as used
```

### 5.1. Components of Creation Options

**Illustrative structural** example (binary fields must be converted to proper bytes before calling the browser API):

```json
{
  "rp": {
    "id": "example.com",
    "name": "Example"
  },
  "user": {
    "id": "BASE64URL_USER_HANDLE",
    "name": "alice@example.com",
    "displayName": "Alice"
  },
  "challenge": "BASE64URL_RANDOM_CHALLENGE",
  "pubKeyCredParams": [
    { "type": "public-key", "alg": -7 },
    { "type": "public-key", "alg": -257 }
  ],
  "timeout": 60000,
  "attestation": "none",
  "authenticatorSelection": {
    "userVerification": "required"
  }
}
```

In the native WebAuthn API, `challenge` and `user.id` are bytes (`BufferSource`), **not raw strings**. When HTTP APIs pass options as JSON, the client must use base64url → bytes conversion or browser WebAuthn JSON helpers. `user.id` (user handle) should be an opaque, stable identifier without clear personal data such as email. Display names only help users recognize credentials; never use them as security keys.

Points to verify when completing registration:

- The user **is authenticated** and authorized to add a credential to that specific account.
- The challenge is cryptographically random, sufficiently long (typically at least 16 bytes, 32 bytes preferred), bound to the transaction/user, short-lived, and never reused.
- `clientDataJSON.type == "webauthn.create"`; `origin` is in the allowlist; challenge matches.
- `authenticatorData.rpIdHash` matches the RP ID; UP/UV satisfy policy.
- Attested credential data contains the credential ID and public key; verify structure/algorithm match policy.
- If policy **requires attestation of authenticator model**, verify trust chains, metadata, and trust policies. If device attestation is unnecessary, `attestation: "none"` can be used, while still verifying required registration data.
- Credential ID is not already assigned to another account in the same RP, respecting unique constraints; save against the authenticated account.
- Persist only after the verifier returns success; discard the challenge and pending state upon success or expiration.

**Attestation is not assertion.** Attestation applies at registration for authenticator provenance info; assertion proves private-key possession during login. Do not mistakenly demand attestation on every login, and never trust attestation solely because a client sent a certificate.

## 6. Authentication Flow (Authentication / get)

With a registered credential, the browser calls `navigator.credentials.get` to produce an assertion against a fresh challenge.

```text
(1) Client requests starting login
(2) Server creates fresh challenge, binds transaction
    -> returns PublicKeyCredentialRequestOptions (rpId, challenge,
       allowCredentials if appropriate, userVerification...)
(3) Browser calls navigator.credentials.get({ publicKey: ... })
    -> authenticator generates signature using the right private key
(4) Server receives credential ID, clientDataJSON,
    authenticatorData, signature, userHandle (nullable)
(5) Server looks up stored credential and verifies:
    - challenge + origin + type == webauthn.get
    - rpIdHash + UP/UV
    - signature using registered public key
    - credential/userHandle/account binding and counter/policy
(6) If valid, create Authentication/session per Spring Security architecture
    and update credential metadata safely
```

### 6.1. Request Options

```json
{
  "challenge": "BASE64URL_NEW_CHALLENGE",
  "rpId": "example.com",
  "timeout": 60000,
  "userVerification": "required"
}
```

`allowCredentials` is omitted in this example: the browser can use a **discoverable credential** (passkey) to support an appropriate username-less flow. If the system already knows the account, it can send `allowCredentials` containing the account’s permitted credential IDs. Regardless of model, the server must verify the credential ID and user binding itself; never trust any client-sent account ID/userHandle without checking the database.

### 6.2. Exact Signature Verification

For assertions:

```text
signedBytes = authenticatorDataBytes ||
              SHA-256(clientDataJSONBytes)

verifySignature(storedPublicKey, signedBytes, signatureBytes)
```

`||` denotes byte concatenation, not string addition. Never parse JSON and re-stringify it before hashing: the signature covers the **original bytes** of `clientDataJSON`. The verifier library is responsible for decoding the COSE public key, signature algorithm, authenticator flags, and checking structure; never roll full WebAuthn crypto with regexes or custom parsers.

A valid `signature` is still insufficient if `origin` or `challenge` is wrong. In particular, the server must never accept a challenge from a different account/transaction or an already-used challenge.

### 6.3. UP, UV, BE, BS, and signCount

- **UP (User Presence):** the authenticator recorded user presence interaction when required by the ceremony.
- **UV (User Verification):** the authenticator performed local user verification as required, such as biometrics/PIN. If policy requires UV, the server must check the **UV** flag; do not just rely on `userVerification: "required"` in request options.
- **BE (Backup Eligible)** and **BS (Backup State):** useful metadata for syncable/backup-capable credentials; interpret them per WebAuthn policy and authenticator variants, never as the sole basis to accept/reject.
- **`signCount`:** a counter that can help detect cloned credentials in certain authenticators. For synced/multi-device passkeys, counters may be 0 or not increment in the traditional way. **Do not enforce a rigid “non-increasing counter means account compromise” rule for all passkeys**; instead use risk signals, product policy, and documented sync handling.

After successful verification, update `lastUsedAt`, counter, and backup state; watch out for concurrent requests and optimistic locking. Never let a counter-write race mark an unverified assertion as successful.

## 7. Public-Key Credential Storage: Which Data Belongs on the Server?

WebAuthn stores the private key on the **authenticator**; for synced passkeys, keys may be protected and synced by the ecosystem mechanism, yet the RP server still **never receives the private key**. The server must keep the public credential record and account relationship.

| Field | Suggested Storage Type | Purpose / Notes |
| --- | --- | --- |
| `user_id` | Internal foreign key to users table | True account owner; enforce authorization when adding/removing credentials |
| `rp_id` | Configured domain string | Prevents credential mixing across RPs and aids auditing/migration |
| `credential_id` | Bytes/BYTEA or normalized base64url | ID returned by authenticator, used for lookup; unique within RP scope |
| `public_key_cose` | Bytes/BYTEA | Public key in COSE/verifier format; **not a secret** |
| `user_handle` | Bytes/BYTEA (opaque, stable) | Links account for discoverable passkeys; avoid email/password |
| `sign_count` | Non-negative integer | Standard counter, do not assume strictly increasing |
| `backup_eligible`, `backup_state` | Boolean/nullable | Metadata aiding policy/risk assessment |
| `aaguid` | UUID/bytes, if present | Authenticator model metadata; not trust proof without attestation verification |
| `transports` | List/JSON as needed | Hint aiding credential selection; not an auth factor |
| `created_at`, `last_used_at` | Timestamp | Auditing, credential management UI, stale-record detection |
| `revoked_at` or status | Timestamp/enum | Revokes auth method when user reports a lost device |
| `display_name` | User-supplied text | For UI “MacBook”, “Security Key”; never used in auth decisions |

### 7.1. PostgreSQL Schema Example

This is a **runnable illustrative PostgreSQL schema**, assuming the application already has `app_users(id UUID PRIMARY KEY)`. Choose your real schema according to the repositories of the Spring Security/WebAuthn library version you use; **do not assume Spring Security classes automatically map to this table**.

```sql
CREATE TABLE webauthn_credentials (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id),
    rp_id VARCHAR(253) NOT NULL,
    credential_id BYTEA NOT NULL,
    public_key_cose BYTEA NOT NULL,
    user_handle BYTEA NOT NULL,
    sign_count BIGINT NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
    backup_eligible BOOLEAN,
    backup_state BOOLEAN,
    aaguid UUID,
    display_name VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,

    CONSTRAINT uq_webauthn_rp_credential
        UNIQUE (rp_id, credential_id)
);

CREATE INDEX idx_webauthn_credentials_user
    ON webauthn_credentials (user_id)
    WHERE revoked_at IS NULL;
```

Explanation:
- `credential_id` and `public_key_cose` should store **exact bytes**, avoiding encodings that drop `+`, `/`, or `=` and cause comparison mismatches. If the API uses base64url, decode at the boundary and store consistently.
- `UNIQUE (rp_id, credential_id)` reduces the risk of one credential being illicitly bound to two accounts under the same RP. On duplicate errors, **reject/investigate** rather than reassigning accounts.
- `user_handle` should be generated with a CSPRNG, remain stable **per account**, and be stored in the user identity store; repeating the user handle across multiple credentials of the same account is normal. You may alternatively normalize it into a foreign key to a dedicated `userHandle` mapping table.
- `revoked_at` marks a removed credential; the verifier must never accept a revoked record.
- This is security- and privacy-sensitive data: restrict DB permissions, secure backups, monitor access, and protect data per organizational policy. Even though public keys are not passwords, account ↔ device/credential ID relationships can be privacy-sensitive.

### 7.2. Do Not Store the Wrong Secrets

**Never store** private keys, PINs, biometrics, authenticator secrets, or a copy of device credentials because the server never needs them. Do not collect biometric data just to check `UV`; WebAuthn is designed for the authenticator to verify locally while the RP checks protocol flags.

**Do not treat `credential_id` as a bearer token or password.** It is used to look up the public key; anyone knowing a credential ID **cannot log in** without producing a valid signature using the private key. Still, avoid bulk-exposing credential IDs/user handles since that can enable tracking, enumeration, or account correlation.

### 7.3. Challenge Storage Differs from Credential Storage

A **challenge** is not a credential: it is a short-lived anti-replay value generated fresh for each ceremony. Challenge state can live in a server-side session or short-TTL cache (`Redis`, DB TTL, session store); lookup keys must bind to the transaction and appropriate user/flow. It must be checked once and invalidated after completion/expiration.

Example state model:

```text
challenge_id / transaction_id
challenge_bytes
ceremony_type: register | authenticate
expected_rp_id
allowed_origins
user_id (for registration; or appropriate user context)
created_at / expires_at / consumed_at
```

The HTTP API should return only the challenge and needed transaction reference; never let the client re-pick expected RP ID/origins at completion. If using a stateless signed-state challenge design, you must still enforce anti-replay, ceremony/context binding, and expiration; a state signature **does not automatically guarantee single-use**.

## 8. Spring Security Servlet: Integrating WebAuthn at the Right Layer

Spring Security supports WebAuthn/passkeys in modern versions. **DSL names, endpoints, repositories, and customization points can differ across Spring Security versions**; always check the API in your actual dependency, migration guide, and application test suite. Do not rewrite pre-standard validators when the library provides safe verification mechanisms.

### 8.1. Shaping the Right Configuration

The Spring Security 6.4+ sketch below shows the core ideas in `SecurityFilterChain`, using the WebAuthn configurer with `rpId` and `allowedOrigins`. This is a **configuration snippet inside a Spring Boot application** (with a Spring Security version supporting WebAuthn), not a standalone Java program:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebAuthnSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .webAuthn(webAuthn -> webAuthn
                .rpId("example.com")
                .allowedOrigins("https://login.example.com"));

        return http.build();
    }
}
```

Key points to read accurately:
1. **`rpId("example.com")`** is a domain RP ID without scheme/port.
2. **`allowedOrigins("https://login.example.com")`** is the list of website origins accepted by the server for WebAuthn ceremonies, not an automatic CORS allowlist for all requests.
3. Authentication flow, login pages, ceremony start/finish endpoints, credential/user-handle persistence, and registration UI must also be configured per the running module/API version. **Do not treat the snippet above as a complete passkey application.**
4. Do not disable CSRF globally because “we have WebAuthn.” Browsers still maintain session cookies after WebAuthn login; other POST/PATCH/DELETE endpoints need appropriate CSRF protection.
5. Never put `permitAll` on every credential management API. **Adding credentials** and **deleting credentials** are account-sensitive actions that must require an authenticated user and usually re-authentication (step-up/recent authentication).

A clean config class does not replace storage and verifier design. In many Spring Security setups, developers must supply repositories for users/credentials (or use an appropriate JDBC implementation). Read the exact repository interfaces, schemas, and configuration methods of your **version** before naming real beans/tables.

### 8.2. Managing RP ID and Allowed Origins per Environment

Example of a testable strategy:

| Environment | RP ID | Allowed Origins | Notes |
| --- | --- | --- | --- |
| Production | `example.com` | `https://login.example.com` | Real domain/HTTPS, trusted login origins only |
| Staging | `staging.example.com` | `https://login.staging.example.com` | Do not unnecessarily share credential scope with production |
| Local dev | `localhost` when supported by browser/library | `http://localhost:8080` | Localhost secure-context exception for dev only |
| Intentional multi-origin | `example.com` | `https://login.example.com`, `https://account.example.com` | Only if both origins are operated and protected at the same trust level |

If you want to change RP ID from `login.example.com` to `example.com`, **existing credentials do not automatically migrate scope**. Users may need to register new credentials or follow a migration plan allowed by the specification/mechanism. Never change production configuration without a plan for existing credentials.

### 8.3. Browser API and JSON Conversion

Browsers use two WebAuthn operations:

```javascript
// Registration (after fetching options from server):
const creationOptions =
    PublicKeyCredential.parseCreationOptionsFromJSON(optionsJson);
const credential = await navigator.credentials.create({
  publicKey: creationOptions
});
// Send credential.toJSON() to registration completion endpoint.

// Login (after fetching options from server):
const requestOptions =
    PublicKeyCredential.parseRequestOptionsFromJSON(requestOptionsJson);
const assertion = await navigator.credentials.get({
  publicKey: requestOptions
});
// Send assertion.toJSON() to authentication completion endpoint.
```

This is **workflow-illustrative code**, with `optionsJson`/`requestOptionsJson` returned by the backend in the previous step; not a standalone runnable file. Modern JSON helpers and `toJSON()` should be **feature-detected** per browser; where unsupported, convert binary fields base64url ↔ `ArrayBuffer` properly. Never pass a raw JSON string as the WebAuthn API `challenge` without converting to bytes.

Client JavaScript only orchestrates the browser. **The server decides whether the ceremony is valid** after verifying challenge, RP ID, origin, flags, signature, and account. Never let the frontend choose RP ID, origin allowlists, or send a “verified” boolean that the server trusts.

## 9. Session Controls, CSRF, and Credential Management

WebAuthn protects assertion creation via challenge and origin binding, yet account systems still have many surfaces to defend.

### 9.1. Credential Registration Is a Sensitive Operation

If an attacker attaches their credential to a victim’s account, they can log in later. Therefore the “add passkey” endpoint should:
- Require the user to be logged into that account, with CSRF protection when using cookies/sessions.
- Consider **recent authentication/step-up** before adding or deleting passkeys.
- Bind the challenge to the account and active registration ceremony.
- Never allow the client to supply a `user_id` different from the session account and persist it.
- Send security notifications and write audit records whenever a credential is added or removed.
- Provide a way to revoke lost/stolen credentials while avoiding locking users out when losing their last device.

### 9.2. WebAuthn Login and Session Cookies

After a valid assertion, Spring Security typically establishes authentication and may create a login session via session cookie depending on application architecture. When doing so:
- Session cookies need appropriate `Secure`, `HttpOnly`, `SameSite`, and session fixation/logout policies.
- State-changing endpoints still need CSRF protection whenever browsers auto-send cookies.
- Never reuse a WebAuthn challenge as an app-wide CSRF token.
- Never put credential IDs, challenges, or raw authenticator responses into URLs.
- Rate-limit ceremony start/finish and credential management actions; curb account enumeration with appropriate errors/responses.

### 9.3. Distinguishing “Phishing-Resistant” from “Invulnerable”

WebAuthn reduces phishing that harvests passwords and manually typed TOTP codes on spoofed websites because keys bind to RP ID. However, XSS on the real origin, stolen session cookies, malicious extensions, weak account recovery, or insecure admin credentials can still cause account takeover. Protecting origins, sessions, recovery, domain management, and the supply chain remains essential.

## 10. Testing and Design QA

### 10.1. RP ID/Origin Test Matrix

| Test | Expected |
| --- | --- |
| `https://login.example.com` with RP ID `example.com` | Valid per domain relationship; origin must be in allowlist |
| `https://evil-example.com` with RP ID `example.com` | Invalid under RP ID relationship |
| `https://login.example.com:8443` when only `https://login.example.com` allowed | Different origin due to port, must reject |
| `http://login.example.com` when production is HTTPS-only | Must not be accepted |
| RP ID `https://example.com` | Invalid RP ID format |
| Disallowed origin even with matching `rpIdHash` | Server still rejects ceremony |
| Wrong `clientDataJSON.type` | Server rejects |
| Stale/wrong/consumed challenge | Server rejects, creates no auth |
| Mismatched `authenticatorData.rpIdHash` | Server rejects |
| Invalid signature | Server rejects |
| UV required but UV flag missing | Server rejects |
| Credential ID already belongs to another account | Registration must be rejected, never reassigned |
| Revoked credential | Assertion does not create login |
| Username-less login sends `userHandle` mismatching mapping | Server rejects |
| Counter does not increment on synced passkey | Apply designed policy/risk handling; do not blindly assume clone |

### 10.2. API-Level Integration Testing

In a Spring Security Servlet application, test end-to-end flows with an appropriate WebAuthn test/vector library:

1. Register a credential from a valid origin, then inspect the DB row for `credential_id`, public key, right user, and RP ID; no private key present.
2. Attempt completing registration with a `clientDataJSON.origin` outside the allowlist or wrong challenge; no new DB row created.
3. Log in with the registered credential using a fresh challenge and valid signature; verify `Authentication`/session is granted and `last_used_at` audit updates.
4. Attempt replaying an old assertion; rejected due to used/expired challenge.
5. Attempt swapping credential ID or user handle to another account; rejected.
6. Change origin scheme, host, or port without updating the allowlist; rejected.
7. Test CSRF cookies when adding/removing passkeys, plus rate-limiting/re-auth.
8. Run behind a real reverse proxy to verify public origin and forwarded header configuration with no trust-header injection.

**Do not send a fake MockMvc request with a pre-populated `Authentication` and claim you tested WebAuthn crypto.** Such tests only verify authorization/filter logic; dedicated tests are needed for challenge, client data, authenticator data, and signature verification.

### 10.3. Operations Checklist

- [ ] Choose RP ID matching the real domain, without scheme/port/path, and never a public suffix.
- [ ] Allowed origins are an exact per-environment list, including ports where needed, without arbitrary wildcards.
- [ ] Production uses valid HTTPS/TLS; forwarded headers trusted only from controlled proxies.
- [ ] Registration and authentication generate CSPRNG challenges with TTL, bound context, and single-use.
- [ ] Verify `type`, challenge, `clientDataJSON.origin`, `rpIdHash`, UP/UV, signature, and account mapping.
- [ ] Registration stores credential ID/public key/user handle/counter/metadata after successful verification; **never stores private keys/PINs/biometrics**.
- [ ] Unique constraint on credential ID per RP, authorization checks on adding/removing credentials, revocation and recovery supported.
- [ ] `signCount` policy accounts for synced passkeys and backup flags rather than treating counter 0 as an automatic error.
- [ ] Negative tests exist for unknown origins, different `rpIdHash`, challenge replay, bad signatures, revoked credentials, and account substitution.
- [ ] If login creates a session cookie, keep CSRF protection on state-changing actions, session hardening, and logout.
- [ ] Staging/production tested on separate domains without “moving” credential scopes by editing RP ID.
- [ ] Verifier/repository compatible with the actual Spring Security version; never re-implement WebAuthn cryptography yourself.

## 11. Common Pitfalls and Solutions

1. **Confusing RP ID with origin:** setting `rpId("https://login.example.com")`. Fix to the domain RP ID, and configure origins separately.
2. **Checking only `rpIdHash`:** ignoring `clientDataJSON.origin`. Fix with an exact origin allowlist and signature/challenge verification.
3. **Suffix wildcards without a leading dot:** `endsWith("example.com")` can accept `evil-example.com`. Use a standard library and explicit origin allowlists.
4. **Ignoring ports:** `https://login.example.com:8443` is not the same origin as default-port HTTPS.
5. **Using HTTP on production domains:** secure context/transport fails; serve over HTTPS.
6. **Configuring RP ID from client `Host` headers:** vulnerable to header spoofing, especially behind proxies. Read from trusted configuration.
7. **Storing private keys on the backend:** violates the WebAuthn model. The backend stores public-key credentials and never needs private keys.
8. **Storing challenges as long-lived credentials:** confuses short-lived anti-replay data with registered credentials; challenges must be single-use and expire.
9. **Forgetting to verify signatures over original bytes:** re-serializing `clientDataJSON` before hashing can fail and weaken verification logic.
10. **Trusting browser-sent `userHandle`:** must verify against credential ID and DB account mapping.
11. **Enforcing strict monotonic increases on every `signCount`:** synced passkeys may lack useful counters; use proper policy/risk handling.
12. **Assuming WebAuthn replaces CSRF:** if login creates a cookie session, account actions still need CSRF defense.
13. **Changing domain/RP ID expecting old passkeys to keep working:** scope is a binding attribute requiring planned migration.
14. **Allowing anonymous registration for arbitrary accounts:** enables account takeover; registration must bind to an authenticated user and proper permissions.
15. **Treating “user already logged in” tests as WebAuthn tests:** misses real challenge/origin/rpIdHash/signature verification.

**Summary:** RP ID answers “which domain scope does the credential belong to”; origin answers “which webpage invoked WebAuthn”; HTTPS guarantees a secure context and transport; the credential store holds **credential ID + public key + account binding + metadata**, never private keys. A WebAuthn ceremony succeeds only after the server verifies **challenge, origin, RP ID hash, signature, and user policy**. In Spring Security Servlet, use the version-appropriate WebAuthn integration, persist credentials durably, and test the entire security flow through proxies and browsers.
