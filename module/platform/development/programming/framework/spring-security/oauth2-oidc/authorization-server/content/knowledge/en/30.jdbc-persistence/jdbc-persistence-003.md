# JdbcOAuth2AuthorizationService and the Authorization Schema

An Authorization Server must remember the state of issued authorizations to continue processing subsequent requests. When a client exchanges an authorization code, refreshes an access token, introspects a token, revokes a token, or completes a multi-step protocol flow, the server needs to look up the exact authorization and its related tokens. If data resides only in a single JVM's memory, state is lost on process restart and other nodes in the cluster cannot see it.

Spring Authorization Server provides the **OAuth2AuthorizationService** abstraction to store and query **OAuth2Authorization**. **JdbcOAuth2AuthorizationService** is an implementation that uses Spring JDBC to persist authorizations into a relational database. It comes with a standard SQL schema and two mappers to convert between the object model and table columns.

This lesson belongs to the **JDBC Persistence** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The module's scope is learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The focus here is the structure of an authorization record, configuring `JdbcOAuth2AuthorizationService`, the `oauth2_authorization` schema, token lifecycle, and production persistence requirements.

> **Core Point:** `JdbcOAuth2AuthorizationService` stores an `OAuth2Authorization` along with the state of the tokens attached to that authorization. It does not replace `RegisteredClientRepository`, `OAuth2AuthorizationConsentService`, a session store, or a signing-key store. Each component manages a distinct type of data.

## 1. Why Does an Authorization Server Need Persistence?

An Authorization Server has multiple protocol flows requiring durable state:

- Authorization Code Flow creates an authorization code and waits for the client to exchange it at the token endpoint.
- Refresh Token Flow looks up the authorization containing the refresh token, checks its state, and updates it with new tokens.
- Token Introspection looks up the authorization by access token to determine whether the token is still active.
- Token Revocation looks up the authorization and marks the token invalidated per endpoint semantics.
- Device Authorization Flow stores the device code, user code, expiration time, and approval status.
- OIDC stores the ID Token and claims associated with the authorization.
- Extensions/custom grants may store additional attributes or token metadata.

If using `InMemoryOAuth2AuthorizationService`, data lives in process memory. After a restart, old authorizations vanish. In a cluster, node A and node B can hold different records. That causes errors such as authorization codes not being found, refresh tokens not being recognized, or introspection returning inactive even though the token was just issued on another node.

JDBC persistence lets nodes read from the same data source and preserve state across restarts. In return, the application must design schemas, transactions, indexes, connection pools, backups, migrations, and database access controls.

### 1.1. In-Memory vs. JDBC

| Criterion | InMemoryOAuth2AuthorizationService | JdbcOAuth2AuthorizationService |
|---|---|---|
| Storage location | JVM heap | Relational database |
| Restart | Authorizations lost | Data survives per database |
| Multiple nodes | Each node has separate state | Can share a database |
| Setup | Simple | Requires schema and DataSource |
| Query capability | In-memory lookup | SQL lookup by ID/token |
| Operations | Suitable for development/testing | Suitable for long-term persistence, requires tuning |
| Throughput | No network/database round-trip | Depends on database, schema, and query plans |

Spring Authorization Server uses `InMemoryOAuth2AuthorizationService` by default if the application does not supply an `OAuth2AuthorizationService`. This is a convenient choice for development and testing. For production, evaluate shared persistence and authorization lifecycles.

### 1.2. An Authorization Is More Than Just an Access Token

An authorization record can contain multiple tokens and states:

~~~text
OAuth2Authorization
  id
  registeredClientId
  principalName
  authorizationGrantType
  authorizedScopes
  attributes
  tokens
    authorizationCode
    accessToken
    oidcIdToken
    refreshToken
    userCode
    deviceCode
~~~

Not every grant produces all tokens. For instance, Client Credentials typically has only an access token; Authorization Code has an authorization code, access token, and possibly a refresh token; OIDC Authorization Code also includes an ID Token.

## 2. Boundaries Between Persistence Components

An Authorization Server has several kinds of data that need persistent storage. Do not lump everything into a single authorization table.

~~~mermaid
flowchart TD
    AS[Authorization Server] --> RC[RegisteredClientRepository]
    AS --> AU[OAuth2AuthorizationService]
    AS --> CO[OAuth2AuthorizationConsentService]
    AS --> JK[JWKSource / Key Store]
    AS --> SS[HTTP Session Store]
    RC --> RDB[(Relational Database)]
    AU --> RDB
    CO --> RDB
    JK --> KS[(Protected Key Store)]
    SS --> SDB[(Session Store)]
    AU --> TOK[Authorization + token state]
    RC --> CLI[Client registrations]
    CO --> COT[Granted authorities / consent]
~~~

| Component | Managed data | JDBC implementation |
|---|---|---|
| RegisteredClientRepository | Client ID, secret, grant types, redirect URIs, scopes, token/client settings | `JdbcRegisteredClientRepository` |
| OAuth2AuthorizationService | Authorization, token values, token metadata, grant-specific attributes | `JdbcOAuth2AuthorizationService` |
| OAuth2AuthorizationConsentService | Authorities/scopes approved by the user for a client | `JdbcOAuth2AuthorizationConsentService` |
| JWKSource / key store | Private/public signing keys | Dedicated key management mechanism |
| Session repository | HTTP sessions and SecurityContext | Servlet container or Spring Session |

`JdbcOAuth2AuthorizationService` needs `RegisteredClientRepository` to reconstruct the `RegisteredClient` when reading an authorization. If a record references a `registered_client_id` that no longer exists, the row mapper cannot build a complete `OAuth2Authorization`.

### 2.1. The Three JDBC Repositories Usually Go Together

In production, you typically need at least:

1. `JdbcRegisteredClientRepository` to store client registrations;
2. `JdbcOAuth2AuthorizationService` to store authorizations and token state;
3. `JdbcOAuth2AuthorizationConsentService` to store consents if the application uses authorization consent.

Each repository has its own schema. Creating the `oauth2_authorization` table does not automatically create the registered client or consent tables. Use the exact schema resource for each component matching the deployed library version.

### 2.2. Why Is RegisteredClientRepository a Required Dependency?

The `oauth2_authorization` table stores `registered_client_id` rather than duplicating all client metadata in every authorization row. When reading a row, `JdbcOAuth2AuthorizationService` calls `RegisteredClientRepository.findById(...)` to look up the client registration, then uses it to construct `OAuth2Authorization.Builder`.

Therefore:

- `registered_client_id` must reference an existing `RegisteredClient`;
- Client registrations must be stored persistently and shared across nodes;
- Do not delete a client registration while authorizations still exist that need to be read;
- When migrating internal client IDs, update or migrate related authorization records.

## 3. What Does OAuth2Authorization Store?

`OAuth2Authorization` is the model representing an authorization granted to a client by a resource owner or by the client itself, such as in the Client Credentials grant. It contains common state and grant-type-dependent tokens.

Main properties:

| Property | Meaning |
|---|---|
| `id` | Unique ID of the authorization record |
| `registeredClientId` | Internal ID of the `RegisteredClient` |
| `principalName` | Principal name of the resource owner or client |
| `authorizationGrantType` | Grant executed |
| `authorizedScopes` | Scopes granted to the client |
| `tokens` | Issued `OAuth2Token`s and corresponding metadata |
| `attributes` | Additional grant state, e.g., `Principal` or `OAuth2AuthorizationRequest` |

### 3.1. Grant-Type-Dependent Tokens

| Grant/flow | Tokens or state typically attached to the authorization |
|---|---|
| Authorization Code | Authorization Code, Access Token, Refresh Token depending on configuration |
| OIDC Authorization Code | Authorization Code, OIDC ID Token, Access Token, Refresh Token depending on configuration |
| Client Credentials | Access Token |
| Refresh Token | Authorization updated with new token state |
| Device Authorization | Device Code, User Code, and Access Token after approval |
| Custom grant | Tokens/attributes produced by the grant implementation |

### 3.2. Authorized Scopes Differ from Access Token Scopes

`authorized_scopes` are the scopes granted in the authorization. `access_token_scopes` are the scopes attached to a specific access token. Both sets may match in simple flows, but do not assume they are always identical if token customization or policies produce narrower access tokens.

### 3.3. Token Metadata Holds Lifecycle State

Each token in `OAuth2Authorization` is wrapped by `OAuth2Authorization.Token` and has its own metadata. Key states include:

- `isExpired()`: the token is past `expiresAt`;
- `isInvalidated()`: the token has been marked invalidated;
- `isActive()`: the token is neither expired nor invalidated;
- `getClaims()`: claims attached to the token if the token carries claims.

Token value, `issuedAt`, `expiresAt`, and metadata are persisted to reconstruct the corresponding object. When revocation occurs, the authorization usually has its token metadata updated to reflect invalidation; the entire authorization record is not always deleted.

## 4. The OAuth2AuthorizationService Contract

`OAuth2AuthorizationService` is the central abstraction for saving new authorizations and querying existing ones. Protocol components call this service during client authentication, authorization grant processing, token introspection, token revocation, dynamic client registration, and related flows.

Primary contract:

~~~java
public interface OAuth2AuthorizationService {

    void save(OAuth2Authorization authorization);

    void remove(OAuth2Authorization authorization);

    OAuth2Authorization findById(String id);

    OAuth2Authorization findByToken(
        String token,
        OAuth2TokenType tokenType
    );
}
~~~

This is the conceptual API signature. `findByToken` takes `tokenType` to narrow which token type to search for; `tokenType` can be `null` when the caller does not know the type yet.

### 4.1. save

`save` persists the current authorization state. It is called when a grant creates an authorization, when a token is issued, when refresh token rotation updates tokens, or when token metadata changes.

Do not call `save` with a stale object after the authorization has been updated by another flow. Using stale data can overwrite newer state.

### 4.2. findById

`findById` retrieves an authorization by its unique ID. The method returns `null` if not found.

~~~java
OAuth2Authorization authorization =
    authorizationService.findById(authorizationId);

if (authorization == null) {
    // No matching authorization record exists.
}
~~~

This ID is the ID of the authorization record, not the client ID, user ID, or token value.

### 4.3. findByToken

`findByToken` looks up the authorization containing the presented credential. `tokenType` is a hint so the repository searches only the matching column, such as access token, refresh token, authorization code, ID Token, user code, or device code.

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        presentedToken,
        OAuth2TokenType.ACCESS_TOKEN
    );
~~~

This method only locates the authorization record. The caller must still verify that the token is active, of the expected type, for the expected client and scopes, and satisfies endpoint policies. Finding a row does not mean the token is valid.

### 4.4. remove

`remove` deletes the entire `OAuth2Authorization` record depending on the implementation. This operation differs from invalidating a specific token. If you only want to revoke one token in an authorization containing multiple tokens, you typically update the token metadata and re-save the authorization according to grant/endpoint semantics.

Do not use `remove` indiscriminately as a substitute for token revocation. Deleting the record can cause the server to lose the code, refresh token, access token metadata, and state needed for subsequent flows.

## 5. JdbcOAuth2AuthorizationService

`JdbcOAuth2AuthorizationService` is the implementation of `OAuth2AuthorizationService` that uses `JdbcOperations` to persist `OAuth2Authorization`. The constructor requires:

- `JdbcOperations` to execute SQL;
- `RegisteredClientRepository` to reconstruct client registrations;
- Optional `LobHandler` to read/write large binary or large text fields.

Common constructor:

~~~java
JdbcOAuth2AuthorizationService(
    JdbcOperations jdbcOperations,
    RegisteredClientRepository registeredClientRepository
)
~~~

Another overload accepts a `LobHandler`:

~~~java
JdbcOAuth2AuthorizationService(
    JdbcOperations jdbcOperations,
    RegisteredClientRepository registeredClientRepository,
    LobHandler lobHandler
)
~~~

### 5.1. Basic Bean Configuration

~~~java
@Configuration
public class AuthorizationPersistenceConfiguration {

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcOperations jdbcOperations,
            RegisteredClientRepository registeredClientRepository) {

        return new JdbcOAuth2AuthorizationService(
            jdbcOperations,
            registeredClientRepository
        );
    }
}
~~~

Spring Boot can provide `DataSource` and `JdbcTemplate` once the JDBC dependency, driver, and datasource properties are configured. `JdbcTemplate` implements `JdbcOperations`, so it can be injected directly into the constructor.

### 5.2. Combining with JdbcRegisteredClientRepository

In production, `RegisteredClientRepository` should also use persistent storage:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcOperations jdbcOperations) {
    return new JdbcRegisteredClientRepository(jdbcOperations);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository) {
    return new JdbcOAuth2AuthorizationService(
        jdbcOperations, registeredClientRepository);
}
~~~

This snippet illustrates the dependency relationship. The application must run both the `RegisteredClient` schema and the `Authorization` schema before starting the service.

### 5.3. Registering via OAuth2AuthorizationServerConfigurer

You can configure the service directly through the configurer:

~~~java
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
        .with(authorizationServer, server -> server
            .authorizationService(authorizationService)
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

When the service is declared as an `OAuth2AuthorizationService` bean, auto-configuration or explicit application configuration can pick up that bean. If multiple implementations exist, specify explicitly which bean is injected into the Authorization Server.

### 5.4. OAuth2AuthorizationService Is Optional, but Production Persistence Should Not Be Left to Default

The framework can default to `InMemoryOAuth2AuthorizationService` when the application does not register a service. That is convenient for small demos and tests, but state is lost on process restart and is not shared across nodes.

A production configuration should verify:

- The `JdbcOAuth2AuthorizationService` bean is created properly;
- The Authorization Server actually uses that bean;
- The schema has been migrated;
- `RegisteredClientRepository` can resolve client IDs;
- All nodes use the same database/schema;
- Connection pool and transaction manager are appropriate.

## 6. Standard oauth2_authorization Schema

`JdbcOAuth2AuthorizationService` depends on the table defined in the resource:

~~~text
classpath:org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
~~~

The schema must exist in the database before the service is used. This is the schema for authorization records, not the schema for registered clients or consents.

### 6.1. Table Structure

The standard Spring Authorization Server 1.5.x schema creates the `oauth2_authorization` table with these column groups:

| Group | Columns | Contents |
|---|---|---|
| Identity | `id` | Primary key of the authorization |
| Client/principal | `registered_client_id`, `principal_name` | Client registration and resource owner/client |
| Grant | `authorization_grant_type` | Executed grant type |
| Scope | `authorized_scopes` | Granted scopes |
| Attributes | `attributes` | Additional authorization attributes |
| State | `state` | Authorization request state if present |
| Authorization Code | `authorization_code_value`, `authorization_code_issued_at`, `authorization_code_expires_at`, `authorization_code_metadata` | Code and metadata |
| Access Token | `access_token_value`, `access_token_issued_at`, `access_token_expires_at`, `access_token_metadata`, `access_token_type`, `access_token_scopes` | Access token and related info |
| OIDC ID Token | `oidc_id_token_value`, `oidc_id_token_issued_at`, `oidc_id_token_expires_at`, `oidc_id_token_metadata` | ID Token and claims metadata |
| Refresh Token | `refresh_token_value`, `refresh_token_issued_at`, `refresh_token_expires_at`, `refresh_token_metadata` | Refresh token |
| User Code | `user_code_value`, `user_code_issued_at`, `user_code_expires_at`, `user_code_metadata` | Device Authorization user code |
| Device Code | `device_code_value`, `device_code_issued_at`, `device_code_expires_at`, `device_code_metadata` | Device code |

Token columns can be `null` because an authorization does not necessarily contain every token type. For example, Client Credentials does not generate an authorization code, ID Token, user code, or device code.

### 6.2. Condensed DDL for Reading the Structure

The snippet below illustrates only the column groups and data types in the default schema. When deploying, use the SQL resource bundled with your exact dependency version and adjust data types for your database vendor.

~~~sql
CREATE TABLE oauth2_authorization (
    id varchar(100) NOT NULL,
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorization_grant_type varchar(100) NOT NULL,
    authorized_scopes varchar(1000) DEFAULT NULL,
    attributes blob DEFAULT NULL,
    state varchar(500) DEFAULT NULL,

    authorization_code_value blob DEFAULT NULL,
    authorization_code_issued_at timestamp DEFAULT NULL,
    authorization_code_expires_at timestamp DEFAULT NULL,
    authorization_code_metadata blob DEFAULT NULL,

    access_token_value blob DEFAULT NULL,
    access_token_issued_at timestamp DEFAULT NULL,
    access_token_expires_at timestamp DEFAULT NULL,
    access_token_metadata blob DEFAULT NULL,
    access_token_type varchar(100) DEFAULT NULL,
    access_token_scopes varchar(1000) DEFAULT NULL,

    oidc_id_token_value blob DEFAULT NULL,
    oidc_id_token_issued_at timestamp DEFAULT NULL,
    oidc_id_token_expires_at timestamp DEFAULT NULL,
    oidc_id_token_metadata blob DEFAULT NULL,

    refresh_token_value blob DEFAULT NULL,
    refresh_token_issued_at timestamp DEFAULT NULL,
    refresh_token_expires_at timestamp DEFAULT NULL,
    refresh_token_metadata blob DEFAULT NULL,

    user_code_value blob DEFAULT NULL,
    user_code_issued_at timestamp DEFAULT NULL,
    user_code_expires_at timestamp DEFAULT NULL,
    user_code_metadata blob DEFAULT NULL,

    device_code_value blob DEFAULT NULL,
    device_code_issued_at timestamp DEFAULT NULL,
    device_code_expires_at timestamp DEFAULT NULL,
    device_code_metadata blob DEFAULT NULL,

    PRIMARY KEY (id)
);
~~~

The full schema is the contract between the service, parameter mapper, and row mapper. Do not rename columns or omit a token group if you still use the default mappers.

### 6.3. There Is No Single Shared expires_at Column

The schema stores `issued_at` and `expires_at` separately for each token type. This reflects that an authorization may hold multiple tokens with different lifecycles. Do not assume a single `authorization_expires_at` exists for cleaning up the entire record.

If expiry-based cleanup is needed, clearly define which token types determine when an authorization record can be deleted, as well as retention policies for authorization codes, refresh tokens, user/device codes, and audit metadata.

### 6.4. The Default Table Has a Primary Key, Not Strategic Indexes

The minimal standard schema creates a primary key on `id`. Token lookup queries may search across multiple token value columns. With large data volumes, inspect query plans and design indexes suitable for your database. Do not assume the default schema is already optimized for all production loads.

## 7. Database Vendors and LOB Data Types

The default schema uses `BLOB` for large values such as token values, attributes, and token metadata. Not every database supports the same data types.

### 7.1. PostgreSQL

PostgreSQL does not support the `BLOB` type in the default SQL resource syntax. Schema documentation requires changing **all columns declared as `BLOB` to `TEXT`** when using PostgreSQL. Do not change only token value columns and forget the metadata/attributes columns.

Example:

~~~sql
attributes text DEFAULT NULL,
authorization_code_value text DEFAULT NULL,
authorization_code_metadata text DEFAULT NULL,
access_token_value text DEFAULT NULL,
access_token_metadata text DEFAULT NULL
~~~

Apply the same adjustment to the OIDC ID Token, refresh token, user code, and device code columns. Keep column names and semantics intact; data types must be compatible with `LobHandler` and the parameter mapper.

### 7.2. CLOB and VARCHAR

Some databases or custom schemas may use `CLOB` or a suitably sized `VARCHAR` instead of `BLOB`. `JdbcOAuth2AuthorizationService` includes a `LobHandler` and checks column metadata to map LOB values. However, do not blindly switch `BLOB` to a short `VARCHAR` without checking whether tokens/JWTs/metadata could exceed the limit.

### 7.3. Timestamps and Timezones

`issuedAt`/`expiresAt` are passed via `java.sql.Timestamp`. Standardize timezones across the application, JDBC driver, and database. With PostgreSQL, you may choose `timestamptz` in migrations if the architecture requires explicit `Instant` storage; any type change must be tested with the active driver and mappers.

With MySQL, configure the JDBC connection timezone and driver to preserve instants according to Connector/J guidance. Avoid running nodes in different timezones, as that can cause token expiry errors or faulty cleanup queries.

### 7.4. Migrations Must Track Versions

Do not copy a schema from Spring Authorization Server 1.5.x into Spring Security 7.x assuming all mappers and serializers are identical. Extract schemas and APIs matching your exact BOM, store them as versioned migrations, and test upgrades on a database clone.

## 8. Schema Initialization and Migration Management

The SQL schema is packaged in the Spring Authorization Server JAR. You can use this resource in development/test or as a reference source to craft your own migrations.

### 8.1. Initializing with Spring Boot SQL Initialization

Example configuration for a local environment:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations:
        - classpath:org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
~~~

This snippet only initializes the authorization schema. If the application uses `JdbcRegisteredClientRepository` or `JdbcOAuth2AuthorizationConsentService`, the corresponding schemas are also needed. Never enable schema initialization blindly in production because DDL could re-run or conflict with existing data.

### 8.2. Using Flyway or Liquibase in Production

A controlled migration process:

1. Select the exact schema resource from the Spring Authorization Server version being deployed.
2. Adjust `BLOB`/`CLOB`/`TEXT`, timestamps, and column lengths for the database vendor.
3. Save the DDL as a versioned migration in source control.
4. Run migrations in the pipeline or a release job with DDL privileges.
5. Verify the schema version and required columns before starting new nodes.
6. Run integration tests against the corresponding database engine.
7. Maintain a rollback/restore plan and take backups before destructive migrations.

Do not let every application node execute an uncoordinated set of DDL statements when multiple nodes deploy simultaneously.

### 8.3. Schema Is a Contract, Not Just a Table with the Same Name

The service uses table names, column names, data types, and SQL parameter ordering defined in its implementation. If you rename tables or columns, changing the schema alone will break the service. When a custom schema is required, replace both SQL/queries and mapping logic with an appropriate implementation or custom service.

## 9. Default Parameter Mapper and Row Mapper

`JdbcOAuth2AuthorizationService` converts the object model into SQL parameters when writing, and converts a `ResultSet` back into `OAuth2Authorization` when reading. The two main extension points are:

- **authorizationParametersMapper:** `Function` from `OAuth2Authorization` to `List<SqlParameterValue>`;
- **authorizationRowMapper:** `RowMapper` from `ResultSet` to `OAuth2Authorization`.

In Spring Authorization Server 1.5.x, the two default implementations are:

- `OAuth2AuthorizationParametersMapper`;
- `OAuth2AuthorizationRowMapper`.

### 9.1. Parameter Mapper

The parameter mapper reads:

- Authorization ID, registered client ID, principal name, and grant type;
- Authorized scopes;
- Attributes and state;
- Token values, `issuedAt`, `expiresAt`, and metadata for each token type;
- Access token type and access token scopes.

Maps such as attributes and token metadata are serialized to JSON using an `ObjectMapper` registered with Spring Security Jackson modules and `OAuth2AuthorizationServerJackson2Module`. Token/LOB values are converted into bytes or text matching the column type.

### 9.2. Row Mapper

The row mapper:

1. Reads `registered_client_id`;
2. Looks up the `RegisteredClient` from `RegisteredClientRepository`;
3. Restores `id`, principal, grant type, scopes, and attributes;
4. Restores each token if its corresponding token value is non-null;
5. Restores `issuedAt`/`expiresAt` and token metadata;
6. Builds the complete `OAuth2Authorization`.

If the `RegisteredClient` no longer exists, the row mapper cannot construct the authorization and raises a data retrieval error.

### 9.3. Why Are Jackson Modules Needed?

Attributes and metadata can contain Spring Security/OAuth2 types that a default Jackson `ObjectMapper` does not serialize/deserialize with the right semantics. Security Jackson modules and `OAuth2AuthorizationServerJackson2Module` supply the mixins/serializers required for those types.

If you replace `ObjectMapper` arbitrarily, certain attributes may fail to deserialize or lose type information. Test round-trips for every custom attribute the application stores inside `OAuth2Authorization`.

### 9.4. When to Use Custom Mappers?

Only replace mappers when you need:

- Custom schemas or column names;
- Custom data types;
- Custom authorization attributes requiring dedicated serializers;
- Database-driver-specific LOB handling;
- Optimized SQL mapping for a specific workload;
- Data compatibility across application versions.

If you only want to add a claim to a JWT, do not edit the JDBC mappers. Token customization belongs in `OAuth2TokenCustomizer`; JDBC mappers are responsible for persisting the authorization object and metadata.

## 10. Configuring Custom Mappers

`JdbcOAuth2AuthorizationService` allows setting the parameter mapper and row mapper via setters:

~~~java
authorizationService.setAuthorizationParametersMapper(parametersMapper);
authorizationService.setAuthorizationRowMapper(rowMapper);
~~~

Call these two setters during bean initialization before the service handles requests. Never swap mappers while the server is actively processing requests.

Illustrative example:

~~~java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository,
        AuthorizationParametersMapper parametersMapper,
        AuthorizationRowMapper rowMapper) {

    JdbcOAuth2AuthorizationService service =
        new JdbcOAuth2AuthorizationService(
            jdbcOperations, registeredClientRepository);

    service.setAuthorizationParametersMapper(parametersMapper);
    service.setAuthorizationRowMapper(rowMapper);
    return service;
}
~~~

`AuthorizationParametersMapper` and `AuthorizationRowMapper` here are application-defined abstractions implementing the corresponding `Function` and `RowMapper` contracts. They must match the SQL schema and the service's parameter ordering exactly. This is a wiring example, not built-in framework classes.

### 10.1. Bidirectional Mappers Must Be Symmetric

If the parameter mapper writes JSON attributes in one format while the row mapper reads another format, data will fail to round-trip. Test:

- Save followed by `findById`;
- Save followed by `findByToken` for each token type;
- Custom attributes;
- Token claims and metadata;
- Null/empty values;
- Exact timestamps;
- Both new data and legacy data after migrations.

### 10.2. Replacing LobHandler

The constructor overload accepts a `LobHandler` to handle large binary/text fields per database. Use it when the driver/database requires specific LOB binding. Before changing it, verify schema column types and tests that read/write long tokens.

## 11. Storing Tokens and Revocation State

The authorization table stores token values and metadata so protocol providers can locate authorizations and check status. Understand the difference between deleting an authorization, clearing a token value, and marking a token invalidated.

### 11.1. Active/Inactive Tokens

A token is generally active when it is neither expired nor invalidated. When a token is revoked, the authorization can have its token metadata updated to mark it invalidated. Introspection or related providers inspect that status.

### 11.2. Revocation Does Not Necessarily Delete the Whole Authorization

An authorization code that has been exchanged for an access token may still need the authorization record to hold the access/refresh tokens. Deleting the entire row just because the code was used would lose the state of the other tokens.

Likewise, revoking a refresh token does not mean deleting every other token in the authorization if policy only revokes the refresh token. Let protocol providers update token state with the right semantics.

Illustrative example of marking an access token invalidated and saving the authorization:

~~~java
OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
    authorization.getAccessToken();

if (accessToken != null) {
    OAuth2Authorization updated = OAuth2Authorization.from(authorization)
        .token(accessToken.getToken(), metadata ->
            metadata.put(
                OAuth2Authorization.Token.INVALIDATED_METADATA_NAME,
                true
            )
        )
        .build();

    authorizationService.save(updated);
}
~~~

This illustrates the token metadata lifecycle; in real applications, let the framework's revocation provider handle protocol validation, client authorization, and which token types are revoked. Never expose this code via an unprotected admin API.

### 11.3. Token Values in the Database Are Sensitive Credentials

The database may contain authorization codes, opaque access tokens, refresh tokens, ID Tokens, user codes, and device codes. Anyone with table read access can extract valid credentials if data is stored directly.

Controls:

- Restrict database roles following the least privilege principle;
- Enable encryption at rest and protect backups;
- Use TLS for JDBC connections;
- Never log token values or SQL bind parameters containing credentials;
- Restrict access to consoles/BI/analytics tools;
- Establish a DB credential rotation process;
- Monitor anomalous queries against the authorization table.

Do not assume `BLOB` means the data is encrypted. Column types only describe storage format, not secret protection.

## 12. Save, Update, Remove, and Token Queries

Understanding how the service executes CRUD operations helps diagnose persistence issues and prevents manual SQL edits from corrupting authorization state.

### 12.1. save Distinguishes Insert and Update

In the standard JDBC implementation, `save` checks whether the authorization ID already exists. If not, the service inserts a new row; if it exists, the service updates the corresponding row.

~~~java
authorizationService.save(authorization);
~~~

Because the authorization ID is the primary key, the same authorization can be saved multiple times as token metadata changes. Do not generate a new authorization ID on every token refresh if the flow needs to update the existing record.

### 12.2. remove Deletes the Authorization by ID

~~~java
authorizationService.remove(authorization);
~~~

The standard implementation deletes the row by authorization ID. This deletes the entire authorization record. Before using it, ensure all related tokens have expired or no longer need to be looked up.

### 12.3. findById

Queries by primary key:

~~~sql
SELECT *
FROM oauth2_authorization
WHERE id = ?;
~~~

This is the right lookup when a component already knows the authorization ID.

### 12.4. findByToken with a Specific Token Type

For an access token:

~~~sql
SELECT *
FROM oauth2_authorization
WHERE access_token_value = ?;
~~~

Other token types correspond to their own columns: `authorization_code_value`, `oidc_id_token_value`, `refresh_token_value`, `user_code_value`, and `device_code_value`. State is stored in the `state` column.

When the caller passes `tokenType`, the service selects the matching filter. When `tokenType` is `null`, the standard implementation also checks the `state` column alongside the authorization code, access token, ID Token, refresh token, user code, and device code columns. This helps when the caller does not know the credential type, but the query must compare more columns.

### 12.5. Custom Token Types Are Not Automatically Supported

The standard schema only has the listed token columns. If a custom grant creates its own credential type, do not assume `findByToken` will automatically find that token. Decide how to store the token and metadata, then provide a matching custom `OAuth2AuthorizationService`/mapper/query.

Do not write a custom token into `access_token_value` just to reuse built-in queries if that token has semantics different from an access token.

## 13. Indexes, Query Plans, and Performance

The standard schema has a primary key on `id`, yet Authorization Server workloads also look up rows by token value. With a large number of authorizations, `findByToken` queries can become a bottleneck if the database must scan many rows.

### 13.1. Identifying Real Query Paths

| Query | Filter column | Consuming components |
|---|---|---|
| `findById` | `id` | Components that already have the authorization ID |
| Authorization Code lookup | `authorization_code_value` | Token endpoint |
| Access Token lookup | `access_token_value` | Introspection, revocation, and resource flows |
| ID Token lookup | `oidc_id_token_value` | OIDC/logout flows depending on provider |
| Refresh Token lookup | `refresh_token_value` | Refresh Token grant/revocation |
| User Code lookup | `user_code_value` | Device verification |
| Device Code lookup | `device_code_value` | Device Authorization grant |
| State lookup | `state` | Authorization request correlation |

### 13.2. Evaluating Indexes per Database Vendor

Do not create indexes on every column mechanically. Token values may be stored as `BLOB`/`TEXT` and some databases do not support direct or efficient indexing on LOBs. Run `EXPLAIN`/`EXPLAIN ANALYZE` against production-like data to identify which queries need optimization.

Options to consider:

- Dedicated indexes on token columns whose data types support them;
- Indexes on `principal_name` or `registered_client_id` if corresponding admin/cleanup queries run;
- Additional digest/hash columns for token lookup when LOBs cannot be indexed;
- Custom service/queries using digests to locate candidates, then verifying the full token value;
- Partitioning or archiving authorization records per policy and database capability.

If adding digest columns, update token writes, queries, rotation/migration, and collision handling together. A hash does not replace checking the original token; after finding candidates, still compare the full credential by design.

### 13.3. High Throughput

Spring Authorization Server API documentation describes `JdbcOAuth2AuthorizationService` as a simplified JDBC implementation and notes it may not satisfy environments requiring high throughput. As workload grows, the consuming application is expected to provide a custom `OAuth2AuthorizationService` implementation suited to its deployment.

Measure these metrics:

- P50/P95/P99 latency of `save`/`findByToken`/`findById`;
- Queries per authorization flow;
- Connection pool active/idle/wait counts;
- Database CPU, lock waits, and I/O;
- Authorization row count and ratio of expired tokens;
- Size of attributes/token metadata;
- Query plans before and after adding indexes.

### 13.4. Do Not Cache Authorizations Indiscriminately

Caching can reduce database reads, but authorization state changes on refresh, revocation, or token invalidation. Stale caches can cause introspection to return active for a revoked token or allow a refresh flow to accept an old token.

If implementing caching, require synchronous invalidation or a consistency model with clear bounds. For security-sensitive lookups, prioritize token state correctness over cache hit ratio.

## 14. Transactions and Consistency

Authorization grants often perform multiple related operations: client authentication, grant validation, token generation, saving the authorization, and returning the response. Database state must remain consistent if a step fails.

### 14.1. Using the Same DataSource and Transaction Manager

`JdbcOAuth2AuthorizationService` takes `JdbcOperations`. In a Spring application, `JdbcTemplate` and the transaction manager should share the same `DataSource` so JDBC operations participate in the same transaction context.

Example of a custom business service:

~~~java
@Service
public class AuthorizationMaintenanceService {

    private final OAuth2AuthorizationService authorizationService;

    public AuthorizationMaintenanceService(
            OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    @Transactional
    public void updateAuthorization(
            OAuth2Authorization authorization) {
        authorizationService.save(authorization);
    }
}
~~~

This example illustrates a transaction boundary for an application operation. You do not need to wrap every protocol filter in one giant transaction. Choose boundaries based on business needs and avoid holding transactions open while waiting on browsers, slow network calls, or user interaction.

### 14.2. Insert Races and Primary Keys

Because `save` may check `findById` before inserting, two concurrent requests attempting to create the same authorization ID can race. The primary key lets the database prevent duplicate IDs, but the application must define how to handle duplicate-key errors/retries if a flow can replay.

Do not blindly retry every SQL error. Retry only recognized transient errors, with idempotent operations and the latest authorization data.

### 14.3. Avoiding Overwriting Newer State with Stale Objects

A refresh token request may update an authorization while another admin task operates on the same record. If both work from objects read at different times, the later `save` can overwrite newer metadata.

If parallel updates occur, control concurrency via transaction isolation, optimistic locking/a version column in a custom schema, or a service implementation with explicit update semantics. The default schema has no version column.

### 14.4. Do Not Edit SQL Directly While the Application Is Running

Do not update token metadata via manual SQL while the service may be reading/writing the same authorization. Any administrative script must use transactions, backups, auditing, and understand the serialization format. Prefer protected protocol endpoints or service APIs.

## 15. Authorization Consent Is Separate Persistence

`OAuth2AuthorizationConsent` stores a resource owner's consent decision for a client, typically consisting of `registered_client_id`, `principal_name`, and granted authorities. This data is distinct from authorization records.

The standard consent schema has its own table:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorities varchar(1000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

`JdbcOAuth2AuthorizationConsentService` is a separate implementation using the `oauth2-authorization-consent-schema.sql` schema.

### 15.1. Consent vs. Authorized Scopes

Consent describes the authorities a user has granted to a client. `OAuth2Authorization` records the scopes/authorization state of a specific flow. One may outlive an individual authorization record.

Do not use `oauth2_authorization` as the sole table to infer all historical consent decisions. If the application needs to audit consent changes, a dedicated audit log/domain table may be necessary.

### 15.2. Registered Client Persistence Also Has Its Own Schema

`JdbcRegisteredClientRepository` uses the `oauth2_registered_client` table. This table stores encoded client secrets, grant types, authentication methods, redirect URIs, scopes, and settings. Authorization rows only store `registered_client_id` to resolve the registration.

Production needs migrations for all three data groups when used:

~~~text
oauth2_registered_client
oauth2_authorization
oauth2_authorization_consent
~~~

Do not delete a registered client row while authorization records still reference it. If you need to decommission a client, disable/rotate credentials first, retain registration metadata through the retention window, and clean up according to plan.

## 16. Retention, Cleanup, and Expired Data

Token expiration does not make authorization rows disappear automatically. `JdbcOAuth2AuthorizationService` is not a background cleanup scheduler. The system must decide how long to keep authorization records to support introspection, revocation, auditing, refresh tokens, and incident handling.

### 16.1. Cleanup Must Consider All Tokens in an Authorization

An authorization may contain an expired access token while its refresh token is still valid. If cleanup checks only `access_token_expires_at` and deletes the entire row, the refresh token can no longer be found.

Similarly, an expired authorization code whose access token was already issued may still need the record. Device/user codes also have lifecycles distinct from access tokens.

### 16.2. Policy-Driven Cleanup Design

A safe cleanup job should:

1. Identify authorizations with no remaining active tokens and no state required for protocol flows;
2. Apply a retention window for audit/incident needs;
3. Exclude authorizations that still have active refresh tokens;
4. Delete in small batches to avoid large table locks;
5. Emit metrics on rows inspected/deleted;
6. Record audit logs and support dry-run mode;
7. Run in short transactions and be resumable after failures.

The default schema has no single combined `expires_at` column. To enable fast cleanup with a simple query, you can add a column/index in a custom schema, provided you update the service/migrations and define precisely how authorization expiry is calculated.

### 16.3. Archiving and Privacy

Authorization attributes may contain principals, authorization requests, or context information. Retention must account for PII, consent data, and audit requirements. Archiving does not mean copying raw access/refresh tokens into a broadly accessible analytics warehouse.

## 17. Testing JdbcOAuth2AuthorizationService

Testing should use a real database or an engine compatible with the production schema. H2 is useful for fast tests, but it does not fully replace PostgreSQL/MySQL integration tests because LOB types, timestamps, collations, and SQL behaviors differ.

### 17.1. Test Context and Schema

A Spring Boot integration test can configure the schema resource:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:authorization-test;DB_CLOSE_DELAY=-1
    username: sa
    password:
  sql:
    init:
      mode: always
      schema-locations:
        - classpath:org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
~~~

This is an illustrative configuration for H2 tests compatible with the schema syntax. You must also create the registered client schema or seed an appropriate `RegisteredClientRepository`. For PostgreSQL, use the migration with `BLOB` changed to `TEXT`.

### 17.2. Save/findById Round-Trip

~~~java
@SpringBootTest
class JdbcAuthorizationServiceTests {

    @Autowired
    OAuth2AuthorizationService authorizationService;

    @Test
    void savesAndLoadsAuthorizationById() {
        OAuth2Authorization authorization =
            authorizationFixture();

        authorizationService.save(authorization);

        OAuth2Authorization loaded =
            authorizationService.findById(authorization.getId());

        assertThat(loaded).isNotNull();
        assertThat(loaded.getRegisteredClientId())
            .isEqualTo(authorization.getRegisteredClientId());
        assertThat(loaded.getPrincipalName())
            .isEqualTo(authorization.getPrincipalName());
        assertThat(loaded.getAuthorizedScopes())
            .isEqualTo(authorization.getAuthorizedScopes());
    }
}
~~~

`authorizationFixture()` is a test-defined fixture that must use a `RegisteredClient` already registered in the repository. Tests should verify token values, timestamps, claims, and metadata as well—not just three basic fields.

### 17.3. Testing findByToken for Each Token Type

Create an authorization fixture containing an authorization code, access token, ID Token, and refresh token. After saving, verify:

- `findByToken(code, code token type)` returns the right authorization;
- `findByToken(accessToken, ACCESS_TOKEN)` returns the right authorization;
- `findByToken(idToken, id token type)` returns the right authorization;
- `findByToken(refreshToken, REFRESH_TOKEN)` returns the right authorization;
- Non-existent tokens return `null`;
- Mismatched token types return `null`;
- `null` `tokenType` can locate tokens across the standard columns supported by the implementation.

For Device Authorization, add a user code/device code fixture and test both lookups separately.

### 17.4. Testing Update and Remove

~~~java
@Test
void updatesAndRemovesAuthorization() {
    OAuth2Authorization original = authorizationFixture();
    authorizationService.save(original);

    OAuth2Authorization updated = OAuth2Authorization
        .from(original)
        .attribute("test.marker", "updated")
        .build();

    authorizationService.save(updated);

    OAuth2Authorization loaded =
        authorizationService.findById(updated.getId());
    assertThat(loaded.getAttribute("test.marker"))
        .isEqualTo("updated");

    authorizationService.remove(updated);
    assertThat(authorizationService.findById(updated.getId()))
        .isNull();
}
~~~

This is an illustrative skeleton for update/remove. In real tests, ensure the builder preserves token state and required attributes, and verify token lookups also no longer return the record after `remove`.

### 17.5. Testing Token Invalidation Metadata

Create an authorization with an active access token, mark the token metadata invalidated using the appropriate `OAuth2Authorization.Builder` API, re-save, and read it back via JDBC. Verify that the token state remains inactive after the round-trip. This is a critical test because revocation/introspection depends on metadata being persisted accurately.

### 17.6. Database Vendor Testing

Use Testcontainers or a production-equivalent database instance to test:

- PostgreSQL `TEXT` LOB mapping;
- Timestamp/`Instant` round-trips;
- Long token values;
- JSON attributes/metadata;
- Indexes and query plans;
- Transaction rollbacks;
- Concurrent saves/updates;
- Connection pool failure/recovery.

## 18. Performance and Production Operations

`JdbcOAuth2AuthorizationService` performs JDBC reads/writes on the protocol critical path. A slow database or exhausted connection pool can increase latency across the token endpoint, introspection, and revocation.

### 18.1. Connection Pooling

- Size the pool according to concurrency and database capacity;
- Set a connection acquisition timeout;
- Monitor pool pending threads;
- Do not size the pool larger than the database can handle;
- Use TLS and dedicated credentials for the application;
- Test connection validation and failover behavior.

### 18.2. Database Observability

Monitor:

| Metric | Meaning |
|---|---|
| `save` latency | Time to persist an authorization |
| `findByToken` latency | Token lookup time |
| `findById` latency | Lookup time by ID |
| rows in `oauth2_authorization` | Size of the authorization store |
| expired/inactive records | Data subject to retention/cleanup |
| lock wait/deadlocks | Update contention |
| slow queries | Missing indexes or poor query plans |
| connection pool wait | Database/pool unable to keep up with load |
| serialization failures | Attributes/metadata failing round-trip |

### 18.3. Backup and Restore

The authorization database is vital for system recovery. Backups must stay consistent with registered clients and consents. If you restore the authorization table without the matching registered client rows, the row mapper cannot reconstruct authorizations.

Test restores periodically, including:

- Restoring schemas and data;
- Restoring the registered client repository;
- Verifying token/authorization lookups;
- Verifying signing keys remain compatible with non-expired JWTs;
- Testing refresh and introspection flows.

### 18.4. Rolling Deployments and Schema Compatibility

When upgrading Spring Authorization Server/Spring Security, do not deploy a new schema before understanding whether old and new mappers are compatible. Use expand-and-contract:

1. Add new columns/types compatible with the running version;
2. Deploy code capable of reading both old and new formats;
3. Switch writes to the new format;
4. Migrate legacy data in batches;
5. Verify all nodes use the new format;
6. Only then drop old columns/formats.

Never change Jackson serialization or custom attribute formats without migrations and round-trip tests.

## 19. Version Differences and Data Compatibility

Spring Authorization Server 1.5.x is the final generation before Authorization Server was integrated into Spring Security 7.0. When upgrading, review all of the following together:

- Packages/APIs of the dependency in use;
- Jackson generation;
- Default row mapper and parameter mapper;
- SQL schemas;
- Security Jackson modules;
- Runtime hints/native image support;
- Custom attributes persisted from older versions.

### 19.1. Spring Authorization Server 1.5.x

In the 1.5.8 API, the default mappers are:

- `JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper`;
- `JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper`.

They use a Jackson 2 `ObjectMapper` configured with Spring Security Jackson modules and `OAuth2AuthorizationServerJackson2Module`. If the application customizes `ObjectMapper`, keep the required modules to serialize/deserialize OAuth2 authorization attributes and token metadata.

### 19.2. Spring Security 7.0+

In the Spring Security 7 generation, Jackson 3 mappers were added named `JsonMapperOAuth2AuthorizationParametersMapper` and `JsonMapperOAuth2AuthorizationRowMapper`. The older Jackson 2 mappers were deprecated to support migration.

Do not mix Jackson 3 code samples with Spring Authorization Server 1.5.x dependencies. Likewise, do not assume JSON data persisted by Jackson 2 is automatically compatible across all custom types with Jackson 3. Test reading actual migrated data on a database clone before upgrading production.

### 19.3. Schemas and Mappers Must Be Upgraded Together

A schema may retain the same table name while metadata formats or mapper behavior change across versions. Compatibility must be verified by:

1. Taking a snapshot of representative authorization data from the old version;
2. Starting the new application version against a database copy;
3. Running `findById` and `findByToken` for each token type;
4. Inspecting custom attributes, claims, and token metadata;
5. Running refresh, introspection, and revocation flows;
6. Comparing token state before and after migration.

If custom mappers were used, migration testing must cover the application's custom format as well, not only the default mappers.

## 20. Symptom-Based Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| Startup reports missing table `oauth2_authorization` | Schema not migrated | Check migration history and datasource/schema |
| `save` fails with column type error | Incompatible `BLOB`/`CLOB`/`TEXT` | Cross-check database vendor and `LobHandler` |
| `findById` does not find authorization | Record not saved, wrong ID, or transaction rolled back | Check ID, transaction, and commit |
| `findByToken` returns `null` | Wrong `tokenType`, differing token value, or custom column not queried | Check token type and lookup column |
| Row mapper reports missing `RegisteredClient` | Orphaned `registered_client_id` | Check `JdbcRegisteredClientRepository` and client lifecycle |
| JSON deserialization error on attributes | Missing Security Jackson module or incompatible custom type | Check `ObjectMapper` and stored JSON |
| Token metadata lost after restart | Mapper/schema didn't write full metadata or migration missing columns | Round-trip test token metadata |
| PostgreSQL reports type `BLOB` does not exist | Used raw default schema | Change all `BLOB` columns to `TEXT` |
| Timestamp offset or premature token expiry | Driver/database timezone mismatch | Check `Timestamp` mapping, UTC, and JDBC URL |
| Refresh token reused improperly | Save/update race or stale state | Check transactions, authorization ID, and rotation |
| Introspection returns active after revoke | Stale cache or invalidation metadata not saved | Check `OAuth2Authorization.Token` metadata and cache |
| Token endpoint latency rises | Large `findByToken` scan, busy DB/pool | `EXPLAIN`, indexes, pool metrics |
| Node A sees authorization but node B does not | Nodes use different databases/schemas or uncommitted transaction | Check datasource and topology |
| Legacy data unreadable after upgrade | Jackson/schema/mapper incompatibility | Restore snapshot and test migration |

### 20.1. Diagnostic Workflow

1. Identify which `OAuth2AuthorizationService` bean is being injected.
2. Identify the datasource, database/schema, and migration version.
3. Check whether `RegisteredClientRepository` can find the related client ID.
4. Inspect the authorization row by ID using controlled read-only DB privileges.
5. Identify the token type and column used by `findByToken`.
6. Check the mappers, LOB types, and JSON metadata.
7. Check transaction commits, lock waits, and query plans.
8. Reproduce on a database clone before modifying production data.

Never troubleshoot lookup failures by logging token values or pasting credentials into tickets. Use authorization IDs, correlation IDs, and protected token fingerprints.

## 21. Production Checklist

1. **Service bean:** Is the Authorization Server using `JdbcOAuth2AuthorizationService`?
2. **DataSource:** Do `JdbcOperations` and the transaction manager point to the right database?
3. **Registered clients:** Is `RegisteredClientRepository` persistent and able to resolve every `registered_client_id`?
4. **Schema:** Has the exact version of `oauth2-authorization-schema.sql` been migrated?
5. **Vendor types:** Do `BLOB`/`CLOB`/`TEXT` and timestamp types match the database?
6. **OIDC:** Are ID Token columns preserved if the server issues OIDC tokens?
7. **Other grants:** Are user code/device code columns present if using Device Authorization?
8. **Mappers:** Do parameter mapper and row mapper round-trip attributes/metadata?
9. **Jackson:** Are the Security modules and OAuth2 module registered for the right version?
10. **Token state:** Are expiry/invalidation metadata persisted and read back accurately?
11. **Lookup:** Does `findByToken` support every token type in use?
12. **Custom grants:** Are custom queries/mappers in place if credentials fall outside the standard schema?
13. **Indexes:** Do token lookup query plans meet throughput requirements?
14. **Transactions:** Do saves/updates have proper transaction semantics and race handling?
15. **Consent:** Does consent persistence use its own service/schema when needed?
16. **Security:** Are token values, attributes, and backups protected, and do logs avoid leaking credentials?
17. **Cleanup:** Does the retention job avoid deleting authorizations with active tokens?
18. **Testing:** Are round-trip, `findByToken`, update/remove, revoke, and vendor-specific tests in place?
19. **Operations:** Are backup/restore tests, pool metrics, and slow query alerts configured?
20. **Upgrades:** Is there a migration plan for schemas, mappers, and Jackson versions?

## 22. Practice Exercises

**Scenario A — Restart loses refresh tokens:** An Authorization Server uses `InMemoryOAuth2AuthorizationService`. After redeploying, clients refreshing tokens receive `invalid_grant`. Explain the cause and propose how to configure JDBC persistence.

**Scenario B — PostgreSQL fails to create the schema:** A migration uses the raw DDL resource and fails because of `BLOB`. Identify all columns that must change and design an LOB round-trip test.

**Scenario C — Client registration deleted:** An authorization row still exists, but `RegisteredClientRepository` cannot find `registered_client_id`. Why can't the row mapper reconstruct the authorization? Propose a client decommissioning lifecycle.

**Scenario D — Revocation has no effect:** The endpoint returns success, yet introspection still shows active. Analyze the difference between removing an authorization, invalidating token metadata, and re-saving the authorization.

**Scenario E — High throughput:** `findByToken` slows down when the table reaches tens of millions of records. Identify query paths, use `EXPLAIN`, examine LOB indexing, and propose a custom digest lookup if needed.

**Scenario F — Jackson upgrade:** An application upgrades from Spring Authorization Server 1.5.x to Spring Security 7.0. Custom authorization attributes fail to deserialize. Design a compatibility test and migration.

**Scenario G — Faulty cleanup:** A job deletes authorizations when the access token expires while the refresh token is still active. Fix the retention condition so refresh capability is not lost.

**Hints:** A needs `JdbcOAuth2AuthorizationService` and the schema; B changes all `BLOB` columns to `TEXT` on PostgreSQL; C retains registration metadata until related authorizations finish their lifecycle; D marks token invalidated and persists the updated authorization; E optimizes lookups on token columns or digests with a custom service; F tests JSON mappers and stored data on a database clone; G evaluates the status of every token in the authorization.

## 23. Summary

`JdbcOAuth2AuthorizationService` is the JDBC implementation of `OAuth2AuthorizationService`. It persists and queries `OAuth2Authorization`, including the client reference, principal, grant type, authorized scopes, attributes, token values, and metadata. Protocol components rely on this service during authorization grant processing, refresh, introspection, revocation, and related flows.

The `oauth2_authorization` schema is packaged inside Spring Authorization Server and must match the exact version. The table has dedicated column groups for authorization codes, access tokens, OIDC ID Tokens, refresh tokens, user codes, and device codes. Database vendors may require adjusting LOB and timestamp types; PostgreSQL requires changing all `BLOB` columns to `TEXT`.

`JdbcOAuth2AuthorizationService` requires `JdbcOperations` and `RegisteredClientRepository`. The default parameter mapper and row mapper convert the object model to SQL parameters and back. In Spring Authorization Server 1.5.x, default mappers use Jackson 2 with Spring Security/OAuth2 Jackson modules; when upgrading to Spring Security 7, verify Jackson 3 mappers and compatibility with stored data.

For production operations, persist registered clients and consents with their respective repositories when used, manage versioned migrations, protect token values/metadata, optimize `findByToken`, control transactions/concurrency, align retention with the lifecycle of all tokens, and test against the real database vendor. When throughput exceeds the capacity of the simplified JDBC implementation, implement a custom `OAuth2AuthorizationService` tailored to your workload and consistency requirements.

## 24. References

- [Spring Authorization Server 1.5.8 API — JdbcOAuth2AuthorizationService](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): constructors, CRUD/query methods, mapper setters, schema requirements, and high-throughput notes.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClientRepository`, `OAuth2Authorization`, `OAuth2AuthorizationService`, token state, and consent.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): protocol components using the authorization service.
- [Spring Authorization Server 1.5.x — Authorization Schema](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql): `oauth2_authorization` table DDL and PostgreSQL notes.
- [Spring Authorization Server — Registered Client Schema](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql): client registration schema.
- [Spring Authorization Server — Authorization Consent Schema](https://github.com/spring-attic/spring-authorization-server/blob/main/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql): separate consent schema.
- [Spring Security 7 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): API and mappers in the Spring Security 7 integrated generation.
- [Spring Framework — JDBC and Data Access](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `JdbcOperations`, `JdbcTemplate`, and transaction integration.
- [PostgreSQL — Character Types](https://www.postgresql.org/docs/current/datatype-character.html): `TEXT` and string types in PostgreSQL.
- [MySQL Connector/J — Preserving Time Instants](https://dev.mysql.com/doc/connector-j/en/connector-j-time-instants.html): timezone configuration and accurate timestamp storage.
