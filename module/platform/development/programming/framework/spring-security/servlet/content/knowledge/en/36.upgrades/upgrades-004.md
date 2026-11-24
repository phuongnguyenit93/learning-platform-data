# From Legacy Chained Configuration to Lambda DSL in Spring Security Servlet

## 1. Upgrade context: the goal is preserving the security policy

A Spring MVC project may have configured Spring Security using **chained DSL**:

~~~java
// OLD style code, for reading/comparison only; does not compile in Spring Security 6.
http
    .authorizeRequests()
        .antMatchers("/public/**").permitAll()
        .antMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
        .and()
    .formLogin()
        .and()
    .httpBasic();
~~~

This style invokes configurers that return intermediate objects and relies on `.and()` to return to the parent `HttpSecurity`. As configurations grow, it becomes hard to see which configurer a method applies to, and syntax support differs across Spring Security versions.

In the **Lambda DSL**, each configurer accepts a clearly scoped lambda function:

~~~java
// NEW style, for Spring Security 6 / Servlet.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());

return http.build();
~~~

In Java files you must import `org.springframework.security.config.Customizer`. The snippets early in this lesson are configuration fragments inside a method receiving `HttpSecurity`, not standalone runnable classes; the complete example and Maven project are in Section 9.

**Most importantly:** upgrading the DSL must **preserve—or deliberately change with verification—** your security invariants: which endpoints are public, who can call which methods, whether CSRF applies to POST, the unauthenticated entry point, filters/cookies/sessions/headers, and data authorization checks. Never treat “the code compiles again” as proof there is no authentication/authorization regression.

This lesson belongs to the **Upgrades** topic of Spring Security Servlet, focusing on migrating from chained/`.and()` style to lambdas along with related API changes. The hands-on example uses **Java 17, Spring Boot 3.3.5, and Spring Security 6**, where the versions merely illustrate a concrete baseline and do **not** claim to be the latest or still supported at release time. When applying to a product, check the release notes, migration guide, and version support for the exact line you use.

## 2. From WebSecurityConfigurerAdapter to a SecurityFilterChain bean

In older codebases, you may encounter:

~~~java
// HISTORICAL CODE — Spring Security 5.x, CANNOT be used as-is with 6.x.
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .httpBasic();
    }
}
~~~

`WebSecurityConfigurerAdapter` was marked deprecated in Spring Security 5.7 and removed in Spring Security 6. `antMatchers()` and `authorizeRequests()` are markers you need to inspect when moving to the new API. The Lambda DSL is not just replacing `.and()`: the application should also migrate to **bean-based configuration**.

Equivalent Spring Security 6 version:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Imports for this snippet: `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.security.config.annotation.web.configuration.EnableWebSecurity`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer`, `org.springframework.security.web.SecurityFilterChain`. When using Spring Boot auto-configuration, `@EnableWebSecurity` is typically optional, though you can keep it when you want it explicit.

**Key points to understand:**

1. `SecurityFilterChain` is a **bean** defining the filter chain for requests selected by its matcher; `HttpSecurity.build()` constructs the chain.
2. You no longer override `configure(HttpSecurity)` from the removed adapter.
3. With `authorizeHttpRequests`, Spring Security uses the **AuthorizationManager/AuthorizationFilter** architecture; this is not merely a rename of `authorizeRequests`. You should also verify dispatcher types, matchers, and evaluation order.
4. `httpBasic(Customizer.withDefaults())` enables HTTP Basic defaults cleanly without calling `.httpBasic().and()`.
5. `@Bean` allows managing multiple chains with `@Order`, configuring components cleanly, and intentionally testing each route.

**Do not** both extend the old adapter and declare new `SecurityFilterChain` beans in the same class hoping Spring will reconcile them. During migration, remove the legacy path and ensure the app only has intentional chains.

## 3. What does Lambda DSL change in how you write config?

A lambda typically looks like:

~~~java
http.formLogin(form -> form
        .loginPage("/login")
        .defaultSuccessUrl("/home", true)
        .permitAll());
~~~

Here `form` is a `FormLoginConfigurer`. Calls inside the lambda configure **form login** only. Once the lambda closes, you are back on `HttpSecurity` **without** calling `.and()`.

Comparison:

| Need | Legacy chained style | Modern Lambda DSL |
| --- | --- | --- |
| Permit public URLs | `authorizeRequests().antMatchers(...).permitAll()` | `authorizeHttpRequests(auth -> auth.requestMatchers(...).permitAll())` |
| Default HTTP Basic | `httpBasic()` then `.and()` if needed | `httpBasic(Customizer.withDefaults())` |
| Form Login | `formLogin().loginPage("/login").and()` | `formLogin(form -> form.loginPage("/login"))` |
| CSRF | `csrf().disable()` in some older code | `csrf(csrf -> csrf.disable())` only if **justified by security analysis** |
| Logout | `logout().logoutUrl("/logout").and()` | `logout(logout -> logout.logoutUrl("/logout"))` |
| Session | `sessionManagement().sessionCreationPolicy(...).and()` | `sessionManagement(session -> session.sessionCreationPolicy(...))` |
| Security headers | `headers().frameOptions().sameOrigin().and()` | `headers(h -> h.frameOptions(f -> f.sameOrigin()))` |
| Resource Server JWT | `oauth2ResourceServer().jwt().and()` | `oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))` |

**Do not copy `csrf(csrf -> csrf.disable())` as a default.** It is merely syntax for a configuration decision that has already been analyzed. In apps with cookies/sessions and unsafe browser methods, disabling CSRF globally can introduce vulnerabilities. The main example in Section 9 **keeps CSRF enabled**.

`Customizer.withDefaults()` expresses “apply this configurer's default settings with no extra customization,” equivalent in DSL semantics to an empty lambda:

~~~java
http.httpBasic(Customizer.withDefaults());
http.httpBasic(basic -> {});
~~~

Pick one style; do not call both repeatedly in the same configuration. An empty lambda is shorter, while `Customizer.withDefaults()` usually communicates intent better.

### 3.1. Must every method call become a lambda?

No. Several methods on `HttpSecurity` and other objects still use regular setters/builders. What needs converting are **no-arg configurer DSL methods returning a configurer + `.and()`**, especially deprecated/removed APIs, to avoid scope confusion. For example:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

The final call is still `.build()` on `HttpSecurity`, not an error. `hasRole(...)` and `permitAll()` are still chained inside the lambda because they define rules on the registry.

### 3.2. Why does declaration order still matter?

Lambdas do not change **first matching rule wins** semantics. Dangerous example:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

If `/api/admin/**` already matches the broader `/api/**` rule placed first, the admin requirement below never takes effect as intended. The right rule is **specific matchers before broad matchers**, paired with negative role tests:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
~~~

Similarly, `hasRole("ADMIN")` checks `ROLE_ADMIN` with the default prefix, whereas `hasAuthority("ADMIN")` checks the exact string `ADMIN`. Migration must never unintentionally alter authority conventions.

## 4. Detailed migration map: URL matchers and authorization APIs

The following APIs commonly appear in legacy projects:

~~~java
// Historical code; does not compile with Spring Security 6.
http.authorizeRequests()
    .antMatchers("/api/public/**").permitAll()
    .mvcMatchers("/reports/**").hasRole("ANALYST")
    .antMatchers(HttpMethod.POST, "/orders/**").hasRole("EDITOR")
    .anyRequest().authenticated();
~~~

In the new configuration, you can write:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/reports/**").hasRole("ANALYST")
    .requestMatchers(HttpMethod.POST, "/orders/**").hasRole("EDITOR")
    .anyRequest().authenticated());
~~~

`HttpMethod` is imported from `org.springframework.http.HttpMethod`. The new snippet uses `requestMatchers`; do not assume every matcher **before and after** has identical semantics in all cases.

**Changes to verify:**

- Historical `antMatchers` and `mvcMatchers` are no longer standard registry methods in Spring Security 6; `requestMatchers` is the unified API that chooses an appropriate request matcher based on context and overloads.
- When Spring MVC is present, matcher selection may rely on `HandlerMappingIntrospector` and the servlet path; verify **in practice** how URL decoding/normalization, trailing slashes, encoded slashes, matrix variables, or custom servlet paths behave.
- `requestMatchers(HttpMethod.POST, "/orders/**")` matches POST only; GET/DELETE on the same path may need separate rules.
- `requestMatchers("/reports/**")` with no HTTP method restriction applies to all HTTP methods matching the path, not only GET.
- `anyRequest().authenticated()` and `anyRequest().denyAll()` mean different things. During migration, classify endpoints and **deliberately decide** whether to switch to default-deny or keep previous behavior.
- Previous custom regex/request matchers need dedicated tests rather than replacing them with `/**`, which easily widens scope.
- For `@PreAuthorize`, if legacy code uses `@EnableGlobalMethodSecurity(prePostEnabled=true)`, review migrating to `@EnableMethodSecurity`; URL DSL **does not** automatically enable method security.

### 4.1. securityMatcher and requestMatchers are not interchangeable

These are two distinct scopes:

~~~java
// Selects WHICH requests the entire filter chain handles:
http.securityMatcher("/api/**");

// Authorizes requests already inside the selected chain:
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`securityMatcher("/api/**")` grants no permissions on its own; it decides **whether the chain is selected**. If no chain matches `/reports/**`, those requests may **not be protected by Spring Security at all**, regardless of whether another chain ends with `anyRequest().denyAll()`. Each chain only decides for requests it handles.

Multi-chain example:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin/**")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This is a **configuration snippet for an application with the required bean dependencies and imports**, not a standalone file. `@Order` is imported from `org.springframework.core.annotation.Order`. The fallback chain has no `securityMatcher` so it catches the remaining routes; verify public assets, login callbacks, and error paths. If form login uses a default login URL outside `/api/**`, check which chain handles it.

With multiple servlets, you may need `MvcRequestMatcher.Builder` or `PathPatternRequestMatcher` appropriate to your framework line, explicitly specifying the servlet path. Avoid copying matcher config verbatim from another app when context paths or reverse-proxy rewrites differ.

## 5. Migrating common configurations while preserving policy

### 5.1. Form login and custom login page

Old style:

~~~java
// Historical — chained
http.formLogin()
        .loginPage("/login")
        .defaultSuccessUrl("/dashboard", true)
        .permitAll()
        .and();
~~~

New style:

~~~java
http.formLogin(form -> form
        .loginPage("/login")
        .defaultSuccessUrl("/dashboard", true)
        .permitAll());
~~~

**You need an actual controller/view for GET `/login`** if using a custom login page. `.permitAll()` on the form login configurer governs access to login-related URLs; it does not ensure CSS, JS, and error views are permitted. If you want Spring Security's default generated login page, use `formLogin(Customizer.withDefaults())`.

Changing `loginPage`, success URL, or saved-request behavior is a **UX/security flow change** and should not be mixed into syntax conversion. With session cookies, keep CSRF checks on login POST and test session fixation protection, logout, and remember-me if used.

### 5.2. HTTP Basic

~~~java
http.httpBasic(Customizer.withDefaults());
~~~

HTTP Basic sends `Authorization: Basic ...` on every request, so it must run over HTTPS. For unauthenticated requests, the entry point normally returns 401 with a `WWW-Authenticate` header, whereas form login usually returns a 302 redirect. Do not treat a change from 302 to 401 as automatically a bug or a win—verify the entry point against your client contract.

An application with both `formLogin` and `httpBasic` may pick an entry point depending on the request, `Accept` header, and chain. Write tests matching your real browser/API clients rather than checking only one `curl -i`.

### 5.3. CSRF: avoid mechanically porting `disable`

Legacy syntax:

~~~java
// Historical, representing a policy that needs re-evaluation.
http.csrf().disable();
~~~

Corresponding lambda syntax:

~~~java
// Illustrates SYNTAX only; not recommended for all projects.
http.csrf(csrf -> csrf.disable());
~~~

**Do not treat this as a default configuration.** Spring Security Servlet enables CSRF by default; for requests where browsers attach cookies/sessions automatically, unsafe methods need CSRF protection. When upgrading, ask: does the app authenticate via cookies, Basic, bearer tokens, or a mix? Does a browser attach credentials automatically? Which endpoints have side effects? Are there cross-origin requests?

To preserve default protection:

~~~java
http.csrf(Customizer.withDefaults());
~~~

Or omit `csrf(...)` when the default configuration is appropriate.

When a webhook is verified with its own signature and does not use browser sessions, you can consider a narrow exception:

~~~java
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhooks/verified/**"));
~~~

This is a **config snippet**: `/webhooks/verified/**` must enforce proper authentication/signature verification and replay protection. Disabling CSRF alone does not make a webhook secure. Specifically, **`permitAll()` does not disable CSRF**: a POST to a public URL can still be rejected by `CsrfFilter` if the token is missing.

### 5.4. CORS

~~~java
http.cors(Customizer.withDefaults());
~~~

Enabling CORS integration does not define your origin policy. The application must supply an appropriate CORS config (such as a `CorsConfigurationSource` or chosen MVC CORS integration), allowing only required origins, methods, and headers. Never combine wildcard origins with credential support; preflight `OPTIONS` requests usually carry no session cookies, so CORS must run properly before authentication.

A valid preflight does not mean the actual request is authorized: the actual request still requires authentication, authorization, and CSRF if dictated by the threat model.

### 5.5. Logout

~~~java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/logged-out")
        .invalidateHttpSession(true));
~~~

In apps with CSRF enabled, Spring Security normally requires **POST /logout** for safe logout. Do not switch to GET logout just for link convenience if it lets third-party sites force users to log out. Ensure `/logged-out` exists and is accessible if everyone should see it after logging out.

When remember-me, refresh tokens, or distributed session stores are used, logout does not automatically revoke every access token or remote session; handle that with a dedicated policy.

### 5.6. Session management

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

Import `org.springframework.security.config.http.SessionCreationPolicy`. For pure bearer-token APIs, you can use:

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

**`STATELESS` does not mean every request is automatically protected by JWT, nor does it disable CSRF by itself.** You still must configure token validation, ensure browsers cannot send credentials automatically in your model, and check session usage across other components. Do not switch an entire `formLogin`/OIDC app to `STATELESS` simply during a DSL migration; doing so can break login state/sessions.

### 5.7. Security headers

~~~java
http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                        "default-src 'self'; object-src 'none'; " +
                        "base-uri 'self'")));
~~~

`Content-Security-Policy` must be tailored to your application's actual script/style/frame sources; the example above shows syntax and a restrictive baseline. Never add `unsafe-inline`/`*` mechanically just to fix broken UI. Server-rendered HTML may need nonces, hashes, or a report-only rollout.

Spring Security provides default security headers, yet **does not generate an app-specific CSP automatically**. HSTS normally depends on HTTPS requests; HTTP MockMvc tests alone are not enough to prove browsers receive HSTS at ingress. Security headers do not replace TLS and never justify logging tokens.

If the old project used:

~~~java
// Old chained snippet:
http.headers()
        .frameOptions().sameOrigin()
        .and();
~~~

The equivalent lambda can be:

~~~java
http.headers(headers -> headers
        .frameOptions(frame -> frame.sameOrigin()));
~~~

Relax `frame-options` only when the app has a legitimate framing requirement reviewed in the threat model; default `DENY` may be preferable. If using the H2 Console in dev, never carry permissive frame/CSRF dev-profile settings into production.

### 5.8. Exception handling and 401/403

~~~java
http.exceptionHandling(errors -> errors
        .authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));
~~~

Imports for the snippet: `org.springframework.security.web.authentication.HttpStatusEntryPoint` and `org.springframework.http.HttpStatus`. This is an option for APIs that want 401 instead of redirects; it is unnecessary when HTTP Basic already handles this appropriately. For hybrid browser-and-API apps, customizing entry points per `RequestMatcher` may be cleaner than global settings.

**401** generally indicates an unauthenticated request; **403** indicates an authenticated user lacking permissions, or a request rejected by CSRF. A POST test returning 403 without a CSRF token **does not prove** role enforcement is working.

### 5.9. OAuth2 Login and OIDC

When a project uses OAuth2 Client, configure each user service branch inside the lambda:

~~~java
// Config snippet; requires oauth2-client dependency and corresponding beans.
http.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(userInfo -> userInfo
                .userService(customOAuth2UserService)
                .oidcUserService(customOidcUserService)));
~~~

`userService` handles non-OIDC OAuth2 login; `oidcUserService` handles OpenID Connect. Do not accidentally drop the OIDC-specific configurer when removing `.and()`. In regressions, verify authorization code callbacks, state, nonce where applicable, ID token validation, issuer, redirect URIs, sessions, and local identity/role mapping.

### 5.10. OAuth2 Resource Server / JWT

~~~java
// Config snippet; not included in the Section 9 Maven demo.
http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
~~~

This configuration is meaningful only when the app includes `spring-boot-starter-oauth2-resource-server` and appropriate JWT decoder/issuer/JWK settings. It does not issue JWTs or validate audience automatically; define policies for issuer, audience, expiry, algorithms, roles/scopes, and error handling. Do not confuse browser `oauth2Login` with bearer-API `oauth2ResourceServer`.

### 5.11. HTTPS-only APIs

In suitable environments, secure-channel policies can be expressed with the Lambda DSL, but ingress HTTPS, proxy forwarded headers, and runtime awareness must all be aligned. If the app runs internal HTTP behind a trusted TLS terminator, a misconfigured “redirect HTTP → HTTPS” rule can cause infinite loops. Test the effective scheme Spring sees, proxy trust, and secure cookies via integration tests through the ingress.

## 6. Non-syntactic changes when upgrading Spring Security

Many teams hit bugs because they assume every difference comes from changing `.and()` to `->`. In reality, distinguish **DSL style migration** from **framework semantic migration**.

| Area | What can change | How to verify |
| --- | --- | --- |
| Adapter → `SecurityFilterChain` bean | Bean ordering, chain selection, Spring Boot default chain | Count chains, inspect `securityMatcher`/`@Order`, test every route |
| `authorizeRequests` → `authorizeHttpRequests` | `AuthorizationManager`/`AuthorizationFilter`, dispatch/invocation behavior | Role matrix + `FORWARD`/`ERROR` dispatch tests |
| `antMatchers`/`mvcMatchers` → `requestMatchers` | MVC/servlet path matching, URL encoding, HTTP methods | Negative tests on paths, queries, servlet contexts |
| `hasRole`/authority mapping | Prefix and hierarchy; no automatic role inheritance | Test `ROLE_USER` vs `ROLE_ADMIN` |
| CSRF config | Matchers and token handling, especially SPA/session | POST/PUT/PATCH/DELETE with/without/invalid CSRF |
| Form login/OIDC | Entry points, redirects, sessions, state/callbacks | Login success/fail, cookies, redirects, logout |
| Headers | CSP, HSTS, frame options, and version defaults | Inspect HTTP headers over HTTPS/browser |
| Custom DSL | `apply`/`with` APIs, bean lifecycle | Check filter order and test before/after effects |
| Multiple chains | Fallback chain, unmatched requests | Test routes outside `/api`, static, error, actuator |
| Method security | `@EnableMethodSecurity`, proxy/SpEL differences | Invoke Spring-managed services and HTTP endpoints |

Legacy API examples are **historical code for recognition/comparison**; they do not compile directly on Boot 3.x. For real projects, consult the migration guide for your exact source/target versions (e.g., 5.x → 6.x or 6.x → 7.x) and test against your system's policy.

### 6.1. FORWARD, ERROR, and ASYNC dispatchers

In Servlet containers, a request may be dispatched as `REQUEST`, `FORWARD`, `ERROR`, or `ASYNC`. When changing authorization strategies, inspect `spring.security.filter.dispatcher-types`, filter registrations, and rules for internal forward/error views. Do not blanket-allow `dispatcherTypeMatchers(FORWARD).permitAll()` if sensitive endpoints are invoked via forwards.

A safer approach protects both source and target URLs while enforcing method/service-level authorization on sensitive data. In tests, `MockMvc.forwardedUrl(...)` does not by itself prove the real container executed a forward and re-ran filters; add integration tests when that is a security requirement.

### 6.2. Static resources and skipping filters

`web.ignoring().requestMatchers("/assets/**")` skips security filters and headers for static requests. In many applications, prefer:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/login").permitAll()
        .anyRequest().authenticated());
~~~

**Only** truly public resources should be permitted. Never store private uploads under `classpath:/static/` while guarding only a `/files/**` controller; those files could still be fetched from another static URL. Private download routes need service-layer owner/tenant ACLs, not just URL roles.

### 6.3. Method security is not replaced by URL DSL

Where `@PreAuthorize` is used, migrating from `@EnableGlobalMethodSecurity(prePostEnabled=true)` to `@EnableMethodSecurity` fits Spring Security 6. Never drop method security simply because URL rules moved to lambdas.

Example snippet:

~~~java
@Service
class DocumentService {

    @PreAuthorize("hasRole('READER') and " +
                  "@documentAccess.canRead(authentication, #p0)")
    Document read(String documentId) {
        // Fetch by exact document ID and enforce ownership in service.
        return repository.getRequired(documentId);
    }
}
~~~

This is an **illustrative snippet that does not compile standalone**: `Document`, `repository`, and `documentAccess` are application domain dependencies. `#p0` references the first method parameter; a `documentAccess` bean and `@EnableMethodSecurity` are required. Method-level checks only run when invoked through the Spring security proxy; self-invocation can bypass the proxy.

## 7. Step-by-step refactoring workflow without unintended privilege widening

Use a **verified process** instead of converting entire files with blind search-and-replace:

1. **Capture baseline policy**: list old `SecurityFilterChain`s, URLs/methods, matcher order, roles, public assets, login/logout, CSRF, CORS, sessions, headers, and custom filters.
2. **Build an expectation matrix**: anonymous/USER/ADMIN/other tenants, GET/POST/PUT/DELETE, valid/missing/invalid CSRF, 401/302/403, and business state.
3. **Upgrade runtime/toolchain properly**: Java 17+ when moving to Spring Boot 3 / Spring Framework 6; update the compatible BOM instead of bumping individual Spring Security modules arbitrarily.
4. **Migrate structure**: `WebSecurityConfigurerAdapter` → `SecurityFilterChain @Bean`; preserve request scopes, filter chain order, and authentication providers.
5. **Convert each configurer**: `authorizeRequests` → `authorizeHttpRequests`, `antMatchers`/`mvcMatchers` → matching `requestMatchers`; `formLogin`/`httpBasic`/`logout`/`csrf`/headers/CORS to lambdas.
6. **Remove `.and()` semantically**: do not blindly delete all `.and()` chains and guess until it compiles; verify each configurer's before/after scope.
7. **Audit behavioral differences**: matcher resolution, dispatchers, default-deny, login entry points, and CSRF tokens—especially when replacing `authorizeRequests` with `authorizeHttpRequests`.
8. **Run security regressions**: MockMvc for URL and method role matrices; integration tests for login/OIDC/LDAP, TLS/ingress, forwarded/ERROR dispatches, and cookies/sessions.
9. **Verify runtime effect**: right profiles/env vars, no unintended default/generated users, no unguarded gaps between chains, no exposed Actuator/debug endpoints.
10. **Release with rollback**: record commit/dependency tree, artifact digest, and security test report; verify canary/staging before production, comparing 401/403/CSRF rejections after deploy.

A successful migration may intentionally **tighten** a route that was previously public by mistake. In that case, update tests and changelogs per the approved decision rather than “preserving the behavior” of an old vulnerability. Conversely, if an old rule checked owner/tenant and the new code checks only a role, that is a security regression even if valid requests still return 200.

### 7.1. Grep commands to locate legacy configurations

In a terminal with Git and a compatible shell:

~~~bash
# Locate legacy markers and inspect every match manually.
git grep -n -E 'WebSecurityConfigurerAdapter|authorizeRequests|antMatchers|mvcMatchers'
git grep -n -E 'csrf\(\)|formLogin\(\)|httpBasic\(\)|sessionManagement\(\)'
git grep -n 'web.ignoring'
git grep -n 'EnableGlobalMethodSecurity'
~~~

Expressions like `csrf()` can also appear inside **test helpers**, not production config; never mass-replace indiscriminately. `git grep` searches only tracked source files, not external config from secret managers/Helm or third-party libraries; verify runtime config separately.

### 7.2. Before-and-after mapping for the same requirement

Requirement: public GET `/public/status`, USER can GET `/api/me`, ADMIN can GET `/admin/audit`, all other routes denied.

Legacy illustration:

~~~java
// OLD CODE; syntax applies only to Spring Security lines supporting legacy APIs.
http.authorizeRequests()
        .antMatchers(HttpMethod.GET, "/public/status").permitAll()
        .antMatchers(HttpMethod.GET, "/api/me").hasRole("USER")
        .antMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
        .anyRequest().denyAll()
        .and()
        .httpBasic();
~~~

Modern:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/me").hasRole("USER")
        .requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
        .anyRequest().denyAll());

http.httpBasic(Customizer.withDefaults());
return http.build();
~~~

Converting code **does not** decide whether `/api/me` should be `hasRole("USER")` or `authenticated()`: that is a business requirement whose agreed policy must be preserved. If the old app allowed ADMIN to read `/api/me` via a role hierarchy, the new app must declare and test that hierarchy or an equivalent `hasAnyRole`.

## 8. Demo goal: verifying new syntax and security invariants

For practice, let's build a standalone app using HTTP Basic and several endpoints:

| Method/URL | Anonymous | READER | ADMIN | Notes |
| --- | ---: | ---: | ---: | --- |
| GET `/public/ping` | 200 | 200 | 200 | Explicitly public |
| GET `/api/me` | 401 | 200 | 200 | Requires authentication |
| POST `/api/notes` (valid CSRF) | 401 | 201 | 403 | READER only; ADMIN does not implicitly have READER |
| GET `/admin/audit` | 401 | 403 | 200 | ADMIN only |
| GET `/unexpected` | 401 | 403 | 403 | Default deny (after auth, if authenticated) |

The app uses test users `reader` and `admin` with `{noop}` demo passwords **solely for this lesson**. This is a fixture for testing behavior via HTTP Basic; never put this password configuration into production. Never copy mock endpoints into business APIs handling sensitive data without ownership/tenant checks.

**About CSRF:** in tests checking POST authorization, we supply a valid token so the 403 (for ADMIN) comes purely from the role check. Dedicated tests also verify that POST with missing/invalid CSRF returns 403 for an authorized user. Browser sessions require real CSRF protection; here it stays enabled by default to demonstrate a safe migration.

## 9. Complete Java 17 + Spring Boot 3.3.5 project

### 9.1. Directory structure

~~~text
lambda-dsl-migration-demo/
  pom.xml
  src/main/java/example/lambdadsl/LambdaDslApplication.java
  src/test/java/example/lambdadsl/LambdaDslSecurityTests.java
~~~

You only need Maven, JDK 17+, and valid Maven repository access to resolve dependencies. **Boot 3.3.5 is an illustrative baseline**, not a recommendation for a future greenfield system to pick a version without checking current security support.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>lambda-dsl-migration-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
~~~

Dependencies for OAuth2 Login/OIDC, JWT Resource Server, and Actuator **are not in the demo POM**; those snippets in Section 5 only illustrate migration syntax and cannot be used directly in this project without adding the right dependencies and configuration.

### 9.3. SecurityFilterChain and controllers

**src/main/java/example/lambdadsl/LambdaDslApplication.java**:

~~~java
package example.lambdadsl;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LambdaDslApplication {

    public static void main(String[] args) {
        SpringApplication.run(LambdaDslApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        // LEARNING ONLY: {noop} allows unhashed demo passwords.
        // Production requires PasswordEncoder and a trusted user store.
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                    .password("{noop}demo-pass")
                    .roles("READER")
                    .build(),
                User.withUsername("admin")
                    .password("{noop}demo-pass")
                    .roles("ADMIN")
                    .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(
                    HttpMethod.POST, "/api/notes").hasRole("READER")
                .requestMatchers(
                    HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // Written explicitly to emphasize CSRF is not disabled.
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "object-src 'none'; base-uri 'self'")))
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public/ping")
        Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("name", authentication.getName());
        }

        @PostMapping("/api/notes")
        ResponseEntity<Map<String, String>> createNote() {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "note-1"));
        }

        @GetMapping("/admin/audit")
        Map<String, String> audit() {
            return Map.of("result", "restricted");
        }
    }
}
~~~

This is a **complete Java file** matching the POM above; `@SpringBootApplication` lets Spring Boot scan the nested controller. Every Security configuration call uses the **Lambda DSL or `Customizer.withDefaults()`**, with zero `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`, or `.and()`.

**Expected policy:**

- `GET /public/ping`: no authentication required; `permitAll`, yet the Security filter chain still runs.
- `GET /api/me`: any valid authenticated user can view **their own** name; the demo's Basic provider validates passwords when requests carry credentials.
- `POST /api/notes`: `ROLE_READER` only, and must include a valid CSRF token to pass `CsrfFilter`.
- `GET /admin/audit`: `ROLE_ADMIN` only.
- Other routes: `denyAll`, not public by default.
- `Content-Security-Policy` is included to illustrate header syntax; real apps rendering HTML/SPAs must verify scripts/styles/assets and roll out report-only/nonces as needed.
- `{noop}` and JSON `Map` responses are fixtures. The POST endpoint writes to no database; real versions need validation, object-level ACLs, idempotency, and data protection.

### 9.4. Running the application and sample requests

In the project directory:

~~~bash
mvn -B -ntp clean verify
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# Public GET: 200.
curl -i http://localhost:8080/public/ping

# Unauthenticated: 401 via HTTP Basic.
curl -i http://localhost:8080/api/me

# Valid credentials: 200 + {"name":"reader"}.
curl -i -u reader:demo-pass http://localhost:8080/api/me

# Reader accessing admin: 403.
curl -i -u reader:demo-pass http://localhost:8080/admin/audit

# Admin allowed: 200.
curl -i -u admin:demo-pass http://localhost:8080/admin/audit

# POST missing CSRF: typically 403 before checking role.
curl -i -u reader:demo-pass -X POST \
    http://localhost:8080/api/notes
~~~

Because this demo keeps CSRF enabled and provides no endpoint issuing CSRF tokens to curl, **do not use the POST command above to conclude whether `ROLE_READER` has permission**. To verify POST role rules with a valid CSRF token, use `MockMvc.with(csrf())` in Section 10. In a real app with a browser/session, GET the page/form to obtain the CSRF token and POST with the same session cookie.

**HTTP Basic over plain HTTP** is for local practice only. Production must use HTTPS. Demo passwords must never be used for real accounts or environments with sensitive data.

## 10. Regression testing with JUnit 5 and MockMvc

When migrating the DSL, the test suite should verify:

1. Public endpoints remain public on the intended HTTP method.
2. Anonymous requests remain blocked on protected endpoints.
3. Valid users pass authentication with **real HTTP Basic credentials** (distinct from mock users).
4. Reader cannot access admin endpoints.
5. Admin does not implicitly possess the READER role.
6. POST with valid role + CSRF succeeds.
7. POST with missing/invalid CSRF is rejected.
8. Undeclared routes/methods hit default-deny.
9. Configured security headers are still emitted.

**src/test/java/example/lambdadsl/LambdaDslSecurityTests.java**:

~~~java
package example.lambdadsl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LambdaDslSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void anonymousUserCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicCredentialsAreValidated() throws Exception {
        mvc.perform(get("/api/me")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("reader"));

        mvc.perform(get("/api/me")
                    .with(httpBasic("reader", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotReadAdminAudit() throws Exception {
        mvc.perform(get("/admin/audit")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAudit() throws Exception {
        mvc.perform(get("/admin/audit")
                    .with(httpBasic("admin", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("restricted"));
    }

    @Test
    void readerCanCreateWithCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("reader", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("note-1"));
    }

    @Test
    void adminHasNoImplicitReaderRole() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("admin", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("reader", "demo-pass"))
                    .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void unlistedRouteIsDeniedAfterLogin() throws Exception {
        mvc.perform(get("/unexpected")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void headersArePreservedAfterMigration() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                    "Content-Security-Policy",
                    "default-src 'self'; object-src 'none'; " +
                            "base-uri 'self'"));
    }
}
~~~

Run:

~~~bash
mvn -B -ntp clean verify
~~~

**Expected:** the tests execute through the application's Spring Security filter chain and verify the defined statuses, bodies, and headers. This is **reviewed sample code**, not a report that a Maven build was actually executed here. Run the command on the learner's machine or CI to observe actual results.

**Why not only use `@WithMockUser`?** With `httpBasic(...)`, real headers pass through the filter and provider, testing both valid and invalid passwords. `@WithMockUser` and `with(user(...))` inject a mock identity to test **authorization** without verifying passwords. Combine both test styles per their purpose rather than testing “login success” with a mock principal and claiming the provider works.

**Why is a CSRF token required in POST role tests?** Without `with(csrf())`, even an authorized user receives 403 from `CsrfFilter` before reaching the `hasRole` rule. `adminHasNoImplicitReaderRole` intentionally sends a valid CSRF token so the 403 proves the missing `READER` role.

## 11. Migration test matrix at production scale

Beyond a minimal project, a production application should maintain a matrix:

| Path category | Caller | Context | Expected outcome |
| --- | --- | --- | --- |
| Public CSS/JS/login | Anonymous | GET | Permitted, no private data leaked |
| Protected API | Anonymous | GET | 401 or redirect per entry point |
| Protected API | Authenticated with right role | GET | 200 and right object/tenant |
| Protected API | Authenticated with wrong role | GET | 403 or 404 per policy |
| Admin endpoint | Lower role | GET | No access |
| File download | Same role, different owner | GET/HEAD/Range | Does not download data |
| Mutation endpoint | Right role | POST/PUT/PATCH/DELETE + valid CSRF | Executes exactly one action |
| Mutation endpoint | Right role | Missing/invalid CSRF (where applicable) | Rejected |
| OAuth2 callback | Browser session flow | State/redirect/nonce | Succeeds/fails per protocol |
| Resource server | Bearer JWT with bad signature/issuer/audience | GET/POST | 401/403 per contract |
| Forward/internal view | Direct/forwarded request | FORWARD dispatcher | Proper authorization at source and target |
| CORS preflight | OPTIONS without credentials | Origin/method/header allowlist | Valid preflight; actual request still requires auth |
| Error/actuator | Anonymous | ERROR/GET | No stack traces, secrets, or mappings exposed |
| Unmatched chain | Any | New URL/servlet path | Protected by fallback, no bypass |

You do not need to test every nonsensical combination. However, for **each security rule carrying distinct risk**, include at least one happy path and one or more denial paths. During framework upgrades, **negative** cases catch privilege-escalation bugs far better than comparing only 200 responses.

### 11.1. Method-level authorization and ownership

On `GET /api/documents/{id}`, `authenticated()` or `hasRole("READER")` only states who may invoke the endpoint. Alice must still be prevented from reading Bob's document unless proper ACL/ownership checks exist. Include cross-tenant and same-role wrong-owner tests in before/after regressions.

### 11.2. HEAD, OPTIONS, CORS, and HTTP methods

An MVC `@GetMapping` may automatically serve `HEAD`, whereas Spring Security's `requestMatchers(HttpMethod.GET, ...)` targets GET. If the system supports `HEAD`, specify and test its permissions explicitly. `OPTIONS` is used for CORS preflight; verify how chains and CORS handle it rather than adding `permitAll(OPTIONS, "/**")` and assuming CORS is configured.

### 11.3. External runtime config sources

Spring Boot can load configuration from YAML, environment variables, JVM flags, Config Server, Kubernetes/Helm, or secret managers. During migration, another source might override ports/profiles, enabled endpoints, cookies, issuer URIs, or debug flags. Compare the **effective runtime policy** (redacted), not only `application.yml`.

### 11.4. Non-functional requirements

`SecurityFilterChain` matchers and `AuthorizationManager` checks can affect performance; measure latency on critical routes, custom policy or DB lookup counts, session creation, and error rates. Broad or incorrect matcher changes can trigger widespread 401/403 errors after deploy; monitor canaries by request method, path, status, and error category without logging raw credentials, JWTs, or cookies.

## 12. Typical migration errors and fixes

| Error | Symptom | Cause or fix |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter` does not exist | Compile error when upgrading to Security 6 | Migrate to `SecurityFilterChain` beans |
| `antMatchers()` does not exist | IDE/compiler rejects the method | Use `requestMatchers` matching your type and version |
| `authorizeRequests()`/`.and()` deprecated or removed in target line | Warnings/compile errors | Migrate to `authorizeHttpRequests(auth -> ...)` and lambda configurers |
| No-arg `httpBasic()` deprecated | Compiler warnings on newer versions | Use `httpBasic(Customizer.withDefaults())` |
| Deleting `.and()` via regex breaks code | Configurer scopes and chains corrupted | Refactor block by block, never mass-replace |
| Broad matcher placed before admin | Regular users reach admin routes | Put specific rules first and test negative roles |
| Using `securityMatcher` as a permit/deny rule | Chain skips requests outside its scope | Distinguish chain selection from URL authorization |
| Forgetting fallback chain | A URL bypasses Security handling | Add a protective catch-all chain and test new routes |
| `ROLE_ADMIN` rejected by `hasRole("USER")` | Unexpected 403 | No default role inheritance; check authorities/role hierarchy |
| POST returns 403 after upgrade | Test lacks CSRF or role is missing | Send valid CSRF when testing roles; test missing CSRF separately |
| Putting `csrf.disable()` in every chain | Browser POSTs vulnerable to CSRF | Disable only per threat model and narrow scope |
| Form login redirects instead of HTTP Basic | Anonymous gets 302 instead of 401 | Check authentication entry point, `Accept` header, and chain |
| Login page redirect loop | `/login` not public or missing controller | Fix form-login allowlist and view mapping |
| Static CSS blocked | Login page loses styling | Permit specific public assets without stripping security globally |
| `@PreAuthorize` has no effect | Wrong bean invocation or method security disabled | Enable `@EnableMethodSecurity`, use Spring proxies, add negative tests |
| Forwarded view 403 or exposed publicly | Wrong dispatcher rule or missing target ACL | Check `FORWARD` registration/authorization and service-level policy |
| CORS preflight gets 401 | `OPTIONS` carries no credentials | Integrate CORS properly before auth; actual request still checked |
| OAuth2/OIDC callback fails | Session/state/redirect URI/issuer changed | Run login flow integration tests, not only mock principals |
| CSP blocks legitimate JS | Header directives mismatch real assets | Roll out CSP via report-only/nonces/asset audit |
| Health/actuator accidentally public | `permitAll("/**")` rule or misconfigured management chain | Explicit allowlist + network/access tests |
| Tests pass yet runtime fails | Mock tests skip real auth providers or proxies | Add E2E tests and inspect effective configuration |

**Debug in order:** identify which **chain** the request enters, which **URL/method rule** matches, which authentication entry point applies, whether CSRF rejects it before authorization, whether `@PreAuthorize`/object ACLs block it, and only then check the MVC handler/status. Never resolve a 403 by broadly adding `permitAll`.

## 13. Diagnosing a concrete upgrade scenario

**Symptom:** After migrating to lambdas, `POST /api/orders` always returns 403.

**Step 1 — Check CSRF:** If the app uses Spring Security Servlet with CSRF enabled, a POST without a token can be blocked even for an authenticated user. Using MockMvc:

~~~java
mvc.perform(post("/api/orders")
        .with(user("member").roles("MEMBER"))
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

This is an **illustrative test snippet**; `/api/orders` must exist and allow order creation returning 201 in the real app. It does **not** belong to the Section 9 demo project, where the POST endpoint is `/api/notes`.

**Step 2 — Check method matchers:** If current config permits only `HttpMethod.GET` on `/api/orders/**`, POST falls through to a deny rule. Ensure an approved POST rule exists:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/api/orders")
            .hasRole("MEMBER")
        .anyRequest().denyAll());
~~~

**Step 3 — Check roles:** `hasRole("MEMBER")` expects `ROLE_MEMBER`, not literal `MEMBER`; if JWT/OIDC grants `SCOPE_order.write`, design and verify explicit mapping rather than turning arbitrary scopes into admin rights.

**Step 4 — Check chain selection:** If `securityMatcher("/web/**")` does not match `/api/orders`, the rule may live in a chain that is **never selected** for the API. Ensure an API chain or matching fallback exists.

**Step 5 — Check service/CSRF/application layers:** `@PreAuthorize`, `AccessDeniedHandler`, validation/ownership, and method checks can deny after URL authorization passes. Log safely without printing tokens/passwords, and never diagnose from HTTP status alone.

After fixing, re-test: **member can POST with CSRF**, **admin without the role is denied even with CSRF**, **member without CSRF is denied**, **anonymous with CSRF is denied**, and GET/DELETE on the same URL follow policy. That matrix prevents “fixing a 403” by widening permissions.

## 14. When is Lambda DSL required? Preparing across multiple release lines

Spring Security 5.7 encouraged component-based configuration over `WebSecurityConfigurerAdapter`; Spring Security 6 removed the adapter and legacy matchers. The chained DSL was progressively deprecated in Spring Security 6.x in favor of the Lambda DSL, especially when moving to newer lines.

**Do not confuse “compiles today” with “will remain supported forever.”** When the current build only emits deprecation warnings, migrating to lambdas reduces technical debt before a major upgrade. When moving to a target release, read the **migration guide for that exact release** to see what was removed and which behaviors changed.

Necessary preparations:

- Remove `WebSecurityConfigurerAdapter` and its overridden methods in code moving to Spring Security 6.
- Stop using `.antMatchers(...)` in new rules; migrate to `requestMatchers` with tested semantics.
- Configure primarily via `SecurityFilterChain` beans, `authorizeHttpRequests`, and lambda configurers/`Customizer.withDefaults()`.
- Verify `@EnableMethodSecurity`, entry points, CSRF, dispatcher types, and multiple chains.
- If using custom DSLs via `http.apply(...)`, consult the target framework's migration guide on `http.with(configurer, customizer)` and constructor/bean lifecycles. Never copy this API onto an older framework version without verifying support.
- Never pin Spring Security to an arbitrary newer version while Spring Boot's BOM manages other modules: upgrade with verified compatibility.

For custom DSLs, a **formal** example on releases supporting `with`:

~~~java
// Use only when your custom configurer and target Spring Security
// version support this API.
http.with(customConfigurer, configurer ->
        configurer.setSomeOption(true));
~~~

This snippet illustrates only the migration concept, **not standalone compilable code**: `customConfigurer` and `setSomeOption` are supplied by the application. Projects without custom DSLs do not need `with`; `authorizeHttpRequests`, `httpBasic`, `csrf`, etc. suffice.

## 15. Self-check exercises

**1.** Why can't `authorizeRequests().antMatchers(...).and()` work in Spring Security 6 simply by deleting `.and()`?  
Because the configurer/matcher APIs and underlying configuration model changed; migrate to `authorizeHttpRequests`/`requestMatchers` with appropriate lambdas and verify semantics.

**2.** Does `Customizer.withDefaults()` mean disabling a security control?  
No. It selects the configurer's default configuration (such as HTTP Basic), not `disable()`.

**3.** Is `http.securityMatcher("/api/**")` equivalent to `auth.requestMatchers("/api/**").authenticated()`?  
No. One selects the scope of the **filter chain**, while the other defines **authorization inside a chain**.

**4.** When `anyRequest().denyAll()` is inside a chain matching only `/api/**`, is `/admin` guaranteed to be denied?  
Not yet. Another chain or fallback must cover `/admin`; if no chain matches a route, Spring Security does not protect it.

**5.** Why isn't a passing `@WithMockUser` test enough to prove HTTP Basic password validation works?  
Because the annotation creates a mock authentication without invoking the real password-verifying provider.

**6.** During migration, an admin receives 403 on a URL requiring `ROLE_USER`. Is that a bug?  
Not by default. `ROLE_ADMIN` does not implicitly grant `ROLE_USER` unless a role hierarchy is defined or both roles are assigned.

**7.** A reader's POST returns 403, but the request lacks a CSRF token. Can we conclude reader lacks the role?  
No. Supply a valid CSRF token to test roles; test missing CSRF separately.

**8.** `/public/ping` uses `permitAll()`, yet Spring Security still adds security headers?  
Usually yes, because `permitAll` still routes the request through the filter chain. Skipping filters via `web.ignoring` behaves differently.

**9.** With `formLogin`, can an unauthenticated user receive 302 instead of 401?  
Yes. Depending on the authentication entry point and client; do not copy HTTP Basic expectations onto browser flows.

**10.** Why must `FORWARD`/`ERROR` dispatches be checked when moving to `authorizeHttpRequests`?  
Because dispatch behavior, filter registration, and internal target routes can affect authorization; protect data with defense-in-depth and proper integration tests.

**11.** Some Spring Security modules were overridden above the BOM to patch a CVE. What tests should run?  
Dependency resolution/compatibility, authentication/authorization, sessions, CSRF, headers, login/OIDC/JWT, corresponding integration tests, and SCA confirming vendor-supported patches.

**12.** Does calling `httpBasic(Customizer.withDefaults())` automatically make the app stateless and CSRF unnecessary?  
No. Evaluate session creation, browser credential behavior, and your threat model separately; enabling Basic does not imply removing CSRF.

## 16. Checklist before merging Lambda DSL changes

### Code checks

- [ ] `WebSecurityConfigurerAdapter`/legacy overrides removed when upgrading to unsupported releases.
- [ ] `SecurityFilterChain` beans have complete matchers, `@Order`, and fallback coverage.
- [ ] `authorizeHttpRequests` uses `requestMatchers` appropriate to HTTP methods, paths, and servlets.
- [ ] `hasRole`/`hasAuthority`, rule order, and default-deny match the baseline.
- [ ] `formLogin`/`httpBasic`/CSRF/CORS/logout/session/headers/OAuth configurers migrated piece by piece to lambdas.
- [ ] No demo `csrf.disable()`, `permitAll("/**")`, `web.ignoring("/**")`, or `{noop}` carried into production.
- [ ] `@EnableMethodSecurity` and owner/tenant checks still enforce when calling service beans.
- [ ] Custom filters/`AuthenticationProvider`s/`ExceptionHandler`s retain intended order and scope.

### Behavior checks

- [ ] Unit/MockMvc role matrix: public, anonymous, lower role, admin, unauthorized roles.
- [ ] Unsafe methods: valid/missing/invalid CSRF across flows requiring protection.
- [ ] Credential tests: Basic/form login/OIDC/JWT include failure paths, not just mock principals.
- [ ] Sessions/redirects/logout/cookies behave accurately after migration.
- [ ] Static resources, error/forward paths, and Actuator/internal URLs are not exposed.
- [ ] CORS preflight + actual requests, security headers, and HTTPS/proxy behavior verified where used.
- [ ] Object/tenant ACLs remain intact when URL config changes; test permissions on concrete data.
- [ ] Regression suite includes **negative cases**, not only 200 OK.
- [ ] Dependency BOM and Java version are compatible, with no deprecated APIs slated for removal in the target release.

### Release checks

- [ ] Run `mvn -B -ntp clean verify` and verify actual test execution counts.
- [ ] Review the security diff rule by rule; reject unintended privilege widening.
- [ ] Verify effective config under staging/production profiles, secrets, and trusted proxies.
- [ ] Record artifact digest, release notes, and test report; prepare a canary/rollback plan.
- [ ] Monitor 401/403/CSRF rejections, login error rates, and session issues after deployment.

**Conclusion:** Migrating from chained configuration to Lambda DSL is not “fixing syntax until warnings disappear.” In Spring Security Servlet, you must understand **`SecurityFilterChain` beans**, lambda configurer scopes, **`requestMatchers` vs `securityMatcher`**, behavioral shifts from `authorizeRequests` to `authorizeHttpRequests`, and use **security regression tests** to ensure the application still allows only the right identities to invoke the right endpoints and HTTP methods with proper CSRF and data-level authorization.
