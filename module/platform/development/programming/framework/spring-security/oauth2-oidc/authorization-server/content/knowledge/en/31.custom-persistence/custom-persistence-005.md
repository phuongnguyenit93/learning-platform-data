# TTL, Serialization, and Updating Token Metadata in Custom Stores

> **Chapter:** Custom Persistence  
> **Module:** `SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER`  
> **Module Goal:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Technical Scope:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x. Examples use the Servlet stack and `OAuth2AuthorizationService`; persistence can be implemented with JDBC, JPA, or a key-value store.

## 1. Objectives and Context

When an Authorization Server moves from in-memory storage to a database or distributed store, storing a token string and a single expiration timestamp is not enough. Spring Authorization Server must reconstruct the complete state of an authorization to continue processing protocol flows.

An `OAuth2Authorization` can contain:

- The Registered Client and the principal involved in the grant.
- The grant type, granted scopes, and authorization request attributes.
- An Authorization Code, Access Token, Refresh Token, ID Token, Device Code, or User Code depending on the grant.
- Issuance times, expiration times, token claims, and metadata for each token.
- Whether each token is invalidated/revoked or still active.

A single authorization can contain multiple tokens with different lifecycles. For example, the Authorization Code may already be expired or consumed and the Access Token still valid, while the Refresh Token continues allowing new Access Tokens to be issued. Therefore, the store must manage per-token TTLs and retain the authorization record long enough to handle the remaining tokens.

After this lesson, you will be able to:

1. Distinguish token TTL from authorization record retention time.
2. Configure per-client TTLs using `TokenSettings`.
3. Design a schema storing token values, `issuedAt`, `expiresAt`, metadata, and claims.
4. Safely serialize/deserialize `OAuth2Authorization` with schema compatibility.
5. Implement `save`, `remove`, `findById`, and `findByToken` of `OAuth2AuthorizationService`.
6. Update token metadata using `OAuth2Authorization.from(...)` without losing existing metadata.
7. Persist invalidation state and refresh token rotation accurately.
8. Handle concurrency, cleanup, indexing, and distributed caching.
9. Test round-trip serialization, token expiry, revocation, and metadata updates.

**Design Principle:** Token lifetimes are determined when tokens are issued; the store must preserve those exact timestamps, persist sufficient token state for framework checks, and only clean up the authorization record once no token or protocol state is still needed.

## 2. OAuth2Authorization and the Persistence Contract

### 2.1. Authorization Is an Aggregate Containing Multiple Tokens

`OAuth2Authorization` represents the state of an authorization granted to a client by a resource owner, or by the client itself in the `client_credentials` grant.

Core properties:

| Property | Meaning |
| --- | --- |
| `id` | Unique identifier of the authorization |
| `registeredClientId` | Internal ID of the `RegisteredClient` |
| `principalName` | Name of the principal or client |
| `authorizationGrantType` | Grant type used |
| `authorizedScopes` | Granted scopes |
| `tokens` | Tokens and metadata attached to each token |
| `attributes` | Additional grant data, such as the authenticated principal and authorization request |

Tokens that may appear depending on the grant:

| Grant/Flow | Tokens or State Typically Stored |
| --- | --- |
| Authorization Code | Authorization Code, Access Token, and Refresh Token depending on client |
| OpenID Connect Authorization Code | Authorization Code, ID Token, Access Token, and Refresh Token depending on client |
| Client Credentials | Access Token |
| Device Authorization | Device Code, User Code, and tokens after the user completes verification |
| Refresh Token | New tokens and old token state per rotation policy |

Do not assume every authorization contains all of the tokens above. Schemas and serializers must handle absent fields gracefully.

### 2.2. OAuth2AuthorizationService Is the Persistence Boundary

`OAuth2AuthorizationService` is the central component for persisting new authorizations and querying existing ones. Protocol components use this service during authorization grant processing, client authentication, token introspection, token revocation, and related flows.

The interface has four methods:

~~~java
public interface OAuth2AuthorizationService {

    void save(OAuth2Authorization authorization);

    void remove(OAuth2Authorization authorization);

    OAuth2Authorization findById(String id);

    OAuth2Authorization findByToken(
        String token, OAuth2TokenType tokenType);
}
~~~

Contract to uphold:

| Method | Custom Store Behavior |
| --- | --- |
| `save` | Persist a new authorization or update the state of an existing authorization |
| `remove` | Delete the entire authorization by ID |
| `findById` | Reconstruct the complete authorization by ID |
| `findByToken` | Find the authorization containing the provided token; return `null` if absent |

`findByToken` accepts a nullable `tokenType`. When `null`, the implementation must search across all token/state types it supports rather than defaulting to Access Token only. A specific token type narrows the lookup and uses the appropriate index.

### 2.3. Keep the Three Core Services Separate

Do not mix the following three types of data into one table or one service simply because they are related:

- `RegisteredClientRepository` stores client registrations, redirect URIs, grant types, scopes, client settings, and token settings.
- `OAuth2AuthorizationService` stores the state of each authorization and issued tokens.
- `OAuth2AuthorizationConsentService` stores a user's consent decisions for a client.

One `RegisteredClient` can have many authorizations. One user can also have multiple authorizations with the same client. Consent has its own lifecycle and does not automatically disappear when an authorization record is deleted.

## 3. Token TTLs in Spring Authorization Server

### 3.1. TokenSettings Is the Issuance Policy

`TokenSettings` is attached to a `RegisteredClient` and defines the lifetimes of tokens issued to that client. In Spring Authorization Server 1.5.x, the builder supports:

- `authorizationCodeTimeToLive(Duration)`
- `accessTokenTimeToLive(Duration)`
- `refreshTokenTimeToLive(Duration)`
- `deviceCodeTimeToLive(Duration)`
- `reuseRefreshTokens(boolean)`
- `accessTokenFormat(OAuth2TokenFormat)`

Example:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
    .authorizationCodeTimeToLive(Duration.ofMinutes(5))
    .accessTokenTimeToLive(Duration.ofMinutes(8))
    .refreshTokenTimeToLive(Duration.ofDays(7))
    .deviceCodeTimeToLive(Duration.ofMinutes(5))
    .reuseRefreshTokens(false)
    .build();

RegisteredClient portalClient = RegisteredClient
    .withId("portal-registration")
    .clientId("portal-client")
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://portal.example.test/login/oauth2/code/portal")
    .scope(OidcScopes.OPENID)
    .scope("orders.read")
    .tokenSettings(tokenSettings)
    .build();
~~~

This example illustrates a per-client policy. Choose TTLs based on client type, resource sensitivity, refresh capability, token exposure risk, and operational requirements.

### 3.2. Default Values

In Spring Authorization Server 1.5.8, the default values in `TokenSettings` include:

| Type | Default TTL |
| --- | ---: |
| Authorization Code | 5 minutes |
| Access Token | 5 minutes |
| Device Code | 5 minutes |
| Refresh Token | 60 minutes |

`reuseRefreshTokens` defaults to `true`. When set to `false`, the server issues a new Refresh Token during the refresh flow instead of reusing the old one.

`TokenSettings` does not have a dedicated builder method named `idTokenTimeToLive` in the 1.5.8 API. An ID Token still carries `issuedAt` and `expiresAt` in the `OidcIdToken` object; custom persistence must store the token's actual timestamps rather than inventing an assumed TTL during deserialization.

### 3.3. Token TTL and Storage TTL Are Two Separate Policies

| Policy | Question to Answer | Where Applied |
| --- | --- | --- |
| Token TTL | Until when is the credential accepted? | `TokenSettings` and `issuedAt`/`expiresAt` timestamps |
| Authorization retention | Until when must the authorization record be kept? | Database/Redis retention policy |
| Cache TTL | How long is a cached entry used before re-reading the primary source? | Cache layer |
| Audit retention | How long must token/revocation history be kept? | Audit store and retention policy |

Never set the Redis TTL of an entire authorization to the shortest TTL among its tokens. If the Authorization Code expires after 5 minutes while the Refresh Token lasts 7 days, deleting the whole authorization record after 5 minutes will break the refresh flow.

### 3.4. Issuance and Expiration Timestamps Are Authoritative Data

When a token is created, the token object carries `issuedAt` and `expiresAt`. A custom store must preserve these values intact as absolute points in time, typically using `Instant` and timezone-aware timestamp columns.

Do not recompute `expiresAt` from the current `TokenSettings` when reading a record. If an admin changes the Access Token TTL from 10 minutes down to 5 minutes, previously issued tokens still retain their original expiration timestamps. Policy changes apply to newly issued tokens unless there is an explicit workflow to revoke or migrate existing tokens.

Time example:

~~~java
Instant issuedAt = accessToken.getIssuedAt();
Instant expiresAt = accessToken.getExpiresAt();

if (expiresAt != null && !expiresAt.isAfter(clock.instant())) {
    // Token has expired according to the current clock.
}
~~~

Use UTC/`Instant` consistently across the application and database. Account for timestamp precision, clock skew across nodes, and a grace window for cleanup. Do not extend token lifetimes just to match a cache TTL.

## 4. Designing Retention and Cleanup

### 4.1. Calculating When an Authorization Can Be Cleaned Up

An authorization can hold multiple tokens. The cleanup time for the full record must account for all tokens still needed:

~~~text
authorizationRetentionUntil =
    max(
        authorizationCodeExpiresAt,
        accessTokenExpiresAt,
        refreshTokenExpiresAt,
        idTokenExpiresAt,
        deviceCodeExpiresAt,
        userCodeExpiresAt
    ) + retentionGrace
~~~

This is a conceptual formula; implementations must ignore absent tokens and handle tokens without an `expiresAt` per policy. If a Refresh Token has an unlimited lifetime or a custom grant has no expiry, do not arbitrarily impose a short TTL that deletes the record.

### 4.2. Do Not Delete the Record as Soon as One Token Expires

Example:

- Authorization Code expires after 5 minutes.
- Access Token expires after 10 minutes.
- Refresh Token expires after 7 days.

After 5 minutes, the authorization still must be kept because the Access Token or Refresh Token remains relevant. After 10 minutes, the refresh flow still needs the record. Only when all required tokens have expired/been invalidated and no protocol state or audit requirement remains is the record eligible for cleanup.

### 4.3. Physical Cleanup Does Not Replace Invalidation State

A token may be revoked before `expiresAt` arrives. Invalidation state must be persisted in the token's metadata and read by protocol components. Deleting a physical row is a retention operation; it does not replace the revocation workflow.

Separate:

- The validity status of a token.
- The state of the authorization aggregate.
- The timestamp when the record becomes eligible for cleanup.
- Audit records if an audit trail must be retained longer.

### 4.4. Cleanup Jobs Must Be Repeatable

Cleanup jobs should be idempotent, batched, and indexed by `retention_until` or `expires_at`. Avoid locking the entire table. If a job is re-run, it must never corrupt active authorizations.

Illustrative query:

~~~sql
DELETE FROM oauth2_authorization
WHERE retention_until < CURRENT_TIMESTAMP
  AND no_token_is_still_retained = TRUE;
~~~

`no_token_is_still_retained` is a conceptual predicate; replace it with a subquery/condition matching your actual schema. If audit retention applies, move records requiring retention to the audit store before deleting operational records.
## 5. Serialization of OAuth2Authorization

### 5.1. Why Is Serialization Complex?

`OAuth2Authorization` contains diverse data types:

- Tokens implement `OAuth2Token` but have distinct concrete subclasses.
- `AuthorizationGrantType` may be a standard constant or a custom grant.
- `attributes` is a `Map` whose values can be framework objects or custom principals.
- `tokens` is a `Map` keyed by token class.
- Token metadata holds claims, invalidation flags, and additional data.

Simply serializing a flat JSON containing `id`, `principalName`, and `accessTokenValue` drops data needed for other flows such as refresh tokens, device authorization, OIDC, or token revocation.

### 5.2. Using JSON with Spring Security Modules

Spring Authorization Server provides `OAuth2AuthorizationServerJackson2Module`. The official JPA guide combines this module with the modules provided by `SecurityJackson2Modules` to serialize Spring Security types.

Mapper initialization example:

~~~java
ObjectMapper objectMapper = new ObjectMapper();

ClassLoader classLoader =
    JpaOAuth2AuthorizationService.class.getClassLoader();

List<Module> securityModules =
    SecurityJackson2Modules.getModules(classLoader);

objectMapper.registerModules(securityModules);
objectMapper.registerModule(
    new OAuth2AuthorizationServerJackson2Module());
~~~

In a real application, create the mapper via a shared bean/configuration and control which modules are registered. Jackson and module versions must align with the application's dependency tree.

### 5.3. Avoid Java Native Serialization for Long-Term Storage

Do not use Java native serialization as a long-term storage format without compelling reasons. That format couples tightly to class names, `serialVersionUID`, and object structure from a specific application version. Across framework upgrades or custom principal changes, deserialization can fail or break compatibility.

JSON with schema versioning and explicit type mapping allows you to:

- Inspect stored data easily.
- Perform controlled migrations.
- Support multiple application versions reading shared data during rolling deployments.
- Distinguish framework metadata from application metadata.

### 5.4. Deserialization Must Use an Allowlist

`OAuth2Authorization.attributes` can hold complex objects, including `Authentication` or custom principals. Never enable broad polymorphic default typing on JSON read from a store that could be tampered with or sourced untrustworthily.

Register only the subtypes/modules strictly needed. If a custom principal is difficult to serialize, consider storing a stable principal snapshot containing subject, issuer, tenant, and required authorities, and reconstructing a supported type in the adapter. Never store credentials/passwords or session secrets inside attributes.

### 5.5. Persist a Schema Version

A JSON document should carry its own version:

~~~json
{
  "schemaVersion": 2,
  "authorizationId": "auth-7c1f",
  "registeredClientId": "portal-registration",
  "principalName": "alice",
  "grantType": "authorization_code",
  "authorizedScopes": ["openid", "orders.read"],
  "attributes": {},
  "tokens": []
}
~~~

This example illustrates only the envelope. Real token values, claims, and metadata must be encrypted/protected per policy. When the schema evolves, implement a reader capable of handling older versions and migrating lazily on writes; never assume all records update instantaneously.

## 6. Data That Must Be Preserved During Serialization

### 6.1. Authorization-Level Attributes

Attributes can contain:

- The authenticated principal.
- `OAuth2AuthorizationRequest`.
- `state` or grant-specific data.
- Context required by protocol components in later steps.

If attributes are stripped to shorten JSON payloads, refresh/token flows or custom grants may fail to restore the original context. Strip attributes only after confirming they are unused and testing every related flow.

### 6.2. Token-Level Metadata

Each `OAuth2Authorization.Token` wraps a token and its associated metadata. Two key metadata names in SAS:

| Constant | Purpose |
| --- | --- |
| `CLAIMS_METADATA_NAME` | Metadata key holding claims attached to the token |
| `INVALIDATED_METADATA_NAME` | Metadata key indicating the token has been invalidated |

`OAuth2Authorization.Token` provides:

- `getToken()`
- `getMetadata()` and `getMetadata(name)`
- `getClaims()`
- `isExpired()`
- `isInvalidated()`
- `isActive()`

Never rename or overwrite standard metadata keys when storing custom metadata.

### 6.3. Distinguish Token Claims from Application Metadata

| Data | Example | Storage Location |
| --- | --- | --- |
| JWT claim | `sub`, `aud`, `scope`, `tenant_id` | Inside the signed JWT |
| Token claims metadata | Claims attached to a token in `OAuth2Authorization.Token` | Token metadata |
| Invalidation state | Token has been revoked | Token metadata |
| Authorization attribute | Authorization request, principal snapshot | `OAuth2Authorization.attributes` |
| Application metadata | Risk label, policy version, source system | Dedicated namespace inside metadata/attributes |

Database metadata does not automatically become a claim inside a JWT. Once a JWT is signed, editing JSON metadata in the store does not alter the JWT's payload or signature.

## 7. Updating Authorization Metadata

### 7.1. Use OAuth2Authorization.from(...)

Do not rebuild an authorization from scratch just to change one property. `OAuth2Authorization.from(existing)` returns a builder initialized from the existing authorization, preserving its ID, Registered Client ID, principal, grant type, scopes, attributes, and token state.

Example updating an application attribute:

~~~java
OAuth2Authorization updated = OAuth2Authorization
    .from(existingAuthorization)
    .attributes(attributes ->
        attributes.put("com.example.risk.label", "reviewed"))
    .build();

authorizationService.save(updated);
~~~

Attribute keys should be namespaced to prevent collisions with keys used by the framework or other custom grants.

### 7.2. Updating Token Metadata While Preserving Existing Metadata

Use `getAccessToken()` to obtain the Access Token wrapper. Then pass the token value and a metadata consumer to the builder:

~~~java
OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
    existingAuthorization.getAccessToken();

if (accessToken == null) {
    throw new IllegalStateException("Authorization has no access token");
}

OAuth2Authorization updated = OAuth2Authorization
    .from(existingAuthorization)
    .token(accessToken.getToken(), metadata -> {
        metadata.putAll(accessToken.getMetadata());
        metadata.put("com.example.risk.reviewed", Boolean.TRUE);
        metadata.put("com.example.policy.version", 3);
    })
    .build();

authorizationService.save(updated);
~~~

`putAll(accessToken.getMetadata())` preserves existing metadata, including claims and invalidation state. Creating a fresh metadata map and writing only custom keys can accidentally wipe out standard metadata.

### 7.3. Updating Claims Metadata Does Not Modify Issued JWTs

If the Access Token is a self-contained JWT, its claims are already embedded in the signed payload. Changing claims in persistence after issuance does not mint a new JWT and does not alter that JWT's signature.

To change claims on new tokens, customize them prior to token signing via `OAuth2TokenCustomizer`. If permissions on an already-issued token must change, you generally must revoke the old token and issue a new one per policy rather than editing database metadata and expecting the Resource Server to see new claims.

### 7.4. Invalidating a Token with the Builder API

In SAS 1.5.x, `OAuth2Authorization.Builder.invalidate(token)` marks a token as invalidated. Example:

~~~java
OAuth2Authorization.Token<OAuth2RefreshToken> refreshToken =
    existingAuthorization.getRefreshToken();

if (refreshToken == null) {
    return;
}

OAuth2Authorization updated = OAuth2Authorization
    .from(existingAuthorization)
    .invalidate(refreshToken.getToken())
    .build();

authorizationService.save(updated);
~~~

This updates the token state within the authorization. You must persist the updated object via `OAuth2AuthorizationService.save` so the database/cache reflects the change. Never mutate a local map and skip persistence.

## 8. Updating Claims Before Token Issuance

### 8.1. JWT Claims Are Determined Before Signing

For self-contained Access Tokens, custom claims must be added to the JWT before signing. `OAuth2TokenCustomizer<JwtEncodingContext>` is the extension point for JWT generation.

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
        TenantResolver tenantResolver) {

    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            String tenantId =
                tenantResolver.resolve(context.getPrincipal());

            context.getClaims().claim("tenant_id", tenantId);
        }
    };
}
~~~

`TenantResolver` is an application service illustrating how to derive the tenant from the authenticated principal. Never take a tenant from an unverified request parameter.

### 8.2. Persisting Metadata After Token Issuance

After tokens are generated, SAS attaches the tokens and metadata to `OAuth2Authorization` and calls `OAuth2AuthorizationService.save(...)`. A custom store must persist:

- Token values or a recoverable representation.
- `issuedAt` and `expiresAt`.
- Token type and scopes if present.
- Claims metadata.
- Invalidation metadata.
- Validly added application metadata.

For JWTs, the signed token payload is the claim source verified by the Resource Server. Claims stored in authorization metadata serve queries/introspection or internal logic; they do not replace the signature.

### 8.3. Opaque Tokens and Introspection

Opaque Access Tokens do not carry a payload that Resource Servers can decode themselves. When introspection is used, the Authorization Server looks up the authorization record and returns status/claims per configuration.

The custom store must ensure introspection can accurately read:

- Active/inactive status.
- Expiry.
- Client/principal.
- Scopes.
- Permitted claims or metadata to disclose.

Never return all internal application metadata or private data in an introspection response. Only expose claims appropriate for the protocol and authorization policy.
## 9. Designing a Schema for a Custom Store

### 9.1. Aggregate and Token Index Model

A design can separate the authorization record and token records:

~~~sql
CREATE TABLE oauth2_authorization (
    id                    varchar(100) PRIMARY KEY,
    registered_client_id  varchar(100) NOT NULL,
    principal_name        varchar(255) NOT NULL,
    authorization_grant_type varchar(255) NOT NULL,
    authorized_scopes     jsonb NOT NULL,
    attributes_json       jsonb NOT NULL,
    schema_version        integer NOT NULL,
    version               bigint NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL,
    updated_at            timestamptz NOT NULL,
    retention_until       timestamptz
);

CREATE TABLE oauth2_authorization_token (
    token_id              uuid PRIMARY KEY,
    authorization_id      varchar(100) NOT NULL
        REFERENCES oauth2_authorization(id) ON DELETE CASCADE,
    token_type            varchar(80) NOT NULL,
    token_value_ciphertext bytea,
    token_lookup_hash     bytea,
    issued_at             timestamptz,
    expires_at            timestamptz,
    token_type_value      varchar(40),
    scopes_json           jsonb,
    claims_json           jsonb,
    metadata_json         jsonb NOT NULL,
    invalidated           boolean NOT NULL DEFAULT false,
    is_current            boolean NOT NULL DEFAULT true,
    UNIQUE (token_type, token_lookup_hash)
);

CREATE INDEX idx_oauth2_authorization_client_principal
    ON oauth2_authorization(registered_client_id, principal_name);

CREATE INDEX idx_oauth2_authorization_retention
    ON oauth2_authorization(retention_until);

CREATE INDEX idx_oauth2_authorization_token_lookup
    ON oauth2_authorization_token(token_type, token_lookup_hash);
~~~

This is a PostgreSQL-oriented reference schema, not a mandatory SAS schema. Adjust data types, lengths, JSON types, keys, and indexes to your actual database and workload.

### 9.2. Why Separate Token Records?

Token records have their own lifetimes, invalidation states, and metadata. Separating them enables:

- Fast token lookups by type and hash.
- Expiry indexing for cleanup.
- Updating token metadata without re-serializing the entire aggregate at the SQL layer.
- Encrypting token values independently.
- Retaining token history if refresh token replay detection is needed.

`OAuth2Authorization` currently represents the active tokens keyed by token class. If you need to retain a history of rotated refresh tokens, use a dedicated history/replay table; do not try to cram every historical token into the framework's current token map.

### 9.3. Token Lookup Index

The Authorization Server frequently needs to locate an authorization from a raw token. Never scan the entire table.

You can compute a lookup hash using HMAC-SHA-256 with a separately managed secret key:

~~~java
byte[] lookupHash = tokenHasher.hmacSha256(rawToken);
~~~

On an incoming request, recompute the HMAC from the presented token and query the index by token type. Use versioned HMAC keys to support rotation; during transition windows, look up across the active key set per policy.

If token values must be recovered to reconstruct `OAuth2Authorization`, store authenticated ciphertext (such as AES-GCM) alongside the key version. The HMAC hash only serves lookups and cannot be decrypted back into the token.

### 9.4. Column Sizing

Tokens, attributes, claims, and metadata can exceed default `varchar` lengths. Use `TEXT`/`CLOB`/`JSONB` or suitable types and set realistic bounds based on payload sizes. The Spring Authorization Server JPA guide also notes adjusting column lengths/types per database and testing before production.

## 10. Serialization/Deserialization with a Mapper

### 10.1. Bidirectional Mapping

Custom persistence should include a dedicated component responsible for translation:

~~~text
OAuth2Authorization
        |
        v
AuthorizationRecord + TokenRecords
        |
        v
JSON metadata / encrypted token values
        |
        v
Database or distributed store
~~~

On reads:

1. Load the authorization record.
2. Look up `RegisteredClient` by `registered_client_id`.
3. Restore grant type and authorized scopes.
4. Deserialize attributes using the configured mapper.
5. Reconstruct each token with its exact concrete class.
6. Restore token metadata, claims, and invalidation state.
7. Rebuild `OAuth2Authorization` using the `Builder`.

### 10.2. RegisteredClient Is a Deserialization Dependency

`OAuth2Authorization.withRegisteredClient(registeredClient)` requires a `RegisteredClient` object, not just a client ID string. Thus, the custom service must depend on `RegisteredClientRepository`.

If the internal client ID no longer exists, never silently fabricate a default client. Throw a clear retrieval exception, emit metrics, and handle orphaned data through administrative procedures.

### 10.3. Restoring the Exact Token Class

Do not reconstruct every token as an `OAuth2AccessToken`. Map each to its exact class:

| Token Class | Data to Restore |
| --- | --- |
| `OAuth2AuthorizationCode` | Value, `issuedAt`, `expiresAt` |
| `OAuth2AccessToken` | Type, value, `issuedAt`, `expiresAt`, scopes |
| `OAuth2RefreshToken` | Value, `issuedAt`, `expiresAt` |
| `OidcIdToken` | Value, `issuedAt`, `expiresAt`, claims |
| `OAuth2DeviceCode` | Value, `issuedAt`, `expiresAt` |
| `OAuth2UserCode` | Value, `issuedAt`, `expiresAt` |

For token metadata, call the `Builder.token` overload accepting a metadata consumer to restore the corresponding metadata `Map`.

### 10.4. Custom Grant Types

`AuthorizationGrantType` permits custom values. When deserializing, do not assume only standard grant type constants exist. Store the `authorizationGrantType.getValue()` string and reconstruct using a standard constant if matched, otherwise `new AuthorizationGrantType(value)`.

The same rule applies to custom token types or metadata keys: store stable, namespaced values with explicit mappings.

## 11. Implementing a Custom OAuth2AuthorizationService

### 11.1. Service Skeleton

The following example illustrates the boundary between the service, codec, and repository. `AuthorizationStore`, `AuthorizationCodec`, and `TokenHasher` are application abstractions:

~~~java
public final class StoreOAuth2AuthorizationService
        implements OAuth2AuthorizationService {

    private final AuthorizationStore store;
    private final AuthorizationCodec codec;
    private final TokenHasher tokenHasher;

    public StoreOAuth2AuthorizationService(
            AuthorizationStore store,
            AuthorizationCodec codec,
            TokenHasher tokenHasher) {

        Assert.notNull(store, "store cannot be null");
        Assert.notNull(codec, "codec cannot be null");
        Assert.notNull(tokenHasher, "tokenHasher cannot be null");

        this.store = store;
        this.codec = codec;
        this.tokenHasher = tokenHasher;
    }

    @Override
    public void save(OAuth2Authorization authorization) {
        Assert.notNull(authorization, "authorization cannot be null");

        AuthorizationRecord record = codec.toRecord(authorization);
        store.upsert(record);
    }

    @Override
    public void remove(OAuth2Authorization authorization) {
        Assert.notNull(authorization, "authorization cannot be null");

        store.deleteById(authorization.getId());
    }

    @Override
    public OAuth2Authorization findById(String id) {
        Assert.hasText(id, "id cannot be empty");

        return store.findById(id)
            .map(codec::toObject)
            .orElse(null);
    }

    @Override
    public OAuth2Authorization findByToken(
            String token, OAuth2TokenType tokenType) {

        Assert.hasText(token, "token cannot be empty");

        byte[] lookupHash = tokenHasher.hash(token);

        return store.findByToken(lookupHash, tokenType)
            .map(codec::toObject)
            .orElse(null);
    }
}
~~~

This skeleton must be completed with transactions, error mapping, key rotation, and concrete store implementations. The crucial requirement is that `save` must support updating an existing authorization's state, not merely inserting a new row.

### 11.2. save Must Be a Controlled Upsert

SAS calls `save` when creating an authorization and when updating tokens/state. Therefore:

- Record does not exist: insert.
- Record already exists: update.
- New token added: update token index.
- Old token invalidated: update metadata/index.
- Token rotation: replace current token and retain history if required by policy.
- Metadata update: preserve other attributes and tokens.

In JDBC/JPA, wrap writes to the parent record, token records, and token indexes in a single transaction. If only the parent updates while the token index still points to an old token, token lookups can return the wrong authorization.

### 11.3. findByToken Must Support the Exact Token Type

For a specific `tokenType`, the lookup should use the corresponding index. For `tokenType == null`, it must search across all token/state types supported by the service, matching how default implementations can search multiple token types.

Never return an authorization solely because a hash matches if the token type disagrees. Verify the decrypted token value as well when needed to guard against collisions or wrong key versions. Never log raw tokens in query diagnostics.

### 11.4. remove Differs from Revocation

`remove(authorization)` deletes the entire authorization aggregate. Revoking a single token typically marks that token invalidated and calls `save` on the updated authorization so other tokens in the same authorization retain their state.

Do not call `remove` just because an Access Token is revoked if a Refresh Token remains active or the record is still needed for introspection/auditing.

## 12. Updating Metadata and Tokens Across the Lifecycle

### 12.1. Authorization Code Redemption

When an Authorization Code is redeemed, the code must become inactive/invalidated per the protocol flow. The custom store must persist this state alongside the newly issued tokens. Do not delete the entire authorization if new Access/Refresh Tokens were just attached to the same aggregate.

### 12.2. Refresh Token Rotation

When `reuseRefreshTokens(false)` is set, the refresh flow issues a new Refresh Token. The custom store must:

1. Verify the old Refresh Token is still active.
2. Process the old token according to the rotation/invalidation state provided by SAS.
3. Persist the new token and its new issued-at/expires-at timestamps.
4. Update the new Access Token if issued by the flow.
5. Update the lookup index within the same transaction.
6. Store the old token's history/hash if replay detection is needed.

Never allow the old refresh token to still look active after rotation. If replay detection is required, store the old token hash in a history table with a used/revoked status and its own retention policy.

### 12.3. Revocation

When the token revocation endpoint processes a token, the provider locates the authorization via `findByToken`, identifies the token type, and updates its state. The custom service must preserve the invalidation metadata and persist the update.

If Access Token JWTs are verified offline by Resource Servers, updating the database at the AS does not automatically invalidate the JWT at the Resource Server. To make revocation take effect early, Resource Servers must use introspection, a denylist, or an online/propagated revocation mechanism.

### 12.4. Updating Client TokenSettings

When an admin updates a `RegisteredClient`'s `TokenSettings`, already-issued tokens retain their original `issuedAt`/`expiresAt`. Do not deserialize authorizations and overwrite `expiresAt` with the new TTL. To block old tokens, perform explicit revocation.
## 13. Concurrency and Consistency

### 13.1. Single-Use Authorization Codes

Two concurrent requests can both read an authorization code before either saves its invalidation. If the store performs only a plain read followed by a write, both requests risk passing the active check.

`OAuth2AuthorizationService` has no dedicated method such as `consumeAuthorizationCodeAtomically`. For strict single-use guarantees in distributed deployments, design transaction/locking or atomic claim mechanisms aligned with grant processing, such as:

- Locking the row by authorization ID.
- Optimistic versioning with conflict retries.
- Conditional updates transitioning code state from active to consumed.
- Unique/compare-and-set constraints for code consumption.

Adding a version field without checking it during writes does not provide true optimistic locking.

### 13.2. Refresh Token Rotation Requires Atomicity

Two refresh requests presenting the same token can race. If both read the active state and mint new tokens, the system can fork two refresh branches.

Use row locking or a conditional update on the old token, and only issue new tokens once consuming the old token succeeds. Test with concurrent requests, not only sequential tests.

### 13.3. Cache and Database

If caching is used:

- The durable database/store is the authoritative source of state.
- Invalidation/revocation must update the cache or emit an invalidation event.
- The cache must never retain an active token after the database marks it invalidated.
- Cache TTLs must not exceed token expiry.
- Cache misses must read the latest state from the primary source per consistency policy.

For token revocation, a stale cache can cause Resource Servers or the introspection endpoint to keep treating a token as active. Choose consistency guarantees and propagation delays based on risk.

## 14. Configuring the Custom Service in the Authorization Server

The custom service can be exposed as a bean and wired into `OAuth2AuthorizationServerConfigurer`:

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationServerPersistenceConfiguration {

    @Bean
    OAuth2AuthorizationService authorizationService(
            AuthorizationStore store,
            AuthorizationCodec codec,
            TokenHasher tokenHasher) {

        return new StoreOAuth2AuthorizationService(
            store, codec, tokenHasher);
    }

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizationService authorizationService)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.authorizationService(authorizationService));

        return http.build();
    }
}
~~~

This fragment illustrates wiring only. A complete application still needs `RegisteredClientRepository`, `AuthorizationServerSettings`, token generator/JWK configuration, and a user authentication filter chain. If the application context already auto-detects a service bean, avoid registering a second implementation that could cause endpoints to wire the wrong bean.

## 15. JDBC, JPA, and Redis: Choosing the Right Structure

### 15.1. JdbcOAuth2AuthorizationService

SAS provides `JdbcOAuth2AuthorizationService` backed by `JdbcOperations` and the accompanying SQL schema. It is a straightforward implementation usable in production, though the API docs note it may not suit high-throughput workloads; applications may need a custom implementation.

You can customize `OAuth2AuthorizationParametersMapper` and `OAuth2AuthorizationRowMapper` to adjust data mapping. Before building a completely custom service, evaluate whether extending the existing mappers or schema is sufficient.

### 15.2. JPA

The official JPA guide provides an entity/repository model for mapping `OAuth2Authorization`. It is a starting point, not an optimal schema for every database. Token, metadata, settings, and claim fields can be large; adjust column types/lengths and indexes accordingly.

### 15.3. Redis or Key-Value Stores

Redis suits fast lookups, per-key TTLs, and distributed caching. However, you must address:

- Multiple tokens belonging to the same authorization aggregate.
- Atomic updates during refresh/revocation.
- Serialization versioning.
- Token lookup indexes and key rotation.
- Persistence durability/replication/failover.
- Backup/restore and cleanup.
- Queryability for auditing.

Never place an entire authorization in a single Redis key with a TTL equal to the shortest token. Use a parent aggregate key with separate token indexes, or keep a database as the source of truth and use Redis as a cache.

## 16. Protecting Token Values and Metadata

### 16.1. Token Values Are Credentials

Access Tokens, Refresh Tokens, Authorization Codes, Device Codes, and User Codes can all authorize protocol actions. Never put raw tokens in logs, tracing spans, metric labels, or exception messages.

If token values must be recovered:

- Encrypt with authenticated encryption such as AES-GCM.
- Store the key version to support rotation.
- Manage encryption keys via KMS/secret manager.
- Restrict read access on token tables/stores.
- HMAC tokens for lookup indexes instead of plaintext indexes.

### 16.2. Do Not Put Secrets into Uncontrolled Metadata

Never store plaintext client secrets in authorization attributes. Never store passwords, private keys, session cookies, or raw credentials in custom metadata. Store only data required for protocol execution and operations.

### 16.3. Claims Can Contain Personal Data

Claims and principal attributes can hold PII or sensitive authorization details. Apply data minimization, encryption at rest, appropriate retention, and access controls. Never return all internal metadata through introspection or administrative APIs.

### 16.4. Separate Auditing from Operational State

Operational authorization records may be cleaned up after all tokens expire. If long-term auditing is needed, write token issuance, refresh, revocation, and cleanup events to a separate audit/event store. Never extend token TTLs just to retain audit records.

## 17. Testing Custom Persistence

### 17.1. Round-Trip Serialization

Create an authorization with representative tokens and attributes, save it to the store, and read it back:

~~~java
OAuth2Authorization original = createAuthorizationFixture();

authorizationService.save(original);

OAuth2Authorization restored =
    authorizationService.findById(original.getId());

assertThat(restored).isNotNull();
assertThat(restored.getRegisteredClientId())
    .isEqualTo(original.getRegisteredClientId());
assertThat(restored.getPrincipalName())
    .isEqualTo(original.getPrincipalName());
assertThat(restored.getAuthorizationGrantType())
    .isEqualTo(original.getAuthorizationGrantType());
assertThat(restored.getAuthorizedScopes())
    .isEqualTo(original.getAuthorizedScopes());
~~~

Add assertions for each token's value/type, `issuedAt`, `expiresAt`, claims, metadata, invalidation state, and attributes. Explicitly test custom principals, custom grant types, and older schema-version records.

### 17.2. Testing TTL and Cleanup

| Test Case | Expected Result |
| --- | --- |
| Authorization Code expired | Code is inactive; record stays if other tokens need it |
| Access Token expired | Access token is inactive; Refresh Token still resolves |
| Refresh Token still valid | Authorization is not cleaned up |
| All tokens expired | Record becomes eligible for retention cleanup |
| Token without `expiresAt` | Cleaned up per dedicated policy, not prematurely |
| `TokenSettings` changed | Existing tokens retain their original `expiresAt` |
| Clock skew | Does not make tokens live unexpectedly past policy |
| Cache TTL | Does not exceed token expiry or retain revoked state |

### 17.3. Testing Token Metadata

- Update custom metadata while preserving claims metadata.
- Read back metadata after restart.
- Invalidate a token and verify `isInvalidated()` and `isActive()` behave correctly.
- Add a claim before JWT issuance and verify the claim inside the signed JWT.
- Edit database metadata after issuance and verify the old JWT remains unchanged.
- Verify introspection returns only permitted claims.

### 17.4. Testing findByToken

Test with Authorization Code, Access Token, Refresh Token, ID Token, Device Code, User Code, and any custom token types supported by the application.

Test both specific `tokenType` values, `tokenType == null`, non-existent tokens, expired tokens, invalidated tokens, and hash/key-version lookups after rotating the HMAC key.

### 17.5. Testing Concurrency

Execute concurrently:

- Two requests redeeming the same Authorization Code.
- Two requests using the same Refresh Token with rotation enabled.
- Concurrent revocation and introspection.
- Concurrent metadata update and token refresh.
- Concurrent cleanup job and refresh request.

Results must ensure one-time tokens cannot be consumed twice, revoked tokens never become active again due to stale writes, and cleanup never deletes authorizations with usable tokens.

## 18. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Refresh Token rejected after a few minutes | Cleanup used the Authorization Code or Access Token TTL for the whole aggregate | Compute retention from all tokens still needed |
| `findByToken` returns `null` even though token is in record | Token index not updated or wrong HMAC key version | Check token type, HMAC, and index transaction |
| Introspection wrongly reports inactive | Invalidation/expiry metadata deserialized incorrectly | Check `issuedAt`, `expiresAt`, and standard metadata |
| Refresh Token rotation does not work | `save` only inserts, does not update | Implement transactional upsert |
| Old token can still refresh | Invalidation state not persisted | Persist token metadata and verify atomicity |
| Authorization fails to deserialize after upgrade | JSON schema/class types changed | Add schema versioning, migration, and compatibility reader |
| Claims disappear after round-trip | Serializer dropped claims metadata | Restore complete token metadata |
| JWT still contains old claim | Database metadata edited after JWT was signed | Reissue token via token customizer |
| Device flow fails after cleanup | Device/User Code deleted before flow finished | Track TTLs per token |
| Cluster nodes return different state | Cache invalidation or replication lag | Check source of truth and propagation policy |
| Duplicate authorization records | `save` does not upsert by authorization ID | Enforce primary key and transactional upsert |
| Data lost after refresh | Mapper writes only the new token, dropping other tokens | Round-trip the entire aggregate before saving |
| Token leaked in logs | Debug SQL/request logging prints raw tokens | Add redaction and token-safe diagnostics |

## 19. Production Checklist

- [ ] Each `RegisteredClient` has `TokenSettings` tailored to client type and risk level.
- [ ] TTLs are configured for Authorization Code, Access Token, Refresh Token, and Device Code.
- [ ] Do not assume ID Token has a dedicated TTL builder method in `TokenSettings` 1.5.8.
- [ ] Each token stores its actual `issuedAt`/`expiresAt`.
- [ ] Storage retention is never shorter than the lifetime of tokens still needed.
- [ ] Authorization records are not deleted just because one token in the aggregate expired.
- [ ] `save` is a transactional upsert.
- [ ] `remove` deletes the whole authorization only when policy dictates.
- [ ] `findByToken` supports both specific token types and `null`.
- [ ] Token claims/invalidation metadata serialize completely.
- [ ] Authorization attributes serialize safely.
- [ ] Custom grant types reconstruct from string values.
- [ ] JSON schemas have versioning and a migration strategy.
- [ ] Jackson modules/subtypes are allowlisted.
- [ ] Token values are encrypted or appropriately protected; lookup indexes contain no raw tokens.
- [ ] HMAC/encryption keys are versioned with a rotation plan.
- [ ] Token metadata updates preserve standard metadata.
- [ ] JWT claims are added before token signing.
- [ ] Refresh token rotation updates tokens/indexes/history atomically.
- [ ] Single-use Authorization Codes are protected against concurrency.
- [ ] Caches never keep tokens active after revocation.
- [ ] Cleanup jobs are idempotent, batched, and instrumented with metrics.
- [ ] Auditing is stored separately if long-term retention is required.
- [ ] Round-trip, expiry, revocation, rotation, concurrency, and migration tests exist.
- [ ] Raw tokens, credentials, and sensitive claims are never logged.

## 20. References and Conclusion

Official documentation:

- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationService.html)
- [Spring Authorization Server 1.5.8 — OAuth2Authorization API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html)
- [Spring Authorization Server 1.5.8 — OAuth2Authorization.Token API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Token.html)
- [Spring Authorization Server 1.5.8 — OAuth2Authorization.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Builder.html)
- [Spring Authorization Server 1.5.8 — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html)
- [Spring Authorization Server 1.5.8 — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html)
- [Spring Authorization Server — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html)
- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)

**Conclusion:** Custom persistence must preserve the entire authorization aggregate, not just token values. `TokenSettings` determines TTLs at issuance; the generated token's `issuedAt` and `expiresAt` are the authoritative data to restore. Storage retention must consider every token still needed within the authorization. Serialization must preserve attributes, token classes, claims, and standard metadata; custom metadata must be namespaced and never drop invalidation flags or claims metadata. When updating, use `OAuth2Authorization.from(existing)`, modify the target fields, and call `OAuth2AuthorizationService.save`. For refresh rotation, revocation, and single-use authorization codes, persistence requires transaction/concurrency controls and synchronized token indexes. When these rules are tested together, the Authorization Server can recover consistent state across restarts, scale-outs, and schema upgrades.



