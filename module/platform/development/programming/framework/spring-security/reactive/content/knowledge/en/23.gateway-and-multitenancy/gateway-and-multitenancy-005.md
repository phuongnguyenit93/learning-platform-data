# ReactiveAuthenticationManagerResolver<ServerWebExchange> and Selecting Authentication Managers in a Multi-Tenant Gateway

> **Scope:** Spring Security Reactive (WebFlux), Java 17+, Spring Security 6.x, and Spring Boot 3.3.x. This lesson explains how to select a **ReactiveAuthenticationManager** per request context via `ReactiveAuthenticationManagerResolver<ServerWebExchange>`; applications in multi-tenant Gateways/APIs, multiple JWT issuers, HTTP Basic, or custom mechanisms; and how to avoid tenant confusion, authentication conflicts, unmatched requests, and cross-tenant privilege leakage. Examples use Spring Boot **3.3.13** to illustrate Java 17 APIs; the demo version is not a 2026 production version recommendation. In real deployments, use a supported branch with current security patches.

## 1. When Is a Single AuthenticationManager Not Enough?

A WebFlux gateway receives several kinds of requests:

- `GET /tenants/alpha/whoami`: account belonging to tenant **alpha**.
- `GET /tenants/beta/whoami`: account belonging to tenant **beta**.
- `GET /api/reports`: Bearer JWT issued by one of several trusted IdPs.
- `GET /public/health`: requires no login yet still follows gateway policy.

If one manager checks every credential, errors can arise:

1. Username `alex` exists in both alpha and beta; if the manager queries a shared user table without binding the tenant, an alpha user may be misidentified in beta.
2. A gateway accepts JWTs from multiple issuers; a decoder knowing only issuer A's keys will reject token B even if B is valid, or worse, a developer disables issuer/audience verification to "support all."
3. One service API uses HTTP Basic while another route uses opaque introspection; requests must not fall through from one mechanism to another when credentials fail.
4. An implementation performs network discovery using a client-supplied `iss`/`Host`/`X-Tenant`, creating **SSRF** or trusting an attacker's Authorization Server.
5. Two reactive authentication filters both attempt to authenticate the request, or a global WebFilter is registered twice, duplicating database queries, introspection calls, metrics, and side effects.

`ReactiveAuthenticationManagerResolver<ServerWebExchange>` helps **choose the right manager** for a request. However, it **does not verify credentials itself**, does not determine resource access permissions, and does not replace authorization.

### Flow Overview

```text
                         HTTP request
                               |
                               v
                      SecurityWebFilterChain
                      (securityMatcher picks chain)
                               |
                               v
                      AuthenticationWebFilter
                  requiresAuthenticationMatcher?
                               |
                  credential matches scheme?
                               |
                               v
             ReactiveAuthenticationManagerResolver
                       .resolve(exchange)
                               |
              +----------------+----------------+
              |                                 |
        /tenants/alpha/**                 /tenants/beta/**
              |                                 |
              v                                 v
     alpha AuthenticationManager      beta AuthenticationManager
              |                                 |
         verify password/token             verify password/token
              |                                 |
              +----------------+----------------+
                               |
                    Authentication succeeded
                               |
                    ReactiveSecurityContextHolder
                               |
                   authorizeExchange / service ACL
                               |
                        controller / downstream
```

**Key takeaway:** a route value or an issuer *read from a token before verifying its signature* is merely a **routing hint to a trusted verifier**. It is **not proof of tenant or identity**. Only the verifier and authorization determine whether the token/user has access in that tenant.

## 2. Exact API: ReactiveAuthenticationManagerResolver<C>

In Spring Security, the interface lives in package:

```java
package org.springframework.security.authentication;

@FunctionalInterface
public interface ReactiveAuthenticationManagerResolver<C> {
    Mono<ReactiveAuthenticationManager> resolve(C context);
}
```

This is an **abbreviated signature for explanation**; import the existing class from the library rather than creating a duplicate file. When `C = ServerWebExchange`:

```java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String path = exchange.getRequest().getPath().value();
        return selectManagerForTrustedRoute(path);
    };
```

The snippet above is **pseudocode** because `selectManagerForTrustedRoute` is not defined. It shows that the resolver receives the full WebFlux request context and returns a **Mono containing a manager**.

Three distinct roles:

| Component | Input | Result | Responsibility |
|---|---|---|---|
| `ServerWebExchangeMatcher` | `ServerWebExchange` | `Mono<MatchResult>` | Which filter/chain does this request belong to? |
| `ServerAuthenticationConverter` | `ServerWebExchange` | Unauthenticated `Mono<Authentication>` | Which credential did the client send? |
| `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | `ServerWebExchange` | `Mono<ReactiveAuthenticationManager>` | Which manager must verify the credential? |
| `ReactiveAuthenticationManager` | Unauthenticated `Authentication` | Authenticated `Mono<Authentication>` or error/empty | Is the credential valid under the selected mechanism? |
| `ReactiveAuthorizationManager` | Authentication and access context | Grant/deny decision | What is the principal allowed to do? |

**A resolver does not return `Authentication`.** If you write a resolver that returns an authenticated token simply because of `X-Tenant: alpha`, that confuses responsibilities and can open an authentication bypass vulnerability.

### 2.1 What Does Mono Mean?

`resolve(exchange)` returns `Mono<ReactiveAuthenticationManager>`:

- `Mono.just(manager)`: a specific manager was selected.
- `Mono.defer(...)`: decides only at subscription time, useful when relying on request-prepared state.
- `Mono.empty()`: no manager found; **never treat empty as granting access**. Downstream behavior depends on the integrating filter, so for protected routes pick an explicit fail-closed policy and test it.
- `Mono.error(new BadCredentialsException(...))`: cannot select a valid verifier; in an authentication flow, security errors must lead to rejection rather than falling back to a broader default manager.

Avoid `block()` inside a resolver on the Netty event loop. If manager selection requires database/network calls, use a truly reactive client, or isolate blocking APIs behind a dedicated scheduler with bounded concurrency, timeouts, and caching.

### 2.2 A Resolver Can Be a Lambda, Class, or Built-in Implementation

```java
ReactiveAuthenticationManagerResolver<ServerWebExchange> r =
    exchange -> Mono.just(preconfiguredManager);
```

With **a single manager**, a resolver like the above adds little value; constructing `new AuthenticationWebFilter(preconfiguredManager)` suffices. A resolver is useful when **requests** genuinely need different managers, such as per-route tenants or Bearer token issuers.

## 3. Three Dispatching Layers — Never Swap Them

Spring Security WebFlux has multiple selection layers:

1. **`ServerHttpSecurity.securityMatcher(...)`:** which **SecurityWebFilterChain** does the request belong to? Only the first matching chain in `@Order` sequence is chosen.
2. **`AuthenticationWebFilter.setRequiresAuthenticationMatcher(...)`:** should this specific authentication filter attempt to authenticate the request?
3. **`ReactiveAuthenticationManagerResolver<ServerWebExchange>.resolve(...)`:** if the converter produces a credential, which manager should verify it?

After those steps, `authorizeExchange(...)` and service-level policies check access rights.

```text
         request
            |
    pick first matching chain
            |
     within that chain:
       (i)  requiresAuthenticationMatcher
       (ii) ServerAuthenticationConverter
       (iii) resolver -> manager
       (iv) manager.authenticate(...)
       (v)  authorizeExchange(...)
            |
      business operation
```

**No resolver is needed if you cleanly separate 2 tenants into 2 independent SecurityWebFilterChains, each with its own manager.** But when a gateway serves dozens of tenants under a common pattern, a resolver lets you use **one filter** and pick the right manager from a trusted server-side registry.

### Comparing Architectural Choices

| Problem | Right Tool | Reason |
|---|---|---|
| `/api/**` uses Bearer; `/web/**` uses form session | Multiple `SecurityWebFilterChain` + `securityMatcher` | Two different HTTP/security models |
| One chain authenticates via Basic, many tenants by URL | `AuthenticationWebFilter` + `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | Same credential converter, different managers |
| One chain accepts JWTs from 2 valid issuers | `JwtIssuerReactiveAuthenticationManagerResolver` | Selects JWT verifier by issuer **in allowlist** |
| One tenant uses opaque tokens, another uses JWT | Resolver selects JWT or opaque manager; policy must determine token type | Same chain but different verification |
| One route supports Basic and Bearer | Clear converters/matchers, or separate chains per contract | Never "try managers sequentially until one succeeds" |
| Logged-in user lacks permission for another tenant's record | Authorization and business-level ACL | Resolver does not decide record permissions |
| API gateway forwards user tokens | Resource server authentication + controlled token relay | Resolver does not change audience/tokens |
| App fetches client-credentials tokens to call APIs | `ReactiveOAuth2AuthorizedClientManager` | This is an **outbound OAuth2 client**, not an inbound AuthenticationManagerResolver |

## 4. Sources of Information Used to Select a Tenant

A resolver can read host, path, headers, mTLS identity, or structured token data. However, **trust levels differ**.

| Selection Source | Usable as a Selector? | Required Safeguard |
|---|---|---|
| Route `/tenants/alpha/**` | Yes | Only for allowlisted tenants; manager verifies that tenant; check tenant-object ACL |
| Header `X-Tenant: alpha` | Yes, **only as a hint** | Never grant tenant privileges from the header alone; cross-check verified identity/issuer/claims |
| `Host` / `Forwarded` / `X-Forwarded-Host` | Yes with trusted proxies | Strip spoofed forwarded headers; verify canonical host/tenant mapping |
| Unverified JWT `iss` | Yes to pick a trusted verifier | **Never** treat as proof of a trusted issuer/token before validating signature+claims |
| Unverified JWT `aud` | Not sufficient to grant access; may be a technical hint when well-designed | Verifier must check actual audience; prevent token substitution |
| Edge-verified SNI or mTLS client cert | Yes when a trust contract is established | Proxy must authenticate/forward identity against spoofing; never trust client-declared headers |
| Query `?tenant=alpha` | Only to pick a tentative tenant if business genuinely needs it | Never auto-grant roles; requires object authorization and auditing |
| Client-entered filename or user code | Not an authority source | Never use as identity to pick a verifier and grant access |
| Issuer ID from internal tenant registry | Yes | Registry editable only by trusted admins; validate TLS/issuer/JWKS and config lifecycle |

**Tenant resolution** and **tenant authorization** are two distinct steps. A request to `/tenants/beta/orders/1` may select the beta manager, yet the user must still hold beta permissions and permission on record `orders/1`.

## 5. How AuthenticationWebFilter Uses a Resolver

`AuthenticationWebFilter` resides in `org.springframework.security.web.server.authentication` and has two constructors:

```java
new AuthenticationWebFilter(ReactiveAuthenticationManager manager);

new AuthenticationWebFilter(
    ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver);
```

Meaningful flow:

1. Check `requiresAuthenticationMatcher`.
2. Convert the HTTP request into an unverified `Authentication` via `ServerAuthenticationConverter`.
3. If the converter returns `Mono.empty()`, **no authentication attempt occurs**; continue down the chain.
4. When a credential is present, invoke the resolver to pick the appropriate manager.
5. The manager verifies the credential and emits an authenticated result or `AuthenticationException`.
6. Success: stores SecurityContext in the Reactor pipeline / configured repository. Failure: `ServerAuthenticationFailureHandler` returns 401 or a policy-defined response.

```java
// Configuration snippet, not a complete application.
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(tenantResolver);

filter.setRequiresAuthenticationMatcher(
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/tenants/**"));

filter.setServerAuthenticationConverter(
    new ServerHttpBasicAuthenticationConverter());

filter.setSecurityContextRepository(
    NoOpServerSecurityContextRepository.getInstance());
```

**Do not misunderstand the default converter.** `AuthenticationWebFilter` defaults to `ServerHttpBasicAuthenticationConverter`; in the example it is also explicitly declared so learners see it reads `Authorization: Basic ...`, **not** Bearer JWTs, API keys, or cookies by guesswork.

### Wrong credential vs. absent credential

`ServerAuthenticationConverter.convert(exchange)` returns empty when **no credential for that scheme is present**. When a user sends **Basic with a wrong password**, the manager must emit an error, **never** return `Mono.empty()` to let another filter try and "rescue" the request.

For a gateway supporting multiple credential types, enforce a transparent policy: choose the manager per trusted route/issuer, never falling back from an invalid user token to a higher-privileged app token.

## 6. Two Built-in Implementations Worth Knowing

### 6.1 ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver

Spring Security provides `ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver`. It can dispatch managers using `ServerWebExchangeMatcher`:

```java
var resolver =
    ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver
        .builder()
        .add(ServerWebExchangeMatchers.pathMatchers(
             "/tenants/alpha/**"), alphaManager)
        .add(ServerWebExchangeMatchers.pathMatchers(
             "/tenants/beta/**"), betaManager)
        .build();
```

This is a **Java snippet** assuming existing `alphaManager`/`betaManager` variables and matching imports. `Builder.add(matcher, manager)` produces a resolver combining matcher → manager pairs. Every match must be checked so a broad `/tenants/**` matcher is not placed before narrower rules and accidentally picks the wrong manager.

`setDefaultAuthenticationManager(manager)` exists, but you must **never** configure a broad-privilege manager as a fallback for unknown tenants; choose a **deny/unknown-tenant** default and test it. If a system genuinely has a default tenant, it must be an explicit business policy and **never** "allowed when the tenant header is invalid."

### 6.2 JwtIssuerReactiveAuthenticationManagerResolver

Spring Security OAuth2 Resource Server Reactive provides:

`org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver`

It is used when a gateway/resource server accepts JWTs from **a set of trusted issuers**:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://login.alpha.example/realms/main",
            "https://login.beta.example/realms/main");

http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .authenticationManagerResolver(resolver));
```

This is a Spring Security 6.3+/6.5 config snippet. Running it for real requires a live IdP/JWKS and an appropriate `SecurityWebFilterChain`. `fromTrustedIssuers` **does not** evaluate business ACLs or tenant ownership on its own. It selects a manager based on the `iss` declared by the token, **only if the issuer is in the trusted list**.

**Security note:** the `iss` value is read during decoder selection **before the JWT is verified**. Use it solely to pick a preconfigured manager from an allowlist; **afterward**, the decoder must verify the signature, issuer, timestamps, and configured validators (including the appropriate audience). An attacker can craft a token with `iss=https://evil.example`; never call discovery/JWKS on an evil host to dynamically build a manager and accept that token.

### 6.3 Do not confuse JWT issuer resolvers with Servlet APIs

| Reactivity | Correct Interface/Class | Do Not Copy by Mistake |
|---|---|---|
| WebFlux | `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | `AuthenticationManagerResolver<HttpServletRequest>` |
| WebFlux JWT multi-issuer | `JwtIssuerReactiveAuthenticationManagerResolver` | `JwtIssuerAuthenticationManagerResolver` (Servlet) |
| Reactive JWT manager | `JwtReactiveAuthenticationManager` | `JwtAuthenticationProvider` (Servlet) |
| WebFlux chain | `ServerHttpSecurity` + `SecurityWebFilterChain` | `HttpSecurity` + `SecurityFilterChain` |
| WebFlux decoder | `ReactiveJwtDecoder` | `JwtDecoder` Servlet-oriented API |
| Reactive request | `ServerWebExchange` | `HttpServletRequest` |

## 7. Ordering Spring Security Chains and Resolvers

A gateway can organize chains as follows:

```text
@Order(0)  /api/tenant/**  -> JWT multi-issuer resolver
@Order(1)  /legacy/**      -> Basic per-tenant resolver
@Order(2)  fallback        -> deny-all
```

In this design:

- `securityMatcher` selects the **chain** by URL.
- The JWT chain uses built-in OAuth2 Resource Server without hand-rolling Bearer token parsing.
- The legacy chain uses an `AuthenticationWebFilter` with a resolver selecting the credential manager per route.
- The deny-all fallback prevents new URLs from accidentally slipping outside security.
- Across chains, avoid placing broad matchers ahead of narrow matchers.

**Do not force every route through one resolver** when authentication models differ drastically. A resolver can pick a manager, but it will not convert a Basic converter into Bearer or resolve CORS/CSRF/cookies/sessions between browsers and APIs.

### Example Route Policy

| Route Group | Credential Scheme | Resolver/Manager | Session | Failure |
|---|---|---|---|---|
| `/tenants/alpha/**` | Basic in demo; production typically JWT/mTLS | Alpha manager | Stateless demo | 401 Basic challenge |
| `/tenants/beta/**` | Basic in demo | Beta manager | Stateless demo | 401 Basic challenge |
| `/api/**` | Bearer JWT | JwtIssuerReactiveAuthenticationManagerResolver | Stateless (per config) | 401 invalid token |
| `/web/**` | Form/OIDC login | Login filters + provider flow | Browser session | 302/login or 401 as appropriate |
| `/actuator/health` | Public only for non-sensitive health | Separate chain policy | None | 200 if permitted |
| Unknown URL | None | Fallback deny-all | None | 403/401 per policy |

## 8. Designing Fail-Closed Behavior for Unknown Tenants

A resolver should behave deterministically for **non-existent tenants**:

```text
/tenants/alpha/whoami -> alpha manager
/tenants/beta/whoami  -> beta manager
/tenants/gamma/whoami -> FAIL CLOSED (never fall back to alpha)
/tenants//whoami      -> invalid
/tenants/../alpha     -> never use raw input to guess tenant
```

You can return `Mono.error(new BadCredentialsException("Unsupported tenant"))` in the authentication flow or use a fixed always-denying manager; the status depends on exception handling/filters. **Never** fall back to `managerDefaultWithAdminPrivileges` when `managers.get(tenant) == null`.

A valid route without credentials must also be blocked by authorization; an empty converter does not mean "anonymous is allowed" if the route requires authentication.

### Protecting Tenant IDs in URLs

Tenant path segments should be constrained by a **server-defined** format/allowlist, such as `[a-z][a-z0-9-]*`, and verified against an active-only registry. Never concatenate this string unvalidated into SQL schemas, hostnames, issuer URIs, or secret paths.

A safe structure:

1. Parse the tenant in **exactly one place** via the route matcher, never from conflicting headers.
2. Look up the tenant in a server-side registry requiring active status.
3. Select the manager bound to that registered tenant.
4. The manager verifies the credential.
5. Authorization reconciles the **route tenant** with the verified tenant/issuer/claims.
6. The business service checks record ownership/tenant, even after route-level checks pass.

## 9. Runnable Demo — Same Username, 2 Tenants, 2 Managers, 1 AuthenticationWebFilter

This lesson demonstrates using **HTTP Basic on localhost** so you can observe the resolver choosing the right password verifier **without needing an online IdP/JWKS**. This is **not a production tenant login architecture**, which typically uses OIDC/JWT or mTLS. There are two tenants:

- `alpha`: user `alex`, study password `alpha-only-dev`, authority `TENANT_ALPHA`.
- `beta`: user **also named `alex`**, but password `beta-only-dev`, authority `TENANT_BETA`.

**What to prove:** valid credentials for alpha **cannot** log into beta despite the identical username; the resolver picks a manager based on the **recognized route**, that manager verifies credentials for **that tenant**, and authorization requires the matching tenant authority.

### 9.1 Structure

```text
webflux-tenant-resolver/
  settings.gradle
  build.gradle
  src/main/java/demo/tenant/TenantResolverApplication.java
  src/main/java/demo/tenant/TenantManagerResolver.java
  src/main/java/demo/tenant/TenantSecurityConfiguration.java
  src/main/java/demo/tenant/TenantController.java
  src/test/java/demo/tenant/TenantResolverTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-tenant-resolver'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.tenant'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The demo uses only GET and keeps default CSRF for unsafe methods; do not add the Servlet starter. Dependencies are managed by the Spring Boot plugin. This version illustrates 6.3 APIs without a real IdP.

### 9.2 Spring Boot main

**src/main/java/demo/tenant/TenantResolverApplication.java**

```java
package demo.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantResolverApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantResolverApplication.class, args);
    }
}
```

### 9.3 TenantManagerResolver.java

```java
package demo.tenant;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class TenantManagerResolver
        implements ReactiveAuthenticationManagerResolver<ServerWebExchange> {

    private static final Pattern ROUTE = Pattern.compile(
        "^/tenants/([a-z][a-z0-9-]*)/whoami$");

    private final Map<String, ReactiveAuthenticationManager> managers;
    private final Map<String, AtomicInteger> selections;

    public TenantManagerResolver(
            Map<String, ReactiveAuthenticationManager> managers) {
        this.managers = Map.copyOf(managers);
        this.selections = new ConcurrentHashMap<>();
        for (String tenant : managers.keySet()) {
            this.selections.put(tenant, new AtomicInteger());
        }
    }

    @Override
    public Mono<ReactiveAuthenticationManager> resolve(
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

            Matcher matcher = ROUTE.matcher(path);
            if (!matcher.matches()) {
                return Mono.error(new BadCredentialsException(
                    "Unsupported tenant route"));
            }

            String tenant = matcher.group(1);
            ReactiveAuthenticationManager manager =
                managers.get(tenant);

            if (manager == null) {
                return Mono.error(new BadCredentialsException(
                    "Unsupported tenant"));
            }

            // Used in tests; never log credentials.
            selections.get(tenant).incrementAndGet();
            return Mono.just(manager);
        });
    }

    public int selectedCount(String tenant) {
        AtomicInteger count = selections.get(tenant);
        return count == null ? 0 : count.get();
    }
}
```

**Mechanism:**

- `implements ReactiveAuthenticationManagerResolver<ServerWebExchange>` is the focus of this lesson.
- `Map.copyOf(managers)` locks down the manager table for the demo; never build arbitrary managers from client input.
- The regex accepts only `/tenants/{id}/whoami` routes with valid structure; the ID is further checked against the allowlist map.
- `Mono.defer(...)` ensures resolution occurs when the publisher is subscribed. Never call `block()` or perform network discovery.
- Unknown routes/tenants return `BadCredentialsException` rather than a default tenant.
- `AtomicInteger` counts manager selections so tests verify **no wrong tenant is chosen**. This is not a production security counter; concurrent requests would invalidate global before/after comparisons, so the demo tests run sequentially.
- **Do not implement `WebFilter` or annotate this class with `@Component`**; it is registered as a resolver bean, preventing it from running as a global WebFilter outside the Security chain.

### 9.4 TenantSecurityConfiguration.java

```java
package demo.tenant;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authentication.ServerHttpBasicAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class TenantSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    private static ReactiveAuthenticationManager manager(
            String password, String authority,
            PasswordEncoder encoder) {

        UserDetails alex = User.withUsername("alex")
            .password(encoder.encode(password))
            .authorities(authority)
            .build();

        var users = new MapReactiveUserDetailsService(alex);
        var manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    TenantManagerResolver tenantResolver(PasswordEncoder encoder) {
        return new TenantManagerResolver(Map.of(
            "alpha", manager("alpha-only-dev",
                "TENANT_ALPHA", encoder),
            "beta", manager("beta-only-dev",
                "TENANT_BETA", encoder)));
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain tenantChain(
            ServerHttpSecurity http,
            TenantManagerResolver resolver) {

        var entryPoint = new HttpBasicServerAuthenticationEntryPoint();
        entryPoint.setRealm("tenant-demo");

        // Filter belongs only to SecurityWebFilterChain; not a @Bean WebFilter.
        var tenantFilter = new AuthenticationWebFilter(resolver);
        tenantFilter.setServerAuthenticationConverter(
            new ServerHttpBasicAuthenticationConverter());
        tenantFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/tenants/**"));
        tenantFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());
        tenantFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(entryPoint));

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/tenants/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/tenants/alpha/whoami")
                    .hasAuthority("TENANT_ALPHA")
                .pathMatchers(HttpMethod.GET,
                    "/tenants/beta/whoami")
                    .hasAuthority("TENANT_BETA")
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .addFilterAt(
                tenantFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain denyAllFallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Configuration explanation:**

1. Each tenant has its **own ReactiveAuthenticationManager**, using `UserDetailsRepositoryReactiveAuthenticationManager` with a separate `MapReactiveUserDetailsService` and BCrypt-encoded passwords.
2. `"alex"` exists in both tenants with different passwords and authorities. Reusing the same username lets us test **cross-tenant authentication** failures.
3. `tenantResolver(...)` returns a `TenantManagerResolver` bean, **not** a global `ReactiveAuthenticationManager` bean, preventing Spring Boot from accidentally wiring it into another chain.
4. `new AuthenticationWebFilter(resolver)` is the exact API: the filter calls the resolver whenever a Basic authentication attempt arrives.
5. `setServerAuthenticationConverter(new ServerHttpBasicAuthenticationConverter())` guarantees only Basic credentials are read. Bearer headers, API keys, or session cookies are never implicitly accepted.
6. `setRequiresAuthenticationMatcher(...)` limits the filter to **GET /tenants/**`. `POST` does not automatically become an authenticated route for this filter.
7. `NoOpServerSecurityContextRepository` keeps authentication only for the **current request** via Reactor Context rather than persisting a login session across requests.
8. `httpBasic(...disable())` prevents a **second built-in Basic filter** from being added to the chain, since we registered our own AuthenticationWebFilter reading Basic. This avoids authenticating requests twice.
9. `formLogin(...disable())` prevents browser form filters from entering the tenant API chain.
10. `exceptionHandling.authenticationEntryPoint(...)` handles missing credentials on protected routes, while the filter's failure handler handles wrong Basic credentials. Both emit HTTP Basic 401 challenges.
11. `authorizeExchange` checks specific tenant authorities, **never** relying on bare `authenticated()` to grant cross-tenant access.
12. The fallback chain denies all remaining routes. It has **no** securityMatcher, so it catches requests outside the `/tenants/**` chain.
13. The demo leaves default CSRF enabled for unsafe methods; all demo routes are intentionally GET. If extending with POST/PUT/DELETE, design CSRF/CORS/authentication per the new threat model instead of disabling protections.

### 9.5 TenantController.java

```java
package demo.tenant;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class TenantController {

    @GetMapping("/tenants/{tenant}/whoami")
    public Mono<String> whoami(
            @PathVariable String tenant,
            Principal principal) {

        return Mono.just(tenant + ":" + principal.getName());
    }
}
```

**Never rely on `@PathVariable tenant` to claim authentication.** The tenant path is returned only after the Security filter and authorization succeed. In real business logic, verify the **tenant ID from the verified identity** and record permissions, especially on dynamic routes without hardcoded `hasAuthority("TENANT_ALPHA")`.

### 9.6 Run and Observe

```bash
gradle bootRun
```

With a matching Gradle Wrapper: `./gradlew bootRun` or Windows `gradlew.bat bootRun`. In PowerShell, you may need `curl.exe` to avoid the alias.

```bash
# Correct Alpha credential. Curl will prompt for password:
curl -i -u alex http://localhost:8080/tenants/alpha/whoami
# Enter alpha-only-dev

# Correct Beta credential:
curl -i -u alex http://localhost:8080/tenants/beta/whoami
# Enter beta-only-dev

# Attempt using alpha credential on beta URL:
curl -i -u alex http://localhost:8080/tenants/beta/whoami
# Enter alpha-only-dev

# Without sending Basic:
curl -i http://localhost:8080/tenants/alpha/whoami

# Unknown tenant:
curl -i -u alex http://localhost:8080/tenants/gamma/whoami
```

**Expected** results:

```text
GET /tenants/alpha/whoami + Basic alex/alpha-only-dev  -> 200 alpha:alex
GET /tenants/beta/whoami  + Basic alex/beta-only-dev   -> 200 beta:alex
GET /tenants/beta/whoami  + Basic alex/alpha-only-dev  -> 401
GET /tenants/alpha/whoami + no Basic                   -> 401
GET /tenants/gamma/whoami + Basic alex/anything        -> 4xx; never 200
```

The credentials/passwords above are training data with no value outside localhost. Production requires TLS, password/secret managers, brute-force controls, an appropriate identity provider, and rate limits.

## 10. WebTestClient: Testing Manager Selection and Tenant Isolation

**src/test/java/demo/tenant/TenantResolverTest.java**

```java
package demo.tenant;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TenantResolverTest {

    @Autowired
    WebTestClient client;

    @Autowired
    TenantManagerResolver resolver;

    @Test
    void alphaWithAlphaPasswordSucceedsAndSelectsOnce() {
        int before = resolver.selectedCount("alpha");

        client.get().uri("/tenants/alpha/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alpha:alex");

        assertEquals(before + 1, resolver.selectedCount("alpha"));
    }

    @Test
    void betaWithBetaPasswordSucceedsAndSelectsOnce() {
        int before = resolver.selectedCount("beta");

        client.get().uri("/tenants/beta/whoami")
            .headers(h -> h.setBasicAuth("alex", "beta-only-dev"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("beta:alex");

        assertEquals(before + 1, resolver.selectedCount("beta"));
    }

    @Test
    void alphaPasswordCannotAuthenticateInBeta() {
        int beforeBeta = resolver.selectedCount("beta");

        client.get().uri("/tenants/beta/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(beforeBeta + 1, resolver.selectedCount("beta"));
    }

    @Test
    void betaPasswordCannotAuthenticateInAlpha() {
        int beforeAlpha = resolver.selectedCount("alpha");

        client.get().uri("/tenants/alpha/whoami")
            .headers(h -> h.setBasicAuth("alex", "beta-only-dev"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(beforeAlpha + 1, resolver.selectedCount("alpha"));
    }

    @Test
    void missingCredentialDoesNotSelectAnyManager() {
        int alpha = resolver.selectedCount("alpha");
        int beta = resolver.selectedCount("beta");

        client.get().uri("/tenants/alpha/whoami")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*");

        assertEquals(alpha, resolver.selectedCount("alpha"));
        assertEquals(beta, resolver.selectedCount("beta"));
    }

    @Test
    void bearerHeaderIsNotAcceptedAsBasicAuthentication() {
        int alpha = resolver.selectedCount("alpha");

        client.get().uri("/tenants/alpha/whoami")
            .header(HttpHeaders.AUTHORIZATION, "Bearer fake-token")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(alpha, resolver.selectedCount("alpha"));
    }

    @Test
    void unknownTenantFailsClosed() {
        int alpha = resolver.selectedCount("alpha");
        int beta = resolver.selectedCount("beta");

        client.get().uri("/tenants/gamma/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().is4xxClientError();

        assertEquals(alpha, resolver.selectedCount("alpha"));
        assertEquals(beta, resolver.selectedCount("beta"));
    }

    @Test
    void unrelatedRouteCannotUseTenantBasicAuthentication() {
        int alpha = resolver.selectedCount("alpha");
        int beta = resolver.selectedCount("beta");

        client.get().uri("/unlisted")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().is4xxClientError();

        assertEquals(alpha, resolver.selectedCount("alpha"));
        assertEquals(beta, resolver.selectedCount("beta"));
    }

    @Test
    void sessionCookieAloneDoesNotAuthenticate() {
        client.get().uri("/tenants/alpha/whoami")
            .cookie("SESSION", "invented-session-id")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unsafePostDoesNotUseGetOnlyAuthenticationFilter() {
        int alpha = resolver.selectedCount("alpha");

        client.post().uri("/tenants/alpha/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(alpha, resolver.selectedCount("alpha"));
    }
}
```

**10 test methods** verifying:

1. Alpha and beta with valid credentials return 200, and the manager is selected once.
2. Same username with another tenant's password **cannot** authenticate successfully.
3. Missing Basic header → converter emits no Authentication → manager resolver is not called and route still returns 401.
4. A Bearer header is not accepted by the custom Basic converter.
5. An unlisted tenant does not fall back to the alpha or beta manager.
6. Routes outside `/tenants/**` do not invoke the resolver.
7. A forged cookie does not create an authenticated session due to `NoOpServerSecurityContextRepository`.
8. An unsafe POST is not picked up by the GET matcher; both CSRF and authorization reject it.

**QA note:** these tests are based on API/Javadoc design, without a Gradle build/test log executed in the author's environment. If production proxies rewrite paths, test the exact paths received by Spring WebFlux and the HTTP stack's normalization.

### 10.1 Why do tests count manager selections?

`AtomicInteger` increments when `TenantManagerResolver.resolve(...)` locates a manager. It confirms that a valid or wrong-password Basic request is routed to **one** manager for the matching tenant. However:

- The counter measures **manager selections**, not directly `manager.authenticate` invocations or DB queries.
- To measure retries/subscriptions, instrument the reactive manager or user repository in tests.
- Shared counters can be affected by parallel tests or other HTTP traffic; the demo runs sequentially.
- Never rely on this counter for production rate limiting or auditing.
- When the converter returns empty, the resolver may not be invoked; this matches standard AuthenticationWebFilter flow.

## 11. Production Multi-Issuer JWT: Proper Selection and Verification

The Basic demo clarifies the resolver cleanly, but production Gateways typically use Bearer JWTs. Spring Security already provides `JwtIssuerReactiveAuthenticationManagerResolver`; **prefer it** whenever the requirement is simply accepting tokens from multiple allowed issuers.

### 11.1 WebFlux Resource Server Pattern with Trusted Issuers

```java
package example.jwt;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class MultiIssuerSecurityConfiguration {

    @Bean
    SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
        var resolver =
            JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                    "https://login.alpha.example/realms/main",
                    "https://login.beta.example/realms/main");

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(resolver))
            .build();
    }
}
```

**This is an alternative to the Basic demo**; do not drop this class beside `TenantSecurityConfiguration` in the same project without redesigning the chains. Running it for real requires actual IdPs/JWKS, valid issuers, and properly targeted tokens. `.example` URLs are illustrative only, not live IdPs.

**Read accurately:**

- Built-in `oauth2ResourceServer` extracts the Bearer token from the request; you do not need to hand-parse Bearer tokens from queries/cookies.
- The resolver uses the issuer claim to **pick** the matching `JwtReactiveAuthenticationManager` among trusted issuers.
- Per Spring Security 6.5 documentation, manager/JWK metadata initialization may occur **lazily** per issuer on the first request, reducing startup dependencies while making the first call dependent on IdP network availability.
- Verifying signatures, issuer, expiry, and configured validators is the responsibility of the decoder/manager.
- `authenticated()` is **not sufficient** for a multi-tenant data Gateway: audience/scope/tenant/object ACLs are needed at both the Gateway and downstream.

### 11.2 Selecting an issuer is not enough to restrict audience

A token from issuer alpha may have been issued for another application/Resource Server. Matching `iss` alone does not prove the token has an `aud` meant for the Gateway.

Production must verify:

```text
signature    valid?
iss          exactly one of trusted issuer strings?
aud          contains this gateway / required resource?
exp, nbf     within allowed time / skew?
scope        enough for requested operation?
subject      allowed to access tenant?
tenant claim consistent with route/host?
record       owned by authorized subject/tenant?
```

For each issuer, add appropriate `OAuth2TokenValidator<Jwt>` checks for audience/scope/tenant claims or configure a complete `ReactiveJwtDecoder`. Never assume `fromTrustedIssuers(...)` infers the expected audience from the URL.

### 11.3 Preventing tenant mix-up via token `iss`

Consider this request:

```http
GET /tenants/beta/reports HTTP/1.1
Host: gateway.example.com
Authorization: Bearer <JWT_ISSUER_ALPHA>
```

If the issuer resolver accepts valid issuer alpha, the request may be **authenticated** under alpha's identity. Yet `/tenants/beta/reports` belongs to beta. The Gateway/downstream must additionally verify **route tenant = tenant bound to authenticated principal**, or enforce an explicitly verified cross-tenant delegation policy. Having only `anyExchange().authenticated()` misses this step.

A safe policy:

```text
issuer alpha -> tenant alpha identity
issuer beta  -> tenant beta identity

GET /tenants/alpha/** with verified alpha identity -> check scope/ACL
GET /tenants/beta/**  with verified alpha identity -> 403
GET /tenants/beta/**  with verified beta identity  -> check scope/ACL
```

The issuer → tenant mapping must reside in a **server-side tenant registry**, never taken directly from a client-supplied `X-Tenant` header. When an organization uses a shared issuer serving multiple tenants, use a verified trusted tenant claim matched against the route instead of relying solely on the issuer string.

## 12. Configuring Multiple Token Types: JWT and Opaque

Some enterprises have two issuers/tenants:

- Tenant A issues signed JWTs with JWKS.
- Tenant B issues **opaque tokens** requiring an introspection endpoint call.

At the API level, `ReactiveAuthenticationManagerResolver<ServerWebExchange>` can select either `JwtReactiveAuthenticationManager` or a manager backed by `ReactiveOpaqueTokenIntrospector` (when configured for your Spring Security version).

```text
request /tenant-A/... + Bearer token
 -> trusted tenant registry A
 -> JwtReactiveAuthenticationManager
 -> ReactiveJwtDecoder verifies JWT

request /tenant-B/... + Bearer token
 -> trusted tenant registry B
 -> Opaque introspection manager
 -> HTTPS introspection service verifies token state
```

**Never guess that a token is a JWT solely by counting dots in the string**. Opaque tokens can look like JWTs, or JWT-like formats can serve other purposes. Decide based on **the issuer/resource server contract and trusted route/tenant**, never brittle structural heuristics.

If a single URL must accept both token types, enforce a fail-closed routing policy and test ambiguous/unsupported cases; never introspect a bad JWT and fall back to a higher-privileged manager just to return 200.

### 12.1 Each tenant has its own introspection credentials

For opaque tokens, the client ID/secret used at the introspection endpoint may differ across tenants. These are **Resource Server credentials** for calling introspection, not user passwords in HTTP requests. Never reuse the same secret across all tenants purely for convenience, and never log tokens in HTTP client tracing.

Introspection introduces network latency and an availability dependency. Use nonblocking WebClient, TLS, bounded connections/timeouts, rate limits, and caching aligned with TTL/revocation policies; never call `block()` on the event loop.

## 13. Dynamic Resolvers: Onboarding Tenants at Runtime

A multi-tenant gateway should not need a restart every time a new tenant is onboarded. A registry can hold:

```text
tenantId / issuer
   -> approved configured manager/decoder
   -> ACTIVE/REVOKED status
   -> allowed audiences + scopes
   -> key rotation/reload policy
```

### 13.1 Never run discovery from user input

**Dangerous anti-pattern:**

```java
// ANTI-PATTERN: do not use inside a request handler.
String issuer = exchange.getRequest().getHeaders()
    .getFirst("X-Issuer");

// The line below risks SSRF if issuer is arbitrarily supplied by the client:
// ReactiveJwtDecoders.fromIssuerLocation(issuer)
```

If an attacker sends `X-Issuer: http://169.254.169.254/...` or an internal URL, the server may issue discovery requests to unauthorized hosts. Even on an Internet URL, the attacker can issue self-signed JWTs and publish their own matching JWKS.

**Better:** only authorized admins via an onboarding workflow approve an issuer/tenant → store it in the server-side registry; the resolver looks up **exclusively from the approved list**. Never trust an issuer just because its domain looks corporate; verify exact URI, TLS, ownership, and scopes.

### 13.2 Designing a repository of managers

Following Spring Security's multi-tenancy guide, you can build `JwtIssuerReactiveAuthenticationManagerResolver` with a controlled repository:

```java
// Code snippet — map was built beforehand from a trusted source.
Map<String, ReactiveAuthenticationManager> managers =
    new ConcurrentHashMap<>();

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    new JwtIssuerReactiveAuthenticationManagerResolver(
        issuer -> Mono.justOrEmpty(managers.get(issuer)));
```

This snippet requires imports for `Map`, `ConcurrentHashMap`, `Mono`, `ReactiveAuthenticationManager`, and the resolver. **Never** put "if map misses, fetch JWK for the token's issuer" logic here. Adding a new tenant must go through admin approval, constructing the decoder/JWKS with issuer and audience validators, and then inserting the manager into the registry.

A safe onboarding plan:

1. Receive tenant request via an authenticated admin channel.
2. Verify tenant admin authority and issuer metadata from a trusted source.
3. Validate HTTPS, hostname, issuer ID, allowed audiences, JWT algs, scopes, JWK URL, and key rotation.
4. Initialize/configure the manager against the verified version; check health and introspection/JWKS.
5. Publish an immutable snapshot or versioned concurrent map update with auditing.
6. When a tenant is disabled, stop selecting the old manager/issuer and expire caches/TTLs per policy.
7. Test in-flight/stale requests and multi-node config convergence.
8. If an issuer has an outage, fail closed; never fall back to another tenant's manager.

### 13.3 Lazy initialization and blocking boundaries

Spring Security provides factory methods to build JWT managers from an issuer; depending on version, some discovery helpers perform synchronous I/O. If blocking discovery must be wrapped for reactive manager provisioning, execute it during startup/admin async workflows or wrap properly:

```java
Mono<ReactiveJwtDecoder> decoder =
    Mono.fromCallable(() ->
        ReactiveJwtDecoders.fromIssuerLocation(trustedIssuer))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an **illustrative snippet** requiring imports, used only when `trustedIssuer` is already in the trusted registry; never invoke it per HTTP request. Avoid creating a new manager/JWKS client per request, which causes bottlenecks, DoS, and inconsistent verification. Cache per issuer with size bounds, timeouts, retry/backoff, and metrics.

## 14. Gateway Routing vs. Security Resolution

Spring Cloud Gateway typically uses route predicates/filter chains to pick the target backend. Never confuse **Gateway routing to a microservice** with **Spring Security selecting a verifier**:

```text
Request
  |
  +--> Security: pick chain + manager + verify token
  |                  |
  |             identity/scope/tenant
  |                  |
  +--> Authorization: permitted to call route/object?
  |                  |
  +--> Gateway route predicate: which backend?
  |                  |
  +--> Token relay / outbound auth: which token is sent?
  |                  |
  v
Downstream API (MUST verify token/audience/tenant per trust model)
```

Traversing the Gateway does not magically make a wrong-audience token valid. If the Gateway receives `aud=gateway` and the backend demands `aud=orders-api`, consider token exchange/on-behalf-of or requesting a properly targeted token. **Never** disable audience validation on the backend merely because the Gateway accepted the token.

### 14.1 Never rely on X-Tenant to grant permissions

```http
GET /tenants/beta/orders HTTP/1.1
X-Tenant: beta
Authorization: Bearer <TOKEN_OF_ALPHA_USER>
```

A client-sent header may help pick a **candidate tenant**, but it does not prove user alpha may view beta. Compare the tenant in **verified JWT claims/authorities and server-side mappings** against the route tenant. Never pass raw `X-Tenant` headers to the backend and treat them as authentication assertions.

### 14.2 Forwarded headers and host-based tenants

Behind a reverse proxy, `X-Forwarded-Host`/`Forwarded` can influence URI/tenant routing. Trust these headers only when trusted ingress **strips/overwrites** all client-supplied values, configures trusted proxies, and normalizes hostnames. Otherwise, an attacker can select an unexpected manager/tenant via host spoofing.

Never try to fix this by having the resolver "try all managers"; that causes route confusion. Maintain a canonical mapping between external hosts, tenants, approved issuers, and resource paths.

### 14.3 Blocking multiple simultaneous credentials

A request carrying both `Authorization: Bearer A` and `X-API-Key: B` requires an explicit policy. Options:

- A Bearer route **only** accepts Bearer, rejecting extra credentials if the threat model requires it.
- An API-key route accepts only the key, ignoring or rejecting Bearer per contract, **never** using an invalid Bearer as a fallback.
- During migrations, a converter policy selects exactly one scheme; if both credentials appear → 400/401 per contract.

The resolver **picks a manager**; it is not required to resolve multi-credential conversion itself. Converters/matchers are a separate layer and must be tested.

## 15. 401, 403, Redirects, and Safe Error Messages

| Scenario | Reasonable HTTP | Cause |
|---|---|---|
| Protected route, no credential | 401 | Unauthenticated |
| Credential present but wrong/expired/bad signature | 401 | Authentication failed |
| Credential valid for tenant alpha sent to beta route | 401 or 403 depending on flow; **must reject** | If beta manager rejects credential → 401; if authenticated but lacking beta permission → 403 |
| Unknown tenant | 4xx fail-closed | Resolver must not fall back to a broad-privilege manager |
| Valid token missing scope/role | 403 | Authorization denied |
| Valid token with wrong resource audience | 401 invalid token or status per resource-server contract | Token validation rejected |
| Unauthenticated browser hits page | 302 to login or 401 per UX/chain | No identity |
| Gateway cannot reach issuer/JWKS/introspection | Reject token; return safe error based on failure point | Never fall back to another issuer |
| Preflight OPTIONS | Per CORS policy | Never "skip auth for all routes" |
| Resource does not exist | 404/4xx after security policy runs | Never make unknown tenants public |

Each system has its own error contract. **Do not turn every 403 into "token expired"**; CSRF failures, missing permissions, wrong tenants, and authentication failures have distinct causes.

Never echo raw authorization tokens, client secrets, sensitive issuer metadata, session IDs, or stack traces in JSON error bodies. Log the route template, validated tenant ID (if permitted), credential mechanism, correlation ID, status, and stable error codes — never log tokens or passwords.

## 16. Diagnosing Common Mistakes

| Symptom | Possible Cause | How to Check / Fix |
|---|---|---|
| Tenant alpha logs into beta route | Shared manager looks up username without tenant; rule is only `authenticated()` | Separate managers/user stores, verify tenant authority |
| Request with unknown `X-Tenant` causes server to call strange URL | Issuer discovery from client input | Issuer allowlist, eliminate SSRF |
| JWKS server called repeatedly | Manager/decoder recreated per request | Cache per issuer, preprovision, telemetry |
| Basic manager called twice | Built-in HTTP Basic + custom AuthenticationWebFilter | Disable built-in Basic or remove duplicate custom filter |
| Spring Security accepts Bearer from wrong issuer | Verifier skips issuer/signature check | Use trusted issuers + JWT validators |
| Alpha issuer token reads beta record | Only `authenticated()`, missing tenant ACL | Compare verified tenant/issuer against route and record |
| Request returns 401 despite valid JWT signature | Wrong audience/scope/issuer, expired/clock skew, missing JWK | Inspect detailed validator policy; never disable checks |
| GET with valid token returns 403 | Missing authority/role or tenant mismatch | Test authorization separately |
| No credential and resolver does not run | Converter returns Mono.empty | Normal; authorization must return 401 |
| POST without CSRF token returns 403 | CSRF filter blocks before manager/controller | Configure proper token handling; never disable globally |
| Gateway routes properly but token relay fails | Downstream token aud mismatch | Token exchange, proper resource token |
| New route callable without auth | No chain matches | Fallback chain denyAll |
| `@Order` sends route to wrong chain | Broad matcher precedes narrow matcher | Order narrow first, test paths |
| Same username in two tenants mixes identities | Account key is username only | Key by issuer+sub or tenant+user ID |
| Backend cannot handle session state | Multi-node session store/TTL issue | Isolate state, shared store, or stateless JWT per contract |
| JWK key rotation breaks requests | Improper key cache/JWKS refresh | Manage cache and rotation |
| Custom resolver runs JDBC query on event loop | Blocking I/O | Reactive driver or bounded scheduler |
| Credentials leaked in tracing logs | Logging raw requests/headers | Redact, audit logging pipeline |
| Disabled tenant still serves requests | Registry/cache not invalidated | Cache lifecycle, revocation propagation |

## 17. Production Test Matrix

| Layer | Test Case | Expected Outcome |
|---|---|---|
| Selector | Approved tenant alpha/beta | Selects exactly one manager |
| Selector | Unknown tenant / lookalike path | Never falls back to permissive default |
| Credential | Alpha user password on beta | Authentication rejected |
| Credential | Missing/invalid Basic/Bearer | 401, business logic never called |
| Filter | No Basic header in WebFlux demo | Converter empty, resolver not called |
| Filter | Duplicate built-in + custom filter | Selection counter test catches and fixes |
| Chain | Narrow before broad, fallback | Route hits the intended chain |
| JWT issuer | Valid issuer A/B token | Picks corresponding manager/JWKS |
| JWT issuer | Attacker issuer, unsigned/wrong-key JWT | 401, **never** calls discovery on attacker issuer |
| JWT claims | Wrong aud, expired, not-before | 401 per validator |
| JWT tenant | Alpha token calling beta route | 403 or 401 per policy; no access to beta |
| JWT scope | Missing required scopes | 403 |
| Data ACL | Matching tenant but another user's record | 403/404 per policy |
| Proxy | Spoofed X-Forwarded-Host | Does not switch tenant outside trusted mapping |
| CORS/CSRF | Preflight and unsafe methods | Policy enforced, no bypass |
| Network | JWKS/introspection outage | Fail closed, bounded timeout/retry |
| Dynamic tenant | Onboard/disable under traffic | Snapshot/registry consistent, caches updated |
| Token relay | Downstream Bearer has right audience | Backend re-verifies token and permissions |
| Concurrency | Burst for new issuer | Manager lazy loading avoids request storm |
| Logging | Authentication errors | Never leaks Bearer/secrets/passwords |

**Important:** testing credential-type routing offline with Basic confirms only **manager selection mechanics**. Thoroughly testing multi-issuer JWTs requires signed test tokens, real JWKS or mock IdPs, and validator audits (signature, issuer, audience, scope, tenant), rather than merely constructing `Jwt` objects via a test builder.

## 18. Deployment Checklist

1. Map route/tenant → issuer/provider → credential type → required scopes/authorities → backend.
2. Decide clearly when to use multiple `SecurityWebFilterChain`s vs. a resolver inside one chain.
3. Use the WebFlux interface `ReactiveAuthenticationManagerResolver<ServerWebExchange>`.
4. Separate `ServerAuthenticationConverter` (extract credential) from resolver (pick verifier) and manager (verify).
5. Select managers only from trusted config/registry; never perform discovery on client-supplied URLs.
6. Never let an unknown tenant become a default trusted tenant or gain ADMIN privileges.
7. For multi-issuer JWTs, prefer `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)`.
8. Check issuer **and** JWT signature, timestamps, audience, and scopes; tenant claim must align with the route.
9. Never treat raw `iss`/`Host`/`X-Tenant` as verified identity.
10. For opaque introspection, separate introspectors/credentials per tenant; never reuse sessions/tokens unconditionally.
11. Prevent credential mixing and fallback from invalid tokens to broader-privilege managers.
12. Place filters inside the right Security chain; never also register them as global `WebFilter`s.
13. Configure `NoOpServerSecurityContextRepository` if the API is designed stateless; audit other filters/sessions.
14. Include a fallback chain, explicit `@Order`, narrow-before-broad authorization rules, and negative tests.
15. Keep CSRF/CORS aligned with the threat model; never fix 403 by disabling everything.
16. Ensure proxy forwarded headers are trusted only from trusted sources to prevent tenant host spoofing.
17. Protect secrets, HTTPS, password policies, JWK/secret rotation, caching, and revocation.
18. Measure latency and failed issuer/resolver selections without logging raw tokens or passwords.
19. Test identical usernames across tenants; test signed JWTs with wrong issuer/audience/tenant and object-level ACLs.
20. When the gateway relays access tokens, verify downstream audience/permissions or use token exchange as needed.
21. Re-verify APIs against your exact Spring Security version before every upgrade.

## 19. Practice Exercises

1. Diagram `AuthenticationWebFilter → converter → resolver → manager → SecurityContext → authorization`. Where is the raw token extracted, and where is identity actually confirmed?
2. Change username `alex` across the two tenants while keeping distinct passwords. Write a WebTestClient test proving no cross-authentication occurs.
3. Add tenant `gamma` with its own password and authority to the resolver. What changes are required in the authorization rules?
4. Add route `/tenants/alpha/admin`. If you leave only `authenticated()`, what vulnerability arises?
5. Remove the fallback chain and hit an unmatched URL. Why must you never assume the default is 403?
6. Register a duplicate `AuthenticationWebFilter` both globally and inside the chain in a test environment. Measure resolver/manager attempts, then fix it.
7. Use `ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver.builder()` to replace the custom regex resolver; compare clarity and matcher ordering.
8. Replace the Basic demo with multi-issuer JWTs and signed test tokens. Test both trusted and untrusted issuers.
9. Send a valid alpha-issuer JWT to the beta route: is `authenticated()` sufficient? Add tenant authorization.
10. Add an audience validator requiring `gateway-api` and test that a token from the same issuer with `aud=other-api` is rejected.
11. Place the API behind a reverse proxy and spoof `X-Forwarded-Host`; define the trust boundary.
12. Design runtime tenant onboarding: admin API, issuer allowlist, metadata validation, manager cache, disable/revoke, and multi-node sync.
13. Configure tenant B to use opaque introspection while A uses JWT; describe the managers and how to avoid fallback when introspection fails.
14. Run a performance test measuring first-request latency when the JWT resolver lazy-loads JWK metadata vs. subsequent requests.
15. Configure timeouts for the registry and decoder; ensure no `block()` runs on the Netty event loop.
16. Write security regression tests for CORS preflight and CSRF unsafe methods after adding a new route.
17. Verify that a Spring Cloud Gateway route to downstream never bypasses audience validation.
18. Audit logs and traces to ensure Authorization, cookies, client secrets, and sensitive JWT claims are redacted.

## Conclusion

`ReactiveAuthenticationManagerResolver<ServerWebExchange>` is an **authentication manager selector**, not an authenticator itself. In Spring Security WebFlux, an `AuthenticationWebFilter` extracts credentials via a converter, calls the resolver per request to pick a **ReactiveAuthenticationManager**, and that manager verifies the password/JWT/opaque token. In a multi-tenant Gateway, selectors such as URL/host/header/unverified `iss` may only be used to **pick from a set of trusted managers/issuers**; tenant permissions must be re-checked after authentication using verified claims/authorities and business policies. When accepting JWTs from multiple issuers, prefer `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)`; when tenants use different mechanisms, use a resolver or matcher-scoped chains while failing closed. A secure design maintains clear filter ordering, avoids double authentication, never blocks the event loop, avoids arbitrary issuer discovery, enforces a deny-all fallback, and tests cross-tenant boundaries across authentication, authorization, and downstream services.

## Official References

1. Spring Security 6.5 — Reactive OAuth2 Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html
2. Spring Security — ReactiveAuthenticationManagerResolver Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html
3. Spring Security — AuthenticationWebFilter Javadoc (resolver constructor, converter, matcher, failure): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
4. Spring Security 6.5 — JwtIssuerReactiveAuthenticationManagerResolver Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html
5. Spring Security 6.5 — ServerHttpSecurity.OAuth2ResourceServerSpec.authenticationManagerResolver: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2ResourceServerSpec.html
6. Spring Security 6.5 — ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver.html
7. Spring Security 6.3 — WebFlux Security multiple filter chains: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
8. Spring Security — Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
9. Spring Security — UserDetailsRepositoryReactiveAuthenticationManager Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
10. Spring Framework — Reactive WebFlux filter processing: https://docs.spring.io/spring-framework/reference/web/webflux.html
