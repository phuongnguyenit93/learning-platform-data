# SSO and the Relationship Between External Identity and Application Session

## 1. Three Entities Easily Confused in Single Sign-On

**Single Sign-On (SSO)** allows users to sign in at one Identity Provider (**IdP**) and then access multiple trust-linked applications without re-entering their password at each application. SSO **does not mean** every application shares a single Java `SecurityContext` object, a single `JSESSIONID` cookie, or a shared HTTP session.

When developing a Spring Security application, you must distinguish:

1. **External identity**: the user record verified by the IdP, for example OIDC `iss=https://login.example.org/realms/staff` and `sub=00u-742`; in SAML it can be based on the combination of issuer/entity ID and a NameID identifier guaranteed stable by policy.
2. **Local account**: an internal key owned by the application, for example `accountId=usr-1042`, which holds status, business data, tenant, and current `GrantedAuthority`/permissions.
3. **Application session**: the login state for **a single application** after the IdP has authenticated the user; in Spring MVC/Servlet it typically holds `SecurityContext` via `HttpSession` and is referenced by the application's cookie.

Example:

```text
    Browser               IdP (login.example.org)             App A
       |                          |                               |
       | GET /reports             |                               |
       |--------------------------------------------------------->|
       |                     redirect /authorize                  |
       |<---------------------------------------------------------|
       | log in, receive SSO cookie on IdP domain                 |
       |------------------------->|                               |
       |<-------------------------| redirect code to App A        |
       |--------------------------------------------------------->|
       |                          |<---- code exchange ---------->|
       |                          |        validate ID Token      |
       |                          |                               |
       |                          |    (iss, sub) -> local account|
       |                          |    -> Authentication          |
       |                          |    -> app session             |
       |<--------------------------------------------Set-Cookie App A|
       |                          |                               |
       | GET /reports + app cookie                                |
       |--------------------------------------------------------->|
       |                       App A reads SecurityContext from session
       |<---------------------------------------------------------|
```

IdP sign-in occurs in one trust domain, while the application session exists in a different trust domain. **Identity linking** is the step that maps the IdP-verified identity to an internal account that the application allows to be used.

## 2. Distinguishing IdP Session, Application Session, and OAuth/OIDC Tokens

| Object | Owner | Used For | Lifetime and Scope |
| --- | --- | --- | --- |
| **IdP SSO session** | IdP | Remembering that the user is signed in at the IdP to support SSO across trusted applications | Governed by the IdP's cookie/session policy |
| **App A session** | App A | Remembering `Authentication` for requests to App A | Governed by App A's cookie, session store, idle/absolute timeout |
| **App B session** | App B | Remembering `Authentication` for App B | Independent of App A, even when using the same IdP |
| **OIDC ID Token** | Signed/issued by IdP, verified by RP | Proving the authentication event and identity (`iss`, `sub`, `aud`, ...) to the RP | Expires at `exp`; not automatically synonymous with app session |
| **OAuth 2.0 Access Token** | Issued by Authorization Server | Allowing a client to call a resource server per scope/audience/policy | Governed by token lifetime and resource server policy |
| **Refresh Token (if issued)** | Issued by Authorization Server | Requesting new access tokens per grant/policy | May be rotated/revoked; does not replace `JSESSIONID` |

At time `t0`, the user signs in to App A via OIDC. The IdP verifies the user and App A opens an `HttpSession`. At `t1`, the ID Token expires after its configured lifetime, yet **App A may still have a valid session**: subsequent requests to App A do not necessarily re-validate the ID Token with the IdP. At `t2`, the app session expires while the IdP session is still active; App A redirects to the IdP and the IdP may re-authenticate very quickly, making the user feel like they were "never logged out".

**Consequence:** ID Token expiration, access token expiration, logout at the IdP, logout at the app, and locking a local account are **distinct events**; you must design policies to synchronize them when needed.

App A's session cookie typically contains only a session ID; Spring Security **does not by default send the ID Token or password inside the app cookie**. How tokens are stored depends on `OAuth2AuthorizedClientRepository`/`OAuth2AuthorizedClientService` and the actual configuration. The IdP's cookie belongs to the IdP's origin/domain; the browser does not arbitrarily expose it to the application.

## 3. OIDC as a Typical SSO Example for Spring Applications

Spring Security supports browser login via the **OAuth 2.0 Authorization Code flow**, and uses OIDC when the client requests the `openid` scope.

Basic steps:

1. The client accesses a route requiring login; Spring Security redirects to `/oauth2/authorization/{registrationId}`.
2. The application creates an authorization request, attaches `state` (and nonce for OIDC when applicable), and manages request/response correlation; PKCE may be used depending on client/policy.
3. The IdP authenticates the user using an existing SSO session or prompts for login/MFA, then redirects back to `/login/oauth2/code/{registrationId}` with an authorization code.
4. Spring Security exchanges the code with the token endpoint, verifies the ID Token (`iss`, `aud`, signature, `exp`, and related constraints), and validates `state`/`nonce` according to the library and configuration.
5. `OidcUserService` creates an `OidcUser` from the ID Token and UserInfo (when called), and then the application looks up the external identity key to determine the **local account**.
6. From the local account, the application loads roles/permissions into `GrantedAuthority`, completes `Authentication`, and saves `SecurityContext` via the configured persistence mechanism.
7. The browser receives the **application's** session cookie. Subsequent requests typically use this session; there is no need to repeat the OIDC authorization code flow on every HTTP request.

### Component Roles in Spring Security Servlet

| Component | Responsibility |
| --- | --- |
| `ClientRegistration` / `ClientRegistrationRepository` | Configures IdP, client ID, issuer URI, redirect URI, scopes |
| `OAuth2AuthorizationRequestRedirectFilter` | Redirects to the authorization endpoint and saves request state |
| `OAuth2LoginAuthenticationFilter` | Handles the callback and completes login |
| `OidcUserService` | Loads the OIDC principal and serves as the extension point to find the local account |
| `OAuth2UserService<OidcUserRequest, OidcUser>` | Contract for customizing OIDC user processing |
| `OAuth2AuthenticationToken` | Application `Authentication` after OAuth2/OIDC login |
| `SecurityContextRepository` | Saves/loads `SecurityContext` for subsequent requests |
| `HttpSessionSecurityContextRepository` | Common session-backed implementation in Servlet |
| `OAuth2AuthorizedClientService`/`OAuth2AuthorizedClientRepository` | Manages authorized clients/tokens for API calls, distinct from `SecurityContextRepository` |

Applications using Spring WebFlux have corresponding APIs such as `ServerHttpSecurity`, `ReactiveSecurityContextHolder`, and `ServerSecurityContextRepository`. The Spring Boot code in section 7 is for **Spring MVC/Servlet**, so do not plug `HttpSecurity` into a WebFlux configuration.

## 4. Identity Linking Key: OIDC (issuer, subject) -> localAccountId

With OpenID Connect, the **`(iss, sub)`** pair from a **verified** ID Token is the stable identifier for a Relying Party to recognize a user at an issuer. **Never use email, username, preferred_username, or display name alone as an automatic linking key.**

Example `external_identity_link` table:

| issuer | subject | local_account_id | status |
| --- | --- | --- | --- |
| `https://login.company.org/realms/staff` | `sub-1001` | `usr-42` | ACTIVE |
| `https://login.partner.org/tenant-a` | `sub-88` | `usr-42` | ACTIVE, link verified |
| `https://login.company.org/realms/staff` | `sub-1002` | `usr-51` | ACTIVE |

Separate `local_account` table:

| id | enabled | application permissions |
| --- | --- | --- |
| `usr-42` | true | `REPORT_READ`, `ROLE_USER` |
| `usr-51` | false | login denied even if IdP just authenticated |

Mandatory rules:

- Enforce a **unique** constraint on the `(issuer, subject)` pair within the management scope and for ACTIVE status per the data model; one active external identity must never automatically point to two different accounts.
- Before looking up a mapping, only accept an ID Token **already verified** by the OIDC library for the exact client, issuer, and audience. Never let a client send two strings `issuer`, `subject` over JSON and treat that as a login result.
- Store a stable local account ID; when the IdP changes email, display name, or login username, the relationship remains intact.
- Handle **pairwise subjects**: the same user may receive different `sub` values for different RPs/sectors. Do not automatically conclude different `sub` values are two different people, nor forcibly merge two identities based on email; if merging is needed, require an authorized linking workflow.
- Do not arbitrarily lowercase/uppercase `sub`, strip special characters, or normalize the issuer; these strings are identifiers with their own rules.
- Multiple tenants/issuers may use the same `sub`, so **`sub` alone is not enough**.
- In SAML, the corresponding key is typically based on issuer Entity ID + a NameID with an appropriate format/qualifier or an immutable attribute governed by the IdP; a **transient NameID** is not a long-term account-binding key.

### IdP Input Only Proves Identity, Not That the Local Account Is Still Valid

An IdP may return `email_verified=true`; this claim does not by itself prove that any local account with the same email belongs to the user currently signing in. Emails can be recycled, verified differently by an IdP in another trust domain, or changed when staff switch departments.

**Successful mapping** requires both conditions:

1. The authenticated external identity has a valid link to a local account.
2. At the time policy is evaluated, the local account is still allowed to be used, belongs to the right tenant, and holds valid permissions.

## 5. SSO Authentication, Account Linking, and Authorization Are Three Distinct Steps

| Step | Trusted Input | Output | Common Mistake |
| --- | --- | --- | --- |
| **SSO authentication** | Verified OIDC/SAML response from IdP | External identity | Manually parsing JWT without checking issuer/audience/signature |
| **Account linking/resolution** | `(iss, sub)` + application-managed registry | `localAccountId` | Merging accounts based on matching email |
| **Authorization** | Active account, application roles/permissions, resource | `GrantedAuthority` + allow/deny decision | Turning any scope or arbitrary claim into `ROLE_ADMIN` |

In Spring Security, if a controller needs to know who is signed in, `Authentication.getPrincipal()` typically holds an `OidcUser` with OIDC claims. If business logic needs the local account's ID, the application should have **a trusted mapping service** or a custom principal containing `localAccountId` alongside the external identity. **Do not repurpose OIDC `sub` into an internal ID**: it is a claim issued by the IdP. You can keep the OIDC principal for logout/claim inspection and store the local account ID in a dedicated structure.

`GrantedAuthority` is typically loaded from the internal account/permission store; claims from the IdP may contribute to permission calculation **only when there is an explicit whitelist/policy and clear trust contract**. `SCOPE_profile` or `SCOPE_email` represents a scope granted to the OAuth client, not administrative permissions over application data.

## 6. Standalone Java 17 Example: External Identity -> Local Account -> App Session

The exercise below simulates **the step after an IdP has authenticated**, meaning the `ExternalIdentity` input is treated as verified. This pure Java program does not generate ID Tokens, verify signatures, or implement real HTTP/cookies/sessions. That lets us observe the exact mapping contract without needing an IdP account.

Create `SsoIdentitySessionDemo.java`:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SsoIdentitySessionDemo {

    // Issuer + subject pair (already passed OIDC validation).
    record ExternalIdentity(String issuer, String subject) {
        ExternalIdentity {
            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new IllegalArgumentException("Invalid external identity");
            }
        }
    }

    record LocalAccount(
            String id,
            boolean enabled,
            Set<String> permissions) {}

    // Session simulation only. Does not contain password or ID Token.
    record AppSession(
            String id,
            String localAccountId,
            List<String> grantedAuthorities) {}

    static final class ApplicationLoginService {
        private final Map<ExternalIdentity, String> links;
        private final Map<String, LocalAccount> accounts;
        private final Map<String, AppSession> sessions = new HashMap<>();
        private int nextSessionNumber = 0;

        ApplicationLoginService(
                Map<ExternalIdentity, String> links,
                Map<String, LocalAccount> accounts) {
            this.links = Map.copyOf(links);
            this.accounts = Map.copyOf(accounts);
        }

        AppSession afterOidcAuthentication(ExternalIdentity identity) {
            // In a real system, identity must ONLY be created from
            // a verified ID Token, never accepted directly from an HTTP body.
            String accountId = links.get(identity);
            if (accountId == null) {
                throw new SecurityException("Identity is not linked to an active account");
            }
            LocalAccount account = accounts.get(accountId);
            if (account == null || !account.enabled()) {
                throw new SecurityException("Identity is not linked to an active account");
            }

            // Load permissions from the account; do not infer roles from email/subject.
            List<String> authorities = account.permissions().stream()
                    .sorted()
                    .toList();

            AppSession session = new AppSession(
                    "app-session-" + (++nextSessionNumber),
                    account.id(),
                    authorities);
            sessions.put(session.id(), session);
            return session;
        }

        boolean isLocallyLoggedIn(String appSessionId) {
            return sessions.containsKey(appSessionId);
        }

        void localLogout(String appSessionId) {
            sessions.remove(appSessionId);
        }
    }

    public static void main(String[] args) {
        ExternalIdentity userAtIdp = new ExternalIdentity(
                "https://login.example.org/realm",
                "subject-1001");

        ApplicationLoginService app = new ApplicationLoginService(
                Map.of(userAtIdp, "usr-42"),
                Map.of("usr-42", new LocalAccount(
                        "usr-42",
                        true,
                        Set.of("REPORT_READ", "ROLE_USER"))));

        AppSession session = app.afterOidcAuthentication(userAtIdp);
        System.out.println("localAccount=" + session.localAccountId());
        System.out.println("authorities=" + session.grantedAuthorities());
        System.out.println("appLoggedIn=" + app.isLocallyLoggedIn(session.id()));

        // Same sub but a different issuer must be treated as a different identity.
        boolean rejected = false;
        try {
            app.afterOidcAuthentication(new ExternalIdentity(
                    "https://another-idp.example.org/realm",
                    "subject-1001"));
        } catch (SecurityException e) {
            rejected = true;
        }
        System.out.println("otherIssuerRejected=" + rejected);

        app.localLogout(session.id());
        System.out.println("appLoggedInAfterLogout="
                + app.isLocallyLoggedIn(session.id()));
    }
}
```

Run with Java 17 or later:

```bash
javac SsoIdentitySessionDemo.java
java SsoIdentitySessionDemo
```

Exact stdout:

```text
localAccount=usr-42
authorities=[REPORT_READ, ROLE_USER]
appLoggedIn=true
otherIssuerRejected=true
appLoggedInAfterLogout=false
```

### Explaining What the Example Deliberately Models

- `ExternalIdentity` has only `issuer` and `subject`; the same `sub` with a different issuer will **not** automatically log into the local account.
- The `links` map preserves approved linking decisions; the `accounts` map holds the user's current status and permissions. No local account is implicitly created from email.
- `AppSession` is decoupled from `ExternalIdentity`. Simulating local logout only deletes the app session and **does not touch the IdP SSO session**.
- Sorting authorities ensures deterministic output; these are application permissions, not the ID Token's scope list.
- `HashMap` and a counter are only suitable for a single-process/non-concurrent demo. Production must use the framework's session mechanism, anti-forgery tokens/cookies, a distributed store when needed, and concurrency/transaction controls for the link table.
- `permissions` are snapshotted when opening the session; if permissions change afterward, this example does not auto-refresh them. That is precisely why systems need policy-driven session TTL/revalidation/invalidation.
- Anyone can instantiate `ExternalIdentity` in the demo snippet. In a real system, only code **after the OIDC validator** may construct that input.

## 7. Applying to Spring Boot 3.x / Spring Security 6.x (Servlet)

This section illustrates a real integration point with OIDC, preserving `iss`/`sub` and loading permissions from a local account. It requires a real OIDC IdP, a client registered with the correct redirect URI, and an `AccountLinkService` implemented with an internal data store.

### 7.1. Dependencies and Client Configuration

A Spring Boot 3.x project (Java 17+) needs at least:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Example `application.yml`, replacing issuer and environment variables with your registered values:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate-idp:
            issuer-uri: https://login.example.org/realm

server:
  servlet:
    session:
      timeout: 30m
  forward-headers-strategy: framework
```

- `openid` selects the OIDC flow; `issuer-uri` uses the corresponding discovery/validator. Issuer is an **exact-match identifier value**, not an arbitrary label changed at runtime.
- `/oauth2/authorization/corporate` initiates login; the callback is `/login/oauth2/code/corporate`.
- Secrets come from protected configuration; do not hard-code them in the repository.
- `server.servlet.session.timeout` illustrates the app session idle timeout; it does not set the IdP session lifetime or ID Token lifetime.
- `forward-headers-strategy` should only be used when there is a trusted reverse proxy that strips/controls forwarded headers and ensures the external scheme/host are accurate. Do not allow clients to arbitrarily set headers affecting the redirect URL.

### 7.2. Customizing OidcUserService to Load GrantedAuthority from the Local Account

In an application with an `AccountLinkService` bean (interface shown in the example) and a DB-backed implementation, place `src/main/java/demo/security/OidcSecurityConfig.java`:

```java
package demo.security;

import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {

    // The application must provide an implementation bean, e.g. repository/DB.
    public interface AccountLinkService {
        LocalAccount findActiveAccount(String issuer, String subject);
    }

    public record LocalAccount(String id, Set<String> permissions) {}

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> linkedOidcUserService)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**").permitAll()
                        .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .userInfoEndpoint(info -> info
                                .oidcUserService(linkedOidcUserService)))
                .build();
    }

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> linkedOidcUserService(
            AccountLinkService links) {

        OidcUserService standardOidcUserService = new OidcUserService();

        return userRequest -> {
            // Spring Security handles OIDC before delegating to return OidcUser.
            OidcUser external = standardOidcUserService.loadUser(userRequest);

            String issuer = external.getIdToken().getIssuer().toString();
            String subject = external.getSubject();

            LocalAccount account = links.findActiveAccount(issuer, subject);
            if (account == null) {
                throw new UsernameNotFoundException(
                        "No enabled local account for verified external identity");
            }

            // Map permissions from the local account per policy; do not infer from email.
            Set<GrantedAuthority> localAuthorities =
                    account.permissions().stream()
                            .<GrantedAuthority>map(SimpleGrantedAuthority::new)
                            .collect(java.util.stream.Collectors.toUnmodifiableSet());

            // Preserve OIDC tokens/claims so Spring Security still knows the IdP identity.
            return new DefaultOidcUser(
                    localAuthorities,
                    external.getIdToken(),
                    external.getUserInfo());
        };
    }
}
```

**Example scope:** this class compiles with the right dependency versions, but for the application to **boot and sign in**, you must provide a bean implementing `AccountLinkService`, real DB entries, a client registration, and a working IdP. `AccountLinkService.findActiveAccount` must query within the proper tenant/trust domain scope, reject duplicate/ambiguous mappings, verify the account is not disabled/locked, and throw an appropriate authentication error when no result exists. In production, standardize and map business errors to an appropriate `AuthenticationException`.

`DefaultOidcUser` here still takes the **OIDC subject** as the principal name; `account.id()` is not masqueraded as `sub`. If a controller needs `localAccountId`, you can create a custom principal containing both IDs or query the service by the (`iss`, `sub`) pair at the application layer. Keep account resolution in a component with clear ownership rather than letting each controller infer the account from `email`.

**Note on `GrantedAuthority`:** the example replaces authorities with internal permissions to illustrate an application's policy. If you also need standard OIDC authorities or scopes for other features, design the combined authority set carefully and test thoroughly. Do not assume `SCOPE_email` grants permission to read the entire internal profile.

### 7.3. SecurityContext and Session After Callback

With standard session-based login on Servlet, Spring Security stores `Authentication` in `SecurityContext` and uses `SecurityContextRepository` for persistence across requests. `HttpSessionSecurityContextRepository` is the common implementation. How authentication is stored in the framework does not mean the `AccountLinkService` dataset is synchronized to the IdP session; that is application data.

**Do not do this yourself**:

```java
// Incorrect persistence expectation: setting ThreadLocal alone does not guarantee
// the next request's session will have the new Authentication.
SecurityContextHolder.getContext().setAuthentication(authentication);
```

The snippet above only takes effect within a single request/thread. When writing a custom login filter or controller in Spring Security 6.x, you must save `SecurityContext` through `SecurityContextRepository.saveContext(context, request, response)` as configured. With default `oauth2Login`, the framework performs the required persistence; do not insert arbitrary context-setting code.

### 7.4. Why Can Permissions Become Stale in a Session?

Most applications store `Authentication` along with its authorities at login time inside the session. If an admin revokes `REPORT_READ` in the DB afterward, requests using the old session may still see the stale permission snapshot until the system refreshes/revalidates or invalidates the session.

Common strategies:

- Short session lifetimes and re-authentication when necessary.
- Invalidate related sessions when an account is locked, unlinked, or has privileges reduced.
- For sensitive authorization, cross-check the current account/permissions or use a permissions version (`permissionsVersion`) to detect stale snapshots.
- For stateless APIs, validate tokens on every request per resource server policy; token revocation/TTL and permission data still need to be designed.

## 8. Secure Account Linking Workflows

### 8.1. First-Time Login: JIT Provisioning or Rejection

If (`iss`, `sub`) does not yet exist:

1. **Invite/enterprise-managed provisioning**: create an account only when the user belongs to an admin-authorized group/tenant or holds a valid invitation.
2. **Just-in-time provisioning (JIT)**: accounts may be created automatically if product policy allows, but you must check issuer, tenant, email policy, minimal default permissions, and consent requirements.
3. **No provisioning policy**: reject login or route to a protected registration flow.

In all three approaches, never silently attach a new external identity to an existing account because of a matching email, even if the email is verified. If the product supports account recovery/linking, design a step proving ownership of the existing account plus verification of the new factor.

### 8.2. Linking IdP B to an Existing Local Account

Recommended workflow:

1. The user is currently signed in **with an identified internal account**; for sensitive actions, require step-up/MFA or recent re-authentication.
2. The user selects "Link IdP B account". The application initiates a dedicated OIDC flow with secure `state`/`nonce` and the proper redirect URI.
3. After the verified callback, extract (`issB`, `subB`) from identity B.
4. Check uniqueness: identity B must not already belong to another account; if it does, never silently transfer ownership.
5. Write the link `(issB, subB) -> localAccountId` inside a transaction with a unique constraint, auditing actor + timestamp + verification method.
6. Report the result without turning the linking action into switching the current session's `accountId`; if re-authentication/account switching is needed, use a separate flow.

Multiple concurrent link requests can race. **A database unique constraint and transaction** are mandatory safeguards; checking `if (find == null) insert` in Java alone is insufficient against race conditions.

### 8.3. Unlinking and Transferring Accounts

- Do not allow unlinking the sole login method if the user would lose access without a verified recovery option.
- If external identity B is linked to local account X, never automatically transfer it to Y when email/Y changes; require an authorized, logged process.
- If the issuer changes due to a migration, do not rewrite `iss` with a raw string replace in the DB; prepare a tested mapping/validation and rollback plan.
- After unlinking, handle **existing app sessions** authenticated via that identity per policy; deleting the link row in the DB does not automatically make already-open sessions disappear.
- If a user has two local accounts that need merging, protect resource ownership, data, and permissions; this is a dedicated business operation, not merely inserting another row into the link table.

## 9. Session Lifecycle: Logout, Timeout, Account Changes

### Scenario Matrix

| Event | IdP SSO session | App A session | App B session |
| --- | --- | --- | --- |
| User logs into App A via OIDC | May be newly created or already exist | Created or updated | Does not necessarily exist |
| User navigates to App B (same IdP) | May be reused for SSO | Still active | May be newly created after redirect |
| App A idle timeout | May still be active | Expired | May still be active |
| App A local logout | Usually still active | Invalidated/authentication cleared | Usually still active |
| User logs out at IdP | Cleared per IdP | **Not guaranteed to be cleared automatically** | **Not guaranteed to be cleared automatically** |
| Account disabled by admin | Depends on IdP | Needs application-level revalidation/invalidation | Needs similar policy |
| Standards-compliant, fully implemented OIDC back-channel logout | IdP emits logout event | Relevant RP can invalidate corresponding session | Other RPs depend on implementation/support |

### Three Forms of Logout in OIDC

**Local logout:** Spring Security handles `POST /logout` under standard configuration; it invalidates `HttpSession`/clears `SecurityContext` and authentication data at the RP. It does not automatically remove the SSO session at the IdP, so logging back in may succeed immediately using the old IdP cookie.

**RP-initiated logout:** the application proactively redirects to the IdP's `end_session_endpoint` (if supported by the IdP) with appropriate parameters and a registered post-logout redirect policy. In Spring Security Servlet, there is `OidcClientInitiatedLogoutSuccessHandler`. This is an additional logout flow on top of local logout; providers may have different session-termination policies.

Example **additional configuration snippet** inside a `@Configuration` class (requires injecting `ClientRegistrationRepository`; not a standalone Java program):

```java
@Bean
OidcClientInitiatedLogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    var handler = new OidcClientInitiatedLogoutSuccessHandler(registrations);
    handler.setPostLogoutRedirectUri("{baseUrl}/");
    return handler;
}

// In SecurityFilterChain, after .oauth2Login(...):
// .logout(logout -> logout.logoutSuccessHandler(oidcLogoutSuccessHandler))
```

**Back-channel logout:** the IdP sends a signed/verified logout notification to the RP, enabling the RP to terminate the corresponding session if the Spring Security version, IdP, and application all support it. Verify issuer, audience, `sid`/`sub`, and the session registry per spec. Never write a custom `/logout` endpoint accepting an unverified `userId` from the Internet and invalidating all sessions.

**Important:** "Log out of all applications" is a multi-system requirement; it cannot be guaranteed by App A's `session.invalidate()` alone. There must be a contract across the IdP, each RP, and compatible revocation/session-registry/notification mechanisms.

### Session Fixation, CSRF, and Cookies

- Spring Security Servlet provides **session fixation protection** upon successful authentication (typically changing the session ID on compatible containers). Never reuse a client-supplied session ID.
- Maintain appropriate `Secure`, `HttpOnly`, and `SameSite` attributes on session cookies; use HTTPS and strict domain/path configuration. Avoid embedding ID Tokens or refresh tokens in unprotected cookies.
- Keep CSRF protection enabled for state-changing operations in session-based applications, including logout, account linking, and unlinking; OAuth/OIDC callbacks require `state`, `nonce`, and corresponding protocol protections.
- When deploying multiple instances, use a shared session store if needed; do not confuse the IdP SSO session with shared Spring Session.
- Check both **idle timeout** and **absolute lifetime**; a session should not be extended indefinitely merely because the browser keeps sending requests.
- For sensitive actions (money transfers, changing MFA, transferring ownership), consider requiring separate re-authentication/step-up; an app session recently opened via SSO does not by itself prove "the user just entered their password".

## 10. How SSO with OAuth2/OIDC, SAML, and API Bearer Tokens Differ

| Flow | Identity Evidence | Relationship to Application Session |
| --- | --- | --- |
| OIDC browser login | ID Token from verified issuer; `iss` + `sub` | RP typically opens a browser session; account linking is managed by the application |
| SAML 2.0 SSO browser | SAML Response/Assertion with verified signature, audience, recipient, validity window, and InResponseTo per profile | Service Provider also maintains its own local session; logout requires SAML SLO if needed |
| OAuth2 resource server Bearer JWT | Access token valid for the resource server (issuer, audience, signature, exp, scopes) | Each request carries its own token; **no default browser app session** |
| OAuth2 opaque token | Introspection/AS policy returns active token and principal | Typically stateless at RP; caching/revocation per configuration |
| LDAP/AD username-password login | Bind or password verification per provider | Application may open a local session; LDAP does not inherently imply browser SSO |

OIDC is built on top of OAuth2 but adds a user authentication protocol; **an OAuth2 access token alone is not an ID Token** and should not be used to build OIDC-style account linking without an explicit identity contract.

In a Resource Server, `JwtAuthenticationConverter` or authority mapping serves API permissions and does not automatically perform browser login using an IdP SSO cookie. Conversely, `oauth2Login` is an interactive browser login mechanism and should not be arbitrarily used in place of Bearer API authentication.

## 11. Real-World Pitfalls and Diagnostics

**(1) One email signs into two IdPs and gets merged into the wrong account.** The lookup used `email` instead of (`iss`, `sub`). Check the identity link table, unique constraint, and the account-ownership proof flow before linking.

**(2) SSO login succeeds, yet the next request is still anonymous.** Verify the callback URL is right, the browser sends back the application cookie, the session store actually holds data, domain/path/SameSite/HTTPS/reverse proxy settings are right, and `SecurityContextRepository` saves authentication per Spring Security 6.x mechanisms.

**(3) Logging out of App A and clicking Login again does not show the IdP screen.** The IdP SSO session may still be active. If the product wants IdP sign-out, design RP-initiated logout; if you want to force re-entering credentials for sensitive operations, use OIDC re-authentication prompts and IdP policy.

**(4) Logging out at the IdP leaves App A still accessible.** App A has already opened a local session. Synchronization requires proper back-channel/front-channel logout or a dedicated session invalidation/revalidation mechanism. Do not assume every RP receives logout events automatically.

**(5) The ID Token expires, yet the user can still access App A.** The app session has its own lifetime. To enforce continuous checks, design session max age/revalidation. Do not treat `idToken.exp` as a timer that deletes `HttpSession` by default.

**(6) An admin removes a permission in IAM, but the old session still has `ROLE_ADMIN`.** `GrantedAuthority` values are snapshotted at login. Invalidate sessions upon permission-change events or check current permissions at decision points.

**(7) The user is allowed to log into the IdP but rejected by the app.** The external identity may not be linked yet, the local account may be disabled, or permissions may be missing. Distinguish IdP authentication from application account provisioning and authorization.

**(8) `preferred_username` or `email` changes and creates a new account.** The lookup key is unstable. Switch to OIDC (`iss`, `sub`); treat email/name only as updatable metadata.

**(9) A logged-in Account B is used to link a new IdP to Account A.** The linking flow failed to protect the current session and CSRF/nonce, or lacked a re-authentication step. Verify the currently signed-in account's authority, enforce state to prevent login-CSRF, and prevent external identity hijacking.

**(10) The application uses multiple OIDC clients or tenants and permission mix-ups occur.** Do not rely solely on `sub` or client name; verify exact issuer, subject, tenant, and client context; perform role mapping at the appropriate trust boundary.

**(11) Creating an account just because the IdP returned `email_verified=true`.** Verified email is information from one issuer and does not by itself prove local account ownership or an invitation. Apply a dedicated JIT provisioning policy.

**(12) Creating a session on every API Bearer request, causing session sprawl.** Choose `oauth2Login` for browser flows and `oauth2ResourceServer` for APIs properly; configure `SessionCreationPolicy.STATELESS` for APIs when needed instead of forcing every auth mechanism into one filter chain.

**(13) App session cookies leak or get fixed.** Review HTTPS, Secure/HttpOnly/SameSite, session fixation, session ID rotation, and logout; never pass session IDs in URLs or public logs.

**(14) Back-channel logout invalidates too many sessions by mistake.** The endpoint failed to verify the logout token and issuer/audience/`sid`/`sub`. Use the framework per spec, a precisely correlated session registry, and test multi-tenant scenarios.

**(15) Using an access token from App A to call App B's API without checking audience.** Access tokens are issued for specific resources/audiences. App B must only trust tokens intended for B under its policy; **sharing an IdP does not mean every token is valid across services**.

**(16) OIDC data gets written to logs.** Never log ID Tokens, access/refresh tokens, cookies, authorization codes, nonce/state, or full personal profiles. Audits should log timestamps, appropriately masked or hashed issuer/IDs, local account, event, and outcome.

## 12. Essential Test Matrix

| Case | Expected Behavior |
| --- | --- |
| Valid OIDC token, (`iss`, `sub`) has an active link | Logs into the exact local account |
| Same `sub` but different issuer | Does not mistakenly link to the account |
| Duplicate email but different `sub` | Does not automatically merge local accounts |
| Invalid `iss`/`aud`/signature/`nonce` | Rejected during OIDC validation; no app session created |
| Link missing and JIT disabled | Rejected or routed to secure registration flow |
| Local account disabled | Rejected even though IdP authentication succeeded |
| User has 2 validly linked external identities | Both log into the same localAccountId |
| Two concurrent requests link the same external identity to two accounts | One wins via transaction/unique constraint; the other is rejected |
| Log into App A then visit App B | App B gets its own session; IdP may use SSO to avoid a password prompt |
| Log out of App A | App A loses its session; IdP/App B depend on separate logout flows |
| IdP logout without back-channel | Do not assume local sessions are cleared; evaluate actual policy |
| Valid back-channel logout | Relevant RP invalidates the exact session matching `sid`/`sub` and client |
| App session timeout while IdP SSO cookie is still valid | Re-login may be fast without showing the IdP login form |
| Permission revoked on local account | Permission is gone after the configured revalidation interval |
| Lost cookie / hostname change / misconfigured reverse proxy | Callback/session issues are diagnosed accurately without bypassing state checks |
| Cross-site POST /logout or /link | CSRF protection and authentication checks block unauthorized actions |

For end-to-end testing, use a test IdP supporting real OIDC, synchronized clocks, a browser storing both types of cookies, and at least two RPs. Unit tests for mapping only prove the (`iss`, `sub`) -> account rule; they **do not replace** validation tests for ID Tokens, session cookies, login-CSRF, logout, or permission changes.

## 13. Checklist for Implementing an SSO + Local Session System

1. Define **sources of truth**: the IdP owns the authentication event and `(iss, sub)`; the application owns `localAccountId`/permissions/sessions.
2. Validate OIDC/SAML using a standards-compliant library for the exact issuer, audience, client registration, and redirect URI.
3. Design the link table with a unique constraint on external identity, tenant scope, status, and audit fields.
4. Define JIT provisioning, linking, and unlinking rules; never equate accounts by email.
5. Configure `Authentication` persistence in `SecurityContextRepository`; choose appropriate cookie/session lifetimes and session store.
6. Load `GrantedAuthority` from the account/policy; choose how to invalidate sessions on permission changes or user lockouts.
7. Clearly define **local logout**, **IdP logout**, **global logout**, and the corresponding mechanisms actually supported by the IdP/RPs.
8. Enforce CSRF/state/nonce, HTTPS, session fixation protection, and cookie attributes; limit tokens/PII in logs.
9. Test at least two IdPs and two applications when deploying multi-provider SSO; test email changes, pairwise `sub` changes, tenant changes, and cross-app logout.
10. Define procedures for losing an IdP account, unlinking, access recovery, and migration without granting wrong access to another account.

### Official References

- OpenID Connect Core 1.0, `iss`/`sub` and Claim Stability: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security — OAuth2 Login Core Configuration (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
- Spring Security — OAuth2 Login Advanced Configuration (authority and OIDC user service): https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — Logout Support: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — OIDC Logout: https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/login/logout.html

**Key takeaway:** SSO lets the IdP authenticate an external identity; the application must link that identity to a local account in a controlled way, grant permissions per its own policy, and manage its own login session. Never treat the SSO cookie, ID Token, access token, account link, and `HttpSession` as the same entity.
