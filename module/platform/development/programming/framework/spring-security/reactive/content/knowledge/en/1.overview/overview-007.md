# Trust Boundaries and Attack Surface of a Reactive Application

> **Context:** Spring Boot 3.3, Spring WebFlux, Spring Security 6, Java 17+. This lesson focuses on how to identify where data or permissions cross a trust boundary and where attacks can target a reactive application. Non-blocking programming helps handle I/O efficiently; it **does not automatically** guarantee authentication, authorization, data security, or overload protection.

## 1. Three Concepts to Distinguish

- **Asset:** user data, orders, tokens, session cookies, identity information, secret configurations, administrative APIs, infrastructure, and CPU/memory/connection resources.
- **Trust boundary:** a point where data, identity, or permissions move from a zone with one level of assurance to another. Examples: external HTTP requests from the Internet entering an API; claims inside a third-party JWT entering authorization decisions; a resource ID from a URL being used to query internal data.
- **Attack surface:** entry points that an untrusted actor can control or influence: URLs, query parameters, bodies, headers, WebSockets, login endpoints, file uploads, callbacks, WebClient, queues, public configurations, logs, and operational endpoints.

**Principle:** receiving a value does not mean that value is trustworthy; authenticating an identity does not imply permission to access every resource.

Typical flow diagram:

```text
Client (browser, mobile, another service)        [untrusted]
       |
       | HTTPS: path, headers, cookie/token, body
       v
CDN / Load balancer / Reverse proxy              [boundary 1]
       |
       | request + controlled forwarded headers
       v
Spring WebFlux: ServerWebExchange, WebFilter     [boundary 2]
       |
       v
Spring Security: SecurityWebFilterChain
       | authentication -> SecurityContext -> permission check
       v
Handler -> Service (Mono/Flux)                    [boundary 3]
       |          |               |
       |          |               +--> WebClient / external API [boundary 5]
       |          +--> DB, cache, object storage              [boundary 4]
       +--> broker, WebSocket, logs, metrics                  [boundary 6]
```

The boxes in the diagram represent **zones that require independent trust evaluation**, not that every connection between two boxes is safe merely because it sits inside an internal network.

## 2. Critical Boundaries

| Crossing point | Common data | Core risks | Required controls |
|---|---|---|---|
| Client → proxy/ingress | URL, Host, Origin, X-Forwarded-*, body, cookies | Spoofed source headers, unencrypted HTTP, malformed requests | HTTPS, trusted proxy policy, request limits, header filtering |
| Proxy → WebFlux app | Scheme, IP address, route, forwarded headers | App trusting client-declared IP/host | Accept forwarded headers only from trusted proxies; strip spoofed headers from the Internet |
| Request → Spring Security | Session/cookie, Authorization bearer | Wrong issuer/audience token, expired token, missing auth | SecurityWebFilterChain, signature/token verification, session policy |
| Principal → business logic | Roles, scopes, tenant, resource ID | Authenticated user reading/modifying another user's objects (BOLA/IDOR) | Server-side authorization **per resource** and per tenant |
| Service → DB/cache | Queries, cache keys, multi-tenant data | Injection, missing tenant predicate, cross-tenant cache leaks | Parameterized queries, tenant constraints, data authorization |
| Service → WebClient/IdP/other APIs | URLs, credentials, bearer tokens, JSON | SSRF, leaking tokens to wrong targets, trusting external responses | Destination allowlists, TLS checks, propagate credentials only by policy |
| HTTP → WebSocket/broker/background job | Handshake session, messages, events | Trusting post-handshake messages, skipping recipient checks | Connection auth, per-action/per-message authorization, event verification |
| App → logs/metrics/Actuator | URLs, errors, request metadata, secrets | Leaking tokens/PII, exposing operational features | Mask sensitive data, restrict endpoints, authorize observability access |

A boundary can recur multiple times: a request that passes authentication at a gateway must still undergo authorization at the service that actually owns the data.

## 3. What Is Specific to WebFlux and Reactor?

### 3.1 Security filter chain

WebFlux receives requests via **ServerWebExchange**; **WebFilter**s process requests and responses. Spring Security uses **SecurityWebFilterChain** to configure authentication and access rules for reactive applications. Path policies are the first line of defense, while business logic must still verify resource permissions.

Rules prone to mistakes:

- `permitAll()` means allowing access under that rule; never place it on `/admin/**` by mistake.
- `authenticated()` only requires a valid identity; it does not prove the caller owns `orderId` or belongs to the required `tenantId`.
- Conditions are evaluated according to matcher configuration; understand the order and scope of each `pathMatchers(...)`.
- Unlisted endpoints should have a strict default policy (`denyAll()` for undeclared paths, or requiring authentication by design).
- WebSockets, Actuator, proxy routes, static resources, and HTTP methods may each require distinct policies.

### 3.2 SecurityContext in reactive streams

In traditional servlet applications, code often relies on `ThreadLocal`. With Reactor, a request can switch threads across asynchronous steps. Spring Security reactive attaches the security context to the **Reactor Context** of the subscription stream; when needed inside a reactive chain, use mechanisms such as `ReactiveSecurityContextHolder.getContext()` or the principal provided by WebFlux.

Practical consequences:

1. Never treat a thread name or a custom `ThreadLocal` as user identity.
2. Switching schedulers via Reactor operators **does not automatically lose Context**; risks typically appear when calling `subscribe()` manually inside a handler, creating a detached subscription, crossing into callbacks/libraries that do not propagate Context, or running out-of-band tasks without explicitly passing required data.
3. Never carry the raw authentication object wholesale into long-lived message queues or jobs. For background tasks, pass a minimal set of verified attributes and re-apply authorization policies on the receiving side.
4. Never block the event loop with `block()`, synchronous JDBC, or blocking I/O calls. Blocking can exhaust threads and expose the application to denial of service. If calling a blocking API is unavoidable, isolate and bound it on an appropriate scheduler; ideally use a reactive client.

### 3.3 Backpressure is not a firewall

`Flux` and backpressure help components coordinate data consumption rates; they **do not automatically limit** attack connections, request payload sizes, stream lifetimes, expensive queries, or concurrent request counts. An endpoint using `Flux` can still be abused via oversized uploads, never-ending streams, slow-reading clients, or thousands of failed authentication attempts.

You must enforce limits on body size, timeouts, concurrency, per-identity/per-source request rates, and service resources. Codec settings like `maxInMemorySize` only cap buffer memory for related decoding operations; they do not replace overall ingress and application-level limits.

## 4. Attack Surfaces Along the Request Flow

### 4.1 Internet edge, TLS, and forwarded headers

Clients control `Host`, URL, body, and most HTTP headers. Client-sent `X-Forwarded-For`, `X-Forwarded-Proto`, or `Forwarded` headers **are not trustworthy evidence** of IP or HTTPS. Only proxies you control may overwrite/set these headers, and only applications behind trusted proxies should use them to infer scheme, host, or real client address.

Example mistake: an IP rate limiter reads `X-Forwarded-For` directly from the Internet; attackers rotate the header on every request to bypass the limit. Mitigation: strip client-supplied headers at the edge, regenerate standard headers at the proxy, define trusted proxy network ranges, and enforce real rate limits at the edge.

TLS must be protected on both client–ingress and ingress–backend hops according to the deployment model. When using secure cookies, configure `Secure`/`HttpOnly`/`SameSite` appropriately and consider HSTS at the HTTPS termination point.

### 4.2 Authentication: who is sending the request?

- **Session/cookie:** the server associates a session with the user; browsers can attach cookies automatically, so CSRF protection is needed for state-changing operations.
- **Bearer access token:** clients send `Authorization: Bearer ...`. A resource server must verify the signature or perform appropriate introspection, expiration, issuer, and expected audience checks; never decode a JWT payload and immediately trust its claims.
- **OIDC/OAuth2:** the Identity Provider (IdP) issues identities/tokens; the application remains responsible for verifying that the token is intended for **the right resource server**. An unexpired token issued for a different API is not valid grounds for access.
- **API keys / service credentials:** must have scoped permissions, lifecycles, secret protection, and usage limits; caller-supplied headers cannot turn themselves into an authenticated identity.

In JWT resource server configuration using `issuer-uri`, Spring Security typically verifies signature, issuer, and timestamps like `exp`/`nbf` via its built-in mechanism. **Do not assume audience is always checked to match your application's requirements:** configure the expected audience validator and test tokens intended for other APIs.

### 4.3 Authorization: what is that user allowed to do?

Two requests may both carry valid tokens yet differ in permissions:

```text
GET /api/orders/1001  Authorization: Bearer <token-user-A>
GET /api/orders/1002  Authorization: Bearer <token-user-A>
```

Suppose order `1001` belongs to A, while `1002` belongs to B. Checking `authenticated()` or `hasRole("USER")` on both requests is still not enough. The service must use the verified identity/tenant to check **permission to read that specific order**, such as querying with both `orderId` and `tenantId` constrained from the trusted principal. Never take `tenantId` from a client-declared query parameter or header as the source of truth.

If viewing a resource is not allowed, the API can return `403 Forbidden` or `404 Not Found` depending on existence-disclosure policy. Keep handling consistent across caches, object storage, and asynchronous events.

### 4.4 CORS, CSRF, and browsers

**CORS** is a browser mechanism deciding whether JavaScript from another origin may read responses or send certain cross-origin requests under server policy. CORS **does not replace** authentication, authorization, or rate limiting; non-browser clients generally do not obey CORS. Never carelessly allow arbitrary origins together with credentials.

**CSRF** exploits browsers automatically sending credentials (cookies or certain browser-cached authentication forms) to trigger unintended actions. For UI/session/cookie flows, keep Spring Security's CSRF mechanism and apply it properly to write requests. An API that genuinely uses no auto-attached credentials and only accepts bearer tokens explicitly attached by the client may have a different CSRF design, but that assumption must be proven before disabling CSRF.

**Origin**, **Referer**, and **SameSite** can support browser policies; they are not proof of user identity. Distinguish `401 Unauthorized` (lacking valid authentication) from `403 Forbidden` (authenticated but lacking permissions), even though specific mechanisms can influence response details.

### 4.5 Input data and resources

Body, query, path, multipart, filename, external URLs, headers, and JSON values are all untrusted inputs. Validate types, lengths, value ranges, encoding, and business constraints on the server. Never carelessly bind JSON directly into entities containing `role`, `ownerId`, `price`, `tenantId`, or `isAdmin` fields to prevent mass assignment.

For databases, use parameterized queries and access constraints to prevent injection and BOLA. For file uploads, restrict sizes, accepted content types, read/write permissions, and storage paths. For WebClient accepting input URLs, defend against **SSRF** with destination allowlists, blocking access to internal addresses/cloud metadata endpoints outside policy, and controlling redirects.

## 5. A Runnable WebFlux Example to Test Permissions

The small example below uses **HTTP Basic with fixed accounts solely for localhost learning**; it is not a production login model. All endpoints perform GET only, so the default CSRF mechanism is not disabled. The goal is to distinguish public access, authentication, and role-based authorization. Never use sample passwords in real environments.

**Create a standalone Gradle project** with structure:

```text
boundary-demo/
  build.gradle
  src/main/java/demo/BoundaryDemo.java
```

**build.gradle**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/java/demo/BoundaryDemo.java**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class BoundaryDemo {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryDemo.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/private").hasRole("USER")
                .pathMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        Mono<String> publicInfo() {
            return Mono.just("public");
        }

        @GetMapping("/private")
        Mono<String> privateInfo() {
            return Mono.just("private: authenticated USER");
        }

        @GetMapping("/admin")
        Mono<String> adminInfo() {
            return Mono.just("admin");
        }
    }
}
```

Run with **compatible Gradle and JDK 17+**: `gradle bootRun`; if the project already has a wrapper, use `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Once the server starts on the default port 8080, test:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u alice:demo-pass http://localhost:8080/private
curl -i -u alice:demo-pass http://localhost:8080/admin
```

| Test | Expected result |
|---|---|
| GET `/public` without credentials | HTTP 200, body `public` |
| GET `/private` without credentials | HTTP 401 (authentication required) |
| GET `/private` as `alice` | HTTP 200, body `private: authenticated USER` |
| GET `/admin` as `alice` | HTTP 403 (lacks `ROLE_ADMIN`) |

HTTP headers/startup logs may vary by environment, but the status codes illustrate the distinction **public → authentication → authorization**. `hasRole("USER")` maps to authority `ROLE_USER`; the example intentionally **does not** assume the ADMIN role automatically inherits USER.

**Limitations of the example:** HTTP Basic sends credentials on every request; test only on localhost or over TLS, and never put credentials in production source code. The example does not yet demonstrate object-level authorization, JWT validation, request rate limiting, or downstream connections. For production applications, controls must be added according to your threat model; merely replacing Basic with JWT does not solve BOLA or SSRF.

## 6. Walkthrough of Protecting a Request Across Proper Boundaries

Consider `GET /api/orders/{orderId}` in a multi-tenant system:

1. **Client → ingress:** receives URL and token; ingress applies connection/request limits, normalizes forwarded headers, and enforces HTTPS.
2. **Ingress → WebFlux:** `ServerWebExchange` passes through `SecurityWebFilterChain`; invalid requests are rejected before entering business logic.
3. **Token → principal:** the resource server validates the token against issuer/audience/signature/expiration as required and creates the principal/authorities. Tenant claims are trusted only after verification and scope checks.
4. **Principal → order:** the handler/service treats `orderId` from the URL solely as an **identifier to verify**, not as an access grant. Business logic verifies the caller is authorized to view the order, e.g., querying by both `orderId` and the authenticated tenant.
5. **Order → DB/cache:** every query and cache key must preserve the tenant boundary; never key caches solely by `orderId` if IDs are not globally safe.
6. **Result → client:** serialize only permitted fields; do not return entities containing excess secrets/PII; log sanitized correlation IDs instead of raw bearer tokens.

A **logical outline, not a standalone program**:

```text
authenticatedTenant = principal.verifiedTenant
order = repository.findByIdAndTenantId(orderId, authenticatedTenant)
if order is missing: return HTTP 404
if policy denies access to order: return HTTP 403
return an approved response DTO (not the raw persistence entity)
```

The crux is that **verifying identity in a filter does not replace checking data-bound permissions in the service/repository**. The same rule applies to updates, deletions, file downloads, and event publishing.

## 7. Non-HTTP Flows Also Carry Trust Boundaries

**WebClient and external systems.** When an API calls service B, do not blindly forward the original `Authorization` header to every URL. Forward tokens only when B is an authorized recipient, the token carries the right audience/scope, and an explicit delegation policy exists. Never use request-supplied URLs to call arbitrary network resources. Validate TLS, and enforce timeouts, connection limits, and response size caps.

**WebSockets or long-lived streams.** Authenticating at handshake identifies who opened the connection, yet does not automatically authorize every message, subscription, or topic. Check permissions per sensitive action, handle token expiration/revocation by design, and limit message sizes and rates. Pushed SSE/Flux data must also be filtered to the right recipient; a long-lived stream does not mean permissions last forever.

**Message brokers / background jobs.** Producers may send malformed messages or be compromised; consumers must verify schemas, sources, and execution permissions. Never treat self-declared `userId`, `tenantId`, or `role` fields inside an event as sufficient proof for privileged actions. Protect service account secrets, retries, and dead-letter queues against data leaks.

**Actuator, diagnostics, and logs.** Health, metrics, config, env, or dump endpoints can expose system details/configurations if misconfigured as public. Expose only what is necessary, segregate networks/authorize access appropriately, scrub tokens, cookies, passwords, and PII, and avoid error responses containing sensitive stack traces. Client-provided Correlation IDs must also be sanitized to prevent log injection.

## 8. How to Build a Simple Threat Model for an Endpoint

For each endpoint or message flow, answer in turn:

1. **Which assets are affected?** Whose data, which actions, and which services/resources could be exhausted?
2. **Where do inputs come from?** Client, proxy, JWT/IdP, DB, cache, external service, message broker? Which parts are attacker-controlled?
3. **Which boundaries are crossed?** At which steps is an input turned into an identity, permission, query, outbound URL, or returned data?
4. **Who checks and what is the proof?** TLS, token verification, audience/scope, object/tenant checks, validation, destination allowlists, resource limits, audit logs.
5. **What if it is abused?** 401/403/404, timeout/429/413, request rejection, limited error disclosure, logging/anomaly monitoring.
6. **Can negative cases be tested?** Invalid tokens, another user's resource ID, spoofed forwarded headers, cross-origin requests, oversized bodies, internal IP URLs, unauthorized subscribers.

Practical test matrix:

| Case | Expectation |
|---|---|
| Missing credentials / expired token / invalid signature | No access to protected data; appropriate rejection response |
| Valid JWT with wrong audience | Not accepted as a token intended for this API |
| USER A accesses an ID belonging to USER B | Denied even though USER A is logged in |
| USER A modifies `tenantId` in query/header/body | Cannot bypass server-side tenant constraints |
| Spoofed `X-Forwarded-For` sent from the Internet | Does not corrupt source identity or rate-limit policies |
| Disallowed origin or forged cookie request | CORS/CSRF policies apply appropriately per client type |
| Oversized body, infinite stream, or request flood | Size/time/resource limits enforced, preventing unbounded system consumption |
| Internal/cloud-metadata URL injected into WebClient | Blocked by destination policy |
| Accessing sensitive management/metrics endpoints | Accessible only to authorized users/systems |
| Mid-stream client disconnect or downstream error | Resources released cleanly, no data leak, no unauthorized side effects |

## 9. Misconceptions to Avoid

- **"Reactive is inherently safer."** Reactive describes an execution model; authentication, authorization, resource limits, and data validation are still required.
- **"Gateway authentication is enough."** The resource-owning service must still enforce business and per-object/per-tenant authorization.
- **"A JWT with a valid signature works everywhere."** You must verify issuer, expiration, audience, token type, and appropriate permissions.
- **"CORS stops hackers from calling the API."** CORS is mainly enforced by browsers; it does not replace server-side security.
- **"Disabling CSRF is standard for every reactive API."** The decision depends on credential types and whether browsers attach them automatically.
- **"Reactor Context = ThreadLocal."** Context is tied to the reactive stream/subscription; watch out for detached subscriptions, manual threads, or non-propagating libraries.
- **"Backpressure stops DDoS automatically."** You still need limits on ingress, requests, bodies, connections, concurrency, timeouts, and resources.
- **"Data inside a VPC is trustworthy."** Internal services, queues, and callbacks can still be misconfigured or compromised.

## 10. Key Takeaways

Trace the path of **request → authentication → authorization decision → data → external services → response**, marking every place where data, identity, or permissions cross into another zone. With Spring Security WebFlux, protective layers must work together: configure `SecurityWebFilterChain` properly, retrieve security context the Reactor way, enforce resource permissions, validate inputs/outputs, and protect every downstream call. An authenticated request is only **an input to the authorization decision**, not a safety guarantee for the entire flow.