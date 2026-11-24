# Identifying OIDC Users by the Issuer and Subject Pair

In **OpenID Connect (OIDC)**, a **Relying Party (RP/client)** application needs a stable identity key to answer: *"Does the user who just signed in correspond to a previously known internal account?"* The standard answer is the **`(iss, sub)` pair from a verified ID Token**—not an email, username, phone number, display name, or a bare `sub` standing alone.

- **`iss` (Issuer):** exact identifier of the **OpenID Provider (OP)** that issued the ID Token, e.g., `https://login.example.test/realms/staff`.
- **`sub` (Subject):** user identifier **unique within that issuer's scope**, which per OIDC Core must never be reassigned to another user.
- **`(iss, sub)`:** the binding key linking an external user to **one internal account**; trustworthy only after the token and entire OIDC context have been verified.

For example, two OPs can both emit `sub="12345"` for **two completely different people**:

| Issuer | Subject | Identity the RP Must Treat This As |
| --- | --- | --- |
| `https://idp-a.example.test` | `12345` | Person A at OP A |
| `https://idp-b.example.test` | `12345` | Person B at OP B |
| `https://idp-a.example.test` | `67890` | Person C at OP A |

**Never** look up a user solely by `sub=12345` when the application trusts multiple OPs. Especially in an **identity broker** architecture, the OP the application directly trusts may be the **broker**, rather than the upstream IdP handling passwords/MFA. The identity pair observed by the RP is then **`(broker_iss, broker_sub)`**, not automatically the upstream pair.

This lesson belongs to **Spring Security – federation → OIDC and Brokering**, focusing on identity key design, public vs. pairwise subjects, broker vs. upstream OP, account linking, Spring Security OAuth2 Login, tenant-based authorization, a Java 17 example with deterministic stdout, and security tests.

## 1. What Are OIDC, OP, RP, and an Identity Broker?

**OIDC** adds an **authentication/identity** layer over OAuth 2.0. With Authorization Code Flow, the RP sends the user to the OP, receives an authorization code, exchanges the code for tokens, and validates the **ID Token** to learn which subject the OP authenticated.

| Concept | Explanation | Role in Identity |
| --- | --- | --- |
| **OP / Issuer** | System issuing ID Tokens | Namespace for `sub` |
| **RP / OAuth2 Client** | Application trusting one or more OPs | Stores `(iss,sub)` → internal account mapping |
| **ID Token** | JWT holding authentication claims, verified per OIDC | Source of `iss`, `sub`, `aud`, and login context |
| **UserInfo** | Endpoint providing supplementary claims | Includes `sub`; must match the ID Token's `sub` |
| **Identity broker** | Intermediary OP bridging multiple upstream IdPs | Issues **the broker's own** `iss` and `sub` to the RP |
| **Upstream IdP** | Google, LDAP bridge, SAML IdP, or OP behind the broker | Supplies evidence to the broker, not necessarily verified directly by the RP |
| **Local account** | User record in the application's database | Stable ID for attaching data, permissions, and tenants |
| **Federated identity link** | Record linking issuer+subject to an account | Governed identity bridge |

### Two Common Architectures

**RP connecting directly to multiple OPs:**

~~~text
                   Spring Security RP
                      /         \
                     /           \
          OP Corp / issuer A   OP Partner / issuer B
                  |                 |
                sub A             sub B
                   \               /
                  Identity links in DB
                           |
                      Local accounts
~~~

**RP connecting through an identity broker:**

~~~text
              Spring Security RP
                     |
       ID Token iss = https://broker.example.test
       ID Token sub = broker-user-271
                     |
                 OIDC Broker
                /           \
             Upstream A    Upstream B
              (OIDC)        (SAML)
               |             |
          upstream sub    SAML NameID
                     |
          Broker's linking policy
~~~

In the second model, the RP generally **lacks the full original upstream tokens/evidence**. The RP directly verifies only the broker's ID Token and trusts the broker within its contract. Never assume the broker's `sub` equals the upstream `sub`.

## 2. The ID Token Is the Identity Source; Verify Before Using

Example decoded JSON payload for reading:

~~~json
{
  "iss": "https://login.example.test/realms/staff",
  "sub": "usr-7h2v8",
  "aud": "portal-web",
  "iat": 1794042000,
  "exp": 1794045600,
  "email": "person@example.test",
  "email_verified": true,
  "name": "Illustrative User"
}
~~~

This is an **illustrative payload**, not a signed JWT; timestamps serve only to illustrate the claims. **Base64URL decoding is not token verification.** Extract `iss` and `sub` **only after** the OIDC client library has validated:

1. **Signature/JWS:** using allowed keys and algorithms for the OP from trusted config/JWKS; preventing `alg=none` and algorithm confusion.
2. **Issuer:** `iss` **matches exactly** the registered/discovered issuer for the current client.
3. **Audience:** `aud` contains the RP's `client_id`; enforce `azp` rules where applicable, especially with multiple audiences.
4. **Timestamps:** `exp`, `iat`, and time constraints per policy with bounded clock skew.
5. **Nonce:** if the flow sent `nonce`, verify the returned nonce to prevent token injection/replay.
6. **Authorization response:** `state`/correlation, redirect URI, code exchange, and PKCE when applicable to the OAuth client.
7. **UserInfo source:** if reading `sub` from UserInfo, it must **match exactly** the `sub` from the verified ID Token.
8. **Client/provider binding:** an ID Token from OP A must not be accepted as an ID Token for OP B's configuration.

**Never** extract `iss` from an unverified JWT and automatically download JWKS from whatever URL the token suggests. You may read claims as a **hint** to locate an OP in a configured allowlist, yet signature/issuer/audience validation against that exact OP must complete before trusting the contents.

## 3. Why Is the (iss, sub) Pair the Stable Identifier?

OIDC Core, section **Claim Stability and Uniqueness**, explicitly states that only `iss` and `sub` **used together** form an identifier an RP can rely on to identify an End-User consistently.

**Counterexample:**

~~~text
OP A issues sub = "42" for person A
OP B issues sub = "42" for person B

If database key = sub:
    key "42" -> risk of overwriting or merging A and B

If database key = (iss, sub):
    (https://op-a.example.test, "42") -> A
    (https://op-b.example.test, "42") -> B
~~~

Emphasis: `iss` is the **OP identifier string**, not merely the domain. Two issuers sharing a host with different paths can be **two separate OP/tenant namespaces**:

- `https://login.example.test/realms/sales`
- `https://login.example.test/realms/hr`

Both can emit `sub="42"`. They are **two distinct keys**.

Similarly, `https://op.example.test` and `https://op.example.test/` must not be treated automatically as identical in identity lookup. OIDC requires **exact matching** between discovery and the ID Token issuer. If a provider changes its issuer URI, that is an identity namespace change requiring controlled migration, not a harmless tweak.

**`sub` is an opaque identifier:** the application must never infer organization, email, issuance order, gender, or role from the structure of `sub`. It may be a numeric string, UUID-like, hashed string, or proprietary format, and should be **preserved verbatim**.

## 4. Why Not Use email, preferred_username, or phone_number as the Key?

| Claim | Useful For | Why Not a Unique Binding Key? |
| --- | --- | --- |
| `email` | Display and contact | Can change, be reassigned to someone else, or collide across OPs |
| `email_verified` | OP asserts it checked email control per its policy | Does not prove two accounts at two OPs are the same person/app account |
| `preferred_username` | Display name or login hint | Can change or collide across organizations |
| `phone_number` | Contact/step-up per policy | Phone numbers can change owners |
| `name`, `given_name` | UX/profile | Non-unique and mutable |
| `picture` | Avatar | Unrelated to identity proof |
| `sub` alone | Identification within an issuer | Not unique across OPs |
| **`iss + sub`** | **OP subject binding key** | **Guaranteed by OIDC within the issuer scope** |

Suppose an employee leaves and `finance@example.test` is reassigned to a new hire. If a legacy system used email as its primary binding key, the new hire could inherit prior data or privileges. With issuer+sub, the two people must have distinct identifiers if the OP conforms to the spec.

**Even `email_verified=true` does not permit auto-merging two accounts.** That claim expresses only an attribute of the email per the OP; it does not replace internal account ownership verification and account takeover controls.

Some systems need email as a **supporting search index**; in that case store it as a mutable profile attribute, never as a unique identity link or source of elevated permissions.

## 5. Public Subject vs. Pairwise Subject

OIDC Core defines **two subject identifier types**:

| Type | Meaning | Consequence |
| --- | --- | --- |
| **public** | OP may emit the same `sub` for the same user across multiple clients | RPs can correlate the same OP subject if policy allows |
| **pairwise** | OP emits different `sub` values per **Sector Identifier** | Reduces cross-RP correlation of user activity |
| **`subject_types_supported`** | Field in OIDC Discovery metadata | Indicates whether the OP supports public/pairwise |

**Pairwise does not necessarily give every client a different `sub`:** two clients sharing the same **sector identifier** can receive the **same pairwise `sub`** for an End-User, whereas different sectors must receive distinct subject identifiers. Therefore do not oversimplify "pairwise = per `client_id`"; check the **sector** and OP configuration.

Example:

~~~text
OP issuer = https://identity.example.test

Internal OP user: user-789

Client Portal: sector = portal.example.test
ID Token: (iss, sub = "p-8af2")

Client HRM: sector = hrm.example.test
ID Token: (iss, sub = "p-31cd")

=> Same person at the OP, yet two different (iss,sub) pairs.
=> RP must not infer they are the same person from email or by guessing sub.
~~~

### sector_identifier_uri

When pairwise is enabled, the OP computes subjects by **Sector Identifier**. If a client specifies `sector_identifier_uri`, the corresponding registration document lists the client group's redirect URIs; otherwise the sector typically derives from the redirect URI host per registration rules. Changing domains/sectors or client registrations can produce a **new `sub`** even though the user has not changed.

**Critical operations note:** When migrating from public to pairwise, changing sector identifiers, or splitting/merging clients, plan an **identity link migration**. Never treat a changed `sub` as a reason to auto-create an account with all prior permissions or link accounts via email.

## 6. Issuer Exactness: Case, Path, Trailing Slash, and Discovery

Per OpenID Connect, `iss` in an ID Token is an HTTPS issuer identifier that may include host, port, and path, **with no query or fragment**. The issuer in discovery metadata and `iss` in the ID Token must **match exactly**.

Examples:

| Issuer A | Issuer B | Treated as Same Identity Key? |
| --- | --- | --- |
| `https://idp.example.test` | `https://idp.example.test` | Yes, if `sub` also matches and tokens are valid |
| `https://idp.example.test` | `https://idp.example.test/tenant` | **No** |
| `https://idp.example.test/tenant-a` | `https://idp.example.test/tenant-b` | **No** |
| `https://idp.example.test` | `https://idp.example.test/` | **Never treat as identical automatically** |
| `https://old-login.example.test` | `https://new-login.example.test` | **No**, requires verified migration |
| Same issuer, `sub="A42"` | Same issuer, `sub="a42"` | **No**, subject is a case-sensitive string |

When storing keys in a database:

- Persist the **exact verified issuer and subject values** emitted by the OP.
- Use **case-sensitive, exact comparison** for both; avoid silent collation or case folding.
- Never lowercase entire issuer paths/subjects or trim `sub` to "optimize".
- Never call `URI.normalize()`, strip trailing slashes, or concatenate URLs heuristically to equate two issuers.
- Record the **registration/client configuration** used to validate the token, without replacing `iss` with registrationId.
- If an approved OP legitimately changes its issuer, handle it via an **explicit migration**, not an implicit issuer alias.

**Caution:** Java URL/URI APIs may normalize certain representations when comparing. When building an identity key, read the **raw `iss` string claim from the library-verified ID Token** and store it verbatim.

## 7. ID Token, UserInfo, and Access Token Are Not Interchangeable

In a Spring Security system combining web login and backend APIs, three artifacts are easy to confuse:

| Source | Purpose | Identity Caveat |
| --- | --- | --- |
| **OIDC ID Token** | RP authenticates End-User via OP | `(iss, sub)` pair is the user identification key |
| **OIDC UserInfo Response** | Supplements claims/profile when authorized | `sub` **must match** the ID Token; cannot stand alone as identity |
| **OAuth access token** | Client accesses API/Resource Server | `sub` may carry a different meaning per token/profile and grant type |
| **Refresh token** | Obtains fresh tokens per granted scope | Not a user key |
| **Local app session** | Holds the application's authenticated context | Uses local account ID and app policy |

If the UserInfo endpoint returns:

~~~json
{
  "sub": "someone-else",
  "email": "person@example.test"
}
~~~

while the verified ID Token has `sub="usr-7h2v8"`, the RP **must reject this UserInfo response** per OIDC; never merge another subject's claims into the current session.

**A JWT access token is not automatically an ID Token.** With client credentials, `sub` may identify a client/service rather than an End-User. At a Resource Server, validate issuer, audience, and token constraints per API profile, then map identity/authorization appropriately. Never take `sub` from an arbitrary access token to bind directly to an OIDC user account.

## 8. Database Model: External Identity Link Instead of Email Primary Key

A safe schema uses **`local_account`** and an external identity link table:

~~~text
local_account
  id (PK)
  status
  created_at
       ^
       | 1 account may have multiple external identities
       |
federated_identity
  id (PK)
  local_account_id (FK)
  issuer (exact string)
  subject (exact string)
  provider_registration (audit/routing, does not replace iss)
  linked_at
  verified_at
  link_method
  UNIQUE(issuer, subject)
~~~

Example **PostgreSQL** DDL (assuming `local_account(id)` already exists):

~~~sql
CREATE TABLE federated_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_account_id BIGINT NOT NULL
        REFERENCES local_account(id),
    issuer TEXT COLLATE "C" NOT NULL,
    subject VARCHAR(255) COLLATE "C" NOT NULL,
    provider_registration VARCHAR(100),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (issuer, subject),
    CHECK (length(issuer) > 0),
    CHECK (length(subject) > 0)
);

CREATE INDEX idx_federated_identity_account
    ON federated_identity(local_account_id);
~~~

**Why UNIQUE(issuer, subject)?** Prevents the same OP identity from being linked simultaneously to two local accounts, blocking race conditions and account takeover. By default, one external identity pair maps to one local account at a time; re-linking must go through an explicit workflow.

**Why not UNIQUE(email)?** Email is not an immutable identifier in OIDC and can change or be recycled.

**Why case-sensitive collation?** `sub` and issuer require exact comparison. The example above uses PostgreSQL's `COLLATE "C"` to illustrate deterministic case-sensitive matching; **never copy DDL verbatim to MySQL/SQL Server** without checking actual collation semantics.

**Do not use `client_id` as the composite key instead of `iss`:** the same OP may rotate client registrations, or a broker may expose multiple clients under one issuer, while pairwise `sub` can vary by sector. `client_id` is useful for auditing/migration, not as the canonical OP subject identifier.

### Concurrent Transactions

When two browsers complete login simultaneously for a new identity, the application must:

1. Verify the token and provisioning policy.
2. Inside a transaction, look up `(issuer, subject)`.
3. If absent and creation is permitted, insert the link protected by the **unique constraint**.
4. On unique violation, re-read the existing link and verify it belongs to the expected account.
5. Never silently reassign an identity link to another account.
6. Audit link/unlink events and enforce optimistic/concurrency control.

Doing `SELECT` followed by `INSERT` without a `UNIQUE` constraint risks creating two local accounts for the same OIDC identity under a race.

## 9. User Identification Flow After OIDC Authentication

~~~text
Browser selects registered OP
       |
Authorization Code + state/PKCE
       |
Token Endpoint -> ID Token
       |
Spring Security OIDC Client:
  verify JWS, issuer, audience, exp, nonce...
       |
Extract verified iss + sub from ID Token
       |
Federated Identity Service
  SELECT ... WHERE issuer = ? AND subject = ?
       |
    +-- Found, active ----------------> local account
    |
    +-- Not found --------------------> onboarding / policy
    |                                     |
    |                           approved JIT? create account
    |                           else: pending / denied
    |
    +-- Suspended / disabled ----------> deny
       |
Check tenant membership / app entitlements
       |
SecurityContext + app session, domain authorization
~~~

**Never turn `OidcUser.getName()` into the local account ID** without checking configuration. Spring Security exposes `sub` as the default principal name, yet multi-issuer federation apps need a **composite key** for lookup. With pairwise identifiers, one user having multiple `sub` values across clients also requires dedicated account linking.

When a domain service needs the local account ID, pass it through an **authenticated session/principal adapter** or an approved lookup service; never let individual controllers look up accounts by email.

## 10. How Does Spring Security OAuth2 Login Differ from SAML2 Login?

| Login Mechanism | Spring Security DSL | Identity Source |
| --- | --- | --- |
| SAML 2.0 SP | `http.saml2Login(...)` | SAML issuer + NameID (and format/qualifiers per profile) |
| OIDC RP | `http.oauth2Login(...)` with `openid` scope | **ID Token `iss` + `sub`** |
| Non-OIDC OAuth2 login | `http.oauth2Login(...)` where provider has no OIDC | Provider-specific `OAuth2User` attributes, no OIDC ID Token |
| JWT Resource Server | `http.oauth2ResourceServer(...)` | Access token claims per API config, **not OIDC login** |

**This topic concerns OIDC and identity brokering**, even though the parent module is Spring Security federation. To integrate with a broker **acting as an OIDC OP**, your SP needs Spring Security **OAuth2 Client/OIDC Login**, rather than feeding an ID Token into `saml2Login`. If the broker speaks SAML upstream, that is a **broker-side federation detail** and does not turn the RP–broker protocol into SAML.

An application can support both SAML2 Login and OIDC Login concurrently, yet must maintain **two separate token verification layers** before converging onto a unified local-account/tenant-authority model.

## 11. Configuring Two OIDC Providers in Spring Boot

With **Spring Boot 3.x, Spring Security 6.x, Java 17+**, include Spring MVC/Servlet, Spring Security, and `spring-boot-starter-oauth2-client`. Using discovery, each provider is configured with its own issuer.

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-op
            client-id: corp-portal
            client-secret: "${CORP_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          broker:
            provider: broker-op
            client-id: broker-portal
            client-secret: "${BROKER_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corp-op:
            issuer-uri: "https://login.example.test/realms/staff"
          broker-op:
            issuer-uri: "https://broker.example.test/realms/federation"
~~~

This is an **illustrative configuration** and cannot run logins without real OPs/issuers, client IDs, protected client secrets, registered redirect URIs, and valid discovery/JWKS. Never commit secrets to Git; use environment variables or a secret manager and HTTPS. `example.test` domains are examples only.

Common Spring Security URLs:

| URL | Purpose |
| --- | --- |
| `/oauth2/authorization/corp` | Starts OAuth2/OIDC login with client registration `corp` |
| `/oauth2/authorization/broker` | Starts login via the broker OP |
| `/login/oauth2/code/corp` | Authorization code callback for `corp` |
| `/login/oauth2/code/broker` | Authorization code callback for `broker` |

**Never confuse `registrationId=corp` with `iss`.** Registration ID is a Spring configuration name; the real `iss` must come from the verified ID Token and match the provider's issuer.

With issuer discovery, Spring fetches endpoints and JWKS from OP metadata. Configuring `issuer-uri` does not allow a token to arbitrarily pick another issuer or follow a browser-supplied URL.

## 12. Reading the Verified Issuer and Subject in Spring Security

When Spring Security **OIDC Login** succeeds, the principal typically implements `OidcUser`; the ID Token is accessible via `getIdToken()`. Javadoc for `IdTokenClaimAccessor` also provides `getIssuer()` and `getSubject()`.

Example controller printing only a **sanitized local identity key** for authenticated administrators (do not expose this endpoint publicly):

~~~java
package com.example.web;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityDebugController {

    @GetMapping("/internal/oidc-identity")
    public String identity(@AuthenticationPrincipal OidcUser user) {
        OidcIdToken token = user.getIdToken();
        String issuer = token.getClaimAsString("iss");
        String subject = token.getSubject();

        // Do not return the full ID Token or PII claims in the response.
        return "issuer=" + issuer + "; subject=" + subject;
    }
}
~~~

**This class belongs in a Spring Boot project**, not a standalone Java program. Protect this endpoint with administrator authorization or **remove it entirely in production**. `@AuthenticationPrincipal` must genuinely receive an `OidcUser`; if the endpoint can also be reached via SAML or anonymous requests, add separate handling or type checks.

**Why use `token.getClaimAsString("iss")`?** To retrieve the exact issuer string from the verified claim, avoiding accidental URL reformatting before using it as a database key. `token.getIssuer()` also exists but returns `java.net.URL` in many Spring Security versions; for storage keys, retain the raw OIDC string and exact matching.

**Do not perform user provisioning inside controllers.** Account resolution should run centrally before the application treats the user as a valid local account.

## 13. Extension Point: OidcUserService and Account-Link Lookup

Spring Security provides `OidcUserService` to load the OIDC principal after OIDC login processing. You can **delegate** to the default implementation and then call an application service to resolve `(iss,sub)`.

Example for **Spring Security 6.x / Servlet**, where `LocalIdentityLinker` is implemented by the app with a database and policy. The sample intentionally **does not auto-link accounts by email**.

`src/main/java/com/example/security/OidcIdentityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcIdentityConfig {

    // Application interface; requires a real DB-backed implementation/bean.
    public interface LocalIdentityLinker {
        boolean isActiveLinkedAccount(String issuer, String subject);
    }

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
            LocalIdentityLinker linker) {

        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser verifiedUser = delegate.loadUser(request);
            String issuer =
                verifiedUser.getIdToken().getClaimAsString("iss");
            String subject = verifiedUser.getIdToken().getSubject();
            String expectedIssuer =
                request.getClientRegistration()
                    .getProviderDetails().getIssuerUri();

            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()
                    || expectedIssuer == null
                    || !issuer.equals(expectedIssuer)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_oidc_identity"),
                    "OIDC issuer or subject is not trusted");
            }

            if (!linker.isActiveLinkedAccount(issuer, subject)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("unlinked_oidc_identity"),
                    "No active local account is linked");
            }

            // Return the principal processed by the OIDC provider.
            // Domain services must continue enforcing tenant/permissions.
            return verifiedUser;
        };
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .userInfoEndpoint(userInfo ->
                    userInfo.oidcUserService(oidcUserService)))
            .build();
    }
}
~~~

**The sample is Spring-dependent integration code**; it cannot be compiled/run with pure JDK `javac` and has no fixed stdout. You must provide a real `LocalIdentityLinker` bean, database schema, active-account check, client registrations, and OP. If JIT provisioning is desired, build a dedicated workflow rather than turning `false` into "auto-create admin".

**Trust boundary:** Spring Security must validate the OIDC ID Token and its issuer/audience/signature/nonce conditions before business services consume `iss/sub`. Never replace `OidcUserService` with code that Base64-decodes a token from the HTTP request and looks up accounts directly.

**Snippet limitation:** It only **allows or blocks an already-linked identity**; it does not yet replace `Authentication.getName()` with the local account ID or grant roles. If the application needs an internal principal, design a custom principal/lookup context or controlled stored account ID; never assume `getName()` is unique across multiple OPs.

### Where Does Each Validation Belong?

- **ID Token protocol validation:** Spring Security/OIDC library, not inside the SQL linker.
- **Local identity resolution:** service/DAO querying exact `issuer + subject`.
- **Provisioning & linking:** business workflow with explicit authorization and auditing.
- **Tenant membership & roles:** server-side domain policy.
- **Session management:** Spring Security; never use an email claim to share sessions across tenants.

## 14. OP Picker Page and Multi-Provider Issues

When multiple OIDC providers exist, Spring Security uses `ClientRegistrationRepository` to manage clients; `InMemoryClientRegistrationRepository` can iterate registrations for the default login page when configured appropriately.

~~~text
GET /private
     |
     v
Login page /login
   [OIDC Corp]     -> /oauth2/authorization/corp
   [OIDC Broker]   -> /oauth2/authorization/broker
     |
     v
Authorization Code Flow
     |
     v
Verified ID Token
     |
     v
(issuer, subject) -> local account
~~~

**Important:** `/oauth2/authorization/{registrationId}` starts **OAuth2/OIDC login**, not the SAML endpoint `/saml2/authenticate/{registrationId}`. Using the wrong path can route the request into the wrong security filter chain or fail to find a valid registration.

With hundreds of tenants, avoid publicly listing every issuer/registration. You can use an organization code or domain hint, mapped solely through a **server-side allowlist** to a registered provider; after callback, still check account and tenant membership. Never accept an arbitrary `issuer-uri` or JWKS URL directly from the browser because that enables SSRF and trust injection.

## 15. Identity Broker: Whose Issuer Does the RP See?

An identity broker can bridge upstream SAML IdPs, upstream OIDC OPs, LDAP, or other login systems. The broker authenticates/transforms the upstream source and issues a **new ID Token** to the RP.

~~~text
Browser
   |
   v
RP: https://portal.example.test
   |
   | OIDC Login (broker's client)
   v
Broker OP: https://broker.example.test/realms/main
   |
   +--> Upstream OIDC OP A
   |
   +--> Upstream SAML IdP B
   |
   +--> Upstream enterprise directory
   |
   v
Broker issues ID Token:
    iss = https://broker.example.test/realms/main
    sub = b-user-6201
   |
   v
RP verifies BROKER's ID Token
   |
   v
Identity link:
    (broker issuer, b-user-6201) -> local-account-9
~~~

**Very common mistake:** Seeing the upstream IdP on the login screen and storing `(upstream_iss, broker_sub)`. Those two values **do not belong to the same ID Token issuer**, producing a bogus identity key. Per OIDC, the RP must take the `iss/sub` pair from **the exact ID Token issued by the OP it trusts**.

If the broker adds custom claims such as:

~~~json
{
  "iss": "https://broker.example.test/realms/main",
  "sub": "b-user-6201",
  "identity_provider": "partner-a",
  "upstream_subject": "employee-8271"
}
~~~

then `identity_provider` and `upstream_subject` are **broker-defined custom claims**, **not standard OIDC Core claims replacing `iss/sub`**. They may only be used for specific purposes when:

1. The ID Token from the broker has been verified.
2. There is a defined contract for their meaning and trustworthiness with the broker.
3. The broker demonstrates that upstream identity mapping is securely governed.
4. Scope, tenant, and assurance match policy.
5. Upstream subjects from different providers are never merged casually.

**Note:** A broker may change how it maps upstream identities, split/merge tenants, or change `sub` when migrating user stores. In that case the RP needs a verified link migration even though the upstream human user is unchanged.

## 16. Upstream Identity vs. Downstream Identity: Never Mix Namespaces

If the application needs to know which upstream IdP a user signed in through to enforce policy, store **two clearly linked layers of information**:

| Layer | Example | Verified By |
| --- | --- | --- |
| **Downstream OIDC identity** | `(https://broker.example.test, b-user-6201)` | RP verifies the broker's ID Token |
| **Upstream identity** | `(https://op-a.example.test, 7182)` | Broker verifies upstream OP; RP trusts only via broker contract |
| **Local account** | `account-9` | Application account database |
| **Tenant membership** | `tenant-north` | Application/domain policy |
| **Assurance/MFA** | `acr`/`amr` emitted by broker | RP trusts broker per policy; do not assume it replaces upstream evidence |

**Never auto-merge accounts** by assuming `broker.sub == upstream.sub`, nor rely on `email_verified` as proof that two OP users represent the same local user. A broker can issue the **same broker `sub`** regardless of whether the user authenticated via upstream A or B if the broker linked those two upstream accounts; in that case **the broker owns safe linking**.

If the RP requires authorization based on the upstream IdP, the broker must provide contracted, signed claims or a protected API, along with anti-spoofing and trust policies. Never read upstream info from a redirect query parameter to grant privileges.

## 17. Account Linking: When Do Two (iss, sub) Pairs Point to One Account?

An application may let a user link multiple verified identities to a single local account:

~~~text
local-account-9
   |
   +-- (issuer corp, sub corp-user-1001)
   |
   +-- (issuer broker, sub broker-user-6201)
   |
   +-- (issuer partner, sub partner-88)
~~~

**These are independent links**, which does not mean the OIDC pairs are "equal". Having them point to the same local account is an **evidenced SP account-linking decision**.

### Safe Linking Workflow

1. The user is already signed into a **local account** with a trusted session meeting the required assurance level.
2. The user selects **add sign-in method**; the server creates a short-lived linking intent bound to session/CSRF/state and target.
3. The app initiates OIDC login with the second OP using an approved client registration.
4. Spring Security validates the new ID Token: signature, issuer, audience, nonce, state, and OIDC rules.
5. Extract `(iss,sub)` for the second OP and verify it is **not already linked to another account**.
6. Enforce step-up/MFA and consent policies if required by business rules.
7. Inside a transaction, insert the link onto the same local account, relying on the unique constraint.
8. Audit the OP, appropriate subject fingerprint/identifier, link method, actor, and timestamp; never log the raw ID Token.
9. If the link already belongs to another account, **reject or route to a verified recovery workflow**, never silently reassign.
10. When unlinking, ensure the account retains at least one valid sign-in/recovery method; prevent attackers from stripping all victim login methods.

### Strictly Avoid

- Auto-linking when emails from two OPs match, even with `email_verified=true`.
- Trusting a browser-supplied `sub` to create a link.
- Accepting a link based on unsigned or unverified upstream broker metadata.
- Allowing a user to swap the target account ID in a request to attach an OP identity to someone else's account.
- Moving an existing link from account A to account B simply because an email changed or an OP updated profile attributes.

## 18. JIT Provisioning and Account Lifecycle

**Just-in-Time (JIT) provisioning** creates a new local account on first OIDC login when `(iss,sub)` is absent from the database. This feature **should not be enabled by default for every OP**.

A safe policy distinguishes:

| State | Behavior |
| --- | --- |
| Link exists, local account active | Proceed to authorization checks |
| Link exists, local account suspended | Deny per account policy |
| No link, OP allowed to JIT for tenant | Create least-privilege account via approved workflow |
| No link, OP not allowed to JIT | Route to onboarding/deny; never auto-merge by email |
| Same subject, different issuer | Treat as a distinct identity; do not reuse old link |
| Broker reports upstream account changed | Verify broker contract/migration; never overwrite automatically |
| Subject suspected of being recycled or OP violates stability | Investigate/protect account; never grant rights from stale claims |

JIT provisioning must define explicitly: who may register, which tenants are permitted, whether invitations or domain proof are required, who approves roles, when accounts are revoked, and how to prevent account enumeration.

**Critical:** If an OP accidentally **reuses a `sub`** in violation of the spec, that is a severe identity-lifecycle defect. The RP cannot fix it with email; suspend trust, investigate, and coordinate with the OP.

## 19. Tenant Isolation and Authorization After Finding the Local Account

The `iss/sub` pair identifies the **external user** within the OP's scope, **not all permitted tenants**. One account may belong to multiple tenants, hold different roles, or be blocked in a particular tenant.

~~~text
ID Token validated
    |
    v
(iss,sub) -> local_account_id
    |
    v
active account? ---- no --> deny
    |
   yes
    |
    v
request tenant (client hint) -> validate server-side membership
    |
    v
roles/entitlements from application policy
    |
    v
resource-level authorization
~~~

If an OP is shared across multiple tenants, assigning a tenant solely from the issuer is wrong. If a broker fronts multiple upstream providers, assigning admin privileges solely from a custom `identity_provider` claim is also unsafe unless the trust and claim-mapping contract is verified.

**Example:**

- An's `(iss,sub)` pair links to `account-9`.
- `account-9` is a Viewer in tenant North and an Approver in tenant South.
- An selects North in the UI: the app must verify North membership and grant/enforce only North permissions.
- Even if `OidcUser` carries `email=admin@example.test`, never auto-grant `ROLE_ADMIN`.

Approving an operation like a payment requires identity, tenant membership, role, and object-level permission—not authentication alone.

## 20. Standalone Java 17: Composite Key, Guarding Against Subject and Issuer Confusion

The Java 17 example below simulates a link store: the same subject at two issuers **does not point to the same account**; an issuer with a different trailing slash is a different key; and two external identities can be intentionally linked to the same local account given proper proof.

Create file **OidcCompositeIdentityDemo.java**:

~~~java
import java.util.Map;
import java.util.Objects;

public class OidcCompositeIdentityDemo {

    record OidcKey(String issuer, String subject) {
        OidcKey {
            Objects.requireNonNull(issuer, "issuer");
            Objects.requireNonNull(subject, "subject");
            if (issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException("Empty issuer or subject");
            }
        }
    }

    private static final Map<OidcKey, String> LINKS = Map.of(
        new OidcKey("https://op-a.example.test", "42"), "ACCOUNT-A",
        new OidcKey("https://op-b.example.test", "42"), "ACCOUNT-B",
        new OidcKey("https://broker.example.test", "b-101"), "ACCOUNT-A"
    );

    static String localAccount(String issuer, String subject) {
        return LINKS.getOrDefault(new OidcKey(issuer, subject),
                "NOT_LINKED");
    }

    public static void main(String[] args) {
        System.out.println(localAccount(
                "https://op-a.example.test", "42"));
        System.out.println(localAccount(
                "https://op-b.example.test", "42"));
        System.out.println(localAccount(
                "https://broker.example.test", "b-101"));
        System.out.println(localAccount(
                "https://op-a.example.test/", "42"));
        System.out.println(localAccount(
                "https://op-a.example.test", "43"));
    }
}
~~~

Run with Java 17+:

~~~bash
javac OidcCompositeIdentityDemo.java
java OidcCompositeIdentityDemo
~~~

**Exact stdout:**

~~~text
ACCOUNT-A
ACCOUNT-B
ACCOUNT-A
NOT_LINKED
NOT_LINKED
~~~

**Explanation:**

1. OP A + `sub=42` resolves to ACCOUNT-A.
2. OP B + the **same** `sub=42` resolves to ACCOUNT-B: no cross-issuer collision.
3. Broker + `sub=b-101` also points to ACCOUNT-A because of an **approved separate identity link**.
4. An issuer with a trailing slash is a distinct string and never auto-aliased.
5. OP A + unlinked subject `43` is rejected per policy.

**Limitations:** `Map.of` simulates a link table after account linking has already been verified. The program **does not parse JWTs**, verify ID Tokens, use JWKS/nonces, or grant permissions. Production inputs to `localAccount` must come from **claims verified by the OIDC library**, never query parameters. In a real database, use `UNIQUE(issuer,subject)` and transactions rather than a static Map.

## 21. Pairwise Scenarios That Change the Subject

### Client A and Client B Use Two Different Sectors

~~~text
Issuer: https://op.example.test
Actual user at OP: U-17

Client A, sector-a -> sub = pw-111
Client B, sector-b -> sub = pw-222

Do not automatically treat the two pairs as the same local account.
To link them: requires broker/OP identity mapping or linking proof.
~~~

### Changing the Redirect URI Domain

If the OP computes pairwise subjects by sector and a client moves from `old.example.test` to `new.example.test`, `sub` may change. Coordinate `sector_identifier_uri` or an OP-supported migration instead of bridging via email.

### Splitting or Merging Client Registrations

When splitting one OIDC client into several, `sub` may remain identical or change depending on the OP's sector policy. Never guess from `client_id` alone; check `subject_types_supported`, sector configuration, and observed behavior with test accounts.

### Placing a Broker Between the RP and an Existing OP

Before:

~~~text
RP -> OP Corp:
 (iss=https://corp.example.test, sub=corp-77)
~~~

After:

~~~text
RP -> Broker:
 (iss=https://broker.example.test, sub=broker-88)
~~~

These are **two different identity pairs**, even though the broker internally authenticates the same user at Corp. To retain the local account, run a **verified migration link** from the old OP identity to the broker identity.

## 22. Changing Issuer, Switching OP, or Upgrading an Identity Broker

A change in `iss` can occur due to domain migration, realm/tenant path changes, vendor replacement, introducing a broker, or OP re-architecture.

**Never do this:**

~~~text
if (iss_old != iss_new) {
    // "Most likely the same person because the email matches"
    // -> overwrite old identity link with the new issuer
}
~~~

**Controlled migration workflow:**

1. **Inventory:** export current `(issuer,subject)` pairs, local accounts, tenants, and dependent applications.
2. **Define the proof source:** OP/broker supplies a migration mapping over a trusted, signed/verified channel, or users perform linking after authenticating both identities.
3. **Canary:** test a small cohort, checking pairwise/public `sub`, issuer path, and subject casing.
4. **Dual-link:** during transition, allow an account to hold two verified external links; never delete old links before all clients cut over.
5. **Collision handling:** if a new issuer+sub pair already belongs to another local account, halt and investigate; never overwrite.
6. **Tenant authorization:** never copy over obsolete roles merely because the identity switched OPs.
7. **Session lifecycle:** decide when old sessions must be revoked and when users must re-authenticate.
8. **Audit:** approver, evidence, timestamp, mapping version, and rollback capability.
9. **Cutover:** switch OIDC client registrations/issuers after new links are validated.
10. **Retire:** remove the old OP config only once no valid client/session/identity flow still depends on it per change policy.

**Never make issuer aliasing a permanent exception in code**, since overly broad aliases can merge two otherwise independent trust namespaces.

## 23. Securing UserInfo and Brokered Account Linking

When an OP exposes a `UserInfo Endpoint`, extra claims may come from supplementary sources, yet `sub` must match the ID Token. When a broker returns aggregated upstream profile data:

- The broker must verify upstream before issuing ID Tokens/UserInfo.
- The RP must verify the broker ID Token and the UserInfo–ID Token relationship.
- Custom attributes like `upstream_provider`, `external_user_id`, and `groups` require contracts on provenance and freshness.
- Never assume a group from upstream IdP A grants admin rights in tenant B just because the broker emitted the same email.
- Never combine an upstream `sub` with the broker's issuer to form a composite key.
- When broker account linking changes, enforce logging, review, and takeover detection.
- If UserInfo contains unexpected/mismatched claims, handle per policy; never switch the primary identity key from `iss/sub` to email.

In some architectures, the broker itself is the **source of truth** for downstream identity; the RP then stores the identity link **by broker issuer + broker subject** and lets the broker manage upstream links. If compliance requires the RP to track upstream links separately, store them in a **secondary table with explicit provenance and proof**, never as the login primary key.

## 24. Security Risks and Controls

| Risk | Symptom | Control |
| --- | --- | --- |
| **Cross-issuer collision** | Two OPs with the same `sub` treated as one user | Unique `(iss,sub)` key, exact matching |
| **Email-based takeover** | Recycled email lets a new user enter an old account | Never auto-link by email |
| **Unvalidated ID Token** | App decodes JWT without verifying | Use Spring OIDC validation; check signature/issuer/audience |
| **Token substitution** | ID Token from another client/OP accepted | Bind issuer/aud/azp/state/nonce to the exact client |
| **Wrong issuer normalization** | Stripping path/slash or lowercasing issuer merges namespaces | Keep issuer exact; use explicit migration |
| **Pairwise subject drift** | Sector change produces a new `sub` | Plan sector/migration; never bridge via email |
| **Broker upstream confusion** | Pairing upstream issuer with broker `sub` | Use only verified downstream ID Token `iss/sub` |
| **Account-link race** | Two local accounts claim one external identity | `UNIQUE(issuer,subject)` and transactions |
| **Cross-tenant privilege** | One OIDC login grants access across all tenants | Enforce separate membership/role/resource checks |
| **Over-trusting `email_verified`** | Merging accounts across two providers without proof | Linking workflow with MFA/step-up and auditing |
| **UserInfo subject mismatch** | UserInfo returns another user's claims | Reject if `UserInfo.sub` differs from `IDToken.sub` |
| **Unauthorized JIT** | Any OP creates internal accounts | Allowlist provisioning by OP/tenant/invitation |
| **Dynamic issuer SSRF** | Browser supplies arbitrary issuer/JWKS URLs | Allowlist `ClientRegistration`/OP metadata |
| **Access-token confusion** | Service access token treated as End-User ID Token | Separate token types, audiences, and grants |
| **Stale entitlement** | Locked account retains an active SP session | Session expiry/revocation and domain checks |

**Never fix errors by** disabling signature validation, dropping `aud` or `nonce`, trusting every issuer on the same hostname, or admitting new users into accounts with a matching email.

## 25. Identity Resolution Test Matrix

| Case | Data / Scenario | Expected Result |
| --- | --- | --- |
| 01 | Same issuer, same `sub`, valid ID Token | Resolves the same identity link |
| 02 | Same `sub`, different issuer | **Two distinct identities** |
| 03 | Same issuer, different `sub` | **Two distinct identities** |
| 04 | Issuer differs by path | Not treated as the same OP |
| 05 | Issuer differs by trailing slash | Not auto-aliased |
| 06 | Subject differs by case | Not auto-lowercased |
| 07 | Same email, different issuer/`sub` | Not auto-linked |
| 08 | `email_verified` is false | Never used as proof/account key |
| 09 | Email changes after login | Identity link remains unchanged |
| 10 | `UserInfo.sub` differs from `IDToken.sub` | Reject |
| 11 | Invalid token signature | Reject before identity lookup |
| 12 | Token issuer not in client config | Reject |
| 13 | Token `aud` lacks `client_id` | Reject |
| 14 | Token past `exp` | Reject |
| 15 | Wrong `nonce` when nonce was sent | Reject |
| 16 | Broker ID Token has broker issuer + broker `sub` | Link by broker identity |
| 17 | Broker provides custom `upstream_subject` | Does not replace composite key |
| 18 | Pairwise `sub` changes when sector changes | Must handle via migration/linking |
| 19 | New identity not approved for JIT | Deny or route to onboarding |
| 20 | Local account suspended | Do not grant an authorized session |
| 21 | Identity link already belongs to another local account | Deny re-link; route to review |
| 22 | Two concurrent logins create the same identity link | `UNIQUE` constraint prevents duplicates |
| 23 | User belongs to tenant X, picks tenant Y | Domain authorization denies Y |
| 24 | `client_credentials` access token has `sub` | Never used as an end-user ID Token |
| 25 | OP `issuer-uri` changes domain | Evidenced migration; no automatic alias |
| 26 | Two OPs use the same `registrationId` string in two apps | Use `iss/sub`, never `registrationId` as identity |
| 27 | OP replaced by broker with same email | Link only via approved proof/migration |
| 28 | Custom IdP URL from browser | Never fetch/join dynamic trust source |
| 29 | Unlinking last sign-in method | Enforce account recovery/step-up check |
| 30 | Login succeeds yet tenant permission is missing | Authentication may PASS, authorization must DENY |

**Integration testing:** Testing only `Map<OidcKey,AccountId>` is insufficient. Integrate with at least two OP/broker test accounts, verify real JWT/ID Tokens, test responses varying `iss/sub`, linking flows, concurrent transactions, and post-login requests on tenant resources. Never log raw tokens in unprotected test artifacts.

## 26. Common Error Diagnosis

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Login at OP A works, OP B lands in the same account | Lookup by `sub` alone or email | Fix to `(iss,sub)` and verify unique schema |
| User changes email and gets a new account | Email was used as the key | Use stable identity link; update email as profile |
| Duplicate accounts created after switching to broker | Broker `iss/sub` differs from old OP | Evidenced migration/linking |
| User gets new `sub` after changing redirect domain | Pairwise sector changed | Coordinate with OP; check `sector_identifier_uri` |
| OP issuer differs by one slash, token rejected | Exact issuer validation | Update metadata/client config after verifying the true OP; never skip verify |
| ID Token has `sub` yet login fails on `aud` | Token issued for another client | Use the right clientId/registration and token flow |
| UserInfo fails with subject mismatch | OP/UserInfo returned wrong person or swapped token | Reject; inspect OP and access token |
| Spring login succeeds yet no local account found | Unlinked or JIT disabled | Onboarding/linking workflow; do not look up by email |
| Duplicate records on parallel logins | Missing `UNIQUE` constraint or transaction | Add constraint and handle conflicts |
| Same `sub` across two clients | OP uses public or same-sector pairwise | Do not assume semantics without checking config |
| Different `sub` for same user across clients | OP uses pairwise with different sectors | Requires proof-based linking |
| API JWT `sub` fails to find user | Token is an access token with different scope/subject | Use resource-server policy; distinguish token types |
| Only tenant B's roles are wrong | Authorization conflated tenants or broker claims | Check membership and mapping scope |
| App allows `email_verified` to auto-link | Account takeover risk | Disable auto-link; migrate existing links if needed |
| `OidcUserService` configuration hits cast error | Login may be non-OIDC OAuth2 or SAML | Separate filter chains or type-aware handlers |

**Minimal logging:** OIDC client registration ID, issuer identifier (per policy), pseudonymized/hashed subject if needed, local account ID, link method, tenant scope, correlation ID, and error code. Never log verbatim ID Tokens, access/refresh tokens, client secrets, or unnecessary personal data.

## 27. Runbook for Changing an Issuer or Broker

**Before the change:**

1. Inventory current issuers, client IDs, public/pairwise `sub` usage, sector identifiers, tenant mappings, and identity links.
2. Identify who owns the mapping between the old OP and the new OP/broker.
3. Verify the proof source: signed migration manifest, trusted OP/broker admin API, or user-driven dual-auth linking.
4. Design rollback, auditing, and collision handling.

**During transition:**

1. Configure the new OP/broker via approved issuer discovery/JWKS.
2. Allow both login methods if policy permits, **without equating the two identity pairs automatically**.
3. Run canary accounts, verifying subject stability and how the broker mints downstream `sub`.
4. Add a **second external identity link** to the local account after proof is verified.
5. Verify disabled accounts, roles/tenants, and absence of duplicate accounts.
6. Monitor races/linking errors; never overwrite a pair belonging to another account.

**After cutover:**

1. Confirm all clients/sessions/tenants resolve the new identity pair properly.
2. Verify reauthentication, logout/revocation, and access to tenant resources.
3. Disable logins via the old issuer once no longer needed per change policy.
4. Retire old mappings after the retention period once recovery paths exist.
5. Retain audit/approval records; never purge logs/evidence needed for investigation.

**In case of account compromise or untrusted OP:** Activate security incident response—block logins and revoke sessions/tokens immediately instead of keeping a scheduled dual-link overlap.

## 28. Self-Assessment Questions

**1. Why can't `sub` alone be the user key in a multi-OP application?**  
Because `sub` is guaranteed unique only within **one issuer**. Two OPs can emit the same `sub` for two different people.

**2. Does `email_verified=true` at two OPs prove they are the same local account?**  
No. Emails can change or be reassigned, and OP verification does not replace the application's account-linking workflow.

**3. Do `https://op.test` and `https://op.test/realm` share the same identity namespace?**  
No. The OIDC issuer path is part of the identifier and must match exactly.

**4. When an OP uses pairwise subjects, can two clients receive the same `sub`?**  
Yes, if they share the same sector identifier. If they belong to different sectors, they receive different pairwise identifiers.

**5. The RP logs in via a broker whose upstream is OP A. Which issuer must the RP use as the identity key?**  
Use `iss` from the **broker ID Token verified by the RP**, paired with that token's `sub`; upstream identity is separate information requiring a contract and proof.

**6. Is `OidcUser.getName()` safe as a database primary key in a multi-issuer setup?**  
Not guaranteed, because the exposed value may be just `sub` or configured differently. Extract the verified ID Token's `iss` and `sub` explicitly.

**7. What if UserInfo returns a different `sub` than the ID Token?**  
Reject the UserInfo response; never mix in another person's claims.

**8. Why does changing an issuer URI require migration?**  
Because a new issuer creates a new identity namespace; exact matching makes the old and new pairs distinct, even for the same human user.

**9. Can a single local account link two `(iss,sub)` pairs?**  
Yes, with approved **explicit linking proof**; they are two distinct external identities pointing to one account.

**10. Is tenant authorization still needed after resolving the local account?**  
Yes. Authenticating identity and authorizing per-tenant data/roles are two independent concerns.

## 29. Production Deployment Checklist

- [ ] Read `iss` and `sub` solely from a **verified OIDC ID Token** or claims guaranteed by the library to belong to that token.
- [ ] Ensure ID Token signature, issuer, audience/client_id, `azp` when applicable, `exp`, nonce, state, and code flow are verified.
- [ ] Require exact match on `iss`/discovery issuer; reject unauthorized dynamic issuers or JWKS URLs.
- [ ] Use **`(issuer,subject)`** as the external identity key, never email or bare `sub`.
- [ ] Enforce `UNIQUE(issuer,subject)`, case-sensitive collation, and transaction-safe linking in the database.
- [ ] Preserve exact issuer/sub strings; never lowercase subjects or strip issuer paths/slashes.
- [ ] Know whether OP subject types are **public** or **pairwise**, checking sectors and client registration policy.
- [ ] If UserInfo is used, verify `UserInfo.sub == IDToken.sub`.
- [ ] When using a broker, separate **downstream broker identity** from **upstream identity** and custom claims.
- [ ] Require proof, CSRF/state protection, step-up when needed, and auditing for account linking between two OPs/brokers.
- [ ] Enable JIT provisioning only per OP/tenant policy; never auto-link solely on `email_verified`.
- [ ] Domain authorization checks active local account, tenant membership, and resource-level entitlements.
- [ ] Never treat a `client_credentials` access token as an End-User ID Token.
- [ ] Maintain a migration plan when issuers, brokers, redirect sectors, or pairwise subjects change.
- [ ] Test cross-issuer same-sub, email collisions, exact issuer matching, UserInfo mismatches, and concurrent linking.
- [ ] Never log raw tokens, client secrets, PII, or unnecessary subject identifiers.
- [ ] Maintain runbooks for account takeover, issuer migration, and safe unlinking/recovery.

## 30. Conclusion

**In OpenID Connect, the trustworthy identifier for an End-User is `(iss,sub)` extracted from a verified ID Token.** `sub` has meaning only within its issuer namespace; email, username, and phone number lack equivalent stability and uniqueness guarantees. When an OP uses pairwise subjects, one person can have different `sub` values across sectors; the application must never guess they are equivalent.

**In an identity broker model**, the RP directly trusts the **broker-issued ID Token**, and must therefore store **broker issuer + broker subject**; upstream identities are managed by the broker or passed via separate contracted and verified mechanisms. To let multiple identities sign into one local account, use an **identity links table, `UNIQUE(issuer,subject)`, explicit account-linking workflows, and server-side tenant authorization**.

Spring Security supports OIDC through `oauth2Login`, `OidcUser`, and `OidcUserService`. The library handles OIDC protocol validation, while the application governs local-account links, policies, provisioning, and permissions. **Never trade identity correctness for convenience by merging on email or blindly trusting any JWT with a `sub`.**

### Official Documentation

- OpenID Connect Core 1.0 (Errata Set 2), **5.7 Claim Stability and Uniqueness**, **8 Subject Identifier Types**, and **16.15 Issuer Identifier**: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0 (Errata Set 2), definitions of `issuer` and `subject_types_supported`: https://openid.net/specs/openid-connect-discovery-1_0-errata2.html
- OpenID Connect Dynamic Client Registration 1.0, `sector_identifier_uri`: https://openid.net/specs/openid-connect-registration-1_0.html
- Spring Security — OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — OAuth2 Login Advanced Configuration, OidcUserService, and ID Token signature verification: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security Javadoc — OidcUser: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- Spring Security Javadoc — IdTokenClaimAccessor: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
