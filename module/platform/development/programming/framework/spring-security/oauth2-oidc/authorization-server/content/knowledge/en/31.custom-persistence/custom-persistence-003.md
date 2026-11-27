# Implementing OAuth2AuthorizationConsentService

The Authorization Server needs to persist a user's consent decision when an OAuth2 Client requests access. Once a user approves certain scopes or authorities for a client, the server must remember that decision to handle subsequent authorization requests. If consent only lives in a single JVM's memory, decisions are lost on restart and other nodes in a cluster cannot share state.

Spring Authorization Server provides the **OAuth2AuthorizationConsentService** abstraction to store, find, and remove **OAuth2AuthorizationConsent**. The framework ships with in-memory and JDBC implementations; an application can provide its own service implementation to use JPA, Redis, a document database, or an external consent system.

This lesson belongs to the **Custom Persistence** chapter of the **SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER** module. The module scope is to learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The focus is on understanding the consent domain model, implementing `OAuth2AuthorizationConsentService`, wiring the service into the authorization endpoint, and keeping consent data consistent and secure.

> **Important Distinction:** `OAuth2AuthorizationConsent` stores the permission decision granted by a resource owner to a `RegisteredClient`. `OAuth2Authorization` stores the state of an authorization flow and issued tokens. The two models are related, yet they have separate lifecycles and purposes.

## 1. What Problem Does Consent Solve?

In the Authorization Code Flow, a client may request scopes such as `profile`, `email`, or `orders.read`. The OP authenticates the End-User and decides whether to display a consent screen. The user may approve all or only a subset of the requested permissions, depending on application policy and UI.

For example, the client `portal-web` requests:

~~~text
openid
profile
email
orders.read
~~~

The user agrees to let the client read profile and email information, but denies permission to read orders. The OP must persist the granted decision so future authorizations can compare already-approved permissions against the permissions the client is currently requesting.

Consent is not a temporary UI checkbox. It is security-sensitive data that determines whether a client can proceed with authorization without prompting the user again.

### 1.1. Consent Is a Decision Between a Principal and a Client

A Spring Authorization Server consent record is identified by two values:

| Field | Meaning |
|---|---|
| registeredClientId | Unique internal ID of the `RegisteredClient` |
| principalName | Principal name of the resource owner |
| authorities | Authorities granted by the principal to the client |

Therefore, the same user can have different consents for different clients. Likewise, the same client can have separate consents for multiple users.

Example:

| Registered client | Principal | Granted Authorities |
|---|---|---|
| portal-web | user-42 | SCOPE_openid, SCOPE_profile |
| mobile-app | user-42 | SCOPE_openid, SCOPE_profile, SCOPE_email |
| portal-web | user-84 | SCOPE_openid, SCOPE_email |

Do not use the public `client_id` in place of `registeredClientId` in the storage key. The model uses the `RegisteredClient` ID; the service can look up the corresponding registration to validate the record.

### 1.2. Consent Can Contain Multiple Types of Authorities

`OAuth2AuthorizationConsent` stores a `Set<GrantedAuthority>`, not merely a list of scopes. An authority can represent:

- An OAuth2 scope, typically prefixed with `SCOPE_`;
- Permission to access a group of claims;
- A business permission defined by the OP;
- A role or extended policy authority.

The builder provides a `scope(String)` method to add a scope and automatically convert it into a `SimpleGrantedAuthority` prefixed with `SCOPE_`. The `authority(GrantedAuthority)` method lets you store a general authority.

### 1.3. Consent Is Not an Access Token

Consent records a granted permission decision. An access token is a credential issued within a specific authorization. Consent can outlive an access token; an expired access token does not mean consent is automatically deleted.

Conversely, revoking consent does not automatically invalidate every already-issued access token. If existing tokens must be revoked, the application must enforce token revocation or a separate authorization lifecycle policy.

## 2. OAuth2AuthorizationConsent and OAuth2AuthorizationConsentService

`OAuth2AuthorizationConsent` is an immutable, `Serializable` domain object containing a registered client ID, a principal name, and a set of authorities. The service manages these objects in a store.

~~~mermaid
flowchart TD
    U[Resource Owner] --> UI[Consent UI]
    UI --> EP[Authorization Endpoint]
    EP --> AP[Consent Authentication Provider]
    AP --> CS[OAuth2AuthorizationConsentService]
    CS --> DB[(Custom Consent Store)]
    CS --> AP
    AP --> AU[OAuth2AuthorizationService]
    AU --> CODE[Authorization Code]
    CODE --> RP[OAuth2 Client]
~~~

This flow shows that the consent service is a dependency of authorization request processing. Consent is read to determine granted permissions and written when the user approves authorities.

### 2.1. Domain Model

Key accessors:

| API | Result |
|---|---|
| getRegisteredClientId() | ID of the `RegisteredClient` |
| getPrincipalName() | Principal name of the resource owner |
| getAuthorities() | Granted `Set<GrantedAuthority>` |
| getScopes() | Scopes derived from authorities prefixed with `SCOPE_` |
| withId(registeredClientId, principalName) | Creates a builder with the composite identity |
| from(consent) | Creates a builder from an existing consent |

Example of creating a consent:

~~~java
OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId(
            registeredClient.getId(),
            authentication.getName())
        .scope("openid")
        .scope("profile")
        .scope("orders.read")
        .build();
~~~

The builder requires at least one `GrantedAuthority` when building. If the user denies all permissions, do not create an empty consent; handle the denial according to the authorization flow and application policy.

### 2.2. Scopes Are Stored as Authorities

When calling:

~~~java
OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId("client-internal-id", "user-42")
        .scope("profile")
        .build();
~~~

The stored authority is:

~~~text
SCOPE_profile
~~~

When reading scopes, `getScopes()` takes authorities prefixed with `SCOPE_` and strips the prefix. Custom non-scope authorities remain in `getAuthorities()`.

### 2.3. Service Contract

`OAuth2AuthorizationConsentService` has three methods:

~~~java
public interface OAuth2AuthorizationConsentService {

    void save(OAuth2AuthorizationConsent authorizationConsent);

    void remove(OAuth2AuthorizationConsent authorizationConsent);

    OAuth2AuthorizationConsent findById(
        String registeredClientId,
        String principalName
    );
}
~~~

This compact contract intentionally uses the `(registeredClientId, principalName)` pair as the identifier. `findById` returns `null` when no consent exists. It does not return `Optional` and does not look up by the public `client_id`.

## 3. The Three Service Operations and Semantics

### 3.1. findById

`findById` looks up a consent decision by the pair:

~~~java
OAuth2AuthorizationConsent consent =
    consentService.findById(
        registeredClient.getId(),
        principal.getName()
    );

if (consent == null) {
    // The principal does not yet have consent for this RegisteredClient.
}
~~~

This is the lookup that authorization request processing uses to compare granted authorities against the authorities requested by the client.

### 3.2. save

`save` persists a new consent or replaces/updates an existing consent according to implementation semantics:

~~~java
OAuth2AuthorizationConsent updatedConsent =
    OAuth2AuthorizationConsent.withId(
            registeredClient.getId(),
            principal.getName())
        .scope("openid")
        .scope("profile")
        .build();

consentService.save(updatedConsent);
~~~

In the consent flow, the provider may construct a consent from the user-approved authorities and call `save`. A custom implementation should clearly define whether `save` is an insert or upsert and ensure the same composite key never produces multiple records.

### 3.3. remove

`remove` deletes the consent for the exact client and principal:

~~~java
consentService.remove(consent);
~~~

This operation revokes the entire consent record for that pair. To revoke only a single authority, build a new consent with the remaining authorities and call `save`; do not delete the record if the user retains other permissions.

### 3.4. Idempotency and Null Handling

The service contract does not require an implementation to throw when removing a non-existent record. In production systems, `remove` should generally be idempotent: calling it multiple times yields a consistent outcome.

For `save` and `findById`:

- Reject `null` inputs;
- Reject empty `registeredClientId`/`principalName`;
- Do not change case or trim the principal name unless the identity provider defines that normalization;
- Never return consent belonging to another client or principal;
- Detect malformed stored data instead of silently granting permissions.

## 4. Built-in InMemory and JDBC Implementations

Spring Authorization Server provides two common implementations:

| Implementation | Mechanism | Purpose |
|---|---|---|
| InMemoryOAuth2AuthorizationConsentService | Stores objects in JVM memory | Development and testing |
| JdbcOAuth2AuthorizationConsentService | Stores via `JdbcOperations` | Relational database |
| Custom implementation | JPA, Redis, document store, or external service | Custom persistence architecture |

`OAuth2AuthorizationConsentService` is an optional component. If the application does not supply a bean, Spring Authorization Server defaults to `InMemoryOAuth2AuthorizationConsentService`. This is convenient for demos, but consent is lost on restart and not shared across nodes.

### 4.1. When Do You Need a Custom Service?

A custom implementation may be needed when:

- The application standardizes persistence on JPA;
- Consents are stored in an existing database;
- Decisions must sync with a privacy/consent management system;
- The system runs across multiple nodes and needs a shared store;
- Additional tenant, version, timestamp, or audit metadata must be stored;
- Queries, transactions, or retention must be tuned to the workload.

If `JdbcOAuth2AuthorizationConsentService` fits your schema, database, and operations, there is no need to rewrite the service. A custom implementation adds ownership of transactions, migrations, concurrency, serialization, and data security.

### 4.2. Do Not Confuse the Consent Service with the Authorization Service

| Service | Stored Data |
|---|---|
| OAuth2AuthorizationConsentService | Authority decisions granted by a principal to a client |
| OAuth2AuthorizationService | Authorization flow state, token values, token metadata, and attributes |
| RegisteredClientRepository | Client registrations, grant types, scopes, redirect URIs, and settings |

A consent record can exist before or after many authorization records. Never use `OAuth2AuthorizationService` as a substitute for a consent store.

## 5. Designing Custom Persistence with JPA

To implement a custom service, start from the domain model and the interface's three operations. With JPA, a consent record can be stored as an entity with a composite primary key consisting of the registered client ID and principal name.

Reference schema:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(255) NOT NULL,
    principal_name varchar(255) NOT NULL,
    authorities varchar(4000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

The composite primary key ensures each client has at most one consent record per principal. When consent changes, the service updates the authorities set on the existing record.

### 5.1. Why Use a Composite Key?

One user can grant consent to multiple clients; one client can hold consents from multiple users. A single key on `principalName` alone causes clients to overwrite each other's consents. A single key on `registeredClientId` alone causes one user to overwrite another user's consent.

The right key is:

~~~text
(registered_client_id, principal_name)
~~~

Do not use email as the principal key if username/subject is the value `Authentication` actually uses. If principal names can change, design a stable identity key and migrate consent records when the identity changes.

### 5.2. Storing Authorities as a String or a Child Table?

There are two common approaches:

| Storage Approach | Advantages | Considerations |
|---|---|---|
| Single `authorities` column as comma-delimited or JSON | Simple entity, fewer joins | Requires length limits and a stable serializer |
| Normalized child table with one row per authority | Normalized, easier to query individual permissions | Adds joins, mapping, and transactions |

The Spring Authorization Server JPA guide illustrates a single comma-delimited `authorities` column. This is a compact structure for simple authority names. If the application has custom authorities that may contain commas, or needs to query/filter by individual authority, use JSON with a standard serializer or a child table instead of an unescaped delimiter.

### 5.3. Entity with Composite Primary Key

Simple entity example:

~~~java
@Entity
@Table(name = "oauth2_authorization_consent")
@IdClass(AuthorizationConsentEntity.ConsentId.class)
public class AuthorizationConsentEntity {

    @Id
    @Column(name = "registered_client_id", length = 255)
    private String registeredClientId;

    @Id
    @Column(name = "principal_name", length = 255)
    private String principalName;

    @Column(name = "authorities", nullable = false, length = 4000)
    private String authorities;

    protected AuthorizationConsentEntity() {
    }

    public String getRegisteredClientId() {
        return registeredClientId;
    }

    public void setRegisteredClientId(String registeredClientId) {
        this.registeredClientId = registeredClientId;
    }

    public String getPrincipalName() {
        return principalName;
    }

    public void setPrincipalName(String principalName) {
        this.principalName = principalName;
    }

    public String getAuthorities() {
        return authorities;
    }

    public void setAuthorities(String authorities) {
        this.authorities = authorities;
    }

    public static class ConsentId implements Serializable {
        private String registeredClientId;
        private String principalName;

        public ConsentId() {
        }

        public ConsentId(String registeredClientId, String principalName) {
            this.registeredClientId = registeredClientId;
            this.principalName = principalName;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ConsentId that)) {
                return false;
            }
            return Objects.equals(registeredClientId, that.registeredClientId)
                && Objects.equals(principalName, that.principalName);
        }

        @Override
        public int hashCode() {
            return Objects.hash(registeredClientId, principalName);
        }
    }
}
~~~

This is an illustrative entity using Jakarta Persistence. The composite ID class must be `Serializable` and implement `equals`/`hashCode` using both fields. In production code, add the imports and consider `@EmbeddedId` if your team prefers encapsulating the key in a value object.

### 5.4. Spring Data Repository

~~~java
public interface AuthorizationConsentRepository
        extends JpaRepository<
            AuthorizationConsentEntity,
            AuthorizationConsentEntity.ConsentId> {

    Optional<AuthorizationConsentEntity>
    findByRegisteredClientIdAndPrincipalName(
        String registeredClientId,
        String principalName
    );

    void deleteByRegisteredClientIdAndPrincipalName(
        String registeredClientId,
        String principalName
    );
}
~~~

The repository provides operations by composite key. You can use `findById(new ConsentId(...))` instead of derived queries if the key class constructor is available.

## 6. Implementing JpaOAuth2AuthorizationConsentService

The adapter service converts between Spring Authorization Server's domain model and the JPA entity. It requires two dependencies:

- `AuthorizationConsentRepository` to save and query entities;
- `RegisteredClientRepository` to verify that the referenced registered client still exists.

Checking `RegisteredClient` helps detect orphaned consent records instead of returning a consent no longer attached to a valid client registration.

### 6.1. Complete Implementation

~~~java
@Service
@Transactional(readOnly = true)
public class JpaOAuth2AuthorizationConsentService
        implements OAuth2AuthorizationConsentService {

    private final AuthorizationConsentRepository repository;
    private final RegisteredClientRepository registeredClientRepository;

    public JpaOAuth2AuthorizationConsentService(
            AuthorizationConsentRepository repository,
            RegisteredClientRepository registeredClientRepository) {
        Assert.notNull(repository, "repository cannot be null");
        Assert.notNull(registeredClientRepository,
            "registeredClientRepository cannot be null");
        this.repository = repository;
        this.registeredClientRepository = registeredClientRepository;
    }

    @Override
    @Transactional
    public void save(OAuth2AuthorizationConsent consent) {
        Assert.notNull(consent, "consent cannot be null");
        assertRegisteredClientExists(consent.getRegisteredClientId());
        repository.save(toEntity(consent));
    }

    @Override
    @Transactional
    public void remove(OAuth2AuthorizationConsent consent) {
        Assert.notNull(consent, "consent cannot be null");
        repository.deleteByRegisteredClientIdAndPrincipalName(
            consent.getRegisteredClientId(),
            consent.getPrincipalName()
        );
    }

    @Override
    public OAuth2AuthorizationConsent findById(
            String registeredClientId,
            String principalName) {
        Assert.hasText(registeredClientId,
            "registeredClientId cannot be empty");
        Assert.hasText(principalName, "principalName cannot be empty");

        return repository.findByRegisteredClientIdAndPrincipalName(
                registeredClientId, principalName)
            .map(this::toObject)
            .orElse(null);
    }

    private AuthorizationConsentEntity toEntity(
            OAuth2AuthorizationConsent consent) {
        AuthorizationConsentEntity entity =
            new AuthorizationConsentEntity();
        entity.setRegisteredClientId(consent.getRegisteredClientId());
        entity.setPrincipalName(consent.getPrincipalName());

        Set<String> authorities = consent.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toCollection(TreeSet::new));

        entity.setAuthorities(
            StringUtils.collectionToCommaDelimitedString(authorities));
        return entity;
    }

    private OAuth2AuthorizationConsent toObject(
            AuthorizationConsentEntity entity) {
        String registeredClientId = entity.getRegisteredClientId();
        assertRegisteredClientExists(registeredClientId);

        if (!StringUtils.hasText(entity.getAuthorities())) {
            throw new DataRetrievalFailureException(
                "Stored consent has no authorities");
        }

        OAuth2AuthorizationConsent.Builder builder =
            OAuth2AuthorizationConsent.withId(
                registeredClientId, entity.getPrincipalName());

        for (String authority :
                StringUtils.commaDelimitedListToSet(entity.getAuthorities())) {
            builder.authority(new SimpleGrantedAuthority(authority));
        }

        return builder.build();
    }

    private void assertRegisteredClientExists(String registeredClientId) {
        if (registeredClientRepository.findById(registeredClientId) == null) {
            throw new DataRetrievalFailureException(
                "RegisteredClient with id '" + registeredClientId
                    + "' was not found");
        }
    }
}
~~~

This code shows a complete adapter for the comma-delimited schema from the previous section. Required imports include Jakarta/Spring annotations, `Assert`, `StringUtils`, `DataRetrievalFailureException`, `GrantedAuthority`, `SimpleGrantedAuthority`, `OAuth2AuthorizationConsent`, `OAuth2AuthorizationConsentService`, `RegisteredClientRepository`, `JpaRepository`, and collection types.

### 6.2. Why Does findById Return Null?

The interface specifies `null` when not found. The service should not throw `EntityNotFoundException` when consent has never been granted; the authorization endpoint needs to distinguish missing consent from database failures.

Conversely, if the record exists while the `RegisteredClient` was deleted, that is an integrity error. The example above throws `DataRetrievalFailureException` rather than silently ignoring an orphaned record.

### 6.3. Why Is save an Upsert by Composite Key?

Spring Data JPA `save` persists or merges an entity depending on its ID state. For entities with composite keys, the repository must properly identify the key to update existing consents. If custom persistence uses insert-only semantics, handle duplicate keys via update/merge inside a transaction.

### 6.4. Why Does remove Delete by Both Fields?

Consent is identified by the pair `(registeredClientId, principalName)`. Deleting by `principalName` alone risks removing consents for multiple clients. Deleting by `registeredClientId` alone could affect multiple resource owners.

## 7. Registering the Custom Service with the Authorization Server

Once the service is declared as a Spring bean, pass it to `OAuth2AuthorizationServerConfigurer`:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationConsentService authorizationConsentService)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .authorizationConsentService(authorizationConsentService)
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is the Authorization Server configuration skeleton. The application still requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, token generators/signing keys, and an application login filter chain. The `authorizationConsentService(...)` method is the configurer's official extension point.

### 7.1. Use a Single Implementation

If multiple beans implement `OAuth2AuthorizationConsentService`, use `@Qualifier` or explicit configuration to avoid miswiring. In particular, prevent the framework from silently using the `InMemory` implementation while the application expects the JPA bean to be active.

### 7.2. Verify Wiring at Startup

You can verify the actual bean in an integration test or application context test:

~~~java
assertThat(applicationContext.getBean(
        OAuth2AuthorizationConsentService.class))
    .isInstanceOf(JpaOAuth2AuthorizationConsentService.class);
~~~

Checking the bean type alone does not prove the authorization endpoint uses it. Run a real consent flow and verify the record appears in the database.

## 8. Consent in the Authorization Code Flow

The consent service is used primarily in the Authorization Code Flow. The authorization request provider checks existing consent to decide whether to display the consent page. When the resource owner submits their choice, the consent authentication provider builds a new/updated consent and calls the service to persist it.

### 8.1. Role of the Two Authentication Providers

| Provider | Consent-Related Responsibility |
|---|---|
| OAuth2AuthorizationCodeRequestAuthenticationProvider | Processes the authorization request, reads existing consent, and determines whether consent is required |
| OAuth2AuthorizationConsentAuthenticationProvider | Processes the submitted consent decision, builds/updates `OAuth2AuthorizationConsent`, and persists it via the service |

Both providers are wired inside the Authorization Server filter chain. They receive `OAuth2AuthorizationConsentService` alongside dependencies such as `RegisteredClientRepository` and `OAuth2AuthorizationService`.

### 8.2. New Consent Flow

1. The client sends an authorization request with `client_id`, `redirect_uri`, `response_type`, `scope`, and `state`.
2. The OP authenticates the resource owner.
3. The authorization request provider looks up the `RegisteredClient` and existing consent by `registeredClientId` + `principalName`.
4. If policy requires consent and the requested permissions have not yet been approved, the OP redirects the browser to the consent page.
5. The consent page displays the client, scopes, and details needed for the user to decide.
6. The browser POSTs the user's choices back to the authorization endpoint with `state` and `client_id`.
7. The consent authentication provider verifies the request context, builds the consent, and calls `save`.
8. The Authorization Server continues the flow, issues an authorization code, and returns the response to the client.

### 8.3. Existing Consent

If the user has already granted sufficient authorities per policy, the authorization endpoint can proceed without showing the consent screen again. If the client requests additional permissions, the OP may prompt for supplemental consent.

For example, the first time `user-42` grants:

~~~text
SCOPE_openid
SCOPE_profile
~~~

Next time the client additionally requests:

~~~text
SCOPE_email
~~~

After the user agrees, the consent record can contain both the old authorities and the new authority:

~~~text
SCOPE_openid
SCOPE_profile
SCOPE_email
~~~

The service must persist the exact set of authorities in the passed object. Never merge by unioning every value with the old record, because doing so could resurrect previously revoked permissions.

## 9. Integrating a Custom Consent Page

You can configure the Authorization Endpoint to redirect the browser to a custom consent page:

~~~java
http.with(authorizationServer, server -> server
    .authorizationEndpoint(endpoint -> endpoint
        .consentPage("/oauth2/consent")
    )
);
~~~

This is a fragment inside the full Authorization Server `SecurityFilterChain`. When using a custom `consentPage`, the application must render the page and handle form presentation itself.

### 9.1. Consent Page Query Parameters

According to the Authorization Endpoint configuration, the query string passed to the consent page may contain:

| Parameter | Meaning |
|---|---|
| client_id | Public client ID for displaying the client |
| scope | Scopes in the authorization request |
| state | Protection/correlation value for the consent request |

The consent page can look up `RegisteredClient` to display the client name and UX details. That lookup is purely for UI display; the server must still validate the client/request when the form is submitted.

### 9.2. The Form Must POST to the Authorization Endpoint

The consent form must send an HTTP POST to the endpoint configured by `AuthorizationServerSettings.getAuthorizationEndpoint()`. The form needs:

- `client_id` received from the authorization request;
- `state` received from the authorization request;
- The scopes approved by the resource owner;
- The CSRF token as configured by Spring Security.

Illustrative HTML example:

~~~html
<form method="post" action="/oauth2/authorize">
  <input type="hidden" name="client_id" value="portal-web">
  <input type="hidden" name="state" value="STATE_FROM_REQUEST">

  <label>
    <input type="checkbox" name="scope" value="openid" checked>
    OpenID Identity
  </label>
  <label>
    <input type="checkbox" name="scope" value="profile" checked>
    Profile Information
  </label>
  <label>
    <input type="checkbox" name="scope" value="email">
    Email Address
  </label>

  <button type="submit">Approve</button>
</form>
~~~

This is condensed HTML illustrating the protocol fields. In a real application, render using a template engine, encode all values, include the CSRF hidden field, and handle explicit denial choices cleanly.

### 9.3. Do Not Trust Form Data

Both the client ID and scopes from the browser can be tampered with. The consent UI must not write directly to the repository based solely on form values. Always POST to the Authorization Endpoint so the provider validates the `state` token, `RegisteredClient`, authorization request, current principal, and permitted scopes.

Do not allow the form to add scopes that the client did not request or is not registered for. The provider must enforce validation and policy before calling the consent service.

### 9.4. Denying Consent

If the resource owner denies the entire request, do not build an `OAuth2AuthorizationConsent` with empty authorities because the builder requires at least one authority. Let the Authorization Endpoint handle the denial decision per protocol and application UX.

If the user grants partial approval, only the approved authorities are saved. Denied scopes must not be added to the consent record.

## 10. Consent Customizer and Policy Extensions

`OAuth2AuthorizationConsentAuthenticationProvider` provides the `setAuthorizationConsentCustomizer(...)` extension point taking a `Consumer<OAuth2AuthorizationConsentAuthenticationContext>`. The context supplies the builder prior to saving along with request details.

The context can provide:

- The `OAuth2AuthorizationConsent.Builder` being constructed;
- The `Authentication` for the consent request;
- The associated `RegisteredClient`;
- The `OAuth2Authorization` linked to the `state` token;
- The original `OAuth2AuthorizationRequest`.

### 10.1. When Do You Need a Customizer?

You can use a customizer to:

- Add business authorities after policy verification;
- Strip authorities disallowed by the tenant;
- Bind the consent decision to additional context;
- Perform per-`RegisteredClient` policy checks;
- Emit audit metadata outside the consent domain model.

Do not use a customizer to grant extra scopes merely because those scopes exist on the `RegisteredClient`. Decisions must match the authorization request, user choices, and policy.

### 10.2. Do Not Turn the Consent Customizer into a Persistence Layer

The customizer mutates the builder; the consent service remains responsible for persisting the domain object. Keep persistence logic inside the service/repository for testability, transaction management, and backend portability.

### 10.3. Consent Can Include Non-Scope Authorities

For example, an application needing to store an additional permission:

~~~java
OAuth2AuthorizationConsent consent =
    OAuth2AuthorizationConsent.withId(registeredClientId, principalName)
        .scope("openid")
        .scope("profile")
        .authority(new SimpleGrantedAuthority("PERMISSION_invoice.read"))
        .build();
~~~

Extended authorities must have a clear namespace and policy. Never allow arbitrary authority names from the browser to be added to consent without validation.

## 11. Designing Consent Updates and Revocation

A consent record typically represents a snapshot of the granted authority set. Each time the user changes their decision, the service must persist the new resulting set.

### 11.1. Partial Permission Updates

Example current consent:

~~~text
SCOPE_openid
SCOPE_profile
SCOPE_email
~~~

The user revokes `email` while keeping `openid` and `profile`. Build a new consent:

~~~java
OAuth2AuthorizationConsent updated =
    OAuth2AuthorizationConsent.withId(registeredClientId, principalName)
        .scope("openid")
        .scope("profile")
        .build();

consentService.save(updated);
~~~

Do not re-add `email` from the old record. `save` must persist the exact authority set from the new object.

### 11.2. Revoking All Consent

~~~java
OAuth2AuthorizationConsent current =
    consentService.findById(registeredClientId, principalName);

if (current != null) {
    consentService.remove(current);
}
~~~

This is how you delete a consent record. Administrative APIs must authenticate the End-User and verify that callers only operate on their own consent or hold explicit admin privileges.

### 11.3. Revoking Consent Does Not Automatically Revoke Tokens

Deleting consent prevents the old consent record from being reused in future authorization requests. It does not automatically delete `OAuth2Authorization` records or revoke previously issued access tokens or refresh tokens.

If privacy policy requires revoking consent to terminate existing access, the workflow must coordinate:

1. Updating/deleting consent;
2. Locating related authorization records by principal and client;
3. Revoking authorizations/tokens according to policy;
4. Updating refresh token and access token state;
5. Recording an audit event;
6. Notifying Resource Servers/RPs if the architecture has a propagation mechanism.

Do not delete all authorizations of a principal just because consent was revoked for one client. Scope the revocation strictly to the affected client and revoked permissions.

### 11.4. Re-Consent After a Client Changes Scopes

When a `RegisteredClient` is granted new scopes, prior consent does not automatically cover the new permissions. Subsequent authorization requests must compare granted permissions against requested permissions and re-prompt the user as needed.

When a client has scopes removed or is decommissioned, decide whether to retain consent for auditing or delete it under your retention policy. Do not delete consent merely because a client temporarily stops requesting a scope.

## 12. Alternative Persistence Options

Because the service interface is small, it can be implemented across multiple backends. The key is preserving the composite identity, authority set, and semantics of the three operations.

### 12.1. Redis

Redis can fit well when the Authorization Server already uses Redis for data shared across nodes:

~~~text
key: oauth2:consent:{registeredClientId}:{principalName}
value: serialized set of authority names
~~~

A Redis design requires:

- Encoding or length-prefixing key components to avoid collisions when values contain delimiter characters;
- Serializing the authority set in a versioned format;
- Having `save` replace the entire set based on the new consent object;
- Having `find` return `null` if the key does not exist;
- Having `remove` delete the exact composite key;
- Not setting arbitrary TTLs if consent has no policy-defined expiration;
- Using atomic commands/scripts when concurrent updates are needed.

Never join client ID and principal name with a delimiter assuming values will never contain that character. You can use Base64URL or a namespaced hash to build deterministic keys.

### 12.2. Document Database

A document can store:

~~~json
{
  "registeredClientId": "client-internal-123",
  "principalName": "user-42",
  "authorities": [
    "SCOPE_openid",
    "SCOPE_profile",
    "PERMISSION_invoice.read"
  ],
  "schemaVersion": 1
}
~~~

Create a unique compound index on `registeredClientId` and `principalName`. Using an array instead of a delimited string preserves authority names intact. If consent history is needed, store audit events in a separate collection; the current document represents only the currently effective state.

### 12.3. External Consent Service

An organization may store consents in a privacy/consent management platform. An adapter implementing `OAuth2AuthorizationConsentService` calls that system's API.

The adapter must define:

- Timeouts and retry policies;
- Idempotency keys for `save`/`remove`;
- Service-to-service authentication;
- Consistency and read-after-write guarantees;
- Mapping between `registeredClientId`/`principalName` and external identifiers;
- Handling when the external service is unavailable.

Do not retry a consent operation indefinitely. The authorization endpoint must fail closed if reliable consent state cannot be determined.

## 13. Normalized Authority Table Model

If authority names can contain commas or the permission set can be large, use a child table to store each authority. Reference schema:

~~~sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(255) NOT NULL,
    principal_name varchar(255) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);

CREATE TABLE oauth2_authorization_consent_authority (
    registered_client_id varchar(255) NOT NULL,
    principal_name varchar(255) NOT NULL,
    authority varchar(500) NOT NULL,
    PRIMARY KEY (
        registered_client_id,
        principal_name,
        authority
    ),
    FOREIGN KEY (registered_client_id, principal_name)
        REFERENCES oauth2_authorization_consent (
            registered_client_id,
            principal_name
        )
        ON DELETE CASCADE
);
~~~

With JPA, the child table can be mapped using `@ElementCollection`:

~~~java
@ElementCollection(fetch = FetchType.EAGER)
@CollectionTable(
    name = "oauth2_authorization_consent_authority",
    joinColumns = {
        @JoinColumn(
            name = "registered_client_id",
            referencedColumnName = "registered_client_id"),
        @JoinColumn(
            name = "principal_name",
            referencedColumnName = "principal_name")
    }
)
@Column(name = "authority", nullable = false, length = 500)
private Set<String> authorities = new HashSet<>();
~~~

The parent entity still holds the composite key of registered client ID and principal name. With this mapping, the service converts `Set<String>` to `SimpleGrantedAuthority` on reads and vice versa on writes. Deleting the parent record can cascade to authority rows via the foreign key.

### 13.1. Advantages of a Child Table

- No need to escape commas in authorities;
- No total length limit on a single `authorities` column;
- Ability to query or aggregate by individual authority;
- Unique key prevents duplicate authorities within one consent;
- Foreign key prevents orphaned authority rows.

### 13.2. Normalization Costs

Reads must load the authority collection; writes may delete/insert multiple child rows; transactions must span both parent and children. At large consent volumes, measure query counts and batching behavior. Do not default to `EAGER` on every relationship across the system; choose fetch strategies based on actual read paths.

## 14. Multi-Tenancy and Identity Boundaries

`OAuth2AuthorizationConsentService` only takes two identifier parameters: `registeredClientId` and `principalName`. It has no dedicated `tenantId`. In a multi-tenant system, the design must guarantee these two values cannot collide across tenants.

Possible approaches:

- Namespace `RegisteredClient` internal IDs by tenant so they are globally unique;
- Use an immutable tenant-namespaced subject for the principal name;
- Have the adapter resolve the tenant from the authenticated security context and include it in the storage key;
- Give each tenant its own schema/database;
- Maintain a central registry mapping external client/subject to canonical key pairs.

Never take a tenant ID from a query/form parameter and use it directly to query consent. Tenant context must come from a trusted authenticated source.

### 14.1. Principal Name Must Be Consistent

Suppose a previous login used an email as `principalName`, while a subsequent `Authentication` returns a user UUID. The service will look up two different consents. Choose a stable canonical principal identifier from the outset and use it consistently across authentication, consent, and authorization.

### 14.2. Do Not Use client_id Instead of registeredClientId

`RegisteredClient` has both an internal `id` and a public `clientId`. `OAuth2AuthorizationConsent` uses `RegisteredClient.getId()`. If storage uses the public `clientId`, maintain an explicit mapping and never pass `clientId` into `findById` by mistake.

## 15. Transactions and Handling Concurrent Consent Updates

Consent can be updated concurrently from multiple browser sessions or nodes. For instance, two open tabs might show the consent page and submit different selections. If the service performs a read-modify-write without a concurrency policy, the later operation can overwrite the earlier change.

### 15.1. Transaction Boundaries

With JPA, `save`/`remove` should run inside a transaction so the entity and authority rows are written/deleted together. `findById` can use a read-only transaction if the repository needs to load lazy associations.

Never hold a database transaction open while the user is reading the consent page. The authorization request, browser interaction, and form submission are separate HTTP requests.

### 15.2. Optimistic Locking

You can add a version column to the entity:

~~~java
@Version
private long version;
~~~

When two requests update the same record concurrently, JPA can detect the stale update and throw `OptimisticLockException`. The application must decide whether to show an error, reload consent state, or ask the user to confirm again.

`OAuth2AuthorizationConsentService` does not carry a version in its domain object, so versioning is a persistence detail. Do not silently retry by unioning authorities from both requests; doing so could restore permissions that one request just revoked.

### 15.3. Unique Constraints and First-Insert Races

Two initial requests for the same client/principal pair may both see no existing consent and both attempt to insert. The composite primary key protects uniqueness. The implementation must handle duplicate-key races by reloading/updating in a new transaction if application semantics permit.

Never catch all database exceptions and treat `save` as successful. Only handle recognized duplicate-key conflicts; connection errors, other constraints, and serialization failures must be propagated.

### 15.4. Save Is a Snapshot, Not a Blind Merge

The service receives a complete `OAuth2AuthorizationConsent`. Persist the exact authorities of that object. If the service merges with the existing record, permissions removed in a new request may never disappear.

## 16. Securing Consent Data

A consent record reflects permissions granted by a resource owner. It is security-sensitive data even though it does not contain access tokens.

Required controls:

- A database role that only grants the application read/write access to the required consent tables;
- TLS for database/cache connections;
- Encryption at rest and backup protection per policy;
- Avoid logging full authority sets or user details unnecessarily;
- Prevent users from modifying another principal's consent;
- Never allow clients to invoke the service or repository directly;
- Validate both `RegisteredClient` and principal before saving;
- Audit consent changes with actor, timestamp, client, and outcome;
- Restrict admin privileges for viewing/deleting consents.

### 16.1. Consent UI CSRF Protection and Anti-Tampering

The consent form is a security-impacting POST. Keep Spring Security's CSRF protection active, validate the `state` token, and let the Authorization Endpoint handle submission. Never build a separate POST endpoint that accepts `client_id`/`principalName`/`scopes` and calls `save` directly while bypassing protocol validation.

### 16.2. Do Not Infer Consent from Client Metadata

`RegisteredClient` scopes indicate which scopes a client is allowed to request. A consent record indicates which authorities a principal has actually granted. These two sets are distinct. Never auto-grant all registered scopes merely because the client is valid.

### 16.3. Separate Audit History from Current State

`OAuth2AuthorizationConsent` only represents the current decision. If you need a history of who granted or revoked permissions, store separate audit events containing event type, principal, registered client, authority delta, timestamp, actor, and correlation ID.

Never record passwords, session cookies, access tokens, refresh tokens, or raw authentication objects in audit events.

## 17. Testing the Custom Consent Service

Tests must verify both domain/entity mapping and how the Authorization Endpoint uses the service. A unit test for a mapper alone does not prove the real consent flow invokes the right bean.

### 17.1. Save/Find Round-Trip

~~~java
@SpringBootTest
class JpaOAuth2AuthorizationConsentServiceTests {

    @Autowired
    OAuth2AuthorizationConsentService consentService;

    @Autowired
    RegisteredClientRepository registeredClientRepository;

    @Test
    void savesAndLoadsConsentByClientAndPrincipal() {
        RegisteredClient client =
            registeredClientRepository.findByClientId("portal-web");

        OAuth2AuthorizationConsent consent =
            OAuth2AuthorizationConsent.withId(
                    client.getId(), "user-42")
                .scope("openid")
                .scope("profile")
                .authority(new SimpleGrantedAuthority(
                    "PERMISSION_invoice.read"))
                .build();

        consentService.save(consent);

        OAuth2AuthorizationConsent loaded =
            consentService.findById(client.getId(), "user-42");

        assertThat(loaded).isNotNull();
        assertThat(loaded.getRegisteredClientId()).isEqualTo(client.getId());
        assertThat(loaded.getPrincipalName()).isEqualTo("user-42");
        assertThat(loaded.getScopes())
            .containsExactlyInAnyOrder("openid", "profile");
        assertThat(loaded.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("PERMISSION_invoice.read");
    }
}
~~~

This is an integration test skeleton. The test database needs the consent schema and a pre-seeded `RegisteredClient`. With a comma-delimited implementation, use authority names without commas or explicitly test your chosen serializer/escaping.

### 17.2. Testing Composite-Key Isolation

Create two consents:

- Same `principalName` with different `registeredClientId`;
- Same `registeredClientId` with different `principalName`.

Then verify `findById` returns the exact authorities for each pair. This test catches bugs that accidentally rely on only part of the composite key.

### 17.3. Testing Updates Replacing the Authority Set

1. Save a consent with `openid`, `profile`, and `email`.
2. Save a new consent with only `openid` and `profile`.
3. Read back the record.
4. Verify `email` is no longer present in `authorities`.

This test catches faulty `save` implementations that automatically union old and new permissions.

### 17.4. Testing Remove and Missing Consent

Verify:

- `findById` returns `null` when no record exists;
- `remove` deletes an existing record;
- Calling `remove` a second time does not break the service if idempotent semantics are chosen;
- `findById` returns `null` after `remove`;
- Removing consent for client A does not delete consent for client B.

### 17.5. Testing RegisteredClient Integrity

Insert a consent row referencing a non-existent `registeredClientId` and call `findById`. The implementation should detect the orphaned record per policy rather than returning a consent that cannot be linked to a valid `RegisteredClient`.

Also test that `save` rejects a non-existent client ID if the service enforces that check.

### 17.6. Testing Transaction Rollback

Trigger an error after writing the parent entity or authority rows but before transaction commit. Verify both the parent record and child rows roll back together. With a normalized child table, a parent must never exist without its authorities, nor should orphaned child rows remain.

### 17.7. Testing Concurrent Updates

Run two transactions that both read the same consent and then write different authority sets. Verify optimistic locking or the conflict policy is enforced. Never allow the final result to become the union of both sets if a user explicitly revoked a permission.

For JPA integration tests, you can use Testcontainers to run against the same database engine as production. H2 is handy for fast tests, but it does not replace verifying dialect behavior, composite keys, locking, and transactions against a real database.

## 18. Testing the End-to-End Authorization Consent Flow

A thorough integration test should execute through the Authorization Server filter chain:

1. Seed a `RegisteredClient` with `authorization_code`, redirect URI, and scopes;
2. Log in as the resource owner;
3. Send an authorization request asking for `openid`/`profile`/`email`;
4. Verify the consent page appears when policy requires it;
5. POST the form with valid `state` and approve only `openid`/`profile`;
6. Verify the consent record contains only the selected authorities;
7. Resend the corresponding authorization request;
8. Verify the consent service is queried and behavior matches policy;
9. Revoke the consent and resend the request;
10. Verify consent is prompted again per policy.

You can use `MockMvc` to send authorization requests and consent POSTs through the real `SecurityFilterChain`. `MockMvc` tests filter/provider wiring; Testcontainers tests the persistence engine. The two test layers complement each other.

### 18.1. Testing State and CSRF

Submit a consent POST with an invalid `state`, missing CSRF token, or mismatched client ID. The request must be rejected. Never let a custom consent controller call `consentService.save` directly before the Authorization Endpoint validates `state`.

### 18.2. Testing Unregistered Scopes

Submit a form attempting to inject a scope that the `RegisteredClient` is not permitted to request. The provider must reject or ignore it per the validation contract; the consent store must never persist scopes outside the request/registration policy.

### 18.3. Testing Partial Consent

The client requests multiple scopes, and the resource owner approves only a subset. Verify:

- Consent persists the exact selected authorities;
- The authorization response obeys the flow and policy;
- Denied scopes do not appear in the consent record;
- Subsequently requesting an additional scope triggers supplemental consent if required.

## 19. Performance and Operations

Consent lookup sits on the authorization request path. A slow database or inconsistent cache can slow down login/SSO or lead to incorrect consent decisions.

### 19.1. Indexing

The composite primary key on `registered_client_id` and `principal_name` supports the service's primary lookup. With an authorities child table, an index/FK on the same two columns supports collection loading and cleanup.

Do not add indexes on `authority` unless there is a specific administrative or analytics query path. Run `EXPLAIN` against your database with production-like data.

### 19.2. Caching

Caching can reduce database reads, but consent changes whenever a user grants or revokes permissions. A stale cache can cause the OP to keep skipping the consent screen or continue trusting revoked permissions.

If caching:

- Keys must include both `registeredClientId` and `principalName`;
- `save`/`remove` must atomically invalidate or update the cache;
- Set TTLs matching consent freshness requirements;
- Never cache across tenants;
- Have a strategy for handling cache outages;
- Measure read-after-write consistency.

Never use per-node local caches without cross-node invalidation.

### 19.3. Retention

Consent does not necessarily have an `expiresAt`. Policy may retain it until the user revokes it, the client is decommissioned, or the account is deleted. If consent expiration exists, store a timestamp/expiry on the custom entity and define how the authorization endpoint handles expired consent.

Do not set a short Redis TTL just to free memory if doing so forces users to re-consent repeatedly.

### 19.4. Metrics and Auditing

Track metrics without PII:

| Metric/Event | Meaning |
|---|---|
| oauth2_consent_find_total | Number of consent lookups |
| oauth2_consent_not_found_total | Consent not yet present |
| oauth2_consent_save_total | Number of consent grants/updates |
| oauth2_consent_remove_total | Number of consent revocations |
| oauth2_consent_store_latency | Persistence latency |
| oauth2_consent_store_errors | Database/cache/external store errors |
| oauth2_consent_conflicts | Concurrent update conflicts |
| oauth2_consent_authority_count | Number of authorities in a record |

Do not use `principalName` or raw authority sets as high-cardinality metric labels. Audit logs can record a pseudonymized principal, client ID, authority delta, actor, timestamp, and correlation ID per policy.

## 20. Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Consent screen always appears | Service always returns `null` or principal key changes | Check composite key and `principalName` |
| Consent screen never appears even though user hasn't granted permissions | Service returns wrong record/client or merges permissions wrongly | Check `registeredClientId` and authorities |
| New scope is not prompted for consent | Implementation unions old authorities or policy is wrong | Check consent comparison and update semantics |
| `save` succeeds but consent disappears after restart | Still using `InMemory` implementation | Check bean wiring and database |
| Node A sees consent, Node B does not | Each node uses a separate store/cache | Shared persistence and cache invalidation |
| Records overwrite across clients | Key uses only `principalName` | Composite key |
| Records overwrite across users | Key uses only `registeredClientId` | Composite key |
| `findById` reports `RegisteredClient` not found | Orphaned consent record or deleted client | Client lifecycle and migration |
| Authorities are truncated | Column length too small | Measure size; use `TEXT`/JSON or child table |
| Authorities split incorrectly | Comma-delimited value contains delimiter | Use JSON/normalized table |
| Consent removed yet tokens remain active | Consent and token lifecycles differ | Revoke authorizations/tokens per policy |
| Two tabs overwrite each other's decisions | Concurrent update without conflict policy | Optimistic locking or serialized updates |
| Consent POST fails CSRF/state checks | Form missing token or mismatched `state` | Template and Authorization Endpoint |
| JPA fails to load authorities | Wrong fetch strategy or mapping | SQL, transaction, and entity mapping |

### 20.1. Diagnostic Workflow

1. Identify the actual `OAuth2AuthorizationConsentService` bean.
2. Check the internal `registeredClientId` and `principalName` from `Authentication`.
3. Inspect the row using a controlled read-only query.
4. Verify the composite key and authority serialization.
5. Check transaction commits and unique constraints.
6. Verify cache invalidation across nodes.
7. Reproduce on a test database clone before modifying production data.

Never log consent form `state` tokens, session cookies, or authentication credentials during diagnostics.

## 21. Production Checklist

1. **Service:** Is the Authorization Server using the right custom `OAuth2AuthorizationConsentService`?
2. **Identity:** Are `registeredClientId` and `principalName` stable and consistent?
3. **Key:** Does storage use the composite key of both client and principal?
4. **Authorities:** Does the serializer preserve all authorities without truncation?
5. **Save:** Does `save` persist the exact snapshot without unintentionally unioning old permissions?
6. **Find:** Does `findById` return `null` when consent is absent and detect orphaned records?
7. **Remove:** Does `remove` delete only the exact client/principal and remain idempotent per policy?
8. **Authorization flow:** Is the Authorization Code provider using the right service?
9. **Consent UI:** Does it POST to the Authorization Endpoint with `state` and CSRF?
10. **Validation:** Are client ID/scopes verified against `RegisteredClient` and the request?
11. **Partial consent:** Are only the authorities actually granted by the user persisted?
12. **Revocation:** Is there a separate policy for existing tokens/authorizations after consent is revoked?
13. **Transactions:** Are parent/authority rows and updates within the same transaction?
14. **Concurrency:** Is there a conflict policy for two concurrent consent updates?
15. **Multi-node:** Are the shared store and cache invalidation consistent?
16. **Tenant:** Is tenant context protected against caller spoofing and key collisions?
17. **Security:** Are DB access, TLS, backups, admin APIs, and auditing protected?
18. **Retention:** Is a consent expiry/deletion policy defined?
19. **Testing:** Are there round-trip, composite isolation, partial consent, revocation, CSRF/state, and cluster tests?
20. **Operations:** Are metrics, alerts, and backup/restore procedures in place?

## 22. Applied Exercises

**Scenario A — Consent lost after restart:** The Authorization Server uses `InMemoryOAuth2AuthorizationConsentService`. A user approved `profile`, but after a deploy they are prompted to consent again. Replace it with a JPA service and verify database persistence.

**Scenario B — Two clients sharing one principal:** `portal-web` and `mobile-app` overwrite each other's consents. Identify the key bug and design a composite primary key.

**Scenario C — Partial consent:** A user grants `openid`/`profile` but denies `email`. Later, the client requests `email` as well. Write a test proving the service does not auto-grant the new scope.

**Scenario D — Revoking consent:** A user deletes consent for a client, yet the old access token is still accepted by the Resource Server. Explain the boundary between consent state and token lifecycle, and propose a revocation policy.

**Scenario E — Concurrent updates:** Two tabs update the same consent; one adds `email`, while the other revokes `profile`. Design optimistic locking and handle the conflict without restoring revoked permissions.

**Scenario F — Authority containing commas:** A custom authority contains a comma, breaking comma-delimited round-trip serialization. Replace the schema with JSON or a normalized authority table.

**Scenario G — Multi-tenancy:** Two tenants share the same `principalName` and client IDs. Why is the service interface alone missing a tenant key? Design namespacing or store partitioning.

**Hints:** A: use a persistent custom bean and verify wiring; B: use `(registeredClientId, principalName)`; C: persist the exact authority snapshot; D: revoke authorizations/tokens separately; E: use `@Version` or serialized updates; F: use JSON/child table; G: namespace client/principal or isolate schemas/stores per tenant.

## 23. Summary

`OAuth2AuthorizationConsentService` manages consent decisions granted to a `RegisteredClient` by a resource owner. The `OAuth2AuthorizationConsent` domain model has a composite identity consisting of `registeredClientId` and `principalName`, plus a `Set<GrantedAuthority>`. The service's three operations are `save`, `remove`, and `findById`.

Spring Authorization Server defaults to `InMemoryOAuth2AuthorizationConsentService` if the application does not provide a service. That implementation suits development/testing; production typically requires JDBC or shared custom persistence. With JPA, you can map the composite key onto an entity, persist the authority set, query through a repository, and build an adapter converting the domain model.

The Authorization Code request provider uses the consent service to read existing decisions; the consent authentication provider saves decisions submitted by the user. The consent page must POST to the Authorization Endpoint with `client_id`, `state`, and selected scopes while maintaining CSRF protection and protocol validation.

A custom implementation must preserve the composite key, persist authority snapshots, handle transactions/concurrency, validate `RegisteredClient`, and ensure read-after-write consistency across nodes. Revoking consent does not automatically revoke already-issued access tokens or refresh tokens; a separate token lifecycle policy is required. With these boundaries clear, consent persistence becomes a durable and testable part of the Authorization Server.

## 24. References

- [Spring Authorization Server 1.5.8 API — OAuth2AuthorizationConsentService](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsentService.html): `save`, `remove`, and `findById` contract.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2AuthorizationConsent`, authorities, and consent service.
- [Spring Authorization Server 1.5.8 — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): schema, entity, repository, and `JpaOAuth2AuthorizationConsentService`.
- [Spring Authorization Server API — OAuth2AuthorizationConsent](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsent.html): builder, `withId`, authorities, and scopes.
- [Spring Authorization Server API — OAuth2AuthorizationServerConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationServerConfigurer.html): configuring `authorizationConsentService`.
- [Spring Authorization Server API — OAuth2AuthorizationCodeRequestAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationCodeRequestAuthenticationProvider.html): authorization request provider and consent-required predicate.
- [Spring Authorization Server API — OAuth2AuthorizationConsentAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationConsentAuthenticationProvider.html): handling consent requests and consent customizers.
- [Spring Data JPA — Repository Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived query methods and repository semantics.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): entity mapping, composite identifiers, transactions, and optimistic locking.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): declarative transaction boundaries.
