# Completing Architecture, Configuration, Operations, and Incident Troubleshooting Documentation

This lab brings together all parts of the module into a deployable and operable Spring Authorization Server system. The objective is to produce a technical documentation set sufficient for development, security, and operations teams to share a clear understanding of the architecture, configure components accurately, execute routine operations, and troubleshoot incidents based on evidence.

The overarching scenario is an Authorization Server issuing OAuth 2.0 access tokens and OpenID Connect ID Tokens for web applications. The server runs behind a TLS-terminating reverse proxy, uses PostgreSQL to store clients, authorizations, and consents, uses independently managed persistent signing keys, and can scale horizontally across multiple instances. Clients use the Authorization Code Flow with PKCE. Features such as refresh tokens, revocation, introspection, UserInfo, and logout are enabled according to system needs.

The complete documentation needs four tightly linked sections:

1. **Architecture:** components, trust boundaries, request flows, and data dependencies.
2. **Configuration:** issuer, clients, endpoints, database, signing keys, proxy, TLS, and secret management.
3. **Operations:** deployment, migrations, health checks, monitoring, backups, rotations, and rollouts.
4. **Incident troubleshooting:** symptoms, evidence to collect, common root causes, and safe recovery steps.

## 1. Defining System Goals and Scope

Before writing documentation, clearly state who the system serves and which protocols it supports. Operational documentation must never implicitly assume that every OAuth/OIDC feature is enabled.

Example scope for the lab:

| Item | Lab Decision |
|---|---|
| Role | OAuth 2.0 Authorization Server and OpenID Provider |
| Issuer | https://auth.example.com |
| Primary grant | Authorization Code |
| Authorization code protection | PKCE, preferring S256 |
| Clients | Confidential web clients and public clients if applicable |
| Tokens | JWT access tokens; ID Tokens when OIDC is enabled |
| Persistence | PostgreSQL for RegisteredClient, OAuth2Authorization, and consent |
| Session | HTTP session; Redis when sharing sessions across multiple instances |
| Signing keys | RSA or EC per selected algorithm, private keys stored in secret manager/KMS |
| Ingress | TLS-terminating reverse proxy/load balancer |
| Observability | Application logs, audit events, health checks, and metrics |
| Deployment | Single instance initially; horizontally scalable when state is shared |

This is an illustrative profile. When finalizing documentation for a real environment, replace all example values with actual domains, grants, databases, token formats, algorithms, client types, and policies. If the system disables an endpoint, explicitly document that it is out of operational scope.

### Questions the Documentation Must Answer

- What is the official issuer? Is there a single fixed issuer or multiple issuers per tenant?
- Which clients are registered? Who is authorized to create, modify, disable, or rotate secrets?
- Which grant types, scopes, redirect URIs, and client authentication methods are allowed?
- What are the access token and refresh token lifetimes? Is refresh token rotation or reuse enabled?
- Are tokens JWTs or opaque? Do resource servers verify signatures or call introspection?
- Where are authorizations, consents, and clients stored? Must sessions be shared across instances?
- How are signing keys generated, stored, distributed, rotated, and revoked?
- Who has access to actuator endpoints, audit logs, the database, and the secret manager?
- How does the system degrade or fail when the database, key store, Redis, or ingress experiences an outage?
- What evidence must be preserved during a security incident?

## 2. Describing Architecture and Trust Boundaries

A reference deployment topology:

~~~text
                    Internet
                       |
              HTTPS auth.example.com
                       |
              +------------------+
              | Reverse Proxy /  |
              | Load Balancer    |
              | TLS termination  |
              +------------------+
                       |
             private network only
                       |
          +------------+------------+
          |                         |
  +---------------+         +---------------+
  | Authorization |         | Authorization |
  | Server node A |         | Server node B |
  +---------------+         +---------------+
          |                         |
          +------------+------------+
                       |
             +-------------------+
             | PostgreSQL        |
             | clients, grants,  |
             | consent, tokens   |
             +-------------------+
                       |
             +-------------------+
             | Secret Manager /  |
             | KMS / Key Store   |
             +-------------------+

       Optional shared session: Redis
       Monitoring: metrics, logs, audit events
~~~

Each component has distinct responsibilities:

| Component | Responsibility | Boundary to Protect |
|---|---|---|
| Reverse proxy | TLS, host allowlist, header normalization, routing | Only the proxy may call backends; client-sent headers must be stripped/overwritten |
| Authorization Server | Authorization endpoint, token endpoint, metadata, OIDC | Security filter chains, client policies, issuer, token signing |
| PostgreSQL | Registered clients, authorizations, consents | Network isolation, dedicated credentials, backups, and migrations |
| Key store/KMS | Private signing keys and key lifecycle | Least privilege, auditing, rotation, recovery |
| Redis (if present) | Shared HTTP sessions or caching | ACLs, network isolation, TTLs, failover |
| Resource Server | Verifies access tokens and enforces permissions | Issuer, audience, signature, expiration, scopes |
| Monitoring | Health, metrics, logs, audits | Never collect tokens, secrets, or unnecessary personal data |

Do not treat PostgreSQL as the default signing key store. Authorization data and private signing keys have different lifecycles, access rights, and recovery procedures. Separating application data read/write privileges from private key usage permissions limits blast radius if one component is compromised.

### Authorization Code Flow

~~~text
Browser / OAuth2 Client
       |
       | 1. Authorization request + state + PKCE S256
       v
Authorization Server
       |
       | 2. Authenticate user / collect consent
       |
       | 3. Redirect with authorization code
       v
Registered redirect URI
       |
       | 4. Token request + code_verifier
       v
Token Endpoint
       |
       | 5. Validate client, code, redirect and PKCE
       | 6. Persist authorization and issue tokens
       v
Access Token + ID Token (+ refresh token by policy)
       |
       v
Resource Server / OIDC Client
~~~

Documentation must clarify that state and nonce are verified on the client/OIDC relying party side; PKCE is bound to the authorization code; redirect URIs must match client configuration; and access tokens and ID Tokens serve different purposes. Never include real tokens, codes, or secrets in diagrams or sample logs.

## 3. Completing Spring Authorization Server Configuration

Configuration is managed per environment, with non-sensitive values in application configuration and secrets supplied via a secret manager or platform security mechanism. Never commit database passwords, client secrets, or private keys to the repository.

### Application Configuration

Example application-prod.yml:

~~~yaml
server:
  port: 9000
  forward-headers-strategy: framework
  shutdown: graceful

spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/authorization
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Datasource username and password are supplied via SPRING_DATASOURCE_USERNAME and SPRING_DATASOURCE_PASSWORD environment variables or secret injection. Pool numbers are only starting values for the lab. Real sizing must account for instance count, PostgreSQL max connections, concurrency, query duration, and platform connection limits. With N instances and max pool size P, theoretical total connections can approach N × P, before counting jobs and other applications.

Do not expose all actuator endpoints to the Internet. Expose only required endpoints, protect them with network policies or appropriate authentication, and restrict health detail visibility. Health endpoints should serve orchestration platforms; metrics endpoints should be accessible only to internal monitoring systems.

### Stable Issuer Configuration

For an Authorization Server with a single public domain, configure the issuer explicitly:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

The issuer is the Authorization Server's identifier. It must be consistent across metadata and tokens carrying the iss claim. Never use arbitrary Host or X-Forwarded-Host headers from requests as the issuer. For multi-tenant setups, map each proxy-validated host to an allowlisted issuer and verify consistency across metadata, tokens, and endpoints.

After deployment, verify discovery from a client's perspective:

~~~bash
curl -fsS https://auth.example.com/.well-known/openid-configuration
~~~

If OIDC is enabled, verify issuer, authorization_endpoint, token_endpoint, jwks_uri, and userinfo_endpoint if present. If the system uses only OAuth metadata, verify the endpoint metadata matches configuration.

### RegisteredClient Configuration

Register clients through a controlled administrative process. Each client requires:

- A stable and unique Client ID.
- A client authentication method suited to the client type.
- Permitted grant types.
- Exact redirect URIs.
- Allowed scopes.
- PKCE and consent requirements per policy.
- Token lifetimes and refresh token policy.
- Owner, environment, creation date, expiration date, or review schedule.

Example confidential web client configuration:

~~~java
RegisteredClient webClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("web-portal")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri(
                "https://portal.example.com/login/oauth2/code/auth")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .refreshTokenTimeToLive(Duration.ofHours(8))
                .reuseRefreshTokens(false)
                .build())
        .build();
~~~

This is an example object instantiation to illustrate policy. In production, store RegisteredClients in a persistent repository such as JdbcRegisteredClientRepository and provision them via migrations or an idempotent administrative workflow. Never generate new random client IDs on every application startup. Never use client_secret_basic for public clients; public clients cannot keep secrets confidential and require PKCE.

JDBC repositories and services can be configured as follows:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcTemplate jdbcTemplate) {
    return new JdbcRegisteredClientRepository(jdbcTemplate);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(
            jdbcTemplate, registeredClients);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationConsentService(
            jdbcTemplate, registeredClients);
}
~~~

Schemas must be installed via versioned migrations. Use the exact schema corresponding to the running Spring Authorization Server version. Test migrations on both an empty database and the previous release's schema before going to production.

### SecurityFilterChain Configuration

Authorization Server endpoints and user login application routes may need two clearly ordered filter chains. The sample below illustrates modern configuration; configurer APIs may differ depending on the pinned Spring Authorization Server version, so cross-check with your dependencies:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                    authorizationServer.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

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
~~~

This is an illustrative skeleton, not a complete configuration for every system. You must integrate authentication providers, user stores, CSRF policies, exception handling, and public endpoints as required. Do not disable CSRF application-wide just to make authorization requests work. Check filter matchers so login, error, static resource, and health probe endpoints are handled per policy.

### Signing Keys and JWKS

Key documentation must specify:

- Accepted algorithms and key sizes.
- Where private keys are stored and which service identities are permitted to use them.
- How public keys are published via JWKS.
- Naming rules for kid and active/next/retired states.
- Overlap duration during rotation.
- How long old keys are retained to verify still-valid tokens.
- Emergency rotation and compromised-key revocation procedures.
- Key backup/restore or regeneration procedures per policy.

Never generate a new random RSA/EC key pair on every application startup. Doing so invalidates previously signed tokens after a restart. In production, retrieve keys from a KMS, HSM, or secret manager; restrict private key usage rights and audit all sensitive operations. Only public keys may be published in JWKS.

## 4. Configuring the Reverse Proxy and Network

Assume Nginx is the point receiving HTTPS directly from clients:

~~~nginx
server {
    listen 443 ssl;
    server_name auth.example.com;

    location / {
        proxy_pass http://authorization-server:9000;

        proxy_set_header Host auth.example.com;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host auth.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
    }
}
~~~

The example assumes Nginx is the direct edge proxy. If a load balancer or CDN sits in front of it, configure real IP extraction only after identifying allowed hop CIDRs and the headers they generate. The edge proxy must strip or overwrite client-supplied forwarded headers. Backends must accept traffic only from designated internal proxies.

Network checks to include in the runbook:

- Security groups/firewalls allow ingress only from the proxy.
- PostgreSQL allows connections only from application subnets.
- Redis allows connections only from required services.
- Management ports are not exposed to the Internet.
- TLS certificates match expected hostnames and are renewed before expiry.
- DNS, load balancer health checks, and routing all point to the intended endpoints.

If the proxy rewrites paths, document the exact external prefix and internal context path. Check discovery, redirects, and JWKS to avoid missing or duplicated path prefixes.

## 5. Managing Configuration by Environment

Separate configuration into three groups:

| Group | Examples | Where Managed |
|---|---|---|
| Non-sensitive | Ports, issuer, pool sizes, endpoint paths, feature flags | Versioned config or deployment config |
| Secrets | DB passwords, client secrets, API credentials | Secret manager or secret injection |
| Cryptographic keys | Private signing keys, encryption keys | Access-controlled KMS/HSM/keystore |

Never reuse the same client secrets, signing keys, or database passwords across dev, test, staging, and production. Never place secrets into Docker images, source control, command lines captured in shell history, or log pipelines.

When changing configuration, record:

- Old and new values (for secrets, record only version/fingerprint, never the secret value).
- Affected environments and instances.
- Person or automation executing the change.
- Effective timestamp.
- Rollback plan.
- Post-change verification.

Issuer, signing algorithm, token lifetime, client redirect URI, and grant type settings are security-impacting configurations. They require corresponding reviews and regression tests.

## 6. Application Deployment and Startup

The deployment process can be broken into steps:

1. Verify image, commit SHA, dependency versions, and SBOM per organizational process.
2. Verify secret references and KMS/secret manager permissions.
3. Verify database connectivity and migration state.
4. Run migrations in a controlled single step before rolling out new instances.
5. Start instances and wait for readiness.
6. Verify discovery, JWKS, and public endpoints.
7. Run smoke tests with a test client.
8. Ramp traffic according to the rollout strategy.
9. Monitor token errors, logins, database pool, latency, and audit events.
10. Complete rollout or roll back based on defined criteria.

### Readiness and Liveness

Liveness answers whether the application is alive to keep running or needs a restart. Readiness answers whether the instance can accept traffic yet. Do not let a transient dependency failure cause liveness to continuously restart every instance when restarting cannot fix the problem.

Readiness can check essential dependencies such as the datasource, depending on policy. If PostgreSQL is unavailable and the Authorization Server cannot process authorizations/tokens, the instance should not receive traffic. However, design health indicators to avoid cascading failures while the database is recovering.

With Spring Boot Actuator, configure health probes and endpoints matching the orchestration platform. Restrict health response details so hosts, schemas, usernames, or internal structure are never exposed.

### Graceful Shutdown

Enable graceful shutdown and set an appropriate drain window. Before stopping an instance:

- The load balancer stops sending new requests to the node.
- In-flight requests are allowed to finish within the timeout window.
- Connection pools close according to the application lifecycle.
- Shared authorizations/sessions are not wiped when a node stops.
- New nodes must be ready with the same issuer, compatible database schema, and required signing key set.

Authorization codes and tokens must share persistence/issuer/key configuration by architecture. Never rely on sticky sessions to mask in-memory-only authorization state when the system needs horizontal scaling.

## 7. Day-to-Day Operations

The runbook must distinguish routine operations, high-risk changes, and incidents.

| Task | Execution | Post-Action Verification |
|---|---|---|
| Service check | Health, readiness, synthetic login | Instances receive traffic and endpoints operate |
| Metadata check | Read discovery and JWKS | Issuer, endpoints, and public keys are accurate |
| Provision client | Reviewed administrative process | Grants, redirects, scopes, and auth methods are accurate |
| Disable client | Disable/rotate credentials per procedure | Client can no longer obtain new tokens |
| Database check | Connection pool, slow queries, replication/backup status | No connection exhaustion or migration drift |
| Key check | Active kid, JWKS, expiry, and KMS audits | New tokens signed by expected key; old keys remain during overlap |
| Audit check | Logins, consents, token failures, and admin changes | Events have correlation IDs and contain no secrets |
| Capacity check | CPU, memory, request rate, DB connections | Sufficient headroom and within quotas |

### Provisioning and Revoking Clients

The client creation workflow must confirm owner identity, client type, redirect URIs, grant types, scopes, authentication method, lifetime, and environment. For confidential clients, deliver secrets via a one-time secure channel or secret delivery mechanism. Store only hashed secrets using mechanisms supported by Spring Authorization Server and internal policy.

When revoking a client:

1. Confirm client ID and owner.
2. Disable or delete credentials per policy.
3. Revoke related authorizations/refresh tokens if required.
4. Verify new tokens can no longer be issued.
5. Verify resource servers reflect revocation according to token model (JWT vs. opaque) and caching.
6. Record an audit event, actor, and reason.

For already issued JWT access tokens, deleting a client does not automatically invalidate token signatures. Resource servers may continue accepting JWTs until expiration unless an appropriate revocation/denylist mechanism exists. Documentation must state this boundary clearly.

## 8. Monitoring, Logging, and Auditing

Monitoring must answer three questions: is the service available, is the protocol functioning properly, and is there anomalous behavior requiring investigation?

### Metrics

Track these metric categories:

- HTTP request rate, latency, and error rate by endpoint.
- Successful/failed authorization request counts.
- Token issuance and token endpoint failures by error category.
- Login/consent failures and failed client authentication counts.
- JVM heap, garbage collection, thread pools, and CPU.
- HikariCP active/idle/pending connections and connection timeouts.
- Database query latency, connection counts, lock waits, and replication lag if applicable.
- Redis latency, connections, and evictions if used.
- KMS/key service latency and access errors.
- Readiness, restart counts, and rollout status.

Avoid putting high-cardinality client IDs, usernames, tokens, or authorization codes into metric labels. Use aggregate metrics and correlation IDs in logs for detailed investigation.

### Structured Logging

Logs should include timestamp, severity, service name, environment, instance ID, trace/correlation ID, endpoint category, and outcome. Example:

~~~json
{
  "timestamp": "2026-11-16T10:15:30Z",
  "level": "WARN",
  "service": "authorization-server",
  "environment": "production",
  "event": "token_request_rejected",
  "error": "invalid_grant",
  "client_id": "web-portal",
  "correlation_id": "req-7f2a"
}
~~~

The example contains no codes, tokens, secrets, or cookies. In practice, log client IDs only if policy permits; usernames and subjects typically require minimization or pseudonymization.

### Audit Events

Auditing focuses on security-significant events:

- Clients created, updated, disabled, or having secrets rotated.
- User login successes/failures.
- Consents approved, denied, or revoked.
- Authorization code or token requests rejected by error category.
- Refresh token rotation/replay and revocation.
- Signing keys transitioning states or rotated.
- Changes to issuer, endpoints, or security policies.
- Administrative access and configuration changes.

Audit events require actor/service identity, action, target reference, outcome, timestamp, and correlation ID. Never store intact tokens or private keys. Define retention, access controls, integrity protection, and export workflows per policy.

## 9. Backup, Recovery, and Availability

Backups must cover all data required to restore Authorization Server behavior. Backing up PostgreSQL without a plan to recover signing keys can render existing tokens unverifiable. Backing up keys without authorization/client data is also insufficient to restore the full service.

| Data / Dependency | What to Protect | Recovery Verification |
|---|---|---|
| Registered clients | Client ID, grants, redirects, scopes, secret hashes, and settings | Clients are retrieved and policies are intact |
| Authorizations | Active code/token states and metadata | Tokens/introspection/revocation behave per policy |
| Consents | User-approved scopes | Consents are read back and enforced |
| Signing keys | Private keys via KMS/HSM backup policy; public key/JWKS metadata | Old tokens still verify while keys remain trusted |
| Application config | Issuer, endpoints, token policies, and security settings | New instances have consistent configuration |
| Session store | Active sessions if recovery is required | Users are handled per policy after restore |
| Audits/logs | Events needed for investigation and compliance | Retrievable per retention policy |

Define RPO (acceptable data loss) and RTO (target recovery time). Run restore drills periodically in an isolated environment. Verify migrations, database permissions, issuer, key access, JWKS, and smoke tests after recovery.

Never restore a production snapshot into a less-protected environment without a sensitive-data sanitization process. Apply access controls and encryption to backups equivalent to the source data.

## 10. Rotation and Security Changes

### Signing Key Rotation

A safe rotation procedure uses overlap:

1. Generate the new key in KMS/HSM or the key manager.
2. Publish the new public key in JWKS with a unique kid.
3. Wait for clients/resource servers to refresh JWKS or for cache windows to expire.
4. Switch the Authorization Server to sign with the new key.
5. Keep the old public key long enough to verify still-valid old tokens.
6. After token lifetimes and overlap expire, stop publishing the old key per policy.
7. Verify new tokens use the new key and old tokens are handled properly.
8. Update audit records and key inventory documentation.

If a private key is compromised, treat it as an emergency response: assess signed tokens, stop using the affected key, publish updated key status, coordinate trust updates with resource servers/clients, and consider revoking tokens/sessions. Exact steps depend on JWKS caching behavior and token formats.

### Client Secret Rotation

- Generate a new secret and deliver it to the client via a secure channel.
- Verify the client has switched to the new secret.
- Disable the old secret after the scheduled overlap window.
- Verify authentication fails with the old secret.
- Record timestamp, owner, and credential version.

Do not keep two valid secrets indefinitely if policy forbids it. If the platform does not support two simultaneous secrets for a client, schedule a specific cutover and rollback plan.

### Database Migrations and Rolling Deployments

Migrations must be compatible with application versions running during the rollout. Prefer expand-and-contract:

1. Add new schema elements so the current version keeps working.
2. Deploy code that can read/write old and new schemas as needed.
3. Backfill data and verify.
4. Shift traffic or toggle feature flags.
5. Once no old instances remain, drop the old schema in a later release.

Never run destructive migrations before having backups and a rollback plan. For large authorization tables, evaluate lock durations, index builds, transaction logs, and impact on the token endpoint.

## 11. Troubleshooting Incidents by Symptom

During an incident, first determine scope: all clients or one client, all instances or one node, authorization endpoint or token endpoint, user login or machine-to-machine. Record start time, most recent deployment/config change, correlation ID, and error category. Never collect intact tokens or secrets.

| Symptom | Possible Cause | Evidence to Inspect | Resolution |
|---|---|---|---|
| Discovery returns internal issuer or URLs | Wrong issuer, untrusted forwarded headers, bad proxy rewrite | Metadata, AuthorizationServerSettings, ingress config | Restore public issuer; fix proxy headers; verify from client network |
| Redirects use HTTP | Wrong TLS termination or forwarded proto | Location, X-Forwarded-Proto, proxy logs | Normalize headers at trusted proxy; check TLS and filter strategy |
| Sudden spike in invalid_client | Secret rotation timing mismatch, changed client auth method | Client config version, auth failure category, rollout timeline | Synchronize credentials; check method; rotate via cutover |
| Spike in invalid_grant | Expired/replayed code, PKCE mismatch, changed redirect URI | Error category, client fixture, scrubbed token request metadata | Check client flow and clocks; never log codes/verifiers |
| Token signature invalid | Key mismatch, JWKS cache, missing kid, algorithm change | JWT header with scrubbed payload, JWKS, key inventory | Check key overlap and caches; restore proper public key |
| ID Token issuer mismatch | Issuer config changed or nodes have divergent config | Discovery, iss claim, instance config version | Align issuer; roll back inconsistent config |
| Users cannot keep sessions | Cookie/SameSite, session store, session fixation, or proxy | Set-Cookie, browser trace, Redis/session metrics | Fix cookie policy; check shared sessions and domain/path |
| Repeated consent prompts | Consent persistence cannot save/read or scopes keep changing | Consent rows/service, client scope config | Restore persistence; check scopes and client identity |
| Token endpoint timeouts | Exhausted DB pool, locks, KMS latency, or thread starvation | Hikari metrics, DB slow queries, KMS latency, thread dumps | Shed load, recover dependency; tune pool after finding root cause |
| One node issues failing tokens | Key/config/schema differs from other nodes | Instance version, active kid, migration level | Drain misconfigured node; synchronize rollout |
| Revoked tokens still accepted by API | Self-contained JWT still unexpired or cache TTL active | Token type, resource server cache, revocation path | Apply short TTL/denylist/introspection per threat model; do not assume JWTs self-revoke |
| Flapping health checks | Readiness depends on too much or probe timeout | Probe responses, dependency health, restart count | Separate liveness/readiness; adjust timeouts and dependency policies |

### Triage Procedure

1. Identify affected endpoints and user/client groups.
2. Correlate correlation IDs across proxy, Authorization Server, and dependency logs.
3. Check release/config/key versions at the time of the incident.
4. Verify issuer, metadata, and JWKS from an external perspective.
5. Inspect PostgreSQL pool, query latency, locks, and migrations.
6. Inspect KMS/secret manager and key states.
7. Inspect session store, cookies, and proxy if the incident involves browser login.
8. Pick the smallest reversible mitigation: drain faulty node, roll back config, restore dependency, or temporarily disable affected client.
9. Run smoke tests and confirm behavior with a test client.
10. Document timeline, impact, root cause, and action items to prevent recurrence.

Do not bulk-delete authorizations or consents to resolve login errors without identifying the root cause. Do not arbitrarily rotate signing keys while old tokens remain valid; such changes can prevent all resource servers from verifying tokens.

## 12. Capstone Practice: Completing a Deployment

Execute the labs in order. Use an isolated local or staging environment, a test domain, and synthetic credentials. Never create or delete test data in production.

### Lab A — Writing the Architecture Decision Record

Create a concise ADR covering:

- OAuth/OIDC goals and scope.
- Topology of proxy, application, database, key manager, and optional Redis.
- Issuer, grant types, token formats, and client types.
- Storage locations for RegisteredClient, authorizations, consents, and sessions.
- Threat boundaries and trust assumptions.
- Decisions on key rotation, refresh tokens, and revocation.
- Remaining limitations and rationale for acceptance.

**Expected result:** a reviewable architecture diagram and decision table, each decision backed by rationale and operational impact.

### Lab B — Standardizing Configuration

1. Set a fixed public issuer.
2. Configure the datasource via environment/secret injection.
3. Configure JDBC repositories and migrations.
4. Register a confidential client using Authorization Code + PKCE.
5. Register a public client if required.
6. Configure JWKSource to load persistent keys from the key provider.
7. Configure filter chains matching the Spring Authorization Server version in use.
8. Enable health probes and restrict actuator access.

**Expected result:** the application starts against a real database, clients reload after restarts, and issuer and JWKS remain stable across restarts.

### Lab C — Completing Ingress

1. Place the application behind Nginx or an ingress controller.
2. Allow backends to accept traffic only from ingress.
3. Strip/rewrite Forwarded and X-Forwarded-* at the edge proxy.
4. Configure TLS and certificates for the test domain.
5. Verify redirects, discovery, and cookies use public URLs.

**Expected result:** clients cannot spoof host/proto via headers; metadata and redirects never leak backend addresses.

### Lab D — Running the OAuth/OIDC Flow

1. Create user and client fixtures.
2. Send an authorization request with state, nonce, and PKCE S256.
3. Log in and approve consent.
4. Exchange the code with the valid verifier.
5. Verify the access token at the resource server and ID Token at the OIDC client.
6. Test an invalid verifier and code replay.
7. Test refresh/revocation if enabled.
8. Inspect audit events and persistence.

**Expected result:** valid flows succeed; negative cases are properly rejected; no tokens or secrets appear in logs.

### Lab E — Operational Verification

1. Start two instances with the same issuer, database, and key set.
2. Issue a code via node A and exchange it via node B.
3. Stop one node using graceful shutdown.
4. Verify readiness, liveness, and load balancer draining.
5. Run a backup/restore drill in an isolated environment.
6. Execute key rotation following the overlap procedure.
7. Simulate database connectivity loss in a test environment and observe readiness/error behavior.

**Expected result:** no unintended local-state dependencies; rollouts do not break token verification; operations can recover using the runbook.

### Lab F — Incident Drill

Choose one scenario:

- Issuer in metadata was misconfigured.
- A client's secret expired.
- JWKS lacks the kid of tokens currently being issued.
- PostgreSQL connection pool is exhausted.
- Redis session store is unreachable.
- One node is running an outdated key set or config.

For each scenario, document: symptoms, detection, evidence, blast radius, mitigation, rollback, recovery verification, and preventive actions.

**Expected result:** an actionable incident runbook an on-call operator can follow without guessing or destructive actions.

## 13. Minimum Deliverable Documentation Set

A complete documentation set should include the following artifacts:

| Document | Required Content | Primary Audience |
|---|---|---|
| Architecture overview | Diagrams, components, trust boundaries, OAuth/OIDC flows | Developers, architects, security |
| Configuration reference | Issuer, endpoints, client policies, DB, keys, proxy, secrets | Developers, platform |
| Deployment runbook | Prerequisites, migrations, rollout, readiness, rollback | SRE/operations |
| Client onboarding guide | Client types, redirects, grants, scopes, PKCE, credential delivery | Application teams |
| Key management runbook | Key inventory, access, rotation, emergency revocation | Security, platform |
| Monitoring and audit guide | Metrics, logs, events, alerts, and retention | SRE, security |
| Backup and recovery plan | RPO/RTO, backups, restore drills, key recovery | Operations |
| Incident playbooks | Symptoms, evidence, mitigation, validation | On-call |
| Test and release checklist | Conformance, regression, smoke tests, release gates | QA, developers, release managers |

Every document must specify an owner, version, last review date, applicable environments, and links to source configuration. Never copy secrets into documentation; reference secret names or resource IDs in the secret manager. Define a review schedule after major changes to the framework, OAuth/OIDC profile, issuer, keys, database schema, or topology.

## 14. Operational Readiness Checklist

- [ ] Issuer is explicitly configured and consistent with metadata/tokens.
- [ ] Grants, scopes, redirect URIs, and client authentication methods have owners.
- [ ] PKCE S256 is enforced by policy for Authorization Code clients.
- [ ] RegisteredClient, authorizations, and consents are persisted durably.
- [ ] Database migrations are versioned, reviewed, and have a rollback strategy.
- [ ] Signing keys are persistent, private keys are protected, and JWKS has a rotation plan.
- [ ] Proxy strips/rewrites forwarded headers and backends accept only trusted traffic.
- [ ] TLS certificates, DNS, ingress, and public URLs are verified.
- [ ] Sessions/cookies/CSRF/CORS match browser flows.
- [ ] Health probes, metrics, logs, and audits are configured.
- [ ] No tokens, codes, secrets, cookies, or private keys are logged.
- [ ] Backups include data and have a key recovery plan.
- [ ] RPO/RTO and restore drills are defined.
- [ ] Graceful shutdown, readiness, and multi-instance rollouts have been tested.
- [ ] Runbooks exist for issuer, client, token, JWKS, DB, session, and proxy errors.
- [ ] Smoke tests and regression gates run before release.

Good documentation bridges architecture decisions to real configuration, configuration to operational procedures, and symptoms to verifiable recovery actions. When issuer, client policies, persistence, signing keys, proxies, and operational processes are documented consistently, Spring Authorization Server can be handed over and operated without relying on any single individual's tribal knowledge.
