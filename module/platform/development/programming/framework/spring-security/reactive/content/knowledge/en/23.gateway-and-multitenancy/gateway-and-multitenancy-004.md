# Resolving Tenants from Trusted Sources and Separating Tenants from Unverified Data — Spring Security WebFlux

## Objectives

This lesson belongs to **Spring Security – reactive**, parent topic **Gateway and Multi-tenancy**. After this lesson, you will be able to:

1. Distinguish **requested tenant** supplied by the client, **verified tenant** derived from an authenticated identity, and **resource tenant** stored on a data record.
2. Classify the trustworthiness of Host, path, query params, cookies, HTTP headers, JWT claims before/after signature verification, opaque token introspection, and a server-side tenant registry.
3. Understand why an unverified `iss` may only be used to select an **allowlisted** verifier and must never become a tenant authority or arbitrary JWKS URL.
4. Configure multi-issuer support with `JwtIssuerReactiveAuthenticationManagerResolver`, `JwtReactiveAuthenticationManager`, `NimbusReactiveJwtDecoder`, and `iss`, `aud`, `exp`, `nbf` validators.
5. After Bearer authentication, reconcile issuer→tenant with the verified `tenant_id` claim, the tenant requested in the URL, and scope permissions.
6. Prevent spoofing of `X-Tenant-ID`, `X-Verified-Tenant`, and `X-Forwarded-Host`; never treat internal headers as proof unless downstream authenticates the gateway workload.
7. Build a sample Java 17+ / Spring Boot 3.5.16 WebFlux gateway with a fixed downstream `WebClient`, and test it using RS256 JWTs, two separate JWKS endpoints, `MockWebServer`, and `WebTestClient`.
8. Apply tenant-aware queries/ACLs, issuer+subject identity namespaces, mTLS, signed internal assertions, logging, caching, SSO sessions, and opaque introspection.

> **Scope:** the demo is a **WebFlux Resource Server acting as an HTTP-protecting gateway**; it does not use the Spring Cloud Gateway starter. Section 12 explains how to apply these principles to actual Spring Cloud Gateway. The demo uses keys and HTTP servers on loopback **for testing only**, not as a production infrastructure design.

---

## 1. Three Types of Tenants Never to Conflate

Suppose a client sends:

```http
GET /api/tenants/alpha/documents/invoice-42 HTTP/1.1
Host: alpha.example.test
X-Tenant-ID: alpha
X-Verified-Tenant: alpha
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

When the request first arrives, all of these inputs can be controlled by the client:

- `alpha` in the URL is merely the **requested tenant**, describing the resource the client wants to access.
- `Host`/subdomain may handle routing at the edge; it does not prove the user belongs to tenant alpha.
- `X-Tenant-ID` and `X-Verified-Tenant` are just HTTP header strings. The word "Verified" carries no cryptographic proof.
- The Bearer token may be a JWT, but a decoded payload is **not yet verified**.
- A database record having `tenant_id=alpha` is only the **resource tenant**, not verification of caller permissions.

Only after Spring Security verifies the Bearer token—validating issuer, audience, signature, and timestamps—and the application verifies membership/tenant policy do we have a **verified tenant**.

```text
                         UNSIGNED REQUEST DATA
                         ---------------------
Client: Host/path/X-Tenant-ID/JWT bytes
                |
                v
Ingress: TLS, hostname allowlist, strip forged headers
                |
                v
Spring Security Reactive Resource Server
  - JWT issuer hint -> ONLY pick verifier from allowlist
  - signature / iss / aud / exp / nbf validation
  - scope -> SCOPE_... authority
                |
                v
VERIFIED Authentication (Jwt principal)
                |
                v
Tenant policy
  - issuer -> ops-approved tenant
  - signed tenant_id claim matches registry?
  - requested tenant == verified tenant?
  - caller permitted for this resource?
                |
                v
Trusted downstream / tenant-scoped database
                |
                v
HTTP 200 / 401 / 403 / 404
```

**Separate error semantics:**

- **401:** missing or unverifiable JWT, bad signature, untrusted issuer, wrong audience, expired token.
- **403:** authenticated token, but missing scope or tenant claim/path tenant mismatch against permissions.
- **404:** document does not exist, or the system intentionally hides the existence of unauthorized resources; requires a consistent policy.

## 2. Classifying Sources of Trust

| Information Source | Before Verification | What Can It Be Used For? |
| --- | --- | --- |
| `/tenants/alpha` | Untrusted selector | Indicates the tenant requested by the client; must be checked against permissions |
| `?tenant=alpha` / JSON body | Client input | Business validation; does not determine identity |
| `X-Tenant-ID` / `X-Verified-Tenant` | Untrusted header | Strip/overwrite at trust boundary; never directly grant privileges |
| `Host` / subdomain | Request-controlled | Routing hint after host allowlist, not proof of membership |
| `Forwarded`/`X-Forwarded-*` | Untrusted from Internet | Use only if sanitized by a trusted proxy |
| Unverified JWT `iss` claim | Untrusted hint | Look up an allowlisted verifier |
| Unverified JWT `tenant_id` claim | Untrusted payload | Never use as identity/cache/access predicate |
| `Jwt` from verified Authentication | Passed signature and validators | Check claims under IdP contract and tenant entitlement |
| Opaque introspection result from trusted IdP | Confirmed active | Apply issuer/audience/tenant policy before granting access |
| Ops-managed issuer→tenant registry | Server-owned config | Map trusted issuer/JWKS/tenant |
| Tenant ID in DB row | Resource attribute | Compare against verified tenant in query |
| Internal header set by gateway | **Conditionally** trusted | B must authenticate the gateway's workload/origin |

**Two layers are required:** the gateway checks identity/tenant/scope, and the backend or database still checks the record's tenant and owner/ACL permissions. Omitting either can cause cross-tenant data leaks.

## 3. An Unverified JWT Does Not Prove a Tenant

Example JWT payload:

```json
{
  "iss": "https://issuer.example.invalid/alpha",
  "sub": "alice",
  "aud": ["api://tenant-gateway"],
  "tenant_id": "alpha",
  "scope": "docs.read",
  "exp": 1893456000
}
```

Anyone can craft a JWT string containing these claims. The Base64URL payload is unprotected until the JWS signature is verified against **the right public key of a trusted issuer**.

### Correct order in a multi-issuer Resource Server

1. Read unverified `iss` **solely to look up a verifier configuration** in an allowlist.
2. Unapproved issuer → fail closed; never fetch discovery/JWKS from arbitrary hosts.
3. The matching verifier checks the signature, exact `iss`, API `aud`, `nbf`, and `exp`.
4. Only then is Authentication created; code may read `@AuthenticationPrincipal Jwt`.
5. Map the verified issuer and verified tenant claims to tenant policy.
6. Match the tenant requested in the URL/host against verified membership.
7. Verify scope, record/owner permissions, and propagation boundaries.

Spring Security 6.5 provides the API:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                        "https://idp.example.test/alpha",
                        "https://idp.example.test/beta");
```

This technique uses an allowlist as the trust boundary. **Do not mistakenly believe that reading `iss` and picking a verifier means authentication succeeded.** If the signing key does not match or the token has the wrong audience, it must still be rejected.

### Anti-pattern: creating a decoder from an attacker-supplied issuer

```java
// Do NOT do this: unverified raw iss can point to an attacker's server.
String issuer = parseUnverifiedJwt(token).get("iss");
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(issuer);
```

This is an **anti-pattern fragment**; no `parseUnverifiedJwt(...)` helper exists to run it. Fetching metadata from an arbitrary issuer lets an attacker exploit SSRF or host their own issuer/JWKS and be mistakenly trusted by the server. Conversely, picking a `ReactiveAuthenticationManager` from an immutable admin-approved map does not turn a raw claim into authority.

### When one IdP represents multiple tenants

A one-issuer-equals-one-tenant rule does not always hold. Some IdPs issue tokens for many organizations/tenants under the same issuer. In that case:

- Use shared signature + issuer + audience validators.
- Read verified `tenant_id` or organization memberships from Authentication.
- Verify that the tenant ID exists in the registry and the caller has an entitlement to the requested tenant.
- A user belonging to multiple tenants needs an active-tenant selection mechanism that is **re-authorized**.
- Never let a client inject a tenant into a token/session/registry via a request.

The lab uses **two issuers, one tenant per issuer** to make both boundaries clear.

## 4. What Is a Trusted Registry?

An operations-managed server-side tenant registry:

| Tenant | Canonical issuer | JWKS URL |
| --- | --- | --- |
| alpha | `https://issuer.example.invalid/alpha` | Approved JWKS config for alpha |
| beta | `https://issuer.example.invalid/beta` | Approved JWKS config for beta |

The registry must never dynamically add issuers based on Host, `X-Issuer`, token claims, or a tenant appearing in a path. If dynamic onboarding is supported, it requires an authenticated control plane, approval, validation of the issuer domain/JWKS, and auditing.

In multi-issuer systems, subject IDs can collide. Two tokens with `sub=alice` from alpha and beta are not necessarily the same user. Logical identity keys should include `issuer + subject`; tenant-permission tokens/caches typically need `issuer + tenant + subject + scope/policy version`.

```text
Identity key:      (issuer, subject)
Data key:          (tenant_id, document_id)
Cache permission:  (issuer, tenant_id, subject, resource, policy_version)
```

Never cache profiles/documents solely by `sub` or `documentId` if multiple tenants share the namespace.

## 5. Host, Path, and Proxy Headers Remain Request Selectors

### Path-based tenant

```http
GET /api/tenants/beta/documents/doc1
Authorization: Bearer <verified-token-for-alpha>
```

The client requests a document belonging to beta. If the verified JWT belongs only to alpha, the result must be rejected—never "auto-switch tenants" just because the path says beta.

### Spoofed headers

```http
X-Tenant-ID: beta
X-Verified-Tenant: beta
X-Forwarded-Host: beta.example.invalid
```

These headers carry no proof of membership. Any client can write them. Even if the gateway sees a Host in an allowed domain, Host identifies only the **requested** endpoint; membership must come from Authentication.

### Reverse proxy

When TLS terminates at a reverse proxy, `Forwarded`/`X-Forwarded-*` can help the application reconstruct the external URI. However, the proxy must strip untrusted client headers and rewrite them from the real connection; a trusted-proxy policy **does not automatically establish a trusted tenant policy**.

### SSO session/cookie

A cookie `active_tenant=beta` is not enough. Switching tenants must check the authenticated user's membership/roles before storing the active tenant in the server session. If the session expires or membership is revoked, re-evaluate it. Never treat a query param or cookie as proof of login.

## 6. Tenant at the Data Layer: Preventing IDOR

The gateway may already have verified:

```text
verified issuer = alpha
verified tenant = alpha
scope = docs.read
requested tenant = alpha
```

Yet user Alice may still not be permitted to view Bob's document within tenant alpha.

Never query by `docId` alone:

```java
// ANTI-PATTERN: missing tenant/ownership predicate.
return documentRepository.findById(docId);
```

Better intent example with R2DBC:

```java
// Fragment; documentRepository belongs to the actual business application.
return documentRepository
        .findByTenantIdAndDocumentId(verifiedTenantId, docId)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

If documents require owner/ACL checks, the query should include the owner condition or an appropriate ACL join. Never use a `tenant_id` taken directly from a header. When using PostgreSQL RLS, manage the tenant context strictly across the transaction/connection lifecycle to avoid leaking context across requests when connection pools are reused.

**The gateway does not replace permission checks in the data service**, especially when the backend can be invoked by jobs, event consumers, or another gateway.

---

## 7. Standalone Spring Boot WebFlux Project

This project simulates a WebFlux gateway protecting tenant routes and calling downstream via WebClient. The Spring Cloud Gateway routing engine is **not** part of this project; Section 12 provides a fragment for Spring Cloud Gateway.

Key practices demonstrated:

- Two pre-configured issuers: alpha/beta.
- Two separate JWT verifiers, each with its own JWKS URI and issuer validator.
- Gateway audience is `api://tenant-gateway`; required scope is `docs.read`.
- Tenant policy produces `VerifiedTenant` only after the JWT is authenticated and the tenant/path match.
- Downstream receives `X-Verified-Tenant`/`X-Verified-Subject` from the gateway **in loopback tests**; raw inbound headers are never copied.
- WebClient uses a fixed path, does not follow redirects, and never accepts arbitrary outbound URLs.

### 7.1. File Structure

```text
trusted-tenant-gateway/
  settings.gradle
  build.gradle
  src/main/java/example/tenantgateway/
    TenantGatewayApplication.java
    TrustedTenantCatalog.java
    TenantSecurityConfiguration.java
    TenantAccessPolicy.java
    TrustedDownstreamClient.java
    TenantGatewayController.java
  src/main/resources/
    application.yml
  src/test/java/example/tenantgateway/
    TenantGatewayIntegrationTest.java
```

### 7.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'trusted-tenant-gateway'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

JDK 17+ and a compatible Gradle Wrapper are required. Spring Security JOSE/JWT classes come from the Resource Server starter dependencies. Do not add the MVC starter when you want pure Reactor Netty/WebFlux.

Spring Boot 3.5.16 is the **final OSS release of the 3.5 branch** and has reached end of OSS support; production deployments should select a supported release line with current security patches.

### 7.3. application.yml

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080

security:
  tenants:
    alpha:
      issuer: https://issuer.example.invalid/alpha
      jwk-set-uri: https://issuer.example.invalid/alpha/jwks
    beta:
      issuer: https://issuer.example.invalid/beta
      jwk-set-uri: https://issuer.example.invalid/beta/jwks

downstream:
  base-url: ${DOWNSTREAM_BASE_URL:https://profiles.example.invalid}
  allow-insecure-loopback-for-tests: false
```

The `security.tenants.*` namespace is **custom app config** defined here, not a built-in Boot Resource Server property. The `.invalid` addresses do not work outside tests; tests override JWKS/downstream with local MockWebServers via `@DynamicPropertySource`.

In production, replace issuer/JWKS with real IdPs, HTTPS/TLS certificate verification, egress rules, and a JWKS rotation policy. `allow-insecure-loopback-for-tests` is strictly a switch for localhost tests—never enable it in Internet-facing environments.

### 7.4. Main class

**`src/main/java/example/tenantgateway/TenantGatewayApplication.java`:**

```java
package example.tenantgateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantGatewayApplication.class, args);
    }
}
```

### 7.5. TrustedTenantCatalog

**`src/main/java/example/tenantgateway/TrustedTenantCatalog.java`:**

```java
package example.tenantgateway;

import java.util.Collection;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class TrustedTenantCatalog {

    public record TenantSpec(
            String tenantId,
            String issuer,
            String jwkSetUri) {}

    private final Map<String, TenantSpec> byIssuer;

    public TrustedTenantCatalog(
            @Value("${security.tenants.alpha.issuer}") String alphaIssuer,
            @Value("${security.tenants.alpha.jwk-set-uri}") String alphaJwks,
            @Value("${security.tenants.beta.issuer}") String betaIssuer,
            @Value("${security.tenants.beta.jwk-set-uri}") String betaJwks) {

        if (alphaIssuer.isBlank() || betaIssuer.isBlank()
                || Objects.equals(alphaIssuer, betaIssuer)) {
            throw new IllegalArgumentException(
                    "Trusted issuer identifiers must be distinct");
        }

        byIssuer = Map.of(
                alphaIssuer, new TenantSpec(
                        "alpha", alphaIssuer, alphaJwks),
                betaIssuer, new TenantSpec(
                        "beta", betaIssuer, betaJwks));
    }

    public Collection<TenantSpec> trustedEntries() {
        return byIssuer.values();
    }

    public TenantSpec findByVerifiedIssuer(String issuer) {
        return byIssuer.get(issuer);
    }
}
```

The registry is populated from server config, **never adding tenants/issuers per request**. When a single IdP serves multiple tenants, implement a membership model instead of a 1:1 map. In the demo, the method name `findByVerifiedIssuer` intentionally reminds callers to extract the issuer **after** the decoder has verified the JWT.

### 7.6. TenantSecurityConfiguration

**`src/main/java/example/tenantgateway/TenantSecurityConfiguration.java`:**

```java
package example.tenantgateway;

import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class TenantSecurityConfiguration {

    private static final String REQUIRED_AUDIENCE =
            "api://tenant-gateway";

    @Bean
    JwtIssuerReactiveAuthenticationManagerResolver tenantIssuerResolver(
            TrustedTenantCatalog catalog) {

        Map<String, ReactiveAuthenticationManager> managers =
                new HashMap<>();

        for (TrustedTenantCatalog.TenantSpec spec
                : catalog.trustedEntries()) {

            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder
                            .withJwkSetUri(spec.jwkSetUri())
                            .build();

            OAuth2TokenValidator<Jwt> issuerAndTime =
                    JwtValidators.createDefaultWithIssuer(spec.issuer());

            OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                    jwt.getAudience() != null
                            && jwt.getAudience().contains(REQUIRED_AUDIENCE)
                            ? OAuth2TokenValidatorResult.success()
                            : OAuth2TokenValidatorResult.failure(
                                    new OAuth2Error("invalid_token",
                                            "Invalid gateway audience", null));

            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            issuerAndTime, audienceValidator));

            managers.put(
                    spec.issuer(),
                    new JwtReactiveAuthenticationManager(decoder));
        }

        // Look up only managers approved in ops config.
        Map<String, ReactiveAuthenticationManager> approved =
                Map.copyOf(managers);

        return new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(approved.get(issuer)));
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            JwtIssuerReactiveAuthenticationManagerResolver resolver) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/tenants/*/documents/*")
                            .hasAuthority("SCOPE_docs.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationManagerResolver(resolver))
                .build();
    }
}
```

The classes and packages use the exact reactive Spring Security 6.5 APIs:

- `org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver` looks up `iss` from the Bearer token to pick a manager.
- `org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager` performs authentication using a `ReactiveJwtDecoder`.
- `NimbusReactiveJwtDecoder.withJwkSetUri` fetches keys from the **configured JWKS URL**, never downloading metadata from an arbitrary raw issuer.
- `JwtValidators.createDefaultWithIssuer` validates `iss` and timestamps; the audience validator ensures the token is actually meant for the gateway.
- `hasAuthority("SCOPE_docs.read")` enforces scope beyond authentication.
- Tokens whose issuer is not in the map never instantiate a new verifier. This is the crucial distinction between an **untrusted routing hint** and a **trusted security policy**.
- A single `SecurityWebFilterChain` covers the demo routes; if a system has multiple chains, verify the policy in every chain.

**Do not create another global `ReactiveJwtDecoder` bean for the demo** because there are two issuers, each with its own decoder and validators. When using `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` against real IdPs, managers can be initialized lazily via discovery; in this lab, JWKS URIs are pinned so tests run without a real IdP.

### 7.7. TenantAccessPolicy

**`src/main/java/example/tenantgateway/TenantAccessPolicy.java`:**

```java
package example.tenantgateway;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class TenantAccessPolicy {

    public record VerifiedTenant(
            String tenantId,
            String issuer,
            String subject) {}

    private final TrustedTenantCatalog catalog;

    public TenantAccessPolicy(TrustedTenantCatalog catalog) {
        this.catalog = catalog;
    }

    public Mono<VerifiedTenant> requireTenant(
            Jwt verifiedJwt, String requestedTenant) {

        return Mono.defer(() -> {
            if (verifiedJwt == null || verifiedJwt.getIssuer() == null) {
                return deny();
            }

            // Called only after authentication in SecurityWebFilterChain.
            String issuer = verifiedJwt.getIssuer().toString();
            TrustedTenantCatalog.TenantSpec trusted =
                    catalog.findByVerifiedIssuer(issuer);

            String signedTenant =
                    verifiedJwt.getClaimAsString("tenant_id");
            String subject = verifiedJwt.getSubject();

            if (trusted == null
                    || signedTenant == null
                    || !trusted.tenantId().equals(signedTenant)
                    || !trusted.tenantId().equals(requestedTenant)
                    || subject == null || subject.isBlank()) {
                return deny();
            }

            return Mono.just(new VerifiedTenant(
                    trusted.tenantId(), issuer, subject));
        });
    }

    private static Mono<VerifiedTenant> deny() {
        return Mono.error(
                new AccessDeniedException("Tenant access denied"));
    }
}
```

Here `requestedTenant` is **only a value to compare against**, never copied directly into the result. `VerifiedTenant` is constructed only when the JWT has been authenticated by Security, the issuer is trusted by the registry, and both the `tenant_id` claim and path match.

Scenarios:

- Alpha token requesting beta URL → 403.
- Token from issuer alpha with claim `tenant_id=beta` even with a valid signature → 403 because it violates the lab's 1:1 contract.
- JWT missing `tenant_id` or `sub` → 403.
- Token from an unknown issuer → 401, never reaches this policy.
- Token with matching tenant but scope `docs.write` instead of `docs.read` → 403 at HTTP security.

In complex multi-issuer/multi-tenant apps, tenant entitlements may come from an authorization service, but they must be trusted data evaluated against principal/tenant—never client-supplied headers.

### 7.8. TrustedDownstreamClient

**`src/main/java/example/tenantgateway/TrustedDownstreamClient.java`:**

```java
package example.tenantgateway;

import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

@Service
public final class TrustedDownstreamClient {

    private final WebClient webClient;

    public TrustedDownstreamClient(
            @Value("${downstream.base-url}") String rawBaseUrl,
            @Value("${downstream.allow-insecure-loopback-for-tests:false}")
                    boolean allowTestHttp) {

        URI base = URI.create(rawBaseUrl);
        boolean https = "https".equalsIgnoreCase(base.getScheme());
        boolean httpLoopbackForTest = allowTestHttp
                && "http".equalsIgnoreCase(base.getScheme())
                && "127.0.0.1".equals(base.getHost());

        if (!(https || httpLoopbackForTest)
                || base.getHost() == null
                || base.getRawUserInfo() != null
                || base.getRawQuery() != null
                || base.getRawFragment() != null
                || !(base.getRawPath() == null
                    || base.getRawPath().isEmpty()
                    || "/".equals(base.getRawPath()))) {
            throw new IllegalArgumentException(
                    "Downstream base URL is not permitted");
        }

        HttpClient httpClient = HttpClient.create()
                .followRedirect(false)
                .responseTimeout(Duration.ofSeconds(5));

        webClient = WebClient.builder()
                .baseUrl(base.toString())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }

    public Mono<String> document(
            TenantAccessPolicy.VerifiedTenant tenant, String docId) {

        if (docId == null || !docId.matches("[A-Za-z0-9_-]{1,40}")) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid document id"));
        }

        return webClient.get()
                .uri("/internal/docs/{id}", docId)
                .headers(headers -> {
                    // Do not copy raw inbound headers from the caller.
                    headers.set("X-Verified-Tenant", tenant.tenantId());
                    headers.set("X-Verified-Subject", tenant.subject());
                })
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(String.class)
                                .switchIfEmpty(Mono.error(
                                        new ResponseStatusException(
                                                HttpStatus.BAD_GATEWAY,
                                                "Empty downstream response")));
                    }
                    return response.releaseBody()
                            .then(Mono.error(
                                    new ResponseStatusException(
                                            HttpStatus.BAD_GATEWAY,
                                            "Downstream rejected request")));
                })
                .onErrorMap(WebClientRequestException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Downstream unavailable"));
    }
}
```

**Analysis:**

1. `downstream.base-url` is **ops-owned configuration**, never a URL taken from an HTTP request. Normally requires HTTPS; HTTP is allowed only for loopback when the test flag is enabled.
2. `.uri("/internal/docs/{id}", docId)` fixes the path and validates the doc ID; a WebClient with a base URL **does not** automatically stop other code from passing an absolute URI.
3. Internal headers are set exclusively from `VerifiedTenant`; inbound `X-Tenant-ID`/`X-Verified-Tenant` are never copied.
4. `followRedirect(false)` stops the client from following a Location to another host; non-2xx statuses are mapped safely without echoing sensitive body headers.
5. **Downstream B must authenticate gateway A** via mTLS/workload identity or a signed internal token; an `X-Verified-Tenant` header over an open network is insecure.
6. The demo **does not relay the original access token**. If B needs end-user authority, use a valid Bearer token with B's audience, token exchange (RFC 8693), or signed internal delegation.
7. Production also needs egress firewall/service mesh and DNS policies; application-level scheme/host checks alone do not fully prevent SSRF/rebinding.
8. Never call `.block()` or `.subscribe()` on the event loop; return the publisher so Reactor manages its lifecycle.

### 7.9. TenantGatewayController

**`src/main/java/example/tenantgateway/TenantGatewayController.java`:**

```java
package example.tenantgateway;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public final class TenantGatewayController {

    private final TenantAccessPolicy policy;
    private final TrustedDownstreamClient downstream;

    public TenantGatewayController(
            TenantAccessPolicy policy,
            TrustedDownstreamClient downstream) {
        this.policy = policy;
        this.downstream = downstream;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/tenants/{tenantId}/documents/{docId}")
    public Mono<String> document(
            @PathVariable String tenantId,
            @PathVariable String docId,
            @AuthenticationPrincipal Jwt verifiedJwt) {

        return policy.requireTenant(verifiedJwt, tenantId)
                .flatMap(tenant -> downstream.document(tenant, docId));
    }
}
```

Spring Security validates the JWT and checks scope before the controller runs. There is no endpoint allowing a caller to supply `issuer`, `jwk-set-uri`, or `downstream URL`. Downstream receives only the verified context emitted by the policy.

---

## 8. Integration Test with Two Issuers and Separate JWKS

The test generates alpha/beta RSA key pairs in memory and serves **public JWKS** via a MockWebServer. A second MockWebServer simulates downstream; another capture server detects whether redirects are followed.

**`src/test/java/example/tenantgateway/TenantGatewayIntegrationTest.java`:**

```java
package example.tenantgateway;

import java.io.IOException;
import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TenantGatewayIntegrationTest {

    private static final String ISSUER_ALPHA =
            "https://issuer.example.invalid/alpha";
    private static final String ISSUER_BETA =
            "https://issuer.example.invalid/beta";
    private static final String AUDIENCE =
            "api://tenant-gateway";

    private static final RSAKey KEY_ALPHA = generate("key-alpha");
    private static final RSAKey KEY_BETA = generate("key-beta");

    private static final MockWebServer CAPTURE = startCapture();
    private static final MockWebServer DOWNSTREAM = startDownstream();
    private static final MockWebServer JWKS = startJwks();

    @DynamicPropertySource
    static void overrideTrustedEndpoints(DynamicPropertyRegistry registry) {
        registry.add("security.tenants.alpha.issuer",
                () -> ISSUER_ALPHA);
        registry.add("security.tenants.beta.issuer",
                () -> ISSUER_BETA);
        registry.add("security.tenants.alpha.jwk-set-uri",
                () -> JWKS.url("/jwks/alpha").toString());
        registry.add("security.tenants.beta.jwk-set-uri",
                () -> JWKS.url("/jwks/beta").toString());
        registry.add("downstream.base-url",
                () -> DOWNSTREAM.url("/").toString());
        registry.add("downstream.allow-insecure-loopback-for-tests",
                () -> "true");
    }

    @LocalServerPort
    int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() throws InterruptedException {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
        while (DOWNSTREAM.takeRequest(0, TimeUnit.MILLISECONDS) != null) {
            // Drain the recorded-request queue from earlier tests.
        }
    }

    @AfterAll
    static void shutdown() throws IOException {
        JWKS.shutdown();
        DOWNSTREAM.shutdown();
        CAPTURE.shutdown();
    }

    private static RSAKey generate(String kid) {
        try {
            return new RSAKeyGenerator(2048)
                    .keyID(kid).generate();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static MockWebServer startCapture() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startJwks() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                RSAKey publicKey;
                if ("/jwks/alpha".equals(request.getPath())) {
                    publicKey = KEY_ALPHA.toPublicJWK();
                } else if ("/jwks/beta".equals(request.getPath())) {
                    publicKey = KEY_BETA.toPublicJWK();
                } else {
                    return new MockResponse().setResponseCode(404);
                }

                return new MockResponse()
                        .setResponseCode(200)
                        .setHeader("Content-Type", "application/json")
                        .setBody(new JWKSet(publicKey).toString());
            }
        });
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startDownstream() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                String path = request.getPath();

                if ("/internal/docs/redirect".equals(path)) {
                    return new MockResponse()
                            .setResponseCode(302)
                            .setHeader("Location",
                                    CAPTURE.url("/capture").toString());
                }

                if (path != null
                        && path.startsWith("/internal/docs/")) {
                    return new MockResponse()
                            .setResponseCode(200)
                            .setHeader("Content-Type", "text/plain")
                            .setBody("tenant="
                                    + request.getHeader("X-Verified-Tenant")
                                    + ";subject="
                                    + request.getHeader("X-Verified-Subject")
                                    + ";path=" + path);
                }

                return new MockResponse().setResponseCode(404);
            }
        });
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String signJwt(
            RSAKey key, String issuer, String subject,
            String tenantId, String audience, String scope,
            boolean expired) {
        try {
            Instant now = Instant.now();
            Instant start = expired
                    ? now.minusSeconds(3600) : now.minusSeconds(30);
            Instant end = expired
                    ? now.minusSeconds(600) : now.plusSeconds(600);

            JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
                    .issuer(issuer)
                    .subject(subject)
                    .audience(audience)
                    .issueTime(Date.from(start.minusSeconds(10)))
                    .notBeforeTime(Date.from(start))
                    .expirationTime(Date.from(end))
                    .claim("scope", scope);

            if (tenantId != null) {
                claims.claim("tenant_id", tenantId);
            }

            SignedJWT jwt = new SignedJWT(
                    new JWSHeader.Builder(JWSAlgorithm.RS256)
                            .type(JOSEObjectType.JWT)
                            .keyID(key.getKeyID())
                            .build(),
                    claims.build());
            jwt.sign(new RSASSASigner(key));
            return jwt.serialize();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String alphaToken() {
        return signJwt(KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.read", false);
    }

    private static String betaToken() {
        return signJwt(KEY_BETA, ISSUER_BETA, "bob",
                "beta", AUDIENCE, "docs.read", false);
    }

    @Test
    void publicPingWorks() {
        client.get().uri("/public/ping")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingBearerReturns401() {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void alphaTokenReadsOnlyAlpha() throws InterruptedException {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("tenant=alpha;subject=alice;path=/internal/docs/doc1");

        RecordedRequest r = DOWNSTREAM.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(r);
        assertEquals("alpha", r.getHeader("X-Verified-Tenant"));
        assertEquals("alice", r.getHeader("X-Verified-Subject"));
    }

    @Test
    void betaTokenReadsOnlyBeta() {
        client.get().uri("/api/tenants/beta/documents/doc1")
                .headers(h -> h.setBearerAuth(betaToken()))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("tenant=beta;subject=bob;path=/internal/docs/doc1");
    }

    @Test
    void alphaCannotRequestBetaPath() {
        int before = DOWNSTREAM.getRequestCount();
        client.get().uri("/api/tenants/beta/documents/doc1")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isForbidden();
        assertEquals(before, DOWNSTREAM.getRequestCount());
    }

    @Test
    void betaCannotRequestAlphaPath() {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(betaToken()))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void spoofedHeadersDoNotChangeVerifiedTenant()
            throws InterruptedException {
        client.get().uri("/api/tenants/alpha/documents/doc2")
                .header("X-Tenant-ID", "beta")
                .header("X-Verified-Tenant", "beta")
                .header("X-Verified-Subject", "mallory")
                .header("X-Forwarded-Host", "beta.example.invalid")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("tenant=alpha;subject=alice;path=/internal/docs/doc2");

        RecordedRequest r = DOWNSTREAM.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(r);
        assertEquals("alpha", r.getHeader("X-Verified-Tenant"));
        assertEquals("alice", r.getHeader("X-Verified-Subject"));
        assertNull(r.getHeader("X-Tenant-ID"));
    }

    @Test
    void conflictingSignedTenantClaimReturns403() {
        String token = signJwt(KEY_ALPHA, ISSUER_ALPHA, "alice",
                "beta", AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void missingTenantClaimReturns403() {
        String token = signJwt(KEY_ALPHA, ISSUER_ALPHA, "alice",
                null, AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void unknownIssuerCannotSelectArbitraryVerifier() {
        String token = signJwt(
                KEY_ALPHA, "https://attacker.example.invalid", "alice",
                "alpha", AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void alphaIssuerWithBetaSignatureReturns401() {
        String token = signJwt(
                KEY_BETA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceReturns401() {
        String token = signJwt(
                KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", "api://billing", "docs.read", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingReadScopeReturns403() {
        String token = signJwt(
                KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.write", false);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void expiredTokenReturns401() {
        String token = signJwt(
                KEY_ALPHA, ISSUER_ALPHA, "alice",
                "alpha", AUDIENCE, "docs.read", true);
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .headers(h -> h.setBearerAuth(token))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unknownRequestedTenantReturns403() {
        client.get().uri("/api/tenants/gamma/documents/doc1")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void forgedHeaderWithoutJwtStillReturns401() {
        client.get().uri("/api/tenants/alpha/documents/doc1")
                .header("X-Verified-Tenant", "alpha")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void downstreamRedirectIsNotFollowed() {
        int before = CAPTURE.getRequestCount();

        client.get().uri("/api/tenants/alpha/documents/redirect")
                .headers(h -> h.setBearerAuth(alphaToken()))
                .exchange().expectStatus().isEqualTo(502);

        assertEquals(before, CAPTURE.getRequestCount());
    }
}
```

### 8.1. Running the Tests

From the directory containing the Gradle Wrapper:

```bash
./gradlew test --tests example.tenantgateway.TenantGatewayIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.tenantgateway.TenantGatewayIntegrationTest
```

Or a compatible preinstalled Gradle:

```bash
gradle test --tests example.tenantgateway.TenantGatewayIntegrationTest
```

**Expected:** 17 tests PASS if the project, JDK 17+, Maven dependencies, and loopback binding work properly. This is an **expected result from static review of the source**, not an actual compile/test run log in the workspace. If JUnit parallel execution is enabled, isolate MockWebServers or synchronize request-count assertions; this test suite is designed to run sequentially.

### 8.2. Security Properties Verified

| Category | What Is Proved |
| --- | --- |
| Public vs protected | Missing token on protected route returns 401 |
| Valid Alpha/Beta | Each issuer uses its own JWKS and matching tenant |
| Alpha on beta path / beta on alpha path | Valid JWT does not allow accessing another tenant |
| Fake X-Tenant-ID/X-Verified-* | Caller headers are not promoted to trusted identity |
| Missing/conflicting tenant_id claim | Signed token must still satisfy tenant policy |
| Unknown issuer | Never fetches arbitrary JWKS/issuers |
| Signed with another key | Cannot spoof issuer alpha with key beta |
| Wrong aud | JWT not intended for the gateway is rejected |
| Wrong scope | Valid token lacking docs.read returns 403 |
| Expired | Timestamp validation rejects it |
| Tenant gamma | URL path does not dynamically add tenants to the registry |
| Fake header without Bearer | Never fabricates Authentication |
| Redirect | Does not follow Location to capture server |

### 8.3. Testing Limitations

- Tests do not call a real IdP; JWKS is served by a loopback HTTP mock, and private signing keys exist only in tests.
- The mock downstream **does not** verify mTLS or a signed internal assertion; it only inspects headers to prove the gateway does not forward forged headers.
- Tests do not connect to a DB/RLS and therefore do not verify real record-level ACLs.
- Tests do not cover JWKS rotation/caching/timeouts or single-issuer multi-tenant entitlements.
- Staging TLS/ingress tests are required before production, specifically to ensure **the backend cannot be reached directly** bypassing the gateway.

---

## 9. Propagating Tenant Downstream Across a Trust Boundary

The gateway may want to forward:

```http
X-Verified-Tenant: alpha
X-Verified-Subject: alice
```

**These two headers alone are never standalone proof.** If B is exposed over public HTTP and trusts a header string, any client can claim to be alpha/alice.

For B to be allowed to trust metadata created by A, you need:

1. B accepts connections only from A/approved gateways via network policy.
2. Authenticate A's **workload identity** via mTLS, SPIFFE/SPIRE, or a service JWT/signed internal assertion with `aud=B`.
3. At the edge, strip/normalize privileged headers that a client could send.
4. A sets the verified tenant only after authentication and tenant entitlement checks.
5. B still checks resource tenant, membership/roles, and owner/ACL—not just a header.
6. Apply defense-in-depth: short TTL, auditing, and revocation when permissions change.

In multi-trust-domain environments, consider **RFC 8693 OAuth2 Token Exchange** or a short-lived signed internal JWT with B's audience, narrowed scopes, and verified tenant and subject. This requires deliberate design and does not happen automatically by adding `X-Verified-Tenant`.

### Opaque tokens

If the inbound token is an opaque access token rather than a JWT, use `ReactiveOpaqueTokenIntrospector` against a **trusted** IdP endpoint to verify `active=true` and obtain an `OAuth2AuthenticatedPrincipal`.

You cannot parse `iss` directly from an opaque string. A routing hint from host/path may only select an **allowlisted introspection provider**; the introspection response must still validate issuer/resource/audience/tenant per contract and match the requested tenant.

Never send tokens or introspection client secrets to a caller-supplied URL.

### API key / mTLS / SSO session

The same principle applies:

- API key: after hashing/looking up a valid server-side key, map key→tenant and permissions.
- mTLS: verify the certificate chain/CA, then map the verified subject/SPIFFE ID→tenant.
- OIDC session: use the authenticated principal + server-side tenant memberships.
- User "switch tenant": require authorization before updating the active tenant in the session.
- Machine workload: use a dedicated service identity and tenant entitlement rather than borrowing a default user token/tenant.

---

## 10. Protecting Tenant Data and Caches

### Tenant-aware database query

Even when the gateway resolves verified tenant alpha, the data service must still query by `tenant_id`. Example:

```sql
SELECT document_id, content
FROM documents
WHERE tenant_id = :verifiedTenant
  AND document_id = :documentId
  AND owner_subject = :verifiedSubject;
```

Bind parameters; never concatenate SQL. If ACLs are required instead of a single owner, use appropriate joins/row-level predicates. When using an R2DBC pool or PostgreSQL RLS, scope the tenant context to the transaction and properly reset connection/session settings.

### Cache isolation

Wrong:

```text
cacheKey = "doc:" + documentId
```

Better per policy:

```text
cacheKey = tenantId + ":" + documentId + ":" + authorizationScope
```

If a cached response depends on owner or permission groups, include the verified identity/policy version or avoid shared caching. Never use a client-header tenant ID as an authorization cache key.

### Audit and observability

Log events with verified issuer, tenant, subject (per privacy policy), resource ID, decision, correlation ID, and error category; **never log raw JWTs, Authorization headers, token secrets, or sensitive document contents**.

For cross-tenant access attempts, alert on 403 metrics without emitting unnecessary PII in logs. When the tenant registry changes, version/audit the mapping and update policy caches.

## 11. Common Pitfalls

| Scenario | Cause | Resolution |
| --- | --- | --- |
| Alpha token reads beta document | Path/header trusted as Authentication | Compare verified tenant against requested tenant |
| Forged X-Verified-Tenant trusted by backend | Public backend without workload auth | Network isolation + mTLS/signed assertion |
| Unknown-issuer JWT accepted | Arbitrary issuer/JWKS discovery | Issuer allowlist and pinned verifiers |
| Correct tenant ID but invalid signature passes | Parsing claims before verification | Validate token before policy |
| Beta JWKS verifies alpha issuer | Keys/issuers not isolated | Separate decoders, exact issuer validators |
| Valid JWT signature, tenant claim mismatches registry | Only checking signature | Explicit trusted issuer→tenant check |
| Token without tenant claim defaults to a tenant | Fail-open fallback | Missing tenant => deny |
| Wrong-audience JWT accepted | Omitting audience validation | Validate gateway aud |
| Insufficient token scope | Missing authorization | Check SCOPE_docs.read |
| Host beta treated as beta entitlement | Host is a routing hint, not membership | Host allowlist and token tenant policy |
| Forged Forwarded-Host | Proxy failed to strip headers | Trusted proxy metadata normalization |
| Alpha/beta users share subject in cache | Missing issuer namespace | Cache key issuer+tenant+sub |
| Downstream queries only docId | Missing tenant predicate | Tenant-scoped query + ACL |
| Shared multi-tenant IdP hardcoded 1:1 | Wrong data model | Signed membership/tenant entitlement |
| 401 confused with 403 | Authentication and authorization conflated | Separate failure layers clearly |
| 302 to another host followed | Uncontrolled outbound redirects | Disable redirects and allowlist |
| Opaque token decoded as JWT | Wrong token strategy | Introspection server |
| API key ID trusted before lookup | Key spoofing | Hash/verify against server-owned store |
| Session active tenant changed via cookie | Missing membership check | Reauthorize tenant switch |
| JWT logged | Credential leakage | Mask Authorization and payload |
| Public HTTP JWKS URL | MITM swaps public key | HTTPS + certificate validation |
| RLS tenant variable persists on pooled connection | Cross-tenant connection state | Transaction-bound context/reset |
| mockJwt tests pass despite broken verifier | Mock skips signature | RSA/JWKS integration tests |
| IdP/JWKS downtime falls back to permitAll | Fail open | Never grant access when verification fails |

## 12. Spring Cloud Gateway: Stripping Headers Before Forwarding

Spring Cloud Gateway WebFlux provides route predicates, `GatewayFilter`/`GlobalFilter`, and `RemoveRequestHeader`. When actually using the Gateway starter, configure filters to strip caller-sent privileged headers:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: tenant-documents
              uri: https://documents.internal.example.test
              predicates:
                - Path=/api/tenants/{tenantId}/documents/**
              filters:
                - RemoveRequestHeader=X-Verified-Tenant
                - RemoveRequestHeader=X-Verified-Subject
                - RemoveRequestHeader=X-Tenant-ID
```

**This fragment only strips headers when forwarding**; it does not authenticate JWTs or grant tenant entitlements. Do not paste this configuration into the runnable project in Section 7 because that project does not use Spring Cloud Gateway. The `{tenantId}` route variable is also client input, not a verified identity. Custom filters/handlers may emit an internal tenant identity **only after** Security and tenant policy succeed; verify filter ordering and never use `AddRequestHeader=X-Verified-Tenant,{tenantId}` to grant permissions.

Trusted proxy config on the Gateway helps interpret Host/IP/scheme metadata from proxies; **it does not prove the user belongs to the tenant indicated by Host**. With multiple proxies, the edge must strip client `Forwarded`/`X-Forwarded-*` headers and recreate them from the real connection alongside a host allowlist.

## 13. Production Checklist

1. Distinguish requested tenant, verified tenant, and resource tenant.
2. Never grant access from raw Host/path/header/query/cookie/unverified JWT payloads.
3. Issuer/JWKS URLs are allowlisted from server admin config, never from JWTs/users.
4. Verify JWT signature, issuer, audience, exp, nbf; check scopes and tenant claims.
5. Namespace every issuer/principal; never treat subject as globally unique.
6. If one issuer serves multiple tenants, enforce verified membership entitlements.
7. Always compare the requested tenant selector against the verified tenant.
8. Never assign a default tenant when claims are absent or verification fails.
9. Both route/HTTP and service/data-layer authorization are active.
10. DB queries include tenant and owner/ACL predicates; RLS/pool lifecycle is safe.
11. Backend is not public and enforces mTLS/signed internal identity.
12. Strip inbound privileged headers; never copy raw headers downstream.
13. Outbound URLs come from trusted config, fixed paths, no auto-redirect, HTTPS/egress restrictions.
14. Opaque tokens use trusted introspection; never parse arbitrary JWT-like strings.
15. SSO tenant switching verifies membership; session cookies do not grant permissions on their own.
16. Cache keys isolate issuer/tenant/subject/resource with revocation-appropriate TTLs.
17. Never log Bearer tokens, JWKS private keys, credentials, or raw PII.
18. Negative tests: wrong issuer/signature/aud, missing scope, tenant mismatch, spoofed headers, expired token.
19. Review tenant onboarding/rotation/deletion in the control plane and audit mappings.
20. Test staging with real TLS/proxy/mTLS; never treat a mock downstream as authentication proof.

## 14. Exercises

1. Run the alpha token/alpha path test and explain why the beta path returns 403.
2. Spoof `X-Verified-Tenant: beta` with an alpha token; why does downstream still receive alpha?
3. Send a JWT with a raw attacker `iss` and self-signed key: why does the map not instantiate a new manager?
4. Swap the signature to the beta key with the alpha issuer and analyze the 401.
5. Try a validly signed JWT with `tenant_id=beta` from issuer alpha: which policy blocks it?
6. Remove the audience validator on an experimental branch and observe the risk of tokens from another API.
7. Remove `SCOPE_docs.read` from the JWT and verify 403 before downstream is called.
8. Add a PostgreSQL R2DBC query scoped by tenant/owner and verify colliding docIds do not leak.
9. With `sub=alice` on two issuers, define a cache key that prevents identity mixing.
10. Replace the 1:1 mapping with a single multi-tenant issuer using verified org memberships.
11. Design admin tenant onboarding with approval/auditing and trusted JWKS rotation.
12. Add an opaque introspection flow comparing the tenant attribute and route path after the active check.
13. Test session-login active tenant switching: verify membership before updating.
14. Place a real Resource Server B behind the gateway; try calling B directly with fake internal headers.
15. Replace header propagation with a short-lived signed internal token having `aud=B`.
16. Place the edge behind a CDN/proxy and verify fake Host/X-Forwarded-Host headers cannot escalate privileges.
17. Emit metrics for cross-tenant denies without logging raw JWTs.
18. Design 404 behavior that hides resource existence without enabling enumeration.

## Summary

**No header, path, or unverified JWT claim establishes a tenant on its own.** The gateway can use untrusted selectors for routing or an issuer hint to pick an **allowlisted verifier**, but only after Spring Security validates the JWT and the application checks tenant entitlements can the data become a verified tenant context.

In WebFlux, `JwtIssuerReactiveAuthenticationManagerResolver` picks a manager by issuer; `JwtReactiveAuthenticationManager` and `NimbusReactiveJwtDecoder` verify signature/issuer/audience/timestamps. `TenantAccessPolicy` reconciles the verified issuer/claim with the requested tenant. The backend must still protect data per tenant and trust gateway metadata **only over an authenticated channel**.

**Multi-tenant security is a chain of controls from ingress to data storage**, not `tenant_id = request.header("X-Tenant-ID")`.

## Official References

- [Spring Security 6.5 — Reactive OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security 6.5 — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [JwtIssuerReactiveAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [JwtReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html)
- [NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Cloud Gateway 4.3 — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html)
- [Spring Cloud Gateway — RemoveRequestHeader Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth2 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [OWASP — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP — SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
