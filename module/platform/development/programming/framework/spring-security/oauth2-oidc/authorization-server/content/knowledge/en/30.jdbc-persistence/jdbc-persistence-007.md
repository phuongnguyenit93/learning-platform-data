# Configuring Required Jackson Modules and Controlling Deserialization

## 1. Why Does JDBC Persistence Require Proper Jackson Configuration?

Spring Authorization Server persists several complexly structured objects. `JdbcRegisteredClientRepository` persists `RegisteredClient` configurations; `JdbcOAuth2AuthorizationService` persists `OAuth2Authorization` state. The JDBC implementations convert certain properties, settings, and token metadata into JSON to write into database columns, then read that JSON back into Java objects.

A plain `ObjectMapper` may not know how to handle the data types and collections used by Spring Security/Spring Authorization Server. For example, authorization attributes may contain `Authentication`, authorization requests, or unmodifiable collections; client settings may contain `Duration`, JWS algorithms, and token formats. If a mapper lacks the corresponding modules/mixins, the application can encounter serialization or deserialization errors or fail to restore exact data types after a restart.

Spring provides two module groups to distinguish:

- **SecurityJackson2Modules**: discovers Jackson modules provided by Spring Security on the classpath.
- **OAuth2AuthorizationServerJackson2Module**: registers mixins required for Spring Authorization Server data types.

This lesson belongs to the **JDBC Persistence** chapter and focuses on configuring the required Jackson modules, wiring mappers into both the read and write paths of JDBC repositories, and controlling polymorphic deserialization risks.

### Learning Objectives

After this lesson, you will be able to:

1. Identify which parts of `RegisteredClient` and `OAuth2Authorization` are stored as JSON.
2. Explain the roles of `SecurityJackson2Modules` and `OAuth2AuthorizationServerJackson2Module`.
3. Create a dedicated `ObjectMapper` for persistence.
4. Configure mappers for `RegisteredClientRowMapper` and `RegisteredClientParametersMapper`.
5. Configure mappers for `OAuth2AuthorizationRowMapper` and `OAuth2AuthorizationParametersMapper`.
6. Understand why serialization and deserialization must be configured symmetrically.
7. Control polymorphic type metadata and trusted data boundaries.
8. Add modules/mixins for custom attributes intentionally.
9. Test round-trips and data compatibility across upgrades.
10. Recognize differences between Jackson 2 and Jackson 3 in newer Spring versions.

## 2. Where Does Jackson Participate in JDBC Persistence?

The persistence process is bidirectional:

~~~mermaid
flowchart LR
    A[RegisteredClient / OAuth2Authorization] --> B[ParametersMapper]
    B --> C[ObjectMapper]
    C --> D[JSON columns]
    D --> E[RowMapper]
    E --> F[ObjectMapper]
    F --> G[RegisteredClient / OAuth2Authorization]
~~~

`ParametersMapper` converts Java objects into SQL parameters. When persisting maps/settings/metadata, the mapper uses Jackson to generate JSON. `RowMapper` reads the JSON columns and restores the maps or settings needed to construct the domain object.

There are two mapper pairs:

| JDBC component | Write path | Read path |
|---|---|---|
| `JdbcRegisteredClientRepository` | `RegisteredClientParametersMapper` | `RegisteredClientRowMapper` |
| `JdbcOAuth2AuthorizationService` | `OAuth2AuthorizationParametersMapper` | `OAuth2AuthorizationRowMapper` |

Each pair must understand the exact same JSON format. If the write and read paths use different configurations, a record may write cleanly yet fail to read back.

### 2.1. Which RegisteredClient Data Is Stored as JSON?

`RegisteredClient` contains simple fields such as client ID, client secret, client name, redirect URIs, and scopes. Two settings structures hold richer data:

- `clientSettings`: settings such as PKCE requirements, consent, and extended settings.
- `tokenSettings`: TTLs, token formats, refresh token reuse, and other token settings.

The JDBC repository stores settings as JSON. Internal types are not merely strings; some values are `Duration`s, Spring Security enums/types, or specialized settings types.

### 2.2. Which OAuth2Authorization Data Is Stored as JSON?

`OAuth2Authorization` stores grant state, principal, authorized scopes, attributes, and per-token metadata. In the standard JDBC schema, token values and issued/expiry timestamps sit in dedicated columns; maps such as authorization attributes and token metadata are serialized as JSON.

Examples of data that may need persistence:

- Authorization attributes, which may include an authentication or authorization request.
- Authorization code metadata.
- Access token metadata.
- Refresh token metadata.
- Claims and metadata related to the ID Token.
- User code or device code metadata if the grant uses them.

Not all of `OAuth2Authorization` is turned into a single JSON blob. The JDBC implementation spreads data across multiple columns and uses JSON for maps/metadata.

## 3. Two Jackson Module Groups to Register

### 3.1. SecurityJackson2Modules

`SecurityJackson2Modules.getModules(ClassLoader)` discovers Jackson modules supplied by whichever Spring Security modules are present on the classpath. Examples may include modules for Spring Security Core, Web, Servlet, OAuth2 Client, CAS, or SAML depending on dependencies.

These modules supply mixins/serializers required for Spring Security types. For instance, `CoreJackson2Module` registers mixins for types like `SimpleGrantedAuthority`, `User`, `UsernamePasswordAuthenticationToken`, and unmodifiable collections.

You do not need to register individual Spring Security modules manually when using this utility.

### 3.2. OAuth2AuthorizationServerJackson2Module

This is Spring Authorization Server's dedicated module. In the Jackson 2 line, the module registers mixins for types such as:

- `UnmodifiableMap` and `HashSet`.
- `OAuth2AuthorizationRequest`.
- `OAuth2TokenExchangeCompositeAuthenticationToken`.
- `Duration`.
- `JwsAlgorithm`.
- `OAuth2TokenFormat`.
- `String[]` within required structures.

Mixins help Jackson handle types that default bean introspection cannot reconstruct properly. This module also enables default typing if the mapper lacks a type information mechanism, because certain structures require type info to serialize/deserialize.

### 3.3. Why Are Both Needed?

`OAuth2AuthorizationServerJackson2Module` handles Authorization Server–specific types. `SecurityJackson2Modules` handles foundational Spring Security types appearing inside attributes or metadata. Registering only one group can leave types from the other group unsupported.

## 4. Creating a Dedicated ObjectMapper for Persistence

The example below uses Spring Authorization Server 1.5.x and Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`):

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.security.jackson2.SecurityJackson2Modules;
import org.springframework.security.oauth2.server.authorization.jackson2
    .OAuth2AuthorizationServerJackson2Module;

ObjectMapper authorizationPersistenceObjectMapper() {
    ObjectMapper objectMapper = new ObjectMapper();

    ClassLoader classLoader =
        JdbcOAuth2AuthorizationService.class.getClassLoader();

    List<Module> securityModules =
        SecurityJackson2Modules.getModules(classLoader);

    objectMapper.registerModules(securityModules);
    objectMapper.registerModule(
        new OAuth2AuthorizationServerJackson2Module());

    return objectMapper;
}
~~~

This ordering follows the configuration pattern used in Spring Authorization Server: register Spring Security modules first, then register the Authorization Server module.

### 4.1. Register Once Before Use

Finish configuring the mapper before repositories process their first request. An `ObjectMapper` can be used concurrently once configured, but do not keep modifying modules, mixins, or features while multiple threads are serializing/deserializing.

Place the mapper in an application-scoped bean and inject it into the JDBC mappers. Do not instantiate a new mapper for every database read/write.

### 4.2. Use a Qualifier Instead of Replacing the Application-Wide ObjectMapper

Name the bean explicitly for its purpose:

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationPersistenceJacksonConfiguration {

    @Bean
    @Qualifier("authorizationPersistenceObjectMapper")
    ObjectMapper authorizationPersistenceObjectMapper() {
        ObjectMapper objectMapper = new ObjectMapper();

        ClassLoader classLoader =
            JdbcOAuth2AuthorizationService.class.getClassLoader();

        objectMapper.registerModules(
            SecurityJackson2Modules.getModules(classLoader));
        objectMapper.registerModule(
            new OAuth2AuthorizationServerJackson2Module());

        return objectMapper;
    }
}
~~~

This bean is meant for JSON stored in authorization tables. Do not mark it `@Primary` or replace the mapper Spring MVC uses to parse JSON requests from browsers/APIs.

Keeping the persistence mapper separate limits where polymorphic deserialization applies and prevents accidentally applying this configuration to untrusted JSON from HTTP.

## 5. Configuring JdbcRegisteredClientRepository in Both Directions

`JdbcRegisteredClientRepository` allows replacing `RegisteredClientRowMapper` and `RegisteredClientParametersMapper`. Pass the same `ObjectMapper` to both.

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcOperations jdbcOperations,
        @Qualifier("authorizationPersistenceObjectMapper")
        ObjectMapper objectMapper) {

    JdbcRegisteredClientRepository repository =
        new JdbcRegisteredClientRepository(jdbcOperations);

    JdbcRegisteredClientRepository.RegisteredClientRowMapper rowMapper =
        new JdbcRegisteredClientRepository.RegisteredClientRowMapper();
    rowMapper.setObjectMapper(objectMapper);

    JdbcRegisteredClientRepository.RegisteredClientParametersMapper
        parametersMapper =
            new JdbcRegisteredClientRepository
                .RegisteredClientParametersMapper();
    parametersMapper.setObjectMapper(objectMapper);

    repository.setRegisteredClientRowMapper(rowMapper);
    repository.setRegisteredClientParametersMapper(parametersMapper);

    return repository;
}
~~~

### 5.1. What Is RowMapper Responsible For?

`RegisteredClientRowMapper` reads settings columns from `ResultSet` and reconstructs `RegisteredClient`. When reading JSON settings, it uses the `ObjectMapper` supplied via `setObjectMapper`.

If settings contain a type needing a mixin while the mapper lacks the corresponding module, errors typically surface during Authorization Server startup or when a client is queried.

### 5.2. What Is ParametersMapper Responsible For?

`RegisteredClientParametersMapper` converts `RegisteredClient` into a list of `SqlParameterValue`s to write to the database. Settings are serialized to JSON using this mapper's `ObjectMapper`.

If you configure only `RowMapper` without `ParametersMapper`, the two directions may use different formats. With custom modules or custom metadata, configure both.

## 6. Configuring JdbcOAuth2AuthorizationService in Both Directions

`JdbcOAuth2AuthorizationService` also has its own mapper pair. The row mapper additionally requires `RegisteredClientRepository` to reconstruct an authorization from its saved registration.

~~~java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository,
        @Qualifier("authorizationPersistenceObjectMapper")
        ObjectMapper objectMapper) {

    JdbcOAuth2AuthorizationService service =
        new JdbcOAuth2AuthorizationService(
            jdbcOperations, registeredClientRepository);

    JdbcOAuth2AuthorizationService.OAuth2AuthorizationRowMapper rowMapper =
        new JdbcOAuth2AuthorizationService
            .OAuth2AuthorizationRowMapper(registeredClientRepository);
    rowMapper.setObjectMapper(objectMapper);

    JdbcOAuth2AuthorizationService.OAuth2AuthorizationParametersMapper
        parametersMapper =
            new JdbcOAuth2AuthorizationService
                .OAuth2AuthorizationParametersMapper();
    parametersMapper.setObjectMapper(objectMapper);

    service.setAuthorizationRowMapper(rowMapper);
    service.setAuthorizationParametersMapper(parametersMapper);

    return service;
}
~~~

### 6.1. RowMapper Reconstructs the Authorization

When reading an authorization, the row mapper:

1. Reads the registered client ID.
2. Looks up the matching `RegisteredClient` via `RegisteredClientRepository`.
3. Reads principal, grant type, and authorized scopes.
4. Reads token columns, issued-at, expires-at, and metadata.
5. Uses `ObjectMapper` to parse the JSON maps.
6. Reconstructs `OAuth2Authorization` along with token metadata.

Therefore, `RegisteredClientRepository` must be operational before the authorization service is used. If the referenced registration no longer exists, the row mapper cannot build a complete authorization.

### 6.2. ParametersMapper Writes the Authorization

`OAuth2AuthorizationParametersMapper` converts an authorization into SQL parameters. The `attributes` and token metadata maps are serialized with `ObjectMapper`.

If the application stores custom attributes, custom authentications, or extended objects inside authorizations, both the write mapper and read mapper must understand those exact types.

## 7. Complete Configuration: Dependency Order Between Beans

The two repositories have a dependency relationship:

~~~mermaid
flowchart TD
    M[authorizationPersistenceObjectMapper]
    R[JdbcRegisteredClientRepository]
    A[JdbcOAuth2AuthorizationService]
    M --> R
    M --> A
    R --> A
~~~

`RegisteredClientRepository` must be created first so `JdbcOAuth2AuthorizationService` can use it when reading authorizations. The `ObjectMapper` is shared across the write and read mappers of both repositories.

Do not create two separate persistence mappers with differing configurations if they read/write compatible JSON types. One shared mapper prevents drift in modules, mixins, and features.

### 7.1. Ensuring the Application Uses the Right Beans

In the Authorization Server configuration, core service beans must reference the configured JDBC repositories. If another in-memory bean is still injected due to duplicate configuration or a wrong qualifier, the application may start while data fails to read/write as expected.

Inspect dependency injection in the `ApplicationContext` and verify that a written record can be read back from the same repository.

## 8. Replace Mappers Only with Good Reason

Spring Authorization Server's JDBC implementations already supply default row mappers and parameter mappers. In their corresponding versions, they already include the Jackson configuration needed for supported framework types.

If you use only standard types and need no custom serialization, prefer the default mappers for your exact dependency version. Create custom mappers when you need to:

- Add custom attribute types.
- Register modules/mixins for application types.
- Standardize a shared `ObjectMapper` across multiple persistence services.
- Enforce deserialization policies per system requirements.
- Migrate JSON formats or maintain compatibility with legacy data.

When replacing default mappers, retain all Spring Security and Authorization Server modules required by stored data.

## 9. Understanding Polymorphic Type Metadata

A JSON map can hold multiple Java types. For instance, authorization attributes might hold a string, a boolean, a map, a set, or an `Authentication` object. When serialized to JSON, basic JSON structure alone is not always enough to restore the exact Java type.

Polymorphic type metadata records extra type information so Jackson knows which concrete object to reconstruct. Spring Security and Authorization Server use this mechanism for certain objects/collections.

Illustrative conceptual example (not fixed JSON that the application should craft manually):

~~~json
{
  "@class": "some.trusted.package.SomeSupportedType",
  "value": "example"
}
~~~

Actual property names and structures depend on the mapper/modules. Never rely on this example to hand-write JSON into database columns.

### 9.1. Why Does Default Typing Appear?

`SecurityJackson2Modules` and `OAuth2AuthorizationServerJackson2Module` support type information needed by framework types. In Jackson 2, registering security modules may enable default typing for non-final types; the Authorization Server module also enables default typing if the mapper does not already have it enabled.

This enables round-tripping polymorphic objects, while simultaneously expanding the deserialization surface. Therefore, this mapper should only read persistence data within a trust boundary controlled by the application.

### 9.2. Do Not Enable Global Default Typing Indiscriminately

Never enable broad default typing on a mapper used for general request/response JSON. Avoid configurations allowing arbitrary subtypes, such as permissive validators or accepting arbitrary class names controlled by input.

Use a dedicated persistence mapper and register only necessary modules. Never deserialize JSON payloads submitted by browsers, public APIs, or untrusted tenants using this mapper.

## 10. Defining the Trust Boundary of JSON in the Database

Data in the database is often treated by the application as internal, yet the database does not automatically remain trustworthy in all situations. JSON could be modified by:

- A database account with overly broad write privileges.
- A misdirected operational script or migration.
- An admin tool directly editing metadata columns.
- An SQL injection vulnerability.
- Another service writing to the same schema without honoring the contract.

If an attacker can control type metadata and the application deserializes with default typing, the impact can be far worse than an ordinary JSON parse error.

### 10.1. Restrict Database Permissions

- Only the required service account may write to authorization/client tables.
- Separate read and write permissions where architecture allows.
- Never grant DDL or schema admin privileges to runtime accounts.
- Never allow unrelated applications to write into these JSON columns.
- Monitor unusual changes in registration and authorization tables.
- Protect backups, snapshots, and staging environments holding production data.

### 10.2. Do Not Treat Tokens as Protection for Database JSON

OAuth tokens protect protocol endpoints. They do not replace database access controls. A service might be validly authenticated via OAuth and still must never have arbitrary write access to the Authorization Server's JSON persistence tables.

## 11. Custom Attributes: Prefer Simple Types First

`OAuth2Authorization.Builder` allows storing custom attributes. While convenient, avoid putting large object graphs or arbitrary framework types into attributes.

Prefer stable, easily compatible types:

- `String`.
- `Boolean` and numeric types.
- `List`/`Set` of simple values.
- `Map<String, Object>` with controlled structure.
- Small DTOs with an explicit schema/version if truly necessary.

Example:

~~~java
OAuth2Authorization authorization =
    OAuth2Authorization.withRegisteredClient(registeredClient)
        .principalName("user-42")
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .attribute("tenant_id", "tenant-17")
        .attribute("login_channel", "web")
        .build();
~~~

These values are easy to understand and far less coupled to class names than complex custom objects.

### 11.1. Avoid Storing Unnecessary Objects

Never store full `HttpServletRequest`, `EntityManager`, JDBC `Connection`, service beans, application contexts, or objects with cyclic references inside authorization attributes. Those objects are not persistence data and may not serialize.

Never store raw passwords, unencoded client secrets, private keys, or unnecessary authentication credentials inside JSON attributes.

## 12. When You Need to Persist Custom Java Types

If the application genuinely needs a custom type, define the contract upfront:

1. Must this data type truly survive restarts?
2. Can it be simplified into primitives/maps/stable DTOs?
3. Does it have clear serializers/deserializers?
4. Might the class move packages or be renamed in the future?
5. Is there a migration path for legacy JSON?
6. Is the type within the permitted deserialization scope?

You can use Jackson mixins or a custom module to define how that type serializes/deserializes. Register only the required types; do not open up entire application packages without reason.

Conceptual example:

~~~java
objectMapper.addMixIn(
    ApplicationAuthenticationContext.class,
    ApplicationAuthenticationContextMixin.class);
~~~

`ApplicationAuthenticationContextMixin` is an application-defined mixin. It must describe the exact constructor/creator, properties, or custom serializers needed; the class names in the example are not Spring APIs.

### 12.1. Class Names Can Become Data Constraints

When polymorphic typing records class names, persisted JSON becomes coupled to packages and class names. If you refactor a class or move its package, legacy data may fail to deserialize.

For long-lived data, consider explicit schema/versioning for custom DTOs, backward-compatible serializers/deserializers, or JSON migrations before deleting old classes.

## 13. Java Time and Additional Modules

`OAuth2AuthorizationServerJackson2Module` includes a mixin for `Duration`. That does not mean every class in the Java Time API or every custom type is automatically supported.

If custom attributes store `Instant`, `LocalDate`, `OffsetDateTime`, or other JDK types, verify which Jackson modules are needed in your active version. With Jackson 2, `JavaTimeModule` from `jackson-datatype-jsr310` may be needed for Java Time types not handled by other modules.

Example if custom attributes genuinely need Java Time:

~~~java
objectMapper.registerModule(new JavaTimeModule());
~~~

Do not add modules under a “register everything just in case” mindset. Every module expands the set of types the mapper accepts; only add dependencies/serializers when concrete data requires support.

## 14. JSON Compatibility Across Version Upgrades

Persisted JSON can outlive a deployment. Upgrading Spring Security or Spring Authorization Server can change:

- Supported classes or mixins.
- Data types inside settings and metadata.
- How type information is written.
- Jackson modules and mapper APIs.
- New enum/algorithm values.
- Application-added custom attribute structures.

A new version may read old data, but that does not mean all new JSON will be readable by the old version. Avoid prolonged mixed-version rollouts where nodes run differing serializers/deserializers without verified compatibility.

### 14.1. Compatibility-Driven Migrations

Before upgrading:

1. Back up client, authorization, and consent tables.
2. Capture representative JSON snapshots for each grant/token type.
3. Verify the new version reads old data.
4. Verify the new version writes data and reads it back.
5. Check rollback: can the old version read JSON written by the new version?
6. If not, plan migrations and a clear cutover window.

Never hand-edit type metadata in the database without migration tooling and round-trip tests.

## 15. Distinguishing Serialization and Deserialization Errors

| Symptom | Phase | Common cause |
|---|---|---|
| `InvalidDefinitionException` on save | Serialization | Missing suitable serializer/creator or unsupported object graph |
| Fails to write `Duration`/settings types | Serialization | Missing matching module/mixin |
| `InvalidTypeIdException` on read | Deserialization | Unrecognized type metadata or class missing from classpath |
| `MismatchedInputException` | Deserialization | JSON shape differs from expected mapper type |
| `UnrecognizedPropertyException` | Deserialization | JSON contains a new property unhandled by current model/mapper |
| Fails to restore `Authentication` | Deserialization | Missing Spring Security module or type metadata |
| `ClassNotFoundException` | Deserialization | Stored class name belongs to a renamed or removed package/class |
| Truncated data or malformed JSON | Database/read | Wrong column length, encoding, or migration |

### 15.1. Read the Root Cause, Not Only the Outer Exception

JDBC mappers may wrap Jackson errors in another exception during database reads/writes. When investigating, trace the root cause and pinpoint the specific JSON column: `clientSettings`, `tokenSettings`, `attributes`, or token metadata.

Do not resolve errors by disabling validation or enabling permissive default typing. First determine which exact data type needs a serializer/deserializer.

## 16. Round-Trip Testing for RegisteredClient

A test should prove that a saved client can be read back through the repository itself:

~~~java
@Test
void registeredClientCanBeSavedAndReadBack() {
    RegisteredClient original = RegisteredClient
        .withId("registered-client-1")
        .clientId("orders-web")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.NONE)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://orders.example.com/login/oauth2/code/oidc")
        .scope(OidcScopes.OPENID)
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .accessTokenTimeToLive(Duration.ofMinutes(5))
            .build())
        .build();

    registeredClientRepository.save(original);

    RegisteredClient restored =
        registeredClientRepository.findByClientId("orders-web");

    assertThat(restored).isNotNull();
    assertThat(restored.getId()).isEqualTo(original.getId());
    assertThat(restored.getTokenSettings().getAccessTokenTimeToLive())
        .isEqualTo(Duration.ofMinutes(5));
}
~~~

This is an integration test against a test database. Do not mock JDBC mappers if the goal is to verify Jackson serialization/deserialization.

## 17. Round-Trip Testing for OAuth2Authorization

Authorization tests should include realistic attributes and token metadata used by the application. Skeleton example:

~~~java
@Test
void authorizationAttributesCanBePersistedAndRestored() {
    OAuth2Authorization original =
        OAuth2Authorization.withRegisteredClient(registeredClient)
            .id("authorization-1")
            .principalName("user-42")
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizedScopes(Set.of("openid", "orders.read"))
            .attribute("tenant_id", "tenant-17")
            .attribute("login_channel", "web")
            .build();

    authorizationService.save(original);

    OAuth2Authorization restored =
        authorizationService.findById("authorization-1");

    assertThat(restored).isNotNull();
    assertThat(restored.getAttribute("tenant_id"))
        .isEqualTo("tenant-17");
    assertThat(restored.getAuthorizedScopes())
        .containsExactlyInAnyOrder("openid", "orders.read");
}
~~~

Complete tests should create valid tokens/metadata via the corresponding builders/providers, then assert token values, issued-at, expires-at, claims, and metadata after reading back.

### 17.1. Testing Custom Types

If authorization attributes include custom DTOs or `Authentication`, add tests for:

- Save and read back in the same process.
- Save, close `ApplicationContext`, restart, and read.
- Read legacy JSON data after an upgrade.
- JSON with disallowed types is rejected.
- Renamed legacy classes have a migration/compatibility path.

## 18. Negative Testing for Deserialization

Do not test only happy paths. Seed controlled malformed data in a test database:

| Test data | Expected result |
|---|---|
| Malformed JSON | Read fails cleanly with a clear root cause |
| Type ID outside contract | Rejected |
| Class no longer on classpath | Compatibility error detected |
| Property with mismatched type | Rejected or handled per defined migration |
| JSON containing unregistered custom class | Not arbitrarily instantiated |
| Truncated JSON column | Caught in persistence tests |
| Type metadata from external payload | Never fed into the persistence mapper |

Negative tests should run on an isolated database; never test by directly mutating production data.

## 19. Jackson 2 and Jackson 3: Do Not Mix APIs

Spring Security 7 shifts toward Jackson 3 support. Jackson 2 APIs such as `SecurityJackson2Modules` and mappers using `com.fasterxml.jackson.databind.ObjectMapper` are marked deprecated for removal in the new line.

Corresponding names in Jackson 3 include:

| Jackson 2 | Jackson 3 |
|---|---|
| `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.json.JsonMapper` |
| `SecurityJackson2Modules` | `SecurityJacksonModules` |
| `OAuth2AuthorizationServerJackson2Module` | `OAuth2AuthorizationServerJacksonModule` |
| `RegisteredClientRowMapper` | `JsonMapperRegisteredClientRowMapper` |
| `RegisteredClientParametersMapper` | `JsonMapperRegisteredClientParametersMapper` |
| `OAuth2AuthorizationRowMapper` | `JsonMapperOAuth2AuthorizationRowMapper` |
| `OAuth2AuthorizationParametersMapper` | `JsonMapperOAuth2AuthorizationParametersMapper` |

In Jackson 3, Spring Security provides `SecurityJacksonModules` to register modules, include type information, and configure a `PolymorphicTypeValidator`. You can extend the validator with specific custom types when the application genuinely requires them.

Conceptual Jackson 3 example:

~~~java
BasicPolymorphicTypeValidator.Builder validator =
    BasicPolymorphicTypeValidator.builder()
        .allowIfSubType(ApplicationPersistedAttribute.class);

JsonMapper jsonMapper = JsonMapper.builder()
    .addModules(SecurityJacksonModules.getModules(
        getClass().getClassLoader(), validator))
    .build();
~~~

This is the approach for the corresponding Jackson 3 stack. Cross-check constructors and nested mapper classes against the exact Spring Security/Spring Authorization Server version API.

**Never pass a Jackson 2 `ObjectMapper` into a constructor expecting a Jackson 3 `JsonMapper`.** The two libraries have different packages and API types.

## 20. Safe Deserialization Checklist

- Use the persistence mapper only to read JSON from the data store inside the Authorization Server's trust boundary.
- Never use this mapper for HTTP request bodies or user-uploaded files.
- Never enable global default typing on web/API mappers.
- Never use a validator that permits all subtypes.
- Restrict database accounts authorized to write to authorization tables.
- Limit custom attribute types and keep schemas small.
- Never store unnecessary object graphs inside authorization attributes.
- Use deliberate mixins/serializers/deserializers for custom types.
- Verify legacy data when renaming packages/classes or upgrading dependencies.
- Maintain round-trip tests, negative tests, and restart tests.
- Redact tokens, secrets, and PII from persistence error logs.
- Monitor type ID errors, class-not-found errors, and JSON parse failures.

## 21. Operations and Observability

Monitor these metrics:

- Serialization errors when saving `RegisteredClient`.
- Serialization errors when saving `OAuth2Authorization`.
- Deserialization errors per repository.
- Rate of failed authorization/client record reads.
- JSON parse errors and unknown type IDs.
- JSON payload sizes in settings/attributes/metadata columns.
- Count of records using older custom attribute versions.
- Changes in error rates after deploying a new version.

Never log raw authorization attributes or token metadata if they may contain tokens, subjects, emails, client secrets, or sensitive data.

### 21.1. Runbook When Authorizations Fail to Read After Restart

1. Confirm the exact `ObjectMapper` bean is injected into both row and parameters mappers.
2. Verify both Jackson modules are registered.
3. Identify the first JSON column causing the error.
4. Verify whether the type ID has a corresponding class on the classpath.
5. Check whether modules/mixins changed after an upgrade.
6. Check whether the JSON data was written by a node running another version.
7. Check column lengths, encoding, and migrations.
8. Restore from backup or run a tested migration if JSON is corrupted.

Never resolve failures by stripping all type validation or deleting authorization records without determining the impact on active grants/tokens.

## 22. Common Configuration Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Registering only the Spring Security module | Authorization Server–specific types fail | Also register the Authorization Server module |
| Registering only the Authorization Server module | Some Spring Security `Authentication`/collections fail to restore | Register `SecurityJackson2Modules` |
| Configuring only `RowMapper` | Written JSON may not match the read mapper's contract | Configure `ParametersMapper` as well |
| Configuring only `ParametersMapper` | Writes succeed but cannot be read back | Configure `RowMapper` as well |
| Sharing the general web mapper | Polymorphic deserialization leaks to HTTP data | Separate the persistence mapper |
| Storing large custom object graphs | JSON is brittle and hard to control | Store small DTOs/primitives |
| Refactoring class names | Legacy JSON may fail to resolve classes | Provide migrations or compatibility types |
| Using Jackson 2 APIs with Jackson 3 | Compile/runtime errors and dependency mismatch | Choose APIs matching the exact version |
| JSON columns too short | Data truncated or save fails | Adjust schema and test sizes |
| Hand-writing JSON into the DB | Type metadata violates contract | Use repositories/mappers or tested migrations |

## 23. Production Deployment Checklist

- [ ] Exact Spring Authorization Server, Spring Security, and Jackson versions identified.
- [ ] Jackson 2 or Jackson 3 chosen consistently.
- [ ] Persistence `ObjectMapper`/`JsonMapper` configured once.
- [ ] Matching Spring Security module present on the classpath.
- [ ] Version-appropriate Spring Authorization Server module registered.
- [ ] `RegisteredClient` `RowMapper` and `ParametersMapper` share the same mapper.
- [ ] `OAuth2Authorization` `RowMapper` and `ParametersMapper` share the same mapper.
- [ ] `RegisteredClientRepository` is injected into `OAuth2AuthorizationService`.
- [ ] Persistence mapper is never used to read untrusted HTTP input.
- [ ] Database write permissions are restricted.
- [ ] Custom types are allowlisted and schema/versioned.
- [ ] Permissive default typing is not enabled on shared mappers.
- [ ] Round-trip tests exist for `RegisteredClient` and `OAuth2Authorization`.
- [ ] Post-restart tests and legacy JSON data tests are in place.
- [ ] Negative tests exist for invalid type IDs.
- [ ] Column lengths accommodate settings/attributes/metadata.
- [ ] Logs/metrics do not leak tokens, secrets, or PII.
- [ ] Runbooks exist for deserialization failures and version migrations.

### Core Knowledge

Spring Authorization Server JDBC persistence uses Jackson to convert settings, attributes, and token metadata to JSON and reconstruct them when reading from the database. On the Jackson 2 stack, configuration generally requires both `SecurityJackson2Modules` and `OAuth2AuthorizationServerJackson2Module`. Both `JdbcRegisteredClientRepository` and `JdbcOAuth2AuthorizationService` have mappers for writing and reading; when replacing mappers, configure both directions with the exact same `ObjectMapper`.

Spring modules supply mixins and type metadata to reconstruct necessary polymorphic types. This mechanism also turns deserialization into a security boundary: use the persistence mapper only for controlled database data, restrict write permissions, never apply it to client-submitted JSON, and never enable permissive default typing application-wide. When storing custom attributes, prefer small, stable, versioned types.

Spring Security 7 transitions to Jackson 3 with `SecurityJacksonModules`, `OAuth2AuthorizationServerJacksonModule`, and `JsonMapper` JDBC mappers. Choose APIs matching your actual dependencies, and never mix Jackson 2 and Jackson 3.

## References

- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html)
- [Spring Authorization Server 1.5.8 — JdbcRegisteredClientRepository API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/JdbcRegisteredClientRepository.html)
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerJackson2Module API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/jackson2/OAuth2AuthorizationServerJackson2Module.html)
- [Spring Security 6.5 — Jackson Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/jackson.html)
- [Spring Security 6.5 — SecurityJackson2Modules API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/jackson2/SecurityJackson2Modules.html)
- [Spring Security 7.1 — Jackson Support and PolymorphicTypeValidator](https://docs.spring.io/spring-security/reference/features/integrations/jackson.html)
- [Spring Security 7.1 — SecurityJacksonModules API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/jackson/SecurityJacksonModules.html)
- [Spring Security 7.1 — OAuth2AuthorizationServerJacksonModule API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/authorization/jackson/OAuth2AuthorizationServerJacksonModule.html)
