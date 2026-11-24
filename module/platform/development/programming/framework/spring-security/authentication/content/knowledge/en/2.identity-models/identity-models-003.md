# Credentials and Sensitive Data Lifecycle Boundaries

In Spring Security's identity model, a **credential** is what a subject presents for the system to verify control over an account, key, session, or service identity. Passwords, OTP codes, API keys, bearer tokens, and session cookies differ in how they are verified, yet share one risk: if they appear in the wrong place or live too long, someone else can use them to impersonate the subject.

Sensitive data lifecycle boundaries answer concrete questions: **Who is allowed to create and receive the data? Which components may it pass through? Where and for how long is it stored? When must it be erased, expired, rotated, or revoked? Who may know the authentication outcome without knowing the original credential?** This lesson places those questions inside the Spring Security authentication flow; its focus is protecting credentials and sensitive data across their lifecycle, not designing the entire authorization rule set.

## 1. Objectives

After this lesson, you will be able to:

1. Distinguish identifiers, raw credentials, verified proof, the `Authentication` result, derived credentials, and sensitive personal data.
2. Map the lifecycle from issuance → transit → verification → use → storage → rotation/revocation → expiration and deletion; place trust boundaries at each stage.
3. Explain why raw passwords, session IDs, tokens, and keys must never be stored/logged; understand password hashing, the limits of encryption, masking, and memory clearing.
4. Understand `PasswordEncoder`, `AuthenticationManager`/`ProviderManager`, `CredentialsContainer`, `eraseCredentials()`, and `SecurityContext` in Spring Security Servlet applications.
5. Choose sound lifecycle policies for passwords, OTPs, access/refresh tokens, sessions, signing keys, and service secrets; know how to test expiration, revocation, leakage, and replay scenarios.

## 2. Which Data Is a Credential? Do Not Equate Every Identity Field

| Data | Role | Is it a secret used for authentication? | Safe handling |
| --- | --- | --- | --- |
| `username`, account ID | Identifier to locate the subject | Usually not, though it may be personal data | Do not treat knowing a username as being authenticated; limit identifier exposure. |
| Raw password, account recovery codes | Secret proving control | **Yes** | Process only long enough to verify/change; never log or store in plaintext. |
| OTP/TOTP codes | Short-lived, potentially single-use proof | **Yes**, within the valid window | Enforce time/retry limits, prevent replay; never write to logs. |
| Private key/passkey private key, API key, client secret | Means to sign/prove identity or call a service | **Yes** | Keep only in authorized components; protect private keys, enforce least privilege, rotate/revoke. |
| Salted password hash with algorithm parameters | Stored verifier for checking passwords | Not used directly as a password with a standard verifier, **yet highly sensitive** | Protect DB, backups, and read access; resist offline password-guessing attacks. |
| Bearer access token | Proof carrying access rights to an API | **Yes while valid**: anyone holding it can use it | Narrow lifetime/scope/audience, protect in transit and memory, never log. |
| Refresh token | Proof to request new access tokens | **Yes, often more sensitive than short-lived access tokens** | Store safely per client type, rotate, and detect replay by design. |
| Session ID / session cookie | Session identifier resuming an authentication result | **Yes while valid** | Set cookie `Secure`/`HttpOnly`/`SameSite` per risk, enforce session timeout and invalidation. |
| JWT claims, email, phone number, full name | Information describing the subject/attributes | Not necessarily a credential, though it may be PII | Collect/expose only as needed, enforce read permissions, protect at rest. |
| Public key/JWKS | Used to verify signatures | Typically **not** a secret | Must still validate key source, issuer, algorithm, freshness, and trust bindings. |

**A secret can also be a credential, yet not every piece of sensitive data is a credential.** For example, a user's email can be PII even though it is not enough to log in. Conversely, a session ID is an unguessable string that may contain no username yet is sufficient to hijack a session if leaked.

Distinguish three states:

- **Client-presented value:** `Authorization` header, password, OTP, cookie, a JSON field, or a client certificate. This is **unverified input**, not a trusted conclusion.
- **Verified proof:** the result of matching a password, verifying a signature/challenge, or confirming a valid, scoped session. You must check issuer, lifetime, and intended purpose.
- **Result used by business logic:** an authenticated `Authentication` with appropriate principal and authorities. Business services should receive the needed identity/authorization result, **never the password/OTP/raw bearer token**.

A secret might not appear in business method parameters yet still leak if a gateway logs all HTTP headers, an exception prints the request object, APM captures bodies, or a platform copies environment variables into diagnostic dumps.

## 3. Lifecycle Map: Which Boundaries May Data Cross?

```text
[Credential creation/issuance]
           |
           | (1) Enrollment: verify ownership, issue over an appropriate channel
           v
[User / device / secret store]
           |
           | (2) TLS; form login / Authorization header / cookie / mTLS
           v
[Reverse proxy / load balancer] -- (5) --> [Logs/APM/traces: filtered metadata only]
           |
           | (3) forwarding rules; do not trust self-asserted headers
           v
[Spring Security: filters / AuthenticationManager / token verifier]
           |                                |
           | (4) look up password hash      +--> [Trusted Issuer/JWKS/introspection]
           +-----------> [User store]
           |
           v
[Verified Authentication / SecurityContext]
           |
           +--> [Authorization + business service receiving principal/scopes]
           |
           +--> [Session store if stateful design]
           |
           v
[Timeout / logout / rotate / revoke / delete]
```

For every arrow, specify **source, destination, access permissions, transport protection, minimal data, lifetime, and destruction/revocation method**:

1. **Issuance:** only an authorized source creates credentials; random secrets need adequate entropy, scoped permissions, and environment isolation. Never embed private keys, service passwords, or production tokens in source code.
2. **Transit:** use TLS and proper endpoints. Ensure proxies, gateways, ingress controllers, and service meshes do not record `Authorization`, `Cookie`, request bodies containing passwords, or sensitive query strings.
3. **Acceptance:** the server verifies via the appropriate mechanism. Clients must never elevate privileges via `userId`, `role`, or `X-Authenticated-User` fields; proxies may forward authenticated identities only when a clear trust chain is established.
4. **Transformation:** the raw credential lives only long enough for verification; the output is principal/scopes/authorities for business logic, never a copy of the password. The password hash stays in the user store for future authentications.
5. **Observability:** logs/traces record only useful events such as normalized principal ID, authentication type, outcome, request ID, and sanitized rejection reason; never write secrets or credential-bearing payloads to long-lived observability stores.
6. **Termination:** logout, account disablement, password reset, token expiry, and key rotation have **different termination points**. Deleting a string on the client **does not automatically invalidate** a session/token the server still accepts.

### Setting Time Boundaries

**Credential lifetime** is not synonymous with **authentication result lifetime**:

- A password is entered at time T0, verified against its hash, and the raw value is discarded; a session may retain the logged-in state until T1.
- A short-lived access token may remain usable until `exp` if the system lacks immediate revocation.
- A refresh token may outlive an access token, so it requires stronger protection and rotation/reuse-detection design.
- Whether locking an account or changing roles at T2 takes effect immediately depends on status-check points and freshness policy; never assume the system automatically revokes every issued JWT.
- Data written to backups, crash dumps, or logs has its own lifecycle; clearing a Java variable or deleting a DB row does not erase all copies.

## 4. Password: From Transient Secret to Durable Verifier

### 4.1 Entry and Verification

1. The user submits a password via a form or HTTP Basic over **HTTPS**. Inside the request, the password is plaintext at the application layer once TLS is terminated, so gateways, filters, tracing, and error handlers can still see it.
2. The application locates the account by identifier and loads the stored **password hash**. The hash is not the password and must not be sent to the client; even so, leaking hashes can still allow offline password-guessing attacks.
3. Spring Security compares using `PasswordEncoder.matches(rawPassword, encodedPassword)`. A suitable password-hashing algorithm must resist brute-force attacks using a salt and appropriate cost factor; **plain SHA-256 or reversible encryption alone is not how passwords are stored**.
4. If valid, the server builds an authentication result and attaches the principal/authorities; the raw password has **no business reason to be placed into `SecurityContext`, responses, a message bus, or logs**.
5. On password change/reset, verify authorization or ownership through a secure mechanism, store the new hash, handle old sessions/tokens according to policy, invalidate the used reset token, and emit an audit event without the password.

**`PasswordEncoder` protects passwords at rest; TLS protects them in transit; log/memory controls restrict where passwords appear.** These are three separate layers of defense. Never substitute one layer for another.

Spring Security provides `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, which creates a `DelegatingPasswordEncoder` supporting the `{id}encodedValue` format and verifying algorithms configured by ID, aiding planned migrations of legacy hashes. For example, `{bcrypt}$2a$...` is a password hash with an algorithm-identifying prefix; `{noop}plain` is only for samples or special legacy data and is **unsafe for real passwords**. Hashing cost must be tuned to the environment and DoS resilience.

**Do not force all users to rotate passwords periodically without cause.** Under modern guidance, require changes when compromise is evidenced/suspected, an account is taken over, or a specific compliance/business rule demands it; combine with phishing-resistant MFA, block known-breached passwords, and rate-limit login attempts. "Forcing more password changes" does not compensate for weak storage or verification.

### 4.2 Hash, Salt, Pepper, and Key Are Not the Same

- **Salt** is a per-password-record random value, typically stored alongside the hash, defeating shared lookup tables; the salt **need not be secret**.
- **Password hash** is derived from the password, salt, and algorithm parameters (such as bcrypt or Argon2id depending on policy and library support). Hashes still need protection because they can be attacked offline.
- **Pepper** (if used in an architecture) is an extra secret managed outside the database, not built into every `PasswordEncoder` by default; the design must handle pepper rotation and exposure risk.
- **Encryption key** encrypts/decrypts data that must be recovered; never use reversible encryption in place of password hashing for user passwords. Secrets that genuinely must be retrieved, such as credentials for calling external systems, belong in a vault/KMS with explicit access controls.

### 4.3 Limits Inside the Java Heap

For secrets read from a terminal or a buffer-supporting library, minimize copies, narrow their lifetime, and clear **buffers you own** after use. However, `String` is immutable: there is no standard API to reliably wipe copies in the heap; body parsers, frameworks, logs, debuggers, or GC may retain other copies. Never claim `Arrays.fill(char[], '\0')` provides complete zeroization.

Standalone, compilable Java 17+ example to understand the scope of clearing **one specific buffer**. File `SecretBufferDemo.java`:

```java
import java.util.Arrays;

public final class SecretBufferDemo {
    public static void main(String[] args) {
        char[] demoSecret = {'d', 'e', 'm', 'o'};
        try {
            System.out.println("characters=" + demoSecret.length);
            // Illustrates using the buffer. Do not print the secret value.
        } finally {
            Arrays.fill(demoSecret, '\0');
        }
        boolean cleared = true;
        for (char value : demoSecret) {
            if (value != '\0') {
                cleared = false;
            }
        }
        System.out.println("owned-buffer-cleared=" + cleared);
    }
}
```

Compile and run:

```bash
javac SecretBufferDemo.java
java SecretBufferDemo
```

Exact stdout:

```text
characters=4
owned-buffer-cleared=true
```

This is **only a demonstration of clearing a self-managed array**, not an authentication class and not proof that no secret copy remains in process memory. In typical Spring Security applications, standard mechanisms may use `String`/`CharSequence` internally; avoid creating extra copies unnecessarily and never log those values.

## 5. Credential Erasure in Spring Security: Useful Yet Bounded

A typical Servlet username/password login flow has these steps:

```text
UsernamePasswordAuthenticationFilter / authentication filter
  -> Authentication requesting verification (holds input credential)
  -> AuthenticationManager, typically ProviderManager
  -> DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
  -> Successful Authentication (principal + authorities)
  -> ProviderManager attempts to erase credentials on the result
  -> SecurityContextHolder holds the result for the current request
  -> repository saves/restores context across requests if stateful
  -> authorization to access controller/service
```

This models the username/password flow; HTTP Basic, form login, OAuth2 resource servers, and custom filters have different entry points, providers, and context storage mechanisms. **Do not infer that every mechanism goes through the same `DaoAuthenticationProvider`.**

Key APIs:

- `Authentication.getCredentials()` holds the data used to authenticate *depending on the stage and token type*. After successful authentication it may be erased or meaningless; do not let business logic depend on this value.
- `CredentialsContainer.eraseCredentials()` is the contract for objects holding credentials that should be cleared. Many built-in types such as `UsernamePasswordAuthenticationToken` and `User` implement it.
- `ProviderManager` by default attempts to erase credentials on the successful `Authentication` object **if** it implements `CredentialsContainer`. This is not a promise that all references, HTTP bodies, request logs, or memory copies are erased.
- `SecurityContextHolder` holds the `SecurityContext` for the current execution context. For Servlets, the default strategy is `ThreadLocal`-based, and the framework manages loading/clearing within the filter lifecycle. Never store a raw password in principal/details/session expecting the manager's erasure behavior to clean it up.
- `SecurityContextRepository` determines how the context is persisted per configuration. Succeeding at authentication in one request **does not by itself prove** the result was saved securely or will remain valid on the next request.
- A custom `AuthenticationProvider` should return an authenticated object **free of unnecessary sensitive data**; custom tokens holding credentials need proper erasure support. Avoid copying raw credentials into `details` or attached metadata.

### Real-World Pitfall: Shared `UserDetails` Reference in a Cache

Suppose a custom provider puts the exact `UserDetails` instance retrieved from a cache into `Authentication.principal`. When `eraseCredentials()` is called, the password on that `UserDetails` may also be cleared; **if it is the same cached object**, the next authentication attempt may no longer have a hash to match against. Good design keeps a clear boundary between the verifier record in the cache/store and the principal returned to the request, cloning/copying as needed, and testing it for real. Do not set `eraseCredentialsAfterAuthentication=false` merely to "patch" a cache bug while giving up a layer of protection.

Distinguish:

- **Erasing from the authentication result:** reduces retention of raw credentials inside Spring Security objects.
- **Clearing `SecurityContext`:** manages per-request/thread state, usually handled by filters; thread-managing code/tests may need `SecurityContextHolder.clearContext()` in the right place.
- **Invalidating sessions/revoking tokens:** security actions involving the server and issuer, never accomplished merely by clearing a Java variable.

**Only create an `Authentication` in an authorized authentication component.** Never read `X-User`/`role` from a request and construct an `authenticated=true` token as a shortcut. Credential erasure does not fix blindly trusting client-supplied data.

## 6. Session, Access Token, and Refresh Token: Three Distinct Lifecycles

### 6.1 Cookie-Based Sessions

After successful login, a stateful application can keep authentication state on the server and place a session ID in a cookie. The cookie is a **bearer credential** for subsequent requests, not a copy of the password. Design requirements:

- Session ID must be sufficiently unpredictable; rotate the session ID at login to mitigate session fixation using the appropriate mechanism and configuration.
- Cookie `Secure` so it travels only over HTTPS, `HttpOnly` to prevent direct JavaScript reads, `SameSite` to help mitigate certain cross-site flows; scope `Domain`/`Path` tightly.
- Enforce idle timeout, absolute timeout if policy requires, concurrent session limits, server-side logout/invalidation, and re-login policies when credentials change.
- Protect against CSRF for flows relying on auto-sent cookies; `HttpOnly` and `SameSite` **do not replace** comprehensive CSRF, XSS, or object-level authorization defenses.
- In distributed systems, session stores/replication have their own lifecycle and access controls; never put raw passwords in session attributes for "later convenience".

**Warning sign:** after testing logout, the cookie disappears from the browser, yet replaying the old cookie still accesses the endpoint. That proves server-side validity was not invalidated as expected.

### 6.2 Bearer Access Tokens to a Resource Server

An access token carries scope/audience/lifetime issued by an authorization server. If it is a self-contained JWT, the API must verify signature, trusted issuer, audience for **this exact API**, timestamps (`exp`/`nbf`), and additional constraints like scope or tenant. **Base64 decoding is not verification**; a `sub` inside the payload is not enough to authenticate.

- Accept tokens only via proper headers/channels over TLS; avoid tokens in URLs since URLs can end up in browser history, referrers, proxies, and logs.
- Never echo access tokens into error JSON, logs, tracing spans, or message queues. If event correlation is needed, use a request ID or a **sanitized token ID insufficient to replay the credential**.
- A JWT with a valid signature is not automatically **revoked immediately** upon account disablement or logout. Immediate revocation requires extra mechanisms (such as introspection, controlled allow/deny lists, appropriately scoped key invalidation, or very short token lifetimes).
- A bearer token alone is not strong proof that the original user is sending it: a stolen bearer token can be replayed while valid; sender-constrained tokens use mechanisms such as mTLS/DPoP.

An OIDC ID token primarily proves the login event to the client/relying party; **never use an ID token as an access token for APIs**. Which claims are issued to which recipient must follow the protocol contract.

### 6.3 Refresh Tokens

A refresh token can obtain new access tokens without prompting for the password again, so a leaked refresh token can sustain access longer than an access token. You need to:

1. Store according to the client's security capability: confidential server-side clients have secret stores; public clients need mechanisms supported by the authorization server, such as refresh-token rotation or sender-constraining per policy.
2. Enforce expiry, scope, and client/subject binding. Never put refresh tokens in local logs, unnecessary responses, or URLs.
3. On refresh, if using rotation, issue a new token and invalidate the old one per policy; replay of an old token must be detected and handled consistently, potentially revoking the entire token family on suspected theft.
4. On global logout, grant revocation, account state changes, or incident detection, clearly define revocation behavior at the authorization server and its impact on already-issued access tokens.

### Comparison Table

| Event | Password | Server-side session cookie | Self-contained access token | Refresh token |
| --- | --- | --- | --- | --- |
| User just logged in | Needed only to verify at that moment | Session may be created | May be issued per flow | May be issued per flow |
| User logs out | No longer needed in current request | Invalidate server-side session | May still work until expiry depending on revocation mechanism | Must be revoked per policy |
| Password changed | New hash in store | Decide whether to invalidate old sessions | Does not automatically expire if API checks no state | Decide revoke/rotate per policy |
| Token leaked | No direct impact on password, investigate related activity | If cookie leaked: revoke session ID | Block/revoke per design or wait out expiry | Revoke token family/grant and check replay |
| Expired | Passwords typically do not have a fixed automatic TTL | Per session timeout | `exp` and validation policy | Per token lifetime/rotation |

The table describes **applicable mechanisms**, without asserting that every default configuration automatically invalidates all sessions/tokens when a user changes their password.

## 7. Service Secrets, API Keys, and Signing Keys: Treat as Assets That Can Leak

Users are not the only ones with credentials. Applications also need database passwords, API keys, OAuth2 client secrets, encryption/signing keys, mTLS certificates, and service-account secrets. If one of these leaks, the blast radius can exceed a single user account.

### Lifecycle for Machine Credentials

1. **Create:** generate with adequate entropy, assign owner, environment, purpose, least privilege, TTL/rotation policy, and version name; never share secrets between dev and production.
2. **Provision:** deliver to the right workload via a secret manager/KMS/vault or controlled platform mechanism; keep secrets out of Git, Docker images, artifacts, command lines, logs, crash reports, and public docs.
3. **Use:** only components that need to know may read; prefer workload identity/short-lived credentials over long-lived secrets where infrastructure supports it; never return service secrets to a frontend.
4. **Rotate:** create a new version, deploy consumers, allow an overlap window if the protocol requires it, verify operation, then retire the old version. Rotation must account for caching, connection pools, and multiple instances.
5. **Revoke/expire:** when leak is suspected or no longer needed, revoke at the verifying source; remove unused copies, review audit logs, and detect use of revoked secrets.
6. **Review/delete:** enforce retention on secondary data like backups and logs; never claim complete deletion while backups have not aged out.

**Distinguish public keys and private keys:** an IdP/issuer can publish public keys via JWKS for signature verifiers, while private signing keys belong in an HSM/KMS or protected keystore. JWT signing key rotation needs a grace period accepting the previous key for unexpired tokens if policy requires; never accidentally accept arbitrary `kid`/issuers chosen by the client.

**Do not apply one fixed rotation schedule to everything:** service secrets may require automated rotation, whereas user passwords should not necessarily be forced to change monthly without signs of compromise. Cadence depends on credential type, threat model, lifetime, and operational cost.

## 8. Spring Boot Servlet Example: Verifying Passwords Without Returning Credentials

Below is a Java 17+, **Spring Boot 3.x / Spring Security 6.x** application with `spring-boot-starter-web` and `spring-boot-starter-security`. The example uses HTTP Basic and an in-memory user **for local learning only**: the controller returns authenticated principal details without returning or logging the password. The password is encoded into a hash when creating the user.

File `src/main/java/demo/CredentialDemoApplication.java`:

```java
package demo;

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
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CredentialDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CredentialDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("local-demo-password"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class WhoAmIController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> currentUser(Authentication authentication) {
        return Map.of(
                "subject", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
```

**How to run:** Create a Spring Boot 3.x application with Java 17+ and the two starters above, place the file in the matching package path, and run `./gradlew bootRun` (Linux/macOS), `.\gradlew.bat bootRun` (Windows PowerShell), or `./mvnw spring-boot:run` with an equivalent Maven project. Because it requires Spring Boot and its dependencies, **you cannot compile this example with a bare `javac` command** like `SecretBufferDemo` in section 4.3.

Send test requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u learner:wrong http://localhost:8080/api/me
curl -i -u learner:local-demo-password http://localhost:8080/api/me
```

On Windows PowerShell you can use `curl.exe` instead of the `curl` alias. Expected outcomes:

| Request | Result | Explanation |
| --- | --- | --- |
| `GET /public` | HTTP 200, body `public` | Public endpoint. |
| `GET /api/me` without credentials | HTTP 401 with HTTP Basic challenge | No valid authentication proof provided. |
| `GET /api/me` with wrong password | HTTP 401 | Hash check failed. |
| `GET /api/me` with `learner:local-demo-password` | HTTP 200, JSON with `subject` = `learner`, `authenticated` = `true` | Credentials verified; endpoint uses only principal, emits no password. JSON key order is not fixed. |

**Why is this example safer than returning credentials?** The controller only needs `Authentication.getName()` and the authentication state. It never calls `authentication.getCredentials()`, never builds a response containing `Authorization`, and never logs passwords. Spring Security performs verification according to the configured mechanism.

**Boundaries of the example:** `local-demo-password` is fixed demo data and **must not be used in production**; HTTP Basic should only be used over HTTPS in practice, with secret management, password policies, and brute-force protection. In a real environment, the user store must be designed and protected to requirements; never hardcode passwords or expose debug endpoints even to logged-in users. The snippet **does not claim runtime test execution across every Spring Boot version**.

### 8.1 Anti-Patterns to Avoid

The following snippets illustrate mistakes only and are **not standalone programs**:

```java
// Wrong: logging the entire request, which may hold password/Authorization/Cookie.
log.info("login request={}", requestBody);

// Wrong: relying on client-asserted data to set the principal.
String caller = request.getHeader("X-User");
SecurityContextHolder.getContext().setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                caller, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));

// Wrong: keeping the raw credential in session or passing it to a business service.
session.setAttribute("password", rawPassword);
paymentService.processPayment(rawPassword, accountId);
```

The right approach is restricting the API/filter so only the authentication component sees the credential, receiving the verified `Authentication` result, and **passing the principal and verified authorities to services**. The logger receives events like `login_failed`, a request ID, and a sanitized reason. If identifying info must be logged, follow PII policies and prevent log injection; masking all but the last few characters of a token can still leak data, so prefer not logging it at all.

## 9. Observability Boundaries: Logs, Traces, Errors, Dumps, and Caches

Sensitive data frequently leaks through **secondary copies**, after the authentication code itself handled things properly. Design controls along the entire data path:

| Origin point | Common mistake | Required constraint |
| --- | --- | --- |
| Gateway/WAF/request logging | Logging full `Authorization`, `Cookie`, or query strings with `token` | Log only necessary metadata, scrub before writing; restrict log read access. |
| App logger | `log.debug("auth={}", authentication)`, request dumps, JSON request bodies | Allowlist logged fields; never rely on `toString()` being safe for arbitrary custom tokens. |
| Exception/error responses | Returning errors with stack traces, secrets, or request headers | Standardized error format, never echo credentials, access-control internal traces. |
| Tracing/APM | Automatically capturing request headers/bodies or baggage containing tokens | Exclude/sanitize sensitive fields upfront; control sampling and retention. |
| Session/cache | Storing raw passwords, keys without TTL, principals holding credentials | Store minimal state only; enforce TTL, access control, encryption-at-rest as needed. |
| Queue/message/event | Publishing `LoginAttempt` events containing password/OTP | Emit events stripped of secrets; never use credentials as correlation IDs. |
| Git/CI/CD | Committing `application.yml` with real passwords, printing env secrets | Secret managers, CI masking, secret scanning, artifact permissions; revoke immediately if leaked. |
| Backup/crash dumps | Sensitive data persisting after source deletion | Encrypt, restrict access, enforce retention/deletion, incident-response procedures. |
| Browser/client | Storing tokens carelessly in localStorage, history, URLs | Pick storage per threat model, CSP/XSS defenses, keep tokens out of URLs, shorten lifetimes. |

**The best redaction happens before writing**, such as before logging middleware or instrumentation, so credentials never enter logs/traces in the first place. Adding a periodic "log cleanup" step afterward cannot undo a secret reaching an unauthorized destination.

Record failure events in enough detail to detect attacks without revealing to the client whether an account exists. Events can include timestamp, request ID, mechanism name, outcome, source application, and a standardized internal reason code; limit PII and honor retention limits.

## 10. Incident Response Workflow When a Credential Leaks

Depending on the credential type, "changing the password" is rarely sufficient:

1. **Confirm type and scope:** user password, session cookie, access/refresh token, API key, private key, or PII. Identify issuer, environment, affected resources, and timeframe.
2. **Contain/revoke:** lock or revoke the credential **where it is actually verified**. If a session leaked, invalidate server-side; if a refresh token leaked, revoke the grant/family per system mechanism; if a service key leaked, rotate/revoke in the vault and downstream APIs.
3. **Replace safely:** issue new credentials, update consumers with required permissions, verify operation before/after cutover. For signing keys, manage `kid`/JWKS, token lifetimes, and controlled rollback.
4. **Clean up copies:** search logs, traces, issue trackers, CI output, Git history, backups, and monitoring systems for the credential; tighten access, scrub/redact per policy, and preserve needed investigation evidence.
5. **Check unauthorized use:** audit logins, actions using the secret, reuse detection, and anomalous access; close the bug that exposed the secret before reissuing.
6. **Close the incident:** record lifecycle, owner, and remediation date; verify the old credential is rejected at every required checkpoint. Never treat "removed from repo" as resolved if the token still works.

**Concrete scenario:** A developer accidentally enables HTTP request debug logging and writes a production bearer token to logs. Deleting the local log line does not invalidate the token stored in a centralized log system. You must revoke/constrain the token at the issuer/API per architecture, lock down log access, handle persisted copies, fix the debug setting, and confirm replaying the old token fails.

## 11. Test Matrix for Lifecycle Boundaries

| Test scenario | What must be proven |
| --- | --- |
| Login with valid and invalid password | Only valid login creates an authenticated principal; no password appears in responses/logs/traces. |
| DB stores password hash | Hash uses suitable algorithm/salt/cost; no plaintext or bare SHA-256; verify `PasswordEncoder.matches`. |
| Successful `Authentication` | Business code does not need `getCredentials()`; verify credential erasure behavior of the token/provider in use. |
| Cached `UserDetails` | After the first login, a second login still authenticates; avoid clearing the password hash on a reused cached object. |
| Logout with session cookie | Reusing the old cookie is rejected by the server; timeout and session fixation policies work. |
| Access token with invalid signature, `iss`, `aud`, or expired | Resource server rejects it and grants no principal/authorities. |
| Revoked token, disabled account | System enforces committed revocation/freshness policies; test with previously issued tokens. |
| Refresh-token rotation | Old token cannot mint new access tokens; replay is detected/handled per policy. |
| Key/service secret rotation | Old secret is rejected at the right time; consumers switch to the new secret without leaking into logs/CI. |
| Request body with OTP/password | Gateway, error handlers, APM, tracing, queues, and metrics do not record sensitive data. |
| Custom filter/header `X-User` | Client-asserted data is never promoted to a trusted `Authentication`. |
| Cross-site request using session cookie | CSRF defense works properly for browser apps and state-changing actions. |
| Non-existent user / wrong password | Client gets an appropriate message preventing account enumeration; audits remain useful. |
| Token in URL/query | API is not designed to distribute tokens via URLs; logs and browser history do not accumulate tokens. |

Testing goes beyond HTTP 200/401. Inspect **every place that might retain credentials** after a request: DB, cache, session, audit logs, log pipeline, traces, metrics labels, queues, browser storage, and backups under appropriate access controls.

## 12. Misconceptions to Avoid

1. **"Once a password is hashed, it is no longer sensitive."** Hashes can be stolen for offline cracking; protect DBs, backups, and password policies.
2. **"Once `ProviderManager` erases, all copies in the heap are gone."** Erasure applies only to certain objects/paths; it does not cover every `String`, log, cache, or framework copy.
3. **"Deleting the cookie in the browser invalidates the server session."** The server must invalidate the session/check timeouts; the browser cannot control copies held by an attacker.
4. **"A validly signed JWT works on every API."** Resource servers must check issuer, audience, purpose, expiration, scopes, and policies.
5. **"A leaked bearer token is still safe because of its signature."** Anyone holding a valid token can replay it within its granted scope until rejected.
6. **"Because we use HTTPS, we can log the Authorization header."** TLS protects transit; logs/traces are a separate copy channel.
7. **"We need to keep the raw password in session to know who the user is."** Store the authenticated principal; never store the raw secret.
8. **"Every secret must rotate every 30 days."** Rotation and expiry depend on credential type and risk; user passwords should change on signs of compromise, whereas service secrets may need automated rotation.
9. **"Zeroing a `char[]` means no secret remains anywhere in the JVM."** It clears only that array; copies, immutable `String`s, and crash dumps have separate limits.
10. **"We can just scrub logs after saving them."** The secret has already entered the logging pipeline; block at collection, restrict access, and treat exposure as an incident.

## 13. Self-Check

**Question 1.** A user logs in with a password and then sends 100 requests using a session cookie. Should the raw password be kept in `HttpSession` to avoid re-verifying?

**Answer:** No. The session stores controlled authentication state; the password is only needed during login or re-authentication. Cookies/session IDs have their own lifecycle and risks.

**Question 2.** Why must both password hashes and access tokens be protected, even though only tokens can directly call APIs?

**Answer:** Bearer access tokens can be replayed directly while valid. Password hashes enable offline password-guessing attacks that can lead to account takeover; both cause harm if leaked, with different exploitation and revocation mechanics.

**Question 3.** A custom `Authentication` erased `credentials`. Can we guarantee no secrets remain in memory?

**Answer:** No. Account for input copies, principal/details, caches, request objects, immutable strings, logs, and JVM dumps. Erasure narrows retention; it does not erase all traces.

**Question 4.** A stolen JWT access token was just issued for API A with `exp` in 10 minutes. The user clicks logout in the browser. Why might API A still accept the stolen token?

**Answer:** Clearing the token in the browser does not revoke an issued JWT. If API A only checks signature and expiration, the token stays valid for its remaining window; revocation/freshness mechanisms or short TTLs per policy are needed.

**Question 5.** After changing a password, an old session still works. Is this always a Spring Security bug?

**Answer:** Not enough to conclude that from this symptom alone. Validity of old sessions depends on the application's invalidation/session-management configuration and policy; if the system promises to revoke all sessions on password change, then it is a defect to fix.

**Question 6.** When a password check fails, should we log the entire request to debug?

**Answer:** No. Log safe metadata such as request ID, authentication type, outcome, and standardized reason code; avoid passwords, OTPs, bearer tokens, cookies, and unnecessary personal data.

## 14. Further Reading

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, `ProviderManager`, `CredentialsContainer`, and erasure limits with caches.
- [Spring Security — CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html): meaning of `eraseCredentials()` and implementing custom credential objects.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder`, and hash formats.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): sessions, session fixation, and lifecycle.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): issuance, rotation, revocation, expiry, logging, and secret controls.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data categories to exclude from logs.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): hashing algorithms and password management.
- [NIST SP 800-63 Digital Identity Guidelines](https://pages.nist.gov/800-63-4/): requirements on authenticators, verification, and modern password policy.

**Key takeaway:** Authentication does not end at `PasswordEncoder.matches()`. A credential is safe only when **created in the right place, transmitted over the right channel, verified by the right party, retained for the right duration, rotated/revoked properly, and kept free of copies outside trusted boundaries**.