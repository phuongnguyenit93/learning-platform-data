# Environment-Specific Origin Allowlists and Avoiding Arbitrary Origin Reflection in Spring Security Reactive

## 1. Real-World Problem and Objectives

A Java application built with **Spring WebFlux** may serve a REST API at api.example.org, while the frontend runs at localhost:5173 during development, staging-ui.example.org during testing, and app.example.org in production. Browsers treat these addresses as **different origins**, even when all belong to the same company. If the API needs to let the frontend make cross-origin calls, the server must configure **CORS (Cross-Origin Resource Sharing)** appropriately.

Two common yet dangerous misconfigurations are:

- Opening CORS to every website so that "any frontend can call it".
- Reading the client-supplied **Origin** header and echoing that exact value into **Access-Control-Allow-Origin** without validating against a trusted list.

The second pattern is called **arbitrary origin reflection**. If paired with **Access-Control-Allow-Credentials: true**, an untrusted website may be allowed by the browser to read API responses carrying a user's valid cookies or credentials when other credential conditions also permit. CORS does not create a login on its own, yet it can expose sensitive data from an already active session.

Lesson objectives:

1. Understand precisely what an **origin** is and how CORS affects browsers.
2. Distinguish **Origin**, **Access-Control-Allow-Origin**, **Access-Control-Allow-Credentials**, and **Vary: Origin**.
3. Grasp the difference between **simple/actual requests** and **OPTIONS preflight**.
4. Define an **exact allowlist per environment (local, staging, production)**; configure **fail-closed** behavior when missing or malformed.
5. Never pair **allowOrigins("*")** with credentials, never reflect arbitrary Origins, and never write overly broad regex or suffix checks.
6. Use the proper Spring Security **Reactive** APIs: **CorsConfiguration**, **CorsConfigurationSource**, **UrlBasedCorsConfigurationSource**, and **ServerHttpSecurity.cors(...)**.
7. Build a Java 17+, Spring Boot WebFlux demo with HTTP Basic, CORS preflight before authentication, and public/private/admin GET policies.
8. Test with **WebTestClient**: allowed/denied origins, credentials, preflight, actual requests, disallowed methods/headers, and false positives with lookalike domains.
9. Recognize the limits of CORS: **CORS does not replace authentication, authorization, CSRF, tenant/owner checks, or API security for non-browser clients**.

**End goal:** each environment maintains an origin list controlled by the deployment team; only genuinely approved origins receive CORS allow headers. When promoting from local to staging/prod, the policy must never silently widen or accept attacker-chosen Origins.

## 2. What Is an Origin?

A **web origin** is defined primarily by the tuple **scheme + hostname + port**. Path, query, and fragment **do not** belong to the origin.

Examples:

| URL | Origin | Compared to https://app.example.org |
| --- | --- | --- |
| https://app.example.org/home | https://app.example.org | Same origin |
| https://app.example.org:443/home | https://app.example.org (default port per browser) | Semantically same origin |
| http://app.example.org | http://app.example.org | **Different** scheme |
| https://app.example.org:8443 | https://app.example.org:8443 | **Different** port |
| https://api.example.org | https://api.example.org | **Different** hostname |
| https://preview.app.example.org | https://preview.app.example.org | **Different** subdomain |
| http://localhost:5173 | http://localhost:5173 | Different origin from production app |

A website at **https://evil.example.net** is not trustworthy just because its URL contains words like "app", "trusted", "example", or looks similar to a real domain.

The **Origin** header typically looks like:

~~~http
Origin: https://app.example.org
~~~

It **never** contains the `/dashboard` path or `?token=...` query. In Spring configuration, **allowedOrigins** must list **explicit origins**, not full URLs with paths:

~~~text
Right: https://app.example.org
Wrong: https://app.example.org/dashboard
Wrong: https://app.example.org/
Wrong: https://*.example.org (if placed in allowedOrigins)
~~~

If wildcard subdomains are needed, Spring offers **allowedOriginPatterns**; that is a separate mechanism and patterns must still be constrained by trust boundaries. In this lesson, we deliberately **avoid patterns** to eliminate ambiguity.

### 2.1. Origin Differs from Site

"Site" in the context of **SameSite** cookies does not necessarily match origin. For instance, app.example.org and api.example.org may share the same "site" under the registrable domain concept yet remain **two distinct origins**. Consequently, setting SameSite=Lax or Strict does not mean CORS automatically permits every subdomain.

Third-party-managed subdomains, preview deployments, CDN hosts, or hijackable subdomains **must not be automatically trusted** simply for sharing a registrable domain. CORS distinguishes at the origin level; cookie Domain and CSRF introduce additional security boundaries that require separate evaluation.

## 3. What Does CORS Solve, and What Does It Not Solve?

The **Same-Origin Policy** restricts JavaScript in one origin from reading responses from another origin. CORS is the mechanism by which a server **grants controlled exceptions** through HTTP response headers verified by the browser.

CORS is not a server firewall. curl, Postman, backend services, or bots can send HTTP requests without browsers enforcing the Same-Origin Policy. An attacker can still call your API directly from their own server if the endpoint allows it; authentication and authorization must protect data independently of `Origin`.

| Need | Does CORS solve it? | Actual mechanism |
| --- | --- | --- |
| Cross-origin frontend reading permitted responses | **Yes** | CORS response headers |
| Requiring user login | **No** | Authentication: session, Basic, bearer/OIDC |
| Blocking regular users from reading admin resources | **No** | Authorization and roles/permissions |
| Blocking users from reading another tenant's resources | **No** | Owner/tenant checks |
| Preventing forged requests carrying cookies | **Insufficient** | CSRF tokens, SameSite, additional Origin checks |
| Stopping malicious scripts inside the frontend | **No** | XSS defenses, escaping, CSP |
| Blocking curl requests without Origin | **No** | API auth, network policies, rate limits |
| Letting browsers send credentials cross-origin | **Conditionally** | CORS credentials + cookie/Fetch policies |

Saying "CORS will block every request from an unknown domain" is false. The browser may send certain requests before concluding the response cannot be read; on the server, CORS rejection can cause Spring WebFlux to return 403 when handling an invalid cross-origin request. **Never rely on CORS alone to prevent side effects or data exfiltration over non-browser channels.**

### 3.1. Origin Is Not Proof of Identity

The `Origin` header reflects the **web client context**. Clients unconstrained by a browser, such as curl, can send any `Origin`. Never write:

~~~java
// WRONG: Origin does not prove the caller is staff.
if ("https://admin.example.org".equals(originHeader)) {
    giveAdminPermissions();
}
~~~

Role rules must rely on **Authentication/GrantedAuthority** verified by Spring Security, never on the `Origin` string. CORS only governs cross-origin exceptions for browsers.

## 4. OPTIONS Preflight and Actual Requests

Some cross-origin requests require a **preflight**: the browser sends `OPTIONS` automatically to ask the server whether the upcoming method and headers are permitted. For example, an SPA sending HTTP Basic or bearer in an **Authorization** header:

~~~http
OPTIONS /api/me HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

If the origin, method, and header are allowed, the server may respond:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.org
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

The status code may be 200 or another appropriate 2xx code depending on the processor; what matters is that the allow headers accurately reflect the policy.

Only after a successful preflight does the browser send the actual request:

~~~http
GET /api/me HTTP/1.1
Origin: https://app.example.org
Authorization: Basic <encoded-credential>
~~~

The server must still **verify the password and check permissions** before returning data. A passing preflight never proves the client is logged in.

### 4.1. Why Does Preflight Usually Omit Cookies?

A CORS preflight is sent by the browser to ask permission, not as a login business request. Preflights typically **carry no cookies or actual-request Authorization**, so if Spring Security demands login before handling `OPTIONS`, the browser may report only a generic "CORS error".

The fix is not setting **permitAll** on all endpoints or disabling `SecurityWebFilterChain`. Configure **`CorsWebFilter` ahead of authentication/authorization** via Spring Security Reactive's integration so preflights are processed against the allowlist.

### 4.2. Simple Requests Do Not Always Have Preflights

An ordinary GET may skip preflight when it uses no custom or non-safelisted headers. Even then, the browser still sends `Origin` and checks **Access-Control-Allow-Origin** on the actual response. CORS configuration must be right for **both preflight and actual requests**.

Conversely, a valid preflight does not guarantee the actual request returns 200: authentication may return 401, authorization 403, validation 400, or the backend 5xx.

### 4.3. Why Is Vary Needed?

When CORS responses can vary by `Origin`, caches and proxies must know about it. **Vary: Origin**—and on preflights also **Access-Control-Request-Method** and **Access-Control-Request-Headers**—prevents CDNs/proxies from reusing headers meant for one origin on another origin.

Never echo a request's `Origin` into headers assuming "caches will figure it out". Caches must honor `Vary`, and personalized responses should carry appropriate `Cache-Control`, typically `no-store`.

## 5. What Is the Arbitrary Origin Reflection Vulnerability?

Dangerous code pattern:

~~~java
// FORBIDDEN as a CORS policy.
String incoming = exchange.getRequest().getHeaders().getOrigin();
if (incoming != null) {
    exchange.getResponse().getHeaders()
            .setAccessControlAllowOrigin(incoming);
    exchange.getResponse().getHeaders()
            .setAccessControlAllowCredentials(true);
}
~~~

This snippet treats a **client-declared `Origin`** as the server's answer saying "I allow that website to read data". Without an allowlist, an attacker can send their own Origin and receive **Access-Control-Allow-Origin: https://evil.example.net**.

A configuration that **reflects Origin only after matching an exact allowlist** can be valid: many CORS frameworks echo the matched origin when multiple allowed origins are configured. Therefore, never judge risk solely by observing "response ACAO equals request Origin"; inspect **how `Origin` is validated before responding**.

### 5.1. Common Anti-Patterns

**Anti-pattern A: wildcard with credentials**

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true);
~~~

Spring Framework rejects this invalid configuration when `validateAllowCredentials` runs. The CORS specification forbids **Access-Control-Allow-Origin: \*** together with **Access-Control-Allow-Credentials: true**.

**Anti-pattern B: copying Origin without checking**

~~~java
config.setAllowedOrigins(List.of(exchange.getRequest()
        .getHeaders().getOrigin()));
~~~

This statement does not form a static allowlist; it lets the client pick any allowed Origin.

**Anti-pattern C: boundary-broken prefix/suffix checks**

~~~java
// WRONG: https://app.example.org.attacker.test also contains this string.
if (origin.contains("app.example.org")) { allow(); }

// WRONG: evil-example.org can also match a naive suffix check.
if (host.endsWith("example.org")) { allow(); }
~~~

If subdomain wildcards are truly required, account for leading dots, eTLD/public suffixes, subdomain ownership, and takeover risks, using governed `allowedOriginPatterns` with an approved list. An **exact allowlist** remains the preferred option for products with a handful of frontends.

**Anti-pattern D: trusting a user-supplied URL**

~~~text
POST /settings/cors
{"allowedOrigin": "https://attacker.example.net"}
~~~

If ordinary users can register an `Origin` allowing a cookie-authenticated API to return data to their website, that is a configuration-authorization flaw. Production CORS lists must be controlled by deployment/security owners; if self-service tenant domains exist, require domain ownership verification and policy-edit authorization.

**Anti-pattern E: "using * in staging for convenience"**

Staging environments often hold data or accounts resembling production. Allowing all Origins with credentials is a severe risk; even without credentials, opening arbitrary frontend origins blurs API contracts and expands readable data exposure. Staging needs its **own** approved origin list, not an unthinking copy from development.

## 6. allowedOrigins, allowedOriginPatterns, and allowCredentials

Spring Framework provides **CorsConfiguration**:

- **setAllowedOrigins(List<String>)**: explicit origin list, or `*` when not using credentials per the spec.
- **setAllowedOriginPatterns(List<String>)**: patterns for origin sets requiring dynamic matching; when matched, ACAO can be set to the **actual matched origin**.
- **setAllowedMethods(...)**: HTTP methods allowed under CORS.
- **setAllowedHeaders(...)**: request headers permitted in preflight.
- **setExposedHeaders(...)**: extra response headers JavaScript may read beyond CORS-safelisted headers.
- **setAllowCredentials(true/false)**: whether cross-origin requests with credentials are accepted by browsers under CORS.
- **setMaxAge(...)**: how long browsers may cache preflight results (subject to browser caps).

### 6.1. When Can "*" Be Used?

A completely public API using no cookies or credentials, intended for any website to read, may deliberately choose:

~~~java
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(false);
~~~

Even so, this is an **explicit decision to publish data**, not a convenience setting. For APIs requiring sessions, cookies, or authorization credentials, use an **explicit allowlist** and enable credentials only with justification.

Spring allows **allowedOriginPatterns** together with `allowCredentials` in certain scenarios because it echoes the actual matched origin, yet that **does not make broad patterns safe**. Pattern **"*"** with `allowCredentials` effectively lets browsers from any matched origin read personal data.

### 6.2. Credentials Are Not Only Cookies

In CORS/Fetch, credentials include cookies, HTTP authentication credentials, and browser-managed credentials. For requests using **fetch(..., { credentials: "include" })**, browsers require an exact ACAO rather than `*` plus **Access-Control-Allow-Credentials: true** to expose responses to JavaScript.

With an explicit `Authorization` header, preflight must also allow the **Authorization** header name. CORS rules and browser credential policies have distinct details, yet **CORS does not verify `Authorization`**: Spring Security's `AuthenticationWebFilter`/manager must do that.

A cross-origin client may still fail to send cookies due to **SameSite, Secure, third-party cookie restrictions, partitioning, browser settings, or Domain/Path config** even when the server returns `Allow-Credentials`. Never "fix" that by opening CORS to every Origin.

### 6.3. Distinguishing Origin and Referer

`Origin` is the signal dedicated to CORS; `Referer` may contain the calling page's URL or be stripped by `Referrer-Policy`. Never build an allowlist via `Referer` substring matching, and never use `Origin` as proof that a user is logged in.

### 6.4. Origin: null

Browsers can send `Origin: null` in opaque-origin contexts, sandboxed iframes, `file://` URLs, or special environments. Without a clear requirement and compensating controls, **never allow `"null"`** in the allowlist; an attacker can craft an opaque-origin context. The demo rejects `Origin: null`.

## 7. Separating Allowlists by Environment

An application typically has three environment tiers:

| Environment | Approved frontend origin | Rule |
| --- | --- | --- |
| local | http://localhost:5173 | Loopback HTTP for development only |
| staging | https://staging-ui.example.org | HTTPS only, verified staging domain |
| production | https://app.example.org | HTTPS only, verified production domain |

The `example.org` domains in the table are **documentation placeholder domains**; in real deployments, replace them with real origins owned and controlled by your organization. Never treat arbitrary `example.org` subdomains as trustworthy by default.

### 7.1. Never "Infer the Environment" from the Client's Origin

Forbidden logic:

~~~java
// WRONG: caller self-declares so the app thinks it is running locally.
if (request.getHeaders().getOrigin().contains("localhost")) {
    allowCors();
}
~~~

Environment identity must come from **deployment configuration**, Spring profiles, or a governed config source—never from request headers.

### 7.2. Fail-Closed Configuration

The demo uses the **`app.cors.allowed-origins`** property. For local runs, deployment supplies:

~~~bash
SPRING_PROFILES_ACTIVE=local \
APP_CORS_ALLOWED_ORIGINS=http://localhost:5173 \
gradle bootRun
~~~

For production, deployment supplies an approved HTTPS list, such as:

~~~bash
SPRING_PROFILES_ACTIVE=prod \
APP_CORS_ALLOWED_ORIGINS=https://app.example.org \
gradle bootRun
~~~

When two approved production frontends exist:

~~~bash
APP_CORS_ALLOWED_ORIGINS=https://app.example.org,https://admin.example.org
~~~

The list **contains origins only**, with no paths, wildcards, or trailing slashes. Spring Boot's `Environment` maps environment variable `APP_CORS_ALLOWED_ORIGINS` to property `app.cors.allowed-origins` under Spring Boot's relaxed binding rules.

**Fail-closed in the demo:** if the property is blank, contains malformed origins, uses `*`, uses `null`, or uses plain HTTP outside loopback / outside the `local` profile, the configuration bean refuses to start; the application never silently falls back to opening all origins. This is deliberate so a misconfigured deployment never silently weakens CORS.

### 7.3. Considerations When Switching Environments

- **Local:** allow HTTP only on `localhost` or `127.0.0.1` when the `local` profile is genuinely active.
- **Staging:** HTTPS only; do not admit developer local origins unless specifically approved under strict controls.
- **Production:** allowlist only exact production websites, minimizing the list.
- **Preview deployments:** avoid admitting all `*.preview.example.org` names if developers or users outside the trust boundary can spin up previews. Use explicit allowlists per authorized preview with a TTL if needed.
- **Multi-tenant:** if tenants register custom domains, verify domain ownership and protect policy-editing endpoints with proper administrative authorization.
- **Kubernetes/CI:** govern environment variables, Helm values, and secret/config sources; review origin config diffs before every release.
- **Rollback:** remember preflight caches can persist in browsers per `maxAge`; measure actual client state after policy changes.

## 8. CORS Configuration Layers in WebFlux

CORS can be configured in several layers:

| Layer | Mechanism | Notes |
| --- | --- | --- |
| Spring Security Reactive | `ServerHttpSecurity.cors(...)` and `CorsConfigurationSource` | Integrates CORS with security filters; runs preflight before authentication |
| WebFlux | `WebFluxConfigurer.addCorsMappings(...)` | Applied via `HandlerMapping`; verify behavior with annotated/functional endpoints |
| Annotated controller | `@CrossOrigin` | Prone to policy drift as teams add annotations individually |
| WebFlux.fn/RouterFunction | `HandlerMapping`/route-specific CORS source | Must be cross-checked with security policy |
| Global WebFilter | `CorsWebFilter` | Watch for duplication with Spring Security's CORS filter |
| Gateway/CDN/reverse proxy | CORS middleware | May add or modify headers before responses reach the client |

Avoid enabling multiple layers with differing allowlists without good reason. For example, a gateway reflecting arbitrary Origins while the Java app restricts them properly can produce responses with conflicting policies, duplicate ACAO headers, or subtle cache bugs.

The demo uses **a single reactive `CorsConfigurationSource`** passed into **`ServerHttpSecurity.cors(...)`**, without manually registering a second `CorsWebFilter` or adding `@CrossOrigin` on controllers.

### 8.1. Choosing the Right Reactive Package

~~~java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
~~~

Do not confuse these with:

~~~java
// Servlet/MVC, do NOT use as a reactive CORS source:
org.springframework.web.cors.UrlBasedCorsConfigurationSource;
org.springframework.web.filter.CorsFilter;
org.springframework.security.config.annotation.web.builders.HttpSecurity;
~~~

Both packages contain a class named **`UrlBasedCorsConfigurationSource`**; importing the wrong one makes the configuration incompatible with reactive `ServerHttpSecurity`.

### 8.2. CORS in SecurityWebFilterChain

Spring Security 6.x provides:

~~~java
http.cors(cors -> cors.configurationSource(source));
~~~

`source` is an **`org.springframework.web.cors.reactive.CorsConfigurationSource`**. This places CORS configuration into the security chain; preflight is resolved by origin/method/header policy ahead of authentication for endpoints in that chain.

Per the `ServerHttpSecurity.CorsSpec` Javadoc, if no matching source exists, CORS integration may do nothing. **Calling `cors()` without supplying trusted origins does not mean you have an allowlist.**

## 9. Sample Java 17+ Project: Spring Boot Reactive with Environment Allowlist

The demo uses **Spring Boot 3.5.16**, Java 17+, and Gradle 8.4+ (e.g., Gradle 8.14). Spring Boot 3.5.16 builds on Spring Framework 6.2.19+ and was announced as the final OSS release of the 3.5 line; for new systems, select a branch still receiving OSS or commercial support. Versions are pinned so the example consistently uses Spring Security 6.x APIs.

Routes:

| URL | CORS policy | Authentication/authorization |
| --- | --- | --- |
| GET /api/public/ping | `/api/**` per allowlist | Public |
| GET /api/me | `/api/**` per allowlist | Valid HTTP Basic required |
| GET /api/admin/report | `/api/**` per allowlist | `ROLE_ADMIN` |
| Other URLs | Not opened by default | `denyAll` |

A preflight to `GET /api/me` **does not need a password**, yet must include `Origin`, `Access-Control-Request-Method`, and appropriate requested headers. After preflight, `GET /api/me` still requires Basic credentials.

Demo accounts: `reader` / `reader-pass` with `ROLE_USER`; `admin` / `admin-pass` with `ROLE_USER`, `ROLE_ADMIN`. Use these only for learning; never hardcode real credentials in production.

### 9.1. Project Structure

~~~text
webflux-cors-allowlist/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/cors/CorsApplication.java
├── src/main/java/example/cors/SecurityConfig.java
├── src/main/java/example/cors/ApiController.java
├── src/test/java/example/cors/CorsIntegrationTest.java
└── src/test/java/example/cors/CorsConfigValidationTest.java
~~~

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-cors-allowlist'
~~~

### 9.3. build.gradle

~~~groovy
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.4. application.yml

~~~yaml
app:
  cors:
    # Do not open any origin by default. Deployment must supply an allowlist.
    allowed-origins: ""
~~~

When launched with environment variable `APP_CORS_ALLOWED_ORIGINS`, its value overrides the corresponding property. If deploying via Spring Config Server or manifests, you can set `app.cors.allowed-origins` directly to the approved origin list.

### 9.5. CorsApplication.java

~~~java
package example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
~~~

### 9.6. SecurityConfig.java — Allowlist, Validation, and CORS Integration

~~~java
package example.cors;

import java.net.URI;
import java.time.Duration;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(Environment env) {
        // Property comes from application.yml or deployment override.
        String csv = env.getProperty("app.cors.allowed-origins", "");
        boolean local = env.acceptsProfiles(Profiles.of("local"));

        List<String> origins = parseAllowedOrigins(csv, local);

        CorsConfiguration cors = new CorsConfiguration();
        // Approved origins only; never use "*" or broad patterns.
        cors.setAllowedOrigins(origins);
        cors.setAllowCredentials(true);

        // Demo exposes GET endpoints; write methods are not opened.
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of(
                HttpHeaders.AUTHORIZATION,
                HttpHeaders.CONTENT_TYPE));
        cors.setMaxAge(Duration.ofMinutes(10));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    static List<String> parseAllowedOrigins(
            String raw, boolean localProfile) {

        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "app.cors.allowed-origins must be explicitly configured");
        }

        List<String> origins = Arrays.stream(raw.split(",", -1))
                .map(String::trim)
                .toList();

        Set<String> seen = new HashSet<>();

        for (String origin : origins) {
            if (origin.isEmpty()
                    || origin.indexOf('*') >= 0
                    || "null".equalsIgnoreCase(origin)) {
                throw new IllegalArgumentException(
                        "Invalid CORS origin: " + origin);
            }

            URI uri;
            try {
                uri = URI.create(origin);
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException(
                        "Malformed CORS origin: " + origin, e);
            }

            String scheme = uri.getScheme();
            String host = uri.getHost();

            boolean https = "https".equals(scheme);
            boolean httpLoopback = localProfile
                    && "http".equals(scheme)
                    && ("localhost".equalsIgnoreCase(host)
                            || "127.0.0.1".equals(host));

            boolean hasPath = uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty();

            if ((!https && !httpLoopback)
                    || host == null
                    || uri.getRawUserInfo() != null
                    || hasPath
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null
                    || uri.getPort() == 0
                    || uri.getPort() > 65535) {
                throw new IllegalArgumentException(
                        "CORS origin must be an exact allowed scheme,"
                        + " hostname and optional port: " + origin);
            }

            if (!seen.add(origin)) {
                throw new IllegalArgumentException(
                        "Duplicate CORS origin: " + origin);
            }
        }

        return List.copyOf(origins);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsConfigurationSource) {

        return http
                // Integrate CorsWebFilter into the security chain.
                .cors(cors -> cors.configurationSource(
                        corsConfigurationSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/api/public/ping")
                                .permitAll()
                        .pathMatchers("/api/admin/**")
                                .hasRole("ADMIN")
                        .pathMatchers("/api/**")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Code analysis:**

1. The **`CorsConfigurationSource`** bean belongs to the reactive package and registers only under `/api/**`.
2. **`parseAllowedOrigins`** rejects empty values, wildcards, `null`, URLs with paths/queries/fragments, userinfo URLs, duplicates, and plain HTTP outside local loopback.
3. **`localProfile`** is decided by Spring's `Environment`, never by reading a request-supplied `Origin`. In production and staging, plain HTTP is rejected.
4. **`setAllowedOrigins`** uses an explicit list; it never builds an allowlist from request headers.
5. **`setAllowCredentials(true)`** is safe here solely because origins are constrained and the app models credentialed browser requests; there are no wildcards.
6. **`setAllowedMethods(GET)`**: GET preflight is permitted; POST/DELETE are not opened to CORS.
7. **`setAllowedHeaders(Authorization, Content-Type)`**: permits only required request headers. Header casing varies across browsers; Spring CORS handles header names per protocol rules.
8. **`setMaxAge(10 minutes)`**: browsers can cache preflight results, balancing traffic against policy rollout responsiveness.
9. **`http.cors(...)`** ensures Spring Security integration; no standalone `CorsWebFilter` bean is added, avoiding duplicate processing.
10. **`authenticated()`** and **`hasRole("ADMIN")`** still run on actual GETs; preflight is never treated as a successful login.
11. **`anyExchange().denyAll()`** is default-deny for unexposed URLs. This is an authorization decision, separate from CORS.
12. HTTP Basic is used for the exercise; demo passwords are BCrypt-hashed when building users. Never send real credentials over cleartext HTTP.
13. Any allowlist change must be reviewed by deployment configuration owners; example domains do not grant admin permissions automatically.

**Validator boundary:** this is an example misconfiguration guard, not a complete origin-normalization library for all URL/IDN/IPv6 specifications. For products handling internationalized or complex origins, use dedicated validation libraries/tests and always store canonical browser-sent values. What matters most is **never establishing a policy that accepts wildcards or arbitrary Origins**.

### 9.7. ApiController.java

~~~java
package example.cors;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(actor -> Map.of(
                "username", actor.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

The controller never writes CORS headers itself; **`CorsWebFilter`** handles them from the single central configuration. Endpoints still enforce authentication and authorization as requests pass through `SecurityWebFilterChain`.

### 9.8. Running Locally with an Explicit Allowlist

Bash:

~~~bash
SPRING_PROFILES_ACTIVE=local \
APP_CORS_ALLOWED_ORIGINS=http://localhost:5173 \
gradle bootRun
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_CORS_ALLOWED_ORIGINS = "http://localhost:5173"
gradle bootRun
~~~

The application listens on `http://localhost:8080` by default. Use demo usernames/passwords strictly over localhost; production must enforce HTTPS/TLS. If `APP_CORS_ALLOWED_ORIGINS` is omitted or set to `*`, the app **refuses to start** per `parseAllowedOrigins`; this fail-closed behavior is intentional.

When deploying to staging/prod, the `local` profile is inactive and only HTTPS origins are accepted. If environments override properties via different precedence levels, inspect the effective configuration at deployment and never log credentials or tokens.

## 10. Testing with curl: Preflight and Actual Requests

The commands below target Bash, run while the app listens on `localhost:8080` with profile `local` and allowed origin **`http://localhost:5173`**.

### 10.1. Valid Preflight Without Credentials

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Expected key output:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Preflight needs no login; without proper CORS integration, `OPTIONS` would be challenged for auth by `SecurityWebFilterChain` before emitting CORS headers.

### 10.2. Preflight from an Unrecognized Origin

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://attacker.example.net' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

With the demo's standard `CorsWebFilter`, expected output is **403 Invalid CORS request**, and it **must never** return `Access-Control-Allow-Origin` for the attacker. Specific status/body details can be altered by proxies or custom error handlers, yet the invariant remains: **zero CORS permission for that origin**.

### 10.3. Lookalike Origin Name

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost.evil.example.net:5173' \
  -H 'Access-Control-Request-Method: GET'
~~~

Even though it contains `localhost`, this is **not** `http://localhost:5173`, so it is rejected. Tests like this catch code that uses `contains("localhost")` to trust callers.

### 10.4. Preflight Requesting a Method Outside the Allowlist

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE'
~~~

Expected: **403** or no CORS allow headers for `DELETE`; in the demo `CorsWebFilter` rejects the invalid preflight. Never open all methods simply because a frontend website is trusted.

### 10.5. Actual Request to Protected API Without Basic Credentials

~~~bash
curl -i http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173'
~~~

Being on the origin allowlist **does not equal login**: HTTP Basic authentication still requires credentials, returning **401 Unauthorized** with a Basic challenge. CORS headers for the allowed origin can appear on the 401 response so the browser frontend can read the status properly.

### 10.6. Actual Request with Credentials and Allowed Origin

~~~bash
curl -i -u reader:reader-pass \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/me
~~~

Expected key output:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"username":"reader"}
~~~

In production, use HTTPS and an appropriate login mechanism; Base64-encoded Basic auth does not protect passwords by itself.

### 10.7. Actual Request with Disallowed Origin Despite Valid Credentials

~~~bash
curl -i -u reader:reader-pass \
  -H 'Origin: https://attacker.example.net' \
  http://localhost:8080/api/me
~~~

In the demo, `CorsWebFilter` rejects the CORS request from the disallowed Origin (expected 403). This reflects Spring's server-side handling, **not that CORS is a universal authentication firewall**. Non-browser clients can omit the `Origin` header, so Basic/role/tenant checks must always remain enforced.

### 10.8. Request Without Origin

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/me
~~~

Expected 200 for `reader`. A direct request without `Origin` is not a cross-origin browser request requiring ACAO. Authentication policy still applies; omitting `-u` yields 401.

### 10.9. Missing ROLE_ADMIN Still Returns 403

~~~bash
curl -i -u reader:reader-pass \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/admin/report
~~~

Expected: 403 **due to authorization**, not CORS. Trying `admin:admin-pass` from the same allowed origin returns 200. Inspect Network/headers to distinguish CORS errors (Origin denied) from authorization errors (role denied).

## 11. WebTestClient: Verifying the Real Policy from Multiple Angles

To prove the allowlist works, test **both preflight and actual GETs**. Unit tests invoking controllers directly bypass `CorsWebFilter` and `SecurityWebFilterChain`.

File **src/test/java/example/cors/CorsIntegrationTest.java**:

~~~java
package example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "app.cors.allowed-origins="
                + "https://frontend.example.org,https://ops.example.org")
@AutoConfigureWebTestClient
class CorsIntegrationTest {

    private static final String ALLOWED =
            "https://frontend.example.org";

    private static final String DENIED =
            "https://evil.example.net";

    @Autowired
    WebTestClient client;

    @Test
    void preflightFromAllowedOriginSucceedsWithoutLogin() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        ALLOWED)
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true")
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
                .expectHeader().exists(HttpHeaders.VARY);
    }

    @Test
    void preflightFromDeniedOriginIsRejected() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void preflightRejectsDisallowedMethod() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "DELETE")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void preflightRejectsDisallowedRequestHeader() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-unsafe-debug")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void allowedOriginDoesNotBypassAuthentication() {
        client.get().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        ALLOWED);
    }

    @Test
    void actualRequestAllowedOriginAndValidLoginWork() {
        client.get().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        ALLOWED)
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true")
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void actualRequestFromDeniedOriginIsRejected() {
        client.get().uri("/api/me")
                .header(HttpHeaders.ORIGIN, DENIED)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void lookalikeSubdomainIsNotTrusted() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN,
                        "https://frontend.example.org.evil.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void opaqueNullOriginIsNotTrusted() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, "null")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sameOriginStyleDirectRequestStillNeedsLogin() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void allowedOriginDoesNotOverrideAdminAuthorization() {
        client.get().uri("/api/admin/report")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }

    @Test
    void publicRouteIsStillRestrictedByCorsInBrowserContext() {
        client.get().uri("/api/public/ping")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/public/ping")
                .header(HttpHeaders.ORIGIN, DENIED)
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**What the 12 tests verify:** not merely "allowed origin returns 200". The suite proves:

- Uncredentialed preflight still permits approved origin/method/headers.
- Unrecognized origins and lookalike hostnames are rejected.
- `DELETE` method and unknown custom headers are rejected even from a valid origin.
- Actual GET still requires login; `ROLE_ADMIN` remains enforced.
- Requests without `Origin` still face authorization without being treated as cross-origin requests requiring ACAO.
- Public APIs still do not open CORS to all origins merely because the security rule says `permitAll`.

**Warning:** if your project sits behind a gateway or external CORS filter, also test responses at the Internet edge. `WebTestClient` only proves policy within the Java application.

### 11.1. Testing Invalid Configuration Values

File **src/test/java/example/cors/CorsConfigValidationTest.java**:

~~~java
package example.cors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;

class CorsConfigValidationTest {

    @Test
    void productionOnlyAcceptsExplicitHttpsOrigins() {
        assertEquals(
                List.of("https://frontend.example.org",
                        "https://ops.example.org"),
                SecurityConfig.parseAllowedOrigins(
                        " https://frontend.example.org,"
                        + "https://ops.example.org ",
                        false));
    }

    @Test
    void missingAndWildcardOriginsFailClosed() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins("", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins("*", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://*.example.org", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "null", false));
    }

    @Test
    void pathQueryAndTrailingCommaAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org/", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org/home", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org?debug=1", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org,", false));
    }

    @Test
    void plainHttpIsOnlyAllowedForLoopbackInLocalProfile() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "http://localhost:5173", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "http://public.example.org", true));

        assertEquals(
                List.of("http://localhost:5173"),
                SecurityConfig.parseAllowedOrigins(
                        "http://localhost:5173", true));
    }

    @Test
    void duplicateOriginsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org,"
                        + "https://frontend.example.org",
                        false));
    }
}
~~~

Run the entire suite:

~~~bash
gradle test
~~~

**Expected result:** 17 tests PASS (12 integration tests + 5 policy parser tests), ending with Gradle `BUILD SUCCESSFUL` when Java, Gradle, and dependencies match. This is an **expectation from the code design**, not a log of an executed build.

### 11.2. Why Is Testing Tokens/Roles Important?

CORS preflight implies zero authentication. Testing only that `OPTIONS` succeeds without running an actual `GET` can mislead you into thinking the API needs no password. Conversely, if actual `GET` returns 403, distinguish among:

- CORS rejecting the `Origin`.
- Valid authentication with insufficient role.
- Authorization denying the URL.
- CSRF blocking an unsafe method.
- Proxy/gateway returning 403 before Spring.

A test matrix varying one factor at a time (origin, method, header, credentials, role) pinpoints the real cause.

## 12. Browser Frontend: Fetch and Cookie Example

With the frontend at **http://localhost:5173** and the API at **http://localhost:8080**, JavaScript can call:

~~~javascript
async function readProfile() {
  const response = await fetch("http://localhost:8080/api/me", {
    method: "GET",
    credentials: "include",
    headers: {
      "Authorization": "Basic " + btoa("reader:reader-pass")
    }
  });

  if (!response.ok) {
    throw new Error("API status: " + response.status);
  }

  return await response.json();
}
~~~

**This is a learning example to observe CORS, not a production login design.** Never hardcode Basic passwords in JavaScript/frontend bundles; attackers can read the source. Production uses OIDC/Authorization Code + PKCE or session/BFF with secure credential management.

The browser typically preflights because **Authorization** is not a CORS-safelisted request header. Preflight asks for GET and `authorization` without sending the Basic password; the server checks the allowlist first. The actual GET carries the frontend-supplied `Authorization`; Spring Security verifies the password and returns the principal.

When using session cookies instead of Basic:

- The frontend needs **`credentials: "include"`** if cross-origin fetches must send cookies under Fetch rules.
- The server needs `Access-Control-Allow-Credentials: true` and ACAO matching the exact origin.
- Cookies need proper `Domain`/`Path`/`Secure`/`SameSite`; third-party cookie restrictions can block cookies.
- Unsafe requests still need CSRF protection; CORS does not replace CSRF.
- The frontend must handle 401/403 properly rather than calling a CORS error "wrong password".

### 12.1. Dev Proxies Can Mask CORS Issues

Vite/dev servers often proxy `/api` to the backend so the browser sees only the frontend's origin. Then no cross-origin request crosses the wire from browser to backend, and the absence of CORS errors does not prove your allowlist is right.

Inspect the **Network panel**: which host did the request hit, what `Origin` header was sent, and what ACAO came back? Also test directly with `WebTestClient`/curl using `Origin` to lock down the policy.

## 13. Caches, CDNs, and Header Reflection Risks

An application can allow multiple origins. Spring WebFlux returns the specific **`Origin` confirmed by the allowlist**, yet if a CDN caches responses under one key ignoring `Vary`, requests from two different origins can receive the wrong header.

Mitigating the risk:

1. Let `CorsWebFilter` emit appropriate **`Vary: Origin`**, **`Access-Control-Request-Method`**, and **`Access-Control-Request-Headers`**.
2. Ensure reverse proxies/CDNs **never strip `Vary`** and never cache personalized responses using cookies/`Authorization` without an explicit safe caching policy.
3. Never let a gateway inject `Access-Control-Allow-Origin: *` after the backend applied an allowlist.
4. Never emit multiple `Access-Control-Allow-Origin` headers with different values; browsers reject duplicate/ambiguous headers.
5. Never rely on `Origin` to key user data caches; authorization also requires identity/tenant context.
6. Cap `Access-Control-Max-Age` when teams need to revoke origins quickly; browsers cache preflights up to their own limits.
7. When rotating hostnames/frontends, deploy and test the new allowlist ahead of DNS cutover, and schedule retirement of old origins.
8. Whenever you see ACAO matching `Origin`, **verify the Origin validation logic** rather than assuming arbitrary reflection from that symptom alone.

Remember that even when a browser stops JavaScript from reading a response due to a mismatched ACAO, the request may still have reached the server. Never use CORS headers in place of validation for financial writes, account changes, or sensitive operations.

## 14. When Is allowedOriginPatterns Appropriate?

Multi-tenant products with custom domains or preview deployments sometimes need dynamic matching. Spring Framework supports:

~~~java
config.setAllowedOriginPatterns(
        List.of("https://*.preview.example.org"));
~~~

This is solely an **API illustration**, not a recommendation to deploy that wildcard in production. Any pattern requires evaluating who can create or control subdomains, subdomain takeover risk, DNS wildcards, custom domain pointing, and whether real user data is exposed.

Key differences:

- **`allowedOrigins`** uses explicit origins—easy to audit and test.
- **`allowedOriginPatterns`** is a dynamic matcher; on a match, Spring emits the matched origin rather than `*`.
- **Arbitrary reflection** echoes any incoming origin without checking a trust set; it is never justified merely because its output looks similar to `allowedOriginPatterns`.
- Overly broad patterns like `"*"` paired with `allowCredentials` carry high risk even when Spring's API permits them.
- Self-service tenant CORS policies require **domain ownership verification, approval, resource read scoping, TTLs, and auditing**.

If you only have three frontend origins, an **exact allowlist is still far better** than a pattern.

### 14.1. Origin Matching Is Not DIY Regex

Never build a regex from unvalidated admin input and let it govern system-wide CORS. When using patterns, understand that Spring `CorsConfiguration` pattern syntax differs from general Java regexes, and test cases like **`evil.example.org`**, **`example.org.evil.test`**, ports, schemes, and unapproved subdomains.

## 15. Operational Checklist for Local, Staging, and Production

| Check | Local | Staging | Production |
| --- | --- | --- | --- |
| Origin list | http://localhost:5173, if needed | Governed HTTPS staging hosts | Governed HTTPS production hosts |
| Wildcard `*` when credentials true | Forbidden | Forbidden | Forbidden |
| `Origin: null` | Disallowed unless specifically approved | Forbidden | Forbidden |
| Plain HTTP outside loopback | No | Forbidden | Forbidden |
| Reflecting request `Origin` | Forbidden | Forbidden | Forbidden |
| Config source | Profile/env controlled by developer | Reviewed CI/CD configuration | Reviewed and approved IaC/secret/config |
| Preflight without `Authorization` | Pass if origin/method/header valid | Pass if valid | Pass if valid |
| Auth/roles on actual request | Required | Required | Required |
| CSRF for browser credentials | Evaluate | Mandatory evaluation | Mandatory evaluation |
| `Vary`, caching | Test | Test through proxy | Test through CDN |
| Duplicate CORS integration | Avoid | Avoid | Avoid |
| Allowlist changes | Developers manage local | Team review | Security/ops review |

Every release should automatically test at least:

- Allowed staging/prod origins receive proper CORS headers.
- Untrusted origins receive no `Access-Control-Allow-Origin`.
- Lookalike hostnames are denied.
- `Origin: "null"` is rejected.
- Plain HTTP origins are rejected in production.
- Preflight for approved methods/headers succeeds; `DELETE` or `X-Unsafe-Debug` are rejected.
- Actual requests lacking credentials receive 401 even with a valid `Origin`.
- Authenticated users lacking the required role receive 403 even with a valid `Origin`.
- Missing CORS config due to bad deployment makes the app fail fast.
- No unexpected `Access-Control-Allow-Origin` header is injected by a proxy/CDN.

### 15.1. Observability and Logging

Log the **event type** (`cors_allowed`, `cors_rejected`, `preflight_denied`), sanitized origin per logging policy, method/path template, `requestId`, and status. Never log `Authorization`, cookies, CSRF tokens, or sensitive user data. Because `Origin` is client-supplied input, escape and truncate it to prevent log injection and metric label cardinality explosion.

Avoid using raw `Origin` as an unbounded Prometheus label; categorize by allowed/denied and environment buckets instead. Distinguish CORS errors from 401 authentication, 403 authorization, and 403 CSRF on operational dashboards.

### 15.2. Common Incidents

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `OPTIONS` returns 401 | CORS not handled before authentication | Check `ServerHttpSecurity.cors` and preflight tests |
| `OPTIONS` returns 403 | Origin/method/header not allowlisted or proxy blocked | Vary `Origin`, `Access-Control-Request-Method/Headers` one by one |
| curl GET succeeds, browser reports CORS | Curl does not enforce Same-Origin Policy | Inspect Network, ACAO, credentials, and preflight |
| Browser reports credentials disallowed | ACAO is `*` or `Access-Control-Allow-Credentials` missing | Use exact origin; enable credentials only when needed |
| Works locally, blocked in prod | Prod hostname missing from allowlist or http/https mismatch | Inspect effective environment properties |
| Test lookalike domain allowed | Faulty `contains`/`startsWith`/suffix check | Replace with exact `allowedOrigins` |
| Two ACAO headers present | Both gateway and Spring inject CORS | Pick one config owner and fix proxy |
| `OPTIONS` succeeds, GET 401 | CORS is right, Authentication missing/invalid | Check auth scheme and credentials |
| `OPTIONS` succeeds, GET 403 | Role/owner/CSRF or another policy | Inspect security filters and status/body |
| Cookies not sent | `SameSite`/`Secure`/third-party blocking | Inspect `Set-Cookie` and browser storage |
| ACAO right yet JS cannot read custom response header | Missing `exposedHeaders` | Add the exact header to `exposedHeaders` if needed |
| Changed allowlist yet browser uses old config | Cached preflight | Check `Access-Control-Max-Age`/browser cache |
| Unknown Origin reflected in ACAO | Some layer accepts without checking | Hunt for manual headers, `@CrossOrigin`, `WebFluxConfigurer`, CDN |
| App fails to start with empty CORS env | Intentional fail-closed validator | Supply exact allowlist via deployment config |

## 16. Practice Exercises and Self-Check Questions

1. What exact string is the origin of `https://app.example.org:8443/dashboard?tab=1`?
2. Why are `https://app.example.org` and `http://app.example.org` not the same origin?
3. If an API returns `Access-Control-Allow-Origin: https://evil.example.net` for an unapproved `Origin`, what risk arises?
4. Why cannot `allowCredentials(true)` be paired with `allowedOrigins("*")`?
5. Why is `allowedOriginPatterns("*")`, even if accepted by the framework, an unsafe policy for credentialed APIs?
6. Does an ACAO response matching the request `Origin` always prove arbitrary reflection?
7. Why must `OPTIONS` preflights be processed ahead of authentication?
8. Under the demo `local` profile, is `Origin http://localhost:5173` allowed? What about `Origin http://localhost.evil.test:5173`?
9. Why does the demo `production` profile reject non-HTTPS HTTP origins?
10. Why must a POST with a valid origin still not skip CSRF protection?
11. If curl calls the API without an `Origin` using valid Basic auth and gets 200, does that prove the allowlist is broken?
12. If a `reader` user from an allowed `Origin` calls `GET /api/admin/report`, what status is expected?
13. Why must you test both allowed `GET` and rejected `DELETE` in preflight?
14. Why doesn't listing HTTP methods in CORS replace method authorization?
15. Why shouldn't you trust `Origin` from a request to decide roles or tenants?
16. How can adding `@CrossOrigin` on a Controller create an inconsistent policy alongside `RouterFunction`s?
17. What roles do `Access-Control-Max-Age` and `Vary` play for caching and preflight?
18. When a deployment omits `APP_CORS_ALLOWED_ORIGINS`, why is failing closed better than defaulting to `"*"`?
19. If a frontend needs to read the `X-Request-Id` response header via JS, what else must be configured?
20. In a multi-tenant system supporting custom domains, what must be verified before allowing CORS for a domain?

**Suggested answers:**

1. `https://app.example.org:8443`; path and query do not belong to the origin.
2. Different schemes.
3. An untrusted browser origin could gain permission to read cross-origin responses, severe when the API uses cookies/credentials.
4. The CORS spec forbids ACAO `*` with `Allow-Credentials: true`; Spring validates the configuration.
5. An overly broad pattern matches any origin, effectively opening personal responses to be read.
6. No; echoing the exact `Origin` after exact allowlist matching is valid.
7. Preflights normally carry no credentials; if auth intercepts first, the browser never sends the actual request.
8. Yes if local config is set properly; the lookalike domain is rejected.
9. Reduces risk of transmitting/reading data over plain HTTP in real environments; local loopback is an intentional exception.
10. CORS does not replace CSRF for cookies or automatic browser credentials.
11. No; curl is not restricted by browser CORS, and Authentication still applies.
12. 403 due to missing `ROLE_ADMIN`, assuming the request passed CORS.
13. Ensures a valid origin does not implicitly open all HTTP methods.
14. CORS only coordinates cross-origin browser access; authorization decides whether the user may run the method.
15. `Origin` is client-controlled outside browsers, not a signed identity claim.
16. `@CrossOrigin` can add allowed origins via `HandlerMapping` that diverge from the central policy.
17. `maxAge` caches preflights; `Vary` prevents caches from mixing responses across origins/methods/headers.
18. Failing fast prevents a misconfigured deployment from silently opening all origins.
19. `setExposedHeaders(List.of("X-Request-Id"))` provided the response emits that header.
20. Ownership, trust boundaries, policy-edit permissions, takeover risk, TTL, approval, and auditing.

## 17. Reference Links

- Spring Security — Reactive CORS integration: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security Javadoc — ServerHttpSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Javadoc — CorsSpec.configurationSource: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework — CorsConfiguration Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Framework — Reactive CorsWebFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- OWASP — CORS and Access-Control-Allow-Origin guidance: https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny

**Conclusion:** In Spring Security WebFlux, **restricting Origin must start with an explicit, deployment-controlled allowlist per environment**; never reflect arbitrary Origins alongside `Access-Control-Allow-Credentials`. Use a **reactive `CorsConfigurationSource`** integrated via **`ServerHttpSecurity.cors(...)`**, validate scheme/host/port, process preflight before authentication, constrain methods/headers, preserve `Vary`/caching properly, and fail closed on misconfiguration. Test both preflight and actual requests, lookalike domains, credentials, and roles: **CORS only tells the browser which responses may be read cross-origin; it never replaces identity, authorization, or CSRF controls.**