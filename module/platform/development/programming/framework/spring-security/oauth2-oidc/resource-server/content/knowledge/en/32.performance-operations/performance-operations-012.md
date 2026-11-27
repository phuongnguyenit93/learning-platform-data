# Checking Clocks, DNS, TLS, Proxies, and Environment Configuration During Incidents

## 1. Why Do Resource Server Incidents Often Originate Outside Authentication Code?

A Spring Security OAuth 2.0 Resource Server API may return 401, fail to fetch JWKS, fail to introspect opaque tokens, or fail in only one environment even though application code and tokens have not changed. The root cause often lies in system clocks, DNS, TLS certificates, proxies, or configuration loaded at startup.

A Bearer token request involves two distinct connection paths:

~~~text
API client
   |
   | HTTPS + Authorization: Bearer ...
   v
Load balancer / reverse proxy / ingress
   |
   | internal HTTPS or HTTP
   v
Spring Security Resource Server
   |
   | outbound HTTPS: discovery / JWKS / introspection
   v
Authorization Server / OpenID Provider
~~~

- **Inbound path:** clients connect to the API via gateways, load balancers, reverse proxies, and the application. Incidents here typically involve listeners, routes, forwarded headers, TLS termination, path rewrites, or stripped headers.
- **Outbound identity path:** the Resource Server connects to issuer metadata, JWKS endpoints, or introspection endpoints. Incidents typically involve DNS, egress proxies, TLS trust, proxy authentication, timeouts, or provider availability.
- **Local validation path:** the application checks JWT claims using its clock and loaded configuration. Incidents typically involve clock skew, wrong issuer/audience, wrong profiles, or inconsistent environment configuration.

The first step in incident triage is identifying which hop is failing. Never start by widening clock skew, disabling certificate validation, or altering issuer URLs without evidence.

## 2. Classify Symptoms Before Changing Configuration

| Symptom | First Area to Check |
|---|---|
| JWT works on developer laptop but rejected on server | Clock, issuer/audience, key/config profile |
| Error appears only after deploy or restart | Environment variables, secret mounts, config precedence |
| Cannot fetch OpenID discovery document | DNS, egress proxy, TLS, issuer URI |
| Cannot fetch JWKS or key rotation fails to take effect | DNS, proxy, TLS, JWKS cache, key ID |
| Opaque tokens return 401 en masse | Introspection endpoint, client credentials, TLS, proxy |
| TLS handshake error or PKIX path building failed | Truststore, certificate chain, hostname, SNI |
| API works directly but fails through gateway | Forwarded headers, routes, host/path rewrites, Authorization header |
| Redirect/callback or issuer URL uses HTTP/internal host | TLS termination and forwarded headers |
| Only one node in the cluster fails | Node clock, DNS cache, truststore, environment/config drift |
| Intermittent time-dependent failures | DNS resolver, connection pool, proxy, IdP, NTP, network timeouts |
| New tokens rejected after key rotation | JWKS refresh/cache, DNS, issuer metadata, and key selection |

Record timestamp, node/pod, endpoint, issuer alias, error category, request ID, and the latest deployment change. Never put access tokens, refresh tokens, private keys, client secrets, or full `Authorization` headers into tickets or logs.

## 3. System Clocks and JWT Timestamps

### 3.1. Why Does Clock Skew Cause JWTs to Be Rejected?

JWTs commonly carry NumericDate claims:

- `exp` — expiration time of the token.
- `nbf` — not-before time when the token becomes valid.
- `iat` — issued-at time of the token.

The Resource Server compares these claims against its current clock. If the Authorization Server and Resource Server clocks drift apart, tokens can be evaluated as expired or not yet valid right after issuance.

Example:

~~~text
Authorization Server clock: 10:00:00
Resource Server clock:      10:02:30
JWT exp:                    10:01:00

The AS just issued a token valid for 60 seconds,
yet the Resource Server already considers it expired.
~~~

Drift in the opposite direction can reject tokens whose `nbf` appears to be in the future. Clock drift on a single node triggers failures only when the load balancer routes requests to that node.

### 3.2. Checking UTC, Timezones, and NTP Synchronization

JWT NumericDate values use Unix epoch time, independent of display timezones. Still, misconfigured timezones make logs hard to correlate and can mislead operators about incident timing.

On Linux:

~~~bash
date -u
timedatectl status
timedatectl timesync-status
chronyc tracking
chronyc sources -v
~~~

On Windows:

~~~powershell
Get-Date
Get-Date -AsUTC
w32tm /query /status
w32tm /query /source
~~~

Verify current UTC time, NTP service status, time source, offset, last successful synchronization, and consistency across nodes. Determine whether hosts/pods use an independent clock or the node's clock.

If resynchronization is needed, follow OS and infrastructure operational procedures. For instance, on Windows `w32tm /resync` can be used when accounts and policy permit. Never manually jump system time on a live production node running workloads, as that can disrupt databases, schedulers, TLS validity, distributed locks, and audit chronologies.

### 3.3. Reading JWT Timestamps Safely

During diagnosis, decode the payload in a test environment to inspect `iat`, `nbf`, and `exp`. Payload decoding does not verify signatures; never treat decoded content as proof of a trustworthy token.

Cross-check:

- When was the token issued in UTC?
- When did the Resource Server receive the request?
- Is `exp` in the past relative to the node's clock?
- Is `nbf` in the future?
- Is clock skew configured consistently across instances?
- Did the issuer mint tokens with abnormal timestamps?

Never paste production tokens into public JWT decoder websites. When inspecting claims, use internal tools or synthetic fixtures stripped of sensitive data.

### 3.4. Clock Skew in Spring Security

Spring Security uses a timestamp validator when verifying JWTs. You can configure a clock-skew tolerance for minor drift across hosts:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(JWK_SET_URI).build();

    JwtTimestampValidator timestamps =
        new JwtTimestampValidator(Duration.ofSeconds(60));

    OAuth2TokenValidator<Jwt> issuer =
        new JwtIssuerValidator(TRUSTED_ISSUER);

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuer,
            timestamps
        )
    );

    return decoder;
}
~~~

This is an illustrative example; retain your application's other validators, especially audience and token profile checks. Keep clock skew small and grounded in real measurements. Overly large skew extends how long tokens remain accepted past `exp` or before `nbf`.

**Clock skew does not replace NTP.** If nodes drift by minutes or hours, fix time synchronization first. Skew settings exist only to absorb small, intentional operational tolerances.

### 3.5. Testing Time Deterministically

Unit tests for application-controlled code should use an injectable `Clock` rather than depending on wall-clock time:

~~~java
@Bean
@Primary
Clock applicationClock() {
    return Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
    );
}
~~~

This example applies to services using `Clock`. Do not assume a `Clock` bean automatically controls every decoder's internal clock; when testing validators/decoders, configure clock/skew via the API supported by your Spring Security version or generate test token fixtures with deterministic timestamps.

## 4. DNS and Authorization Server Reachability

### 4.1. DNS Sits on the Outbound Identity Path

When configuring a Resource Server with an issuer URI, the framework may access metadata discovery to locate the JWKS URI. When JWTs arrive, the decoder must connect to the JWKS endpoint for public keys. For opaque tokens, the introspector must resolve the introspection endpoint host.

DNS failures can surface as:

- `UnknownHostException`.
- Name or service not known.
- Temporary failure in name resolution.
- Connection timeouts after resolving to a stale IP.
- One pod resolving the hostname while another pod fails.
- Private DNS zones not associated with the subnet/cluster.
- Search domains or split-horizon DNS returning different answers per environment.

### 4.2. Checking DNS from the Actual Runtime

Testing from a laptop is insufficient when the app runs inside Kubernetes, containers, VMs, or private subnets. Run checks from the exact network namespace or a diagnostic pod sharing the same DNS and network policies.

Linux:

~~~bash
getent hosts id.example.test
nslookup id.example.test
dig id.example.test A
dig id.example.test AAAA
cat /etc/resolv.conf
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName id.example.test
nslookup id.example.test
ipconfig /all
~~~

In Kubernetes, run a diagnostic pod in the matching namespace and network policy. Do not install extra packages into production images solely for temporary checks when ephemeral debug containers are available.

Check both A and AAAA records. An environment with AAAA records but broken IPv6 routing can hit timeouts even when IPv4 works. Confirm DNS returns the intended private or public addresses.

### 4.3. DNS Caching and TTL

DNS resolvers, JVMs, and HTTP clients can cache answers per TTL or internal policy. Updating a DNS record does not guarantee every JVM switches to the new IP immediately.

When checking:

- Record DNS answers and TTLs.
- Compare answers across nodes.
- Check the JVM DNS cache policy.
- Check whether HTTP connection pools hold open connections to old IPs.
- Check whether an outbound proxy resolves hostnames on the proxy side.
- After DNS updates, monitor convergence across the TTL/cache window.

Do not blindly flush caches or restart the entire cluster as step one. Identify which layer caches stale values and perform rolling restarts if required by deployment procedures.

### 4.4. Distinguishing DNS Errors from TCP/Egress Errors

If the hostname resolves yet connections fail, check routing, firewalls, security groups, network policies, proxies, and ports.

Linux:

~~~bash
nc -vz id.example.test 443
curl -v --connect-timeout 5 https://id.example.test/
~~~

Windows:

~~~powershell
Test-NetConnection id.example.test -Port 443
curl.exe -v --connect-timeout 5 https://id.example.test/
~~~

Curling the root path proves only that an HTTP/TLS connection was established or pinpoints which layer failed. It does not prove the discovery, JWKS, or introspection endpoint is correct. Continue testing the exact URL configured in the Resource Server.

### 4.5. Discovery, JWKS, and Issuer URIs

With an issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

The Resource Server may need to fetch discovery metadata from the issuer to find the JWKS URI and verify the issuer. Check:

- Do the issuer URL scheme, host, path, and realm/tenant match?
- Does the metadata endpoint return HTTP 200?
- Does the `issuer` field in metadata match the configured issuer?
- Does `jwks_uri` use a hostname resolvable from the runtime?
- Does the JWKS endpoint return valid JSON containing the key matching the token header `kid`?
- Is a proxy blocking or rewriting the discovery path?

Never pull a URL from an old log and assume it is still current configuration. Inspect the loaded effective configuration and live metadata in the target environment.

### 4.6. JWKS Caching and Key Rotation

Resource Servers typically cache public keys to avoid fetching JWKS per request. When the issuer rotates signing keys:

- Old tokens may still use the old key during overlap.
- New tokens may carry a new `kid`.
- The Resource Server must fetch the updated JWKS or refresh per decoder behavior.
- Proxies, DNS, or caches might still route to an old endpoint.
- One node may have refreshed while another has not.

Inspect `kid` in the JWT header and key IDs in JWKS. The `kid` header is only a key-selection hint, not proof of trust. Do not flush caches across all nodes before understanding refresh behavior and provider load.

## 5. TLS, Certificate Chains, Hostnames, and Truststores

### 5.1. Two Separate TLS Connections

A Resource Server architecture typically involves at least two TLS sessions:

1. Client -> API gateway/ingress/Resource Server (inbound).
2. Resource Server -> Authorization Server/JWKS/introspection (outbound).

The inbound certificate is presented by the gateway or app to clients. The outbound certificate is presented by the issuer to the Resource Server. The Resource Server JVM's truststore typically governs outbound connections; ingress certificate configuration governs inbound connections.

An inbound TLS error is not necessarily a JWKS TLS error. Identify which TLS handshake failed.

### 5.2. Common TLS Errors

| Error / Symptom | Possible Cause |
|---|---|
| `PKIX path building failed` | JVM does not trust the CA or intermediate certificate is missing |
| `unable to find valid certification path` | Truststore lacks the required CA |
| `No subject alternative DNS name matching` | Hostname does not match certificate SAN |
| `Certificate expired` / `not yet valid` | Certificate expired or system clock wrong |
| `handshake_failure` | Incompatible TLS version, cipher, mTLS, or server policy |
| `Received fatal alert: certificate_unknown` | Peer rejects the certificate or chain |
| Connection reset during handshake | Proxy/firewall/TLS inspection or peer closing connection |
| Works with curl, fails in JVM | curl and JVM use different truststores, providers, or TLS configs |

### 5.3. Inspecting Certificate Chains and SNI

Use OpenSSL from the actual runtime/network path if available:

~~~bash
openssl s_client -connect id.example.test:443 -servername id.example.test -showcerts -verify_return_error
~~~

`-servername` sets SNI. Omitting SNI against a multi-tenant virtual host can return a default certificate with a mismatched hostname.

Verify:

- Does the leaf certificate SAN include the target hostname?
- Is the certificate valid in UTC?
- Is the intermediate chain complete?
- Is the root CA present in the active truststore?
- Was a certificate rotated around deployment time?
- Is a TLS-inspection proxy substituting certificates with an internal CA?
- Is the JVM using a different truststore than curl/OpenSSL?

Never inspect only the subject CN; modern hostname verification relies on Subject Alternative Names.

### 5.4. Inspecting the JVM Truststore

Check the Java runtime:

~~~bash
java -version
~~~

Where process arguments can be inspected safely, check properties such as `javax.net.ssl.trustStore` and `javax.net.ssl.trustStoreType`. Never dump full environments or process command lines into tickets if they could hold secrets.

Inspect truststore contents:

~~~bash
keytool -list -v -keystore /path/to/truststore.p12 -storetype PKCS12
~~~

This command may prompt for a password; supply it via prompt or secret manager per procedure, never recording passwords in shell history or logs.

An application may use the JDK default truststore, a custom truststore, a container CA bundle, or a Spring Boot SSL bundle. Identify which mechanism is active rather than importing a CA into a file the JVM never reads.

### 5.5. Updating CAs Safely

When an internal CA is required:

1. Verify the fingerprint/certificate chain from a trusted infrastructure source.
2. Identify the truststore/bundle the process actually reads.
3. Add the required CA through change management.
4. Keep hostname verification enabled.
5. Restart or refresh the workload per reload procedures.
6. Verify the TLS handshake and real discovery/JWKS/introspection calls.
7. Track certificate expiry and rotation.

Never disable trust validation, hostname verification, or install a trust-all manager as a "quick fix". Doing so strips protection against Authorization Server impersonation.

### 5.6. Mutual TLS (mTLS)

When an IdP or gateway requires client certificates, check both sides:

- Client certificate is unexpired and carries the `clientAuth` EKU.
- Private key matches the certificate.
- Server trusts the client certificate chain.
- JVM/application loads the right keystore.
- Proxies forward or terminate mTLS per contract.
- Certificate identity maps to the right client/service.

An outbound mTLS client certificate is distinct from a certificate-bound access token. A successful mTLS handshake does not by itself prove token binding or request authorization.

## 6. Proxies, Reverse Proxies, and Forwarded Headers

### 6.1. Identify Which Direction the Proxy Sits On

Your topology may involve:

- An outbound forward proxy for Resource Server calls to issuer/JWKS/introspection.
- An inbound reverse proxy/load balancer in front of the API.
- A service mesh sidecar intercepting outbound/inbound traffic.
- A TLS-terminating ingress.
- An API gateway performing preliminary auth or route rewrites.

Do not lump all of these into a generic "proxy issue". Each proxy has distinct routing, trust boundaries, and logs.

### 6.2. Outbound Proxies

If the JVM must traverse a corporate proxy to reach the issuer, proxy settings can affect discovery and JWKS. Depending on the HTTP client/transport, proxies may be configured via JVM system properties or client-specific settings.

Common JVM properties:

~~~text
https.proxyHost
https.proxyPort
http.proxyHost
http.proxyPort
http.nonProxyHosts
~~~

Never assume every Spring Security decoder, `WebClient`, or HTTP client shares the exact same proxy settings. Inspect the actual transport configured for your decoder/introspector. If the proxy requires authentication, use secure secret injection; never embed proxy passwords in YAML or command lines.

Check:

- Are proxy host and port correct on the pod/node?
- Is the issuer host unintentionally listed in `nonProxyHosts`?
- Does the proxy allow `CONNECT` to port 443?
- Does the proxy require authentication?
- Does TLS inspection swap certificates?
- Is DNS resolved by the client or by the proxy?
- Are proxy timeouts or connection limits being hit?

### 6.3. Inbound Reverse Proxies and TLS Termination

A client might call:

~~~text
https://api.example.test/api/orders
~~~

While the backend receives an internal connection:

~~~text
http://orders-service:8080/api/orders
~~~

If the application builds absolute URLs, redirects, issuer metadata, or checks origins from requests, it needs the true external scheme and host. Spring Boot handles forwarded headers through an appropriate server forward-headers strategy.

Example:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The exact setting depends on the Spring Boot version and infrastructure. Use native container support or framework strategy per version-matched guidance. Never trust forwarded headers on endpoints reachable directly from untrusted clients.

### 6.4. Forwarded Headers Cross a Trust Boundary

Common headers:

~~~http
Forwarded: proto=https;host=api.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

If the backend trusts any value sent by a client, an attacker can spoof scheme, host, or prefix. Trusted proxies must strip client-supplied forwarded headers and write their own values. The backend should accept forwarded metadata only from designated proxy/network paths.

Check:

- Does ingress strip client-supplied forwarded headers?
- Does ingress set accurate proto, host, port, and prefix?
- Can the backend be reached directly from the Internet or untrusted networks?
- Are multiple proxy hops configured with consistent forwarded-chain ordering?
- Is a path prefix added or stripped twice?
- Does the Spring app generate accurate external URLs?

### 6.5. Proxies Dropping the `Authorization` Header

Some gateway routes or filters strip or overwrite `Authorization`. The symptom is the API receiving requests with an anonymous authentication context or returning 401.

Compare the request at the client, gateway access logs (logging presence only, never token values), and the backend. Check route policies, header allowlists, token relay settings, and gateway authentication modes.

Never demand logging full bearer tokens to debug this. Log a boolean `authorization_header_present`, scheme name, request ID, and gateway route ID.

### 6.6. Path Rewrites and Security Matchers

A proxy might translate:

~~~text
Public:  /gateway/orders/42
Backend: /api/orders/42
~~~

If security matchers or forwarded prefixes disagree, requests can hit the wrong filter chain or fail endpoint matchers unexpectedly.

Record the public URI, backend URI, context path, servlet path / path within application, and chain matchers. Test through the real ingress/gateway setup when errors appear only in production.

## 7. Environment Configuration and Configuration Drift

### 7.1. One Codebase Can Receive Different Configurations

Spring Boot loads configuration from multiple sources: packaged config files, profile-specific files, environment variables, command-line arguments, external configs, and secret mounts. Effective values can differ across local, test, staging, and production.

Key Resource Server properties:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Support and behavior for audience properties depend on your Spring Boot/Spring Security version or custom configuration. If your project version lacks that property, configure an audience validator in code. Never copy YAML from another version without verifying effective configuration.

### 7.2. Checking Active Profiles and Effective Configuration

Check:

- Active Spring profiles.
- Resolved issuer URI and JWKS URI.
- Audience allowlist.
- Introspection URI and client ID (never print secrets).
- Proxy host, port, and non-proxy rules.
- SSL bundle / truststore reference.
- Clock skew and token validators.
- Timeouts, connection pools, and cache settings.
- Ingress host/path and forward-header strategy.
- Secret version and mount timestamp.

Spring Boot Actuator can expose health and environment details depending on configuration. Never expose `env` or `configprops` publicly without authentication and sanitization; they can leak sensitive configuration.

### 7.3. Environment Variables and Property Names

Environment variables override YAML. Spring Boot relaxed binding maps property names to uppercase/underscore formats per Boot rules. When debugging, inspect actual variables in container deployment manifests and secret references—not just YAML files in the repository.

Never dump all environment variables. Inspect only an allowlist of non-secret keys or redacted values. For secrets, verify presence, version, and mount path without displaying values.

### 7.4. Secret Rotation and Config Reloads

An introspection client secret, truststore password, or private key may be rotated in a secret manager while a running application process still holds the old value.

Check:

- Which secret version is mounted into the workload.
- Whether mounted files/volumes actually updated.
- Whether the app supports live reload or reads config only at startup.
- Whether the pod rollout replaced every instance.
- Whether old and new secrets overlap per the IdP's contract.
- Whether any older node is still receiving traffic.

Never paste secrets into tickets or chat, or copy them into logs. Use secret references and version identifiers.

### 7.5. Multiple `SecurityFilterChain` Configurations

An application may define multiple `SecurityFilterChain` beans with distinct `@Order` and `securityMatcher` rules. A request may match a chain that does not even contain the Resource Server config an operator is inspecting.

Verify which matcher handles public vs. backend URIs, which chain enables `oauth2ResourceServer()`, whether a catch-all chain precedes the API chain, whether a gateway path rewrite alters matching, and whether test profiles swap security configs.

Enable Spring Security debug logging only temporarily in controlled environments; avoid leaving verbose authentication logs running indefinitely in production.

## 8. Outbound HTTP and Timeout Configuration

Discovery, JWKS, and introspection are outbound HTTP dependencies. Overly short timeouts cause intermittent failures; overly long timeouts tie up request threads or reactive resources too long.

Distinguish:

- DNS lookup timeout.
- TCP connect timeout.
- TLS handshake timeout.
- HTTP response timeout.
- Connection pool acquisition timeout.
- Retries and backoff.
- Circuit breaker / open state.
- JWKS cache refresh timeout.

Do not simply raise every timeout. Measure latency at each hop and choose timeouts aligned with your service-level objective. In reactive stacks, use non-blocking HTTP clients and avoid calling blocking APIs on the event loop.

For opaque tokens, introspection usually sits on the request path, so IdP availability and latency affect the API directly. For JWTs, cached keys allow the API to keep verifying tokens during brief IdP outages, though key rotations or cache misses can still fail requests.

## 9. Ordered Diagnostic Workflow

A practical runbook follows these steps:

~~~text
1. Capture request ID, timestamp UTC, node/pod, route and status.
2. Confirm Authorization header reached the application (presence only).
3. Confirm which SecurityFilterChain handled the request.
4. If JWT: inspect issuer/audience/time/key ID validation category.
5. If remote key/introspection lookup failed:
     a. resolve hostname from the application runtime
     b. test TCP route and proxy path
     c. inspect TLS chain, SNI and truststore
     d. call the exact discovery/JWKS/introspection URL
6. Compare effective non-secret configuration across healthy and failing nodes.
7. Check NTP offset and DNS/cache differences between nodes.
8. Reproduce with a synthetic token and controlled environment.
9. Apply the smallest verified correction and roll out safely.
10. Confirm recovery across all nodes and monitor error rate.
~~~

### 9.1. Start from a Specific Request

Record:

- UTC timestamp.
- Request/correlation ID.
- API route and HTTP method.
- Backend node/pod.
- HTTP status.
- Error category, exception class, and sanitized cause.
- Token type (JWT/opaque/DPoP) and issuer alias.
- Timestamp of the most recent deploy, config change, or secret rotation.

Never record raw tokens, sensitive claims, PII, or client secrets.

### 9.2. Determine Whether the Token Reached the Application

If the gateway received the request yet the backend never saw an `Authorization` header, fix the gateway route/header policy. If the backend received the header yet built no `Authentication`, inspect filter chains, schemes, token extraction, and decoder/introspector errors.

### 9.3. Distinguish Local vs. Remote Validation Failures

JWT signature/claims validation can fail without any network call when keys are cached. If errors show `UnknownHost`/`SSLHandshake`/timeouts, identify whether the actual outbound URL is issuer discovery, JWKS, or introspection.

### 9.4. Compare Healthy and Failing Nodes

Compare two nodes serving the same traffic:

- Clock offset.
- DNS answers.
- JVM version and truststore.
- Active profiles and effective issuer.
- Secret version.
- Proxy settings.
- Pod image digest.
- Security chain/config revision.

If only one node fails, inspect node drift before changing cluster-wide policies.

## 10. Practical Diagnostic Commands

### 10.1. Linux / Containers

~~~bash
date -u
timedatectl status
getent hosts id.example.test
cat /etc/resolv.conf
curl -v --connect-timeout 5 https://id.example.test/realms/shop/.well-known/openid-configuration
openssl s_client -connect id.example.test:443 -servername id.example.test -showcerts
~~~

### 10.2. Windows PowerShell

~~~powershell
Get-Date -AsUTC
w32tm /query /status
Resolve-DnsName id.example.test
Test-NetConnection id.example.test -Port 443
curl.exe -v --connect-timeout 5 https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

### 10.3. Inspecting Metadata and JWKS

Once the discovery endpoint responds, verify:

- The issuer in metadata matches configuration.
- The JWKS URI resolves and connects from the application runtime.
- The JWKS response is valid JSON.
- A key with the `kid` used by new tokens is present.
- Key type/algorithm are compatible with the token.
- Certificates and hostnames for both discovery and JWKS endpoints are valid.

Never assume discovery and JWKS share a hostname. Providers can host JWKS on a separate domain, so check DNS, proxy, and TLS for each hostname individually.

### 10.4. Inspecting TLS in the JVM

If OpenSSL/curl succeeds while the JVM fails, compare CA bundles, truststores, TLS providers, proxies, and Java runtimes. You can temporarily enable bounded SSL debugging in a test/staging environment:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

This output is verbose and can contain environment details. Enable it only temporarily, bound duration/traffic, store securely, and turn it off immediately after gathering evidence.

## 11. Logs, Metrics, and Health Checks

### 11.1. Log by Error Category

Classify errors so the failure domain is clear:

| Category | Example |
|---|---|
| `jwt_expired` | Token expired per clock validator |
| `jwt_not_yet_valid` | `nbf` outside clock skew |
| `jwt_issuer_invalid` | Issuer mismatch |
| `jwt_audience_invalid` | Audience mismatch |
| `jwks_dns_failure` | Failed to resolve JWKS host |
| `jwks_tls_failure` | TLS trust/hostname failure |
| `jwks_http_failure` | HTTP status/timeout from JWKS |
| `introspection_unavailable` | Introspection dependency error |
| `proxy_connect_failure` | Failed to connect to outbound proxy |
| `forwarded_header_mismatch` | Wrong external host/scheme/path |
| `configuration_mismatch` | Node running a different issuer/profile/secret version |

Logs should carry request ID, node ID, issuer alias, dependency hostname alias, error category, and elapsed time. Never log `Authorization` headers, compact JWT strings, refresh tokens, private JWKs, client secrets, or truststore passwords.

### 11.2. Metrics

Useful metrics:

- Authentication successes/failures by error category.
- JWT validation failures by issuer alias and reason.
- JWKS fetch latency, error count, and cache refreshes.
- Introspection latency, errors, and timeouts.
- DNS/TCP/TLS connection failures if exposed by transport.
- Clock offset / NTP sync health from node monitoring.
- Request 401/403 rates by route.
- Proxy connection pool saturation.
- Number of nodes/pods running each config revision.

Never use raw subjects, tenant IDs, token IDs, or URLs containing user IDs as high-cardinality metric labels.

### 11.3. Readiness and Liveness

Liveness should reflect whether the process is healthy; do not restart apps simply because the IdP is briefly unavailable.

Readiness may reflect critical dependencies per service policy, while avoiding restart storms or pulling all instances out of the load balancer during a global issuer incident. A JWT Resource Server with cached JWKS can continue handling known tokens in several scenarios; opaque introspection depends more directly on the IdP.

Never expose Actuator health details publicly to anonymous Internet traffic. Protect endpoints and sanitize dependency metadata.

## 12. Component-Specific Incidents

### 12.1. Clock Drift on a Single Node

**Signal:** same token, same request, yet only one pod returns 401; error mentions expired/not-before.

**Check:** NTP source, UTC offset, node time, container runtime, and log timestamps.

**Fix:** repair time synchronization per platform runbook, confirm offset converges, then replay requests with a fresh token. Never widen cluster-wide clock skew to hide one node's drift.

### 12.2. DNS Fails Only Inside the Cluster

**Signal:** laptop reaches the issuer, yet pods fail to resolve; `UnknownHost` or timeout errors.

**Check:** pod resolver config, CoreDNS, private DNS zones, network policies, A/AAAA records, and DNS answers per node.

**Fix:** fix zones, forwarders, or network policies, wait for TTL/cache convergence, and verify per pod. Never hardcode the IdP's IP inside the application when hostname/SNI/certificate contracts require a domain name.

### 12.3. TLS Trust Fails After Certificate Rotation

**Signal:** worked before deploy; after IdP/ingress rotated its certificate, the JVM reports PKIX failures.

**Check:** new certificate chain, issuer CA, intermediates, active truststore, certificate validity, and SNI.

**Fix:** update the managed CA bundle/truststore, test outbound TLS, and roll out cleanly. Keep hostname verification enabled.

### 12.4. Proxy Blocks the JWKS Endpoint

**Signal:** discovery host is reachable, yet `jwks_uri` times out or returns 403; fails only on production egress.

**Check:** whether the JWKS hostname is in the proxy allowlist, `CONNECT` policy, non-proxy rules, proxy authentication, and TLS inspection.

**Fix:** update egress policy for the exact endpoint and re-verify from the application runtime. Never disable TLS validation to bypass proxy inspection.

### 12.5. Issuer URI Differs Between Staging and Production

**Signal:** token is validly signed, yet the issuer validator rejects it; metadata issuer disagrees with config.

**Check:** effective issuer property, trailing slash/path/realm, active profile, ConfigMap/secret revision, and `iss` claim in the token.

**Fix:** align canonical issuer URI per provider contract, update config, and roll out. Never alter the token's issuer claim or drop the issuer validator to force requests through.

### 12.6. Reverse Proxy Reports HTTP to the Backend

**Signal:** the application emits redirects or absolute URLs with `http` or internal hosts even though clients called `https` and the public host.

**Check:** TLS termination, `Forwarded`/`X-Forwarded-*` headers, proxy stripping/rewrites, and Spring forward-headers strategy.

**Fix:** configure trusted proxies, strip untrusted forwarded headers, send accurate external metadata, and restrict direct backend access.

### 12.7. One Node Still Uses an Old Secret or Truststore

**Signal:** some requests to the same endpoint succeed while others fail; errors isolate to specific pods.

**Check:** image/config revision, mounted secret version, truststore checksum, startup timestamp, and rollout status.

**Fix:** complete the rolling deployment, drain old instances per procedure, and verify every pod runs the same revision. Never copy secrets into logs to compare them; compare version IDs or checksums instead.

## 13. Safety When Enabling Debug Logs and Collecting Evidence

Spring Security supports `DEBUG`/`TRACE` logging to observe filter chains and authentication flows. Use it temporarily in controlled environments, bounded by logger/package and duration.

Before sharing logs externally, redact:

- `Authorization`/Bearer headers.
- Compact JWT strings and refresh tokens.
- Client secrets and introspection credentials.
- Private keys and keystore/truststore passwords.
- PII in claims, plus tenant/user identifiers.
- Internal hostnames/IPs if classified as sensitive.
- Private certificate material.

You can log issuer aliases, `kid`, thumbprint prefixes, host aliases, status codes, request IDs, and error categories if policy allows. You never need to log full tokens just to see whether a node picked up a new key ID.

## 14. Sample Incident Runbooks

### Scenario A — All JWT Requests Return 401 After a Deploy

1. Confirm UTC timestamp and deploy revision.
2. Check effective issuer/audience configuration.
3. Check clocks/NTP across all nodes.
4. Verify a local decoder using a synthetic token signed with a test key.
5. If key retrieval fails, trace DNS -> proxy -> TLS -> JWKS URL.
6. Compare truststore, secrets, and profiles before vs. after deploy.
7. Restore the last known good config if the recent change caused the failure and rollback is approved.

### Scenario B — Only New Tokens Fail After Key Rotation

1. Read the new token's `kid` from a fixture or sanitized log.
2. Verify the JWKS response includes the matching public key.
3. Verify the Resource Server can reach the updated JWKS host.
4. Check DNS, proxies, TLS, and cache refresh behavior.
5. Confirm the issuer retains overlap between old and new keys per the rotation plan.
6. Verify whether every node has refreshed its key set.

### Scenario C — Intermittent Opaque Token Failures

1. Identify the actual introspection endpoint and outbound client.
2. Measure DNS, connect, TLS, HTTP response, and pool acquisition latency.
3. Check client authentication and secret versions.
4. Check proxy timeouts, rate limits, and IdP availability.
5. Separate invalid/inactive tokens from dependency unavailability.
6. Monitor 401/5xx rates and latency after recovery.

### Scenario D — Fails Only Through the Gateway

1. Compare public and backend request paths.
2. Confirm the `Authorization` header is forwarded.
3. Confirm host/proto/port/prefix forwarded headers.
4. Confirm ingress strips client-supplied forwarded headers.
5. Inspect security chain matchers and context paths.
6. Run integration tests through the ingress or an equivalent staging route.

## 15. How Should Environment Configuration Be Governed?

A configuration baseline should record non-secret settings and their owning sources:

| Category | Configuration to Manage | Authoritative Owner |
|---|---|---|
| Identity | Issuer URI, audience, JWKS/introspection URI | Identity platform |
| Trust | CA bundle, truststore reference, certificate policy | Platform/security team |
| Network | DNS zones, egress proxies, allowlists, routes | Network/platform team |
| Time | NTP sources, max offset policy | Infrastructure |
| Application | Spring profiles, filter chains, validators, timeouts | Application team |
| Secrets | Client secret/cert references and versions | Secret manager |
| Edge | Public hosts, TLS termination, forwarded-header policy | Gateway/ingress owner |
| Observability | Request IDs, error categories, metrics | Operations team |

Values do not need to be identical across environments; they should differ intentionally and under control. For instance, a staging issuer differing from production is normal as long as the token issuer and trust configuration match.

Add startup validation for required properties: valid issuer URI, non-empty audience, positive timeouts, existing truststore, and valid proxy settings. Never log secret values when validation fails.

## 16. Pre-Blame Checklist Before Concluding a Code Bug

- [ ] Identified whether the inbound or outbound hop is failing.
- [ ] Recorded request ID, node/pod, and UTC timestamp.
- [ ] Node clocks are NTP-synchronized with offset within policy.
- [ ] `exp`, `nbf`, and `iat` compared against actual node clocks.
- [ ] Clock skew is small, intentional, and consistent.
- [ ] DNS tested from the real runtime/network namespace.
- [ ] A/AAAA records, TTLs, and DNS caches checked.
- [ ] TCP routing, firewalls, and egress policies verified.
- [ ] Exact discovery, JWKS, or introspection URLs tested individually.
- [ ] TLS chain, SANs, expiry, SNI, and truststore verified.
- [ ] mTLS keystore/certificate checked if required by provider.
- [ ] Outbound proxy, `CONNECT`, authentication, and non-proxy rules verified.
- [ ] Inbound reverse proxy forwards the `Authorization` header.
- [ ] Forwarded headers are trusted only from trusted proxies.
- [ ] Public host/scheme/path match application config.
- [ ] Active profiles and effective issuer/audience confirmed.
- [ ] Secret/truststore versions match across expected nodes.
- [ ] The right `SecurityFilterChain` handles the endpoint.
- [ ] Logs/metrics classify errors without containing credentials.
- [ ] Readiness/liveness avoid restart storms during brief IdP errors.
- [ ] Post-change recovery verified across all nodes with error rates monitored.

## 17. Conclusion

OAuth 2.0/OIDC Resource Server incidents do not always stem from tokens or security code. Clock drift can expire JWTs from one node's perspective; DNS can block discovery/JWKS; TLS trust can halt issuer connections; proxies can drop `Authorization` headers or alter public URIs; and configuration drift can leave pods running mismatched issuers, secrets, or truststores.

Effective diagnosis follows the exact request path:

1. **Clock:** inspect UTC, NTP, and JWT time claims.
2. **DNS/network:** resolve from the real runtime, check routing, and test exact endpoints.
3. **TLS:** verify chains, SANs, SNI, truststores, and mTLS.
4. **Proxies:** separate outbound proxies from inbound reverse proxies; inspect header and URI forwarding.
5. **Environment:** compare effective configuration, profiles, secret versions, and node revisions.
6. **Observability:** use request IDs, error categories, and metrics to isolate the failing hop without logging credentials.

Change configuration only after pinpointing the failure domain, then re-verify from the actual runtime across all instances. Never disable TLS validation, drop issuer validation, or widen clock skew excessively to paper over an infrastructure failure.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Multi-tenancy for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot Reference — HTTP Forwarded Headers](https://docs.spring.io/spring-boot/reference/howto/webserver.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
