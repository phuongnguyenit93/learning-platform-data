# Passkeys: Authenticator, Relying Party, and public-key credentials

## 1. Objectives and big picture

A **passkey** is a type of **discoverable WebAuthn public-key credential** used to sign in without sending a shared secret password to the application. Each credential is bound to a specific **Relying Party (RP)** and relies on a cryptographic key pair: the **private key** is managed by the authenticator/provider and the **public key** is stored by the RP to verify signatures when the user signs in.

Three core concepts in this topic:

- **Authenticator:** the component that creates and manages credentials, verifies user interaction, and signs challenges with the private key. It can be built into a phone/computer or be a separate security key.
- **Relying Party:** the application/service that trusts the WebAuthn verification result. The RP generates challenges, declares the RP ID and allowed origins, stores the public key with the credential ID, verifies assertions, and issues a login session.
- **Public-key credential:** a record identifying a key pair and related metadata. **The credential private key is never sent to the RP**; the RP stores the public key along with the credential ID for verification.

After this lesson, you will be able to:

1. Distinguish **RP**, **browser/WebAuthn client**, **authenticator**, and **user** in a single diagram.
2. Explain how credentials are registered using `navigator.credentials.create()` and signed in using `navigator.credentials.get()`.
3. Differentiate **credential ID**, **user handle**, **public key**, **private key**, **RP ID**, **origin**, **challenge**, **UP/UV**, **attestation**, and **assertion**.
4. Know what data the RP must store and what conditions **must be verified on the server**.
5. Understand how to enable passkeys/WebAuthn in Spring Security 6.5 for Java 17+ applications and the limitations when moving to production.

**Scope:** this lesson focuses on the WebAuthn/FIDO2 model in a **Spring Security Servlet web application**. Passkeys are an identity verification mechanism; they **do not replace authorization**, do not automatically issue OAuth access tokens, and do not automatically handle all account recovery flows.

## 2. Four entities in a single passkey interaction

~~~text
                    User
             (selects account,
               PIN/biometric)
                     │
                     ▼
      ┌─────────────────────────────┐
      │ Authenticator               │
      │ - creates key pair          │
      │ - holds/manages private key │
      │ - confirms UP/UV            │
      │ - signs WebAuthn assertion  │
      └──────────────▲──────────────┘
                     │  communicates via
                     │  platform/CTAP
                     ▼
      ┌─────────────────────────────┐
      │ Browser / WebAuthn Client   │
      │ navigator.credentials       │
      │ - checks web context        │
      │ - coordinates create/get    │
      │ - provides clientDataJSON   │
      └──────────────▲──────────────┘
                     │ HTTPS
                     ▼
      ┌─────────────────────────────┐
      │ Relying Party (RP)          │
      │ Spring Security / Backend   │
      │ - issues challenge          │
      │ - checks origin and RP ID   │
      │ - stores credential ID +    │
      │   public key + account      │
      │ - verifies assertion sig    │
      │ - creates session, authz    │
      └─────────────────────────────┘
~~~

**The RP** is neither the browser nor the authenticator. The browser is merely the intermediary between the web RP and the authenticator. The browser/WebAuthn client knows the origin of the page calling the API, presents the passkey selection UI, and forwards data over the appropriate interface. The authenticator performs operations with the key; the RP verifies the result on the server.

### 2.1. Responsibility table

| Component | What does it hold? | What does it do? | What should it NOT do? |
| --- | --- | --- | --- |
| User | Device, passkey provider, PIN/biometric when applicable | Selects account/credential and authorizes the operation | Send PIN or biometric data to the website |
| WebAuthn client (browser) | Origin, `navigator.credentials` API | Calls authenticator, creates client data, checks context | Self-assert that the user is authenticated on behalf of the server |
| Authenticator | Private key or key access via credential provider | Generates keys, signs, reports UP/UV flags | Send the private key to the RP |
| Relying Party (server) | Challenge, RP policy, credential ID, public key, and account mapping | Verifies signature and constraints; creates local session | Trust `credential.id` or username sent by client without verification |

An **Authenticator** can be a platform authenticator (Windows Hello, Android/iOS devices, passkey provider ecosystems) or a roaming authenticator (USB/NFC/Bluetooth security keys). **CTAP** is the protocol between the client and a roaming authenticator; **WebAuthn** is the web API/protocol between the RP, browser, and authenticator.

## 3. What is a public-key credential?

When creating a WebAuthn credential, the authenticator creates or manages cryptographic key material matching an algorithm supported by both the RP and the authenticator. In a typical digital signature model:

- **Credential private key:** used only for signing and protected by the authenticator/provider. The RP does not have the private key.
- **Credential public key:** exported in the registration response and stored on the RP server.
- **Credential ID:** byte sequence identifier provided by the authenticator, helping the RP look up the right credential record during login; usually serialized as Base64URL.
- **User handle:** opaque byte sequence generated by the RP, stable for an account; used to link accounts in discoverable credential flows. Should not default to email or username.
- **RP ID:** domain name to bind the credential, e.g., `login.example.com` or `example.com` per policy.
- **Metadata:** COSE algorithm, creation/last-used timestamps, display label, transports, AAGUID, or backup/counter state when needed.

An RP record typically resembles this **data model**:

~~~text
account_id                42
user_handle               <opaque bytes, unique, stable>
credential_id             <opaque bytes, unique for RP>
credential_public_key     <COSE public key bytes>
public_key_algorithm      -7  (ES256, for example)
signature_counter         7
backup_eligible           true/false (when available)
backup_state              true/false (when available)
label                     "Personal Laptop"
created_at                ...
last_used_at              ...
status                    active / revoked
~~~

The fields above illustrate the design and are **not a mandatory default schema** of Spring Security. Depending on the WebAuthn library, you may also need other formats/attributes. For synced passkeys, handling `signCount` or backup state must follow authenticator rules; do not assume every device uses a strictly monotonically increasing counter.

**Never store private keys in the RP database.** If the RP's public keys/credential IDs are leaked, an attacker still cannot forge valid assertions without the private key, yet you must still protect account mappings, credential management, and sessions to prevent account takeover.

### 3.1. Is a credential a hashed password?

No. Password authentication usually requires the client to send a secret for the server to check. With WebAuthn, the server generates a **fresh challenge**, the authenticator signs data bound to the RP ID/challenge/origin, and the server verifies with the registered **public key**. There is no corresponding "password hash" transmitted to the RP on every login.

### 3.2. Is the Credential ID a secret?

Do not treat the credential ID as a password or bearer token. The ID only helps select the public key record; knowing the ID is not enough to forge a signature. Still, the ID and user handle can carry identifying and privacy implications; do not log or expose them publicly unnecessarily.

## 4. Passkeys, WebAuthn credentials, and discoverable credentials

A **WebAuthn public-key credential** is the general concept. A **Passkey** in current usage is a **discoverable** credential that the authenticator can look up by RP ID without the user typing a username first.

There are two cases:

- **Username-first:** the user enters their username. The RP looks up the account's credential records and passes the `allowCredentials` list to the browser.
- **Username-less/discoverable:** the browser calls `navigator.credentials.get()` with an empty/omitted `allowCredentials` list per the appropriate flow. The authenticator/provider finds credentials for the RP ID and the user picks an account; the RP relies on the verified credential ID and `userHandle` to find the right account.

Do not confuse `userHandle` with `user.name` or `user.displayName` in registration options. `user.id` (the user handle) must be stable for the account. Usernames/emails can change and can collide across tenants; the server needs an appropriate immutable mapping.

### 4.1. Device-bound vs. synced passkeys

| Type | Characteristics | Management considerations |
| --- | --- | --- |
| Device-bound | Private key is tied to one authenticator/device and typically does not sync | Device loss → needs another credential or recovery |
| Synced passkey | Provider can back up/sync key material via its own protected mechanism to the same user's devices | Security of the provider account, recovery, and sync fabric |
| Roaming security key | Hardware key usable across multiple machines via USB/NFC | Managing lost/replaced keys, attestation if required by enterprise |
| Platform authenticator | Built into a computer or phone, using local PIN/biometrics | Screen lock policies, backups, and device management |

Saying "the private key never leaves any device" is **inaccurate for all synced passkeys**. What is accurate is that **the RP never receives the private key and cannot sign on the authenticator's behalf** in the standard model; the passkey provider may sync keys through a protected mechanism.

## 5. RP ID and origin: WebAuthn's anti-phishing lock

Two important but distinct concepts:

- **RP ID:** domain name without scheme or port, e.g., `example.com`.
- **Origin:** triple of scheme + host + port of the page running WebAuthn, e.g., `https://login.example.com:443` (actual URL representation may normalize default ports).

Examples:

~~~text
App origin:      https://login.example.com
RP ID:           example.com

App origin:      https://login.example.com
RP ID:           login.example.com

App origin:      https://evil.example.net
Requested RP ID: example.com        → rejected under standard rules
~~~

WebAuthn rule: the RP ID must correspond to the origin's effective domain or a valid registrable domain suffix, barring separately specified extension mechanisms. You cannot arbitrarily pick another domain's RP ID; never use a public suffix like `com`.

**Risk of setting the RP ID too broad:** using `example.com` across many subdomains allows multiple origins in that scope to request credentials, so every origin within policy scope must be controlled. Prefer a narrow, stable RP ID, and only broaden it when the application genuinely needs to share credentials across trusted subdomains.

### 5.1. Origin must be verified on the server

The browser puts `origin` inside `clientDataJSON`. The RP must verify this value belongs to the allowed origins list—**never** trust an origin self-reported by the frontend in arbitrary JSON. If the application sits behind a proxy/multi-domain layer, configure a **fixed** origin list that exactly matches the public scheme/host/port.

WebAuthn runs in a **secure context**. Production deployments must use HTTPS. For dev, `http://localhost:8080` is an origin exception considered trustworthy under the WebAuthn model; do not generalize that to arbitrary internal HTTP addresses or IPs. Therefore, configuring `rpId("localhost")` combined with `allowedOrigins("http://localhost:8080")` is strictly for **local demos**.

### 5.2. Why isn't phishing resistance absolute?

A spoofed website at `evil.example.net` cannot validly use a passkey with RP ID `example.com` in standard WebAuthn. The server also checks `origin`/`rpIdHash` to guard against misconfiguration or abnormal clients. However, passkeys **cannot prevent every attack**: XSS on the real origin, hijacking an active session, weak recovery flows, letting an attacker register a new passkey, or broken authorization remain dangerous.

## 6. Registration ceremony: creating a credential for the first time

Registration usually happens **after the user/account is already known** and authorized to register a passkey for that specific account (logged in, recently re-authenticated, or via trusted onboarding).

~~~text
User                Browser                    RP server                Authenticator
 |                     |                           |                          |
 | click "Add passkey" |                           |                          |
 |-------------------->| POST registration options |                          |
 |                     |-------------------------->|                          |
 |                     |  challenge + rp + user    |                          |
 |                     |<--------------------------|                          |
 |                     | navigator.credentials.create({publicKey: options})   |
 |                     |----------------------------------------------------->|
 |                     |              create key pair, verify UP/UV           |
 |                     |<-----------------------------------------------------|
 |                     |  credential + attestation response                   |
 |                     | POST credential JSON      |                          |
 |                     |-------------------------->|                          |
 |                     |   verify challenge, origin, rpIdHash, flags,         |
 |                     |   attestation policy, account binding                |
 |                     |   save credential ID + public key + userHandle       |
 |                     |<--------------------------|  success                 |
~~~

### 6.1. Generating options on the RP side

The server builds `PublicKeyCredentialCreationOptions` which may look like:

~~~json
{
  "rp": {
    "id": "login.example.com",
    "name": "Learning Portal"
  },
  "user": {
    "id": "b3BhcXVlLXVzZXItNDI",
    "name": "learner@example.com",
    "displayName": "Learner"
  },
  "challenge": "c2VydmVyLWdlbmVyYXRlZC1yYW5kb20tYnl0ZXM",
  "pubKeyCredParams": [
    {"type": "public-key", "alg": -7},
    {"type": "public-key", "alg": -8}
  ],
  "timeout": 60000,
  "excludeCredentials": [],
  "authenticatorSelection": {
    "residentKey": "required",
    "userVerification": "required"
  },
  "attestation": "none"
}
~~~

This is **structural illustrative JSON**; the challenge and user ID strings are not secrets/test vectors to reuse. In practice:

- The challenge must be generated with a CSPRNG, have sufficient entropy (≥16 bytes recommended, typically 32 bytes), a short TTL, be tied to the specific ceremony, and be **single-use**.
- `user.id` is an opaque user handle generated by the RP and linked to the account; never let the client pick an arbitrary account ID.
- `pubKeyCredParams` indicates the algorithms the RP is willing to accept, such as COSE `-7` (ES256) or `-8` (EdDSA) when supported by the library/ecosystem.
- `residentKey="required"` requests a discoverable credential suited to the passkey experience.
- `userVerification="required"` requires user verification on the authenticator; choose this according to UX/security policy and verify UP/UV in the response.
- `attestation="none"` is suitable for many consumer products; enterprises may need additional attestation per device/key policy.

The server must not store challenges indefinitely or reuse the same challenge across accounts. For session-based web apps, protect the options and registration endpoints with CSRF tokens and prevent registration via a hijacked session.

### 6.2. Browser calls the authenticator

The JavaScript snippet below only illustrates the browser API; the application must fetch options from the server, properly convert Base64URL binary fields to `ArrayBuffer`, and send the encoded response to the backend:

~~~javascript
// Illustrative snippet (does not include fetch/CSRF/JSON encoding).
const credential = await navigator.credentials.create({
  publicKey: creationOptionsWithArrayBuffers
});

// credential.response is an AuthenticatorAttestationResponse.
// Send required fields to the server over HTTPS for verification.
~~~

Binary fields that must be handled properly include `challenge`, `user.id`, and `excludeCredentials[].id`. The browser WebAuthn API does not accept raw Base64URL strings as binary directly. The result containing `rawId`, `response.clientDataJSON`, and `response.attestationObject` must be serialized/encoded to match the server library's contract.

### 6.3. What does the authenticator return during registration?

The registration response provides information for the RP to extract:

- **Credential ID** and **credential public key**.
- **Authenticator data** with `rpIdHash`, flags, `signCount`, and (during registration) attested credential data.
- **Client data** containing `type="webauthn.create"`, challenge, origin, and contextual fields.
- **Attestation statement** if requested/supported; may be none/self/basic/enterprise per policy and implementation.
- **User presence / user verification** flags that the RP must check as required.

The server must use a **standards-compliant WebAuthn library** to verify all constraints, rather than manually parsing a few fields and declaring registration successful.

### 6.4. Storing the record under the right account

The RP **only saves the credential after all checks pass**, bound to the user authorized for that registration ceremony. Never read a username/account ID from an unverified payload and attach an attacker's credential to a victim's account.

Store multiple credentials per account to support multiple devices and maintain a controlled recovery mechanism. `excludeCredentials` helps prevent re-registering the same credential on an authenticator; the server still needs a unique constraint on credential ID.

## 7. Authentication ceremony: using the private key to prove identity

After registration, the user signs in using a **fresh challenge**:

~~~text
Browser                  RP server                     Authenticator
   |                         |                                |
   | POST authentication     |                                |
   | options                 |                                |
   |------------------------>|                                |
   | challenge, rpId,        |                                |
   | allowCredentials / UV   |                                |
   |<------------------------|                                |
   | navigator.credentials.get({publicKey: options})          |
   |--------------------------------------------------------->|
   |                    select credential, verify UP/UV       |
   |<---------------------------------------------------------|
   | assertion: credential ID, authenticatorData,             |
   |            clientDataJSON, signature, userHandle         |
   |------------------------>|                                |
   |                         | look up public key by ID       |
   |                         | verify challenge/origin/rp ID  |
   |                         | verify UP/UV + sig/counter     |
   |                         | bind account, create session   |
   |<------------------------| success                        |
~~~

### 7.1. Authentication options

Example:

~~~json
{
  "challenge": "bmV3LWNzcHJuZy1jaGFsbGVuZ2U",
  "timeout": 60000,
  "rpId": "login.example.com",
  "allowCredentials": [],
  "userVerification": "required"
}
~~~

This is **illustrative** (do not use this challenge value outside documentation). If `allowCredentials` is empty, the authenticator can offer **discoverable credentials** belonging to the RP ID. For username-first, the RP can supply a list of credential IDs belonging to the specific account being authenticated.

### 7.2. Browser calls get()

~~~javascript
// Illustrative snippet; requestOptionsWithArrayBuffers is options
// with Base64URL challenge and credential IDs converted to binary.
const assertion = await navigator.credentials.get({
  publicKey: requestOptionsWithArrayBuffers
});

// assertion.response is an AuthenticatorAssertionResponse.
// Send ID, authenticatorData, clientDataJSON, signature,
// userHandle (if present) per the server API contract.
~~~

If the user cancels, times out, or has no matching credential, the browser may throw errors like `NotAllowedError` or `SecurityError` depending on the situation. Do not treat every error as "wrong passkey" and encourage unchecked re-registration.

### 7.3. Which bytes does the authenticator sign?

For a standard authentication assertion, the authenticator computes the signature over:

~~~text
authenticatorData || SHA-256(clientDataJSON)
~~~

Where:

- `authenticatorData` contains `rpIdHash = SHA-256(RP ID)`, UP/UV flags, and other components such as the signature counter.
- `clientDataJSON` provided by the WebAuthn client contains `type="webauthn.get"`, challenge, origin, and contextual fields.
- The credential's private key creates the signature using the registered algorithm; the server uses the corresponding **public key** to verify it.

**Important:** the server does not just check `signature` and call it valid. It must also check every component and ceremony policy. Modifying `clientDataJSON` or the challenge breaks the signature or fails data validation.

### 7.4. Mandatory server-side RP checklist for assertion verification

1. **Locate the exact credential:** using the credential ID returned by the browser, retrieve the registered record; non-existent or revoked credential → reject.
2. **Verify `type`:** client data must specify `webauthn.get`, not confused with `webauthn.create`.
3. **Verify challenge:** exact bytes of the generated challenge, belonging to the expected request/session/transaction, still valid and unused.
4. **Verify origin:** present in the allowed origins list; handle `crossOrigin`, `topOrigin`/iframe if implementing special cases.
5. **Verify `rpIdHash`:** matches the SHA-256 of the expected RP ID.
6. **Verify signature:** using the stored credential public key and the right algorithm; data strictly formatted per WebAuthn.
7. **Verify UP/UV:** UP is user presence; UV is user verification. If policy requires UV, the UV flag must be set—do not equate simply tapping a key with verifying the user.
8. **Verify user handle and account mapping:** the credential belongs to the right account/tenant; never switch accounts based on a client-supplied field when it mismatches stored data.
9. **Check signature counter appropriately:** if the authenticator has a reliable counter, treat non-incrementing counters as a risk signal; do not enforce a rigid "must increment" rule on all synced credentials whose counter stays 0.
10. **Clean up state:** consume the challenge, update metadata, create the Spring `Authentication`, and establish a session protected against session fixation.

Only when **all policy-relevant checks** pass should you establish a user session. Do not write a validator with a handful of `if` statements; use WebAuthn4J or a battle-tested library to handle CBOR/COSE and the full protocol.

## 8. Key WebAuthn flags and fields

### 8.1. User Presence (UP) and User Verification (UV)

| Attribute | What does it prove? | Example | What does it NOT prove? |
| --- | --- | --- | --- |
| **UP** | Someone interacting with the authenticator is present/approved the action | Touching a security key | Local identity verification via PIN/biometric |
| **UV** | The authenticator verified the user locally via a supported mechanism | PIN, biometric, device password | Evidence for the RP to collect biometrics |
| **BE/BS** | Backup eligibility / backup state when reported by the authenticator | Credential can be synced or is backed up | Security quality guarantee of the cloud sync provider |
| **signCount** | Per-authenticator/credential counter when available | RP can detect anomalies if a counter is used | Absolute proof of device cloning when 0 or non-incrementing |

When an organization wants **passkey sign-in with local user verification**, the RP should request `userVerification="required"` and the server must check UV. Fingerprint/Face ID sensors only send verification results through the authenticator; the RP never receives biometric templates.

### 8.2. Attestation differs from assertion

**Attestation** happens during credential **registration**: it helps the RP evaluate information about the authenticator or credential provenance per policy. It may include an attestation statement, AAGUID, and attestation certificates; in many consumer use cases, `attestation="none"` is sufficient to reduce tracking/privacy risks.

**Assertion** happens during **sign-in**: a signature over a fresh challenge and WebAuthn data proving authorization to use the registered credential's private key.

Attestation is not a password and is not required by default for sign-in. Do not require every user to present enterprise X.509 attestation certificates when the product does not need a device-verification policy.

### 8.3. Data formats

- `attestationObject`: CBOR object, typically containing `authData` and an attestation statement.
- `authenticatorData`: binary, containing RP ID hash/flags/counter and extensions.
- `clientDataJSON`: JSON bytes generated by the browser with type, challenge, and origin.
- `credentialPublicKey`: public key in COSE_Key format; the server needs a proper COSE decoder.
- `credential.id`/`rawId`: byte ID, usually Base64URL-encoded in JSON APIs.
- `signature`: bytes generated by the authenticator.
- `userHandle`: opaque byte account identifier, which may appear during authentication.

**Base64URL is an encoding, not a signature or secret encryption.** When passing binary over JSON, encode/decode cleanly in the right direction—do not arbitrarily compare Base64URL strings directly against raw byte arrays.

## 9. Spring Boot 3.5 + Spring Security 6.5 example (Java 17+)

Spring Security 6.5 supports passkey registration and verification in Servlet apps using WebAuthn, backed by the **WebAuthn4J** library. This example uses **password login to register a passkey the first time**, then tests **passkey login**. This is a **learning demo**: it has no durable persistence, account recovery, auditing, rate limiting, or enterprise policies.

### 9.1. Create the Maven project

Create the structure:

~~~text
passkey-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── passkey/
                    └── PasskeyDemoApplication.java
~~~

Complete `pom.xml` file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
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

The WebAuthn4J version here follows the Spring Security 6.5 guide. If upgrading to Spring Security 7 or Boot 4, **re-verify dependencies**: the module system and WebAuthn configuration may differ. Do not blindly copy this version across all Spring versions.

### 9.2. Complete Java source

Create `src/main/java/demo/passkey/PasskeyDemoApplication.java`:

~~~java
package demo.passkey;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PasskeyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasskeyDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("localhost")
                .rpName("Passkey Learning Demo")
                .allowedOrigins("http://localhost:8080"));

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-password")
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @RestController
    static class ExampleController {

        @GetMapping({"/", "/public"})
        String welcome() {
            return "Passkey demo running";
        }

        @GetMapping("/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }
    }
}
~~~

**Explanation:**

1. `formLogin(...)` provides a password login path for **demo onboarding**; it is not a WebAuthn requirement that passkeys always need passwords.
2. `webAuthn(...)` enables passkey integration: RP ID `localhost`, trusting only the origin `http://localhost:8080`.
3. `.anyRequest().authenticated()` protects `/me` and other routes; the default WebAuthn registration page requires an authenticated user so credentials are bound to the right account.
4. `UserDetailsService` creates the demo user `learner`. `{noop}` **must only be used in labs**; production uses a strong `PasswordEncoder` and never stores plaintext passwords.
5. Spring Security 6.5 provides a credential registration UI at `/webauthn/register` and supports passkeys on the default login page.
6. The default WebAuthn repository stores data in-memory; after restart, demo passkey data **no longer exists**, even though the passkey provider on the device may still hold the old credential. Production requires persistent storage and credential lifecycle management.

### 9.3. Test run on localhost

In the `passkey-demo` directory, with JDK 17+ and Maven installed:

~~~bash
mvn spring-boot:run
~~~

Open **exactly** `http://localhost:8080` in the browser (do not use `http://127.0.0.1:8080` for this `localhost` RP ID/origin demo). Once the app starts, the public page shows:

~~~text
Passkey demo running
~~~

Visiting `http://localhost:8080/me` while logged out → Spring Security redirects to the login page. Sign in with:

~~~text
Username: learner
Password: demo-password
~~~

Then visit:

~~~text
http://localhost:8080/webauthn/register
~~~

Using a WebAuthn-capable browser/device, create a passkey via the OS or passkey provider UI. Local PIN/biometric may be prompted. After successful registration:

1. Log out via `/logout` following the appropriate Spring Security flow.
2. Reopen the login page and pick the passkey option if shown by the browser and default UI.
3. Select the registered passkey and verify on the authenticator.
4. Visit `/me`. Expected JSON response:

~~~json
{"username":"learner"}
~~~

Login outcomes depend on browser/OS, WebAuthn4J, accurate RP ID/origin, session state, and available passkeys. Do not claim a specific Java stdout message when a credential is registered, as it is a browser↔server flow.

**Testing distinction:** the Spring code above is **a runnable Maven application when dependencies are compatible**, but there is no pre-built "mock passkey" generated by Java code. Real browser/authenticator interaction is required to complete the WebAuthn ceremony.

### 9.4. Illustrative endpoints when building a custom frontend

Per the Spring Security 6.5 guide, endpoints you may encounter:

| Endpoint | Role | Notes |
| --- | --- | --- |
| `GET /webauthn/register` | Default registration UI | User must be authenticated |
| `POST /webauthn/register/options` | Generates creation options + challenge | CSRF token; mutates state |
| `POST /webauthn/register` | Receives registration response | CSRF; save only after validation |
| `POST /webauthn/authenticate/options` | Generates authentication options + challenge | CSRF; ceremony binding |
| `POST /login/webauthn` | Receives authentication assertion | CSRF; creates authentication when valid |

When building a custom frontend, the browser must convert binary fields Base64URL↔ArrayBuffer and send payloads matching the exact JSON contract of the Spring Security version in use. Do not assume an arbitrary response shape from another JavaScript library is automatically compatible with the default endpoints.

Spring Security 6.5 provides credential storage interfaces such as `PublicKeyCredentialUserEntityRepository` and `UserCredentialRepository`; JDBC implementations are included, and custom repository beans are supported. The challenge/creation options repository may default to HTTP session; across multiple replicas, ensure sticky routing or appropriate shared session state.

## 10. Standalone Java 17 program: private key signs, public key verifies

This program is **not a WebAuthn server/client**. It only demonstrates the asymmetric signature principle in a credential: the private key signs data bound to an RP/challenge; the public key detects when data is altered. Real WebAuthn uses `authenticatorData || SHA-256(clientDataJSON)`, checks origin/`rpIdHash`/counter/flags, and processes CBOR/COSE as in section 7.

Create `CredentialSignatureDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Base64;

public class CredentialSignatureDemo {

    static byte[] sign(PrivateKey key, byte[] message) throws Exception {
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(key);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(PublicKey key, byte[] message, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signature);
    }

    static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(256);
        KeyPair credentialKeys = generator.generateKeyPair();

        byte[] challenge = new byte[32];
        new SecureRandom().nextBytes(challenge);
        String challengeText = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(challenge);

        String original = "rp=login.example.com|challenge=" + challengeText;
        byte[] signature = sign(credentialKeys.getPrivate(), bytes(original));

        String wrongRp = "rp=evil.example.net|challenge=" + challengeText;
        String wrongChallenge = original + "-modified";

        System.out.println("valid=" +
                verify(credentialKeys.getPublic(), bytes(original), signature));
        System.out.println("wrongRp=" +
                verify(credentialKeys.getPublic(), bytes(wrongRp), signature));
        System.out.println("wrongChallenge=" +
                verify(credentialKeys.getPublic(), bytes(wrongChallenge), signature));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 CredentialSignatureDemo.java
java CredentialSignatureDemo
~~~

**Exact stdout:**

~~~text
valid=true
wrongRp=false
wrongChallenge=false
~~~

Explanation: each run generates a new key pair and challenge, yet the boolean results remain identical; the public key verifies a valid signature on the original data and detects both tampered message cases.

**Do not use this crypto demo as an authentication backend**: it lacks browser-provided origin, authenticator data structure, RP ID hash, challenge persistence, UP/UV, credential record/account mapping, COSE standard, and every other WebAuthn requirement.

## 11. Why does Spring Security need a separate credential store?

One user can have multiple credentials and multiple devices. The system must store **public keys and metadata per account**, while distinguishing app management accounts from passkey identities.

Example:

~~~text
users
  user_id: 42
  username: learner

webauthn_users
  user_id: 42
  user_handle: opaque-account-identity

credentials
  credential_id: <binary ID>
  user_id: 42
  public_key: <COSE>
  signature_counter: ...
  status: active
  created_at: ...
  last_used_at: ...
~~~

The schema above illustrates a relational model, not Spring's DDL. Security essentials:

- The **credential ID record must be unique** within the valid namespace.
- Credentials are bound **solely to the authenticated account during registration**; never bind by an unverified email.
- If email/username changes, the user handle remains stable and credential mapping stays intact.
- Revoking a credential must ensure logins with that credential are no longer accepted, even if the authenticator/provider still holds the private key.
- In a cluster, all instances must share the same credential store and keep counter/challenge lifecycles consistent.

### What does credential management need?

A secure UI should support:

- Listing credentials by label, creation time, last-used time, and type/device when metadata is available.
- Adding a passkey after **recent reauthentication** or equivalent strong proof.
- Deleting a credential after authorized confirmation, never relying solely on a client-submitted ID.
- Alerting on credential addition/removal; checking when removing the last remaining passkey.
- Allowing multiple passkeys to reduce single-device dependency.
- A recovery flow protected on par with passkeys; avoid weak password fallbacks that negate phishing resistance.

## 12. Security risks and limitations often misunderstood

### 12.1. Where does phishing resistance come from?

Passkeys are bound to an RP ID, while the browser client constructs `clientDataJSON` containing the origin and challenge. The authenticator signs data linked to the RP ID; the RP verifies the signature and related fields. A site on another domain cannot validly use a credential with the same RP ID in a standard WebAuthn flow. This improves on passwords/OTPs, which are easily relayed to fake sites.

However, **enabling WebAuthn while skipping server-side origin/challenge/rpIdHash checks** breaks that protection. Use a maintained library and test negative cases.

### 12.2. Does not protect against all session risks

Passkey login may be strong, yet post-login session cookies can still be stolen via XSS, misconfigured cookies, or session fixation. Continue configuring:

- HTTPS, HSTS, CSP, and XSS controls.
- Appropriate `Secure`/`HttpOnly`/`SameSite` cookies and session fixation protection.
- CSRF protection for state-changing operations, especially registering/deleting credentials.
- Rate limiting, auditing, session timeouts, and restrictions on sensitive actions.
- Reauthentication for adding passkeys, changing recovery methods, or administrative actions.

### 12.3. UP is not synonymous with UV

Tapping a security key can demonstrate **user presence** without verifying the user locally. If policy requires a PIN/biometric, the server must request UV and **verify the UV flag**. Never claim "passkeys are always MFA" just because some devices have biometrics.

### 12.4. Attestation is not required by default

Attestation can help enterprises restrict authenticators to a trusted allowlist, but it adds complexity and privacy constraints. For consumer services, requesting `attestation="none"` is typically appropriate. Even when attestation passes, you must still verify the public key, challenge, RP ID, and account binding.

### 12.5. Syncing and device loss

Synced passkeys support signing in across multiple devices via a sync provider, but organizations need to evaluate sync account security, provider recovery policies, and assurance requirements. Device-bound credentials may suit high-assurance environments, provided backup credentials exist if a key is lost. Avoid making absolute claims that either synced or device-bound is always safer in every use case.

## 13. Common WebAuthn integration errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `navigator.credentials` missing/throws SecurityError | Page is not a secure context, or invalid RP ID | Use HTTPS; `http://localhost` for dev; verify effective domain |
| Browser reports `NotAllowedError` | User cancelled, timeout, missing credential, authenticator didn't satisfy policy | Handle browser error without leaking internals; allow sensible retry |
| Registered successfully but login fails after restart | In-memory credential repository was wiped | Use a persistent database |
| Challenge mismatch | Lost session, expired challenge, replayed request, or wrong binary decoding | Store short TTL, proper base64url, bind session/operation |
| Origin mismatch | Accessed via different host/port/scheme than configured | Set `allowedOrigins` to match actual public origin |
| RP ID hash mismatch | `rpId` changed between registration and login | Use a stable RP ID matching the domain |
| Signature failed | Public key mismatches credential ID, wrong data decode/serialize, or altered signature | Do not write your own crypto parser; use a library |
| User verification required but UV=false | Authenticator did not verify user locally | Choose supported device/method, enforce UV policy |
| Credential exists but wrong user is assigned | Incorrect `userHandle`/credentialId→account mapping | Verify server-side mapping and unique constraints |
| Counter does not increment | Synced key/zero counter or cloning risk | Apply counter rules per device/library, audit |
| POST options/register returns 403 | Missing CSRF or unauthenticated account | Send valid CSRF token and protect registration |
| Using `127.0.0.1` for `localhost` demo RP | Origin/RP ID mismatch | Use `http://localhost:8080` exactly |
| User lost device with no remaining passkey | No multiple credentials/recovery configured | Flow to enroll backup credentials and strong recovery |
| Attacker with stale session adds a new passkey | Missing recent reauthentication | Require step-up, notify on changes, audit |

## 14. Production deployment checklist

### RP configuration

- [ ] Minimal, stable RP ID covering only trusted origins.
- [ ] Production HTTPS; public hostname/scheme/port matching `allowedOrigins`.
- [ ] Up-to-date server WebAuthn library; no custom COSE/CBOR validators.
- [ ] Challenges generated via CSPRNG, sufficient entropy, TTL, one-time use, and ceremony-bound.
- [ ] Configured trusted algorithms and user verification per policy.
- [ ] Ensure registration only runs for authenticated/validly onboarded accounts.
- [ ] Verify type/challenge/origin/rpIdHash/UP/UV/signature/account mapping.
- [ ] Clear-purpose attestation policy respecting privacy.
- [ ] Signature counter and backup flags handled safely, without applying flawed logic to synced passkeys.

### Data and lifecycle

- [ ] Store credential ID, public key, user handle, owner, and necessary metadata in persistent storage.
- [ ] Support adding multiple passkeys and managing/deleting/revoking with reauthentication.
- [ ] Enforce `userHandle`/credential ID uniqueness and tenant isolation.
- [ ] Design strong account recovery without downgrading security via weak password/email fallbacks.
- [ ] Monitor audits/passkey enrollment, anomalies, loss/recovery, and device rotation.
- [ ] Protect sessions, CSRF, XSS, cookies, and rate limiting just like other login mechanisms.

### Minimum testing

- [ ] Successful registration and login with a real passkey.
- [ ] Login with no credential, deleted credential, or revoked credential.
- [ ] Expired challenge, replayed/wrong challenge.
- [ ] Wrong origin and RP ID; tampered JSON fields.
- [ ] Invalid signature, non-existent credential ID.
- [ ] UP/UV flags failing policy.
- [ ] Credential belonging to user A cannot authenticate as user B.
- [ ] Login after restart/across replicas when using persistent storage.
- [ ] Unauthorized credential addition/deletion or missing recent reauthentication must be rejected.
- [ ] Recovery and lost/swapped device flows cannot bypass authorization.

For server-side validation tests in Java, prefer properly structured WebAuthn fixtures and controlled integration tests using a browser/virtual authenticator, rather than just unit-testing that JSON contains a `signature` field.

## 15. Self-check questions

1. Are the Relying Party and authenticator the same component? Which side owns the private key?
2. Why does the server need to store both the credential ID and the public key?
3. How does `user.id` (user handle) differ from email/username?
4. What role does the browser play between the JavaScript WebAuthn API and the authenticator?
5. During registration, does `navigator.credentials.create()` return an attestation response or an authentication assertion?
6. During login, why must the server check `SHA-256(RP ID)` in the authenticator data?
7. Is verifying the signature with the public key alone enough for a valid WebAuthn login? What is missing?
8. What is the difference between User Presence and User Verification?
9. Why does a synced passkey not mean the private key permanently exists on only one device?
10. Why do passkeys still require CSRF, session management, and strong account recovery?
11. Why does the demo use `localhost`, rather than any arbitrary HTTP hostname?
12. If an account's session is hijacked and an attacker registers a new passkey, do passkeys automatically protect the account from this scenario?

**Conclusion:** The authenticator **manages the private key and signs**, the browser **coordinates WebAuthn and provides the origin**, and the RP **issues challenges, stores public keys, and verifies all constraints**. Public-key credentials ensure the server doesn't need to hold a shared-secret password to authenticate users, but they are only secure when registration, assertion verification, sessions, and recovery are all properly designed.

## 16. Official references and security guides

- [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/)
- [Spring Security 6.5 — Passkeys (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html)
- [Spring Security 6.5 — WebAuthnConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/WebAuthnConfigurer.html)
- [OWASP — Passkey Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Passkey_Security_Cheat_Sheet.html)
- [FIDO Alliance — Passkeys](https://fidoalliance.org/passkeys-2/)
- [MDN — Web Authentication API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API)
- [Spring Blog — Spring Boot 3.4 / WebAuthn demo](https://spring.io/blog/2024/11/24/bootiful-34-security/)
