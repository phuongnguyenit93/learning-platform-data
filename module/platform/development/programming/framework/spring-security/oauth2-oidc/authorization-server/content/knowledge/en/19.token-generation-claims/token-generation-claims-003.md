# OAuth2TokenContext, JwtEncodingContext, and OAuth2TokenClaimsContext

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, a token is not merely a random string or a signed JWT. Every token is generated within a specific context: which client is requesting it, which principal is involved, which grant type is being processed, which scopes were approved, which token type is being generated, and which Authorization Server is issuing it.

Spring Authorization Server passes that information through the **token context** system. Three types you need to understand clearly are:

- <code>OAuth2TokenContext</code>: the general context that a token generator uses to decide which token to generate and its associated data.
- <code>JwtEncodingContext</code>: the specialized context for JWT creation, providing builders for the JWS header and JWT claims before signing.
- <code>OAuth2TokenClaimsContext</code>: the specialized context for claims of a reference/opaque access token, created by <code>OAuth2AccessTokenGenerator</code>.

Running example: Alice logs into <code>orders-web</code> and approves the scopes <code>orders.read</code> and <code>orders.write</code>. The Authorization Server issues an access token for the Orders API. The API needs to know the issuer, audience, expiration, and scopes. If the access token is a JWT, the Resource Server can verify its signature and claims without calling the Authorization Server on every request. If the access token is a reference token, the Resource Server typically calls introspection to obtain the status and claims stored by the Authorization Server.

After this lesson, you will be able to:

1. Describe the data contained in <code>OAuth2TokenContext</code> and why token generators need it.
2. Distinguish the context for creating JWTs from the context for creating claims on reference access tokens.
3. Write an <code>OAuth2TokenCustomizer</code> with the right generic type and customize only the intended token type.
4. Add claims from trusted sources without taking sensitive data or privileges from unverified requests.
5. Understand the relationship between <code>JwtGenerator</code>, <code>OAuth2AccessTokenGenerator</code>, <code>OAuth2RefreshTokenGenerator</code>, and <code>DelegatingOAuth2TokenGenerator</code>.
6. Preserve default validations for issuer, subject, audience, lifetime, scopes, and token format when adding custom claims.
7. Test claims across JWTs, reference tokens/introspection, and different grants.

**Version scope:** Java examples follow the Spring Authorization Server 1.5.x and Spring Security 6.x APIs on the Servlet stack. Newer Spring Security releases with integrated Authorization Server support may change package names or configuration DSLs; verify against your project version. Business classes like <code>TenantMembershipService</code> in this lesson are application-defined abstractions.

## 2. Token Generation Pipeline

### 2.1. From Authorization Grant to Token

The Token Endpoint or another protocol endpoint validates the grant request first. When the grant is valid, the provider builds a token context and calls <code>OAuth2TokenGenerator</code>. The matching generator creates the token; the provider then persists authorization/token metadata and returns the result to the endpoint.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant E as Authorization Endpoint / Token Endpoint
    participant P as AuthenticationProvider
    participant CTX as OAuth2TokenContext
    participant G as OAuth2TokenGenerator
    participant J as JwtGenerator
    participant O as OAuth2AccessTokenGenerator
    participant S as OAuth2AuthorizationService
    C->>E: Authorization request or token request
    E->>P: Parsed grant authentication
    P->>P: Verify client, grant, consent, scope, and policy
    P->>CTX: Build token context for the token type to generate
    P->>G: generate(context)
    G->>J: Try generating JWT if format/token type matches
    J-->>G: Jwt or null
    G->>O: Try generating reference access token if applicable
    O-->>G: OAuth2AccessToken or null
    G-->>P: Token produced by the matching generator
    P->>S: Save authorization and token metadata
    P-->>E: Authentication succeeded
    E-->>C: OAuth/OIDC token response
~~~

The diagram illustrates the generator's role; the exact order of generators in <code>DelegatingOAuth2TokenGenerator</code> depends on how the application configures it. A generator does not replace grant verification. A token context is constructed **after** the provider has determined the client, principal, and grantable permissions.

### 2.2. Four Stages to Distinguish

| Stage | Component | Responsibility |
| --- | --- | --- |
| Receive request | Filter + <code>AuthenticationConverter</code> | Reads protocol parameters and creates the grant authentication request. |
| Verify grant | <code>AuthenticationProvider</code> | Validates client, authorization, code/refresh token, consent, scope, and policy. |
| Generate token | <code>OAuth2TokenContext</code> + <code>OAuth2TokenGenerator</code> + customizer | Builds token data from context, signs JWT or creates reference token. |
| Persist and respond | <code>OAuth2AuthorizationService</code> + endpoint filter | Saves required state and outputs the token response. |

Do not use <code>OAuth2TokenCustomizer</code> as a substitute for authorization policy. A customizer can add claims to a token, but if the grant has not been verified or the scopes are wrong, adding a nice claim does not make the request valid.

## 3. OAuth2TokenContext: The Shared Token Context

### 3.1. Core Information

<code>OAuth2TokenContext</code> is the interface describing the context received by <code>OAuth2TokenGenerator</code>. Important accessors include:

| Accessor | Meaning | Example |
| --- | --- | --- |
| <code>getRegisteredClient()</code> | Registered/authenticated client for the current grant. | <code>orders-web</code>. |
| <code>getPrincipal()</code> | Principal tied to the token issuance process. | Alice in Authorization Code; client principal in Client Credentials. |
| <code>getAuthorizationServerContext()</code> | Authorization Server context, including issuer and related configuration. | <code>https://auth.example.com</code>. |
| <code>getAuthorization()</code> | Authorization being created/updated, if present in context. | Record containing authorization code or refresh token. |
| <code>getAuthorizedScopes()</code> | Set of scopes approved/allowed for the current token. | <code>orders.read</code>. |
| <code>getTokenType()</code> | Type of token being generated. | <code>OAuth2TokenType.ACCESS_TOKEN</code>. |
| <code>getAuthorizationGrantType()</code> | Grant type currently being processed. | <code>authorization_code</code>. |
| <code>getAuthorizationGrant()</code> | Authentication object representing the grant request. | Authorization Code authentication or Refresh Token authentication. |

These accessors help the customizer understand **which client, which principal, which grant, which scopes, and which token type** the token belongs to. Not every field is populated in every flow. For example, some early token creation steps do not yet have a complete <code>OAuth2Authorization</code>; customizers must handle optional/null cases according to the actual API rather than assuming authorization is always present.

### 3.2. Example Building DefaultOAuth2TokenContext

Inside a provider, a token context can be built as follows:

~~~java
OAuth2TokenContext tokenContext = DefaultOAuth2TokenContext.builder()
    .registeredClient(registeredClient)
    .principal(principal)
    .authorizationServerContext(
        AuthorizationServerContextHolder.getContext())
    .authorizedScopes(authorizedScopes)
    .tokenType(OAuth2TokenType.ACCESS_TOKEN)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrant(authorizationGrantAuthentication)
    .build();

OAuth2Token generated = tokenGenerator.generate(tokenContext);
~~~

This is a structural example; standard providers already perform this step. <code>registeredClient</code>, <code>principal</code>, <code>authorizedScopes</code>, and <code>authorizationGrantAuthentication</code> must come from grant verification results. Do not pull corresponding values directly from the form body and put them into the context.

For refresh tokens, the provider can also include the existing authorization in the context so the token generator/customizer has context from the stored grant. Use the default provider or extend the proper hook; do not write a separate custom token endpoint just to construct contexts.

### 3.3. The Client Principal Is Not Always an End-User

The value of <code>getPrincipal()</code> depends on the grant:

| Grant | Typical principal | Meaning |
| --- | --- | --- |
| Authorization Code | Authenticated user | Token represents permissions granted by the End-User to the client. |
| Client Credentials | Authenticated client | Token represents an application/service; no default End-User. |
| Refresh Token | Principal tied to the original authorization | New token continues the saved authorization context. |
| Device Authorization | User who verified the device after flow completion | Depends on device authorization state. |
| Token Exchange | Subject/actor per exchange grant | Must preserve subject token and actor token semantics. |

Therefore, a customizer that reads <code>context.getPrincipal().getAuthorities()</code> and treats all of them as user roles can be wrong when the grant is Client Credentials. Branch by grant type and principal type, or read entitlements from a trusted source bound to the client/principal.

### 3.4. Granted Scopes Differ from Scopes a Client May Request

<code>RegisteredClient.getScopes()</code> is the list of scopes the client is registered to request. <code>OAuth2TokenContext.getAuthorizedScopes()</code> represents the scopes approved/allowed in the **current authorization**. When creating an access token, the customizer should rely on <code>authorizedScopes</code>, not copy all registered scopes into claims.

For example, if a client is registered with <code>orders.read</code>, <code>orders.write</code>, and <code>orders.admin</code>, but Alice only approves <code>orders.read</code>, the token must not have a scope claim containing all three permissions. A customizer is not the place to expand permissions; any scope changes must be handled in authorization/grant policy before token generation.

## 4. JwtEncodingContext: Context for Creating JWTs

### 4.1. Builders for JWS Header and JWT Claims

<code>JwtEncodingContext</code> extends <code>OAuth2TokenContext</code> and adds two important builders:

- <code>getJwsHeader()</code>: builder for the JOSE/JWS header, such as algorithm and signing key metadata.
- <code>getClaims()</code>: builder for <code>JwtClaimsSet</code>, used to add or adjust claims before the JWT is encoded/signed.

<code>JwtGenerator</code> builds the JWT from this context and uses <code>JwtEncoder</code> to sign it. Once the signature is created, editing claims inside the token is no longer safe: modifying the payload invalidates the signature. Thus the customizer runs **before** the encoding step.

~~~mermaid
flowchart TD
    A["JwtGenerator receives OAuth2TokenContext"] --> B["Create JwtEncodingContext"]
    B --> C["Set default JWS header"]
    C --> D["Set default JWT claims"]
    D --> E["OAuth2TokenCustomizer<JwtEncodingContext>"]
    E --> F["JwtEncoder"]
    F --> G["Compact JWS: header.payload.signature"]
    G --> H["Jwt stored in OAuth2Authorization"]
~~~

The diagram focuses on JWT generation. Exact default claims and headers depend on token type, OIDC, and JWK/encoder configuration. Do not assume all JWT types carry the same claims.

### 4.2. Example Adding Claims for a JWT Access Token

Suppose the application has a <code>TenantMembershipService</code> that retrieves the current verified tenant for the principal and client:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
        TenantMembershipService tenantMemberships) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        // Only use scopes approved for the current authorization.
        context.getClaims().claim(
            "scope", context.getAuthorizedScopes());

        String tenantId = tenantMemberships.findAuthorizedTenant(
            context.getRegisteredClient(),
            context.getPrincipal(),
            context.getAuthorization());

        if (tenantId != null) {
            context.getClaims().claim(
                "https://claims.example.com/tenant_id", tenantId);
        }
    };
}
~~~

<code>TenantMembershipService</code> is an illustrative application-built service; <code>findAuthorizedTenant(...)</code> must check the tenant relationship against the principal and client using trusted data. Do not read a tenant ID directly from an <code>X-Tenant</code> header or an unverified request parameter.

This snippet only processes JWT access tokens. If the application already produces a default scope claim, inspect the generated token first before rewriting the <code>scope</code> claim yourself; there is no need to overwrite a default claim just to produce the same value. The goal of this example is to show how the context provides approved scopes and how to add a namespaced custom claim.

### 4.3. Selectively Adding Roles

A customizer can add roles to a JWT access token when the token represents a user:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> userRoleCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        if (!AuthorizationGrantType.AUTHORIZATION_CODE.equals(
                context.getAuthorizationGrantType())) {
            return; // Do not treat Client Credentials as a user login.
        }

        Authentication principal = context.getPrincipal();
        Set<String> roles = principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .filter(authority -> authority.startsWith("ROLE_"))
            .map(authority -> authority.substring("ROLE_".length()))
            .collect(Collectors.toUnmodifiableSet());

        context.getClaims().claim("roles", roles);
    };
}
~~~

This is an illustrative example. A real application must ensure the principal's authorities are loaded from a trusted source and kept up to date per policy. Do not dump all authorities—such as <code>SCOPE_orders.read</code>, <code>ROLE_...</code>, internal admin flags, or technical attributes—indiscriminately into a <code>roles</code> claim. The Resource Server must have clear rules for mapping claims to GrantedAuthority.

**Note on multiple customizers:** Avoid declaring multiple beans of the same generic type and assuming the framework will always combine them in your desired order. If multiple JWT policies are needed, combine them inside a single explicitly ordered <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> or configure them directly on <code>JwtGenerator</code>.

### 4.4. JWS Header and Key Selection

The JWS header contains signature-verification information such as <code>alg</code>, <code>kid</code>, and <code>typ</code> per profile. <code>JwtEncodingContext.getJwsHeader()</code> allows customizing the header before signing. However:

- The algorithm must match the key and server policy; never let clients arbitrarily choose <code>alg</code>.
- <code>kid</code> must identify the actual signing key in the JWK Set; never set a value that does not exist in the key store.
- Never expose private keys or secrets in headers/claims.
- Only set <code>typ</code> when adhering to a token profile and matching Resource Server expectations; for example, RFC 9068 JWT access tokens have specific type rules.
- Key rotation requires publishing the appropriate public keys and keeping a compatibility window so Resource Servers can verify still-valid tokens.

Usually it is best to let <code>JwtGenerator</code>, <code>JwtEncoder</code>, and the JWK source select algorithms/keys from configuration. Only intervene in the header when there is an explicit profile requirement and integration tests prove the Resource Server handles it properly.

## 5. OAuth2TokenClaimsContext: Claims for Reference Access Tokens

### 5.1. Why Is a Separate Context Needed?

Not every access token is a JWT. Spring Authorization Server supports formats:

| Token format | Characteristics |
| --- | --- |
| <code>SELF_CONTAINED</code> | JWT access token containing claims and a signature; Resource Server can verify locally using issuer/JWK. |
| <code>REFERENCE</code> | Access token is an unguessable reference string; authorization/claims live server-side and Resource Server typically calls introspection. |

For reference access tokens, <code>OAuth2AccessTokenGenerator</code> creates the token value and builds a claims context for claims associated with the access token. <code>OAuth2TokenClaimsContext</code> also extends <code>OAuth2TokenContext</code>, but exposes a <code>getClaims()</code> builder of type <code>OAuth2TokenClaimsSet.Builder</code> rather than <code>JwtClaimsSet.Builder</code>, and has no JWS header.

Claims are used in server-side authorization/token metadata and may appear in introspection responses depending on configuration. There is no JWT for the Resource Server to decode directly. **Do not attempt to use <code>JwtEncodingContext</code> to customize reference tokens**, because the generator does not go through JWT encoding.

### 5.2. Example Custom Claims for a Reference Access Token

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> referenceTokenCustomizer(
        TenantMembershipService tenantMemberships) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return;
        }

        String tenantId = tenantMemberships.findAuthorizedTenant(
            context.getRegisteredClient(),
            context.getPrincipal(),
            context.getAuthorization());

        if (tenantId != null) {
            context.getClaims().claim(
                "https://claims.example.com/tenant_id", tenantId);
        }

        context.getClaims().claim(
            "authorization_grant",
            context.getAuthorizationGrantType().getValue());
    };
}
~~~

<code>OAuth2TokenClaimsContext</code> is used to customize claims for reference access tokens generated by <code>OAuth2AccessTokenGenerator</code>. The example requires the <code>REFERENCE</code> token format; if the client uses <code>SELF_CONTAINED</code>, this customizer does not replace the JWT customizer.

When the Resource Server uses opaque token introspection, verify that the actual response contains the custom claims as defined by the contract. Adding claims only to server-side metadata without configuring the introspection endpoint or having the Resource Server consume them does not enforce business authorization.

### 5.3. Do Not Confuse Opaque Access Tokens with Refresh Tokens

<code>OAuth2TokenClaimsContext</code> is not a way to customize refresh tokens. A refresh token is a credential used to obtain a new access token; a reference access token is a resource-access token with a reference value. The two token types have different lifecycles, purposes, and storage policies.

## 6. Choosing the Right Generator and Customizer

### 6.1. Common Generators

| Generator | Role |
| --- | --- |
| <code>JwtGenerator</code> | Generates JWTs, including self-contained JWT access tokens and ID Tokens in corresponding OIDC flows. |
| <code>OAuth2AccessTokenGenerator</code> | Generates reference/opaque access tokens and corresponding claims metadata. |
| <code>OAuth2RefreshTokenGenerator</code> | Generates refresh tokens per client/token settings and grant conditions. |
| <code>DelegatingOAuth2TokenGenerator</code> | Tries generators in order, returning the token from the matching generator. |

Each generator has its own scope of support. Adding a customizer does not make every generator handle every token type.

### 6.2. Configuring Format on RegisteredClient

Example choosing a JWT access token:

~~~java
RegisteredClient ordersClient = RegisteredClient.withId("orders-record-001")
    .clientId("orders-web")
    // Client authentication methods, grants, and redirect URIs omitted.
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .scope("orders.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .build())
    .build();
~~~

Example choosing a reference access token:

~~~java
TokenSettings referenceSettings = TokenSettings.builder()
    .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .build();
~~~

Lifetimes shown are illustrative values. <code>accessTokenFormat</code> determines the matching generator and how the Resource Server verifies tokens. Do not change the format on the Authorization Server and forget to update the Resource Server: a JWT decoder cannot validate an opaque string as a JWT, and opaque token introspection does not replace audience/claims checks at the API.

### 6.3. Registering Customizers with Generators

In the default Spring Authorization Server configuration, <code>OAuth2TokenCustomizer</code> beans with matching generic types can be wired into their respective generators according to the configuration mechanism of the version in use. If the application **constructs <code>OAuth2TokenGenerator</code> itself**, you must explicitly attach each customizer to the proper generator.

Illustrative example when assembling the generator manually:

~~~java
@Bean
OAuth2TokenGenerator<?> tokenGenerator(
        JwtEncoder jwtEncoder,
        OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
        OAuth2TokenCustomizer<OAuth2TokenClaimsContext> claimsCustomizer) {

    JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
    jwtGenerator.setJwtCustomizer(jwtCustomizer);

    OAuth2AccessTokenGenerator accessTokenGenerator =
        new OAuth2AccessTokenGenerator();
    accessTokenGenerator.setAccessTokenCustomizer(claimsCustomizer);

    OAuth2RefreshTokenGenerator refreshTokenGenerator =
        new OAuth2RefreshTokenGenerator();

    return new DelegatingOAuth2TokenGenerator(
        jwtGenerator,
        accessTokenGenerator,
        refreshTokenGenerator);
}
~~~

This configuration replaces the framework's default auto-configured token generator; do not declare a custom generator while expecting the default generators to be merged automatically. If your project does not need to assemble the generator manually, prefer registering customizer beans per your version's documentation. When assembling manually, keep all generators required for supported token types, maintain proper ordering, and ensure valid <code>JwtEncoder</code>/<code>JWKSource</code> beans.

**Note on generic injection:** If an application has multiple customizers with the same generic type, constructor injection may become ambiguous or Spring may not pick what you expect. Consolidate logic into a single explicitly ordered bean or inject the intended bean via a qualifier. Avoid circular dependencies between the token generator and customizers.

## 7. Distinguishing Access Token Claims and ID Token Claims

### 7.1. Access Tokens Are for the Resource Server

An access token represents resource access privileges. Commonly important claims include:

| Claim | Purpose |
| --- | --- |
| <code>iss</code> | Authorization Server issuer that issued the token. |
| <code>sub</code> | Subject the token represents per grant. |
| <code>aud</code> | Target Resource Server/API permitted to accept the token. |
| <code>exp</code> | Expiration timestamp. |
| <code>iat</code> | Issued-at timestamp. |
| <code>jti</code> | Token ID, useful for auditing/denylisting by design. |
| <code>scope</code> or equivalent claim | Granted OAuth permissions. |
| <code>client_id</code> | Client to which the token was issued. |

The exact claim list depends on profile, grant, and generator configuration. Decode a test token or inspect an introspection response for your exact version to confirm. Do not assume all claims above automatically appear in every token or that every Resource Server uses the same claim names.

### 7.2. ID Tokens Are for the OIDC Client

An ID Token confirms End-User authentication details to the OIDC Client. It contains OIDC claims such as <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>iat</code>, and optionally <code>auth_time</code>, <code>nonce</code>, <code>acr</code>, <code>amr</code>, or other claims per request/policy.

**Never use an ID Token as an access token to call an API.** The ID Token's audience typically refers to the OIDC Client; the access token's audience must refer to the Resource Server. A customizer must check token type, grant, and target consumer before adding claims.

### 7.3. Do Not Put UI-Only Display Data into Tokens

Not everything the frontend wants to display belongs in an access token. Tokens may pass through browsers, proxies, logs, mobile storage, and multiple APIs; JWT payloads are only Base64URL-encoded, not encrypted by default. Avoid including:

- Passwords, refresh tokens, API keys, client secrets, private keys, or authentication credentials.
- ID card numbers, home addresses, or unnecessary financial/sensitive data.
- Huge role/permission lists that do not serve Resource Server authorization.
- Rapidly changing data that token TTL cannot reflect in time.
- Internal details such as database paths, internal hostnames, or stack traces.

Prefer minimal, stable claims that are meaningful to the Resource Server and issued according to consent/policy.

## 8. Design Rules for Custom Claims

### 8.1. Use Namespaces to Avoid Collisions

Generic claim names like <code>role</code>, <code>tenant</code>, or <code>permissions</code> can conflict with other applications or future profiles. For system-specific data, you can use a URI namespace you control, for example:

~~~json
{
  "https://claims.example.com/tenant_id": "tenant-42",
  "https://claims.example.com/entitlements": [
    "orders.read"
  ]
}
~~~

This is illustrative JSON, not a real token. A namespace URI does not have to be a callable endpoint; it identifies a claim namespace. Document the data type, semantics, owner, and version of each claim.

### 8.2. Rely on Trusted Data Sources

| Data to add | Trusted source to use | Where NOT to take it from |
| --- | --- | --- |
| Tenant ID | Membership/tenant service that verified principal and client. | Unchecked query parameter or header. |
| Roles | Authenticated authorities, current policy. | Claim sent by browser/client. |
| Entitlements | Authoritative permission service or authorization domain. | All scopes registered on the client. |
| Authentication assurance | Authentication/MFA outcome stored in trusted context. | Boolean <code>mfa=true</code> from a form. |
| Resource audience | Verified resource indicator and client/grant policy. | Arbitrary URL sent by caller. |
| Subject | Stable principal ID per grant semantics. | Mutable email or username when a long-lived ID is needed. |

### 8.3. Keep Claims Consistent with Scopes

Suppose the token context has <code>authorizedScopes = {orders.read}</code>. Do not generate a claim:

~~~json
{
  "permissions": ["orders.read", "orders.write", "orders.admin"]
}
~~~

unless an independent, verified policy actually grants those permissions. If the Resource Server uses both scopes and a custom permission claim, the two sources must have clear precedence rules; otherwise, the API may accidentally grant broader permissions than the scope allows.

### 8.4. Do Not Arbitrarily Alter Protocol Claims

Claims such as <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>iat</code>, <code>jti</code>, and <code>nonce</code> have standard semantics. Do not overwrite the issuer from <code>AuthorizationServerContext</code> with a request value, change the subject of an authorization without a designed mapping, extend <code>exp</code> beyond TokenSettings, or drop audience so a token works on every API.

If a specific audience is required, validate the resource indicator and client policy in the provider first, then build the audience claim from the verified result. If a custom TTL is needed, configure TokenSettings or an appropriate token generation policy; do not just set an arbitrary <code>exp</code> in a customizer and bypass operational limits.

## 9. Different Grants Produce Different Contexts

### 9.1. Authorization Code

The principal is typically the authenticated End-User. Scopes have been approved and consent is tied to the client. Customizers may add profile/tenant/role claims if the data source is valid and the token is an access token for the Resource Server. Do not dump full profile information into every token just because the principal has those attributes.

### 9.2. Client Credentials

The principal is the authenticated client; there is no user Alice behind it. Claims such as <code>sub</code>, <code>client_id</code>, roles, and tenant must represent service identity per policy. Do not read client authorities and put them in a <code>user_roles</code> claim as if they were user privileges.

### 9.3. Refresh Token

A refresh grant continues an existing authorization. Customizers must respect granted scopes, token settings, client status, and updated policies. If user/tenant privileges were revoked after the previous issuance, blindly copying old claims can preserve privileges too long; verify current policy at the appropriate refresh/provider point.

### 9.4. Device Authorization

After the user verifies the device code and approves consent, the principal/token context reflects the completed authorization. Do not use <code>user_code</code> as the subject or an identity claim; a user code is a short-lived verification code, not a user identity, and should not appear in tokens.

### 9.5. Token Exchange

Token Exchange may involve a subject token and an actor token, so custom claims must preserve the subject/actor relationship and audience/resource properly. Do not blindly copy all claims from the subject token to the new token; some claims may not be forwardable or may require downscoping.

## 10. Testing Token Contexts and Claims

### 10.1. Unit Testing a JWT Customizer

A clean approach is to extract claim computation into a pure function/strategy and test grant/token type cases. Example policy test:

~~~java
@Test
void accessTokenCustomizerDoesNotAddUserRolesForClientCredentials() {
    // Assumes a test JwtEncodingContext built with:
    // tokenType=ACCESS_TOKEN, grantType=CLIENT_CREDENTIALS,
    // principal is client authentication, not an End-User.
    JwtEncodingContext context = testContextForClientCredentials();

    jwtTokenCustomizer().customize(context);

    assertThat(context.getClaims().build().getClaims())
        .doesNotContainKey("roles");
}
~~~

<code>testContextForClientCredentials()</code> is a test-defined helper, not a Spring API. The test verifies that the customizer does not misinterpret a client principal as user roles. For context builders, create fixtures using the API of your exact version and avoid calling <code>build()</code> prematurely in production.

### 10.2. Integration Testing JWT Access Tokens

With a real test Authorization Server:

1. Register client and user fixtures; configure JWT/self-contained access tokens.
2. Complete Authorization Code + PKCE and consent with scope <code>orders.read</code>.
3. Exchange the code for tokens.
4. Decode the token with the public JWK/test decoder, verifying <code>iss</code>, <code>aud</code>, <code>exp</code>, <code>scope</code>, and custom tenant/role claims.
5. Verify the token contains no scopes outside consent and no sensitive data.
6. Call a test Resource Server to verify claims map properly to authorities.

Do not merely inspect raw JSON strings without verifying the signature. Use a proper decoder/JWK to prove the token was signed by the Authorization Server's key.

### 10.3. Integration Testing Reference Tokens/Introspection

When using <code>OAuth2TokenFormat.REFERENCE</code>:

1. Configure the Resource Server to use opaque token introspection.
2. Issue an access token via a real grant.
3. Call the introspection endpoint using proper client authentication.
4. Verify the token is active and custom claims are present per the designed contract.
5. Revoke the authorization/token, call introspection again, and confirm inactive status per storage behavior.

Reference token values cannot be decoded as JWTs. Do not write tests assuming every access token has three dot-separated segments.

### 10.4. Required Test Matrix

| Scenario | Expected result |
| --- | --- |
| JWT access token, Authorization Code | Contains only valid claims per user, client, consent, and scope. |
| JWT access token, Client Credentials | Claims represent client/service; no accidental user roles. |
| OIDC ID Token | Claims follow OIDC and target the client's audience. |
| Reference access token | Claims stored/exposed to introspection per policy. |
| Refresh grant | Scopes/claims do not exceed active authorization. |
| Token context missing optional authorization | Customizer handles safely, no NullPointerException. |
| Unverified tenant | No tenant claim issued or rejected per policy. |
| Unapproved scope | Does not appear in the token. |
| Client requests extra claim via form | Ignored or rejected; unverified input is not trusted. |
| Token generator returns null | Grant provider handles error, does not issue empty token. |
| JWK rotation | Tokens signed with valid keys and verified by Resource Server during rotation window. |
| JWT claim customizer fails | Does not report success if token was not safely generated. |
| Multiple customizers with same generic type | Clear ordering/composition, no unintended claim overwrites. |
| Wrong Resource Server audience | Resource Server rejects token. |
| Unnecessary sensitive claims | Absent from token/introspection. |

### 10.5. Testing Compatibility Between Tokens and Resource Servers

Token claims are only useful if the Resource Server understands them. Verify:

- The issuer is trusted by the Resource Server.
- The audience contains the intended target API, not overly broad values.
- Scopes map to authorities per actual configuration.
- Custom claims have stable data types (string, array, number, boolean).
- Expired tokens are rejected according to configured clock skew.
- Opaque introspection returns accurate <code>active</code>, scopes, client/principal, and permitted claims.

## 11. Common Design Mistakes

### Mistake 1: Using JwtEncodingContext for Opaque Access Tokens

**Symptom:** Custom claims appear in JWT tests but are missing from introspection when switching a client to reference format.

**Cause:** <code>JwtGenerator</code> does not generate reference access tokens.

**Fix:** Use <code>OAuth2TokenCustomizer&lt;OAuth2TokenClaimsContext&gt;</code> for reference access token claims and check the <code>OAuth2AccessTokenGenerator</code> configuration.

### Mistake 2: Using OAuth2TokenClaimsContext for JWTs

**Symptom:** The opaque customizer is not invoked when the access token format is SELF_CONTAINED.

**Cause:** The matching generator is <code>JwtGenerator</code> and the context is <code>JwtEncodingContext</code>.

**Fix:** Register the right customizer/generator for each token format.

### Mistake 3: Putting All Registered Scopes into the Token

**Symptom:** The access token contains <code>orders.write</code> even though the user only approved <code>orders.read</code>.

**Cause:** Reading <code>RegisteredClient.getScopes()</code> instead of <code>OAuth2TokenContext.getAuthorizedScopes()</code>.

**Fix:** Rely on the scopes approved by grant/consent and test final permissions on the Resource Server.

### Mistake 4: Treating the Principal as Always a User

**Symptom:** Client Credentials tokens contain roles from an unrelated user account or the customizer throws an error because the principal lacks user details.

**Cause:** Failing to distinguish grant types and principals.

**Fix:** Branch by grant, principal type, and verified entitlement source.

### Mistake 5: Overwriting Standard Claims

**Symptom:** Resource Server rejects issuer/audience or tokens have lifetimes outside policy.

**Cause:** Customizer replaces <code>iss</code>, <code>sub</code>, <code>aud</code>, or <code>exp</code> with request data or hardcoded values.

**Fix:** Keep standard claims provided by the generator/context; only modify them under controlled profiles and policies.

### Mistake 6: Treating JWT Payload as Secret Data

**Symptom:** Users can read email, tenant, roles, or internal data from the access token.

**Cause:** Confusing Base64URL encoding with encryption.

**Fix:** Include only necessary claims; if confidentiality is required, use an appropriate encryption architecture/token format instead of plain signed JWTs.

### Mistake 7: Customizer Querying Remote Services for Every Token

**Symptom:** Token endpoint becomes slow, times out, or issues tokens unreliably when the permission service has an outage.

**Cause:** Customizer performs multiple synchronous HTTP calls on the hot path.

**Fix:** Prepare entitlement data at the appropriate authorization step, use caching with TTL/invalidation or a policy service with an SLA, and decide fail-open/fail-closed explicitly.

### Mistake 8: Declaring a Custom Token Generator and Forgetting Default Generators

**Symptom:** JWT access tokens work, but refresh tokens or reference tokens fail to generate.

**Cause:** Replacing the composite generator while keeping only a single generator.

**Fix:** When assembling <code>DelegatingOAuth2TokenGenerator</code> manually, include all generators required by your grants/token formats and run regression tests.

### Mistake 9: Treating the Customizer as the Authorization Decision Point

**Symptom:** Tokens are issued even when the client is not allowed the grant or consent is invalid.

**Cause:** Checking only one condition in the customizer while bypassing the provider.

**Fix:** Validate grant/client/scope before token generation; the customizer only builds claims from an already-verified context.

## 12. Production Deployment Checklist

| Item | Question to answer |
| --- | --- |
| Context | Are client, principal, grant type, authorized scopes, and token type taken from verified sources? |
| Token format | Does the client use JWT or reference tokens? How does the Resource Server verify them? |
| Customizer | Does the generic type match the generator/token format? |
| Claims | Which claims are genuinely needed by the API? Is there any excess PII/secrets? |
| Scope | Does the token carry only approved scopes rather than all registered scopes? |
| Subject | Is the subject stable and aligned with grant semantics? |
| Audience | Is the token scoped only to permitted resources? |
| Issuer/expiry | Are issuer and TTL sourced from trusted configuration/token settings? |
| JWS | Are algorithm, kid, and key rotation compatible with the Resource Server? |
| OIDC | Do ID Token claims match client audience and OIDC semantics? |
| Opaque token | Does introspection return custom claims per contract and revoke properly? |
| Persistence | Are token metadata/authorizations persisted consistently and revocable? |
| Performance | Does the customizer avoid heavy synchronous I/O and handle dependency failures? |
| Observability | Are sensitive tokens/claims excluded from logs, with metrics for generation failures? |
| Tests | Are there tests per grant, token type, token format, Resource Server, and key rotation? |

## 13. Practice Exercise

An Authorization Server serves two APIs: Orders and Billing. Client <code>orders-web</code> uses Authorization Code + PKCE; client <code>billing-worker</code> uses Client Credentials. Both can be issued JWT or reference access tokens based on configuration.

1. Diagram the pipeline from grant provider to <code>OAuth2TokenGenerator</code> and describe the data populated in <code>OAuth2TokenContext</code>.
2. Create an <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> that adds a tenant claim only after verifying the principal is a member of that tenant.
3. Add the role claim only for Authorization Code; prove Client Credentials does not receive user roles.
4. Switch the Orders client to <code>OAuth2TokenFormat.REFERENCE</code>, configure <code>OAuth2TokenCustomizer&lt;OAuth2TokenClaimsContext&gt;</code>, and verify the introspection response.
5. Explain why <code>registeredClient.getScopes()</code> cannot substitute for <code>context.getAuthorizedScopes()</code> when building scope claims.
6. Design audiences for the Orders API and Billing API, ensuring an Orders token is not accepted by Billing.
7. Write a test proving an ID Token cannot be used as an access token and that their audiences differ.
8. Try adding an unnecessary sensitive claim and analyze the risk when the JWT payload is read by a client.
9. Configure customizer beans and, if assembling the token generator manually, verify all required generators still operate.
10. Test key rotation, token expiry, Resource Server authorization, and reference token revocation.

**Completion criteria:** You must be able to show **which context is used for which token**, **where each claim comes from**, **which Resource Server accepts the token**, and **that customizers cannot escalate permissions beyond verified authorization**.

## 14. Reference Documentation

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>OAuth2TokenContext</code>, token generators, customizers, and the authorization model.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): grant providers and token generation points within endpoints.
- [Spring Authorization Server — OAuth2TokenContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenContext.html): shared context contract.
- [Spring Authorization Server — JwtEncodingContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/JwtEncodingContext.html): JWS header builder and JWT claims builder.
- [Spring Authorization Server — OAuth2TokenClaimsContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenClaimsContext.html): claims context for the access token generator.
- [Spring Authorization Server — OAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenGenerator.html): token generation contract.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): access token format and lifetimes.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): standard claims and JWT structure.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile, issuer/audience/type, and claims.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth 2.0 security best practices and access token protection.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, claims, and OIDC scopes.
