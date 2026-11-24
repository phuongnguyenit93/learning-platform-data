# Limiting Allowed Issuers and Recipient Applications in Federation

**Module:** Spring Security – federation  
**Context:** Trust boundary

## 1. Learning Objectives

In federated login (federated identity/SSO), an application typically receives an authentication result created by another system, such as an OpenID Connect (OIDC) **ID Token** or a **SAML Assertion**. To trust that result safely, the application must explicitly determine:

1. **Who is allowed to issue it?** Trust only Identity Providers/OpenID Providers (IdPs/OPs) registered and approved by the organization.
2. **Who was the result issued for?** Only the application, client, or service that is the intended recipient may accept that result.
3. **What is the result used for?** An ID Token proves a login event to an OIDC client; an OAuth access token grants API access; a SAML Assertion is sent to the corresponding Service Provider (SP).
4. **Is it still valid and matched to the transaction?** Verify signature, timestamps, anti-replay/mix-up parameters, session bindings, and access control policy.

The two central checks are **issuer** and **audience/recipient**. Merely checking that a digital signature is "valid" is not enough: a token may genuinely be signed by a trusted IdP yet issued for **another application**.

## 2. Visualizing the Trust Boundary

Suppose a company deploys:

- **OP/Authorization Server:** https://login.example.org/realms/company
- **Web application A:** client_id **staff-portal**, requiring OIDC for employee sign-in.
- **Web application B:** client_id **vendor-portal**, intended for suppliers.
- **Reporting API:** resource identifier/audience **urn:reports-api**.
- **Test IdP:** https://test-login.example.org/realms/company, not permitted for production.

Valid boundary:

~~~text
[User]
     |
     | Sign in
     v
[Production OP: login.example.org/realms/company]
     | ID Token: iss=Production OP, aud=staff-portal
     +----------------------------------------------> [staff-portal]
     |                                                       |
     |  Access Token: iss=Production OP, aud=urn:reports-api | call API
     +-------------------------------------------------------v
                                                     [reports-api]
~~~

**staff-portal** must not accept an ID token intended for **vendor-portal**. **reports-api** must not accept an ID token intended for **staff-portal** in place of an API access token. Neither may trust tokens issued by **test-login** merely because the domain name or keys look similar.

One issuer can serve multiple applications; one application can also support multiple issuers. **Each trust relationship must be independently approved and verified**; never assume that "same SSO system" means any token can be accepted everywhere.

## 3. What Is the Issuer and Why Must It Be Restricted?

In OIDC/JWT, the **iss** claim represents the identifier of the token issuer, typically an HTTPS URL. For example:

~~~json
{
  "iss": "https://login.example.org/realms/company",
  "sub": "employee-847",
  "aud": "staff-portal",
  "exp": 1794100000,
  "iat": 1794096400
}
~~~

This is an **illustrative payload**, not a real token, and proves nothing without signature verification. The timestamps are for explanation only.

An application trusting tokens must:

1. Configure the issuer **accurately and completely**, including the tenant/realm path. Compare the issuer by the exact identifier published by the provider; do not use rules like "contains string", "same domain suffix", or "same organization".
2. Fetch discovery metadata and JWKS public keys from the **registered issuer** over a trusted channel; never extract an arbitrary server URL from an unverified payload/header and connect to it automatically.
3. Verify the signature using a key bound to the issuer and an approved algorithm; check expiration, not-before, and required claims.
4. Compare **iss** in the token against the issuer configured for the trust relationship being processed.
5. Maintain an issuer lifecycle governance policy: who approves new connections, which tenants are allowed, how keys/metadata are rotated, and how trust is revoked.

For example, **https://login.example.org/realms/company** and **https://login.example.org/realms/partner** may reside on the same server yet are **two distinct issuers**. If the system only allows company employees to sign in, tokens from the partner realm must be rejected unless a separate federation policy permits them.

**JWKS is not a list of allowed issuers.** JWKS returns keys for signature verification; the decision to trust an issuer must exist before trusting any key. Headers such as **kid** only help select the appropriate key; they do not allow the client to pick an issuer dynamically or fetch keys from arbitrary URLs like **jku/x5u**.

## 4. What Is Audience/Recipient and Why Does It Matter?

**aud** (audience) describes the intended recipient of a token. The recipient must verify that **it is actually listed in the audience**, not merely that the token was issued by a trusted issuer.

Interpretation depends on token type:

| Credential Type | Issuer | Authorized Recipient | Primary Checks |
| --- | --- | --- | --- |
| **OIDC ID Token** | OpenID Provider | **OIDC client/Relying Party (RP)** | **iss** matches trusted OP, **aud** includes RP's **client_id** |
| **OAuth 2.0 JWT access token** | Authorization Server | **Resource Server/API** | **iss** matches trusted AS, **aud** includes expected API identifier; check permissions/scopes |
| **OAuth 2.0 opaque access token** | Authorization Server | Resource Server with introspection relationship | API verifies/introspects status and intended target per AS/API contract; cannot read JWT claims directly |
| **SAML Assertion** | SAML IdP | **Service Provider (SP)** | Signature, **Issuer**, **AudienceRestriction**, **Recipient/Destination**, and related conditions |

The two **aud** values for the two purposes typically differ:

~~~json
{
  "token_kind": "ID Token (external descriptive label)",
  "iss": "https://login.example.org/realms/company",
  "sub": "employee-847",
  "aud": "staff-portal"
}
~~~

~~~json
{
  "token_kind": "JWT access token (external descriptive label)",
  "iss": "https://login.example.org/realms/company",
  "sub": "employee-847",
  "aud": ["urn:reports-api"],
  "scope": "reports.read"
}
~~~

**token_kind** in the two blocks above is only an explanatory label added by this document, **not a standard default OIDC/OAuth claim**. These JSON snippets also omit fields and the signature portion required in real tokens.

Consequences:

- An ID token with **aud=staff-portal** is accepted by the web client to prove identity; the **reports-api** API must reject it if sent as a Bearer access token.
- An access token with **aud=urn:reports-api** is not proof of OIDC login for **staff-portal**, even when issued by the same OP.
- An access token with **aud=urn:billing-api** must not be used to call **reports-api**, even if it carries a scope that looks like **reports.read**.
- Checking **scope/roles** comes **after** confirming the token has the right issuer and audience; scopes cannot fix a wrong audience.

In OIDC, an ID token's **aud** may be a single string or a list. The RP must verify the list contains its own **client_id**; when additional audiences are present, trust requirements for those audiences must also be applied. Do not compare using substring matching.

## 5. Distinguishing iss, aud, azp, client_id, sub, and Other URLs

| Field | Role | What Not to Confuse It With |
| --- | --- | --- |
| **iss** | "Who issued this token?" | Not the browser domain or the user's email |
| **aud** | "Which recipient was this token issued for?" | Not a list of roles or permissions |
| **azp** in OIDC ID token | "Authorized party"; used in cases specified by OIDC/extensions, typically relating to the authorized client | Does not replace mandatory **aud** verification |
| **client_id** | Application ID registered at the AS/OP; JWT access tokens under RFC 9068 also include a **client_id** claim | Not synonymous with the access token's audience by default |
| **sub** | Subject identifier scoped to the issuer | Not a global ID across all tenants; not an email by default |
| **redirect_uri** | Client endpoint receiving the authorization code response | Does not replace **aud**; redirect URIs must be registered/checked separately |
| **scope** | Permissions requested by/granted to the client for an API | Does not prove identity under OIDC |
| **kid** | Hint to select a verification key from a trusted key set | Does not permit choosing an issuer dynamically or bypassing signature verification |

### When to Check azp?

For an **OIDC ID token**, the client checks that the audience contains its own client_id. If the ID token includes **azp**, apply the corresponding OIDC/extension rules; in the common case, the client verifies **azp** matches its own client_id. With multiple audiences, both the trusted parties and the meaning of azp must be evaluated—never accept unconditionally.

**Do not equate azp with client_id across all access token types.** Some IdPs place an **azp** claim in access tokens, but this is not a universal OAuth 2.0 structure. If an API must restrict **which applications are allowed to call it**, require a token profile and client-identifier claim standardized/committed by the AS itself (such as **client_id** per RFC 9068); verify them after the token is verified, combined with scope and subject policies.

### When to Use (iss, sub)?

The user account linking key should rely on the **(issuer, subject) pair**. Two different issuers may issue the same **sub** while referring to two different people. Changing issuers or changing tenant mapping is a security/data event that must be handled explicitly, never merged automatically by **sub** or email.

## 6. Flow for Receiving an ID Token from an Allowed OP

Suppose RP **staff-portal** only accepts sign-in from **https://login.example.org/realms/company**:

1. The administrator registers the RP at the OP: **client_id=staff-portal**, exact redirect URI, and client authentication method if it is a confidential client; declare appropriate scopes.
2. The RP configures the **fixed approved provider/issuer** and uses this issuer's metadata to locate the authorization endpoint, token endpoint, and JWKS.
3. The user accesses the login function. The RP sends an authorization request with **openid**, Authorization Code Flow, **state**, PKCE, and nonce when required; stores the issuer and request context.
4. The RP receives the callback, matches it to the initiated request (preventing CSRF and mix-up), and exchanges the code with the **right issuer's token endpoint**.
5. The RP obtains the ID token and verifies at minimum: approved signature/algorithm, **iss**, **aud containing client_id=staff-portal**, **exp** expiration, **iat/nbf** conditions if applicable, **nonce if sent**, and **azp** per relevant OIDC rules.
6. The RP creates an application session only after the token passes verification; internal user identification is based on **(iss, sub)**.
7. The RP enforces separate business authorization checks. **User authentication does not automatically grant all permissions**.

**Fail-closed principle:** if issuer, signature, audience, callback, or critical conditions cannot be verified, abort sign-in; never "temporarily skip checks" just to preserve the SSO experience.

### Two Allowed OPs

If the RP supports both **company** and **partner**, two approved **ClientRegistration/provider** entries must be configured. Whichever provider a request started with must be matched against that provider's response. When a client interacts with multiple ASes, protect against **authorization server mix-up** (for example, issuer in the response per RFC 9207 or standardized equivalents), preventing use of another provider's token endpoint/keys.

Relying solely on an **@example.org** email domain to automatically trust a new issuer URL is **unsafe**. An email address or tenant claim read from an unverified token can only serve as a **hint to select a configuration within the allowlist**, never as evidence to expand the allowlist.

## 7. Flow for an API Receiving an Access Token with the Right Audience

Suppose **reports-api** receives a Bearer request with a token issued by the production issuer:

1. Determine the **allowed issuers** for the API from a fixed configuration/policy set.
2. For JWTs, select the validator/keys bound to the trusted issuer, and verify the signature and algorithm.
3. Compare **iss** exactly and check **exp/nbf** within reasonable clock skew limits.
4. Verify **aud** contains **urn:reports-api**. Tokens whose audience is for another application must be rejected.
5. If the API requires a JWT access token profile such as RFC 9068, additionally verify the token type **typ=at+jwt** or **application/at+jwt**, along with mandatory profile claims; never assume every JWT is an access token.
6. Check **scope/permission** for the endpoint (e.g., **reports.read**) and the subject's internal/tenant permissions. If only specific clients may call the API, verify the client identity from an issuer-defined claim and allow policy.
7. Only after all conditions pass does the API process the request.

If the token is **opaque**, the resource server cannot verify a JWT signature and claims as above; use **token introspection** or an AS-published mechanism, then enforce equivalent audience/permission checks based on the information returned by the AS. Never attempt to decode an opaque string as a JWT.

**Note on OAuth:** an access token may represent a user or a machine client (e.g., **client_credentials**). Having a valid token does not guarantee a user signed in interactively. If business logic requires an "authenticated employee", design requirements around subject, grant/auth context, and appropriate controls; do not infer it solely from scope.

## 8. Implementation with Spring Security 6.x and Spring Boot 3.x (Java 17+)

This example illustrates a Spring MVC application acting both as an **OIDC Relying Party** for **/me** and as an **OAuth 2.0 Resource Server** for **/api/reports**. Both flows use the same production issuer yet **verify different audiences**.

This code can be placed into a **Spring Boot 3.x, Java 17+ Maven project**. To run in practice, the organization needs an OP with a valid issuer/discovery, a registered **staff-portal** client, an **urn:reports-api** audience configured, access tokens issued with the right scope, and environment variables supplied. The **example.org** URL is an illustrative placeholder, not a real login service.

### 8.1. Maven Dependencies

Add the following dependencies to **pom.xml** of a Spring Boot project using the appropriate BOM/parent:

~~~xml
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
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 8.2. application.yml – Trust Only Approved Issuers

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/company
          audiences:
            - urn:reports-api
~~~

Meaning:

- **client.provider.company.issuer-uri** restricts the OP trusted by the OIDC client. From the issuer, Spring fetches metadata to execute login and verify ID tokens intended for the registered **client_id**.
- **resourceserver.jwt.issuer-uri** lets the API verify the **iss** of JWT access tokens and locate signing keys per issuer configuration.
- **resourceserver.jwt.audiences** verifies that the JWT's **aud** contains **urn:reports-api**, preventing acceptance of tokens belonging to other clients/APIs.
- **client-id** must match the client registered at the OP. Use environment variables or a secret manager only for the client secret; never put real secrets in source control.
- Register the exact redirect URI at the OP; by default for registrationId **staff** this is **{baseUrl}/login/oauth2/code/staff**. Never configure wildcard redirect URIs.
- If an issuer has multiple tenants/realms, configure the exact issuer of the permitted tenant; do not substitute a root issuer or similar-looking hostname.

### 8.3. Two Filter Chains Separating Web App and API

**SecurityConfig.java** – in package **com.example.federation**:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_reports.read"))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

- **/api/** is a Bearer-token API, authorized by the **SCOPE_reports.read** authority (Spring typically maps OAuth scopes to authorities prefixed with **SCOPE_**).
- The **/me** page goes through OIDC login, receiving authenticated user details. Two filter chains separate credential acceptance mechanisms.
- Disable CSRF only for stateless Bearer-authenticated API endpoints under this design; the web login portion keeps default CSRF protection.
- Having multiple chains does not create additional trusted issuers. Both chains must still apply the configured issuer and audience policies.

### 8.4. Controller Observing Verified Identity

**DemoController.java** – same package:

~~~java
package com.example.federation;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getSubject()
        );
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(@AuthenticationPrincipal Jwt token) {
        return Map.of(
            "issuer", token.getClaimAsString("iss"),
            "audience", String.join(",", token.getAudience()),
            "subject", String.valueOf(token.getSubject())
        );
    }
}
~~~

Returned values depend on tokens issued by the actual OP; this document does not assume a fixed subject, JWT, or JSON output. In production, avoid exposing unnecessary claims and apply data protection policies.

**Run:** place these classes in a Spring Boot application with **@SpringBootApplication**, configure Maven parent/BOM, a real issuer, and **OIDC_CLIENT_ID/OIDC_CLIENT_SECRET** variables; run **mvn spring-boot:run**. The manual sign-in initiation URL is **/oauth2/authorization/staff**. Accessing **/me** while unauthenticated triggers the OIDC login flow. If the illustrative issuer has not been replaced with a real IdP, the application cannot complete login or resource-server discovery.

**Expected API test behavior** (with a real configured IdP):

| Request to /api/reports | Expected Outcome |
| --- | --- |
| No Bearer token | **401 Unauthorized** |
| Access token with wrong issuer, wrong audience, expired, or bad signature | **401 Unauthorized** |
| Valid access token with right issuer/audience but missing **reports.read** scope | **403 Forbidden** |
| Valid access token with right issuer/audience and **reports.read** scope | **200 OK**, controller returns sample metadata |

Status codes reflect typical behavior under the configuration above; response body/header details may depend on the Spring Security version and project error handling.

### 8.5. If Only a Specific Group of Clients May Call the API

Checking **issuer + audience** identifies the issuer and the API receiving the token. However, the same API may serve multiple clients. If business rules specify that only **staff-portal** and one batch client can call an endpoint, add a **client-identity policy** after the token is verified.

For instance, if the AS commits to issuing **RFC 9068 JWT access tokens** containing a **client_id** claim, the resource server can write a custom validator accepting only client IDs on an allowlist. A condensed example for **the staff-portal client only**:

~~~java
// Method example, placed in the same @Configuration class.
// Requires imports org.springframework.security.oauth2.jwt.*,
// org.springframework.security.oauth2.core.*,
// org.springframework.security.oauth2.core.validator.*.
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://login.example.org/realms/company";
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> allowedAudience = jwt ->
        jwt.getAudience().contains("urn:reports-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> allowedClient = jwt ->
        "staff-portal".equals(jwt.getClaimAsString("client_id"))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Client is not allowed", null));

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        allowedAudience,
        allowedClient
    ));
    return decoder;
}
~~~

**Safe usage:** this is an **additional example to replace the default JwtDecoder configuration**, not automatically merged into the Section 8.3 code. Add concrete imports to place it in a project configuration class. This bean must continue verifying **issuer, timestamps, and audience**; when implementing per **RFC 9068**, also verify **token type/typ** and profile requirements—do not assume this condensed snippet covers every policy. Specifically, require **client_id** only if real tokens carry that claim guaranteed by the AS; for OPs using another claim, confirm semantics in OP documentation before writing a validator. If policy allows multiple clients, replace the single comparison with an allowlist.

Never use **sub** or **email** to infer the calling client application. Likewise, never use an unverified client claim to dynamically accept a new issuer.

## 9. SAML Federation: Similar Boundaries, Different Field Names

In SAML 2.0 SSO, the SP receives a **SAML Response/Assertion** from the IdP. Corresponding concepts:

- **Issuer:** the EntityID identifier of the IdP with an established trust relationship; verify signature using the corresponding trusted certificate/metadata.
- **AudienceRestriction:** restricts the assertion to the matching **SP entityID**, preventing reuse by another SP.
- **SubjectConfirmationData.Recipient:** restricts the endpoint/ACS allowed to receive the bearer assertion.
- **Destination, InResponseTo, NotBefore, NotOnOrAfter:** bind the response to the endpoint, login request, and validity window per profile/flow.
- **Replay prevention and correlation:** prevents an assertion from being replayed or a response from being attached to the wrong request; verify profile conditions.

For example, if an IdP issues an assertion for SP **https://portal.example.org/saml/metadata**, SP **https://admin.example.org/saml/metadata** cannot accept it in its place merely because both use the same IdP verification certificate.

**Do not mechanically apply OIDC claim names to SAML XML.** Checking issuer, audience, and recipient is a shared trust boundary concept, while fields, signature profiles, response rules, and verification libraries differ. With Spring Security SAML2 Service Provider, configure a **relying party registration** containing the asserting party/metadata and verify SAML via the corresponding module—never use **oauth2Login()** to handle SAML.

## 10. Risks of Misconfiguration

### 10.1. Trusting Any Issuer / Fetching JWKS from the Token

**Wrong:** The API reads an unverified **iss** claim, constructs an arbitrary discovery/JWKS URL, and trusts signatures from that URL. An attacker can stand up an issuer and self-sign a "valid" token with their own key, or even trigger SSRF when the API calls internal hosts.

**Right:** Select issuers only from a trusted allowlist, with metadata/JWKS bound to the approved issuer; prevent SSRF and maintain an appropriate algorithm/signature policy.

### 10.2. Checking Only Signature and exp, Skipping aud

**Wrong:** staff-portal accepts vendor-portal's ID token, or reports-api accepts an access token issued for billing-api because both were signed by the company OP.

**Right:** Every RP/API checks its own dedicated audience, as well as the proper purpose/token type.

### 10.3. Token Substitution: Using an ID Token as an Access Token

**Wrong:** The API accepts a Bearer ID token with **aud=staff-portal**. In some architectures, this can lead to privilege exposure because the token was issued for the login flow, not for the API.

**Right:** The API accepts only access tokens with the right profile and API audience. When using RFC 9068 JWT access tokens, require **typ=at+jwt** or the standard equivalent when configuring profile validators; verification rules for ID vs. access tokens must be kept separate.

### 10.4. Tenant Confusion Due to Identical Email or sub

**Wrong:** Two tenants have **sub=123** or the same email and are treated as the same user.

**Right:** Identity and permissions are bound to **(iss, sub)**, an approved tenant, and an explicit mapping; validate tenant/organization claims per policy after verification.

### 10.5. Overly Broad Clients or Redirect URIs

**Wrong:** Any client/redirect URI on the same domain can receive codes/tokens; a production client uses wildcard redirect URIs or shared secrets.

**Right:** Register separate clients, exact redirect URIs, Authorization Code + PKCE, protect state/nonce and confidential client secrets; grant minimal scopes and audiences.

### 10.6. Mix-Up Errors with Multiple IdPs

**Wrong:** The RP initiates login at OP A yet receives the callback and processes it using OP B's token endpoint/keys.

**Right:** Bind the request to the chosen issuer; verify the authorization response issuer per RFC 9207 or equivalent safeguards; reject cross-flow responses.

### 10.7. Improper Token Formats or Algorithms

**Wrong:** Treating any three-segment Base64URL string as a valid JWT; accepting **alg=none**; using out-of-policy algorithms/keys or merely decoding the payload.

**Right:** Verify the real signature, allowed algorithms, and keys belonging to a trusted issuer; build separate validation rules for each JWT type and require mandatory contents.

### 10.8. Treating Login as Default Access to Everything

**Wrong:** Anyone authenticated by the IdP automatically receives admin permissions across all applications.

**Right:** Identity from a valid issuer/audience is only the authentication step. Authorization based on roles, scopes, data permissions, tenant, and business conditions is checked at each application/API.

## 11. Trust Governance Approach in a Multi-Application System

A configuration policy should explicitly state for each consumer:

| Consumer | Trusted Issuer | Accepted Audience | Credential Type | Additional Permissions/Conditions |
| --- | --- | --- | --- | --- |
| **staff-portal** | issuer **company** | OIDC ID token with **aud=staff-portal** | OIDC ID token | nonce, azp if applicable, (iss, sub) link |
| **vendor-portal** | approved **partner** issuer | OIDC ID token with **aud=vendor-portal** | OIDC ID token | partner tenant, vendor role |
| **reports-api** | issuer **company** | access token with **aud=urn:reports-api** | Appropriate JWT/opaque access token | **reports.read**, client policy if any |

When adding an issuer, the process should include: verifying the organization operating the IdP; confirming the exact issuer and metadata; approving client registration/redirect URIs; ID/access token rules; testing wrong-issuer/wrong-audience tokens; tenant limits; and a trust revocation plan. Never grant API access or perform user-linking based solely on a shared email field.

**Key rotation:** signing keys may rotate within the same issuer. The application can refresh JWKS per library mechanisms and appropriate caching, but **key changes must never expand the set of trusted issuers**. When ceasing to trust an OP, remove/block its trust configuration per operational procedures and handle active sessions/tokens under a separate policy.

**Multiple issuers for an API:** select the authentication manager/decoder by issuer **within an allowlist**, then check the audience and policy corresponding to each issuer. An unverified JWT's `iss` value can only be a **selector into the allowlist**; it must never be turned into an arbitrary discovery URL. An API permitted to accept multiple issuers **does not mean** accepting all tenants or identical claim mappings.

## 12. Accept/Reject Classification Exercises

Assume **staff-portal** trusts only issuer **company** and has client_id **staff-portal**; **reports-api** trusts only issuer **company** and requires audience **urn:reports-api** along with scope **reports.read**.

| Scenario | Decision | Reason |
| --- | --- | --- |
| ID token **iss=company**, **aud=staff-portal**, valid signature/time/nonce | RP **may accept** | Right issuer and audience; still requires all OIDC conditions |
| ID token **iss=company**, **aud=vendor-portal** | RP **rejects** | Wrong audience despite valid signature |
| ID token **iss=test-login**, **aud=staff-portal** | RP **rejects** | Unapproved issuer |
| ID token **iss=company**, **aud=staff-portal**, invalid signature | RP **rejects** | Cannot verify true issuing source |
| Access token **iss=company**, **aud=urn:reports-api**, has **reports.read** and valid | API **may accept** | Right issuer, audience, and permission; subject to other policies |
| Access token **iss=company**, **aud=urn:billing-api**, has **reports.read** | API **rejects** | Scope does not substitute for audience |
| Access token **iss=company**, **aud=urn:reports-api**, missing **reports.read** | API **denies permission** | Authentication may be valid, but authorization is not met |
| ID token **aud=staff-portal** sent as Bearer to reports-api | API **rejects** | Wrong token type and audience |
| Access token signed OK but past **exp** | API **rejects** | Expired |
| ID token with **sub=123** from partner issuer | Do not auto-merge with company user having **sub=123** | Subject is only stable within the issuer's scope |

Note the phrase **"may accept"** because the table does not list every condition: authentication policy, scope, client, token type, key, request binding, and tenant must still be satisfied.

### Check Questions

**Question 1:** If a system shares a common JWKS, can every application in the company accept the same ID token?  
**Answer:** No. Each RP must still verify **iss**, **aud containing its own client_id**, signature, and other validation conditions. Sharing an issuing key does not make client B a valid audience for a token intended for client A.

**Question 2:** Is configuring only **issuer-uri** on an API in Spring Security enough to prevent tokens intended for another API?  
**Answer:** No. You must check the API's specific audience, such as the **resourceserver.jwt.audiences** property, and permissions/scopes; if needed, also check token type and allowed clients.

**Question 3:** If an unverified JWT's **iss** claim specifies a new domain, should you fetch that domain's JWKS?  
**Answer:** No. You may only select an issuer already in the trusted allowlist; then use the metadata/keys bound to that issuer and verify the token.

**Question 4:** If a token has the right **aud**, can you skip signature verification because it was "sent to the right application"?  
**Answer:** No. Audience is just a claim that can be forged in an unverified token. Signature, issuer, timestamps, token type, and audience must all be verified.

**Question 5:** If an API is valid for multiple clients, is it always necessary to restrict which client may call it?  
**Answer:** It depends on business requirements. **aud** ensures the token targets the API; if policy permits only a specific group of applications to call it, additional client identity (and scope/permission) checks must be enforced based on an issuer-guaranteed token profile.

## 13. Pre-Production Checklist for Federation

- [ ] Only issuers/OPs/IdPs on the approved allowlist are enabled; use **tenant-exact** URLs/EntityIDs.
- [ ] Metadata, JWKS/certificates, and verification algorithms are bound to the right trusted issuer; no dynamic trust from unverified tokens.
- [ ] OIDC RP verifies ID tokens have **aud matching client_id**, and checks **iss, exp, signature, nonce/azp** per OIDC rules.
- [ ] OAuth resource server accepts only access tokens matching **issuer, API audience, timestamps, signature/introspection**, and deployed token profile.
- [ ] Separate rules for ID tokens, access tokens, and SAML Assertions; no token substitution.
- [ ] Enforce **state/PKCE**, exact redirect URI, multi-IdP mix-up protection, and anti-replay.
- [ ] Identify users by **(iss, sub)** and bind to authorized tenants/units.
- [ ] API/application permissions (scopes, roles, permissions, client allowlists) are checked separately after authentication.
- [ ] Negative scenarios tested: wrong issuer, wrong audience, wrong token type, bad signature, expired, missing permissions, unauthorized tenant.
- [ ] Secrets and tokens are protected; key rotation, trust link revocation, and appropriate logout/session handling are in place.

**Rule of thumb:** **Issuer answers "Do I trust who issued this credential?"; audience answers "Was this credential issued specifically for me?"; permission checks answer "Is this subject/client allowed to perform the requested action?". All three layers must pass before allowing an operation.**

## 14. Official References

- [OpenID Connect Core 1.0 – ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation): validation rules for **iss, aud, azp, signature, exp, nonce**.
- [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): verifying issuer, audience, **typ=at+jwt**, and **client_id** of profiled JWT access tokens.
- [RFC 8725 – JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): per-JWT-type validation, preventing cross-JWT confusion.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect URIs, PKCE, CSRF, and mix-up protection.
- [RFC 9207 – Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): verifying issuer in authorization responses when a client supports multiple ASes.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): declaring OIDC client registrations and issuers.
- [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer-uri, audiences, decoders, token validators.
- [Spring Security – SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): relying party and SAML SP trust.
