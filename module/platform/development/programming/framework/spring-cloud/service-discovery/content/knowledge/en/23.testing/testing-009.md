# Testing Network Paths, Certificates, and Denied Access

Service discovery only works when components can connect to the right endpoint, verify peer identity, and hold sufficient permissions for the requested operation. A consumer may fail to find a service because DNS fails to resolve, TCP is blocked, TLS rejects a certificate, the registry demands credentials, or an ACL forbids reading the catalog. On the surface, all of these errors can look like “no instances available”, yet the fixes are completely different.

Testing must verify both the success path and the denied path. At every layer, you must prove that valid connections are accepted and misconfigured or unauthorized connections are blocked at the proper boundary.

This article focuses on connections between providers, consumers, and registries in Spring Cloud Service Discovery, particularly with Eureka and Consul. Topics include DNS/TCP/routing checks, TLS and mutual TLS, registry authentication, catalog read/write permissions, HTTP 401/403 testing, NetworkPolicy, integration testing, and fail-closed error handling.

## 1. Layers to test

A service discovery request can traverse multiple layers:

~~~mermaid
flowchart LR
    APP["Spring Boot provider / consumer"]
    DNS["DNS"]
    NET["Routing / Firewall / NetworkPolicy"]
    TLS["TLS / mTLS"]
    AUTH["Authentication"]
    ACL["Authorization / ACL"]
    REG[("Eureka / Consul")]
    DATA["Service endpoint"]

    APP --> DNS --> NET --> TLS --> AUTH --> ACL --> REG
    APP --> DATA
~~~

Each layer answers a distinct question:

| Layer | Question | Failure symptoms |
|---|---|---|
| DNS | Does the hostname resolve properly? | NXDOMAIN, wrong IP, DNS timeout |
| Routing/TCP | Is there a network path and a listening port? | Connection refused, timeout, no route |
| TLS | Do both sides trust the certificate and hostname? | Unknown CA, SAN mismatch, expired certificate |
| mTLS | Does the client present a valid certificate when required? | Handshake failure, certificate required |
| Authentication | Can the client prove its identity? | HTTP 401 or corresponding auth error |
| Authorization | Does that identity have permission for the action? | HTTP 403, ACL permission denied |
| Discovery | Does the registry return the expected service and instances? | Empty list, instances filtered out |

Do not lump all failures into a single “service unreachable” assertion. Tests must pinpoint whether the failure occurred at DNS, TCP, TLS, authentication, or authorization. Only when the exact layer is identified can logs and test results point to the root cause.

## 2. Designing the test matrix

Before writing tests, build a table for each flow that needs protection:

- Provider registers an instance with the registry.
- Consumer reads the list of services and instances.
- Consumer calls the provider's endpoint.
- Registry server accepts requests from clients.
- Monitoring or operators read registry status.
- Health check agent calls the provider's endpoint.

One flow may require different permissions from another. For example, a provider needs write permission to register its own service; a consumer needs read permission for the services it depends on; only an operator holds ACL administration privileges.

| Test group | Valid case | Must-be-denied case |
|---|---|---|
| DNS | Registry hostname resolves accurately | Wrong or non-existent hostname |
| TCP | Pod is allowed to connect to the target port | Pod is outside the allow rule |
| TLS server | Valid CA, chain, SAN, and validity period | Untrusted CA, wrong SAN, expired certificate |
| mTLS client | Trusted client certificate | Missing certificate or invalid certificate |
| Eureka authentication | Client provides valid credentials | Missing or wrong Basic Auth |
| Consul ACL | Token has matching service permissions | Missing, invalid, or under-privileged read/write token |
| Service authorization | Consumer calls an authorized API | Consumer lacks required role/scope |
| Discovery | Consumer sees valid instances | Cannot read catalog or instances filtered by health |

Each test case should specify:

1. Caller: provider, consumer, registry server, or debug Pod.
2. Target: hostname, port, path, and protocol.
3. Identity: service account, username, ACL token, or client certificate.
4. Expected permission: read, register, deregister, or invoke API.
5. Expected outcome: success, timeout, TLS failure, 401, or 403.
6. Logs/metrics expected to appear to aid investigation.

Run tests from the exact environment where the application runs. Commands run from a laptop may succeed while a Pod is blocked by a NetworkPolicy, uses a different DNS search path, or runs a JVM truststore missing the internal CA.

## 3. Testing DNS, routing, and TCP

### 3.1. Verifying DNS

Before checking TLS or ACLs, verify that registry and service endpoint hostnames resolve properly from the workload's network namespace.

Example inside a Linux container:

~~~bash
getent hosts consul.service.internal
nslookup consul.service.internal
~~~

On Kubernetes, test from a Pod in the same namespace as the provider or consumer:

~~~bash
kubectl exec deploy/inventory-service -- nslookup consul-server.registry.svc.cluster.local
~~~

Cases to test:

- Valid hostname returns the expected IP address.
- Non-existent hostname returns NXDOMAIN.
- Internal DNS is not shadowed by search domains or stale DNS records.
- Pods can reach the DNS server over UDP and TCP port 53.
- DNS SRV-based service discovery returns the expected target and port if the architecture relies on SRV.

Successful DNS only proves the name resolves. It does not prove the port accepts connections or the endpoint certificate is valid.

### 3.2. Checking TCP and ports

Use TCP tools from the workload itself or a debug Pod sharing the same policies:

~~~bash
nc -vz consul.service.internal 8501
nc -vz eureka.service.internal 8761
~~~

You can use curl to test HTTP/HTTPS connectivity:

~~~bash
curl --connect-timeout 3 --max-time 8 -v https://consul.service.internal:8501/v1/status/leader
~~~

Common interpretations:

| Result | Possible meaning | Next check |
|---|---|---|
| Connection refused | Host is reachable, but no listener on port or connection rejected | Service port, targetPort, process |
| Connection timed out | Packets dropped, bad route, or policy blocked | NetworkPolicy, firewall, routes, CNI |
| No route to host | No matching route or network misconfiguration | Routing table, subnet, gateway |
| DNS lookup failed | Hostname fails to resolve | DNS zone, CoreDNS, search path |
| TCP connect succeeded | Socket opened successfully | Proceed to check TLS and HTTP |

A timeout alone does not prove NetworkPolicy is the culprit. Compare between an allowed Pod and a blocked Pod, inspect CNI/firewalls, and confirm whether packets reach the destination.

### 3.3. Testing Kubernetes NetworkPolicy

Kubernetes NetworkPolicy controls traffic at L3/L4. A Pod isolated for egress can only connect to targets permitted by allow rules; the target Pod also needs a matching ingress allow rule if isolated for ingress. Rules across multiple policies are additive—there is no declaration-order “deny overrides allow” rule. The cluster must run a CNI plugin that enforces NetworkPolicy.

Example policy restricting inventory-service traffic:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: inventory-network-access
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: inventory-service
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway
          podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: registry
          podSelector:
            matchLabels:
              app: consul
      ports:
        - protocol: TCP
          port: 8501
~~~

This is an illustrative policy. Namespace and DNS Pod labels vary by cluster; inspect actual labels with **kubectl get namespace --show-labels** and **kubectl get pods -n kube-system --show-labels**. If the application also needs a database, message broker, telemetry, or other endpoints, add corresponding allow rules. A default-deny egress policy also blocks DNS unless DNS is explicitly allowed.

The test suite must cover both allowed and blocked paths:

1. Pod api-gateway in the permitted namespace calls inventory-service:8080: connection succeeds.
2. Pod in an unpermitted namespace calls the same endpoint: connection is blocked.
3. inventory-service calls Consul port 8501: connection succeeds.
4. inventory-service calls a disallowed port: connection fails.
5. inventory-service resolves the Consul hostname: DNS still works via the UDP/TCP 53 rule.

NetworkPolicy does not replace TLS or ACLs. A connection permitted on port 8501 still must verify certificates and tokens. Conversely, a valid token cannot carry a request across a blocked network path.

## 4. Testing TLS certificates

TLS server authentication lets the client verify the server it connects to is the trusted endpoint. Do not merely check that the handshake finishes; verify the entire chain, hostname, and certificate validity window.

Conditions to verify:

- The server certificate is currently valid.
- Current time is after NotBefore and before NotAfter.
- The chain builds to a CA trusted by the truststore.
- Subject Alternative Name (SAN) matches the hostname the client uses.
- Extended Key Usage permits serverAuth.
- The server sends all required intermediate certificates.
- SNI is sent accurately when an endpoint serves multiple hostnames on one IP.
- Protocols and ciphers are mutually supported per security policy.

### 4.1. Inspecting certificates and SANs

Use OpenSSL to inspect a certificate:

~~~bash
openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Use keytool to inspect truststore contents:

~~~bash
keytool -list -v -keystore registry-truststore.p12 -storetype PKCS12
~~~

Verify the CA fingerprint through a trusted channel before importing a certificate into a truststore. Never import a certificate simply because it was downloaded from the very endpoint being verified.

### 4.2. Checking TLS server with OpenSSL

~~~bash
openssl s_client \
  -connect consul.service.internal:8501 \
  -servername consul.service.internal \
  -verify_hostname consul.service.internal \
  -CAfile registry-ca.pem \
  -verify_return_error \
  </dev/null
~~~

Meaning of flags:

- -connect: TCP address and port.
- -servername: hostname sent in TLS SNI.
- -verify_hostname: verifies hostname matches the certificate.
- -CAfile: CA trusted by the client.
- -verify_return_error: exits with failure if certificate verification fails.

A handshake is only considered valid when both chain and hostname verification succeed. The -showcerts flag prints certificates sent by the server, but displaying them does not prove the chain was verified.

### 4.3. Intentionally testing certificate errors

Generate dedicated test certificates in the test environment; never modify production certificates. Negative tests should include:

| Test | How to trigger failure | Expected outcome |
|---|---|---|
| Unknown CA | Use a CA absent from truststore | TLS verification fails |
| SAN mismatch | Call a hostname missing from SAN | Hostname verification fails |
| Expired certificate | Use an expired cert | Client rejects handshake |
| Not-yet-valid | Use a cert with NotBefore in the future | Client rejects handshake |
| Missing intermediate | Server omits required intermediate cert | Chain validation fails if client lacks intermediate |
| Wrong SNI | Send an SNI different from target virtual host | Receives wrong cert or handshake/verification fails |
| Weak protocol | Enable only protocols disallowed by client | Handshake fails |

Never use curl -k, --insecure, a trust-all manager, or disabled hostname verification to make tests pass. Those options bypass the exact controls tests exist to verify.

## 5. Testing mutual TLS

Mutual TLS (mTLS) requires both client and server to present certificates to verify identity at the TLS layer:

- Client verifies the server certificate using its truststore.
- Server verifies the client certificate using the server's CA truststore.
- Server can require a certificate (need) or request one if sent (want), depending on configuration.

When a registry or service endpoint requires client certificates, minimal tests must cover:

1. Client presents a valid certificate signed by a server-trusted CA: handshake succeeds.
2. Client sends no certificate: server rejects when client certs are mandatory.
3. Client sends a certificate signed by an untrusted CA: server rejects.
4. Client sends an expired certificate or one lacking clientAuth usage: server rejects.
5. Client certificate is valid, but ACL/application authorization is insufficient: TLS may succeed while the request is still rejected at authorization.

With Spring Boot's embedded web server, mandatory mTLS can use `server.ssl.client-auth: need` along with the server keystore and a truststore containing the CA that issues client certificates:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    client-auth: need
    key-store: file:/run/secrets/service-server.p12
    key-store-type: PKCS12
    key-store-password: "<secret injected by deployment>"
    trust-store: file:/run/secrets/client-ca-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: "<secret injected by deployment>"
~~~

Only use `need` when every client on that listener must present a certificate. If you only want client certificates on certain routes, design dedicated listeners or gateways accordingly; mTLS at the TLS handshake does not authorize per HTTP path.

Testing with OpenSSL:

~~~bash
openssl s_client \
  -connect registry.service.internal:8501 \
  -servername registry.service.internal \
  -verify_hostname registry.service.internal \
  -CAfile registry-ca.pem \
  -cert discovery-client.crt \
  -key discovery-client.key \
  -verify_return_error \
  </dev/null
~~~

Tests without -cert and -key must fail when the server mandates mTLS. Tests with an untrusted client certificate must also fail.

mTLS authenticates the peer's certificate at the connection layer. It does not automatically grant permission to read payment-service or register inventory-service; business permissions still require ACLs or authorization.

## 6. Testing HTTPS with Spring Boot

Spring Boot provides SSL Bundles to group keystores, truststores, and TLS settings into named configurations. Example JKS/PKCS12 bundle configuration for a client:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        registry-client:
          keystore:
            location: file:/run/secrets/discovery-client.p12
            password: "<secret injected by deployment>"
            type: PKCS12
          truststore:
            location: file:/run/secrets/registry-truststore.p12
            password: "<secret injected by deployment>"
            type: PKCS12
~~~

Bundles can be retrieved via the SslBundles bean to build an SSLContext for custom HTTP clients. Do not assume every client library automatically consumes this bundle; verify that the actual HTTP adapter uses the intended truststore and keystore.

### 6.1. Eureka client TLS

Spring Cloud Netflix has dedicated TLS configuration for Eureka clients:

~~~yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: file:/run/secrets/eureka-client.p12
      key-store-type: PKCS12
      key-store-password: "<secret injected by deployment>"
      key-password: "<secret injected by deployment>"
      trust-store: file:/run/secrets/eureka-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: "<secret injected by deployment>"
~~~

eureka.client.tls.enabled must be true for the Eureka client to use the configured TLS material. If no truststore is configured, the client may fall back to the JVM default truststore. In tests, intentionally use a truststore containing only the test CA to prove the client actually validates against the internal CA.

### 6.2. Consul client HTTPS and service scheme

Spring Cloud Consul separates the scheme used to call the Consul Agent from the scheme advertised for the service instance:

- spring.cloud.consul.scheme: HTTP/HTTPS for connections to the Consul Agent.
- spring.cloud.consul.discovery.scheme: scheme of the service registered in the catalog.

Example:

~~~yaml
spring:
  cloud:
    consul:
      scheme: https
      host: consul.service.internal
      port: 8501
      discovery:
        scheme: https
        acl-token: "<discovery token injected by secret manager>"
~~~

Trust material and client certificate settings must match Consul's TLS listener and your Spring Cloud Consul version. Never enable health-check-tls-skip-verify in production to hide certificate errors; only use verification-skip options in deliberate test fixtures and assert they are disabled in deployment configs.

### 6.3. Testing with curl

HTTPS with an internal CA:

~~~bash
curl --cacert registry-ca.pem \
  --connect-timeout 3 \
  https://consul.service.internal:8501/v1/status/leader
~~~

mTLS with a client certificate:

~~~bash
curl --cacert registry-ca.pem \
  --cert discovery-client.crt \
  --key discovery-client.key \
  https://consul.service.internal:8501/v1/status/leader
~~~

To test invalid certificates, use an invalid CA/certificate fixture and verify curl aborts with a TLS error. Never use --insecure in positive tests.

## 7. Testing Eureka authentication and protection

Eureka server can be secured with Spring Security. Clients can use HTTP Basic Authentication; Spring Cloud Netflix automatically attaches Basic Auth when `eureka.client.serviceUrl.defaultZone` embeds URL credentials. For more complex needs, you can customize DiscoveryClientOptionalArgs and ClientFilter.

Illustrative URL example:

~~~yaml
eureka:
  client:
    serviceUrl:
      defaultZone: https://<username>:<password>@eureka.service.internal/eureka/
~~~

Credentials must be injected from a secret store—never committed to source control or logged as full URLs. Eureka documentation also notes limitations regarding multiple Basic Auth credential sets across server URLs; test carefully if configuring multiple Eureka servers with distinct credentials.

### 7.1. Protecting Eureka endpoints with Spring Security

Example filter chain configuration:

~~~java
@Bean
SecurityFilterChain eurekaSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/eureka/**").hasRole("REGISTRY_CLIENT")
            .requestMatchers("/admin/**").hasRole("REGISTRY_ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .csrf(csrf -> csrf.ignoringRequestMatchers("/eureka/**"));

    return http.build();
}
~~~

Eureka clients do not normally send CSRF tokens. Therefore, the example ignores CSRF on `/eureka/**` so clients can register and send heartbeats. Only ignore CSRF on necessary registry paths; do not disable CSRF application-wide out of habit.

In real systems, separate privileges for registry clients, dashboard operators, and administrative endpoints. Do not grant admin roles to every service just so clients can register.

### 7.2. Testing authentication and authorization

For Eureka endpoints requiring Basic Auth, test:

| Request | Expected outcome |
|---|---|
| No credentials sent | 401 Unauthorized |
| Wrong username/password | 401 Unauthorized |
| Valid credentials and matching role | Success |
| Authenticated but missing required role | 403 Forbidden |
| Client sends POST registration with configured CSRF policy | Not rejected for missing CSRF token under /eureka/** |
| POST to admin endpoint without privilege | 403 Forbidden |

401 usually indicates an unauthenticated request; 403 indicates an authenticated identity lacking permission. However, exact status codes depend on authentication entry points, reverse proxies, and framework settings. Test the contract of your running system while ensuring response bodies and logs never leak credentials.

## 8. Testing Consul ACLs

Consul uses ACL tokens to authenticate requests and policies to grant permissions. The HTTP API accepts tokens via the X-Consul-Token header or Bearer authorization header. When ACLs are enabled, requests without a token may fall back to a default or anonymous token depending on configuration; therefore, missing-header tests must verify actual anonymous/default policy behavior.

Spring Cloud Consul has a dedicated property:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        acl-token: "<service discovery token from secret manager>"
~~~

Do not confuse spring.cloud.consul.discovery.acl-token with spring.cloud.consul.config.acl-token. A token scoped for reading KV config is not automatically valid for service registration/discovery.

### 8.1. Least-privilege permissions for providers and consumers

Providers typically need write permission to register their own service. Consumers need read permission for services they look up. Example Consul HCL policy:

~~~hcl
service "inventory-service" {
  policy = "write"
}

service "order-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
~~~

If a consumer must discover multiple services, grant read access strictly to the approved list or prefix. Avoid handing global-management tokens to applications. node:read may be required for certain Catalog/Health operations or service mesh features; determine permissions from the APIs and architecture in use.

### 8.2. Checking Consul requests

Example querying the Catalog with a token:

~~~bash
curl \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  https://consul.service.internal:8501/v1/catalog/services \
  --cacert registry-ca.pem
~~~

Checking the Health API for a service:

~~~bash
curl \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  "https://consul.service.internal:8501/v1/health/service/inventory-service" \
  --cacert registry-ca.pem
~~~

Bearer tokens can be used if the API client is configured accordingly:

~~~http
Authorization: Bearer <consul-token>
~~~

Never put tokens in query strings because URLs often end up in access logs, proxy logs, or telemetry. Never enable debug logging that dumps full HTTP headers when running tests with real tokens.

### 8.3. Mandatory ACL tests

| Token | Action | Expected outcome |
|---|---|---|
| No token | Read catalog | Succeeds only if anonymous/default policy permits |
| Invalid token | Read catalog | Denied |
| Service read-only token | Read permitted service | Succeeds |
| Service read-only token | Register or update service | Denied |
| Token with write for inventory-service | Register inventory-service | Succeeds |
| Token with write for inventory-service | Register payment-service | Denied |
| Consumer token with read for order-service only | Query inventory-service | Denied or returns no entries per policy/version |
| Service token | Create ACL policy/token | Denied due to missing acl:write |

In Consul, some endpoints filter results based on permissions rather than returning everything. Thus, tests must inspect HTTP status, response body, and ensure disallowed entries do not appear. Do not assert status codes alone.

## 9. Distinguishing 401, 403, and TLS errors

Not every rejected request returns the same error type. The TLS handshake happens before HTTP; if TLS fails, the server never receives an HTTP request, so no HTTP 401/403 is produced.

| Error | Layer | How to recognize |
|---|---|---|
| TLS handshake failure | TLS | OpenSSL/JVM reports certificate or handshake error; no HTTP response |
| 401 Unauthorized | Authentication | Missing or invalid credentials per authentication entry point |
| 403 Forbidden | Authorization/CSRF | Authenticated but lacking permission, or missing CSRF token |
| 404 Not Found | HTTP routing/filtering | Wrong path or API intentionally hides unauthorized resource |
| 429 Too Many Requests | Rate limit | Request exceeds quota/rate limit |
| 5xx | Server/proxy | Processing error on server, upstream, or gateway |
| TCP timeout | Network | Connection did not complete before timeout |

A Consul ACL denial may vary in response code/body by endpoint and version. Inspect permission-denied messages and policy evaluation rather than assuming every ACL failure is always 403.

## 10. Testing authorization in Spring Security applications

Registry ACLs govern who can read/write the catalog. They do not replace authorization for business APIs. A consumer discovering payment-service does not imply that consumer is authorized to call every endpoint on that service.

Use spring-security-test to verify web-layer rules:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ServiceAccessTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadInternalEndpoint() throws Exception {
        mvc.perform(get("/internal/instances"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "READER")
    void readerCannotRegisterService() throws Exception {
        mvc.perform(post("/internal/registry/register").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "REGISTRY_ADMIN")
    void registryAdminCanRegisterService() throws Exception {
        mvc.perform(post("/internal/registry/register").with(csrf()))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Paths and roles in this example are application-defined. If a POST endpoint is not on the CSRF ignore list, tests must supply a valid CSRF token; tests omitting or sending an invalid token must be rejected.

MockMvc tests Spring MVC and the security filter chain. It does not test DNS, NetworkPolicy, real TLS handshakes, or Consul ACLs. Test those at their respective layers.

## 11. Integration testing with a real registry

Unit tests can mock DiscoveryClient, but mocks do not prove the client can connect, validate certificates, present tokens, or handle denied permissions properly.

An integration suite should run against a pinned-version registry in an isolated environment:

- Eureka Server with Spring Security and TLS configured like production.
- Consul Agent/server with ACLs and HTTPS enabled.
- Spring Boot provider registering an instance.
- Spring Boot consumer invoking DiscoveryClient and LoadBalancer.
- Short-lived test fixtures for CAs, client certificates, truststores, and ACL tokens.

Minimum scenario:

1. Start the registry and verify health.
2. Provider registers a service using a valid certificate/token.
3. Consumer with read permission sees the service.
4. Consumer calls the instance and gets a successful response.
5. Provider tries to register using a read-only token: must be rejected.
6. Consumer tries discovery using a token lacking read permission: must be rejected or see no entries per ACL contract.
7. Client uses wrong CA or wrong hostname: TLS must fail before HTTP.
8. Client omits certificate when mTLS is required: handshake must fail.
9. Block TCP via network policy: client cannot connect even with valid token and certificate.
10. Restore valid policy/credentials: service registration and discovery resume working.

Use Testcontainers or an equivalent ephemeral environment to build reproducible registry and network dependencies. Pin image versions to your target release; never use latest in CI because version drift makes test results unstable.

## 12. Testing fail-closed behavior and preventing security downgrade

When the registry is unreachable or a token is rejected, the application must exhibit well-defined behavior:

- Providers must never pretend registration succeeded when the registry denies writes.
- Consumers must never fall back to unencrypted HTTP just because HTTPS failed.
- Clients must never bypass certificate validation to force a connection through.
- Under-privileged tokens must never be swapped for admin tokens or broad anonymous access.
- Uncontrolled static endpoints must never be used as a fallback to bypass discovery policies.
- If the consumer uses a cached snapshot during a registry outage, there must be an explicit policy for stale-data TTL and handling revoked endpoints.

Not every system needs to halt the entire application during a registry outage. Deciding between failing fast and serving from cache depends on the service role and SLO. What is mandatory is never masking authentication/authorization failures by silently falling back to a less secure path.

Scenarios to verify:

| Scenario | Behavior to verify |
|---|---|
| Registry timeout at startup | Startup fails or degrades per defined policy; emits logs/metrics |
| Registration gets 403 | Instance is not marked as successfully registered |
| Discovery query gets ACL deny | Does not return a fake list or unauthorized fallback |
| Expired certificate | Client rejects TLS and alerts |
| Truststore missing new CA | Connection fails clearly, never trust-all |
| Registry outage after caching | Cache used only within stale-data policy bounds |
| Revoked credential | Subsequent requests fail and system does not keep using old credential indefinitely |

## 13. Testing certificate and token rotation

Both certificates and ACL tokens have lifecycles. Tests running only at startup will miss failures when credentials rotate.

### 13.1. Certificate rotation

Test the new CA/certificate rollout flow:

1. Client trusts both old and new CAs during the transition window.
2. Server switches its certificate to the new CA.
3. Client verifies handshake succeeds with the new certificate.
4. Verify logs contain no trust or hostname errors.
5. After all clients migrate, remove the old CA from the truststore.
6. Verify the old certificate is no longer accepted.

If Spring Boot SSL Bundles enable reload-on-update, test that file watchers and bundle-consuming components actually support reload. Do not assume every Eureka/Consul HTTP client automatically reloads its truststore when a file changes; test your exact client implementation.

### 13.2. ACL token rotation

1. Create a new token with the exact least-privilege policy.
2. Deploy the new token to providers/consumers.
3. Verify register, discovery, and health queries succeed.
4. Revoke the old token.
5. Verify the old token is rejected.
6. Verify logs, environment variables, and secret volumes do not retain the old token past the allowed window.

Never write secret IDs into test reports. Record only the token alias, policy name, rotation timestamp, and outcome.

## 14. Observability and diagnostics

Security tests must leave enough telemetry to diagnose failures without leaking secrets.

Useful signals:

- DNS resolution failures.
- TCP connect timeouts/refusals.
- TLS handshake failures categorized by cause.
- Certificate expiry and remaining days.
- Eureka registration/authentication failures.
- Consul ACL permission denied events.
- HTTP 401/403 counts by endpoint and client identity.
- Discovery result count and filtered instance count.
- Token/certificate rotation timestamps.

Never log:

- Passwords, Basic Auth headers, or URLs containing credentials.
- X-Consul-Token or Bearer tokens.
- Private keys, keystore passwords, or secret contents.
- Full request headers when debugging HTTP clients.

When logging an error, record the service name, registry endpoint alias, operation, error category, correlation ID, and status code. Hostnames/IPs may appear in internal logs per policy, but never place them in unbounded-cardinality metric labels.

## 15. Sample test matrix for CI/CD

You can use the following matrix as acceptance criteria:

| ID | Condition | Expected outcome |
|---|---|---|
| NET-01 | Valid registry DNS | Resolves to expected hostname |
| NET-02 | Invalid DNS hostname | NXDOMAIN/resolve failure detected |
| NET-03 | Pod allowed to reach registry | TCP connect succeeds |
| NET-04 | Pod egress denied | TCP connection cannot open |
| TLS-01 | Valid server cert, matching SAN | TLS handshake succeeds |
| TLS-02 | Untrusted CA | TLS handshake fails |
| TLS-03 | SAN mismatch | Hostname verification fails |
| TLS-04 | Expired server cert | TLS verification fails |
| MTLS-01 | Valid client cert | Handshake succeeds |
| MTLS-02 | Missing client cert | Server rejects when mTLS is required |
| MTLS-03 | Client cert from wrong CA | Server rejects |
| EUREKA-01 | Valid Basic Auth | Client reads/writes registry per role |
| EUREKA-02 | Invalid Basic Auth | Request rejected |
| CONSUL-01 | Token with service write | Provider registers authorized service |
| CONSUL-02 | Read-only token | Register rejected |
| CONSUL-03 | Token missing service read | Consumer cannot read out-of-scope service |
| AUTH-01 | Anonymous request to internal endpoint | 401 per security contract |
| AUTH-02 | Authenticated user lacking role | 403 per security contract |
| AUTH-03 | Missing/invalid CSRF token on CSRF-protected endpoint | 403 |
| ROT-01 | New token deployed | Valid requests succeed |
| ROT-02 | Old token revoked | Requests with old token are rejected |

A test only passes when both allowed and denied behaviors are verified. For example, a read-only token test should not merely observe that registration failed; it must also verify the service can still read the permitted catalog so the test does not “pass” simply because the registry is completely unreachable.

## 16. Investigation workflow when tests fail

When a consumer cannot find a service or registration fails:

1. Check hostname and DNS resolution from the Pod running the application.
2. Check TCP connectivity to the target host/port.
3. If using HTTPS, verify chain, SAN, expiry, and SNI with OpenSSL.
4. If using mTLS, verify the client certificate and the server's CA truststore.
5. Check HTTP status and response body once TLS succeeds.
6. Check Basic Auth credentials or the Consul ACL token.
7. Compare the policy against the exact read/register/deregister action.
8. Check NetworkPolicy ingress/egress rules and CNI enforcement.
9. Inspect application logs, registry logs, and metrics sharing the same timestamp.
10. Re-run positive tests after fixes to ensure permitted paths still work.

Do not change firewall rules, truststores, tokens, and policies all at once in one attempt. Change one layer at a time to preserve cause-and-effect clarity.

## 17. Takeaways

- DNS, TCP, TLS, authentication, and authorization are independent layers; tests must pinpoint failures at the right layer.
- NetworkPolicy controls only L3/L4 traffic; both source egress and destination ingress may need allow rules.
- TLS must verify chain, SAN, validity dates, SNI, and certificate usage.
- mTLS authenticates the client certificate but does not automatically grant registry read/write permissions.
- Eureka can use Basic Auth and dedicated TLS settings via eureka.client.tls.*.
- Consul uses ACL tokens; Spring Cloud Consul provides spring.cloud.consul.discovery.acl-token.
- Consul separates spring.cloud.consul.scheme for Agent connections from spring.cloud.consul.discovery.scheme for service registration.
- 401 generally relates to authentication; 403 generally relates to authorization or CSRF; TLS handshake failures occur before HTTP.
- MockMvc does not replace network, TLS, or real registry tests.
- Never use curl -k, trust-all, admin tokens, or HTTP fallbacks to make tests pass.
- Test certificate and token rotation, not only startup behavior.
- Log enough diagnostic context, but never log credentials or private keys.

Testing network paths, certificates, and denied access proves that services are registered, discovered, and called only over authorized connections. When positive and negative tests run inside the real deployment environment, teams catch DNS, policy, TLS, credential, and ACL mistakes early before they turn into production discovery outages.

## References

- [Spring Cloud Netflix — Authenticating with Eureka Server and Client TLS](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Security — CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Consul — HTTP API Authentication](https://developer.hashicorp.com/consul/api-docs/api-structure)
- [Consul — ACL Rules](https://developer.hashicorp.com/consul/docs/secure/acl/rule)
- [Consul — Service Tokens](https://developer.hashicorp.com/consul/docs/secure/acl/token/service)
- [OpenSSL — s_client](https://docs.openssl.org/master/man1/openssl-s_client/)
- [Oracle JDK — keytool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html)
