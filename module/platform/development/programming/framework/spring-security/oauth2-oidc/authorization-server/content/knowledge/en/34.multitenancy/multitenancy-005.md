# Partitioning Authorization Service and Consent Service by Tenant

## 1. Context and Objectives

In the **Multitenancy** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides you through partitioning OAuth authorization data and consent decisions per tenant when deploying Spring Authorization Server on a shared host or shared service cluster.

This module covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. In a multi-tenant system, the same application can serve multiple organizations, each with its own issuer, clients, users, tokens, and consent policies.

Suppose the platform has two customers:

- Tenant A uses issuer `https://login.example.com/tenant-a`.
- Tenant B uses issuer `https://login.example.com/tenant-b`.
- Both have a client named `billing-portal` and a principal `alice`.
- Tenant A grants scope `invoice.read`; Tenant B grants scope `payment.approve`.

If both tenants write to the same authorization/consent store without tenant-scoped queries, the system can return the wrong authorization, accept another tenant's consent, or revoke the wrong token. Overlapping `client_id` or username values are normal; what is mandatory is that the two tenants' data have clear storage and query boundaries.

After this lesson, you will be able to:

1. Distinguish `OAuth2AuthorizationService` from `OAuth2AuthorizationConsentService`.
2. Select a tenant based on the issuer determined by the Authorization Server.
3. Use `AuthorizationServerContextHolder` to route services by issuer.
4. Build a component registry and delegating services per tenant.
5. Configure `JdbcOAuth2AuthorizationService` and `JdbcOAuth2AuthorizationConsentService` with isolated data.
6. Ensure `RegisteredClientRepository` is routed to the same tenant.
7. Choose between database-per-tenant, schema-per-tenant, or shared-table models.
8. Test for cross-tenant access, token lookup, consent lookup, revocation, and concurrent processing.

## 2. Distinguishing Authorization and Consent

The two services are related during an authorization flow, but store two different types of state.

### 2.1. OAuth2AuthorizationService

`OAuth2AuthorizationService` stores and queries a created OAuth authorization. An `OAuth2Authorization` can contain:

- Internal ID of the authorization.
- ID of the `RegisteredClient`.
- Principal name of the resource owner or client.
- Authorization grant type.
- Scopes approved within that authorization.
- Authorization Code, Access Token, Refresh Token, ID Token, and corresponding metadata depending on the grant.
- Attributes of the authorization request and principal.

This service is used across many protocol flows such as authorization grant processing, client authentication, introspection, token revocation, and related operations.

Example: Alice completes an Authorization Code Flow for the Billing Portal client. The Authorization Server persists the authorization along with the Access Token and potentially a Refresh Token. When the client exchanges a Refresh Token, introspects, or revokes a token, the server looks up this state via `OAuth2AuthorizationService`.

### 2.2. OAuth2AuthorizationConsentService

`OAuth2AuthorizationConsentService` manages a resource owner's consent decision for a `RegisteredClient`. An `OAuth2AuthorizationConsent` contains:

- `registeredClientId`: internal ID of the registered client.
- `principalName`: the user's principal.
- `authorities`: set of authorities the user has approved, typically representing scopes, claims, or permissions.

Consent answers the question: **what permissions has the user granted to this client?** It is not a token and does not hold active/expired Access Token state.

Example: Alice consents to Billing Portal reading invoices. The consent may store authority `SCOPE_invoice.read`. On a subsequent login, the Authorization Server uses the consent to decide whether to display the consent screen again.

### 2.3. Comparison Table

| Aspect | `OAuth2AuthorizationService` | `OAuth2AuthorizationConsentService` |
| --- | --- | --- |
| Subject | A single grant/authorization instance | User's consent decision for a client |
| Primary data | Grant, tokens, principal, granted scopes, attributes | Registered client, principal, approved authorities |
| Where used | Authorization grants, tokens, introspection, revocation | Authorization requests and consent page |
| Typical lookup key | ID or token | `registeredClientId` + `principalName` |
| Contains tokens? | Can contain tokens and token metadata | No |
| Lifecycle | Follows grant/token and revoke/expire policies | Follows consent decision; can span multiple token issuances |
| Tenant partitioning | Must query authorizations within the right issuer | Must query consents within the right issuer |

Never use consent as proof that an Access Token is still active. Likewise, never delete consent simply because an Access Token expires.

## 3. Why Must Both Services Be Partitioned by Tenant?

In Spring Authorization Server, these service interfaces do not include a `tenantId` parameter on their methods by default. For example:

~~~java
public interface OAuth2AuthorizationService {
    void save(OAuth2Authorization authorization);
    void remove(OAuth2Authorization authorization);
    OAuth2Authorization findById(String id);
    OAuth2Authorization findByToken(String token, OAuth2TokenType tokenType);
}

public interface OAuth2AuthorizationConsentService {
    void save(OAuth2AuthorizationConsent authorizationConsent);
    void remove(OAuth2AuthorizationConsent authorizationConsent);
    OAuth2AuthorizationConsent findById(
            String registeredClientId, String principalName);
}
~~~

If only a single global JDBC bean is created, operations read from and write to the same store. When client IDs, principal names, or token identifiers lack a tenant namespace, lookups risk returning data belonging to another organization.

A composite service solves this by:

1. Determining the current request's issuer.
2. Looking up the service implementation registered for that issuer.
3. Forwarding method calls to the matching implementation.
4. Rejecting the request if the issuer is missing or unregistered.

~~~mermaid
flowchart TD
    R["HTTP request to Authorization Server"] --> I["Resolve trusted issuer"]
    I --> C["AuthorizationServerContextHolder"]
    C --> D{"Select service by issuer"}
    D -->|Tenant A| A["AuthorizationService A"]
    D -->|Tenant A| AC["ConsentService A"]
    D -->|Tenant B| B["AuthorizationService B"]
    D -->|Tenant B| BC["ConsentService B"]
    A --> DA["Database / schema A"]
    AC --> DA
    B --> DB["Database / schema B"]
    BC --> DB
    D -->|Missing or invalid| X["Fail closed"]
~~~

Authorization and consent must both be routed to the same tenant. If authorizations are written to database A while consents are read from database B, login flows can return wrong results or fail.

## 4. Determining the Tenant from the Issuer

Spring Authorization Server supports multiple issuers on the same host by using a path component in the issuer identifier. Example:

| Tenant | Issuer | OIDC Metadata |
| --- | --- | --- |
| A | `https://login.example.com/tenant-a` | `https://login.example.com/tenant-a/.well-known/openid-configuration` |
| B | `https://login.example.com/tenant-b` | `https://login.example.com/tenant-b/.well-known/openid-configuration` |

Each tenant's protocol endpoints are built from its corresponding issuer, such as authorization endpoint, token endpoint, JWKS URI, revocation endpoint, and introspection endpoint.

### 4.1. Enabling Multiple Issuers

Support for multiple issuers on the same host is disabled by default. Enable it with `AuthorizationServerSettings`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
~~~

In a multi-issuer configuration, do not set a fixed issuer via `issuer("https://login.example.com")`, as that forces the server onto a single specific issuer. The issuer must be resolved per request and per registered tenant.

### 4.2. AuthorizationServerContextHolder

During request processing, `AuthorizationServerContextHolder` supplies the current `AuthorizationServerContext`. This context holds the issuer resolved by the Authorization Server:

~~~java
AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

String issuer = context != null ? context.getIssuer() : null;
~~~

This issuer is the routing key for composite services. Services do not need to accept a tenant from an arbitrary caller parameter; they obtain the issuer from the current protocol context.

### 4.3. Do Not Trust Request-Supplied Tenant Selectors

Do not treat the following values as proof that the caller belongs to a tenant:

- Client-sent `X-Tenant-ID` headers.
- Query parameter `tenant`.
- Unverified tenant cookies.
- Arbitrary `Host` headers when the proxy/ingress is not configured as trusted.
- A path segment matched solely with `contains` or `endsWith`.

The tenant must be determined from a configured and controlled issuer/host/path. If using forwarded headers, trust only headers overwritten by a trusted reverse proxy. Never allow external clients to spoof `X-Forwarded-Host` or `X-Forwarded-Prefix`.

### 4.4. Exact Issuer Matching

Official examples demonstrate a per-issuer registry that may inspect a tenant suffix. In systems with closely named tenants such as `tenant-a` and `a`, suffix matching is prone to ambiguity. This lesson uses the full issuer URI as the key and performs exact lookup:

`https://login.example.com/tenant-a` maps only to that exact entry.

Never normalize URIs in a way that alters the issuer. Scheme, host, port, and path must stay consistent with the issuer published in discovery and the token `iss` claim.

## 5. Designing TenantPerIssuerComponentRegistry

The registry manages concrete implementations per issuer. Each issuer can register multiple component types, such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `OAuth2AuthorizationConsentService`.

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.Assert;
import org.springframework.util.StringUtils;

@Component
public final class TenantPerIssuerComponentRegistry {

    private final ConcurrentMap<String, ConcurrentMap<Class<?>, Object>> registry =
            new ConcurrentHashMap<>();

    public <T> void register(String issuer, Class<T> componentType, T component) {
        Assert.hasText(issuer, "issuer cannot be empty");
        Assert.notNull(componentType, "componentType cannot be null");
        Assert.notNull(component, "component cannot be null");

        ConcurrentMap<Class<?>, Object> components =
                this.registry.computeIfAbsent(issuer, key -> new ConcurrentHashMap<>());

        Object previous = components.putIfAbsent(componentType, component);
        Assert.state(previous == null,
                () -> "Component already registered for issuer " + issuer
                        + " and type " + componentType.getName());
    }

    public <T> T getRequired(Class<T> componentType) {
        AuthorizationServerContext context =
                AuthorizationServerContextHolder.getContext();

        Assert.state(context != null && StringUtils.hasText(context.getIssuer()),
                "AuthorizationServerContext with issuer is required");

        Map<Class<?>, Object> components = this.registry.get(context.getIssuer());
        Assert.state(components != null,
                () -> "Unknown issuer: " + context.getIssuer());

        Object component = components.get(componentType);
        Assert.state(component != null,
                () -> "Component " + componentType.getName()
                        + " is not registered for issuer " + context.getIssuer());

        return componentType.cast(component);
    }
}
~~~

This registry has three characteristics:

1. The key is the full issuer, not a caller-supplied tenant label.
2. Each component type has a separate implementation per issuer.
3. Missing context, issuer, or component raises an error; there is no fallback to a default tenant.

`putIfAbsent` prevents configurations from being silently overwritten. When updating a tenant is needed, follow a controlled administrative workflow rather than arbitrarily swapping beans serving live requests.

### 5.1. Declaring Issuer Constants

~~~java
final class TenantIssuers {
    static final String TENANT_A = "https://login.example.com/tenant-a";
    static final String TENANT_B = "https://login.example.com/tenant-b";

    private TenantIssuers() {
    }
}
~~~

Issuer constants must match the public issuer values emitted by discovery and tokens. In real environments, load the issuer list from a governed tenant catalog and validate uniqueness before registering components.

## 6. Creating a Delegating OAuth2AuthorizationService

The delegating service solely selects the tenant-specific implementation. It does not access databases directly and does not alter `OAuth2Authorization` semantics.

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;

public final class TenantAwareOAuth2AuthorizationService
        implements OAuth2AuthorizationService {

    private final TenantPerIssuerComponentRegistry componentRegistry;

    public TenantAwareOAuth2AuthorizationService(
            TenantPerIssuerComponentRegistry componentRegistry) {
        this.componentRegistry = componentRegistry;
    }

    private OAuth2AuthorizationService delegate() {
        return this.componentRegistry.getRequired(OAuth2AuthorizationService.class);
    }

    @Override
    public void save(OAuth2Authorization authorization) {
        delegate().save(authorization);
    }

    @Override
    public void remove(OAuth2Authorization authorization) {
        delegate().remove(authorization);
    }

    @Override
    public OAuth2Authorization findById(String id) {
        return delegate().findById(id);
    }

    @Override
    public OAuth2Authorization findByToken(String token, OAuth2TokenType tokenType) {
        return delegate().findByToken(token, tokenType);
    }
}
~~~

Every method invokes `delegate()` within the current context. In particular, `findByToken` must query only the current issuer's store; never iterate across all tenants, as that both leaks token existence and creates a cross-tenant access path.

### 6.1. Why Does findByToken Need Tenant Isolation?

Introspection, revocation, and grant processing endpoints can look up authorizations by token. If a token belonging to Tenant A is sent to Tenant B's issuer, B's service must not find that token. Never try database A as a fallback.

The correct outcome when a token belongs to another tenant is that no authorization exists in the current tenant; the endpoint then returns the corresponding protocol response for its endpoint type.

## 7. Creating a Delegating OAuth2AuthorizationConsentService

The consent service also routes by the current issuer:

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsent;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;

public final class TenantAwareOAuth2AuthorizationConsentService
        implements OAuth2AuthorizationConsentService {

    private final TenantPerIssuerComponentRegistry componentRegistry;

    public TenantAwareOAuth2AuthorizationConsentService(
            TenantPerIssuerComponentRegistry componentRegistry) {
        this.componentRegistry = componentRegistry;
    }

    private OAuth2AuthorizationConsentService delegate() {
        return this.componentRegistry.getRequired(
                OAuth2AuthorizationConsentService.class);
    }

    @Override
    public void save(OAuth2AuthorizationConsent authorizationConsent) {
        delegate().save(authorizationConsent);
    }

    @Override
    public void remove(OAuth2AuthorizationConsent authorizationConsent) {
        delegate().remove(authorizationConsent);
    }

    @Override
    public OAuth2AuthorizationConsent findById(
            String registeredClientId, String principalName) {
        return delegate().findById(registeredClientId, principalName);
    }
}
~~~

Consent lookup takes two parameters: `RegisteredClient` ID and principal name. Both can collide across two tenants. The tenant boundary lies in the implementation selected before performing the lookup, not in hoping ID values are globally unique across the entire system.

### 7.1. Why Not Simply Prefix principalName with the Tenant?

You can construct a namespaced principal name such as `tenant-a:alice`, but that is only a namespacing layer. It does not replace tenant routing for the authorization store:

- The authorization service still must isolate tokens and grants.
- `RegisteredClient` IDs can still collide across stores.
- Revocation and introspection still must be scoped to the issuer.
- Principal naming can vary depending on the identity provider.

Enforce tenant isolation at the persistence/service layer; use principal namespacing as a supplementary measure if your identity model calls for it.

## 8. Routing RegisteredClientRepository to the Same Tenant

`JdbcOAuth2AuthorizationService` and `JdbcOAuth2AuthorizationConsentService` accept a `RegisteredClientRepository` to look up clients when reading/writing data. Therefore, if the authorization/consent services are partitioned by tenant while the repository remains global, data can be paired with a `RegisteredClient` from another tenant.

Create a delegating repository:

~~~java
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

public final class TenantAwareRegisteredClientRepository
        implements RegisteredClientRepository {

    private final TenantPerIssuerComponentRegistry componentRegistry;

    public TenantAwareRegisteredClientRepository(
            TenantPerIssuerComponentRegistry componentRegistry) {
        this.componentRegistry = componentRegistry;
    }

    private RegisteredClientRepository delegate() {
        return this.componentRegistry.getRequired(RegisteredClientRepository.class);
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        delegate().save(registeredClient);
    }

    @Override
    public RegisteredClient findById(String id) {
        return delegate().findById(id);
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return delegate().findByClientId(clientId);
    }
}
~~~

This is a critical dependency: when a JDBC authorization service deserializes an authorization, the injected repository must query `RegisteredClient` within the same tenant context.

In a complete system, other components also need tenant-aware implementations if their data depends on the issuer, especially `JWKSource<SecurityContext>`. While this lesson focuses on the authorization and consent services, you must never implement those two while letting keys or the client repository fall back to a default tenant.

## 9. Configuring Separate JDBC Services per Tenant

Spring Authorization Server provides:

- `JdbcOAuth2AuthorizationService` to persist authorizations via JDBC.
- `JdbcOAuth2AuthorizationConsentService` to persist consents via JDBC.
- `JdbcRegisteredClientRepository` to persist `RegisteredClient` instances via JDBC.

These implementations use `JdbcOperations` and are production-ready persistence choices when schemas, transactions, and dedicated databases are configured as required. Both authorization and consent interfaces are optional in server configuration and default to in-memory implementations; `InMemoryOAuth2AuthorizationService` and `InMemoryOAuth2AuthorizationConsentService` are suitable only for development/testing, never for production or multi-node persistence.

### 9.1. Configuring RegisteredClientRepository

The example below assumes the application already has two `DataSource` beans configured with distinct qualifiers:

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration(proxyBeanMethods = false)
class TenantRegisteredClientRepositoryConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            @Qualifier("tenantADataSource") DataSource tenantADataSource,
            @Qualifier("tenantBDataSource") DataSource tenantBDataSource,
            TenantPerIssuerComponentRegistry registry) {

        registry.register(TenantIssuers.TENANT_A,
                RegisteredClientRepository.class,
                new JdbcRegisteredClientRepository(new JdbcTemplate(tenantADataSource)));

        registry.register(TenantIssuers.TENANT_B,
                RegisteredClientRepository.class,
                new JdbcRegisteredClientRepository(new JdbcTemplate(tenantBDataSource)));

        return new TenantAwareRegisteredClientRepository(registry);
    }
}
~~~

### 9.2. Configuring OAuth2AuthorizationService

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration(proxyBeanMethods = false)
class TenantAuthorizationServiceConfiguration {

    @Bean
    OAuth2AuthorizationService authorizationService(
            @Qualifier("tenantADataSource") DataSource tenantADataSource,
            @Qualifier("tenantBDataSource") DataSource tenantBDataSource,
            RegisteredClientRepository registeredClientRepository,
            TenantPerIssuerComponentRegistry registry) {

        registry.register(TenantIssuers.TENANT_A,
                OAuth2AuthorizationService.class,
                new JdbcOAuth2AuthorizationService(
                        new JdbcTemplate(tenantADataSource), registeredClientRepository));

        registry.register(TenantIssuers.TENANT_B,
                OAuth2AuthorizationService.class,
                new JdbcOAuth2AuthorizationService(
                        new JdbcTemplate(tenantBDataSource), registeredClientRepository));

        return new TenantAwareOAuth2AuthorizationService(registry);
    }
}
~~~

### 9.3. Configuring OAuth2AuthorizationConsentService

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration(proxyBeanMethods = false)
class TenantConsentServiceConfiguration {

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            @Qualifier("tenantADataSource") DataSource tenantADataSource,
            @Qualifier("tenantBDataSource") DataSource tenantBDataSource,
            RegisteredClientRepository registeredClientRepository,
            TenantPerIssuerComponentRegistry registry) {

        registry.register(TenantIssuers.TENANT_A,
                OAuth2AuthorizationConsentService.class,
                new JdbcOAuth2AuthorizationConsentService(
                        new JdbcTemplate(tenantADataSource), registeredClientRepository));

        registry.register(TenantIssuers.TENANT_B,
                OAuth2AuthorizationConsentService.class,
                new JdbcOAuth2AuthorizationConsentService(
                        new JdbcTemplate(tenantBDataSource), registeredClientRepository));

        return new TenantAwareOAuth2AuthorizationConsentService(registry);
    }
}
~~~

These beans share the same registry and the same per-tenant `DataSource` set. Calling `registry.register` during bean initialization registers the concrete implementations; the bean returned to Spring is the composite service.

### 9.4. Configuring Authorization Server to Use Composite Services

Wire the composite services and repository into `OAuth2AuthorizationServerConfigurer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            RegisteredClientRepository registeredClientRepository,
            OAuth2AuthorizationService authorizationService,
            OAuth2AuthorizationConsentService authorizationConsentService)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer
                    .registeredClientRepository(registeredClientRepository)
                    .authorizationService(authorizationService)
                    .authorizationConsentService(authorizationConsentService)
            );

        return http.build();
    }
}
~~~

This snippet illustrates configuring the Authorization Server endpoints. A real application still requires `JWKSource`, an authentication chain, user store, issuer configuration, and appropriate endpoint policies. Ensure no other bean overrides these multi-tenant services.

## 10. Schemas and DataSources per Tenant

Each tenant needs the corresponding schemas for `RegisteredClient`, authorizations, and consents. Spring Authorization Server ships SQL schema scripts inside its artifact:

| Table | Script |
| --- | --- |
| Registered clients | `oauth2-registered-client-schema.sql` |
| Authorizations/tokens | `oauth2-authorization-schema.sql` |
| Consents | `oauth2-authorization-consent-schema.sql` |

These scripts are packaged inside Spring Authorization Server's resources. Example resource paths:

~~~text
org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql
org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql
~~~

Run migrations for each tenant database/schema before putting the tenant into service.

### 10.1. Database-per-Tenant

Each tenant has its own `DataSource`/database:

| Tenant | `RegisteredClient` | Authorization | Consent |
| --- | --- | --- | --- |
| A | DB A | DB A | DB A |
| B | DB B | DB B | DB B |

Advantages:

- Clear data boundaries.
- Independent backup/restore, encryption, retention, and database permissions.
- Default JDBC queries need no extra tenant predicate.
- A query missing a tenant filter cannot accidentally read another database if credentials are separated.

In return, the number of connection pools, migrations, and database resources grows with tenants. Cap total pools and manage `DataSource` lifecycles.

### 10.2. Schema-per-Tenant

Tenants can share the same database instance with one schema per tenant. Each JDBC service must use a connection/`DataSource` pinned to the right schema. Never switch the schema on a pooled connection and forget to reset it before returning the connection to the pool.

If setting schemas per transaction/session, test connection reuse and reset-on-return thoroughly. With PostgreSQL, you can use transaction-local settings or a `DataSource` wrapper bound to a fixed schema; never rely on a session variable persisting across requests.

### 10.3. Shared Tables with tenant_id

A shared database/schema can add a `tenant_id` column to each table. However, Spring Authorization Server's default JDBC implementations do not automatically add a tenant predicate to SQL queries simply because the column exists.

If using shared tables:

- Write custom repositories/services or JDBC implementations with a tenant predicate in every operation.
- Include `tenant_id` in primary keys, unique constraints, and indexes where needed.
- Ensure `findById`, `findByToken`, `remove`, and consent `findById` all filter by tenant.
- Consider database Row-Level Security as a defense-in-depth layer.
- Test database permissions and connection pools so tenant context never leaks across requests.

Never add a `tenant_id` column and continue using the unmodified `JdbcOAuth2AuthorizationService` assuming data is already separated.

### 10.4. Choosing a Storage Model

| Criterion | Database-per-tenant | Schema-per-tenant | Shared tables |
| --- | --- | --- | --- |
| Data isolation | Strong, at the database level | Strong if schema routing is correct | Depends on query filters/RLS |
| Operational cost | Higher | Moderate | Lower |
| Default JDBC services | Usable with dedicated `DataSource` | Usable with schema-scoped `DataSource` | Usually needs custom SQL/services |
| Per-tenant backup/restore | Convenient | Feasible per schema | More complex |
| Scaling to many tenants | Must manage many DBs/pools | Must manage schemas/pools | Easy to centralize, must guarantee isolation |

Choose a model based on compliance requirements, tenant count, isolation guarantees, operations, and scalability. No single strategy fits every platform.

## 11. Authorization and Consent Flows After Tenant Partitioning

Example of Alice logging into Tenant A:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant AS as Authorization Server
    participant C as AuthorizationServerContext
    participant CS as Consent Service A
    participant AU as Authorization Service A
    B->>AS: GET /tenant-a/oauth2/authorize
    AS->>C: Resolve issuer tenant-a
    AS->>CS: findById(clientA, alice)
    CS-->>AS: Consent A or null
    alt User consent required
        AS-->>B: Display consent screen
        B->>AS: User approves scopes
        AS->>CS: save(consent A)
    end
    AS->>AU: save(authorization A)
    AU-->>AS: Persisted
    AS-->>B: Redirect with authorization code
~~~

When the same Alice logs into Tenant B, the issuer context is Tenant B. Composite services switch to Consent Service B and Authorization Service B. Consent A is not used to skip the consent screen at B.

### 11.1. Consent and Authorization Are Not Necessarily Written at the Same Time

Consent is a user decision; authorization is an issuance of permissions/tokens. They have different lifecycles. When the user approves, the consent service saves authorities; when the grant completes, the authorization service saves the authorization and tokens.

Transaction design should verify that both services share the same tenant `DataSource` and transaction manager. If they reside in different databases or use separate transaction managers, do not assume a single ACID transaction spans both. Define behavior when one operation succeeds and the other fails; use retries/idempotency or compensating workflows if business logic requires it.

### 11.2. Client Credentials

With `client_credentials`, an authorization can be created for the client itself without user consent. Even so, `OAuth2Authorization` must still be stored under the issuer's tenant so introspection/revocation/token lookups never cross tenants.

## 12. Tenant Identity in Principal and RegisteredClient

In `OAuth2AuthorizationConsent`, the lookup key is `registeredClientId` and `principalName`. In `OAuth2Authorization`, the record stores `registeredClientId` and `principalName` alongside token state.

One tenant may have:

- Client ID `billing-portal`.
- Internal `RegisteredClient` ID `client-001`.
- Principal `alice`.

Another tenant can use the exact same three values. With database-per-tenant, these values do not conflict. With shared tables, `tenant_id` must participate in every related key and query.

For OIDC subjects, avoid using email as the unique identifier if emails can change or be reused. Use a stable subject within the issuer/tenant, and treat the `(iss, sub)` pair as the namespaced identifier when correlating outside the tenant store.

Never allow a consent record from Tenant A to be reused for Tenant B merely because `principalName` and `clientId` look identical.

## 13. JWKSource and Related Components

Although this lesson focuses on the authorization and consent services, a multi-tenant Authorization Server typically also needs to separate:

- `RegisteredClientRepository`.
- `JWKSource<SecurityContext>`.
- `AuthorizationServerSettings`/issuer resolution.
- User/identity stores if user identities differ by tenant.
- Caches, consent UI, and audit contexts.

If two tenants share a signing key when policy requires independent keys, tokens from one tenant could be verified under the other tenant if the Resource Server fails to check issuer and key policy properly. Typically, each issuer has its own key set and discovery returns the corresponding `jwks_uri`.

`JWKSource` can use the same registry pattern: retrieve the `JWKSet` by issuer and return the keys requested by `JWKSelector`. Never return a default tenant's `JWKSet` when the issuer cannot be resolved.

### 13.1. Resource Servers Must Also Validate the Issuer

Partitioning databases in the Authorization Server is not enough if Resource Servers accept tokens without validating `iss`. Resource Servers must:

- Verify signatures against the issuer's trusted key set.
- Validate the exact issuer.
- Validate audience/resource.
- Enforce per-tenant scope/authority policies.
- Never use a tenant ID from the request body in place of verified token claims.

## 14. Transactions, Caching, and Concurrency

### 14.1. Transaction Managers

If each tenant has its own `DataSource`, JDBC operations for that tenant must use a transaction manager bound to that `DataSource`. If the application uses a routing `DataSource`, tenant routing must be established before the transaction acquires a connection and remain fixed throughout the transaction.

Never switch tenant context mid-transaction. Never allow a connection acquired for Tenant A to be reused to query Tenant B.

### 14.2. Cache Keys Must Include the Tenant

If caching `RegisteredClient`, consent, authorization, or token lookup data, cache keys must include the issuer/tenant:

~~~text
issuer + registeredClientId
issuer + registeredClientId + principalName
issuer + tokenFingerprint
~~~

Do not use `principalName`, `clientId`, or token fingerprint as a global key if the cache can return sensitive authorization data. When a tenant revokes or disables a client, invalidation must be scoped to that tenant and synchronized across nodes.

### 14.3. Threads and Async Tasks

`AuthorizationServerContextHolder` supplies context for the currently executing request. Do not assume this context automatically propagates to executors, message listeners, or background schedulers.

For background jobs such as cleaning up expired authorizations, exporting consents, or batch revocation:

1. Pass the validated issuer/tenant as a job parameter.
2. Verify the tenant exists in the registry/allowlist.
3. Open a transaction and select services/`DataSource` for that tenant.
4. Clear the context upon completion.
5. Never reuse the previous request's tenant from a thread pool.

## 15. Operating the Tenant Lifecycle

### 15.1. Provisioning a Tenant

The tenant creation workflow should:

1. Verify tenant identity, domain, and unique issuer.
2. Create database/schema and appropriate credentials.
3. Run migrations for registered clients, authorizations, and consents.
4. Initialize `RegisteredClientRepository`, authorization service, and consent service.
5. Register components in the registry using the exact issuer.
6. Configure the tenant's `JWKSource` and key material.
7. Verify discovery metadata and protocol endpoints.
8. Run smoke tests confirming data from other tenants cannot be read.
9. Only then expose the issuer in the load balancer/public tenant catalog.

### 15.2. Suspended Tenants

When a tenant is suspended, do not only block web pages. Define policies for authorization requests, token endpoints, introspection, revocation, consent management, and background jobs. Never delete databases or keys simply because a tenant is temporarily suspended.

### 15.3. Offboarding and Data Deletion

When a tenant terminates:

- Stop issuing new authorizations.
- Revoke/expire tokens according to contractual and retention policies.
- Handle consents, authorizations, `RegisteredClient` records, and signing keys per procedure.
- Retain audit records for the mandatory retention period.
- Back up/export as legally required.
- Remove components from the registry after in-flight requests drain.
- Confirm the tenant no longer appears in discovery/catalog.

Never delete registry entries before in-flight requests/transactions finish; likewise, never delete another tenant's data during batch cleanup.

## 16. Testing Tenant Isolation

Tests must prove data never crosses tenant boundaries, even when client IDs, principal names, or token-like identifiers overlap.

### 16.1. Unit Tests for the Registry

Verify:

- Issuer A returns component A.
- Issuer B returns component B.
- Unregistered issuers are rejected.
- Context without an issuer is rejected.
- Two issuers with similar suffixes are not misrouted.
- Registering two implementations of the same component type for the same issuer cannot happen silently.

### 16.2. Integration Tests for Authorization Service

Prepare two independent databases/schemas and create identical values in both:

- Same `RegisteredClient` ID.
- Same Client ID.
- Same principal name.
- Different scopes or token states.

Then verify:

1. Saving an authorization in Tenant A appears only in A.
2. `findById` in B does not return A's authorization.
3. `findByToken` in B does not find A's token.
4. `remove`/revocation in A does not modify B's authorization.
5. Token introspection at Issuer B does not accept A's token.

### 16.3. Integration Tests for Consent Service

1. Save consent A with `SCOPE_invoice.read`.
2. Save consent B with `SCOPE_payment.approve`.
3. With identical `registeredClientId`/`principalName`, querying A returns only A's authorities.
4. Querying B returns only B's authorities.
5. Removing consent A does not delete consent B.
6. An authorization request at B does not skip the consent screen simply because the user consented at A.

### 16.4. Concurrency and Connection Pool Tests

Run Tenant A and B requests concurrently sharing the same application instance and connection pool infrastructure. Repeat many times to catch:

- Uncleaned `ThreadLocal` contexts.
- Routing `DataSource` retaining the previous tenant.
- Transactions opening connections before the tenant is resolved.
- Cache keys missing the issuer.
- Background jobs picking up the wrong context.

## 17. Test Matrix

| # | Scenario | Expected outcome |
| --- | --- | --- |
| 1 | Request for Issuer A | Uses Service A |
| 2 | Request for Issuer B | Uses Service B |
| 3 | Unregistered issuer | Fails closed |
| 4 | Missing `AuthorizationServerContext` | Fails closed |
| 5 | Tenant label shares only a suffix | Not misrouted due to exact issuer matching |
| 6 | Save authorization A | Stored only in A |
| 7 | `findById` authorization A in B | Not found |
| 8 | `findByToken` token A in B | Not found |
| 9 | Remove authorization A | Does not affect B |
| 10 | Introspect token A at Issuer B | Not active / not found |
| 11 | Revoke token A at Issuer B | Does not modify authorization A |
| 12 | Save consent A | Stored only in A |
| 13 | Consent lookup with same client/principal in B | Does not return consent A |
| 14 | Remove consent A | Does not delete consent B |
| 15 | Two tenants with identical `clientId` | Repository returns the right client for the issuer |
| 16 | Two tenants with identical `principalName` | Consents stay isolated |
| 17 | `JdbcAuthorizationService` deserialization | Uses `RegisteredClientRepository` of the same tenant |
| 18 | Consent service deserialization/lookup | Uses the right tenant's repository and database |
| 19 | Concurrent A/B requests | No tenant context leakage |
| 20 | Connection reused after Request A | Request B does not read Schema A |
| 21 | Authorization cache | Cache key includes issuer |
| 22 | Consent cache | Cache key includes issuer + client + principal |
| 23 | Background cleanup | Tenant is passed and verified explicitly |
| 24 | Suspended tenant | Requests handled per suspend policy |
| 25 | Provision new tenant | Active only after migrations/components/smoke tests complete |
| 26 | Remove tenant components | In-flight requests drain; other tenants keep running |
| 27 | Token issuer mismatches endpoint | Resource Server rejects it |
| 28 | `JWKSource` without tenant context | Does not return a default tenant's key |
| 29 | Roll back migration for one tenant | Does not affect other tenants' schemas/databases |
| 30 | Restore backup for Tenant A | Does not overwrite Tenant B's data |

## 18. Troubleshooting Common Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Tenant B's consent appears in A | Global consent service or wrong routing | Check issuer context and registry |
| Tenant A's token introspects at B | Cross-tenant authorization lookup | Ensure `findByToken` uses only the current issuer's service |
| Authorization deserialization error | `RegisteredClientRepository` points to wrong tenant | Use a tenant-aware repository |
| Unknown issuer still succeeds | Fallback to a default tenant exists | Remove fallback and fail closed |
| Similarly named tenant misselected | Suffix/substring matching used | Use exact canonical issuer keys |
| Consent not saved after approval | Consent service points to wrong `DataSource` or missing migration | Check bean routing, schema, and transactions |
| Concurrent requests return wrong data | Context/connection/cache leaked | Check context lifecycle, transactions, and cache keys |
| Valid token signature but wrong issuer | Resource Server does not validate `iss` properly | Configure issuer-specific validation |
| New tenant returns missing table error | Migrations not executed | Run schema migrations before publishing tenant |
| Deleting a tenant affects others | Shared DB cleanup lacks tenant predicate | Check migrations/cleanup and RLS |

## 19. Production Deployment Checklist

1. **Issuer:** each tenant has a canonical, unique issuer.
2. **Resolution:** tenant is determined from a trusted issuer, never from self-declared headers/queries.
3. **Multiple issuers:** enable `multipleIssuersAllowed(true)` and do not force a fixed issuer.
4. **Registry:** map exact issuer to implementation; unknown issuers must fail closed.
5. **Authorization:** dedicated `OAuth2AuthorizationService` per tenant.
6. **Consent:** dedicated `OAuth2AuthorizationConsentService` per tenant.
7. **Registered client:** repository must also be tenant-aware.
8. **JWK:** key sets and signing keys belong to the right tenant.
9. **Persistence:** choose DB/schema/shared-table with explicit tenant filtering.
10. **Schema:** migrations run independently and are versioned per tenant.
11. **Transactions:** transaction manager and `DataSource` routing stay consistent.
12. **Cache:** every cache key includes issuer/tenant.
13. **Async:** background jobs receive an explicit tenant instead of relying on request `ThreadLocal`.
14. **Resource Server:** validate `iss`, `aud`, signature, and per-tenant scopes.
15. **Tests:** include negative cross-tenant access tests and concurrency tests.
16. **Operations:** maintain per-tenant provisioning, suspension, offboarding, backup, and restore.
17. **Observability:** log safe issuer/tenant identifiers; never log tokens, sensitive consent payloads, or secrets.

## 20. Exercises and Self-Assessment Questions

**Exercise A — Distinguishing the two services.** A user revokes consent, yet an old Access Token has not expired. Describe which service stores consent, which stores authorizations/tokens, and what the system must do if old tokens should stop being active.

**Exercise B — Composite service.** Write a registry mapping issuers A/B and implement a delegating `OAuth2AuthorizationService` covering all four methods: `save`, `remove`, `findById`, and `findByToken`.

**Exercise C — Consent isolation.** Create two tenants with the same `principalName` and `registeredClientId`. Write an integration test proving consent authorities are not shared across tenants.

**Exercise D — Storage design.** Compare database-per-tenant, schema-per-tenant, and shared-table with `tenant_id`. Explain why default JDBC services do not automatically filter by `tenant_id`.

**Exercise E — Context spoofing.** A client sends `X-Tenant-ID: tenant-b` while the request issuer is `tenant-a`. Build a threat model and explain why that header must not determine service routing.

**Exercise F — Async cleanup.** A scheduled job cleans up expired authorizations for multiple tenants. Design how to pass the issuer, open a transaction, select services, and guarantee no stale tenant context is reused.

**Exercise G — Full integration.** Configure `multipleIssuersAllowed(true)`, two `DataSource` instances, three delegating components, and `JWKSource`. Test the authorization code flow for both issuers.

**Review questions:**

1. What data does `OAuth2Authorization` store?
2. What decision does `OAuth2AuthorizationConsent` store?
3. Why does consent not imply that a token is still active?
4. Why do the service interfaces omit a `tenantId` parameter?
5. What information does `AuthorizationServerContextHolder` provide?
6. Why should full issuers be used as keys instead of suffixes?
7. When a tenant is not found in the registry, how must the server respond?
8. Why must `RegisteredClientRepository` be partitioned alongside the authorization service?
9. Why must the consent service also be routed by issuer?
10. How do database-per-tenant and schema-per-tenant differ?
11. What changes are required in JDBC queries for a shared-table model?
12. What components must cache keys contain?
13. How should background jobs pass the tenant?
14. How must a Resource Server validate the issuer?
15. What tests should be written to detect cross-tenant token/consent access?

## 21. References

- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html)
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [OAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationService.html)
- [OAuth2AuthorizationConsentService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsentService.html)
- [RegisteredClientRepository API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClientRepository.html)
- [Spring Security — Multi Tenant Security Cheat Sheet (OWASP)](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

**Key takeaway:** `OAuth2AuthorizationService` stores grant/token state; `OAuth2AuthorizationConsentService` stores user approval decisions for clients. In a multi-tenant Authorization Server, both must be routed by the current request's issuer. Use `AuthorizationServerContextHolder` and a registry mapping full issuers to separate implementations; unknown issuers or missing contexts must fail closed. At the same time, `RegisteredClientRepository`, `JWKSource`, `DataSource`, transactions, and caches must all enforce the same tenant boundary. Test with two tenants sharing identical client IDs and principal names to prove authorizations, consents, introspection, and revocation never cross tenants.
