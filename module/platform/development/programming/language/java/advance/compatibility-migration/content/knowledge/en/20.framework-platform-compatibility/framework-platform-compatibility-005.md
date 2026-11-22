# Upgrading Spring Security and Re-Testing Security Contracts

Upgrading Spring Security is never just swapping a dependency or updating configuration APIs. Spring Security decides which requests require authentication, who may invoke which endpoints, when CSRF tokens are enforced, how sessions are protected, how JWTs are validated, and where filters execute. Unintended shifts in any of those rules can let an application compile and boot cleanly while **accidentally exposing sensitive endpoints**, locking out legitimate users, or skipping data-ownership checks.

In **Java Advance Compatibility Migration**, upgrading Spring Security typically goes alongside upgrading the JDK, Spring Framework, Spring Boot, the Servlet/Jakarta stack, OAuth2/JWT libraries, and custom Spring Security filters. This lesson walks through migrating configuration across major release lines, defining **security contracts** before and after migration, writing negative tests, and deploying with rollback readiness.

## 1. What Is a Security Contract?

A **security contract** is the verifiable set of rules an application guarantees:

- Which endpoints or actions allow anonymous access?
- Are unauthenticated users redirected to login or returned HTTP 401?
- Are authenticated users lacking permissions blocked with HTTP 403 or another API-specific response?
- Which roles, authorities, scopes, and JWT claims authorize each action?
- Which operations require a CSRF token?
- Is the API strictly stateless with bearer tokens, or backed by cookies/sessions?
- Which origins, methods, headers, and credentials does CORS permit?
- How are sessions created, expired, invalidated, and protected?
- Must users access *only their own resources* rather than merely holding a coarse role?

Illustrative contract example:

| Action | Anonymous | Authenticated User | Admin | Other Conditions |
|---|---|---|---|---|
| GET /public/info | Allow | Allow | Allow | Must not leak sensitive data. |
| GET /api/orders/me | 401 | Allow if holding read scope | Per policy | Read only own records. |
| POST /api/orders | 401 | Requires write scope | Per policy | Valid token and input validation. |
| GET /admin/reports | 401 or redirect | 403 | Allow | Restricted to appropriate role/authority. |
| POST /web/account/email | Blocked if not logged in | Requires CSRF token | Requires CSRF token | Web uses cookie-backed session. |

Statuses and endpoints in this table are illustrative. **Real projects must pin explicit policies** because web form logins typically issue 302 redirects while bearer APIs typically return 401.

## 2. Why Compilation Success Is Not Enough

Rewriting an older rule:

```java
http.authorizeRequests()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

into:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").permitAll()
    .anyRequest().authenticated());
```

lets code use the new API, yet silently opens admin paths to every request. Such regressions are severe and completely invisible to the Java compiler.

Subtler regressions include:

- Newer pattern matchers carrying different matching semantics from old matchers.
- Splitting one chain into multiple chains while forgetting a catch-all chain.
- Mapping role `ROLE_ADMIN` mistakenly to authority `ADMIN`.
- Custom authentication filters failing to persist `SecurityContext` as before.
- Accepting JWTs from a wrong issuer because tests only mock tokens.
- Disabling CSRF across the entire web session just because one API is stateless.
- Skipping method security because tests instantiate objects directly via `new`.

Therefore, migration tests must verify not just “who **is** allowed in,” but also “who **must be blocked**.”

## 3. Upgrade Milestones

| Source / Target | Primary Change Focus | Preparation Actions |
|---|---|---|
| Legacy Spring Security 5.x | `WebSecurityConfigurerAdapter`, `authorizeRequests`, and `antMatchers` may still be present. | Read migration guides and establish baseline rules. |
| 5.8 → 6.x | Bean-based configuration, request matcher APIs, Spring Framework 6 / Boot 3 / Jakarta compatibility shifts, Java 17 baseline. | Complete 5.8 preparation steps first, then move to 6. |
| 6.x → 7.x | Legacy DSLs/matchers removed; Lambda DSL and `PathPatternRequestMatcher` become central. | Follow 6.5 preparation guides for 7; align with Boot 4 / Framework 7. |
| Any upgrade | Security fixes, changed defaults, dependencies, and runtimes. | Read patch-specific release notes and re-run security contract tests. |

Do not infer target JDKs or valid configs purely from major version numbers. Spring Boot normally aligns Spring Security modules via its BOM; inspect the actual resolved versions and the compatibility matrix across Boot, Framework, Security, the Servlet container, and the JDK.

### 3.1. Inventory Real Versions

Maven:

```bash
mvn -version
mvn dependency:tree
```

Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security \
  --configuration runtimeClasspath
```

Check `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-test`, OAuth2/JWT modules, Spring Boot/Framework, the application server, and third-party libraries participating in authentication/filter chains. Upgrading only one Security JAR while leaving others behind risks runtime linkage errors.

## 4. Inventory Configuration Before Editing

Search for all occurrences of:
- `WebSecurityConfigurerAdapter`, `SecurityFilterChain`, `HttpSecurity`, `WebSecurityCustomizer`.
- `antMatchers`, `mvcMatchers`, `requestMatchers`, `securityMatcher`, `@Order`.
- `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`.
- `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@EnableMethodSecurity`.
- CSRF, CORS, logout, headers, remember-me, and sessions.
- OAuth2 client, resource server, JWT decoder, and SAML2 if applicable.
- Custom `Filter`, `OncePerRequestFilter`, `SecurityContextRepository`, entry points, and denied handlers.
- Routes across MVC, WebFlux, actuator, WebSocket, static files, and error pages.
- Runtime parameters, reverse proxies, IdPs, and session stores.

Do not overlook policies configured via YAML/properties, annotations, or framework auto-configuration. Some filters register directly with the servlet container outside the Spring Security filter chain.

## 5. Migrating Away from `WebSecurityConfigurerAdapter`

Common legacy configuration:

```java
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig
        extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public/**").permitAll()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
            .and()
            .formLogin();
    }
}
```

This is **illustrative legacy code**, not usable directly in Spring Security 6/7. Define a `SecurityFilterChain` bean instead:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Key points:
- `SecurityFilterChain` declares filters and rules for requests matching that chain.
- `authorizeHttpRequests` uses the newer authorization model.
- Lambda DSL avoids chained `.and()` calls; in Spring Security 7, follow the migration guide's Lambda DSL style.
- `anyRequest().authenticated()` acts as a catch-all rule for remaining paths within the chain.
- Never disable CSRF for cookie-backed web sessions without compelling justification.

Configuration is meaningful only once actual application paths and rules are verified by tests.

## 6. Distinguishing `securityMatcher` from `requestMatchers`

`http.securityMatcher(...)` selects **which requests enter the entire `SecurityFilterChain`**. In contrast, `requestMatchers(...)` inside `authorizeHttpRequests` selects **authorization rules** for requests already inside the chain.

Example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

If this is the only chain, `/admin/reports` does not match `/api/**` and may end up **unprotected by Spring Security**. Add an appropriate fallback chain:

```java
@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
    return http.build();
}
```

These snippets assume matching configuration files and imports. In real apps, the fallback might enforce web/form-login policy, yet unmatched requests must never pass through unprotected.

### 6.1. Filter Chain Ordering

`FilterChainProxy` selects the first chain matching the request in configured order.

```text
Request
  |
  +--> Chain 1 matches /api/**? ---- yes --> bearer/API rules
  |
  +--> Chain 2 matches /admin/**? -- yes --> admin rules
  |
  +--> Catch-all --------------------------> web/deny rules
```

Test all cases:
- Narrow chain match.
- Multi-chain overlap and which chain wins priority.
- Requests hitting the catch-all chain.
- Login/logout, static resources, and `/error`.
- Dispatcher types, path encoding, and trailing slashes.
- Management/actuator endpoints on separate contexts.

Never use `anyRequest().permitAll()` as a catch-all “fix” for deployment errors.

## 7. Request Matchers When Upgrading to Spring Security 7

Spring Security 6 migrated many teams from `antMatchers`/`mvcMatchers` to `requestMatchers`. Spring Security 7 introduces further changes:
- `AntPathRequestMatcher` and `MvcRequestMatcher` are removed per migration guides.
- `PathPatternRequestMatcher` is used by default.
- URIs in the Java DSL specify paths **relative to the servlet context without the context root**.
- Custom matchers outside the DSL require individual review.

For servlet paths, verify actual runtime routing:

```text
Application context path: /shop
Servlet mapping: /api/*
Request URL: /shop/api/orders/42
Security rule: /api/orders/**
```

Do not include the `/shop` context root in matchers when the contract specifies application-relative paths; always verify how the runtime and matcher version parse paths. With multiple servlets, JSPs, encoded legacy URLs, and custom matchers, run integration tests on a real servlet container.

Paths to test include `/admin`, `/admin/`, `/admin/users`, URLs with path variables, encoded characters, and different HTTP methods. Mismatched matchers can yield wrong 404/403 responses or, worse, leave a route exposed.

## 8. Roles and Authorities Are Not Identical

By default convention:

```java
.hasRole("ADMIN")
```

typically checks authority `ROLE_ADMIN`. Whereas:

```java
.hasAuthority("ADMIN")
```

checks the literal string `ADMIN`.

With JWT resource servers, scopes usually become authorities prefixed with `SCOPE_`:

```text
JWT scope: orders.read orders.write

Spring authorities:
SCOPE_orders.read
SCOPE_orders.write
```

Policy:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

During migration, test real JWT claims and how `JwtAuthenticationConverter` maps them. If an IdP moves from `scope` to a custom claim or alters authority names, controllers still boot while users receive too few or too many permissions.

## 9. Distinguishing 401, 403, and Redirects

**Authentication** answers who the identity is. **Authorization** answers what that identity may do.

For bearer APIs:
- Missing or invalid token: usually HTTP 401.
- Valid token lacking permission: usually HTTP 403.
- Authorized: request reaches business logic, yet may still be blocked by ownership/tenant checks.

For web form login:
- Unauthenticated: usually 302 redirect to login page.
- Authenticated lacking role: usually 403.
- Expired session: returns to login flow per config.

Do not force one HTTP status across every mechanism. Align `AuthenticationEntryPoint`, `AccessDeniedHandler`, response bodies, `WWW-Authenticate` headers, and redirect URLs with your API contract.

## 10. CSRF and the Limits of “Stateless” Advice

CSRF primarily concerns requests where browsers automatically send cookies/session credentials. An authenticated POST can still require a CSRF token.

Web session example:

```text
POST /web/account/email
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...
```

If a required CSRF token is missing, HTTP 403 is usually **the expected result**.

For APIs authenticating strictly via bearer tokens in the `Authorization` header without cookies or browser-managed credentials, you may disable CSRF only on that **isolated API chain**:

```java
http
    .securityMatcher("/api/**")
    .csrf(csrf -> csrf.disable())
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
```

However, calling an endpoint “REST” does not automatically justify disabling CSRF. If cookie auth, browser HTTP Basic, or mixed credentials exist, evaluate CSRF separately. Never disable CSRF app-wide just to make a unit test pass.

## 11. CORS Is Browser Policy, Not a Substitute for Authentication

Browser `OPTIONS` preflight requests normally omit bearer tokens or session cookies sent on actual requests. If CORS executes after authentication without proper allowance, browser clients are blocked.

Valid origin example:

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(
        java.util.List.of("https://app.example.test"));
    config.setAllowedMethods(
        java.util.List.of("GET", "POST", "PUT"));
    config.setAllowedHeaders(
        java.util.List.of("Authorization", "Content-Type"));
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

On the associated chain:

```java
http.cors(Customizer.withDefaults());
```

Import classes from Spring Web's CORS API. The domain above is illustrative, not a production host. CORS never bypasses authentication/authorization on actual requests. Test preflight from an allowed origin, a disallowed origin, and actual POST requests carrying valid tokens.

## 12. Sessions and `SecurityContext` Persistence

Changes in how recent Spring Security releases read/persist `SecurityContext` can break custom login flows:
- User authenticates successfully on the first request.
- Custom code populates `SecurityContextHolder`.
- The second request fails to see the logged-in session.

A frequent cause is failing to save `SecurityContext` explicitly through `SecurityContextRepository` as required in newer setups.

When session persistence is needed:
1. Identify the active `SecurityContextRepository`.
2. Identify which filter creates, reads, and saves the context.
3. Verify when context saving occurs after custom authentication.
4. Test **two consecutive requests**, not just the login response itself.
5. Test session fixation protection, logout, and session invalidation.

For truly stateless bearer APIs, every request must validate its token rather than relying on an accidentally persisted session.

## 13. JWT Resource Server: Test the Real Decoder

Resource server configuration:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));
    return http.build();
}
```

This example relies on `HttpMethod`, `SessionCreationPolicy`, and matching bean imports. To run, the app must also configure a `JwtDecoder`, `issuer-uri`, `jwk-set-uri`, or equivalent provider.

A thorough test suite covers:
- Missing, blank, or malformed tokens.
- Invalid signatures/algorithms or untrusted keys.
- Expired or not-yet-valid tokens.
- Wrong issuer/audience claims.
- Key rotation and JWKS fetch errors.
- Valid token lacking required scopes.
- Valid token holding required scopes.
- Tokens belonging to another tenant/issuer.
- Principal and authority mapping matching contract.

Never treat `jwt()` in `spring-security-test` as cryptographic signature verification: it injects mock authentication solely to test authorization rules. Keep integration tests passing signed JWTs through the real decoder.

## 14. OAuth2 Login, OIDC, and SAML

When using `oauth2Login()` or SAML2, verify:
- Client registrations, redirect URIs, grant types, and PKCE.
- OAuth state, OIDC nonce, code exchange, and token validation.
- UserInfo, authority/claim mapping, and local account linking.
- Post-login sessions, local logout, and upstream IdP logout if required.
- Cookie attributes, proxy headers, and HTTPS redirects.
- Behavior during IdP timeouts, JWKS rotations, or malformed responses.

Never embed real production client secrets or access tokens in tests or logs. Use a test IdP or controlled staging IdP, and confirm unauthenticated calls cannot reach protected resources.

## 15. Method Security and Proxy Behavior

Legacy code may use:

```java
@EnableGlobalMethodSecurity(prePostEnabled = true)
```

Modern configuration:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Example:

```java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports.export')")
    public byte[] export(String reportId) {
        return ("report:" + reportId)
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

Verify:
- Callers with `reports.export` succeed.
- Callers with only `reports.read` are denied.
- Calls enter through the Spring bean/proxy; internal self-calls via `this` bypass AOP advice.
- Expressions referencing parameter names compile with `-parameters` if needed.
- `PermissionEvaluator`, role hierarchies, and post-authorization continue working.
- Scheduled jobs/listeners invoking the service align with authorization policy.

Never instantiate `new ReportService()` inside tests expecting security annotations to fire, because Spring AOP proxies will not wrap it.

## 16. `PasswordEncoder` and Legacy Password Hashes

During migration check:
- The actual registered `PasswordEncoder` bean.
- Existing stored hash structures and algorithm prefixes.
- Legacy accounts still holding older hashes.
- Progressive rehashing policy upon login.
- Password-reset tokens, account lockout, and rate limits.

Delegating encoder example:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories
        .createDelegatingPasswordEncoder();
}
```

`DelegatingPasswordEncoder` typically relies on prefixes like `{bcrypt}`. Never enable `NoOpPasswordEncoder` or bypass password verification to “restore” login in production. If legacy hashes require migration, plan an explicit upgrade path and test both legacy and new accounts.

## 17. Custom Filters and Execution Order

Custom filters often handle tokens, API keys, tenants, auditing, request signatures, correlation IDs, or custom authentication.

After upgrading verify:
- Whether `Filter` classes import `jakarta.servlet.*` or `javax.servlet.*` to match the runtime.
- Whether the filter is a servlet container auto-registered bean or explicitly wired into `SecurityFilterChain`.
- Whether it accidentally registers **twice**.
- Filter ordering relative to authentication, `SecurityContext`, and authorization filters.
- Whether the filter leaks credentials in logs or leaves `ThreadLocal` state uncleaned.

API illustration:

```java
http.addFilterBefore(
    customAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class);
```

This placement is not a universal prescription for every custom filter. Audit filters may belong after authentication; custom token filters must follow `SecurityContext` lifecycle rules cleanly. Test against the real runtime filter chain rather than eyeballing source config.

## 18. HTTP Security Headers, HTTPS, and Reverse Proxies

Framework/container updates can affect:
- HSTS.
- `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`.
- `Cache-Control` for sensitive responses.
- Cookie `Secure`/`HttpOnly`/`SameSite` flags.
- Trusted forwarded headers, HTTP/HTTPS scheme detection, and HTTPS redirects.
- Login redirects behind ingress controllers or reverse proxies.

Do not rely solely on `MockMvc` when production sits behind an API gateway or reverse proxy. Run contract tests through the ingress to verify final response headers and confirm no HTTP↔HTTPS redirect loops occur.

## 19. Method-Level Rules vs Resource Ownership

A rule such as:

```java
.hasAuthority("SCOPE_orders.read")
```

only checks a broad permission. It **does not** establish whether User A may read User B's order. If a service fetches orders by ID without checking owner/tenant ownership, the endpoint remains vulnerable to IDOR even with Spring Security enabled.

Test contracts must cover:
1. User A reads Order A: allowed.
2. User A reads Order B: denied (403 or 404 per contract).
3. Unauthenticated user: sees zero records.
4. Admin or operator: broader access granted only where policy explicitly states.
5. Token with altered tenant claim: never crosses tenant data boundaries.

Preserve these checks across migration even if HTTP routes and security annotations stay identical.

## 20. `MockMvc` Integration Tests for Web Security

On a Spring Boot 3-era test stack, test the MVC security filter chain with:

```java
@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityContractTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public/info"))
            .andExpect(status().isOk());
    }

    @Test
    void normalUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin/reports")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin/reports")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isOk());
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/web/account/email")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/web/account/email")
                .with(user("reader").roles("USER"))
                .with(csrf()))
            .andExpect(status().is2xxSuccessful());
    }
}
```

Required static imports (depending on exact version):
- `MockMvcRequestBuilders.get` and `post`.
- `MockMvcResultMatchers.status`.
- `SecurityMockMvcRequestPostProcessors.user` and `csrf`.

Endpoints and status codes above are hypothetical and must exist in the real application. If a controller returns 302/204/201 on success, assert the real contract status. **Spring Boot 4 organizes certain test modules/packages differently from Boot 3**, so consult your version's guide for exact annotations and imports instead of copying Boot 3 test code blindly.

## 21. Testing JWT Authorization with Mock Principals

Using `spring-security-test`:

```java
@Test
void orderReadAllowedWithScope() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void orderReadDeniedWithOnlyWriteScope() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write"))))
        .andExpect(status().isForbidden());
}
```

Import `SecurityMockMvcRequestPostProcessors.jwt`, `SimpleGrantedAuthority`, and `MockMvc` static helpers. This verifies authorization against a prebuilt principal—it does not test signatures, issuers, audiences, expiry, or JWKS. Cover those at the JWT decoder/integration layer.

Beyond happy paths, test authority casing, scope prefixes, cross-tenant tokens, missing permissions, and non-leaking error bodies.

## 22. Testing Method Security

```java
@SpringBootTest
class ReportMethodSecurityTest {
    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "reports.read")
    void readerCannotExport() {
        assertThrows(AccessDeniedException.class,
            () -> reportService.export("R-42"));
    }

    @Test
    @WithMockUser(authorities = "reports.export")
    void exporterCanExport() {
        reportService.export("R-42");
    }
}
```

This abbreviated example requires JUnit/Spring imports and the `ReportService` bean shown earlier. It only proves protection when `@EnableMethodSecurity` is active and tests obtain the proxied bean from the Spring context. Add tests for self-invocation, internal service calls, and parameter-name expressions if used.

## 23. Testing Sessions, CSRF, and CORS Across Multi-Request Flows

A single isolated request cannot validate session policy. Test sequences:
1. Valid POST login.
2. Extract session cookie from the response.
3. Subsequent request carrying that session to a protected resource.
4. Logout, followed by retrying with the old session cookie.
5. Verify expired or invalidated sessions are rejected.
6. Verify privilege changes/session fixation behavior matches contract.

For CSRF:
- POST without token is rejected where policy requires it.
- POST with valid token proceeds to business logic.
- Invalid or cross-session tokens are rejected.
- Stateless bearer APIs are tested independently without weakening web routes.

For CORS:
- Valid-origin `OPTIONS` preflight receives exact expected headers.
- Disallowed origins are rejected.
- Actual requests still undergo full authentication and authorization.
- Never conflate CORS origin allowlists with authorization policies.

## 24. Reactive WebFlux Uses a Distinct Stack from Servlet

If the application uses WebFlux, do not apply Servlet configuration verbatim:

| Spring MVC / Servlet | Spring WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |
| Servlet Filter | `WebFilter` |

Example:

```java
@Bean
SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Follow the proper Servlet or Reactive migration guide. Accessing `SecurityContext`, `WebFilter` ordering, session handling, and test APIs differ markedly.

## 25. Diagnosing Common Errors

| Symptom | Possible Cause | Investigation Approach |
|---|---|---|
| Cannot find `WebSecurityConfigurerAdapter` | Legacy config base class removed. | Switch to `SecurityFilterChain` beans. |
| Cannot find `antMatchers` | Newer matcher API generation. | Use supported matchers and verify path semantics. |
| `NoClassDefFoundError: javax/servlet/...` | Mixing legacy Servlet namespace with Jakarta runtime. | Audit dependency graph/framework/container. |
| Admin endpoint is left exposed | Unmatched chain or overly broad fallback. | Check `securityMatcher`, `@Order`, and negative tests. |
| Valid user gets 403 | Wrong role/authority mapping or missing permission. | Check authorities and matcher rules. |
| Bearer API returns 302 login redirect | Request fell into form-login chain. | Separate chains and entry points. |
| Web POST gets 403 | Missing or invalid CSRF token. | Verify token flow before relaxing rules. |
| Preflight OPTIONS fails with 401 | CORS blocked by authentication filter. | Verify CORS configuration inside security chain. |
| Post-login follow-up request returns 401 | `SecurityContext` not saved properly. | Inspect custom auth flow/repository/session. |
| Mock JWT tests pass, production returns 401 | `JwtDecoder`/JWKS/issuer untested. | Run integration tests with signed tokens. |
| `@PreAuthorize` ignored | Method security disabled or proxy bypassed. | Invoke through the real Spring bean. |
| Custom filter executes twice | Registered both as container bean and in Security chain. | Check filter registrations and order. |
| Unexpected 401/403 on `/error` | `ERROR`/`FORWARD` dispatches hit different chain rules. | Test error flows and dispatcher types. |

Never “fix” errors by changing a rule to `permitAll` before identifying root cause.

## 26. Wave-Based Migration Plan

### Wave 0 — Baseline

Record JDK, Spring Boot/Framework/Security, dependency versions, filter chain setups, and endpoint inventories. Archive security contract tests and baseline auth-failure metrics before upgrading.

### Wave 1 — Bridge Release

If moving from 5.x to 6, follow 5.8 preparation guides; if moving from 6.x to 7, follow 6.5 preparation guides. Migrate deprecated APIs, adopt Lambda DSL, extract `SecurityFilterChain` beans, and move to recommended request matchers.

### Wave 2 — Authorization and Matching

Audit all URL/method rules, `securityMatcher`, `@Order`, catch-all chains, role prefixes, and scope mappings. Execute positive/negative tests and encoded-path edge cases.

### Wave 3 — Authentication Integrations

Test password encoders, custom providers, OAuth2/OIDC, JWT signature/issuer/audience/JWKS validation, and SAML if used. Test session context persistence and logout.

### Wave 4 — Browser, Method, and Data Security

Test CSRF, CORS, security headers, cookies, method security, and ownership/tenant IDOR rules. Execute against a representative servlet container/gateway/IdP, not mocks alone.

### Wave 5 — Controlled Rollout

Roll out via canary or blue-green deployment. Monitor login failures, 401/403/302 rates, CSRF rejections, CORS preflights, JWT validation failures, and access denials. Maintain rollback readiness across both application config and session/data state.

## 27. Security Contract Test Matrix to Retain

| Case | Credentials | Privileges | Expected Result |
|---|---|---|---|
| Public GET | None | — | Allowed. |
| Restricted GET | None | — | 401 or contract-defined redirect. |
| Admin GET | Regular user | `ROLE_USER` | 403. |
| Admin GET | Admin | `ROLE_ADMIN` | Allowed. |
| User A reads User B's resource | Token A | Broad read privilege | Denied per ownership policy. |
| Web POST without CSRF | Session cookie | Valid user | Denied. |
| Web POST with CSRF | Cookie + token | Valid user | Reaches business logic. |
| API GET without JWT | None | — | 401. |
| API GET bad-issuer JWT | Untrusted JWT | — | 401. |
| API GET valid JWT missing scope | Valid JWT | Lacks read scope | 403. |
| API GET valid JWT with scope | Valid JWT | Holds read scope | Allowed if resource valid. |
| Allowed-origin OPTIONS | Preflight | — | Accurate CORS headers returned. |
| Unknown-origin OPTIONS | Preflight | — | Origin denied access. |
| Post-logout request | Stale cookie | — | No authentication retained. |

Version expected outcomes alongside API contracts. If a product team deliberately switches an endpoint from 302 redirect to JSON 401, document and review that decision—never quietly update snapshots to rubber-stamp regressions.

## 28. Post-Migration Security: Negative Tests Before Positive Comfort

Questions to verify:
- Can any URI bypass all `SecurityFilterChain` beans?
- Were HTTP methods like `PATCH`/`DELETE`/`OPTIONS` omitted from rules?
- Are bypasses possible via URL encoding, trailing slashes, servlet mappings, or proxy prefixes?
- Does any custom filter bypass authorization?
- Did any role/scope mapping grant broader access than intended?
- Are tokens with bad issuer, audience, or expiration accepted?
- Can one user read another user's records within the same tenant or across tenants?
- Does logout genuinely invalidate sessions?
- Do error handlers leak sensitive payloads?
- Does auditing log access-denied events without leaking raw tokens?

Automate these negative tests and run them again after Security 7 matcher changes. An “admin succeeds” test never substitutes for a “regular user is denied” test.

## 29. Rollout, Rollback, and Production Observability

When running two versions side by side:
- Are cookie names, paths, domains, `SameSite` flags, and signing keys compatible?
- Can session stores deserialize session state written by both versions?
- Do OAuth callback/redirect URIs match gateway/canary routing?
- Are JWT authority mappings identical?
- Do proxies forward `X-Forwarded-Proto`/forwarded headers properly?
- Does logging out on one version log the user out across the other?
- If rolling back code, do newly issued sessions or tokens stay valid?

Track metrics split by endpoint/category:
- Login success/failure counts and MFA challenges if applicable.
- HTTP 401/403/302 anomalies by user class without logging PII.
- JWT validation, expiration, and issuer failures.
- CSRF/CORS rejections.
- Added latency in authentication, authorization, or IdP calls.
- Audit coverage and access-denied event counts.

Never widen permissions globally to suppress 403s before confirming which requests legitimately deserve access.

## 30. Mistakes to Avoid

**“Green build means migration is done.”** Endpoints may still be silently unprotected.

**“Just rename the matcher API.”** Path semantics, ordering, and servlet context behavior may differ.

**“Disable CSRF on all REST APIs.”** REST endpoints using cookies/sessions still need CSRF protection.

**“`hasRole("ADMIN")` and `hasAuthority("ADMIN")` are the same.”** Default `ROLE_` prefix handling distinguishes them.

**“Mock JWT checks signatures cleanly.”** `jwt()` helpers bypass real JWT decoder verification.

**“An `/api` matcher eliminates the need for a catch-all chain.”** Unmatched paths risk falling outside Spring Security.

**“`authenticated()` handles ownership.”** Object/tenant ownership remains a distinct authorization contract.

**“Securing controllers protects everything.”** Services may still be invoked by jobs, listeners, or internal code.

**“Method security annotations fire on `new`-created objects.”** Without Spring AOP proxies, advice does not run.

**“Every 403 is a bug.”** Missing CSRF tokens or insufficient permissions rightly trigger 403.

## 31. Pre-Approval Checklist for Upgraded Spring Security

- [ ] Recorded exact Spring Security, Spring Boot, Spring Framework, Servlet/Jakarta, and JDK versions.
- [ ] Reviewed migration guides and release notes for each upgrade step.
- [ ] Inventoried all filter chains, matchers, filter ordering, and custom auth flows.
- [ ] Maintained an endpoint × principal × credentials × expected result matrix.
- [ ] Verified every protected URI matches at least one security chain.
- [ ] Verified path matchers, context paths, multi-servlet setups, and encoded paths.
- [ ] Built positive and negative tests for roles, authorities, scopes, and claim mappings.
- [ ] Tested real JWT decoder validation for signatures, issuer, audience, expiry, and key rotation.
- [ ] Confirmed CSRF enforcement remains intact on protected cookie/session flows.
- [ ] Tested CORS preflight requests separately from actual authenticated requests.
- [ ] Verified session login, logout, expiration, and persistence across consecutive requests.
- [ ] Verified OAuth2/OIDC/SAML flows if used.
- [ ] Verified Method Security executes through Spring proxies with negative tests.
- [ ] Confirmed custom filters neither double-register nor run out of order.
- [ ] Confirmed ownership, tenant isolation, and IDOR protections stayed intact.
- [ ] Tested security headers, cookies, and HTTPS redirects behind proxies.
- [ ] Prepared canary rollout, audit/metrics tracking, and rollback handling session state changes.
- [ ] Refused to relax permissions merely to turn failing tests green without a security review.

## References

- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): official documentation on HTTP security, authentication, and authorization.
- [Spring Security 6 Migration Guide](https://docs.spring.io/spring-security/reference/6.5/migration/index.html): preparing from 5.8 and migrating to 6.
- [Spring Security 7 Migration Guide](https://docs.spring.io/spring-security/reference/7.0/migration/index.html): steps for upgrading to 7.
- [Spring Security 7 Web Migration Preparation](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html): `PathPattern` and matcher changes.
- [Spring Security Configuration Migration to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html): Lambda DSL and configuration updates.
- [Spring Security 6.5 Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): differences between `securityMatcher` and `requestMatchers`.
- [Spring Security 7 Authorization](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` and `authorizeHttpRequests`.
- [Spring Security Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/7.0/servlet/test/mockmvc/oauth2.html): `jwt` mocks and `MockMvc` testing.
- [Spring Security CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF protection principles.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): compatibility, auto-configuration, and testing per Boot release.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege, and IDOR prevention.
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/): reference for security verification requirements.

## Conclusion

Upgrading Spring Security must be executed as **a security contract migration**. API shifts in Spring Security 6/7—most notably `SecurityFilterChain` beans, Lambda DSL, request matchers, and Jakarta modules—are merely the surface representation in source code. What matters is verifying that every endpoint and operation still enforces the intended authentication, authorization, CSRF, CORS, session, and JWT policies. Establish a baseline, test both authorized callers and callers who must be rejected, verify real JWT decoders and proxy/container integrations, and roll out via canary with rollback readiness. A sound migration prevents not only startup failures, but also unintended privilege escalation.
