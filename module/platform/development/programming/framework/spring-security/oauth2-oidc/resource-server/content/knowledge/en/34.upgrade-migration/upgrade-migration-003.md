# Lambda DSL, Replaced Methods, and Version-Line Changes

## 1. Why Did Spring Security Change Its Configuration DSL?

Spring Security gradually moved from chained method-call configuration to the **Lambda DSL**. This change makes configurations easier to read, clearly delineates each configurer's boundaries, and prepares the API for newer versions.

Legacy configuration typically used `.and()` chaining:

~~~java
http
    .authorizeRequests()
        .antMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    .and()
    .oauth2ResourceServer()
        .jwt();
~~~

Modern configuration passes a lambda into each configurer:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

The Lambda DSL is not just a syntax change. It goes hand in hand with declaring security configuration via beans, selecting `SecurityFilterChain` instances, authorization APIs, request matchers, JWT/opaque token Resource Servers, method security, and the Java/Jakarta baseline.

When migrating, determine the exact Spring Security and Spring Boot versions in use. An example that is valid in Spring Security 5.x may already be deprecated or removed in 6.x/7.x.

## 2. Timeline of Key Changes

The table below summarizes major milestones when moving from legacy configuration to modern configuration. Cross-check with the release notes and API reference for your project's exact minor version before making changes.

| Version Line | Notable Changes | Migration Direction |
|---|---|---|
| Spring Security 5.2 | Lambda DSL introduced | Can start using lambdas for configurers |
| Spring Security 5.5+ | `authorizeHttpRequests` and `AuthorizationManager` become the new direction | Gradually migrate from `authorizeRequests` |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` deprecated | Declare `SecurityFilterChain` beans |
| Spring Security 5.8 | Transitional APIs provided for 6.x preparation, including `requestMatchers`/`securityMatcher` | Adopt new APIs before upgrading major version |
| Spring Security 6.0 | `WebSecurityConfigurerAdapter` and legacy matchers such as `antMatchers`, `mvcMatchers`, `regexMatchers` removed; Jakarta namespace adopted | Move to bean configuration and new matchers |
| Spring Security 6.1 | No-arg configurer methods deprecated in preparation for 7.0 | Use lambdas or `Customizer.withDefaults()` |
| Spring Security 7.x | Lambda DSL required; previously deprecated APIs scheduled for removal are no longer usable | Remove no-arg configurer calls and legacy DSL |

Some changes are introduced in a minor release and removed in the next major release. Therefore, do not assume every legacy API was removed immediately in 6.0 or that all 6.x applications emit the same warnings.

### 2.1. Spring Security 5.2: Lambda DSL

The Lambda DSL appeared in Spring Security 5.2. In 5.x releases, legacy code can still run, but lambdas clearly show the scope of each configuration group.

~~~java
http
    .authorizeRequests(authorize -> authorize
        .antMatchers("/health").permitAll()
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

At this stage, authorization DSL names and matchers can still be the legacy APIs. What is new is passing lambdas. When preparing for further migration, also move the DSL/matchers to modern APIs if the current version supports them.

### 2.2. Spring Security 5.7: Replacing `WebSecurityConfigurerAdapter`

`WebSecurityConfigurerAdapter` was deprecated in Spring Security 5.7. Applications can keep running during the transition period, but should move to explicit beans before upgrading to 6.x.

### 2.3. Spring Security 5.8: Useful Transitional Release

Spring Security 5.8 provides new APIs to reduce the number of simultaneous changes needed when upgrading to 6.0. It is a helpful migration checkpoint:

- Switch from `antMatchers`/`mvcMatchers`/`regexMatchers` to `requestMatchers`.
- Switch filter-chain selection matchers to `securityMatcher`.
- Move off `WebSecurityConfigurerAdapter`.
- Update configurations to the Lambda DSL.

If the application can first upgrade to a compatible 5.8 release, resolve warnings and run tests there before bumping the Spring Boot/Spring Security major version.

### 2.4. Spring Security 6.x and 7.x

Spring Security 6 requires a newer Java/Jakarta baseline and removes several APIs deprecated in 5.x. Spring Security 6.1 further marks no-arg configurer methods for removal in 7.0.

For Spring Security 7, write configurations using the Lambda DSL from the start. Avoid calling methods like `http.csrf()`, `http.oauth2ResourceServer()`, or `http.authorizeHttpRequests()` without a lambda if the API version has removed those overloads.

## 3. Understanding Lambda DSL Structure

### 3.1. Each Lambda Configures One Configurer

~~~java
http
    .csrf(csrf -> csrf.disable())
    .cors(cors -> cors.configurationSource(corsConfigurationSource))
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

Each lambda has a distinct purpose:

- `csrf` configures CSRF protection.
- `cors` configures CORS.
- `session` configures session policy.
- `authorize` configures authorization rules.
- `oauth2` configures the OAuth 2.0 Resource Server.
- `jwt` configures the JWT decoder/converter inside Resource Server.

Reading the code lambda by lambda makes it clear which configurer is being modified.

### 3.2. No Need for `.and()` to Return to `HttpSecurity`

In the legacy DSL, `.and()` was commonly used to exit the current configurer and return to `HttpSecurity`:

~~~java
http
    .authorizeRequests()
        .anyRequest().authenticated()
    .and()
    .httpBasic();
~~~

With the Lambda DSL, the configurer closes when the lambda ends:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Do not append `.and()` at the end of a lambda. Nor do you need to call `and()` to move from authorization configuration to Resource Server.

### 3.3. `Customizer.withDefaults()` and Empty Lambdas

When you only want to enable a configurer with defaults:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

You can import:

~~~java
import org.springframework.security.config.Customizer;
~~~

Some APIs allow an equivalent empty lambda:

~~~java
.httpBasic(Customizer.withDefaults())
~~~

Not all configurers share identical overloads or default behaviors. Consult the API reference for the running version instead of extrapolating from another configurer.

### 3.4. Extracting Helper Methods When Lambdas Grow Long

The Lambda DSL does not require cramming all configuration into a single method. Logic can be split by responsibility:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {

    configureApiAuthorization(http);
    configureResourceServer(http, jwtDecoder);

    return http.build();
}

private void configureApiAuthorization(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    );
}

private void configureResourceServer(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {

    http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.decoder(jwtDecoder))
    );
}
~~~

This example only illustrates decomposition; in real projects, structure helpers so configurations are not called twice and matcher ordering is preserved.

## 4. Replacing `WebSecurityConfigurerAdapter` with `SecurityFilterChain`

### 4.1. Legacy Configuration

A Servlet Resource Server configuration might previously have been written as:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            .and()
            .oauth2ResourceServer()
                .jwt();
    }
}
~~~

Problems when upgrading:

- `WebSecurityConfigurerAdapter` was deprecated and then removed.
- `authorizeRequests`/`antMatchers` belong to the legacy DSL.
- No-arg configurer methods are no longer recommended.
- Configuration depends on inheritance and method overrides, making it harder to see which bean owns the chain.

### 4.2. New Bean-Based Configuration

Migrate to `SecurityFilterChain`:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http) throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

`HttpSecurity` is supplied by Spring to construct the chain. Calling `build()` returns the `SecurityFilterChain` that Spring Security registers in the application context.

No adapter inheritance is needed. Dependencies such as `JwtDecoder`, converters, authentication providers, or CORS configuration can be injected directly into the bean method.

### 4.3. Explicit JWT Decoder Configuration

When custom validators are needed:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .decoder(jwtDecoder)
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        )
        .build();
}
~~~

This keeps the JWT decoder and converter as separate, testable, and reusable dependencies. For opaque tokens, the DSL switches to `opaqueToken(...)` with an appropriate `OpaqueTokenIntrospector`.

### 4.4. Multiple `SecurityFilterChain` Beans

For multiple endpoint types, declare multiple chains:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Spring Security selects the matching chain by order and matcher. The API chain applies only to `/api/**`; the web chain handles the rest.

**`securityMatcher` and `requestMatchers` serve different roles:**

- `securityMatcher(...)` selects the entire `SecurityFilterChain` for a request.
- `requestMatchers(...)` selects authorization rules inside the already-selected chain.

Confusing the two APIs can send endpoints to a chain without Resource Server support, or leave rules written that are never evaluated.

## 5. Replacing Legacy Authorization DSL and Request Matchers

### 5.1. `authorizeRequests` Moves to `authorizeHttpRequests`

~~~java
http.authorizeRequests()
    .antMatchers("/api/public/**").permitAll()
    .antMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated();
~~~

Converts to:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

`authorizeHttpRequests` uses `AuthorizationManager` and `AuthorizationFilter`. This is a newer authorization model that handles `Authentication` differently from legacy `FilterSecurityInterceptor`/`AccessDecisionManager`. Do not just rename the method and assume legacy custom voters or metadata sources automatically behave identically.

### 5.2. `antMatchers`, `mvcMatchers`, and `regexMatchers` Move to `requestMatchers`

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers("/legacy/[0-9]+").permitAll()
);
~~~

String overloads of `requestMatchers` choose a matcher based on the Spring MVC/Spring Security environment and version; do not assume identical semantics to legacy `antMatchers`, `mvcMatchers`, or regex matchers in all cases. If rules depend on servlet paths, path patterns, HTTP methods, context paths, or custom matchers, configure an explicit `RequestMatcher` and verify with request tests.

### 5.3. `securityMatcher` vs. `requestMatchers`

| API | Effect |
|---|---|
| `http.securityMatcher("/api/**")` | Selects the entire SecurityFilterChain for the request |
| `authorize.requestMatchers("/api/admin/**")` | Selects an authorization rule inside the chain |
| `WebSecurityCustomizer.ignoring()` | Bypasses the Spring Security filter chain |
| `permitAll()` | Still passes through the security chain without requiring authentication |

A common migration mistake is converting `http.antMatcher("/api/**")` into authorization `requestMatchers("/api/**")`. Those two are not equivalent. When the goal is filter-chain selection, use `securityMatcher`.

### 5.4. Verifying Matcher Ordering

Authorization rules are evaluated in declaration order. Placing a broad rule first can shadow a more specific rule:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

In the example above, requests to `/api/admin/**` already match `/api/**` before reaching the ADMIN rule. Place specific rules first:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

After migration, test overlapping paths, differing HTTP methods, trailing slashes, encoded paths, and context paths against the API contract.

### 5.5. Static Resources: `ignoring` or `permitAll`?

Legacy configurations often skipped static assets with:

~~~java
web.ignoring().antMatchers("/css/**", "/js/**");
~~~

The newer equivalent can use:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/static/**");
}
~~~

However, `ignoring` removes requests from the security filter chain. Unless bypassing the chain is specifically required, `permitAll` is usually preferred so requests still receive security headers and necessary filter behaviors:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Choose based on application requirements rather than mechanically porting every `web.ignoring()` call without understanding why it bypassed security.

## 6. Deprecated No-Arg Configurer Methods

Starting in Spring Security 6.1, many no-arg configurer methods without lambdas were deprecated in preparation for 7.0. Migrate to overloads accepting a lambda or `Customizer.withDefaults()`.

| Legacy Call | Lambda DSL |
|---|---|
| `http.csrf().disable()` | `http.csrf(csrf -> csrf.disable())` |
| `http.cors()` | `http.cors(Customizer.withDefaults())` |
| `http.httpBasic()` | `http.httpBasic(Customizer.withDefaults())` |
| `http.formLogin()` | `http.formLogin(Customizer.withDefaults())` |
| `http.logout()` | `http.logout(Customizer.withDefaults())` |
| `http.sessionManagement().sessionCreationPolicy(...)` | `http.sessionManagement(session -> session.sessionCreationPolicy(...))` |
| `http.exceptionHandling().authenticationEntryPoint(...)` | `http.exceptionHandling(errors -> errors.authenticationEntryPoint(...))` |
| `http.oauth2ResourceServer().jwt()` | `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` |
| `http.headers().frameOptions().sameOrigin()` | `http.headers(headers -> headers.frameOptions(frame -> frame.sameOrigin()))` |

Combined configuration example:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .csrf(csrf -> csrf.disable())
        .cors(Customizer.withDefaults())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(new BearerTokenAuthenticationEntryPoint())
            .accessDeniedHandler(new BearerTokenAccessDeniedHandler())
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

This example is for a stateless API using Bearer tokens. Disable CSRF only if your threat model and credential transport permit it. If the application also uses browser sessions/cookie authentication, do not disable CSRF merely because some endpoints use JWTs.

Specific methods may vary by minor version or configurer. Whenever the compiler flags a method as deprecated-for-removal, switch to the lambda overload provided by your current API version.

## 7. Authentication Configuration Changes After Removing the Adapter

### 7.1. Legacy Configuration in `configure(AuthenticationManagerBuilder)`

Applications previously often overrode:

~~~java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth
        .userDetailsService(userDetailsService)
        .passwordEncoder(passwordEncoder);
}
~~~

Once `WebSecurityConfigurerAdapter` is removed, you no longer override this method. Declare authentication dependencies as explicit beans instead.

### 7.2. Declaring `UserDetailsService` and `PasswordEncoder`

~~~java
@Bean
UserDetailsService userDetailsService(UserRepository users) {
    return username -> users.findByUsername(username)
        .orElseThrow(() ->
            new UsernameNotFoundException("User not found")
        );
}

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

This example shows how user lookup and password hashing are separated. Choose an encoder matching application policy and configure password migration/upgrades properly. Never store plaintext passwords or use weak encoders to simplify tests.

### 7.3. Declaring `AuthenticationProvider`

When explicit DAO authentication configuration is needed:

~~~java
@Bean
AuthenticationProvider authenticationProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider();

    provider.setUserDetailsService(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
~~~

You can then register the provider on the chain:

~~~java
@Bean
SecurityFilterChain webSecurity(
        HttpSecurity http,
        AuthenticationProvider authenticationProvider)
        throws Exception {

    return http
        .authenticationProvider(authenticationProvider)
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

There is no need to build an `AuthenticationManagerBuilder` manually just to replace the legacy override. Use provider beans or the `AuthenticationManager` mechanism appropriate for the actual authentication flow.

### 7.4. Exposing `AuthenticationManager` Only When Needed

If a controller/service or integration needs to inject `AuthenticationManager`, expose it via `AuthenticationConfiguration`:

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration)
        throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Expose it only when callers actually require it. For a JWT Resource Server, Spring Security typically configures the authentication manager automatically from `JwtDecoder` and the converter; do not construct a manual `AuthenticationManager` without a specific requirement.

## 8. Changes in Method Security

### 8.1. `EnableGlobalMethodSecurity` Moves to `EnableMethodSecurity`

Legacy configuration:

~~~java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class MethodSecurityConfig {
}
~~~

New configuration:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@EnableMethodSecurity` is the modern annotation for enabling method authorization. Note the default difference: `prePostEnabled` defaults to `true` on `@EnableMethodSecurity`, whereas legacy setups often had to set `prePostEnabled = true` explicitly. During migration, declare options explicitly to preserve the exact policy.

If the application uses `@Secured` or JSR-250 annotations, enable them explicitly:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Do not enable extra annotation mechanisms just because an online example does. Retain only the mechanisms the application actually uses.

### 8.2. Preserving `PreAuthorize`/`PostAuthorize` Semantics

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto getOrder(UUID id) {
    return service.load(id);
}
~~~

Migrating the annotation does not automatically fix expressions. Verify that method proxies are created and invoked through the Spring bean proxy; check whether self-invocation bypasses the proxy; ensure parameter names are preserved for expressions like `#tenantId`; confirm expressions read the expected principal type after Resource Server authentication; and check whether overloaded methods carry distinct policies.

Method security is an additional authorization layer; do not remove URL authorization or tenant/resource checks just because annotations are present.

### 8.3. Checking Authorization Order and Interaction

When both request-level and method-level authorization exist, a request can be rejected in the filter chain before the method is invoked. Tests should make clear which layer is enforcing which condition.

Do not write a test that only asserts 403 and conclude the method expression worked. The filter chain might have denied the request earlier. For method-security tests, invoke the method via the Spring-managed bean with an appropriate `Authentication` context configured.

## 9. Updating OAuth 2.0 Resource Server Configuration

### 9.1. JWT Resource Server

Legacy call:

~~~java
http
    .oauth2ResourceServer()
        .jwt();
~~~

Lambda DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

When custom decoders and converters are needed:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .decoder(jwtDecoder)
        .jwtAuthenticationConverter(jwtAuthenticationConverter)
    )
);
~~~

Changing the DSL does not automatically preserve trust policies safely. Retain and verify issuer validators, audience validators, timestamp validators and clock skew, algorithm/key trust, claim-to-authority converters, custom principal mapping, and invalid-token error handling.

Do not delete validators just to resolve compile errors during migration.

### 9.2. Opaque Token Resource Server

Legacy call:

~~~java
http
    .oauth2ResourceServer()
        .opaqueToken();
~~~

Lambda DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(opaqueTokenIntrospector)
    )
);
~~~

When relying solely on default auto-configuration:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Verify the introspection URI, client authentication, timeouts, error mapping, authorities, and principal attributes. Do not accidentally switch from opaque tokens to JWTs or vice versa just to match a sample snippet.

### 9.3. Bearer Token Resolver and Custom Converter

If the application customizes how tokens are extracted:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(bearerTokenResolver)
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter)
    )
);
~~~

Preserve the policy governing where tokens may appear. By standard convention, access tokens are sent in the `Authorization` header. If an application allows query parameters or form parameters, evaluate the risk of token leakage via URLs, browser history, referrers, and access logs.

### 9.4. Legacy Spring Security OAuth Project

Distinguish modern Spring Security OAuth Resource Server from the legacy `spring-security-oauth` project. Classes such as `@EnableResourceServer`, `ResourceServerConfigurerAdapter`, `ResourceServerTokenServices`, or `JwtAccessTokenConverter` belong to the legacy model.

Migration typically moves to Spring Security's built-in Resource Server support:

- Use `SecurityFilterChain` instead of `ResourceServerConfigurerAdapter`.
- Use `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` for JWTs.
- Use `oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` for opaque tokens.
- Use `JwtDecoder`/`JwtAuthenticationConverter` or `OpaqueTokenIntrospector` depending on token format.
- Convert custom token services/claim mappings into corresponding decoders, validators, converters, or introspectors.

This is an architectural migration, not a simple package rename. Inventory custom grants, token enhancers, claims, authentication details, exception mappings, and downstream principal contracts before removing the legacy dependency.

## 10. Servlet and WebFlux Have Separate DSLs

Do not apply Servlet examples to a reactive stack merely by swapping client types.

| Component | Servlet | WebFlux |
|---|---|---|
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain type | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Enable annotation | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Authorization DSL | `authorizeHttpRequests` | `authorizeExchange` |
| Request type | `HttpServletRequest` | `ServerWebExchange` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspector | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

WebFlux example:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder jwtDecoder) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtDecoder(jwtDecoder))
        )
        .build();
}
~~~

In WebFlux, the authorization DSL is `authorizeExchange` and matchers use `pathMatchers` or `matchers` depending on API version. Do not copy Servlet's `authorizeHttpRequests` onto `ServerHttpSecurity`.

If an application includes both MVC and WebFlux dependencies, identify which stack the application actually runs and test the matching chain. Do not rely solely on which dependencies are present on the classpath.

## 11. Platform Changes When Upgrading to Spring Security 6

### 11.1. Java and Jakarta Namespace

Spring Security 6 is built on Spring Framework 6 and Jakarta EE APIs. Applications upgrading from Spring Boot 2/Spring Security 5 to Boot 3/Security 6 must migrate the relevant Jakarta packages.

Servlet example:

~~~java
// Before
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;

// After
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
~~~

Similarly, review other Jakarta APIs used by the application such as validation, persistence, and annotations. Do not blindly replace every `javax.` occurrence with `jakarta.`; several Java SE packages remain in the `javax` namespace.

### 11.2. Aligning Spring Boot and Spring Security Versions

Spring Boot manages Spring Framework, Spring Security, and related dependency versions via dependency management/BOM. Normally, use the versions managed by the Spring Boot BOM rather than manually pinning individual Spring Security artifacts.

Gradle example:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

When using the Spring Boot plugin/BOM, avoid specifying separate versions for individual `spring-security-*` artifacts unless there is a verified compatibility reason.

Misaligned version overrides can cause linkage errors, `NoSuchMethodError`, `ClassNotFoundException`, or divergent compile/runtime behavior.

### 11.3. Inspecting the Dependency Tree

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-resource-server --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Confirm that Spring Security modules belong to one compatible release train, starters and test dependencies do not pull conflicting versions, and no unintended legacy modules remain.

## 12. Step-by-Step Migration Process

Avoid changing Java, Spring Boot, Spring Security, Jakarta, matchers, and authorization policies simultaneously in one massive commit if stages can be separated.

### Step 1 — Capture a Baseline

Record the Java version, Spring Boot version, Spring Security module versions, Servlet vs. WebFlux stack, number of `SecurityFilterChain` instances, JWT vs. opaque token usage, custom decoders/converters/introspectors/resolvers/validators, method security annotations, and existing tests.

Save the dependency tree and test results before migration as a baseline for comparison.

### Step 2 — Upgrade to a Compatible Transitional Release if Needed

If starting from an older Spring Security 5.x release, consider upgrading to 5.8 before the major jump. Use the transitional APIs to eliminate legacy matchers and adapters, then run tests.

Do not force an unsupported project onto an intermediate version incompatible with its current Java/Boot setup. Follow an upgrade path supported by the Spring Boot release train.

### Step 3 — Replace `WebSecurityConfigurerAdapter`

Create a `SecurityFilterChain` bean for each chain. Move URL rules, Resource Server config, CORS, CSRF, sessions, exception handling, and custom providers into the bean.

If multiple adapters existed previously, verify how many chains they produced and in what order. Do not merge multiple chains into one if each has different matchers, authentication mechanisms, or stateless/session policies.

### Step 4 — Migrate the Authorization DSL and Matchers

Replace `authorizeRequests` with `authorizeHttpRequests`. Replace legacy matchers with `requestMatchers` or an appropriate `RequestMatcher`. Move chain-selection matchers to `securityMatcher`.

Verify path semantics, HTTP methods, context paths, servlet paths, and rule ordering.

### Step 5 — Convert No-Arg Configurer Calls

Use lambdas for CSRF, CORS, headers, session management, exception handling, OAuth2 Resource Server, form login, and HTTP Basic. Clear deprecated-for-removal warnings.

### Step 6 — Migrate Authentication and Method Security

Replace `AuthenticationManagerBuilder`/adapter overrides with `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider`, or `AuthenticationManager` beans. Migrate method security to `@EnableMethodSecurity` and retain enabled flags.

### Step 7 — Upgrade Java/Jakarta Baseline and Dependencies

Ensure Java, Spring Boot, Spring Framework, and Spring Security versions are compatible. Update Jakarta imports across affected APIs. Verify no Security module is pinned out of alignment.

### Step 8 — Run Integration Tests with Real Tokens

Send signed JWT test keys through the filter chain or use an appropriate introspection stub. Verify issuer, audience, signature, expiry, scope mapping, principal type, 401/403 responses, and multiple filter chains.

### Step 9 — Canary Deploy and Observe

Monitor authentication successes/failures, 401/403 rates, decoder/JWKS errors, introspection latency, session behavior, and endpoint matchers. Compare old and new nodes before completing the rollout.

## 13. Post-Migration Regression Testing

### 13.1. Testing URL Authorization

For each chain, verify:

- Public endpoints remain public.
- Protected endpoints still require authentication.
- Scope/role mappings remain intact.
- Specific matchers are not shadowed by broad rules.
- Different HTTP methods enforce the expected rules.
- Endpoints outside the API chain are not unintentionally opened.
- CSRF/CORS/session behavior remains accurate for each client type.

### 13.2. Testing the JWT Resource Server

Send compact JWTs signed with a test key via the `Authorization` header and confirm:

- The configured decoder is actually invoked.
- Issuer, audience, signature, and timestamp validations still execute.
- Custom `JwtAuthenticationConverter` produces the same authorities as before.
- Controllers receive the expected principal/claims.
- Invalid tokens return 401; valid tokens lacking permissions return 403.
- Key rotation/JWKS refresh behavior did not change unexpectedly.

MockMvc `jwt()` or WebFlux `mockJwt()` are useful for principal/authorization tests, but they inject a mock `Authentication` and bypass the decoder. Do not rely on them as proof of signature validation.

### 13.3. Testing Opaque Tokens

If the application uses opaque tokens:

- The introspection endpoint and client authentication remain accurate.
- Active principals have the expected attributes/authorities.
- Inactive tokens return authentication failures.
- Network/timeout errors are distinguished from inactive tokens.
- Principal type and application mapping are unchanged.
- Requests still follow the intended Bearer token extraction path.

### 13.4. Testing Method Security

Invoke methods through Spring-managed beans. Test both allow and deny cases, parameter expressions, tenant ownership, and self-invocation cases if the code makes internal method calls.

If `@EnableGlobalMethodSecurity` was used previously, separately test `@PreAuthorize`, `@PostAuthorize`, `@Secured`, and JSR-250 according to the migrated flags.

### 13.5. Testing Multiple `SecurityFilterChain` Beans

For each chain, send requests that match and do not match its matcher. Confirm the intended chain handles each request, authentication mechanisms are not mixed, and `@Order` precedence does not route endpoints into an unintended catch-all.

## 14. Common Migration Pitfalls

### Pitfall 1 — Renaming Methods While Leaving Legacy DSL Intact

Changing `authorizeRequests` to `authorizeHttpRequests` while still calling no-arg configurers or removed matchers. Migrate the authorization DSL, matchers, and configurer calls together.

### Pitfall 2 — Still Extending `WebSecurityConfigurerAdapter`

The adapter has been removed from Spring Security 6. Move configuration to `SecurityFilterChain` beans and required authentication beans.

### Pitfall 3 — Using `requestMatchers` to Select a Chain

`requestMatchers` defines authorization rules inside a chain. Use `securityMatcher` to determine which chain handles a request.

### Pitfall 4 — New Matchers Differing in Semantics from Legacy Matchers

String overloads may choose a matcher based on classpath/version. Test context paths, servlet paths, MVC matching, and HTTP methods. Use an explicit `RequestMatcher` when specific semantics are required.

### Pitfall 5 — Replacing `ignoring` with `permitAll` Without Checking Filter Behavior

`permitAll` still runs security filters; `ignoring` bypasses the chain. Choose based on security headers, CORS, logging, and other filter requirements.

### Pitfall 6 — Disabling CSRF Application-Wide

Stateless APIs using Bearer headers may have a different CSRF policy from browser sessions/cookies. Do not disable CSRF for the entire application solely because it includes a Resource Server.

### Pitfall 7 — Forgetting `@EnableMethodSecurity` New Defaults

`@EnableMethodSecurity` enables pre/post annotations by default. Declare flags explicitly to preserve intended behavior and test each annotation mechanism.

### Pitfall 8 — Pinning Spring Security Modules at Mismatched Versions

Use the Spring Boot BOM or compatible dependency management. Inspect the runtime dependency tree, not only the compile classpath.

### Pitfall 9 — Dropping Validators When Switching Resource Server DSL

Retain issuer, audience, timestamp, and custom validators. Compiling cleanly does not prove trust policies are intact.

### Pitfall 10 — Running Only Unit Tests

Unit tests do not verify that the filter chain, decoder, request matchers, and method security are wired properly. Run integration tests through the application's real HTTP stack.

## 15. Legacy-to-Modern API Mapping Table

| Legacy API / Configuration Style | Modern API / Configuration Style | Migration Notes |
|---|---|---|
| `WebSecurityConfigurerAdapter` | `SecurityFilterChain` bean | Keep individual chains and ordering distinct |
| `configure(HttpSecurity)` | `@Bean SecurityFilterChain` | Return the result of `http.build()` |
| `configure(WebSecurity)` | `WebSecurityCustomizer` | Ignore only when bypassing filters is genuinely needed |
| `authorizeRequests` | `authorizeHttpRequests` | AuthorizationManager model |
| `antMatchers` / `mvcMatchers` / `regexMatchers` | `requestMatchers` | Verify matcher semantics |
| `http.antMatcher` / `mvcMatcher` | `securityMatcher` | Selects the chain, not an authorization rule |
| No-arg configurer methods | Lambdas / `Customizer.withDefaults()` | Avoid deprecated-for-removal methods |
| `configure(AuthenticationManagerBuilder)` | `AuthenticationProvider` / `AuthenticationManager` beans | Migrate user lookup and password encoder |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Preserve flags and verify defaults |
| `oauth2ResourceServer().jwt()` | `oauth2ResourceServer(o -> o.jwt(...))` | Keep decoder, validators, and converter |
| `oauth2ResourceServer().opaqueToken()` | `oauth2ResourceServer(o -> o.opaqueToken(...))` | Keep introspector and principal mapping |
| Legacy `@EnableResourceServer` | Built-in Resource Server support | Architectural migration |
| `javax.servlet.*` | `jakarta.servlet.*` | Applies when moving to Jakarta baseline |

This table is a directional guide, not an automated replacement script. Specific overloads can vary across minor releases; the compiler and target version's API reference are the final authority.

## 16. Complete Migration Example for a Servlet Resource Server

A modern JWT API configuration can look like this:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtDecoder jwtDecoder,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .decoder(jwtDecoder)
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)
                )
            )
            .build();
    }
}
~~~

This example targets a stateless API accepting only Bearer tokens in headers. If the application uses cookies/sessions, evaluate CSRF before disabling it. If browser routes exist, place them in a separate chain with appropriate session/login policies.

The decoder/converter beans must retain the system's validators and claim mappings. Do not consider migration finished merely because code compiles with lambdas if an audience validator or custom authority mapping was dropped.

## 17. Checking Version Changes in Build and IDE

When upgrading versions, read compiler warnings instead of blindly running find-and-replace on API names. Some methods exist in the current release but are deprecated-for-removal; others have already been removed completely.

Helpful workflow:

1. Verify the Spring Boot plugin/BOM and Java toolchain.
2. Run a build to surface removed APIs.
3. Enable or inspect deprecation warnings for Spring Security.
4. Locate legacy adapter, matcher, and configurer classes.
5. Inspect runtime and test dependency trees.
6. Run security chain tests after each group of changes.

Useful repository searches include:

~~~bash
rg -n "WebSecurityConfigurerAdapter|authorizeRequests|antMatchers|mvcMatchers|regexMatchers" src
rg -n "EnableGlobalMethodSecurity|oauth2ResourceServer\\(\\)|csrf\\(\\)|headers\\(\\)" src
rg -n "EnableResourceServer|ResourceServerConfigurerAdapter|JwtAccessTokenConverter" .
~~~

Adjust paths to match your project layout. These commands only locate potential migration sites; they do not replace reading the surrounding context of each match.

## 18. Migration Completion Checklist

- [ ] Compatible Spring Boot, Spring Framework, Spring Security, and Java versions are locked in.
- [ ] Spring Security modules are managed within the same release train.
- [ ] No classes extend `WebSecurityConfigurerAdapter`.
- [ ] Every `SecurityFilterChain` has a proper matcher and `@Order`.
- [ ] `securityMatcher` and `requestMatchers` are properly distinguished.
- [ ] Legacy authorization DSL and removed matchers have been replaced.
- [ ] No deprecated-for-removal no-arg configurer calls remain.
- [ ] `WebSecurityCustomizer` and reasons for `ignoring` have been reviewed.
- [ ] CSRF/CORS/session behavior fits each client type.
- [ ] `AuthenticationProvider`/`AuthenticationManager` beans are registered properly.
- [ ] Method security uses the new annotation with matching flags.
- [ ] JWT decoder still validates issuer, audience, signature, and timestamps.
- [ ] Authority converter and principal claims preserve the contract.
- [ ] Opaque introspection still uses the right endpoint, client auth, and mapping.
- [ ] Legacy Spring Security OAuth components have been inventoried and intentionally migrated.
- [ ] Jakarta imports are updated across affected APIs.
- [ ] Unit, MockMvc/WebTestClient, and signed-token integration tests all pass.
- [ ] 401/403, matcher ordering, and multiple-chain tests are verified.
- [ ] Canary/production rollout includes metrics to catch authentication regressions.

## 19. Conclusion

Migrating to the Lambda DSL should be carried out alongside migrating configuration APIs deprecated or removed in each Spring Security release line.

The most important steps are replacing the adapter with `SecurityFilterChain` beans, converting authorization to `authorizeHttpRequests` and `requestMatchers`, using `securityMatcher` for chain selection, converting no-arg configurer calls to lambdas, updating method security, and preserving Resource Server decoders/validators/converters.

Use the version matrix, compiler warnings, dependency tree, and integration tests to verify the migration. A new configuration is only complete when requests still traverse the right filter chain, tokens are verified against the existing trust policy, and authorization behavior does not change unintentionally.

### References

- [Spring Security Reference — Lambda DSL](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security Reference — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — Migration Guides](https://docs.spring.io/spring-security/reference/migration/index.html)
- [Spring Boot Reference — Dependency Versions](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
