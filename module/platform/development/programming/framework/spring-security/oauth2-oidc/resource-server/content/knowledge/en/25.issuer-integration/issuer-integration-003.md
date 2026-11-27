# User-Facing Clients and Machine Clients Can Receive Different Claims

In a **Spring Security OAuth 2.0/OIDC Resource Server**, the same Authorization Server (AS) can issue **access tokens with different claim structures** for two groups of applications:

1. **User-facing clients**: web applications, BFFs, mobile apps, or SPAs using OAuth 2.0 Authorization Code + PKCE to call APIs under permissions granted in relation to a user.
2. **Machine clients**: backend jobs, batch processors, cron workers, or other services using `client_credentials` to call APIs under the application's own permissions, **without a direct end-user in the token issuance flow**.

A user-facing token may contain the user's `sub`, profile attributes, and scopes like `orders.read`. A machine-to-machine token may contain `client_id`, a service application subject, and scopes like `orders.import`, while lacking `email`, `preferred_username`, or a real user profile.

> **Core point:** A Resource Server must never assume **every access token represents a human user** or **every token carries the same claims**. It must verify the token, understand the AS issuance contract, distinguish a user subject from an application identity, and enforce permissions based on the caller kind.

This lesson belongs to the **Issuer Integration** chapter: how to coordinate with the Authorization Server/Identity Provider so each OAuth client receives the right claims; how to configure Spring Security Resource Server to validate tokens, convert claims into principals/authorities, reject tokens used for the wrong purpose, and protect data by tenant/ownership. Code samples use Java 17+, Spring Boot, and **Spring Security Servlet/Spring MVC**; WebFlux has corresponding APIs, not copy-paste equivalents.

## 1. First, Distinguish Four Concepts

A common mistake is using *client*, *user*, *subject*, and *principal* interchangeably.

| Concept | Meaning | Example |
|---|---|---|
| **OAuth client** | Application registered with the AS, having a `client_id` | `storefront-web`, `inventory-sync` |
| **Resource owner/end-user** | Human subject in a human-authorized flow | User `person-42` |
| **Access token subject** | Entity represented by the `sub` claim per the AS token profile | `person-42` or `svc-inventory` |
| **Authenticated principal at the API** | Identity Spring Security creates **after the token is verified** | `JwtAuthenticationToken` or `BearerTokenAuthentication` |
| **Scope** | OAuth authorization scope granted by the AS | `orders.read`, `orders.import` |
| **Application role/permission** | Business permission managed by an authoritative system | `ORDER_APPROVER`, `orders.export` |
| **Grant type** | Mechanism the client used to obtain the access token | `authorization_code`, `client_credentials` |
| **Token type/profile** | Format and purpose of the credential | JWT access token, opaque access token, OIDC ID token |

**A user-facing OAuth client is not the user itself.** Thousands of people can sign in through the same `client_id=storefront-web`; per-user authorization relies on the subject and appropriate entitlements, not the client ID alone.

**A machine client is not an administrator by default.** Holding a client secret or private key only lets a backend authenticate to the AS to request tokens under granted grants/scopes. The API must still restrict the token's permissions.

### 1.1. Client Type Alone Does Not Tell Each Token's Grant Type

Registered clients can be public clients (SPA/mobile) or confidential clients (backend). A confidential web app may use Authorization Code for users **and** some systems permit the same client to use another grant depending on configuration.

Therefore:

~~~text
client_id=orders-backend
```

is **not sufficient** to infer whether a token represents an end-user or a backend service. You need a token-issuance contract stating how to recognize token purpose/grant and how the AS sets claims. Never rely solely on `client_id` when a client can receive both user tokens and service tokens.

## 2. Two Distinct OAuth 2.0 Flows

### 2.1. Authorization Code + PKCE: A User Participates

~~~text
User
   |
   v
Web/Mobile/SPA OAuth Client
   |
   | Authorization request, PKCE, state
   v
Authorization Server / OIDC Provider
   |
   | Authenticate user, consent/policy if needed
   |
   v
Authorization Code
   |
   | Client exchanges code with code_verifier
   v
Access Token for Orders API
   |
   | Authorization: Bearer <access-token>
   v
Spring Security Resource Server
   |
   | Verify JWT or introspect opaque token
   v
Authenticated USER principal + authorities
   |
   v
Check scope + tenant + order ownership
~~~

With OIDC login, the client typically also receives an **ID token** conveying user authentication results. However, the **Orders Resource Server** must consume an **access token with the right audience**, **not** accept an OIDC ID token as an API credential merely because it is also a JWT.

In a user-involved flow, the access token's `sub` usually represents the user per the AS contract. `client_id` still indicates which application requested/received the token.

### 2.2. Client Credentials: No User Logging In During the Grant

~~~text
Scheduled Import Worker
   |
   | Authenticates itself (client secret / private_key_jwt / mTLS ...)
   | grant_type=client_credentials
   v
Authorization Server Token Endpoint
   |
   | Checks client identity, allowed scopes/audience/policy
   v
Access Token representing the client's application/capabilities
   |
   | Authorization: Bearer <access-token>
   v
Spring Security Resource Server
   |
   | Verify JWT or introspect opaque token
   v
Authenticated SERVICE principal + authorities
   |
   v
Check import scope + tenant/service ACL
~~~

There is **no end-user login step** within the `client_credentials` grant itself. RFC 6749 describes the client as acting on its own behalf, or under an authorization pre-established with the AS.

This **does not prohibit** an AS from implementing an internal service-account identity. However, a service account having a `sub` does not mean a human is sitting at a screen or consented to private user data access.

### 2.3. Two Illustrative HTTP Token Requests

For a user-facing client, the OAuth 2.0 Authorization Code flow (after redirect/code issuance) includes a code exchange step:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
client_id=storefront-web&
code_verifier=PKCE_VERIFIER
~~~

This is a conceptual example. Client authentication depends on public vs. confidential client; a confidential BFF may also need to authenticate as required by the AS. Never put client secrets into SPAs or mobile apps.

For a machine client:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-client-credentials>

grant_type=client_credentials&
scope=orders.import&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

`resource` here illustrates RFC 8707 Resource Indicators; the AS supports it only if configured. Client authentication may be Basic, `private_key_jwt`, or mTLS depending on the AS; no single mechanism is mandated across all deployments.

**Purpose:** the AS must establish **which client**, **which grant**, **which resource**, and **which permissions** before issuing a token. The Resource Server must never guess these details from the request URL or application name.

## 3. Two Valid Access Tokens Can Look Very Different

Suppose the AS and Orders API agree on a **custom claim**:

~~~text
caller_kind = "user" | "service"
```

This claim is **not a required field in OAuth 2.0 or RFC 9068**; it is a custom contract that must be set by the AS from a trusted grant/client/token policy, **never** read from user-editable profile attributes.

### 3.1. Access Token When a User Calls the API

Example JWT header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-key-1"
}
~~~

Example payload:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "person-42",
  "aud": ["orders-api"],
  "client_id": "storefront-web",
  "caller_kind": "user",
  "scope": "orders.read orders.create",
  "preferred_username": "mai",
  "email": "mai@example.test",
  "tenant_id": "tenant-a",
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

This is only a **sample payload**; not every AS puts profile claims into **access tokens**. `preferred_username`, `email`, `tenant_id`, and `caller_kind` here are attributes that may depend on client scopes, mappers, and AS policy.

Even when `email` is present, it does not prove the address is verified or that the user is an admin. Depending on the OIDC/AS contract, check `email_verified` separately if email verification truly matters, and **never use `email_verified` to grant business permissions**.

### 3.2. Access Token When a Machine Calls the API

The header may still be:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-key-1"
}
~~~

Payload:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "svc:inventory-sync",
  "aud": ["orders-api"],
  "client_id": "inventory-sync",
  "caller_kind": "service",
  "scope": "orders.read orders.import",
  "tenant_id": "tenant-a",
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

This token has no end-user `email` or `preferred_username`. That is **normal** for a token representing an application.

Some ASs use `sub=inventory-sync`, some use a service-account ID for `sub`, and some use a custom-profile subject. **Never assume `sub == client_id` across every implementation.** RFC 9068 recommends that `sub` for tokens without a resource owner (like `client_credentials`) match the client application identifier as managed by the AS, though a given AS may follow a different profile.

### 3.3. Claims Comparison Table

| Claim | User Token | Machine Token | What the Resource Server Must Know |
|---|---|---|---|
| `iss` | AS issuer | AS issuer | Must belong to the trusted issuers set |
| `sub` | Usually end-user subject | Usually app/service subject | Never assume it is always a human |
| `client_id` | User-facing OAuth client | OAuth machine client | Does not indicate grant type by itself |
| `aud` | Orders API | Orders API | **Both** must match the intended resource |
| `scope`/`scp` | Scopes granted per user/client policy | Scopes granted per client policy | Never backfill missing scopes |
| `caller_kind` (custom) | `user` | `service` | Trust only if managed by AS per contract |
| `email` | May or may not be present | Usually no end-user email | Never use as a role |
| `preferred_username` | May be present | May be absent or a service-account name | Never use as identity proof |
| `groups`/`roles` | Depends on config/entitlement | May be different application roles | Requires mapper/allowlist and authoritative source |
| `tenant_id` (custom) | Tenant related to user | Tenant authorized for client | Does not prove access to every object |
| `azp` | Some profiles, especially OIDC ID tokens | Not universal | Do not blindly substitute for `client_id` |
| `gty`/`grant_type` | May be a vendor extension | May be a vendor extension | **Not guaranteed to be present in every access token** |
| `act` | May appear in token-exchange delegation | May appear when a service acts on a user's behalf | Interpret only per RFC 8693/AS contract |
| `exp`/`nbf`/`iat` | Token timestamps | Token timestamps | Validate identically per token profile |

Important: **The OAuth grant type from the token request does not have to be embedded in the JWT access token.** If the application needs a caller-kind indicator, require the AS to emit a contract-defined claim bound to verified grant context, or design genuinely separate token profiles/clients.

## 4. `sub`, `client_id`, and Principal Are Not the Same Field

There are three common identity mistakes.

### 4.1. Using `client_id` to Identify a User

Suppose:

~~~text
client_id = storefront-web
sub       = person-42
```

Another person also uses the same app:

~~~text
client_id = storefront-web
sub       = person-99
```

If order ownership is stored using `client_id`, every user on `storefront-web` gets collapsed into a single identity. **Never use `client_id` in place of the user subject.**

### 4.2. Using `sub` as a User Key Without Considering Caller Kind

Suppose a machine token has:

~~~text
sub       = svc:inventory-sync
client_id = inventory-sync
```

Spring Security JWT by default sets `Authentication#getName()` from `sub`. If a service queries `users.findById(authentication.getName())`, it can:

- Fail to find a user.
- Unintentionally create a "ghost user"/service account.
- Conflate human and machine permissions.
- Bypass "user must be owner" checks with a service account.

**Solution:** model `HumanCaller` and `ServiceCaller` separately, or use a domain identity with a verified `kind`.

### 4.3. Using `sub` While Ignoring the Issuer

~~~text
Issuer A: sub = person-42
Issuer B: sub = person-42
```

Those two subjects are not automatically the same person. With multiple issuers, the canonical external identity is usually **`(iss, sub)`**, or mapping that pair to an internal user ID via a trusted directory.

Machine tokens also need an issuer/client namespace. Never use bare `client_id` as a global key if the same client ID can exist across multiple AS deployments.

## 5. OAuth 2.0 Access Token Differs from OIDC ID Token

Carefully distinguish three token/document surfaces:

| Surface | Primary Consumer | Content/Meaning |
|---|---|---|
| **Access token** | Resource Server/API | Resource access authorization; `aud` and scopes |
| **OIDC ID token** | OIDC client/Relying Party | End-user authentication result, issuer/sub/client audience |
| **UserInfo response** | OIDC client holding a suitable access token | OIDC user profile claims |

Example OIDC ID token:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "person-42",
  "aud": "storefront-web",
  "name": "Mai",
  "email": "mai@example.test",
  "exp": 2000000300
}
~~~

Meanwhile, an access token for the API must carry `aud=orders-api` or a contract-compliant resource indicator.

**Never accept an ID token as a bearer credential for the Orders API** just because it has `sub`, `email`, and a valid signature. `openid profile email` are scopes/claims of the **OIDC identity flow**, not default permissions to read/write orders.

A machine using `client_credentials` has no logging-in end-user in the grant, so it **normally has no human OIDC ID token**. If an AS issues special token types in other flows, establish their purpose and profile explicitly; never infer them from JWT formatting alone.

## 6. Why Does an AS Issue Different Claims?

Many IdPs/Authorization Servers base claim publication policies on:

1. **Grant flow:** is a user authenticating or only client credentials?
2. **Registered OAuth client:** which scopes/audience/profile is the client granted?
3. **Consent and authorization:** what is the user or client permitted to access?
4. **Client scopes and protocol mappers:** which fields are placed into access tokens, ID tokens, and UserInfo?
5. **Resource/`audience`:** which claims does the target API require?
6. **Assigned roles/permissions:** user roles differ from service-account/application roles.
7. **Token lifetime and issuer policy:** environment, client assurance level, token type.
8. **Privacy/data minimization:** if an API does not need name/email, the AS may omit them.
9. **Tenant context:** a user or workload may be granted a specific tenant scope.
10. **Token format:** JWT access tokens carry claims in their payload; opaque tokens only expose information through the introspection contract.

### 6.1. AS Mappings Should Be Designed Around Token Purpose

Example of a sound policy:

~~~text
Client: storefront-web
Grant: authorization_code
User present: yes
Audience: orders-api
Claims in access token:
  iss, sub(user), aud, client_id, scope, caller_kind=user
  tenant_id if authorized
  optional profile claims only if needed

Client: inventory-sync
Grant: client_credentials
User present: no
Audience: orders-api
Claims in access token:
  iss, sub(service/application), aud, client_id, scope,
  caller_kind=service, tenant_id if authorized
  no end-user profile attributes
~~~

This table is an **illustrative contract**; there is no single standard configuration across Keycloak, Entra ID, Auth0, Okta, Spring Authorization Server, or other IdPs. Each issuer configures claim mappings differently.

### 6.2. Service Account Roles Differ from User Roles

Some IdPs have a **service account** concept linked to a machine OAuth client. Permissions granted to a service account may appear in `roles`, `realm_access`, `resource_access`, or another vendor-specific namespace.

Never read:

~~~json
{
  "roles": ["realm-admin"]
}
~~~

and turn it into `ROLE_ADMIN` on the Orders API unless it is truly an **authoritative role for this API** permitted by the contract. An IdP management role or another client's admin role does not equal permission to approve refunds.

### 6.3. `gty`/`grant_type` Claims Are Not Universal Standards

Some ASs embed the grant type or token purpose in the JWT, for example:

~~~json
{
  "gty": "client-credentials"
}
~~~

However, claim names and values can be **vendor-specific**. Never write security code assuming every OAuth 2.0 JWT contains `grant_type=client_credentials`. If classification is needed, define an AS-controlled claim or rely on a verified token profile.

## 7. Design the Claim Contract Before Writing Java Code

A Resource Server can require the AS to fulfill a contract:

| Requirement | User Token | Machine Token |
|---|---|---|
| Issuer | Same issuer or allowlist | Same issuer or allowlist |
| Audience | `orders-api` | `orders-api` |
| Token type | OAuth access token, not ID token | OAuth access token |
| `sub` | Stable user subject | Stable service/app subject per AS |
| `client_id` | One of the approved user-facing clients | One of the approved machine clients |
| `caller_kind` | `user` set by AS | `service` set by AS |
| Scopes | `orders.read`, `orders.create` per policy | `orders.import`, `orders.read` per policy |
| Optional profile claims | May be present | Not required; typically absent |
| Tenant claim | Only if AS is authoritative | Only if AS is authoritative |
| Missing required claim | **Reject** | **Reject** |
| Unknown role/permission | Do not map to privileges | Do not map to privileges |

**Crucially:** `caller_kind` must be derived by the AS from **verified grant/client authentication/token issuance context** that the client cannot alter. If a client can edit a custom user attribute `caller_kind=service`, that claim is not trustworthy for classification.

### 7.1. Maintain Authoritative Sources for Tenants and Roles

A user may belong to tenant A and tenant B; a machine client may only be permitted to import inventory for tenant A. `tenant_id` in an access token can be used if the AS authoritatively manages membership/delegation. If tenant permissions live in the Orders API database, the token claim is only an identifier input and must be checked against current ACLs.

### 7.2. Do Not Require Machine Tokens to Have an Email

Wrong:

~~~java
// WRONG: a valid machine token does not necessarily have an email.
String email = jwt.getClaimAsString("email");
if (email == null) {
    throw new BadCredentialsException("Missing email");
}
~~~

This can trigger mass 401 errors for service clients even when tokens have the right issuer and audience. **At the same time**, never fall back to a default admin role just because `email` is missing.

Instead, require the claims appropriate for the **verified caller kind**:

~~~text
User token -> requires human sub, caller_kind=user, valid user client
Machine token -> requires service identity, caller_kind=service, valid client_id
```

## 8. What Does Spring Security Resource Server Validate?

A JWT bearer request typically flows through:

~~~text
Authorization: Bearer <JWT>
            |
            v
BearerTokenAuthenticationFilter
            |
            v
JwtAuthenticationProvider
            |
            v
JwtDecoder
  - verify signature / public key
  - validate issuer
  - validate audience
  - validate exp, nbf
  - validate token profile/type as configured
            |
            v
JwtAuthenticationConverter
  - scopes -> SCOPE_*
  - custom caller-kind -> CALLER_USER / CALLER_SERVICE
            |
            v
JwtAuthenticationToken
            |
            v
SecurityContextHolder
            |
            v
HTTP + method + business authorization
~~~

By default, Spring Security typically:

- Verifies the JWT using the configured `JwtDecoder`.
- Maps `scope` or `scp` to `SCOPE_*` authorities.
- Sets `Authentication#getPrincipal()` to a `Jwt`.
- Sets `Authentication#getName()` to `sub` when present.

It **does not automatically understand** a custom `caller_kind` claim, classify human vs. service by email, or map arbitrary IdP `roles`/`groups` to authorities.

The customizations in the next example span three layers:

1. **`JwtDecoder` validators**: reject tokens violating issuer/audience/caller contracts.
2. **`JwtAuthenticationConverter`**: emit marker authority `CALLER_USER` or `CALLER_SERVICE` from the verified token and issuance contract.
3. **HTTP/service authorization**: authorize endpoints by scope and caller kind, then enforce tenant/ownership.

## 9. Configuring a JWT Resource Server for Both Caller Types

Assume the AS guarantees:

- Public issuer: `https://login.example.com/realms/orders`.
- Orders API audience is `orders-api`.
- Access token signatures use RS256 with an AS-managed JWK Set.
- JWT access tokens carry `sub`, `client_id`, `caller_kind`.
- `caller_kind=user` is issued only to approved user-facing clients.
- `caller_kind=service` is issued only to approved machine clients.
- Do not accept other token types by guessing.
- `caller_kind` and `client_id` are placed by the AS inside the **signed** token, never self-declared via request headers.

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

With Spring Boot starters, the required Resource Server and JOSE/JWT modules are managed by the BOM. Avoid unintentionally mixing Spring Security versions.

### 9.2. Config Values

~~~yaml
app:
  security:
    issuer: https://login.example.com/realms/orders
    jwk-set-uri: https://login.example.com/realms/orders/certs
    audience: orders-api
~~~

This is an **application-defined illustrative config namespace**, not Spring Boot auto-configuration properties.

### 9.3. Validator Dedicated to the Caller Contract

Create a validator that checks `caller_kind`, `client_id`, and `sub` on a JWT whose signature the decoder has already verified. This validator **must not replace** issuer, time, or audience validators.

~~~java
package com.example.orders.security;

import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class CallerContractValidator
        implements OAuth2TokenValidator<Jwt> {

    private static final Set<String> USER_CLIENTS =
        Set.of("storefront-web", "orders-mobile");

    private static final Set<String> SERVICE_CLIENTS =
        Set.of("inventory-sync", "fulfillment-worker");

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String kind = jwt.getClaimAsString("caller_kind");
        String clientId = jwt.getClaimAsString("client_id");
        String subject = jwt.getSubject();

        if (subject == null || subject.isBlank()
                || clientId == null || clientId.isBlank()) {
            return invalid();
        }

        boolean isApprovedUser =
            "user".equals(kind) && USER_CLIENTS.contains(clientId);

        boolean isApprovedService =
            "service".equals(kind)
                && SERVICE_CLIENTS.contains(clientId);

        if (!isApprovedUser && !isApprovedService) {
            return invalid();
        }

        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult invalid() {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Caller token contract is not satisfied",
                null
            )
        );
    }
}
~~~

**Important limitation:** The client ID allowlist is an **example policy** and is not by itself what verifies the grant. It works because the **AS contract asserts** `caller_kind` is bound to the real issuance flow. If a client is permitted to receive **both user tokens and service tokens**, or the AS cannot guarantee `caller_kind` trustworthiness, this validator alone is insufficient to prove caller kind; stricter profile/issuer policies are required.

### 9.4. Combining Issuer, Audience, Time, and Caller Validators

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator,
                new CallerContractValidator()
            )
        );

        return decoder;
    }
}
~~~

This preserves default issuer/time checks and adds audience and caller contract validation. If the actual profile requires **JWT access token type `at+jwt`** per RFC 9068, apply the **type/profile validator appropriate for your Spring Security version**; never replace all validations with a single `caller_kind` check.

**Specifically:** a matching `client_id` never makes a JWT with an invalid signature valid. `NimbusJwtDecoder`'s signature verification must succeed before any claim authorization is applied.

## 10. Mapping Scope and Caller Kind to GrantedAuthority

If a JWT contains:

~~~json
{
  "scope": "orders.read",
  "caller_kind": "user"
}
~~~

Spring Security creates `SCOPE_orders.read` by default, but not `CALLER_USER`. A converter can preserve scope authorities while adding an **application marker** from the verified contract.

### 10.1. Converter for a Verified JWT

~~~java
package com.example.orders.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class CallerAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final JwtGrantedAuthoritiesConverter scopeConverter =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<GrantedAuthority> authorities = new ArrayList<>();

        Collection<GrantedAuthority> scopes =
            scopeConverter.convert(jwt);

        if (scopes != null) {
            authorities.addAll(scopes);
        }

        String kind = jwt.getClaimAsString("caller_kind");

        if ("user".equals(kind)) {
            authorities.add(
                new SimpleGrantedAuthority("CALLER_USER"));
        } else if ("service".equals(kind)) {
            authorities.add(
                new SimpleGrantedAuthority("CALLER_SERVICE"));
        }

        return authorities;
    }
}
~~~

`CALLER_USER` and `CALLER_SERVICE` are **API-defined marker authorities**, not OAuth scopes and not built-in Spring Security roles.

**Do not add `SCOPE_orders.import` just because `caller_kind=service`.** Import permission must still be genuinely granted by the AS via `scope`/authoritative entitlement. Caller kind identifies the principal type, not business permissions.

### 10.2. Registering JwtAuthenticationConverter

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
public class JwtAuthenticationMappingConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(
            new CallerAuthoritiesConverter()
        );

        return converter;
    }
}
~~~

`scope` authorities are preserved via `JwtGrantedAuthoritiesConverter`. If an implementation replaces the list with **only `CALLER_USER`**, an API requiring `SCOPE_orders.read` will return 403 even when the AS actually granted read access.

### 10.3. Why Should the Converter Only Run After Validation?

A converter configured on the Resource Server receives a `Jwt` verified by the decoder. Never invoke the converter yourself on a `Jwt` object constructed from a raw Base64 payload and treat the resulting authorities as proof of authentication.

**Trust begins at the decoder**: signature, issuer, audience, timestamps, and caller contract have already been verified. The converter simply maps those verified permissions into application authority names.

## 11. Protecting HTTP Endpoints by Caller Kind **and** Scope

Illustrative design:

| Endpoint | Who Can Call | Required Permissions |
|---|---|---|
| `GET /api/me` | User token | `CALLER_USER` + `SCOPE_profile.read` |
| `GET /api/orders/**` | User or service | `SCOPE_orders.read` + business policy |
| `POST /api/orders/**` | User token | `CALLER_USER` + `SCOPE_orders.create` |
| `POST /api/import/jobs` | Machine token | `CALLER_SERVICE` + `SCOPE_orders.import` |
| `/api/admin/**` | Approved dedicated policy | Never open merely for client credentials |
| Other URLs | No caller | `denyAll()` |

### 11.1. Using AuthorizationManagers.allOf

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        AuthorizationManager<RequestAuthorizationContext> humanReadProfile =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasAuthority("CALLER_USER"),
                AuthorityAuthorizationManager.hasAuthority(
                    "SCOPE_profile.read")
            );

        AuthorizationManager<RequestAuthorizationContext> humanCreateOrder =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasAuthority("CALLER_USER"),
                AuthorityAuthorizationManager.hasAuthority(
                    "SCOPE_orders.create")
            );

        AuthorizationManager<RequestAuthorizationContext> machineImport =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager.hasAuthority("CALLER_SERVICE"),
                AuthorityAuthorizationManager.hasAuthority(
                    "SCOPE_orders.import")
            );

        return http
            // Example API authenticating solely via bearer header.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .access(humanReadProfile)

                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .access(humanCreateOrder)

                .requestMatchers(HttpMethod.POST, "/api/import/jobs")
                    .access(machineImport)

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

This example performs **coarse-grained HTTP-layer authorization** and does not yet solve ownership/tenant checks when returning data. `SCOPE_orders.read` is granted to both user and machine tokens **only if** both token types have contracts allowing the same action within appropriate resource bounds.

The snippet disables CSRF **strictly under the assumption of a pure bearer-header API**, without automatically sent authentication cookies. If the application uses browser sessions, a BFF, cookie-based access tokens, or form login, evaluate CSRF separately.

### 11.2. Why Check Both Marker and Scope Together?

If the rule were only:

~~~java
.requestMatchers(HttpMethod.POST, "/api/import/jobs")
    .hasAuthority("SCOPE_orders.import")
~~~

then a user token accidentally granted the `orders.import` scope by the AS could pass the HTTP layer. Whether that is right or wrong depends on policy.

If the business requirement is "import only for **approved machine workloads**," both are needed:

~~~text
CALLER_SERVICE AND SCOPE_orders.import
```

Similarly, the `/api/me` endpoint displaying user profile information **should not** be callable by a machine token treating a service account as a user.

### 11.3. `authenticated()` Is Not Enough

A policy:

~~~java
.requestMatchers("/api/users/**").authenticated()
~~~

lets both machine tokens and user tokens pass the HTTP layer. If an endpoint requires human-user context, use an appropriate marker/policy; if machines are allowed to call it, enforce separate permissions and ownership rules.

## 12. Resource-Level Authorization Must Differ by Principal Kind

A user token and a machine token with the same `SCOPE_orders.read` **do not necessarily get to view the same set of orders**.

Example:

~~~text
User token:
  subject = person-42
  client  = storefront-web
  scope   = orders.read
  policy  = read the user's own orders within an allowed tenant

Machine token:
  subject = svc:inventory-sync
  client  = inventory-sync
  scope   = orders.read
  policy  = read inventory-related order subset for tenant-a
```

If service code merely does:

~~~java
String owner = authentication.getName();

return orderRepository.findByOwnerId(owner);
~~~

it fails for machine callers because `getName()` is a service subject, not a user owner. The system may return empty results, or worse, bypass ownership via a default role.

### 12.1. Kind-Aware Domain Identity

~~~java
public sealed interface CallerIdentity
        permits HumanCaller, ServiceCaller {

    String issuer();
}

public record HumanCaller(
        String issuer,
        String userSubject,
        String clientId
) implements CallerIdentity {}

public record ServiceCaller(
        String issuer,
        String serviceSubject,
        String clientId
) implements CallerIdentity {}
~~~

These are **example-defined domain types**, not built into Spring Security. They should only be constructed **after successful JWT validation or introspection**. `issuer` keeps identity namespaces distinct.

### 12.2. Adapter from an Authenticated JWT

~~~java
public CallerIdentity resolveCaller(Jwt jwt) {
    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();
    String clientId = jwt.getClaimAsString("client_id");
    String kind = jwt.getClaimAsString("caller_kind");

    // Assumes CallerContractValidator has already been applied.
    if ("user".equals(kind)) {
        return new HumanCaller(issuer, subject, clientId);
    }
    if ("service".equals(kind)) {
        return new ServiceCaller(issuer, subject, clientId);
    }
    throw new AccessDeniedException("Unsupported caller kind");
}
~~~

This is an illustrative method inside a service/adapter receiving a `Jwt` from Spring Security, with the records and `AccessDeniedException` imported. Never obtain a `Jwt` from `JWTParser.parse(rawToken).getJWTClaimsSet()` and apply similar logic; unverified claims remain untrusted input.

### 12.3. Object-Level Policy

~~~java
public OrderDto readOrder(
        CallerIdentity caller,
        String tenantId,
        String orderId) {

    Order order = orderRepository
        .findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(NotFoundException::new);

    if (caller instanceof HumanCaller human) {
        if (!orderPolicy.canUserRead(
                human.issuer(), human.userSubject(), order)) {
            throw new AccessDeniedException("Forbidden");
        }
    } else if (caller instanceof ServiceCaller service) {
        if (!orderPolicy.canServiceRead(
                service.issuer(), service.clientId(), order)) {
            throw new AccessDeniedException("Forbidden");
        }
    } else {
        throw new AccessDeniedException("Unsupported caller");
    }

    return toDto(order);
}
~~~

`Order`, `OrderDto`, repositories, `NotFoundException`, `orderPolicy`, and `toDto(...)` belong to the **illustrative business application**. What must be preserved is **tenant-scoped querying and caller-kind-specific policy**. Never grant "machines read everything" simply because there is no user subject.

### 12.4. A `tenant_id` Claim Does Not Replace Membership Checks

`tenant_id=tenant-a` in a verified token indicates the AS asserts tenant context per contract. However, if the Orders API manages membership itself, the Resource Server must still check the current DB/ACL.

For machine callers, access may need restriction by client ID + tenant + operation + resource instance; for users, by subject + tenant + owner/role. Both must prevent BOLA/IDOR bugs.

## 13. Opaque Tokens Can Also Carry Client-Specific Claims

Not every AS issues JWTs. With opaque tokens, the Resource Server calls a trusted introspection endpoint:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=opaque-reference-token
~~~

A user token may introspect as:

~~~json
{
  "active": true,
  "sub": "person-42",
  "client_id": "storefront-web",
  "scope": "orders.read",
  "caller_kind": "user",
  "aud": ["orders-api"]
}
~~~

A machine token may return:

~~~json
{
  "active": true,
  "sub": "svc:inventory-sync",
  "client_id": "inventory-sync",
  "scope": "orders.import",
  "caller_kind": "service",
  "aud": ["orders-api"]
}
~~~

`caller_kind`, `aud`, and `sub` here belong to the **illustrative AS contract**; RFC 7662 does not require every response to include all of these fields.

**Never** construct an `OAuth2AuthenticatedPrincipal` for a token with `active=false`. The delegate introspector must confirm the token is valid before custom claim mapping.

### 13.1. Opaque Token Principals Differ from JWTs

| Token Flow | Principal After Authentication | Customization Point |
|---|---|---|
| JWT | Typically `Jwt` via `JwtAuthenticationToken` | `JwtDecoder`, `JwtAuthenticationConverter` |
| Opaque | `OAuth2AuthenticatedPrincipal` via `BearerTokenAuthentication` | `OpaqueTokenIntrospector`, corresponding converter |

Never cast an opaque principal to `Jwt`. If sharing controllers across both token mechanisms, accept `Authentication` or build a domain caller adapter branching on authentication type.

### 13.2. Wrapper Introspector Preserving Scopes

Custom example:

~~~java
package com.example.orders.security;

import java.util.LinkedHashSet;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class CallerKindOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public CallerKindOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Authentication first, mapping second.
        OAuth2AuthenticatedPrincipal p = delegate.introspect(token);

        String kind = p.getAttribute("caller_kind");
        String clientId = p.getAttribute("client_id");

        boolean user = "user".equals(kind)
            && "storefront-web".equals(clientId);

        boolean service = "service".equals(kind)
            && "inventory-sync".equals(clientId);

        if (!user && !service) {
            throw new BadOpaqueTokenException(
                "Unexpected caller contract");
        }

        var authorities = new LinkedHashSet<GrantedAuthority>(
            p.getAuthorities());

        authorities.add(new SimpleGrantedAuthority(
            user ? "CALLER_USER" : "CALLER_SERVICE"));

        return new DefaultOAuth2AuthenticatedPrincipal(
            p.getName(),
            p.getAttributes(),
            authorities
        );
    }
}
~~~

**Note:** this abbreviated example only illustrates **wrapping the delegate** and preserving scopes. In production, the contract must also validate `aud`/resource binding, token type, issuer/identity source, client ID allowlists, and field types; do not rely solely on `active=true`.

When an opaque response **omits `iss`**, derive the identity source from the trusted configured introspection endpoint per contract. Never take the issuer from a client header.

## 14. Notably: `roles` and `groups` Can Differ Between Users and Services

Some ASs emit:

~~~json
{
  "roles": ["orders-reader"],
  "groups": ["sales-team"]
}
~~~

for user tokens; machine tokens have:

~~~json
{
  "roles": ["inventory-importer"]
}
~~~

or **neither** claim.

By default, Spring Security **has no universal rule** that maps arbitrary `roles` and `groups` from any AS into API permissions. Decide explicitly:

- Which roles belong to `orders-api`, rather than the IdP's management realm?
- Are roles user-editable or assigned by an authoritative admin/policy?
- Are roles tenant-scoped or global?
- When the AS omits roles, fail closed or simply add no authorities?
- Should a service account's role count as a human role? Typically **no**.
- What allowlist is needed per issuer/client mapping?

Example mapping:

| Input from Authoritative Source | Application Authority | Caller Kind |
|---|---|---|
| `scope=orders.read` | `SCOPE_orders.read` | Both if contract permits |
| `roles=["order-viewer"]` | `ROLE_ORDER_VIEWER` | Approved user policy |
| `roles=["inventory-importer"]` | `ROLE_INVENTORY_IMPORTER` | Approved service policy |
| `permissions=["orders.export"]` | `PERM_ORDERS_EXPORT` | Per AS entitlement |
| `email` contains `admin` | **Grant no permission** | Not applicable |
| Machine lacks `groups` | Do not synthesize user groups | Not applicable |
| Unknown role `root` | Do not map to admin | Not applicable |

**Never convert arbitrary strings via `"ROLE_" + value.toUpperCase()`.** An `admin` role in an IdP console is not automatically equivalent to an Orders API admin role.

## 15. Machine Clients Should Not Borrow User Permissions

A service can call an API in two different contexts.

### 15.1. Service Acting **for Itself**

~~~text
Inventory Worker
  -> client_credentials
  -> access token with client/service subject
  -> Orders API
```

It is allowed to exercise granted **application-level** permissions, such as importing inventory data for a registered tenant.

### 15.2. Service Acting **on Behalf of a User**

~~~text
Person-42 -> BFF -> Orders API
              |
              +-> Another API on behalf of Person-42
```

In the second case, if downstream needs both **user identity** and **actor/service identity**, machine `client_credentials` alone does not preserve user delegation. You may need:

- An access token issued for the exact downstream audience per the client flow.
- A token exchange under **RFC 8693** or an AS-supported on-behalf-of mechanism.
- Explicit actor/delegation semantics, potentially via the `act` claim when using a token exchange profile.
- Appropriately downscoped scopes and resource restrictions.
- Auditing that records actor and subject with proper semantics.

**Never** inject:

~~~json
{
  "sub": "person-42",
  "caller_kind": "user"
}
~~~

into a machine token or a header and treat it as user-delegated authorization. A machine token authenticating service A does not become person-42's token just because the caller attaches `X-User-Id: person-42`.

### 15.3. Service-to-Service Forwarding and Audience

If API A receives an access token with `aud=api-a`, API A **must not forward** that token to API B expecting B to accept it. B must enforce `aud=api-b` or the appropriate resource. When downstream delegation is needed, obtain a token with the right audience/scope via an AS-approved mechanism.

This applies to both user-facing and machine-to-machine flows.

## 16. Different Issuers Can Publish Different Claims

In a multi-issuer integration:

~~~text
Issuer A user token:
  scope = "orders.read"
  client_id = "storefront-web"
  sub = "person-42"

Issuer B service token:
  scp = ["orders.import"]
  client_id = "inventory-sync"
  sub = "service-18"
```

You may need to normalize claim names:

~~~text
scope / scp -> OAuth authorities
sub         -> canonical subject per issuer
client_id   -> OAuth client
caller kind -> per issuer/token profile contract
```

However, **do not equate fields with different semantics**. For example, issuer B's `roles` are not automatically equivalent to issuer A's `roles`.

If an API supports multiple JWT issuers, use a **trusted issuer allowlist** with `JwtIssuerAuthenticationManagerResolver` or an issuer-specific decoder/manager repository. The `iss` claim from an unverified payload may only be used to route to a trusted manager; never allow an attacker-supplied token to point to arbitrary JWKS/metadata URLs.

### 16.1. Same `client_id` at Two Issuers May Not Be the Same App

~~~text
(issuer A, client_id=worker)
(issuer B, client_id=worker)
```

are two independent client registrations unless the system has an explicit federation mapping. Machine callers should be audited by **issuer + client ID + service subject + tenant** per contract, not `client_id` alone.

### 16.2. User Profiles Can Differ by Issuer

One issuer may return `email`, another may not; one returns `preferred_username`, another only `sub`. Do not force all user tokens to contain the same display fields if the API does not need them, and never use email as a canonical cross-issuer identity.

## 17. AS and Resource Server Must Agree on Responsibilities

One cause of "user token has roles, machine token does not" may simply be that **the AS protocol mapper is not configured for that client/grant**, not necessarily a Spring Security bug.

Division of responsibility:

| Task | Authorization Server | Resource Server |
|---|---|---|
| Authenticate end-user | Yes, in user-authentication flows | Do not re-authenticate the user for bearer APIs |
| Authenticate machine client at token endpoint | Yes | Never treat client secrets as bearer tokens |
| Determine client/grant allowed scopes | Yes | Never backfill missing scopes |
| Set `sub`/`client_id`/`aud` | Yes, per profile | Validate and interpret properly |
| Set custom `caller_kind` | Yes, per governed contract | Validate + map marker |
| Emit profile claims | Optionally per client scopes/mappers | Never treat profile fields as entitlements |
| Sign JWT or store opaque token state | Yes | Verify JWT or introspect |
| Map claims -> authorities | May emit standardized entitlements | Map via application allowlist |
| Determine which tenant/owner owns an order | May provide coarse tenant claim | **Must enforce object/resource policy** |
| Revoke/rotate credentials | Yes | Enforce token status/time/key policy |
| Audit and anomaly detection | Yes | Log caller kind, resource, and accurate decision |

### 17.1. What to Check on the AS Side When Machine Tokens Lack Claims

Before editing the converter, verify:

1. Is the machine client authorized to use `client_credentials`?
2. Did the AS assign the right **client scopes** and **audience**?
3. Are roles/permissions assigned to the **service account/application** or only to human users?
4. Does the protocol mapper include entitlements in the **access token**, not just ID token/UserInfo?
5. Is custom `caller_kind` set **from token issuance policy**?
6. Does the AS emit `sub`/`client_id` per the chosen JWT access token profile?
7. Was the token sent to the right API, issuer, tenant, and environment?
8. Is a machine token calling an endpoint restricted to human users?

### 17.2. Do Not Demand That "Every Token Look Identical"

A completely valid situation:

~~~text
User token:
  sub person-42
  client_id storefront-web
  scope orders.read
  preferred_username mai

Machine token:
  sub svc:inventory-sync
  client_id inventory-sync
  scope orders.import
  no preferred_username
```

This is not necessarily an error. The goal is for **the API to have the right contract for each token purpose**, not to force machine tokens to carry every end-user field.

## 18. Distinguishing 401, 403, and Claim Mapping Errors

| Symptom | Likely Root Cause Layer | Action |
|---|---|---|
| Machine token lacks `email` | Claim profile outside machine contract | Do not require email if unnecessary |
| Machine token lacks `sub` despite contract requirement | Issuer/token profile mismatch | Fix AS contract or reject |
| Token has `client_id` yet lacks required `caller_kind` | Missing issuer mapper | Reject, never guess |
| `caller_kind=service` yet client ID is in user allowlist | Token purpose mismatch | Reject |
| Invalid JWT signature/issuer/audience | Authentication failure | 401 per bearer entry point |
| Expired token | Authentication failure | 401 |
| Opaque token `active=false` | Authentication failure | 401 |
| Valid token yet user calls service-only import | Authorization failure | 403 |
| Machine has `SCOPE_orders.read` yet calls `/api/me` | Not a human caller | 403 |
| Valid user reads another tenant's order | Object-level authorization | 403/404 per policy |
| Machine has role yet API ignores it | Mapper/claim contract | Fix approved mapping, never grant admin blindly |
| Auth service/JWKS outage | Dependency failure | Never fail open |
| Client ID right yet grant purpose wrong | Grant/profile contract | AS policy and caller-kind validation |
| User `sub` collides with service `sub` | Identity collision | Add issuer/kind namespace |
| OIDC ID token sent to API | Wrong token audience/type | Reject |

**401** typically relates to missing or failed token authentication; **403** typically relates to an authenticated token lacking permissions. Infrastructure errors may map to 5xx or other statuses depending on exception handling/version; do not treat every timeout as a permission denial.

### 18.1. Why Not Add Permissions When Seeing a 403?

A wrong fix:

~~~java
if (clientId.equals("inventory-sync")) {
    authorities.add(
        new SimpleGrantedAuthority("SCOPE_orders.write"));
}
~~~

if the AS only granted `orders.read`, this is **privilege escalation**. The proper fix is adjusting client authorization/entitlements at the AS or updating API policy if the business genuinely requires it.

## 19. Unit Testing the Claim Contract

Unit tests help verify that the validator **does not treat every `sub` as a user**.

### 19.1. Building a Jwt Test Object

~~~java
package com.example.orders.security;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CallerContractValidatorTest {

    private final CallerContractValidator validator =
        new CallerContractValidator();

    private Jwt jwt(
            String subject,
            String clientId,
            String kind) {

        return Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .issuer("https://login.example.com/realms/orders")
            .subject(subject)
            .claim("client_id", clientId)
            .claim("caller_kind", kind)
            .issuedAt(Instant.now())
            .expiresAt(Instant.now().plusSeconds(600))
            .build();
    }

    @Test
    void userClientWithUserPurposeIsAccepted() {
        var token = jwt("person-42", "storefront-web", "user");
        assertFalse(validator.validate(token).hasErrors());
    }

    @Test
    void serviceClientWithServicePurposeIsAccepted() {
        var token = jwt(
            "svc:inventory-sync",
            "inventory-sync",
            "service"
        );
        assertFalse(validator.validate(token).hasErrors());
    }

    @Test
    void userClientCannotClaimServicePurpose() {
        var token = jwt("person-42", "storefront-web", "service");
        assertTrue(validator.validate(token).hasErrors());
    }

    @Test
    void missingPurposeIsRejected() {
        var token = jwt("person-42", "storefront-web", null);
        assertTrue(validator.validate(token).hasErrors());
    }
}
~~~

This test uses an in-memory `Jwt` and **does not verify signatures**. It only exercises `CallerContractValidator` logic; it does not replace real `JwtDecoder` tests. `Jwt.Builder` helpers may vary by Spring Security version; if needed, use `.claim("iss", ...)`, `.claim("sub", ...)` as supported by your fixture.

### 19.2. Testing Authority Mapping

Goal:

~~~text
User token:
  scope="orders.read"
  caller_kind="user"
=> SCOPE_orders.read + CALLER_USER

Machine token:
  scope="orders.import"
  caller_kind="service"
=> SCOPE_orders.import + CALLER_SERVICE

Unknown caller_kind:
=> validator must reject before converter builds Authentication
```

A converter unit test should assert:

- All granted `SCOPE_*` authorities are preserved.
- Import/write scopes are never added automatically.
- `ROLE_ADMIN` is never derived from email/username.
- Marker type appears only per contract.
- Behavior does not depend on absent `groups`/`email`.

### 19.3. Testing Web Authorization

With `MockMvc` and Spring Security Test:

~~~java
mvc.perform(post("/api/import/jobs")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("CALLER_SERVICE"),
            new SimpleGrantedAuthority("SCOPE_orders.import")
        )))
    .andExpect(status().isOk());
~~~

This example assumes the endpoint exists, no CSRF is required in the bearer-only test chain, and business code succeeds. A **mock token** only proves authorization rules; it bypasses the decoder and custom converter.

Add a contrasting test:

~~~java
mvc.perform(post("/api/import/jobs")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("CALLER_USER"),
            new SimpleGrantedAuthority("SCOPE_orders.import")
        )))
    .andExpect(status().isForbidden());
~~~

This result demonstrates that import scope **is not enough** when the endpoint requires a machine caller. Import `post`, `status`, `jwt`, and `SimpleGrantedAuthority` from Spring Test/MockMvc.

### 19.4. JWT Integration Tests Must Use Genuinely Signed Tokens

To prove the entire pipeline:

1. Generate a dedicated test RSA key pair.
2. Mock a JWKS endpoint serving the test public key.
3. Create **genuinely signed** JWTs with `iss`, `aud`, `exp`, `client_id`, `caller_kind`, and `scope`.
4. Send `Authorization: Bearer <signedJwt>` through real security filters.
5. Verify valid user tokens receive the human marker and valid service tokens receive the service marker.
6. Reject bad signatures, wrong issuers, wrong audiences, and expired tokens.
7. Reject `caller_kind=service` signed for `storefront-web` in violation of the contract.
8. Reject missing `caller_kind` or unknown client IDs.
9. Verify absence of end-user email does not reject valid service tokens when email is not required by contract.
10. Verify 403 when a service token calls a user-only endpoint.
11. Verify ownership/tenant ACLs at the service layer.
12. Verify an OIDC client's ID token fails API audience/token-type policies.

**Never** use production private signing keys or Base64-decode payloads and assume tests verified signatures.

## 20. Negative Claim Test Matrix

| Token | Expected Principal Kind | Outcome |
|---|---|---|
| User token with right issuer/aud/client/kind | `user` | Authentication passes; authorization depends on scope |
| Machine token with right issuer/aud/client/kind | `service` | Authentication passes; authorization depends on scope |
| User token missing email | `user` | Can pass, if email is optional |
| Machine token missing email | `service` | Passes per service contract |
| Machine token with `preferred_username` set to service account name | `service` | Not treated as a human user |
| User token with `caller_kind=service` yet user client | Invalid | Reject |
| Machine client with `caller_kind=user` | Invalid | Reject |
| Missing `caller_kind` when required by contract | Unknown | Reject |
| Kind claim set to `admin` | Unknown | Reject, do not map role |
| `aud=billing-api` | Invalid for Orders API | Reject |
| Wrong issuer/signature/expiry | Invalid | Reject |
| Has `SCOPE_orders.import` yet is user token | `user` | Machine-only import returns 403 |
| Has `SCOPE_profile.read` yet is machine token | `service` | `/api/me` returns 403 |
| Has `orders.read` yet order belongs to another tenant | User or service | Rejected at service |
| Two issuers sharing `sub` | Separate identities | Never merged |
| Client Credentials token spoofed with `X-User-Id` | `service` | Not turned into a user |
| Opaque `active=false` | No principal | Reject |
| AS timeout during introspection | Unverifiable | Never fail open |

A robust system **does not only test tokens with complete claims**, but also missing fields, wrong types, spoofed token purposes, and erroneous identity collisions.

## 21. Client Credential Security and Lifecycle

### 21.1. Public User-Facing Clients

For SPAs/mobile apps, the OAuth client usually cannot hold a secret like a backend. Use Authorization Code + PKCE and appropriate session/redirect/CSRF protections for the architecture.

Never embed a client secret in a JavaScript bundle or mobile app and treat it as confidential.

### 21.2. Confidential Machine Clients

For `client_credentials`, use a client authentication method supported by the AS and approved by your organization, such as:

- Secrets stored in a secret manager and rotated.
- Private key JWT client authentication where appropriate.
- Mutual TLS if provided by infrastructure.
- Workload identity/federation when supported by the AS.
- Least-privilege scopes/audiences per workload.
- Short token lifetimes aligned with SLOs and refresh capabilities.

**Never send client credentials to the Orders API** as if they were access tokens. The client authenticates to the AS, then uses the **issued access token** to call the Resource Server.

### 21.3. Opaque vs. JWT, Revocation

Locally verified JWTs normally do not query the AS per request once keys are fetched; early revocation requires additional design if needed.

Opaque token introspection can reflect `active=false` sooner per AS policy, though introspection or directory caches can still cause stale permissions. Never treat `client_credentials` tokens as holding unlimited privileges.

## 22. Privacy and Data Minimization

A core issuer-integration principle is to **put into access tokens only what the Resource Server truly needs**.

For example, Orders API needs:

~~~text
iss, sub, aud, exp, scope, client_id, caller_kind
tenant context per contract if needed
```

It likely **does not need**:

~~~text
birthdate, home address, full user profile,
email, phone number, every group across the organization
```

Stuffing all OIDC profile claims into access tokens so the API "has plenty of data" increases PII exposure if tokens are logged or passed across services.

For machine tokens, there is typically no reason to include human profile claims. If you need to audit who operates a workload, store that metadata in a trusted registry/admin inventory rather than faking a human `sub` inside a client-credentials token.

### 22.1. Do Not Log Raw Bearer Tokens

Log normalized details at a minimal level:

~~~text
requestId=trace-123
issuerRef=orders-prod
callerKind=service
clientRef=inventory-sync
subjectRef=<stable-internal-ref>
endpoint=/api/import/jobs
decision=DENY
reason=missing_scope
bearerToken=[REDACTED]
~~~

Never write raw Authorization headers, ID tokens, private signing keys, client secrets, or full JWT claims/opaque responses to production logs.

## 23. Investigation Procedure When Two Clients Receive Different Claims

When a developer asks "same AS, why does the web token have `email`/`roles` while the job token does not," follow this order:

**Step 1 — Identify the exact token.** Is it an access token, ID token, or UserInfo response? Never compare a browser ID token to a machine access token.

**Step 2 — Identify the grant.** Is the web app using Authorization Code or token exchange? Is the job actually using client credentials or a stored user token?

**Step 3 — Identify the issuer and intended audience.** Do both have the right `iss` and `aud=orders-api`? Are they in different realms/environments?

**Step 4 — Check AS client registrations.** Do `client_id`, client scopes, allowed grants, audience, service account roles, and protocol mappers differ?

**Step 5 — Identify the claim source.** Email comes from a user profile; service entitlements come from client/service-account authorization; both should not be expected to carry identical fields.

**Step 6 — Check the API's claim contract.** Which `sub`, `client_id`, caller purpose, and scopes does the API need? Is it mistakenly requiring email on machine paths?

**Step 7 — Check the Resource Server mapper.** `JwtGrantedAuthoritiesConverter` reads scope/scp by default; it does not automatically interpret arbitrary `roles` or `groups`.

**Step 8 — Check HTTP rules.** A valid token may still lack `SCOPE_orders.import` or fail `CALLER_SERVICE`.

**Step 9 — Check service policy.** Tenant membership, owner/ACL, and resource state can deny access even if another endpoint returns HTTP 200.

**Step 10 — Write tests for AS mappings.** Add unit, signed-token integration, and end-to-end tests with real clients/grants; never add default roles just to make a 403 go away.

### 23.1. Never Fix by "Copying All User Claims to Machines"

If a job lacks `email`, the right fix is usually **not requiring email** on the machine path. If a job lacks permissions, grant the proper entitlements at the AS for that application client. Never assign fake emails or admin roles to machines just to satisfy shared code.

## 24. Common Misconceptions

**"Same Authorization Server means all access tokens must have identical claims."** False. Clients, grants, scopes, mappers, and resource audiences can produce different tokens.

**"Having `sub` means a human user."** False. RFC 9068 allows access tokens without a resource owner to use `sub` for the application/client.

**"Machine tokens never have `sub`."** False. Depending on the token profile, `sub` can be the service/application identity.

**"`sub == client_id` for all `client_credentials`."** Do not assume this. Contracts depend on the AS; RFC 9068 recommends identifying the client app.

**"A user client has `client_id`, so `client_id` is the user ID."** False. Many users can share the same client.

**"Client ID alone tells whether an end-user is present."** Uncertain when a client supports multiple grant types; a trustworthy token-purpose/grant contract is required.

**"A machine client lacking email has a broken token."** False if email is not part of the service token contract.

**"OIDC `openid profile email` means the Orders API can read all profiles."** False. OIDC identity scopes do not replace OAuth API business scopes.

**"An ID token works at a Resource Server because it is also a JWT."** False. An access token with the right audience and type must be used.

**"If `roles` is in the JWT, Spring automatically converts everything to `ROLE_*`."** Not by default. Explicit mapping and a trusted entitlement source are required.

**"A service account named with `admin` means `ROLE_ADMIN`."** False. Display/usernames are not permissions.

**"M2M tokens have stronger permissions than user tokens."** Not by default. Both have distinct policy-defined permissions and should follow least privilege.

**"A client credentials token can act for any user via `X-User-Id`."** False. Delegation/token exchange/AS policy is required when truly acting on a user's behalf.

**"Same `SCOPE_orders.read` means every caller reads the same data."** False. Service business authorization also evaluates subject, tenant, and owner.

**"A custom JWT converter guarantees the JWT was properly signed."** No. The decoder verifies; the converter only maps validated claims in the standard pipeline.

**"Saw a 403, so I added the scope myself."** Dangerous. Scopes must originate from an authoritative issuer.

**"Testing with `MockMvc.with(jwt())` proves the AS issues the right claims."** No. Mocks bypass the decoder and real issuer issuance.

## 25. Self-Check Questions

**1.** Why might a `client_credentials` token lack `email` or `preferred_username`?

> Because the grant has no logged-in end-user; the token primarily represents an application or service identity.

**2.** Is `sub` in a JWT always a human user ID?

> No. In a JWT access token profile, a token without a resource owner can use `sub` to represent the application/client identity.

**3.** Is `client_id` in a user token a user identifier?

> No. It identifies the OAuth client application, whereas user identity typically comes from subject and issuer.

**4.** Can user vs. machine callers be distinguished by `client_id` alone?

> Only if the AS/client registration contract guarantees that client is exclusive to one token kind; if a client supports multiple grants, it is insufficient.

**5.** Is there a mandatory standard `grant_type` claim on every access token?

> No. The OAuth grant is sent in the token request; claims inside the access token depend on the profile and AS. `gty`/`grant_type` in a JWT may be vendor extensions.

**6.** Where do ID tokens and access tokens primarily differ?

> ID tokens serve OIDC user authentication at the client; access tokens authorize the Resource Server to access resources with the right audience/scopes.

**7.** What does Spring Security convert `scope=orders.read` into by default?

> Typically into the `SCOPE_orders.read` authority, after the token has been verified.

**8.** Does Spring Security automatically map `roles=["inventory-importer"]`?

> Not universally. A custom mapper/claim contract is required.

**9.** Why must the `CALLER_SERVICE` marker accompany `SCOPE_orders.import`?

> Caller kind identifies the principal type; scope expresses the operation permission. Neither replaces the other.

**10.** Can a machine client with `SCOPE_orders.read` view orders across all tenants?

> No. Service ACLs/tenant binding and resource-level authorization are still required.

**11.** When can a machine token represent a user?

> When backed by contract-compliant authorization/delegation such as token exchange/on-behalf-of; plain client credentials never count as a user token.

**12.** To investigate why a machine token lacks roles, which layer should be checked first?

> AS client registration, service account entitlements, client scopes/protocol mappers, and access-token issuance policy.

**13.** If a token has `caller_kind=service` yet was issued to a user-facing client, what should happen?

> Reject it per the caller contract if that combination is disallowed.

**14.** Should all tokens be forced to carry profile claims so one DTO works everywhere?

> No. Design domain principals/DTOs around caller kind and data minimization.

**15.** Why do integration tests need JWTs signed with test keys?

> To genuinely exercise the decoder, issuer, audience, caller kind, and mapping; mock authentications do not prove the trust chain.

## 26. References

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, Client Credentials, access tokens, scopes.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): Authorization Code with proof key, especially for public clients.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `iss`, `sub`, `client_id`, `aud`, scopes, and subjects for tokens without a resource owner.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `client_id`, `scope`, `sub`, attributes of opaque tokens.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): binding intended resource/audience.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegation, impersonation, and actor `act`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience validation, algorithm confusion, and cross-token confusion.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, and end-user profile claims.
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification, `JwtAuthenticationConverter`, `scope`/`scp` mapping.
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, `OAuth2AuthenticatedPrincipal`, authorities.
- [Spring Security — JwtGrantedAuthoritiesConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): claim name, scope prefix, and custom authorities.
- [Spring Security — JwtAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): building `JwtAuthenticationToken` from a verified JWT.
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuers/issuer-aware managers.
- [Spring Security — HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, `AuthorizationManagers.allOf`, rule ordering.
- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/): server-side token customization, registered clients, and client authentication.

**Summary:** tokens for **user-facing clients** and **machine clients** can have **completely different claims** because they represent different principals and authorization contexts. The Resource Server must properly verify JWTs/introspection, enforce issuer/audience/token type, interpret `sub` and `client_id` per the AS contract, map only substantiated scopes/roles, and authorize according to human/service identity. Never assume `email` is always present, never treat a machine client as a human user, and never turn profile fields into permissions. Proper design pairs a **claim contract at the Authorization Server**, **validation/conversion in Spring Security**, and **tenant/ownership authorization in business services**.