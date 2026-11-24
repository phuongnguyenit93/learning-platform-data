# SAML Assertions, ID Tokens, Access Tokens, and Service Tickets

> **Context:** Spring Security – Federation / SSO Protocols. These four artifacts can all appear around a centralized login, yet they **differ in protocol, purpose, intended recipient, and validation method**. Referring to all of them generically as "login tokens" easily leads to security vulnerabilities.

## 1. Big Picture: Authentication, Authorization, and SSO

- **Authentication:** "Who logged in, how, and when?" In SAML Web SSO, the identity provider (IdP) issues an assertion; in OpenID Connect (OIDC), the OpenID Provider issues an **ID token**.
- **Authorization (access delegation):** "Which client is allowed to call which resource, with what scope?" OAuth 2.0 uses an **access token** as a resource-access credential. An access token can be issued in a flow with no end user, such as `client_credentials`.
- **Ticket-based SSO:** CAS issues a **service ticket** for one specific service; the service must send that ticket back to CAS for verification, usually single-use.
- **SSO:** Users typically log in at the IdP/CAS once and can then enter multiple applications. This **does not mean** an assertion, ID token, access token, or service ticket can be freely reused across all applications.

Common roles:

| Role | Meaning |
| --- | --- |
| User / browser | The user and the browser following redirects, submitting forms, or carrying codes/tickets |
| IdP / OpenID Provider (OP) | Authenticates users and issues identity assertions |
| SAML Service Provider (SP) / OIDC Relying Party (RP) | Application that trusts the IdP/OP and logs the user in |
| OAuth Authorization Server (AS) | Issues access tokens according to grants and policies |
| OAuth Resource Server (RS) | API receiving access tokens, validating tokens, and deciding permissions |
| CAS Server / CAS Service | CAS login server / application receiving service tickets |

A single system can take on multiple roles, but **the intended recipient must be validated separately for each role**.

## 2. Comparison Table of the Four Artifacts

| Aspect | SAML assertion | OIDC ID token | OAuth 2.0 access token | CAS service ticket |
| --- | --- | --- | --- | --- |
| Typical protocol | SAML 2.0 | OpenID Connect 1.0 | OAuth 2.0 | CAS Protocol |
| Core question | What does the IdP assert about the authentication event? | Which user did the OP authenticate for this client? | Which resource access permissions were granted? | Does CAS confirm login for this exact service? |
| Intended recipient | SAML SP (entity ID / ACS) | OIDC client (client ID) | Resource server/API | One CAS service URL |
| Representation | XML assertion, usually inside a SAML Response | JWT (signed; may be encrypted) | Opaque string or JWT, depending on AS | Opaque string such as `ST-…` |
| Issuing party | SAML IdP | OpenID Provider | Authorization Server | CAS Server |
| Verification sequence | XML signature, issuer, conditions, subject confirmation, audience/recipient, replay | JWS/JOSE, issuer, audience, timestamps, nonce when applicable | JWT: signature + issuer + audience + expiry + permissions; opaque: introspection | HTTPS call to CAS endpoint to validate ticket with `service` |
| Lifetime/usage | Time-bounded; requires replay protection | Bounded `exp`, requires client/request binding | Typically short-lived; Bearer can be reused while valid | Short-lived, bound to one service, single-use for validation |
| Use directly to call APIs? | Not an OAuth API credential | **No** | **Yes**, if the API accepts the token and permissions match | **No**; used to establish the CAS service session |

> **Quick identification rule:** Assertions/ID tokens are primarily **proof of authentication** for an intended recipient; access tokens are **resource-access credentials**; service tickets are **one-time codes for a service to query CAS back**.

## 3. SAML Assertion: Structured XML Statement from the IdP

### 3.1. Assertion vs. SAML Response

In SAML Web Browser SSO, the SP may send a `<samlp:AuthnRequest>` to the IdP. The IdP authenticates the user and creates a `<samlp:Response>`, which usually contains one or more `<saml:Assertion>` elements. The browser sends the SAML Response to the SP's **Assertion Consumer Service (ACS)**, typically via HTTP POST.

```text
Browser -> SP: requests login-protected page
SP -> Browser -> IdP: AuthnRequest (SP-initiated)
IdP: authenticates user, creates SAML Response/Assertion
IdP -> Browser -> SP ACS: sends SAMLResponse
SP: checks trust + signature + issuer + time + audience + recipient
SP: creates application session (e.g. HttpSession), applies internal permissions
```

**SAML Response** is the protocol envelope; **SAML assertion** is the statement inside. Signatures may protect the Response, the assertion, or both according to profile/trust configuration; never assume that seeing a single `Signature` tag means all data you consume is protected.

### 3.2. Components to Understand

- `Issuer`: IdP entity issuing the assertion; must match the configured trusted IdP.
- `Subject` / `NameID`: subject identifier; application policy determines how it maps to an internal user. `NameID` is not a role/permission.
- `AuthnStatement`: authentication context/event; may include `AuthnInstant`, `SessionIndex`, and `AuthnContext`.
- `AttributeStatement`: attributes such as department, email, and groups; these are **claims**, not automatically equivalent to admin permissions.
- `Conditions`: time limits `NotBefore`, `NotOnOrAfter`, and typically `AudienceRestriction` specifying the SP.
- `SubjectConfirmationData`: for bearer SSO, must check `Recipient` (valid ACS), `InResponseTo` if responding to an AuthnRequest, validity window, and related conditions.

A **trimmed structural example**, not a valid assertion for deployment (signature and profile-required security fields omitted):

```xml
<saml:Assertion
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_a123" Version="2.0" IssueInstant="2026-11-07T01:00:00Z">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID>user-123</saml:NameID>
  </saml:Subject>
  <saml:Conditions
    NotBefore="2026-11-07T00:59:00Z"
    NotOnOrAfter="2026-11-07T01:04:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://portal.example.org/saml/sp</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
</saml:Assertion>
```

The example illustrates that `Audience` points to the **SP**, not an arbitrary API. Timestamps are mock data only; `NotOnOrAfter` is an **exclusive** boundary (no longer valid at or after that instant).

### 3.3. What Must the SP Actually Verify?

1. Trust the **right IdP** via configured metadata/certificates; verify the XML signature over the **exact data being processed** and validate Reference structure. Beware of XML signature wrapping: never extract a different assertion than the one verified.
2. Match `Issuer`, SP `entityID`/`AudienceRestriction`, Response `Destination`, ACS/`Recipient`, and `InResponseTo` against the issued request when applicable. **IdP-initiated** flows may lack `InResponseTo`; accept them only with an explicit policy and replay-prevention measures.
3. Check assertion/confirmation time windows, allowing small controlled clock skew; store assertion/response IDs for the validity window to prevent replay.
4. Check `SubjectConfirmation` for the right method/profile; only then map the user/attributes to an account and application permissions.
5. Use HTTPS, trusted keys, and trusted metadata; assertion encryption (when used) protects confidentiality and **does not replace** verifying signatures and conditions.

**Common mistake:** merely Base64-decoding `SAMLResponse` and reading the email, or accepting SP A's assertion at SP B because "both use the same IdP." Being able to read XML does not prove it is valid or issued for the current SP.

## 4. OIDC ID Token: Login Proof for the Client

OpenID Connect adds an **authentication layer** on top of OAuth 2.0. With Authorization Code Flow (often with PKCE), the browser receives a `code` via redirect; the backend/client exchanges the code at the token endpoint and receives an `id_token` along with other tokens per the flow and OP policy.

```text
Browser -> OIDC client: opens page
Client -> OP: authorization request (client_id, scope=openid, state, PKCE, nonce if used)
OP: authenticates user
OP -> Browser -> Client redirect URI: authorization code
Client -> OP token endpoint: exchanges code (and PKCE code_verifier)
OP -> Client: ID token and usually access token
Client: verifies ID token, creates local login session
```

### 4.1. Format and Claims

An ID token is an OIDC JWT structured as `base64url(header).base64url(payload).signature` when JWS-signed. **Illustrative decoded payload example, not a validly signed token**:

```json
{
  "iss": "https://idp.example.org",
  "sub": "7f2a-user-123",
  "aud": "web-client",
  "iat": 1794013200,
  "exp": 1794013500,
  "nonce": "nonce-from-original-login-request",
  "auth_time": 1794013100
}
```

- `iss`: exact identifier of the OP/issuer.
- `sub`: stable subject within the issuer's scope, typically combined with `iss` as the application identity key: **(iss, sub)**.
- `aud`: client ID receiving the ID token; may be an array. Multi-audience cases must check `azp` rules and trustworthiness of the audiences.
- `iat`, `exp`: issued-at and expiration times; `auth_time`: user authentication timestamp if requested/returned.
- `nonce`: when the client sends a nonce, it must verify that the ID token value matches the stored request; helps prevent replay/token injection.
- `acr`, `amr` if present: authentication level/methods; do not automatically grant API access.

### 4.2. Verification Before Trusting an ID Token

1. Use a trusted OIDC library, verifying the signature against the trusted OP's keys/algorithms; reject `alg=none`, and never trust a JWT merely because it decodes to JSON.
2. Match `iss` **exactly**, verify `aud` contains the application's `client_id`, check `azp` when applicable, and verify `exp`, `iat`, and related time bounds.
3. Bind the response to the right login transaction using `state`, redirect URI, and PKCE. Check `nonce` when sent/required by the flow; do not treat `state` and `nonce` as the same field.
4. Use only verified claims to establish identity/sessions. Email/display name can change and are not global identifier keys; avoid linking users across issuers by email alone.
5. Check `auth_time` when recent login is required (`max_age`), along with client-specific security requirements.

**An ID token is NOT an access token.** APIs must not accept an ID token as a bearer token just because it has a valid JWT signature: its `aud` is the **OIDC client**, whereas an API must require a token issued for the **resource server**. Conversely, using an access token as full login proof does not substitute for the OIDC flow.

## 5. OAuth 2.0 Access Token: Credential for Calling Resource Servers

An access token is issued by the AS to a **client** under a grant and AS policy so the client can call resources. The token may represent user-delegated permissions or the application's own permissions (e.g. `client_credentials`); therefore, "having an access token" does not always mean "a user just logged in."

```http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...example-access-token...
```

Bearer means **anyone holding the valid token can present it** within the scope of its permissions. Never place tokens in URLs/query strings, logs, analytics, client error responses, or public storage.

### 5.1. Opaque and JWT Access Tokens

| Form | Characteristics | Resource server verification |
| --- | --- | --- |
| Opaque/reference | String with no client-readable structure; AS stores state or performs lookup | Call **token introspection** over a secure channel, inspect `active` and metadata, verify audience/scope/policy |
| JWT access token | Claims reside in a decodable payload; must be signed and validated | Signature with trusted key; `iss`, the **API's** `aud`, `exp`/`nbf`, algorithm policy, scope/permissions, and required constraints |

**Illustrative** JWT access token payload example, not a valid security credential:

```json
{
  "iss": "https://idp.example.org",
  "sub": "7f2a-user-123",
  "aud": "orders-api",
  "client_id": "web-client",
  "scope": "orders:read orders:create",
  "iat": 1794013200,
  "exp": 1794013500
}
```

Suppose the `orders-api` API accepts only `aud=orders-api`. It cannot replace that check by seeing that `sub`, `email`, or `iss` "looks right." `scope` indicates permissions **granted to the token**, but the endpoint still must make the final decision based on policy and the specific resource: `orders:read` permission does not necessarily permit reading someone else's orders.

**Standards note:** RFC 9068 describes a **JWT access token profile** with `typ=at+jwt` and specific validation rules. Not every JWT access token implements this profile; do not enforce RFC 9068 format/claims on an AS that does not claim to use it. OAuth 2.0 does not require access tokens to always be JWTs.

### 5.2. How the Resource Server Processes It

1. Extract the bearer token from the `Authorization` header; reject missing/malformed tokens.
2. Verify using a **JWT decoder + validators** matching issuer/audience, or introspection for opaque tokens. Base64 decoding alone is **insufficient**.
3. Verify the token is intended for this exact API, currently valid, and unrevoked; check scope/permissions in the context of the request, tenant, and object.
4. Return **401 Unauthorized** when the token is missing/invalid; typically return **403 Forbidden** when the identity is valid but lacks permission. Include `WWW-Authenticate: Bearer` per OAuth semantics when appropriate.

**Access token vs. refresh token:** a refresh token is used by the client with the AS to request a new access token; never send a refresh token to a resource server. JWT revocation does not happen automatically just because a user logged out: short lifetimes, introspection, or a denylist/revocation mechanism may be needed.

## 6. CAS Service Ticket: One-Time Code for the Exact Service

CAS has its own ticket model. After the user logs in with the CAS Server, the browser may hold a **Ticket Granting Cookie (TGC)** tied to the CAS session; the CAS Server manages the **Ticket Granting Ticket (TGT)** server-side. Upon entering a CAS application (service), CAS issues a short-lived **service ticket (ST)**, usually prefixed with `ST-`.

```text
Browser -> Service A: login required
Service A -> Browser -> CAS /login?service=<service-A-URL>
CAS: authenticates user or reuses existing CAS SSO session
CAS -> Browser -> Service A?ticket=ST-...
Service A -> CAS /serviceValidate?service=<service-A-URL>&ticket=ST-...
CAS -> Service A: authenticationSuccess(user, attributes) or failure
Service A: creates internal session; removes ticket from URL after processing
```

Decisive differences:

- **ST is bound to the exact requested `service`.** Service B must not use a ticket issued for Service A.
- Per the CAS Protocol, **each service ticket may be submitted for validation only once**; CAS must invalidate it after a single validation attempt, even a failed attempt. Consumed or expired tickets must not be reused.
- The service calls an endpoint such as `/serviceValidate` or `/p3/serviceValidate` (depending on version/deployment) over **HTTPS** and checks the success/failure response; never infer a user solely from the `ST-...` string.
- **TGT/TGC is not an ST.** TGT/TGC enables issuing new STs via SSO, whereas an ST serves a single login handoff to one service.
- CAS also has **proxy tickets**, used for delegation through intermediary services per the CAS protocol; they must not be arbitrarily treated as OAuth access tokens, and the validation endpoint/ticket type must match.

Illustrative HTTP example, with fake ticket data:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-example-123 HTTP/1.1
Host: sso.example.org
```

If `service` is wrong, or the ticket is already used or expired, CAS must return a validation failure. On success, the service receives authentication data from **CAS's validation result**, and then maps the internal user and permissions.

## 7. One User Login, Four Distinct Trust Boundaries

Suppose a company has a Web portal, an orders API, and a legacy CAS application. The IdP and CAS may share a user directory, but the artifacts cannot be swapped for one another:

1. **SAML:** The IdP issues an assertion for `https://portal.example.org/saml/sp`. Only the SP configured to trust it accepts, validates, and creates a login session.
2. **OIDC:** The OP issues an ID token with `aud=web-client`. The Web application uses it to complete login and create a session.
3. **OAuth 2.0:** The AS issues an access token with `aud=orders-api` and `scope=orders:read`. The API validates the token and policy; `web-client`'s ID token cannot substitute for it.
4. **CAS:** CAS issues an ST for `https://legacy.example.org/login/cas`. The legacy application sends the ST with the service URL to CAS, validates it once, and creates a session.

The bridge between protocols is **identity federation / account mapping**, not directly "relabeling" tokens. If an organization needs token exchange or a SAML→OIDC broker, that is a **transaction issuing a new token** under an explicit trust policy, not renaming claims or copying token strings.

### SSO Session, Token Lifetime, and Logout

- The IdP/CAS session and the SP/RP/service's internal session are **two separate states**; a token expiring does not necessarily end an already-created HttpSession.
- Application logout does not automatically guarantee logout at the IdP or remaining applications. SAML SLO, OIDC RP-Initiated Logout/front-channel/back-channel logout, and CAS SLO each have their own protocols, limitations, and support levels.
- Do not use an active access token as proof that the SSO session is still open; likewise, do not assume revoking an access token deletes the web login session.
- Design lifetimes, clock synchronization, replay protection, session storage, and logout per **artifact type**.

## 8. Applying in Spring Security

Spring Security explicitly models the application's **role**; choose configuration according to the flow being protected. The snippets below are **separate integration options**, not lines to combine into one filter chain.

### 8.1. Web Application as OIDC Client (RP)

Declare the appropriate OAuth2 Client dependency and register the client with the OP. Java example using compatible Spring Security 6+/Spring Boot; this is a complete configuration class, requiring Spring Security dependencies and `spring.security.oauth2.client` configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

For OIDC to work, `scope` must include `openid`, and the provider/client needs settings such as `issuer-uri`, `client-id`, `client-secret`/appropriate authentication method, and a valid redirect URI. Spring Security yields `OidcUser`/`OidcIdToken` after login; the application should rely on the framework's default validation and customize only with solid OIDC understanding. **Do not turn the ID token into Authorization: Bearer to call an API.**

### 8.2. API as OAuth 2.0 Resource Server

Add the resource-server and JOSE dependencies to the application if accepting JWTs. Spring Boot configuration example when the AS provides metadata/JWKS:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: orders-api
```

`issuer-uri` is used for key discovery and issuer validation; `audiences` requires tokens intended for this API (verify property support for the Spring Boot version in use). The filter chain takes the form:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders:read")
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
```

The snippet above is a **fragment placed inside an `HttpSecurity` configuration method**, not a standalone Java program. If tokens are opaque, switch to `oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` and configure the introspection endpoint/credentials per your Spring Security version. Do not write a custom decoder that skips issuer/audience checks.

### 8.3. Web Application as SAML Service Provider

Use SAML2 Service Provider support, configuring `RelyingPartyRegistration`/IdP metadata, trusted keys/certificates, and ACS; in `SecurityFilterChain`, use `saml2Login(Customizer.withDefaults())`. Spring Security processes `SAMLResponse` at the ACS (typically `/login/saml2/sso/{registrationId}`) and creates `Saml2Authentication` after the provider verifies signature, conditions, and subject. Specific metadata/paths depend on version/configuration and must stay synchronized with the IdP side.

### 8.4. CAS Service Application

CAS does not use `oauth2Login()`, `saml2Login()`, or `oauth2ResourceServer()` to validate an ST. Integrate a CAS client/validator matching your Spring Security version, configuring the CAS login URL, **exact service URL**, HTTPS trust, and `TicketValidator`. The service receives the ticket, calls CAS validation, and only then places the principal into `SecurityContext`/session. For new systems, consider an IdP supporting OIDC/SAML when cross-technology integration is needed, rather than substituting an access token for a CAS ST.

**General Spring Security principle:** succeeding at the authentication step creates an `Authentication` in `SecurityContext`; having an `Authentication` does not automatically imply the user has permission for every endpoint. Always configure authorization per request/resource and role.

## 9. Java 17+ Experiment: Why Audiences Are Not Interchangeable

The plain Java program below **only illustrates audience matching after a token has already been verified by a security library**. It **does not** decode, verify signatures, or accept real tokens and must not be used as a production validator.

Create `AudienceBoundaryDemo.java`:

```java
import java.util.Set;

public class AudienceBoundaryDemo {
    private static boolean isFor(Set<String> audiences, String expected) {
        return audiences.contains(expected);
    }

    public static void main(String[] args) {
        Set<String> idTokenAud = Set.of("web-client");
        Set<String> accessTokenAud = Set.of("orders-api");

        System.out.println("ID token -> web client: "
                + isFor(idTokenAud, "web-client"));
        System.out.println("ID token -> orders API: "
                + isFor(idTokenAud, "orders-api"));
        System.out.println("Access token -> orders API: "
                + isFor(accessTokenAud, "orders-api"));
    }
}
```

Run with JDK 17 or higher:

```bash
javac AudienceBoundaryDemo.java
java AudienceBoundaryDemo
```

Exact stdout output:

```text
ID token -> web client: true
ID token -> orders API: false
Access token -> orders API: true
```

Both an ID token and an access token **can be validly signed JWTs** yet have different intended recipients. In a real system you must also verify issuer, signature, timestamps, token type, nonce/introspection (depending on protocol), grants, and specific permissions; the demo does not perform those checks.

## 10. Common Mistakes and Fixes

| Mistake | Why it is wrong / remediation |
| --- | --- |
| Sending an ID token to an API as an access token | `aud` points to the OIDC client; the API must require an access token issued for the resource server and verify permissions |
| Merely decoding JWT/SAML and trusting claims | Decoding does not verify signature, issuer, timestamps, intended recipient, or request binding |
| API checking only JWT signature and `exp` | A validly signed token issued for another API/client is still dangerous; check `iss`, `aud`, and policy |
| Treating `scope=read` as sufficient to read every record | Scope does not replace tenant, ownership, and object-level authorization checks |
| Reusing a SAML assertion or CAS ST | SAML requires replay protection by ID/request; a CAS ST is valid for one-time validation |
| Accepting an ST just because it starts with `ST-` | An ST is an opaque string; must validate online with CAS along with the exact `service` |
| Using email as the linking ID across issuers | Email can change or be unverified; use a stable key by issuer + subject and controlled mapping |
| Configuring logout in one place and assuming everything logged out | IdP/CAS sessions, application sessions, and API tokens have separate lifecycles |
| Placing tokens in URLs, logs, or XSS-exposed frontend stores | Bearer credentials can be stolen; use HTTPS, protect storage, limit permissions and lifetimes |
| Forgetting to check `state`/PKCE/`nonce` in OIDC | Easily creates login CSRF, code interception, or token replay vulnerabilities; use a standard OIDC client |

### How to Self-Audit an SSO Design

For **each credential received**, answer all seven questions thoroughly:

1. Which **protocol** does it belong to, **who issued it**, and for **which recipient**?
2. Is it proving **authentication**, granting **resource access**, or merely a ticket to look up?
3. Which trusted validator verifies the signature/issuer or calls introspection/CAS validator?
4. Where are **audience/service, expiry, request binding, and replay** constraints enforced?
5. Which subject is mapped to an internal account, and does that mapping prevent cross-tenant/cross-issuer confusion?
6. From the trusted principal, which policy determines **permissions on endpoints and individual resources**?
7. Upon logout, revocation, or ticket expiration, how do the **application session** and remaining SSO sessions change?

If any question lacks an answer, the design is not yet clear enough to consider that credential trustworthy.

## 11. Quick Review Questions

**Q:** Both an ID token and an access token are validly signed JWTs. Can they replace each other?  
**A:** No. Token type, intended audience, purpose, and validation rules differ; an API requires an access token issued for itself.

**Q:** After CAS login, why doesn't the service save the ST to resend on every request?  
**A:** An ST is used to validate once and create the service's session; any subsequent validation attempt must fail per the CAS Protocol.

**Q:** If a SAML Assertion contains `NameID` and `email`, can the SP trust it immediately?  
**A:** No. It must verify signature, issuer, audience, recipient, timestamps, subject confirmation, request binding, and replay protection before using claims.

**Q:** If an API receives an opaque access token, how should it validate it?  
**A:** Use trusted introspection with the AS, checking `active` and permission/recipient metadata according to the API's policy.

**Q:** Does successful SSO mean all applications/APIs automatically grant access?  
**A:** No. Each application creates/maintains its own session and enforces authorization; each resource server checks the access token's permissions.

## Reference Standards

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) – ID token definition and validation.
- [RFC 6749: OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749) and [RFC 6750: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) – access permissions and bearer usage.
- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068) – JWT access token profile.
- [SAML 2.0 Technical Overview (OASIS)](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) – SAML structure, browser SSO, and trust boundaries.
- [CAS Protocol Specification (Apereo)](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html) – service tickets and `/serviceValidate`.
- [Spring Security: SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html), [OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html), [JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html), [Opaque Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html) – Spring Security roles and configuration.