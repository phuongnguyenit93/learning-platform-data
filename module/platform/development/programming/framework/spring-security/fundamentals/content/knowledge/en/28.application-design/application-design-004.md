# Managing Accounts Locally vs. Integrating an Identity Provider

## 1. Deciding where identities are managed

When building an application with Spring Security, the team must decide: **manage accounts and passwords locally** or **sign in through an Identity Provider (IdP)**? This is not merely a login UI choice. The decision affects security, data ownership, user support, MFA, workforce lifecycle, availability, and integration with other systems.

Three common architectures:

- **Local identity:** the application owns the user store, persists password hashes, authenticates logins, and manages password resets, credential changes, account lockouts, and sessions.
- **Federated identity/SSO:** an external IdP authenticates users; the application receives verified identity information over a protocol such as **OpenID Connect (OIDC)** or **SAML 2.0**, then enforces its own business authorization.
- **Hybrid:** the IdP handles authentication while the application still maintains internal user IDs, per-tenant permissions, and profiles; a separate local flow may exist for groups permitted by policy.

**No option is universally secure in every case.** A well-designed local system can suit a standalone product; a properly configured IdP can greatly reduce credential management burden, especially for SSO and MFA. Yet a misconfigured IdP or auto-granting admin rights based on email can equally introduce critical vulnerabilities.

Overarching principle: **an IdP or local login only proves identity; the application itself must still verify what that person may do on which resources.**

## 2. Distinguishing authentication, identity, authorization, and tokens

| Term | Meaning | Example in Spring Security |
| --- | --- | --- |
| **Identity** | A record identifying a person or service | Internal user ID, subject issued by an IdP |
| **Credential** | A factor used to prove identity | Password, passkey, MFA factor, session credential |
| **Authentication** | Verifies credentials and establishes an identity for the request | `AuthenticationManager`, `UserDetailsService`, OIDC login |
| **Authorization** | Decides which actions are allowed on a resource | `hasRole`, `AuthorizationManager`, owner/tenant checks |
| **Identity Provider (IdP)** | System that authenticates users and issues identity info | OIDC Provider, SAML IdP |
| **OIDC client/relying party** | Application delegating sign-in to an IdP | Spring `oauth2Login()` on a web app |
| **Authorization server** | System issuing tokens for OAuth2 | Identity platform's token endpoint |
| **Resource server** | API verifying access tokens before allowing requests | Spring `oauth2ResourceServer().jwt()` |
| **Provisioning** | Creating, updating, disabling, or deleting accounts used in the app | JIT provisioning, SCIM, invitations |
| **SSO** | Using one identity to access multiple applications | Multiple apps signing in through the same IdP |

**OAuth2 does not automatically mean user login.** OAuth2 focuses on **delegated authorization** and issuing access tokens; **OIDC** adds an authentication layer atop OAuth2, including the ID token and identity verification rules. An API can use OAuth2 Resource Server to accept access tokens without having an OIDC login page at all.

**An ID token differs from an access token.** An ID token proves authentication details to an OIDC client; an access token is designed for a resource server/API. Never send a client's ID token to another API as a Bearer token unless that API was designed for and specifically validates that token.

## 3. Comparing responsibilities across both models

| Question | Self-managed accounts | IdP integration |
| --- | --- | --- |
| Who stores passwords? | App stores **password hashes** and manages changes | IdP manages credentials; app never receives IdP passwords |
| Who provides MFA/passkeys? | App must build or integrate them itself | Usually supported centrally by the IdP |
| Who handles forgot-password? | App designs reset tokens, email delivery, and verification | IdP typically provides recovery |
| Multiple apps sharing login? | Must build SSO or duplicate accounts | Uses federation/SSO via the same IdP |
| Locking departing employees? | App needs lockout and permission revocation mechanisms | IdP aids centralized admin; app still handles sessions/tokens |
| Who controls data access? | App | **App must still control it** |
| Ease of login UI customization? | Higher, which means owning the risks too | Depends on IdP customization options |
| What if IdP/network fails? | Independent of external IdPs | New logins may be impacted |
| Cost? | Building, operating, support, and security | Service fees, integration, administration, migration |
| Business data? | Managed by app | Still typically managed by app |
| System migration? | Requires migrating users/password hashes | Requires migrating issuer, subject, account linking, role mapping |

Teams often underestimate the cost of local identity if they only count a few days to build a login form. Real costs include protecting the credential store, defending against credential stuffing, MFA, account recovery, security notifications, password changes, login sessions, account lockouts, and user support.

On the other hand, using an IdP does not eliminate in-app costs: record-level permissions, tenant mapping, admin provisioning, onboarding, handling duplicate accounts, logout, auditing, and handling IdP outages.

## 4. Local account architecture: what you own

A local-account application must design the complete lifecycle:

1. **Registration:** verify required attributes (e.g., email) and defend against automated sign-ups or username squatting.
2. **Credential storage:** use an adaptive hash such as bcrypt, scrypt, PBKDF2, or Argon2 with appropriate policy, salts, and work factors; never store plaintext or raw fast SHA-256 hashes.
3. **Login:** HTTPS, handle bad passwords without enumerating accounts, rate limiting, and protection against credential stuffing.
4. **MFA/passkeys:** select multi-factor authentication options with secure enrollment and recovery flows.
5. **Forgot/change password:** random tokens, short expiration, single-use limits, and session revocation/re-authentication when needed.
6. **Sessions:** session fixation protection, appropriate `Secure`/`HttpOnly`/`SameSite` cookies, idle/absolute timeouts, logout, and CSRF for forms and state-changing requests.
7. **Account lifecycle:** lock or delete per policy, verify new email addresses, role changes, auditing, and related notifications.
8. **Monitoring:** anomalous logins, credential attacks, lock/unlock events, data leaks, mass resets.
9. **Authorization:** never trust browser-sent roles/owners/tenants; enforce in services using the authenticated user.

Spring Security provides `PasswordEncoder`, `AuthenticationProvider`, `UserDetailsService`, form login, CSRF, and foundational security building blocks. **Spring Security does not ship a complete identity management product** covering registration, recovery, MFA, support, and compliance workflows out of the box for your application.

### Typical local login flow

```text
Browser -> GET /me
    -> Spring Security sees unauthenticated
    -> redirect to /login
Browser -> POST /login (username, password, CSRF)
    -> authentication filter / authentication manager
    -> UserDetailsService loads account
    -> PasswordEncoder matches password against hash
    -> Authentication succeeds
    -> appropriate SecurityContext and web session
    -> authorizeHttpRequests / method security / service policy
    -> endpoint allowed or denied
```

During matching, the server temporarily receives the password in the request, so **never log passwords**. Password hashes in the database are sensitive data to protect, not harmless strings. After login, the browser uses a session cookie instead of re-sending the password on every request in the form-session model.

## 5. Runnable project example: self-managed login with Spring Security

Create a Spring Boot **3.x**, Spring Security **6.x**, Java **17+**, Servlet/MVC project with **Spring Web** and **Spring Security** dependencies (choose Gradle in Spring Initializr). Create file:

```text
src/main/java/demo/localidentity/LocalIdentityApplication.java
```

Complete code:

```java
package demo.localidentity;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LocalIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocalIdentityApplication.class, args);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class Endpoints {
        @GetMapping("/public")
        public Map<String, String> publicEndpoint() {
            return Map.of("message", "open");
        }

        @GetMapping("/me")
        public Map<String, String> me(Authentication authentication) {
            return Map.of(
                "user", authentication.getName(),
                "message", "authenticated"
            );
        }

        @GetMapping("/admin")
        public Map<String, String> admin() {
            return Map.of("message", "admin-only");
        }
    }
}
```

**This program is runnable inside a project with Spring Boot/Security**; standalone `javac` will lack the required classpath. In-memory accounts are strictly for localhost and learning; they cannot serve as a production user store.

- `InMemoryUserDetailsManager` supplies users to the authentication system. When storing real users, replace it with a repository/JDBC/LDAP or custom `UserDetailsService` while still using a proper `PasswordEncoder`.
- `DelegatingPasswordEncoder` uses an algorithm-prefixed hash format that supports upgrade strategies. When storing real users, **hash on creation or password change**, never re-hash every time a user is loaded from the DB.
- `formLogin()` sets up a session-based login flow, default login page, and credential submission handler. The demo does not write a manual POST password controller.
- `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority. Being logged in as `reader` is not enough to open `/admin`.
- **CSRF is not disabled** in the demo. Form login enforces CSRF verification; production apps must design CSRF to match cookie/session usage.

Run:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

Browser checks (open a fresh private window when switching accounts):

| Action | Expected result |
| --- | --- |
| GET `/public` unauthenticated | HTTP 200, JSON `{"message":"open"}` |
| GET `/me` unauthenticated | HTTP 302 to `/login`, then login page displays |
| Login `reader / reader123`, open `/me` | 200, user `reader` |
| `reader` opens `/admin` | 403 |
| Login `admin / admin123`, open `/admin` | 200, JSON `{"message":"admin-only"}` |

`curl -i http://localhost:8080/me` lets you observe the initial 302. Never use sample passwords on real networks; both HTTP Basic and form login require HTTPS in production.

### Testing local authorization with MockMvc

Add `spring-boot-starter-test` and `spring-security-test` in the `build.gradle` of your project:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create `src/test/java/demo/localidentity/LocalIdentityApplicationTests.java`:

```java
package demo.localidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LocalIdentityApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void readerCannotOpenAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-only"));
    }
}
```

Run `./gradlew test`; all four tests are expected to pass if configured properly. This is **not measured stdout** in the lesson. `user(...)` creates a test identity to exercise authorization, **not proof that real passwords were verified**. To test the credential flow, add integration tests for valid/invalid form login, CSRF, session lifecycle, and locked accounts.

## 6. IdP: delegating authentication to a dedicated system

IdP integration is typically preferred for enterprise SSO, centralized MFA/passkeys, multiple apps sharing identities, B2B customers wanting to use their own accounts, or when the app team wants to avoid operating a password store.

With OIDC on a server-side application, the conceptual flow is:

```text
Browser -> /me (no app session yet)
Spring Security -> redirect to /oauth2/authorization/corp
Browser -> IdP authorization endpoint
IdP -> verify user, MFA, and policies
IdP -> redirect back to /login/oauth2/code/corp with code + state
Spring Security OAuth2 Client:
    validate state, exchange code, process and verify ID token
    create Authentication for web app and appropriate session
Application:
    map issuer + subject -> internal user ID
    check status, tenant, and business permissions
    return authorized resource
```

Authorization Code and PKCE protect flows appropriately per OAuth2 client type; `state` and OIDC `nonce` enforce distinct bindings. Never skip verification checks just to work around a broken redirect/callback. **Never write a custom callback endpoint and blindly trust raw `code` strings or unverified JWT payloads.**

### 6.1. OIDC Spring Boot application example

Create **a separate project** with Spring Boot 3.x, Java 17+, **Spring Web**, **Spring Security**, **OAuth2 Client**. Place the file at:

```text
src/main/java/demo/oidc/OidcIdentityApplication.java
```

```java
package demo.oidc;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OidcIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcIdentityApplication.class, args);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }

    @RestController
    public static class Endpoints {
        @GetMapping("/")
        public Map<String, String> home() {
            return Map.of("message", "public");
        }

        @GetMapping("/me")
        public Map<String, String> me(
                @AuthenticationPrincipal OidcUser user) {

            String issuer = String.valueOf(
                user.getIdToken().getClaims().get("iss")
            );
            return Map.of(
                "issuer", issuer,
                "subject", user.getSubject()
            );
        }
    }
}
```

This example **runs login only when connected to a valid OIDC IdP**; it is a complete Spring Boot program, yet Java code alone cannot simulate a real IdP. In production, avoid exposing claims/tokens to the frontend for debugging; `/me` should return a minimal profile and the internal user ID once the identity is linked.

Configure `src/main/resources/application.properties`:

```properties
spring.security.oauth2.client.registration.corp.client-id=${OIDC_CLIENT_ID}
spring.security.oauth2.client.registration.corp.client-secret=${OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.scope=openid,profile
spring.security.oauth2.client.provider.corp.issuer-uri=${OIDC_ISSUER_URI}
```

The `${...}` values above are **Spring Boot environment variable placeholders**, such as `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URI`. Supply them from an appropriate secret manager/environment, and never commit client secrets to Git or print them to console logs.

With registration ID `corp`, the default redirect URI is typically:

```text
http://localhost:8080/login/oauth2/code/corp
```

Register this exact URI at the IdP for local testing; production requires HTTPS and a callback allowlist. Wildcard configurations or arbitrary redirects increase authorization code leakage risk.

Open `http://localhost:8080/me` without an active session: the app sends the user to the IdP. After successful OIDC authentication, the result contains `issuer` and `subject` extracted by Spring Security from the verified ID token. **You must link both values to an internal user ID before granting access to business data.**

### 6.2. You do not automatically get ROLE_ADMIN after OIDC login

OIDC login tells you that a user has been authenticated. Spring Security may attach an authority like `OIDC_USER`; that is **not the application's `ROLE_ADMIN`**. If you configure `.hasRole("ADMIN")` without an internal role source or trusted authority mapping, a user who logs in successfully at the IdP will still receive 403—and that is the correct protection.

The authority source can be a user–tenant–role table in the app, an authorization management service, or IdP claims/groups **verified and mapped via an allowlist**. Never auto-grant ADMIN because an email ends with a domain or because the frontend sends a `role=ADMIN` query parameter.

### 6.3. OIDC login is not a JWT Resource Server

| Role | Spring Security Servlet config | Credential |
| --- | --- | --- |
| OIDC web login | `oauth2Login(Customizer.withDefaults())` | Browser redirect/callback; ID token handled by OIDC client |
| REST API receiving JWT | `oauth2ResourceServer(o -> o.jwt(...))` | `Authorization: Bearer ...` with access token |
| API receiving opaque token | `oauth2ResourceServer(o -> o.opaqueToken(...))` | Bearer token requiring introspection/validation |
| Local web form | `formLogin(...)` | Username/password form with CSRF and session |

Illustrative configuration snippet **in a separate Resource Server project**:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
```

With dependency `spring-boot-starter-oauth2-resource-server` and configuration:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${API_ISSUER_URI}
```

This is a **conditional configuration excerpt, not a standalone Java file**. The Resource Server must verify signature, issuer, expiration, and **audience/token type/scopes matching the API contract**. Default issuer configuration does not guarantee every product-specific audience requirement is automatically enforced; add validators and tests. **Never treat an ID token meant for a web app as a Bearer token meant for another API.**

## 7. Hybrid: IdP handles credentials, application handles profiles and permissions

A real-world system often has:

- **IdP** authenticating users, managing credentials and MFA.
- **Application** managing `app_user_id`, user status, per-tenant memberships, roles, resource ownership, operational restrictions, and business auditing.
- **Linking table** mapping external identities to internal users.

Conceptual schema example:

```sql
CREATE TABLE app_users (
    id UUID PRIMARY KEY,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE external_identities (
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    app_user_id UUID NOT NULL REFERENCES app_users(id),
    PRIMARY KEY (issuer, subject)
);

CREATE TABLE tenant_memberships (
    app_user_id UUID NOT NULL REFERENCES app_users(id),
    tenant_id UUID NOT NULL,
    role VARCHAR(64) NOT NULL,
    PRIMARY KEY (app_user_id, tenant_id)
);
```

This is an illustrative schema, not a full production migration: add appropriate uniqueness constraints, indexes, lifecycle tracking, soft deletes, history, and administrative permissions.

**Why use (issuer, subject)?** In OIDC, `sub` identifies a subject within the scope of an issuer. Two different IdPs can issue the exact same `sub` string for two different people. Emails and usernames can change, be recycled, or remain unverified.

```text
(issuer-A, subject-123) -> app-user-10
(issuer-B, subject-123) -> app-user-27

app-user-10 and app-user-27 are not the same person by default.
```

Never automatically merge two accounts just because **their emails match**. A weakly configured IdP or a changed email address can let someone take over an internal account. Account linking must follow a workflow that **verifies control over both the old and new identities**, obtains user consent where appropriate, logs an audit trail, and supports recovery.

### Controlled JIT provisioning flow

1. Spring Security verifies a successful OIDC login.
2. Extract the `issuer + subject` pair from the verified identity, never from client query parameters.
3. Look up the link in `external_identities` and retrieve the internal ID if present.
4. If absent, apply **onboarding rules**: invitation, verified tenant, email verification, or relevant organization policy; not every provider should auto-create accounts.
5. New users should receive minimal permissions or pending-approval status, never automatic ADMIN.
6. Verify user status and membership upon resource access; roles from the IdP do not replace owner/tenant policies.
7. When a user is deleted/locked at the IdP, sync or re-verify app permissions according to your designed SLA/revocation needs.

When changing IdPs (e.g., during a corporate acquisition), do not update existing accounts via heuristic email matching. Perform a verified migration with proof, cutover, and auditing; business data should keep `app_user_id` stable.

## 8. SSO, login sessions, logout, and permission revocation

**SSO does not mean every application shares one session.** The browser may hold an IdP session while each app maintains its own session. Logging out of one app usually ends that app's session; it does not necessarily clear the IdP session or sessions in other apps. Likewise, someone locked out at the IdP does not necessarily lose every previously issued app session/token immediately.

Design explicitly for:

- Session lifetimes, idle timeouts, and re-authentication for sensitive operations.
- Cookie attributes, session fixation protection, and CSRF for browser sessions.
- Revocation when a user leaves, admin rights are revoked, or an incident occurs.
- Single logout/front-channel/back-channel logout only when both the IdP and app genuinely support it, with proper flow testing.
- When tokens are long-lived, downgrade policies may need to consult current account/membership state rather than trusting stale roles inside the token.
- For API resource servers, expired/wrong-audience/wrong-issuer tokens must be rejected regardless of whether the user holds another website session.

**IdP outage:** distinguish **new logins** being blocked from **existing sessions** continuing until expiration. JWTs can be verified with cached public keys under valid configuration; opaque tokens may depend on introspection. Never automatically open a "login bypass" when the IdP is unreachable. If operational break-glass accounts are required, they must have dedicated scopes, MFA, auditing, and emergency procedures—never a shared default admin/password.

## 9. Security pitfalls to check when choosing a model

| Mistake | Consequence |
| --- | --- |
| Storing plaintext passwords or raw fast SHA-256 hashes | Risk if credential store leaks |
| Failing to protect password resets | Account takeover without knowing the old password |
| Enabling login while skipping owner/tenant checks | Broken Object Level Authorization |
| Trusting matching emails to auto-link accounts | Account takeover |
| Trusting unverified role claims | Privilege escalation |
| Decoding JWTs without verifying signature/issuer/expiry | Forged tokens or tokens from other systems accepted |
| Ignoring access token audience | API accepts tokens meant for another resource |
| Allowing wildcard redirect URIs | Authorization code leakage, open/wrong redirects |
| Leaving client secrets in Git/logs | Credential leak |
| Using an ID token as an API access token | Wrong target recipient and token constraints |
| Disabling CSRF on all browser endpoints because an IdP is used | Forged request risk via session/cookies |
| Clearing the app session and assuming the IdP logged out everywhere | Broken Single Logout expectations |
| Using the same client registration/secret across all environments | Larger blast radius if a secret leaks |
| Granting an admin bypass during an IdP outage | Authentication bypass |
| Failing to update user status upon leaving an organization | Unintended active app sessions/roles |

**Always authorize against business data.** `ROLE_USER` or a successful login does not prove permission to read every invoice, record, or document. Owner, tenant, and action rules must be enforced in the backend.

## 10. Identity system testing matrix

Do not merely test "login succeeds and home page returns 200." Verify separate layers:

| Layer | Self-managed accounts | With an IdP |
| --- | --- | --- |
| Authentication | Valid/invalid password, disabled account, reset, lockout | OIDC redirect, callback, state/nonce, ID token validation |
| Authorization | USER cannot access ADMIN/other owners | Valid OIDC user without required role still gets 403 |
| Session | Cookies, CSRF, session expiry, logout | App session, IdP session, promised logout scope |
| Identity | Internal user ID matches credentials | Correct issuer + subject; never matched by email |
| Provisioning | Registration and user locking | JIT invitation, SCIM/lifecycle, membership |
| API | Any access tokens are verified properly | JWT/opaque token with valid issuer/audience/expiry/scope |
| Operations | Password recovery, credential stuffing | IdP outage, key rotation, migration, revocation |

Essential negative tests:

1. Anonymous request to a private resource → 401 or 302 to login, depending on the interface.
2. Authenticated user lacking admin permission → 403.
3. Tenant A user requesting tenant B resources → denied.
4. Two IdPs issuing the same `sub` → never merged into one account.
5. OIDC email matching a local account → never auto-linked.
6. Token with wrong issuer/audience or expired → rejected by API.
7. Invalid OIDC callback state or invalid authorization code → no session issued.
8. IdP account locked while app session still exists → behavior reflects the designed revocation policy.
9. IdP unavailable → no login bypass opened.
10. POST in a cookie-based app without a CSRF token → rejected per policy.

**Mock logins differ from verifying a real provider.** `@WithMockUser`, `user()`, `oidcLogin()`, and `mockJwt()` in `spring-security-test` are suitable for testing in-app authentication context/authorization, but they do not prove real passwords, token signing, OIDC discovery, or token endpoints work. Add integration/e2e tests against a trusted test IdP environment when needed.

## 11. Context-based selection guidance

| System | Starting point worth evaluating | Still built in-house |
| --- | --- | --- |
| Small standalone app | Local accounts or managed consumer identity depending on team capacity | Authorization and data protection |
| Internal enterprise app suite | OIDC/SAML via the enterprise IdP | Roles/memberships, sessions, and access policies |
| Multi-company B2B SaaS | Per-tenant federated IdP + internal app users | Tenant isolation, invitations, permission mapping |
| Consumer app needing social login | OIDC with appropriate providers; optionally local too | Account linking, privacy, support, recovery |
| API for mobile/SPA and other services | Appropriate OAuth2 resource/authorization server | Token audience/scope validation, owner/tenant checks |
| Offline-capable environments | Evaluate local or governed offline identity mechanisms | Credential/revocation/sync, stale-permission risk |

Ask additional questions:

- Who owns the users: HR organization, B2B customers, or our platform?
- Are SSO, MFA, passkeys, device policies, or offboarding sync mandatory?
- Which data must the application actually retain for business operations?
- Who can grant/revoke ADMIN or per-tenant permissions?
- Are there data residency, retention period, and export requirements?
- When the IdP fails, how should the app behave for new logins vs. active sessions?
- When switching IdPs, how will data and account links be migrated?
- Does the app team have the operational capacity to run a password store, MFA, resets, and incident response if choosing local?

Do not compare only IdP subscription fees against the cost of writing a few login forms. Compare **total cost of ownership, risk, user lifecycle, and operational capacity**.

## 12. Production deployment checklist

- [ ] Document which system authenticates users: local, OIDC/SAML, or hybrid.
- [ ] Define internal user IDs and map external identities via `issuer + subject`.
- [ ] Trust ID/role/tenant information only after verification and mapping through a trusted source.
- [ ] For local accounts, enforce proper password hashing, MFA/rate limiting/resets/session protection.
- [ ] For IdPs, lock down redirect URIs, client registrations, and secrets; verify state/nonce/issuer/tokens per the model.
- [ ] Separate OIDC web login from API OAuth2 Resource Server.
- [ ] Define permission assignment, tenant isolation, ownership, and admin rights independently from login.
- [ ] Design provisioning, account linking, disabled accounts, migration, and offboarding.
- [ ] Design CSRF/CORS/sessions/cookies and logout to match client characteristics.
- [ ] Have plans for IdP outages, key/secret rotation, and permission revocation.
- [ ] Test valid flows as well as account takeover, duplicate emails, wrong-audience tokens, and cross-tenant access.
- [ ] Log only necessary audit data; never log passwords, ID/access/refresh tokens, cookies, or client secrets.

**Conclusion:** choosing self-managed accounts means taking full responsibility for protecting credentials and the login lifecycle. Integrating an IdP shifts substantial authentication work to a specialized platform, yet **never transfers business authorization decisions**. Designs tend to hold up best when the application owns an **internal user ID**, the IdP supplies verified identities, and all data permissions are enforced by the backend.

### References

- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — OAuth2 Client and Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
