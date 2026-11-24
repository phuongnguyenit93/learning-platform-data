# Never Trust Client-Supplied User or Role Headers

## 1. The Problem: A Client Can Send Any HTTP Header

In a **Spring Security reactive** system with an **API Gateway and multiple tenants**, requests typically traverse these components:

~~~text
Browser / Mobile / Partner
           │
           │ HTTPS
           │ Authorization: Bearer <access-token>
           │ X-User-Id: admin
           │ X-User-Roles: ROLE_ADMIN
           │ X-Tenant-Id: tenant-victim
           ▼
┌───────────────────────────────────────┐
│ Edge / Spring Cloud Gateway           │
│ - TLS / routing / logging             │
│ - Strip client-sent identity headers  │
│ - Never treat X-User-* as identity    │
└──────────────────┬────────────────────┘
                   │ Private network
                   │ Authorization: Bearer <access-token>
                   ▼
┌────────────────────────────────────────────┐
│ Spring Boot WebFlux Resource Server        │
│ - ReactiveJwtDecoder.verify(...)           │
│ - Verify iss, aud, exp, nbf, signature     │
│ - JwtAuthenticationToken in Context        │
│ - Scope/role from trusted identity policy  │
│ - Verify URL tenant and data permissions   │
└────────────────────────────────────────────┘
~~~

**Problem statement:** any client can send arbitrary `X-User-Id`, `X-User-Roles`, or `X-Tenant-Id` headers. If the gateway or a downstream service treats those values as already authenticated, an attacker can impersonate another user, spoof an administrator, or access another tenant's data.

An HTTP header is just data supplied by the sender; **a header name does not confer trustworthiness**. The exact same string `X-Authenticated-User: alice` could have been:
- Written directly by an external client.
- Added by a reverse proxy after authenticating the user.
- Overwritten by a gateway on an authenticated route.
- Retained from an old request by an intermediate proxy.
- Sent directly to the backend by an untrusted internal system.

A backend can only trust an identity header if **the network, gateway, protocol, and policy have proved the origin, integrity, and permission scope** of that information. In a more conservative design, the backend **independently verifies the JWT Bearer token** and never treats raw identity headers as authentication proof.

### Learning Objectives

After this lesson, you will be able to:
1. Articulate the threat model of `X-User-Id`, `X-User-Roles`, `X-Tenant-Id`, `X-Forwarded-User`, and similar headers.
2. Distinguish **client-declared headers**, **network metadata from proxies**, and **claims inside a verified access token**.
3. Establish a trust boundary at the gateway/ingress: strip untrusted identity headers, verify JWTs, and control access paths to the backend.
4. Use Spring Cloud Gateway WebFlux `RemoveRequestHeader` properly.
5. Understand why **merely stripping headers at the gateway is still insufficient** if the backend is directly reachable or another service trusts those headers.
6. Configure a Spring Security WebFlux Resource Server with `issuer-uri`, `jwk-set-uri`, `audiences`, and `SecurityWebFilterChain`.
7. Incorporate the tenant from a verified JWT claim into authorization decisions without letting `X-Tenant-Id` or query/path parameters override permissions.
8. Build a Java 17+ application and `WebTestClient` tests with real RSA-signed JWTs demonstrating 401, 403, and 200.
9. Identify risks around multi-issuer setups, confused deputy, insecure internal headers, header spoofing, and lateral movement.
10. Design safer alternatives when identity genuinely must cross the gateway: audience-bound signed internal assertions/mTLS or token relay verified at the service.

## 2. Commonly Abused Header Names

| Header | Can a Client Send It? | Risk if Blindly Trusted as Identity |
| --- | --- | --- |
| `X-User-Id` | Yes | Impersonate another user to read data by ID |
| `X-Authenticated-User` | Yes | Bypass login if the app treats it as an authenticated principal |
| `X-Auth-Request-User` | Yes | Bypass an auth proxy mechanism if ingress does not strip/overwrite it |
| `X-Principal` | Yes | Inject an arbitrary principal |
| `X-Roles` | Yes | Spoof ADMIN/MANAGER/OWNER |
| `X-User-Roles` | Yes | Role spoofing/privilege escalation |
| `X-Tenant-Id` | Yes | Cross-tenant data access if code trusts the header |
| `X-Organization-Id` | Yes | Select a different org than the authenticated identity |
| `X-Forwarded-User` | Yes | Abuse a header that "looks proxy-generated" |
| `X-Forwarded-For` | Yes if proxy does not sanitize | Spoof IP; not user identity |
| `Forwarded` | Yes if proxy does not sanitize | Spoof scheme/host/for metadata, leading to URL/IP spoofing |
| `Authorization` | Yes | Carries a credential; **trust only after cryptographic/protocol verification** |

There is no single fixed header list for every product. You must audit all **identity-related names used by your organization's gateway, ingress, auth proxy, service mesh, frameworks, and legacy apps**.

Some infrastructures use other headers such as `X-Remote-User`, `X-Email`, `X-Group`, or `X-Auth-Request-Groups`. **Renaming a header does not increase its trustworthiness**.

### 2.1. Direct attack example

~~~http
GET /api/tenants/tenant-b/reports HTTP/1.1
Host: api.example.com
X-User-Id: ceo
X-User-Roles: ROLE_ADMIN
X-Tenant-Id: tenant-b
X-Authenticated-User: ceo
~~~

If the server executes:

~~~java
// ANTI-PATTERN: never grant permissions from a client header.
String userId = request.getHeaders().getFirst("X-User-Id");
String roles = request.getHeaders().getFirst("X-User-Roles");
String tenant = request.getHeaders().getFirst("X-Tenant-Id");

if ("ROLE_ADMIN".equals(roles)) {
    // GRANTS ADMIN PRIVILEGE -- VERY DANGEROUS!
}
~~~

then anyone who knows the endpoint can assign themselves any role. Spring Security cannot automatically protect this custom code if you deliberately bypass Authentication and trust a header.

**Correct approach:** identity and authorities must come from an `Authentication` that passed through a `ReactiveAuthenticationManager`/JWT validation or a verified internal security mechanism. Headers may carry a **tenant selection hint**, but the server must cross-check it against actual permissions.

### 2.2. Header spoofing can still happen alongside a Bearer token

~~~http
GET /api/tenants/tenant-b/reports HTTP/1.1
Authorization: Bearer <TOKEN_FOR_ALICE_TENANT_A>
X-User-Id: bob
X-User-Roles: ROLE_ADMIN
X-Tenant-Id: tenant-b
~~~

A valid JWT for Alice/tenant A **does not** allow headers to escalate the caller to Bob/admin/tenant B. Distinguish:
- Verified token: subject and scopes confirmed by the AS within the issuer/audience scope.
- `X-User-Id` header: has no trusted provenance.
- Tenant in URL `tenant-b`: the **target/object requested by the client**, not an entitlement.
- Tenant in token: may be context issued by a trusted AS, though sensitive data may still require local DB membership/owner verification.

## 3. Trust Boundary: Where Trust Starts and Ends

### 3.1. Unsafe: public backend or callable bypassing the gateway

~~~text
Internet client
     │
     ├─► Gateway strips X-User-Id
     │       └─► Backend
     │
     └────────────► Backend direct HTTP :8090
                     X-User-Id: admin
~~~

If the backend listens to the Internet on port 8090 and trusts headers as identity, an attacker will bypass the gateway and send requests directly. **Stripping headers at the gateway does not fix a backend that has a bypass path**.

Production requirements:
- The backend must only be reachable from the trusted gateway/sidecar/ingress via firewalls, security groups, or Kubernetes NetworkPolicies.
- Never accidentally expose a backend NodePort/LoadBalancer/public IP.
- Account for lateral movement paths between internal pods/services.
- At high-security boundaries, use service-to-service TLS/mTLS and verify service identity.
- More importantly, downstream still verifies the access token or a narrow-audience signed internal assertion independently; **network isolation is defense in depth, not end-user identity verification**.

### 3.2. Secure by design: both stripping spoofed headers and verifying Bearer

~~~text
Untrusted client
   │ X-User-Id=admin (forged)
   │ Authorization=Bearer(valid token Alice)
   ▼
Gateway:
  ├─ RemoveRequestHeader X-User-Id
  ├─ RemoveRequestHeader X-User-Roles
  ├─ RemoveRequestHeader X-Tenant-Id
  └─ Route to private downstream
          │ Bearer(valid token Alice)
          ▼
Resource Server:
  ├─ Verify JWT (signature/iss/aud/exp)
  ├─ JWT principal = Alice
  ├─ JWT scopes → SCOPE_...
  ├─ JWT tenant_id = tenant-a
  ├─ Request tenant-b ≠ tenant-a
  └─ 403, independent of spoofed headers
~~~

These are **two independent layers**:
1. Gateway hygiene: never forward client-crafted identity data under internal header names.
2. Resource Server trust: never use those headers as credentials; trust the JWT only after validation and check tenant/resource ownership.

Even if a route configuration accidentally omits stripping a header, the Resource Server still refuses to grant privileges from that header. That is valuable defense in depth.

### 3.3. Difference between network metadata and identity

`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and RFC 7239 `Forwarded` describe metadata about proxies, IPs, schemes, and hosts. They are **not** user roles or identity. Spring WebFlux provides `ForwardedHeaderTransformer` to interpret data from a **trusted proxy**, but it cannot automatically tell which headers were forged by an attacker.

Therefore:
- The edge must strip/overwrite untrusted forwarded metadata at the Internet boundary.
- `X-Forwarded-For: 127.0.0.1` does not prove the request truly originated from localhost.
- Never use self-declared `X-Forwarded-Host`/`Host` to select a privileged tenant or construct token-bearing password-reset URLs.
- Separate IP used for rate limiting/auditing from identity used for authorization.
- Every path between proxies and backends must have a clear trusted-hops policy, never blindly picking the first element of `X-Forwarded-For`.

## 4. Spring Cloud Gateway: What RemoveRequestHeader Does and Does Not Do

Spring Cloud Gateway **WebFlux** supports the filter factory:

~~~yaml
filters:
  - RemoveRequestHeader=X-User-Id
~~~

Meaning: removes the `X-User-Id` header from requests **forwarded to the upstream service** for that route. This is a hygiene control, not a user verification step.

A practical policy should strip identity/role/tenant headers that a client could send:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: reports
          uri: http://127.0.0.1:8090
          predicates:
            - Path=/api/**
          filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-User-Roles
            - RemoveRequestHeader=X-Roles
            - RemoveRequestHeader=X-Tenant-Id
            - RemoveRequestHeader=X-Authenticated-User
            - RemoveRequestHeader=X-Auth-Request-User
            - RemoveRequestHeader=X-Principal
            - RemoveRequestHeader=X-Forwarded-User
~~~

This snippet targets **Spring Cloud Gateway Server WebFlux 4.1** (Spring Cloud 2023.0.x release train), which uses the `spring.cloud.gateway.routes` key. Do not mistakenly copy configuration keys from Spring Cloud Gateway MVC or Gateway 5.x, as property paths differ across products and versions.

**Important limitations of RemoveRequestHeader:**
- It strips headers **on requests routed through that gateway**, and cannot stop clients from calling the backend directly if the network allows it.
- It does not make `Authorization` trustworthy; Bearer tokens still require a decoder/validator.
- It does not verify tenant membership, roles, or ownership.
- It does not protect routes without the filter applied; use a shared policy/GlobalFilter when an organization has many routes.
- It does not stop another downstream service from trusting headers under new names.
- It does not replace TLS/mTLS/network isolation.
- It does not guarantee that proxies in front of the gateway sanitized `Forwarded`/`X-Forwarded-*`.

### 4.1. Why not simply set the header to "anonymous"?

If the gateway simply configures:

~~~yaml
filters:
  - SetRequestHeader=X-User-Id,anonymous
~~~

then the backend might treat `anonymous` as a trusted identity, or other code continues relying on a header unbound to a JWT. Better:
- **Do not pass** client-supplied internal identity headers.
- Let the Resource Server verify the JWT and construct the principal inside Spring Security Context.
- If an internal identity header is genuinely required for a legacy service, use an assertion protocol with integrity and explicit origin binding rather than merely substituting a string.

### 4.2. Case-insensitive header names and multiple values

In HTTP, header field names are case-insensitive. A client may try:

~~~http
x-user-id: admin
X-USER-ID: administrator
X-User-Roles: ROLE_ADMIN
x-user-roles: ROLE_OWNER
~~~

Do not check `headers.keySet().contains("X-User-Id")` using purely case-sensitive comparison and assume no spoofed header exists. Server frameworks and gateways typically use case-insensitive abstractions, but if you write low-level code yourself, you must follow standard semantics.

A header can also appear multiple times or carry a list of values. Never use `getFirst()` to "trust the first value" across an unsanitized trust boundary. For internal identity assertions, enforce a strict contract: exactly one value, canonical format, trusted origin; reject ambiguous duplicates instead of guessing.

### 4.3. Do not confuse StripPrefix/RewritePath with tenant permission

A gateway route may strip `/gateway` or rewrite the path before forwarding to a service. That does not grant the request permission for the tenant in the new URL. A request to `/api/tenants/tenant-b/reports` remains a tenant B request even if the gateway altered the prefix. The service must verify tenant and permissions.

If gateway authorization checks the URL **before rewriting** while the service checks the URL **after rewriting**, ensure both agree on semantics (HTTP method, path normalization, encoded slashes/dot segments). Never rely solely on gateway path matchers to enforce all object-level rules.

## 5. Three Strategies for Propagating Identity from Gateway to Service

### 5.1. Strategy A — Gateway forwards the Bearer access token, service verifies independently

~~~text
Client --Bearer access token--> Gateway
                                  │
                                  └--Bearer access token--> Resource Server
                                                                 │
                                                                 ├─ verify JWT
                                                                 ├─ map authorities
                                                                 └─ check tenant/object
~~~

This is the primary strategy in this lesson:
- The Gateway strips client-sent identity headers.
- No trusted `X-User-Id` is minted.
- The downstream service uses `spring-boot-starter-oauth2-resource-server` and `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)`.
- The access token must carry an `aud` matching the service, rather than borrowing a token issued for the frontend or a different API.
- The JWT is validated against the public key/JWKS specified by a trusted AS, not an arbitrary `jku` or `iss`.
- The service still checks tenant/ownership and may verify internal user status/membership.

**Pros:** clear trust boundary, easy to test; the service does not trust identity headers. **Tradeoff:** multiple services must verify tokens/cache JWKS; mitigated with centralized config and reviewed shared libraries.

### 5.2. Strategy B — Gateway authenticates and mints a signed internal assertion

When a legacy backend should not receive Internet access tokens or when token exchange is needed:

~~~text
External Bearer
   ▼
Gateway verifies signature/issuer/audience and policy
   ▼
Gateway mints INTERNAL assertion
  iss  = trusted-gateway
  aud  = target-service
  sub  = verified external subject / local user ID
  tid  = authorized tenant
  exp  = now + short TTL
  jti  = unique ID (if replay protection is needed)
  act  = provenance/actor metadata per protocol
   ▼
Private TLS/mTLS connection
   ▼
Service verifies internal assertion against trusted gateway key,
issuer, audience, expiry, and required permissions
~~~

This is **not** simply adding `X-User-Id: alice`. The assertion must have:
- A signature from a key trusted by the service, with key rotation and an allowlisted algorithm.
- A specific issuer and a narrow audience per downstream service.
- A short TTL and scopes/permissions that never exceed the original token.
- Tenant/actor/context bound by policy, uncontrollable by the client.
- A protected transport channel (TLS/mTLS, ingress-only routes).
- Replay/forwarding prevention to other services (audience-bound; optionally confirmation/`cnf` per threat model).

If a header must still carry the transport, e.g. `X-Internal-Assertion: <signed JWT>`, that header is only **the carrier of signed proof** and is not inherently trusted. The service **must verify the assertion** and ingress must strip any client-sent header of the same name.

### 5.3. Strategy C — Network-enforced pre-auth headers for legacy services

Sometimes a legacy app only accepts `X-Authenticated-User` from an auth proxy. This model **requires**:
- The service is unreachable directly from clients or untrusted lateral services.
- The trusted proxy always strips client-sent headers and **sets** identity itself after auth.
- mTLS/service identity or a connection-origin enforcement layer.
- Duplicate-header/serialization policies and single-path enforcement.
- Auditing, key ownership, and integration tests covering bypass/proxy changes.
- Never granting `X-User-Roles=ADMIN` merely because a request arrives from a private IP.

This model is complex and easy to misuse; for new WebFlux systems, prefer independent Bearer token verification or signed internal assertions at the service.

### 5.4. "TokenRelay" is not proof that all headers are safe

Spring Cloud Gateway provides a TokenRelay mechanism in the OAuth2 Client/authorized client context to forward access tokens downstream. However:
- Not every bearer-only gateway needs the `TokenRelay` filter.
- TokenRelay does not make `X-User-Id` trustworthy.
- Downstream still needs to verify the access token or be protected by another controlled trust architecture.
- The access token must match the downstream's audience, scope, and purpose.
- Forwarding tokens across routes must never leak bearer credentials to an unauthorized service.

This lesson's example **does not use TokenRelay**: the gateway forwards the request to the backend, and the backend verifies the Bearer header itself. When implementing a complex OAuth2 Client setup, define the token forwarding/exchange mechanism explicitly instead of blindly adding a filter.

## 6. Multi-tenant: A Tenant Header Is Never a Permission

Consider three types of tenant context:

| Tenant Source | Example | Meaning |
| --- | --- | --- |
| URL path | `/api/tenants/tenant-b/reports` | Client wants to access tenant B's resources |
| HTTP header | `X-Tenant-Id: tenant-b` | Client-declared; does not prove membership |
| Verified JWT claim | `tenant_id=tenant-a` | AS attested a tenant context per token contract; still needs internal policy |
| Database membership | `user=alice, tenant-a, role=READER` | Authoritative internal source determining whether the user may access a specific tenant and object |

**Never** use `X-Tenant-Id` to override the token's `tenant_id`. If the token is only for tenant A while the URL requests tenant B, reject the request regardless of what headers say.

### 6.1. Minimal check in the example

~~~java
String requestedTenant = tenantIdFromPath;
String tokenTenant = jwt.getClaimAsString("tenant_id");

if (!requestedTenant.equals(tokenTenant)) {
    return Mono.error(new ResponseStatusException(
        HttpStatus.FORBIDDEN, "Tenant mismatch"));
}
~~~

This is the **minimal check** when the access token contract restricts a token to a single tenant. In real B2B multi-tenancy:
- A user may belong to multiple tenants.
- A token may contain a list of tenants or only a subject; membership must be checked in the database.
- When a user switches tenants, reauthorization/token refresh or a backend permission lookup is required per policy.
- If a token carries `tenant_id` without the issuer verifying membership, the signed claim alone is not authoritative.
- Owner/tenant checks must be enforced in **repository queries/updates**, avoiding checking a request parameter and then running an unscoped query.

Wrong example:

~~~java
// ANTI-PATTERN: client chooses tenantId itself and runs a bare query.
return repository.findByReportId(reportId);
~~~

Safer architectural intent example:

~~~java
// ARCHITECTURE SNIPPET: repository is already scoped by tenant
// and user permission/membership has been checked separately.
return repository.findByTenantIdAndReportId(
    authorizedTenantId, reportId);
~~~

The repository method above is a hypothetical interface, not a built-in Spring API. In production, security policy should enforce ownership/tenant at the data boundary to prevent IDOR/BOLA.

### 6.2. Tenant in a subdomain is also client input

`tenant-a.app.example.com` can serve as routing context, but the Host header can be spoofed if proxies do not validate it. Never treat a hostname or `X-Forwarded-Host` as proof that the user belongs to that tenant. Proper flow:
1. The edge validates canonical host mapping and sanitizes `Forwarded/X-Forwarded-Host`.
2. The gateway routes according to the resolved tenant.
3. The backend maps the verified identity to membership in that tenant.
4. The service returns only data belonging to the authorized tenant.

### 6.3. Multi-issuer and JWKS SSRF

In multi-tenant OIDC/JWT, an unverified token can claim:

~~~json
{"iss":"https://attacker.example","sub":"admin","roles":["ADMIN"]}
~~~

If the Resource Server fetches JWKS from whatever `iss` is written in the JWT without an allowlist, an attacker can mint a token and host their own signing key. Proper design:
- Accept only trusted issuer URIs in an approved registry/configuration.
- Each issuer has its own decoder, audience/algorithm/keys, and tenant mapping.
- Never blindly trust `X-Issuer`, `X-Jwks-Url`, or a JWT's `jku` header.
- If using a multi-issuer resolver, the issuer selection policy must prevent SSRF/dynamic trust expansion.
- An `ADMIN` role from tenant A's IdP does not automatically grant global admin across the entire system.

## 7. Demo Project: Gateway and Downstream Resource Server

This lesson splits into **two Java 17+ applications** to make the boundary explicit:

- **gateway**: Spring Cloud Gateway **4.1.9** (release train **2023.0.6**, compatible with Spring Boot **3.3.13**), listening on `8080`; strips client identity headers; routes `/api/**` downstream.
- **resource-service**: Spring Boot WebFlux Resource Server, listening on `8090`; never reads user/role/tenant from HTTP headers; trusts only verified JWTs and enforces scope + tenant.

Two separate Gradle projects. Version numbers are pinned to illustrate the APIs; this does not imply **end-of-support** lines should be chosen for production at the time of reading.

### 7.1. Directory Structure

~~~text
header-trust-lab/
├── gateway/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/
│       ├── java/demo/gateway/GatewayApplication.java
│       └── resources/application.yml
└── resource-service/
    ├── settings.gradle
    ├── build.gradle
    └── src/
        ├── main/
        │   ├── java/demo/resource/
        │   │   ├── ResourceApplication.java
        │   │   ├── SecurityConfig.java
        │   │   └── ReportController.java
        │   └── resources/application.yml
        └── test/java/demo/resource/
            └── HeaderSpoofingTests.java
~~~

The local demo uses `localhost:8080` and `localhost:8090` for observability. **This is not a production network boundary**. Production must place resource-service behind a private service/network ACL; the backend must not be reachable from the Internet.

## 8. Gateway: Stripping Client-Supplied Identity Headers

### 8.1. Gradle build

`gateway/settings.gradle`:

~~~groovy
rootProject.name = 'gateway'
~~~

`gateway/build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2023.0.6'
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Cloud 2023.0.6 manages Spring Cloud Gateway 4.1.x and is compatible with Boot 3.3.13 in this example. Do not mix the Spring Cloud Gateway MVC starter with reactive Gateway here.

### 8.2. GatewayApplication

`gateway/src/main/java/demo/gateway/GatewayApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

### 8.3. Gateway application.yml

`gateway/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: resource-api
          uri: http://127.0.0.1:8090
          predicates:
            - Path=/api/**
          filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Roles
            - RemoveRequestHeader=X-User-Roles
            - RemoveRequestHeader=X-Tenant-Id
            - RemoveRequestHeader=X-Authenticated-User
            - RemoveRequestHeader=X-Auth-Request-User
            - RemoveRequestHeader=X-Principal
            - RemoveRequestHeader=X-Forwarded-User
            - RemoveRequestHeader=X-Organization-Id
~~~

Key points:
1. Route `/api/**` forwards downstream on port 8090, keeping the corresponding path. `StripPrefix` is not used in this example.
2. `RemoveRequestHeader` deletes the configured header names **before sending downstream to the backend**.
3. The `Authorization` header **is not stripped** because downstream needs the Bearer JWT to authenticate. This gateway configuration does not decode JWTs itself.
4. **This gateway only illustrates forwarding + sanitization, not an authentication gate itself**. Resource-service must still verify the token rather than trusting a request merely because it passed through the gateway.
5. Other header names used by the organization (legacy identity, service mesh assertions, custom groups) must be added to the gateway policy or replaced with an allowlist header-forwarding policy.
6. Route configuration alone does not replace a firewall; in production, block all direct-to-backend bypasses.
7. Proxies/LBs in front of the gateway must separately handle `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, and TLS termination. Never confuse them with user identity.
8. If the gateway routes to multiple services, apply the filter everywhere identity headers could be received, not just `resource-api`.

**Architecture warning:** Some systems have a pre-auth service that writes `X-Authenticated-User` after verifying a JWT. If that service sits **behind** the gateway and uses the same header name, you must define filter ordering before/after authentication and ensure only a single trusted component can set the header. This demo does not generate identity headers, so it has no such precedence conflict.

## 9. Resource Service: Always Build Authentication from a Verified JWT

### 9.1. Gradle build

`resource-service/settings.gradle`:

~~~groovy
rootProject.name = 'resource-service'
~~~

`resource-service/build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-resource-server` brings in Resource Server and JOSE/JWT components. Do not include Servlet `spring-boot-starter-web` when Security code relies on reactive `ServerHttpSecurity`.

### 9.2. application.yml

`resource-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8090

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/lab
          jwk-set-uri: https://issuer.example.test/realms/lab/jwks
          audiences:
            - report-api
~~~

The `example.test` URLs are **architectural placeholders** for an AS/JWKS; real login is impossible until replaced with a trusted provider. In production:
- `iss` must match the access token's issuer.
- `aud` must contain `report-api`.
- The JWK Set URI must be provided by a trusted IdP and served over valid HTTPS.
- The decoder verifies signature, algorithm, and timestamps, accepting only allowed algorithms.
- If you define a custom `ReactiveJwtDecoder` bean, you must preserve issuer/audience validators; Boot properties do not automatically apply to custom beans in all cases.
- Do not treat an OIDC ID Token (whose audience is typically the OAuth client) as an API access token.

### 9.3. Main

`resource-service/src/main/java/demo/resource/ResourceApplication.java`:

~~~java
package demo.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig: scopes come from the JWT, never headers

`resource-service/src/main/java/demo/resource/SecurityConfig.java`:

~~~java
package demo.resource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .pathMatchers(HttpMethod.GET,
                    "/api/tenants/*/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_admin")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

- `oauth2ResourceServer(...).jwt(...)` validates Bearer JWTs. No filter in this code reads `X-User-Id`, `X-Tenant-Id`, or `X-User-Roles` to grant permissions.
- Spring Security maps `scope`/`scp` to `SCOPE_*` authorities by default.
- `/api/admin` requires the `admin` scope in the **verified token**, unaffected by an `X-User-Roles: ADMIN` header.
- `/api/tenants/*/reports` requires the `reports.read` scope, and still must check the tenant in the controller/service.
- `anyExchange().denyAll()` enforces deny-by-default.
- HTTP Basic/form login are disabled because the demo uses Bearer tokens only.
- Since the demo only exposes safe-method GETs, default CSRF does not need changing; if unsafe methods are added, evaluate credentials and CSRF per threat model.

### 9.5. Controller: URL tenant must match the verified token

`resource-service/src/main/java/demo/resource/ReportController.java`:

~~~java
package demo.resource;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/whoami")
    Mono<Map<String, String>> whoami(
            @AuthenticationPrincipal Jwt jwt) {

        String tenant = jwt.getClaimAsString("tenant_id");

        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString(),
            "tenant", tenant == null ? "" : tenant
        ));
    }

    @GetMapping("/api/tenants/{tenantId}/reports")
    Mono<Map<String, Object>> reports(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant_id");

        // JWT is verified before @AuthenticationPrincipal is injected.
        // Does not read X-Tenant-Id or X-User-Roles.
        if (!tenantId.equals(tokenTenant)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Tenant mismatch"));
        }

        Map<String, Object> result = Map.of(
            "tenant", tenantId,
            "subject", jwt.getSubject(),
            "reports", List.of("report-1", "report-2")
        );

        return Mono.just(result);
    }

    @GetMapping("/api/admin")
    Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("status", "admin scope granted"));
    }
}
~~~

**Important:** `@AuthenticationPrincipal Jwt` is populated only once Spring Security has created a valid Authentication. Never parse the raw `Authorization` header inside a controller to extract `sub`. The route never uses `X-Tenant-Id` as authority.

The `tenantId.equals(tokenTenant)` check is the **minimal demo rule for single-tenant tokens**. Production typically requires:
- Local user ↔ tenant membership in the DB.
- Per-report owner/ACL checks.
- Canonicalized and non-empty tenant IDs across URL/host/claims per contract.
- If a token carries multiple tenants, membership checks rather than simple equality.
- Preventing an attacker from changing `tenant_id` via a request header.
- Never granting a global admin role based on a client-sent user ID.

## 10. Testing with WebTestClient and Real RSA-Signed JWTs

**Why not use only `mockJwt()`?** When a test uses `mockJwt()`, Spring Security Test can inject a pre-built `Authentication` and authorities without invoking the decoder; such tests can skip the entire signature/issuer/audience pipeline. This lesson uses genuinely signed JWTs to exercise the authentication path.

Test-only setup:
- Generate a fresh RSA keypair inside the test JVM.
- Sign JWTs via `NimbusJwtEncoder` using a private key **confined strictly to tests**.
- Configure `NimbusReactiveJwtDecoder` with the matching public key.
- Add issuer and `report-api` audience validators.
- Send Bearer strings through `WebTestClient` bound to the WebFlux application context.
- Verify that requests carrying forged identity headers **do not alter the principal, roles, or tenant**.

No real IdP is needed when running unit/integration tests, though HTTP JWKS retrieval, proxy network isolation, and Gateway filter behavior must have dedicated deployment tests.

### 10.1. HeaderSpoofingTests.java

`resource-service/src/test/java/demo/resource/HeaderSpoofingTests.java`:

~~~java
package demo.resource;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(HeaderSpoofingTests.LocalJwtKeys.class)
class HeaderSpoofingTests {

    private static final String ISSUER =
        "https://issuer.example.test/realms/lab";

    @Autowired
    ApplicationContext context;

    @Autowired
    JwtEncoder encoder;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalJwtKeys {

        @Bean
        KeyPair keyPair() {
            try {
                KeyPairGenerator gen =
                    KeyPairGenerator.getInstance("RSA");
                gen.initialize(2048);
                return gen.generateKeyPair();
            }
            catch (GeneralSecurityException ex) {
                throw new IllegalStateException(ex);
            }
        }

        @Bean
        JwtEncoder testJwtEncoder(KeyPair keys) {
            RSAKey rsa = new RSAKey.Builder(
                (RSAPublicKey) keys.getPublic())
                .privateKey((RSAPrivateKey) keys.getPrivate())
                .keyID("test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<SecurityContext>(
                    new JWKSet(rsa)));
        }

        @Bean
        ReactiveJwtDecoder testJwtDecoder(KeyPair keys) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withPublicKey(
                    (RSAPublicKey) keys.getPublic())
                    .build();

            OAuth2TokenValidator<Jwt> audience =
                jwt -> jwt.getAudience().contains("report-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Wrong audience",
                            null));

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience));

            return decoder;
        }
    }

    String signedToken(
            JwtEncoder signer,
            String issuer,
            String audience,
            String subject,
            String tenant,
            String scopes,
            Instant expiresAt) {

        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject(subject)
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(10))
            .notBefore(now.minusSeconds(10))
            .expiresAt(expiresAt)
            .claim("tenant_id", tenant)
            .claim("scope", scopes)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return signer.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    String aliceTenantA() {
        return signedToken(
            encoder, ISSUER, "report-api",
            "alice-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));
    }

    @Test
    void publicHealthDoesNotRequireBearer() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void noBearerCannotBecomeAliceByUserHeader() {
        client.get().uri("/api/whoami")
            .header("X-User-Id", "alice-sub")
            .header("X-Authenticated-User", "alice-sub")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void noBearerCannotBecomeAdminByRoleHeader() {
        client.get().uri("/api/admin")
            .header("X-User-Roles", "ROLE_ADMIN")
            .header("X-Roles", "ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validJwtDefinesPrincipalNotSpoofedHeaders() {
        client.get().uri("/api/whoami")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-User-Id", "ceo-sub")
            .header("X-Authenticated-User", "ceo-sub")
            .header("X-Tenant-Id", "tenant-victim")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice-sub")
            .jsonPath("$.tenant").isEqualTo("tenant-a")
            .jsonPath("$.issuer").isEqualTo(ISSUER);
    }

    @Test
    void spoofedRoleCannotGrantAdminWithoutScope() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-User-Roles", "ROLE_ADMIN")
            .header("X-Roles", "ADMIN")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void matchingTokenTenantCanReadReports() {
        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("tenant-a")
            .jsonPath("$.subject").isEqualTo("alice-sub")
            .jsonPath("$.reports[0]").isEqualTo("report-1");
    }

    @Test
    void tenantBPathCannotBeAuthorizedByHeaderTenantB() {
        client.get().uri("/api/tenants/tenant-b/reports")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-Tenant-Id", "tenant-b")
            .header("X-User-Roles", "OWNER")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void headerTenantAStillCannotOverrideTenantBPath() {
        client.get().uri("/api/tenants/tenant-b/reports")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-Tenant-Id", "tenant-a")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tenantSpecificTokenOfBobCannotClaimAliceTenant() {
        String bobTenantB = signedToken(
            encoder, ISSUER, "report-api",
            "bob-sub", "tenant-b", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(bobTenantB))
            .header("X-User-Id", "alice-sub")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validJwtWithoutReportScopeIsForbidden() {
        String token = signedToken(
            encoder, ISSUER, "report-api",
            "alice-sub", "tenant-a", "profile",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void malformedBearerWithAdminHeadersIsUnauthorized() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("not.a.valid.jwt"))
            .header("X-User-Roles", "ROLE_ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIsUnauthorizedEvenWithUserHeaders() {
        String token = signedToken(
            encoder, "https://evil.example", "report-api",
            "ceo-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .header("X-User-Id", "ceo-sub")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsUnauthorized() {
        String token = signedToken(
            encoder, ISSUER, "unrelated-api",
            "alice-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredJwtIsUnauthorized() {
        String token = signedToken(
            encoder, ISSUER, "report-api",
            "alice-sub", "tenant-a", "reports.read",
            Instant.now().minusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void jwtFromUntrustedSigningKeyIsUnauthorized() {
        KeyPair other;
        try {
            KeyPairGenerator gen =
                KeyPairGenerator.getInstance("RSA");
            gen.initialize(2048);
            other = gen.generateKeyPair();
        }
        catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }

        RSAKey jwk = new RSAKey.Builder(
            (RSAPublicKey) other.getPublic())
            .privateKey((RSAPrivateKey) other.getPrivate())
            .keyID("test-key")
            .build();

        JwtEncoder attackerEncoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<SecurityContext>(
                new JWKSet(jwk)));

        String forged = signedToken(
            attackerEncoder, ISSUER, "report-api",
            "ceo-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(forged))
            .header("X-User-Roles", "ROLE_ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

### 10.2. Test Matrix — Cases to Distinguish

| Scenario | Credential/Header | Expected |
| --- | --- | --- |
| Public health | No token | **200** |
| Only `X-User-Id=alice` | No token | **401** |
| Only `X-User-Roles=ROLE_ADMIN` | No token | **401** |
| Alice tenant-a JWT + fake X-User-Id=CEO | Valid token, forged header | **200** on whoami but subject remains Alice |
| Alice read-scope JWT + fake ADMIN role | Valid token, forged header | **403** on admin |
| Alice tenant-a JWT → tenant-a URL | Valid read scope | **200** |
| Alice tenant-a JWT → tenant-b URL, tenant-b header | Cross-tenant | **403** |
| Alice tenant-a JWT → tenant-b URL, tenant-a header | Header does not alter URL ownership | **403** |
| Bob tenant-b JWT → tenant-a URL, fake X-User-Id Alice | Cross-tenant | **403** |
| Valid JWT missing reports.read scope | Insufficient capability | **403** |
| Malformed Bearer + fake ADMIN headers | Invalid token | **401** |
| Wrong-issuer JWT + fake X-User-Id | Issuer validation | **401** |
| Wrong-audience JWT | Wrong `aud` | **401** |
| Expired JWT | Expired | **401** |
| Token signed by attacker key | Signature mismatch | **401** |

There are **15 test methods**. They verify that downstream does not trust user/role/tenant headers, that JWTs must be verified, and that scope and tenant must be valid.

### 10.3. Limitations of the Test Suite

**The tests above are resource-service tests and do not test the live Gateway route.** They prove that even if spoofed headers reach the backend, the backend will not use them to grant permissions. However, they do not yet prove:
- That the Gateway strips headers before forwarding downstream (requires Gateway E2E tests with an echo/stub upstream).
- That the network firewall blocks direct bypasses.
- That TLS/mTLS is properly configured.
- Network HTTP JWKS retrieval/rotation and issuer discovery.
- Real tenant membership database/owner checks.
- That the Gateway does not accidentally forward Bearer tokens to unintended routes.
- Duplicate-header handling across actual proxies/libraries in deployment.

**Production must have E2E tests covering the entire chain**, rather than extrapolating from controller tests alone.

## 11. Running Both Applications and Testing with curl

Install JDK 17+ and Gradle 8.x. From each project directory:

~~~bash
# Terminal A: downstream
cd resource-service
gradle bootRun
~~~

~~~bash
# Terminal B: gateway
cd gateway
gradle bootRun
~~~

In the local example, `resource-service` uses port `8090` and Gateway uses `8080`. Because the `example.test` issuer is only a placeholder, **no valid production JWT is available** unless you configure a real AS. The tests in Section 10 generate their own keypair and therefore run offline:

~~~bash
cd resource-service
gradle test
~~~

If using the Gradle Wrapper, run `./gradlew test` on Unix/macOS or `gradlew.bat test` on Windows.

### 11.1. Only forged headers, no token

~~~bash
curl -i \
  -H "X-User-Id: admin" \
  -H "X-User-Roles: ROLE_ADMIN" \
  http://localhost:8080/api/admin
~~~

Expect downstream to return **401 Unauthorized**, not 200, because no accepted Bearer JWT was provided.

### 11.2. Self-declared tenant header does not change permissions

~~~bash
curl -i \
  -H "X-User-Id: ceo" \
  -H "X-Tenant-Id: tenant-b" \
  -H "Authorization: Bearer ACCESS_TOKEN_ALICE_TENANT_A" \
  http://localhost:8080/api/tenants/tenant-b/reports
~~~

`ACCESS_TOKEN_ALICE_TENANT_A` is a **placeholder**, not a valid JWT. With a **real token** issued by a trusted issuer for Alice in tenant-a carrying the `reports.read` scope, the response must be **403** per the demo contract because the path requests tenant-b. With this placeholder, the request actually returns **401** because the token fails verification.

**Never place real tokens in public documentation, shell history, or logs.** Use HTTPS outside local environments, secret-protection tooling, and tokens whose audience matches the service.

### 11.3. Direct backend security test in a lab environment

Send a request with forged identity headers directly to `http://localhost:8090/api/whoami` **without a token**:

~~~bash
curl -i \
  -H "X-Authenticated-User: ceo" \
  -H "X-User-Roles: ROLE_ADMIN" \
  http://localhost:8090/api/whoami
~~~

Expect **401**. This demonstrates that downstream does not blindly trust headers; however, production must still **block public access to 8090** with firewalls/private networking.

### 11.4. How to test Gateway header stripping end-to-end

To prove `RemoveRequestHeader` actually runs (as opposed to testing that downstream ignores headers):
1. Stand up a **test-only stub upstream** that returns a controlled list of received header names; never enable a public header-echo endpoint in production.
2. Point a test Gateway route at that stub.
3. Send requests through the Gateway containing `X-User-Id`, `X-User-Roles`, and `X-Tenant-Id` in mixed casing and duplicate headers.
4. Assert that the stub **did not** receive any of the stripped headers.
5. Assert that the stub still receives `Authorization` only on routes authorized to receive Bearer tokens, never forwarding it to unrelated services.
6. Temporarily remove one `RemoveRequestHeader` in the test environment to verify both positive and negative behavior.
7. Verify that firewall/NetworkPolicy rules block direct backend access from client networks.
8. Repeat these tests whenever adding a gateway route, adding an auth proxy, or upgrading Spring Cloud versions.

Never use a public header-echo endpoint to debug live credentials. Test logs must redact Bearer tokens, cookies, and personal data.

## 12. Header Spoofing Variants to Handle at the Gateway

### 12.1. Header names, casing, multiple values, and value normalization

Variants:

~~~http
X-User-Id: alice
x-user-id: ceo
X-User-Roles: AUDITOR,ADMIN
X-User-Roles: OWNER
X-Tenant-Id: tenant-a
X-Tenant-Id: tenant-b
~~~

Defenses:
- Use HTTP libraries with proper case-insensitive semantics.
- Enforce a single canonical schema for internal identity assertions.
- Reject ambiguous duplicates wherever assertions are consumed.
- Never use raw `getFirst()` to trust "the first value added by the gateway."
- The Gateway should strip all client-provided identity headers before adding any controlled assertion.
- Test against the real proxy chain if HTTP/1.1 ↔ HTTP/2 ↔ proxy normalization differs.

### 12.2. Header injection via a proxy/sidecar in front of the Gateway

If a WAF/CDN/Ingress forwards a request carrying a forged `X-Authenticated-User` to the Gateway, the Gateway must strip it before routing. If another auth proxy *adds* a user header later, clearly define which layer is authorized to set it and which may only consume it.

Avoid having multiple layers "append" identity headers, as downstream could pick the wrong value. Headers such as `X-Auth-Request-User` are meaningful only after passing through a trusted auth proxy under an explicit network/protocol contract.

### 12.3. `X-Forwarded-*` is network metadata, not a user

`X-Forwarded-For: 127.0.0.1` does not prove the client is an internal admin. `Forwarded: proto=https;host=...` does not prove identity, even though frameworks use it to construct public URLs. The edge must sanitize this metadata via a trusted-hop policy; never use it as a security authority.

### 12.4. `Host`, `X-Original-URL`, method overrides, and route mismatch

Some reverse proxies support URL/Host/method rewrites driven by headers. If the gateway checks authorization on one path while the backend receives another, attackers may attempt a bypass. Require:
- A Host allowlist at the edge.
- Consistent path/encoding canonicalization between proxy and backend.
- Rejecting arbitrary `X-Original-URL`, `X-Rewrite-URL`, and `X-HTTP-Method-Override` unless required by the architecture and sanitized.
- Downstream authorization against the actual resource, not solely the gateway matcher.
- Never deriving a tenant from raw Host without validating a mapping.

### 12.5. Never use CORS as a substitute for authentication

CORS is a browser cross-origin policy, not API authentication. A client such as curl or mobile can send `X-User-Roles` even if browser CORS blocks that header. Therefore:
- A CORS allowlist does not prevent header spoofing from non-browser clients.
- CSRF is a separate risk for ambient browser credentials; never disable CSRF app-wide just because you use a gateway.
- OAuth2 Bearer JWT validation and authorization determine API access rights.
- Rate limiting and IP allowlists are defense in depth, not identity substitutes.

## 13. Designing Properly Layered Multi-Tenant Authorization

A Resource Server may require three conditions:

~~~text
Authentication:
  Verified JWT:
    (issuer, subject)
    audience matches report-api
    exp/nbf valid
    scopes include reports.read

Tenant authorization:
  Local mapping (issuer,subject) → localUserId
  Local membership ACTIVE for requested tenant

Object authorization:
  Report belongs to requested tenant
  Local user can read this report
~~~

Combined condition:

~~~text
ALLOW_READ_REPORT =
    signed access token valid
AND token has SCOPE_reports.read
AND local identity ACTIVE
AND membership active for requested tenant
AND report.tenant_id = requested tenant
AND report ACL/owner permits action
~~~

A gateway route may add coarse authorization (such as requiring login before routing), but downstream must enforce the final policy, especially when resource IDs and private data are involved.

### 13.1. Never treat a query parameter as an "entitlement"

~~~http
GET /api/reports/123?tenantId=tenant-admin
X-Tenant-Id: tenant-admin
~~~

`tenantId` in the query is merely a client request parameter. Never use it as proof that the user belongs to that tenant. If querying a repository with a client-supplied tenant ID, enforce membership and row-level predicates on the backend.

### 13.2. Never substitute email for user identity

A JWT with `email=ceo@company.example` does not automatically grant CEO privileges. Emails can change or be recycled, and multiple issuers can issue matching emails. A stable identity key is typically a validated `(iss, sub)` mapped to a local user UUID. Admin privileges and tenant membership are governed by local policy.

### 13.3. A tenant ID in a JWT is an issuer assertion that still needs policy

A signed `tenant_id=tenant-a` claim is only trustworthy in provenance if:
- The issuer, audience, and token purpose are correct.
- The IdP/AS is authoritative for determining tenant membership.
- Claim semantics are explicit and synchronized with business policy.

If the AS merely echoes a client-requested tenant without verifying membership, even a signed claim is insufficient. The backend must enforce permissions at the data layer. **A signature proves who issued a claim, not that the provider applied the right business policy.**

## 14. "Confused Deputy" and Lateral Movement Risks

**Confused deputy:** a trusted gateway/service authorized to call a backend acts on attacker input without verifying end-user permissions. For example, the Gateway has an mTLS service identity and the backend trusts every request from the Gateway; the client tells the gateway to send `X-Tenant-Id: victim`. If the Gateway skips tenant checks and the backend skips End User auth, the attacker borrows the service identity to access another tenant.

Mitigations:
- Service identity (mTLS) **must never** replace end-user authorization.
- Bind the end-user principal and scopes into a verified token/assertion.
- Use narrow audiences per downstream service.
- Enforce tenant/resource-level checks at the service.
- If using a gateway-signed assertion, never grant scopes exceeding the original token and never source the user ID from a client header.
- Audit the external subject, authenticated client/service, tenant, and policy decision.

**Lateral movement:** a low-privilege service can directly call another backend in the cluster if that backend trusts `X-User-Roles=ADMIN`. Defend with NetworkPolicy/service mesh identity, token audience + authorization, zero-trust between services, and deny-by-default.

## 15. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| No token but sending X-User-Id still returns 200 | Backend has a pre-auth header bypass | Remove raw-header trust; verify JWT/assertion |
| Sending X-User-Roles=ADMIN grants admin | Mapper trusts client header | Derive roles from Authentication/DB policy |
| Tenant A JWT accesses tenant B | Using X-Tenant-Id/URL as entitlement | Enforce JWT/local membership + object checks |
| Gateway strips properly yet backend is still spoofable | Backend directly reachable or another route omits strip | Private network + downstream verification |
| Lowercase header slips past custom policy | Broken case-sensitive parsing | Use proper HTTP header semantics and E2E tests |
| Repeated header behaves differently across proxy/service | Inconsistent normalization | Reject duplicates/canonicalize at boundary |
| Valid JWT gets backend 401 | Wrong issuer/audience/signature/time/alg | Inspect filtered decoder/validator/JWKS logs |
| Valid JWT gets backend 403 | Missing scope or tenant mismatch | Check `SCOPE_` and membership |
| Gateway loses Authorization header | Filter/security middleware stripped it | Check route forwarding policy |
| Password reset link points to attacker domain | Trusting Host/X-Forwarded-Host | Canonical public URL and proxy sanitization |
| Wrong Secure/HSTS cookie after TLS termination | Inconsistent public/internal scheme | Trusted Forwarded boundary + edge TLS |
| Tenant A user hits tenant B URL and gets data | Query not scoped by tenant | Repository predicates/row-level security |
| Only mockJwt tests run and everything passes | Mock bypasses JWT signature validation | Signed Bearer integration tests |
| IP-based allowlist bypassed | Trusting client-sent X-Forwarded-For | Edge overwrite + trusted proxies |
| Internal assertion accepted from client | Plain custom header without signature/peer auth | Verify assertion + mTLS + strip external header |
| Auth proxy adds X-User-Id while keeping old header | Wrong append/overwrite behavior | Clear before set; reject ambiguous values |
| Filter stops running after Gateway upgrade | Changed property path/version | Check docs for exact release train and E2E tests |

## 16. Exercises and Questions

**Q1.** A client sends `X-User-Roles: ROLE_ADMIN`. Will it receive the admin role?

**Answer:** No. Headers are client-supplied data, not signed authentication evidence.

**Q2.** The Gateway strips `X-User-Roles`, yet the backend remains directly reachable. Is it secure?

**Answer:** No. Network isolation and a downstream that never trusts raw headers are both required.

**Q3.** When does `RemoveRequestHeader=X-User-Id` take effect?

**Answer:** On requests routed through that gateway before being sent upstream; it has no effect on requests bypassing the gateway.

**Q4.** Where should a downstream service obtain user identity?

**Answer:** From an `Authentication` produced by Bearer JWT validation or a verified signed internal assertion—never from self-declared headers.

**Q5.** Is `Authorization: Bearer ...` inherently trustworthy?

**Answer:** No. It is a credential sent over HTTP; it is trusted only after the decoder checks signature, issuer, audience, timestamps, and purpose.

**Q6.** With Alice's tenant A Bearer token and header `X-Tenant-Id: tenant B`, can the caller read B's data?

**Answer:** Not based on the header. Valid membership/tenant authorization is required.

**Q7.** With Alice's tenant A token and a URL requesting tenant B, what is the demo result?

**Answer:** 403 when the token is valid and has the scope, due to tenant mismatch.

**Q8.** With only a user header and no Bearer token, what is the demo result on a protected endpoint?

**Answer:** 401.

**Q9.** Valid JWT without `reports.read`, what is the demo result?

**Answer:** 403 on routes requiring `SCOPE_reports.read`.

**Q10.** Does `X-Forwarded-For: 127.0.0.1` prove an internal admin?

**Answer:** No. Clients can forge it if the edge does not strip/overwrite it.

**Q11.** Does mTLS between Gateway → backend prove the end user is CEO?

**Answer:** No. It authenticates the service peer, not end-user identity or tenant permissions.

**Q12.** When using a gateway-signed internal JWT, what must be checked?

**Answer:** Signature, issuer, target audience, expiration, algorithm, tenant/scopes/provenance, and a policy that does not exceed the external token.

**Q13.** Should the gateway forward tokens to every service for convenience?

**Answer:** No. Tokens require matching audience/scope; never leak bearer credentials to unauthorized services.

**Q14.** Seeing `X-User-Id` inside a controller request means the gateway failed to strip it?

**Answer:** Possibly: the request bypassed the gateway, a route omitted the filter, or an internal layer re-added it. Trace the pipeline and run E2E tests.

**Q15.** Should an untrusted issuer be allowed to advertise its own JWKS URL inside the JWT?

**Answer:** No. Trusted issuers and JWKS URLs must be allowlisted/managed centrally.

**Q16.** Why should a subdomain tenant never serve as authorization on its own?

**Answer:** Host is routing context that can be forged/altered; user membership must be verified separately.

**Q17.** Does a `mockJwt()` test verify real RSA signatures?

**Answer:** No. It typically bypasses the decoder; signed-token Bearer tests are required.

**Q18.** Why test duplicate headers and mixed casing?

**Answer:** HTTP header names are case-insensitive, and different proxies/frameworks may pick different values on duplicates, creating bypasses when parsed manually.

**Q19.** Does `ROLE_ADMIN` for tenant A automatically grant admin on tenant B?

**Answer:** No. Tenant-scoped permissions and object-level authorization are required.

**Q20.** What is the single most important control?

**Answer:** Never grant privileges from client-declared headers; **verify tokens/assertions at trust boundaries, isolate backends, strip untrusted identity headers, and enforce tenant/resource ownership**.

## 17. Production Checklist

### Gateway / Ingress

- [ ] Backend ports are not exposed to the Internet; Kubernetes NetworkPolicy/firewall/security groups are active.
- [ ] Gateway/edge strips all client-supplied identity/role headers per contract (including legacy names).
- [ ] Case-insensitive HTTP header names and duplicate handling tested across the actual proxy chain.
- [ ] Only trusted components may mint internal assertions; signed + short-lived + audience-bound.
- [ ] Never grant user identity based on header names or private source IPs.
- [ ] `Forwarded`/`X-Forwarded-*` are sanitized at the edge and never used to determine roles.
- [ ] Authorization is never forwarded to unrelated downstream services; check token audience.
- [ ] TLS/mTLS applied to appropriate hops without confusing service identity with end users.
- [ ] Route rewrite/path/Host/HTTP method semantics match between Gateway and backend.
- [ ] E2E tests verify header removal on routes and block bypasses.

### Spring Security / Resource Server

- [ ] Use `spring-boot-starter-oauth2-resource-server` in API-protecting WebFlux services.
- [ ] `ReactiveJwtDecoder` verifies signature, issuer, audience, exp/nbf, and algorithm.
- [ ] `SecurityWebFilterChain` uses `ServerHttpSecurity` and `oauth2ResourceServer().jwt()`.
- [ ] Never read user/roles from `ServerHttpRequest.getHeaders()` to bypass Authentication.
- [ ] Scopes/roles come from trusted sources mapped via allowlist; never auto-grant ADMIN.
- [ ] Default-deny rule; protected routes require Bearer tokens.
- [ ] Authentication and object/tenant authorization are separated.
- [ ] Map `(iss,sub)` to a stable local user ID when needed, not email.
- [ ] Account status/membership/revocation policy explicitly defined for unexpired JWTs.
- [ ] Never treat a signed role from tenant A as global admin for tenant B.
- [ ] Ensure resource queries enforce tenant/owner predicates.
- [ ] Never log raw JWTs, secret keys, session cookies, or sensitive PII.

### QA / Monitoring

- [ ] Header-only without token → 401.
- [ ] Alice JWT + forged X-User-Id Bob → principal remains Alice.
- [ ] Read JWT + forged admin header → admin endpoint 403.
- [ ] Tenant A JWT + tenant B URL/tenant B header → 403.
- [ ] Valid JWT with matching tenant and scope → 200.
- [ ] JWT missing scope → 403.
- [ ] JWT with invalid signature/issuer/audience/expired → 401.
- [ ] Dedicated tests for Gateway stripping, network bypass, and JWT verification.
- [ ] Re-verify proxy/header policies after every Gateway/version upgrade.
- [ ] Auditing/alerts enabled for header spoofing attempts, direct backend access, failed JWT verification, and cross-tenant attempts.

## 18. References

- Spring Cloud Gateway 4.1 — RemoveRequestHeader GatewayFilter: https://docs.spring.io/spring-cloud-gateway/reference/4.1/spring-cloud-gateway/gatewayfilter-factories/removerequestheader-factory.html
- Spring Cloud 2023.0 release train (Boot 3.3 compatible): https://docs.spring.io/spring-cloud-release/reference/2023.0/index.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Testing Reactive OAuth2: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Boot 3.3 — OAuth2 Resource Server issuer/audience properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Framework — Forwarded Headers and trusted proxy boundary: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html#webflux-forwarded-headers
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — API Security Broken Object Level Authorization (BOLA): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/

**Remember:** `X-User-Id`, `X-User-Roles`, `X-Tenant-Id`, and other "internal-looking" headers remain client-controllable data. The Gateway should **strip** untrusted identity headers; the backend must **verify the Bearer JWT or signed assertion** and check user/tenant/resource permissions. Network isolation + proxy sanitization + downstream authentication + object-level authorization are complementary layers, none of which completely replaces the others.
