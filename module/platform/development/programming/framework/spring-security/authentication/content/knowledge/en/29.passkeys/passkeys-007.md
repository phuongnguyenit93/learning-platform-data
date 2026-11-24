# User presence, user verification, and the meaning of verification policies in Passkeys

## 1. Objectives and scope

Passkeys are based on **WebAuthn/FIDO2**: the web application (Relying Party, abbreviated **RP**) stores a credential's public key; the authenticator holds the private key and creates a signature over the RP's challenge during sign-in. In every response, the authenticator also includes **status flags** so the RP knows whether the operation had **user presence (UP)** and/or **user verification (UV)**.

Two questions that sound similar yet differ fundamentally:

- **User presence (UP):** was there proof of **interaction/intent to use the authenticator**, such as touching a button on a security key?
- **User verification (UV):** did the authenticator perform **local verification of the user**, such as a PIN, biometrics, or a device unlock method accepted by the authenticator?

This lesson clarifies **how to read UP/UV**, WebAuthn's `userVerification` requirement (`required`, `preferred`, `discouraged`), how the RP checks flags **after verifying the signature**, and operational implications in Spring Security. The focus is Spring MVC/Servlet with Spring Security **6.4–6.5 and 7.x**, Java 17+; WebFlux has a different mechanism and cannot reuse Servlet `HttpSecurity` verbatim.

After this lesson, you will be able to:

1. Accurately explain the difference between UP, UV, WebAuthn signatures, and account identification.
2. Recognize the `flags` byte in `authenticatorData`, extract the UP/UV bits, and avoid confusing them with BE/BS.
3. Choose `required`, `preferred`, or `discouraged` policies according to business risk.
4. Distinguish between the preference sent to the browser/authenticator and **conditions the server must enforce**.
5. Understand both **registration (`create`)** and **authentication (`get`)** ceremonies, along with intentional exceptions.
6. Integrate passkeys via `HttpSecurity.webAuthn(...)` and test UP/UV present/absent cases.
7. Never misconstrue `UV=1` as granting `ROLE_ADMIN`, proving legal human identity, or automatically satisfying MFA under every policy.

## 2. Trust model: who verifies what?

In WebAuthn there are at least four participants:

| Participant | Responsibility |
| --- | --- |
| **RP / Spring Security** | Generates challenges, manages options, trusted RP ID, and origins; stores credential public keys; verifies assertions/registrations, authenticates accounts, and grants permissions |
| **Browser / WebAuthn client** | Calls `navigator.credentials.create()` or `.get()`, coordinates with the authenticator, binds origin/RP ID, and sends results back to the RP |
| **Authenticator** | Holds the credential's private key, prompts for local presence/verification per policy, produces signatures and flags |
| **User** | Interacts with the device and proves authorization to use the authenticator under the device's UV rules |

Sign-in diagram:

```text
Browser                         RP / Spring Security             Authenticator
  |                                     |                               |
  | POST /webauthn/authenticate/options |                               |
  |------------------------------------>| generate challenge + req opts |
  |<------------------------------------| rpId, userVerification, ...   |
  | navigator.credentials.get({publicKey})                              |
  |-------------------------------------------------------------------->|
  |                                     |          perform UP and/or UV |
  |                                     |     sign challenge-bound data |
  |<--------------------------------------------------------------------|
  | POST /login/webauthn                |                               |
  |------------------------------------>| verify signature, challenge   |
  |                                     | origin, rpIdHash, UP, UV, ... |
  |                                     | -> Authentication/session     |
  |<------------------------------------| succeed or reject             |
```

**An assertion is trustworthy only after verifying the entire WebAuthn context.** A malicious client can send handcrafted JSON containing `"uv": true`, which proves nothing. UP/UV are meaningful because they live inside `authenticatorData`, which is **covered by the credential's signature** during the authentication ceremony.

WebAuthn prevents phishing by binding credentials to the **RP ID** and verifying **origin**; UP/UV do not replace origin binding, RP ID checks, or signature verification.

## 3. What is User Presence (UP)?

**UP** answers: "Was there an interaction accepted by the authenticator as a signal that the user was **present and intentional** when performing the action?"

Examples:

- The user **touches** the capacitive sensor on a USB/NFC security key.
- The user **confirms** the prompt to use a passkey on the device.
- An authenticator combines unlocking and confirmation into a single user gesture.

UP **does not assert**:
- that the person who touched it is the rightful account owner;
- that a PIN, fingerprint, or Face ID was used;
- that the browser is talking to the real RP if the server skips origin/signature checks;
- that the user holds business permissions inside the application.

In `authenticatorData.flags`, **bit 0** (mask `0x01`) represents **User Present**. `UP=1` means the authenticator ran a presence test; `UP=0` means no such presence test result is present in the response.

Per WebAuthn Level 3, **standard authentication assertion flows require the UP bit to be 1**. Special cases such as background credential-upgrade mechanisms specify different rules, yet they **do not** allow a regular passkey login flow to drop the UP check.

## 4. What is User Verification (UV)?

**UV** answers: "Did the authenticator verify **who is using it** via a local mechanism before permitting credential use?"

Examples:
- Entering an authenticator PIN (such as a FIDO2 security key PIN).
- Device-approved fingerprint/facial recognition verification.
- Unlocking with a device password/PIN, if the device uses that method for UV in the WebAuthn flow.

In `authenticatorData.flags`, **bit 2** (mask `0x04`) represents **User Verified**. `UV=1` asserts the authenticator ran a UV method satisfying device policy for this operation; `UV=0` means UV was not proven for this operation.

Things that **cannot be inferred** from `UV=1`:

- You do not know **specifically** whether fingerprint, PIN, or another method was used without additional data/assurance mechanisms.
- You do not know the person's **legal identity**; UV typically verifies someone authorized to use the **authenticator**, not a passport check.
- You do not know who else might be able to unlock the same device or manage the synced passkey account.
- It is not proof that the user is authorized for business actions like withdrawing funds or changing roles.
- You must not automatically conclude the credential is non-exportable hardware, non-synced, or satisfies a specific assurance level.

**Common confusion:** a touch-only security key can still produce a valid signature with `UP=1` and `UV=0`. An authenticator with PIN/biometrics can return `UP=1`, `UV=1`. A valid signature in both cases **does not imply** equivalent user verification levels.

## 5. UP and UV are not two names for the same action

| Scenario | UP | UV | Interpretation for standard login flows |
| --- | --- | --- | --- |
| Security key requires touch, no PIN required | 1 | 0 | Interaction occurred; **no** UV proof. Acceptable only if the RP allows missing UV |
| Device passkey requires unlock then confirm | 1 | 1 | Both interaction and UV occurred; must still verify signature and all other constraints |
| Authenticator returns data without proving presence | 0 | 0 | Standard authentication ceremony must reject due to missing UP |
| UV bit set while UP bit is clear | 0 | 1 | Must not waive the standard assertion UP requirement just because UV is set |
| No valid assertion/signature | — | — | Do not trust any flags supplied by the request |

The symbols `1` and `0` are just bit values; **you cannot read two bits alone and grant a login session**. The RP must know the registered credential, verify the signature against the public key, and check challenge, origin, `rpIdHash`, expiration/anti-replay, and other rules.

Two questions must remain separate:

1. **Is there a valid private key for this RP?** Check the signature and credential bindings.
2. **To what level was the authenticator's user verified?** Check UP and UV against the server-stored policy.

## 6. Where does `authenticatorData` store flags?

For an authentication assertion, `authenticatorData` is a byte array (at least **37 bytes** in the basic structure):

```text
0                    31  32      33                   36
+----------------------+--------+-----------------------+
| rpIdHash (32 bytes)  | flags  | signCount (4 bytes)   | ...
+----------------------+--------+-----------------------+
                          ^
                          byte index 32
```

Bit layout inside the `flags` byte (bit 0 is the least significant bit):

| Bit | Mask | Name | Primary meaning |
| --- | --- | --- | --- |
| 0 | `0x01` | **UP** | User Present |
| 1 | `0x02` | RFU1 | Reserved, do not interpret yourself |
| 2 | `0x04` | **UV** | User Verified |
| 3 | `0x08` | **BE** | Backup Eligible: credential may be backed up/synced |
| 4 | `0x10` | **BS** | Backup State: credential is currently backed up |
| 5 | `0x20` | RFU2 | Reserved |
| 6 | `0x40` | **AT** | Attested credential data included, normally present at registration |
| 7 | `0x80` | **ED** | Extension data included |

How to check:

```text
UP = (flags & 0x01) != 0
UV = (flags & 0x04) != 0
BE = (flags & 0x08) != 0
BS = (flags & 0x10) != 0
```

Examples:
- `flags=0x01`: UP=1, UV=0, BE=0, BS=0.
- `flags=0x05`: UP=1, UV=1, BE=0, BS=0.
- `flags=0x1D`: UP=1, UV=1, BE=1, BS=1.
- `flags=0x00`: UP=0, UV=0, fails standard login policy.

**BE/BS differ from UV:** a passkey can sync across devices while still requiring UV every time. A non-synced hardware passkey may also skip UV when tapped without a PIN. `BS=1` is not proof that "Face ID was used," and `UV=1` does not reveal whether the passkey is synced.

Under credential state rules, `BS=1` requires the credential to be backup eligible (`BE=1`). Do not invent your own backup-state interpretation while skipping spec validation.

## 7. Runnable Java 17+ program: reading flags and comparing policies

The snippet below **only** demonstrates flag bit extraction and UP/UV boolean logic. It **does not** verify signatures, compare challenges, and **must never be used as a production WebAuthn validator**.

Create `WebAuthnFlagsDemo.java`:

```java
import java.util.Locale;

public class WebAuthnFlagsDemo {
    private static final int UP = 0x01;
    private static final int UV = 0x04;
    private static final int BE = 0x08;
    private static final int BS = 0x10;

    private static boolean has(int flags, int mask) {
        return (flags & mask) != 0;
    }

    // Illustrative logic after WebAuthn signature/context have been verified.
    private static boolean allowed(int flags, boolean requireUv) {
        if (!has(flags, UP)) {
            return false;
        }
        return !requireUv || has(flags, UV);
    }

    public static void main(String[] args) {
        int[] samples = { 0x00, 0x01, 0x05, 0x1D };

        for (int flags : samples) {
            System.out.printf(
                Locale.ROOT,
                "flags=0x%02X UP=%s UV=%s BE=%s BS=%s "
                    + "required=%s preferred=%s%n",
                flags,
                has(flags, UP),
                has(flags, UV),
                has(flags, BE),
                has(flags, BS),
                allowed(flags, true),
                allowed(flags, false)
            );
        }
    }
}
```

Run:

```bash
javac WebAuthnFlagsDemo.java
java WebAuthnFlagsDemo
```

**Exact stdout:**

```text
flags=0x00 UP=false UV=false BE=false BS=false required=false preferred=false
flags=0x01 UP=true UV=false BE=false BS=false required=false preferred=true
flags=0x05 UP=true UV=true BE=false BS=false required=true preferred=true
flags=0x1D UP=true UV=true BE=true BS=true required=true preferred=true
```

Explanation:
- `requireUv=true` passes only when **UP=1 and UV=1**.
- `requireUv=false` still requires UP=1, yet does **not** mandate UV.
- The `preferred` column illustrates the **acceptance condition** when the RP does not mandate UV, not proof that browsers always choose UV.
- `0x1D` carries both UP/UV and backup flags; do **not** conclude UV is weaker simply because a credential is synced.
- The example reads a hypothetical integer representing `flags`. In a real WebAuthn verifier, flags must come from **signature-protected `authenticatorData`**; never use a query param `flags` or client-supplied JSON field to authorize access.

Self-check: changing `0x05` to `0x01` causes the `required` policy to reject; a policy not requiring UV may accept **after all other WebAuthn checks**.

## 8. `required`, `preferred`, `discouraged`: the most important policy

In the WebAuthn API, the RP sends `userVerification` when invoking:

- `navigator.credentials.create({ publicKey: ... })` for registration, inside `authenticatorSelection.userVerification`.
- `navigator.credentials.get({ publicKey: ... })` for authentication, inside `userVerification`.

`UserVerificationRequirement` has three values:

| Value | RP's intent | For assertions lacking UV |
| --- | --- | --- |
| **`"required"`** | Mandate that the authenticator perform UV | **Reject**; if UV cannot be performed, the browser/authenticator typically fails |
| **`"preferred"`** | Prefer UV when possible, prioritizing UX/compatibility | Do not necessarily reject solely because `UV=0` |
| **`"discouraged"`** | Do not require/prefer triggering UV when avoidable | Do not reject `UV=0` by default; some devices may still perform UV |

**Note:** `discouraged` is **not** a command "forbidding the authenticator from verifying the user." A device may still perform UV under its own policy, and when valid proof exists, the UV flag may still be 1.

### When to choose `required`

Consider using it for:
- **Passwordless** sign-in requiring both credential possession and local verification.
- Step-up authentication before sensitive actions when policy requires UV.
- Passkey registration or changes when the organization requires the device to verify the acting user.
- High-risk accounts where UP-only fails policy requirements.

UX risk: authenticators lacking UV support, unset PINs, biometric failures, or locked UV can block users from signing in. Maintain secure recovery rather than silently weakening the policy.

### When to choose `preferred`

Consider when:
- The product must support a broad mix of authenticators, including touch-only security keys.
- Another authentication factor exists with an explicit risk-based design.
- Migrating toward passkeys without treating every UV-incapable device as an error.

**Warning:** `preferred` does not guarantee every authentication includes UV. If the app advertises "login only succeeds with PIN or biometrics" while accepting `UV=0`, the claim and the policy contradict each other.

### When to choose `discouraged`

Use only when there is a genuine compatibility/UX design reason and UV is **not needed** for that ceremony. Never choose `discouraged` for high-risk passwordless sign-in merely to suppress prompts.

### Difference between "sending a requirement" and "verifying the outcome"

A serious security flaw is merely sending:

```json
{
  "userVerification": "required"
}
```

to the browser and **trusting** the browser enforced it. The RP must remember **the server-configured policy** and verify the **actual UV bit** when processing the assertion. If `UV=0`, whether the client showed a PIN prompt cannot substitute for post-authentication verification.

With `"preferred"`, even though a valid WebAuthn assertion with `UV=0` may be accepted, the app should record the session's **assurance level** explicitly—never treat it as UV proof for a transaction requiring step-up.

## 9. Registration and authentication are two independent ceremonies

### 9.1. Registration (`navigator.credentials.create`)

The RP requests creation of a new credential for an account:

```json
{
  "rp": { "id": "example.org", "name": "Example" },
  "user": {
    "id": "<base64url-opaque-user-handle>",
    "name": "linh@example.org",
    "displayName": "Linh"
  },
  "challenge": "<fresh-base64url-random>",
  "pubKeyCredParams": [
    { "type": "public-key", "alg": -7 }
  ],
  "authenticatorSelection": {
    "residentKey": "preferred",
    "userVerification": "required"
  },
  "attestation": "none"
}
```

This is a **JSON sketch**, not a sufficient request to create a passkey without a real challenge/user handle. The browser receives `PublicKeyCredentialCreationOptions`, converts binary fields from base64url into byte arrays, and calls `.create()`.

Server flow:
1. Verify the account is **authorized to register a credential** and is authenticated/re-authenticated per policy.
2. Generate a fresh challenge and store state with the session or transaction.
3. Verify response type `webauthn.create`, challenge, origin, RP ID hash, attestation/credential public key data, UP, and UV **per the registration policy**.
4. Save credential ID, public key, user handle, metadata, and meaningful flags; bind to the exact account.
5. Never let the browser specify another account ID in the response to hijack someone else's account.

In particular, **userVerification at registration** does not automatically enforce itself for **all future authentications**. If login requires UV, configure and enforce a separate policy at the `get` step.

### 9.2. Authentication (`navigator.credentials.get`)

The RP issues options to prove authority to use a registered credential:

```json
{
  "challenge": "<fresh-base64url-random>",
  "rpId": "example.org",
  "timeout": 300000,
  "allowCredentials": [],
  "userVerification": "required"
}
```

`allowCredentials: []` can be used in discoverable credential/passkey login; depending on the flow, the RP may send specific credential IDs when the username is already known. `timeout` is only a client-side execution hint, not a substitute for server-side challenge TTL.

The client receives options from the server and calls:

```javascript
// Assume publicKeyOptions was received from the RP and
// challenge/credential ID fields were converted to Uint8Array in WebAuthn format.
const assertion = await navigator.credentials.get({
  publicKey: publicKeyOptions
});
```

This is a **browser snippet**, not a complete JS file; it requires an HTTPS secure context (with appropriate local dev exceptions), server endpoints, and a base64url decoder. When sending results back to Spring Security, binary fields must be properly encoded.

An authentication response contains:
- `id`/`rawId`: credential ID.
- `response.clientDataJSON`: `type`, `challenge`, `origin`, `crossOrigin`, etc.
- `response.authenticatorData`: `rpIdHash`, flags, and `signCount`.
- `response.signature`: signature created by the credential's private key.
- `response.userHandle`: optional depending on credential type/flow.

The RP must verify the response against the **stored request**, never reading a new `userVerification` field from the browser's POST request to decide acceptance.

## 10. Server-side assertion verification order

You can use this checklist when processing a WebAuthn authentication assertion:

1. **Format and type**: decode binary safely, reject malformed structure/lengths, and ensure `clientDataJSON.type` is `"webauthn.get"`.
2. **Challenge**: the challenge in `clientDataJSON` must match the **issued** challenge for the pending transaction, unexpired and unused.
3. **Origin**: must match a trusted origin (scheme/host/port); `https://app.example.org` is not `https://evil.example.org`.
4. **RP ID hash**: SHA-256 of the expected RP ID must match the first 32 bytes of `authenticatorData`; never accept a client-supplied RP ID without verification.
5. **Credential**: look up the registered credential ID and public key, revocation status, and exact user/account mapping; verify `userHandle` per flow rules.
6. **Signature**: verify `signature` with the stored public key over `authenticatorData || SHA256(clientDataJSON)` using the WebAuthn algorithm.
7. **UP**: for standard authentication assertions, `flags & 0x01` must be set.
8. **UV**: if server policy requires user verification, `flags & 0x04` must be set; otherwise authentication fails.
9. **Sign count/extensions**: handle counters and clone risk per spec, credential characteristics, and policy; never allow invalid extension data to override policy.
10. **Account/authorization**: confirm the account is still enabled/allowed to sign in, then create `Authentication` and session per policy; business permissions never arise automatically from `UP/UV`.

This illustrative logical order may vary across verifier libraries. What matters is **never** decoupling UP/UV checks from signature and challenge verification.

### A bad counterexample

```java
// WRONG: a browser-supplied request parameter is not WebAuthn proof.
boolean verified = "true".equals(request.getParameter("uv"));
if (verified) {
    // Never grant a session or role based solely on this condition.
}
```

Never build a WebAuthn signature verifier with `if` statements over JSON fields. Use Spring Security/WebAuthn4J's standards-compliant verifier and test all failure paths.

## 11. Spring Security: enabling Passkey login by version

Spring Security added WebAuthn/passkey support in **6.4**. Both 6.5 and 7.x docs use `HttpSecurity.webAuthn(...)` for Servlet, yet **required dependencies differ**.

| Library line | Appropriate starting point |
| --- | --- |
| Spring Security before 6.4 | No built-in `webAuthn(...)` DSL matching this example; use a compatible integration or upgrade |
| Spring Security **6.4–6.5**, corresponding Boot 3.x | Uses Spring Security WebAuthn in `spring-security-web`, plus the **WebAuthn4J core** dependency required by that version's docs |
| Spring Security **7.x** | Per 7.x docs, add the `spring-security-webauthn` module matching the Security modules' version |
| Spring WebFlux | Do not attach Servlet `HttpSecurity`/`SecurityFilterChain` to `SecurityWebFilterChain`; check reactive support/integration per version |

### 11.1. Gradle dependencies for Spring Security 6.5

In a Spring Boot **3.x** project with Gradle plugins and dependency management compatible with Spring Security 6.5:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'com.webauthn4j:webauthn4j-core:0.29.7.RELEASE'
}
```

`0.29.7.RELEASE` is the WebAuthn4J core version listed in Spring Security **6.5** docs; when using another Spring Security version, check compatibility requirements rather than forcing old JARs onto newer releases.

For **Spring Security 7.x**, the docs require adding:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

The line above is an **additional dependency** for a Spring MVC app that already has version-aligned Web/Security dependencies. Never mix `spring-security-webauthn:7.x` with Spring Security 6.x modules.

### 11.2. Minimal Servlet configuration

File `src/main/java/example/passkey/PasskeySecurityConfig.java`:

```java
package example.passkey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class PasskeySecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("example.org")
                .allowedOrigins("https://example.org")
            );

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails demo = User.withUsername("linh@example.org")
            .password("{noop}demo-password-not-for-production")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(demo);
    }
}
```

With `.formLogin(withDefaults())`, the demo lets a password-logged-in user **register** a passkey first and then use it for subsequent logins. The `{noop}` password is completely **unsuitable for production**; use a strong `PasswordEncoder` and a real account repository in real apps.

`rpId` must be consistent with a domain owned by the RP (e.g., `example.org`); `allowedOrigins` is the list of genuinely trusted origins. Never use arbitrary wildcards or public `localhost` outside test environments. To run a real demo, you need a matching HTTPS host, a WebAuthn/passkey-capable browser, credential persistence, and working CSRF/sessions.

**Core point of this lesson:** the configuration above **enables WebAuthn**, without yet guaranteeing every assertion requires `UV=1`. Per Spring Security 6.5 docs, sample authentication options return:

```json
{
  "rpId": "example.localhost",
  "userVerification": "preferred",
  "allowCredentials": []
}
```

`"preferred"` can yield a valid authentication with `UV=0`. Therefore, for production deployments needing UV, **check the actual request-options/verification configuration** of your exact Spring Security version and design the server-side policy; never assume `.webAuthn(...)` always defaults to `"required"`.

### 11.3. Common HTTP endpoints

| Endpoint | Purpose | Notes |
| --- | --- | --- |
| `POST /webauthn/register/options` | Request options for registration | Requires authenticated user and valid CSRF per guide |
| `POST /webauthn/register` | Submit attestation/credential registration | Verifies and stores public key/credential under the right account |
| `POST /webauthn/authenticate/options` | Fetch options/challenge for authentication | Creates request state, requires CSRF under default config |
| `POST /login/webauthn` | Submit assertion to sign in | Verifies `webauthn.get`, signature, challenge, origin, flags |

Default endpoints can be customized depending on version/config. In production, store `challenge` in a session or shared repository suited to multi-node setups and consume/delete it strictly once. Never disable CSRF unconditionally just because requests carry JSON.

### 11.4. Request options example is not the verification result

Producing the JSON response:

```json
{
  "challenge": "base64url-challenge-from-server",
  "rpId": "example.org",
  "userVerification": "required"
}
```

is only the **request issuance step**. The RP must also enforce `UV=1` when checking the assertion. Do not just mutate the field in the browser:

```javascript
publicKeyOptions.userVerification = "required";
```

and think the server raised assurance; the browser can be tampered with. RP policy must be configured and enforced by the verifier on the server. When customizing request-options providers, repositories, or verifiers, use the API of your **exact minor version** and ensure stored requirements are verified when assertions arrive. Never invent a method like `.webAuthn(w -> w.userVerification(...))` unless your version's configurer Javadoc actually defines it.

## 12. Designing policy by use case

**Verification policy** is not just a string in JSON. It is the set of server conditions deciding **whether login is permitted**, **what actions are allowed**, and **how soon re-verification is needed**.

| Scenario | Suggested UV policy | Rationale and notes |
| --- | --- | --- |
| **Passwordless** passkey login for sensitive internal systems | `required` | Must verify the person using the authenticator, not merely a key tap |
| Migrating from passwords to passkeys, prioritizing legacy device support | `preferred` if risk policy permits | Must accept that `UV=0` sessions occur and not label them "locally verified" |
| Password + UP-only security key login as an additional factor | UV may not be mandatory on **that key tap** | Must ensure the password factor was checked and proper MFA rules hold; prevent factor bypass |
| Updating payment info, API keys, adding/removing passkeys | `required` with a **fresh challenge/reauth** if step-up is designed | One old login should not automatically suffice for high-risk actions |
| Account recovery when passkeys are lost | Separately controlled recovery | Never silently set `discouraged` across all logins as a workaround |
| Kiosk/shared workstation | Carefully assess device/ownership; may disallow synced passkeys per policy | UV on a shared device does not prove legal identity or stop others who know the PIN |

These choices are architectural guidance, **not** rigid mandates for every product. Always weigh your threat model, organizational policies, and assurance requirements; sometimes it is better to use an IdP supporting passkeys/MFA and have the application consume bound authentication results from the IdP.

### `preferred` is not "`required` with fallback"

A system that sends `"preferred"`, accepts `UV=0`, and grants **the exact same privileges** as `UV=1` has effectively chosen a UP-only-tolerant policy. It does not silently achieve `required`-level security.

Two sound designs:
- **Single login tier:** issue a session only when the assertion satisfies UV per policy; otherwise fail or trigger a secure fallback.
- **Tiered assurance:** server grants a restricted session for UP-only proofs and requires extra verification/step-up before sensitive features.

Mandatory rule: the server **records the verification level actually checked**, never trusting an `uv` flag from a form or assuming every passkey session has UV.

## 13. Registration policy and authentication policy can differ

An operational mistake is configuring `"userVerification": "required"` during **registration** while overlooking that **login** may still send `"preferred"`.

Verify them separately:

| Ceremony | State to retain | Policy to verify |
| --- | --- | --- |
| `create` | Challenge, account ID/user handle, RP ID, origin, credential options | UP/UV per registration requirement, new public key/credential, attestation policy |
| `get` | Challenge, relying party, allowed credential(s), session, and expected UV | Signature with stored public key, UP=1, UV per **authentication** requirement |
| Step-up `get` | Fresh challenge bound to account, action/risk context, and TTL | `UV=1` if policy requires, proof of fresh auth, and safe assurance upgrade |

A credential registered with `UV=1` **does not** prove that **every future assertion** has `UV=1`. It must be checked **every time**. Likewise, `UV=0` on a single `get` **does not** mean the credential's private key changed; it merely reflects the user verification level proven in that specific ceremony.

For passkey-only login, a `required` policy must be enforced before establishing `Authentication`, rather than only inside a `/sensitive` controller after a full session has already been granted.

## 14. WebAuthn, authentication factors, and Spring Security authorization

WebAuthn proves credential usage and its associated conditions; Spring Security decides the account and authorities.

```text
Valid WebAuthn assertion
      |
      +--> Verify public key + challenge + origin + rpIdHash
      |
      +--> Verify UP=1
      |
      +--> Verify UV per server policy
      |
      v
Authenticated principal (account)
      |
      v
GrantedAuthority, hasRole/hasAuthority, @PreAuthorize
```

- `ROLE_ADMIN` is **never** granted simply because `UV=1`.
- UP/UV **never** replace role mapping from the account repository, groups, or policy engine.
- A single account may have multiple passkeys with different authenticators/capabilities; evaluate based on the **current assertion**, rather than fixed assumptions based solely on passkey type in the profile.
- If distinct assurance tiers are needed, design server-protected session/`Authentication` state and test step-up; never accept a `role=UV` from a client-controlled request.

### Are passkeys automatically MFA?

A **user-verifying** cryptographic authenticator can support multi-factor assurance when meeting relevant standards and policies. However, stating "having a passkey always means MFA" is inaccurate:

- With `UV=0`, you may only have proof of private-key possession and user presence.
- With `UV=1`, the authenticator verified the user locally; actual assurance still depends on the authenticator, key management, syncing, enrollment, recovery, and applicable standards.
- An organization's MFA requirement may demand additional signals or constraints; do not assume every device and every UV mechanism are equivalent.

Never equate "Face ID popped up" with "the RP definitely received `UV=1`." UI is user experience; **signed flags and server verification** are the technical data you must check.

## 15. Synced passkeys, BE/BS, and device management policies

Passkeys can be:
- **Single-device credentials:** keys bound to one authenticator and not synced.
- **Multi-device/synced credentials:** keys that can be backed up and synced across an ecosystem or passkey manager.

`BE` and `BS` give the RP signals about backup eligibility/state. However:

1. `BE=1` does not tell you whether the user verified via PIN/biometric **right now**; that is `UV`'s role.
2. `BS=1` does not prove how many copies or devices currently hold the credential.
3. `BE=0` is insufficient to claim strong hardware certificates, specific compliance tiers, or compromise immunity.
4. `signCount` may be 0 or non-monotonic on synced credentials; do not use it as a sole check to declare cloning.
5. If an organization requires managed devices, authenticator provenance, or hardware attestation, it needs a dedicated **attestation/device policy**, not an inference from UV.

An app can require `UV=1` for every passkey while accepting both synced passkeys and security keys, provided the verification policy fits. Conversely, blocking multi-device credentials for internal requirements is a **device governance decision**, not the meaning of UV.

## 16. Policy-matrix testing

Most UP/UV bugs show up when testing only the happy path on a biometric-enabled phone.

### 16.1. Required test table

| Test | Expectation |
| --- | --- |
| Assertion with valid signature/challenge/origin, UP=1, UV=1; `required` policy | **Accept** if account and all other constraints pass |
| Same, UP=1, UV=0; `required` policy | **Reject**, no authenticated session created |
| Same, UP=1, UV=0; `preferred` policy | Acceptable per policy, yet must not be tagged with UV assurance |
| Valid signature but UP=0, UV=1; standard login | **Reject** due to missing user presence |
| UP=1, UV=1, invalid signature | **Reject** |
| UP=1, UV=1, mismatched challenge or replay | **Reject** |
| UP=1, UV=1, wrong origin/RP ID | **Reject** |
| Assertion passes WebAuthn yet account is locked | **Reject** per account policy |
| Valid assertion, account lacks `ROLE_ADMIN` | **Reject** on admin endpoint (authorization) |
| Registration uses `required`, login uses `preferred` | Verify as **two separate policies**; do not assume login has UV |
| Client alters options from `preferred` to `required` or vice versa | Server enforces its **stored policy**, ignoring client-modified options |
| UP-only session requests sensitive action | Require proper step-up; do not authorize from stale session alone |
| Session/challenge lost across cluster | Login fails cleanly with sensible retry; never disable challenge checks |
| Credential deleted/revoked | Login fails even with valid signature from old private key |
| BE/BS flags change against spec rules | Apply credential state validation and audit; never ignore |

### 16.2. Java 17 unit tests for flag decisions

In this example, `WebAuthnFlagsDemo.allowed` is private for `main`. To unit test independently, extract a utility with a public method and call it from JUnit. For **pure JDK** Java code, `main` in section 7 suffices to test basic bitmask cases via `javac`/`java`.

**Limitations of flag tests:** evaluating boolean logic on `0x01` or `0x05` **does not verify WebAuthn**. Proper integration tests must invoke Spring Security/WebAuthn4J's verifier or a test authenticator with a registered public key and valid signatures, plus negative cases (signature/challenge/origin/UV) that the real verifier rejects.

### 16.3. Verifying Spring Security configuration over HTTP

With the default WebAuthn flow in Spring Security 6.5:

```http
POST /webauthn/authenticate/options
X-CSRF-TOKEN: <valid-session-csrf-token>
```

Sample response (abbreviated):

```json
{
  "challenge": "<server-generated-base64url>",
  "rpId": "example.org",
  "allowCredentials": [],
  "userVerification": "preferred"
}
```

Once the policy is tightened to `required` per server design, tests must verify **both**:
1. Server options actually state `userVerification: "required"` for UV-required transactions.
2. An assertion lacking UV—even with a valid signature—**is still rejected by the verifier** with no session issued.

Checking only the options JSON without testing the `UV=0` failure path does not protect the actual policy.

### 16.4. Do not overlook infrastructure pitfalls

- Differing RP ID and HTTPS origin behind a reverse proxy: configure exact public hosts/allowed origins.
- Session/challenge storage lost when a load balancer routes requests across instances: verify sticky/distributed sessions and TTLs.
- CSRF blocked because UI calls options POST incorrectly: pass a valid CSRF token instead of disabling CSRF globally.
- Browser lacks secure context or authenticator lacks PIN/UV: may hit `NotAllowedError`/other failures; handle UX and recovery clearly.
- Users with multiple credentials/devices: map credential ID/user handle to the right account, never relying on client-supplied emails.
- Adding/deleting credentials without reauth: can create an account takeover path even when primary WebAuthn login is strong.

## 17. Anti-patterns to avoid

**Mistake 1: `UP=1` means biometric authentication.**

False: tapping a security key may prove only UP. If a transaction needs UV, check `UV=1`.

**Mistake 2: With a valid signature, UP/UV are unnecessary.**

The signature proves the credential private key was used. Requiring user intent and local verification are **additional** conditions.

**Mistake 3: Sending `userVerification:"required"` without checking UV on the server.**

That is only a hint to the client/authenticator. An attacker can modify HTTP client code; the server must enforce based on signed `authenticatorData` and RP-stored policy.

**Mistake 4: `preferred` means biometrics are always used if the phone supports them.**

No such guarantee exists. "Preferred" permits missing UV under policy.

**Mistake 5: Seeing `UV=1` and skipping signature or challenge checks.**

A forged JSON response can still contain bytes with UV=1. Flags are trustworthy only after the verifier checks signature, challenge, origin, RP ID, and credential.

**Mistake 6: Seeing `UV=1` and granting `ROLE_ADMIN`.**

UV reflects **how authentication was performed**, not **entitlements**; roles must come from a trusted authorization source.

**Mistake 7: Registering a passkey with UV means every subsequent login defaults to UV.**

UP/UV are reported **per ceremony**. A login requiring UV must verify it on that login assertion.

**Mistake 8: Without UV it is always insecure and the credential must be deleted.**

A UP-only credential can fit a password + security key flow or low-risk profile; decide based on real policy. Never silently upgrade its assurance level.

**Mistake 9: Silently allowing UV bypass when supporting legacy devices.**

Fallback lowers assurance. If allowed at all, enforce explicit risk controls, auditing, session scoping, and dedicated recovery.

**Mistake 10: Mutating flag bytes in JSON tests and calling it a WebAuthn integration test.**

Altering bytes invalidates the signature; a test that merely sends broken payloads does not prove the verifier handles **valid signature with `UV=0`**. Use a test harness/authenticator producing valid responses with the desired flags.

## 18. Policy design process before deployment

A development team can settle these questions before choosing `required` vs. `preferred`:

1. **Authentication goal?** Passwordless login, password + security key, device enrollment, or transaction reauth?
2. **Sensitivity level?** Standard accounts, personal data, financial, infrastructure admin?
3. **Is UV required every time?** If not, which features are accessible in a UP-only session?
4. **Supported devices?** Platform authenticators, roaming hardware keys, synced passkeys, users without PIN/biometrics?
5. **How do enrollment and recovery work?** Who can add/remove passkeys, and how are lost devices, locked devices, or phone/email changes handled?
6. **Where does the server enforce policy?** Request options, challenge/policy storage, assertion verifier, session/step-up, and authorization?
7. **Is a dedicated device/attestation policy needed?** UV/BE/BS cannot answer device-trust questions.
8. **How are negative cases tested?** Including `UP=0`, `UV=0`, bad signatures, challenge replay, wrong origin, and revoked accounts.
9. **Logging and observability?** Record verification tier/error types cleanly without storing sensitive raw assertions/credential material.
10. **Framework version?** Match the exact WebAuthn dependencies and APIs of 6.4, 6.5, or 7.x; never copy configs blindly across major versions.

For **passwordless passkeys** protecting sensitive data, the standard choice is **mandating UV** and verifying the flag on the server. If `"preferred"` is chosen for accessibility, explicitly document where UV-less sessions are accepted and where step-up is required.

## 19. Self-check questions

**Question 1:** The user taps a security key and we receive `UP=1, UV=0`. Can we say "a PIN was entered"?

No. UP indicates a presence test; UV is the proof of local verification. If the policy is `required`, assertions lacking UV must be rejected.

**Question 2:** The browser returned `"userVerification":"required"` in options and the UI displayed Face ID. Is that enough to grant a session?

No. The RP must verify the WebAuthn assertion using public key, challenge, origin, RP ID hash, UP, and UV **over signed data**, never relying on UI.

**Question 3:** Does a synced passkey with `BE=1,BS=1` always have `UV=1`?

No. Backup eligibility/state and user verification are separate dimensions.

**Question 4:** Why is `userVerification:"preferred"` not equivalent to `required`?

Because `preferred` can allow a ceremony to complete without the UV bit set. `required` must reject that case.

**Question 5:** A user registers a credential with `UV=1`, then logs in with the same credential and `UV=0`. Can we rely on registration data to treat the login as UV-verified?

No. The UV level of the **current authentication** must be verified independently.

**Question 6:** Can we grant `hasRole("ADMIN")` solely from `UV=1`?

No. UV proves a property of the authentication event; roles are an authorization decision from separate account/entitlement policies.

**Question 7:** What if an assertion has `UV=1` but the wrong `origin`?

It must be **rejected**. UP/UV cannot compensate for missing checks on origin, RP ID, signature, or challenge.

## 20. Core summary

- **UP = interaction/presence test occurred**, not verification of the owner's identity.
- **UV = authenticator verified the user locally**, without specifying the method and without granting privileges.
- `required` means the server **must reject** assertions lacking UV; `preferred` and `discouraged` **do not mandate** UV, though standard login flows still require UP.
- Flags live at byte 32 of `authenticatorData` and are protected by the **WebAuthn signature**. Never trust self-reported browser flags.
- **Registration and authentication have separate UV policies**; check outcomes on every ceremony.
- Spring Security supports WebAuthn/passkeys since **6.4**; Servlet config uses `.webAuthn(...)`, while dependencies and customization APIs vary between 6.5 and 7.x.
- Valid authentication always requires **signature, challenge, origin, RP ID, credential mapping, UP/UV policy, and account status**; business permissions are checked after authentication.
- To raise assurance for sensitive transactions, use step-up with a fresh challenge and real UV verification—never just edit JSON options or rely on an old login session.

## 21. Standards and API references

- W3C Web Authentication Level 3, Recommendation 2026-08-25: https://www.w3.org/TR/webauthn-3/
- W3C WebAuthn Level 3: authenticator data flags and verification steps (see Authenticator Data and Verifying an Authentication Assertion): https://www.w3.org/TR/webauthn-3/
- Spring Security 6.5 — Passkeys (Servlet), dependencies and endpoints: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html
- Spring Security 7.0 — Passkeys (Servlet), `spring-security-webauthn` module: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Spring Security Javadoc — `UserVerificationRequirement` (`REQUIRED`, `PREFERRED`, `DISCOURAGED`): https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/webauthn/api/UserVerificationRequirement.html
- Spring Security Javadoc — `PublicKeyCredentialRequestOptions`: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/web/webauthn/api/PublicKeyCredentialRequestOptions.html
- WebAuthn4J reference — user presence/user verification verification parameters: https://webauthn4j.github.io/webauthn4j/en/
- NIST SP 800-63B-4 — Authentication and Authenticator Management, WebAuthn flags and assurance: https://pages.nist.gov/800-63-4/sp800-63b.html
