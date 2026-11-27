# Protecting Introspection Credentials and Rotation Processes

When a Spring Security Resource Server verifies an opaque access token, it typically calls an **introspection endpoint** on the Authorization Server. This request carries two kinds of information that must be protected separately:

- **The user's or client's access token:** the token whose status the Resource Server needs to query.
- **The Resource Server's own credentials:** the client ID and client secret (or another client authentication mechanism) used to prove to the Authorization Server that the application is authorized to call the introspection endpoint.

These two credentials have different lifecycles and purposes. An introspection client secret is not a user access token, not a JWT signing secret, and not a user's password. It is the credential of an OAuth client representing the Resource Server. If this credential is exposed, an attacker can impersonate the Resource Server to query token statuses or access other capabilities granted to that client registration.

Protecting introspection credentials therefore requires least-privilege configuration, secure secret storage, TLS, logging controls, a rotation procedure with overlap, rollback, and post-rotation verification. Changing the secret must be coordinated with the Authorization Server and all running Resource Server instances.

## 1. What Is Introspection and Who Authenticates to Whom?

Under OAuth 2.0 Token Introspection (RFC 7662), the Resource Server sends a token to an endpoint published by the Authorization Server to ask whether the token is active and retrieve permitted metadata.

Example introspection request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>&token_type_hint=access_token
~~~

Two credentials appear in this request:

| Value | Represents Whom? | Purpose |
| --- | --- | --- |
| Client ID/secret in HTTP Basic | Resource Server (registered OAuth client) | Authenticates the application calling the introspection endpoint |
| `token` in form body | Caller/user/service that received the access token | Lets the Authorization Server look up the token's status and claims |

The Authorization Server authenticates the Resource Server first, and only then evaluates the token sent in the `token` parameter. The Resource Server must not confuse these two identities.

For example, `orders-api` may be registered as a confidential client solely to call introspection. That request carries `orders-api`'s client ID and corresponding secret, while the `token` parameter is the access token of user `user-42` or service `orders-worker`.

### Introspection Client Secrets Are Not Signing Keys

- A JWT signing key is the private key or secret used by the issuer to sign tokens.
- A JWT verification key is the public key or secret used by the Resource Server to verify signatures per profile.
- An introspection client secret authenticates the Resource Server to the introspection endpoint.
- A user password is the user's login credential at the Authorization Server.

Rotating the introspection client secret normally does not alter already-issued JWT signatures and does not automatically revoke user access tokens. It changes the Resource Server's ability to authenticate to the introspection endpoint.

## 2. Why Are Introspection Credentials High-Value?

If an attacker obtains a Resource Server's client secret, they can attempt to:
- Call the introspection endpoint on behalf of the application.
- Query token statuses that the client registration is permitted to introspect.
- Learn claims/subject/client metadata returned by the endpoint.
- Generate heavy load on the Authorization Server via introspection requests.
- Abuse other grants or APIs if the same client registration has excessive permissions.
- Reuse the secret to impersonate the Resource Server in another system if secrets are reused.

The blast radius depends on the Authorization Server and the client registration's permissions. Therefore, each Resource Server should have its own client identity or a tightly controlled shared scope, granted only the introspection permissions needed.

Never share one client secret across every microservice when separate credentials can be issued. If `orders-api` is compromised, dedicated credentials limit impact and allow independent rotation.

## 3. Principle of Least Privilege for the Introspection Client

Create a dedicated OAuth client registration for the Resource Server. Grant only:
- Permission to call the required introspection endpoint.
- Permission to view only the token types/claims the API actually needs.
- Audience or resource scope per Authorization Server policy if supported by the product.
- Network access from permitted workloads/namespaces if the AS supports network policies.

Avoid granting extra permissions such as:
- `client_credentials` access tokens for business APIs if unnecessary.
- Permission to call the token endpoint to obtain tokens on behalf of users.
- Client or user administration privileges.
- Permission to read unrelated sensitive claims.
- Permission to introspect every token type if the AS can restrict it.

Some Authorization Servers share a client registration across multiple features or do not offer dedicated introspection permissions. In that case, document the product's limitation and mitigate risk with dedicated clients, dedicated secrets, network restrictions, rate limits, and monitoring.

### One Client per Resource Server

~~~text
Authorization Server
  |
  +-- orders-api-introspection
  |      +-- dedicated client ID
  |      +-- dedicated secret
  |      +-- used only by Orders API
  |
  +-- billing-api-introspection
  |      +-- dedicated client ID
  |      +-- dedicated secret
  |      +-- used only by Billing API
  |
  +-- reporting-api-introspection
         +-- dedicated client ID
         +-- dedicated secret
         +-- used only by Reporting API
~~~

If multiple instances of the same Resource Server run in a cluster, they can share that application's client registration, yet the secret must be provisioned via secret management and restricted by workload identity. Sharing secrets across unrelated services increases the blast radius if one service is compromised.

## 4. Client Authentication at the Introspection Endpoint

RFC 7662 requires the introspection endpoint to be protected by an appropriate authorization mechanism. A common approach is confidential client authentication using HTTP Basic over TLS.

~~~http
Authorization: Basic base64(client_id:client_secret)
~~~

Base64 is only encoding, not encryption. TLS is mandatory to protect credentials in transit. Never send client secrets over unencrypted HTTP.

Other mechanisms an Authorization Server may support:
- `client_secret_post`: client ID/secret in the form body.
- `private_key_jwt`: client signs an assertion with a registered private key.
- Mutual TLS client authentication.
- Vendor-specific client authentication mechanisms.

**Not every Spring Security version or Boot configuration supports all of these methods via default properties.** The common constructor of `NimbusOpaqueTokenIntrospector` accepts the introspection URI, client ID, and client secret, typically using HTTP Basic. If the AS requires `private_key_jwt`, mTLS, or another method, check the API of your version and configure a custom introspector/client authentication accordingly. Do not rename properties or assume Boot automatically switches methods.

### Do Not Put Secrets in URLs

Avoid configurations like:

~~~text
https://client-id:client-secret@auth.example.com/oauth2/introspect
~~~

Never place secrets in query strings. URLs can appear in proxy logs, tracing, browser history, or telemetry. Use a supported client authentication mechanism and TLS.

## 5. Spring Boot Configuration for Opaque Tokens

Spring Boot provides common opaque-token Resource Server properties:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: <secret-injected-at-runtime>
~~~

`<secret-injected-at-runtime>` is a placeholder describing a value injected from a secret store; never put this literal placeholder into production config. With Spring Boot, you can use externalized configuration, environment variables injected by a secret manager, or config trees/files as supported by your Boot version.

Corresponding environment variable names typically follow the pattern:

~~~text
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_INTROSPECTION_URI
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_ID
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_SECRET
~~~

Verify property names and binding against your project's Spring Boot version. Avoid putting secrets directly in committed YAML files.

### Servlet Resource Server

A security chain configuration can use opaque tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Spring Boot auto-configuration can provide an introspector based on properties. If you declare a custom `OpaqueTokenIntrospector`, verify bean precedence and ensure client authentication configuration is not unintentionally bypassed.

### WebFlux Resource Server

In a reactive application, the security chain can use:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Reactive Resource Server uses `ReactiveOpaqueTokenIntrospector`. Never call synchronous introspection using `block()` on the event loop. If custom client authentication or HTTP client customization is needed, choose a reactive implementation compatible with your running Spring Security version.

## 6. Injecting Secrets from a Secret Manager

Secrets should be managed outside source code and build artifacts. Options include:
- Vault or a cloud provider's secret manager.
- Kubernetes Secrets encrypted at rest with RBAC controls, or better yet, integrated via an external secrets operator/CSI driver.
- The deployment platform's secret store.
- Mounted secret files with minimal filesystem permissions.
- Workload identity to fetch secrets from the secret manager without storing long-lived secret-store access credentials in the image.

Example flow:

~~~text
Secret Manager
      |
      | issues secret for workload identity
      v
Kubernetes / runtime secret integration
      |
      | inject environment or mount file
      v
Spring Boot configuration binding
      |
      v
OpaqueTokenIntrospector
      |
      | HTTPS + client authentication
      v
Authorization Server introspection endpoint
~~~

### Storage Rules

- Never commit client secrets to Git, even on private branches or sample files.
- Never bake secrets into Docker images, JARs, Helm charts, or ConfigMaps.
- Never write secrets in build scripts, command lines, or CI logs.
- Never put secrets in URLs or query strings.
- Never share secrets over tickets, chat, email, or uncontrolled documents.
- Restrict which people and workloads can read secrets.
- Enable encryption at rest and audit logging on the secret store.
- Use separate secrets per environment: dev, staging, production.
- Assign an owner, issuance date, rotation schedule, and revocation procedure.
- Never reuse secrets across unrelated applications.

Kubernetes Secrets are Base64-encoded by default in manifests/APIs; Base64 is not encryption. Enable encryption at rest in the control plane, restrict RBAC, avoid committing manifests containing secrets, and prefer secret-manager integration where appropriate.

### Are Environment Variables the Ideal Storage Mechanism?

Environment variables are convenient for Spring Boot externalized configuration, yet they can be exposed via process inspection, diagnostic dumps, crash reports, or misconfigured operational tooling. If the platform supports it, mount secrets as files with restricted permissions or use config trees/secret integrations. If using environment variables, restrict process/environment read access and never dump the entire environment into logs.

Never pass secrets as command-line arguments like `--spring...client-secret=...`; command lines can appear in process listings, shell histories, or process supervisor metadata.

## 7. Preventing Secret Leaks via Logging and Diagnostics

Common leak vectors:
- Full HTTP request/response logging.
- Debug logging in OAuth clients or HTTP clients.
- Wiretap logging headers/bodies.
- Spring Boot Actuator `env`, `configprops`, or diagnostic endpoints.
- Exceptions containing request bodies or authorization headers.
- Distributed tracing recording the `Authorization` header.
- APM agents capturing HTTP headers.
- Heap dumps, thread dumps, or crash dumps.
- CI/CD logs when rendering configs or running tests.

### Headers Requiring Redaction

At a minimum, redact:
- `Authorization` of the introspection request (client Basic credentials).
- `token` in the introspection form body.
- Access tokens in requests to the Resource Server if logging middleware records headers.
- `client_secret`, `password`, `refresh_token`, and equivalent secrets.
- DPoP proofs or unnecessary sensitive JWT claims.

Redaction must be enforced at the proxy, application logger, tracing/APM, and log pipeline. Redacting at only one layer is insufficient if another layer records raw requests.

### Actuator and Configuration

If Actuator is enabled:
- Expose only necessary endpoints.
- Protect management endpoints with network policies and authentication.
- Verify sanitization for sensitive properties.
- Never expose `env` or `configprops` publicly.
- Do not treat default sanitization as a reason to expose endpoints to everyone.
- Test diagnostic endpoints to confirm the client secret is masked.

Never log configuration objects containing secrets using `toString()`. Never log exception chains that might contain unredacted sensitive headers/bodies.

## 8. Protecting the Connection to the Introspection Endpoint

Client authentication cannot protect a secret if the connection is eavesdropped on or TLS is misconfigured.

Requirements:
- Use HTTPS with the exact hostname.
- Verify the Authorization Server's certificate chain and hostname.
- Use a managed trust store; never disable hostname verification.
- Never use a trust-all SSL context in production.
- Only allow the workload to connect to allowlisted introspection hosts/paths.
- Restrict egress network traffic by namespace/service identity if supported by the platform.
- Configure connect/read/response timeouts.
- Control redirects; never forward client credentials on redirects to another host.
- Bound connection pools and concurrency.
- Monitor TLS handshakes, certificate expiry, and trust errors.

If using an outbound proxy, verify whether the proxy terminates TLS, whether the proxy can see Basic credentials/tokens, and who has access to proxy logs. An internal proxy is also a trust boundary.

### Do Not Send Tokens in Query Strings

RFC 7662 uses POST with the token in the request body. Avoid GET URLs like:

~~~text
GET /oauth2/introspect?token=<access-token>
~~~

Query strings are easily written into access logs, reverse proxy logs, tracing, and monitoring. Use POST form encoding per the introspection protocol.

## 9. Timeouts, Retries, and Introspection Errors

Introspection is a runtime dependency. If the endpoint does not respond, the Resource Server cannot infer on its own whether a token is active.

Configure:
- Connect timeout.
- TLS handshake timeout.
- Response/read timeout.
- Connection pool acquisition timeout.
- Total deadline for introspection.
- Small retry budget with backoff and jitter for transient errors.
- Rate limits to prevent request storms when the AS is slow.
- Circuit breakers if appropriate for the architecture.

Never retry indefinitely. An API request hanging too long ties up connections, memory, and worker resources.

### Distinguishing Inactive Tokens from Dependency Failures

| Scenario | Meaning | Handling |
| --- | --- | --- |
| Introspection returns `active: false` | AS confirms the token is inactive | Reject token |
| Introspection returns `active: true` | AS confirms the token is active | Continue validation/authorization per profile |
| HTTP 401/403 from introspection | Client authentication/authorization issue | Investigate credentials/registration; do not arbitrarily treat as user token inactive |
| HTTP 429 | AS rate limit | Honor `Retry-After` if present, reduce concurrency |
| HTTP 5xx/timeout/TLS/DNS | Cannot determine token status | Fail closed, alert on dependency |
| Malformed JSON response | Result cannot be trusted | Fail closed |
| Missing `active` or wrong data type | Response violates contract | Fail closed |

Never treat network errors as `active: true`. Never fall back to allowing requests merely because the introspection endpoint is temporarily failing. If the API needs to return 503 for a dependency outage instead of a 401 authentication failure, implement explicit exception mapping per the application's contract and test that behavior. Default status codes may depend on exception types, Spring Security version, and custom entry points.

### Retries Can Overload the Authorization Server

If every API request triggers an introspection call and all instances retry immediately when the AS returns 503, an outage can escalate into a retry storm. Use exponential backoff with jitter, cap retry counts, and limit concurrency. With synchronous Servlet introspection, protect request threads and connection pools; with WebFlux, keep execution non-blocking.

## 10. Introspection Caching and Impact on Revocation

Introspection is typically called per request or on cache miss depending on configuration. Caching reduces latency and AS load, yet delays visibility of revoked tokens.

Example:
- A token is introspected at 10:00 and returns active.
- The Resource Server caches the result for 5 minutes.
- The Authorization Server revokes the token at 10:01.
- Without cache invalidation, the Resource Server may continue using the active result until the entry expires.

Therefore, cache TTL must be based on:
- The system's revocation SLA.
- Remaining token lifetime (`exp`), if present.
- API sensitivity.
- Revocation frequency.
- Ability to invalidate caches on AS events.
- Introspection request volume and AS capacity.

A TTL bound can be expressed as:

~~~text
cache_ttl = min(configured_max_ttl, token_expiry - now, revocation_freshness_budget)
~~~

This is a design rule, not a built-in property in every Spring Security version.

### Caching Active and Inactive Results

- Caching `active: true` can delay revocation; keep TTL short per requirements.
- Briefly caching `active: false` can reduce repeated lookups for already rejected tokens, though cache key collisions must be avoided so new tokens are not miskeyed.
- Never cache network/5xx errors as if the token were inactive or active.
- Never use a TTL exceeding token expiry.
- Use a token hash as the cache key instead of the raw token if the cache system allows it.
- Protect the cache store and restrict read access.
- Never log cache keys if they can reconstruct or link back to the token.

Spring Security should not be assumed to cache introspection with a specific TTL across all configurations. If caching is needed, implement an `OpaqueTokenIntrospector` or `ReactiveOpaqueTokenIntrospector` wrapper appropriate for your version, then test expiry, revocation, and concurrency.

## 11. Secret Rotation Process with Overlap

Safe rotation must ensure old and new instances do not lose introspection capability simultaneously during rollout.

The best pattern is when the Authorization Server allows two simultaneously valid secrets for the same client registration:

~~~text
Phase 1:
  AS accepts secret A
  All Resource Servers use A

Phase 2:
  AS creates secret B while still accepting A
  Resource Servers unchanged, requests still use A

Phase 3:
  Secret store updated to B
  New/reloaded Resource Server instances use B
  AS accepts both A and B

Phase 4:
  Verify all instances now use B
  No introspection requests use A anymore

Phase 5:
  AS revokes A
  Only B remains valid
~~~

### Execution Steps

1. **Check AS capability:** confirm whether multiple active secrets/credential versions are supported for the same client.
2. **Create new secret:** generate B, set expiry/owner, and store it in the secret manager.
3. **Keep old secret:** do not revoke A yet.
4. **Update secret store:** switch workload secret reference/value to B.
5. **Controlled rollout:** restart/reload instances in batches; avoid restarting the whole fleet at once.
6. **Verify:** monitor introspection success, auth failures, client ID, deployment revision, and non-sensitive secret version identifiers.
7. **Confirm A is unused:** use AS-side audit logs or secret-version telemetry; never log raw secrets.
8. **Revoke A:** only after all instances have switched and the rollback window has ended.
9. **Record:** creation, deployment, verification, and revocation timestamps in the change record.
10. **Post-rotation checks:** valid opaque token requests still succeed; inactive tokens are still rejected.

Overlap prevents downtime during rollout. The overlap duration must cover deployment, autoscaling, pod restarts, and the rollback window without extending unnecessarily.

## 12. When the Authorization Server Allows Only One Secret

Some providers allow only one active client secret at a time. If changing the secret immediately invalidates the old secret, a rolling deployment can enter a split state:
- Old instances still use A.
- The AS only accepts B.
- Old instances fail introspection.
- New instances using B work.

In this case, consider creating a **second client registration**:

~~~text
orders-api-introspection-v1 -> client ID A, secret A
orders-api-introspection-v2 -> client ID B, secret B
~~~

Procedure:
1. Register client v2 with equivalent, minimal introspection permissions.
2. Store secret v2 in the secret manager.
3. Deploy Resource Servers using client v2 in batches.
4. Confirm all instances use v2 and introspection succeeds.
5. Keep v1 during the rollback window if policy allows.
6. Revoke v1 and delete secret v1 from the secret store after the rollback window ends.

When using a new client ID, check whether the AS applies permissions, audiences, policies, or rate limits per client registration. Never assume v2 automatically inherits the same permissions as v1.

If neither overlap nor a second client registration is possible, plan a maintenance window or controlled cutover. Never revoke the old secret before workloads are ready to switch to the new secret.

## 13. Rollback When a New Secret Fails

Rollback is only safe while the old credential is still accepted by the AS.

Before starting rotation, document:
- Current secret version.
- New secret version.
- Client registration.
- Instances/namespaces using the credential.
- Overlap start and end times.
- Rollback criteria.
- Person/role authorized to revoke credentials.

If B fails:
1. Halt further rollout.
2. Inspect HTTP errors from the introspection endpoint and AS audit logs.
3. Check client ID, authentication method, secret version, TLS, and endpoint.
4. If A is still active, revert workloads to A.
5. Verify introspection recovers across all instances.
6. Keep B for investigation or revoke it per incident policy.
7. Only end overlap once a stable working credential is confirmed.

Never roll back to secret A if A was compromised or revoked due to a security incident. In that situation, issue a newly generated credential and handle the incident under emergency procedures.

## 14. Automated Rotation and Secret Versioning

A secret manager can support:
- Creating new versions.
- Assigning aliases/current versions.
- Distributing secrets to workloads.
- Auditing who reads/rotates/revokes.
- Expiry and notifications.
- Version rollback if the old credential is still active.

An automated pipeline may include:

~~~text
Scheduled rotation trigger
        |
        v
Create new credential at Authorization Server
        |
        v
Store new secret version
        |
        v
Update workload secret reference
        |
        v
Roll out Resource Server instances
        |
        v
Verify introspection success across fleet
        |
        v
Revoke old credential
        |
        v
Close rotation record
~~~

Never automatically revoke the old secret immediately after creating the new one. There must be a rollout verification step and an approved overlap period.

### Rotation Does Not Mean Automatic Reload

Updating a Kubernetes Secret or secret manager value does not guarantee every Spring Boot application picks up the new value automatically. Confirm:
- Whether the secret is injected via environment variables or mounted files.
- Whether environment variables update in running processes (normally process environments do not update dynamically).
- Whether Spring configuration supports reloading.
- Whether pods must restart to read the new secret.
- Whether connection/client objects hold old credentials in memory.
- Whether a secret rotation controller restarts workloads based on version/checksum.

With environment variables, pod rollouts/restarts are usually required for processes to pick up new values. With mounted files, the file may update while the application does not reload automatically without a supporting mechanism. Never mark rotation complete merely because the secret store has a new version.

## 15. Emergency Rotation When a Secret Is Exposed

When an introspection client secret is suspected of compromise, prioritize blocking use of the old secret:
1. Identify the client registration and scope of workloads using the secret.
2. Create a new credential or replacement client registration per AS capability.
3. Update the secret store and deploy workloads.
4. Revoke the exposed credential per incident decision; if risk is high, immediate revocation may be required even at the cost of introspection disruption.
5. Monitor authentication failures and suspicious requests to the introspection endpoint.
6. Inspect AS audit logs to determine where the client credential was used from.
7. Check logs/tracing/heap dumps/CI artifacts that may have stored the secret.
8. Purge or restrict access to artifacts containing the secret per incident procedures.
9. Assess whether tokens/claims introspected by the attacker could have been accessed without authorization.
10. Document root cause and improve secret distribution/redaction.

Never send the new secret through the same channel that leaked the old secret. Never keep a compromised secret active just to avoid downtime if the threat model requires immediate revocation.

## 16. Distinguishing Client Secret Rotation from Access Token Rotation

| Action | What Changes? | Typical Impact |
| --- | --- | --- |
| Rotate introspection client secret | Credential the Resource Server uses to authenticate to the AS | Instances still using the old secret fail introspection after the old secret is revoked |
| Revoke access token | Caller's token status at the AS | Introspection returns inactive per propagation/cache policy |
| Rotate JWT signing key | Key the AS uses to sign JWTs | Resource Servers need new JWKS keys and overlap/cache handling |
| Rotate mTLS client certificate | Client certificate/private key | Must update TLS identity/trust and possibly token bindings |
| Rotate DPoP key | Client's proof-of-possession key | Tokens bound to the old key do not automatically transfer to the new key |

Do not use introspection client secret rotation to handle stolen user tokens; the goals are different. Likewise, revoking access tokens does not replace revoking an exposed client secret.

## 17. Testing Introspection Credentials and Rotation

Test across multiple layers.

### Unit/Configuration Tests

- Property binding receives the right introspection URI and client ID.
- Secret is loaded from the expected secret source.
- No weak default secret exists in the production profile.
- Objects containing credentials are never logged.
- Custom introspectors use the right authentication method.
- Timeouts/retries apply as designed.

Never print secret values on assertion failures. Assert secret version IDs or mock invocations without logging raw values.

### HTTP Integration Tests with an Introspection Stub

Use WireMock, `MockWebServer`, or a test HTTP server to verify:
- POST is sent to the right endpoint.
- Token is in the form body, not in the query string.
- Client authentication is sent with the right method.
- `active: true` produces appropriate principal and authorities.
- `active: false` is rejected.
- Wrong client secret receives an error response.
- 429/5xx/timeouts are handled per policy.
- TLS trust/hostname is verified in HTTPS tests if needed.

If using the default Nimbus introspector, inspect actual requests to confirm HTTP Basic matching your constructor/configuration. If a custom introspector uses `private_key_jwt` or mTLS, separately test client assertion/certificate behavior.

### Rotation Tests

| Step | Authorization Server | Resource Server | Expectation |
| --- | --- | --- | --- |
| Before rotation | Only A active | All use A | Introspection succeeds |
| Create B | A and B active | Still use A | Zero disruption |
| Partial rollout | A and B active | Some use B, rest use A | Both groups work |
| Rollout complete | A and B active | All use B | No more requests using A |
| Revoke A | Only B active | All use B | Introspection keeps succeeding |
| Test credential A | A revoked | Test client uses A | AS rejects |
| Test credential B | B active | Test client uses B | AS accepts |

Tests must not use production secrets. Use dedicated test client registrations and test credentials.

### Cache Tests After Token Revocation

If using an introspection cache:
- Cache an active response.
- Revoke the token at the stub/AS.
- Verify behavior before and after TTL.
- Test invalidation events if supported.
- Verify outages do not turn into active results.
- Verify cache keys do not store raw tokens.

## 18. Monitoring and Alerting

Monitor by client registration/issuer alias, avoiding labels containing secrets or raw tokens.

| Metric | Signal to Watch |
| --- | --- |
| Introspection success rate | Sudden drop after rotation |
| HTTP 401/403 from AS | Wrong client ID/secret or permissions |
| Introspection 429/5xx | Rate limits or AS outage |
| Introspection latency | Slow AS, saturated connection pool |
| Timeout/connect/TLS errors | Network, trust store, or endpoint issues |
| Active/inactive counts | Unusual shifts in token population |
| API authentication failures | Invalid caller tokens or failing introspection dependency |
| Running credential version | Identify instances still on old versions |
| Instance rollout progress | Confirm fleet switched secrets |
| Secret read/audit events | Detect anomalous access |

Do not create metric labels for client secret versions if every rotation produces unbounded cardinality; use a bounded label or structured log events instead. Never log raw secrets.

### Useful Alerts

- Introspection 401/403 rate exceeds threshold after deployment.
- Introspection p95/p99 latency rises.
- Timeout/5xx rate exceeds threshold.
- Instances still using the old secret version after the overlap window.
- Secret nearing expiration or scheduled rotation date.
- Introspection requests originating from network sources outside permitted workloads.
- AS returning sustained 429s.
- Actuator/log pipelines detecting unsanitized sensitive properties.

## 19. Secure Deployment Checklist

Pre-production:
- [ ] Dedicated client registration for the Resource Server.
- [ ] Client has only necessary introspection permissions.
- [ ] Client ID/secret are not in source code or images.
- [ ] Secrets are stored in a secret manager or protected store.
- [ ] Secrets differ across dev, staging, and production.
- [ ] TLS hostname and certificate validation are enabled.
- [ ] Introspection endpoint is allowlisted.
- [ ] Tokens are sent in POST bodies, never in URLs.
- [ ] `Authorization` headers, form bodies, and exception logs are redacted.
- [ ] Actuator/diagnostics are protected.
- [ ] Timeouts, retry budgets, and concurrency limits are configured.
- [ ] Introspection errors never fail open.
- [ ] Cache TTL meets the revocation SLA.
- [ ] Overlap procedure or second client registration is ready.
- [ ] Rollback plan exists before revoking old credentials.
- [ ] Tests confirm all instances use the new credential.
- [ ] Auditing and alerts exist for secret access/rotation.

During rotation:
- [ ] Create the new secret and store it in the secret manager.
- [ ] Keep the old secret active during overlap.
- [ ] Deploy in batches.
- [ ] Verify success rates and credential versions across the fleet.
- [ ] Revoke the old secret only after verification.
- [ ] Remove access to the old secret and close the change record.

## 20. Common Mistakes

**"The introspection client secret is the user's access token."** No. The secret authenticates the Resource Server to the AS; the `token` in the form body is the token being introspected.

**"Base64 Basic Auth encrypts the secret."** No. Base64 is only encoding; TLS is required to protect it in transit.

**"Introspection requests can be logged at DEBUG."** Not if the logger writes the `Authorization` header or form body containing the token. Redaction is required across the application, proxy, and tracing.

**"Storing secrets in a ConfigMap or private Git repo is enough."** No. Use a secret store, RBAC, encryption at rest, and auditing.

**"Updating a Kubernetes Secret automatically updates running processes."** Not necessarily. Environment variables and already-bound objects may hold old values; verified rollouts/reloads are required.

**"Revoke the old secret immediately after creating the new secret."** This can break introspection for instances that have not rolled out yet. Use overlap or a replacement client registration.

**"If the new secret fails, always roll back to the old secret."** Not if the old secret was compromised or revoked. Rollback must respect the credential's trust state.

**"An introspection timeout means the token is inactive."** No. That is a dependency failure; token status cannot be determined.

**"If the AS fails, let requests through to preserve availability."** No. Without a trustworthy introspection result, a token cannot be treated as active.

**"Cache active responses for a long time to reduce load."** Long TTLs delay awareness of revocation. Choose TTLs based on freshness/revocation SLAs.

**"Rotating the client secret revokes all access tokens."** No. That is the introspection client's credential; token lifecycle is separate.

**"One secret for all microservices makes management easier."** It widens the blast radius and makes rotation hard to isolate.

## 21. Recommended Operational Workflow

1. **Register dedicated clients:** create a confidential client per Resource Server or shared boundary group.
2. **Restrict permissions:** grant only necessary introspection and metadata permissions.
3. **Choose authentication method:** use HTTP Basic over TLS when appropriate; verify support before choosing `private_key_jwt` or mTLS.
4. **Store secrets securely:** secret manager, workload identity, mounted files, or appropriate integration.
5. **Inject at runtime:** Spring Boot reads properties via externalized config; never commit secrets.
6. **Configure Resource Server:** use opaque token introspection with version-appropriate endpoints and client credentials.
7. **Protect HTTP:** TLS validation, endpoint allowlists, timeouts, pools, and redaction.
8. **Define cache policy:** TTL per revocation freshness, never cache errors, and never store raw tokens as keys.
9. **Design rotation:** two-secret overlap or a second client registration.
10. **Execute rollout:** update the secret store, restart/reload in batches, and verify every instance.
11. **Revoke old credentials:** only after the whole fleet uses the new credential and the rollback window ends.
12. **Monitor:** success rate, AS status, latency, secret version, audits, and alerts.
13. **Practice incident drills:** secret leaks, AS outages, bad rotations, rollbacks, and emergency revocations.

**Key takeaway:** The introspection client secret authenticates the **Resource Server** to the Authorization Server; the access token in the request body is the token being looked up. Protect the secret with a dedicated client registration, least privilege, a secret manager, TLS, and full redaction across logs/diagnostics. During rotation, prefer two simultaneously active credentials across an overlap window; if the AS does not support that, use a new client registration for batched cutover. Only revoke the old credential after confirming all instances use the new one, except in compromise scenarios requiring emergency revocation. Introspection outages must fail closed; never treat a dependency error as an active token.
