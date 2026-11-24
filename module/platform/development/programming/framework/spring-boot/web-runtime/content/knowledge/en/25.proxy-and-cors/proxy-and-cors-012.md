# Avoiding duplicate CORS configuration across application, gateway, and Spring Security

## 1. The problem: the API returns HTTP 200 yet the browser still reports a CORS error

A Spring Boot system typically spans multiple layers:

```text
Browser (https://ui.example.test)
       |
       | Origin: https://ui.example.test
       v
API gateway / ingress / NGINX
       |
       v
Spring Security filter chain
       |
       v
Spring MVC / WebFlux controller
       |
       v
Business logic
```

Gateways, Spring Security, and Spring MVC/WebFlux can all **participate in CORS handling**. When multiple layers emit response headers without a single unified policy, the browser may report:

```text
Access to fetch at ... has been blocked by CORS policy:
The 'Access-Control-Allow-Origin' header contains multiple values ...
```

This error **does not necessarily mean the API failed to run**. The backend can return 200 with valid JSON, yet the browser refuses to let JavaScript read the response because the CORS response headers are invalid. Bad example:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Origin: https://ui.example.test
Content-Type: application/json
```

Even when both values are identical, sending **two `Access-Control-Allow-Origin` headers** is still invalid under browser CORS rules. When a layer concatenates values into `https://ui.example.test, https://other.example.test`, that is also invalid: a CORS response may advertise only one explicit origin (or `*` where allowed), never a comma-separated list of origins.

**Goal:** Every request on a **public route** must flow through **one consistent CORS policy**, and the final HTTP response must never carry conflicting or duplicate CORS headers written by multiple layers.

Illustrative scope: **Spring Boot 3.3.x, Spring Security 6.x, Spring Framework 6.1.x, Java 17+**; the sample application uses Spring MVC with Java 21. Also covers Spring Cloud Gateway 4.1.x (the release line compatible with Spring Boot 3.3 via Spring Cloud 2023.0.x), general HTTP gateways, and a WebFlux comparison. Do not confuse CORS with authentication/authorization, CSRF, or proxy forwarded metadata.

## 2. CORS is a contract between browser and server, not a firewall

An **origin** has three components:

```text
scheme + host + port
```

Examples:

| URL | Origin | Compared to `https://ui.example.test` |
| --- | --- | --- |
| `https://ui.example.test/page` | `https://ui.example.test` | Same origin |
| `https://api.example.test/v1` | `https://api.example.test` | Different host |
| `http://ui.example.test/page` | `http://ui.example.test` | Different scheme |
| `https://ui.example.test:8443/page` | `https://ui.example.test:8443` | Different port |
| `https://ui.example.test/other` | `https://ui.example.test` | Same origin |

Browsers enforce the same-origin policy when JavaScript reads data via `fetch` or `XMLHttpRequest`. A server can grant an origin permission to read responses using **CORS response headers**. Clients such as `curl`, Java `HttpClient`, Postman, or backend-to-backend callers do not apply browser CORS rules: they send requests and read responses according to their own client rules.

CORS **does not replace**:

- Authentication (identifying the caller).
- Authorization (who may read/modify a resource).
- CSRF protection for cookie-backed sessions.
- TLS/HTTPS and certificate verification.
- Network policies, API gateway authentication, and rate limiting.

Because CORS is not authentication, the `Origin` header **must never be used as caller identity**. Non-browser clients can forge any header; even in a browser, CORS only restricts JavaScript from reading responses and does not automatically prevent all side effects.

## 3. Distinguishing preflight and actual requests

A browser sends a **preflight request** ahead of the actual request when the method or request headers exceed the conditions of a "simple CORS request." Example JavaScript:

```javascript
const response = await fetch("https://api.example.test/api/ping", {
  method: "GET",
  headers: {
    "Authorization": "Bearer some-token"
  }
});
console.log(await response.text());
```

`Authorization` is not a CORS-safelisted request header, so the browser usually sends a preflight:

```http
OPTIONS /api/ping HTTP/1.1
Host: api.example.test
Origin: https://ui.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

If policy permits it:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
```

After preflight succeeds, the browser sends the actual `GET`. Example actual response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Content-Type: text/plain

pong
```

The headers and status codes above are **illustrative**. The framework may emit a `Vary` list including `Access-Control-Request-Method` and `Access-Control-Request-Headers`; exact ordering, casing, and 2xx status codes can vary. Verify policy logic and required fields rather than asserting exact verbatim HTTP text.

A simple `GET` request may **skip preflight**, yet it still needs an appropriate `Access-Control-Allow-Origin` on its response if cross-origin JavaScript needs to read the result. Fixing only `OPTIONS` while forgetting `GET`/`POST` responses is incomplete.

## 4. Recognizing response headers and request headers

| Header | Direction | Role |
| --- | --- | --- |
| `Origin` | Browser → server | Origin initiating the request |
| `Access-Control-Request-Method` | Browser → server (preflight) | Intended actual method |
| `Access-Control-Request-Headers` | Browser → server (preflight) | Actual headers the client wants to send |
| `Access-Control-Allow-Origin` | Server → browser | **One** allowed origin or `*` in permitted cases |
| `Access-Control-Allow-Methods` | Server → browser (preflight) | Methods permitted to be used |
| `Access-Control-Allow-Headers` | Server → browser (preflight) | Request headers permitted to be sent |
| `Access-Control-Allow-Credentials` | Server → browser | Allows browser to expose response in matching credentials mode |
| `Access-Control-Expose-Headers` | Server → browser | Extra response headers JavaScript may read |
| `Access-Control-Max-Age` | Server → browser (preflight) | Preflight result cache duration, seconds |
| `Vary: Origin` | Server → cache/proxy/client | Indicates response may vary by `Origin` |

`Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` are sensitive to **duplication or conflict**. Never emit multiple values for `Access-Control-Allow-Origin`. When an allowlist has multiple origins, emit **the single origin matching the current request**, never the entire list.

`Vary: Origin` is crucial for CDNs and shared caches: a response allowed for `https://a.example` must never be cached and served mistakenly to `https://b.example`. For **preflight** caching, `Access-Control-Request-Method` and `Access-Control-Request-Headers` also matter. Spring CORS processors add suitable `Vary` values automatically; do not strip/overwrite them at the gateway when configuring caching.

`Vary` itself can have **multiple valid occurrences** or a list of values; do not apply `Access-Control-Allow-Origin`'s "single header value only" rule to every response header.

## 5. Distinguishing "CORS configured in multiple places" from "duplicated CORS headers"

There are three different kinds of overlap:

**Type A — overlapping config within Spring MVC.** An app has global `WebMvcConfigurer.addCorsMappings()` and `@CrossOrigin` on a controller. Spring Framework **combines global and local `CorsConfiguration`** instances. Lists of origins/methods/headers are generally merged additively, while single-valued properties like `allowCredentials` and `maxAge` follow override rules. Thus **having both does not automatically produce two `Access-Control-Allow-Origin` headers**. The risk is that policies become hard to audit, and local annotations may widen access unintentionally.

**Type B — two independent layers both write the response.** For example, the gateway adds:

```http
Access-Control-Allow-Origin: https://ui.example.test
```

and the Spring MVC or Security backend also adds:

```http
Access-Control-Allow-Origin: https://ui.example.test
```

The gateway forwards the upstream response including its header and appends another header. The browser sees two values—or a comma-joined string—and throws a **real CORS error**. This happens even though each layer looks right on its own.

**Type C — multiple CORS processors within the same app.** A custom `CorsFilter` bean, Security `.cors(...)`, and MVC handler-level CORS can create multiple processing points. Some Spring CORS implementations skip adding headers when `Access-Control-Allow-Origin` is already present, so they do not always produce duplicate headers. Still, policies, filter order, error paths, and preflight behavior can diverge; avoid managing one endpoint with multiple independent mechanisms.

**The primary goal is not deleting every mention of CORS**, but having **one clearly designated policy owner**, having participating components **share one policy source**, and letting only one layer emit CORS headers for each public route.

## 6. Map of where CORS headers can be injected

```text
Request:
Browser
  -> CDN / WAF
  -> API Gateway / Ingress / NGINX
  -> Spring Security CORS filter
  -> Spring MVC HandlerMapping / @CrossOrigin
  -> Controller

Response:
Controller
  -> MVC CorsProcessor may add ACAO
  -> Security filter / CorsFilter may participate
  -> API Gateway may add ACAO again
  -> CDN may modify or cache
  -> Browser evaluates final response
```

What matters is the **final response at the public URL**. A response directly from the backend may have one `Access-Control-Allow-Origin`, whereas through the gateway it has two. Conversely, if the gateway returns 401 or 404 **before calling the backend**, the app—no matter how well configured—never gets a chance to add CORS headers to that gateway-generated response.

| Layer | Common config | Risk |
| --- | --- | --- |
| Spring MVC | `@CrossOrigin`, `WebMvcConfigurer.addCorsMappings` | Local and global policies merge too broadly |
| Spring Security | `http.cors(...)`, `CorsConfigurationSource` | Preflight blocked by auth or ambiguous multiple sources |
| Servlet filters | Custom `CorsFilter` bean | Overlaps or misorders against Security and MVC |
| Spring WebFlux | `CorsWebFilter`, WebFlux global CORS | Same risks, reactive runtime |
| Spring Cloud Gateway | `globalcors`, route `cors` metadata, `DedupeResponseHeader` | Gateway and service both emit headers |
| NGINX/Ingress/CDN | `add_header`, `more_set_headers`, CORS middleware | Duplicates upstream header or adds only on 2xx |
| Error handler | Custom 401/403/404/5xx | Error response lacks CORS policy or uses a different one |

Not every gateway product merges or replaces headers the same way. Checking a configuration table without inspecting actual network responses is never enough.

## 7. Architectural rule: one policy owner per public API boundary

Choose **one ownership strategy**, document it in deployment docs, and test it:

| Architecture | Recommended owner | Condition to work properly |
| --- | --- | --- |
| Single Spring Boot API, reverse proxy only forwards | Spring backend (Security + one CORS source) | Proxy/CDN **must not add** `Access-Control-Allow-*` |
| Multiple microservices behind one public API gateway | Gateway | Backends omit CORS headers on public routes, or gateway explicitly strips upstream policy by design |
| Gateway handles auth, returning 401/403 before reaching services | Usually gateway | Gateway's own error responses must also include matching CORS headers |
| Services with differing origin policies | Gateway per-route **or** backend per-service | Never have both emit; keep a clear contract per route |
| Public assets/static CDN separate from API | Independent owner per resource/domain | Do not mix static-asset headers with private API policies |
| Internal-only backend never called by browsers | CORS may be unneeded | Authentication and network policies remain required |

"**One owner**" does not mean only one line of config anywhere in the codebase. When Spring Security needs to process preflight ahead of authentication, Security can **share the same `CorsConfigurationSource`** as the application; that is **integrating one policy**, not maintaining two independent allowlists.

The contract should specify: public paths, allowed origins, methods, headers, credentials, preflight owner, error-response behavior, cache variation, which services must not emit headers, and rollback ownership. If the app is also reachable via a direct path bypassing the gateway, review that path's policy separately—never assume a gateway protects a backend exposed straight to the Internet.

## 8. Preflight must run ahead of Spring Security authentication

Spring Security documentation states clearly: CORS should be processed **before Spring Security authorization**, because preflight requests usually **lack session cookies** such as `JSESSIONID`. If a preflight request is treated as unauthenticated, the security chain can return 401/403 before the CORS processor ever grants permission to the valid origin.

Example symptom:

```text
OPTIONS /api/orders
Origin: https://ui.example.test
Access-Control-Request-Method: POST

HTTP 401 / 403
Access-Control-Allow-Origin: [missing]
```

The browser shows only a CORS error, making it look like the backend "has a CORS error" when the earliest root cause is **filter order / auth rules**. Never fix this by applying `permitAll()` to all of `/api/**` or disabling Spring Security globally.

In modern Spring Security, the configuration API is typically:

```java
http.cors(Customizer.withDefaults());
```

When **one** matching `UrlBasedCorsConfigurationSource` bean exists, Security integrates with it. If you use Spring MVC CORS mappings and **declare no separate `CorsConfigurationSource`**, Security can reuse the MVC CORS configuration via `.cors(withDefaults())`. Both options are shown separately below.

**Important:** When a system has multiple `CorsConfigurationSource` beans or multiple `SecurityFilterChain`s, automatic lookup may fail to choose the right source per chain; pass `cors.configurationSource(...)` explicitly on each chain instead of relying on guesswork.

## 9. Option A: Spring Boot backend is the owner, gateway only forwards

This option fits when an API has its own policy and the external gateway only handles routing/TLS/external auth **without setting `Access-Control-Allow-*`**. Pick **one** `UrlBasedCorsConfigurationSource` and pass it to Spring Security.

### 9.1. Runnable Spring Boot MVC + Security project

This example uses **Spring Boot 3.3.13, Java 21**, and the Gradle Wrapper. Code lives in package `com.example.cors`.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/cors/CorsApplication.java`:**

```java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
```

**`src/main/java/com/example/cors/ApiController.java`:**

```java
package com.example.cors;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/ping")
    public ResponseEntity<String> ping() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-123")
                .body("pong");
    }
}
```

The controller **has no `@CrossOrigin`**; the CORS owner sits in the centralized configuration below.

**`src/main/java/com/example/cors/SecurityConfiguration.java`:**

```java
package com.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://ui.example.test"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(
                List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setMaxAge(1800L);
        config.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) throws Exception {

        http
                .cors(cors -> cors.configurationSource(corsSource))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/ping")
                        .permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Characteristics of this example:

- **One** `UrlBasedCorsConfigurationSource` defines the allowlist, and Security `.cors(...)` uses that exact source.
- Only `https://ui.example.test` is allowed for `/api/**`; `allowedOrigins("*")` is avoided.
- The demo path is public `GET /api/ping`; all other APIs remain protected by the security chain. CORS does not replace protecting them.
- Cross-origin cookies are off: `allowCredentials(false)`. If a real system uses cookies/sessions, credentials must be configured separately alongside CSRF and `SameSite`/`Secure`.
- `Access-Control-Expose-Headers: X-Request-Id` lets JavaScript read that response header (for allowed origins).
- No second `CorsFilter` bean, no `WebMvcConfigurer.addCorsMappings`, no `@CrossOrigin` on the controller, and **no** ACAO added by the gateway.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
server.address=127.0.0.1
```

This binds only to loopback for local development testing. Production needs proper authentication, network controls, and TLS. `ui.example.test` is merely a **simulated origin sent in headers**; no live DNS is required to test with `curl`.

### 9.2. Starting and testing preflight

From the project directory with the Gradle Wrapper:

```bash
./gradlew bootRun
```

From another terminal:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization' \
  http://127.0.0.1:8080/api/ping
```

When Spring Security CORS handles it properly, the preflight response **succeeds at the CORS layer**, typically 200, with **one**:

```http
Access-Control-Allow-Origin: https://ui.example.test
```

and allowed methods/headers permitting `GET` and `Authorization`. Headers such as `Vary`, `Access-Control-Max-Age`, and status formatting vary by Spring/container version; do not treat the entire HTTP response as fixed stdout.

Actual request:

```bash
curl -i \
  -H 'Origin: https://ui.example.test' \
  http://127.0.0.1:8080/api/ping
```

Exact successful body:

```text
pong
```

The response has one ACAO for the allowed origin and `X-Request-Id: demo-123`. Compare with an origin outside the allowlist:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://untrusted.example' \
  -H 'Access-Control-Request-Method: GET' \
  http://127.0.0.1:8080/api/ping
```

In Spring's normal CORS processor, preflight from an invalid origin is rejected, typically returning 403; **no** `Access-Control-Allow-Origin` granting permission to that origin may appear. With gateway/security customizations, the status may differ, yet **permission must never be granted to an origin outside the policy**.

### 9.3. Why does this example include Spring Security without creating two owners?

Spring Security sits in the filter chain and is used to **coordinate CORS ahead of authn/authz**. `UrlBasedCorsConfigurationSource` defines the policy and is wired straight into `.cors(...)`. There is no second origin set in MVC or the gateway to conflict with it. Security/CORS filters and controllers retain clean separation of duties.

The example uses `.httpBasic(...)` solely for a default authn mechanism on non-public endpoints; it is not a guide for cross-origin cookie/session auth. If your real API uses bearer tokens, JWT, or OAuth2 Resource Server, configure matching authentication—**never tweak CORS policy to make auth work**.

## 10. Option B: Spring MVC owns the policy, Spring Security shares MVC's source

If a project already uses `WebMvcConfigurer.addCorsMappings`, you can keep **MVC as the policy source** instead of creating a separate `CorsConfigurationSource` bean.

**Alternative** CORS configuration for section 9 (do not put both in the same sample):

**`MvcCorsPolicy.java` — integration sample:**

```java
package com.example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcCorsPolicy implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://ui.example.test")
                .allowedMethods("GET")
                .allowedHeaders("Authorization", "Content-Type")
                .exposedHeaders("X-Request-Id")
                .maxAge(1800);
    }
}
```

In the security configuration for **Option B**, use:

```java
// Replaces .cors(cors -> cors.configurationSource(corsSource))
// when no separate CorsConfigurationSource exists:
http.cors(Customizer.withDefaults());
```

To run Option B cleanly, remove Option A's `corsConfigurationSource()` bean and update `securityFilterChain` accordingly (without injecting `UrlBasedCorsConfigurationSource`). In MVC, Spring Security automatically picks up Spring MVC's policy when no custom `CorsConfigurationSource` is defined.

**This does not mean** `WebMvcConfigurer` + `.cors(withDefaults())` emits two ACAO headers: they are an **integrated** mechanism supported by Spring Security. However, if you then also add a `CorsFilter` bean or scatter `@CrossOrigin(origins = "*")` on controllers, the policy can widen, turn ambiguous, or span multiple layers.

`@CrossOrigin` may be warranted for a specific exception endpoint, yet it should be clearly documented in the architecture and tested to see how it **combines** with global CORS. Scattering annotations across dozens of controllers without an overarching policy is discouraged.

## 11. `@CrossOrigin` and global MVC: why merging can open access too wide

Spring MVC supports CORS globally and locally:

```java
// Illustrative example; DO NOT add to Option A/B samples unintentionally.
@CrossOrigin(origins = "https://partner.example.test")
@GetMapping("/api/ping")
public String pingForPartner() {
    return "pong";
}
```

If global MVC also allows `https://ui.example.test`, Spring Framework merges local and global CORS configs via `CorsConfiguration.combine(...)`. For lists such as origins, the result is normally **additive**; local does not replace the entire allowlist. For single-valued properties such as `allowCredentials` and `maxAge`, local can override global.

Consequences:

- Someone writing the local annotation thinks "only partner is allowed," yet global still allows UI, so the effective origin set is wider.
- A `@CrossOrigin` without explicit origins has broader defaults than intended in some situations.
- When changing global policy, check local exceptions to know the effective policy; reading a single global config block is insufficient.
- Having two Spring sources **does not automatically equal two duplicate headers**. Distinguish **policy merging inside Spring** from **header appending across multiple HTTP hops**.

If clear per-route exceptions are needed, define the per-route/per-handler policy in a single source and test both allowed and denied origins. In microservices, gateway per-route or per-service backend policies are usually cleaner than scattered local annotations.

## 12. Option C: Spring Cloud Gateway is the CORS owner

When multiple services are exposed under **one public gateway**, the gateway is often the natural place to emit consistent CORS headers. Under this option, backends **do not emit ACAO/ACAC on public routes**, or the gateway explicitly strips upstream headers in a tested setup. Backend security still handles authentication and authorization for **actual requests**.

Spring Cloud Gateway **Reactive Server 4.1.x** example — this is a **separate gateway configuration**, not to be pasted into section 9's MVC sample:

**Gateway `application.yml`:**

```yaml
server:
  port: 8081

spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - "https://ui.example.test"
            allowedMethods:
              - GET
              - POST
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
              - X-Request-Id
            maxAge: 1800

      routes:
        - id: api
          uri: http://127.0.0.1:8080
          predicates:
            - Path=/api/**
```

In this example:

- The gateway listens on 8081 and forwards `/api/**` to backend 8080; the URI/backend host suits a **same-machine** demo, not a Docker/Kubernetes setup verbatim.
- `globalcors.cors-configurations` declares CORS policies by **gateway** URL patterns.
- `add-to-simple-url-handler-mapping=true` handles preflight even when route predicates do not match `OPTIONS` (for instance, a predicate matching only specific HTTP methods).
- Do not add `@CrossOrigin`, `WebMvcConfigurer`, or service-side CORS filters for the same public boundary; ensure the backend emits no duplicate CORS headers.
- Specify only the allowed methods/headers the API actually needs; avoid blanket `*`. Listing `OPTIONS` here is an illustrative choice; permissions for actual methods must still match.
- On gateways with multiple routes having different policies, use route-level CORS metadata or specific URL patterns instead of one broad wildcard for every API.

In Spring Cloud Gateway, **route metadata `cors`** also supports per-route policies. Never define conflicting `globalcors` and per-route metadata expecting the framework to guess your intent. If using both, understand exact merge rules for your version and test through the public URL.

**Important for security:** When the gateway owns CORS, preflight must be handled before any gateway authentication filter rejects `OPTIONS`. If Spring Security runs **on the gateway itself**, it must also let valid preflight pass through the proper CORS handler/filter. Gateway `globalcors` does not guarantee a custom filter or an edge WAF ahead of the gateway won't block `OPTIONS`.

## 13. Gateway's `DedupeResponseHeader`: a stopgap, not a long-term architecture

Spring Cloud Gateway 4.1 offers the `DedupeResponseHeader` filter for cases where both the gateway and downstream emit headers such as `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials`.

**Illustrative route configuration example:**

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: api
          uri: http://127.0.0.1:8080
          predicates:
            - Path=/api/**
          filters:
            - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
```

When used, this filter removes **duplicate values**. It supports strategies:

- `RETAIN_FIRST` (default).
- `RETAIN_LAST`.
- `RETAIN_UNIQUE`.

**Never assume deduplication produces the right policy.** Suppose the backend returns `Access-Control-Allow-Origin: https://service.example` while the gateway returns `https://ui.example.test`; keeping first or last can pick the **wrong origin**, even though only one value remains. Deduplication also cannot fix missing `Access-Control-Allow-Headers`, redirected preflights, credential mismatches, or broken cache policies.

When using this filter, understand response filter ordering and each layer's origin policy, and test 200, 401, 403, 404, and 500. Best practice is **removing the second header emitter** and using deduplication only as a temporary migration bridge when shifting CORS ownership.

## 14. NGINX/Ingress/CDN: do not "conveniently" add headers when the backend is already owner

A configuration very prone to duplication:

```nginx
# Anti-pattern when the Spring backend already emits Access-Control-Allow-Origin:
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    add_header Access-Control-Allow-Origin "https://ui.example.test" always;
}
```

If Spring already emitted ACAO, NGINX `add_header` **adds another header** to the final response. `always` only controls which status codes receive the header; it does **not** mean "add only if absent."

When choosing **backend ownership**, the proxy should simply forward requests without writing `Access-Control-Allow-*` or overwriting required `Vary` headers:

```nginx
# Illustrative forwarding location, not a full TLS/production config.
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    # Do not add_header Access-Control-Allow-* here.
}
```

When choosing **NGINX ownership**, implement preflight, actual responses, origin allowlist, credentials, allowed headers/methods, error responses, `Vary`, and upstream CORS header stripping completely. Never just slap `Access-Control-Allow-Origin` onto 200 responses and consider CORS done. When multiple origins are allowed, reflecting raw `Origin` without an allowlist is a security vulnerability.

Especially with ingress controllers, CORS can be turned on via **ingress annotations** or middleware while the app also enables it. Audit effective ingress config, CDN edge rules, WAF response headers, and inherited NGINX `add_header` directives across scopes.

If the gateway is owner while the backend still emits headers, establish **a plan to strip upstream CORS headers** or migrate the policy—never layer appends arbitrarily.

## 15. Preflight can terminate at the gateway and never reach the application

An `OPTIONS` request **does not always reach the Spring Boot service**:

```text
Browser OPTIONS
    |
    +--> CDN/WAF rejects       -> response created by edge
    +--> Gateway handles CORS  -> response created by gateway
    +--> Gateway routes OPTIONS -> Spring Security CORS / MVC
```

This explains why a developer sets a breakpoint in a controller, never sees preflight hit it, and concludes the browser "didn't send a request." To see where requests go, inspect **hop-by-hop network traces** and gateway access logs, not just controller logs.

With gateway ownership, proactively answer valid preflights for allowlisted origins/methods/headers right at the gateway. Actual requests must still pass through authentication/authorization. With backend ownership, the gateway must pass `OPTIONS` through to the backend CORS processor while avoiding generating error responses without CORS headers when browsers need to read errors.

If the gateway returns 401/403 **before the backend**, the backend owner cannot attach ACAO to that response. Either rethink the CORS boundary (e.g., move public-path CORS ownership to the gateway) or ensure consistent edge error-response handling. Never fix it by adding a fixed ACAO to every error response regardless of whether the origin is allowed.

## 16. Filter order in Spring Security and multiple `SecurityFilterChain`s

Spring Security executes its filter chain before controllers. CORS must run in the right order so preflight is not blocked merely for lacking cookies/tokens. With a single `SecurityFilterChain`, section 9 used:

```java
http.cors(cors -> cors.configurationSource(corsSource));
```

In systems with multiple chains, such as `/api/admin/**` and `/api/public/**`, check:

1. Which chain matches preflight and the actual request?
2. Does that chain have the right CORS config and source?
3. Should allowed origins/methods/headers differ between the two paths?
4. Could preflight be caught first by another chain and receive 401/403?
5. Does the gateway apply CORS to the route even when preflight does not match a method predicate?

A single global `CorsConfigurationSource` bean does not automatically cover every multi-chain setup if Security is configured manually. With multiple sources, pass `.cors(...)` an **explicit** source per chain, or build a centralized route-aware source.

**Never do this reflexively:**

```java
// Not a safe solution for preflight:
http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
```

Disabling authorization across the entire API just to make 401s vanish breaks your security boundary. Keep **CORS preflight permission** separate from an authenticated user's permission to execute `GET`/`POST`/`DELETE`.

If the app sits behind a gateway with identity forwarding, Security and the gateway still need a clear trust contract; CORS never verifies user identity or token validity.

## 17. `allowCredentials(true)`, wildcard origins, and cookies

When JavaScript sends cross-origin requests with credentials mode `"include"` (e.g., session cookies), browsers require matching headers:

```http
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Credentials: true
```

Never send:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browsers disallow wildcard ACAO in credentialed CORS. In Spring Framework, when `allowCredentials(true)` is set, `allowedOrigins` must list explicit origins, **never** `"*"`. `allowedOriginPatterns` can be used when patterns are genuinely needed, yet be very careful with domain wildcards, subdomain takeovers, and partner domains; the framework echoes the matching origin rather than `*`.

**Credentialed CORS differs from CSRF:** With session cookies, cookies still need `SameSite`, `Secure`, `HttpOnly`, HTTPS, and proper CSRF protections. Preflight omitting session cookies does not make unsafe actual requests safe. CORS does not prevent HTML form `POST`s or CSRF conditions.

If an API uses bearer tokens in `Authorization`, browsers can emit preflight because that header is not safelisted. `allowedHeaders` must permit `Authorization`, though that must never be mistaken for trusting all tokens or opening all resources to any origin.

Never turn on `allowCredentials(true)` casually "just to stop errors" if the API does not use credentialed browser requests. Enabling unnecessary privileges widens the trust surface.

## 18. Error responses also need a consistent CORS policy

Do not test only HTTP 200:

| Response | Usually created by? | CORS risk |
| --- | --- | --- |
| 200/201/204 | Controller or gateway | Duplicate ACAO from multiple layers |
| 301/302/307 | Proxy, login redirect, Spring Security | Redirects preflight or switches origin/scheme |
| 400/404 | MVC validation/error handler, gateway | Response bypasses the same CORS path |
| 401/403 | Gateway auth, Spring Security | Preflight blocked or actual error lacks ACAO |
| 413 | NGINX/body-size limit | Backend never received request to add headers |
| 429 | WAF/rate limiter | Edge-generated response lacks CORS policy |
| 500/502/503 | App or gateway upstream error | Headers differ between app errors and edge errors |

Browsers cannot expose error bodies to scripts when responses lack valid CORS headers. Hence "server returned 401 yet DevTools only shows CORS" can be **two chained issues**, not automatically a single-layer bug.

If the gateway is owner, confirm the gateway applies CORS for allowed origins even on **gateway-generated** error responses, within safe bounds. If the backend is owner while an edge/WAF intercepts earlier, decide how errors are surfaced without creating a second conflicting CORS policy; sometimes the architecture itself requires moving CORS ownership to the edge.

For requests from **disallowed** origins, omitting ACAO and having the browser refuse to read the body is the intended behavior—not a bug to "patch" with a wildcard.

## 19. Caching, `Vary`, and preflight `Access-Control-Max-Age`

Caching can make policy pass on origin A yet fail on origin B:

```text
Origin A -> Gateway responds ACAO:A -> CDN caches by URL only
Origin B -> CDN returns cached ACAO:A -> Browser B rejects
```

When a server emits dynamic origins from an allowlist, responses usually need:

```http
Vary: Origin
```

Preflight also has inputs:

```http
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

So cache keys and policies must vary across whatever inputs can alter the response. Spring CORS usually adds the relevant `Vary` fields; verify the CDN/gateway **does not strip or overwrite** them.

`Access-Control-Max-Age` controls how long browsers **may cache preflight outcomes**, subject to browser caps, not `Cache-Control: max-age` for actual API responses. When changing origin policies, stale preflights may remain cached by browsers for the allowed period; account for caching or use a clean browser profile when testing new policies.

**Never use `Access-Control-Allow-Origin: *` just to simplify caching** on private APIs. On uncredentialed public APIs, wildcards can be valid, yet must be a deliberate decision independent of authorization.

## 20. How to diagnose duplicate headers hop by hop

Before changing code, collect **two responses** using the same `Origin`, method, and URL path:

```text
A. Hit the backend directly via its internal port (in a test network).
B. Hit the public URL through the gateway/ingress/CDN.
```

**Example A — checking the backend from an authorized environment:**

```bash
curl -si \
  -H 'Origin: https://ui.example.test' \
  http://127.0.0.1:8080/api/ping
```

**Example B — checking the public gateway:**

```bash
curl -si \
  -H 'Origin: https://ui.example.test' \
  https://api.example.test/api/ping
```

If A has **one** ACAO yet B has **two**, the gateway/CDN/ingress is the primary suspect. If A already has two, inspect the service's filters and MVC/Security configurations.

Count headers in a Unix-like shell (only in trusted environments or against test URLs):

```bash
curl -si -H 'Origin: https://ui.example.test' \
  https://api.example.test/api/ping \
  | grep -i '^access-control-allow-origin:'
```

A valid CORS response for an allowed origin has **one ACAO line with one valid origin value**. If a gateway folds multiple values into a single line, that is still invalid; inspect **the content itself**, not just the line count.

Do not use `curl -I` as your sole verification: it sends **HEAD**, whose CORS policy/mappings may differ from `GET`/`OPTIONS`. Use `curl -i` with the exact method and headers matching the browser request.

When HTTP/2 or proxies alter wire header formatting, DevTools or `curl -v` still reveals responses on the wire, though header order and display formatting may differ. Read the **effective field values**.

## 21. Testing preflight properly: origin, method, and headers

To reproduce browser preflight:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type' \
  https://api.example.test/api/orders
```

This is a **test request for a hypothetical API** `/api/orders`, not the `/api/ping` sample endpoint. Substitute a real route and ensure policy allows `POST` when required by business logic.

Observe:

1. Did the request reach the gateway? Did it reach the backend?
2. Does `Access-Control-Allow-Origin` contain exactly one value matching the request origin?
3. Do allowed methods permit **POST**?
4. Do allowed headers permit **Authorization** and **Content-Type**?
5. Was preflight hit by a 301/302 login redirect or 401/403 before CORS ran?
6. Is `Access-Control-Allow-Credentials: true` present if the browser genuinely uses credentials mode `include`?
7. Are `Vary` and `Access-Control-Max-Age` appropriate for caching?
8. Is the **subsequent** actual request permitted by Security and business logic?

`OPTIONS` rarely needs its own explicit controller method. In properly configured MVC/Security, the CORS processor handles preflight ahead of controllers. Writing manual `@RequestMapping(method=OPTIONS)` methods emitting headers risks creating a conflicting policy, breaking method/path matching, and disrupting Security filter order.

## 22. Automated integration test verifying no duplicate headers

For the Spring Boot sample from section 9, `spring-boot-starter-test` is already present. You can test against the real embedded HTTP server rather than just checking that a config bean exists.

**`src/test/java/com/example/cors/CorsHttpTest.java`:**

```java
package com.example.cors;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CorsHttpTest {

    @Autowired
    private TestRestTemplate client;

    @Test
    void preflightGetsExactlyOneAllowedOrigin() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://ui.example.test");
        headers.add(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET");
        headers.add(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization");

        ResponseEntity<String> response = client.exchange(
                "/api/ping",
                HttpMethod.OPTIONS,
                new HttpEntity<>(headers),
                String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getHeaders()
                .get(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .containsExactly("https://ui.example.test");
    }

    @Test
    void actualGetGetsExactlyOneAllowedOrigin() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://ui.example.test");

        ResponseEntity<String> response = client.exchange(
                "/api/ping",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("pong");
        assertThat(response.getHeaders()
                .get(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .containsExactly("https://ui.example.test");
    }
}
```

The `import java.util.List;` line is unused in this test and can be removed; it does not break compilation. In your IDE, enable unused-import warnings to keep examples clean.

Run:

```bash
./gradlew test
```

Both tests align with **Option A** on `/api/ping`, demonstrating that Spring Security handles preflight ahead of authn and the actual response emits **exactly one ACAO**. Tests have no fixed stdout; passing indicates success.

However, this test only exercises **the application's embedded HTTP server**. It cannot catch headers added by a gateway/CDN. You must also run **smoke/integration tests through the public gateway URL** after deployment—testing origin A and origin B, preflight, actual `GET`, actual 401/403, and verifying no duplicate headers in the final response.

If a `@SpringBootTest` with a random port runs on a setup pinning `server.address=127.0.0.1`, it can still connect via loopback, though CI/container environments must ensure localhost connectivity inside that network namespace.

## 23. WebFlux and WebFlux Security share the same ownership problem

In reactive Spring WebFlux apps, CORS can be configured via:

- `@CrossOrigin` on reactive controllers.
- WebFlux global mappings via `WebFluxConfigurer.addCorsMappings`.
- `CorsWebFilter` and a matching `CorsConfigurationSource`.
- Spring Security WebFlux CORS integration via `SecurityWebFilterChain`.
- Spring Cloud Gateway Reactive Server in front.

The principle remains **one source/policy owner per public API boundary**. Yet Servlet classes such as `CorsFilter`, `HttpSecurity`, `SecurityFilterChain`, and `HttpServletRequest` from Spring MVC **are not drop-in equivalents** for WebFlux `CorsWebFilter`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchange`.

Example purely for recognizing WebFlux APIs, not a standalone runnable program:

```java
// Reactive Security configuration excerpt; requires a separate WebFlux project.
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .cors(cors -> { })
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/public/**").permitAll()
                    .anyExchange().authenticated())
            .build();
}
```

WebFlux `.cors(...)` configuration requires a policy source matching your actual stack and version. **Do not paste this snippet directly to replace an MVC `SecurityConfig`**; register a reactive CORS policy and test preflight.

When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot typically chooses **Servlet** by default during web application type detection. Confirm your real stack before hunting for beans or debugging CORS filters, to avoid configuring the wrong world.

## 24. Code review checklist when suspecting duplicate configuration

In the codebase/backend configuration of **the service you are inspecting**, look for:

```text
@CrossOrigin
WebMvcConfigurer.addCorsMappings
WebFluxConfigurer.addCorsMappings
CorsConfigurationSource
UrlBasedCorsConfigurationSource
CorsFilter
CorsWebFilter
http.cors(...)
SecurityWebFilterChain / ServerHttpSecurity.cors(...)
HandlerMapping CORS configurations
```

At the gateway/edge layer, inspect:

```text
spring.cloud.gateway.globalcors.*
Route metadata cors
DedupeResponseHeader
AddResponseHeader / SetResponseHeader
NGINX add_header Access-Control-Allow-*
Ingress CORS annotations
CDN response header policies
WAF / auth middleware returning preflight or errors
```

This is a maintainer checklist; do not lump all grep matches together assuming they are **all active**. Check active runtime profiles, conditions, security chains, route matching, and actual filter ordering. A `@CrossOrigin` on an unscanned class has no effect; an overridden ingress annotation may not appear on responses.

Maintain an ownership table in operations documentation:

| Public path | CORS owner | Allowed origins | Where is preflight handled? | Error response owner |
| --- | --- | --- | --- | --- |
| `/api/shop/**` | Shop backend | `https://ui.example.test` | Spring Security CORS | Backend; proxy errors aligned |
| `/api/admin/**` | Gateway | `https://admin.example.test` | Gateway CORS | Gateway |
| `/assets/**` | CDN | Separate public-asset policy | CDN if needed | CDN |
| Internal `/internal/**` | No browser CORS | No public CORS granted | Not required | Internal security |

This table is an **architectural template**. If any route has two owners or nobody owns error responses, resolve it before release.

## 25. Minimum test matrix

| Scenario | What must be verified |
| --- | --- |
| Preflight from allowed origin | 2xx response, **exactly one** ACAO, sufficient methods/headers |
| Actual `GET` from allowed origin | Right business HTTP status and one ACAO |
| Disallowed origin | No CORS permission granted to that origin |
| Browser sends `Authorization` | Preflight permits header; actual request still requires valid token |
| Cookie-based cross-origin | Explicit origin + ACAC when needed; valid CSRF, `SameSite`, `Secure` |
| Public endpoint returns 401/403 | Not duplicated by gateway and backend; browser sees status per policy |
| Gateway returns 502/503 | Gateway error path handled per CORS owner |
| Multiple origins in allowlist | Each response echoes only **one** matching origin; valid `Vary` |
| `POST` preflight when route predicate checks only `GET` | Gateway does not swallow `OPTIONS` improperly |
| CDN cache enabled | Never serves cached ACAO of origin A to origin B |
| HTTP → HTTPS redirect | Does not send preflight into login/redirect loops |
| `@CrossOrigin` + MVC global | Effective origins/methods do not expand unintentionally |
| NGINX/Ingress adds headers | Does not duplicate upstream CORS, or enforces clear single owner |
| Multiple Security chains | Chain matching request/preflight has the right policy |

When a browser reports an error, capture the **Network tab** including preflight and actual request (if sent), status, request headers, response headers, and redirect chain; then compare against `curl -i`. Never paste just a Console message screenshot and tweak CORS blindly.

## 26. Common errors and fixes at the right root cause

| Error / symptom | Common cause | Fix at the right layer |
| --- | --- | --- |
| `Multiple CORS header 'Access-Control-Allow-Origin' not allowed` | Gateway and Spring both return ACAO | Designate owner, remove redundant policy/header; dedupe is temporary only |
| ACAO becomes `originA, originB` | Backend/proxy joined two origins | Never send a list; emit only the single matching origin |
| `Access-Control-Allow-Origin: *` yet credentialed fetch fails | Wildcard invalid with `credentials: include` | Explicit allowed origin + ACAC per policy |
| Preflight 401 | Spring Security or gateway auth runs before CORS | Position CORS preflight ahead of auth / at owner |
| Preflight 404 | Gateway route predicates fail to match `OPTIONS` | SCG `add-to-simple-url-handler-mapping` or route/preflight design |
| Preflight missing `Authorization` in allowed headers | Policy lacks the requested header | Update `allowedHeaders` at the **owner**, not across three layers |
| `GET` 200 yet JavaScript cannot read | Missing/duplicated/wrong ACAO on actual response | Inspect public response, compare backend vs. gateway |
| Only 200 works, 401/403 blocked | Error generated by another layer lacking ACAO | Design error path per owner |
| Browser origin A works, B fails intermittently | Cached response lacks `Vary: Origin` or bad CDN config | Fix `Vary`/cache key at owner/CDN |
| Preflight succeeds, `POST` returns 403 | CSRF/authz/business policy | Fix authz/CSRF per business rules; do not loosen CORS |
| Response has CORS yet frontend hits mixed content | HTTPS page calling HTTP API | Use public HTTPS URL; never tweak ACAO to bypass mixed content |
| Works locally, fails in production | Ingress/CDN/gateway adds CORS or profile differs | Compare network hops and effective config |
| `@CrossOrigin` has no effect | Security blocked earlier or request missed handler | Check filter chain/path/preflight |
| Multiple `CorsConfigurationSource` beans | Security failed to auto-pick the right bean | Specify `.cors(configurationSource(...))` per chain |
| Missing `Access-Control-Expose-Headers` | JS cannot read custom response header | Expose the right header at the owner; do not change ACAO |

**Note:** A Console CORS error can **mask the real cause**, such as a 502 from a gateway or a 401 from Security. Always inspect the network response before assuming controller policy is wrong.

## 27. Extra safeguard: client-side requests cannot "fix CORS themselves"

Bad workarounds often suggested:

```javascript
// Wrong: Access-Control-Allow-Origin is a RESPONSE header decided by the SERVER.
fetch("/api/orders", {
  headers: {
    "Access-Control-Allow-Origin": "*"
  }
});
```

Adding `Access-Control-Allow-Origin` on a client request **does not permit** the server to share cross-origin data; it can even trigger an extra preflight because it is a custom request header.

Likewise, `mode: "no-cors"` is not a way to read cross-origin APIs normally: the response is restricted to opaque mode, and JavaScript cannot access its body or headers as with CORS-permitted responses. Disabling web security in the browser is only for unusual local debugging and is never a production fix.

A frontend can configure a **same-origin proxy** during development (Vite/webpack dev server) to avoid cross-origin calls in local testing; that does not prove the public deployment's CORS policy works. Always verify URLs, schemes, ports, and configs in production.

CORS is a **server-to-browser contract**; clients cannot unilaterally elevate privileges via request headers.

## 28. Policy ownership thought exercises

**Scenario A — two ACAOs on the same response:** Backend emits ACAO for UI, and the gateway also uses `AddResponseHeader`. Browser rejects it. Explain why controller code still appears to work via `curl` while JS cannot read it; choose either the backend or gateway as owner and fix one layer.

**Scenario B — preflight 401:** Security requires login for `/api/orders`. Browser sends `OPTIONS` without `JSESSIONID`, the gateway forwards it to the service, and gets 401. Describe how to integrate the CORS processor ahead of authn for valid requests **without** disabling authorization on actual `POST`s.

**Scenario C — `@CrossOrigin` + MVC global:** Global allows UI, local allows partner. Under what rule does Spring MVC combine origins? Does this necessarily emit two ACAOs? How do you test the effective origin list to avoid over-permissive access?

**Scenario D — CDN cache:** Two origins are allowed and responses echo the origin dynamically, yet the CDN caches solely by URL. What happens when B receives A's ACAO? Which `Vary` and cache-key policies are needed?

**Scenario E — gateway returns 502:** The backend is the CORS owner, yet never receives the request due to a gateway upstream failure. Browser sees a CORS error instead of 502 details. Should public-boundary ownership be reconsidered? How do you add error handling without creating a second conflicting policy?

**Scenario F — cookie auth:** Frontend uses `credentials: "include"` and the API returns ACAO `*`. Why does the browser reject it? Why is switching to an explicit origin without checking CSRF/`SameSite` still incomplete?

**Scenario G — Spring Cloud Gateway:** A route predicate matches only `GET`, so `OPTIONS` preflight does not match. Which category of cases does `globalcors.add-to-simple-url-handler-mapping` solve, and what still needs testing?

## 29. Conclusion and implementation rules

**Rules to remember:**

1. **One public API boundary — one clear CORS policy owner.**
2. If the Spring backend is owner, Spring Security **integrates the same policy** to handle preflight before authentication; the gateway adds no second headers.
3. If the gateway is owner, downstream emits no CORS on public routes or header stripping is explicitly designed; the gateway handles both preflight and error responses.
4. Global MVC configuration and `@CrossOrigin` **merge** rather than automatically emitting duplicates; always verify the effective policy.
5. `DedupeResponseHeader` only removes duplicates during migration; **it does not decide which origin is right** and does not replace ownership design.
6. **One** valid `Access-Control-Allow-Origin` per response for an allowed origin—never a list of origins or two identical values.
7. `allowCredentials`, allowed methods/headers, `Vary`, and caching must be tested at the **public URL**, not only the backend port.
8. CORS is not authentication, authorization, or CSRF; never disable security to bypass preflight.
9. Before editing anything, capture responses **hop by hop**: browser → edge/gateway → backend, comparing headers and statuses of both preflight **and** actual requests.

**Desired outcome:** Browsers receive one consistent CORS contract, APIs stay protected by Spring Security/gateway authentication, and policies are never accidentally widened or broken by extra header-adding filters across layers.

### Official references

- Spring Framework — CORS in Spring MVC, global/local combination: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — Servlet CORS integration and preflight: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Cloud Gateway 4.1 — Global/Route CORS: https://docs.spring.io/spring-cloud-gateway/reference/4.1/spring-cloud-gateway/cors-configuration.html
- Spring Cloud Gateway 4.1 — DedupeResponseHeader: https://docs.spring.io/spring-cloud-gateway/reference/4.1/spring-cloud-gateway/gatewayfilter-factories/deduperesponseheader-factory.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- MDN — Multiple Access-Control-Allow-Origin headers not allowed: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSMultipleAllowOriginNotAllowed
- MDN — Access-Control-Allow-Origin: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin
- Fetch Standard — CORS protocol: https://fetch.spec.whatwg.org/