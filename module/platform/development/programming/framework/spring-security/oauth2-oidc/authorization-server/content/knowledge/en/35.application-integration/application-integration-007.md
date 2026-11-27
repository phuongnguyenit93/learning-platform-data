# Issuing Audiences and Scopes for Multiple APIs or a Gateway

## 1. The Challenge When One Authorization Server Protects Multiple APIs

In a system with multiple APIs, a single client may need to read orders, create invoices, query inventory, or call an aggregation API behind an API Gateway. If the Authorization Server simply issues one generic access token for all APIs without explicitly defining where the token may be used, a token stolen in one place can be replayed elsewhere.

OAuth 2.0 provides two complementary concepts to constrain permissions:

- **Audience (`aud`)** identifies which Resource Server or group of resources is allowed to accept the access token.
- **Scope (`scope`)** describes what actions or permissions the token represents at that resource.

RFC 8707 adds the **Resource Indicator (`resource`)** so clients can explicitly specify the target resource they intend to access when requesting a token. The Authorization Server evaluates that request against policy and decides the token's actual audience.

This lesson belongs to the **Application Integration** chapter of the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module. It focuses on designing audiences, scopes, and resources for multiple APIs or gateways, along with the required extension points in Spring Authorization Server 1.5.8.

After this lesson, you will be able to:
1. Distinguish between audience, scope, and resource indicator.
2. Design stable audience URIs for each API, gateway, or tenant resource.
3. Name scopes by API and operation to avoid ambiguity.
4. Bind scopes to audiences and client registrations.
5. Customize the `aud` claim in JWT access tokens using `OAuth2TokenCustomizer`.
6. Determine when to support RFC 8707 `resource` and how to store the selected resource in the authorization.
7. Design tokens for direct API calls, gateway routing, or multi-backend architectures.
8. Validate audiences and scopes at each Resource Server.
9. Handle opaque tokens via introspection and manage token lifecycles.
10. Test wrong scopes, wrong audiences, multi-resource requests, and token forwarding.

## 2. Components in the Model

| Component | Responsibility | Example |
| --- | --- | --- |
| **OAuth2 Client** | Requests an access token for the resource to access | `orders-web`, `billing-worker` |
| **Authorization Server (AS)** | Authenticates client/grant, evaluates policies, and issues tokens | Spring Authorization Server |
| **Resource Indicator** | Indicates the target resource in authorization/token requests | `https://api.example.com/orders/` |
| **Audience** | Identifies the recipient authorized by the token | `https://api.example.com/orders/` |
| **Scope** | Describes permissions at the selected resource | `orders.read`, `orders.write` |
| **Resource Server** | Verifies tokens and enforces permissions on APIs | Orders API, Billing API |
| **API Gateway** | Common entry point, verifies tokens, and routes requests | `https://gateway.example.com/` |

An access token can be represented as a JWT or an opaque/reference token. Regardless of format, policy must still determine which resource the token is issued for and what operations it is permitted to perform.

## 3. Distinguishing Audience, Scope, and Resource Indicator

These three concepts often appear in the same flow, yet answer three distinct questions:

| Concept | Question | Example |
| --- | --- | --- |
| `resource` | Where does the client want to use the token? | `https://api.example.com/orders/` |
| `aud` | Which recipient has the AS authorized to accept the token? | `https://api.example.com/orders/` |
| `scope` | What operations does the token permit at that recipient? | `orders.read` |

**Resource is the client's request; audience is the AS's decision.** A client may submit a resource URI, but the AS must verify whether that URI exists, whether the client is allowed to access it, and whether the requested scopes are valid for it. Never blindly copy the `resource` value from the request into the `aud` claim.

Example:

~~~text
resource = https://api.example.com/orders/
aud      = https://api.example.com/orders/
scope    = orders.read orders.write
~~~

The token above is issued for the Orders API and carries two permissions for reading and writing orders. The Billing API must not accept that token merely because it was signed by the same Authorization Server.

A scope should not be used as a substitute for audience. For instance, `orders.read` describes reading orders; it does not specify which host or API the token may be sent to. Conversely, the Orders API audience does not automatically grant permission to read or write orders.

### 3.1. A Valid Token Requires Both Dimensions of Control

The Resource Server must verify:

1. The token was issued by a trusted issuer.
2. The signature and token validity window are valid.
3. The audience contains the exact identifier of this Resource Server itself.
4. Scopes or authorities are sufficient for the endpoint being called.
5. Additional conditions such as tenant, ownership, account state, or business policies are satisfied.

Checking scopes while ignoring audience creates token redirect/replay risk against other APIs. Checking audience while ignoring scopes lets any token targeting that API perform any operation.

## 4. Multi-API and API Gateway Architectures

Three deployment patterns are common.

### 4.1. Client Calling Each API Directly

~~~mermaid
flowchart LR
    C[OAuth2 Client] -->|Token aud=Orders API| AS[Authorization Server]
    C -->|Bearer token| O[Orders API]
    C -->|Token aud=Billing API| AS
    C -->|Bearer token| B[Billing API]
    O --> D[(Orders DB)]
    B --> F[(Billing DB)]
~~~

The client requests a separate token for each API. The Orders API only accepts tokens with the Orders API audience; the Billing API only accepts tokens with the Billing API audience. This is usually the easiest option to control when a client calls multiple independent APIs.

### 4.2. Client Calling Through a Gateway

~~~mermaid
flowchart LR
    C[Client] -->|Token aud=Gateway| G[API Gateway]
    G -->|Internal service identity| O[Orders API]
    G -->|Internal service identity| B[Billing API]
    O --> D[(Orders DB)]
    B --> F[(Billing DB)]
    AS[Authorization Server] -. issue .-> C
~~~

The token is issued for the Gateway. The Gateway validates the audience and scopes, then calls backends using a controlled internal service-identity mechanism such as mTLS or a dedicated token between the gateway and backend.

In this model, a backend must not receive a token whose audience is solely the Gateway and treat it as a valid backend token. If the backend must verify access tokens end-to-end, the token must carry the backend's audience or the Gateway must acquire a new token tailored to the backend.

### 4.3. Gateway Forwarding Tokens to Backends

~~~mermaid
flowchart LR
    C[Client] -->|Token aud=Gateway + API| G[API Gateway]
    G -->|Forward Bearer token| O[Orders API]
    G -->|Forward Bearer token| B[Billing API]
    AS[Authorization Server] -. issue .-> C
~~~

This approach is valid only when tokens are explicitly designed for backends to accept them. When a token carries multiple audiences, every scope in the token must be meaningful to the corresponding resources and policy must eliminate ambiguous combinations.

Do not pack numerous audiences into a token simply to avoid having the gateway obtain a new token. A multi-audience token widens the replay surface if compromised. When a gateway needs to call multiple backends, consider token exchange or acquiring separate tokens per backend.

## 5. Designing Stable Audience URIs

Audiences are typically represented by URIs identifying the Resource Server or API. For example:

~~~text
https://api.example.com/orders/
https://api.example.com/billing/
https://api.example.com/inventory/
https://gateway.example.com/
~~~

An audience is an identifier in the security contract. It does not have to be the URL of a concrete endpoint or an address the AS must call.

When designing audiences:
- Use stable URIs within a namespace owned by the organization.
- Prefer identifiers at the API/resource level rather than coupling to fine-grained routes.
- Distinguish independent APIs even when they share a host.
- Do not use dev hostnames, mutable internal IPs, or temporary URLs.
- Do not include query strings or fragments in resource identifiers.
- Do not arbitrarily alter trailing slashes, casing, or paths when comparing audiences.
- For multi-tenant APIs, decide whether the tenant lives in the audience or in authorization context based on your isolation model.

For example, when multiple APIs share the same host:

~~~text
https://api.example.com/orders/
https://api.example.com/billing/
https://api.example.com/admin/
~~~

These three URIs represent three distinct recipients. Do not collapse all three into `https://api.example.com/` if the APIs have different security boundaries or operational teams.

### 5.1. Per-Tenant Audiences

If a token must be restricted to a specific tenant resource, the audience can reflect the tenant identifier:

~~~text
https://api.example.com/tenants/tenant-42/orders/
~~~

This helps distinguish recipients per tenant, though potential identifier structure exposure should be considered. Another option is a fixed API audience combined with a tenant claim and membership policies. Either way, the Resource Server must verify tenant ownership and never trust a client-supplied tenant claim.

## 6. Designing Scopes by API and Operation

Scopes should describe the actions a client is permitted to perform on the corresponding API. For example:

| API | Read Scope | Write Scope | Admin Scope |
| --- | --- | --- | --- |
| Orders API | `orders.read` | `orders.write` | `orders.admin` |
| Billing API | `billing.invoices.read` | `billing.invoices.write` | `billing.admin` |
| Inventory API | `inventory.stock.read` | `inventory.stock.write` | `inventory.admin` |

Namespaced scope names help operators recognize which API a scope belongs to. This also helps the AS maintain a scope-to-audience mapping table and helps Resource Servers enforce clear policies.

One scope can cover multiple endpoints when they share the same permission semantics. Avoid creating a separate scope for every URL or HTTP method unnecessarily; too many scopes complicate consent, client registration, and operations.

Scopes are not internal roles. Roles may be mapped to scopes in token-issuance policies, yet the two concepts remain distinct:
- Roles describe a subject's position or privilege group within the system.
- Scopes describe the specific permissions granted to a client in an access token.
- The Resource Server may still need to check ownership, tenant, or business state after validating scopes.

### 6.1. Scopes Must Be Meaningful for the Audience

If a token contains:

~~~json
{
  "aud": ["https://api.example.com/orders/"],
  "scope": "orders.read billing.invoices.read"
}
~~~

then `billing.invoices.read` has no meaning at the Orders API. Under RFC 9068, scopes in a JWT access token must be meaningful with respect to the resources listed in the audience.

The AS should reject incompatible scope/resource combinations. Do not issue tokens containing extraneous scopes simply because the client has all of them registered.

## 7. Registering Client Scopes in RegisteredClient

Spring Authorization Server uses `RegisteredClient` to declare the set of scopes a client is allowed to request. Example:

~~~java
@Bean
RegisteredClient registeredClient(
        PasswordEncoder passwordEncoder, Environment environment) {
    String clientSecret = environment.getRequiredProperty("app.clients.orders-web.secret");
    return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("orders-web")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri("https://orders.example.com/login/oauth2/code/oidc")
            .scope("orders.read")
            .scope("orders.write")
            .clientSettings(ClientSettings.builder()
                    .requireAuthorizationConsent(true)
                    .build())
            .build();
}
~~~

The example above only shows a client permitted to request two Orders API scopes. `RegisteredClient` does not by itself define which scope belongs to which audience. The application needs additional policy to bind clients, scopes, and resources.

`clientSecret` must be supplied from a secret manager or environment configuration; never hard-code raw secrets in source code. The example requires importing `org.springframework.core.env.Environment`.

In production:
- Do not grant `orders.write` to a read-only client.
- Do not grant `billing.invoices.read` to a client without a Billing use case.
- Separate client registrations by application and trust boundary when appropriate.
- Verify consent and scopes approved by the Resource Owner.
- Use `JdbcRegisteredClientRepository` or another durable repository to persist registrations.
- Manage secrets through a secret manager and store encoded values aligned with your PasswordEncoder configuration.

## 8. Building a Policy Binding Client, Scope, and Audience

The AS needs a central policy to answer:
- Which client is allowed to access which audience?
- Which scopes belong to that audience?
- May a client request one or multiple audiences in the same token?
- Which scopes are strictly OIDC scopes rather than API permissions?
- If a client requests scopes spanning multiple APIs, will the AS issue separate tokens or reject the combination?

Example policy table:

| Client ID | Audience | Allowed Scopes |
| --- | --- | --- |
| `orders-web` | `https://api.example.com/orders/` | `orders.read`, `orders.write` |
| `billing-worker` | `https://api.example.com/billing/` | `billing.invoices.read`, `billing.invoices.write` |
| `ops-console` | `https://api.example.com/orders/` | `orders.read`, `orders.admin` |
| `ops-console` | `https://api.example.com/inventory/` | `inventory.stock.read`, `inventory.admin` |

This is an application policy; it can be stored in a database or versioned configuration. `RegisteredClient.getScopes()` is the per-client scope allowlist, while the resource policy must additionally check audiences and scope-resource relationships.

### 8.1. Example Scope-to-Audience Validation Service

The snippet below illustrates a policy that issues one access token for exactly one API. If a request includes scopes from multiple APIs, the policy rejects it so the client requests separate tokens:

~~~java
@Component
public class ResourceAudiencePolicy {

    private static final Map<String, String> SCOPE_TO_AUDIENCE = Map.of(
            "orders.read", "https://api.example.com/orders/",
            "orders.write", "https://api.example.com/orders/",
            "orders.admin", "https://api.example.com/orders/",
            "billing.invoices.read", "https://api.example.com/billing/",
            "billing.invoices.write", "https://api.example.com/billing/",
            "billing.admin", "https://api.example.com/billing/",
            "inventory.stock.read", "https://api.example.com/inventory/",
            "inventory.stock.write", "https://api.example.com/inventory/",
            "inventory.admin", "https://api.example.com/inventory/"
    );

    private static final Set<String> OIDC_SCOPES = Set.of(
            "openid", "profile", "email", "address", "phone", "offline_access"
    );

    private static final Map<String, Set<String>> CLIENT_AUDIENCES = Map.of(
            "orders-web", Set.of("https://api.example.com/orders/"),
            "billing-worker", Set.of("https://api.example.com/billing/"),
            "ops-console", Set.of(
                    "https://api.example.com/orders/",
                    "https://api.example.com/inventory/"
            )
    );

    public Set<String> resolveApiAudiences(
            RegisteredClient registeredClient,
            Set<String> authorizedScopes) {

        Set<String> allowedAudiences = CLIENT_AUDIENCES.getOrDefault(
                registeredClient.getClientId(), Set.of());

        Set<String> audiences = new LinkedHashSet<>();

        for (String scope : authorizedScopes) {
            String audience = SCOPE_TO_AUDIENCE.get(scope);

            if (audience == null) {
                if (OIDC_SCOPES.contains(scope)) {
                    continue;
                }
                throw invalidScope();
            }

            if (!allowedAudiences.contains(audience)) {
                throw invalidScope();
            }

            audiences.add(audience);
        }

        if (audiences.size() > 1) {
            throw invalidScope();
        }

        if (audiences.isEmpty() && (authorizedScopes.isEmpty()
                || authorizedScopes.stream().anyMatch(scope -> !OIDC_SCOPES.contains(scope)))) {
            throw invalidScope();
        }

        return Collections.unmodifiableSet(audiences);
    }

    private OAuth2AuthenticationException invalidScope() {
        return new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_SCOPE));
    }
}
~~~

The example assumes required Spring Security/SAS imports are present. The policy skips OIDC scopes such as `openid` and `profile` when computing API audiences. If the token has only OIDC scopes, the method returns an empty set so the caller keeps the default policy for OIDC flows; API Resource Servers must still never treat the client ID as an API audience.

For clients calling APIs, requests must include at least one mapped API scope or a `resource` processed by an extension. Never let an API request without scopes fall back to the default client ID audience. A token with only OIDC scopes is a special case serving OIDC flows; if applying RFC 9068 to all JWT access tokens, define an appropriate default resource indicator for that flow or use a separate token format/policy.

A real implementation should load `CLIENT_AUDIENCES` and `SCOPE_TO_AUDIENCE` from versioned configuration or a policy store rather than maintaining static maps in source code.

## 9. Customizing JWT Access Token Audience in Spring Authorization Server

Spring Authorization Server 1.5.8 provides `OAuth2TokenCustomizer<JwtEncodingContext>` to customize claims before a JWT is encoded. `JwtEncodingContext` holds the RegisteredClient, authorized scopes, authorization grant, and related authorization.

By default, `JwtGenerator` uses the client ID as the JWT audience. For API access tokens, the application must replace the default audience with the policy-approved resource identifier.

A client ID identifies the client, not by default an API audience. When implementing the JWT Access Token Profile per RFC 9068, the AS must emit `aud` as the resolved resource indicator. When the `resource` parameter is absent, policy must select a default resource by scope or configuration; if scopes point to multiple distinct default resources, reject the ambiguous request.

Example:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
        ResourceAudiencePolicy audiencePolicy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        Set<String> audiences = audiencePolicy.resolveApiAudiences(
                context.getRegisteredClient(),
                context.getAuthorizedScopes()
        );

        if (!audiences.isEmpty()) {
            context.getClaims().audience(audiences);
            // Set typ only when this token complies with RFC 9068 JWT Access Token Profile.
            context.getJwsHeader().type("at+jwt");
        }
    };
}
~~~

`context.getClaims().audience(...)` overrides the `aud` claim in the JWT. When scopes map to an API, the token receives that API's audience URI in place of the default client ID.

Key points to keep in mind:
- Modify the audience only for access tokens; do not replace the ID Token's audience with an API audience.
- Use `getAuthorizedScopes()` to rely on scopes approved by the AS rather than reading raw scopes from the HTTP request.
- Enforce both the client allowlist and the scope-to-resource policy before issuing a token.
- If the request contains scopes belonging to multiple APIs, the example policy rejects it instead of issuing a multi-audience token.
- If the application already has an `OAuth2TokenCustomizer<JwtEncodingContext>`, consolidate the logic into one bean; Spring Authorization Server advises declaring only one customizer bean of this type.
- This example targets JWT/self-contained access tokens. Opaque/reference tokens require the corresponding customizer and token generator.

Setting the `typ` header to `at+jwt` is required when opting into RFC 9068 compliance; adding the `aud` claim alone does not make a JWT conform to this profile. Resource Servers implementing RFC 9068 must also verify that `typ` is `at+jwt` or `application/at+jwt`, in addition to issuer, audience, signature, and validity window. If not adopting the RFC 9068 profile, publish and consistently enforce your system's own token profile.

Do not rely on the token customizer as the sole place to check policy if the application needs to return detailed errors at the authorization request stage. You can validate scopes/resources early in the authorization/token request processor, then have the customizer reuse the policy to attach the final audience.

## 10. Resource Indicators per RFC 8707

RFC 8707 defines the `resource` request parameter for clients to specify the protected resource they want to access. The value must be an absolute URI with no fragment. The RFC allows multiple `resource` parameters, though a single resource is recommended in most cases.

Example authorization request:

~~~http
GET /oauth2/authorize?
    response_type=code&
    client_id=orders-web&
    redirect_uri=https%3A%2F%2Forders.example.com%2Flogin%2Fcallback&
    scope=orders.read&
    resource=https%3A%2F%2Fapi.example.com%2Forders%2F&
    state=STATE_VALUE
~~~

Example token request when the client sends `resource` at the Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Forders.example.com%2Flogin%2Fcallback&
resource=https%3A%2F%2Fapi.example.com%2Forders%2F
~~~

`resource` is only a client request. The AS must:
1. Parse the URI and verify it is an absolute URI.
2. Reject URIs containing a fragment; normally reject query components as well unless a clear use case exists.
3. Match against the configured resource registry/allowlist.
4. Verify the client is allowed to request that resource.
5. Verify every requested scope is meaningful at that resource.
6. Restrict the requested resource to the approved grant/consent.
7. Bind the approved resource into the authorization/token context.
8. Issue the token with the corresponding audience.

Never fetch a client-supplied URL to "check whether the API exists" or download arbitrary metadata. A Resource URI is an identifier; it is not an instruction for the Authorization Server to make network calls to a client-controlled address.

### 10.1. Spring Authorization Server and the resource Parameter

Spring Authorization Server 1.5.8 provides extension points to customize request processing at the Authorization Endpoint and Token Endpoint. Do not assume that merely adding a `resource` parameter to a request causes SAS to automatically validate the resource and rewrite the `aud` claim.

If your application implements RFC 8707:
- Add converter/provider logic or request validation at the relevant endpoints to parse `resource`.
- Enforce the resource registry and client/resource policies.
- Store the approved resource in `OAuth2Authorization` attributes for the Authorization Code flow.
- When issuing tokens, read the stored selection from `OAuth2TokenContext.getAuthorization()` rather than trusting a new value from the request.
- For Client Credentials, pass the validated resource into the custom grant/request context before token generation.
- For Refresh Tokens, allow only new resources that belong to the original grant's resource set or a policy-approved subset.

`OAuth2Authorization` includes an attributes map for storing extra state. `OAuth2TokenContext` exposes `getAuthorization()` and `getAuthorizationGrant()`, enabling custom token generation to access the verified resource selection.

## 11. Storing the Approved Resource in the Authorization Code Flow

With Authorization Code, the resource chosen in the authorization request must be bound to the authorization code. Do not allow a client to exchange a code and arbitrarily switch the resource to another API that the Resource Owner never approved.

Example state model:

~~~text
OAuth2Authorization
-------------------
registered_client_id
principal_name
authorized_scopes
attributes:
  approved_resource = https://api.example.com/orders/
  resource_policy_version = 7
tokens:
  authorization_code
  access_token
  refresh_token
~~~

Processing flow:
1. The Authorization Endpoint receives `resource` and scopes.
2. Policy validates the client, user consent, and resource-scope relationship.
3. The Authorization Server stores `approved_resource` in authorization attributes.
4. The client exchanges the authorization code at the Token Endpoint.
5. The token generator/customizer reads the stored resource and sets `aud`.
6. Refresh Tokens may only obtain tokens for resources permitted by the original grant.

If the Token Request specifies a `resource` differing from the resource stored with the authorization code, the AS must verify whether the new request is an allowed subset. If not, reject it with an appropriate error such as `invalid_target` or `invalid_scope` per extension semantics.

## 12. Client Credentials and Multiple Resources

In the Client Credentials flow there is no Resource Owner to grant consent. The AS must rely on client registration, the resource allowlist, and service-to-service policies.

Example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_BILLING_WORKER
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=billing.invoices.read&
resource=https%3A%2F%2Fapi.example.com%2Fbilling%2F
~~~

The AS verifies:
- The client is authenticated.
- The client is authorized for `client_credentials`.
- The client holds the `billing.invoices.read` scope.
- The Billing API audience is allowlisted for that client.
- Workload/tenant policies permit this operation.

A Client Credentials token represents the client/workload, not an end user. Do not inject user roles or a user subject into the token under Authorization Code flow assumptions.

If a worker needs to call both the Billing API and Inventory API, issue two tokens with their respective audiences. If using one multi-audience token, prove that every scope makes sense for every resource listed in `aud` and that sharing the token does not unintentionally broaden privileges.

## 13. Designing Audience for an API Gateway

When the Gateway is the sole recipient of an access token, the audience can be:

~~~text
https://gateway.example.com/
~~~

The Gateway validates the token, scopes, and routing policies. Then the Gateway calls backends using one of these patterns:

| Pattern | Token/Credential Sent to Backend | Condition |
| --- | --- | --- |
| Gateway service identity | mTLS or gateway's own credentials | Backend trusts the gateway's workload identity |
| Downstream token exchange | New token with the backend's audience | AS supports token exchange and delegation policies |
| Forward original token | Token whose audience includes the backend | Backend independently verifies issuer, audience, scopes, and expiry |

If a token carries only `aud=https://gateway.example.com/`, the Orders API must reject it. The Gateway cannot alter the `aud` claim by modifying headers or rewriting the token; doing so invalidates the signature.

### 13.1. Gateway Checking Routes and Scopes

Example route policy:

| Route | Token Audience | Required Scope |
| --- | --- | --- |
| `GET /orders/**` | Gateway | `orders.read` |
| `POST /orders/**` | Gateway | `orders.write` |
| `GET /billing/**` | Gateway | `billing.invoices.read` |

The Gateway can map routes to backends, yet scopes must remain meaningful to the target API. Backends still need to authenticate the workload identity or a token intended for themselves if those backends are reachable outside the gateway.

### 13.2. When the Gateway Forwards Tokens

If the gateway forwards the raw Bearer token:
- The token must include the receiving backend in its audience.
- The backend must independently verify signature/issuer/audience/expiry and scopes.
- The gateway must never add audiences or scopes by altering the token.
- Replay risk must be evaluated across every API listed in `aud`.
- Never forward tokens to services outside the audience.

If the gateway needs to call multiple backends while the initial token targets only the gateway, use token exchange or dedicated service credentials. Never widen the initial audience merely for routing convenience.

## 14. Resource Server Audience Validation in Spring Security

Each API needs to know the audience identifier it accepts. Example Orders API:

~~~java
@Bean
JwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.example.com";
    String jwkSetUri = "https://auth.example.com/oauth2/jwks";
    String expectedAudience = "https://api.example.com/orders/";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTimeValidator =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The access token is not intended for Orders API",
                null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    OAuth2TokenValidator<Jwt> typeValidator = jwt -> {
        Object typ = jwt.getHeaders().get("typ");
        if ("at+jwt".equals(typ) || "application/at+jwt".equals(typ)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token", "JWT is not an OAuth 2.0 access token", null));
    };

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            issuerAndTimeValidator,
            audienceValidator,
            typeValidator
    ));

    return decoder;
}
~~~

Then attach the decoder to the Resource Server:

~~~java
@Bean
SecurityFilterChain ordersApiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(ordersJwtDecoder()))
        );

    return http.build();
}
~~~

The example assumes remaining beans/imports are declared. `JwtValidators.createDefaultWithIssuer` checks default validators such as issuer and timestamps; the audience validator adds the recipient requirement.

Spring Security's `JwtGrantedAuthoritiesConverter` maps scopes by default to authorities with the `SCOPE_` prefix. Thus `orders.read` becomes `SCOPE_orders.read` for use in authorization rules.

Each API should configure its own audience. Do not use one decoder that accepts every audience across the entire system if the APIs have distinct trust boundaries.

## 15. Audience and Scope in Opaque Tokens

Opaque/reference tokens do not let the Resource Server read JWT claims directly. The Resource Server sends the token to the AS's Token Introspection Endpoint to retrieve status and metadata.

RFC 8707 allows audience restrictions to be expressed in the top-level `aud` field of the introspection response. The Resource Server must still check:
- `active` is true.
- `iss` is a trusted issuer if required by policy.
- `aud` contains the current API's resource identifier.
- `scope` includes the permissions needed by the endpoint.
- Additional claims such as tenant or client ID satisfy policy.

In SAS, `OAuth2TokenCustomizer<JwtEncodingContext>` customizes only JWTs. When using opaque access tokens, configure `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>` with `OAuth2AccessTokenGenerator` and verify that the introspection response returns the policy-approved audience.

Example customizer snippet for reference tokens:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueAccessTokenCustomizer(
        ResourceAudiencePolicy audiencePolicy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        Set<String> audiences = audiencePolicy.resolveApiAudiences(
                context.getRegisteredClient(),
                context.getAuthorizedScopes()
        );

        if (!audiences.isEmpty()) {
            context.getClaims().audience(new ArrayList<>(audiences));
        }
    };
}
~~~

This customizer must be wired into the `OAuth2AccessTokenGenerator` in use. When manually configuring `OAuth2TokenGenerator`, call `setAccessTokenCustomizer(...)` on the opaque generator; if using SAS's default configured generator, verify how your Spring Boot/SAS version connects customizer beans.

Do not assume switching token format from JWT to opaque automatically preserves all custom claims. Test the introspection response against the exact generator and authorization service in use.

## 16. Multiple Audiences in One Request: When Should It Be Allowed?

RFC 8707 lets clients submit multiple resource indicators. RFC 9068 requires the AS not to issue a JWT access token if the granted permissions become ambiguous.

A multi-audience token should be issued only when:
- Each resource is validated and allowlisted.
- Each scope can be clearly associated with its corresponding resource.
- The Resource Servers share an appropriate trust boundary.
- The client genuinely needs to use the same token across multiple resources.
- Replay risks and token blast radius are acceptable.
- Tests prove each API enforces only its own permissions.

Example token:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": [
    "https://api.example.com/orders/",
    "https://api.example.com/inventory/"
  ],
  "scope": "orders.read inventory.stock.read",
  "client_id": "ops-console"
}
~~~

The Orders API uses only `orders.read`; the Inventory API uses only `inventory.stock.read`. If a scope could be interpreted by multiple APIs, or an API cannot determine which scopes apply to it, the AS should reject the combination instead of issuing the token.

In most systems, one access token per resource reduces risk surface and simplifies observability. Clients can request multiple independent tokens.

## 17. Downstream Token Exchange and Delegation

A gateway or aggregation API sometimes needs to call backends on behalf of a user. OAuth 2.0 Token Exchange per RFC 8693 can be used if the AS implements this flow.

Conceptual flow:
1. Client receives a token intended for the Gateway.
2. Gateway validates the incoming token and identifies the backend to call.
3. Gateway uses its own credentials/workload identity to request a new token.
4. AS validates the subject token, actor, client, resource, and scopes.
5. AS issues a short-lived token with the backend's audience and minimal scopes.
6. Backend validates the new token as an independent Resource Server.

Token exchange does not mean the gateway modifies `aud` on an existing token. The AS must issue a new token and record delegation context according to policy.

If the backend only needs to know the request came from the Gateway without user delegation, mTLS/service identity may be simpler than token exchange. Choose the pattern based on authorization and audit requirements.

## 18. Protocol Errors and Responses

| Scenario | Suggested Error | Meaning |
| --- | --- | --- |
| Invalid/unknown Resource URI | `invalid_target` | Resource indicator is malformed or unsupported by AS |
| Scope not granted to client | `invalid_scope` | Client is not allowed to request that scope |
| Scope does not belong to resource | `invalid_scope` or `invalid_target` | Scope/resource combination invalid per policy |
| Client not permitted to access resource | `invalid_target` | Client is not on the resource allowlist |
| Token audience does not match API | `invalid_token` | Resource Server rejects token |
| Expired token or invalid signature | `invalid_token` | Token is invalid |
| Valid token but missing scope | `insufficient_scope` | Token lacks permissions for endpoint |

Do not expose internal details of the resource registry, policies, or tenants in public error responses. Log policy codes, client IDs, normalized resource identifiers, and correlation IDs; never log raw access tokens.

## 19. Audience and Scope Test Matrix

| Scenario | Action | Expected Result |
| --- | --- | --- |
| Orders audience | Request `orders.read` | Token carries Orders API audience |
| Billing audience | Request `billing.invoices.read` | Token carries Billing API audience |
| Wrong API | Send Orders token to Billing API | Billing API returns `invalid_token` |
| Scope escalation | Client with only `orders.read` requests `orders.admin` | AS returns `invalid_scope` |
| Scope/resource mismatch | Request `billing.invoices.read` with Orders resource | AS rejects |
| Unknown resource | Send resource URI outside registry | AS returns `invalid_target` |
| Non-absolute resource | Send relative URI | AS rejects |
| Fragment in resource | Send URI with `#fragment` | AS rejects |
| Multiple resources | Request Orders and Billing in one request | Rejected per single-resource/token policy, or issued only under explicit multi-audience policy |
| Gateway-only token | Forward token with only Gateway audience to Orders API | Orders API rejects |
| Backend token | Exchange token for Orders audience | Orders API accepts if scope is valid |
| Missing audience | Token lacks API audience | API rejects |
| Wrong token type | RFC 9068 API receives JWT with `typ` other than `at+jwt`/`application/at+jwt` | Resource Server returns `invalid_token` |
| Client not allowed | Client requests audience outside allowlist | AS rejects |
| OIDC-only scope | Request `openid profile` | Does not automatically grant API audience or API permissions |
| Ambiguous default resource | Scopes point to multiple default resources without `resource` | AS rejects ambiguous combination |
| Opaque token | Introspect Orders token at Billing API | Billing API checks `aud` and rejects |
| Expired token | Send expired token | Resource Server returns `invalid_token` |
| Tenant mismatch | Token carries tenant not matching request/resource | API rejects per tenant policy |
| Refresh token resource | Request refresh token for resource outside original grant | AS rejects |
| Gateway route scope | Call POST orders with token carrying only `orders.read` | Gateway/API rejects |

Tests must verify token responses, JWT claims or introspection responses, and the decision at each API. A validly signed token does not by itself prove it is authorized for the target resource.

## 20. Case Study Exercise

An e-commerce system has an Orders API, Billing API, and Inventory API. Client `ops-console` needs to read orders and inventory. Client `billing-worker` only needs to read invoices. All APIs sit behind a Gateway.

Audiences:

~~~text
https://gateway.example.com/
https://api.example.com/orders/
https://api.example.com/billing/
https://api.example.com/inventory/
~~~

Scopes:

~~~text
orders.read
orders.write
billing.invoices.read
billing.invoices.write
inventory.stock.read
inventory.stock.write
~~~

Analyze the following:

1. When `ops-console` calls the Gateway to read Orders, which audience should the token carry?
2. If the Gateway forwards the token to the Orders API, what conditions must the audience satisfy?
3. Why should `billing-worker` not receive `orders.read`?
4. If a client requests `orders.read` and `inventory.stock.read` in one request, should the AS issue one multi-audience token or reject it?
5. When should token exchange be used?
6. If the token is opaque, where does the Resource Server validate the audience?
7. Which scope is required for `POST /orders`?
8. How do you test that a Gateway-only token is rejected by the Orders API?
9. If tenant `tenant-42` only has Orders permissions, how should tenant and audience be bound?
10. Propose a way to observe requests rejected for wrong audience without logging raw tokens.

**Hint:** Separate the Gateway audience from each backend's audience. If a backend verifies tokens itself, the token must be issued for that backend. Map each scope to one API and reject incompatible scope/resource pairs. Use multi-audience only when scopes clearly map to each resource; otherwise request separate tokens or use token exchange.

## 21. Production Deployment Checklist

1. **Resource registry:** define stable URIs for each API, gateway, and distinct tenant resource.
2. **Scope taxonomy:** name scopes by API and action; avoid overlapping meanings across APIs.
3. **Client allowlist:** restrict allowed audiences and scopes per RegisteredClient.
4. **Scope-resource binding:** maintain a policy mapping scopes to audiences and clients.
5. **Resource parameter:** if using RFC 8707, parse absolute URIs, reject fragments, and validate against an allowlist.
6. **Authorization persistence:** store approved resources in authorization attributes to bind them to codes/refresh tokens.
7. **JWT customization:** set the `aud` claim on access tokens per policy; do not alter ID Token audiences.
8. **Default audience:** understand JwtGenerator's default client ID audience and override it when tokens target APIs.
9. **Gateway:** clarify whether the gateway is a recipient or merely a router; never forward tokens with the wrong audience.
10. **Backend validation:** each Resource Server verifies issuer, signature, expiry, audience, and scopes.
11. **Opaque tokens:** ensure introspection returns the audience and Resource Servers check that field.
12. **Multi-resource:** issue multi-audience tokens only when the scope-resource relationship is unambiguous.
13. **Token exchange:** issue new downstream tokens with minimal audience/scopes when delegation is needed.
14. **Tenant:** verify tenant membership/ownership in addition to checking audience.
15. **Lifecycle:** bound TTLs, revoke tokens, and update policies when clients/resources are decommissioned.
16. **Observability:** log policy decisions, client, resource, scope, and correlation ID; never log raw tokens.
17. **Testing:** test positive/negative cases across AS, Gateway, APIs, and introspection.
18. **Documentation:** publish resource identifiers, scopes, error semantics, and API onboarding procedures.

## 22. Standards and Spring References

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): scopes and authorization/token requests.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): protecting bearer tokens and preventing token redirects.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): introspection responses for opaque/reference tokens.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): delegation and tokens for downstream resources.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html): `resource` parameter, audience restriction, and `invalid_target`.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `aud` claim, `scope`, validation, and scope-resource relationships.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, OAuth2Authorization, OAuth2TokenContext, and OAuth2TokenCustomizer.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): Authorization Endpoint and Token Endpoint extension points.
- [Spring Authorization Server 1.5.8 — Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): configuring OAuth2TokenCustomizer for JWT access tokens.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, JwtAuthenticationConverter, and JWT validation.

**Takeaway:** Audience determines which API may accept an access token; scope determines which operations are permitted at that API; resource indicator is the client's request letting the AS know where the token will be used. The AS must evaluate client, resource, and scope as one unified policy and then issue a token with the appropriate audience. With multiple APIs, prefer separate tokens per resource; when using a gateway, distinguish gateway-targeted tokens from backend-targeted tokens. Each Resource Server must independently verify audience and scopes before executing requests.
