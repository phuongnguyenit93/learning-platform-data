# Sharing Client, Authorization, and Consent Data Across Instances

> **Chapter: Deployment and Scaling.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, focusing on deploying multiple Spring Authorization Server instances serving the same OAuth 2.0/OpenID Connect issuer. The goal is to consistently store and share OAuth client configurations, authorization state, tokens, and consents so requests can pass through any instance while maintaining proper security behavior.

An Authorization Server running on a single machine can start with in-memory data. When deployed across multiple machines behind a load balancer, each JVM has its own memory. If instance A issues an authorization code but the code-exchange request is routed to instance B, B will not find the data if both instances use independent stores. The same problem occurs with newly registered clients, recently granted user consents, recently revoked refresh tokens, and token status needed for introspection.

The core solution is to use a shared store as the authoritative data source. Spring Authorization Server provides JDBC implementations for three key abstractions: **RegisteredClientRepository**, **OAuth2AuthorizationService**, and **OAuth2AuthorizationConsentService**.

## 1. Objectives and deployment scenario

Suppose an Authorization Server has two instances behind a load balancer:

- Instance A receives the authorization request, authenticates the client, and generates an authorization code.
- Instance B receives the token request sent by the client to exchange the authorization code.
- A user may log in on A, while the subsequent request is routed to B.
- An administrator may update a client's redirect URI, scopes, or secret while both instances are running.
- A resource server may call the introspection endpoint to check the state of an opaque token.

These operations must observe the same business state. Both instances must read from and write to the same data store, apply the same issuer rules, and have access to the same token signing key set.

~~~mermaid
flowchart TD
    U[Browser / OAuth Client] --> LB[Load Balancer]
    LB --> A[Authorization Server A]
    LB --> B[Authorization Server B]
    A --> DB[(Shared relational database)]
    B --> DB
    A --> KMS[Shared signing keys / KMS]
    B --> KMS
    A -. optional .-> S[(Shared user session store)]
    B -. optional .-> S
    RS[Resource Server] -->|JWT validation or introspection| A
    RS -->|JWT validation or introspection| B
~~~

The database in the diagram is the shared data source for clients, authorizations, and consents. The signing key store and session store can be separate systems because they manage different types of state.

After this lesson, learners will be able to:

1. Distinguish client data, authorizations, consents, user sessions, and signing keys.
2. Select the appropriate Spring Authorization Server JDBC implementations.
3. Configure multiple instances to use the same DataSource.
4. Organize schemas, migrations, client data seeding, and credential protection.
5. Test authorization code, PKCE, refresh, revocation, and consent flows across multiple instances.
6. Detect consistency bugs, stale caches, race conditions, and configuration drift between nodes.

## 2. Three groups of data that must be shared

Spring Authorization Server separates persistence into abstractions. Each abstraction has its own lifecycle and security implications.

| Abstraction | JDBC Implementation | Managed data | Consequence if stored per node |
|---|---|---|---|
| **RegisteredClientRepository** | **JdbcRegisteredClientRepository** | Client ID, secret, redirect URIs, grant types, scopes, client settings, and token settings | A client created or updated on node A may not exist or may have different settings on node B |
| **OAuth2AuthorizationService** | **JdbcOAuth2AuthorizationService** | Authorization requests, principals, authorization codes, access tokens, refresh tokens, ID tokens, and related metadata | Node B cannot find the authorization code or see token state created or revoked by A |
| **OAuth2AuthorizationConsentService** | **JdbcOAuth2AuthorizationConsentService** | Authorities/scopes a user has approved for a client | Users may be prompted for consent repeatedly or another node may apply stale consent decisions |

### 2.1. Registered client

RegisteredClient describes an OAuth client trusted by the Authorization Server. The data typically includes:

- **id**: stable internal identifier of the record.
- **clientId**: client identifier used in the protocol.
- **clientSecret**: secret encoded with a PasswordEncoder if the client uses a shared secret.
- **clientAuthenticationMethods**: how the client authenticates at the token endpoint.
- **authorizationGrantTypes**: permitted grant types.
- **redirectUris** and **postLogoutRedirectUris**: registered target URIs.
- **scopes**: permissions the client may request.
- **clientSettings**: policies such as requiring PKCE or consent.
- **tokenSettings**: access token and refresh token lifetimes and refresh token reuse policy.

A client is configuration with a longer lifecycle than a single authorization transaction. Client changes require controlled governance, auditing, and consistent visibility across all instances.

### 2.2. Authorization

OAuth2Authorization represents a single authorization grant and the tokens generated from it. Depending on the flow, a record may contain:

- Principal and associated client information.
- Authorization code along with request metadata and expiration timestamp.
- Access token, refresh token, ID token, and per-token metadata.
- Attributes used to resume or validate the authorization flow.
- Token states such as invalidated or expired.

Authorization codes typically have short lifetimes and are single-use. Refresh tokens may live longer and can be rotated or revoked. Sharing authorization records enables another instance to continue processing the exact state created by the first instance.

With self-contained JWT access tokens, resource servers normally verify signatures and claims without querying authorization records on every request. Nevertheless, the Authorization Server still needs to store authorizations to handle refresh, revocation, introspection, and administrative actions. If resource servers must observe revocations near real time, a state-checking mechanism such as introspection or an appropriate denylist is required; a validly signed JWT does not automatically vanish from every resource server simply because the record on the Authorization Server was marked revoked.

### 2.3. Consent

OAuth2AuthorizationConsent stores a user's decision regarding permissions a client is allowed to use. The logical key is typically tied to registeredClientId and principalName. Consent contents may include authorities representing approved scopes.

Consent differs from an authorization transaction:

- Consent represents the user's saved choices for a client.
- Authorization represents a specific grant instance and its tokens.
- A user may have consent that persists across multiple logins or authorization requests.
- An authorization may expire or be revoked while consent remains valid according to policy.

Do not infer that deleting an access token means the user withdrew consent, or that deleting consent automatically revokes all previously issued tokens. Both actions should follow product policy with explicit auditing.

## 3. Why in-memory implementations are unsuitable for multiple instances

Implementations such as InMemoryRegisteredClientRepository, InMemoryOAuth2AuthorizationService, and InMemoryOAuth2AuthorizationConsentService store data in the Java process's local memory. Each instance maintains an isolated dataset.

For example:

1. A user sends an authorization request to node A.
2. A creates an authorization code and stores it in A's memory.
3. The client sends a token request; the load balancer routes the request to node B.
4. B looks up the authorization code in B's memory and does not find it.
5. Token exchange fails even though the authorization code is still valid on A.

Sticky sessions can route some requests back to the same node, but they do not solve data loss during node restarts, autoscaling, failover, or requests routed to another node. Sticky sessions also do not synchronize client configurations or consents.

In-memory implementations remain useful for demos, simple tests, or a single process that does not require durable state. For multi-instance production, use shared persistence.

## 4. Shared storage architecture

A common architecture is having instances share a strongly consistent relational database:

~~~mermaid
flowchart LR
    C[Clients and users] --> LB[Load balancer]
    LB --> N1[AS instance 1]
    LB --> N2[AS instance 2]
    LB --> N3[AS instance N]
    N1 --> DS[(Shared DataSource)]
    N2 --> DS
    N3 --> DS
    DS --> T1[(Registered clients)]
    DS --> T2[(Authorizations)]
    DS --> T3[(Consents)]
~~~

Configuration principles:

- Every instance uses the same database/schema and the same migration set.
- Each instance has its own connection pool pointing to the same database cluster.
- Instances share the same public issuer URL.
- Instances can access the same signing key set or the same KMS/HSM.
- Protocol configuration, token settings, clocks, and trusted proxy settings must be compatible.
- Data must never fall back to local memory when the database fails.

A centralized database is a straightforward and usually appropriate choice for an Authorization Server. If using Redis or a NoSQL store instead, you must fully implement the contracts, transactions/atomicity, TTLs, queries, and consistency semantics required by the services. You cannot swap JDBC for a simple key-value cache and assume all semantics remain intact.

## 5. Preparing the schema and database

Spring Authorization Server provides sample SQL schemas for the three JDBC implementations. Use the scripts bundled with the exact dependency version being deployed, then turn them into migrations managed by Flyway, Liquibase, or your organization's migration tool.

The schema resources are typically named:

- **oauth2-registered-client-schema.sql**
- **oauth2-authorization-schema.sql**
- **oauth2-authorization-consent-schema.sql**

They reside in the resource packages corresponding to Spring Authorization Server's client repository and authorization service. Verify exact locations inside the artifact of the version you use; do not copy schemas from another version without comparing them.

The default tables are typically:

| Table | Contents |
|---|---|
| **oauth2_registered_client** | Registered client configurations |
| **oauth2_authorization** | Authorization and token state |
| **oauth2_authorization_consent** | Principal consents for clients |

JDBC schemas may require data-type adjustments for PostgreSQL, MySQL, Oracle, or SQL Server, especially for long text columns and binary data. Preserve the columns, lengths, and data types expected by the implementation's row mappers. When upgrading Spring Authorization Server, review release notes and updated schemas before running migrations.

### 5.1. Configuring the DataSource

Spring Boot configuration example using environment variables to supply connection details:

~~~yaml
spring:
  datasource:
    url: ${AUTH_DB_URL}
    username: ${AUTH_DB_USERNAME}
    password: ${AUTH_DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
~~~

The values above illustrate configuration structure only. Pool size must be calculated based on total instance count, database connection limits, concurrent requests, and actual query durations. If each node opens 20 connections and 10 nodes are deployed, the database may have to serve up to 200 connections from this service alone.

Never commit database credentials directly to source control. Use a secret manager or your deployment platform's secret injection mechanism; enable TLS for database connections if required by the environment.

### 5.2. Migrations and initial seed data

Execute migrations as a controlled deployment step:

1. Identify the exact Spring Authorization Server version.
2. Compare the sample schema against the existing schema.
3. Create versioned migrations and review them.
4. Run migrations via a deployment job or a designated process.
5. Verify tables, indexes, constraints, and database permissions.
6. Start application instances once the schema is compatible.

Do not let every instance run uncontrolled DDL statements concurrently at startup. Multiple nodes applying migrations simultaneously can cause contention or unpredictable rollouts.

Initial client data should be provisioned via data migrations, authenticated admin workflows, or an idempotent job. Do not create a new random client on every startup. Nodes must reference the same clientId and the same client record.

## 6. Configuring the three JDBC services

Once Spring Boot provides a DataSource and JdbcTemplate, the three JDBC implementations can be configured as follows:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
public class AuthorizationPersistenceConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationService(
                jdbcTemplate, registeredClientRepository);
    }

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationConsentService(
                jdbcTemplate, registeredClientRepository);
    }
}
~~~

JdbcTemplate implements JdbcOperations, which is the type used by the JDBC services. All three beans are instantiated inside each JVM, yet all access the same database. That is what makes data shared across instances.

Inspect application configuration to ensure only one matching bean exists per abstraction. If legacy configuration still creates in-memory implementations, remove it from the production profile or ensure the JDBC beans are injected into the Authorization Server configuration.

Do not create a separate JdbcTemplate pointing to a different database for each service if the goal is a single source of truth. If architecture forces multiple databases, you must explicitly design synchronization, transaction boundaries, and failure handling between them; that is a different distributed systems problem.

## 7. Provisioning and managing RegisteredClient

Example creating a public web client using authorization code and PKCE:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public class ClientProvisioning {

    public void provisionWebClient(
            RegisteredClientRepository repository) {

        RegisteredClient client = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("web-portal")
                .clientName("Web Portal")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.NONE)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://app.example.com/login/oauth2/code/portal")
                .scope("openid")
                .scope("profile")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .refreshTokenTimeToLive(Duration.ofDays(14))
                        .reuseRefreshTokens(false)
                        .build())
                .build();

        repository.save(client);
    }
}
~~~

This is a public client example, so there is no client secret. For a confidential client using a shared secret, encode the secret with a PasswordEncoder before saving:

~~~java
String encodedSecret = passwordEncoder.encode(rawClientSecret);
RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-service")
        .clientSecret(encodedSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();
~~~

Never log raw secrets, never commit secrets to repositories, and never return stored secrets via administrative APIs. The password encoder configured in the Authorization Server must be compatible with how secrets are encoded. When rotating secrets, provide a proper transition period and revocation procedure for old credentials.

### 7.1. Avoiding duplicate seeding when scaling out

If all three instances execute provisioning code on startup, the following can happen:

- Multiple identical client records created with different ids.
- Unique constraint conflicts on client_id.
- One node overwriting settings another node just updated.
- Secrets being regenerated or differing across restarts.

Manage clients through a dedicated provisioning workflow. If using an automated job, the job must use stable identifier keys, existence checks, and reviewed update behavior. Do not generate a new UUID on every startup for the same logical client.

### 7.2. Updating clients in a multi-node environment

When changing redirect URIs, scopes, grant types, or client settings:

1. Verify the change through governance procedures.
2. Write the update to the shared data source.
3. Ensure node caches are refreshed if caching is used.
4. Test new authorization requests across multiple nodes.
5. Monitor for redirect URI errors, invalid client errors, or unauthorized grants.

Client configuration directly impacts security boundaries. Do not allow clients to modify their own redirect URIs or scopes without corresponding administrative policies and authorization.

## 8. Storing and sharing consent

The Authorization Server uses OAuth2AuthorizationConsentService whenever it needs to read or save consent decisions. With the JDBC implementation, consents are persisted to the shared table.

A consent saved by node A will be read by node B through the same service and database. Example illustrating creating a consent record:

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsent;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;

public class ConsentProvisioning {

    public void grantReadConsent(
            OAuth2AuthorizationConsentService consentService,
            String registeredClientId,
            String principalName) {

        OAuth2AuthorizationConsent consent =
                OAuth2AuthorizationConsent.withId(
                                registeredClientId, principalName)
                        .authority("SCOPE_orders.read")
                        .build();

        consentService.save(consent);
    }
}
~~~

In real applications, consent is normally saved through the authorization flow and the application's configured consent page. The snippet above only demonstrates the persistence API; do not grant consent on a user's behalf without valid policy grounds and authorization.

When a user withdraws consent, the application must clearly define whether existing authorizations/tokens issued under that consent must also be revoked. If so, revocation must update the corresponding authorizations via an audited workflow. Simply deleting consent does not guarantee that JWTs already accepted by resource servers are immediately invalidated.

## 9. Authorization codes and PKCE across multiple instances

The authorization code flow is the clearest test for shared persistence:

1. The browser sends an authorization request to the issuer.
2. The load balancer routes the request to node A.
3. A looks up the RegisteredClient, authenticates the user, and checks consent.
4. A generates an authorization code along with request metadata, including the required PKCE data.
5. OAuth2AuthorizationService persists the authorization to the database.
6. The browser/client receives a redirect containing the authorization code.
7. The client sends a token request; the load balancer may route this request to node B.
8. B looks up the authorization in the same database and validates the client, redirect URI, PKCE verifier, expiration, and code status.
9. If valid, B marks the code as used and issues tokens per the flow.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant LB as Load Balancer
    participant A as AS node A
    participant DB as Shared DB
    participant B as AS node B
    participant C as OAuth Client
    U->>LB: Authorization request
    LB->>A: Route to A
    A->>DB: Read RegisteredClient / Consent
    A->>DB: Save OAuth2Authorization + code
    A-->>U: Redirect with authorization code
    U->>C: Deliver callback
    C->>LB: POST token request + code + verifier
    LB->>B: Route to B
    B->>DB: Find authorization by code
    B->>DB: Validate and update code/token state
    B-->>C: Access token / ID token
~~~

PKCE does not replace persistence. PKCE binds the token request to the client that created the code verifier/challenge; the Authorization Server still has to look up the matching authorization and verify the verifier during code exchange. If the code exists only in A's memory, B cannot perform this check.

An authorization code must be consumed exactly once. Under concurrent requests or network retries, verify that the implementation and database prevent issuing tokens twice for the same code. Test real race conditions rather than testing only the sequential happy path.

## 10. Refresh tokens, revocation, and introspection

### 10.1. Refresh token rotation

When a refresh token is used to obtain a new access token, the Authorization Server must read the current authorization, check its status, and update token state. When configured not to reuse refresh tokens, the old token is invalidated and the new token is saved.

With multiple instances, the node receiving the refresh request must see the latest record. If node A has rotated the refresh token but node B reads stale data from a lagging replica or stale cache, the system might accept the old token or erroneously reject the new token.

### 10.2. Token revocation

The revocation endpoint must update token status in the authorization store. Other instances must read that updated status when handling refreshes or introspection. When using JWT access tokens and resource servers verify signatures locally only, updating the database on the Authorization Server does not automatically force resource servers to reject the JWT before expiration.

### 10.3. Token introspection

With opaque tokens, resource servers can call the introspection endpoint. The Authorization Server looks up the token in OAuth2AuthorizationService and returns the active status per protocol. All nodes must see the same token status so introspection results do not depend on which node handled the request.

| Scenario | Requirement for the shared store |
|---|---|
| Token issued on A, introspection on B | B finds the token and returns the accurate status |
| Refresh token rotated on A, next request hits B | B sees the old token invalidated and the new token |
| Token revoked on A, introspection hits B | B reads the revoked status |
| Node A restarts | Authorization and token state remain in the database |
| Resource server verifies JWT offline | Signature, issuer, audience, and expiration must be valid; revocation status needs an additional mechanism if immediate revocation is required |

## 11. Data consistency and concurrency handling

Sharing the same database is necessary, but not sufficient. Consistency models, caching, and concurrent operations must also be considered.

### 11.1. Favoring consistent reads for security data

Authorization codes, refresh tokens, and revocation state have strict read-after-write requirements. After node A updates token state, node B must see that change when handling the next request.

If the database uses primary/replica topology:

- Write to the primary.
- Operations requiring read-your-writes or latest state should read from the primary or a read path with matching consistency guarantees.
- Do not use replicas with replication lag for deciding whether to accept an authorization code or refresh token if doing so could allow an old token to be accepted.
- Measure and alert on replication lag.

Do not default to eventual consistency for every table simply for scalability. Some analytics data can tolerate delay; authorization decisions and token state require stricter semantics.

### 11.2. Race conditions when using authorization codes or refresh tokens

Two requests can hit two instances nearly simultaneously with the same authorization code or refresh token. If both read the unused state before either writes the used state, duplicate processing may occur.

Ensure you:

- Check the behavior of your deployed Spring Authorization Server version and database.
- Test two concurrent requests across two instances.
- Verify update/consume atomicity according to one-time token requirements.
- If implementing custom persistence, use transactions, row-level locks, or conditional compare-and-set operations so only one request wins.
- Include tests ensuring the second request is rejected once the token has been consumed.

Do not assume sticky sessions eliminate race conditions; two concurrent requests can still arrive at the same node.

### 11.3. Transaction boundaries

The JDBC implementations use JdbcOperations and participate in active Spring transactions via Spring's connection management. For application-written administrative workflows, use @Transactional when a logical operation must update multiple related records.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ClientAdministrationService {

    private final RegisteredClientRepository clients;

    public ClientAdministrationService(RegisteredClientRepository clients) {
        this.clients = clients;
    }

    @Transactional
    public void updateClient(RegisteredClient replacement) {
        clients.save(replacement);
        // Write audit records or update related data in the same transaction
        // if those operations share the same transaction manager.
    }
}
~~~

The example above illustrates a transaction for an administrative workflow. Do not wrap an entire HTTP request or an entire authorization flow in a long-running transaction. Long transactions hold connections and locks, increasing contention and reducing availability.

If auditing resides in another system or publishes events to a broker, a database transaction does not automatically span external systems. Design an outbox pattern or appropriate consistency mechanism instead of assuming a distributed transaction exists.

## 12. Caching and cache invalidation

Caching can reduce read queries for RegisteredClient, but JVM-local caches can create diverging configurations across nodes.

For example:

1. Node A caches an old redirect URI.
2. An administrator updates the redirect URI in the database.
3. Node B reads the new URI.
4. Node A keeps using the old URI until its cache expires.

If caching is needed:

- Define clearly what data is cached and its maximum TTL.
- Use a distributed cache or a mechanism that publishes invalidation events to all nodes.
- Handle dropped events, node restarts, and cache warm-up.
- Do not cache authorization/token state in ways that delay visibility of revocations or refresh rotations.
- Monitor cache hits, misses, invalidation delay, and stale data.

Do not treat the database as the source of truth while letting local caches override security decisions with stale data. At moderate scale, reading directly via JDBC can be simpler and easier to operate.

## 13. Other states that must also be synchronized

The three JDBC services solve clients, authorizations, and consents. They do not automatically share all other Authorization Server state.

### 13.1. Signing keys and JWK Set

If each node generates its own RSA key at startup, node A may sign JWTs with key A while node B publishes or uses key B. Resource servers may fail to verify tokens depending on which node issued them.

Instances must use the same aligned key set:

- Store private keys in KMS, HSM, or a protected secret store.
- Share public keys / JWK Set consistently across nodes.
- Keep kid values stable per key.
- Design rotation with a phase for publishing the new key and retaining the old key long enough to verify unexpired tokens.
- Never place private keys in logs, container images, or source control.

The key store is a separate data domain; private keys do not belong directly inside the three authorization tables.

### 13.2. Issuer and protocol configuration

Every node must publish the same issuer URL, such as https://auth.example.com. Tokens issued by A and metadata published by B must identify the same issuer.

Nodes must also be compatible on:

- Authorization Server settings and endpoint paths.
- Grant types, authentication methods, and client policies.
- Token formats, lifetimes, and claim mappings.
- Trusted proxies and redirect URL construction.
- Application versions during rolling deployments.

Do not let individual nodes derive the issuer from internal hostnames or arbitrary client-sent headers. When running behind a reverse proxy, trust forwarded headers only from configured trusted proxies.

### 13.3. User login sessions

User authentication sessions in Spring Security are separate state from OAuth2 authorizations. When a user logs in on A, the cookie/session may be sent to B; B can only restore the session if the session store is shared or the authentication design permits it.

If shared sessions are needed, consider Spring Session with Redis or JDBC. Configure cookies, session serialization, timeouts, and session fixation protection appropriately. Do not confuse the oauth2_authorization table with an HTTP session store.

Sticky sessions can assist certain session-local behaviors, but they do not replace persistence for clients, authorizations, and consents.

## 14. Protecting the database and OAuth data

The database holds information that determines who receives tokens and which tokens remain active. Protect it as a critical security component.

- Use a dedicated database account for the Authorization Server with only the required schema privileges.
- Enable TLS for database connections when appropriate for the environment.
- Encrypt data at rest and backups per policy.
- Never log passwords, raw client secrets, authorization codes, access tokens, refresh tokens, or session cookies.
- Restrict direct access to authorization and consent tables.
- Audit changes to clients, redirect URIs, scopes, consents, and revocation actions.
- Set retention policies for expired authorization/token records.
- Back up the database and test restores periodically.
- Protect database connection secrets using a secret manager.

Do not manually edit token state with ad-hoc SQL during incidents without understanding Spring Authorization Server's mappers and lifecycle. Use audited administrative services/APIs or tested runbooks.

If the database becomes unavailable, the Authorization Server should fail closed for operations requiring reading or writing authorization state. Do not automatically fall back to an in-memory store and continue issuing tokens; doing so creates split state across nodes and can break revocation.

## 15. Deployment and scaling

### 15.1. Rolling deployments

During a rolling deployment, old and new versions may run concurrently. Therefore:

- Migrations must be compatible with both versions throughout the rollout window.
- Avoid renaming or dropping columns while old nodes are still active.
- Prefer expand-migrate-contract: add new structures, deploy compatible code, migrate data, and remove old structures in a later release.
- Verify read/write compatibility across versions sharing the same schema.
- Do not let new nodes write formats old nodes cannot read while both still serve traffic.

### 15.2. Connection pools and database capacity

Increasing the number of Authorization Server instances increases connection pools. Calculate total maximum connections across all nodes, admin jobs, and operational tools. Monitor:

- Active, idle, and pending connections.
- Connection acquisition timeouts.
- Query latency and slow queries.
- Lock waits, deadlocks, and transaction durations.
- CPU, IOPS, storage growth, and replication lag.

Larger pools do not automatically mean higher throughput. When the database is already saturated, adding connections can worsen contention.

### 15.3. Database failover

During database failover, open connections may be severed. Pool configuration must validate connections and reconnect according to platform behavior. In-flight requests may fail; clients need safe retry handling.

Do not blindly retry a token request if it is unknown whether the server already committed token issuance. Client and server design must account for indeterminate outcomes caused by connection drops after commit. Inspect logs/audits and authorization state to handle such cases.

## 16. Multi-instance testing

A test that boots only a single Spring context is not enough to prove data sharing works. Run two application contexts or two independent instances connected to the same test database.

| # | Scenario | Expected outcome |
|---|---|---|
| 1 | Create client via node A, look up client via node B | B finds the same clientId and settings |
| 2 | Update redirect URI via A, read via B | B observes the new value per consistency policy |
| 3 | Issue authorization code via A, exchange code via B | B finds the authorization and processes the valid code |
| 4 | Reuse an already-exchanged code a second time on B | Second request is rejected |
| 5 | Create consent via A, send authorization request to B | B reads the right consent |
| 6 | Withdraw consent per policy | All nodes enforce the updated consent state |
| 7 | Refresh token via A, use old refresh token via B | Old token is rejected once rotation completes |
| 8 | Revoke token via A, introspect via B | B returns inactive status per protocol |
| 9 | Restart A after saving authorization | B can still read the data |
| 10 | Database unavailable | Does not fall back to issuing tokens from local memory |
| 11 | Two concurrent requests using the same authorization code | Only one request succeeds |
| 12 | Two concurrent requests using the same refresh token | Outcome conforms to rotation and replay detection policy |
| 13 | Nodes A and B issue JWTs | Resource server verifies tokens from both nodes |
| 14 | Rotate signing keys | JWK Set and nodes verify tokens during transition |
| 15 | Rolling deployment across two versions | Both versions read/write compatible schema |

### 16.1. Integration testing with two service instances

The following example illustrates testing RegisteredClientRepository backed by a shared database. Two repositories are created independently while receiving the same JdbcTemplate/database:

~~~java
@Test
void clientSavedByOneRepositoryCanBeReadByAnother() {
    RegisteredClientRepository nodeA =
            new JdbcRegisteredClientRepository(jdbcTemplate);
    RegisteredClientRepository nodeB =
            new JdbcRegisteredClientRepository(jdbcTemplate);

    RegisteredClient client = RegisteredClient
            .withId("test-client-id")
            .clientId("test-client")
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.NONE)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("https://client.example.test/callback")
            .scope("openid")
            .build();

    nodeA.save(client);

    RegisteredClient loaded = nodeB.findByClientId("test-client");

    assertThat(loaded).isNotNull();
    assertThat(loaded.getId()).isEqualTo("test-client-id");
}
~~~

In real tests, clean up data between tests, use a production-compatible database engine, and avoid parallel tests sharing the same fixed clientId if conflicts could arise. For authorizations, consents, refresh, and revocation, write service/HTTP-level integration tests with two instances to verify full serialization, transactions, and token lifecycles.

Do not rely on H2 as the sole proof if production uses PostgreSQL or MySQL. Differences in data types, locking, isolation, and SQL dialects may surface only on the production database engine. Testcontainers is one option for running integration tests against the matching engine.

## 17. Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Authorization code created on A, not found on B | A and B use different stores or B points to a different database/schema | Inspect DataSource, schema, and OAuth2AuthorizationService beans |
| Client exists on A but not on B | Using in-memory repository or separate caches | Use JdbcRegisteredClientRepository and check cache invalidation |
| Consent prompted again on another node | Consent service does not use shared database or principal/client ID differs | Check OAuth2AuthorizationConsentService, registeredClientId, and principal |
| Old refresh token still accepted on one node | Replica lag, stale cache, or non-atomic concurrency handling | Enforce consistent reads, remove token state caching, and test race conditions |
| Revoked on A, introspection on B still shows active | Node B reads stale data or does not share the same authorization store | Check database routing, transaction commits, and read paths |
| JWT from A fails verification when metadata/JWK comes from B | Different key pairs or JWK Sets | Share signing keys and check kid |
| Users forced to log in again when requests hit another node | HTTP sessions are not shared | Configure Spring Session or an appropriate session architecture |
| Node restart loses clients or consents | Data still resides in memory | Switch to durable persistence |
| SQL error when saving authorization | Schema version mismatch or incompatible column types | Compare bundled schema with dependencies and migrations |
| Pool exhausted when adding nodes | Total connections exceed database capacity | Recalculate pools, pace rollouts, and optimize queries |
| Two exchanges of the same authorization code both succeed | Consumption is not protected against race conditions | Verify atomic updates/locking and add concurrency tests |
| New node errors reading records created by old node | Schema or serialized data incompatibility during rolling deploy | Use backward-compatible migrations and check data formats |

### 17.1. Pre-production checklist

- [ ] All three abstractions (client, authorization, and consent) use JDBC/shared persistence.
- [ ] All instances point to the same database/schema.
- [ ] Schema is created via migrations matching the Spring Authorization Server version.
- [ ] No in-memory implementations remain in the production profile.
- [ ] Clients are provisioned in a controlled manner, not randomly created on each startup.
- [ ] Client secrets are encoded with an appropriate PasswordEncoder.
- [ ] Database credentials are managed by a secret manager.
- [ ] Read paths for authorization codes, refreshes, and revocations satisfy read-your-writes requirements.
- [ ] Concurrent authorization code and refresh token tests exist.
- [ ] Client caching has invalidation; token state cannot go stale.
- [ ] Signing keys/JWK Set are shared and have a rotation plan.
- [ ] All nodes use the same issuer and compatible protocol settings.
- [ ] HTTP sessions are shared if login flows require it.
- [ ] Backups, restore tests, connection pool monitoring, and query latency monitoring are in place.
- [ ] Runbooks exist for database failover or unavailability.
- [ ] Resource servers have a strategy aligned with JWT revocation requirements.
- [ ] Auditing is enabled for client changes, consents, and revocations.

## 18. Self-assessment questions

1. Why is InMemoryOAuth2AuthorizationService unsuitable when authorization requests and token requests can arrive at different instances?
2. Which three categories of data do RegisteredClientRepository, OAuth2AuthorizationService, and OAuth2AuthorizationConsentService manage?
3. Why is consent not synonymous with an authorization or token?
4. Which tables do the three default JDBC implementations use?
5. Why must every instance share the same DataSource?
6. Do sticky sessions solve data loss when a node restarts?
7. Why do authorization codes and refresh tokens require read-after-write consistency?
8. What security error can replication lag cause when processing tokens?
9. Why can a local cache for client settings cause two nodes to enforce different policies?
10. When an authorization code is used concurrently across two nodes, what must be tested?
11. Why must signing keys and the JWK Set also remain consistent across instances?
12. How does an HTTP session differ from OAuth2Authorization?
13. Is a JWT access token automatically invalidated immediately when its authorization record is revoked?
14. What must be done to keep schemas compatible during a rolling deployment?
15. When the database is unavailable, why should you not fall back to in-memory persistence?

## References

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, OAuth2Authorization, consent abstractions, and services/repositories.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): Authorization Server configuration and foundational components.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization, token, introspection, and revocation endpoints.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring Authorization Server components.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate, JdbcOperations, and database access.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries and @Transactional.
- [Spring Session](https://docs.spring.io/spring-session/reference/): sharing HTTP sessions across multi-instance deployments.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT and JWK Set verification.
