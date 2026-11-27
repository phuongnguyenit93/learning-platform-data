# Registered Claims, Public Claims, and System-Specific Claims

In **Spring Security OAuth 2.0 / OIDC Resource Server**, an Access Token can be represented as a **JSON Web Token (JWT)**. A JWT contains **claims**: name–value pairs representing information about the subject, issuer, intended audience, lifetime, access permissions, and system-defined data.

Not every claim has the same origin or meaning. According to [RFC 7519, Section 4](https://www.rfc-editor.org/rfc/rfc7519#section-4), claim names are divided into three categories: **Registered Claim Names**, **Public Claim Names**, and **Private Claim Names**. This classification helps parties align on naming, avoid collisions, and determine which claims require validation. However, **having claims in a JWT does not automatically prove the token is valid or the caller is authorized**: the Resource Server must validate the token and enforce specific policies.

## 1. Where Do Claims Reside in a JWT?

A JWT in **JWS compact serialization** typically has the structure:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
        Part 1              Part 2              Part 3
~~~

Example JSON of a **JOSE Header**:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "at+jwt"
}
~~~

Example JSON of a **JWT Claims Set**:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Where:

- **alg**, **kid**, **typ** belong to the **JOSE Header**, not payload claims. **alg** indicates the declared signing algorithm; **kid** helps pick the verification key; **typ** helps identify the object/token type when required by a profile.
- **iss**, **sub**, **aud**, **exp**, **iat** are familiar **registered claims**.
- **scope** is a claim used in the OAuth 2.0/JWT Access Token profile context; it is **not part of RFC 7519's original list of seven registered claims**.
- **tenant_id** is a custom claim name defined by the example system; it is not a universal standard name by default.

The JSON snippets above are solely for explaining structure; they are not a validly signed JWT. **Base64url is a data-to-string encoding, not security encryption.** If a JWT is only signed as a JWS, anyone holding the token can read the payload, even though they cannot validly modify it without the signing key.

> **Core point:** "A claim written in the token" describes data carried by the token; "a claim trusted for decision-making" requires the Resource Server to verify the token, context, audience, issuer, and business rules.

## 2. Three Claim Name Categories in RFC 7519

| Category | Characteristics | Usage | Examples |
| --- | --- | --- | --- |
| **Registered Claim Names** | Names defined by RFC 7519 with standardized semantics. | Used to represent standard information such as issuer, audience, and lifetime. | **iss**, **sub**, **aud**, **exp**, **nbf**, **iat**, **jti**. |
| **Public Claim Names** | Names defined by a community or system for broad use; must be **registered in the IANA JWT Claims Registry** or use a **collision-resistant name**. | Helps multiple components exchange claims while reducing the risk of name collisions with conflicting meanings. | **https://claims.example.test/tenant_id** (illustrates an organization-controlled namespace). |
| **Private Claim Names** | Names **agreed upon directly** between JWT producers and consumers; global uniqueness is not guaranteed. | Serves business data for a specific system or group of applications. | **tenant_id**, **roles**, **permissions**, **department_code**. |

**Registered**, **public**, and **private** here refer to **naming and convention scope**, not the confidentiality of the values:

- A **public claim** does not mean its content is meant to be public to outsiders.
- A **private claim** does not mean its content is encrypted or confidential by default.
- A **registered claim** does not mean its value is checked by the framework in every case.

RFC 7519 intentionally does not require every JWT to include all seven registered claims. **A specific profile** such as OIDC ID Token or JWT Access Token dictates which fields are mandatory and how they must be validated.

### 2.1. "Defined in a Standard" vs. "One of the Seven Core Registered Claims"

Many standards and systems use additional claim names:

- OIDC defines authentication-related claims such as **auth_time**, **nonce**, **acr**, **amr** and profile claims such as **name**, **email**, **email_verified**.
- The OAuth 2.0 JWT Access Token profile (RFC 9068) defines how to represent claims intended for Resource Servers, including names like **client_id** and **scope**.
- Providers may use **scp**, **realm_access**, **groups**, **roles**, or namespaced names depending on design.

Some claims from extension specifications have been registered in the **IANA JWT Claims Registry**. Therefore, a more accurate phrasing is: **RFC 7519's seven core registered claims** and **claims defined/registered by extension profiles**. Never assume every claim outside the first seven is "private," nor assume a familiar name always has the same data type across all issuers.

## 3. The Seven Registered Claims in RFC 7519

### 3.1. Overview Table

| Claim | Full name | Typical value | Practical meaning |
| --- | --- | --- | --- |
| **iss** | Issuer | String, typically the Authorization Server's HTTPS URL | Who issued the JWT? |
| **sub** | Subject | Subject identifier string | Who/what is the JWT about? |
| **aud** | Audience | String **or array of strings** | Which recipient is the JWT intended for? |
| **exp** | Expiration Time | **NumericDate** | After what time is the JWT no longer accepted? |
| **nbf** | Not Before | **NumericDate** | What is the earliest time the JWT is accepted? |
| **iat** | Issued At | **NumericDate** | When was the JWT issued? |
| **jti** | JWT ID | JWT identifier string | Unique token identifier, useful for tracking/replay control. |

### 3.2. **iss** — Issuer

~~~json
{
  "iss": "https://idp.example.test/realms/training"
}
~~~

**iss** identifies the party that issued the JWT. In Spring Security JWT Resource Server, **issuer-uri** is commonly used to declare the trusted issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
~~~

The Resource Server must verify **iss** against trusted configuration; **never** arbitrarily read the **iss** URL from an unverified token and automatically trust every issuer a client sends. When multiple tenants have separate issuers, the system needs a controlled issuer selection mechanism constrained to a trusted issuer allowlist.

### 3.3. **sub** — Subject

~~~json
{
  "sub": "user-123"
}
~~~

**sub** represents the subject of the JWT. In an OIDC ID Token, it is the user identifier issued by the OpenID Provider to the Relying Party per OIDC rules. In a JWT Access Token, it may represent a user or another principal depending on the grant and issuance profile—for instance, a machine-to-machine flow with no interactive user.

Do not use **sub** alone as a global identifier across all accounts: **sub** must be interpreted **within the issuer's context**, typically combining **(iss, sub)** when linking to internal users. In particular, **email** can change or be unverified, so never treat it as a default substitute for **sub**.

### 3.4. **aud** — Audience

~~~json
{
  "aud": "orders-api"
}
~~~

Or:

~~~json
{
  "aud": ["orders-api", "reports-api"]
}
~~~

**aud** specifies the intended recipient(s) of the JWT. Under RFC 7519, audience can be **a single string** or **an array of strings**; APIs must handle both forms properly. On a Resource Server named **orders-api**, checking that tokens carry an audience for **orders-api** prevents **token substitution**: using a token meant for another application to call this API.

For example, an OIDC **ID Token** typically has **aud** containing the web client's **client_id**; a JWT **Access Token** meant for an API requires an audience matching the Resource Server. Both may be signed by the same issuer, which is never a reason for an API to accept an ID Token as a Bearer Access Token.

### 3.5. **exp** — Expiration Time

~~~json
{
  "exp": 1893456000
}
~~~

**exp** is the expiration timestamp. Under RFC 7519 semantics, a token **must not be accepted at or after `exp`**, aside from a small clock skew tolerance allowed by the validator. The value must be a **NumericDate**, not an arbitrary date string.

Common mistakes:

- Confusing **seconds** with **milliseconds**, causing severely wrong validity periods.
- Decoding the payload to check **exp** while skipping signature or issuer verification.
- Sending an expired token expecting the Resource Server to refresh it automatically; **refreshing tokens** is the responsibility and flow of the OAuth 2.0 Client, not the API's default job.

### 3.6. **nbf** — Not Before

~~~json
{
  "nbf": 1893452400
}
~~~

**nbf** sets the **earliest** time at which the token may be accepted. A token before **nbf** must be rejected per claim semantics, accounting for a small configured clock skew. Some systems omit this claim when unused, but when present, the validator must enforce it per profile.

### 3.7. **iat** — Issued At

~~~json
{
  "iat": 1893452400
}
~~~

**iat** indicates when the JWT was issued. This claim helps calculate token age or enforce a "accept only recent tokens" policy. **iat is not synonymous with exp**; having `iat` by itself imposes no expiration time. Systems must also never assume "having `iat` means the token is valid."

### 3.8. **jti** — JWT ID

~~~json
{
  "jti": "order-access-b97c0f41"
}
~~~

**jti** is an issuer-assigned token identifier; its value should have a negligible collision probability per JWT rules. It can support mechanisms such as:

- **Replay prevention** for **single-use** requirements.
- **Denylists** to support invalidating specific tokens.
- Correlating token activity in tightly controlled systems.

**Merely having `jti` in the payload does not prevent replay by itself.** The API must maintain state or a dedicated verification mechanism if it needs to reject an already-used **jti**. For standard Bearer Access Tokens reused multiple times within their lifetime, "allow a `jti` only once" is usually unsuitable unless explicitly designed for that model.

### 3.9. NumericDate and Clocks

**exp**, **nbf**, and **iat** use **NumericDate**: seconds since **1970-01-01T00:00:00Z**, ignoring leap seconds as defined by the RFC. A NumericDate can be an integer or non-integer number; systems typically emit integers. Example:

~~~json
{
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

This illustrative token has a nominal validity window of **one hour**, assuming all other conditions pass. Resource Servers require synchronized clocks; a small **clock skew** can absorb minor system time drift, but should never arbitrarily extend token lifetimes.

## 4. Public Claims: Naming So Multiple Systems Share the Same Meaning

RFC 7519 allows parties to define new claims for public use or multi-party exchange. To avoid collisions, new claim names should follow one of two approaches:

1. **Register the name and semantics** in the **IANA JSON Web Token Claims Registry** via the appropriate registration process.
2. Use a **collision-resistant name** controlled by the defining organization, such as a namespaced name based on an organization-owned domain.

Example application representing an organization (tenant) identifier when sharing an Access Token across multiple APIs:

~~~json
{
  "https://claims.example.test/tenant_id": "tenant-42",
  "https://claims.example.test/account_tier": "enterprise"
}
~~~

These are **string-valued claim names**, not required to be live URLs or endpoints for the API to call. The key point is tying the namespace to a domain controlled by the organization, reducing the risk of another party accidentally defining the same name with a different meaning. The **example.test** domain is illustrative only.

Never use a domain namespace not controlled by the issuing system. Likewise, never invent a "standard-looking" name and assume every Authorization Server will understand it. For claims exchanged across multiple partners, publish clear documentation:

| Definition field | Example |
| --- | --- |
| Claim name | **https://claims.example.test/tenant_id** |
| JSON type | **string** |
| Meaning | ID of the tenant the token is authorized to access |
| Value domain | Tenants managed by the issuer |
| May be omitted? | No, for this multi-tenant API profile |
| Validation rules | Must match the tenant in the path/resource and the principal's permissions |
| Issuing source | Only the trusted Authorization Server may attach this claim |
| Versioning/compatibility | Convention kept stable; schema change process defined |

A "collision-resistant name" only guarantees **name distinctness**, providing no automatic data protection. The API must still verify signature, issuer, audience, and value validity.

## 5. Private Claims: Internal Agreement Between Issuer and Resource Server

Development teams often need to carry domain-specific data in JWTs:

~~~json
{
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER", "ORDER_EDITOR"],
  "permissions": ["order:read", "order:edit"],
  "department_code": "SALES"
}
~~~

Names like **tenant_id**, **roles**, **permissions**, and **department_code** can act as **private claim names** when parties agree on them privately without registration or collision-resistant naming. They are convenient within a system managed by one team, yet come with limitations:

- **No automatically uniform data types or semantics.** One issuer might emit **roles** as an array of strings, while another uses a space-delimited string or nested object.
- **Name collisions.** Two products can both define **tenant_id** with incompatible meanings of what a tenant is.
- **Not automatically tied to access rights.** A claim **roles: ["ADMIN"]** does not mean the user administers every API; you must define which application, tenant, and scope ADMIN applies to.
- **Not automatically confidential.** Signed JWT payloads can be decoded; never put overly sensitive data into claims.
- **Can become stale before the token expires.** If roles or tenant membership change between token issuances, an active Access Token can carry outdated permissions unless the architecture supports updates or revocation controls.

Private claim names should be documented as a **contract** between the Authorization Server and Resource Server. At a minimum, specify name, JSON type, value domain, missing/null behavior, authorized issuer, validation policy, freshness window, and versioning strategy when semantics change.

### 5.1. Why Not Let Clients Send Claims Directly for the API to Trust?

The following HTTP request does **not** grant admin privileges:

~~~http
GET /api/admin/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
X-User-Role: ADMIN
~~~

The **X-User-Role** header sent arbitrarily by a client is not a claim protected by the Authorization Server's signature. If the API requires roles, it must derive them from the **verified Access Token** or another trusted policy source, while validating against the actual target resource and tenant.

Even when a role appears inside a validly signed JWT, the API must still verify **the token is meant for this API**, **the issuer is trusted**, and **the role's semantics** match the agreement between issuer and API.

## 6. Distinguishing Claims in OIDC ID Tokens vs. OAuth 2.0 Access Tokens

A common pitfall in **JWT and JOSE** is thinking a JWT carries a self-evident "for login" or "for API" label just because it contains **sub** and **email**. You must inspect the **token profile**, **audience**, and issuance purpose.

### 6.1. OIDC Client ID Token

Illustrative ID Token payload:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1893452400,
  "exp": 1893456000,
  "auth_time": 1893452000,
  "nonce": "nonce-created-by-client",
  "email": "user@example.test",
  "email_verified": true
}
~~~

An OIDC Client uses the ID Token to process login results under OIDC rules, including verifying signature, issuer, audience, lifetime, and **nonce** when required. Profile fields like email may appear depending on scopes, claims requests, and provider policies.

**email_verified: true** only reflects email verification status according to the issuer; **it is not an API access permission**. **sub** is a more reliable identifier than email for account linking within an issuer's context.

### 6.2. JWT Access Token for Resource Servers

Illustrative JWT Access Token payload:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "jti": "access-6a45d9",
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42"
}
~~~

The **orders-api** verifies the Access Token and allows only actions permitted by scope, tenant, and policies. In many systems, Spring Security automatically maps scopes from **scope** or **scp** into authorities prefixed with **SCOPE_**, such as **SCOPE_orders.read**. Spring Security does **not** automatically understand what permissions custom claims like **tenant_id**, **roles**, or **permissions** should grant unless the application defines explicit rules.

**Two tokens can share the same issuer and `sub` while having different audiences.** Never send an ID Token in **Authorization: Bearer** in place of an Access Token; the Resource Server must verify the JWT was issued for the resource it protects. Specific profiles may also require checking **typ**, such as **at+jwt** in RFC 9068; this field resides in the JOSE Header, not the payload.

### 6.3. Common Claim Names and How to Read Them Properly

| Claim | Typical meaning | Key points to remember |
| --- | --- | --- |
| **scope** | OAuth 2.0 permission list, commonly a space-separated string. | Not one of RFC 7519's seven core registered claims; semantics depend on issuance profile. |
| **scp** | A scope representation used by some providers. | Check the issuer's schema; do not assume the type always matches **scope**. |
| **client_id** | Client issued the token under the applicable profile. | Can help identify the client, but does not replace the Resource Server's **aud**. |
| **azp** | Authorized party in OIDC, used when an ID Token involves multiple audiences. | Never swap with **aud** or infer API permissions from it. |
| **auth_time** | Time when the user authenticated at the OpenID Provider. | Distinct from **iat**, which is when the token was issued. |
| **nonce** | Value binding an OIDC login result to the client's authentication request. | Not an access scope, and does not perform API replay protection by itself. |
| **email** / **email_verified** | User identity metadata under OIDC. | Do not infer roles/permissions; minimize personal data in Access Tokens. |
| **roles** / **permissions** | System-defined roles or permissions. | May be private claims; require an explicit contract and mapping. |
| **tenant_id** | Application tenant associated with the token. | Must validate consistency between token and target resource, not just read for display. |

## 7. Validating Claims in Spring Security Resource Server

In Spring Security Servlet, **oauth2ResourceServer().jwt()** uses Bearer authentication and **JwtDecoder**. A Resource Server requires a validation pipeline:

~~~text
HTTP Authorization: Bearer ...
               |
               v
      BearerTokenAuthenticationFilter
               |
               v
         JWT verification
   - Valid signature / key / algorithm
   - Valid time window
   - Valid issuer
   - Audience targeting the API
   - Profile claim rules
               |
               v
       JwtAuthenticationToken
               |
               v
       Authorization rules
   - Scope/authority matches operation
   - Tenant and resource permissions
   - Other business policies
               |
        +------+------+
        |             |
      Allow         Deny
~~~

### 7.1. Configuring Issuer and Audience

Spring Boot example for JWT Access Tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
          audiences:
            - orders-api
~~~

On Spring Boot versions supporting **audiences**, this configuration requires the JWT's **aud** to include **orders-api**. If your project uses a version without that property or needs custom rules, declare a **JwtDecoder** with a dedicated validator.

Java example using a decoder with an added audience validator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtClaimValidationConfig {

    private static final String ISSUER =
        "https://idp.example.test/realms/training";
    private static final String API_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT is not intended for this resource server",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

**JwtValidators.createDefaultWithIssuer** preserves standard issuer and timestamp checks. The custom validator adds the audience requirement. This example uses illustrative constants; real applications should load issuer and audience from environment-managed configuration while also enforcing JWT algorithm/signature policies.

If a project sets both the **audiences** property and a custom decoder bean, note that **a custom bean can override auto-configuration**. Verify that audience validation actually runs in the active decoder; never assume declaring YAML alone applies to every custom decoder.

### 7.2. Checking Data Types and Semantics of Private Claims

In a multi-tenant API, for example:

~~~json
{
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER"]
}
~~~

The Resource Server must verify:

- Is **tenant_id** a string? Is it empty or null?
- Does **tenant_id** fall within the authenticated principal's permitted scope?
- Which tenant does the URL **/api/tenants/{tenantId}/orders** target? Does the token authorize access to that tenant?
- Is **roles** an array of strings or another format? Was the role issued by this issuer for this application?

Example controller reading claims from a JWT **already authenticated by Spring Security**:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@RestController
@RequestMapping("/api/tenants")
public class TenantOrderController {

    @GetMapping("/{tenantId}/orders")
    Map<String, Object> orders(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant_id");
        if (tokenTenant == null || !tokenTenant.equals(tenantId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        // Must still enforce scope/permission in SecurityFilterChain
        // and data-level permissions in the business layer as needed.
        return Map.of("tenantId", tenantId, "orders", new String[0]);
    }
}
~~~

This is a **basic tenant comparison** example, not a full multi-tenant design. In real applications, tenant checks must generally align with resource ownership and authorization policies; never allow a user to gain access simply by changing a client-supplied **tenant_id** header.

### 7.3. Mapping Scopes to Authorities

Example `SecurityFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/tenants/*/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In standard default configuration, **scope: "orders.read orders.write"** yields authorities **SCOPE_orders.read** and **SCOPE_orders.write**. Authority names must match your actual token profile. Disabling CSRF here illustrates a stateless Bearer-header API that does not use session cookies as credentials; browser apps using cookie authentication need appropriate CSRF protection.

**A private `roles` claim does not automatically become `ROLE_...`.** To use **roles**, configure a **JwtAuthenticationConverter** or enforce roles via another authorization model. Never replace data-level authorization with a generic role check.

### 7.4. Explicitly Mapping Custom Roles

Example where an API has a contract defining **roles** as an array of role names (without the **ROLE_** prefix):

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public class CustomJwtAuthorities {

    public static Converter<Jwt, AbstractAuthenticationToken> converter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        return jwt -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    if ("ORDER_READER".equals(role) ||
                        "ORDER_EDITOR".equals(role)) {
                        authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }
            return new JwtAuthenticationToken(
                jwt, authorities, jwt.getSubject());
        };
    }
}
~~~

In the previous `SecurityFilterChain`, you can replace:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(jwt -> jwt.jwtAuthenticationConverter(
        CustomJwtAuthorities.converter())))
~~~

This snippet is part of the **HttpSecurity configuration DSL**, not a standalone Java program. This keeps default scope authorities intact and maps only roles explicitly recognized by the application. When using **hasRole("ORDER_READER")**, Spring Security matches the **ROLE_ORDER_READER** authority. Keep role conventions unambiguous: avoid granting broad privileges from a bare **ADMIN** string without scoping to service or tenant.

## 8. Designing Safe and Maintainable Claim Schemas

### 8.1. Specify Name, Type, and Issuing Source

Before adding a new claim to an Access Token, answer:

1. **Who owns the name?** Is the claim internal or shared across organizations? Does it need a collision-resistant namespace?
2. **What is the JSON type?** String, number, boolean, array, or object? A claim name must keep a consistent type across token versions.
3. **What do the values mean?** For instance, does a role apply to an app, tenant, resource, or entire organization?
4. **Who is permitted to set the claim?** Claims must be assigned by the Authorization Server or trusted source and protected via the appropriate token mechanism.
5. **Is the claim required or optional?** If missing or wrong-typed, should the API accept or reject? Define the rule upfront.
6. **Can the information change rapidly?** Roles, permissions, and tenant membership can go stale before the token expires.
7. **Is the data sensitive?** Tokens should not carry unnecessary personal data or secrets.
8. **Will the schema evolve later?** Define compatibility and versioning strategies for both producers and consumers.

### 8.2. Do Not Use Claims as a Database

Because JWTs can be verified locally by a Resource Server, it is tempting to pack extensive data into tokens. Overly large claims or excessive personal data cause:

- Larger HTTP headers on every request.
- Greater exposure when tokens are copied, logged, or sent to the wrong audience.
- Stale authorization state when roles or tenant memberships change.
- Conflicting sources of truth across contexts.

Keep JWTs lean with just enough data for authentication and designed authorization decisions. For fresh or sensitive business data, query an authoritative source after authentication.

### 8.3. Avoid Conflicts Across Issuers and Profiles

Suppose two issuers both send:

~~~json
{
  "roles": ["ADMIN"]
}
~~~

One system may treat **ADMIN** as order administrator; another treats it as full account administrator. If a Resource Server trusts multiple issuers, it cannot simply "merge roles" while ignoring **issuer, audience, and per-issuer mapping contracts**.

A clean strategy:

- For **registered claims**, follow exact RFC and profile semantics.
- For standard claims defined by OIDC or the JWT Access Token profile, follow profile requirements strictly.
- For claims shared across organizations, prefer registered names or collision-resistant namespaces.
- For internal claims, define explicit contracts and mappings per issuer, tenant, and resource.

### 8.4. Never Trust Payloads Before Verification

The following payload can be created with any JSON editor:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "attacker",
  "aud": "orders-api",
  "scope": "orders.admin",
  "roles": ["ADMIN"]
}
~~~

Without a valid signature and lifetime constraints, this payload is **no proof of authorization from the Authorization Server**. The API must rely on a properly configured `JwtDecoder`/validator and never manually Base64url-decode and trust claims. Even the token's **alg** header is no guarantee; the verifier must control allowed algorithms and trusted keys.

When using multiple JWT types (ID Tokens, Access Tokens, internal tokens), enforce rules against **cross-JWT confusion**: require the appropriate audience, issuer, and token profile/type per endpoint type to avoid accepting tokens meant for a different purpose.

## 9. Example: Analyzing a JWT When Troubleshooting 401/403 Errors

Suppose the **orders-api** Resource Server receives a validly signed JWT. Inspecting the claims:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

The token has **scope: orders.read**, yet **aud** contains only **inventory-api**. **orders-api must reject the token** because it is not intended for this API. Having the right scope does not fix a wrong audience.

With a second token:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

If signature, issuer, and timestamps are valid at request time, the token passes authentication. Yet if the URL is **/api/tenants/tenant-99/orders**, the API must deny access under tenant constraints and resource permissions; having a read scope does not grant access to any arbitrary tenant.

For a third token:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "profile.read",
  "tenant_id": "tenant-42"
}
~~~

This token can authenticate validly yet **lacks the `orders.read` scope**, so the read-orders request is blocked at authorization. In standard API setups, **missing or invalid tokens** yield **401 Unauthorized**, whereas **valid tokens with insufficient permissions** yield **403 Forbidden**.

These examples are illustrative payloads. Never paste real JWTs into tickets, logs, or public online tools for debugging: **a Bearer Token is a sensitive credential** even when its payload is readable.

## 10. Misconceptions to Avoid

| Misconception | Accurate understanding |
| --- | --- |
| "Registered claims are always mandatory." | The names have standardized semantics; whether they are required depends on the token profile and application. |
| "Public claims contain public data." | Public/private describes the **naming** mechanism, not the secrecy of the **values**. |
| "Private claims are encrypted." | No; private claims are simply names agreed between parties. JWS JWT payloads are readable. |
| "A JWT with `sub` and `email` is an ID Token." | Those claims do not uniquely determine purpose. Check token profile and audience. |
| "A JWT with the right `aud` is allowed to do everything." | Audience identifies the intended recipient; scopes/roles and resource checks are still required. |
| "Having `jti` prevents replay." | Replay protection requires stateful tracking/validation of `jti` and a single-use policy. |
| "`iat` is when the token expires." | **iat** is issued-at time; **exp** is expiration time. |
| "`scope` and `roles` are always the same." | OAuth scopes and business roles can differ in issuing source, naming, scope, and enforcement. |
| "Spring Security automatically understands all custom claims." | Default mapping covers only select claims like scope; private claims need explicit contracts, validators, and authorization. |
| "Just decoding a JWT yields trusted permissions." | You must verify signature, issuer, audience, lifetime, profile, and API permissions. |

## 11. Practice Exercise: Identifying Claims

Read the following JWT Claims Set:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "worker-7",
  "aud": ["billing-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "jti": "billing-2026-001",
  "scope": "invoices.read",
  "https://claims.example.test/region": "apac",
  "cost_center": "FIN-01",
  "roles": ["BILLING_READER"]
}
~~~

**Questions:**

1. Which fields belong to RFC 7519's seven registered claims?
2. Which field illustrates a collision-resistant namespaced **public claim name**?
3. Which fields illustrate system-defined **private claims**?
4. If **orders-api** receives this token, looking only at audience, how should it respond?
5. Does **jti** guarantee a Bearer Access Token can only be used once?

**Suggested answers:** (1) **iss**, **sub**, **aud**, **exp**, **iat**, **jti**; (2) **https://claims.example.test/region**; (3) **cost_center** and **roles**; **scope** is a claim name defined in OAuth/JWT Access Token profile contexts rather than one of the seven core registered claims; (4) **orders-api** must reject a token that lacks its audience; (5) **no**, preventing replay requires additional tracking mechanisms and control policies.

## 12. Takeaways

The three JWT claim categories distinguish **origin and naming conventions**:

1. **Registered claims** carry standard semantics in RFC 7519: **iss**, **sub**, **aud**, **exp**, **nbf**, **iat**, **jti**.
2. **Public claims** should be registered or use collision-resistant namespaces so multiple systems share the same meaning.
3. **Private claims** are agreed upon directly between parties; useful for business context, provided there are clear contracts and mappings.

With **Spring Security Resource Server**, enforce both **token validation** (signature, issuer, audience, lifetime, token profile) and **authorization** (scopes, roles, tenant, resource permissions). Never skip either stage simply because a JWT contains rich claims.

## References

- [RFC 7519 — JSON Web Token (JWT), Section 4: JWT Claims](https://www.rfc-editor.org/rfc/rfc7519#section-4).
- [IANA — JSON Web Token (JWT) Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml).
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
