# Distinguishing Application Permissions from User Permissions in OAuth2 and Spring Security

## 1. Why can a valid access token still represent the wrong principal?

An enterprise application has different API call flows:

- Alice signs in to the documents portal and clicks to read one of her own documents.
- A nightly reporting service obtains a token on its own to aggregate data authorized for the enterprise.
- A backend receives Alice's request, then calls the document service on Alice's behalf.
- A third-party integration app is granted permission by an administrator to manage certain data sources.
- Bob holds the ADMIN role in tenant A, but only VIEWER in tenant B.

All of these may use `Authorization: Bearer ...`, yet **not every access token represents a signed-in human user**. OAuth2 distinguishes two authorization patterns:

1. **Delegated / user-delegated access**: an application is authorized to act **on behalf of a user** who participated in the authorization flow.
2. **Application-only / app-only access**: an application or service is granted permissions **in its own right**, not as a specific user.

When a resource server receives a token, it must accurately determine the **caller's principal**, the **client application**, the **token's granted permissions**, the **tenant/resource**, and **business policy**. If a backend uses its own `client_credentials` token to access "Alice's" data merely because the request contains `userId=alice`, it easily becomes a **confused deputy**: a broadly privileged application is abused to act for an unauthorized caller.

**Lesson objectives**: distinguish permission types conceptually and in Spring Security Resource Server/OAuth2 Client implementations, enforce separate policies for USER and APPLICATION actors, experiment with Java 17+, distinguish token scopes/roles from business authorization, and detect privilege escalation in service-to-service or on-behalf-of flows.

## 2. Four OAuth2 roles that must not be conflated

In OAuth2, a system can involve:

| Role | Meaning | Example |
| --- | --- | --- |
| **Resource owner** | Entity capable of granting access to a resource, typically the user in a delegated flow | Alice |
| **Client** | Application requesting access to resources via an API | web-portal, reporting-bot |
| **Authorization server** | Authenticates/authorizes per grant and issues access tokens | IdP/authorization service |
| **Resource server** | API receiving tokens, validating them, and enforcing resource access decisions | document-api |

A client is **not necessarily the resource owner**. In `client_credentials`, the client obtains an access token for **itself**. In `authorization_code`, a user participates, yet the access token may still carry only **API scopes** rather than all business roles, owner relationships, or current ACLs.

This leads to four distinct questions:

```text
WHO is calling?          -> user, application, or a verified delegation?
WHICH client is involved? -> client_id / authorized party
WHAT token allows?       -> scopes, permissions, audience, validity
WHAT resource permits?   -> tenant, owner, ACL, policy, state and action
```

A token with `scope=documents.read` usually proves that the authorization server granted an **allowed API call scope**. It does not prove that Document 42 belongs to Alice, is not deleted, is shared with Alice, or resides in a tenant with active membership.

## 3. User-delegated vs. app-only: core comparison table

| Attribute | User permissions (delegated) | Application permissions (app-only) |
| --- | --- | --- |
| Acting principal | Actual user in a delegated context | Client/service/application |
| Common grants | Authorization Code + PKCE, or an approved delegated/token-exchange flow | Client Credentials |
| User login involved? | Usually yes, per the authorization flow | Not required; typically no |
| OAuth permissions | Delegated scopes granted to user/client | Scopes/roles/app permissions assigned to the client |
| Business constraints | User membership, role, ACL, tenant, resource owner **and** scopes | App identity, app grant, tenant/resource scope **and** scopes |
| Audit subject | User ID, client ID, authorization context | Client/service ID, optional initiator *if verified separately* |
| Data visibility | Within delegated scope and user's actual rights | Within service/app permissions explicitly granted by admins |
| Can "assume user rights" by default? | No; requires proper delegation | **No**; there is no implicit user |
| Policy changes | Changing user role/ACL can reduce rights | Revoking grant/role/app assignment reduces rights |
| Key risks | User token used on wrong audience, role bleed, IDOR | Confused deputy, overly broad access, all requests sharing one bot token |

A `GET /me` endpoint typically requires a **verified user**. An app-only token must never be mapped to a default user or the service owner. An endpoint `POST /internal/reports/rebuild` may accept **only authorized services**, and must not automatically allow any user holding a similarly named authority.

**Do not treat "app-only" as "administrator."** App-only only states that the actor is an application. Even if a client holds `reports.generate`, that does not mean it can access every document in every tenant or perform all CRUD operations.

## 4. Three permission layers: OAuth permission, app/user role, data permission

In practice, the word "permission" appears in multiple places:

1. **OAuth scope / application permission**: permissions carried in the access token or managed in the authorization server/IdP.
2. **What role does the internal app/user have?** E.g., app `reporting-bot` is allowed to generate reports for tenant A; Alice holds EDITOR in tenant A.
3. **Who may act on the object itself?** E.g., Document 42 belongs to tenant A, owner Bob, READ share grant for Alice.

A checklist formula:

```text
ALLOW delegated =
    validAccessTokenForThisAPI
    AND recognizedDelegatedUser
    AND clientAllowedForThisOperation
    AND tokenScopeAllowsAction
    AND userActiveAndTenantMembershipValid
    AND resourceTenantAndObjectPolicyAllows
    AND contextConditionsHold

ALLOW app-only =
    validAccessTokenForThisAPI
    AND recognizedAppIdentity
    AND appAssignedForThisOperation
    AND tokenPermissionAllowsAction
    AND appTenantAndResourceGrantAllows
    AND contextConditionsHold
```

The difference lies in the **user entitlement** vs. **application entitlement** branches. Neither branch may silently fall back to the other when data is missing.

For example, Alice has `document:read` in tenant B, but the delegated token has only `reports.read`: Alice cannot use that token to read documents through an endpoint requiring `documents.read`. Conversely, if the token has `documents.read` but Alice was removed from tenant B, reading in B is still denied by data policy. An app-only token with `documents.read` also cannot read documents in tenant B if the app grant is restricted to tenant A.

## 5. Authorization Code + PKCE flow: calling APIs on behalf of a user

Conceptual example:

```text
Alice                  Browser / Web Portal         Authorization Server
  |                            |                             |
  |--- Click "Sign in" ------->|                             |
  |                            |--- /authorize + PKCE ------>|
  |<------------ browser redirects / authentication -------->|
  |                            |<--- authorization code -----|
  |                            |--- code + verifier -------->|
  |                            |<--- delegated access token --|
  |                            |                             |
  |--- Read Doc42 ------------>|                             |
                               |--- Bearer delegated token --->
                                             Document API
                               <--- data allowed for Alice ---|
```

Authorization Code + PKCE is appropriate for public clients and user-login applications; confidential web clients can also use Authorization Code with client authentication and PKCE depending on configuration. The token is meant for a designated resource server (`aud`), not to be sent arbitrarily to any API.

**Core point:** a client holding a token from Alice's flow **cannot change `userId` in the HTTP body** to act as Bob. The resource server must take the user subject from the verified token or verified delegation and check it against the resource. When Alice signs out or permissions are revoked, the system must define how tokens and caches are invalidated per security requirements.

### Delegated does not mean the browser always holds the token

With a BFF (Backend for Frontend), the backend can hold tokens on behalf of the browser and call APIs for Alice. Regardless of where the token is stored, business logic must still know **the exact delegated subject Alice**; having a service credential in the backend must never turn all user requests into app-only superuser calls.

## 6. Client Credentials flow: an application calling an API as itself

A scheduled worker requires no user sign-in:

```text
Reporting Worker                  Authorization Server
      |                                    |
      |-- authenticate client ------------>|
      |   grant_type=client_credentials    |
      |   requested scope / resource       |
      |<-- app access token ---------------|
      |                                    |
      |---------- Bearer app token --------> Document API
      |                                     verify app identity, scope,
      |                                     tenant grant and action
      |<-------- report data / deny --------|
```

Protocol-level HTTP example (client credential values are illustrative only; **never place secrets in URLs or production code**):

```http
POST /oauth2/token HTTP/1.1
Host: authorization.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

grant_type=client_credentials&scope=reports.read
```

The authorization server authenticates the client itself and issues a token per that client's configuration. The token may carry OAuth scopes, application roles, or provider-specific permissions. It is **not** a user's access token simply because the app is owned by an employee.

For an internal API, service principal `reporting-bot` is granted only specific rights such as:

```text
client_id: reporting-bot
allowed tenants: tenant-a
allowed actions: READ_AGGREGATED_REPORTS
max data classification: INTERNAL
expires/requires service credential validation
```

That is an **app assignment** governed by a trusted server. Any caller sending `X-User: alice` alongside an app token does not become Alice. If a report needs data that only Alice is permitted to read, the service must have **verified delegated authorization** or an appropriate workflow approval—never self-escalate using an app-only credential.

### Trap in servers handling both user requests and client credentials

A backend might accept Alice's request while also configuring `OAuth2AuthorizedClientManager` to obtain a client-credentials token. If a controller calls a downstream API with the app-only token and puts `userId` from the browser into the body, downstream only knows the app authenticated; enforcing Alice's policy requires a trusted delegation protocol, not a plain `userId` field.

A powerful service credential in a backend creates a **confused deputy** risk: attackers exploit the service's privileges instead of their own. Enforce authorization before the backend initiates downstream calls, constrain app grants, and re-verify downstream per policy.

## 7. Do not infer token kind from a single arbitrary claim

OAuth2 defines no single universal JWT claim across all IdPs to distinguish delegated from app-only tokens. Common observations:

| Signal | What can it indicate? | Why is it insufficient alone? |
| --- | --- | --- |
| `sub` | Subject assigned by issuer | In client credentials, subject may be the client itself |
| `client_id` / `azp` | Verified client / authorized party | Can appear in both user-delegated and app-only tokens |
| `scope` / `scp` | Granted token scopes | Does not prove a user exists or proves ownership |
| `roles` | Roles/app roles per IdP schema | May appear in user **or** app tokens depending on provider |
| `grant_type` / `gty` | If included by issuer, may relate to OAuth grant | Not guaranteed to exist in every access token |
| `iss` | Token issuer | Must verify issuer trust before trusting claims |
| `aud` | Target resource server/API | Not a user/app role |
| `exp`, `nbf` | Token lifetime | Does not prove object/ACL grants are still active |

**RFC 9068** (JWT Profile for OAuth2 Access Tokens) states that for grants with a resource owner, `sub` **SHOULD** identify the resource owner; for grants without a resource owner such as client credentials, `sub` **SHOULD** identify the client application. "SHOULD" is not an invariant across every issuer. `client_id` is required in that profile, yet **not every access token follows this profile**: access tokens can also be opaque and require introspection.

Consequently, the resource server must rely on the **trusted issuer's specific token contract** to classify the caller. Designs may use:

- An issuer-guaranteed, signed token type/subject type; or
- Separate policies per authorization server, audience, issuer, and client assignment; or
- Token introspection returning trustworthy metadata; or
- Two distinct audiences/issuers or two clearly separated token types.

**Never trust** an `X-Actor-Type: USER` header, a `{"kind":"delegated"}` request body, or an unverified JWT payload to turn an app principal into a user principal.

## 8. Two sample access tokens to understand claims

### 8.1. Sample delegated token

```json
{
  "iss": "https://idp.example.test/",
  "aud": "document-api",
  "sub": "user-alice",
  "client_id": "web-portal",
  "scope": "documents.read",
  "exp": 1800000000
}
```

These are **illustrative JWT claims only**, not a real/signed token. Issuers following the JWT access-token profile also require `iat`, `jti`, and a `typ` header; this example is shortened to focus on identity. The resource server must perform full validation per issuer/profile before using it.

If the issuer's contract confirms this is a delegated user token, the policy can attach:

```text
USER(subjectId=user-alice, clientId=web-portal)
  has delegated scope documents.read
  AND is member of selected tenant
  AND can READ this Document by owner/ACL
```

### 8.2. Sample app-only token

```json
{
  "iss": "https://idp.example.test/",
  "aud": "document-api",
  "sub": "reporting-bot",
  "client_id": "reporting-bot",
  "scope": "reports.read",
  "exp": 1800000000
}
```

There is no user Alice. The policy must evaluate:

```text
APPLICATION(clientId=reporting-bot)
  has app capability reports.read
  AND has approved access to selected tenant
  AND can READ the report data allowed to this service
```

**You cannot treat `sub` in both tokens as a database "userId."** An app-only token has `sub=reporting-bot`; if the system looks up a user record by that name or an owner ID collides, false permissions can be granted.

### Token validation is an independent step

At minimum, verify:

- Signature, allowed key/algorithm, and token format/profile.
- Trusted issuer `iss`.
- Audience `aud` matching this API.
- `exp`, `nbf`, and reasonable clock skew.
- Scope/permission presence granted by the issuer.
- Client authorization and caller kind per issuer-specific contract.
- If opaque, introspection against a trusted Authorization Server with clear caching/freshness.

Never accept an **ID token** (meant for an OIDC client authenticating a user) as an OAuth2 API access token. An ID token's audience is typically the client ID, not the resource server; accepting it creates a token-substitution vulnerability.

## 9. Scopes, roles, authorities: what does Spring Security see?

Spring Security OAuth2 Resource Server JWT by default typically reads `scope` or `scp` from a verified JWT and maps them to `GrantedAuthority` instances prefixed with `SCOPE_`.

Example:

```json
{
  "scope": "documents.read reports.read"
}
```

can become:

```text
SCOPE_documents.read
SCOPE_reports.read
```

An expression:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public DocumentView readDocument(Long id) {
    // ...
}
```

checks only the authority **attached to `Authentication`**. By default it **does not**:

- Verify whether this is a user token rather than an application token.
- Resolve user business roles from tenant membership.
- Check Document ID, owner, share grants, or status.
- Ensure the client is permitted to perform this delegated action.
- Separate an `ADMIN` role in tenant A from tenant B.

Therefore, never use `hasAuthority('SCOPE_documents.read')` as the sole protection when the API requires **user-specific data authorization**.

### Scopes and application roles have no universal mapping

In some IdPs, app-only permissions appear in `roles` while delegated permissions appear in `scp`. **Microsoft Graph / Microsoft Entra** is a common example distinguishing delegated permissions and application permissions. However, **that is a provider convention**, not a universally safe detection rule:

- A `roles` claim may contain **user** roles, **application** roles, or other domain mappings depending on issuer/API.
- A `scope` claim may appear in app-only tokens from other authorization servers.
- Some tokens have no readable JWT claims at all (opaque tokens).
- A token carrying a claim that looks like an app role may still have the wrong audience or issuer.

**Takeaway:** apply classification rules **versioned and verified for the specific issuer/token profile**. Never write `if (has("roles")) APP else USER` as a generic rule.

## 10. Explicitly typed caller model: USER vs. APPLICATION

A clean Java 17 design can use a sealed type to represent both caller kinds:

```java
public sealed interface VerifiedCaller
        permits DelegatedUserCaller, ApplicationCaller {

    String clientId();
    String tenantId();
}

public record DelegatedUserCaller(
    String userId,
    String clientId,
    String tenantId
) implements VerifiedCaller {}

public record ApplicationCaller(
    String clientId,
    String tenantId
) implements VerifiedCaller {}
```

These are **Java 17 domain types**; `tenantId` in them must originate from a **verified tenant**, never assigned directly from an unchecked request path. `DelegatedUserCaller.userId` is the user subject from a trusted issuer or internal identity mapping; `ApplicationCaller.clientId` is the client verified by the AS.

Using two distinct types prevents policies from accidentally assuming every `Authentication.getName()` is a user:

```java
switch (caller) {
    case DelegatedUserCaller user -> checkUserRead(user, document);
    case ApplicationCaller app -> checkAppRead(app, document);
}
```

**Java 17 note:** switch pattern matching over sealed types in this snippet is a **preview feature** in Java 17 and should not be used as default runnable code without preview enabled. In Java 17 production code without preview enabled, use `if (caller instanceof DelegatedUserCaller user) ... else if (...)`, or an explicit visitor. The runnable example at the end uses `instanceof` so standard `javac`/`java` runs without `--enable-preview`.

### Token classifier interface with an explicit contract

```java
public interface VerifiedCallerResolver {
    VerifiedCaller resolve(
        org.springframework.security.core.Authentication authentication,
        String requestedTenantId
    );
}
```

A safe implementation must:

1. Accept an `Authentication` that has passed Resource Server validation.
2. Identify the configured issuer/token profile.
3. Classify user/app using **trusted issuer metadata**, not by guessing from claim names.
4. Verify the client ID belongs to an approved registry/assignment.
5. For users: map subject to user identity and verify tenant membership.
6. For apps: verify client assignment within the tenant and purpose scope.
7. Reject unclassifiable tokens or tokens missing required claims.
8. Never fall back to "default admin" when information is incomplete.

**There is no built-in generic `VerifiedCallerResolver` in Spring Security** that handles all of these steps for every IdP. This is an application-owned abstraction.

## 11. Effective delegated permission is an intersection, not a union

Suppose Alice has:

```text
Alice in tenant-a:
  user permissions = {documents.read, documents.edit}

Web Portal token for Alice:
  token scopes = {documents.read}

Document42:
  tenant = tenant-a
  owner = alice

Document43:
  tenant = tenant-a
  owner = bob
  no share for alice
```

Results:

| Request | Token scope | User/domain permission | Result |
| --- | --- | --- | --- |
| Alice reads Document42 | Has documents.read | Owner READ | ALLOW |
| Alice edits Document42 | **No** documents.edit | User has EDIT but token lacks scope | DENY |
| Alice reads Document43 | Has documents.read | Not owner/shared | DENY |
| Alice switches to tenant B | Has documents.read | No membership in B | DENY |
| Bob calls API using Alice's token | Token still carries Alice's subject | System sees Alice per token; this is token theft | Protect tokens; do not read Bob's name from request |

Typically:

```text
effective delegated permission
    ⊆ token scopes granted to client
    ∩ resource owner's current business rights
    ∩ resource/tenant policy
    ∩ contextual constraints
```

Set notation here expresses intersecting conditions, not literal set intersection implying every system shares one permission taxonomy.

### Consent does not grant all data permissions

User/admin consent for `documents.read` only says the application may request read access within granted bounds. It does not make every document in the tenant public to the client. The resource server remains responsible for checking ACL/owner/tenant and enforcing field-level restrictions.

If a consent is delegated, effective execution is bounded by **the user's rights**. If it is an application permission, bounds are **app assignments** and API policy. Distinguish the two rather than relying solely on labels in an IdP admin portal.

## 12. Application permissions: app principals need their own grants and data bounds

Suppose app `invoice-sync` is granted permission to read invoices in tenant A:

```text
service/application identity: invoice-sync
tenant assignment: tenant-a
allowed API action: invoices.read
allowed resource domain: invoices tagged for ERP sync
max classification: INTERNAL
approval: integration-admin
```

When calling:

```http
GET /api/tenants/tenant-a/invoices/991
Authorization: Bearer <invoice-sync-app-token>
```

The API must verify:

1. Token is verified; issuer/audience and app identity are valid.
2. App has an assignment for tenant A.
3. App is granted action `invoices.read`.
4. Invoice 991 belongs to tenant A and is marked eligible for ERP sync.
5. Invoice is not deleted/locked per policy.
6. Returned payload includes only fields permitted for the integration.

Do not skip the "only invoices tagged for sync" restriction just because the app token has `invoices.read`. An application may be permitted to read **data that regular users are not**, but that must be an **approved app-specific business policy**, not a default bypass.

### A service account is not a fake user

A system may store service accounts in a shared table alongside users, yet **principal types must remain distinct**. Avoid using `serviceAccount.email` to infer user ownership or placing services unconditionally into `ROLE_USER`. If an app needs internal administrative capabilities, model it with a service principal, explicit assignments, auditing, and restricted actions.

Even a global admin should be granted via an explicit separate policy; client credentials are never an automatic basis for granting `ROLE_ADMIN`.

## 13. Confused deputy: when a backend uses an app token to act for a user

This is the most notable pitfall when distinguishing the two permission types.

### Faulty flow

```text
Alice can read Doc10, cannot read Doc99
             |
             v
Frontend sends /documents/99?userId=alice
             |
             v
Backend uses client_credentials token with documents.read.all
             |
             v
Document API sees only APP/BACKEND with broad rights
             |
             v
Returns Doc99 even though Alice lacks permission
```

Here the backend becomes a **broadly privileged deputy**, executing Alice's unauthorized request. Without checking user policy, the downstream API cannot reliably infer "Alice requested this" from an app-only token.

### Fix 1: delegated token from the proper OAuth flow

```text
Alice -> BFF (session/user authenticated)
      -> obtains valid delegated access token for Document API
      -> Document API verifies Alice + client + scopes
      -> checks Alice tenant/owner/ACL for Doc99 -> DENY
```

Not every architecture or IdP permits passing tokens from browser to backend. The BFF must use a supported OAuth flow to obtain the right access token for the API, protecting tokens and CSRF/sessions where applicable.

### Fix 2: explicit trusted delegation / token exchange

Sometimes a backend uses token exchange/on-behalf-of:

```text
User token for intermediary
  -> trusted STS / authorization server
  -> delegated downstream token, correct audience
  -> downstream validates actor/user/client/delegation constraints
```

OAuth2 Token Exchange (RFC 8693) provides a framework for exchanging tokens using `subject_token` and `actor_token` per contract. However, **not every IdP supports it fully**, and you cannot self-exchange tokens simply by copying the `sub` claim into a new app-signed JWT.

Downstream must trust an **authoritative authorization server** for the delegation chain, scopes/actors, and audience; never trust a self-asserted request header claiming "on behalf of Alice."

### Fix 3: app-only backend + explicit domain authorization

Some workflows legitimately require app credentials in the backend, which must then enforce user permissions at the front boundary:

```text
User authenticated at gateway
 -> gateway/service checks user can initiate action on resource
 -> creates narrow, audited command with verified user + resource
 -> app service authenticates command producer
 -> rechecks command scope and app grant
 -> acts only within approved resource/action
```

For sensitive operations like DELETE, EXPORT, and SHARE, the backend should re-check or use a signed authorization context with expiry/replay protection, transaction policy, and auditing per the threat model. Never treat a plain `initiatedBy` string in a message queue as proof.

## 14. Access tokens should not be used interchangeably with ID tokens

An **OIDC ID token** primarily tells the client that a user authenticated under OpenID Connect. An **OAuth2 access token** is used to call a resource server/API.

| Token | Primary audience | Purpose |
| --- | --- | --- |
| ID token | OIDC client | Authenticates user identity to the client |
| OAuth access token | Resource server/API | Calls API within granted scopes |
| Refresh token | Authorization server | Requests new tokens when policy permits |

An API that accepts an ID token merely because it contains `sub=alice` is vulnerable to token substitution: a token whose audience and semantics were never meant for the API gets treated as authorization. Resource servers must require an **access token with the right audience and token profile**, never an ID token as an API bearer credential.

A `client_credentials` token typically does not need a refresh token; the service can re-authenticate as the client to obtain a new access token. Always rely on your authorization server and API contract rather than hardcoding assumptions from a `grant_type` string inside a token.

## 15. Spring Security Resource Server JWT: authenticate first, classify second

Spring Boot Resource Server is configured with the Resource Server + JOSE JWT dependencies and an issuer URI:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/
          audiences: document-api
```

This is an **example configuration**; `example.test` is not a real IdP. The `audiences` property is available in current Spring Boot/Spring Security configurations; depending on version, you may need a custom `OAuth2TokenValidator<Jwt>`. Never load tokens from an unfamiliar issuer at runtime just because the issuer URL appears inside an unverified JWT.

### A `SecurityFilterChain` for an API

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

This is a **Servlet Spring Security configuration fragment**. It requires a Spring MVC/Servlet application, JWT decoder/issuer/audience configuration, and real endpoints. CSRF/CORS, session strategy, security headers, and exception handling must match your client type: if the API uses cookies or browser sessions, do not blindly copy CSRF-disabling snippets meant for pure bearer-only APIs.

Note: `authenticated()` only confirms a valid `Authentication` exists. It **neither distinguishes** user vs. app types nor protects objects. Both protections belong in application policies/services or custom authorization managers.

### Running Spring Boot on WebFlux?

If the application is reactive, use `ServerHttpSecurity` + `SecurityWebFilterChain` and `@EnableReactiveMethodSecurity`; do not copy this Servlet class expecting equivalent behavior. The security semantics match, while the APIs differ. This lesson focuses on OAuth authorities rather than treating the two stacks as identical.

## 16. `JwtAuthenticationConverter` and scope mapping

For JWT access tokens, Spring Security by default creates a `JwtAuthenticationToken` and maps `scope`/`scp` into `SCOPE_*`.

Example customizing the claim name when an issuer uses a different claim:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public JwtAuthenticationConverter scopeConverter() {
    JwtGrantedAuthoritiesConverter grants =
        new JwtGrantedAuthoritiesConverter();
    grants.setAuthoritiesClaimName("scope");
    grants.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grants);
    return converter;
}
```

This is a **method fragment**. Registered as a bean and wired into `oauth2ResourceServer(...).jwt(jwt -> jwt.jwtAuthenticationConverter(...))`, it customizes authority conversion. Do not assume `roles` turns into `ROLE_*` or that roles belong to USER; mapping is **issuer-specific** and must be tested for both app-only and delegated tokens.

Code like:

```java
if (authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("SCOPE_documents.read"))) {
    return true;
}
```

is **insufficient** to grant read access to user data. Both app-only and delegated tokens may carry that authority depending on the issuer; you must distinguish caller kind and check data permissions.

### Do not turn every "role" into `ROLE_ADMIN`

A custom converter can extract roles from a JWT and create `ROLE_ADMIN`. If an app-only token has an `Admin` app role per the provider, the mapper must never interpret it as **user admin rights** in the domain. Use clear namespaces:

```text
token scope:        SCOPE_documents.read
trusted app grant:  APP_REPORT_EXPORT
trusted user role:  TENANT_A_EDITOR (when membership is verified)
```

These strings are **illustrative internal conventions**, not standard authorities generated automatically by Spring. The `ROLE_` name carries special meaning for `hasRole(...)`; never let one role string mean two different things for USER and APPLICATION.

## 17. Classifying callers in Spring: the contract must come from the issuer

An example application might define a custom claim `actor_kind` signed and guaranteed by its internal authorization server to be either `delegated_user` or `application`. This is not a standard OAuth2 claim; use it only when **your own IdP emits it accordingly**.

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

public final class TrustedActorClassifier {
    public VerifiedCaller classify(
            JwtAuthenticationToken authentication,
            String verifiedTenantId) {

        Jwt jwt = authentication.getToken();
        String kind = jwt.getClaimAsString("actor_kind");
        String client = jwt.getClaimAsString("client_id");

        if (client == null || client.isBlank()) {
            throw new AccessDeniedException("Unknown OAuth client");
        }

        // These calls must use trusted registry/tenant grants in the app.
        if ("delegated_user".equals(kind)) {
            String userSubject = jwt.getSubject();
            if (userSubject == null || userSubject.isBlank()) {
                throw new AccessDeniedException("Missing user identity");
            }
            return new DelegatedUserCaller(
                userSubject, client, verifiedTenantId);
        }

        if ("application".equals(kind)) {
            return new ApplicationCaller(client, verifiedTenantId);
        }

        throw new AccessDeniedException("Unrecognized actor kind");
    }
}
```

This is an **illustrative component class** using the `VerifiedCaller`/records defined earlier. `verifiedTenantId` must be verified **before calling**, e.g., via server-side membership/client assignment; never pass `@PathVariable tenantId` directly. This class only classifies the actor and **does not grant any permissions**. Downstream policy must query membership/grants.

A production implementation must verify:

- `JwtAuthenticationToken` was produced by a trusted decoder with a matching token profile.
- Issuer and audience were validated per contract.
- Client is allowed in the system's registry.
- The `actor_kind` claim is issuer-managed, not a client-supplied request field.
- For delegated: user identity and client consent are valid.
- For app: app assignment and permissions are governed.
- If the issuer does not emit this claim: **do not guess**—implement a different issuer-specific classifier.

**Do not use this class directly with Entra/Keycloak/Okta unless they emit `actor_kind` under that exact contract.** It is a suggested abstraction to avoid actor confusion, not a built-in Spring Security class.

## 18. Domain policy: two separate decision branches

An application service can define:

```java
public boolean canRead(
        VerifiedCaller caller,
        DocumentFacts resource,
        Set<String> tokenScopes) {

    if (caller == null || resource == null
            || !tokenScopes.contains("documents.read")
            || resource.deleted()) {
        return false;
    }

    if (!caller.tenantId().equals(resource.tenantId())) {
        return false;
    }

    if (caller instanceof DelegatedUserCaller user) {
        return users.isActiveMember(
                   user.userId(), user.tenantId())
            && (
                user.userId().equals(resource.ownerId())
                || shares.hasActiveGrant(
                    user.userId(), resource.id(), "READ")
            );
    }

    if (caller instanceof ApplicationCaller app) {
        return appAssignments.canRead(
            app.clientId(), app.tenantId(), resource.id());
    }

    return false;
}
```

This is a **Java-style pseudocode fragment**: `DocumentFacts`, `users`, `shares`, and `appAssignments` are domain objects/services to be wired into a service class with dependency injection, transaction/context handling, and cache invalidation. `tokenScopes` must come from the verified token or authorization context, never from client JSON.

Key properties:

1. Shared conditions: right tenant, active resource, right action/scope.
2. User branch: **active membership + owner/ACL**.
3. App branch: **approved app assignment + resource scope**.
4. No path from **app → implicit user**.
5. Unknown caller → DENY.
6. User business roles and application privileges are never collapsed into one `ROLE_ADMIN`.

### Preventing TOCTOU

If a handler checks `canRead` and then runs an unscoped `documents.findById(id)`, a race or another code path can leak data. For critical queries, use:

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :verified_tenant
  AND deleted = FALSE;
```

For delegated USERs, add owner/ACL/share predicates; for app-only, add app assignment/resource grant predicates per domain rules. For updates/deletes, use conditional SQL or appropriate transactions/locks rather than post-write checks.

**Never** let an app-only batch service call a broad `findAll()` repository method and filter afterward using a `userId` header.

## 19. OAuth2 Client in Spring: requesting app-only tokens for the right purpose

A Spring Boot service needing to call a downstream API with client credentials can register a dedicated client:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-client:
            provider: reports-idp
            client-id: reporting-bot
            client-secret: \${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          reports-idp:
            token-uri: https://idp.example.test/oauth2/token
```

This is an **example configuration**, not real credentials. In real YAML files, supply secrets via a secret manager or environment variables, avoiding plaintext commits. The string `\${REPORTS_CLIENT_SECRET}` is a Spring runtime configuration placeholder, not an unfinished item in the lesson.

### `AuthorizedClientServiceOAuth2AuthorizedClientManager`

For a **Servlet/unattended service** using Spring Security OAuth2 Client, you can configure:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ReportingClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager appClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

This is a **Spring configuration class**; it requires Spring Security OAuth2 Client dependencies, real registration/provider settings, secure storage, and lifecycle management. WebFlux uses **`ReactiveOAuth2AuthorizedClientManager`** and its reactive service counterpart; never replace it with this Servlet manager plus `block()` on an event loop.

Requesting a token by registration:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public String fetchAppToken(OAuth2AuthorizedClientManager manager) {
    OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("reports-client")
            .principal("reporting-service")
            .build();

    OAuth2AuthorizedClient authorized =
        manager.authorize(request);

    if (authorized == null) {
        throw new IllegalStateException(
            "No authorized client for reports-client");
    }

    return authorized.getAccessToken().getTokenValue();
}
```

This is a **method fragment** (not a standalone class) illustrating the mechanism; be careful never to log or serialize raw token strings. `principal("reporting-service")` is the **management key for `OAuth2AuthorizedClient` in the service application**; **it does not create a Reporting Service user on the resource server**. With client credentials, the token still represents the client authenticated by the authorization server.

### Common confusion around caching and principals

A web app with many users may use `OAuth2AuthorizedClientManager` to manage **authorized clients per user session/principal**, whereas an app-only background job typically uses a dedicated service key. Never use Alice's principal key in a client-credentials request and then assume the resulting access token became Alice's delegated token.

A report triggered by Alice may need to store **initiator metadata** for auditing and business-layer authorization. Yet the identity of the access token sent downstream remains the **application** if the actual grant is client credentials.

## 20. JWT converters should not merge app and user permissions

Sometimes an issuer puts a `roles` claim in both app-only and delegated tokens; suppose we customize it:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

JwtGrantedAuthoritiesConverter roles =
    new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
```

This is a **converter fragment**, not a complete configuration. The danger lies not in reading claims, but in **misinterpreting scopes/roles**:

- `ROLE_ADMIN` from an app grant is not automatically a global USER ADMIN.
- `ROLE_EDITOR` from a user token does not necessarily apply across all tenants.
- `SCOPE_documents.read` does not prove owner/ACL permissions.
- Changing an authority prefix does not transform the nature of the token.

A clearer design builds policy methods that distinguish `VerifiedCaller`, then checks **token scopes** and **domain grants separately**. If canonical authorities are needed, namespace app and delegated permissions consistently by issuer type, with unit tests preventing principal-kind escalation.

## 21. Standalone Java 17: same scope, two distinct permission sources

The following example **requires no Spring Security or OAuth libraries**. It simulates actors already verified by an authorization server/Resource Server, then models policy evaluation. The goal is to prove **the same `documents.read` scope does not grant the same data access**: USER requires membership/ownership; APPLICATION requires an app assignment on the resource.

Save `OAuthActorPermissionDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class OAuthActorPermissionDemo {

    sealed interface Actor permits UserActor, AppActor {
        String tenantId();
        Set<String> scopes();
    }

    record UserActor(
        String userId,
        String clientId,
        String tenantId,
        Set<String> scopes
    ) implements Actor {}

    record AppActor(
        String clientId,
        String tenantId,
        Set<String> scopes
    ) implements Actor {}

    record Document(
        long id, String tenantId, String ownerId, boolean deleted
    ) {}

    static final Map<String, Boolean> MEMBERSHIPS = Map.of(
        "alice|tenant-a", true,
        "bob|tenant-a", true,
        "alice|tenant-b", false
    );

    static final Map<String, Set<Long>> APP_GRANTS = Map.of(
        "reporting-bot|tenant-a", Set.of(11L)
    );

    static final Document A10 =
        new Document(10, "tenant-a", "alice", false);
    static final Document A11 =
        new Document(11, "tenant-a", "bob", false);
    static final Document B20 =
        new Document(20, "tenant-b", "carol", false);

    static boolean readAllowed(Actor actor, Document doc) {
        if (actor == null || doc == null || doc.deleted()
                || !actor.scopes().contains("documents.read")
                || !actor.tenantId().equals(doc.tenantId())) {
            return false;
        }

        if (actor instanceof UserActor user) {
            boolean member = MEMBERSHIPS.getOrDefault(
                user.userId() + "|" + user.tenantId(), false);
            return member && user.userId().equals(doc.ownerId());
        }

        if (actor instanceof AppActor app) {
            Set<Long> permitted = APP_GRANTS.getOrDefault(
                app.clientId() + "|" + app.tenantId(), Set.of());
            return permitted.contains(doc.id());
        }

        return false;
    }

    static boolean canRunReport(Actor actor) {
        return actor instanceof AppActor app
            && app.clientId().equals("reporting-bot")
            && app.scopes().contains("reports.generate");
    }

    static boolean canReadOwnProfile(Actor actor) {
        return actor instanceof UserActor user
            && MEMBERSHIPS.getOrDefault(
                user.userId() + "|" + user.tenantId(), false);
    }

    static String label(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        UserActor alice = new UserActor(
            "alice", "web-portal", "tenant-a",
            Set.of("documents.read"));
        UserActor bob = new UserActor(
            "bob", "web-portal", "tenant-a",
            Set.of("documents.read"));
        UserActor revoked = new UserActor(
            "alice", "web-portal", "tenant-b",
            Set.of("documents.read"));
        UserActor noScope = new UserActor(
            "alice", "web-portal", "tenant-a",
            Set.of("reports.read"));

        AppActor reporting = new AppActor(
            "reporting-bot", "tenant-a",
            Set.of("documents.read", "reports.generate"));
        AppActor wrongTenant = new AppActor(
            "reporting-bot", "tenant-b",
            Set.of("documents.read", "reports.generate"));
        AppActor unknown = new AppActor(
            "unknown-app", "tenant-a",
            Set.of("documents.read"));

        System.out.println("Alice own A10: "
            + label(readAllowed(alice, A10)));
        System.out.println("Alice Bob A11: "
            + label(readAllowed(alice, A11)));
        System.out.println("Bob own A11: "
            + label(readAllowed(bob, A11)));
        System.out.println("Reporting app A11 grant: "
            + label(readAllowed(reporting, A11)));
        System.out.println("Reporting app A10 not granted: "
            + label(readAllowed(reporting, A10)));
        System.out.println("Reporting app tenant B: "
            + label(readAllowed(wrongTenant, B20)));
        System.out.println("Unknown app A11: "
            + label(readAllowed(unknown, A11)));
        System.out.println("Alice missing scope: "
            + label(readAllowed(noScope, A10)));
        System.out.println("Alice revoked tenant B: "
            + label(readAllowed(revoked, B20)));
        System.out.println("App report action: "
            + label(canRunReport(reporting)));
        System.out.println("User report action: "
            + label(canRunReport(alice)));
        System.out.println("User profile action: "
            + label(canReadOwnProfile(alice)));
        System.out.println("App profile action: "
            + label(canReadOwnProfile(reporting)));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac OAuthActorPermissionDemo.java
java OAuthActorPermissionDemo
```

Exact stdout:

```text
Alice own A10: ALLOW
Alice Bob A11: DENY
Bob own A11: ALLOW
Reporting app A11 grant: ALLOW
Reporting app A10 not granted: DENY
Reporting app tenant B: DENY
Unknown app A11: DENY
Alice missing scope: DENY
Alice revoked tenant B: DENY
App report action: ALLOW
User report action: DENY
User profile action: ALLOW
App profile action: DENY
```

**Explanation:**

- Alice is a user with READ scope, yet cannot read Bob's document A11 merely for being in the same tenant.
- Bob holds owner entitlement on A11, so READ is allowed.
- Reporting bot is an **application** with an explicit app grant only for A11. It cannot read A10 even though Alice owns A10 in the same tenant.
- Reporting bot has no grant in tenant B and cannot "read everything" just by holding an app token.
- An unknown app with the same scope but no assignment → DENY.
- Alice missing the token scope or having her tenant B membership revoked → DENY.
- `canRunReport` accepts only an application with the needed identity/scopes; users cannot invoke service-only jobs.
- `canReadOwnProfile` accepts only a user with membership; an app-only actor has no user profile to read.

**Limitation:** actors are constructed directly in Java rather than extracted from verified JWTs. `APP_GRANTS`/`MEMBERSHIPS` are in-memory maps with no database, TTL, revocation events, transactions, or concurrency; real applications must derive actors from token contracts and trusted authorization stores. The demo illustrates actor classification policy, **not a real OAuth authorization server or resource server**.

## 22. Designing separate APIs for users and apps

It is not always appropriate to share one endpoint across both caller types.

### User-only endpoints

```http
GET /api/me/documents
Authorization: Bearer <delegated-user-token>
```

Here `/me` means **the user proven in the token**, not "the owner of the client." If an app-only token calls it, return an error for missing user context (typically 403 when the token is authenticated but the actor type is wrong). Never fall back to `service-owner@example.test` or `system`.

### App/service-only endpoints

```http
POST /api/internal/reports/rebuild
Authorization: Bearer <client-credentials-token>
Content-Type: application/json

{"tenantId":"tenant-a","reportId":"quarterly"}
```

Only applications assigned that specific action and tenant may invoke it, with separate auditing. `tenantId` in the body is merely a selector: verify the service app assignment before creating the job. The endpoint should also enforce rate limits, idempotency, approvals, and appropriate network/service authentication.

### Endpoints accepting both

An endpoint `GET /api/documents/{id}` can serve both delegated users and app-only callers if required by the domain. In that case, the policy must be an OR **between two complete branches**, never an OR between two generic authorities:

```text
ALLOW =
    sharedMandatoryChecks
    AND
    (
      verifiedDelegatedUser AND userResourcePolicyAllows
      OR
      verifiedApplication AND appResourcePolicyAllows
    )
```

Never write `hasAuthority("SCOPE_documents.read") OR isAdmin()` if `isAdmin()` could be inferred from an out-of-scope app role. Mandatory checks like tenant, resource state, and token audience must apply to **both** branches.

## 23. On-behalf-of, token exchange, and actor chains

In microservices, Alice → Service A → Service B → Document API can produce layered identities:

```text
originating user: Alice
immediate caller: Service B
OAuth client at current hop: Service B
requested action: READ Document 42
delegation chain: Alice -> Service A -> Service B
resource: Document 42 in tenant A
```

Neither user identity nor service actor should be lost:

- If B receives an app-only token from A with no delegation proof, B knows only that the app authenticated.
- If B receives a token exchange with `act`/actor metadata per the issuer contract, B can distinguish **subject** and **actor**.
- If B receives Alice's user token with `aud=service-a`, B **must not** accept it for `aud=service-b` simply because the signature is valid.
- If B needs to call C, it needs an access token for **C's exact audience** via an AS-supported flow.

**RFC 8693** defines token exchange, though not every authorization server emits `act` with identical semantics. The resource server must validate token format and delegation context per an agreed profile.

An informative audit record:

```json
{
  "requestId": "r-123",
  "callerKind": "DELEGATED_USER",
  "userId": "alice",
  "clientId": "document-frontend",
  "actingService": "backend-gateway",
  "tenantId": "tenant-a",
  "resourceType": "Document",
  "resourceId": "42",
  "action": "READ",
  "decision": "DENY",
  "reasonCode": "NO_RESOURCE_GRANT"
}
```

This is an **illustrative record**. Logs must protect privacy, omitting raw access tokens, client secrets, sensitive profiles, or document payloads. For app-only calls, `userId` should be **absent**, unless a verified initiator is recorded separately without being treated as the token's principal.

## 24. App permissions and user permissions in multi-tenant systems

A user can be ADMIN in tenant A and VIEWER in tenant B. An app may be assigned only in tenant A. These are **two independent dimensions**.

| Caller | Tenant | Source permissions | Read Document A10 | Read Document B20 |
| --- | --- | --- | --- | --- |
| Alice delegated | A | User EDITOR, token READ | Per A owner/ACL | Denied (different tenant) |
| Alice delegated | B | User VIEWER, token READ | Denied (different tenant) | Per B owner/ACL |
| Reporting bot app-only | A | App assignment REPORTS_READ | Only data granted to app in A | Denied |
| Reporting bot app-only | B | No assignment | Denied | Denied |
| Admin in A | B | Not admin in B | No cross-tenant access | Per role in B if any |

**Never use a global JWT authority** `ROLE_ADMIN` to give a tenant-A admin ADMIN access in tenant B. Likewise, never use an app-only `ROLE_ADMIN` authority to let an app modify all tenants.

For owner/resource objects, queries should include `tenant_id = :verifiedTenant`, with data permissions enforced per branch. If real data is cached, cache keys must include caller type + user ID or client ID + tenant + resource + action + policy/ACL version. A cached ALLOW for Alice must never apply to the bot, nor a bot's ALLOW to Alice.

### Memberships and app assignments can be revoked

When an admin removes Alice from tenant B, an unexpired delegated token may still pass signature checks. When revoking `reporting-bot`, its unexpired app-only token may as well. The resource server must check current entitlements or use revocation/introspection/version/short-TTL mechanisms with a clear SLA. "Hiding the button in the UI" is never enough.

## 25. Application permissions in Microsoft Graph are an example, not a universal OAuth standard

Microsoft Graph distinguishes:

- **Delegated permissions**: the app calls Graph on behalf of a signed-in user. Effective privileges are bounded by **both the app's scopes and the user's permissions**.
- **Application permissions**: the app calls Graph under its own identity with no user. These permissions can be very broad and typically require appropriate admin consent/governance.

In Microsoft identity platform/Graph access tokens, `scp` typically represents delegated scopes while `roles` typically represents application permissions in app-only tokens. However, **user app roles** can also use `roles` depending on the application/issuer. Never write logic assuming **every JWT with `roles` is app-only**.

Other systems may emit `scope` for client credentials, `permissions` in custom claims, or opaque tokens. Always consult **your exact IdP's token claim mapping** and the target audience/resource server.

### Consent does not replace object authorization

An app granted broad Graph application permissions via admin consent can perform many actions regular users cannot. That is why service credentials require great care; Graph defines its own model and permissions, while internal APIs must implement their own app assignments and tenant scoping. Never copy Graph permission names like `Files.Read.All` onto internal document endpoints assuming identical semantics.

## 26. Practical Spring Security testing

### 26.1. Unit tests for caller classification

Create fixtures for these scenarios:

- Delegated token with user subject Alice and client `web-portal`.
- App-only token with client `reporting-bot` and **no user**.
- Tokens with the exact same `scope=documents.read` across both kinds.
- Token from an untrusted issuer.
- Token missing or having an unknown `actor_kind` per custom contract.
- User token with valid `client_id` whose tenant membership was revoked.
- App token with `roles` but no app grant for the target resource.
- ID token and wrong-audience access token.
- Properly signed but expired token.
- Resource in another tenant, different owner, or expired grant.

A critical assertion: `classify(app-only)` **must never** construct a `DelegatedUserCaller` merely because the request body has `userId=alice`.

### 26.2. MockMvc with `mockJwt()`

`spring-security-test` provides `SecurityMockMvcRequestPostProcessors.jwt()`. Example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/me/documents")
        .with(jwt()
            .jwt(j -> j.subject("user-alice")
                .claim("actor_kind", "delegated_user")
                .claim("client_id", "web-portal"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isOk());
```

**Fragment:** requires Spring Boot/Test context, security configuration, controller/fixtures, and proper Principal/tenant membership. 200 is only valid when the handler exists and the user is authorized; never rely on a single test to prove policy correctness. For an app-only fixture:

```java
mockMvc.perform(get("/api/me/documents")
        .with(jwt()
            .jwt(j -> j.subject("reporting-bot")
                .claim("actor_kind", "application")
                .claim("client_id", "reporting-bot"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isForbidden());
```

This is also a **fragment**, expecting 403 based on the user-only API contract. **Crucial point:** the app holds the exact same scope as the user yet is denied by caller-kind policy. Without a properly configured actor classifier/authorization rule, this test cannot pass on its own.

`mockJwt()` **does not verify real JWT signatures, issuers, or audiences**: it mocks `Authentication` for authorization testing. Supplement with integration tests using the resource server decoder and tokens from a test issuer to verify parsing, validation, and token-type contracts.

### 26.3. Testing client credentials and call chains

You can use a mock HTTP token endpoint or test IdP environment to verify:

1. Spring OAuth2 Client uses `authorization-grant-type=client_credentials`.
2. The obtained token is for **client `reporting-bot`** itself, with no delegated user.
3. The token targets the **exact audience** of the downstream API.
4. The resource server rejects an app lacking a tenant/resource grant.
5. A user request with a forged `X-User-Id` cannot escalate the bot's permissions.
6. A BFF holding a user token does not degrade into app-only across downstream calls.
7. Services are allowed to use app credentials only on approved routes/workflows.
8. When an app grant is revoked, cache/policy honors the SLA.
9. Credential rotation keeps services running without leaking secrets.
10. Async jobs preserve actor kind and clear audit trails.

## 27. Comprehensive permission test matrix

| Caller | Token | Resource / action | Expected |
| --- | --- | --- | --- |
| Alice delegated | `documents.read` | Read Alice's document in tenant A | ALLOW if membership/ACL valid |
| Alice delegated | `documents.read` | Read Bob's private document in A | DENY |
| Alice delegated | Lacks `documents.edit` | Edit Alice's document | DENY |
| Alice delegated | Has `documents.read` | Read tenant B document with no membership | DENY |
| Reporting bot app-only | `reports.generate` | Generate report for assigned tenant | ALLOW |
| Reporting bot app-only | `documents.read` | Read document outside app grant | DENY |
| Reporting bot app-only | `documents.read` | User's `GET /me` | DENY |
| Unknown app-only | `documents.read` | Read any document | DENY |
| User Alice | `documents.read` | Call internal app-only endpoint | DENY |
| User Alice with admin role in tenant A | `documents.read` | Admin action in tenant B | DENY |
| App-only token with app `roles` | Wrong audience | Call internal API | Authentication failure |
| OIDC ID token | `sub=alice`, aud=web-client | Use as API access token | DENY |
| Delegated token | Expired | Call API | Authentication failure |
| App-only token | Unexpired, app grant revoked | Access object | DENY per SLA |
| Delegated token | Unexpired, membership revoked | Access object | DENY per SLA |
| App-only token + body `userId=alice` | Any | "Act for Alice" without delegation proof | DENY |
| Valid Token Exchange | Right audience, verified actor chain | Action within delegation scope | Per user + actor + resource policy |
| Remote PDP unavailable | Valid token | Protected action | Never ALLOW; safe error/5xx |

For app-only/service workflows, assert **side effects**, not just HTTP status. A 403 returned after an export or delete already ran is still a vulnerability.

## 28. Anti-patterns and fixes

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| Treating every `sub` in a JWT as a user | Client credentials can use client ID as subject | Classify actor per verified token contract |
| App has READ scope, so user must have consented | App-only has no user delegation | Separate app assignments, no implicit user |
| Assuming `roles` ⇒ app-only | Role semantics are provider-dependent | Use issuer-specific documented claims |
| Assuming `scp` ⇒ user in all IdPs | Some servers issue scopes for app-only | Verify issuer/token type contract |
| Checking only `hasAuthority("SCOPE_documents.read")` | Knows neither caller kind nor object owner | Enforce user/app domain policy and tenant/ACL |
| Mapping every app `Admin` role to `ROLE_ADMIN` | Service can escalate into user admin | Namespace/typed principals and limited grants |
| Using backend token to read data per body `userId` | Confused deputy | Delegated token/OBO or strong user auth |
| Backend forwarding ID token to API | Wrong audience/semantics | Use access token meant for resource API |
| Sending access token for audience A to API B | Token substitution | Validate `aud`, issue/exchange target audience |
| Using `client_id` as business user ID | Conflates client and user | Separate client identity from human subject |
| Using `Authentication.getName()` for app owner checks | Colliding fake IDs / no user exists | Resolve verified caller kind first |
| Assuming unexpired token ⇒ active ACL | Revoked grants can still be stale | Re-check/cache version/introspection policy |
| Treating consent as object ACL | Token grant does not prove Document42 access | Tenant/owner/ACL scoped queries |
| Calling `findAll` with app token then filtering | Data/metadata leaks, heavy load | Data-scoped queries/DB permissions |
| OAuth app permission = global superuser | Over-privileged and unaudited | Least privilege per client, tenant, resource |
| Not logging `clientId` on user tokens | Hard to trace malicious clients | Audit both user subject and client identity |
| App-only audit using fake user `system@...` | Loses attribution, confuses policy | Audit APP kind + client ID separately |
| Reusing user tokens arbitrarily in nightly jobs | Tokens expire / violate delegated contract | Service-only flow or approved delegation |
| Self-signing a JWT with `sub=alice` for exchange | No trusted STS authorization | Use issuer-supported flow and validate chain |
| Sharing cache entries between user and app for same scope | Bot ALLOW leaks to Alice or vice versa | Key cache by caller type, ID, tenant, action, policy |
| Running mock JWT tests and claiming signature is verified | Mocks bypass real decoder | Integration tests with issuer/signature/audience |
| Putting client secrets in Git/logs/URLs | Credential leak | Secret manager, rotation, redaction |
| Not testing revocation or tenant changes | Access persists after offboarding | Freshness SLA and negative tests |
| Disabling authorization when IdP/PDP fails | Fail-open | Never ALLOW; graceful 5xx/deny |

## 29. Design checklist for user vs. application permissions

1. Does the API serve **user-delegated**, **app-only**, or both?
2. Is there a formal IdP contract distinguishing the two actor kinds?
3. Does the resource server validate issuer, audience, signature, `exp`, and token type properly?
4. Could an OIDC ID token ever be accepted as an API access token?
5. Are `client_id` and `sub` kept distinct during identity mapping?
6. Do user business permissions check tenant membership, owner, and ACLs?
7. Do app-only permissions enforce application assignments by tenant/resource/action?
8. Are scopes treated as a **necessary condition**, never automatic object access?
9. Does `ADMIN` distinguish user tenant roles from app permissions?
10. Do `/me` endpoints reject app-only tokens?
11. Do background/app-only endpoints reject user tokens?
12. Could a backend receiving user requests and holding client credentials create a confused deputy?
13. If OBO is needed, is token exchange backed by a trusted issuer with the right audience?
14. Are apps granted least privilege and bounded by tenant/data classification?
15. Are permissions checked **before** export, update, delete, share, and job enqueueing?
16. Do token/permission caches key on caller kind, tenant, action, version, and honor a revocation SLA?
17. Do audit logs capture both user subject **and** client/service identity during delegation?
18. Are service secrets protected/rotated and kept out of logs and source code?
19. Do tests cover scenarios with the same OAuth scope yielding different results for user vs. app?
20. Are there integration tests verifying real JWTs rather than `mockJwt` alone?
21. Do GraphQL routes, queues, workers, file downloads, and search/export share the domain policy?
22. When actor kind is unknown or the permission store fails, does it **deny by default**?

**Conclusion:** In OAuth2, **user permissions** and **application permissions** solve two different problems. A delegated token carries an authorized user context; a client-credentials token verifies that **the client itself** is allowed to call the resource server. Token scopes and roles must be verified and interpreted per the IdP, yet remain insufficient for business data permissions. A secure design classifies callers reliably, applies separate policies to USER and APPLICATION, checks resource/tenant/action server-side, prevents confused deputies, and tests both allowed operations and data that must never be exposed.

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): resource owner, client, authorization server, resource server, and grant types.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): PKCE for authorization code.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `sub`, `client_id`, issuer/audience, and differences for grants with/without a resource owner.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): trusted token exchange and actor/delegation.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): presenting bearer access tokens and error handling.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `scope`/`scp` → `SCOPE_*`, JWT validation, and `JwtAuthenticationConverter`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): Authorized Client, Authorized Client Manager, and client flows.
- [Spring Security — OAuth2 Client Credentials](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): client credentials for applications/services and authorized client lifecycle (verify exact section per version).
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and protecting domain services.
- [Microsoft Graph — Permissions Overview](https://learn.microsoft.com/en-us/graph/permissions-overview): delegated permissions vs. application permissions per provider.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and action/resource checks.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): never trust object IDs; enforce tenant/owner/ACL server-side.
