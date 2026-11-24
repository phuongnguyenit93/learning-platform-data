# Re-verifying Endpoints, Method Security, and External Integrations After an Upgrade — Spring Security Servlet

## 1. Objective and scope

Upgrading **Spring Boot / Spring Security** is more than bumping version numbers and making sure the application starts. More importantly, you must verify the **security contract still holds**: public endpoints remain intentionally public, protected endpoints do not widen access, service-layer annotations actually execute, and external identity/partner systems continue working over TLS, tokens, callbacks, and sessions as designed.

This lesson targets **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC/Servlet**. Examples use the `SecurityFilterChain` DSL and `@EnableMethodSecurity`. Exact APIs and behavior can vary across 3.x/6.x releases; always cross-check the version **actually managed by your dependency BOM**, the corresponding migration/release notes, and your project's configuration. Do not treat these examples as guaranteeing identical secondary APIs across every Spring Boot 3.x release.

After this lesson, you will be able to:

1. Capture a **pre-upgrade** endpoint and permission baseline and verify it **post-upgrade** across principal × HTTP method × URL × resource.
2. Audit `SecurityFilterChain`, matcher ordering, CSRF, CORS, sessions, entry points, and 401/403/302/405 responses.
3. Ensure `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` execute through Spring AOP proxies without self-invocation bypasses or shifted principal/authority semantics.
4. Write **Spring Boot integration tests using MockMvc and Spring Security Test** to catch HTTP and method-security regressions, including cross-owner/cross-tenant cases.
5. Verify integrations: OAuth2/OIDC, JWT Resource Server, SAML2, LDAP where used, and downstream APIs; distinguish login, token validation, certificate, network, and contract failures.
6. Design smoke tests, canaries, safe logging, and conditional rollbacks without lowering security just to reach a passing test rate.

**Principle:** `BUILD SUCCESSFUL`, all beans initializing, or a `/health` endpoint returning 200 **does not prove authorization is right**. Tests must cover both **allowed** and **denied** paths.

## 2. Map of notable changes when moving to Spring Security 6

| Dimension | What to compare during upgrade | Risk if overlooked |
| --- | --- | --- |
| Java / Servlet namespace | Java 17+, Spring Framework 6 uses `jakarta.servlet.*` instead of `javax.servlet.*` | Custom filters, servlet listeners, and external libraries fail at compile/runtime |
| HTTP security declaration | `SecurityFilterChain` beans replacing legacy `WebSecurityConfigurerAdapter` subclasses | New chain omits previous matchers/handlers |
| Matchers | `authorizeHttpRequests`, `requestMatchers`, `securityMatcher`, MVC matchers, and order | Endpoints enter the wrong chain or broad rules shadow specific rules |
| Method security | `@EnableMethodSecurity` and method-security advisors | `@PreAuthorize` stays in source yet never runs |
| Context persistence | `SecurityContextHolderFilter` / explicit save is standard in 6.x | Custom login sets `ThreadLocal` yet the next request is anonymous |
| CSRF | Protects state-changing requests by default in web/session contexts | POSTs return 403 after upgrade, or worse: CSRF is disabled to “fix” it |
| CORS / preflight | `OPTIONS`, origin allowlist, credentials/cookies | Browsers cannot call APIs even when `curl GET` works |
| Authentication | Password encoder, principal mapping, role/scope prefixes | `hasRole`/`hasAuthority` evaluate differently than expected |
| OAuth2 / SAML2 | Callback paths, state/nonce, issuer/metadata, cookies, keys | SSO loops, signature mismatches, invalid state |
| JWT Resource Server | Issuer, audience, algorithms, JWKS, scopes, authority converter | Wrong API/tenant tokens accepted, or valid tokens get 401 |
| External HTTP clients | TLS, truststores, mTLS, redirects, headers, timeouts, retries, JSON schemas | Partner calls fail or leak tokens/credentials |
| Sessions / clustering | `SameSite`/`Domain`, session serialization, and Redis namespaces | Login drops only when switching nodes or behind a reverse proxy |

**Do not upgrade blindly from another version's guide.** Inventory running versions, Spring Boot's BOM, Java runtime, Servlet container, IdP adapters, OpenSAML, JDBC drivers, Redis clients, HTTP clients, test libraries, and existing security policies. On Boot 3, check for dependencies still referencing legacy `javax.servlet` only on rare runtime code paths.

### 2.1. A migration is more than renaming APIs

Legacy configurations may use deprecated or removed matcher/authorization methods. Moving to:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
    return http.build();
}
```

is only an **illustrative configuration snippet**. For an application to handle authentication properly, you must also configure the right mechanism (`httpBasic`, `formLogin`, `oauth2Login`, `oauth2ResourceServer`, etc.) along with CSRF, CORS, sessions, and exception handling. **Do not** assume replacing `.antMatchers(...)` with `.requestMatchers(...)` preserves identical path-matching across every URL; test patterns with wildcards, trailing slashes, path variables, and encoded paths.

## 3. Capture a baseline before upgrading

A minimal regression table should come from **business policy** (not from “whatever tests currently pass” if prior security bugs are suspected):

| ID | Principal/role | Request | Resource | Expected outcome |
| --- | --- | --- | --- | --- |
| E01 | Anonymous | `GET /healthz` | Public health | 200 |
| E02 | Anonymous | `GET /api/reports/101` | Alice's report | 401 (HTTP Basic/Bearer) or 302 (form login) |
| E03 | Alice, with `SCOPE_reports:read` | `GET /api/reports/101` | Owner Alice's report | 200 |
| E04 | Alice, with read scope | `GET /api/reports/202` | Ops's report | 403 or 404 per policy |
| E05 | Alice, missing export scope | `POST /api/reports/export` + CSRF | Export | 403 |
| E06 | Ops, with `SCOPE_reports:export` | `POST /api/reports/export` + CSRF | Export | 200 |
| E07 | Ops, with export scope | POST export **missing CSRF** in web session chain | Mutation | 403 |
| E08 | Alice, lacking integration role | `GET /api/partner/status` | Downstream status | 403; **never calls partner** |
| E09 | Ops, `ROLE_INTEGRATION` | `GET /api/partner/status` | Downstream status | 200 when mock partner returns 200 |
| E10 | Authenticated user | Undeclared endpoint | Unknown route | Denied by default |
| E11 | Tenant A | Endpoint with ID belonging to Tenant B | Cross-tenant | Denied, no data leaked |
| E12 | JWT with wrong `aud` | Bearer on API | Wrong recipient | 401 even with valid signature |
| E13 | Expired JWT / wrong issuer | Bearer on API | Invalid token | 401 |
| E14 | Cross-origin browser | `OPTIONS`/GET API with valid CORS | Preflight/actual | Only allowed origins served |
| E15 | Session-authenticated user | Logout, then reuse old ID | Invalidated session | Not authenticated |

This is a **sample baseline**, not a rigid contract for all systems. Form login normally redirects 302 when unauthenticated; Resource Servers normally return 401. Systems may hide object existence with 404 instead of 403 to curb ID enumeration. Document **how denials are returned** and avoid accidentally changing semantics after upgrading.

**Negative tests are mandatory:** if you only test “Ops can export” and skip “Alice cannot export,” an overly broad rule can slip into production with all happy-path tests green.

## 4. Re-verifying endpoints from the outside in

### 4.1. `securityMatcher` selects the chain; `requestMatchers` selects rules inside it

Two-chain example (illustrative code; add matching imports):

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/**")
                .permitAll()
            .anyRequest().authenticated()
        )
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            Customizer.withDefaults()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

**Note:** `@Order` determines which chain is evaluated first; the first matching chain handles the request. Callback and logout URLs must sit inside the right chain. If an SSO callback falls outside existing chains or into a stateless JWT chain, state/sessions and authentication will mishandle it.

With Spring MVC, matchers can be sensitive to `HandlerMappingIntrospector` configuration, servlet paths, context paths, and Spring Framework/Boot changes. Never assume `requestMatchers("/api/**")` handles every encoded path or trailing slash identically without testing real URLs.

### 4.2. Four scenarios to test for every sensitive endpoint

1. **Anonymous:** protected endpoints return no data and follow the right entry point/redirect.
2. **Authenticated yet lacking authority:** returns 403 or the policy's denial response.
3. **Right authority yet wrong owner/tenant/resource:** still denied. A general scope **never** permits reading another user's record.
4. **Right permissions and right resource:** returns 2xx with the right data without bypassing security to pass tests.

Also test **HTTP methods**: permitting safe GET must not implicitly allow POST, DELETE, or PATCH; `requestMatchers(HttpMethod.GET, ...)` protects GET only. An unintended `anyRequest().permitAll()` can expose new endpoints after an upgrade.

### 4.3. 401, 403, 302, and 404

| Response | When commonly seen | What not to assume |
| --- | --- | --- |
| 401 Unauthorized | Authentication needed or Bearer token invalid on API | Every 401 is an expired token; could be chain/decoder |
| 403 Forbidden | Authenticated yet lacking permission, or rejected by CSRF | Every 403 comes from `hasRole` |
| 302 Found | Form login redirect to `/login`, or OAuth2/SAML redirect to IdP | Every redirect means login succeeded |
| 404 Not Found | Missing route or intentionally masking unauthorized objects | Every 404 proves the object truly does not exist |
| 405 Method Not Allowed | Route exists, yet HTTP method is not mapped | Every 405 is a security bug; could be MVC routing |
| 5xx | App/IdP/Redis/downstream failure, serialization/exception | Never “fix” by disabling authentication |

In regression reports, specify the error contract: HTTP status, `WWW-Authenticate`, `Location`, JSON error schema, CORS headers, cache policy, and browser redirect behavior. Do not assert only happy-path status codes.

### 4.4. OPTIONS, CORS, and CSRF after an upgrade

CORS preflight can precede **the actual request** when frontends issue cross-origin requests with custom headers or methods. Spring Security must configure CORS explicitly with allowed origins; credentialed responses cannot use wildcard origins. A preflight `OPTIONS` returning 401 does not prove the GET endpoint blocks the user; it means the browser will not send/read the request under current policy.

CSRF must stay active for **web apps using cookie/session authentication**. POST/PUT/PATCH/DELETE without a CSRF token can return 403 even when the principal has full authority. APIs accepting **only** Bearer tokens in the `Authorization` header with no auto-sent cookies can use a different CSRF strategy, evaluated per chain. **Never disable CSRF app-wide simply because POST tests fail.**

## 5. Method security: annotations in source must be proven to run

### 5.1. From global method security to `@EnableMethodSecurity`

Spring Security 6 commonly configures:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` are enforced by method-security interceptors/advisors. Enabling the annotation does not mean every internal call is intercepted; Spring AOP proxies are integral to the design.

| Annotation | When evaluated | Notes |
| --- | --- | --- |
| `@PreAuthorize` | Before the method executes | Ideal for mutations, ownership guards, or required authorities |
| `@PostAuthorize` | After the method returns | Side effects may **have already occurred**, so insufficient alone for writes |
| `@PreFilter` | Filters each argument item before execution | Can **silently drop items** without returning 403 for the whole batch |
| `@PostFilter` | Filters each result item after execution | Does not stop queries from reading unauthorized rows; awkward with pagination |

After upgrading, check `@Secured`/JSR-250 if used by the app: they have separate enablement flags (`securedEnabled`/`jsr250Enabled`), rather than assuming `@EnableMethodSecurity` turns on every annotation style by default. With `@RolesAllowed`/`@Secured`, verify the `ROLE_` prefix and enabled modes.

### 5.2. `hasRole` differs from `hasAuthority`

- `hasRole("ADMIN")` normally checks `ROLE_ADMIN` under the default role prefix.
- `hasAuthority("ROLE_ADMIN")` checks the **exact string**.
- JWT `scope=reports:read` in Resource Server defaults to `SCOPE_reports:read`.
- Never mistakenly swap `hasAuthority("SCOPE_reports:read")` for `hasRole("reports:read")`.
- If the upgrade changed a custom `JwtAuthenticationConverter`, claims, issuer, or authority mapper, test **real `Authentication.getAuthorities()`** after token verification.

Never grant `ROLE_ADMIN` automatically to every user holding an `admin` scope unless that is the IdP contract. Roles, scopes, and permissions have distinct semantics, especially in multi-tenant apps.

### 5.3. Self-invocation and proxy bypass

```java
@Service
class ReportsService {

    public void controllerEntry() {
        restrictedAction(); // this-call: typically bypasses the Spring AOP proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void restrictedAction() {
        // Sensitive action.
    }
}
```

This is an **illustrative anti-pattern**. Tests calling `controllerEntry()` can still run `restrictedAction()` despite its privilege annotation because intra-bean `this` calls bypass the proxy. Place guards on public methods of Spring-managed beans invoked through proxies, or enforce explicit authorization at the service boundary.

Avoid `new ReportsService(...)` inside controllers instead of injecting the bean; manually constructed instances have no method-security advice. Under proxy mode, `final`/`private` methods and certain self-invocations may not be intercepted as expected.

### 5.4. Checking owner/tenant beyond authorities

Holding `SCOPE_reports:read` does not allow reading **every report**. When a resource ID comes from a path parameter, the policy must check **owner/tenant against a trusted server-side source**, never trusting `owner`/`tenantId` sent by the client in JSON.

Illustrative expression:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports:read') and " +
    "@ownershipPolicy.isOwner(#p0, authentication.name)"
)
```

`#p0` references the first parameter regardless of whether parameter names are preserved in compiled bytecode. `ownershipPolicy` must be a Spring bean. In multi-tenant apps, real policy functions must verify both tenant/ACL membership and guard against TOCTOU races between check and use (transactions, optimistic locking, or conditional updates).

## 6. Runnable project: Spring Boot 3.x + Java 17 with endpoints, method security, and an external partner

The small example below creates a standalone **regression fixture** testing three layers: HTTP endpoints, service methods, and external integration. It uses **HTTP Basic locally/in tests** to avoid needing a live IdP, keeps default CSRF enabled, and **mocks the partner client in tests**. Its purpose is proving authorization is not lost during an upgrade.

Create a Spring Initializr project with Java 17+, Spring Boot 3.x, Gradle Groovy, Spring Web, and Spring Security. `@MockBean` is supported across common Boot 3.x lines even though deprecated in newer releases; on Spring Framework 6.2/Boot 3.4+, you can migrate cleanly to `@MockitoBean` and adjust imports.

### 6.1. Dependencies

The `dependencies` block in `build.gradle` (keep plugins, BOM, and repositories/versions generated by Initializr):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Layout:

```text
src/main/java/com/example/upgradeaudit/
  UpgradeAuditApplication.java
  SecurityConfig.java
  OwnershipPolicy.java
  ReportService.java
  PartnerStatusClient.java
  HttpPartnerStatusClient.java
  PartnerService.java
  ApiController.java
src/main/resources/
  application.yml
src/test/java/com/example/upgradeaudit/
  SecurityRegressionTests.java
```

### 6.2. `UpgradeAuditApplication.java`

```java
package com.example.upgradeaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UpgradeAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(UpgradeAuditApplication.class, args);
    }
}
```

### 6.3. `SecurityConfig.java`

```java
package com.example.upgradeaudit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("local-alice-password"))
                .authorities("SCOPE_reports:read")
                .build(),
            User.withUsername("ops")
                .password(encoder.encode("local-ops-password"))
                .authorities(
                    "ROLE_INTEGRATION",
                    "SCOPE_reports:read",
                    "SCOPE_reports:export"
                )
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/healthz", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Default CSRF is kept. Mutating POSTs require a token if
        // this chain is used in a browser/session model.
        return http.build();
    }
}
```

Demo usernames/passwords are for internal testing only; real environments must use an IdP/user store, MFA, and secret management per policy. HTTP Basic requires HTTPS; never use demo credentials on public networks. `SCOPE_reports:*` here are **authorities explicitly assigned in the fixture**, not verified JWT claims.

**Two layers of defense:** HTTP requires `.authenticated()` for `/api/**`, while the service enforces **specific authorities and resources** via `@PreAuthorize`. If method-security advice stops running after an upgrade, negative tests catch it even though the HTTP filter lets authenticated users through.

### 6.4. `OwnershipPolicy.java` — server-side authorization source

```java
package com.example.upgradeaudit;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component("ownershipPolicy")
public class OwnershipPolicy {

    private static final Map<Long, String> OWNERS =
        Map.of(101L, "alice", 202L, "ops");

    public boolean isOwner(long id, String username) {
        return username != null
            && username.equals(OWNERS.get(id));
    }

    public String ownerOf(long id) {
        return OWNERS.get(id);
    }
}
```

This is a small **in-memory test dataset**, not a production ACL. In real systems, check ownership and tenant in a repository or policy service rather than trusting an `owner` field in the HTTP body. If an ID does not exist, `isOwner` returns false: the demo fails closed rather than leaking data. Choosing 403 vs 404 for invalid IDs must align with your product contract.

### 6.5. `ReportService.java` — method-level guards

```java
package com.example.upgradeaudit;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final OwnershipPolicy ownership;

    public ReportService(OwnershipPolicy ownership) {
        this.ownership = ownership;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_reports:read') and " +
        "@ownershipPolicy.isOwner(#p0, authentication.name)"
    )
    public Map<String, Object> getReport(long id) {
        return Map.of(
            "id", id,
            "owner", ownership.ownerOf(id)
        );
    }

    @PreAuthorize("hasAuthority('SCOPE_reports:export')")
    public String export() {
        return "exported";
    }
}
```

`getReport` should not be invoked via `new ReportService(...)`; inject the Spring bean instead. `export()` only returns a demo string with **no real side effects**. When actually exporting data or writing files, enforce policies on report sets, tenants, sensitive fields, auditing, and output storage.

If `@PreAuthorize` stops working, Alice could read report 202 or export reports. Thus this fixture detects method-security regressions rather than being solely a happy-path sample.

### 6.6. `PartnerStatusClient.java` — external integration port

```java
package com.example.upgradeaudit;

public interface PartnerStatusClient {
    String status();
}
```

Extracting an interface lets tests replace the external dependency with a mock. Mocking stabilizes security behavior tests, yet **does not test real TLS/JSON/status-code contracts**; cover those separately per Section 10.

### 6.7. `HttpPartnerStatusClient.java` — Java 17 HTTP client

```java
package com.example.upgradeaudit;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class HttpPartnerStatusClient implements PartnerStatusClient {

    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

    private final URI endpoint;

    public HttpPartnerStatusClient(
            @Value("${partner.status-url}") String url) {
        endpoint = URI.create(url);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                "Partner endpoint must use HTTPS");
        }
    }

    @Override
    public String status() {
        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        try {
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                    "Partner HTTP " + response.statusCode());
            }
            return response.body();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Partner call interrupted", ex);
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Partner transport failure", ex);
        }
    }
}
```

This class **compiles on JDK 17**, enforces connection/request timeouts, and requires HTTPS URLs. Never implicitly forward user `Cookie` or `Authorization` headers to partners. If OAuth2 client credentials, service tokens, or mTLS are needed, configure them **separately** and test audience/scope/trust per contract.

In production, handle response bodies/content-types/schemas, response size limits, retries/backoff on idempotent calls, circuit breakers, and safe telemetry. Non-200 HTTP statuses here throw `IllegalStateException` rather than mapping to standard gateway codes; that is intentional **test simplification**, not full operational error handling.

### 6.8. `PartnerService.java` — never call the partner when unauthorized

```java
package com.example.upgradeaudit;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PartnerService {

    private final PartnerStatusClient client;

    public PartnerService(PartnerStatusClient client) {
        this.client = client;
    }

    @PreAuthorize("hasRole('INTEGRATION')")
    public String readStatus() {
        return client.status();
    }
}
```

`hasRole('INTEGRATION')` maps to authority `ROLE_INTEGRATION` under the default prefix. The annotation sits **before** the network call. Alice lacks this role; the method must reject before `client.status()` is ever called. That is a crucial negative test after an upgrade.

### 6.9. `ApiController.java` — real routes through SecurityFilterChain

```java
package com.example.upgradeaudit;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final ReportService reports;
    private final PartnerService partner;

    public ApiController(
            ReportService reports,
            PartnerService partner) {
        this.reports = reports;
        this.partner = partner;
    }

    @GetMapping("/healthz")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports/{id}")
    public Map<String, Object> report(@PathVariable long id) {
        return reports.getReport(id);
    }

    @PostMapping("/api/reports/export")
    public String export() {
        return reports.export();
    }

    @GetMapping("/api/partner/status")
    public String partner() {
        return partner.readStatus();
    }
}
```

`/healthz` is public for process health checks without leaking secrets or config. Production apps can separate liveness/readiness and access controls, yet public health must never expose user/tenant lists, tokens, or IdP/Redis settings.

### 6.10. `application.yml`

```yaml
partner:
  status-url: https://partner.example.test/status
```

This is an **illustrative URL**, not a live server. The tests below mock the client so no external network calls occur. When exercising `/api/partner/status` on the demo app without mocks, point it to a real test partner via environment/external config; never force production HTTP clients to trust all certificates just to get 200.

## 7. Runnable regression tests: MockMvc, CSRF, method security, external boundary

File `src/test/java/com/example/upgradeaudit/SecurityRegressionTests.java`:

```java
package com.example.upgradeaudit;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRegressionTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService reports;

    @MockBean
    PartnerStatusClient partnerClient;

    @Test
    void publicHealthIsAccessible() throws Exception {
        mvc.perform(get("/healthz"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadOnlyOwnReport() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(httpBasic("alice", "local-alice-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        mvc.perform(get("/api/reports/202")
                .with(httpBasic("alice", "local-alice-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void exportNeedsCsrfAndAuthority() throws Exception {
        // 403 due to missing CSRF, even though Ops holds export authority.
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("ops", "local-ops-password")))
            .andExpect(status().isForbidden());

        // 403 due to missing authority, even though Alice has a CSRF token.
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("alice", "local-alice-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports/export")
                .with(httpBasic("ops", "local-ops-password"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("exported"));
    }

    @Test
    void missingIntegrationRoleNeverCallsPartner() throws Exception {
        when(partnerClient.status()).thenReturn("UP");

        mvc.perform(get("/api/partner/status")
                .with(httpBasic("alice", "local-alice-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/partner/status")
                .with(httpBasic("ops", "local-ops-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("UP"));

        verify(partnerClient, times(1)).status();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"SCOPE_reports:read"}
    )
    void directServiceProxyEnforcesOwnership() {
        assertThrows(AccessDeniedException.class,
            () -> reports.getReport(202L));
    }
}
```

### 7.1. What do these tests guarantee?

- **HTTP filter chain:** anonymous gets 401 in the Basic-auth fixture, while health stays public.
- **Object-level permission:** Alice cannot read ID 202 thanks to the server-side owner policy, even with `SCOPE_reports:read`.
- **CSRF:** POST missing a CSRF token is blocked, and POST with CSRF but missing authority is also blocked.
- **Method security:** annotations enforce on the Spring-injected `ReportService` bean; the test fails if the interceptor does not run.
- **External boundary:** a user lacking `ROLE_INTEGRATION` **never invokes the partner HTTP client**; only Ops can trigger it.
- **Positive path:** Ops with export authority and a CSRF token succeeds on the demo export.

`@MockBean` mocks `PartnerStatusClient`; it does not prove real API HTTPS, JSON schemas, DNS, mTLS, or timeouts. `@WithMockUser` on the service test injects a mock authentication: it does not prove password/JWT verification. That is why real HTTP auth tests in the fixture use `.with(httpBasic(...))` and the application's password encoder.

### 7.2. Running tests

In a Gradle project with the Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

With all files and dependencies set up in a compatible Spring Boot 3.x project, these tests are **expected to pass**. This is not live stdout captured from the learner's system. The tests run inside the JVM with no real partner host needed; neither `idp.example.test` nor real certificates are used.

After upgrading, run the same suite on **both the old and new versions** and compare outcomes. Negative tests should also fail deliberately if `@EnableMethodSecurity` is temporarily removed in a test branch: if negative tests still pass, the fixture is not going through real advice.

### 7.3. Why not only use `@WithMockUser`?

`@WithMockUser` is great for testing **authorization**, yet it does not verify `AuthenticationManager`, session cookies, Bearer JWT signatures/issuers/audiences, or IdP logins. If an entire regression suite uses only mock users, a dangerous decoder/authority-converter change can go unnoticed.

Separate:
- Method-security tests with mock principals to exercise the policy matrix.
- HTTP integration tests with real authentication mechanisms or controlled test tokens/decoders.
- Contract/E2E login/token tests against a test IdP and certificate/key rotation.
- Browser/proxy tests for CORS/SameSite/redirects/CSRF in cookie-authenticated flows.

## 8. Standalone Java 17: policy matrix without Spring

To practice writing **allow and deny** checks, create `UpgradePolicySmoke.java`:

```java
import java.util.Map;
import java.util.Set;

public class UpgradePolicySmoke {

    private static final Map<Long, String> OWNER =
        Map.of(101L, "alice", 202L, "ops");

    static int read(
            String username,
            Set<String> authorities,
            long reportId) {

        if (username == null) return 401;
        if (!authorities.contains("SCOPE_reports:read")) return 403;
        if (!username.equals(OWNER.get(reportId))) return 403;
        return 200;
    }

    static int export(
            String username,
            Set<String> authorities,
            boolean csrfValid) {

        if (username == null) return 401;
        if (!csrfValid) return 403;
        return authorities.contains("SCOPE_reports:export")
            ? 200 : 403;
    }

    public static void main(String[] args) {
        System.out.println("anonymous=" +
            read(null, Set.of(), 101L));
        System.out.println("alice-own=" +
            read("alice", Set.of("SCOPE_reports:read"), 101L));
        System.out.println("alice-other=" +
            read("alice", Set.of("SCOPE_reports:read"), 202L));
        System.out.println("alice-export=" +
            export("alice", Set.of("SCOPE_reports:read"), true));
        System.out.println("ops-export=" +
            export("ops", Set.of("SCOPE_reports:export"), true));
        System.out.println("ops-no-csrf=" +
            export("ops", Set.of("SCOPE_reports:export"), false));
    }
}
```

Compile/run:

```bash
javac UpgradePolicySmoke.java
java UpgradePolicySmoke
```

**Exact stdout:**

```text
anonymous=401
alice-own=200
alice-other=403
alice-export=403
ops-export=200
ops-no-csrf=403
```

**Limitations:** This is only a pure-Java policy matrix without `SecurityFilterChain`, `AuthenticationManager`, CSRF token repository, or real HTTP. It **does not** replace the MockMvc suite in Section 7; its purpose is illustrating the negative cases that must continue to be tested after upgrading.

## 9. Verifying JWT Resource Server after an upgrade

An API receiving Bearer JWTs must both validate tokens **and** enforce permissions. For Resource Servers, minimal regression checks include:

1. **Signature and algorithms:** tokens signed by trusted keys, disallowing unapproved `alg` values; proper JWKS URL/key rotation handling.
2. **Issuer:** `iss` matches the expected issuer; never blindly trust an unknown issuer just because it points to a public JWKS.
3. **Audience:** `aud` must contain the agreed API audience. Tokens issued for a frontend or another API must not be accepted here.
4. **Timestamps:** `exp` expiration, `nbf` not-before, and clock skew per validator; test expired and not-yet-valid JWTs.
5. **Token type:** never accept an ID Token as an access token merely because its signature and subject are valid.
6. **Authorities:** `scope` or `scp` defaults to `SCOPE_xxx`; custom role/permission claims must go through a controlled converter.
7. **Object/tenant:** a token holding `reports:read` must still be denied when requesting another tenant's report.
8. **401/403:** invalid tokens must return 401; valid tokens lacking permissions must return 403 per contract.
9. **Key rollover:** JWKS metadata/caching/algorithms and old/new keys overlap cleanly without disabling signature validation.
10. **Opaque tokens:** if using introspection, test the endpoint, client credentials, `active`, TTL/cache, and permission mapping separately; JWT converters do not run on the opaque path.

Method policy example:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports:read') and " +
    "@ownershipPolicy.isOwner(#p0, authentication.name)"
)
```

If Resource Server's `Authentication` derives its username from `sub`, while the ownership DB keys by a different internal user ID, ensure explicit identity mapping. Never treat mutable display emails/usernames as immutable owner keys when the IdP allows email changes or multi-tenant collisions.

**Test with the right suite:** `SecurityMockMvcRequestPostProcessors.jwt()` is convenient for HTTP authorization tests yet creates a mock `Authentication` and can **bypass the real JWT decoder/validator/converter**. Add decoder unit tests with tokens signed by test keys, or E2E tests against a test IdP. Never claim JWT validation passed solely because `.with(jwt())` returned 200.

## 10. Verifying OAuth2/OIDC, SAML2, and other identity integrations

### 10.1. OAuth2 Client / OIDC login

Verify end to end:

- `authorization-uri`, `token-uri`, `jwk-set-uri`, discovery metadata, client ID, client authentication method, and client secret rotation.
- Redirect URI **exact match** with IdP registration, including scheme/host/port/path behind reverse proxies.
- `state` binding authorization requests and callbacks against CSRF; **never skip** state checks when logins fail.
- PKCE verifier/challenge where required by flow/client; typically required or strongly recommended for public clients per profile.
- OIDC `nonce` when using ID Tokens; `iss`, `aud`, `exp`, signature, and nonce are all verified.
- Scopes/claims and how they map to `GrantedAuthority` on `OAuth2AuthenticationToken`/`OidcUser` per app logic.
- Sessions, `SameSite` cookies, and `authorization_request_not_found` when callbacks arrive without cookies.
- Refresh token handling/revocation/log redaction when integrations call downstream services with delegated tokens.

Never confuse **browser OAuth2 login** with **JWT Resource Server validating Bearer tokens**. They use different filter chains and session policies.

### 10.2. SAML2 Service Provider

If using SAML2:

- IdP/SP entityIDs, Assertion Consumer Service URLs, SSO/SLO endpoints, bindings, and public URLs behind proxies.
- SAML Response/assertion signatures and certificate verification (IdP signing certs), including multi-key rotation.
- SP signing credentials when signed AuthnRequest/LogoutRequest are required; decryption credentials if assertions are encrypted.
- `InResponseTo`, `Destination`, `Audience`, time conditions, `NameID`, `SessionIndex`, and correlation.
- HTTP-POST callbacks/SLO with browser `SameSite` cookie policies; **never disable signature/correlation checks** to fix errors.
- Multi-node: session/correlation data uses a shared store and compatible serializer.

Dependency upgrades can alter OpenSAML, metadata parsers, XML security defaults, or supported certificate algorithms. Test both valid logins and responses with bad signatures, issuers, or destinations rather than happy paths alone.

### 10.3. LDAP / directory integration

If the app authenticates against LDAP/AD:

- Provider URL/TLS/StartTLS, truststores, certificates, and bind service accounts.
- User DN patterns, filter escaping, group-to-role mapping, case sensitivity, and nested groups.
- Disabled/locked/expired-password accounts; failure semantics match policy.
- Never log passwords or bind credentials. Escape user/tenant inputs properly in LDAP filters to prevent injection.
- When the directory is unavailable, never fail open to allow arbitrary users.

### 10.4. Downstream APIs / external partners

| Contract | Minimum check | If changed |
| --- | --- | --- |
| DNS/URL | Correct host/path/port/scheme, redirects | Wrong endpoint or downgrade to insecure HTTP |
| TLS/mTLS | Trusted CA, hostname verification, cert/key rotation | `SSLHandshakeException`, client rejected |
| Authentication | Service tokens, client credentials, mTLS, vault-managed API keys | 401/403 from partner |
| OAuth2 audience/scope | Token matches target resource and outbound permissions | Valid token rejected with 403 by partner |
| Headers | `Content-Type`, `Accept`, correlation ID, idempotency key | Partner rejects or misparses request |
| HTTP statuses | 200/201/204, 400/401/403, 409/429, 5xx | Wrong retries, duplicate writes, data loss |
| JSON/XML schemas | Required/optional fields, enums, dates/timezones, nullability | Deserialization failure or silent data corruption |
| Timeouts | Connect/read/request timeouts, cancellation | Hung threads, pool exhaustion |
| Retries | Retry only contract-allowed calls, backoff/jitter, rate limits | Duplicate mutating POSTs |
| Circuit breakers | Shed load when partner is unhealthy, policy-aligned fallbacks | Fail-open or cascading failures |
| Telemetry | Trace/correlation IDs, latency, error rates | Cannot separate network from auth failures |
| Redaction | Never log Authorization/Cookie/secrets/PII | Leaked tokens or user data |

**Never forward browser session cookies or user access tokens straight to partners** unless an explicit token-delegation/on-behalf-of design enforces target audience and scopes. Outbound APIs should use dedicated credentials with managed secrets and clear rotation lifecycles.

## 11. Contract tests for external integrations independent of production

Three complementary testing layers exist:

1. **Security boundary tests with mock beans:** as in Section 7, confirming unauthorized callers never invoke the client and partner returns `"UP"` only for Ops. Fast, deterministic, CI-friendly.
2. **HTTP client contract tests with a local fake server:** verify methods/paths/headers, bodies/schemas, timeouts, 429/5xx, redirects, and retries/idempotency using WireMock, MockWebServer, or JDK `HttpServer` in tests—with zero calls to production partners.
3. **Staging/partner sandbox E2E:** verify DNS, TLS chains/mTLS, service tokens, issuer/audience, real schemas, and rate limits using test accounts, cleanup, and approved network/secret controls.

For example, `HttpPartnerStatusClient.status()` currently rejects non-200 responses; in a sandbox, test distinguishing 401 credential failures, 403 scope denials, 429 rate limits, and 503 outages. Never code infinite retries or mask a 401 as `"UP"`.

If enabling Java TLS debug logs to investigate handshakes, do so only in isolated environments because traces are verbose and sensitive. Never paste private keys or client secrets into issue trackers.

## 12. Separating endpoint, method security, and integration failures

A regression pipeline can be layered as follows:

| Layer | Tooling | What it verifies | What it does NOT prove alone |
| --- | --- | --- | --- |
| Compile/static | Gradle, javac, dependency checks | Java/Jakarta imports, API presence | Correct access policy |
| Unit policy | JUnit 5 | Role, owner, tenant logic | Spring AOP/filters execute |
| Method integration | `@SpringBootTest`, `@WithMockUser` | Proxies/interceptors and `@PreAuthorize` | Real tokens/cookies/IdP |
| HTTP integration | MockMvc + Spring Security | 401/403/200/CSRF/routing | Reverse proxy/browser `SameSite` |
| JWT decoder tests | Test keys/JWKS | `iss`/`aud`/expiry/signature/converter | Production IdP rotation |
| External client contract | Local fake service | Headers/body/status/timeouts/retries | Real partner TLS/network |
| Browser E2E | Browser + staging ingress | Cookies, `SameSite`, CORS, redirects, SSO | Prod topology failure modes |
| Multi-node | Two pods + shared session store | Cookie/session continuity, logout, serialization | Every Redis failover mode |
| Canary/monitoring | Runtime metrics and rollback | Security/error/latency drift outside staging | Replaces negative policy tests |

**Note on test false positives:** `.with(user("alice"))` does not prove Alice can actually log in; `.with(jwt())` does not prove token signatures are verified; mocking a partner does not prove TLS. State clearly **which layer was verified** in QA reports.

### 12.1. Mandatory negative cases

- Anonymous hitting private endpoints; users lacking roles; users with roles hitting wrong owner/tenant records.
- Form POSTs with missing/invalid CSRF; CORS preflight from untrusted origins.
- Expired JWTs, wrong issuer/audience, wrong algorithm/key, missing scopes.
- SAML Responses with bad signatures/destinations; OAuth2 state mismatches / bad PKCE verifiers.
- Endpoints without specific matchers, trailing slashes/encoded paths, GET vs POST differences.
- Calls from another bean and self-invocation paths to detect proxy bypasses.
- Partners returning 401/403/429/5xx, TLS handshake failures, malformed JSON, timeouts, and retries.
- Expired sessions, stale post-logout cookies, node switches with shared Redis stores.
- Cross-site browser callback POSTs under valid/invalid `SameSite` settings.
- Multiple tenants sharing identical usernames across distinct resources.

### 12.2. Inspecting security responses beyond the body

Tests should also assert where required by contract:

- `Cache-Control`/`Pragma` preventing caching of sensitive payloads.
- No stack traces, tokens, or sensitive JWT claims in error JSON.
- CORS origins/credentials matching only the allowlist.
- `WWW-Authenticate`/redirects on 401 matching the mechanism.
- Session cookie `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, and expiry attributes.
- 403 responses not leaking existence/details of another tenant's objects.
- Actuator/debug/docs endpoints protected per baseline, never accidentally `permitAll`.
- Downstream calls triggered only **after** authorization guards, with zero side effects when denied.

## 13. Specific issues when updating Java, Servlets, and proxies

### 13.1. Jakarta namespace

When upgrading Boot 2.x → 3.x:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Custom libraries/filters still importing `javax.servlet.*` can fail to compile or malfunction on modern Servlet containers. This is a **namespace** change, not a reason to remove filter security; upgrade dependencies to Jakarta-compatible releases.

### 13.2. Reverse proxies and forwarded headers

After an upgrade, the public URL may stay `https://app.example.test` while the app sees `http://service:8080`. Consequences include redirects to internal HTTP, `Secure` cookies failing to return, OAuth2 `redirect_uri` mismatches, or SAML `Destination` mismatches.

Spring Boot offers:

```yaml
server:
  forward-headers-strategy: framework
```

Enable this only when a **trusted reverse proxy** strips client-forged forwarded headers from the internet and re-emits valid ones. Never blindly trust `X-Forwarded-Host`/`X-Forwarded-Proto` just to fix a callback; that opens host-injection and open-redirect risks.

### 13.3. Sessions and explicit save

Spring Security 6 defaults to explicit saving of `SecurityContext`. If a custom login handler calls only:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

and returns a response, the next request may be anonymous. Use `SecurityContextRepository.saveContext(...)` properly inside the auth flow along with session fixation strategies and response-commit ordering. Standard `formLogin`/`oauth2Login` filters handle this already; avoid writing custom login code unless necessary.

### 13.4. Session cookies and multiple nodes

For form/OIDC/SAML logins, browsers must return correlation/session cookies properly to callbacks. Verify `Secure`, `SameSite` `Lax`/`None` for cross-site POSTs, host-only `Domain`, `Path`, `JSESSIONID`/`SESSION`, and Redis/Spring Session namespaces. If login drops only when switching pods, suspect session stores/serializers rather than resetting passwords.

Never combine changing cookie names, Redis namespaces, serializers, and security DSLs in one unplanned rollout; doing so complicates root-cause analysis and can log out all active users at once.

## 14. Controlled upgrade and rollback workflow

### 14.1. Before upgrading

1. Lock down the dependency/BOM/JDK/Jakarta map and snapshot security chain configs plus IdP/partner endpoints.
2. Collect the Section 3 baseline matrix, especially **negative tests** and tenant/owner policies.
3. Confirm public/health/admin endpoints, callbacks, CORS, CSRF, logout, and cookie/session policies.
4. Record certificates/JWKS, expiries, truststores, mTLS, client credentials, and rotation plans.
5. Verify external API schemas/versions, rate limits/timeouts, and sandbox test data.
6. Capture baseline metrics for `401`, `403`, login success/error, token validation, latency, Redis failures, and partner 4xx/5xx.

### 14.2. During the upgrade

1. Update dependencies via Spring Boot's BOM and matching migration guides without mixing Spring Framework/Servlet API versions manually.
2. Migrate `SecurityFilterChain` config, method security, Jakarta imports, and principal/authority mappers systematically.
3. Run unit + method + MockMvc + JWT decoder tests; verify **negative cases**.
4. Test external services against mocks/sandboxes, TLS/mTLS, issuer/audience, callback state/nonce/SAML signatures.
5. Test browser flows through proxies/ingress and multi-node sessions.
6. Compare outcomes against baseline, documenting **approved** changes and regressions to fix.

### 14.3. Canary and production

- Roll out to a slice of traffic or test accounts first, keeping per-version/pod metrics comparable.
- Alert on spikes in `401/403`, SSO callback errors, CSRF denials, JVM exceptions, Redis misses, TLS handshakes, and partner timeout/retry rates.
- Propagate correlation IDs across browser → gateway → Spring → partner, **never logging raw Cookies, Authorization headers, assertions, refresh tokens, or private keys**.
- Run canary checks on both positive and negative routes, not only `/health`.
- On a security regression (unintended privilege widening), **roll back or disable the route per runbook**; never keep a broken release because happy paths work.
- If session serializer, cookie name, or schema changes prevent rolled-back binaries from reading new data, plan dual-read/migration strategies or controlled re-logins. Never assume binary rollback alone restores state.
- Distinguish expected 401/403 shifts from approved policy changes against real bugs using baselines and diagnostics—never loosen authorization to quiet metrics.

### 14.4. Go/No-Go criteria

**Go** when:

- No public/private endpoint access shifted outside approved decisions.
- Every user × role × scope × tenant × action test matches expectations.
- JWT/SAML/OIDC validation still blocks invalid tokens/messages.
- CSRF/CORS/cookies/browser callbacks remain intact.
- External sandbox contracts, TLS, auth, timeouts, errors, and retries pass.
- Multi-node session and canary metrics are acceptable.
- Rollback and incident response plans are executable.

**No-Go** if any unintended `permitAll` appears, `@PreAuthorize` is bypassed, wrong-audience tokens are accepted, CSRF was disabled without approval, cross-tenant data leaks, outbound clients send credentials to the wrong target, or key/cert verification was skipped.

## 15. Post-upgrade quick diagnostic table

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Previously protected endpoint now returns 200 anonymously | Wrong matcher, chain order, or `permitAll` | Anonymous HTTP test and inspect effective `SecurityFilterChain` |
| Previously public endpoint now returns 401 | Broad rule shadows `permitAll` or API chain matched unexpectedly | Inspect `securityMatcher` and rule order |
| Method with `@PreAuthorize` runs for unauthorized user | Missing `@EnableMethodSecurity`, proxy bypass, or self-invocation | Call Spring-managed service bean in a negative test |
| HTTP GET works, POST returns 403 | CSRF or method-specific permission/matcher | Test POST with/without CSRF and scopes |
| JWT has valid scope yet API returns 403 | Converter dropped `SCOPE_`, `scp`/`scope` claim, or principal mapping | Inspect authorities after decoder and policy expression |
| Token with wrong audience is accepted | Audience validator not enabled for this API | Negative JWT test with a different `aud` |
| API returns 401 even though browser logged into web | API chain is stateless Bearer-only | Check `securityMatcher` and `Authorization` header |
| Next request is anonymous right after login | Custom auth skipped `saveContext` or cookie/session lost | Two-request MockMvc test; DevTools `Set-Cookie`/`Cookie` |
| OAuth2 callback state mismatch | Cookie not returned or different auth-request repo | `SameSite`/redirect URI/Redis correlation |
| SAML login fails after upgrade | Signing cert/binding/parser/metadata changed | Redacted IdP/SP logs and signature validation |
| Browser CORS fails while curl succeeds | `OPTIONS` preflight/CORS credentials/allowed origin | Browser network tab + MockMvc preflight |
| Browser uses HTTPS yet app redirects to HTTP | Wrong proxy forwarded headers | Check public scheme and proxy trust |
| Partner returns 401/403 | Wrong service token/cert/scope/audience/client auth | Sandbox contract test and partner logs |
| Partner slow / timing out | Uncontrolled connect/read timeouts or retries | Fake server delay/429 and tracing |
| API returns 500 after JSON change | Incompatible schema/nulls/enums/serialization | Request/response contract tests |
| Login fails on only one pod | Mismatched session namespace/serializer/keys/config | Compare effective config/versions across pods |
| MockMvc passes yet production fails | Browser/TLS/IdP/Redis/multi-node untested | E2E/canary tests; verify test scope |
| `.with(jwt())` passes despite broken decoder | Bypassed real JWT decoder | Test tokens signed with test keys/IdP |
| Another app's `ADMIN` role works here | Trust/claim mapper accepts roles from wrong audience | Restrict issuer/audience and claim paths |

## 16. Handoff checklist for Ops and QA

- [ ] Recorded old/new versions: Java, Spring Boot, Spring Security, Servlet container, Jackson, Redis, OpenSAML, OAuth2/JWT libraries, and external HTTP clients.
- [ ] Verified `SecurityFilterChain` and `securityMatcher`/`requestMatchers` order, including unknown-endpoint deny-by-default.
- [ ] Tested anonymous, missing authority, valid authority, wrong owner/tenant, and right owner/tenant for every sensitive endpoint.
- [ ] Tested HTTP methods GET/POST/PUT/PATCH/DELETE, CSRF, CORS `OPTIONS`, and error contracts 401/403/302/404/405.
- [ ] Enabled `@EnableMethodSecurity` and verified `@PreAuthorize` and active annotations via Spring proxies without self-invocation.
- [ ] Verified `hasRole`/`hasAuthority` prefixes, JWT `SCOPE_`, custom principals/claims, and tenant-bound permissions.
- [ ] For JWTs, tested signatures, issuer, audience, expiry, key rollover, and opaque introspection if used.
- [ ] For OAuth2/OIDC, tested redirect URIs, state, PKCE/nonce, cookie/session correlation, and IdP secret rotation.
- [ ] For SAML2, tested ACS/SLO metadata, signatures, certificates, session correlation, and bindings.
- [ ] For LDAP/directories, tested TLS/bind/filters/group mapping and error handling when directory is unavailable.
- [ ] For external partners, tested TLS/mTLS, credentials, audience/scope, payload schemas, HTTP errors, timeouts, retries, and **no token leaks**.
- [ ] Executed MockMvc, real token/IdP sandbox, proxied browser, and multi-node session tests, documenting each layer's scope limits.
- [ ] Monitored canary metrics for 401/403, CSRF, login callbacks, partner 4xx/5xx, timeouts, Redis, and TLS handshakes per release.
- [ ] Verified rollback compatibility with sessions and schemas, not just redeploying old binaries.
- [ ] Never dropped signatures, CSRF, tenant/object policies, or TLS verification to make the regression suite pass.

**Conclusion:** After upgrading Spring Security Servlet, verify across three distinct yet connected rings: **HTTP endpoints match and authenticate accurately → method security enforces authorities and object-level policies → identity and downstream integrations validate tokens, certificates, requests/responses, and errors properly**. A trustworthy test suite proves both **“the right caller is allowed”** and **“the wrong caller is denied,”** followed by E2E and canary checks covering what MockMvc cannot simulate: browsers, proxies, IdPs, and multi-node infrastructure.
