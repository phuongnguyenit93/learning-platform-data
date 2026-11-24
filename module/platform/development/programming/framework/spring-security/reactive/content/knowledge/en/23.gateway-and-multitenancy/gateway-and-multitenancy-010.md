# Boundaries Between HTTP Security, Business Authorization, and Infrastructure Policy

> **Topic:** Spring Security – reactive  
> **Group:** Gateway and Multi-tenancy  
> **Lesson:** Boundaries Between HTTP Security, Business Authorization, and Infrastructure Policy.  
> **Practice baseline:** Java 17+, Spring Boot 3.5.16, Spring Cloud 2025.0.3 (Gateway Server WebFlux 4.3.x), Spring Security 6.5.x. This is a baseline for learning APIs, **not a recommended production release train as of November 2026** because the 3.5/2025.0 lines have reached end of OSS support.

## 1. Problem: If the JWT Is Valid, How Can Data Still Leak?

A SaaS system has two organizations: tenant `acme` owns report `r1` belonging to `alice` and `r2` belonging to `carol`; tenant `beta` has a report with the **exact same ID** `r1` belonging to `bob`. A customer calls:

```http
GET /api/tenants/acme/reports/r1 HTTP/1.1
Host: api.example.test
Authorization: Bearer <valid-JWT-for-alice-acme>
```

Spring Cloud Gateway validates the JWT and sees the `reports.read` scope. If the backend takes `reportId=r1` and queries:

```sql
-- Wrong: does not constrain tenant or actor.
SELECT * FROM reports WHERE id = :reportId;
```

it could return the record belonging to Beta or another user. This is **BOLA/IDOR** (*Broken Object Level Authorization / Insecure Direct Object Reference*). A valid token proves claims issued by a trusted issuer; **it does not prove permission to read a specific record**.

Proper architecture:

```text
Client
  |
  | HTTPS + Bearer JWT + tenant in URL (tenant candidate)
  v
+----------------------------------------------------------+
| GATEWAY: HTTP SECURITY                                   |
| Verify JWT signature/exp/nbf/iss/aud                     |
| Method/path allowlist + coarse scope SCOPE_reports.read |
| Fixed route, strip spoofed headers, quota/throttling     |
+----------------------------------------------------------+
  |
  | Forward JWT to trusted backend; do not forward fake X-User.
  v
+----------------------------------------------------------+
| DOMAIN API: RESOURCE / TENANT AUTHORIZATION              |
| Re-verify JWT (defense in depth)                         |
| pathTenant == verifiedJwt.tenant_id                       |
| activeMembership(jwt.sub, tenant)                         |
| report.tenant_id == tenant AND actorCanRead(report)       |
+----------------------------------------------------------+
  |
  | Tenant-scoped repository query
  v
+----------------------------------------------------------+
| INFRASTRUCTURE / DATA                                    |
| NetworkPolicy, mTLS, TLS, DB RLS, encryption, quotas     |
| Key rotation, secrets, observability, audit              |
+----------------------------------------------------------+
```

**All three boundaries are required:**
- The Gateway decides whether the request may enter an **HTTP API group**.
- The domain service decides whether the actor may touch the **exact tenant and object**.
- Infrastructure constrains network paths, capacity, isolation, and data protection; it does not understand ownership on its own.

### After this lesson, you will be able to

1. Distinguish authentication from HTTP authorization, domain authorization, and infrastructure policies.
2. Place JWT/issuer/audience/scope, tenant/membership/owner, and mTLS/NetworkPolicy/quotas at the right layers.
3. Spot spoofed `X-Tenant-Id`, `X-User-Id`, `Forwarded`, cache keys missing tenants, and SQL queries missing tenant filters.
4. Use independent `SecurityWebFilterChain`s in the Gateway and WebFlux Reports API.
5. Inject `@AuthenticationPrincipal Jwt` to check `tenant_id`/membership/owner in reactive services.
6. Build two Maven projects and 24 unit/HTTP tests proving zero cross-tenant access.
7. Explain HTTP `401`, `403`, `404`, `429`, and `503` by layer.
8. Know the exact limits of `mockJwt()` and what integration tests are still needed before production.

## 2. Per-Layer Responsibility Matrix

| Decision | Primary Layer | Source of Truth | Error Outcome |
| --- | --- | --- | --- |
| Valid TLS, mTLS certificate? | Ingress/infra | PKI, truststore | TLS failure |
| Valid JWT signature/time/issuer/audience? | Gateway **and** backend Resource Server | Trusted AS/JWKS | 401 |
| HTTP URL/method, OAuth scope permitted? | WebFlux security | Verified JWT authorities, route policy | 403 |
| User still belongs to requested tenant? | Domain service | Membership DB/directory | 403/404 |
| User permitted on this specific report? | Domain service | Owner/ACL/sharing/business state | 403/404 |
| Query isolated from other tenants' data? | Repository/DB | Tenant predicate, RLS | No rows/denied |
| Is the backend publicly reachable? | Infrastructure | Firewall/NetworkPolicy/mTLS | Connection blocked |
| Did tenant exceed quota/rate? | Gateway/platform | Quota keyed by verified identity | 429/503 |
| How are keys/secrets/certs rotated? | Infra/SRE | Secrets manager, CA | Incident/availability |
| Who read which object? | Domain audit | Actor, tenant, resource, decision | Audit event |

A security rule `hasAuthority("SCOPE_reports.read")` protects only the **API group**. An RLS policy checking only tenant still does not stop Alice from reading Carol's report in the same tenant. Nor does an mTLS service identity prove an end user's permissions.

### 2.1. Authentication, authorization, and authentication context

- **Authentication:** Did the AS sign the JWT? Are `iss`, `aud`, `exp`, `nbf`, and signature/algorithm valid? Spring builds an `Authentication` for `sub=alice`.
- **HTTP authorization:** Are GET and `SCOPE_reports.read` sufficient to enter this route group?
- **Domain authorization:** Does Alice have active membership in Acme, and does record Acme/r1 grant owner/ACL access to Alice?
- **Infra:** Which workloads can connect to backend/DB, and how are quotas and TLS keys operated?

Spring Security WebFlux stores security data in the **Reactor Context**, never assume a fixed Servlet `ThreadLocal`. Use `@AuthenticationPrincipal Jwt` in controllers and reactive composition in services.

## 3. Tenant Identity: What Can Be Trusted?

```text
Path:           /api/tenants/acme/reports/r1
X-Tenant-Id:    beta                 <- attacker can set this
X-User-Id:      bob                  <- attacker can set this
Host:           acme.api.example.test
Forwarded:      host=beta.example.test
Verified JWT:   sub=alice, tenant_id=acme, scope=reports.read
DB membership:  (alice, acme) active=true
DB record:      (tenant=acme, id=r1, owner=alice)
```

**Path/Host/headers are inputs/candidates, not proof of rights.** `X-Tenant-Id`/`X-User-Id`/`X-Roles` can be forged by any HTTP client unless protected by a dedicated mechanism. `Host` and `X-Forwarded-Host` require trusted domain/ingress rules; never use them to change tenant entitlements or arbitrary downstream URIs.

**Verified JWT** is trustworthy only after passing through a Spring Security Resource Server decoder enforcing issuer, keys, allowed algorithms, audience, and timestamps. AS-issued `tenant_id` can grow stale if a user is removed from a tenant, so **membership** must be verified against an authoritative store. Report tenant and owner must be verified against real data.

In a one-active-tenant-per-JWT model:

```text
JWT verified
AND SCOPE_reports.read
AND pathTenant.equals(jwt.tenant_id)
AND membershipActive(jwt.sub, pathTenant)
AND report.tenant_id == pathTenant
AND ownerOrAclAllows(jwt.sub, report)
```

If a user belongs to multiple tenants or multiple issuers, design explicit claims/permissions rather than blindly trusting any frontend-supplied `tenant_ids`.

### 3.1. BOLA and cache keys

```text
(acme, r1) -> Alice's report
(acme, r2) -> Carol's report
(beta, r1) -> Bob's report
```

A cache keyed solely by ID `r1` can return the wrong tenant's data. Cache keys must include at least **tenant + resource type + resource ID**; when output varies by user/ACL, also include actor and policy version, or cache isolated raw data and authorize afterward. Avoid `@Cacheable(key="#reportId")` on authorized responses in SaaS without reviewing tenant/actor isolation.

### 3.2. Forwarded headers and trusted proxies

`X-Forwarded-For` can be forged by clients to evade IP-based rate limits. `X-Forwarded-Host` can cause wrong routing/tenant/redirects if trusted blindly. Spring Cloud Gateway 4.3 WebFlux uses the `spring.cloud.gateway.server.webflux.*` namespace; Forwarded/X-Forwarded behavior is controlled via `trusted-proxies`. **Never** set `trusted-proxies: .*` to trust the entire Internet. Restrict to exact approved proxies, strip untrusted inbound headers, and verify every hop.

## 4. Gateway: HTTP Security and What It Cannot Do for the Domain

The Gateway is well suited for:

- Enforcing HTTPS and validating JWT Bearer tokens, issuer/audience/signature/timestamps.
- Early rejection of unpermitted methods/paths/scopes.
- Routing to fixed downstream URIs / trusted service discovery.
- Stripping untrusted identity headers, enforcing CORS and size limits.
- Rate limiting/quotas/WAF/DDoS protection, correlation IDs, and redacted access logs.

The Gateway **should not** store owner/ACL state for millions of reports inside edge filters. Record-by-record data decisions belong in the business service.

Example coarse rule:

```java
.authorizeExchange(ex -> ex
    .pathMatchers("/health").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/tenants/*/reports/*")
        .hasAuthority("SCOPE_reports.read")
    .anyExchange().denyAll())
```

The rule above neither inspects the tenant claim nor queries membership. If the backend simply configures `permitAll("/api/**")` because "the Gateway already checked," a direct call from a worker, internal mesh, SSRF, or misconfigured ingress bypasses all identity enforcement. Therefore the backend **independently authenticates the JWT** and applies domain policies, even when network controls/mTLS exist.

### 4.1. Header sanitation does not create permissions

In Gateway routes, use `RemoveRequestHeader=X-Tenant-Id`, `RemoveRequestHeader=X-User-Id`, and `RemoveRequestHeader=X-Roles`. The backend **never depends** on these headers; the verified JWT and domain store are the sources of truth. Never write:

```java
// WRONG: any caller can spoof this HTTP header.
String user = request.getHeaders().getFirst("X-User-Id");
String tenant = request.getHeaders().getFirst("X-Tenant-Id");
```

If the Gateway **must** forward user identity, use an internal mechanism with cryptographic integrity/delegation, strip untrusted client headers, and protect the Gateway→backend hop. A raw `X-Verified-User` string is not equivalent to a signed internal identity token.

### 4.2. TokenRelay does not mean forwarding Bearer

Spring Cloud Gateway provides OAuth2 `TokenRelay`, typically for OAuth2 Client/login session/authorized-client flows. This demo's Gateway is a **Resource Server receiving Bearer JWTs directly** and forwarding the same token to an API with a matching audience. `TokenRelay` does not need to be enabled here. If using a BFF/session, design OAuth2 Login, CSRF, cookies, authorized-client storage, token exchange, and downstream audiences for that model. **Never substitute an OIDC ID token for an access token** when calling a Resource Server.

## 5. Domain: Stateful Business Authorization

The Domain API must verify:

1. Verified JWT, `sub`, and `tenant_id`.
2. `{tenant}` in the URI matches the tenant claim.
3. The user still holds active membership in that tenant.
4. The object is queried by **tenant + report ID**, and owner/ACL permits the user.
5. Sharing/delegation/tenant roles/feature flags/record state per business rules.
6. The returned DTO contains only permitted fields.

Illustrative SQL:

```sql
SELECT r.tenant_id, r.id, r.title
FROM reports AS r
JOIN memberships AS m
  ON m.tenant_id = r.tenant_id
 AND m.subject_id = :subject
 AND m.active = TRUE
WHERE r.tenant_id = :tenant
  AND r.id = :report_id
  AND r.owner_sub = :subject;
```

Use R2DBC bind parameters, never SQL string concatenation; `subject` comes from verified identity, `tenant` from the route reconciled against trusted claim/membership. If reports can be shared, add a controlled ACL join; **never drop the owner check arbitrarily**.

### 5.1. 403 or 404?

- Missing/invalid JWT: **401** HTTP authentication.
- Valid JWT missing scope: **403** HTTP authorization.
- JWT tenant differs from path or missing membership: **403** per demo policy.
- Actor is a member, but the report belongs to someone else or does not exist: **404**, reducing object enumeration.
- Rate limit: **429**; infra/DB outage: **503/5xx**, never granting access implicitly.

An API may also choose 404 for unauthorized tenants to hide resource existence; enforce a consistent policy and tests, and never leak titles/owners in error bodies.

## 6. Infra: Defense, Not Business Authorization

| Control | Protects | Cannot Replace |
| --- | --- | --- |
| TLS/mTLS | Transport channel and workload credentials | User permissions on a report |
| NetworkPolicy | Blocks direct Internet access to API | Tenant membership |
| WAF/DDoS | Mitigates abuse, request-size limits | JWT issuer verification |
| Rate limiter | Tenant/IP/client quotas | Object ACLs |
| Circuit breaker/bulkhead | Isolates downstream failures | Domain state |
| Secrets/KMS/PKI | Key/cert/secret rotation | Tenant claim binding |
| Database RLS | Row filtering by tenant | Owner/ACL among users in the same tenant |
| Audit/tracing | Investigating events and behavior | Enforcement |

Rate limiting **before** authentication can use reliably determined IP/proxy data, whereas **post-authentication** per-tenant quotas use verified tenant/subject/client. Never trust raw XFF/`X-Tenant-Id` to grant higher quotas.

### 6.1. PostgreSQL RLS is an additional defense layer

```sql
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON reports
USING (tenant_id = current_setting('app.tenant_id', true));
```

This is an **illustrative snippet insufficient for production on its own**. Set `app.tenant_id` **after** authorization, scope it strictly to the transaction/connection (consider `SET LOCAL`), prevent tenant context leaks across pooled connections, use a DB user without `BYPASSRLS`, and test table owners/`FORCE RLS`. Filtering only by tenant still lets Alice read Carol's rows in the same tenant; owner/ACL remains needed in the domain layer.

### 6.2. Egress, service identity, and SSRF

Gateway route destinations must be governed by deployment config/trusted registries. **Never** take a target URI from `X-Backend-Url` or query params and proxy Bearer tokens—that risks SSRF and token exfiltration. For microservices, use mTLS/NetworkPolicy for Gateway→API and never leave API ports public. Gateway workload identity must never implicitly equate to user admin privileges.

## 7. Two Standalone Spring Boot Apps

We build:

```text
tenant-boundaries-demo/
├── gateway/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/gateway/
│       │   ├── GatewayApplication.java
│       │   ├── GatewaySecurity.java
│       │   └── GatewayHealthController.java
│       └── resources/application.yml
└── reports-api/
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/demo/reports/
        │   │   ├── ReportsApplication.java
        │   │   ├── ApiSecurity.java
        │   │   ├── ReportService.java
        │   │   └── ReportController.java
        │   └── resources/application.yml
        └── test/java/demo/reports/
            ├── ReportServiceTests.java
            └── ReportsHttpSecurityTests.java
```

Gateway runs on `localhost:8080`, backend on `localhost:8081`. Both validate Bearer JWTs with the **same issuer/audience**, while the backend verifies tenant/owner. IdP `id.example.test` in YAML is a **placeholder host**; tests use mock JWTs and do not contact an IdP. True end-to-end HTTP requires replacing the endpoints and supplying real JWTs from a sandbox. HTTP loopback is **for demo only**; production requires private transport/TLS/mTLS.

Boot `3.5.16` is compatible with Spring Cloud `2025.0.3`, though Spring Cloud 2025.0.x reached end of OSS support on 2026-06-30. For production in late 2026, choose a supported train (such as compatible Boot 4.x/Cloud 2025.1.x) with migration tests; do not mix Spring Cloud 2025.1 with Boot 3.5 arbitrarily.

## 8. Gateway Maven

### 8.1. gateway/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>tenant-gateway</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>2025.0.3</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Spring Cloud 2025.0.x renamed the WebFlux Gateway starter to **`spring-cloud-starter-gateway-server-webflux`**, replacing the deprecated `spring-cloud-starter-gateway`. Gateway Server WebFlux runs on Netty/Project Reactor, not Servlet WAR or MVC Gateway.

### 8.2. gateway/src/main/resources/application.yml

```yaml
server:
  port: 8080
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/demo
          jwk-set-uri: https://id.example.test/realms/demo/jwks
          audiences: reports-api
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: reports-api
              uri: http://127.0.0.1:8081
              predicates:
                - Path=/api/tenants/**
              filters:
                - RemoveRequestHeader=X-Tenant-Id
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Roles
                - RemoveRequestHeader=X-Authenticated-User
```

**Explanation:**

- `issuer-uri` and `jwk-set-uri` are operator-configured trusted sources used to verify JWT issuer + public keys. They must never come from untrusted JWT issuer URLs or user input.
- `audiences` requires JWTs issued for `reports-api`. Tokens with valid signatures yet the wrong audience are still rejected.
- `spring.cloud.gateway.server.webflux.routes` is the new prefix; do not mistakenly copy `spring.cloud.gateway.routes` from older examples.
- Destination URI is fixed; never accept an arbitrary backend URL from clients.
- `RemoveRequestHeader` prevents forwarding raw user/tenant/role headers. The backend must still ignore them even if this route is bypassed.
- Keep `Authorization` in the demo flow so the API verifies the Bearer token independently; never send credentials to unrelated origins.
- `TokenRelay` is not enabled because OAuth2 Client login/sessions are not used. Forwarding an incoming Bearer token and OAuth2 TokenRelay are distinct use cases.
- Do not enable `trusted-proxies: .*`; when proxies sit in front of the Gateway, configure a specific allowlist.

### 8.3. gateway/src/main/java/demo/gateway/GatewayApplication.java

```java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

### 8.4. gateway/src/main/java/demo/gateway/GatewaySecurity.java

```java
package demo.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurity {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/tenants/*/reports/*")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // Stateless Bearer-only API: does not use login session cookies.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

`hasAuthority("SCOPE_reports.read")` is only a route-level requirement. The Gateway verifies neither membership nor owner. `csrf.disable()` applies strictly to a pure client-sent Bearer-header API, **not by default** to browser BFF/session logins where automatic credentials introduce a different CSRF threat model.

### 8.5. gateway/src/main/java/demo/gateway/GatewayHealthController.java

```java
package demo.gateway;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GatewayHealthController {
    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("gateway OK");
    }
}
```

The public health endpoint falls outside the `Path=/api/tenants/**` Gateway route. Production needs proper liveness/readiness probes that never leak IdP/DB/secret details.

## 9. Reports API Maven and Independent JWT Security

### 9.1. reports-api/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>tenant-reports-api</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

### 9.2. reports-api/src/main/resources/application.yml

```yaml
server:
  port: 8081
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/demo
          jwk-set-uri: https://id.example.test/realms/demo/jwks
          audiences: reports-api
```

Reports API validates Bearer JWTs independently and never accepts self-declared identity headers from the Gateway or Internet. Real JWTs work only after replacing the placeholder IdP/JWKS with a trusted sandbox provider.

### 9.3. reports-api/src/main/java/demo/reports/ReportsApplication.java

```java
package demo.reports;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
```

### 9.4. reports-api/src/main/java/demo/reports/ApiSecurity.java

```java
package demo.reports;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/tenants/*/reports/*")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // Bearer API, does not use browser sessions in the demo.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Defense in depth:** The backend still checks JWT/scope if a direct call bypasses the Gateway; never configure `permitAll("/api/**")` merely because a Gateway sits in front.

## 10. Reports API Domain Service and Controller

### 10.1. reports-api/src/main/java/demo/reports/ReportService.java

```java
package demo.reports;

import java.util.Map;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public final class ReportService {

    public record ReportView(
        String tenant, String id, String title) {}

    private record StoredReport(
        String tenant, String id, String ownerSub, String title) {}

    // In-memory demo only; production uses R2DBC/directory,
    // checking tenant-aware identity and ACTIVE membership.
    private static final Map<String, Set<String>> MEMBERS = Map.of(
        "acme", Set.of("alice", "carol"),
        "beta", Set.of("bob")
    );

    // Report ID r1 collides across both tenants.
    private static final Map<String, StoredReport> REPORTS = Map.of(
        "acme|r1", new StoredReport(
            "acme", "r1", "alice", "Acme quarterly report"),
        "acme|r2", new StoredReport(
            "acme", "r2", "carol", "Carol private report"),
        "beta|r1", new StoredReport(
            "beta", "r1", "bob", "Beta quarterly report")
    );

    public Mono<ReportView> read(
            String pathTenant, String reportId, Jwt verifiedJwt) {

        return Mono.defer(() -> {
            String tokenTenant =
                verifiedJwt.getClaimAsString("tenant_id");
            if (tokenTenant == null ||
                    !pathTenant.equals(tokenTenant)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Tenant claim mismatch"));
            }

            String subject = verifiedJwt.getSubject();
            if (subject == null || subject.isBlank() ||
                    !MEMBERS.getOrDefault(
                        pathTenant, Set.of()).contains(subject)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "No active membership"));
            }

            StoredReport report =
                REPORTS.get(pathTenant + "|" + reportId);
            if (report == null ||
                    !pathTenant.equals(report.tenant()) ||
                    !subject.equals(report.ownerSub())) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
            }

            return Mono.just(new ReportView(
                report.tenant(), report.id(), report.title()));
        });
    }
}
```

**Key explanations:**

1. `verifiedJwt` comes from Spring Security `@AuthenticationPrincipal Jwt` after signature verification at runtime. Unit tests use fixtures without altering the production trust boundary.
2. Compare `pathTenant` with the trusted `tenant_id` from the JWT. Any `X-Tenant-Id` header is completely ignored.
3. Verify membership against an authoritative store. A JWT tenant claim can be stale if a user was revoked from the organization.
4. Look up the report by **tenant+report ID**, then verify owner. Never fetch or cache by ID alone.
5. If the record does not exist or the actor is not the owner, return 404 per domain policy without leaking the record title.
6. `Mono.defer` defers logic to reactive subscription; with R2DBC, use `flatMap`/bound SQL params, never `.block()`.
7. Static `MEMBERS`/`REPORTS` are illustrative only; production needs roles/ACLs, issuer-qualified `sub`, tenant membership status, cache invalidation, and auditing.

### 10.2. reports-api/src/main/java/demo/reports/ReportController.java

```java
package demo.reports;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("api OK");
    }

    @GetMapping("/api/tenants/{tenant}/reports/{reportId}")
    public Mono<ReportService.ReportView> report(
            @PathVariable String tenant,
            @PathVariable String reportId,
            @AuthenticationPrincipal Jwt principal) {
        return service.read(tenant, reportId, principal);
    }
}
```

The controller never reads `?user=` or `X-User-Id` to construct identity. `Jwt` is the authenticated principal placed in Reactor Context by the Spring WebFlux Resource Server filter. The controller returns a minimal DTO rather than dumping raw JWTs or full DB records.

## 11. Unit Tests: Domain Policy via StepVerifier

### 11.1. reports-api/src/test/java/demo/reports/ReportServiceTests.java

```java
package demo.reports;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.server.ResponseStatusException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportServiceTests {

    private final ReportService service = new ReportService();

    private static Jwt jwt(String subject, String tenant) {
        // JWT Java fixture: not a real signed token.
        return Jwt.withTokenValue("unit-test-token")
            .header("alg", "none")
            .subject(subject)
            .claim("tenant_id", tenant)
            .build();
    }

    private void fails(
            String tenant, String id, Jwt jwt, HttpStatus status) {
        StepVerifier.create(service.read(tenant, id, jwt))
            .expectErrorMatches(error ->
                error instanceof ResponseStatusException ex &&
                ex.getStatusCode() == status)
            .verify();
    }

    @Test
    void aliceReadsOwnAcmeReport() {
        StepVerifier.create(
                service.read("acme", "r1", jwt("alice", "acme")))
            .assertNext(view -> {
                assertEquals("acme", view.tenant());
                assertEquals("r1", view.id());
                assertEquals("Acme quarterly report", view.title());
            })
            .verifyComplete();
    }

    @Test
    void bobReadsBetaReportWithSameId() {
        StepVerifier.create(
                service.read("beta", "r1", jwt("bob", "beta")))
            .assertNext(view ->
                assertEquals("Beta quarterly report", view.title()))
            .verifyComplete();
    }

    @Test
    void tenantMismatchIsForbidden() {
        fails("beta", "r1", jwt("alice", "acme"),
            HttpStatus.FORBIDDEN);
    }

    @Test
    void unknownMemberIsForbidden() {
        fails("acme", "r1", jwt("eve", "acme"),
            HttpStatus.FORBIDDEN);
    }

    @Test
    void aliceCannotReadCarolReport() {
        fails("acme", "r2", jwt("alice", "acme"),
            HttpStatus.NOT_FOUND);
    }

    @Test
    void unknownReportIsNotFound() {
        fails("acme", "missing", jwt("alice", "acme"),
            HttpStatus.NOT_FOUND);
    }

    @Test
    void tenantClaimAloneDoesNotCreateMembership() {
        fails("beta", "r1", jwt("alice", "beta"),
            HttpStatus.FORBIDDEN);
    }

    @Test
    void missingTenantClaimIsForbidden() {
        Jwt missing = Jwt.withTokenValue("unit-test-token")
            .header("alg", "none")
            .subject("alice")
            .build();
        fails("acme", "r1", missing, HttpStatus.FORBIDDEN);
    }
}
```

There are **8 `@Test` methods**. Two identical report IDs in Acme and Beta expose a common bug class: queries or caches keyed solely by report ID. `alg=none` is only a header on the **Jwt Java object fixture**, never passing through a decoder. It is **not** a policy allowing the Resource Server to accept unsigned JWTs; production JWT decoders must verify signatures and allowed algorithms.

## 12. HTTP Tests: WebTestClient Scope + Tenant + Owner

### 12.1. reports-api/src/test/java/demo/reports/ReportsHttpSecurityTests.java

```java
package demo.reports;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReportsHttpSecurityTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient as(
            String subject, String tenant, String authority) {
        return client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .subject(subject)
                .claim("tenant_id", tenant))
            .authorities(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api OK");
    }

    @Test
    void withoutBearerIs401() {
        client.get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void aliceScopeTenantAndOwnerAllowRead() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("acme")
            .jsonPath("$.id").isEqualTo("r1")
            .jsonPath("$.title").isEqualTo("Acme quarterly report");
    }

    @Test
    void bobBetaGetsDifferentDataWithSameReportId() {
        as("bob", "beta", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("beta")
            .jsonPath("$.title").isEqualTo("Beta quarterly report");
    }

    @Test
    void missingReadScopeIs403() {
        as("alice", "acme", "SCOPE_profile.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void jwtTenantDifferentFromPathIs403() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void forgedTenantHeaderCannotOverrideJwt() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .header("X-Tenant-Id", "beta")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void forgedUserHeaderCannotActAsBob() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .header("X-User-Id", "bob")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownMembershipIs403() {
        as("eve", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void sameTenantOtherOwnerGets404() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/r2")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void absentReportGets404() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/missing")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void forgedRoleHeaderCannotReplaceScope() {
        as("alice", "acme", "SCOPE_profile.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .header("X-Roles", "ROLE_ADMIN")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void basicAuthCannotReplaceJwt() {
        client.get().uri("/api/tenants/acme/reports/r1")
            .headers(h -> h.setBasicAuth("alice", "secret"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownPathIsDefaultDenied() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/internal")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postMethodIsDefaultDenied() {
        as("alice", "acme", "SCOPE_reports.read")
            .post().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tokenWithoutTenantClaimIs403() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports.read")))
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

There are **16 `WebTestClient` tests**; the Reports API project has **24 tests** in total. `mockJwt()` creates a synthetic authenticated principal and therefore **bypasses JWT signature/JWKS/issuer/time validation**. It verifies URL security, `SCOPE_`, and business authorization, **not** real signature verification. Gateway routes/TLS/RLS are also untested in this suite.

To test cryptographic JWTs, write signed-token tests using `NimbusJwtEncoder`/`NimbusReactiveJwtDecoder` or a sandbox IdP/JWKS; to test real proxying, run Gateway+mock downstream integration tests.

## 13. Running Maven and Sample Requests

Two independent projects from the `tenant-boundaries-demo` directory:

```bash
cd reports-api
mvn clean test
cd ../gateway
mvn clean test
```

With compatible dependencies and environment, `reports-api` is **expected** to pass 24 tests. Gateway has no dedicated test class yet; `mvn test` checks the Maven lifecycle and compilation. **Maven was not executed on these tests when authoring this Knowledge lesson**; outcomes are code-based expectations only. Inspect Surefire logs and dependency trees on errors rather than claiming empirical completion.

Start API (Terminal 1):

```bash
cd reports-api
mvn spring-boot:run
```

Start Gateway (Terminal 2):

```bash
cd gateway
mvn spring-boot:run
```

Verify public health and missing tokens:

```bash
curl -i http://localhost:8081/health
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/tenants/acme/reports/r1
curl -i http://localhost:8081/api/tenants/acme/reports/r1
```

Expect `/health` to return HTTP 200 with body `api OK` or `gateway OK`, and protected routes without Bearer to return 401 on both.

### 13.1. Sending a real JWT through the Gateway

YAML uses `https://id.example.test/realms/demo` and `/jwks`, which **are illustrative addresses** with no live IdP there. To run end-to-end:

1. Configure a sandbox Authorization Server issuing JWT access tokens with matching issuer/audience/JWKS.
2. Update `issuer-uri`/`jwk-set-uri` in **both Gateway and API**.
3. Issue a JWT with `sub=alice`, `tenant_id=acme`, scope `reports.read`, `aud` containing `reports-api`, valid timestamps, and a valid JWS signature.
4. Call the Gateway:

```bash
# Use only a real sandbox access token issued by the AS.
curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/tenants/acme/reports/r1
```

When all conditions pass, the API is expected to return:

```json
{"tenant":"acme","id":"r1","title":"Acme quarterly report"}
```

Try changing the path to `/api/tenants/beta/reports/r1` with the **same Alice Acme token**: the Gateway may pass it through because the coarse scope matches, but the domain service must return **403**. That is the exact boundary of this lesson.

**Never use demo-style HTTP loopback in production.** Use TLS/mTLS/private networking and never commit tokens/secrets into repos or tickets. Tokens in command lines/shell histories can leak; use sandbox environments only and revoke tokens appropriately.

## 14. When Multiple Tenants or Multiple Issuers Exist

### 14.1. One user belonging to multiple tenants

Options:

| Token Model | Tenant Context | What to Verify |
| --- | --- | --- |
| Single-active-tenant token | `tenant_id` in verified JWT | Path match + DB membership |
| Multi-tenant list token | Verified `tenant_ids` | User picks candidate + active membership |
| Tenantless token | Verified subject + directory | Policy lookup per request |
| M2M client credentials | Verified service ID + tenant grants | Service does not implicitly access all tenants |
| One issuer per tenant | Trusted issuer registry | Per-issuer audience/key/tenant mapping |

The demo uses a single active tenant for simplicity. In a list model, never rely on `list.contains(tenant)` alone because memberships can be revoked. When implementing tenant switching, require an explicit authorized selection/token-issuance workflow and UI, never trusting an arbitrary `X-Tenant-Id`.

### 14.2. JwtIssuerReactiveAuthenticationManagerResolver

Reactive Spring Security supports multi-issuer setups:

```java
// @Configuration snippet, not a standalone class in the demo.
JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-acme.example.test",
        "https://idp-beta.example.test");

http.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver));
```

Imported from `org.springframework.security.oauth2.server.resource.authentication`. `fromTrustedIssuers` uses a **trusted allowlist**. Unverified JWT `iss` is used only to pick among approved issuers, **never** to build decoders or fetch JWKS from arbitrary token-supplied or query-param URLs.

Pay attention to per-issuer **audience** and token-profile validators, plus domain-level tenant/member authorization. The resolver does not automatically know resource owners or guarantee business API audiences. Dynamic tenant onboarding must follow a reviewed/approved trust registry.

### 14.3. Opaque tokens

If the AS issues opaque tokens, the API uses `ReactiveOpaqueTokenIntrospector`/RFC 7662 introspection instead of a JWT decoder. A different token format does not erase boundaries: HTTP authentication still comes first, and the domain must determine membership and object permissions after token verification.

## 15. When Permissions Move Outside an HTTP Request

- `POST/PATCH/DELETE`: enforce tenant membership, owner/ACL, and method-specific permissions directly in the service.
- Search/pagination/export: filter entire datasets and counts by tenant; never leak aggregates.
- Cache: key by tenant/resource and actor/ACL context when responses are personalized.
- Cron/scheduler/queues: no inbound `ServerWebExchange`; use a verified service identity or integrity-protected delegation context.
- Events: a tenant ID in an unauthenticated producer's payload is untrusted; protect message provenance.
- SSE/WebSocket: enforce subscription/channel tenant authorization, not only the handshake.
- Object storage/presigned URLs: verify tenant/owner/access/expiry before issuing URLs.

If policy lives only in the Gateway, execution paths bypassing the Gateway **lose authorization**. The business service is where durable domain decisions are enforced.

## 16. Operating When a Component Fails

| Failure | Safe Behavior | Never Do |
| --- | --- | --- |
| JWKS/AS unreachable, JWT unverified | Deny / return appropriate error; fail closed | Skip signature |
| Wrong JWT audience | 401 | Accept because scope matched |
| Membership DB outage | Grant no access; return 5xx/503 per policy | Default user to member |
| Redis rate limiter down | Apply reviewed fail-open/fail-closed policy per endpoint | Disable all authorization |
| User revoked | Invalidate authz cache / reduce TTL | Keep `ROLE_ADMIN` indefinitely |
| API public ingress accidentally exposed | Backend JWT/domain checks still enforce; fix network | Trust `X-User-Id` |
| Caller-controlled Gateway route target | Reject, audit | Proxy token to arbitrary host |
| Invalid DB RLS context | No rows / deny | Use superuser bypassing RLS |
| Cross-tenant cache collision | Stop/evict/audit exposure | Keep using id-only keys |

Fail-open on an **availability control** (such as certain rate limits) never permits **business authorization to fail open**. Quotas, privacy, and tenant isolation each require separate runbooks and failure-injection tests.

## 17. Logging and Auditing

Logs should differ between the Gateway (route/status/latency/trace) and the domain (actor, tenant, resource, decision). Example safe schema:

```json
{
  "requestId": "req-314",
  "layer": "domain",
  "route": "reports-api",
  "actorAlias": "hashed-actor",
  "tenantAlias": "hashed-tenant",
  "resourceType": "report",
  "decision": "DENY",
  "reasonCategory": "OBJECT_NOT_OWNED",
  "httpStatus": 404
}
```

This is an **illustrative schema**, not an emitted log. Never log raw Bearer JWTs, refresh tokens, secrets, key material, or sensitive report bodies. Avoid unbounded user/tenant/report IDs as metric labels (cardinality/PII). A correlation ID is not identity; a caller-supplied `X-Request-Id` grants zero privileges.

## 18. Mandatory Negative Tests Before Production

1. Real signed JWTs: wrong key/issuer/audience/exp/nbf/alg, and ID tokens not accepted as access tokens.
2. Gateway routes: method allowlists, header sanitation, no open proxy, tokens never sent to unrelated hosts.
3. Domain: wrong tenant path, missing membership, same-tenant non-owner, colliding IDs across tenants.
4. DB RLS: missing tenant predicate still denied; pooled connections leak no context; DB role lacks `BYPASSRLS`.
5. Network/mTLS: direct backend blocked from Internet; compromised services still cannot bypass JWT domain policies.
6. Caching: tenant-qualified keys; membership/role revocation triggers invalidation.
7. Concurrency: two tenants sharing a report ID, parallel requests never mixing Reactor Context.
8. Failure injection: JWKS/IdP/DB/Redis outages, timeouts, 401/403/404/429/503, and no unsafe fallbacks.
9. Exports, searches, bulk updates, queues, WebSocket channels, and admin routes all have BOLA coverage.

`mockJwt()` tests verify **domain policy** but do not verify actual JWT signature validation; add crypto/JWKS/IdP integration tests before production. Never report everything as PASS merely because `WebTestClient` `mockJwt` passes.

## 19. Self-Check Questions

**1. Once the Gateway verifies the JWT and scope, can the API skip object ACLs?** No, JWT scopes do not encode per-report permissions.

**2. Why not trust client-sent `X-Tenant-Id`?** Headers are untrusted and easily spoofed/altered to switch tenants.

**3. When two tenants share ID `r1`, is caching by ID alone safe?** No, it risks cross-tenant data leakage.

**4. What happens if an Acme-tenant token calls a Beta-tenant URL?** Rejected with 403 in the demo regardless of any headers sent by the caller.

**5. What if a JWT is unexpired yet the user lost membership?** The domain must deny based on current state, never assuming an unexpired token suffices.

**6. Is a NetworkPolicy allowing only the Gateway to call the API enough?** No, it does not enforce user/report permissions.

**7. `401` vs. `403`?** 401 when authentication is missing/invalid; 403 when authenticated yet lacking permissions, CSRF, or another policy check.

**8. Why return 404 when Alice tries to access Carol's report?** To hide object existence and prevent record enumeration.

**9. What should per-tenant rate limiting rely on?** Verified identity/tenant, never raw headers.

**10. Is `trusted-proxies: .*` safe?** No, trusting all forwarded sources enables IP/host spoofing.

**11. Does tenant-only RLS stop users in the same tenant from viewing each other's data?** No, owner/ACL checks are still required.

**12. Does `mockJwt()` verify RSA signatures?** No, it bypasses the decoder.

**13. Why do both the Gateway and API verify the JWT?** Defense in depth and preventing direct calls from bypassing the Gateway.

**14. Is `TokenRelay` needed for every incoming Bearer JWT?** No, TokenRelay is primarily for OAuth2 Client authorized-token flows.

**15. Can CORS replace object authorization?** No, CORS is a browser cross-origin policy.

**16. Can a cron job preserve request authentication via a static variable?** No; use a service identity/delegation mechanism with integrity.

**17. Can decoders be instantiated dynamically for any `iss` in a token?** No, use only a trusted issuer allowlist.

**18. If the membership DB fails, should access default to allowed to preserve uptime?** No, fail closed.

## 20. Deployment Checklist

- [ ] Gateway and backend verify JWT signature, iss/aud/time, and scopes per the trust model.
- [ ] HTTP path/method allowlists, default deny, no arbitrary downstream URIs.
- [ ] Header spoofing blocked; backend never trusts `X-Tenant`/`X-User`/`X-Roles`.
- [ ] Forwarded/trusted proxy config uses an allowlist, never wildcard trust.
- [ ] URL tenant candidate matched against verified tenant and active membership.
- [ ] Object owner/ACL checked in the domain service, not solely in gateway filters.
- [ ] SQL/R2DBC queries bind tenant+actor parameters; no id-only cache keys.
- [ ] RLS/DB roles/connection pooling tested independently, no `BYPASSRLS`.
- [ ] mTLS/NetworkPolicy/private backend ingress, secrets management, and rotation.
- [ ] Rate limits/quotas keyed by verified tenant, never trusting spoofed XFF.
- [ ] 401/403/404/429/503 policies enforced; errors never leak private data.
- [ ] CSRF/CORS/BFF/TokenRelay designed properly when browser sessions exist.
- [ ] Async jobs, events, exports, search, and SSE/WebSockets also enforce tenant authorization.
- [ ] Multi-issuer: trust registry, per-issuer audience, tenant mapping.
- [ ] Negative tests cover cross-tenant/same-tenant non-owner, spoofed headers, and wrong scopes.
- [ ] Real JWT, Gateway proxy, RLS, and network integration tests run before production.
- [ ] Domain-level auditing of actor/tenant/resource/outcome with tokens/PII redacted.
- [ ] Production Boot/Cloud versions are supported and the regression suite is complete.

## 21. Conclusion and Official Sources

**One-sentence takeaway:** The Gateway decides who enters an **HTTP endpoint group**; the domain decides what the user may do with a **real tenant and resource**; infrastructure governs **network paths, isolation, and resource limits**. No layer replaces another.

```text
HTTP security:      verified JWT + route/method/scope policy
Business policy:    verified identity + tenant membership + object ACL
Infrastructure:     trusted networks + mTLS + RLS + quotas + secrets
```

With only a Gateway, SQL missing a tenant predicate or cache keys missing a tenant will still leak data. With only tenant RLS, users inside the same tenant can still read each other's data. With only mTLS, service identity does not prove end-user rights. **Safe multi-tenancy requires all three boundaries and negative tests.**

**References:**

- Spring Security 6.5 – Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 – WebTestClient OAuth2 mockJwt: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security – Reactive Multi-tenancy: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- Spring Security 6.5 – JwtIssuerReactiveAuthenticationManagerResolver API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html
- Spring Cloud Gateway 4.3 – WebFlux starter: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html
- Spring Cloud Gateway – HttpHeadersFilters/trusted proxies: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html
- Spring Cloud Gateway – RemoveRequestHeader: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html
- Spring Cloud 2025.0 release notes (starter/prefix migration): https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes
- Spring Cloud 2025.0.3 release/support: https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/
- Spring Cloud supported versions: https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions
- OWASP API Security Top 10 – Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- RFC 6750 – OAuth2 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 – JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 – JWT Profile for OAuth2 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
