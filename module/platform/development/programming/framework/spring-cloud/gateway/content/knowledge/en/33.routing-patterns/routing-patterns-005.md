# Backend for Frontend by Application Type

## 1. When One Shared API No Longer Fits Every Client

Suppose a retail platform has three frontends: a **customer website**, a **mobile app**, and an **internal admin portal**. All three consume data from the `catalog`, `orders`, `customers`, and `inventory` microservices, yet they use that data very differently:

- The website needs carts, checkout, browser login state, and page-oriented display data.
- The mobile app needs lean payloads, fewer network round trips, small-screen pagination, and resilience on weak networks.
- The admin portal needs wide field lookups, change histories, sensitive operations, and strict access controls.

If every client calls one general-purpose backend, the API accumulates flags like `?device=mobile&admin=true&fields=...`, responses bloat, and UI changes risk breaking other consumers. **Backend for Frontend (BFF)** solves this by creating a **dedicated backend layer tailored to each frontend type or user experience**.

In the **SPRING_CLOUD_GATEWAY** module, we already have building blocks for an API Gateway—route predicates, filter chains, path/header rewriting, service discovery, plus authentication, rate limiting, circuit breakers, retries, TLS, and observability. A BFF is an **architectural pattern deployed behind or alongside the Gateway**, not the name of a built-in `GatewayFilterFactory` or route predicate.

The lesson **“Backend for Frontend by Application Type”**, in the **Routing Patterns** chapter, explains when to adopt a BFF, how to use Spring Cloud Gateway Server to route web/mobile/admin traffic, how to design per-client data and security contracts, and how to prove with labs and tests that traffic never misroutes.

After this lesson, you will be able to:

1. Distinguish a **shared API Gateway**, a **dedicated BFF**, and a **business domain microservice**.
2. Design hostname- or path-based routes without trusting self-declared headers like `X-App-Type` for authorization.
3. Configure Gateway Server WebFlux 4.x/5.x to dispatch web, mobile, and admin traffic to their respective BFFs.
4. Explain the browser OAuth BFF pattern: confidential client, session cookies, server-side tokens, and CSRF.
5. Contrast mobile public OAuth clients + PKCE against session-backed browser BFFs.
6. Build an aggregation endpoint using WebFlux `WebClient` with controlled timeouts and fan-out.
7. Test BFF selection, path transformations, authentication, authorization, rate limiting, and observability.
8. Evaluate trade-offs in service count, coupling, latency, and ownership across frontend teams.

> **Technical scope:** Gateway examples use **Spring Cloud Gateway Server WebFlux**. Server Web MVC provides equivalent routing/filtering via WebMvc.fn, but with different packages, filters, and configuration namespaces. The OAuth portion for a browser BFF must be designed independently of routing; never assume a Gateway route automatically constitutes a complete OAuth confidential client.

## 2. What Is a BFF, and How Does It Differ from an API Gateway?

An **API Gateway** typically serves as the shared entry point for cross-cutting concerns: upstream selection by `Host`/`Path`/`Method`, edge authn/authz, headers, TLS, rate limiting, routing, and observability. A **BFF** serves the needs of **one frontend or a group of frontends sharing a contract**: aggregating data, shaping DTOs, paginating, screen-level caching, and handling client-appropriate login sessions.

| Concern | Shared API Gateway | Experience-specific BFF | Domain microservice |
| --- | --- | --- | --- |
| Scope | Multiple clients and many routes | One frontend experience or cohesive group | One bounded context / domain |
| Routing | `Host`/`Path`/`Method` predicates | UI-contract endpoints | Business API / resource routing |
| Request/response shaping | Route filters, headers/paths/status | DTO composition, shaping, defaults | Business validation and domain logic |
| Authentication | Edge policies or token validation | Browser session/OAuth or client-appropriate bearer | Token / workload identity checks |
| Authorization | Coarse route-level access control | Use-case scopes/roles | Resource ownership / tenant checks |
| Deployment cadence | Gateway routing / infra team | Frontend team can deploy independently | Domain team |
| Observability | Route IDs, downstream latency, failures | Screen/use-case latency, fan-out counts | Domain latency, DB/business errors |
| Should not contain | Excessive UI-specific business DTOs | Core business rules / cross-service transactions | Screen-by-screen layout structures |

### 2.1. A BFF Does Not Require One Microservice per Screen

The pattern does not mandate a separate process for **every view** or **every physical device**. Group by **contract divergence and release cadence**:

- Desktop and tablet web apps sharing login flows and payloads can share `web-bff`.
- iOS and Android apps sharing UI and contracts can share `mobile-bff`.
- An admin portal with sensitive data and distinct permissions typically warrants a separate `admin-bff`.

If you have only two simple endpoints and all clients consume the exact same payload, adding three services merely inflates operational cost. **Real contract divergence** dictates the number of BFFs.

### 2.2. A BFF Does Not Replace Business Microservices

For example, `mobile-bff` can combine product names with delivery status, yet **it must never own tax calculation rules, funds transfers, inventory reservation, or account permissions**. Those belong in domain services. Keep BFFs free of core business state and avoid creating a second, out-of-sync source of truth.

### 2.3. API Gateway and BFF Can Be One or Two Layers

Two common topologies:

**Option A — Shared Gateway in front of multiple BFF services:**

~~~mermaid
flowchart TD
    W["Web browser"] --> E["Ingress / Edge TLS"]
    M["Mobile app"] --> E
    A["Admin UI"] --> E
    E --> G["Spring Cloud Gateway Server"]
    G -->|"Host/Path web"| BW["web-bff"]
    G -->|"Host/Path mobile"| BM["mobile-bff"]
    G -->|"Host/Path admin"| BA["admin-bff"]
    BW --> S["Catalog / Orders / Customer services"]
    BM --> S
    BA --> S
~~~

**Option B — A BFF also runs Gateway Server internally:** a public edge selects the BFF, and `web-bff` uses Spring Cloud Gateway's `TokenRelay`, path filters, and HTTP routing to resource servers alongside DTO-shaping controllers. This works well when a BFF primarily proxies APIs while managing an OAuth session.

Not **every** BFF needs the Gateway Server starter. If a BFF mainly aggregates multiple resource APIs, Spring WebFlux `@RestController` and `WebClient` often fit better while the shared Gateway handles edge routing.

## 3. Data and Security Profiles by Application Type

| Characteristic | Browser/Web BFF | Native Mobile BFF | Admin BFF |
| --- | --- | --- | --- |
| Client | JavaScript in browser | Native iOS/Android | Internal browser or admin client |
| Contract | Cart, checkout, profile pages | Lean home/feed, small pages, offline sync | Audits, reports, bulk actions |
| Typical OAuth | Confidential BFF client, session cookie; tokens stay on server | Public OAuth client + Auth Code/PKCE, bearer access token | SSO/MFA, strong roles/scopes, appropriate session or token |
| CSRF | Mandatory consideration because cookies auto-attach | Not the default mechanism if bearer-header only | Required whenever cookie sessions are used |
| CORS | Prefer same-origin web UI + BFF | Native apps are not browser-CORS bound like JS | Prefer same-origin / explicit admin hostname |
| Response payload | Rich per page | Compact, few round trips, resilient on weak links | Detailed, filtering/pagination/audit fields |
| Quota | Per user/session + route | Per verified principal, device risk, plan | Per operator/tenant and operation type |
| Caching | `no-store` for private/cart; TTL for catalog | Cache featured/read-only safely, ETag | Strictly limited for sensitive data |
| Primary threats | XSS, CSRF, session fixation, token/session theft | Token theft, replay, app version drift | Privilege escalation, data export, insider risk |

**Never use `X-Client-Type: mobile` as an authority source.** Client-supplied headers may assist logging or formatting if validated, yet they never prove device or user identity and must never bypass MFA or authorization. Likewise, `User-Agent` is trivially spoofed and unsuitable as a security boundary.

### 3.1. Same Domain API, Different Responses by Use Case

Suppose the orders service returns this domain DTO:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-9",
  "items": [{"sku": "A1", "price": 120000, "qty": 2}],
  "discountBreakdown": {"campaign": "WELCOME"},
  "shipping": {"state": "IN_TRANSIT", "trackingNumber": "TR-99"},
  "internalWarehouseCode": "WH-3",
  "audit": {"lastModifier": "ops-12"}
}
~~~

The Web BFF can return details suited to a web order page (items, shipping state); the Mobile BFF can return only `orderId`, `displayTotal`, and `shippingState`; the Admin BFF can include `audit` **after verifying permissions**. The Gateway does not magically filter JSON fields by `User-Agent`: **each BFF owns and enforces its own DTO contract in backend code**.

Never ship `internalWarehouseCode` or private audit metadata to mobile merely because “the app doesn't render it”; **unauthorized fields must be stripped on the server**.

## 4. Designing the BFF Routing Layer: Host or Path?

Two widely used schemes:

| Scheme | Public URL example | Strengths | Drawbacks |
| --- | --- | --- | --- |
| **Host-based** | `https://web.example.test/bff/home`, `https://mobile.api.example.test/v1/home` | Isolates origins, cookies, and TLS per client; BFF owns login callbacks cleanly | Requires explicit DNS, TLS, and host routing |
| **Path-based** | `https://api.example.test/web/home`, `.../mobile/home` | Simple for labs or a single shared API domain | Path rewrites, login redirects, cookie paths, CORS, and policies are trickier |
| Combined Host+Path | `admin.api.example.test/admin/audit` | Restricts allowed paths on the expected host | Not auth by itself; still requires RBAC and network boundaries |

### 4.1. Why Prefer Hostnames When a Browser BFF Holds Sessions?

A browser BFF performs OAuth2 redirect logins, `/login/oauth2/code/{registrationId}` callbacks, session cookies, and sometimes static web assets. If the Gateway strips a `/web` prefix via `StripPrefix=1`, the BFF may generate redirects to `/login` instead of `/web/login`, misaligning cookie paths and breaking callbacks.

Separate hostnames keep **public origins** consistent for UI and BFF—e.g., both live on `https://web.example.test`. Path-based `/web/**` still works if you properly configure forwarded prefixes, redirect URIs, cookie paths, CORS, and end-to-end tests—never just add `StripPrefix` and assume it works.

### 4.2. The `Host` Predicate Does Not Authenticate the Client

Any HTTP client can send:

~~~bash
curl -i "http://127.0.0.1:8080/bff/home" \
  -H "Host: web.example.test"
~~~

The Gateway will match the web route from the `Host` header. That **proves routing only**, not that the caller is a legitimate browser. HTTPS SNI/certificates, edge allowlists, Spring Security OAuth2 login, session protections, and backend authorization establish the real trust boundary.

### 4.3. Never Route Admin Traffic via a Spoofable Header

**Wrong:**

~~~yaml
predicates:
  - Path=/**
  - Header=X-Admin,^true$
~~~

Any client can send `X-Admin: true`. **Right direction:** route admin traffic via explicit `Host`/`Path` **and** enforce SSO/MFA, roles/scopes, network isolation, and auditing:

~~~yaml
predicates:
  - Host=admin.api.example.test
  - Path=/admin/**
~~~

Even those two predicates remain route selection, **never a substitute for authorization**.

## 5. Gateway Server WebFlux 5.x Configuration: One Edge, Three BFFs

In a production-like host-based topology, assume:

| Public host allowed by ingress | Internal service | Role |
| --- | --- | --- |
| `web.example.test` | `http://web-bff:9081` | Web UI, OAuth login, sessions, REST BFF |
| `mobile.api.example.test` | `http://mobile-bff:9082` | Mobile API `/v1/**` |
| `admin.api.example.test` | `http://admin-bff:9083` | Admin API `/admin/**` |

Public DNS and TLS are terminated at Ingress. Service names are **illustrative**, resolving only within the target network/cluster. Localhost labs substitute `127.0.0.1` with three ports. Adding a `Host` predicate does not automatically provision TLS certificates for those three hosts.

### 5.1. `application.yml` for Gateway Server WebFlux 5.x

~~~yaml
spring:
  application:
    name: edge-bff-gateway
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Role
            - RemoveRequestHeader=X-Tenant-Id
          routes:
            - id: web-bff-route
              order: -30
              uri: http://web-bff:9081
              predicates:
                - Host=web.example.test
              filters:
                - AddResponseHeader=X-Lab-Bff-Route,web-bff-route

            - id: mobile-bff-route
              order: -20
              uri: http://mobile-bff:9082
              predicates:
                - Host=mobile.api.example.test
                - Path=/v1/**
              filters:
                - AddResponseHeader=X-Lab-Bff-Route,mobile-bff-route

            - id: admin-bff-route
              order: -10
              uri: http://admin-bff:9083
              predicates:
                - Host=admin.api.example.test
                - Path=/admin/**
              filters:
                - AddResponseHeader=X-Lab-Bff-Route,admin-bff-route
~~~

**Route-by-route breakdown:**

1. `web-bff-route` matches only `web.example.test`. It **omits a `Path` predicate** so `/oauth2/authorization/...`, `/login/oauth2/code/...`, static assets, and `/bff/**` APIs all reach the web BFF. Which URLs are actually permitted or denied remains governed by **the web BFF's `SecurityWebFilterChain`**.
2. `mobile-bff-route` requires **both `Host` and `Path`** (logical AND). The BFF exposes only the mobile `/v1/**` API contract.
3. `admin-bff-route` requires the admin host and `/admin/**`. This **is insufficient protection on its own**: the backend must enforce SSO, roles, scopes, and MFA policies.
4. In this layout, BFFs keep paths intact with no `StripPrefix`. The Gateway forwards to the right service while preserving URL contracts.
5. `RemoveRequestHeader` strips client-supplied identity-like headers **before reaching the BFF**, preventing backends from trusting them.
6. `X-Lab-Bff-Route` is a **test marker**, never security evidence. In production, typically omit or avoid exposing internal route IDs unnecessarily.

**Critical note:** `Host=web.example.test` checks the HTTP `Host` header; **it does not verify SNI, connection origin, hostname authorization, or OAuth login**. Ingress must reject invalid `Host` headers and enforce TLS, and backend services must accept traffic only along approved paths.

### 5.2. Method-Specific Routes and CORS Preflight

You can add `Method=GET,POST` to an API route when only those methods are allowed. Remember that browser CORS preflight sends **`OPTIONS`**, which will not match that predicate; configure CORS at the appropriate layer and test both `OPTIONS` and actual requests. Never treat the `Method` predicate as an authorization control.

Example:

~~~yaml
predicates:
  - Host=mobile.api.example.test
  - Path=/v1/catalog/**
  - Method=GET,HEAD
~~~

For read-only routes, test that `POST` does not match and verify no broad fallback route captures `POST` unintentionally.

### 5.3. Avoid Overly Broad Host/Path Fallbacks

A configuration such as:

~~~yaml
- id: catch-all
  uri: http://web-bff:9081
  predicates:
    - Path=/**
~~~

can swallow requests targeting admin or mobile hostnames that missed primary routes, leaking requests to the wrong service or muddying debugging. If you define a fallback, give it an **explicit purpose**, order, host allowlist, and clear policy response—never silently send unknown hosts to the web BFF.

### 5.4. Route Order and Privilege Separation

Spring Cloud Gateway evaluates routes by runtime `order`; lower values take precedence when multiple routes match. Above, hosts are disjoint, so `order` merely documents priority rather than “granting access.” If you later add a shared route:

~~~yaml
- id: shared-public
  order: 100
  predicates:
    - Host=web.example.test,mobile.api.example.test
    - Path=/public/**
~~~

verify which route matches first and check each BFF's security rules. Never rely on `order` as the sole barrier protecting admin access: both the BFF and domain services must enforce permissions.

## 6. Namespaces and Starters: WebFlux Gateway 4.x vs. 5.x

Spring Cloud Gateway changed module names and configuration prefixes across release trains. Never mix prefixes from two lines in the same `application.yml`.

| Purpose | WebFlux Gateway 4.2/4.3 | WebFlux Gateway 5.x |
| --- | --- | --- |
| Route config | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Default filters | `spring.cloud.gateway.default-filters` | `spring.cloud.gateway.server.webflux.default-filters` |
| Typical starter | `spring-cloud-starter-gateway` on older lines | `spring-cloud-starter-gateway-server-webflux` |
| Web stack | Spring WebFlux / Reactor Netty | Spring WebFlux / Reactor Netty |
| Verification | Effective BOM + runtime route inventory | Effective BOM + runtime route inventory |

Abbreviated example for **WebFlux Gateway 4.2/4.3**:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveRequestHeader=X-User-Id
        - RemoveRequestHeader=X-Role
        - RemoveRequestHeader=X-Tenant-Id
      routes:
        - id: web-bff-route
          uri: http://web-bff:9081
          predicates:
            - Host=web.example.test

        - id: mobile-bff-route
          uri: http://mobile-bff:9082
          predicates:
            - Host=mobile.api.example.test
            - Path=/v1/**

        - id: admin-bff-route
          uri: http://admin-bff:9083
          predicates:
            - Host=admin.api.example.test
            - Path=/admin/**
~~~

Pick the **Spring Cloud BOM compatible with your Spring Boot version**. Never include both old and new starter names together “just in case.” Web MVC uses `spring.cloud.gateway.server.webmvc.routes` on newer lines with distinct WebMvc.fn APIs, so never copy WebFlux `GlobalFilter` or `ServerWebExchange` code into MVC.

**Verify after startup:** confirm route IDs, URIs, predicates, and default filters actually materialized. A YAML file with the wrong prefix can be silently ignored so the app boots with **zero BFF routes**.

## 7. Simpler Lab: Routing by Path Prefix

To test quickly on localhost, run one Gateway on port 8080 and three BFF stubs on ports 9081/9082/9083. This lab omits OAuth login; it proves **route selection and path rewriting**.

| Public request to Gateway | Downstream URI | Which BFF? |
| --- | --- | --- |
| `GET /web/whoami` | `http://127.0.0.1:9081/whoami` | web |
| `GET /mobile/whoami` | `http://127.0.0.1:9082/whoami` | mobile |
| `GET /admin/whoami` | `http://127.0.0.1:9083/whoami` | admin |
| `GET /unknown/whoami` | No route in this fixture | none |

### 7.1. `application-bff-lab.yml` on Gateway 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: edge-bff-lab
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Role
          routes:
            - id: web-bff-lab
              uri: http://127.0.0.1:9081
              predicates:
                - Path=/web/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Lab-Channel,web
                - AddResponseHeader=X-Lab-Bff-Route,web-bff-lab

            - id: mobile-bff-lab
              uri: http://127.0.0.1:9082
              predicates:
                - Path=/mobile/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Lab-Channel,mobile
                - AddResponseHeader=X-Lab-Bff-Route,mobile-bff-lab

            - id: admin-bff-lab
              uri: http://127.0.0.1:9083
              predicates:
                - Path=/admin/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Lab-Channel,admin
                - AddResponseHeader=X-Lab-Bff-Route,admin-bff-lab
~~~

Run with the profile active:

~~~bash
./mvnw spring-boot:run \
  -Dspring-boot.run.profiles=bff-lab
~~~

Or set `SPRING_PROFILES_ACTIVE=bff-lab` as appropriate for your shell/platform. Ensure the test profile **replaces the main profile's routes**, avoiding extra host-based routes that could skew results.

### 7.2. Predicate/Filter Ordering

With `Path=/web/**`, `/web/whoami` first matches the web route; only afterward does `StripPrefix=1` rewrite the downstream path to `/whoami`. Mutating the path in a filter **does not cause the Gateway to re-evaluate `Path` predicates** against the rewritten path.

`AddRequestHeader=X-Lab-Channel,web` adds a lab diagnostic marker only. It is **not verified identity**: a client could send a header with the same name, creating duplicate values. In production, if a BFF relies on a trusted channel header, strip any inbound header first, set it from route metadata at the trusted Gateway, and still enforce authorization via the authenticated principal.

### 7.3. Why Not Use the Path Lab Directly for an OAuth Web BFF?

For example, `/web/login/oauth2/code/browser` gets stripped to `/login/oauth2/code/browser`, matching the callback **inside the BFF**; however, the OAuth provider's redirect URI must match the **public URL** `https://api.example.test/web/login/oauth2/code/browser`. You would need accurate forwarded prefixes/hosts/schemes, aligned cookie paths/`SameSite`, and `/web`-aware OAuth security redirects.

Until you are ready to engineer and test all of those pieces, prefer **host-based routing** for production web BFFs. Never copy the path-lab config and claim your browser OAuth flow is secure.

## 8. Browser BFF: OAuth Confidential Client and Cookie Sessions

A core reason to adopt the BFF pattern is **avoiding exposing OAuth access/refresh tokens to browser JavaScript**. According to **RFC 10017 (OAuth 2.0 for Browser-Based Applications, August 2026)**, a browser BFF performs three jobs:

1. Acts as a **confidential OAuth client**: initiates the authorization code flow and exchanges codes for tokens server-side with the authorization server.
2. Stores access/refresh tokens in a **server-side session or secure store**, issuing only a secure session cookie to the browser.
3. Accepts resource requests from the browser and attaches the **appropriate access token** before forwarding to resource servers.

### 8.1. Browser BFF Sequence

~~~mermaid
sequenceDiagram
    participant Browser
    participant BFF as Web BFF
    participant IdP as OAuth/IdP
    participant API as Orders Resource Server
    Browser->>BFF: GET /bff/orders/42 (unauthenticated)
    BFF-->>Browser: 302 to IdP /authorization
    Browser->>IdP: Authorization Code flow
    IdP-->>Browser: 302 to BFF callback + code
    Browser->>BFF: GET /login/oauth2/code/browser
    BFF->>IdP: Server-to-server code + client authentication
    IdP-->>BFF: Access token / refresh token (if issued)
    BFF-->>Browser: Session cookie Secure; HttpOnly; appropriate SameSite
    Browser->>BFF: GET /bff/orders/42 + session cookie
    BFF->>API: GET /orders/42 + token scoped for resource server
    API-->>BFF: Order data (resource authorized)
    BFF-->>Browser: Web DTO JSON
~~~

**Never place access tokens into `localStorage` or JSON responses to the browser just for coding convenience.** If the browser holds tokens and calls microservices directly, you no longer have the token-isolating OAuth BFF pattern described above.

### 8.2. Keeping Tokens Out of the Browser Does Not Eliminate XSS Risk

With a BFF, malicious JavaScript can still **issue requests using the user's active session** even without reading raw tokens. Therefore combine:

- XSS defenses: CSP, output encoding, avoiding unsafe dynamic HTML, dependency hygiene.
- CSRF defenses: token and origin validation on state-changing requests.
- Session cookies marked `Secure`, `HttpOnly`, and `SameSite` aligned with OAuth redirects and cross-site topology.
- Session rotation upon login, proper logout/invalidation, TTL/idle timeouts, renewal, and multi-replica session storage.
- HTTPS/HSTS, with the BFF application listener never exposed directly.
- Backend resource authorization based on tokens, claims, and object ownership—not merely “user logged in.”

RFC 10017 emphasizes that a BFF requires **CSRF defense** because browsers attach cookies automatically on certain requests. CORS allowlists and `SameSite` cookies help, yet neither solves every same-site cross-origin subdomain scenario alone.

### 8.3. Cookie Session Attributes Across Applications

| Attribute | Consideration | Notes |
| --- | --- | --- |
| `Secure` | Mandatory over public HTTPS | Never emit auth cookies over plain Internet HTTP |
| `HttpOnly` | Yes for session cookies | Prevents JS from reading the session ID directly |
| `SameSite=Lax/Strict` | Pick based on OAuth redirects and domain layout | `Strict` can break cross-site IdP login callbacks |
| `Path` | Usually `/` when UI and BFF share a host | If path-based, verify cookie `Path` behind proxies |
| `Domain` | Prefer host-only cookies | Never widen to `.example.test` unnecessarily |
| Expiry | TTL, idle timeout, rotation | Never leave sessions valid indefinitely |
| Session store | Secure multi-replica store when scaled | In-memory works only for a single process/lab |

During OAuth authorization-code callbacks, state/session cookies may need to travel on a top-level cross-site redirect. Test on **real browsers** (`SameSite` behavior), not solely `curl`; never set `SameSite=Strict`, break login, and then disable all cookie protections out of frustration.

## 9. Configuring Spring Cloud Gateway as a Browser BFF

When a web BFF primarily **proxies existing resource servers** while managing an OAuth session, it can run its own **Gateway Server WebFlux** instance. In a host-based topology, the public edge matches `web-bff-route` and forwards `/oauth2/**`, `/login/**`, and `/bff/**` intact to `web-bff`.

### 9.1. Dependencies

Maven example using a compatible Spring Boot / Spring Cloud BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
~~~

Do not pin individual Spring Cloud versions when managed by the BOM. On Gateway WebFlux 4.2, adjust starter names and route prefixes to your release line; never combine Server Web MVC and WebFlux starters together.

### 9.2. Illustrative `application.yml` for `web-bff` (Gateway 5.x)

~~~yaml
server:
  port: 9081

spring:
  application:
    name: web-bff
  security:
    oauth2:
      client:
        registration:
          browser:
            provider: corporate
            client-id: web-bff-client
            client-secret: ${WEB_BFF_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          corporate:
            issuer-uri: https://idp.example.test/realms/platform
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: web-orders-api
              uri: http://orders-service:9091
              predicates:
                - Path=/bff/orders/**
              filters:
                - StripPrefix=1
                - TokenRelay=
                - AddResponseHeader=X-Lab-Bff-Route,web-orders-api
~~~

This is an **illustrative config**; replace the IdP/issuer and secret with securely managed real values. The `TokenRelay` filter factory is registered only when OAuth2 Client auto-configuration detects valid client registrations; if `spring.security.oauth2.client.*` is absent, the filter may not exist.

`StripPrefix=1` turns `/bff/orders/42` into `/orders/42` for the orders resource server. `TokenRelay=` (with no explicit `clientRegistrationId`) attaches the logged-in user's access token to the downstream `Authorization` header per Gateway documentation. **This relays the principal's token as-is** without exchanging audiences; the backend must verify that the token is intended for that resource server.

**Whenever a backend demands its own token audience**, perform proper token exchange or authorized-client acquisition instead of forwarding a BFF-scoped token. Never send refresh tokens downstream, and never log bearer access tokens.

### 9.3. `SecurityWebFilterChain` for the Web BFF

~~~java
package demo.webbff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class WebBffSecurityConfig {

    @Bean
    SecurityWebFilterChain webBffSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/oauth2/**", "/login/**")
                        .permitAll()
                        .pathMatchers(HttpMethod.GET, "/", "/index.html",
                                "/assets/**", "/favicon.ico")
                        .permitAll()
                        .pathMatchers("/bff/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

This configuration requires authentication on `/bff/**` and keeps Spring Security's CSRF protection enabled. If the BFF serves additional static assets or health endpoints, **allowlist only the exact URLs required**—never switch to `anyExchange().permitAll()` to work around login or CSRF issues.

### 9.4. Browser Requests

When UI and BFF share the origin `https://web.example.test`:

~~~javascript
const response = await fetch("/bff/orders/42", {
  method: "GET",
  credentials: "same-origin"
});

if (!response.ok) {
  throw new Error("Request failed: " + response.status);
}

const order = await response.json();
console.log(order);
~~~

**Do not attach a browser-stored `Authorization: Bearer` header** when using the confidential-client BFF pattern; the browser sends its session cookie, and the BFF manages sessions and downstream tokens.

For `POST /bff/orders`, the browser must send a CSRF token per Spring Security configuration; `credentials: "same-origin"` **does not replace CSRF protection**. You can configure `X-XSRF-TOKEN` via a server-issued cookie where appropriate, testing both cookie and header flow on the real frontend. Never disable CSRF globally because a `POST` returned 403.

### 9.5. Session and Token Storage When Scaling `web-bff` Horizontally

Gateway `TokenRelay` documentation notes that the default `ReactiveOAuth2AuthorizedClientService` uses an **in-memory store**. When deploying multiple replicas:

- Use a shared, secure session and authorized-client/token store (or evaluated sticky sessions with explicit risk acceptance).
- Encrypt sensitive stored token data, enforce TTL/idle timeouts, rotate tokens, and support revocation/logout.
- Guard against session fixation and verify CSRF state across OAuth redirects.
- Monitor errors caused by a replica missing an authorized client or token.
- Never dump plaintext access/refresh tokens into a cookie to stay “stateless” without full encryption, integrity, size, and security controls.

Spring Session with Redis handles HTTP sessions, yet **does not automatically persist OAuth2 authorized clients** unless the corresponding reactive services/beans are wired together properly. Always test login, token refresh, and logout across multiple replicas.

## 10. Native Mobile BFF: Do Not Copy Browser Cookie-Session Patterns

Native iOS and Android apps are normally **OAuth public clients**: they run Authorization Code + **PKCE** through the system browser/OS authorization agent and obtain access tokens directly. Mobile calls the BFF/API using:

~~~http
GET /v1/home HTTP/1.1
Host: mobile.api.example.test
Authorization: Bearer <mobile_access_token>
~~~

Here, **`mobile-bff`** acts as a resource server validating bearer tokens; it does not rely on browser session cookies as its primary identity mechanism. The BFF still optimizes mobile DTOs, versioning, aggregation, and per-user/app quotas.

### 10.1. `SecurityWebFilterChain` for the Mobile BFF

~~~java
package demo.mobilebff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class MobileBffSecurityConfig {

    @Bean
    SecurityWebFilterChain mobileSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/v1/catalog/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/v1/**").hasAuthority(
                                        "SCOPE_mobile.read")
                        .pathMatchers(HttpMethod.POST,
                                "/v1/**").hasAuthority(
                                        "SCOPE_mobile.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                // Only disable CSRF when clients strictly send
                // bearer tokens in the Authorization header with no cookie auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

This assumes `spring-boot-starter-oauth2-resource-server` and proper JWT decoder, issuer, and audience validators are configured. **Never disable CSRF like this** if `mobile-bff` also serves browsers or accepts session cookies. If a service handles both auth modes, define **separate `SecurityWebFilterChain` beans by matcher** and test CSRF enforcement on each path.

### 10.2. Validating `aud` and Scopes

A validly signed JWT issued for a different resource server **must not automatically work** on `mobile-bff`. Validate:

- Issuer, JWK signature, and allowed signing algorithms.
- `exp`/`nbf`, clock skew, and revocation where applicable.
- Audience matching `mobile-bff`; reject tokens minted only for web or admin.
- Endpoint-specific scopes/roles—never rely solely on `authenticated()` across all APIs.
- Downstream user/tenant permissions on specific resources.

Never trust client-supplied `X-App-Version`, `User-Agent`, or `X-Device-Id` to bypass scopes; they are metadata, not authentication.

### 10.3. What Should a Mobile BFF Optimize?

| Concern | BFF behavior | How to test |
| --- | --- | --- |
| Weak networks, high RTT | Aggregate calls needed for one screen | Count downstream requests; measure p95 under simulated mobile networks |
| Small screens | Return trimmed fields/DTOs | Contract tests per app version |
| Unstable connections | Timeouts, idempotent retries, ETag caching | Simulate timeouts, dropped responses, and retries |
| Asynchronous app releases | Versioned APIs, backward compatibility | Test across all still-supported app versions |
| Offline users | Provide ETags, timestamps, valid sync cursors | Revalidation and stale-data policy tests |
| Battery and bandwidth | Lean payloads and appropriate compression | Measure response bytes and network/battery impact |

Native apps store tokens using platform secure storage—**never embed an access token in a static HTTP header** or treat an unsigned device ID as authentication.

## 11. Admin BFF: Higher Privilege Comes from Security, Not a Route Named “admin”

An Admin BFF typically exposes endpoints such as:

~~~text
GET  /admin/audit/events
POST /admin/orders/{id}/refund
POST /admin/users/{id}/disable
GET  /admin/reports/export
~~~

These are high-impact actions. Matching `Host=admin.api.example.test` + `Path=/admin/**` **proves zero administrative privilege**. The Admin BFF requires:

- SSO/MFA and step-up authentication matched to action sensitivity.
- Action-specific scopes/roles (e.g., `admin.audit.read` and `admin.orders.refund`), **deny by default**.
- Resource-level authorization checking tenant scope, data ownership, and separation of duties (SoD) where mandated.
- CSRF enforcement whenever cookie sessions are used in an admin browser UI.
- Network isolation, TLS, operator/action/approval audit logs, and dedicated rate limits.
- Export row caps, PII redaction, pagination, masking, and report TTLs.
- Independent authentication/authorization in downstream domain services—never trust `X-Is-Admin: true`.

### 11.1. Spring Security for a Bearer-Token `admin-bff`

Example for an admin client **using bearer headers exclusively**:

~~~java
package demo.adminbff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class AdminBffSecurityConfig {

    @Bean
    SecurityWebFilterChain adminSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/admin/audit/**")
                        .hasAuthority("SCOPE_admin.audit.read")
                        .pathMatchers(HttpMethod.POST,
                                "/admin/orders/*/refund")
                        .hasAuthority("SCOPE_admin.orders.refund")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                // Applies only to bearer-only APIs; browser-cookie admin
                // must use an explicit CSRF/session policy.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

This snippet illustrates fine-grained matchers per action. For URLs like `/admin/orders/123/refund`, verify Spring path-pattern behavior on your exact version; **never treat route path matching alone as sufficient**. The JWT decoder must verify issuer, audience, and scopes, and the backend must still verify whether order 123 is eligible for a refund under business rules.

If the admin UI is a cookie-session browser app, use an OAuth BFF login flow like web's—with **stronger MFA and CSRF**—rather than copying `csrf.disable()` from the bearer-only example. Never mix cookie sessions and bearer auth on the same path without explicit rules separating them.

### 11.2. Admin Routing and Data Isolation Must Be Genuine

Reasons to isolate `admin-bff`:

- Never send PII, audit trails, or admin metadata inside web/mobile DTOs even if the UI hides them.
- Never reuse a token with `aud=mobile-api` to call an admin resource server.
- Never fall back to `web-bff` when an admin route misses.
- Maintain separate release cadences, approvals, and audit policies decoupled from customer UI releases.

Verify network and service-identity isolation through connectivity policies, not merely service names or URL prefixes.

## 12. BFFs Specialize for the UI Without Breaking Domain Boundaries

### 12.1. Appropriate Responsibilities Inside a BFF

| Task | Web BFF | Mobile BFF | Admin BFF |
| --- | --- | --- | --- |
| Adapt pagination into view models | Yes | Yes, smaller pages | Yes, larger bounded pages |
| Combine catalog + recommendations | Yes | Yes, compact payload | Rarely needed |
| Select display fields | Yes | Yes | Yes, permission-gated |
| Handle client-specific auth/tokens | Cookie session | Bearer JWT | SSO/role/MFA |
| Format user-friendly domain errors | Yes | Yes | Yes + audit reference |
| Alter domain transactions / pricing logic | **No** | **No** | **No** |
| Write directly to domain databases | Avoid | Avoid | Avoid |

### 12.2. Avoid Pulling the Whole Business Core Into BFFs

Anti-pattern:

~~~text
mobile-bff:
  - calculates prices and taxes itself
  - updates inventory directly
  - initiates bank transfers
  - confirms orders
~~~

When web BFF and admin BFF each grow their own copies of those rules, you end up with **three diverging sources of truth**, producing inconsistent totals and security gaps. Domain services must own data and transactions; BFFs orchestrate and compose already-authorized data.

### 12.3. Never Turn “Data Shaping” Into a Privacy Leak

Suppose mobile needs only `displayTotal`, while the domain response includes `internalCost`. Do not pass the full JSON and ask the mobile app to ignore `internalCost`; **construct a trimmed DTO on the server**. When composing multiple services, verify the caller is authorized for every upstream source rather than using an overly broad service token for the entire BFF.

## 13. Building an Aggregation Endpoint with WebFlux `WebClient`

A BFF can cut round trips between frontend and backend. Suppose the mobile home screen needs:

~~~text
GET /v1/home
  → GET /catalog/featured
  → GET /catalog/categories
  → JSON {"featuredSkus": [...], "categories": [...]}
~~~

Instead of mobile issuing two sequential requests over 4G, `mobile-bff` makes **two parallelizable downstream calls** and returns one compact DTO. In exchange, the BFF takes on **fan-out latency, timeouts, failure amplification, and concurrency management**.

### 13.1. Designing Non-Sensitive Lab Payloads

Two sample public catalog upstreams:

~~~json
// GET /catalog/featured
{"skus":["SKU-A1","SKU-B2"]}
~~~

~~~json
// GET /catalog/categories
{"names":["books","accessories"]}
~~~

Mobile DTO:

~~~json
{
  "featuredSkus":["SKU-A1","SKU-B2"],
  "categories":["books","accessories"]
}
~~~

Because both sample APIs serve **public catalog data**, the lab snippet needs no end-user token forwarding. For private order or customer data, attach a **properly scoped/audience-matched token** or mTLS/delegation and verify resource authorization; `WebClient` is not automatically protected by a Gateway route's `TokenRelay`.

### 13.2. WebFlux Java Controller for Mobile Home

`src/main/java/demo/mobilebff/MobileHomeController.java`:

~~~java
package demo.mobilebff;

import java.time.Duration;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@RestController
public class MobileHomeController {

    public record FeaturedResponse(List<String> skus) {}
    public record CategoriesResponse(List<String> names) {}
    public record MobileHomeResponse(
            List<String> featuredSkus,
            List<String> categories) {}

    private final WebClient catalogClient;

    public MobileHomeController(
            WebClient.Builder builder,
            @Value("${demo.catalog.base-url}") String baseUrl) {
        // Upstream URI is managed by approved deployment config,
        // never read from client query/header (prevents SSRF).
        this.catalogClient = builder.baseUrl(baseUrl).build();
    }

    @GetMapping("/v1/home")
    public Mono<MobileHomeResponse> home() {

        Mono<FeaturedResponse> featured =
                catalogClient.get()
                        .uri("/catalog/featured")
                        .retrieve()
                        .bodyToMono(FeaturedResponse.class)
                        .timeout(Duration.ofMillis(800));

        Mono<CategoriesResponse> categories =
                catalogClient.get()
                        .uri("/catalog/categories")
                        .retrieve()
                        .bodyToMono(CategoriesResponse.class)
                        .timeout(Duration.ofMillis(800));

        return Mono.zip(featured, categories,
                (f, c) -> new MobileHomeResponse(
                        f.skus(), c.names()))
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

Sample `application.yml` for the mobile BFF:

~~~yaml
server:
  port: 9082

demo:
  catalog:
    base-url: http://catalog-service:9091
~~~

This code is a **complete composition example**, not a finished production system. It still needs Spring WebFlux dependencies, security config, a catalog stub/upstream, HTTP client connect/read timeouts, status/error mapping, and tests. Never call `Mono.block()` on the WebFlux event loop.

### 13.3. What Happens When One Upstream Fails?

`Mono.zip(featured, categories)` emits only when both succeed; if either fails, it **fails the whole response** by default and may cancel the sibling call. Sometimes that is right (all data is mandatory), and sometimes it is not:

| Data | Policy to consider | Why |
| --- | --- | --- |
| Price/stock before checkout | Fail closed / never serve stale guesses | Transaction-critical data |
| Featured recommendations | Fall back to empty/cached list | Non-critical enhancement |
| User profile/permissions | Never fall back to guest or admin | Authorization risk |
| Admin audit trail | Fail closed and log reference | Never hide audit data failures |

To add fallback only for recommendations, attach `onErrorResume`/`onErrorReturn` **solely to that approved optional branch**—never add a catch-all turning auth or timeout errors into HTTP 200. For write APIs, enforce retry/idempotency keys and deadlines, avoiding fan-outs that split non-atomic mutations.

### 13.4. Fan-Out Latency and Load Amplification

For two parallel downstream calls:

\[
T_{\mathrm{home}}\approx T_{\mathrm{gateway}}
  + \max(T_{\mathrm{featured}},T_{\mathrm{categories}})
  +T_{\mathrm{compose}}
\]

This estimates parallel latency; actual latency includes queueing, connection pools, TLS, and CPU/GC. If a BFF fans out to **10 microservices**, one frontend request triggers **10 downstream requests**; at 1,000 frontend RPS, backends see 10,000 calls/s. Measure the fan-out factor and enforce concurrency and rate caps.

**Key takeaway:** A BFF can reduce client-side RTT and bandwidth, yet **it does not automatically reduce total backend load**. Optimize against real user experience and SLOs rather than counting browser HTTP calls alone.

### 13.5. Never Create an Open Proxy from a URL Parameter

Wrong:

~~~java
// Never use client input as an arbitrary HTTP target.
String target = request.getQueryParams().getFirst("url");
return webClient.get().uri(target).retrieve().bodyToMono(String.class);
~~~

Callers could probe cloud metadata endpoints, management listeners, or internal admin services, or exfiltrate access tokens to external hosts. BFFs must call only **allowlisted backends**, validate redirects and DNS resolution if dynamic targets exist, and never build downstream URIs from unverified `Host` or `X-Forwarded-Host` headers.

## 14. Localhost Lab with Three BFF Stubs

To watch routing reach the exact target service, run three instances of **the same echo application** with different configurations. This is a **learning stub** with no auth or business data; never expose it publicly as a production BFF.

### 14.1. Spring Boot WebFlux Stub

Dependencies example: `spring-boot-starter-webflux` with a matching Spring Boot version.

`src/main/java/demo/bffstub/BffStubApplication.java`:

~~~java
package demo.bffstub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BffStubApplication {
    public static void main(String[] args) {
        SpringApplication.run(BffStubApplication.class, args);
    }
}
~~~

`src/main/java/demo/bffstub/BffStubController.java`:

~~~java
package demo.bffstub;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BffStubController {

    private final String appName;
    private final AtomicLong requests = new AtomicLong();

    public BffStubController(
            @Value("${demo.bff.name}") String appName) {
        this.appName = appName;
    }

    @GetMapping("/whoami")
    public Map<String, Object> whoami(ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("bff", appName);
        result.put("path", request.getPath().value());
        result.put("method", request.getMethod().name());
        result.put("channelMarker",
                request.getHeaders().getFirst("X-Lab-Channel"));
        result.put("untrustedUserId",
                request.getHeaders().getFirst("X-User-Id"));
        result.put("requestNumber", requests.incrementAndGet());
        return result;
    }
}
~~~

### 14.2. Starting the Three Instances

In three separate terminals inside the **BFF stub project**:

~~~bash
# Instance web
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9081 --demo.bff.name=web"

# Instance mobile
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9082 --demo.bff.name=mobile"

# Instance admin
./mvnw spring-boot:run \
  -Dspring-boot.run.arguments="--server.port=9083 --demo.bff.name=admin"
~~~

Depending on your shell and Maven wrapper, adjust argument quoting (PowerShell/cmd/Linux). You can also run three built JARs with `java -jar ... --server.port=... --demo.bff.name=...`. Each process maintains its own counter; **never hard-assert a fixed `requestNumber`** because it depends on prior test traffic.

Run the Gateway lab separately on port 8080 using the `bff-lab` profile from Section 7.

### 14.3. Positive Tests with `curl`

~~~bash
curl -i "http://127.0.0.1:8080/web/whoami" \
  -H "X-User-Id: forged-admin"

curl -i "http://127.0.0.1:8080/mobile/whoami" \
  -H "X-User-Id: forged-admin"

curl -i "http://127.0.0.1:8080/admin/whoami" \
  -H "X-User-Id: forged-admin"
~~~

Illustrative response for `/mobile/whoami`:

~~~http
HTTP/1.1 200 OK
X-Lab-Bff-Route: mobile-bff-lab
Content-Type: application/json

{"bff":"mobile","path":"/whoami","method":"GET",
 "channelMarker":"mobile","untrustedUserId":null,
 "requestNumber":1}
~~~

What to verify: the Gateway's route marker header, the exact BFF name, that `StripPrefix` rewrote the downstream path to `/whoami`, and that the spoofed `X-User-Id` is **absent** at the stub because the default filter stripped it.

### 14.4. Negative Tests

~~~bash
# No route in this fixture matches.
curl -i "http://127.0.0.1:8080/unknown/whoami"

# Path /web/ has no / handler on the stub;
# route may match, then backend returns 404.
curl -i "http://127.0.0.1:8080/web/"

# Backend stub only defines @GetMapping("/whoami").
# Gateway may forward POST, then backend rejects it.
curl -i -X POST "http://127.0.0.1:8080/mobile/whoami"
~~~

**These three cases are not equivalent:**

- `/unknown/whoami`: no Gateway route matches in this fixture, typically returning 404 if no fallback handler exists.
- `/web/`: the web `Path` predicate **matches**; the backend receives `/` and returns 404 because no handler maps `/`.
- `POST /mobile/whoami`: the Gateway route **does not restrict `Method`**, so it forwards `POST` and the backend returns 405. Never use this case to claim the Gateway enforced a `Method` predicate.

That is why tests must inspect **route markers and backend request captures**, not HTTP status codes alone.

### 14.5. Direct Access to the Stub

~~~bash
curl -i "http://127.0.0.1:9082/whoami" \
  -H "X-User-Id: forged-admin"
~~~

The stub echoes the spoofed header (having bypassed the Gateway), proving that Gateway default filters **do not protect a backend listening on an exposed port**. In production, block direct BFF access or require every BFF to authenticate and authorize requests independently of entry path.

## 15. Integration Testing Host-Based Routing with `WebTestClient` and `MockWebServer`

Manual `curl` checks build intuition, yet preventing regressions as new BFFs are added requires **repeatable HTTP integration tests in CI**. Run Gateway Server WebFlux on a random port alongside three `MockWebServer` stubs on random ports, asserting exact **Host → BFF target**, Path/Method matching, and header filtering.

### 15.1. Fixture Topology

~~~text
JUnit 5 + WebTestClient
      ↓ GET with specific Host
Gateway Server WebFlux (RANDOM_PORT)
  ├── Host=web.example.test      → MockWebServer WEB
  ├── Host=mobile.api.example.test, Path=/v1/**
  │                             → MockWebServer MOBILE
  └── Host=admin.api.example.test, Path=/admin/**
                                → MockWebServer ADMIN
~~~

This is an **unauthenticated routing test** isolating route selection from Spring Security/IdP. **Never** use a passing run of this class to claim the admin BFF is secured: a dedicated security suite must test scopes, cookies/CSRF, MFA, and backend resource authorization.

### 15.2. Dependencies for Gateway 4.3 + Spring Boot 3.5

Maven example (compatible Spring Cloud BOM):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

In the Java class below, `@AutoConfigureWebTestClient` uses the **Spring Boot 3.5** package. When upgrading to Spring Boot 4.x, check the updated test module/auto-configuration package—**not only the Gateway YAML prefix**. MockWebServer 5.x also changes package names; this sample pins MockWebServer 4.12.0.

### 15.3. Gateway Test Application

`src/main/java/demo/edge/EdgeGatewayApplication.java`:

~~~java
package demo.edge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EdgeGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(EdgeGatewayApplication.class, args);
    }
}
~~~

### 15.4. `application-bff-test.yml`: Three Test Routes Only

File `src/test/resources/application-bff-test.yml` for **Gateway 4.3 + Boot 3.5**:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveRequestHeader=X-User-Id
      routes:
        - id: web-bff-route
          order: -30
          uri: http://127.0.0.1:${test.web.port}
          predicates:
            - Host=web.example.test
          filters:
            - AddResponseHeader=X-Lab-Bff-Route,web-bff-route

        - id: mobile-bff-route
          order: -20
          uri: http://127.0.0.1:${test.mobile.port}
          predicates:
            - Host=mobile.api.example.test
            - Path=/v1/**
          filters:
            - AddResponseHeader=X-Lab-Bff-Route,mobile-bff-route

        - id: admin-bff-route
          order: -10
          uri: http://127.0.0.1:${test.admin.port}
          predicates:
            - Host=admin.api.example.test
            - Path=/admin/**
          filters:
            - AddResponseHeader=X-Lab-Bff-Route,admin-bff-route
~~~

**On Gateway 5.x:** nest `routes` and `default-filters` under `spring.cloud.gateway.server.webflux.*`; on Boot 4.x, update test imports/starters too. Never put both namespaces in one fixture and guess which wins.

If the main project defines extra Java `RouteLocator` beans, discovery routes, or default routes elsewhere, ensure **the `bff-test` profile loads only these three routes**; otherwise negative tests could hit a fallback route and return 200.

### 15.5. JUnit 5: Sending HTTP Through the Gateway and Recording Backend Calls

`src/test/java/demo/edge/BffRoutingTest.java`:

~~~java
package demo.edge;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = EdgeGatewayApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("bff-test")
@Execution(ExecutionMode.SAME_THREAD)
class BffRoutingTest {

    private static final MockWebServer WEB = startStub("web");
    private static final MockWebServer MOBILE = startStub("mobile");
    private static final MockWebServer ADMIN = startStub("admin");

    @Autowired
    WebTestClient client;

    @DynamicPropertySource
    static void registerStubPorts(DynamicPropertyRegistry registry) {
        registry.add("test.web.port", WEB::getPort);
        registry.add("test.mobile.port", MOBILE::getPort);
        registry.add("test.admin.port", ADMIN::getPort);
    }

    private static MockWebServer startStub(String name) {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setResponseCode(200)
                        .addHeader("Content-Type", "application/json")
                        .addHeader("X-Bff-Stub", name)
                        .setBody("{\"bff\":\"" + name + "\"}");
            }
        });
        try {
            server.start();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
        return server;
    }

    @AfterAll
    static void closeStubs() throws IOException {
        WEB.shutdown();
        MOBILE.shutdown();
        ADMIN.shutdown();
    }

    @Test
    void webHostGoesOnlyToWebBff() throws InterruptedException {
        int webBefore = WEB.getRequestCount();
        int mobileBefore = MOBILE.getRequestCount();
        int adminBefore = ADMIN.getRequestCount();

        client.get().uri("/bff/home")
                .header(HttpHeaders.HOST, "web.example.test")
                .header("X-User-Id", "forged-admin")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Lab-Bff-Route", "web-bff-route")
                .expectHeader().valueEquals("X-Bff-Stub", "web")
                .expectBody()
                .jsonPath("$.bff").isEqualTo("web");

        assertThat(WEB.getRequestCount()).isEqualTo(webBefore + 1);
        assertThat(MOBILE.getRequestCount()).isEqualTo(mobileBefore);
        assertThat(ADMIN.getRequestCount()).isEqualTo(adminBefore);

        RecordedRequest forwarded =
                WEB.takeRequest(1, TimeUnit.SECONDS);
        assertThat(forwarded).isNotNull();
        assertThat(forwarded.getPath()).isEqualTo("/bff/home");
        assertThat(forwarded.getMethod()).isEqualTo("GET");
        assertThat(forwarded.getHeader("X-User-Id")).isNull();
    }

    @Test
    void mobileHostAndPathChooseMobileBff()
            throws InterruptedException {
        int before = MOBILE.getRequestCount();

        client.get().uri("/v1/feed?page=1")
                .header(HttpHeaders.HOST, "mobile.api.example.test")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Lab-Bff-Route", "mobile-bff-route")
                .expectHeader().valueEquals("X-Bff-Stub", "mobile");

        assertThat(MOBILE.getRequestCount()).isEqualTo(before + 1);
        RecordedRequest forwarded =
                MOBILE.takeRequest(1, TimeUnit.SECONDS);
        assertThat(forwarded).isNotNull();
        assertThat(forwarded.getPath()).isEqualTo("/v1/feed?page=1");
    }

    @Test
    void adminHostAndPathChooseAdminBff()
            throws InterruptedException {
        int before = ADMIN.getRequestCount();

        client.get().uri("/admin/audit/events")
                .header(HttpHeaders.HOST, "admin.api.example.test")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Lab-Bff-Route", "admin-bff-route")
                .expectHeader().valueEquals("X-Bff-Stub", "admin");

        assertThat(ADMIN.getRequestCount()).isEqualTo(before + 1);
        RecordedRequest forwarded =
                ADMIN.takeRequest(1, TimeUnit.SECONDS);
        assertThat(forwarded).isNotNull();
        assertThat(forwarded.getPath())
                .isEqualTo("/admin/audit/events");
    }

    @Test
    void unknownHostHasNoBffRoute() {
        int webBefore = WEB.getRequestCount();
        int mobileBefore = MOBILE.getRequestCount();
        int adminBefore = ADMIN.getRequestCount();

        client.get().uri("/bff/home")
                .header(HttpHeaders.HOST, "unknown.example.test")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().doesNotExist("X-Lab-Bff-Route");

        assertThat(WEB.getRequestCount()).isEqualTo(webBefore);
        assertThat(MOBILE.getRequestCount()).isEqualTo(mobileBefore);
        assertThat(ADMIN.getRequestCount()).isEqualTo(adminBefore);
    }

    @Test
    void mobileHostCannotUseAdminPath() {
        int adminBefore = ADMIN.getRequestCount();
        int mobileBefore = MOBILE.getRequestCount();

        client.get().uri("/admin/audit/events")
                .header(HttpHeaders.HOST, "mobile.api.example.test")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().doesNotExist("X-Lab-Bff-Route");

        assertThat(ADMIN.getRequestCount()).isEqualTo(adminBefore);
        assertThat(MOBILE.getRequestCount()).isEqualTo(mobileBefore);
    }
}
~~~

### 15.6. Interpreting Test Results Accurately

- These tests **do not** prove web, mobile, or admin callers are authenticated; the stubs reply 200 to every downstream call. Their sole goal is **BFF selection**.
- An invalid `Host` returns 404 in **a fallback-free fixture**. Adding another route changes the expected route ID/target—never assume every negative case is 404.
- `WEB.takeRequest(...)` confirms the path stays unmodified on the host-based route, unlike the `StripPrefix=1` lab in Section 7.
- `X-Lab-Bff-Route` is solely a test marker; a route matching cleanly while security fails still requires dedicated security tests.
- `MockWebServer` counters prove requests never leaked into another BFF.
- Spoofed `X-User-Id` is stripped by `RemoveRequestHeader` on the tested route; **this does not prove every endpoint/handler scrubs headers**. In production, sanitize at the trusted edge and via an appropriate `WebFilter`.
- `@Execution(SAME_THREAD)` prevents parallel tests within this class from racing on shared counters and request queues. Other test suites must not share these three stub instances.
- Explicit 4.3 / Boot 3.5 configuration: when migrating to 5.x / Boot 4, update namespaces and imports before running.

### 15.7. Running and Confirming Actual Executed Test Count

~~~bash
./mvnw -Dtest=BffRoutingTest test
~~~

Verify the test runner reports **5 tests executed**, not “build successful / 0 tests.” With Gradle, Failsafe, or JUnit tags, adjust include patterns accordingly.

This is a **test template for learners to implement themselves**; Maven/Gradle suites were not executed in this lesson inside the repository, so do not mark academic QA checks as PASS from reading alone.

## 16. Dedicated Security Test Matrix per BFF

Passing route tests is **not enough** to deploy. Each BFF requires its own authentication and authorization suite using test tokens issued/signed in a test environment.

| ID | Request | Expected |
| --- | --- | --- |
| SEC01 | Unauthenticated browser calls `/bff/orders/42` | Login redirect or 401 per contract; zero private data leaked |
| SEC02 | Browser with valid session cookie, same-origin GET | BFF uses authorized client; downstream token has right audience |
| SEC03 | Browser POST missing CSRF token, valid cookie | Rejected; backend never called |
| SEC04 | Browser POST with valid CSRF token and permissions | Processed per contract |
| SEC05 | Web host's cookie sent to admin host | Never treated as admin session under Domain/host-only policy |
| SEC06 | Mobile request missing bearer token to `/v1/me` | 401; no private data forwarded |
| SEC07 | Validly signed mobile bearer with wrong `aud` | Rejected |
| SEC08 | Mobile token with right audience but missing `SCOPE_mobile.read` | 403 |
| SEC09 | Mobile sends `X-Is-Admin: true` | Grants zero admin roles |
| SEC10 | Admin missing `SCOPE_admin.audit.read` | 403; audit API not called |
| SEC11 | Admin has audit-read role, tries POST refund | Rejected without refund permission |
| SEC12 | User in one tenant tries accessing another tenant's resource | Backend checks ownership and rejects |
| SEC13 | Client sets `X-User-Id` / `X-Tenant-Id` | Gateway never relays as verified identity |
| SEC14 | Client spoofs admin `Host` | May match `Host` route in routing tests, yet **BFF authz still blocks** |
| SEC15 | Client connects directly to BFF/service port | Production network/mTLS policies block bypass |
| SEC16 | Admin export response contains out-of-scope PII | Server response strips unauthorized fields |
| SEC17 | Browser logs out; old session cookie replayed | Session invalidated per logout policy |
| SEC18 | Token refresh or session store fails | Never falls back to anonymous admin; clear error mapping |

**Especially SEC14:** do not try to “block every Internet request carrying the admin Host” at the predicate level when clients hit the same IP; a valid `Host` routing rule can match, yet **grants zero admin capability**. What you must prove is that the Security chain, MFA, backend scopes, network isolation, and data boundaries hold.

## 17. Cross-Cutting Policies: Shared Gateway or Per-BFF?

Spring Cloud Gateway provides many filter factories: header/path rewrites, `RequestRateLimiter`, `CircuitBreaker`, `Retry`, `TokenRelay` (under valid OAuth2 client setups), caching/response filters, and metrics. Never dump every filter into **one global `default-filters` list** across all BFFs without considering how browser, mobile, and admin differ.

### 17.1. Policy Placement Matrix

| Policy | Shared Edge / Gateway | Dedicated BFF | Domain service |
| --- | --- | --- | --- |
| TLS termination, `Host` allowlist | Yes | Receives over private link by default | Verify service-to-service TLS as needed |
| `Host`/`Path` routing | Yes | Internal use-case routes | Domain endpoints |
| Anti-header-spoofing | Scrub client-controlled headers | Never trust unverified metadata | Never trust raw headers outside trust boundary |
| Browser OAuth login/cookies | Route to web BFF; do not manage BFF sessions | **Web BFF** confidential client + CSRF | Validate audience-matched tokens |
| Mobile bearer JWT | Optional coarse validation at edge | **Mobile BFF** validates scopes/audience | Resource-level authorization |
| Admin SSO/MFA/roles | Edge enforces perimeter only | **Admin BFF** enforces use-case authz | Verify object/transaction permissions |
| Rate limiting | Coarse site/client edge quotas | Per-user/plan/action quotas | Domain quotas / idempotency |
| Retries / circuit breakers | Transport/route level where safe | Use-case fan-out budgets and fallbacks | Business retries / transactions |
| Caching | Public responses with cache contracts | User-aware data shaping/caching | Source of truth / ETags |
| Observability | Route IDs, latency, upstream health | Screen SLOs, fan-out counts, view-model errors | Domain transaction metrics |

### 17.2. Per-Frontend Rate Limiters

Each BFF sees a different traffic profile:

- **Web checkout:** limit per authenticated user/account; curb bots without breaking login/callback flows.
- **Mobile feed:** quota by verified principal/plan, optionally augmented with verified device-risk signals. Never treat self-declared `X-Device-Id` as identity.
- **Admin export/refund:** stricter quotas—rate limits, concurrency caps, approvals, and auditing keyed by operator and tenant/action.

When using Gateway Server WebFlux `RequestRateLimiter`, configure a trustworthy `KeyResolver`. Example principal-based key:

~~~java
package demo.edge;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class RateLimitKeys {

    @Bean
    KeyResolver authenticatedPrincipalKeyResolver() {
        return exchange -> exchange.getPrincipal()
                .map(principal -> principal.getName())
                .switchIfEmpty(Mono.just("anonymous"));
    }
}
~~~

This is a **sample resolver**, not a complete policy. With a session-backed browser BFF, the edge Gateway in front **may have no authenticated OAuth principal**, causing an edge-level resolver to see `anonymous` for many web sessions. For per-user web quotas, enforce the limiter inside **`web-bff` after session authentication** or use trusted principal propagation (never raw headers). For native mobile bearer tokens, edge enforcement works when the edge is configured as a genuine Resource Server.

Never build rate-limit keys from untrusted `X-User-Id`, `X-Tenant-Id`, or `X-Forwarded-For` headers. In-memory quota state across replicas multiplies quotas by node count; Redis/clustered stores require explicit failure policies when storage is unreachable.

### 17.3. Circuit Breakers and Retries per Downstream, Not Blindly for “Every Request”

| Operation type | Retry? | Fallback? |
| --- | --- | --- |
| Idempotent public catalog GET | Allowed, bounded attempts + deadline | Freshness-checked cached data |
| User profile / private order GET | Restricted if backend contract permits | Never serve another user's profile or fake data |
| Checkout / payment POST | Never retry blindly | Require idempotency key and explicit transaction state |
| Admin refund / disable account | Never retry carelessly | Fail closed + audit/escalation |
| Recommendations widget | Light retry acceptable | Empty list / last-known-good if contract permits |

A BFF's SLO budget must account for downstream attempts. If a BFF aggregates three upstreams and each retries three times, one UI request can generate **9 attempts**—before counting edge retries. Enforce a **cross-layer retry budget**, overall deadlines, and circuit breakers for flaky upstreams.

Never put a `Retry` filter at the edge and let the BFF re-issue side-effecting `POST` calls without an idempotency contract.

### 17.4. CORS: Browser vs. Native

Same-origin browsers on `https://web.example.test` calling `/bff/**` avoid most CORS complexity. If the UI sits on `https://app.example.test` while the BFF sits on `https://web.api.example.test`, requests are **cross-origin** despite sharing a site: configure CORS explicitly with allowlisted origins, methods, headers, and credentials.

For cookie sessions:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Never use `Access-Control-Allow-Origin: *` when credentials are allowed.** Browsers also require matching `fetch` credentials modes and `SameSite`/`Secure` cookie flags. CORS never stops `curl`, native mobile apps, or service-to-service callers; it **is not authentication**.

Native apps are unaffected by browser CORS preflights. Never try to “fix a mobile bearer 401” by randomly disabling CORS, CSRF, or security; inspect JWT audience, scopes, TLS, token expiry, or network connectivity instead.

### 17.5. Caching Scoped to Data Sensitivity

| Response | Cache policy to consider | Risk |
| --- | --- | --- |
| Public catalog featured | Short CDN/BFF TTL, ETag | Stale inventory or prices if misused |
| Mobile public categories | ETag, conditional GET | Older apps require compatible schemas |
| Private web cart/orders | `Cache-Control: private, no-store` by sensitivity | Cross-user cache leaks |
| Admin audits/exports | Typically `no-store` | PII / security audit exposure |
| User-specific recommendations | Keyed on verified principal/tenant when approved | Cross-user data leaks |

Never key caches solely on path when responses depend on cookies, tokens, or tenants. Distinguish HTTP caches, Gateway `LocalResponseCache` (if enabled and eligible), distributed BFF caches, and domain caches—each has **different invalidation, auth sensitivity, and consistency semantics**.

### 17.6. Service Discovery and Workload Identity

In Kubernetes you can address internal DNS such as `http://mobile-bff:9082`; with Spring Cloud discovery, Gateway Server can route `lb://mobile-bff` when paired with Spring Cloud LoadBalancer/discovery integration. That handles **service resolution**, not permission to call the BFF.

Enforce:

- BFF services never exposed directly to the Internet when the public edge is the intended entry point.
- `NetworkPolicy`/security groups and mTLS where required across edge → BFF → domain services.
- Gateway trusts forwarded headers only from controlled proxies.
- BFFs ignore client-supplied `X-Authenticated-User` or `X-Client-Type`.
- Backends verify audience-matched bearer tokens or approved workload identities.

## 18. BFF Performance: When Another Hop Helps vs. Hurts

### 18.1. Latency Model

If a browser or mobile app calls three backends **sequentially**:

\[
T_{\mathrm{client\;seq}}
\approx T_A+T_B+T_C+3T_{\mathrm{client\;RTT}}
\]

If a BFF calls those three backends **in parallel** and returns one response:

\[
T_{\mathrm{BFF}}
\approx T_{\mathrm{client\;RTT}}
 +T_{\mathrm{edge}}
 +\max(T_A,T_B,T_C)
 +T_{\mathrm{compose}}
\]

This is an **approximation**, not a production benchmark. It shows BFFs pay off when frontend RTT is high and backend-to-backend latency is low. However, if a BFF generates excessive calls or suffers tight concurrency limits, p99 latency can still end up worse than direct client calls.

### 18.2. SLOs Differ Across the Three Application Types

| Client | Metrics to track |
| --- | --- |
| Web checkout | UI-linked Core Web Vitals, checkout API p95, retries/double-submits, auth/session failures |
| Mobile feed/home | Bytes/response, client RTT count, p95/p99 on weak networks, offline/cache hit rates |
| Admin audit/refund | Correctness, 403/401 policy enforcement, audit completeness, export durations, sensitive error rates |

Never impose one uniform p99 target across every BFF and ignore their differences. Large admin exports take longer and belong in async jobs/pagination with explicit status tracking, whereas mobile home requires low latency and lean payloads.

### 18.3. Batching, Pagination, and Streaming

Key techniques:

- **Pagination/cursors:** keep mobile pages small; sign/validate cursors if they encode permissions or filters.
- **Batch fetching:** aggregate bounded lists of SKUs/IDs in one BFF call to avoid `N+1` fan-outs.
- **ETag / `If-None-Match`:** save bytes on infrequently changing lists without leaking user-specific caches.
- **Compression:** balance CPU vs. bandwidth by payload type and TLS posture.
- **Streaming/SSE:** adopt only when real-time UI updates demand it; manage event-loop health, backpressure, and long-lived connections carefully.
- **Async jobs:** run heavy admin exports as background jobs with safe polling/webhooks instead of holding an HTTP request open for minutes.

Never feed thousands of unbounded items into `Mono.zip` to “maximize parallelism.” Enforce concurrency budgets, right-sized connection pools, per-upstream timeouts, and cancellation when clients disconnect.

### 18.4. Never Duplicate Business Logic Across Three BFFs to “Optimize”

When shared rules (final pricing, order visibility, tax calculation) are duplicated into web, mobile, and admin BFFs, consistency bugs cost far more than the saved RTT. Domain services should expose stable APIs; each BFF chooses only **presentation and client-specific orchestration**.

## 19. Observability and BFF Ownership

A single distributed trace may traverse:

~~~text
browser → ingress → edge-gateway (route=web-bff-route)
        → web-bff (useCase=checkout-summary)
        → orders-service
        → inventory-service
~~~

Correlate across hops:

| Layer | Suggested spans / metrics | What to avoid |
| --- | --- | --- |
| Edge | route ID, status, duration, target BFF, retries | Logging JWTs, cookies, or raw queries |
| BFF | use-case, frontend version bucket, fan-out count, cache hit, p99 | High-cardinality user IDs or tokens in labels |
| Backend | business operation, outcome, DB latency, authz decision | Leaking PII or domain secrets |
| Security | 401/403 reason category, issuer/audience failures, CSRF failures | Logging raw tokens or session IDs |

Some log formats record `traceId` and `routeId`, though **field names are implementation conventions** rather than guaranteed outputs across every Gateway release. Use OpenTelemetry, Micrometer, and Reactor context propagation suited to your stack, and verify trace context propagates across `WebClient` fan-outs.

### 19.1. Bound Cardinality on Frontend Version Labels

Never put build numbers, beta hashes, user IDs, or full `User-Agent` strings into metric labels. To compare p95 between old and new mobile versions, bucket by `apiMajorVersion=1|2` or curated release groups. Unbounded labels blow up Prometheus cardinality and leak data.

### 19.2. Every BFF Needs a Clear Owner

Example:

| BFF | Primary owner | Shared dependencies |
| --- | --- | --- |
| `web-bff` | Web experience team | Platform auth/TLS/metrics standards |
| `mobile-bff` | Mobile team | Domain API contracts, schemas/versioning |
| `admin-bff` | Back-office team + Security review | Audit/RBAC/PII compliance |

The Platform/Gateway team owns edge routing, TLS, networking, shared filters, and platform SLOs; **frontend teams deploy their own DTOs independently**. Any source-of-truth change in domain services still requires coordination with domain owners.

### 19.3. Using Traces to Catch Misrouted Requests

If the mobile app receives the web BFF's response shape:

1. Check the public `Host` and path received by the Gateway.
2. Check which route ID actually matched, along with default/route filters and route order.
3. Check whether `mobile-bff` or `web-bff` actually received the call.
4. Check cache keys, CDN/Ingress rewrites, and route-refresh revisions.
5. Check app version and contract tests.

Never guess from HTTP 200: both BFFs can return 200 with completely different schemas.

## 20. When to Adopt a BFF vs. Keeping a Shared Gateway

The BFF pattern trades **coupling and ownership** for frontend-specific optimization. Never adopt it dogmatically merely because you run microservices.

| Scenario | Better fit | Reason |
| --- | --- | --- |
| Single frontend, few endpoints, payloads match domain APIs | Shared Gateway + domain services | Avoids deploying an extra pass-through service |
| Web and mobile share one contract, differing only in layout/CSS | Usually no separate BFF needed yet | Frontends format locally without backend sprawl |
| Browser needs confidential OAuth client keeping tokens out of JS | **Browser BFF** makes sense | Session cookies + server-side token storage |
| Mobile needs lean DTOs merging 4–5 calls into one | **Mobile BFF** worth considering | Saves client RTT and bandwidth |
| Back-office needs distinct RBAC/MFA/audit/exports | Separate **Admin BFF** worth considering | Isolates privilege scope and change cadence |
| Public API shared by many third parties | API Gateway + versioned general API | Avoids forcing partners onto UI-specific DTOs |
| Frontend already uses GraphQL with field-selecting resolvers | Evaluate before adding a BFF | May deliver similar shaping; still requires auth/security |
| BFF merely passes through identical URIs with no shaping/auth | Route directly via Gateway | Eliminates an unnecessary network hop |
| Multiple frontend teams deploying independently against shared backends | Per-experience/team BFF | Reduces contention over shared contracts |

### 20.1. Operational Costs Introduced by Each BFF

Every new BFF adds:

- Builds, CI/CD pipelines, vulnerability scanning, and dependency patching.
- DNS/service discovery, TLS/mTLS, secrets, and network policies.
- On-call rotations, logs/traces/metrics, SLOs, and capacity planning.
- API contracts, backward compatibility, canaries, and rollbacks.
- Security reviews for OAuth/session/bearer token flows.
- Testing for aggregation, retries/fallbacks, and user-scoped caching.

If those costs outweigh UX gains, **do not split solely to follow a pattern name**. You can begin with a BFF module/controller inside an existing app and extract a separate deployable once boundaries and ownership stabilize.

### 20.2. BFF and GraphQL Are Not Mutually Exclusive

GraphQL lets clients pick fields and reduce over-fetching, which can reduce the need for hand-crafted BFF DTOs. Even so:

- GraphQL still needs endpoint auth, query cost/depth/rate limits, and resolver `N+1` guards.
- Browsers still need an OAuth/session/CSRF strategy; GraphQL **does not protect tokens on its own**.
- Admin and mobile clients still have distinct permissions and SLOs even over one GraphQL schema.

Decide based on contracts, ownership, and threat models—not as a binary “GraphQL or BFF” choice.

## 21. Migrating from a Shared API to BFFs

Suppose every client currently calls:

~~~text
https://api.example.test/api/orders/{id}
https://api.example.test/api/catalog/items
https://api.example.test/api/profile/me
~~~

Target state:

~~~text
https://web.example.test/bff/orders/{id}
https://mobile.api.example.test/v1/home
https://admin.api.example.test/admin/audit/events
~~~

Do not cut over all traffic at once. Follow a staged plan:

### 21.1. Step 1 — Map Clients and Contracts

- Gather request patterns by **verified client type** from approved analytics/telemetry.
- Document endpoints, methods, auth flows, scopes, payload sizes, p95/p99, and app versions.
- Classify public, private, and regulated data, business operations, and caching policies.
- Identify endpoints suffering from over-fetching or chatty round trips.
- Assign team ownership and on-call for each frontend.

Never classify users from a client-supplied `X-Client-Type` header as if it were verified; use trusted identifiers/release channels and keep tokens/PII out of logs.

### 21.2. Step 2 — Introduce Minimal Web/Mobile/Admin BFFs

1. Pick one high-value use case, such as mobile home aggregation.
2. Create the new DTO and endpoint in `mobile-bff` without duplicating domain business logic.
3. Add non-overlapping routes at the public edge alongside legacy routes.
4. Enforce client-appropriate auth at the BFF while domain services still verify permissions.
5. Add contract tests and negative auth tests before onboarding live clients.

### 21.3. Step 3 — Shift Traffic Incrementally

- Canary 1%→10%→50%→100% or roll out by defined app release cohorts.
- Keep legacy routes alive for the required backward-compatibility window.
- Watch route selection, BFF/downstream errors, p99, cache/fan-out behavior, and user outcomes.
- Never silently fall back across backends when tokens or scopes are incompatible.
- Keep a rollback route revision ready and verify the full DNS/TLS/Host/forwarding chain.

### 21.4. Step 4 — Upgrade Authentication at the Right Layer

For web browsers:

- Never move tokens from `localStorage` into sessions merely by rewriting headers at the Gateway. Implement **confidential-client authorization-code login**, sessions, CSRF, refresh, and logout.
- Use `TokenRelay` if `web-bff` uses Gateway routes to resource servers with properly configured OAuth2 clients.
- Verify downstream token audiences; use token exchange when audiences differ.

For mobile:

- Keep native public-client Authorization Code/PKCE flows (or approved strategy); never force browser session cookies onto native just for “uniformity.”
- Keep older still-active app versions supported throughout the transition.

For admin:

- Enforce SSO/MFA/step-up auth, action-level scopes, and admin BFF auditing before migrating endpoints.
- Never merely rename `/api/admin/**` to `/admin/**` and assume it is secure.

### 21.5. Step 5 — Retire Legacy APIs Safely

Retire old routes only when:

- No dependent clients remain (or end-of-support was formally announced).
- No auth/identity bypass remains open on legacy routes.
- Contract and observability reports confirm the new web/mobile/admin flows.
- Any rollback path preserves strict permission boundaries.
- Cache/DNS/session TTLs and CDN behavior are accounted for.

**Easy-to-miss detail:** an app store mobile release can remain active for months. Never assume all clients upgrade instantaneously like a web SPA.

## 22. Troubleshooting BFF Routing and Security

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Web OAuth login redirects to `/login` missing `/web` | Path-based `StripPrefix` + wrong public base URL | Redirect URI, `Forwarded-Prefix`, cookie `Path`; prefer host-based |
| OAuth callback returns 404 | Gateway fails to route `/login/oauth2/code/**` to `web-bff` | Host route predicates, route inventory, IdP redirect allowlist |
| Browser sessions fail across replicas | In-memory `WebSession`/authorized client or unstable cookie key | Session store, token persistence, sticky/Redis policy |
| Browser POST to web BFF returns 403 | Missing/mismatched CSRF token | Cookie/token repository, header, Origin/`SameSite`; never disable CSRF blindly |
| Login succeeds, downstream returns 401 | `TokenRelay` lacks OAuth2 client config or wrong token audience | Authorized client, `TokenRelay` factory, JWT audience |
| Mobile request has bearer yet returns 401 | Wrong issuer/JWKS/audience or expired token | JWT decoder, public-client PKCE, scopes |
| Mobile request returns 403 | Missing `SCOPE_mobile.read/write` | Authority mapping / route policy |
| Correct admin Host still returns 403 | Admin BFF missing authority or MFA policy | `SecurityWebFilterChain`, IdP roles, resource permissions |
| Spoofed admin Host routes to admin BFF | `Host` predicate does not authenticate clients | Verify RBAC/MFA/network isolation, not `Host` alone |
| Wrong BFF returns 200 | Overlapping Host/Path routes or broad fallback | Response marker, backend stub, route order |
| `StripPrefix=1` strips too much | Prefix layout mismatched or double-rewritten | `RecordedRequest` path and filter list |
| Mobile GET `/v1/home` returns 502 | Upstream catalog unreachable | HTTP client logs, DNS, timeouts, fan-out |
| Mobile payload bloated | Returning raw domain DTO | DTO shaping, bytes/response, contract tests |
| p99 spikes after adding BFF | Extra hop, wide fan-out, pool/GC, retries | Traces, downstream attempts, per-use-case p99 |
| Public catalog cached wrongly | Improper cache keys, `Vary`, or TTL | `ETag`, `Cache-Control`, CDN, user-specific variants |
| User A sees User B's data | Path-only cache key or authz bypass | Disable unsafe cache; audit authz and tenant tests |
| Admin audit drops events | BFF fallback hides downstream failures | Fail-closed policy, audit pipeline, SLOs |
| Browser `fetch` blocked by CORS | Misconfigured cross-origin + credentials | Origin allowlist, preflight, `SameSite`, actual GET |
| Changing mobile `X-App-Type` alters access | Client-controlled header used for authz | Separate route metadata from verified principal |
| Cookies sent to unintended subdomains | Cookie `Domain` too broad | Host-only cookies, `Secure`/`HttpOnly`/`SameSite` |
| `TokenRelay` works on one node, fails on others | Unshared authorized-client store | Token/session persistence, replica routing |
| Spoofed `X-User-Id` reaches downstream | Route missing default filter or bypassed directly | Edge scrub, effective Gateway filters, network |
| `/actuator/gateway/routes` omits BFF host route | Wrong config prefix/starter or wrong profile | BOM, active profile, effective runtime routes |
| Test returns 404 on wrong Host yet leaks data | Another controller/fallback or direct backend path | Recorded backend calls, security tests |

### 22.1. Ordered Debugging Workflow

1. **Identify the client type** calling in and its true business and authorization requirements.
2. **Inspect the public request:** scheme, `Host`, path, method, `Origin`, and auth mode.
3. **Confirm Gateway routing:** verify routes materialized under the right prefix/version and which route ID matched.
4. **Confirm the target BFF** via backend request capture—never status 200 alone.
5. **Verify security at the BFF:** cookie session/CSRF or bearer JWT/scopes/audience?
6. **Verify downstreams:** resource server token audience, domain permissions, fan-out count.
7. **Inspect responses and caching:** UI-appropriate DTO, zero leaked private fields, proper `Vary`/`ETag`.
8. **Inspect metrics and traces:** per-route/use-case p95/p99, retries, timeouts.
9. **Inspect topology:** edge forwarded headers, DNS/TLS, service discovery, `NetworkPolicy`.
10. **Run the regression suite** covering positive and negative web/mobile/admin cases before deploying.

Never “fix” a Host/path issue by putting `Path=/**` on all BFFs, or “fix” a 401 by deleting Spring Security. Those shortcuts turn routing bugs into cross-client authorization breaches.

## 23. Implementation Checklist by Application Type

### 23.1. Architecture and Routing

- [ ] Clearly distinguish **shared Gateway**, **experience BFFs**, and **domain services**.
- [ ] Document concrete criteria for splitting a BFF: diverging contracts, session/auth model, SLOs, team ownership.
- [ ] Plan Host/Path layout explicitly; prefer same-origin/host-based when a browser BFF owns OAuth callbacks.
- [ ] Assign unique route IDs, clear ordering, and zero wildcards that could misroute admin/mobile.
- [ ] Test the exact Gateway WebFlux 4.x or 5.x namespace; never mix versions.
- [ ] Add `StripPrefix`/`RewritePath` only when required by downstream contracts; recorded-path tests pass.
- [ ] Verify the `Host` predicate is **never treated as authentication**.
- [ ] Never route or bypass security using client-supplied `X-Admin`, `X-Client-Type`, or `User-Agent`.
- [ ] Enforce network isolation so clients cannot bypass Gateway/BFF via internal ports.
- [ ] Verify public DNS/TLS/SNI, forwarded host/proto, and proxy trust against real ingress.

### 23.2. Browser/Web BFF

- [ ] Confidential OAuth client runs server-side; access/refresh tokens never reach browser JS.
- [ ] Session cookies enforce `Secure`, `HttpOnly`, `SameSite`, `Path`, host scope, and proper TTLs.
- [ ] CSRF protection covers all state-changing browser requests, including same-site subdomains.
- [ ] OAuth redirects/callbacks preserve public `Host`, scheme, and prefix behind reverse proxies.
- [ ] `TokenRelay` enabled only alongside valid OAuth2 client registrations and authorized-client persistence.
- [ ] Downstream access tokens match target audiences/scopes; use token exchange when needed.
- [ ] Multi-replica session/token storage, logout, invalidation, and rotation tested.
- [ ] Private carts/orders never cached across users; appropriate response headers set.
- [ ] Static UI assets and login endpoints allowlisted; private `/bff/**` endpoints require auth.

### 23.3. Mobile BFF

- [ ] Native OAuth clients use Authorization Code/PKCE per platform best practices.
- [ ] Mobile BFF Resource Server validates issuer, signature, expiry, audience, and scopes.
- [ ] Browser cookie/CSRF settings never copied blindly onto bearer-only APIs.
- [ ] Mobile DTOs stay compact with pagination/cursors/versioning covering supported app releases.
- [ ] Timeouts, bounded fan-out, ETag caching, and idempotent retries handle weak networks.
- [ ] `X-Device-Id` and `X-App-Version` never treated as verified identity.
- [ ] Backward compatibility tested across still-active mobile app versions.

### 23.4. Admin BFF

- [ ] SSO/MFA/step-up auth matched to sensitivity, with per-action scopes and roles.
- [ ] No accidental `/admin/**` `permitAll()` wildcard.
- [ ] Domain services verify resource/tenant permissions; BFF never derives roles from headers.
- [ ] CSRF enforced on browser-cookie admin UIs, distinct from bearer-only endpoints.
- [ ] Full audit logging for refunds, account disables, exports, and sensitive reads.
- [ ] PII masking, export caps, `no-store`, resource ownership, and network isolation enforced.
- [ ] Negative tests cover under-scoped admin tokens and spoofed Internet `Host` headers.

### 23.5. Operations and Quality

- [ ] HTTP routing tests with backend stubs verify target BFF and route markers.
- [ ] Dedicated security tests cover authn/authz, CSRF/CORS, direct access, and header spoofing.
- [ ] Every BFF has SLOs, dashboards, alerts, on-call ownership, and a rollback plan.
- [ ] Fan-out per request, downstream retries, p95/p99, and cache hit rates measured.
- [ ] Raw JWTs, cookies, user IDs, and tenant IDs excluded from metric labels.
- [ ] Dynamic routes require approval, URI allowlists/SSRF checks, and revision audits.
- [ ] Canaries track app version / route ID; rollbacks never cross incompatible token audiences.
- [ ] Unit/integration tests never target live Internet backends; use ephemeral ports.
- [ ] CI confirms **actual test execution counts**, rejecting green builds with 0 tests.
- [ ] API changes maintain both contract and security backward compatibility.

## 24. Hands-On Exercises

### Exercise 1 — Designing Routes for Four Client Types

A system serves browser, mobile, admin, and partner API clients. Propose:

- A `Host`/`Path` namespace for each client type.
- Route predicates, IDs, `order`, and BFF upstream targets.
- Security policy per service.
- Headers that must be scrubbed at the edge/Gateway.
- 4 positive and at least 8 negative test requests.

**Hint:** A Partner API does not have to be a “partner BFF”; it may simply be a stable-contract public API. Do not lump partners into the mobile BFF merely because both use bearer tokens.

### Exercise 2 — Converting the Path-Based Lab to Host-Based

Starting from:

~~~text
GET /web/whoami    → port 9081 /whoami
GET /mobile/whoami → port 9082 /whoami
GET /admin/whoami  → port 9083 /whoami
~~~

Rewrite using:

~~~text
Host=web.example.test        GET /whoami
Host=mobile.api.example.test GET /v1/whoami
Host=admin.api.example.test  GET /admin/whoami
~~~

Update the stub mappings and tests. Prove **`StripPrefix` is no longer needed**, unknown hostnames match no route, and the mobile `Host` cannot reach the admin backend. Discuss why spoofing the admin `Host` is **not** enough to gain admin privileges.

### Exercise 3 — Building an Authenticated Web BFF

Against a test IdP:

1. Register a confidential OAuth2 client with a redirect URI matching the public hostname.
2. Configure `oauth2Login` and a `SecurityWebFilterChain` protecting `/bff/**`.
3. Configure `TokenRelay=` on a route to a test resource server.
4. Inspect browser network traces to verify **no access or refresh tokens appear in JS or `localStorage`**.
5. Verify session cookies and CSRF enforcement on `POST`.
6. Test logout, expired sessions, and requests with missing or forged CSRF tokens.

Never use a production IdP or real tokens in exercises; use test accounts/issuers and prevent logging raw secrets.

### Exercise 4 — Mobile Home Aggregation and Intentional Fallback

Building on `MobileHomeController`:

- Add a third optional recommendations API.
- If recommendations time out, return an empty list **only** for that optional field.
- If pricing or authorization APIs fail, never fall back to synthetic data.
- Benchmark sequential vs. parallel latency against local stubs.
- Bound concurrency and record downstream attempt metrics.
- Verify the response shape excludes internal fields.

### Exercise 5 — Protecting Admin BFF Against Spoofed `Host` and Wrong Tokens

Write a test:

~~~http
GET /admin/audit/events HTTP/1.1
Host: admin.api.example.test
Authorization: Bearer <token-aud-mobile>
X-Is-Admin: true
~~~

Expect the admin BFF to **reject** it because the token lacks the right audience/scope, even though the Gateway `Host` predicate matched. Add a test with a valid admin token missing `SCOPE_admin.audit.read` and another with the required scope. Verify the backend receives zero rejected requests.

### Exercise 6 — Testing for Cache Data Leaks

Create a private response containing distinct `customerName` values for two test users. Enable a test cache and prove:

1. User A's request never causes User B to receive User A's DTO.
2. Cache keys and tenant isolation work properly.
3. `Cache-Control` headers match private-data rules.
4. Logout and permission changes handle cached entries safely.

If you cannot prove all four conditions, **never enable caching for private data** just to shave latency.

### Exercise 7 — Drafting a Migration Plan with Rollback

Suppose mobile v1 still carries 20% of traffic while v2 adopts `/v2/home`. Draft a plan covering:

- Route/version compatibility matrix.
- Canary cohorts, telemetry, and SLOs.
- Safeguards against data or scope leaks between v1 and v2.
- Cache invalidation and rollback steps.
- Criteria for deprecating v1 and notifying client teams.

Never assume mobile users upgrade on release day.

## 25. Self-Check Questions

**1. Is BFF a `GatewayFilterFactory` in Spring Cloud Gateway?**

No. BFF is an **architectural pattern** creating experience-specific backends; Spring Cloud Gateway can route to BFFs or implement a proxy-heavy BFF itself.

**2. Why run a separate web BFF when a mobile API already exists?**

When web needs cookie sessions/confidential OAuth clients and page-oriented DTOs while mobile uses public OAuth + PKCE and compact payloads, both threat models and contracts diverge. If every API is identical, splitting two deployables may be unnecessary.

**3. Does routing via `Host=admin.api.example.test` grant admin privileges?**

No. Clients can set `Host` in many contexts; route predicates never replace JWT validation, SSO/MFA, RBAC, or domain resource authorization.

**4. Where should a browser OAuth BFF store access tokens?**

In a **secure server-side BFF/session store**, never returned to JavaScript. The browser holds a secure session cookie while the BFF attaches audience-matched tokens when calling resource servers.

**5. Does `TokenRelay=` automatically make any access token valid for downstream services?**

No. It relays the OAuth authorized client's token; resource servers still validate audience and scopes. If audiences differ, use token exchange or dedicated client registrations.

**6. Must native mobile apps reuse the browser BFF's session cookies?**

No. Native apps typically use OAuth Authorization Code + PKCE with bearer tokens, where the BFF acts as a Resource Server. Using cookies would require matching threat-model and CSRF controls rather than blind copying.

**7. Why does path-based `/web/**` sometimes break OAuth login?**

Because `StripPrefix` alters the downstream path while redirect URIs, cookie `Path`s, and public scheme/`Host` must align with the user-facing URL. Host-based routing avoids that rewrite layer.

**8. Why might `admin-bff` warrant its own service?**

Because its privileges, PII exposure, audit requirements, MFA, and release cadence differ from customer-facing web/mobile. Still, enforce authorization at both the BFF **and** domain services.

**9. Is a mobile endpoint using `Mono.zip` across two upstreams guaranteed to be twice as fast?**

No. It saves client RTT and parallelizes downstream calls, yet total latency depends on the slowest upstream, connection pools, CPU, fan-out, and error handling. Measure p95/p99 under representative load.

**10. Why never cache user-specific responses by path alone?**

Because the same path returns different data for different principals or tenants. Caching without proper identity scoping risks leaking one user's data to another.

**11. Should a BFF mutate domain business transactions directly?**

No. BFFs shape DTOs and orchestrate experience-level calls; domain services own business rules, transaction boundaries, and resource authorization.

**12. When a positive test returns 200 from the wrong BFF, what should you inspect?**

Inspect the effective `Host`/`Path`, Gateway route ID and `order`, backend request captures, and fallback routes. HTTP 200 does not prove a request reached the intended target.

**13. Is CORS alone enough to protect a browser BFF?**

No. Cookie sessions require CSRF defense; CORS is only a browser policy and neither replaces authentication nor blocks native or `curl` clients.

**14. When is a single shared Gateway sufficient?**

When client contracts are nearly identical, no distinct session/auth model or heavy data shaping is needed, and a BFF would add only a pass-through network hop. Weigh cost against benefit.

## 26. References

1. [Microsoft Azure Architecture Center — Backends for Frontends Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/backends-for-frontends): defines BFFs, problems with a single backend across frontends, UI-aligned ownership, deployment trade-offs, and web/mobile examples.
2. [RFC 10017 — OAuth 2.0 for Browser-Based Applications](https://www.rfc-editor.org/rfc/rfc10017.html): 2026 Best Current Practice; defines the confidential-client OAuth BFF, session cookies, server-side tokens, CSRF/XSS, and outbound proxy constraints.
3. [Spring Cloud Gateway Server WebFlux 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): `Host`, `Path`, `Method`, logical AND across predicates, URI templates.
4. [Spring Cloud Gateway WebFlux 4.2 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): reference for the `spring.cloud.gateway.routes` namespace and 4.x contract.
5. [Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html): OAuth2 Client registration, `TokenRelay=`, and authorized-client storage.
6. [Spring Cloud Gateway Server WebFlux — StripPrefix GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/stripprefix-factory.html): rewriting paths after route matching.
7. [Spring Cloud Gateway Server WebFlux — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html): `SecurityWebFilterChain`, OAuth2 client and resource-server integration.
8. [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): OAuth login with Spring WebFlux.
9. [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): token repositories and cookie/header CSRF defense.
10. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT validation in WebFlux.
11. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): authorization rules by request and principal.
12. [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client and request/response composition.
13. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing Gateway HTTP responses and assertions.
14. [OkHttp MockWebServer](https://square.github.io/okhttp/features/mockwebserver/): upstream stubs, recorded requests, and downstream call-count assertions.
15. [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/): object-level authorization, resource exhaustion, SSRF, and API security.

**Key takeaway:** **Backend for Frontend** is far more than routing on `X-Client-Type`. It is a deliberate decision to separate **data contracts, authentication/session models, and deployment ownership** across web, native mobile, and admin clients. Use Spring Cloud Gateway to route via **explicitly designed `Host`/`Path` rules**, keep browser OAuth BFF tokens server-side, verify bearer/PKCE flows properly in native mobile BFFs, and lock down admin BFFs with MFA, RBAC, and resource authorization. A well-built BFF gives each frontend **the right data in fewer round trips**, while keeping domain services as the source of truth, bounding fan-out/caching/timeouts, and proving with **both routing tests and security tests** that traffic never leaks across BFFs or users.
