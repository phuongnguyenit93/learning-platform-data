# Phishing, step-up authentication, and the limits of replayable-secret mechanisms

## 1. Learning objectives

Phishing tricks users into interacting with a spoofed page, application, or verifier to steal information, induce unauthorized login approvals, or hand over a login session. In systems using passwords and OTPs, a fake site can **collect user-entered values** and immediately relay them to the real system.

Three concerns must be separated:

1. **Phishing:** an attacker impersonates a website/app or support flow to steal credentials or hijack a session.
2. **Additional authentication (step-up/reauthentication):** requiring fresher or stronger authentication proof before a sensitive action. Step-up may involve re-entering a password, adding an OTP, or using a passkey, yet **not every form is phishing-resistant**.
3. **Limits of replayable secrets:** passwords, website-entered PINs, SMS OTPs, TOTPs, or recovery codes are values that can be copied/forwarded. Short lifetimes or single-use properties shrink the abuse window, yet **do not stop real-time relaying**.

After this lesson you should be able to:
- Distinguish classic phishing, real-time reverse-proxy phishing, and session hijacking.
- Explain why password+TOTP is usually MFA yet **is not phishing-resistant MFA**.
- Understand WebAuthn/FIDO2 passkey principles based on `origin`/`RP ID` and their security boundaries.
- Determine when reauthentication/step-up is needed and what proof the server must check.
- Design session controls, anti-downgrade, recovery, enrollment, and monitoring.
- Understand a Spring Boot 3.x, Spring Security 6.x, Java 17+ example demonstrating **password reauthentication**, while clearly knowing why that example is *neither* MFA nor phishing-resistant.

**Core idea:** more authentication factors generally reduce account takeover risk, yet **phishing resistance is a property of the protocol and verifier binding**, not simply how many code-entry screens appear.

## 2. How does phishing work?

### 2.1. Fake login pages

An email impersonating IT sends a user to `https://login-example.attacker.example` styled like `https://login.example.org`. If the user types their password into the fake page, the attacker can use that password on the real website.

~~~text
User                            Fake site                      Real website
    |                               |                                |
    | clicks spoofed link           |                                |
    |------------------------------>|                                |
    | enters username/password      |                                |
    |------------------------------>| steals credentials             |
    |                               |---- signs in with password --->|
    |                               |                                |
    |                               |       (may be blocked by MFA)  |
~~~

Measures such as password managers autofilling only on exact domains, training to spot fake websites, email protection, and lookalike domain detection all help, yet users must never be forced to act as the **sole line of defense**.

### 2.2. Real-time phishing via reverse proxy

A more dangerous case: the fake site proxies requests/responses to the real site live during the session. The user enters their password, then enters an OTP on the fake page; the attacker relays each value immediately before expiration.

~~~text
Victim's browser          Fake site / relay              Real RP or IdP
      |                           |                               |
      | username + password       |                               |
      |-------------------------->|---- forwards ---------------->|
      |<--------------------------|<--- requests OTP -------------|
      | fresh OTP (6 digits)      |                               |
      |-------------------------->|---- forwards rapidly -------->|
      |                           |<--- session/token ------------|
      |                           |                               |
      |                           └── can hijack session if       |
      |                               matching artifact is captured |
~~~

An OTP with a 30-second TTL and single-use semantics **can still be relayed on its very first use**. "One-time" does not mean "bound only to the victim's browser". After login, the attacker can capture session cookies or tokens depending on system architecture and controls.

This is a threat-model analysis for **defense**, not a guide to deploying phishing infrastructure. Real systems must protect passwords, OTPs, sessions, and recovery/enrollment flows alike.

### 2.3. Phishing can pivot to other targets

Phishing does not only target passwords:
- Tricking users into entering OTPs or recovery codes.
- Flooding push approvals so users tap approve out of habit.
- Tricking users into enrolling an attacker's MFA device/passkey onto their account.
- Coaxing users into granting OAuth consent to a malicious client.
- Sending "account recovery" links leading to untrusted reset flows.
- Stealing cookies/sessions after the user logs in through a valid authentication step.

Thus anti-phishing policies must apply **after login** and on authenticator-setup operations, not only on `POST /login`.

## 3. What is a replayable secret?

"Replayable secret" here means **a string or answer a user can type/copy into an interface**, such as:
- passwords or passphrases;
- SMS/voice OTP codes;
- codes from TOTP apps;
- recovery/backup codes;
- email confirmation codes;
- security-question answers;
- certain PINs requested directly by a website form.

These values can be **observed, copied, and presented to another verifier** if collected by a fake site. By contrast, a **local** authenticator-unlock PIN for WebAuthn is normally never sent to the RP; do not equate that PIN with a PIN typed into a website form.

### Mechanism comparison table

| Mechanism | Typical role | Can be typed into a fake site? | Phishing-resistant by design? |
|---|---|---|---|
| Password/passphrase | Something you know | Yes | **No** |
| SMS OTP | Out-of-band/possession channel per policy | Yes | **No** |
| Email OTP | Code in inbox | Yes | **No**; weak independence if email shares account/recovery |
| TOTP app | Secret- and time-based OTP | Yes | **No** |
| HOTP / hardware OTP display | Counter- or device-based OTP | Yes | **No** if user types the code |
| Recovery code | Account rescue | Yes | **No** |
| Password + TOTP | Two independent factors if configured properly | Yes | **MFA, yet not resistant to real-time phishing** |
| Simple "Approve" push | App confirmation | Not a typed string, yet easily tricked into approving | **Not by default** |
| Push number matching | Pairs prompt and challenge number to cut fatigue | Users can still be socially engineered/relayed | **Does not by default meet phishing-resistance criteria** |
| FIDO2/WebAuthn passkey | Public key bound to RP ID | Private key is never sent or re-typed | **Can be phishing-resistant** when verifying origin/RP ID properly |
| Client-authenticated TLS with channel binding | Key proof bound to TLS channel | Cannot simply copy a string | **Can be phishing-resistant** when designed properly |

**You cannot conclude a product is phishing-resistant merely from the label "MFA".** You must check whether authenticator output can be manually typed/copied and whether the protocol binds cryptographically to the matching verifier/challenge/channel.

## 4. MFA, reauthentication, step-up, and phishing resistance

### 4.1. True MFA requires independent factors

Traditional factor categories:
1. **Something you know:** passwords/PINs.
2. **Something you have:** enrolled authenticators/certs/keys.
3. **Something you are:** biometrics used to unlock/verify at the authenticator.

Entering the password twice is **the same factor**, not MFA. A password plus another PIN may also remain solely "something you know" without independent possession/biometric proof. IPs, locations, remember-device cookies, CAPTCHAs, or "are you sure?" prompts are extra signals/friction, **never MFA factors on their own**.

A typical TOTP app proves possession of the device holding the TOTP secret; combined with a password, it can constitute MFA. Yet because the TOTP code is displayed and typed into websites, it can be relayed live to the real website.

### 4.2. Reauthentication and step-up are not synonymous

- **Reauthentication:** requesting fresh identity proof, typically due to an old session or sensitive action—for example, re-entering a password.
- **Step-up authentication:** raising assurance level as risk rises, such as moving from password to WebAuthn, or from a routine session to an action freshly verified by a strong factor.
- **Phishing-resistant authentication:** a protocol preventing authenticator output from working at an impostor verifier without relying on user vigilance.

Re-entering a password can refresh `auth_time` (freshness), yet **does not upgrade to MFA**, much less confer phishing resistance. Adding TOTP can upgrade password-only to MFA, yet still fails against real-time relaying.

### 4.3. Freshness, assurance, and intent are three distinct dimensions

| Dimension | Question to answer | Example |
|---|---|---|
| **Freshness** | How long ago was the last strong authentication? | `auth_time` within 5 minutes |
| **Assurance / factors** | Which mechanism was used, and does it meet required policy? | Passkey with UV, or password+TOTP |
| **Intent / transaction binding** | Did the user confirm this exact specific action? | Confirm changing email from A to B |

A token/signal stating the user logged in recently **does not automatically prove** they confirmed money-transfer details. For high-risk transactions, bind approval to `transactionId`, amount/destination, or changed content per policy, and protect against payload tampering after approval.

## 5. Why can valid unexpired OTPs still be phished?

For example: a user sees TOTP code `123456` (illustrative string only, not a valid OTP) and enters it on a fake website. The fake website forwards the code to the real verifier before it expires. If the real system only checks the code, **it has no idea which website the code was entered on**.

Helpful controls that **do not fully stop relaying**:
- Short TTLs and one-time consumption prevent reuse after consumption, yet do not stop the attacker from using the token first.
- Attempt limits/rate limits stop brute-forcing short codes, not stealing real codes via deception.
- User/session-bound OTPs curb token substitution, yet if the attacker relays that entire session flow, verifier-binding protection is still needed.
- TLS to the real website secures transit between legitimate endpoints, yet the victim may hold an HTTPS connection **to the fake website itself**.
- CAPTCHA curbs automation, not users manually typing codes into fake sites.

Per **NIST SP 800-63B-4**, authenticator outputs requiring manual user entry (especially OTPs/out-of-band codes) **are not considered phishing-resistant**, because the output is not cryptographically bound to the authenticating verifier/session.

### Where are one-time OTP codes still useful?

OTPs still carry practical value, especially when a password leaks outside the website. They raise the bar over password-only, limit replay *after* consumption, and support legacy workflows. The issue is not that "OTPs are useless", but **never claiming OTPs resist real-time phishing**.

## 6. Why are WebAuthn/FIDO2 passkeys different from typed codes?

WebAuthn uses **public-key cryptography bound to a Relying Party ID (RP ID)**. The authenticator holds the private key, and the browser coordinates with the authenticator to produce a signed assertion over a fresh challenge. The server verifies using the **registered public key**.

~~~text
Credential registration:
  Browser at https://login.example.org
     → navigator.credentials.create()
     → authenticator creates credential for RP ID example.org
     → server stores credential ID + public key

Login:
  Browser gets fresh challenge from RP
     → navigator.credentials.get()
     → authenticator selects private key bound to exact RP ID
     → creates assertion containing authenticatorData + signature
     → RP verifies challenge/origin/rpIdHash/signature/flags
~~~

### 6.1. Verifier name binding

NIST calls this **verifier name binding**: the authenticator output is cryptographically bound to the verifier's identifier, typically a verified domain. A phishing site on another domain cannot simply ask the authenticator to sign a valid assertion for the real site's RP ID if browser, authenticator, and server follow WebAuthn rules properly.

### 6.2. Must verify properly on the server

WebAuthn is not secure merely by calling `navigator.credentials.get()`. The server must still verify:
1. `clientDataJSON.type = webauthn.get`.
2. `challenge` matches the request, is fresh, unexpired, and unused.
3. `clientDataJSON.origin` is in the exact scheme/host/port allowlist.
4. `authenticatorData.rpIdHash` matches the SHA-256 of the expected RP ID.
5. UP/UV flags meet policy, especially when user verification is required.
6. Credential ID exists, belongs to the right account, and is not revoked.
7. Signature validates against the **stored public key**, never a key taken arbitrarily from the request.
8. Account/session/authorization still satisfy policy.

**Note:** a passkey with proper user verification can satisfy multiple factors in one ceremony; yet never claim every WebAuthn assertion automatically qualifies as "MFA" without inspecting flags, policies, and assurance.

### 6.3. Limitations still remain

Phishing resistance in the **authentication ceremony** does not make the whole application immune to attacks:
- XSS on the real origin can act inside the session or steal readable data.
- Cookies/session tokens can still be stolen and replayed without protection.
- Weak account recovery can let attackers replace passkeys.
- Broken authorization on passkey enrollment pages can let others attach credentials.
- Malware/compromised devices or compromised passkey managers still pose risks.
- OAuth consent phishing can persuade users to grant permissions to another app even without leaking passwords/passkeys.

Therefore protect **origins, sessions, account lifecycles, authorization, and recovery**—do not stop at swapping passwords for passkeys.

## 7. Channel binding and certificates: another anti-phishing direction

Alongside WebAuthn's verifier name binding, NIST highlights **channel binding**: authenticator output cryptographically bound to the protected channel established with the verifier. Properly configured client-authenticated TLS is an example.

For example, in enterprise infrastructure: clients hold trusted issued private keys/certificates, and TLS client authentication proves key possession bound to the TLS channel's negotiation/messages. An OTP typed on a fake website **cannot substitute** for this private-key proof.

However:
- mTLS between **gateway and backend** does not prove the **end-user browser** performed a phishing-resistant factor.
- Sending `X-Client-Cert` from public browsers is not mTLS; trust results only from protected, sanitized proxies.
- Strong cryptography does not fix broken authorization, weak recovery, or hijacked sessions.
- Certificate config, chain verification, revocation, rotation, and client identity mapping remain operational responsibilities.

## 8. When should step-up authentication be required?

Not every request needs a heavy ceremony. Step-up should be driven by **action risk and authentication state**.

| Scenario | Suggested control |
|---|---|
| Reading low-sensitivity profile page | Valid session, permission check |
| Viewing sensitive transaction history | Fresh authentication or suitable assurance |
| Changing recovery email/phone | Recent reauthentication + passkey/MFA per risk |
| Changing password or disabling MFA | Fresh, strong auth, audit/notifications, and safe recovery |
| Adding/removing passkeys or authenticators | Step-up, account-binding checks, anti-CSRF |
| Creating long-lived API keys/refresh tokens | Fresh strong auth, scope limits, and audits |
| Deleting account, transferring funds, high-value payments | Strong auth and potentially **transaction-specific approval** |
| Login from unusual device/location | Risk-based step-up; avoid easily spoofed confirmations |
| Admin role changes, tenant privilege grants | Admin authorization + fresh phishing-resistant auth where fitting |

Policies must explicitly define:
- Which actions/routes require it.
- Which mechanism is required (`PASSWORD_REENTRY`, `MFA`, `PHISHING_RESISTANT`).
- Maximum freshness; e.g., 5 minutes is purely an **illustrative value**.
- Where proof is stored and which user/session/tenant it binds to.
- Expiration and revocation on logout, account switch, credential change, compromise, or session rotation.
- Whether binding to a specific transaction is required or session-wide suffices.

### Step-up must never rely on self-asserted headers

Wrong:

~~~http
POST /api/admin/change-email HTTP/1.1
X-MFA-Verified: true
X-Auth-Strength: high
~~~

Any HTTP client can set arbitrary headers. Right: the server or trusted IdP must **actually verify** the factor and record proof inside a protected session/token with verified provenance, timestamp, and assurance. If crossing a gateway, enforce trust boundaries/mTLS and strip Internet-originated headers.

## 9. Step-up authentication evidence must be bound

A server-side evidence record might contain:

~~~json
{
  "subjectId": "account-42",
  "sessionIdBinding": "server-internal-binding",
  "method": "WEBAUTHN",
  "phishingResistant": true,
  "verifiedAt": "2030-01-01T10:00:00Z",
  "expiresAt": "2030-01-01T10:05:00Z",
  "transactionId": null
}
~~~

This is a **descriptive structure**, not data clients may write into cookies/plain JSON. `method` and `phishingResistant` must be marked strictly from a **server-verified** ceremony/protocol result, never from a browser-sent `method=WEBAUTHN` parameter.

Distinguish clearly:
- **Server-side session proof:** the application server retains evidence and validates the session; combine with CSRF, session fixation protection, timeouts, and logout.
- **Signed identity token / OIDC ID Token:** claims such as `auth_time`, `acr`, `amr` can carry assurance info **only after signature/issuer/audience/nonce are verified** under a clear semantic contract with the IdP.
- **Frontend state:** `localStorage`, JS booleans, or hidden form inputs are mutable client data, never factor proofs.

Recent proof is not automatically **transaction approval**. If confirming "transfer amount X to account Y", bind approval to the exact content shown to the user and prevent post-approval payload tampering.

## 10. Integrating with IdP/OIDC: understanding `auth_time`, `acr`, `amr`

When Spring Security uses `oauth2Login()` or `oidcLogin` with an IdP, the app typically **does not verify passwords itself**. The IdP enforces MFA/step-up and emits evidence the RP can trust per contract.

- `auth_time`: user authentication timestamp per OIDC.
- `acr`: authentication context class reference, meaningful only under an **IdP policy contract**.
- `amr`: authentication methods references describing methods; values and emission depend on the provider.
- `max_age`: asks the IdP to enforce maximum authentication age per OIDC.
- `prompt=login`: may request a fresh login UI, yet does not by itself strengthen the method.
- `acr_values`: hints/requests context depending on provider; **not every IdP guarantees honoring it**.

**Proper flow:** after redirect, Spring/OIDC client validates the response and ID Token; the application verifies trusted claims indicate the required assurance level. If the IdP provides no trusted `acr` or lacks step-up support, the app **must not infer "MFA happened" from the login screen**.

Scenario:
1. User holds an OAuth2 Login session.
2. User chooses to change recovery email.
3. App asks the IdP for fresh authentication using a phishing-resistant method per the IdP's profile.
4. IdP runs the ceremony and returns matching ID Token/claims.
5. App verifies response, `auth_time`, `acr`/policy, and that subject matches the current user; only then does it allow the change.

**Warning:** never compare `acr == "high"` blindly without defining what that string guarantees; an IdP may use arbitrary strings for differing assurance levels. Also prevent account switching during step-up and manage sessions if the IdP returns a different subject.

## 11. Spring Security: where does step-up sit in the architecture?

Spring Security 6.x for Servlet provides:
- `SecurityFilterChain` to require route-based authentication/authorization.
- `AuthenticationManager`/`AuthenticationProvider` to verify credentials.
- `SecurityContext` to hold the logged-in principal.
- `AuthorizationManager<RequestAuthorizationContext>` to enforce custom access conditions.
- CSRF/session management and `AuthenticationSuccessHandler` for browser logins.
- `.webAuthn(...)` in Spring Security 6.5 for passkey login when matching dependencies are added.

**However:** `authenticated()` only states the request holds valid authentication; it **does not say whether login used MFA or a passkey**, nor does it provide a built-in "stepped up within 5 minutes" rule. That policy must read evidence from server-side verification or a trusted IdP.

### Suggested pipeline

~~~text
Browser → Spring Security session (logged-in user)
   |
   | POST /sensitive/action
   v
SecurityFilterChain
   |
   +--> Authentication still valid?
   |
   +--> Authorization: user has business permission?
   |
   +--> Server-side step-up proof:
   |      subject matches?
   |      assurance strong enough?
   |      timestamp still fresh?
   |      session/transaction binding valid?
   |
   +--> if insufficient → require reauthentication/step-up
   |
   +--> once sufficient → service checks resource/tenant and commits action
~~~

Step-up verification **does not replace** business permissions or IDOR/BOLA controls. A user authenticated with a passkey still cannot grant themselves admin roles or edit another account.

## 12. Standalone Java 17 example: distinguishing freshness, MFA, and phishing resistance

The sample below performs no real authentication; it is **a simulated policy program** runnable on JDK 17 with fixed stdout. Its purpose is preventing the misconception that "requested a code = phishing-resistant".

File `AssurancePolicyDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

public final class AssurancePolicyDemo {
    enum Method {
        PASSWORD,
        TOTP,
        SMS_OTP,
        WEBAUTHN_WITH_UV
    }

    record Evidence(
            String subject,
            Instant verifiedAt,
            Set<Method> methods) {
    }

    static boolean isMfa(Evidence evidence) {
        boolean password = evidence.methods().contains(Method.PASSWORD);
        boolean secondFactor = evidence.methods().contains(Method.TOTP)
                || evidence.methods().contains(Method.SMS_OTP);

        // A properly verified passkey with user verification may be
        // a multi-factor cryptographic authenticator.
        return (password && secondFactor)
                || evidence.methods().contains(Method.WEBAUTHN_WITH_UV);
    }

    static boolean isPhishingResistant(Evidence evidence) {
        return evidence.methods().contains(Method.WEBAUTHN_WITH_UV);
    }

    static boolean allowedForSensitiveAction(
            Evidence evidence,
            String subject,
            Instant now) {

        if (!evidence.subject().equals(subject)) return false;

        Duration age = Duration.between(evidence.verifiedAt(), now);
        return !age.isNegative()
                && age.compareTo(Duration.ofMinutes(5)) < 0
                && isPhishingResistant(evidence);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2030-01-01T10:00:00Z");

        Evidence passwordTotp = new Evidence(
                "alice",
                now.minusSeconds(60),
                Set.of(Method.PASSWORD, Method.TOTP));

        Evidence passkey = new Evidence(
                "alice",
                now.minusSeconds(60),
                Set.of(Method.WEBAUTHN_WITH_UV));

        Evidence stalePasskey = new Evidence(
                "alice",
                now.minusSeconds(600),
                Set.of(Method.WEBAUTHN_WITH_UV));

        System.out.println("password-totp-mfa=" + isMfa(passwordTotp));
        System.out.println("password-totp-resistant="
                + isPhishingResistant(passwordTotp));
        System.out.println("password-totp-accepted="
                + allowedForSensitiveAction(passwordTotp, "alice", now));
        System.out.println("passkey-accepted="
                + allowedForSensitiveAction(passkey, "alice", now));
        System.out.println("stale-passkey-accepted="
                + allowedForSensitiveAction(stalePasskey, "alice", now));
        System.out.println("wrong-subject-accepted="
                + allowedForSensitiveAction(passkey, "bob", now));
    }
}
~~~

Commands:

~~~bash
javac AssurancePolicyDemo.java
java AssurancePolicyDemo
~~~

**Exact stdout:**

~~~text
password-totp-mfa=true
password-totp-resistant=false
password-totp-accepted=false
passkey-accepted=true
stale-passkey-accepted=false
wrong-subject-accepted=false
~~~

This is strictly a **policy model**. In production, a string `WEBAUTHN_WITH_UV` in an HTTP request is not proof. `Evidence` must be constructed solely from thoroughly verified WebAuthn authenticator assertions/IdP tokens bound to the account and session. If the app supports mTLS or other phishing-resistant mechanisms, update predicates based on **real proofs**, never trusting client-supplied string lists.

## 13. Spring Boot 3.x + Spring Security 6.x demo: password reauthentication

This example illustrates **freshness and session proof**, not MFA. The password is re-entered before `POST /demo/change-email`; when valid, the server saves a timestamp in the session and allows access to the demo route for 5 minutes only.

**Security limitations to read first:** a password can be phished and relayed; a session hijacked after step-up can still be abused within the proof window; the demo endpoint **does not change a real email**. Production uses a WebAuthn step-up ceremony or trusted IdP assurance when phishing resistance is required. Never label a password re-entry example `phishingResistant=true`.

### 13.1. Project structure

~~~text
reauth-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/reauth/
    │   ├── ReauthDemoApplication.java
    │   ├── StepUpProof.java
    │   ├── FreshPasswordAuthorizationManager.java
    │   ├── SecurityConfiguration.java
    │   └── StepUpController.java
    ├── resources/
    │   ├── application.yml
    │   └── templates/step-up.html
    └── ...
~~~

### 13.2. `pom.xml`

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
    <artifactId>reauth-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

### 13.3. `application.yml`

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

Supply the password via environment variable when running the demo; never commit real passwords or use test credentials in Internet-exposed environments.

### 13.4. `ReauthDemoApplication.java`

~~~java
package com.example.reauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReauthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReauthDemoApplication.class, args);
    }
}
~~~

### 13.5. `StepUpProof.java`: info stored strictly in server session

~~~java
package com.example.reauth;

import java.io.Serializable;
import java.time.Instant;

public record StepUpProof(
        String username,
        Instant verifiedAt
) implements Serializable {
    public static final String SESSION_KEY = "demo.reauth.proof";
}
~~~

A session attribute is not a JWT and is never accepted from client-sent bodies/headers. This proof record **only has `password re-entry` strength**, with no field pretending it is MFA. In multi-instance deployments, the session store needs proper integrity, TTLs, and access controls.

### 13.6. `FreshPasswordAuthorizationManager.java`

~~~java
package com.example.reauth;

import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class FreshPasswordAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private static final Duration MAX_AGE = Duration.ofMinutes(5);

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        if (current == null || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        HttpSession session = context.getRequest().getSession(false);
        Object stored = session == null
                ? null : session.getAttribute(StepUpProof.SESSION_KEY);

        if (!(stored instanceof StepUpProof proof)) {
            return new AuthorizationDecision(false);
        }

        Instant now = Instant.now();
        Duration age = Duration.between(proof.verifiedAt(), now);

        boolean allowed = proof.username().equals(current.getName())
                && !age.isNegative()
                && age.compareTo(MAX_AGE) < 0;

        return new AuthorizationDecision(allowed);
    }
}
~~~

**Strengths of this structure:** evidence does not come from client-asserted headers, carries subject and expiration, and the sensitive route uses Spring Security's `AuthorizationManager`. **Limitations:** the check only requires password re-entry—it does not prove MFA, does not prove the user is on the real domain, and is not bound to specific transaction contents.

### 13.7. `SecurityConfiguration.java`

~~~java
package com.example.reauth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

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
        var user = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        var defaultSuccess =
                new SavedRequestAwareAuthenticationSuccessHandler();
        var fresh = new FreshPasswordAuthorizationManager();

        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .requestMatchers(HttpMethod.POST,
                                "/demo/change-email").access(fresh)
                        .anyRequest().authenticated())
                .formLogin(form -> form.successHandler(
                        (request, response, authentication) -> {
                            var session = request.getSession(false);
                            if (session != null) {
                                session.removeAttribute(
                                        StepUpProof.SESSION_KEY);
                            }
                            defaultSuccess.onAuthenticationSuccess(
                                    request, response, authentication);
                        }))
                .build();
    }
}
~~~

- `DaoAuthenticationProvider` checks passwords using `PasswordEncoder`, never plaintext string comparison.
- `formLogin` builds the default login page. The success handler clears old proof so **a new login never inherits an old step-up**, then invokes default redirect behavior.
- `POST /demo/change-email` requires fresh proof; not just `authenticated()`.
- Default CSRF **remains enabled** for POSTs; session fixation and logout are managed by Spring. Never disable CSRF just to skip putting tokens in forms.
- Remaining routes require login; this is a local demo lacking production account/tenant/role policies.
- Production systems must also invalidate proofs on credential change, account revocation, security/session events, or assurance changes.

### 13.8. `StepUpController.java`: rechecking current password

~~~java
package com.example.reauth;

import java.time.Instant;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class StepUpController {

    private final AuthenticationManager manager;

    public StepUpController(AuthenticationManager manager) {
        this.manager = manager;
    }

    @GetMapping("/step-up")
    public String form() {
        return "step-up";
    }

    @PostMapping("/step-up")
    public String verifyAgain(
            @RequestParam("password") String password,
            Authentication current,
            HttpServletRequest request) {

        try {
            Authentication checked = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            current.getName(), password));

            if (!checked.isAuthenticated()
                    || !checked.getName().equals(current.getName())) {
                return "redirect:/step-up?error";
            }

            // This is recent PASSWORD proof only, not MFA.
            request.getSession(true).setAttribute(
                    StepUpProof.SESSION_KEY,
                    new StepUpProof(current.getName(), Instant.now()));
            return "redirect:/me";
        } catch (AuthenticationException ex) {
            return "redirect:/step-up?error";
        }
    }

    @GetMapping("/me")
    @ResponseBody
    public Map<String, Object> me(Authentication authentication) {
        return Map.of("username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }

    @PostMapping("/demo/change-email")
    @ResponseBody
    public Map<String, String> simulateSensitiveAction() {
        // Illustrates authorization only; NO email is changed.
        return Map.of("result", "recent password proof accepted");
    }
}
~~~

**Code limitations:** the `POST /step-up` endpoint needs **rate limiting**, anti-automation, safe logging, generic errors, and proper session/cookie mechanisms in real deployments. The demo does not handle password reset, phishing resistance, MFA, or business transactions. Never treat a password re-entered in this request as WebAuthn evidence.

### 13.9. `templates/step-up.html`

File `src/main/resources/templates/step-up.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Re-verify with password</title>
</head>
<body>
  <h1>Re-verify with password</h1>
  <p>This example only asks to re-enter the password,
     it is not MFA and is not phishing-resistant.</p>
  <p th:if="${param.error}">Could not verify. Please try again.</p>
  <form th:action="@{/step-up}" method="post">
    <label for="password">Current password</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Re-verify</button>
  </form>
</body>
</html>
~~~

The hidden CSRF token is issued and verified by Spring Security, not MFA proof. Never let the frontend inject `verifiedAt` or `method` into the session. Production pages must enforce HTTPS, CSP, anti-XSS/clickjacking, and no untrusted third-party scripts.

### 13.10. Running and expected results

Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD='local-demo-password-only'
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "local-demo-password-only"
mvn spring-boot:run
~~~

This is a test password for localhost, **never use it on the Internet or commit it to source**.

Steps:
1. Visit `http://localhost:8080/login`, log in as `alice` with the demo password.
2. Before step-up, a CSRF-valid POST to `/demo/change-email` returns **403 Forbidden** due to missing fresh proof.
3. Open `/step-up`, enter the right current password. The controller re-verifies via `AuthenticationManager` and stores `StepUpProof` server-side.
4. POST `/demo/change-email` within 5 minutes, with valid session + CSRF, returns JSON like:

~~~json
{"result":"recent password proof accepted"}
~~~

5. After at least 5 minutes from `verifiedAt`, the same action gets **403**. Wrong passwords grant no proof.
6. Logout or a new login must not reuse old proofs. Test another browser session too.

There is no simple `curl` one-liner because form login/step-up use CSRF tokens and session cookies; test via a browser or `MockMvc` integration tests preserving state. **The demo proves password freshness only**, making zero phishing-resistance guarantees in this example.

## 14. Moving from reauthentication demo to phishing-resistant step-up

Changing `new StepUpProof(username, Instant.now())` to `method="WEBAUTHN"` is not enough. You must **change the proof-issuing source**:

1. User holds a session and wants to perform a sensitive action.
2. Server requests a fresh WebAuthn assertion for the right RP ID, generating a CSPRNG challenge bound to session/user and TTL.
3. Browser calls `navigator.credentials.get({publicKey: ...})` with an enrolled credential.
4. Server verifies challenge, `clientDataJSON.type`, origin, RP ID hash, UP/UV, credential ID, signature, and account mapping using a vetted WebAuthn library.
5. **Only upon verification success** store evidence `method=WEBAUTHN`, `verifiedAt`, `subject`, and `session binding`.
6. `AuthorizationManager` requires **the exact method/assurance, freshness, and session**, not just a timestamp.
7. When changing payout targets/emails, consider proof bound to `transactionId` and action payload.

Spring Security 6.5 provides passkey login via the `webAuthn` DSL and `webauthn4j-core`. Basic config:

~~~java
// Illustrative snippet used inside Servlet HttpSecurity:
http
    .formLogin(org.springframework.security.config.Customizer.withDefaults())
    .webAuthn(webAuthn -> webAuthn
        .rpId("example.org")
        .allowedOrigins("https://login.example.org"));
~~~

The config above **enables passkey registration/login**; it **does not automatically enforce step-up on every endpoint** or emit `WEBAUTHN` proofs as in section 13. For step-up assertions inside an already-logged-in session, use a version-supported integration/ceremony or design additional challenge/verification/repository/authorization flows. Never write custom WebAuthn signature verification by ad-hoc JSON parsing.

When using an IdP, the app should request step-up at the IdP and verify `acr`/`auth_time`/subject after callback. Never let client websites self-assert WebAuthn completion.

## 15. Protecting sessions and cookies after MFA

Phishing-resistant login protects the **authentication ceremony**, yet applications typically rely on session cookies or access tokens as **bearer credentials** after login. Anyone stealing a valid session can still wield its privileges without extra controls.

Defenses:
- HTTPS/TLS, `Secure`, `HttpOnly`, appropriate `SameSite` cookies, narrow path/domain.
- Defenses against XSS, CSRF, and clickjacking; CSP and third-party script/resource controls.
- Session fixation protection on login, idle/absolute timeouts, and server-side logout.
- Token/session revocation on compromise detection or password/credential changes.
- Short-lived step-up evidence, cleared on logout/new login and sensitive to account changes.
- For high-value actions, re-prompt a strong factor and confirm action contents rather than trusting general sessions alone.
- Never log `Cookie`, `Authorization`, raw OTPs, recovery codes, or session IDs.
- For SPAs and OAuth, minimize token exposure in JS/storage and evaluate Backend-for-Frontend (BFF) architectures.

**Do not conflate:** phishable typed OTP codes and stolen session cookies are **two separate risks**. WebAuthn reduces one risk yet does not replace all session-protection controls.

## 16. Enrollment, recovery, and fallbacks are frequently overlooked weak spots

### 16.1. Adding a new device can be riskier than logging in

If an attacker obtains an insufficiently secured session and can enroll their own MFA/passkey onto the victim's account, future logins can be taken over without the old password. Therefore adding/removing authenticators needs:
- Sufficiently strong fresh reauthentication/step-up;
- Account-binding verification, never trusting form-supplied user IDs;
- CSRF protection, audits, and notifications to verified contacts;
- Session/credential revocation after unusual changes;
- Blocking removal of the last strong factor without a controlled recovery flow.

### 16.2. Recovery must not unconditionally downgrade

A system advertising "phishing-resistant MFA" that lets anyone knowing an email and SMS OTP disable passkeys and sign in may fail its overall target assurance.

Recovery policies should:
- use verification factors/paths commensurate with risk;
- limit attempts, enforce audits/notifications, and add delays where needed;
- check for SIM swaps, email account takeovers, and link scanners;
- never auto-strip MFA when a user clicks "I don't have my device" without independent verification;
- place accounts under review or apply transaction limits after high-risk recovery.

### 16.3. Downgrade via legacy protocols

A system running WebAuthn on a new web UI while leaving:
- an HTTP Basic password-only legacy API;
- a mobile endpoint skipping MFA;
- weak password login/admin fallbacks;
- an OIDC login flow not verifying `acr` after step-up;

lets attackers pick **the weakest path**. Inventory all entry points, retire obsolete protocols, and enforce uniform assurance for sensitive actions regardless of channel.

## 17. User behavior and product design supporting phishing defense

Technical controls should pair with UX:
- Guide users to sign in via bookmarks/trusted apps; password managers usually refuse to autofill on fake domains.
- Display exact domain/system names and avoid unnecessary URL shorteners in security emails.
- Never ask users to share OTPs/recovery codes in chat/support.
- Distinguish user-initiated push approvals from unexpected prompts; use number matching if deploying push, curbing fatigue.
- Display new device/session info and support revocation.
- Let users view and manage passkeys/MFA methods with safe backups.
- Send alerts for sensitive changes (password, email, auth factors).
- Never treat "passed CAPTCHA" as proof of legitimate ownership.
- Reduce false positives for accessibility and shared-device users while keeping anti-automation controls.

**User training has value, yet does not replace anti-phishing protocols.** The goal is reducing dependence on users spotting visually identical spoofed pages.

## 18. Scenarios before and after upgrading authentication

### Scenario A: password alone

~~~text
Password entered on fake site
   → attacker gets password
   → real login may succeed
~~~

Baseline defenses: password managers, unique passwords, breached-password screening, rate limiting, login alerts, MFA.

### Scenario B: password + TOTP

~~~text
Password and OTP entered on fake site
   → attacker relays both near real-time
   → session hijacking remains possible
~~~

Better than password-only when a password leaks alone, yet not immune to real-time phishing. Protect extra factors, sessions, and migrate toward WebAuthn.

### Scenario C: properly configured WebAuthn passkey

~~~text
Fake site has different RP ID
   → browser/authenticator refuses to sign a valid
      assertion for the real RP domain via the fake site
   → attacker cannot simply relay a typed OTP
~~~

Origin/RP ID validation, post-login session protection, account recovery, and XSS prevention remain necessary.

### Scenario D: step-up before email change

~~~text
Normal session (logged in)
   → requests email change
   → server requires fresh strong authentication
   → verifies via WebAuthn/IdP assurance
   → account & target contact policy
   → commits change, audits & notifies
~~~

If the system only asks to re-enter the password, that is **fresh password evidence**; while reducing risk from unattended sessions, it **creates no phishing resistance**.

## 19. Security testing matrix

| Test case | Expected result |
|---|---|
| Valid password on fake site | Never treat password as phishing-resistant proof |
| Valid password + TOTP relayed | Risk of compromise; detect/mitigate and migrate to WebAuthn |
| Expired or already-used TOTP | Rejected; proper single-use and TTL |
| Consecutive wrong OTPs | Rate limit/attempt cap, safe logging |
| Successful password re-entry | Creates **fresh password proof** only, never grants MFA |
| Another account's reauth proof | Rejected for current account |
| Expired reauth proof | Sensitive route returns 403/step-up required |
| New login while old session holds proof | Old proof cleared/unusable |
| Logout then replay old cookie | No valid session established |
| Client sends `X-MFA-Verified:true` | Grants no privileges |
| Spoofer sends `acr=high` in query | Untrusted; verify trusted IdP token |
| OIDC subject changes after step-up | Never attach proof to old account |
| OIDC `acr` fails policy | Sensitive action denied |
| OIDC token wrong issuer/audience/nonce | Rejected in OIDC flow |
| Stale/wrong WebAuthn challenge | Assertion rejected |
| Wrong WebAuthn origin/RP ID hash | Rejected |
| Tampered WebAuthn signature | Rejected |
| Missing WebAuthn UV when policy requires | Rejected |
| Revoked credential or disabled account | Rejected |
| Password-only login on phishing-resistant route | Rejected despite authenticated session |
| Account recovery via weak path | Never auto-downgrade overall policy assurance |
| Session cookie leaked after MFA | Revoke/detect/reauth before sensitive actions |
| Email change on another tenant | Denied by authorization/object-level policy |
| Modifying transaction payload after approval | Transaction-bound proof becomes invalid |
| Login from new IP/device | Risk-based step-up and proper logging |
| XSS/clickjacking on real origin | CSP, anti-XSS/CSRF/framing, and independent tests |
| Credentials/MFA recovery codes in logs | Redacted, never returned to clients |

**Tests must separate layers:** JUnit tests pure policies; `MockMvc` tests endpoints/CSRF/sessions; integration tests with IdPs and WebAuthn libraries test cryptographic ceremonies. Never infer "phishing-resistant" merely because a mocked principal holds an `MFA` authority or an API returns 200.

## 20. Common mistakes

1. **Equating MFA with phishing resistance:** password+TOTP can be MFA yet remains vulnerable to relaying.
2. **Assuming short-lived OTPs cannot be stolen:** attackers use real codes within their TTL window.
3. **Using two passwords and calling it two factors:** still the same factor type.
4. **Treating push number matching as equivalent to WebAuthn:** curbs fatigue better, yet lacks cryptographic verifier binding.
5. **Trusting `mfa=true` flags from frontend/headers:** must be issued after real verification at a trusted server/IdP.
6. **Using `authenticated()` instead of assurance checks:** cannot tell password-only from passkeys.
7. **Trusting `acr` without an IdP contract:** semantics vary by provider; inspect tokens and profiles.
8. **Not checking `auth_time`/freshness:** a days-old session could pass sensitive actions.
9. **Not binding step-up to subject/session:** account A's evidence applied to B.
10. **Not revoking step-up proof on logout/new login:** old proofs get reused.
11. **Treating password reauth as phishing-resistant:** passwords remain secrets typeable on fake sites.
12. **Skipping CSRF on browser POST reauth:** attackers abuse session/context.
13. **Putting credentials/OTPs into logs:** observability turns into a leak source.
14. **Skipping business permissions after step-up:** strong proof does not let users edit other accounts' data.
15. **Enabling passkeys alongside weak recovery:** attackers seize accounts via passkey-free paths.
16. **Trusting any `https` website as real:** fake sites also get valid HTTPS certs for spoofed domains.
17. **Skipping RP ID/origin checks in WebAuthn verifiers:** breaks the phishing-resistance model.
18. **Using WebAuthn passwordless login as automatic step-up proof:** check ceremony, freshness, and account binding per policy.
19. **Assuming MFA stops session theft:** MFA primarily protects authentication; sessions still need defense.
20. **Not verifying approved action contents:** fresh authentication does not prove approval of every transaction.
21. **Not measuring false positives when raising step-up:** frustrates users or pushes them onto weak recovery paths.
22. **Leaving legacy endpoints bypassing MFA:** every sensitive entry point needs consistent policy.

## 21. Production checklist

- [ ] Inventoried authentication entry points (web, mobile, admin, API, IdP, legacy).
- [ ] Classified passwords, SMS/TOTP, push, and WebAuthn by assurance, not marketing labels.
- [ ] Phishing-resistant mechanisms available for high-risk accounts/actions as needed.
- [ ] WebAuthn verifies challenge, origin, RP ID, signature, UP/UV, and account binding.
- [ ] MFA enrollment, removal, reset, and account recovery enforce step-up/audits/notifications.
- [ ] Never grant authority from unverified `mfa=true` or `acr`.
- [ ] IdP `auth_time`, `acr`, `amr` have semantic contracts and are verified.
- [ ] Freshness and assurance are both enforced **server-side**, bound to the right subject/session.
- [ ] Sensitive business actions enforce separate tenant/object authorization.
- [ ] Step-up proofs have TTLs and invalidate on logout/login/revocation/credential compromise.
- [ ] Sensitive transactions bind approval to exact contents and resist post-approval tampering when required.
- [ ] Cookies/sessions/TLS/CSP/CSRF/XSS protected, with session fixation defenses.
- [ ] OTPs enforce TTL, attempt caps, single-use, anti-spam, and no logging.
- [ ] Rate limiting and detection cover follow-up phishing, OTP abuse, and MFA fatigue.
- [ ] Post-MFA session takeover detection with alerts and revocation procedures.
- [ ] No assurance bypasses via legacy Basic, password fallbacks, or uncontrolled recovery.
- [ ] Negative tests run: wrong domain, replay, wrong subject, stale proof, fake headers, weak recovery.
- [ ] User and support guidelines forbid asking for passwords/OTPs/recovery codes.

## 22. Key takeaways

**MFA answers "how many independent proof types"; phishing resistance answers "does the protocol stop sending proof to an impostor verifier".** Those are two distinct questions.

- Passwords, SMS OTPs, email OTPs, TOTPs, and recovery codes are secrets or outputs that can be re-entered and relayed.
- Single-use/short-TTL OTPs stop certain abuses, yet do not prevent **real-time relaying**.
- Password reauthentication boosts freshness, **is not MFA, and is not phishing-resistant**.
- WebAuthn/FIDO2 uses public keys bound to RP ID/origin and challenges to curb ceremony phishing when verified properly by the server.
- Authorization, session bounds, real step-up, enrollment/recovery controls, and post-login protection remain essential.
- Spring Security provides the foundation for authentication/authorization/sessions, while assurance/step-up policies must be reliably designed, issued as evidence, and verified.

## 23. References

1. [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): phishing resistance, verifier name binding, channel binding, OTPs, and MFA.
2. [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA factors, OTPs, push fatigue, phishing-resistant passkeys, and recovery.
3. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, risk-based authentication, generic errors, and sessions.
4. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session hijacking, cookie protection, and timeouts.
5. [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): login abuse and defensive MFA.
6. [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/): origin, RP ID, registration, assertions, and protocol checks.
7. [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): WebAuthn integration in Spring Security.
8. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` and endpoint rules.
9. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter`, handlers, and `SecurityContext`.
10. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `auth_time`, `acr`, `amr`, `max_age`, and authentication request/ID Token claims.
