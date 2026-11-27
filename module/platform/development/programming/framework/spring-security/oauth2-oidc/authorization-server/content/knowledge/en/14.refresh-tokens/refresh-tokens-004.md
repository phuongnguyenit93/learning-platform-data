# Validating Refresh Token Binding to Client and Authorization

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security** and **Spring Authorization Server** on **Spring Boot**, a refresh token is a high-value credential: it lets a client request new access tokens without requiring the user to repeat the entire Authorization Code flow and sign-in. Because it can be used over a longer period than an access token, a refresh token must be strictly validated before issuing new access permissions.

Suppose Alice signs in through the <code>orders-web</code> application and consents to the <code>orders.read</code> scope. The Authorization Server issues access token <code>AT-1</code> and refresh token <code>RT-1</code> for **a specific authorization of <code>orders-web</code>**. An attacker steals <code>RT-1</code> and attempts to use another client, <code>billing-web</code>, to exchange it for an access token. If the Authorization Server only checked whether the refresh token string exists, it could mistakenly grant Alice's permissions to the wrong client. Binding the refresh token to the **issued client** and the **original authorization** prevents this scenario.

After this lesson, you will be able to:

1. Distinguish protocol <code>client_id</code> from <code>RegisteredClient.getId()</code> used in the data store.
2. Understand the data linking refresh tokens, clients, principals, authorizations, scopes, and resources in <code>OAuth2Authorization</code>.
3. Describe how <code>OAuth2RefreshTokenAuthenticationProvider</code> looks up the authorization, verifies the client, checks active token status, and validates scopes before issuing new tokens.
4. Configure client registrations, lifetimes, and refresh token rotation using Spring Authorization Server.
5. Design additional controls for user status, revocation, replay detection, durable persistence, and transactions in multi-instance systems.
6. Write tests for valid refreshes, wrong clients, wrong authorizations, expired tokens, revoked tokens, scope escalation, and concurrency errors.

**Running example:** An Authorization Server at <code>https://auth.example.com</code> has two confidential clients: <code>orders-web</code> and <code>billing-web</code>. Alice grants <code>orders-web</code> the <code>orders.read</code> permission. Java illustrations follow the Spring Authorization Server 1.x API group; in newer Spring Security versions with integrated Authorization Server, package/configurer locations may differ. The lesson focuses on **binding checks** and does not replace a complete system deployment guide.

## 2. What Is a Refresh Token Bound To?

Per [RFC 6749, §6](https://www.rfc-editor.org/rfc/rfc6749#section-6), when a confidential client uses a refresh token, the Authorization Server must authenticate the client, verify that the refresh token **was issued to that exact client**, and verify the refresh token is valid. [RFC 9700, §4.14](https://www.rfc-editor.org/rfc/rfc9700#section-4.14) adds protective requirements stating that refresh tokens must be restricted to the scopes and resource servers approved by the resource owner.

A secure design inspects multiple bindings simultaneously:

~~~mermaid
flowchart LR
    C["RegisteredClient<br/>record ID = client-record-A<br/>client_id = orders-web"]
    A["OAuth2Authorization<br/>id = auth-1001<br/>registeredClientId = client-record-A<br/>principalName = user-42<br/>authorizedScopes = orders.read"]
    RT["Refresh Token<br/>RT-1<br/>status active"]
    AT["Access Token<br/>AT-1 / AT-2"]
    API["Orders API<br/>permitted resource/audience"]
    C -->|"referenced by internal ID"| A
    A -->|"stores tokens and metadata"| RT
    A -->|"issues/updates"| AT
    AT --> API
~~~

| Binding | What must be verified | If skipped |
| --- | --- | --- |
| **Refresh token → Authorization** | Look up the exact record containing **the presented refresh token itself**, under the matching token type. | Strings not belonging to the authorization could be used if repository lookup is flawed. |
| **Authorization → RegisteredClient** | <code>authorization.getRegisteredClientId()</code> matches <code>registeredClient.getId()</code> of the authenticated client. | Client B can exchange Client A's refresh token. |
| **Refresh token → status** | Token exists, is unexpired, and has not been invalidated/revoked. | Old or revoked tokens can still issue new tokens. |
| **Client → permission to use refresh grant** | Client is still registered with <code>AuthorizationGrantType.REFRESH_TOKEN</code>. | A client that lost refresh grant permission can keep refreshing. |
| **Authorization → scopes and resources** | New tokens do not exceed previously granted scopes and allowed resources. | Client requests extra scopes or switches resources using an old token. |
| **Authorization → principal/current policy** | If product rules require it, the user/tenant/session is still permitted to maintain the grant. | Disabled account's refresh token keeps issuing access tokens. |
| **Token → sender/device (when applicable)** | Bound via DPoP, mTLS, or another registered and deployed mechanism. | Stolen refresh token can be reused from another environment. |

Therefore, **a refresh token is not Alice's login password**, nor can it be treated as a "ticket" freely transferable between clients. It is a credential issued by the Authorization Server in a specific context and must be safeguarded and validated at the token endpoint.

## 3. Spring Authorization Server Data Model

### 3.1. <code>RegisteredClient</code> Has Two Distinct Identifiers

Example registration:

~~~text
RegisteredClient.id       = "client-record-A"
RegisteredClient.clientId = "orders-web"

RegisteredClient.id       = "client-record-B"
RegisteredClient.clientId = "billing-web"
~~~

<code>clientId</code> is the client identifier in OAuth 2.0 requests, such as the value sent in HTTP Basic. <code>id</code> is the **registered client record key on the Authorization Server side**. Inside <code>OAuth2Authorization</code>, the <code>registeredClientId</code> field stores **<code>RegisteredClient.getId()</code>**, not <code>getClientId()</code> by default.

Some projects set both values equal for demo convenience, but that does not give them the same role. During database migrations or client recreation, if <code>RegisteredClient.id</code> changes, existing authorizations can point to an obsolete ID. Keep IDs stable and handle migrations/revocations by policy.

### 3.2. <code>OAuth2Authorization</code> Is the Record Linking Tokens to Grants

Spring Authorization Server uses <code>OAuth2Authorization</code> to persist authorization state:

| Attribute | Meaning | Example |
| --- | --- | --- |
| <code>id</code> | Authorization ID, separate from token values. | <code>auth-1001</code> |
| <code>registeredClientId</code> | Internal ID of the authorized client. | <code>client-record-A</code> |
| <code>principalName</code> | Subject of the authorization, typically the End-User in Authorization Code Flow. | <code>user-42</code> |
| <code>authorizationGrantType</code> | Grant that **originally created the authorization**. | <code>authorization_code</code> |
| <code>authorizedScopes</code> | Scopes approved/granted for the authorization. | <code>orders.read</code> |
| <code>attributes</code> | Stored authorization context, which may hold authentication or data for token generation. | Principal/associated authorization request |
| <code>tokens</code> | Tokens and metadata associated with the authorization. | Access token, refresh token, ID Token if OIDC |

In Authorization Code Flow, the original authorization typically stores the authorization code, access token, and possibly a refresh token; in OIDC, it may include an ID Token. Under the default Spring Authorization Server model, Client Credentials typically has only an access token—**do not assume every grant includes a refresh token**.

Important point to remember: during a <code>grant_type=refresh_token</code> call, <code>authorization.getAuthorizationGrantType()</code> may still be <code>authorization_code</code>, because that was the grant type that **initiated the authorization record**. Never write a faulty check like "authorizationGrantType must be refresh_token" and reject every valid refresh.

### 3.3. Token Metadata and <code>isActive()</code>

<code>OAuth2Authorization</code> may contain:

~~~java
OAuth2Authorization.Token<OAuth2RefreshToken> stored =
    authorization.getRefreshToken();

if (stored == null || !stored.isActive()) {
    // Must not issue new tokens from a missing/expired/invalidated refresh token.
}
~~~

<code>isActive()</code> reflects that the token is unexpired and not invalidated in the Spring Authorization Server model. It **does not imply** the user account is still active, the client has not been blocked by an out-of-framework policy, or the token has not been flagged as leaked by an external monitoring system. Those business conditions require separate integration.

An authorization record may also contain an expired access token while its refresh token remains active. This is the normal scenario for the refresh grant.

## 4. HTTP Request and Verification Chain at the Token Endpoint

A confidential client using a refresh token typically sends a request to the token endpoint over HTTPS:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-of-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT-1&scope=orders.read
~~~

The snippet above uses placeholder values and contains no real credentials. In practice, the client ID/secret string must be encoded per OAuth 2.0 HTTP Basic rules and form values must be properly URL-encoded. Clients **must not** send refresh tokens in URL query strings, logs, or analytics.

Parameters:

| Parameter | Role |
| --- | --- |
| <code>grant_type=refresh_token</code> | Explicitly states the request uses the refresh grant. |
| <code>refresh_token</code> | The token value previously issued. |
| <code>scope</code> (optional) | Requested scopes for the new access token; must not exceed previously granted scopes. |
| Client authentication | Proves the confidential client is the registered client, e.g. <code>client_secret_basic</code> or <code>private_key_jwt</code>. |

Per RFC 6749, if <code>scope</code> is omitted, the request is treated as using the originally granted scope. If new scopes are sent, the server must verify no permissions exceed the old scope. Additionally, RFC 9700 requires binding the refresh token to the **resources** approved by the resource owner, even if the client tries changing the resource indicator in a refresh request.

### 4.1. From HTTP Request to Provider

~~~mermaid
sequenceDiagram
    autonumber
    participant C as orders-web
    participant F as OAuth2ClientAuthenticationFilter
    participant T as OAuth2TokenEndpointFilter
    participant P as OAuth2RefreshTokenAuthenticationProvider
    participant S as OAuth2AuthorizationService
    participant G as OAuth2TokenGenerator
    C->>F: POST /oauth2/token + client credentials + RT-1
    F->>F: Authenticate client against RegisteredClient
    F->>T: Proceed when client is valid
    T->>P: OAuth2RefreshTokenAuthenticationToken
    P->>S: findByToken(RT-1, REFRESH_TOKEN)
    S-->>P: OAuth2Authorization auth-1001
    P->>P: Compare RegisteredClient.id with authorization.registeredClientId
    P->>P: Check client is allowed to use refresh grant
    P->>P: Check refresh token active and scopes valid
    P->>G: Generate new access token (+ refresh token per settings)
    P->>S: Save updated OAuth2Authorization
    P-->>T: OAuth2AccessTokenAuthenticationToken
    T-->>C: JSON token response or OAuth error
~~~

The diagram depicts **key logical steps**, not a fixed ordering of every filter/context across all versions. In Spring Authorization Server, <code>OAuth2TokenEndpointFilter</code> uses <code>OAuth2RefreshTokenAuthenticationConverter</code> and <code>OAuth2RefreshTokenAuthenticationProvider</code> in the default token endpoint configuration. Client authentication runs through the Authorization Server's dedicated client authentication mechanism.

### 4.2. How the Provider Binds the Refresh Token to the Client

The crux of the default flow can be expressed with pseudocode closely tracking Spring's API:

~~~java
// Illustrates core logic; does NOT replace the real provider.
OAuth2ClientAuthenticationToken authenticatedClient =
    getAuthenticatedClientFromSecurityContext();
RegisteredClient client = authenticatedClient.getRegisteredClient();

OAuth2Authorization authorization = authorizationService.findByToken(
    presentedRefreshToken, OAuth2TokenType.REFRESH_TOKEN);

if (authorization == null) {
    reject("invalid_grant");
}

if (!client.getId().equals(authorization.getRegisteredClientId())) {
    reject("client/token binding mismatch");
}

if (!client.getAuthorizationGrantTypes()
        .contains(AuthorizationGrantType.REFRESH_TOKEN)) {
    reject("unauthorized_client");
}

OAuth2Authorization.Token<OAuth2RefreshToken> refresh =
    authorization.getRefreshToken();
if (refresh == null || !refresh.isActive()) {
    reject("invalid_grant");
}

Set<String> granted = authorization.getAuthorizedScopes();
Set<String> requested = requestedRefreshScopes.isEmpty()
    ? granted : requestedRefreshScopes;

if (!granted.containsAll(requested)) {
    reject("invalid_scope");
}

// Continue applying additional policies and issuing new tokens.
~~~

<code>getAuthenticatedClientFromSecurityContext()</code> and <code>reject(...)</code> are **explanatory pseudocode**, not ready-made Java methods to paste into a controller. Spring Authorization Server contains equivalent internal logic inside <code>OAuth2RefreshTokenAuthenticationProvider</code>. Exact error mapping for mismatches may vary by version; business logic must ensure the request is rejected rather than relying exclusively on the returned error name.

**Never write a separate custom <code>/refresh</code> endpoint that accepts a token string, calls <code>findByToken()</code>, and issues a JWT** without faithfully reproducing all client, grant, scope, resource, status, and replay checks. Reuse the framework's token endpoint and provider, adding only necessary policies through appropriate extension points.

## 5. Why Compare Internal IDs Instead of Protocol Client IDs?

Suppose:

~~~text
Client A:
  RegisteredClient.id       = "db-client-A"
  RegisteredClient.clientId = "orders-web"

Client B:
  RegisteredClient.id       = "db-client-B"
  RegisteredClient.clientId = "billing-web"

Authorization auth-1001:
  registeredClientId = "db-client-A"
  principalName      = "user-42"
  refreshToken        = "RT-1"
~~~

When <code>billing-web</code> authenticates successfully with its own secret and sends <code>RT-1</code>, the repository may locate <code>auth-1001</code> (since the token exists), yet **the current client is not the client issued RT-1**:

~~~java
boolean sameClient = registeredClient.getId()
    .equals(authorization.getRegisteredClientId());

// "db-client-B".equals("db-client-A") => false
~~~

The Authorization Server must reject it. The fact that <code>billing-web</code> shares the same issuer, the same user Alice, or has <code>orders.read</code> in its registered scope list **does not validate another client's refresh token**.

### 5.1. When Can Binding Fail Even When <code>client_id</code> Looks Identical?

Several edge cases:

- **Faulty ID migration:** Client <code>orders-web</code> was recreated with a new <code>RegisteredClient.id</code>. Old authorizations still reference the old ID; do not automatically rewrite client bindings based solely on display client ID strings.
- **Multi-tenancy:** Two tenants share the same client ID name but require separate registration partitions. If sharing a repository/issuer, internal keys and access boundaries must be strictly isolated.
- **Database restore:** Restoring authorizations while omitting registered clients, or restoring from a cross-environment backup with mismatched colliding IDs; verify consistency on restore.
- **Custom token store:** A repository returns an authorization by token value without checking token type or returns the wrong record. The provider may trust the service lookup result; this is a severe data-layer bug.

**Never "fix" mismatch errors by removing the <code>getRegisteredClientId()</code> comparison.** Restore the proper mapping via controlled migration, or invalidate old authorizations and require users to re-authorize.

### 5.2. Client Authentication Does Not Replace Token Binding

A confidential client authenticating successfully only proves it is **a valid client**, not that the refresh token was issued to it. All conditions must hold simultaneously:

~~~text
authenticatedClient == registered client
AND
authorization.registeredClientId == authenticatedClient.registeredClient.id
AND
authorization holds the matching active refresh token
~~~

For public clients, merely declaring <code>client_id</code> is not proof of secret protection. RFC 9700 requires public client refresh tokens to be **sender-constrained or rotated** with replay detection. Verify under what conditions your Spring Authorization Server version issues refresh tokens to public clients; never treat a public client registration having the <code>refresh_token</code> grant as proof of compliance.

## 6. Validating the Authorization, Status, and Scopes

### 6.1. Looking Up the Exact Presented Token and Token Type

Standard Spring API:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        tokenValue, OAuth2TokenType.REFRESH_TOKEN);
~~~

<code>OAuth2AuthorizationService.findByToken(String, OAuth2TokenType)</code> must look up the exact submitted token within the **refresh token** category, never confusing it with an access token, authorization code, or ID Token.

In a custom JDBC/JPA implementation, verify:

1. Queries parameterize both token type and token value properly.
2. No authorization is returned unless the token value exactly matches the record's refresh token.
3. Never look up solely by <code>principalName</code>, <code>client_id</code>, or a client-supplied authorization ID.
4. Never return a corrupted authorization record or inconsistent token metadata.
5. Token store read/write permissions are restricted; avoid logging raw tokens, passwords/secrets, or bearer credentials.

If using opaque tokens, **entropy/unpredictability** must be high and the store must protect token values. If using another token format, verify cryptographic integrity and authorization binding before trusting self-asserted token contents.

### 6.2. The Token Must Still Be Active

~~~java
OAuth2Authorization.Token<OAuth2RefreshToken> tokenState =
    authorization.getRefreshToken();

boolean valid = tokenState != null
    && tokenState.isActive()
    && tokenValue.equals(tokenState.getToken().getTokenValue());
~~~

Comparing <code>tokenValue</code> in this example clarifies the **exact-token** invariant if you build custom validation/storage. When using the standard provider, ensure <code>findByToken()</code> upholds accurate semantics; do not re-implement provider logic inside controllers.

A token is no longer valid if expired or invalidated. A refresh token replaced by rotation must also not continue issuing new tokens. Other states, such as a locked account or revoked tenant policy, may require extra checks beyond <code>isActive()</code>.

### 6.3. New Scopes Must Not Exceed Old Scopes

If the authorization stores:

~~~text
authorizedScopes = {"orders.read", "orders.write"}
~~~

then a refresh request with <code>scope=orders.read</code> is a downscoping request; a request with <code>scope=orders.read billing.admin</code> must be rejected because it includes a scope that was never granted. Omitting scope in the request normally uses the originally granted scopes per RFC 6749.

For dynamic permission revocation policies, checking the old scope set alone is insufficient. For example, an admin removed <code>orders.write</code> from Alice or <code>orders-web</code>; if that permission must no longer be issued, integrate policy checks restricting new tokens to **current permissions**, while handling old authorizations/refresh tokens per design.

### 6.4. Resource and Audience Restrictions

RFC 9700 requires refresh tokens to be bound to the scopes **and resource servers** permitted by the resource owner. If the original authorization was only for Orders API, the client must not use the same refresh token to request a token for Billing API merely by altering the <code>resource</code> parameter (RFC 8707) or audience.

In Spring Authorization Server, you may need to store/cross-check the **resource indicator** in the authorization and enforce access token audience issuance policies. Do not assume the framework automatically enforces all of RFC 8707 just because a client sends a <code>resource</code> parameter, and never copy client-supplied URIs verbatim into <code>aud</code> without validation.

## 7. Configuring Clients and Refresh Tokens in Spring Authorization Server

### 7.1. Registering a Client Allowed to Use the Refresh Grant

Example of a **confidential web client**:

~~~java
RegisteredClient ordersWeb = RegisteredClient
    .withId("client-record-A")
    .clientId("orders-web")
    .clientSecret(encodedClientSecret) // Securely hashed from secret manager.
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://orders.example.com/login/oauth2/code/orders-web")
    .scope("openid")
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .requireProofKey(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build())
    .build();
~~~

<code>encodedClientSecret</code> is a secret **hashed with an appropriate PasswordEncoder** and provided from a secure source; never place real passwords/secrets in documentation or Git. This configuration pattern is for a **server-side confidential client**; do not use client secrets in SPAs/mobile apps.

Related conditions:

- <code>AuthorizationGrantType.REFRESH_TOKEN</code> must appear in the registration to use the refresh grant.
- <code>TokenSettings.refreshTokenTimeToLive(...)</code> sets the TTL of server-issued refresh tokens.
- <code>TokenSettings.reuseRefreshTokens(false)</code> requests creating a new refresh token upon successful refresh rather than reusing the same value.
- <code>ClientSettings.requireProofKey(true)</code> applies PKCE to the authorization flow; it does not bind a refresh token to a single client instance.
- <code>requireAuthorizationConsent(true)</code> governs the corresponding consent step; **persisted consent and active refresh tokens have distinct lifecycles**.

The 10-minute and 7-day values are illustrative; choose TTLs based on risk, client type, login policies, token storage, and required revocation windows.

### 7.2. Bean Holding Authorization State

For testing environments:

~~~java
@Bean
OAuth2AuthorizationService authorizationService() {
    return new InMemoryOAuth2AuthorizationService();
}
~~~

For a JDBC application with the corresponding schema, switch to:

~~~java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbc,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(jdbc, registeredClients);
}
~~~

**Note:** These are mutually exclusive alternatives; **never declare two beans of the same type in one application** expecting the token endpoint to distinguish them automatically. JDBC requires the <code>oauth2_authorization</code> table and library-version-matched schema, migrations, connection pooling, and DB permissions. <code>JdbcOAuth2AuthorizationService</code> persists both authorization context and metadata for multiple token types; it is not designed as a table storing only refresh token values.

To run multiple Authorization Server instances, every node must share a valid authorization store, consistent client registration/issuer/key configurations, and appropriate transaction policies.

### 7.3. SecurityFilterChain for the Token Endpoint

Token refreshes should continue passing through the Authorization Server's default chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer as =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(as.getEndpointsMatcher())
        .with(as, Customizer.withDefaults())
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    return http.build();
}
~~~

This is a **configuration skeleton**; the application needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, a token generator, JWK/decoder if OIDC is enabled, and related beans. <code>getEndpointsMatcher()</code> ensures the AS chain matches protocol endpoints properly. <code>oauth2/token</code> is handled by the token endpoint filter, where providers validate the client and refresh token.

Never "fix" refresh errors by adding <code>requestMatchers("/oauth2/token").permitAll()</code> or bypassing client authentication. <code>permitAll()</code> is an HTTP authorization rule; it does not replace the token endpoint's OAuth validations.

### 7.4. OIDC Flow During Refresh

An OIDC authorization may contain an ID Token and other tokens; the refresh grant serves to issue new access tokens and, depending on configuration, may issue a new ID Token per OIDC rules. However, **refreshing does not force the user to re-login**, does not automatically check account-locked status, and is not a way to use an ID Token for client authentication.

If policy requires <code>max_age</code>, MFA, session state, or re-authentication, design explicit checkpoints matching OIDC specifications and your application.

## 8. Rotation, Replay Detection, and Authorization Lineage

### 8.1. What Does <code>reuseRefreshTokens(false)</code> Do?

~~~mermaid
sequenceDiagram
    autonumber
    participant C as orders-web
    participant AS as Authorization Server
    participant DB as Authorization Store
    C->>AS: Send RT-1
    AS->>DB: Look up RT-1 and verify client + authorization
    DB-->>AS: RT-1 active, belongs to client-record-A
    AS->>AS: Generate AT-2 and RT-2
    AS->>DB: Save authorization with new refresh token
    AS-->>C: Return AT-2 + RT-2
    Note over C,DB: RT-1 must no longer succeed for future refreshes
~~~

When <code>reuseRefreshTokens(false)</code>, the framework generates a new refresh token in a successful refresh response. The client must **replace the old token with the new token** in secure storage. This is **rotation** at the issuance level.

**Distinguish rotation from complete replay detection:** if you merely overwrite the active refresh token value and discard traces of the old token, a request reusing <code>RT-1</code> may simply receive <code>invalid_grant</code> without the server knowing which family it belonged to in order to revoke <code>RT-2</code>. RFC 9700 requires mechanisms **maintaining token-family relationships and handling replay** for public clients choosing rotation over sender-constrained tokens. Never treat setting <code>reuseRefreshTokens(false)</code> as proof the framework automatically implements full stolen-token-family detection across multiple nodes.

### 8.2. Designing Lineage and Replay Detection When Required

A custom refresh token family store might require fields such as:

| Field | Role |
| --- | --- |
| <code>family_id</code> | Groups refresh tokens originating from the same authorization/grant. |
| <code>authorization_id</code> | Original authorization ID. |
| <code>registered_client_id</code> | Client owning the family. |
| <code>token_hash</code> | One-way token digest for identification without storing raw tokens in logs/audits. |
| <code>generation</code>, <code>parent_token_id</code> | Ordering relationship between tokens. |
| <code>status</code> | Active / rotated / revoked / replay_detected. |
| <code>issued_at</code>, <code>expires_at</code> | Time bounds and data cleanup. |

These are **application-specific data suggestions**, not Spring Authorization Server's default schema. Upon detecting reuse of an already-rotated refresh token, the server must mark the family compromised and revoke active tokens per policy. Distinguish harmless concurrent retries caused by network glitches from suspected replay, without opening an uncontrolled "grace period" that lets attackers reuse tokens successfully.

### 8.3. Race Conditions Under Two Concurrent Refresh Requests

Suppose two instances receive the same <code>RT-1</code> nearly simultaneously:

~~~text
Node A: reads RT-1 active
Node B: reads RT-1 active
Node A: issues RT-2 and saves
Node B: issues RT-3 and saves
Client: may only receive RT-2 (while DB holds RT-3)
~~~

Without locking/optimistic versioning or an **atomic compare-and-update** mechanism, both requests can pass active checks before the old token is replaced. Consequences include dual issuance, losing valid tokens, and obscured replay detection. In multi-instance systems, test with a real database and design **marking the used token + creating the next token** atomically per authorization/family. Never solve this with <code>synchronized</code> inside a single JVM.

### 8.4. Sender-Constrained Refresh Tokens

Per RFC 9700, public clients can satisfy replay protection using **sender-constrained refresh tokens** instead of rotation, such as DPoP (RFC 9449) or mTLS (RFC 8705) where applicable. If implemented, bind the token to the key/certificate material of the specific client instance and verify the proof on every refresh request. Form-submitted <code>client_id</code> is **not** a sender constraint.

Support and completeness of DPoP/mTLS refresh tokens depend on framework version, configuration, and infrastructure; do not claim flipping a single property automatically fulfills RFC 9700.

## 9. Revoking Authorizations and User/Client State Changes

### 9.1. Deleting Consent Does Not Equal Revoking Refresh Tokens

<code>OAuth2AuthorizationConsentService</code> stores user consent for a registered client; <code>OAuth2AuthorizationService</code> stores issued authorizations/tokens. If a user clicks "Disconnect application," deleting only the consent record **does not automatically** invalidate refresh tokens in the authorization store. Decide whether product policy requires blocking refreshes immediately; if so, revoke related authorizations/tokens or enforce centralized state checks.

### 9.2. User Locked or Disabled After Refresh Token Issuance

The refresh grant normally **does not require re-entering the End-User's password**. A disabled account in the database will not necessarily make <code>OAuth2RefreshTokenAuthenticationProvider</code> re-invoke <code>UserDetailsService</code>. If policy requires blocking new tokens after locking an account:

1. Identify the authorization's principal/tenant using trusted stored data, not from the request body.
2. Verify latest account status at an appropriate refresh/issuance hook, or revoke all related authorizations/refresh tokens.
3. Prevent races between account disabling and refreshing using a consistent, testable mechanism.
4. Handle already-issued JWT access tokens via TTL/denylist/introspection strategies; deleting a refresh token does not expire an offline JWT already issued.

**Note:** Querying all authorizations for a user **is not defined by a standard <code>findAllByPrincipalName()</code> method on the <code>OAuth2AuthorizationService</code> interface**. Projects must add custom repositories/queries or revocation workflows rather than arbitrarily scanning the entire token store inside the token endpoint.

### 9.3. Client Deleted or Registration Modified

If <code>orders-web</code> is disabled, stripped of the refresh grant, or removed from the repository, the server must stop issuing tokens from old authorizations per policy. Never recreate a client with a different <code>RegisteredClient.id</code> and expect old tokens to still belong to it. Rotating secrets for confidential clients must also ensure refresh requests use currently valid client authentication methods.

### 9.4. Revocation Endpoint and Already-Issued Tokens

RFC 7009 describes the revocation endpoint: the client presents a token to revoke, and the server applies authentication and client-ownership checks. It **does not provide a built-in button** to delete all refresh tokens for a user across every client. When building an admin "Revoke all sessions" feature, define how to query authorizations by principal/tenant, handle token families, transactions, auditing, and effective enforcement at Resource Servers.

## 10. Testing Bindings with Code and Real Requests

### 10.1. Unit Test: Authorization Bound to the Right Client Record ID

Example using an in-memory authorization service to demonstrate the data model and lookup; this is **not** a full token endpoint test:

~~~java
@Test
void refreshTokenRecordBelongsToRegisteredClient() {
    RegisteredClient clientA = RegisteredClient.withId("client-record-A")
        .clientId("orders-web")
        .clientSecret("{noop}test-only-secret")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://orders.example.com/callback")
        .scope("orders.read")
        .build();

    Instant now = Instant.now();
    OAuth2RefreshToken rt = new OAuth2RefreshToken(
        "test-refresh-value", now, now.plusSeconds(600));
    OAuth2Authorization authorization =
        OAuth2Authorization.withRegisteredClient(clientA)
            .principalName("user-42")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizedScopes(Set.of("orders.read"))
            .refreshToken(rt)
            .build();

    OAuth2AuthorizationService service =
        new InMemoryOAuth2AuthorizationService();
    service.save(authorization);

    OAuth2Authorization found = service.findByToken(
        "test-refresh-value", OAuth2TokenType.REFRESH_TOKEN);

    assertThat(found).isNotNull();
    assertThat(found.getRegisteredClientId()).isEqualTo(clientA.getId());
    assertThat(found.getRefreshToken().isActive()).isTrue();
    assertThat(service.findByToken(
        "unknown-value", OAuth2TokenType.REFRESH_TOKEN)).isNull();
}
~~~

This test proves the repository returns the authorization containing the right refresh token and client ID. It **does not** prove the token endpoint rejected Client B; to verify client binding at the provider, write an **integration test going through the token endpoint and client authentication**.

### 10.2. Integration Test: Client A Allowed, Client B Rejected

Test scenario:

1. Register <code>orders-web</code> and <code>billing-web</code> as two confidential clients **with distinct record IDs**, separate secrets, and appropriate refresh grants.
2. Create a real authorization for <code>orders-web</code> with refresh token <code>RT-1</code>, <code>authorizedScopes = {orders.read}</code>, active state.
3. Send <code>POST /oauth2/token</code> with <code>grant_type=refresh_token</code>, <code>RT-1</code>, and **billing-web**'s client authentication.
4. Verify the request **receives no access token** and authorization state is not improperly altered; exact OAuth error code depends on version/provider.
5. Send the same request with **orders-web** client authentication and valid scopes; if no policy blocks it, receive a new access token and refresh token per <code>TokenSettings</code>.
6. Verify the new JWT/access token has the right issuer, audience, and scopes; never use an ID Token to call APIs.

For the test to be meaningful, keep the real filter chain and provider intact—never use a mock <code>Authentication</code> marking the client as authenticated and conclude client authentication works. Use <code>MockMvc</code> or an HTTP integration test; keep client/authorization services and token stores under controlled test fixtures.

### 10.3. Test Matrix

| Condition | Expected outcome |
| --- | --- |
| Token active, belongs to Client A, valid scopes | Refresh succeeds if other policies permit. |
| Token belongs to Client A but request authenticates as Client B | Rejected; no token issued. |
| Token absent from <code>OAuth2AuthorizationService</code> | <code>invalid_grant</code> or appropriate protocol error. |
| Repository returns an authorization lacking the exact refresh token | No token issued; catch data access bug. |
| Token expired | Rejected, typically <code>invalid_grant</code>. |
| Token invalidated/revoked | Rejected; never reactivated by a refresh request. |
| Client lost permission to use refresh grant | Rejected even if token is unexpired. |
| Requested scope is a granted subset | Issues token with valid scopes per policy. |
| Requested scope includes ungranted permission | <code>invalid_scope</code> or corresponding error; no privilege escalation. |
| Resource indicator changed from Orders API to Billing API | Reject unapproved resource scope. |
| Comparing <code>clientId</code> instead of <code>getId()</code> for binding | Test catches schema/binding mismatch. |
| Client record ID changed after migration | Detect orphaned authorization; do not bypass binding. |
| Old refresh token resubmitted after rotation | Must not issue tokens again; if replay detection exists, handle family. |
| Two concurrent refresh requests | Must not both issue valid new refresh tokens off-policy. |
| User disabled or tenant locked | Block refresh if policy requires checking current status. |
| Account session logged out while refresh token remains | Behavior follows revocation policy; never assume logout deletes refreshes automatically. |
| Two instances sharing a database | No rotation race; consistent state. |
| Token stolen, credentials exposed in logs/proxy | Detect, revoke, rotate secrets, and investigate per runbook. |

### 10.4. Testing Custom Repositories with Malformed Data

If a project writes a custom <code>OAuth2AuthorizationService</code> (JPA/Redis/Cassandra), add tests verifying:

- <code>findByToken(value, REFRESH_TOKEN)</code> returns a record only when **both token type and value** match.
- An authorization with a nonexistent <code>registeredClientId</code> is handled safely, never issuing tokens to a similarly named client.
- Inconsistent or undeserializable token metadata is rejected rather than defaulted to active.
- No divergent results occur across nodes sharing an authorization store.
- Concurrent rotation/revocation updates use genuine optimistic locking/transactions.

Never test by manually editing a client ID inside a token and assuming the access token's JWT signature proves refresh token binding; the two token types and state stores serve different roles.

## 11. Common Design Mistakes

### Mistake 1: Only Checking That a Refresh Token Exists and Issuing Tokens

<code>findByToken()</code> returning an authorization is **the first step**. You must cross-check registered client ID, refresh grant, active token status, scopes/resources, and additional policies. If building a custom provider, never skip any fundamental security check.

### Mistake 2: Comparing the Wrong Client Identifier

Comparing <code>authorization.getRegisteredClientId()</code> against <code>registeredClient.getClientId()</code> fails whenever internal IDs differ from protocol client IDs. Compare against <code>getId()</code> and keep IDs stable across migrations.

### Mistake 3: Treating a Refresh Token as a Self-Validating JWT

Even if a refresh token is represented in a signed format, check status, revocation, client/authorization binding, scopes, and sender constraints per policy. A self-asserted JWT payload does not replace authoritative authorization data.

### Mistake 4: Assuming Rotation Detects Every Replay

<code>reuseRefreshTokens(false)</code> makes the framework generate a new token, whereas detecting replay and revoking the whole family requires storing old/new token relationships, recognizing reuse, and performing atomic updates. This is especially critical for public clients per RFC 9700.

### Mistake 5: Skipping Resource/Audience Checks on Refresh

A refresh token issued for Orders API is not a license to switch to Billing API just because the client sends a new <code>resource</code> parameter. Enforce consented resource bindings per RFC 9700 and implement explicit checks.

### Mistake 6: Assuming Logout/Disabling a User Revokes Tokens

Login sessions, consent, authorizations, and refresh tokens have distinct lifecycles. Logging out or disabling an account does not automatically invalidate old JWT access tokens. If rapid disconnection is required, enforce token revocation/TTL/introspection or status checks.

### Mistake 7: Logging Raw Tokens in Logs and Audit Tables

Refresh tokens are bearer credentials. Never write them to URLs, logs, exception messages, tracing baggage, or analytics events. When security tracing is needed, use controlled token IDs/hashes with restricted data access policies.

### Mistake 8: Testing with Mock Authentication and Declaring Security

Repository unit tests only prove mapping. A mocked authenticated principal can bypass client credential validation. You need at least one integration test sending real HTTP refresh requests with two differently credentialed clients to prove binding at the token endpoint.

## 12. Production Operations

A complete deployment must answer:

| Area | Control question |
| --- | --- |
| Client registration | Are internal IDs stable? Does the client hold the refresh grant? Are secrets/certs/keys securely managed? |
| Authorization store | Does it store refresh tokens with the right authorization, scopes, client ID, and metadata? |
| Transactions | Can concurrent refreshes issue two new tokens or overwrite one another? |
| Rotation/replay | Is enough token-family lineage kept to detect reuse and revoke the family when needed? |
| TTL | Are idle expiry, max lifetime, and policies preventing infinite family extension defined? |
| Resource restriction | Can a refresh be used on an API outside the original audience/resource? |
| Revocation | Are disabled accounts, password resets, consent revocations, and revoked tokens handled as required? |
| Multi-node | Do instances share DB/state cache, issuer, keys, and locking strategy? |
| Logging | Are refresh tokens, client secrets, authorization codes, and sensitive data redacted? |
| Client behavior | Does the client store new tokens safely, replace old ones, and avoid concurrent refreshes? |
| Tests/monitoring | Are wrong-client, replay, scope/resource escalation, and anomaly alerts tested and active? |

For confidential web clients, keep refresh tokens on the backend or in access-controlled storage, avoiding browser localStorage. If using public clients, rigorously assess token extraction risks and satisfy RFC 9700's sender-constrained or rotation-with-replay-detection requirements. Token lifetimes and resource policies must match data sensitivity.

## 13. Applied Exercises

A system has three clients—<code>orders-web</code>, <code>billing-web</code>, and <code>mobile-public</code>—sharing one Authorization Server. Alice grants <code>orders.read</code> to <code>orders-web</code> and receives refresh token <code>RT-1</code>. An hour later, the token is refreshed, and the server team is evaluating rotation configuration.

1. Design the corresponding <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, and <code>OAuth2RefreshToken</code> records, highlighting how <code>RegisteredClient.id</code> and <code>clientId</code> differ.
2. Describe the verification sequence when <code>billing-web</code> sends <code>RT-1</code> with its own valid client authentication. What must the outcome be?
3. Write code using <code>OAuth2AuthorizationService.findByToken(..., REFRESH_TOKEN)</code> checking client ID, token status, and <code>authorizedScopes</code>; mark which parts are pseudocode and which are real Spring APIs.
4. The client requests <code>scope=orders.read billing.admin</code> using <code>RT-1</code>. State the rejection policy and how to test it.
5. If <code>RT-1</code> is rotated to <code>RT-2</code>, describe the lineage storage required to detect reuse of <code>RT-1</code>, along with behavior under two concurrent requests.
6. Propose resource constraints for when <code>orders-web</code> attempts to obtain an access token for Billing API using the original refresh token.
7. Choose a refresh token protection strategy for <code>mobile-public</code> per RFC 9700, explaining the sender-constraint or rotation requirements.
8. Design the workflow to disable Alice and revoke refresh tokens across all related clients while Orders API validates JWT access tokens offline.
9. Write an integration test hitting the real token endpoint to guarantee Client B cannot exchange a refresh token belonging to Client A.

A passing solution must prove that **a refresh token belongs only to its exact authorization**, **the authorization belongs only to its exact registered client**, **scopes/resources never escalate beyond granted permissions**, and **revoked, expired, or replayed tokens cannot continue issuing new permissions outside policy**.

## 14. Reference Documentation

- [RFC 6749, §6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): client authentication, refresh token binding, scopes on refresh, and new token issuance behavior.
- [RFC 6749, §10.4 — Refresh Tokens](https://www.rfc-editor.org/rfc/rfc6749#section-10.4): keeping tokens confidential, TLS, and client binding.
- [RFC 9700, §4.14 — Refresh Token Protection](https://www.rfc-editor.org/rfc/rfc9700#section-4.14): best current practice on scope/resource binding, rotation, replay, and public clients.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint and error model.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource parameters and resource-restricted tokens.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens via application-layer proofs.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, <code>OAuth2AuthorizationService</code>, token metadata.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): token endpoint and providers handling the refresh grant.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): Java DSL and extending the token endpoint.
- [Spring Authorization Server — JPA Core Services Guide](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): mapping authorizations, client IDs, and tokens in persistence.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): <code>refreshTokenTimeToLive</code> and <code>reuseRefreshTokens</code>.
