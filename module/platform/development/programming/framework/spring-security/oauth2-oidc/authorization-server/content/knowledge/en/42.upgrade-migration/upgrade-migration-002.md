# Migrating from Legacy Spring Security OAuth to Current Authorization Server

Legacy Spring Security OAuth (often referred to as Spring Security OAuth 2.x) and Spring Authorization Server have different models for configuration, storage, and token handling. The transition should therefore be treated as an authentication system migration, not merely a dependency swap or endpoint URL change.

Legacy Spring Security OAuth has been superseded in the Spring ecosystem. Spring Authorization Server provides the new foundation for implementing OAuth 2.0 and OpenID Connect, integrated with modern Spring Security. The goal of this article is to help you plan and execute a controlled migration: maintaining compatibility with clients and resource servers, migrating client registrations and consents, handling still-valid tokens, replacing legacy extension points, and testing before shifting traffic.

## 1. Understanding the Scope of Change

In the legacy system, an authorization server was typically configured using classes such as **@EnableAuthorizationServer**, **AuthorizationServerConfigurerAdapter**, **AuthorizationServerEndpointsConfigurer**, **AuthorizationServerSecurityConfigurer**, and **ClientDetailsServiceConfigurer**. Tokens were issued and managed through **DefaultTokenServices**, **TokenStore**, **OAuth2Request**, **OAuth2Authentication**, and related implementations.

On the new platform, configuration is organized around **SecurityFilterChain**, **OAuth2AuthorizationServerConfigurer**, **RegisteredClientRepository**, **OAuth2AuthorizationService**, **OAuth2AuthorizationConsentService**, **OAuth2TokenGenerator**, and **AuthorizationServerSettings**.

The business concepts remain familiar: client, redirect URI, scope, authorization code, access token, refresh token, and consent. However, object structures, storage schemas, endpoint extension mechanisms, and several security defaults have changed. Java-serialized data from the legacy system cannot be assumed to be directly compatible with the new system.

### 1.1 Legacy-to-New Concept Map

| Legacy Spring Security OAuth | Spring Authorization Server | Action Required |
|---|---|---|
| @EnableAuthorizationServer | SecurityFilterChain dedicated to authorization server endpoints | Create a filter chain with the appropriate matcher and order |
| AuthorizationServerConfigurerAdapter | OAuth2AuthorizationServerConfigurer along with configuration beans | Migrate each customization to the new API |
| ClientDetailsService | RegisteredClientRepository | Migrate clients, grants, authentication methods, redirect URIs, and scopes |
| ClientDetailsServiceConfigurer | In-memory, JDBC, or custom repository implementation | Choose where to store clients and manage schema |
| AuthorizationServerEndpointsConfigurer | Endpoints and extension points of authorization server configurer | Migrate converters, providers, token generators, and custom endpoints |
| TokenStore | OAuth2AuthorizationService combined with token generator | Determine how authorizations are stored and token formats |
| DefaultTokenServices | OAuth2TokenGenerator and grant-handling providers | Migrate issuance policies, TTL, refresh, and revocation |
| OAuth2Authentication | OAuth2Authorization, Authentication, and token issuance context | Migrate principal, scope, and claim logic |
| ApprovalStore / approval records | OAuth2AuthorizationConsentService | Map consents by client and principal |
| ResourceServerConfigurerAdapter / @EnableResourceServer | SecurityFilterChain with oauth2ResourceServer | Migrate resource servers independently |
| OAuth2RestTemplate | Spring Security OAuth2 Client and OAuth2AuthorizedClientManager | Migrate API-calling applications |

This table is a conceptual map, not a one-to-one mapping for every implementation. For example, a legacy TokenStore might store JWTs, opaque tokens, or data in Redis; the right migration approach depends on the token type and how resource servers currently verify tokens.

### 1.2 Identifying Components in Scope

An OAuth system typically involves multiple applications and data stores. Before modifying code, list:

- Authorization Server: endpoints, grant types, client registry, consent, token store, signing keys, and custom grants.
- Resource Server: how JWTs are verified or introspected, mapping scopes to authorities, issuer and audience validation.
- OAuth2 Client: how tokens are obtained, authorized client storage, token refresh, and login handling.
- User-facing applications: login, consent, session, redirect URI, and logout.
- Infrastructure: database, Redis, KMS/HSM, reverse proxy, gateway, DNS, and TLS.
- Operational systems: logs, audit, metrics, alerts, backups, and token revocation procedures.

A client may still be able to call the token endpoint while downstream APIs reject the token because the issuer, audience, signature, or claims changed. Therefore, testing only the authorization server is insufficient.

## 2. Inventorying Legacy Configuration and Behavior

Create an inventory from running configuration and actual data. Do not rely solely on configuration files, as clients may be created dynamically in the database or via an admin console.

For each client, record:

| Attribute | Details to Collect |
|---|---|
| Client ID | Current identifier and owning system |
| Client secret | Storage method, encryption/hashing algorithm, and rotation schedule |
| Client authentication | Basic, form post, public client, or custom mechanism |
| Grant type | Authorization Code, Client Credentials, Refresh Token, and extended grants |
| Redirect URI | Exact list, environment, and owner |
| Scope | Granted scopes, defaults, and approval rules |
| Token policy | Access token TTL, refresh token TTL, reuse/rotation, and token format |
| Consent | Approval status, timestamp, and associated principal |
| Customization | Claims, converters, token enhancers, exception handlers, and custom endpoints |

Also inspect global configurations: issuer, public URL behind a reverse proxy, signing keys, access token converters, authentication manager, password encoder, CORS, CSRF, session policy, and error handling.

For each flow, save requests and responses with secrets scrubbed. A minimal sample set should include:

- Client Credentials success and failure.
- Authorization Code with PKCE, including wrong redirect URI cases.
- Refresh token success, expired, revoked, and reuse cases.
- Introspection or resource server token verification.
- Revocation.
- OIDC discovery, JWKS, UserInfo, and logout if OpenID Connect is enabled.
- `invalid_client`, `invalid_grant`, `invalid_scope`, and consent error cases.

These samples will become the regression test suite for the new system.

## 3. Planning Client and Resource Server Compatibility

### 3.1 Endpoints May Change

Common default endpoints in the legacy system include /oauth/authorize, /oauth/token, /oauth/check_token, and /oauth/token_key. Spring Authorization Server commonly uses /oauth2/authorize, /oauth2/token, /oauth2/introspect, /oauth2/revoke, and /oauth2/jwks. OIDC endpoints are exposed when OIDC is enabled and depend on server configuration.

Do not assume new URLs are automatically compatible with legacy clients. There are three ways to handle this:

1. Update clients to use the new endpoints and roll out in batches.
2. Use a reverse proxy or gateway to route legacy URLs to the right system during the transition period, after confirming request/response compatibility.
3. Keep legacy endpoints on the legacy authorization server for a period while onboarding clients onto the new server along a clear timeline.

Do not build a simple URL-rewriting proxy and consider the migration complete. You must verify that client authentication methods, parameters, error formats, token responses, and introspection mechanisms are genuinely compatible.

### 3.2 Keep the Issuer Stable When Possible

The issuer is the identifier of the authorization server and usually appears in the JWT `iss` claim, discovery metadata, and resource server configuration. If the issuer changes, resource servers may reject tokens even when the signature is valid.

If keeping the legacy issuer, ensure the public URL and the new server's issuer configuration match exactly. Configuration behind a proxy must reflect the public scheme, host, and context path; do not let the server infer the issuer as an internal address.

If changing the issuer is unavoidable, plan updates for clients, resource servers, discovery caches, allowlists, and monitoring. During the transition period, resource servers should accept both the old and new issuers only intentionally, with a time limit and separate validation per issuer.

### 3.3 Maintaining Token Compatibility

Classify the tokens in use:

- **JWT access token:** check signing algorithm, kid, issuer, audience, subject, scope, expiration, and custom claims.
- **Opaque access token:** requires a state store or introspection endpoint to verify. You cannot move a legacy opaque string into the new authorization store simply by copying its value.
- **Refresh token:** usually tied to an authorization record and rotation policy. Legacy refresh token data is not implicitly usable in the new authorization service.
- **Authorization code:** short-lived, single-use, and bound to redirect URI/PKCE. Pending codes should not be migrated as long-lived data.

For JWTs, resource servers need to continue verifying legacy tokens until they expire or are revoked according to policy. If changing signing keys, you can publish both old and new public keys in JWKS during the transition window. Keep the kid stable for the old key and do not reuse a kid for another key. Only remove the old public key after no valid tokens signed by that key remain.

For opaque tokens, you can continue using the legacy authorization server to introspect old tokens during the transition window, while new tokens are verified through the new server. Resource servers need to route by token source or according to an agreed endpoint configuration. Do not send all tokens to a single introspection endpoint if that endpoint does not understand the corresponding token store.

## 4. Migrating Client Registrations

RegisteredClient describes a client in the new structure. When creating records, transfer completely:

- Client ID and secret converted to a compatible password encoder format.
- Client authentication method.
- Authorization grant type.
- Redirect URIs and post-logout redirect URIs if using OIDC logout.
- Scopes.
- Client settings, including PKCE and consent requirements.
- Token settings, including access token TTL, refresh token TTL, access token format, and refresh token reuse policy.

The example below illustrates a service client using Client Credentials in an in-memory repository. This is a configuration example to understand the model; production systems should load clients from a managed store rather than generating a new random secret on every startup.

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(PasswordEncoder passwordEncoder) {
    RegisteredClient billingClient = RegisteredClient.withId(
            UUID.randomUUID().toString())
        .clientId("billing-service")
        .clientSecret(passwordEncoder.encode("load-from-a-secret-manager"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("invoice.read")
        .tokenSettings(TokenSettings.builder()
            .accessTokenTimeToLive(Duration.ofMinutes(10))
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(billingClient);
}
~~~

When migrating client secrets, confirm that the new system's password encoder can verify the stored format accurately. If legacy secrets were stored in plaintext, do not copy plaintext into the new database. You can require clients to rotate secrets or execute a controlled conversion process with restricted access and auditing. A `{noop}` value is only appropriate for isolated testing, never for production.

For public clients, do not create a dummy client secret. Configure the appropriate client authentication method for public clients and enforce PKCE per policy. Validate exact redirect URIs; do not relax them to wildcards to avoid updating clients.

### 4.1 Grant Type Mapping

| Grant in Legacy System | Handling in New System |
|---|---|
| authorization_code | Register Authorization Code; require PKCE, especially for public clients |
| client_credentials | Register Client Credentials and restrict scopes per service |
| refresh_token | Enable Refresh Token with appropriate TTL and rotation policy |
| password | Move to Authorization Code + PKCE or an appropriate login model; do not recreate the password grant in the new system |
| implicit | Move to Authorization Code + PKCE |
| Custom grant | Re-evaluate the business need and implement corresponding extension points if truly necessary |

Resource Owner Password Credentials (password grant) and implicit grant do not belong in the flows recommended for continued use in the new architecture. For user-facing applications, Authorization Code + PKCE is the standard replacement. For service-to-service, use Client Credentials or an appropriate workload identity mechanism.

If the system has a custom grant, document precisely how client authentication, credential verification, scope checking, principal creation, and token issuance work. Spring Authorization Server supports extension via authentication converters, authentication providers, and token generators. Do not port legacy logic verbatim without reviewing its threat model and OAuth compatibility.

## 5. Migrating Authorizations, Consents, and Token Stores

This is usually the most complex part. The old and new schemas may store the same business state in completely different ways.

### 5.1 Distinguishing Data Types

| Legacy Data | Handling During Migration |
|---|---|
| Client registration | Convert to RegisteredClient and re-verify configuration |
| Approval / consent | Map principal, client, and scope; verify the meaning of each status |
| Authorization code | Typically let expire on the legacy system; do not migrate active codes without a verified compatibility mechanism |
| JWT access token | Continue verifying with old keys and claims until expiration or revocation |
| Opaque access token | Continue introspecting from the legacy store or let expire per plan |
| Refresh token | Continue processing on the issuing system or require re-authentication/re-authorization on schedule |
| Revocation state | Ensure resource servers still observe revocation status during the transition window |

Tables such as oauth_client_details, oauth_access_token, oauth_refresh_token, oauth_code, and oauth_approvals commonly appear in legacy deployments, though table names and column types may have been customized. Spring Authorization Server provides its own JDBC repositories/services, such as JdbcRegisteredClientRepository, JdbcOAuth2AuthorizationService, and JdbcOAuth2AuthorizationConsentService, with the schema for the corresponding version.

Do not run new schema creation scripts against the production database before backing up and checking for table name conflicts. Do not overwrite the old schema. Create a separate target schema, and check indexes, column types, transactions, database permissions, and the rollback plan.

### 5.2 Do Not Copy Serialized Tokens Directly

Some legacy TokenStores store serialized objects or custom internal structures. The new system's OAuth2AuthorizationService stores a different authorization model. Copying blobs from old tables to new tables does not translate object semantics and can corrupt refresh, revoke, or scope state.

A typical safe strategy is:

1. Migrate client registrations and required configurations first.
2. Start the new authorization server with the new schema.
3. Stop creating new authorizations on the legacy server at the planned cutover time.
4. Let legacy tokens be verified/introspected via the legacy mechanism until expiration, or revoke them as planned.
5. Issue new tokens from the new server.
6. Monitor remaining active legacy tokens; only decommission the old store once the compatibility window ends and revocation obligations are handled.

If business requirements demand preserving login sessions or refresh tokens across the cutover point, a dedicated data conversion design is required. That design must verify token format, client binding, principal, scope, expiration, revocation state, rotation, and replay protection. Do not mark an old token as valid in the new store merely because the token string still exists.

### 5.3 Handling Consent

Legacy consent may contain multiple statuses such as approved, denied, approval timestamp, and approved scopes. The new consent service typically represents consent by principal, client, and authorities. Clearly determine:

- Which scopes the user approved.
- Which scopes were denied or never requested.
- Whether consents expire or can be revoked.
- Whether the legacy principal still has the same identifier as the new principal.
- Whether users must be prompted for consent again when scopes or processing purposes change.

Do not convert all legacy approvals into valid consents without analyzing their meaning. A denied or expired approval must not become a granted permission.

## 6. Configuring the New Authorization Server

The new configuration uses one filter chain for authorization server endpoints and another filter chain for the login application or remaining endpoints. The condensed example below illustrates separating matchers and enabling OIDC; repositories, token generators, issuer, and decoders must be declared according to the actual architecture.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults()));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http.authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
}
~~~

This snippet is a configuration skeleton for the API of the chosen Spring Authorization Server version. Check dependency management and version-specific documentation before applying; do not mix arbitrary versions of Spring Boot, Spring Security, and Authorization Server.

In a complete deployment, declare the appropriate repositories and services:

- RegisteredClientRepository to read clients.
- OAuth2AuthorizationService to store authorizations and tokens.
- OAuth2AuthorizationConsentService to store consents.
- OAuth2TokenGenerator and beans for JWT signing or opaque token issuance.
- AuthorizationServerSettings to fix the issuer and endpoint URIs.
- JwtDecoder when OIDC features or other components need to decode JWTs.

For the login endpoint, the second filter chain must have real user authentication, appropriate session policy, and CSRF protection. Do not allow authorization endpoints to run before an overly broad filter chain that mishandles requests.

### 6.1 Migrating Claims and Token Customization

In the legacy system, claims may have been added via TokenEnhancer, AccessTokenConverter, or custom code in DefaultTokenServices. In the new system, JWT access tokens can be customized via OAuth2TokenCustomizer with a JwtEncodingContext. Migrate each claim with a clear data source and rule.

Check claims commonly used by resource servers: iss, sub, aud, exp, iat, jti, scope or scp, tenant, role, and business claims. Do not put sensitive data or unnecessary personal information into access tokens. If changing claim names, update resource servers and policies at the same time.

For opaque tokens, claims are not read directly from a JWT; resource servers obtain information via introspection or a corresponding verification mechanism. Do not apply JWT customizer logic to opaque tokens and assume identical results.

### 6.2 Signing Keys and JWKS

Establish a key source with lifecycle management. In production, private keys should be protected by a secret manager, KMS, or HSM according to system requirements. Public keys are published via JWKS; private keys must never appear in JWKS responses or logs.

During migration:

- Record the signing algorithm and kid currently trusted by resource servers.
- Confirm the new server issues JWTs with compatible algorithms and claims.
- If rotating keys, publish both old and new public keys during the overlap period.
- Test JWKS caching and key refresh timing on resource servers.
- Only remove the old key once all tokens signed with that key have expired or been revoked and no longer require verification.

Do not use weak HMAC keys or share token signing secrets with clients. Choose asymmetric algorithms and a key rotation policy suited to the environment.

## 7. Migrating Resource Servers and OAuth2 Clients

### 7.1 Resource Server

If a legacy resource server uses @EnableResourceServer or ResourceServerConfigurerAdapter, migrate to a Spring Security SecurityFilterChain and oauth2ResourceServer configuration.

For JWTs, declare a JwtDecoder or issuer/JWK Set URI using the appropriate discovery mechanism. Validate issuer, audience, expiration, signing algorithm, and required claims. For opaque tokens, configure the introspection endpoint and credentials for a client authorized to introspect.

Scopes are commonly mapped to authorities prefixed with SCOPE_. If the legacy system used ROLE_, a custom role claim, or a custom converter, migrate that mapping explicitly. Do not lower authorization requirements just to make new tokens pass tests.

During the transition window, resource servers may need to verify both legacy and new tokens. Separate validators by issuer, key set, or introspection source; track verification sources so legacy compatibility paths can be retired on time.

### 7.2 OAuth2 Client

Applications using legacy Spring Security OAuth's OAuth2RestTemplate must migrate to modern OAuth2 Client. Spring Security provides ClientRegistration, OAuth2AuthorizedClientService, and OAuth2AuthorizedClientManager to manage client registrations and issued tokens.

During conversion, check:

- Client registration and authentication method.
- Authorization Code + PKCE for user-facing applications.
- Client Credentials for service-to-service communication.
- How authorized clients and refresh tokens are stored.
- How expired tokens, refresh failures, and logout are handled.
- Redirect URI and post-login callback configuration.

Do not store access tokens or refresh tokens in logs, URLs, browser local storage, or unprotected data stores. For web applications, prefer a server-side/BFF model where appropriate to reduce exposing tokens to the browser.

## 8. Controlled Cutover Roadmap

A migration should be divided into phases with clear exit criteria.

### Phase 1: Preparation

1. Complete the inventory of clients, grants, scopes, endpoints, tokens, and customizations.
2. Lock in the compatible version matrix for Spring Boot, Spring Security, and Spring Authorization Server.
3. Back up databases, key configurations, and consent data.
4. Stand up a staging environment with anonymized data.
5. Finalize issuer, public endpoints, signing keys, token TTLs, and compatibility policy.

### Phase 2: Building the New Server

1. Create a dedicated filter chain for the authorization server.
2. Configure the client repository, authorization service, and consent service.
3. Migrate client registrations and verify secrets.
4. Configure Authorization Code + PKCE, Client Credentials, and Refresh Token as needed.
5. Configure JWT or opaque tokens, issuer, and JWKS.
6. Migrate approved claims, consent page, login flow, and custom grants.
7. Test endpoints and OAuth error responses in staging.

### Phase 3: Migrating Resource Servers and Clients

1. Update resource servers to verify new tokens.
2. If needed, add time-bounded verification for legacy tokens.
3. Update clients in batches, starting with pilot clients.
4. Verify redirect URIs, PKCE, scopes, refresh, and logout.
5. Confirm audit and monitoring identify the token source.

### Phase 4: Cutover

1. Choose a low-traffic window and notify client owners.
2. Stop or restrict new authorization creation on the legacy server per plan.
3. Route selected clients to the new endpoints.
4. Monitor authentication errors, token issuance, introspection, latency, and 401/403 rates.
5. Keep the legacy token verification path active until tokens expire or are revoked.
6. Advance remaining client groups after the previous group meets stability criteria.

Avoid having two authorization servers simultaneously issue tokens for the same client flow without clear routing and state rules. In particular, never let a refresh token issued by server A be sent arbitrarily to server B. During parallel operation, know precisely which server owns each client's authorizations and refresh tokens.

### Phase 5: Completion

Once legacy tokens have expired or been handled per policy, disable legacy endpoints, revoke unused credentials, archive required audit records, and purge old data per retention procedures. Update operational documentation, dashboards, alerts, and recovery runbooks.

## 9. Regression and Security Testing

Use the same set of sample requests/responses collected during the inventory phase. Verify both protocol outcomes and impact on protected APIs.

| Group | Test Case | Expected Result |
|---|---|---|
| Client auth | Basic, post, public client per configuration | Only registered authentication methods are accepted |
| Authorization Code | Valid and invalid redirect URIs | Only exact registered URIs are accepted |
| PKCE | Correct S256, wrong or missing verifier | Only transactions with a valid proof can exchange the code |
| Client Credentials | Valid client, wrong secret, unauthorized scope | Tokens are issued only for permitted clients and scopes |
| Refresh Token | Valid, expired, revoked, reused after rotation | Behavior matches TTL and rotation policy |
| Consent | Not consented, consented, revoked, changed scopes | No permissions granted beyond consent |
| JWT | Signature, issuer, audience, exp, kid, and claims | Resource server accepts only valid tokens |
| Opaque token | Valid introspection, invalid, dependency failure | Introspection failures are never treated as valid tokens |
| Revocation | Revoke access/refresh tokens per implementation capability | Revocation state is reflected accurately |
| OIDC | Discovery, JWKS, UserInfo, nonce, and logout | Metadata and claims match configuration |
| Compatibility | Legacy tokens during overlap window | Only still-valid tokens compliant with policy are accepted |
| Operations | Database, Redis, KMS, or JWKS disruption | System fails gracefully and recovers as designed |

In addition to functional testing, run load tests on the token endpoint, rate limit tests, fault injection for database/Redis/KMS, and key rotation tests. Verify that logs do not contain client secrets, access tokens, refresh tokens, authorization codes, or private keys.

## 10. Rollback and Common Migration Pitfalls

Rollback must be designed before cutover. If the new server has already issued refresh tokens or authorization records that the legacy server does not understand, shifting all traffic back to the legacy server can cause users to lose sessions or trigger refresh errors. Therefore, rollback must account for tokens issued after cutover, not just DNS switching.

One option is to keep the new server handling tokens it issued during recovery, or transition clients through a controlled re-authentication flow. The decision depends on parallel-run capability and system availability requirements.

Common mistakes to avoid:

- Changing only dependencies while keeping legacy configuration.
- Migrating clients while omitting authentication methods, PKCE, or redirect URIs.
- Copying serialized token blobs directly into the new schema.
- Changing the issuer or signing key without updating resource servers.
- Converting all legacy approvals into valid consents.
- Continuing password grant or implicit grant in the new design.
- Letting multiple servers handle the same refresh token without routing rules.
- Changing scopes or claims so API authorization behaves differently than before.
- Deleting old public keys before tokens signed with them expire.
- Treating a 200 response from the token endpoint as proof that the entire API flow works.

Before cutover, document stop conditions: error rate exceeding threshold, clients unable to obtain tokens, resource servers rejecting valid tokens, introspection unavailable, or missing audit logs. Each condition needs an owner and concrete recovery action.

## 11. Exit Criteria

The migration is considered technically complete when:

- All active clients have been inventoried and mapped to the new configuration.
- Unsupported grant types have confirmed replacements.
- Client registrations, secrets, scopes, redirect URIs, and consents are migrated per policy.
- The new authorization server issues tokens and handles errors according to approved configuration.
- Resource servers accurately validate issuer, audience, signatures, scopes, and claims.
- Legacy tokens are verified, introspected, or allowed to expire according to the transition plan.
- Refresh tokens and authorization records are never misrouted between the two servers.
- JWKS and key rotation workflows operate properly during the overlap window.
- Regression, security, load, and fault injection test suites meet criteria.
- Rollback plans, monitoring, audit logging, and operational runbooks are updated.
- Legacy endpoints and legacy data are decommissioned only when no tokens or clients depend on them.

Migrating from legacy Spring Security OAuth to Spring Authorization Server is an architectural change to the authorization system. By clearly separating client registration, authorization state, token validation, and each application's responsibilities, the team can migrate in phases, preserve necessary compatibility, and control risk during cutover.
