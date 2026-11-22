# Testing authentication, authorization, and secure connectivity after migration

## 1. Context: upgrading the JDK is not just changing the runtime version

During **Java Advance Compatibility Migration**, the application may have upgraded the JDK, security framework, HTTP client, application server, OAuth/OIDC libraries, digital signing libraries, JDBC drivers, or container configuration. Even when business APIs still compile successfully, these changes can directly impact **authentication**, **authorization**, and **secure connectivity**.

Several common scenarios:

- Users logged in successfully on the old JDK yet cannot log in after upgrading the framework.
- Valid access tokens are rejected due to issuer, audience, signature, or clock differences across machines.
- An API requiring administrator privileges accidentally returns data to a regular account after changing security filters or routes.
- HTTPS clients fail because certificates are no longer trusted, hostnames mismatch, old signing algorithms are restricted, or obsolete TLS protocols are disabled.
- mTLS connections to partner systems fail because the new runtime fails to load the right client certificate.
- Changing store types, security providers, or secret configurations causes the application to look up the wrong private key or trust anchor.
- Integration tests pass because mocks bypass TLS/tokens, yet production fails handshake or authorization.

These errors carry two risk directions: **denial of valid access** (availability) and **allowing invalid access** (confidentiality/integrity). Therefore, post-migration testing must verify both permitted cases and rejected cases, not only test one admin account or one successful HTTPS connection.

Objectives of this lesson:

1. Establish a security contract baseline before migration.
2. Test authentication paths: passwords, login sessions, tokens, OIDC/OAuth2, SAML, or service credentials depending on the system.
3. Test authorization by role, attribute, tenant, resource ownership, and the deny-by-default principle.
4. Test HTTPS/TLS/mTLS, certificate chains, hostname verification, truststores, and keystores on the target JDK.
5. Detect differences in JSSE, security providers, algorithms, cookies, proxies, and runtime configuration.
6. Organize regression/security tests in CI and release with reproducible evidence.

## 2. Distinguishing three layers of security testing

| Layer | Question to answer | Test example |
|---|---|---|
| Authentication | Does the accessing subject have a proven identity? | Valid credentials log in successfully; forged or expired tokens are rejected. |
| Authorization | Is the authenticated identity allowed to perform this action on this resource? | A user cannot read records of another tenant; an admin can access admin pages within scope. |
| Secure channel | Is data transmitted to the right peer through a trusted protocol, certificate, and configuration? | TLS checks certificate chain + hostname; mTLS verifies certificates on both sides. |

The three layers interact yet do not replace one another:

- TLS securing the transport channel does not prove the end user has permission to access a resource.
- Logging in successfully does not guarantee the user is allowed to call every endpoint.
- Having permissions in the database does not guarantee a JWT is valid, unexpired, or issued for the API being called.
- A valid client certificate does not automatically equate to business permissions, unless the system has a policy mapping certificate identity to permissions.

Testing must identify each layer's responsibility. For example, an API gateway may validate JWTs, yet internal services still must enforce per-object access control and never implicitly trust all headers sent by a request.

## 3. Establishing a baseline before upgrading

Before running on the new JDK, save a baseline of the security behavior of the currently operating version.

### 3.1. Inventorying access flows

| Flow | Involved components | Points to record |
|---|---|---|
| Interactive login | Browser, frontend, IdP, application, session store | Redirect URI, callback, cookies, timeout, MFA, logout. |
| API with bearer token | Client, resource server, IdP/JWKS | Issuer, audience, scope, signing algorithm, token expiry, clock skew. |
| Service-to-service | Caller, target service, secret manager | Client credentials, mTLS, rotation, service identity. |
| Data access | App, DB, JDBC driver, database | Authentication mode, TLS, certificates, DB role, access rights. |
| Message broker | Producer/consumer, Kafka/AMQP, broker | SASL, TLS, topic/queue ACLs, client identity. |
| Operations administration | Operator, reverse proxy, admin API | RBAC, privilege escalation, audit trail, network boundaries. |

Record the JDK version and security providers currently in use, framework versions, proxies/gateways, IdP, and how certificates/secrets are distributed. A system may use the new JDK on a developer machine yet still use the old JDK in test workers or production images, so the baseline must be collected in the exact runtime.

### 3.2. Recording the current access policy

Document:

- Which endpoints are public and which endpoints require authentication.
- Accepted token/credential types.
- Roles, permissions, scopes, and data sources determining access.
- Rules governing tenants, organizations, ownership, or user groups.
- Behavior when tokens are missing, wrong, expired, or revoked.
- Session timeout, logout, CSRF, and cookie policies.
- Trusted certificates and CAs, hostname requirements, TLS versions, and cipher policies.
- Secret/certificate rotation processes and expiration handling.

Do not include passwords, private keys, raw tokens, or secrets in baseline reports. Store **non-sensitive metadata** such as issuer, public key ID, expiration dates, policy configurations, and references to secure secret locations.

### 3.3. Choosing reproducible test fixtures

Create test identities with minimum privileges:

~~~text
anonymous             : unauthenticated
user-a / tenant-a     : read resources belonging to tenant-a only
user-b / tenant-b     : read resources belonging to tenant-b only
manager-a / tenant-a  : modify authorized resources within tenant-a
admin-test            : administration with defined scope
service-client-test   : machine-to-machine connection, restricted scope
~~~

Test tokens/certificates must be issued specifically for test environments, with controlled lifetimes and claims. Do not copy production tokens into fixtures or commit production private keys into repositories.

## 4. Testing user authentication

### 4.1. Testing the success path

For each login mechanism supported by the product, verify:

1. Valid credentials are accepted properly.
2. Identity is mapped to the right user ID and tenant.
3. Sessions/tokens are created only after authentication succeeds.
4. MFA or additional verification steps are triggered per policy.
5. Redirects or callbacks return the user to the right allowed domain and path.
6. Identity details display properly without leaking sensitive data.
7. After logout, sessions/tokens undergo the exact published invalidation policy.

Successful login tests can detect changes in password encoders, user stores, cookie parsers, or authentication libraries, yet are insufficient to assert the system is secure.

### 4.2. Rejection cases

Negative scenarios to include:

| Scenario | Expected behavior |
|---|---|
| No credentials sent | Reject with protocol-appropriate status/challenge; do not create a valid session. |
| Wrong password | Do not issue session/token; apply rate-limit/lockout policy if present. |
| Disabled account | Deny access even with the right password. |
| Expired or revoked credentials | Reject and deny access to protected resources. |
| MFA incomplete | Do not treat login state as fully authenticated. |
| Invalid session ID | Cannot access resources requiring authentication. |
| Disallowed redirect URI | Reject or apply allowlist; do not pass tokens to arbitrary domains. |
| Forged token or wrong signature | Reject; do not fall back to an anonymous state with higher privileges. |

For HTTP APIs, missing or invalid credential errors typically involve **401 Unauthorized** and challenge mechanisms, while **403 Forbidden** typically indicates the request was identified yet lacks sufficient permissions. Details may depend on framework and protocol, so verify the specific contract instead of asserting one status across all systems.

### 4.3. Password storage and migration

When upgrading frameworks, password hashing or encoder changes easily prevent old accounts from logging in. The upgrade must handle stored hashes properly, such as algorithm/version prefixes used by the framework.

Principles:

- Do not fall back to storing plaintext or unsalted hashes to quickly fix migration errors.
- When changing algorithms, verifying old hashes and rehashing under the new policy **after a successful authentication** can be supported if design and security requirements allow.
- Do not treat “able to log in” as enough if the system accidentally accepts disallowed weak algorithms/configurations.
- Test accounts created on old versions, new accounts, and partially migrated accounts.

If the framework changes password encoder defaults, deliberate configuration, test data covering all hash generations, and a compatible migration plan are needed.

## 5. Testing OAuth2/OIDC tokens and JWTs

In distributed systems, authentication may occur via OpenID Connect and OAuth2, with access tokens verified by resource servers.

### 5.1. Token attributes to check

| Attribute | Meaning | What to test |
|---|---|---|
| iss (issuer) | Token-issuing organization | Accept only configured issuers. |
| aud (audience) | Intended token recipient | Tokens meant for other APIs are rejected. |
| exp (expiration) | Expiration time | Expired tokens are rejected per clock skew policy. |
| nbf (not before) | Time when token becomes valid | Tokens used too early are rejected. |
| iat (issued at) | Issuance time | Check when policy needs to limit token age. |
| sub (subject) | Subject identity | Maps user/service accurately, avoiding tenant confusion. |
| scope/scp | Token permission scope | Grant only permissions assigned in policy. |
| roles/groups | Role/group claims if IdP uses them | Mapping and role prefixes are unchanged when upgrading frameworks. |
| kid | Signing key identifier | Selects the right public key in JWKS; handles rotation. |
| alg | Signing algorithm | Accept only explicitly allowlisted algorithms. |

Do not trust claims just because Base64 of a JWT can be decoded. Parsing and reading the payload does not prove the signature is valid.

### 5.2. Minimum test suite for JWTs

Generate mock tokens using **test signing keys**, including:

1. Valid token with matching issuer, audience, signature, and scope.
2. Expired token.
3. Token before nbf.
4. Token with wrong issuer.
5. Token using another service's audience.
6. Token missing required scope or role.
7. Token with mismatched signature, tampered payload, or disallowed algorithm.
8. Token with nonexistent kid or unrefreshed JWKS.
9. Token signed with a new key after rotation.
10. Revoked token, if the system has a revocation or token introspection mechanism.

Do not design tests to accept arbitrary tokens so pipelines run easily. In test environments, the resource server still needs to enforce the exact same validation policy, merely substituting a test-controlled issuer/key source.

### 5.3. JWKS and rotation

When changing JDKs/HTTP clients, calling the JWKS endpoint may fail due to TLS, proxy, DNS, or timeouts. When upgrading security libraries, JWKS caching and refresh mechanisms may also change.

Tests:

- Start up with a valid JWKS and verify tokens.
- Rotate signing keys within policy; cache refreshes properly.
- Unrecognized key IDs are handled safely.
- JWKS endpoint temporarily unavailable: the system behaves as expected without skipping signature verification.
- No dependency or truststore disables hostname/certificate validation.

If the environment requires Internet or internal network access to fetch JWKS, CI should use a stable test IdP/JWKS endpoint or suitable test server, alongside integration tests in a production-like environment.

### 5.4. Authorization Code/PKCE, OIDC login, and logout

For browser logins, test end-to-end:

~~~text
Browser ──> Application ──> Identity Provider
   ▲             │               │
   │             └─ callback <───┘
   │                   │
   └── authenticated session / user identity
~~~

Tests should verify:

- state and nonce are used and validated per flow requirements.
- Redirect URI matches the allowlist.
- PKCE is used where appropriate for the client/flow type.
- Authorization codes are not reused outside policy.
- ID tokens are validated for matching issuer, audience, signature, lifetime, and nonce.
- Access tokens and ID tokens are not used interchangeably contrary to their purpose.
- Logout and session invalidation operate per contract.
- Cookies and proxy headers do not lose the exact scheme/host after upgrading the gateway.

Do not equate “IdP returns HTTP 200” with “login flow is securely right”.

## 6. Testing role-based and resource-based authorization

### 6.1. Authentication does not equal authorization

A logged-in user might not be allowed to read all orders; a service with a valid token might only be permitted to call read endpoints; an administrator might only administer a specific tenant.

Common post-migration risks:

- Security filter order or request matchers change, leaving a route unprotected.
- Method security configuration stops taking effect or annotations change.
- Role prefixes or claim mappings differ from before, granting wrong permissions.
- New APIs skip ownership checks at the service layer.
- Endpoints change paths yet old rules no longer match.
- The gateway layer validates tokens yet the backend trusts headers that clients can send themselves.

### 6.2. Role × action × resource matrix

Do not test only “regular user” and “admin”. Model requirements in detail:

| Principal | Read own orders | Read other user's orders in same tenant | Read orders of another tenant | Edit admin settings |
|---|---|---|---|---|
| Anonymous | No | No | No | No |
| User A / tenant A | Yes, per policy | No, unless granted | No | No |
| Manager A / tenant A | Yes | Yes, per management permissions | No | No, unless separately granted |
| Admin tenant A | Per policy | Per policy | No, without cross-tenant permission | Within tenant A scope |
| Global admin test | Per approved special permissions | Per special permissions | Per special permissions | Per global policy |

This is an illustrative example, not the default permission model of every application. “Yes” cells must come from actual policy.

### 6.3. Testing IDOR and cross-tenant isolation

An API like:

~~~http
GET /api/orders/123
Authorization: Bearer <test-token>
~~~

may be safe when user A accesses order 123 belonging to user A, yet unsafe if user A changes the ID to order 124 belonging to tenant B and still receives data.

Test suites should create resources belonging to multiple owners/tenants and then verify:

- Valid tokens of tenant A cannot read, modify, or delete resources of tenant B.
- Incrementing/decrementing IDs or changing routes does not bypass authorization.
- Database query filters preserve tenant boundaries and ownership checks.
- Bulk/export/search endpoints do not skip scope merely because they return multiple resources.
- Caches do not return cross-tenant data due to keys missing tenant/subject.
- Background jobs/async flows still apply the right authorization context, rather than inheriting the previous request's permissions.

This testing is crucial when migration changes the ORM, repository, security framework, or cache because data-layer authorization bugs do not necessarily surface in simple controller tests.

### 6.4. Testing both route-level and method-level security

A URL protection rule does not replace checks in business services if the same service is called from batch jobs, messaging, scheduled jobs, or other interfaces. Conversely, a method-level permission annotation does not guarantee every public endpoint is mapped properly.

When upgrading Spring Security or similar frameworks, verify:

1. Request matchers and security filter chains apply to all expected routes.
2. Different HTTP methods on the same path have different permissions if needed.
3. Method security is actually enabled and proxies/interceptors are applied.
4. Internal/self-invocation methods do not accidentally bypass proxies when designs rely on proxies.
5. Async/scheduled/messaging paths do not carry the wrong security context.
6. Deny-by-default rules apply to newly added undeclared endpoints.

Do not only check that annotations appear in source code; test actual requests or calls to verify permissions are enforced.

## 7. Sessions, cookies, and CSRF after migration

### 7.1. Session lifecycle

For applications using sessions:

- After login, the session binds to the right principal.
- Session ID is rotated when needed to reduce session fixation risk.
- Sessions expire according to idle timeout or absolute lifetime per policy.
- Logout invalidates sessions within the published scope.
- Distributed session stores operate across multiple replicas.
- Key serialization or framework session schemas do not break existing sessions if the system needs rolling upgrades.
- Cookies do not contain credentials in an easily exposed form.

During rolling deployments, instances running old and new versions may read the same session store concurrently. If session objects are Java-serialized, changing classes, serialVersionUID, or framework versions can prevent one node from reading another node's session. A compatibility policy is needed, or controlled logout accepted if published.

### 7.2. Cookie security flags

Check cookies are issued with appropriate attributes:

| Attribute | Role | Scenarios to test |
|---|---|---|
| Secure | Restricts sending cookies over insecure connections. | Proxy TLS termination has forwarded headers configured properly so the app issues Secure cookies. |
| HttpOnly | Reduces page-side JavaScript ability to read session cookies. | Session cookies do not lose the flag under the new framework. |
| SameSite | Controls sending cookies in cross-site contexts. | Login redirects and form flows still work with expected protection level. |
| Domain | Limits domains receiving cookies. | Does not accidentally widen to untrusted subdomains. |
| Path | Limits applicable paths. | Post-migration context paths do not create mis-scoped cookies. |
| Max-Age/Expires | Defines client-side lifetime. | Does not unintentionally turn session cookies into persistent cookies. |

Cookie flags should be chosen according to application architecture and supported browsers; do not set SameSite arbitrarily causing valid OIDC or cross-site flows to fail.

### 7.3. CSRF, CORS, and reverse proxies

CSRF involves browser requests where credentials are sent automatically (especially cookie-based sessions). Upgrading security frameworks may change CSRF defaults or CSRF-ignoring matchers.

Tests:

- State-changing operations via browsers are rejected when missing a CSRF token if policy requires it.
- Valid CSRF tokens are accepted; invalid or expired tokens are rejected.
- APIs using bearer tokens in a non-cookie model have appropriate configuration, without disabling CSRF wholesale across all paths.
- CORS allowlists do not widen to allowing arbitrary origins with credentials.
- Forwarded headers are trusted only from controlled proxies; do not blindly trust X-Forwarded-* headers sent by Internet clients.

Migration may move HTTPS termination from the app server to a gateway, changing how the application detects scheme, host, and secure cookies. Tests must go through a production-like proxy topology, not only call localhost directly.

## 8. HTTPS/TLS: connecting is not enough, the recipient must be verified properly

TLS protects confidentiality, integrity, and endpoint authentication under the trust model. A “successful” HTTPS connection only has security value when the client verifies the certificate chain and server identity per policy.

### 8.1. Common changes when upgrading the JDK

In a new JDK, JSSE configuration, supported protocol and cipher suite lists, default truststores, security providers, and restricted algorithms may differ from the old JDK.

Impacts may include:

- Old servers only support TLS versions or weak ciphers no longer allowed by default on the target JDK.
- Certificate chains use signing algorithms or key sizes no longer accepted.
- Root/intermediate CAs are not in the new runtime's truststore.
- Server fails to send full intermediate certificates.
- SAN does not contain the endpoint hostname, even though the old Common Name looks right.
- Client relies on a trust-all TrustManager or an insecure hostname verifier.
- Proxy TLS termination or SNI/ALPN changes when upgrading the HTTP client.
- Certificate/key stores were converted from JKS to PKCS12 or passwords/aliases changed without updating configuration.

When encountering a handshake failure, **do not** use disabling certificate verification as a migration solution. That change removes endpoint authentication guarantees and can create man-in-the-middle vulnerabilities.

### 8.2. Main components of TLS

~~~text
Java HTTPS Client
  │
  ├─ TrustStore: trusted CAs/certificates allowed
  ├─ TrustManager: checks certificate chain
  ├─ Hostname verification: matches endpoint identity
  ├─ Protocol/cipher policy: accepted algorithms
  └─ (If mTLS) KeyStore/KeyManager: client certificate and private key
  │
  ▼
TLS handshake
  │
  ▼
Server Certificate + Chain + Protocol/Cipher
  │
  ▼
Channel authenticated according to policy
~~~

Truststores and keystores have different roles: a truststore typically holds trust anchors, whereas an mTLS client's keystore holds the certificate/private key the client uses to prove identity. One file can hold multiple entry types, yet configuration should distinguish intended usage.

### 8.3. TLS positive tests

Verify:

1. Connecting to an endpoint with a valid certificate chain and matching SAN.
2. Negotiated TLS protocol and cipher suite belong to the policy allowlist.
3. SNI is sent properly when the server has multiple virtual hosts.
4. Proxies, load balancers, and service meshes do not alter endpoint identity outside design.
5. Retries/timeouts and connection pooling work after upgrading the HTTP client.
6. Certificate rotation is handled without requiring disabling certificate verification.
7. TLS works in the actual container/runtime, not only on the development machine.

Record TLS version/cipher suite as metadata if appropriate to observability policy, yet avoid logging key material or sensitive session contents.

### 8.4. TLS negative tests

Key rejection cases:

| Scenario | Expectation |
|---|---|
| Untrusted self-signed certificate | Connection fails under chain validation. |
| Expired / not-yet-valid certificate | Rejected under validity verification rules. |
| Incomplete certificate chain unable to build a valid path | Connection fails; clearly record the cause. |
| Hostname/SAN mismatch | Rejected, without falling back to ignoring hostname. |
| Server only uses disallowed protocol/cipher | Connection does not negotiate. |
| Certificate signed with an algorithm banned by policy | Rejected; do not lower system-wide standards to suppress the error. |
| Wrong truststore or missing CA | Does not accept servers outside trust policy. |
| Wrong client certificate in mTLS environment | Server rejects under client authentication policy. |

These tests should be placed in a controlled environment, using test CAs/certificates and endpoints owned by the team. Do not disable the application's TLS checks to simulate negative cases.

## 9. Testing mTLS and service identity

In mutual TLS, in addition to the client verifying the server, the server also requires the client to present a valid certificate.

### 9.1. Items to verify

- Client loads the exact alias containing the private key and certificate chain.
- Client certificate is valid and has the appropriate usage purpose and identity.
- Server trusts the CA issuing the client certificate per policy.
- A certificate belonging to service A cannot be used as service B if the system distinguishes service identities.
- Identity mapping from SAN, SPIFFE ID, DN, or other attributes is explicitly configured.
- Client certificate rotation can occur without downtime beyond acceptable limits.
- Connection is rejected if the client lacks a certificate or uses a disallowed certificate.

A successful mTLS handshake proves the certificate constraints of both sides of the connection. It does not determine business permissions on its own; if an API authorizes by service identity, test permissions on resource/service operations separately.

### 9.2. Testing with certificate fixtures

A test certificate set should contain:

~~~text
test-root-ca
  ├─ valid-server.example.test (matching SAN)
  ├─ wrong-host.example.test (SAN mismatches endpoint)
  ├─ valid-client-a (service A identity)
  ├─ valid-client-b (service B identity)
  └─ untrusted-client (signed by another CA)
~~~

Fixtures can be prepared for CI, yet test private keys still need proper management. Do not use production certificates to replicate staging environments.

If tests need to simulate an expired certificate or incomplete chain, use specialized fixtures and a controllable TLS server; do not alter the global runner date/clock if it affects other tests.

### 9.3. TLS termination and service mesh

In architectures with ingress, API gateways, or service meshes, TLS may be terminated or re-established across multiple hops:

~~~text
Browser ── TLS ── Ingress ── mTLS ── Service A ── mTLS ── Service B
~~~

For each hop, determine:

1. Who is the TLS client and who is the TLS server?
2. Which component verifies the other side's certificate?
3. Where are private keys and trust anchors stored?
4. By what mechanism is end-user identity forwarded?
5. Which boundary checks roles/tenants/resources?
6. Which network and identity policies still protect internal traffic?

Testing service A alone over localhost can skip ingress and mTLS; therefore, test through the official deployment path.

## 10. Java JSSE, certificate stores, and security providers

### 10.1. Checking the JDK and actual TLS configuration

In test/CI environments:

~~~bash
java -version
java -XshowSettings:security -version
~~~

Depending on the JDK version, security-related XshowSettings options may not exist or may differ; check java -XshowSettings:help of that exact JDK. keytool can be used to inspect keystores/truststores controlled by the project.

Example listing metadata of a test truststore:

~~~bash
keytool -list -v -keystore test-truststore.p12 -storetype PKCS12
~~~

The command may prompt for a password. In CI, do not put passwords on command lines or in unprotected logs. Secrets must be fetched from a secret manager or a secure input mechanism supported by the platform.

### 10.2. JKS, PKCS12, and JSSE parameters

An application may have previously used JKS, while configuration or keytool on a newer JDK prefers PKCS12. During migration, identify:

- Actual format of the store file.
- Alias of the key/certificate to load.
- Store and key passwords, if any.
- How truststores are loaded in the app server, Java HttpClient, Spring, or other HTTP clients.
- Whether security providers support the algorithms/key formats in use.
- Certificate rotation/reload rules executed by the runtime.

Examples of JVM properties you may encounter:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType
~~~

Do not arbitrarily use one global truststore for all outbound requests if partners require different trust policies. In multi-tenant systems or systems with multiple integrations, separate SSLContexts/HTTP clients per trust boundary may be needed.

### 10.3. Configuring restricted algorithms

Certain security properties control disallowed algorithms/certificates, for example:

~~~text
jdk.tls.disabledAlgorithms
jdk.certpath.disabledAlgorithms
~~~

Exact defaults and behavior depend on the JDK distribution/update. When an old endpoint fails to handshake, find the root cause and upgrade the server-side configuration/algorithms or certificate chain.

**Do not remove algorithm restrictions JVM-wide just so one legacy endpoint can connect**, because that weakens TLS/certificate policy for other connections. If a mandatory security exception exists, it must be evaluated separately with a clear deadline, scope, and mitigation measures.

### 10.4. Security providers and crypto APIs

Applications may use JCA/JCE, PKCS#11, HSMs, hardware tokens, or third-party providers. Upgrading the JDK or provider can change:

- Algorithm names/aliases.
- KeyStore types and how private keys are opened.
- Provider order.
- Supported signature/cipher algorithms and key sizes.
- Behavior when signing/verifying or reading certificates.
- Compatibility with native libraries and drivers/HSMs.

Tests should execute real supported encryption/signing/verification operations in a test environment with the corresponding provider, rather than only checking class initialization succeeds.

## 11. Safe TLS diagnostics

### 11.1. Distinguishing handshake, trust path, and hostname

When an HTTPS connection fails, collect:

- Endpoint host/port and actual DNS name.
- JDK version, runtime image, and client library version.
- Public certificate metadata: subject, issuer, SAN, validity, chain.
- Error category and stack trace with secrets stripped.
- Negotiated or rejected TLS version/cipher, if available.
- Relevant proxy/gateway/service mesh hops.

Common errors:

| Error or signal | Investigation direction |
|---|---|
| PKIX path building failed | Truststore, CA/intermediate chain, certificate path policy. |
| No subject alternative DNS name matching | Hostname/SAN mismatches the real endpoint. |
| handshake_failure | Protocol/cipher mismatch, client auth, policy, or certificate. |
| certificate_unknown | Partner side rejects certificate chain/identity. |
| bad_certificate | Certificate or certificate verification fails policy. |
| No appropriate protocol | TLS version/cipher policy has no intersection. |
| Keystore file/alias not found | Path, store type, alias, packaging, secret injection. |

The same error message can have multiple causes. Do not conclude by reading only the first line of the stack trace.

### 11.2. Using keytool and openssl to observe test endpoints

Check certificate metadata in a test keystore:

~~~bash
keytool -list -v -keystore test-truststore.p12 -storetype PKCS12
~~~

Observe the handshake of a team-controlled endpoint:

~~~bash
openssl s_client -connect api.example.test:443 -servername api.example.test -showcerts
~~~

openssl s_client displays handshake and certificate chain information for investigation, yet seeing “CONNECTED” does not mean hostname/trust was verified properly by the Java client. Verify the verification result and run the actual Java client with the application's policy.

If using curl:

~~~bash
curl -v https://api.example.test/health
~~~

Avoid using options that skip certificate verification to claim a secure connection passes. Some curl builds use a different truststore than the JDK, so curl succeeding does not prove the Java application's JSSE will succeed.

### 11.3. Debugging JSSE handshakes

In a controlled test environment, you can enable:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar application.jar
~~~

TLS debugging can make logs huge and may expose sensitive metadata or session details. Use it only in a secure environment, time-bound, handle logs per security policy, and do **not** leave it enabled by default long-term in production.

Do not log secrets, private keys, full bearer tokens, or passwords merely to fix a handshake. Prefer logging categories, correlation IDs, endpoint logical names, and certificate fingerprints when permitted.

## 12. Testing connections to databases, brokers, and external services

Upgrading Java or drivers affects many channels beyond the application's HTTPS.

### 12.1. JDBC / database

Check:

- Authentication: username/password, Kerberos, cloud IAM, or certificates if used.
- That TLS is actually enabled and certificate/hostname verification is enforced per driver.
- JDBC driver compatibility with the target JDK.
- Whether the database principal has least-privilege permissions.
- Whether connection pools initialize, reconnect, and rotate secrets properly.
- That the server does not require ciphers/protocols rejected by new Java policy.
- That test queries and transactions do not use an account with permissions exceeding production roles.

A successful JDBC connection does not prove the database is encrypting the transport channel; check driver configuration and server verification in the actual deployment path.

### 12.2. Kafka/AMQP/message broker

Environments may use TLS, SASL, mTLS, and ACLs. Tests should cover:

- Producers/consumers with the right principal connecting and reading/writing granted resources.
- Read-only principals cannot write if policy disallows it.
- Access to another tenant's topics/queues is rejected.
- Certificate/secret rotation, reconnect, and failover work properly.
- TLS is not accidentally disabled or plaintext listeners selected after config changes.

If producers send the same data through multiple channels during migration, control idempotency and avoid creating duplicate business side effects.

### 12.3. External services and API gateways

Partners may require OAuth2 client credentials, mTLS, request signing, or API keys. Identify each auth layer separately and test token refresh, secret rotation, certificate identity, and retry/timeout policies.

Do not call production endpoints using unauthorized fixtures. Integration tests need a valid sandbox environment or mocks with confirmed contracts.

## 13. End-to-end testing matrix

A good matrix must combine identity, permissions, and connection channels:

| Scenario | Authentication | Authorization | Secure channel | Expectation |
|---|---|---|---|---|
| User with right role calls owned API | Valid token/session | Has resource permission | Valid HTTPS | Succeeds per contract. |
| Anonymous calls API requiring login | No token | No permission | Valid HTTPS | Rejected, leaks no data. |
| Expired token | Invalid | Not considered valid | Valid HTTPS | Rejected. |
| Valid token yet missing scope | Valid | Lacks permission | Valid HTTPS | Rejected. |
| User A reads tenant B resource | Valid | Wrong tenant/ownership | Valid HTTPS | Rejected. |
| Forged token with admin claim | Invalid signature | Not granted admin | Valid HTTPS | Rejected. |
| Admin calls via wrong cert hostname | Valid credentials | Has permission | Wrong TLS identity | Connection rejected before accepting response. |
| Service A uses client certificate B | May prove another certificate | Wrong service identity | mTLS | Rejected per policy. |
| Rotate valid JWKS/certificate | New token/cert valid | Preserves permissions | Valid TLS/mTLS | Switchover does not widen permissions. |
| Missing or wrong secrets | Cannot authenticate | No privilege escalation | Depends on channel | Fail closed, safe logging. |

The example matrix must be tailored to real policy. A system may use 401, 403, redirects, or different protocols; do not treat all authorization errors as the same HTTP status.

## 14. Writing integration tests and negative tests

### 14.1. Organizing test layers

To increase regression detection capability, divide into:

1. **Security mapping unit tests:** converting claims/roles/scopes, policy evaluators, handling null/missing claims.
2. **Component tests:** resource server with test issuer/JWKS or mock identity provider with real signatures.
3. **Integration tests:** application starting with security filters/method interceptors, database/broker, and test TLS endpoints.
4. **End-to-end tests:** browser login/OIDC/mTLS/gateway through production-like topology.
5. **Post-deploy smoke tests:** checking low-risk access paths without using sensitive production data.

Lower-level tests are faster yet do not replace testing real flows. For example, mocking Authentication in a controller test can bypass all JWT or cookie verification; some flows must be tested through actual security filters.

### 14.2. Authorization test example with JUnit and MockMvc

Illustrative example for a Spring MVC application with security filters enabled in tests:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationTest {

    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadProtectedOrder() throws Exception {
        mvc.perform(get("/api/orders/100"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "user-a", roles = "USER")
    void userCannotReadAnotherTenantsOrder() throws Exception {
        mvc.perform(get("/api/orders/200"))
           .andExpect(status().isForbidden());
    }
}
~~~

This is an illustrative snippet; test imports/dependencies and appropriate order/tenant test data must be added. Actual status also depends on how the application hides resource existence (some systems deliberately return 404 instead of 403). The key is that users must not receive data outside their authorization.

WithMockUser helps test authorization mapping in some cases, yet does not verify JWT signatures, issuers, or token parsing itself. Therefore, integration tests sending bearer tokens issued by a test IdP and running through actual security filters are required.

### 14.3. Token test example with an HTTP client

A high-level test can:

~~~text
1. Start test issuer/JWKS with test signing key.
2. Create token with right issuer, audience, scope, and exp.
3. Call API over HTTPS test endpoint with bearer token.
4. Confirm response code and tenant-matching data.
5. Create token with invalid signature or missing scope.
6. Call API again; confirm it is rejected and leaks no data.
~~~

Those token fixtures use test keys, not real access tokens. If integrating directly with an external IdP, a sandbox environment and test account with minimum permissions are required.

### 14.4. Testing certificates and TLS without trust-all

A TLS integration test can use a test HTTPS server built from certificates issued by a test CA:

- Client trusting the test CA and connecting to the right hostname succeeds.
- Client not trusting the test CA is rejected.
- Client connecting to a hostname outside SAN is rejected.
- Client with/without a certificate when the server requires mTLS is handled per policy.

This is an end-to-end way to verify the verification mechanism. When tests must prove fail-closed behavior, do not create a TrustManager that accepts all certificates or a HostnameVerifier that always returns true.

## 15. Java version, framework upgrades, and risk of default changes

A migration may upgrade simultaneously:

~~~text
JDK 8/11 ──> JDK 17/21
Old Spring Security / framework ──> new framework
Old HTTP client ──> new HttpClient
TLS/Keystore/Provider ──> new configuration
Application Server / Container Image ──> new runtime
~~~

When things change simultaneously, errors may stem from config code rather than directly from the JDK.

### 15.1. Defaults to verify

| Default category | Example differences that may appear |
|---|---|
| TLS protocols/ciphers | Allowed sets and negotiation priorities change. |
| Disabled algorithms | Old certificates or signatures are no longer accepted. |
| Truststore | Root CAs or truststore loaded differently than old environment. |
| Keystore | Different store type/alias/provider; cannot load private key. |
| HTTP redirects | Clients/libraries have different redirect and auth-header policies. |
| Proxy/forwarded headers | Scheme/host detected differently, affecting cookies and redirect URIs. |
| Security filter order | Rules/routes or exception mappings differ. |
| Token claim mapping | `ROLE_` prefixes, scope mapping, or authorities differ. |
| Session serialization | Sessions from old version incompatible with rolling upgrades. |
| Timeouts/retries | Easily exposes race conditions during token refresh or certificate reload. |

Do not assert that all JDKs of the same version have identical security defaults: distributions, patches, and security properties files can differ. CI and production must publish the supported JDK set and record sufficient build/runtime information for traceability.

### 15.2. Separating JDK errors from configuration errors

The investigation process should separate:

1. Run the old artifact on the new JDK if compatible to observe runtime impact.
2. Run the new artifact on the target JDK, recording dependency/framework versions.
3. Compare security settings, truststores, certificates, and proxy paths.
4. Use the same token/certificate fixtures and test policies when possible.
5. Trace errors to filters, token validators, TLS handshakes, authorization policies, or providers.

You do not need to run every combination if technology does not support it; explicitly document infeasible combinations and scope conclusions.

## 16. CI pipeline and managing sensitive test data

### 16.1. Checks that should be automated

A post-migration security pipeline can include:

~~~text
Compile + unit tests
        │
        ▼
Authentication/authorization component tests
        │
        ▼
TLS/mTLS tests with test certificates
        │
        ▼
Integration tests with test IdP/DB/broker
        │
        ▼
Artifact/image verification
        │
        ▼
Staging E2E and security smoke tests
        │
        ▼
Release gate + evidence
~~~

Tests should run on the target JDK and actual deployment runtime. If a product announces support for multiple Java versions, CI should include the corresponding matrix or at least have verification evidence for the declared supported environments.

### 16.2. Secret hygiene

Do not place the following in repositories or build logs:

- Real passwords, API keys, or still-valid bearer tokens.
- Production/staging private keys not meant for CI tests.
- Full keystore dumps or secret manager contents.
- Refresh tokens and session cookies of real users.
- Unnecessary sensitive identifying information in debug traces.

For integration tests requiring credentials, use a secret manager/CI secrets with least privilege, environment isolation, and a rotation process. Test result records should save only metadata/correlation IDs and non-sensitive evidence.

### 16.3. Fail closed, do not make pipelines falsely “green”

Do not:

- Disable all security filters in tests and then conclude auth works.
- Mock a user who always has admin permissions for every endpoint.
- Skip verifying JWT signatures or audiences.
- Use trust-all certificate managers/hostname verifiers to bypass TLS errors.
- Allow unknown roles/scopes to be granted permissions by default.
- Skip failing tests due to unstable IdP/TLS environments without recording missing evidence.

If a test environment lacks a required service or certificate, explicitly report **test not executed** instead of reporting all tests passed.

## 17. Production observability and rollout safety

After upgrading the JDK/security stack, monitor both unexpected rejected failures and wrongly permitted access.

### 17.1. Metrics to monitor

- Login failure rate by non-sensitive cause category.
- Count of 401 and 403 responses and rate of change compared to baseline.
- Count of expired token, issuer/audience mismatch, or JWKS refresh failure events.
- TLS handshake failures and certificate/trust/protocol cause groups.
- mTLS client authentication failures by standardized service identity.
- Count of anomalous cross-tenant access or policy-deny alerts.
- Latency of token verification, IdP redirects, and outbound HTTPS.
- Refresh token failure rate or session resets during rolling deployments.

Do not treat an increase in 403s purely as a bug; it may be properly blocking unauthorized requests. Compare before/after behavior, principals, and policy to distinguish false positives/false negatives.

### 17.2. Rollout and rollback

A safe plan can include:

1. Deploy to staging matching network topology, proxies, certificates, and IdP close to production.
2. Run the regression matrix with positive/negative tests before release.
3. Canary a controlled group of requests/consumers.
4. Observe 401/403s, token validation, handshakes, and backend operations.
5. Have rollback criteria if valid access is blocked en masse or signs of privilege escalation appear.
6. Verify rolling back artifacts, certificates, truststores, session schemas, and dependencies remains feasible.

Do not only roll back the JDK if session data, certificate trust, key rotation, or schemas were migrated one-way. You must know which combinations of JDK + artifact + security configuration are mutually compatible during the transition period.

### 17.3. Certificate and signing key rotation

JDK migration may coincide with key/certificate rotation timing. If both change at once, errors are hard to trace.

Plan to:

- Separate runtime update milestones and rotation milestones if possible.
- Record effective times and expiration dates of keys/certificates.
- Maintain a policy-defined overlap period to avoid disruption when consumers cache JWKS or CA bundles.
- Test tokens signed with both old and new keys during the allowed period.
- Revoke/remove old trust on schedule after consumers have migrated.

Do not extend acceptance windows for expired certificates/tokens merely to prolong migration without a security assessment.

## 18. Post-migration security test report template

A result report should record:

| Field | Content |
|---|---|
| Artifact and commit | Service/library name, version, build ID, checksum. |
| Java runtime | Full version, distribution, OS/container image. |
| Framework/security libraries | Versions of Spring Security/OIDC client/JWT library/HTTP driver. |
| Identity provider | IdP type, test environment, configured issuer (containing no secrets). |
| Authorization policy | Version of rule/role/tenant matrix tested. |
| TLS/mTLS topology | Endpoint logical names, truststore/keystore references, proxy hops. |
| Certificate metadata | Validity, issuer/SAN/fingerprint when permitted; do not store private keys. |
| Test cases | Positive/negative, expected result, actual result, pass/fail. |
| Gaps | Unexecuted tests, missing environment dependencies, staging/production differences. |
| Risk/owner | Remaining issues, responsible person, resolution deadline, or approved exception. |
| Release decision | Accept, block release, needs additional checks, or rollback plan. |

Example of a result recording matrix:

| Test ID | Objective | Expected | Evidence | Status |
|---|---|---|---|---|
| AUTH-01 | JWT with valid issuer/audience/signature is accepted | 2xx for valid resource | Integration test run ID | PASS/FAIL |
| AUTH-02 | JWT with invalid signature is rejected | 401/challenge per contract | Security filter test log | PASS/FAIL |
| AUTHZ-01 | User A does not read tenant B data | Deny or 404 per policy | Data fixture + response | PASS/FAIL |
| TLS-01 | Valid HTTPS certificate chain and SAN | Connection succeeds | TLS test report | PASS/FAIL |
| TLS-02 | Untrusted certificate | Handshake rejected | TLS test report | PASS/FAIL |
| MTLS-01 | Client missing cert on endpoint requiring mTLS | Connection rejected | Mutual TLS test run | PASS/FAIL |
| SESSION-01 | Logout invalidates session per contract | Cannot reuse old session | Browser E2E run | PASS/FAIL |

PASS/FAIL values are only filled in after tests actually run; the table above is a structural template, not results of a specific system.

## 19. Common mistakes

| Mistake | Risk | Remediation |
|---|---|---|
| Testing only successful logins. | Fails to detect bugs allowing forged credentials/tokens. | Also test expired, wrong signature, wrong audience, disabled user. |
| Testing only with admin. | Misses over-permission bugs for regular users/tenants. | Role × action × resource matrix. |
| Checking only routes, not resource ownership. | IDOR/cross-tenant data leaks. | Use multi-tenant fixtures and negative resource tests. |
| Mocking security filters in all integration tests. | Fails to catch framework configuration bugs. | Include tests through filters, token parsers, and test IdPs. |
| Using trust-all SSL to fix handshakes. | Loses endpoint authentication, MITM risk. | Fix CA/truststore/certificate/SAN/protocol properly. |
| Checking server certificates only by CN name. | SAN/hostname mismatch may be bypassed. | Keep standard HTTP client hostname verification. |
| Allowing JWTs with wrong issuer/audience as valid. | Tokens meant for other systems can be misused. | Validate issuer/audience/signature/expiry per allowlist. |
| Allowing unknown roles by default. | Privilege escalation when mappings change. | Deny-by-default and test role mapping. |
| Testing only directly on localhost. | Skips ingress, mTLS, proxy, secure cookies. | Test the real deployment path. |
| Storing raw tokens/keys in logs. | Credential leaks. | Minimal metadata logging and redaction. |
| Mistaking 401/403 for any runtime error. | Misdiagnosis, overlooking TLS or policy failures. | Classify by authn/authz/TLS and stack traces. |
| Upgrading only the JDK without checking dependencies. | Incompatible security providers/drivers/frameworks. | Record dependency graph and test on actual running artifacts. |
| Green tests yet a group of tests skipped. | Missing evidence still treated as passing. | Surface test gaps and release gates. |

## 20. Post-migration execution process

When deploying a security-related JDK/framework upgrade, you can proceed:

**Step 1 — Collect the baseline.** Identify auth flows, security rules, IdP, TLS endpoints, secrets, certificate stores, runtime, and dependency versions.

**Step 2 — Build the risk list.** Group token/credentials, login/session, RBAC/ABAC/tenant, HTTPS/TLS/mTLS, database/broker, and security providers.

**Step 3 — Prepare fixtures.** Create test accounts, tokens, multi-tenant resources, and test certificates; do not use production secrets.

**Step 4 — Positive tests.** Valid logins, API access, service-to-service, and secure connections operate per contract.

**Step 5 — Rejection tests.** Invalid tokens, missing permissions, another tenant's resources, wrong/untrusted certificates, and session/CSRF cases are rejected per policy.

**Step 6 — Test real topology.** Test through gateway/ingress, load balancer, app server, container, and IdP/DB/broker equivalent to the target environment.

**Step 7 — Analyze differences.** Separate causes due to JDK, JSSE/providers, framework security, configuration, secrets/certificates, and environment.

**Step 8 — Standardize configuration.** Fix truststores, certificates, role mappings, security matchers, or token validation. Do not use auth/TLS bypasses to mask regressions.

**Step 9 — Re-test and save evidence.** Run the full positive/negative matrix, save artifact identity, JDK, test results, and gaps.

**Step 10 — Rollout and observe.** Canary/staging first, monitor 401/403s, handshakes, JWT/JWKS, mTLS, and cross-tenant anomalies, with rollback prepared.

## 21. Conclusion

Post-migration Java security testing must simultaneously verify **who is accessing**, **what they are allowed to do on which resource**, and **whether the connection actually authenticates the exact peer over a protected channel**. Upgrading the JDK can change JSSE/TLS/security providers and certificate constraints; upgrading frameworks can change filters, token claim mappings, cookies/CSRF, or method security mechanisms. Therefore, the application compiling and returning HTTP 200 is not enough to assert a safe migration.

A sound strategy requires a baseline, a positive/negative test matrix, safe token and certificate fixtures, testing across real runtime topologies, validation by issuer/audience/signature/scope, tenant/resource ownership control, TLS hostname/certificate chains, and mTLS identity. Results must have reproducible evidence, clearly state untested parts, and avoid any “quick fix” by skipping token verification, skipping authorization, or disabling TLS verification.

When these tests are integrated into CI alongside post-deployment observation, teams can upgrade JDKs, frameworks, and dependencies while preserving valid access contracts, blocking unauthorized access, and protecting data across required connections.
