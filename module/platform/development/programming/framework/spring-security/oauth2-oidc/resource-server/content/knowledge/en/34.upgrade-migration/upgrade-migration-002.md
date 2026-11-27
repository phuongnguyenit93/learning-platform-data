# Configuring `SecurityFilterChain` Instead of Legacy Configuration Patterns

Spring Security 6 shifts web security configuration to a model based on **declaring `SecurityFilterChain` beans**. Applications previously commonly extended `WebSecurityConfigurerAdapter` and overrode `configure(HttpSecurity)`, `configure(WebSecurity)`, or `configure(AuthenticationManagerBuilder)`. That adapter was deprecated in Spring Security 5.7 and removed in Spring Security 6.0. When upgrading, each responsibility must be moved to the corresponding bean or DSL.

For a Spring Security OAuth 2.0 / OIDC Resource Server, the new configuration is typically shorter: define a `SecurityFilterChain` bean, declare authorization rules, and enable JWT or opaque token support. However, migration is not merely renaming classes. You must preserve matcher ordering, filter chain selection, CSRF/CORS/session behavior, error handling, and token validators.

This lesson belongs to the **Upgrade and Migration** chapter. Examples use Spring Boot 3 and Spring Security 6 with the lambda DSL.

## 1. Why Was `WebSecurityConfigurerAdapter` Replaced?

The legacy configuration pattern concentrated multiple responsibilities inside a single subclass:

```java
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            .and()
            .oauth2ResourceServer()
                .jwt();
    }
}
```

This approach forced applications to extend an adapter to customize configuration. The new model uses beans and composition: Spring discovers `SecurityFilterChain` beans and registers them with `FilterChainProxy`.

Key benefits:

- Configuration is split into independent beans that are easier to read and test.
- Multiple filter chains can be defined for distinct URL scopes.
- No adapter subclass is needed to declare security policy.
- Dependencies are injected explicitly via method parameters.
- The lambda DSL makes nested configuration clear and reduces reliance on `.and()` chaining.

`WebSecurityConfigurerAdapter` was deprecated in Spring Security 5.7 and removed in Spring Security 6.0. When migrating to 6.x, classes extending the adapter must be converted; you cannot keep the old code as-is and only bump dependencies.

## 2. Converting `configure(HttpSecurity)` into a `SecurityFilterChain` Bean

New configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

Spring injects an `HttpSecurity` builder into the bean method. The application configures the builder and calls `build()` to create the `SecurityFilterChain`.

Points to remember:

- The bean method must return `SecurityFilterChain`.
- Call `http.build()` after declaring the full configuration.
- Do not call `build()` multiple times on the same builder.
- Do not instantiate `new HttpSecurity(...)` manually; use the builder provided by Spring.
- You can inject `JwtDecoder`, `AuthenticationManager`, `CorsConfigurationSource`, or handlers as bean method parameters.

In Spring Boot, when an application provides a `SecurityFilterChain` bean, Boot's default security configuration typically backs off via auto-configuration conditions. Therefore, the new bean must explicitly declare all rules the application intends to enforce.

## 3. Migrating Legacy Authorization DSL to `authorizeHttpRequests`

Several legacy APIs have been removed:

| Legacy Configuration | New Configuration |
| --- | --- |
| authorizeRequests() | authorizeHttpRequests(...) |
| antMatchers(...) | requestMatchers(...) |
| mvcMatchers(...) | requestMatchers(...) |
| WebSecurityConfigurerAdapter | SecurityFilterChain bean |
| @EnableGlobalMethodSecurity | @EnableMethodSecurity |
| DSL chain and() | Lambda DSL |

Legacy example:

```java
http.authorizeRequests()
    .antMatchers("/health", "/docs/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

New example:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/health", "/docs/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Rules are evaluated in declaration order. Specific rules must precede general ones. If `anyRequest().authenticated()` is placed before `/admin/**`, the subsequent rule never gets a chance to apply.

## 4. Distinguishing `securityMatcher` and `requestMatchers`

This is the most important distinction when using multiple filter chains:

- `securityMatcher(...)` decides **which filter chain handles the request**.
- `requestMatchers(...)` inside `authorizeHttpRequests` decides **authorization for the request after the chain is selected**.

Example:

```java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

    return http.build();
}
```

The chain above participates only for requests matching `/api/**`. Inside that chain, `/api/public/**` is permitted and the remaining API requests require authentication.

If `securityMatcher` is omitted, the chain defaults to matching every request. If a chain defines `securityMatcher` and it does not match the request, `FilterChainProxy` tries the next chain in order. If no chain matches, the request is not processed by the security filters in those chains.

## 5. When Are Multiple `SecurityFilterChain` Beans Needed?

Multiple chains make sense when an application has distinct security surfaces, for example:

- `/api/**` is a Resource Server using Bearer JWTs.
- `/admin/**` is a browser application using form login.
- `/actuator/health` is exposed under a separate policy.
- An internal endpoint requires mutual TLS or a dedicated authentication mechanism.

Example with API and browser in the same application:

```java
@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

The chain with the lower order number is evaluated first. The API chain handles only `/api/**`; other requests fall through to the browser chain. The browser chain has no `securityMatcher`, so it serves as the fallback for remaining requests.

Do not create multiple chains just to split configuration files. Each chain adds complexity around ordering, matchers, and filter behavior. Split chains only when authentication mechanisms or security policies genuinely differ.

## 6. `@Order` and Chain Selection Order

`FilterChainProxy` selects the first chain whose matcher matches the request. It does not combine multiple matching chains for the same request.

For example, if the first chain matches `/api/**`, a request to `/api/orders` is handled by that chain alone; a second chain does not add extra rules. Therefore:

1. Place chains with narrow scopes or special requirements first.
2. Place the catch-all/fallback chain last.
3. Do not let two chains match the same URL without a clear reason.
4. Test representative requests for every chain.
5. Also test URLs that do not match any specific chain.

If two beans lack an explicit order and both match, behavior may be unpredictable. Use `@Order` or `Ordered` to declare precedence explicitly.

## 7. Do Not Confuse `permitAll` with Ignoring Security Filters

In legacy configurations, applications often used:

```java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**");
}
```

The modern equivalent is `WebSecurityCustomizer`:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
```

However, for most public endpoints, prefer `permitAll()` inside the chain:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/assets/**", "/health").permitAll()
    .anyRequest().authenticated()
);
```

Difference:

- `permitAll()` still runs through the security filter chain. Security headers, CORS, security context, and other filters can operate as configured.
- `web.ignoring()` bypasses the Spring Security filter chain for matching requests.

Use `ignoring` only when you genuinely want to skip all security filters, typically for very simple static resources. Do not use `ignoring` for health endpoints, public APIs, or routes requiring security headers/CORS without weighing the consequences.

## 8. Migrating JWT Resource Server Configuration

A JWT Resource Server can be configured directly inside the chain:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Spring Boot can configure the decoder from an issuer URI:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

If the application needs a custom `JwtDecoder`, declare a bean:

```java
@Bean
JwtDecoder jwtDecoder() {
    return JwtDecoders.fromIssuerLocation(
        "https://identity.example.com/realms/shop");
}
```

When configuring a decoder manually, retain required validators such as issuer, timestamp, and audience. Moving to `SecurityFilterChain` does not automatically add audience validation if the application did not configure it previously.

## 9. Migrating Opaque Token Configuration

For opaque tokens, configure the chain with `opaqueToken`:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
```

Configure the introspection endpoint:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: INTROSPECTION_CLIENT_SECRET_FROM_SECRET_MANAGER
```

When migrating, preserve the introspection URI, client authentication, custom `OpaqueTokenIntrospector`, and metadata validation. If a dedicated introspector bean existed before, confirm the new chain still uses that exact bean.

## 10. Stateless APIs and Session Policy

Resource Server APIs typically receive Bearer tokens in the `Authorization` header and do not need to store HTTP sessions:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
```

`STATELESS` instructs Spring Security not to use a session to store `SecurityContext` across requests. It does not mean everything in the application is stateless; business sessions, databases, and caches can still exist.

Main options:

| Policy | Behavior |
| --- | --- |
| ALWAYS | Always create a session |
| IF_REQUIRED | Create a session when needed |
| NEVER | Do not create a new session, but may use an existing one |
| STATELESS | Never create or use a session to obtain SecurityContext |

Do not apply `STATELESS` to browser form login if the application needs a session to maintain login state. With multiple chains, set the session policy per chain.

## 11. CSRF: Do Not Disable It Just Because the App Has a REST API

Spring Security enables CSRF protection by default for unsafe HTTP methods. An API using Bearer tokens sent explicitly in the `Authorization` header—not automatically sent like cookies—can disable CSRF protection on the API chain.

Example for a pure Bearer-token API:

```java
http
    .securityMatcher("/api/**")
    .csrf(csrf -> csrf.disable())
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
```

Disable CSRF only when the chain truly does not rely on credentials automatically attached by browsers, such as session cookies or authentication cookies. If an API uses cookie authentication, browser sessions, or mixed authentication, keep CSRF protection enabled and configure an appropriate token repository/handler.

Do not disable CSRF application-wide simply because some routes are APIs. With multiple chains, keep CSRF enabled on the browser chain and disable it deliberately on the stateless bearer API chain.

## 12. CORS in the New Configuration

CORS must be handled before authorization for preflight requests. Enable CORS and inject a `CorsConfigurationSource`:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://app.example.com"));
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));
    configuration.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Do not use wildcard origins with credentials. Allow only required origins, methods, and headers. CORS is not authorization: it governs browser cross-origin access and does not replace token validation or scope checks.

## 13. Migrating Custom Authentication Entry Points and Access Denied Handlers

Legacy configurations could register handlers via the older DSL. The new configuration uses lambdas:

```java
http
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(customAuthenticationEntryPoint)
        .accessDeniedHandler(customAccessDeniedHandler)
    );
```

The two handlers serve different situations:

- `AuthenticationEntryPoint`: the request is unauthenticated or the Bearer credential is invalid.
- `AccessDeniedHandler`: the caller is authenticated but lacks permission.

For a Resource Server, the Bearer token failure handler can also emit a compliant `WWW-Authenticate` challenge. If replacing the default entry point, preserve required OAuth Bearer error response behavior and avoid leaking internal IdP details.

Do not use the same handler to turn every error into 403 or every error into 401. Status codes and challenges must accurately reflect the API's authentication/authorization semantics.

## 14. Migrating Custom Filters

If the legacy adapter added a filter:

```java
http.addFilterBefore(
    customFilter,
    UsernamePasswordAuthenticationFilter.class);
```

This configuration can still be used inside a `SecurityFilterChain` bean, but you should review the filter's position in the new chain. For a Resource Server, do not add a custom Bearer token parser when Spring Security already runs `BearerTokenAuthenticationFilter`, unless a specific protocol requirement demands it.

If a filter uses request attributes, MDC, or `SecurityContext`, ensure cleanup in `finally` and proper handling of async dispatches. Do not register the same filter both as a servlet container filter and inside the Spring Security chain if doing so causes it to execute twice.

If a filter must run before/after a specific security filter, use `addFilterBefore`, `addFilterAfter`, or `addFilterAt` per the contract and test actual execution order.

## 15. Migrating `configure(WebSecurity)` to `WebSecurityCustomizer`

Legacy configuration:

```java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**", "/favicon.ico");
}
```

Bean configuration:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/assets/**", "/favicon.ico");
}
```

Reminder: `ignoring` excludes requests from the Spring Security filter chain. For public APIs or endpoints needing security headers, using `permitAll` inside the chain is usually safer and more consistent.

Do not blindly port every `web.ignoring()` from the legacy configuration without checking its original rationale. Some routes may have been ignored previously just to work around static resource issues that are now cleanly handled with `permitAll()`.

## 16. Migrating `configure(AuthenticationManagerBuilder)` and `AuthenticationManager`

Legacy adapters often configured user details or authentication providers:

```java
@Override
protected void configure(AuthenticationManagerBuilder auth) throws Exception {
    auth.userDetailsService(userDetailsService)
        .passwordEncoder(passwordEncoder);
}
```

In the bean model, declare those components directly:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
```

Then configure the provider on the browser chain if form login is needed:

```java
http.authenticationProvider(daoAuthenticationProvider);
```

If `AuthenticationManager` needs to be exposed:

```java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
```

For an OAuth2 Resource Server, `UserDetailsService` or a password encoder is normally not needed just to verify access tokens. JWTs use decoders/validators; opaque tokens use an introspector. Keep `DaoAuthenticationProvider` only if the application still supports username/password login or a separate authentication flow.

## 17. Migrating `@EnableGlobalMethodSecurity`

If the legacy configuration used:

```java
@EnableGlobalMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true
)
```

Spring Security 6 uses:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

`@EnableMethodSecurity` enables pre/post annotations by default. `securedEnabled` enables `@Secured`; `jsr250Enabled` enables JSR-250 annotations such as `@RolesAllowed`.

Method security is an independent layer from request authorization in `SecurityFilterChain`. A controller may be allowed through the filter chain while a service method is still denied by `@PreAuthorize`. When migrating, retain both policy layers if the application relies on them.

## 18. Matcher Semantics and Path Matching After Migration

`requestMatchers` can select a matcher suited to the MVC and Spring Security environment. Do not assume every path expression has identical semantics to the legacy `AntPathRequestMatcher` across all applications.

Check:
- Context path and servlet path.
- Path variables and wildcard patterns.
- Trailing slash behavior.
- HTTP method constraints.
- Dispatcher types and error/forward dispatches.
- Multiple servlet mappings if the application has them.

Example rule with HTTP methods:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

If exact matcher semantics or path handling independent of MVC auto-selection are needed, declare an explicit `RequestMatcher`. What matters is testing actual URLs rather than eyeballing patterns.

## 19. `anyRequest()` and Deny-by-Default

A sensitive API should terminate its rules with an explicit policy:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
```

`anyRequest().authenticated()` only requires an authenticated caller and does not restrict operations by scope. If endpoints have distinct permissions, declare specific scopes/roles before the catch-all.

During migration, do not accidentally replace a legacy `denyAll()` rule with `authenticated()` just to avoid access errors. Preserve least-privilege policies and add tests for undeclared routes.

## 20. Security Headers and HTTPS

If the legacy configuration customized headers, migrate to the lambda DSL:

```java
http.headers(headers -> headers
    .frameOptions(frame -> frame.deny())
    .contentTypeOptions(Customizer.withDefaults())
    .httpStrictTransportSecurity(hsts -> hsts
        .includeSubDomains(true)
        .maxAgeInSeconds(31536000)
    )
);
```

Do not enable HSTS with `includeSubDomains` unless all subdomains are ready for HTTPS. A reverse proxy terminating TLS may require proper forwarded-headers/trusted-proxy configuration so Spring understands the scheme. Do not trust arbitrary `X-Forwarded-Proto` headers from clients.

Migration must preserve approved security headers and HTTPS redirect behavior. Do not assume they carry over automatically just because the new `SecurityFilterChain` builds cleanly.

## 21. CSRF, CORS, and Sessions with Multiple Chains

A typical design:

| Chain | Authentication | Session | CSRF | CORS |
| --- | --- | --- | --- | --- |
| /api/** | Bearer JWT/opaque | Stateless | Can be disabled if no cookie credentials | Per API origins |
| Browser routes | Form login/session | IF_REQUIRED | Enabled | Per browser app |
| Internal routes | Workload/mTLS or dedicated token | Per contract | Per credential mechanism | Usually tightly restricted |

Do not use a global configuration that accidentally applies browser session or CSRF policies to APIs. With multiple chains, each chain has its own matcher and policy; verify which chain actually handles each route.

## 22. Filter Order and Bean Order Are Two Different Things

`@Order` on a `SecurityFilterChain` bean determines chain selection order. `addFilterBefore`/`addFilterAfter` calls determine a custom filter's position inside a single chain.

Do not confuse:
- Chain order: the API chain is evaluated before the browser chain.
- Filter order: a custom correlation filter runs before or after a specific security filter.
- Authorization rule order: specific matcher rules are evaluated before catch-all rules.

These three ordering layers are independent, and any of them can alter behavior during migration.

## 23. Testing `SecurityFilterChain` with MockMvc

Use `MockMvc` to verify HTTP behavior through the filter chain:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleWithoutToken() throws Exception {
        mvc.perform(get("/api/public/status"))
            .andExpect(status().isOk());
    }

    @Test
    void protectedEndpointRejectsMissingToken() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
```

This is a skeleton example; a real endpoint or controller fixture is needed in the test context. Do not disable filters when the goal is to test `SecurityFilterChain`. A controller slice test may need to import the corresponding security configuration and resource server dependencies.

## 24. Testing JWT Authorities and Authorization Rules

Spring Security Test provides the `jwt()` request post-processor:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void readerCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void readerCannotCreateOrders() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"item\":\"book\"}"))
        .andExpect(status().isForbidden());
}
```

`jwt()` creates a mock `Authentication` for tests; it does not verify signatures, issuer, audience, or JWK retrieval. Use it to test request authorization and authority mapping. Add separate integration tests with signed JWTs or decoder fixtures to verify actual token validation.

## 25. Testing an Opaque Token Chain

For opaque tokens, the `opaqueToken()` post-processor can create a mock authentication for request tests:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void opaqueTokenWithReadScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}
```

This post-processor does not call the introspection endpoint. If integration testing of introspection is required, configure a mock endpoint and send a real Bearer token through the filter chain. Do not treat tests using `opaqueToken()` as proof that client credentials or the introspection URI work.

## 26. Testing Multiple Chains and Matcher Precedence

If an application has both API and browser chains, test each URL group:

| Request | Expected Chain | Behavior |
| --- | --- | --- |
| /api/orders | API chain | Bearer token, orders scope |
| /api/public/status | API chain | Public per API rule |
| /login | Browser fallback | Login page |
| /admin/users | Browser fallback | Session/role policy |
| /unknown | Fallback or deny | Per default policy |

Include tests for routes that do not match the first chain and must fall into the fallback chain. Otherwise, a route can accidentally fall outside every chain.

In tests, you can inject chain beans or use request behavior to verify which chain was chosen. Avoid only asserting that `@Order` exists; what must be proven is that the request passes through the intended authentication mechanism and authorization rules.

## 27. Step-by-Step Migration of Custom Filters, Handlers, and Matchers

Safe workflow:

1. List every `configure(...)` override in the legacy adapter.
2. Separate authorization rules, session, CSRF, CORS, headers, exception handling, and custom filters.
3. Identify which routes belong to the API, browser, or internal chain.
4. Create the initial `SecurityFilterChain` bean preserving existing behavior.
5. Convert matchers to `requestMatchers` and verify semantics.
6. Replace `web.ignoring()` with `permitAll()` when skipping the filter chain is unnecessary.
7. Convert `AuthenticationProvider`/`UserDetailsService` to beans if still used.
8. Migrate method security annotation enablement.
9. Add positive and negative tests for every route.
10. Compare before/after behavior in a test or staging environment.

Do not combine multiple policy changes with the framework migration at the same time if that would make it hard to isolate regressions.

## 28. Complete Migration Example for an API Resource Server

Complete configuration for a pure JWT Bearer API:

```java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

This configuration assumes:
- The API uses Bearer tokens in the `Authorization` header.
- Cookie/session authentication is not used on `/api/**`.
- CSRF is disabled only for this stateless chain.
- A CORS source has been declared.
- The issuer/JWT decoder is configured via properties or another bean.
- Each operation has its own scope.
- Undeclared routes are denied.

If any of these assumptions do not hold, adjust the policy instead of copying the example verbatim.

## 29. Is `@EnableWebSecurity` Required?

In Spring Boot applications, auto-configuration normally registers web security automatically when the dependency is present. `@EnableWebSecurity` can be used to enable web security configuration explicitly, though it is not always required on every configuration class.

What matters is that the `SecurityFilterChain` bean is discovered and registered by Spring. If an application has multiple security configurations, avoid redundant annotations or imports that obscure intent. Inspect auto-configuration conditions and the live context if bean conflicts arise.

## 30. Common Migration Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Keeping WebSecurityConfigurerAdapter on Spring Security 6 | Fails to compile | Migrate to SecurityFilterChain beans |
| Using antMatchers/authorizeRequests | Removed APIs | Use requestMatchers/authorizeHttpRequests |
| Confusing securityMatcher with requestMatchers | Chain or rule applies to wrong scope | Separate chain selection from authorization |
| Missing @Order with multiple chains | Requests may hit the wrong chain | Declare precedence explicitly |
| Missing fallback chain | Some routes bypass security filters | Add an appropriate catch-all chain |
| Using web.ignoring for public APIs | Skips headers/CORS/security filters | Use permitAll if the chain is still needed |
| Disabling CSRF application-wide | Browser/cookie flows become vulnerable to CSRF | Disable only on stateless bearer chains |
| Using STATELESS for form login | Session login fails to work as expected | Configure session policy per chain |
| Using only authenticated for all APIs | Tokens may lack business scopes | Declare authorities per method/resource |
| Losing custom JwtDecoder/introspector | Loses issuer/audience/metadata policies | Retain and test validator/delegate beans |
| Custom filter running twice | Duplicate work or context leaks | Check servlet registration vs. chain registration |
| Testing with jwt() and assuming the decoder works | Skips signature/JWK validation | Add signed-token integration tests |

## 31. Pre- and Post-Upgrade Checklist

Before migration:
- Record every `configure(...)` override and DSL rule.
- List public, protected, admin, and internal routes.
- Document authentication mechanisms and custom providers.
- Document session, CSRF, CORS, headers, and custom filters.
- Identify JWT/opaque token validators and authority converters.
- Document exception entry point/access denied behavior.

After migration:
- No remaining dependency on `WebSecurityConfigurerAdapter`.
- Every `SecurityFilterChain` has a clear matcher and order.
- Rules use `authorizeHttpRequests`/`requestMatchers`.
- `permitAll` and `ignoring` are chosen deliberately.
- CSRF/session policies match each chain.
- Resource Server still validates issuer, signature, expiry, audience, and scopes.
- Custom filters/handlers are registered exactly once.
- Method security is enabled if the application uses annotations.
- MockMvc tests cover success, 401, 403, and fallback routes.
- JWT/opaque integration tests still verify real decoder/introspection behavior.
- Monitor logs/metrics for unexpected 401/403/5xx rates after deployment.

## 32. References

- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): declaring `SecurityFilterChain` and multiple chains.
- [Spring Security 6.5 — Lambda DSL](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html): lambda DSL and modern configuration patterns.
- [Spring Security 6.5 — Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `requestMatchers`, and authorization rules.
- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): configuring a JWT Resource Server.
- [Spring Security 6.5 — Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): configuring opaque token introspection.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF protection and configuration.
- [Spring Security 6.5 — CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html): integrating CORS into the filter chain.
- [Spring Security 5.7 Release Notes](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter): rationale and replacements for the legacy adapter.

## 33. Conclusion

Migrating to `SecurityFilterChain` moves security configuration from adapter inheritance to explicit declarative beans. For a single chain, create a bean accepting `HttpSecurity`, convert the DSL to `authorizeHttpRequests`, enable JWT or opaque tokens, and call `build()`. For multiple chains, use `securityMatcher` to scope each chain and `@Order` to control which chain is evaluated first; use `requestMatchers` inside to enforce authorization.

When upgrading, intentionally preserve security behaviors: CSRF, CORS, session policy, exception handling, custom filters, token validators, and method security. Do not turn every rule into `authenticated`, do not bypass the filter chain for public routes that still need security headers, and do not disable CSRF for browser/cookie flows. Test with `MockMvc` and token fixtures to confirm the right chain, authorities, and HTTP responses.

**Key takeaway:** *A complete migration does more than compile against Spring Security 6; it preserves the exact chain selected, credentials verified, and authorization policy enforced for every route.*
