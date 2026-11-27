# Serializing Principals, Attributes, and Token Metadata

## 1. Why Does JDBC Persistence Need Serialization?

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**. This lesson focuses on how Spring Authorization Server converts an `OAuth2Authorization` into data suitable for JDBC storage and reconstructs that object when a protocol endpoint needs to look it up.

An authorization contains more than just an authorization code, access token, or refresh token. Throughout a flow, the Authorization Server also holds client details, the principal, the authorization request, granted scopes, claims, and the state of each token. This information must outlive the HTTP request because subsequent requests may need to:

- exchange an authorization code for tokens;
- use a refresh token to issue a new access token;
- introspect or revoke a token;
- handle an OIDC ID Token, device code, or other grants;
- check whether a token has expired or been invalidated;
- restore the authorization context on another instance in a cluster.

With `JdbcOAuth2AuthorizationService`, Spring Authorization Server maps an `OAuth2Authorization` to columns of the `oauth2_authorization` table. `Map`-based structures such as authorization attributes and token metadata are serialized to JSON. On read, `OAuth2AuthorizationRowMapper` decodes the JSON and reconstructs the authorization along with its corresponding tokens.

**Example Scope:** APIs and code in this lesson follow Spring Authorization Server **1.5.x**, referencing API 1.5.8 and Jackson 2. On the newer major branch using Jackson 3, module and mapper names change; do not mix code from the two generations.

After this lesson, you will be able to:

1. Distinguish `principalName`, `attributes`, and token metadata inside `OAuth2Authorization`.
2. Understand which data is stored in dedicated columns and which is stored as JSON.
3. Describe the roles of `OAuth2AuthorizationParametersMapper` and `OAuth2AuthorizationRowMapper`.
4. Configure Jackson modules to persist and restore principals along with security attributes.
5. Integrate custom principals or custom attributes in a stable way.
6. Protect polymorphic deserialization and manage schema/type changes across versions.
7. Write round-trip tests to prove an authorization can be accurately reconstructed.

## 2. OAuth2Authorization Data Model

### 2.1. An Authorization Is an Aggregate Storing Flow State

`OAuth2Authorization` represents the authorization state granted to a client. This object includes the authorization identifier, client, principal, grant type, scopes, tokens, and additional attributes.

```java
public class OAuth2Authorization implements Serializable {
    private String id;
    private String registeredClientId;
    private String principalName;
    private AuthorizationGrantType authorizationGrantType;
    private Set<String> authorizedScopes;
    private Map<Class<? extends OAuth2Token>, Token<?>> tokens;
    private Map<String, Object> attributes;
}
```

Tokens depend on the grant:

| Grant/flow | Typically associated tokens |
| --- | --- |
| OAuth2 Authorization Code | Authorization Code, Access Token, optional Refresh Token |
| OIDC Authorization Code | Authorization Code, ID Token, Access Token, optional Refresh Token |
| Client Credentials | Access Token |
| Device Authorization | Device Code, User Code, and Access Token when the flow completes |

Each token can have its own issued-at, expires-at, token value, and metadata. `OAuth2Authorization.Token` also exposes `isExpired()`, `isInvalidated()`, and `isActive()` states.

### 2.2. principalName Is Not the Entire Principal

Two fields easily confused:

- `principalName`: string name of the principal, such as username, subject, or client ID. Spring uses this value for lookups and related operations.
- `attributes`: map holding flow context. In the Authorization Code Flow, the map may contain the authenticated `Authentication` object and `OAuth2AuthorizationRequest`.

Example:

```java
OAuth2Authorization authorization = OAuth2Authorization
        .withRegisteredClient(registeredClient)
        .principalName(authentication.getName())
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizedScopes(authorizedScopes)
        .attribute(Principal.class.getName(), authentication)
        .attribute(
                OAuth2AuthorizationRequest.class.getName(),
                authorizationRequest
        )
        .build();
```

`principal_name` in SQL stores only the `authentication.getName()` string. The `Authentication` object inside `attributes` is what the serializer/deserializer must understand. When restoring a row, `principalName` may still be readable even if the principal object inside `attributes` fails to deserialize; in that case, certain steps of the authorization flow can still fail.

Do not assume implementing `Serializable` is enough. `Serializable` only governs Java's native serialization contract. The JDBC mappers in Spring Authorization Server 1.5.x use Jackson JSON for metadata maps; custom principals must be compatible with the configured `ObjectMapper`.

### 2.3. What Data Does attributes Store?

`attributes` is an extensible map for flow state. Common entries include:

| Attribute | Role |
| --- | --- |
| `Principal.class.getName()` | Authenticated `Authentication`/`Principal` |
| `OAuth2AuthorizationRequest.class.getName()` | Authorization request preserved across redirect/callback |
| Grant-specific attributes | Extra context for custom grants or extensions |

Keys must stay consistent between creating the authorization and reading it back. If custom code adds an object to the map, you are also responsible for ensuring that object can be serialized and restored.

### 2.4. Token Metadata Differs from Token Value

Each token in `OAuth2Authorization` is wrapped by `OAuth2Authorization.Token`, which holds:

- token value;
- issued-at and expires-at;
- additional metadata, such as generated claims or an invalidated flag.

Metadata is typically accessed via `authorization.getToken(...).getMetadata()`. Claims of a JWT/ID Token are stored in metadata under key `OAuth2Authorization.Token.CLAIMS_METADATA_NAME`. The token value is stored separately in its corresponding column.

Thus, storing metadata does not mean storing the entire JWT object. Mappers store the token string, timestamps, token type/scopes, and metadata according to the table's column structure.

## 3. JDBC Serialization Pipeline

### 3.1. Two Mapping Directions

`JdbcOAuth2AuthorizationService` uses two components:

| Component | Direction | Responsibility |
| --- | --- | --- |
| `OAuth2AuthorizationParametersMapper` | Java → SQL | Converts `OAuth2Authorization` into a list of `SqlParameterValue`s for INSERT/UPDATE |
| `OAuth2AuthorizationRowMapper` | SQL → Java | Reads `ResultSet`, parses attributes/metadata, and reconstructs `OAuth2Authorization` |

Write flow:

```text
OAuth2Authorization
       |
       v
OAuth2AuthorizationParametersMapper
       |
       +-- scalar fields -> VARCHAR / TIMESTAMP
       |
       +-- attributes Map -> JSON
       |
       +-- each token value -> token column
       |
       +-- each token metadata Map -> JSON
       |
       v
JdbcOperations -> INSERT or UPDATE oauth2_authorization
```

Read flow:

```text
ResultSet
   |
   v
OAuth2AuthorizationRowMapper
   |
   +-- registered_client_id -> RegisteredClientRepository
   |
   +-- scalar columns -> builder fields
   |
   +-- attributes JSON -> Map<String, Object>
   |
   +-- token value + timestamps + metadata JSON -> token objects
   |
   v
OAuth2Authorization
```

### 3.2. How save Works

Conceptually, `save(authorization)` checks whether the authorization already exists by ID. If not, it executes an INSERT; if it exists, it executes an UPDATE. The mapper generates SQL parameters in the exact order expected by the implementation's statements.

`findById(...)` and `findByToken(...)` use `RowMapper` to reconstruct the object. `findByToken(...)` can search by a specific token type or scan supported token types if the caller does not specify a type.

Do not write a custom SQL INSERT with fewer columns and invoke the default mapper. The parameter list and schema must match; if changing the schema, replace both the mappers and statements accordingly or implement a custom `OAuth2AuthorizationService`.

### 3.3. JSON Stored in Metadata Columns

Key columns in the standard schema include:

| Column | Data |
| --- | --- |
| `id`, `registered_client_id`, `principal_name`, `authorization_grant_type` | Authorization identity and core info |
| `authorized_scopes`, `state` | Scopes and state in scalar/string form |
| `attributes` | JSON map holding principal/authentication and authorization request attributes |
| `authorization_code_value`, `authorization_code_issued_at`, `authorization_code_expires_at` | Authorization code and timestamps |
| `authorization_code_metadata` | JSON metadata of the authorization code |
| `access_token_value`, `access_token_issued_at`, `access_token_expires_at`, `access_token_type`, `access_token_scopes` | Access token and queryable attributes |
| `access_token_metadata` | JSON metadata/claims of the access token |
| `oidc_id_token_value`, `oidc_id_token_issued_at`, `oidc_id_token_expires_at` | ID Token and timestamps |
| `oidc_id_token_metadata` | JSON metadata/claims of the ID Token |
| `refresh_token_value`, `refresh_token_issued_at`, `refresh_token_expires_at` | Refresh token and timestamps |
| `refresh_token_metadata` | JSON metadata of the refresh token |
| `user_code_value`, `user_code_issued_at`, `user_code_expires_at`, `user_code_metadata` | User Code and metadata |
| `device_code_value`, `device_code_issued_at`, `device_code_expires_at`, `device_code_metadata` | Device Code and metadata |

The standard schema uses LOB types for large fields. `JdbcOAuth2AuthorizationService` inspects column metadata and uses `LobHandler` to read/write BLOB or CLOB according to the actual database column type. When using an organization-designed schema, verify column types and JDBC driver binding capabilities.

## 4. Default Jackson in Spring Authorization Server 1.5.x

### 4.1. Not Java ObjectOutputStream

`OAuth2Authorization` implements `Serializable`, but `JdbcOAuth2AuthorizationService` 1.5.x does not write the whole object with `ObjectOutputStream` by default. The implementation uses a JSON mapper to serialize the `attributes` and token metadata maps, then binds the JSON string into LOB columns.

This has an important consequence: a Java object may implement `Serializable` yet still fail to serialize/deserialize with Jackson if it lacks appropriate getters, constructors, creators, or serializers.

### 4.2. SecurityJackson2Modules

Spring Security provides `SecurityJackson2Modules.getModules(classLoader)` to discover Jackson modules for security types on the classpath. These modules register mixins/serializers required for Spring Security types such as `Authentication` and related structures.

### 4.3. OAuth2AuthorizationServerJackson2Module

Spring Authorization Server provides `OAuth2AuthorizationServerJackson2Module`. This module registers mixins for Authorization Server types, including:

- `OAuth2AuthorizationRequest`;
- unmodifiable maps/sets;
- `Duration`;
- `JwsAlgorithm`;
- `OAuth2TokenFormat`;
- other data types used in authorization attributes/settings.

The module also enables default typing when type information is needed to restore an object of a concrete type. When mapping JSON back into `Map<String, Object>`, type metadata lets Jackson know the actual value type rather than restoring everything as a `LinkedHashMap` or generic type.

Example of initializing `ObjectMapper` per Spring guidance:

```java
ObjectMapper objectMapper = new ObjectMapper();
ClassLoader classLoader = getClass().getClassLoader();

objectMapper.registerModules(
        SecurityJackson2Modules.getModules(classLoader)
);
objectMapper.registerModule(
        new OAuth2AuthorizationServerJackson2Module()
);
```

Do not construct a completely custom `ObjectMapper` while omitting these modules if authorization attributes contain Spring Security/Spring Authorization Server types. JSON might write cleanly yet fail when read back, especially on `Authentication`, `OAuth2AuthorizationRequest`, immutable collections, or token-specific types.

### 4.4. Type Metadata Is Part of the Storage Format

For a map whose value type is `Object`, the same key could hold a `String`, `Instant`, `Authentication`, `OAuth2AuthorizationRequest`, or custom principal. JSON needs type information to reconstruct the exact object.

Conceptual example:

```json
{
  "principal": {
    "@class": "com.example.security.ApplicationPrincipal",
    "userId": "u-1001",
    "tenantId": "tenant-a"
  }
}
```

The exact type-marker field name in JSON depends on the `ObjectMapper` and typing configuration; the snippet above only illustrates the idea. Do not rely on specific marker names to write SQL queries or manipulate data manually.

## 5. Serializing Custom Principals and Attributes

### 5.1. Prefer Lean, Stable Principals

A principal stored in authorization attributes can outlive the web request that created it. Use a DTO carrying only the fields needed by flows, such as user ID, tenant ID, and display name. Avoid stuffing entire JPA entities or request/session-bound objects into `attributes`.

```java
import java.io.Serializable;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.security.core.AuthenticatedPrincipal;

public final class ApplicationPrincipal implements AuthenticatedPrincipal, Serializable {

    private static final long serialVersionUID = 1L;

    private final String userId;
    private final String tenantId;
    private final String displayName;

    @JsonCreator
    public ApplicationPrincipal(
            @JsonProperty("userId") String userId,
            @JsonProperty("tenantId") String tenantId,
            @JsonProperty("displayName") String displayName) {
        this.userId = userId;
        this.tenantId = tenantId;
        this.displayName = displayName;
    }

    public String getUserId() {
        return userId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getDisplayName() {
        return displayName;
    }

    @Override
    public String getName() {
        return userId;
    }
}
```

`Serializable` in the example maintains compatibility with Java components that may require this contract, while JDBC round-trip capability still comes from Jackson annotations/modules and `ObjectMapper`. Write serialize/deserialize tests using the exact mapper configured for production.

### 5.2. Never Store Credentials in the Principal

Do not place raw passwords, password hashes, OTPs, recovery codes, client secrets, or sensitive credentials into a custom principal merely to reconstruct `Authentication`. The authorization flow's security context needs identity and required authorities, not the user's login secrets stored inside authorization records.

If the current principal carries excessive data, build a sanitized principal snapshot before putting it into authorization attributes. Do not expect Jackson to automatically know which fields to strip.

### 5.3. Placing a Custom Principal into an Authorization

Example of how a service can store a sanitized `Authentication` in attributes:

```java
Authentication authorizationPrincipal =
        UsernamePasswordAuthenticationToken.authenticated(
                applicationPrincipal,
                null,
                authorities
        );

OAuth2Authorization authorization = OAuth2Authorization
        .withRegisteredClient(registeredClient)
        .principalName(authorizationPrincipal.getName())
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizedScopes(authorizedScopes)
        .attribute(Principal.class.getName(), authorizationPrincipal)
        .attribute(
                OAuth2AuthorizationRequest.class.getName(),
                authorizationRequest
        )
        .build();
```

This example illustrates setting the attribute; let Spring Authorization Server create/update authorizations during standard grant flows instead of manually constructing authorizations to bypass default `AuthenticationProvider`s. When customizing providers or grants, ensure the principal is saved under the exact key expected by the reading component.

### 5.4. When Is a Custom Serializer/Deserializer Needed?

You may need a custom serializer when:

- the principal is a proprietary domain type without constructors/getters Jackson understands;
- the principal holds data recoverable only via a service lookup;
- JSON structure must evolve while still reading legacy rows;
- a custom authentication token carries proprietary attribute types;
- you want to persist only a slim snapshot instead of an entire object graph.

There are three common approaches:

1. Design a serialization-friendly DTO with `@JsonCreator` and `@JsonProperty`.
2. Register a Jackson mixin for an existing class without modifying that class's source code.
3. Register a custom `JsonSerializer`/`JsonDeserializer` in a `SimpleModule`.

If a deserializer would need to query a database or service, consider creating an explicit principal snapshot instead of injecting dependencies into serializers. Serialization should be a testable data transformation, not a hidden service locator.

## 6. Customizing ObjectMapper for JdbcOAuth2AuthorizationService

### 6.1. When Do You Need to Replace the Default ObjectMapper?

Do not replace the mapper if your principal/attribute types are already supported by Spring Jackson modules. Customize only when you have custom types or proprietary JSON formats that the default mapper cannot restore.

`JdbcOAuth2AuthorizationService` 1.5.x allows replacing both mappers:

- `setAuthorizationParametersMapper(...)` for the write path;
- `setAuthorizationRowMapper(...)` for the read path.

Both directions must use compatible `ObjectMapper` configurations. Replacing only the write mapper allows new data to be written that cannot be read back. Replacing only the read mapper may read old data while the next `save` writes a different format.

### 6.2. Configuring a Shared ObjectMapper

The following example illustrates Jackson 2 configuration for a custom principal. `SecurityJackson2Modules` and `OAuth2AuthorizationServerJackson2Module` preserve the mixins/type support Spring requires; `JavaTimeModule` helps if custom DTOs contain `Instant`, `LocalDate`, or `Duration` fields:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.jackson2.SecurityJackson2Modules;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.jackson2.OAuth2AuthorizationServerJackson2Module;

@Configuration
public class AuthorizationPersistenceConfig {

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcOperations jdbcOperations,
            RegisteredClientRepository registeredClientRepository) {

        JdbcOAuth2AuthorizationService service =
                new JdbcOAuth2AuthorizationService(
                        jdbcOperations,
                        registeredClientRepository
                );

        ObjectMapper objectMapper = new ObjectMapper();
        ClassLoader classLoader = getClass().getClassLoader();
        objectMapper.registerModules(
                SecurityJackson2Modules.getModules(classLoader)
        );
        objectMapper.registerModule(
                new OAuth2AuthorizationServerJackson2Module()
        );
        objectMapper.registerModule(new JavaTimeModule());

        JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper
                parametersMapper =
                new JdbcOAuth2AuthorizationService
                        .OAuth2AuthorizationParametersMapper();
        parametersMapper.setObjectMapper(objectMapper);

        JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper rowMapper =
                new JdbcOAuth2AuthorizationService
                        .OAuth2AuthorizationRowMapper(
                                registeredClientRepository
                        );
        rowMapper.setObjectMapper(objectMapper);

        service.setAuthorizationParametersMapper(parametersMapper);
        service.setAuthorizationRowMapper(rowMapper);

        return service;
    }
}
```

This is a complete configuration for a standalone service bean. If the application already defines an `OAuth2AuthorizationService` bean or an Authorization Server filter chain, integrate this bean into the existing configuration. Example wiring in the configurer:

```java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.authorizationService(authorizationService)
    );
```

The `oauth2_authorization` schema must exist before the service initializes. `JdbcOAuth2AuthorizationService` uses `JdbcOperations` and `RegisteredClientRepository`; the row mapper looks up `registered_client_id` to retrieve the `RegisteredClient` before constructing `OAuth2Authorization`.

### 6.3. Mixins for Custom Principals

If you cannot add Jackson annotations directly to the principal class, declare a mixin:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

abstract class ApplicationPrincipalMixin {

    @JsonCreator
    ApplicationPrincipalMixin(
            @JsonProperty("userId") String userId,
            @JsonProperty("tenantId") String tenantId,
            @JsonProperty("displayName") String displayName) {
    }
}
```

Register the mixin before attaching `ObjectMapper` to the two JDBC mappers:

```java
objectMapper.addMixIn(
        ApplicationPrincipal.class,
        ApplicationPrincipalMixin.class
);
```

If a class needs dedicated serializers/deserializers, register a `SimpleModule`:

```java
SimpleModule applicationModule = new SimpleModule("application-authorization-types");
applicationModule.addSerializer(
        ApplicationPrincipal.class,
        new ApplicationPrincipalSerializer()
);
applicationModule.addDeserializer(
        ApplicationPrincipal.class,
        new ApplicationPrincipalDeserializer()
);
objectMapper.registerModule(applicationModule);
```

`ApplicationPrincipalSerializer` and `ApplicationPrincipalDeserializer` here are application-defined classes. When using custom serializers, ensure the JSON retains enough data to restore the exact logical principal and remains compatible with previously stored authorization records.

### 6.4. Do Not Replace Mappers Just to Rename JSON Fields

`OAuth2AuthorizationParametersMapper` must return the exact list of `SqlParameterValue`s expected by the schema and SQL statements used by `JdbcOAuth2AuthorizationService`. If you only want to customize how a custom type is serialized, customize the `ObjectMapper`/modules first. Only replace the entire mapper when you genuinely need to change column mappings, in which case you assume responsibility for parameter order, SQL types, nullability, and read/write symmetry.

## 7. Token Metadata and Claims

### 7.1. Metadata Is Stored Per Token

`OAuth2Authorization.Token` holds dedicated metadata for each token. These metadata maps are written to their corresponding columns:

| Token | Metadata column | Common contents |
| --- | --- | --- |
| Authorization Code | `authorization_code_metadata` | State and code-related metadata |
| Access Token | `access_token_metadata` | Claims, invalidated status, and extra metadata |
| OIDC ID Token | `oidc_id_token_metadata` | ID Token claims and metadata |
| Refresh Token | `refresh_token_metadata` | Refresh-token-related metadata |
| User Code | `user_code_metadata` | Device authorization metadata |
| Device Code | `device_code_metadata` | Device authorization metadata |

Some metadata keys are managed internally by Spring. Never define keys colliding with framework-reserved keys or overwrite claims metadata with incompatible objects.

### 7.2. JWT and ID Token Claims

When a token is minted by `JwtGenerator`, claims can be kept in `OAuth2Authorization.Token` metadata. For OIDC, ID Token claims are stored in `oidc_id_token_metadata`; when the row mapper reconstructs `OidcIdToken`, it reads claims from metadata using `OAuth2Authorization.Token.CLAIMS_METADATA_NAME`.

This means:

- `oidc_id_token_value` holds the compact ID Token string;
- `oidc_id_token_metadata` holds the metadata/claims needed by the model;
- timestamp columns hold `issued_at` and `expires_at`.

Similarly, Access Token has its own value, type, scopes, issued/expiry timestamps, and metadata. Do not infer that the metadata map is the source for verifying token signatures; signatures and token values are still processed according to the protocol's token format and validators.

### 7.3. Custom Token Metadata

If the application adds custom metadata to a token:

1. Choose namespaced keys to avoid colliding with framework keys.
2. Persist only data needed for authorization/introspection/revocation processing.
3. Use data types Jackson can deserialize reliably.
4. Never store secrets, private keys, or unnecessary credentials.
5. Ensure all cluster instances run the same modules and DTO versions.

Example of adding metadata values to a token builder only makes sense inside an appropriate extension point that creates/updates authorizations:

```java
authorizationBuilder.token(accessToken, metadata -> {
    metadata.put("com.example.policy.version", "2026-01");
    metadata.put("com.example.risk.level", "standard");
});
```

This illustrates setting metadata in the builder; do not mutate authorization records outside the grant lifecycle. If metadata drives security decisions, verify its integrity, origin, and update timing.

## 8. Security When Deserializing Authorization Data

### 8.1. The Database Influences Object Reconstruction

JSON in `attributes` can carry type metadata. When Jackson restores the map, it may instantiate specific classes. Consequently, anyone able to tamper with `attributes` or token metadata columns can influence deserialization.

Principles:

- Only the Authorization Server service account may write to the authorization table.
- Restrict direct database read/write permissions and audit out-of-band modifications.
- Never accept authorization JSON from clients and deserialize it using the internal `ObjectMapper`.
- Never enable unrestricted polymorphic typing on endpoints accepting untrusted input.
- If adding custom types, restrict allowed classes and keep the allowlist small.
- Test serializers/deserializers before deploying to production.

### 8.2. Default Typing and Allowlists

Spring Security/Spring Authorization Server uses type metadata because polymorphic map values must be restored to their exact classes. Do not arbitrarily disable typing without checking required security types. At the same time, do not widen typing to every class in the application without cause.

For custom principals, favor clean DTOs and scalar types. If your Jackson/security module version supports a custom polymorphic type validator, configure an allowlist for your application's packages/classes rather than permitting arbitrary classes. Above all, avoid deserializing JSON submitted by users, clients, or untrusted external sources.

### 8.3. Minimizing Sensitive Data in Attributes

Never put into authorization attributes:

- raw passwords or password hashes;
- copies of refresh tokens or other credentials stuffed into attributes outside the token model;
- private keys, signing keys, or client secrets;
- HTTP request/response objects;
- servlet sessions, connections, service beans, or JPA persistence contexts;
- object graphs with unnecessary lazy/cyclic references.

Principal snapshots should contain only the subject, tenant, required authorities, and stable properties the flow actually uses. For details retrievable from a user service, consider storing an ID instead of the entire entity.

### 8.4. Protecting Token Values in the Database

The authorization schema stores token values in dedicated columns such as authorization code, access token, ID Token, refresh token, user code, and device code. These values are usable credentials if leaked; do not assume the JDBC service hashes or encrypts every token before writing.

- Enable encryption at rest for databases, volumes, snapshots, and backups per organizational operating standards.
- Use TLS for application-to-database connections and restrict read access on the authorization table.
- Never log token values, JSON attributes, or metadata that may contain sensitive claims.
- Never copy the authorization table to analytics/dev environments without stripping or protecting credentials.
- Enforce retention/cleanup for expired or revoked authorizations aligned with auditing and recovery requirements.

## 9. Version Compatibility and Data Structure Changes

### 9.1. Class Names Can Become Part of Stored Data

When JSON contains type metadata, a custom principal's class/package name can appear inside stored rows. If you move packages, rename classes, or remove a module from the classpath, older authorization records may fail to deserialize.

Before refactoring a custom principal:

1. Identify existing authorizations containing that class.
2. Keep the legacy class or provide a compatibility mixin/deserializer during the transition window.
3. Convert legacy data to the new format via tested migrations.
4. Remove the legacy class only when no rows remain that require reading the prior format.

### 9.2. Rolling Deployments in a Cluster

When multiple Authorization Server instances read/write the same database, all instances must understand formats written by other instances. Never deploy a new node writing a new JSON type while older nodes do not recognize that class.

Safe rollout sequence:

- deploy a version capable of **reading both old and new formats** first;
- only then switch writers to the new format;
- backfill live rows if needed;
- finally remove the legacy compatibility reader.

If dual-read cannot be supported, use a maintenance window or ensure old authorizations expire/get revoked before changing formats.

### 9.3. Schema Migrations and JSON Migrations Are Distinct Tasks

Changing an SQL column type (such as BLOB to CLOB) is a schema migration. Changing JSON structures or class names inside `attributes` is a data-format migration. A release may require both, and they do not synchronize automatically.

Do not edit metadata columns directly with SQL unless you fully understand type information, escaping, and the active mappers. For JSON containing polymorphic types, raw find/replace on class names can corrupt JSON or alter payload strings unintentionally.

### 9.4. Jackson 2 vs. Jackson 3

Examples in this lesson use Spring Authorization Server 1.5.x Jackson 2 APIs:

- `SecurityJackson2Modules`;
- `OAuth2AuthorizationServerJackson2Module`;
- `OAuth2AuthorizationParametersMapper`;
- `OAuth2AuthorizationRowMapper`.

In the Spring Security 7 / newer Authorization Server major line moving to Jackson 3, corresponding modules and mappers have new names/APIs, such as `SecurityJacksonModules`, `OAuth2AuthorizationServerJacksonModule`, and `JsonMapper...` mappers. When upgrading major versions, read the exact version's API docs and run migration/round-trip tests before sharing a database with older instances.

## 10. Testing Serialization Round-Trips

### 10.1. What Must Be Proven

The most important test does not merely check that JSON was written—it proves the reconstructed object retains the exact same logical state:

- `principalName` is unchanged;
- custom principal preserves its exact class and fields;
- authorization request attributes are restored;
- authorized scopes remain intact;
- token values, types, issued-at, and expires-at match;
- token metadata/claims are preserved;
- invalidated metadata is not lost;
- `findByToken(...)` still locates the authorization.

### 10.2. Test Matrix

| ID | Scenario | Expected result |
| --- | --- | --- |
| JDBC-SER-01 | Save and read authorization with scalar fields only | ID, client ID, principal name, and grant type match |
| JDBC-SER-02 | Attributes contain standard Spring Security `Authentication` | Deserializes to the expected security type |
| JDBC-SER-03 | Attributes contain `OAuth2AuthorizationRequest` | Request is restored with all required parameters |
| JDBC-SER-04 | Attributes contain custom principal DTO | Restores exact class and fields |
| JDBC-SER-05 | Custom principal lacks suitable creator/getters | Test catches deserialization error |
| JDBC-SER-06 | Token metadata has string/boolean/number/map | JSON round-trip preserves expected values and types |
| JDBC-SER-07 | Access Token has claims metadata | Claims are restored |
| JDBC-SER-08 | OIDC ID Token has claims metadata | `OidcIdToken` is reconstructed with claims |
| JDBC-SER-09 | Token has invalidated metadata | Invalidated state is preserved |
| JDBC-SER-10 | Authorization has refresh token | Refresh token value and timestamps match |
| JDBC-SER-11 | Authorization has user/device code | Corresponding tokens are restored |
| JDBC-SER-12 | Call `findByToken` with access token | Returns matching authorization |
| JDBC-SER-13 | Call `findByToken` with specific token type | Searches only the requested token type |
| JDBC-SER-14 | `registered_client_id` missing from repository | Row mapper fails restoration rather than building an authorization without a client |
| JDBC-SER-15 | Custom `ObjectMapper` applied only to write side | Read-back test detects incompatible format |
| JDBC-SER-16 | Custom `ObjectMapper` applied only to read side | Write/read test detects mismatched mappers |
| JDBC-SER-17 | Mapper includes `SecurityJackson2Modules` and SAS module | Spring security attributes restore successfully |
| JDBC-SER-18 | Omit `OAuth2AuthorizationServerJackson2Module` | Test catches failure on authorization request/settings needing mixins |
| JDBC-SER-19 | Rename custom principal class/package | Compatibility test reads legacy rows cleanly |
| JDBC-SER-20 | Two nodes run different mappers/versions | Cluster compatibility test catches cross-read failure |
| JDBC-SER-21 | Attributes contain non-allowlisted object | Deserialization is rejected per policy |
| JDBC-SER-22 | Attributes contain passwords/sensitive credentials | Security test confirms data is not persisted |
| JDBC-SER-23 | BLOB/CLOB on target database | LOB binding and reading work |
| JDBC-SER-24 | Authorization has large attributes | No data truncation; payload size and latency measured |
| JDBC-SER-25 | Update existing authorization | New tokens/metadata updated properly |
| JDBC-SER-26 | Remove authorization | Row deleted and `findById`/`findByToken` no longer return it |

### 10.3. Service-Level Round-Trip Test Example

Test skeleton against a Spring JDBC test database:

```java
@SpringBootTest
class JdbcAuthorizationSerializationTests {

    @Autowired
    OAuth2AuthorizationService authorizationService;

    @Test
    void shouldRestoreCustomPrincipalAndTokenMetadata() {
        OAuth2Authorization authorization = createAuthorizationWithCustomPrincipal();

        authorizationService.save(authorization);

        OAuth2Authorization restored =
                authorizationService.findById(authorization.getId());

        assertThat(restored).isNotNull();
        assertThat(restored.getPrincipalName())
                .isEqualTo(authorization.getPrincipalName());

        Object principal = restored.getAttribute(Principal.class.getName());
        assertThat(principal).isInstanceOf(Authentication.class);

        Authentication authentication = (Authentication) principal;
        assertThat(authentication.getPrincipal())
                .isInstanceOf(ApplicationPrincipal.class);

        ApplicationPrincipal restoredPrincipal =
                (ApplicationPrincipal) authentication.getPrincipal();
        assertThat(restoredPrincipal.getUserId()).isEqualTo("u-1001");
        assertThat(restoredPrincipal.getTenantId()).isEqualTo("tenant-a");

        OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
                restored.getToken(OAuth2AccessToken.class);
        assertThat(accessToken).isNotNull();
        assertThat(accessToken.getMetadata())
                .containsEntry("com.example.policy.version", "2026-01");
    }
}
```

`createAuthorizationWithCustomPrincipal()` is a test-defined fixture that must construct an authorization matching the test's grant and token model. When using Testcontainers, run tests on the same database engine/version as production to catch BLOB/CLOB and SQL dialect differences.

### 10.4. Testing Mappers in Isolation

When errors occur, isolate mappers before running full OAuth flows:

1. Create an authorization fixture containing the attributes and token metadata to test.
2. Invoke `OAuth2AuthorizationParametersMapper.apply(...)` to produce SQL parameters.
3. Persist and read the row using `OAuth2AuthorizationRowMapper`.
4. Compare classes/values of attributes and metadata.
5. Once mapper round-trips succeed, run integration tests for authorization code, refresh token, introspection, and revocation.

Do not rely solely on JSON string snapshot tests. What matters is that the restored object remains usable by Spring Authorization Server throughout protocol flows.

## 11. Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `InvalidDefinitionException` on save | Custom principal lacks a Jackson-serializable structure | Add creator/getters, mixin, or serializer |
| `InvalidTypeIdException` on load | Missing type metadata/module or class removed from classpath | Register proper modules and keep compatibility class |
| Principal loads as `LinkedHashMap` | Type metadata lost or `ObjectMapper` lacks compatible typing | Inspect mappers on both directions and legacy JSON |
| Cannot deserialize `OAuth2AuthorizationRequest` | Missing `OAuth2AuthorizationServerJackson2Module` or security modules | Configure mapper per Spring guidance |
| Write succeeds but read fails | Write and read mappers have different configurations | Share the exact same `ObjectMapper`/modules |
| `RegisteredClient` not found when mapping row | `registered_client_id` points to a deleted client or wrong repository | Restore client registration or enforce proper retention order |
| ID Token claims lost | Mapper fails to save/read claims metadata under expected key | Check `CLAIMS_METADATA_NAME` and `oidc_id_token_metadata` |
| `DataIntegrityViolationException` | Column too small, wrong LOB type, or payload exceeds limit | Check schema, column types, and payload sizes |
| Restoration fails after rolling deploy | New node writes a type unknown to old nodes | Deploy compatibility reader before new writer |
| Errors appear only on production database | JDBC driver handles BLOB/CLOB differently from test DB | Test against the exact DB engine and `LobHandler` |
| Authorization queries slow under high load | Default JDBC service not optimized for very high throughput | Measure queries/indexes/LOBs; consider custom `OAuth2AuthorizationService` |

### 11.1. Distinguishing Serialization Errors from Lookup Errors

- **Serialization error:** Jackson fails to write attributes/metadata to JSON.
- **Deserialization error:** Jackson reads JSON but cannot reconstruct object types.
- **Client lookup error:** `RowMapper` reads `registered_client_id`, but `RegisteredClientRepository` cannot find the matching client.
- **Schema/LOB error:** JDBC fails to bind or read the column type properly.

Categorizing properly ensures fixes target the right layer. Do not work around deserialization errors by deleting `attributes` from the database if authorization flows still need that principal or request context.

### 11.2. Performance

Spring documentation describes `JdbcOAuth2AuthorizationService` as a simple JDBC implementation and notes it may not satisfy high-throughput environments. Measure in practice:

- call frequency of `findById`/`findByToken`;
- JSON sizes in `attributes` and token metadata;
- Jackson serialize/deserialize cost;
- LOB read/write duration;
- indexes on token values, authorization ID, and filter columns;
- locks/transactions when updating the same authorization.

If deep optimization is required, implement a custom `OAuth2AuthorizationService` or extend mappers/queries for your workload. Preserve the semantics of save/update/remove/find and token state; never trade revocation/introspection correctness for fewer reads.

## 12. Production Checklist and Reference Documentation

### 12.1. Pre-Production Checklist

- [ ] Exact Spring Authorization Server version and Jackson major version identified.
- [ ] `JdbcOAuth2AuthorizationService` uses a compatible `oauth2-authorization-schema.sql` schema.
- [ ] `RegisteredClientRepository` is shared and holds all clients referenced by authorization rows.
- [ ] `SecurityJackson2Modules` and `OAuth2AuthorizationServerJackson2Module` are registered for Jackson 2 on 1.5.x.
- [ ] The exact same `ObjectMapper`/modules are used for both parameters mapper and row mapper.
- [ ] Custom principals have stable serializers/deserializers and round-trip tests.
- [ ] Attributes contain only necessary data, with no passwords/secrets/private keys.
- [ ] Token metadata and claims are verified after restoration.
- [ ] Authorization JSON is never deserialized from untrusted external sources.
- [ ] Type metadata/custom types are restricted and managed across versions.
- [ ] Compatibility plan exists for rolling deployments and class/package renames.
- [ ] Database LOB types are tested with the exact DB engine/JDBC driver.
- [ ] Round-trip tests cover principals, authorization requests, access/refresh/ID tokens, and invalidated metadata.
- [ ] Metrics track payload sizes, query latency, and serialization latency.
- [ ] Databases, volumes, and backups protect token values with encryption at rest; read permissions on the authorization table are restricted.
- [ ] Logs and telemetry contain no token values, principal attributes, or sensitive token metadata.
- [ ] Retention/cleanup policy exists for expired or revoked authorization rows.

### Memory Map

```text
OAuth2Authorization
  |
  +-- id / registeredClientId / principalName / grantType / scopes
  |
  +-- attributes
  |     +-- Authentication / Principal
  |     +-- OAuth2AuthorizationRequest
  |     +-- custom flow attributes
  |
  +-- tokens
        +-- token value + timestamps
        +-- token metadata / claims
                 |
                 v
JdbcOAuth2AuthorizationService
  |
  +-- ParametersMapper
  |      +-- scalar columns
  |      +-- attributes Map -> JSON
  |      +-- token metadata Map -> JSON
  |
  +-- RowMapper
         +-- scalar columns -> builder
         +-- JSON -> typed Map
         +-- registered_client_id -> RegisteredClientRepository
         +-- tokens + metadata -> token objects
                 |
                 v
        OAuth2Authorization restored

Jackson 2 in SAS 1.5.x:
  SecurityJackson2Modules
  + OAuth2AuthorizationServerJackson2Module
  + same ObjectMapper for write and read
```

**Key Takeaway:** `principalName` is a standalone identifier string, whereas `Principal`/`Authentication` and `OAuth2AuthorizationRequest` are typically stored inside `attributes`. Token values, timestamps, and token metadata are stored per token type. In Spring Authorization Server 1.5.x, `JdbcOAuth2AuthorizationService` serializes these maps with Jackson 2; Spring Security/Spring Authorization Server Jackson modules and the exact same `ObjectMapper` are required for both writes and reads. Keep principals lean, exclude sensitive credentials, govern type metadata, and test round-trips before altering classes or storage formats.

## Official Reference Documentation

- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization`, attributes, token metadata, and `OAuth2AuthorizationService`.
- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): constructors, schema requirements, parameters mapper, and row mapper.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationParametersMapper API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper.html): `ObjectMapper` and SQL parameter mapping.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationRowMapper API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper.html): reconstructing `OAuth2Authorization` from `ResultSet`.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerJackson2Module API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/jackson2/OAuth2AuthorizationServerJackson2Module.html): mixins and type information required for JSON serialization.
- [Spring Security — SecurityJackson2Modules API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/jackson2/SecurityJackson2Modules.html): registering Spring Security's Jackson modules.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring `OAuth2AuthorizationService` in the Authorization Server.
