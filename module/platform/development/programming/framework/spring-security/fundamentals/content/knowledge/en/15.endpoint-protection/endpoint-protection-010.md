# Testing Unexpected Paths to Detect Protection Gaps

> **Scope:** Spring Security for **Spring MVC/Servlet** applications, focusing on **negative security testing** against URLs, HTTP methods, and entry points outside the expected endpoint list. Examples use **Java 17, Spring Boot 3.5.0, Spring Security 6.x, JUnit 5, and MockMvc**. Boundary-testing principles apply to WebFlux as well, though WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain` and `WebTestClient` instead of the Servlet APIs in the examples.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Understand what an **endpoint protection gap** is: a request can reach a controller, servlet, filter, Actuator, or a newly added route without undergoing the intended authorization policy.
2. Distinguish **approved valid endpoints** from **unexpected paths that must be denied**, even when the caller is logged in or holds high privileges.
3. Use `requestMatchers`, `securityMatcher`, `SecurityFilterChain` ordering, and `anyRequest().denyAll()` to design safe defaults.
4. Build a test matrix covering path variants, HTTP methods, multi-filter-chain setups, newly added paths, context paths, reverse proxies, and unusual URL encoding.
5. Write **MockMvc + Spring Security Test** cases verifying that unexpected paths do not succeed and do not leak data.
6. Distinguish **401, 403, 404, 400** responses and what a single status code *alone does not prove*.
7. Integrate finding unprotected paths into API update workflows and CI.

## 2. The Problem: Protecting Known URLs Can Still Leave Other URLs Exposed

Suppose an application has three clearly defined endpoints:

| HTTP | Path | Intent |
| --- | --- | --- |
| GET | `/api/public/ping` | Public |
| GET | `/api/account/me` | Logged-in users only |
| GET | `/api/admin/report` | Users with role `ADMIN` only |

The team tests all three paths and everything passes. Later, someone adds a controller:

```java
@GetMapping("/api/experimental/export")
String export() {
    return "sensitive-export";
}
```

If security configuration only targets `/api/admin/**`, while other requests get `permitAll()` or fall **outside every `SecurityFilterChain`**, the new endpoint can be called without the intended controls.

This is the key takeaway of the lesson:

> **Do not test only "are the protected paths protected?", also test "are all unapproved paths closed?"**

An "unexpected path" can be a new route whose authorization was forgotten, a legacy/fallback URL, a near-miss path similar to a valid route, a different HTTP method on the same URL, a path registered by another filter/servlet, or a URL normalized differently by a proxy/servlet than the matcher author expected.

A test that only calls `GET /api/admin/report` as an unprivileged user is not enough to catch these cases. You need **boundary/negative tests** covering unlisted entry points as well.

## 3. Three Layers to Verify Separately

### 3.1. `SecurityFilterChain` Selection Layer

Spring Security uses `FilterChainProxy` to pick a `SecurityFilterChain` matching the request. If you declare `http.securityMatcher("/api/**")`, that chain applies only to requests matching `/api/**`.

**Risk:** configuring **only** one chain scoped to `/api/**` can leave `/internal/**`, `/legacy/**`, or new endpoints outside Spring Security's protection. `anyRequest()` inside the `/api/**` chain does **not** apply to paths that never match that chain.

### 3.2. In-Chain Rule Selection Layer

Inside `authorizeHttpRequests`, Spring Security evaluates `requestMatchers` in **declaration order** and uses the first matching rule. For example:

```java
// Example ordering bug: overly broad rule precedes admin rule.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

The admin route already matched `/api/**`, so the `hasRole("ADMIN")` rule behind it never gets a chance to protect it. A test on `/api/admin/report` must catch this.

### 3.3. Application and Infrastructure Routing Layer

Spring MVC, servlet containers, reverse proxies, gateways, Actuator, WebSocket handshakes, and filter-provided routes can interpret paths differently. `@GetMapping("/api/admin/report")` and a separate security matcher can diverge when an application changes context path, servlet path, trailing slash handling, encoded slashes, or adds another servlet.

Therefore, verify **security configuration**, **actual mappings**, and **HTTP paths after deployment**. MockMvc tests are highly valuable, yet they do not simulate every production proxy or container setting.

## 4. Design Principle: Allowlist + Default Deny

For APIs with a strict route policy, an easily testable configuration is:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/account/me").authenticated()
    .requestMatchers(HttpMethod.GET, "/api/admin/report").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Explanation:

- `permitAll()` applies only to GET on the exact public ping route.
- `authenticated()` requires authentication, without checking permissions on a specific resource itself.
- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority under default conventions; pass `"ADMIN"`, not `"ROLE_ADMIN"`, to `hasRole`.
- `anyRequest().denyAll()` denies every request **entering this chain** that did not match the rules above. Hence, if a new endpoint is deployed and the author forgets to declare a policy, that route **does not become public automatically**.
- Specifying `HttpMethod.GET` also prevents `POST`, `PATCH`, `DELETE`, or another method on the same path from inheriting GET's permission.

Not every application needs deny-all on every URL: web apps with static resources, login pages, or business endpoints need corresponding rules. However, every permitted case must be **intentionally defined and tested**. If using an `authenticated()` fallback, recognize it as "anyone logged in may pass"; it does not block a newly added sensitive endpoint by itself.

**Important warning:** when using multiple chains with `securityMatcher`, you need a **final chain covering all requests** or an equivalent global protection mechanism. `denyAll()` in a scoped chain does not protect URLs outside that chain.

## 5. Preparing a Runnable Spring Boot Example

Let's create an API with three valid endpoints and **one unapproved endpoint** `/api/experimental/export`. This last route exists intentionally in the demo to prove the fallback denies **even when a controller can genuinely handle the request**; it does not just return 404 because "there is no handler."

### 5.1. Project Structure

```text
route-boundary-demo/
├── pom.xml
├── src/
│   ├── main/java/demo/routes/
│   │   ├── RouteBoundaryApplication.java
│   │   ├── SecurityConfig.java
│   │   └── DemoController.java
│   └── test/java/demo/routes/
│       └── EndpointSecurityTest.java
```

Requires **JDK 17+** and Maven. The example pins Maven parent `3.5.0` to avoid ambiguity in dependencies; in real projects, use the latest supported patch version compatible with your system.

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>route-boundary-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

`spring-security-test` provides `user(...)`, `csrf()`, and Spring Security testing utilities for MockMvc. `spring-boot-starter-test` provides JUnit, AssertJ, and Spring Test.

### 5.3. Entry Point

`src/main/java/demo/routes/RouteBoundaryApplication.java`:

```java
package demo.routes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RouteBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RouteBoundaryApplication.class, args);
    }
}
```

### 5.4. Controller with Expected Routes and an Unexpected Route

`src/main/java/demo/routes/DemoController.java`:

```java
package demo.routes;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/account/me")
    public String me(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "REPORT_PRIVATE";
    }

    // Has a handler, but is not yet permitted in SecurityConfig.
    @GetMapping("/experimental/export")
    public String experimentalExport() {
        return "UNRELEASED_EXPORT";
    }
}
```

The `/experimental/export` route is a **teaching fixture**: its purpose is to demonstrate the default-deny rule. In a real project, a similar test route should live in a test profile/fixture rather than accidentally shipping an unused endpoint to production.

### 5.5. `SecurityConfig` with an Explicit Fallback

`src/main/java/demo/routes/SecurityConfig.java`:

```java
package demo.routes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/account/me"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/api/admin/report"
                ).hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

An intentional point: **do not call `securityMatcher`** in this single chain, so the chain has the default matcher applying to every request in the Spring Security application. `anyRequest().denyAll()` covers all unlisted URLs, including the `/api/experimental/export` fixture route.

In-memory accounts and static passwords are for demonstration only. In production, use proper authentication, TLS, secure password storage, and never ship demo accounts.

**CSRF remains enabled by default** in this configuration. For `POST/PATCH/DELETE` write requests from MockMvc, add `with(csrf())` to test authorization past CSRF; do not disable CSRF just to make a test easy to run. Whether CSRF should be disabled for a stateless API depends on **how credentials are transmitted** and the risk of browsers automatically sending credentials.

## 6. Automated Testing to Detect Protection Gaps

Create `src/test/java/demo/routes/EndpointSecurityTest.java`:

```java
package demo.routes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingCanBeCalledWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void accountEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/api/account/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/account/me")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:reader"));
    }

    @Test
    void adminEndpointRejectsAReader() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanUseOnlyApprovedAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT_PRIVATE"));
    }

    @Test
    void existingButUnlistedHandlerIsDenied() throws Exception {
        // The handler does exist in DemoController,
        // but no rule allows reaching it.
        mvc.perform(get("/api/experimental/export")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void nearMissRoutesAreDeniedEvenForAdmin() throws Exception {
        String[] unapprovedPaths = {
            "/api/admin/report/",
            "/api/admin/report.json",
            "/api/admin/report/extra",
            "/api/admin",
            "/API/admin/report",
            "/api/admin/REPORT",
            "/internal/admin/report"
        };

        for (String path : unapprovedPaths) {
            var response = mvc.perform(
                    get(path).with(user("admin").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andReturn()
                .getResponse();

            assertThat(response.getContentAsString())
                .doesNotContain("REPORT_PRIVATE")
                .doesNotContain("UNRELEASED_EXPORT");
        }
    }

    @Test
    void unexpectedPostCannotReuseGetPermission() throws Exception {
        mvc.perform(post("/api/admin/report")
                .with(user("admin").roles("ADMIN"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicGetDoesNotOpenPostAtSamePath() throws Exception {
        mvc.perform(post("/api/public/ping")
                .with(user("reader").roles("USER"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

To run:

```bash
mvn test
mvn spring-boot:run
```

When Maven finishes normally, the test suite above has **8 `@Test` methods** and all are expected to pass. This is an **expected outcome from the demo source**, not an actual run log of a project started inside this reading.

Each check contributes differently:

- **Positive controls:** the public URL works; admin actually accesses the proper admin URL. If the entire application were locked down, negative tests could turn "green" while the system is still misconfigured.
- **Negative controls:** regular users cannot enter admin; an endpoint with a handler but no granted permission is still denied; even admin cannot enter non-conforming URLs.
- **Method boundary:** a GET rule does not open POST permission. `csrf()` ensures the 403 is measured at the authorization layer rather than just due to a missing CSRF token.
- **No-leak assertion:** the body of a denied response contains no sensitive data markers, in addition to checking the status.

**Note:** the standard path-variant cases here expect **403** because of `anyRequest().denyAll()`. For URLs without a handler that are **not** blocked early, MVC may return **404**; for URLs rejected by `HttpFirewall`, the HTTP layer may return **400** or handle otherwise per configuration. Do not enforce 403 for every bizarre URL string, especially syntactically invalid requests. The invariant goal is **no unauthorized access and no content leakage**.

### 6.1. Verifying Over Real HTTP

Start the application on port 8080 and run:

```bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/account/me
curl -i -u reader:reader-demo http://localhost:8080/api/admin/report
curl -i -u admin:admin-demo http://localhost:8080/api/admin/report
curl -i -u admin:admin-demo http://localhost:8080/api/admin/report/
curl -i -u admin:admin-demo http://localhost:8080/api/experimental/export
```

For the demo, the expected statuses in order are **200, 401, 403, 200, 403, 403**. Only the fourth authorized request receives the body `REPORT_PRIVATE`. Do not use the demo's hardcoded accounts/passwords outside local environments.

Testing against a real server complements MockMvc because containers, reverse proxies, and real network paths can alter URL handling. When a reverse proxy is present, repeat tests through the **public address behind the proxy**, rather than only calling loopback.

## 7. Building an Unexpected-Paths Matrix

Do not test a few random URLs and conclude everything is airtight. Start from the **actual endpoint list**, then systematically generate variant groups:

| Group | Examples from `/api/admin/report` | What to verify |
| --- | --- | --- |
| Missing/extra segments | `/api/admin`, `/api/admin/report/extra` | Does not accidentally match an overly broad rule |
| Trailing slash | `/api/admin/report/` | Security and controller interpret consistently |
| Case variation | `/API/admin/report`, `/api/admin/REPORT` | Does not rely on case-normalization assumptions |
| File extensions | `/api/admin/report.json`, `/api/admin/report.csv` | Endpoint aliases or suffixes do not open access |
| Different HTTP methods | POST/PUT/PATCH/DELETE/HEAD/OPTIONS on same path | Action-based authorization, CORS/HEAD per design |
| Legacy paths | `/admin/report`, `/v1/admin/report` | No forgotten aliases, redirects, or deprecated routes |
| Duplicate separators | `/api//admin/report` | Verify proxy, container, and firewall handle consistently |
| Dot segments | `/api/../api/admin/report` | No authorization discrepancy after normalization |
| Encoded separators | `/api/admin%2Freport`, `/api/admin/report%2F` | No bypass by encoding `/` |
| Semicolons/matrix params | `/api/admin;v=1/report` | Firewall and matcher do not disagree |
| Other servlet paths | `/internal/admin/report` | Does not fall outside all filter chains |
| Context path/proxy prefix | `/app/api/admin/report` when mounted under `/app` | Matcher corresponds to the path Spring Security actually sees |
| Unpublished APIs | `/api/experimental/export` | Fallback must deny even when a handler exists |
| Error/forward dispatches | Requests forwarded to `/error` or internal forwards | Does not open unintended bypass paths |
| Operational endpoints | `/actuator/**`, health, metrics, mappings | Dedicated policies and network surface |

**Important note on query strings:** `/api/admin/report?format=csv` still has the **same path** `/api/admin/report`; a path-only matcher normally does **not** treat this as a different path. If `format=csv` changes the data or action performed, check permissions in the feature's service/policy layer; never assume changing a query parameter will be blocked by the fallback.

### 7.1. URL Encoding and `StrictHttpFirewall`

Spring Security includes `HttpFirewall` to protect against URL variants that cause discrepancies between the servlet container and matchers. `StrictHttpFirewall` rejects suspicious requests by default, such as semicolons `;`, encoded slashes, backslashes, or unnormalized paths. **Do not relax the firewall just to make an unusual URL "work"** without a business requirement and an analysis of differences across layers.

These cases must be tested on **real infrastructure**, because MockMvc, Tomcat/Jetty/Undertow, gateways, CDNs, and proxies can decode or normalize differently. In an authorized test environment, you can use:

```bash
# Keep dot-segments intact to the server/proxy within what curl allows.
curl --path-as-is -i -u reader:reader-demo \
  'http://localhost:8080/api/../api/admin/report'

# Encoded slash: exact response depends on container/firewall.
curl -i -u reader:reader-demo \
  'http://localhost:8080/api/admin%2Freport'
```

Record the raw URL, HTTP method, response status/body, **whether the request reached the sensitive controller**, and the versions/configs of the proxy, container, and Spring Security. A 400 response rejected by the firewall can be a completely valid security outcome.

### 7.2. HTTP Methods and Method Override

Many policies specify `GET`, `POST`, etc.; tests must probe methods outside the API contract. Specifically:

- **HEAD:** some frameworks automatically support HEAD for GET; in the example, a GET method policy does not mean HEAD is automatically permitted. If HEAD is needed, define and test it intentionally.
- **OPTIONS/CORS:** preflight has its own rules; proper protection allows valid preflight without exposing sensitive data. Never conclude that `OPTIONS 200` means any caller can call GET.
- **POST/PUT/PATCH/DELETE:** test CSRF properly so CSRF failures are not confused with authorization.
- **Method override:** if the app enables `HiddenHttpMethodFilter` or a proxy's `X-HTTP-Method-Override` mechanism, test the **final method seen by both the router and security**. Do not enable override support if the app does not need it.

## 8. Common Bug: A Single `SecurityFilterChain` Covering Only `/api/**`

Consider the following configuration:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

*This is illustrative code, not a standalone file in the section 5 demo.*

If this is the **only chain**, requests to `/internal/status` or `/legacy/export` do not match `/api/**`. Spring Security does not automatically apply a fallback authorization rule from this chain to them. If those URLs have handlers, they may bypass Spring Security.

A multi-chain configuration usually needs a **final catch-all**:

```java
// Place in the same @Configuration class of a multi-chain architecture.
// This is a replacement illustration; do not append to the section 5 demo.
@Bean
@org.springframework.core.annotation.Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
```

The differences:

- `securityMatcher` decides **which chain receives the request**; `requestMatchers` decides **which rule applies inside that chain**.
- `@Order(1)` lets the specific chain be evaluated first; the default chain without `securityMatcher` must be evaluated afterward.
- `anyRequest().denyAll()` in the fallback **is what** covers routes outside `/api/**`.
- `anyRequest().authenticated()` in the API chain is only a login policy, insufficient for sensitive object/role operations. In a real system, replace it with granular per-feature rules.

**Note when mounting multiple servlets:** If an app has multiple Servlets or changes the servlet path, verify matchers attach to the right servlet. You cannot just read a URL in the browser and deduce the exact path string each matcher sees.

## 9. Preventing Missed New Routes with Inventory and Constraint Testing

### 9.1. Building a Realistic Endpoint Inventory

Cross-check at least three sources:

1. **Application runtime:** mappings from Spring MVC `RequestMappingHandlerMapping`, router functions, servlets/filters registered by libraries, Spring Security–provided endpoints, and Actuator.
2. **API contract:** OpenAPI specs, endpoint documentation, business authorization tables, and approved public paths.
3. **Deployment infrastructure:** gateway routes, reverse proxy rewrites, context paths, management ports, ingress rules, and legacy URLs.

`/actuator/mappings` can help inventory part of the mappings when configured/exposed **only in safe environments and access scopes**. Never expose mappings/beans/env endpoints publicly just for testing. Looking only at OpenAPI may also miss endpoints created by libraries, filters, or servlets.

Compare each route as a triple `(HTTP method, effective path pattern, security policy)`, extendable with actor/role, tenant, API version, and source chain.

### 9.2. A Reusable CI Approach

- **Baseline:** obtain the approved route list from repo/config. Tag each route as public, authenticated, role/scope, or custom authorization.
- **Diffing:** detect new runtime routes lacking a policy in the baseline; require rule/test updates if the feature is legitimate.
- **Negative tests:** generate out-of-contract variants for sensitive routes plus existing unapproved paths. Test callers must include **anonymous**, **regular user**, and where needed **admin**, since high-privilege users still must not enter unpublished routes.
- **Positive tests:** keep verifying that valid routes continue to work. This prevents a "everything is forbidden" failure where security tests stay green.
- **Integration smoke:** run additional checks through real reverse proxies/servers for unusual URL strings. Do not use MockMvc as sole proof of URL normalization.
- **Review on changes:** whenever adding controllers, changing mappings, adding chains, editing gateways, installing Actuator, or adding servlets, update the inventory and regression tests.

Do not demand that every randomly guessed URL return one fixed status code. Tie expectations to **policy**: valid route with permission → success; existing route without permission → denied; out-of-contract route → **does not execute functionality / does not return secret data**.

## 10. What Do 401, 403, 404, and 400 Tell You?

| Status | Common interpretation | What cannot be concluded yet |
| --- | --- | --- |
| `401 Unauthorized` | Missing/invalid authentication, often with an HTTP Basic challenge | Does not prove the endpoint is protected by the right business rule |
| `403 Forbidden` | Denied with sufficient context or failed CSRF | Must check whether blocked by authorization, CSRF, firewall, or other logic |
| `404 Not Found` | No handler or app intentionally hides resource | **Does not prove** another handler or a later-added route will be protected |
| `400 Bad Request` | Invalid request, possibly rejected by firewall/container | Does not prove other valid variants are safe |
| `2xx` | Request succeeded at some layer | For sensitive out-of-contract endpoints, this is a **signal to investigate** |

For example: `GET /legacy/admin` currently returns 404. That does not prove a security rule protects `/legacy/admin`; there may simply be no controller yet. If a plugin registers that route tomorrow, the status could turn into 200. You need a **protective fallback** and tests on a route that truly exists yet is unpermitted, like `/api/experimental/export`.

Even when receiving 403, verify the handler was not invoked and had no side effects. For instance, a POST writing to the DB and only then using `@PostAuthorize` to reject the result is **too late**; authorization checks must run before side effects, or be bound to proper transaction boundaries.

## 11. Blind Spots Easily Overlooked

### 11.1. Overly Broad Public Paths

```java
// Risk if a sensitive endpoint appears inside /api/public/**.
.requestMatchers("/api/public/**").permitAll()
```

A controller accidentally moved into the public namespace can become exposed automatically. When a group has few public endpoints, use exact method/path matchers and test new routes in that namespace.

### 11.2. Matcher Order

If `/api/**.authenticated()` precedes `/api/admin/**.hasRole("ADMIN")`, admin endpoints only require login. Test a **regular user without the ADMIN role** against the admin endpoint itself to catch misordering. Do not test only with admin, since admin normally passes both rules.

### 11.3. Security Bypassing the Filter Chain

`web.ignoring()` can cause specified URLs to **bypass the entire Spring Security filter chain**, including many other protection layers. For static/public resources, Spring Security recommends `permitAll()` inside the chain whenever possible. Audit broad ignore rules such as `/resources/**`, `/static/**`, and legacy aliases in particular.

### 11.4. Error and Forward Dispatches

`AuthorizationFilter` can run for `REQUEST`, `FORWARD`, and `ERROR`. A legitimate error can forward to an error page and get blocked again by an overly strict deny rule, producing an unexpected status. If the app must permit certain dispatcher types to render errors/views, test so you do not accidentally expose sensitive handlers via forward. Do not blindly `permitAll()` all internal paths without analyzing dispatch paths and access conditions.

### 11.5. Actuator/Management

Some management endpoints can live on a different context or management port. The main application's `SecurityFilterChain` **cannot implicitly prove** the management port is configured identically. Audit `health`, `metrics`, `mappings`, `env`, `heapdump`, and enabled Actuator endpoints separately; consider network isolation and matching access controls.

### 11.6. Static Content, Downloads, Redirects

A URL absent from controllers does not mean no content is served: resource handlers, default servlets, redirects, download endpoints, web server static directories, or object storage proxies can also return data. Inspect returned files, redirect locations, and final target URLs. Do not rely on UI checks ("button is hidden") as authorization.

### 11.7. Reverse Proxies and Context Paths

Proxies can add or strip an `/app` prefix, normalize `//`, decode `%2F`, or route from a host/path to another service. A request blocked when calling the backend directly can take a different path through the gateway, and vice versa. Test using the **exact public scheme/host/port/path** and compare with backend routes. Do not trust client-supplied `X-Forwarded-*` headers directly unless infrastructure establishes trusted proxy sources.

### 11.8. CORS and CSRF

CORS controls whether browser JavaScript can read responses across origins; **CORS is not authentication/authorization** and does not block curl or server-to-server clients. CSRF protects against forged requests when browsers automatically attach credentials; **CSRF does not replace authorization**. When testing unusual methods, separate CORS/CSRF failures from permission policies to understand the real denial reason.

### 11.9. Dynamically Created Routes

Plugins, versioned APIs, router functions, feature-flagged endpoints, and profile-exposed resources can differ across local/test/staging/prod. Run route inventories and smoke tests on **profiles, dependencies, and configurations close to production**; a test suite knowing only one module's source code does not cover every deployed entry point.

## 12. Workflow for Finding and Fixing a Protection Gap

Suppose `GET /api/experimental/export` is discovered returning 200 to a regular user:

1. **Reproduce under control:** record request method/path/host, test identity, configuration, and response; avoid real user data and impact.
2. **Trace the processing path:** which chain did the request match? Did any `securityMatcher` miss it? Which rule in `authorizeHttpRequests` matched first? Was `web.ignoring()` or a proxy rewrite involved?
3. **Decide business permissions:** should the endpoint be public, authenticated, role-restricted, or require object-level authorization? Do not patch one URL while ignoring sibling routes.
4. **Apply the minimal fix:** add the proper rule before the fallback, adjust chains to cover all requests, or add a catch-all; if needed, enforce per-resource permissions in the service.
5. **Add regression tests:** valid users can use the right route; invalid users and unexpected paths are blocked. Include a test with a real handler to prove it is not merely 404.
6. **Verify through final infrastructure:** repeat tests through the proxy/container with relevant method/encoding/path variants; compare outcomes against approved policy.
7. **Monitor:** log/metric denial outcomes, mapping changes, and anomalous 2xx responses on unclassified routes; avoid logging tokens, passwords, or sensitive payloads.

Do not turn every "denied" path into success: after adding rules, keep positive tests to ensure authorized routes work and services enforce business-data authorization.

## 13. Self-Check Questions

**1. Why is `anyRequest().denyAll()` inside a `securityMatcher("/api/**")` chain insufficient to protect `/internal/secret`?**  
Because `anyRequest()` applies **only after a request has been selected into the chain**. `/internal/secret` does not match `/api/**`; without another chain, it falls outside Spring Security's scope.

**2. If `/legacy/export` returns 404, does that prove the path is safe?**  
No. It may simply lack a handler right now. Check the fallback security chain, route inventory, and what happens if an endpoint appears.

**3. If `/api/**.authenticated()` is declared before `/api/admin/**.hasRole("ADMIN")`, what happens?**  
The broad matcher matches first, letting any authenticated user pass through admin URLs. Reverse the rule order and test with the USER role.

**4. Why must a POST test include `csrf()` when evaluating authorization?**  
Because a missing CSRF token can trigger 403 at the CSRF layer, making you think the authorization rule blocked it even though it never ran.

**5. Is `/api/admin/report?format=csv` a different path from `/api/admin/report` for a path-based request matcher?**  
Usually no. The query string is not part of the path matcher; if `format` alters behavior, the feature must check permissions accordingly.

**6. Is it reasonable for an ADMIN user to get 403 on an unapproved path?**  
Yes. Being admin does not mean being allowed to call every secret or unreleased API; access must be granted by explicit business rules.

**7. Does passing all MockMvc tests prove the production proxy is safe against encoded slashes?**  
No. You must also check the servlet container, firewall, and paths through the real reverse proxy because URL normalization can differ.

## 14. Checklist for Code Review and CI

- [ ] Inventory actual HTTP mappings, including legacy, Actuator, servlets/filters, resource handlers, and dependency-added routes.
- [ ] Every intended route has an explicit policy by method/path, role/scope, or business-data check.
- [ ] `SecurityFilterChain` beans cover the full scope needing protection; a fallback chain handles URLs outside specialized chains.
- [ ] Matchers are ordered from specific to general; the final rule has an intentional default policy.
- [ ] Public URLs open only the right method/path; avoid overly broad ignores or permits.
- [ ] Positive tests confirm valid routes and valid roles continue working.
- [ ] Negative tests confirm anonymous, regular users, and where needed admins cannot access out-of-contract routes.
- [ ] Tests include an **existing but unlisted handler** to verify deny-by-default.
- [ ] Probe trailing slashes, casing, path extensions, extra segments, other methods, and relevant encoding variants.
- [ ] For write methods, separate CSRF errors from authorization; verify no side effects when requests are denied.
- [ ] Test context paths, proxy rewrites, management ports, and relevant dispatcher types separately.
- [ ] Verify status **alongside body and side effects**; never treat isolated 403/404 as proof the entire system is secure.
- [ ] When adding controllers/routes/dependencies, CI detects new mappings and requires policy tests/approval.

## Official Reference Documentation

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher order, `anyRequest`, dispatchers, matching by path/method.
- [Spring Security — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher` and request-selecting chains.
- [Spring Security — HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): path normalization risks and `StrictHttpFirewall`.
- [Spring Security — MockMvc Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): integrating security filters and writing tests.
- [OWASP Web Security Testing Guide — Authorization Testing](https://owasp.org/www-project-web-security-testing-guide/): negative testing mindset and differences between entry points.
