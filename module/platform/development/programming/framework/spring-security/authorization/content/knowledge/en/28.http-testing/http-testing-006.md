# Testing Matcher Order, Wildcards, Servlet Paths, and Boundary Paths

> **Scope:** Spring Security **Servlet**, HTTP authorization layer via `SecurityFilterChain` and `authorizeHttpRequests`. The goal of this lesson is to prove via tests that **the right requests are allowed, boundary requests are blocked**, and reordering matchers does not introduce vulnerabilities. Main examples use Java 17+, Spring Boot 3.5.x, and Spring Security 6.5.x; the `PathPatternRequestMatcher` APIs used are also present in Spring Security 7.x.

## 1. What Must Be Verified After This Lesson?

An authorization configuration that looks reasonable can still be broken because an overly broad matcher is declared before a narrow matcher, the `DispatcherServlet` path is misunderstood, `*`/`**` semantics are misread, or only one "happy" URL was tested. A good test suite must answer:

1. **Which filter chain actually receives the request?** `securityMatcher` selects the `SecurityFilterChain`; with multiple chains, chain ordering matters too.
2. **Which rule wins inside the chain?** `AuthorizationFilter` evaluates `requestMatchers(...).rule(...)` pairs in declaration order and uses **the first matching rule**.
3. **Which parts of the request does the matcher inspect?** HTTP method, path after context path, servlet path, path segments; query strings do not automatically become part of the path pattern.
4. **Are path boundaries protected?** Test the root path, children, siblings with similar prefixes, trailing `/`, differing case, different methods, extra segments, encoded URLs, and differently configured servlet paths.
5. **Do status codes reflect the true cause?** `200` means the request was permitted and handled by the controller; `401` usually means unauthenticated with HTTP Basic; `403` usually means denied or missing CSRF; `404` may simply mean no handler exists. Never infer "secure" from a single status code.

## 2. Two Matching Layers, Two Kinds of Ordering

Servlet flow to test:

```text
HTTP request
    |
    v
FilterChainProxy
    |-- SecurityFilterChain @Order(1), securityMatcher(...) ? --+
    |-- SecurityFilterChain @Order(2), securityMatcher(...) ? --+--> select first matching chain
    |-- Default chain matching all requests ? ------------------+
    |
    v
AuthorizationFilter in the selected chain
    |-- requestMatchers(specific matcher).hasAuthority(...)
    |-- requestMatchers(broader matcher).authenticated()
    |-- anyRequest().denyAll()
    +--> apply only the first matching rule
    |
    v
Allow -> DispatcherServlet -> controller, or deny -> security response
```

- `http.securityMatcher(...)` defines **the filter chain's scope**. `http.authorizeHttpRequests(...).requestMatchers(...)` defines **access permissions inside the selected chain**. A request matching no `SecurityFilterChain` can pass through without Spring Security filters; `anyRequest().denyAll()` in another chain will not rescue that case.
- With **multiple chains**, use explicit `@Order` for specialized chains first, and a final catch-all chain if you want default denial. Inside **each chain**, write narrow rules before broad rules; put `anyRequest()` last.
- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority under default conventions; `hasAuthority("admin")` checks the exact string `admin`. Tests must supply the exact authority in use without mixing the two styles.
- Authentication, CSRF, firewall, CORS, controllers, and method security can all affect outcomes. Authorization tests must isolate these factors to avoid wrong conclusions.

### Wrong-Order Example

```java
// WRONG: every GET /admin/** passes permitAll, including /admin/audit.
.authorizeHttpRequests(a -> a
    .requestMatchers(HttpMethod.GET, "/admin/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

```java
// RIGHT: specific exception precedes broad wildcard.
.authorizeHttpRequests(a -> a
    .requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/admin/**").authenticated()
    .anyRequest().denyAll()
)
```

The two snippets above are **configuration fragments**, replacing the `authorizeHttpRequests` section of an `HttpSecurity`, not standalone Java programs. Never put a broad `permitAll` rule first expecting a specific matcher later to "override" it.

## 3. Wildcards and Boundary Paths

The examples below use `PathPatternRequestMatcher` and the default parser (`PathPatternParser.defaultInstance`). Do not assume all apps use the same engine: older apps may use `AntPathRequestMatcher`, `MvcRequestMatcher`, or regex. When upgrading, pin down the matcher in use and re-run the entire boundary table.

| Pattern | Can match | Must not assume it matches |
| --- | --- | --- |
| `/admin` | Exactly `/admin` | `/admin/users`, `/administrator` |
| `/admin/*` | One segment directly under `/admin`, e.g. `/admin/users` | `/admin/users/7` |
| `/admin/**` | `/admin` and subpaths such as `/admin/users/7` | `/administrator` |
| `/reports/{id}` | One segment at `{id}`, e.g. `/reports/42` | `/reports/42/items` |
| `/assets/*.css` | One matching filename segment in `/assets` | `/assets/css/site.css` |
| `/api/?` | Exactly one character in the final segment, e.g. `/api/a` | `/api/ab` |

`*` matches within **one segment**, `?` matches one character, `**` matches multiple segments (with `PathPattern`, `**` must be at the end of the pattern). `{id}` names a segment and can extract its value; it does not prove the user is authorized to view that `id`. While `/admin/**` can cover `/admin` as well, do not infer that `/admin/*` behaves equivalently.

Confusing pairs that must be tested separately:

- `/admin` ↔ `/admin/`: a trailing slash can change matching; modern default parsers do not automatically treat the two URLs as identical.
- `/admin/item` ↔ `/admin/item/extra`: one segment versus two segments.
- `/admin/item` ↔ `/administrator/item`: sharing a string prefix does not mean sharing the same branch.
- `/reports/42` ↔ `/Reports/42`: the default parser is case-sensitive; do not rely on this behavior if the app customizes the parser.
- `GET /reports/42` ↔ `POST /reports/42`: same path, different method; matchers constraining `HttpMethod` will distinguish them.
- `/reports/42?view=full` ↔ `/reports/42`: query strings do not change path patterns; if permissions depend on query params, design separate logic or matchers.
- `/reports/42` ↔ `/reports/%34%32` and `/reports/%2F`: URL encoding/decoding, proxies, servlet containers, and `HttpFirewall` decide how requests are normalized or rejected. Do not hardcode a 200/403 expectation for every environment; verify safety at real deployment boundaries.

## 4. Complete Example: Report Authorization by Path and HTTP Method

Use a Spring Boot **Servlet MVC** project, Java 17+, with dependencies `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test`, and `spring-security-test`. With Gradle Groovy, the corresponding `dependencies` section is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is **the dependencies section for a project that already has the Spring Boot plugin and repository/dependency management declarations**; it does not replace a full `build.gradle`.

**`src/main/java/example/authorization/AuthorizationDemoApplication.java`**

```java
package example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
```

**`src/main/java/example/authorization/SecurityConfig.java`**

```java
package example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var path = PathPatternRequestMatcher.withDefaults();

        http.authorizeHttpRequests(auth -> auth
            // Must precede /reports/{id}.
            .requestMatchers(path.matcher(HttpMethod.GET, "/reports/public"))
                .permitAll()
            .requestMatchers(path.matcher(HttpMethod.GET, "/reports/{id}"))
                .hasAuthority("report:read")
            .requestMatchers(path.matcher(HttpMethod.POST, "/reports/{id}"))
                .hasAuthority("report:write")
            // Block subpaths not matching the two allowed URL forms.
            .requestMatchers(path.matcher("/reports/**"))
                .denyAll()
            .anyRequest().denyAll()
        );
        // With this configuration, unauthenticated requests to protected endpoints
        // receive an HTTP Basic challenge (typically 401).
        http.httpBasic(Customizer.withDefaults());
        // Keep default CSRF: POST tests must supply a valid token.
        return http.build();
    }
}
```

**`src/main/java/example/authorization/ReportController.java`**

```java
package example.authorization;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/reports")
public class ReportController {
    @GetMapping("/public")
    String publicReport() {
        return "PUBLIC";
    }

    @GetMapping("/{id}")
    String getReport(@PathVariable String id) {
        return "REPORT:" + id;
    }

    @PostMapping("/{id}")
    String updateReport(@PathVariable String id) {
        return "UPDATED:" + id;
    }
}
```

Meaning of the configuration:

- `GET /reports/public` is public even though `/reports/{id}` could also match the string `public`; **priority comes from rule order**.
- `GET /reports/42` requires `report:read`; `POST /reports/42` requires `report:write` and a valid CSRF token per the demo config.
- `/reports/42/extra` and other methods are not granted access; `anyRequest().denyAll()` is the final gate for remaining paths.
- The authorities here are intentionally named `report:read`/`report:write`; the code checks **endpoint-level permissions**, not ownership of individual reports. Permission to view a specific individual's report 42 requires additional checks at the business layer.

## 5. Integration Testing with MockMvc

**`src/test/java/example/authorization/AuthorizationBoundaryTest.java`**

```java
package example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationBoundaryTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicExactPathIsAnonymous() throws Exception {
        mvc.perform(get("/reports/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC"));
    }

    @Test
    void protectedPathIsUnauthorizedWithoutIdentity() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanGetOneReport() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT:42"));
    }

    @Test
    @WithMockUser(authorities = "other")
    void unrelatedAuthorityCannotRead() throws Exception {
        mvc.perform(get("/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void writerCanPostWithCsrf() throws Exception {
        mvc.perform(post("/reports/42").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:42"));
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readDoesNotGrantWrite() throws Exception {
        mvc.perform(post("/reports/42").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void missingCsrfIsForbiddenEvenForWriter() throws Exception {
        mvc.perform(post("/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void extraSegmentCannotBypassExactResourceRule() throws Exception {
        mvc.perform(get("/reports/42/extra"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void trailingSlashIsNotAutomaticallyEquivalent() throws Exception {
        mvc.perform(get("/reports/42/"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void queryStringDoesNotChangePathMatch() throws Exception {
        mvc.perform(get("/reports/42").param("view", "full"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void unlistedMethodIsDeniedEvenWithCsrf() throws Exception {
        mvc.perform(put("/reports/42").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void caseChangedPrefixIsNotSamePath() throws Exception {
        mvc.perform(get("/Reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    void similarPublicPrefixIsStillProtected() throws Exception {
        // "publication" matches /reports/{id}, not /reports/public.
        mvc.perform(get("/reports/publication"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void otherPathIsDeniedByFallback() throws Exception {
        mvc.perform(get("/unlisted"))
            .andExpect(status().isForbidden());
    }
}
```

Run in a project using Gradle wrapper:

```bash
./gradlew test --tests 'example.authorization.AuthorizationBoundaryTest'
```

On Windows PowerShell you can use `.\gradlew.bat test --tests "example.authorization.AuthorizationBoundaryTest"`. **Expected result:** all tests above pass when the app uses the exact configuration and dependencies stated; results are reported by JUnit/Gradle after running, not stdout printed by the Java program itself.

In this example, `@SpringBootTest` + `@AutoConfigureMockMvc` initializes the Security config and registers filters with `MockMvc`. If building `MockMvcBuilders` manually, you must add `springSecurity()`/`FilterChainProxy`; missing filters cause authorization tests to produce wrong results. `@WithMockUser` simulates the principal and authorities in tests and does not prove real login flows or valid JWTs. Therefore, add real authentication tests if the problem requires verifying both.

### Test Matrix to Maintain

| Method, URL | Principal / condition | Expectation in demo | What is proven |
| --- | --- | --- | --- |
| GET `/reports/public` | Unauthenticated | 200 | Exact public rule wins |
| GET `/reports/42` | Unauthenticated | 401 | Private URL must authenticate (HTTP Basic) |
| GET `/reports/42` | `report:read` | 200 | Allowed to read |
| GET `/reports/42` | `other` | 403 | Authenticated but lacking permission |
| POST `/reports/42` | `report:write` + CSRF | 200 | Right method + authority |
| POST `/reports/42` | `report:read` + CSRF | 403 | Read does not imply write |
| POST `/reports/42` | `report:write`, missing CSRF | 403 | CSRF is a separate check layer |
| GET `/reports/42/extra` | `report:read` | 403 | Extra segment does not pass `/{id}` |
| GET `/reports/42/` | `report:read` | 403 | Trailing slash is controlled |
| GET `/Reports/42` | `report:read` | 403 | Case is distinguished by default |
| GET `/reports/42?view=full` | `report:read` | 200 | Query does not change path matcher |
| GET `/reports/publication` | Unauthenticated | 401 | Similar prefix is not the public URL |
| PUT `/reports/42` | `report:write` + CSRF | 403 | Unlisted methods are not implicitly allowed |
| GET `/unlisted` | `report:read` | 403 | Deny-all fallback works |

Key point: **assert both success and denial**. If you only test 403 on endpoints with no controller, you can mask routing issues; thus the allowed cases above also verify **the real body** to prove the controller ran.

## 6. Servlet Path Specifics: Distinguishing Context Path and DispatcherServlet Mapping

Suppose an external request is `GET /shop/mvc/admin/7`:

| Component | Example | Meaning |
| --- | --- | --- |
| `requestURI` | `/shop/mvc/admin/7` | Full request path (excluding query) |
| `contextPath` | `/shop` | Application deployment prefix, e.g. `server.servlet.context-path` |
| `servletPath` | `/mvc` | `DispatcherServlet` mapping prefix, e.g. `spring.mvc.servlet.path` |
| Path inside MVC | `/admin/7` | Path handled by controllers behind the servlet mapping |

With `PathPatternRequestMatcher`, patterns are interpreted **relative to the context path**. If you want to reuse a servlet prefix, configure `basePath("/mvc")` and write remaining patterns relative to that prefix:

```java
import static org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher.withDefaults;

// Snippet inside SecurityFilterChain configuration:
var mvc = withDefaults().basePath("/mvc");
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher("/admin/**")).hasAuthority("admin")
    .anyRequest().denyAll()
);
```

In this example, the matcher checks requests to `/shop/mvc/admin/7` against a pattern matching `/mvc/admin/**` **after stripping context path `/shop`**. Do not include `/shop` in the pattern; nor accidentally omit `/mvc`. Ensure the application's real servlet mapping matches this assumption.

A standalone matcher test to verify prefix stripping (using JUnit 5 and `spring-test`):

```java
package example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ServletPathMatcherTest {
    @Test
    void matchesServletPrefixButNotUnrelatedPath() {
        var builder = PathPatternRequestMatcher.withDefaults().basePath("/mvc");
        var admin = builder.matcher("/admin/**");

        var request = new MockHttpServletRequest("GET", "/shop/mvc/admin/7");
        request.setContextPath("/shop");
        request.setServletPath("/mvc");
        request.setPathInfo("/admin/7");
        assertTrue(admin.matches(request));

        var unrelated = new MockHttpServletRequest("GET", "/shop/other/admin/7");
        unrelated.setContextPath("/shop");
        unrelated.setServletPath("/other");
        unrelated.setPathInfo("/admin/7");
        assertFalse(admin.matches(unrelated));
    }
}
```

A standalone matcher test only proves `RequestMatcher.matches` on a simulated request; **it does not prove `DispatcherServlet` and the controller are mapped properly**. To verify end-to-end, also run `MockMvc` in a dedicated fixture with `spring.mvc.servlet.path=/mvc`, a controller at `@GetMapping("/admin/7")`, and perform `get("/mvc/admin/7").servletPath("/mvc")` with allowed/blocked authorities. When running the real app, test both context paths and reverse-proxy prefixes.

**Version note directly related to servlet path:** Spring Security **7.0.0–7.0.4** has CVE-2026-22753 when combining `securityMatchers(String)` with a `PathPatternRequestMatcher.Builder` bean used to attach a servlet path; paths intended to be protected may fail to select the right filter chain. The fix version is **7.0.5**. If your project falls under the affected configuration, upgrade to the patched version and add a chain-selection regression test for the servlet path; do not assume `requestMatchers` tests suffice to verify `securityMatchers`.

## 7. Multiple SecurityFilterChains: Test Chain Selection Before Testing Permissions

The following example is an **illustrative snippet of two beans**, not a replacement for the complete configuration in section 4:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().hasAuthority("api:read"))
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a.anyRequest().denyAll());
    return http.build();
}
```

Add imports when placing this into a runnable class: `org.springframework.context.annotation.Bean`, `org.springframework.core.annotation.Order`, `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, and `org.springframework.security.config.Customizer`.

With multiple chains, **do not assume** `anyRequest().denyAll()` inside `apiChain` will handle `/outside`: the `/outside` request does not match `securityMatcher("/api/**")`. Tests should prove `/api/resource` enters the API chain with valid and invalid permissions, while `/outside` is still blocked by the fallback. Test `/api`, `/api/`, `/apis`, and a path outside `/api`; if there is a servlet `basePath`, test that exact path too. Matcher declarations per chain must match your project's version/engine.

## 8. Abnormal Paths, Firewall, and Status Codes

The following cases form a **policy-driven security test checklist**; do not assume all of them will return 403:

| Group | Data to try | Verification |
| --- | --- | --- |
| Path traversal/normalization | `/admin/../public`, `/admin//audit` | Proxy, servlet container, `StrictHttpFirewall` create no path outside rules |
| Encoded separator | `%2F`, `%5C`, double-encoding | URL is rejected or shares the same policy after decoding; confirm on real container |
| Path parameters | `/admin;v=1/audit` | Does not alter matcher results; watch semicolon `;` policy |
| Case/trailing slash | `/Admin`, `/admin/` | Does not accidentally change permissions via parser or redirect |
| Method | GET, HEAD, POST, PUT, DELETE, OPTIONS | Specific methods and CORS preflight are handled intentionally |
| Dispatcher | REQUEST, FORWARD, ERROR | Rules per dispatcher type if the app has forward/error routes |

`StrictHttpFirewall` can **reject requests before `AuthorizationFilter`**, yielding different statuses or exceptions depending on environment and handlers. If a test gets 400, 403, or `RequestRejectedException`, inspect logs/filters before claiming the matcher executed. `MockMvc` tests may not faithfully emulate reverse proxies/servlet containers; for dangerous URL variants, also run HTTP integration tests against the application's real port.

`401 Unauthorized` and `403 Forbidden` in this lesson are **expectations of the stated HTTP Basic + CSRF configuration**. When switching to `formLogin`, OAuth2 resource server, or a custom `AuthenticationEntryPoint` or `AccessDeniedHandler`, response codes may differ; test according to the real security contract. `404 Not Found` and `405 Method Not Allowed` can originate from MVC **after** security passes the request: they do not themselves prove permissions were checked properly.

## 9. Workflow for Writing Tests for a New Rule

1. **Specify the contract**: method, URI and servlet/context path, principal/authority, whether a controller exists, expected status/body.
2. **List competing matchers**: specific rule, broad rule, method-based matcher, `anyRequest`; with multiple filter chains, also list `securityMatcher` and `@Order`.
3. **Create control pairs**: one request that must be allowed and a similar request that must be denied; include at least one anonymous case and one authenticated wrong-authority case.
4. **Test boundaries**: base path, child segments, extra segments, similar prefixes, trailing `/`, casing, different methods, query params, CSRF, servlet path; only add encoding/firewall cases that the app actually accepts or faces risk from.
5. **Assert the right cause**: for success cases, verify body/handler; for denial cases, ensure a matching handler exists when proving an authorization rule, and isolate CSRF and firewall.
6. **Re-run after every route/matcher/Spring Security change**. Never make tests pass by loosening `permitAll` or disabling security filters; first find which matcher actually matched.

### Common Mistakes and Root-Cause Checks

- **Broad rule before narrow rule:** add a test `GET /admin/audit` with a regular user; move specific rules first.
- **Confusing `securityMatcher` and `requestMatchers`:** check which filter chain is actually selected and whether a fallback exists; do not look only at `anyRequest()`.
- **Confusing servlet path/context path:** log or inspect `requestURI`, `contextPath`, `servletPath`, and `pathInfo` in tests; match `basePath` to the servlet mapping.
- **Tests checking only deny statuses:** add 200 cases with response body to prove the controller ran.
- **Authority mismatch due to `ROLE_` prefix:** stay consistent with `hasRole`/`roles` vs `hasAuthority`/`authorities`.
- **POST returns 403 despite valid permission:** add `with(csrf())` if policy requires CSRF, then test missing-token separately.
- **MockMvc drops filters:** use `@AutoConfigureMockMvc` with filters enabled, or `apply(springSecurity())` when building `MockMvc` manually.
- **Assuming wildcards behave identically across versions:** identify the actual engine/parser, test slashes, `**`, `;`, encoded paths, and guard upgrades with regression tests.
- **Confusing resource owner checks:** request-level `hasAuthority` only checks broad permissions; add `@PreAuthorize`/`AuthorizationManager` or business checks per object.

## 10. Self-Verification Exercises

1. Swap the two rules GET `/reports/public` and GET `/reports/{id}` in the example. Run `publicExactPathIsAnonymous`: the changed outcome proves **first match wins**. Then restore the right order.
2. Add an endpoint `GET /reports/42/items` and a rule allowing only `report:read:items`. Write a test proving an account with only `report:read` cannot automatically access the new path; place the new rule before the `/reports/**` fallback.
3. Move the app to servlet path `/mvc` in a separate fixture. Test `/mvc/reports/42`, `/reports/42`, and context path `/shop` to verify present/missing prefixes.
4. Create two `SecurityFilterChain`s with `@Order` and intentionally omit the fallback in an experimental fixture. Observe the difference versus a config with a fallback, then restore the default-deny policy.
5. Build a permission test matrix for three roles: anonymous, reader, writer; each method/path must have both allow and deny cases.

**Completion criteria:** tests must detect rule order changes, single-segment or servlet-prefix mismatches, different methods, and missing permissions/CSRF. A path returning 404 or rejected by the firewall must be classified accurately instead of being treated as sole proof of authorization.

## Official References

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — rule ordering, matchers, and servlet path.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — multiple `SecurityFilterChain`s and `securityMatcher`.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html) — simulated principals and integrating security into `MockMvc`.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) — valid/invalid tokens in tests.
- [PathPatternRequestMatcher.Builder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html) — `matcher`, `basePath`, and method.
- [Spring Security advisory CVE-2026-22753](https://spring.io/security/cve-2026-22753/) — chain selection bug when combining `securityMatchers(String)` and servlet path in Spring Security 7.0.0–7.0.4.