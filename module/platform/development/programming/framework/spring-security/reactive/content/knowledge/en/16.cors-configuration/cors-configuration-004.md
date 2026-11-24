# CorsConfiguration and UrlBasedCorsConfigurationSource for WebFlux

## 1. The Problem to Solve: Frontend and API on Different Origins

A UI may run at `http://localhost:5173` (Vite/React/Vue), while the Spring WebFlux API runs at `http://localhost:8080`. These two URLs are **cross-origin** because their ports differ, even with the same hostname. A production system might use `https://app.example.test` for the frontend and `https://api.example.test` for the API; they are also cross-origin because their hosts differ.

Browsers enforce the Same-Origin Policy and the **Cross-Origin Resource Sharing (CORS)** mechanism when JavaScript calls an API at a different origin. If the server does not return appropriate CORS response headers, the browser may block JavaScript from reading the response or block the request during preflight. A `curl` command does not enforce browser CORS policies and can still read the same response. Therefore:

> **CORS is a browser policy governing cross-origin access permissions, not a login mechanism, not business authorization, and not a firewall blocking arbitrary HTTP clients.**

In Spring WebFlux, the two key components for configuring path-based CORS are:
- **`CorsConfiguration`** — describes which origins, HTTP methods, and request headers are accepted; whether the browser may send credentials; which response headers JavaScript may read; and how long preflights may be cached.
- **`org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`** — selects a `CorsConfiguration` based on the Reactive request's URL pattern.

Spring Security Reactive integrates this policy via `ServerHttpSecurity.cors(...)` so preflights are processed **before** authentication/authorization rejects requests lacking credentials.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish `origin` and `site`; know when a browser issues a CORS preflight.
2. Understand each field: `allowedOrigins`, `allowedOriginPatterns`, `allowedMethods`, `allowedHeaders`, `exposedHeaders`, `allowCredentials`, and `maxAge`.
3. Create a Reactive `UrlBasedCorsConfigurationSource`, mapping one or more route groups with distinct policies.
4. Connect the configuration source into `SecurityWebFilterChain` using the proper WebFlux DSL.
5. Distinguish CORS preflight, actual requests, authentication, authorization, and CSRF.
6. Run a Java 17+ Spring Boot WebFlux project, test `OPTIONS`, `GET`, `POST`, 200/401/403, and response headers.
7. Write `WebTestClient` tests for allowed origins, denied origins, denied methods/headers, credentials, and CSRF.
8. Avoid mixing Servlet CORS classes with Reactive ones or treating CORS as a substitute for access control.

## 2. What Is an Origin? When Is a Request Cross-Origin?

**Origin = scheme + host + port** of a URL; path and query string are not part of the origin comparison.

| Frontend | API | Cross-origin? | Reason |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:8080` | Yes | Different port |
| `https://app.example.test` | `https://api.example.test` | Yes | Different host |
| `https://api.example.test` | `https://api.example.test/v2` | No | Same scheme/host/port |
| `http://api.example.test` | `https://api.example.test` | Yes | Different scheme |
| `https://app.example.test` | `https://app.example.test:8443` | Yes | Different port |

**Same-origin differs from same-site.** Some subdomains with different origins can still be treated by the browser as same-site under cookie `SameSite` policy. Do not infer from cookies being sent that CORS allowed scripts to read the response, or from CORS allowing an origin that cookies are guaranteed to be sent by the browser.

A cross-origin `fetch` typically carries the header:

~~~http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

The server may return:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: text/plain

public-ok
~~~

The browser uses `Access-Control-Allow-Origin` to decide whether JavaScript from the requesting origin may read the response. Not every request includes an `Origin` header: normal `curl` calls may omit it, and same-origin navigation typically does not require CORS.

## 3. Simple Requests, Actual Requests, and CORS Preflight

CORS has two notable processing steps:

The **actual request** is the request performing the business operation, such as a GET fetching data or a POST creating a record. A **preflight request** is an HTTP `OPTIONS` request automatically sent by the browser before certain cross-origin actual requests to ask the server for permission to use the intended method and headers.

For example, suppose the browser wants to perform a POST with `Authorization` and `X-CSRF-TOKEN`:

~~~http
OPTIONS /api/items HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
~~~

The server may reply:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
~~~

This example illustrates header semantics; exact ordering, method/header lists, and status codes are determined by Spring and the processor. Do not assert exact raw header string formatting in tests. Once preflight succeeds, the browser can proceed to send the **actual POST**, yet that actual POST **must still pass** authentication, authorization, CSRF, and business validation.

### 3.1. Signals Identifying a True Preflight

An ordinary `OPTIONS` request **is not automatically a CORS preflight**. A preflight simultaneously includes:
- HTTP method `OPTIONS`;
- the `Origin` header;
- the `Access-Control-Request-Method` header;
- optionally `Access-Control-Request-Headers`.

Running `curl -X OPTIONS /api/items` alone and concluding CORS is broken is wrong: that request lacks the headers of a browser preflight.

### 3.2. Why Does Preflight Normally Carry No Credentials?

Under the browser CORS model, preflight does not send authentication credentials the way an authenticated actual request does; in particular, you should never require cookies or Basic credentials on an `OPTIONS` preflight to decide whether it is permitted. If security checks authentication before CORS runs, `OPTIONS` requests can receive 401/403 and the browser will not proceed to the actual request.

Spring Security Reactive supports processing CORS **before** the corresponding security checks. Configure a proper CORS source and integrate it via `ServerHttpSecurity.cors` or an appropriate `CorsWebFilter` instead of forcing every preflight through login.

### 3.3. Requests Without Preflight

Certain requests meeting **CORS-safelisted methods/headers/content types** conditions can proceed straight to the actual request without an `OPTIONS` preflight—for example, certain GETs and HTML form POSTs. CORS **does not guarantee** all cross-origin POSTs are stopped before reaching the server.

This relates directly to CSRF: an attacking website may not need to read the response or use JS at all to trigger an HTML form submission. CORS does not replace CSRF tokens.

## 4. CorsConfiguration: Role and Key Properties

The class used by both WebFlux and Spring Framework's common CORS configuration is:

~~~java
import org.springframework.web.cors.CorsConfiguration;
~~~

An explicit, allowlist-based configuration:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
        "http://localhost:5173",
        "https://app.example.test"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of(
        "Authorization", "Content-Type", "X-CSRF-TOKEN"));
cors.setExposedHeaders(List.of("X-Request-ID"));
cors.setAllowCredentials(true);
cors.setMaxAge(1800L);
~~~

This is a **snippet** (requiring `import java.util.List` inside a method/class), not a complete Java file. The demo section below provides a full runnable application.

| Property | Meaning | Risk when misconfigured |
| --- | --- | --- |
| `allowedOrigins` | Specific permitted origins | Broad wildcards or forgotten scheme/port |
| `allowedOriginPatterns` | Dynamic origin patterns, optionally with host/port wildcards | Admitting untrusted subdomains outside your trust boundary |
| `allowedMethods` | HTTP methods browsers may use in a CORS context | Unnecessarily allowing DELETE/PUT |
| `allowedHeaders` | Request header names allowed in preflight | Blocking `Authorization`/`X-CSRF-TOKEN` or overly broad wildcard |
| `exposedHeaders` | Response header names JS is allowed to read | Leaking unnecessary metadata or hiding `X-Request-ID` from JS |
| `allowCredentials` | Whether credentialed cross-origin browser access is allowed | Can expose session-authenticated data if origins are too broad |
| `maxAge` | Duration browsers may cache preflight results, in seconds | Confusing with token TTL/cookie lifetime or setting too long |

### 4.1. allowedOrigins: Must Include Exact Scheme and Port

`http://localhost:5173` differs from `http://localhost:3000` and `https://localhost:5173`. Your CORS policy should declare the exact frontend origins for each environment. Never take the client's `Origin` header and echo it into `Access-Control-Allow-Origin` **without checking an allowlist**.

Example:

~~~java
cors.setAllowedOrigins(List.of(
        "https://app.example.test",
        "https://admin.example.test"));
~~~

Both origins must be controlled by your organization and serve an appropriate purpose. CORS does not verify the identity of a script or user; it only checks whether the origin is permitted to call/read responses under the browser CORS mechanism.

### 4.2. allowedOriginPatterns for Dynamic Origins

When you need to allow a controlled set of subdomains, Spring Framework offers:

~~~java
cors.setAllowedOriginPatterns(List.of(
        "https://*.trusted.example.test"));
~~~

Compared with `allowedOrigins`, patterns can match multiple hosts. When `allowCredentials=true`, patterns are supported because the response echoes **the specific matched origin**, rather than a wildcard `*` in `Access-Control-Allow-Origin`.

**However, "supported by the framework" does not mean "safe by default".** If an attacker can claim a subdomain under `trusted.example.test`, they become an allowed origin. Use patterns only when DNS, hosting, tenant isolation, and subdomain issuance are strictly controlled.

### 4.3. allowedMethods Differs from Authorization Rules

~~~java
cors.setAllowedMethods(List.of("GET", "POST"));
~~~

This means a frontend at an allowed origin may use GET/POST under the CORS protocol. It does **not** mean the API allows anonymous POSTs, skips roles, or skips CSRF tokens. CORS governs browser communication permission; `SecurityWebFilterChain` authorization decides whether an identity/authority may invoke the route.

When changing an API to PUT/PATCH, review both CORS allowed methods **and** security authorization/CSRF rules; if either layer is missing, the browser may report an error.

### 4.4. allowedHeaders Differs from exposedHeaders

`allowedHeaders` specifies **which request headers the client may send** during CORS preflight, such as `Authorization`, `Content-Type`, and `X-CSRF-TOKEN`.

`exposedHeaders` specifies **which response headers JavaScript may read** beyond the safelisted response headers. For instance, an API returning `X-Request-ID` for debugging:

~~~java
cors.setExposedHeaders(List.of("X-Request-ID"));
~~~

For the client to read `X-Request-ID` via `response.headers.get("X-Request-ID")`, the response needs a matching `Access-Control-Expose-Headers`. Never place tokens, session IDs, or secrets into response headers just because CORS can expose them.

### 4.5. allowCredentials and Wildcard Origins

When setting:

~~~java
cors.setAllowCredentials(true);
~~~

the browser can accept credentialed cross-origin responses if the remaining CORS policies match. However:
- The frontend must still use `fetch(..., {credentials:"include"})` when cross-origin cookies/credentials are needed; not all credentials are sent automatically.
- The browser still enforces SameSite, Secure, third-party cookie policies, authentication caches, and its own rules.
- The API must still validate credentials and enforce authorization.
- The response requires `Access-Control-Allow-Credentials: true` under the proper conditions.
- **`Access-Control-Allow-Origin: *` cannot be used with credentialed requests.**

The configuration below is **invalid** for credentials:

~~~java
// INVALID: wildcard origin with credentials.
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
~~~

Spring Framework provides `CorsConfiguration.validateAllowCredentials()` to detect this case and can throw `IllegalArgumentException` during processing. Replace it with explicit origins:

~~~java
cors.setAllowedOrigins(List.of("https://app.example.test"));
cors.setAllowCredentials(true);
~~~

Do not use `allowedOriginPatterns(List.of("*"))` to "work around" this rule. Even though the framework echoes the specific matched origin, an overly broad pattern allows untrusted origins to read user data when the browser sends credentials.

### 4.6. maxAge Is a Cache TTL for Preflight

~~~java
cors.setMaxAge(1800L);
~~~

This corresponds to `Access-Control-Max-Age` of **1,800 seconds** (30 minutes), allowing the browser to cache the preflight decision per browser rules. This is **not**:
- session cookie expiration;
- JWT or refresh token lifetime;
- `WebSession` timeout;
- response body cache TTL;
- a "login validity" duration.

Browsers may enforce a lower cap or bypass the cache under certain conditions. When changing CORS policies, still deploy and configure properly rather than waiting on client cache expiration.

## 5. CorsConfiguration Defaults: Do Not Confuse with applyPermitDefaultValues

A newly constructed object:

~~~java
CorsConfiguration config = new CorsConfiguration();
~~~

**does not allow all origins by default**. If unconfigured, `CorsConfiguration` denies cross-origin requests by default.

There is a method:

~~~java
config.applyPermitDefaultValues();
~~~

It applies "conveniently open" defaults to unset fields, including:
- `allowedOrigins=["*"]` if no origins or origin patterns are set;
- HTTP methods GET, HEAD, POST;
- `allowedHeaders=["*"]`;
- `maxAge=1800` seconds.

These are intentional defaults of **that method**, distinct from an empty `new CorsConfiguration()`. If you also set `allowCredentials=true` without replacing the wildcard origins, the configuration becomes invalid.

**Recommendation:** write an explicit allowlist configuration instead of calling `applyPermitDefaultValues()` out of habit in APIs that restrict cross-origin access. CORS defaults in `WebFluxConfigurer.addCorsMappings` or `@CrossOrigin` can differ because the framework applies its own defaults upon registration; do not conflate those contexts.

## 6. UrlBasedCorsConfigurationSource: Mapping Policies by URL

For WebFlux, use the **Reactive package**:

~~~java
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
~~~

`UrlBasedCorsConfigurationSource` implements `CorsConfigurationSource`; its key methods are:

~~~java
// Illustrative signatures; not a complete Java class.
void registerCorsConfiguration(String path, CorsConfiguration config);
CorsConfiguration getCorsConfiguration(ServerWebExchange exchange);
~~~

Example:

~~~java
UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

source.registerCorsConfiguration("/api/**", apiCors);
source.registerCorsConfiguration("/public/**", publicCors);
~~~

This means a request entering CORS processing selects its policy based on the **WebFlux request's path pattern**, not on user roles or controller names. Methods, headers, and origins are then validated against the selected `CorsConfiguration`.

### 6.1. A Source Is Not a Filter

`UrlBasedCorsConfigurationSource` itself only **supplies configuration**. It neither blocks requests nor injects HTTP headers on its own. A CORS processor/filter must consume this source, such as:
- `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))`: integrates CORS into Spring Security Reactive.
- Spring Framework's `CorsWebFilter`: a Reactive `WebFilter` registered with the source.

**Do not enable both approaches unknowingly**, causing multiple CORS filters to process the same request. Choose **one CORS owner** and verify actual response headers and preflights.

### 6.2. Using Route-Specific Policies

Suppose you want a sensitive reporting API exposed only to an admin frontend:

~~~java
CorsConfiguration adminCors = new CorsConfiguration();
adminCors.setAllowedOrigins(List.of("https://admin.example.test"));
adminCors.setAllowedMethods(List.of("GET"));
adminCors.setAllowedHeaders(List.of("Authorization"));
adminCors.setAllowCredentials(true);

CorsConfiguration publicCors = new CorsConfiguration();
publicCors.setAllowedOrigins(List.of("https://app.example.test"));
publicCors.setAllowedMethods(List.of("GET"));
publicCors.setAllowedHeaders(List.of("Content-Type"));
publicCors.setAllowCredentials(false);

UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/admin/**", adminCors);
source.registerCorsConfiguration("/api/public/**", publicCors);
~~~

This is a configuration snippet that belongs inside a method with proper imports. URL patterns must **match the paths WebFlux sees after any reverse-proxy or context-path rewrite**. Do not widen a pattern to `/**` unnecessarily just to "make the frontend work".

### 6.3. What If a Path Has No Mapping?

If a preflight hits a URL with no matching CORS config, the CORS processor may **reject the preflight**; for an actual cross-origin request without configuration, the browser normally sees no matching `Access-Control-Allow-Origin` header and refuses to let scripts read the response. Exact behavior also depends on how filters/handlers are wired.

This **differs** from `anyExchange().denyAll()` in authorization:
- CORS config matches by path for **browser cross-origin access**.
- Security authorization matches by path, method, and authentication/authorities for **API permissions**.
- WebFlux `HandlerMapping` decides whether a route/controller exists.

A URL lacking a CORS mapping can still be called directly with `curl` if security permits it. CORS is not a mechanism for blocking non-browser access.

## 7. Spring Security Reactive: CORS Must Run Before Authentication

Spring Security states explicitly: **preflight must be processed before Spring Security authentication**, because preflight lacks credentials/session cookies the way actual requests have them. Otherwise, security treats preflight as anonymous and returns 401 before the browser knows whether the server allows the request.

The standard pattern in Spring Security 6.x WebFlux:

~~~java
return http
        .cors(cors -> cors.configurationSource(source))
        .authorizeExchange(ex -> ex
                .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
~~~

This is a snippet inside a `SecurityWebFilterChain` factory method, where `source` is the reactive `CorsConfigurationSource` created earlier. Per the `ServerHttpSecurity.CorsSpec` Javadoc, `configurationSource` accepts `org.springframework.web.cors.reactive.CorsConfigurationSource` and places `CorsWebFilter` at the proper order.

If you declare **a single** CORS source bean recognized by Spring Security, `.cors(Customizer.withDefaults())` can pick it up automatically; however, calling `configurationSource(source)` explicitly avoids ambiguity when multiple beans, chains, or configurations exist.

### 7.1. The Mistake of Using Servlet's CorsFilter

**Wrong for WebFlux**:

~~~java
// These classes are Servlet/MVC; DO NOT use them in WebFlux examples:
org.springframework.web.filter.CorsFilter
org.springframework.web.cors.UrlBasedCorsConfigurationSource
org.springframework.web.cors.CorsConfigurationSource
~~~

**Right for Reactive**:

~~~java
org.springframework.web.cors.reactive.CorsWebFilter
org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource
org.springframework.web.cors.reactive.CorsConfigurationSource
org.springframework.web.cors.CorsConfiguration
~~~

Two classes share the simple name `UrlBasedCorsConfigurationSource` across two packages. Incorrect IDE auto-import can cause compile errors or incompatibility with `ServerHttpSecurity.CorsSpec.configurationSource`. Always verify the full package of each import.

### 7.2. Why Isn't "permitAll OPTIONS /**" Enough?

~~~java
// Not a complete CORS solution.
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

This rule only changes **authorization** for `OPTIONS`. It **does not generate** `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`, or `Access-Control-Allow-Methods`, nor does it validate allowed origins. Without proper CORS headers on the response, the browser will still reject the request.

Never open all `OPTIONS` routes just to patch around a missing `CorsWebFilter`. Configure proper CORS integration and test preflights with full `Origin`, requested method, and requested headers.

### 7.3. CORS Does Not Automatically Disable CSRF

Even when a cross-origin POST preflight is approved, the **actual POST can still receive 403** due to a missing or invalid CSRF token. This holds for browsers using cookie logins, cached Basic credentials, or other ambient authentication mechanisms.

Two separate layers:

~~~text
OPTIONS preflight
   |
   +--> Origin/method/headers allowed by CORS?
         |
         +--> No  --> browser does not send valid actual request
         |
         +--> Yes --> Browser sends actual POST
                        |
                        +--> Valid authentication?
                        +--> Valid CSRF token if required?
                        +--> Sufficient authorization?
                        +--> Valid business request?
~~~

CORS is a **cross-origin communication policy**, while CSRF is **anti-forgery for state-changing operations**. Never disable `csrf()` just because preflight passed.

## 8. Three Ways to Configure CORS in WebFlux: Pick One Clear Owner

Spring Framework provides several CORS APIs:

| Approach | Where used? | Notes |
| --- | --- | --- |
| `CorsConfiguration` + reactive `UrlBasedCorsConfigurationSource` + `ServerHttpSecurity.cors` | Spring Security Reactive apps | **Main example's choice**; explicit source, filter ordered properly inside security chain |
| `CorsWebFilter(source)` bean | Spring WebFlux, functional routing, or standalone filter | Check interaction with Spring Security to avoid duplicate filters |
| `WebFluxConfigurer.addCorsMappings(CorsRegistry)` | Global `HandlerMapping` configuration | Good when no separate filter is needed; check ordering with Security |
| `@CrossOrigin` | Per controller/class/handler | Convenient for individual routes, hard to govern centrally at scale |

### 8.1. @CrossOrigin and Global CORS Can Combine

At the WebFlux `HandlerMapping` layer, global CORS config and `@CrossOrigin` can be combined: list properties such as origins, headers, and methods are typically merged, while single-valued fields like `allowCredentials` or `maxAge` follow override rules.

**Risk:** a `@CrossOrigin(origins="*")` annotation on a controller can widen origins unintentionally. Once you use `CorsWebFilter` or a Security CORS source as the primary layer, **do not assume** HandlerMapping CORS and filter CORS always combine the way you expect. Test actual responses per route.

### 8.2. Standalone CorsWebFilter Example (Do Not Combine With Primary Config)

~~~java
// Alternative snippet; do not add this bean in the main demo.
@Bean
CorsWebFilter corsWebFilter(
        UrlBasedCorsConfigurationSource source) {
    return new CorsWebFilter(source);
}
~~~

Import `org.springframework.web.cors.reactive.CorsWebFilter`. If you choose this path, clarify who handles `OPTIONS` ahead of authentication in the security chain, set filter ordering, and avoid duplicate CORS processing. When Spring Security already configures `cors(configurationSource(source))`, do not add this bean.

## 9. Runnable Project: Java 17 + WebFlux + CORS Source + Security

We will build a minimal yet complete project covering:
- Demo frontend origin `http://localhost:5173` and hypothetical production frontend `https://app.example.test`.
- CORS applied to `/api/**`, rejecting other origins.
- Methods `GET` and `POST`, headers `Authorization`, `Content-Type`, and `X-CSRF-TOKEN`.
- `allowCredentials=true` with explicitly listed origins.
- Exposed header `X-Request-ID`.
- Public GET allowed; private GET and items POST require HTTP Basic; items POST also requires CSRF.
- Endpoint `GET /api/csrf` to inspect Spring Security WebFlux's CSRF token/cookie.
- Separate tests for preflight, actual requests, credentials, and CSRF.

**Note:** Hardcoded Basic users/passwords and `{noop}` are strictly for local demos. Every real product needs HTTPS, a secure `PasswordEncoder`, proper authentication, domain authorization, and logging that never leaks secrets.

### 9.1. Structure

~~~text
webflux-cors-source/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/
        └── CorsSecurityTest.java
~~~

### 9.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-cors-source'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Requires JDK 17 and a compatible Gradle. If the project includes the Gradle Wrapper, use `./gradlew` or `gradlew.bat`. The Spring Boot BOM coordinates compatible Spring Framework, Spring Security, and Reactor versions. `3.5.7` is a fixed example baseline; production apps should follow supported release branches and current security patches per organizational policy.

### 9.3. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java — Combining CorsConfiguration and Reactive Source

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(
                "http://localhost:5173",
                "https://app.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {
        return http
                .cors(cors -> cors.configurationSource(
                        corsConfigurationSource))
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/public")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/private")
                                .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/csrf")
                                .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/items")
                                .authenticated()
                        .pathMatchers(HttpMethod.POST, "/api/items")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

Reading the configuration decision by decision:

1. `new CorsConfiguration()` does not open a wildcard origin; every field is set explicitly.
2. `allowedOrigins` contains only the two approved simulated origins. Port `5173` is part of the local origin.
3. `setAllowedMethods` enables GET and POST. PUT and DELETE are absent from the CORS policy.
4. `allowedHeaders` includes `Authorization` and the CSRF header so actual POSTs can pass preflight.
5. `exposedHeaders` lets JS read `X-Request-ID` returned by the endpoint.
6. `allowCredentials(true)` is valid only with explicit origins, never `*`.
7. `registerCorsConfiguration("/api/**", cors)` applies the policy strictly to the API namespace; other routes do not automatically get CORS.
8. `http.cors(cors -> cors.configurationSource(...))` instructs Spring Security to process CORS at the right position; no extra `CorsWebFilter` bean is needed.
9. `authorizeExchange` is an **independent security policy**: public, authenticated, and deny by default.
10. `csrf(Customizer.withDefaults())` preserves default protection on POST; **CORS allowing POST does not remove CSRF**.

**Production security:** the two origins in this lesson are simulated/localhost. In deployment, configure allowlists per environment, remove demo users/passwords, and enforce HTTPS plus real token/password policies. Never allow arbitrary origins with credentials.

### 9.5. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final AtomicReference<String> item =
            new AtomicReference<>("initial");

    @GetMapping(path = "/api/public",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicData() {
        return Mono.just("public-ok");
    }

    @GetMapping(path = "/api/private",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> privateData() {
        return Mono.just(ResponseEntity.ok()
                .header("X-Request-ID", "demo-request-1")
                .body("private-ok"));
    }

    @GetMapping("/api/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is unavailable"));
        }

        return token.map(t -> Map.of(
                "headerName", t.getHeaderName(),
                "token", t.getToken()));
    }

    @GetMapping(path = "/api/items",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> readItem() {
        return Mono.fromSupplier(item::get);
    }

    @PostMapping(path = "/api/items",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> saveItem(@RequestBody Mono<String> body) {
        return body.map(text -> {
            item.set(text);
            return "saved:" + text;
        });
    }
}
~~~

Purpose of each endpoint:
- Public GET demonstrates CORS on an endpoint requiring no login.
- Private GET requires Basic auth and returns `X-Request-ID` to demonstrate `exposedHeaders`; the ID value is a demo constant with no sensitive data.
- `/api/csrf` uses the `Mono<CsrfToken>` provided by `CsrfWebFilter`; the client sends the token value presented by the request handler rather than unmasking raw session tokens itself.
- POST updates `AtomicReference`, requiring CORS, Basic auth, and CSRF. Data lives only in process memory, not production persistence.
- No manual `block()` or `subscribe()` calls appear in the WebFlux controller.

## 10. Running curl to Observe Preflight in Action

In the directory containing `build.gradle`:

~~~bash
gradle bootRun
~~~

If using the Wrapper, run `./gradlew bootRun`. The server listens on `http://localhost:8080` by default; HTTP is strictly for local demos.

### 10.1. Preflight from an Allowed Origin

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-csrf-token'
~~~

Expected: preflight is accepted by the CORS processor, typically **HTTP 200 OK**, with headers showing:
- `Access-Control-Allow-Origin: http://localhost:5173`;
- `Access-Control-Allow-Methods` containing POST;
- `Access-Control-Allow-Headers` permitting the requested headers;
- `Access-Control-Allow-Credentials: true`;
- `Access-Control-Max-Age: 1800`;
- matching `Vary` headers.

**No need** to pass `-u learner:localpass` on preflight. If `OPTIONS` returns 401 for missing Basic auth, inspect CORS integration and filter ordering; never "fix" it by adding an Authorization header to simulated OPTIONS while ignoring real browser behavior.

### 10.2. Preflight from a Disallowed Origin

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Expected: the CORS processor **rejects** it, typically returning **403 Forbidden** or a response that prevents the browser from continuing. `Access-Control-Allow-Origin: https://untrusted.example.test` must never appear when that origin is outside policy.

### 10.3. Preflight for a Disallowed Method

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Even with a valid origin, DELETE is not in `allowedMethods`, so preflight is rejected. This is a **CORS rule**, not proof of Security authorization on DELETE, since the request never reaches an actual DELETE.

### 10.4. Preflight for a Disallowed Header

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: x-not-approved'
~~~

Expected rejection because `x-not-approved` is not in `allowedHeaders`. Do not rush to add `*`; verify whether the frontend truly needs that header and what state or exposure it could introduce.

### 10.5. Actual GET from a Valid Origin

~~~bash
curl -i http://localhost:8080/api/public \
  -H 'Origin: http://localhost:5173'
~~~

Expected **200** with body `public-ok` and the matching `Access-Control-Allow-Origin`. Running `curl` directly without `Origin` still returns 200 without needing CORS headers—that is not a CORS error.

### 10.6. Actual GET with Basic Authentication

~~~bash
# Missing credentials: auth is rejected (typically 401),
# yet the allowed origin is still processed by CORS.
curl -i http://localhost:8080/api/private \
  -H 'Origin: http://localhost:5173'

# With valid demo credentials.
curl -i -u learner:localpass \
  http://localhost:8080/api/private \
  -H 'Origin: http://localhost:5173'
~~~

Private GET without Basic typically returns **401**; with valid Basic auth it returns **200** with `private-ok`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, and `Access-Control-Expose-Headers: X-Request-ID`. Browsers let JS read non-safelisted headers like `X-Request-ID` only if exposed.

### 10.7. CORS Allows POST Yet CSRF Can Still Return 403

~~~bash
curl -i -u learner:localpass \
  http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: text/plain' \
  --data 'without-csrf'
~~~

Without a CSRF token, Spring Security can return **403 Forbidden**, even though CORS permitted the origin, method, and header. This does not indicate broken CORS; keep the CORS and CSRF layers distinct.

### 10.8. Fetching a CSRF Token for a Valid POST

With `curl` and `jq` in a Bash-style shell:

~~~bash
# Fetch token and store the WebSession cookie.
curl -sS -u learner:localpass \
  -c csrf-cookies.txt \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/csrf > csrf.json

HEADER="$(jq -r '.headerName' csrf.json)"
TOKEN="$(jq -r '.token' csrf.json)"

# Send Basic + WebSession cookie + CSRF token together.
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H 'Origin: http://localhost:5173' \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'with-csrf' \
  http://localhost:8080/api/items

curl -i -u learner:localpass \
  http://localhost:8080/api/items
~~~

When cookie and token belong to the same session, expected output:

~~~text
POST /api/items -> HTTP 200; body: saved:with-csrf
GET  /api/items -> HTTP 200; body: with-csrf
~~~

Browsers must still satisfy `credentials` mode, SameSite, and CORS; `curl` skips many browser policies yet is handy for confirming the server returns the expected headers.

Never log real tokens, cookies, or passwords or paste them into shared tools. The files `csrf.json` and `csrf-cookies.txt` are for local runs only and must never be committed to a real repository.

## 11. WebTestClient: Properly Testing the CORS Source and Spring Security

Include `spring-boot-starter-test` and `spring-security-test` as in `build.gradle` above. `WebTestClient` can issue requests with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` and assert response status and headers. For security integration, apply `springSecurity()`.

`src/test/java/demo/CorsSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsSecurityTest {

    private static final String ALLOWED = "http://localhost:5173";
    private static final String DENIED = "https://untrusted.example.test";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void permittedPreflightWorksWithoutAuthentication() {
        client.options().uri("/api/items")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "authorization,content-type,x-csrf-token")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin", ALLOWED)
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Credentials", "true");
    }

    @Test
    void unknownOriginPreflightIsForbidden() {
        client.options().uri("/api/items")
                .header("Origin", DENIED)
                .header("Access-Control-Request-Method", "POST")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownMethodPreflightIsForbidden() {
        client.options().uri("/api/items")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "DELETE")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownHeaderPreflightIsForbidden() {
        client.options().uri("/api/items")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "x-not-approved")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void allowedOriginCanReadPublicResponse() {
        client.get().uri("/api/public")
                .header("Origin", ALLOWED)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin", ALLOWED)
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateRouteWithoutCredentialsIs401() {
        client.get().uri("/api/private")
                .header("Origin", ALLOWED)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void allowedOriginWithBasicCanReadPrivateData() {
        client.get().uri("/api/private")
                .header("Origin", ALLOWED)
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin", ALLOWED)
                .expectHeader().valueEquals(
                        "Access-Control-Expose-Headers", "X-Request-ID")
                .expectBody(String.class).isEqualTo("private-ok");
    }

    @Test
    void disallowedOriginCannotUseActualCorsRequest() {
        client.get().uri("/api/public")
                .header("Origin", DENIED)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void actualPostWithoutCsrfIs403EvenWhenCorsAllowsIt() {
        client.post().uri("/api/items")
                .header("Origin", ALLOWED)
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not-allowed")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithBasicAndCsrfPasses() {
        client.mutateWith(csrf())
                .post().uri("/api/items")
                .header("Origin", ALLOWED)
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("allowed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("saved:allowed");
    }

    @Test
    void sameOriginStyleRequestStillNeedsAuthentication() {
        // Without Origin: CORS is not authentication.
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected:** 11 tests reflecting the 200/401/403 scenarios in the example policy. This is an API-based analysis, **not a claim that Gradle was run in this environment**. Error 403 bodies can vary across Spring Security versions; tests should assert status codes and key headers rather than full error pages.

### 11.1. Why Does the OPTIONS Test Provide No Credentials?

That is a key property to verify: **preflight runs before authentication**, and the policy depends on `Origin`, requested method, and requested headers—not user roles. The subsequent actual request is authenticated separately.

### 11.2. Why Does the POST with Valid Basic Auth Return 403?

Because Spring Security's default CSRF still blocks a POST missing a CSRF token. The `csrf()` test proves that when a valid token is present, CORS + authentication + route handling work together. It is not a mechanism to bypass CSRF in real environments.

### 11.3. Why Don't Tests Replace a Real Browser?

`WebTestClient` sends HTTP requests to WebFlux and inspects responses; it **does not simulate all browser decisions** such as third-party cookies, SameSite, credential caches, or preflight caching. Supplement with E2E tests in supported browsers and check the Network tab to confirm the real frontend works.

## 12. Frontend JavaScript Example

This snippet illustrates the fetch flow from `http://localhost:5173` to the WebFlux API at `http://localhost:8080`:

~~~javascript
const API = "http://localhost:8080";

// Public GET case: no credentials required.
const publicResponse = await fetch(API + "/api/public");
if (!publicResponse.ok) throw new Error("Public API rejected");
console.log(await publicResponse.text());

// Protected GET case: assumes the browser already holds valid
// credentials/session per the application's login flow.
const privateResponse = await fetch(API + "/api/private", {
  credentials: "include"
});
if (!privateResponse.ok) throw new Error("Authentication required");
console.log(privateResponse.headers.get("X-Request-ID"));

// Protected POST case: token must be fetched from the API within the
// same session context. Obtaining Basic credentials depends on your
// real login flow and must never be hardcoded in frontend code.
const csrfResponse = await fetch(API + "/api/csrf", {
  credentials: "include"
});
if (!csrfResponse.ok) throw new Error("CSRF token unavailable");
const csrf = await csrfResponse.json();

const saveResponse = await fetch(API + "/api/items", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "text/plain",
    [csrf.headerName]: csrf.token
  },
  body: "new-value"
});
if (!saveResponse.ok) throw new Error("Update rejected");
~~~

**This is not a complete frontend**; it assumes the browser already has valid Basic credentials or an integrated login flow. `credentials:"include"` does not fabricate a username/password the browser lacks. For easy local verification, use `curl -u` on the server side and test with a real frontend once your authentication flow is designed.

For cookies, browsers also evaluate `SameSite`, `Secure`, and third-party cookie restrictions. Allowing CORS credentials **only lets the browser accept credentialed responses under qualifying conditions**; it does not force the browser to send any cookie.

## 13. CORS + CSRF + SameSite + Authorization: None Replaces Another

A sound design separates four distinct questions:

| Control | Question it addresses | What it does NOT guarantee |
| --- | --- | --- |
| CORS | May a script from origin A read/interact with B's response in a browser? | Who the user is, their permissions, or whether the request was intentional |
| Authentication | Do the credentials verify an identity? | Whether the resource may be accessed |
| Authorization | Does the user/role/authority/tenant have rights on the route/object? | That the browser wasn't tricked into sending an unintended action |
| CSRF | Does a browser-originated state-changing request carry a trusted token/context? | That the user holds the right role or ownership |
| SameSite cookies | Will the browser send cookies in specific site contexts? | Protection against all CSRF, CORS, or HTTP Basic issues |
| XSS controls | Can malicious script run inside a trusted origin? | Full authentication/authorization |

### 13.1. Never Treat CORS as "Protecting an API from curl"

CORS is enforced primarily by **browsers**. Any standard HTTP client can set or omit `Origin` freely and read responses regardless of `Access-Control` headers. An API wishing to block unauthorized clients must use authentication, authorization, network controls, rate limits, and other defenses; it cannot rely on CORS alone.

### 13.2. SameSite Is Not Same-Origin

`https://a.example.test` and `https://b.example.test` are cross-origin yet same-site. A `SameSite` cookie may be sent in certain contexts even though JavaScript remains governed by CORS between the two origins. Conversely, an allowlisted CORS origin does not guarantee third-party cookies will be sent by the browser.

### 13.3. A Passing Preflight Grants Zero POST Permissions

A request with:
- a valid Origin;
- POST in allowed methods;
- valid headers;

can still receive 401 for missing credentials, 403 for insufficient role or missing CSRF token, 400 for an invalid request body, or 409 for a business conflict. Preflight is merely a step before the actual request.

## 14. Managing Multiple Frontend Origins and Environments

### 14.1. Local, Staging, and Production

Each environment should maintain its own list of origins, for example:

| Environment | Controlled Frontend | API |
| --- | --- | --- |
| Local | `http://localhost:5173` | `http://localhost:8080` |
| Staging | `https://app.staging.example.test` | `https://api.staging.example.test` |
| Production | `https://app.example.test` | `https://api.example.test` |

**Never** leave localhost origins in production configuration merely for developer convenience. If you have an admin frontend, consider a dedicated allowlist for the admin namespace and audit DNS, deployment ownership, and subdomain takeover risks.

Origins can be loaded from environment-specific configuration:

~~~yaml
app:
  cors:
    allowed-origins:
      - https://app.example.test
      - https://admin.example.test
~~~

This YAML is an **example custom property design**, not a Spring Boot auto-configured CORS property. To use it, bind it with `@ConfigurationProperties`/`@Value` and wire it into `CorsConfiguration` properly; do not assume dropping this YAML in place gives your app CORS automatically.

### 14.2. Never Reflect Origins Without Verification

Insecure pattern:

~~~java
// INSECURE PSEUDOCODE: never copy into production.
// response.header("Access-Control-Allow-Origin",
//                 request.header("Origin"));
// response.header("Access-Control-Allow-Credentials", "true");
~~~

If the server accepts any `Origin` and reflects it alongside credentials, an attacker's website becomes an allowed origin able to read sensitive user data whenever the browser sends credentials. **Always validate against a trusted allowlist** before selecting an origin.

### 14.3. Evolving CORS Policies Across Releases

When onboarding a new frontend:
1. Review origin ownership and authentication mechanisms.
2. Identify the required endpoints and HTTP methods.
3. Add only the request headers actually used.
4. Decide whether credentialed access is required.
5. Design CSRF tokens/cookies for browser flows.
6. Deploy the policy and test preflight on staging and production.
7. Monitor error metrics without logging tokens or credentials.
8. Audit periodically and retire unused origins.

## 15. Common Configuration Mistakes

| Mistake | Symptom or consequence | Fix |
| --- | --- | --- |
| Importing `org.springframework.web.cors.UrlBasedCorsConfigurationSource` in WebFlux | Wrong source type for Reactive API | Use `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| Using Servlet `CorsFilter` or `HttpSecurity` | Config does not apply to Reactor WebFilter chain | Use `CorsWebFilter` and `ServerHttpSecurity` |
| `new CorsConfiguration()` with no origins set | Preflights are rejected | Declare an origin allowlist |
| Calling `applyPermitDefaultValues()` blindly | May open wildcard origins | Set an explicit policy |
| `allowedOrigins("*")` with `allowCredentials(true)` | Invalid combination | List explicit trusted origins |
| `allowedOriginPatterns("*")` with credentials just to avoid exception | Lets any origin read sensitive data | Use narrow patterns/allowlist |
| Missing port in local origin | `localhost:5173` does not match `localhost:3000` | Match exact scheme/host/port |
| Missing `Authorization` in `allowedHeaders` | Preflights requesting Basic/Bearer fail | Allow the exact headers needed |
| Confusing `exposedHeaders` with `allowedHeaders` | Browser cannot read response header despite 200 | Use `exposedHeaders` for response headers |
| Using only `permitAll OPTIONS` | Missing CORS response headers | Integrate a proper CORS source/filter |
| Preflight returns 401 | Authentication runs before CORS | Configure `ServerHttpSecurity.cors`/`CorsWebFilter` properly |
| Preflight 200 yet POST returns 403 | Missing CSRF token or insufficient role | Check CSRF/authz; do not blindly disable CSRF |
| Omitting `credentials:"include"` | Browser drops cookies/credentials on cross-origin fetch | Check login flow, SameSite, and CORS |
| CORS permits origin yet browser withholds cookies | Cookie SameSite/Secure/third-party policy | Inspect Set-Cookie and Network tab |
| Treating `maxAge` as session timeout | Mismatched client/cache expectations | Separate preflight TTL from session/token TTL |
| Creating both a `CorsWebFilter` bean and Security `.cors` for the same source | Possible duplicate processing | Choose a single CORS owner |
| `@CrossOrigin(origins="*")` on sensitive route | Overly broad origin policy | Centralize allowlist and test per endpoint |
| Unaccounted reverse proxy path rewrite | `/api/**` misses the path Spring sees | Test the path seen by WebFlux behind the proxy |
| Treating `curl 200` as browser CORS PASS | curl does not enforce CORS | Verify with browser E2E/DevTools |
| Using CORS in place of authentication/CSRF | API remains callable or vulnerable to CSRF | Keep security controls independent |

## 16. Concrete CORS Debugging Workflow

When the frontend reports "blocked by CORS policy", check in order:

1. **Identify the actual origin:** inspect `Origin` in DevTools, including scheme and port. Do not guess from the visible URL bar alone.
2. **Inspect OPTIONS preflight:** are both `Origin` and `Access-Control-Request-Method` present? What are the requested headers?
3. **Verify the source:** does the bean import `...cors.reactive.UrlBasedCorsConfigurationSource`? Does `registerCorsConfiguration` match the path?
4. **Security integration:** is CORS processed before auth? If `OPTIONS` returns 401, check `ServerHttpSecurity.cors`.
5. **Response headers:** does `Access-Control-Allow-Origin` match `Origin`? Are `Allow-Methods` and `Allow-Headers` sufficient?
6. **Credentials:** does the frontend pass `credentials:"include"`? Does the API allow credentials with explicit origins? Is the browser blocking cookies via SameSite/third-party rules?
7. **CORS vs. auth:** does the actual GET/POST return 401/403? Read the server response rather than concluding from one console CORS line.
8. **CSRF:** is the POST missing `X-CSRF-TOKEN` or the `WebSession` cookie? Is the CSRF filter returning 403?
9. **Proxies:** is a CDN or gateway adding/stripping `Access-Control-*` headers, mis-caching by Origin, or rewriting paths?
10. **Multiple chains:** which `SecurityWebFilterChain` did the request match? Does that chain have the right CORS source?
11. **Multiple CORS owners:** are a `CorsWebFilter` bean, `WebFluxConfigurer`, or `@CrossOrigin` conflicting with `ServerHttpSecurity.cors`?
12. **Test across real browsers:** Safari, Firefox, and Chrome enforce different policies around cookies, private network requests, and preflight caching.
13. **Assess exposure:** never turn on broad wildcards for origins, headers, or credentials just to make errors disappear.
14. **Log safely:** correlation IDs, methods, route templates, and origins may be logged if policy permits; never log `Authorization`, session IDs, or CSRF tokens.

### 16.1. Distinguishing Symptoms

| Symptom | Likely cause | Action |
| --- | --- | --- |
| OPTIONS returns 401 | Security intercepts preflight before CORS | Integrate CORS source in security chain |
| OPTIONS returns 403 | Disallowed origin/method/header, or another security rule | Compare requested values against config |
| OPTIONS 200 yet browser does not send POST | Invalid CORS headers or mismatched credentials policy | Check allow-origin/method/header/credentials |
| GET 200 in curl, CORS error in browser | curl does not enforce Same-Origin Policy | Inspect Network/console and response headers |
| Authenticated GET still returns 401 | Missing/invalid credentials | Debug authentication; do not alter allowed origins |
| POST with valid Basic returns 403 | CSRF or authorization | Verify valid token and permissions |
| JS cannot read `X-Request-ID` | Missing `exposedHeaders` | Add response header to exposed list |
| Cookie not sent in fetch | credentials mode / SameSite / Secure / 3rd-party | Inspect browser cookie policy |
| One endpoint has CORS, another lacks it | Different URL registration or security chain | Check `/api/**`, `/admin/**`, and matcher priority |
| Policy changed yet client sees old behavior | Cached preflight or CDN/gateway cache | Check `Access-Control-Max-Age` and `Vary: Origin` |

### 16.2. Role of Vary

When the server returns different `Access-Control-Allow-Origin` values per request `Origin`, HTTP caches and intermediaries must know the response varies by `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`. The CORS processor normally adds appropriate `Vary` headers, yet with custom CDNs/proxies you should inspect cache keys so one origin's response/CORS policy is never served to another origin.

Never strip `Vary` to "boost cache hit rates" on resources with origin-dependent CORS policies.

## 17. Self-Check Exercises

**Q1.** Is `http://localhost:5173` calling `http://localhost:8080` cross-origin?

> Yes, because an origin consists of scheme, host, and port, and the ports differ.

**Q2.** What distinct tasks do `CorsConfiguration` and `UrlBasedCorsConfigurationSource` perform?

> `CorsConfiguration` describes the policy; reactive `UrlBasedCorsConfigurationSource` selects the policy by the request's URL path. The filter/processor performs the actual checks and writes response headers.

**Q3.** In WebFlux, from which package should `UrlBasedCorsConfigurationSource` be imported?

> `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`, not Servlet's `org.springframework.web.cors`.

**Q4.** Why should `OPTIONS` preflight not require login?

> Browser preflight checks CORS before sending the actual request and typically carries no credentials; security must process CORS ahead of authentication.

**Q5.** Can `allowCredentials(true)` be paired with `allowedOrigins("*")`?

> No. Credentialed responses cannot carry a wildcard `Access-Control-Allow-Origin`; specify trusted origins explicitly or use carefully reviewed narrow patterns.

**Q6.** How does `allowedHeaders` differ from `exposedHeaders`?

> Allowed headers are request headers the browser is allowed to send; exposed headers are response headers JavaScript is allowed to read.

**Q7.** Does `maxAge=1800` keep a `WebSession` alive for 30 minutes?

> No. It governs only how long the CORS preflight result may be cached.

**Q8.** Does `OPTIONS` 200 prove the actual POST will succeed?

> No. The actual request still requires authentication, authorization, CSRF, and business validation.

**Q9.** Why doesn't CORS protect an API from `curl`?

> CORS is enforced primarily by browsers; non-browser HTTP clients can call the API independently. Authentication and authorization enforce access control.

**Q10.** Why isn't `pathMatchers(HttpMethod.OPTIONS,"/**").permitAll()` sufficient?

> It only opens authorization for `OPTIONS`; it does not generate CORS allow headers or validate `Origin`.

**Q11.** If `Access-Control-Allow-Origin` is right yet JS still cannot read `X-Request-ID`, what should you check?

> Check `Access-Control-Expose-Headers`/`setExposedHeaders`.

**Q12.** Why does a cookie-session app still need CSRF protection even when CORS restricts origins?

> Browsers can send certain cross-origin requests without the attacker needing to read the response; CORS does not prove the user intentionally initiated the action.

## 18. Code Review and Production Checklist

### Configuration
- [ ] Reactive WebFlux APIs selected properly; no Servlet classes imported.
- [ ] `CorsConfiguration` lists organization-controlled origins with exact schemes and ports.
- [ ] `allowedOriginPatterns`, if used, has been audited for subdomain takeover/tenant risks.
- [ ] `allowCredentials` is enabled only when needed and never paired with wildcard `allowedOrigins("*")`.
- [ ] Methods, request headers, and exposed response headers are minimal.
- [ ] `maxAge` is a reasonable preflight TTL, not confused with session/token TTL.
- [ ] `UrlBasedCorsConfigurationSource` covers the exact route namespace.
- [ ] `ServerHttpSecurity.cors` processes preflight before authentication.
- [ ] No unintended duplicate CORS filters or owners.
- [ ] Security rules do not substitute CORS for authentication/authorization.

### Browser/Client
- [ ] Frontend sends the proper credentials mode and required headers.
- [ ] Session cookies have appropriate `Secure`/`HttpOnly`/`SameSite` attributes.
- [ ] Browser POSTs carry valid CSRF tokens/flows when required.
- [ ] Tested in real browsers, not only with curl.
- [ ] Verified login/logout/token rotation and third-party cookie restrictions.

### Testing
- [ ] Preflight with allowed origin, requested method, and headers succeeds **without authentication**.
- [ ] Preflight from denied origin is rejected.
- [ ] Preflight for denied method is rejected.
- [ ] Preflight for denied header is rejected.
- [ ] Actual GET from allowed origin returns ACAO and expected body.
- [ ] Actual GET from denied origin is blocked per policy.
- [ ] Protected GET without credentials still returns 401.
- [ ] Valid Basic credentials with allowed origin returns 200.
- [ ] POST permitted by CORS yet missing CSRF still returns 403.
- [ ] POST with CSRF, auth, and allowed origin genuinely succeeds.
- [ ] Browser/DevTools verifies exposed response headers.
- [ ] No responses are mis-cached across different Origins.
- [ ] Reverse proxy, CORS source, security chain, and `HandlerMapping` agree on the expected paths.

## 19. Summary

`CorsConfiguration` and the **reactive** `UrlBasedCorsConfigurationSource` form an allowlist-based WebFlux CORS configuration: which origins are permitted, which methods/headers may be used, which response headers JS may read, and how long browsers may cache preflights.

In Spring Security Reactive, the key integration point is:

~~~java
.cors(cors -> cors.configurationSource(corsConfigurationSource))
~~~

where `corsConfigurationSource` is a bean/source of type `org.springframework.web.cors.reactive.CorsConfigurationSource`. This ensures preflights are handled in the proper place instead of being rejected by authentication.

Three rules to remember:
1. **CORS is not authentication or authorization**; APIs still must verify users, permissions, and data.
2. **CORS does not replace CSRF**; actual browser POSTs can still require a CSRF token even after OPTIONS succeeds.
3. **Origin allowlists and credentials must be deliberate**; strictly avoid wildcard origins with cookies or credentialed cross-origin access.

### Official References

- Spring Security Reference — CORS for WebFlux: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security Javadoc — ServerHttpSecurity.CorsSpec: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Framework Reference — CORS for WebFlux: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html
- Spring Framework Javadoc — CorsConfiguration: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Framework Javadoc — Reactive UrlBasedCorsConfigurationSource: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/cors/reactive/UrlBasedCorsConfigurationSource.html
- Spring Framework Javadoc — CorsWebFilter: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Fetch credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials