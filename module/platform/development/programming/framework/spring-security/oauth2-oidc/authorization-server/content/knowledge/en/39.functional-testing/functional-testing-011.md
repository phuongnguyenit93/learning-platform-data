# Testing durable persistence, restarts, and multi-instance coordination

An Authorization Server can work fine across a single startup and still fail in production: authorization codes vanish after a restart, revoked refresh tokens are accepted again, consents are not shared between nodes, or two instances both successfully consume the same authorization code. These bugs usually appear when data is kept in local memory, node configurations diverge, or state updates are not protected against concurrent access.

With Spring Authorization Server, functional testing must prove that client, authorization, consent, and token state are persisted durably; that flows can continue across restarts; and that multiple instances can serve the same issuer without creating conflicting state. This lesson focuses on designing fixtures, scenarios, and pass criteria for those tests.

## 1. Distinguishing the state groups to test

Spring Authorization Server uses separate storage abstractions for each group of data. Tests must verify the exact store the application actually uses:

| Component | Role | What to verify |
|---|---|---|
| RegisteredClientRepository | Stores OAuth2 client configuration | Client, redirect URIs, grant types, scopes, and auth methods survive restarts |
| OAuth2AuthorizationService | Stores authorizations and token state | Authorization codes, access tokens, refresh tokens, and metadata are read accurately from another instance |
| OAuth2AuthorizationConsentService | Stores principal consent per client | New, updated, and removed consents are reflected consistently |
| JWKSource / key store | Provides signing keys and public keys | Instances share the same key ring and older tokens still verify |
| HTTP session / Spring Session | Holds browser login state | User sessions are shared if login flows can span multiple nodes |
| Issuer and endpoint config | Defines Authorization Server identity | Discovery metadata, issuer, and endpoints do not drift between instances |

Do not lump all of this data into one "session" concept. Authorizations, consents, and `RegisteredClient` each have their own persistence lifecycle. Browser login sessions may also be managed by Spring Security or Spring Session. Passing an OAuth2 token test after restart does not by itself prove user login sessions are shared across nodes.

## 2. Configuring durable persistence for test environments

In production, applications commonly use JDBC or a custom implementation to store data. Spring Authorization Server provides standard JDBC implementations:

- **JdbcRegisteredClientRepository** for `RegisteredClient`.
- **JdbcOAuth2AuthorizationService** for authorizations and tokens.
- **JdbcOAuth2AuthorizationConsentService** for consents.

Example configuring the repositories sharing one `DataSource`:

~~~java
@Configuration
public class AuthorizationStorageConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository clients) {
        return new JdbcOAuth2AuthorizationService(jdbcTemplate, clients);
    }

    @Bean
    OAuth2AuthorizationConsentService consentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository clients) {
        return new JdbcOAuth2AuthorizationConsentService(jdbcTemplate, clients);
    }
}
~~~

The SQL schemas bundled with Spring Authorization Server must be applied matching the exact library version in use. In real projects, manage schema changes via Flyway or Liquibase so every instance deploys the exact same database structure. Do not let individual nodes run uncontrolled startup scripts on their own.

Integration tests can use Testcontainers to run a real database for the test lifecycle:

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthorizationPersistenceIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // Tests call real endpoints and verify state via repositories.
}
~~~

The example above illustrates provisioning a database for tests. You must still apply the application's migrations/schemas, seed test clients, and configure test-only signing keys. Never use production data or production private keys in Testcontainers.

H2 can be useful for fast checks, but it should never be the sole evidence for multi-instance scenarios. Differences in transaction isolation, row locking, data types, unique constraints, and SQL syntax can cause behavior on H2 to diverge from PostgreSQL, MySQL, or production databases. Run critical persistence and concurrency tests on the exact database engine used in deployment.

## 3. Testing that data survives restarts

A meaningful restart test must keep the database intact between two application runs. If a test wipes the database, recreates the schema, or re-seeds all data before checking, it fails to prove durability.

You can structure the scenario in two phases:

1. Start the application the first time; create the `RegisteredClient`, authorization, consent, and token state to test.
2. Close the application context or stop the process, then start the application a second time against the same database and same issuer/key ring configuration; query the data back and call the relevant endpoints.

Example test skeleton exercising repositories across two independent service instances:

~~~java
@Test
void authorizationSurvivesServiceRecreation() {
    RegisteredClientRepository clients =
            new JdbcRegisteredClientRepository(jdbcTemplate);

    OAuth2AuthorizationService firstService =
            new JdbcOAuth2AuthorizationService(jdbcTemplate, clients);

    OAuth2Authorization authorization = createTestAuthorization(clients);
    firstService.save(authorization);

    // Create a new service while keeping the same database and RegisteredClient.
    OAuth2AuthorizationService secondService =
            new JdbcOAuth2AuthorizationService(jdbcTemplate, clients);

    OAuth2Authorization restored =
            secondService.findById(authorization.getId());

    assertThat(restored).isNotNull();
    assertThat(restored.getRegisteredClientId())
            .isEqualTo(authorization.getRegisteredClientId());
}
~~~

This snippet is an illustrative skeleton; **createTestAuthorization** must construct a valid authorization matching the application's fixtures, including the `RegisteredClient` and matching principal. Creating a new service instance exercises the persistence layer. To test a real restart, also write tests that start two application contexts or two processes sequentially against the same database, not merely two service objects in a single JVM.

Data groups to verify after restart:

- `RegisteredClient` still has the same client ID, grant types, redirect URIs, authentication methods, and scopes.
- Consent still has the same principal, client, and approved authorities.
- Authorizations can be looked up again by ID or matching token.
- Token metadata, lifetimes, invalidated status, and related attributes are read accurately.
- Signing keys and public keys are restored properly, including key IDs.
- Issuer and discovery metadata retain the deployed values.

Do not check only that records exist. Test behavior after restart: authorization codes still work if unexpired and unused; invalidated refresh tokens remain rejected; removed consents do not reappear; older JWTs still verify as long as the corresponding key remains trusted.

## 4. Testing authorization codes and refresh tokens across restarts

An authorization code is a short-lived, single-use credential. A key scenario creates an authorization code before a restart and exchanges it for tokens after the restart. This proves authorization state lives in durable storage rather than instance memory.

Test flow:

1. Seed a `RegisteredClient` supporting authorization code and PKCE.
2. Issue an authorization request with a valid redirect URI, state, and PKCE challenge.
3. Log in the test principal and complete consent per configuration.
4. Capture the authorization code from the redirect URI in the test environment.
5. Stop the application while preserving the database and key ring.
6. Restart with the same issuer and configuration.
7. Send a token request containing the code, redirect URI, and valid PKCE verifier.
8. Verify the token endpoint returns valid tokens and the authorization code cannot be used a second time.

If the authorization code expired during the restart window, rejection is the expected result, yet it does not verify code recovery. Control the clock or use a long enough TTL for that test, while keeping a separate test confirming expired codes are rejected.

For refresh tokens, create a token, perform rotation or revocation per configuration, restart the application, and try reusing it. If rotation is enabled and reuse is disallowed, the old refresh token must remain rejected after restart. The new refresh token must be accepted per its stored lifetime and state.

Do not assume every refresh token configuration behaves identically. Tests must reflect the actual reuse/rotation policy of the client and Authorization Server. If reuse is allowed, test criteria must follow that policy; if rotation is configured, verify the old token is invalidated and the new token is saved.

## 5. Testing consent and revocation across restarts

Consent must be verified via both persistence state and authorization flow outcomes. A consent record still sitting in the database that the application fails to read because of a mismatched `RegisteredClient` ID or principal name is still a functional bug.

Baseline scenarios:

| Scenario | Before restart | After restart |
|---|---|---|
| New consent | User approves scopes for client | Consent store returns the exact authorities |
| Updated consent | Scopes added or removed | Read result reflects the updated authority set |
| Removed consent | Consent removed | Consent does not reappear |
| Revoked token | Authorization saves invalidated state | Introspection or token usage reflects revoked status |
| Deleted authorization | Record removed per business flow | New instance does not find the deleted authorization |

For instance, when a user revokes consent for client A, send a new authorization request from client A after restart and verify the application enforces the consent policy again. If client B has an independent consent, client B's state must remain untouched.

When testing revocation, distinguish expired tokens from invalidated tokens. An expired token may be inactive without proving a revoke operation was persisted. Tests should check the invalidated state or introspection/revocation endpoint behavior matching the design.

## 6. Testing coordination between two instances

In a multi-instance deployment, every node must use the same issuer, `RegisteredClient` data, authorization/consent store, and a consistent key ring. No node may keep its own in-memory copy as the source of truth for OAuth2 state.

Test flow diagram:

~~~mermaid
flowchart TD
    C[OAuth2 Client] --> LB[Load Balancer]
    LB --> A[Authorization Server A]
    LB --> B[Authorization Server B]
    A --> DB[(Shared Database)]
    B --> DB
    A --> K[Shared KMS / Key Ring]
    B --> K
    A --> J[Same Issuer and JWKS]
    B --> J
    R[Resource Server] --> J
~~~

Execute cross-node scenarios:

- Instance A creates an authorization; instance B finds that authorization.
- Instance A issues a token; instance B can introspect or process revocation against stored state.
- Instance A updates consent; instance B reads the change immediately per the system's consistency guarantee.
- Tokens signed by A verify with public keys published/consumed by B and the resource server.
- Tokens signed by B also carry a key ID belonging to the jointly managed key ring.
- Instance A restarts; instance B continues serving previously persisted authorizations.
- Instance B restarts; A's state and behavior remain unaffected.

You can run two application contexts or two processes on different HTTP ports pointing at one test database. Send state-creating requests to A and state-reading or consuming requests to B. This provides far stronger real-world evidence than calling two repositories directly inside one context.

The issuer must stay identical across nodes. In production, instances typically sit behind one hostname/load balancer; never let individual nodes advertise an issuer containing their own local hostname or port. Discovery metadata and JWKS must serve compatible contents regardless of which node handles the request.

## 7. Testing concurrency and single-use guarantees

Multiple instances sharing one database do not automatically guarantee that sensitive operations execute strictly once. Two requests can both read an authorization code in an active state before either finishes saving the consumed state.

Concurrency tests should include:

| Resource | Concurrent scenario | Expected result |
|---|---|---|
| Authorization code | Two instances exchange the same code nearly simultaneously | At most one request succeeds |
| Refresh token with rotation | Two requests use the same old refresh token | Behavior follows reuse/rotation policy; no conflicting state created |
| Consent | Two requests update authority sets | No lost updates outside defined policy |
| Revocation | Two requests revoke the same token | Final state is consistent; audits emit no misleading conclusions |
| RegisteredClient | Client updated while another node reads | Reading node observes consistent config per cache/versioning rules |

Example synchronizing two requests in a test:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

Callable<Response> redeemSameCode = () -> {
    ready.countDown();
    start.await();
    return tokenClient.exchangeAuthorizationCode(code, verifier);
};

Future<Response> first = executor.submit(redeemSameCode);
Future<Response> second = executor.submit(redeemSameCode);

ready.await();
start.countDown();

Response a = first.get();
Response b = second.get();

assertThat(List.of(a.isSuccessful(), b.isSuccessful()))
        .containsExactlyInAnyOrder(true, false);
~~~

This is pseudocode illustrating how to create contention. `tokenClient`, `Response`, and executor management are test fixtures. In a real test, dispatch two independent HTTP requests to two instances and assert protocol responses, typically one successful token response and one invalid grant error. Never use mock repositories, because the goal is testing real database transactions and behavior.

If both requests succeed, investigate how authorization state is saved, transaction isolation, locking, and update conditions. You may need row locks, optimistic locking/versioning, conditional updates, or synchronization suited to the database. Never assume the default JDBC repository automatically guards every application race condition without checking your specific version and implementation.

For refresh tokens, criteria depend on reuse settings. If the old token must be invalidated after rotation, concurrency tests must prove the system never mints two independent refresh branches from the same old token. If reuse is enabled, verify that exact policy and any replay detection required by the application.

## 8. Testing signing keys and JWKS across nodes

Multiple instances must sign and verify tokens using a jointly managed key ring. If each node generates a fresh key pair on startup, tokens issued by node A may fail verification when the resource server or node B knows only a different public key.

Required tests:

1. Start A and B; verify JWKS returns compatible public key sets on both nodes.
2. Have A issue a JWT; verify its signature using the matching public key from JWKS.
3. Have B issue a JWT; verify likewise.
4. Restart A and verify tokens issued by A prior to restart still verify while unexpired and the key remains trusted.
5. Restart B and repeat the check for tokens issued by B.
6. Key rotation in the test environment: the new public key is published before new tokens are signed; the old public key remains published for the required window.
7. After retiring the old key per schedule, verify the resource server refreshes JWKS and handles older tokens per policy.

Do not write tests that only assert the JWKS endpoint returns HTTP 200. Parse the JWK Set, inspect `kid`, `kty`, `use`, and algorithm, and verify signatures of real JWTs. Private keys must never appear in JWKS responses or test logs.

If using a KMS/HSM, integration tests must verify every instance has permission to sign with the right key ID and that published public keys match the keys in the hardware/service. You can use a fake KMS in unit tests, but maintain at least one integration test against a key management mechanism close to production.

## 9. Testing browser sessions under load balancing

Persisting authorizations to a database does not mean user login sessions are shared across nodes. If a login request hits instance A and the next request lands on B, B must restore the session and SecurityContext according to the application architecture.

If the application uses HTTP sessions, test Spring Session configuration and a shared session store such as Redis. If using sticky sessions, also test what happens when the node holding the session is lost and the load balancer routes requests to another node. Sticky sessions can reduce node switching, but they do not replace session recovery when a node fails.

Test scenarios should simulate:

- The user starts the authorization request through A.
- The login flow continues through B.
- SecurityContext, login status, and required data are restored.
- Consent and authorization are written to the shared store.
- After restarting a node, the user can proceed or is prompted to log in again accurately per session policy.

If the system intentionally requires re-login after a node failure, tests must verify a safe flow back to the authorization request, preserving `state`/`nonce` and never issuing tokens for tampered requests. Do not treat forced re-login as a failure if that is the defined security policy.

## 10. Testing database errors, replica lag, and connection recovery

A multi-instance application must handle database failures cleanly. Tests should simulate temporary database unavailability, transaction rollbacks, connection pool exhaustion, deadlocks, and replica lag if the architecture uses read replicas.

Key scenarios:

- Unable to save authorization: the token endpoint never returns a false success when mandatory state has not been persisted.
- Transaction rollback: data is never left half-written, such as a token persisted without invalidation metadata updated.
- Database recovery: the connection pool reconnects and the node resumes operation per retry policy.
- Slow read replica: nodes do not misread stale state right after a revocation or authorization update has committed.
- Deadlock or lock timeout: errors are handled within bounds, logged, and never retried infinitely causing load amplification.
- Schema migration: nodes do not run application versions incompatible with un-upgraded or rolled-back schemas.

For token exchange, refresh, and revocation operations, reading from a lagging replica can produce incorrect security outcomes. If the system uses read replicas, clearly define which operations must read from the primary or require read-your-writes consistency. Tests must measure actual post-commit behavior rather than merely confirming a replica eventually receives data.

Never apply blind retries to token requests. A request may have committed while its response was lost on the network. If a client resends an authorization code or refresh token, the server must enforce single-use credential semantics and replay policy properly. Tests should simulate a timeout after server commit to verify final state and retry behavior.

## 11. Recommended functional test suite

A test suite can be divided into layers to balance speed and confidence:

| Layer | Components | Goal |
|---|---|---|
| Unit tests | Mappers, validators, policy logic, event handlers | Test small rules quickly |
| Repository integration | JDBC services with a real database | Test mapping, queries, transactions, and schemas |
| Restart integration | Two sequential application contexts/processes | Verify data survives restarts |
| Multi-instance integration | Two servers sharing database and key ring | Verify cross-node reads/writes |
| Concurrency tests | Concurrent requests to two instances | Verify single-use codes/refresh tokens and state updates |
| Failure tests | Disrupted database/KMS/network | Verify rollbacks, retries, failover, and recovery |
| End-to-end tests | Client, Authorization Server, and Resource Server | Verify complete OAuth2/OIDC flows |

Minimum test checklist:

- [ ] `RegisteredClient` is read accurately after creating a new application context.
- [ ] Saved, updated, and removed consents remain accurate after restart.
- [ ] Authorization codes created before restart can be exchanged after restart while still valid.
- [ ] Already-used authorization codes cannot be exchanged a second time, even when hitting another node.
- [ ] Refresh token rotation and invalidation states persist across restarts.
- [ ] Tokens revoked on A are observed by B per the committed consistency guarantee.
- [ ] Tokens issued by A verify via JWKS after A restarts.
- [ ] Tokens issued by B are verified by a Resource Server using the same issuer.
- [ ] Two concurrent requests cannot both consume the same authorization code.
- [ ] Two nodes do not overwrite consents or client config in a way that loses updates unintentionally.
- [ ] Browser sessions are shared or recovered per policy.
- [ ] Database errors, rollbacks, replica lag, and reconnects never create invalid authorization state.
- [ ] No private keys, client secrets, authorization codes, or raw tokens appear in test logs.

## 12. Completion criteria and interpreting results

A test is only valuable when it specifies exact inputs, observation points, and expected states. For example, "restart test passed" is too vague. Specify concretely: create consent for principal P and client C, shut down process A, start process B on the same database, query consent, and verify the authority set matches the exact saved values.

When a test fails, classify the root cause by layer:

- **Persistence**: data was not written, mapping failed, or schema is incompatible.
- **Lifecycle**: authorization state was not updated properly when codes were consumed, tokens revoked, or refreshed.
- **Coordination**: nodes read stale caches, used different key rings, or failed to share sessions.
- **Concurrency**: two requests both passed the state check before an update completed.
- **Infrastructure**: connection pool, DNS, load balancer, KMS/HSM, or replica caused the error.

Record the instance ID, request correlation ID, timestamp, database transaction, or internal authorization ID in test reports. Never include raw tokens or credentials in test artifacts. Use isolated test data and clean up after each scenario so tests stay independent of execution order.

When restart, multi-instance, and concurrency tests all pass against a production-like database and key configuration, the development team has proof that the Authorization Server preserves OAuth2/OIDC state across the deployment lifecycle. This catches bugs early that only surface when nodes change, applications restart, or concurrent requests act on a single credential.
