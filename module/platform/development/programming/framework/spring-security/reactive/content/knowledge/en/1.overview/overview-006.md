# Application Models: Session-Based Browsers, Token-Based REST APIs, and Service-to-Service Calls

**Context:** Spring Security for **reactive applications using Spring WebFlux**, Java 17+, and Spring Boot 3.x. All three models can coexist in one system; the deciding factors are **who sends the request, how credentials are transmitted, and what state the server must maintain**.

## 1. Distinguishing the Three Models

| Model | Primary subject | Credential sent per request | Authentication state management | Typical use cases |
| --- | --- | --- | --- | --- |
| Session-based browser | Human user via browser | Cookie containing **session ID** | Server stores `SecurityContext` in `WebSession`; browser holds only session identifier | Server-rendered web pages, BFF applications, admin dashboards |
| Token-based REST API | User or application calling the API | Header `Authorization: Bearer <access-token>` | API verifies the token per request; typically maintains no login session on the API | Mobile apps, OAuth2-based SPAs, public/partner APIs |
| Service-to-service (M2M) | A workload / backend application | Usually an OAuth2 access token, sometimes mTLS | Calling service acquires/manages tokens itself; receiving service verifies tokens | Orders calling Inventory, workers calling Billing, background jobs |

**Three non-synonymous concepts:** a cookie is a data transport mechanism; a session is server-side state; an access token is a credential for accessing resources. A browser can still call a REST API using a Bearer token, and a service can still use a session if designed that way, though those are not the typical choices.

In WebFlux, key components to know include `SecurityWebFilterChain` (security filter chain), `ServerHttpSecurity` (configuration DSL), `Authentication` (authenticated identity), `SecurityContext` and `ReactiveSecurityContextHolder` (security context bound to Reactor Context), `WebSession` (web session), and OAuth2 Client / Resource Server components.

## 2. Session-Based Browser: Authenticating Users and Keeping Them Logged In

### 2.1 Request flow

1. Browser opens `GET /dashboard` while unauthenticated; security filters detect that the route requires authentication.
2. The application redirects to the login page (form login) or initiates OAuth2/OIDC login at an identity provider.
3. After verifying credentials, Spring Security creates `Authentication` and saves `SecurityContext` in `WebSession` via the session-based context repository.
4. The response sets a session identifier cookie, typically `SESSION`. The browser automatically sends this cookie on subsequent matching requests.
5. The server looks up the session, restores identity, and checks permissions. Upon logout, expiration, or session invalidation, the old cookie can no longer reconstruct an authenticated session.

**A session cookie should never contain passwords or the entire user object.** The session identifier cookie is solely a reference key to server-managed state. With multiple instances, an appropriate shared session store is needed, such as Spring Session + reactive Redis, or an alternative meeting operational requirements.

### 2.2 What must be protected

- **CSRF:** browsers automatically attach cookies; malicious pages can abuse this to send commands on the user's behalf. Spring Security WebFlux enables CSRF by default. For cookie-based POST/PUT/PATCH/DELETE requests, keep CSRF protection and submit a valid CSRF token. In WebFlux, the default repository for CSRF tokens uses `WebSession`.
- **Cookies:** when deploying over HTTPS, configure appropriate `Secure`, `HttpOnly`, and `SameSite` attributes; set minimal `Domain`/`Path` scope. `SameSite` is an additional layer and does not automatically replace all CSRF mechanisms.
- **XSS:** sanitize/control HTML data and Content Security Policy because malicious scripts can still act on the user's behalf inside the page, even when cookies are `HttpOnly`.
- **Session lifecycle:** active timeouts, logout, session revocation, and concurrent login limits when needed. Re-authentication should ensure session IDs are not reused in a way that enables session fixation.
- **Scale-out:** if different nodes must serve the same session, use an appropriate session store; sticky sessions alone do not fully solve the problem when a node is lost.

**Note on OAuth2 login:** OIDC/OAuth2 authorization code verifies identity with an Identity Provider, yet the WebFlux application behind it can still **maintain login state using cookies**. Using OIDC for login does not automatically turn all web page requests into Bearer-token requests.

## 3. Token-Based REST API: Resource Server

### 3.1 Request flow

1. Client obtains an **access token** from an appropriate authorization system, typically an OAuth2 Authorization Server. Public apps like mobile/SPA usually use authorization code + PKCE.
2. Client calls the API over HTTPS with the `Authorization: Bearer eyJ...` header.
3. WebFlux Resource Server extracts the Bearer token, validates it, and builds `Authentication` for the duration of the request.
4. Filter and method authorization check scopes/roles/permissions; business logic runs if valid.
5. Subsequent requests send the token again; the API does not need to rely on a session cookie from the previous request.

For **JWT**, the Resource Server must verify the signature using trusted keys, expiration (`exp`, `nbf`), issuer (`iss`), and **the audience (`aud`) intended for this API**; then check scopes/permissions. Never merely Base64-decode a JWT and trust its claims. For **opaque tokens**, the Resource Server uses the Authorization Server's introspection endpoint; the trade-off is near-real-time token status checking at the cost of extra latency/network dependency and the need for sensible caching.

In standard JWT configuration, Spring Security maps values in the `scope`/`scp` claim to authorities prefixed with `SCOPE_`, e.g., scope `orders.read` → `SCOPE_orders.read`. Scopes represent permissions granted to the token; controllers/services must still enforce resource-specific access checks, such as whether an order actually belongs to the requesting customer.

### 3.2 401, 403, and state

- **401 Unauthorized:** no valid token present, expired token, invalid signature, wrong issuer/audience, or authentication failed. The client may request a new token via an allowed flow.
- **403 Forbidden:** authenticated but lacking permissions/scopes, or blocked by policy. Re-requesting the exact same old token does not grant additional permissions.
- **Do not store authentication state in sessions:** use `NoOpServerSecurityContextRepository` when you want to cleanly separate the API from session-backed security context storage. This **does not eliminate all `WebSession`** usage that other framework features might trigger.
- **CSRF:** can be disabled specifically for APIs that **only accept Bearer tokens from headers and do not use credentials automatically attached by browsers**. If the API still accepts login cookies or an auto-sent auth mechanism, reconsider CSRF instead of disabling it globally.
- **CORS differs from CSRF:** CORS governs whether browsers are allowed to read responses and send certain cross-origin requests; it does not replace authentication, authorization, or CSRF protection.

Do not carelessly place access tokens in query strings, URLs, logs, error responses, or local storage. Use HTTPS, short-lived tokens, narrow scopes and audiences, and manage refresh tokens according to client type and security requirements.

## 4. Service-to-Service: OAuth2 Client and Resource Server Working Together

For example, `orders-service` needs to call `inventory-service` to read stock levels without an interactive user present:

1. `orders-service` has its own OAuth2 **client registration**, with a `client_id` and client authentication method (e.g., a protected `client_secret` or certificate).
2. The service sends a `grant_type=client_credentials` request to the token endpoint over TLS.
3. The Authorization Server issues an access token representing **the service/client**, with approved scopes and audience (e.g., `inventory.read`, `inventory-api`).
4. The service calls Inventory with `Authorization: Bearer <access-token>`.
5. Inventory acts as a **Resource Server**, verifying the token and `SCOPE_inventory.read` before returning results.
6. The client manager reuses valid tokens and fetches a new token when needed; this happens inside the reactive flow.

**Client credentials do not represent an end user.** If Orders needs to access Inventory **on behalf of a user**, design an appropriate delegation flow such as OAuth2 token exchange/on-behalf-of depending on Identity Provider capabilities, or propagate verified user identity via a clear security contract. Do not blindly forward a user's token to every downstream service: the token may have the wrong audience or overly broad permissions.

Alternatives include **mTLS/workload identity** for workload authentication. Regardless of the solution, the receiving service must still enforce its own authorization; a private network or API gateway is not sufficient to skip authorization. Each service has its own identity, credentials, scopes, and audit trail; secrets/certs must be stored and rotated via a secrets management system.

### 4.1 Why does WebFlux need a reactive client manager?

`ReactiveOAuth2AuthorizedClientManager` manages issuing and refreshing access tokens asynchronously. When a `ServerWebExchange` is present, `DefaultReactiveOAuth2AuthorizedClientManager` can be used; in background jobs/services **without a browser request**, use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with `ReactiveOAuth2AuthorizedClientService`. Do not use the servlet manager (`OAuth2AuthorizedClientManager` without `Reactive`) in a reactive WebFlux configuration.

## 5. Configuring WebFlux for Both Browser and API in the Same Application

These examples use Java 17+, Spring Boot 3.x / Spring Security 6.x. In `build.gradle` (Groovy), add dependencies according to application roles:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    // Only needed if the application performs OAuth2 login or calls downstream services as an OAuth2 Client:
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Do not mix `spring-boot-starter-web` (Servlet MVC) into this application if the goal is practicing the reactive security chain; when both MVC and WebFlux are present, Spring Boot typically chooses MVC by default.

Below is a `SecurityConfig.java` file containing **two independent chains**. It assumes the application already provides a `ReactiveUserDetailsService` bean or user store configuration for form login, an Authorization Server issuing valid JWTs, and the corresponding endpoints. This is a security configuration that compiles inside a Boot project with sufficient dependencies, not a standalone Java SE program to run with plain `javac`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/public/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

**Explanation:**

- `@Order(1)` and `securityMatcher("/api/**")` select the Bearer-token chain for the API first; the browser chain ordered second handles the remaining paths. Spring Security selects **one matching chain** for a request, rather than accumulating all chains.
- The API only permits GET with `orders.read` and POST with `orders.write`; undeclared API methods/paths are denied. Adjust the policy to match real business rules.
- The API has no form login, no HTTP Basic, and does not save security context into sessions; CSRF is disabled only within the API chain confirmed to use Bearer headers exclusively.
- The browser chain uses form login and CSRF. Enable `oauth2Login(Customizer.withDefaults())` instead of/alongside form login only once an OAuth2/OIDC client registration is configured for IdP login scenarios.
- For cross-origin frontends, configure CORS for specific allowed origins/methods/headers; do not use wildcards carelessly alongside credentials. For endpoints needing deeper business authorization, add checks in services/method security.

Example `application.yml` for the **JWT-validating API**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
          audiences:
            - orders-api
```

`issuer-uri` must match the `iss` claim issued by the real IdP, and `orders-api` must appear in `aud` of the access token. Set the real issuer/JWK and audience before running; the URL above is illustrative only. For opaque tokens, configure introspection and `oauth2ResourceServer(o -> o.opaqueToken(Customizer.withDefaults()))` instead of JWT.

**Do not simply apply `csrf.disable()` application-wide:** doing so strips CSRF protection from cookie-based browser operations as well.

## 6. Reactive client_credentials Example to Call Inventory

Add `spring-boot-starter-oauth2-client` and register a dedicated client in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: company-idp
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          company-idp:
            token-uri: https://idp.example.com/oauth2/token
```

Two environment variables supply credentials rather than hard-coding secrets into source/repository. The IdP and Inventory must agree on token audience, scopes, client authentication method, and signing/introspection keys. The client should use TLS for both the token endpoint and downstream APIs.

`InventoryOAuth2Config.java` below creates a manager usable even when running background jobs outside a `ServerWebExchange`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class InventoryOAuth2Config {
    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clients) {
        var manager = new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, clients);
        manager.setAuthorizedClientProvider(
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
        return manager;
    }
}
```

`InventoryClient.java` uses the manager to fetch a token and place it in the header when calling downstream. The method returns `Mono<String>` without blocking threads:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryClient {
    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public InventoryClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient.Builder webClientBuilder) {
        this.manager = manager;
        this.webClient = webClientBuilder
            .baseUrl("https://inventory.example.com")
            .build();
    }

    public Mono<String> fetchStock() {
        var request = OAuth2AuthorizeRequest
            .withClientRegistrationId("inventory")
            .principal("orders-service")
            .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Unable to obtain OAuth2 authorized client")))
            .flatMap(client -> webClient.get()
                .uri("/api/stock")
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(String.class));
    }
}
```

**Runtime notes:** `principal("orders-service")` is the identity name used by the manager to key the authorized client; **it does not turn the token into a user token**. In production, consider secure storage and shared caching per deployment architecture; across multiple nodes, `InMemoryReactiveOAuth2AuthorizedClientService` only caches per instance. Never log `getTokenValue()`. `inventory.example.com` and the token endpoint are placeholders to replace with real services. Inventory's Resource Server must also verify the token, audience, and `SCOPE_inventory.read`; merely acquiring a token does not guarantee permission to call every Inventory API.

## 7. SecurityContext in Reactive Pipelines

Reactive WebFlux processes asynchronously on Reactor, so never assume the principal is stored stably in `ThreadLocal` or retrievable from a prior request. `ReactiveSecurityContextHolder` carries `SecurityContext` along the **Reactor Context** of the same reactive stream. Inside a handler/service, the context can be read as follows (snippet inside a reactive component):

```java
public Mono<String> currentUsername() {
    return org.springframework.security.core.context.ReactiveSecurityContextHolder
        .getContext()
        .map(context -> context.getAuthentication().getName())
        .defaultIfEmpty("anonymous");
}
```

This method must run within a pipeline that has a security context; do not expect to see a user when invoking it standalone outside a request. Avoid `block()` on the WebFlux event loop, avoid manual `subscribe()`, and avoid switching to threads/executors outside Reactor without preserving context. When using `@PreAuthorize` on reactive methods, enable `@EnableReactiveMethodSecurity` and keep a `Mono`/`Flux` return signature.

A valid Bearer-token request creates its own `Authentication` within that request's processing chain; it **does not mean** Spring needs to store the authentication in `WebSession`. Conversely, a browser session is a mechanism to **restore** authentication on subsequent requests. This is a core distinction when reading Spring Security WebFlux configurations.

## 8. Choosing a Model for Your Problem

| Scenario | Initial recommendation | Why / what to check |
| --- | --- | --- |
| Same-origin admin portal, server-managed session | Browser session + form/OIDC login + CSRF | Browser sends cookies automatically; manage logout and session store |
| SPA connecting to backend via BFF | Browser ↔ BFF with session cookie, BFF holds tokens server-side when needed | Avoids exposing tokens to JavaScript; BFF still needs CSRF and cookie policy |
| Mobile / SPA as an OAuth2 public client calling API directly | Authorization code + PKCE; API as Bearer-token Resource Server | Never embed a client secret in a public client; carefully review on-device token storage |
| Partner API without browser cookies | Bearer JWT/opaque token, dedicated audience and scopes | API validates token per request and enforces per-resource authorization |
| Scheduled worker or microservice calling microservice | OAuth2 client_credentials or workload identity; receiver verifies token | No user browser/session; distinct service identity |
| Service acting on behalf of a user | Proper delegation / token exchange flow | Client credentials reflect service identity only, not user permissions |

**Quick decision question:** Are credentials automatically attached by the browser as cookies? If yes, address CSRF and sessions. Are credentials explicitly sent in a Bearer header? If yes, protect the Resource Server and token lifecycle. Is an end user actually part of the flow? If not, use a workload/service identity; never fabricate user permissions.

## 9. Test Scenarios and Expected Outcomes

Actual outcomes depend on real endpoints, policies, and data; the statuses below are expected security outcomes, not stdout from a specific executed sample program:

| Test case | Expectation |
| --- | --- |
| Unauthenticated browser opens `/dashboard` | Redirect to login or initiate OIDC login |
| Valid browser login with session cookie opens `/dashboard` | Passes authentication/authorization; endpoint response if it exists |
| Browser sends state-changing POST with cookie but missing CSRF token | 403 on CSRF-protected routes |
| API `GET /api/orders` without Bearer token | 401 |
| API sends token with invalid signature / expired / wrong `iss` / wrong `aud` | 401 |
| API sends valid token lacking `orders.read` | 403 |
| API sends valid token with `orders.read` and passes business checks | May return 2xx if endpoint/resource is valid |
| Orders calls Inventory via client_credentials without `inventory.read` | Inventory rejects with 403 |
| M2M fails to obtain token due to wrong client credentials | Fails at token endpoint / authorized client step; no valid Bearer token to send downstream |

You can test the API separately once a valid access token has been issued by a test IdP:

```bash
curl -i https://localhost:8443/api/orders
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://localhost:8443/api/orders
```

These commands assume the service is actually running HTTPS on port 8443 and `ACCESS_TOKEN` holds a validly issued token; neither command generates a JWT. Never use `curl -k` to skip TLS verification in production guides.

## 10. Common Mistakes and How to Fix Them

1. **Assuming a JWT is always safe because it has three parts:** a JWT might only be *decoded* without verification. Use a Resource Server decoder and check signature, issuer, audience, and expiration.
2. **Disabling CSRF system-wide because the API uses tokens:** the browser chain still uses cookies. Disable CSRF only on API chains with no browser-attached automatic credentials.
3. **Sharing the same token across multiple APIs:** lacks `aud` and scope boundaries, increasing blast radius on leakage. Issue tokens scoped per resource and minimal permissions.
4. **Confusing OAuth2 login with OAuth2 Resource Server:** login establishes a user session; resource server validates incoming Bearer tokens. One app may need both with separate chains.
5. **Using client_credentials in place of user permissions:** a service token does not prove user consent or data ownership. Design delegation when needed.
6. **Trusting an API gateway alone:** every downstream resource server still needs authentication, authorization, and object-level checks.
7. **Reading Servlet `SecurityContextHolder` in reactive code:** easily loses or mixes context across threads. Use `ReactiveSecurityContextHolder` and preserve the Reactor chain.
8. **Mixing up 401 and 403:** credential failure differs from insufficient permissions. Log structured events (never tokens) for analysis.
9. **Hard-coding secrets, logging tokens, or using plain HTTP:** exposes credentials. Move to a secret manager/env, HTTPS, and secret/key rotation.
10. **Skipping resource-level authorization:** `SCOPE_orders.read` does not necessarily allow viewing *every* order; enforce tenant/user/ownership checks per business rules.

## 11. Summary of Key Knowledge

- **Session browser:** server manages login state via `WebSession`, browser holds cookies, and sensitive operations use CSRF protection.
- **Bearer API:** every request carries an access token; Resource Server validates token, issuer, audience, expiration, and scopes before deciding permissions; usually does not use sessions to restore login.
- **Service-to-service:** calling service acts as an OAuth2 Client actively obtaining tokens via `client_credentials`, downstream acts as a Resource Server; service identity differs from user identity.
- **Reactive:** use `SecurityWebFilterChain` / `ServerHttpSecurity` and `Reactive...` classes; context flows through the Reactor pipeline, avoiding direct reuse of ThreadLocal/Servlet MVC patterns.

### Official documentation for reference

- [Spring Security WebFlux — Multiple SecurityWebFilterChains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security WebFlux — CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security Reactive OAuth2 Client — Core Interfaces](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html)
- [Spring Boot 3.3 — Resource Server Properties](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
