# Identifying the Issuer, Relying Party, and Protected Resource in Identity Federation

In an identity federation system, a trust decision must always answer three independent questions:

1. **Who issued the credential?** Which identity provider or authorization server issued the assertion/token, and does the system actually trust that source?
2. **Who is the authorized recipient?** Which application/client/service provider or API is the intended recipient of the credential?
3. **What resource is protected?** After receiving a valid credential, what actions is the user allowed to perform on which specific API, data, record, and tenant?

A token with a valid signature only proves that it originated from a trusted key; **that is not enough** to use the token in any application or grant access to any data. Misidentifying any one of the three roles can lead to accepting the wrong token, confusing organizations, linking the wrong account, or cross-tenant access.

This lesson focuses on how to identify the three roles and trust boundaries in enterprise SSO, OpenID Connect (OIDC), OAuth 2.0, SAML 2.0, and Spring Security applications.

## 1. The Three Core Roles and Related Terminology

| Question | Role | Common Terms | Responsibilities |
| --- | --- | --- | --- |
| Who authenticates and issues? | **Issuer** | Identity Provider (IdP), OpenID Provider (OP), Authorization Server (AS), SAML IdP | Authenticates users or grants authorization, signs/issues credentials according to the protocol |
| Who receives and processes the credential? | **Recipient / Relying Party** | Relying Party (RP), OIDC Client, SAML Service Provider (SP), OAuth 2.0 Resource Server | Verifies the credential is from the right source, for the right recipient, and meets conditions; establishes the security context |
| What needs to be protected? | **Protected Resource** | Protected Resource, API endpoint, data object, tenant, business operation | Enforces authorization based on subject, scope, role, tenant, and context |

**Note:** One component may hold multiple roles depending on the protocol and flow. A web application is an OIDC client/RP when receiving an ID token to sign in; an API called by that application can be a resource server when receiving an access token. In OAuth 2.0, **a resource server is also an access token recipient**, though it is not necessarily where the user signs in via a browser.

To name the roles accurately, you must also distinguish:

- **Subject (`sub` / NameID):** the identity the credential refers to. The subject is not the issuer; an identical subject string from two different issuers is not automatically the same person.
- **Trust anchor:** the trust configuration—for example, allowed issuers, metadata, signing keys/JWKS or SAML certificates, client registrations, and organizational policies. A URL pointing to an IdP does not create a trust relationship by itself.
- **Audience (`aud` / AudienceRestriction):** the intended recipient for which the credential was issued. It is not synonymous with "the user gets to view every resource".
- **Recipient/destination:** where the SAML message is sent; it must match the registered receiving endpoint and flow.
- **Tenant/organization:** the administrative and data scope the user is accessing. Tenant belongs to application policy, not a permission that automatically emerges from a token signature.
- **Scope/authority/role:** information that can assist authorization decisions; you must distinguish the source granting the scope, how roles are mapped, and the policy of the specific resource.

## 2. How to Ask the Three Questions on a Diagram

Suppose an employee of company B needs to use company A's order management application:

~~~mermaid
flowchart LR
    U["Employee B"]
    I["IdP B<br/>Identity Issuer"]
    W["Portal A<br/>OIDC Client / RP"]
    API["A's Orders API<br/>Resource Server"]
    D[("Tenant B Orders<br/>Protected Resource")]
    U -->|"Sign in"| I
    I -->|"ID token for Portal A"| W
    W -->|"API-appropriate access token"| API
    API -->|"Tenant + order policy"| D
~~~

The diagram illustrates **logical responsibility relationships**; depending on the architecture, Portal A may use a server session, call the API itself with another token, or the application may be issued an access token with the API's exact audience. An ID token from IdP B intended for Portal A **must not be passed straight through as a bearer token for the Orders API** simply because the user has signed in.

Identifying roles at each hop:

| Hop | Issuer | Intended Recipient | Protected Resource / Decision |
| --- | --- | --- | --- |
| OIDC sign-in to Portal | OpenID Provider trusted by Portal A | OIDC client Portal A (ID token has an audience matching the client) | Create/maintain the login session after verification |
| OAuth 2.0 call to Orders API | Authorization Server issuing the access token | Orders API or the introspection/authorization mechanism configured for the API | Endpoint, action, order, and tenant |
| SAML sign-in to an SP | SAML IdP | SP with configured entityID/ACS | SP session; resource permissions are still decided by the SP |
| SCIM synchronization (if any) | Lifecycle/user governance source | SCIM service endpoint | Create, update, deactivate accounts; does not replace login tokens |

One product may act as both an IdP and an Authorization Server, but the roles of authentication, issuing access tokens, and checking API permissions remain distinct logical steps.

## 3. Identifying the Issuer: Who Is Really Behind `iss`?

### With OpenID Connect

A JWT-formatted ID token typically contains these claims:

~~~json
{
  "iss": "https://login.partner-b.example",
  "sub": "employee-842",
  "aud": "portal-a-client",
  "iat": 1760000000,
  "exp": 1760003600
}
~~~

This is an **illustrative payload**, not a signed JWT, and cannot be used for authentication. To conclude that an issuer is trusted, the RP must verify the real token against allowed metadata, algorithms, and signing keys, and match `iss` against the configured issuer. Do not take the `iss` value from unverified JSON to automatically trust it or download configuration from an arbitrary user-supplied URL.

Checklist for an OIDC issuer:

1. The issuer name is registered and allowed for the relevant application/tenant.
2. Discovery metadata, JWKS URI, and key rotation procedures are fetched from a trusted source matching the configuration.
3. The signature is valid under an allowed algorithm; reject `alg=none` and algorithms not permitted by policy.
4. `iss` matches the expected issuer; the token satisfies `iat`, `exp`, and other conditions for the token type.
5. The token was issued **for the right recipient** via `aud`; do not mix up tokens from other clients/APIs.
6. `sub` is interpreted within the scope of the issuer before mapping it to an internal identity.

The issuer is the *source responsible for the identity claims or token*; a company email address, domain shown on the login page, hostname in the redirect URL, and token issuer are not always the same. Do not infer trust based solely on the `@partner-b.example` suffix.

### With OAuth 2.0

An Authorization Server issues an **access token** so a client can access resources. Depending on the system, the token may be a JWT or an opaque token. If it is a JWT with an issuer, the API must check the signature, issuer, and audience according to configuration; if it is an opaque token, the API needs introspection or the deployed verification mechanism. An access token valid for API X is not automatically valid for API Y.

**OAuth 2.0 by itself is not a login protocol.** OIDC provides the ID token and identity verification rules for the client. "The Authorization Server issued an access token" does not mean "the API can use the access token as an ID token to sign a user in".

### With SAML 2.0

The issuer is the SAML IdP with a trusted `Issuer` (entityID). The SP verifies the XML signature in the proper context, the configured signing certificate, metadata, and assertion conditions. Do not infer the issuer from the domain name in the browser, or from the user's NameID/email.

### When an Identity Broker Is Present

~~~mermaid
flowchart LR
    U["User"]
    O["B's upstream IdP"]
    B["A's Identity Broker"]
    R["A's RP Application"]
    U --> O
    O -->|"Upstream assertion/token"| B
    B -->|"Broker-issued token"| R
~~~

If the RP directly receives a **token signed by the broker**, the issuer that the RP verifies is typically the **broker**. IdP B is the **upstream** authentication source, not the direct issuer of that token. Only use an "upstream identity provider" claim when the broker commits to, protects, and clearly defines the claim's meaning. Do not trust an arbitrary claim from the browser to "switch issuers".

## 4. Identifying the Recipient: Who Was the Credential Issued For?

Verifying the signature and issuer is not enough: the token/assertion must be **bound to the right recipient**.

### OIDC ID Token: RP/Client and `aud`

Suppose one IdP serves two applications:

- Portal A has `client_id = portal-a-client`.
- Dashboard C has `client_id = dashboard-c-client`.

An ID token with `aud = portal-a-client` is meant for **Portal A**. Dashboard C must not accept that token for sign-in, even if the signature and issuer are valid. When `aud` has multiple values, full OIDC rules regarding audience and `azp` (authorized party) must be applied where required. The RP must also enforce `state`, flow-appropriate `nonce`, redirect URI, and code exchange checks to prevent transaction mixing and login CSRF attacks.

### OAuth 2.0 Access Token: Resource Server and API Audience

Suppose the same Authorization Server issues tokens for:

- `orders-api`: view and edit orders.
- `payroll-api`: view payroll data.

A token intended for `orders-api` must not be accepted at `payroll-api`. The audience condition must be checked against the **access token** contract, which may differ from the `aud` of an ID token used for the Portal. A `scope` like `orders.read` also does not imply permission to view every order of every tenant.

If the access token is opaque and can only be verified via introspection, the API must verify that the token is active, along with its permissions/scopes and resource information consistent with the authorization server model. Do not attempt to decode an opaque token as a JWT.

### SAML Assertion: SP entityID, ACS, and Recipient Conditions

For SAML Web Browser SSO:

- `Issuer` identifies the IdP.
- `AudienceRestriction` restricts the assertion to the intended **SP entityID**.
- `SubjectConfirmationData Recipient` must typically match the appropriate receiving ACS URL.
- `Destination`, `InResponseTo` (when applicable), `NotBefore`/`NotOnOrAfter`, and a replay cache help bind the exact message and timeframe.

SP X must not accept an assertion for SP Y. Do not just look for an assertion with "the right email" and grant a session. With SAML, you must use an XML Signature processing library that prevents signature wrapping and verifies the exact referenced message elements that are required to be signed.

### Quick Identification Table

| Credential | Issuer to Verify | Recipient to Check | Do Not Use As a Substitute For |
| --- | --- | --- | --- |
| OIDC ID token | Trusted OP/issuer | OIDC client (`aud`/`azp` per rules) | Access token for an API |
| OAuth JWT access token | Trusted Authorization Server/issuer | API/resource audience and token policy | ID token to sign a user in |
| OAuth opaque access token | Authorization Server via introspection or equivalent mechanism | Resource/API, active status, scope, policy constraints | Self-verifiable signed JWT |
| SAML assertion | Trusted SAML IdP/entityID | SP entityID, recipient/ACS, assertion conditions | Arbitrary bearer token for an API |
| Application session cookie | Application issuing/managing the session | Application owning the session | Cross-organization credential or API access token |

## 5. Identifying the Protected Resource: API Address Is Only the First Layer

"Resource" does not stop at the endpoint. An API `GET /api/orders/812` might return an order belonging to tenant B; user C, even with scope `orders.read`, must still not see that order.

Verification layers should be separated:

1. **Authentication:** Is the token/assertion or session valid and associated with an identified principal?
2. **Token acceptance:** Do the issuer, audience, expiration, status, and protocol bindings match the exact application/API?
3. **Coarse authorization:** Does the token have the scope/authority required to invoke this API group?
4. **Tenant membership:** Is the principal a valid member of the target tenant according to application-controlled data?
5. **Object-level authorization:** Which tenant does the record/order belong to, who is the owner, and is there valid sharing?
6. **Business policy:** Do the order status, separation of duties, limits, or business conditions allow the action?

Example checks for `GET /api/tenants/B/orders/812`:

| Condition | Expected Result |
| --- | --- |
| Valid JWT signature, correct issuer, audience contains `orders-api` | Token can be authenticated for the API |
| Token has scope `orders.read` | Allowed to proceed to order-read business checks |
| Principal is only a member of tenant C | **DENY** due to not belonging to tenant B |
| Principal belongs to B, but order 812 belongs to C | **DENY** due to object-level access control |
| Principal belongs to B, order 812 belongs to B, and read permission exists | **ALLOW** if all other conditions are also met |

A tenant name in the URL, path, query, header, or body is client-chosen data. The server must cross-check it against actual membership and permissions; do not trust `X-Tenant-Id` or a self-asserted `tenant` claim from an unauthorized source as the ultimate source of authority. A tenant claim issued by a trusted authorization server can be used, but a consistent policy is still needed regarding the claim's owner, tenant scope, and object permissions.

**An ID token does not grant data access permissions.** A successful sign-in only means the recipient has authenticated the identity per policy; per-resource permissions must be evaluated separately.

## 6. Intra-Organization and Cross-Organization Federation Models

### Example A: A Company with Multiple Internal Applications

- Company A's IdP is the issuer of ID tokens for Portal, Wiki, and HR.
- Portal, Wiki, and HR are three RPs with separate client registrations/audiences.
- The HR API is a resource server, and payroll data is an especially sensitive resource.

An employee who has signed in to Portal via SSO does not automatically have permission to read payroll. HR must verify a token suitable for the HR API as well as roles/membership. A Wiki token with a valid issuer but an audience of Wiki must be rejected by HR.

### Example B: Organization A Collaborating with B and C

- IdP B and IdP C are two external identity sources.
- A's partner portal is an RP, or a broker inside A is the upstream RP.
- A's Orders API protects records by tenant and contract.
- A is the authority deciding membership/roles for guests from B/C in A's data.

Company B can authenticate B's employees, but **must not automatically grant administrative permissions over all of A's data** solely through a group/role issued by B. If a `groups = ["admin"]` claim comes from B, A only uses it after an explicit permission-mapping contract and policy, preventing roles from carrying over to a different scope.

### Example C: Multiple IdPs Behind One Broker

- The broker accepts and verifies upstream tokens from B/C.
- The broker issues a new token for Portal A.
- Portal A verifies the issuer/audience of the **broker token**.
- The broker must reliably provide upstream information if A needs to distinguish between B and C, and A still checks tenant membership.

Key takeaway: the number of issuers and recipients changes at **each token hop**, not by the product's commercial name. Each hop has its own recipient and trust policy.

## 7. The Trust Matrix Must Be Explicitly Declared

To build a multi-organization system, design a trust matrix instead of inferring trust from email domains or redirect URLs:

| Relationship | Allowed Issuer/IdP | Recipient | Token/Assertion | Resource and Policy |
| --- | --- | --- | --- | --- |
| A → Portal A | `https://idp.a.example` | `portal-a-client` | OIDC ID token | Create Portal session; then check membership |
| B → Portal A | `https://login.b.example` | `portal-b2b-client` | OIDC ID token | Only guests invited by A |
| A AS → Orders API | `https://auth.a.example` | `orders-api` | Access token | Scope + role + tenant + ownership |
| A IdP → Legacy SP | `https://idp.a.example/saml` | `urn:sp:legacy-a` | SAML assertion | Legacy session; separate policy |

This table is a design example; URIs using the `.example` domain do not exist for direct deployment. In practice, you must store key/certificate configurations, metadata, client IDs, ACS/redirect URIs, expiration times, authentication levels, rotation/revocation procedures, and owners.

**There is no default transitive trust.** If Portal A trusts broker X, and X trusts IdP B, that does not mean all of A's other services automatically trust IdP B tokens directly; nor does it mean B is allowed to issue valid tokens for all of A's APIs. Every RP/resource server must have its own trust contract.

## 8. Process for Analyzing a Request When Multiple Tokens Exist

When reviewing an architecture diagram or an incident, apply the following process at **each hop**:

1. Identify which request/response carries a token, assertion, or cookie; **do not confuse an ID token with an access token**.
2. Identify the exact **signer/issuer** of the token (issuer, entityID, authorization server, session authority).
3. Identify which **client/API/SP** the token was issued for using `aud`, entityID, recipient, and redirect/ACS configuration.
4. Identify the real recipient: reverse proxy, backend, RP, or API? Does that component verify the token itself or merely trust headers from a proxy?
5. Specify the trust boundary at each step, such as Internet → RP, RP → API, proxy → backend, tenant B → A's data.
6. List the resources (endpoint, object, tenant, data), actions (read/write/admin), and business conditions.
7. Identify who owns the data and who is the authority for permissions. Do not automatically turn external claims into internal permissions.
8. Map out **deny** cases: wrong audience token, unknown issuer, expired, wrong tenant, revoked membership, object belonging to another party.

In a reverse proxy or API gateway architecture, clarify who the **final token verification point** is. If the backend trusts an `X-User` header passed by the gateway, the gateway→backend connection must be protected, client-sent headers must be stripped/overwritten at the gateway, and the backend's authorization policy must be explicit. Do not trust arbitrary user headers from the Internet.

## 9. Applying with Spring Security: OIDC Login at the RP

With Spring Boot 3.x, Java 17+, and a Servlet application using OIDC, two commonly used dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

An `application.yml` example illustrating **two issuers**, each with a separately registered client registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-a:
            provider: corp-a
            client-id: portal-a-client
            client-secret: REPLACE_WITH_SECRET_MANAGER_VALUE
            authorization-grant-type: authorization_code
            scope: [openid, profile]
          partner-b:
            provider: partner-b
            client-id: portal-b2b-client
            client-secret: REPLACE_WITH_SECRET_MANAGER_VALUE
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          corp-a:
            issuer-uri: https://idp.a.example
          partner-b:
            issuer-uri: https://login.b.example
~~~

The issuers/secrets above are placeholder data. `issuer-uri` is used to locate OIDC protocol configuration if the IdP supports standard discovery. The Redirect URI on the IdP must match the client callback configured in the application; by default in many Spring Security configurations, it takes the form `/login/oauth2/code/{registrationId}`. Login initiation URLs typically take the form `/oauth2/authorization/corp-a` or `/oauth2/authorization/partner-b`.

A minimal security filter chain for web login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfiguration {
    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Place the class above in `PortalSecurityConfiguration.java` in a Spring Boot project with the dependencies mentioned above. `oauth2Login` handles the authorization code flow and verifies OIDC data per registration; **the sample configuration does not decide who can view orders or which tenant they belong to**. After sign-in, the application must look up the mapping by verified issuer/subject and membership at A, then enforce object-level permissions in the service/repository.

Do not build the issuer list using an unverified `issuer` value from a query string; tenant selection must be bound to an allowed registration per server configuration. For **SAML**, use Spring Security SAML2 Service Provider (`spring-security-saml2-service-provider` with `saml2Login`) and a `RelyingPartyRegistration` configured with the appropriate metadata/certificates/entityID/ACS. OIDC RP and SAML SP use different terminology, but both require checking the issuer, the recipient, and application permissions.

## 10. Applying with Spring Security: Resource Server Protecting an API

Suppose A's Orders API accepts JWT access tokens from **one trusted issuer**, and only when the audience includes `orders-api`. You can configure `spring-boot-starter-oauth2-resource-server`, add a security chain, and add an audience validator. This is a **design example for a single issuer**; a multi-issuer environment requires a separately configured registry/allowlist and resolver.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {
    private static final String TRUSTED_ISSUER = "https://auth.a.example";
    private static final String REQUIRED_AUDIENCE = "orders-api";

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation(TRUSTED_ISSUER)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(REQUIRED_AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Token audience is not orders-api", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

This is an **application configuration class**, not a standalone runnable Java program. With a standard JWT, the library decodes and verifies the signature using keys from the configured issuer. `JwtValidators.createDefaultWithIssuer` checks the issuer along with default time-related conditions; the second validator checks the audience. By default, Spring Security typically maps access token scopes to `SCOPE_...` authorities under standard JWT resource server configuration. If a provider uses a different claim, a controlled custom converter is required.

**Important limitation:** `hasAuthority("SCOPE_orders.read")` only checks the scope; it does not check the specific order or tenant. The endpoint/controller/service must look up the order by ID, determine the true tenant, membership, and object-level permissions. Do not assume that someone with `orders.read` can view every order. In a multi-client/multi-issuer system, do not open the decoder to accept any issuer just to avoid login errors; only allow issuers with a trust contract, check the specific audience per API, and avoid confusable issuers.

**Why can't Portal's token replace an access token?** An ID token typically has Portal's client as its audience, whereas Orders API requires `orders-api` as the audience. If the API only checks the signature and accepts any token from the same issuer, an attacker can present a valid token **intended for another recipient** to the API (token substitution/confused deputy).

## 11. Standalone Java 17: Verifying the Three Roles at the Policy Layer

The following snippet simulates **a policy decision after the credential has been cryptographically verified**. It **does not sign, decode, verify JWTs, or perform authentication**. In a real product, the `issuer`/`subject`/`audience` fields of `VerifiedContext` must come from Spring Security or a trusted token-verification component; they must not be taken directly from user-submitted data.

Create the file `TrustBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class TrustBoundaryDemo {
    record IdentityKey(String issuer, String subject) {}
    record VerifiedContext(IdentityKey identity, String audience,
                           Set<String> scopes) {}
    record Order(String id, String tenantId) {}

    private static final Set<String> TRUSTED_ISSUERS =
            Set.of("https://idp.partner-b.example");
    private static final String API_AUDIENCE = "orders-api";

    static boolean canReadOrder(
            VerifiedContext context,
            Order order,
            Map<IdentityKey, Set<String>> memberships) {

        if (!TRUSTED_ISSUERS.contains(context.identity().issuer())) {
            return false;
        }
        if (!API_AUDIENCE.equals(context.audience())) {
            return false;
        }
        if (!context.scopes().contains("orders.read")) {
            return false;
        }
        return memberships
                .getOrDefault(context.identity(), Set.of())
                .contains(order.tenantId());
    }

    public static void main(String[] args) {
        IdentityKey userB = new IdentityKey(
                "https://idp.partner-b.example", "employee-842");
        Map<IdentityKey, Set<String>> memberships =
                Map.of(userB, Set.of("tenant-b"));

        VerifiedContext valid = new VerifiedContext(
                userB, "orders-api", Set.of("orders.read"));
        VerifiedContext wrongAudience = new VerifiedContext(
                userB, "portal-a-client", Set.of("orders.read"));
        VerifiedContext unknownIssuer = new VerifiedContext(
                new IdentityKey("https://unknown.example", "employee-842"),
                "orders-api", Set.of("orders.read"));

        Order orderB = new Order("B-101", "tenant-b");
        Order orderC = new Order("C-201", "tenant-c");

        System.out.println("B order: " +
                canReadOrder(valid, orderB, memberships));
        System.out.println("C order: " +
                canReadOrder(valid, orderC, memberships));
        System.out.println("Wrong audience: " +
                canReadOrder(wrongAudience, orderB, memberships));
        System.out.println("Unknown issuer: " +
                canReadOrder(unknownIssuer, orderB, memberships));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac TrustBoundaryDemo.java
java TrustBoundaryDemo
~~~

Exact stdout:

~~~text
B order: true
C order: false
Wrong audience: false
Unknown issuer: false
~~~

Meaning of each result:

- **B order: true** — valid issuer, valid API audience, has read scope, and is a member of tenant B.
- **C order: false** — same authentication/scope info, but the order belongs to tenant C.
- **Wrong audience: false** — a token intended for Portal A is not accepted at the Orders API.
- **Unknown issuer: false** — an issuer not on the allowlist is rejected, even if the subject looks familiar.

In production, policy must look up current permissions in the data store, apply unique identity mapping, check per-order permissions, and never accept a `VerifiedContext` constructed by the caller. The Java demo uses an in-memory map to clarify boundaries, not as a complete token-verification or authorization solution.

## 12. Risks of Confusing the Issuer, Recipient, or Resource

| Mistake | Boundary Broken | Attack/Consequence | Mitigation |
| --- | --- | --- | --- |
| Trusting any issuer from a claim or input URL | Issuer source | Forged/spoofed tokens or unapproved source | Allowlist, trusted metadata/JWKS, verify signature and issuer |
| Checking signature only, skipping `aud` | Recipient | Using another RP/API's token on the current system | Check audience for the exact client/SP/API |
| Using an ID token as a bearer token for an API | Credential type / recipient | Token substitution, granting access for the wrong purpose | API uses an appropriate access token, verifies resource audience |
| Confusing broker issuer with upstream IdP | Issuer source | Wrong identity mapping and partner policy | Verify the issuer of the received token; upstream via trusted broker claim |
| Merging users by email/subject without issuer | Cross-organization identity | Account takeover or mis-linking | Use issuer + subject + tenant; verify before linking |
| Trusting roles from a partner IdP as A's admin rights | Application permissions | Privilege escalation | Explicit role mapping, permissions governed by A |
| Assuming a valid scope suffices to read every record | Specific resource | IDOR/BOLA, cross-tenant data leak | Membership and object-level authorization |
| Verifying SAML signature while skipping recipient/audience | SP recipient | Assertion for another SP wrongly accepted | Validate entityID, ACS, audience, recipient, InResponseTo |
| Accepting `X-User` header from the Internet | Proxy/backend | Impersonation at the backend | Trusted proxy, strip incoming headers, protect the channel |
| Disabling login at IdP only, leaving active sessions | Access lifecycle | Former employee uses old session/token | Deprovision, session expiry/revocation, and permission review |

**Deeper controls:** restrict accepted algorithms, prevent replay, protect `state`/`nonce`, enforce reasonable clock synchronization/skew, rotate keys, require MFA/step-up for sensitive operations, manage secrets securely, avoid logging tokens/secrets, trace issuer/subject/tenant, and enforce allow/deny decisions in compliance with data protection regulations.

## 13. Scenario-Based Trust Boundary Testing

Do not stop testing at "sign-in succeeded". Build a test suite covering tokens, recipients, and resources:

1. **Valid issuer + right audience + right permissions:** request is accepted.
2. **Unknown issuer:** rejected during token verification; do not create a local user based on an email matching an internal user.
3. **Valid issuer, another application's audience:** rejected at the recipient.
4. **Expired JWT / invalid signature or untrusted key:** rejected before authorization.
5. **Token has `orders.read`, but order belongs to another tenant:** rejected at the object layer.
6. **Same `sub` from two issuers:** do not automatically merge the two users.
7. **Same email from B/C:** do not automatically link accounts.
8. **SAML assertion for SP Y sent to SP X:** rejected due to audience/recipient/ACS mismatch.
9. **Gateway skips token verification or forwards client headers straight through:** backend must reject the untrusted path.
10. **Permissions/tenancy revoked after token issuance:** API adheres to the designed validity policy and revocation/TTL mechanisms.
11. **Issuer/certificate/JWKS or broker change:** system only accepts per newly approved configuration with migration/audit procedures.
12. **Two organizations use group `admin`:** B's permissions never automatically become A's administrative permissions.

When logging results, record business error codes and non-sensitive metadata such as registration name, verified issuer, expected audience, and tenant/resource ID per retention policy; avoid storing full bearer tokens, SAML assertions, or unnecessary personal data.

## 14. Practical Checklist When Designing Spring Security Federation

| Step | Question to Answer | Evidence/Artifact |
| --- | --- | --- |
| Identify the issuer source | Which OP/AS/IdP is trusted for each organization? | Issuer/entityID allowlist, metadata, keys/certificates |
| Identify the receiving hop | Which RP/SP/API is receiving the right token type? | Client registration, redirect URI/ACS, audience, validator |
| Identify the principal | Who does `issuer + subject` map to? | Identity link store; link/unlink audit |
| Identify the resource | Which endpoint, object, data set, tenant? | Resource map, ownership, tenant hierarchy |
| Identify permissions | Who governs scopes/roles and membership? | Source-of-truth policy, role mapping, access conditions |
| Lifecycle | Who has permission to invite, grant, modify, and revoke access? | SCIM/JIT/invitation policy, session revocation and expiry |
| Negative testing | What if a token has the wrong issuer/audience, or right scope/wrong tenant? | Automated security tests and audit logs |
| Operations | Who manages issuers/JWKS/certs and cross-organization incidents? | Runbook, key rotation, alerting, recovery |

**Rule of thumb:** for **every token or assertion**, draw an arrow from the **issuer** to the **designated recipient**; after the arrow comes a separate decision about the **protected resource**. Token verification answers "do we trust this credential and was it sent to the right recipient?"; authorization answers "what can this principal do with which data, in which tenant?". Only when both layers are right are trust boundaries upheld.