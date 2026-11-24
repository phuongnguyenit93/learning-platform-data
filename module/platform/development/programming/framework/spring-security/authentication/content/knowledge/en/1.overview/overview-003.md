# Users, Service Accounts, and Identity Providers in Spring Security

> **Context:** Spring Security — Authentication / Overview. This lesson explains *who or what is being authenticated*, *who issues identity evidence*, and *how a Java application should interpret that identity*. The OAuth 2.0/OIDC examples assume Spring Boot 3.x, Spring Security 6.x or later, and Java 17+; the illustrative configurations require an actual Identity Provider (IdP) to issue tokens.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Distinguish **human users**, **service accounts / workload identities**, and **Identity Providers (IdP)**.
2. Distinguish subject/principal, account, credential, login session, access token, ID token, and access permissions.
3. Describe the user login flow and the machine-to-machine flow using `client_credentials`; understand when a human user is or is not behind a request.
4. Recognize `Authentication`, `SecurityContext`, `AuthenticationManager`, `AuthenticationProvider`, and `GrantedAuthority` in Spring Security.
5. Choose appropriate trust boundaries and permission checks; avoid confusing an authenticated identity with granted permissions.

## 2. Three Concepts: Who, Which Account, Who Verifies?

| Component | Nature and examples | What credentials does it typically hold? | Key point to remember |
| --- | --- | --- | --- |
| **User** | An individual person: employee Lan, customer Minh, operations admin | Password + MFA, passkey, security key, login session; or authenticated by an IdP | One person may have multiple accounts; a locked account does not mean the person does not exist |
| **Service account** | Identity for an application, job, worker, workload: `svc-invoice-export`, CI job | Client secret, private key, certificate, platform identity, short-lived token | Does not represent a person by default; needs an operational owner, least privilege, and its own lifecycle |
| **IdP** | System that verifies and manages identities, such as an enterprise IdP or OpenID Provider | Holds user profiles, login policies, signing keys, and/or authentication systems | The IdP is the party confirming identity; the API must still validate the token itself and decide resource permissions |

**Identity** is the set of information identifying a principal. **Subject/principal** is the entity the security mechanism is referring to; it can be a person or a workload. **Account** is the record used to manage the principal, credentials, and state. **Credential** is evidence for authentication; **token** is a message issued by a trusted party carrying scope/claims and an expiration time. A token is often a bearer credential: whoever holds a valid token can use it until it expires or is blocked by an enforced mechanism.

Distinguish two questions:
- **Authentication:** "Which principal sent this request, and is the evidence trustworthy?"
- **Authorization:** "Is that principal allowed to read the report, edit the profile, call the API, or operate on this specific tenant?"

Successful login does not automatically imply having all permissions. "Authenticated" and "authorized to perform a specific action" are two separate decisions.

## 3. Users: Human Identity and Access Lifecycle

An application may store users locally (for example, `UserDetailsService` looking up usernames and hashed passwords) or delegate the login process to an IdP. In enterprise systems, an IdP typically supports centralized login, MFA, device policies, and access revocation when an employee leaves. The application may still need its own business data: which organization a customer belongs to, account status within the product, and which orders they are allowed to see.

For example, the username "lan" may appear in multiple systems. When linking identities from external sources, the durable key is usually the **`(issuer, subject)`** pair: `iss` identifies the issuer and `sub` identifies the subject within that issuer's scope. Never assume email, display name, phone number, or username is an immutable global identifier; they can change, collide, or be unverified.

The lifecycle should cover: account creation and verification -> login/MFA -> granting job-appropriate permissions -> role changes -> disabling/locking -> deletion or archival per policy. A web login session has its own cookie and lifetime; do not equate a session with an access token. When a user leaves an organization, consider existing sessions, still-valid tokens, and access rights in dependent systems.

**Scenario:** Lan logs in via OIDC and opens a financial report. The IdP verifies "this is Lan"; the reporting API next checks whether Lan has permission to view **that report in that tenant**. Both checks are necessary.

## 4. Service Accounts: Software Identity, Not "A Special User" by Default

A batch job running at 02:00 has no human typing a password. The job still needs its own identity so the system can identify and trace it. Service accounts govern the questions: "Which workload is calling the API, who is operationally responsible for it, what is it allowed to do, and when will its credentials rotate?"

**Common models:**
- **Service account in an internal system:** a record like `svc-report-job` in an identity store; may use mTLS/certificates or an internal mechanism. Not necessarily a user account that can log into a UI.
- **OAuth 2.0 confidential client:** an application registered with an Authorization Server using a `client_id` and client authentication method (secret, private key JWT, mTLS...). When using `client_credentials`, the client requests an access token for itself, with **no end user** in the flow.
- **Workload identity / federation:** the runtime environment (such as a cloud platform or orchestrator) issues a verifiable identity, reducing the need to store long-lived secrets. "No static secret" does not mean skipping authentication.

`client_id` is the OAuth client's identifier, while the access token's `sub` depends on the issuer's convention. Do not assume the two values are always equal. Depending on the provider, a token may carry specific claims indicating the client, workload, authorized party, or grant type; **only rely on claims that have been verified and have a clear contract with the IdP**.

### Machine-to-Machine Flow with OAuth 2.0 Client Credentials

~~~mermaid
sequenceDiagram
    participant Job as Batch job
    participant AS as Authorization Server / IdP
    participant API as Resource Server (Spring Security)
    Job->>AS: Client authentication + grant_type=client_credentials
    AS-->>Job: Access token (scoped, audience, expiry)
    Job->>API: GET /api/reports + Bearer access token
    API->>API: Verify signature/issuer/audience/time
    API->>API: Check scope and resource permissions
    API-->>Job: 200 or 401/403
~~~

Because there is no end user in `client_credentials`, the API must not assume that token carries Lan's consent or permissions. If a process executes a request on Lan's behalf, that is **user-context delegation** (delegation/on-behalf-of or an equivalently designed mechanism), distinct from a token representing only the workload. Having a job write `createdBy = "admin"` or fabricate a "fake user" does not turn it into administrator authority.

**Operational rules:** create separate identities per service/environment or trust purpose; assign minimal scopes; avoid sharing secrets across workloads; store secrets in a secret manager or use workload identities; rotate and revoke credentials; log audits by service identity, client, and task; disable accounts or revoke permissions when a job is retired. Never embed secrets in source code, logs, or command-line arguments that may be recorded.

## 5. Identity Provider (IdP), Authorization Server, OIDC Provider

These three terms are related but not completely synonymous:

- **Identity Provider (IdP):** verifies identity, manages or links accounts, enforces MFA and login policies. May use OIDC, SAML, or other mechanisms.
- **OAuth 2.0 Authorization Server:** performs protocol-level authentication/authorization and issues access tokens to OAuth clients per grants and policies; not every OAuth system is a user IdP.
- **OpenID Provider (OP):** a system supporting OpenID Connect on top of OAuth 2.0, enabling applications to verify user identity and receive an `ID token`. One product can fulfill all three roles.

**OAuth 2.0 is primarily about delegating resource access; OIDC adds a user-identity authentication layer.** In a web "Sign in with IdP" flow, the application typically uses Authorization Code with appropriate protections such as PKCE, receiving an ID token to verify client-side login and an access token to call authorized APIs. **An ID token is not an access token**: APIs should not accept an ID token in place of an access token. The Resource Server must check that the token was issued specifically for it.

An IdP may connect to a user directory/LDAP/AD or another IdP; a directory store is not automatically an OAuth access-token issuer. Multi-IdP federation must clearly define which issuers are trusted and how accounts and permissions are mapped; do not merge two principals merely because their emails match.

### Two Common User Flows

1. **Local login:** browser sends credentials over a secure channel -> application/Spring Security checks against the user source -> creates an authenticated `Authentication` -> maintains a session per design. The authentication process depends on configuration; passwords must be stored using a proper password-hashing mechanism, never in plaintext.
2. **OIDC login:** browser is redirected to the IdP -> IdP authenticates the user (possibly with MFA) -> application receives an authorization code, exchanges it at the token endpoint, and verifies the result -> application maintains its own login session if using the web session model.

Never pass one issuer's access token to another issuer, skip audience checks, or treat "the JWT can be decoded" as valid authentication. Base64 decoding only reads data; **verifying the signature and token conditions** is the trust step.

## 6. Authentication Model Selection Table

| Scenario | Principal to identify | Appropriate approach | Where permissions are decided |
| --- | --- | --- | --- |
| Employee logs into a web app | Specific human user | OIDC login / SSO, appropriate web session | Application + API, based on roles and resources |
| User calls an API through an authorized app | User and associated app | Authorization Code + PKCE, API-targeted access token | API checks scope and data-level permissions |
| Scheduler calls an internal API | Workload or OAuth client | Client Credentials, workload identity, or mTLS | API checks service identity, scope, audience, and policy |
| API receives a JWT bearer token | Subject in the access token | Spring Security OAuth2 Resource Server | Authentication from token and authorization on endpoints/data |
| Service needs to act *on behalf of a user* | Both user context and client | IdP-supported delegation/token exchange | API checks both delegated permissions and resource permissions |

**Scope-limiting example:** `svc-export` only needs `reports.read`; do not grant `users.admin`. Conversely, Lan having permission to view certain reports does not mean a service job owns that permission. Least privilege must account for *tenant, resource, action, and time* where business logic requires.

## 7. How Does Spring Security Know "Who Is Calling"?

In a Spring Security **Servlet** application, an HTTP request passes through a chain of security filters. According to the chosen authentication mechanism, a filter receives the credential/token, passes it through the appropriate authentication component, and produces an `Authentication` object. When authentication succeeds, the information is placed in `SecurityContext` so the rest of the request can retrieve it. `SecurityContextHolder` stores data per thread by default, so never assume the context automatically propagates to background threads or async tasks.

Core components:

| Component | Role |
| --- | --- |
| `Authentication` | Holds `principal`, `credentials` (if still present), `authorities`, and authentication status; can also represent an authentication request before confirmation |
| `AuthenticationManager` | Interface coordinating authentication requests; `ProviderManager` is the common implementation |
| `AuthenticationProvider` | Authenticates one type of credential/token; for example, a provider for username/password or JWT |
| `SecurityContext` / `SecurityContextHolder` | Stores authentication information in the current processing context |
| `GrantedAuthority` | Mapped permission/role/scope used by Spring Security during authorization |
| `SecurityFilterChain` | Defines the HTTP request security path and rules |

**Principal shape varies by login mechanism:** with username/password it may be `UserDetails`; with OAuth2/OIDC Login it may be `OAuth2User`/`OidcUser`; with a JWT Resource Server the default principal is `Jwt` and `Authentication` is typically `JwtAuthenticationToken`. **Do not cast every principal to `UserDetails`** or assume `authentication.getName()` is always an email. With a JWT Resource Server, the default name typically comes from the `sub` claim.

Roles and scopes are not automatically equivalent. `hasRole("ADMIN")` checks the authority `ROLE_ADMIN` by default convention; a JWT Resource Server by default maps scopes to authorities of the form `SCOPE_reports.read`. Only build mappings from claims to application authorities after clearly defining trusted issuers, claim semantics, tenants, and access levels.

### Integration Example A — API Receiving an Access Token from an IdP

This example is for **an existing Spring Boot Servlet API** with `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-boot-starter-oauth2-resource-server`. It is an integration configuration, **not a standalone Java SE program**. Replace the dummy issuer/audience with your actual Authorization Server and API values; register the client, scopes, and signing keys at the IdP.

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/tenant
          audiences: https://api.example.test
```

`src/main/java/example/demo/ApiSecurityConfig.java`:

```java
package example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(requests -> requests
                .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
```

`src/main/java/example/demo/IdentityController.java`:

```java
package example.demo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        Object principal = authentication.getPrincipal();
        String subject = principal instanceof Jwt jwt
                ? jwt.getSubject()
                : authentication.getName();

        return Map.of(
                "subject", subject,
                "authenticationType", authentication.getClass().getSimpleName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "Report visible";
    }
}
```

**How to verify (with a real IdP and token):**
- `GET /api/me` without a valid access token -> typically **401 Unauthorized**.
- Valid bearer access token with the right issuer/audience but missing `reports.read` -> `GET /api/reports` gets **403 Forbidden**.
- Valid token with scope `reports.read`, mapped by Spring to `SCOPE_reports.read` -> `GET /api/reports` returns body `Report visible` (200).
- `/api/me` illustrates `Authentication`; the `authenticationType` field depends on how Spring authenticated the request. JSON key order is not a fixed contract.

The configuration above only illustrates **GET** routes. For APIs with POST/PUT/DELETE, design CSRF, sessions, CORS, and other policies according to the real client model. In a multi-tenant system, `hasAuthority("SCOPE_reports.read")` is only an initial check: the business layer must also verify whether the token/principal has permission to access a *specific report* belonging to a given tenant.

By default, a JWT Resource Server verifies the signature, issuer, validity timestamps, and maps scopes. Configuring `audiences` adds audience validation for the API. For opaque tokens, use an appropriate introspection mechanism instead of handling them as JWTs manually. How an IdP expresses service identity in claims has no universal convention reliable enough to guess from a single field.

### Integration Example B — A Service Requesting a Token via client_credentials

This is the **configuration of a service calling an API**, distinct from the Resource Server configuration receiving tokens in Example A. The caller application uses `spring-boot-starter-oauth2-client` and registers an OAuth client with the Authorization Server. `REPORTS_CLIENT_SECRET` is provided via environment/secret manager; never commit real values.

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-job:
            provider: internal-as
            client-id: report-batch-job
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: reports.read
        provider:
          internal-as:
            token-uri: https://idp.example.test/oauth2/token
```

In a real configuration, `client-secret` uses the Spring property placeholder `${REPORTS_CLIENT_SECRET}`. A properly configured `OAuth2AuthorizedClientManager` obtains, caches, and uses access tokens under the `client_credentials` grant; background jobs typically need a manager backed by `OAuth2AuthorizedClientService`, rather than relying on a user's `HttpServletRequest`. When calling the API, send the access token in the `Authorization: Bearer ...` header over HTTPS. **Do not send an ID token** here. Never write custom token-fetching/refresh/secret-storage code when the framework and IdP already provide proper flows.

The example above shows configuration; **it cannot generate a token without an actual IdP, client registration, credentials, and scope policy**. Whether the AS grants a specific scope and what the token claims look like depend on the AS configuration.

### Integration Example C — User Login with OIDC

A typical web application adds `spring-boot-starter-oauth2-client`, registers a client for Authorization Code, and configures the OIDC Provider's issuer. With a valid registration configuration, the filter chain can enable:

```java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(requests -> requests
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
```

This is a **method snippet integrated into a `@Configuration` class**, not a standalone runnable Java file; it requires the corresponding imports and client/redirect URI configuration. In a handler for a logged-in user, you can receive `@AuthenticationPrincipal OidcUser` if the principal genuinely comes from an OIDC flow. This flow creates a **user** login context, distinct from a batch job's `client_credentials`. In an application with multiple filter chains, you must define URL scopes and matching order clearly; Examples A and C are **two independent options**, so do not copy two beans that match all requests into the same app.

## 8. Standalone Java 17 Example: Same Permission, Different Principal Kinds

The Java SE example below **runs without Spring**, illustrating only the business logic after a trusted authentication layer has identified the principal and granted permissions. It does not perform authentication or JWT verification, so it does not replace Spring Security.

Save with the exact filename `IdentityDecisionDemo.java`:

```java
import java.util.Set;

public class IdentityDecisionDemo {
    enum Kind { HUMAN, SERVICE }

    record Caller(String subject, Kind kind, Set<String> permissions) {}

    static boolean canReadReports(Caller caller) {
        return caller.permissions().contains("reports.read");
    }

    public static void main(String[] args) {
        Caller human = new Caller(
                "user:lan", Kind.HUMAN, Set.of("reports.read"));
        Caller service = new Caller(
                "service:nightly-export", Kind.SERVICE, Set.of("reports.read"));
        Caller guest = new Caller(
                "user:guest", Kind.HUMAN, Set.of());

        System.out.println("human=" + canReadReports(human));
        System.out.println("service=" + canReadReports(service));
        System.out.println("guest=" + canReadReports(guest));
    }
}
```

Run with JDK 17+:

```bash
javac IdentityDecisionDemo.java
java IdentityDecisionDemo
```

Exact stdout:

```text
human=true
service=true
guest=false
```

Explanation: **principal kind** tells who is acting; **permission** decides the "read reports" action in the example. In real systems, never trust a `Caller` freely sent by the client: construct it from verified `Authentication`/tokens, then further check permissions on the tenant and record. A system may explicitly forbid service accounts from calling an endpoint even with the same scope; that is an explicitly designed **additional business policy**.

## 9. Claims and Trust Boundaries to Remember

| Field/concept | Question to answer | What must not be assumed |
| --- | --- | --- |
| `iss` (issuer) | Who issued the token? Does the API trust this issuer? | A JWT with a valid signature from **any** issuer is accepted |
| `sub` (subject) | Which principal does the token bind to within the issuer's scope? | `sub` is an email or is always `client_id` |
| `aud` (audience) | Which service/API is the token intended for? | A token valid for App A is also valid at API B |
| `exp`, `nbf` | Has the token expired or not yet reached its valid time? | Tokens have no time limit or require no revocation mechanism |
| `scope` / `scp` | What access scopes did the AS grant? | Scope automatically replaces all resource and tenant checks |
| `client_id` / related client claims | Which client/workload is participating in the flow? | Client is the same as the end user, or claims always share the same name/meaning |
| `Authentication#getAuthorities()` | Which authorities did Spring map? | Every role from an IdP is trusted as an internal role without mapping rules |

An API must enforce **trust boundaries where requests arrive**: validate token format, signature or introspection, issuer, audience, expiry, status, and additional rules; then authorize by endpoint, record, and tenant. A validly signed JWT can still be rejected for the wrong audience/scope. A stolen bearer token can still be used within its validity window: use HTTPS, short-lived tokens, secure storage, and incident-response mechanisms.

**Useful audits** typically record request/correlation ID, issuer, verified subject or client identifier, action, resource, and allow/deny decision. Avoid logging raw access tokens, ID tokens, passwords, client secrets, and sensitive data.

## 10. Common Real-World Mistakes

1. **Treating a service account like a "shared admin user".** Loses traceability and over-grants privileges. Create separate workload identities with owners, scopes, environments, and rotation policies.
2. **Decoding a JWT and trusting its claims directly.** Must verify the token and issuer/audience/time; never trust claims from client-supplied request bodies/headers.
3. **Using an ID token to call an API.** ID tokens verify login for the OIDC client; the Resource Server validates an access token issued for it.
4. **Confusing `client_credentials` with user login.** This grant has no end user; do not attribute a service's action as user-delegated without verified delegation evidence.
5. **Using email as the global user key.** With federation, link by subject and issuer, with controlled account-merge/link workflows.
6. **Trusting every group/role from an IdP as admin rights.** Establish clear mappings, restrict trusted issuers, and check data permissions at the API.
7. **Treating `authenticated()` as sufficient.** That only confirms the request has a valid Authentication per configuration; sensitive endpoints still need scopes/roles and ownership checks.
8. **Failing to revoke/rotate service credentials.** Indefinitely lived credentials are a major risk; use short lifetimes, secret managers, or workload identities.
9. **Assuming logout immediately invalidates every JWT access token.** In practice it depends on token lifetime, revocation/introspection, sessions, and IdP/Resource Server policies.
10. **Reading `SecurityContext` from another thread by assumption.** For jobs/schedulers or async execution, use proper context propagation and explicitly identify the workload; do not accidentally reuse a user request's context.

## 11. Scenarios to Check Understanding

**Scenario 1:** Lan logs in via SSO successfully, yet receives 403 when calling `/api/reports`. Is this contradictory?  
**Answer:** No. Lan authenticated successfully, but the API may lack `SCOPE_reports.read` or lack permission on the requested report/tenant. If the token were invalid/expired or authentication were missing entirely, 401 would typically be returned.

**Scenario 2:** A batch job obtains an access token via `client_credentials`; the token has `client_id=report-batch-job`. Can all actions be attributed to user "Lan"?  
**Answer:** No. This token represents the client/workload, unless a dedicated user-delegation mechanism verified by both the AS and API exists. Audit by service identity and operational owner.

**Scenario 3:** Two IdPs both issue `sub=123`. Is that the same person?  
**Answer:** Cannot conclude that. `sub` is scoped per issuer; you must inspect the `(iss, sub)` pair and account-linking workflow.

**Scenario 4:** A properly signed JWT has `aud` pointing to a billing service; should the reporting API accept it?  
**Answer:** No. The token was not issued for the reporting API, even though its signature is valid.

**Scenario 5:** A human user has internal role `ROLE_MANAGER`, and a workload has `SCOPE_reports.read`; both need to view the same report. Should roles and scopes be merged mechanically?  
**Answer:** No. Clear policies are needed to define which principals may read which reports. Roles and scopes are input signals; resource/tenant permission checks remain the application's responsibility.

## 12. Takeaways When Designing

- **Human user:** real person, login, and account lifecycle; an IdP may handle authentication.
- **Service account/workload:** dedicated identity for software; `client_credentials` carries no user context.
- **IdP/Authorization Server:** verifies/authenticates and may issue tokens; **Resource Server** must validate tokens and enforce its own access policies.
- In Spring Security, `Authentication` describes the authenticated principal and authorities; **`authenticated()` does not replace permission checks**.
- Always ask: **who issued the evidence? who is the token for? who is the principal? which actions are allowed on which resources?** Answer all four questions before trusting a request.

### Official References

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/
- Spring Security — OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth 2.0 Client / Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
