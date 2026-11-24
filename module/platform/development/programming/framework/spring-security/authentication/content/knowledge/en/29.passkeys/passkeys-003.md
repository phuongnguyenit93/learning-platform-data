# Passkeys: how the credential registration flow differs from authentication by assertion

## 1. Big picture

Passkeys use WebAuthn/FIDO2 technology, allowing a Relying Party (RP, the web application) to authenticate users using public-key cryptography. The application never needs to receive a password or the passkey's private key. Users can unlock a passkey with a PIN, biometrics, or the authenticator's verification mechanism.

**WebAuthn has two distinct ceremonies that cannot be interchanged:**

- **Registration / credential creation:** The browser calls `navigator.credentials.create()`; the authenticator creates a new credential and key pair. The server verifies the registration response, then stores **credential ID + public key + account association**.
- **Authentication / assertion:** The browser calls `navigator.credentials.get()`; the authenticator uses the **existing private key** to sign a fresh challenge. The server verifies the signature using the **public key stored during registration**, then authenticates the account.

> **Registration issues and binds a new login method. Assertion uses an already-registered method to prove authority to use the credential.** Succeeding in `create()` is not yet signing in; succeeding in `get()` is also not signing in until the server verifies the assertion.

Lesson objectives:
1. Understand the similarities and differences between a registration challenge and an authentication challenge.
2. Distinguish `attestationObject` in registration from `authenticatorData + signature` in assertion.
3. Grasp the server-side WebAuthn verification suite: `challenge`, `type`, `origin`, `rpIdHash`, UP/UV, attestation/credential data, or signature.
4. Implement Spring Security 6.5 configuration with Java 17+ for both flows, understanding state and persistence.
5. Test account linking, replay, phishing resistance, credential data, and sessions.

## 2. Components and terminology

| Component / data | Meaning |
|---|---|
| **Relying Party (RP)** | Application server that owns accounts, creates challenges/options, and verifies results |
| **Browser / WebAuthn client** | User agent executing `navigator.credentials.create/get`, providing `origin` info |
| **Authenticator** | Device, platform, or passkey provider that creates/holds the private key and performs signing |
| **Credential ID** | Binary value identifying a credential for server lookup |
| **Public key** | Stored by the server after registration and used to verify login signatures |
| **Private key** | Never sent to the RP; protected by the passkey provider and may sync in multi-device models |
| **RP ID** | Domain, e.g., `example.com`, hashed into authenticator data |
| **Origin** | Scheme + hostname + port of the page, e.g., `https://login.example.com` |
| **Challenge** | Random byte sequence, fresh per ceremony; prevents replay |
| **`user.id` / `userHandle`** | Stable opaque account identifier in the RP, not necessarily username/email |
| **Attestation** | Data about the new credential and, if required by policy, authenticator provenance info |
| **Assertion** | Data proving the private key signed the challenge and authentication context |
| **UP** | User Presence: the authenticator detected a sign of user presence |
| **UV** | User Verification: the authenticator verified the user via PIN/biometrics |

A synced passkey can be used across multiple devices. Do not assume "the private key is always hardware-locked to one exact machine"; however, the private key **is never sent to the RP server** during registration or authentication.

### Two distinct checks

~~~text
REGISTRATION:
  create() → authenticator creates key pair
  → returns credential ID + attestation object
  → RP verifies then SAVES NEW PUBLIC KEY

AUTHENTICATION:
  get() → authenticator uses EXISTING PRIVATE KEY to sign challenge
  → returns authenticatorData + clientDataJSON + signature
  → RP LOOKS UP STORED PUBLIC KEY and verifies signature
~~~

**Credential ID is not a password:** knowing the credential ID is insufficient to produce a valid assertion. **A registration/attestation signature is also not an authentication signature**; attestation has its own role in verifying provenance and credential properties at creation time.

## 3. Comparison table: registration vs. authentication

| Criterion | Registration | Authentication |
|---|---|---|
| Purpose | Bind a new credential to an account | Verify an already-bound credential |
| Browser API | `navigator.credentials.create` | `navigator.credentials.get` |
| Options | `PublicKeyCredentialCreationOptions` | `PublicKeyCredentialRequestOptions` |
| User | RP must know which account is authorized to add a passkey | RP looks up account via verified credential ID/`userHandle` |
| Cryptographic key | Authenticator generates a public/private key pair | Uses private key of an existing credential |
| `clientDataJSON.type` | `webauthn.create` | `webauthn.get` |
| Response subtype | `AuthenticatorAttestationResponse` | `AuthenticatorAssertionResponse` |
| Key fields | `attestationObject`, `clientDataJSON` | `authenticatorData`, `clientDataJSON`, `signature`, optionally `userHandle` |
| Server verification | Challenge, RP ID, origin, flags, credential structure, attestation policy | Challenge, RP ID, origin, flags, user binding, **signature with stored public key** |
| Outcome on success | Persists credential record; does not automatically create a new login session | Authenticates user, creates/updates Authentication/session |
| Key risk | Attacker covertly binds their passkey to a victim's account | Replay, cross-account credential use, skipping signature verification |

Both flows require a **server-generated challenge**, but they do not share the same challenge or the same response structure. A browser response for `webauthn.create` must never be accepted at a `webauthn.get` endpoint.

## 4. Registration flow: creating and binding a new credential

Assume Alice is logged in via an existing method and clicks **Add passkey**. For passkey-first account signup, the application needs a separately protected flow proving the right to create and bind the account, never letting a stranger simply enter Alice's email to attach a key to that account.

~~~text
Alice/browser                       RP server                    Authenticator
     |                                 |                               |
     | POST /webauthn/register/options |                               |
     |-------------------------------->| identify Alice's account      |
     |                                 | generate challenge C1         |
     |                                 | store state C1 + account      |
     |<--------------------------------| return creation options       |
     | navigator.credentials.create()  |                               |
     |---------------------------------------------------------------->|
     |                                 |         create new key pair   |
     |                                 |         UP/UV per policy      |
     |<----------------------------------------------------------------|
     | receive attestation response    |                               |
     | POST /webauthn/register         |                               |
     |-------------------------------->| verify create/C1/origin/RP ID |
     |                                 | extract credential/public key |
     |                                 | save link to Alice            |
     |<--------------------------------| success                       |
~~~

### R1. Server returns creation options

Example JSON describing the options structure (challenge and user ID are sample values, never reuse in operations):

~~~json
{
  "rp": {"id": "example.com", "name": "Learning App"},
  "user": {
    "id": "dXNlcjQy",
    "name": "alice@example.com",
    "displayName": "Alice"
  },
  "challenge": "FJ9YpeCb1MR7COoaX84e00veXBxSXd6Z_8V-9yYGkd8",
  "pubKeyCredParams": [
    {"type": "public-key", "alg": -7},
    {"type": "public-key", "alg": -8}
  ],
  "timeout": 300000,
  "excludeCredentials": [],
  "authenticatorSelection": {
    "residentKey": "preferred",
    "userVerification": "required"
  },
  "attestation": "none"
}
~~~

- `rp.id`: RP domain; not a URL with scheme/port. For instance, `example.com` can be used by origin `https://login.example.com` under appropriate domain rules.
- `user.id`: stable opaque ID issued by the server for Alice. Do not treat `user.name`/email as a cryptographic key.
- `challenge`: must be generated by CSPRNG, stored with ceremony/account/session and TTL; sufficient entropy, fresh per request.
- `pubKeyCredParams`: list of accepted algorithms; `-7` is ES256, `-8` is EdDSA in COSE.
- `excludeCredentials`: already-registered IDs to help avoid duplicates on the authenticator; the server must still enforce uniqueness itself.
- `residentKey`: relates to discoverable credentials and username-less login experiences.
- `userVerification`: requirement level such as `required` or `preferred`. The server must verify actual flags; sending options alone is insufficient.
- `attestation: none`: RP does not require device provenance proof via attestation certificates; this does not mean skipping registration checks.

### R2. Browser calls create

The browser converts binary fields `challenge`, `user.id`, and `excludeCredentials[].id` from Base64URL JSON to `ArrayBuffer`, then:

~~~javascript
const credential = await navigator.credentials.create({
  publicKey: creationOptions
});
~~~

This is a **browser JavaScript** call, not Java. `creationOptions` must be fetched directly from the RP with byte fields decoded accurately. WebAuthn can only run in a secure context; real websites use HTTPS, while `http://localhost` is a local development exception supported by browsers.

The authenticator creates a key pair and credential ID bound to the RP ID, checking user presence/verification per device and policy. **The private key does not appear in `credential.response`.**

### R3. Browser sends attestation response

Data shape after encoding binary fields as Base64URL:

~~~json
{
  "id": "dYF7EGnRFFIXkpXi9XU2wg",
  "rawId": "dYF7EGnRFFIXkpXi9XU2wg",
  "type": "public-key",
  "response": {
    "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIn0",
    "attestationObject": "o2NmbXRkbm9uZWdhdHRTdG10oA"
  }
}
~~~

The JSON above only illustrates **field shapes**; truncated bytes do not form a valid registration. Real data is returned by the browser/authenticator after `create()` succeeds.

Once decoded, `clientDataJSON` contains:
- `type = "webauthn.create"`
- `challenge` equal to the exact value C1 issued by the server
- `origin` matching the exact web page origin
- `crossOrigin` and optionally `topOrigin`, used per cross-origin policy

`attestationObject` is CBOR data containing `fmt`, `authData`, and `attStmt`. `authData` contains `rpIdHash`, flags, signature counter, and **attested credential data**: AAGUID, credential ID, and credential public key in COSE format.

### R4. Server verifies registration before saving

The RP must complete the following checks:

1. **Authorization to link:** the request belongs to Alice's account, **already authenticated and permitted to register**. Never rely on a client-supplied `user.id` or email to select the target account.
2. **Ceremony state:** locate the generated challenge C1 for the right session/account, unexpired and unused.
3. **Client type:** `clientDataJSON.type` must be `webauthn.create`; challenge must match.
4. **Origin:** match against the exact allowlist and check `crossOrigin/topOrigin` if applicable.
5. **RP ID hash:** `rpIdHash == SHA-256(expectedRpId)`.
6. **UP/UV:** enforce the user presence/verification policy; check allowed algorithms and credential data.
7. **Attestation:** process statement/trust path per format/policy. If `none`, no manufacturer certificate is required, yet all other registration checks remain mandatory.
8. **Storage:** verify credential ID uniqueness and ensure no unauthorized link to another user; only on success store **credential ID, public key, account ID, metadata** and consume the challenge.

**Browser `create()` succeeding is not the same as server registration succeeding.** The UI should only report "Passkey added" after the RP accepts and saves the credential, not merely when the device returns attestation.

## 5. What do attestation and the public key mean?

**Attestation** concerns recording/verifying authenticator characteristics or provenance **when the credential is created**, depending on RP policy. It can:
- use the `none` format, providing no device provenance proof;
- use self attestation or an accepted attestation statement/trust chain;
- support device/enterprise policies in high-assurance systems, trading off privacy and compatibility.

**There is no requirement that every consumer passkey carry a manufacturer certificate trusted by the RP.** With `attestation=none`, the RP still verifies challenge, origin, `rpIdHash`, flags, and credential structure, and stores a valid public key.

Registration normally does not authenticate a user via the signature of a **previously registered** credential; it creates/records a new credential. Thus protecting the account before adding a credential is critical. If an attacker binds their passkey to Alice's account, next time the attacker can log in as Alice using **the credential stored by the server**.

## 6. Authentication flow: verifying identity via assertion

After registration, the RP has stored credential ID + public key. On the next login, the server issues a **fresh challenge C2** and uses that public key to verify.

~~~text
Alice/browser                      RP server                  Authenticator
     |                                |                              |
     | POST /webauthn/authenticate/   |                              |
     | options                        |                              |
     |------------------------------->| create challenge C2          |
     |<-------------------------------| return request options       |
     | navigator.credentials.get()    |                              |
     |-------------------------------------------------------------->|
     |                                |            select credential |
     |                                |            UP/UV, sign C2    |
     |<--------------------------------------------------------------|
     | receive assertion response     |                              |
     | POST /login/webauthn           |                              |
     |------------------------------->| lookup credential ID         |
     |                                | verify C2, origin, rpIdHash  |
     |                                | verify signature/public key  |
     |                                | verify account/role          |
     |<-------------------------------| auth success + session       |
~~~

### A1. Server returns request options

~~~json
{
  "challenge": "mx_wD_MxCWQAP5gpGj8dqnlT7G2HxWBZxAunYADAgT0",
  "timeout": 300000,
  "rpId": "example.com",
  "allowCredentials": [],
  "userVerification": "required"
}
~~~

- `challenge` C2 is fresh and **different from C1**; never reuse across logins or sessions.
- `rpId` must still match the credential's domain.
- `allowCredentials` can list credential IDs for a known username. When empty, the browser may select a matching discoverable credential; the server **must still verify ID, key, and account mapping**.
- `userVerification` is re-checked from authenticator flags, not just trusted from browser UI.

### A2. Browser calls get

~~~javascript
const assertion = await navigator.credentials.get({
  publicKey: requestOptions
});
~~~

`requestOptions.challenge` and `allowCredentials[].id` (if present) are `ArrayBuffer`s decoded from Base64URL. The authenticator picks the credential matching the RP ID and signs the **current challenge/context** with the existing private key. **No new key pair is generated.**

### A3. Browser sends assertion

~~~json
{
  "id": "dYF7EGnRFFIXkpXi9XU2wg",
  "rawId": "dYF7EGnRFFIXkpXi9XU2wg",
  "type": "public-key",
  "response": {
    "clientDataJSON": "eyJ0eXBlIjoid2ViYXV0aG4uLmdldCJ9",
    "authenticatorData": "y9GqwTRaMpzVDbXq1dyEAXVOxrou08k22ggRC45MKNgdAAAAAA",
    "signature": "MEUCIQDBylREhLzAQ_QMXqly7sZjotCP6mMde0bo-4KbK0zaIQ",
    "userHandle": null
  }
}
~~~

The bytes in the example do not form a valid assertion; field names and structure are what matter. `userHandle` may be null in some flows. When `userHandle` is present, the RP must match it against the linked account—never treat it as standalone proof while skipping signature checks.

`clientDataJSON.type = "webauthn.get"`. In an assertion, **`authenticatorData` and `signature` are separate**; no new public key is trusted from the client. This is the clearest way to distinguish it from registration.

## 7. Server verifies assertion with the stored public key

Conceptually, the authenticator signs:

~~~text
clientDataHash = SHA-256(clientDataJSON)
signedBytes = authenticatorData || clientDataHash
signature = Sign(credentialPrivateKey, signedBytes)

RP:
  credential = lookup(credentialId)
  Verify(credential.storedPublicKey, signedBytes, signature)
~~~

The `||` symbol denotes byte concatenation. This is only a conceptual model; exact signing algorithms are handled by the COSE key/algorithm and WebAuthn verifier. **Never build your own CBOR parser or WebAuthn cryptographic verifier** instead of a tested library.

Conditions to verify alongside the signature:

1. Credential ID exists, is not revoked, belongs to the right account (if username is known), and matches the right RP/tenant.
2. Challenge C2 is exact, unexpired/unused, and tied to the ceremony/session.
3. `clientDataJSON.type == "webauthn.get"`.
4. `origin` matches the allowlist; verify `crossOrigin/topOrigin` per policy.
5. `authenticatorData.rpIdHash` is the SHA-256 of the expected RP ID.
6. UP/UV are satisfied; if policy requires UV and the authenticator only provides UP, reject.
7. `signature` is valid under the **public key stored during registration**.
8. If `userHandle` is present, account mapping matches; account is active and unrestricted.
9. Check/update signature counter and backup flags per policy; consume the challenge to prevent replay.
10. Create Spring Security `Authentication`/session and enforce domain authorization—**never elevate privileges simply because the user logged in with a passkey**.

### Why is the challenge an anti-replay condition?

If an attacker captures an earlier assertion, its signature was created for the **previous challenge**. On a new login, the server must issue a new challenge and reject the old assertion. If the server skips challenge checks, uses shared global state, or accepts expired challenges, a valid signature alone won't prevent replay.

### `signCount` and synced passkeys

Some authenticators have counters; some always return `0`. Passkeys synced across devices may not have linearly incrementing counters. An anomalous value is a **risk signal**, not absolute proof of cloning. Consider backup eligibility/state, authenticator type, and WebAuthn policy to avoid rejecting all passkeys whose counter doesn't increment.

## 8. Shared security checkpoints with different outcomes

| Check | Registration | Authentication |
|---|---|---|
| Fresh challenge | Bound to **the account adding a key** | Bound to **the login attempt** |
| Type in `clientDataJSON` | `webauthn.create` | `webauthn.get` |
| Origin | Mandatory match | Mandatory match |
| RP ID hash | Mandatory match | Mandatory match |
| User Presence / Verification | Per enrollment policy | Per login policy |
| Public key | Extracted and saved after verification | Retrieved from registered DB |
| Attestation trust | Per credential creation policy | Does not replace login signature |
| Login signature | Not the primary check here | **Mandatory verification** |
| Account | Verify **who is allowed to attach a credential** | Verify **who owns the credential** |
| Result | Adds credential record | Creates Authentication and session |

**Never use client-submitted email, displayName, or `user.id` to bind a credential to another account.** Registration is an authentication-method management action; it must require a verified account or protected bootstrap flow, with CSRF and consideration of step-up auth.

## 9. Spring Boot 3.x + Spring Security 6.5 + Java 17 example

Spring Security 6.4/6.5 provides WebAuthn configuration in the Servlet DSL. On the 6.5 line, docs require adding `webauthn4j-core` alongside Spring Security web; **do not use the 7.x `spring-security-webauthn` dependency pattern for this project**.

The example builds a demo application with initial password login so Alice can register a passkey, then log in with the passkey. The Java source below belongs to a **complete Spring Boot Maven project**, not standalone files run with `javac` without Spring dependencies.

### 9.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>passkey-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>com.webauthn4j</groupId>
            <artifactId>webauthn4j-core</artifactId>
            <version>0.29.7.RELEASE</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-security` pulls in `spring-security-web`. The WebAuthn4J version here corresponds to the Spring Security 6.5 docs example. When upgrading to Spring Security 7, re-verify dependencies—do not mix APIs across version branches.

### 9.2. Application configuration file

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

The password comes from an environment variable; never hardcode real usernames/passwords in source. If the variable is missing, the app should fail with a missing-config error rather than falling back to a weak password.

### 9.3. Main application class

File `src/main/java/com/example/passkey/PasskeyDemoApplication.java`:

~~~java
package com.example.passkey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasskeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasskeyDemoApplication.class, args);
    }
}
~~~

### 9.4. Spring Security configuration

File `src/main/java/com/example/passkey/SecurityConfiguration.java`:

~~~java
package com.example.passkey;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        var alice = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .webAuthn(webAuthn -> webAuthn
                        .rpName("Passkey Demo")
                        .rpId("localhost")
                        .allowedOrigins("http://localhost:8080"))
                .build();
    }
}
~~~

**Key points:**
- `.formLogin(...)` lets Alice sign in initially with a demo password. Only an authenticated user may add credentials to that account via the registration flow.
- `.webAuthn(...)` enables passkey registration and authentication via Spring Security; no custom signature-verification layer is needed.
- `.anyRequest().authenticated()` protects resources; login and entry points are managed by Spring Security's filter chain per this configuration.
- `.rpId("localhost")` is the RP ID for **local development**. Browsers treat `http://localhost` as a special secure context; production must use HTTPS with the proper RP domain/allowed origin.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` encodes passwords in the demo; never use `{noop}` to store production passwords.
- Do not disable CSRF: Spring Security uses POST requests to create/consume challenges, requiring valid CSRF tokens.
- Users and WebAuthn credentials are **in-memory by default**, so this demo is unsuitable for production or clusters.

### 9.5. Endpoint to inspect status after login

File `src/main/java/com/example/passkey/ProfileController.java`:

~~~java
package com.example.passkey;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/me")
    public Map<String, Object> profile(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
~~~

When Alice logs in validly with password or passkey and calls `GET /me`, expect JSON containing `username: "alice"` and `authenticated: true`. JSON key ordering is not guaranteed. The endpoint does not return credential IDs, private keys, or session details.

### 9.6. Test run

From the project directory, with Java 17+ and Maven:

~~~bash
export DEMO_USER_PASSWORD='local-demo-password'
mvn spring-boot:run
~~~

Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "local-demo-password"
mvn spring-boot:run
~~~

This password value is strictly for localhost; never use it in externally accessible environments.

Steps in a WebAuthn-capable browser:
1. Open `http://localhost:8080/login`; sign in as `alice` with the demo password.
2. Visit `http://localhost:8080/webauthn/register`; Spring Security provides a credential registration page. Create a passkey using PIN/biometrics or a security key.
3. Spring receives the attestation and saves credential ID + public key for Alice after verification.
4. Log out. Return to the login page and choose the passkey login option provided.
5. The browser creates an assertion with the registered credential; Spring verifies challenge, origin, RP ID, and signature, then establishes authentication.
6. Visit `/me` and confirm user Alice.

**Do not use `curl` with handcrafted JSON to substitute for an authenticator**, as there is no valid signature. If the browser does not allow `localhost` in a specific environment, configure an appropriate hostname and HTTPS; never disable origin validation just to make a demo run.

## 10. Spring Security 6.5 endpoints: separating the two ceremonies cleanly

Spring Security 6.5 docs describe:

| Action | Method + path | Result |
|---|---|---|
| Request creation options | `POST /webauthn/register/options` | Challenge and options bound to the authenticated user |
| Submit attestation | `POST /webauthn/register` | Registers credential, returns result after verification |
| Request authentication options | `POST /webauthn/authenticate/options` | Fresh challenge for login |
| Submit assertion | `POST /login/webauthn` | Verifies signature and completes login |

The POSTs above use CSRF tokens per standard config, along with the appropriate cookie/session. Both `/webauthn/register/options` and `/webauthn/authenticate/options` mutate server-side challenge state, so they are not static GETs.

In Spring 6.5, the registration request uses the **`publicKey.credential`** JSON structure, whereas the login assertion sends `id`, `rawId`, and `response` directly:

~~~text
Registration request:
  POST /webauthn/register
  publicKey.credential.response.attestationObject
  publicKey.credential.response.clientDataJSON
  publicKey.credential.id
  publicKey.label

Authentication request:
  POST /login/webauthn
  id, rawId, type
  response.authenticatorData
  response.clientDataJSON
  response.signature
  response.userHandle (if present)
~~~

Do not mistake `/webauthn/register` for a login endpoint or mix the response bodies of the two types. Spring's default registration/login pages are a convenient reference when building a custom frontend.

## 11. Browser JavaScript: how do binary data and payloads differ?

The browser WebAuthn API takes `ArrayBuffer` for `challenge`, registration `user.id`, `excludeCredentials[].id`, and authentication `allowCredentials[].id`; JSON from the server typically carries Base64URL. Illustrative helper functions:

~~~javascript
function fromBase64Url(s) {
  const base64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), c => c.charCodeAt(0)).buffer;
}

function toBase64Url(buffer) {
  const bytes = new Uint8Array(buffer);
  let value = "";
  for (const n of bytes) value += String.fromCharCode(n);
  return btoa(value).replace(/\+/g, "-").replace(/\//g, "_")
      .replace(/=+$/g, "");
}

function decodeCreationOptions(json) {
  return {
    ...json,
    challenge: fromBase64Url(json.challenge),
    user: {...json.user, id: fromBase64Url(json.user.id)},
    excludeCredentials: (json.excludeCredentials ?? []).map(c => ({
      ...c, id: fromBase64Url(c.id)
    }))
  };
}

function decodeRequestOptions(json) {
  return {
    ...json,
    challenge: fromBase64Url(json.challenge),
    allowCredentials: (json.allowCredentials ?? []).map(c => ({
      ...c, id: fromBase64Url(c.id)
    }))
  };
}
~~~

After receiving options from the backend via `fetch` with CSRF/session and checking the HTTP response:

~~~javascript
// Registration ceremony: create a new credential.
const created = await navigator.credentials.create({
  publicKey: decodeCreationOptions(creationOptionsJson)
});

const registrationPayload = {
  publicKey: {
    credential: {
      id: created.id,
      rawId: toBase64Url(created.rawId),
      type: created.type,
      response: {
        clientDataJSON: toBase64Url(created.response.clientDataJSON),
        attestationObject: toBase64Url(
          created.response.attestationObject),
        transports: created.response.getTransports?.() ?? []
      },
      clientExtensionResults: created.getClientExtensionResults()
    },
    label: "Laptop"
  }
};
~~~

Authentication differs in the payload shape:

~~~javascript
// Authentication ceremony: sign using a registered credential.
const assertion = await navigator.credentials.get({
  publicKey: decodeRequestOptions(authenticationOptionsJson)
});

const authenticationPayload = {
  id: assertion.id,
  rawId: toBase64Url(assertion.rawId),
  type: assertion.type,
  response: {
    clientDataJSON: toBase64Url(assertion.response.clientDataJSON),
    authenticatorData: toBase64Url(
      assertion.response.authenticatorData),
    signature: toBase64Url(assertion.response.signature),
    userHandle: assertion.response.userHandle
      ? toBase64Url(assertion.response.userHandle) : null
  },
  clientExtensionResults: assertion.getClientExtensionResults()
};
~~~

This is browser-side code illustrating **serialization** and distinguishing the two responses; it omits the full HTML page, `fetch`, CSRF, and error UI. When building your own UI, send `registrationPayload` to `POST /webauthn/register` after fetching options, and send `authenticationPayload` to `POST /login/webauthn`. Mark success only after the **server response is verified**, not when `create/get` resolves.

## 12. Repositories and credential lifecycle

After registration, the RP typically persists:
- `credential_id` (bytes, unique);
- internal `user_id` or WebAuthn user entity;
- `public_key_cose` (verified public key);
- signature counter, backup flags, and transports per policy;
- created time, last-used time, revoked status, and friendly label.

Never store private keys. Never use a client-submitted `email` as the account binding key.

**Domain-illustrative** schema, not Spring's mandatory schema:

~~~sql
CREATE TABLE app_passkey_credentials (
    credential_id       BYTEA PRIMARY KEY,
    user_id             VARCHAR(100) NOT NULL,
    public_key_cose     BYTEA NOT NULL,
    sign_count          BIGINT NOT NULL DEFAULT 0,
    backup_eligible     BOOLEAN,
    backed_up           BOOLEAN,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ
);
~~~

Spring Security 6.5 uses `PublicKeyCredentialUserEntityRepository` and `UserCredentialRepository`. In-memory storage is the default; for JDBC, `JdbcPublicKeyCredentialUserEntityRepository` and `JdbcUserCredentialRepository` are provided. When moving to production, use the **exact Spring Security DDL/schema for your version**, configure transactions/constraints, and do not assume an illustrative table works with the framework repositories.

One account can have **multiple passkeys**. Provide a protected UI to view/add/remove credentials, require reauthentication when adding or removing sensitive keys, audit events, notify the owner, and maintain recovery mechanisms resistant to account takeover. Deleting/revoking a key must block logins with that public key even if it remains synced on another device.

## 13. Critical trust boundaries

### 13.1. Permission to add a passkey is sensitive

Registration must never be left open for anyone to register a credential against another account's `user.id`. The server must:
- identify the account from an authenticated `SecurityContext` (or trusted bootstrap enrollment state);
- check session freshness and consider step-up auth;
- keep CSRF protection enabled;
- notify/audit when a passkey is added or removed;
- guard against races/duplicate credential IDs.

If an attacker adds their own key to Alice's account, on the next login the attacker can produce a **completely valid** assertion with their key: the bug is in **registration account binding**, not assertion signature verification.

### 13.2. Origin and RP ID prevent phishing, but must be configured properly

A WebAuthn credential is bound to an RP ID/domain, and the browser puts the origin into client data. The server must verify accurately:
- RP ID is a valid domain for the actual origin;
- `rpIdHash` in authenticator data;
- `origin` scheme/host/port matches the allowlist;
- iframe/`crossOrigin`/`topOrigin` policies if supported.

Use HTTPS in real deployments. `http://localhost` is only a dev exception. Never wildcard all origins to work around reverse-proxy issues, and never assume passkeys protect against XSS on the **real origin** or flawed account recovery.

### 13.3. Passkeys do not exempt authorization or sessions

After a valid assertion, Spring must still verify the account is active and has the right roles, checking access by endpoint/tenant/object. Session fixation, timeouts, logout, and security alerts all still require proper design. Never grant `ROLE_ADMIN` just because a user has a passkey.

### 13.4. Syncing and device attestation

Passkeys can sync across providers. `signCount` is not proof of a single physical machine. If an enterprise requires non-synced hardware keys, design an explicit authenticator/attestation policy while weighing privacy and compatibility; simply setting `userVerification=required` does not yield device-bound credentials.

## 14. Common mistakes

1. **Treating `navigator.credentials.create()` as login:** wrong; it creates a new credential that the server must verify and save to an authorized user.
2. **Treating `navigator.credentials.get()` as public-key creation:** wrong; the public key already came from registration.
3. **Skipping `clientDataJSON.type` checks:** `webauthn.create` and `webauthn.get` responses must go through their respective verifiers.
4. **Generating challenges on the client, reusing challenges, or skipping TTL checks:** leads to replay/state confusion.
5. **Using a client-supplied user ID to link a credential:** vulnerable to account takeover.
6. **Skipping origin/RP ID verification:** weakens phishing resistance.
7. **Trusting `rawId` as proof:** credential ID enables lookup, not proof of the private key.
8. **Skipping assertion signature verification:** fails to prove the credential holder.
9. **Verifying the signature with a public key sent inside the login request:** an attacker can forge a key pair; always use the stored public key.
10. **Requiring attestation certificates for all passkeys:** breaks consumer passkeys; requires an intentional policy.
11. **Assuming `userHandle` is always non-null:** must support missing/null cases and verify binding.
12. **Forcing `signCount` to increment linearly for all passkeys:** incompatible with certain authenticators and synced passkeys.
13. **Using WebAuthn on a public plain HTTP origin:** browsers block it as a non-secure context; `localhost` is the exception.
14. **Disabling CSRF so options POSTs work:** instead, send the proper CSRF token/cookie.
15. **Losing credentials after restart:** caused by using the demo's in-memory store; production needs a persistent repository.
16. **Mixing Spring 6.5 and 7.x dependencies:** follow the version-specific docs.
17. **Returning HTTP 200 immediately when browser `get()` resolves:** insufficient; the RP must verify the assertion before logging in.

## 15. Test matrix for the two ceremonies

| Test | Registration | Authentication | Expected outcome |
|---|---|---|---|
| Valid flow | Logged-in user creates new key | Signs with linked private key | Registration succeeds; login succeeds |
| Stranger tries adding key to Alice | No session/step-up | N/A | Rejected |
| Reusing old challenge | Replay attestation | Replay assertion | Rejected |
| Challenge from another session | Crossed flows | Crossed flows | Rejected |
| Wrong `clientDataJSON.type` | Sends `webauthn.get` | Sends `webauthn.create` | Rejected |
| Disallowed origin | Wrong `origin` | Wrong `origin` | Rejected |
| Wrong RP ID hash | Wrong `rpIdHash` | Wrong `rpIdHash` | Rejected |
| Missing UV flag when policy is required | Invalid | Invalid | Rejected |
| Corrupted CBOR/COSE | Invalid attestation | N/A | Rejected |
| Credential ID already bound to another account | Duplicate/cross-account | N/A | Rejected |
| Unknown credential ID | N/A | Unknown ID | Rejected |
| Tampered signature | N/A | Invalid signature | Rejected |
| `userHandle` mismatches account | N/A | Wrong user binding | Rejected |
| Account disabled | Block adding key | Valid assertion but locked account | Rejected |
| Counter 0 or backed-up key | Save metadata | Does not increment every time | Handled per multi-device risk policy |
| DB/memory wiped after restart | Key gone | Lookup fails | Use persistent store |
| Missing CSRF token | Options/submit blocked | Options/submit blocked | Bypass prevented |
| Passkey login succeeds without business permissions | Unrelated | Valid identity | Authorization still returns 403/404 |

`MockMvc` tests that merely mock `Authentication` do not prove the library verified WebAuthn signatures. You need integration tests with valid fixtures/authenticators, negative cases for challenge/origin/signature, and end-to-end tests in a browser secure context. Re-test whenever changing reverse proxies, domains, browsers, or repositories.

## 16. Production checklist

- [ ] Registration binds credentials to a **server-authenticated** account, with CSRF and risk-based step-up.
- [ ] Every `create`/`get` ceremony generates a fresh CSPRNG challenge, stored per session/flow, with TTL and one-time use.
- [ ] Always verify `webauthn.create` vs. `webauthn.get` accurately.
- [ ] Exact origin, domain-matching RP ID and `rpIdHash`; HTTPS in production.
- [ ] Registration validates attestation/credential data per policy before persisting the public key.
- [ ] Authentication looks up the stored public key and verifies signature, flags, credential ID, and account mapping.
- [ ] Never derive business permissions from client-supplied data; user status and authorization are still enforced.
- [ ] `userHandle` may be null; discoverable/synced passkeys are handled appropriately.
- [ ] Never assume `signCount` always increments; maintain a risk policy for synced passkeys.
- [ ] Persistent credential store, unique constraints, backups, recovery, and revocation work across multiple instances.
- [ ] Protect add/remove passkey pages, log safely, and send new-device notifications.
- [ ] Sessions, logout, reauthentication, and account recovery do not become a weaker backdoor.
- [ ] Java/Spring Security/WebAuthn dependencies belong to one compatible version range.
- [ ] Negative tests for replay, invalid signature, wrong origin/RP ID, registration permissions, and cross-account binding.

## 17. Conclusion

**Registration uses `navigator.credentials.create()` to create and bind a new public key/credential ID to an account; Authentication uses `navigator.credentials.get()` to sign a challenge with the existing private key and prove ability to use that credential.**

Both ceremonies share the need for a challenge, origin, RP ID, and UP/UV policies, yet differ completely in **`attestationObject`** vs. **`authenticatorData`/`signature`**, how the public key is obtained, and the business outcome of **persisting a credential** vs. **creating an authentication session**. You cannot rename endpoints or copy payloads between the two steps to bypass verification.

## 18. References

1. [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): dependencies, WebAuthn configuration, persistence, and the two endpoint pairs.
2. [W3C WebAuthn Level 3 — Registration](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential): creation options, attestation response, and verification procedure.
3. [W3C WebAuthn Level 3 — Authentication](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion): assertion, challenge, signature, origin, and flags.
4. [W3C WebAuthn Level 3 — Security Considerations](https://www.w3.org/TR/webauthn-3/#sctn-security-considerations): RP ID, phishing resistance, attestation, and privacy.
5. [Spring Security 6.5 API — WebAuthnConfigurer](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html): `rpId`, `rpName`, `allowedOrigins`.
6. [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): SecurityContext, Authentication, and session.
7. [FIDO Alliance — Passkeys](https://fidoalliance.org/passkeys/): passkey overview, unlock methods, discoverable/synced credentials.
