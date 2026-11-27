# Scope, Claim, Audience, Resource, and Subject in OAuth 2.0 / OpenID Connect

## 1. Objectives and Context

In systems using **Spring Security** and **Spring Authorization Server**, the five concepts **scope**, **claim**, **audience**, **resource**, and **subject** appear together when a client requests a token, the Authorization Server issues a token, and the Resource Server validates a token. They answer different questions:

| Concept | Primary question | Example in an order management system |
| --- | --- | --- |
| **Scope** | Which **access boundaries** was the client granted? | <code>orders.read</code> |
| **Claim** | What **statement** is the token or identity source asserting? | <code>sub</code>, <code>iss</code>, <code>aud</code>, <code>email</code> |
| **Audience** | Who is the token **intended for**? | <code>https://orders.api.example.com</code> |
| **Resource** | Which **resource/API** does the client want to access? | Orders API, or a specific order |
| **Subject** | Which **principal** is the token about? | <code>user-42</code>, or a service client |

After this lesson, you should be able to read an OAuth 2.0/OIDC request and JWT, distinguish these five concepts, decide where each piece of information should be validated, configure a simple example with Spring Authorization Server and Spring Security Resource Server, and recognize common authorization mistakes.

**Running scenario:** User Alice logs into the <code>orders-web</code> application; the application calls the Orders API to read orders. The Authorization Server issues an access token. The Orders API accepts only tokens with the expected issuer, appropriate audience, and <code>orders.read</code> scope; the API further verifies whether Alice is permitted to view the requested order.

~~~mermaid
sequenceDiagram
    participant U as Alice (Subject)
    participant C as orders-web (Client)
    participant AS as Authorization Server
    participant API as Orders API (Resource Server)
    U->>C: Request to view order
    C->>AS: Authorization Code + PKCE; scope=openid orders.read
    AS->>U: Authenticate, apply consent/policy
    AS-->>C: Authorization code
    C->>AS: Exchange code for token with code_verifier
    AS-->>C: Access token (sub, aud, scope...)
    C->>API: GET /api/orders/123 + Bearer access token
    API->>API: Validate signature, iss, expiration, aud, scope
    API->>API: Check whether Alice has access to order 123
    API-->>C: Data or 401/403 error
~~~

Key takeaway from the start: **scope is granted permission, audience restricts where the token can be used, subject identifies the principal, claim represents an assertion, and resource is the target resource/API**. In a JWT, <code>aud</code>, <code>sub</code>, and sometimes <code>scope</code> are all stored as *claims*; these are different perspectives, not five mutually exclusive field types.

## 2. Scope: Access Boundaries Granted to the Client

### 2.1. Scope in OAuth 2.0

In OAuth 2.0, <code>scope</code> is a list of strings representing **access boundaries** requested by the client and potentially granted by the Authorization Server. Scope strings have system-defined semantics. For example:

| Scope | System-defined meaning |
| --- | --- |
| <code>orders.read</code> | Read permitted order data |
| <code>orders.write</code> | Perform permitted order modifications |
| <code>inventory.read</code> | Read inventory |
| <code>openid</code> | Request an **OpenID Connect** authentication flow |
| <code>profile</code> / <code>email</code> | OIDC scopes indicating groups of identity attributes that may be provided |

In a request, multiple scopes are separated by **spaces** and must be properly encoded in forms/URLs, e.g. <code>scope=openid%20profile%20orders.read</code>. Names like <code>orders.read</code> are not constants that Spring inherently understands: the development team must agree on their meaning, register allowed scopes, and enforce policies at the API.

Distinguish three stages:

1. **Requested scopes:** The client sends desired permissions, e.g. <code>orders.read orders.write</code>.
2. **Authorized/granted scopes:** The Authorization Server applies client registration, user, consent, and policies; it might grant only <code>orders.read</code>.
3. **Enforced scopes:** The Resource Server checks the scopes **actually present in the token or introspection response**, then applies business authorization.

Never assume all requested scopes were granted. User consent also does not replace API-side policies.

### 2.2. Scope Differs from Role, Permission, and Object-Level Access

Scope usually expresses permissions **delegated to a client/token**; a role like <code>ROLE_ADMIN</code> describes an application role; a permission is how the system interprets a specific capability. You can map between them, but should not treat them as identical.

For example, a token containing <code>orders.read</code> only proves that the client can request order-reading operations. If Alice calls <code>GET /api/orders/123</code>, the API must still verify whether order 123 belongs to Alice's organization or was shared with Alice. Skipping this check leaves the system vulnerable to **Broken Object Level Authorization (BOLA/IDOR)**.

With Spring Security Resource Server, a JWT with an appropriate <code>scope</code> or <code>scp</code> claim is typically converted into authorities like <code>SCOPE_orders.read</code>. This authority supports endpoint-level checks, while data ownership rules should be enforced in the service/domain layer.

### 2.3. An OIDC Scope Does Not Guarantee a Claim Will Be Present

<code>openid</code> turns an authentication request into an OIDC request and allows the client to receive an **ID Token** via the appropriate flow. <code>profile</code> and <code>email</code> relate to identity attribute groups, but what data is actually issued depends on the user, configuration, consent, and provider policy. Do not assume that requesting <code>email</code> guarantees every access token will always contain an <code>email</code> claim.

## 3. Claim: Statements Asserted About a Token or Principal

A **claim** is a name–value pair representing an assertion, such as <code>"sub": "user-42"</code>. A JWT consists of a header, a payload containing claims, and a signature (for signed JWTs); claims are not inherently trustworthy merely because they can be decoded from a JWT string. The recipient must verify the signature and all token acceptance conditions.

| Claim | Common purpose | Security notes |
| --- | --- | --- |
| <code>iss</code> | Issuer: issuing party | Match against configured trusted issuer |
| <code>sub</code> | Subject: principal identifier | Do not assume it is an email, username, or global user ID |
| <code>aud</code> | Audience: intended recipient | Must match the inspecting application/API |
| <code>exp</code>, <code>nbf</code>, <code>iat</code> | Expiration, not before, issued at | Enforce validity windows with reasonable clock skew |
| <code>jti</code> | Token identifier | Useful for tracking/replay protection depending on design; does not guarantee revocation by itself |
| <code>scope</code> | Granted scopes when represented by the AS in the token | Does not equate to roles or per-object ownership |
| <code>email</code>, <code>email_verified</code> | OIDC identity attributes | Use only after source verification, context checks, and suitability verification |
| <code>tenant_id</code> | Custom claim in multi-tenant systems | Cross-check against data access rights; never trust client-supplied values |

Claims are categorized into **registered claims** in the JWT standard, **public claims** with standardized names, and **private/custom claims** agreed upon by parties. OIDC also defines a set of **standard claims** for End-User information, such as <code>name</code>, <code>preferred_username</code>, and <code>email</code>. Not every claim is required in every token.

### 3.1. Do Not Confuse Claims in an ID Token with Claims in an Access Token

| Property | ID Token (OIDC) | Access token (OAuth 2.0) |
| --- | --- | --- |
| Purpose | Client verifies the authentication event and End-User identity | Client presents to Resource Server to access APIs |
| Primary recipient | OIDC Client; <code>aud</code> must include <code>client_id</code> | Resource Server/API; audience depends on format, configuration, and profile |
| <code>sub</code> | End-User identifier at the issuer | Token subject per grant/profile; may be an End-User or a client |
| Scope | Not a required field of an ID Token | Typically appears in JWT access token contents or introspection results |
| Usage | Establishes a login session on the client | Sent as <code>Authorization: Bearer ...</code> to APIs |

**Do not use an ID Token as an access token to call APIs.** A validly signed ID Token still has the client as its audience, not the Orders API. Furthermore, an access token may be an opaque string; the client must not rely on decoding its payload.

An example *abbreviated payload* of a JWT access token (omitting time claims and header to focus on concepts):

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["https://orders.api.example.com"],
  "scope": "orders.read",
  "client_id": "orders-web"
}
~~~

An example *abbreviated payload* of an ID Token issued for the same login session:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-web",
  "email": "alice@example.com",
  "email_verified": true
}
~~~

The two payloads above only illustrate **how audience and subject are set**; real tokens must include additional claims required by the standard/profile, such as <code>exp</code> and <code>iat</code> in an ID Token, and must be fully validated. <code>email</code> is merely one attribute that may be issued when policy allows.

### 3.2. Trustworthiness and Data Minimization

A validly signed JWT indicates that the payload was attested by the holder of the signing key and has not been tampered with; it **does not automatically** prove the contents satisfy every application policy. The Resource Server must still evaluate issuer, audience, lifetime, token type, scope, and business permissions. JWT payloads are Base64URL-encoded, **not encrypted** by default, so avoid placing passwords, sensitive secrets, or unnecessary personal data inside access tokens.

OIDC also supports the <code>claims</code> request parameter for a client to specify which claims it wants to receive. That is a mechanism for **requesting identity attributes**, distinct from the <code>scope</code> parameter requesting access boundaries. Requesting a claim does not mean the AS is obligated to provide it in all circumstances.

## 4. Audience: Ensuring Tokens Reach the Right Recipient

**Audience** refers to one or more parties for whom the token is intended. In JWT, the <code>aud</code> claim can be a string or an array of strings per RFC 7519. A JWT recipient must verify that the token is intended for it before using it.

In our example:

- <code>aud = orders-web</code> on the **ID Token**: OIDC Client <code>orders-web</code> is the recipient.
- <code>aud = https://orders.api.example.com</code> on the **access token**: the Orders API is the recipient by system convention.
- A Billing API with audience <code>https://billing.api.example.com</code> must reject an access token intended only for the Orders API, even when the JWT has a valid signature and a trusted issuer.

Standards do not mandate that every OAuth 2.0 access token be a JWT containing <code>aud</code>. However, when adopting the **RFC 9068 JWT access token profile**, audience is a mandatory part of the design and the Resource Server must verify it. For opaque tokens, the Resource Server typically uses **token introspection** or an equivalent server-side mechanism to retrieve granted attributes, then enforces audience/resource restrictions accordingly.

Why is audience validation critical? Suppose two APIs trust the same Authorization Server. If they only check the signature and <code>iss</code>, the Billing API could mistakenly accept a token issued for the Orders API. That is a **token substitution / confused deputy** flaw: a valid token used at the wrong target.

**Audience and scope are two independent checks.** A token with scope <code>orders.read</code> whose audience is the Billing API must not be accepted at the Orders API; a token with the right audience but missing <code>orders.read</code> is likewise not allowed to read orders.

## 5. Resource: Protected Resources and the <code>resource</code> Parameter

The word *resource* has at least three usages depending on context:

1. **Protected resource:** the data or operation being protected, such as order #123.
2. **Resource Server:** the service hosting/exposing protected resources, such as the Orders API.
3. **Resource indicator:** an OAuth 2.0 URI identifier allowing the client to indicate which resource the token will be used at, per **RFC 8707**.

Do not use a specific data path like <code>/api/orders/123</code> as the audience for every token if your design applies audience at the API level. In that case, a stable resource indicator could be <code>https://orders.api.example.com</code>, while permission to access order 123 is a business-level check.

### 5.1. Distinguishing the <code>resource</code> Parameter and the <code>aud</code> Claim

| | <code>resource</code> | <code>aud</code> |
| --- | --- | --- |
| Where does it appear? | In authorization/token requests per RFC 8707, when supported by the AS | In the JWT issued by the AS |
| Who specifies the value? | The client requests the target resource | The Authorization Server determines the token contents |
| Meaning | "I need a token for this API" | "This token is intended for this recipient" |
| Immediately trustworthy? | No; the AS must verify the client is allowed to request that resource | The Resource Server trusts it only after full token validation |

Example of a client requesting an access token for the Orders API:

~~~http
GET /oauth2/authorize?response_type=code&client_id=orders-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback
    &scope=openid%20orders.read
    &resource=https%3A%2F%2Forders.api.example.com
    &state=opaque-state
    &code_challenge=base64url-challenge
    &code_challenge_method=S256
~~~

This is a **protocol** example; line breaks are for readability only. The <code>state</code> and <code>code_challenge</code> values are illustrative and must be properly generated and validated in a real implementation.

**Spring Authorization Server note:** Do not assume that merely having the client send <code>resource</code> causes the framework to automatically handle RFC 8707 and populate <code>aud</code> from the requested resource. When resource indicators are needed, verify the level of support in your version and add request validation, allowed-resource lists, authorization context storage, and appropriate token issuance logic. Never copy a client-supplied URI directly into <code>aud</code> without validation.

An architecture with multiple APIs should generally issue **audience-restricted tokens** separately for each API. If a token carries multiple audiences, each API might inadvertently accept broader privileges than intended; only do so after evaluating the specific trust and access model.

## 6. Subject: Who or What Entity Is the Token About?

**Subject** is usually represented by the <code>sub</code> claim, an identifier **unique within the issuer's scope** per the issuer's rules. You can use the composite key <code>(iss, sub)</code> when correlating users across multiple systems; never assume <code>sub</code> is a globally unique ID. In OIDC, <code>sub</code> is the End-User identifier, which can be *public* or *pairwise* depending on provider configuration.

Do not confuse four roles:

| Role | In the example | Meaning |
| --- | --- | --- |
| Resource Owner / End-User | Alice | The person whose data access is authorized/authenticated |
| Client | <code>orders-web</code> | The application requesting tokens and calling the API |
| Subject | <code>user-42</code> | The principal identified by the <code>sub</code> claim |
| Resource Server | Orders API | The service validating tokens and enforcing resource permissions |

With **Authorization Code + PKCE**, the access token can represent user Alice as the subject; the API can use the subject to look up Alice's permissions. However, with **Client Credentials**, there is usually **no End-User**: the token represents the client/service. In the RFC 9068 JWT access token profile, when there is no resource owner, <code>sub</code> represents the client. Do not write logic assuming "every <code>sub</code> is a user ID" across all grant types.

If your system has a service calling an API on behalf of a user, explicitly design whether the token represents the user, the client, or an intermediary actor. Token exchange/delegation mechanisms can represent an additional actor, rather than inferring it from <code>sub</code> alone.

**Do not use email in place of subject**: emails can change, collide in unintended data scopes, or remain unverified. Enforce permissions based on a stable identifier combined with issuer/tenant when appropriate.

## 7. Combining All Five Concepts in One Transaction

Suppose the AS issues an access token for <code>orders-web</code> after Alice logs in:

~~~text
Client          = orders-web
Subject         = (https://auth.example.com, user-42)
Requested scope = openid orders.read
Granted scope   = orders.read (+ openid in OIDC context)
Resource        = https://orders.api.example.com
Access token aud= https://orders.api.example.com
Access token sub= user-42
~~~

To handle <code>GET /api/orders/123</code>, the Orders API passes through multiple decision layers:

~~~mermaid
flowchart TD
    A["Receive Bearer access token"] --> B{"Signature / format / issuer / lifetime valid?"}
    B -- No --> U["401 Unauthorized"]
    B -- Yes --> C{"Audience contains Orders API?"}
    C -- No --> U
    C -- Yes --> D{"Has orders.read scope?"}
    D -- No --> F["403 Forbidden"]
    D -- Yes --> E{"Subject permitted to view order 123?"}
    E -- No --> F
    E -- Yes --> G["200 OK: return permitted data"]
~~~

The diagram is a **security verification model**; actual HTTP status codes depend on how the API represents authentication errors, policies, and resource hiding. By default in Spring Security, invalid tokens typically return 401, while an authenticated principal lacking an authority typically returns 403.

A common mistake is checking <code>scope</code> solely on the client and then allowing API calls. Security decisions must be enforced again **on the Resource Server side**; what the client UI displays only improves user experience.

## 8. Applying This in Spring Authorization Server and Spring Security

The following snippets illustrate configuring a **JWT access token for a fixed API**. They assume the Spring Boot project has already set up Authorization Server, client repository, JWT/JWK signing keys, and OIDC per the relevant documentation. Examples focus on this lesson's five concepts; packages/imports are omitted.

### 8.1. Defining Requestable Scopes

Register the client with allowed scopes (excerpt of creating a <code>RegisteredClient</code>):

~~~java
RegisteredClient ordersClient = RegisteredClient.withId(clientInternalId)
    .clientId("orders-web")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://app.example.com/callback")
    .scope(OidcScopes.OPENID)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

This client is permitted to request <code>openid</code> and <code>orders.read</code>, not arbitrary scopes supplied by the client. This is an example of a **public client using Authorization Code + PKCE**; for a BFF/confidential client, choose the corresponding client authentication method and protect secrets/keys. Issuance/grant policies and other OIDC components of the Authorization Server must be configured before running the full flow.

### 8.2. Attaching a Controlled Audience to a JWT Access Token

For the simple case of **one client dedicated to one API**, you can map the registered client to a fixed audience using <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code>:

~~~java
@Configuration
class AccessTokenAudienceConfiguration {
    private static final String ORDERS_API =
        "https://orders.api.example.com";

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenAudience() {
        return context -> {
            // Do not modify aud of an ID Token or other token types.
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            // Only map the permitted client to the configured resource.
            if ("orders-web".equals(context.getRegisteredClient().getClientId())) {
                context.getClaims().audience(List.of(ORDERS_API));
            }
        };
    }
}
~~~

This mapping condition is a **fixed configuration example**, not a complete RFC 8707 handler. In real products, design a **client ↔ resource ↔ scope** permission table, validate the client's requested resource, handle scope downscoping, and reject inappropriate requests before issuing tokens. If a client can access multiple APIs, never naively infer audience from a single scope or copy an unvalidated <code>resource</code> parameter verbatim. Avoid adding sensitive custom claims unless the Resource Server genuinely requires them.

Spring Authorization Server can issue access tokens in **self-contained (JWT)** or **reference/opaque** format depending on <code>TokenSettings</code>. <code>JwtEncodingContext</code> applies when issuing JWTs; if using opaque tokens, use the corresponding claims/introspection mechanism (such as an opaque-token customizer), and do not expect the code above to run on non-JWT tokens.

### 8.3. Resource Server Verifying Audience and Scope

The Orders API uses Spring Security Resource Server to verify JWTs. The example below accepts only a trusted issuer, the Orders API audience, and the <code>SCOPE_orders.read</code> authority on the order-reading endpoint:

~~~java
@Configuration
@EnableWebSecurity
class OrdersResourceServerSecurity {
    private static final String ISSUER = "https://auth.example.com";
    private static final String ORDERS_AUDIENCE =
        "https://orders.api.example.com";

    @Bean
    SecurityFilterChain ordersSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(ISSUER + "/oauth2/jwks")
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(ORDERS_AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Token is not intended for Orders API", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

Explanation of each control point:

1. <code>withJwkSetUri</code> supplies the public key source for signature verification; this URL must genuinely belong to a trusted Authorization Server. In real systems, control allowed signing algorithms and key rotation procedures.
2. <code>createDefaultWithIssuer</code> validates the issuer and default temporal conditions, including token expiration.
3. The custom validator forces <code>aud</code> to contain **the exact resource identifier** of the Orders API.
4. Spring Security converts matching scopes into authorities prefixed with <code>SCOPE_</code> under default configuration; the rule above checks <code>orders.read</code>.
5. The order-processing service must still verify whether <code>sub</code> (with issuer/tenant as needed) has access to each individual order. **Scope and audience do not automatically check ownership.**

This is an illustrative configuration for HTTP Servlet endpoints and JWTs. Systems must separately address other HTTP methods/endpoints, CSRF/session per architecture, error handling, and validating the expected access token type. If adopting **RFC 9068**, verify all related profile requirements, not only <code>iss</code> and <code>aud</code>. If using opaque tokens, replace the JWT decoder mechanism with introspection and an appropriate audience policy.

### 8.4. Do Not Arbitrarily Modify <code>sub</code>

The <code>sub</code> of an ID Token must reflect the OIDC issuer's End-User identification policy. For an access token, the source of subject depends on the grant and token profile. Inside a token customizer, never set <code>sub</code> from a <code>userId</code> supplied by an HTTP client; if specialized identification is needed, map it from a trusted authentication and a designed subject model, and test consistency across grant flows.

## 9. Required Test Cases

| Case | Input | Expected outcome |
| --- | --- | --- |
| Valid | JWT issued by trusted AS; right audience, unexpired, has <code>orders.read</code>; Alice is allowed to view the order | Permitted |
| Wrong audience | Token for Billing API sent to Orders API | Token validation rejected, typically 401 |
| Missing scope | Right audience but lacks <code>orders.read</code> | Read access denied, typically 403 |
| Wrong issuer/signature | Tampered token or issued by untrusted issuer | 401 |
| Expired | <code>exp</code> is in the past | 401 |
| Wrong owner | Right audience and scope, but Alice has no permission for the order | 403 (or appropriate hiding policy) |
| Using ID Token to call API | <code>aud</code> contains <code>orders-web</code> instead of Orders API | Not accepted as an access token |
| Client Credentials | Token subject is a service, no End-User | Apply service-to-service policy; do not infer Alice |
| Requesting disallowed resource | Client requests Billing API despite only being registered for Orders API | AS rejects request or downscopes per policy; never issues a wrong-audience token |

You should have **real integration tests exercising the JWT decoder/validator** for wrong issuer, wrong audience, invalid signature, and expiration cases. In Spring Security Test, the <code>jwt()</code> helper typically builds a mocked Authentication and **bypasses** the decoder's signature/audience validation, so use it only for testing authorization rules—not as proof that token validation was tested.

## 10. Misconceptions and Corrections

| Misconception | Correct understanding |
| --- | --- |
| "Having the scope grants access to every object." | Scope is only a coarse permission layer; per-resource authorization must still be checked. |
| "Any validly signed token works on any API." | Each API must check audience, issuer, expiration, and applicable token conditions. |
| "<code>aud</code> is the client ID in every token type." | For ID Tokens, audience includes the client ID; for API access tokens, audience is typically the Resource Server. |
| "<code>resource</code> and <code>aud</code> are always identical." | <code>resource</code> is the request/target identifier; the AS determines audience after validation and mapping. |
| "<code>sub</code> is always an email/user." | Subject is an identifier scoped by issuer and grant; client credentials may represent a service. |
| "The <code>email</code> scope guarantees the access token contains email." | OIDC scopes and claim issuance depend on token type, consent, and policy. |
| "Decoding the JWT is enough." | You must verify signature, required claims, issuer, audience, timestamps, and permissions. |
| "An ID Token can be used with a Resource Server." | ID Tokens are for OIDC Clients; APIs require an access token issued for that API. |
| "Spring Authorization Server automatically handles every <code>resource</code> request." | Check version support and implement any missing extensions yourself. |

## 11. Practice Exercise

Design a system with <code>catalog-web</code>, a Catalog API, and a Billing API sharing one Authorization Server.

1. Propose dedicated scopes for reading products and viewing invoices, and choose stable resource identifiers for both APIs.
2. Explain why a token having <code>catalog.read</code> with <code>aud=Catalog API</code> must be rejected by the Billing API even though both share the same issuer.
3. State the difference between <code>sub</code> in an Authorization Code token when a customer logs in and in a Client Credentials token when a cron job runs.
4. Write the policy for a case where customer A holds the <code>billing.read</code> scope but attempts to read customer B's invoice.
5. List the checks performed at the Resource Server and the checks that must be performed at the Authorization Server when supporting the <code>resource</code> parameter.

A satisfactory design must have **separate checks** for client/token permissions, where the token is allowed to be used, and the subject's permission on the data record.

## 12. Reference Documentation

- [RFC 6749, §3.3 — Access Token Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): access boundaries in OAuth 2.0.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): structure and registered claims such as <code>iss</code>, <code>sub</code>, and <code>aud</code>.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): the <code>resource</code> parameter and resource-restricted tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile requirements for JWT access tokens.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): how a Resource Server retrieves token metadata (especially opaque tokens).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, subject, and standard claims.
- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/): client registration, token customization, and Authorization Server.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification, JWT decoder, authorities, and claim validation.
